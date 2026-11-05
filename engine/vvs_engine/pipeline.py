"""Pipeline orchestration: RAW PDF -> DrawingProfile -> annotations -> designations -> leaders -> attachments
-> pipe families -> topology -> physical pipes -> measurement -> quantities -> artifacts."""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any, Callable

from .geometry.core import stable_id
from .pdf.extract import RawDocument, RawPage, extract_document
from .geometry.core import GridIndex, dist, point_seg_distance
from .pipes.representation import (Prim, RepresentationFamily, build_graph, chains, collect_prims, describe_family, page_symbols,
                                   duplicate_overlaps, family_key,
                                   stroke_family,
                                   graph_tolerances, split_prims_at_points)
from .profile.layers import compute_layer_stats
from .profile.hatch import HatchFamily, discover_hatch, inside_hatch
from .semantics.annotation import (AnnotationBlock, Designation, build_blocks, extract_designations,
                                    free_segments, merge_lines, one_reading_per_place)
from .text.model import project, row_axes
from .semantics.attachment import (GeometryIndex, PathsByPlace, PipeCodeAnchor, family_of, layer_system_tokens,
                                   leader_contacts, resolve_block, system_layer_match)
from .semantics.legend import (DrawingLegend, adopt, assign_roles, number_as_listed, opens_with, read_legend,
                               roles_of)
from .semantics.declarations import Declarations, read_declarations
from .semantics.grammar import split_tokens

# Under measurement: whether a dimension on the row below means the label names a stack and nothing else. Off
# until the reference set says otherwise - an earlier measurement on four drawings said stripping the run
# fragmented the takeoff, and the set is now thirty-three.
DN_ROWS_ARE_VERTICAL_ONLY = os.environ.get("VVS_DN_ROWS_VERTICAL_ONLY") == "1"
from .semantics.leaders import Leader, annotation_layers, discover_leaders, leader_family_report
from .text.searchable import searchable_rows
from .text.vector_text import VectorTextResult, vector_text_rows
from .measure.scale import ScaleResult, discover_scale, scale_from_the_set, scale_given_by_hand
from .measure.measure import SETTLED_SCALE, PipeMeasure, aggregate, measure_pipes
from .measure.scale import NOT_MEASURED_HERE, SECTION_NOT_MEASURED
from .pipes.ownership import (Identity, OwnershipResult, complete_identities, identity_of, identity_from_text,
                              propagate, DECLARED_RUN_MAX_M)
from .pipes.frontier import end_evidence, frontiers_of, summary as frontier_summary
from .film import Film
from .handling import reads_as_a_drawing_number
from .routes import apply_routes, cross_check, review, run_routes

from . import rules as _rules
from . import disciplines as _disciplines


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


def _annotation_row_has_text(row, named_pipe_layers):
    line = row.line
    if line.source == "text":
        return True
    text = re.sub(r"\s+", "", row.text_norm.upper())
    # Repeated coupling ticks can be recognised as "I / / / /". A CAD
    # component layer does not make those strokes a note: accepting it erased
    # the adjacent pipe bend as a supposed leader. Require lexical evidence
    # for these rows, while preserving native text and actual detail notes.
    if sum(text.count(c) for c in "/\\") >= 2 and not re.search(r"[^I1|/\\?]", text):
        return False
    if line.layer and line.layer not in named_pipe_layers:
        return True
    return bool((len(text) >= 2 or not line.layer) and re.search(r"[^IO0?]", text))


# a drawing draws its leaders alike: a family carrying this share of the leaders is where it draws them
LEADER_MIN_SHARE = 0.25
LEADER_INK_SHARE = 0.5     # a nameless pen is the leader pen when its leaders are most of what it draws
PEER_SHARE = 0.15          # a drawn family carrying this much of the best family's label ends is a peer of it
PEER_LABELS_MIN = 2        # and two of the sheet's own labels pointing at it is the least that can say so
PEER_FOLLOWS_THE_BEST_LAYERS = True   # on a sheet with layer names a peer is named the way the best pens are
CONFLICT_ONLY_WITH_PIPE_LABELS = True  # only a pipe label's system can make a layer another system's
WRITING_PEN_TICKED_LABELS = 2   # labels that left their tick on a pen: it draws what they name, whatever else it touches
# and with no layer name to vouch for it, this share of the sheet's own pipe labels must have reached it
LABELS_MUST_REACH = 0.15
# How much of a pen's own ink has to be the sheet's writing before withholding it is safe. Measured over the
# style library: a pen that genuinely writes carries leaders and label frames for nearly all of what it draws
# beside its glyphs, while a pipe pen that happens to rule a few bars carries them for a few per cent of it.
# Half is far above every writing pen seen and far below every drawing pen.
WRITE_INK_SHARE = 0.5
OCR_ASSIST_BUDGET_S = 90.0  # naming a handful of glyphs may not hold a reading that is otherwise finished
LABELS_MIN = 20
DECLINED_SEGMENT_BUDGET = 8000        # strokes of declined families a reading carries, so they can be looked at
DECLINED_SEGMENTS_PER_FAMILY = 3000   # and no single family may spend the whole budget
UNCONSIDERED_SEGMENT_BUDGET = 4000    # and a smaller one for the ink no label ever pointed at
UNCONSIDERED_SEGMENTS_PER_FAMILY = 1500
UNCONSIDERED_PATHS_PER_FAMILY = 400

STAGES = ["READING_PDF", "DISCOVERING_DRAWING_GRAMMAR", "EXTRACTING_VECTORS", "RECONSTRUCTING_TEXT", "READING_DESIGNATIONS",
          "FINDING_LEADERS", "RESOLVING_PIPE_REPRESENTATION", "ATTACHING_PIPES", "BUILDING_TOPOLOGY", "BUILDING_PHYSICAL_PIPES",
          "MEASURING", "GENERATING_OVERLAYS", "COMPLETED"]


@dataclass
class PageAnalysis:
    page: RawPage
    layer_stats: dict
    vtext: VectorTextResult
    srows: list
    lines: list
    blocks: list[AnnotationBlock]
    designations: list[Designation]
    grammar: Any
    ann_layers: dict[str, int]
    leaders: list[Leader]
    pipe_families: dict[str, RepresentationFamily]
    prims: dict[str, list[Prim]]
    graphs: dict[str, Any]
    anchors: list[PipeCodeAnchor]
    contact_stats: dict[str, Any]
    ownership: OwnershipResult | None = None
    scale: ScaleResult | None = None
    measures: list[PipeMeasure] = field(default_factory=list)
    quantities: list[dict] = field(default_factory=list)
    elevations: dict[str, list[dict]] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    hatch_families: list[HatchFamily] = field(default_factory=list)
    risers: dict[str, list[dict]] = field(default_factory=dict)     # identity key -> riser symbols
    ocr_assist: dict | None = None                                  # report of the OCR-assisted glyph resolution
    crosscheck: dict = field(default_factory=dict)                  # the routes side by side, and where they differ
    review_findings: dict = field(default_factory=dict)             # what the reading did not reach, and why
    legend: DrawingLegend = field(default_factory=DrawingLegend)    # the sheet's own designation list
    declarations: Declarations = field(default_factory=Declarations)   # the sheet's written rules for unlabelled pipes
    second_reader: dict | None = None       # bounded cases put to a second reader, and what it did with them
    vision: dict | None = None              # what a look at the rendered page said the reading may have missed
    source_assignment: dict | None = None
    frontiers: list[dict] = field(default_factory=list)   # var varje rör slutar och varför (pipes/frontier.py)
    register: dict | None = None            # varje beteckning bladet skriver, i läget "Alla" (register.py)
    wide_runs: list[dict] = field(default_factory=list)   # andra discipliners ledningar, i läget "Alla" (widened_runs)


# A label over a bundle has found its pipes - the leader landed on as many drawn parallel lines as the block has
# rows - even though which line is which is still open. For "did this reading find the geometry the sheet is
# labelling?", that is a hit; the ordering is settled later, and on a sheet that stacks every label it is settled
# only after the reading has been chosen. Counting it as a miss let a reading that had found nothing but the
# heating pipes beat one that had found the water and waste runs it was being asked about.
FOUND_ITS_PIPES = ("multi_row_bundle_awaiting_elimination",)


def reached_labels(anchors, pipe_labels: set[str]) -> set[str]:
    """The sheet's own pipe labels whose leader ended on the geometry they name."""
    return {a.designation_id for a in anchors
            if a.state == "VERIFIED_PIPE_ATTACHMENT" or a.reason in FOUND_ITS_PIPES} & pipe_labels


def reach_is_poor(families, anchors, pipe_labels: set[str]) -> bool:
    """Whether the sheet's own labels found the geometry that was taken, whatever its layers are called.

    A sheet labels the pipes it draws, so the share of its pipe labels that ended up on a pipe is the sheet's own
    verdict on the reading. This asks that question of any sheet with enough labels to answer it - a named layer
    included, because a name vouches for what the geometry IS, never for its being what the labels are asking
    about. A sheet naming a hundred water and waste runs, whose reading accepts three hundred points of ink on a
    layer called VS1 and places four labels, has been read wrong; the name on that layer is true and beside the
    point.
    """
    if not families or len(pipe_labels) < _R("pipeline.LABELS_MIN", LABELS_MIN):
        return False
    return len(reached_labels(anchors, pipe_labels)) < _R("pipeline.LABELS_MUST_REACH", LABELS_MUST_REACH) * len(pipe_labels)


def label_reach_fails(families, anchors, pipe_labels: set[str]) -> bool:
    """Whether a reading is poor enough to be thrown away entirely.

    The same measure as `reach_is_poor`, but this one discards the reading, so it keeps the exemption the harder
    judgement needs: where a layer name vouches for the geometry taken, a thin result is reported rather than
    deleted. Reaching for more is a different decision from destroying what there is.
    """
    if any(f.split("|s|")[0] for f in families or ()):
        return False
    return reach_is_poor(families, anchors, pipe_labels)


BLOCK_INK_SHARE = 0.6       # så stor del av en pennas streck måste börja eller sluta vid en beteckningsruta
WRITING_PEN_MIN_STROKES = 8  # så många streck måste en penna ha innan "varenda ett" säger något om den


BLOCK_TOL = 14.0


class _BlockBoxes:
    """Bladets beteckningsrutor i ett rutnät, så att frågan "börjar strecket vid en ruta?" bara ser rutorna nära
    punkten. Att pröva varje streck mot varje ruta växte som streck gånger rutor, och ett tätt blad med tusentals
    etiketter och hundratusentals streck blev minuter av ingenting."""

    CELL = 64.0

    def __init__(self, boxes: list[tuple[float, float, float, float]], tol: float = BLOCK_TOL):
        self.boxes = list(boxes)
        self.tol = tol
        self.cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        self.wide: list[int] = []          # rutor som täcker för många rutnätsceller, eller saknar ändliga mått
        c = self.CELL
        for i, (x0, y0, x1, y1) in enumerate(self.boxes):
            if not all(math.isfinite(v) for v in (x0, y0, x1, y1)) or \
                    (x1 - x0 + 2 * tol) * (y1 - y0 + 2 * tol) > 256 * c * c:
                self.wide.append(i)
                continue
            for cx in range(math.floor((x0 - tol) / c), math.floor((x1 + tol) / c) + 1):
                for cy in range(math.floor((y0 - tol) / c), math.floor((y1 + tol) / c) + 1):
                    self.cells[(cx, cy)].append(i)

    def __bool__(self) -> bool:
        return bool(self.boxes)

    def hit(self, x: float, y: float) -> bool:
        tol = self.tol
        near = self.cells.get((math.floor(x / self.CELL), math.floor(y / self.CELL)), ()) \
            if math.isfinite(x) and math.isfinite(y) else range(len(self.boxes))
        for group in (near, self.wide):
            for i in group:
                x0, y0, x1, y1 = self.boxes[i]
                if x0 - tol <= x <= x1 + tol and y0 - tol <= y <= y1 + tol:
                    return True
        return False


def _runs_from_a_block(pth, boxes, tol: float = BLOCK_TOL) -> bool:
    """Börjar eller slutar strecket vid en beteckningsruta? Då är det en hänvisningslinje, inte en ledning."""
    if not isinstance(boxes, _BlockBoxes) or boxes.tol != tol:
        boxes = _BlockBoxes(boxes.boxes if isinstance(boxes, _BlockBoxes) else boxes, tol)
    for sg in pth.segs:
        for x, y in ((sg.x0, sg.y0), (sg.x1, sg.y1)):
            if boxes.hit(x, y):
                return True
    return False


def _block_boxes(blocks) -> list[tuple[float, float, float, float]]:
    """Rutorna bladet skriver sina beteckningar i."""
    return [(min(r.line.bbox[0] for r in b.rows), min(r.line.bbox[1] for r in b.rows),
             max(r.line.bbox[2] for r in b.rows), max(r.line.bbox[3] for r in b.rows))
            for b in (blocks or []) if b.rows]


def _writing_pens(page: RawPage, families, blocks) -> set[str]:
    """Pennor som skriver i stället för att rita: varenda streck börjar eller slutar vid en beteckningsruta.

    En hänvisningslinje går från etiketten till röret. En ledning går genom byggnaden. På ett tätt blad passerar
    en ledning ofta nära en etikettruta - mätt på de blad som tappar mest ligger mellan 46 och 82 procent av
    rörpennornas streck an mot en ruta - men aldrig alla. Pennorna där *varenda* streck gör det bar noll
    bekräftade meter: de drar bladets hänvisningslinjer, och ett lagernamn som liknar rörlagrens hade släppt in
    dem som rörgeometri ändå. Då står tvåhundrafemtio meter hänvisningslinje i läsningen som "ritad som rör",
    och den som granskar letar efter ett tappat rör som aldrig fanns.

    Villkoret har ingen tröskel att ställa in: antingen finns ett streck som är fritt från bladets etiketter
    eller så finns det inte. Bara kravet att pennan ritat tillräckligt många streck för att "varenda ett" ska
    betyda något, så att en penna med två streck inte döms av en slump.
    """
    boxes = _BlockBoxes(_block_boxes(blocks))
    if not boxes:
        return set()
    # Glyfstrecken räknas med, inte bort. En penna vars bläck är bokstäver skriver om möjligt ännu tydligare än
    # en som drar hänvisningslinjer, och en ritpenna har fria streck hur som helst.
    n: Counter = Counter()
    free: Counter = Counter()
    for pth in page.paths:
        if pth.kind != "s":
            continue
        fk = stroke_family(pth.layer, pth.width, pth.color)
        if fk not in families:
            continue
        n[fk] += 1
        if not _runs_from_a_block(pth, boxes):
            free[fk] += 1
    floor = _R("pipeline.WRITING_PEN_MIN_STROKES", WRITING_PEN_MIN_STROKES)
    return {fk for fk in families if n[fk] >= floor and free[fk] == 0}


def _unconsidered(page: RawPage, pipe_families: dict, contact_stats: dict, ann_layers: dict, glyph_pids: set,
                  leaders: list, blocks: list | None = None) -> dict:
    """Every drawn stroke the reading did not weigh as a candidate for pipe, and which of two things it was.

    Ink lands here for one of two reasons. Either no label's leader ever came near it, or it sits on a layer this
    drawing uses for its labels and frames - and on a sheet whose text is drawn as strokes that second group is
    large. Neither can become pipe: identity comes from a designation and its real leader, and there is none
    here. But together they are most of what a reader sees, and a line that is simply absent from the reading
    looks the same whether it was judged and set aside or never looked at. Saying which is the whole point. No
    graph is built for any of it - that is what the reading does for a family a label reached, and doing it for
    the title block would cost the reading its time for nothing.
    """
    seen_fams = set(pipe_families) | set(contact_stats.get("declined_families") or {})
    ann = set(ann_layers or {})
    # A pen a label's leader actually pointed at, which the reading nonetheless did not take as pipe, is its own
    # case and the most important one on the page. It used to be reported as "on a layer the reading treats as
    # text and frames", which on a sheet exported without layer names is not merely imprecise but false - there
    # is no such layer - and it sends whoever reads it looking for a layer problem that does not exist. What
    # actually happened is that the sheet's own labels found this ink and the reading refused it anyway.
    pointed = (set(contact_stats.get("votes") or {}) - seen_fams) - ann
    lead_pids = {pid for ld in leaders for pid in ld.path_ids}
    # Var bladet skriver sina beteckningar. Ett streck som börjar eller slutar där är en hänvisningslinje, och
    # att kalla det "aldrig vägd som rör" är sant men vilseledande: det ser ut som en tappad ledning för den som
    # läser, och skickar hen att leta efter ett lagerfel som inte finns. Ritningen säger vad strecket är, och
    # läsningen ska säga det vidare.
    boxes = _BlockBoxes(_block_boxes(blocks))
    fams: dict[str, dict] = {}
    for pth in page.paths:
        if pth.kind != "s" or pth.pid in glyph_pids or pth.pid in lead_pids:
            continue
        fk = stroke_family(pth.layer, pth.width, pth.color)
        if fk in seen_fams:
            continue
        why = ("ON_A_LAYER_THE_READING_TREATS_AS_ANNOTATION" if fk in ann else
               "A_LABEL_POINTED_AT_IT_AND_IT_WAS_NOT_TAKEN" if fk in pointed else
               "NO_LEADER_EVER_CAME_NEAR_IT")
        r = fams.setdefault(fk, {"family": fk, "why": why, "width": round(pth.width, 2),
                                 "total_length_pt": 0.0, "n_segments": 0, "paths": [],
                                 "n_strokes": 0, "n_from_a_block": 0})
        r["total_length_pt"] += pth.length
        r["n_segments"] += len(pth.segs)
        r["n_strokes"] += 1
        if boxes and _runs_from_a_block(pth, boxes):
            r["n_from_a_block"] += 1
        if len(r["paths"]) < UNCONSIDERED_PATHS_PER_FAMILY:
            r["paths"].append(pth)
    for r in fams.values():
        if r["n_strokes"] and r["n_from_a_block"] >= BLOCK_INK_SHARE * r["n_strokes"]:
            r["why"] = "IT_RUNS_FROM_A_LABEL_BLOCK"
    # A family drawn on a layer named the way this drawing names its pipe layers is the one worth a second look:
    # it is where the sheet puts pipes, and nothing pointed at it. It still cannot be measured - a run with no
    # label has no identity - but "this looks like a pipe layer and no leader reached it" is a different sentence
    # from "this is the title block", and a reader deserves to be told which one it is. So it is also the ink the
    # stroke budget is spent on first; a vector logo must not crowd it out by being long.
    for fk, r in fams.items():
        lay = fk.partition("|s|")[0]
        r["on_a_pipe_like_layer"] = bool(lay) and any(_layer_template_similar(lay, pf.partition("|s|")[0])
                                                      for pf in pipe_families if pf.partition("|s|")[0])
    budget = UNCONSIDERED_SEGMENT_BUDGET
    for fk in sorted(fams, key=lambda k: (not fams[k]["on_a_pipe_like_layer"], -fams[k]["total_length_pt"])):
        r = fams[fk]
        segs = []
        for pth in r["paths"]:
            for sg in pth.segs:
                if len(segs) >= min(budget, UNCONSIDERED_SEGMENTS_PER_FAMILY):
                    break
                segs.append([round(sg.x0, 2), round(sg.y0, 2), round(sg.x1, 2), round(sg.y1, 2)])
        r["segments"] = segs
        r["segments_truncated"] = len(segs) < r["n_segments"]
        r["total_length_pt"] = round(r["total_length_pt"], 1)
        del r["paths"]
        budget -= len(segs)
    return fams



def _width_lengths(page: RawPage) -> dict[float, float]:
    """Drawn stroke length per pen width on the page."""
    out: dict[float, float] = {}
    for p in page.paths:
        if p.kind == "s":
            w = round(p.width, 2)
            out[w] = out.get(w, 0.0) + p.length
    return out


def _t(timings: dict, key: str, t0: float) -> float:
    now = time.perf_counter()
    timings[key] = timings.get(key, 0.0) + (now - t0) * 1000.0
    return now



# A leader that ends this close to a run is on it; the tolerance is the pen, not a search radius. Measured over
# the reference drawings, the endpoints that sit on geometry their own designation already owns are at 0.0-6.7 pt
# and the next one is at 13, so nothing is reached for.
CLOSE_ON_OWNED_TOL = 8.0

# Hur många punkter en ritad bit högst provas i mot skrafferingen. Steget är en halv skrafferingsdelning, så
# taket slår bara in på mycket långa bitar - och där räcker det gott för att veta hur stor del som ligger inne.
HATCH_SAMPLES_MAX = 200


