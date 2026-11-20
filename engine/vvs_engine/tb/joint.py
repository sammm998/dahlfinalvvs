"""Samläsning: den tekniska beskrivningen och ritningarna läses tillsammans, inte som två källor var för sig.

Ordningen är den en kalkylator följer vid AB 04:

  1  beskrivningen först   krav, produkter, AMA-koder, mängder och hänvisningar ("antal enligt ritning")
  2  ritningarna           komponentkoder och rörmeter (vvs_engine.tb.drawing_link)
  3  mängden per post      en hänvisning till ritning hämtar ritningens mängd; en mängd i beskrivningen som
                           ritningen bekräftar står kvar; säger de olika saker avgör systemet INTE vilken som
                           gäller - posten flaggas som motstridig och handlingarnas prioriteringsordning (eller
                           en människa) avgör. Samma objekt räknas en gång: ritningens antal läggs aldrig till
                           beskrivningens.
  4  spårbarhet            varje mängd säger var den kommer ifrån: beskrivningen (sida, AMA-kod), ritningen
                           (vilka blad), båda, härledd eller manuell
  5  det som inte är mängd reglerbara mängder (R20), optioner, tekniska förutsättningar, gränsdragning,
                           hänvisningar mellan kapitel, och poster där handlingen beskriver en funktion utan att
                           föreskriva en artikel

Dokumentanalysen (analyse) läser hela beskrivningens text, inte bara posterna: förutsättningar och gränsdragning
står ofta i löptext under en rubrik, inte på en materialrad.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

AMA_CODE = re.compile(r"\b([A-Z]{1,4}(?:\.\d{1,4}){1,3})\b")
BY_DRAWING = re.compile(r"\b(enl(?:\.|igt)?\s*(?:ritn(?:ing(?:ar)?)?\.?|ritn)|se\s+ritning|enl\.?\s*rit|"
                        r"antal\s+(?:enligt|enl\.?)\s+ritning|redovisas\s+på\s+ritning)", re.I)
ADJUSTABLE = re.compile(r"^\s*R\s*(\d+(?:[.,]\d+)?)\s*([A-Za-zåäö²³]{0,5})\.?\s*$")
ADJUSTABLE_TEXT = re.compile(r"reglerbar\w*\s+mängd\w*[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*([A-Za-zåäö]{0,4})", re.I)
OPTION = re.compile(r"\b(option(?:en|er|erna|s)?|optionspris|som\s+tillval|tilläggsoption)\b", re.I)


# ---------------------------------------------------------------- mängden per post

def adjustable(item: dict[str, Any]) -> dict[str, Any] | None:
    """R20 = reglerbar mängd 20: kalkylen räknar 20, och mängden regleras ekonomiskt efter verkligt utfall."""
    for t in (item.get("quantity_text") or "", ):
        m = ADJUSTABLE.match(t)
        if m:
            return {"quantity": float(m.group(1).replace(",", ".")), "unit": (m.group(2) or item.get("unit") or "st").lower(),
                    "as_written": t.strip()}
    m = ADJUSTABLE_TEXT.search(item.get("text") or "")
    if m:
        return {"quantity": float(m.group(1).replace(",", ".")), "unit": (m.group(2) or item.get("unit") or "st").lower(),
                "as_written": m.group(0).strip()}
    return None


def by_drawing(item: dict[str, Any]) -> bool:
    return bool(BY_DRAWING.search(item.get("quantity_text") or "") or
                (item.get("quantity") is None and BY_DRAWING.search(item.get("text") or "")))


def quantity(item: dict[str, Any], from_drawing: dict[str, Any] | None, priority: str = "flagga") -> dict[str, Any]:
    """Posten med sin mängd, mängdens källa och eventuell motsägelse. Ersätter att ritningen alltid gick före.

    priority: "flagga" (standard: en motsägelse avgörs inte, beskrivningens mängd står som arbetsvärde och
              posten flaggas), "beskrivning" eller "ritning" (handlingarnas prioriteringsordning i AF)."""
    out = dict(item)
    desc_q = item.get("total_quantity") if item.get("total_quantity") is not None else item.get("quantity")
    flags = list(item.get("quantity_flags") or [])
    trace = [{"kind": "beskrivning", "page": item.get("page"), "ama": item.get("ama_code"),
              "as_written": item.get("quantity_text") or ""}]
    adj = adjustable(item)
    if adj:
        desc_q = adj["quantity"]
        out["unit"] = adj["unit"] or out.get("unit")
        out["adjustable"] = adj
        flags.append(f"reglerbar mängd ({adj['as_written']}): kalkylen räknar {adj['quantity']:g}, slutlig mängd regleras")
    ref = by_drawing(item)
    out["by_drawing"] = ref
    fd = from_drawing
    if fd:
        trace.append({"kind": "ritning", "sheets": fd.get("sheets") or {}, "drawings": fd.get("drawings") or [],
                      "tag": fd.get("tag"), "system": fd.get("system")})
        out["from_drawing"] = fd
    draw_q = fd.get("quantity") if fd and (fd.get("kind") == "antal" or (fd.get("quantity") or 0) > 0) else None
    source, conflict = "saknas", None
    if ref and not adj:
        if draw_q is not None:
            out["total_quantity"], out["unit"], source = draw_q, fd["unit"], "ritning (beskrivningen hänvisar dit)"
        else:
            out["total_quantity"], source = None, "saknas"
            flags.append("beskrivningen säger 'enligt ritning' men objektet hittades inte på ritningarna - räkna för hand")
    elif desc_q is not None and draw_q is not None:
        same_unit = (fd.get("unit") or "") == (out.get("unit") or "st") or fd.get("kind") == "antal"
        if same_unit and abs(float(desc_q) - float(draw_q)) < 0.01 * max(1.0, abs(float(desc_q))):
            out["total_quantity"], source = desc_q, "beskrivning, bekräftad av ritning"
        else:
            conflict = {"beskrivning": desc_q, "ritning": draw_q, "unit_description": out.get("unit"), "unit_drawing": fd.get("unit")}
            pick = {"ritning": draw_q, "beskrivning": desc_q}.get(priority, desc_q)
            out["total_quantity"] = pick
            if fd.get("unit") and priority == "ritning":
                out["unit"] = fd["unit"]
            source = {"ritning": "ritning (prioriteringsordning)", "beskrivning": "beskrivning (prioriteringsordning)"}.get(
                priority, "beskrivning - motstridig mot ritningen")
            flags.append(f"motstridig mängd: beskrivningen {desc_q:g}, ritningen {draw_q:g} - avgörs av handlingarnas "
                         f"prioriteringsordning")
    elif desc_q is not None:
        out["total_quantity"], source = desc_q, "beskrivning"
    elif draw_q is not None:
        out["total_quantity"], out["unit"], source = draw_q, fd["unit"], "ritning (beskrivningen anger ingen mängd)"
    if adj and source in ("beskrivning", "beskrivning, bekräftad av ritning"):
        source = "beskrivning (reglerbar)"
    if item.get("quantity_override") is not None:
        out["total_quantity"], source = item["quantity_override"], "manuellt"
        trace.append({"kind": "manuellt"})
    out.update(quantity_source=source, quantity_conflict=conflict, quantity_trace=trace, quantity_flags=flags,
               quantity_from={"ritning (beskrivningen hänvisar dit)": "ritning", "manuellt": "manuellt"}.get(
                   source, "ritning" if source.startswith("ritning") else "beskrivning"),
               description_quantity=desc_q)
    return out


# ---------------------------------------------------------------- posternas övriga klasser

def is_option(item: dict[str, Any], option_codes: set[str] | None = None) -> bool:
    if OPTION.search(" ".join(str(item.get(k) or "") for k in ("name", "text", "section", "subcategory", "category"))):
        return True
    code = item.get("ama_code") or ""
    return bool(option_codes and any(_under(code, c) for c in option_codes))


def _under(code: str, parent: str) -> bool:
    """PUB.21 och PUB.211 ligger under PUB.2 (AMA lägger till siffror), 52.BC under 52."""
    return bool(code and parent) and (code == parent or code.startswith(parent if "." in parent else parent + "."))


def article_status(item: dict[str, Any]) -> str:
    """föreskriven: fabrikat, typ eller nummer står i handlingen. funktion: handlingen beskriver vad som behövs
    (automatisk toppavluftare med minikulventil) men inte vilken artikel - ett förslag måste verifieras."""
    if item.get("rsk") or item.get("art_nr") or (item.get("manufacturer") and item.get("type")):
        return "föreskriven"
    if item.get("manufacturer"):
        return "fabrikat föreskrivet, typ saknas"
    return "funktion - artikel ej föreskriven"


HEATING_CONTROL = re.compile(r"termostat|radiatorventil|rumsgivare|rumstemperatur|reglerventil|givare|styr", re.I)


def relevant_conditions(item: dict[str, Any], conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Förutsättningar som påverkar produktvalet för posten: krav på temperatur för termostater och reglering,
    tryck för ventiler och pumpar, och allt som står under postens egen AMA-kod."""
    t = " ".join(str(item.get(k) or "") for k in ("name", "category", "subcategory", "text"))
    code = item.get("ama_code") or ""
    out = []
    for c in conditions:
        if code and c.get("ama") and _under(code, c["ama"]) and c["kind"] != "övrigt":
            out.append(c)
        elif c["kind"] == "temperatur" and HEATING_CONTROL.search(t):
            out.append(c)
        elif c["kind"] == "tryck" and re.search(r"ventil|pump|kärl|säkerhet", t, re.I):
            out.append(c)
    seen, uniq = set(), []
    for c in out:
        if c["text"] not in seen:
            seen.add(c["text"])
            uniq.append(c)
    return uniq[:8]


