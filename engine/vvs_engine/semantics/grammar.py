"""Drawing-local VVS designation grammar.

The engine never knows expected code VALUES. It discovers the STRUCTURE of code-like words in the current drawing:
class patterns such as  A9-A9-9  or  A9-A9-9-A9  (A = letters, 9 = digits, separators literal), their frequencies,
and which pattern position behaves like a nominal diameter. Twin-shape ambiguities left by the recognizer
(O/0, I/1, S/5, B/8, Z/2, G/6) are resolved by choosing the reading whose pattern is most frequent in this drawing.
All of this is local to one analysis job.
"""
from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..text.model import Glyph, TextRow

from .. import rules as _rules


def _R(rule_id, default):
    """Vad regeln står på för den läsning som körs på den här tråden."""
    return _rules.value(rule_id, default)


TWINS = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "8": "B", "Z": "2", "2": "Z", "G": "6", "6": "G"}
SEPARATORS = "-/+.,:()[]"
MARGIN = 0.07
PATTERN_FLOOR = 2.0       # words: below this a drawing-local pattern is a one-off, not structure


def char_class(c: str) -> str:
    if c.isalpha():
        return "A"
    if c.isdigit():
        return "9"
    return c


COUNT_PREFIX_RE = re.compile(r"^(\d{1,2})[xX](.+)$")
# a whole word that is a size and nothing more, with an optional short medium qualifier: a dimension row
DIM_ROW_RE = re.compile(r"^(\d{1,4})(?:[-/]?[(\[]?[A-ZÅÄÖ]{1,3}[)\]]?)?$")


def strip_count_prefix(word: str) -> tuple[int, str]:
    m = COUNT_PREFIX_RE.match(word)
    if m and is_code_like(m.group(2)) and any(ch in m.group(2) for ch in "-/"):
        return int(m.group(1)), m.group(2)
    return 1, word


def token_shape(tok: str) -> str:
    """Shape of a token: A<alpha-run-length>D<digit-run-length> for prefix-letters-then-digits tokens."""
    m = re.fullmatch(r"([A-Za-zÅÄÖ]*)(\d*)([A-Za-zÅÄÖ]*)", tok)
    if not m:
        return "?"
    return f"A{len(m.group(1))}D{len(m.group(2))}{'A' + str(len(m.group(3))) if m.group(3) else ''}"


def strip_row_separator(word: str) -> str:
    """Skiljetecknet sist i ett ord hör till raden, inte till koden.

    En rad som räknar upp flera koder skriver dem med komma emellan - "KV0175-32, VV0175-32". Ordet före
    kommatecknet är koden; kommatecknet är bara det som skiljer den från nästa. Behålls det blir samma kod två
    olika koder: `KV0175-32,` och `KV0175-32` har samma tecken men olika mönster (`A9-9,` mot `A9-9`), och då
    delas bladets egen grammatik i två familjer för ett rör, ingendera stark nog att bära det.

    Bara sist i ordet. Ett kommatecken inne i ordet kan vara en decimal - "32,5" är ett mått, inte två koder -
    och det röret rörs inte.
    """
    return word.rstrip(",;") if word.rstrip(",;") else word


def compress_pattern(word: str) -> str:
    cnt, core = strip_count_prefix(word)
    if cnt > 1:
        return "#" + compress_pattern(core)
    out = []
    for c in word:
        k = char_class(c)
        if out and out[-1] == k and k in "A9":
            continue
        out.append(k)
    return "".join(out)


def is_code_like(word: str) -> bool:
    """Structural test: letters AND digits present, only code characters, starts with a letter or a count prefix.

    The opening letter is what the rule has always said and is worth enforcing: a code names its system first,
    before any count prefix is stripped. Without it every word whose leading letter the recogniser read as its
    twin digit - a plain word, a date in the title block - counts as a code and teaches the drawing-local grammar
    a pattern that then outvotes the real labels.

    The length limit holds per code, not per word. A label that names the tap-water trio of one riser writes
    three codes with slashes between them - `KV01-53-/VV01-53-32/VVC01-53-20`, 31 characters - and a limit on
    the whole word took the label for prose: the three pipes it names got no metres at all, though each part
    is as short as any single code. Each slash-separated part keeps the old limit of 24, and the word as a
    whole may carry at most four of them."""
    parts = word.split("/")
    if len(word) < 2 or len(parts) > 4 or any(len(p) > 24 for p in parts) or (len(parts) == 1 and len(word) > 24):
        return False
    if not re.fullmatch(r"[A-Za-zÅÄÖØ0-9\-/+.,:()\[\]]+", word):
        return False
    has_a = any(c.isalpha() for c in word)
    has_d = any(c.isdigit() for c in word)
    if not (has_a and has_d):
        return False
    m = COUNT_PREFIX_RE.match(word)
    head = m.group(2) if m else word
    return bool(head) and head[0].isalpha()


@dataclass
class WordReading:
    text: str
    pattern: str
    flips: int          # number of twin flips relative to the recognizer's best reading
    cost: float         # summed score deltas of flips


