"""Läsaren: en teknisk beskrivning i AMA-uppställning blir en lista med materialposter.

Läsningen går på sidans geometri, inte på textens ordning. pymupdf lämnar raderna i den ordning PDF:en skrev
dem, och i en beskrivning står mängden "1 st" ofta skriven före sin post eller efter hela stycket; ordnade på
läge hamnar mängden på samma rad som koden den hör till. Kolumnerna tas ur bladets egen rubrikrad - KOD, TEXT,
MÄNGD, ENHET - när den finns, och ur hur raderna faktiskt står när den inte gör det.

Tre slags rader bär strukturen:

  AMA-rubrik   koden i vänsterkolumnen (PRB.12) och rubriken bredvid: kategorierna
  post         fetstil i textkolumnen, med en kod (B202B) eller en mängd i mängdkolumnen: en sak att köpa
  avsnitt      fetstil i versaler utan siffror (MATERIAL- OCH VARUKRAV): text om krav, inte en post

Allt mellan två poster är postens text. I den finns specifikationen (nyckel till vänster, värde i kolumnen
bredvid) och tillbehören under "Härtill:", som blir egna poster med posten de hör till som förälder. Produkter
som nämns i kravtexten utanför en post ("föravstängningsventiler Broens typ Ballofix") tas också med, som
omnämnda: de ska köpas, men mängden står i ritningen eller ingenstans.

Sidhuvud och sidfot känns igen på att de upprepas: samma text på samma ställe på mer än hälften av sidorna.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from .rsk import find as rsk_find  # RSK i alla skrivsätt: 573 24 87, 573 2487, 5732487

import pymupdf

# ---------------------------------------------------------------- fabrikat

# Varumärken som en VVS-beskrivning skriver, med de stavningar och böjningar de skrivs i. Nyckeln är gemener;
# värdet är namnet som det visas och filtreras på. Furo är Furhoffs varumärke och står under Furhoff, så att
# alla deras brunnar och rännor hamnar under ett fabrikat.
BRANDS: dict[str, str] = {
    "furhoff": "Furhoff", "furhoffs": "Furhoff", "furo": "Furhoff",
    "ifö": "IFÖ", "ifös": "IFÖ", "ifo": "IFÖ",
    "fmm": "FMM", "fmms": "FMM",
    "broen": "Broen", "broens": "Broen",
    "geberit": "Geberit", "geberits": "Geberit",
    "purus": "Purus",
    "armatec": "Armatec", "armatecs": "Armatec",
    "beulco": "Beulco", "beulcos": "Beulco",
    "nibe": "Nibe", "nibes": "Nibe",
    "mitsubishi": "Mitsubishi Electric",
    "wafix": "Wafix",
    "altech": "Altech", "altechs": "Altech",
    "mora": "Mora", "moras": "Mora",
    "gustavsberg": "Gustavsberg", "gustavsbergs": "Gustavsberg", "gbg": "Gustavsberg",
    "oras": "Oras", "uponor": "Uponor", "uponors": "Uponor", "danfoss": "Danfoss", "grundfos": "Grundfos",
    "wavin": "Wavin", "pipelife": "Pipelife", "jeremias": "Jeremias", "tece": "TECE", "viega": "Viega",
    "blücher": "Blücher", "aco": "ACO", "jafo": "Jafo", "kinnan": "Kinnan", "kemper": "Kemper",
    "sanka": "Sanka", "tapwell": "Tapwell", "hansgrohe": "Hansgrohe", "grohe": "Grohe",
    "thermotech": "Thermotech", "rehau": "Rehau", "isover": "Isover", "armacell": "Armacell",
    "rockwool": "Rockwool", "paroc": "Paroc", "kingspan": "Kingspan", "lk": "LK", "lks": "LK",
    "ta": "TA", "esbe": "ESBE", "esbes": "ESBE", "watts": "Watts", "honeywell": "Honeywell",
    "vaillant": "Vaillant", "bosch": "Bosch", "ctc": "CTC", "thermia": "Thermia", "duka": "Duka",
    "daikin": "Daikin", "panasonic": "Panasonic", "toshiba": "Toshiba", "samsung": "Samsung",
    "wilo": "Wilo",
    "xylem": "Xylem",
    "lowara": "Lowara",
    "ivt": "IVT",
    "kamstrup": "Kamstrup",
    "diehl": "Diehl",
    "oventrop": "Oventrop",
    "imi": "IMI",
    "belimo": "Belimo",
    "siemens": "Siemens",
    "regin": "Regin",
    "svedbergs": "Svedbergs",
    "franke": "Franke",
    "intra": "Intra",
    "lindab": "Lindab",
    "villeroy": "Villeroy & Boch",
    "duravit": "Duravit",
    "ksb": "KSB",
    "flygt": "Flygt",
    "kessel": "Kessel",
    "purmo": "Purmo",
    "rettig": "Rettig",
    "calpeda": "Calpeda",
    "dab": "DAB",
    "ebara": "Ebara",
    "viessmann": "Viessmann",
    "stiebel": "Stiebel Eltron",
    "eltron": "Stiebel Eltron",
    "metro": "Metro Therm",
    "bastec": "Bastec",
    "grundfoss": "Grundfos",
    "grundfos'": "Grundfos",
    "thermias": "Thermia",
    "wilos": "Wilo",
    "zehnder": "Zehnder",
    "lyngson": "Lyngson",
    "sanipex": "Sanipex",
    "ballofix": "Broen",
    "nordic": "Nordic Tec",
    "tour": "TA",
    "cupori": "Cupori",
    "mapress": "Geberit",
    "sanha": "Sanha",
    "conex": "Conex",
    "bänninger": "Conex Bänninger",
    "inr": "INR",
    "smedbo": "Smedbo",
    "hafa": "Hafa",
    "byggbeslag": "Byggbeslag",
    "marbodal": "Marbodal",
    "swegon": "Swegon",
    "beslagdesign": "Beslagdesign",
    "alterna": "Alterna",
    "vedum": "Vedum",
    "ballingslöv": "Ballingslöv",
    "tvättex": "Tvättex",
    "macro": "Macro Design"
}

# Ord som står före "typ" utan att vara ett fabrikat: ett system (KV typ EA), ett don, ett ord i texten.
NOT_BRANDS = {"kv", "vv", "vvc", "s", "d", "av", "för", "med", "och", "en", "ett", "den", "det", "som", "skyddsdon",
              "ventil", "ventiler", "klass", "utförande", "samma", "annan", "vald"}

# ---------------------------------------------------------------- mönster

AMA_CODE = re.compile(r"^(?:[A-ZÅÄÖ]{1,4}(?:\.\d+)*|\d{1,2})$")
CODE_TOKEN = re.compile(r"^(?=.*[A-ZÅÄÖ])(?=.*\d)[A-ZÅÄÖ0-9][A-ZÅÄÖ0-9\-/.]{1,15}$")
QTY = re.compile(r"^(\d+(?:[.,]\d+)?)(?:\s*[-–]\s*(\d+(?:[.,]\d+)?))?\s*([A-Za-zåäöÅÄÖ²³.]{1,8})?\.?$")
ART_NR = re.compile(r"Art\.?\s*nr\.?:?\s*((?:[A-Za-z]{1,4}\s)?[A-Za-z0-9][A-Za-z0-9\-/]*[A-Za-z0-9])", re.I)
LEAD_QTY = re.compile(r"^(\d+)\s*st\.?\s+", re.I)
OR_EQUAL = re.compile(r"eller\s+likvärdig", re.I)
DOTS = re.compile(r"\.{6,}")
SPEC_HEADS = {"specifikation", "storlek", "teknisk data", "tekniska data", "data"}
HERETO = re.compile(r"^härtill:?$", re.I)
# en lista av delar som ingår i posten: "Flödesmätarutrustning bestående av:", "Levereras med:"
PARTS_HEAD = re.compile(r"(bestående av|består av|levereras med|ingår|tillbehör|komplett med)\s*:?$", re.I)
SUPPLIED = re.compile(
    r"(?:levereras|tillhandahåll\w*|utföres|utförs|monteras|anslutes|ansluts)(?:\s+och\s+monteras)?\s+(?:av|utav)\s+"
    r"(?:den\s+)?(beställare\w*|kommunen|\w*kommun|markentreprenör\w*|byggentreprenör\w*|elinstallatör\w*|el-?entreprenör\w*|"
    r"EE|BE|GE|VSE|VS-entreprenör\w*|\w*leverantör\w*)", re.I)
SUPPLIER_NAMES = {"ee": "Elentreprenör", "be": "Byggentreprenör", "ge": "Generalentreprenör", "vse": "VS-entreprenör"}
# Armatecs artiklar heter AT och ett nummer: "Smutsfilter AT 4003A", "Backventil ... AT 1159"
ARMATEC = re.compile(r"\bAT\s?(\d{3,4}[A-Z0-9]*)")
WORK = re.compile(r"(\d+(?:[.,]\d+)?)\s*(tim|timmar|h)\b\.?", re.I)
BULLETS = {"•", "-", "–", "*", "·"}


@dataclass
class Line:
    page: int
    x: float
    y: float
    x1: float
    size: float
    bold: bool
    text: str


@dataclass
class Row:
    page: int
    y: float
    cells: list[Line]

    def text(self) -> str:
        return " ".join(c.text for c in self.cells)


@dataclass
class Heading:
    code: str
    title: str
    page: int

    @property
    def level(self) -> int:
        """AMA-kodens nivå: P 1, PR 2, PRB 3, PRB.1 4, PRB.12 5, PRB.121 6."""
        c = self.code
        if c.isdigit():
            return len(c)
        head, _, tail = c.partition(".")
        return len(head) + (len(tail) if tail else 0)


@dataclass
class Item:
    """En sak beskrivningen föreskriver: en post, ett tillbehör till en post eller en produkt kravtexten nämner."""
    id: str
    kind: str                       # post | tillbehor | omnamnd
    code: str                       # postens kod (B202B), eller tom
    name: str                       # benämning
    quantity: float | None
    unit: str
    quantity_text: str              # som det står: "1 st", "Enl. ritning"
    manufacturer: str               # normaliserat fabrikat (Furhoff), eller tomt
    manufacturer_text: str          # som det står (Furhoffs)
    type: str                       # typ/modell (FURO 142)
    rsk: list[str]
    art_nr: list[str]
    or_equal: bool                  # "eller likvärdig"
    spec: dict[str, str]
    text: str                       # postens hela text
    category: str                   # AMA-rubriken på postens fjärde nivå (Golvbrunnar)
    subcategory: str                # den närmaste rubriken (Golvbrunnar av rostfritt stål)
    ama_code: str                   # den närmaste rubrikens kod (PRB.12)
    ama_path: list[dict[str, str]]
    section: str                    # avsnittet posten står i (MATERIAL- OCH VARUKRAV), eller tomt
    page: int                       # 1-baserad
    parent: str = ""                # förälderns id för ett tillbehör
    total_quantity: float | None = None
    supplied_by: str = ""           # levereras av någon annan: Beställare, Kommunen, Markentreprenör ...
    inferred: str = ""              # vad som är härlett och inte skrivet: "fabrikat ur artikelnumret AT 4003A"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- sidan som rader

def _lines(doc: pymupdf.Document) -> list[list[Line]]:
    pages: list[list[Line]] = []
    for pn, page in enumerate(doc):
        out: list[Line] = []
        for b in page.get_text("dict").get("blocks", []):
            for ln in b.get("lines", []):
                spans = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = re.sub(r"\s+", " ", "".join(s["text"] for s in ln["spans"])).strip()
                s0 = spans[0]
                bold = bool(s0.get("flags", 0) & 16) or "bold" in (s0.get("font") or "").lower()
                x0, y0, x1, _ = ln["bbox"]
                out.append(Line(pn, round(x0, 1), round(y0, 1), round(x1, 1), round(float(s0["size"]), 1), bold, text))
        pages.append(out)
    return pages


def _repeating(pages: list[list[Line]]) -> set[tuple[str, int, int]]:
    """Sidhuvud och sidfot: samma text på samma ställe på mer än hälften av sidorna."""
    if len(pages) < 3:
        return set()
    seen = Counter()
    for lines in pages:
        for k in {(ln.text, round(ln.x / 4), round(ln.y / 4)) for ln in lines}:
            seen[k] += 1
    # sidnumret ändras från sida till sida men står på samma ställe: "2025-09-15 21 (37)"
    return {k for k, n in seen.items() if n > len(pages) / 2}


def _page_number_line(text: str) -> bool:
    return re.search(r"\b\d{1,3}\s*\(\d{1,3}\)\s*$", text) is not None or re.fullmatch(r"sida\s*\d{1,3}(\s*/\s*\d{1,3})?", text, re.I) is not None


@dataclass
class Columns:
    code_x: float           # vänsterkant för KOD
    text_x: float           # vänsterkant för TEXT
    value_x: float          # specifikationens värdekolumn
    qty_x: float            # vänsterkant för MÄNGD
    body_top: dict[int, float]


def _columns(pages: list[list[Line]], widths: list[float]) -> Columns:
    """Kolumnerna ur bladets rubrikrad KOD TEXT MÄNGD ENHET, annars ur hur raderna står."""
    code_x = text_x = qty_x = None
    body_top: dict[int, float] = {}
    for pn, lines in enumerate(pages):
        kod = [ln for ln in lines if ln.text.upper() == "KOD"]
        txt = [ln for ln in lines if ln.text.upper() == "TEXT"]
        mng = [ln for ln in lines if ln.text.upper() in ("MÄNGD", "MANGD", "ANTAL")]
        if kod and txt:
            body_top[pn] = max(kod[0].y, txt[0].y) + 6
            code_x, text_x = code_x or kod[0].x, text_x or txt[0].x
            if mng:
                qty_x = qty_x or mng[0].x
    xs = Counter(round(ln.x) for lines in pages for ln in lines if len(ln.text) > 25)
    if text_x is None:
        text_x = float(xs.most_common(1)[0][0]) if xs else 100.0
    if code_x is None:
        code_x = max(0.0, text_x - 60)
    width = max(widths) if widths else 595.0
    if qty_x is None:
        qty_x = 0.72 * width
    # en mängd står gärna lite till vänster om rubriken MÄNGD ("Enl. ritning" börjar före den)
    qty_x = min(qty_x, 0.72 * width) - 14
    # värdekolumnen: där specifikationens värden står, till höger om nyckeln
    vals = Counter(round(ln.x) for lines in pages for ln in lines if text_x + 40 < ln.x < qty_x)
    value_x = float(vals.most_common(1)[0][0]) if vals else text_x + 110
    return Columns(code_x, text_x, value_x, qty_x, body_top)


def _rows(pages: list[list[Line]], cols: Columns, drop: set) -> list[Row]:
    rows: list[Row] = []
    for pn, lines in enumerate(pages):
        top = cols.body_top.get(pn)
        if top is None and cols.body_top:
            continue                                    # en sida utan tabellen: försättsblad, innehållsförteckning
        keep = [ln for ln in lines
                if (ln.text, round(ln.x / 4), round(ln.y / 4)) not in drop
                and (top is None or ln.y >= top)
                and not DOTS.search(ln.text)
                and not _page_number_line(ln.text)]
        keep.sort(key=lambda ln: (ln.y, ln.x))
        for ln in keep:
            if rows and rows[-1].page == pn and abs(rows[-1].y - ln.y) <= 2.0:
                rows[-1].cells.append(ln)
            else:
                rows.append(Row(pn, ln.y, [ln]))
        for r in rows:
            r.cells.sort(key=lambda c: c.x)
    return rows


# ---------------------------------------------------------------- tolkning av en post

def supplied_by(text: str) -> str:
    """Vem som levererar eller utför, när det är någon annan än VS-entreprenören: "Vattenmätare levereras av
    kommunen" -> Kommunen. VS-entreprenören själv ger tomt - det är den som räknar."""
    m = SUPPLIED.search(text or "")
    if not m:
        b = re.search(r"\b(beställaren|beställare)\s+tillhandahåller\b", text or "", re.I)
        return "Beställare" if b else ""
    who = m.group(1)
    key = who.lower()
    if key in ("vse",) or key.startswith("vs-entrepren"):
        return ""
    if key in SUPPLIER_NAMES:
        return SUPPLIER_NAMES[key]
    if key.startswith("beställ"):
        return "Beställare"
    if "kommun" in key:
        return "Kommunen"
    return who[:1].upper() + who[1:].lower()