def references(item: dict[str, Any], by_code: dict[str, str]) -> list[dict[str, str]]:
    """Hänvisningar till andra kapitel i postens text ("se PPC.61", "enligt YRC.1") och texten där."""
    own = item.get("ama_code") or ""
    out = []
    for m in AMA_CODE.finditer(item.get("text") or ""):
        c = m.group(1)
        if c == own or own.startswith(c + ".") or c in {o["code"] for o in out}:
            continue
        if c in by_code:
            out.append({"code": c, "text": by_code[c][:1500]})
    return out[:5]


def inquiry_text(item: dict[str, Any], conditions: list[dict[str, Any]] | None = None,
                 refs: list[dict[str, str]] | None = None) -> str:
    """Allt en leverantör behöver för att prissätta: hela kravtexten, hänvisade kapitel och förutsättningarna -
    inte bara KVP01 och ett antal."""
    parts = [f"{item.get('ama_code') or ''} {item.get('subcategory') or item.get('category') or ''}".strip(),
             (item.get("text") or item.get("name") or "").strip()]
    for r in refs or []:
        parts.append(f"Hänvisning {r['code']}: {r['text']}")
    if conditions:
        parts.append("Förutsättningar: " + " ".join(c["text"] for c in conditions))
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------- hela beskrivningen

