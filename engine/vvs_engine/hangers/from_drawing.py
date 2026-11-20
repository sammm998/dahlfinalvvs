"""Rören ur en analyserad 2D-ritning (PDF), när det inte finns någon IFC-modell.

Ritningsläsningen ger varje bekräftat rör som en linje i planen (physical-pipes.json per blad) med system,
beteckning och dimension, och bladets skala. Beteckningen är SYSTEM-MATERIAL-DIMENSION (VS2-S13-35): materialet
står i ritningens teckenförklaring (S13 = stålrör tunnväggiga, E17 = plaströr PE).

En planritning säger inte på vilken höjd rören ligger. Höjden matas därför in: takets höjd och rörets avstånd under
taket, per blad eller för hela ritningen. Varje hängare får höjdkällan "antagen (2D-ritning)" och en flagga om
att mäta på plats, så att ingen pendellängd tas för given. Bara bekräftade rör används; rör i skrafferade
områden, utan skala eller med osäker skala står i redovisningen.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any

from . import rules as RL

USABLE_SCALE = ("VERIFIED", "BAR_ONLY", "CONFLICT", "TEXT_ONLY", "MANUAL")


def _load(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def legend_materials(root: str) -> dict[str, str]:
    """Rörtypskod -> materialtext ur ritningens teckenförklaring."""
    out = {}
    for e in (_load(os.path.join(root, "drawing-legend.json")) or {}).get("entries") or []:
        if e.get("role") == "material" and e.get("code"):
            out[str(e["code"]).upper().replace("O", "0") if re.fullmatch(r"[A-Z]+\d*O\d*", str(e["code"]).upper()) else str(e["code"]).upper()] = e.get("description") or ""
    return out


def _straight(points: list[list[float]], tol_deg: float = 2.0) -> list[tuple[list[float], list[float]]]:
    """En polylinje som raka bitar: punkter i samma riktning slås ihop."""
    pts = [p for i, p in enumerate(points) if i == 0 or (abs(p[0] - points[i - 1][0]) + abs(p[1] - points[i - 1][1])) > 1e-6]
    if len(pts) < 2:
        return []
    out, start = [], pts[0]
    for i in range(1, len(pts) - 1):
        a = math.atan2(pts[i][1] - start[1], pts[i][0] - start[0])
        b = math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
        d = abs((a - b + math.pi) % (2 * math.pi) - math.pi)
        if d > math.radians(tol_deg):
            out.append((start, pts[i]))
            start = pts[i]
    out.append((start, pts[-1]))
    return out


def sheet_name(root: str, page: int) -> str:
    return f"Blad {page + 1}"


def sheets_in_reading(root: str) -> list[dict[str, Any]]:
    """Bladen i en läsning med antalet bekräftade rör och skalan - för att välja vilka som ska hängas."""
    out = []
    d0 = os.path.join(root, "sheets")
    for n in sorted((int(x) for x in os.listdir(d0) if x.isdigit())) if os.path.isdir(d0) else []:
        d = os.path.join(d0, str(n))
        recs = (_load(os.path.join(d, "physical-pipes.json")) or {}).get("physical_pipes") or []
        sc = ((_load(os.path.join(d, "quantities.json")) or {}).get("scale") or {})
        conf = [r for r in recs if r.get("evidence_state") == "CONFIRMED"]
        if not recs:
            continue
        ratio = next((e.get("detail", {}).get("ratio") for e in sc.get("evidence") or [] if e.get("kind") == "scale_text"), None)
        out.append({"name": sheet_name(root, n), "page": n, "confirmed": len(conf), "pipes": len(recs),
                    "m": round(sum(float(r.get("total_m") or 0) for r in conf if isinstance(r.get("total_m"), (int, float))), 1),
                    "scale": f"1:{ratio}" if ratio else None, "scale_state": sc.get("state"),
                    "usable": bool(sc.get("meters_per_pdf_point")) and sc.get("state") in USABLE_SCALE})
    return out


def pipes_from_reading(root: str, heights: dict[str, Any] | None = None, drawing: str = "",
                       only: list[str] | None = None) -> dict[str, Any]:
    """Modellen i samma form som geometry.pipes, ur en ritningsläsning (resultatkatalogen).

    heights: {"ceiling_mm": 2700, "drop_mm": 300, "sheets": {"Blad 13": {"ceiling_mm": .., "drop_mm": ..}}}
    Rörets underkant = takhöjd - avstånd under tak. Saknas takhöjden ligger rören på 0 och hängarna flaggas."""
    h = heights or {}
    mats = legend_materials(root)
    sheets_dir = os.path.join(root, "sheets")
    pages = sorted((int(n) for n in os.listdir(sheets_dir) if n.isdigit()), key=int) if os.path.isdir(sheets_dir) else [0]
    pipes, skipped, storeys = [], [], []
    for page in pages:
        d = os.path.join(sheets_dir, str(page)) if os.path.isdir(sheets_dir) else root
        q = _load(os.path.join(d, "quantities.json")) or {}
        sc = q.get("scale") or {}
        mpp = sc.get("meters_per_pdf_point")
        recs = (_load(os.path.join(d, "physical-pipes.json")) or {}).get("physical_pipes") or []
        if not recs:
            continue
        name = sheet_name(root, page)
        if only is not None and name not in only:
            continue
        if not mpp or sc.get("state") not in USABLE_SCALE:
            skipped.append({"pipe": name, "name": f"{drawing} {name}".strip(), "why": f"bladet har ingen säker skala ({sc.get('state')})"})
            continue
        per = (h.get("sheets") or {}).get(name) or {}
        ceiling = per.get("ceiling_mm", h.get("ceiling_mm"))
        drop = float(per.get("drop_mm", h.get("drop_mm") or 300))
        storeys.append({"name": name, "elevation": None, "ceiling_mm": ceiling})
        k = float(mpp) * 1000.0
        for r in recs:
            if r.get("evidence_state") != "CONFIRMED":
                skipped.append({"pipe": r.get("physical_pipe_id"), "name": r.get("designation"),
                                "why": f"inte bekräftat på ritningen ({r.get('evidence_state')})"})
                continue
            des = r.get("designation") or ""
            parts = des.split("-")
            mcode = parts[1].upper() if len(parts) > 2 else ""
            mtext = mats.get(mcode, "")
            dn = r.get("dn")
            # avståndet gäller till rörets underkant: rör av olika dimension vilar på samma takjärn
            z = (float(ceiling) - drop + float(dn or 0) / 2) if ceiling not in (None, "") else 0.0
            for i, poly in enumerate(r.get("geometry") or []):
                for j, (a, b) in enumerate(_straight(poly)):
                    pipes.append({"id": f"{r['physical_pipe_id']}:{i}:{j}", "name": des, "dn": dn, "od": dn,
                                  "material": mtext or mcode, "system": r.get("system") or (parts[0] if parts else ""),
                                  "start": [round(a[0] * k, 1), round(-a[1] * k, 1), z],
                                  "end": [round(b[0] * k, 1), round(-b[1] * k, 1), z],
                                  "storey": name, "storey_elevation": None, "source": "2D-ritning",
                                  "drawing": drawing, "page": page, "drop_mm": drop})
    return {"pipes": pipes, "fittings": [], "storeys": storeys, "skipped": skipped, "unit_to_mm": 1.0,
            "source": "2D-ritning", "drop_mm": h.get("drop_mm"), "ceiling_mm": h.get("ceiling_mm")}


def ceilings_from(model: dict[str, Any]) -> dict[str, float]:
    """De inmatade takhöjderna per blad, i den form generate tar."""
    return {s["name"]: float(s["ceiling_mm"]) for s in model.get("storeys") or [] if s.get("ceiling_mm") not in (None, "")}


def material_summary(model: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in model.get("pipes") or []:
        k = RL.material_key(p.get("material"))
        out[k] = out.get(k, 0) + 1
    return out
