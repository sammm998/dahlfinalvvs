"""The drawing's own designation list.

Every one of these drawings carries a legend - a column of short codes, each with the words that say what it
is, under headings that group them. It is the drawing telling us its own vocabulary: which codes are systems,
which are pipe materials, which are components that will never be a pipe. Read from the page like everything
else, per job, and never carried between drawings.

Per job, not per sheet. A set writes its designation list once, on the sheet that has room for it, and the plan
sheets are governed by it without repeating it. A reading that looks for the list on each sheet alone finds it
on one of them and, on all the others, concludes the drawing has no vocabulary at all - so every label passes as
possibly a pipe, the review list fills with door marks and room numbers, and the same project is read one way on
one sheet and another way on the next. A sheet that carries no list of its own is handed the set's, marked as
having come from elsewhere; what it may never do is silently borrow the other sheet's geometry with it.

Nothing here knows any Swedish. A legend is found by its shape - a stack of rows sharing a left edge, each a
short code beside a description - and a code's role is settled by how the drawing itself uses it: a code that
opens a dimensioned designation is a system, a code that stands alone as a whole label is a component.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from ..text.model import TextRow
from .grammar import split_tokens
from .. import disciplines as _disciplines

from .. import rules as _rules


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


MIN_ENTRIES = 6                 # a shorter stack is a table cell or a note, not a designation list
MIN_CODES = 6                   # ...and it must say six different things, or it is one table column repeated
USED_MIN = 2                    # codes the drawing writes out itself, for the list to be its own vocabulary
LIST_MARGIN = 4.0               # how far outside its rows the list's own block still reaches, in points
ALIGNED_SHARE = 0.6             # ...or the share of descriptions that share a left edge, which a note's do not
MAX_CODE_LEN = 10
DESC_GAP_ROWS = 12.0            # how far right of the code its description may start, in row heights
LIST_BREAK_ROWS = 10.0         # a gap of more than this many of the list's own entry pitches ends the list
COL_TOL = 3.0                   # how far two rows' left edges may differ and still be one column

_INLINE = re.compile(r"^([^\s]{1,%d})\s+(\S.{2,})$" % _R("semantics.legend.MAX_CODE_LEN", MAX_CODE_LEN))


def is_code_token(tok: str) -> bool:
    """A legend code, as opposed to a heading word.

    Codes carry a digit ('KV01', 'S13'), or a placeholder run ('ALxxx'), or are very short ('W', 'P2'). A word of
    five letters or more with no digit in it is a heading - the drawing's own section title."""
    t = tok.strip().rstrip(".:,;")
    if not t or not t[0].isalnum():
        return False
    if any(c.isdigit() for c in t):
        return True
    up = t.upper()
    if up.count("X") >= 2 and len(up) <= 6:
        return True
    return len(t) <= 4


def code_matches(label: str, code: str) -> bool:
    """Whether a drawn label is this legend code.

    A legend writes the varying part of a component tag as a run of placeholder letters ("ALxxx", "Bxxx"), so
    those positions stand for the number the drawing actually writes - and, on a real sheet, for the letters an
    office hangs off it. `Bxxx GOLVBRUNN` is written B1 and B10, but also B12ML, B12KL and B21M, and reading the
    placeholder as digits alone left every one of those unrecognised: the drawing named a floor drain and the
    reading had it down as something that might be a pipe.

    The letters are a suffix, never a prefix and never the whole varying part: everything outside the placeholder
    run must still agree character for character, so this widens what a tag matches without letting it reach a
    designation. `S3-R8-110` cannot match `Bxxx` however the placeholder is read."""
    L, C = label.upper(), code.upper()
    if L == C:
        return True
    if "X" not in C[1:] or len(L) < 2:
        return False
    pat = re.sub(r"(?<!\\)X{2,}", r"\\d+[A-ZÅÄÖ]{0,3}", re.escape(C))
    return re.fullmatch(pat, L) is not None


# Where a stroke-drawn letter and digit share a shape, the reader may give either: O and 0, S and 5, I and 1.
_TWIN_FOLD = str.maketrans({"O": "0", "I": "1", "S": "5", "B": "8", "Z": "2", "G": "6"})
_PLACEHOLDER_CODE = re.compile(r"^([A-ZÅÄÖ]+)X{2,}(.*)$")


@lru_cache(maxsize=4096)
def _placeholder_pattern(code: str):
    """A list's code with a placeholder for the system number, as a pattern for the labels it stands for.

    A list writes a system family once, the number the drawing gives each system written as XX - `KVXX-3
    KALLVATTENLEDNING KOPPAR`, `VSXX-22 VÄRMEBÄRARE SEKUNDÄR STÅLRÖR` - and says so in a line of its own: "XX AVSER
    SYSTEMBETECKNING". So `KV02-3-15` is that code: KV, a system number, then the -3 that follows the placeholder.
    Read letter for letter, no label ever opened with KVXX-3, every code of such a list was taken for a material,
    and a whole set of sheets named no pipe at all. The code and the label are compared as the strokes allow: a
    sheet whose lettering is drawn reads its 0 as O, and its S as 5, as often as not."""
    m = _PLACEHOLDER_CODE.match(code.upper())
    if not m:
        return None
    stem, rest = m.group(1).translate(_TWIN_FOLD), m.group(2).translate(_TWIN_FOLD)
    return re.compile(r"^%s\d{1,3}%s(?=$|[-/+.,:(\[ ])" % (re.escape(stem), re.escape(rest)))


_CODE_END = "-/+.,:([ "