def _close_labels_on_owned_runs(anchors, ownership, graphs) -> None:
    """A label the drawing repeats over a run it already named is not an unresolved case.

    Runs after ownership, so it cannot add a metre: it only records that a label which failed to attach names
    the very identity that already owns the geometry under its leader. Where the nearest owned geometry belongs
    to a different identity - another system, another dimension - nothing is claimed and the case stays open.
    """
    owned: dict[str, list[tuple[str, int]]] = {}
    for p in ownership.pipes:
        owned.setdefault(p.identity.key, []).extend((p.family, i) for i in p.prim_ids)
    if not owned:
        return
    for a in anchors:
        if a.state == "VERIFIED_PIPE_ATTACHMENT" or not a.endpoint:
            continue
        stated = (a.designation_display or a.designation or "").upper()
        best = None
        for key, prims in owned.items():
            if key.replace("|DN", "-").upper() != stated:
                continue
            for fk, i in prims:
                d = point_seg_distance(a.endpoint[0], a.endpoint[1], graphs[fk].prims[i].seg)[0]
                if best is None or d < best:
                    best = d
        if best is not None and best <= _R("pipeline.CLOSE_ON_OWNED_TOL", CLOSE_ON_OWNED_TOL):
            a.evidence["closed_on_owned_run"] = {"identity": stated, "distance_pt": round(best, 2)}


CLAIM_WALK_LIMIT = 600      # a line, not a network: a claim that runs away is not worth drawing


def claimed_runs(anchors, ownership, graphs) -> dict[str, dict[int, list[str]]]:
    """The lines a label points at that no identity could take, and which labels point at them.

    A designation whose case the reading could not settle still reached geometry - the leader touched a drawn
    line, and that line is on the sheet whether or not anyone can say what it is called. Left as plain unowned
    ink it is indistinguishable from the ink nothing points at, so it is drawn as neither: it is not measured,
    because nothing here settles anything, and it is not hidden, because the drawing plainly has a pipe there.

    The walk follows the line and stops where the drawing does something: at a junction, and at the point the
    run becomes owned. Following the whole network instead would light up half a sheet from one open label.
    """
    from collections import defaultdict
    out: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    prim_of: dict[tuple[str, str, int], int] = {}
    for fk, g in graphs.items():
        for pid, prim in g.prims.items():
            prim_of[(fk, prim.pid, prim.seg_index)] = pid
    for a in sorted(anchors, key=lambda x: x.anchor_id):
        if a.state == "VERIFIED_PIPE_ATTACHMENT" or not a.contacts:
            continue
        code = a.designation_display or a.designation
        if not code:
            continue
        for c in a.contacts:
            fk = c.family
            g = graphs.get(fk)
            if g is None:
                continue
            start = prim_of.get((fk, c.pid, c.seg_index))
            if start is None:
                continue
            states = ownership.prim_states.get(fk) or {}
            seen: set[int] = set()
            stack = [start]
            while stack and len(seen) < _R("pipeline.CLAIM_WALK_LIMIT", CLAIM_WALK_LIMIT):
                cur = stack.pop()
                if cur in seen:
                    continue
                st = states.get(cur)
                if st is not None and st.state != "UNOWNED":
                    continue                  # the run is spoken for from here on; the claim stops
                seen.add(cur)
                for nid in g.prim_nodes.get(cur, ()):
                    node = g.nodes.get(nid)
                    if node is None or node.degree > 2:
                        continue              # a junction: the drawing changes something here
                    stack.extend(x for x in node.prims if x not in seen)
            for pid in seen:
                if code not in out[fk][pid]:
                    out[fk][pid].append(code)
    return {fk: dict(v) for fk, v in out.items()}


def _components(graph) -> dict[int, int]:
    """The drawn geometry of one family, split into single lines.

    Not connected components: on a real sheet the water, hot water and circulation runs all meet at the fixtures
    they serve, so everything the family draws is one or two connected pieces and the split says nothing. A line
    is what a bundle run is - the chain you get by following a stroke through the nodes where nothing else joins,
    and stopping where something does. A junction is where the drawing does something, and that is where one line
    ends and another begins.
    """
    from collections import defaultdict
    adj: dict[int, set[int]] = defaultdict(set)
    for node in graph.nodes.values():
        if node.degree > 2:
            continue                     # a junction: the lines meeting here are not the same line
        ps = list(node.prims)
        for a in ps:
            for b in ps:
                if a != b:
                    adj[a].add(b); adj[b].add(a)
    comp: dict[int, int] = {}
    n = 0
    for pid in sorted(graph.prims):
        if pid in comp:
            continue
        n += 1
        stack = [pid]
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp[cur] = n
            stack.extend(x for x in adj[cur] if x not in comp)
    return comp


def _style_colour(style: str):
    """Färgen ur en stilnyckel `w0.72|c(0.73, 0.73, 0.73)`; None när ingen färg står där."""
    m = re.search(r"c\(([^)]*)\)", style or "")
    if not m:
        return None
    try:
        return tuple(float(x) for x in m.group(1).split(","))
    except ValueError:
        return None


def _ink_weight(width: float, color) -> float:
    """Hur mycket en penna syns på pappret: bredd gånger mörkhet. Svart 0,48 väger 0,48; grå (0,73) 0,72 väger 0,19."""
    try:
        if color and len(color) >= 3:
            lightness = (0.299 * float(color[0]) + 0.587 * float(color[1]) + 0.114 * float(color[2]))
        elif color and len(color) == 1:
            lightness = float(color[0])
        else:
            lightness = 0.0
    except (TypeError, ValueError):
        lightness = 0.0
    return float(width or 0.0) * max(0.0, 1.0 - min(1.0, lightness))


def pen_key(family: str) -> str:
    """A pen as an office draws it, with the sheet it happened to be drawn on taken off.

    A CAD layer path carries the drawing's own number in front of the layer code - `268140-W-50-P-A-03|V-52BB-…`
    on one sheet and `…-A-00|V-52BB-…` on the next. The office's habit lives in the code and the ink, never in
    the sheet number, so anything carried from one drawing to another has to be keyed on what they share.
    """
    layer, _, style = family.partition("|s|")
    return f"{layer.rsplit('|', 1)[-1]}|s|{style}"


def settle_bundles_by_sheet_consistency(anchors, graphs, known: dict[str, str] | None = None) -> int:
    """The bundles a sheet cannot settle one at a time, settled by taking the sheet as a whole.

    A stacked label over a bundle says which codes are there and not which line is which. On a sheet that names
    a system on its own somewhere, elimination is enough. On a sheet that never does - one that puts KV, VV and
    VVC on two shared layers and labels them only in stacks - elimination has nothing to work from, and reading
    the order off a drawing convention would swap systems wherever that convention did not hold.

    But the sheet is not one bundle. It is dozens, and they run over the same pipes: a line belongs to one
    connected piece of geometry, that piece carries one system along its length, and every block that touches it
    names that system among its codes. So each piece can only be a system that appears in EVERY block reaching
    it, no two pieces in one block can be the same system, and a piece the reading already named is fixed. Where
    those three things leave a piece with one possible system, the sheet has said which it is - not a convention,
    not an order, but the only reading its own labels are all consistent with.

    On some sheets that is still not enough, and the reason is worth stating: where every block names the same
    systems over the same two pens, swapping two of those systems everywhere satisfies every constraint just as
    well. The sheet is then symmetric and nothing in its geometry says which of two parallel lines is the cold
    one. A person knows by convention, and convention is the guess this refuses.

    `known` is how that is broken without asking anyone: what the rest of the project has already stated, as
    drawn family -> system. A set of drawings is one office drawing one building, and the sheet that labels a
    run on its own says which pen that office uses for that system. Carried across, it is a fixpoint on the sheet
    that does not - and it is a fact taken from a drawing, not from a reader.

    Where all of it still leaves a choice, nothing is assigned. That is the ordinary outcome and it is honest.
    """
    from collections import defaultdict

    by_block: dict[tuple, list] = defaultdict(list)
    for a in anchors:
        if a.reason == "multi_row_bundle_awaiting_elimination" and a.evidence.get("bundle"):
            by_block[(a.block_id, a.leader_id)].append(a)
    if not by_block:
        return 0

    comps = {fk: _components(g) for fk, g in graphs.items()}
    prim_of: dict[tuple[str, str, int], int] = {}
    for fk, g in graphs.items():
        for pid, prim in g.prims.items():
            prim_of[(fk, prim.pid, prim.seg_index)] = pid

    def piece_of(fam_pid: str, seg: int) -> tuple[str, int] | None:
        """Which connected piece of which family a drawn segment belongs to."""
        for fk in graphs:
            pid = prim_of.get((fk, fam_pid, seg))
            if pid is not None:
                c = comps[fk].get(pid)
                if c is not None:
                    return (fk, c)
        return None

    # what the reading already settled: a piece a verified label sits on carries that label's system
    pinned: dict[tuple[str, int], set[str]] = defaultdict(set)
    for a in anchors:
        if a.state != "VERIFIED_PIPE_ATTACHMENT" or not a.system_token:
            continue
        for c in a.contacts:
            pc = piece_of(c.pid, c.seg_index)
            if pc:
                pinned[pc].add(a.system_token.upper())
    # and what the rest of the project has stated about the pens this sheet draws with
    if known:
        by_family: dict[str, str] = {pen_key(k): v.upper() for k, v in known.items()}
        for fk in graphs:
            sysname = by_family.get(pen_key(fk))
            if not sysname:
                continue
            for pid in graphs[fk].prims:
                pc = (fk, comps[fk].get(pid))
                if pc[1] is not None and pc not in pinned:
                    pinned[pc].add(sysname)

    # every block, as the pieces its runs lie on and the systems its rows name
    cases: list[tuple[tuple, list, list[tuple[str, int] | None], list[str]]] = []
    for key, group in sorted(by_block.items(), key=lambda kv: str(kv[0])):
        b = group[0].evidence["bundle"]
        runs = b["runs"]
        if len(group) != b["n"] or len(runs) != b["n"]:
            continue
        group.sort(key=lambda a: a.evidence["bundle"]["pos"])
        systems = [(a.system_token or "").upper() for a in group]
        if not all(systems):
            continue
        pieces: list[tuple[str, int] | None] = []
        for run in runs:
            hit = {piece_of(fam_pid, seg) for fam_pid, seg in run}
            hit.discard(None)
            pieces.append(hit.pop() if len(hit) == 1 else None)
        if any(p is None for p in pieces) or len(set(pieces)) != len(pieces):
            continue                      # a run on no piece, or two runs on one: says nothing about order
        cases.append((key, group, pieces, systems))
    if not cases:
        return 0

    # A piece can only be a system that every block reaching it names, and only one the reading has not already
    # settled as something else.
    domain: dict[tuple[str, int], set[str]] = {}
    for _, _, pieces, systems in cases:
        for pc in pieces:
            want = set(systems)
            domain[pc] = (domain[pc] & want) if pc in domain else set(want)
    for pc, fixed in pinned.items():
        if pc in domain:
            domain[pc] = domain[pc] & fixed if (domain[pc] & fixed) else set()

    # and no two pieces of one bundle are the same system: a system placed on one is off the others
    for _ in range(8):
        changed = False
        for _, _, pieces, systems in cases:
            for i, pc in enumerate(pieces):
                if len(domain.get(pc, ())) != 1:
                    continue
                only = next(iter(domain[pc]))
                for j, other in enumerate(pieces):
                    if i != j and only in domain.get(other, ()):
                        domain[other] = domain[other] - {only}
                        changed = True
            # a system only one piece of this bundle can take belongs to that piece
            for sysname in set(systems):
                takers = [pc for pc in pieces if sysname in domain.get(pc, ())]
                if len(takers) == 1 and len(domain[takers[0]]) > 1:
                    domain[takers[0]] = {sysname}
                    changed = True
        if not changed:
            break

    settled = 0
    for key, group, pieces, systems in cases:
        # a row can be given its line where that line can only be its system, and no other row of the block
        # shares that system - two KV rows over one bundle are still two KV rows
        take: list[tuple] = []
        for i, a in enumerate(group):
            sysname = systems[i]
            if systems.count(sysname) != 1:
                continue
            mine = [pc for pc in pieces if domain.get(pc) == {sysname}]
            if len(mine) != 1:
                continue
            idx = pieces.index(mine[0])
            touching = [c for c in a.contacts
                        if [c.pid, c.seg_index] in group[0].evidence["bundle"]["runs"][idx]]
            if touching:
                take.append((a, idx, touching, sysname))
        for a, idx, touching, sysname in take:
            a.state = "VERIFIED_PIPE_ATTACHMENT"
            a.reason = "multi_row_bundle_settled_by_sheet_consistency"
            a.contacts = touching
            a.evidence["sheet_consistency"] = {"run": idx, "system": sysname,
                                               "blocks_agreeing": sum(1 for _, _, ps, _ in cases if pieces[idx] in ps)}
            settled += 1
    return settled


def _settle_bundles_by_elimination(anchors, ownership, graphs) -> int:
    """A bundle of parallel runs named by one stacked label, settled by what the rest of the sheet already says.

    The label lists its codes in order and the runs lie side by side, but nothing in the label says which code is
    which line - and guessing by a drawing convention swaps identities between systems on the sheet where the
    convention does not hold. What does say it is the drawing: a run of the bundle usually carries on and is
    named on its own somewhere else. Every run the sheet has already named pins its code, and where that leaves
    one code and one run over, the last one is determined rather than chosen.

    Runs before ownership is recomputed, so what it settles is seeded like any other reading. A bundle the sheet
    does not name enough of stays ambiguous.
    """
    owner: dict[tuple[str, int], str] = {}
    prim_of: dict[tuple[str, str, int], int] = {}
    for fk, g in graphs.items():
        for pid, prim in g.prims.items():
            prim_of[(fk, prim.pid, prim.seg_index)] = pid
    # What a run is already called has to be spelled the way the label spells it. The identity's key is a
    # normalised form - it drops the suffix the sheet writes, so `KV1-X7-16/W` becomes `KV1-X7-16` - and it was
    # being compared against the label's own text. The two alphabets never met, so every run the sheet had
    # already named looked unnamed and no bundle was ever settled. The display form is the label's own.
    for p in ownership.pipes:
        name = (p.identity.display or p.identity.key.replace("|DN", "-")).upper()
        for i in p.prim_ids:
            owner[(p.family, i)] = name

    by_block: dict[str, list] = defaultdict(list)
    for a in anchors:
        if a.reason == "multi_row_bundle_awaiting_elimination" and a.evidence.get("bundle"):
            by_block[(a.block_id, a.leader_id)].append(a)
    settled = 0
    for key, group in sorted(by_block.items(), key=lambda kv: str(kv[0])):
        b = group[0].evidence["bundle"]
        runs = b["runs"]
        if len(group) != b["n"] or len(runs) != b["n"]:
            continue
        group.sort(key=lambda a: a.evidence["bundle"]["pos"])
        codes = [(a.designation_display or a.designation or "").upper() for a in group]
        if len(set(codes)) != len(codes):
            continue                      # the same code twice: order says nothing about which line is which
        # what the sheet already calls each run of the bundle
        named: list[str | None] = []
        for run in runs:
            got = set()
            for fam_pid, seg in run:
                for fk in graphs:
                    pid = prim_of.get((fk, fam_pid, seg))
                    if pid is not None and (fk, pid) in owner:
                        got.add(owner[(fk, pid)])
            named.append(got.pop() if len(got) == 1 else None)
        fixed = {n for n in named if n is not None}
        free_codes = [c for c in codes if c not in fixed]
        free_slots = [i for i, n in enumerate(named) if n is None]
        if len(free_codes) != len(free_slots) or len(free_slots) > 1:
            continue                      # more than one left over: the sheet has not said enough
        if free_slots:
            named[free_slots[0]] = free_codes[0]
        if sorted(x for x in named if x) != sorted(codes):
            continue
        # Elimination says which code is left over; it must not be what makes the identity. Each label of the
        # bundle keeps its own contact with the run it is being given, so what settles the case is a leader
        # touching that line plus the constraint - never the arithmetic on its own.
        assign = []
        for a in group:
            code = (a.designation_display or a.designation or "").upper()
            idx = named.index(code)
            touching = [c for c in a.contacts if [c.pid, c.seg_index] in runs[idx]]
            if not touching:
                break
            assign.append((a, idx, touching))
        if len(assign) != len(group):
            continue                      # a code with no line of its own under it: not settled, still ambiguous
        for a, idx, touching in assign:
            a.state = "VERIFIED_PIPE_ATTACHMENT"
            a.reason = "multi_row_bundle_settled_by_elimination"
            a.contacts = touching
            a.evidence["settled_against"] = {"run": idx, "named_by_the_sheet": [n for n in named]}
            settled += 1
    return settled

BUNDLE_ORDER_WITNESSES = 2  # bundles the sheet settled itself before its row order counts as said


def _settle_bundles_by_the_sheets_own_row_order(anchors, page) -> int:
    """What a bundle the sheet has already settled says about the bundles it has not.

    A stacked label lists its codes in an order and the runs lie side by side. Which row is which line is not
    written anywhere, and guessing it by a drawing convention swaps identities between systems on the sheets
    where the convention does not hold - so the reading never guesses. But a sheet that has settled one bundle
    on its own evidence has *stated* the relation: the row order and the order the leader meets the lines either
    agree or they do not. Where every bundle the sheet settled says the same thing, and at least two of them
    said it, the bundles it did not settle are read the same way.

    Nothing here is a rule about VVS drawings. It is this drawing's own habit, measured on the cases it
    answered by itself, and a sheet that answered none of them settles none of the rest.
    """
    paths = {p.pid: p for p in page.paths}

    def ranks(a) -> list[int] | None:
        """The bundle's runs in the order this label's own leader meets them."""
        b = a.evidence.get("bundle") or {}
        runs = b.get("runs") or []
        if len(runs) < 2:
            return None
        centres = []
        for run in runs:
            pts = []
            for fam_pid, seg in run:
                pth = paths.get(fam_pid)
                if pth is None or seg >= len(pth.segs):
                    return None
                sg = pth.segs[seg]
                pts.append(((sg.x0 + sg.x1) / 2.0, (sg.y0 + sg.y1) / 2.0))
            centres.append((sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)))
        cx = sum(x for x, _ in centres) / len(centres)
        cy = sum(y for _, y in centres) / len(centres)
        far, best = None, -1.0
        for pid in a.leader_paths:
            pth = paths.get(pid)
            if pth is None:
                continue
            for sg in pth.segs:
                for pt in ((sg.x0, sg.y0), (sg.x1, sg.y1)):
                    d = math.hypot(pt[0] - cx, pt[1] - cy)
                    if d > best:
                        best, far = d, pt
        if far is None:
            return None
        order = sorted(range(len(centres)), key=lambda i: (math.hypot(centres[i][0] - far[0], centres[i][1] - far[1]), i))
        out = [0] * len(centres)
        for r, i in enumerate(order):
            out[i] = r
        return out

    # what the sheet settled by itself, read as a relation between row order and line order
    votes: dict[str, set] = {"same": set(), "reversed": set()}
    for a in anchors:
        if a.reason not in ("multi_row_bundle_settled_by_elimination", "multi_row_bundle_settled_by_sheet_consistency"):
            continue
        b = a.evidence.get("bundle") or {}
        run = ((a.evidence.get("settled_against") or {}).get("run"))
        if run is None:
            run = ((a.evidence.get("sheet_consistency") or {}).get("run"))
        rk = ranks(a)
        if run is None or rk is None or run >= len(rk) or b.get("pos") is None:
            continue
        n, pos = len(rk), b["pos"]
        if rk[run] == pos:
            votes["same"].add(a.block_id)
        elif rk[run] == n - 1 - pos:
            votes["reversed"].add(a.block_id)
        else:
            return 0                      # the sheet contradicts itself: it has no habit to follow
    said = [k for k, v in votes.items() if v]
    if len(said) != 1 or len(votes[said[0]]) < _R("pipeline.BUNDLE_ORDER_WITNESSES", BUNDLE_ORDER_WITNESSES):
        return 0
    order = said[0]
    witnesses = len(votes[order])

    by_block: dict[tuple, list] = defaultdict(list)
    for a in anchors:
        if a.reason == "multi_row_bundle_awaiting_elimination" and a.evidence.get("bundle"):
            by_block[(a.block_id, a.leader_id)].append(a)
    settled = 0
    for key, group in sorted(by_block.items(), key=lambda kv: str(kv[0])):
        b = group[0].evidence["bundle"]
        runs = b["runs"]
        if len(group) != b["n"] or len(runs) != b["n"]:
            continue
        group.sort(key=lambda a: a.evidence["bundle"]["pos"])
        codes = [(a.designation_display or a.designation or "").upper() for a in group]
        if len(set(codes)) != len(codes):
            continue                      # the same code twice: order says nothing about which line is which
        rk = ranks(group[0])
        if rk is None:
            continue
        n = len(runs)
        assign = []
        for a in group:
            pos = a.evidence["bundle"]["pos"]
            want = pos if order == "same" else n - 1 - pos
            idx = next((i for i, r in enumerate(rk) if r == want), None)
            if idx is None:
                break
            touching = [c for c in a.contacts if [c.pid, c.seg_index] in runs[idx]]
            if not touching:
                break
            assign.append((a, idx, touching))
        if len(assign) != len(group) or len({i for _, i, _ in assign}) != len(assign):
            continue
        for a, idx, touching in assign:
            a.state = "VERIFIED_PIPE_ATTACHMENT"
            a.reason = "multi_row_bundle_settled_by_the_sheets_own_row_order"
            a.contacts = touching
            a.evidence["row_order"] = {"run": idx, "order": order, "bundles_the_sheet_settled_itself": witnesses}
            settled += 1
    return settled


