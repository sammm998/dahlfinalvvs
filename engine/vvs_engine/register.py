"""Alla beteckningar på bladet: vad varje skriven kod är, hur många gånger den står och vad den mängdar.

En VVS-läsning frågar efter rören. Den som har valt "Alla" frågar efter allt bladet skriver: rören, men också
ventilerna, apparaterna, radiatorerna, brandklasserna och rummen - oavsett disciplin. Här samlas varje sådan
beteckning en gång, med var den står, så att den kan markeras, och med sin mängd:

  ledning    meter, de VVS-läsningen mätte på rören under just den beteckningen
  komponent  styck: en per skriven etikett, och ett antal skrivet framför koden räknas som det antalet (4*TV103)
  klass      styck: en brandklass (EI60), eller en material- eller isolerklass som förklaringslistan förklarar.
             Den beskriver ett utförande, och det bladet skriver är hur många gånger den står
  rum        m², den area rumsetiketten själv skriver
  okänd      styck, som komponenten - men varken bladet eller motorns referensdata säger vad koden är

Det läsningen inte förstår gissas inte: en kod som bladets egen förklaringslista inte förklarar står kvar som
"granskas", och om motorns svenska referensdata känner koden visas dess ord bredvid som en ledtråd, aldrig som
bladets besked.

Det som inte är en beteckning räknas inte: förklaringslistans egna rader (de förklarar koden, de använder den
inte), ritningsnummer och filnamn, mätvärden - ett decimaltal är ett värde (0,007 l/s, 11,7 m²), aldrig ett
namn - och höjder, ett höjdord följt av ett tal (CL 3441 ÖFG).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from .handling import reads_as_a_drawing_number
from .semantics.grammar import is_code_like

COUNT_PREFIX = re.compile(r"^(\d{1,3})\s*[*xX×]\s*(?=[A-ZÅÄÖa-zåäö])(\S+)$")   # 4*TV103, 2xKV1-X32-16, 2*TM
# a drawing number written out in full: discipline, content code, category, then the numbering (reference data,
# drawing_numbering.json: V-56-1-124) - however long the numbering is (V-50-2-123456-0003)
DRAWING_NUMBER = re.compile(r"^[A-ZÅÄÖ]{1,2}-\d{2}-\d-[A-ZÅÄÖ0-9]")
# a list writes a family once with its placeholder for what varies (TS1XX, X0-X0-00/XX): a pattern, not a label
PLACEHOLDER = re.compile(r"(?:^|[-/])X{2,}$|[A-ZÅÄÖ0-9]X{2,}$")
TEMPLATE = re.compile(r"^[XO0/.\-]+$")             # XXOO-X00-000/X00: letters as X, digits as 0
VALUE = re.compile(r"\d[.,]\d")                     # a decimal number is a value, never a name
FILE = re.compile(r"\.(?:dwg|dxf|pdf|png|jpe?g|tiff?)$", re.I)
EDGE = ",.;:()[]\"'"
NOTE = re.compile(r"\s*\([^)]*\)$")               # a note set beside a name: S3-P5-160 (L)
# a size written on the row below a name that ends in a class: KV1-K1/S2 over 22 reads KV1-K1/S2-22
SIZE_AFTER_CLASS = re.compile(r"^(.+?)(/[A-ZÅÄÖ]{1,3}\d{0,2})-(\d{1,4})$", re.I)
HEAD = re.compile(r"^[A-ZÅÄÖ]+")

KINDS = ("ledning", "komponent", "klass", "rum", "okänd")
UNIT = {"ledning": "m", "komponent": "st", "klass": "st", "rum": "m²", "okänd": "st"}

# The engine's own Swedish reference data (reference_sources): what a code commonly means. Shown beside a code the
# sheet does not explain, as a hint and named as such.
REFERENCE_FILES = (("valves.json", "ventil"), ("apparatus.json", "apparat"), ("sanitary_fixtures.json", "sanitet"),
                   ("drainage_wells.json", "brunn"), ("control_devices.json", "styrdon"),
                   ("side_contractor_equipment.json", "sidoentreprenad"))
# words the sheet's own list writes for a medium, and the discipline that medium belongs to
AIR_WORDS = ("TILLUFT", "FRÅNLUFT", "FRANLUFT", "UTELUFT", "AVLUFT", "ÖVERLUFT", "OVERLUFT", "CIRKULATIONSLUFT")
WATER_WORDS = ("KALLVATTEN", "VARMVATTEN", "SPILLVATTEN", "DAGVATTEN", "DRÄNVATTEN", "TAPPVATTEN", "FJÄRRVÄRME",
               "VÄRMEVATTEN", "KÖLDBÄRARE")


def _reference_data(fn: str) -> dict:
    root = Path(__file__).resolve().parents[2] / "reference_sources" / "swedish-vvs-drawings-main" / "data"
    try:
        return json.loads((root / fn).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def level_codes() -> frozenset[str]:
    """CL, VG, UK, ÖK, FG ...: the words a height is written with (reference data, level_references.json)."""
    return frozenset((e.get("code") or "").upper() for e in _reference_data("level_references.json").get("entries", [])
                     if e.get("code"))


def _common(terms: list[str]) -> str:
    """What several terms for one code have in common. AV is a two-, three- and four-way shut-off valve, told
    apart by the symbol and never by the code: a written AV says shut-off valve and no more."""
    terms = list(dict.fromkeys(t for t in terms if t))
    if len(terms) <= 1:
        return terms[0] if terms else ""
    heads = {t.split(",")[0].strip() for t in terms}
    return heads.pop() if len(heads) == 1 else " / ".join(terms)


@lru_cache(maxsize=1)
def reference_terms() -> dict[str, tuple[str, str, str | None]]:
    """Code -> (Swedish term, what kind of thing, English term) from the reference data the engine ships."""
    found: dict[str, dict] = {}
    for fn, what in REFERENCE_FILES:
        for e in _reference_data(fn).get("entries", []):
            code = (e.get("code") or "").upper()
            if not code or not e.get("term_sv"):
                continue
            f = found.setdefault(code, {"what": what, "sv": [], "en": []})
            if f["what"] == what:                  # the first file that knows the code speaks for it
                f["sv"].append(e["term_sv"])
                f["en"].append(e.get("term_en") or "")
    return {code: (_common(f["sv"]), f["what"], _common(f["en"]) or None) for code, f in found.items()}


def _overlaps(a, b, pad: float = 0.5) -> bool:
    return min(a[2], b[2]) + pad > max(a[0], b[0]) and min(a[3], b[3]) + pad > max(a[1], b[1])


def _same_text(a, b) -> bool:
    """Whether two boxes hold the same writing: they cover at least half of the smaller one. Two labels set
    close together touch; one label read twice - from the text layer and from its strokes - covers itself."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return False
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return small > 0 and w * h >= 0.5 * small