def word_readings(glyphs: list[Glyph]) -> list[WordReading]:
    """Enumerate alternative readings of a word over its twin-ambiguous glyphs (capped).

    Identical ambiguous characters inside one token are the same glyph shape of the same font and are resolved
    together ("1OO" reads "1OO" or "100", never "10O"); tokens are independent ("KVO1-40" stays possible)."""
    amb = [i for i, g in enumerate(glyphs) if g.char in TWINS and any(a == TWINS[g.char] and sc <= g.score + MARGIN for a, sc in g.alternatives)]
    base = "".join(g.char for g in glyphs)
    readings = [WordReading(base, compress_pattern(base), 0, 0.0)]
    if not amb:
        return readings
    tok_idx, t = [], 0
    for g in glyphs:
        if not g.char.isalnum():
            t += 1
        tok_idx.append(t)
    groups: dict[tuple[int, str], list[int]] = {}
    for i in amb:
        groups.setdefault((tok_idx[i], glyphs[i].char), []).append(i)
    keys = list(groups)[:5]
    for k in range(1, len(keys) + 1):
        for combo in itertools.combinations(keys, k):
            chars = [g.char for g in glyphs]
            cost = 0.0
            for key in combo:
                for i in groups[key]:
                    g = glyphs[i]
                    alt = TWINS[g.char]
                    sc = next(s for a, s in g.alternatives if a == alt)
                    chars[i] = alt
                    cost += max(0.0, sc - g.score)
            txt = "".join(chars)
            readings.append(WordReading(txt, compress_pattern(txt), k, cost))
    return readings


@dataclass
class GrammarFamily:
    pattern: str
    count: int
    examples: list[str] = field(default_factory=list)
    numeric_positions: dict[int, int] = field(default_factory=dict)   # token index -> occurrences of pure-digit token
    dn_token_index: int | None = None
    dn_nominal_fraction: dict[int, float] = field(default_factory=dict)