SYSTEM_FAMILY_SHARE = 0.8   # the sheet places a system on one family this consistently
SYSTEM_FAMILY_MIN = 3       # and has said so this many times before its habit counts as evidence


def _settle_by_system_usage(anchors) -> int:
    """Where a leader ends on several families at once, the sheet's own habit for that system decides.

    A drawing draws a system with one pen. Where other labels of the same system have already been placed on
    this sheet - each by its own leader, each verified on its own evidence - and they agree overwhelmingly on
    one of the families THIS leader actually touched, that is the family this label means too.

    It is the same kind of evidence as the designation list and the grammar: not a rule about VVS drawings, but
    a reading of what this drawing does. Nothing is chosen that the leader did not touch, so no geometry is
    claimed that the label never reached, and a sheet that has not said the same thing several times over
    settles nothing.
    """
    habit: dict[str, Counter] = defaultdict(Counter)
    for a in anchors:
        if a.state != "VERIFIED_PIPE_ATTACHMENT" or not a.system_token:
            continue
        for fk in {c.family for c in a.contacts}:
            habit[a.system_token.upper()][fk] += 1
    settled = 0
    for a in sorted(anchors, key=lambda a: a.anchor_id):
        if a.state != "AMBIGUOUS_PIPE_ATTACHMENT" or not a.system_token:
            continue
        if not a.reason.startswith("several_vector_families_at_leader_no_token_discrimination"):
            continue
        touched = {c.family for c in a.contacts}
        if len(touched) < 2:
            continue
        used = habit.get(a.system_token.upper())
        if not used:
            continue
        among = {f: used.get(f, 0) for f in touched}
        total = sum(among.values())
        if total < _R("pipeline.SYSTEM_FAMILY_MIN", SYSTEM_FAMILY_MIN):
            continue
        best, n = max(sorted(among.items()), key=lambda kv: kv[1])
        if n < _R("pipeline.SYSTEM_FAMILY_SHARE", SYSTEM_FAMILY_SHARE) * total:
            continue                    # the sheet uses more than one family for this system: no habit to read
        a.contacts = [c for c in a.contacts if c.family == best]
        a.candidate_families = [best]
        a.state = "VERIFIED_PIPE_ATTACHMENT"
        a.reason = "family_this_sheet_uses_for_this_system"
        a.evidence = dict(a.evidence or {}, system_usage={"family": best, "of": n, "seen": total})
        settled += 1
    return settled


@dataclass
class PreparedPage:
    """Everything about a sheet that can be worked out before anything is claimed about its pipes.

    The front half of a reading - the text rebuilt from strokes, the lines, the annotation blocks, the
    designations and the sheet's own list - costs about two thirds of the time a sheet takes, and it does not
    depend on any of the choices the second half makes. Made a value, it can be worked out once and read twice:
    the set's designation list has to be found before the sheets are read against it, and finding it used to
    mean reading those sheets twice over.
    """
    page: RawPage
    layer_stats: Any
    vtext: Any
    srows: list
    lines: list
    blocks: list
    free: Any
    consumed: set
    designations: list
    grammar: Any
    legend: DrawingLegend
    ocr_report: Any
    timings: dict
    vt_timing: dict
    declarations: Declarations = field(default_factory=Declarations)


def prepare_page(page: RawPage, progress: Callable[[str], None] | None = None, ocr_assist: bool = False,
                 film: "Film | None" = None) -> PreparedPage:
    """Read the sheet as far as its own words go, and no further."""
    timings: dict[str, float] = {}
    film = film or Film(None)
    t0 = time.perf_counter()
    if progress:
        progress("DISCOVERING_DRAWING_GRAMMAR")
    film.note("READING_PDF", f"Öppnar blad {page.info.index + 1}, {int(page.info.width)} × {int(page.info.height)} "
                             f"punkter. Ser efter vad filen säger om sig själv innan något mäts.")
    film.page(page)
    layer_stats = compute_layer_stats(page)
    t0 = _t(timings, "profile_ms", t0)
    if film:
        named = [n for n in layer_stats if n]
        pens = Counter()
        for st in layer_stats.values():
            for w, n in st.widths.items():
                pens[w] += n
        film.note("READING_PDF", f"{len(page.paths)} ritade objekt, {len(page.spans)} textobjekt.")
        film.note("READING_PDF",
                  f"{len(named)} namngivna lager bär geometri." if named
                  else "Exporten bär inga lagernamn - ingenting utom pennorna säger vad geometrin är.")
        film.note("READING_PDF",
                  "Pennor: " + ", ".join(f"{float(w):.2f} pt ({n} objekt)" for w, n in pens.most_common(5)) + ".")
    if progress:
        progress("RECONSTRUCTING_TEXT")
    vt_timing: dict = {}
    vtext = vector_text_rows(page, vt_timing, say=(lambda t: film.note("RECONSTRUCTING_TEXT", t)) if film else None)
    srows = searchable_rows(page)
    t0 = _t(timings, "text_ms", t0)
    if film:
        unknown = vtext.stats.get("unknown_families")
        film.note("RECONSTRUCTING_TEXT",
                  f"{vtext.n_glyphs} tecken byggda ur {vtext.n_components} streckklumpar, "
                  f"{len(vtext.families)} formfamiljer."
                  + (f" {unknown} familjer gick inte att namnge." if unknown else ""))
        if srows:
            film.note("RECONSTRUCTING_TEXT", f"{len(srows)} rader låg redan som riktig text i filen.")
        film.text(vtext.rows)
    ocr_report = None
    if ocr_assist:
        # characters the stroke recogniser could not name are filled from an OCR pass over the same page, and
        # only where the OCR word lines up character for character with what the vector reader already read
        if progress:
            progress("RESOLVING_UNREADABLE_TEXT")
        from .text.ocr_assist import resolve_unknown_glyphs
        # bounded, and it says where it is: an assist that holds a finished reading is worse than no assist
        ocr_report = resolve_unknown_glyphs(page, vtext.rows, budget_s=_R("pipeline.OCR_ASSIST_BUDGET_S", OCR_ASSIST_BUDGET_S),
                                            progress=(lambda t: progress(f"RESOLVING_UNREADABLE_TEXT {t}"))
                                            if progress else None,
                                            seen=film.seeing if film else None)
        t0 = _t(timings, "ocr_assist_ms", t0)
    if progress:
        progress("READING_DESIGNATIONS")
    lines = merge_lines(srows + vtext.rows, page.info.index)
    # Ett blad som bär sin text två gånger - som text i filen och som strecken som ritar den - ger två rader
    # per etikett, och blocket ser då ut som en staplad etikett som pekar på ett enda rör. En läsning per
    # ställe, den bättre av de två.
    twice: dict = {}
    lines = one_reading_per_place(lines, twice)
    consumed = set(pid for r in vtext.rows for pid in r.provenance) | set(pid for m in vtext.marks for pid in m.path_ids)
    free = free_segments(page, consumed)
    blocks = build_blocks(page, lines, free)
    designations, grammar, _ = extract_designations(page, blocks)
    legend = read_legend(lines, designations)
    declarations = read_declarations(lines)
    if film and declarations:
        film.note("READING_DESIGNATIONS",
                  "Bladet förklarar i ord vad rören utan etikett är: kopplingsledningar enligt tabell - "
                  + ", ".join(d.text for d in declarations.connection_pipes) + ".")
    if film:
        with_dn = sum(1 for d in designations if d.dn is not None)
        film.note("READING_DESIGNATIONS",
                  f"{len(lines)} textrader blev {len(blocks)} etikettblock och {len(designations)} beteckningar, "
                  f"{with_dn} med en dimension.")
        shapes = grammar.pattern_weight.most_common(3) if hasattr(grammar, "pattern_weight") else []
        if shapes:
            film.note("READING_DESIGNATIONS",
                      "Formen bladet skriver dem i: " + ", ".join(f"{pat} ({int(w)}x)" for pat, w in shapes) + ".")
        if legend.entries:
            film.note("READING_DESIGNATIONS",
                      f"Beteckningslistan hittad: {len(legend.entries)} rader på bladets egen kant.")
        else:
            film.note("READING_DESIGNATIONS",
                      "Bladet bär ingen beteckningslista jag kan hitta - då gäller handlingens, om något annat "
                      "blad skriver den.")
        film.designations(designations)
    _t(timings, "designation_ms", t0)
    return PreparedPage(page=page, layer_stats=layer_stats, vtext=vtext, srows=srows, lines=lines, blocks=blocks,
                        free=free, consumed=consumed, designations=designations, grammar=grammar, legend=legend,
                        ocr_report=ocr_report, timings=timings, vt_timing=vt_timing, declarations=declarations)


def rows_needing_a_pipe(rows: list, pipe_labels: set[str]) -> list:
    """Raderna i en etikettruta som faktiskt ska ha var sin ritad sträcka.

    Rutan bär rörnamnen och under dem ofta en höjd - "CL 3060 REL", "CL=2500". Höjden säger var röret ligger,
    inte att där finns ett rör till, och bladets egen förklaringslista säger själv att CL är centrumlinje. Men
    raden har samma form som en beteckning, så den räknades som en rad till som skulle ha en sträcka. Då gick
    avbildningen inte ihop - två rader mot en ritad sträcka - och kravet på ett-till-ett gjorde *båda*
    tvetydiga: rörnamnet tappade sitt rör för att noten stod bredvid det.

    Noten räknas därför inte med. Men bara när rutan har ett rörnamn att lämna den åt: en ruta som bara bär
    noter lämnas som den är, så att den redovisas som den olösta rad den är i stället för att tystna.
    """
    pipe_rows = [d for d in rows if d.did in pipe_labels]
    return pipe_rows if pipe_rows and len(pipe_rows) < len(rows) else rows


