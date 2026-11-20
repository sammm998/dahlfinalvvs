"""Från rör i rummet till SmartHangers: stråk, upphängningspunkter, hängare, materiallista, kapning och kollin.

  1  rören som ska hängas    horisontella rör (stigare får ingen takhängare och redovisas för sig)
  2  rörstråk                parallella rör på samma våning, nära varandra i sidled, som går längs samma sträcka
  3  upphängningspunkter     jämnt fördelade längs stråket med det kortaste klamringsavståndet bland rören;
                             sedan kontrolleras varje rör för sig (avstånd till änden, största avstånd, närmast
                             ventil/rördel) och punkter läggs till där en regel inte är uppfylld
  4  hängare                 rören som passerar en punkt, uppdelade på nivå och bredd: ett rör blir en pendel,
                             flera blir ett takjärn med två pendlar
  5  höjder                  takets höjd per våning: inmatad (manuell) eller räknad ur nästa våning minus
                             bjälklaget (beräknad) - källan står på varje hängare, och utan höjd flaggas hängaren
  6  last                    vattenfyllt rör och isolering gånger det upphängda avståndet; gängstångens storlek
                             väljs ur regeln, och det som inte bärs flaggas
  7  materiallista, kapoptimering och kollin

Allt i millimeter. Inga mått gissas: det som saknas flaggas på hängaren.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

import numpy as np

from . import rules as RL

STATUSES = ["föreslagen", "granskad", "godkänd", "producerad", "packad", "levererad", "monterad"]
DEVIATIONS = ["ej möjlig", "avvikelse", "omarbete", "paus", "materialbrist"]


def _up(v: float, step: float) -> int:
    return int(math.ceil(v / step - 1e-9) * step)


def storey_code(name: str | None, index: int) -> str:
    b = re.fullmatch(r"Blad (\d+)", name or "")
    if b:
        return f"B{b.group(1)}"
    m = re.search(r"(-?\d+)", name or "")
    return f"P{m.group(1)}" if m else f"P{index}"


def ceilings(storeys: list[dict[str, Any]], manual: dict[str, float] | None, rules: dict[str, Any]) -> dict[str, dict]:
    """Takets höjd (absolut z, mm) per våning och var den kommer ifrån."""
    out = {}
    manual = manual or {}
    elev = [s for s in storeys if s.get("elevation") is not None]
    for s in storeys:
        name = s["name"]
        if manual.get(name) not in (None, ""):
            out[name] = {"z": float(manual[name]), "source": "manuell"}
            continue
        nxt = [x for x in elev if s.get("elevation") is not None and x["elevation"] > s["elevation"] + 1]
        if nxt:
            z = min(x["elevation"] for x in nxt) - rules["fixing"]["slab_thickness"]
            out[name] = {"z": float(z), "source": "beräknad (nästa våning minus bjälklag)"}
        else:
            out[name] = {"z": None, "source": "saknas"}
    return out


class _P:
    """Ett horisontellt rör med sina mått och sin regel."""

    def __init__(self, p: dict[str, Any], rules: dict[str, Any]):
        self.raw = p
        self.id = p["id"]
        self.s = np.array(p["start"], float)
        self.e = np.array(p["end"], float)
        self.vec = self.e - self.s
        self.len = float(np.linalg.norm(self.vec))
        h = self.vec[:2]
        self.dir = h / (np.linalg.norm(h) or 1.0)
        if self.dir[0] < -1e-9 or (abs(self.dir[0]) < 1e-9 and self.dir[1] < 0):
            self.dir = -self.dir
        self.material = RL.material_key(" ".join([p.get("material") or "", p.get("name") or ""]))
        self.dn = p.get("dn")
        self.od = float(p.get("od") or p.get("dn") or 22.0)
        self.system = p.get("system") or ""
        self.storey = p.get("storey") or "?"
        self.spacing, self.spacing_rule = RL.spacing(rules, self.material, self.dn, self.system, p.get("od"))
        self.kgm = RL.kg_per_m(rules, self.material, self.od, self.system)

    def at(self, u: np.ndarray, o: np.ndarray, t: float) -> np.ndarray:
        a, b = float(np.dot(self.s[:2] - o, u)), float(np.dot(self.e[:2] - o, u))
        lam = 0.0 if abs(b - a) < 1e-9 else (t - a) / (b - a)
        return self.s + self.vec * min(1.0, max(0.0, lam))


def _runs(ps: list[_P], rules: dict[str, Any]) -> list[list[_P]]:
    """Rörstråk: parallella rör nära varandra i sidled med överlappande sträckor (union-find per våning)."""
    pl = rules["placement"]
    cos_tol = math.cos(math.radians(pl["parallel_angle_deg"]))
    out = []
    by_storey: dict[str, list[_P]] = defaultdict(list)
    for p in ps:
        by_storey[p.storey].append(p)
    for group in by_storey.values():
        n = len(group)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        D = np.array([p.dir for p in group])
        S = np.array([p.s[:2] for p in group])
        E = np.array([p.e[:2] for p in group])
        M = (S + E) / 2
        for i, p in enumerate(group):
            cos = np.abs(D @ p.dir)
            perp = np.array([-p.dir[1], p.dir[0]])
            lat = np.abs((M - p.s[:2]) @ perp)
            a0, a1 = sorted((0.0, float(np.dot(p.e[:2] - p.s[:2], p.dir))))
            ps_ = (S - p.s[:2]) @ p.dir
            pe_ = (E - p.s[:2]) @ p.dir
            lo, hi = np.minimum(ps_, pe_), np.maximum(ps_, pe_)
            overlap = (np.minimum(hi, a1) - np.maximum(lo, a0)) > -50
            ok = (cos >= cos_tol) & (lat <= pl["run_max_width"]) & overlap
            for j in np.nonzero(ok)[0]:
                if j > i:
                    ri, rj = find(i), find(int(j))
                    if ri != rj:
                        parent[rj] = ri
        comp: dict[int, list[_P]] = defaultdict(list)
        for i, p in enumerate(group):
            comp[find(i)].append(p)
        out += list(comp.values())
    return out


def _even(a: float, b: float, e: float, s: float) -> list[float]:
    if b - a <= 2 * e:
        return [(a + b) / 2]
    n = max(1, math.ceil((b - a - 2 * e) / s - 1e-9))
    return [a + e + (b - a - 2 * e) * k / n for k in range(n + 1)]


def _stations(run: list[_P], u: np.ndarray, o: np.ndarray, fittings: list[np.ndarray], rules: dict[str, Any]):
    pl = rules["placement"]
    e = pl["end_max"]
    iv = {}
    for p in run:
        a, b = sorted((float(np.dot(p.s[:2] - o, u)), float(np.dot(p.e[:2] - o, u))))
        iv[p.id] = (a, b)
    # sammanhängande delar av stråket
    segs = []
    for a, b in sorted(iv.values()):
        if segs and a <= segs[-1][1] + 1:
            segs[-1][1] = max(segs[-1][1], b)
        else:
            segs.append([a, b])
    smin = min(p.spacing for p in run)
    st: list[float] = []
    for a, b in segs:
        st += _even(a, b, min(e, smin / 2), smin)
    why: dict[float, str] = {}
    for _ in range(6):
        added = False
        for p in run:
            a, b = iv[p.id]
            ee = min(e, (b - a) / 2)
            mine = sorted(t for t in st if a - 1 <= t <= b + 1)
            need = []
            if not mine or mine[0] > a + ee + 1:
                need.append((a + ee, "ände"))
            if not mine or mine[-1] < b - ee - 1:
                need.append((b - ee, "ände"))
            for x, y in zip(mine, mine[1:]):
                if y - x > p.spacing + 1:
                    k = math.ceil((y - x) / p.spacing)
                    need += [(x + (y - x) * i / k, "klamringsavstånd") for i in range(1, k)]
            # ventiler och rördelar på röret
            for f in fittings:
                rel = f[:2] - p.s[:2]
                along = float(np.dot(rel, p.dir))
                lat = abs(float(p.dir[0] * rel[1] - p.dir[1] * rel[0]))
                if lat > p.od / 2 + 150 or abs(f[2] - p.at(u, o, float(np.dot(f[:2] - o, u)))[2]) > p.od + 150:
                    continue
                tf = float(np.dot(f[:2] - o, u))
                if not (a - 1 <= tf <= b + 1) or along < -1:
                    continue
                if not any(abs(t - tf) <= pl["fitting_max"] for t in st):
                    side = -1 if tf - a > b - tf else 1
                    need.append((min(b, max(a, tf + side * pl["fitting_max"] * 0.6)), "nära ventil/rördel"))
            for t, w in need:
                if not any(abs(t - x) < 1 for x in st):
                    st.append(t)
                    why[round(t, 1)] = w
                    added = True
        if not added:
            break
    return sorted(set(round(t, 1) for t in st)), iv, why


def generate(model: dict[str, Any], rules: dict[str, Any] | None = None, manual_heights: dict[str, float] | None = None,
             project: str = "", revision: str = "A") -> dict[str, Any]:
    """Hängarna för en modell (vvs_engine.hangers.geometry.pipes)."""
    rules = RL.merged(rules)
    pl, g = rules["placement"], rules["geometry"]
    ceil = ceilings(model.get("storeys") or [], manual_heights, rules)
    storey_index = {s["name"]: i for i, s in enumerate(model.get("storeys") or [])}
    hor, skipped = [], []
    for p in model.get("pipes") or []:
        P = _P(p, rules)
        dz = abs(P.vec[2])
        if P.len < pl["min_pipe_length"]:
            skipped.append({"pipe": P.id, "name": p.get("name"), "why": f"kort rör ({P.len:.0f} mm) - hängs av grannrören"})
        elif dz / (P.len or 1) > pl["vertical_ratio"]:
            skipped.append({"pipe": P.id, "name": p.get("name"), "why": "stigare/lutande - väggfäste, inte takhängare"})
        else:
            hor.append(P)
    fittings = [np.array(f["at"], float) for f in model.get("fittings") or []]
    raw: list[dict[str, Any]] = []
    for ri, run in enumerate(_runs(hor, rules)):
        longest = max(run, key=lambda p: p.len)
        u = longest.dir
        v = np.array([-u[1], u[0]])
        o = longest.s[:2].copy()
        lo = min(min(np.dot(p.s[:2] - o, u), np.dot(p.e[:2] - o, u)) for p in run)
        o = o + u * lo
        st, iv, why = _stations(run, u, o, fittings, rules)
        for t in st:
            here = []
            for p in run:
                a, b = iv[p.id]
                if a - 1 <= t <= b + 1:
                    pt = p.at(u, o, t)
                    here.append((float(np.dot(pt[:2] - o, v)), pt, p))
            # nivåer, sedan bredd
            here.sort(key=lambda x: x[1][2])
            levels, cur = [], []
            for h in here:
                if cur and h[1][2] - cur[0][1][2] > pl["level_tolerance"]:
                    levels.append(cur)
                    cur = []
                cur.append(h)
            if cur:
                levels.append(cur)
            for lev in levels:
                lev.sort(key=lambda x: x[0])
                grp: list = []
                for h in lev:
                    if grp and h[0] - grp[0][0] > pl["run_max_width"]:
                        raw.append({"run": ri, "t": t, "pipes": grp, "u": u, "v": v, "o": o, "why": why.get(t)})
                        grp = []
                    grp.append(h)
                if grp:
                    raw.append({"run": ri, "t": t, "pipes": grp, "u": u, "v": v, "o": o, "why": why.get(t)})
    # upphängd längd per rör och punkt: halva avståndet till grannpunkterna (och ända ut till rörets ände)
    per_pipe: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for k, h in enumerate(raw):
        h["k"] = k
        for _, _, p in h["pipes"]:
            per_pipe[p.id].append((h["t"], k))
    trib: dict[tuple[int, str], float] = {}
    for p in hor:
        pts = sorted(per_pipe.get(p.id, []))
        if not pts:
            continue
        o_ = next(raw[k] for _, k in pts)
        a, b = sorted((float(np.dot(p.s[:2] - o_["o"], o_["u"])), float(np.dot(p.e[:2] - o_["o"], o_["u"]))))
        ts = [t for t, _ in pts]
        for i, (t, k) in enumerate(pts):
            left = (t - ts[i - 1]) / 2 if i else t - a
            right = (ts[i + 1] - t) / 2 if i + 1 < len(ts) else b - t
            trib[(k, p.id)] = max(0.0, left) + max(0.0, right)
    hangers = []
    counters: dict[str, int] = defaultdict(int)
    raw.sort(key=lambda h: (storey_index.get(h["pipes"][0][2].storey, 99), h["run"], h["t"]))
    for k, h in enumerate(raw):
        pipes_ = h["pipes"]
        storey = pipes_[0][2].storey
        code = storey_code(storey, storey_index.get(storey, 0))
        counters[code] += 1
        hid = f"{code}-{counters[code]:03d}"
        c = ceil.get(storey) or {"z": None, "source": "saknas"}
        flags = []
        w = [x[0] for x in pipes_]
        ods = [x[2].od for x in pipes_]
        centre_xy = h["o"] + h["u"] * h["t"] + h["v"] * ((min(w) + max(w)) / 2)
        bottoms = [x[1][2] - x[2].od / 2 for x in pipes_]
        n_rods = 1 if len(pipes_) == 1 else 2
        load_kg = sum(x[2].kgm * trib.get((h["k"], x[2].id), x[2].spacing) / 1000.0 for x in pipes_)
        load_kn = round(load_kg * 9.81 / 1000.0, 3)
        rod = RL.rod_size(rules, load_kn / n_rods)
        if rod is None:
            flags.append(f"lasten {load_kn} kN överstiger gängstångens bärförmåga - konstruktören avgör")
            rod = max(rules["load"]["rod_capacity_kn"], key=lambda s: rules["load"]["rod_capacity_kn"][s])
        takjarn = None
        clamps = []
        if n_rods == 1:
            p = pipes_[0]
            top = p[1][2] + p[2].od / 2 + g["clamp_base"]
            rod_len = (c["z"] - top) if c["z"] is not None else None
            kind = "pendel"
            z_hang = top
        else:
            kind = "takjärn"
            ptop = min(bottoms) - g["clamp_base"]
            pbot = ptop - g["profile_height"]
            length = _up((max(w) - min(w)) + max(ods) + 2 * g["overhang"], g["length_step"])
            x0 = (min(w) + max(w)) / 2 - length / 2
            for (wi, pt, p), b in zip(pipes_, bottoms):
                rise = round(b - g["clamp_base"] - ptop)
                clamps.append({"pipe": p.id, "at_mm": int(round((wi - x0) / g["hole_step"]) * g["hole_step"]), "rise_mm": rise if rise > 10 else 0,
                               "dn": p.dn, "od": p.od})
                if rise > 10:
                    flags.append(f"rör {p.dn or p.od} ligger {rise} mm högre - distans/förhöjning på klammern")
            takjarn = {"profile": g["profile"], "length_mm": length, "rod_holes_mm": [25, length - 25],
                       "clamps": clamps, "top_z": round(ptop, 1)}
            rod_len = (c["z"] - pbot + g["rod_allowance"]) if c["z"] is not None else None
            z_hang = pbot
            if load_kn > rules["load"]["profile_capacity_kn"] / rules["load"]["safety_factor"]:
                flags.append(f"lasten {load_kn} kN på takjärnet över tillåten - kraftigare profil")
        if rod_len is None:
            flags.append("takhöjd saknas - ange takhöjd för våningen")
        else:
            rod_len = _up(max(rod_len, 0), g["rod_step"])
            if rod_len < g["min_rod"]:
                flags.append(f"röret ligger för nära taket ({rod_len} mm pendel) - annan infästning")
            if rod_len > g["max_rod"]:
                flags.append(f"lång pendel ({rod_len} mm) - stagning bedöms")
        if c["z"] is not None and z_hang > c["z"]:
            flags.append("röret ligger över taket i modellen - kontrollera takhöjden")
        rods = [{"size": rod, "length_mm": rod_len, "at_mm": (25 if i == 0 else (takjarn or {}).get("length_mm", 50) - 25) if takjarn else 0}
                for i in range(n_rods)]
        hanger = {
            "id": hid, "project": project, "revision": revision, "storey": storey, "zone": f"stråk {h['run'] + 1}",
            "run": h["run"], "station_mm": round(h["t"]), "kind": kind,
            "position": {"x": round(float(centre_xy[0])), "y": round(float(centre_xy[1])),
                         "z": round(c["z"]) if c["z"] is not None else None},
            "reference": {"run_start": [round(float(x)) for x in h["o"]], "along_run_mm": round(h["t"]),
                          "text": f"{round(h['t'])} mm längs stråk {h['run'] + 1} från dess början"},
            "pipes": [{"id": p.id, "dn": p.dn, "od": p.od, "material": p.material, "system": p.system,
                       "centre_z": round(float(pt[2])), "spacing_rule": p.spacing_rule,
                       "hung_length_mm": round(trib.get((h["k"], p.id), 0))} for _, pt, p in pipes_],
            "ceiling_z": round(c["z"]) if c["z"] is not None else None, "height_source": c["source"],
            "takjarn": takjarn, "rods": rods, "load_kn": load_kn,
            "anchor": rules["fixing"]["anchor"].get(rules["fixing"]["ceiling"], "Takinfästning"),
            "finish": rules["environment"]["finish"].get(rules["environment"]["default"], ""),
            "placed_because": h.get("why") or "klamringsavstånd",
            "flags": flags, "status": "föreslagen", "history": [], "approved": {},
        }
        unknown = [p for _, _, p in pipes_ if p.material == "okänt"]
        if unknown:
            flags.append(f"materialet okänt för {', '.join(sorted({p.raw.get('name') or p.id for p in unknown}))[:80]} - "
                         f"försiktigt klamringsavstånd {rules['spacing']['okänt'][0][1]} mm")
        if model.get("source") == "2D-ritning":
            # en planritning har ingen höjd: takhöjden och rörets avstånd under taket är inmatade antaganden
            hanger["height_source"] = ("antagen (2D-ritning)" if c["z"] is not None else "saknas")
            hanger["flags"].append("höjd ur 2D-ritning - mät på plats innan produktion")
        hanger["bom"] = bom(hanger, rules)
        hangers.append(hanger)
    return {"hangers": hangers, "skipped": skipped + [dict(s, why=s.get("why")) for s in model.get("skipped") or []],
            "ceilings": ceil, "rules_version": rules.get("version"), "rules_verified": bool(rules.get("verified")),
            "n_pipes": len(model.get("pipes") or []), "n_hung_pipes": len(hor),
            "runs": len({h["run"] for h in hangers}), "summary": summary(hangers, rules)}


def bom(h: dict[str, Any], rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Materialet i en hängare. Benämningar, inte artikelnummer: artiklarna kopplas mot leverantörens sortiment."""
    out = []
    rods = h["rods"]
    size = rods[0]["size"] if rods else "M10"
    if h.get("takjarn"):
        out.append({"part": "takjärn", "text": h["takjarn"]["profile"], "qty": 1, "length_mm": h["takjarn"]["length_mm"]})
        out.append({"part": "kanalmutter", "text": f"Kanalmutter {size} med fjäder", "qty": len(h["pipes"]), "length_mm": None})
        out.append({"part": "skruv", "text": f"Skruv {size} till klammer", "qty": len(h["pipes"]), "length_mm": None})
        nuts = 2 * len(rods) + len(rods)
    else:
        nuts = 2 * len(rods)
    lengths: dict[tuple, int] = {}
    for r in rods:
        lengths[(r["size"], r["length_mm"])] = lengths.get((r["size"], r["length_mm"]), 0) + 1
    for (sz, ln), q in lengths.items():
        out.append({"part": "gängstång", "text": f"Gängstång {sz} förzinkad", "qty": q, "length_mm": ln,
                    "stock": f"gängstång {sz} {rules['stock']['rod_mm']}"})
        if ln and ln > rules["stock"]["rod_mm"]:
            out.append({"part": "skarvmutter", "text": f"Skarvmutter {sz}", "qty": q, "length_mm": None})
    anchor = re.sub(r"\bM\d+\b", size, h.get("anchor") or "Takinfästning")
    out.append({"part": "infästning", "text": anchor, "qty": len(rods), "length_mm": None})
    out.append({"part": "mutter", "text": f"Mutter {size}", "qty": nuts, "length_mm": None})
    out.append({"part": "bricka", "text": f"Bricka {size}", "qty": 2 * len(rods), "length_mm": None})
    for p in h["pipes"]:
        out.append({"part": "rörklammer", "text": f"Rörklammer {round(p['od'] or 0)} mm {('med gummiinlägg ' if p['material'] != 'plast' else '')}{size}-anslutning".replace("  ", " "),
                    "qty": 1, "length_mm": None, "pipe": p["id"]})
    return _articles(out, rules)


