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
SLABS = ("IFCSLAB", "IFCSLABSTANDARDCASE", "IFCSLABELEMENTEDCASE", "IFCROOF")
BEAMS = ("IFCBEAM", "IFCBEAMSTANDARDCASE")
WALLS = ("IFCWALL", "IFCWALLSTANDARDCASE", "IFCCURTAINWALL")
OPENINGS = ("IFCOPENINGELEMENT", "IFCOPENINGSTANDARDCASE")
OBSTACLES = ("IFCDUCTSEGMENT", "IFCCABLECARRIERSEGMENT", "IFCCOLUMN", "IFCCOLUMNSTANDARDCASE")
CHANNELS = ("IFCBUILDINGELEMENTPROXY", "IFCDISCRETEACCESSORY", "IFCMECHANICALFASTENER")
CHANNEL_WORDS = re.compile(r"ingjut|halfen|\bhta\b|jordahl|cast.?in|ankarskena|montageskena", re.I)
FITTINGS = ("IFCPIPEFITTING", "IFCFLOWFITTING", "IFCVALVE", "IFCFLOWCONTROLLER")
CEILINGS = SLABS + BEAMS            # det rören hängs i (K-modellen): underkanten är Z_UK i gängstångens formel


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
        # olikformig skalning (MagiCAD): Scale gäller x, Scale2 y och Scale3 z
        s2 = float(a[5]) if self.cls(i).endswith("NONUNIFORM") and len(a) > 5 and isinstance(a[5], float) else s
        s3 = float(a[6]) if self.cls(i).endswith("NONUNIFORM") and len(a) > 6 and isinstance(a[6], float) else s
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x * s, y * s2, z * s3, o
        return m

    def shell_points(self, shells) -> np.ndarray | None:
        """Hörnen i en eller flera skal (IfcOpenShell/IfcClosedShell) - ytor av polyloopar."""
        ids = set()
        for sh in shells or []:
            sa = self.a(_ref(sh))
            for f in (sa[0] if sa and isinstance(sa[0], list) else []):
                fa = self.a(_ref(f))
                for b in (fa[0] if fa and isinstance(fa[0], list) else []):
                    ba = self.a(_ref(b))
                    loop = self.a(_ref(ba[0])) if ba else []
                    for p in (loop[0] if loop and isinstance(loop[0], list) else []):
                        ids.add(p)
        if not ids:
            return None
        return np.array([self.point(p) for p in ids])

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
        elif c in ("IFCSHELLBASEDSURFACEMODEL", "IFCFACEBASEDSURFACEMODEL"):
            P = self.shell_points(a[0] if a and isinstance(a[0], list) else [])
            if P is not None:
                out["points"].append((np.c_[P, np.ones(len(P))] @ T.T)[:, :3])
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


HEADER = re.compile(r"FILE_NAME\s*\(\s*'((?:[^']|'')*)'\s*,\s*'([^']*)'\s*,\s*\(([^)]*)\)\s*,\s*\(([^)]*)\)\s*,\s*'([^']*)'\s*,\s*'([^']*)'", re.S)
SCHEMA = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'")
REVISION = re.compile(r"(?:^|[-_ ])(?:rev(?:ision)?\.?\s*)?([A-Z]|\d{1,2})$", re.I)
SLAB_TYPES = [("HD/F", r"hd\s*/?\s*f|hdf|håldäck|hollow.?core|\bhd\b"), ("KL-trä", r"\bkl\b|kl-?trä|clt|massivträ|krysslimm"),
              ("Trapetsplåt", r"trapets|\btrp\b|plåtbjälklag|profilplåt|deck"),
              ("Platsgjutet", r"platsgjut|betong|concrete|\bbtg\b|plattbärlag|filigran|bjälklag")]


def slab_type(text: str) -> str | None:
    """Bjälklagstypen ur namn, typ och material: HD/F, KL-trä, trapetsplåt eller platsgjutet. None om okänd (V7)."""
    for name, rx in SLAB_TYPES:
        if re.search(rx, text or "", re.I):
            return name
    return None


