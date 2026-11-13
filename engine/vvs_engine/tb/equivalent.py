"""Likvärdiga alternativ ur ett eget varumärke (Alterna) när beskrivningen föreskriver ett annat fabrikat.

En byggbeskrivning föreskriver "INR Core Solid XS 60" eller "Hafa Go 1509635", eller bara krav: mått, material,
miljökrav. Alternas produkter står inte i handlingen, varken med namn eller nummer. Matchningen går därför på vad
posten kräver, inte på vad den heter:

  1. vilken sorts vara det är (tvättställskommod, spegelskåp, spegel, handdukstork, duschvägg, krok, hållare ...)
     - ur sakvarans benämning, den föreskrivna produkten och texten
  2. måtten: bredd först (en kommod 60 är 600 mm bred), sedan höjd och djup
  3. material och utförande (porslin, glas, aluminium, rostfritt, el)
  4. miljökrav (Svanen, Byggvarubedömningen, Sunda Hus, BASTA, Möbelfakta, E1)

Varje krav redovisas för sig: uppfyllt, ej uppfyllt, eller okänt när produktdatan inte säger något. Likvärdighet
fastställs aldrig automatiskt - förslaget är ett förslag, att kontrollera mot samtliga tekniska, estetiska och
miljömässiga krav.
"""
from __future__ import annotations

import re
from typing import Any

# sorten: nyckel -> (benämning, ord i posten, ord i produktnamnet)
CATEGORIES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "kommod": ("Tvättställskommod / underskåp", ("tvättställskommod", "kommod", "underskåp", "tvättställsskåp",
                                                   "core solid"), ("underskåp", "kommod")),
    "spegelskåp": ("Spegelskåp", ("spegelskåp", "spegelskap", "stage"), ("spegelskåp",)),
    "spegel": ("Spegel", ("spegel",), ("spegel", "planspegel")),
    "handdukstork": ("Handdukstork", ("handdukstork", "handukstork", "torkstång", "handduksvärmare"), ("handdukstork",)),
    "duschvägg": ("Duschvägg / duschhörna", ("duschvägg", "duschväggar", "duschhörna", "duschskärm",
                                            "duschdörr", "linc angle"), ("duschhörna", "duschvägg", "duschdörr")),
    "pappershållare": ("Toalettpappershållare", ("papperhållare", "pappershållare", "toalettpappershållare",
                                                 "toarullehållare", "toalettrulleshållare", "toalettrullehållare",
                                                 "rullhållare", "wc-papper"), ("toalettpappershållare",
                                                                                   "pappershållare")),
    "krok": ("Krok / hängare", ("handdukskrok", "krok", "krokar", "klädkrok"), ("krok",)),
    "tvättställ": ("Tvättställ", ("tvättställ",), ("tvättställ",)),
    "hylla": ("Hylla", ("hylla", "glashylla"), ("hylla",)),
    "borsthållare": ("Toalettborste", ("toalettborste", "borsthållare", "wc-borste"), ("toalettborste",)),
}
# ord som avgör före andra: "spegelskåp" är inte en spegel, "tvättställskommod" inte ett tvättställ
PRIORITY = ("spegelskåp", "kommod", "handdukstork", "duschvägg", "pappershållare", "borsthållare", "krok", "hylla",
            "spegel", "tvättställ")

MATERIALS = {
    "porslin": ("porslin", "sanitetsporslin", "keramik"), "glas": ("glas", "härdat glas", "säkerhetsglas"),
    "aluminium": ("aluminium",), "rostfritt": ("rostfri", "rostfritt", "syrafast"), "mässing": ("mässing",),
    "krom": ("krom", "förkromad", "blank krom"), "mdf": ("mdf",), "spånskiva": ("spånskiva",),
    "gjuten marmor": ("gjuten marmor", "komposit", "solid surface"),
}
LABELS = {
    "Svanen": ("svanen", "svanenmärkt", "nordic swan"), "Byggvarubedömningen": ("byggvarubedömningen", "bvb"),
    "Sunda Hus": ("sunda hus",), "BASTA": ("basta",), "Möbelfakta": ("möbelfakta",), "E1": ("e1",),
    "EU Ecolabel": ("eu ecolabel", "eu-blomman"), "FSC": ("fsc",), "PEFC": ("pefc",),
}
DISCLAIMER = ("Förslag - likvärdighet är inte automatiskt fastställd. Kontrollera mot samtliga tekniska, estetiska "
              "och miljömässiga krav.")


