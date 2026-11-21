"""Offertsteget: den färdiga matchningen blir en materialoffert eller en kalkyloffert.

Ersätter flödet i Excel med Prixel och Dahlmenyn: välj kund med kundnummer, kundens rabattmatris läses in, priset
räknas per rad (bruttopris minus kundens rabatt för artikelns rabattgrupp, eller kundens nettopris), bonusen hämtas
med en knapp, och inköpspris och marginal visas per rad och totalt - internt, aldrig på kundens offert.

Data som M3 ska leverera, tills kopplingen finns: laddas upp som filer (Excel eller CSV) av en administratör.

    prislista     RSK (eller Dahls artikelnr), Bruttopris, Rabattgrupp, Enhet   (priserna på Dahls katalog)
    kunder        Kundnr, Namn, Bonus %, Bonusavtal
    rabatter      Kundnr, Rabattgrupp, Rabatt %                 (kundens rabattmatris)
    nettopriser   Kundnr, RSK (eller artikelnr), Nettopris      (kundunika priser, går före rabatten)
    inkopspriser  RSK (eller artikelnr), Inköpspris
    korsreferens  Material, Dimension, Fabrikat, Serie, RSK, Benämning, Pris saknas   (valregeln för rör)

Bruttopris och rabattgrupp kommer ur Dahls prislista (prislista: RSK/artikelnr, bruttopris, rabattgrupp).
"""
from __future__ import annotations

import csv
import datetime as dt
import html as _html
import io
import json
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from starlette.concurrency import run_in_threadpool

from vvs_engine import offer as OF
from vvs_engine.tb.rsk import normalize as rsk_norm

from .auth import current_admin, current_user
from .db import Offer, Project, TechSpec, User, get_db
from .storage import storage

router = APIRouter(tags=["offert"])
KINDS = {
    "kunder": {"kundnr": ("kundnr", "kundnummer", "kund nr", "kund"), "namn": ("namn", "kundnamn", "företag", "name"),
               "bonus": ("bonus %", "bonus", "bonusprocent"), "bonusavtal": ("bonusavtal", "bonustext", "avtal")},
    "rabatter": {"kundnr": ("kundnr", "kundnummer", "kund nr", "kund"),
                 "grupp": ("rabattgrupp", "rabatt grupp", "grupp", "varugrupp", "prisgrupp"),
                 "pct": ("rabatt %", "rabatt", "rabattprocent", "procent")},
    "nettopriser": {"kundnr": ("kundnr", "kundnummer", "kund nr", "kund"),
                    "rsk": ("rsk", "rsk-nr", "artikel", "artikelnr", "artikelnummer"), "pris": ("nettopris", "pris")},
    "inkopspriser": {"rsk": ("rsk", "rsk-nr", "artikel", "artikelnr", "artikelnummer"),
                     "pris": ("inköpspris", "inkopspris", "inköp", "pris")},
    "prislista": {"rsk": ("rsk", "rsk-nr", "rsk nr", "artnr", "art.nr", "art nr", "artikel", "artikelnr", "artikelnummer",
                          "dahl art.nr", "dahl artikelnr"),
                  "namn": ("benämning", "artikelbenämning", "namn"),
                  "pris": ("bruttopris", "listpris", "pris", "brutto"),
                  "grupp": ("kalkylgr", "kalkylgrupp", "rabattgrupp", "rabatt grupp", "grupp", "prisgrupp", "varugrupp", "prod.gr"),
                  "enhet": ("enhet", "enh")},
    # rabatt per kalkylgrupp (Prisfilens flik "Grupper_rabatter"): gäller där kunden saknar en egen rabatt för gruppen
    "grundrabatter": {"grupp": ("prod.gr", "produktgrupp", "kalkylgr", "kalkylgrupp", "rabattgrupp", "grupp"),
                      "namn": ("benämning", "namn"), "pct": ("rabatt", "rabatt %", "rabattprocent")},
    "korsreferens": {"material": ("material",), "dimension": ("dimension", "dim", "storlek"),
                     "fabrikat": ("fabrikat", "förskrivet fabrikat", "tillverkare"), "serie": ("serie",),
                     "rsk": ("rsk", "rsk-nr", "artikel", "artikelnr", "dahl art.nr", "vår artikel"),
                     "benamning": ("benämning", "vår benämning", "artikelbenämning"),
                     "pris_saknas": ("pris saknas", "saknar pris")},
}