def analyze_page(page: RawPage, progress: Callable[[str], None] | None = None, ocr_assist: bool = False,
                 film_sink: Callable[[str, dict], None] | None = None,
                 second_reader: Callable[[Any], str] | None = None,
                 known_families: dict[str, str] | None = None,
                 known_legend: DrawingLegend | None = None,
                 known_scale: float | None = None,
                 known_scale_pages: list[int] | None = None,
                 given_scale: float | None = None,
                 prepared: "PreparedPage | None" = None,
                 source_mode: str | None = None, source_ask=None, source_style="auto", source_detector=None) -> PageAnalysis:
    """second_reader: an optional transport for putting the reading's own open cases to a language model.

    Without it - the default, and what every test and every reference run uses - nothing is asked, the analysis
    is deterministic and needs no network, and every ambiguous case stays ambiguous. With it, only cases the
    engine itself gave up on are asked, only among candidates the drawing offers, and every answer is verified
    against those candidates twice before it can move a metre.
    """
    film = Film(film_sink)
    # The front half of the reading says what it is finding as it finds it, so a prepared sheet must not say it
    # all a second time: it was said when it was worked out.
    prep = prepared if prepared is not None else prepare_page(page, progress, ocr_assist, film)
    timings = dict(prep.timings)
    layer_stats, vtext, srows = prep.layer_stats, prep.vtext, prep.srows
    lines, blocks, free, designations, grammar = prep.lines, prep.blocks, prep.free, prep.designations, prep.grammar
    ocr_report, vt_timing = prep.ocr_report, prep.vt_timing
    if prepared is not None and film:
        film.page(page)
        film.text(vtext.rows)
        film.designations(designations)
    legend = prep.legend                         # the sheet's own designation list, read against what it draws
    declarations = prep.declarations             # ...and its written rules for the pipes it does not label
    if not legend.entries and known_legend is not None and known_legend.entries:
        legend = adopt(known_legend)             # ...or the one the rest of the set carries for it
    else:
        legend = replace(legend, entries=[replace(e) for e in legend.entries])
    assign_roles(legend, designations, prior=roles_of(known_legend) if known_legend is not None else None)
    # The system number a list's placeholder stands for is a number: written in digits, one system is one name
    # however the strokes read it (legend.number_as_listed).
    listed = [e.code for e in legend.entries if e.role == "system"]
    for d in designations:
        written = number_as_listed(d.text, listed) if listed else d.text
        if written != d.text:
            d.text = written
            d.tokens = split_tokens(written)
            d.system_token = d.tokens[0] if d.tokens else d.system_token
    if film and legend.entries:
        film.note("READING_DESIGNATIONS",
                  ("Handlingens lista" if not legend.own else "Bladets lista")
                  + f" ger {len(legend.systems())} rörsystem ({', '.join(sorted(legend.systems())[:8]) or 'inga'}) "
                  + f"och {len(legend.components())} komponentkoder som aldrig blir rör.")
    t0 = time.perf_counter()
    if progress:
        progress("FINDING_LEADERS")
    des_by_block: dict[str, list[Designation]] = defaultdict(list)
    for d in designations:
        des_by_block[d.block_id].append(d)
    paths = PathsByPlace((p.pid, p) for p in page.paths)
    glyph_pids = set(pid for r in vtext.rows for pid in r.provenance)
    block_by_id = {b.bid: b for b in blocks}
    # NOTE: consumed (for free segments) still excludes marks; the geometry index only excludes accepted text glyphs
    system_tokens = {d.system_token for d in designations}
    # the sheet's own designation list says which labels name pipes; the rest describe objects and may sit
    # anywhere, so they say nothing about what pipe geometry looks like
    # Koder bladets egen förklaringslista aldrig nämner är inga rörbeteckningar på det bladet - rumsnummer har
    # samma form som en rörbeteckning, och formen kan inte skilja dem åt. Räknas de som rörnamn drar de dessutom
    # ned bladets etikettäckning och kan få hela läsningen att förkastas.
    # In the widened reading of "Alla" another discipline's run is no pipe code of the sheet's VVS list either, and
    # that is no reason it names nothing: a label written the way a run is written is let through (see
    # _another_disciplines_run). Everything else the list never mentions stays out, there as here.
    other_runs = _disciplines.value("pipeline.OTHER_RUNS_NAME_RUNS", False)
    unknown_codes = _unknown_to_the_legend(legend, designations)
    if other_runs:
        unknown_codes = {d.did for d in designations
                         if d.did in unknown_codes and not _another_disciplines_run(d, legend)}
    # a sheet read from pixels (raster/): every run on it is reviewed, and its scale must be measured on the sheet
    from_image = (page.input_class or {}).get("read_as") == "raster"
    # A drawing number names a sheet, never a pipe. It has a pipe label's shape - `V-50-1-A0111` opens with a
    # letter and carries a number where a size would stand - and on a page read from pixels the title block's
    # ruled cells come out as lines running on from under it, so the sheet's own number was read as a pipe the
    # length of its title block. It is told apart the way the set's handling reads it (`handling.py`): a
    # discipline letter on its own, a two-digit group and at least one part more - a shape no pipe label has, from
    # `S13-12` to `VS1-S13-15/W`. On a vector sheet the title block's cells are drawn apart from its text and the
    # number has reached no line on any sheet read; that reading is left as it is.
    sheet_numbers = {d.did for d in designations if reads_as_a_drawing_number(d.text)} if from_image else set()
    pipe_labels = {d.did for d in designations
                   if (_names_a_run(d, legend) if other_runs else legend.names_a_pipe(d))
                   and (d.text or "").upper() not in legend.components()
                   and d.did not in unknown_codes and d.did not in sheet_numbers and not legend.holds(d.bbox)}
    spelled_out = layer_system_tokens(page)      # the system names the file writes on layers of its own

    named_systems = {d.system_token for d in designations if d.did in pipe_labels}
    # The systems a layer name may be found to contradict: those the sheet's pipe labels name. A reference to
    # another sheet - "FORTS. SE RITNING V50-01-2712" - has a label's shape and its "V50" is the very prefix the
    # set's own layers carry (`v50_p270|V-55512`), so counted as a system it made every pipe layer of the sheet
    # "V50's layer", every pipe label on it a conflict, and the sheet measured nothing. Only what names a pipe
    # can say a layer belongs to another pipe.
    conflict_tokens = named_systems if _R("pipeline.CONFLICT_ONLY_WITH_PIPE_LABELS", CONFLICT_ONLY_WITH_PIPE_LABELS) \
        else system_tokens
    named_pipe_layers = {layer for layer in {p.layer for p in page.paths if p.layer}
                         if any(system_layer_match(token, layer, spelled_out)
                                for token in named_systems)}

    def unit_has_text(block, unit):
        # A CAD pipe layer is evidence against interpreting its single arc or
        # riser as a letter. Native text and text on other named layers remain
        # independent annotation evidence, including one-letter detail notes.
        for i, r in enumerate(block.rows):
            if unit is not None and i not in unit:
                continue
            if _annotation_row_has_text(r, named_pipe_layers):
                return True
        return False

    annotation_paths: set[str] = set()

    def run_pass(ann_layers: dict[str, int] | None, admit_leader_pens: bool = False):
        ann_marks = [m for m in vtext.marks if f"{m.layer}|{m.style}" in ann_layers] if ann_layers else vtext.marks
        leaderless: dict[str, list[str]] = {}
        leaders = discover_leaders(page, blocks, free, ann_marks, ann_layers, report=leaderless)
        # A riser circle can also have been read as a solitary O/zero. A line
        # leaving that non-label unit is pipe geometry, not a second leader.
        # Use the same label-unit ownership here as at final attachment, before
        # the candidate's paths can be removed from the drawing.
        def is_annotation_leader(ld):
            block = block_by_id[ld.block_id]
            unit = block.unit_of_row(ld.start_row) if ld.start_row is not None else block.unit_for_point(ld.start)
            if any(unit is None or d.row_index in unit for d in des_by_block.get(ld.block_id, [])):
                return True
            # Ordinary notes and component tags also have real leaders. Only
            # an isolated circle misread as O/0 gives no annotation evidence.
            return unit_has_text(block, unit)
        leaders = [ld for ld in leaders if is_annotation_leader(ld)]
        if film:
            reached = len({ld.block_id for ld in leaders} & set(des_by_block))
            film.note("FINDING_LEADERS",
                      f"{len(leaders)} ritade hänvisningslinjer följda; {reached} av {len(des_by_block)} "
                      f"etikettblock drar en. En etikett utan linje pekar inte på något - den gissas inte fram.")
        exclude = set(ann_layers) if ann_layers else set()
        annotation_pids = {pid for ld in leaders for pid in ld.path_ids}
        for b in blocks:
            label_rows = {d.row_index for d in des_by_block.get(b.bid, [])}
            owned_rows = {ri for unit in b.units
                          if label_rows.intersection(unit) or unit_has_text(b, unit)
                          for ri in unit}
            for ri in owned_rows:
                annotation_pids.update(u.pid for u in b.rows[ri].underline)
            if owned_rows or label_rows:
                annotation_pids.update(sg.pid for sg in b.box_segs)
        # Restricting the pipe-label tracer in a later pass does not turn
        # previously established note leaders into pipe geometry. Keep their
        # path evidence even when that pass no longer searches their pen.
        annotation_paths.update(annotation_pids)
        annotation_pids = annotation_paths.copy()
        gidx = GeometryIndex(page, exclude, glyph_pids | annotation_pids)
        des_leaders = [ld for ld in leaders if ld.block_id in des_by_block]
        votes: Counter = Counter()
        token_votes: Counter = Counter()
        leader_votes: Counter = Counter()
        run_label_votes: Counter = Counter()
        run_objects: dict[str, set[str]] = defaultdict(set)
        # one leader meeting one drawn object is one vote for that object's family, however many segments the
        # object is exported as: a symbol drawn as sixteen little strokes is not sixteen pieces of evidence
        for ld in des_leaders:
            if not any(d.did in pipe_labels for d in des_by_block[ld.block_id]):
                continue
            seen_obj: dict[tuple[str, str], float] = {}
            for c in leader_contacts(ld, gidx, None, paths):
                w = 1.0 if c.kind in ("end_tick", "crossing_tick") else 0.5
                key = (c.family, c.pid)
                seen_obj[key] = max(seen_obj.get(key, 0.0), w)
            for (fam, _), w in seen_obj.items():
                votes[fam] += w
                for d in des_by_block[ld.block_id]:
                    if system_layer_match(d.system_token, fam.split("|s|")[0], spelled_out):
                        token_votes[fam] += 1
            # how many of the sheet's own pipe labels point at this family, counted once per label however many
            # of its objects that label's leader happens to run along. This is the quantity a reader would count
            # off the drawing, and unlike a sum of contact weights it does not grow with how a family is exported.
            for fam in {f for f, _ in seen_obj}:
                leader_votes[fam] += 1
            for f, pid in seen_obj:
                if max(paths[pid].bbox[2]-paths[pid].bbox[0], paths[pid].bbox[3]-paths[pid].bbox[1]) >= 10.0:
                    run_objects[f].add(pid)
            for fam in {f for f, pid in seen_obj
                        if max(paths[pid].bbox[2]-paths[pid].bbox[0],
                               paths[pid].bbox[3]-paths[pid].bbox[1]) >= 10.0}:
                run_label_votes[fam] += 1
        total = sum(votes.values()) or 1.0
        tick_votes: Counter = Counter()
        for ld in des_leaders:
            seen_tick: set[tuple[str, str]] = set()
            for c in leader_contacts(ld, gidx, None, paths):
                if c.kind in ("end_tick", "crossing_tick") and (c.family, c.pid) not in seen_tick:
                    seen_tick.add((c.family, c.pid))
                    tick_votes[c.family] += 1
        # The leader lines themselves are annotation geometry, never pipes, and neither are the label frames: the
        # paths are dropped from whatever family they land in, so a leader drawn with the pipes' own pen is never
        # measured as pipe. Beyond that, a drawing draws its leaders alike - on one layer, or with one pen - and
        # those families are excluded whole, because they also carry the leaders the tracer missed. A family that
        # carries a handful of leaders while another carries most of them is not where this drawing draws them:
        # those few are strays, a label's bounding box touching a pipe, and excluding the family on their account
        # would drop the pipes with them. On a sheet exported without layers that is the difference between
        # reading the pipes and reading nothing.
        lead_count: Counter = Counter()
        for ld in des_leaders:
            lead_count[stroke_family(ld.layer, ld.width, ld.color)] += 1
        top = max(lead_count.values(), default=0)
        # a layer name is the drawing's own statement about what that geometry is for, so a named family carrying
        # leaders is a leader family however few it carries. A pen width says nothing, and counting leaders is not
        # enough there either: a sheet exported without layer names draws its leaders with the same pens as its
        # pipes, and refusing every pen that carries a quarter of the leaders left such a sheet with no pipes at
        # all. What separates them is how much of the pen's own ink the leaders are. Where a pen draws leaders and
        # little else, it is the leader pen; where the leaders are a fraction of what it draws, the rest of that
        # ink is the drawing, and the pen stays a candidate.
        lead_ink: Counter = Counter()
        for ld in des_leaders:
            fk = stroke_family(ld.layer, ld.width, ld.color)
            for sgm in ld.segs:
                lead_ink[fk] += sgm.seg.length
        fam_ink: Counter = Counter()
        for pth in page.paths:
            if pth.pid in annotation_pids:
                continue
            fk = stroke_family(pth.layer, pth.width, pth.color)
            for sgm in pth.segs:
                fam_ink[fk] += sgm.length
        leader_fams = {f for f, c in lead_count.items()
                       if f.split("|s|")[0]
                       or c >= _R("pipeline.LEADER_MIN_SHARE", LEADER_MIN_SHARE) * top
                       and (run_label_votes[f] < 2 or len(run_objects[f]) < 2)
                       and not (admit_leader_pens and lead_ink[f] < _R("pipeline.LEADER_INK_SHARE", LEADER_INK_SHARE) * fam_ink.get(f, 0.0))} \
            | (set(ann_layers) if ann_layers else set())
        if os.environ.get("VVS_DEBUG_INK"):
            for f, v in votes.most_common():
                if f not in lead_count:
                    print(f"[ink] n=   0 andel=  0.000 röster={v:7.1f} ticks={tick_votes.get(f,0):4d} ledarfamilj=False  {f}", file=sys.stderr)
            for f, c in lead_count.most_common():
                fi = fam_ink.get(f, 0.0) or 1.0
                print(f"[ink] n={c:4d} andel={lead_ink[f]/fi:7.3f} röster={votes.get(f,0):7.1f} ticks={tick_votes.get(f,0):4d} "
                      f"ledarfamilj={f in leader_fams}  {f}", file=sys.stderr)
        # evaluate the vector structure of every voted family first (kind: fragmented-dashed / continuous / sparse)
        voted = sorted(f for f in votes if f not in leader_fams)
        figures: dict[str, list] = {}
        prims_all = collect_prims(page, set(voted), exclude_pids=annotation_pids | glyph_pids, figures_out=figures)
        desc: dict[str, tuple] = {}
        for fk in voted:
            if not prims_all.get(fk):
                continue
            g = build_graph(prims_all[fk], fk, graph_tolerances(page), symbols=page_symbols(page))
            rf = describe_family(fk, prims_all[fk], g)
            desc[fk] = (rf, g)
        from .source_rules.geometry_evidence import has_pipe_run
        contact_pen = Counter(round(ld.width, 2) for ld in des_leaders).most_common(1)
        contact_pen = contact_pen[0][0] if contact_pen else None
        def chain_like(fk):
            return fk in desc and has_pipe_run(desc[fk][0], token_votes[fk], contact_pen)
        token_fams = {f for f in voted if token_votes[f] >= 1 and chain_like(f)}
        total_votes = sum(votes.values()) or 1.0
        # styles that may vouch for name-less families: only strongly supported token families
        token_styles = {f.split("|s|")[1] for f in token_fams if votes[f] >= max(2.0, 0.05 * total_votes)}
        token_layers = [f.split("|s|")[0] for f in token_fams]
        total_ticks = sum(tick_votes.values()) or 1
        # the sheet's middle pen by drawn length: half the ink on the page is thinner than this
        by_width = sorted(_width_lengths(page).items())
        half = 0.5 * sum(L for _, L in by_width)
        median_width = 0.0
        run = 0.0
        for w, L in by_width:
            run += L
            if run >= half:
                median_width = w
                break
        # the weight this sheet annotates with: the pen most of its leaders are drawn with. Where it draws no
        # leaders at all there is nothing to compare against, and the rule stands down rather than guessing.
        lead_widths: Counter = Counter()
        lead_weights: Counter = Counter()
        for ld in leaders:
            lead_widths[round(ld.width, 2)] += 1
            lead_weights[round(_ink_weight(ld.width, ld.color), 2)] += 1
        annotation_width = lead_widths.most_common(1)[0][0] if lead_widths else 0.0
        # the weight the sheet annotates with, as ink on paper: width times darkness. A grey line is fainter than
        # a black one of the same width, and on a sheet without layers that faintness is the only thing that says
        # the grey dashed lines behind the pipes are the building - hidden beams, grids - and not more pipe.
        annotation_weight = lead_weights.most_common(1)[0][0] if lead_weights else 0.0
        pipe_families: dict[str, RepresentationFamily] = {}
        graphs: dict[str, Any] = {}
        # the strongest evidence any single drawn family carries, which is what the others are compared with
        chain_voted = [f for f in voted if chain_like(f)]
        best_ticks = max((tick_votes[f] for f in chain_voted), default=0)
        best_votes = max((votes[f] for f in chain_voted), default=0.0)
        best_leaders = max((leader_votes[f] for f in chain_voted), default=0)
        layered = [g for g in chain_voted if g.split("|s|")[0]]

        def template_support(layer_name: str) -> int:
            return sum(tick_votes[g] + leader_votes[g] for g in layered
                       if _layer_template_similar(layer_name, g.split("|s|")[0]))
        best_template_support = max((template_support(g.split("|s|")[0]) for g in layered), default=0)
        for f in voted:
            if not chain_like(f):
                continue
            layer, style = f.split("|s|")
            # With no layer name to vouch for anything, the pens have to be told apart by how they are drawn. A
            # draughtsman does not draw a pipe fainter than the line that points at it: the leaders are the
            # sheet's own annotation weight, and ink below it is construction lines, hatching and grids.
            #
            # This used to compare against the median width instead, which cannot say what it meant to say. A
            # background that is most of the ink IS the median, so the rule never caught it except by a rounding
            # accident - and on a sheet drawn with a single pen the same accident threw the pipes away, because
            # the histogram rounds to two places while the family carries the raw float: 0.35999998 < 0.36. Five
            # drawings of one office, ninety labels each, measured nothing at all.
            if not layer and desc[f][0].width < annotation_width - 1e-6:
                continue
            # ...and not fainter either. Measured on a layer-less export of a sheet whose layered twin puts its
            # pipes in black 1.44 and 2.04 pt and its hidden beams in grey 0.72 pt: the grey pen carried fourteen
            # label ticks - pipes laid on those beams - and was taken as a pipe family, and one designation
            # measured six times its reference. The beams are wider than the leaders and lighter than them.
            if not layer and annotation_weight > 0 and _ink_weight(desc[f][0].width, _style_colour(style)) < annotation_weight - 1e-6:
                continue
            similar = any(_layer_template_similar(layer, tl) for tl in token_layers)
            accept = (token_votes[f] >= 1) or (tick_votes[f] >= 2 and similar) \
                or (tick_votes[f] >= 3 and style in token_styles)
            # ...and a pen carrying a good share of all the ticks is weighed the same way as a peer below: on a sheet
            # with layer names the interior designer's `I40_p270|I050` carried five ticks of labels whose leaders
            # crossed it on their way to the pipes, was taken as pipe, and brought its own pen and template along
            # into the families gathered after it.
            share = not accept and tick_votes[f] >= 5 and tick_votes[f] / total_ticks >= 0.15
            peer = share or not accept and not token_fams and (
                (tick_votes[f] >= 2 and tick_votes[f] >= _R("pipeline.PEER_SHARE", PEER_SHARE) * best_ticks)
                or (votes[f] >= 5 and votes[f] >= _R("pipeline.PEER_SHARE", PEER_SHARE) * best_votes)
                or (leader_votes[f] >= _R("pipeline.PEER_LABELS_MIN", PEER_LABELS_MIN) and leader_votes[f] >= _R("pipeline.PEER_SHARE", PEER_SHARE) * best_leaders))
            # A peer is a pen measured against the best pen, for sheets where no layer name says which pens are
            # pipe. Where the pens do carry layer names, a peer has to be named the way the best pens are. A sheet
            # whose pipes lie on `v50_p270|V-55512` and the architect's walls on `A30_p270|A040` had two labels'
            # leaders end on a wall: the walls were taken as a peer of the pipes, the toilets' walls measured
            # ninety-one metres of water pipe and the facade sixty-eight metres of heating. On a sheet without
            # layer names nothing changes.
            # The pipes' template is the one the sheet's labels reach most, all its pens taken together: a single
            # pen of another template can tie the best pipe pen (the interior's I050 carried six ticks, as many
            # as the best heating pen) without the sheet's labels being about it.
            if peer and layer and _R("pipeline.PEER_FOLLOWS_THE_BEST_LAYERS", PEER_FOLLOWS_THE_BEST_LAYERS):
                if template_support(layer) < best_template_support:
                    peer = False
            accept = accept or peer
            # A leader that ends on a valve or a floor drain and only then reaches the pipe leaves no tick on the
            # pipe itself, and a sum of contact weights counts one label several times when its leader runs along
            # several pieces of the same family. Neither says what a reader would say, which is simply: how many
            # of this sheet's labels point here. Counted that way, a third pipe size on a layer-less sheet that
            # carried more labels than either family taken - and was refused for holding fewer than five contact
            # weights, on a sheet whose best family held four - is a peer of them.
            #
            # A sheet with no layer names to vouch for anything used to need one family to carry a large share of
            # every leader on the page. But a drawing that runs tap water, waste and heating draws them with
            # their own pens, and then no single family holds a large share of the total - the votes are split
            # between them and every one of them falls short. So a family is measured against the best family
            # rather than against the sum: several pens carrying comparable numbers of label ends are several
            # systems, while the sheet's background carries almost none however the rest is divided.
            if accept:
                pipe_families[f] = desc[f][0]
                graphs[f] = desc[f][1]
            if film:
                # The one decision on the sheet that a reader would most want to see made: which pens draw pipe.
                # It is said in the terms it was decided in - how many of the sheet's own labels end here, how
                # many left a tick, and whether a layer name vouched for any of it.
                film.note("RESOLVING_PIPE_REPRESENTATION",
                          f"Penna {desc[f][0].width:.2f} pt"
                          + (f" på {layer.rsplit('|', 1)[-1]}" if layer else " utan lagernamn") + ": "
                          f"{leader_votes[f]} etiketter pekar hit, {tick_votes[f]} lämnar ett märke, "
                          f"längsta sträcka {int(desc[f][0].longest_chain)} pt "
                          + ("-> tas som rör." if accept else "-> tas inte."))
        # what this sheet writes with: the pens its leaders run on, and the pens the bars under its own
        # designations are ruled with. Neither is ever pipe, and neither may be reached by a family template.
        writing_pens = set(leader_fams)
        for b in blocks:
            for r in b.rows:
                for u in r.underline:
                    writing_pens.add(stroke_family(u.layer, u.width, u.color))
            for sgm in b.box_segs:
                writing_pens.add(stroke_family(sgm.layer, sgm.width, sgm.color))
        pipe_families, graphs = _generalize_families(page, pipe_families, graphs, writing_pens - set(pipe_families))
        # Every drawn family the reading looked at and did not take, with the reason it did not. A family that is
        # declined is drawn on the sheet and simply absent from the reading afterwards, and geometry that is
        # absent without a word is indistinguishable from geometry that was never seen. Declining is often
        # right - walls and grids share a pen with pipes - so the point is not to take these, it is to say them.
        declined: dict[str, dict] = {}
        # Ink that stands still: a radiator hatched with two dozen strokes, a pump, a gully. It is drawn on a pen
        # the reading weighed, and it is not a run - so it is said here rather than silently left out.
        for f, qs in sorted(figures.items()):
            ink = sum(q.seg.length for q in qs)
            declined[f] = {"family": f, "kind": "figure", "why": "DRAWN_FIGURE_NOT_A_RUN",
                           "width": round(qs[0].width, 2), "longest_chain": 0.0,
                           "total_length_pt": round(ink, 1), "votes": round(votes.get(f, 0.0), 2),
                           "tick_votes": tick_votes.get(f, 0), "leader_votes": leader_votes.get(f, 0),
                           "n_segments": len(qs), "figure_segments": [
                               [round(q.seg.x0, 2), round(q.seg.y0, 2), round(q.seg.x1, 2), round(q.seg.y1, 2)] for q in qs[:400]]}
        for f in voted:
            if f in declined:
                continue
            if f in pipe_families or f not in desc:
                continue
            rf = desc[f][0]
            layer, style = f.split("|s|")
            if not chain_like(f):
                why = "NO_CONTINUOUS_RUN"
            elif not layer and rf.width < annotation_width - 1e-6:
                why = "FAINTEST_PEN_ON_THE_SHEET"
            elif tick_votes.get(f, 0) or votes.get(f, 0):
                # Etiketter nådde fram, och läsningen tog pennan ändå inte. Att då säga "ingen rörbeteckning
                # når fram till den" är inte bara oprecist utan osant: den som läser ser sin hänvisningslinje
                # sluta på strecket och letar efter ett fel som inte finns där. Det som hände var att pennan
                # vägdes och inte togs - ofta rätt, för arkitektens väggar bär hänvisningslinjer som slutar
                # strax bortom röret - och det är den meningen som ska stå.
                why = "A_LABEL_POINTED_AT_IT_AND_IT_WAS_NOT_TAKEN"
            else:
                why = "NO_LABEL_REACHED_IT"
            declined[f] = {"family": f, "kind": rf.kind, "why": why, "width": round(rf.width, 2),
                           "longest_chain": round(rf.longest_chain, 1), "total_length_pt": round(rf.total_length, 1),
                           "votes": round(votes.get(f, 0.0), 2), "tick_votes": tick_votes.get(f, 0),
                           "leader_votes": leader_votes.get(f, 0),
                           "n_segments": len(prims_all.get(f) or ())}
        # Keep the drawn strokes of the declined families so a reader can see them, spending the budget on the
        # ones a label came closest to: a wall layer holds tens of thousands of strokes and would drown both the
        # payload and the eye, while the family that nearly became pipe is the one worth looking at.
        budget = _R("pipeline.DECLINED_SEGMENT_BUDGET", DECLINED_SEGMENT_BUDGET)
        for f in sorted(declined, key=lambda k: (-declined[k]["tick_votes"], -declined[k]["votes"], -declined[k]["total_length_pt"])):
            take = min(budget, DECLINED_SEGMENTS_PER_FAMILY, declined[f]["n_segments"])
            qs = (prims_all.get(f) or [])[:take]
            declined[f]["segments"] = [[round(q.seg.x0, 2), round(q.seg.y0, 2), round(q.seg.x1, 2), round(q.seg.y1, 2)] for q in qs]
            declined[f]["segments_truncated"] = take < declined[f]["n_segments"]
            budget -= take
        anchors: list[PipeCodeAnchor] = []
        pf = set(pipe_families)
        for ld in des_leaders:
            block = block_by_id[ld.block_id]
            # a leader that starts on one row's own line speaks for that row's label, whatever else the block holds
            unit = block.unit_of_row(ld.start_row) if ld.start_row is not None else block.unit_for_point(ld.start)
            rows = sorted(des_by_block[ld.block_id], key=lambda d: d.row_index)
            rows = rows_needing_a_pipe(rows, pipe_labels)
            if unit is not None:
                rows = [d for d in rows if d.row_index in unit]
                if not rows:
                    continue        # leader belongs to a non-designation label unit (component tag, note)
                rows = _rows_owning_leader(block, rows, ld)
            contacts = leader_contacts(ld, gidx, pf, paths, ticks_across=not from_image)
            if not contacts and ld.length < 2.5 * max(block.height, 1.0) and not ld.end_marks:
                continue        # dangling frame stub, not a leader
            anchors.extend(resolve_block(block, rows, ld, contacts, conflict_tokens, spelled_out, paths, gidx))
        anchors.sort(key=lambda a: a.anchor_id)
        stats = {"votes": dict(votes.most_common()), "token_votes": dict(token_votes.most_common()), "candidate_families": sorted(pipe_families), "tick_votes": dict(tick_votes.most_common()),
                 "leader_votes": dict(leader_votes.most_common()), "declined_families": declined,
                 "labels_without_a_leader": {b: sorted(set(v)) for b, v in leaderless.items()},
                 "leader_pens_admitted": admit_leader_pens}
        if os.environ.get("VVS_DEBUG_PASS"):
            print(f"[pass ann_layers={sorted(ann_layers) if ann_layers else None}] leaders={len(leaders)} des_leaders={len(des_leaders)} votes={dict(votes)} ticks={dict(tick_votes)} "
                  f"voted={voted} chain_like={[f for f in voted if chain_like(f)]} accepted={sorted(pipe_families)} anchors={Counter(a.state for a in anchors)}", file=sys.stderr)
        return leaders, pipe_families, graphs, anchors, stats

    # pass 1: unrestricted leaders; pass 2: leaders/marks restricted to the annotation layers evidenced by
    # verified attachments of pass 1 (frames + leader layers + designation glyph layers)
    leaders, pipe_families, graphs, anchors, contact_stats = run_pass(None)
    ann_layers: Counter = Counter()
    ver_blocks = {a.block_id for a in anchors if a.state == "VERIFIED_PIPE_ATTACHMENT"}
    # The bar the draughtsman rules under a designation is annotation and nothing else - no pipe is an underline
    # under a label - and it is drawn for every label the sheet writes, not only for the ones whose leader the
    # first reading managed to verify. Learning the writing pens from the verified blocks alone cost whole
    # systems on a sheet whose office puts each system's text on a layer of its own: the systems that happened
    # not to verify were then not writing pens either, their leaders were withdrawn in the second reading, and
    # the pipes they named went unlabelled and unmeasured. What every block's frame is drawn with is the same
    # evidence, available for all of them.
    for b in blocks:
        if not any(r.role == "designation" for r in b.rows):
            continue
        for r in b.rows:
            for u in r.underline:
                ann_layers[stroke_family(u.layer, u.width, u.color)] += 1
        for sgm in b.box_segs:
            ann_layers[stroke_family(sgm.layer, sgm.width, sgm.color)] += 1
    for a in anchors:
        if a.state != "VERIFIED_PIPE_ATTACHMENT":
            continue
        ld = next(l for l in leaders if l.lid == a.leader_id)
        ann_layers[stroke_family(ld.layer, ld.width, ld.color)] += 1
        b = block_by_id[a.block_id]
        for r in b.rows:
            for u in r.underline:
                ann_layers[stroke_family(u.layer, u.width, u.color)] += 1
            if r.line.source != "text" and r.line.font.startswith("vector:"):
                ann_layers[f"{r.line.layer}|{r.line.font[len('vector:'):]}"] += 1
        for sgm in b.box_segs:
            ann_layers[stroke_family(sgm.layer, sgm.width, sgm.color)] += 1
    # A sheet labels the pipes it draws. Where the families accepted carry no layer name to vouch for them, and
    # the sheet's own pipe labels overwhelmingly failed to reach them, the wrong geometry was accepted: had it
    # been the pipes, the labels would have found it. Measured over the style library, a sheet reading its own
    # pipes places a quarter of its pipe labels or better; the one reading its building outline placed 6 %.
    def _reached(anchors) -> set[str]:
        return reached_labels(anchors, pipe_labels)

    def _label_reach_fails(fams, anchors) -> bool:
        return label_reach_fails(fams, anchors, pipe_labels)

    def _reach_is_poor(fams, anchors) -> bool:
        return reach_is_poor(fams, anchors, pipe_labels)

    # A pen that carries the sheet's leaders is normally not one that draws its pipes, and where a layer name
    # vouches for the geometry that always holds. Without layer names it is the only rule there is, and on a sheet
    # whose export collapsed leaders and pipes onto one pen it refuses the pipes as well: the page then measures
    # nothing at all. So the refusal stands unless it leaves the sheet unread, and only then are the pens whose
    # leaders are a small part of what they draw let back in - a rescue, not a default, because admitting them
    # everywhere also admits the pen a sheet hatches its building with, and the drawing fills with pipe that no
    # label owns.
    # Asked of every sheet, named layers included: admitting a pen can only ever add a reading, and it is taken
    # only when the sheet's own labels place better for it. A sheet whose export put the pipes on the same pen as
    # the leaders reads as nothing at all otherwise - and where the layers carry names, the old test never even
    # asked, so the rescue never ran and a hundred labels went unplaced beside their own geometry.
    # Which readings of the sheet were tried, what each of them managed, and which one was kept. The choice is
    # made by weighing the sheet's own labels against each other, and until now it was made silently: a reader
    # could see the answer but not that there had been a second candidate, nor why it lost. A decision nobody
    # can inspect is a decision nobody can argue with.
    passes: list[dict] = []

    def record(name: str, why: str, fams, anch, kept: bool | None = None) -> None:
        passes.append({"pass": name, "why": why, "families": sorted(fams),
                       "labels_placed": len(_reached(anch)), "labels": len(pipe_labels), "kept": kept})

    record("unrestricted", "varje penna bladet ritar med prövas mot bladets egna etiketter", pipe_families, anchors)
    if film:
        film.note("RESOLVING_PIPE_REPRESENTATION",
                  f"Första läsningen: {len(pipe_families)} familjer tagna som rör, "
                  f"{len(_reached(anchors))} av {len(pipe_labels)} rörnamn placerade.")
    if not pipe_families or _reach_is_poor(pipe_families, anchors):
        if film:
            film.note("RESOLVING_PIPE_REPRESENTATION",
                      "För få etiketter nådde fram. Provar om med pennorna som också drar hänvisningslinjer - "
                      "en export utan lager kan ha ritat rör och linjer med samma penna.")
        rescue = run_pass(None, admit_leader_pens=True)
        if rescue[1] and not _label_reach_fails(rescue[1], rescue[3]) and len(_reached(rescue[3])) > len(_reached(anchors)):
            if os.environ.get("VVS_DEBUG_PASS"):
                print(f"[rescue] leader pens admitted: {len(_reached(anchors))} -> {len(_reached(rescue[3]))} "
                      f"of {len(pipe_labels)} labels placed", file=sys.stderr)
            leaders, pipe_families, graphs, anchors, contact_stats = rescue
            record("leader_pens_admitted", "för få etiketter nådde fram; pennorna som också drar "
                   "hänvisningslinjer släpptes in", rescue[1], rescue[3])
        else:
            record("leader_pens_admitted", "prövad och förkastad: den placerade inte fler av bladets etiketter",
                   rescue[1], rescue[3], kept=False)
    pass1 = (leaders, pipe_families, graphs, anchors, contact_stats)
    if os.environ.get("VVS_DEBUG_PASS"):
        print(f"[reach] pass1 placed {len(_reached(anchors))}/{len(pipe_labels)} pipe labels, fams={sorted(pipe_families)}", file=sys.stderr)
    # A page read from pixels is read once. The second reading tests a hypothesis about the sheet's pens - which of
    # them write and which draw - and a scan cannot answer it: its pens are widths measured in pixels, and the one pen
    # a sheet draws its leaders with comes out as two or three widths that the building's thin lines share. Withholding
    # the widths the first reading's leaders were measured at took the leaders measured at the others away with the
    # building, and their labels were left without a line to any pipe.
    if ann_layers and not from_image:
        # a vector family accepted as pipe geometry in pass 1 is never an annotation family (an underline bar that
        # happens to share the pipes' stroke class must not remove the pipes)
        #
        # And a pen is a writing pen only if that is what it mostly does. Carrying a leader or a bar under a
        # designation was taken as proof on its own, and on a sheet whose office draws its pipes and its label
        # frames with one pen on one layer that took the drawing away: the second reading withheld the pen, the
        # pipes went with it, and the sheet reported three thousand metres of "never weighed as pipe, on a layer
        # the reading treats as text and frames". No office writes three thousand metres of labels.
        #
        # So it is measured instead of assumed, over the ink that could have become pipe - the glyphs are already
        # out of that reckoning, being text either way. A pen where most of the rest is leaders and label frames
        # writes; a pen where most of the rest is something else draws, whatever few frames it also carries.
        write_pt: Counter = Counter()
        for ld in leaders:
            for sgm in ld.segs:
                write_pt[stroke_family(ld.layer, ld.width, ld.color)] += sgm.seg.length
        for b in blocks:
            for r in b.rows:
                for u in r.underline:
                    write_pt[stroke_family(u.layer, u.width, u.color)] += u.seg.length
            for sgm in b.box_segs:
                write_pt[stroke_family(sgm.layer, sgm.width, sgm.color)] += sgm.seg.length
        candidate_pt: Counter = Counter()
        for pth in page.paths:
            if pth.kind == "s" and pth.pid not in glyph_pids:
                candidate_pt[stroke_family(pth.layer, pth.width, pth.color)] += pth.length

        def _writes_more_than_it_draws(fk: str) -> bool:
            ink = candidate_pt.get(fk, 0.0)
            return ink <= 0.0 or write_pt[fk] >= _R("pipeline.WRITE_INK_SHARE", WRITE_INK_SHARE) * ink

        keep = {k: v for k, v in ann_layers.items()
                if (v >= 2 or v >= 0.05 * max(ann_layers.values())) and k not in pipe_families
                and _writes_more_than_it_draws(k)}
        if film:
            film.note("RESOLVING_PIPE_REPRESENTATION",
                      f"Läser om bladet med {len(keep)} pennor undantagna - de som den första läsningens "
                      f"hänvisningslinjer visade sig vara ritade med. Bladets egna etiketter får avgöra vilken "
                      f"av de två läsningarna som är rätt.")
        pass2 = run_pass(keep)
        # The restriction is a hypothesis about which of the sheet's pens write rather than draw, learned from
        # the attachments the first reading verified. It is the sheet's own labels that test it: a sheet labels
        # the pipes it draws, so the reading that puts more of its labels on pipes is the one that read it. Where
        # the restriction withdraws the very pens the leaders were drawn with, it places fewer of them - or none
        # at all - and then the unrestricted reading stands. Without this a sheet the first pass read well ended
        # with a worse answer, and on some sheets with no answer at all.
        # Where a layer name vouches for the geometry, the restriction is checked only against collapse: the name
        # is the drawing's own statement and outweighs a count. Where nothing vouches for anything, the count is
        # all there is, and a restriction that costs the sheet more than half its placed labels has withdrawn the
        # pens the drawing was read with rather than the pens it was written with.
        # A layer name says what the geometry IS. It does not say that the restricted reading found more of what
        # the sheet's labels are asking about, and that is the only thing this choice turns on. The exemption
        # used to sit here too, so on a sheet whose water and waste runs the restriction hid, the reading that
        # placed a hundred labels lost to the one that placed four - because the four sat on a named layer.
        collapsed = not pass2[1] or _label_reach_fails(pass2[1], pass2[3])
        halved = 2 * len(_reached(pass2[3])) < len(_reached(pass1[3]))
        take1 = (collapsed or halved) and pass1[1] and not _label_reach_fails(pass1[1], pass1[3])
        if film:
            film.note("RESOLVING_PIPE_REPRESENTATION",
                      f"Med bladets skrivpennor undantagna placeras {len(_reached(pass2[3]))} rörnamn, utan "
                      f"undantag {len(_reached(pass1[3]))}. "
                      + ("Den obegränsade läsningen står." if (not pass2[1] or _label_reach_fails(pass2[1], pass2[3]))
                         or 2 * len(_reached(pass2[3])) < len(_reached(pass1[3]))
                         else "Den begränsade läsningen står."))
        record("annotation_pens_withheld",
               "bladets skrivpennor, som den första läsningens hänvisningslinjer pekade ut, hålls utanför",
               pass2[1], pass2[3], kept=not take1)
        # pass1 is whichever reading came out of the step above - the unrestricted one, or the rescue that
        # replaced it - so the verdict is written on the record that describes it, not always on the first
        kept_first = next((q for q in reversed(passes[:-1]) if q.get("kept") is not False), passes[0])
        kept_first["kept"] = bool(take1)
        if take1:
            if os.environ.get("VVS_DEBUG_PASS"):
                print(f"[withdraw] restricted pass left {len(_reached(pass2[3]))}/{len(pipe_labels)} labels placed, "
                      f"unrestricted placed {len(_reached(pass1[3]))}; keeping the unrestricted reading", file=sys.stderr)
            leaders, pipe_families, graphs, anchors, contact_stats = pass1
            contact_stats = dict(contact_stats, annotation_restriction_withdrawn=True)
            ann_layers = {}
        else:
            leaders, pipe_families, graphs, anchors, contact_stats = pass2
            ann_layers = keep
    else:
        if ann_layers:
            if film:
                film.note("RESOLVING_PIPE_REPRESENTATION",
                          "Sidan är läst ur bild, så den läses inte om med skrivpennorna undantagna: en penna är där en "
                          "bredd mätt i bildpunkter, och hänvisningslinjernas penna delar sina bredder med husets "
                          "tunna linjer. Den första läsningen står.")
            contact_stats = dict(contact_stats, annotation_restriction_not_tried_on_image=True)
        ann_layers = {}
        passes[-1]["kept"] = True
    if _label_reach_fails(pipe_families, anchors):
        if os.environ.get("VVS_DEBUG_PASS"):
            print(f"[drop] only {len(_reached(anchors))}/{len(pipe_labels)} pipe labels reached {sorted(pipe_families)}", file=sys.stderr)
        passes.append({"pass": "none", "why": "för få av bladets egna rörnamn nådde någon av de tagna familjerna; "
                                              "en läsning som inte når fram är sämre än ingen",
                       "families": [], "labels_placed": 0, "labels": len(pipe_labels), "kept": True})
        for q in passes[:-1]:
            q["kept"] = False
        pipe_families, graphs, anchors, contact_stats = {}, {}, [], dict(contact_stats, dropped_by_label_reach=True)
    contact_stats = dict(contact_stats, reading_passes=passes)
    film.leaders(leaders)
    film.families(pipe_families, graphs)
    timings["leader_ms"] = 0.0
    t0 = _t(timings, "leader_attachment_ms", t0)
    if progress:
        progress("BUILDING_TOPOLOGY")
    # En penna vars varenda streck börjar eller slutar vid en beteckningsruta skriver, den ritar inte - och en
    # skrivpenna är inte rörgeometri, hur mycket dess lagernamn än liknar rörlagrens.
    #
    # Utom där bladets egna etiketter har märkt pennan. En hänvisningslinje sätter sitt märke på röret den
    # pekar på, aldrig på en annan hänvisningslinje, så en penna som två etiketter märkt ritar rör. Ett blad
    # ritar sina värmerör fram till små ringar vid radiatorerna, och textläsningen tog ringarna för bokstaven O:
    # varje streck i pennan slutade då "vid en etikett", och pennan med fyra märkta värmeetiketter domdes som
    # skrivpenna. Ingen av dem fick en meter.
    ticked: dict[str, set[str]] = defaultdict(set)
    for a in anchors:
        if a.state == "VERIFIED_PIPE_ATTACHMENT":
            for c in a.contacts:
                if c.kind in ("end_tick", "crossing_tick"):
                    ticked[c.family].add(a.designation_id)
    for fk in sorted(_writing_pens(page, set(pipe_families), blocks)):
        if len(ticked.get(fk, ())) >= _R("pipeline.WRITING_PEN_TICKED_LABELS", WRITING_PEN_TICKED_LABELS):
            continue
        pipe_families.pop(fk, None)
        graphs.pop(fk, None)
        contact_stats.setdefault("writing_pens_not_taken_as_pipe", []).append(fk)
    native = None
    native_identities, native_elevations = {}, {}
    native_merge = None
    # The reading's own leaders are never pipe. On a page read from pixels a traced leader is a run of the skeleton,
    # and it can carry on into the pipe it points at, so there what it holds is not held out.
    written_leaders = set() if from_image else {pid for ld in leaders for pid in ld.path_ids}
    if source_detector is not None:
        from .source_rules.native_bridge import merge_detection
        # the lettering this reading already built from the glyphs: the detector reads those label boxes from it
        # instead of rasterising and OCR-ing the same strokes again
        known_text = [{"text": r.text, "bbox": [round(v, 2) for v in r.bbox], "angle": round(r.angle, 1)}
                      for r in vtext.rows if not r.unknown_chars and r.text.strip()]
        native = source_detector(page.source_path, page.info.index, progress=progress, known_text=known_text)
        from .source_rules.host_label_repair import repair as repair_label_sizes
        label_sizes = repair_label_sizes(native.get('labels') or [], designations)
        from .source_rules.unattested_codes import set_aside as set_aside_misread_codes
        misread_codes = set_aside_misread_codes(native.get('labels') or [], designations)
        native_merge = merge_detection(page, native, graphs, pipe_families, anchors,
                                       native_identities, native_elevations, not_pipe=written_leaders,
                                       lettering=glyph_pids | annotation_paths)
        native_merge['label_sizes_from_drawing_lettering'] = label_sizes
        native_merge['misread_codes_set_aside'] = misread_codes
        from .source_rules.lost_suffix import restore as restore_lost_suffixes
        native_merge['suffixes_from_drawing_lettering'] = restore_lost_suffixes(
            native.get('labels') or [], [d.text for d in designations])
    graphs, pipe_families = _split_at_tick_contacts(page, graphs, pipe_families, anchors, written_leaders)
    prims = {fk: graphs[fk].prims for fk in graphs}
    # a family taken after the passes ran is not a declined one, whatever the pass that looked at it decided
    if contact_stats.get("declined_families"):
        contact_stats["declined_families"] = {k: v for k, v in contact_stats["declined_families"].items() if k not in pipe_families}
    contact_stats["unconsidered_families"] = _unconsidered(page, pipe_families, contact_stats, ann_layers, glyph_pids, leaders, blocks)
    # where the drawing drew the same line twice. Said, not subtracted: see duplicate_overlaps for the measurement
    # that settles which of the two is the smaller error.
    dup_pt, dup_places = 0.0, []
    for fk, g in graphs.items():
        t, places = duplicate_overlaps(list(g.prims.values()))
        dup_pt += t
        dup_places.extend(places)
    dup_places.sort(key=lambda d: (-d["pt"], d["source_path"]))
    contact_stats["drawn_twice"] = {"total_pt": round(dup_pt, 2), "places": dup_places[:200],
                                    "n_places": len(dup_places)}
    # filled shapes are counted but never drawn as candidates: a pipe is a stroked line, and a filled outline of
    # a room or a piece of furniture is not one however much of the sheet it covers
    contact_stats["filled_shapes"] = {"paths": sum(1 for p in page.paths if p.kind != "s"),
                                      "length_pt": round(sum(p.length for p in page.paths if p.kind != "s"), 1)}
    t0 = _t(timings, "topology_ms", t0)
    if film:
        n_j = sum(len(g.junctions) for g in graphs.values())
        n_n = sum(len(g.nodes) for g in graphs.values())
        film.note("BUILDING_PHYSICAL_PIPES",
                  f"{sum(len(g.prims) for g in graphs.values())} ritade sträckor blir {n_n} noder och "
                  f"{n_j} förgreningar."
                  + (" Så tät förgrening betyder att rör, väggar och symboler ligger i samma graf: en identitet "
                     "kommer inte långt innan den möter en korsning." if n_n and n_j > 0.5 * n_n else ""))
    if progress:
        progress("BUILDING_PHYSICAL_PIPES")
    # what the rest of the sheet already says about where this system is drawn, before anyone is asked anything
    _settle_by_system_usage(anchors)

    # A second reader, where one is offered, sees the open cases before ownership is built - so anything it
    # settles is seeded like any other reading and carried by the same rules, rather than pasted on afterwards.
    second: dict | None = None
    if second_reader is not None:
        from .semantics.astra import Settlement, apply_answers, questions_for, settle as ask_settle
        qs = questions_for(anchors)
        st = Settlement(answers=ask_settle(qs, ask=second_reader))
        second = dict(st.as_dict(), applied=apply_answers(anchors, st.answers))
        anchors.sort(key=lambda a: a.anchor_id)

    def _identities_now() -> dict:
        """What each verified label names, with what the sheet says elsewhere filled in.

        The completion is done here rather than inside the ownership pass so that everything counting labels
        works from the same names: a run written short in one place and in full in another is one entry in the
        takeoff, one label count and one riser count, not two of each.
        """
        return complete_identities(_pipe_identities(
            designations, anchors, grammar,
            _R("pipeline.DN_ROWS_ARE_VERTICAL_ONLY", DN_ROWS_ARE_VERTICAL_ONLY), legend=legend,
            unknown_codes=unknown_codes, sheet_numbers=sheet_numbers,
            run_labels=pipe_labels if other_runs else None))

    scale = discover_scale(page, lines)
    if scale.meters_per_pt is None:
        # nothing on the sheet states its size: measure it on the pipes, whose labels say how wide they are
        from .measure.scale import ScaleResult, is_schematic, pipe_scale, scale_from_pipes
        widths = pipe_scale(page, anchors)
        if widths is not None:
            scale = scale_from_pipes(widths, scale.reason)
        elif is_schematic(lines):
            # a flow or principle diagram is drawn without a scale on purpose: its lines say what connects to
            # what, not how long anything is
            scale = ScaleResult(None, "none", scale.state, scale.evidence, "schematic_not_to_scale")
    if from_image:
        from .measure.scale import scale_read_from_image
        scale = scale_read_from_image(scale)
    if known_scale is not None and not from_image and scale.state in ("NONE", "CONFLICT") and scale.meters_per_pt is None:
        # the rest of the set agreed about how big it is, and this sheet's own stamp did not settle it
        scale = scale_from_the_set(known_scale, f"ritningsomgången är enig; bladets eget besked: {scale.reason}",
                                   known_scale_pages)
    if given_scale:
        # Någon har skrivit in skalan. Den går före bladets egen läsning - personen har ritningen framför sig -
        # men den ersätter den inte tyst: bladets eget utfall står kvar i skälet, och ingen rad som vilar på en
        # handskriven skala får heta bekräftad.
        scale = scale_given_by_hand(given_scale, scale.reason)
    from .measure.scale import ScaleResult, is_section
    if is_section(lines, page.info.width, page.info.height):
        # A section shows the plans' pipes from the side: its lengths are the plans' lengths again, and its
        # vertical lines are as often ladders and walls as pipes. It is read as a schema is - its designations
        # and components counted, no metres taken - whatever scale it is drawn in.
        scale = ScaleResult(None, "none", "NONE", scale.evidence, SECTION_NOT_MEASURED)
    # the rule for connection pipes names short runs; how short is a length in metres, so the scale comes first
    _mpp = scale.meters_per_pt if scale.meters_per_pt else None
    declared_max_pt = (_R("pipes.ownership.DECLARED_RUN_MAX_M", DECLARED_RUN_MAX_M) / _mpp) if _mpp else None
    # the sheet's note for the fixtures it connects without a label (radiators, DN12): applied to short unnamed
    # runs that meet one heating name, as the list calls it
    from .pipes.ownership import BRANCH_RUN_MAX_M
    def _heats(ident) -> bool:
        code = legend.code_for((ident.display or "").upper()) if legend.entries else None
        e = legend.by_code.get(code) if code else None
        desc = (e.description or "").upper() if e else ""
        return bool(re.search(r"V[ÄA]RMEB[ÄA]R|\bV[ÄA]RME\b|RADIATOR", desc)) and not re.search(r"[ÅA]TERVINN", desc)
    branch_rule = (declarations.branches, _heats,
                   (_R("pipes.ownership.BRANCH_RUN_MAX_M", BRANCH_RUN_MAX_M) / _mpp) if _mpp else None) \
        if declarations.branches and _mpp else None
    identities = _identities_now()
    identities.update(native_identities)
    # vad som sitter vid varje fri ände, läst innan ägandet: det bevis en onämnd gren behöver för ett namn
    end_ev = end_evidence(page, graphs)
    source_assignment = None
    elevations = _elevations(blocks, anchors)
    elevations.update(native_elevations)
    hatch = discover_hatch(page, set(pipe_families))
    if source_mode is not None:
        from .source_rules.adapter import analyze as source_analyze
        from .source_rules.styles import resolve as resolve_source_style
        profile, style_evidence = resolve_source_style(page, source_style)
        if native is not None and source_mode == 'combined':
            from .source_rules.native_assignment import analyze as native_analyze
            from .source_rules.native_system_contacts import reject_incompatible_landings
            native_merge['incompatible_landings'] = reject_incompatible_landings(native)
            from .source_rules.native_contacts import supplement
            native_merge['supplementary_contacts'] = supplement(native, anchors, identities, elevations)
            from .source_rules.declaration_candidates import propose
            native_merge['drawing_table_proposals'] = propose(native['graph'], native['labels'], native['association'], declarations.as_dict())
            def host_reading(split_graphs):
                """The host's own reading of the same (split) geometry, on copies of its anchors."""
                import copy
                own = copy.deepcopy(anchors)
                ids = complete_identities(_pipe_identities(
                    designations, own, grammar,
                    _R("pipeline.DN_ROWS_ARE_VERTICAL_ONLY", DN_ROWS_ARE_VERTICAL_ONLY), legend=legend,
                    unknown_codes=unknown_codes, sheet_numbers=sheet_numbers,
                    run_labels=pipe_labels if other_runs else None))
                return propagate(split_graphs, own, page.info.index, ids, spelled_out,
                                 declared=declarations.connection_pipes, declared_max_pt=declared_max_pt, branches=branch_rule,
                                 end_evidence=end_ev)
            ownership, source_assignment = native_analyze(graphs, native, page.info.index,
                source_ask, elevations, page, host_reading)
        else:
            ownership, source_assignment = source_analyze(
                graphs, anchors, identities, page.info.index, mode=source_mode,
                ask=source_ask, elevations=elevations, hatch=hatch, style=profile, leaders=leaders, raw_page=page, endpoint_evidence=end_ev)
        from .source_rules.coverage import report as source_coverage_report
        source_assignment["rule_coverage"] = source_coverage_report()
        source_assignment["style"] = style_evidence
        if native is not None:
            source_assignment['native_detection'] = {
                'state': 'COMPLETED', 'source_pdf_sha256': native['source_pdf_sha256'],
                'timings': native['timings'], 'merge': native_merge,
                'style_match': native.get('style_match'),
                'stages': ['extract', 'profile', 'detect', 'ocr', 'bucket', 'assemble', 'associate'],
                'annotations_used': False, 'expert_overrides_used': False,
                # where each label the detector read sits, and the leaders drawn from it: a pipe names its
                # labels as native_label_<id>, and the viewer lights exactly those when the pipe is picked
                'labels': _native_label_marks(native)}
    else:
        ownership = propagate(graphs, anchors, page.info.index, identities, spelled_out,
                              declared=declarations.connection_pipes, declared_max_pt=declared_max_pt, branches=branch_rule, end_evidence=end_ev)
        if _settle_bundles_by_elimination(anchors, ownership, graphs):
            identities = _identities_now()
            ownership = propagate(graphs, anchors, page.info.index, identities, spelled_out,
                              declared=declarations.connection_pipes, declared_max_pt=declared_max_pt, branches=branch_rule, end_evidence=end_ev)
        # and what one bundle at a time cannot settle, the sheet taken as a whole sometimes can
        if settle_bundles_by_sheet_consistency(anchors, graphs, known_families):
            identities = _identities_now()
            ownership = propagate(graphs, anchors, page.info.index, identities, spelled_out,
                              declared=declarations.connection_pipes, declared_max_pt=declared_max_pt, branches=branch_rule, end_evidence=end_ev)
        # ...and last, what the sheet's own settled bundles say about the order its rows are written in
        if _settle_bundles_by_the_sheets_own_row_order(anchors, page):
            identities = _identities_now()
            ownership = propagate(graphs, anchors, page.info.index, identities, spelled_out,
                              declared=declarations.connection_pipes, declared_max_pt=declared_max_pt, branches=branch_rule, end_evidence=end_ev)
        _close_labels_on_owned_runs(anchors, ownership, graphs)
    # what the reading could not settle is measured all the same, under its best reading or as unnamed pipe, and
    # marked to be reviewed (pipes.ownership.include_for_review)
    from .pipes.ownership import (BEST_READING_AMONG_CANDIDATES, UNNAMED_PEN_NAMED_SHARE, UNNAMED_RUNS_ARE_ROWS,
                                  include_for_review)
    review_taken = include_for_review(
        graphs, ownership, anchors, _identities_now(), page.info.index,
        best=_R("pipes.ownership.BEST_READING_AMONG_CANDIDATES", BEST_READING_AMONG_CANDIDATES),
        # in the widened reading of "Alla" every discipline's lines are open to the labels, and what no label
        # names there is mostly not pipe at all: no unnamed rows
        unnamed=_R("pipes.ownership.UNNAMED_RUNS_ARE_ROWS", UNNAMED_RUNS_ARE_ROWS) and not other_runs,
        named_share=_R("pipes.ownership.UNNAMED_PEN_NAMED_SHARE", UNNAMED_PEN_NAMED_SHARE))
    if review_taken:
        ownership.stats.update(review_taken)
    film.pipes(ownership.pipes)
    t0 = _t(timings, "physical_pipes_ms", t0)
    if progress:
        progress("MEASURING")
    if film:
        st = Counter(a.state for a in anchors)
        film.note("BUILDING_PHYSICAL_PIPES",
                  f"{st.get('VERIFIED_PIPE_ATTACHMENT', 0)} beteckningar möter sitt rör, "
                  f"{st.get('AMBIGUOUS_PIPE_ATTACHMENT', 0)} är tvetydiga och "
                  f"{st.get('NO_PIPE_ATTACHMENT', 0)} når ingen rörgeometri alls.")
    if film:
        sv = {"FROM_THE_SET": "hämtad från handlingen - bladets egen stämpel avgjorde inget",
              "VERIFIED": "verifierad - utskriven skala och skalstock säger samma sak",
              "STATED": "tagen ur den utskrivna skalan", "BAR_ONLY": "tagen ur skalstocken; ingen utskriven skala",
              "DIMENSIONS_ONLY": "tagen ur bladets måttsättning; ingen utskriven skala",
              "FROM_PIPES": "mätt på rören - deras beteckningar säger hur breda de är; ingen utskriven skala",
              "CONFLICT": "utskriven skala och skalstock säger emot varandra", "NONE": "gick inte att fastställa"}
        film.note("MEASURING",
                  f"Skalan: {sv.get(scale.state, scale.state.lower())}"
                  + (f", {scale.meters_per_pt:.6f} m per punkt." if scale.meters_per_pt else ".")
                  + ("" if scale.state in ("VERIFIED", "STATED", "BAR_ONLY", "FROM_THE_SET", "DIMENSIONS_ONLY", "FROM_PIPES")
                     else " Utan säker skala mäts ingenting."))
    elevations = _elevations(blocks, anchors)
    # read the sheet again by the other routes, put the answers side by side, and let a second route add what the
    # first missed or take out what it contradicts
    _read = SimpleNamespace(graphs=graphs, ownership=ownership, scale=scale, designations=designations,
                            anchors=anchors, legend=legend, pipe_families=pipe_families, page=page,
                            lines=lines, contact_stats=contact_stats)
    route_reports = run_routes(_read)
    crosscheck = cross_check(_read, route_reports)
    crosscheck["applied"] = apply_routes(_read, route_reports) if source_mode is None else {"skipped": "source_assignment_is_final"}
    review_findings = review(_read, crosscheck)
    t0 = _t(timings, "routes_ms", t0)
    hatch = discover_hatch(page, set(pipe_families))
    hatched_pt: dict[str, float] = {}
    if hatch:
        # Hur mycket av varje bit som ligger inne i skrafferingen, inte om dess mittpunkt råkar göra det.
        # Mittpunkten var hela provet förut, och en bit är antingen hel eller ingen: ett rör som ritats som en
        # enda lång linje tvärs genom en vägg fick noll skrafferade meter, för mitten låg utanför väggen. Det
        # är just det fallet man ser på en ritning där väggen är smal och ledningen lång.
        step = max(2.0, min(h.spacing for h in hatch) / 2.0)
        for pp in ownership.pipes:
            g = graphs[pp.family]
            tot = 0.0
            for pid in pp.prim_ids:
                sg = g.prims[pid].seg
                n = max(2, min(HATCH_SAMPLES_MAX, int(sg.length / step) + 1))
                inside = sum(1 for i in range(n)
                             if inside_hatch(hatch, sg.x0 + (sg.x1 - sg.x0) * (i + 0.5) / n,
                                             sg.y0 + (sg.y1 - sg.y0) * (i + 0.5) / n) is not None)
                tot += sg.length * inside / n
            hatched_pt[pp.physical_pipe_id] = tot
    if from_image:
        from .raster import RASTER_FLAG
        for pp in list(ownership.pipes) + list(ownership.review_pipes):
            pp.needs_review = True
            if RASTER_FLAG not in pp.flags:
                pp.flags.append(RASTER_FLAG)
    measures = measure_pipes(ownership, scale, elevations, hatched_pt, from_image=from_image)
    risers = _riser_symbols(page, ann_layers, glyph_pids, graphs, ownership, anchors, identities)
    for key, lst in _shaft_risers(page, ann_layers, glyph_pids, anchors, designations, legend, risers).items():
        risers.setdefault(key, []).extend(lst)
    label_risers = _risers_from_dn_rows(designations, anchors, leaders, identities)
    # En stigare inne i en skraffering hör till den del bladet inte redovisar, precis som röret där: mängdaren
    # räknar den inte (W-50-1-A-0013-bladet med pålbalken: ändpunkterna i skrafferingen räknades som stigare 75).
    if hatch:
        for book in (risers, label_risers):
            for key in list(book):
                book[key] = [r for r in book[key] if inside_hatch(hatch, *r["point"]) is None]
                if not book[key]:
                    del book[key]
    # var varje rör slutar, och varför: inget rör lämnar läsningen utan en kant med skäl
    frontiers = frontiers_of(page, graphs, ownership, risers)
    _by_pipe: dict[str, list[dict]] = defaultdict(list)
    for f in frontiers:
        _by_pipe[f.pipe_id].append(f.as_dict())
    for pp in ownership.pipes:
        pp.frontiers = _by_pipe.get(pp.physical_pipe_id, [])
        pp.frontier_reasons = sorted({f["reason"] for f in pp.frontiers})
    amb_pt: Counter = Counter()
    for fk, g in graphs.items():
        for pid, st in ownership.prim_states[fk].items():
            if st.state == "AMBIGUOUS":
                for ident in st.candidates:
                    amb_pt[ident.key] += g.prims[pid].seg.length / max(len(st.candidates), 1)
    # what a reader counts on the drawing: verified labels per identity (a run usually carries several)
    from .measure.label_counts import verified_label_counts
    label_counts = verified_label_counts(anchors, identities)
    quantities = aggregate(measures, dict(amb_pt), scale.meters_per_pt, risers, dict(label_counts), label_risers)
    film.measured(quantities, scale)
    t0 = _t(timings, "measurement_ms", t0)
    timings.update({f"text_{k}": v for k, v in vt_timing.items()})
    pa = PageAnalysis(page=page, legend=legend, declarations=declarations, second_reader=second, source_assignment=source_assignment, layer_stats=layer_stats, vtext=vtext, srows=srows, lines=lines, blocks=blocks,
                      designations=designations, grammar=grammar, ann_layers=ann_layers, leaders=leaders,
                      pipe_families=pipe_families, prims=prims, graphs=graphs, anchors=anchors, contact_stats=contact_stats,
                      ownership=ownership, scale=scale, measures=measures, quantities=quantities, elevations=elevations,
                      timings=timings, hatch_families=hatch, risers=risers, ocr_assist=ocr_report,
                      crosscheck=crosscheck, review_findings=review_findings,
                      frontiers=[f.as_dict() for f in frontiers])
    # Den som valt "Alla" får varje beteckning bladet skriver, inte bara rören. Rören är VVS-läsningens egna, och
    # en VVS-läsning får ingenting av det här - den ser ut exakt som förut. Andra discipliners ledningar mäts i en
    # andra, vidgad läsning av samma blad, och bara där VVS-läsningen inte redan äger linjerna.
    if _disciplines.current().reads_all and not _disciplines.is_widened():
        pa.wide_runs = widened_runs(pa, page, prep, known_families=known_families, known_legend=known_legend,
                                    known_scale=known_scale, known_scale_pages=known_scale_pages,
                                    given_scale=given_scale)
        from .register import register_of_designations
        pa.register = register_of_designations(pa)
    return pa


