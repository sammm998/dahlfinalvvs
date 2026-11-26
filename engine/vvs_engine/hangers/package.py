"""Ett beräkningspaket: en VS-modell och de K- och A-modeller som täcker samma område, med kontrollrapporten.

Programmet bygger på entreprenörens produktionsmodell. Varje disciplin äger sin fil; filerna har gemensam nollpunkt
och läggs ihop här. Ingen beräkning körs förrän reglerna på nivån Stopp är uppfyllda (V1-V3, och V6 när ingen
takhöjd alls finns). Ett rör som bryter mot en Stopp-regel per rör (V4, V6) listas och hoppas över. Varje fynd har
objektets GlobalId, så att projektören kan rätta direkt i sin modell (och öppna BCF-rapporten i Solibri, Navisworks
eller Dalux).

  V1  Gemensam nollpunkt          Stopp   modellernas nollpunkt skiljer högst 10 mm
  V2  Gemensamma våningsplan      Stopp   samma namn och höjder, högst 5 mm avvikelse
  V3  Enheter                     Stopp   längdenheten identifierad och omräknad till mm
  V4  Röregenskaper               Stopp per rör   system, dimension och material
  V5  Isolering                   Varning isolertjocklek saknas: klammer på rördimension
  V6  Bjälklag ovanför            Stopp per rör   bjälklag eller balk ovanför inom största gängstångslängd
  V7  Bjälklagstyp                Varning typen saknas: välj per zon innan ankare väljs
  V8  Kollisionsstatus            Varning modellen inte markerad fryst/samordnad: resultatet är preliminärt
  V9  Internt kollisionstest      Varning gängstång eller upphängning kolliderar med annat objekt
  V10 Revision                    Info    revision och datum per fil sparas med resultatet
  V11 Rörens höjdläge             Varning identiska höjder i stora stråk utan fall: möjlig zonmodell

Gränsvärdena för V1 (10 mm) och V2 (5 mm) är förslag i kravunderlaget och ligger i regeltabellen.
"""
from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from typing import Any

import numpy as np

from . import rules as RL

LEVELS = ("stopp", "varning", "info")


def storey_key(name: str | None) -> int | None:
    """Våningens nummer ur namnet: "PLAN 09 M30" -> 9, "Plan 9" -> 9, "09" -> 9, "Våning 2 (+7.20)" -> 2.
    Ett nummer som är en höjd (+7.20) eller en zon/modul (M30) räknas inte. Inget nummer -> None."""
    import re
    t = re.sub(r"[+-]\s*\d+[.,]\d+", " ", str(name or ""))          # höjder i namnet
    t = re.sub(r"\b[A-ZÅÄÖ]{1,2}\s?\d+\b", lambda m: m.group(0) if re.match(r"(?i)plan|vån|vaning|level|lvl|etage|floor|bv|kv|ov", m.group(0)) else " ", t.upper())
    m = re.search(r"(?<![\d.])(\d{1,3})(?![\d.])", t)
    return int(m.group(1)) if m else None


def finding(rule: str, level: str, title: str, text: str, guids: list[str] | None = None, file: str = "",
            **extra) -> dict[str, Any]:
    return {"rule": rule, "level": level, "title": title, "text": text, "guids": (guids or [])[:500],
            "n": len(guids or []), "file": file, **extra}


