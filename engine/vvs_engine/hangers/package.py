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
    vs = [m for m in models if (m.get("discipline") or "VS").upper() == "VS"]
    for m in models:
        if m in vs or not vs:
            continue
        ref = {s["name"]: s["elevation"] for s in vs[0].get("storeys") or []}
        mine = {s["name"]: s["elevation"] for s in m.get("storeys") or []}
        missing = sorted(set(ref) - set(mine))
        off = [(n, ref[n], mine[n]) for n in set(ref) & set(mine)
               if ref[n] is not None and mine[n] is not None and abs(ref[n] - mine[n]) > tol_storey]
        if missing:
            out.append(finding("V2", "stopp", "Våningsplan saknas",
                               f"{name(m)} saknar våningsplanen {', '.join(missing[:8])} med samma namn som VS-modellen.",
                               file=name(m)))
        for n, a_, b_ in off:
            out.append(finding("V2", "stopp", "Olika våningshöjd",
                               f"Våningsplanet {n}: VS {a_:.0f} mm, {name(m)} {b_:.0f} mm (högst {tol_storey:.0f} mm).", file=name(m)))
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
        if manual:
            out.append(finding("V6", "varning", "K-modell saknas - inmatad takhöjd",
                               "Ingen K-modell i paketet. Underkant bjälklag är inmatad per våning/zon och märks så på varje "
                               "upphängning; kontrollera mot konstruktionen."))
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


def blocking(report: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stopp som gäller hela beräkningen (inte ett enskilt rör)."""
    return [f for f in report if f["level"] == "stopp" and not f.get("per_pipe")]


def summary(report: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(f["level"] for f in report)
    return {k: c.get(k, 0) for k in LEVELS}
