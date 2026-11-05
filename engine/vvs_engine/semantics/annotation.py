"""VVS annotation population: text lines -> annotation blocks (stacked rows + underlines/boxes) -> designations + DN.

Block geometry is later used by leader discovery: leaders start at block boundaries (underline ends, box corners).
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..geometry.core import GridIndex, Seg, bbox_expand, bbox_intersects, bbox_union, stable_id
from ..pdf.extract import RawPage, RawPath

from .. import rules as _rules


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


# Hur mycket av den mindre rutan som måste ligga inuti den större för att det ska vara samma text ritad två
# gånger. Halva rutan är långt över vad två olika etiketter någonsin delar och långt under vad två läsningar av
# samma etikett delar - de ligger i praktiken ovanpå varandra.
SAME_PLACE_SHARE = 0.5
# ...men en rad som är en liten bit av en annan - ringen i ett Å läst som `O` inne i ordet - är en del av den,
# inte samma text en gång till. Två läsningar av samma etikett har nästan samma ruta; en del av en rad har en
# bråkdel av radens yta.
PART_OF_ROW_SHARE = 0.2

# Hur mycket längre bort blockets näst närmaste etikett måste ligga för att den närmaste ska få svara. Mätt på
# ritningar där två etiketter står staplade över var sitt rör: den som linjen hör till ligger tre till fem
# gånger närmare, och de fall där de ligger lika nära är fall ritningen inte har avgjort.
UNIT_MARGIN = 1.5
from ..text.model import Glyph, TextRow, make_row, project, row_axes
from .grammar import DesignationGrammar, NOMINAL_SIZES, compress_pattern, dn_plausible, is_code_like, split_tokens, strip_count_prefix, strip_row_separator, word_readings


# ----------------------------------------------------------------------------------------------------------------
# lines (rows merged along the baseline)
# ----------------------------------------------------------------------------------------------------------------

def _reading_quality(line: TextRow) -> tuple:
    """Hur väl en rad lästes, för att välja mellan två läsningar av samma rad.

    Sökbar text är vad filen säger; återskapade glyfer är vad formerna ser ut som. Finns båda vinner filen, och
    därefter den läsning som har färst tecken den inte kunde namnge, och sedan den vars glyfer den var säkrast
    på. Sist raden själv, så att samma blad alltid läses likadant.
    """
    gl = getattr(line, "glyphs", ()) or ()
    scores = [getattr(g, "score", 1.0) for g in gl]
    return (1 if getattr(line, "source", "") == "text" else 0,
            -int(getattr(line, "unknown_chars", 0) or 0),
            sum(scores) / len(scores) if scores else 0.0,
            len(line.text or ""),
            getattr(line, "rid", ""))


def _overlap_share(a: tuple, b: tuple) -> float:
    """Hur stor del av den mindre rutan som ligger inuti den större."""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return (ix * iy) / small if small > 0 else 0.0


def _area(r: TextRow) -> float:
    return max(r.bbox[2] - r.bbox[0], 0.0) * max(r.bbox[3] - r.bbox[1], 0.0)


def _a_piece_of(small: TextRow, large: TextRow) -> bool:
    """Whether `small` is a stray piece of the row `large` rather than another reading of the same text.

    Only a character or two, read the same way as the row it lies in, standing lower than the row's own letters - an
    accent's ring or dots, not a letter - and only inside a row read in full: a large row of unread strokes laid
    over real text is not a word the text is a piece of, and never takes its place; and a letter-sized `O` at the
    head of a row `OOOO` is the same ring read twice, which the better reading settles as before."""
    if small.source != large.source or len(small.text.strip()) > 2 or "?" in large.text:
        return False
    if (small.bbox[3] - small.bbox[1]) >= 0.6 * max(large.height, 0.01):
        return False
    return _area(small) < _R("semantics.annotation.PART_OF_ROW_SHARE", PART_OF_ROW_SHARE) * _area(large)


def one_reading_per_place(rows: list[TextRow], report: dict | None = None) -> list[TextRow]:
    """En läsning per ställe på bladet.

    Ett blad kan bära sin text två gånger: en gång som text i filen och en gång som strecken som ritar den,
    lagda på varandra så att en läsare ser en enda. Läsningen såg två, och den sämre halvan var skräp - `I I`
    där filen säger `12`, `O 8` där den säger `08`.

    Det kostar mer än några felstavade koder. Två läsningar av samma etikett hamnar i samma etikettblock, och
    blocket ser då ut som en staplad etikett med två rader som pekar på ett enda rör - det som en ritare skriver
    när KV, VV och VVC går i samma stråk. Läsningen kan inte veta vilken rad som namnger röret, kallar fallet
    tvetydigt och lägger ner. På ett blad av det slaget blev åttiosju beteckningar av fyrtioen verkliga, arton
    av trettio rörnamn tvetydiga på just det skälet, och bladet mätte noll meter av tvåtusen.

    Två rader vars rutor täcker varandra i båda led är alltså samma text ritad två gånger, och den bättre
    läsningen behålls. Det krävs överlappning i BÅDA led med flit: två olika etiketter på samma rad, en till
    vänster och en till höger, är två etiketter och får aldrig slås ihop.
    """
    kept: list[TextRow] = []
    dropped = 0
    for line in sorted(rows, key=lambda r: (r.bbox[1], r.bbox[0], r.rid)):
        for i, other in enumerate(kept):
            if _overlap_share(line.bbox, other.bbox) <= _R("semantics.annotation.SAME_PLACE_SHARE", SAME_PLACE_SHARE):
                continue
            dropped += 1
            small, large = sorted((line, other), key=_area)
            if _a_piece_of(small, large):
                # A piece lying inside a row many times its size is a part of it - the ring of an Å read on its own
                # as `O` - and not the same text written twice. As the better-read of the two it replaced
                # `PÅFYLLNINGSVENTIL` in a legend, and the code it described was left without a description.
                kept[i] = large
            elif _reading_quality(line) > _reading_quality(other):
                kept[i] = line
            break
        else:
            kept.append(line)
    if report is not None:
        report["rows_in"] = len(rows)
        report["rows_kept"] = len(kept)
        report["read_twice"] = dropped
    return kept


def merge_lines(rows: list[TextRow], page: int) -> list[TextRow]:
    """Merge rows sharing angle + baseline whose gap is <= 1.6 H into one line (words separated by a space)."""
    rows = sorted(rows, key=lambda r: r.rid)
    if not rows:
        return []
    idx = GridIndex(cell=40.0)
    for i, r in enumerate(rows):
        idx.insert(i, r.bbox)
    parent = list(range(len(rows)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, r in enumerate(rows):
        d, n = row_axes(r.angle)
        H = max(r.height, 1.0)
        b = bbox_expand(r.bbox, 1.7 * H)
        for j in idx.query(b):
            if j <= i:
                continue
            q = rows[j]
            if q.source != r.source or q.layer != r.layer:
                continue
            if abs(((q.angle - r.angle) + 180) % 360 - 180) > 3:
                continue
            if abs(q.height - r.height) > 0.25 * max(r.height, q.height):
                continue
            # baseline proximity: perpendicular centers within 0.35H
            if abs(project((q.cx, q.cy), n) - project((r.cx, r.cy), n)) > 0.35 * H:
                continue
            # gap along d
            r0, r1 = row_span(r, d); q0, q1 = row_span(q, d)
            gap = max(q0 - r1, r0 - q1)
            if -0.3 * H <= gap <= 1.6 * H:
                pa, pb = find(i), find(j)
                if pa != pb:
                    parent[max(pa, pb)] = min(pa, pb)
    groups: dict[int, list[TextRow]] = defaultdict(list)
    for i in range(len(rows)):
        groups[find(i)].append(rows[i])
    out: list[TextRow] = []
    for g in groups.values():
        if len(g) == 1:
            out.append(g[0])
            continue
        r0 = g[0]
        d, n = row_axes(r0.angle)
        g_sorted = sorted(g, key=lambda r: row_span(r, d)[0])
        glyphs: list[Glyph] = []
        for k, r in enumerate(g_sorted):
            if k > 0:
                prev = g_sorted[k - 1]
                gap = row_span(r, d)[0] - row_span(prev, d)[1]
                if gap > 0.25 * r0.height and glyphs and glyphs[-1].char != " ":
                    glyphs.append(Glyph(gid=r.rid + "_sp", char=" ", bbox=(r.bbox[0], r.bbox[1], r.bbox[0], r.bbox[3]), source=r.source, layer=r.layer))
            glyphs.extend(r.glyphs)
        line = make_row(page, glyphs, r0.angle, r0.source, layer=r0.layer, font=r0.font, family=r0.family)
        out.append(line)
    out.sort(key=lambda r: r.rid)
    return out


def row_span(r: TextRow, d) -> tuple[float, float]:
    """Extent of a row along axis d, from glyph centers +- half glyph size (robust for rotated text)."""
    gl = [g for g in r.glyphs if g.char != " "]
    if not gl:
        corners = [(r.bbox[0], r.bbox[1]), (r.bbox[2], r.bbox[1]), (r.bbox[0], r.bbox[3]), (r.bbox[2], r.bbox[3])]
        ps = [project(c, d) for c in corners]
        return min(ps), max(ps)
    half = 0.5 * max(r.height, 1.0)
    ps = [project((g.cx, g.cy), d) for g in gl]
    # along the reading axis glyph width matters, across it the height does
    ax = math.radians(r.angle)
    along = abs(d[0] * math.cos(ax) + d[1] * math.sin(ax)) > 0.7
    if along:
        ws = [0.5 * max(g.w if abs(math.cos(ax)) > 0.7 else g.h, 0.3) for g in gl]
        return min(p - w for p, w in zip(ps, ws)), max(p + w for p, w in zip(ps, ws))
    return min(ps) - half, max(ps) + half


# ----------------------------------------------------------------------------------------------------------------
# free thin segments (underlines, boxes, leaders) index
# ----------------------------------------------------------------------------------------------------------------

@dataclass
class FreeSeg:
    fid: int
    pid: str
    seg_index: int
    seg: Seg
    layer: str
    width: float
    n_path_segs: int
    color: tuple | None = None


def free_segments(page: RawPage, consumed_pids: set[str]) -> list[FreeSeg]:
    out: list[FreeSeg] = []
    fid = 0
    max_segs = 6
    for p in sorted(page.paths, key=lambda p: p.pid):
        if p.kind != "s" or p.pid in consumed_pids or p.n_curves > 0:
            continue
        if len(p.segs) > max_segs:
            continue
        for k, s in enumerate(p.segs):
            if s.length < 0.3:
                continue
            out.append(FreeSeg(fid=fid, pid=p.pid, seg_index=k, seg=s, layer=p.layer, width=round(p.width, 2),
                               n_path_segs=len(p.segs), color=p.color))
            fid += 1
    return out


# ----------------------------------------------------------------------------------------------------------------
# annotation blocks
# ----------------------------------------------------------------------------------------------------------------

@dataclass
class BlockRow:
    line: TextRow
    role: str = "text"           # designation | dn | elevation | note | count | text
    underline: list[FreeSeg] = field(default_factory=list)
    text_norm: str = ""


@dataclass
class AnnotationBlock:
    bid: str
    page: int
    rows: list[BlockRow]
    bbox: tuple[float, float, float, float]
    angle: float
    height: float
    layer: str
    source: str
    box_segs: list[FreeSeg] = field(default_factory=list)
    frame_layers: Counter = field(default_factory=Counter)
    units: list[list[int]] = field(default_factory=list)     # row index groups sharing one frame / one label

    def unit_of_row(self, ri: int) -> list[int]:
        for u in self.units:
            if ri in u:
                return u
        return [ri]

    def unit_for_point(self, pt: tuple[float, float]) -> list[int] | None:
        """Unit whose frame (underline endpoints) or row extent contains the point (leader start)."""
        best = None
        for u in self.units:
            for ri in u:
                r = self.rows[ri]
                for ul in r.underline:
                    for ep in ((ul.seg.x0, ul.seg.y0), (ul.seg.x1, ul.seg.y1)):
                        d = math.hypot(ep[0] - pt[0], ep[1] - pt[1])
                        if d <= 0.35 * max(self.height, 1.0) and (best is None or d < best[0]):
                            best = (d, u)
        if best is not None:
            return best[1]
        # fall back to the row whose bbox corner is closest
        for u in self.units:
            for ri in u:
                b = self.rows[ri].line.bbox
                for c in ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3])):
                    d = math.hypot(c[0] - pt[0], c[1] - pt[1])
                    if d <= 0.35 * max(self.height, 1.0) and (best is None or d < best[0]):
                        best = (d, u)
        if best is not None:
            return best[1]
        return self._nearest_unit(pt)

    def _nearest_unit(self, pt: tuple[float, float]) -> list[int] | None:
        """Vilken av blockets etiketter en linje hör till, när den inte startar tillräckligt nära någon av dem.

        Att linjen hör till det HÄR blocket är redan avgjort - det avgjordes när linjen hittades. Kvar är bara
        frågan vilken av blockets etiketter, och att inte svara på den kostar allt: den som frågade tog då
        blockets alla rader som en enda staplad etikett, och två etiketter över var sitt rör blev ett fall
        läsningen inte kunde avgöra och lade ner. På ett blad av det slaget blev arton av trettio rörnamn
        tvetydiga på just det, och bladet mätte noll meter av tvåtusen.

        Så närmast vinner - men bara när den är TYDLIGT närmast, med samma disciplin som gäller när en
        hänvisningslinje stannar strax intill ett rör: den näst närmaste måste ligga betydligt längre bort.
        Ligger de lika nära har ritningen inte svarat, och då svarar inte läsningen heller.
        """
        if len(self.units) < 2:
            return self.units[0] if self.units else None
        ds: list[tuple[float, list[int]]] = []
        for u in self.units:
            d = min((math.hypot(x - pt[0], y - pt[1])
                     for ri in u
                     for x, y in ([(ep[0], ep[1]) for ul in self.rows[ri].underline
                                   for ep in ((ul.seg.x0, ul.seg.y0), (ul.seg.x1, ul.seg.y1))]
                                  + [(self.rows[ri].line.bbox[i], self.rows[ri].line.bbox[j])
                                     for i, j in ((0, 1), (2, 1), (0, 3), (2, 3))])), default=None)
            if d is not None:
                ds.append((d, u))
        if len(ds) < 2:
            return ds[0][1] if ds else None
        ds.sort(key=lambda t: t[0])
        margin = _R("semantics.annotation.UNIT_MARGIN", UNIT_MARGIN)
        return ds[0][1] if ds[1][0] >= margin * max(ds[0][0], 1e-6) else None

    @property
    def boundary_points(self) -> list[tuple[float, float]]:
        """Points where a leader may start: underline/box segment endpoints + bbox corners."""
        pts: list[tuple[float, float]] = []
        for r in self.rows:
            for u in r.underline:
                pts += [(u.seg.x0, u.seg.y0), (u.seg.x1, u.seg.y1)]
        for b in self.box_segs:
            pts += [(b.seg.x0, b.seg.y0), (b.seg.x1, b.seg.y1)]
        x0, y0, x1, y1 = self.bbox
        pts += [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
        return pts


@dataclass
class Designation:
    did: str
    page: int
    block_id: str
    row_index: int
    text: str                       # resolved code text
    raw_text: str                   # recognizer reading
    pattern: str
    tokens: list[str]
    system_token: str
    dn: int | None
    dn_source: str | None           # 'inline' | 'row' | None
    dn_row_index: int | None
    dn_row_text: str | None         # the dimension row as drawn, when the dimension stands on the row below
    multiplier: int
    bbox: tuple[float, float, float, float]
    angle: float
    layer: str
    source: str
    glyph_scores: list[float]
    unknown_chars: int
    evidence: dict[str, Any] = field(default_factory=dict)
    family: str = ""

    @property
    def aside(self) -> str:
        """The original parenthesised text, also retained as annotation metadata.

        L/V after a size is a service suffix, not a disposable note. It is kept
        in display_text as well; other parenthetical prose stays in this field.
        """
        if not self.dn_row_text:
            return ""
        m = re.search(r"\(([^()]*)\)\s*$", self.dn_row_text.strip())
        return m.group(0) if m else ""

    @property
    def dimension_text(self) -> str:
        """The dimension row with its aside removed: what the row says the pipe measures."""
        return (self.dn_row_text or "")[:len(self.dn_row_text or "") - len(self.aside)].strip() if self.aside \
            else (self.dn_row_text or "")

    @property
    def display_text(self) -> str:
        """The designation as the drawing states it.

        A dimension written on the row below belongs to the code above it - the drawing only breaks the line to
        fit the label - so the name a reader would write down, and the name a takeoff lists, carries it. The two
        rows are joined by the separator the code itself uses between its tokens. What the row adds in
        parentheses stays in metadata; L/V service suffixes also remain in the name."""
        if self.dn_source != "row" or not self.dimension_text:
            return self.text
        dim = self.dimension_text
        if self.dn is not None and re.fullmatch(r"\(\s*[LV]\s*\)", self.aside, re.I):
            dim = f"{dim.strip()} ({self.aside.strip('() ').strip().upper()})"
        seps = re.findall(r"[\-/+.,:]", self.text)
        sep = seps[0] if seps else "-"
        # a code may end with a short medium qualifier written off with a separator; the dimension goes in front
        # of it, where the drawing puts it when it writes the whole label on one line
        tail = re.search(r"[\-/+.,:][A-ZÅÄÖa-zåäö]{1,3}$", self.text)
        if tail:
            return f"{self.text[:tail.start()]}{sep}{dim}{tail.group(0)}"
        return f"{self.text}{sep}{dim}"

    def as_dict(self) -> dict[str, Any]:
        return {"did": self.did, "page": self.page, "block_id": self.block_id, "row_index": self.row_index, "text": self.text,
                "raw_text": self.raw_text, "pattern": self.pattern, "tokens": self.tokens, "system_token": self.system_token,
                "dn": self.dn, "dn_source": self.dn_source, "display_text": self.display_text, "aside": self.aside,
                "multiplier": self.multiplier, "bbox": [round(v, 2) for v in self.bbox],
                "angle": round(self.angle, 1), "layer": self.layer, "source": self.source, "unknown_chars": self.unknown_chars,
                "min_glyph_confidence": round(1.0 - max(self.glyph_scores), 3) if self.glyph_scores else None,
                "evidence": self.evidence, "family": self.family}


# An elevation is a tag and a level: the level carries a sign or a decimal separator ("VG+1.67", "FG-0.25",
# "VG1.67"), or the two are written apart ("CL 2690", handled separately). A tag and a bare integer run together
# is a code, not a level - a system code names itself that way ("S12", "DBA1"), and reading those as elevations
# hides every designation a drawing writes without a separator.
# A level read from strokes loses its decimal comma to a slash as often as not: "VG+28,46" came out "VG+28/46",
# was no level any more, and was taken for a pipe of size 28 that competed with the pipes it stood beside. After a
# sign, a slash between two numbers is that comma; a pipe name never puts a sign after its system code.
ELEV_RE = re.compile(r"^([A-ZÅÄÖ]{1,4})\s*([+\-]\s*\d+(?:[.,/]\d+|[.,])?|\d+[.,]\d+)$")


def _norm_number(t: str) -> str:
    return t.replace(",", ".")


def _dash_of_a_run(f: FreeSeg, fmap: dict, seg_idx: GridIndex, d, n, lo: float, hi: float, H: float) -> bool:
    """Is this stroke one dash of a dashed line that runs on past the block, rather than a side of its frame?

    A frame side ends at the frame's corners. A dashed pipe passing alongside a label is drawn as a row of
    separate strokes on one pen and one axis, and it carries on beyond the label: the same pen, on the same line,
    a gap apart, outside the block's own span. Taking those dashes for the label's frame put them among the
    sheet's annotation and cut the pipe out of the reading - a short run beside its own label went unmeasured.
    The dashes are followed from this one along the line; strokes that touch end to end (the sides of stacked
    boxes) are not a dashed run and are never followed."""
    pen = (f.layer, round(f.width, 2), f.color)
    axis = project(f.seg.mid, d)
    seen = {f.fid}
    todo = [f]
    while todo and len(seen) < 64:
        cur = todo.pop()
        s = cur.seg
        a0, a1 = sorted((project((s.x0, s.y0), n), project((s.x1, s.y1), n)))
        for fid in seg_idx.query(bbox_expand(s.bbox(), 2.0 * H)):
            if fid in seen:
                continue
            g = fmap[fid]
            if (g.layer, round(g.width, 2), g.color) != pen:
                continue
            t = g.seg
            if abs(project(t.mid, d) - axis) > 0.3 or abs(((t.angle - s.angle) + 90) % 180 - 90) > 2:
                continue
            b0, b1 = sorted((project((t.x0, t.y0), n), project((t.x1, t.y1), n)))
            gap = max(b0 - a1, a0 - b1)
            if gap <= 0.3 or gap > 2.0 * H:
                continue                          # touching end to end, or too far to be the same line
            if b1 < lo or b0 > hi:
                return True                       # the line carries on outside the block
            seen.add(fid)
            todo.append(g)
    return False


def build_blocks(page: RawPage, lines: list[TextRow], free: list[FreeSeg]) -> list[AnnotationBlock]:
    """Group lines into annotation blocks using stacking geometry and underline/box lines."""
    lines = sorted(lines, key=lambda r: r.rid)
    seg_idx = GridIndex(cell=30.0)
    for f in free:
        seg_idx.insert(f.fid, f.seg.bbox())
    fmap = {f.fid: f for f in free}
    # 1. underline of each line: near-parallel free segment just below the line covering >= 50 % of it
    underline_of: dict[str, list[FreeSeg]] = {}
    for ln in lines:
        d, n = row_axes(ln.angle)
        H = max(ln.height, 1.0)
        s0, s1 = row_span(ln, d)
        base = row_span(ln, n)[1]
        found = []
        for fid in seg_idx.query(bbox_expand(ln.bbox, 0.8 * H)):
            f = fmap[fid]
            s = f.seg
            ang = s.angle
            if min(abs(ang - (ln.angle % 180)), 180 - abs(ang - (ln.angle % 180))) > 3:
                continue
            p0 = project((s.x0, s.y0), n); p1 = project((s.x1, s.y1), n)
            off = (p0 + p1) / 2 - base
            if not (-0.15 * H <= off <= 0.6 * H):
                continue
            a0 = min(project((s.x0, s.y0), d), project((s.x1, s.y1), d)); a1 = max(project((s.x0, s.y0), d), project((s.x1, s.y1), d))
            ov = min(a1, s1) - max(a0, s0)
            # an underline underlines this row: it may run past the text a little, but a line many times the
            # row's own length that happens to pass beneath it is a border or a wall, and taking it for the
            # label's frame hands the label every stroke that touches that line anywhere on the sheet
            if ov >= 0.5 * (s1 - s0) and (a1 - a0) <= 2.0 * (s1 - s0) + 2.0 * H:
                found.append(f)
        if found:
            underline_of[ln.rid] = sorted(found, key=lambda f: (f.pid, f.seg_index))
    # 2. stacking: union-find over lines with same angle, overlapping along d, pitch <= 2.4H
    idx = GridIndex(cell=40.0)
    for i, ln in enumerate(lines):
        idx.insert(i, ln.bbox)
    parent = list(range(len(lines)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, ln in enumerate(lines):
        d, n = row_axes(ln.angle)
        H = max(ln.height, 1.0)
        for j in idx.query(bbox_expand(ln.bbox, 2.4 * H)):
            if j <= i:
                continue
            q = lines[j]
            if abs(((q.angle - ln.angle) + 180) % 360 - 180) > 3:
                continue
            if q.source != ln.source:
                continue
            if abs(q.height - ln.height) > 0.35 * max(ln.height, q.height):
                continue
            a0, a1 = row_span(ln, d); b0, b1 = row_span(q, d)
            ov = min(a1, b1) - max(a0, b0)
            left_aligned = abs(a0 - b0) <= 0.6 * H
            if ov < 0.3 * min(a1 - a0, b1 - b0) and not left_aligned:
                continue
            pc = sum(project((g.cx, g.cy), n) for g in ln.glyphs) / max(len(ln.glyphs), 1)
            qc = sum(project((g.cx, g.cy), n) for g in q.glyphs) / max(len(q.glyphs), 1)
            pitch = abs(pc - qc)
            if 0.8 * H <= pitch <= 2.4 * H:
                pa, pb = find(i), find(j)
                if pa != pb:
                    parent[max(pa, pb)] = min(pa, pb)
    groups: dict[int, list[TextRow]] = defaultdict(list)
    for i in range(len(lines)):
        groups[find(i)].append(lines[i])
    blocks: list[AnnotationBlock] = []
    for g in groups.values():
        r0 = g[0]
        d, n = row_axes(r0.angle)
        g_sorted = sorted(g, key=lambda r: sum(project((gg.cx, gg.cy), n) for gg in r.glyphs) / max(len(r.glyphs), 1))
        rows = [BlockRow(line=ln, underline=underline_of.get(ln.rid, [])) for ln in g_sorted]
        bbox = bbox_union([ln.bbox for ln in g_sorted])
        H = sorted(ln.height for ln in g_sorted)[len(g_sorted) // 2]
        # block frame extents in the row frame
        s0 = min(row_span(ln, d)[0] for ln in g_sorted); s1 = max(row_span(ln, d)[1] for ln in g_sorted)
        n0 = min(row_span(ln, n)[0] for ln in g_sorted); n1 = max(row_span(ln, n)[1] for ln in g_sorted)
        for ln in g_sorted:
            for u in underline_of.get(ln.rid, []):
                s0 = min(s0, project((u.seg.x0, u.seg.y0), d), project((u.seg.x1, u.seg.y1), d))
                s1 = max(s1, project((u.seg.x0, u.seg.y0), d), project((u.seg.x1, u.seg.y1), d))
        # box sides: free segments perpendicular to d at the block's side, lying within the block's perpendicular span
        box: list[FreeSeg] = []
        for fid in seg_idx.query(bbox_expand(bbox, 0.6 * H)):
            f = fmap[fid]
            s = f.seg
            ang = s.angle
            perp = abs(((ang - (r0.angle % 180)) + 90) % 180 - 90)
            if abs(perp - 90) > 3:
                continue
            if s.length < 0.8 * H:
                continue
            a = project(s.mid, d)
            if min(abs(a - s0), abs(a - s1)) > 0.5 * H:
                continue
            p0 = project((s.x0, s.y0), n); p1 = project((s.x1, s.y1), n)
            if min(p0, p1) < n0 - 0.6 * H or max(p0, p1) > n1 + 0.6 * H:
                continue
            if _dash_of_a_run(f, fmap, seg_idx, d, n, n0 - 0.6 * H, n1 + 0.6 * H, H):
                continue
            box.append(f)
        frame_layers = Counter([u.layer for r in rows for u in r.underline] + [b.layer for b in box])
        bid = stable_id("blk", page.info.index, *(ln.rid for ln in g_sorted))
        blocks.append(AnnotationBlock(bid=bid, page=page.info.index, rows=rows, bbox=bbox, angle=r0.angle, height=H,
                                      layer=r0.layer, source=r0.source, box_segs=sorted(box, key=lambda f: (f.pid, f.seg_index)),
                                      frame_layers=frame_layers))
    blocks.sort(key=lambda b: b.bid)
    return blocks


def _span_bbox(bbox, d):
    corners = [(bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[0], bbox[3]), (bbox[2], bbox[3])]
    ps = [project(c, d) for c in corners]
    return min(ps), max(ps)


# ----------------------------------------------------------------------------------------------------------------
# designation extraction
# ----------------------------------------------------------------------------------------------------------------

COUNT_RE = re.compile(r"^(\d{1,2})[xX](.+)$")
# a dimension row may carry a short medium qualifier after the size, bracketed or written off with a
# separator: the size is the dimension, the qualifier belongs to the designation


def _words(line: TextRow) -> list[list[Glyph]]:
    words: list[list[Glyph]] = []
    cur: list[Glyph] = []
    for g in line.glyphs:
        if g.char == " ":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(g)
    if cur:
        words.append(cur)
    return _counts_joined(words)


def _counts_joined(words: list[list[Glyph]]) -> list[list[Glyph]]:
    """A count written apart from its code is the code's count.

    One sheet writes the bundle at a manifold both ways: "4xKV1-X32-16" and "6x VV1-X32-16". Read as two words,
    "6x" is no code and the row became a note, so the six pipes it names went unnamed - and a row that also
    carried "2xVV1-X32-16" beside it was lost with it. The space is spacing, not a second word: the two read as
    one word exactly where, written together, the count would be read as the code's count."""
    out: list[list[Glyph]] = []
    for w in words:
        if out and re.fullmatch(r"\d{1,2}[xX]", "".join(g.char for g in out[-1])) \
                and strip_count_prefix("".join(g.char for g in out[-1] + w))[0] > 1:
            out[-1] = out[-1] + w
        else:
            out.append(w)
    return out