def opens_as_twin(label: str, code: str) -> bool:
    """Whether a label opens with this literal code of the list once letters and the digits they resemble are
    folded together - and the code ends where a code ends.

    The list writes `SS4 SPILLVATTENLEDNING PP-RÖR`; drawn in strokes, the labels on the sheet read `S54-75`
    as often as not, S and 5 being one shape. Compared letter for letter no label opened with SS4, all fourteen
    on one sheet were taken for something other than a pipe, and the waste pipes they name got no metres. The
    folded head has to stop at a separator, so a twin can never stretch a short code over a longer word: `S3`
    does not open `S35` just because both fold to digits. Placeholder codes are compared folded already
    (_placeholder_pattern), and single-character codes are left to the letter-for-letter comparison."""
    L, C = (label or "").upper().strip(), (code or "").upper()
    if len(C) < 2 or len(L) < len(C) or _placeholder_pattern(C) is not None:
        return False
    if L[:len(C)].translate(_TWIN_FOLD) != C.translate(_TWIN_FOLD):
        return False
    return len(L) == len(C) or L[len(C)] in _CODE_END


def opens_with(label: str, code: str) -> bool:
    """Whether a label opens with this code of the list: letter for letter, through the list's placeholder, or
    letter for letter once twins are folded (opens_as_twin)."""
    L, C = (label or "").upper().strip(), (code or "").upper()
    if not L or not C:
        return False
    if L == C or L.startswith(C):
        return True
    pat = _placeholder_pattern(C)
    if pat is not None:
        return pat.match(L.translate(_TWIN_FOLD)) is not None
    return opens_as_twin(L, C)


def number_as_listed(label: str, codes) -> str:
    """The label with the system number a list's placeholder stands for written in digits.

    Read from strokes the number reads as letters as often as not: `KVO1-53-/VVOZ-3-16`. Compared through the twin
    folding it is found as it should be, but the name it was given carried the letters, so one system came out
    as two rows under names the drawing never wrote. Where a list code says that a number stands in this place
    (KVXX-53), there is nothing but a number there to read: the letters in it are the digits they resemble. Only
    that place is rewritten, and only in a part that opens with such a code; everything else stands as read."""
    parts = (label or "").split("/")
    out = []
    for part in parts:
        P = part.upper()
        done = part
        for c in codes:
            m = _PLACEHOLDER_CODE.match((c or "").upper())
            if not m and opens_as_twin(P, c) and not P.startswith((c or "").upper()):
                # a literal code read through its twins: written the way the list writes it (S54-75 -> SS4-75)
                done = (c or "").upper() + part[len(c):]
                break
            if not m or not opens_with(P, c):
                continue
            stem = m.group(1)
            n = re.match(r"([A-ZÅÄÖ0-9]{%d})([0-9OISBZG]{1,3})(?=[^0-9OISBZG]|$)" % len(stem), P)
            if n and n.group(1).translate(_TWIN_FOLD) == stem.translate(_TWIN_FOLD):
                done = n.group(1) + n.group(2).translate(_TWIN_FOLD) + part[n.end():]
                break
        out.append(done)
    return "/".join(out)


@dataclass
class LegendEntry:
    code: str
    description: str
    heading: str
    bbox: tuple[float, float, float, float]
    role: str = "unused"        # system | component | material | unused
    role_from: str = "usage"    # usage | heading | other_sheet - what settled the role
    page: int | None = None     # the sheet of the set that wrote this line

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "description": self.description, "heading": self.heading,
                "role": self.role, "role_from": self.role_from, "page": self.page,
                "bbox": [round(v, 1) for v in self.bbox]}