def _key(kind: str) -> str:
    return f"offer/{kind}.json"


_CACHE: dict[str, tuple[float, list]] = {}


def data(kind: str) -> list[dict[str, Any]]:
    if not storage.exists(_key(kind)):
        return []
    try:
        stamp = os.path.getmtime(storage.path(_key(kind)))
    except (OSError, AttributeError, NotImplementedError):
        stamp = -1.0
    hit = _CACHE.get(kind)
    if hit and hit[0] == stamp and stamp >= 0:
        return hit[1]
    with storage.open(_key(kind)) as fh:
        rows = json.load(fh).get("rows") or []
    _CACHE[kind] = (stamp, rows)
    return rows


def _sheets_from_file(name: str, raw: bytes) -> list[list[list[Any]]]:
    """Alla flikar i en Excel-fil (en CSV är en flik)."""
    if name.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        return [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets]
    return [_rows_from_file(name, raw)]


def _rows_from_file(name: str, raw: bytes) -> list[list[Any]]:
    n = name.lower()
    if n.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    text = raw.decode("utf-8-sig", "replace")
    return list(csv.reader(io.StringIO(text), csv.Sniffer().sniff(text[:4000], delimiters=";,\t")))


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v)).replace(" ", "")
    if s.count(",") == 1 and s.count(".") >= 1:
        s = s.replace(".", "")
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def parse(kind: str, rows: list[list[Any]]) -> list[dict[str, Any]]:
    spec = KINDS[kind]
    head_i, cols = None, {}
    for i, r in enumerate(rows[:15]):
        found = {}
        for j, c in enumerate(r):
            h = re.sub(r"\s+", " ", str(c or "").strip().lower().rstrip(":"))
            for k, names in spec.items():
                if k not in found and h in names:
                    found[k] = j
        if len(found) >= 2:
            head_i, cols = i, found
            break
    if head_i is None:
        raise HTTPException(422, f"Hittade ingen rubrikrad. Kolumner för {kind}: " +
                            ", ".join(v[0].capitalize() for v in spec.values()))
    out = []
    for r in rows[head_i + 1:]:
        g = {k: (r[j] if j < len(r) else None) for k, j in cols.items()}
        if not any(v not in (None, "") for v in g.values()):
            continue
        row = {k: (str(v).strip() if v is not None else "") for k, v in g.items()}
        for k in ("pct", "pris", "bonus"):
            if k in row:
                row[k] = _num(g.get(k))
        if "rsk" in row:
            row["rsk"] = rsk_norm(row["rsk"]) or row["rsk"]
        if "kundnr" in row:
            row["kundnr"] = re.sub(r"\.0$", "", row["kundnr"])
        if "pris_saknas" in row:
            row["pris_saknas"] = str(row["pris_saknas"]).lower() in ("ja", "x", "1", "true", "sant")
        out.append(row)
    return out


@router.get("/api/offer-data")
def offer_data_status(user: User = Depends(current_user)):
    out = {}
    for k in KINDS:
        if storage.exists(_key(k)):
            with storage.open(_key(k)) as fh:
                d = json.load(fh)
            out[k] = {"n": len(d.get("rows") or []), "file": d.get("file"), "updated_at": d.get("updated_at")}
        else:
            out[k] = {"n": 0}
    return out