def header(text: str) -> dict[str, Any]:
    """Filhuvudet: filnamn, datum, upphov, program och schema - revision och spårbarhet (V10)."""
    head = text[:20000]
    m = HEADER.search(head)
    sc = SCHEMA.search(head)
    out = {"file_name": _decode(m.group(1)) if m else "", "timestamp": m.group(2) if m else "",
           "author": _decode(m.group(3).replace("'", "").strip()) if m else "",
           "organization": _decode(m.group(4).replace("'", "").strip()) if m else "",
           "application": _decode(m.group(5)) if m else "", "schema": sc.group(1) if sc else ""}
    base = re.sub(r"\.ifc$", "", out["file_name"], flags=re.I)
    r = REVISION.search(base)
    out["revision"] = r.group(1) if r and len(base) > 3 else ""
    out["frozen"] = bool(re.search(r"fryst|frozen|samordnad|coordinated|f[öo]r produktion|bygghandling", head, re.I))
    return out


def read_model(text_or_lines, discipline: str | None = None, want: set[str] | None = None) -> dict[str, Any]:
    """En IFC-fil läst till det Smart Hangers räknar med.

    VS: rör (axel, ytterdiameter, isolering, material/serie, system, fall), rördelar och ventiler (punkter och
        punktlaster). K: bjälklag, balkar och håltagningar (underkant, utbredning, bjälklagstyp), ingjutningsskenor.
    A: väggar (yta i plan), undertak. Andra discipliner: kanaler och kabelstegar som hinder för kollisionstestet.
    Alla filer: nollpunkt, våningsplan, längdenhet och filhuvud (revision, datum) för valideringen.
    want: begränsa till {"pipes", "structure", "architecture", "obstacles"}; utan want läses allt."""
    text = text_or_lines if isinstance(text_or_lines, str) else "\n".join(text_or_lines)
    M = Model(text)
    R = M.R
    want = want or {"pipes", "structure", "architecture", "obstacles"}
    unit_found = False
    for i, (c, raw) in R.items():
        if c == "IFCUNITASSIGNMENT":
            for u in M.a(i)[0] or []:
                ua = M.a(_ref(u))
                if M.cls(_ref(u)) == "IFCSIUNIT" and len(ua) > 1 and ua[1] == ".LENGTHUNIT.":
                    M.unit = {".MILLI.": 1.0, ".CENTI.": 10.0, ".DECI.": 100.0}.get(ua[2] if len(ua) > 2 else "$", 1000.0)
                    unit_found = True
            break
    if not unit_found:
        unit_found = any(c == "IFCSIUNIT" and ".LENGTHUNIT." in raw for c, raw in R.values())
    storeys, site = {}, None
    for i, (c, _) in R.items():
        if c == "IFCBUILDINGSTOREY":
            a = M.a(i)
            elev = float(a[9]) * M.unit if len(a) > 9 and isinstance(a[9], float) else None
            storeys[i] = {"name": _decode(a[2]) if isinstance(a[2], str) and a[2] != "$" else f"#{i}", "elevation": elev,
                          "placed_z": round(float(M.placement(a[5])[2, 3]), 1) if len(a) > 5 else None}
        elif c == "IFCSITE" and site is None:
            a = M.a(i)
            P = M.placement(a[5]) if len(a) > 5 else np.eye(4)
            site = {"origin": [round(float(v), 1) for v in P[:3, 3]], "x_axis": [round(float(v), 6) for v in P[:3, 0]], "map": None}
        elif c == "IFCMAPCONVERSION":
            a = M.a(i)
            vals = [float(v) if isinstance(v, float) else None for v in a[2:5]] if len(a) > 4 else []
            site = site or {"origin": [0, 0, 0], "x_axis": [1, 0, 0], "map": None}
            site["map"] = vals
    parent, where, types, mats, groups, covers = {}, {}, {}, {}, defaultdict(list), set()
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
        elif c == "IFCRELDEFINESBYTYPE":
            a = M.a(i)
            for e in a[4] or []:
                types[_ref(e)] = _ref(a[5])
        elif c == "IFCRELASSOCIATESMATERIAL":
            a = M.a(i)
            for e in a[4] or []:
                mats[_ref(e)] = _ref(a[5])
        elif c == "IFCRELASSIGNSTOGROUP":
            a = M.a(i)
            g = M.a(_ref(a[6])) if len(a) > 6 else []
            gname = _decode(g[2]) if len(g) > 2 and isinstance(g[2], str) and g[2] != "$" else ""
            for e in a[4] or []:
                groups[_ref(e)].append(gname)
        elif c == "IFCRELCOVERSBLDGELEMENTS":
            a = M.a(i)
            for e in a[5] or []:
                covers.add(_ref(e))                       # isolering som täcker ett rör: inget undertak

    def storey_of(x):
        for _ in range(6):
            if x is None or x in storeys:
                return x
            x = parent.get(x)
        return None

    def props(e) -> dict[str, Any]:
        out = {}
        for ps in psets.get(e, []) + psets.get(types.get(e), []):
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

    def type_text(e) -> str:
        parts = []
        a = M.a(e)
        for k in (2, 4):
            if len(a) > k and isinstance(a[k], str) and a[k] != "$":
                parts.append(_decode(a[k]))
        t = types.get(e)
        if t is not None and len(M.a(t)) > 2 and isinstance(M.a(t)[2], str):
            parts.append(_decode(M.a(t)[2]))
        m = mats.get(e)
        seen = 0
        while m is not None and seen < 4:
            seen += 1
            ma = M.a(m)
            cm = M.cls(m)
            if cm == "IFCMATERIAL":
                parts.append(_decode(ma[0]) if ma else "")
                break
            nxt = next((_ref(v) for v in ma if isinstance(v, str) and v.startswith("#")), None)
            if cm in ("IFCMATERIALLAYERSET", "IFCMATERIALLIST", "IFCMATERIALCONSTITUENTSET") and ma and isinstance(ma[0], list):
                nxt = _ref(ma[0][0]) if ma[0] else None
                if cm == "IFCMATERIALLAYERSET" and len(ma) > 1 and isinstance(ma[1], str) and ma[1] != "$":
                    parts.append(_decode(ma[1]))
            m = nxt
        return " ".join(p for p in parts if p)

    def geometry(i, a, want_profile=False):
        T = M.placement(a[5]) if len(a) > 5 else np.eye(4)
        out = {"axes": [], "points": [], "want_profile": want_profile}
        pds = M.a(_ref(a[6])) if len(a) > 6 else []
        for rep in (pds[2] if len(pds) > 2 and isinstance(pds[2], list) else []):
            ra = M.a(_ref(rep))
            if len(ra) > 1 and str(ra[1]).lower() in ("body", "axis", "facetation"):
                M.body(_ref(rep), T, out)
        return out

    def bbox(out) -> list[float] | None:
        pts = [np.vstack([s_, e_]) for s_, e_, _ in out["axes"]] + list(out["points"])
        if not pts:
            return None
        P = np.vstack(pts)
        lo, hi = P.min(axis=0), P.max(axis=0)
        return [round(float(v), 1) for v in (*lo, *hi)]

    found, fittings, skipped, ceilings, slabs, openings, walls, suspended, obstacles, channels = ([] for _ in range(10))
    for i, (c, raw) in R.items():
        cat = ("pipe" if c in PIPES else "fitting" if c in FITTINGS else "slab" if c in SLABS else "beam" if c in BEAMS
               else "opening" if c in OPENINGS else "wall" if c in WALLS
               else "ceiling" if c == "IFCCOVERING" and ".CEILING." in raw and i not in covers
               else "obstacle" if c in OBSTACLES else "channel" if c in CHANNELS else None)
        if cat is None:
            continue
        if cat in ("pipe", "fitting") and "pipes" not in want:
            continue
        if cat in ("slab", "beam", "opening", "channel") and "structure" not in want:
            continue
        if cat in ("wall", "ceiling") and "architecture" not in want:
            continue
        if cat == "obstacle" and "obstacles" not in want:
            continue
        a = M.a(i)
        name = _decode(a[2]) if len(a) > 2 and isinstance(a[2], str) and a[2] != "$" else ""
        if cat == "channel" and not CHANNEL_WORDS.search(type_text(i)):
            continue
        out = geometry(i, a, want_profile=cat in ("slab", "beam", "opening", "wall", "ceiling", "obstacle", "channel"))
        st = storey_of(where.get(i))
        sname = (storeys.get(st) or {}).get("name")
        if cat != "pipe":
            bb = bbox(out)
            if bb is None:
                continue
            base = {"id": a[0], "name": name[:80], "storey": sname, "bbox": bb}
            if cat == "fitting":
                p = props(i)
                kind = str(p.get("parttype") or p.get("producttype") or name or c[3:]).lower()
                mass = next((p[k] for k in ("mass", "weight", "vikt", "qto:netweight", "qto:grossweight") if isinstance(p.get(k), float)), None)
                fittings.append({**base, "kind": "ventil" if c in ("IFCVALVE", "IFCFLOWCONTROLLER") or "valve" in kind or "ventil" in kind
                                 else "böj" if re.search(r"bend|böj|elbow", kind) else "t-rör" if re.search(r"tee|t-rör|branch|gren", kind)
                                 else "rördel", "at": [round((bb[0] + bb[3]) / 2, 1), round((bb[1] + bb[4]) / 2, 1), round((bb[2] + bb[5]) / 2, 1)],
                                 "dn": int(p["diameter"] * M.unit) if isinstance(p.get("diameter"), float) else None, "mass_kg": mass})
            elif cat in ("slab", "beam"):
                tt = type_text(i)
                ceilings.append({**base, "kind": cat, "zmin": bb[2], "zmax": bb[5], "xy": [bb[0], bb[1], bb[3], bb[4]],
                                 "type_text": tt[:120], "slab_type": slab_type(tt)})
            elif cat == "opening":
                openings.append(base)
            elif cat == "wall":
                P = np.vstack([np.vstack([s_, e_]) for s_, e_, _ in out["axes"]] + list(out["points"]))
                ax = _axis_from_points(np.c_[P[:, :2], np.zeros(len(P))]) if len(P) >= 4 else None
                seg = [[round(float(ax[0][0]), 1), round(float(ax[0][1]), 1)], [round(float(ax[1][0]), 1), round(float(ax[1][1]), 1)]] if ax else None
                walls.append({**base, "segment": seg, "thickness": round(2 * ax[2], 1) if ax else None})
            elif cat == "ceiling":
                suspended.append({**base, "ztop": bb[5], "zmin": bb[2]})
            elif cat == "channel":
                P = np.vstack([np.vstack([s_, e_]) for s_, e_, _ in out["axes"]] + list(out["points"]))
                ax = _axis_from_points(P) if len(P) >= 4 else None
                if ax:
                    channels.append({**base, "start": [round(float(v), 1) for v in ax[0]], "end": [round(float(v), 1) for v in ax[1]]})
            elif cat == "obstacle":
                obstacles.append({**base, "kind": c[3:].lower()})
            continue
        if out["axes"]:
            s_, e_, r = max(out["axes"], key=lambda x: np.linalg.norm(x[1] - x[0]))
        elif out["points"]:
            ax = _axis_from_points(np.vstack(out["points"]))
            if ax is None:
                skipped.append({"id": a[0], "name": name, "why": "för få punkter i geometrin"})
                continue
            s_, e_, r = ax
        else:
            skipped.append({"id": a[0], "name": name, "why": "ingen läsbar geometri"})
            continue
        p = props(i)
        kind = str(p.get("parttype") or p.get("producttype") or "").lower()
        if re.search(r"duct|kanal|air|luft|cable|kabel", kind):
            bb = bbox(out)
            if bb:
                obstacles.append({"id": a[0], "name": name[:80], "storey": sname, "bbox": bb, "kind": "kanal"})
            continue
        num = lambda *keys: next((float(p[k]) for k in keys if isinstance(p.get(k), (int, float))), None)
        od = num("outer diameter", "outsidediameter", "outerdiameter", "ytterdiameter", "diameter")
        od = od * M.unit if od else None
        dn = None
        for k in ("nominaldiameter", "nominal diameter", "connectionsize", "connectionsize_mm", "size", "dimension"):
            v = p.get(k)
            if isinstance(v, float):
                dn = int(round(v * M.unit))
                break
            if isinstance(v, str) and re.search(r"(\d{2,3})", v):
                dn = int(re.search(r"(\d{2,3})", v).group(1))
                break
        if dn is None:
            m = DN_IN_NAME.search(name or "")
            dn = int(m.group(1)) if m else (int(round(od)) if od else (int(round(2 * r)) if r else None))
        ins_v = next((p[k] for k in ("insulationthickness", "insulation_thickness_mm", "insulation thickness", "isolertjocklek",
                                     "isolering") if k in p), None)
        insulation = float(ins_v) * M.unit if isinstance(ins_v, (int, float)) else None
        material = " ".join(_decode(str(p[k])) for k in ("seriesdescription", "typename", "productserie", "material", "sewerseries")
                            if isinstance(p.get(k), str) and p.get(k))[:160]
        if not material.strip():
            material = type_text(i)
        code = str(p.get("typeid") or p.get("user code") or p.get("material") or "")
        system = str(p.get("systemname") or p.get("system name") or p.get("systemid") or p.get("system classification") or "") \
            or next((g for g in groups.get(i, []) if g), "")
        fall = num("fall_per_mill", "fall_prm", "fall", "slope")
        found.append({"id": a[0], "name": _decode(name)[:120] or _decode(str(p.get("typename") or ""))[:120],
                      "start": [round(float(v), 1) for v in s_], "end": [round(float(v), 1) for v in e_],
                      "od": round(od or (2 * r if r else (dn or 0)), 1) or None, "dn": dn,
                      "material": _decode(material), "code": _decode(code), "system": _decode(system),
                      "insulation_mm": insulation, "fall_per_mill": fall,
                      # MagiCAD exporterar ofta hela huset i ett IFC-våningsplan och skriver våningen på varje rör
                      "storey": _decode(str(p.get("storeyname") or p.get("storey") or "")).strip() or sname,
                      "ifc_storey": sname, "storey_elevation": (storeys.get(st) or {}).get("elevation")})
    st_list = [{"name": v["name"], "elevation": v["elevation"]} for v in storeys.values()]
    known = {x["name"] for x in st_list}
    zs: dict[str, list[float]] = defaultdict(list)
    for p in found:
        if p["storey"] and p["storey"] not in known:
            zs[p["storey"]].append(min(p["start"][2], p["end"][2]))
    for n, z in zs.items():
        st_list.append({"name": n, "elevation": None, "z_min": round(min(z)), "from": "rörens våningsegenskap"})
    return {"discipline": discipline, "header": header(text), "unit_to_mm": M.unit, "unit_found": unit_found,
            "site": site, "pipes": found, "fittings": fittings,
            "storeys": sorted(st_list, key=lambda s: (s.get("elevation") is None, s.get("elevation") or s.get("z_min") or 0, s["name"])),
            "skipped": skipped, "ceilings": ceilings, "openings": openings, "walls": walls, "suspended": suspended,
            "obstacles": obstacles, "channels": channels}


def pipes(text_or_lines) -> dict[str, Any]:
    """Hela modellen (bakåtkompatibelt namn): se read_model."""
    return read_model(text_or_lines)
