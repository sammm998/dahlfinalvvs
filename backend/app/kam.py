"""KAM: prisjustering för KAM-kund.

  GET    /api/kam/status                          vilka data simuleringen bygger på (prislista, matris, kunder)
  GET    /api/kam/cases                           mina ärenden (administratör: alla)
  POST   /api/kam/cases                           nytt ärende {kundnr, old_period, new_period}
  GET    /api/kam/cases/{id}                      ärendet med simuleringen räknad mot aktuell prislista och matris
  POST   /api/kam/cases/{id}/statistics           kundens artiklar ur fil (Dahlmenyns offertfil eller tabell)
  POST   /api/kam/cases/{id}/statistics/offers    kundens artiklar ur kundens offerter i tjänsten
  PUT    /api/kam/cases/{id}/proposal             kundavvikelser, extrarabatt, nettopriser, prisunderlag
  POST   /api/kam/cases/{id}/submit               säljaren skickar för attest
  POST   /api/kam/cases/{id}/approve|reject       säljledaren (administratör) attesterar
  POST   /api/kam/cases/{id}/register             SIMULERAD M3-registrering: kundens rabatter i tjänstens data
  GET    /api/kam/cases/{id}/export.xlsx?kind=analys|registrering|kund
  DELETE /api/kam/cases/{id}                      ett utkast tas bort

Ingen skarp koppling finns ännu. Statistiken (Y12MAN i M3) ersätts av en uppladdad fil eller kundens offerter,
prislistan och matrisen av prisfilen (offertdata), och registreringen skriver kundens rabatter och nettopriser
i tjänstens rabattdata - de gäller sedan direkt i offerterna.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from vvs_engine import kam as K

from . import offers as O
from .auth import current_admin, current_user
from .db import KamCase, Offer, User, get_db
from .storage import storage

router = APIRouter(tags=["kam"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXTRA_KEY = "kam/extra_rabatt.json"
_PRICES: dict[str, Any] = {"id": None, "map": {}}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _prices() -> dict[str, dict[str, Any]]:
    rows = O.data("prislista")
    if _PRICES["id"] != id(rows):
        _PRICES["map"] = {str(r["rsk"]): r for r in rows if r.get("rsk")}
        _PRICES["id"] = id(rows)
    return _PRICES["map"]


def _group_names() -> dict[str, str]:
    return {r["grupp"]: r.get("namn") or "" for r in O.data("grundrabatter") if r.get("grupp")}


def _extras() -> dict[str, float]:
    if not storage.exists(EXTRA_KEY):
        return {}
    with storage.open(EXTRA_KEY) as fh:
        return json.load(fh)


def _terms(kundnr: str) -> dict[str, Any]:
    t = O.customer_terms(kundnr) or {}
    return {"rabatter": t.get("rabatter") or {}, "netto": t.get("netto") or {},
            "extra": _extras().get(kundnr) or 0.0, "namn": t.get("namn") or "", "bonus": t.get("bonus")}


def _case(db: Session, user: User, cid: str) -> KamCase:
    c = db.get(KamCase, cid)
    if not c or (c.created_by != user.id and (user.role or "member") != "admin"):
        raise HTTPException(404, "Ärendet finns inte")
    return c


def _log(c: KamCase, user: User, what: str) -> None:
    c.history = [*(c.history or []), {"at": _now().isoformat(), "by": user.email, "what": what}]
    c.updated_at = _now()


def simulate(c: KamCase) -> dict[str, Any]:
    cost = {r["rsk"]: r["pris"] for r in O.data("inkopspriser") if r.get("pris") is not None}
    return K.simulate(c.statistics or [], _prices(), O.base_discounts(), _terms(c.kundnr), c.proposal or {},
                      cost, _group_names())


def _out(c: KamCase, sim: bool = True) -> dict[str, Any]:
    d = {k: getattr(c, k) for k in ("id", "kundnr", "kundnamn", "rabattsystem", "old_period", "new_period", "status",
                                    "statistics_source", "proposal", "comment", "history", "attest_saljare",
                                    "attest_saljledare")}
    d["created_at"] = c.created_at.isoformat() if c.created_at else None
    d["updated_at"] = c.updated_at.isoformat() if c.updated_at else None
    d["n_articles"] = len(c.statistics or [])
    d["simulated"] = True
    if sim:
        d["terms"] = _terms(c.kundnr)
        d["simulation"] = simulate(c) if c.statistics else None
    return d


@router.get("/api/kam/status")
def status(user: User = Depends(current_user)):
    return {"simulated": True, "rule_version": K.RULE_VERSION, "prislista": len(_prices()),
            "matris": len(O.base_discounts()), "kunder": len(O.data("kunder")), "kundrabatter": len(O.data("rabatter")),
            "nettopriser": len(O.data("nettopriser")), "inkopspriser": len(O.data("inkopspriser")),
            "margin_floor": K.DEFAULT_MARGIN_FLOOR,
            "note": "Ingen skarp koppling till M3: statistik, prislista och matris kommer ur uppladdade filer."}


@router.get("/api/kam/cases")
def list_cases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(KamCase)
    if (user.role or "member") != "admin":
        q = q.filter(KamCase.created_by == user.id)
    return {"cases": [_out(c, sim=False) for c in q.order_by(KamCase.updated_at.desc()).limit(200)]}


class NewCase(BaseModel):
    kundnr: str
    kundnamn: str = ""
    old_period: str = ""
    new_period: str = ""
    rabattsystem: str = "DAHL12"


def _period(p: str) -> str:
    p = (p or "").strip()
    if p and not re.fullmatch(r"\d{2}(0[1-9]|1[0-2])", p):
        raise HTTPException(422, "Ange prisdatum i formatet ÅÅMM")
    return p


@router.post("/api/kam/cases")
def create_case(body: NewCase, user: User = Depends(current_user), db: Session = Depends(get_db)):
    no = re.sub(r"\.0$", "", body.kundnr.strip())
    if not re.fullmatch(r"[0-9A-Za-z\-]{4,12}", no):
        raise HTTPException(422, "Detta är inte ett kundnummer")
    t = O.customer_terms(no) or {}
    system = body.rabattsystem.upper()
    c = KamCase(kundnr=no, kundnamn=body.kundnamn.strip() or t.get("namn") or "",
                rabattsystem=K.SYSTEMS.get(system, system if system in K.SYSTEMS.values() else "KAM12"),
                old_period=_period(body.old_period), new_period=_period(body.new_period), created_by=user.id,
                proposal={"avvikelser": {}, "extra": None, "netto": {}, "price_source": "prisfil",
                          "list_change_pct": None, "margin_floor": K.DEFAULT_MARGIN_FLOOR})
    _log(c, user, "Ärendet skapat")
    db.add(c)
    db.commit()
    return _out(c)


@router.get("/api/kam/cases/{cid}")
def get_case(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(_case(db, user, cid))


def _editable(c: KamCase) -> None:
    if c.status not in ("utkast", "avslagen"):
        raise HTTPException(409, "Ärendet är skickat för attest och kan inte ändras")


@router.post("/api/kam/cases/{cid}/statistics")
async def upload_statistics(cid: str, file: UploadFile = File(...), user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    c = _case(db, user, cid)
    _editable(c)
    raw = await file.read()
    if len(raw) > 30 * 1024 * 1024:
        raise HTTPException(413, "Filen är större än 30 MB")
    name = (file.filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xlsm")):
            st = await run_in_threadpool(K.statistics_from_xlsx, raw)
        else:
            st = K.statistics_from_rows(O._rows_from_file(file.filename or "", raw))
    except Exception as e:  # noqa: BLE001 - trasig eller skyddad fil
        raise HTTPException(400, f"Kunde inte läsa filen: {e}") from e
    if not st:
        raise HTTPException(422, "Hittade ingen rubrikrad med artikelnummer och antal (t.ex. Artnr, Ant)")
    c.statistics, c.statistics_source = st, file.filename or "fil"
    _log(c, user, f"Statistik inläst ur {c.statistics_source}: {len(st)} artiklar")
    db.commit()
    return _out(c)


@router.post("/api/kam/cases/{cid}/statistics/offers")
def statistics_from_offers(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _case(db, user, cid)
    _editable(c)
    acc: dict[str, dict[str, Any]] = {}
    offers = db.query(Offer).filter(Offer.customer_no == c.kundnr).all()
    for o in offers:
        for r in o.rows or []:
            rsk = str(r.get("rsk") or "").strip()
            if not rsk or not r.get("antal"):
                continue
            a = acc.setdefault(rsk, {"rsk": rsk, "antal": 0.0, "namn": r.get("text") or "", "grupp": r.get("rabattgrupp") or "",
                                     "enhet": r.get("enhet") or "", "brutto": r.get("brutto"), "r1": r.get("rabatt_pct"),
                                     "r2": None, "r3": None, "netto": r.get("netto"), "cp": r.get("inkop")})
            a["antal"] += float(r["antal"])
    if not acc:
        raise HTTPException(422, f"Kunden {c.kundnr} har inga offerter med artiklar i tjänsten")
    c.statistics, c.statistics_source = list(acc.values()), f"{len(offers)} offerter i tjänsten"
    _log(c, user, f"Statistik ur kundens offerter: {len(acc)} artiklar")
    db.commit()
    return _out(c)


class Proposal(BaseModel):
    avvikelser: dict[str, float | None] = {}
    extra: float | None = None
    netto: dict[str, float | None] = {}
    price_source: str = "prisfil"
    list_change_pct: float | None = None
    margin_floor: float = K.DEFAULT_MARGIN_FLOOR
    comment: str = ""


@router.put("/api/kam/cases/{cid}/proposal")
def set_proposal(cid: str, body: Proposal, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _case(db, user, cid)
    _editable(c)
    for k, v in body.avvikelser.items():
        if not re.fullmatch(r"[A-Za-z0-9]{2}|[A-Za-z0-9]{4}|[A-Za-z0-9]{6}", k):
            raise HTTPException(422, f"Kalkylgruppen {k} ska ha 2, 4 eller 6 tecken")
        if v is not None and not 0 <= v < 100:
            raise HTTPException(422, f"Rabatten för {k} ska vara 0-99 %")
    if body.extra is not None and not 0 <= body.extra < 100:
        raise HTTPException(422, "Extrarabatten ska vara 0-99 %")
    if body.price_source not in ("prisfil", "index"):
        raise HTTPException(422, "Prisunderlag ska vara prisfil eller index")
    c.proposal = {"avvikelser": {k.upper(): v for k, v in body.avvikelser.items()}, "extra": body.extra,
                  "netto": body.netto, "price_source": body.price_source, "list_change_pct": body.list_change_pct,
                  "margin_floor": body.margin_floor}
    c.comment = body.comment
    if c.status == "avslagen":
        c.status = "utkast"
    _log(c, user, "Förslaget ändrat")
    db.commit()
    return _out(c)


@router.post("/api/kam/cases/{cid}/submit")
def submit(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _case(db, user, cid)
    _editable(c)
    if not c.statistics:
        raise HTTPException(409, "Läs in kundens statistik först")
    sim = simulate(c)
    if sim["approval_level"] == "BLOCKERAD":
        raise HTTPException(409, "Förslaget ger pris under kostpris för " + ", ".join(sim["totals"]["under_cost"][:10]))
    c.status, c.attest_saljare = "attest", f"{user.name or user.email} {_now():%Y-%m-%d}"
    _log(c, user, f"Skickat för attest (nivå {sim['approval_level']}, ändring {sim['totals']['change_pct']} %)")
    db.commit()
    return _out(c)


class Decision(BaseModel):
    comment: str = ""


@router.post("/api/kam/cases/{cid}/approve")
def approve(cid: str, body: Decision, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    c = _case(db, admin, cid)
    if c.status != "attest":
        raise HTTPException(409, "Ärendet väntar inte på attest")
    if c.created_by == admin.id:
        raise HTTPException(403, "Säljledarens attest ska göras av en annan person än säljaren")
    if simulate(c)["approval_level"] == "BLOCKERAD":
        raise HTTPException(409, "Förslaget ger pris under kostpris med aktuell prislista")
    c.status, c.attest_saljledare = "godkand", f"{admin.name or admin.email} {_now():%Y-%m-%d}"
    _log(c, admin, "Attesterat av säljledare" + (f": {body.comment}" if body.comment else ""))
    db.commit()
    return _out(c)


@router.post("/api/kam/cases/{cid}/reject")
def reject(cid: str, body: Decision, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    c = _case(db, admin, cid)
    if c.status != "attest":
        raise HTTPException(409, "Ärendet väntar inte på attest")
    c.status = "avslagen"
    _log(c, admin, "Avslaget" + (f": {body.comment}" if body.comment else ""))
    db.commit()
    return _out(c)


def _store(kind: str, rows: list[dict[str, Any]], note: str) -> None:
    storage.put(O._key(kind), io.BytesIO(json.dumps({"file": note, "updated_at": _now().isoformat(), "rows": rows},
                                                     ensure_ascii=False).encode("utf-8")))
    O._CACHE.pop(kind, None)


@router.post("/api/kam/cases/{cid}/register")
def register(cid: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Simulerad M3-registrering: kundens nya rabatter och nettopriser ersätter de gamla i tjänstens rabattdata."""
    c = _case(db, admin, cid)
    if c.status != "godkand":
        raise HTTPException(409, "Ärendet måste vara attesterat innan det registreras")
    sim = simulate(c)
    terms = sim["new_terms"]
    note = f"KAM-ärende {c.id} ({c.kundnr})"
    rab = [r for r in O.data("rabatter") if r.get("kundnr") != c.kundnr]
    rab += [{"kundnr": c.kundnr, "grupp": k, "pct": v} for k, v in sorted(terms["avvikelser"].items())]
    _store("rabatter", rab, note)
    net = [r for r in O.data("nettopriser") if r.get("kundnr") != c.kundnr]
    net += [{"kundnr": c.kundnr, "rsk": k, "pris": v} for k, v in sorted(terms["netto"].items())]
    _store("nettopriser", net, note)
    ex = _extras()
    if terms["extra"]:
        ex[c.kundnr] = terms["extra"]
    else:
        ex.pop(c.kundnr, None)
    storage.put(EXTRA_KEY, io.BytesIO(json.dumps(ex).encode("utf-8")))
    c.status = "registrerad"
    _log(c, admin, f"Registrerat (simulerat): {len(terms['avvikelser'])} kundavvikelser, {len(terms['netto'])} nettopriser")
    db.commit()
    return _out(c)


@router.get("/api/kam/cases/{cid}/export.xlsx")
def export(cid: str, kind: str = "analys", user: User = Depends(current_user), db: Session = Depends(get_db)):
    if kind not in ("analys", "registrering", "kund"):
        raise HTTPException(422, "kind ska vara analys, registrering eller kund")
    c = _case(db, user, cid)
    if not c.statistics:
        raise HTTPException(409, "Läs in kundens statistik först")
    data = K.to_xlsx(_out(c, sim=False), simulate(c), kind)
    name = f"KAM_{c.kundnr}_{kind}_{dt.date.today().isoformat()}.xlsx"
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.delete("/api/kam/cases/{cid}")
def delete_case(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _case(db, user, cid)
    if c.status not in ("utkast", "avslagen"):
        raise HTTPException(409, "Bara utkast kan tas bort")
    db.delete(c)
    db.commit()
    return {"ok": True}