UNITS = {
    "temperatur": re.compile(r"[-+]?\d+(?:[.,]\d+)?\s*°\s*C|\d+\s*grader", re.I),
    "tryck": re.compile(r"\d+(?:[.,]\d+)?\s*(?:kPa|MPa|bar|mvp)\b", re.I),
    "flöde": re.compile(r"\d+(?:[.,]\d+)?\s*(?:l/s|m3/h|m³/h|l/min)\b", re.I),
    "ljud": re.compile(r"\d+\s*dB\b", re.I),
    "effekt": re.compile(r"\d+(?:[.,]\d+)?\s*(?:kW|W/m²|W)\b"),
}
WORDS = {
    "anslutning": re.compile(r"\banslut\w*\s+(?:till|mot)\b|förbindelsepunkt|servis|kommunal\w*\s+(?:ledning|nät)", re.I),
    "dimensionering": re.compile(r"dimensioner\w+|beräknings\w+|projekteringsförutsättning", re.I),
    "system": re.compile(r"systemet\s+(?:utförs|består|är)|systembeskrivning|systemuppbyggnad", re.I),
    "orientering": re.compile(r"projektorientering|objektet\s+omfattar|entreprenaden\s+omfattar|byggnaden\s+(?:består|är|omfattar)", re.I),
}
PARTIES = [   # (namn, ord - skiftlägesokänsligt, förkortning - exakt)
    ("Byggentreprenör", r"bygg\s*entreprenör\w*|totalentreprenör\w*|generalentreprenör\w*", r"BE|GE"),
    ("Elentreprenör", r"el\s*entreprenör\w*|el\s*installatör\w*", r"EE"),
    ("Luftbehandlingsentreprenör", r"luftbehandlings\s*entreprenör\w*|ventilations\s*entreprenör\w*", r"LE"),
    ("Styrentreprenör", r"styr\s*entreprenör\w*|automations\s*entreprenör\w*", r"SE|SÖE"),
    ("Markentreprenör", r"mark\s*entreprenör\w*", r"ME"),
    ("Sprinklerentreprenör", r"sprinkler\s*entreprenör\w*", r"SPE"),
    ("Kylentreprenör", r"kyl\s*entreprenör\w*", r"KE"),
    ("Beställaren", r"beställare\w*|byggherre\w*", r"BH|BS"),
    ("Hyresgästen", r"hyresgäst\w*", r"HG"),
    ("Kommunen", r"kommun\w*|ledningsägare\w*|nätägare\w*", None),
    ("Prefab-/stomleverantör", r"prefab\w*|stomleverantör\w*|stomentreprenör\w*", None),
    ("Denna entreprenör", r"VS[- ]?entreprenör\w*|rörentreprenör\w*|denna\s+entreprenör\w*|sidoentreprenör\w*", r"UE|VSE"),
]
ACTS = [("levereras", r"levereras|tillhandahålls|anskaffas|levererad"),
        ("monteras", r"monteras|installeras|placeras|uppsätts|sätts upp"),
        ("ansluts", r"ansluts|inkopplas|kopplas\s+in|anslutning\s+utförs|inkoppling\s+utförs"),
        ("utförs", r"utförs|ombesörjs|åligger")]
