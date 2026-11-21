"""Rören i en IFC-modell som linjer i rummet: start, slut, dimension, material, system och våning.

Läser STEP själv (vvs_engine.ifc.reader) och räknar geometrin utan IfcOpenShell:

  placering    IfcLocalPlacement-kedjan (relativ placering i placering) till världskoordinater
  kropp        IfcExtrudedAreaSolid med cirkelprofil: axeln och radien läses exakt (Revits vanliga rör)
               IfcMappedItem: representationen genom sin transformation (Revits typbaserade export)
               IfcTriangulatedFaceSet / IfcPolygonalFaceSet / IfcFacetedBrep: axeln ur punkternas huvudriktning
  egenskaper   dimension (NominalDiameter, OuterDiameter, Size eller namnet), material, systemnamn

Allt i millimeter. Ett rör vars geometri inte går att läsa står med i redovisningen men inte bland rören -
det gissas inte fram.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import numpy as np

from ..ifc.reader import _args, _decode, _records, _ref

PIPES = ("IFCPIPESEGMENT", "IFCFLOWSEGMENT")
FITTINGS = ("IFCPIPEFITTING", "IFCFLOWFITTING", "IFCVALVE", "IFCFLOWCONTROLLER")
# det rören hängs i: bjälklag, tak och undertak (takhöjden vid hängaren läses ur deras undersida)
CEILINGS = ("IFCSLAB", "IFCSLABSTANDARDCASE", "IFCROOF", "IFCCOVERING")


class Model:
    def __init__(self, text_or_lines):
        lines = text_or_lines.splitlines() if isinstance(text_or_lines, str) else text_or_lines
        self.R = _records(lines)
        self._P: dict[int, list] = {}
        self._place: dict[int, np.ndarray] = {}
        self.unit = 1.0                              # till mm
        for i, (c, raw) in self.R.items():
            if c == "IFCSIUNIT" and ".LENGTHUNIT." in raw:
                a = self.a(i)
                self.unit = {".MILLI.": 1.0, ".CENTI.": 10.0, ".DECI.": 100.0}.get(a[2] if len(a) > 2 else "$", 1000.0)
                break

    def a(self, i: int | None) -> list:
        if i is None or i not in self.R:
            return []
        if i not in self._P:
            self._P[i] = _args(self.R[i][1])
        return self._P[i]

    def cls(self, i: int | None) -> str:
        return self.R[i][0] if i in self.R else ""

    # ------------------------------------------------------------ punkter och placeringar
    def point(self, i) -> np.ndarray:
        a = self.a(_ref(i) if isinstance(i, str) else i)
        c = a[0] if a and isinstance(a[0], list) else [0.0, 0.0, 0.0]
        c = [float(x) for x in c] + [0.0] * (3 - len(c))
        return np.array(c[:3]) * self.unit

    def direction(self, i, default) -> np.ndarray:
        i = _ref(i) if isinstance(i, str) else i
        if i is None or i not in self.R:
            return np.array(default, dtype=float)
        a = self.a(i)
        d = [float(x) for x in (a[0] if a and isinstance(a[0], list) else default)] + [0.0] * 3
        v = np.array(d[:3])
        n = np.linalg.norm(v)
        return v / n if n else np.array(default, dtype=float)

    def axis2(self, i) -> np.ndarray:
        """IfcAxis2Placement3D (eller 2D) som 4x4-matris."""
        i = _ref(i) if isinstance(i, str) else i
        m = np.eye(4)
        if i is None or i not in self.R:
            return m
        a = self.a(i)
        loc = self.point(a[0]) if a else np.zeros(3)
        if self.cls(i) == "IFCAXIS2PLACEMENT2D":
            x = self.direction(a[1] if len(a) > 1 else None, [1, 0, 0])
            z = np.array([0.0, 0.0, 1.0])
        else:
            z = self.direction(a[1] if len(a) > 1 else None, [0, 0, 1])
            x = self.direction(a[2] if len(a) > 2 else None, [1, 0, 0])
        x = x - z * np.dot(x, z)
        if np.linalg.norm(x) < 1e-9:
            x = np.array([1.0, 0, 0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
            x = x - z * np.dot(x, z)
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, y, z, loc
        return m

    def placement(self, i) -> np.ndarray:
        i = _ref(i) if isinstance(i, str) else i
        if i is None or i not in self.R:
            return np.eye(4)
        if i in self._place:
            return self._place[i]
        a = self.a(i)
        self._place[i] = np.eye(4)                   # skydd mot cykler
        parent = self.placement(a[0]) if a and a[0] not in (None, "$") else np.eye(4)
        m = parent @ self.axis2(a[1] if len(a) > 1 else None)
        self._place[i] = m
        return m

    def operator(self, i) -> np.ndarray:
        """IfcCartesianTransformationOperator3D som 4x4-matris."""
        i = _ref(i) if isinstance(i, str) else i
        m = np.eye(4)
        if i is None or i not in self.R:
            return m
        a = self.a(i)
        x = self.direction(a[0], [1, 0, 0]) if len(a) > 0 and a[0] not in (None, "$") else np.array([1.0, 0, 0])
        y = self.direction(a[1], [0, 1, 0]) if len(a) > 1 and a[1] not in (None, "$") else np.array([0, 1.0, 0])
        o = self.point(a[2]) if len(a) > 2 else np.zeros(3)
        s = float(a[3]) if len(a) > 3 and isinstance(a[3], float) else 1.0
        z = self.direction(a[4], [0, 0, 1]) if len(a) > 4 and a[4] not in (None, "$") else np.cross(x, y)
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x * s, y * s, z * s, o
        return m

    def profile_points(self, prof) -> np.ndarray | None:
        """Hörnen i en rektangel- eller polylinjeprofil, i profilens plan (z = 0)."""
        c, pa = self.cls(prof), self.a(prof)
        if c == "IFCRECTANGLEPROFILEDEF" and len(pa) > 4 and isinstance(pa[3], float) and isinstance(pa[4], float):
            P = self.axis2(pa[2]) if len(pa) > 2 else np.eye(4)
            x, y = pa[3] * self.unit / 2, pa[4] * self.unit / 2
            pts = np.array([[-x, -y, 0, 1], [x, -y, 0, 1], [x, y, 0, 1], [-x, y, 0, 1]], dtype=float)
            return (pts @ P.T)[:, :3]
        if c == "IFCARBITRARYCLOSEDPROFILEDEF" and len(pa) > 2:
            curve = _ref(pa[2])
            ca = self.a(curve)
            if self.cls(curve) == "IFCPOLYLINE" and ca and isinstance(ca[0], list):
                return np.array([self.point(p) for p in ca[0]])
            if self.cls(curve) == "IFCINDEXEDPOLYCURVE" and ca:
                pl = self.a(_ref(ca[0]))
                if pl and isinstance(pl[0], list):
                    pts = [[float(v) for v in p[:2]] + [0.0] for p in pl[0]]
                    return np.array(pts) * self.unit
        return None

    # ------------------------------------------------------------ kroppen
    def body(self, rep_id, T: np.ndarray, out: dict) -> None:
        """Samlar axlar (exakt) och punkter (för huvudriktning) ur en representation."""
        for item in (self.a(rep_id)[3] if len(self.a(rep_id)) > 3 and isinstance(self.a(rep_id)[3], list) else []):
            self.item(_ref(item), T, out)

    def item(self, i, T: np.ndarray, out: dict, depth: int = 0) -> None:
        if i is None or depth > 8:
            return
        c, a = self.cls(i), self.a(i)
        if c == "IFCMAPPEDITEM":
            src = self.a(_ref(a[0]))
            origin = self.axis2(src[0]) if src else np.eye(4)
            M = T @ self.operator(a[1]) @ origin
            if len(src) > 1:
                rep = self.a(_ref(src[1]))
                for it in (rep[3] if len(rep) > 3 and isinstance(rep[3], list) else []):
                    self.item(_ref(it), M, out, depth + 1)
        elif c == "IFCEXTRUDEDAREASOLID":
            P = T @ self.axis2(a[1])
            d = self.direction(a[2], [0, 0, 1])
            depth_ = float(a[3]) * self.unit if len(a) > 3 and isinstance(a[3], float) else 0.0
            prof = _ref(a[0])
            pa = self.a(prof)
            r = None
            if self.cls(prof) in ("IFCCIRCLEPROFILEDEF", "IFCCIRCLEHOLLOWPROFILEDEF") and len(pa) > 3:
                r = float(pa[3]) * self.unit
            pos = self.axis2(pa[2]) if len(pa) > 2 and self.cls(prof).startswith("IFCCIRCLE") else np.eye(4)
            start = (P @ np.append(pos[:3, 3], 1))[:3]
            dirw = P[:3, :3] @ d
            dirw = dirw / (np.linalg.norm(dirw) or 1)
            out["axes"].append((start, start + dirw * depth_, r))
            # en platta (rektangel eller sluten polylinje): hörnen nere och uppe, för utbredning och höjd
            corners = self.profile_points(prof)
            if corners is not None and out.get("want_profile"):
                base = (np.c_[corners, np.ones(len(corners))] @ P.T)[:, :3]
                out["points"].append(np.vstack([base, base + dirw * depth_]))
        elif c in ("IFCBOOLEANCLIPPINGRESULT", "IFCBOOLEANRESULT"):
            self.item(_ref(a[1]), T, out, depth + 1)
        elif c in ("IFCTRIANGULATEDFACESET", "IFCPOLYGONALFACESET"):
            pl = self.a(_ref(a[0]))
            if pl and isinstance(pl[0], list):
                pts = np.array([[float(v) for v in p[:3]] for p in pl[0]]) * self.unit
                out["points"].append((np.c_[pts, np.ones(len(pts))] @ T.T)[:, :3])
        elif c in ("IFCFACETEDBREP", "IFCMANIFOLDSOLIDBREP"):
            pts = []
            shell = self.a(_ref(a[0]))
            for f in (shell[0] if shell and isinstance(shell[0], list) else []):
                for b in (self.a(_ref(f))[0] if self.a(_ref(f)) else []):
                    loop = self.a(_ref(self.a(_ref(b))[0])) if self.a(_ref(b)) else []
                    for p in (loop[0] if loop and isinstance(loop[0], list) else []):
                        pts.append(self.point(p))
            if pts:
                P = np.array(pts)
                out["points"].append((np.c_[P, np.ones(len(P))] @ T.T)[:, :3])


def _axis_from_points(P: np.ndarray) -> tuple[np.ndarray, np.ndarray, float] | None:
    if len(P) < 4:
        return None
    c = P.mean(axis=0)
    u, s, vt = np.linalg.svd(P - c, full_matrices=False)
    d = vt[0]
    t = (P - c) @ d
    perp = np.linalg.norm((P - c) - np.outer(t, d), axis=1)
    return c + d * t.min(), c + d * t.max(), float(np.percentile(perp, 90))


DN_IN_NAME = re.compile(r"(?:DN\s*|Ø\s*|\b)(\d{2,3})(?:\s*x\s*[\d,.]+)?\b")


def pipes(text_or_lines) -> dict[str, Any]:
    """Rören (och rördelarnas lägen) i modellen. Returnerar {"pipes", "fittings", "storeys", "skipped"}."""
    M = Model(text_or_lines)
    R = M.R
    storeys = {}
    for i, (c, _) in R.items():
        if c == "IFCBUILDINGSTOREY":
            a = M.a(i)
            elev = float(a[9]) * M.unit if len(a) > 9 and isinstance(a[9], float) else None
            storeys[i] = {"name": a[2] if isinstance(a[2], str) and a[2] != "$" else f"#{i}", "elevation": elev}
    parent, where = {}, {}
    psets: dict[int, list[int]] = defaultdict(list)
    for i, (c, raw) in R.items():
        if c == "IFCRELAGGREGATES":
            a = M.a(i)
            for p in a[5] or []:
                parent[_ref(p)] = _ref(a[4])
        elif c == "IFCRELCONTAINEDINSPATIALSTRUCTURE":
            a = M.a(i)
            for e in a[4] or []:
                where[_ref(e)] = _ref(a[5])
        elif c == "IFCRELDEFINESBYPROPERTIES":
            a = M.a(i)
            for e in a[4] or []:
                psets[_ref(e)].append(_ref(a[5]))

    def storey_of(x):
        for _ in range(6):
            if x is None or x in storeys:
                return x
            x = parent.get(x)
        return None

    def props(e) -> dict[str, Any]:
        out = {}
        for ps in psets.get(e, []):
            a = M.a(ps)
            if M.cls(ps) == "IFCPROPERTYSET" and len(a) > 4:
                for pr in a[4] or []:
                    pa = M.a(_ref(pr))
                    if len(pa) > 2 and pa[2] not in (None, "$"):
                        out.setdefault(str(pa[0]).lower(), pa[2])
            elif M.cls(ps) == "IFCELEMENTQUANTITY" and len(a) > 5:
                for q in a[5] or []:
                    qa = M.a(_ref(q))
                    if len(qa) > 3:
                        out.setdefault("qto:" + str(qa[0]).lower(), qa[3])
        return out

    found, fittings, skipped, ceilings = [], [], [], []
    for i, (c, _) in R.items():
        if c not in PIPES and c not in FITTINGS and c not in CEILINGS:
            continue
        a = M.a(i)
        T = M.placement(a[5]) if len(a) > 5 else np.eye(4)
        out = {"axes": [], "points": [], "want_profile": c in CEILINGS}
        pds = M.a(_ref(a[6])) if len(a) > 6 else []
        for rep in (pds[2] if len(pds) > 2 and isinstance(pds[2], list) else []):
            ra = M.a(_ref(rep))
            if len(ra) > 1 and str(ra[1]).lower() in ("body", "axis", "facetation"):
                M.body(_ref(rep), T, out)
        name = a[2] if len(a) > 2 and isinstance(a[2], str) and a[2] != "$" else ""
        st = storey_of(where.get(i))
        if c in CEILINGS:
            if out["points"]:
                P = np.vstack(out["points"])
                ceilings.append({"id": a[0], "kind": c[3:].lower(), "name": _decode(name)[:60],
                                 "storey": (storeys.get(st) or {}).get("name"),
                                 "zmin": round(float(P[:, 2].min()), 1), "zmax": round(float(P[:, 2].max()), 1),
                                 "xy": [round(float(P[:, 0].min())), round(float(P[:, 1].min())),
                                        round(float(P[:, 0].max())), round(float(P[:, 1].max()))]})
            continue
        if c in FITTINGS:
            pts = [np.array(s) for s, e, r in out["axes"]] + [p.mean(axis=0) for p in out["points"]]
            if pts:
                fittings.append({"id": a[0], "kind": c[3:].lower(), "name": _decode(name)[:80],
                                 "at": [round(float(v), 1) for v in np.mean(pts, axis=0)], "storey": (storeys.get(st) or {}).get("name")})
            continue
        if out["axes"]:
            s, e, r = max(out["axes"], key=lambda x: np.linalg.norm(x[1] - x[0]))
        elif out["points"]:
            ax = _axis_from_points(np.vstack(out["points"]))
            if ax is None:
                skipped.append({"id": a[0], "name": name, "why": "för få punkter i geometrin"})
                continue
            s, e, r = ax
        else:
            skipped.append({"id": a[0], "name": name, "why": "ingen läsbar geometri"})
            continue
        p = props(i)
        od = None
        for k in ("outer diameter", "outsidediameter", "outerdiameter", "ytterdiameter"):
            if isinstance(p.get(k), float):
                od = p[k] * M.unit
        dn = None
        for k in ("nominaldiameter", "nominal diameter", "size", "dimension", "diameter"):
            v = p.get(k)
            if isinstance(v, float):
                dn = int(round(v * M.unit))
                break
            if isinstance(v, str) and re.search(r"\d", v):
                dn = int(re.search(r"(\d{2,3})", v).group(1)) if re.search(r"(\d{2,3})", v) else None
                break
        if dn is None:
            m = DN_IN_NAME.search(name or "")
            dn = int(m.group(1)) if m else (int(round(2 * r)) if r else None)
        material = str(p.get("material") or "")
        system = str(p.get("system name") or p.get("systemname") or p.get("system classification") or p.get("system type") or "")
        found.append({"id": a[0], "name": _decode(name)[:120], "start": [round(float(v), 1) for v in s],
                      "end": [round(float(v), 1) for v in e], "od": round(od or (2 * r if r else (dn or 0)), 1) or None,
                      "dn": dn, "material": _decode(material), "system": _decode(system),
                      "storey": (storeys.get(st) or {}).get("name"), "storey_elevation": (storeys.get(st) or {}).get("elevation")})
    return {"pipes": found, "fittings": fittings,
            "storeys": sorted(({"name": v["name"], "elevation": v["elevation"]} for v in storeys.values()),
                              key=lambda s: (s["elevation"] is None, s["elevation"] or 0)),
            "skipped": skipped, "unit_to_mm": M.unit, "ceilings": ceilings}
