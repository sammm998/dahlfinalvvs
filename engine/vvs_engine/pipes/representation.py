"""Pipe representation discovery and fragment chaining.

Physical pipes are usually exported as many straight PDF fragments (dash pieces, dash-dot pieces, polyline
segments). For every (layer, style) family we discover the dominant micro-gap between collinear consecutive
fragments and bridge such gaps only when continuation is unique. Crossing is never connection.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

from ..geometry.core import EXPORT_EPS, GridIndex, Seg, angle_diff, collinear, dist, point_seg_distance, seg_intersection, stable_id
from ..pdf.extract import RawPage, RawPath

from .. import rules as _rules
from .ink import is_stroked


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


TOUCH_TOL = 0.15
# A stroke shorter than this is a dot of the line style - the dot of a dash-dot line - and has no direction of
# its own: at a point and a half long, the export's rounding turns it a few degrees, and a collinearity test
# that trusts its angle finds every dash-to-dot gap "not collinear" and breaks the run at every dot. A dot
# never claims a continuation; it is claimed, by the dash whose ray it lies on.
DOT_MAX = 2.5
DOT_GAP_MAX = 4.0     # pt: a dot this close on the dash's own ray belongs to the line whatever the pen's gap statistics say
# A valve, pump or filter drawn in the line of a pipe interrupts the stroke: the pipe stops at one side of the
# symbol and goes on from the other. The two free ends face each other across the symbol, collinear, and the
# symbol - a small drawn thing of another pen - sits in the gap. That is the drawing saying the pipe runs
# through it; a pipe does not end at a valve. The gap it may span, and how big a symbol may be.
SYMBOL_SPAN = 24.0
SYMBOL_SIZE = 30.0
SYMBOL_OFF = 0.6            # pt: lateral tolerance for the far end, wider than a micro gap's since a symbol's ends are hand-placed


class SymbolIndex:
    """The small drawn things of a page - valves, pumps, filters, markers - by place, built once per page."""

    def __init__(self, page):
        self.idx = GridIndex(cell=12.0)
        self.paths: dict[str, tuple[object, str]] = {}
        for p in page.paths:
            bb = p.bbox
            diag = math.hypot(bb[2] - bb[0], bb[3] - bb[1])
            if 1.5 <= diag <= SYMBOL_SIZE:
                self.paths[p.pid] = (p, stroke_family(p.layer, p.width, p.color))
                self.idx.insert(p.pid, bb)

    def covering(self, x: float, y: float, family: str) -> list[str]:
        """Symbols of another pen whose box holds the point."""
        out = []
        for pid in self.idx.query((x - 1.0, y - 1.0, x + 1.0, y + 1.0)):
            p, fam = self.paths[pid]
            if fam == family:
                continue
            bb = p.bbox
            if bb[0] - 1.0 <= x <= bb[2] + 1.0 and bb[1] - 1.0 <= y <= bb[3] + 1.0:
                out.append(pid)
        return sorted(out)


def page_symbols(page) -> SymbolIndex:
    """The page's symbol index, built the first time it is asked for."""
    cached = getattr(page, "_symbol_index", None)
    if cached is None:
        cached = SymbolIndex(page)
        try:
            page._symbol_index = cached
        except Exception:
            pass
    return cached


@dataclass(frozen=True)
class GraphTolerances:
    """Geometric precision the graph builder may assume of the source (exported vectors are exact)."""
    ang_tol: float = 1.5        # degrees, collinear continuation across a micro gap
    off_tol: float = 0.35       # pt, lateral offset of the continuation
    gap_slack: float = 0.5      # fraction of the gap mode accepted as deviation
    max_gap: float = 12.0       # pt, search window for a continuation
    gap_window: float = 0.0     # pt either side of a gap size that still counts as that size when the family's
                                # dash pattern is found; 0 = the gaps are exact and only the same size counts
    end_hook: float = 0.0       # pt: a line's last stroke this short is a tracer's hook, and the line's direction is
                                # the stroke before it; 0 = the source's strokes are what was drawn


VECTOR_TOL = GraphTolerances()
# A sheet read from its pixels (raster/) is exact to a pixel, not to an export's rounding: at 200 dpi a pixel is a
# third of a point, and a centreline traced out of the ink may stand a pixel off its line or a degree askew.
# The gaps of one dash pattern come out a pixel either way too: on a scanned plan whose pipes are all dash-dot
# lines the commonest gap of 9 pt was read as 8.75, 9.0 and 9.25 in near equal parts, no single size reached the
# share a pattern needs, no dash was joined to the next, and the sheet measured 24 m of 2,300. Counted within
# a point and a half of pixels either way, the pattern is the third of all gaps it is.
# And a traced line ends in a hook: the last pixel or two of the skeleton bend towards a corner of the ink, a
# stroke of half a point at forty degrees from the line. Looked at from its end, every scanned line then pointed
# somewhere else, no gap in it was bridged, and the runs of a scanned plan were a third of a metre long.
RASTER_TOL = GraphTolerances(ang_tol=4.0, off_tol=1.0, gap_window=0.5, end_hook=1.0)


def graph_tolerances(page) -> GraphTolerances:
    if ((getattr(page, "input_class", None) or {}).get("read_as")) == "raster":
        return RASTER_TOL
    return VECTOR_TOL


@dataclass
class Prim:
    """A straight primitive of a pipe-candidate family (one segment of a raw path)."""
    prim_id: int
    pid: str
    seg_index: int
    seg: Seg
    family: str
    layer: str
    width: float
    src_len: float = 0.0            # källsegmentets längd före varje delning - det som säger vad ritaren drog
    solid_long: bool = False        # en lång heldragen linje i en streckad familj: ett annat ritsätt, inte ett streck

    @property
    def a(self):
        return (self.seg.x0, self.seg.y0)

    @property
    def b(self):
        return (self.seg.x1, self.seg.y1)


@dataclass
class Node:
    nid: int
    x: float
    y: float
    prims: list[int] = field(default_factory=list)   # prim ids incident here

    @property
    def degree(self) -> int:
        return len(self.prims)


@dataclass
class PipeGraph:
    family: str
    prims: dict[int, Prim]
    nodes: dict[int, Node]
    prim_nodes: dict[int, tuple[int, int]]           # prim id -> (node a, node b)
    bridges: list[dict]                               # micro-gap bridges (evidence)
    gap_mode: float | None
    junctions: list[dict] = field(default_factory=list)
    solid_long_pt: float | None = None                # över den här längden är ett heldraget streck ett annat ritsätt

    def neighbours(self, prim_id: int, node_id: int) -> list[int]:
        return [p for p in self.nodes[node_id].prims if p != prim_id]


@dataclass
class RepresentationFamily:
    family: str
    layer: str
    style: str
    width: float
    n_prims: int
    total_length: float
    gap_mode: float | None
    dash_mode: float | None
    n_chains: int
    longest_chain: float
    kind: str                       # 'fragmented-dashed' | 'continuous' | 'sparse'
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {"family": self.family, "layer": self.layer, "style": self.style, "width": self.width, "n_primitives": self.n_prims,
                "total_length_pt": round(self.total_length, 1), "gap_mode_pt": self.gap_mode, "dash_mode_pt": self.dash_mode,
                "n_chains": self.n_chains, "longest_chain_pt": round(self.longest_chain, 1), "kind": self.kind, "description": self.description}