HEIGHT = re.compile(r"^([A-ZÅÄÖ]{1,3})[+=\-]?(\d{3,5})([A-ZÅÄÖ]{0,3})$")
# a part of eight letters or more is a word, also where a hyphen ties it to a code: a title's VS-INSTALLATIONER,
# read V5-INSTALLATIONER out of strokes, is no designation
LONG_WORD = re.compile(r"(?:^|-)[A-ZÅÄÖ]{8,}(?:-|$)")


def _a_height(word: str) -> bool:
    """CL3441, written CL 3441 ÖFG: a centre line 3441 mm above the finished floor. A level word followed by a
    number is where something is, not what it is."""
    m = HEIGHT.match(word.upper())
    levels = level_codes()
    return bool(m) and m.group(1) in levels and (not m.group(3) or m.group(3) in levels)


def _untwin(word: str) -> str:
    """A glyph read out of strokes as its twin. An O between two digits is a 0 (RAD1O1 is RAD101), an I between
    two digits a 1, and a 0 between two letters an O."""
    w = re.sub(r"(?<=\d)[OQ](?=\d)", "0", word)
    w = re.sub(r"(?<=\d)I(?=\d)", "1", w)
    return re.sub(r"(?<=[A-ZÅÄÖ])0(?=[A-ZÅÄÖ])", "O", w)


def _not_a_name(word: str) -> str | None:
    """Why a written word is not a designation, or None when it may be one."""
    if VALUE.search(word) or _a_height(word):
        return "values"
    stem = FILE.sub("", word)
    if stem != word or reads_as_a_drawing_number(stem.rstrip("-")) or DRAWING_NUMBER.match(stem.upper()):
        return "drawing_numbers"
    if PLACEHOLDER.search(word.upper()) or ("X" in word.upper() and TEMPLATE.match(word.upper())):
        return "placeholders"
    if "-" in word and LONG_WORD.search(word.upper()):
        return "words"
    return None