def _clip_stroke_at(page_idx: GridIndex, paths: list[RawPath], glyph: Glyph, line: TextRow, outer: str) -> bool:
    """True when a straight stroke crosses the text line right at the glyph's outer ink edge: the drawing clips
    its own content there (sheet-part boundaries cut labels in half), so this glyph's ink is incomplete."""
    x0, y0, x1, y1 = glyph.bbox
    h = max(line.height, 1.0)
    d, n = row_axes(line.angle)
    corners = ((x0, y0), (x1, y1), (x0, y1), (x1, y0))
    gl = [project(c, d) for c in corners]
    gn = [project(c, n) for c in corners]
    edge = max(gl) if outer == "end" else min(gl)
    for pid in page_idx.query((x0 - 1.5, y0 - 1.5, x1 + 1.5, y1 + 1.5)):
        p = paths[pid]
        for sg in p.segs:
            if sg.length < 1.2 * h:
                continue
            ang = abs(((sg.angle - line.angle) + 90) % 180 - 90)
            if ang < 70.0:
                continue                       # a clipping edge cuts the line squarely; slanted strokes crossing
                                               # a label (hatching, leaders) are drawn over it, not clipping it
            a0, a1 = project((sg.x0, sg.y0), d), project((sg.x1, sg.y1), d)
            b0, b1 = project((sg.x0, sg.y0), n), project((sg.x1, sg.y1), n)
            if min(b0, b1) > min(gn) or max(b0, b1) < max(gn):
                continue                       # does not span the glyph across the line
            if abs((a0 + a1) / 2 - edge) <= 0.35:
                return True                    # the ink runs straight into the line: cut, not merely adjacent
    return False