def widened_runs(pa: PageAnalysis, page: RawPage, prep: "PreparedPage", **known) -> list[dict]:
    """What a second reading of the sheet measures when other disciplines' labels may name their runs too.

    The VVS reading names a run only with a code the sheet's list calls a system, and counts a family of labels as
    pipes only when its labels carry a DN. A duct is written TL01-Ø250 or FL01-400x200, a cable tray with its width,
    a sprinkler pipe with a code the VVS list never mentions: to the VVS reading none of them names anything. So
    "Alla" reads the same prepared sheet once more, with the discipline's `wide` values, and keeps what that reading
    measures on lines the first reading did not take:

    - a run under a name the takeoff already has is the takeoff's, and is left to it - also where the reading kept
      a note beside the name (S3-P5-160 (L) is S3-P5-160)
    - a run touching a single line the takeoff owns, measured or ambiguous, is not taken either: the line is VVS's
    - the second edge of a double-drawn run carries no metres of its own, as in the takeoff

    The second reading asks no model and uses no second reader: it is the engine's own, and deterministic. Every
    run it gives is for review - no other discipline has a reference takeoff to hold it against.
    """
    from .register import NOTE
    with _disciplines.widened():
        wide = analyze_page(page, prepared=prep, **known)
    owned = {sp for p in pa.ownership.pipes for sp in p.source_paths}
    names = {NOTE.sub("", q.get("designation") or "").upper() for q in pa.quantities}
    runs: dict[str, dict] = {}
    for m in wide.measures:
        p = m.pipe
        if (p.identity is None or NOTE.sub("", p.identity.display or "").upper() in names
                or owned.intersection(p.source_paths)):
            continue
        r = runs.setdefault(p.identity.key, {"designation": p.identity.display, "size": p.identity.dn,
                                             "metres": 0.0, "pieces": 0, "runs": []})
        r["runs"].extend([[round(x, 1), round(y, 1)] for x, y in poly] for poly in p.points)
        if m.twin_of is not None:
            continue                     # the run's second edge: its metres are the first edge's
        r["pieces"] += 1
        r["metres"] += m.horizontal_m or 0.0
    return [dict(r, metres=round(r["metres"], 2)) for r in runs.values() if r["metres"] > 0]


