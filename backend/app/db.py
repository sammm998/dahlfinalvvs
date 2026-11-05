from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import settings

# SQLite under en trådpool: mätningen skriver framsteg medan API:t läser. I standardläget håller varje
# skrivning hela filen låst och en läsare som kommer emellan får "database is locked" - inte efter en stund,
# utan direkt. WAL låter läsare och en skrivare arbeta samtidigt, och en väntetid gör att den som ändå
# krockar väntar i stället för att falla.
_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30} if _sqlite else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)

if _sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # vad inloggningen får se, och vilken kund den hör till. En medlem ser sitt eget arbete; en admin ser
    # tjänsten. Rollen står här och ingen annanstans, så att frågan "får den här se det" har ett svar.
    role: Mapped[str] = mapped_column(String(16), default="member")
    account_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    # Vilken sorts analys projektet använder. Saknas den är projektet ett av de gamla, och de fortsätter
    # fungera precis som förut - "simple" är vad de alltid har gjort.
    analysis_mode: Mapped[str] = mapped_column(String(16), default="")     # "" | simple | project
    # Entreprenadformen och disciplinen (docs/abt06-plan.md, docs/multi-discipline-plan.md). Tomt är vad varje
    # projekt var innan valen fanns: AB 04 och VVS, läst precis som förut.
    contract_form: Mapped[str] = mapped_column(String(8), default="")       # "" | AB04 | ABT06
    discipline: Mapped[str] = mapped_column(String(24), default="")         # "" | vvs | sprinkler | kyla | ventilation ...
    # ABT 06 med teknisk beskrivning: projektet läser en beskrivning utan ritningar och tar ut dess material
    tech_spec: Mapped[bool] = mapped_column(Boolean, default=False)
    # ABT 06 i två varianter: "ritningar" läser handlingens alla blad (och kan ha en beskrivning bredvid),
    # "beskrivning" har bara den tekniska beskrivningen och inga ritningar. Tomt är "ritningar".
    abt_variant: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    owner: Mapped[User] = relationship(back_populates="projects")
    drawings: Mapped[list["Drawing"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectAnalysis(Base):
    """Projektet läst som en handling: vad varje blad är, vad som hör ihop, och vad som inte gick att avgöra.

    Skilt från analysis_jobs därför att det är en annan fråga. Ett jobb läser en ritning och svarar med meter.
    Det här läser alla blad och svarar med vad handlingen består av - och det svaret ändras när ett blad läggs
    till eller när någon rättar en klassificering, inte när en ritning mängdas om.
    """
    __tablename__ = "project_analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    stage: Mapped[str] = mapped_column(String(64), default="QUEUED")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentOverride(Base):
    """Vad en människa rättade om ett blad.

    Den automatiska klassificeringen ska alltid gå att korrigera, och rättelsen ska överleva en omläsning. Den
    ligger därför här och inte i rapporten: rapporten byggs om, det här gör den inte.
    """
    __tablename__ = "document_overrides"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    field: Mapped[str] = mapped_column(String(32))      # building | discipline | role | number | floor | part
    value: Mapped[str] = mapped_column(String(128))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Drawing(Base):
    __tablename__ = "drawings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    n_pages: Mapped[int] = mapped_column(Integer, default=0)
    # en ritning kan ha en annan disciplin än sitt projekt; tomt = projektets. Flödet väljs i ABT 06: tomt är mätning
    discipline: Mapped[str] = mapped_column(String(24), default="")
    flow: Mapped[str] = mapped_column(String(16), default="")               # "" | rum_symboler | kravtext
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    project: Mapped[Project] = relationship(back_populates="drawings")
    jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="drawing", cascade="all, delete-orphan")


class TechSpec(Base):
    """En teknisk beskrivning i ett projekt, läst till materialposter (vvs_engine.tb).

    Posterna sparas som de lästes. Matchningen mot materialboken och katalogen görs när de visas, så att en
    katalog som läses in senare gäller för beskrivningar som redan finns.
    """
    __tablename__ = "tech_specs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    n_pages: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="COMPLETED")    # COMPLETED | FAILED
    error: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(255), default="")
    items: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    stage: Mapped[str] = mapped_column(String(64), default="QUEUED")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # disciplinen läsningen gjordes i, så att ett resultat alltid går att läsa som det lästes
    discipline: Mapped[str] = mapped_column(String(24), default="")
    drawing: Mapped[Drawing] = relationship(back_populates="jobs")


