"""Att driva tjänsten: vad som lästs, vem som läser, vad de betalar och vad de rättat.

Ingenting här får avgöra hur en ritning läses. Det är avsiktligt: den dagen en affärsregel kan flytta en meter
går det inte längre att svara på varför en mängd blev som den blev. Modulen läser läsningarnas resultat och
skriver aldrig i dem.

Fyra saker den svarar på, och det är de fyra en som driver tjänsten faktiskt frågar:

  vad har lästs     alla konton, projekt och analyser med utfallet - täckning, falska meter, olösta fall
  vad rättades      varje rättelse en kund gjort, vad den handlade om, och om den lett till något
  vad har lärts     vilka lärdomar rättelserna gett, hur ofta de talar, och träffsäkerheten över tid
  vad kostar det    konton, planer, rabatter, partners och deras provision

Allt utom det sista är läsning av det som redan finns i databasen. Det sista är den enda delen som skriver.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from vvs_engine.learning import lessons as build_lessons

from .auth import current_admin, current_staff
from .db import (Account, AnalysisJob, Content, Correction, CourseProgress, CrmNote, Drawing, Event,
                 Experiment, Partner, Payout, Project, RuleSetting, User, get_db, ServiceSetting)
from .jobs import sheet_coverage

router = APIRouter(prefix="/api/admin", tags=["admin"])
_STARTED = dt.datetime.now(dt.timezone.utc)


def _iso(v) -> str | None:
    return v.isoformat() if v else None


def _kr(ore: int) -> float:
    return round((ore or 0) / 100.0, 2)


# ---------------------------------------------------------------------------------------------------------
# Överblick
# ---------------------------------------------------------------------------------------------------------
@router.get("/overview")
def overview(days: int = 30, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Tjänsten på en sida.

    Talen är valda så att de svarar på om tjänsten fungerar, inte på om den ser stor ut. Antal konton säger
    ingenting utan hur många av dem som läst en ritning den här månaden; antal analyser säger ingenting utan
    hur många som gick igenom. Därför står de i par.
    """
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max(1, days))
    jobs = db.query(AnalysisJob).filter(AnalysisJob.created_at >= since).all()
    done = [j for j in jobs if j.status == "COMPLETED"]
    failed = [j for j in jobs if j.status == "FAILED"]

    cov, false_share, secs = [], [], []
    for j in done:
        s = j.summary or {}
        c = sheet_coverage(s)
        if isinstance(c.get("share"), (int, float)):
            cov.append(c["share"])
        drawn, unowned = c.get("drawn_m") or 0.0, c.get("unowned_m") or 0.0
        if drawn:
            false_share.append(unowned / drawn)
        if j.started_at and j.finished_at:
            secs.append((j.finished_at - j.started_at).total_seconds())

    active = {p.owner_id for p in db.query(Project).join(Drawing).join(AnalysisJob)
              .filter(AnalysisJob.created_at >= since).all()}
    accounts = db.query(Account).all()
    corr = db.query(Correction).filter(Correction.created_at >= since).all()

    def avg(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    return {
        "days": days,
        "users": {"total": db.query(func.count(User.id)).scalar() or 0, "active": len(active),
                  "new": db.query(func.count(User.id)).filter(User.created_at >= since).scalar() or 0},
        "accounts": {"total": len(accounts),
                     "by_plan": dict(Counter(a.plan for a in accounts)),
                     "by_status": dict(Counter(a.status for a in accounts)),
                     "mrr_kr": _kr(sum(a.mrr_ore for a in accounts if a.status == "aktiv"))},
        "readings": {"total": len(jobs), "done": len(done), "failed": len(failed),
                     "median_seconds": round(sorted(secs)[len(secs) // 2], 1) if secs else None,
                     "mean_coverage": avg(cov), "mean_unowned_share": avg(false_share)},
        "corrections": {"total": len(corr), "by_kind": dict(Counter(c.kind for c in corr)),
                        "people": len({c.user_id for c in corr})},
        "drawings": db.query(func.count(Drawing.id)).scalar() or 0,
        "projects": db.query(func.count(Project.id)).scalar() or 0,
    }


@router.get("/timeline")
def timeline(days: int = 60, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """En rad per dygn: hur många läsningar, hur de gick, och hur mycket av bladen de kom igenom.

    Det är den enda kurvan som säger om systemet blir bättre. Antal läsningar per dygn mäter marknadsföring;
    täckningen per dygn mäter läsningen.
    """
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max(1, days))
    by_day: dict[str, dict] = defaultdict(lambda: {"readings": 0, "done": 0, "failed": 0, "cov": [], "corrections": 0})
    for j in db.query(AnalysisJob).filter(AnalysisJob.created_at >= since).all():
        d = by_day[j.created_at.date().isoformat()]
        d["readings"] += 1
        if j.status == "COMPLETED":
            d["done"] += 1
            share = sheet_coverage(j.summary).get("share")
            if isinstance(share, (int, float)):
                d["cov"].append(share)
        elif j.status == "FAILED":
            d["failed"] += 1
    for c in db.query(Correction).filter(Correction.created_at >= since).all():
        by_day[c.created_at.date().isoformat()]["corrections"] += 1
    out = []
    for day in sorted(by_day):
        d = by_day[day]
        out.append({"day": day, "readings": d["readings"], "done": d["done"], "failed": d["failed"],
                    "corrections": d["corrections"],
                    "coverage": round(sum(d["cov"]) / len(d["cov"]), 3) if d["cov"] else None})
    return {"days": days, "rows": out}


@router.get("/readings")
def readings(limit: int = 100, offset: int = 0, status: str = "", q: str = "",
             admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Varje läsning någon kört, med vem som körde den och vad den gav."""
    query = (db.query(AnalysisJob, Drawing, Project, User)
             .join(Drawing, AnalysisJob.drawing_id == Drawing.id)
             .join(Project, Drawing.project_id == Project.id)
             .join(User, Project.owner_id == User.id))
    if status:
        query = query.filter(AnalysisJob.status == status)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(Drawing.filename).like(like) | func.lower(Project.name).like(like)
                             | func.lower(User.email).like(like))
    total = query.count()
    rows = query.order_by(AnalysisJob.created_at.desc()).offset(offset).limit(min(limit, 300)).all()
    out = []
    for j, d, p, u in rows:
        s = j.summary or {}
        c = sheet_coverage(s)
        out.append({
            "job_id": j.id, "status": j.status, "stage": j.stage, "created_at": _iso(j.created_at),
            "seconds": round((j.finished_at - j.started_at).total_seconds(), 1) if j.started_at and j.finished_at else None,
            "drawing": d.filename, "drawing_id": d.id, "pages": d.n_pages,
            "project": p.name, "project_id": p.id, "user": u.email, "user_id": u.id,
            "scale": s.get("scale"), "designations": s.get("designations"),
            "confirmed_m": s.get("confirmed_horizontal_m"), "ambiguous_m": s.get("ambiguous_m"),
            "names": c.get("pipe_names"), "names_with_metres": c.get("pipe_names_with_metres"),
            "coverage": c.get("share"), "unowned_m": c.get("unowned_m"),
            "markup_set_aside": c.get("markup_set_aside"),
            "error": j.error,
        })
    return {"total": total, "rows": out}


# ---------------------------------------------------------------------------------------------------------
# Rättelser och vad de lärt
# ---------------------------------------------------------------------------------------------------------
@router.get("/corrections")
def corrections(limit: int = 200, offset: int = 0, kind: str = "", user_id: str = "",
                admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Varje rättelse en kund gjort, med situationen den gjordes i.

    Situationen är det som avgör om rättelsen någonsin kan tala igen: den är fingeravtrycket motorn jämför mot
    på nästa blad. En rättelse utan situation är ett påstående om sin egen ritning och inget mer, och det syns.
    """
    query = db.query(Correction, User, Drawing).join(User, Correction.user_id == User.id) \
        .join(Drawing, Correction.drawing_id == Drawing.id)
    if kind:
        query = query.filter(Correction.kind == kind)
    if user_id:
        query = query.filter(Correction.user_id == user_id)
    total = query.count()
    rows = query.order_by(Correction.created_at.desc()).offset(offset).limit(min(limit, 500)).all()
    return {"total": total, "rows": [{
        "id": c.id, "kind": c.kind, "designation": c.designation, "page": c.page, "note": c.note,
        "undone": c.undone, "created_at": _iso(c.created_at),
        "user": u.email, "user_id": u.id, "drawing": d.filename, "drawing_id": d.id, "job_id": c.job_id,
        "situation": c.situation or {}, "teaches": bool(c.situation) and not c.undone,
        "payload_keys": sorted((c.payload or {}).keys()),
    } for c, u, d in rows]}


@router.get("/learning")
def learning(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Vad rättelserna faktiskt lärt systemet - och vad de inte kan lära det.

    Det här är den ärliga versionen av "systemet blir smartare". En rättelse får göra exakt en sak på ett
    senare blad: avgöra ett fall motorn själv redan märkt som tvetydigt, till förmån för det svar en människa
    gav i samma situation. Den får aldrig skapa en sträcka, aldrig namnge geometri ingen hänvisningslinje nått
    och aldrig gå emot ritningen.

    Så sidan redovisar tre tal och inte ett: hur många rättelser som finns, hur många av dem som blivit en
    lärdom som går att tillämpa, och hur ofta en människa svarat likadant i samma situation. En lärdom som en
    enda person gett en enda gång står kvar som just det, och märks som svag.
    """
    corr = db.query(Correction).filter(Correction.undone.is_(False)).all()
    as_dicts = [{"kind": c.kind, "designation": c.designation, "payload": c.payload or {},
                 "situation": c.situation or {}, "user_id": c.user_id} for c in corr]
    ls = build_lessons(as_dicts)
    with_situation = [c for c in corr if c.situation]
    by_kind = Counter(c.kind for c in corr)
    strong = [l for l in ls if (l.get("times") or 0) >= 2]
    return {
        "corrections": {"total": len(corr), "with_situation": len(with_situation),
                        "without_situation": len(corr) - len(with_situation), "by_kind": dict(by_kind)},
        "lessons": {"total": len(ls), "strong": len(strong),
                    "rows": sorted(ls, key=lambda l: -(l.get("times") or 0))[:60]},
        "limits": [
            "En lärdom får bara avgöra ett fall som motorn själv märkt som tvetydigt.",
            "Den får aldrig skapa en sträcka eller namnge geometri ingen hänvisningslinje nådde.",
            "Den får aldrig ändra en sträcka motorn är säker på, och aldrig gå emot ritningen.",
            "Den talar bara vid exakt träff på alla sex delar av situationen - inte vid likhet.",
        ],
        "keys": ["family_style", "leader_style", "reason", "designation_shape", "topology", "candidate_shape"],
    }


@router.get("/rules")
def rule_settings(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Varje regel något konto flyttat, med skälet och skärmbilden.

    Samma regel flyttad av flera konton åt samma håll är inte en inställning, det är ett fel i grundvärdet.
    Därför grupperas de: en rad per regel, med vilka som flyttat den och vart.
    """
    rows = db.query(RuleSetting, User).join(User, RuleSetting.user_id == User.id).all()
    by_rule: dict[str, dict] = {}
    for r, u in rows:
        e = by_rule.setdefault(r.rule_id, {"rule_id": r.rule_id, "movers": [], "values": []})
        e["movers"].append({"user": u.email, "user_id": u.id, "value": r.value, "note": r.note,
                            "has_shot": bool(r.shot), "at": _iso(r.created_at)})
        e["values"].append(r.value)
    out = []
    for e in by_rule.values():
        vs = e.pop("values")
        e["n"] = len(vs)
        e["min"] = min(vs)
        e["max"] = max(vs)
        e["same_direction"] = len(set(round(v, 6) for v in vs)) == 1 and len(vs) > 1
        out.append(e)
    return {"rows": sorted(out, key=lambda e: (-e["n"], e["rule_id"]))}


@router.get("/rules/{rule_id}/shot/{user_id}")
def rule_shot(rule_id: str, user_id: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Skärmbilden någon lade vid en flyttad regel: fallet som fick dem att flytta den."""
    r = db.query(RuleSetting).filter(RuleSetting.rule_id == rule_id, RuleSetting.user_id == user_id).first()
    if r is None or not r.shot:
        raise HTTPException(404, "Ingen skärmbild")
    return {"rule_id": rule_id, "user_id": user_id, "shot": r.shot, "note": r.note}


# ---------------------------------------------------------------------------------------------------------
# Konton, partners och provision
# ---------------------------------------------------------------------------------------------------------
class AccountIn(BaseModel):
    name: str = ""
    org_no: str = ""
    plan: str = "prov"
    discount_pct: float = 0.0
    mrr_ore: int = 0
    status: str = "aktiv"
    partner_id: str | None = None
    note: str = ""


@router.get("/attention")
def attention(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Det som väntar på någon: misslyckade läsningar, en kö som växer, regler flera konton flyttat åt samma
    håll, provision som inte betalats ut, rättelser som strömmar in. Varje rad säger var man går för att göra
    något åt den. Tomt är ett svar: då väntar inget."""
    now = dt.datetime.now(dt.timezone.utc)
    week = now - dt.timedelta(days=7)
    items: list[dict] = []
    failed = db.query(func.count(AnalysisJob.id)).filter(AnalysisJob.status == "FAILED", AnalysisJob.created_at >= week).scalar() or 0
    if failed:
        items.append({"kind": "failed", "n": failed, "text": f"{failed} läsningar misslyckades de senaste sju dygnen",
                      "go": "lasningar", "tone": "bad"})
    waiting = db.query(func.count(AnalysisJob.id)).filter(AnalysisJob.status.in_(("QUEUED", "RUNNING"))).scalar() or 0
    if waiting > 3:
        items.append({"kind": "queue", "n": waiting, "text": f"{waiting} läsningar står i kö eller pågår just nu",
                      "go": "system", "tone": "warn"})
    moved = rule_settings(admin, db)["rows"]
    same = [r for r in moved if r["same_direction"]]
    if same:
        items.append({"kind": "rules", "n": len(same), "text": f"{len(same)} regler har flera konton flyttat åt samma håll - grundvärdet kan vara fel",
                      "go": "regler", "tone": "warn"})
    open_payouts = db.query(func.count(Payout.id)).filter(Payout.status == "oppen").scalar() or 0
    if open_payouts:
        items.append({"kind": "payouts", "n": open_payouts, "text": f"{open_payouts} provisionsutbetalningar är öppna",
                      "go": "partners", "tone": "warn"})
    corr = db.query(func.count(Correction.id)).filter(Correction.created_at >= week).scalar() or 0
    if corr:
        items.append({"kind": "corrections", "n": corr, "text": f"{corr} rättelser gjorda de senaste sju dygnen - se vad de lärt",
                      "go": "rattelser", "tone": "info"})
    trial = db.query(func.count(Account.id)).filter(Account.plan == "prov", Account.status == "aktiv",
                                                     Account.created_at <= now - dt.timedelta(days=30)).scalar() or 0
    if trial:
        items.append({"kind": "trial", "n": trial, "text": f"{trial} provkonton är äldre än trettio dagar",
                      "go": "konton", "tone": "info"})
    return {"items": items, "badges": {"lasningar": failed, "regler": len(same), "partners": open_payouts,
                                       "rattelser": corr, "konton": trial}}


@router.get("/system")
def system_health(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Vad som kör, och hur det mår: byggning, andra läsaren, kön, lagret, databasen. Bara fakta som går att
    kontrollera, inga hemligheter."""
    import os
    import platform
    import shutil
    import sys as _sys
    from .config import settings as cfg
    from .jobs import second_reader_state, _executor
    from .storage import storage as _storage
    on, why = second_reader_state()
    try:
        import pymupdf
        mupdf = pymupdf.version[0]
    except Exception:
        mupdf = None
    root = getattr(_storage, "root", None) or getattr(cfg, "storage_root", None) or "."
    used = 0
    try:
        for dp, _, fns in os.walk(root):
            for f in fns:
                try:
                    used += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
    except Exception:
        used = None
    try:
        free = shutil.disk_usage(root).free
    except Exception:
        free = None
    db_url = str(getattr(cfg, "database_url", "") or "")
    db_size = None
    if db_url.startswith("sqlite"):
        path = db_url.split("///")[-1]
        try:
            db_size = os.path.getsize(path)
        except OSError:
            db_size = None
    counts = {k: (db.query(func.count(AnalysisJob.id)).filter(AnalysisJob.status == k).scalar() or 0)
              for k in ("QUEUED", "RUNNING", "COMPLETED", "FAILED")}
    return {
        "build": os.environ.get("RAILWAY_GIT_COMMIT_SHA", os.environ.get("VVS_BUILD", ""))[:12] or None,
        "python": platform.python_version(), "pymupdf": mupdf,
        "second_reader": {"on": on, "why": why},
        "workers": getattr(_executor, "_max_workers", None),
        "jobs": counts,
        "storage": {"root": root, "used_bytes": used, "free_bytes": free},
        "database": {"kind": "sqlite" if db_url.startswith("sqlite") else (db_url.split(":")[0] or "okänd"), "size_bytes": db_size},
        "rules_moved": db.query(func.count(ServiceSetting.key)).filter(ServiceSetting.key.like("rule:%")).scalar() or 0,
        "started_at": _STARTED.isoformat(),
    }


@router.post("/system/cleanup")
def system_cleanup(admin: User = Depends(current_admin)):
    """Frigör lagret: äldre körningar av samma ritning, misslyckade körningar, kvarlämnade arbetsmappar och
    detektorns cache. Den senaste färdiga körningen av varje ritning och allt som pågår står kvar."""
    from .disk_space import clean_up
    from .storage import storage as _storage
    return clean_up(_storage.path(""), _storage.path("results"), _storage.path("cache/native"))


@router.get("/accounts")
def list_accounts(q: str = "", admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    accounts = db.query(Account).order_by(Account.created_at.desc()).all()
    users = db.query(User).all()
    by_account: dict[str, list[User]] = defaultdict(list)
    for u in users:
        by_account[u.account_id or ""].append(u)
    partners = {p.id: p for p in db.query(Partner).all()}
    # hur mycket var och en faktiskt använder tjänsten, vilket är det enda som förutsäger om de stannar
    use = dict(db.query(Project.owner_id, func.count(AnalysisJob.id))
               .join(Drawing, Drawing.project_id == Project.id)
               .join(AnalysisJob, AnalysisJob.drawing_id == Drawing.id)
               .group_by(Project.owner_id).all())
    rows = []
    for a in accounts:
        members = by_account.get(a.id, [])
        if q and q.lower() not in f"{a.name} {a.org_no} {' '.join(m.email for m in members)}".lower():
            continue
        rows.append({
            "id": a.id, "name": a.name, "org_no": a.org_no, "plan": a.plan, "status": a.status,
            "discount_pct": a.discount_pct, "mrr_kr": _kr(a.mrr_ore), "note": a.note,
            "created_at": _iso(a.created_at),
            "partner": partners[a.partner_id].name if a.partner_id in partners else None,
            "partner_id": a.partner_id, "referral_code": a.referral_code,
            "members": [{"id": m.id, "email": m.email, "role": m.role, "last_seen_at": _iso(m.last_seen_at)}
                        for m in members],
            "readings": sum(use.get(m.id, 0) for m in members),
        })
    unassigned = [{"id": u.id, "email": u.email, "role": u.role, "created_at": _iso(u.created_at),
                   "readings": use.get(u.id, 0)} for u in by_account.get("", [])]
    return {"rows": rows, "without_account": unassigned}


@router.post("/accounts")
def create_account(body: AccountIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    a = Account(**body.model_dump())
    db.add(a); db.commit()
    return {"id": a.id}


@router.put("/accounts/{account_id}")
def update_account(account_id: str, body: AccountIn, admin: User = Depends(current_admin),
                   db: Session = Depends(get_db)):
    a = db.get(Account, account_id)
    if a is None:
        raise HTTPException(404, "Okänt konto")
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    return {"ok": True}


class MemberIn(BaseModel):
    account_id: str | None = None
    role: str | None = None


@router.put("/users/{user_id}")
def update_user(user_id: str, body: MemberIn, admin: User = Depends(current_admin),
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "Okänd användare")
    if body.role is not None:
        if body.role not in ("member", "partner", "admin"):
            raise HTTPException(400, "Okänd roll")
        # den sista administratören får inte degradera sig själv: då finns ingen kvar som kan ge rollen igen
        if u.id == admin.id and body.role != "admin":
            others = db.query(func.count(User.id)).filter(User.role == "admin", User.id != u.id).scalar() or 0
            if not others:
                raise HTTPException(400, "Du är den enda administratören - utse en till först")
        u.role = body.role
    if body.account_id is not None:
        u.account_id = body.account_id or None
    db.commit()
    return {"ok": True}


class PartnerIn(BaseModel):
    name: str
    email: str
    kind: str = "affiliate"
    code: str
    discount_pct: float = 10.0
    commission_pct: float = 20.0
    commission_months: int = 12
    status: str = "aktiv"
    payout_ref: str = ""
    note: str = ""


def _commission(db: Session, partner: Partner) -> dict:
    """Vad en partner tjänat: intäkten från deras konton, gånger deras procent.

    Räknat i ören hela vägen. Ett provisionsbelopp som räknats i flyttal är ett belopp som inte stämmer med
    fakturan, och skillnaden dyker upp först när någon klagar.
    """
    accounts = db.query(Account).filter(Account.partner_id == partner.id).all()
    now = dt.datetime.now(dt.timezone.utc)
    live, earned = [], 0
    for a in accounts:
        months = (now.year - a.created_at.year) * 12 + (now.month - a.created_at.month)
        within = partner.commission_months == 0 or months < partner.commission_months
        share = int(round(a.mrr_ore * partner.commission_pct / 100.0)) if a.status == "aktiv" and within else 0
        earned += share
        live.append({"account_id": a.id, "name": a.name, "status": a.status, "plan": a.plan,
                     "mrr_kr": _kr(a.mrr_ore), "months": months, "within_window": within,
                     "commission_kr": _kr(share)})
    paid = db.query(func.coalesce(func.sum(Payout.amount_ore), 0)).filter(
        Payout.partner_id == partner.id, Payout.status == "utbetald").scalar() or 0
    # Öret följer med ut. Utan det måste den som skapar en utbetalning multiplicera kronor med hundra igen,
    # och då är beloppet räknat i flyttal precis som kommentaren ovan säger att det aldrig får vara.
    return {"accounts": live, "monthly_commission_kr": _kr(earned), "paid_total_kr": _kr(paid),
            "monthly_commission_ore": earned, "paid_total_ore": paid}


@router.get("/partners")
def list_partners(staff: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Alla partners för en admin; sin egen rad för en partner."""
    query = db.query(Partner)
    if staff.role != "admin":
        query = query.filter(Partner.email == staff.email)
    rows = []
    for p in query.order_by(Partner.created_at.desc()).all():
        c = _commission(db, p)
        rows.append({"id": p.id, "name": p.name, "email": p.email, "kind": p.kind, "code": p.code,
                     "discount_pct": p.discount_pct, "commission_pct": p.commission_pct,
                     "commission_months": p.commission_months, "status": p.status,
                     "payout_ref": p.payout_ref, "note": p.note, "created_at": _iso(p.created_at),
                     "n_accounts": len(c["accounts"]), **c})
    return {"rows": rows, "is_admin": staff.role == "admin"}


@router.post("/partners")
def create_partner(body: PartnerIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    if db.query(Partner).filter(Partner.code == body.code).first():
        raise HTTPException(400, "Koden är redan tagen")
    p = Partner(**body.model_dump())
    db.add(p); db.commit()
    return {"id": p.id}


@router.put("/partners/{partner_id}")
def update_partner(partner_id: str, body: PartnerIn, admin: User = Depends(current_admin),
                   db: Session = Depends(get_db)):
    p = db.get(Partner, partner_id)
    if p is None:
        raise HTTPException(404, "Okänd partner")
    clash = db.query(Partner).filter(Partner.code == body.code, Partner.id != partner_id).first()
    if clash:
        raise HTTPException(400, "Koden är redan tagen")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return {"ok": True}


class PayoutIn(BaseModel):
    partner_id: str
    period: str
    amount_ore: int
    note: str = ""


@router.get("/payouts")
def list_payouts(staff: User = Depends(current_staff), db: Session = Depends(get_db)):
    query = db.query(Payout, Partner).join(Partner, Payout.partner_id == Partner.id)
    if staff.role != "admin":
        query = query.filter(Partner.email == staff.email)
    return {"rows": [{"id": p.id, "partner": pt.name, "partner_id": pt.id, "period": p.period,
                      "amount_kr": _kr(p.amount_ore), "status": p.status, "note": p.note,
                      "created_at": _iso(p.created_at), "paid_at": _iso(p.paid_at)}
                     for p, pt in query.order_by(Payout.period.desc()).all()]}


@router.post("/payouts")
def create_payout(body: PayoutIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    if db.get(Partner, body.partner_id) is None:
        raise HTTPException(404, "Okänd partner")
    p = Payout(**body.model_dump())
    db.add(p); db.commit()
    return {"id": p.id}


class DraftIn(BaseModel):
    partner_id: str
    period: str                                   # 2026-08
    note: str = ""


@router.post("/payouts/draft")
def draft_payout(body: DraftIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Skapa en utbetalning ur den provision som faktiskt räknats fram.

    Beloppet skrivs aldrig för hand och passerar aldrig gränssnittet: det räknas här, ur samma funktion som
    visar provisionen i tabellen, och i ören hela vägen. Ett belopp som någon skrivit av från en skärm är ett
    belopp som inte går att härleda till en rad.

    En period per partner. Två utbetalningar för augusti är en dubbelbetalning som ingen upptäcker förrän
    partnern hör av sig, och den sortens fel ska inte gå att göra av misstag.
    """
    p = db.get(Partner, body.partner_id)
    if p is None:
        raise HTTPException(404, "Okänd partner")
    if not re.fullmatch(r"\d{4}-\d{2}", body.period or ""):
        raise HTTPException(400, "Perioden skrivs som 2026-08")
    old = (db.query(Payout).filter(Payout.partner_id == p.id, Payout.period == body.period,
                                   Payout.status != "makulerad").first())
    if old is not None:
        raise HTTPException(400, f"Det finns redan en utbetalning för {body.period}")
    ore = _commission(db, p)["monthly_commission_ore"]
    if ore <= 0:
        raise HTTPException(400, "Ingen provision att betala ut för perioden")
    row = Payout(partner_id=p.id, period=body.period, amount_ore=ore, note=body.note)
    db.add(row); db.commit()
    return {"id": row.id, "amount_kr": _kr(ore), "period": row.period}


@router.put("/payouts/{payout_id}")
def settle_payout(payout_id: str, status: str, admin: User = Depends(current_admin),
                  db: Session = Depends(get_db)):
    p = db.get(Payout, payout_id)
    if p is None:
        raise HTTPException(404, "Okänd utbetalning")
    if status not in ("oppen", "utbetald", "makulerad"):
        raise HTTPException(400, "Okänt läge")
    p.status = status
    p.paid_at = dt.datetime.now(dt.timezone.utc) if status == "utbetald" else None
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------------------------------------
class NoteIn(BaseModel):
    account_id: str
    kind: str = "anteckning"
    subject: str = ""
    body: str = ""
    due_at: dt.datetime | None = None


@router.get("/crm")
def crm(account_id: str = "", open_only: bool = False, admin: User = Depends(current_admin),
        db: Session = Depends(get_db)):
    query = db.query(CrmNote, Account).join(Account, CrmNote.account_id == Account.id)
    if account_id:
        query = query.filter(CrmNote.account_id == account_id)
    if open_only:
        query = query.filter(CrmNote.done.is_(False))
    rows = query.order_by(CrmNote.created_at.desc()).limit(400).all()
    return {"rows": [{"id": n.id, "account": a.name or a.id, "account_id": a.id, "kind": n.kind,
                      "subject": n.subject, "body": n.body, "due_at": _iso(n.due_at), "done": n.done,
                      "created_at": _iso(n.created_at)} for n, a in rows]}


@router.post("/crm")
def add_note(body: NoteIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    if db.get(Account, body.account_id) is None:
        raise HTTPException(404, "Okänt konto")
    n = CrmNote(author_id=admin.id, **body.model_dump())
    db.add(n); db.commit()
    return {"id": n.id}


@router.put("/crm/{note_id}")
def close_note(note_id: str, done: bool = True, admin: User = Depends(current_admin),
               db: Session = Depends(get_db)):
    n = db.get(CrmNote, note_id)
    if n is None:
        raise HTTPException(404, "Okänd anteckning")
    n.done = done
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------
# CMS
# ---------------------------------------------------------------------------------------------------------
class ContentIn(BaseModel):
    title: str = ""
    body: str = ""
    draft: str | None = None
    published: bool = False


@router.get("/content")
def list_content(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    return {"rows": [{"id": c.id, "slug": c.slug, "title": c.title, "published": c.published,
                      "has_draft": bool(c.draft and c.draft != c.body), "updated_at": _iso(c.updated_at),
                      "chars": len(c.body or "")}
                     for c in db.query(Content).order_by(Content.slug).all()]}


@router.get("/content/{slug}")
def get_content(slug: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    c = db.query(Content).filter(Content.slug == slug).first()
    if c is None:
        raise HTTPException(404, "Okänd sida")
    return {"slug": c.slug, "title": c.title, "body": c.body, "draft": c.draft, "published": c.published,
            "updated_at": _iso(c.updated_at)}


@router.put("/content/{slug}")
def put_content(slug: str, body: ContentIn, publish: bool = False, admin: User = Depends(current_admin),
                db: Session = Depends(get_db)):
    """Spara som utkast, eller publicera.

    Att spara och att publicera är två handlingar och inte en. Ett utkast som publicerar sig självt är hur en
    halvskriven mening hamnar på förstasidan.
    """
    c = db.query(Content).filter(Content.slug == slug).first()
    if c is None:
        c = Content(slug=slug)
        db.add(c)
    c.title = body.title
    if publish:
        c.body = body.draft if body.draft is not None else body.body
        c.draft = None
        c.published = True
    else:
        c.draft = body.draft if body.draft is not None else body.body
        c.published = body.published
    c.updated_by = admin.id
    db.commit()
    return {"ok": True, "published": c.published}


# ---------------------------------------------------------------------------------------------------------
# A/B-prov och heatmaps
# ---------------------------------------------------------------------------------------------------------
class ExperimentIn(BaseModel):
    key: str
    title: str = ""
    hypothesis: str = ""
    goal_event: str
    variants: dict = {"a": "Nuvarande", "b": "Nytt"}
    split_b: float = 0.5
    status: str = "utkast"


def _wilson(hits: int, n: int) -> tuple[float, float]:
    """Ett konfidensintervall som håller även vid små tal.

    Andelen träffar säger ingenting utan hur många försök den bygger på: en av två är inte femtio procent, det
    är för lite data. Wilsons intervall säger det, och det är därför det står här i stället för hits/n.
    """
    if n <= 0:
        return (0.0, 1.0)
    z = 1.96
    p = hits / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (max(0.0, (c - s) / d), min(1.0, (c + s) / d))


@router.get("/experiments")
def list_experiments(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Varje prov med utfallet, och med intervallet runt utfallet.

    Ett prov redovisas aldrig som ett enda tal. Två andelar som skiljer sig men vars intervall överlappar är
    inte ett resultat, det är ett prov som behöver gå längre - och sidan säger det rakt ut i stället för att
    låta någon läsa en vinnare ur brus.
    """
    rows = []
    for e in db.query(Experiment).order_by(Experiment.created_at.desc()).all():
        seen = dict(db.query(Event.variant, func.count(func.distinct(Event.session)))
                    .filter(Event.experiment == e.key, Event.name == "sidvisning")
                    .group_by(Event.variant).all())
        goal = dict(db.query(Event.variant, func.count(func.distinct(Event.session)))
                    .filter(Event.experiment == e.key, Event.name == e.goal_event)
                    .group_by(Event.variant).all())
        arms = {}
        for v in ("a", "b"):
            n, k = seen.get(v, 0), goal.get(v, 0)
            lo, hi = _wilson(k, n)
            arms[v] = {"label": (e.variants or {}).get(v, v.upper()), "sessions": n, "goal": k,
                       "rate": round(k / n, 4) if n else None, "lo": round(lo, 4), "hi": round(hi, 4)}
        a, b = arms["a"], arms["b"]
        settled = bool(a["sessions"] and b["sessions"] and (a["hi"] < b["lo"] or b["hi"] < a["lo"]))
        rows.append({"id": e.id, "key": e.key, "title": e.title, "hypothesis": e.hypothesis,
                     "goal_event": e.goal_event, "split_b": e.split_b, "status": e.status,
                     "winner": e.winner, "created_at": _iso(e.created_at), "arms": arms,
                     "settled": settled,
                     "reading": ("B är bättre" if settled and b["rate"] > a["rate"] else
                                 "A är bättre" if settled else
                                 "Ännu inget att läsa ut - intervallen överlappar")})
    return {"rows": rows}


@router.post("/experiments")
def create_experiment(body: ExperimentIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    if db.query(Experiment).filter(Experiment.key == body.key).first():
        raise HTTPException(400, "Nyckeln är redan tagen")
    e = Experiment(**body.model_dump())
    db.add(e); db.commit()
    return {"id": e.id}


@router.put("/experiments/{key}")
def update_experiment(key: str, status: str = "", winner: str = "", admin: User = Depends(current_admin),
                      db: Session = Depends(get_db)):
    e = db.query(Experiment).filter(Experiment.key == key).first()
    if e is None:
        raise HTTPException(404, "Okänt prov")
    if status:
        if status not in ("utkast", "igang", "avslutad"):
            raise HTTPException(400, "Okänt läge")
        e.status = status
        e.ended_at = dt.datetime.now(dt.timezone.utc) if status == "avslutad" else None
    if winner:
        e.winner = winner
    db.commit()
    return {"ok": True}


@router.get("/heatmap")
def heatmap(path: str, days: int = 30, cols: int = 48, rows: int = 64,
            admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Var folk klickar på en sida, som ett rutnät av andelar.

    Punkterna lagras som andelar av fönstret och inte som bildpunkter, så rutnätet gäller alla skärmstorlekar
    på en gång. Det som sparas är rutan, inte punkten: en heatmap som går att spåra tillbaka till en enskild
    person är inte en heatmap, det är en logg över någons arbetsdag.
    """
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max(1, days))
    cols, rows = max(4, min(cols, 120)), max(4, min(rows, 160))
    grid: Counter = Counter()
    n = 0
    for x, y in db.query(Event.x, Event.y).filter(
            Event.name == "klick", Event.path == path, Event.created_at >= since,
            Event.x.isnot(None), Event.y.isnot(None)).all():
        cx = min(cols - 1, max(0, int(x * cols)))
        cy = min(rows - 1, max(0, int(y * rows)))
        grid[(cx, cy)] += 1
        n += 1
    top = dict(Counter(t for (t,) in db.query(Event.target).filter(
        Event.name == "klick", Event.path == path, Event.created_at >= since).all() if t).most_common(20))
    return {"path": path, "days": days, "cols": cols, "rows": rows, "clicks": n,
            "peak": max(grid.values()) if grid else 0,
            "cells": [{"x": x, "y": y, "n": c} for (x, y), c in sorted(grid.items())],
            "targets": top}


@router.get("/paths")
def paths(days: int = 30, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Vilka sidor som alls har klick att titta på."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max(1, days))
    rows = db.query(Event.path, func.count(Event.id)).filter(
        Event.created_at >= since, Event.name == "klick").group_by(Event.path).all()
    return {"rows": [{"path": p, "clicks": c} for p, c in sorted(rows, key=lambda r: -r[1]) if p]}


@router.get("/academy")
def academy(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Hur långt folk kommer i akademin, och var de fastnar.

    Ett steg som många börjar och få slutför är inte ett svårt steg, det är ett dåligt formulerat steg.
    """
    rows = db.query(CourseProgress, User).join(User, CourseProgress.user_id == User.id).all()
    by_course: dict[str, dict] = defaultdict(lambda: {"started": 0, "completed": 0, "steps": Counter(), "score": 0})
    for p, _u in rows:
        c = by_course[p.course]
        c["started"] += 1
        c["completed"] += 1 if p.completed else 0
        c["score"] += p.score
        c["steps"][p.step] += 1
    return {"rows": [{"course": k, "started": v["started"], "completed": v["completed"],
                      "completion": round(v["completed"] / v["started"], 3) if v["started"] else 0.0,
                      "mean_score": round(v["score"] / v["started"], 1) if v["started"] else 0,
                      "stuck_at": dict(v["steps"].most_common(6))}
                     for k, v in sorted(by_course.items())],
            "people": len({p.user_id for p, _ in rows})}


@router.get("/agent-recipes")
def agent_recipes(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Agentens recept över alla konton: vilka som håller (personen lät rättelserna stå), hur ofta och på hur
    många konton.

    Ett recept blir aldrig en regel av sig självt. Agenten skriver lösningen som en regel, regeln prövas mot de
    kontrollerade bladen och en admin aktiverar den under Lärda regler, så att en lösning som höll på en ritning
    inte gör tio andra sämre."""
    from .db import AgentRecipe
    from .solver import recipe_score, recipe_state
    users = {u.id: u.email for u in db.query(User).all()}
    out = []
    for rec in db.query(AgentRecipe).order_by(AgentRecipe.created_at.desc()).limit(500).all():
        score, n, accounts = recipe_score(db, rec)
        out.append({"id": rec.id, "user": users.get(rec.user_id), "drawing_id": rec.drawing_id, "page": rec.page,
                    "problem_types": rec.problem_types, "state": recipe_state(db, rec), "uses": rec.uses,
                    "score": round(score, 2), "outcomes": n, "accounts": accounts,
                    "code_runs": len(rec.code or []), "corrections": len(rec.correction_ids or []),
                    "created_at": rec.created_at.isoformat()})
    by_type: dict[str, dict] = defaultdict(lambda: {"kept": 0, "rejected": 0, "uses": 0})
    for r in out:
        for t in r["problem_types"] or []:
            by_type[t][r["state"]] += 1
            by_type[t]["uses"] += r["uses"] or 0
    return {"recipes": out, "by_problem": dict(by_type)}


@router.get("/agent-recipes/{recipe_id}")
def agent_recipe(recipe_id: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Ett recept i sin helhet - problemen, koden, verktygen, rättelserna - för den som ska göra det till en regel."""
    from .db import AgentRecipe, Correction
    from .solver import recipe_state
    rec = db.get(AgentRecipe, recipe_id)
    if rec is None:
        raise HTTPException(404, "Receptet finns inte")
    corr = db.query(Correction).filter(Correction.id.in_(rec.correction_ids or [""])).all()
    return {"id": rec.id, "state": recipe_state(db, rec), "problems": rec.problems, "code": rec.code,
            "tools": rec.tools, "report": rec.report, "uses": rec.uses, "drawing_id": rec.drawing_id,
            "page": rec.page, "job_id": rec.job_id,
            "corrections": [{"id": c.id, "kind": c.kind, "designation": c.designation, "payload": c.payload,
                             "undone": c.undone} for c in corr]}


@router.get("/learned-rules")
def learned_rules_list(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """De regler systemet lärt sig av agenten: var de står på vägen från ett löst blad till alla läsningar."""
    from .db import ConfirmedTakeoff, LearnedRule
    from .learned_rules import rule_out
    rules = db.query(LearnedRule).order_by(LearnedRule.created_at.desc()).limit(500).all()
    checked = db.query(ConfirmedTakeoff).filter(ConfirmedTakeoff.withdrawn == False).count()  # noqa: E712
    return {"rules": [rule_out(db, r) for r in rules], "checked_sheets": checked}


@router.get("/learned-rules/{rule_id}")
def learned_rule(rule_id: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    from .db import LearnedRule
    from .learned_rules import rule_out
    rule = db.get(LearnedRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Regeln finns inte")
    return rule_out(db, rule, full=True)


@router.post("/learned-rules/{rule_id}/gate")
def learned_rule_gate(rule_id: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Kör spärren igen, i bakgrunden: regeln prövas på varje kontrollerat blad."""
    from .db import LearnedRule
    from .jobs import submit_rule_gate
    if db.get(LearnedRule, rule_id) is None:
        raise HTTPException(404, "Regeln finns inte")
    submit_rule_gate(rule_id)
    return {"queued": True}


@router.post("/learned-rules/{rule_id}/activate")
def learned_rule_activate(rule_id: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Låt regeln gälla alla läsningar. Bara en regel som klarat spärren kan aktiveras."""
    from .db import LearnedRule
    from .learned_rules import AKTIV, rule_out
    rule = db.get(LearnedRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Regeln finns inte")
    if not rule.gate_passed:
        raise HTTPException(409, f"Regeln har inte klarat spärren: {rule.gate_reason or 'den är inte prövad än'}")
    rule.state, rule.activated_by, rule.off_reason = AKTIV, admin.id, None
    rule.applied_count, rule.undone_count = rule.applied_count or 0, rule.undone_count or 0
    db.commit()
    return rule_out(db, rule)


@router.post("/learned-rules/{rule_id}/deactivate")
def learned_rule_deactivate(rule_id: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    from .db import LearnedRule
    from .learned_rules import AVSTANGD, rule_out
    rule = db.get(LearnedRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Regeln finns inte")
    rule.state, rule.off_reason = AVSTANGD, "avstängd av admin"
    db.commit()
    return rule_out(db, rule)


# ------------------------------------------------------------------------------------------------------------
# Taket på API-kostnaden (api_budget.py)
# ------------------------------------------------------------------------------------------------------------

class ApiBudgetIn(BaseModel):
    limit_kr: float | None = None
    usd_sek: float | None = None
    prices: dict[str, dict | None] | None = None


@router.get("/api-budget")
def api_budget_status(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Vad tjänsten lagt på språkmodeller sedan den senaste nollställningen, taket, och prislistan."""
    from . import api_budget
    return api_budget.status(db)


@router.put("/api-budget")
def api_budget_set(body: ApiBudgetIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    from . import api_budget
    change: dict[str, Any] = {}
    if body.limit_kr is not None:
        if body.limit_kr < 0:
            raise HTTPException(422, "Taket kan inte vara negativt.")
        change["limit_kr"] = float(body.limit_kr)
    if body.usd_sek is not None:
        if body.usd_sek <= 0:
            raise HTTPException(422, "Växelkursen måste vara större än noll.")
        change["usd_sek"] = float(body.usd_sek)
    if body.prices is not None:
        clean: dict[str, dict | None] = {}
        for name, p in body.prices.items():
            if p is None:
                clean[name] = None
                continue
            for k in ("in", "out", "cached", "cache_write"):
                if k in p and p[k] is not None and float(p[k]) < 0:
                    raise HTTPException(422, f"Priset för {name} kan inte vara negativt.")
            clean[name] = {k: (float(v) if k in ("in", "out", "cached", "cache_write") and v is not None else v)
                           for k, v in p.items() if k in ("in", "out", "cached", "cache_write", "source", "date")}
        change["prices"] = clean
    api_budget.save(db, change, admin.id)
    return api_budget.status(db)


@router.post("/api-budget/reset")
def api_budget_reset(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Räkningen börjar om på noll från nu; reskontran står kvar som den var."""
    from . import api_budget
    api_budget.save(db, {"reset_at": dt.datetime.now(dt.timezone.utc).isoformat()}, admin.id)
    return api_budget.status(db)
