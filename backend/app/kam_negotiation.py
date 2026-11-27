"""KAM: årlig prisförhandling för en KAM-kund.

  POST   /api/kam/negotiations                       ny förhandling {name, customer, kundnr, valid_from}
  GET    /api/kam/negotiations                       mina (administratör: alla)
  GET    /api/kam/negotiations/{id}                  förhandlingen: filer, underlagets status, korgarnas totaler
  DELETE /api/kam/negotiations/{id}
  POST   /api/kam/negotiations/{id}/files            filer (Excel, .xlsm, .xlsb, rabattbrev .txt) - läses i bakgrunden
  POST   /api/kam/negotiations/{id}/files/reset      töm underlaget
  GET    /api/kam/negotiations/{id}/groups           justeringsvyn: en rad per kalkylgrupp med räta linjen per korg
  PUT    /api/kam/negotiations/{id}/adjustments      {rab: {kg: % | null}, netto: {kg: andel | null}, comments: {kg: text}}
  GET    /api/kam/negotiations/{id}/insights         avvikelser och förslag
  POST   /api/kam/negotiations/{id}/insights/apply   {kgs: [...]} - för in förslagen
  GET    /api/kam/negotiations/{id}/groups/{kg}/articles
  GET    /api/kam/negotiations/{id}/presentation     det kunden får se: totalt och per produktområde
  GET    /api/kam/negotiations/{id}/export.xlsx?kind=intern|kund
  GET    /api/kam/negotiations/{id}/rabattbrev.txt
  POST   /api/kam/negotiations/{id}/submit|approve|reject|register

Ingen skarp koppling till M3 finns: underlaget läses ur filer. Räkningen följer arbetsbokens formler och ger samma
totaler (se vvs_engine.kam_pricing). Registreringen skriver kundens nya rabatter i tjänstens offertdata.
"""
from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import os
import re
import tempfile
import threading
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vvs_engine import kam_pricing as KP

from . import offers as O
from .auth import current_admin, current_user
from .db import KamNegotiation, SessionLocal, User, get_db
from .storage import storage

router = APIRouter(tags=["kam"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD = 400 * 1024 * 1024
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[str, Any]] = {}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _key(nid: str, what: str) -> str:
    return f"kam/neg/{nid}/{what}.json.gz"


def _save(nid: str, what: str, obj: Any) -> None:
    raw = gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 5)
    storage.put(_key(nid, what), io.BytesIO(raw))
    _CACHE.pop(f"{nid}/{what}", None)


def _load(nid: str, what: str, default=None):
    k = _key(nid, what)
    if not storage.exists(k):
        return default
    try:
        stamp = str(os.path.getmtime(storage.path(k)))
    except (OSError, NotImplementedError, AttributeError):
        stamp = ""
    hit = _CACHE.get(f"{nid}/{what}")
    if hit and stamp and hit[0] == stamp:
        return hit[1]
    with storage.open(k) as fh:
        obj = json.loads(gzip.decompress(fh.read()).decode("utf-8"))
    if stamp:
        _CACHE[f"{nid}/{what}"] = (stamp, obj)
    return obj


def _inputs(nid: str) -> dict[str, Any]:
    inp = _load(nid, "inputs") or KP.empty_inputs()
    for k in ("kund_bp", "kund_netto"):
        inp[k] = {a: tuple(v) for a, v in (inp.get(k) or {}).items()}
    return inp


def _neg(db: Session, user: User, nid: str) -> KamNegotiation:
    n = db.get(KamNegotiation, nid)
    if not n or (n.created_by != user.id and (user.role or "member") != "admin"):
        raise HTTPException(404, "Förhandlingen finns inte")
    return n


def _log(n: KamNegotiation, user: User | None, what: str) -> None:
    n.history = [*(n.history or []), {"at": _now().isoformat(), "by": user.email if user else "tjänsten", "what": what}]
    n.updated_at = _now()


def _groups(n: KamNegotiation) -> list[dict[str, Any]]:
    grs = _load(n.id, "groups") or []
    return KP.set_adjustments(grs, n.adjustments, n.netto)


