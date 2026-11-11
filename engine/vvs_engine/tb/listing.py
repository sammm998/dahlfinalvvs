"""En materiallista som inte är en AMA-beskrivning: ett mejl, en textfil, ett Word-dokument, ett kalkylark, en BOM.

Underlag kommer ofta i ett mejl: "3 st cirkulationspump, Grundfos Magna3 25-60, RSK 573 24 87" - eller en rad med
produkten och fabrikatet och numret på raderna under. Allt som hör till en position läses in och kopplas till den:
en rad utan eget antal eller egen kod är en fortsättning på positionen ovanför, inte en ny.

    .eml            mejlet som det sparas ur Outlook, Apple Mail eller Gmail (text eller html)
    .txt            text, t.ex. inklistrad ur ett mejl
    .docx           styckena och tabellerna i ett Word-dokument
    .xlsx / .csv    ett kalkylark eller en BOM; rubrikraden säger vilken kolumn som är vad

Ut kommer poster i samma form som en teknisk beskrivnings (reader.Item), så att samma matchning, RSK-regler,
mejlutkast och offert gäller.
"""
from __future__ import annotations

import csv
import email
import email.policy
import html as _html
import io
import re
from typing import Any

from .reader import ART_NR, OR_EQUAL, _brand_in, _brand_in_body, _qty, find_maker, supplied_by
from .rsk import find as rsk_find

# en position börjar med en kod (PB101, RB201, Pos 12) och/eller ett antal (3 st, 12 m, 2x)
CODE = re.compile(r"^(?:pos(?:ition)?\.?\s*)?([A-ZÅÄÖ]{1,5}[- ]?\d{1,4}[A-Z]?|\d{1,3}(?:\.\d{1,2})?)[\s:.\-–)]+(?=\S)", re.I)
LEAD_QTY = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(st|stk|styck|m|meter|lm|pkt|paket|set|sats|par|x)\b\.?\s*", re.I)
TRAIL_QTY = re.compile(r"[\s,;–\-]+(\d+(?:[.,]\d+)?)\s*(st|stk|styck|m|meter|lm|pkt|paket|set|sats|par)\.?\s*$", re.I)
SIGNATURE = re.compile(r"^(med vänlig|mvh|hälsningar|best regards|kind regards|--\s*$|skickat från)", re.I)
QUOTED = re.compile(r"^(>|från:|from:|skickat:|sent:|till:|to:|ämne:|subject:|kopia:|cc:)", re.I)

HEADERS = {
    "qty": ("antal", "mängd", "st", "kvantitet", "qty", "quantity", "antal st"),
    "unit": ("enhet", "unit", "enh"),
    "name": ("benämning", "beskrivning", "artikel", "produkt", "text", "description", "artikelbenämning", "vara"),
    "maker": ("fabrikat", "tillverkare", "leverantör", "manufacturer", "märke"),
    "type": ("typ", "modell", "model", "typbeteckning"),
    "rsk": ("rsk", "rsk-nr", "rsk nr", "rsknummer", "rsk-nummer"),
    "art": ("art.nr", "artikelnummer", "art nr", "artnr", "e-nr", "lev.art.nr", "article"),
    "code": ("pos", "position", "kod", "beteckning", "littera", "id"),
}


def _col(head: str) -> str | None:
    h = re.sub(r"\s+", " ", (head or "").strip().lower().rstrip(":."))
    for key, names in HEADERS.items():
        if h in names or any(h.startswith(n + " ") for n in names):
            return key
    return None


# ---------------------------------------------------------------- filerna som text och tabeller

def _eml_text(data: bytes) -> str:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    raw = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        text = raw.decode(charset, "strict")
    except (LookupError, UnicodeDecodeError):
        text = raw.decode("utf-8", "replace") if _is_utf8(raw) else raw.decode("cp1252", "replace")
    if part.get_content_type() == "text/html":
        text = re.sub(r"(?is)<(script|style).*?</\1>", "", text)
        text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", text)
        text = re.sub(r"(?i)</t[dh]>", "\t", text)
        text = _html.unescape(re.sub(r"<[^>]+>", "", text))
    subject = str(msg.get("subject") or "")
    return (f"{subject}\n" if subject else "") + text