@dataclass
class DrawingLegend:
    entries: list[LegendEntry] = field(default_factory=list)
    column_x: float | None = None
    own: bool = True            # False when the list was written on another sheet of the same set
    usage_systems: dict[str, list[str]] = field(default_factory=dict)  # label IDs, local to this sheet

    @property
    def by_code(self) -> dict[str, LegendEntry]:
        return {e.code.upper(): e for e in self.entries}

    def systems(self) -> set[str]:
        return {e.code.upper() for e in self.entries if e.role == "system"} | set(self.usage_systems)

    def code_for(self, head: str) -> str | None:
        """Vilken av listans koder en etikett faktiskt öppnar med.

        Den längsta som passar, och det är hela poängen. En lista som har både `T` för tilluft och `TD102` för
        ett tilluftsdon läser `TD102-100` som ett don och inte som hundra millimeter tilluft - men bara om den
        längre koden får gå före den kortare. Prövat kortaste först blev varje don ett system, och en ritnings
        alla trettio don blev trettio rörsystem utan meter.
        """
        h = (head or "").upper().strip()
        if not h:
            return None
        best = None
        for e in self.entries:
            c = e.code.upper()
            if not c:
                continue
            if h == c or (h.startswith(c) and len(h) > len(c)) \
                    or (_placeholder_pattern(c) is not None and opens_with(h, c)) or opens_as_twin(h, c):
                if best is None or len(c) > len(best):
                    best = c
        return best

    def role_of_head(self, head: str) -> str | None:
        """Vad listan säger om koden en etikett öppnar med."""
        c = self.code_for(head)
        if c is None:
            tokens = split_tokens((head or '').upper())
            return 'system' if tokens and tokens[0] in self.usage_systems else None
        # A list may write one code in two of its sections - `S1` a waste system under SYSTEM and an insulation
        # class under ISOLERINGTYP. A label opening with it is the system: the section that makes it a run speaks
        # for the head of a label, the one that makes it a covering for what follows the slash.
        roles = [e.role for e in self.entries if e.code.upper() == c]
        for role in ("system", "component"):
            if role in roles:
                return role
        return roles[0] if roles else None

    def names_a_pipe(self, designation) -> bool:
        """Whether the sheet's own designation list says this label names a pipe.

        True when the label opens with a code the legend lists as a system. When the legend named no systems at
        all - it was not found, or the sheet does not carry one - nothing is claimed and every label passes.

        A list read off another sheet of the set carries less authority than the sheet's own, and it is worth
        being exact about how much less. It is a vocabulary, not a census: it says what the codes in it are, and
        the sheet that wrote it may simply never have covered what this sheet draws. So a borrowed list may
        refuse a code it lists as something other than a run, and may not refuse a code it has never heard of -
        which is what it would be doing if silence counted as a verdict. That keeps the borrowing one-directional:
        it can take away a label the set itself calls a floor drain, and it can never take away a pipe."""
        systems = self.systems()
        if not systems:
            return True
        head = (getattr(designation, "system_token", "") or "").upper()
        text = (getattr(designation, "text", "") or "").upper() or head
        # Vilken kod etiketten öppnar med avgörs av den längsta som passar, inte av den första. Prövat på
        # etikettens hela text först: den bär hela koden även när system_token bara bär dess början.
        role = self.role_of_head(text) or self.role_of_head(head)
        if role == "component":
            return False
        if role == "system":
            return True
        if self.names_a_component(text):
            return False
        if any(opens_with(text, c) or opens_with(head, c) for c in systems):
            return True
        return not self.own and not any(opens_with(text, c) or opens_with(head, c) for c in self.by_code)

    def components(self) -> set[str]:
        return {e.code.upper() for e in self.entries if e.role == "component"}

    def names_a_component(self, text: str) -> bool:
        """Whether the sheet's own list says this label is a fitting rather than a run.

        A designation list does not write out every floor drain it has; it writes the family once, with the
        drawing's own placeholder for the number that varies: `BXXX GOLVBRUNN`, `TSXXX TVATTSTALL`,
        `RLX RENSROR MED LOCK`. So `B1`, `B10` and `B221BL` are that entry, and comparing the text letter for
        letter never finds them. A trailing run of X after at least one other character is that placeholder;
        `X31`, whose X leads, is not. A label that also opens with a system code stays a pipe."""
        head = (text or "").upper().strip()
        if not head:
            return False
        role = self.role_of_head(head)
        if role is not None:
            return role == "component"
        for code in self.components():
            stem = code.rstrip("X")
            if not stem or stem == code:                     # no trailing placeholder: an exact code
                if head == code:
                    return True
                continue
            rest = head[len(stem):]
            if head.startswith(stem) and rest[:1].isdigit():
                return True
        return False

    def bbox(self) -> tuple[float, float, float, float] | None:
        """The block the legend occupies, so its own rows can be told from labels out on the drawing.

        A list read from another sheet occupies nothing here. Its coordinates describe a block on that sheet, and
        on this one they are a rectangle in an arbitrary place - one that would quietly disqualify whatever real
        labels happen to fall inside it. A borrowed vocabulary brings no geometry with it."""
        if not self.entries or not self.own:
            return None
        xs = [v for e in self.entries for v in (e.bbox[0], e.bbox[2])]
        ys = [v for e in self.entries for v in (e.bbox[1], e.bbox[3])]
        return (min(xs), min(ys), max(xs), max(ys))

    def holds(self, bbox) -> bool:
        """Whether a label stands inside the list's own block rather than out on the drawing.

        The list's rows are read as designations like any other text, so every code in the list appears twice in
        the reading: once as a line of the list, once - if the drawing uses it - as a label out on the plan. The
        two say entirely different things. A line of the list only repeats what the list already says; a label
        out on the drawing is the sheet using the code. Wherever the question is what the list knows about this
        sheet, the list's own rows must not be allowed to answer it, or the list vouches for itself."""
        box = self.bbox()
        if box is None or bbox is None:
            return False
        return (box[0] - LIST_MARGIN <= bbox[0] and bbox[2] <= box[2] + LIST_MARGIN
                and box[1] - LIST_MARGIN <= bbox[1] and bbox[3] <= box[3] + LIST_MARGIN)

    def as_dict(self) -> dict[str, Any]:
        return {"column_x": round(self.column_x, 1) if self.column_x is not None else None,
                "own": self.own, "n_entries": len(self.entries),
                "usage_systems": self.usage_systems,
                "entries": [e.as_dict() for e in self.entries]}


def densest_edge(xs: list[float], tol: float | None = None) -> float | None:
    """The left edge that carries the most rows: the start of the narrow window holding the most of them.

    A designation list is found by the edge its codes share, and rows on a real sheet do not share one exactly -
    a column can jitter a point either way. Rounding each left edge onto a fixed grid decides that by where the
    boundaries happen to fall: two rows of one column at x=100.4 and x=101.6 land in different cells, and a list
    of eight entries becomes two of four, each too short to be a list at all. Nothing about the drawing changed;
    only where the grid was drawn. Grouping by the distance between edges instead has no boundaries to fall on.

    Ties go to the leftmost edge, as the widest thing a column can be is what stands furthest left.
    """
    if tol is None:
        tol = _R("semantics.legend.COL_TOL", COL_TOL)
    xs = sorted(xs)
    best_n, best_x, j = 0, None, 0
    for i, x in enumerate(xs):
        while j < len(xs) and xs[j] <= x + tol:
            j += 1
        if j - i > best_n:
            best_n, best_x = j - i, x
    return best_x


def _description_x(line: TextRow, at: int) -> float:
    """Where the words beside the code start, in page coordinates.

    For a row written as one piece of text the description begins at a character index, and the glyph boxes say
    where that character sits. It matters because whether the descriptions line up is one of the two things that
    tell a designation list from a note."""
    lead = len(line.text) - len(line.text.lstrip())
    i = lead + at
    if 0 <= i < len(line.glyphs):
        return line.glyphs[i].bbox[0]
    return line.bbox[2]


def _quality(line: TextRow) -> tuple:
    """How well a row was read, for choosing between two readings of the same row.

    Searchable text is what the file says; reconstructed glyphs are what the shapes look like. Where both exist
    the file wins, and after that the reading with fewer characters it could not name, and then the one whose
    glyphs it was surest of.
    """
    gl = getattr(line, "glyphs", ()) or ()
    scores = [getattr(g, "score", 1.0) for g in gl]
    return (1 if getattr(line, "source", "") == "text" else 0,
            -int(getattr(line, "unknown_chars", 0) or 0),
            sum(scores) / len(scores) if scores else 0.0,
            len(line.text or ""))


