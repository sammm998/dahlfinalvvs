"""SmartHangers i tjänsten: från IFC-modellen till granskade, producerade, packade och monterade hängare.

  regler          GET/PUT /api/prefab/rules, POST /api/prefab/rules/verify (administratören). Varje ändring blir en
                  ny version; en ny version är overifierad tills en tekniskt ansvarig verifierar den.
  generera        POST /api/projects/{pid}/hangers  (IFC-fil, takhöjder per våning)
  revision        POST /api/hanger-sets/{id}/revise (ny IFC): jämför rören, behåller status där inget ändrats,
                  och visar berörda hängare - producerade, packade, levererade eller monterade är kritiska
  granska         PATCH en hängare (flytta, ändra höjd/pendel, status, avvikelse, kommentar), lägg till, ta bort
  godkänna        POST /api/hanger-sets/{id}/approve {kind: offert | konstruktion | produktion}
                  produktionsfrisläppning kräver godkänd konstruktion, verifierade regler och inga flaggade
                  hängare som ingen har granskat
  produktion      status producerad/packad/levererad/monterad; en hängare produceras först när uppsättningen är
                  frisläppt
  ut              materiallista och kapplan och kollin (Excel), etiketter med QR (PDF), IFC med hängarna, kalkyl
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from vvs_engine.hangers import calc as HC
from vvs_engine.hangers import generate as HG
from vvs_engine.hangers import ifc_export as HX
from vvs_engine.hangers import qr as HQ
from vvs_engine.hangers import rules as HR
from vvs_engine.hangers.geometry import pipes as read_pipes

from .auth import current_admin, current_user
from .db import HangerSet, Project, User, get_db
from .storage import storage

router = APIRouter(tags=["smarthangers"])
RULES_KEY = "prefab/rules.json"
APPROVALS = ("offert", "konstruktion", "produktion")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- regler

def rules() -> dict[str, Any]:
    if storage.exists(RULES_KEY):
        with storage.open(RULES_KEY) as fh:
            return HR.merged(json.load(fh))
    return HR.default()


def _save_rules(r: dict[str, Any]) -> None:
    raw = json.dumps(r, ensure_ascii=False).encode("utf-8")
    storage.put(RULES_KEY, io.BytesIO(raw))
    storage.put(f"prefab/rules-v{r['version']}.json", io.BytesIO(raw))


@router.get("/api/prefab/rules")
def get_rules(user: User = Depends(current_user)):
    return rules()


@router.put("/api/prefab/rules")
def put_rules(body: dict[str, Any], user: User = Depends(current_admin)):
    """En ny version av reglerna. Den är overifierad tills någon verifierar den."""
    cur = rules()
    new = HR.merged({**cur, **{k: v for k, v in body.items() if k not in ("version", "verified", "verified_by", "verified_at")}})
    new.update(version=int(cur.get("version") or 1) + 1, verified=False, verified_by=None, verified_at=None,
               changed_by=user.email, changed_at=_now())
    _save_rules(new)
    return new


@router.post("/api/prefab/rules/verify")
def verify_rules(user: User = Depends(current_admin)):
    r = rules()
    r.update(verified=True, verified_by=user.email, verified_at=_now(),
             note=f"Verifierad av {user.email} {_now()[:10]}")
    _save_rules(r)
    return r


# ---------------------------------------------------------------- uppsättningarna

def _project(db: Session, user: User, pid: str) -> Project:
    p = db.get(Project, pid)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Projektet finns inte")
    return p


# Rollerna ur systembeskrivningen. Projektets ägare och en systemadministratör har alla; andra konton bjuds in
# till en uppsättning med de roller de behöver.
ROLES = {
    "projektadmin": "Projektadministratör - modeller, revisioner, roller och produktionsfrisläppning",
    "granskare": "BIM-/konstruktionsgranskare - geometri, regler, avsteg och godkänd konstruktion",
    "kalkyl": "Sälj/kalkyl - kalkyl och offert",
    "produktion": "Produktionsoperatör - produktion, egenkontroll och avvikelser",
    "lager": "Lager/pack - plock, packning, märkning och leverans",
    "montor": "Montör - montageguide och kvittering",
}


def _roles(s: HangerSet, db: Session, user: User) -> set[str] | None:
    """Rollerna användaren har i uppsättningen, eller None om hen inte får se den."""
    p = db.get(Project, s.project_id)
    if p is not None and p.owner_id == user.id or (user.role or "") == "admin":
        return set(ROLES)
    got = ((s.settings or {}).get("members") or {}).get((user.email or "").lower())
    return set(got) if got else None


def _set(db: Session, user: User, sid: str, need: tuple[str, ...] | str | None = None) -> HangerSet:
    """Uppsättningen, om användaren får se den - och, med need, har någon av de rollerna."""
    s = db.get(HangerSet, sid)
    if s is None:
        raise HTTPException(404, "Hängaruppsättningen finns inte")
    have = _roles(s, db, user)
    if have is None:
        raise HTTPException(404, "Hängaruppsättningen finns inte")
    if need:
        need = (need,) if isinstance(need, str) else need
        if not have & set(need):
            raise HTTPException(403, "Kräver rollen " + " eller ".join(ROLES[n].split(" - ")[0] for n in need))
    return s


def _need(s: HangerSet, db: Session, user: User, *need: str) -> None:
    have = _roles(s, db, user) or set()
    if not have & set(need):
        raise HTTPException(403, "Kräver rollen " + " eller ".join(ROLES[n].split(" - ")[0] for n in need))


def _touch(s: HangerSet) -> None:
    for k in ("hangers", "settings", "approvals", "log", "pipes"):
        flag_modified(s, k)
    s.updated_at = dt.datetime.now(dt.timezone.utc)


def _log(s: HangerSet, user: User, action: str, hanger: str | None = None, **kw) -> None:
    s.log = (s.log or []) + [{"at": _now(), "user": user.email, "action": action, "hanger": hanger, **kw}]


def _out(s: HangerSet, full: bool = True) -> dict[str, Any]:
    hs = s.hangers or []
    st = s.settings or {}
    counts: dict[str, int] = {}
    for h in hs:
        counts[h.get("status") or "föreslagen"] = counts.get(h.get("status") or "föreslagen", 0) + 1
    base = {"id": s.id, "project_id": s.project_id, "name": s.name, "revision": s.revision,
            "source_filename": s.source_filename, "approvals": s.approvals or {}, "n": len(hs), "status_counts": counts,
            "flagged": sum(1 for h in hs if h.get("flags")), "rules_version": st.get("rules_version"),
            "rules_verified": st.get("rules_verified"), "updated_at": s.updated_at}
    if full:
        base.update(hangers=hs, settings=st, log=(s.log or [])[-200:], skipped=(s.pipes or {}).get("skipped", [])[:200],
                    storeys=(s.pipes or {}).get("storeys", []),
                    pipes_preview=[{"id": p["id"], "start": p["start"][:2], "end": p["end"][:2], "storey": p.get("storey")}
                                   for p in ((s.pipes or {}).get("pipes") or [])[:8000]], ceilings=st.get("ceilings"), diff=st.get("diff"),
                    summary=HG.summary(hs, rules()))
    return base


def _read_ifc(file: UploadFile, data: bytes) -> dict[str, Any]:
    name = (file.filename or "").lower()
    if name.endswith((".zip", ".ifczip")):
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            inner = next((n for n in z.namelist() if n.lower().endswith(".ifc")), None)
            if not inner:
                raise HTTPException(400, "Zip-filen har ingen .ifc i sig")
            data = z.read(inner)
    elif not name.endswith(".ifc"):
        raise HTTPException(400, "Modellen ska vara en .ifc-fil (eller .zip med en .ifc)")
    m = read_pipes(data.decode("utf-8", "replace"))
    if not m["pipes"]:
        raise HTTPException(422, "Modellen har inga rör med läsbar geometri (IfcPipeSegment/IfcFlowSegment)")
    return m


def _generate(s: HangerSet, model: dict[str, Any], heights: dict[str, float]) -> dict[str, Any]:
    r = rules()
    res = HG.generate(model, r, heights, project=s.name, revision=s.revision)
    _pack(s, res["hangers"], r)
    HG.apply_references(res["hangers"], (s.settings or {}).get("references"))
    s.settings = {**(s.settings or {}), "manual_heights": heights, "rules_version": r.get("version"),
                  "rules_verified": bool(r.get("verified")), "ceilings": res["ceilings"]}
    s.pipes = {"pipes": model["pipes"], "fittings": model["fittings"], "storeys": model["storeys"], "skipped": res["skipped"],
               "source": model.get("source"), "ceilings": model.get("ceilings") or []}
    return res


def _pack(s: HangerSet, hangers: list[dict[str, Any]], r: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Kollin med uppsättningens egna gränser och leveransetapper, annars reglernas."""
    r = HR.merged(r or rules())
    pk = (s.settings or {}).get("packing") or {}
    r["packing"] = {**r["packing"], **{k: v for k, v in pk.items() if k in r["packing"] and v not in (None, "")}}
    return HG.pack(hangers, r, by=pk.get("by") or "montage", etapper=pk.get("etapper") or {})


