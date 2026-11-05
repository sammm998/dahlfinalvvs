from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, _now, _uuid

"""Dahl Academy: utbildningen som data i stället för som kod.

Den förra akademin bodde i en TypeScript-fil. Det fungerar tills någon vill ändra en lektion utan att bygga om
frontenden, lägga till en övning, eller se vilka som klarat sluttentan - och då fungerar det inte alls. Här är
kursen, modulen, lektionen, övningen, frågan och tentan rader i en databas, och gränssnittet är en läsare.

Tre saker är medvetet hårda:

  * **Facit lämnar aldrig servern.** `Exercise.answer` och `Question.answer` serialiseras inte av API:t. En
    rättning sker i `grade()` här inne, och klienten får poängen och en förklaring - aldrig nyckeln. Utan den
    regeln är ett certifikat värt exakt ingenting.
  * **Certifikatets id går inte att gissa.** Det är slumpat ur secrets, inte ett löpnummer. Ett löpnummer gör
    varje certifikat verifierbart genom att räkna uppåt.
  * **Ett försök på tentan är ett objekt, inte ett formulär.** Svaren sparas medan man skriver, så en
    omladdning mitt i tentan förlorar ingenting, och ett inlämnat försök går inte att ändra.

Tabellerna heter `ac_*` och rör inte den gamla `course_progress`, som fortsätter bära den befintliga
lärandevyn tills den flyttat in hit.
"""


class Course(Base):
    """En utbildning. Slug är det som står i adressen och det som seedningen känner igen den på."""
    __tablename__ = "ac_courses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    blurb: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(32), default="grund")      # grund | fortsattning | avancerad
    order: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    hours: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Module(Base):
    """En modul i en utbildning. `requires` är slug på den modul som måste vara klar först."""
    __tablename__ = "ac_modules"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("ac_courses.id"), index=True)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    blurb: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    requires: Mapped[str] = mapped_column(String(64), default="")
    xp: Mapped[int] = mapped_column(Integer, default=100)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("course_id", "slug", name="uq_ac_module_slug"),)


class Lesson(Base):
    """En lektion. Innehållet är en lista med block, så nya blocktyper inte kräver en ny kolumn."""
    __tablename__ = "ac_lessons"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(ForeignKey("ac_modules.id"), index=True)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    minutes: Mapped[int] = mapped_column(Integer, default=5)
    order: Mapped[int] = mapped_column(Integer, default=0)
    blocks: Mapped[list] = mapped_column(JSON, default=list)
    xp: Mapped[int] = mapped_column(Integer, default=10)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("module_id", "slug", name="uq_ac_lesson_slug"),)