def _brand(word: str) -> str | None:
    w = (word or "").strip(" .,:;()").lower()
    if not w or w in NOT_BRANDS:
        return None
    return BRANDS.get(w)


def _clean_type(t: str) -> str:
    t = re.sub(r"\btyp\b", " ", t, flags=re.I)
    t = OR_EQUAL.split(t)[0]
    t = re.sub(r"\s+", " ", t).strip(" .,;:")
    return t


def _type_tokens(rest: str) -> str:
    """Modellen efter fabrikatet: ord med versal eller siffra, och 'eller' mellan två sådana. Den slutar vid
    första vanliga ord ("där", "för", "i vit färg") eller vid ett skiljetecken som avslutar satsen."""
    out: list[str] = []
    numbered = False
    for tok in re.split(r"\s+", rest.strip()):
        bare = tok.strip(",.;:")
        if not bare:
            break
        if bare.lower() == "typ":
            continue
        if bare.lower() == "eller" and out:
            out.append("eller")
            continue
        digit = re.search(r"\d", bare) is not None
        if numbered and not digit and not re.fullmatch(r"[A-ZÅÄÖ]{1,2}", bare) and out[-1] != "eller":
            break                               # "FURO 142 Storlek": efter modellnumret börjar texten
        if re.search(r"[A-ZÅÄÖ0-9]", bare[0]) or digit:
            out.append(bare)
            numbered = numbered or digit
            if tok.endswith((",", ".", ";", ":")):
                break                           # satsen slutar: "FURO 152. Golvtyp ..."
            continue
        break
    while out and out[-1] == "eller":
        out.pop()
    return " ".join(out)