def _settings(n: KamNegotiation) -> dict[str, Any]:
    return {**{"brv_drop": 0.01, "price_gap": 0.01, "share_ratio": 0.5, "seg_gap": 0.03, "max_step": 5.0,
               "min_volume": 10000.0, "min_brv": 0.05}, **(n.settings or {}).get("insights", {})}


def _summary(n: KamNegotiation, grs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    grs = _groups(n) if grs is None else grs
    return {b: KP.totals(grs, b) for b in KP.BASKETS}


def _out(n: KamNegotiation, full: bool = True) -> dict[str, Any]:
    d = {k: getattr(n, k) for k in ("id", "name", "customer", "kundnr", "valid_from", "status", "files", "job",
                                    "history", "attest_saljare", "attest_saljledare", "settings")}
    d["created_at"] = n.created_at.isoformat() if n.created_at else None
    d["updated_at"] = n.updated_at.isoformat() if n.updated_at else None
    d["n_adjusted"] = len([k for k, v in (n.adjustments or {}).items() if v is not None])
    d["simulated"] = True
    if full:
        d["data_status"] = _load(n.id, "status") or {}
        d["totals"] = _summary(n) if storage.exists(_key(n.id, "groups")) else None
        d["basket_names"] = KP.BASKET_NAMES
    return d


# ---------------------------------------------------------------- inläsning i bakgrunden

def _recompute(nid: str, inp: dict[str, Any]) -> dict[str, Any]:
    rows = KP.compute_articles(inp)
    grs = KP.groups(inp, rows)
    seg = KP.segment_brv(inp, rows)
    by_kg: dict[str, list] = {}
    for r in rows:
        by_kg.setdefault(r["kg_ny"], []).append({k: r[k] for k in (
            "artnr", "namn", "kg_nu", "moved", "levnamn", "month", "in_nu", "in_ny", "brutto_nu", "brutto_ny", "rab_nu",
            "bonus_nu", "bonus_ny", "fn_nu", "nn_nu", "knet_ny", "lin_a", "lin_f", "qty")})
    _save(nid, "groups", grs)
    _save(nid, "articles", by_kg)
    _save(nid, "segments", seg)
    st = KP.status(inp)
    st["computed_articles"] = len(rows)
    st["groups"] = len(grs)
    _save(nid, "status", st)
    return st


def _job(nid: str, **kw) -> None:
    with SessionLocal() as db:
        n = db.get(KamNegotiation, nid)
        if not n:
            return
        n.job = {**(n.job or {}), **kw, "at": _now().isoformat()}
        db.commit()


def _ingest(nid: str, paths: list[tuple[str, str]], user_email: str) -> None:
    """Läser filerna, lägger in dem i underlaget och räknar om. Körs i en tråd."""
    try:
        with _LOCK:
            inp = _inputs(nid)
            found: list[dict[str, Any]] = []
            adj_from_book: dict[str, float] = {}
            # arbetsboken först: filer som laddas upp var för sig går före dess blad
            paths = sorted(paths, key=lambda np: 0 if np[0].lower().endswith(".xlsm") and os.path.getsize(np[1]) > 30 * 1024 * 1024 else 1)
            for name, path in paths:
                _job(nid, state="running", step=f"Läser {name}")
                low = name.lower()
                if low.endswith(".xlsm") and os.path.getsize(path) > 30 * 1024 * 1024:
                    parts = KP.parse_workbook_path(path, progress=lambda m: _job(nid, step=f"{name}: {m}"))
                else:
                    with open(path, "rb") as fh:
                        data = fh.read()
                    parts = KP.detect_and_parse(name, data)
                kinds = []
                for kind, content in parts:
                    KP.merge(inp, kind, content)
                    kinds.append(kind)
                    if kind == "justeringsvy":
                        adj_from_book.update(content.get("adjustments") or {})
                found.append({"name": name, "kinds": kinds, "at": _now().isoformat(), "by": user_email})
            _job(nid, step="Räknar")
            for k in ("kund_bp", "kund_netto"):
                inp[k] = {a: list(v) for a, v in inp[k].items()}
            _save(nid, "inputs", inp)
            for k in ("kund_bp", "kund_netto"):
                inp[k] = {a: tuple(v) for a, v in inp[k].items()}
            st = _recompute(nid, inp)
        with SessionLocal() as db:
            n = db.get(KamNegotiation, nid)
            if n:
                n.files = [*(n.files or []), *found]
                if adj_from_book:
                    n.adjustments = {**adj_from_book, **(n.adjustments or {})}
                unknown = [f["name"] for f in found if not f["kinds"]]
                n.job = {"state": "done", "at": _now().isoformat(), "step": "Klart",
                         "unknown": unknown, "articles": st.get("computed_articles"), "groups": st.get("groups")}
                _log(n, None, "Underlag inläst: " + ", ".join(f"{f['name']} ({', '.join(f['kinds']) or 'okänd'})" for f in found))
                db.commit()
    except Exception as e:  # noqa: BLE001 - visas för användaren
        _job(nid, state="error", step=f"Fel: {e}")
    finally:
        for _, p in paths:
            try:
                os.unlink(p)
            except OSError:
                pass


# ---------------------------------------------------------------- förhandlingen

class NewNeg(BaseModel):
    name: str = ""
    customer: str = ""
    kundnr: str = ""
    valid_from: str = ""


@router.post("/api/kam/negotiations")
def create(body: NewNeg, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not (body.name.strip() or body.customer.strip()):
        raise HTTPException(422, "Ge förhandlingen ett namn eller en kund")
    n = KamNegotiation(name=body.name.strip() or f"{body.customer.strip()} {dt.date.today().year}",
                       customer=body.customer.strip(), kundnr=body.kundnr.strip(), valid_from=body.valid_from.strip(),
                       created_by=user.id, settings={}, job={})
    _log(n, user, "Förhandlingen skapad")
    db.add(n)
    db.commit()
    return _out(n)


@router.get("/api/kam/negotiations")
def list_negs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(KamNegotiation)
    if (user.role or "member") != "admin":
        q = q.filter(KamNegotiation.created_by == user.id)
    return {"negotiations": [_out(n, full=False) for n in q.order_by(KamNegotiation.updated_at.desc()).limit(200)]}


@router.get("/api/kam/negotiations/{nid}")
def get_neg(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(_neg(db, user, nid))


class Meta(BaseModel):
    name: str | None = None
    customer: str | None = None
    kundnr: str | None = None
    valid_from: str | None = None
    insights: dict[str, float] | None = None


@router.put("/api/kam/negotiations/{nid}")
def update_meta(nid: str, body: Meta, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    for k in ("name", "customer", "kundnr", "valid_from"):
        v = getattr(body, k)
        if v is not None:
            setattr(n, k, v.strip())
    if body.insights is not None:
        n.settings = {**(n.settings or {}), "insights": {k: float(v) for k, v in body.insights.items()}}
    _log(n, user, "Uppgifterna ändrade")
    db.commit()
    return _out(n)


@router.delete("/api/kam/negotiations/{nid}")
def delete(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    if n.status in ("attest", "godkand"):
        raise HTTPException(409, "Förhandlingen väntar på eller har attest och kan inte tas bort")
    storage.delete_prefix(f"kam/neg/{n.id}/")
    db.delete(n)
    db.commit()
    return {"ok": True}


@router.post("/api/kam/negotiations/{nid}/files")
async def upload(nid: str, files: list[UploadFile] = File(...), user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    if (n.job or {}).get("state") == "running":
        raise HTTPException(409, "En inläsning pågår redan")
    tmpdir = os.path.join(tempfile.gettempdir(), "kam-upload")
    os.makedirs(tmpdir, exist_ok=True)
    paths = []
    for f in files:
        name = os.path.basename(f.filename or "fil")
        if not re.search(r"\.(xlsx|xlsm|xlsb|txt|csv)$", name, re.I):
            raise HTTPException(422, f"{name}: bara Excel (.xlsx, .xlsm, .xlsb) och rabattbrev (.txt) kan läsas")
        fd, path = tempfile.mkstemp(dir=tmpdir, suffix="-" + re.sub(r"[^\w.\-]", "_", name))
        size = 0
        with os.fdopen(fd, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    out.close()
                    os.unlink(path)
                    raise HTTPException(413, f"{name} är större än 400 MB")
                out.write(chunk)
        paths.append((name, path))
    n.job = {"state": "running", "step": "Väntar", "at": _now().isoformat()}
    db.commit()
    threading.Thread(target=_ingest, args=(n.id, paths, user.email), daemon=True).start()
    return _out(n)


@router.post("/api/kam/negotiations/{nid}/files/reset")
def reset(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    if (n.job or {}).get("state") == "running":
        raise HTTPException(409, "En inläsning pågår")
    storage.delete_prefix(f"kam/neg/{n.id}/")
    for k in list(_CACHE):
        if k.startswith(n.id + "/"):
            _CACHE.pop(k, None)
    n.files, n.job = [], {}
    _log(n, user, "Underlaget tömt")
    db.commit()
    return _out(n)


# ---------------------------------------------------------------- justeringsvyn

def _compact(gr: dict[str, Any]) -> dict[str, Any]:
    keep = ("kg", "name", "omr", "kat", "omr_name", "kat_name", "affomr", "forhomr", "leverantor", "n_articles", "moved",
            "month", "rab_nu", "rab_level", "new_group", "rab_ny", "rab_old", "netto_pct")
    d = {k: gr.get(k) for k in keep}
    d["b"] = {b: {k: round(v, 2) for k, v in s.items() if k in ("qty", "in_nu", "in_ny", "nn_nu", "nn_ny", "lin_a", "lin_f", "n")}
              for b, s in gr["b"].items() if s}
    return d


@router.get("/api/kam/negotiations/{nid}/groups")
def get_groups(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    grs = _groups(n)
    seg = _load(n.id, "segments") or {}
    return {"groups": [_compact(g) for g in grs], "comments": n.comments or {}, "totals": _summary(n, grs),
            "segments": {name: {k: {"brv": v.get("brv"), "netto": v.get("netto")} for k, v in s.items()} for name, s in seg.items()},
            "basket_names": KP.BASKET_NAMES, "supplier_info": (_inputs(n.id).get("supplier_info") or [])}


class Adjust(BaseModel):
    rab: dict[str, float | None] = {}
    netto: dict[str, float | None] = {}
    comments: dict[str, str] = {}


def _editable(n: KamNegotiation) -> None:
    if n.status not in ("utkast", "avslagen"):
        raise HTTPException(409, "Förhandlingen är skickad för attest och kan inte ändras")


@router.put("/api/kam/negotiations/{nid}/adjustments")
def adjust(nid: str, body: Adjust, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    _editable(n)
    adj, net, com = dict(n.adjustments or {}), dict(n.netto or {}), dict(n.comments or {})
    for k, v in body.rab.items():
        k = k.upper()
        if v is None:
            adj.pop(k, None)
        elif not 0 <= v < 100:
            raise HTTPException(422, f"Rabatten för {k} ska vara 0-99 %")
        else:
            adj[k] = round(float(v), 3)
    for k, v in body.netto.items():
        k = k.upper()
        if v is None or v == 0:
            net.pop(k, None)
        elif not -0.9 < v < 2:
            raise HTTPException(422, f"Nettoprisjusteringen för {k} är orimlig")
        else:
            net[k] = float(v)
    for k, v in body.comments.items():
        if v.strip():
            com[k.upper()] = v.strip()[:2000]
        else:
            com.pop(k.upper(), None)
    n.adjustments, n.netto, n.comments = adj, net, com
    if n.status == "avslagen":
        n.status = "utkast"
    n.updated_at = _now()
    db.commit()
    return {"totals": _summary(n), "n_adjusted": len(adj)}


@router.get("/api/kam/negotiations/{nid}/insights")
def get_insights(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    grs = _groups(n)
    return {"insights": KP.insights(grs, _load(n.id, "segments") or {}, _settings(n)), "settings": _settings(n)}


class Apply(BaseModel):
    kgs: list[str] = []


@router.post("/api/kam/negotiations/{nid}/insights/apply")
def apply(nid: str, body: Apply, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    _editable(n)
    ins = {i["kg"]: i for i in KP.insights(_groups(n), _load(n.id, "segments") or {}, _settings(n)) if i["suggestion"]}
    want = [k.upper() for k in body.kgs] if body.kgs else list(ins)
    adj, net, done = dict(n.adjustments or {}), dict(n.netto or {}), []
    for k in want:
        s = (ins.get(k) or {}).get("suggestion")
        if not s:
            continue
        if s.get("type") == "netto":
            net[k] = round(s["pct"], 4)
        else:
            adj[k] = s["rab"]
        done.append(k)
    n.adjustments, n.netto = adj, net
    _log(n, user, f"Förslag införda för {len(done)} kalkylgrupper")
    db.commit()
    return {"applied": done, "totals": _summary(n)}


@router.get("/api/kam/negotiations/{nid}/groups/{kg}/articles")
def articles(nid: str, kg: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    kg = kg.upper()
    rows = (_load(n.id, "articles") or {}).get(kg) or []
    x = float((n.adjustments or {}).get(kg, next((g["rab_nu"] for g in _groups(n) if g["kg"] == kg), 0.0)))
    p = float((n.netto or {}).get(kg) or 0.0)
    out = []
    for r in rows:
        nn_ny = r["lin_a"] * (1 - x / 100) + r["lin_f"] * (1 + p)
        out.append({**{k: r[k] for k in ("artnr", "namn", "kg_nu", "moved", "levnamn", "month", "brutto_nu", "brutto_ny",
                                          "rab_nu", "bonus_nu", "bonus_ny", "in_nu", "in_ny", "nn_nu")},
                    "rab_ny": x, "nn_ny": nn_ny, "netto_unikt": bool(r["knet_ny"]),
                    "brv_nu": (r["nn_nu"] - r["in_nu"]) / r["nn_nu"] if r["nn_nu"] else None,
                    "brv_ny": (nn_ny - r["in_ny"]) / nn_ny if nn_ny else None,
                    "prisdiff": nn_ny / r["nn_nu"] - 1 if r["nn_nu"] else None, "qty": r["qty"]})
    out.sort(key=lambda r: -(r["nn_nu"] * r["qty"].get("kund", 0)))
    return {"kg": kg, "rab_ny": x, "netto_pct": p, "articles": out}


@router.get("/api/kam/negotiations/{nid}/presentation")
def presentation(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    grs = _groups(n)
    t = KP.totals(grs, "kund")
    areas = KP.by_area(grs, "kund")
    return {"customer": n.customer, "name": n.name, "valid_from": n.valid_from,
            "totals": {k: t[k] for k in ("nn_nu", "nn_ny", "prisdiff")}, "riks_prisdiff": KP.totals(grs, "riks")["prisdiff"],
            "areas": [{k: a[k] for k in ("omr", "name", "nn_nu", "nn_ny", "prisdiff")} for a in areas],
            "supplier_info": _inputs(n.id).get("supplier_info") or [],
            "changed_groups": [{"kg": g["kg"], "name": g["name"], "rab_nu": g["rab_nu"], "rab_ny": g["rab_ny"]}
                               for g in grs if abs(g["rab_ny"] - g["rab_nu"]) > 1e-9]}


@router.get("/api/kam/negotiations/{nid}/export.xlsx")
def export(nid: str, kind: str = "intern", user: User = Depends(current_user), db: Session = Depends(get_db)):
    if kind not in ("intern", "kund"):
        raise HTTPException(422, "kind ska vara intern eller kund")
    n = _neg(db, user, nid)
    grs = _groups(n)
    if not grs:
        raise HTTPException(409, "Läs in underlaget först")
    ins = KP.insights(grs, _load(n.id, "segments") or {}, _settings(n)) if kind == "intern" else None
    data = KP.to_xlsx({"customer": n.customer, "name": n.name, "valid_from": n.valid_from}, _inputs(n.id), grs, kind, ins)
    safe = re.sub(r"[^\w\-]+", "_", n.customer or n.name or "kund").strip("_")
    return Response(data, media_type=XLSX, headers={
        "Content-Disposition": f'attachment; filename="Prisjustering_{safe}_{kind}_{dt.date.today().isoformat()}.xlsx"'})


@router.get("/api/kam/negotiations/{nid}/rabattbrev.txt")
def rabattbrev(nid: str, only_changed: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    grs = _groups(n)
    txt = KP.rabattbrev_txt(grs, _inputs(n.id), only_changed)
    safe = re.sub(r"[^\w\-]+", "_", n.customer or "kund").strip("_")
    return Response(txt.encode("cp1252", errors="replace"), media_type="text/plain; charset=windows-1252",
                    headers={"Content-Disposition": f'attachment; filename="Rabattbrev_{safe}.txt"'})


# ---------------------------------------------------------------- attest och registrering

class Decision(BaseModel):
    comment: str = ""


@router.post("/api/kam/negotiations/{nid}/submit")
def submit(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = _neg(db, user, nid)
    _editable(n)
    grs = _groups(n)
    if not grs:
        raise HTTPException(409, "Läs in underlaget först")
    t = KP.totals(grs, "kund")
    n.status, n.attest_saljare = "attest", f"{user.name or user.email} {_now():%Y-%m-%d}"
    _log(n, user, f"Skickad för attest: prisdiff {((t['prisdiff'] or 0) * 100):.2f} %, BRV {((t['brv_nu'] or 0) * 100):.2f} → "
                  f"{((t['brv_ny'] or 0) * 100):.2f} %")
    db.commit()
    return _out(n)


@router.post("/api/kam/negotiations/{nid}/approve")
def approve(nid: str, body: Decision, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    n = _neg(db, admin, nid)
    if n.status != "attest":
        raise HTTPException(409, "Förhandlingen väntar inte på attest")
    if n.created_by == admin.id:
        raise HTTPException(403, "Säljledarens attest ska göras av en annan person än säljaren")
    n.status, n.attest_saljledare = "godkand", f"{admin.name or admin.email} {_now():%Y-%m-%d}"
    _log(n, admin, "Attesterad av säljledare" + (f": {body.comment}" if body.comment else ""))
    db.commit()
    return _out(n)


@router.post("/api/kam/negotiations/{nid}/reject")
def reject(nid: str, body: Decision, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    n = _neg(db, admin, nid)
    if n.status != "attest":
        raise HTTPException(409, "Förhandlingen väntar inte på attest")
    n.status = "avslagen"
    _log(n, admin, "Avslagen" + (f": {body.comment}" if body.comment else ""))
    db.commit()
    return _out(n)


@router.post("/api/kam/negotiations/{nid}/register")
def register(nid: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Simulerad M3-registrering: kundens rabattbrev (med justeringarna) blir kundens rabatter i offertdatan."""
    n = _neg(db, admin, nid)
    if n.status != "godkand":
        raise HTTPException(409, "Förhandlingen måste vara attesterad innan den registreras")
    if not n.kundnr:
        raise HTTPException(422, "Ange kundnummer innan registrering")
    grs = _groups(n)
    inp = _inputs(n.id)
    rab = dict(inp["rabattbrev"])
    rab.update({g["kg"]: g["rab_ny"] for g in grs})
    rows = [r for r in O.data("rabatter") if r.get("kundnr") != n.kundnr]
    rows += [{"kundnr": n.kundnr, "grupp": k, "pct": v} for k, v in sorted(rab.items())]
    storage.put(O._key("rabatter"), io.BytesIO(json.dumps({"file": f"KAM-förhandling {n.id}", "updated_at": _now().isoformat(),
                                                            "rows": rows}, ensure_ascii=False).encode("utf-8")))
    O._CACHE.pop("rabatter", None)
    n.status = "registrerad"
    _log(n, admin, f"Registrerad (simulerat M3): {len(rab)} rabattrader för kund {n.kundnr}")
    db.commit()
    return _out(n)
