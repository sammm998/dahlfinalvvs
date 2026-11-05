from __future__ import annotations

import datetime as dt
import random
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .academy_grading import grade, grade_question
from .academy_models import (
    Certificate, Course, Exam, ExamAttempt, Exercise, ExerciseAttempt, Lesson, Module, Progress, Question,
    QuizAttempt, Xp,
)
from .academy_seed import seed as seed_content
from .auth import current_admin, current_user
from .db import User, get_db

"""Dahl Academy: API:t.

Regeln som allt annat följer av: **facit lämnar aldrig servern.** Varje utgång här går genom `_ex_out` eller
`_q_out`, som bygger ett svar fält för fält i stället för att dumpa raden. Lägger någon till en kolumn i
framtiden kommer den inte med av misstag - den måste skrivas in, och då är frågan ställd om den får synas.

Poäng, godkänt och certifikat bestäms också här. En klient som säger "jag klarade tentan" blir inte trodd.
"""

router = APIRouter(prefix="/api/academy", tags=["academy"])
public = APIRouter(prefix="/api/public", tags=["academy"])
admin = APIRouter(prefix="/api/admin/academy", tags=["academy-admin"])


# ---------------------------------------------------------------- nivåer

LEVELS = [
    (0, "VVS Nybörjare"),
    (300, "Mängdare"),
    (900, "Kalkylator"),
    (2000, "Senior Kalkylator"),
    (4000, "Dahl Certified"),
]


def level_for(xp: int) -> dict:
    now = LEVELS[0]
    nxt = None
    for i, (need, name) in enumerate(LEVELS):
        if xp >= need:
            now = (need, name)
            nxt = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    return {
        "namn": now[1], "fran": now[0],
        "nasta": nxt[1] if nxt else None, "nasta_vid": nxt[0] if nxt else None,
        "kvar": (nxt[0] - xp) if nxt else 0,
    }


def award_xp(db: Session, user: User, source: str, points: int, why: str) -> int:
    """Poäng för en sak, en gång. Källan är nyckeln, så samma lektion kan inte ge poäng två gånger."""
    have = db.query(Xp).filter(Xp.user_id == user.id, Xp.source == source).first()
    if have:
        return 0
    db.add(Xp(user_id=user.id, source=source, points=points, why=why))
    return points


def total_xp(db: Session, user: User) -> int:
    return int(db.query(func.coalesce(func.sum(Xp.points), 0)).filter(Xp.user_id == user.id).scalar() or 0)


# ---------------------------------------------------------------- framsteg

def _prog(db: Session, user: User, kind: str, ref: str) -> Progress:
    row = db.query(Progress).filter(Progress.user_id == user.id, Progress.kind == kind, Progress.ref == ref).first()
    if not row:
        row = Progress(user_id=user.id, kind=kind, ref=ref)
        db.add(row)
        db.flush()
    return row


def _progress_map(db: Session, user: User) -> dict[str, Progress]:
    rows = db.query(Progress).filter(Progress.user_id == user.id).all()
    return {f"{r.kind}:{r.ref}": r for r in rows}


def _module_done(db: Session, user: User, mod: Module) -> bool:
    lessons = db.query(Lesson).filter(Lesson.module_id == mod.id, Lesson.published == True).all()  # noqa: E712
    if not lessons:
        return False
    pm = _progress_map(db, user)
    return all(pm.get(f"lesson:{l.id}") and pm[f"lesson:{l.id}"].state in ("klar", "godkand") for l in lessons)


def _unlocked(db: Session, user: User, mod: Module, by_slug: dict[str, Module]) -> bool:
    """En modul är låst tills den den kräver är klar. Tom `requires` betyder öppen."""
    if not mod.requires:
        return True
    need = by_slug.get(mod.requires)
    return bool(need and _module_done(db, user, need))


# ---------------------------------------------------------------- utgångar utan facit

def _ex_out(ex: Exercise, attempts: list[ExerciseAttempt] | None = None) -> dict:
    tries = attempts or []
    best = max((a.score for a in tries), default=0.0)
    out = {
        "slug": ex.slug, "kind": ex.kind, "title": ex.title, "instructions": ex.instructions,
        "difficulty": ex.difficulty, "data": ex.data or {}, "points": ex.points,
        "tolerance_pct": round(float(ex.tolerance or 0) * 100, 1),
        "hints": ex.hints or [], "max_attempts": ex.max_attempts, "reveal_after": ex.reveal_after,
        "attempts": len(tries), "best": round(best, 3),
        "passed": any(a.passed for a in tries),
    }
    return out


