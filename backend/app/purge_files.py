"""Töm lagret på ritningar och modeller - när administratören ber om det (Administration → System).

Bort:     ritningar med analyser, resultat, markeringar och kalkyler; SmartHangers-uppsättningar med sina filer;
          tekniska beskrivningar, materiallistor och IFC-material; offerter (de byggde på det som tas bort);
          radiatorläsningar, cache och temporära filer.
Behålls:  konton, projekt (tomma), prisfil, kunder och rabatter (offer/), SmartHangers-reglerna, Dahls katalog,
          eget varumärke, CAD-blad som ritats i tjänsten, utbildningen och budgeten.

Görs bara på uttrycklig begäran: endpointen kräver administratör och att bekräftelsen skrivs ut."""
from __future__ import annotations

import shutil
from pathlib import Path

DROP_DIRS = ("drawings", "results", "radiators", "techspecs", "lists", "ifc", "cache", "tmp", "temp", "abt", "tb_ai")


def _size(p: Path) -> int:
    try:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size
    except OSError:
        return 0


def purge_all(db, storage_root: str) -> dict:
    from .db import AnalysisJob, Drawing, HangerSet, Offer, TechSpec
    from .purge import purge_drawing
    n = {"drawings": 0, "jobs": 0, "hanger_sets": 0, "tech_specs": 0, "offers": 0}
    for d in db.query(Drawing).all():
        purge_drawing(db, d)
        n["jobs"] += db.query(AnalysisJob).filter(AnalysisJob.drawing_id == d.id).delete(synchronize_session=False)
        db.delete(d)
        n["drawings"] += 1
    db.flush()
    n["offers"] = db.query(Offer).delete(synchronize_session=False)
    n["hanger_sets"] = db.query(HangerSet).delete(synchronize_session=False)
    n["tech_specs"] = db.query(TechSpec).delete(synchronize_session=False)
    db.commit()
    root = Path(storage_root)
    freed = 0
    if root.is_dir():
        for name in DROP_DIRS:
            p = root / name
            if p.exists():
                freed += _size(p)
                shutil.rmtree(p, ignore_errors=True)
        prefab = root / "prefab"
        if prefab.is_dir():
            for p in prefab.iterdir():
                if p.is_dir():                              # en uppsättnings filer; reglerna ligger som filer här
                    freed += _size(p)
                    shutil.rmtree(p, ignore_errors=True)
    return {**n, "freed_mb": round(freed / 1e6)}
