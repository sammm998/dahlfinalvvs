"""ABT 06 fas 3: nyckeltalen och schablonraderna.

Ett nyckeltal är företagets eget: per enhet ("ett WC ger ...") eller per m² ("ett badrum ger ... per m²"), med vad
det ger - rör per system och dimension, artiklar ur materialboken, timmar. Inget värde här är en branschsanning.
Biblioteket är tomt tills någon lägger in sina egna, och ett nyckeltal används inte i ett projekt förrän någon har
bekräftat det (docs/abt06-plan.md, fas 3).

En SCHABLON-rad räknas fram varje gång ur projektets räknade enheter och ytor och de valda nyckeltalen. Den lagras
aldrig, så att varje rad kan visa var den kommer ifrån: "12 st VK × 6 m = 72 m", och riskpåslaget ovanpå. Det som
lagras är bara det kalkylatorn bestämt: vilka nyckeltal projektet använder och vilket påslag som gäller.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth import current_user
from .db import KeyFigure, Project, ProjectEstimate, User, get_db

router = APIRouter(prefix="/api", tags=["abt06"])

BASES = ("per_enhet", "per_m2")
MEASURES = {"LENGTH": "m", "COUNT": "st", "AREA": "m²", "VOLUME": "m³"}
STATES = ("utkast", "bekraftad")
ROW_KEY = re.compile(r"^[0-9a-f]{32}:\d{1,3}$")      # a key figure's id and the row's place in it


class Output(BaseModel):
    """What one unit, or one square metre, gives: a quantity of something, with an article if there is one."""
    system: str = Field("", max_length=80)               # KV, VV, S, "Tvättställsblandare" ...
    measure: str = "LENGTH"
    value: float = Field(0.0, ge=0)
    unit: str | None = None
    article: dict | None = None                          # {a, n, e} from the material book


class KeyFigureIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    basis: str = "per_enhet"
    unit_code: str = Field("", max_length=24)
    room_type: str = Field("", max_length=64)
    building_type: str = Field("", max_length=64)
    outputs: list[Output] = Field(default_factory=list, max_length=60)
    hours: float | None = Field(None, ge=0)
    source: str = Field("", max_length=2000)


class KeyFigurePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    basis: str | None = None
    unit_code: str | None = Field(None, max_length=24)
    room_type: str | None = Field(None, max_length=64)
    building_type: str | None = Field(None, max_length=64)
    outputs: list[Output] | None = Field(None, max_length=60)
    hours: float | None = Field(None, ge=0)
    source: str | None = Field(None, max_length=2000)
    status: str | None = None


def _mine(db: Session, user: User):
    """The library a person works in: the company's, or her own when she has no company."""
    q = db.query(KeyFigure)
    return q.filter(KeyFigure.account_id == user.account_id) if user.account_id else \
        q.filter(KeyFigure.account_id.is_(None), KeyFigure.user_id == user.id)


def _key_figure(db: Session, user: User, kf_id: str) -> KeyFigure:
    kf = _mine(db, user).filter(KeyFigure.id == kf_id).first()
    if kf is None:
        raise HTTPException(404, "Nyckeltalet finns inte")
    return kf


def _outputs(outputs: list[Output]) -> list[dict]:
    out = []
    for o in outputs:
        measure = o.measure.upper()
        if measure not in MEASURES:
            raise HTTPException(422, f"Okänt mått: {o.measure}")
        art = None
        if o.article and o.article.get("a"):
            art = {k: str(o.article.get(k) or "")[:200] for k in ("a", "n", "e")}
        out.append({"system": o.system.strip(), "measure": measure, "value": float(o.value),
                    "unit": (o.unit or MEASURES[measure]).strip()[:8], "article": art})
    return out


def _check(basis: str, unit_code: str, room_type: str) -> None:
    if basis not in BASES:
        raise HTTPException(422, f"Okänd grund: {basis}")
    if basis == "per_enhet" and not unit_code.strip():
        raise HTTPException(422, "Ett nyckeltal per enhet behöver en enhet: koden eller namnet den räknas på")