SAME_RISER = 15.0        # pt: a label's leader ends at the riser symbol it names, not exactly on its centre


SHAFT_MARK_MIN, SHAFT_MARK_MAX = 3.5, 14.0    # pt: the ring a riser in a shaft is drawn as
SHAFT_DOUBLE_MIN = 2.2                        # pt: a smaller ring counts only drawn double (pipe and insulation)


def _shaft_risers(page: RawPage, ann_layers, glyph_pids, anchors, designations, legend, risers) -> dict[str, list[dict]]:
    """Risers in a shaft that no horizontal run reaches.

    A shaft drawn in plan is a row of rings - one per riser passing the floor - and the labels beside it point at
    them: KB01-6-80, VB01-2-125, VS01-2-65. Nothing is drawn running into the rings, because the pipes run
    vertically through the plan. The attachment looked for pipe geometry at the end of each leader, found none
    and left the label as "points at nothing", so the shaft's risers were not in the takeoff at all.

    A label that names a pipe by the sheet's own list, carries a dimension, and whose leader ends on a ring of a
    riser's size names that riser. One per ring - or as many as a count prefix says - and only for a ring no other
    riser reading has already counted."""
    from .geometry.core import dist as _dist
    from .pipes.ownership import identity_from_text
    gidx = GeometryIndex(page, set(ann_layers) if ann_layers else set(), glyph_pids)
    round_ = []
    for sym in gidx.symbols:
        w, h = sym.bbox[2] - sym.bbox[0], sym.bbox[3] - sym.bbox[1]
        if 1.0 <= max(w, h) <= SHAFT_MARK_MAX and min(w, h) >= 0.75 * max(w, h):
            round_.append(((sym.bbox[0] + sym.bbox[2]) / 2, (sym.bbox[1] + sym.bbox[3]) / 2, max(w, h) / 2, sym.pid))
    # A small ring alone is an end dot or a connection point; a small ring drawn double - the pipe and its
    # insulation, one inside the other - is a riser, which is how a shaft of thin pipes is drawn. The outer ring
    # stands for the riser; the inner one only says it is double.
    rings = []
    for cx, cy, r, pid in round_:
        if 2 * r < SHAFT_DOUBLE_MIN:
            continue
        double = any(abs(x - cx) <= 0.6 and abs(y - cy) <= 0.6 and rr < r - 0.2 for x, y, rr, _ in round_)
        if 2 * r >= SHAFT_MARK_MIN or double:
            rings.append((cx, cy, r, pid))
    if not rings:
        return {}
    taken = [tuple(r["point"]) for lst in risers.values() for r in lst]
    des = {d.did: d for d in designations}
    out: dict[str, list[dict]] = defaultdict(list)
    for a in sorted(anchors, key=lambda x: x.anchor_id):
        if a.state != "NO_PIPE_ATTACHMENT" or a.dn is None:
            continue
        d = des.get(a.designation_id)
        if d is None or (legend is not None and not legend.names_a_pipe(d)):
            continue
        ex, ey = a.endpoint
        # the nearest ring no other riser has: in a tight shaft two labels end between the same two rings
        near = sorted((_dist((ex, ey), (cx, cy)), cx, cy, r, pid) for cx, cy, r, pid in rings
                      if _dist((ex, ey), (cx, cy)) <= r + 2.0
                      and not any(_dist((cx, cy), t) <= 1.0 for t in taken))
        if not near:
            continue
        _, cx, cy, _, pid = near[0]
        ident = identity_from_text(a.designation_display or a.designation, a.dn, a.system_token, None)
        for _ in range(max(a.multiplier, 1)):
            out[ident.key].append({"designation": ident.display, "dn": ident.dn, "point": [round(cx, 2), round(cy, 2)],
                                   "symbol": pid, "source": "label_at_shaft_ring", "anchor_id": a.anchor_id,
                                   "count_prefix": a.multiplier})
        taken.append((cx, cy))
    return out