NOT_INCLUDED = re.compile(r"ingår\s+(?:ej|inte)|ingår\s+ej\s+i\s+(?:denna|VS)|utgår\s+ur\s+entreprenaden|ej\s+i\s+entreprenaden", re.I)


def _party(text: str) -> str | None:
    for name, words, abbr in PARTIES:
        if re.search(rf"\b(?:{words})", text, re.I) or (abbr and re.search(rf"\b(?:{abbr})\b", text)):
            return name
    return None


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÅÄÖ0-9])", text) if len(s.strip()) > 8]


def _subject(sent: str, verb_at: int) -> str:
    head = sent[:verb_at].strip(" ,:;-")
    head = re.sub(r"^(?:och|samt|men|där|som|för|av)\s+", "", head, flags=re.I)
    words = head.split()
    return " ".join(words[-8:]) if words else ""


def contract_form(text: str) -> dict[str, Any]:
    """AB 04 eller ABT 06 ur handlingarna: hur många gånger varje form nämns, och var. Ett förslag - projektets
    val står kvar tills någon ändrar det."""
    ab = len(re.findall(r"\bAB\s*0?4\b", text))
    abt = len(re.findall(r"\bABT\s*0?6\b", text))
    guess = "ABT06" if abt > ab else ("AB04" if ab > abt else None)
    return {"AB04": ab, "ABT06": abt, "guess": guess,
            "sure": bool(guess) and min(ab, abt) == 0 and max(ab, abt) >= 1}


def blocks_of(doc) -> list[dict[str, Any]]:
    """Beskrivningens text i block: en AMA-rubrik (kod och titel) och texten under den, per sida. Läses med samma
    kolumner och samma rubrikregel som posterna (reader), utan sidhuvud och sidfot."""
    from .reader import _ama_heading, _columns, _lines, _repeating, _rows
    pages = _lines(doc)
    cols = _columns(pages, [p.rect.width for p in doc])
    rows = _rows(pages, cols, _repeating(pages))
    blocks: list[dict[str, Any]] = []
    code, title = "", ""
    for row in rows:
        h = _ama_heading(row, cols)
        if h:
            code, title = h[0], h[1]
            blocks.append({"code": code, "title": title, "page": row.page + 1, "text": ""})
            continue
        if not blocks or blocks[-1]["page"] != row.page + 1:
            blocks.append({"code": code, "title": title, "page": row.page + 1, "text": ""})
        blocks[-1]["text"] += " " + row.text()
    return blocks