def _is_utf8(b: bytes) -> bool:
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _docx(data: bytes) -> tuple[str, list[list[list[str]]]]:
    import docx
    d = docx.Document(io.BytesIO(data))
    text = "\n".join(p.text for p in d.paragraphs)
    tables = [[[c.text.strip() for c in r.cells] for r in t.rows] for t in d.tables]
    return text, tables


def _xlsx(data: bytes) -> list[list[list[str]]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = [["" if v is None else str(v).strip() for v in r] for r in ws.iter_rows(values_only=True)]
        out.append([r for r in rows if any(r)])
    return out


def _csv(text: str) -> list[list[list[str]]]:
    dialect = csv.Sniffer().sniff(text[:4000], delimiters=";,\t") if text.strip() else csv.excel
    return [[r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]]


def file_content(name: str, data: bytes) -> tuple[str, list[list[list[str]]]]:
    """(löptext, tabeller) ur filen."""
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext == "eml":
        return _eml_text(data), []
    if ext == "docx":
        return _docx(data)
    if ext in ("xlsx", "xlsm"):
        return "", _xlsx(data)
    if ext == "msg":
        raise ValueError("Outlook-filer (.msg) går inte att läsa direkt. Spara mejlet som .eml (Arkiv > Spara som) "
                         "eller klistra in texten.")
    text = data.decode("utf-8-sig", "replace") if not data.startswith(b"\xff\xfe") else data.decode("utf-16")
    if ext == "csv" or (ext in ("", "txt") and text.count(";") > 3 and "\n" in text and _looks_tabular(text)):
        return "", _csv(text)
    return text, []


def _looks_tabular(text: str) -> bool:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return sum(1 for c in re.split(r"[;\t]", first) if _col(c)) >= 2


# ---------------------------------------------------------------- till poster

def _item(n: int, code: str, text: str, qty: float | None, unit: str, qty_text: str, name: str = "", maker: str = "",
          typ: str = "", rsk: list[str] | None = None, art: list[str] | None = None, source: str = "") -> dict[str, Any]:
    text = re.sub(r"\s+", " ", text).strip()
    brand, raw, found_typ = (maker, maker, typ) if maker else find_maker(text)
    if not brand:
        brand, raw, found_typ = _brand_in(text)
    if not brand:
        brand, raw, found_typ = _brand_in_body(text)
    if not name:
        name = re.split(r"[,.;](?!\d)|\s(?:fabrikat|fabr\.|typ|rsk|art\.?\s*nr)\b", text, maxsplit=1, flags=re.I)[0].strip()
        if raw and name.lower().startswith(raw.lower()):
            name = ""
        elif raw and f" {raw.lower()} " in f" {name.lower()} ":
            name = name[:name.lower().index(raw.lower())].strip()      # "Cirkulationspump Grundfos Magna3" -> Cirkulationspump
        name = name or (f"{brand} {found_typ}".strip())
    rsk = rsk if rsk is not None else rsk_find(text)
    return {"id": f"l{n}", "kind": "post", "code": code, "name": (name[:1].upper() + name[1:])[:160], "quantity": qty,
            "unit": unit or ("st" if qty is not None else ""), "quantity_text": qty_text, "manufacturer": brand,
            "manufacturer_text": raw, "type": (typ or found_typ or "")[:120], "rsk": rsk,
            "art_nr": art if art is not None else ART_NR.findall(text), "or_equal": bool(OR_EQUAL.search(text)),
            "spec": {"Källa": source} if source else {}, "text": text, "category": "Materiallista",
            "subcategory": "", "ama_code": "", "ama_path": [], "section": "", "page": 0, "parent": "",
            "total_quantity": qty, "supplied_by": supplied_by(text), "inferred": ""}


def _qty_of(text: str) -> tuple[float | None, str, str, str]:
    """(antal, enhet, som skrivet, texten utan antalet)."""
    m = LEAD_QTY.match(text)
    if m:
        unit = {"stk": "st", "styck": "st", "meter": "m", "lm": "m", "x": "st", "paket": "pkt"}.get(m.group(2).lower(),
                                                                                                  m.group(2).lower())
        return float(m.group(1).replace(",", ".")), unit, m.group(0).strip(), text[m.end():]
    m = TRAIL_QTY.search(text)
    if m:
        unit = {"stk": "st", "styck": "st", "meter": "m", "lm": "m", "paket": "pkt"}.get(m.group(2).lower(),
                                                                                         m.group(2).lower())
        return float(m.group(1).replace(",", ".")), unit, m.group(0).strip(" ,;–-"), text[:m.start()]
    return None, "", "", text


def from_text(text: str, source: str = "") -> list[dict[str, Any]]:
    """Löptext: en position per rad med kod eller antal, och raderna under den som fortsättning."""
    items: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None

    def close():
        nonlocal cur
        if cur and (cur["text"].strip()):
            items.append(_item(len(items) + 1, cur["code"], cur["text"], cur["qty"], cur["unit"], cur["qty_text"],
                               source=source))
        cur = None

    for raw in (text or "").splitlines():
        line = raw.strip(" \t•·*-–").strip()
        if not line:
            continue
        if SIGNATURE.match(line):
            break                                          # signaturen och det citerade mejlet under hör inte dit
        if QUOTED.match(line):
            if cur or items:
                break
            continue
        code = ""
        m = CODE.match(line)
        rest = line
        if m and (re.search(r"[A-Za-zÅÄÖåäö]", m.group(1)) or LEAD_QTY.match(line[m.end():])):
            code, rest = m.group(1).replace(" ", ""), line[m.end():]
        qty, unit, qty_text, body = _qty_of(rest)
        starts = bool(code) or qty is not None
        if starts:
            close()
            cur = {"code": code, "qty": qty, "unit": unit, "qty_text": qty_text, "text": body}
        elif cur is not None:
            cur["text"] += " " + line                      # fabrikat, RSK, typ på raderna under positionen
    close()
    # en rad utan något som liknar en vara (en hälsning, "Hej,") är ingen position
    return [it for it in items if it["manufacturer"] or it["rsk"] or it["art_nr"] or len(it["name"]) >= 4]


def from_table(rows: list[list[str]], source: str = "") -> list[dict[str, Any]]:
    """Ett kalkylark eller en BOM: rubrikraden säger vilken kolumn som är vad; utan rubrik läses raderna som text."""
    head_i, cols = None, {}
    for i, r in enumerate(rows[:15]):
        found = {k: j for j, c in enumerate(r) if (k := _col(str(c)))}
        if len(found) >= 2 and ("name" in found or "rsk" in found or "art" in found):
            head_i, cols = i, {}
            for j, c in enumerate(r):
                k = _col(str(c))
                if k and k not in cols:
                    cols[k] = j
            break
    if head_i is None:
        return from_text("\n".join(" ".join(c for c in r if c) for r in rows), source)
    items = []
    for r in rows[head_i + 1:]:
        get = lambda k: (str(r[cols[k]]).strip() if k in cols and cols[k] < len(r) and r[cols[k]] is not None else "")
        whole = " ".join(str(c) for c in r if str(c).strip())
        if not whole.strip():
            continue
        q_raw = get("qty")
        try:
            qty = float(q_raw.replace(",", ".").split()[0]) if q_raw else None
        except ValueError:
            qty, _ = _qty(q_raw)
        rsk = rsk_find("RSK " + get("rsk")) if get("rsk") else rsk_find(whole)
        art = [get("art")] if get("art") else ART_NR.findall(whole)
        name = get("name")
        if not (name or rsk or art or get("type")):
            continue
        text = " ".join(x for x in (name, get("maker"), get("type"), whole if not name else "") if x)
        items.append(_item(len(items) + 1, get("code"), text, qty, get("unit"), q_raw, name=name, maker=get("maker"),
                           typ=get("type"), rsk=rsk, art=art, source=source))
    return items


def read_material_list(name: str, data: bytes) -> dict[str, Any]:
    text, tables = file_content(name, data)
    items: list[dict[str, Any]] = []
    for t in tables:
        items += from_table(t, source=name)
    if text.strip():
        items += from_text(text, source=name)
    for n, it in enumerate(items, 1):
        it["id"] = f"l{n}"
    stats = {"items": len(items), "posts": len(items), "accessories": 0, "mentioned": 0,
             "with_rsk": sum(1 for i in items if i["rsk"]), "categories": 1,
             "manufacturers": len({i["manufacturer"] for i in items if i["manufacturer"]})}
    title = text.strip().splitlines()[0][:200] if name.lower().endswith(".eml") and text.strip() else name
    return {"meta": {"title": title, "n_pages": 0}, "items": items, "stats": stats}
