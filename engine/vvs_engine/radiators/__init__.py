"""Radiatorer på VS-ritningen: mängdning per hus och korsning mot Altech (Dahls eget märke).

Läsningen
---------
En projektör skriver varje radiator som en beteckning och, bredvid, det radiatorn ska ge:

    TPv4 22-218                 Purmo Thermopanel V4, typ 22, höjd 2 dm, längd 18 dm
    650W-57l/h-Kv0,25           projekterad effekt, flöde och förinställning

Beteckningen läses i två former: tillverkarens kod med höjd och längd i decimeter (TPv4 22-218, CV22-512,
TP11-304) och en form med millimeter (C22-300-1200, K22 300x1200). Ett antal framför räknas (2xTPv4 22-212).
Effektraden kopplas till närmaste beteckning som saknar en; den som inte får någon står kvar utan effekt.

Var radiatorn sitter: bladets egna rubriker "HUS 1" ... "HUS n" och lägenhetsnumren (LGH 141, 142 i hus 1) ger
husen; varje radiator hamnar i huset vars lägenheter den ligger bland. Utan husrubriker blir bladet en zon.

Korsningen
----------
Föreskriven radiator -> Altech i samma utförande: ventilradiator (TPv4, CV, FCV, TP) mot Altech typ D med
integrerad ventil, kompaktradiator (C, PC, K) mot Altech typ K. Reglerna, i ordning:

1. Exakt: samma typ (11, 21, 22, 33), höjd och längd finns hos Altech -> den.
2. Lucka: Altech saknar storleken. Kandidaterna är Altechs modeller i samma utförande som ger minst den
   projekterade effekten (eller, utan projekterad effekt, minst den föreskrivna modellens katalogeffekt) vid
   projektets temperaturer. Bland dem väljs, i ordning: samma typ före en kraftigare typ, samma höjd före
   närmaste höjd, samma längd före närmaste längd, kortare före längre, och sist minsta överskott.
3. Räcker ingen: den som kommer närmast i effekt, flaggad "effekten räcker inte".

Varje korsning visar skillnaden i effekt (W och %), längd och höjd, och vad som ska kontrolleras (fönsterbänk vid
högre radiator, väggutrymme vid längre, anslutningen). Altechs låga konvektorer (H150/H200) föreslås som
alternativ när föreskriven höjd är 200 mm eller lägre, med effekten omräknad från 75/65/20.

Effekten räknas om mellan temperaturer med logaritmisk medeltemperaturdifferens och radiatorns n-exponent ur
Altechs katalog (Φ = Φ_ref · (ΔT_ln / ΔT_ln,ref)^n). Altechs data: AH-102-2024 (altech_ah102_2024.json)."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent

# tillverkarens kod: familj, typ, höjd i dm och längd i dm (TPv4 22-218 = typ 22, 200 x 1800)
DESIG_DM = re.compile(r"(?<![A-ZÅÄÖ0-9])(?:(?P<count>\d{1,2})\s*[x×*]\s*)?(?P<fam>TPV4|TP\s?V4|TPV|FCV|CV|PCV|TP|PC|C)\s?"
                      r"(?P<type>10|11|20|21|22|30|33)\s?[-–\s]\s?(?P<h>[1-9])(?P<l>\d{2})(?![\d.,])", re.I)
# millimeterform: C22-300-1200, K22 300x1200, D22-300-1200
DESIG_MM = re.compile(r"(?<![A-ZÅÄÖ0-9])(?:(?P<count>\d{1,2})\s*[x×*]\s*)?(?P<fam>TPV4|TPV|FCV|CV|PCV|TP|PC|C|K|D|KV)\s?"
                      r"(?P<type>10|11|20|21|22|30|33)\s?[-–\s]\s?(?P<h>\d{3})\s?[-x×]\s?(?P<l>\d{3,4})(?![\d.,])", re.I)
EFFECT = re.compile(r"(?<![\d,.])(?P<w>\d{2,5})\s*W(?![a-zåäö])(?:\s*[-–/]?\s*(?P<q>\d{1,4}(?:[.,]\d+)?)\s*l/h)?"
                    r"(?:\s*[-–/]?\s*Kv\s*=?\s*(?P<kv>\d+(?:[.,]\d+)?))?", re.I)
HUS = re.compile(r"^HUS\s+(\d{1,2})$", re.I)
LGH = re.compile(r"^LGH\s+(\d{3,5})$", re.I)
ROOM = re.compile(r"^(SOVRUM|KÖK/VARDAGSRUM|KÖK|VARDAGSRUM|VARDAGS|ALLRUM|RUM|HALL|ENTRÉ|ENTRE|BAD|BAD/TVÄTT|WC|DUSCH|TVÄTT|"
                  r"KLK|ARB\.RUM|ARBETSRUM|KONTOR|PASSAGE|TRAPPHUS|KORRIDOR|MATRUM|GROVENTRÉ|FÖRRÅD|TEKNIK|KONFERENS|"
                  r"PERSONALRUM|OMKLÄDNING|LOKAL|GYM|SAMLINGSLOKAL|KLASSRUM|GRUPPRUM)\b", re.I)

VALVE_FAMILIES = {"TPV4", "TPV", "TP", "FCV", "CV", "PCV", "D", "KV"}
MAKERS = {"TPV4": ("Purmo", "Thermopanel V4"), "TPV": ("Purmo", "Thermopanel V4"), "TP": ("Purmo", "Thermopanel"),
          "FCV": ("Purmo", "Plan Ventil Compact"), "CV": ("Purmo", "Ventil Compact"), "PCV": ("Purmo", "Ventil Compact"),
          "C": ("Purmo", "Compact"), "PC": ("Purmo", "Compact"), "K": ("", "kompakt"), "D": ("", "ventil"), "KV": ("", "ventil")}
TYPE_ORDER = ["10", "11", "20", "21", "22", "30", "33"]
DEFAULT_TEMPS = (55.0, 45.0, 20.0)


@lru_cache(maxsize=1)
def altech() -> dict[str, Any]:
    with open(HERE / "altech_ah102_2024.json", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def purmo_reference() -> dict[str, Any]:
    with open(HERE / "purmo_reference.json", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- läsningen

def _family(raw: str) -> str:
    return re.sub(r"\s", "", raw).upper()


def parse_designation(text: str) -> list[dict[str, Any]]:
    """Radiatorbeteckningarna i en textrad (oftast en)."""
    out = []
    taken: list[tuple[int, int]] = []
    for rx, unit in ((DESIG_MM, "mm"), (DESIG_DM, "dm")):
        for m in rx.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            fam = _family(m.group("fam"))
            if unit == "mm":
                h, l = int(m.group("h")), int(m.group("l"))
                if not (150 <= h <= 950 and 300 <= l <= 4000):
                    continue
            else:
                if fam in ("K", "D", "KV"):
                    continue
                h, l = int(m.group("h")) * 100, int(m.group("l")) * 100
                if l < 300:
                    continue
            maker, series = MAKERS.get(fam, ("", ""))
            name = m.group(0).strip()
            if m.group("count"):
                name = re.sub(r"^\d{1,2}\s*[x×*]\s*", "", name)
            fam_disp = "TPv4" if fam in ("TPV4", "TPV") else fam
            designation = (f"{fam_disp} {m.group('type')}-{h // 100}{l // 100:02d}" if unit == "dm"
                           else f"{fam_disp}{m.group('type')}-{h}-{l}")
            out.append({"designation": designation, "written": name, "family": fam, "maker": maker, "series": series,
                        "kind": "ventil" if fam in VALVE_FAMILIES else "kompakt", "type": m.group("type"), "h": h, "l": l,
                        "count": int(m.group("count") or 1), "span": (m.start(), m.end())})
            taken.append((m.start(), m.end()))
    return sorted(out, key=lambda r: r["span"][0])


def parse_effect(text: str) -> dict[str, Any] | None:
    m = EFFECT.search(text)
    if not m or not (m.group("q") or m.group("kv") or re.search(r"\d\s*W\s*$", text.strip())):
        return None
    f = lambda s: float(s.replace(",", ".")) if s else None
    return {"w": int(m.group("w")), "flow_lh": f(m.group("q")), "kv": f(m.group("kv"))}


def _lines_of_page(page) -> list[tuple[float, float, float, float, str]]:
    """Ordrader ur en pymupdf-sida: (x0, y0, x1, y1, text)."""
    rows: dict[tuple[int, int], list] = defaultdict(list)
    for w in page.get_text("words"):
        rows[(w[5], w[6])].append(w)
    out = []
    for ws in rows.values():
        ws.sort(key=lambda w: w[0])
        out.append((min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws),
                    " ".join(w[4] for w in ws)))
    return out


def _c(b) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def _d2(a, b) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _zones(lines, points: list[tuple[float, float]]) -> tuple[list[str], dict[str, Any]]:
    """Husets namn per radiator. Frön: lägenheterna per hus (LGH-numrets första siffra är husets nummer när bladet
    har rubrikerna HUS 1..n och lägenhetsnumren börjar på just de siffrorna), annars rubrikernas egna lägen."""
    hus = {}
    for l in lines:
        m = HUS.match(l[4].strip())
        if m:
            hus[m.group(1)] = _c(l)
    if not hus or not points:
        return [""] * len(points), {"method": "ingen husindelning på bladet"}
    seeds: dict[str, list] = defaultdict(list)
    for l in lines:
        m = LGH.match(l[4].strip())
        if m and m.group(1)[0] in hus:
            seeds[m.group(1)[0]].append(_c(l))
    if set(seeds) == set(hus):
        cent = {k: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v)) for k, v in seeds.items()}
        method = "lägenheterna per hus (LGH-numrets första siffra = husets nummer)"
    else:
        cent = dict(hus)
        method = "närmaste husrubrik"
    keys = sorted(cent, key=lambda k: int(k))
    C = [cent[k] for k in keys]
    assign = [0] * len(points)
    for _ in range(30):
        assign = [min(range(len(C)), key=lambda i: _d2(p, C[i])) for p in points]
        new = []
        for i in range(len(C)):
            mine = [p for p, a in zip(points, assign) if a == i]
            new.append((sum(p[0] for p in mine) / len(mine), sum(p[1] for p in mine) / len(mine)) if mine else C[i])
        if new == C:
            break
        C = new
    return [f"Hus {keys[a]}" for a in assign], {"method": method, "zones": [f"Hus {k}" for k in keys]}


def read_page(page, page_no: int = 0) -> dict[str, Any]:
    """Radiatorerna på en sida (pymupdf.Page) med effekt, flöde, Kv, hus, lägenhet och närmaste rum."""
    lines = _lines_of_page(page)
    labels, effects = [], []
    for ln in lines:
        found = parse_designation(ln[4])
        for r in found:
            rest = ln[4][r["span"][1]:]
            eff = parse_effect(rest) if rest.strip() else None
            labels.append({**r, "bbox": list(ln[:4]), "effect": eff})
        if not found:
            e = parse_effect(ln[4])
            if e:
                effects.append({**e, "bbox": list(ln[:4]), "text": ln[4]})
    # varje effektrad till närmaste beteckning utan effekt (girigt efter avstånd)
    size = max(page.rect.width, page.rect.height)
    lim2 = (size * 0.03) ** 2
    pairs = sorted(((_d2(_c(lb["bbox"]), _c(ef["bbox"])), i, j) for i, lb in enumerate(labels) if not lb["effect"]
                    for j, ef in enumerate(effects)), key=lambda t: t[0])
    used_l, used_e = set(), set()
    for d, i, j in pairs:
        if d > lim2:
            break
        if i in used_l or j in used_e:
            continue
        labels[i]["effect"] = {k: effects[j][k] for k in ("w", "flow_lh", "kv")}
        labels[i]["effect_bbox"] = effects[j]["bbox"]
        used_l.add(i)
        used_e.add(j)
    pts = [_c(lb["bbox"]) for lb in labels]
    zones, zinfo = _zones(lines, pts)
    lgh = [(_c(l), l[4].strip()) for l in lines if LGH.match(l[4].strip())]
    rooms = [(_c(l), l[4].strip()) for l in lines if ROOM.match(l[4].strip()) and len(l[4]) < 40]
    out = []
    for n, (lb, z) in enumerate(zip(labels, zones), 1):
        p = pts[n - 1]
        same_zone_lgh = [x for x in lgh if not z or x[1][4:5] == z.split()[-1][:1]] or lgh
        apt = min(same_zone_lgh, key=lambda x: _d2(p, x[0]))[1] if same_zone_lgh else ""
        room = min(rooms, key=lambda x: _d2(p, x[0]))[1] if rooms else ""
        e = lb["effect"] or {}
        out.append({"nr": n, "page": page_no, "zone": z, "apartment": apt, "room": room,
                    "designation": lb["designation"], "written": lb["written"], "maker": lb["maker"], "series": lb["series"],
                    "family": lb["family"], "kind": lb["kind"], "type": lb["type"], "h": lb["h"], "l": lb["l"],
                    "count": lb["count"], "w": e.get("w"), "flow_lh": e.get("flow_lh"), "kv": e.get("kv"),
                    "bbox": [round(v, 1) for v in lb["bbox"]]})
    return {"page": page_no, "radiators": out, "zones": zinfo, "unpaired_effects": len(effects) - len(used_e),
            "text_lines": len(lines)}


def read_pdf(path: str, pages: list[int] | None = None) -> dict[str, Any]:
    import pymupdf
    doc = pymupdf.open(path)
    sheets = []
    for i in pages if pages is not None else range(doc.page_count):
        if 0 <= i < doc.page_count:
            sheets.append(read_page(doc[i], i))
    rads = [r for s in sheets for r in s["radiators"]]
    for k, r in enumerate(rads, 1):
        r["nr"] = k
    no_text = [s["page"] for s in sheets if s["text_lines"] == 0]
    return {"sheets": [{k: v for k, v in s.items() if k != "radiators"} for s in sheets], "radiators": rads,
            "summary": summary(rads), "no_text_pages": no_text}


def summary(rads: list[dict[str, Any]]) -> dict[str, Any]:
    """Sammanställningen: en rad per beteckning med antal per hus, totalt och summa projekterad effekt."""
    zones = sorted({r["zone"] for r in rads}, key=lambda z: (len(z), z))
    rows: dict[str, dict[str, Any]] = {}
    for r in rads:
        row = rows.setdefault(r["designation"], {"designation": r["designation"], "maker": r["maker"], "series": r["series"],
                                                 "kind": r["kind"], "type": r["type"], "h": r["h"], "l": r["l"],
                                                 "per_zone": Counter(), "total": 0, "w_total": 0, "w_max": None,
                                                 "without_effect": 0})
        row["per_zone"][r["zone"]] += r["count"]
        row["total"] += r["count"]
        if r["w"] is not None:
            row["w_total"] += r["w"] * r["count"]
            row["w_max"] = max(row["w_max"] or 0, r["w"])
        else:
            row["without_effect"] += r["count"]
    out = sorted(rows.values(), key=lambda x: (x["type"], x["h"], x["l"], x["designation"]))
    for row in out:
        row["per_zone"] = {z: row["per_zone"].get(z, 0) for z in zones}
    return {"zones": zones, "rows": out, "total": sum(r["count"] for r in rads),
            "w_total": sum((r["w"] or 0) * r["count"] for r in rads),
            "per_zone": {z: sum(r["count"] for r in rads if r["zone"] == z) for z in zones}}


# ---------------------------------------------------------------- effekt

def lmtd(t_in: float, t_out: float, t_room: float) -> float:
    a, b = t_in - t_room, t_out - t_room
    if a <= 0 or b <= 0:
        raise ValueError("temperaturerna ska ligga över rumstemperaturen")
    return a if abs(a - b) < 1e-9 else (a - b) / math.log(a / b)


def effect_at(model: dict[str, Any], temps: tuple[float, float, float]) -> tuple[float | None, str]:
    """Altechmodellens effekt vid projektets temperaturer och hur den togs fram."""
    temps = tuple(float(t) for t in temps)
    n = model.get("n")
    if model.get("w_55_45") is not None:
        if temps == (55.0, 45.0, 20.0):
            return float(model["w_55_45"]), "katalog 55/45/20"
        if temps == (60.0, 45.0, 20.0):
            return float(model["w_60_45"]), "katalog 60/45/20"
        ref, base = (55.0, 45.0, 20.0), float(model["w_55_45"])
    elif model.get("w_75_65") is not None:
        ref, base = (75.0, 65.0, 20.0), float(model["w_75_65"])
        if temps == ref:
            return base, "katalog 75/65/20"
    else:
        return None, "effekt saknas"
    assumed = n is None
    n = n or 1.4
    w = base * (lmtd(*temps) / lmtd(*ref)) ** n
    return round(w), (f"omräknad från {ref[0]:g}/{ref[1]:g}/{ref[2]:g} med n = {n:g}" + (" (antagen)" if assumed else ""))


def prescribed_effect(r: dict[str, Any], temps: tuple[float, float, float]) -> tuple[float | None, str]:
    """Den föreskrivna modellens katalogeffekt där referensdata finns (Purmo typ 22 H200/H300 ur underlaget)."""
    ref = purmo_reference()
    key = f"{r['kind']}-{r['type']}-{r['h']}"
    row = (ref.get("w_per_m_55_45") or {}).get(key)
    if row is None:
        return None, ""
    w55 = row * r["l"] / 1000
    if tuple(float(t) for t in temps) == DEFAULT_TEMPS:
        return round(w55), ref["source"]
    w = w55 * (lmtd(*temps) / lmtd(*DEFAULT_TEMPS)) ** float(ref.get("n", 1.3))
    return round(w), ref["source"] + f", omräknad med n = {ref.get('n', 1.3)}"


# ---------------------------------------------------------------- korsningen

def _models(family: str) -> list[dict[str, Any]]:
    return [m for m in altech()["models"] if m["family"] == family]


def cross(r: dict[str, Any], need_w: float | None = None, temps: tuple[float, float, float] = DEFAULT_TEMPS,
          max_alternatives: int = 3) -> dict[str, Any]:
    """Föreskriven radiator (beteckningens typ, höjd, längd, utförande) mot Altech.

    need_w: den effekt som ska uppnås (projekterad effekt ur ritningen, största för beteckningen). Saknas den
    används den föreskrivna modellens katalogeffekt; finns ingen av dem väljs storleken utan effektkrav."""
    fam = "D" if r["kind"] == "ventil" else "K"
    pres_w, pres_src = prescribed_effect(r, temps)
    basis = "projekterad effekt" if need_w else ("föreskriven modells katalogeffekt" if pres_w else None)
    need = float(need_w or pres_w or 0) or None
    cands = []
    t0 = TYPE_ORDER.index(r["type"]) if r["type"] in TYPE_ORDER else 0
    heights = sorted({m["h"] for m in _models(fam)})
    for m in _models(fam):
        if m["type"] not in TYPE_ORDER or TYPE_ORDER.index(m["type"]) < t0:
            continue
        w, how = effect_at(m, temps)
        if w is None:
            continue
        cands.append((m, w, how))
    exact = next((c for c in cands if c[0]["type"] == r["type"] and c[0]["h"] == r["h"] and c[0]["l"] == r["l"]), None)

    def key(c):
        m, w, _ = c
        dl = m["l"] - r["l"]
        h_rank = sorted(heights, key=lambda h: (abs(h - r["h"]), h < r["h"])).index(m["h"]) if m["h"] in heights else 99
        return (m["type"] != r["type"], TYPE_ORDER.index(m["type"]), h_rank, abs(dl), dl > 0, w - (need or 0))

    ok = [c for c in cands if need is None or c[1] >= need - 0.5]
    status = "exakt" if exact and (need is None or exact[1] >= need - 0.5) else None
    if status:
        best = exact
    elif ok:
        best, status = min(ok, key=key), "närmaste"
    elif cands:
        best, status = max(cands, key=lambda c: (c[1], -abs(c[0]["l"] - r["l"]))), "räcker inte"
    else:
        return {"status": "saknas", "family": fam, "notes": ["Altech har inget i det utförandet"]}
    out = {"status": status, "family": fam, "basis": basis, "need_w": round(need) if need else None,
           "temps": "/".join(f"{t:g}" for t in temps), "prescribed_w": pres_w, "prescribed_source": pres_src,
           "altech": _describe(best, r, need, pres_w, exact is not None and status != "exakt")}
    # alternativen, ett av varje slag så att valet syns: samma längd (närmaste höjd), samma höjd och längd i en
    # kraftigare typ, och de närmast följande i regelordningen
    alts = []
    seen = {tuple(best[0]["rsk"])}

    def add(c, why):
        if c and tuple(c[0]["rsk"]) not in seen:
            seen.add(tuple(c[0]["rsk"]))
            alts.append({**_describe(c, r, need, pres_w, False), "why": why})
    same_l = [c for c in ok if c[0]["l"] == r["l"] and c[0]["type"] == r["type"]]
    add(min(same_l, key=key) if same_l else None, "samma längd")
    stronger = [c for c in ok if c[0]["l"] == r["l"] and c[0]["h"] == min(heights, key=lambda h: (abs(h - r["h"]), h < r["h"]))
                and c[0]["type"] != r["type"]]
    add(min(stronger, key=key) if stronger else None, "kraftigare typ, samma längd")
    for c in sorted(ok, key=key):
        if len(alts) >= max_alternatives:
            break
        add(c, "nästa i regelordningen")
    if r["h"] <= 200:
        konv = [(m, *effect_at(m, temps)) for m in _models("KONV") if m["h"] <= max(200, r["h"]) and m["type"] >= r["type"]]
        konv = [c for c in konv if c[1] is not None and (need is None or c[1] >= need - 0.5)]
        if konv:
            c = min(konv, key=lambda c: (c[0]["type"] != r["type"], abs(c[0]["h"] - r["h"]), abs(c[0]["l"] - r["l"]), c[0]["l"] > r["l"]))
            add(c, "låg höjd: konvektor")
    out["alternatives"] = alts
    return out


def _describe(c, r, need, pres_w, exact_too_weak: bool) -> dict[str, Any]:
    m, w, how = c
    fam_txt = {"D": "Altech ventilradiator typ D", "K": "Altech panelradiator typ K", "KONV": "Altech konvektor"}[m["family"]]
    name = f"{fam_txt} {m['type']} {m['h']}x{m['l']}"
    dl, dh = m["l"] - r["l"], m["h"] - r["h"]
    notes = []
    if exact_too_weak:
        notes.append("samma storlek finns hos Altech men ger för lite effekt")
    if m["type"] != r["type"]:
        notes.append(f"typ {m['type']} i stället för {r['type']} (djupare radiator) - kontrollera utrymmet")
    if dh > 0:
        notes.append(f"{dh} mm högre - kontrollera fönsterbänk/bröstning och montagehöjd")
    elif dh < 0:
        notes.append(f"{-dh} mm lägre")
    if dl > 0:
        notes.append(f"{dl} mm längre - kontrollera väggutrymmet")
    elif dl < 0:
        notes.append(f"{-dl} mm kortare")
    if m["family"] == "D":
        notes.append("anslutning 4 x M22x1,5 c/c 40 mm, Danfoss RA-U - kontrollera mot föreskriven ventilkoppling")
        notes.append("konsoler ingår (omslutande)")
    if m["family"] == "KONV":
        notes.append("konvektor: annan produkttyp (6 x R15, ventil på höger sida) - projektörens godkännande")
        notes.append("väggkonsol eller golvkonsol beställs som tillbehör")
    out = {"name": name, "rsk": m["rsk"], "family": m["family"], "type": m["type"], "h": m["h"], "l": m["l"], "w": w,
           "w_source": how, "dl_mm": dl, "dh_mm": dh, "notes": notes}
    if need:
        out["dw_need"] = round(w - need)
        out["dw_need_pct"] = round((w - need) / need * 100, 1)
    if pres_w:
        out["dw_prescribed"] = round(w - pres_w)
        out["dw_prescribed_pct"] = round((w - pres_w) / pres_w * 100, 1)
    return out


def cross_all(read: dict[str, Any], temps: tuple[float, float, float] = DEFAULT_TEMPS) -> list[dict[str, Any]]:
    """En korsning per föreskriven beteckning, mot den största projekterade effekten för den, och en kontroll
    av varje enskild radiator mot den valda Altechmodellen."""
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in read["radiators"]:
        by[r["designation"]].append(r)
    out = []
    for des, rs in sorted(by.items(), key=lambda kv: (kv[1][0]["type"], kv[1][0]["h"], kv[1][0]["l"])):
        ws = [x["w"] for x in rs if x["w"] is not None]
        x = cross(rs[0], max(ws) if ws else None, temps)
        a = (x.get("altech") or {})
        under = [y["nr"] for y in rs if y["w"] is not None and a.get("w") is not None and a["w"] < y["w"] - 0.5]
        out.append({"designation": des, "maker": rs[0]["maker"], "series": rs[0]["series"], "kind": rs[0]["kind"],
                    "type": rs[0]["type"], "h": rs[0]["h"], "l": rs[0]["l"], "count": sum(y["count"] for y in rs),
                    "w_min": min(ws) if ws else None, "w_max": max(ws) if ws else None, "radiators_under": under, **x})
    return out