def _low(t: str) -> str:
    return (t or "").lower().replace(" ", " ")


def category_of(*texts: str, names: bool = False) -> str | None:
    t = " " + " ".join(_low(x) for x in texts if x) + " "
    for key in PRIORITY:
        words = CATEGORIES[key][2] if names else CATEGORIES[key][1]
        if any(w in t for w in words):
            return key
    return None


def dims_of(text: str, category: str | None = None) -> dict[str, int]:
    """Mått i millimeter: "450 x 900", "53x70" (cm), "600 mm", "60 cm", och bredden ur "kommod 60" / "Aqua 60"."""
    t = _low(text)
    out: dict[str, int] = {}
    m = re.search(r"(\d{2,4})\s*[x×]\s*(\d{2,4})(?:\s*[x×]\s*(\d{2,4}))?\s*(mm|cm)?", t)
    if m:
        vals = [int(v) for v in m.groups()[:3] if v]
        unit = m.group(4) or ("cm" if max(vals) < 200 else "mm")
        vals = [v * 10 if unit == "cm" else v for v in vals]
        out["bredd"], out["höjd"] = vals[0], vals[1]
        if len(vals) > 2:
            out["djup"] = vals[2]
        return out
    for key, word in (("bredd", r"bredd|b"), ("höjd", r"höjd|h"), ("djup", r"djup|d")):
        mm = re.search(rf"\b(?:{word})\s*[:=]?\s*(\d{{2,4}})\s*(mm|cm)?\b", t)
        if mm:
            v = int(mm.group(1))
            out[key] = v * 10 if (mm.group(2) == "cm" or (not mm.group(2) and v < 200)) else v
    if "bredd" not in out:
        mm = re.search(r"(?<!cc )(?<!c/c )(?<!\+)(?<!\d)\b(\d{2,3})\s*(cm|mm)\b(?!\s*öfg)", t)
        if mm:
            v = int(mm.group(1))
            out["bredd"] = v * 10 if mm.group(2) == "cm" else v
        elif category in ("kommod", "spegelskåp", "tvättställ", "spegel"):
            # "Tvättställskommod 60", "Ariella Aqua 60", "INR Stage 50": ett ensamt tal 30-160 är bredden i cm
            mm = re.search(r"(?<![\d.,x×-])\b(30|35|40|45|50|55|60|65|70|75|80|90|100|120|140|160)\b(?![\d.,x×]|\s*(?:mm|%|st|w|kw))", t)
            if mm:
                out["bredd"] = int(mm.group(1)) * 10
    return out


def _found(table: dict[str, tuple[str, ...]], text: str) -> list[str]:
    t = " " + _low(text) + " "
    return [k for k, words in table.items() if any(re.search(rf"(?<![a-zåäö]){re.escape(w)}(?![a-zåäö])", t) for w in words)]


def requirements(item: dict[str, Any]) -> dict[str, Any]:
    """Vad en post kräver: sort, mått, material, miljömärkning, el, och den föreskrivna produkten."""
    name = item.get("name") or ""
    pres = " ".join(x for x in (item.get("manufacturer"), item.get("type")) if x)
    text = " ".join([item.get("text") or ""] + [f"{k} {v}" for k, v in (item.get("spec") or {}).items()])
    cat = category_of(name) or category_of(pres, text)
    dims = dims_of(name, cat) or dims_of(pres, cat) or dims_of(text, cat)
    whole = " ".join([name, pres, text])
    return {"category": cat, "category_label": CATEGORIES[cat][0] if cat else "", "dims": dims,
            "materials": _found(MATERIALS, text), "labels": _found(LABELS, whole),
            "electric": bool(re.search(r"\bel(?:ektrisk|handdukstork|anslut|\b)|\b\d+\s*w\b", _low(whole))) or None,
            "prescribed": pres.strip() or "", "or_equal": bool(item.get("or_equal"))}


