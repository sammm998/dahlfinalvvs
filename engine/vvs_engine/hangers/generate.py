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
        self.ins = float(p.get("insulation_mm") or 0.0)
        self.od_eff = self.od + 2 * self.ins            # ytterdiameter med isolering: klammer och avstånd räknas på den
        self.system = p.get("system") or ""
        self.storey = p.get("storey") or "?"
        self.spacing, self.spacing_rule = RL.spacing(rules, self.material, self.dn, self.system, p.get("od"))
        self.kgm = RL.kg_per_m(rules, self.material, self.od, self.system)
        if self.ins:
            # isoleringens vikt efter tjockleken (mineralull/cellgummi ~ 60 kg/m3) i stället för schablonen
            self.kgm = round(self.kgm - rules["load"]["insulation_kg_m"] * (self.kgm > 0)
                             + 3.1416 * (self.od + self.ins) * self.ins * 60e-6, 3)

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
            near = fittings
            if len(fittings) > 50:
                F = np.asarray(fittings)
                lo_, hi_ = np.minimum(p.s, p.e) - 300, np.maximum(p.s, p.e) + 300
                near = F[np.all((F >= lo_) & (F <= hi_), axis=1)]
            for f in near:
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


class _Grid:
    """Ett rutnät över planet: vilka objekt (med bbox [x0, y0, z0, x1, y1, z1]) som ligger nära en punkt."""

    def __init__(self, items: list[dict[str, Any]], cell: float = 2000.0):
        self.cell, self.items, self.map = cell, items, defaultdict(list)
        for i, it in enumerate(items):
            b = it["bbox"]
            for cx in range(int(b[0] // cell), int(b[3] // cell) + 1):
                for cy in range(int(b[1] // cell), int(b[4] // cell) + 1):
                    self.map[(cx, cy)].append(i)

    def near(self, x: float, y: float, r: float = 0.0) -> list[dict[str, Any]]:
        out = set()
        for cx in range(int((x - r) // self.cell), int((x + r) // self.cell) + 1):
            for cy in range(int((y - r) // self.cell), int((y + r) // self.cell) + 1):
                out.update(self.map.get((cx, cy), ()))
        return [self.items[i] for i in out]


def _inside(b: list[float], x: float, y: float, m: float = 0.0) -> bool:
    return b[0] - m <= x <= b[3] + m and b[1] - m <= y <= b[4] + m


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    d = b - a
    t = float(np.clip(np.dot(p - a, d) / (np.dot(d, d) or 1.0), 0.0, 1.0))
    return float(np.linalg.norm(p - (a + d * t)))


def _beam_slab_type(c: dict[str, Any]) -> str | None:
    if c.get("kind") == "beam":
        return "Stålbalk" if re.search(r"stål|steel|\bhe[ab]\b|\bipe\b|\bvkr\b|\bkkr\b|\bupe\b", c.get("type_text") or "", re.I) \
            else (c.get("slab_type") or "Platsgjutet")
    return c.get("slab_type")


def _adjust(t: float, point_at, grids: dict, rules: dict[str, Any], spacing: float) -> tuple[float, str | None, str | None]:
    """Flytta en upphängningspunkt bort från håltagningar och balkkanter (K-modellen), eller till en
    ingjutningsskena. Returnerar (t, varför den flyttades, flagga om den inte gick att flytta)."""
    cl = rules.get("clearances") or {}
    m_open, m_beam, snap = float(cl.get("opening_mm", 100)), float(cl.get("beam_edge_mm", 100)), float(cl.get("channel_snap_mm", 300))

    def blocked(tt):
        x, y = point_at(tt)[:2]
        for o in grids["openings"].near(x, y, m_open):
            if _inside(o["bbox"], x, y, m_open):
                return f"håltagning {o['id']}"
        for c in grids["beams"].near(x, y, m_beam):
            b = c["bbox"]
            inner = _inside(b, x, y, -m_beam)
            if _inside(b, x, y, m_beam) and not inner:
                return f"balkkant {c['id']}"
        return None

    x, y = point_at(t)[:2]
    for ch in grids["channels"].near(x, y, snap):
        a_, b_ = np.array(ch["start"][:2]), np.array(ch["end"][:2])
        # skärningen mellan skenan och stråkets linje, inom snäppavståndet
        p0, p1 = np.array(point_at(t - 1000)[:2]), np.array(point_at(t + 1000)[:2])
        d1, d2 = p1 - p0, b_ - a_
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            continue
        s_ = ((a_[0] - p0[0]) * d2[1] - (a_[1] - p0[1]) * d2[0]) / den
        u_ = ((a_[0] - p0[0]) * d1[1] - (a_[1] - p0[1]) * d1[0]) / den
        tc = t - 1000 + s_ * 2000
        if 0 <= u_ <= 1 and abs(tc - t) <= snap:
            return tc, f"snäppt till ingjutningsskena {ch['id']}", None
    why = blocked(t)
    if not why:
        return t, None, None
    for step in (50, 100, 150, 200, 300, 400, 500):
        if step > spacing / 3:
            break
        for tt in (t - step, t + step):
            if not blocked(tt):
                return tt, f"flyttad {step} mm från {why}", None
    return t, None, f"upphängning vid {why} - gick inte att flytta inom c/c, kontrollera"


def generate(model: dict[str, Any], rules: dict[str, Any] | None = None, manual_heights: dict[str, float] | None = None,
             project: str = "", revision: str = "A", zone_slab_types: dict[str, str] | None = None,
             estimate_above: float | None = None) -> dict[str, Any]:
    """Upphängningarna för ett beräkningspaket (package.combine) eller en enskild modell (geometry.read_model).

    Per rörstråk: punkterna längs röret (c/c ur regeltabellen, extra punkt vid böj, T-rör, ventil och anslutning,
    bort från håltagningar och balkkanter, till ingjutningsskenor), geometrin per punkt (gängstången enligt
    L = Z_UK - Z_CL - D/2 - t_iso - h_klammer - h_ankare, avstånd till vägg och undertak), lasten (rör, fyllt medium,
    isolering och punktlaster) mot gängstångens och ankarets tillåtna last, infästningen per bjälklagstyp, och
    delade bärverk (takjärn) för parallella rör på liknande höjd. Vertikala rör får fixpunkt och styrning."""
    rules = RL.merged(rules)
    pl, g, fm = rules["placement"], rules["geometry"], rules["formula"]
    ceil = ceilings(model.get("storeys") or [], manual_heights, rules)
    storey_index = {s["name"]: i for i, s in enumerate(model.get("storeys") or [])}
    zone_slab_types = zone_slab_types or {}
    has_k = bool((model.get("has") or {}).get("K")) or any(c.get("kind") in ("slab", "beam") for c in model.get("ceilings") or [])
    hor, risers, skipped, findings = [], [], [], []
    for p in model.get("pipes") or []:
        miss = [k for k, ok in (("system", p.get("system")), ("dimension", p.get("dn") or p.get("od")),
                                ("material", p.get("material") or p.get("code"))) if not ok]
        if miss and model.get("source") != "2D-ritning" and (model.get("has") or {}).get("VS"):
            skipped.append({"pipe": p["id"], "name": p.get("name"), "why": f"V4: saknar {', '.join(miss)}"})
            continue
        P = _P(p, rules)
        dz = abs(P.vec[2])
        if P.len < pl["min_pipe_length"]:
            skipped.append({"pipe": P.id, "name": p.get("name"), "why": f"kort rör ({P.len:.0f} mm) - hängs av grannrören"})
        elif dz / (P.len or 1) > pl["vertical_ratio"]:
            (risers if dz > 1000 and dz / (P.len or 1) > 0.9 else skipped).append(
                P if dz > 1000 and dz / (P.len or 1) > 0.9 else
                {"pipe": P.id, "name": p.get("name"), "why": "lutande rör - hängs av grannrören"})
        else:
            hor.append(P)
    fit_all = model.get("fittings") or []
    fittings = [np.array(f["at"], float) for f in fit_all]
    valves = [f for f in fit_all if f.get("kind") == "ventil"]
    mk = lambda key: _Grid([dict(it, bbox=it["bbox"]) for it in model.get(key) or [] if it.get("bbox")])
    grids = {"openings": mk("openings"), "channels": _Grid([dict(c, bbox=[min(c["start"][0], c["end"][0]), min(c["start"][1], c["end"][1]), 0,
                                                                          max(c["start"][0], c["end"][0]), max(c["start"][1], c["end"][1]), 0])
                                                              for c in model.get("channels") or []]),
             "beams": _Grid([c for c in model.get("ceilings") or [] if c.get("kind") == "beam" and c.get("bbox")]),
             "ceilings": _Grid([dict(c, bbox=c.get("bbox") or [c["xy"][0], c["xy"][1], c["zmin"], c["xy"][2], c["xy"][3], c.get("zmax", c["zmin"])])
                                for c in model.get("ceilings") or [] if c.get("xy")]),
             "walls": _Grid([w for w in model.get("walls") or [] if w.get("bbox")]),
             "suspended": _Grid([c for c in model.get("suspended") or [] if c.get("bbox")]),
             "obstacles": _Grid([o for o in model.get("obstacles") or [] if o.get("bbox")]),
             "pipes": _Grid([{"id": p["id"], "s": p["start"], "e": p["end"], "r": (p.get("od") or 0) / 2 + (p.get("insulation_mm") or 0),
                              "storey": p.get("storey"),
                              "bbox": [min(p["start"][0], p["end"][0]) - (p.get("od") or 0) / 2,
                                                       min(p["start"][1], p["end"][1]) - (p.get("od") or 0) / 2,
                                                       min(p["start"][2], p["end"][2]) - (p.get("od") or 0) / 2,
                                                       max(p["start"][0], p["end"][0]) + (p.get("od") or 0) / 2,
                                                       max(p["start"][1], p["end"][1]) + (p.get("od") or 0) / 2,
                                                       max(p["start"][2], p["end"][2]) + (p.get("od") or 0) / 2]}
                             for p in model.get("pipes") or []])}
    raw: list[dict[str, Any]] = []
    for ri, run in enumerate(_runs(hor, rules)):
        longest = max(run, key=lambda p: p.len)
        u = longest.dir
        v = np.array([-u[1], u[0]])
        o = longest.s[:2].copy()
        lo = min(min(np.dot(p.s[:2] - o, u), np.dot(p.e[:2] - o, u)) for p in run)
        o = o + u * lo
        st, iv, why = _stations(run, u, o, fittings, rules)
        smin = min(p.spacing for p in run)
        lat0 = float(np.dot(longest.s[:2] - o, v))
        point_at = lambda tt, o=o, u=u, v=v, lat0=lat0: o + u * tt + v * lat0
        moved = {}
        for t in st:
            t2, w2, fl = _adjust(t, point_at, grids, rules, smin)
            moved[round(t2, 1)] = (w2 or why.get(t), fl)
        st = sorted(moved)
        for t in st:
            here = []
            for p in run:
                a, b = iv[p.id]
                if a - 1 <= t <= b + 1:
                    pt = p.at(u, o, t)
                    here.append((float(np.dot(pt[:2] - o, v)), pt, p))
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
                        raw.append({"run": ri, "t": t, "pipes": grp, "u": u, "v": v, "o": o, "why": moved[t][0], "adj": moved[t][1]})
                        grp = []
                    grp.append(h)
                if grp:
                    raw.append({"run": ri, "t": t, "pipes": grp, "u": u, "v": v, "o": o, "why": moved[t][0], "adj": moved[t][1]})
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
        o_ = raw[pts[0][1]]
        a, b = sorted((float(np.dot(p.s[:2] - o_["o"], o_["u"])), float(np.dot(p.e[:2] - o_["o"], o_["u"]))))
        ts = [t for t, _ in pts]
        for i, (t, k) in enumerate(pts):
            left = (t - ts[i - 1]) / 2 if i else t - a
            right = (ts[i + 1] - t) / 2 if i + 1 < len(ts) else b - t
            trib[(k, p.id)] = max(0.0, left) + max(0.0, right)
    # punktlaster: varje ventil på närmaste upphängning av sitt rör
    point_kg: dict[int, float] = defaultdict(float)
    by_pipe_pts = {pid: sorted(v_) for pid, v_ in per_pipe.items()}
    pipe_obj = {p.id: p for p in hor}
    pg = _Grid([{"id": p.id, "bbox": [min(p.s[0], p.e[0]) - 300, min(p.s[1], p.e[1]) - 300, 0,
                                      max(p.s[0], p.e[0]) + 300, max(p.s[1], p.e[1]) + 300, 0]} for p in hor])
    for vlv in valves:
        x, y, z = vlv["at"]
        best = None
        for c in pg.near(x, y):
            p = pipe_obj[c["id"]]
            d = _seg_dist(np.array([x, y, z]), p.s, p.e)
            if d < p.od / 2 + 200 and (best is None or d < best[0]):
                best = (d, p)
        if not best or best[1].id not in by_pipe_pts:
            continue
        p = best[1]
        o_ = raw[by_pipe_pts[p.id][0][1]]
        tv = float(np.dot(np.array([x, y]) - o_["o"], o_["u"]))
        t_, k_ = min(by_pipe_pts[p.id], key=lambda q: abs(q[0] - tv))
        point_kg[k_] += float(vlv.get("mass_kg") or RL.table(rules["point_loads"]["ventil"], vlv.get("dn") or p.dn or 25, 5.0))
    hangers = []
    counters: dict[str, int] = defaultdict(int)
    raw.sort(key=lambda h: (storey_index.get(h["pipes"][0][2].storey, 99), h["run"], h["t"]))
    max_size = max(fm["max_rod_by_size"].values()) if fm.get("max_rod_by_size") else g["max_rod"]
    for h in raw:
        pipes_ = h["pipes"]
        storey = pipes_[0][2].storey
        code = storey_code(storey, storey_index.get(storey, 0))
        counters[code] += 1
        hid = f"{code}-{counters[code]:03d}"
        zone = f"stråk {h['run'] + 1}"
        flags: list[str] = []
        if h.get("adj"):
            flags.append(h["adj"])
        w = [x[0] for x in pipes_]
        ods = [x[2].od_eff for x in pipes_]
        centre_xy = h["o"] + h["u"] * h["t"] + h["v"] * ((min(w) + max(w)) / 2)
        cx, cy = float(centre_xy[0]), float(centre_xy[1])
        bottoms = [x[1][2] - x[2].od_eff / 2 for x in pipes_]
        top = max(x[1][2] + x[2].od_eff / 2 for x in pipes_)
        # Z_UK: underkant på närmaste bjälklag eller balk lodrätt ovanför (K-modellen), inom största gängstångslängd
        c = ceil.get(storey) or {"z": None, "source": "saknas"}
        manual = (manual_heights or {}).get(f"{storey}|{zone}", (manual_heights or {}).get(storey))
        slab = None
        over = [s_ for s_ in grids["ceilings"].near(cx, cy) if _inside(s_["bbox"], cx, cy) and s_["zmin"] > top + 20]
        if over:
            slab = min(over, key=lambda x: x["zmin"])
        if slab is not None and manual in (None, ""):
            c = {"z": float(slab["zmin"]), "source": f"modell: {slab.get('kind')} {slab.get('name') or slab['id']}".strip()}
        elif manual not in (None, ""):
            c = {"z": float(manual), "source": "manuell" if not has_k else "manuell (över K-modellen)"}
        elif has_k:
            c = {"z": None, "source": "saknas"}
            flags.append("V6: inget bjälklag eller balk ovanför punkten i K-modellen")
        elif estimate_above is not None:
            # uppskattad lokalt (anbudsskede utan K-modell): högsta röret på samma våning inom 2 m, plus ett avstånd
            near = [ob for ob in grids["pipes"].near(cx, cy, 2000) if ob.get("storey") == storey]
            tops = [max(ob["s"][2], ob["e"][2]) + ob["r"] for ob in near
                    if abs(ob["s"][2] - ob["e"][2]) < 300 and _inside(ob["bbox"], cx, cy, 2000)]
            zt = max([top] + [t_ for t_ in tops if t_ < top + 1500])
            c = {"z": float(zt + estimate_above), "source": "uppskattad (högsta röret inom 2 m + avstånd) - ej K-modell"}
        slab_kind = (_beam_slab_type(slab) if slab else None) or zone_slab_types.get(f"{storey}|{zone}") \
            or zone_slab_types.get(storey) or rules.get("default_slab_type")
        n_rods = 1 if len(pipes_) == 1 else 2
        load_kg = sum(x[2].kgm * trib.get((h["k"], x[2].id), x[2].spacing) / 1000.0 for x in pipes_) + point_kg.get(h["k"], 0.0)
        load_kn = round(load_kg * 9.81 / 1000.0, 3)
        rod = RL.rod_size(rules, load_kn / n_rods)
        if rod is None:
            flags.append(f"lasten {load_kn} kN överstiger gängstångens bärförmåga - konstruktören avgör")
            rod = max(rules["load"]["rod_capacity_kn"], key=lambda s_: rules["load"]["rod_capacity_kn"][s_])
        anchor = RL.anchor_for(rules, slab_kind, rod)
        if anchor.get("capacity_kn") and load_kn / n_rods * rules["load"]["safety_factor"] > anchor["capacity_kn"]:
            flags.append(f"lasten {load_kn / n_rods:.2f} kN per ankare över ankarets {anchor['capacity_kn']} kN i {anchor['slab_type']}")
        if anchor.get("note"):
            flags.append(anchor["note"])
        takjarn, clamps = None, []
        if n_rods == 1:
            x = pipes_[0]
            h_kl = float(RL.table(fm["clamp_height"], x[2].od_eff, g["clamp_base"]))
            # L = Z_UK - Z_CL - D/2 - t_iso - h_klammer - h_ankare
            L = (c["z"] - x[1][2] - x[2].od_eff / 2 - h_kl - anchor["height_mm"]) if c["z"] is not None else None
            kind, z_hang = "pendel", x[1][2] + x[2].od_eff / 2 + h_kl
        else:
            kind = "takjärn"
            h_kl = max(float(RL.table(fm["clamp_height"], x[2].od_eff, g["clamp_base"])) for x in pipes_)
            ptop = min(bottoms) - g["clamp_base"]
            pbot = ptop - g["profile_height"]
            length = _up((max(w) - min(w)) + max(ods) + 2 * g["overhang"], g["length_step"])
            x0 = (min(w) + max(w)) / 2 - length / 2
            for (wi, pt, p), b in zip(pipes_, bottoms):
                rise = round(b - g["clamp_base"] - ptop)
                clamps.append({"pipe": p.id, "at_mm": int(round((wi - x0) / g["hole_step"]) * g["hole_step"]),
                               "rise_mm": rise if rise > 10 else 0, "dn": p.dn, "od": p.od, "insulation_mm": p.ins})
                if rise > 100:
                    flags.append(f"rör {p.dn or p.od} ligger {rise} mm högre än de andra på takjärnet - egen nivå eller förhöjning")
            takjarn = {"profile": g["profile"], "length_mm": length, "rod_holes_mm": [25, length - 25],
                       "clamps": clamps, "top_z": round(ptop, 1)}
            L = (c["z"] - pbot - anchor["height_mm"] + g["rod_allowance"]) if c["z"] is not None else None
            z_hang = pbot
            if load_kn > rules["load"]["profile_capacity_kn"] / rules["load"]["safety_factor"]:
                flags.append(f"lasten {load_kn} kN på takjärnet över tillåten - kraftigare profil")
        rod_len = cut = None
        if L is None:
            if not has_k:
                flags.append("takhöjd saknas - ange underkant bjälklag för våningen/zonen")
        else:
            rod_len = round(L)
            cut = _up(max(L, 0) + float(fm.get("adjust_margin_mm") or 0), g["rod_step"])
            if L < g["min_rod"]:
                flags.append(f"röret ligger för nära bjälklaget ({rod_len} mm gängstång) - annan infästning")
            lim = (fm.get("max_rod_by_size") or {}).get(rod, g["max_rod"])
            if L > lim:
                kind = "konsol" if L > max_size else kind
                flags.append(f"gängstång {rod_len} mm över tillåtna {lim} mm för {rod} - {fm.get('konsol_text')}")
        if c["z"] is not None and z_hang > c["z"]:
            flags.append("röret ligger över bjälklaget i modellen - kontrollera höjden")
        rods = [{"size": rod, "length_mm": cut, "calc_mm": rod_len,
                 "at_mm": (25 if i == 0 else (takjarn or {}).get("length_mm", 50) - 25) if takjarn else 0} for i in range(n_rods)]
        # avstånd till vägg (A-modellen) och till undertaket
        wall = None
        for wl in grids["walls"].near(cx, cy, 3000):
            if not wl.get("segment"):
                continue
            d = _seg_dist(np.array([cx, cy]), np.array(wl["segment"][0]), np.array(wl["segment"][1])) - (wl.get("thickness") or 0) / 2
            if wall is None or d < wall["mm"]:
                wall = {"mm": max(0, round(d)), "id": wl["id"], "name": wl.get("name") or ""}
        under = None
        for sc in grids["suspended"].near(cx, cy):
            if _inside(sc["bbox"], cx, cy) and sc["bbox"][5] < top + 500:
                d = round(min(bottoms) - sc["bbox"][5])
                if under is None or d < under["mm"]:
                    under = {"mm": d, "id": sc["id"]}
        if under and under["mm"] < 0:
            flags.append(f"röret går {abs(under['mm'])} mm ner i undertaket {under['id']}")
        # V9: gängstängerna mot andra objekt i modellerna
        rod_xy = [(cx, cy)] if n_rods == 1 else [tuple(centre_xy + h["v"] * (r_["at_mm"] - takjarn["length_mm"] / 2)) for r_ in rods]
        carried = {x[2].id for x in pipes_}
        collisions = []
        m_col = float((rules.get("clearances") or {}).get("collision_mm", 10))
        if c["z"] is not None:
            for rx, ry in rod_xy:
                for grid_name in ("obstacles", "pipes"):
                    for ob in grids[grid_name].near(rx, ry, m_col):
                        if ob["id"] in carried:
                            continue
                        b = ob["bbox"]
                        if not (_inside(b, rx, ry, m_col) and b[5] > z_hang and b[2] < c["z"]):
                            continue
                        if grid_name == "pipes":
                            # ett rör: verkligt avstånd från gängstången till rörets axel, och rörets höjd just där
                            ps_, pe_ = np.array(ob["s"]), np.array(ob["e"])
                            d2 = pe_[:2] - ps_[:2]
                            lam = float(np.clip(np.dot(np.array([rx, ry]) - ps_[:2], d2) / (np.dot(d2, d2) or 1.0), 0, 1))
                            q = ps_ + (pe_ - ps_) * lam
                            if np.linalg.norm(q[:2] - np.array([rx, ry])) > ob["r"] + m_col or not (z_hang < q[2] < c["z"]):
                                continue
                        collisions.append(ob["id"])
        if collisions:
            flags.append(f"V9: gängstången kolliderar med {len(set(collisions))} objekt ({', '.join(sorted(set(collisions))[:3])})")
        hanger = {
            "id": hid, "project": project, "revision": revision, "storey": storey, "zone": zone,
            "run": h["run"], "station_mm": round(h["t"]), "kind": kind,
            "position": {"x": round(cx), "y": round(cy), "z": round(c["z"]) if c["z"] is not None else None},
            "reference": {"run_start": [round(float(x)) for x in h["o"]], "along_run_mm": round(h["t"]),
                          "text": (f"{wall['mm']} mm från vägg {wall['name'] or wall['id']}" if wall else
                                   f"{round(h['t'])} mm längs stråk {h['run'] + 1} från dess början")},
            "wall": wall, "ceiling_clearance": under,
            "pipes": [{"id": p.id, "dn": p.dn, "od": p.od, "insulation_mm": p.ins, "material": p.material, "system": p.system,
                       "centre_z": round(float(pt[2])), "spacing_rule": p.spacing_rule,
                       "hung_length_mm": round(trib.get((h["k"], p.id), 0))} for _, pt, p in pipes_],
            "ceiling_z": round(c["z"]) if c["z"] is not None else None, "height_source": c["source"],
            "slab": {"id": slab["id"], "type": slab_kind, "name": slab.get("name")} if slab else {"id": None, "type": slab_kind},
            "takjarn": takjarn, "rods": rods, "load_kn": load_kn, "point_load_kg": round(point_kg.get(h["k"], 0.0), 1),
            "anchor": anchor["text"], "anchor_info": anchor,
            "finish": rules["environment"]["finish"].get(rules["environment"]["default"], ""),
            "placed_because": h.get("why") or "klamringsavstånd", "collisions": sorted(set(collisions))[:20],
            "flags": flags, "status": "föreslagen", "history": [], "approved": {},
        }
        unknown = [p for _, _, p in pipes_ if p.material == "okänt"]
        if unknown:
            flags.append(f"materialet okänt för {', '.join(sorted({p.raw.get('name') or p.id for p in unknown}))[:80]} - "
                         f"försiktigt klamringsavstånd {rules['spacing']['okänt'][0][1]} mm")
        if model.get("source") == "2D-ritning":
            hanger["height_source"] = ("antagen (2D-ritning)" if c["z"] is not None else "saknas")
            hanger["flags"].append("höjd ur 2D-ritning - mät på plats innan produktion")
        hanger["bom"] = bom(hanger, rules)
        hangers.append(hanger)
    # vertikala rör: fixpunkt och styrning per våningsplan (ingen gängstång)
    for P in risers:
        code = storey_code(P.storey, storey_index.get(P.storey, 0))
        counters[code] += 1
        mid = (P.s + P.e) / 2
        hr = {"id": f"{code}-{counters[code]:03d}", "project": project, "revision": revision, "storey": P.storey,
              "zone": "stigare", "run": -1, "station_mm": 0, "kind": "stigare",
              "position": {"x": round(float(mid[0])), "y": round(float(mid[1])), "z": round(float(mid[2]))},
              "reference": {"text": f"stigare {P.system} DN{P.dn or round(P.od)}, mitt på {abs(P.vec[2]):.0f} mm lodrätt rör"},
              "pipes": [{"id": P.id, "dn": P.dn, "od": P.od, "insulation_mm": P.ins, "material": P.material, "system": P.system,
                         "centre_z": round(float(mid[2])), "spacing_rule": "stigare: fixpunkt och styrning per våningsplan",
                         "hung_length_mm": round(P.len)}],
              "ceiling_z": None, "height_source": "stigare", "takjarn": None, "rods": [],
              "load_kn": round(P.kgm * P.len / 1000 * 9.81 / 1000, 3), "anchor": "Väggfäste/konsol mot schaktvägg",
              "finish": rules["environment"]["finish"].get(rules["environment"]["default"], ""),
              "placed_because": "vertikalt rör: fixpunkt per våningsplan", "collisions": [],
              "flags": ["stigare: fixpunkt och styrning - välj väggkonsol efter schaktet"], "status": "föreslagen",
              "history": [], "approved": {}, "slab": {"id": None, "type": None}, "wall": None, "ceiling_clearance": None}
        hr["bom"] = bom(hr, rules)
        hangers.append(hr)
    # kontrollrapportens V6 och V9 efter beräkningen
    from .package import finding
    v6 = [p["id"] for hh in hangers if any(f.startswith("V6") for f in hh["flags"]) for p in hh["pipes"]]
    if v6:
        findings.append(finding("V6", "stopp", "Bjälklag saknas ovanför",
                                f"{len(set(v6))} rör har upphängningspunkter utan bjälklag eller balk ovanför i K-modellen.",
                                sorted(set(v6)), per_pipe=True))
    v9 = [hh["id"] for hh in hangers if hh.get("collisions")]
    if v9:
        findings.append(finding("V9", "varning", "Kollision", f"{len(v9)} upphängningar kolliderar med andra objekt "
                                "(gängstång genom rör, kanal, balk eller pelare).",
                                sorted({c_ for hh in hangers for c_ in hh.get("collisions") or []}), hangers=v9[:200]))
    return {"hangers": hangers, "skipped": skipped + [dict(s_, why=s_.get("why")) for s_ in model.get("skipped") or []],
            "ceilings": ceil, "rules_version": rules.get("version"), "rules_verified": bool(rules.get("verified")),
            "n_pipes": len(model.get("pipes") or []), "n_hung_pipes": len(hor), "n_risers": len(risers),
            "runs": len({h["run"] for h in hangers if h["run"] >= 0}), "summary": summary(hangers, rules), "findings": findings}


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
    if h.get("kind") == "stigare":
        for p in h["pipes"]:
            od = round((p["od"] or 0) + 2 * (p.get("insulation_mm") or 0))
            out.append({"part": "fixpunkt", "text": f"Rörklammer {od} mm med fixpunkt", "qty": 1, "length_mm": None, "pipe": p["id"]})
            out.append({"part": "styrning", "text": f"Rörklammer {od} mm glidande (styrning)", "qty": 1, "length_mm": None, "pipe": p["id"]})
        out.append({"part": "konsol", "text": "Väggkonsol för stigare", "qty": 2, "length_mm": None})
        return _articles(out, rules)
    if h.get("kind") == "konsol":
        out.append({"part": "konsol", "text": (rules.get("formula") or {}).get("konsol_text") or "Konsol", "qty": 1, "length_mm": None})
    anchor = re.sub(r"\bM\d+\b", size, h.get("anchor") or "Takinfästning")
    out.append({"part": "infästning", "text": anchor, "qty": len(rods), "length_mm": None})
    out.append({"part": "mutter", "text": f"Mutter {size}", "qty": nuts, "length_mm": None})
    out.append({"part": "bricka", "text": f"Bricka {size}", "qty": 2 * len(rods), "length_mm": None})
    for cl in (h.get("takjarn") or {}).get("clamps") or []:
        if cl.get("rise_mm"):
            out.append({"part": "distans", "text": f"Distans/förhöjning {size} {cl['rise_mm']} mm under klammer", "qty": 1,
                        "length_mm": cl["rise_mm"], "pipe": cl["pipe"]})
    for p in h["pipes"]:
        # klammern väljs på ytterdiametern med isolering (V5: utan isolertjocklek på rördimensionen)
        od = round((p["od"] or 0) + 2 * (p.get("insulation_mm") or 0))
        out.append({"part": "rörklammer", "text": f"Rörklammer {od} mm {('med gummiinlägg ' if p['material'] != 'plast' else '')}{size}-anslutning".replace("  ", " "),
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


def volume_l(h: dict[str, Any]) -> float:
    """Hängarens volym packad (liter): takjärnet som en låda 50 x 50 mm, gängstängerna buntade, smådelarna."""
    v = 0.2
    for b in h.get("bom") or []:
        if b["part"] == "takjärn":
            v += b["length_mm"] / 1000 * 0.05 * 0.05 * 1000
        elif b["part"] == "gängstång" and b.get("length_mm"):
            v += b["qty"] * b["length_mm"] / 1000 * 0.015 * 0.015 * 1000
    return round(v, 2)


def etapp_of(h: dict[str, Any], etapper: dict[str, str] | None) -> str:
    """Leveransetappen för en hängare: angiven för "våning|zon" eller för våningen, annars ingen."""
    e = etapper or {}
    return e.get(f"{h.get('storey')}|{h.get('zone')}") or e.get(h.get("storey") or "") or ""


def pack(hangers: list[dict[str, Any]], rules: dict[str, Any] | None = None, by: str = "montage",
         etapper: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Kollin: per leveransetapp, våning och område (stråk), i montageordning, högst N hängare, M kg och V liter
    per kolli. Varje hängare får sin packsekvens (kolli-nummer, plats i kollit och etapp).

    by: "montage" (stråk och läge längs stråket, så att kollit tas ur i den ordning det monteras) eller "id"."""
    rules = RL.merged(rules)
    P = rules["packing"]
    etapper = etapper or {}
    keys = sorted({etapp_of(h, etapper) for h in hangers}, key=lambda x: (x == "", x))
    rank = {k: i for i, k in enumerate(keys)}
    if by == "montage":
        order = sorted(hangers, key=lambda h: (rank[etapp_of(h, etapper)], h["storey"] or "", h.get("run", 0),
                                               h.get("station_mm", 0)))
    else:
        order = sorted(hangers, key=lambda h: (rank[etapp_of(h, etapper)], h["storey"] or "", h["id"]))
    kollin: list[dict[str, Any]] = []
    max_l = float(P.get("max_volume_l_per_kolli") or 1e9)
    for h in order:
        kg, vol, et = weight_kg(h), volume_l(h), etapp_of(h, etapper)
        k = kollin[-1] if kollin else None
        if (not k or k["etapp"] != et or k["storey"] != h["storey"] or len(k["hangers"]) >= P["max_per_kolli"]
                or k["kg"] + kg > P["max_kg_per_kolli"] or k["l"] + vol > max_l):
            k = {"no": len(kollin) + 1, "etapp": et, "storey": h["storey"], "zone": h.get("zone"), "hangers": [],
                 "kg": 0.0, "l": 0.0}
            kollin.append(k)
        k["hangers"].append(h["id"])
        k["kg"] = round(k["kg"] + kg, 2)
        k["l"] = round(k["l"] + vol, 2)
        h["pack"] = {"kolli": k["no"], "seq": len(k["hangers"]), "etapp": et}
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


def apply_references(hangers: list[dict[str, Any]], refs: list[dict[str, Any]] | None) -> None:
    """Referensmått från valda väggar eller gridlinjer: en linje är {"name": "Grid 3", "axis": "x", "value": 12000}
    (x = konstant x, en linje i y-led). Varje hängare får avståndet till närmaste linje i var riktning, och
    referenstexten blir det montören mäter ifrån ("1 057 mm från Grid 3, 2 300 mm från Vägg A")."""
    refs = [r for r in (refs or []) if r.get("axis") in ("x", "y") and r.get("value") is not None]
    for h in hangers:
        ref = h.setdefault("reference", {})
        lines = []
        for axis in ("x", "y"):
            cands = [r for r in refs if r["axis"] == axis and (not r.get("storey") or r["storey"] == h.get("storey"))]
            if not cands or h["position"].get(axis) is None:
                continue
            r = min(cands, key=lambda r: abs(h["position"][axis] - float(r["value"])))
            lines.append({"name": r.get("name") or f"{axis} = {r['value']}", "axis": axis,
                          "mm": int(round(abs(h["position"][axis] - float(r["value"]))))})
        ref["lines"] = lines
        along = f"{ref.get('along_run_mm', h.get('station_mm', 0))} mm längs {h.get('zone') or 'stråket'} från dess början"
        ref["text"] = ", ".join(f"{l['mm']:,} mm från {l['name']}".replace(",", " ") for l in lines) or along


def estimate_heights(model: dict[str, Any], above_mm: float = 100.0) -> dict[str, float]:
    """Underkant bjälklag uppskattad per våning ur rörens högsta läge (för anbudsskedet, när K-modellen saknas):
    det högsta horisontella röret med isolering plus ett avstånd. Ett antagande - märks så och ersätts av K-modellen
    eller av uppmätt höjd."""
    tops: dict[str, list[float]] = defaultdict(list)
    for p in model.get("pipes") or []:
        s, e = np.array(p["start"]), np.array(p["end"])
        L = float(np.linalg.norm(e - s))
        if L < 300 or abs(e[2] - s[2]) / L > 0.15:
            continue
        tops[p.get("storey") or "?"].append(max(s[2], e[2]) + (p.get("od") or 0) / 2 + (p.get("insulation_mm") or 0))
    return {k: float(np.percentile(v, 98) + above_mm) for k, v in tops.items() if v}