class Correction(Base):
    """One thing a person changed about a reading.

    Stored against the drawing rather than the job, so a re-analysis keeps them, and with the situation the
    correction was made in - the pen the run was drawn with, the reason the engine gave, the designation - so a
    later reading can tell whether it is looking at the same case or merely a similar-looking one.
    """
    __tablename__ = "corrections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(32))          # extend | draw | erase | retag | quantity
    designation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    situation: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    undone: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentRecipe(Base):
    """A way the solving agent settled a problem on one of an account's drawings, kept to try first next time.

    What it holds is the agent's own working - the problems it was given, the code it ran, the tools it called -
    and the corrections it recorded. Whether the recipe is any good is not stored but read off those corrections
    each time: kept while the person leaves them standing, dropped the moment one is undone. A recipe is shown
    to the agent on the same account's later drawings and nowhere else; it becomes a rule of the engine only
    through a developer and the corpus gate.
    """
    __tablename__ = "agent_recipes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    problem_types: Mapped[list] = mapped_column(JSON, default=list)
    problems: Mapped[list] = mapped_column(JSON, default=list)
    code: Mapped[list] = mapped_column(JSON, default=list)          # the code runs that worked, in order
    tools: Mapped[list] = mapped_column(JSON, default=list)         # the tool names called, in order
    correction_ids: Mapped[list] = mapped_column(JSON, default=list)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    # each later reading the recipe was shown on, and what the agent recorded there: {job_id, drawing_id,
    # user_id, correction_ids} - whether those stand is how good the recipe is, across every account
    outcomes: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LearnedRule(Base):
    """A solution the agent wrote as a rule: a function that names actions for one kind of problem.

    It reads other accounts' drawings only after it has reproduced its own sheet, passed the gate of sheets
    customers have checked, and an admin has activated it; it is switched off by itself when people undo too
    much of what it does. The code is the method, never the drawing it was learned on."""
    __tablename__ = "learned_rules"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160), default="")
    problem_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    code: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(24), default="kandidat", index=True)
    recipe_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    origin: Mapped[dict] = mapped_column(JSON, default=dict)        # job, page, what it reproduced there
    gate_results: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    gate_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    gate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    applied_count: Mapped[int] = mapped_column(Integer, default=0)
    undone_count: Mapped[int] = mapped_column(Integer, default=0)
    off_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ConfirmedTakeoff(Base):
    """A sheet whose owner says the takeoff is right: the corrected metres per designation at that moment.

    These are the facit the learned rules are tested against - real drawings, read by the engine and put right by
    the person who priced them. Withdrawn, it stops counting; the newest per drawing and sheet is the one used."""
    __tablename__ = "confirmed_takeoffs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id"), index=True)
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"), index=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    rows: Mapped[dict] = mapped_column(JSON, default=dict)          # designation -> horizontal metres
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DisciplineOverride(Base):
    """Ett företags eller ett projekts egna koder och mönster för en disciplin (inte VVS).

    Beteckningar skiljer sig mellan beställare och konsulter, så de är data och inte antaganden i koden. VVS läses
    av sin egen förklaringslista på varje blad och tar aldrig emot en avvikelse härifrån."""
    __tablename__ = "discipline_overrides"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    discipline: Mapped[str] = mapped_column(String(24), index=True)
    account_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class KeyFigure(Base):
    """Ett nyckeltal i ett företags bibliotek (ABT 06 fas 3): per enhet eller per m², med vad det ger.

    Inget värde här är en branschsanning. Ett nyckeltal är företagets eget, eller härlett ur företagets egna
    genomförda projekt med källan utskriven, och används inte förrän någon bekräftat det."""
    __tablename__ = "key_figures"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    basis: Mapped[str] = mapped_column(String(16), default="per_enhet")    # per_enhet | per_m2
    unit_code: Mapped[str] = mapped_column(String(24), default="")         # WC, TS, DUSCH ... eller yta
    building_type: Mapped[str] = mapped_column(String(64), default="")
    room_type: Mapped[str] = mapped_column(String(64), default="")
    outputs: Mapped[list] = mapped_column(JSON, default=list)              # [{system, article, measure, value, unit}]
    hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="utkast")       # utkast | bekraftad
    source: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProjectEstimate(Base):
    """Det en kalkylator bestämt för ett ABT 06-projekt: riskpåslag och valda nyckeltal. Schablonraderna räknas
    fram ur detta och de räknade enheterna varje gång - ett lagrat resultat går inte att spåra."""
    __tablename__ = "project_estimates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    risk_pct: Mapped[float] = mapped_column(Float, default=0.0)
    line_risk: Mapped[dict] = mapped_column(JSON, default=dict)            # rad -> påslag i procent
    key_figures: Mapped[list] = mapped_column(JSON, default=list)          # valda nyckeltal
    unit_names: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)   # kod -> namn, angivna av en person
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Requirement(Base):
    """Ett kostnadsdrivande krav ur en rambeskrivning (ABT 06 fas 4), med sida och ordagrant utdrag.

    `verified` säger att utdraget står ordagrant på den sidan. Ett krav påverkar aldrig kalkylen förrän en
    människa kopplat det till en rad eller ett nyckeltal."""
    __tablename__ = "requirements"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    drawing_id: Mapped[str | None] = mapped_column(ForeignKey("drawings.id"), nullable=True, index=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="oppen")        # oppen | kopplad | hanterad
    links: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(8), default="ai")         # ai | user
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RuleSetting(Base):
    """A rule a person changed, and what they changed it to.

    The engine's rules have defaults that hold for most drawings and not for all. An office that draws its
    leaders a hair short, or writes a designation list of four rows, is not wrong - the reading is, for that
    office. So the rules can be moved, per account, and what was moved is kept here rather than in the code:
    the code keeps what holds generally, this keeps what one reader found for their own drawings.

    Kept against the user and not the drawing on purpose. A rule that had to be changed for one sheet almost
    always has to be changed for every sheet the same office drew.
    """
    __tablename__ = "rule_settings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)     # varför den flyttades
    shot: Mapped[str | None] = mapped_column(Text, nullable=True)     # skärmbild som visar fallet (data-URL)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------------------------------------------