def product_attrs(p: dict[str, Any]) -> dict[str, Any]:
    """En produkts egenskaper: det katalogen anger, och det som går att läsa ur namnet."""
    name = p.get("name") or ""
    text = " ".join(str(p.get(k) or "") for k in ("name", "series", "description", "material", "category"))
    cat = p.get("category_key") or category_of(p.get("category") or "", name, names=True) or category_of(text)
    dims = {k: int(p[k]) for k in ("bredd", "höjd", "djup") if p.get(k) not in (None, "")}
    if not dims:
        dims = dims_of(name, cat)
    labels = p.get("labels") or _found(LABELS, text + " " + " ".join(p.get("labels_text") or []))
    return {"category": cat, "dims": dims, "materials": p.get("materials") or _found(MATERIALS, text),
            "labels": labels, "electric": True if re.search(r"\bel(?:handdukstork|ektrisk)", _low(text)) else
            (False if cat == "handdukstork" and re.search(r"vattenburen", _low(text)) else None)}


def _check(name: str, state: str, detail: str) -> dict[str, str]:
    return {"krav": name, "status": state, "detalj": detail}


def compare(req: dict[str, Any], p: dict[str, Any]) -> tuple[float, list[dict[str, str]]]:
    a = product_attrs(p)
    checks: list[dict[str, str]] = []
    score = 0.0
    if req["category"] and a["category"] == req["category"]:
        score += 10
        checks.append(_check("Sort", "uppfyllt", req["category_label"]))
    for k in ("bredd", "höjd", "djup"):
        want = req["dims"].get(k)
        if want is None:
            continue
        have = a["dims"].get(k)
        if have is None:
            checks.append(_check(k.capitalize(), "okänt", f"{want} mm krävs, produkten anger inget"))
            continue
        diff = abs(have - want)
        tol = max(10, round(want * 0.03))
        if diff <= tol:
            score += 6 if k == "bredd" else 3
            checks.append(_check(k.capitalize(), "uppfyllt", f"{have} mm (krav {want} mm)"))
        else:
            score -= 4 if k == "bredd" else 2
            checks.append(_check(k.capitalize(), "ej uppfyllt", f"{have} mm mot krav {want} mm"))
    for m in req["materials"]:
        if m in a["materials"]:
            score += 2
            checks.append(_check("Material", "uppfyllt", m))
        else:
            checks.append(_check("Material", "okänt" if not a["materials"] else "ej uppfyllt",
                                 f"{m} krävs" + (f", produkten: {', '.join(a['materials'])}" if a["materials"] else "")))
    for lab in req["labels"]:
        if lab in a["labels"]:
            score += 2
            checks.append(_check("Miljökrav", "uppfyllt", lab))
        else:
            checks.append(_check("Miljökrav", "okänt", f"{lab} krävs - verifiera mot produktens miljödokument"))
    if req.get("electric") and req["category"] == "handdukstork":
        if a["electric"] is False:
            score -= 5
            checks.append(_check("Elansluten", "ej uppfyllt", "produkten är vattenburen"))
        elif a["electric"]:
            score += 1
            checks.append(_check("Elansluten", "uppfyllt", "elhanddukstork"))
    return score, checks


def suggest(item: dict[str, Any], products: list[dict[str, Any]], limit: int = 3) -> dict[str, Any] | None:
    """Alternativen ur det egna varumärket för en post, med kraven ett och ett, eller None när posten inte är en
    sort vi har."""
    req = requirements(item)
    if not req["category"]:
        return None
    ranked = []
    for p in products:
        if product_attrs(p)["category"] != req["category"]:
            continue
        score, checks = compare(req, p)
        ranked.append((score, p, checks))
    if not ranked:
        return {"requirements": req, "candidates": [], "note": f"Inget {req['category_label'].lower()} i sortimentet",
                "disclaimer": DISCLAIMER}
    ranked.sort(key=lambda r: (-r[0], r[1].get("price") or 0, r[1].get("name") or ""))
    cands = []
    for score, p, checks in ranked[:limit]:
        bad = [c for c in checks if c["status"] == "ej uppfyllt"]
        unknown = [c for c in checks if c["status"] == "okänt"]
        cands.append({"rsk": p.get("rsk") or "", "name": p.get("name") or "", "price": p.get("price"),
                      "url": p.get("url") or "", "score": round(score, 1), "checks": checks,
                      "state": "avviker" if bad else ("att verifiera" if unknown else "uppfyller angivna krav")})
    return {"requirements": req, "candidates": cands, "disclaimer": DISCLAIMER}