_MAKER_TYP = re.compile(r"(?:\bav\s+)?\b[Ff]abrikat:?\s+(?P<m>[A-ZÅÄÖ][\wÅÄÖåäö&\-]*(?:\s+Electric)?)\s+(?P<t>typ\s+.+)")
_MAKER = re.compile(r"\b[Ff]abrikat:?\s+(?P<m>[A-ZÅÄÖ][\wÅÄÖåäö&\-]*(?:\s+Electric)?)\s+(?P<t>.+)")
_GENITIVE_TYP = re.compile(r"(?<![\wÅÄÖåäö])(?P<m>[A-ZÅÄÖ][\wÅÄÖåäö&\-]+)\s+typ\s+(?P<t>.+)")


def find_maker(text: str) -> tuple[str, str, str]:
    """(fabrikat normaliserat, fabrikat som det står, typ) ur en text, eller tomma strängar.

    Beskrivningen skriver fabrikatet på tre sätt: "av fabrikat Furhoffs typ FURO typ 142", "Fabrikat Armatec
    AT3700 eller AT3701" och i genitiv "IFÖs typ Cera 23220". Fabrikatet normaliseras mot en lista över kända
    varumärken; ett okänt ord före "typ" räknas bara när det står efter ordet fabrikat, så att "skyddsdon typ BA"
    och "För KV typ EA" inte blir fabrikat."""
    flat = re.sub(r"\s+", " ", text or "")
    for rx, needs_brand in ((_MAKER_TYP, False), (_MAKER, False), (_GENITIVE_TYP, True)):
        for m in rx.finditer(flat):
            raw = m.group("m")
            brand = _brand(raw) or _brand(raw.split()[0])
            if needs_brand and brand is None:
                continue
            if brand is None:
                # ett okänt fabrikat efter ordet "fabrikat": en genitivs s tas bort när ordet skrivs i versaler
                brand = raw[:-1] if re.fullmatch(r"[A-ZÅÄÖ]{2,}s", raw) else raw
            typ = _clean_type(_type_tokens(m.group("t")))
            return brand, raw, typ
    return "", "", ""


