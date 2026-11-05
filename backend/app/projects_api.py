"""Projektanalys: hela handlingen läst som en modell.

En enkel analys läser en ritning och svarar med meter. Den här läser alla blad i ett projekt och svarar med vad
handlingen består av: vilka hus, vilka discipliner, vilka versioner, vad som hör ihop och vad som inte gick att
avgöra.

Den återanvänder allt som redan finns - projekten, ritningarna, lagringen, jobbkön - och lägger till två saker:
en klassificering per blad, och en parning av versioner som aldrig hittar på ett före och ett efter.

Läsningen är billig med flit. Att köra mängdningen på trehundra blad tar timmar; att läsa deras namnrutor tar
sekunder. Så fas ett är metadata, och mängderna hämtas från de analyser som redan körts på bladen - projektet
mängdar inte om något det redan mängdat.
"""
from __future__ import annotations

import datetime as dt
import os
from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vvs_engine.handling import Handling, as_report, read_handling

from .auth import current_user
from .db import (AnalysisJob, DocumentOverride, Drawing, Project, ProjectAnalysis, User, get_db)
from .storage import storage

router = APIRouter(prefix="/api/projects", tags=["projektanalys"])

MODES = ("simple", "project")
OVERRIDE_FIELDS = ("building", "discipline", "role", "number", "floor", "part")
ROLES = ("underlag", "fore", "efter", "revision", "relation", "referens", "kravhandling",
         "teknisk_beskrivning", "annat")


def _project(db: Session, user: User, pid: str) -> Project:
    p = db.get(Project, pid)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Okänt projekt")
    return p


class ModeIn(BaseModel):
    mode: str