def stroke_family(layer: str, width: float, color) -> str:
    """A drawn line's family: the layer it is on, its stroke width, and its colour.

    Colour is part of how a CAD file separates its lines. A flattened export that carries no layers at all still
    draws the building in grey and the installation in black, so two lines of the same width in different colours
    are not one family - reading them as one hands the pipes' vote to the walls.

    Linetype is deliberately not in this key, and that is a measured decision rather than an oversight. It is
    read - `describe_family` reconstructs each family's dash and gap from the drawing, and `build_graph` uses
    those to decide where a broken line continues - but it does not divide the family, for two reasons found in
    the drawings themselves. First, these exports carry no PDF dash array at all: across the whole style library
    every stroke is drawn solid and the dashes are separate short segments, so there is no linetype to key on
    without reconstructing it. Second, when the reconstruction is done and a family's chains are sorted into
    dashed and solid, the solid ones are almost always a bend or a fitting of a few dozen points sitting inside
    a run of several thousand points of dashes. Splitting on linetype would cut those runs in half at exactly
    the places where a pipe is most obviously continuous.
    """
    return _family_string(layer, width, color)


@lru_cache(maxsize=65536)
def _family_string(layer: str, width: float, color: Any) -> str:
    """Samma penna ger samma familj, så strängen byggs en gång per penna och inte en gång per fråga.

    Familjen är en ren funktion av lager, bredd och färg - den kan inte ändra sig under en läsning. Den frågas
    däremot om och om igen: en ledarände frågar efter varje väg på bladet, och ett blad kan ha sjuttiofemtusen
    vägar. Ett blad ritas med några hundra pennor, så minnet är litet och träffarna nästan alla."""
    return f"{layer}|s|w{width:.2f}|c{color if color else '-'}"


def family_key(p: RawPath) -> str:
    return stroke_family(p.layer, p.width, p.color)


def is_sheet_border(p: RawPath, page: RawPage) -> bool:
    """A few square-on segments ruled around nearly the whole sheet: the drawing's own border, never a pipe.

    On a sheet exported without layers the border shares its pen with the pipes, and a note in the title block
    pointing at it would otherwise be measured as a pipe the length of the paper."""
    w = page.info.width or 0.0
    h = page.info.height or 0.0
    if w <= 0 or h <= 0 or len(p.segs) > 6 or not p.segs:
        return False
    if p.bbox[2] - p.bbox[0] < 0.85 * w or p.bbox[3] - p.bbox[1] < 0.85 * h:
        return False
    return all(min(sg.angle, 180.0 - sg.angle) <= 1.0 or abs(sg.angle - 90.0) <= 1.0 for sg in p.segs)


def _stamp(s: Seg) -> tuple:
    """A segment's identity on the page, direction-free and rounded to a twentieth of a point."""
    a = (round(s.x0 * 20), round(s.y0 * 20))
    b = (round(s.x1 * 20), round(s.y1 * 20))
    return (a, b) if a <= b else (b, a)


OVERLAP_ANG = 0.6       # degrees: the same drawn line, redrawn
OVERLAP_OFF = 0.30      # pt across the line: nearer than this and it is the same line, not a second pipe
OVERLAP_MIN = 0.15      # pt: a remainder shorter than this is the rounding of an export, not drawn line


def duplicate_overlaps(prims: list[Prim]) -> tuple[float, list[dict]]:
    """Where the drawing drew the same line twice, and how much length that is.

    The exact-duplicate test in collect_prims catches a segment redrawn end for end. It does not catch the
    commoner case: a run drawn once whole and once in pieces, or two collinear segments sharing part of their
    length. Both are one pipe. Measured over the style library it is a fifth of the drawn length on the sheets
    that do it and a few tenths of a percent on the ones that do not.

    It is reported and not subtracted, and that is a measured decision rather than a shrug. Removing the shared
    length costs more than it saves: the duplicated stubs sit at joins, dropping them moves a graph node, and on
    the reference sheet a size frontier then landed where the drawing makes no join at all - six metres changed
    size to save eight tenths of a metre of double count. So the reading says where the doubled line is and
    leaves the measurement alone until the frontier no longer depends on it.
    """
    kept: list[Prim] = []
    idx = GridIndex(cell=12.0)
    total = 0.0
    places: list[dict] = []
    for q in sorted(prims, key=lambda q: (-q.seg.length, q.pid, q.seg_index)):
        s = q.seg
        L = s.length
        if L <= OVERLAP_MIN:
            continue
        dx, dy = (s.x1 - s.x0) / L, (s.y1 - s.y0) / L
        nx, ny = -dy, dx
        b = s.bbox()
        shared = 0.0
        for k in idx.query((b[0] - _R("pipes.representation.OVERLAP_OFF", OVERLAP_OFF), b[1] - _R("pipes.representation.OVERLAP_OFF", OVERLAP_OFF), b[2] + _R("pipes.representation.OVERLAP_OFF", OVERLAP_OFF), b[3] + _R("pipes.representation.OVERLAP_OFF", OVERLAP_OFF))):
            r = kept[k].seg
            if angle_diff(s.angle, r.angle) > _R("pipes.representation.OVERLAP_ANG", OVERLAP_ANG):
                continue
            o0 = (r.x0 - s.x0) * nx + (r.y0 - s.y0) * ny
            o1 = (r.x1 - s.x0) * nx + (r.y1 - s.y0) * ny
            if abs(o0) > _R("pipes.representation.OVERLAP_OFF", OVERLAP_OFF) or abs(o1) > _R("pipes.representation.OVERLAP_OFF", OVERLAP_OFF):
                continue            # beside this line, not on it
            t0 = (r.x0 - s.x0) * dx + (r.y0 - s.y0) * dy
            t1 = (r.x1 - s.x0) * dx + (r.y1 - s.y0) * dy
            lo, hi = (min(t0, t1), max(t0, t1))
            ov = min(hi, L) - max(lo, 0.0)
            if ov > OVERLAP_MIN:
                shared = max(shared, ov)
        if shared > OVERLAP_MIN:
            total += shared
            places.append({"pt": round(shared, 2), "bbox": [round(v, 1) for v in b],
                           "source_path": q.pid, "family": q.family})
        idx.insert(len(kept), s.bbox())
        kept.append(q)
    places.sort(key=lambda d: (-d["pt"], d["source_path"]))
    return total, places