def _risers_from_dn_rows(designations, anchors, leaders, identities) -> dict[str, list[dict]]:
    """Risers the drawing names outright: a label whose dimension stands on the row below states the size of the
    VERTICAL pipe at that point (the drop to a drain, a stack), while a dimension inline names the horizontal run.

    Reported alongside the risers found from drawn symbols rather than merged into them. Against the reference
    takeoff of drawing A the two sources disagree - symbols 58, labels 41, reference 55 - and their union (68) is
    further off than either, so the operator chooses which one the quantity uses.

    A stack is counted from what the label says, not from how well its leader landed. Whether the leader could be
    tied to one drawn run decides which run gets metres; it does not decide whether the drawing wrote a stack
    there. So an ambiguous attachment counts too - a count is not a length, and no metre can come out of it.

    What it still may not do is count a code the sheet never uses as a pipe: a fitting tag with a size under it
    would otherwise become a stack. The test is the drawing's own: the base has to be one the sheet already
    carries as a pipe identity somewhere else.
    """
    from .pipes.ownership import identity_from_text
    des = {d.did: d for d in designations}
    ends = {l.lid: l.end for l in leaders}
    # what the sheet carries as a pipe somewhere else, tested on the designation itself rather than on how it
    # happened to be written out: a sheet that always states the insulation would otherwise refuse every stack
    # whose label leaves it off, which is most of them
    known = {i.stem for i in identities.values()}
    mine: dict[str, Any] = {}
    for a in sorted(anchors, key=lambda x: x.anchor_id):
        d = des.get(a.designation_id)
        if d is None or not _is_vertical_label(d) or ends.get(a.leader_id) is None:
            continue
        ident = identities.get(a.anchor_id)
        if ident is None:
            ident = identity_from_text(a.designation_display or a.designation, d.dn, a.system_token, None)
            if ident.stem not in known:
                continue
        mine[a.anchor_id] = ident if ident.dn is not None else replace(ident, dn=d.dn)
    # En stigare namngiven det korta sättet är samma stigare som den namngiven i sin helhet, så kompletteringen
    # måste se hela bladet: `S01-P5` vid stammen tar sin dimension ur `S01-P5-110` bredvid.
    #
    # Men kompletteringen svarar för varje etikett den fick, och skrevs svaret rakt tillbaka hit blev
    # kandidatlistan bladets alla etiketter. Nästa slinga går igenom kandidaterna, och en vågrät etikett med
    # dimensionen inne i raden räknades då som en stigare - stigarantalet blev etikettantalet, och med en satt
    # våningshöjd blev det meter ingen ritning bär. Kandidaternas id:n hålls därför fast genom kompletteringen.
    candidates = list(mine)
    completed = complete_identities({**identities, **mine})
    mine = {aid: completed[aid] for aid in candidates if aid in completed}
    labelled: dict[str, list[dict]] = {}
    for a in sorted(anchors, key=lambda x: x.anchor_id):
        if a.anchor_id not in mine:
            continue
        d = des.get(a.designation_id)
        pt = ends[a.leader_id]
        key = mine[a.anchor_id].key
        lst = labelled.setdefault(key, [])
        if any(dist(tuple(r["point"]), pt) <= 3.0 for r in lst):
            continue                      # two leaders of one label onto the same riser
        lst.append({"designation": d.text, "dn": d.dn, "point": [round(pt[0], 2), round(pt[1], 2)],
                    "evidence": "dimension_on_the_row_below_states_a_vertical_pipe",
                    "attachment": a.state, "designation_id": d.did})
    return labelled


# a small ring (under 4 pt) at the very end of a run, with nothing passing through it, is the riser up to a tap
TAP_RISER_RINGS = True
TAP_RING_MAX = 4.5    # pt: larger is a riser mark of its own family
TAP_RING_PIPES = 2    # designations ending at one tap ring: a cold and a hot connection at most


def _riser_symbols(page: RawPage, ann_layers, glyph_pids, graphs, ownership, anchors, identities) -> dict[str, list[dict]]:
    """Risers (vertical pipes) are drawn as closed marks (circle / circle-cross) that a pipe run ends at or that
    a label points at. Concentric marks form one riser. The riser's designation is the label pointing at it
    (a DN-less label takes the DN of the pipe at the mark), otherwise the designation of the pipe ending there."""
    from .geometry.core import dist as _dist
    from .pipes.ownership import _merge_identity, _seed_prims
    gidx = GeometryIndex(page, set(ann_layers) if ann_layers else set(), glyph_pids)
    syms = [s for s in gidx.symbols if 1.5 <= max(s.bbox[2] - s.bbox[0], s.bbox[3] - s.bbox[1]) <= 14.0 and family_key(s) not in graphs]
    groups: list[dict] = []
    for s in sorted(syms, key=lambda s: s.pid):
        cx, cy = (s.bbox[0] + s.bbox[2]) / 2, (s.bbox[1] + s.bbox[3]) / 2
        size = max(s.bbox[2] - s.bbox[0], s.bbox[3] - s.bbox[1])
        for grp in groups:
            if _dist((cx, cy), grp["center"]) <= 1.0:
                grp["pids"].append(s.pid); grp["size"] = max(grp["size"], size)
                break
        else:
            groups.append({"center": (cx, cy), "size": size, "pids": [s.pid]})
    by_pid = {pid: i for i, grp in enumerate(groups) for pid in grp["pids"]}
    layer_of = {}
    for s in syms:
        layer_of[s.pid] = s.layer
    for grp in groups:
        grp["fam"] = (min(layer_of[p] for p in grp["pids"]), round(grp["size"]))
    gi_idx = GridIndex(cell=12.0)
    for i, grp in enumerate(groups):
        cx, cy = grp["center"]; r = grp["size"] / 2 + 1.5
        gi_idx.insert(i, (cx - r, cy - r, cx + r, cy + r))

    def stack_of(i: int) -> list[int]:
        """Marks of the same family touching / adjacent to mark i (a stack of end markers)."""
        grp = groups[i]
        out_ids, frontier = {i}, [i]
        while frontier:
            j = frontier.pop()
            cj = groups[j]["center"]; sz = groups[j]["size"]
            for k in gi_idx.query_point(cj[0], cj[1], 1.6 * sz):
                if k in out_ids or groups[k]["fam"] != grp["fam"]:
                    continue
                if _dist(cj, groups[k]["center"]) <= 1.5 * max(sz, groups[k]["size"]):
                    out_ids.add(k); frontier.append(k)
        return sorted(out_ids)

    out: dict[str, list[dict]] = defaultdict(list)
    counted: set[int] = set()
    riser_fams: set = set()
    # (a) labels pointing at a mark; a count prefix ("5x") names the number of risers of the mark's stack
    for a in sorted(anchors, key=lambda a: a.anchor_id):
        if a.anchor_id not in identities or not a.contacts or not all(c.kind == "via_symbol" for c in a.contacts):
            continue
        gi = next((by_pid[c.via] for c in a.contacts if c.via in by_pid), None)
        if gi is None or gi in counted:
            continue
        ident = identities[a.anchor_id]
        if ident.dn is None:
            for fk, lst in _seed_prims(a, graphs).items():
                for pid, _, _ in lst:
                    st = ownership.prim_states[fk][pid]
                    if st.state == "CONFIRMED" and st.identity is not None and _merge_identity([ident, st.identity]) is not None:
                        ident = _merge_identity([ident, st.identity])
                        break
        members = stack_of(gi) if a.multiplier > 1 else [gi]
        counted.update(members)
        riser_fams.add(groups[gi]["fam"])
        n = max(a.multiplier, 1)
        for k in range(n):
            grp = groups[members[min(k, len(members) - 1)]]
            out[ident.key].append({"designation": ident.display, "dn": ident.dn, "point": [round(v, 2) for v in grp["center"]],
                                   "symbol": grp["pids"][0], "source": "label", "anchor_id": a.anchor_id, "count_prefix": a.multiplier})
    # (b) unlabeled marks of a riser mark family (established by the labels above) sitting at the end of, or on,
    #     a confirmed pipe: risers of that pipe's designation. Tiny marks (< 4 pt: end dots, connection points)
    #     count only when a label points at them.
    from .geometry.core import point_seg_distance as _psd
    prim_idx: dict[str, GridIndex] = {}
    for fk, g in graphs.items():
        idx = GridIndex(cell=12.0)
        for pid, q in g.prims.items():
            idx.insert(pid, q.seg.bbox())
        prim_idx[fk] = idx
    tap_rings = _rules.value("pipeline.TAP_RISER_RINGS", TAP_RISER_RINGS)
    for i, grp in enumerate(groups):
        small = grp["size"] < 4.0
        if i in counted or (small and not tap_rings) or (not small and grp["fam"] not in riser_fams):
            continue
        if small and grp["size"] > TAP_RING_MAX:
            continue
        cx, cy = grp["center"]; R = grp["size"] / 2 + 1.5
        near = []   # (ends here, dn, distance, identity, family)
        for fk in sorted(graphs):
            g = graphs[fk]
            for pid in sorted(set(prim_idx[fk].query_point(cx, cy, R))):
                q = g.prims[pid]
                d, t = _psd(cx, cy, q.seg)
                if d > R:
                    continue
                st = ownership.prim_states[fk][pid]
                if st.state != "CONFIRMED" or st.identity is None:
                    continue
                at_end = any(_dist((n.x, n.y), (cx, cy)) <= R and n.degree == 1 for n in (g.nodes[k] for k in g.prim_nodes[pid]))
                near.append((at_end, st.identity.dn if st.identity.dn is not None else 10 ** 6, d, st.identity, fk))
        if not near:
            continue
        ending = [c for c in near if c[0]]
        if small:
            # a tap riser: a small ring that a thin run ends at, and nothing passes through it - a dot on a run
            # that goes on is a connection point, not a riser
            if len(ending) != len(near) or len({c[3].key for c in ending}) > TAP_RING_PIPES:
                continue
        # the riser belongs to the run that ends at the mark, not one that passes it; where several end there, the
        # smallest: the branch rises, the main it leaves stays on the floor
        _, _, _, ident, fk = min(ending, key=lambda c: (c[1], c[2])) if ending else min(near, key=lambda c: c[2])
        src = "tap_ring" if small else ("pipe_end" if ending else "on_pipe")
        counted.add(i)
        out[ident.key].append({"designation": ident.display, "dn": ident.dn, "point": [round(cx, 2), round(cy, 2)],
                               "symbol": grp["pids"][0], "source": src, "family": fk})
    return dict(out)


def _rows_owning_leader(block: AnnotationBlock, rows: list[Designation], ld: Leader) -> list[Designation]:
    """Within a label unit of several designation rows each carrying its own underline (no box frame), a leader
    starting at the end of one row's underline belongs to that row alone."""
    if len(rows) > 1 and ld.start_span is not None:
        # ...and where a row holds several designations side by side, the line under them is drawn in pieces,
        # one under each. The leader left from one of those pieces, and it speaks for the label written over it.
        d, _n = row_axes(block.angle)
        lo, hi = ld.start_span
        own = []
        for des in rows:
            xs = [project((des.bbox[0], des.bbox[1]), d), project((des.bbox[2], des.bbox[1]), d),
                  project((des.bbox[0], des.bbox[3]), d), project((des.bbox[2], des.bbox[3]), d)]
            if min(hi, max(xs)) - max(lo, min(xs)) > 0:
                own.append(des)
        if len(own) == 1:
            return own
    if len(rows) <= 1 or block.box_segs or ld.start_type != "underline_end":
        return rows
    tol = 0.35 * max(block.height, 1.0)
    own = []
    for d in rows:
        br = block.rows[d.row_index]
        if any(dist(ld.start, ep) <= tol for u in br.underline for ep in ((u.seg.x0, u.seg.y0), (u.seg.x1, u.seg.y1))):
            own.append(d)
    return own if len(own) == 1 else rows


def _split_at_tick_contacts(page: RawPage, graphs: dict, pipe_families: dict, anchors: list[PipeCodeAnchor],
                            leader_pids: set[str] | None = None):
    """Tick marks of verified leaders are drawn boundary evidence on the pipe: re-split the pipe primitives there
    so every tick contact becomes a graph node (ownership can then change identity exactly at the tick).

    leader_pids: the reading's own leaders. The pen is collected again, and a sheet that writes with the pen it
    draws with had every leader back in the pipe graph, joined to the pipe it points at - and measured as it."""
    pts: dict[str, set[tuple[float, float]]] = defaultdict(set)
    for a in anchors:
        if a.state != "VERIFIED_PIPE_ATTACHMENT":
            continue
        for c in a.contacts:
            if c.kind in ("end_tick", "crossing_tick") and c.family in graphs:
                pts[c.family].add((round(c.point[0], 3), round(c.point[1], 3)))
    if not pts:
        return graphs, pipe_families
    prims_all = collect_prims(page, set(pts), exclude_pids=leader_pids)
    for fk in sorted(pts):
        if not prims_all.get(fk):
            continue
        ps = split_prims_at_points(prims_all[fk], sorted(pts[fk]))
        g = build_graph(ps, fk, graph_tolerances(page), symbols=page_symbols(page))
        graphs[fk] = g
        pipe_families[fk] = describe_family(fk, ps, g)
    return graphs, pipe_families


def _pipe_identities(designations, anchors, grammar, dn_rows_are_vertical_only: bool = False,
                    legend=None, unknown_codes: set[str] | None = None,
                    sheet_numbers: set[str] | None = None, run_labels: set[str] | None = None) -> dict[str, Identity]:
    """Anchors of pipe-designation grammar families: a family qualifies when >= 50 % of its members carry a DN
    (inline or DN row) or >= 50 % of its verified attachments have layer-token support. Other code families
    (component tags) never seed pipe ownership.

    dn_rows_are_vertical_only: whether a label whose dimension stands on the row below names ONLY a vertical pipe,
    so that the run its leader touches gets no horizontal metres from it. The reading of the convention is not in
    doubt - a dimension on the row below is a stack - but what the takeoff does with the run underneath it is a
    measured question, not a deduced one, and the switch is here so it can be measured rather than argued.

    run_labels: in the widened reading of "Alla", the labels that name runs (_names_a_run). Only they seed a run
    there. A size makes a family of tags look like one of runs: a terminal the sheet's list explains, tagged with
    its connection's size, had the outline it is drawn as measured under its tag. What the list explains as a
    thing, a tag and a code the list never mentions are counted there, never measured. The VVS reading passes none.
    """
    des_by_id = {d.did: d for d in designations}
    unknown = unknown_codes or set()
    # In the widened reading of "Alla" a duct's size (Ø250, 400x200) is a size as a DN is
    sized = _disciplines.value("pipeline.DUCT_SIZES_ARE_SIZES", False)
    fam_members: Counter = Counter()
    fam_dn: Counter = Counter()
    fam_ver: Counter = Counter()
    fam_tok: Counter = Counter()
    # En kod bladets egen förklaringslista aldrig nämner röstar inte om vad en formfamilj är. Rumsnummer har
    # samma form som en rörbeteckning, och räknades de med spädde de ut familjen tills den inte längre var en
    # rörfamilj - och då tappade bladet också de riktiga rören i den. Felet syntes som en tom mängdtabell.
    for d in designations:
        if d.did in unknown:
            continue
        fam_members[d.family] += 1
        if d.dn is not None or (sized and run_size(d) is not None):
            fam_dn[d.family] += 1
    for a in anchors:
        if a.state != "VERIFIED_PIPE_ATTACHMENT":
            continue
        d = des_by_id.get(a.designation_id)
        if d is None or d.did in unknown:
            continue
        fam_ver[d.family] += 1
        if a.evidence.get("layer_token_match") or a.evidence.get("layer_token"):
            fam_tok[d.family] += 1
    pipe_fams = set()
    for f, n in fam_members.items():
        if fam_dn[f] >= 0.5 * n or (fam_ver[f] and fam_tok[f] >= 0.5 * fam_ver[f]):
            pipe_fams.add(f)
    out: dict[str, Identity] = {}
    for a in anchors:
        if a.state != "VERIFIED_PIPE_ATTACHMENT":
            continue
        d = des_by_id.get(a.designation_id)
        if d is None:
            continue
        if run_labels is not None and d.did not in run_labels:
            continue        # the widened reading of "Alla": only a label that names a run seeds one
        # A pattern is a weak test of whether a code names a pipe: on a sheet where the component tags happen to
        # share the shape of the system codes, the whole shape fails the test and the systems go with it. The
        # sheet's own designation list settles it directly, so a code it lists as a system qualifies whatever the
        # pattern statistics say - and a code it lists as an object never does.
        if dn_rows_are_vertical_only and _is_vertical_label(d):
            continue                # the label names a stack; it does not claim the run its leader lands on
        by_legend = legend is not None and legend.systems() and legend.names_a_pipe(d)
        if d.family not in pipe_fams and not by_legend:
            continue
        if legend is not None and (d.text or "").upper() in legend.components():
            continue        # the legend says this code names an object, not a pipe
        if d.did in (unknown_codes or set()):
            continue        # bladets egen förklaringslista nämner aldrig den här koden
        if d.did in (sheet_numbers or set()):
            continue        # ett ritningsnummer namnger ett blad, aldrig ett rör
        if _is_an_apparatus_tag(d, legend):
            continue        # AV21-10 är en ventil på röret, inte röret
        gf = grammar.families.get(d.pattern)
        dn_idx = gf.dn_token_index if gf is not None else None
        if dn_idx is None and d.dn_source == "inline":
            toks = d.tokens
            cand = [i for i, t in enumerate(toks) if t.isdigit() and int(t) == d.dn]
            dn_idx = cand[0] if cand else None
        size = run_size(d) if sized and a.dn is None else None
        out[a.anchor_id] = (identity_from_text(a.designation_display or a.designation, size, a.system_token, None)
                            if size is not None else identity_of(a, dn_idx))
    return out


# A run's size as other disciplines write it: a round duct by its diameter (Ø250), a rectangular one by width and
# height (400x200). The width comes first, and the width is what a plan draws, so the duct's two edges lie that far
# apart. Read only in the widened reading of "Alla"; to the VVS reading these are no sizes.
ROUND_SIZE = re.compile(r"^[ØøΦφ⌀](\d{2,4})$")
RECT_SIZE = re.compile(r"^(\d{2,4})[xX×](\d{2,4})$")


def run_size(d) -> int | None:
    """The size a label writes for a duct, in mm across the plan, or None."""
    from .semantics.grammar import split_tokens
    for t in (getattr(d, "tokens", None) or split_tokens(getattr(d, "text", "") or "")):
        m = ROUND_SIZE.match(t.strip()) or RECT_SIZE.match(t.strip())
        if m:
            return int(m.group(1))
    return None


def _another_disciplines_run(d, legend) -> bool:
    """A label the sheet's own list says nothing about, written the way a run is written: with a duct's size
    (Ø250, 400x200), or with a system code of the Swedish table (BRL, KB, G ...).

    A code with a serial number and a size and nothing more is how a valve or an apparatus is tagged, and the tag
    names the thing, not the pipe it sits on. On a section sheet the widened reading measured the outline of a
    drain assembly under its tag AVT101-32: 1.36 m of a device. Such a tag is counted and never measured."""
    from .source_rules.systems import system_code, systems
    text = (d.text or "").upper()
    head = (getattr(d, "system_token", "") or "").upper()
    if legend is not None and legend.entries and (legend.role_of_head(text) is not None
                                                  or legend.role_of_head(head) is not None
                                                  or legend.names_a_component(text)):
        return False
    return run_size(d) is not None or system_code(head) in systems()


def _names_a_run(d, legend) -> bool:
    """Which labels name runs in the widened reading of "Alla": a label the VVS reading would take that writes a
    size or a system the list knows, and another discipline's run.

    A tag (an outlet's UT1, a terminal's TD01) names a thing, and an electrical plan writes far more of them than
    labels of runs. Taken for names of runs, the tags are most of the sheet's labels and none of them reaches a run;
    a sheet whose labels miss their runs is refused (LABELS_MUST_REACH), and the trays went unmeasured with it."""
    head = (getattr(d, "system_token", "") or "").upper()
    sized = d.dn is not None or run_size(d) is not None
    listed = legend is not None and legend.role_of_head(head) == "system"
    return (legend.names_a_pipe(d) and (sized or listed)) or _another_disciplines_run(d, legend)


# Ventilkoder i svensk VVS-praxis: avstängnings-, styr-, injusterings-, back-, säkerhets-, tapp- och
# termostatventil. Se reference_sources/swedish-vvs-drawings-main/data/valves.json.
APPARATUS_HEADS = ("AV", "SV", "RV", "BV", "SÄV", "TV", "TRV", "STV")



def _native_label_marks(native) -> list[dict]:
    """The detector's labels as the viewer draws them: box, text and the leader lines that leave each one."""
    leaders = defaultdict(list)
    for ld in (native.get('association') or {}).get('leaders') or []:
        if ld.get('label') is not None and ld.get('points'):
            leaders[ld['label']].append([[round(x, 2), round(y, 2)] for x, y in ld['points']])
    return [{'id': f"native_label_{l['id']}", 'bbox': [round(v, 2) for v in l['rect']],
             'text': l.get('text') or '', 'leaders': leaders.get(l['id'], [])}
            for l in native.get('labels') or [] if l.get('rect') and l.get('designations')]

def _is_an_apparatus_tag(d, legend) -> bool:
    """Om etiketten är en ventils märkning och inte ett rörs namn.

    `AV21-10` och `SV611-10` står i samma etikettblock som rören och har samma form som en rörbeteckning utan
    material: kod, löpnummer, dimension. Hela formfamiljen bär en dimension, så statistiken kallade den en
    rörfamilj, och ventilen fick metrarna i röret den sitter på (A0222: 1,2 % av bladet under `AV21-10`).

    Ett rörs namn bär system och material (`VS1-S13-22`, `SV01-51-110`); en ventil bär bara kod och dimension.
    Så en ventilkod med exakt två fält är en ventil - utom där bladets egen förklaringslista kallar koden ett
    system, för på ett blad där `SV` är spillvatten är `SV1-110` ett rör.
    """
    tokens = [t for t in (getattr(d, "tokens", None) or []) if t]
    if len(tokens) != 2 or not tokens[1].isdigit():
        return False
    m = re.match(r"^([A-ZÅÄÖ]+)\d+$", tokens[0].upper())
    from . import disciplines
    if not m or m.group(1) not in disciplines.value("pipeline.APPARATUS_HEADS", APPARATUS_HEADS):
        return False
    return not (legend is not None and legend.role_of_head(tokens[0].upper()) == "system")