def _one_per_line(column: list[TextRow]) -> list[TextRow]:
    """One reading per line of the list.

    A sheet can carry its designation list twice over: once as text in the file and once as the strokes that
    draw it, laid on top of each other so a reader sees one list. The reading saw two, and the second was the
    worse one - `RL1O1` beside `RL101`, `LD1OZ` beside `LD102`, `1OOmm` beside `100mm`. Sixty rows where the
    sheet has thirty, half of them codes that do not exist, each becoming a name the takeoff then reports as a
    pipe it never found.

    Rows that occupy the same line of the same column are therefore one row, and the better reading of it is
    kept. Overlap is measured against the shorter of the two so that a tall row and a short one on the same
    baseline still count as one.
    """
    kept: list[TextRow] = []
    for line in column:
        y0, y1 = line.bbox[1], line.bbox[3]
        h = max(y1 - y0, 0.01)
        for i, other in enumerate(kept):
            o0, o1 = other.bbox[1], other.bbox[3]
            over = min(y1, o1) - max(y0, o0)
            if over > 0.5 * min(h, max(o1 - o0, 0.01)):
                if _quality(line) > _quality(other):
                    kept[i] = line
                break
        else:
            kept.append(line)
    return kept


def _one_block(entries: list[LegendEntry]) -> list[LegendEntry]:
    """The list's own block of entries: the largest run whose entries follow each other within LIST_BREAK_ROWS of
    their own pitch.

    A designation list is set as one block, its sections a few lines apart. The same left edge often runs on
    below it into the title block - the consultants' list, `V VVS-KONSULT AB`, `E ELKONSULT AB` - and read as
    more of the list, a consultant's initial became a system code: `V`, opening the sheet's own number
    `V50-02-421`, named it a pipe the length of the title block. The title block's other text stands on the same
    edge, so the gap is measured between entries, not between rows."""
    if len(entries) < 3:
        return entries
    ys = [e.bbox[1] for e in entries]
    gaps = sorted(b - a for a, b in zip(ys, ys[1:]) if b - a > 0.5)
    if not gaps:
        return entries
    pitch = gaps[len(gaps) // 2]
    blocks, cur = [], [entries[0]]
    for a, b in zip(entries, entries[1:]):
        if b.bbox[1] - a.bbox[1] > _R("semantics.legend.LIST_BREAK_ROWS", LIST_BREAK_ROWS) * pitch:
            blocks.append(cur)
            cur = []
        cur.append(b)
    blocks.append(cur)
    return max(blocks, key=len)


def _candidate(rows: list[TextRow], found: dict, edge: float) -> list[LegendEntry]:
    """The list that would be read off one left edge: its entries, under the headings standing above them - the
    list's own block of them, not what the edge runs on into."""
    column = sorted((l for l in rows if edge - 0.1 <= l.bbox[0] <= edge + _R("semantics.legend.COL_TOL", COL_TOL)),
                    key=lambda l: (l.bbox[1], l.bbox[0]))
    column = _one_per_line(column)
    entries: list[LegendEntry] = []
    heading = ""
    for line in column:
        f = found.get(line.rid)
        if f is None or not is_code_token(f[0]):
            heading = line.text.strip()
            continue
        entries.append(LegendEntry(code=f[0].strip().rstrip(".:,;"), description=f[1].strip(), heading=heading,
                                   bbox=tuple(line.bbox), page=getattr(line, "page", None)))
    return _one_block(entries)


def read_legend(lines: list[TextRow], designations=()) -> DrawingLegend:
    """Find the sheet's designation list and read it.

    A legend row is a short code with a description: either both in one text row, or the code in one row and the
    description in another on the same baseline a little to the right. Rows on one left edge that read that way
    are a candidate list, and rows on that edge whose leading word is not a code are the headings above them.

    Being a stack of short words with sentences beside them is not enough to be a designation list, and taking it
    to be enough is how a note block becomes the drawing's vocabulary. `FALL 1:100 MOT GOLVBRUNN`, `MED
    ISOLERING`, `OBS! SAMORDNAS MED EL` is six rows on one edge, each a short leading token with words after it,
    and the reading filed it as the sheet saying what its codes mean. A parts table repeating the word POS sixty
    times is the same mistake with a straighter face.

    Two things separate the real list from those, and either will do:

      * the drawing uses the codes. A designation list is a vocabulary for what is drawn on the paper, so its
        codes turn up out on the drawing at the head of the labels. A note's leading words turn up nowhere else.
      * the descriptions line up. A list is set as a table - the codes in one column, the words in another - so
        the descriptions share a left edge of their own. A note's words start wherever its leading word ended.

    The first is the stronger evidence and decides between candidates; the second is what lets an index sheet,
    which carries the list for a set without drawing any of it, still be read. A stack that shows neither is a
    stack of text, and the sheet is left with no list rather than a made-up one - which costs nothing, because
    a legend that was never found claims nothing.
    """
    rows = [l for l in lines if abs(l.angle) <= 5.0 and l.text.strip()]
    if not rows:
        return DrawingLegend()
    by_band: dict[int, list[TextRow]] = defaultdict(list)
    for l in rows:
        by_band[round(l.bbox[1] / 2.0)].append(l)
    found: dict[str, tuple[str, str, float]] = {}
    for l in rows:
        t = l.text.strip()
        h = max(l.bbox[3] - l.bbox[1], 1.0)
        m = _INLINE.match(t)
        if m and any(c.isalpha() for c in m.group(2)):
            found[l.rid] = (m.group(1), m.group(2), _description_x(l, m.start(2)))
            continue
        if len(t) > _R("semantics.legend.MAX_CODE_LEN", MAX_CODE_LEN) or " " in t:
            continue
        best = None
        band = round(l.bbox[1] / 2.0)
        # The bands are an index, not the rule: what decides is the test below, that the description sits on the
        # code's own line within six tenths of its height. Two-point bands reached one band either way, which is
        # narrower than that test - and a description drawn a couple of points higher than its code, as a row
        # with a tall fragment in it is, fell outside the index and was never offered. Its code then read as a
        # heading, the code itself vanished from the sheet's vocabulary, and every label of that system was
        # unknown to the legend: on four drainage plans that was every pipe on the sheet, and they measured
        # nothing at all. The index now reaches as far as the test does.
        reach = int(0.6 * h / 2.0) + 2
        for k in range(band - reach, band + reach + 1):
            for o in by_band.get(k, []):
                if o is l or o.bbox[0] <= l.bbox[2] - 0.1 or abs(o.bbox[1] - l.bbox[1]) > 0.6 * h:
                    continue
                gap = o.bbox[0] - l.bbox[2]
                if 0.0 <= gap <= _R("semantics.legend.DESC_GAP_ROWS", DESC_GAP_ROWS) * h and (best is None or gap < best[0]):
                    best = (gap, o)
        if best is not None and any(c.isalpha() for c in best[1].text):
            found[l.rid] = (t, best[1].text.strip(), best[1].bbox[0])
    if not found:
        return DrawingLegend()
    heads = {(getattr(d, "system_token", "") or "").upper() for d in designations}
    heads |= {(getattr(d, "text", "") or "").upper().strip() for d in designations}
    heads.discard("")
    by_rid = {l.rid: l for l in rows}
    best_list: tuple[tuple, list[LegendEntry], float] | None = None
    for edge in sorted({by_rid[rid].bbox[0] for rid in found}):
        entries = _candidate(rows, found, edge)
        if len(entries) < _R("semantics.legend.MIN_ENTRIES", MIN_ENTRIES):
            continue
        codes = {e.code.upper() for e in entries}
        if len(codes) < _R("semantics.legend.MIN_CODES", MIN_CODES):
            continue                    # a column that repeats one word is a table, not a vocabulary
        used = sum(1 for c in codes if any(opens_with(h, c) for h in heads))
        dxs = [found[rid][2] for rid in (l.rid for l in rows)
               if rid in found and edge - 0.1 <= by_rid[rid].bbox[0] <= edge + _R("semantics.legend.COL_TOL", COL_TOL)]
        dedge = densest_edge(dxs)
        lined = sum(1 for x in dxs if dedge is not None and dedge - 0.1 <= x <= dedge + _R("semantics.legend.COL_TOL", COL_TOL))
        if used < _R("semantics.legend.USED_MIN", USED_MIN) and lined < _R("semantics.legend.ALIGNED_SHARE", ALIGNED_SHARE) * len(dxs):
            continue
        score = (used, lined, len(entries))
        if best_list is None or score > best_list[0]:
            best_list = (score, entries, edge)
    if best_list is None:
        return DrawingLegend()
    return DrawingLegend(entries=best_list[1], column_x=best_list[2])


def adopt(legend: DrawingLegend) -> DrawingLegend:
    """The same designation list, as it stands for a sheet that does not carry it.

    What travels between the sheets of one set is the vocabulary and nothing else: the codes, the words beside
    them, the headings that group them, and the roles the sheet that carried the list settled from its own use.
    What does not travel is where any of it sat on paper. Roles arrive as a starting point, not a verdict - this
    sheet's own use of a code still outranks what another sheet made of it."""
    return DrawingLegend(own=False, column_x=None,
                         entries=[LegendEntry(code=e.code, description=e.description, heading=e.heading,
                                              bbox=(0.0, 0.0, 0.0, 0.0), role=e.role, role_from=e.role_from,
                                              page=e.page)
                                  for e in legend.entries])


def merged(a: DrawingLegend | None, b: DrawingLegend) -> DrawingLegend:
    """The set's vocabulary after reading one more of its sheets.

    Sets do not always write the whole list in one place: a big project puts the water systems on one sheet and
    the heating systems on another, and either sheet alone is a partial vocabulary. Codes accumulate, and the
    first sheet to write a code keeps it - a later sheet repeating the same list says nothing new, and a later
    sheet that disagrees about a code is not evidence enough to overwrite the sheet that introduced it. The
    result is nobody's own list, so it never lends its geometry to anything."""
    if a is None or not a.entries:
        return DrawingLegend(own=False, entries=list(b.entries))
    have = {e.code.upper() for e in a.entries}
    return DrawingLegend(own=False, entries=list(a.entries) + [e for e in b.entries if e.code.upper() not in have])


def roles_of(legend: DrawingLegend) -> dict[str, str]:
    """What each code was settled as, in the form another sheet of the set can be given it."""
    return {e.code.upper(): e.role for e in legend.entries if e.role in ("system", "component")}


# what a role is worth against another claim on the same code: a sheet that showed a code opening a dimensioned
# label has said more than a sheet on which the code never appeared
_ROLE_RANK = {"unused": 0, "material": 1, "component": 2, "system": 2}


def learn_roles(vocab: DrawingLegend | None, sheet: DrawingLegend) -> None:
    """Carry back into the set's vocabulary what a sheet settled about its codes by using them.

    The vocabulary is read before any sheet is, so its rows start out saying only that the codes exist - a list
    of words with no verdict on any of them. What a code IS - a pipe system, a fitting, a material - is something
    a sheet shows by using it, and a set is read one sheet at a time. Without this the list travels between the
    sheets as bare words: every row stays 'unused', the next sheet is handed nothing to stand on, and the list
    that is written down at the end says the reading made nothing of any of its sixty-four rows.

    Only what a sheet showed travels. Its own written descriptions are evidence
    too; borrowed descriptions and inherited roles are not new evidence.
    """
    if vocab is None or not vocab.entries:
        return
    by_code = vocab.by_code
    for e in sheet.entries:
        local_words = sheet.own and e.role_from in LIST_SAYS
        if e.role_from not in ("usage", "the_sheet_writes_it_as_a_pipe") and not local_words:
            continue
        v = by_code.get(e.code.upper())
        if v is None or _ROLE_RANK[e.role] <= _ROLE_RANK.get(v.role, 0):
            continue
        v.role, v.role_from = e.role, e.role_from


# ---------------------------------------------------------------------------------------------------------
# Vad listan själv säger att en kod är
#
# Resten av modulen kan ingen svenska, och ska inte kunna det: en lista hittas på sin form och läses på hur
# ritningen använder den. Men listan skriver också ut vad varje kod betyder, med ingenjörens egna ord, och att
# inte läsa dem är att kasta bort det starkaste beviset som finns på bladet.
#
# Svenskan gör det ovanligt lätt. Ett svenskt sammansatt ord bär sitt huvudord sist: en TILLUFTSDON är ett DON,
# ett BRANDGASSPJÄLL är ett SPJÄLL, en CIRKULATIONSFLÄKT är en FLÄKT. Så det räcker att se efter vad ordet
# slutar på för att veta vad saken är. Det är därför listorna nedan är ändelser och inte ord.
#
# Skillnaden som betyder något för en mängd: en KANAL och en LEDNING mäts i meter, ett DON och ett SPJÄLL i
# stycken. En kod som listan kallar ett don är aldrig rör, hur ritningen än skriver den - och just det var vad
# som gick fel: TD102 skrivs TD102-100 med anslutningsmåttet, läsningen såg en dimension och tog donet för ett
# system, och femtio meter kanal hamnade under ett tilluftsdon.
# ---------------------------------------------------------------------------------------------------------

# Saker som köps i stycken. Sista ledet i ordet säger vad det är, så listan är ändelser: ett BRANDGASSPJÄLL
# slutar på SPJÄLL, ett TILLUFTSDON på DON, en CIRKULATIONSFLÄKT på FLÄKT, ett VATTENLÅS på LÅS.
COMPONENT_HEADS = (
    "DON", "SPJÄLL", "SPJALL", "DÄMPARE", "DAMPARE", "FLÄKT", "FLAKT", "AGGREGAT", "LUCKA", "GALLER",
    "HUV", "KÅPA", "KAPA", "VENTIL", "RENARE", "FILTER", "BATTERI", "PUMP", "RADIATOR", "BRUNN",
    "LÅS", "BLANDARE", "MÄTARE", "MATARE", "GIVARE", "ENHET", "GENOMFÖRING", "GENOMFORING",
    "KASSETT", "AVSKILJARE", "VÄXLARE", "VAXLARE", "BEREDARE", "TANK", "CISTERN", "ARMATUR", "STOS",
    "TERMOMETER", "MANOMETER", "REGULATOR", "TVÄTTSTÄLL", "TVATTSTALL", "HANDFAT", "URINOAR", "BADKAR",
    "DUSCH", "TORKSKÅP", "DISKMASKIN", "TVÄTTMASKIN", "ELPATRON", "EXPANSIONSKÄRL", "KÄRL",
)
# ...och det som bara beskriver vad något är gjort av eller klätt med
MATERIAL_HEADS = ("PLÅT", "PLAT", "ISOLERING", "FOLIE", "MATTA", "SKIVA")
# ett medium som flödar, och som listan förklarar för sig självt
SYSTEM_WORDS = ("TILLUFT", "FRÅNLUFT", "FRANLUFT", "UTELUFT", "AVLUFT", "ÖVERLUFT", "OVERLUFT",
                "CIRKULATIONSLUFT", "KALLVATTEN", "VARMVATTEN", "SPILLVATTEN", "DAGVATTEN", "DRÄNVATTEN",
                "FJÄRRVÄRME", "FJARRVARME", "TAPPVATTEN", "VARMVATTENCIRKULATION")


def _is_fire_class(w: str) -> bool:
    """EI15, EI30, EI60, E60: en brandklass beskriver en klädsel, aldrig ett medium."""
    return len(w) >= 3 and w[0] == "E" and (w[1] == "I" or w[1].isdigit()) and w[-1].isdigit()


def _ends_with(word: str, tail: str, unread: int = 2) -> bool:
    """Whether the word ends with tail, an unread character ('?') standing for any letter - at most `unread` of
    them, and never more than leave four letters that do agree."""
    if len(word) < len(tail):
        return False
    end = word[-len(tail):]
    if any(a != b and a != "?" for a, b in zip(end, tail)):
        return False
    return end.count("?") <= unread and len(tail) - end.count("?") >= 4


def _words(text: str, keep_unread: bool = False) -> list[str]:
    out, cur = [], []
    for ch in (text or "").upper():
        if ch.isalpha() or ch.isdigit() or (keep_unread and ch == "?"):
            cur.append(ch)
        elif cur:
            out.append("".join(cur)); cur = []
    if cur:
        out.append("".join(cur))
    return out


def role_from_heading(heading: str) -> str | None:
    """What the list's own section title says its codes are, or None when it says nothing about that.

    A designation list groups its codes under titles, and the titles name the kind: SYSTEM over the media,
    MATERIAL over the pipe materials, ISOLERINGTYP over the insulation classes. That is the list answering the
    question in its own words, as plainly as a description does - more plainly where the description names a
    medium only because the class is for it: `S2 KALLVATTEN` under ISOLERINGTYP is the insulation for cold water,
    not a cold water system. Only the title's own word is read; a title that names neither kind decides nothing."""
    for w in _words(heading):
        if w.startswith("SYSTEM"):
            return "system"
        if w.startswith("MATERIAL") or w.startswith("ISOLER") or any(w.startswith(h) for h in MATERIAL_HEADS):
            return "material"
    return None


# where a role was taken from what the list writes, rather than from how the drawing uses the code
LIST_SAYS = ("the_list_says_so", "the_list_heading_says_so")


def role_from_words(description: str) -> str | None:
    """Vad listan säger att koden är, eller None om den inte säger något om saken.

    Sista ledet vinner, och en sak vinner över ett medium: `= TILLUFSDON, VENTIL` är ett don och inte tilluft,
    fast ordet börjar på tilluft. Ett medium räknas bara när listan skriver ut mediets eget namn.

    Vad den med flit inte gör: säger att något är ett rör. `RENSRÖR MED LOCK` slutar på RÖR och mäts ändå i
    stycken, `STUPRÖR` slutar likadant och mäts i meter, och ordet skiljer dem inte åt. Där orden inte räcker
    får ritningens egen användning avgöra, som förut. Det som står här är bara det som orden avgör säkert - och
    ett don, ett spjäll eller en brunn är aldrig meter, hur ritningen än skriver dem.
    """
    ws = _words(description)
    if not ws:
        return None
    for w in ws:
        if any(w.endswith(h) for h in _disciplines.value("legend.COMPONENT_HEADS", COMPONENT_HEADS)):
            return "component"
    # samma sammansättningsregel som för sakerna: TAPPKALLVATTEN är KALLVATTEN, TILLUFT är TILLUFT
    if any(any(w.endswith(sw) for sw in _disciplines.value("legend.SYSTEM_WORDS", SYSTEM_WORDS)) for w in ws):
        return "system"
    # ...och KALLVATTENLEDNING är en ledning av kallvatten: mediet står före efterledet, inte sist. Ett blad med
    # ritad text läser dessutom inte varje bokstav - "SPI??VATTEN?EDNING" - och ett oläst tecken är vilken
    # bokstav som helst. Så ordet prövas med ett efterled LEDNING avskuret och med högst två olästa tecken,
    # aldrig fler, i det som ska stämma.
    for w in _words(description, keep_unread=True):
        stems = [w] + ([w[:-len("LEDNING")]] if _ends_with(w, "LEDNING") else [])
        if any(_ends_with(st, sw) for st in stems for sw in _disciplines.value("legend.SYSTEM_WORDS", SYSTEM_WORDS)):
            return "system"
    for w in ws:
        if any(w.endswith(h) for h in MATERIAL_HEADS) or _is_fire_class(w):
            return "material"
    return None


def _role_pattern(designation) -> str:
    """Compare label structure independently of a trailing covering code or DN layout.

    RAD2-S13/W over 35 and KV1-X7 over 16 share a system/material
    structure. The covering and the printed position of the size do not turn
    the former system into a material. This is only a role comparison; the
    full designations and their distinct quantities remain unchanged.
    """
    pattern = getattr(designation, "pattern", "") or ""
    pattern = re.sub(r"/A+$", "", pattern)
    if getattr(designation, "dn_source", None) == "inline":
        pattern = re.sub(r"[-/+.]9$", "", pattern)
    return pattern


def assign_roles(legend: DrawingLegend, designations, prior: dict[str, str] | None = None) -> None:
    """Settle what each legend code is, from how the drawing uses it.

    A code that opens a designation carrying a dimension is a system code. A code that appears as a whole label
    of its own out on the drawing, and never opens a dimensioned one, is a component tag: a floor drain or a
    mixer, never a pipe. The rest are the materials and insulation classes the designations spell in the middle.

    The legend's own rows are read as designations too, so they are left out of this: a legend line proves only
    that the code exists, never how the drawing uses it."""
    legend.usage_systems = {}
    opens: set[str] = set()
    standalone: set[str] = set()
    codes = sorted({e.code.upper() for e in legend.entries}, key=len, reverse=True)

    def owner(head: str, text: str = "") -> str | None:
        for c in codes:
            if head == c or (head.startswith(c) and len(head) > len(c)):
                return c
            # a code with a placeholder for the system number carries what follows the number too (KVXX-3), and
            # only the whole label has that
            if _placeholder_pattern(c) is not None and (opens_with(text, c) or opens_with(head, c)):
                return c
        return None

    def outside(d) -> bool:
        return not legend.holds(getattr(d, "bbox", None))

    # Which shapes this sheet writes its pipe designations in. A code carrying a size is not yet a system: a
    # valve tag carries one too - `AV201-22` is a shut-off valve of 22 mm, not twenty-two metres of AV pipe -
    # and reading it as a system handed the drawing a pipe it does not draw. What separates them is the shape
    # the sheet writes: a pipe designation puts a material token after the system code and a fitting tag does
    # not. A shape only one code ever writes is that code's own tag; a shape several codes share is the sheet's
    # designation grammar, and that is what says a code opens one.
    by_pattern: dict[str, set[str]] = defaultdict(set)
    for d in designations:
        if getattr(d, "dn", None) is None or not outside(d):
            continue
        c = owner((getattr(d, "system_token", "") or "").upper(), (getattr(d, "text", "") or "").upper())
        if c:
            by_pattern[_role_pattern(d)].add(c)
    shared = {pat for pat, cs in by_pattern.items() if len(cs) >= 2}

    for d in designations:
        if legend.holds(getattr(d, "bbox", None)):
            continue                                    # this is the legend line itself
        text = (d.text or "").upper()
        head = (d.system_token or "").upper()
        if d.dn is not None:
            # where the sheet writes no shape more than one code shares, there is no grammar to appeal to and
            # a size on the label is all the evidence there is
            if not shared or _role_pattern(d) in shared:
                c = owner(head, text)
                if c:
                    opens.add(c)
                    # A label naming two pipes drawn side by side writes both codes, the size once at the end:
                    # `VV02-3-/KV02-3-15`. The second code opens a pipe as surely as the first - but it never
                    # stands first, so read from the head alone the cold water code of a whole sheet was a
                    # material. Each part after the slash that opens with a listed code opens it.
                    for part in text.split("/")[1:]:
                        toks = split_tokens(part)
                        cp = owner(toks[0], part) if toks else None
                        if cp:
                            opens.add(cp)
        else:
            for c in codes:
                if code_matches(text, c):
                    standalone.add(c)
                    break
    # Där listan säger att en kod är ett föremål och bladet ändå skriver den som ett rör, avgör bladet - men
    # bara på ett bevis och inte på en likhet: att etiketten bär ett materialled som listan själv räknar upp.
    # `TS1-X7-16` är ett tvättställ enligt orden och en PEX-ledning enligt bladet, för X7 står i listan som ett
    # material; `TD102-100` är ett tilluftsdon med anslutningsmåttet 100 och bär inget material alls. Det är den
    # skillnaden som skiljer en ledning från en pryl med ett mått, och den är hämtad ur listan och inte gissad.
    materials = {e.code.upper() for e in legend.entries
                 if role_from_words(e.description) == "material" or e.role == "material"}
    writes_a_pipe: set[str] = set()
    for d in designations:
        if getattr(d, "dn", None) is None or not outside(d):
            continue
        toks = [t.upper() for t in (getattr(d, "tokens", None) or split_tokens(getattr(d, "text", "") or ""))]
        c = owner((getattr(d, "system_token", "") or "").upper(), (getattr(d, "text", "") or "").upper())
        if c and any(t in materials for t in toks[1:]):
            writes_a_pipe.add(c)

    for e in legend.entries:
        c = e.code.upper()
        # Vad listan själv säger går före vad bladet råkar göra med koden. Ingenjören har skrivit ut svaret
        # bredvid koden; att gissa det ur användningen när det står där är att gissa i onödan - och gissningen
        # blev fel åt det dyra hållet, med kanalmeter under ett tilluftsdon.
        said = role_from_words(e.description)
        titled = role_from_heading(e.heading)
        if said == "component" and c in writes_a_pipe:
            e.role, e.role_from = "system", "the_sheet_writes_it_as_a_pipe"
        elif titled is not None and not (said == "component" and titled == "system"):
            e.role, e.role_from = titled, "the_list_heading_says_so"
        elif said is not None:
            e.role, e.role_from = said, "the_list_says_so"
        elif c in opens:
            e.role, e.role_from = "system", "usage"
        elif c in standalone:
            e.role, e.role_from = "component", "usage"
        else:
            e.role, e.role_from = "material", "usage"

    # What another sheet of the same set already worked out about a code this sheet never uses. A plan sheet
    # draws a floor of a building, not the whole vocabulary: a set's cold water code appears on every sheet, its
    # sprinkler code on three of them. Deciding from this sheet alone that the sprinkler code is a material - it
    # opened nothing here - reads the same project differently from one sheet to the next, which is the worst
    # kind of wrong, because a refused label never becomes a pipe label that is missing.
    #
    # It only fills silence. A code this sheet did use is settled by that use, whatever another sheet made of it.
    if prior:
        for e in legend.entries:
            was = prior.get(e.code.upper())
            if e.role == "material" and e.role_from not in LIST_SAYS and was in ("system", "component"):
                e.role, e.role_from = was, "other_sheet"

    # A legend can omit a numbered variant which the plan explicitly labels.
    # Admit its vocabulary only when repeated complete labels carry a listed
    # material and a structure used by two listed systems of the same class.
    # No pipe or dimension is borrowed from those systems: each label must
    # still reach its own geometry in the attachment and ownership stages.
    listed_systems = {e.code.upper() for e in legend.entries if e.role == 'system'}
    materials = {e.code.upper() for e in legend.entries if e.role == 'material'}
    classes: dict[str, set[str]] = defaultdict(set)
    for code in listed_systems:
        match = re.fullmatch(r'([A-ZÅÄÖ]+)\d+', code)
        if match:
            classes[match[1]].add(code)
    evidence: dict[str, set[str]] = defaultdict(set)
    for d in designations:
        head = (getattr(d, 'system_token', '') or '').upper()
        match = re.fullmatch(r'([A-ZÅÄÖ]+)\d+', head)
        if (owner(head, (getattr(d, 'text', '') or '').upper()) is not None or not match or len(classes[match[1]]) < 2
                or getattr(d, 'dn', None) is None or not outside(d)
                or _role_pattern(d) not in shared):
            continue
        tokens = split_tokens((getattr(d, 'text', '') or '').upper())
        if any(t in materials for t in tokens[1:]):
            evidence[head].add(getattr(d, 'did', '') or str(d.bbox))
    legend.usage_systems = {head: sorted(ids) for head, ids in sorted(evidence.items()) if len(ids) >= 2}

    # A sheet only shows what a sheet shows. A code the legend lists under "SYSTEM SPILLVATTEN" is a system code
    # whether or not this particular page happens to carry a dimensioned label for it - and where it does not,
    # every label of that system was being refused as not naming a pipe at all. That is the same project reading
    # differently from one sheet to the next, which is the worst kind of wrong: silent, and invisible in the
    # counts, because a refused label never becomes a pipe label to be missing.
    #
    # The drawing's own grouping settles it. A heading is the sheet saying "these belong together", so a code with
    # no usage of its own takes the role its heading-mates were given by usage - and only when the heading has
    # such evidence, and only in one direction: it may promote a code the page did not use, never demote or
    # reclassify one the page did.
    by_heading: dict[str, list[LegendEntry]] = defaultdict(list)
    for e in legend.entries:
        by_heading[(e.heading or "").strip().upper()].append(e)
    if len(by_heading) < 2:
        return              # one heading over everything groups nothing, and cannot speak for anything
    for head, group in by_heading.items():
        if not head:
            continue
        evidenced = Counter(e.role for e in group if e.role in ("system", "component")
                            and e.role_from == "usage")
        if len(evidenced) != 1:
            continue        # a section holding both kinds is not a section that says which one a code is
        role, n = evidenced.most_common(1)[0]
        if 2 * n < len(group):
            continue        # A section speaks when the page has shown most of it. Two codes out of nineteen is
                            # not the section speaking: on a real sheet the section listing the sanitary fittings
                            # - floor drain, mixer, washbasin, WC, water heater - carried a dimensioned label for
                            # a shut-off valve and a slop hopper, and every fitting in it was promoted to a pipe
                            # system. The page then named a hundred pipes it does not draw, each of them a
                            # fitting, and reported every one as a pipe that never got a metre.
        for e in group:
            if e.role == "material":
                e.role = role
                e.role_from = "heading"