def _q_out(q: Question, shuffle: random.Random | None = None) -> dict:
    opts = list(q.options or [])
    order = list(range(len(opts)))
    if shuffle and q.kind in ("single", "multi") and len(opts) > 2:
        shuffle.shuffle(order)
    return {
        "slug": q.slug, "kind": q.kind, "prompt": q.prompt,
        "options": [opts[i] for i in order], "order": order, "points": q.points, "area": q.area,
    }


def _course_out(c: Course) -> dict:
    return {"slug": c.slug, "title": c.title, "blurb": c.blurb, "level": c.level, "hours": c.hours}


@router.get("/plan/{slug}")
def plan(slug: str, _: User = Depends(current_user)):
    """Ett övningsblad som geometri. Bladet är det man ska läsa - det är inget facit, det är ritningen."""
    from .academy_plans import PLANS
    p = PLANS.get(slug)
    if not p:
        raise HTTPException(404, "Ritningen finns inte")
    return p.data()


# ---------------------------------------------------------------- kurser och lektioner

@router.get("/courses")
def courses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Course).filter(Course.published == True).order_by(Course.order).all()  # noqa: E712
    pm = _progress_map(db, user)
    out = []
    for c in rows:
        mods = db.query(Module).filter(Module.course_id == c.id, Module.published == True).all()  # noqa: E712
        lessons = db.query(Lesson).filter(Lesson.module_id.in_([m.id for m in mods] or [""])).all()
        done = sum(1 for l in lessons if pm.get(f"lesson:{l.id}") and pm[f"lesson:{l.id}"].state in ("klar", "godkand"))
        out.append({**_course_out(c), "moduler": len(mods), "lektioner": len(lessons),
                    "klara": done, "andel": round(done / len(lessons), 3) if lessons else 0.0})
    return {"kurser": out}