@router.put("/{project_id}/mode")
def set_mode(project_id: str, body: ModeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Vilken sorts analys projektet använder. Valet sparas på projektet och går att se senare."""
    p = _project(db, user, project_id)
    if body.mode not in MODES:
        raise HTTPException(400, "Okänd analystyp")
    p.analysis_mode = body.mode
    db.commit()
    return {"mode": p.analysis_mode}


@router.get("/{project_id}/mode")
def get_mode(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Vad projektet valt, och om det redan finns arbete gjort under valet.

    Ett projekt utan valt läge är ett av de gamla. De fortsätter fungera precis som förut - det svaret säger
    "simple" utan att skriva något, så ingenting ändras för dem förrän någon väljer.
    """
    p = _project(db, user, project_id)
    n_drawings = db.query(Drawing).filter(Drawing.project_id == p.id).count()
    n_jobs = (db.query(AnalysisJob).join(Drawing, AnalysisJob.drawing_id == Drawing.id)
              .filter(Drawing.project_id == p.id).count())
    last = (db.query(ProjectAnalysis).filter(ProjectAnalysis.project_id == p.id)
            .order_by(ProjectAnalysis.created_at.desc()).first())
    return {"mode": p.analysis_mode or "", "effective": p.analysis_mode or "simple",
            "chosen": bool(p.analysis_mode), "drawings": n_drawings, "readings": n_jobs,
            "analysis": {"id": last.id, "status": last.status, "stage": last.stage,
                         "progress": last.progress, "created_at": last.created_at.isoformat()} if last else None}


def _apply_overrides(docs: list[Handling], by_path: dict[str, dict]) -> None:
    """Vad en människa rättat går före vad läsningen kom fram till, och det syns att den gjorde det."""
    from vvs_engine.handling import Field
    for d in docs:
        for fld, value in (by_path.get(d.path) or {}).items():
            if fld in ("building", "discipline", "number", "floor", "part"):
                setattr(d, fld, Field(value, "rättat av en människa", "rättelse", 1.0))


def run_project_analysis(analysis_id: str) -> None:
    """Läs varje blad och bygg handlingen. Körs på jobbkön, som mängdningen."""
    from .db import SessionLocal
    db = SessionLocal()
    try:
        pa = db.get(ProjectAnalysis, analysis_id)
        if pa is None:
            return
        pa.status, pa.stage, pa.progress = "RUNNING", "LÄSER NAMNRUTOR", 0.0
        db.commit()

        drawings = db.query(Drawing).filter(Drawing.project_id == pa.project_id).all()
        over = defaultdict(dict)
        for o in db.query(DocumentOverride).filter(DocumentOverride.project_id == pa.project_id).all():
            over[o.drawing_id][o.field] = o.value

        docs: list[Handling] = []
        by_drawing: dict[str, str] = {}
        for i, d in enumerate(drawings):
            path = storage.path(d.storage_key)
            h = read_handling(path)
            h.filename = d.filename                      # visa det namn användaren laddade upp, inte lagringens
            by_drawing[h.path] = d.id
            docs.append(h)
            pa.progress = round((i + 1) / max(len(drawings), 1) * 0.8, 3)
            if i % 5 == 0:
                db.commit()

        _apply_overrides(docs, {h.path: over.get(by_drawing[h.path], {}) for h in docs})
        pa.stage, pa.progress = "PARAR VERSIONER", 0.85
        db.commit()

        report = as_report(docs)
        for row in report["documents"]:
            row["drawing_id"] = by_drawing.get(row["path"])
            row.pop("path", None)                        # lagringsvägen hör inte hemma i ett svar
        for group in ("pairs", "unclear"):
            for item in report[group]:
                for k in ("before", "after"):
                    if k in item:
                        item[k]["drawing_id"] = by_drawing.get(item[k].pop("path", None))
                for sub in item.get("docs", []):
                    sub["drawing_id"] = by_drawing.get(sub.pop("path", None))
        for b in report["tree"].values():
            for rows in b.values():
                for row in rows:
                    row["drawing_id"] = by_drawing.get(row.pop("path", None))

        pa.stage, pa.progress = "HÄMTAR MÄNGDER", 0.92
        db.commit()
        report["quantities"] = _quantities_by_building(db, pa.project_id, report)

        pa.report, pa.status, pa.stage, pa.progress = report, "DONE", "KLAR", 1.0
        pa.finished_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
    except Exception as e:                                # noqa: BLE001
        pa = db.get(ProjectAnalysis, analysis_id)
        if pa is not None:
            pa.status, pa.error, pa.stage = "FAILED", f"{type(e).__name__}: {e}"[:400], "FEL"
            db.commit()
    finally:
        db.close()


def _latest_readings(db: Session, project_id: str) -> dict[str, AnalysisJob]:
    """Den senaste färdiga läsningen per ritning.

    En ritning kan ha lästs flera gånger - efter en rättelse, efter en regeländring. Det är den sista som
    gäller, och en läsning som inte gick igenom gäller inte alls.
    """
    out: dict[str, AnalysisJob] = {}
    rows = (db.query(AnalysisJob, Drawing).join(Drawing, AnalysisJob.drawing_id == Drawing.id)
            .filter(Drawing.project_id == project_id, AnalysisJob.status == "COMPLETED")
            .order_by(AnalysisJob.created_at).all())
    for job, d in rows:
        out[d.id] = job                              # sorterad på tid: den sista skriver över de tidigare
    return out


def _rows_of(db: Session, job: AnalysisJob) -> list[dict]:
    """Beteckningsraderna ur en läsning, med kundens rättelser lagda ovanpå.

    Raderna står i läsningens egen artefakt och inte i jobbets sammanfattning - sammanfattningen bär bara
    totaler. Rättelserna läggs ovanpå av samma skäl som på bladet: projektet ska visa samma meter som ritningen
    gör, annars är det två svar på samma fråga.
    """
    import json
    import os

    from vvs_engine.corrections import apply as apply_corrections

    from .db import Correction
    if not job.result_key:
        return []
    base = storage.path(job.result_key)
    # Handlingen, inte första bladet. En uppladdad PDF bär ofta hela handlingen - tjugosex blad i en fil - och
    # quantities.json är bara det första bladets rader; document-quantities.json är alla blad, summerade per
    # beteckning. Läste vi den första mätte vi bottenvåningen och kallade det huset: på en verklig handling gav
    # blad 1 noll rader och noll meter medan bladen bakom bar 64,91 m. Kalkylen och anbudet stod på nollan.
    # Bladets egen fil finns kvar som reserv för läsningar gjorda innan handlingsfilen skrevs.
    doc_path = os.path.join(base, "document-quantities.json")
    path = os.path.join(base, "quantities.json")
    q = {}
    rows = []
    by_page: dict[int, float] = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            q = json.load(fh)
        rows = q.get("rows") or []
    if os.path.isfile(doc_path):
        with open(doc_path, "r", encoding="utf-8") as fh:
            doc = json.load(fh) or {}
        rows = doc.get("rows") or rows
        # Varje blad bär sin egen skala. En rättelse ritad på en detalj i 1:20 och en ritad på en plan i 1:100
        # blir vitt skilda längder av samma streck, så bladets egen skala följer med rättelsen till dess blad.
        for sh in doc.get("sheets") or []:
            mpp = (sh.get("scale") or {}).get("meters_per_pt")
            if sh.get("page") is not None and mpp:
                by_page[int(sh["page"])] = float(mpp)
    if not rows:
        return []
    corr = db.query(Correction).filter(Correction.drawing_id == job.drawing_id,
                                       Correction.undone.is_(False)).all()
    if not corr:
        return rows
    out = [{"id": c.id, "drawing_id": c.drawing_id, "job_id": c.job_id, "page": c.page, "kind": c.kind,
            "designation": c.designation, "payload": c.payload, "situation": c.situation, "note": c.note,
            "undone": c.undone} for c in corr]
    return apply_corrections(rows, out, (q.get("scale") or {}).get("meters_per_pdf_point"),
                             by_page)["quantities"]


def _quantities_by_building(db: Session, project_id: str, report: dict) -> dict:
    """Mängderna från de läsningar som redan gjorts, hållna per hus.

    Hus A och hus B har var sin beteckningslista, och hus A:s koder får aldrig vandra över till hus B. Så
    summeringen görs per hus och aldrig över hela projektet: en beteckning som bara finns i ett av husen ska
    stå under det huset och ingen annanstans.
    """
    by_drawing = {r["drawing_id"]: r for r in report["documents"] if r.get("drawing_id")}
    jobs = _latest_readings(db, project_id)
    names = {d.id: d.filename for d in db.query(Drawing).filter(Drawing.project_id == project_id).all()}
    out: dict[str, dict[str, dict]] = {}
    for did, job in jobs.items():
        doc = by_drawing.get(did) or {}
        b = ((doc.get("building") or {}).get("value")) or "Okänt hus"
        for q in _rows_of(db, job):
            name = q.get("designation")
            if not name:
                continue
            e = out.setdefault(b, {}).setdefault(name, {
                "designation": name, "dn": q.get("dn"), "horizontal_m": 0.0, "risers": 0,
                "sheets": [], "labels": 0})
            e["horizontal_m"] += q.get("confirmed_horizontal_m") or 0.0
            e["risers"] += max(q.get("riser_count") or 0, q.get("riser_count_from_labels") or 0)
            if q.get("riser_height_m") is not None:
                e["riser_height_m"] = q["riser_height_m"]
            e["labels"] += q.get("label_count") or 0
            fn = names.get(did)
            if fn and fn not in e["sheets"]:
                e["sheets"].append(fn)
    for b in out:
        for e in out[b].values():
            e["horizontal_m"] = round(e["horizontal_m"], 2)
    return {b: sorted(v.values(), key=lambda e: e["designation"]) for b, v in out.items()}


# ------------------------------------------------------------------------------------------------------------
# ändringsregistret
# ------------------------------------------------------------------------------------------------------------

CHANGE_FLOOR_M = 0.5        # under en halvmeter säger två läsningar av samma rör ingenting om varandra
CHANGE_SHARE = 0.05         # och en skillnad under fem procent av sträckan är läsningens spridning, inte en ändring


def _changes(db: Session, before_id: str | None, after_id: str | None) -> dict:
    """Vad som skiljer två versioner av samma blad.

    Det här är en jämförelse mellan två LÄSNINGAR, inte mellan två ritningar, och det är en viktig skillnad.
    Två läsningar av samma oförändrade rör kan skilja sig något åt. Att en beteckning finns på det ena bladet
    och inte på det andra är starkt: den är antingen tillkommen eller borttagen. Att dess meter skiljer sig är
    svagare, och en halvmeter är inom vad läsningen själv rör sig.

    Och framför allt: finns det ingen läsning på någon av sidorna finns det ingen jämförelse. Då står det så.
    Att fylla i den saknade sidan med noll skulle göra hela den lästa sidan till "tillkommet", och den listan
    ser ut precis som en riktig ändringslista.
    """
    jobs = {}
    for side, did in (("before", before_id), ("after", after_id)):
        if not did:
            continue
        j = (db.query(AnalysisJob).filter(AnalysisJob.drawing_id == did, AnalysisJob.status == "COMPLETED")
             .order_by(AnalysisJob.created_at.desc()).first())
        if j is not None:
            jobs[side] = j
    missing = [side for side in ("before", "after") if side not in jobs]
    if missing:
        return {"state": "OLÄST", "missing": missing,
                "why": "Bladen måste vara mängdade var för sig innan de går att jämföra. En sida som inte "
                       "lästs är inte en sida utan rör - den är en sida ingen vägt, och skillnaden mellan de "
                       "två är hela ändringslistan."}

    a = {r["designation"]: r for r in _rows_of(db, jobs["before"]) if r.get("designation")}
    b = {r["designation"]: r for r in _rows_of(db, jobs["after"]) if r.get("designation")}

    def m(r):
        return round(r.get("confirmed_horizontal_m") or 0.0, 2)

    rows = []
    for k in sorted(set(a) | set(b)):
        fa, fb = a.get(k), b.get(k)
        if fa is None:
            rows.append({"designation": k, "what": "TILLKOMMEN", "before_m": None, "after_m": m(fb),
                         "dn": fb.get("dn"), "strength": "stark",
                         "why": "beteckningen finns bara på efter-bladet"})
        elif fb is None:
            rows.append({"designation": k, "what": "BORTTAGEN", "before_m": m(fa), "after_m": None,
                         "dn": fa.get("dn"), "strength": "stark",
                         "why": "beteckningen finns bara på före-bladet"})
        else:
            d = m(fb) - m(fa)
            big = abs(d) >= CHANGE_FLOOR_M and abs(d) >= CHANGE_SHARE * max(m(fa), m(fb), 1e-9)
            dn_moved = fa.get("dn") != fb.get("dn")
            rows.append({
                "designation": k, "what": "ÄNDRAD" if (big or dn_moved) else "OFÖRÄNDRAD",
                "before_m": m(fa), "after_m": m(fb), "delta_m": round(d, 2),
                "dn": fb.get("dn"), "dn_before": fa.get("dn"),
                "strength": "stark" if dn_moved else ("svag" if big else "ingen"),
                "why": ("dimensionen är läst olika på de två bladen" if dn_moved else
                        f"skillnaden är {abs(d):.2f} m" if big else
                        "skillnaden ryms inom vad två läsningar av samma rör kan skilja sig åt")})

    counts = Counter(r["what"] for r in rows)
    return {
        "state": "JÄMFÖRD",
        "jobs": {side: {"id": j.id, "at": j.created_at.isoformat()} for side, j in jobs.items()},
        "totals": {"before_m": round(sum(m(r) for r in a.values()), 2),
                   "after_m": round(sum(m(r) for r in b.values()), 2),
                   "added": counts.get("TILLKOMMEN", 0), "removed": counts.get("BORTTAGEN", 0),
                   "changed": counts.get("ÄNDRAD", 0), "unchanged": counts.get("OFÖRÄNDRAD", 0)},
        "rows": rows,
        "caveat": "Jämförelsen står mellan två läsningar. En beteckning som bara finns på ena bladet är ett "
                  "starkt tecken; en skillnad i meter är ett svagt, för två läsningar av samma oförändrade rör "
                  f"kan skilja sig åt. Under {CHANGE_FLOOR_M} m eller "
                  f"{int(CHANGE_SHARE * 100)} % av sträckan räknas skillnaden inte som en ändring alls.",
    }


@router.get("/{project_id}/analysis/changes")
def changes(project_id: str, key: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ändringsregistret för ett versionspar. Nyckeln är parets egen, ur den senaste projektanalysen."""
    p = _project(db, user, project_id)
    pa = (db.query(ProjectAnalysis).filter(ProjectAnalysis.project_id == p.id,
                                           ProjectAnalysis.status == "DONE")
          .order_by(ProjectAnalysis.created_at.desc()).first())
    if pa is None or not pa.report:
        raise HTTPException(404, "Ingen projektanalys körd ännu")
    pair = next((x for x in (pa.report.get("pairs") or []) if x.get("key") == key), None)
    if pair is None:
        raise HTTPException(404, "Det finns inget säkert versionspar med den nyckeln. Ett par som inte gick "
                                 "att ordna har inget före och inget efter, och därmed ingen ändringslista.")
    return {"key": key, "why": pair.get("why"), "confidence": pair.get("confidence"),
            "before": {"drawing_id": (pair.get("before") or {}).get("drawing_id"),
                       "filename": (pair.get("before") or {}).get("filename")},
            "after": {"drawing_id": (pair.get("after") or {}).get("drawing_id"),
                      "filename": (pair.get("after") or {}).get("filename")},
            "changes": _changes(db, (pair.get("before") or {}).get("drawing_id"),
                                (pair.get("after") or {}).get("drawing_id"))}


@router.post("/{project_id}/analysis")
def start_analysis(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Starta projektanalysen. Körs på samma kö som mängdningen."""
    p = _project(db, user, project_id)
    if not db.query(Drawing).filter(Drawing.project_id == p.id).count():
        raise HTTPException(400, "Projektet har inga handlingar att läsa")
    if not p.analysis_mode:
        p.analysis_mode = "project"
    pa = ProjectAnalysis(project_id=p.id)
    db.add(pa); db.commit()
    from .jobs import _reader
    import contextvars                                 # vem som bad om läsningen följer med till tråden
    _reader.submit(contextvars.copy_context().run, run_project_analysis, pa.id)      # egen kö: den här läsningen ska inte stå bakom mängdningen
    return {"id": pa.id, "status": pa.status}


@router.get("/{project_id}/analysis")
def latest_analysis(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    pa = (db.query(ProjectAnalysis).filter(ProjectAnalysis.project_id == p.id)
          .order_by(ProjectAnalysis.created_at.desc()).first())
    if pa is None:
        # Att ingen läsning körts ännu är ett vanligt läge, inte ett fel. Ett 404 här fick gränssnittet att
        # svälja svaret och webbläsaren att logga ett fel på varje sidladdning.
        return {"id": None, "status": "NONE", "stage": "", "progress": 0.0, "error": None, "report": None,
                "created_at": None, "finished_at": None}
    return {"id": pa.id, "status": pa.status, "stage": pa.stage, "progress": pa.progress,
            "error": pa.error, "report": pa.report,
            "created_at": pa.created_at.isoformat(),
            "finished_at": pa.finished_at.isoformat() if pa.finished_at else None}


# ------------------------------------------------------------------------------------------------------------
# projektagenten
# ------------------------------------------------------------------------------------------------------------

PROJECT_AGENT_SYSTEM_NOTE = (
    "Du arbetar mot en hel handling - flera blad, flera hus - och inte mot en ritning. Svar om ett hus bygger "
    "bara på det husets blad; en summa över projektet är en summa över två olika saker. Varje svar ska säga "
    "vilka blad det vilar på, med bladets namn eller nummer."
)


def _project_model(db: Session, p: Project):
    """Projektet som agenten ser det, byggt ur den senaste färdiga projektanalysen och bladens läsningar."""
    from vvs_engine.agent.project_tools import ProjectModel
    pa = (db.query(ProjectAnalysis).filter(ProjectAnalysis.project_id == p.id, ProjectAnalysis.status == "DONE")
          .order_by(ProjectAnalysis.created_at.desc()).first())
    if pa is None or not pa.report:
        raise HTTPException(409, "Kör projektanalysen först - agenten svarar ur det som lästs, aldrig ur något annat.")
    jobs = _latest_readings(db, p.id)
    rows = {did: _rows_of(db, job) for did, job in jobs.items()}
    report = pa.report

    def changes_for(key: str) -> dict:
        pair = next((x for x in (report.get("pairs") or []) if x.get("key") == key), None)
        if pair is None:
            return {"state": "OKÄNT_PAR"}
        return _changes(db, (pair.get("before") or {}).get("drawing_id"), (pair.get("after") or {}).get("drawing_id"))

    over = [{"drawing_id": o.drawing_id, "falt": o.field, "varde": o.value, "notering": o.note}
            for o in db.query(DocumentOverride).filter(DocumentOverride.project_id == p.id).all()]
    return ProjectModel(report, rows, changes_for=changes_for, overrides=over)


class ProjectAsk(BaseModel):
    question: str
    history: list[dict] | None = None


@router.post("/{project_id}/agent")
def project_agent(project_id: str, body: ProjectAsk, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Fråga hela handlingen. Modellen väljer verktyg, verktygen svarar ur det som lästs."""
    p = _project(db, user, project_id)
    model = _project_model(db, p)
    from vvs_engine.agent import project_tools as PT

    from .agent import run_turn
    try:
        from tools.astra_transport import agent_transport
    except Exception as e:                                      # noqa: BLE001
        raise HTTPException(503, f"agenttransporten kunde inte laddas: {type(e).__name__}")
    question = f"{PROJECT_AGENT_SYSTEM_NOTE}\n\n{body.question}"
    try:
        out = run_turn(model, agent_transport(), question, history=body.history or [], tools=PT)
    except Exception as e:                                      # noqa: BLE001
        raise HTTPException(502, f"Agenten kunde inte nås: {type(e).__name__}: {str(e)[:160]}")
    return out


class ProjectToolIn(BaseModel):
    name: str
    arguments: dict = {}


@router.post("/{project_id}/agent/tool")
def project_agent_tool(project_id: str, body: ProjectToolIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """Ett verktyg rakt av, utan modell: de färdiga frågorna i panelen. Kan inte hitta på en siffra."""
    p = _project(db, user, project_id)
    model = _project_model(db, p)
    from vvs_engine.agent import project_tools as PT
    if body.name not in PT.TOOLS:
        raise HTTPException(404, f"Okänt verktyg: {body.name}")
    return {"svar": "", "verktyg": [{"namn": body.name, "argument": body.arguments,
                                     "resultat": PT.run(body.name, model, body.arguments)}]}


@router.get("/{project_id}/agent/tools")
def project_agent_tools(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _project(db, user, project_id)
    from vvs_engine.agent import project_tools as PT
    return {"tools": [{"name": t["name"], "description": t["description"]} for t in PT.TOOLS.values()]}


class OverrideIn(BaseModel):
    drawing_id: str
    field: str
    value: str
    note: str = ""


@router.post("/{project_id}/overrides")
def set_override(project_id: str, body: OverrideIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """Rätta vad läsningen kom fram till om ett blad.

    Rättelsen ligger kvar när analysen körs om - det är hela poängen med den. Att köra om analysen är det som
    räknar om modellen och parningen, så svaret säger att det behövs.
    """
    p = _project(db, user, project_id)
    if body.field not in OVERRIDE_FIELDS:
        raise HTTPException(400, f"Går inte att rätta: {body.field}")
    if body.field == "role" and body.value not in ROLES:
        raise HTTPException(400, "Okänd roll")
    d = db.get(Drawing, body.drawing_id)
    if d is None or d.project_id != p.id:
        raise HTTPException(404, "Okänd handling")
    old = (db.query(DocumentOverride)
           .filter(DocumentOverride.drawing_id == d.id, DocumentOverride.field == body.field).first())
    if old is not None:
        old.value, old.note = body.value, body.note
    else:
        db.add(DocumentOverride(project_id=p.id, drawing_id=d.id, user_id=user.id,
                                field=body.field, value=body.value, note=body.note))
    db.commit()
    return {"ok": True, "rerun_needed": True}


@router.get("/{project_id}/overrides")
def list_overrides(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    rows = db.query(DocumentOverride).filter(DocumentOverride.project_id == p.id).all()
    return {"rows": [{"drawing_id": o.drawing_id, "field": o.field, "value": o.value, "note": o.note,
                      "at": o.created_at.isoformat()} for o in rows]}