def combine(models: list[dict[str, Any]]) -> dict[str, Any]:
    """Modellerna i paketet till en: rör ur VS, bärverk och håltagningar ur K, väggar och undertak ur A, och allt
    annat (kanaler, kabelstegar, pelare, andra rör) som hinder för kollisionstestet."""
    by = defaultdict(list)
    for m in models:
        by[(m.get("discipline") or "VS").upper()].append(m)
    vs, k, a = by.get("VS", []), by.get("K", []), by.get("A", [])
    other = [m for d, ms in by.items() if d not in ("VS", "K", "A") for m in ms]
    pick = lambda ms, key: [x for m in ms for x in m.get(key) or []]
    # en K-modell bär; saknas den används det bärverk som ligger i VS-filen (sällan) - V6 avgör
    ceilings = pick(k, "ceilings") or pick(vs + a, "ceilings")
    storeys = {}
    for m in vs + k + a:
        for s in m.get("storeys") or []:
            storeys.setdefault(s["name"], s)
    return {"pipes": pick(vs, "pipes"), "fittings": pick(vs, "fittings"), "skipped": pick(vs, "skipped"),
            "storeys": sorted(storeys.values(), key=lambda s: (s["elevation"] is None, s["elevation"] or 0)),
            "ceilings": ceilings, "openings": pick(k, "openings") or pick(vs + a, "openings"),
            "channels": pick(k, "channels"), "walls": pick(a, "walls") or pick(vs + k, "walls"),
            "suspended": pick(a, "suspended") or pick(vs, "suspended"),
            "obstacles": pick(vs + k + a + other, "obstacles") + [
                {"id": c["id"], "bbox": [c["xy"][0], c["xy"][1], c["zmin"], c["xy"][2], c["xy"][3], c["zmax"]], "kind": "balk"}
                for c in pick(k, "ceilings") if c.get("kind") == "beam"],
            "files": [{"discipline": (m.get("discipline") or "VS").upper(), **(m.get("header") or {})} for m in models],
            "has": {"VS": bool(vs), "K": bool(k), "A": bool(a)}}


