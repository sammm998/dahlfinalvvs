"""Teknisk beskrivning: en beskrivning utan ritningar, läst till material och jämförd med vad som går att köpa.

Ett ABT 06-projekt kan kryssa i "Teknisk beskrivning". Då laddas beskrivningen upp här, läses med
vvs_engine.tb.reader till poster - kod, mängd, fabrikat, typ, RSK-nummer, specifikation, kategori - och varje
post jämförs med materialboken och Dahls produktkatalog. Det som inte finns får ett mejlutkast.

Katalogen är tjänstens, inte projektets: en administratör läser in den en gång, från länken på katalog.dahl.se
eller som uppladdad PDF, och den gäller sedan för varje beskrivning - också de som laddades upp innan.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import threading
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from vvs_engine.tb import read_tech_spec_bytes
from vvs_engine.tb.catalog import find_pdf_link, index_pdf, unwrap_url
from vvs_engine.tb.mail import drafts_by_maker
from vvs_engine.tb.match import MaterialIndex
from vvs_engine.tb.rsk import pretty as rsk_pretty

from . import api_budget
from .auth import current_admin, current_user
from .db import Project, TechSpec, User, get_db
from .storage import storage

router = APIRouter(tags=["teknisk beskrivning"])

MAX_SPEC_BYTES = 60 * 1024 * 1024
MAX_CATALOG_BYTES = 500 * 1024 * 1024
CATALOG_KEY = "catalog/dahl/index.json"
CATALOG_PDF = "catalog/dahl/katalog.pdf"
DEFAULT_CATALOG_URL = "https://katalog.dahl.se/dahl-sverige-ab/dahl-produktkatalog-2026pdf/"


# ---------------------------------------------------------------- indexet

_INDEX: MaterialIndex | None = None
_LOCK = threading.Lock()


def _catalog_index() -> dict[str, Any] | None:
    if not storage.exists(CATALOG_KEY):
        return None
    with storage.open(CATALOG_KEY) as fh:
        return json.load(fh)


def material_index() -> MaterialIndex:
    """Materialboken och katalogen i ett ordindex. Byggs vid första frågan och när katalogen byts."""
    global _INDEX
    with _LOCK:
        if _INDEX is None:
            ix = MaterialIndex()
            # samma material som Materialsidan: Dahls katalog när den finns, annars materialboken
            from .main import _material
            book = _material()
            if book.get("rows"):
                if book.get("kind") == "dahl":
                    ix.add_material_book(book["rows"], label=book.get("source") or "Dahls produktkatalog", source="katalog")
                else:
                    ix.add_material_book(book["rows"], label=f"Materialboken ({book.get('source') or 'materialsortering'})")
            cat = _catalog_index()
            if cat:
                ix.add_catalog(cat)
            _INDEX = ix
        return _INDEX


def _reset_index() -> None:
    global _INDEX
    with _LOCK:
        _INDEX = None


def _sources(ix: MaterialIndex) -> dict[str, Any]:
    return {"materialbok": ix.sources.get("materialbok"), "katalog": ix.sources.get("katalog"),
            "catalog_url": DEFAULT_CATALOG_URL}


# ---------------------------------------------------------------- katalogen

@router.get("/api/catalog")
def catalog_status(user: User = Depends(current_user)):
    """Vad posterna jämförs med: materialboken alltid, Dahls katalog när den är inläst."""
    return _sources(material_index())


class CatalogIn(BaseModel):
    url: str = DEFAULT_CATALOG_URL


def _store_catalog(data: bytes, origin: str) -> dict[str, Any]:
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Katalogen är inte en PDF")
    try:
        idx = index_pdf(data, origin=origin)
    except Exception:
        raise HTTPException(400, "Katalogens PDF gick inte att läsa")
    if not idx["pages"]:
        raise HTTPException(422, "Katalogen har ingen läsbar text - den är troligen skannad som bilder")
    storage.put(CATALOG_PDF, io.BytesIO(data))
    storage.put(CATALOG_KEY, io.BytesIO(json.dumps(idx, ensure_ascii=False).encode("utf-8")))
    _reset_index()
    return {"pages": idx["n_pages"], "lines": sum(len(p["lines"]) for p in idx["pages"]), "origin": origin,
            "imported_at": idx["imported_at"]}


def _fetch_catalog(url: str) -> tuple[bytes, str]:
    """Katalogen från en länk. Pekar länken på en bläddringsvy letas PDF:en upp i sidan."""
    import httpx
    url = unwrap_url(url)
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "Länken ska börja med https://")

    def get(u: str) -> tuple[bytes, str, str]:
        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(180.0, connect=20.0),
                          headers={"User-Agent": "Mozilla/5.0 (compatible; materialkatalog)"}) as c:
            with c.stream("GET", u) as r:
                if r.status_code >= 400:
                    raise HTTPException(502, f"Katalogen svarade {r.status_code} på {u}")
                buf, size = [], 0
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > MAX_CATALOG_BYTES:
                        raise HTTPException(413, "Katalogen är större än 500 MB")
                    buf.append(chunk)
                return b"".join(buf), r.headers.get("content-type", ""), str(r.url)

    try:
        data, ctype, final = get(url)
        if data.startswith(b"%PDF"):
            return data, final
        pdf = find_pdf_link(data.decode("utf-8", "replace"), final)
        if not pdf:
            raise HTTPException(422, "Länken går till en bläddringsvy utan länk till själva PDF:en. Ladda ner "
                                     "katalogen som PDF från katalog.dahl.se och ladda upp filen här i stället.")
        data, _, final = get(pdf)
        if not data.startswith(b"%PDF"):
            raise HTTPException(422, "Länken i bläddringsvyn gav ingen PDF. Ladda upp katalogen som PDF i stället.")
        return data, final
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Katalogen gick inte att hämta: {type(e).__name__}")


@router.post("/api/catalog/import")
async def catalog_import(body: CatalogIn, admin: User = Depends(current_admin)):
    """Läs in Dahls katalog från länken. Tar en stund: hela katalogen hämtas och läses sida för sida."""
    data, origin = await run_in_threadpool(_fetch_catalog, body.url or DEFAULT_CATALOG_URL)
    return await run_in_threadpool(_store_catalog, data, origin)


@router.post("/api/catalog/upload")
async def catalog_upload(file: UploadFile = File(...), admin: User = Depends(current_admin)):
    data = await _read_capped(file, MAX_CATALOG_BYTES)
    return await run_in_threadpool(_store_catalog, data, os.path.basename(file.filename or "katalog.pdf"))


# ---------------------------------------------------------------- beskrivningarna

def _project(db: Session, user: User, pid: str) -> Project:
    p = db.get(Project, pid)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Projektet finns inte")
    return p


def _spec(db: Session, user: User, sid: str) -> TechSpec:
    s = db.get(TechSpec, sid)
    if s is None:
        raise HTTPException(404, "Beskrivningen finns inte")
    _project(db, user, s.project_id)
    return s


def _ai_out(s: TechSpec) -> dict[str, Any] | None:
    a = s.ai
    if not a:
        return None
    return {k: a.get(k) for k in ("status", "model", "ran_at", "by", "kr", "calls", "cached_calls", "tokens",
                                  "lines_sent", "asked", "error")} | {
        "picked": len(a.get("picks") or {}),
        "missed": [m for m in (a.get("missed") or []) if m.get("state") == "förslag"],
        "accepted": sum(1 for m in (a.get("missed") or []) if m.get("state") == "godkänd")}


def _spec_out(s: TechSpec) -> dict[str, Any]:
    return {"id": s.id, "project_id": s.project_id, "filename": s.filename, "n_pages": s.n_pages,
            "size_bytes": s.size_bytes, "status": s.status, "error": s.error, "title": s.title,
            "stats": s.stats or {}, "created_at": s.created_at, "ai": _ai_out(s), "source": s.source or "tb"}


async def _read_capped(file: UploadFile, cap: int) -> bytes:
    chunks, size = [], 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > cap:
            raise HTTPException(413, f"Filen är större än {cap // (1024 * 1024)} MB")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/api/projects/{project_id}/tech-specs")
async def upload_tech_spec(project_id: str, file: UploadFile = File(...), user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    """Ladda upp en teknisk beskrivning och läs den. Samma fil två gånger i samma projekt blir en beskrivning."""
    p = _project(db, user, project_id)
    filename = os.path.basename(file.filename or "beskrivning.pdf")
    if not filename.lower().endswith((".pdf", ".zip")):
        raise HTTPException(400, "Beskrivningen ska vara en PDF, eller en zip med förfrågans handlingar")
    data = await _read_capped(file, MAX_SPEC_BYTES * 5 if filename.lower().endswith(".zip") else MAX_SPEC_BYTES)
    if not (data.startswith(b"%PDF") or data[:2] == b"PK"):
        raise HTTPException(400, "Filen är inte en giltig PDF eller zip")
    sha = hashlib.sha256(data).hexdigest()
    same = db.query(TechSpec).filter(TechSpec.project_id == p.id, TechSpec.sha256 == sha).first()
    if same is not None:
        return {**_spec_out(same), "duplicate": True}
    try:
        out = await run_in_threadpool(read_any_description, filename, data)
    except Exception:
        raise HTTPException(400, "Filen kunde inte läsas")
    if not out["items"]:
        status, error = "FAILED", ("Inga materialposter hittades. Beskrivningen är kanske skannad som bilder, "
                                   "eller inte uppställd med koder och mängder.")
    else:
        status, error = "COMPLETED", ""
    s = TechSpec(project_id=p.id, filename=filename, storage_key="", sha256=sha, size_bytes=len(data),
                 n_pages=out["meta"].get("n_pages", 0), status=status, error=error,
                 title=(out["meta"].get("title") or "")[:255], items=out["items"], stats=out["stats"])
    db.add(s)
    db.flush()
    if out["meta"].get("documents"):
        s.stats = {**(s.stats or {}), "documents": out["meta"]["documents"], "groups": out["meta"].get("groups")}
    ext = ".zip" if data[:2] == b"PK" else ".pdf"
    s.storage_key = storage.put(f"techspecs/{p.id}/{s.id}{ext}", io.BytesIO(data))
    db.commit()
    return {**_spec_out(s), "duplicate": False}


def _zip_has_ifc(data: bytes) -> bool:
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return any(n.lower().endswith(".ifc") for n in z.namelist())
    except zipfile.BadZipFile:
        return False


def read_any_description(filename: str, data: bytes) -> dict[str, Any]:
    """En AMA-beskrivning, en typrumsbeskrivning, en ritning med förteckning - eller en zip med flera."""
    if data[:2] == b"PK" or filename.lower().endswith(".zip"):
        from vvs_engine.tb.inquiry import read_inquiry
        return read_inquiry(filename, data)
    import pymupdf
    from vvs_engine.tb.legend import has_legend
    from vvs_engine.tb.rooms import is_room_description
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        head = "".join(doc[i].get_text() for i in range(min(3, len(doc))))
        special = has_legend(doc) or is_room_description(head)
    finally:
        doc.close()
    if special:
        from vvs_engine.tb.inquiry import read_inquiry
        return read_inquiry(filename, data)
    return read_tech_spec_bytes(data)


@router.get("/api/projects/{project_id}/tech-specs")
def list_tech_specs(project_id: str, source: str = "tb", user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    q = db.query(TechSpec).filter(TechSpec.project_id == p.id)
    q = q.filter(TechSpec.source.in_(("ifc", "lista"))) if source == "ifc" \
        else q.filter((TechSpec.source == "tb") | (TechSpec.source.is_(None)))
    return [_spec_out(s) for s in q.order_by(TechSpec.created_at.desc()).all()]


MAX_IFC_BYTES = 500 * 1024 * 1024
LIST_TYPES = (".eml", ".txt", ".docx", ".xlsx", ".xlsm", ".csv", ".msg")


def _store_list(db: Session, p: Project, filename: str, data: bytes) -> dict[str, Any]:
    from vvs_engine.tb.listing import read_material_list
    sha = hashlib.sha256(data).hexdigest()
    same = db.query(TechSpec).filter(TechSpec.project_id == p.id, TechSpec.sha256 == sha).first()
    if same is not None:
        return {**_spec_out(same), "duplicate": True}
    try:
        out = read_material_list(filename, data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    except Exception:
        raise HTTPException(400, "Materiallistan kunde inte läsas")
    status, error = ("COMPLETED", "") if out["items"] else (
        "FAILED", "Inga materialrader hittades. En rad behöver ett antal (3 st, 12 m) eller en kod (PB101), och "
                  "gärna fabrikat eller RSK på samma rad eller raderna under.")
    s = TechSpec(project_id=p.id, filename=filename, storage_key="", sha256=sha, size_bytes=len(data), n_pages=0,
                 status=status, error=error, title=(out["meta"].get("title") or filename)[:255], items=out["items"],
                 stats=out["stats"], source="lista")
    db.add(s)
    db.flush()
    s.storage_key = storage.put(f"lists/{p.id}/{s.id}{os.path.splitext(filename)[1] or '.txt'}", io.BytesIO(data))
    db.commit()
    return {**_spec_out(s), "duplicate": False}


@router.post("/api/projects/{project_id}/material-list")
async def upload_material_list(project_id: str, file: UploadFile = File(...), user: User = Depends(current_user),
                               db: Session = Depends(get_db)):
    """En materiallista som inte är en AMA-beskrivning: ett mejl (.eml), text, Word, Excel eller CSV/BOM. Varje
    position med all text som hör till den - fabrikat och RSK på raderna under - blir en post."""
    p = _project(db, user, project_id)
    filename = os.path.basename(file.filename or "lista.txt")
    if not filename.lower().endswith(LIST_TYPES):
        raise HTTPException(400, "Materiallistan ska vara .eml, .txt, .docx, .xlsx eller .csv")
    data = await _read_capped(file, 50 * 1024 * 1024)
    return await run_in_threadpool(_store_list, db, p, filename, data)


class ListTextIn(BaseModel):
    text: str
    title: str = ""


@router.post("/api/projects/{project_id}/material-list/text")
def material_list_text(project_id: str, body: ListTextIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """Text inklistrad ur ett mejl: samma läsning som en uppladdad lista."""
    p = _project(db, user, project_id)
    if len(body.text.strip()) < 5:
        raise HTTPException(422, "Klistra in texten med materialet")
    name = (body.title.strip() or "Inklistrad text")[:200]
    return _store_list(db, p, name if name.lower().endswith(".txt") else f"{name}.txt", body.text.encode("utf-8"))


@router.post("/api/projects/{project_id}/ifc")
async def upload_ifc(project_id: str, file: UploadFile = File(...), user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    """Ladda upp en IFC-modell (.ifc, eller .zip med en .ifc i) och läs den till VVS-material: varje produkttyp en
    post med antal per våning, fabrikat och modell. Samma matchning mot Dahls katalog som en teknisk beskrivning."""
    from vvs_engine.ifc import read_ifc_bytes
    p = _project(db, user, project_id)
    filename = os.path.basename(file.filename or "modell.ifc")
    if not filename.lower().endswith((".ifc", ".zip", ".ifczip")):
        raise HTTPException(400, "IFC-modellen ska vara en .ifc-fil eller en .zip med en .ifc i")
    data = await _read_capped(file, MAX_IFC_BYTES)
    sha = hashlib.sha256(data).hexdigest()
    same = db.query(TechSpec).filter(TechSpec.project_id == p.id, TechSpec.sha256 == sha).first()
    if same is not None:
        return {**_spec_out(same), "duplicate": True}
    if data[:2] == b"PK" and not _zip_has_ifc(data):
        # en zip med förfrågans handlingar (PDF), inte en IFC-modell: läses som en förfrågan
        out = await run_in_threadpool(read_any_description, filename, data)
        st = "COMPLETED" if out["items"] else "FAILED"
        s = TechSpec(project_id=p.id, filename=filename, storage_key="", sha256=sha, size_bytes=len(data), n_pages=out["meta"].get("n_pages", 0),
                     status=st, error="" if out["items"] else "Inga poster hittades i handlingarna",
                     title=(out["meta"].get("title") or filename)[:255], items=out["items"],
                     stats={**out["stats"], "documents": out["meta"].get("documents"), "groups": out["meta"].get("groups")},
                     source="lista")
        db.add(s)
        db.flush()
        s.storage_key = storage.put(f"lists/{p.id}/{s.id}.zip", io.BytesIO(data))
        db.commit()
        return {**_spec_out(s), "duplicate": False}
    try:
        out = await run_in_threadpool(read_ifc_bytes, data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    except Exception:
        raise HTTPException(400, "IFC-filen kunde inte läsas")
    if not out["items"]:
        status, error = "FAILED", ("Modellen innehåller inga VVS-objekt (sanitet, armaturer, ventiler, rör, brunnar ...). "
                                   "Är det arkitektens eller konstruktörens modell utan installationer?")
    else:
        status, error = "COMPLETED", ""
    title = out["meta"].get("inner") or filename
    s = TechSpec(project_id=p.id, filename=filename, storage_key="", sha256=sha, size_bytes=len(data), n_pages=0,
                 status=status, error=error, title=os.path.splitext(title)[0][:255], items=out["items"],
                 stats={**out["stats"], "schema": out["meta"].get("schema"), "storeys": out["meta"].get("storeys"),
                        "classes": out["meta"].get("classes")}, source="ifc")
    db.add(s)
    db.flush()
    ext = ".zip" if data[:2] == b"PK" else ".ifc"
    s.storage_key = storage.put(f"ifc/{p.id}/{s.id}{ext}", io.BytesIO(data))
    db.commit()
    return {**_spec_out(s), "duplicate": False}


def item_match(ix: MaterialIndex, it: dict[str, Any]) -> dict[str, Any]:
    """Var en post finns. Allmänt material och arbete söks inte som artiklar - "upphängningsdon" är ett krav, inte
    en vara att fråga efter - och det som någon annan levererar ska inte köpas alls."""
    who = it.get("supplied_by") or ""
    if who and not who.startswith("Ingår"):
        return {"status": "annan", "hits": [], "in_catalog": False, "note": f"Levereras av {who}"}
    if it.get("kind") in ("krav", "arbete"):
        return {"status": "allmänt", "hits": [], "in_catalog": False,
                "note": "Allmänt krav: mängd och val enligt ritning" if it.get("kind") == "krav" else "Arbete"}
    return ix.match(it)


_DQ: dict[str, tuple[tuple, dict]] = {}


def drawing_quantities(project_id: str) -> dict[str, Any]:
    """Komponentkoder och rörmeter ur projektets analyserade ritningar (den senaste färdiga läsningen per ritning).
    Sparas så länge samma läsningar gäller."""
    from vvs_engine.tb.drawing_link import collect
    from .db import AnalysisJob, Drawing, SessionLocal
    with SessionLocal() as db:
        rows = (db.query(AnalysisJob, Drawing).join(Drawing, AnalysisJob.drawing_id == Drawing.id)
                .filter(Drawing.project_id == project_id, AnalysisJob.status == "COMPLETED")
                .order_by(AnalysisJob.created_at.desc()).all())
        latest: dict[str, tuple] = {}
        for j, d in rows:
            if d.id not in latest and j.result_key:
                latest[d.id] = (j.id, storage.path(j.result_key), d.filename)
    key = tuple(sorted(v[0] for v in latest.values()))
    hit = _DQ.get(project_id)
    if hit and hit[0] == key:
        return hit[1]
    found = collect([{"dir": v[1], "drawing": v[2]} for v in latest.values() if os.path.isdir(v[1])])
    _DQ[project_id] = (key, found)
    return found


def matched_items(s: TechSpec, with_ai: bool = True) -> list[dict[str, Any]]:
    """Posterna med var de finns i katalogen - och med mängden ur projektets ritningar när den finns där."""
    from vvs_engine.tb.drawing_link import apply, link
    from .tb_ai import overlay
    ix = material_index()
    picks = ((s.ai or {}).get("picks") or {}) if with_ai else {}
    try:
        found = drawing_quantities(s.project_id)
    except Exception:                                    # noqa: BLE001 - mängden ur beskrivningen står kvar
        import logging
        logging.getLogger("vvs.tb").warning("Ritningarnas mängder kunde inte läsas", exc_info=True)
        found = {}
    from vvs_engine.tb.equivalent import suggest
    from .brand_catalog import products
    house = products()
    out = []
    for it in s.items or []:
        it = apply(it, link(it, found))
        if it.get("quantity_override") is not None:
            it = {**it, "total_quantity": it["quantity_override"], "quantity_from": "manuellt"}
        m = overlay(item_match(ix, it), picks.get(it.get("id")))
        eq = suggest(it, house) if house and it.get("kind") not in ("krav", "arbete") else None
        if eq:
            m = {**m, "equivalent": eq}
        out.append({**it, "match": m})
    return out


class QuantityIn(BaseModel):
    quantity: float | None = None


@router.post("/api/tech-specs/{spec_id}/items/{item_id}/quantity")
def set_quantity(spec_id: str, item_id: str, body: QuantityIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """Ange antalet för hand (null tar bort det): för rader där handlingarna inte räcker för att räkna."""
    from sqlalchemy.orm.attributes import flag_modified
    s = _spec(db, user, spec_id)
    items = [dict(x) for x in s.items or []]
    hit = next((x for x in items if x.get("id") == item_id), None)
    if hit is None:
        raise HTTPException(404, "Raden finns inte")
    if body.quantity is not None and body.quantity < 0:
        raise HTTPException(422, "Antalet kan inte vara negativt")
    hit["quantity_override"] = body.quantity
    hit["quantity_override_by"] = user.email if body.quantity is not None else ""
    s.items = items
    flag_modified(s, "items")
    db.commit()
    return {"ok": True, "id": item_id, "quantity": body.quantity}


@router.get("/api/tech-specs/{spec_id}/equivalents.csv")
def equivalents_csv(spec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Likvärdighetsförslag ur det egna varumärket, en rad per position: sakvara, föreskrift, alternativ, RSK,
    antal, pris per styck och summa - som ett manuellt facit - med kraven och flaggorna bredvid."""
    from .brand_catalog import catalog
    s = _spec(db, user, spec_id)
    brand = catalog().get("brand") or "Eget varumärke"
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Pos", "Sakvara", "Föreskrift", f"{brand} alternativ", "RSK", "Antal", "Pris per styck", "Summa",
                "Bedömning", "Krav som avviker eller ska verifieras", "Flagga", "Antal enligt"])
    total = 0.0
    for it in matched_items(s):
        eq = (it["match"].get("equivalent") or {})
        c = (eq.get("candidates") or [None])[0]
        if not c:
            continue
        q = it.get("total_quantity")
        price = c.get("price")
        line = (q or 0) * (price or 0)
        total += line
        pres = " ".join(x for x in (it.get("manufacturer"), it.get("type")) if x) or "Okänd"
        issues = "; ".join(f"{x['krav']}: {x['detalj']}" for x in c["checks"] if x["status"] != "uppfyllt")
        w.writerow([it.get("code") or "", it.get("name"), pres, c["name"], c.get("rsk") or "",
                    _num(q) if q is not None else "", _num(price) if price is not None else "",
                    _num(round(line, 2)) if q is not None and price is not None else "", c["state"], issues,
                    (it.get("spec") or {}).get("Flagga", ""), it.get("inferred") or it.get("quantity_text") or ""])
    w.writerow([])
    w.writerow(["", "", "", "", "", "", "Total offertsumma:", _num(round(total, 2))])
    w.writerow(["", "Förslag - likvärdighet är inte automatiskt fastställd. Kontrollera mot samtliga tekniska, "
                    "estetiska och miljömässiga krav."])
    name = os.path.splitext(s.filename)[0]
    return Response(("\ufeff" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": _disposition(f"likvardighet-{name}.csv")})


# ---------------------------------------------------------------- AI-kontrollen

@router.post("/api/tech-specs/{spec_id}/ai")
def run_ai_check(spec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Låt en språkmodell leta efter det läsaren kan ha missat och välja katalograd där det finns flera
    kandidater. Billigt: bara text, bara det osäkra, korta svar och cache (tb_ai.py). Kostnaden dras från den
    gemensamma budgeten. Samma beskrivning en gång till kostar ingenting."""
    from . import tb_ai
    s = _spec(db, user, spec_id)
    if s.status != "COMPLETED":
        raise HTTPException(409, "Beskrivningen är inte läst")
    api_budget.require()
    try:
        s.ai = tb_ai.run(s, matched_items(s, with_ai=False), user.email)
    except api_budget.BudgetExhausted as e:
        raise HTTPException(402, str(e)) from None
    except RuntimeError as e:
        raise HTTPException(503, f"AI-kontrollen kunde inte köras: {e}") from None
    except Exception:
        import logging
        logging.getLogger("vvs.tb_ai").exception("AI-kontrollen misslyckades")
        raise HTTPException(502, "AI-kontrollen kunde inte köras just nu. Försök igen.") from None
    db.commit()
    return _ai_out(s)


class MissedIn(BaseModel):
    accept: bool


@router.post("/api/tech-specs/{spec_id}/ai/missed/{key}")
def decide_missed(spec_id: str, key: str, body: MissedIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Godkänn ett AI-förslag (det blir en post, utan antal) eller avfärda det."""
    from sqlalchemy.orm.attributes import flag_modified
    from . import tb_ai
    s = _spec(db, user, spec_id)
    a = dict(s.ai or {})
    missed = [dict(m) for m in a.get("missed") or []]
    m = next((x for x in missed if x.get("key") == key), None)
    if m is None:
        raise HTTPException(404, "Förslaget finns inte")
    if m.get("state") == "förslag":
        m["state"] = "godkänd" if body.accept else "avfärdad"
        if body.accept:
            items = list(s.items or [])
            items.append(tb_ai.as_item(m, items, user.email))
            s.items = items
            flag_modified(s, "items")
    a["missed"] = missed
    s.ai = a
    flag_modified(s, "ai")
    db.commit()
    return _ai_out(s)


def _facets(items: list[dict[str, Any]]) -> dict[str, Any]:
    def count(key):
        c = Counter(it.get(key) or "" for it in items)
        return [{"value": k, "n": n} for k, n in sorted(c.items(), key=lambda kv: (kv[0] == "", kv[0].lower()))]
    status = Counter(it["match"]["status"] for it in items)
    return {"categories": count("category"), "manufacturers": count("manufacturer"), "kinds": count("kind"),
            "status": [{"value": k, "n": status.get(k, 0)} for k in ("hittad", "möjlig", "förslag", "saknas", "allmänt", "annan")
                       if status.get(k, 0) or k in ("hittad", "möjlig", "saknas")]}


@router.get("/api/tech-specs/{spec_id}")
def get_tech_spec(spec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Beskrivningens poster med var de finns: hittad, möjlig träff eller saknas, och vad det vilar på."""
    s = _spec(db, user, spec_id)
    items = matched_items(s)
    return {**_spec_out(s), "items": items, "facets": _facets(items), "sources": _sources(material_index())}


@router.delete("/api/tech-specs/{spec_id}")
def delete_tech_spec(spec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _spec(db, user, spec_id)
    folder = {"ifc": "ifc", "lista": "lists"}.get(s.source or "", "techspecs")
    storage.delete_prefix(f"{folder}/{s.project_id}/{s.id}")
    db.delete(s)
    db.commit()
    return {"ok": True}


class MailIn(BaseModel):
    ids: list[str] | None = None      # posterna; utan dem alla som saknas
    to: str = ""
    sender: str = ""


@router.post("/api/tech-specs/{spec_id}/mail")
def mail_draft(spec_id: str, body: MailIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ett mejlutkast för det som inte finns i materialboken eller katalogen - eller för de poster som valts."""
    s = _spec(db, user, spec_id)
    items = matched_items(s)
    if body.ids:
        want = set(body.ids)
        chosen = [it for it in items if it["id"] in want]
    else:
        chosen = [it for it in items if it["match"]["status"] == "saknas"]
    if not chosen:
        raise HTTPException(422, "Inga poster att fråga om: allt finns i materialboken eller katalogen.")
    p = db.get(Project, s.project_id)
    drafts = drafts_by_maker(chosen, project=p.name if p else "", document=s.title or s.filename, to=body.to,
                             sender=body.sender or user.email)
    return {"drafts": drafts, "n": len(chosen)}


def _disposition(filename: str) -> str:
    """Ett filnamn med å, ä och ö: en ASCII-version för gamla klienter och det riktiga namnet enligt RFC 5987."""
    from urllib.parse import quote
    import unicodedata
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode() or "material.csv"
    ascii_name = ascii_name.replace('"', "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _num(v) -> str:
    return "" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)).replace(".", ",")


def _drawing_text(fd: dict[str, Any] | None) -> str:
    if not fd:
        return ""
    if fd["kind"] == "antal":
        return f"{fd['tag']}: " + ", ".join(f"{k} ({n})" for k, n in fd["sheets"].items())
    dn = ", ".join(f"DN{k} {_num(v)} m" for k, v in fd.get("by_dn", {}).items())
    return f"{fd['system']}: {dn}" + (f"; att granska {_num(fd['review_m'])} m" if fd.get("review_m") else "")


def _rsk_text(m: dict[str, Any]) -> str:
    r = m.get("rsk") or {}
    if r.get("kind") == "ai":
        return f"{r.get('value')} (AI-val{'' if r.get('sure') else ', kontrollera'})"
    if r.get("kind") == "storlek":
        return "välj storlek: " + ", ".join(f"{v.get('size') or ''} {v['rsk']}".strip() for v in r.get("variants") or [])
    return r.get("value") or ""


@router.get("/api/tech-specs/{spec_id}/items.csv")
def tech_spec_csv(spec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _spec(db, user, spec_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Kod", "Slag", "Benämning", "Antal", "Enhet", "Mängd som skrivet", "Fabrikat", "Typ", "RSK",
                "RSK förslag", "Grund", "Eget förslag (granskas)",
                "Antal ur ritning", "Antal i underlaget", "Ritning",
                "Art.nr", "Eller likvärdig", "Kategori", "Underkategori", "AMA", "Sida", "Status", "Träff", "Källa",
                "Specifikation"])
    for it in matched_items(s):
        m = it["match"]
        h = m["hits"][0] if m["hits"] else {}
        q = it.get("total_quantity")
        w.writerow([it["code"], it["kind"], it["name"], "" if q is None else str(q).replace(".", ","), it["unit"],
                    it["quantity_text"], it["manufacturer"], it["type"], " ".join(rsk_pretty(r) for r in it["rsk"]),
                    _rsk_text(m), m.get("basis", ""),
                    "; ".join(f"{x.get('ref')} {x.get('name')}" for x in (m.get("suggestions") or [])[:3]),
                    _num(it.get("total_quantity")) if it.get("quantity_from") == "ritning" else "",
                    _num(it.get("description_quantity")) if it.get("quantity_from") == "ritning" else "",
                    _drawing_text(it.get("from_drawing")),
                    " ".join(it["art_nr"]),
                    "ja" if it["or_equal"] else "", it["category"], it["subcategory"], it["ama_code"], it["page"],
                    m["status"], " ".join(x for x in (h.get("ref"), h.get("name")) if x), h.get("source", ""),
                    "; ".join(f"{k} {v}" for k, v in (it.get("spec") or {}).items())])
    name = os.path.splitext(s.filename)[0]
    return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": _disposition(f"material-{name}.csv")})