def analyse(blocks: list[dict[str, Any]], items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Hela beskrivningens text (blocks_of): förutsättningar, gränsdragning, optioner, kapiteltexter och
    entreprenadform."""
    full = " ".join(b["text"] for b in blocks)
    conditions, boundaries, options = [], [], []
    by_code: dict[str, str] = defaultdict(str)
    for b in blocks:
        if b["code"]:
            by_code[b["code"]] += (" " + b["text"]).strip()[:4000]
        for s in _sentences(b["text"]):
            kinds = [k for k, rx in UNITS.items() if rx.search(s)] + [k for k, rx in WORDS.items() if rx.search(s)]
            if kinds and len(s) < 600:
                conditions.append({"kind": kinds[0], "kinds": kinds, "text": s, "ama": b["code"], "title": b["title"],
                                   "page": b["page"],
                                   "values": [v.group(0) for k in kinds if k in UNITS for v in UNITS[k].finditer(s)][:6],
                                   "requirement": bool(re.search(r"\b(minst|lägst|högst|max\w*|min\.|ska|skall|får\s+inte)\b", s, re.I))})
            acts = [(a, re.search(rf"\b(?:{p})\b(?:\s+(?:och|samt)\s+\w+)?\s+(?:av|genom|via)\s+([^.;:]+)", s, re.I)) for a, p in ACTS]
            acts = [(a, m) for a, m in acts if m]
            if acts or NOT_INCLUDED.search(s):
                row: dict[str, Any] = {"object": "", "levereras": None, "monteras": None, "ansluts": None, "utförs": None,
                                       "ingår_ej": bool(NOT_INCLUDED.search(s)), "text": s[:500], "ama": b["code"], "page": b["page"]}
                for a, m in acts:
                    row[a] = _party(m.group(1)) or m.group(1).strip()[:60]
                    subj = _subject(s, m.start())
                    if re.match(r"^(?:levereras|monteras|ansluts|installeras|tillhandahålls|och)\b", subj, re.I) or not subj:
                        subj = b["title"] or subj                 # "Levereras och monteras av ..." - rubriken är objektet
                    row["object"] = row["object"] or subj
                if not row["object"]:
                    nm = NOT_INCLUDED.search(s)
                    row["object"] = _subject(s, nm.start()) if nm else ""
                if row["object"] and len(row["object"]) > 2:
                    boundaries.append(row)
            if OPTION.search(s):
                options.append({"text": s[:500], "ama": b["code"], "title": b["title"], "page": b["page"]})
    option_codes = {o["ama"] for o in options if o["ama"] and OPTION.search(o.get("title") or "")}
    return {"contract": contract_form(full), "conditions": conditions[:400], "boundaries": boundaries[:400],
            "options": options[:200], "option_codes": sorted(option_codes), "by_code": dict(by_code)}


def boundary_list(boundaries: list[dict[str, Any]], items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Gränsdragningslistan: objekt → levereras av → monteras av → ansluts av → källa. Det handlingen inte säger
    står tomt, inte gissat. Poster som levereras av någon annan (reader.supplied_by) kommer med."""
    acc: dict[str, dict[str, Any]] = {}
    for b in boundaries:
        key = re.sub(r"\s+", " ", b["object"].lower()).strip()[:80]
        r = acc.setdefault(key, {"object": b["object"], "levereras_av": None, "monteras_av": None, "ansluts_av": None,
                                 "utförs_av": None, "ingår_ej": False, "sources": []})
        for a in ("levereras", "monteras", "ansluts", "utförs"):
            if b.get(a) and not r[f"{a}_av"]:
                r[f"{a}_av"] = b[a]
        r["ingår_ej"] = r["ingår_ej"] or b.get("ingår_ej")
        r["sources"].append({"ama": b.get("ama"), "page": b.get("page"), "text": b.get("text")})
    for it in items or []:
        if it.get("supplied_by"):
            key = (it.get("name") or "").lower()[:80]
            r = acc.setdefault(key, {"object": it.get("name"), "levereras_av": it["supplied_by"], "monteras_av": None,
                                     "ansluts_av": None, "utförs_av": None, "ingår_ej": False, "sources": []})
            r["levereras_av"] = r["levereras_av"] or it["supplied_by"]
            r["sources"].append({"ama": it.get("ama_code"), "page": it.get("page"), "text": (it.get("text") or "")[:300]})
    return sorted(acc.values(), key=lambda r: (r["sources"][0].get("page") or 0) if r["sources"] else 0)
