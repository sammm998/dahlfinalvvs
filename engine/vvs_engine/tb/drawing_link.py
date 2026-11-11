"""Mängder från ritning: en post i beskrivningen eller listan får sitt antal och sina meter ur projektets ritningar.

Beskrivningen säger vad som ska köpas; ritningen säger hur mycket. När projektet har analyserade ritningar hämtas:

  antal komponenter   en post med en komponentkod (RB201, SIL501, VVB01, RV602) räknas på ritningarna: varje
                      gång koden står på ett blad är en komponent. Samma kod på samma ställe två gånger (en
                      överlagrad text) räknas en gång. En kod som bara står i en förteckning räknas inte.
  rörlängder          en ledningspost med ett systemnamn (KV01, VV01, VVC01, S01) får metrarna för det systemet
                      ur ritningarnas mängder, per dimension. KV01 i beskrivningen är KV1 på ritningen.

Ritningens mängd går före beskrivningens när den finns; båda står kvar, så att en skillnad syns. Hittas inget
på ritningen står beskrivningens mängd kvar, och det sägs.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from typing import Any

# komponentkoder: bokstäver och siffror, ibland en storlek efter bindestreck (RV602-20) som inte är en del av koden
TAG = re.compile(r"(?<![A-Za-zÅÄÖåäö0-9])([A-ZÅÄÖ]{1,5}\d{2,4}[A-Z]?)(?:-\d{1,3}[A-Z]{0,2})?(?![A-Za-zÅÄÖåäö0-9])")
SYSTEM = re.compile(r"^([A-ZÅÄÖ]{1,4})0*(\d{1,3})$")
LIST_WORDS = re.compile(r"förteckning|förklaring|teckenförklaring|beteckningar|innehåll|ritningsförteckning", re.I)


def system_key(token: str | None) -> str | None:
    """KV01, KV1, kv 1 -> KV1. None om token inte är ett systemnamn."""
    m = SYSTEM.match(re.sub(r"\s+", "", (token or "").upper()))
    return f"{m.group(1)}{int(m.group(2))}" if m else None


def _component(code: str) -> bool:
    """RB201, SIL501, VVB01, KVP01 är komponenter; KV1, S1, VS2, VVC1 är system och P5, K1 rörtyper. Ett system
    skrivs med en siffra på ritningen, en komponent med ett löpnummer (minst två siffror, ofta 01)."""
    m = re.fullmatch(r"([A-ZÅÄÖ]{1,5})(\d+)[A-Z]?", code)
    if not m:
        return False
    digits = m.group(2)
    return len(digits) >= 3 or (len(digits) == 2 and digits.startswith("0"))


def _load(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _sheet_dirs(root: str) -> list[tuple[int, str]]:
    d = os.path.join(root, "sheets")
    if os.path.isdir(d):
        return [(int(n), os.path.join(d, n)) for n in sorted(os.listdir(d), key=lambda x: int(x) if x.isdigit() else 0)
                if n.isdigit()]
    return [(0, root)]


def collect(readings: list[dict[str, Any]]) -> dict[str, Any]:
    """Komponentkoder och rörmeter ur projektets lästa ritningar.

    readings: [{"dir": resultatkatalog, "drawing": filnamn}] - en per ritning, den senaste färdiga läsningen."""
    tags: dict[str, dict[str, Any]] = {}
    pipes: dict[str, dict[str, Any]] = {}
    for r in readings:
        root, drawing = r["dir"], r.get("drawing") or ""
        # all text på bladen: i resultatets rot (märkt med sida), och per blad där en läsning skrev den så
        rows: list[dict[str, Any]] = list((_load(os.path.join(root, "vector-designations.json")) or {}).get("text_rows") or [])
        have = {t.get("page") for t in rows}
        for page, d in _sheet_dirs(root):
            tagged = (_load(os.path.join(d, "component-tags.json")) or {}).get("rows")
            if tagged is not None and page not in have:
                rows += [dict(t, page=t.get("page", page)) for t in tagged]
                have.add(page)
            elif d != root and page not in have:
                rows += (_load(os.path.join(d, "vector-designations.json")) or {}).get("text_rows") or []
        by_page: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for t in rows:
            by_page[t.get("page")].append(t)
        for page, prow in by_page.items():
            # på ett blad som är en förteckning står varje kod en gång utan att vara en komponent
            if any(LIST_WORDS.search(t.get("text") or "") for t in prow) and len(prow) > 400:
                prow = [t for t in prow if not LIST_WORDS.search(t.get("text") or "")]
            seen = set()
            for t in prow:
                text = t.get("text") or ""
                for m in TAG.finditer(text):
                    code = m.group(1)
                    i = m.start(1)
                    if i >= 2 and text[i - 1] in "-/" and text[i - 2].isalnum():
                        continue                            # S13 i "VS2-S13-35/S4": en del av en rörbeteckning
                    if not _component(code):
                        continue
                    bb = t.get("bbox") or [0, 0, 0, 0]
                    key = (code, round(bb[0] / 6), round(bb[1] / 6))
                    if key in seen:
                        continue
                    seen.add(key)
                    g = tags.setdefault(code, {"count": 0, "sheets": defaultdict(int)})
                    g["count"] += 1
                    g["sheets"][f"{drawing} blad {int(page or 0) + 1}".strip()] += 1
        dq = _load(os.path.join(root, "document-quantities.json")) or _load(os.path.join(root, "quantities.json")) or {}
        for row in dq.get("rows") or []:
            des = row.get("designation") or ""
            if des.startswith("Onämnt"):
                continue
            sk = system_key(re.split(r"[-/ ]", des)[0])
            if not sk:
                continue
            m = float(row.get("confirmed_total_m") or 0.0)
            review = float(row.get("review_m") or 0.0) + float(row.get("ambiguous_m") or 0.0)
            g = pipes.setdefault(sk, {"m": 0.0, "review_m": 0.0, "by_dn": defaultdict(float), "designations": set(),
                                      "drawings": set(), "no_scale": False})
            g["m"] += m
            g["review_m"] += review
            if row.get("dn"):
                g["by_dn"][str(int(row["dn"]))] += m
            g["designations"].add(des)
            g["drawings"].add(drawing)
            g["no_scale"] = g["no_scale"] or row.get("state") == "NO_SCALE"
    return {
        "tags": {k: {"count": v["count"], "sheets": dict(v["sheets"])} for k, v in tags.items()},
        "pipes": {k: {"m": round(v["m"], 2), "review_m": round(v["review_m"], 2),
                      "by_dn": {dn: round(x, 2) for dn, x in sorted(v["by_dn"].items(), key=lambda kv: int(kv[0]))},
                      "designations": sorted(v["designations"])[:30], "drawings": sorted(v["drawings"]),
                      "no_scale": v["no_scale"]} for k, v in pipes.items()},
        "n_readings": len(readings),
    }


def _is_pipe(it: dict[str, Any]) -> bool:
    t = " ".join([it.get("subcategory") or "", it.get("category") or "", it.get("name") or ""]).lower()
    return t.startswith("ledning") or "ledningar" in t or bool(re.search(r"\brör\b|rörledning|tappvatten|spillvatten", t))


def link(item: dict[str, Any], found: dict[str, Any]) -> dict[str, Any] | None:
    """Vad ritningarna säger om en post, eller None om de inte säger något."""
    if not found or not found.get("n_readings"):
        return None
    code = (item.get("code") or "").upper().replace(" ", "")
    if code:
        base = TAG.fullmatch(code)
        tag = (base.group(1) if base else code)
        hit = found["tags"].get(tag)
        if hit and not (_is_pipe(item) and system_key(code.split("-")[0])):
            return {"kind": "antal", "quantity": float(hit["count"]), "unit": "st", "tag": tag,
                    "sheets": hit["sheets"]}
    if _is_pipe(item):
        sk = system_key((item.get("code") or "").split("-")[0]) or system_key((item.get("name") or "").split(" ")[0])
        if sk and sk in found["pipes"]:
            p = found["pipes"][sk]
            if p["m"] > 0 or p["review_m"] > 0:
                return {"kind": "meter", "quantity": p["m"], "unit": "m", "system": sk, "review_m": p["review_m"],
                        "by_dn": p["by_dn"], "designations": p["designations"], "drawings": p["drawings"],
                        "no_scale": p["no_scale"]}
    return None


def apply(item: dict[str, Any], from_drawing: dict[str, Any] | None) -> dict[str, Any]:
    """Posten med ritningens mängd när den finns: antalet ur ritningen, beskrivningens kvar bredvid."""
    if not from_drawing:
        return item
    out = dict(item, from_drawing=from_drawing, quantity_from="ritning",
               description_quantity=item.get("total_quantity") if item.get("total_quantity") is not None
               else item.get("quantity"))
    if from_drawing["kind"] == "antal" or from_drawing["quantity"] > 0:
        out["total_quantity"] = from_drawing["quantity"]
        out["unit"] = from_drawing["unit"]
    return out