@router.get("/courses/{slug}")
def course(slug: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.query(Course).filter(Course.slug == slug, Course.published == True).first()  # noqa: E712
    if not c:
        raise HTTPException(404, "Utbildningen finns inte")
    mods = db.query(Module).filter(Module.course_id == c.id, Module.published == True).order_by(Module.order).all()  # noqa: E712
    by_slug = {m.slug: m for m in mods}
    pm = _progress_map(db, user)
    out_mods = []
    for m in mods:
        lessons = db.query(Lesson).filter(Lesson.module_id == m.id, Lesson.published == True).order_by(Lesson.order).all()  # noqa: E712
        ex_n = db.query(func.count(Exercise.id)).filter(Exercise.module_id == m.id).scalar() or 0
        q_n = db.query(func.count(Question.id)).filter(Question.module_id == m.id, Question.published == True).scalar() or 0  # noqa: E712
        open_ = _unlocked(db, user, m, by_slug)
        out_mods.append({
            "slug": m.slug, "title": m.title, "blurb": m.blurb, "xp": m.xp,
            "requires": m.requires, "open": open_,
            "quiz": q_n, "ovningar": int(ex_n),
            "lektioner": [{
                "id": l.id, "slug": l.slug, "title": l.title, "minutes": l.minutes,
                "state": (pm.get(f"lesson:{l.id}").state if pm.get(f"lesson:{l.id}") else "ny"),
            } for l in lessons],
        })
    exam = db.query(Exam).filter(Exam.course_id == c.id, Exam.published == True).first()  # noqa: E712
    return {**_course_out(c), "moduler": out_mods,
            "tenta": {"slug": exam.slug, "title": exam.title, "pass_pct": exam.pass_pct} if exam else None}


@router.get("/lessons/{lesson_id}")
def lesson(lesson_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    l = db.get(Lesson, lesson_id)
    if not l or not l.published:
        raise HTTPException(404, "Lektionen finns inte")
    m = db.get(Module, l.module_id)
    c = db.get(Course, m.course_id) if m else None
    sibs = db.query(Lesson).filter(Lesson.module_id == l.module_id, Lesson.published == True).order_by(Lesson.order).all()  # noqa: E712
    i = next((n for n, s in enumerate(sibs) if s.id == l.id), 0)
    exs = db.query(Exercise).filter(Exercise.lesson_id == l.id, Exercise.published == True).order_by(Exercise.order).all()  # noqa: E712
    tries = db.query(ExerciseAttempt).filter(
        ExerciseAttempt.user_id == user.id,
        ExerciseAttempt.exercise_id.in_([e.id for e in exs] or [""])).all()
    by_ex: dict[str, list[ExerciseAttempt]] = {}
    for a in tries:
        by_ex.setdefault(a.exercise_id, []).append(a)
    p = _prog(db, user, "lesson", l.id)
    db.commit()
    return {
        "id": l.id, "slug": l.slug, "title": l.title, "minutes": l.minutes, "blocks": l.blocks or [],
        "state": p.state, "xp": l.xp,
        "modul": {"slug": m.slug, "title": m.title} if m else None,
        "kurs": {"slug": c.slug, "title": c.title} if c else None,
        "forra": sibs[i - 1].id if i > 0 else None,
        "nasta": sibs[i + 1].id if i + 1 < len(sibs) else None,
        "ovningar": [_ex_out(e, by_ex.get(e.id)) for e in exs],
    }


@router.post("/lessons/{lesson_id}/klar")
def lesson_done(lesson_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    l = db.get(Lesson, lesson_id)
    if not l:
        raise HTTPException(404, "Lektionen finns inte")
    p = _prog(db, user, "lesson", l.id)
    first = p.state != "klar"
    p.state = "klar"
    p.done_at = p.done_at or dt.datetime.now(dt.timezone.utc)
    got = award_xp(db, user, f"lesson:{l.id}", l.xp, f"Lektion: {l.title}") if first else 0
    # Blev modulen klar av det här? Då ger den sina poäng, en gång.
    m = db.get(Module, l.module_id)
    if m and _module_done(db, user, m):
        mp = _prog(db, user, "module", m.id)
        mp.state = "klar"
        mp.done_at = mp.done_at or dt.datetime.now(dt.timezone.utc)
        got += award_xp(db, user, f"module:{m.id}", m.xp, f"Modul: {m.title}")
    db.commit()
    return {"state": "klar", "xp": got, "xp_totalt": total_xp(db, user)}


# ---------------------------------------------------------------- övningar

class AttemptIn(BaseModel):
    given: dict[str, Any] = {}


@router.post("/exercises/{slug}/forsok")
def exercise_attempt(slug: str, body: AttemptIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ex = db.query(Exercise).filter(Exercise.slug == slug, Exercise.published == True).first()  # noqa: E712
    if not ex:
        raise HTTPException(404, "Övningen finns inte")
    before = db.query(ExerciseAttempt).filter(
        ExerciseAttempt.user_id == user.id, ExerciseAttempt.exercise_id == ex.id).all()
    if ex.max_attempts and len(before) >= ex.max_attempts:
        raise HTTPException(409, f"Du har använt alla {ex.max_attempts} försök på den här övningen")

    score, passed, feedback = grade({
        "kind": ex.kind, "data": ex.data or {}, "answer": ex.answer or {}, "tolerance": ex.tolerance,
    }, body.given)

    n = len(before) + 1
    db.add(ExerciseAttempt(user_id=user.id, exercise_id=ex.id, n=n, given=body.given,
                           score=score, passed=passed, feedback=feedback))
    got = 0
    if passed:
        # Full poäng på första försöket, sedan avtagande - men aldrig under en tredjedel.
        share = 1.0 if n == 1 else max(0.34, 1.0 - 0.22 * (n - 1))
        got = award_xp(db, user, f"exercise:{ex.id}", round(ex.points * share), f"Övning: {ex.title}")
    db.commit()

    out: dict[str, Any] = {
        "score": round(score, 3), "passed": passed, "feedback": feedback,
        "forsok": n, "xp": got, "xp_totalt": total_xp(db, user),
    }
    # Lösningen visas först när den som övar faktiskt behöver den, och aldrig innan.
    if not passed and ex.reveal_after and n >= ex.reveal_after:
        out["losning"] = (ex.answer or {}).get("solution") or (ex.answer or {}).get("why") or feedback.get("text")
    if not passed and ex.hints:
        out["ledtrad"] = ex.hints[min(n - 1, len(ex.hints) - 1)]
    return out


# ---------------------------------------------------------------- quiz per modul

@router.get("/modules/{course_slug}/{module_slug}/quiz")
def quiz(course_slug: str, module_slug: str, n: int = 6,
         user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _find_module(db, course_slug, module_slug)
    qs = db.query(Question).filter(Question.module_id == m.id, Question.published == True).all()  # noqa: E712
    if not qs:
        raise HTTPException(404, "Modulen har inget quiz")
    rng = random.Random()
    picked = rng.sample(qs, min(n, len(qs)))
    return {"modul": m.title, "fragor": [_q_out(q, rng) for q in picked]}


class QuizIn(BaseModel):
    svar: dict[str, Any] = {}
    order: dict[str, list[int]] = {}


@router.post("/modules/{course_slug}/{module_slug}/quiz")
def quiz_submit(course_slug: str, module_slug: str, body: QuizIn,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _find_module(db, course_slug, module_slug)
    qs = {q.slug: q for q in db.query(Question).filter(Question.module_id == m.id).all()}
    rows, got, tot = [], 0.0, 0.0
    for slug, given in (body.svar or {}).items():
        q = qs.get(slug)
        if not q:
            continue
        # Alternativen visades blandade. Svaret pekar på den blandade listan och måste tillbaka till den äkta.
        order = (body.order or {}).get(slug)
        real = given
        if order and q.kind == "single" and isinstance(given, int) and 0 <= given < len(order):
            real = order[given]
        elif order and q.kind == "multi" and isinstance(given, list):
            real = [order[i] for i in given if isinstance(i, int) and 0 <= i < len(order)]
        s, ok = grade_question({"kind": q.kind, "answer": q.answer, "tolerance": q.tolerance}, real)
        got += s * q.points
        tot += q.points
        rows.append({"slug": slug, "ratt": ok, "poang": round(s * q.points, 1), "av": q.points,
                     "forklaring": q.explain})
    score = got / tot if tot else 0.0
    passed = score >= 0.7
    db.add(QuizAttempt(user_id=user.id, module_id=m.id, given=body.svar, score=score, passed=passed))
    xp = award_xp(db, user, f"quiz:{m.id}", round(50 * score), f"Quiz: {m.title}") if passed else 0
    db.commit()
    return {"score": round(score, 3), "passed": passed, "fragor": rows, "xp": xp, "xp_totalt": total_xp(db, user)}


def _find_module(db: Session, course_slug: str, module_slug: str) -> Module:
    c = db.query(Course).filter(Course.slug == course_slug).first()
    m = db.query(Module).filter(Module.course_id == (c.id if c else ""), Module.slug == module_slug).first()
    if not m:
        raise HTTPException(404, "Modulen finns inte")
    return m


# ---------------------------------------------------------------- mitt läge

@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    xp = total_xp(db, user)
    pm = _progress_map(db, user)
    courses_ = db.query(Course).filter(Course.published == True).order_by(Course.order).all()  # noqa: E712
    out_c, fortsatt = [], None
    for c in courses_:
        mods = db.query(Module).filter(Module.course_id == c.id, Module.published == True).order_by(Module.order).all()  # noqa: E712
        lessons = db.query(Lesson).filter(
            Lesson.module_id.in_([m.id for m in mods] or [""]), Lesson.published == True).order_by(Lesson.order).all()  # noqa: E712
        done = [l for l in lessons if pm.get(f"lesson:{l.id}") and pm[f"lesson:{l.id}"].state in ("klar", "godkand")]
        nxt = next((l for l in lessons if l not in done), None)
        state = "klar" if lessons and len(done) == len(lessons) else ("pagaende" if done else "ny")
        out_c.append({**_course_out(c), "klara": len(done), "av": len(lessons),
                      "andel": round(len(done) / len(lessons), 3) if lessons else 0.0,
                      "state": state, "nasta": {"id": nxt.id, "title": nxt.title} if nxt else None})
        if state == "pagaende" and not fortsatt and nxt:
            fortsatt = {"kurs": c.slug, "kurs_titel": c.title, "lektion": nxt.id, "titel": nxt.title}

    tries = db.query(ExerciseAttempt).filter(ExerciseAttempt.user_id == user.id).all()
    best: dict[str, float] = {}
    for a in tries:
        best[a.exercise_id] = max(best.get(a.exercise_id, 0.0), a.score)
    certs = db.query(Certificate).filter(Certificate.user_id == user.id, Certificate.revoked == False).all()  # noqa: E712
    senaste = db.query(Xp).filter(Xp.user_id == user.id).order_by(Xp.created_at.desc()).limit(8).all()
    return {
        "xp": xp, "niva": level_for(xp),
        "kurser": out_c, "fortsatt": fortsatt,
        "ovningar": {"gjorda": len(best), "godkanda": sum(1 for v in best.values() if v >= 1.0),
                     "snitt": round(sum(best.values()) / len(best), 3) if best else 0.0},
        "certifikat": [{"code": c.code, "title": c.title, "score": round(c.score * 100),
                        "issued": c.issued_at.isoformat()} for c in certs],
        "aktivitet": [{"why": x.why, "points": x.points, "when": x.created_at.isoformat()} for x in senaste],
    }


# ---------------------------------------------------------------- sluttentan

@router.post("/exams/{slug}/start")
def exam_start(slug: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ex = db.query(Exam).filter(Exam.slug == slug, Exam.published == True).first()  # noqa: E712
    if not ex:
        raise HTTPException(404, "Tentan finns inte")
    open_ = db.query(ExamAttempt).filter(
        ExamAttempt.user_id == user.id, ExamAttempt.exam_id == ex.id,
        ExamAttempt.status == "pagaende").first()
    if open_:
        return _attempt_out(db, open_, ex)

    if ex.requires_modules and not _exam_allowed(db, user, ex):
        raise HTTPException(409, "Du behöver göra klart utbildningens moduler innan du skriver sluttentan")

    rng = random.Random()
    items: list[dict] = []
    for sec in (ex.sections or []):
        area = sec.get("area")
        want = int(sec.get("n") or 0)
        qs = db.query(Question).filter(Question.area == area, Question.in_exam == True,  # noqa: E712
                                       Question.published == True).all()  # noqa: E712
        exs = db.query(Exercise).filter(Exercise.published == True).all()  # noqa: E712
        exs = [e for e in exs if (e.data or {}).get("exam_area") == area]
        pool: list[dict] = [{"area": area, "kind": "q", "ref": q.slug} for q in qs]
        pool += [{"area": area, "kind": "ex", "ref": e.slug} for e in exs]
        rng.shuffle(pool)
        items += pool[:want] if want else pool
    if not items:
        raise HTTPException(409, "Tentan har inga frågor ännu")
    att = ExamAttempt(user_id=user.id, exam_id=ex.id, items=items, given={})
    db.add(att)
    db.commit()
    return _attempt_out(db, att, ex)


def _exam_allowed(db: Session, user: User, ex: Exam) -> bool:
    mods = db.query(Module).filter(Module.course_id == ex.course_id, Module.published == True).all()  # noqa: E712
    return bool(mods) and all(_module_done(db, user, m) for m in mods)


def _attempt_out(db: Session, att: ExamAttempt, ex: Exam) -> dict:
    """Provet som den som skriver det får se: frågor och övningar, aldrig svar."""
    rng = random.Random(att.id)                    # samma blandning varje gång samma försök öppnas
    out = []
    for it in att.items:
        if it["kind"] == "q":
            q = db.query(Question).filter(Question.slug == it["ref"]).first()
            if q:
                out.append({"typ": "fraga", **_q_out(q, rng), "area": it["area"]})
        else:
            e = db.query(Exercise).filter(Exercise.slug == it["ref"]).first()
            if e:
                out.append({"typ": "ovning", **_ex_out(e), "area": it["area"]})
    return {
        "id": att.id, "titel": ex.title, "status": att.status,
        "sections": ex.sections or [], "pass_pct": ex.pass_pct, "section_min_pct": ex.section_min_pct,
        "minuter": ex.minutes, "startad": att.started_at.isoformat(),
        "svar": att.given or {}, "uppgifter": out,
    }


@router.get("/exams/attempt/{attempt_id}")
def exam_get(attempt_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    att = db.get(ExamAttempt, attempt_id)
    if not att or att.user_id != user.id:
        raise HTTPException(404, "Försöket finns inte")
    ex = db.get(Exam, att.exam_id)
    if att.status == "inlamnad":
        return {**_attempt_out(db, att, ex), "resultat": _exam_result(att)}
    return _attempt_out(db, att, ex)


class SaveIn(BaseModel):
    ref: str
    given: Any = None


@router.put("/exams/attempt/{attempt_id}/svar")
def exam_save(attempt_id: str, body: SaveIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Autospar. Ett svar i taget, så att en tappad uppkoppling förlorar ett svar och inte ett prov."""
    att = db.get(ExamAttempt, attempt_id)
    if not att or att.user_id != user.id:
        raise HTTPException(404, "Försöket finns inte")
    if att.status != "pagaende":
        raise HTTPException(409, "Försöket är inlämnat och går inte att ändra")
    given = dict(att.given or {})
    given[body.ref] = body.given
    att.given = given
    db.commit()
    return {"sparat": body.ref, "antal": len(given)}


def _exam_result(att: ExamAttempt) -> dict:
    return {"score": round(att.score, 3), "passed": att.passed, "per_omrade": att.by_area or {},
            "inlamnad": att.submitted_at.isoformat() if att.submitted_at else None}


@router.post("/exams/attempt/{attempt_id}/lamna-in")
def exam_submit(attempt_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    att = db.get(ExamAttempt, attempt_id)
    if not att or att.user_id != user.id:
        raise HTTPException(404, "Försöket finns inte")
    if att.status == "inlamnad":
        return {**_exam_result(att), "certifikat": _cert_for(db, att)}
    ex = db.get(Exam, att.exam_id)
    given = att.given or {}

    by_area: dict[str, dict[str, float]] = {}
    for it in att.items:
        area = it["area"]
        acc = by_area.setdefault(area, {"got": 0.0, "max": 0.0})
        if it["kind"] == "q":
            q = db.query(Question).filter(Question.slug == it["ref"]).first()
            if not q:
                continue
            s, _ = grade_question({"kind": q.kind, "answer": q.answer, "tolerance": q.tolerance}, given.get(it["ref"]))
            acc["got"] += s * q.points
            acc["max"] += q.points
        else:
            e = db.query(Exercise).filter(Exercise.slug == it["ref"]).first()
            if not e:
                continue
            s, _, _ = grade({"kind": e.kind, "data": e.data or {}, "answer": e.answer or {},
                             "tolerance": e.tolerance}, given.get(it["ref"]) or {})
            acc["got"] += s * e.points
            acc["max"] += e.points

    # Vikterna gäller, inte antalet frågor: mängdning är en fjärdedel av tentan även om den har färre uppgifter.
    weights = {s.get("area"): float(s.get("weight") or 0) for s in (ex.sections or [])}
    total_w = sum(weights.values()) or 1.0
    score = 0.0
    areas_out: dict[str, Any] = {}
    for area, acc in by_area.items():
        part = acc["got"] / acc["max"] if acc["max"] else 0.0
        areas_out[area] = {"andel": round(part, 3), "poang": round(acc["got"], 1), "av": round(acc["max"], 1),
                           "vikt": weights.get(area, 0.0),
                           "godkand": part * 100 >= ex.section_min_pct}
        score += part * (weights.get(area, 0.0) / total_w)

    every_area = all(a["godkand"] for a in areas_out.values()) if areas_out else False
    passed = (score * 100 >= ex.pass_pct) and every_area

    att.score = score
    att.by_area = areas_out
    att.passed = passed
    att.status = "inlamnad"
    att.submitted_at = dt.datetime.now(dt.timezone.utc)

    cert = None
    if passed:
        have = db.query(Certificate).filter(Certificate.user_id == user.id, Certificate.exam_id == ex.id,
                                            Certificate.revoked == False).first()  # noqa: E712
        if not have:
            have = Certificate(user_id=user.id, exam_id=ex.id, attempt_id=att.id,
                               holder=(user.name or user.email.split("@")[0]).strip(),
                               title=ex.title, score=score)
            db.add(have)
            db.flush()
        cert = have.code
        award_xp(db, user, f"exam:{ex.id}", 500, f"Sluttenta: {ex.title}")
    db.commit()
    return {**_exam_result(att), "certifikat": cert, "svaga": _weak(areas_out, ex.section_min_pct)}


def _weak(areas: dict, floor: int) -> list[str]:
    return sorted([a for a, v in areas.items() if v["andel"] * 100 < floor])


def _cert_for(db: Session, att: ExamAttempt) -> str | None:
    c = db.query(Certificate).filter(Certificate.attempt_id == att.id, Certificate.revoked == False).first()  # noqa: E712
    return c.code if c else None


# ---------------------------------------------------------------- certifikat

@router.get("/certificates")
def my_certs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Certificate).filter(Certificate.user_id == user.id).order_by(Certificate.issued_at.desc()).all()
    return {"certifikat": [{
        "code": c.code, "holder": c.holder, "title": c.title, "score": round(c.score * 100, 1),
        "issued": c.issued_at.isoformat(), "revoked": c.revoked,
    } for c in rows]}


@public.get("/academy")
def catalogue(db: Session = Depends(get_db)):
    """Utbildningen utifrån: vad den består av, för den som inte loggat in.

    Öppen med flit. En utbildningssida som beskriver en kurs den inte kan visa är en annons, och den som väljer
    en utbildning har rätt att se vad den faktiskt innehåller innan hen skaffar ett konto. Det som är stängt är
    att **göra** den - lektionstexten, övningarna, tentan - inte att veta vad den är.

    Räknat ur databasen, aldrig ur en siffra skriven i gränssnittet: en sida som lovar nio kurser när det finns
    tio är fel på samma sätt oavsett åt vilket håll den räknar fel.
    """
    kurser = db.query(Course).filter(Course.published == True).order_by(Course.order).all()  # noqa: E712
    ut = []
    for c in kurser:
        mods = db.query(Module).filter(Module.course_id == c.id, Module.published == True).all()  # noqa: E712
        mids = [m.id for m in mods]
        lek = db.query(Lesson).filter(Lesson.module_id.in_(mids or [""]),
                                      Lesson.published == True).count()  # noqa: E712
        ovn = db.query(Exercise).filter(Exercise.module_id.in_(mids or [""]),
                                        Exercise.published == True).count()  # noqa: E712
        ut.append({"slug": c.slug, "title": c.title, "blurb": c.blurb, "level": c.level, "hours": c.hours,
                   "moduler": len(mods), "lektioner": lek, "ovningar": ovn,
                   "modulnamn": [m.title for m in sorted(mods, key=lambda m: m.order)]})
    tenta = db.query(Exam).filter(Exam.published == True).order_by(Exam.slug).first()  # noqa: E712
    return {
        "kurser": ut,
        "totalt": {"kurser": len(ut), "moduler": sum(k["moduler"] for k in ut),
                   "lektioner": sum(k["lektioner"] for k in ut), "ovningar": sum(k["ovningar"] for k in ut),
                   "timmar": round(sum(k["hours"] or 0 for k in ut), 1)},
        "tenta": ({"slug": tenta.slug, "title": tenta.title, "pass_pct": tenta.pass_pct,
                   "delar": [{"title": d.get("title"), "n": d.get("n"), "weight": d.get("weight")}
                             for d in (tenta.sections or [])],
                   "uppgifter": sum(int(d.get("n") or 0) for d in (tenta.sections or []))}
                  if tenta else None),
    }


@public.get("/certificate/{code}")
def verify(code: str, db: Session = Depends(get_db)):
    """Verifieringen. Öppen med flit - ett certifikat som bara innehavaren kan visa bevisar ingenting.

    Det som visas är det som behövs för att lita på det: namn, utbildning, datum, id. Ingen e-post, inget
    konto-id, inga resultat per område. Den som verifierar ska kunna svara på "är det här äkta", inte läsa
    någon annans studieresultat.
    """
    c = db.query(Certificate).filter(func.upper(Certificate.code) == code.strip().upper()).first()
    if not c:
        return {"giltigt": False, "skal": "Certifikat-ID finns inte"}
    if c.revoked:
        return {"giltigt": False, "skal": "Certifikatet är återkallat", "code": c.code}
    now = dt.datetime.now(dt.timezone.utc)
    if c.expires_at and c.expires_at < now:
        return {"giltigt": False, "skal": "Certifikatet har gått ut", "code": c.code}
    return {
        "giltigt": True, "code": c.code, "holder": c.holder, "title": c.title,
        "issued": c.issued_at.date().isoformat(),
        "expires": c.expires_at.date().isoformat() if c.expires_at else None,
    }


# ---------------------------------------------------------------- admin: kursbyggaren

def _rows(db: Session, model, **flt):
    q = db.query(model)
    for k, v in flt.items():
        q = q.filter(getattr(model, k) == v)
    return q.all()


@admin.get("/tree")
def tree(_: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Hela utbildningen som ett träd, med facit - det här är enda stället facit får synas, och bara för admin."""
    out = []
    for c in db.query(Course).order_by(Course.order).all():
        mods = []
        for m in db.query(Module).filter(Module.course_id == c.id).order_by(Module.order).all():
            mods.append({
                "id": m.id, "slug": m.slug, "title": m.title, "order": m.order, "requires": m.requires,
                "xp": m.xp, "published": m.published,
                "lektioner": [{"id": l.id, "slug": l.slug, "title": l.title, "order": l.order,
                               "minutes": l.minutes, "published": l.published, "block": len(l.blocks or [])}
                              for l in db.query(Lesson).filter(Lesson.module_id == m.id).order_by(Lesson.order).all()],
                "ovningar": [{"id": e.id, "slug": e.slug, "kind": e.kind, "title": e.title,
                              "points": e.points, "published": e.published}
                             for e in db.query(Exercise).filter(Exercise.module_id == m.id).all()],
                "fragor": db.query(func.count(Question.id)).filter(Question.module_id == m.id).scalar() or 0,
            })
        out.append({"id": c.id, "slug": c.slug, "title": c.title, "order": c.order,
                    "published": c.published, "moduler": mods})
    exams = [{"id": e.id, "slug": e.slug, "title": e.title, "pass_pct": e.pass_pct,
              "section_min_pct": e.section_min_pct, "sections": e.sections, "published": e.published}
             for e in db.query(Exam).all()]
    return {"kurser": out, "tentor": exams}


class PatchIn(BaseModel):
    faltet: dict[str, Any] = {}


MODELS = {"course": Course, "module": Module, "lesson": Lesson, "exercise": Exercise,
          "question": Question, "exam": Exam}
# Vad en admin får ändra. Listan är vit med flit: id, ägare och användar-id ska inte gå att skriva över
# genom samma väg som en rubrik.
EDITABLE = {
    "course": {"slug", "title", "blurb", "level", "order", "published", "hours"},
    "module": {"slug", "title", "blurb", "order", "requires", "xp", "published"},
    "lesson": {"slug", "title", "minutes", "order", "blocks", "xp", "published"},
    "exercise": {"slug", "kind", "title", "instructions", "difficulty", "order", "data", "answer",
                 "tolerance", "points", "hints", "max_attempts", "reveal_after", "published"},
    "question": {"slug", "kind", "prompt", "options", "answer", "tolerance", "explain", "points",
                 "in_exam", "area", "published"},
    "exam": {"slug", "title", "sections", "pass_pct", "section_min_pct", "minutes",
             "requires_modules", "published"},
}


@admin.patch("/{what}/{row_id}")
def patch(what: str, row_id: str, body: PatchIn,
          _: User = Depends(current_admin), db: Session = Depends(get_db)):
    model = MODELS.get(what)
    if not model:
        raise HTTPException(404, "Okänd sort")
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, "Raden finns inte")
    allowed = EDITABLE[what]
    changed = []
    for k, v in (body.faltet or {}).items():
        if k not in allowed:
            raise HTTPException(400, f"Fältet {k!r} går inte att ändra här")
        setattr(row, k, v)
        changed.append(k)
    db.commit()
    return {"andrat": changed}


class NewIn(BaseModel):
    faltet: dict[str, Any] = {}


@admin.post("/{what}")
def create(what: str, body: NewIn, _: User = Depends(current_admin), db: Session = Depends(get_db)):
    model = MODELS.get(what)
    if not model:
        raise HTTPException(404, "Okänd sort")
    allowed = EDITABLE[what] | {"course_id", "module_id", "lesson_id"}
    data = {k: v for k, v in (body.faltet or {}).items() if k in allowed}
    row = model(**data)
    db.add(row)
    db.commit()
    return {"id": row.id}


@admin.delete("/{what}/{row_id}")
def remove(what: str, row_id: str, _: User = Depends(current_admin), db: Session = Depends(get_db)):
    model = MODELS.get(what)
    if not model:
        raise HTTPException(404, "Okänd sort")
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, "Raden finns inte")
    db.delete(row)
    db.commit()
    return {"borttagen": row_id}


@admin.post("/seed")
def reseed(_: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Lägg in eller uppdatera utbildningsinnehållet. Idempotent: känner igen allt på slug."""
    return seed_content(db)