@router.post("/api/offer-data/{kind}")
async def offer_data_upload(kind: str, file: UploadFile = File(...), admin: User = Depends(current_admin)):
    if kind not in KINDS:
        raise HTTPException(404, "Okänd sorts data")
    raw = await file.read()
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()

    def store(k: str, rows: list[dict[str, Any]]) -> None:
        storage.put(_key(k), io.BytesIO(json.dumps({"file": file.filename, "updated_at": stamp, "rows": rows},
                                                   ensure_ascii=False).encode("utf-8")))
        _CACHE.pop(k, None)

    if kind == "prislista":
        # Dahls prisfil: en flik med artiklarna och bruttopriset, en med rabatten per kalkylgrupp
        found: dict[str, list] = {}
        for sheet in await run_in_threadpool(_sheets_from_file, file.filename or "", raw):
            for k in ("prislista", "grundrabatter"):
                if k in found:
                    continue
                try:
                    rows = parse(k, sheet)
                except HTTPException:
                    continue
                if k == "prislista" and not any(r.get("pris") is not None for r in rows[:200]):
                    continue
                if k == "grundrabatter" and not any(r.get("pct") is not None for r in rows[:200]):
                    continue
                if rows:
                    found[k] = rows
                    break
        if "prislista" not in found:
            raise HTTPException(422, "Hittade ingen flik med artikelnummer och bruttopris (Artnr/RSK, Bruttopris)")
        for k, rows in found.items():
            store(k, rows)
        from .main import _reset_material
        _reset_material()                           # priserna gäller direkt i offert, kalkyl och sökning
        return {"kind": kind, "n": len(found["prislista"]), "grundrabatter": len(found.get("grundrabatter") or [])}
    rows = parse(kind, _rows_from_file(file.filename or "", raw))
    if not rows:
        raise HTTPException(422, "Inga rader i filen")
    store(kind, rows)
    return {"kind": kind, "n": len(rows)}


def _customers() -> dict[str, dict[str, Any]]:
    return {r["kundnr"]: r for r in data("kunder") if r.get("kundnr")}


def customer_terms(no: str) -> dict[str, Any] | None:
    if not no:
        return None
    c = _customers().get(no)
    rab = {r["grupp"]: r["pct"] for r in data("rabatter") if r.get("kundnr") == no and r.get("pct") is not None}
    net = {r["rsk"]: r["pris"] for r in data("nettopriser") if r.get("kundnr") == no and r.get("pris") is not None}
    if c is None and not rab and not net:
        return None
    return {"kundnr": no, "namn": (c or {}).get("namn") or "", "bonus": (c or {}).get("bonus"),
            "bonusavtal": (c or {}).get("bonusavtal") or "", "rabatter": rab, "netto": net,
            "grundrabatter": base_discounts()}


def base_discounts() -> dict[str, float]:
    """Rabatten per kalkylgrupp ur prisfilen, för grupper där kunden saknar en egen."""
    return {r["grupp"]: r["pct"] for r in data("grundrabatter") if r.get("grupp") and r.get("pct") is not None}


@router.get("/api/customers")
def customers(q: str = "", user: User = Depends(current_user)):
    ql = q.strip().lower()
    rows = [c for c in _customers().values() if not ql or ql in c["kundnr"].lower() or ql in (c.get("namn") or "").lower()]
    return {"customers": [{"kundnr": c["kundnr"], "namn": c.get("namn") or ""} for c in rows[:50]],
            "n": len(_customers())}


@router.get("/api/customers/{no}")
def customer(no: str, user: User = Depends(current_user)):
    t = customer_terms(no)
    if t is None:
        raise HTTPException(404, "Kunden finns inte i kundregistret")
    return {**t, "rabattgrupper": len(t["rabatter"]), "nettopriser": len(t["netto"])}


# ---------------------------------------------------------------- offerterna

def _book() -> dict[str, dict[str, Any]]:
    from .main import _material_book
    out: dict[str, dict[str, Any]] = {}
    for r in _material_book().get("rows") or []:
        for k in (r.get("a"), r.get("dahl"), r.get("rsk"), rsk_norm(r.get("rsk") or "")):
            if k:
                out.setdefault(str(k), r)              # RSK och Dahls artikelnummer slår upp samma artikel
    for p in data("prislista"):                     # en artikel som bara står i prislistan har ändå sitt pris
        if p.get("rsk") and p.get("pris") is not None and (p["rsk"] not in out or out[p["rsk"]].get("p") is None):
            out[p["rsk"]] = {"a": p["rsk"], "n": out.get(p["rsk"], {}).get("n") or "", "p": float(p["pris"]),
                             "k": str(p.get("grupp") or ""), "e": p.get("enhet") or "st"}
    return out


