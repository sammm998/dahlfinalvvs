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
            path = os.path.join(os.path.dirname(__file__), "data", "material.json.gz")
            if os.path.exists(path):
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    book = json.load(fh)
                ix.add_material_book(book.get("rows", []), label=f"Materialboken ({book.get('source') or 'materialsortering'})")
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


def _spec_out(s: TechSpec) -> dict[str, Any]:
    return {"id": s.id, "project_id": s.project_id, "filename": s.filename, "n_pages": s.n_pages,
            "size_bytes": s.size_bytes, "status": s.status, "error": s.error, "title": s.title,
            "stats": s.stats or {}, "created_at": s.created_at}


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
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Den tekniska beskrivningen ska vara en PDF")
    data = await _read_capped(file, MAX_SPEC_BYTES)
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Filen är inte en giltig PDF")
    sha = hashlib.sha256(data).hexdigest()
    same = db.query(TechSpec).filter(TechSpec.project_id == p.id, TechSpec.sha256 == sha).first()
    if same is not None:
        return {**_spec_out(same), "duplicate": True}
    try:
        out = await run_in_threadpool(read_tech_spec_bytes, data)
    except Exception:
        raise HTTPException(400, "PDF-filen kunde inte läsas")
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
    s.storage_key = storage.put(f"techspecs/{p.id}/{s.id}.pdf", io.BytesIO(data))
    db.commit()
    return {**_spec_out(s), "duplicate": False}


@router.get("/api/projects/{project_id}/tech-specs")
def list_tech_specs(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    rows = db.query(TechSpec).filter(TechSpec.project_id == p.id).order_by(TechSpec.created_at.desc()).all()
    return [_spec_out(s) for s in rows]


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


def matched_items(s: TechSpec) -> list[dict[str, Any]]:
    ix = material_index()
    return [{**it, "match": item_match(ix, it)} for it in (s.items or [])]


def _facets(items: list[dict[str, Any]]) -> dict[str, Any]:
    def count(key):
        c = Counter(it.get(key) or "" for it in items)
        return [{"value": k, "n": n} for k, n in sorted(c.items(), key=lambda kv: (kv[0] == "", kv[0].lower()))]
    status = Counter(it["match"]["status"] for it in items)
    return {"categories": count("category"), "manufacturers": count("manufacturer"), "kinds": count("kind"),
            "status": [{"value": k, "n": status.get(k, 0)} for k in ("hittad", "möjlig", "saknas", "allmänt", "annan")
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
    storage.delete_prefix(f"techspecs/{s.project_id}/{s.id}")
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


def _rsk_text(m: dict[str, Any]) -> str:
    r = m.get("rsk") or {}
    if r.get("kind") == "storlek":
        return "välj storlek: " + ", ".join(f"{v.get('size') or ''} {v['rsk']}".strip() for v in r.get("variants") or [])
    return r.get("value") or ""


@router.get("/api/tech-specs/{spec_id}/items.csv")
def tech_spec_csv(spec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _spec(db, user, spec_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Kod", "Slag", "Benämning", "Antal", "Enhet", "Mängd som skrivet", "Fabrikat", "Typ", "RSK",
                "RSK förslag",
                "Art.nr", "Eller likvärdig", "Kategori", "Underkategori", "AMA", "Sida", "Status", "Träff", "Källa",
                "Specifikation"])
    for it in matched_items(s):
        m = it["match"]
        h = m["hits"][0] if m["hits"] else {}
        q = it.get("total_quantity")
        w.writerow([it["code"], it["kind"], it["name"], "" if q is None else str(q).replace(".", ","), it["unit"],
                    it["quantity_text"], it["manufacturer"], it["type"], " ".join(it["rsk"]), _rsk_text(m),
                    " ".join(it["art_nr"]),
                    "ja" if it["or_equal"] else "", it["category"], it["subcategory"], it["ama_code"], it["page"],
                    m["status"], " ".join(x for x in (h.get("ref"), h.get("name")) if x), h.get("source", ""),
                    "; ".join(f"{k} {v}" for k, v in (it.get("spec") or {}).items())])
    name = os.path.splitext(s.filename)[0]
    return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="material-{name}.csv"'})