# Hur stor en förklaringslista ska vara för att få stänga ute en kod, och hur mycket av bladets egna etiketter
# den ska ha visat sig känna igen innan den får göra det. Båda finns för att en lista som inte täcker bladets
# rörordförråd aldrig ska kunna radera ett rör den bara råkat utelämna.
LEGEND_MIN_ENTRIES = 8
LEGEND_MIN_KNOWN_HEADS = 3


def _a_whole_pipe_name_of_a_standard_system(text: str) -> bool:
    """Om etiketten är ett helt rörnamn - system, material, dimension - för ett system ur den svenska tabellen.

    Läsningen av förklaringslistan missar rader: på W-50-1-A-0311 fick den med S1 och S2 men inte S3 eller S4, och
    då raderades varje `S3-P5-110` och `S4-P3-32` som bladet ritar - ett helt spillvattenstråk utan en meter. Ett
    rumsnummer, som regeln finns till för, har aldrig den formen: tre fält med dimensionen sist, och ett system
    som svensk VVS-praxis känner (S, D, KV, VV, VS ...). Ett sådant namn är en rörbeteckning vad listan än missat.
    """
    from .source_rules.systems import systems, system_code
    tokens = [t for t in (text or "").upper().split("/")[0].split("-") if t]
    if len(tokens) < 3 or not tokens[-1].rstrip("LV").isdigit():
        return False
    if not re.match(r"^[A-ZÅÄÖ]+\d+$", tokens[0]) or not re.match(r"^[A-ZÅÄÖ]+\d+$", tokens[1]):
        return False
    return system_code(tokens[0]) in systems()


def _unknown_to_the_legend(legend, designations) -> set[str]:
    """Beteckningar vars kod bladets egen förklaringslista aldrig nämner.

    Ett rumsnummer har samma form som en rörbeteckning. `C 2004` med `FRD` under sig ser ut precis som
    `KV11-16` med sin dimension på raden under - bokstäver, siffror, rader - och formen kan inte skilja dem åt.
    Ett helt hus av rumsnummer hamnade i mängden med meter och stigare, och de metrarna finns inte.

    Listan kan skilja dem åt: `C` står inte i den. Så en kod bladets egen lista aldrig nämner är ingen
    rörbeteckning på det bladet.

    Regeln är smal med flit, för en lista kan vara ofullständig. Den gäller bara när bladet har en egen lista av
    någon storlek, och bara när listan bevisligen känner igen bladets eget ordförråd - flera av de koder
    etiketterna faktiskt öppnar med ska stå i den. Gör de inte det säger listan ingenting om det här bladet, och
    då stänger den inte ute någonting. En kod som står i listan får passera vad den än fått för roll.
    """
    if legend is None or not getattr(legend, "own", False):
        return set()
    entries = getattr(legend, "entries", []) or []
    if len(entries) < _R("pipeline.LEGEND_MIN_ENTRIES", LEGEND_MIN_ENTRIES):
        return set()
    codes = {c.upper() for c in (getattr(legend, "by_code", {}) or {})}
    if not codes:
        return set()

    holds = getattr(legend, "holds", None) or (lambda _b: False)

    def known(d) -> bool:
        text = (getattr(d, "text", "") or "").upper()
        head = (getattr(d, "system_token", "") or "").upper()
        if legend.role_of_head(text) is not None or (head and legend.role_of_head(head) is not None):
            return True
        if any(opens_with(text, c) or opens_with(head, c) for c in codes):
            return True
        return _a_whole_pipe_name_of_a_standard_system(text)

    # Whether the list knows this sheet is asked of the labels out on the drawing, never of the list's own rows.
    # The rows are read as designations like everything else, so every code in the list also stands in the
    # reading as a label sitting inside the list - and those match the list by construction. A sheet whose list
    # covers only valves and materials was credited with a dozen known codes on the strength of its own twelve
    # rows, and then refused every pipe designation it draws: a hundred and thirteen labels, forty-two pipe
    # names, and not a metre. A list must not be allowed to vouch for itself.
    on_the_drawing = [d for d in designations if not holds(getattr(d, "bbox", None))]
    heads_known = {(getattr(d, "system_token", "") or "").upper() for d in on_the_drawing if known(d)}
    heads_known.discard("")
    if len(heads_known) < _R("pipeline.LEGEND_MIN_KNOWN_HEADS", LEGEND_MIN_KNOWN_HEADS):
        return set()
    return {d.did for d in designations if not known(d)}


def _is_vertical_label(d) -> bool:
    """A label whose dimension stands on the row below names a vertical pipe at that point: the drop to a drain,
    a stack. A label with the dimension inline names the horizontal run.

    The exception is a count prefix ("2xKV1-X31" over "16"): that counts parallel pipes running together, a
    bundle along the horizontal run, not a stack - and the reference takeoff of drawing A gives exactly that
    label 0 vertical metres.

    The vertical reading decides how many risers the identity has. It does not take the size away from the run
    the leader touches: measured against the reference, stripping it fragments the horizontal quantity (213.4 m
    of reference became 205.8 m), because a drain connection is usually drawn on a branch of its own size."""
    return d.dn_source == "row" and d.dn is not None and d.multiplier <= 1


ELEV_TAG_RE = __import__("re").compile(r"^([A-ZÅÄÖ]{1,4})\s*([+\-]?)\s*(\d+[.,]?\d*)$")


def _elevations(blocks, anchors) -> dict[str, list[dict]]:
    """Elevation annotations (e.g. VG+1.67, CL 4000) of the label unit of each anchor's designation row."""
    out: dict[str, list[dict]] = {}
    bmap = {b.bid: b for b in blocks}
    for a in anchors:
        b = bmap.get(a.block_id)
        if b is None:
            continue
        ri = a.evidence.get("row_index")
        if ri is None:
            continue
        unit = b.unit_of_row(ri)
        ev = []
        for k in unit:
            r = b.rows[k]
            if r.role != "elevation":
                continue
            m = ELEV_TAG_RE.match(r.text_norm.replace(" ", ""))
            if m:
                try:
                    v = float(m.group(3).replace(",", "."))
                except ValueError:
                    continue
                if m.group(2) == "-":
                    v = -v
                # The unit is what the drawing wrote, not what the number looks like. A decimal separator is a
                # level in metres ("VG+1,67"); a whole number of a thousand or more is millimetres ("CL 4000").
                # A bare small integer says neither, and guessing there turns 100 and 150 into fifty metres of
                # pipe. Such a value is carried with no unit and no vertical length is claimed from it.
                digits = m.group(3)
                unit = "m" if ("." in digits or "," in digits) else ("mm" if abs(v) >= 1000 else None)
                ev.append({"tag": m.group(1), "value": v, "unit": unit,
                           "text": r.text_norm, "row_id": r.line.rid})
        if ev:
            out[a.anchor_id] = ev
    return out


def _layer_template_similar(a: str, b: str) -> bool:
    """Two layer names follow the same template when their token counts differ by <= 1 and >= 60 % of the
    tokens (position-wise) are identical."""
    from .profile.layers import layer_tokens
    ta, tb = layer_tokens(a), layer_tokens(b)
    if not ta or not tb or abs(len(ta) - len(tb)) > 1:
        return False
    n = min(len(ta), len(tb))
    same = sum(1 for i in range(n) if ta[i].upper() == tb[i].upper())
    return same >= 0.6 * max(len(ta), len(tb))


def _generalize_families(page: RawPage, pipe_families: dict, graphs: dict, never: set[str] | None = None):
    """Layers that follow the same name template as discovered pipe layers (same token count, same style)
    and carry chain-like geometry are pipe geometry as well (their pipes may remain UNNAMED).

    `never` is what the sheet writes with rather than draws with - the pens its leaders and the bars under its
    designations are drawn with. An office that names each system's layer after that system names the layer it
    writes that system's labels on the same way, so the template that gathers the pipe layers gathers the text
    layer with them. Taken as pipe, that layer turns every leader the tracer did not follow into measured metres
    and, worse, wins the reading: the labels reach their own leaders, which is a reading that places labels
    without measuring anything the drawing draws.
    """
    if not pipe_families:
        return pipe_families, graphs
    never = never or set()
    from .profile.layers import layer_tokens
    templates = set()
    styles = set()
    tokenised: list[list[str]] = []
    for fk in pipe_families:
        layer, _, style = fk.partition("|s|")
        toks = layer_tokens(layer)
        templates.add((len(toks), tuple(t if i != len(toks) - 1 else "*" for i, t in enumerate(toks))))
        styles.add(style)
        tokenised.append(toks)
    # A layer name may name its system in more than one place - a discipline code and the system code itself.
    # Every position that already varies among the accepted pipe layers is therefore a variable of the template
    # rather than part of it; the constant positions still have to carry the template, so a name with more
    # variables than constants is no template at all.
    by_len: dict[int, list[list[str]]] = defaultdict(list)
    for toks in tokenised:
        by_len[len(toks)].append(toks)
    for n, group in by_len.items():
        if len(group) < 2:
            continue
        tpl = tuple("*" if len({g[i].upper() for g in group}) > 1 else group[0][i] for i in range(n))
        if sum(1 for t in tpl if t == "*") <= n // 2:
            templates.add((n, tpl))
    all_fams = Counter()
    for p in page.paths:
        if p.kind == "s":
            all_fams[family_key(p)] += 1
    add = set()
    for fk in all_fams:
        if fk in pipe_families or fk in never:
            continue
        layer, _, style = fk.partition("|s|")
        if style not in styles:
            continue
        toks = layer_tokens(layer)
        for (n, tpl) in templates:
            if len(toks) == n and all(t == "*" or t == toks[i] for i, t in enumerate(tpl)):
                add.add(fk)
    if add:
        prims = collect_prims(page, add)
        for fk in sorted(add):
            if not prims.get(fk):
                continue
            g = build_graph(prims[fk], fk, graph_tolerances(page), symbols=page_symbols(page))
            rf = describe_family(fk, prims[fk], g)
            if rf.kind != "sparse" and rf.longest_chain >= 25 and rf.total_length >= 60:
                pipe_families[fk] = rf
                graphs[fk] = g
    return pipe_families, graphs


def _names_a_fitting(name: str, legend) -> bool:
    """Whether a written label names a fitting rather than a run: the sheet's own list calls it one, or it is a
    valve's tag (`AV201-40`) by the rule the reading keeps for those."""
    if legend is not None and legend.names_a_component(name):
        return True
    tokens = [t for t in name.split("/")[0].split("-") if t]
    return _is_an_apparatus_tag(SimpleNamespace(tokens=tokens), legend)


def _text_layer_pipe_names(pa: PageAnalysis) -> dict[str, list]:
    """{designation: [rect, ...]} for every pipe designation the page writes as text; empty without a text layer."""
    from types import SimpleNamespace
    from .source_rules.text_labels import text_designations
    from .source_rules.swedish import designation_text
    spans = getattr(getattr(pa, "page", None), "spans", None) or []
    out: dict[str, list] = {}
    try:
        found = text_designations(SimpleNamespace(texts=spans))
    except Exception:
        return {}
    for rect, d in found:
        name = (designation_text(dict(d.__dict__)) or "").strip().upper()
        if name:
            out.setdefault(name, []).append([round(v, 1) for v in rect])
    return out


def _pair_key(name: str):
    """A pair label as a pair, whatever order it is written in: KV02-3-/VV02-3-15 -> ((KV02-3, VV02-3), 15).
    None for a single code. The codes are compared with letter and digit twins folded (KVO1 is KV01)."""
    parts = [p for p in (name or "").upper().split("/") if p]
    if len(parts) < 2:
        return None
    # the size is written once, after the last code, when the codes before it end in a dash: KV02-3-/VV02-3-15.
    # A pair's identity key (KV01-3/VV01-3) carries no size at all.
    m = re.match(r"^(.*?)-(\d{1,4})$", parts[-1]) if parts[0].endswith("-") else None
    dn = m.group(2) if m else ""
    if m:
        parts[-1] = m.group(1)
    fold = str.maketrans({"O": "0", "I": "1"})
    return tuple(sorted(p.rstrip("-").translate(fold) for p in parts)), dn


def reading_coverage(pa: PageAnalysis) -> dict[str, Any]:
    """How much of what the sheet names the reading actually carried through to a metre.

    Every other number in a takeoff is about what was found. This one is about what was not, and it is the only
    figure that tells a sheet the reading got through from a sheet it barely opened: the drawing writes so many
    pipe designations, and the takeoff has metres for so many of them. A sheet that names ninety runs and
    measures four says so in one line instead of in ninety review rows.

    The share is deliberately taken over the names the sheet writes, not over the geometry the reading accepted.
    A reading that accepted no pipe geometry at all has nothing left unowned, and every ratio built on its own
    families is then vacuously perfect - which is exactly the case that needs to be visible.
    """
    # A fitting the sheet writes - a valve, a floor drain - is counted, not measured. It stands in the same blocks
    # as the pipes' names and often in their shape (`AV201-40`), and a share taken over everything written counted
    # every valve as a pipe the reading had missed: on one sheet half its "missed pipes" were its valves. What the
    # sheet's own list calls a fitting, and a valve's tag by the rule the reading already keeps for those, is
    # listed apart with how many times it is written.
    fittings: dict[str, list] = defaultdict(list)
    named = set()
    for d in pa.designations:
        text = (d.text or "").strip().upper()
        if not text:
            continue
        if _names_a_fitting(text, pa.legend):
            if not pa.legend.holds(d.bbox):          # the list's own row explains the code; it is no fitting
                fittings[text].append([round(v, 1) for v in d.bbox])
        elif pa.legend.names_a_pipe(d) and text not in pa.legend.components() and not pa.legend.holds(d.bbox):
            # the list's own rows (DS4, S3, VVCXX-3 ...) name codes, not runs: they are not pipes the reading missed
            named.add(text)
    # A sheet whose lettering is text says itself which pipes it names: every designation it writes, the split form
    # (code over a bare dimension) joined. That list, not the host's own parse of the lettering, is what the share
    # is taken over: the host's parse counts fire classes and fittings (EI60, TV102) and the split form unjoined.
    places = _text_layer_pipe_names(pa)
    if places:
        for name in [n for n in places if _names_a_fitting(n, pa.legend)]:
            places.pop(name)
        named = set(places)
    # a riser is carried too: a shaft's stack has no horizontal metre, it has its count of storeys
    measured = {q["designation"].upper() for q in pa.quantities
                if (q.get("confirmed_total_m") or 0) > 0 or (q.get("riser_count") or 0) > 0}

    measured_pairs = [k for k in (_pair_key(m) for m in measured) if k is not None]

    def carried(name: str) -> bool:
        # a pair written the other way round is the same pair: KV02-3-/VV02-3-15 is VV02-3-/KV02-3-15; and a
        # pair's riser row, named by its identity without a size, carries the label that gave it its size
        k = _pair_key(name)
        return name in measured or any(m.startswith(name + "-") or name.startswith(m + "-") for m in measured) \
            or (k is not None and any(k[0] == m[0] and (k[1] == m[1] or not m[1]) for m in measured_pairs))

    got = {n for n in named if carried(n)}
    ink = {"drawn_pt": 0.0, "confirmed_pt": 0.0, "ambiguous_pt": 0.0, "unowned_pt": 0.0}
    for fk, g in (pa.graphs or {}).items():
        states = (pa.ownership.prim_states if pa.ownership else {}).get(fk, {})
        for pid, prim in g.prims.items():
            L = prim.seg.length
            ink["drawn_pt"] += L
            st = states.get(pid)
            key = {"CONFIRMED": "confirmed_pt", "AMBIGUOUS": "ambiguous_pt"}.get(getattr(st, "state", ""), "unowned_pt")
            ink[key] += L
    # Utan skala finns inga meter att redovisa - och noll meter är inte svaret. Ett blad vars skala aldrig blev
    # fastställd har ritat rör i punkter men ingen omräkning till meter, och att då skriva "0 m ritat rör" säger
    # att bladet är tomt när sanningen är att frågan inte gick att besvara. Metertalen lämnas därför som None,
    # punkterna redovisas som de är, och skalans tillstånd följer med så att den som läser får veta varför.
    mpp = (pa.scale.meters_per_pt if pa.scale else None)
    metres = (lambda pt: round(pt * mpp, 2)) if mpp else (lambda pt: None)
    # A flow or principle diagram names its pipes and draws them without a scale: none of its names is a pipe the
    # reading missed - they are measured on the plans - and listing them as missed sent the reader looking for
    # metres the sheet never had. They are said as what they are: the pipes the schema shows.
    schematic = bool(pa.scale and pa.scale.reason in NOT_MEASURED_HERE)
    section = bool(pa.scale and pa.scale.reason == SECTION_NOT_MEASURED)
    missing = set() if schematic else named - got
    out = {
        "pipe_names": len(named), "pipe_names_with_metres": len(got),
        "share": round(len(got) / len(named), 3) if named and not schematic else None,
        "without_metres": sorted(missing)[:40],
        "names_from": "text_layer" if places else "reading",
        # where on the sheet each name without metres is written, so the reader can go and look
        "missed": [{"name": n, "rects": places[n][:6]} for n in sorted(missing)][:60] if places else [],
        "drawn_m": metres(ink["drawn_pt"]), "confirmed_m": metres(ink["confirmed_pt"]),
        "ambiguous_m": metres(ink["ambiguous_pt"]), "unowned_m": metres(ink["unowned_pt"]),
        "drawn_pt": round(ink["drawn_pt"], 2), "confirmed_pt": round(ink["confirmed_pt"], 2),
        "ambiguous_pt": round(ink["ambiguous_pt"], 2), "unowned_pt": round(ink["unowned_pt"], 2),
        "scale_state": (pa.scale.state if pa.scale else "NONE"),
        "scale_settled": bool(pa.scale and pa.scale.state in SETTLED_SCALE and pa.scale.meters_per_pt),
        "scale_reason": (pa.scale.reason if pa.scale else None),
    }
    if fittings:
        out["components"] = [{"name": n, "count": len(r), "rects": r[:6]} for n, r in sorted(fittings.items())][:60]
    if schematic:
        out["schematic"] = True
        if section:
            out["section"] = True
        out["names_on_schematic"] = [{"name": n, "rects": (places.get(n) or [])[:6]} for n in sorted(named)][:60]
    # Someone else's marks on the sheet, and how far they ran. A page that arrives already measured by hand
    # carries the answer drawn on top of the drawing; the reading takes that ink off before it reads, and says
    # here that it did, so nobody has to wonder whether a number came from the drawing or from the markup.
    mk = getattr(getattr(pa.page, "info", None), "markup_set_aside", None) if getattr(pa, "page", None) else None
    if mk:
        out["markup_set_aside"] = {**mk, "ink_m": metres(mk.get("ink_pt") or 0.0)}
    if pa.frontiers:
        from .pipes.frontier import Frontier as _F
        fs = [_F(d["pipe"], d["family"], d["node"], d["x"], d["y"], d["reason"], d["detail"]) for d in pa.frontiers]
        out["frontiers"] = frontier_summary(fs, pa.ownership.pipes if pa.ownership else [], mpp or 0.0)
    return out


def summarize(pa: PageAnalysis) -> dict[str, Any]:
    st = Counter(a.state for a in pa.anchors)
    return {
        "designations": len(pa.designations), "with_dn": sum(1 for d in pa.designations if d.dn is not None),
        "blocks": len(pa.blocks), "leaders": len(pa.leaders), "designation_leaders": sum(1 for l in pa.leaders if any(d.block_id == l.block_id for d in pa.designations)),
        "anchors": dict(st), "pipe_families": {k: v.kind for k, v in pa.pipe_families.items()},
        "ownership": pa.ownership.stats if pa.ownership else {}, "physical_pipes": len(pa.ownership.pipes) if pa.ownership else 0,
        "scale": pa.scale.state if pa.scale else None,
        "confirmed_horizontal_m": round(sum(q["confirmed_horizontal_m"] for q in pa.quantities), 2),
        "ambiguous_m": round(sum(q["ambiguous_m"] for q in pa.quantities), 2),
        "declared_m": round(sum(q.get("declared_m", 0.0) for q in pa.quantities), 2),
        "declarations": pa.declarations.as_dict() if pa.declarations else None,
        "coverage": reading_coverage(pa),
        "timings_ms": {k: round(v) for k, v in pa.timings.items()},
    }