def _armatec(text: str) -> tuple[str, str, str]:
    """Armatec ur ett AT-nummer när fabrikatet inte är utskrivet: (fabrikat, typ, vad det vilar på)."""
    m = ARMATEC.search(text or "")
    if not m:
        return "", "", ""
    return "Armatec", f"AT {m.group(1)}", f"fabrikat härlett ur artikelnumret AT {m.group(1)}"


def _strip_lead(text: str) -> str:
    """Texten utan en inledande bisats om användning: "För tappvatten. Smutsfilter AT 4003A" -> Smutsfilter..."""
    parts = re.split(r"(?<=[a-zåäö])\.\s+", (text or "").strip(), maxsplit=1)
    return parts[1] if len(parts) == 2 and parts[0].lower().startswith(("för ", "till ", "i ")) else text


def _join_breaks(text: str) -> str:
    """Ett modellnummer som radbrytningen delade: "8118- 0010" -> 8118-0010."""
    return re.sub(r"(\d)-\s+(\d)", r"\1-\2", text)


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[a-zåäö0-9)])\.\s", (text or "").strip(), maxsplit=1)[0]


def _brand_in(text: str) -> tuple[str, str, str]:  # noqa: C901
    """Ett känt varumärke var som helst i en kort text, och modellen efter det: "Rensrör Wafix grå PP",
    "ettgreppsblandare FMM 9000E EcoSafe". Bara i rubriken och första meningen - längre ner i en text nämns
    fabrikat i förbigående ("kopplingstillverkarens anvisningar")."""
    words = (text or "").split()
    for i, w in enumerate(words):
        b = _brand(w)
        if b:
            n = len(b.split())
            rest = " ".join(words[i + n:]) if n > 1 and len(words) > i + 1 and words[i + 1].lower() == b.split()[-1].lower() \
                else " ".join(words[i + 1:])
            return b, w, _clean_type(_type_tokens(rest))
    return "", "", ""


def _brand_in_body(text: str) -> tuple[str, str, str]:
    """Fabrikatet längre ner i positionens text: "Värmepump mark/vatten. Thermia Atlas 12 kW, RSK 621 73 05."
    Bara i en mening som också har en modell eller ett RSK-nummer - ett fabrikat i förbigående
    ("enligt Grundfos anvisningar") är ingen förskrivning."""
    for sent in re.split(r"(?<=[.;])\s+|\n", text or ""):
        b, raw, typ = _brand_in(sent)
        if b and (rsk_find(sent) or re.search(r"\d", typ or "")) and not re.search(r"anvisning|instruktion|rekommend", sent, re.I):
            return b, raw, typ
    return "", "", ""


def _lead_name(text: str) -> str:
    """Postens benämning ur textens början: "Golvbrunn av fabrikat ..." -> Golvbrunn."""
    first = re.split(r"(?<=[a-zåäö0-9])\.\s|\.$", text.strip())[0]
    head = re.split(r"\s+(?:av\s+fabrikat|av\s+|fabrikat|typ\s|för\s|med\s|i\s+DN|DN\d|AT\s?\d|levereras|ska\s|skall\s|monteras|"
                    r"utföres|utförs|ansluts)", first, maxsplit=1, flags=re.I)[0]
    head = head.split(",")[0].strip(" ,.:;")
    words = head.split()
    for i, w in enumerate(words):
        if i and _brand(w):
            words = words[:i]                   # "Vattenutkastare FMMs typ ...": fabrikatet hör inte till namnet
            break
    head = " ".join(words)
    if not words or len(words) > 5 or words[0].lower().startswith("fabrikat"):
        return ""
    if _brand(words[0]) or words[0].lower() in ("för", "på", "i", "vid", "om"):
        return ""
    if not words[0][0].isupper():
        return ""
    return head


def _qty(text: str) -> tuple[float | None, str]:
    t = (text or "").strip()
    m = QTY.match(t.replace(" ", " "))
    if m:
        unit = (m.group(3) or "st").strip(".").lower()
        # "1-2 st": den övre gränsen, så att ett anbud inte räknar för lite; som det står följer med
        hi = m.group(2) or m.group(1)
        return float(hi.replace(",", ".")), unit
    return None, ""


def _category(path: list[Heading]) -> tuple[str, str, str]:
    """(kategori, underkategori, AMA-kod). Kategorin är rubriken på fjärde nivån - PRB.1 Golvbrunnar, PSB.1
    Kulventiler, PUC.1 Tvättställ - så att golvbrunnar av plast och av rostfritt hamnar under samma kategori.
    Finns ingen sådan rubrik är det den närmaste rubriken med punkt i koden, annars den närmaste alls."""
    if not path:
        return "Övrigt", "", ""
    deepest = path[-1]
    cat = next((h for h in path if h.level == 4 and "." in h.code), None) \
        or next((h for h in reversed(path) if "." in h.code), None) or deepest
    return _title(cat.title), _title(deepest.title), deepest.code


def _title(t: str) -> str:
    """En rubrik i versaler skrivs som en mening: SANITETSENHETER OCH SANITETSUTRUSTNINGAR -> Sanitetsenheter...
    Ett ord som står två gånger i rad skrivs en gång ("återströmningsskydd Återströmningsskydd")."""
    t = re.sub(r"\s+", " ", t).strip()
    if t.isupper():
        t = t[:1] + t[1:].lower()
    ws = t.split(" ")
    ws = [w for i, w in enumerate(ws) if i == 0 or w.lower() != ws[i - 1].lower()]
    t = " ".join(ws)
    return t[:1].upper() + t[1:]