def _articles(out: list[dict[str, Any]], rules: dict[str, Any]) -> list[dict[str, Any]]:
    arts = rules.get("articles") or {}
    for b in out:
        a = arts.get(b.pop("stock", "") or "")
        if a:
            b.update(art=a["art"], supplier=a.get("supplier"), art_source=a.get("source"))
    return out


def summary(hangers: list[dict[str, Any]], rules: dict[str, Any]) -> dict[str, Any]:
    by_kind = defaultdict(int)
    for h in hangers:
        by_kind[h["kind"]] += 1
    return {"hangers": len(hangers), "by_kind": dict(by_kind), "flagged": sum(1 for h in hangers if h["flags"]),
            "by_storey": dict(sorted(_count(h["storey"] for h in hangers).items()))}


def _count(xs):
    d = defaultdict(int)
    for x in xs:
        d[x] += 1
    return d


def bom_total(hangers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Projektets materiallista: samma del och längd summeras."""
    acc: dict[tuple, dict[str, Any]] = {}
    for h in hangers:
        for b in h.get("bom") or []:
            k = (b["text"], b.get("length_mm"))
            r = acc.setdefault(k, {"text": b["text"], "length_mm": b.get("length_mm"), "qty": 0, "hangers": 0})
            r["qty"] += b["qty"]
            r["hangers"] += 1
    return sorted(acc.values(), key=lambda r: (r["text"], r["length_mm"] or 0))


def cut_plan(hangers: list[dict[str, Any]], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Kapoptimering (first-fit decreasing): takjärn och gängstång ur lagerlängder, med sågsnitt."""
    rules = RL.merged(rules)
    S = rules["stock"]
    out = {}
    for part, stock in (("takjärn", S["profile_mm"]), ("gängstång", S["rod_mm"])):
        pieces = defaultdict(list)
        for h in hangers:
            for b in h.get("bom") or []:
                if b["part"] == part and b.get("length_mm"):
                    for _ in range(b["qty"]):
                        pieces[b["text"]].append((int(b["length_mm"]), h["id"]))
        res = []
        for text, items in pieces.items():
            bars: list[dict[str, Any]] = []
            for L, hid in sorted(items, key=lambda x: -x[0]):
                if L > stock:
                    # längre än lagerlängden: skarvas av flera hela längder och en rest
                    full, rest = divmod(L, stock)
                    for _ in range(full):
                        bars.append({"cuts": [{"mm": stock, "hanger": hid}], "left": 0})
                    L = rest
                    if not L:
                        continue
                for b in bars:
                    if b["left"] >= L + S["kerf_mm"]:
                        b["cuts"].append({"mm": L, "hanger": hid})
                        b["left"] -= L + S["kerf_mm"]
                        break
                else:
                    bars.append({"cuts": [{"mm": L, "hanger": hid}], "left": stock - L - S["kerf_mm"]})
            used = sum(c["mm"] for b in bars for c in b["cuts"])
            res.append({"text": text, "stock_mm": stock, "bars": bars, "n_bars": len(bars), "pieces": len(items),
                        "waste_pct": round(100 * (1 - used / (len(bars) * stock)), 1) if bars else 0.0})
        out[part] = res
    return out


def weight_kg(h: dict[str, Any]) -> float:
    """Hängarens egen vikt (för kollin): takjärn ~1,5 kg/m, gängstång M10 ~0,5 kg/m, smådelar 0,05 kg st."""
    kg = 0.0
    for b in h.get("bom") or []:
        if b["part"] == "takjärn":
            kg += 1.5 * b["length_mm"] / 1000
        elif b["part"] == "gängstång" and b.get("length_mm"):
            kg += 0.5 * b["length_mm"] / 1000
        else:
            kg += 0.05 * b["qty"]
    return round(kg, 2)


def pack(hangers: list[dict[str, Any]], rules: dict[str, Any] | None = None, by: str = "montage") -> list[dict[str, Any]]:
    """Kollin i montageordning: per våning och stråk, högst N hängare och M kg per kolli. Varje hängare får sin
    packsekvens (kolli-nummer/plats)."""
    rules = RL.merged(rules)
    P = rules["packing"]
    order = sorted(hangers, key=lambda h: (h["storey"] or "", h.get("run", 0), h.get("station_mm", 0))) if by == "montage" \
        else sorted(hangers, key=lambda h: (h["storey"] or "", h["id"]))
    kollin: list[dict[str, Any]] = []
    for h in order:
        kg = weight_kg(h)
        k = kollin[-1] if kollin else None
        if not k or k["storey"] != h["storey"] or len(k["hangers"]) >= P["max_per_kolli"] or k["kg"] + kg > P["max_kg_per_kolli"]:
            k = {"no": len(kollin) + 1, "storey": h["storey"], "zone": h.get("zone"), "hangers": [], "kg": 0.0}
            kollin.append(k)
        k["hangers"].append(h["id"])
        k["kg"] = round(k["kg"] + kg, 2)
        h["pack"] = {"kolli": k["no"], "seq": len(k["hangers"])}
    return kollin


def diff(old_pipes: list[dict[str, Any]], new_pipes: list[dict[str, Any]], hangers: list[dict[str, Any]],
         tol: float = 20.0) -> dict[str, Any]:
    """Revision: vilka rör som är nya, borttagna, flyttade eller ändrade, och vilka hängare det berör. En hängare
    som redan är producerad, packad, levererad eller monterad är kritisk."""
    old = {p["id"]: p for p in old_pipes}
    new = {p["id"]: p for p in new_pipes}
    added = [i for i in new if i not in old]
    removed = [i for i in old if i not in new]
    moved, changed = [], []
    for i in set(old) & set(new):
        a, b = old[i], new[i]
        d = max(np.linalg.norm(np.array(a["start"]) - np.array(b["start"])), np.linalg.norm(np.array(a["end"]) - np.array(b["end"])))
        if d > tol:
            moved.append({"pipe": i, "moved_mm": round(float(d))})
        if (a.get("dn"), a.get("material"), a.get("system")) != (b.get("dn"), b.get("material"), b.get("system")):
            changed.append({"pipe": i, "from": {"dn": a.get("dn"), "material": a.get("material")},
                            "to": {"dn": b.get("dn"), "material": b.get("material")}})
    touched = set(removed) | {m["pipe"] for m in moved} | {c["pipe"] for c in changed}
    affected = []
    for h in hangers:
        hit = [p["id"] for p in h["pipes"] if p["id"] in touched]
        if hit:
            crit = h.get("status") in ("producerad", "packad", "levererad", "monterad")
            affected.append({"hanger": h["id"], "status": h.get("status"), "pipes": hit, "critical": crit})
    return {"added": added, "removed": removed, "moved": moved, "changed": changed, "affected": affected,
            "critical": sum(1 for a in affected if a["critical"])}
