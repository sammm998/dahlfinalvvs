"""Engångstömning av lagret, beställd av ägaren 2026-11-26 ("töm åt mig") när volymen blivit full.

Vid uppstart jämförs PURGE_ID med det som står i databasen. Står det inte där töms lagret på ritningar och
modeller med purge_files.purge_all (samma som knappen Administration → System → Töm alla ritningar och modeller)
och id:t skrivs; nästa uppstart gör ingenting. Ett nytt id betyder en ny tömning och ändras bara när ägaren ber om det.
Konton, projekt, prisfil, kunder, regler, katalog och CAD-blad står kvar."""
from __future__ import annotations

PURGE_ID = "2026-11-26-owner-requested-empty-storage"
MARKER = "purge_once"


def run(storage_root: str) -> dict | None:
    from .db import ServiceSetting, SessionLocal, init_db
    from .purge_files import purge_all
    init_db()
    with SessionLocal() as db:
        row = db.get(ServiceSetting, MARKER)
        if row is not None and (row.value or {}).get("v") == PURGE_ID:
            return None
        out = purge_all(db, storage_root)
        row = db.get(ServiceSetting, MARKER)
        value = {"v": PURGE_ID, "result": out}
        if row is None:
            db.add(ServiceSetting(key=MARKER, value=value, note="Engångstömning av ritningar och modeller beställd av ägaren"))
        else:
            row.value = value
        db.commit()
    print(f"[tömning] alla ritningar och modeller borttagna ({PURGE_ID}): {out}", flush=True)
    return out