def _pipe_finder(item: dict[str, Any], dn: int) -> dict[str, Any] | None:
    """Ett rör i rätt material och dimension ur Dahls katalog och prisfil - samma sökning som ritningskalkylen.
    Materialet ur postens text (kopparrör, PEX, rostfritt ...); utan känt material inget förslag."""
    from . import calc as C
    text = " ".join(str(item.get(k) or "") for k in ("name", "subcategory", "category", "text"))
    klass = C._material_class(text)
    if not klass:
        return None
    found = C._find_articles([klass], dn, klass=klass, limit=1)
    return found[0] if found else None


def _project(db: Session, user: User, pid: str) -> Project:
    p = db.get(Project, pid)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Projektet finns inte")
    return p


def _offer(db: Session, user: User, oid: str) -> Offer:
    o = db.get(Offer, oid)
    if o is None:
        raise HTTPException(404, "Offerten finns inte")
    _project(db, user, o.project_id)
    return o


def _out(o: Offer, internal: bool = True) -> dict[str, Any]:
    st = o.settings or {}
    rows = o.rows or []
    t = OF.totals(rows, st.get("bonus_pct"), st.get("extra_hours") or 0, st.get("hourly_rate") or 0)
    if not internal:
        rows = [{k: v for k, v in r.items() if k not in ("inkop", "inkop_summa", "marginal_kr", "marginal_pct")}
                for r in rows]
        t = {k: v for k, v in t.items() if k not in ("inkop", "marginal_kr", "marginal_pct", "inkop_tackning")}
    return {"id": o.id, "project_id": o.project_id, "number": o.number, "kind": o.kind, "title": o.title,
            "customer_no": o.customer_no, "customer_name": o.customer_name, "settings": st, "sources": o.sources,
            "rows": rows, "totals": t, "created_at": o.created_at, "updated_at": o.updated_at, "created_by": o.created_by}


class OfferIn(BaseModel):
    kind: str = "materialoffert"
    spec_ids: list[str] = []
    customer_no: str = ""
    title: str = ""
    use_house_brand: bool = False
    hourly_rate: float = 0.0
    job_ids: list[str] = []