def validate(models: list[dict[str, Any]], merged: dict[str, Any], rules: dict[str, Any] | None = None,
             settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Kontrollrapporten före beräkningen (V1-V5, V7, V8, V10, V11). V6 och V9 läggs till efter beräkningen."""
    rules = RL.merged(rules)
    lim = rules.get("validation") or {}
    tol_origin = float(lim.get("origin_mm", 10))
    tol_storey = float(lim.get("storey_mm", 5))
    settings = settings or {}
    out: list[dict[str, Any]] = []
    name = lambda m: (m.get("header") or {}).get("file_name") or (m.get("discipline") or "")
    # V3 enheter
    for m in models:
        if not m.get("unit_found"):
            out.append(finding("V3", "stopp", "Längdenhet saknas", "Filen anger ingen längdenhet - kan inte räknas om till mm.",
                               file=name(m)))
    # V1 nollpunkt
    for m1, m2 in itertools.combinations(models, 2):
        o1, o2 = (m1.get("site") or {}).get("origin"), (m2.get("site") or {}).get("origin")
        mp1, mp2 = (m1.get("site") or {}).get("map"), (m2.get("site") or {}).get("map")
        diff = None
        if o1 and o2:
            diff = float(np.max(np.abs(np.array(o1) - np.array(o2))))
        if mp1 and mp2 and all(v is not None for v in mp1 + mp2):
            diff = max(diff or 0.0, float(np.max(np.abs(np.array(mp1) - np.array(mp2)))) * 1000.0)
        if diff is not None and diff > tol_origin:
            out.append(finding("V1", "stopp", "Olika nollpunkt",
                               f"{name(m1)} och {name(m2)} har nollpunkter som skiljer {diff:.0f} mm (högst {tol_origin:.0f} mm).",
                               file=f"{name(m1)} / {name(m2)}"))
    # V2 våningsplan
    # Bara modellernas riktiga våningsplan (IfcBuildingStorey med höjd) jämförs - inte de våningar VS-läsningen
    # tagit ur rörens MagiCAD-egenskaper - och ett plan känns igen på sitt nummer ("PLAN 09 M30", "Plan 09" och
    # "09" är samma plan) eller, utan nummer, på sin höjd. Konsulterna namnger olika; det är inget fel.
    vs = [m for m in models if (m.get("discipline") or "VS").upper() == "VS"]
    for m in models:
        if m in vs or not vs:
            continue
        # VS: IFC-planen och de våningar rören själva bär (MagiCAD StoreyName - en MagiCAD-export har ofta ett enda
        # IFC-plan för hela huset); de senare har ingen höjd och paras bara på nummer
        ref = [s for s in vs[0].get("storeys") or [] if s.get("elevation") is not None or storey_key(s["name"]) is not None]
        mine = [s for s in m.get("storeys") or [] if s.get("elevation") is not None]
        if not ref or not mine:
            continue
        pairs, missing = [], []
        for s in ref:
            k = storey_key(s["name"])
            hit = next((o for o in mine if k is not None and storey_key(o["name"]) == k), None)
            if hit is None and s.get("elevation") is not None:
                hit = next((o for o in mine if abs(o["elevation"] - s["elevation"]) <= tol_storey), None)
            (pairs.append((s, hit)) if hit else missing.append(s["name"]))
        # ett plan som bara finns som rörens våningsnamn och inte i den andra modellen är inget fel i sig
        missing = [n for n in missing if any(x["name"] == n and x.get("elevation") is not None for x in ref)] or \
            ([] if pairs else missing)
        if not pairs:
            out.append(finding("V2", "stopp", "Inga gemensamma våningsplan",
                               f"{name(m)} har inget våningsplan som VS-modellen har - varken med samma nummer eller "
                               f"på samma höjd (VS: {', '.join(s['name'] for s in ref[:6])}; {name(m)}: "
                               f"{', '.join(s['name'] for s in mine[:6])}). Är det samma byggnad och samma nollpunkt?",
                               file=name(m)))
            continue
        if missing:
            out.append(finding("V2", "varning", "Våningsplan saknas i modellen",
                               f"{name(m)} har inte VS-modellens våningsplan {', '.join(missing[:8])}. Rören på de "
                               "våningarna får ingen information ur den här modellen.", file=name(m)))
        for s, o in pairs:
            if s.get("elevation") is not None and abs(s["elevation"] - o["elevation"]) > tol_storey:
                out.append(finding("V2", "stopp", "Olika våningshöjd",
                                   f"Våningsplanet {s['name']}: VS {s['elevation']:.0f} mm, {name(m)} ({o['name']}) "
                                   f"{o['elevation']:.0f} mm (högst {tol_storey:.0f} mm).", file=name(m)))
            elif storey_key(s["name"]) is None or s["name"].strip().lower() != o["name"].strip().lower():
                if not any(f["rule"] == "V2" and f["title"] == "Olika namn på våningsplanen" and f["file"] == name(m) for f in out):
                    out.append(finding("V2", "info", "Olika namn på våningsplanen",
                                       f"{name(m)} namnger planen annorlunda (t.ex. VS {s['name']} = {o['name']}); de "
                                       "paras ihop på nummer och höjd.", file=name(m)))
    # V4 röregenskaper (per rör)
    bad = defaultdict(list)
    for p in merged.get("pipes") or []:
        miss = [k for k, ok in (("system", p.get("system")), ("dimension", p.get("dn") or p.get("od")),
                                ("material", p.get("material") or p.get("code"))) if not ok]
        if miss:
            bad[", ".join(miss)].append(p["id"])
    for what, ids in bad.items():
        out.append(finding("V4", "stopp", f"Rör saknar {what}", f"{len(ids)} rör saknar {what} och hoppas över i beräkningen.",
                           ids, per_pipe=True))
    # V5 isolering
    noins = [p["id"] for p in merged.get("pipes") or [] if p.get("insulation_mm") is None]
    if noins:
        out.append(finding("V5", "varning", "Isolertjocklek saknas",
                           f"{len(noins)} rör saknar isolertjocklek: klammer väljs på rördimension.", noins))
    # V6 utan K-modell: global
    manual = settings.get("manual_heights") or {}
    if not merged["has"].get("K"):
        if merged.get("ceilings") and merged["has"].get("A"):
            out.append(finding("V6", "varning", "K-modell saknas - bjälklag ur A-modellen",
                               f"Ingen K-modell i paketet. Underkant bjälklag tas ur A-modellens {len(merged['ceilings'])} "
                               "bjälklag; kontrollera mot konstruktionen innan kapning. Rör utan bjälklag ovanför flaggas."))
        elif manual:
            out.append(finding("V6", "varning", "K-modell saknas - inmatad takhöjd",
                               "Ingen K-modell i paketet. Underkant bjälklag är inmatad per våning/zon och märks så på varje "
                               "upphängning; kontrollera mot konstruktionen."))
        elif settings.get("estimate_above") not in (None, ""):
            out.append(finding("V6", "varning", "K-modell saknas - takhöjd uppskattad",
                               f"Ingen K-modell i paketet. Underkant bjälklag uppskattas till {settings['estimate_above']:.0f} mm "
                               "över det högsta röret i närheten och märks 'uppskattad' på varje upphängning. Det är ett "
                               "underlag för offert och mängd - inte för kapning. Ladda upp K-modellen före produktion."))
        elif not merged.get("ceilings"):
            out.append(finding("V6", "stopp", "K-modell saknas",
                               "Ingen K-modell och inget bjälklag i paketet: underkant bjälklag okänd. Ladda upp K-modellen "
                               "eller ange underkant bjälklag per våning."))
    # V7 bjälklagstyp
    untyped = [c["id"] for c in merged.get("ceilings") or [] if c.get("kind") == "slab" and not c.get("slab_type")]
    if untyped:
        out.append(finding("V7", "varning", "Bjälklagstyp saknas",
                           f"{len(untyped)} bjälklag har ingen typ (HD/F, platsgjutet, KL-trä, trapetsplåt): välj typ per zon "
                           "innan ankare väljs.", untyped))
    if not merged["has"].get("K") and not (settings.get("zone_slab_types") or {}):
        out.append(finding("V7", "varning", "Bjälklagstyp ej vald",
                           "Utan K-modell: välj bjälklagstyp per zon/våning, annars används projektets standardankare."))
    # V8 frusen
    if not settings.get("frozen") and not all((f.get("frozen") for f in merged.get("files") or [])):
        out.append(finding("V8", "varning", "Modellen är inte markerad fryst/samordnad",
                           "Resultatet är preliminärt tills modellen är fryst efter kollisionskontroll."))
    # V10 revision
    for f in merged.get("files") or []:
        out.append(finding("V10", "info", f"{f.get('discipline')}: {f.get('file_name') or '-'}",
                           f"Datum {f.get('timestamp') or '-'}, revision {f.get('revision') or '-'}, "
                           f"{f.get('application') or '-'}, {f.get('organization') or '-'}, {f.get('schema') or '-'}"))
    # V11 zonmodell
    out += zone_model_check(merged.get("pipes") or [])
    return out


def zone_model_check(pipes: list[dict[str, Any]], min_run: int = 20, share: float = 0.6) -> list[dict[str, Any]]:
    """V11: en bygghandling ritar ofta alla rör i ett stråk på samma höjd och spillet utan fall. Många horisontella
    rör per system och våning på exakt en höjd, eller spillvatten utan fall, flaggas som möjlig zonmodell."""
    out = []
    groups = defaultdict(list)
    for p in pipes:
        s, e = np.array(p["start"]), np.array(p["end"])
        L = float(np.linalg.norm(e - s))
        if L < 200 or abs(e[2] - s[2]) / L > 0.15:
            continue
        groups[(p.get("storey"), p.get("system"))].append((round((s[2] + e[2]) / 2), p))
    for (st, sysn), items in groups.items():
        if len(items) < min_run:
            continue
        z, n = Counter(z for z, _ in items).most_common(1)[0]
        spill = str(sysn or "").upper().startswith(("S", "D", "SP"))
        nofall = [p["id"] for _, p in items if spill and not (p.get("fall_per_mill") or 0)]
        if n / len(items) >= share and len(items) >= min_run:
            out.append(finding("V11", "varning", f"Möjlig zonmodell: {sysn} på {st}",
                               f"{n} av {len(items)} horisontella rör i {sysn} ligger exakt på z = {z} mm. Kontrollera att "
                               "det är en produktionsmodell och inte en bygghandling med rör i zon.", [p['id'] for zz, p in items if zz == z]))
        if spill and len(nofall) >= max(5, len(items) // 2):
            out.append(finding("V11", "varning", f"Spillvatten utan fall: {sysn} på {st}",
                               f"{len(nofall)} spillvattenrör har inget fall - möjlig zonmodell.", nofall))
    return out


USES = {"K": "bjälklag, balkar och håltagningar (underkant bjälklag, ankare)", "A": "väggavstånd, undertak och A-modellens bjälklag",
        "Ö": "kollisionskontrollen", "VS": "rören"}


def _file_name(m: dict[str, Any]) -> str:
    return (m.get("header") or {}).get("file_name") or (m.get("discipline") or "")


def run_checks(models: list[dict[str, Any]], rules: dict[str, Any] | None = None,
               settings: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, list[str]]]:
    """Kontrollrapporten, och vad som görs med den: en Stopp som gäller en annan modell än VS (V1 nollpunkt, V2
    våningsplan, V3 enhet) stoppar inte beräkningen - den modellen tas ur paketet, flaggas tydligt, och de delar
    av beräkningen som behöver den får klara sig utan (K/KP bär, manuell underkant där inget bjälklag finns).
    Bara det som gäller VS-modellen eller beräkningen i stort (V6 utan någon höjd alls) stoppar.

    Returnerar (modellerna som används, sammanslagningen, rapporten, {fil: [skäl]} för de uteslutna)."""
    report = validate(models, combine(models), rules, settings)
    vs_names = {_file_name(m) for m in models if (m.get("discipline") or "VS").upper() == "VS"}
    by_name = {_file_name(m): m for m in models}
    excluded: dict[str, list[dict[str, Any]]] = {}
    for f in blocking(report):
        files = [x.strip() for x in (f.get("file") or "").split(" / ") if x.strip()]
        culprits = [x for x in files if x in by_name and x not in vs_names]
        if culprits:
            excluded.setdefault(culprits[-1], []).append(f)
    if not excluded:
        return models, combine(models), report, {}
    used = [m for m in models if _file_name(m) not in excluded]
    merged = combine(used)
    out = validate(used, merged, rules, settings)
    for fn, fs in excluded.items():
        disc = (by_name[fn].get("discipline") or "Ö").upper()
        for f in fs:
            out.append({**f, "level": "varning", "excluded": True, "title": f"{f['title']} - modellen exkluderad"})
        out.append(finding(fs[0]["rule"], "varning", f"Modell exkluderad: {fn}",
                           f"{fn} används inte i beräkningen ({'; '.join(f['title'] for f in fs)}). Det den skulle ge - "
                           f"{USES.get(disc, 'stödgeometri')} - kommer från de andra modellerna eller manuella värden. "
                           "Rätta modellen och ladda upp den som ny revision.", file=fn, excluded=True))
    order = {"stopp": 0, "varning": 1, "info": 2}
    out.sort(key=lambda f: (order.get(f["level"], 3), f["rule"]))
    return used, merged, out, {fn: [f["title"] for f in fs] for fn, fs in excluded.items()}


def blocking(report: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stopp som gäller hela beräkningen (inte ett enskilt rör)."""
    return [f for f in report if f["level"] == "stopp" and not f.get("per_pipe")]


def summary(report: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(f["level"] for f in report)
    return {k: c.get(k, 0) for k in LEVELS}