class Exercise(Base):
    """En övning.

    `kind` avgör vilket gränssnitt som ritas och hur `grade()` rättar. `data` är allt gränssnittet behöver -
    ritningen, alternativen, siffrorna - och `answer` är facit, som aldrig lämnar servern.
    """
    __tablename__ = "ac_exercises"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("ac_lessons.id"), index=True, default="")
    module_id: Mapped[str] = mapped_column(ForeignKey("ac_modules.id"), index=True, default="")
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=1)            # 1..3
    order: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    answer: Mapped[dict] = mapped_column(JSON, default=dict)               # facit — serialiseras aldrig
    tolerance: Mapped[float] = mapped_column(Float, default=0.0)           # andel, 0.02 = ±2 %
    points: Mapped[int] = mapped_column(Integer, default=10)
    hints: Mapped[list] = mapped_column(JSON, default=list)
    max_attempts: Mapped[int] = mapped_column(Integer, default=0)          # 0 = obegränsat
    reveal_after: Mapped[int] = mapped_column(Integer, default=3)          # visa lösningen efter så många
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class ExerciseAttempt(Base):
    __tablename__ = "ac_exercise_attempts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("ac_exercises.id"), index=True)
    n: Mapped[int] = mapped_column(Integer, default=1)
    given: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, default=0.0)               # 0..1
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Question(Base):
    """En fråga i en modulls quiz eller i en tenta. Samma tabell, olika ägare."""
    __tablename__ = "ac_questions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    module_id: Mapped[str] = mapped_column(ForeignKey("ac_modules.id"), index=True, default="")
    area: Mapped[str] = mapped_column(String(32), default="teori")         # tentans huvudområde
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), default="single")        # single|multi|bool|numeric|match
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    answer: Mapped[dict] = mapped_column(JSON, default=dict)               # facit — serialiseras aldrig
    tolerance: Mapped[float] = mapped_column(Float, default=0.0)
    explain: Mapped[str] = mapped_column(Text, default="")
    points: Mapped[int] = mapped_column(Integer, default=10)
    in_exam: Mapped[bool] = mapped_column(Boolean, default=False)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class QuizAttempt(Base):
    __tablename__ = "ac_quiz_attempts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    module_id: Mapped[str] = mapped_column(ForeignKey("ac_modules.id"), index=True)
    given: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Progress(Base):
    """Var någon är. En rad per användare och sak, med saken identifierad av sin sort och sitt id."""
    __tablename__ = "ac_progress"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))                          # course | module | lesson
    ref: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(16), default="pagaende")     # pagaende | klar | godkand | underkand
    score: Mapped[float] = mapped_column(Float, default=0.0)
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    done_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref", name="uq_ac_progress"),)


class Xp(Base):
    """Varje poäng har ett skäl och en källa, så att samma sak aldrig kan ge poäng två gånger."""
    __tablename__ = "ac_xp"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)            # t.ex. "lesson:<id>"
    points: Mapped[int] = mapped_column(Integer, default=0)
    why: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (UniqueConstraint("user_id", "source", name="uq_ac_xp_source"),)


class Exam(Base):
    """Sluttentan. Vikterna per område och gränserna ligger i raden, inte i koden."""
    __tablename__ = "ac_exams"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    course_id: Mapped[str] = mapped_column(ForeignKey("ac_courses.id"), default="")
    sections: Mapped[list] = mapped_column(JSON, default=list)             # [{area, title, weight, n}]
    pass_pct: Mapped[int] = mapped_column(Integer, default=80)
    section_min_pct: Mapped[int] = mapped_column(Integer, default=60)
    minutes: Mapped[int] = mapped_column(Integer, default=0)               # 0 = ingen tidsgräns
    requires_modules: Mapped[bool] = mapped_column(Boolean, default=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class ExamAttempt(Base):
    """Ett tentaförsök. Frågorna lottas vid start och ligger kvar, så en omladdning ger samma prov."""
    __tablename__ = "ac_exam_attempts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    exam_id: Mapped[str] = mapped_column(ForeignKey("ac_exams.id"), index=True)
    items: Mapped[list] = mapped_column(JSON, default=list)                # [{area, kind, ref}]
    given: Mapped[dict] = mapped_column(JSON, default=dict)                # ref -> svar, autosparat
    status: Mapped[str] = mapped_column(String(16), default="pagaende")    # pagaende | inlamnad
    score: Mapped[float] = mapped_column(Float, default=0.0)
    by_area: Mapped[dict] = mapped_column(JSON, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def certificate_code() -> str:
    """FC-VVS-XXXXXXXX ur slumpen. Inget löpnummer: ett sådant går att räkna uppåt och verifiera främmandes."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # utan I, O, 0, 1 - de förväxlas när koden läses upp
    return "FC-VVS-" + "".join(secrets.choice(alphabet) for _ in range(8))


class Certificate(Base):
    __tablename__ = "ac_certificates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=certificate_code)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    exam_id: Mapped[str] = mapped_column(ForeignKey("ac_exams.id"))
    attempt_id: Mapped[str] = mapped_column(ForeignKey("ac_exam_attempts.id"), default="")
    holder: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