def _repair_clipped_words(page: RawPage, blocks: list[AnnotationBlock], word_cache: dict, chosen_words: list[str]) -> int:
    """Complete words whose outermost glyph is cut by a clipping edge of the drawing.

    The truncated glyph is read as a wildcard and the drawing's own vocabulary completes it; the repair is made
    only when exactly one distinct code-like word of this drawing matches. No completion is invented."""
    idx = GridIndex(cell=40.0)
    for i, p in enumerate(page.paths):
        if p.kind == "s":
            idx.insert(i, p.bbox)
    vocab = Counter(chosen_words)
    repaired = 0
    for b in blocks:
        for ri, br in enumerate(b.rows):
            gws = _words(br.line)
            parts = br.text_norm.split(" ") if br.text_norm else []
            if len(parts) != len(gws):
                continue
            changed = False
            for wi, gw in enumerate(gws):
                word = parts[wi]
                gl = [g for g in gw if g.char != " "]
                if len(gl) != len(word) or len(gl) < 3:
                    continue
                d, _ = row_axes(br.line.angle)
                starts = sorted(project((x.bbox[0], x.bbox[1]), d) for x in gl)
                steps = sorted(starts[i + 1] - starts[i] for i in range(len(starts) - 1))
                pitch = steps[len(steps) // 2] if steps else 0.0
                if pitch <= 0.5:
                    continue
                for pos, outer in ((len(gl) - 1, "end"), (0, "start")):
                    g = gl[pos]
                    span = max(abs(project((g.bbox[2], g.bbox[1]), d) - project((g.bbox[0], g.bbox[1]), d)),
                               abs(project((g.bbox[2], g.bbox[3]), d) - project((g.bbox[0], g.bbox[1]), d)))
                    if span > 0.75 * pitch:
                        continue               # the character fills its cell: whole ink, not truncated
                    if not _clip_stroke_at(idx, page.paths, g, br.line, outer):
                        continue
                    cands = sorted(((vocab[w], w) for w in vocab if len(w) == len(word) and w != word
                                    and all(w[i] == word[i] for i in range(len(word)) if i != pos)), reverse=True)
                    # the completion must be what this drawing overwhelmingly writes: a one-off reading (often
                    # another copy of the same truncated label) may never rewrite a word
                    if not cands or cands[0][0] < 2 or cands[0][0] < 3 * vocab[word]:
                        continue
                    if len(cands) > 1 and cands[0][0] < 3 * cands[1][0]:
                        continue
                    word = cands[0][1]
                    parts[wi] = word
                    changed = True
                    repaired += 1
                    break
            if changed:
                br.text_norm = " ".join(parts)
                for w in parts:
                    if is_code_like(w):
                        chosen_words.append(w)
    return repaired


COMMA_SIZE = 0.35          # of the row height: the longest a comma's ink runs, where a digit or letter fills it


def _read_commas(glyphs: list[Glyph], row_height: float) -> int:
    """Read the commas of a label that the recogniser left unknown.

    A label that lists the codes of one riser writes them with commas between them: `VVC01-53-16,VV01-53-20,
    KV01-53-20`. A drawn comma is one short tick at the foot of the row, a fifth of its height, and the
    recogniser scored it just past what it calls a glyph, so it came out `?` - and a word with a `?` in it is not
    a code, so the label named nothing and the three pipes under it got no metres. On the same sheet the same
    tick was read as `/` as often as not, and that is the compound the rest of the reading understands.

    Only an unknown glyph is read, only one no larger than a comma, and only one whose own best guesses are a
    comma or a slash. Between a code and the letter that opens the next one it is the slash of a compound label;
    last in the word it is the comma that closes a code in a list, which the row separator strips. Anywhere else
    it stays unknown: a tick between two digits may be a decimal point, and what it is is not this rule's call."""
    marks = [i for i, g in enumerate(glyphs) if g.char == "?"]
    read = 0
    for i in marks:
        g = glyphs[i]
        if max(g.w, g.h) > COMMA_SIZE * max(row_height, 1e-6):
            continue
        if not any(a in ",/" for a, _ in g.alternatives[:3]):
            continue
        before = glyphs[i - 1].char if i > 0 else ""
        after = glyphs[i + 1].char if i + 1 < len(glyphs) else ""
        if not (before.isalnum() or before == "-"):
            continue
        if after.isalpha():
            g.char = "/"
        elif not after:
            g.char = ","
        else:
            continue
        read += 1
    return read


def extract_designations(page: RawPage, blocks: list[AnnotationBlock]) -> tuple[list[Designation], DesignationGrammar, dict]:
    grammar = DesignationGrammar()
    # pass 1: observe all code-like word readings (drawing-local structure)
    word_cache: dict[tuple[str, int, int], list] = {}
    commas = 0
    for b in blocks:
        for ri, br in enumerate(b.rows):
            for wi, w in enumerate(_words(br.line)):
                commas += _read_commas(w, br.line.height)
                rd = word_readings(w)
                word_cache[(b.bid, ri, wi)] = (w, rd)
                if any(is_code_like(r.text) for r in rd):
                    grammar.observe(rd)
    # pass 2: choose readings, assign roles
    chosen_words: list[str] = []
    for b in blocks:
        for ri, br in enumerate(b.rows):
            parts = []
            for wi, _ in enumerate(_words(br.line)):
                w, rd = word_cache[(b.bid, ri, wi)]
                best = grammar.choose(rd)
                parts.append(best.text)
                if is_code_like(best.text):
                    chosen_words.append(best.text)
            br.text_norm = " ".join(parts)
    stats_repair = _repair_clipped_words(page, blocks, word_cache, chosen_words)
    grammar.finalize(chosen_words)
    # role assignment per row, then label units
    for b in blocks:
        for br in b.rows:
            br.role = _row_role(br.text_norm, br, b)
        b.units = _units(b)
    designations: list[Designation] = []
    stats = Counter()
    for b in blocks:
        for ri, br in enumerate(b.rows):
            if br.role != "designation":
                continue
            words = [strip_row_separator(w) for w in br.text_norm.split(" ")]
            glyph_words = _words(br.line)
            multi = len(words) >= 2 and all(is_code_like(strip_count_prefix(w)[1]) for w in words)
            targets = list(zip(words, glyph_words)) if multi else [(_designation_word(br.text_norm) if " " in br.text_norm else words[0], None)]
            for wi, (word, gw) in enumerate(targets):
                if word is None:
                    continue
                mult, word = strip_count_prefix(word)
                toks = split_tokens(word)
                pat = compress_pattern(word)
                fam = grammar.families.get(pat)
                wbbox = bbox_union([g.bbox for g in gw]) if gw else br.line.bbox
                dn, dn_src, dn_row, dn_row_text = _find_dn(word, toks, fam, b, ri, wbbox if multi else None)
                gl = [g for g in (gw if gw else br.line.glyphs) if g.char != " "]
                did = stable_id("des", page.info.index, word, f"{wbbox[0]:.1f}", f"{wbbox[1]:.1f}")
                designations.append(Designation(
                    did=did, page=page.info.index, block_id=b.bid, row_index=ri, text=word,
                    raw_text="".join(g.char for g in gl), pattern=pat, tokens=toks, system_token=toks[0] if toks else "",
                    dn=dn, dn_source=dn_src, dn_row_index=dn_row, dn_row_text=dn_row_text, multiplier=mult, bbox=wbbox,
                    angle=br.line.angle,
                    layer=br.line.layer, source=br.line.source, glyph_scores=[g.score for g in gl], unknown_chars=sum(1 for g in gl if g.char == "?"),
                    evidence={"pattern_count": fam.count if fam else 0, "underlined": bool(br.underline),
                              "block_rows": len(b.rows), "frame_layers": dict(b.frame_layers), "word_index": wi},
                    family=f"grammar:{pat}"))
                stats["designations"] += 1
    designations.sort(key=lambda d: d.did)
    return designations, grammar, {"blocks": len(blocks), "clipped_words_completed": stats_repair,
                                   "commas_read": commas, **stats}


def _designation_word(text: str) -> str | None:
    for w in text.split(" "):
        if is_code_like(w):
            return w
    return None


# a size's qualifier: a separator, then letters that may carry a number - "-F60", "/W", "(L)" - but never a
# second measurement, which is what a cross followed by digits is
_QUALIFIED_SIZE = re.compile(r"[^A-Za-z0-9]?(?![Xx]\d)[A-ZÅÄÖa-zåäö]{1,2}\d{1,3}[)\]]?")


def _row_role(text: str, br: BlockRow, b: AnnotationBlock) -> str:
    t = text.strip()
    if not t:
        return "text"
    words = t.split(" ")
    # pure number row (possibly underlined) -> dn candidate. A row that opens with a nominal size and carries
    # only a short wordless tail after it is a dimension row too, whatever that tail is: the drawing writes the
    # medium or the laying after the size in whatever bracket it likes ("75 (L)", "75/W", "50-F"), and the
    # recogniser does not always read a bracket as a bracket. The size is the content; the tail is a qualifier.
    if len(words) == 1 and re.fullmatch(r"\d{1,4}", words[0]):
        return "dn"
    packed = t.replace(" ", "")
    mq = re.match(r"(\d{1,4})(.*)$", packed)
    if mq and int(mq.group(1)) in NOMINAL_SIZES and (
            (len(mq.group(2)) <= 4 and not any(c.isdigit() for c in mq.group(2)))
            # ...and a qualifier may carry a number of its own. An insulation class is written "22-F60": the
            # size is 22 and F60 names the insulation. The rule that the tail be digit-free read that row as a
            # designation of its own, so the code above it kept no dimension at all - on one sheet the whole
            # DN22 main, eighty metres, took the name of the DN15 branches beside it. What tells a qualifier
            # from a second measurement is that it starts with a letter: "22-F60" is a size with a class,
            # "600X300" is two sizes, and the cross between them is not a qualifier.
            or _QUALIFIED_SIZE.fullmatch(mq.group(2))):
        return "dn"
    # elevation: short letter tag + signed number (VG+1.67, CL 4000, FG +19.82)
    if ELEV_RE.match(t.replace(" ", "")) or (len(words) == 2 and re.fullmatch(r"[A-ZÅÄÖ]{1,4}", words[0]) and re.fullmatch(r"[+\-]?\d+[.,]?\d*", words[1])):
        return "elevation"
    if len(words) == 1 and is_code_like(words[0]) and _has_separator_or_prefix(words[0]):
        return "designation"
    if len(words) >= 2 and is_code_like(words[0]) and _has_separator_or_prefix(words[0]) and all(re.fullmatch(r"[(\[]?[A-ZÅÄÖ]{1,3}[)\]]?|\d{1,4}", w) for w in words[1:]):
        return "designation"
    if len(words) >= 2 and all(is_code_like(strip_count_prefix(w)[1]) and _has_separator_or_prefix(strip_count_prefix(w)[1]) for w in words):
        return "designation"
    if len(words) == 1 and strip_count_prefix(words[0])[0] > 1:
        return "designation"
    return "note"


def _has_separator_or_prefix(w: str) -> bool:
    if any(c in w for c in "-/"):
        return True
    return re.fullmatch(r"[A-ZÅÄÖ]{1,4}\d{1,4}[A-ZÅÄÖ]{0,3}", w) is not None


def _find_dn(word: str, toks: list[str], fam, b: AnnotationBlock, ri: int, word_bbox=None):
    """DN from inline pure-digit token (grammar family position) or from a pure-number row directly below.

    Returns (dn, source, row index of the dimension row, that row's text as drawn)."""
    numeric = [(i, t) for i, t in enumerate(toks) if t.isdigit()]
    # An attached service suffix does not make the printed size disappear.
    for tok in toks[1:]:
        m = re.fullmatch(r"(\d{1,4})[LV]", tok)
        if m and dn_plausible(int(m.group(1))):
            return int(m.group(1)), "inline", None, None
    if fam is not None and fam.dn_token_index is not None:
        i = fam.dn_token_index
        if i < len(toks) and toks[i].isdigit() and dn_plausible(int(toks[i])):
            return int(toks[i]), "inline", None, None
    if fam is not None and fam.count <= 2 and len(numeric) == 1 and numeric[0][0] > 0 and int(numeric[0][1]) in NOMINAL_SIZES:
        # rare pattern (no family statistics): a single nominal-size token after the system token
        return int(numeric[0][1]), "inline", None, None
    if numeric and (fam is None or fam.dn_token_index is None) and any(i > 0 for i, _ in numeric):
        return None, None, None, None
    # DN row directly below (next row(s) in the block with role dn); for multi-word rows the DN row must overlap
    # the word horizontally (each word has its own DN row)
    # Several side-by-side codes may have three or more separate DN rows
    # on the same printed baseline. A two-row list limit lost later columns.
    limit = len(b.rows) if word_bbox is not None else min(ri + 3, len(b.rows))
    own = b.rows[ri].line.bbox
    upright = abs(math.sin(math.radians(getattr(b.rows[ri].line, "angle", 0.0) or 0.0))) < 0.5

    def beside(r):
        # a row printed next to this code's own row, not under it: `S3-R8  5xVV1-X31` over `75  16`
        lo, hi = (0, 2) if upright else (1, 3)
        return min(own[hi], r[hi]) - max(own[lo], r[lo]) <= 0
    for rj in range(ri + 1, limit):
        nxt = b.rows[rj]
        if nxt.role == "designation":
            if word_bbox is None and beside(nxt.line.bbox):
                continue
            break
        if nxt.role != "dn":
            continue
        if word_bbox is None and beside(nxt.line.bbox):
            continue
        if word_bbox is not None:
            origin = b.rows[ri].line.bbox
            if abs((nxt.line.bbox[1]+nxt.line.bbox[3]-origin[1]-origin[3])/2) > 2.4 * b.height:
                continue
            ov = min(word_bbox[2], nxt.line.bbox[2]) - max(word_bbox[0], nxt.line.bbox[0])
            if ov <= 0:
                continue
        mv = re.match(r"\d{1,4}", nxt.text_norm.strip())
        v = int(mv.group(0)) if mv else -1
        if dn_plausible(v):
            return v, "row", rj, nxt.text_norm.strip()
    return None, None, None, None


def _units(b: AnnotationBlock) -> list[list[int]]:
    """Split a block into label units: a new unit starts at each designation row unless that row shares the
    frame extent (underline span along the reading axis) with the previous row (stacked box style)."""
    d, n = row_axes(b.angle)
    H = max(b.height, 1.0)

    def ul_extent(br: BlockRow):
        if not br.underline:
            return None
        xs = []
        for u in br.underline:
            xs += [project((u.seg.x0, u.seg.y0), d), project((u.seg.x1, u.seg.y1), d)]
        return (round(min(xs) / (0.5 * H)), round(max(xs) / (0.5 * H)))

    units: list[list[int]] = []
    prev_role = None
    prev_ext = None
    for ri, br in enumerate(b.rows):
        ext = ul_extent(br)
        if br.role == "designation" and units:
            # stacked-box style: consecutive designation rows sharing the same underline extent
            shared = prev_role == "designation" and ext is not None and prev_ext is not None and ext == prev_ext
            if shared:
                units[-1].append(ri)
            else:
                units.append([ri])
        elif units:
            units[-1].append(ri)
        else:
            units.append([ri])
        prev_role = br.role
        prev_ext = ext
    return units