def _line_for(legend, name: str):
    """The sheet's own list line for a written code.

    - the code itself, or the opening code of a pipe's name (KV1 of KV1-K1-22)
    - else the family the list writes with its placeholder: B12ML is the list's BXXX GOLVBRUNN
    - else, for a pipe's name only, a system code followed by the system's number: KV + 1 for KV1-K1-22

    A code written on its own is never a longer form of a shorter one. A grid line's A200 is not the list's A,
    and B12ML is not its insulation class B. The reading's own lookup takes the longest code a label opens with.
    That is enough for a pipe's name, whose system code is followed by its number. Across everything a sheet
    writes, it is not."""
    key = (name or "").upper()
    head = re.split(r"[-/]", key)[0]
    piped = "-" in key
    best, rank = None, None
    for e in legend.entries or []:
        c = (e.code or "").upper()
        if not c:
            continue
        stem = c.rstrip("X")
        if key == c or (piped and head == c):
            r = (2, len(c), 0)
        elif stem and stem != c:
            if not (head.startswith(stem) and head[len(stem):][:1].isdigit()):
                continue
            r = (1, len(stem), 1)
        elif piped and head.startswith(c) and head[len(c):].isdigit():
            r = (1, len(c), 0)
        else:
            continue
        if rank is None or r > rank:
            best, rank = e, r
    return best


def _readable(text: str | None) -> bool:
    """Whether a list's words can be read as words. Text drawn as strokes and read glyph by glyph can come apart
    into its letters - "Y G G ?I A N D L I N G" - and that explains nothing."""
    words = (text or "").split()
    if not words:
        return False
    singles = sum(1 for w in words if len(w.strip("?")) <= 1)
    return not (len(words) >= 4 and 2 * singles >= len(words))


def _is_fire_class(code: str) -> bool:
    """EI15, EI30, EI60, E60: en brandklass beskriver en klädsel."""
    c = code.upper()
    return len(c) >= 3 and c[0] == "E" and (c[1] == "I" or c[1].isdigit()) and c[1:].lstrip("I").isdigit()


def _discipline_of(entry) -> str | None:
    """What the sheet's own list says the medium is, when its words say it outright."""
    if entry is None:
        return None
    words = f"{entry.heading} {entry.description}".upper()
    if any(w in words for w in AIR_WORDS):
        return "ventilation"
    if any(w in words for w in WATER_WORDS):
        return "vvs"
    return None


def _rooms_and_units(page) -> tuple[list, list]:
    """The room labels with an area, and the fixture codes beside them, from the page's text layer."""
    path = getattr(page, "source_path", None)
    if not path:
        return [], []
    try:
        import pymupdf
        from .abt.rooms import read_rooms, text_lines
        from .abt.units import read_units
        with pymupdf.open(path) as doc:
            pdf_page = doc[page.info.index]
            lines = text_lines(pdf_page)
            rooms = [r for r in read_rooms(pdf_page, page.info.index, lines) if r.kind != "summa"]
            units, _ = read_units(pdf_page, page.info.index, lines, rooms)
        return rooms, units
    except Exception:
        return [], []


