"""Radiatorkorsning mot Altech enligt Golden Standard (Dahl Radiator- och korsreferensagent v1.0).

Deterministisk motor, ingen AI i besluten:
* samma typ + höjd + längd, annars närmaste KORTARE längd i samma typ och höjd
* original H200 -> Altech Konvektor H200 av samma typ (exakt eller närmast kortare) + väggkonsol
* aldrig längre, annan höjd eller annan typ utan uttrycklig projektöverstyrning med godkännare
* V -> vänster-RSK, H -> höger-RSK, vändbar -> gemensamt RSK; okänd riktning där H/V krävs -> E005
* effekt jämförs bara inom samma temperaturprogram, ingen omräkning
* konsolrad direkt under konvektorraden; Ant = par per konvektor (inte gånger antal konvektorer)
"""
from __future__ import annotations

import io
import json
import math
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

RULE_VERSION = "golden-standard-1.0"
PROGRAM = "55/45/20"

DEVIATIONS = {
    "E001": "RSK_MISSING",
    "E002": "PRODUCT_NOT_FOUND",
    "E003": "TYPE_NOT_VERIFIED",
    "E004": "DIMENSION_NOT_VERIFIED",
    "E005": "ORIENTATION_UNKNOWN",
    "E006": "TEMPERATURE_REGIME_MISMATCH",
    "E007": "POWER_MISSING",
    "E008": "SOURCE_CONFLICT",
    "E009": "DUPLICATE_SOURCE_ROW",
    "E010": "ACCESSORY_CLASSIFICATION_UNCERTAIN",
}
DEVIATION_SV = {
    "E001": "RSK saknas",
    "E002": "Ingen Altech-produkt i samma typ och höjd (eller kortare längd)",
    "E003": "Typen kunde inte verifieras",
    "E004": "Måtten kunde inte verifieras",
    "E005": "Höger/vänster okänd men Altech har separata H/V-artiklar",
    "E006": "Effekten finns inte i samma temperaturprogram, differens lämnas tom",
    "E007": "Effekt saknas",
    "E008": "Källuppgift motsäger masterregistret",
    "E009": "Dubblerad källrad",
    "E010": "Osäker klassning radiator/tillbehör",
}
MATCH_SV = {
    "EXACT_MATCH": "Exakt mått",
    "NEAREST_SHORTER": "Närmaste kortare",
    "H200_EXACT": "Altech Konvektor H200 - exakt mått",
    "H200_NEAREST_SHORTER": "Altech Konvektor H200 - närmaste kortare",
    "OVERRIDE": "Projektöverstyrning (godkänd)",
    "NO_MATCH": "Ingen träff",
}
VALID_TYPES = {11, 21, 22, 33}
SEPARATE_HV_TYPES = {11, 33}
ACCESSORY_WORDS = ("termostat", "ventil", "konsol", "tillb", "handduk", "givare", "luftskruv", "koppling", "rör")