class DesignationGrammar:
    """Drawing-local statistics of code-like word structures (patterns + token shapes)."""

    def __init__(self):
        self.pattern_weight: Counter = Counter()
        self.shape_weight: Counter = Counter()      # (base pattern, token index, shape) -> weight
        self.families: dict[str, GrammarFamily] = {}

    @staticmethod
    def _base(pattern: str) -> str:
        return pattern[1:] if pattern.startswith("#") else pattern

    @staticmethod
    def _admissible(r: "WordReading") -> bool:
        """Readings a label may consist of: a code, a number, or a bare dimension with its medium qualifier."""
        return (is_code_like(r.text) or r.text.isdigit()
                or re.fullmatch(r"\d[\d.,:+\-/]*\d", r.text) is not None
                or DIM_ROW_RE.fullmatch(r.text.upper()) is not None)

    def observe(self, readings: list[WordReading]) -> None:
        """Only words whose recognizer reading (0 flips) is code-like or a pure number contribute; their
        alternative readings share the word's unit weight."""
        base_r = readings[0]
        if not self._admissible(base_r):
            return
        code = [r for r in readings if self._admissible(r)]
        w = 1.0 / len(code)
        for r in code:
            base = self._base(r.pattern)
            self.pattern_weight[base] += w
            _, core = strip_count_prefix(r.text)
            for i, tok in enumerate(split_tokens(core)):
                self.shape_weight[(base, i, token_shape(tok))] += w

    def typicality(self, r: WordReading) -> float:
        """Mean drawing-local support of the reading's token shapes. A shape seen in fewer than two words (or in
        under 5 % of the pattern's words) is no evidence: it must not overturn the recognizer's best reading."""
        base = self._base(r.pattern)
        _, core = strip_count_prefix(r.text)
        toks = split_tokens(core)
        if not toks:
            return 0.0
        floor = max(2.0, 0.05 * self.pattern_weight.get(base, 0.0))
        ws = [self.shape_weight.get((base, i, token_shape(t)), 0.0) for i, t in enumerate(toks)]
        return sum(w for w in ws if w >= floor) / len(toks)

    @staticmethod
    def nominal_tokens(text: str) -> int:
        """Digit tokens that read as a generic nominal pipe size.

        Any token after the first counts, and the first one too when the whole word is nothing but a size with an
        optional short medium qualifier: such a word is a dimension row, where the size is the entire content,
        so between two twin readings of it the one that spells a size is the one that says something."""
        _, core = strip_count_prefix(text)
        n = sum(1 for i, t in enumerate(split_tokens(core)) if i > 0 and t.isdigit() and int(t) in NOMINAL_SIZES)
        m = DIM_ROW_RE.fullmatch(core.upper())
        if m and int(m.group(1)) in NOMINAL_SIZES:
            n += 1
        return n

    def choose(self, readings: list[WordReading]) -> WordReading:
        """Pick the reading with the most frequent drawing-local pattern, then the most typical token shapes.
        When the drawing itself cannot separate the readings (every word carries the same twin ambiguity, so the
        alternative patterns tie), the reading whose size token is a nominal pipe size wins (11O -> 110); only
        then fewer twin flips, lower cost, then text."""
        def weight(r: WordReading) -> float:
            # a pattern carried by fewer than two words is no evidence: often the only word carrying it IS this
            # word, whose reading would then be voting for itself (the same floor typicality already applies)
            w = self.pattern_weight.get(self._base(r.pattern), 0.0)
            return w if w >= _R("semantics.grammar.PATTERN_FLOOR", PATTERN_FLOOR) else 0.0

        def dimension(r: WordReading) -> int:
            """How completely the whole word reads as a dimension: 2 for a bare generic nominal size, 1 for one
            with a short medium qualifier after it, 0 otherwise.

            A drawing-local pattern is evidence about how this drawing structures its codes; a word that is
            nothing but a size has no structure to speak of, so there the size itself is the stronger reading.
            A size that needs no qualifier to be a size outranks one that reads a trailing letter into it, which
            is how a size and its twin ("160" against "16O") separate at all."""
            m = DIM_ROW_RE.fullmatch(r.text.upper())
            if not m or int(m.group(1)) not in NOMINAL_SIZES:
                return 0
            return 2 if r.text.isdigit() else 1

        base = next((r for r in readings if r.flips == 0), None)
        base_tokens = split_tokens(base.text) if base is not None else []

        def invented_numbers(r: WordReading) -> int:
            """Fields a twin flip turned into a number that is no pipe size: `VS1-S13` read as `VS1-513`.

            A flip that makes a size out of a misread one (`11O` -> `110`) is what flipping is for. One that turns
            a material code into a three-digit number that no pipe has is not, however common that wrong shape
            happens to be on a small sheet - there it outvoted the right reading three to one."""
            if base is None or r.flips == 0:
                return 0
            toks = split_tokens(r.text)
            if len(toks) != len(base_tokens):
                return 0
            return sum(1 for a, b in zip(base_tokens, toks)
                       if a != b and b.isdigit() and not a.isdigit() and len(b) >= 3 and int(b) not in NOMINAL_SIZES)

        def key(r: WordReading):
            return (-dimension(r), invented_numbers(r), -weight(r), -round(self.typicality(r), 3),
                    -self.nominal_tokens(r.text), r.flips, r.cost, r.text)
        code = [r for r in readings if self._admissible(r)]
        pool = code if code else readings
        return sorted(pool, key=key)[0]

    def finalize(self, words: list[str]) -> None:
        fams: dict[str, GrammarFamily] = {}
        for w in words:
            if not is_code_like(w):
                continue
            _, w = strip_count_prefix(w)
            pat = compress_pattern(w)
            f = fams.get(pat)
            if f is None:
                f = GrammarFamily(pattern=pat, count=0)
                fams[pat] = f
            f.count += 1
            if len(f.examples) < 6 and w not in f.examples:
                f.examples.append(w)
            for i, tok in enumerate(split_tokens(w)):
                if tok.isdigit():
                    f.numeric_positions[i] = f.numeric_positions.get(i, 0) + 1
        # values seen per (pattern, token index)
        values: dict[tuple[str, int], list[int]] = defaultdict(list)
        for w in words:
            if not is_code_like(w):
                continue
            _, w = strip_count_prefix(w)
            pat = compress_pattern(w)
            for i, tok in enumerate(split_tokens(w)):
                if tok.isdigit():
                    values[(pat, i)].append(int(tok))
        for f in fams.values():
            # DN token index: a pure-digit position that is numeric in (nearly) every member AND whose values
            # mostly belong to the generic nominal pipe-size series (industry knowledge, not drawing-specific)
            cands = []
            for i, n in f.numeric_positions.items():
                if n < 0.8 * f.count or i == 0:
                    continue
                vals = values.get((f.pattern, i), [])
                nominal = sum(1 for v in vals if v in NOMINAL_SIZES)
                if vals and nominal >= 0.6 * len(vals):
                    cands.append((i, nominal / len(vals)))
            if len(cands) == 1:
                f.dn_token_index = cands[0][0]
            elif len(cands) > 1:
                cands.sort(key=lambda c: (-c[1], c[0]))
                f.dn_token_index = cands[0][0] if cands[0][1] > cands[1][1] else None
            f.dn_nominal_fraction = {i: round(frac, 2) for i, frac in cands}
        self.families = fams

    def as_dict(self) -> dict:
        return {"families": [{"pattern": f.pattern, "count": f.count, "examples": f.examples,
                              "numeric_positions": f.numeric_positions, "dn_token_index": f.dn_token_index}
                             for f in sorted(self.families.values(), key=lambda x: (-x.count, x.pattern))]}


def split_tokens(word: str) -> list[str]:
    return [t for t in re.split(r"[\-/+.,:()\[\]]+", word) if t]


# Generic nominal pipe sizes (industry standard DN / copper / plastic series); used as PLAUSIBILITY evidence only.
NOMINAL_SIZES = {6, 8, 10, 12, 15, 16, 18, 20, 22, 25, 28, 32, 35, 40, 42, 50, 54, 63, 65, 75, 76, 80, 90, 100, 108,
                 110, 125, 133, 140, 150, 160, 168, 200, 219, 225, 250, 300, 315, 350, 400, 450, 500, 600, 630}


def dn_plausible(v: int) -> bool:
    return 6 <= v <= 1200