class _Builder:
    def __init__(self, cols: Columns):
        self.cols = cols
        self.path: list[Heading] = []
        self.section = ""
        self.items: list[Item] = []
        self.cur: dict | None = None            # posten som läses
        self.loose: list[tuple[int, str]] = []  # kravtext utanför poster, för omnämnda produkter
        self.loose_path: list[list[Heading]] = []
        self.n = 0
        self.waiting: list[Item] = []           # poster utan egen text, som delar nästa posts

    # -- rubriker
    def heading(self, code: str, title: str, page: int):
        self.close()
        self.waiting = []
        h = Heading(code, title, page)
        while self.path and not (h.code.startswith(self.path[-1].code) and h.code != self.path[-1].code
                                 and h.level > self.path[-1].level):
            self.path.pop()
        self.path.append(h)
        self.section = ""

    # -- poster
    def start(self, code: str, title: str, qty_text: str, page: int):
        self.close()
        self.cur = {"code": code, "title": title, "qty_text": qty_text, "page": page, "text": [], "spec": {},
                    "spec_mode": None, "spec_key": None, "acc": [], "path": list(self.path), "section": self.section}

    def close(self):
        c = self.cur
        if c is None:
            return
        self.cur = None
        text = _join_breaks(" ".join(c["text"]).strip())
        qty, unit = _qty(c["qty_text"])
        brand, raw, typ = find_maker(" ".join([c["title"], text] + [f"{k}: {v}" for k, v in c["spec"].items()]))
        if not brand:
            in_title = _brand_in(c["title"])
            brand, raw, typ = in_title if in_title[0] else _brand_in(_first_sentence(text))
            if not brand:
                brand, raw, typ = _brand_in_body(text)
            if in_title[0]:
                # "Mitsubishi Electric RAC" och i texten "Utomhusdel typ MUZ-FT25VGHZ(-SC)": serien ur rubriken,
                # modellen ur texten
                typed = re.search(r"\btyp\s+([A-Z0-9][^\s,;]*)",
                                  " ".join([text] + [f"{k} {v}" for k, v in c["spec"].items()]), re.I)
                if typed:
                    typ = (typ + " " + typed.group(1).rstrip(".")).strip()
        if brand and " " in brand and typ.lower().startswith(brand.split(" ", 1)[1].lower()):
            typ = typ[len(brand.split(" ", 1)[1]):].strip()       # "Mitsubishi Electric RAC" -> RAC
        inferred = ""
        if not brand:
            brand, typ, inferred = _armatec(text)
            raw = ""
        cat, sub, ama = _category(c["path"])
        name = c["title"] if c["title"] and not CODE_TOKEN.match(c["title"].split()[0]) else ""
        if name and (_brand(name.split()[0]) or name.lower().startswith("fabrikat")):
            name = ""
        elif name:
            name = _lead_name(name) or name
        insul = re.search(r"isoleras\s+med\s+(.+?)(?:\.\s|\.$|$)", c["title"] + " " + text)
        if insul:
            name = insul.group(1)                       # "KV01 isoleras med diff.tät rörskål 30mm"
        name = name or _lead_name(text) or _lead_name(_strip_lead(text)) or sub or cat
        all_text = " ".join([c["title"], text] + list(c["spec"].values()))
        self.n += 1
        it = Item(id=f"p{self.n}", kind="post", code=c["code"], name=_title(name), quantity=qty, unit=unit,
                  quantity_text=c["qty_text"], manufacturer=brand, manufacturer_text=raw, type=typ,
                  rsk=rsk_find(all_text), art_nr=sorted(set(ART_NR.findall(all_text))),
                  or_equal=bool(OR_EQUAL.search(all_text)), spec=dict(c["spec"]), text=text, category=cat,
                  subcategory=sub, ama_code=ama, ama_path=[{"code": h.code, "title": _title(h.title)} for h in c["path"]],
                  section=c["section"], page=c["page"] + 1, total_quantity=qty,
                  supplied_by=supplied_by(_first_sentence(_strip_lead(text))) if not brand else "", inferred=inferred)
        self.items.append(it)
        for acc_text, page in c["acc"]:
            self._accessory(it, acc_text, page)
        for part_text, page in c.get("parts", []):
            self._accessory(it, part_text, page)
        if not text and not c["spec"] and not c["acc"]:
            self.waiting.append(it)
            return
        # Ett par rader under samma rubrik - KV01-K1 Tappkallvatten, VV01-K1 Tappvarmvatten - och sedan en text
        # för båda: "Raka koppar rör av fabrikat Geberits Mapress". Texten gäller alla rader som stod utan egen.
        for w in self.waiting:
            w.text, w.spec = it.text, dict(it.spec)
            w.manufacturer, w.manufacturer_text, w.type = w.manufacturer or it.manufacturer, \
                w.manufacturer_text or it.manufacturer_text, w.type or it.type
            w.or_equal = w.or_equal or it.or_equal
        self.waiting = []

    def _accessory(self, parent: Item, text: str, page: int):
        text = _join_breaks(re.sub(r"\s+", " ", text).strip())
        if not text:
            return
        m = LEAD_QTY.match(text)
        qty = float(m.group(1)) if m else None
        body = text[m.end():] if m else text
        body = body[:1].upper() + body[1:]
        brand, raw, typ = find_maker(body)
        if not brand:
            # "1st ettgreppsblandare FMM 9000E EcoSafe typ 8060-0000": fabrikatet mitt i benämningen
            brand, raw, typ = _brand_in(body)
        art = ART_NR.findall(body)
        if brand and not re.search(r"\d", typ or "") and art:
            typ = art[0]
        typed = re.search(r"\btyp\s+([A-Z0-9][\w\-]*)", body)
        if brand and typed and typed.group(1) not in typ:
            typ = (typ + " " + typed.group(1)).strip()   # "FMM 9000E EcoSafe typ 8060-0000"
        name = _lead_name(body)
        if not name and raw and body.startswith(raw):
            # "FMM Tvågrepps spolblandare. Art.nr ...": benämningen efter fabrikatet
            name = re.split(r"[.,]", body[len(raw):].strip())[0]
            typ = art[0] if art else ""
        inferred = ""
        if not brand:
            brand, typ, inferred = _armatec(body)
        if re.match(r"^VSE\s+lever", body, re.I):
            # "VSE leverar vattenmätarkonsol": det VS-entreprenören levererar är det som följer
            body2 = re.sub(r"^VSE\s+lever\w*\s+", "", body, flags=re.I)
            name = re.split(r"[.,]", body2)[0]
        if typed and not typ:
            typ = typed.group(1).rstrip(".")               # "Markstativ typ DP-900"
        name = name or body.split(",")[0][:60]
        self.n += 1
        total = qty * parent.quantity if qty is not None and parent.quantity is not None else qty
        self.items.append(Item(
            id=f"p{self.n}", kind="tillbehor", code=parent.code, name=_title(name[:1].upper() + name[1:]),
            quantity=qty, unit="st" if qty is not None else "", quantity_text=(m.group(0).strip() if m else ""),
            manufacturer=brand, manufacturer_text=raw, type=typ, rsk=rsk_find(body),
            art_nr=sorted(set(ART_NR.findall(body))), or_equal=bool(OR_EQUAL.search(body)), spec={}, text=body,
            category=parent.category, subcategory=parent.subcategory, ama_code=parent.ama_code,
            ama_path=parent.ama_path, section=parent.section, page=page + 1, parent=parent.id, total_quantity=total,
            supplied_by=supplied_by(body), inferred=inferred))

    def body(self, row: Row):
        cols = self.cols
        main = [c for c in row.cells if c.x < cols.qty_x]
        right = [c for c in row.cells if c.x >= cols.qty_x]
        if self.cur is None:
            t = " ".join(c.text for c in main).strip()
            if t:
                self.loose.append((row.page, t))
                self.loose_path.append(list(self.path))
            return
        c = self.cur
        first = main[0] if main else None
        txt = " ".join(x.text for x in main).strip()
        if right and not c["qty_text"]:
            # mängden kan stå på en rad i specifikationen: "Ansl. nr. / 25  1 st", "Storlek / DN XX  1-2 st"
            q = " ".join(x.text for x in right)
            if _qty(q)[0] is not None or q.lower().startswith("enl"):
                c["qty_text"] = q
        if not txt:
            return
        low = txt.lower().rstrip(":")
        if PARTS_HEAD.search(txt) and txt.endswith(":"):
            c["spec_mode"] = "parts"
            c.setdefault("parts", [])
            c["text"].append(txt)
            return
        if c["spec_mode"] == "parts":
            if first and first.text in BULLETS:
                c["parts"].append((" ".join(x.text for x in main[1:]).strip(), row.page))
                return
            if first and first.x > cols.text_x + 8 and c["parts"]:
                c["parts"][-1] = (c["parts"][-1][0] + " " + txt, c["parts"][-1][1])
                return
            c["spec_mode"] = None
        cap = re.match(r"^([A-ZÅÄÖ]{4,})\s+([A-Z0-9][A-Z0-9\-]*\d[A-Z0-9\-]*)\s*[–-]?\s*(.*)$", txt)
        if cap and c["spec_mode"] is None:
            # "MARKSTATIV DP-900 – Rostfritt markstativ med dropptråg": en del med egen modell, i texten
            c.setdefault("parts", []).append((f"{cap.group(1).capitalize()} typ {cap.group(2)}. {cap.group(3)}", row.page))
            c["text"].append(txt)
            return
        # tillbehör: "Härtill:" och sedan punktlistan
        if HERETO.match(txt):
            c["spec_mode"] = "acc"
            return
        if c["spec_mode"] == "acc":
            if first and first.text in BULLETS:
                rest = " ".join(x.text for x in main[1:]).strip()
                c["acc"].append((rest, row.page))
                return
            if first and first.x > cols.text_x + 8 and c["acc"]:
                c["acc"][-1] = (c["acc"][-1][0] + " " + txt, c["acc"][-1][1])
                return
            c["spec_mode"] = None
        # specifikation: rubriken, sedan nyckel och värde på samma rad
        if low in SPEC_HEADS and first is not None and not first.bold:
            c["spec_mode"] = "spec" if low == "specifikation" else "value"
            c["spec_key"] = None if low == "specifikation" else _title(txt.rstrip(":"))
            return
        if c["spec_mode"] == "value" and c["spec_key"]:
            c["spec"][c["spec_key"]] = txt
            c["spec_mode"] = "spec"
            c["spec_key"] = None
            return
        if c["spec_mode"] == "spec":
            keys = [x for x in main if x.x < cols.value_x - 6]
            vals = [x for x in main if x.x >= cols.value_x - 6]
            if keys and vals:
                k = " ".join(x.text for x in keys).strip().rstrip(":")
                c["spec"][_title(k)] = " ".join(x.text for x in vals).strip()
                c["spec_key"] = _title(k)
                return
            if vals and not keys and c["spec_key"]:
                c["spec"][c["spec_key"]] += " " + " ".join(x.text for x in vals).strip()
                return
            if keys and not vals and len(txt) <= 30 and not txt.endswith("."):
                c["spec_key"] = _title(txt.rstrip(":"))
                c["spec"][c["spec_key"]] = ""
                return
            c["spec_mode"] = None
        c["text"].append(txt)

    def dedupe(self):
        """Ett krav som bara upprepar en post eller en namngiven produkt tas bort: vattenmätarkonsolen som
        nämns i funktionsöversikten är samma som den under VM101."""
        named = [it.name.lower() for it in self.items if it.kind != "krav"]
        keep = []
        for it in self.items:
            if it.kind == "krav":
                n = it.name.lower()
                # samma vara, eller en precisering av den ("plastbelagda konsoler" om TS101:s konsoler) - men inte
                # ett ord i ett längre namn: oljeavskiljaren är inte "spillvatten till oljeavskiljare"
                if any(n == x or (x and x in n and len(x) > 4) for x in named):
                    continue
            keep.append(it)
        self.items = keep

    def loose_products(self):
        """Det kravtexten nämner utanför posterna. Fyra slag:

          omnamnd  en produkt med fabrikat: "föravstängningsventiler Broens typ Ballofix", "kompressor typ Kaeser
                   Premium 660/90D", "O-ringar från A-press Viton"
          krav     allmänt material utan fabrikat som entreprenaden ska ha: upphängningsdon, klammer, rörskål,
                   märkband ... - mängden står i ritningen, men det ska med i kalkylen
          arbete   tid beskrivningen anger: "Bedömd tidsåtgång: 2 tim", "Tid för utbildning och information: 2 tim"
        och för var och en vem som levererar när det inte är VS-entreprenören ("levereras av markentreprenör")."""
        seen = {(it.manufacturer, it.type.lower()) for it in self.items if it.manufacturer}
        seen_generic: set[tuple[str, str]] = set()
        paras: list[tuple[int, str, list[Heading]]] = []
        for (page, t), path in zip(self.loose, self.loose_path):
            if paras and paras[-1][2] == path and (not paras[-1][1].endswith((".", ":")) or t[:1].islower()):
                paras[-1] = (paras[-1][0], paras[-1][1] + " " + t, path)
            else:
                paras.append((page, t, path))
        for page, para, path in paras:
            cat, sub, ama = _category(path)
            ama_path = [{"code": h.code, "title": _title(h.title)} for h in path]
            for sent in re.split(r"(?<=[a-zåäö0-9)])\.\s+(?=[A-ZÅÄÖ•])|\s+•\s+|(?<=:)\s+(?=[A-ZÅÄÖ])", para):
                sent = sent.strip(" •")
                if not sent:
                    continue
                who = supplied_by(sent)
                included = re.search(r"levereras\s+med\s+([A-ZÅÄÖ]{2,}\d+)", sent)
                if included and not who:
                    who = f"Ingår i {included.group(1)}"

                def add(kind, name, brand="", raw="", typ="", qty=None, unit="", qtext="", inferred=""):
                    self.n += 1
                    self.items.append(Item(
                        id=f"p{self.n}", kind=kind, code="", name=_title(name[:1].upper() + name[1:]), quantity=qty,
                        unit=unit, quantity_text=qtext, manufacturer=brand, manufacturer_text=raw, type=typ,
                        rsk=rsk_find(sent), art_nr=sorted(set(ART_NR.findall(sent))),
                        or_equal=bool(OR_EQUAL.search(sent)), spec={}, text=sent, category=cat, subcategory=sub,
                        ama_code=ama, ama_path=ama_path, section="", page=page + 1, total_quantity=qty,
                        supplied_by=who, inferred=inferred))

                # arbete med timmar
                w = WORK.search(sent)
                if w and re.search(r"tidsåtgång|utbildning|tid för|service", sent, re.I):
                    hours = float(w.group(1).replace(",", "."))
                    label = re.split(r"[:.]", sent)[0] if re.search(r"tid för", sent, re.I) else (sub or cat)
                    add("arbete", label, qty=hours, unit="tim", qtext=w.group(0))
                    continue

                brand, raw, typ = find_maker(sent)
                inferred = ""
                if not brand:
                    m = re.search(r"\b(?:typ|från)\s+(?P<m>[A-ZÅÄÖ][\w\-]+)\s+(?P<t>[A-Z0-9][^.;,]*)", sent)
                    if m and m.group("m").lower() not in NOT_BRANDS and not re.fullmatch(r"[A-ZÅÄÖ]{1,3}", m.group("m")):
                        t = _clean_type(_type_tokens(m.group("t")))
                        if t and (re.search(r"\d", t) or m.group("m")[0].isupper()):
                            brand, raw, typ = m.group("m"), m.group("m"), t
                    elif re.search(r"\btyp\s+(?P<m>[A-ZÅÄÖ]{2,})\b", sent) and _brand(re.search(r"\btyp\s+([A-ZÅÄÖ]{2,})\b", sent).group(1)):
                        # "väggkopplingssystem för lödfria genomföringar typ FMM": fabrikatet är typen
                        raw = re.search(r"\btyp\s+([A-ZÅÄÖ]{2,})\b", sent).group(1)
                        brand, typ = _brand(raw), ""
                if not brand:
                    brand, typ, inferred = _armatec(sent)
                    raw = ""
                if brand and (brand, typ.lower()) not in seen:
                    seen.add((brand, typ.lower()))
                    before = sent.split(raw)[0] if raw else sent.split("AT ")[0]
                    words = [x for x in re.findall(r"[A-Za-zÅÄÖåäö\-]+", before) if len(x) > 3
                             and x.lower() not in ("fabrikat", "från", "levereras", "beställare", "förses", "används",
                                                   "ska", "skall", "användas", "lödfria", "genomföringar")]
                    name = (_generic_in(before) or (words[-1] if words else "") or typ)
                    add("omnamnd", name, brand, raw, typ, inferred=inferred)
                    continue
                # allmänt material
                marking = re.search(r"\bmärk|skylt", sent, re.I)
                top = path[1].code if len(path) > 1 else (path[0].code if path else "")
                for noun in _generic_all(sent):
                    if noun in SUPPLY_ONLY and not who:
                        continue                     # "tappkallvatten till högtryckstvätt": en mottagare, inte en vara
                    if marking and not re.search(r"märk|skylt|varsel", noun, re.I):
                        continue                     # "Huvudkomponent, t.ex. pump, kompressor, ska märkas"
                    key = (noun.lower(), top)
                    if key in seen_generic:
                        continue
                    seen_generic.add(key)
                    add("krav", noun)