@lru_cache(maxsize=1)
def register() -> dict[str, Any]:
    return json.loads((Path(__file__).with_name("golden_register.json")).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- tolkning

_G40 = re.compile(r"\bGRAD(?:[- ]?IN)?\s*(?:G?40)?\s*(?:(V|H)\s+)?(\d{2})\s*[- ]\s*(\d)(\d{2})\b", re.I)
_TP = re.compile(r"\bTP\s*(\d{2})\s*(?:(V|H)\s+)?V4\s*[- ]\s*(\d)(\d{2})\b", re.I)
_GENERIC = re.compile(r"(?:^|\s)(?:(V|H)\s+)?(\d{2})\s*[- ]\s*(\d)(\d{2})(?:\s+(V|H))?\b")
_ALTECH = re.compile(r"\b[DK](\d{2})\s*[- ]\s*(\d{3})\s*[- ]\s*(\d{3,4})\b", re.I)


def parse_code(text: str) -> dict[str, Any] | None:
    """Tolkar en modellkod. Returnerar typ, höjd, längd, riktning (V/H/None) och familj."""
    t = " " + str(text or "").strip() + " "
    m = _G40.search(t)
    if m:
        o, ty, h, ll = m.groups()
        return {"family": "Grad-IN G40", "model": f"{ty}-{h}{ll}", "type": int(ty), "height": int(h) * 100,
                "length": int(ll) * 100, "orientation": (o or "").upper() or None}
    m = _TP.search(t)
    if m:
        ty, o, h, ll = m.groups()
        return {"family": "Thermopanel V4", "model": f"TP {ty} V4-{h}{ll}", "type": int(ty), "height": int(h) * 100,
                "length": int(ll) * 100, "orientation": (o or "").upper() or None}
    m = _ALTECH.search(t)
    if m:
        ty, h, ll = m.groups()
        return {"family": "Altech", "model": m.group(0).strip(), "type": int(ty), "height": int(h),
                "length": int(ll), "orientation": None}
    m = _GENERIC.search(t)
    if m:
        o1, ty, h, ll, o2 = m.groups()
        return {"family": "Okänt fabrikat", "model": f"{ty}-{h}{ll}", "type": int(ty), "height": int(h) * 100,
                "length": int(ll) * 100, "orientation": ((o1 or o2) or "").upper() or None}
    return None


def classify(text: str) -> str:
    """'radiator', 'accessory' eller 'uncertain'."""
    low = str(text or "").lower()
    code = parse_code(text)
    accessory = any(w in low for w in ACCESSORY_WORDS)
    if code and not accessory:
        return "radiator"
    if accessory and not code:
        return "accessory"
    if code and accessory:
        return "uncertain"
    return "uncertain" if re.search(r"rad|konvekt|panel", low) else "accessory"


def original_power(code: dict[str, Any], program: str = PROGRAM, reg: dict | None = None) -> float | None:
    reg = reg or register()
    for o in reg.get("originals", {}).get(code["family"], []):
        if o["model"] == code["model"] or (o["type"], o["height"], o["length"]) == (code["type"], code["height"], code["length"]):
            return o.get("power", {}).get(program)
    return None


# ---------------------------------------------------------------- matchning

def _family_for(height: int) -> str:
    return "Altech Konvektor H200" if height == 200 else "Altech Typ D"


def candidates(ty: int, height: int, reg: dict | None = None) -> list[dict[str, Any]]:
    reg = reg or register()
    fam = _family_for(height)
    return sorted((p for p in reg["altech"] if p["family"] == fam and p["type"] == ty and p["height"] == height
                   and p.get("status", "VERIFIED") == "VERIFIED"), key=lambda p: p["length"])


def select(ty: int, height: int, length: int, reg: dict | None = None) -> tuple[dict | None, str]:
    c = candidates(ty, height, reg)
    exact = [p for p in c if p["length"] == length]
    h200 = height == 200
    if exact:
        return exact[0], "H200_EXACT" if h200 else "EXACT_MATCH"
    shorter = [p for p in c if p["length"] < length]
    if shorter:
        return shorter[-1], "H200_NEAREST_SHORTER" if h200 else "NEAREST_SHORTER"
    return None, "NO_MATCH"


def pick_rsk(p: dict[str, Any], orientation: str | None) -> tuple[str | None, str | None]:
    """Returnerar (rsk, felkod)."""
    if p.get("orientation") == "reversible" or p.get("rsk_common"):
        rsk = p.get("rsk_common") or p.get("rsk_right")
        return (str(rsk), None) if rsk else (None, "E001")
    if orientation == "V":
        rsk = p.get("rsk_left")
    elif orientation == "H":
        rsk = p.get("rsk_right")
    else:
        return None, "E005"
    return (str(rsk), None) if rsk else (None, "E001")


def brackets(length_mm: int) -> tuple[int, float]:
    """(fysiska konsoler per konvektor, par per konvektor = Prixel Ant)."""
    phys = max(2, math.ceil(length_mm / 600))
    return phys, phys / 2


def _override_product(ov: dict | None, reg: dict) -> tuple[dict | None, str | None]:
    if not ov:
        return None, None
    if not str(ov.get("approved_by") or "").strip():
        return None, "Överstyrning saknar godkännare - vägras, standardregeln används"
    rsk = str(ov.get("rsk") or "")
    for p in reg["altech"]:
        if rsk in {p.get("rsk_right"), p.get("rsk_left"), p.get("rsk_common")}:
            return p, None
    return None, f"Överstyrning till okänt RSK {rsk} - vägras"


def cross_row(row: dict[str, Any], reg: dict | None = None, program: str = PROGRAM) -> dict[str, Any]:
    """Korsar en källrad. row: id, text, qty, location, power (valfri), program (valfri), override (valfri)."""
    reg = reg or register()
    text = str(row.get("text") or "")
    qty = row.get("qty") or 0
    given = row.get("code")
    out: dict[str, Any] = {
        "id": row.get("id"), "source_text": text, "qty": qty, "location": row.get("location") or "",
        "article": row.get("article") or "", "rule_version": RULE_VERSION, "deviations": [], "notes": [],
        "selected": None, "rsk": None, "match_status": "NO_MATCH", "technical_comparison_status": "NOT_APPLICABLE",
        "approval_status": "MANUAL_REVIEW", "length_diff_mm": None, "power_diff_w": None, "power_diff_pct": None,
        "bracket": None, "category": "radiator" if given else classify(text),
    }
    if "code" in row and not given:
        out["category"] = "radiator"
        out["deviations"].append("E002")
        out["notes"].append("Ingår inte i det fasta Altech-registret (t.ex. kompaktradiator) - manuell korsning")
        return out
    if out["category"] == "accessory":
        out["approval_status"] = "EXCLUDED_ACCESSORY"
        return out
    if out["category"] == "uncertain":
        out["deviations"].append("E010")
        if not parse_code(text):
            return out
    code = dict(given) if given else parse_code(text)
    if not code:
        out["deviations"].append("E002")
        return out
    code.setdefault("family", "Okänt fabrikat")
    code.setdefault("model", text)
    code.setdefault("orientation", None)
    out["original"] = code
    orientation = (row.get("orientation") or code["orientation"] or "").upper() or None
    out["orientation"] = orientation or ("VÄNDBAR" if code["type"] not in SEPARATE_HV_TYPES else None)
    if code["type"] not in VALID_TYPES:
        out["deviations"].append("E003")
        return out

    src_prog = row.get("program") or program
    reg_pow = original_power(code, src_prog, reg)
    pow_in = row.get("power")
    if pow_in not in (None, "") and reg_pow is not None and float(pow_in) != float(reg_pow):
        out["deviations"].append("E008")
        out["notes"].append(f"Källraden anger {pow_in} W, masterregistret {reg_pow} W - källraden används")
    orig_pow = float(pow_in) if pow_in not in (None, "") else reg_pow
    out["original_power_w"] = orig_pow
    out["original_program"] = src_prog

    prod, err = _override_product(row.get("override"), reg)
    if err:
        out["notes"].append(err)
    if prod:
        match = "OVERRIDE"
        out["notes"].append(f"Projektöverstyrning godkänd av {row['override']['approved_by']}")
    else:
        prod, match = select(code["type"], code["height"], code["length"], reg)
    out["match_status"] = match
    if not prod:
        out["deviations"].append("E002")
        return out

    rsk, rerr = pick_rsk(prod, orientation)
    if rerr:
        out["deviations"].append(rerr)
    out.update({"selected": {k: prod.get(k) for k in ("family", "model", "type", "height", "length", "rsk_right",
                                                       "rsk_left", "rsk_common", "source")},
                "rsk": rsk, "length_diff_mm": prod["length"] - code["length"]})

    target_pow = (prod.get("power") or {}).get(src_prog)
    out["target_power_w"] = target_pow
    if target_pow is None:
        has_other = any(v is not None for v in (prod.get("power") or {}).values()) or prod["family"].endswith("H200")
        if has_other:
            out["technical_comparison_status"] = "TEMPERATURE_REGIME_MISMATCH"
            out["deviations"].append("E006")
        else:
            out["technical_comparison_status"] = "POWER_MISSING"
            out["deviations"].append("E007")
    elif orig_pow is None:
        out["technical_comparison_status"] = "POWER_MISSING"
        out["deviations"].append("E007")
    else:
        out["technical_comparison_status"] = "COMPARABLE"
        out["power_diff_w"] = round(target_pow - orig_pow)
        if orig_pow:
            out["power_diff_pct"] = round((target_pow - orig_pow) / orig_pow * 100, 1)

    if prod["family"] == "Altech Konvektor H200":
        b = reg["brackets"].get(str(prod["type"]))
        phys, pairs = brackets(prod["length"])
        out["bracket"] = {"rsk": b["rsk"] if b else None, "physical_per_convector": phys, "pairs_per_convector": pairs}
        if not b:
            out["deviations"].append("E001")

    if not rsk:
        out["approval_status"] = "MANUAL_REVIEW"
    elif match in ("EXACT_MATCH", "H200_EXACT") and out["technical_comparison_status"] == "COMPARABLE":
        out["approval_status"] = "APPROVED_DIMENSION_MATCH"
    else:
        out["approval_status"] = "REVIEW_REQUIRED"
    return out


def cross_rows(rows: Iterable[dict[str, Any]], reg: dict | None = None, program: str = PROGRAM) -> list[dict[str, Any]]:
    seen: dict[tuple, int] = {}
    res = []
    for i, r in enumerate(rows):
        r = dict(r)
        r.setdefault("id", f"RAD-{i + 1:03d}")
        x = cross_row(r, reg, program)
        key = (str(r.get("article") or ""), str(r.get("text") or "").strip().lower(), str(r.get("location") or ""))
        if key in seen and r.get("text"):
            x["deviations"].append("E009")
            x["notes"].append(f"Samma artikel, benämning och placering som {res[seen[key]]['id']}")
        seen.setdefault(key, i)
        res.append(x)
    return res


# ---------------------------------------------------------------- Prixel

def prixel_rows(res: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for x in res:
        if x["category"] == "accessory" or not x.get("rsk") or "E009" in x["deviations"]:
            continue
        src = f"{x['id']} | {x['source_text']}"
        out.append({"Artnr": str(x["rsk"]), "Ant": x["qty"], "Kontrollkälla": src})
        b = x.get("bracket")
        if b and b.get("rsk"):
            pairs = b["pairs_per_convector"]
            out.append({"Artnr": str(b["rsk"]), "Ant": int(pairs) if float(pairs).is_integer() else pairs,
                        "Kontrollkälla": f"{x['id']} | Väggkonsol: {b['physical_per_convector']} konsoler = {pairs} par per konvektor"})
    return out


def prixel_summed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[str, float] = {}
    for r in rows:
        agg[r["Artnr"]] = agg.get(r["Artnr"], 0) + r["Ant"]
    return [{"Artnr": k, "Ant": int(v) if float(v).is_integer() else v} for k, v in agg.items()]


def deviations(res: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for x in res:
        for c in x["deviations"]:
            out.append({"id": x["id"], "source_text": x["source_text"], "code": c, "type": DEVIATIONS[c],
                        "text": DEVIATION_SV[c], "in_prixel": bool(x.get("rsk")) and c != "E009"})
        if x["category"] == "accessory":
            out.append({"id": x["id"], "source_text": x["source_text"], "code": "-", "type": "EXCLUDED_ACCESSORY",
                        "text": "Tillbehör, räknas inte som radiator", "in_prixel": False})
    return out


def summary(res: list[dict[str, Any]], prixel: list[dict[str, Any]]) -> dict[str, Any]:
    rads = [x for x in res if x["category"] != "accessory"]
    cnt: dict[str, int] = {}
    for x in rads:
        cnt[x["match_status"]] = cnt.get(x["match_status"], 0) + 1
    return {
        "source_rows": len(res), "radiator_rows": len(rads), "radiators": sum(x["qty"] or 0 for x in rads),
        "excluded_accessories": len(res) - len(rads), "by_match": cnt,
        "prixel_rows": len(prixel), "prixel_formulas": 0,
        "without_rsk": sum(1 for x in rads if not x.get("rsk")),
    }


# ---------------------------------------------------------------- QA A-I

def qa(res: list[dict[str, Any]], prixel: list[dict[str, Any]], filename: str = "", sources: list[str] | None = None,
       program: str = PROGRAM) -> list[dict[str, Any]]:
    def q(i, area, ok, comment, blocking=True):
        st = "NOT_APPLICABLE" if ok is None else ("PASS" if ok else "FAIL")
        return {"id": i, "area": area, "status": st, "comment": comment, "blocking": blocking}

    rads = [x for x in res if x["category"] != "accessory"]
    sel = [x for x in rads if x.get("selected")]
    conv = [x for x in sel if x["selected"]["family"] == "Altech Konvektor H200"]
    progs = {x.get("original_program") for x in rads if x.get("original_program")}
    out = [
        q("A", "Källor och omfattning", bool(sources is None or sources) and progs <= {program},
          f"Temperaturprogram {', '.join(sorted(progs)) or program}; regelversion {RULE_VERSION}"),
        q("B", "Mängd", not any("E009" in x["deviations"] for x in res),
          f"{sum(x['qty'] or 0 for x in rads)} radiatorer, {len(res) - len(rads)} tillbehörsrader exkluderade"),
        q("C", "Produktdata", all(x["selected"].get("rsk_right") or x["selected"].get("rsk_common") for x in sel) if sel else None,
          "Typ, höjd, längd och RSK ur verifierat masterregister"),
        q("D", "H/V", all(
            (x["selected"].get("rsk_common") and x["rsk"] == x["selected"]["rsk_common"])
            or (x.get("orientation") == "V" and x["rsk"] == x["selected"].get("rsk_left"))
            or (x.get("orientation") == "H" and x["rsk"] == x["selected"].get("rsk_right"))
            or not x["rsk"] for x in sel) if sel else None, "V -> vänster, H -> höger, vändbar -> gemensamt"),
        q("E", "Matchning", all(
            (x["match_status"] in ("EXACT_MATCH", "H200_EXACT") and x["length_diff_mm"] == 0)
            or (x["match_status"] in ("NEAREST_SHORTER", "H200_NEAREST_SHORTER") and x["length_diff_mm"] < 0)
            or x["match_status"] == "OVERRIDE" for x in sel)
          and all(x["selected"]["type"] == x["original"]["type"] and x["selected"]["height"] == x["original"]["height"]
                  for x in sel if x["match_status"] != "OVERRIDE") if sel else None,
          "Exakt diff 0, kortare diff negativ, ingen typ/höjd byts"),
        q("F", "Effekt", all(
            (x["technical_comparison_status"] == "COMPARABLE" and x["power_diff_w"] == round(x["target_power_w"] - x["original_power_w"]))
            or (x["technical_comparison_status"] != "COMPARABLE" and x["power_diff_w"] is None) for x in sel) if sel else None,
          "Rätt tecken, procent ej vid saknad effekt, samma temperaturprogram"),
        q("G", "Konvektor/konsol", all(
            x["bracket"] and x["bracket"]["rsk"] and x["bracket"]["physical_per_convector"] == max(2, math.ceil(x["selected"]["length"] / 600))
            for x in conv) if conv else None, "H200-typ, konsol-RSK, fysisk mängd och par per konvektor"),
        q("H", "Prixel", all(r["Artnr"] and not str(r["Artnr"]).startswith("=") and isinstance(r["Artnr"], str) for r in prixel),
          f"{len(prixel)} rader, 0 formler, 0 externa länkar, RSK som text"),
        q("I", "Leverans", bool(re.match(r".+_korsad_mot_Altech_inkl_Prixel_\d{4}-\d{2}-\d{2}_v\d{2}\.xlsx$", filename)) if filename else None,
          "Avvikelser redovisade, filnamn och version", blocking=False),
    ]
    return out


def filename(project: str, manufacturer: str, day: date | None = None, version: int = 1) -> str:
    clean = lambda s: re.sub(r"[^\w\-]+", "_", str(s or "Projekt").strip()).strip("_") or "Projekt"
    return f"{clean(project)}_{clean(manufacturer)}_korsad_mot_Altech_inkl_Prixel_{(day or date.today()).isoformat()}_v{version:02d}.xlsx"


def run(rows: Iterable[dict[str, Any]], project: str = "Projekt", manufacturer: str | None = None,
        reg: dict | None = None, program: str = PROGRAM, day: date | None = None) -> dict[str, Any]:
    res = cross_rows(rows, reg, program)
    fams = [x["original"]["family"] for x in res if x.get("original")]
    manufacturer = manufacturer or (max(set(fams), key=fams.count) if fams else "Original")
    px = prixel_rows(res)
    fn = filename(project, manufacturer, day)
    checks = qa(res, px, fn, program=program)
    return {"rule_version": RULE_VERSION, "program": program, "results": res, "prixel": px,
            "prixel_summed": prixel_summed(px), "deviations": deviations(res), "summary": summary(res, px),
            "qa": checks, "export_blocked": any(c["status"] == "FAIL" and c["blocking"] for c in checks),
            "filename": fn, "manufacturer": manufacturer, "project": project}


# ---------------------------------------------------------------- indata

def rows_from_xlsx(data: bytes) -> list[dict[str, Any]]:
    """Läser en kundlista (artikelnr, benämning, antal, placering, ev. effekt)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out: list[dict[str, Any]] = []
    for ws in wb.worksheets:
        head: dict[str, int] | None = None
        for r in ws.iter_rows(values_only=True):
            cells = [str(c).strip().lower() if c is not None else "" for c in r]
            if head is None:
                if any("benämning" in c or "beteckning" in c or "modell" in c for c in cells) and any("antal" in c or c == "ant" for c in cells):
                    head = {}
                    for i, c in enumerate(cells):
                        if ("benämning" in c or "beteckning" in c or "modell" in c) and "text" not in head:
                            head["text"] = i
                        elif (c.startswith("antal") or c == "ant") and "qty" not in head:
                            head["qty"] = i
                        elif ("placering" in c or "plan" in c or "rum" in c) and "location" not in head:
                            head["location"] = i
                        elif "artikel" in c and "article" not in head:
                            head["article"] = i
                        elif "effekt" in c and "power" not in head:
                            head["power"] = i
                        elif c in ("test-id", "id", "pos", "position") and "id" not in head:
                            head["id"] = i
                continue
            if not any(cells):
                continue
            rec = {k: r[i] for k, i in head.items() if i < len(r)}
            if not rec.get("text"):
                continue
            try:
                rec["qty"] = int(float(rec.get("qty") or 0))
            except (TypeError, ValueError):
                rec["qty"] = 0
            rec = {k: (str(v) if k in ("article", "id", "location") and v is not None else v) for k, v in rec.items()}
            out.append(rec)
        if out:
            break
    return out


def rows_from_reader(read: dict[str, Any]) -> list[dict[str, Any]]:
    """Gör om ritningsläsarens summering till källrader (en rad per beteckning)."""
    out = []
    for s in (read.get("summary") or {}).get("rows", []):
        if not (s.get("type") and s.get("h") and s.get("l")) or s.get("kind") == "kompakt":
            code = None  # kompaktradiatorer ingår inte i Typ D-registret: redovisas som avvikelse
        else:
            code = {"family": " ".join(x for x in (s.get("maker"), s.get("series")) if x) or "Ritning",
                    "model": s["designation"], "type": int(s["type"]), "height": int(s["h"]), "length": int(s["l"]),
                    "orientation": None}
        zones = ", ".join(f"{z}: {n}" for z, n in (s.get("per_zone") or {}).items() if n)
        out.append({"text": s["designation"], "qty": s.get("total") or 0, "location": zones, "code": code,
                    "power": None})
    return out


# ---------------------------------------------------------------- Excel

SHEETS = ["Källunderlag", "Fast sortimentsregister", "Korsreferens", "Konvektor och konsol", "Prixel import",
          "Prixel summerad", "Sammanfattning", "Avvikelser", "Källor och regler"]


def to_xlsx(run_: dict[str, Any], reg: dict | None = None) -> bytes:
    """Excel med de nio obligatoriska bladen. Endast fasta värden, RSK som text."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    reg = reg or register()
    wb = Workbook()
    wb.remove(wb.active)
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="DDE6F0")

    def sheet(name, head, rows, text_cols=()):
        ws = wb.create_sheet(name)
        ws.append(head)
        for c in ws[1]:
            c.font, c.fill = bold, fill
        for r in rows:
            vals = []
            for v in r:
                if isinstance(v, str) and v.startswith("="):
                    v = "'" + v
                vals.append(v)
            ws.append(vals)
        for col in text_cols:
            for cell in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                for c in cell:
                    c.number_format = "@"
                    if c.value is not None:
                        c.value = str(c.value)
        for i, h in enumerate(head, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(10, min(48, len(str(h)) + 4))
        return ws

    res = run_["results"]
    sheet("Källunderlag", ["Rad-ID", "Artikelnr", "Benämning", "Antal", "Placering", "Klassning", "Typ", "Höjd", "Längd",
                           "H/V", "Originaleffekt W", "Temperaturprogram"],
          [[x["id"], x["article"], x["source_text"], x["qty"], x["location"], x["category"],
            (x.get("original") or {}).get("type"), (x.get("original") or {}).get("height"),
            (x.get("original") or {}).get("length"), x.get("orientation"), x.get("original_power_w"),
            x.get("original_program")] for x in res], text_cols=(2,))
    used = {x["selected"]["model"] + str(x["selected"]["length"]) for x in res if x.get("selected")}
    sheet("Fast sortimentsregister", ["Fabrikat", "Serie", "Benämning", "Typ", "Höjd", "Längd", "RSK Höger/vändbar",
                                      "RSK Vänster", "Effekt 55/45/20", "Effekt 60/45/20", "Använd i projektet", "Källa"],
          [["Altech", p["family"].replace("Altech ", ""), p["model"], p["type"], p["height"], p["length"],
            p.get("rsk_common") or p.get("rsk_right"), p.get("rsk_left"), (p.get("power") or {}).get("55/45/20"),
            (p.get("power") or {}).get("60/45/20"), "Ja" if p["model"] + str(p["length"]) in used else "",
            p.get("source")] for p in reg["altech"]], text_cols=(7, 8))
    sheet("Korsreferens", ["Rad-ID", "Originalmodell", "Antal", "Typ", "Orig H", "Orig L", "H/V", "Orig effekt",
                           "Vald Altech", "Altech L", "RSK Höger/vändbar", "RSK Vänster", "Valt RSK", "Altech effekt",
                           "Längddiff mm", "Effektdiff W", "Effektdiff %", "match_status", "technical_comparison_status",
                           "approval_status", "Matchtyp"],
          [[x["id"], x["source_text"], x["qty"], (x.get("original") or {}).get("type"), (x.get("original") or {}).get("height"),
            (x.get("original") or {}).get("length"), x.get("orientation"), x.get("original_power_w"),
            (x["selected"] or {}).get("model"), (x["selected"] or {}).get("length"),
            (x["selected"] or {}).get("rsk_common") or (x["selected"] or {}).get("rsk_right"),
            (x["selected"] or {}).get("rsk_left"), x["rsk"], x.get("target_power_w"), x["length_diff_mm"],
            x["power_diff_w"], x["power_diff_pct"], x["match_status"], x["technical_comparison_status"],
            x["approval_status"], MATCH_SV.get(x["match_status"], "")] for x in res if x["category"] != "accessory"],
          text_cols=(11, 12, 13))
    sheet("Konvektor och konsol", ["Rad-ID", "Originalmodell", "Antal konvektorer", "Konvektortyp", "Vald längd",
                                   "Konvektor-RSK", "Fysiska konsoler/konvektor", "Par/konvektor", "Konsol-RSK", "Kommentar"],
          [[x["id"], x["source_text"], x["qty"], x["selected"]["type"], x["selected"]["length"], x["rsk"],
            x["bracket"]["physical_per_convector"], x["bracket"]["pairs_per_convector"], x["bracket"]["rsk"],
            "Prixel Ant på konsolraden = par per konvektor, inte totalen"] for x in res if x.get("bracket")],
          text_cols=(6, 9))
    sheet("Prixel import", ["Artnr", "Ant", "Kontrollkälla"],
          [[r["Artnr"], r["Ant"], r["Kontrollkälla"]] for r in run_["prixel"]], text_cols=(1,))
    sheet("Prixel summerad", ["Artnr", "Ant"], [[r["Artnr"], r["Ant"]] for r in run_["prixel_summed"]], text_cols=(1,))
    s = run_["summary"]
    sheet("Sammanfattning", ["Nyckeltal", "Värde"],
          [["Projekt", run_["project"]], ["Originalfabrikat", run_["manufacturer"]], ["Regelversion", run_["rule_version"]],
           ["Temperaturprogram", run_["program"]], ["Indatarader", s["source_rows"]], ["Radiatorrader", s["radiator_rows"]],
           ["Radiatorer", s["radiators"]], ["Exkluderade tillbehör", s["excluded_accessories"]]]
          + [[MATCH_SV.get(k, k), v] for k, v in s["by_match"].items()]
          + [["Prixel-rader", s["prixel_rows"]], ["Prixel-formler", 0], ["Rader utan RSK", s["without_rsk"]],
             ["Export blockerad", "Ja" if run_["export_blocked"] else "Nej"]]
          + [[f"QA {c['id']} {c['area']}", f"{c['status']} - {c['comment']}"] for c in run_["qa"]])
    sheet("Avvikelser", ["Rad-ID", "Källtext", "Kod", "Feltyp", "Beskrivning", "Med i Prixel"],
          [[d["id"], d["source_text"], d["code"], d["type"], d["text"], "Ja" if d["in_prixel"] else "Nej"]
           for d in run_["deviations"]])
    sheet("Källor och regler", ["Område", "Styrande uppgift"], [
        ["Regelversion", RULE_VERSION], ["Masterregister", f"Altech Typ D masterregister {reg.get('version')}"],
        ["Matchning", "Exakt typ+höjd+längd, annars samma typ+höjd och närmast kortare. Aldrig längre/annan höjd/annan typ utan godkänd överstyrning."],
        ["H/V", "V väljer vänster-RSK. H väljer höger-RSK. Vändbar väljer gemensamt RSK. Okänd riktning ger E005."],
        ["H200", "Använd Altech Konvektor H200 av samma typ, exakt eller närmast kortare."],
        ["Konsol", "Typ 22 H200: 6739888. Typ 33 H200: 6712064. 1 artikel = 1 par. Fysiska = max(2, ceil(L/600))."],
        ["Prixel", "Konsolrad Ant = par per konvektor, inte multiplicerat med antal konvektorer. Konsolrad direkt under konvektor."],
        ["Effekt", "Jämför endast samma temperaturprogram. Ingen omräkning."],
        ["Konvektorregister", reg.get("note", "")],
    ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