def _build(db: Session, o: Offer) -> None:
    from .tech_spec import matched_items
    st = o.settings or {}
    items: list[dict[str, Any]] = []
    for sid in o.sources or []:
        s = db.get(TechSpec, sid)
        if s is not None and s.project_id == o.project_id:
            items += matched_items(s)
    terms = customer_terms(o.customer_no)
    if terms is None and base_discounts():
        terms = {"rabatter": {}, "netto": {}, "grundrabatter": base_discounts()}   # ingen kund: prisfilens grundrabatt
    purchase = {r["rsk"]: r["pris"] for r in data("inkopspriser") if r.get("pris") is not None}
    rows = OF.build_rows(items, _book(), terms, purchase, kind=o.kind, hourly_rate=st.get("hourly_rate") or 0,
                         pipe_finder=_pipe_finder,
                         use_house_brand=bool(st.get("use_house_brand")), crossref=data("korsreferens"))
    # det någon ändrat för hand står kvar när offerten räknas om
    manual = {r["id"]: r for r in (o.rows or []) if r.get("manuellt")}
    for i, r in enumerate(rows):
        m = manual.get(r["id"])
        if m:
            for k in ("rsk", "artikel", "antal", "netto", "tim_per_enhet", "manuellt"):
                if k in m:
                    r[k] = m[k]
            if "rsk" in m["manuellt"] and m.get("rsk"):
                r.update({k: v for k, v in OF.customer_price(m["rsk"], _book(), terms).items()
                          if k != "netto" or "netto" not in m["manuellt"]})
                r["val"] = "valt för hand"
                r["flaggor"] = [f for f in r["flaggor"] if "artikel" not in f and "storlek" not in f]
            rows[i] = OF.compute(r, st.get("hourly_rate") or 0)
    if o.kind == "kalkyloffert":
        # rören och deras timmar ur ritningskalkylen: den senast sparade kalkylen för varje ritning i projektet
        from .db import AnalysisJob, Calculation, Drawing
        calcs = (db.query(Calculation, AnalysisJob, Drawing).join(AnalysisJob, Calculation.job_id == AnalysisJob.id)
                 .join(Drawing, AnalysisJob.drawing_id == Drawing.id).filter(Drawing.project_id == o.project_id)
                 .order_by(Calculation.updated_at.desc()).all())
        seen = set()
        for c, j, d in calcs:
            if d.id in seen:
                continue
            seen.add(d.id)
            t = c.totals or {}
            rows.append(OF.compute({"id": f"calc-{d.id}", "pos": "", "text": f"Rörledningar enligt ritningskalkyl: {d.filename}",
                                    "foreskrift": "", "rsk": "", "artikel": "material och normtid per meter ur kalkylen",
                                    "val": "ritningskalkyl", "antal": 1, "enhet": "post", "brutto": None,
                                    "rabattgrupp": "", "rabatt_pct": None, "netto": t.get("material_kr"),
                                    "pris_enligt": "ritningskalkylen", "inkop": None, "flaggor": [] if t.get("material_kr") else
                                    ["kalkylen saknar material - öppna ritningens kalkyl"], "kalla": "ritning",
                                    "tim_per_enhet": t.get("timmar"), "tim_kalla": "Normtid VVS via ritningskalkylen"},
                                   st.get("hourly_rate") or 0))
    o.customer_name = (terms or {}).get("namn") or o.customer_name
    o.rows = rows
    o.settings = dict(st)
    flag_modified(o, "settings")
    o.updated_at = dt.datetime.now(dt.timezone.utc)