# Allmänt material en beskrivning ställer krav på utan fabrikat. Nyckeln är ordets början (så att plural och
# sammansättningar träffar), värdet namnet det visas med.
GENERIC: dict[str, str] = {
    "upphängningsdon": "Upphängningsdon", "pendl": "Pendlar", "glidbygl": "Glidbyglar", "fixering": "Fixeringar",
    "glidstöd": "Glidstöd", "avväxlingsbalk": "Avväxlingsbalkar", "klammer": "Klammer", "plastklamm": "Plastklammor",
    "svep": "Svep", "fästdon": "Fästdon", "profiler": "Profiler för upphängning", "tätningsmassa": "Tätningsmassa",
    "fogmassa": "Fogmassa", "mellanvägg av gummi": "Mellanlägg av gummi", "avtappningsdon": "Avtappningsdon",
    "stos": "Stos", "väggbrick": "Väggbricka", "rörhylsa": "Rörhylsa", "rörskål": "Rörskål",
    "ytbeklädnad": "Ytbeklädnad", "aluminiumplåt": "Aluminiumplåt", "plastplåt": "Plastplåt",
    "märkband": "Märkband", "märkbrick": "Märkbricka", "märkskylt": "Märkskylt", "hänvisningsskylt": "Hänvisningsskylt",
    "varselmärkning": "Varselmärkning med faropiktogram", "snabbkoppling": "Snabbkoppling", "o-ring": "O-ringar",
    "konsol": "Konsoler", "vattenmätarkonsol": "Vattenmätarkonsol", "skyddslock": "Skyddslock",
    "radontätning": "Radontätning", "väggkopplingssystem": "Väggkopplingssystem",
    "föravstängningsventil": "Föravstängningsventiler", "ångbroms": "Ångbroms", "tejp": "Tejp",
    "oljeavskiljare": "Oljeavskiljare", "kompressor": "Kompressor", "högtryckstvätt": "Högtryckstvätt",
    "vattenmätare": "Vattenmätare", "flödesmätare": "Flödesmätare", "ventilrörskoppel": "Ventilrörskoppel",
    "säkerhetsventil": "Säkerhetsventil", "luftningsledning": "Luftningsledning", "isolering": "Isolering",
    "sil ": "Sil", "rensanordning": "Rensanordning",
}
# Det som oftast levereras av någon annan: med bara när texten säger vem, annars är det en mottagare i en mening
SUPPLY_ONLY = {"Kompressor", "Högtryckstvätt", "Oljeavskiljare", "Vattenmätare"}
_ADJ = re.compile(r"(förkromade|plastbelagda|förstärkta|mögelresistent|självhäftande|rostfria|diff\.täta?|"
                  r"vibrationsisolerade|provisoriska|mönsterpräglad|formpressad|erforderliga|godkända)\s+$", re.I)