def _out(kf: KeyFigure) -> dict[str, Any]:
    return {"id": kf.id, "name": kf.name, "basis": kf.basis, "unit_code": kf.unit_code, "room_type": kf.room_type,
            "building_type": kf.building_type, "outputs": kf.outputs or [], "hours": kf.hours, "status": kf.status,
            "source": kf.source, "created_at": kf.created_at.isoformat() if kf.created_at else None}


@router.get("/key-figures")
def list_key_figures(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = _mine(db, user).order_by(KeyFigure.name).all()
    return {"key_figures": [_out(k) for k in rows]}


@router.post("/key-figures")
def create_key_figure(body: KeyFigureIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A new key figure, as a draft: it is used in no project until someone confirms it."""
    _check(body.basis, body.unit_code, body.room_type)
    kf = KeyFigure(account_id=user.account_id, user_id=user.id, name=body.name.strip(), basis=body.basis,
                   unit_code=body.unit_code.strip(), room_type=body.room_type.strip(),
                   building_type=body.building_type.strip(), outputs=_outputs(body.outputs), hours=body.hours,
                   status="utkast", source=body.source.strip())
    db.add(kf)
    db.commit()
    return _out(kf)


@router.patch("/key-figures/{kf_id}")
def update_key_figure(kf_id: str, body: KeyFigurePatch, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    """Change a key figure, or confirm it. A confirmed one that is changed is a draft again: what someone confirmed
    is what is used."""
    kf = _key_figure(db, user, kf_id)
    changed = False
    for field in ("name", "basis", "unit_code", "room_type", "building_type", "source"):
        v = getattr(body, field)
        if v is not None:
            setattr(kf, field, v.strip())
            changed = True
    if body.outputs is not None:
        kf.outputs = _outputs(body.outputs)
        changed = True
    if "hours" in body.model_fields_set:
        kf.hours = body.hours
        changed = True
    _check(kf.basis, kf.unit_code, kf.room_type)
    if body.status is not None:
        if body.status not in STATES:
            raise HTTPException(422, f"Okänd status: {body.status}")
        kf.status = body.status
    elif changed:
        kf.status = "utkast"
    db.commit()
    return _out(kf)


@router.delete("/key-figures/{kf_id}")
def delete_key_figure(kf_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kf = _key_figure(db, user, kf_id)
    for est in db.query(ProjectEstimate).all():
        if kf.id in (est.key_figures or []):
            est.key_figures = [k for k in est.key_figures if k != kf.id]
    db.delete(kf)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------------------------------------------------
# Schablonraderna: räknade enheter och ytor gånger de valda nyckeltalen, med riskpåslag
# ------------------------------------------------------------------------------------------------------------

def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip().casefold() == b.strip().casefold()


def _bases(db: Session, project: Project) -> dict[str, Any]:
    """What the project's key figures can multiply: its units by code and name, its named symbols, its apartment
    types, and its rooms with their areas - all counted on the pages that count."""
    from .abt import project_rooms, project_symbols, project_units
    units = project_units(db, project)["units"]
    symbols = [s for s in project_symbols(db, project)["symbols"] if s["counted"]]
    rooms = project_rooms(db, project)
    return {"units": units, "symbols": symbols, "apartments": rooms["register"]["apartments"],
            "rooms": [r for r in rooms["rooms"] if r["counted"] and r["kind"] == "rum"]}


def _basis_of(kf: dict, bases: dict) -> tuple[float, str, list[str]]:
    """How many of what the key figure is per, and where that number comes from."""
    if kf["basis"] == "per_m2":
        rooms = [r for r in bases["rooms"] if not kf["room_type"] or _same(r["name"], kf["room_type"])
                 or (r["name"] or "").casefold().startswith(kf["room_type"].strip().casefold() + " ")]
        area = round(sum(r["area_m2"] or 0.0 for r in rooms), 2)
        what = kf["room_type"] or "alla rum"
        return area, "m²", [f"{len(rooms)} rum ({what}): {area:g} m²"]
    code = kf["unit_code"]
    qty, why = 0.0, []
    for u in bases["units"]:
        if _same(u["code"], code) or _same(u.get("name"), code):
            qty += u["count"]
            why.append(f"{u['count']} st {u['code']} (koder)")
    coded = qty > 0
    for s in bases["symbols"]:
        if _same(s["name"], code):
            # a copy drawn where its code is written is the unit the code already counted
            twice = (s.get("beside_code") or {}).get("count", 0) if coded else 0
            qty += s["count"] - twice
            why.append(f"{s['count'] - twice} st {s['name']} (symboler)" +
                       (f", {twice} till vid en kod räknas inte två gånger" if twice else ""))
    for a in bases["apartments"]:
        if _same(a["type"], code):
            qty += a["count"]
            why.append(f"{a['count']} lägenheter {a['type']}")
    return qty, "st", why or [f"inga {code} räknade"]


_ARTICLES: dict[int, dict[str, dict]] = {}


def _price(article: dict | None) -> float | None:
    """The article's net price in the material book, as the calculation reads it. A price of nothing is no price:
    the book holds a few thousand articles at 0 kr, and a row costed at 0 kr would say it costs nothing."""
    if not article:
        return None
    from .main import _material_book
    book = _material_book()
    if id(book) not in _ARTICLES:
        _ARTICLES.clear()
        _ARTICLES[id(book)] = {r.get("a"): r for r in book["rows"]}
    row = _ARTICLES[id(book)].get(article.get("a"))
    if row is None or not row.get("p"):
        return None
    return round(float(row["p"]) * (1 - float(row.get("r") or 0.0)), 2)


def _estimate(db: Session, project_id: str) -> ProjectEstimate:
    est = db.query(ProjectEstimate).filter(ProjectEstimate.project_id == project_id).first()
    if est is None:
        est = ProjectEstimate(project_id=project_id, unit_names={}, key_figures=[], line_risk={}, risk_pct=0.0)
        db.add(est)
        db.flush()
    return est


def project_schablon(db: Session, user: User, project: Project) -> dict[str, Any]:
    est = db.query(ProjectEstimate).filter(ProjectEstimate.project_id == project.id).first()
    chosen = list((est.key_figures if est else None) or [])
    risk = float((est.risk_pct if est else 0.0) or 0.0)
    line_risk = dict((est.line_risk if est else None) or {})
    library = {k.id: k for k in _mine(db, user).filter(KeyFigure.id.in_(chosen or [""])).all()}
    bases = _bases(db, project)
    rows: list[dict] = []
    for kf_id in chosen:
        kf = library.get(kf_id)
        if kf is None or kf.status != "bekraftad":
            continue
        k = _out(kf)
        qty, per, why = _basis_of(k, bases)
        lines = [dict(o) for o in k["outputs"]]
        if kf.hours:
            lines.append({"system": "Arbete", "measure": "TIME", "value": float(kf.hours), "unit": "h", "article": None})
        for i, o in enumerate(lines):
            key = f"{kf.id}:{i}"
            r = float(line_risk.get(key, risk))
            amount = round(o["value"] * qty, 3)
            with_risk = round(amount * (1 + r / 100), 3)
            price = _price(o.get("article"))
            rows.append({"key": key, "source_type": "SCHABLON",
                         "key_figure": {"id": kf.id, "name": kf.name, "source": kf.source, "basis": kf.basis},
                         "system": o["system"], "measure": o["measure"], "unit": o["unit"], "article": o.get("article"),
                         "per": o["value"], "basis_qty": qty, "basis_unit": per, "basis_from": why,
                         "quantity": amount, "risk_pct": r, "own_risk": key in line_risk,
                         "quantity_with_risk": with_risk, "price": price,
                         "cost": round(with_risk * price, 2) if price is not None else None,
                         "provenance": f"{qty:g} {per} × {o['value']:g} {o['unit']} = {amount:g} {o['unit']}"})
    return {"project_id": project.id, "risk_pct": risk, "key_figures": chosen, "rows": rows,
            "totals": {"rows": len(rows), "cost": round(sum(r["cost"] or 0.0 for r in rows), 2),
                       "hours": round(sum(r["quantity_with_risk"] for r in rows if r["measure"] == "TIME"), 2)},
            "bases": {"units": [{"code": u["code"], "name": u.get("name"), "count": u["count"]} for u in bases["units"]],
                      "symbols": [{"name": s["name"], "count": s["count"]} for s in bases["symbols"]],
                      "apartments": bases["apartments"],
                      "room_names": sorted({r["name"] for r in bases["rooms"] if r["name"]})}}


def _project(db: Session, user: User, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Projektet finns inte")
    return p


@router.get("/projects/{project_id}/schablon")
def get_schablon(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return project_schablon(db, user, _project(db, user, project_id))


class EstimateIn(BaseModel):
    risk_pct: float | None = Field(None, ge=-100, le=1000)
    key_figures: list[str] | None = Field(None, max_length=500)
    line_risk: dict[str, float | None] | None = None      # a row's own mark-up; None takes it back


@router.put("/projects/{project_id}/estimate")
def put_estimate(project_id: str, body: EstimateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What the person pricing the project decides: which key figures it uses, and the mark-up for risk - for the
    project, and for a row of its own. Only a confirmed key figure from her own library can be used."""
    p = _project(db, user, project_id)
    est = _estimate(db, p.id)
    if body.risk_pct is not None:
        est.risk_pct = float(body.risk_pct)
    if body.key_figures is not None:
        found = {k.id: k for k in _mine(db, user).filter(KeyFigure.id.in_(body.key_figures or [""])).all()}
        for kid in body.key_figures:
            if kid not in found:
                raise HTTPException(404, "Nyckeltalet finns inte")
            if found[kid].status != "bekraftad":
                raise HTTPException(422, f"Nyckeltalet {found[kid].name} är inte bekräftat")
        est.key_figures = list(dict.fromkeys(body.key_figures))
    if body.line_risk is not None:
        lines = dict(est.line_risk or {})
        for k, v in body.line_risk.items():
            if not ROW_KEY.match(k):
                raise HTTPException(422, "Okänd rad")
            if v is None:
                lines.pop(k, None)
            elif -100 <= float(v) <= 1000:
                lines[k] = float(v)
            else:
                raise HTTPException(422, "Påslaget ligger utanför -100 till 1000 %")
        est.line_risk = lines
    db.commit()
    return project_schablon(db, user, p)


@router.get("/projects/{project_id}/schablon.csv")
def export_schablon(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The SCHABLON rows as a list a calculation can take: each with its basis, its key figure and its mark-up."""
    out = project_schablon(db, user, _project(db, user, project_id))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["källtyp", "nyckeltal", "system", "artikel", "benämning", "underlag", "per underlag", "enhet",
                "mängd", "risk_procent", "mängd med risk", "nettopris", "kostnad", "nyckeltalets källa"])
    fmt = lambda v: "" if v is None else f"{v:g}".replace(".", ",")  # noqa: E731
    for r in out["rows"]:
        art = r["article"] or {}
        w.writerow([r["source_type"], r["key_figure"]["name"], r["system"], art.get("a", ""), art.get("n", ""),
                    f"{fmt(r['basis_qty'])} {r['basis_unit']}", fmt(r["per"]), r["unit"], fmt(r["quantity"]),
                    fmt(r["risk_pct"]), fmt(r["quantity_with_risk"]), fmt(r["price"]), fmt(r["cost"]),
                    r["key_figure"]["source"]])
    name = "".join(c for c in out["project_id"] if c.isalnum())[:12]
    return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="schablon-{name}.csv"'})