def register_of_designations(pa) -> dict[str, Any]:
    """Every designation the sheet writes, once, with its kind, its places and its quantity."""
    from .pipeline import _is_an_apparatus_tag

    legend = pa.legend
    found: dict[str, dict] = {}
    excluded: Counter = Counter()
    # a flow or principle diagram is drawn without a scale: its pipes are measured on the plans, not missed here
    from .measure.scale import NOT_MEASURED_HERE, SECTION_NOT_MEASURED
    reason = getattr(getattr(pa, "scale", None), "reason", None)
    schematic = reason in NOT_MEASURED_HERE
    elsewhere = ("sektion, mängdas på planritningarna" if reason == SECTION_NOT_MEASURED
                 else "schema, mängdas på planritningarna")

    def add(name: str, bbox, line: str, count: int = 1, source: str = "reading") -> None:
        # KV1-K1/S2 over 22 is the takeoff's KV1-K1-22/S2: the takeoff writes the size before the class, as the
        # sheet does where it writes the label on one line, and both ways of writing it are one entry
        m = SIZE_AFTER_CLASS.match(name)
        if m:
            name = f"{m.group(1)}-{m.group(3)}{m.group(2)}"
        key = name.upper()
        e = found.setdefault(key, {"name": name, "labels": 0, "count": 0, "places": [], "sources": set()})
        e["labels"] += 1
        e["count"] += count
        e["places"].append({"bbox": [round(v, 1) for v in bbox], "line": " ".join((line or name).split()),
                            "count": count})
        e["sources"].add(source)

    # 1. The reading's own designations: the names the takeoff uses, a dimension on the row below joined on.
    #    A note written beside the name - S1-P2-75 (L) - stays on the line where it stands and is not part of
    #    the name. Where the sheet writes its labels as text, a code read out of strokes is more often a symbol
    #    drawn with lines - a gauge's ring read as O1 - than a label, and it is weighed with the words below.
    #    Which way a sheet writes is what most of its labels out on the drawing show: a sheet drawn in strokes
    #    can still carry its grid lines' letters as text.
    taken = []
    stroked = []
    read = []
    for d in pa.designations:
        if legend.holds(d.bbox):
            excluded["legend_rows"] += 1
            continue
        line = (d.display_text or d.text or "").strip()
        aside = (getattr(d, "aside", "") or "").strip()
        name = line[: -len(aside)].strip() if aside and line.endswith(aside) else line
        drawn = getattr(d, "source", "text") != "text"
        if drawn:
            name = _untwin(name)
        why = _not_a_name(name) if name else "empty"
        if not why and not any(ch.isdigit() for ch in name) and any(ch.isdigit() for ch in (d.display_text or "")):
            why = "words"                      # M0BIL: only a code by the twin it was read with
        if why:
            excluded[why] += 1
            continue
        read.append((d, name, line, drawn))
    writes_text = sum(1 for r in read if not r[3]) > sum(1 for r in read if r[3])
    for d, name, line, drawn in read:
        taken.append(d.bbox)
        if writes_text and drawn:
            stroked.append((name, d.bbox, line, max(int(d.multiplier or 1), 1)))
            continue
        add(name, d.bbox, line, max(int(d.multiplier or 1), 1))

    # 2. What the sheet writes that the reading did not take for a label: a radiator's type beside its size, a
    #    count written in front of a fixture's code, a tag beside an apparatus.
    #    Text drawn as strokes is read glyph by glyph, and a glyph read as its twin (0 for O) turns a word into
    #    something code-shaped: "SOM" in a note became S0M. Such a misreading is a one-off; a code the sheet
    #    really uses there recurs. So a code read from strokes counts where it is read at least twice, where the
    #    sheet also writes it as text, or where the reading measured a pipe under it.
    candidates = []
    for row in pa.lines:
        if legend.holds(row.bbox) or any(_same_text(row.bbox, b) for b in taken):
            continue
        drawn = getattr(row, "source", "text") != "text"
        for raw in (row.text or "").split():
            w = raw.strip(EDGE)
            if drawn:
                w = _untwin(w)
            if not w:
                continue
            why = _not_a_name(w)
            if why:
                if is_code_like(w):
                    excluded[why] += 1
                continue
            m = COUNT_PREFIX.match(w)
            if m:
                code = m.group(2).strip(EDGE)
                if code and not _not_a_name(code):
                    candidates.append((code, row, int(m.group(1)), drawn))
                continue
            if is_code_like(w):
                candidates.append((w, row, 1, drawn))
    measured = {q["designation"].upper().split("/")[0] for q in pa.quantities
                if q.get("designation") and float(q.get("confirmed_total_m") or 0) > 0}
    drawn_seen = Counter([c[0].upper() for c in candidates if c[3]] + [x[0].upper() for x in stroked])

    def corroborated(code: str) -> bool:
        key = code.upper()
        return drawn_seen[key] >= 2 or key in found or key.split("/")[0] in measured

    for code, row, n, is_drawn in candidates:
        if is_drawn and not corroborated(code):
            excluded["one_off_drawn_words"] += 1
            continue
        add(code, row.bbox, row.text, n, "text" if not is_drawn else "strokes")
    for name, bbox, line, n in stroked:
        if not corroborated(name):
            excluded["one_off_drawn_words"] += 1
            continue
        add(name, bbox, line, n, "strokes")

    # 3. Rooms with their written area, and the fixture codes beside them, where the page has a text layer.
    rooms, units = _rooms_and_units(pa.page)
    for u in units:
        if not any(_same_text(u.bbox, p["bbox"]) for e in found.values() for p in e["places"]):
            add(u.code, u.bbox, u.code, 1, "units")
    room_entries = defaultdict(lambda: {"labels": 0, "area": 0.0, "places": []})
    for r in rooms:
        name = " ".join(x for x in (r.number, r.name) if x) or r.area_text
        re_ = room_entries[name]
        re_["labels"] += 1
        re_["area"] += float(r.area_m2)
        re_["places"].append({"bbox": [round(v, 1) for v in r.bbox], "line": " / ".join(r.lines), "count": 1})

    from .pipeline import _a_whole_pipe_name_of_a_standard_system
    # The takeoff's rows by the name they carry. A row is a name and a size, so one name can have several:
    # S3-R8 measured at DN 110 and drawn as a stack at DN 75 is one name on the sheet and two rows.
    by_name: dict[str, list[dict]] = defaultdict(list)
    for q in pa.quantities:
        if q.get("designation"):
            by_name[q["designation"].upper()].append(q)
    # ...and the runs of other disciplines the widened reading measured on lines the takeoff left alone. They are
    # rows of the register only, never of the takeoff, and every one of them is for review: their state is never
    # the takeoff's CONFIRMED.
    for w in getattr(pa, "wide_runs", None) or []:
        by_name[w["designation"].upper()].append({"designation": w["designation"], "dn": w.get("size"),
                                                  "confirmed_total_m": w["metres"], "state": "WIDE",
                                                  "wide": True, "runs": w.get("runs") or []})
    claimed: set[str] = set()

    def name_for(name: str) -> str | None:
        """The takeoff's name for a written name: the same name, or the same name with or without the suffix
        after the slash (VS2-S13-12 written, VS2-S13-12/S4 measured), or with the note a reading kept beside it
        (S3-P5-160 (L)). A name gives its metres to one entry."""
        key = name.upper()
        if key in by_name and key not in claimed:
            return key
        bare = [k for k in by_name if NOTE.sub("", k) == key and k not in claimed]
        if len(bare) == 1:
            return bare[0]
        base = key.split("/")[0]
        same = [k for k in by_name if NOTE.sub("", k).split("/")[0] == base and k not in claimed]
        return same[0] if len(same) == 1 else None

    def metres(q) -> float:
        return float(q.get("confirmed_total_m") or q.get("confirmed_horizontal_m") or 0.0)

    refs = reference_terms()
    entries = []

    def entry_for(name: str, labels: int, count: int, places: list, qs: list | None) -> dict:
        lentry = _line_for(legend, name)
        # a code the list does not write but the sheet's own pipe names show to be a system
        role = lentry.role if lentry is not None else (
            legend.role_of_head(name) if legend.code_for(name) is None else None)
        readable = lentry is not None and _readable(lentry.description)
        head_m = HEAD.match(name.upper())
        head = head_m.group(0) if head_m else ""
        ref = refs.get(head)
        explained = readable and role in ("system", "component", "material")
        description, said_by = ((lentry.description, "förklaringslistan") if readable
                                else (ref[0], "referensdata") if ref else (None, None))
        reasons = []
        wide = any(q.get("wide") for q in qs or [])
        if qs:
            # a pipe's metres are the VVS reading's, and so is how sure they are
            kind = "ledning"
            quantity = round(sum(metres(q) for q in qs), 2)
            review = sum(float(q.get("review_m") or 0.0) for q in qs)
            sure = quantity > 0 and not review and all(q.get("state") == "CONFIRMED" for q in qs if metres(q) > 0)
            if quantity <= 0:
                reasons.append(elsewhere if schematic else "ingen sträcka nådd")
            elif wide:
                reasons.append("mätt i den vidgade läsningen, utan referensmängd")
            elif review:
                reasons.append(f"{review:.2f} m att granska")
            elif not sure:
                reasons.append("tvetydig")
        elif role == "system" or (role is None and _a_whole_pipe_name_of_a_standard_system(name)):
            kind, quantity, sure = "ledning", 0.0, False
            reasons.append(elsewhere if schematic else "ingen sträcka nådd")
        elif _is_fire_class(name):
            kind, quantity, sure = "klass", count, False
        elif role == "material" and "-" not in name:
            # a material or insulation class written on its own; inside a pipe's name it is the second part, so a
            # tag that opens with the code and a number (SHG613-V52) is a thing, whatever the list's role says
            kind, quantity, sure = "klass", count, explained
        elif role == "material":
            kind, quantity, sure = "komponent", count, explained
        elif role == "component" or ref is not None or _is_an_apparatus_tag(
                _Named(name, head, tokens=[t for t in name.split("/")[0].split("-") if t]), legend):
            kind, quantity, sure = "komponent", count, explained
        else:
            kind, quantity, sure = "okänd", count, explained
        if not sure and not qs and lentry is not None and not readable:
            reasons.append("förklaringslistans rad går inte att läsa")
        if not sure and not reasons:
            reasons.append("granskas" if explained else "bladet förklarar inte koden")
        lines = Counter(p["line"] for p in places)
        return {
            "name": name, "kind": kind, "unit": UNIT[kind], "quantity": quantity,
            "labels": labels, "state": "säker" if sure else "granskas", "reasons": reasons,
            "description": description, "described_by": said_by,
            # the reference data writes its own English term; the sheet's words are the sheet's
            "description_en": ref[2] if said_by == "referensdata" else None,
            "discipline": _discipline_of(lentry) or ("vvs" if (qs or ref) else None),
            "places": places,
            "variants": [{"line": ln, "labels": n} for ln, n in sorted(lines.items())] if len(lines) > 1 else [],
            # the lines a run of another discipline was measured on: the takeoff has no pipe for them to light
            **({"runs": [r for q in qs for r in q.get("runs") or []]} if wide else {}),
        }

    # the same name first, so that a name written in full keeps its own rows; then the near ones
    rows_of: dict[str, list[dict]] = {}
    for key in found:
        if key in by_name:
            rows_of[key] = by_name[key]
            claimed.add(key)
    for key, e in found.items():
        if key not in rows_of:
            k = name_for(e["name"])
            if k is not None:
                rows_of[key] = by_name[k]
                claimed.add(k)
    for key, e in found.items():
        entries.append(entry_for(e["name"], e["labels"], e["count"], e["places"], rows_of.get(key)))
    used = [q for qs in rows_of.values() for q in qs]
    # a name the takeoff measured that is not written out as such on the sheet still belongs to the sheet
    for k, qs in by_name.items():
        if k not in claimed and sum(metres(q) for q in qs) > 0:
            claimed.add(k)
            entries.append(entry_for(qs[0]["designation"], sum(int(q.get("label_count") or 0) for q in qs), 0, [], qs))
            used.extend(qs)
    for name, r in room_entries.items():
        entries.append({"name": name, "kind": "rum", "unit": "m²", "quantity": round(r["area"], 2),
                        "labels": r["labels"], "state": "säker", "reasons": [], "description": None,
                        "described_by": "rumsetiketten", "discipline": None, "places": r["places"], "variants": []})
    entries.sort(key=lambda x: (KINDS.index(x["kind"]), x["name"]))
    totals = {
        "entries": len(entries),
        "by_kind": {k: sum(1 for x in entries if x["kind"] == k) for k in KINDS},
        # the takeoff's own sum, not a sum of rounded rows, so that the two tables beside each other say the same -
        # with the other disciplines' runs on top, and said apart
        "metres": round(sum(metres(q) for q in used), 2),
        "wide_metres": round(sum(metres(q) for q in used if q.get("wide")), 2),
        "pieces": int(sum(x["quantity"] for x in entries if x["unit"] == "st")),
        "square_metres": round(sum(x["quantity"] for x in entries if x["unit"] == "m²"), 2),
        "to_review": sum(1 for x in entries if x["state"] == "granskas"),
    }
    return {"entries": entries, "totals": totals, "not_counted": dict(excluded)}


class _Named:
    """A written code seen the way the legend and the valve rule ask about a label."""

    def __init__(self, text: str, head: str, tokens: list[str] | None = None):
        self.text = text
        self.system_token = (text.split("-")[0].split("/")[0] if text else head)
        self.tokens = tokens or [t for t in text.split("-") if t]