_NOT_MATERIAL = re.compile(r"\b(får\s+(ej|inte)|ej\s+överisoleras|isoleras\s+ej|ska\s+inte)\b", re.I)


def _generic_all(sent: str) -> list[str]:
    if _NOT_MATERIAL.search(sent):
        return []
    low = " " + sent.lower() + " "
    out: list[str] = []
    for stem, name in GENERIC.items():
        for m in re.finditer(r"(?<![a-zåäö])" + re.escape(stem), low):
            if stem == "isolering" and not re.search(r"isolering\s+(av|med)\b", low[m.start():m.start() + 30]):
                continue                            # "isolering" som material, inte som ämne
            adj = _ADJ.search(low[:m.start()])
            label = (adj.group(1).capitalize() + " " + name.lower()) if adj and adj.group(1) not in ("erforderliga",) else name
            if label not in out and name not in out:
                out.append(label)
            break
    # det längre ordet vinner: vattenmätarkonsol före konsol och vattenmätare
    out = [x for x in out if not any(x != y and x.lower() in y.lower() for y in out)]
    return out


def _generic_in(text: str) -> str:
    g = _generic_all(text)
    return g[-1] if g else ""


def _is_section(row: Row, cols: Columns) -> bool:
    """MATERIAL- OCH VARUKRAV, UTFÖRANDEKRAV: ett avsnitt, inte en post - fetstil, versaler, inga siffror,
    ingen mängd."""
    cells = [c for c in row.cells if c.x < cols.qty_x]
    if not cells or len(cells) != len(row.cells) or not all(c.bold for c in cells):
        return False
    t = " ".join(c.text for c in cells)
    return t.isupper() and not re.search(r"\d", t) and abs(cells[0].x - cols.text_x) <= 8


