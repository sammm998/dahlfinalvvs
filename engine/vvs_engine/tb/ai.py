"""AI-kontroll av en läst teknisk beskrivning: vad läsaren kan ha missat, och vilken katalograd en post är.

Läsaren (reader.py) tar posterna ur AMA-tabellen och hittar aldrig på ett antal. Den här modulen låter en
språkmodell titta på två saker läsaren inte kan avgöra själv - och gör det så billigt som möjligt:

  missat   rader i beskrivningen som inte blev en post men nämner en produkt (fabrikat, typ, RSK, modellnummer).
           Bara de raderna skickas, numrerade, och svaret är radnummer plus vad raden nämner. Ett svar godtas bara
           om det modellen säger faktiskt står på raden: ett fabrikat, en typ eller ett RSK-nummer som inte finns i
           texten kastas.
  val      poster där matchningen har flera kandidater i Dahls katalog (samma serie i flera storlekar, liknande
           varor). Modellen får posten i en rad och kandidaterna numrerade, och svarar med ett nummer. Den kan bara
           välja bland riktiga katalograder - ett RSK-nummer kan aldrig hittas på.

Ingenting här ändrar ett antal eller en post. Missade produkter är förslag som en människa godkänner, och ett val
är ett förslag i RSK-kolumnen.

Modulen vet inget om leverantören: `ask(instruktioner, indata, schema)` returnerar svaret som en dict. Tjänsten
(backend/app/tb_ai.py) står för anropet, cachen och kostnaden.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .reader import BRANDS, NOT_BRANDS, _lines, _repeating

VERSION = "tb-ai-1"
Ask = Callable[[str, str, dict], dict]

MISSED_BATCH_CHARS = 6000       # rader per anrop: stort nog för få anrop, litet nog för ett kort svar
PICK_BATCH = 20                 # poster per anrop
MAX_CANDIDATES = 8

MISSED_INSTRUCTIONS = """Du granskar en teknisk beskrivning för VVS (AMA). Du får numrerade rader som INTE blivit
materialposter. Lista varje produkt som ska köpas och som en rad nämner med fabrikat, typ/modell, RSK-nummer eller
artikelnummer. Hoppa över: krav och utförande, arbete, sådant som levereras av någon annan, allmänna ord utan
fabrikat eller modell, och produkter som bara nämns som exempel på något som inte ska användas.
Skriv fabrikat, typ och RSK exakt som de står på raden. Hitta aldrig på något. Svara bara med JSON enligt schemat;
en tom lista om inget ska köpas."""

MISSED_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["found"],
    "properties": {"found": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["line", "name", "manufacturer", "type", "rsk"],
        "properties": {"line": {"type": "integer"}, "name": {"type": "string"}, "manufacturer": {"type": "string"},
                       "type": {"type": "string"}, "rsk": {"type": "string"}}}}}}

PICK_INSTRUCTIONS = """Du väljer artikel i Dahls produktkatalog för poster i en teknisk beskrivning för VVS.
Varje post har numrerade kandidater. Välj den kandidat som är exakt den vara posten föreskriver: rätt fabrikat,
serie, typ, storlek/dimension och material. Svara c = -1 om ingen kandidat stämmer, eller om posten inte säger
vilken storlek eller variant det ska vara. sure = true bara när posten entydigt pekar ut kandidaten.
Svara bara med JSON enligt schemat, en rad per post."""

PICK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["picks"],
    "properties": {"picks": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["i", "c", "sure"],
        "properties": {"i": {"type": "integer"}, "c": {"type": "integer"}, "sure": {"type": "boolean"}}}}}}

# en rad som nämner en produkt: ett känt fabrikat, ett fabrikatord, ett RSK- eller artikelnummer, eller ett
# modellnummer (FURO 142, AT 4003A, S600017)
WORDS = re.compile(r"\b(fabrikat|fabr\.|typ|modell|el\.?\s*likv|eller\s+likvärd|rsk|art\.?\s*nr)\b|\b\d{7}\b", re.I)
MODEL = re.compile(r"\b([A-ZÅÄÖ]{1,6})[- ]?(\d{2,}[A-Z0-9]*)\b")
# standarder, system- och ritningskoder är inga modellnummer: EN 997, SS 741, KIFS 2001, KV01, W-50, DN25
NOT_MODELS = {"EN", "ISO", "SS", "KIFS", "AFS", "BBR", "ELSÄK", "FS", "AMA", "DN", "W", "S", "KV", "VV", "VVC", "PN",
              "SN", "VS", "VVS", "BKR", "SFS", "IEC", "NS", "SP", "RAL", "IP", "V"}


def _signal(t: str) -> bool:
    if WORDS.search(t):
        return True
    return any(m.group(1).upper() not in NOT_MODELS for m in MODEL.finditer(t))


def _norm(t: str) -> str:
    return re.sub(r"[^0-9a-zåäöéü]+", " ", (t or "").lower()).strip()


def _squash(t: str) -> str:
    return re.sub(r"[^0-9a-zåäöéü]+", "", (t or "").lower())


def _has_brand(text: str) -> bool:
    return any((w in BRANDS and w not in NOT_BRANDS) for w in _norm(text).split())


# ---------------------------------------------------------------- missat

def residual_lines(doc, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Raderna som nämner en produkt men inte står i någon post: det enda modellen behöver läsa."""
    pages = _lines(doc)
    drop = _repeating(pages)
    by_page: dict[int, str] = {}
    words_on: dict[int, set] = {}
    for it in items:
        p = int(it.get("page") or 0) - 1
        blob = " ".join(str(it.get(k) or "") for k in ("name", "text", "type", "manufacturer", "manufacturer_text",
                                                        "quantity_text"))
        blob += " " + " ".join(f"{k} {v}" for k, v in (it.get("spec") or {}).items())
        for q in (p - 1, p, p + 1):
            by_page[q] = by_page.get(q, "") + " " + _squash(blob)
            words_on.setdefault(q, set()).update(w for w in _norm(blob).split() if len(w) >= 3)
    out = []
    for pn, lines in enumerate(pages):
        covered = by_page.get(pn, "")
        kept = [ln for ln in lines if (ln.text, round(ln.x / 4), round(ln.y / 4)) not in drop]
        for k, ln in enumerate(kept):
            t = ln.text.strip()
            if len(t) < 6 or not (_signal(t) or _has_brand(t)):
                continue
            if not re.search(r"[a-zåäö]{4,}", t, re.I):
                continue                                   # en ren systemkod (KV01-K1, S01-P2) är ingen produkt
            sq = _squash(t)
            if len(sq) < 5 or sq in covered:
                continue
            # raden står redan i en post med andra radbrytningar eller utan sitt antal: dess ord finns där
            ws = [w for w in _norm(t).split() if len(w) >= 3]
            known = words_on.get(pn, set())
            if ws and sum(w in known for w in ws) >= 0.75 * len(ws):
                continue
            # en produkt bryts ofta över två rader ("konsoler typ skolmodell med" / "dold infästning"): nästa rad
            # följer med som sammanhang
            nxt = kept[k + 1].text.strip() if k + 1 < len(kept) else ""
            out.append({"page": pn + 1, "text": (t + (" / " + nxt[:120] if nxt else ""))[:400]})
    return out