def _heights(raw: str | None) -> dict[str, float]:
    try:
        h = json.loads(raw or "{}")
        return {str(k): float(v) for k, v in h.items() if v not in (None, "")}
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Takhöjderna ska vara {våning: höjd i mm}")


@router.post("/api/projects/{project_id}/hangers")
async def create_set(project_id: str, file: UploadFile = File(...), heights: str = Form("{}"), name: str = Form(""),
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    data = await file.read()
    model = _read_ifc(file, data)
    s = HangerSet(project_id=p.id, name=name or p.name, revision="A", source_filename=os.path.basename(file.filename or ""),
                  created_by=user.email, approvals={}, log=[])
    db.add(s)
    db.flush()
    storage.put(f"prefab/{s.id}/A.ifc", io.BytesIO(data))
    res = _generate(s, model, _heights(heights))
    s.hangers = res["hangers"]
    _log(s, user, "genererad", n=len(res["hangers"]), rules_version=res["rules_version"])
    _touch(s)
    db.commit()
    return _out(s)


def _readings(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Projektets analyserade ritningar: den senaste färdiga läsningen per ritning."""
    from .db import AnalysisJob, Drawing
    rows = (db.query(AnalysisJob, Drawing).join(Drawing, AnalysisJob.drawing_id == Drawing.id)
            .filter(Drawing.project_id == project_id, AnalysisJob.status == "COMPLETED")
            .order_by(AnalysisJob.created_at.desc()).all())
    seen, out = set(), []
    for j, d in rows:
        if d.id in seen or not j.result_key:
            continue
        seen.add(d.id)
        root = storage.path(j.result_key)
        if os.path.isdir(root):
            out.append({"drawing_id": d.id, "job_id": j.id, "filename": d.filename, "root": root})
    return out


@router.get("/api/projects/{project_id}/hangers/drawings")
def hanger_drawings(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ritningarna som kan ge hängare när IFC saknas, med bladen och de bekräftade rören per blad."""
    from vvs_engine.hangers.from_drawing import sheets_in_reading
    p = _project(db, user, project_id)
    return [{k: v for k, v in r.items() if k != "root"} | {"sheets": sheets_in_reading(r["root"])} for r in _readings(db, p.id)]


class FromDrawing(BaseModel):
    drawing_id: str
    ceiling_mm: float | None = None
    drop_mm: float = 300.0
    sheets: list[str] | None = None
    name: str = ""


@router.post("/api/projects/{project_id}/hangers/from-drawing")
def create_from_drawing(project_id: str, body: FromDrawing, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Hängare ur en analyserad 2D-ritning. Höjden är inmatad (takhöjd och avstånd till rörets underkant) och står
    som antagen på varje hängare."""
    from vvs_engine.hangers.from_drawing import ceilings_from, pipes_from_reading
    p = _project(db, user, project_id)
    r = next((x for x in _readings(db, p.id) if x["drawing_id"] == body.drawing_id), None)
    if r is None:
        raise HTTPException(404, "Ritningen har ingen färdig analys i projektet")
    model = pipes_from_reading(r["root"], {"ceiling_mm": body.ceiling_mm, "drop_mm": body.drop_mm}, r["filename"], body.sheets)
    if not model["pipes"]:
        raise HTTPException(422, "Inga bekräftade rör på de valda bladen")
    s = HangerSet(project_id=p.id, name=body.name or f"{p.name} – {r['filename']}", revision="A",
                  source_filename=r["filename"], created_by=user.email, approvals={}, log=[],
                  settings={"source": "2D-ritning", "drawing_id": body.drawing_id, "drop_mm": body.drop_mm,
                            "ceiling_mm": body.ceiling_mm, "sheets": body.sheets})
    db.add(s)
    db.flush()
    res = _generate(s, model, ceilings_from(model))
    s.settings = {**s.settings, "source": "2D-ritning", "drawing_id": body.drawing_id, "drop_mm": body.drop_mm,
                  "ceiling_mm": body.ceiling_mm, "sheets": body.sheets}
    s.hangers = res["hangers"]
    _log(s, user, "genererad ur ritning", n=len(res["hangers"]), drawing=r["filename"])
    _touch(s)
    db.commit()
    return _out(s)


@router.get("/api/projects/{project_id}/hangers")
def list_sets(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    return [_out(s, full=False) for s in db.query(HangerSet).filter(HangerSet.project_id == p.id)
            .order_by(HangerSet.created_at.desc()).all()]


@router.get("/api/hanger-sets/{set_id}")
def get_set(set_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id)
    return {**_out(s), "my_roles": sorted(_roles(s, db, user) or []), "roles": ROLES}


class MembersIn(BaseModel):
    members: dict[str, list[str]]


@router.put("/api/hanger-sets/{set_id}/members")
def set_members(set_id: str, body: MembersIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Vilka andra konton som får arbeta i uppsättningen, och med vilka roller: {"e-post": ["montor", ...]}."""
    s = _set(db, user, set_id, "projektadmin")
    out = {}
    for email, roles in body.members.items():
        e = (email or "").strip().lower()
        if not e or "@" not in e:
            raise HTTPException(422, f"Ogiltig e-postadress: {email}")
        bad = [r for r in roles if r not in ROLES]
        if bad:
            raise HTTPException(422, f"Okänd roll: {', '.join(bad)}. Roller: {', '.join(ROLES)}")
        if roles:
            out[e] = sorted(set(roles))
    s.settings = {**(s.settings or {}), "members": out}
    _log(s, user, "roller", members={k: v for k, v in out.items()})
    _touch(s)
    db.commit()
    return {"members": out, "roles": ROLES}


@router.get("/api/hanger-sets-shared")
def shared_sets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Uppsättningar i andras projekt där användaren har en roll: montören, lagret och produktionen hittar sina."""
    me = (user.email or "").lower()
    out = []
    for s in db.query(HangerSet).order_by(HangerSet.updated_at.desc()).limit(500).all():
        roles = ((s.settings or {}).get("members") or {}).get(me)
        if roles:
            p = db.get(Project, s.project_id)
            out.append({**_out(s, full=False), "project_name": p.name if p else "", "my_roles": roles,
                        "first": (s.hangers or [{}])[0].get("id")})
    return out


@router.delete("/api/hanger-sets/{set_id}")
def delete_set(set_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id, "projektadmin")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/api/hanger-sets/{set_id}/regenerate")
def regenerate(set_id: str, body: dict[str, Any], user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Räkna om med nya takhöjder eller nya regler. Går inte när något redan är producerat."""
    s = _set(db, user, set_id, ("projektadmin", "granskare"))
    if any(h.get("status") in ("producerad", "packad", "levererad", "monterad") for h in s.hangers or []):
        raise HTTPException(409, "Hängare är redan producerade - gör en ny revision i stället")
    heights = {str(k): float(v) for k, v in (body.get("heights") or {}).items() if v not in (None, "")}
    model = {k: (s.pipes or {}).get(k) or [] for k in ("pipes", "fittings", "storeys", "ceilings")}
    model["source"] = (s.pipes or {}).get("source")
    if model["source"] == "2D-ritning":
        # ritningens rör har ingen egen höjd: underkanten flyttas med den nya takhöjden
        drop = float(body.get("drop_mm") or (s.settings or {}).get("drop_mm") or 300)
        for p in model["pipes"]:
            c = heights.get(p.get("storey") or "")
            z = (c - drop + float(p.get("dn") or 0) / 2) if c is not None else 0.0
            p["start"][2] = p["end"][2] = z
            p["drop_mm"] = drop
        for st in model["storeys"]:
            st["ceiling_mm"] = heights.get(st["name"])
        s.settings = {**(s.settings or {}), "drop_mm": drop}
    res = _generate(s, model, heights)
    s.hangers = res["hangers"]
    s.approvals = {}
    _log(s, user, "omräknad", n=len(res["hangers"]))
    _touch(s)
    db.commit()
    return _out(s)


def _next_rev(r: str) -> str:
    return chr(ord(r[-1]) + 1) if r and r[-1].isalpha() and r[-1] not in "Zz" else (r or "A") + "1"


@router.post("/api/hanger-sets/{set_id}/revise")
async def revise(set_id: str, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """En ny revision av modellen. Hängare vars rör inte ändrats behåller status och historik; de berörda står i
    jämförelsen, och de som redan är producerade, packade, levererade eller monterade är kritiska."""
    s = _set(db, user, set_id, "projektadmin")
    data = await file.read()
    model = _read_ifc(file, data)
    old_h = s.hangers or []
    d = HG.diff((s.pipes or {}).get("pipes") or [], model["pipes"], old_h)
    s.revision = _next_rev(s.revision)
    storage.put(f"prefab/{s.id}/{s.revision}.ifc", io.BytesIO(data))
    res = _generate(s, model, (s.settings or {}).get("manual_heights") or {})
    touched = {p for a in d["affected"] for p in a["pipes"]} | set(d["added"])
    old_by_key = {(tuple(sorted(p["id"] for p in h["pipes"])), round(h["station_mm"] / 50)): h for h in old_h}
    for h in res["hangers"]:
        key = (tuple(sorted(p["id"] for p in h["pipes"])), round(h["station_mm"] / 50))
        o = old_by_key.get(key)
        if o and not touched & set(key[0]):
            h.update(status=o.get("status"), history=o.get("history") or [], approved=o.get("approved") or {},
                     id=o["id"], pack=o.get("pack") or h.get("pack"))
            h["carried_from"] = o["id"]
    s.hangers = res["hangers"]
    s.approvals = {}
    s.settings = {**s.settings, "diff": {**d, "from_revision": _prev(s.revision), "to_revision": s.revision}}
    _log(s, user, "ny revision", revision=s.revision, critical=d["critical"], affected=len(d["affected"]))
    _touch(s)
    db.commit()
    return _out(s)


def _prev(r: str) -> str:
    return chr(ord(r[-1]) - 1) if r and r[-1].isalpha() and r[-1] not in "Aa" else r


# ---------------------------------------------------------------- en hängare

class HangerPatch(BaseModel):
    status: str | None = None
    deviation: str | None = None          # ej möjlig | avvikelse | omarbete | paus | materialbrist
    comment: str | None = None
    position: dict[str, float] | None = None
    rod_length_mm: float | None = None
    takjarn_length_mm: float | None = None
    clear_flags: bool = False


def _find(s: HangerSet, hid: str) -> dict[str, Any]:
    for h in s.hangers or []:
        if h["id"] == hid:
            return h
    raise HTTPException(404, "Hängaren finns inte")


@router.get("/api/hanger-sets/{set_id}/hangers/{hid}")
def get_hanger(set_id: str, hid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id)
    hs = s.hangers or []
    h = _find(s, hid)
    i = hs.index(h)
    nxt = next((x["id"] for x in hs[i + 1:] if x.get("status") not in ("monterad",)), None)
    return {"set": _out(s, full=False), "hanger": h, "next": nxt, "prev": hs[i - 1]["id"] if i else None,
            "index": i + 1, "of": len(hs), "nearby": _nearby(s, h), "my_roles": sorted(_roles(s, db, user) or [])}


def _nearby(s: HangerSet, h: dict[str, Any], r: float = 5000.0) -> dict[str, Any]:
    """Ritningsutsnittet runt hängaren: rören och hängarna på samma våning inom några meter, och referenslinjerna."""
    x, y = h["position"]["x"], h["position"]["y"]
    inside = lambda px, py: abs(px - x) <= r and abs(py - y) <= r
    pipes = []
    for p in (s.pipes or {}).get("pipes") or []:
        if p.get("storey") != h.get("storey"):
            continue
        (x1, y1), (x2, y2) = p["start"][:2], p["end"][:2]
        # med om någon del av röret ligger i rutan (ändpunkt inne, eller röret korsar rutan)
        if inside(x1, y1) or inside(x2, y2) or (min(x1, x2) <= x + r and max(x1, x2) >= x - r
                                                and min(y1, y2) <= y + r and max(y1, y2) >= y - r):
            pipes.append({"id": p["id"], "start": [x1, y1], "end": [x2, y2], "dn": p.get("dn"), "system": p.get("system")})
    hangers = [{"id": o["id"], "x": o["position"]["x"], "y": o["position"]["y"], "status": o.get("status")}
               for o in s.hangers or [] if o.get("storey") == h.get("storey") and inside(o["position"]["x"], o["position"]["y"])]
    return {"box": [x - r, y - r, x + r, y + r], "pipes": pipes[:300], "hangers": hangers[:200],
            "references": [l for l in (s.settings or {}).get("references") or []
                           if not l.get("storey") or l["storey"] == h.get("storey")]}


class PackingIn(BaseModel):
    max_per_kolli: int | None = None
    max_kg_per_kolli: float | None = None
    max_volume_l_per_kolli: float | None = None
    by: str = "montage"
    etapper: dict[str, str] = {}             # "Plan 2" eller "Plan 2|stråk 3" -> "Etapp 1"


@router.post("/api/hanger-sets/{set_id}/packing")
def set_packing(set_id: str, body: PackingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Packningen: högst antal, vikt och volym per kolli, ordningen (montage eller ID) och leveransetapp per våning
    eller per våning och stråk. Kollin och packsekvenser räknas om; det som redan är packat behåller sin plats."""
    s = _set(db, user, set_id, ("projektadmin", "lager"))
    if body.by not in ("montage", "id"):
        raise HTTPException(422, "Ordningen är montage eller id")
    s.settings = {**(s.settings or {}), "packing": body.model_dump()}
    hs = s.hangers or []
    fixed = {h["id"]: h.get("pack") for h in hs if h.get("status") in ("packad", "levererad", "monterad")}
    kollin = _pack(s, hs)
    for h in hs:
        if h["id"] in fixed and fixed[h["id"]]:
            h["pack"] = fixed[h["id"]]
    _log(s, user, "packning", kollin=len(kollin))
    _touch(s)
    db.commit()
    return {**_out(s), "kollin": kollin}


class RefsIn(BaseModel):
    references: list[dict[str, Any]]


@router.post("/api/hanger-sets/{set_id}/references")
def set_references(set_id: str, body: RefsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Väggar och gridlinjer som referensmåtten mäts från: [{"name": "Grid 3", "axis": "x", "value": 12000,
    "storey": "Plan 2" (valfritt)}]. Varje hängares referensmått räknas om."""
    s = _set(db, user, set_id, ("projektadmin", "granskare"))
    refs = []
    for r in body.references:
        if r.get("axis") not in ("x", "y"):
            raise HTTPException(422, "En referenslinje har axeln x (linje i y-led) eller y (linje i x-led)")
        try:
            v = float(r.get("value"))
        except (TypeError, ValueError):
            raise HTTPException(422, "En referenslinje behöver ett läge i mm")
        refs.append({"name": str(r.get("name") or "")[:40], "axis": r["axis"], "value": v,
                     **({"storey": r["storey"]} if r.get("storey") else {})})
    s.settings = {**(s.settings or {}), "references": refs}
    HG.apply_references(s.hangers or [], refs)
    _log(s, user, "referenslinjer", n=len(refs))
    _touch(s)
    db.commit()
    return _out(s)


@router.patch("/api/hanger-sets/{set_id}/hangers/{hid}")
def patch_hanger(set_id: str, hid: str, body: HangerPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id)
    h = _find(s, hid)
    ap = s.approvals or {}
    ev: dict[str, Any] = {"at": _now(), "user": user.email}
    # vem får göra vad: granskaren ändrar geometrin, produktionen producerar, lagret packar och levererar,
    # montören kvitterar montaget; en kommentar får alla som ser uppsättningen skriva
    if body.position or body.rod_length_mm is not None or body.takjarn_length_mm is not None or body.clear_flags:
        _need(s, db, user, "granskare")
    if body.status:
        _need(s, db, user, *{"föreslagen": ("granskare",), "granskad": ("granskare",), "godkänd": ("granskare",),
                             "producerad": ("produktion",), "packad": ("lager",), "levererad": ("lager",),
                             "monterad": ("montor",)}.get(body.status, ("granskare",)))
    if body.deviation:
        _need(s, db, user, *{"paus": ("produktion",), "materialbrist": ("produktion", "lager"),
                             "ej möjlig": ("montor",), "avvikelse": ("produktion", "lager", "montor", "granskare"),
                             "omarbete": ("produktion", "montor", "granskare")}.get(body.deviation, ("granskare",)))
    if body.status:
        if body.status not in HG.STATUSES:
            raise HTTPException(422, f"Status är en av: {', '.join(HG.STATUSES)}")
        if body.status in ("producerad", "packad", "levererad") and "produktion" not in ap:
            raise HTTPException(409, "Uppsättningen är inte frisläppt för produktion")
        if body.status == "godkänd" and "konstruktion" not in ap and h.get("status") != "godkänd":
            pass                                         # en enskild hängare kan godkännas vid granskning
        ev.update(action="status", **{"from": h.get("status"), "to": body.status})
        h["status"] = body.status
    if body.deviation:
        if body.deviation not in HG.DEVIATIONS:
            raise HTTPException(422, f"Avvikelse är en av: {', '.join(HG.DEVIATIONS)}")
        h["deviation"] = body.deviation
        ev.update(action=ev.get("action", "avvikelse"), deviation=body.deviation)
    elif body.status:
        h.pop("deviation", None)
    if body.position:
        if h.get("status") in ("producerad", "packad", "levererad", "monterad"):
            raise HTTPException(409, "Hängaren är redan producerad - flytta den i en ny revision")
        old = dict(h["position"])
        h["position"] = {**h["position"], **{k: round(float(v)) for k, v in body.position.items() if k in ("x", "y", "z")}}
        ev.update(action="flyttad", **{"from": old, "to": h["position"]})
        h["status"] = "föreslagen" if h.get("status") == "godkänd" else h.get("status")
    if body.rod_length_mm is not None:
        for r in h.get("rods") or []:
            r["length_mm"] = int(body.rod_length_mm)
        ev.update(action="pendel ändrad", rod_length_mm=int(body.rod_length_mm))
        h["flags"] = [f for f in h.get("flags") or [] if "takhöjd" not in f]
        h["height_source"] = "manuell (granskning)"
    if body.takjarn_length_mm is not None and h.get("takjarn"):
        L = int(body.takjarn_length_mm)
        h["takjarn"]["length_mm"] = L
        h["takjarn"]["rod_holes_mm"] = [25, L - 25]
        if len(h.get("rods") or []) == 2:
            h["rods"][1]["at_mm"] = L - 25
        ev.update(action="takjärn ändrat", takjarn_length_mm=L)
    if body.clear_flags:
        ev.update(action=ev.get("action", "flaggor kvitterade"), cleared=h.get("flags"))
        h["flags_cleared"] = (h.get("flags_cleared") or []) + (h.get("flags") or [])
        h["flags"] = []
    if body.comment:
        ev["comment"] = body.comment[:2000]
        ev.setdefault("action", "kommentar")
    h["bom"] = HG.bom(h, rules())
    h["history"] = (h.get("history") or []) + [ev]
    _log(s, user, ev.get("action", "ändrad"), hid, **{k: v for k, v in ev.items() if k not in ("at", "user", "action")})
    _touch(s)
    db.commit()
    return get_hanger(set_id, hid, user, db)


@router.post("/api/hanger-sets/{set_id}/hangers/{hid}/photo")
async def hanger_photo(set_id: str, hid: str, file: UploadFile = File(...), comment: str = Form(""),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id)
    h = _find(s, hid)
    data = await file.read()
    if len(data) > 15_000_000:
        raise HTTPException(413, "Bilden är för stor (högst 15 MB)")
    ext = os.path.splitext(file.filename or "")[1].lower()[:5] or ".jpg"
    key = f"prefab/{s.id}/photos/{hid}-{len(h.get('photos') or []) + 1}{ext}"
    storage.put(key, io.BytesIO(data))
    h["photos"] = (h.get("photos") or []) + [{"key": key, "at": _now(), "user": user.email, "comment": comment[:500]}]
    h["history"] = (h.get("history") or []) + [{"at": _now(), "user": user.email, "action": "foto", "comment": comment[:500]}]
    _log(s, user, "foto", hid)
    _touch(s)
    db.commit()
    return {"ok": True, "n": len(h["photos"])}


@router.get("/api/hanger-sets/{set_id}/hangers/{hid}/photo/{n}")
def get_photo(set_id: str, hid: str, n: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id)
    h = _find(s, hid)
    ph = (h.get("photos") or [])
    if not 1 <= n <= len(ph):
        raise HTTPException(404, "Fotot finns inte")
    with storage.open(ph[n - 1]["key"]) as fh:
        return Response(fh.read(), media_type="image/jpeg")


class NewHanger(BaseModel):
    storey: str
    x: float
    y: float
    pipe_ids: list[str]
    comment: str = ""


@router.post("/api/hanger-sets/{set_id}/hangers")
def add_hanger(set_id: str, body: NewHanger, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """En hängare för hand: rören den bär och var. Mått räknas ur modellen och reglerna som för de andra."""
    s = _set(db, user, set_id, "granskare")
    pipes = {p["id"]: p for p in (s.pipes or {}).get("pipes") or []}
    sel = [pipes[i] for i in body.pipe_ids if i in pipes]
    if not sel:
        raise HTTPException(422, "Välj minst ett rör som hängaren bär")
    import numpy as np
    # en tillfällig modell med korta bitar av rören vid punkten: samma regler ger höjd, pendel och takjärn
    cands = []
    for p in sel:
        a, b = np.array(p["start"], float), np.array(p["end"], float)
        d = b - a
        u = d / (np.linalg.norm(d) or 1)
        lam = float(np.clip(np.dot(np.array([body.x, body.y]) - a[:2], d[:2]) / (np.dot(d[:2], d[:2]) or 1), 0, 1))
        c = a + d * lam
        cands.append({**p, "start": list(c - u * 400), "end": list(c + u * 400)})
    r = rules()
    r1 = HR.merged({**r, "placement": {**r["placement"], "end_max": 400, "min_pipe_length": 100, "run_max_width": 5000}})
    res = HG.generate({"pipes": cands, "storeys": (s.pipes or {}).get("storeys") or [], "fittings": []}, r1,
                      (s.settings or {}).get("manual_heights") or {}, project=s.name, revision=s.revision)
    if not res["hangers"]:
        raise HTTPException(422, "Rören går inte att hänga här (stigare eller för korta)")
    h = res["hangers"][0]
    code = HG.storey_code(h["storey"], 0)
    n = 1 + max([int(x["id"].split("-")[-1]) for x in s.hangers or [] if x["id"].startswith(code + "-") and x["id"].split("-")[-1].isdigit()] or [0])
    h.update(id=f"{code}-{n:03d}", manual=True, placed_because="tillagd för hand",
             history=[{"at": _now(), "user": user.email, "action": "tillagd", "comment": body.comment}])
    h["position"]["x"], h["position"]["y"] = round(body.x), round(body.y)
    s.hangers = (s.hangers or []) + [h]
    s.approvals = {k: v for k, v in (s.approvals or {}).items() if k == "offert"}
    _log(s, user, "tillagd", h["id"])
    _touch(s)
    db.commit()
    return h


@router.delete("/api/hanger-sets/{set_id}/hangers/{hid}")
def delete_hanger(set_id: str, hid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id, "granskare")
    h = _find(s, hid)
    if h.get("status") in ("producerad", "packad", "levererad", "monterad"):
        raise HTTPException(409, "Hängaren är redan producerad - den tas bort i en ny revision")
    s.hangers = [x for x in s.hangers if x["id"] != hid]
    _log(s, user, "borttagen", hid)
    _touch(s)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- godkännanden

@router.post("/api/hanger-sets/{set_id}/approve")
def approve(set_id: str, body: dict[str, Any], user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Tre godkännanden var för sig: offert, konstruktion och produktionsfrisläppning."""
    s = _set(db, user, set_id)
    kind = body.get("kind")
    if kind not in APPROVALS:
        raise HTTPException(422, "Godkännandet är offert, konstruktion eller produktion")
    _need(s, db, user, *{"offert": ("kalkyl", "projektadmin"), "konstruktion": ("granskare",),
                         "produktion": ("projektadmin",)}[kind])
    ap = dict(s.approvals or {})
    hs = s.hangers or []
    if kind == "konstruktion":
        open_flags = [h["id"] for h in hs if h.get("flags") and h.get("status") == "föreslagen"]
        if open_flags:
            raise HTTPException(409, f"{len(open_flags)} flaggade hängare är inte granskade: {', '.join(open_flags[:10])}")
        for h in hs:
            if h.get("status") in ("föreslagen", "granskad"):
                h["status"] = "godkänd"
                h["history"] = (h.get("history") or []) + [{"at": _now(), "user": user.email, "action": "konstruktion godkänd"}]
    if kind == "produktion":
        if "konstruktion" not in ap:
            raise HTTPException(409, "Konstruktionen är inte godkänd")
        r = rules()
        if not (r.get("verified") and (s.settings or {}).get("rules_verified")):
            raise HTTPException(409, "Reglerna är inte verifierade av en tekniskt ansvarig - räkna om med verifierade "
                                     "regler innan produktionen frisläpps")
    ap[kind] = {"by": user.email, "at": _now(), "revision": s.revision}
    s.approvals = ap
    _log(s, user, f"godkänd: {kind}")
    _touch(s)
    db.commit()
    return _out(s)


# ---------------------------------------------------------------- ut

def _base_url(request: Request) -> str:
    env = os.environ.get("VVS_PUBLIC_URL")
    if env:
        return env.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def montage_url(base: str, set_id: str, hid: str) -> str:
    return f"{base}/montage/{set_id}/{hid}"


def _xlsx(s: HangerSet) -> bytes:
    import openpyxl
    from openpyxl.styles import Font
    hs = s.hangers or []
    r = rules()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hängare"
    ws.append([f"SmartHangers {s.name} - revision {s.revision}", "", "", f"Regler v{(s.settings or {}).get('rules_version')}"
               + ("" if (s.settings or {}).get("rules_verified") else " EXEMPEL - EJ VERIFIERADE")])
    ws.append(["ID", "Våning", "Zon", "Typ", "X", "Y", "Tak Z", "Höjdkälla", "Pendel mm", "Gängstång", "Takjärn mm",
               "Rör", "Last kN", "Status", "Kolli", "Packsekvens", "Flaggor"])
    for h in hs:
        ws.append([h["id"], h["storey"], h.get("zone"), h["kind"], h["position"]["x"], h["position"]["y"], h["position"].get("z"),
                   h.get("height_source"), (h["rods"][0]["length_mm"] if h.get("rods") else None),
                   (h["rods"][0]["size"] if h.get("rods") else None), (h.get("takjarn") or {}).get("length_mm"),
                   ", ".join(f"{p.get('material')} {p.get('dn') or p.get('od')}" for p in h["pipes"]), h.get("load_kn"),
                   h.get("status"), (h.get("pack") or {}).get("kolli"), (h.get("pack") or {}).get("seq"), "; ".join(h.get("flags") or [])])
    for c in ws[2]:
        c.font = Font(bold=True)
    w2 = wb.create_sheet("Material per hängare")
    w2.append(["Hängare", "Del", "Benämning", "Antal", "Längd mm"])
    for h in hs:
        for b in h.get("bom") or []:
            w2.append([h["id"], b["part"], b["text"], b["qty"], b.get("length_mm")])
    w3 = wb.create_sheet("Material projekt")
    w3.append(["Benämning", "Längd mm", "Antal", "I antal hängare"])
    for b in HG.bom_total(hs):
        w3.append([b["text"], b["length_mm"], b["qty"], b["hangers"]])
    w4 = wb.create_sheet("Kapplan")
    w4.append(["Del", "Lagerlängd mm", "Längd nr", "Kap (mm: hängare)", "Rest mm"])
    cp = HG.cut_plan(hs, r)
    for part, items in cp.items():
        for it in items:
            for i, b in enumerate(it["bars"], 1):
                w4.append([it["text"], it["stock_mm"], i, ", ".join(f"{c['mm']}: {c['hanger']}" for c in b["cuts"]), b["left"]])
            w4.append([f"{it['text']}: {it['n_bars']} längder, {it['pieces']} bitar, spill {it['waste_pct']} %"])
    w5 = wb.create_sheet("Packlista")
    w5.append(["Kolli", "Etapp", "Våning", "Zon", "Vikt kg", "Volym l", "Hängare (i den ordning de tas ur)"])
    kollin = _pack(s, hs, r)
    for k in kollin:
        w5.append([k["no"], k.get("etapp") or "", k["storey"], k.get("zone"), k["kg"], k.get("l"), ", ".join(k["hangers"])])
    w6 = wb.create_sheet("Material per kolli")
    w6.append(["Kolli", "Benämning", "Längd mm", "Antal"])
    by_id = {h["id"]: h for h in hs}
    for k in kollin:
        for b in HG.bom_total([by_id[i] for i in k["hangers"] if i in by_id]):
            w6.append([k["no"], b["text"], b["length_mm"], b["qty"]])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _labels_pdf(s: HangerSet, base: str, only: list[str] | None = None) -> bytes:
    """En etikett per hängare, 100 x 50 mm: ID stort, projekt, våning/zon, revision, kolli och packsekvens, och en
    QR-kod som öppnar hängaren i montageguiden."""
    import pymupdf
    mm = 72 / 25.4
    doc = pymupdf.open()
    for h in s.hangers or []:
        if only and h["id"] not in only:
            continue
        page = doc.new_page(width=100 * mm, height=50 * mm)
        m = HQ.matrix(montage_url(base, s.id, h["id"]))
        n = len(m)
        size = 40 * mm
        cell = size / n
        x0, y0 = 57 * mm, 5 * mm
        for r_, row in enumerate(m):
            for c_, v in enumerate(row):
                if v:
                    page.draw_rect(pymupdf.Rect(x0 + c_ * cell, y0 + r_ * cell, x0 + (c_ + 1) * cell, y0 + (r_ + 1) * cell),
                                   color=None, fill=(0, 0, 0), width=0)
        page.insert_text((4 * mm, 14 * mm), h["id"], fontsize=24, fontname="hebo")
        pk = h.get("pack") or {}
        lines = [s.name[:34], f"{h['storey']} · {h.get('zone') or ''}", f"Revision {h.get('revision') or s.revision} · {h['kind']}",
                 f"Kolli {pk.get('kolli', '-')} · nr {pk.get('seq', '-')}" + (f" · {pk['etapp']}" if pk.get("etapp") else ""),
                 f"Pendel {(h.get('rods') or [{}])[0].get('length_mm') or '-'} mm" + (f" · takjärn {h['takjarn']['length_mm']} mm" if h.get("takjarn") else "")]
        for i, t in enumerate(lines):
            page.insert_text((4 * mm, (21 + i * 5.5) * mm), t, fontsize=8, fontname="helv")
    if doc.page_count == 0:
        doc.new_page(width=100 * mm, height=50 * mm)
    return doc.tobytes()


@router.get("/api/hanger-sets/{set_id}/export.{fmt}")
def export(set_id: str, fmt: str, request: Request, ids: str = "", user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    s = _set(db, user, set_id)
    fname = f"smarthangers-{s.name or 'projekt'}-rev{s.revision}".replace(" ", "_")
    if fmt == "xlsx":
        return Response(_xlsx(s), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})
    if fmt == "pdf":
        only = [x for x in ids.split(",") if x] or None
        return Response(_labels_pdf(s, _base_url(request), only), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{fname}-etiketter.pdf"'})
    if fmt == "ifc":
        return Response(HX.export(s.hangers or [], s.name, s.revision), media_type="application/x-step",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.ifc"'})
    raise HTTPException(400, "Format: xlsx (material, kapplan, packlista), pdf (etiketter) eller ifc")


@router.get("/api/hanger-sets/{set_id}/qr/{hid}.svg")
def qr_svg(set_id: str, hid: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id)
    _find(s, hid)
    return Response(HQ.svg(montage_url(_base_url(request), s.id, hid)), media_type="image/svg+xml")


@router.post("/api/hanger-sets/{set_id}/calc")
def calc(set_id: str, body: dict[str, Any], user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lönsamhetskalkylen med uppsättningens antal som utgångspunkt; antagandena sparas på uppsättningen."""
    s = _set(db, user, set_id, ("kalkyl", "projektadmin"))
    inp = {k: float(v) for k, v in (body or {}).items() if k in HC.EXAMPLE and k != "label" and v not in (None, "")}
    inp.setdefault("antal", float(len(s.hangers or [])) or HC.EXAMPLE["antal"])
    res = HC.compute(inp)
    s.settings = {**(s.settings or {}), "calc": inp}
    _touch(s)
    db.commit()
    return res


@router.get("/api/hanger-sets/{set_id}/calc")
def get_calc(set_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _set(db, user, set_id)
    inp = dict((s.settings or {}).get("calc") or {})
    inp.setdefault("antal", float(len(s.hangers or [])) or HC.EXAMPLE["antal"])
    return HC.compute(inp)