# A run goes somewhere: the ink it spends buys distance. A drawn figure - a radiator hatched with two dozen
# strokes, a pump, a floor gully - stands still: its ink is spent filling one small box, and no stroke of it ever
# leaves that box. So a knot of strokes whose ink is many times the box it sits in is a figure, not a run.
#
# On the heating sheets the radiators are hatched on a pen of their own. The reading weighed that pen as pipe:
# every leader that passed a radiator gained a second candidate family, the anchor went ambiguous, and the metres
# on the real pipe went to nobody - a hundred metres a sheet. Measured over the corpus, a pipe pen's knots stand
# at 0,8-2,9 and a hatched radiator at 8,8-15,7, so the two are not close.
FIGURE_INK = 6.0          # times: ink over the diagonal of the box the knot sits in
FIGURE_MIN_INK = 40.0     # pt: below this a knot is too small for the ratio to say anything
FIGURE_MAX_SPAN = 200.0   # pt: a drawn object is small - 3,5 m at 1:50. A run may fill a room; a radiator may not.
FIGURE_GAP = 3.0          # pt: strokes this close belong to the same knot


def _knots(prims: list[Prim], gap: float = FIGURE_GAP) -> list[list[Prim]]:
    """Strokes grouped by nearness, not by touching: a hatch stroke inside a radiator touches nothing."""
    idx = GridIndex(cell=12.0)
    for i, q in enumerate(prims):
        idx.insert(i, q.seg.bbox())
    parent = list(range(len(prims)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, q in enumerate(prims):
        b = q.seg.bbox()
        for j in idx.query((b[0] - gap, b[1] - gap, b[2] + gap, b[3] + gap)):
            if j <= i:
                continue
            ra, rb = find(i), find(j)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    groups: dict[int, list[Prim]] = defaultdict(list)
    for i, q in enumerate(prims):
        groups[find(i)].append(q)
    return [groups[k] for k in sorted(groups)]


def _stands_still(knot: list[Prim], ratio: float) -> bool:
    ink = sum(q.seg.length for q in knot)
    xs = [v for q in knot for v in (q.seg.x0, q.seg.x1)]
    ys = [v for q in knot for v in (q.seg.y0, q.seg.y1)]
    diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    return ink >= FIGURE_MIN_INK and 1e-6 < diag <= FIGURE_MAX_SPAN and ink / diag >= ratio


def _closed_strokes(knot: list[Prim], tol: float = TOUCH_TOL) -> list[Prim]:
    """The strokes of a knot that lie on a closed loop of its own drawing: a box, a box within a box, the rungs
    of a filled outline.

    Strokes meet where their ends touch or where an end lands on another stroke; a crossing is no meeting, as
    everywhere in the reading. A run is a tree however it branches - none of its strokes lies on a loop - so the
    strokes of a run that ends at a drawn object are not counted as the object's."""
    n = len(knot)
    idx = GridIndex(cell=12.0)
    for i, q in enumerate(knot):
        idx.insert(i, q.seg.bbox())
    nodes: list[tuple[float, float]] = []
    nidx = GridIndex(cell=6.0)

    def node_at(x: float, y: float) -> int:
        for j in nidx.query_point(x, y, tol):
            if math.hypot(nodes[j][0] - x, nodes[j][1] - y) <= tol:
                return j
        nodes.append((x, y))
        nidx.insert(len(nodes) - 1, (x, y, x, y))
        return len(nodes) - 1

    stops: list[set[tuple[float, int]]] = [set() for _ in range(n)]
    for i, q in enumerate(knot):
        stops[i].add((0.0, node_at(*q.a)))
        stops[i].add((1.0, node_at(*q.b)))
    for i, q in enumerate(knot):
        for x, y in (q.a, q.b):
            for j in idx.query_point(x, y, tol):
                if j == i:
                    continue
                d, t = point_seg_distance(x, y, knot[j].seg)
                if d <= tol and 0.0 < t < 1.0:
                    stops[j].add((t, node_at(x, y)))
    edges: list[tuple[int, int, int, float]] = []
    for i, q in enumerate(knot):
        st = sorted(stops[i])
        for (t0, u), (t1, v) in zip(st, st[1:]):
            if u != v:
                edges.append((u, v, i, (t1 - t0) * q.seg.length))
    adj: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for e, (u, v, _, _) in enumerate(edges):
        adj[u].append((v, e))
        adj[v].append((u, e))
    # the bridges of the knot's graph (Tarjan, iteratively): an edge on no loop
    disc: dict[int, int] = {}
    low: dict[int, int] = {}
    bridges: set[int] = set()
    timer = 0
    for s in sorted(adj):
        if s in disc:
            continue
        disc[s] = low[s] = timer
        timer += 1
        stack = [(s, -1, iter(adj[s]))]
        while stack:
            u, came_by, it = stack[-1]
            for v, e in it:
                if e == came_by:
                    continue
                if v in disc:
                    low[u] = min(low[u], disc[v])
                else:
                    disc[v] = low[v] = timer
                    timer += 1
                    stack.append((v, e, iter(adj[v])))
                    break
            else:
                stack.pop()
                if stack:
                    p = stack[-1][0]
                    low[p] = min(low[p], low[u])
                    if low[u] > disc[p]:
                        bridges.add(came_by)
    on_loop = [0.0] * n
    for e, (_, _, i, length) in enumerate(edges):
        if e not in bridges:
            on_loop[i] += length
    return [q for i, q in enumerate(knot) if on_loop[i] >= 0.5 * q.seg.length > 0]


def figure_pieces(prims: list[Prim]) -> tuple[list[Prim], list[Prim]]:
    """(runs, figures): the strokes that go somewhere, and the knots that stand still and fill a box."""
    runs: list[Prim] = []
    figures: list[Prim] = []
    ratio = _R("pipes.representation.FIGURE_INK", FIGURE_INK)
    loose: list[list[Prim]] = []
    objects: list[tuple[float, float, float, float]] = []
    for knot in _knots(prims):
        if _stands_still(knot, ratio):
            figures.extend(knot)
            continue
        # A run that ends at a drawn object joins the object's knot: an air handling unit drawn box beside box on
        # the pipe pen, with the pipe that feeds it. The knot then reaches as far as the run does, and spends too
        # little ink over that reach to stand still - so the unit was measured as the pipe, round every box. The
        # object's strokes close on themselves and a run's never do, so the strokes on loops are weighed again on
        # their own, by the same measure.
        # An object is larger than a symbol drawn in a line, though: a ring at a pipe's end or a valve's body closes
        # on itself as well, and the run goes on through it - on a section sheet a ring at the end of a pipe drawn
        # as its outline was set aside, and the pipe behind it lost its name.
        closed = _closed_strokes(knot) if len(knot) >= 4 else []
        held: set[int] = set()
        for part in _knots(closed):
            b = _box_of(part)
            if math.hypot(b[2] - b[0], b[3] - b[1]) > SYMBOL_SIZE and _stands_still(part, ratio):
                held.update(id(q) for q in part)
                objects.append(b)
        figures.extend(q for q in knot if id(q) in held)
        rest = [q for q in knot if id(q) not in held]
        if rest:
            loose.append(rest)
    # ...and what such an object holds is the object's: the fan drawn inside the unit stands apart from its edges,
    # too small to stand still on its own, and was left as a run nobody named.
    for rest in loose:
        b = _box_of(rest)
        if any(o[0] - TOUCH_TOL <= b[0] and o[1] - TOUCH_TOL <= b[1] and b[2] <= o[2] + TOUCH_TOL
               and b[3] <= o[3] + TOUCH_TOL for o in objects):
            figures.extend(rest)
        else:
            runs.extend(rest)
    return runs, figures


def _box_of(prims: list[Prim]) -> tuple[float, float, float, float]:
    xs = [v for q in prims for v in (q.seg.x0, q.seg.x1)]
    ys = [v for q in prims for v in (q.seg.y0, q.seg.y1)]
    return min(xs), min(ys), max(xs), max(ys)


def collect_prims(page: RawPage, families: set[str], exclude_pids: set[str] | None = None,
                  figures_out: dict[str, list[Prim]] | None = None) -> dict[str, list[Prim]]:
    """Primitives of the given families. exclude_pids drops individual paths - the leader lines of the drawing,
    which on a sheet without layers are drawn with the same pen as the pipes and would otherwise be measured.

    Drawn figures - a radiator hatched solid on its own pen - are set aside here rather than measured: they are
    ink that stands still, and every consumer of a family's geometry should see the same runs. What was set
    aside is handed back through figures_out so the reading can say so."""
    out: dict[str, list[Prim]] = defaultdict(list)
    seen: dict[str, set[tuple]] = defaultdict(set)
    for p in sorted(page.paths, key=lambda p: p.pid):
        # Bara ritat bläck blir rör: en penna med bredd. Kontraktet står på ett ställe (pipes/ink.py) och
        # anknytningen läser samma - annars kan en etikett peka på bläck ingen mätning känner till.
        if not is_stroked(p):
            continue
        if exclude_pids and p.pid in exclude_pids:
            continue
        if is_sheet_border(p, page):
            continue
        fk = family_key(p)
        if fk not in families:
            continue
        for k, s in enumerate(p.segs):
            if s.length < 1e-6:
                continue
            if _stamp(s) in seen[fk]:
                # the same line drawn a second time on the same pen: one pipe, not two
                continue
            seen[fk].add(_stamp(s))
            out[fk].append(Prim(prim_id=0, pid=p.pid, seg_index=k, seg=s, family=fk, layer=p.layer, width=p.width, src_len=s.length))
    # a pen's figures are not its runs: set them aside before anyone builds a graph on them
    for fk in list(out):
        runs, figures = figure_pieces(out[fk])
        if figures:
            out[fk] = runs
            if figures_out is not None:
                figures_out[fk] = figures
            if not runs:
                del out[fk]
    # deterministic prim ids by content order
    for fk in out:
        out[fk].sort(key=lambda q: (q.pid, q.seg_index))
        for i, q in enumerate(out[fk]):
            q.prim_id = i
    return out


def split_t_junctions(prims: list[Prim]) -> tuple[list[Prim], list[dict]]:
    """An endpoint lying on the interior of another primitive of the same family is a proven T-contact
    (not a crossing): split that primitive there so the junction becomes a graph node."""
    idx = GridIndex(cell=12.0)
    for q in prims:
        idx.insert(q.prim_id, q.seg.bbox())
    pmap = {q.prim_id: q for q in prims}
    cuts: dict[int, list[float]] = defaultdict(list)
    junctions = []
    for q in prims:
        for ep in (q.a, q.b):
            for pid2 in idx.query_point(ep[0], ep[1], TOUCH_TOL + 0.05):
                if pid2 == q.prim_id:
                    continue
                r = pmap[pid2]
                d, t = point_seg_distance(ep[0], ep[1], r.seg)
                if d <= TOUCH_TOL and 0.02 < t < 0.98:
                    # not already an endpoint of r
                    if dist(ep, r.a) > TOUCH_TOL and dist(ep, r.b) > TOUCH_TOL:
                        cuts[pid2].append(t)
                        junctions.append({"prim": pid2, "t": round(t, 4), "from_prim": q.prim_id})
    return _apply_cuts(prims, cuts), junctions


def split_prims_at_points(prims: list[Prim], points: list[tuple[float, float]], tol: float = 1.0) -> list[Prim]:
    """Split primitives at drawn boundary points (tick marks of verified leaders) so that the boundary becomes a
    graph node; only interior hits (not already an endpoint) are cut."""
    if not points or not prims:
        return prims
    idx = GridIndex(cell=12.0)
    for q in prims:
        idx.insert(q.prim_id, q.seg.bbox())
    pmap = {q.prim_id: q for q in prims}
    cuts: dict[int, list[float]] = defaultdict(list)
    for (x, y) in sorted(points):
        for pid in idx.query_point(x, y, tol + 0.1):
            q = pmap[pid]
            d, t = point_seg_distance(x, y, q.seg)
            if d <= tol and 0.02 < t < 0.98 and dist((x, y), q.a) > tol and dist((x, y), q.b) > tol:
                cuts[pid].append(t)
    return _apply_cuts(prims, cuts)


def _apply_cuts(prims: list[Prim], cuts: dict[int, list[float]]) -> list[Prim]:
    if not cuts:
        return prims
    out: list[Prim] = []
    next_id = max(p.prim_id for p in prims) + 1
    for q in sorted(prims, key=lambda q: q.prim_id):
        ts = sorted(set(round(t, 5) for t in cuts.get(q.prim_id, [])))
        if not ts:
            out.append(q)
            continue
        pts = [q.a] + [(q.seg.x0 + t * (q.seg.x1 - q.seg.x0), q.seg.y0 + t * (q.seg.y1 - q.seg.y0)) for t in ts] + [q.b]
        for k in range(len(pts) - 1):
            a, b = pts[k], pts[k + 1]
            if dist(a, b) < 1e-6:
                continue
            nid = q.prim_id if k == 0 else next_id
            if k > 0:
                next_id += 1
            out.append(Prim(prim_id=nid, pid=q.pid, seg_index=q.seg_index, seg=Seg(a[0], a[1], b[0], b[1]), family=q.family, layer=q.layer, width=q.width,
                            src_len=q.src_len or q.seg.length, solid_long=q.solid_long))
    return out


def _merge_nodes(nodes, prim_nodes, nid: int, tn: int, merged: dict[int, int] | None = None) -> None:
    """Join node tn into node nid. `merged` remembers where an emptied node went, so that a later bridge that
    still names the old node lands on the node its pieces now sit in instead of on an empty shell - at a
    crossing two runs bridge onto the same node, and the second must find what the first left behind."""
    if merged is not None:
        while nid in merged:
            nid = merged[nid]
        while tn in merged:
            tn = merged[tn]
        if nid == tn:
            return
        merged[tn] = nid
    for p in nodes[tn].prims:
        nodes[nid].prims.append(p)
        prim_nodes[p] = [nid if x == tn else x for x in prim_nodes[p]]
    nodes[tn].prims = []


def _split_crossings(nodes, pmap, prim_nodes) -> None:
    """A node where every arm pairs off with a collinear arm on the opposite side - two straight runs through one
    point and nothing else - is two lines crossing, not a junction. Two pipes that cross in plan lie at different
    heights; the drawing says nothing about a connection, and a chain that walked into such a node would turn
    the corner into the other line. Each straight pair gets a node of its own at the same place."""
    for nid in sorted(nodes):
        n = nodes[nid]
        arms = sorted(set(n.prims))
        if len(arms) < 4 or len(arms) != len(n.prims):
            continue
        # The node sits where the first bridge left it, which can be a gap's width off the other run's axis, so the
        # arms are paired by their own directions: the same line (within the collinearity tolerance) and their far
        # ends on opposite sides of the node.
        def ends(p):
            q = pmap[p]
            near, far = (q.a, q.b) if dist(q.a, (n.x, n.y)) < dist(q.b, (n.x, n.y)) else (q.b, q.a)
            return near, far
        pairs: list[tuple[int, int]] = []
        left = list(arms)
        while left:
            a = left.pop(0)
            _, fa = ends(a)
            best = None
            for b in left:
                _, fb = ends(b)
                if angle_diff(pmap[a].seg.angle, pmap[b].seg.angle) > 3.0:
                    continue
                if (fa[0] - n.x) * (fb[0] - n.x) + (fa[1] - n.y) * (fb[1] - n.y) >= 0:
                    continue        # same side: a fold, not a run through
                best = b
                break
            if best is None:
                pairs = []
                break
            left.remove(best)
            pairs.append((a, best))
        if len(pairs) < 2:
            continue
        for k, (a, b) in enumerate(pairs):
            na, nb = ends(a)[0], ends(b)[0]
            x, y = (na[0] + nb[0]) / 2.0, (na[1] + nb[1]) / 2.0     # the gap's centre, on the run's own axis
            if k == 0:
                n.x, n.y = x, y
                continue
            new = max(nodes) + 1
            nodes[new] = Node(nid=new, x=x, y=y, prims=[a, b])
            for p in (a, b):
                n.prims.remove(p)
                prim_nodes[p] = [new if x_ == nid else x_ for x_ in prim_nodes[p]]


def _outward(node, prim) -> tuple[float, float] | None:
    """Unit direction of the line leaving `node` along `prim`, pointing away from the primitive."""
    far = prim.b if dist(prim.a, (node.x, node.y)) < dist(prim.b, (node.x, node.y)) else prim.a
    dx, dy = node.x - far[0], node.y - far[1]
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-9 else None


def _corner_bridges(nodes, pmap, prim_nodes, idx, gap_mode: float, gtol: float, tol: GraphTolerances):
    """Pairs of free ends whose outward rays meet at a corner one gap away. Each end may take part in one
    corner only; a contested end is left open."""
    free = [n for n in nodes.values() if n.degree == 1]
    cands: dict[tuple[int, int], tuple[int, int, float, str]] = {}
    use: Counter = Counter()
    reach = gap_mode + gtol
    if reach < 0:
        return []
    # Only ends within one gap of each other can meet at a corner, so each end looks in its own lattice cell and
    # the eight around it. Comparing every free end with every other was quadratic: a dashed sheet has two free
    # ends per dash, and on a dense sheet that is tens of thousands of ends and a reading that never finished.
    cell = max(reach, 1e-3)
    lattice: dict[tuple[int, int], list] = defaultdict(list)
    for m in free:
        lattice[(math.floor(m.x / cell), math.floor(m.y / cell))].append(m)
    for n in free:
        u = _outward(n, pmap[n.prims[0]])
        if u is None:
            continue
        cx, cy = math.floor(n.x / cell), math.floor(n.y / cell)
        near = [m for dx in (-1, 0, 1) for dy in (-1, 0, 1) for m in lattice.get((cx + dx, cy + dy), ())]
        for m in near:
            if m.nid <= n.nid or not m.prims:
                continue
            if abs(m.x - n.x) > gap_mode + gtol or abs(m.y - n.y) > gap_mode + gtol:
                continue
            v = _outward(m, pmap[m.prims[0]])
            if v is None:
                continue
            turn = abs(((math.degrees(math.atan2(u[1], u[0]) - math.atan2(v[1], v[0])) + 180) % 360) - 180)
            if turn > 180 - tol.ang_tol:
                continue                      # only the actual collinearity range belongs to the straight-gap rule
            den = u[0] * (-v[1]) - u[1] * (-v[0])
            if abs(den) < 1e-9:
                continue
            wx, wy = m.x - n.x, m.y - n.y
            t = (wx * (-v[1]) - wy * (-v[0])) / den      # along n's ray
            r = (u[0] * wy - u[1] * wx) / den            # along m's ray
            if t <= 0.2 or r <= 0.2 or t > tol.max_gap or r > tol.max_gap:
                continue
            if abs(t + r - gap_mode) > gtol:
                continue                      # the bend must span exactly one gap of this line style
            key = (min(n.nid, m.nid), max(n.nid, m.nid))
            if key not in cands or t + r < cands[key][2]:
                cands[key] = (n.nid, m.nid, t + r, "corner")
            use[n.nid] += 1; use[m.nid] += 1
    out = []
    for key in sorted(cands):
        a, b = key
        if use[a] > 1 or use[b] > 1:
            continue
        out.append(cands[key])
    return out


def _crossing_in_gap(n, along: float, ux: float, uy: float, pmap, prim_nodes, idx, own: int, far_node: int) -> str | None:
    """Ett streck av samma penna som korsar glappet mellan två fria ändar - inte det egna, inte det som slutar
    i andra änden - på tvären (mer än tjugo grader) och inne i glappet, inte vid dess ändar."""
    x0, y0 = n.x, n.y
    x1, y1 = n.x + ux * along, n.y + uy * along
    box = (min(x0, x1) - 1.0, min(y0, y1) - 1.0, max(x0, x1) + 1.0, max(y0, y1) + 1.0)
    for pid in sorted(idx.query(box)):
        if pid == own or far_node in prim_nodes.get(pid, ()):
            continue
        r = pmap[pid]
        if r.seg.length <= DOT_MAX or angle_diff(r.seg.angle, math.degrees(math.atan2(uy, ux)) % 180.0) < 20.0:
            continue
        # skärning mellan glappets sträcka och strecket, som parametrar längs var och en
        dx, dy = r.seg.x1 - r.seg.x0, r.seg.y1 - r.seg.y0
        den = ux * dy - uy * dx
        if abs(den) < 1e-9:
            continue
        t = ((r.seg.x0 - x0) * dy - (r.seg.y0 - y0) * dx) / den
        u = ((r.seg.x0 - x0) * uy - (r.seg.y0 - y0) * ux) / den
        if 0.05 * along < t < 0.95 * along and -0.05 <= u <= 1.05:
            return f"crossing:{r.pid}"
    return None


def _end_strokes(prims, hook: float):
    """For a free end, the stroke whose direction is the line's: the end's own, or - where the end is a hook no
    longer than `hook` - the stroke of the same path it hangs from."""
    by_seg: dict[tuple[str, int], list[Prim]] = defaultdict(list)
    for q in prims:
        by_seg[(q.pid, q.seg_index)].append(q)

    def stroke(n, q):
        if hook <= 0 or q.seg.length > hook:
            return q
        joint = q.b if dist(q.a, (n.x, n.y)) < dist(q.b, (n.x, n.y)) else q.a
        for k in (q.seg_index - 1, q.seg_index + 1):
            for r in by_seg.get((q.pid, k), ()):
                if r.seg.length > DOT_MAX and min(dist(r.a, joint), dist(r.b, joint)) <= TOUCH_TOL + 0.05:
                    return r
        return q
    return stroke


def _symbol_bridges(nodes, pmap, prim_nodes, idx, symbols: SymbolIndex, family: str, end_stroke=None):
    """Two free ends of one run facing each other across a symbol of another pen: (node, node, gap, symbol).

    Each free end of a real stroke (not a dot) looks ahead along its own ray for the nearest free end of a
    collinear stroke within a symbol's span; the midpoint of the gap has to lie inside a small path of another
    pen. Two ends that name each other are joined; a one-sided claim is joined only when nothing else claims
    either end - the same rule as for a micro gap."""
    claim: dict[int, tuple[int, float, str]] = {}
    for n in sorted(nodes.values(), key=lambda m: m.nid):
        if n.degree != 1:
            continue
        q0 = pmap[n.prims[0]]
        q = end_stroke(n, q0) if end_stroke else q0
        if q.seg.length <= DOT_MAX:
            continue
        far = q.b if dist(q.a, (n.x, n.y)) < dist(q.b, (n.x, n.y)) else q.a
        dx, dy = n.x - far[0], n.y - far[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        ux, uy = dx / L, dy / L
        R = SYMBOL_SPAN
        box = (min(n.x, n.x + ux * R) - 1, min(n.y, n.y + uy * R) - 1, max(n.x, n.x + ux * R) + 1, max(n.y, n.y + uy * R) + 1)
        best = None
        for pid2 in idx.query(box):
            if pid2 in (q.prim_id, q0.prim_id):
                continue
            r = pmap[pid2]
            if end_stroke and r.seg.length <= DOT_MAX:
                # the far end's own hook: the line it hangs from is the one to compare with
                r = next((end_stroke(nodes[k], r) for k in prim_nodes[pid2] if nodes[k].degree == 1), r)
            if r.seg.length <= DOT_MAX or angle_diff(q.seg.angle, r.seg.angle) > 3.0:
                continue
            hooked = pmap[pid2]
            for ep in (hooked.a, hooked.b):
                vx, vy = ep[0] - n.x, ep[1] - n.y
                along = vx * ux + vy * uy
                perp = abs(-vx * uy + vy * ux)
                if 0.5 < along <= R and perp <= SYMBOL_OFF + (0.4 if end_stroke else 0.0):
                    tn = next((nn for nn in prim_nodes[pid2] if dist((nodes[nn].x, nodes[nn].y), ep) <= TOUCH_TOL + 0.05), None)
                    if tn is None or tn == n.nid or nodes[tn].degree != 1:
                        continue
                    if best is None or along < best[0]:
                        best = (along, tn)
        if best is None:
            continue
        along, tn = best
        sym = symbols.covering(n.x + ux * along / 2.0, n.y + uy * along / 2.0, family)
        # ...eller ett streck av samma penna tvärs över glappet: en gren som ansluter, en korsande ledning.
        # Ritaren bryter linjen där en annan går in i den, och de två fria ändarna vänder sig mot varandra
        # över anslutningen precis som över en ventil. Utan något i glappet är två ändar bara två ändar.
        evidence = sym[0] if sym else _crossing_in_gap(n, along, ux, uy, pmap, prim_nodes, idx, q.prim_id, tn)
        if not evidence:
            continue
        claim[n.nid] = (tn, along, evidence)
    pairs: dict[tuple[int, int], tuple[int, int, float, str]] = {}
    for nid in sorted(claim):
        tn, g, sym = claim[nid]
        if claim.get(tn, (None,))[0] == nid:
            pairs.setdefault((min(nid, tn), max(nid, tn)), (nid, tn, g, sym))
    taken = {n for key in pairs for n in key}
    wanted = Counter(tn for tn, _, _ in claim.values())
    for nid in sorted(claim):
        tn, g, sym = claim[nid]
        if nid in taken or tn in taken or tn in claim or wanted[tn] != 1:
            continue
        pairs[(min(nid, tn), max(nid, tn))] = (nid, tn, g, sym)
        taken |= {nid, tn}
    return [pairs[k] for k in sorted(pairs)]


def _windowed_modes(hist: Counter, n: int, window: float) -> list[float]:
    """Up to three gap sizes that recur through a family, each counted with the gaps within `window` of it, and
    each more than a window from the ones already taken - so the pixel either side of one size is that size, and
    not a second size of its own."""
    counted = {g: sum(k for h, k in hist.items() if abs(h - g) <= window) for g in hist}
    modes: list[float] = []
    for g, cnt in sorted(counted.items(), key=lambda v: (-v[1], -hist[v[0]], v[0])):
        if cnt < 0.15 * n or len(modes) == 3:
            break
        if all(abs(g - m) > 2 * window for m in modes):
            modes.append(g)
    return modes


def build_graph(prims: list[Prim], family: str, tol: GraphTolerances | None = None,
                symbols: SymbolIndex | None = None) -> PipeGraph:
    """Nodes: shared endpoints (within TOUCH_TOL) incl. proven T-junctions. Then bridge collinear micro-gaps
    with unique continuation, and the gaps a symbol of another pen sits in."""
    tol = tol or VECTOR_TOL
    prims, junctions = split_t_junctions(prims)
    # 1. endpoint clustering on a lattice
    pts = []
    for q in prims:
        pts.append((q.a, q.prim_id)); pts.append((q.b, q.prim_id))
    nodes: dict[int, Node] = {}
    lattice: dict[tuple[int, int], list[int]] = defaultdict(list)
    prim_nodes: dict[int, list[int]] = defaultdict(list)
    cell = TOUCH_TOL

    def find_node(x, y, not_prim: int | None = None):
        """The node at this point, if the family already has one. `not_prim` keeps a primitive's own two ends
        apart: a line's ends are two places however short the line, and a piece shorter than the touch tolerance
        - the tenth-of-a-point slivers a rounded corner is exported as - would otherwise put both its ends in one
        node. That reads as a loop: the node counts the piece twice, a plain corner comes out as a four-armed
        junction, and the identity stops there rather than running on round the bend."""
        cx, cy = int(math.floor(x / cell)), int(math.floor(y / cell))
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for nid in lattice.get((cx + dx, cy + dy), []):
                    n = nodes[nid]
                    if not_prim is not None and not_prim in n.prims:
                        continue
                    d = math.hypot(n.x - x, n.y - y)
                    if d <= TOUCH_TOL and (best is None or d < best[0]):
                        best = (d, nid)
        return best[1] if best else None

    for q in sorted(prims, key=lambda q: q.prim_id):
        for pt in (q.a, q.b):
            nid = find_node(pt[0], pt[1], not_prim=q.prim_id)
            if nid is None:
                nid = len(nodes)
                nodes[nid] = Node(nid=nid, x=pt[0], y=pt[1])
                lattice[(int(math.floor(pt[0] / cell)), int(math.floor(pt[1] / cell)))].append(nid)
            nodes[nid].prims.append(q.prim_id)
            prim_nodes[q.prim_id].append(nid)
    # 2. micro-gap statistics between collinear consecutive fragments at degree-1 nodes
    idx = GridIndex(cell=12.0)
    pmap = {q.prim_id: q for q in prims}
    for q in prims:
        idx.insert(q.prim_id, q.seg.bbox())
    gaps = []
    cand_bridges = []
    deg1 = [n for n in nodes.values() if n.degree == 1]

    def look_ahead(n, ux: float, uy: float, ref, skip: set[int]):
        """The nearest collinear end ahead of node n along (ux, uy), within the family's largest gap: (along, pid, end)."""
        R = tol.max_gap
        box = (min(n.x, n.x + ux * R) - 1, min(n.y, n.y + uy * R) - 1, max(n.x, n.x + ux * R) + 1, max(n.y, n.y + uy * R) + 1)
        best = None
        for pid2 in idx.query(box):
            if pid2 in skip:
                continue
            r = pmap[pid2]
            is_dot = r.seg.length <= DOT_MAX
            if not is_dot and not collinear(ref.seg, r.seg, ang_tol=tol.ang_tol, off_tol=tol.off_tol):
                continue
            if is_dot:
                # the whole dot has to sit on the dash's own ray, not only the end nearest the gap
                if any(abs(-(e[0] - n.x) * uy + (e[1] - n.y) * ux) > tol.off_tol + 0.15 for e in (r.a, r.b)):
                    continue
            # nearest endpoint of r ahead of the node
            for ep in (r.a, r.b):
                vx, vy = ep[0] - n.x, ep[1] - n.y
                along = vx * ux + vy * uy
                perp = abs(-vx * uy + vy * ux)
                if 0.2 < along <= R and perp <= tol.off_tol:
                    if best is None or along < best[0]:
                        best = (along, pid2, ep)
        return best

    end_stroke = _end_strokes(prims, tol.end_hook) if tol.end_hook > 0 else None
    claimants: set[int] = set()
    for n in deg1:
        q0 = pmap[n.prims[0]]
        q = end_stroke(n, q0) if end_stroke else q0
        if q.seg.length <= DOT_MAX:
            continue                      # a dot's direction is noise: it never claims, it gets claimed
        # direction pointing outward from the node
        far = q.b if dist(q.a, (n.x, n.y)) < dist(q.b, (n.x, n.y)) else q.a
        dx, dy = n.x - far[0], n.y - far[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        ux, uy = dx / L, dy / L
        best = look_ahead(n, ux, uy, q, {q.prim_id, q0.prim_id})
        if best is None:
            continue
        gaps.append(best[0])
        cand_bridges.append((n.nid, best[1], best[2], best[0], pmap[best[1]].seg.length <= DOT_MAX))
        claimants.add(n.nid)
        # A dot the dash claimed lies on the dash's own ray, and the dash's direction is the dot's too: from the
        # dot's far end the run looks on for the next piece the same way. Without this the run stops wherever a
        # dot faces a piece that cannot claim back - a dash whose end is already a junction with a crossing
        # line, as at every crossing where the pieces touch. Two hops, for a dash-dot-dot pattern.
        hops = 0
        while pmap[best[1]].seg.length <= DOT_MAX and hops < 2:
            hops += 1
            dot = pmap[best[1]]
            near = find_node(best[2][0], best[2][1])
            far_n = next((k for k in prim_nodes[dot.prim_id] if k != near), None)
            if far_n is None or nodes[far_n].degree != 1 or far_n in claimants:
                break
            nxt = look_ahead(nodes[far_n], ux, uy, q, {q.prim_id, dot.prim_id})
            if nxt is None:
                break
            gaps.append(nxt[0])
            cand_bridges.append((far_n, nxt[1], nxt[2], nxt[0], pmap[nxt[1]].seg.length <= DOT_MAX))
            claimants.add(far_n)
            best = nxt
    gap_mode = None
    gap_modes: list[float] = []
    if len(gaps) >= 6:
        hist = Counter(round(g * 4) / 4 for g in gaps)
        # A dash-dot line has more than one gap in its pattern - dash to dot and dot to dash, or a dot the export
        # never drew as a stroke of its own - so every gap size that recurs through the family belongs to its
        # style. Taking only the commonest one leaves every second continuation of such a line unbridged.
        if tol.gap_window > 0:
            gap_modes = _windowed_modes(hist, len(gaps), tol.gap_window)
        else:
            gap_modes = [g for g, cnt in hist.most_common(3) if cnt >= 0.15 * len(gaps)]
        gap_mode = gap_modes[0] if gap_modes else None
    bridges = []
    merged_into: dict[int, int] = {}
    if gap_mode is not None or any(is_dot and g <= DOT_GAP_MAX for _, _, _, g, is_dot in cand_bridges):
        gtol = max(0.6, tol.gap_slack * gap_mode) if gap_mode is not None else 0.6
        # the commonest gap keeps the family's own slack; a further gap of the pattern is matched tightly, since
        # it is evidence of a repeat and not a licence to close any distance
        bands = ([(gap_mode, gtol)] if gap_mode is not None else []) + [(g, max(0.6, 0.25 * g)) for g in gap_modes[1:]]
        # unique continuation: each free end names the nearest collinear end ahead of it within the family's own
        # gap; the two ends of one break name each other, and that mutual naming is the drawing's own statement
        # that the run continues there. A third end further back that also names one of them is looking past the
        # break, not competing for it, so it must not stop the pair from being joined. A one-sided claim only
        # bridges when nothing else claims either end.
        claim: dict[int, tuple[int, str, float]] = {}
        for (nid, pid2, ep, g, is_dot) in cand_bridges:
            # a dot on the dash's own ray, this close, is the line's own dot whether or not the pen draws
            # enough of them for the gap to show up as a mode: it is claimed on the geometry alone
            if not (is_dot and g <= DOT_GAP_MAX) and not any(abs(g - m) <= t for m, t in bands):
                continue
            tn = find_node(ep[0], ep[1])
            if tn is None or tn == nid:
                continue
            claim[nid] = (tn, pid2, g)
        pairs: dict[tuple[int, int], tuple[int, int, str, float]] = {}
        for nid in sorted(claim):
            tn, pid2, g = claim[nid]
            if nid in claim.get(tn, (None, None, None))[:1]:
                pairs.setdefault((min(nid, tn), max(nid, tn)), (nid, tn, pid2, g))
        taken = {n for key in pairs for n in key}
        # A one-sided claim competes with the other claims on the same piece, not with every claim on the same
        # node: at a node where a crossing line's pieces already meet, the run continuing straight through and
        # the crossing run continuing straight through each name their own piece, and both go on.
        one_sided: dict[tuple[int, str], list[tuple[int, int, str, float]]] = defaultdict(list)
        for nid in sorted(claim):
            tn, pid2, g = claim[nid]
            if nid in taken or tn in taken:
                continue
            one_sided[(tn, pid2)].append((nid, tn, pid2, g))
        for tn, pid2 in sorted(one_sided):
            lst = one_sided[(tn, pid2)]
            if len(lst) != 1 or lst[0][0] in taken or tn in taken:
                continue    # competing continuations -> no bridge (ambiguous)
            pairs[(min(lst[0][0], tn), max(lst[0][0], tn))] = lst[0]
            taken.add(lst[0][0])
            if nodes[tn].degree == 1:
                taken.add(tn)
        for key in sorted(pairs):
            nid, tn, pid2, g = pairs[key]
            _merge_nodes(nodes, prim_nodes, nid, tn, merged_into)
            bridges.append({"from_node": nid, "to_node": tn, "gap_pt": round(g, 2), "kind": "collinear",
                            "prims": sorted({pmap[n_p].pid for n_p in nodes[nid].prims})[:4]})
        # corner bridges: a dashed run that turns a corner inside a gap leaves two free ends that are not
        # collinear. Their outward rays meet at the corner, and the two legs together span exactly one gap of
        # this line style - the drawing's own evidence that the run continues around the bend.
        for nid, tn, g, kind in (_corner_bridges(nodes, pmap, prim_nodes, idx, gap_mode, gtol, tol) if gap_mode is not None else []):
            _merge_nodes(nodes, prim_nodes, nid, tn, merged_into)
            bridges.append({"from_node": nid, "to_node": tn, "gap_pt": round(g, 2), "kind": kind,
                            "prims": sorted({pmap[n_p].pid for n_p in nodes[nid].prims})[:4]})
    if symbols is not None:
        # a valve in the line, or another line of the same pen crossing it: the run goes on beyond it,
        # whatever gap style the pen has
        for nid, tn, g, sym in _symbol_bridges(nodes, pmap, prim_nodes, idx, symbols, family,
                                               _end_strokes(prims, tol.end_hook) if tol.end_hook > 0 else None):
            _merge_nodes(nodes, prim_nodes, nid, tn, merged_into)
            crossing = sym.startswith("crossing:")
            bridges.append({"from_node": nid, "to_node": tn, "gap_pt": round(g, 2),
                            "kind": "crossing" if crossing else "symbol", "symbol": sym,
                            "prims": sorted({pmap[n_p].pid for n_p in nodes[nid].prims})[:4]})
    _split_crossings(nodes, pmap, prim_nodes)
    # remove emptied nodes
    nodes = {k: v for k, v in nodes.items() if v.prims}
    pn = {k: (v[0], v[1]) for k, v in prim_nodes.items()}
    g = PipeGraph(family=family, prims=pmap, nodes=nodes, prim_nodes=pn, bridges=bridges, gap_mode=gap_mode, junctions=junctions)
    mark_solid_long(g)
    return g


def solid_long_threshold(dash_mode: float | None, gap_mode: float | None) -> float | None:
    """Över den här längden är ett heldraget streck i en streckad familj inte ett streck av den.

    Måttet kommer ur familjen själv: strecken har en längd (dash_mode) och glappen en (gap_mode), och en böj
    eller en armatur ritad heldragen mitt i en streckad ledning är några tiotal punkter - några streck lång.
    En linje som är åtta streck lång, eller fyra streck-och-glapp, är inte en del av strecknings-rytmen; den
    är något annat ritaren drog med samma penna: en pålbalk, en vägg, ett rutnät, en kant."""
    if dash_mode is None or dash_mode <= 0:
        return None
    return max(8.0 * dash_mode, 4.0 * (dash_mode + (gap_mode or 0.0)))


def mark_solid_long(g: PipeGraph) -> None:
    """Märk de primitiver i en streckad familj vars källsegment är för långa för att vara streck.

    Bara familjer som faktiskt är streckade (bryggade glapp) delas så: i en heldragen familj är en lång linje
    precis vad ledningen är. Längden mäts på källsegmentet, före T-delningarna, för en pålbalk som korsas av
    tio ledningar är tio korta bitar i grafen och fortfarande en lång linje på pappret."""
    if g.gap_mode is None or not g.bridges:
        return
    hist = Counter(round(q.src_len or q.seg.length) for q in g.prims.values() if (q.src_len or q.seg.length) > 2)
    if not hist:
        return
    dash_mode = float(hist.most_common(1)[0][0])
    thr = solid_long_threshold(dash_mode, g.gap_mode)
    g.solid_long_pt = thr
    if thr is None:
        return
    for q in g.prims.values():
        q.solid_long = (q.src_len or q.seg.length) > thr


def chains(graph: PipeGraph) -> list[list[int]]:
    """Maximal degree-2 chains of primitives (deterministic order)."""
    visited: set[int] = set()
    out: list[list[int]] = []
    for pid in sorted(graph.prims):
        if pid in visited:
            continue
        chain = [pid]
        visited.add(pid)
        for direction in (0, 1):
            cur = pid
            node = graph.prim_nodes[cur][direction]
            while True:
                nb = graph.neighbours(cur, node)
                if len(nb) != 1 or graph.nodes[node].degree != 2:
                    break
                nxt = nb[0]
                if nxt in visited:
                    break
                visited.add(nxt)
                if direction == 0:
                    chain.insert(0, nxt)
                else:
                    chain.append(nxt)
                a, b = graph.prim_nodes[nxt]
                node = b if a == node else a
                cur = nxt
        out.append(chain)
    return out


def describe_family(fk: str, prims: list[Prim], graph: PipeGraph) -> RepresentationFamily:
    layer, _, style = fk.partition("|s|")
    width = prims[0].width if prims else 0.0
    total = sum(q.seg.length for q in prims)
    lens = [q.seg.length for q in prims]
    dash_mode = None
    if lens:
        hist = Counter(round(l) for l in lens if l > 2)
        if hist:
            dash_mode = float(hist.most_common(1)[0][0])
    ch = chains(graph)
    clen = [sum(graph.prims[p].seg.length for p in c) for c in ch]
    longest = max(clen) if clen else 0.0
    if graph.gap_mode is not None and graph.bridges:
        kind = "fragmented-dashed"
        desc = f"dashed/fragmented line, dash~{dash_mode}pt gap~{graph.gap_mode}pt, width {width:.2f}"
    elif longest > 60:
        kind = "continuous"
        desc = f"continuous polyline, width {width:.2f}"
    else:
        kind = "sparse"
        desc = f"short/isolated strokes, width {width:.2f}"
    return RepresentationFamily(family=fk, layer=layer, style=style, width=width, n_prims=len(prims), total_length=total,
                                gap_mode=graph.gap_mode, dash_mode=dash_mode, n_chains=len(ch), longest_chain=longest, kind=kind, description=desc)