def missed_batches(lines: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Raderna numrerade och delade i anrop: (första radens index, indata)."""
    batches, cur, start, size = [], [], 0, 0
    for i, ln in enumerate(lines):
        row = f"{i + 1}|s{ln['page']}|{ln['text']}"
        if cur and size + len(row) > MISSED_BATCH_CHARS:
            batches.append((start, "\n".join(cur)))
            cur, start, size = [], i, 0
        cur.append(row)
        size += len(row) + 1
    if cur:
        batches.append((start, "\n".join(cur)))
    return batches


def _on_line(value: str, line: str) -> bool:
    v = _squash(value)
    return not v or v in _squash(line)


def accept_missed(found: list[dict[str, Any]], lines: list[dict[str, Any]],
                  items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Det modellen sade, kontrollerat mot raden: står fabrikat, typ och RSK inte på raden kastas svaret."""
    have = {(_squash(it.get("manufacturer")), _squash(it.get("type"))) for it in items if it.get("type")}
    have_rsk = {r for it in items for r in it.get("rsk") or []}
    out, seen = [], set()
    for f in found or []:
        try:
            n = int(f.get("line"))
        except (TypeError, ValueError):
            continue
        if not 1 <= n <= len(lines):
            continue
        line = lines[n - 1]
        maker, typ = (f.get("manufacturer") or "").strip(), (f.get("type") or "").strip()
        rsk = re.sub(r"\D", "", f.get("rsk") or "")
        if rsk and (len(rsk) != 7 or rsk not in re.sub(r"\D", " ", line["text"]).split()):
            rsk = ""                                       # ett nummer som inte står på raden är inget nummer
        if not _on_line(maker, line["text"]) or not _on_line(typ, line["text"]):
            continue
        if not (maker or typ or rsk):
            continue
        key = (_squash(maker), _squash(typ), rsk)
        if key in seen or (key[:2] in have and key[1]) or (rsk and rsk in have_rsk):
            continue
        if _already_a_post(maker, typ, line["page"], items):
            continue
        seen.add(key)
        from .reader import _brand
        out.append({"line": n, "page": line["page"], "line_text": line["text"],
                    "name": (f.get("name") or typ or maker)[:120].strip(),
                    "manufacturer": _brand(maker.split()[0]) or maker if maker else "",
                    "manufacturer_text": maker, "type": typ[:80], "rsk": rsk})
    return out


def _already_a_post(maker: str, typ: str, page: int, items: list[dict[str, Any]]) -> bool:
    """Samma fabrikat på samma sida, och typen ingår i postens typ ("RAC" i "RAC MUZ-FT25VGHZ"): redan en post."""
    m, t = _squash(maker), _squash(typ)
    if not m:
        return False
    for it in items:
        if abs(int(it.get("page") or 0) - page) > 1:
            continue
        im = _squash(it.get("manufacturer") or it.get("manufacturer_text") or "")
        if im and (im.startswith(m) or m.startswith(im)) and (not t or t in _squash(it.get("type") or "")):
            return True
    return False


def find_missed(doc, items: list[dict[str, Any]], ask: Ask) -> dict[str, Any]:
    lines = residual_lines(doc, items)
    found: list[dict[str, Any]] = []
    calls = 0
    for _, payload in missed_batches(lines):
        calls += 1
        r = ask(MISSED_INSTRUCTIONS, payload, MISSED_SCHEMA) or {}
        found += r.get("found") or []
    return {"lines_sent": len(lines), "calls": calls, "missed": accept_missed(found, lines, items)}


# ---------------------------------------------------------------- val i katalogen

def _candidates(match: dict[str, Any]) -> list[dict[str, str]]:
    out, seen = [], set()
    for h in match.get("hits") or []:
        if h.get("ref") and h["ref"] not in seen:
            seen.add(h["ref"])
            out.append({"ref": h["ref"], "name": h.get("name") or ""})
    for v in ((match.get("rsk") or {}).get("variants") or []):
        if v.get("rsk") and v["rsk"] not in seen:
            seen.add(v["rsk"])
            out.append({"ref": v["rsk"], "name": v.get("name") or ""})
    return out[:MAX_CANDIDATES]


def needs_pick(it: dict[str, Any]) -> bool:
    """Bara där läsaren inte kan avgöra: en möjlig träff med flera kandidater, eller en vara i flera storlekar."""
    m = it.get("match") or {}
    if m.get("status") != "möjlig" or it.get("rsk"):
        return False
    r = m.get("rsk") or {}
    if r.get("kind") == "förslag" and not r.get("alternatives") and len(m.get("hits") or []) < 2:
        return False
    return len(_candidates(m)) >= 2


def _post_line(it: dict[str, Any]) -> str:
    spec = "; ".join(f"{k} {v}" for k, v in (it.get("spec") or {}).items() if v)
    text = re.sub(r"\s+", " ", it.get("text") or "")[:220]
    parts = [it.get("name") or "", " ".join(x for x in (it.get("manufacturer"), it.get("type")) if x), spec, text]
    return " | ".join(p for p in parts if p)


def pick_batches(items: list[dict[str, Any]]) -> list[tuple[list[dict[str, Any]], str]]:
    todo = [it for it in items if needs_pick(it)]
    out = []
    for k in range(0, len(todo), PICK_BATCH):
        chunk = todo[k:k + PICK_BATCH]
        rows = []
        for i, it in enumerate(chunk):
            rows.append(f"P{i}: {_post_line(it)}")
            rows += [f"  {j}: {c['ref']} {c['name'][:90]}" for j, c in enumerate(_candidates(it['match']))]
        out.append((chunk, "\n".join(rows)))
    return out


def find_picks(items: list[dict[str, Any]], ask: Ask) -> dict[str, Any]:
    picks: dict[str, dict[str, Any]] = {}
    calls = asked = 0
    for chunk, payload in pick_batches(items):
        calls += 1
        asked += len(chunk)
        r = ask(PICK_INSTRUCTIONS, payload, PICK_SCHEMA) or {}
        for p in r.get("picks") or []:
            try:
                i, c = int(p.get("i")), int(p.get("c"))
            except (TypeError, ValueError):
                continue
            if not 0 <= i < len(chunk):
                continue
            cands = _candidates(chunk[i]["match"])
            if not 0 <= c < len(cands):
                continue                                 # -1 eller ett nummer utanför listan: inget val
            picks[chunk[i]["id"]] = {**cands[c], "sure": bool(p.get("sure"))}
    return {"asked": asked, "calls": calls, "picks": picks}