# Att driva tjänsten, inte att läsa en ritning
#
# Allt ovanför handlar om en ritning och vad som står på den. Allt härunder handlar om företaget runt
# omkring: vem som använder tjänsten, vad de betalar, vem som förde dem hit, vad de sett och vad som lärts
# av deras rättelser. Det är avsiktligt skilt åt - en tabell här får aldrig avgöra hur en ritning läses.
# ---------------------------------------------------------------------------------------------------------


class Role:
    """Vad ett konto får se. En medlem ser sitt eget; en admin ser tjänsten."""
    MEMBER = "member"
    PARTNER = "partner"      # affiliate eller ambassadör: ser sina egna värvningar och sin provision
    ADMIN = "admin"


class Account(Base):
    """Kontot bakom en användare: företaget, planen, rabatten och vem som förde dem hit.

    Skilt från `users` därför att en användare är en inloggning och ett konto är en kund. Ett företag med
    fyra rörläggare är ett konto och fyra inloggningar, och rabatten, fakturan och partnern hör till kontot.
    """
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), default="")
    org_no: Mapped[str] = mapped_column(String(32), default="")
    plan: Mapped[str] = mapped_column(String(32), default="prov")          # prov | grund | kontor | obegransad
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)        # rabatt kunden fått, i procent
    mrr_ore: Mapped[int] = mapped_column(Integer, default=0)               # månadsintäkt i ören, aldrig flyttal
    status: Mapped[str] = mapped_column(String(32), default="aktiv")       # aktiv | pausad | uppsagd
    partner_id: Mapped[str | None] = mapped_column(ForeignKey("partners.id"), nullable=True, index=True)
    referral_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Partner(Base):
    """En affiliate eller ambassadör: vem som värvar, vad kunden får och vad partnern får.

    Två procenttal, aldrig ett. Rabatten är kundens skäl att komma; provisionen är partnerns skäl att värva.
    De sätts var för sig därför att de betalas av olika sidor av samma affär.
    """
    __tablename__ = "partners"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="affiliate")     # affiliate | ambassador | aterforsaljare
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    discount_pct: Mapped[float] = mapped_column(Float, default=10.0)       # vad kunden får
    commission_pct: Mapped[float] = mapped_column(Float, default=20.0)     # vad partnern får
    commission_months: Mapped[int] = mapped_column(Integer, default=12)    # hur länge provisionen löper, 0 = alltid
    status: Mapped[str] = mapped_column(String(32), default="aktiv")
    payout_ref: Mapped[str] = mapped_column(String(255), default="")       # bankgiro eller motsvarande
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Payout(Base):
    """En utbetalning till en partner, med perioden den avser."""
    __tablename__ = "payouts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    partner_id: Mapped[str] = mapped_column(ForeignKey("partners.id"), index=True)
    period: Mapped[str] = mapped_column(String(16))                        # 2026-08
    amount_ore: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="oppen")       # oppen | utbetald | makulerad
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrmNote(Base):
    """Vad som hänt med en kund: ett samtal, ett mejl, ett löfte, ett problem."""
    __tablename__ = "crm_notes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="anteckning")    # anteckning | samtal | mejl | mote | arende
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Content(Base):
    """En text på webbplatsen, redigerad utan att koden byggs om.

    Utkast och publicerat i samma rad: ingen ska behöva välja mellan att skriva färdigt och att inte råka
    publicera halvfärdigt.
    """
    __tablename__ = "content"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Experiment(Base):
    """Ett A/B-prov: två sätt att göra samma sak, och vilket som visade sig bättre.

    Andelen som ser B står i raden. Ett prov utan mål är ingen fråga, så målet är obligatoriskt: det är den
    händelse som räknas som att provet lyckades.
    """
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    goal_event: Mapped[str] = mapped_column(String(64))
    variants: Mapped[dict] = mapped_column(JSON, default=lambda: {"a": "Nuvarande", "b": "Nytt"})
    split_b: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(32), default="utkast")      # utkast | igang | avslutad
    winner: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Event(Base):
    """En sak som hände i gränssnittet.

    Bär både A/B-provets utfall och heatmapens punkter, därför att de är samma sak sedd två gånger: var någon
    klickade och vad det ledde till. Koordinaterna är andelar av fönstret, inte bildpunkter - en heatmap i
    bildpunkter är en heatmap av en enda skärmstorlek.
    """
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    session: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)              # klick | sidvisning | mal
    path: Mapped[str] = mapped_column(String(255), index=True, default="")
    x: Mapped[float | None] = mapped_column(Float, nullable=True)          # 0..1 av bredden
    y: Mapped[float | None] = mapped_column(Float, nullable=True)          # 0..1 av den skrollade höjden
    target: Mapped[str] = mapped_column(String(255), default="")
    experiment: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    variant: Mapped[str | None] = mapped_column(String(8), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class CourseProgress(Base):
    """Var någon är i akademin: vilket steg i vilken kurs, och vad de fått för det."""
    __tablename__ = "course_progress"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course: Mapped[str] = mapped_column(String(64), index=True)
    step: Mapped[int] = mapped_column(Integer, default=0)
    done_steps: Mapped[dict] = mapped_column(JSON, default=dict)           # steg-id -> försök och resultat
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    awards: Mapped[dict] = mapped_column(JSON, default=dict)               # utmärkelse-id -> när den togs
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Calibration(Base):
    """Skalan någon mätt upp själv på ett blad.

    Motorn läser skalan ur bladets egen skalstock och utskrivna skala. Går det inte - ett urklipp, ett blad
    utan stock, en detalj i annan skala - så mäter mängdaren upp den för hand: dra en linje över något vars
    längd är känd och skriv vad det är. Den uppmätta skalan gäller framför läsningens för markeringarna på
    just det bladet och den sidan, och den säger vem som satte den och mot vad.
    """
    __tablename__ = "calibrations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"), index=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    meters_per_pdf_point: Mapped[float] = mapped_column(Float)
    length_m: Mapped[float] = mapped_column(Float)                        # vad sträckan var i verkligheten
    points: Mapped[list] = mapped_column(JSON, default=list)              # sträckan som mättes
    note: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DrawingViewport(Base):
    """Ett område på en sida med en egen skala: detaljen i hörnet är inte i planens skala.

    Ordningen avgör överlapp, så att två viewportar som täcker samma punkt alltid ger samma svar - annars kunde
    en mängd ändras av i vilken ordning någon råkade rita dem.
    """
    __tablename__ = "drawing_viewports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"), index=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(80), default="")
    ring: Mapped[list] = mapped_column(JSON, default=list)                 # [[x, y], ...] i sidans punkter
    meters_per_pdf_point: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(32), default="")            # "1:20" när den är känd
    unit: Mapped[str] = mapped_column(String(8), default="m")
    order: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CadSheet(Base):
    """Ett blad någon ritar själv.

    CAD-rummet är inte en granskning av någon annans ritning - det är ritbordet. Bladet är ett pappersformat,
    en skala och det som ritats på det, och det senare ligger som ritobjekt i världens millimeter: en vägg är
    3 000 mm lång oavsett vilken skala bladet råkar skrivas ut i. Skalan hör till pappret, inte till väggen.

    Innehållet sparas som det ritprogrammet arbetar med, så att ett blad kan öppnas igen och ritas vidare på.
    Vill man mängda det trycks det först ut till en PDF, och då blir det en handling som alla andra.
    """
    __tablename__ = "cad_sheets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), default="Nytt blad")
    paper: Mapped[str] = mapped_column(String(16), default="A3")           # A0..A4 | eget
    width_mm: Mapped[float] = mapped_column(Float, default=420.0)
    height_mm: Mapped[float] = mapped_column(Float, default=297.0)
    scale_ratio: Mapped[int] = mapped_column(Integer, default=50)          # 1:50
    content: Mapped[dict] = mapped_column(JSON, default=dict)              # lager och ritobjekt
    drawing_id: Mapped[str | None] = mapped_column(ForeignKey("drawings.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Space(Base):
    """Ett ställe i bygget: hus, plan, rum, lägenhet - ritat som ett område på ett blad.

    En mätning inne i ett space hör till det stället, och mängdtabellen kan grupperas efter det. Spaces kan
    ligga i varandra (hus > plan > rum), och det djupaste som håller punkten vinner.
    """
    __tablename__ = "spaces"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    drawing_id: Mapped[str | None] = mapped_column(ForeignKey("drawings.id"), nullable=True, index=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("spaces.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), default="rum")          # byggnad | plan | rum | lagenhet | zon
    name: Mapped[str] = mapped_column(String(120), default="")
    code: Mapped[str] = mapped_column(String(64), default="")
    ring: Mapped[list] = mapped_column(JSON, default=list)
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ToolPreset(Base):
    """Ett verktyg mängdaren ställt in och vill ha kvar: lager, färg, djup, multiplikator, beteckning.

    Bluebeams verktygslåda i miniatyr. Den som mängdar tjugo blad ställer inte in samma sak tjugo gånger.
    """
    __tablename__ = "tool_presets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    tool: Mapped[str] = mapped_column(String(32))
    layer: Mapped[str] = mapped_column(String(64), default="Mängdning")
    designation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    style: Mapped[dict] = mapped_column(JSON, default=dict)
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ServiceSetting(Base):
    """Det tjänsten själv går efter, satt av en administratör: en flyttad regel, ett antagande.

    Reglerna avgör hur en ritning läses och antagandena hur det lästa räknas ihop. Båda gällde förr per konto,
    i webbläsaren eller på användaren; nu gäller de för tjänsten, och den som flyttar en skriver varför och kan
    lägga bilden av fallet bredvid. Nyckeln säger vad raden är: `rule:<regel-id>` eller `assume:<antagande>`.
    """
    __tablename__ = "service_settings"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)                   # {"v": ...}
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    shot: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Calculation(Base):
    """Kalkylen för en läsning: antagandena och valen. Talen räknas om ur läsningen varje gång.

    Det som sparas är det en människa bestämde - timpris, påslag, vilken artikel, en timme skriven för hand -
    aldrig resultatet. Ett lagrat resultat är ett tal som inte längre går att spåra till en meter.
    """
    __tablename__ = "calculations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    assumptions: Mapped[dict] = mapped_column(JSON, default=dict)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)               # beteckning -> {artikel, timmar}
    totals: Mapped[dict] = mapped_column(JSON, default=dict)                  # senast räknade, för överblicken
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Markup(Base):
    """Vad någon ritat själv ovanpå ritningen - mätt, markerat eller antecknat.

    Det ligger vid sidan av läsningen, aldrig i den. Motorn mäter det ritaren ritade; det här är vad
    mängdaren lade till, och de två redovisas var för sig så att ingen behöver undra vilket som är vilket.
    """
    __tablename__ = "markups"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    drawing_id: Mapped[str] = mapped_column(ForeignKey("drawings.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    page: Mapped[int] = mapped_column(Integer, default=0)
    tool: Mapped[str] = mapped_column(String(32))     # langd | area | antal | polylinje | rektangel | text | moln | frihand
    layer: Mapped[str] = mapped_column(String(64), default="Mängdning")
    designation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    points: Mapped[list] = mapped_column(JSON, default=list)               # [[x, y], ...] i sidans punkter
    style: Mapped[dict] = mapped_column(JSON, default=dict)                # färg, bredd, streck, fyllning
    text: Mapped[str] = mapped_column(Text, default="")
    props: Mapped[dict] = mapped_column(JSON, default=dict)                # djup, multiplikator, tillägg, avdrag
    subject: Mapped[str] = mapped_column(String(120), default="")          # vad markeringen handlar om
    status: Mapped[str] = mapped_column(String(32), default="oppen")       # oppen | klar | avvisad | granskad
    comment: Mapped[str] = mapped_column(Text, default="")
    space_id: Mapped[str | None] = mapped_column(ForeignKey("spaces.id"), nullable=True, index=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)                 # kostnadskod, disciplin, material, egna fält
    source: Mapped[str] = mapped_column(String(24), default="manuell")     # manuell | matning | cad | ai | ocr | import
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)        # löpnummer inom lagret, för antal
    measure: Mapped[dict] = mapped_column(JSON, default=dict)              # {m, kvm, m3, antal} som verktyget räknade
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CreditEntry(Base):
    """En rad i kreditreskontran: vad som kom in, vad som gick åt, och varför.

    Saldot är summan av raderna och ingenting annat - det finns inget fält någonstans som säger "saldo" och som
    kan komma i otakt med det som hänt. Beloppet står i hundradelar av en credit, som heltal, så att en läsning
    som kostar 1,5 credits kan bokföras utan flyttal. Ägaren är kontot när användaren har ett, annars
    användaren själv: en firma med fyra inloggningar delar en pott.
    """
    __tablename__ = "credit_entries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_key: Mapped[str] = mapped_column(String(40), index=True)          # "account:<id>" | "user:<id>"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    delta_cc: Mapped[int] = mapped_column(Integer)                          # + in, - ut, i hundradels credits
    kind: Mapped[str] = mapped_column(String(24))                           # prov | kop | lasning | syn | aterbetalning | tilldelning
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)   # jobb-id, paket-id
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="")             # för köp: fakturerad | betald | makulerad
    amount_ore: Mapped[int] = mapped_column(Integer, default=0)             # för köp: priset i ören exkl. moms
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApiSpend(Base):
    """En rad i API-reskontran: ett anrop till en språkmodell och vad det kostade tjänsten.

    Taket på vad tjänsten får lägga på språkmodeller (`api_budget.py`) är summan av raderna efter den senaste
    nollställningen. Varje rad bär sina tokens och priset den räknades med, så att en flyttad prislista inte
    skriver om vad som redan gått åt."""
    __tablename__ = "api_spend"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # vem som använde budgeten: budgeten är gemensam, och alla ser vad som gått åt och till vad
    user_id: Mapped[str] = mapped_column(String(32), default="")
    user_email: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(32), default="")              # tilldelning | agent | röst | andra_läsaren
    model: Mapped[str] = mapped_column(String(64), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    kr: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[dict] = mapped_column(JSON, default=dict)                   # priset raden räknades med
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class CadRevision(Base):
    """En sparning som ändrade något: vad bladet var då, vem som sparade och vad som rördes.

    Revisionerna är historien bakom ett blad - "Flyttade vägg och tre dörrar" - och det som gör att en
    felsparning går att gå tillbaka från. Hela dokumentet sparas per revision hellre än en skillnad, för en
    skillnad man inte kan tillämpa är ingen historia, och skivan är billigare än en förlorad ritning.
    """
    __tablename__ = "cad_revisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    sheet_id: Mapped[str] = mapped_column(ForeignKey("cad_sheets.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(255), default="")
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    touched: Mapped[list] = mapped_column(JSON, default=list)              # objekt-id som ändrades
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ContactMessage(Base):
    """Ett meddelande från kontaktsidan: vem som skrev, vad, och om någon svarat."""
    __tablename__ = "contact_messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    company: Mapped[str] = mapped_column(String(255), default="")
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="ny")           # ny | besvarad | stangd
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# Kolumner som kom till efter att en databas redan var i drift. SQLAlchemys create_all skapar tabeller som
# saknas men rör aldrig en tabell som finns, så en ny kolumn på en gammal tabell måste läggas till för hand.
# Listan står här hellre än i ett migreringsverktyg därför att den är kort och läses en gång per uppstart.
_ADDED_COLUMNS = (
    ("users", "role", "VARCHAR(16) DEFAULT 'member'"),
    ("users", "account_id", "VARCHAR(32)"),
    ("users", "name", "VARCHAR(255) DEFAULT ''"),
    ("users", "last_seen_at", "TIMESTAMP"),
    ("projects", "analysis_mode", "VARCHAR(16) DEFAULT ''"),
    ("agent_recipes", "outcomes", "JSON"),
    ("projects", "contract_form", "VARCHAR(8) DEFAULT ''"),
    ("projects", "discipline", "VARCHAR(24) DEFAULT ''"),
    ("drawings", "discipline", "VARCHAR(24) DEFAULT ''"),
    ("drawings", "flow", "VARCHAR(16) DEFAULT ''"),
    ("analysis_jobs", "discipline", "VARCHAR(24) DEFAULT ''"),
    ("project_estimates", "unit_names", "JSON"),
    ("projects", "tech_spec", "BOOLEAN DEFAULT FALSE"),
    ("projects", "abt_variant", "VARCHAR(16) DEFAULT ''"),
    ("api_spend", "user_id", "VARCHAR(32) DEFAULT ''"),
    ("api_spend", "user_email", "VARCHAR(255) DEFAULT ''"),
)


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    have = set(insp.get_table_names())
    with engine.begin() as cx:
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in have:
                continue                       # create_all just made it, with the column already on it
            if column in {c["name"] for c in insp.get_columns(table)}:
                continue
            cx.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