def _post_start(row: Row, cols: Columns) -> tuple[str, str, str] | None:
    """(kod, rubrik, mängd) när raden öppnar en post, annars None.

    En post står i fetstil i textkolumnen. Den har en kod - bokstäver och siffror, B202B, VVB001, KV01-K1 - eller
    en mängd i mängdkolumnen ("Mitsubishi Electric RAC  2st", "TRYCKLUFTSUTTAG  4 st"). En fet rad med en kod
    och lång text är också en post: "KV01 isoleras med diff.tät rörskål 30mm" föreskriver KV01:s isolering."""
    main = [c for c in row.cells if c.x < cols.qty_x]
    right = [c for c in row.cells if c.x >= cols.qty_x]
    if not main or not main[0].bold or abs(main[0].x - cols.text_x) > 8:
        return None
    head = main[0].text.strip()
    if head in BULLETS or len(head) < 2:
        return None
    toks = head.split()
    qty_text = " ".join(c.text for c in right).strip()
    value = " ".join(c.text for c in main[1:]).strip()
    has_qty = bool(qty_text) and (_qty(qty_text)[0] is not None or qty_text.lower().startswith("enl"))
    if CODE_TOKEN.match(toks[0]):
        # också en lång rad: "KV01 isoleras med diff.tät rörskål 30mm" är isoleringens post för KV01
        return toks[0], (" ".join(toks[1:]) + (" " + value if value else "")).strip(), qty_text
    if has_qty and len(toks) <= 8:
        return "", (head + (" " + value if value else "")).strip(), qty_text
    return None


def _ama_heading(row: Row, cols: Columns) -> tuple[str, str] | None:
    left = [c for c in row.cells if c.x < cols.text_x - 12]
    if not left:
        return None
    toks = left[0].text.split()
    if not toks or not AMA_CODE.match(toks[0]):
        return None
    rest = " ".join(toks[1:] + [c.text for c in row.cells if c.x >= cols.text_x - 12 and c.x < cols.qty_x])
    return toks[0], rest.strip()


def read_tech_spec(doc: pymupdf.Document) -> dict[str, Any]:
    pages = _lines(doc)
    widths = [p.rect.width for p in doc]
    cols = _columns(pages, widths)
    drop = _repeating(pages)
    rows = _rows(pages, cols, drop)
    b = _Builder(cols)
    i = 0
    while i < len(rows):
        row = rows[i]
        ama = _ama_heading(row, cols)
        if ama:
            code, title = ama
            size = max(c.size for c in row.cells)
            # en rubrik i stor stil som fortsätter på nästa rad: "SANITETSENHETER OCH" / "SANITETSUTRUSTNINGAR"
            while i + 1 < len(rows) and rows[i + 1].page == row.page and not _ama_heading(rows[i + 1], cols) \
                    and all(abs(c.size - size) < 0.3 and c.x >= cols.text_x - 12 for c in rows[i + 1].cells) \
                    and size >= 11 and rows[i + 1].y - rows[i].y < 2.2 * size:
                title += " " + rows[i + 1].text()
                i += 1
            b.heading(code, title, row.page)
            i += 1
            continue
        if _is_section(row, cols):
            b.close()
            b.section = row.text().strip()
            i += 1
            continue
        post = _post_start(row, cols)
        if post:
            b.start(post[0], post[1], post[2], row.page)
            i += 1
            continue
        b.body(row)
        i += 1
    b.close()
    b.loose_products()
    b.dedupe()
    items = b.items
    meta = _meta(pages)
    return {"meta": meta, "items": [it.as_dict() for it in items], "stats": _stats(items),
            "columns": {"code_x": cols.code_x, "text_x": cols.text_x, "value_x": cols.value_x, "qty_x": cols.qty_x}}


def read_tech_spec_bytes(data: bytes) -> dict[str, Any]:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        out = read_tech_spec(doc)
        out["meta"]["n_pages"] = len(doc)
        return out
    finally:
        doc.close()


def _meta(pages: list[list[Line]]) -> dict[str, Any]:
    """Titeln ur försättsbladet: de största raderna på första sidan."""
    lines = pages[0] if pages else []
    big = sorted({ln.size for ln in lines}, reverse=True)
    title = [ln.text for ln in lines if big and ln.size >= big[min(1, len(big) - 1)]][:4]
    return {"title": " ".join(title)[:200]}


def _stats(items: list[Item]) -> dict[str, Any]:
    return {"items": len(items), "posts": sum(1 for i in items if i.kind == "post"),
            "accessories": sum(1 for i in items if i.kind == "tillbehor"),
            "mentioned": sum(1 for i in items if i.kind == "omnamnd"),
            "with_rsk": sum(1 for i in items if i.rsk),
            "categories": len({i.category for i in items}), "manufacturers": len({i.manufacturer for i in items if i.manufacturer})}