@router.post("/api/projects/{project_id}/offers")
def create_offer(project_id: str, body: OfferIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """En offert ur projektets matchade underlag (tekniska beskrivningar, listor, IFC)."""
    p = _project(db, user, project_id)
    if body.kind not in ("materialoffert", "kalkyloffert"):
        raise HTTPException(422, "Offerten är en materialoffert eller en kalkyloffert")
    specs = body.spec_ids or [s.id for s in db.query(TechSpec).filter(TechSpec.project_id == p.id,
                                                                      TechSpec.status == "COMPLETED").all()]
    if not specs:
        raise HTTPException(422, "Projektet har inget matchat underlag att göra en offert av")
    n = db.query(Offer).count() + 1
    o = Offer(project_id=p.id, kind=body.kind, title=body.title or p.name, customer_no=body.customer_no.strip(),
              sources=specs, created_by=user.email, number=f"{dt.date.today():%y%m}-{n:04d}",
              settings={"use_house_brand": body.use_house_brand, "hourly_rate": body.hourly_rate,
                        "job_ids": body.job_ids})
    if body.customer_no and customer_terms(body.customer_no.strip()) is None:
        raise HTTPException(404, "Kunden finns inte i kundregistret")
    db.add(o)
    db.flush()
    _build(db, o)
    db.commit()
    return _out(o)


@router.get("/api/projects/{project_id}/offers")
def list_offers(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    rows = db.query(Offer).filter(Offer.project_id == p.id).order_by(Offer.created_at.desc()).all()
    return [{"id": o.id, "number": o.number, "kind": o.kind, "title": o.title, "customer_no": o.customer_no,
             "customer_name": o.customer_name, "totals": _out(o)["totals"], "updated_at": o.updated_at} for o in rows]


@router.get("/api/offers/{offer_id}")
def get_offer(offer_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(_offer(db, user, offer_id))


class RowChange(BaseModel):
    id: str
    antal: float | None = None
    netto: float | None = None
    rsk: str | None = None
    tim_per_enhet: float | None = None


class OfferPatch(BaseModel):
    customer_no: str | None = None
    title: str | None = None
    use_house_brand: bool | None = None
    hourly_rate: float | None = None
    bonus_pct: float | None = None
    rows: list[RowChange] = []


@router.patch("/api/offers/{offer_id}")
def patch_offer(offer_id: str, body: OfferPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Byt kund (rabattmatrisen läses in igen), ändra rader för hand, timpris, eget varumärke. Räknas om direkt."""
    o = _offer(db, user, offer_id)
    st = dict(o.settings or {})
    if body.customer_no is not None:
        if body.customer_no and customer_terms(body.customer_no.strip()) is None:
            raise HTTPException(404, "Kunden finns inte i kundregistret")
        o.customer_no, st["bonus_pct"] = body.customer_no.strip(), None
    for k in ("use_house_brand", "hourly_rate", "bonus_pct"):
        v = getattr(body, k)
        if v is not None:
            st[k] = v
    if body.title is not None:
        o.title = body.title
    rows = [dict(r) for r in o.rows or []]
    by_id = {r["id"]: r for r in rows}
    for ch in body.rows:
        r = by_id.get(ch.id)
        if r is None:
            raise HTTPException(404, f"Raden {ch.id} finns inte")
        man = set(r.get("manuellt") or [])
        for k in ("antal", "netto", "rsk", "tim_per_enhet"):
            v = getattr(ch, k)
            if v is not None:
                r[k] = (rsk_norm(v) or v) if k == "rsk" else v
                man.add(k)
        r["manuellt"] = sorted(man)
    o.rows = rows
    o.settings = st
    _build(db, o)
    flag_modified(o, "rows")
    db.commit()
    return _out(o)


@router.post("/api/offers/{offer_id}/bonus")
def fetch_bonus(offer_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Hämta kundens bonus ur kundregistret och räkna den på offerten."""
    o = _offer(db, user, offer_id)
    t = customer_terms(o.customer_no)
    if t is None:
        raise HTTPException(422, "Välj en kund först")
    if t.get("bonus") is None:
        raise HTTPException(404, "Kunden har ingen bonus i kundregistret")
    st = dict(o.settings or {})
    st["bonus_pct"], st["bonusavtal"] = t["bonus"], t.get("bonusavtal") or ""
    o.settings = st
    flag_modified(o, "settings")
    db.commit()
    return _out(o)


@router.delete("/api/offers/{offer_id}")
def delete_offer(offer_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = _offer(db, user, offer_id)
    db.delete(o)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- export

def _kr(v) -> str:
    return "" if v is None else f"{v:,.2f}".replace(",", " ").replace(".", ",")


def _xlsx(o: dict[str, Any], internal: bool) -> bytes:
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Offert"
    ws.append([f"{o['kind'].capitalize()} {o['number']}", o["title"]])
    ws.append(["Kund", f"{o['customer_no']} {o['customer_name']}".strip()])
    ws.append([])
    head = ["Pos", "Benämning", "Föreskrift", "RSK", "Artikel", "Antal", "Enhet", "Pris/enhet", "Summa"]
    if o["kind"] == "kalkyloffert":
        head += ["Timmar"]
    if internal:
        head += ["Brutto", "Rabatt %", "Rabattgrupp", "Inköpspris", "Inköp summa", "Marginal kr", "Marginal %",
                 "Artikelval", "Flaggor"]
    ws.append(head)
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for r in o["rows"]:
        line = [r.get("pos"), r.get("text"), r.get("foreskrift"), r.get("rsk"), r.get("artikel"), r.get("antal"),
                r.get("enhet"), r.get("netto"), r.get("summa")]
        if o["kind"] == "kalkyloffert":
            line += [r.get("timmar")]
        if internal:
            line += [r.get("brutto"), r.get("rabatt_pct"), r.get("rabattgrupp"), r.get("inkop"), r.get("inkop_summa"),
                     r.get("marginal_kr"), r.get("marginal_pct"), r.get("val"), "; ".join(r.get("flaggor") or [])]
        ws.append(line)
    t = o["totals"]
    ws.append([])
    ws.append(["", "Material", "", "", "", "", "", "", t["material"]])
    if o["kind"] == "kalkyloffert":
        ws.append(["", f"Arbete ({t['timmar']} h)", "", "", "", "", "", "", t["arbete"]])
    ws.append(["", "Totalt exkl. moms", "", "", "", "", "", "", t["total"]])
    if t.get("bonus_kr"):
        ws.append(["", f"Bonus enligt avtal ({t['bonus_pct']} %)", "", "", "", "", "", "", t["bonus_kr"]])
    if internal:
        ws.append(["", "INTERNT: inköp", "", "", "", "", "", "", t.get("inkop")])
        ws.append(["", "INTERNT: marginal", "", "", "", "", "", "", t.get("marginal_kr"), t.get("marginal_pct")])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _customer_html(o: dict[str, Any]) -> str:
    e = _html.escape
    kalk = o["kind"] == "kalkyloffert"
    rows = "".join(
        f"<tr><td>{e(str(r.get('pos') or ''))}</td><td>{e(r.get('text') or '')}<br><small>{e(r.get('artikel') or '')}"
        f"</small></td><td>{e(r.get('rsk') or '')}</td><td class=n>{e(str(r.get('antal') if r.get('antal') is not None else ''))} "
        f"{e(r.get('enhet') or '')}</td><td class=n>{_kr(r.get('netto'))}</td><td class=n>{_kr(r.get('summa'))}</td></tr>"
        for r in o["rows"])
    t = o["totals"]
    extra = (f"<tr><td colspan=5>Arbete, {t['timmar']} h</td><td class=n>{_kr(t['arbete'])}</td></tr>" if kalk else "")
    bonus = (f"<p>Bonus enligt avtal: {t['bonus_pct']} % ({_kr(t['bonus_kr'])} kr)</p>" if t.get("bonus_kr") else "")
    return (f"<html><head><meta charset='utf-8'><style>body{{font-family:Arial,sans-serif;font-size:10pt;color:#1d2a33}}"
            f"h1{{color:#004976;font-size:16pt}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid "
            f"#dde3e8;padding:4px 6px;text-align:left;vertical-align:top}}th{{color:#004976}}.n{{text-align:right}}"
            f"</style></head><body><h1>{'Kalkyloffert' if kalk else 'Materialoffert'} {e(o['number'])}</h1>"
            f"<p><b>{e(o['title'])}</b><br>Kund: {e(o['customer_no'])} {e(o['customer_name'])}<br>Datum: "
            f"{dt.date.today():%Y-%m-%d}</p><table><tr><th>Pos</th><th>Benämning</th><th>RSK</th><th class=n>Antal</th>"
            f"<th class=n>À-pris</th><th class=n>Summa</th></tr>{rows}{extra}<tr><th colspan=5>Totalt exkl. moms</th>"
            f"<th class=n>{_kr(t['total'])}</th></tr></table>{bonus}<p><small>Priser i SEK exkl. moms.</small></p>"
            f"</body></html>")


@router.get("/api/offers/{offer_id}/export.{fmt}")
def export_offer(offer_id: str, fmt: str, internal: bool = False, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """Kundens offert (xlsx eller pdf) utan inköp och marginal, eller det interna underlaget (internal=true)."""
    from .tech_spec import _disposition
    o = _out(_offer(db, user, offer_id), internal=internal)
    base = f"{o['kind']}-{o['number']}" + ("-internt" if internal else "")
    if fmt == "xlsx":
        return Response(_xlsx(o, internal), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": _disposition(base + ".xlsx")})
    if fmt == "pdf":
        if internal:
            raise HTTPException(422, "Det interna underlaget finns som Excel")
        from .calc import _body_pdf
        return Response(_body_pdf(_customer_html(o)), media_type="application/pdf",
                        headers={"Content-Disposition": _disposition(base + ".pdf")})
    raise HTTPException(404, "Formatet finns inte")
