from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from typing import Literal

import subprocess
from contextlib import asynccontextmanager
from functools import lru_cache
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from . import (abt as abt_api, academy as academy_legacy, academy_api, admin as admin_api, cad as cad_api,
               calc as calc_api, credits as credits_api, desk as desk_api, exports, jobs,
               keyfigures as keyfigures_api, markups as markups_api, projects_api, public as public_api)
from vvs_engine.output.schema import upgrade
from vvs_engine.coverage import completion_checks
from vvs_engine.corrections import KINDS as CORRECTION_KINDS, apply as apply_corrections
from vvs_engine.learning import KEYS, lessons, settle, situation
from .auth import (create_token, current_user, hash_password, login_blocked, login_failed, current_admin,
                   login_succeeded, verify_or_burn, verify_password)
from .config import demand_a_real_secret, settings
from .db import ServiceSetting, Correction, AnalysisJob, Drawing, Project, RuleSetting, User, get_db, init_db
from .storage import storage

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Först av allt: en tjänst som undertecknar inloggningsbevis med den nyckel som står i källkoden ska inte
    # gå upp alls. Ett varningsmeddelande i en logg ingen läser är samma sak som ingenting.
    demand_a_real_secret()
    init_db()
    from . import api_budget
    api_budget.install_meter()      # the engine's own transports ask and pay through the service's ledger
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        from .reset_once import run as _reset_once
        _reset_once(storage.path(""))
    # Var data bor, sagt i loggen vid varje uppstart. Den som letar efter försvunna ritningar hittar svaret här
    # i stället för att gissa, och den som driftsätter ser det innan den första ritningen laddas upp.
    try:
        from .persistence import say_at_startup
        say_at_startup()
    except Exception as e:                                     # noqa: BLE001
        print(f"[data] kunde inte avgöra var data ligger: {type(e).__name__}: {e}", flush=True)
    # Utbildningens innehåll hör till koden, inte till en handpåläggning efter driftsättning. Seedningen känner
    # igen allt på slug och uppdaterar i stället för att skapa dubbletter, så den kan köras vid varje uppstart.
    try:
        from .academy_seed import seed as _seed_academy
        from .db import SessionLocal as _S
        with _S() as _db:
            _seed_academy(_db)
    except Exception as e:                                     # noqa: BLE001
        # En utbildning som inte gick att lägga in får inte hindra tjänsten från att starta.
        print(f"[academy] innehållet kunde inte läggas in: {e}", flush=True)
    # Diskutrymme som inte bär någon information - dubbla kopior, okomprimerad diagnostik, kvarlämnade
    # arbetskataloger, misslyckade analysers rester - återtas i bakgrunden, så att uppstarten inte väntar på det.
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        import threading

        def _reclaim():
            try:
                from .disk_space import reclaim, free_bytes, clean_up, STARTUP_CLEAN_BELOW
                print(f"[disk] återtaget: {reclaim(storage.path('results'))}", flush=True)
                if free_bytes(storage.path("")) < STARTUP_CLEAN_BELOW:
                    got = clean_up(storage.path(""), storage.path("results"), storage.path("cache/native"))
                    print(f"[disk] nästan fullt, äldre körningar och cache rensade: {got}", flush=True)
            except Exception as e:                             # noqa: BLE001
                print(f"[disk] kunde inte städa: {type(e).__name__}: {e}", flush=True)
        threading.Thread(target=_reclaim, name="disk-reclaim", daemon=True).start()
    # jobb som var på väg när tjänsten senast stängde körs igen; ett RUNNING som ingen kör är en lögn på skärmen
    if os.environ.get("PYTEST_CURRENT_TEST") is None or os.environ.get("VVS_RESUBMIT_ON_START") == "1":
        from . import jobs as _jobs
        _jobs.resubmit_unfinished()
    yield
    api_budget.uninstall_meter()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=_lifespan)


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    """Ett oväntat fel svarar med vad som hände, inte med ett tomt "Fel 500".

    En full disk och en resultatfil som skrevs halvt (när disken tog slut mitt i en analys) är de vanligaste, och
    båda går att göra något åt - men bara om den som ser felet får veta vilket det är. Felet loggas i sin helhet;
    till webbläsaren går orsaken i en mening."""
    import errno
    import logging
    logging.getLogger("vvs").exception("Oväntat fel i %s %s", request.method, request.url.path)
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        why = ("Disken där ritningar och resultat sparas är full. Rensa under Admin -> System eller utöka volymen "
               "i Railway, och försök igen.")
    elif isinstance(exc, (ValueError, UnicodeDecodeError)) and "/result" in request.url.path:
        why = ("En resultatfil för den här analysen är trasig (troligen skrevs den när disken var full). "
               "Kör analysen igen.")
    else:
        why = f"Serverfel: {type(exc).__name__}: {str(exc)[:200]}"
    return JSONResponse(status_code=500, content={"detail": why})
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


app.include_router(admin_api.router)
app.include_router(public_api.router)
app.include_router(projects_api.router)
# Den gamla akademins framsteg ligger kvar och bär den befintliga lärandevyn; den nya bär Radiator VVS Academy.
# De delar prefix men inga vägar, och den gamla tabellen rörs inte.
app.include_router(academy_legacy.router)
app.include_router(academy_api.router)
app.include_router(academy_api.public)
app.include_router(academy_api.admin)
app.include_router(markups_api.router)
app.include_router(markups_api.presets)
app.include_router(calc_api.router)
app.include_router(cad_api.router)
app.include_router(credits_api.router)
app.include_router(abt_api.router)
app.include_router(keyfigures_api.router)
app.include_router(desk_api.router)


# ---------------------------------------------------------------- health / auth
@lru_cache(maxsize=1)
def _build_stamp() -> dict:
    """Which code produced this reading. A number on screen is only checkable if you can tell what made it."""
    from vvs_engine import __version__
    # the image carries no .git, so take the build from whatever the platform exposes before falling back to git
    # "unknown" is what the image bakes in when nothing was passed at build time, and it is not an answer: taking
    # it as one stops the search before the platform's own variables are ever looked at, which is exactly what
    # happened in production - the endpoint reported "unknown" while Railway knew the commit all along.
    cand = [os.environ.get(k, "") for k in ("VVS_BUILD", "RAILWAY_GIT_COMMIT_SHA", "SOURCE_COMMIT", "GIT_COMMIT",
                                            "RAILWAY_DEPLOYMENT_ID")]
    build = next((v[:12] for v in cand if v.strip() and v.strip().lower() != "unknown"), "")
    if not build:
        try:
            build = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                   timeout=2, cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                                   ).stdout.strip() or "unknown"
        except Exception:
            build = "unknown"
    return {"engine": __version__, "build": build}


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/health")
def api_health():
    return {"status": "ok"}


@app.get("/api/version")
def version():
    """What is running here, and what it can reach - answerable without logging in.

    A reading is only checkable if you can tell which code produced it, and a second reader is only verifiable if
    you can tell whether this installation is configured for one and can actually reach it. Both are said here as
    plain facts. No credential is returned, and none can be inferred beyond "there is one" or "there is not".
    """
    from .jobs import second_reader_state
    on, why = second_reader_state()
    who: list[dict] = []
    try:
        from tools.readers import state as reader_state
        who = reader_state()
    except Exception:                                           # noqa: BLE001
        who = []
    used = [r for r in who if r.get("in_use")]
    try:
        from .persistence import verdict
        data = verdict()
    except Exception as e:                                      # noqa: BLE001
        data = {"persistent": None, "why": f"gick inte att avgöra: {type(e).__name__}"}
    return {**_build_stamp(), "data": data,
            "second_reader": {"enabled": on, "reason": why,
                              "model": used[0]["model"] if len(used) == 1 else None,
                              "readers": who, "agreement_required": len(used) > 1,
                              "setting": settings.second_reader}}


class RegisterIn(BaseModel):
    email: EmailStr
    password: str


@app.post("/api/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not settings.allow_registration and db.query(User).count() > 0:   # the first account is always possible
        raise HTTPException(403, "Registrering är avstängd")
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(400, "E-postadressen är redan registrerad")
    if len(body.password) < 6:
        raise HTTPException(400, "Lösenordet måste vara minst 6 tecken")
    # The first account to register runs the service. Somebody has to be able to reach the admin pages, and the
    # alternatives are worse: a password in an environment variable is a password in a deployment log, and a
    # hard-coded address is an account nobody can take away. After the first, every admin is made by an admin.
    first = (db.query(User).count() == 0)
    u = User(email=body.email.lower(), password_hash=hash_password(body.password),
             role="admin" if first else "member")
    db.add(u); db.flush()
    # ett nytt konto får något att prova med - bokfört i reskontran, så att det bara sker en gång
    credits_api.grant_trial(db, u)
    db.commit()
    return {"access_token": create_token(u), "token_type": "bearer", "email": u.email, "role": u.role}


@app.post("/api/auth/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.lower().strip()
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or \
        (request.client.host if request.client else "?")
    wait = login_blocked(email, ip)
    if wait:
        raise HTTPException(429, f"För många misslyckade försök. Försök igen om {max(1, wait // 60)} minuter.",
                            headers={"Retry-After": str(wait)})
    u = db.query(User).filter(User.email == email).first()
    if not verify_or_burn(form.password, u.password_hash if u else None):
        login_failed(email, ip)
        raise HTTPException(401, "Fel e-post eller lösenord")
    login_succeeded(email)
    return {"access_token": create_token(u), "token_type": "bearer", "email": u.email, "role": u.role}


@app.get("/api/knowledge")
def code_knowledge(user: User = Depends(current_user)):
    from .knowledge import vocabulary
    return vocabulary()


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "role": user.role or "member", "account_id": user.account_id}


# ---------------------------------------------------------------- projects
class ProjectIn(BaseModel):
    name: str
    description: str = ""
    # AB 04 och VVS är förval: ett projekt skapat utan val är det som alla projekt varit (docs/abt06-plan.md)
    contract_form: str = "AB04"
    discipline: str = "vvs"


CONTRACT_FORMS = ("AB04", "ABT06")


def _checked_modes(contract_form: str | None, discipline: str | None) -> tuple[str | None, str | None]:
    """The project's modes as stored, or a 422 that says which choice is not available."""
    from vvs_engine import disciplines as disc
    cf = None if contract_form is None else (contract_form or "").strip().upper()
    if cf is not None and cf not in CONTRACT_FORMS:
        raise HTTPException(422, "Okänd entreprenadform. Välj AB 04 eller ABT 06.")
    d = None if discipline is None else disc.normalize(discipline)
    if d is not None and not disc.known(d):
        raise HTTPException(422, "Okänd disciplin.")
    if d is not None and not disc.selectable(d):
        raise HTTPException(422, f"{disc.get(d).name} är inte byggd än och kan inte väljas.")
    return cf, d


class ProjectFormIn(BaseModel):
    contract_form: str | None = None
    discipline: str | None = None
    confirm: bool = False


def _project(db: Session, user: User, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Projektet finns inte")
    return p


def _drawing(db: Session, user: User, drawing_id: str) -> Drawing:
    d = db.get(Drawing, drawing_id)
    if d is None or d.project.owner_id != user.id:
        raise HTTPException(404, "Ritningen finns inte")
    return d


def _job(db: Session, user: User, job_id: str) -> AnalysisJob:
    j = db.get(AnalysisJob, job_id)
    if j is None or j.drawing.project.owner_id != user.id:
        raise HTTPException(404, "Analysen finns inte")
    return j


def _proj_out(p: Project):
    from vvs_engine import disciplines as disc
    return {"id": p.id, "name": p.name, "description": p.description, "created_at": p.created_at, "n_drawings": len(p.drawings),
            # tomt är vad projektet var innan valen fanns: AB 04 och VVS
            "contract_form": p.contract_form or "AB04", "discipline": disc.normalize(p.discipline)}


def _drawing_out(d: Drawing):
    latest = sorted(d.jobs, key=lambda j: j.created_at)[-1] if d.jobs else None
    return {"id": d.id, "project_id": d.project_id, "filename": d.filename, "size_bytes": d.size_bytes, "n_pages": d.n_pages,
            "sha256": d.sha256, "created_at": d.created_at, "latest_job": _job_out(latest) if latest else None,
            "discipline": d.discipline or "", "flow": d.flow or ""}


def _job_out(j: AnalysisJob):
    return {"id": j.id, "drawing_id": j.drawing_id, "status": j.status, "stage": j.stage, "progress": j.progress, "error": j.error,
            "summary": j.summary, "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at}


@app.get("/api/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Handlingarna - inte agentens skrivbord.

    Det som släpps i agentens chatt blir en riktig ritning med ett riktigt jobb, så att svaret går att öppna i
    Analys och räkna vidare på. Men det är inte en handling någon har lagt upp, och i listan över projekt vore
    den bara i vägen: skrivbordet hör till samtalet, och syns där.
    """
    rows = (db.query(Project).filter(Project.owner_id == user.id, Project.analysis_mode != desk_api.DESK_MODE)
            .order_by(Project.created_at.desc()).all())
    return [_proj_out(p) for p in rows]


@app.post("/api/projects")
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    contract_form, discipline = _checked_modes(body.contract_form, body.discipline)
    p = Project(owner_id=user.id, name=body.name.strip() or "Namnlöst projekt", description=body.description,
                contract_form=contract_form, discipline=discipline)
    db.add(p); db.commit()
    return _proj_out(p)


@app.get("/api/disciplines")
def list_disciplines():
    """Disciplinerna tjänsten känner, byggda eller inte. Valet visar dem alla och låter de byggda väljas."""
    from vvs_engine import disciplines as disc
    return [d.out() for d in disc.registry().values()]


@app.patch("/api/projects/{project_id}/form")
def change_project_form(project_id: str, body: ProjectFormIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Byt entreprenadform eller disciplin i efterhand.

    Bytet kräver en bekräftelse: det ändrar hur nya blad i projektet läses, och den som byter ska ha sett det
    sagt. Läsningar som redan är gjorda ändras inte. Bytet skrivs i händelseloggen med vad det var och vad det blev."""
    p = _project(db, user, project_id)
    contract_form, discipline = _checked_modes(body.contract_form, body.discipline)
    before = {"contract_form": p.contract_form or "AB04", "discipline": _proj_out(p)["discipline"]}
    after = {"contract_form": contract_form or before["contract_form"], "discipline": discipline or before["discipline"]}
    if after == before:
        return _proj_out(p)
    if not body.confirm:
        raise HTTPException(409, "Bekräfta bytet: det gäller nya läsningar i projektet, gjorda läsningar ändras inte.")
    p.contract_form, p.discipline = after["contract_form"], after["discipline"]
    from .db import Event
    db.add(Event(user_id=user.id, session="server", name="projektlage", path=f"/projects/{p.id}",
                 meta={"before": before, "after": after}))
    db.commit()
    return _proj_out(p)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    return {**_proj_out(p), "drawings": [_drawing_out(d) for d in sorted(p.drawings, key=lambda d: d.created_at, reverse=True)]}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    for d in p.drawings:
        storage.delete_prefix(f"results/{d.id}")
        storage.delete_prefix(f"drawings/{d.id}")
    from .purge import purge_project
    purge_project(db, p)
    db.delete(p); db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- drawings
MAX_UPLOAD_BYTES = 200 * 1024 * 1024      # samma tak som docker/nginx.conf: client_max_body_size 200m


@app.post("/api/projects/{project_id}/drawings")
async def upload_drawing(project_id: str, file: UploadFile = File(...), discipline: str | None = Query(default=None),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    _, own_discipline = _checked_modes(None, discipline) if discipline else (None, None)
    from vvs_engine.raster import IMAGE_MAGIC, ImageTooLarge, image_to_pdf, is_image
    filename = os.path.basename(file.filename or "")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext != "pdf" and ext not in IMAGE_MAGIC:
        raise HTTPException(400, "Endast PDF-filer och bilder (PNG, JPG, TIFF) stöds")
    # Läs in filen bit för bit och sluta vid taket. `file.read()` rakt av drar hela filen in i minnet innan
    # någon tittat på storleken, och en tillräckligt stor fil tar då hela arbetaren med sig - ett tak som
    # prövas först när allt redan är läst är inget tak. Samma gräns som nginx sätter framför tjänsten.
    chunks, size = [], 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Filen är större än {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    if ext in IMAGE_MAGIC:
        # En bild av en ritning - ett foto, en skanning sparad som bild - blir en PDF med bilden som sida. Den läses
        # sedan ur bildpunkterna, och allt den ger står som att granska (vvs_engine/raster).
        if not is_image(data, filename):
            raise HTTPException(400, "Filen är inte en giltig bild")
        from starlette.concurrency import run_in_threadpool
        try:
            data, _ = await run_in_threadpool(image_to_pdf, data, filename)
        except ImageTooLarge as e:
            raise HTTPException(413, f"Bilden är för stor att läsas som ritning ({e}).")
        except Exception:
            raise HTTPException(400, "Bilden kunde inte läsas")
        filename = filename.rsplit(".", 1)[0] + ".pdf"
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Filen är inte en giltig PDF")
    import pymupdf
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
        # En lösenordsskyddad PDF går att öppna men inte att läsa. Släpps den igenom faller läsningen först på
        # jobbkön, långt från den som laddade upp den, och svaret blir "document closed or encrypted" i stället
        # för den enda mening som hjälper: ta bort skyddet och ladda upp igen.
        locked = bool(doc.needs_pass or doc.is_encrypted)
        n_pages = len(doc)
        doc.close()
    except Exception:
        raise HTTPException(400, "PDF-filen kunde inte läsas")
    if locked:
        raise HTTPException(400, "PDF-filen är lösenordsskyddad och går inte att läsa. Spara om den utan "
                                 "lösenord och ladda upp igen.")
    if not n_pages:
        raise HTTPException(400, "PDF-filen innehåller inga sidor")
    digest = hashlib.sha256(data).hexdigest()
    existing = db.query(Drawing).filter(Drawing.project_id == p.id, Drawing.sha256 == digest).first()
    if existing is not None:
        return {**_drawing_out(existing), "duplicate": True}
    d = Drawing(project_id=p.id, filename=filename, storage_key="", sha256=digest,
                size_bytes=len(data), n_pages=n_pages, discipline=own_discipline or "")
    db.add(d); db.flush()
    key = f"drawings/{d.id}/{d.filename}"
    import io
    storage.put(key, io.BytesIO(data))
    d.storage_key = key
    db.commit()
    return _drawing_out(d)


@app.get("/api/drawings/{drawing_id}")
def get_drawing(drawing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _drawing(db, user, drawing_id)
    return {**_drawing_out(d), "jobs": [_job_out(j) for j in sorted(d.jobs, key=lambda j: j.created_at, reverse=True)]}


@app.get("/api/drawings/{drawing_id}/file")
def drawing_file(drawing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _drawing(db, user, drawing_id)
    return FileResponse(storage.path(d.storage_key), media_type="application/pdf", filename=d.filename)


@app.get("/api/drawings/{drawing_id}/page-image")
def drawing_page_image(drawing_id: str, page: int = 0, x0: float = 0, y0: float = 0, x1: float = 0, y1: float = 0,
                       px: int = 4096, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A part of one page as a picture, in the sheet's own points: the floor the 3D model stands on.

    Drawn here, where it takes a second, rather than in the browser, where a heavy sheet held the page still
    for minutes while the model waited. The region is in the coordinates the reading works in (the page as
    shown); the longer side gets `px` pixels."""
    import pymupdf
    from fastapi.responses import Response
    d = _drawing(db, user, drawing_id)
    with pymupdf.open(storage.path(d.storage_key)) as doc:
        if not 0 <= page < doc.page_count:
            raise HTTPException(404, "Sidan finns inte")
        pg = doc[page]
        shown = pg.rect * pg.rotation_matrix
        want = pymupdf.Rect(x0, y0, x1, y1) if x1 > x0 and y1 > y0 else shown.normalize()
        z = max(64, min(int(px), 8192)) / max(want.width, want.height)
        # the picture covers exactly the region asked for; what lies off the page is paper-white
        out = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, round(want.width * z), round(want.height * z)), False)
        out.clear_with(255)
        part = want & shown.normalize()
        if not part.is_empty:
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z).prerotate(pg.rotation),
                                clip=(part * pg.derotation_matrix).normalize(), alpha=False)
            pix.set_origin(round((part.x0 - want.x0) * z), round((part.y0 - want.y0) * z))
            out.copy(pix, pix.irect)
        return Response(out.tobytes("jpg", jpg_quality=88), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.delete("/api/drawings/{drawing_id}")
def delete_drawing(drawing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _drawing(db, user, drawing_id)
    storage.delete_prefix(f"results/{d.id}"); storage.delete_prefix(f"drawings/{d.id}")
    from .purge import purge_drawing
    purge_drawing(db, d)
    db.delete(d); db.commit()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/live/session")
def live_session(job_id: str, language: Literal["sv", "en"] = "sv", user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = _job(db, user, job_id)
    if j.status != "COMPLETED":
        raise HTTPException(409, "Analysen är inte klar")
    from .live_agent import create_session
    from . import api_budget
    api_budget.require()
    try:
        result = create_session(language=language)
    except ValueError:
        raise HTTPException(503, "OpenAI-anslutning saknas") from None
    except Exception:
        # Provider errors can contain request details. Never forward credentials or raw bodies.
        raise HTTPException(502, "Röstanslutningen kunde inte startas. Kontrollera OpenAI-anslutningen.") from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/jobs/{job_id}/live/text")
def live_text(job_id: str, body: dict, language: Literal["sv", "en"] = "sv", user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    """Samtalsagenten i text, när webbläsarens röstanslutning inte går att öppna (brandvägg, ingen WebRTC)."""
    j = _job(db, user, job_id)
    if j.status != "COMPLETED":
        raise HTTPException(409, "Analysen är inte klar")
    from .live_agent import text_turn
    from . import api_budget
    api_budget.require()
    prev = body.get("previous_response_id")
    try:
        result = text_turn(body.get("input") or [], prev if isinstance(prev, str) else None, language=language)
    except ValueError:
        raise HTTPException(503, "OpenAI-anslutning saknas") from None
    except Exception:
        import logging; logging.getLogger("vvs.live").exception("Samtalsagentens textsvar misslyckades")
        raise HTTPException(502, "Agenten kunde inte svara. Försök igen.") from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.get("/api/analysis-options")
def analysis_options(user: User = Depends(current_user)):
    from vvs_engine.source_rules.styles import profiles
    from .source_model import connection_settings
    key, model = connection_settings()
    from . import ai_models, api_budget
    ready = ai_models.available()
    # the service's ceiling on what language models may cost: past it, every model but "none" is closed
    blocked = {c: api_budget.blocked(ai_models.model_id(c)) for c in ai_models.CHOICES if c != ai_models.NONE}
    exhausted = api_budget.blocked(None) is not None
    for c, why in blocked.items():
        if why:
            ready[c] = False
    return {"styles": [{"id": k, "name": p.get("name", k)} for k,p in profiles().items()],
            "model": {"configured": bool(key), "name": model},
            "ai_models": [{"id": c, "label": ai_models.LABELS[c], "available": ready[c],
                           "blocked": blocked.get(c)} for c in ai_models.CHOICES],
            "ai_default": ai_models.default(),
            "ai_budget_exhausted": exhausted}


# ---------------------------------------------------------------- analysis jobs
class AnalyzeIn(BaseModel):
    """Skalan någon skriver in för ett blad vars egen stämpel inte räckte: 1:50 skrivs som 50.

    Ett blad utan fastställd skala är omätt, inte omätbart - rören är lästa och deras längd i punkter är känd,
    det som saknas är hur många meter en punkt är. Den uppgiften kommer från den som har ritningen framför sig.
    Den går in i läsningen som ett besked från en person, inte från bladet, och ingen rad som vilar på den får
    heta bekräftad.
    """
    assignment_mode: Literal["combined", "dimension", "model", "compare"] = "combined"
    source_style: str = "auto"
    # vilken språkmodell som avgör rörens beteckningar - eller ingen, då ritningens egna belägg avgör
    ai_model: Literal["none", "gpt-6-astra", "gpt-6.1-sol", "claude-opus-5-5", "gemini-pro"] | None = None
    scale_ratio: float | None = Field(default=None, ge=1, le=20000, allow_inf_nan=False)
    page: int = Field(default=0, ge=0)


@app.post("/api/drawings/{drawing_id}/analyze")
def analyze(drawing_id: str, body: AnalyzeIn | None = None, user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    from vvs_engine.measure.scale import ratio_to_meters_per_pt
    d = _drawing(db, user, drawing_id)
    mode = "combined"  # Legacy clients also use the unified pipeline.
    style_id = body.source_style if body else "auto"
    from vvs_engine.source_rules.styles import profiles
    if style_id != "auto" and style_id not in profiles():
        raise HTTPException(422, "Okänd ritningsstil.")
    style_id = "auto"  # Style is inferred for every application analysis.
    from . import ai_models
    ai_model = (body.ai_model if body else None) or ai_models.default()
    if ai_model != ai_models.NONE:
        from . import api_budget
        why = api_budget.blocked(ai_models.model_id(ai_model))
        if why:
            raise HTTPException(402, f"{why} Välj Utan AI - analysen går lika bra utan.")
    if not ai_models.available().get(ai_model):
        raise HTTPException(422, f"{ai_models.LABELS[ai_model]} är inte ansluten på servern. Välj en annan modell eller Utan AI.")
    given: dict | None = None
    if body is not None and body.scale_ratio is not None:
        if body.page >= d.n_pages:
            raise HTTPException(422, "Det angivna bladet finns inte i ritningen.")
        given = {"ratio": body.scale_ratio, "page": body.page,
                 "meters_per_pdf_point": ratio_to_meters_per_pt(body.scale_ratio)}
    active = (db.query(AnalysisJob).filter(AnalysisJob.drawing_id == d.id,
              AnalysisJob.status.notin_(["COMPLETED", "FAILED"]))
              .order_by(AnalysisJob.created_at.desc()).first())
    if active is not None:
        if (active.summary or {}).get("source_style", "auto") != style_id:
            raise HTTPException(409, "Ritningen analyseras redan med en annan ritningsstil.")
        if (active.summary or {}).get("assignment_mode", "dimension") != mode:
            raise HTTPException(409, "Ritningen analyseras redan med ett annat analysläge. Vänta tills den analysen är klar.")
        if (active.summary or {}).get("ai_model", ai_models.NONE) != ai_model:
            raise HTTPException(409, "Ritningen analyseras redan med en annan AI-modell. Vänta tills den analysen är klar.")
        if ((active.summary or {}).get("given_scale") or None) != given:
            raise HTTPException(409, "Ritningen analyseras redan. Vänta tills den analysen är klar innan skalan ändras.")
        return _job_out(active)
    # the discipline the drawing is read in: its own, else its project's - and only one that is built
    from vvs_engine import disciplines as disc
    discipline = disc.normalize(d.discipline or d.project.discipline)
    if not disc.selectable(discipline):
        raise HTTPException(409, f"{disc.get(discipline).name if disc.known(discipline) else discipline} är inte byggd än.")
    j = AnalysisJob(drawing_id=d.id, status="QUEUED", stage="QUEUED", progress=0.0, discipline=discipline,
                    summary={"given_scale": given, "assignment_mode": mode, "source_style": style_id,
                             "ai_model": ai_model})
    db.add(j); db.flush()
    # priset dras innan läsningen startar, och det som drogs står på jobbet; räcker inte saldot skapas inget jobb
    charged = credits_api.charge_for_reading(db, user, d, j)
    if charged:
        j.summary = {**(j.summary or {}), "credits": charged}
    db.commit()
    jobs.submit(j.id)
    return _job_out(j)


def _reading_engine(j: AnalysisJob) -> dict | None:
    """Vilken motor som läste - och om den är en annan än den som svarar nu.

    Ett resultat är en läsning gjord av en viss motor, och en läsning görs en gång. Motorn står inte stilla: ett
    blad som lästes i våras är inte det blad samma ritning ger idag, och den som tittar på det gamla svaret ska
    slippa undra varför siffran skiljer sig från kollegans. Läsningen skriver sin källa i sitt frysprotokoll, så
    frågan går att besvara utan att gissa - och svaret är inte "fel siffra", det är "läst med en äldre motor".
    """
    if j.status != "COMPLETED" or not j.result_key:
        return None
    try:
        with open(os.path.join(storage.path(j.result_key), "freeze-manifest.json"), encoding="utf-8") as fh:
            man = json.load(fh)
    except (OSError, ValueError):
        return None
    read_with = (man.get("source_revision") or "").strip()
    now = _build_stamp().get("build") or ""
    known = bool(read_with) and read_with.lower() != "unknown" and bool(now) and now.lower() != "unknown"
    from vvs_engine.build import engine_digest
    saved_digest = man.get("engine_source_sha256")
    source_changed = (saved_digest != engine_digest()) if saved_digest else None
    return {"last_med": read_with[:12] or None, "nu": now or None, "motorversion": man.get("engine_version"),
            "last": man.get("created"), "source_changed": source_changed,
            # samma källa = samma svar; olika källa säger bara att de kan skilja sig, inte att någon är fel
            "foraldrad": bool(source_changed if source_changed is not None else
                              (known and not read_with.startswith(now) and not now.startswith(read_with[:12])))}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = _job(db, user, job_id)
    out = _job_out(j)
    motor = _reading_engine(j)
    if motor:
        out["motor"] = motor
    return out


def _proposals(db: Session, user: User, anchors: list, pipes: list, geom: list) -> list[dict]:
    """What this account's earlier corrections would say about the cases this reading could not settle.

    Proposals, never decisions. A lesson may speak only where the engine itself called the case ambiguous and
    only when the answer is among the candidates the drawing offers; accepting one is a correction a person
    makes, recorded like any other, so the takeoff never moves on a lesson alone.
    """
    open_cases = [a for a in anchors if a["state"] == "AMBIGUOUS_PIPE_ATTACHMENT"]
    if not open_cases:
        return []
    mine = (db.query(Correction).join(Drawing, Correction.drawing_id == Drawing.id)
            .join(Project, Drawing.project_id == Project.id)
            .filter(Project.owner_id == user.id, Correction.undone == False).all())  # noqa: E712
    taught = lessons([_correction_out(c) for c in mine])
    if not taught:
        return []
    fam_of = {}
    for p in pipes:
        fam_of[(p.get("identity") or "").replace("|DN", "-").upper()] = p.get("family", "")
    cases = []
    for a in open_cases:
        name = (a.get("designation") or "").upper()
        cands = _candidates_of(a, geom) or [name]
        cases.append({"id": a["anchor_id"], "designation": a.get("designation"),
                      "situation": situation(**_case_shape(a, fam_of.get(name, "")), candidates=cands),
                      "candidates": cands})
    return settle(cases, taught)


def _candidates_of(anchor: dict, geom: list) -> list[str]:
    """The answers the drawing itself puts forward for an unresolved case.

    An ambiguous anchor points at geometry the reading could not give to one identity, and that geometry carries
    the identities that were still in play. Those are the candidates - not a list of every designation on the
    sheet, and not the anchor's own name, which would let a lesson only ever agree with the reading.
    """
    touched = {(c.get("pid"), c.get("seg_index")) for c in (anchor.get("contacts") or [])}
    if not touched:
        return []
    out: set[str] = set()
    for g in geom:
        if g.get("state") != "AMBIGUOUS":
            continue
        if (g.get("pid"), g.get("seg")) not in touched:
            continue
        for c in g.get("candidates") or []:
            out.add(str(c).replace("|DN", "-").upper())
    return sorted(out)


def _case_shape(anchor: dict, family: str) -> dict:
    """Everything about an unresolved case that a later reading could recognise it by, read off the anchor.

    The leader family is how this drawing draws the line that reached the label; the counts are the local shape
    of the junction - label rows in the block, compatible groups at the leader end, pieces of geometry actually
    touched. All of it comes from the reading, none of it from the browser.
    """
    ev = anchor.get("evidence") or {}
    return {"family": family, "reason": anchor.get("reason", ""),
            "designation": anchor.get("designation") or "",
            "leader_family": ev.get("leader_family") or "",
            "n_rows": ev.get("n_rows"), "n_groups": ev.get("n_groups"),
            "n_contacts": len(anchor.get("contacts") or [])}


def _situation_of(db: Session, user: User, job_id: str | None, designation: str | None) -> dict:
    """The case a correction was made in, taken from the reading rather than from the browser.

    The pen the run was drawn with and the reason the engine gave are what make this case what it is, and both
    are in the result. Where they cannot be read the situation stays empty, which means the correction applies
    to this drawing and teaches nothing - the honest outcome when we cannot say what the case was.
    """
    if not job_id or not designation:
        return {}
    try:
        j = _job(db, user, job_id)
        rd = _result_dir(j)
        pipes = _load(rd, "physical-pipes.json")["physical_pipes"]
        anchors = _load(rd, "pipe-code-anchors.json")["anchors"]
        geom = _load(rd, "pipe-geometry-inventory.json")["primitives"]
    except Exception:
        return {}
    want = designation.upper()
    family = next((p.get("family", "") for p in pipes
                   if (p.get("identity") or "").replace("|DN", "-").upper() == want), "")
    case = next((a for a in anchors
                 if (a.get("designation") or "").upper() in (want, want.rsplit("-", 1)[0])
                 and a.get("state") != "VERIFIED_PIPE_ATTACHMENT"), None)
    if case is None:
        # nothing in the reading was unresolved for this designation: the correction is about this drawing only
        return {}
    cands = _candidates_of(case, geom) or [want]
    return situation(**_case_shape(case, family), candidates=cands)


def _is_our_proposal(db: Session, user: User, job_id: str | None, sit: dict) -> bool:
    """Whether this fingerprint is one this reading actually put forward, rather than one a caller made up.

    Accepting a proposal is the only way a situation may arrive from outside, so it is checked against the
    proposals this job offers right now, computed here rather than trusted from the request.
    """
    if not job_id or not isinstance(sit, dict):
        return False
    try:
        j = _job(db, user, job_id)
        rd = _result_dir(j)
        anchors = _load(rd, "pipe-code-anchors.json")["anchors"]
        pipes = _load(rd, "physical-pipes.json")["physical_pipes"]
        geom = _load(rd, "pipe-geometry-inventory.json")["primitives"]
    except Exception:
        return False
    want = {k: sit.get(k) for k in KEYS}
    return any(p.get("situation") == want for p in _proposals(db, user, anchors, pipes, geom))


class CorrectionIn(BaseModel):
    kind: str
    designation: str | None = None
    page: int = 0
    payload: dict = {}
    situation: dict = {}
    note: str | None = None
    job_id: str | None = None


def _correction_out(c: Correction) -> dict:
    return {"id": c.id, "drawing_id": c.drawing_id, "job_id": c.job_id, "page": c.page, "kind": c.kind,
            "designation": c.designation, "payload": c.payload, "situation": c.situation, "note": c.note,
            "undone": c.undone, "created_at": c.created_at.isoformat()}


@app.get("/api/drawings/{drawing_id}/corrections")
def list_corrections(drawing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _drawing(db, user, drawing_id)
    rows = db.query(Correction).filter(Correction.drawing_id == drawing_id).order_by(Correction.created_at).all()
    return [_correction_out(c) for c in rows]


@app.post("/api/drawings/{drawing_id}/corrections")
def add_correction(drawing_id: str, body: CorrectionIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    _drawing(db, user, drawing_id)
    if body.kind not in CORRECTION_KINDS:
        raise HTTPException(400, f"Okänd rättelsetyp: {body.kind}")
    # The situation always comes from the reading, never from the caller: what a lesson may be shown to apply to
    # is a fact about the drawing, and a caller who could supply one could forge a fingerprint, post it twice and
    # have it settle real cases on someone else's later drawing. The only situation that may arrive from outside
    # is one this server itself put forward, and it is taken only when it matches a live proposal exactly.
    sit = _situation_of(db, user, body.job_id, body.designation)
    if not sit and body.situation:
        sit = body.situation if _is_our_proposal(db, user, body.job_id, body.situation) else {}
    c = Correction(drawing_id=drawing_id, job_id=body.job_id, user_id=user.id, page=body.page, kind=body.kind,
                   designation=body.designation, payload=body.payload, situation=sit, note=body.note)
    db.add(c); db.commit()
    return _correction_out(c)


class CorrectionShape(BaseModel):
    points: list[list[float]]
    meters: float | None = None


@app.put("/api/drawings/{drawing_id}/corrections/{correction_id}/shape")
def reshape_correction(drawing_id: str, correction_id: str, body: CorrectionShape, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """A drawn correction bent to follow the pipe: its points and the metres they measure, nothing else.

    What the correction is - its kind, its designation, the situation it was made in - stays as it was filed. The
    shape it had before is kept beside the new one, so what was changed can be seen."""
    _drawing(db, user, drawing_id)
    c = db.get(Correction, correction_id)
    if c is None or c.drawing_id != drawing_id:
        raise HTTPException(404, "Rättelsen finns inte")
    if c.undone:
        raise HTTPException(409, "En ångrad rättelse går inte att ändra")
    if c.kind not in ("extend", "draw") or len(body.points) < 2 or any(len(q) < 2 for q in body.points):
        raise HTTPException(400, "Bara ett ritat streck med minst två punkter kan böjas")
    payload = dict(c.payload or {})
    earlier = list(payload.get("earlier_shapes") or [])
    if payload.get("points"):
        earlier.append({"points": payload.get("points"), "meters": payload.get("meters")})
    payload.update({"points": [[float(q[0]), float(q[1])] for q in body.points], "earlier_shapes": earlier[-10:]})
    if body.meters is not None:
        payload["meters"] = round(float(body.meters), 3)
    else:
        payload.pop("meters", None)       # measured from the points and the sheet's scale when applied
    c.payload = payload
    db.commit()
    return _correction_out(c)


@app.delete("/api/drawings/{drawing_id}/corrections/{correction_id}")
def undo_correction(drawing_id: str, correction_id: str, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    _drawing(db, user, drawing_id)
    c = db.get(Correction, correction_id)
    if c is None or c.drawing_id != drawing_id:
        raise HTTPException(404, "Rättelsen finns inte")
    # kept rather than deleted: what a person changed and then changed back is itself worth having
    c.undone = True
    # a correction a learned rule made, undone by a person: counted against the rule, which switches itself off
    # when people undo too much of what it does
    from .learned_rules import on_undone
    on_undone(db, c)
    db.commit()
    return _correction_out(c)


_MATERIAL: dict | None = None


def _material() -> dict:
    """Materialboken, läst en gång.

    Femtiofemtusen artiklar är för många att skicka till en webbläsare och för få att förtjäna en databas. Den
    ligger som en komprimerad fil bredvid koden, läses in vid första frågan och stannar - sökningen sker här,
    och bara det som frågades efter går över tråden.
    """
    global _MATERIAL
    if _MATERIAL is None:
        import gzip
        path = os.path.join(os.path.dirname(__file__), "data", "material.json.gz")
        if not os.path.exists(path):
            _MATERIAL = {"n": 0, "rows": [], "source": None}
        else:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                _MATERIAL = json.load(fh)
    return _MATERIAL


@app.get("/api/materials")
def materials(q: str = "", group: str = "", unit: str = "", limit: int = 60, offset: int = 0,
              user: User = Depends(current_user)):
    """Artiklar ur materialboken, sökta på benämning eller artikelnummer.

    Varje ord i frågan måste finnas i raden, i vilken ordning som helst: "110 pp mark" hittar markrör i PP av
    dimension 110 utan att någon behöver veta hur leverantören stavar sin benämning.
    """
    book = _material()
    rows = book["rows"]
    words = [w for w in (q or "").lower().split() if w]
    if group:
        rows = [r for r in rows if r.get("gr") == group]
    if unit:
        rows = [r for r in rows if (r.get("e") or "").lower() == unit.lower()]
    if words:
        rows = [r for r in rows if all(w in f'{r["n"]} {r["a"]}'.lower() for w in words)]
    limit = max(1, min(int(limit), 300))
    return {"total": len(rows), "offset": offset, "limit": limit,
            "rows": rows[offset:offset + limit],
            "book": {"n": book["n"], "source": book.get("source")},
            "units": sorted({(r.get("e") or "") for r in book["rows"] if r.get("e")})[:24],
            "groups": sorted({(r.get("gr") or "") for r in book["rows"] if r.get("gr")})[:60]}


# A riser is one storey, 2.8 m, until the service or the reader says otherwise: every reference takeoff measured
# (W-50-1-A-0033, -0111, -0114 and the rest) counts each riser at 2.80 m, and a vertical column left UNKNOWN
# dropped the risers the reading had found - ten of ten on -0033 - out of the total.
ASSUMPTION_DEFAULTS = {"floor_height_m": 2.8, "riser_source": "symbols", "include_hatched": False,
                       "include_declared": True}

# Vad läsningen kör, till skillnad från vad den antar. De två OCR-passen kostar tid och är mätta: se
# `Settings.review_ocr` och `Settings.ocr_assist` för siffrorna. Standarden kommer ur installationens miljö;
# den som sätts här gäller för tjänsten och kan ändras utan att något behöver läggas om.
RUN_KEYS = ("review_ocr", "ocr_assist")


def service_rules(db: Session) -> dict[str, float | bool]:
    """Reglerna som flyttats för tjänsten: regel-id -> värde."""
    out = {}
    for row in db.query(ServiceSetting).filter(ServiceSetting.key.like("rule:%")).all():
        out[row.key[5:]] = (row.value or {}).get("v")
    return out


@app.get("/api/rules")
def rules_catalogue(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Every rule the reading follows, what it decides, and what it stands at for this service.

    A takeoff nobody can question is not evidence. The engine's limits are all written down where they are used,
    which serves whoever reads the code and nobody else - so they are served here too, in the words of the
    drawing, together with what each one has been moved to and why. Anyone signed in may read them; moving one
    is the administrator's, since a moved rule holds for every drawing the service reads next.
    """
    from vvs_engine import rules as R
    rows = {r.key[5:]: r for r in db.query(ServiceSetting).filter(ServiceSetting.key.like("rule:%")).all()}
    cat = R.catalogue({k: (v.value or {}).get("v") for k, v in rows.items()})
    for g in cat["groups"]:
        for row in g["rules"]:
            st = rows.get(row["id"])
            row["changed"] = st is not None
            row["note"] = st.note if st else None
            row["shot"] = st.shot if st else None
            row["changed_at"] = st.updated_at.isoformat() if st and st.updated_at else None
    cat["n_changed"] = len(rows)
    cat["may_edit"] = (user.role or "member") == "admin"
    return cat


@app.put("/api/rules/{rule_id:path}")
def set_rule(rule_id: str, body: dict, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Move one rule for the service, or put it back.

    A value outside what the rule can mean is refused rather than clamped: a limit silently rewritten is a limit
    nobody can reason about afterwards. Rules the code does not let anyone move are refused with the reason.
    """
    from vvs_engine import rules as R
    rule = R.BY_ID.get(rule_id)
    if rule is None:
        raise HTTPException(404, "okänd regel")
    if not rule.tunable:
        raise HTTPException(400, rule.fixed_why or "regeln går inte att ändra")
    key = f"rule:{rule_id}"
    row = db.get(ServiceSetting, key)
    if body.get("reset"):
        if row:
            db.delete(row); db.commit()
        return {"id": rule_id, "value": rule.default, "changed": False}
    v = body.get("value")
    if isinstance(rule.default, bool):
        v = bool(v)
    else:
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise HTTPException(400, "värdet är inget tal")
        if rule.lo is not None and v < rule.lo or rule.hi is not None and v > rule.hi:
            raise HTTPException(400, f"värdet ligger utanför vad regeln kan betyda ({rule.lo}–{rule.hi})")
    shot = body.get("shot")
    if shot and (not isinstance(shot, str) or not shot.startswith("data:image/") or len(shot) > 4_000_000):
        raise HTTPException(400, "skärmbilden måste vara en bild och under 4 MB")
    if row is None:
        row = ServiceSetting(key=key, value={"v": v})
        db.add(row)
    row.value = {"v": v}
    row.note = (body.get("note") or None)
    row.updated_by = admin.id
    if shot is not None:
        row.shot = shot or None
    db.commit()
    return {"id": rule_id, "value": v, "changed": True, "note": row.note, "shot": bool(row.shot)}


@app.get("/api/settings")
def read_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Antagandena mängden räknas ihop med: våningshöjd för stigare, var stigare räknas ifrån, om rör i
    skrafferade ytor ingår. Satta av administratören för tjänsten; varje läsning kan avvika i sin egen vy."""
    out = dict(ASSUMPTION_DEFAULTS)
    for row in db.query(ServiceSetting).filter(ServiceSetting.key.like("assume:%")).all():
        out[row.key[7:]] = (row.value or {}).get("v")
    for k in RUN_KEYS:
        out[k] = run_setting(db, k)
    out["may_edit"] = (user.role or "member") == "admin"
    return out


def run_setting(db: Session, key: str) -> bool:
    """Vad tjänsten kör, med installationens miljö som utgångsläge."""
    row = db.get(ServiceSetting, f"run:{key}")
    if row is not None and isinstance(row.value, dict) and "v" in row.value:
        return bool(row.value["v"])
    return bool(getattr(settings, key))


@app.put("/api/settings")
def write_settings(body: dict, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Ändra antagandena för tjänsten. Ett värde utanför vad det kan betyda avvisas, aldrig klipps."""
    clean: dict[str, object] = {}
    if "floor_height_m" in body:
        v = body["floor_height_m"]
        if v in (None, "", 0):
            clean["floor_height_m"] = None
        else:
            try:
                v = float(str(v).replace(",", "."))
            except ValueError:
                raise HTTPException(400, "våningshöjden är inget tal")
            if not 1.0 <= v <= 8.0:
                raise HTTPException(400, "våningshöjden ska ligga mellan 1 och 8 m")
            clean["floor_height_m"] = v
    if "riser_source" in body:
        if body["riser_source"] not in ("labels", "symbols"):
            raise HTTPException(400, "stigare räknas från etiketter eller symboler")
        clean["riser_source"] = body["riser_source"]
    if "include_hatched" in body:
        clean["include_hatched"] = bool(body["include_hatched"])
    if "include_declared" in body:
        clean["include_declared"] = bool(body["include_declared"])
    for k in RUN_KEYS:
        if k in body:
            row = db.get(ServiceSetting, f"run:{k}")
            if row is None:
                row = ServiceSetting(key=f"run:{k}", value={"v": bool(body[k])})
                db.add(row)
            row.value = {"v": bool(body[k])}
            row.updated_by = admin.id
    for k, v in clean.items():
        row = db.get(ServiceSetting, f"assume:{k}")
        if row is None:
            row = ServiceSetting(key=f"assume:{k}", value={"v": v})
            db.add(row)
        row.value = {"v": v}
        row.updated_by = admin.id
    db.commit()
    return read_settings(admin, db)


@app.get("/api/lessons")
def my_lessons(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What this account's corrections have taught, and how often each answer was given.

    A lesson never measures anything on its own; it can only settle a case the engine already called ambiguous,
    and only where the pen, the reason and the shape of the name are the same.
    """
    mine = (db.query(Correction).join(Drawing, Correction.drawing_id == Drawing.id)
            .join(Project, Drawing.project_id == Project.id).filter(Project.owner_id == user.id).all())
    return {"lessons": lessons([_correction_out(c) for c in mine]), "corrections": len(mine)}


@app.get("/api/jobs/{job_id}/film")
def job_film(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What each stage of the reading found, as far as it has got. Available while the job is still running."""
    j = _job(db, user, job_id)
    if not j.result_key:
        return {"frames": []}
    path = os.path.join(storage.path(j.result_key), "film.json")
    if not os.path.exists(path):
        return {"frames": []}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"frames": []}          # a frame caught mid-write; the next poll gets it


def _result_dir(j: AnalysisJob) -> str:
    if j.status != "COMPLETED" or not j.result_key:
        raise HTTPException(409, "Analysen är inte klar")
    return storage.path(j.result_key)


ARTIFACTS = ["reference-comparison.json", "label-audit-status.json", "label-audit.json", "drawing-style.json", "pdf-visibility.json", "drawing-profile.json", "drawing-profile-report.md", "raw-vector-inventory.json", "cad-layer-map.json", "vector-designations.json",
             "all-designations.json",
             "drawing-legend.json", "ocr-assisted-characters.json",
             "designation-overlay.pdf", "leader-forensics.json", "leader-family-report.json", "pipe-code-anchors.json",
             "endpoint-pipe-attachment-overlay.pdf", "pipe-representation-families.json", "pipe-geometry-inventory.json", "declined-geometry.json", "pipe-topology.json",
             "physical-pipes.json", "pipe-extent-frontiers.json", "frontier-overlay.pdf", "coverage-validity.json", "drawing-declarations.json",
             "quantities.json", "unresolved-issues.json", "evidence-graph.json", "reconciliation.json",
             "route-crosscheck.json", "reading-review.json", "determinism.json",
             "contamination-report.json", "performance-report.json", "production-overlay.pdf", "topology-overlay.pdf", "ambiguous-overlay.pdf",
             "unsupported-style-overlay.pdf", "analysis-report.md", "freeze-manifest.json", "summary.json"]


def _load(rd: str, name: str):
    p = os.path.join(rd, name)
    if not os.path.exists(p):
        raise HTTPException(404, f"Artefakten saknas: {name}")
    with open(p, "r", encoding="utf-8") as fh:
        # ett resultat räknat med en äldre motor läses som dagens: fält som inte fanns då är tomma, inte fel
        return upgrade(name, json.load(fh))


def _sheet_dir(rd: str, page: int) -> str:
    """Where the reading of one sheet was written down, or the result root for a reading that has only one.

    A set of drawings is read sheet by sheet and each sheet written down as it is read, under sheets/<page>/.
    Older readings - made before the sheets were kept apart - have only the root, which holds the first sheet.
    Falling back to it is right for a single-sheet drawing and honest for an old multi-sheet one: the reader gets
    what was actually written down rather than an error about a directory.
    """
    d = os.path.join(rd, "sheets", str(int(page)))
    return d if os.path.isdir(d) else rd


def _sheet_pages(rd: str) -> list[int]:
    d = os.path.join(rd, "sheets")
    if not os.path.isdir(d):
        return []
    return sorted(int(n) for n in os.listdir(d) if n.isdigit())


class ConfirmIn(BaseModel):
    page: int = 0


def _confirmed_out(ct) -> dict | None:
    if ct is None:
        return None
    return {"id": ct.id, "page": ct.page, "created_at": ct.created_at.isoformat(), "rows": ct.rows,
            "total_m": round(sum(float(v) for v in (ct.rows or {}).values()), 2)}


@app.post("/api/jobs/{job_id}/kontrollerad")
def confirm_takeoff(job_id: str, body: ConfirmIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Den som äger ritningen säger att mängden på bladet stämmer: den rättade mängden sparas som facit.

    Det är de bladen de lärda reglerna prövas mot innan någon av dem får läsa en annan kunds ritning. Därför sparas
    mängden som den ser ut nu, med alla rättelser, och inte en hänvisning till den: en regel ska mätas mot det som
    personen godkände, inte mot det som råkar stå där senare."""
    from .db import ConfirmedTakeoff
    j = _job(db, user, job_id)
    root = _result_dir(j)
    pages = _sheet_pages(root)
    if pages and body.page not in pages:
        raise HTTPException(404, "Det valda bladet har inget analysresultat.")
    rd = _sheet_dir(root, body.page)
    quantities = _load(rd, "quantities.json")
    mpp = quantities["scale"].get("meters_per_pdf_point")
    corr = [_correction_out(c) for c in db.query(Correction).filter(
        Correction.drawing_id == j.drawing_id, Correction.undone == False).all()  # noqa: E712
        if c.page in (None, body.page)]
    rows = apply_corrections(quantities["rows"], corr, mpp)["quantities"] if corr else quantities["rows"]
    snap: dict[str, float] = {}
    for r in rows:
        name = r.get("designation")
        if name:
            snap[name] = round(snap.get(name, 0.0) + float(r.get("confirmed_horizontal_m") or 0.0), 3)
    if not mpp and not any(snap.values()):
        raise HTTPException(409, "Bladet har ingen skala och inga meter; det finns ingen mängd att bekräfta.")
    for old in db.query(ConfirmedTakeoff).filter(ConfirmedTakeoff.drawing_id == j.drawing_id,
                                                 ConfirmedTakeoff.page == body.page,
                                                 ConfirmedTakeoff.withdrawn == False).all():  # noqa: E712
        old.withdrawn = True
    ct = ConfirmedTakeoff(job_id=j.id, drawing_id=j.drawing_id, page=body.page, user_id=user.id, rows=snap)
    db.add(ct)
    db.commit()
    # a new checked sheet is a new test for every rule that is waiting or in use
    from .db import LearnedRule
    from .jobs import submit_rule_gate
    for rid, in db.query(LearnedRule.id).filter(LearnedRule.state.in_(("kandidat", "klarat_sparren", "aktiv"))).all():
        submit_rule_gate(rid)
    return _confirmed_out(ct)


@app.delete("/api/jobs/{job_id}/kontrollerad")
def withdraw_confirmed(job_id: str, page: int = Query(default=0, ge=0), user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    from .db import ConfirmedTakeoff
    j = _job(db, user, job_id)
    for ct in db.query(ConfirmedTakeoff).filter(ConfirmedTakeoff.drawing_id == j.drawing_id,
                                                ConfirmedTakeoff.page == page,
                                                ConfirmedTakeoff.withdrawn == False).all():  # noqa: E712
        ct.withdrawn = True
    db.commit()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str, page: int | None = Query(default=None, ge=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The reading, as the sheet the reader is looking at plus the takeoff for the whole set.

    `page` picks the sheet. Everything drawn on the drawing - the pipes, the labels, the leaders, the ink that
    was declined - is a fact about one sheet and comes from that sheet's own reading. The quantity rows are the
    set's: a designation drawn on four sheets is one row, and the sheets it stands on are named on it. Serving
    the first sheet's rows for a twenty-six sheet set is how a reading of four hundred metres shows up as an
    empty table.
    """
    j = _job(db, user, job_id)
    root = _result_dir(j)
    pages = _sheet_pages(root)
    if page is None:
        page = pages[0] if pages else 0
    elif pages and page not in pages:
        raise HTTPException(404, "Det valda bladet har inget analysresultat.")
    rd = _sheet_dir(root, page)
    page_no = page
    review = _load_optional(root, "review-findings.json") if page == (pages[0] if pages else 0) else None
    quantities = _load(rd, "quantities.json")
    pipes = _load(rd, "physical-pipes.json")["physical_pipes"]
    # what the reading measured for review: drawn on the sheet with the review mark, alongside the reading's own
    review_pipes = (_load_optional(rd, "review-pipes.json") or {}).get("review_pipes") or []
    issues = _load(rd, "unresolved-issues.json")["issues"]
    prof = _load(root, "drawing-profile.json")
    rec = _load(rd, "reconciliation.json")
    perf = _load(root, "performance-report.json")
    summary = _load(root, "summary.json")
    anchors = _load(rd, "pipe-code-anchors.json")["anchors"]
    des = _load(rd, "vector-designations.json")["designations"]
    leaders = _load(rd, "leader-forensics.json")["leaders"]
    geom = _load(rd, "pipe-geometry-inventory.json")["primitives"]
    declined = _load_optional(rd, "declined-geometry.json") or {"families": [], "totals": {}, "drawn_twice": {}}
    # A line a label's leader actually reaches but no identity could take. It is not measured and it is not
    # hidden: filing it with the ink nobody mentioned is how a drawn, labelled pipe disappears off the sheet.
    claimed = [g for g in geom if g["state"] == "UNOWNED" and g.get("claimed_by")]
    unowned = [g for g in geom if g["state"] == "UNOWNED" and not g.get("claimed_by")]
    ambiguous = [g for g in geom if g["state"] == "AMBIGUOUS"]
    hatched = [g for g in geom if g["state"] == "CONFIRMED" and g.get("in_hatch")]
    mpp = quantities["scale"].get("meters_per_pdf_point")
    # the sheet in front of the reader, not whichever sheet the set-wide profile was built from
    page = _load_optional(rd, "page.json") or prof["page_structure"]
    # what a person changed is layered over the reading, never into it: the engine's own figure stays on every row
    corr = [_correction_out(c) for c in
            db.query(Correction).filter(Correction.drawing_id == j.drawing_id, Correction.undone == False).all()]  # noqa: E712
    layered = apply_corrections(quantities["rows"], corr, mpp)
    rows = layered["quantities"] if corr else quantities["rows"]
    from .db import ConfirmedTakeoff
    confirmed = (db.query(ConfirmedTakeoff).filter(ConfirmedTakeoff.drawing_id == j.drawing_id,
                                                   ConfirmedTakeoff.page == (page_no if page_no is not None else 0),
                                                   ConfirmedTakeoff.withdrawn == False)  # noqa: E712
                 .order_by(ConfirmedTakeoff.created_at.desc()).first())
    return {
        "job": _job_out(j), "page": page, "input": prof.get("input"), "scale": quantities["scale"], "quantities": rows, "totals": quantities["totals"],
        "confirmed": _confirmed_out(confirmed),
        "corrections": corr,
        "drawing_style": _load_optional(rd, "drawing-style.json"),
        "quality": completion_checks(_load_optional(rd, "coverage-validity.json"), rows,
            _load_optional(rd, "source-assignment.json"), review),
        "reference_comparison": _load_optional(root, "reference-comparison.json"),
        "declarations": _load_optional(rd, "drawing-declarations.json"),
        "label_audit": _load_optional(root, "label-audit-status.json"),
        "pdf_visibility": {k:v for k,v in (_load_optional(rd, "pdf-visibility.json") or {}).items()
                           if k not in ("removed", "blank_text_spans")},
        "corrections_applied": layered["applied"] if corr else [],
        "corrected_total_m": layered["corrected_total_m"] if corr else None,
        "pipes": [{k: v for k, v in p.items() if k not in ("source_segments",)} for p in pipes]
                 + [{**{k: v for k, v in p.items() if k not in ("source_segments",)}, "needs_review": True,
                     "for_review": True} for p in review_pipes],
        # in_wall: the mark sits inside a hatched area, and pipe length in a wall is already outside the
        # horizontal quantity - so a mark drawn there points at something the takeoff does not count.
        # names_a_pipe: false for a component tag, whose leader reaches a floor drain or a mixer, not a run.
        "designations": [{"id": d["did"], "text": d["text"], "dn": d["dn"], "bbox": d["bbox"], "source": d["source"],
                          "in_wall": d.get("in_wall", False), "names_a_pipe": d.get("names_a_pipe", True)} for d in des],
        "leaders": [{"id": l["lid"], "points": l["points"], "family": l["family"], "in_wall": l.get("in_wall", False)} for l in leaders],
        # the detector's own labels (a pipe names them native_label_<id>): where each sits and its leaders
        "native_labels": ((_load_optional(rd, "source-assignment.json") or {}).get("native_detection") or {}).get("labels") or [],
        "anchors": [{"id": a["anchor_id"], "designation": a["designation"], "dn": a["dn"], "state": a["state"], "reason": a["reason"],
                     # which label box and which leader line this connection is: the viewer paints both in the
                     # colour of the pipe the label names, so a reader can follow label -> leader -> pipe by eye
                     "designation_id": a.get("designation_id"), "leader_id": a.get("leader_id"),
                     # a connection the detector made: the label it came from, as a pipe names it
                     "native_label": a["block_id"] if str(a.get("block_id") or "").startswith("native_label_") else None,
                     "display": a.get("designation_display"),
                     "endpoint": a["leader_endpoint"], "in_wall": a.get("in_wall", False),
                     "names_a_pipe": a.get("names_a_pipe", True)} for a in anchors],
        "ambiguous_geometry": [{"x0": g["x0"], "y0": g["y0"], "x1": g["x1"], "y1": g["y1"], "candidates": g["candidates"], "reason": g["reason"]} for g in ambiguous],
        "unowned_geometry": [{"x0": g["x0"], "y0": g["y0"], "x1": g["x1"], "y1": g["y1"], "family": g["family"]} for g in unowned],
        "claimed_geometry": [{"x0": g["x0"], "y0": g["y0"], "x1": g["x1"], "y1": g["y1"], "claimed_by": g["claimed_by"]} for g in claimed],
        "hatched_geometry": [{"x0": g["x0"], "y0": g["y0"], "x1": g["x1"], "y1": g["y1"], "identity": g["identity"]} for g in hatched],
        # Ink the reading looked at and decided was not pipe. Without it a declined wall and a missed run look
        # the same on the sheet - both are simply grey - and the reader has no way to tell which one they see.
        "declined_geometry": declined,
        "issues": issues,
        "proposals": _proposals(db, user, anchors, pipes, geom),
        "build": _build_stamp(),
        "coverage": {
            "designations": len(des), "with_dn": sum(1 for d in des if d["dn"] is not None), "leaders": len(leaders),
            "verified_attachments": sum(1 for a in anchors if a["state"] == "VERIFIED_PIPE_ATTACHMENT"),
            "ambiguous_attachments": sum(1 for a in anchors if a["state"] == "AMBIGUOUS_PIPE_ATTACHMENT"),
            "no_attachments": sum(1 for a in anchors if a["state"] == "NO_PIPE_ATTACHMENT"),
            "physical_pipes": len(pipes),
            "unowned_m": round(rec["unowned_pt"] * mpp, 2) if mpp else None,
            "unowned_outside_hatch_m": round(sum(g["length"] for g in geom if g["state"] == "UNOWNED" and not g.get("in_hatch")) * mpp, 2) if mpp else None,
            "unowned_in_hatch_m": round(sum(g["length"] for g in geom if g["state"] == "UNOWNED" and g.get("in_hatch")) * mpp, 2) if mpp else None, "ambiguous_m": quantities["totals"]["ambiguous_m"],
            # how much drawn pipe a label reaches without the reading being able to name it: the size of what is
            # shown but not counted, which is the one number that says how much a sheet is actually missing
            "claimed_m": round(sum(g["length"] for g in claimed) * mpp, 2) if mpp else None,
            "unsupported_families": len(prof["unknown_structure"]["unsupported_families"]),
            "reconciliation": rec["state"],
            # Determinism is a property of the engine, checked in the test suite on every change. Re-running
            # every production analysis twice to check it again would double what a reader waits for, so it is
            # off unless asked for - and that is said here rather than left as an empty field that reads as a
            # failed check.
            "determinism": summary.get("determinism") or "NOT_RUN_FOR_THIS_JOB",
            "contamination": summary.get("contamination"),
            # whether another machine was consulted about this reading, and what it did - a number on screen is
            # only checkable if you can tell what made it
            "second_reader": summary.get("second_reader") or {"consulted": False},
            # How much of what the drawing names ended up with a metre. Every other number here is about what was
            # found; this one is about what was not, and it is what separates a sheet the reading got through
            # from one it barely opened.
            "named_vs_measured": next((c for c in ((_load_optional(root, "reading-coverage.json") or {}).get("sheets") or [])
                                       if c.get("page") == page.get("page")), {}),
        },
        # The whole set, not only its first sheet: a row per designation summed over the sheets it stands on,
        # and what each sheet on its own contributed.
        "document": _load_optional(root, "document-quantities.json"),
        "source_assignment": _load_optional(rd, "source-assignment.json"),
        # which sheets this reading holds, so the reader can move between them
        "pages": pages or [page.get("page", 0)],
        "skipped_pages": summary.get("skipped_pages") or [],
        "performance": perf,
        "review": _load_optional(root, "review-findings.json"),
        "crosscheck": _load_optional(rd, "route-crosscheck.json"),
        "reading_review": _load_optional(rd, "reading-review.json"),
        # the drawing's own designation list, as the reading understood it: which codes it took for systems,
        # which for fittings, which for materials, and whether the page itself showed that or its own grouping did
        "legend": _load_optional(rd, "drawing-legend.json") or {"n_entries": 0, "entries": []},
        # every designation this sheet writes, with its kind, its places and its quantity - only in "Alla"
        "all_designations": next((s for s in ((_load_optional(root, "all-designations.json") or {}).get("sheets") or [])
                                  if s.get("page") == (page_no or 0)), None),
    }


def _load_optional(result_dir: str, name: str):
    path = os.path.join(result_dir, name)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return upgrade(name, json.load(fh))


@app.get("/api/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = _job(db, user, job_id)
    rd = _result_dir(j)
    return [{"name": n, "size": os.path.getsize(os.path.join(rd, n))} for n in ARTIFACTS if os.path.exists(os.path.join(rd, n))]


@app.get("/api/jobs/{job_id}/artifacts/{name}")
def get_artifact(job_id: str, name: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = _job(db, user, job_id)
    rd = _result_dir(j)
    if name not in ARTIFACTS:
        raise HTTPException(404, "Okänd artefakt")
    p = os.path.join(rd, name)
    if not os.path.exists(p):
        raise HTTPException(404, "Artefakten saknas")
    media = "application/pdf" if name.endswith(".pdf") else ("text/markdown" if name.endswith(".md") else "application/json")
    return FileResponse(p, media_type=media, filename=name)


@app.get("/api/jobs/{job_id}/judge")
def job_judge(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What, out of everything the reading and its reviewers found, should actually change.

    The reviewers state disagreements and stop; the judge decides. It implements only answers the drawing itself
    puts forward, never touches a measurement the reading confirmed, writes anything it does implement as a
    correction that can be undone, and says plainly where the evidence does not settle a case. It calls no model:
    the same reading judged twice gives the same verdicts.
    """
    from vvs_engine.agent.model import DrawingModel
    from vvs_engine.review.judge import judge as run_judge

    j = _job(db, user, job_id)
    if j.status != "COMPLETED":
        raise HTTPException(409, "analysen är inte klar")
    rd = _result_dir(j)
    anchors = _load(rd, "pipe-code-anchors.json")["anchors"]
    pipes = _load(rd, "physical-pipes.json")["physical_pipes"]
    geom = _load(rd, "pipe-geometry-inventory.json")["primitives"]
    return run_judge(DrawingModel(rd), proposals=_proposals(db, user, anchors, pipes, geom))


class AgentAsk(BaseModel):
    question: str
    language: str | None = None     # "en": svaret skrivs på engelska, som resten av vyn
    page: int | None = None
    pipe_ids: list[str] | None = None
    bbox: list[float] | None = None
    history: list[dict] | None = None


@app.get("/api/agent/tools")
def agent_tools(user: User = Depends(current_user)):
    """The contract, so the interface can show what the agent is actually able to do."""
    from vvs_engine.agent import tools as T
    return {"tools": [{"name": t["name"], "description": t["description"], "andrar": bool(t.get("writes")),
                       "parameters": sorted(t["parameters"]["properties"])} for t in T.TOOLS.values()]}


class ToolAsk(BaseModel):
    name: str
    arguments: dict | None = None


@app.post("/api/jobs/{job_id}/agent/tool")
def agent_tool(job_id: str, body: ToolAsk, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Run one tool against this reading and say what it found, with no model in the way.

    Every question the interface offers as a button is a single call into the reading, and the answer is already
    a number - so composing the sentence is arithmetic, not judgement. It costs nothing, it cannot hallucinate,
    and it works on an installation that has no model configured at all.
    """
    from vvs_engine.agent import tools as T
    from vvs_engine.agent.answers import say
    from vvs_engine.agent.model import DrawingModel

    j = _job(db, user, job_id)
    if j.status != "COMPLETED":
        raise HTTPException(409, "analysen är inte klar")
    if body.name not in T.TOOLS:
        raise HTTPException(404, f"okänt verktyg {body.name}")
    m = DrawingModel(_result_dir(j))
    result = T.run(body.name, m, body.arguments or {})
    from app.agent import _highlights
    return {"svar": say(body.name, result), "verktyg": [{"namn": body.name, "argument": body.arguments or {}, "resultat": result}],
            "markera": _highlights([{"resultat": result}])}


class EditAsk(BaseModel):
    name: str
    arguments: dict | None = None
    note: str | None = None


@app.post("/api/jobs/{job_id}/agent/edit")
def agent_edit(job_id: str, body: EditAsk, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Accept a change the agent proposed, and write it to the correction log.

    The proposal itself never crosses the wire back. What arrives is the call that produced it - the tool and its
    arguments - and the server runs that call again against this reading and records what comes out. So a caller
    cannot hand back a proposal with the metres edited, or one made against another drawing: the numbers written
    are the ones this reading produces right now, or nothing is written at all.

    What lands is ordinary corrections. They layer over the reading the same way a person's own do, they sit
    beside the engine's untouched figures, and each one can be undone.
    """
    from vvs_engine.agent import tools as T
    from vvs_engine.agent.model import DrawingModel

    j = _job(db, user, job_id)
    if j.status != "COMPLETED":
        raise HTTPException(409, "analysen är inte klar")
    if not T.writes(body.name):
        raise HTTPException(400, f"{body.name} ändrar ingenting; den svarar på en fråga")
    result = T.run(body.name, DrawingModel(_result_dir(j)), body.arguments or {})
    if result.get("fel"):
        raise HTTPException(400, str(result["fel"]))
    if result.get("tillstand") != "FORESLAGEN" or not result.get("forslag"):
        raise HTTPException(409, str(result.get("skal") or "ritningen stöder inte den ändringen"))

    written = []
    for f in result["forslag"]:
        if f["kind"] not in CORRECTION_KINDS:
            continue
        # The situation is read off the reading here exactly as it is for a correction a person makes by hand:
        # what a correction may teach a later drawing is a fact about this one, never something a caller sends.
        sit = _situation_of(db, user, job_id, f.get("designation"))
        note = " · ".join(x for x in (body.note, f.get("text"),
                                      (f.get("payload") or {}).get("reason")) if x)
        c = Correction(drawing_id=j.drawing_id, job_id=job_id, user_id=user.id, page=0, kind=f["kind"],
                       designation=f.get("designation"), payload=f.get("payload") or {}, situation=sit,
                       note=note[:1000] or None)
        db.add(c)
        written.append(c)
    if not written:
        raise HTTPException(409, "förslaget innehöll ingen rättelse som kunde skrivas")
    db.commit()
    return {"skrivna": [_correction_out(c) for c in written],
            "sammanfattning": result.get("sammanfattning"), "berord_meter": result.get("berord_meter")}


@app.post("/api/jobs/{job_id}/agent")
def agent_ask(job_id: str, body: AgentAsk, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ask the agent about this reading.

    The model chooses which questions to put to the drawing; the engine answers them. Every number in the reply
    came out of a tool call over the artifacts the measurement wrote, so the chat and the takeoff table cannot
    disagree, and the reply carries the ids it rests on so the claim can be pointed at on the sheet.
    """
    from vvs_engine.agent.model import DrawingModel

    from app.agent import run_turn

    j = _job(db, user, job_id)
    if j.status != "COMPLETED":
        raise HTTPException(409, "analysen är inte klar")
    # The agent reads; it cannot move a metre. VVS_SECOND_READER is about whether a model may settle a case
    # during the measurement, which is a stronger promise than "no model may answer a question about a finished
    # reading" - and switching the first off used to silence the second, which is not what anyone asked for.
    try:
        from tools.astra_transport import agent_transport
    except Exception as e:                                      # noqa: BLE001
        raise HTTPException(503, f"agenttransporten kunde inte laddas: {type(e).__name__}")
    # No pre-flight guess about whether a model can be reached. Every guess so far has been wrong in a different
    # way - a flag that meant something else, a proxy that attaches the credential without setting HTTPS_PROXY -
    # and a wrong "cannot" is worse than a slow "could not": it is a refusal on a false premise. So the call is
    # made, and what comes back is what the reader is told.
    from . import api_budget
    api_budget.require()
    model = DrawingModel(_result_dir(j))
    sel = {"pipe_ids": body.pipe_ids or [], "bbox": body.bbox, "page": body.page}
    try:
        # the reader works in English: the answer is written in English, whatever language the instructions use
        question = (("[Reply in English only - every sentence of the answer.]\n\n" + body.question)
                    if body.language == "en" else body.question)
        out = run_turn(model, agent_transport(), question, selection=sel, history=body.history or [])
    except Exception as e:                                      # noqa: BLE001
        raise HTTPException(502, f"Agenten nådde inte modellen: {type(e).__name__}: {str(e)[:200]}. "
                                 f"Knapparna svarar ändå — de går rakt in i läsningen och behöver ingen modell.")
    return out


@app.post("/api/jobs/{job_id}/vision")
def vision_check(job_id: str, page: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A second opinion by eye on a reading that is already finished.

    Asked for, never automatic: it costs a call and a wait, and the reading does not depend on it. What comes
    back are observations to check in the vector data - designations that look visible but were not read, drawn
    pipe no overlay follows, an overlay running along something that is not a pipe. None of it can move a metre;
    there is no path from a vision finding to a quantity, by construction.
    """
    j = _job(db, user, job_id)
    if j.status != "COMPLETED":
        raise HTTPException(409, "Analysen är inte klar")
    from . import api_budget
    api_budget.require()
    credits_api.charge_vision(db, user, j, page)
    try:
        import pymupdf
        from vvs_engine.pdf.extract import extract_document
        from vvs_engine.pipeline import analyze_page
        from vvs_engine.review import vision as vz
        from tools.readers import vision as vision_transport
    except Exception as e:
        raise HTTPException(503, f"Vision är inte tillgänglig i den här installationen: {type(e).__name__}")
    path = storage.path(j.drawing.storage_key)
    doc = extract_document(path)
    if page < 0 or page >= len(doc.pages):
        raise HTTPException(404, "Sidan finns inte")
    pa = analyze_page(doc.pages[page])
    out = vz.look(pa, pymupdf.open(path), ask=vision_transport())
    return out.as_dict()


@app.get("/api/jobs/{job_id}/why/{pipe_id}")
def why(job_id: str, pipe_id: str, page: int | None = None,
        user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Why this run is what it is - looked up on the sheet it was found on.

    A run belongs to one sheet, and so does the chain behind it. Searching only the first sheet is how a
    question about a pipe on page nine comes back "unknown pipe" for a reading that measured it.
    """
    j = _job(db, user, job_id)
    root = _result_dir(j)
    order = ([page] if page is not None else []) + (_sheet_pages(root) or [0])
    rd, p = root, None
    for pg in order:
        rd = _sheet_dir(root, pg)
        pipes = _load_optional(rd, "physical-pipes.json") or {}
        p = next((x for x in (pipes.get("physical_pipes") or []) if x["physical_pipe_id"] == pipe_id), None)
        if p is not None:
            break
    if p is None:
        raise HTTPException(404, "Okänt rör")
    anchors = {a["anchor_id"]: a for a in _load(rd, "pipe-code-anchors.json")["anchors"]}
    des = {d["did"]: d for d in _load(rd, "vector-designations.json")["designations"]}
    leaders = {l["lid"]: l for l in _load(rd, "leader-forensics.json")["leaders"]}
    scale = _load(rd, "quantities.json")["scale"]
    chain = []
    for aid in p["supporting_anchors"]:
        a = anchors.get(aid)
        if not a:
            continue
        chain.append({"designation": des.get(a["designation_id"]), "dn": a["dn"], "leader": leaders.get(a["leader_id"]), "attachment": a})
    return {"pipe": p, "evidence_chain": chain, "scale": scale}


def _attachment(name: str) -> dict:
    """En nedladdning med ett svenskt filnamn.

    Ett HTTP-huvud får bara bära latin-1, och ett filnamn med ö i skickat rakt av föll hela svaret - så en
    ritning som heter "Kv Björken plan 2" gick inte att exportera alls, vilket är varenda svensk ritning.
    RFC 5987 löser det med två namn: ett rent ASCII-namn som varje läsare förstår, och det riktiga namnet
    procentkodat i `filename*`, som moderna webbläsare föredrar. Starlettes FileResponse gör redan så; det
    här är samma sak för de svar som byggs i minnet.
    """
    from urllib.parse import quote
    import unicodedata
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    plain = "".join(ch if ch.isalnum() or ch in "-_. " else "_" for ch in plain).strip() or "fil"
    return {"Content-Disposition": f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name)}"}


@app.get("/api/jobs/{job_id}/export/{fmt}")
def export(job_id: str, fmt: str, floor_height: float | None = None, include_hatched: bool = False,
           riser_source: str = "symbols", include_declared: bool = True,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = _job(db, user, job_id)
    rd = _result_dir(j)
    base = os.path.splitext(j.drawing.filename)[0]
    fh = floor_height if floor_height and floor_height > 0 else None
    if floor_height is None:
        # no height in the request: the service's assumption, which is a storey of 2.8 m unless changed
        row = db.get(ServiceSetting, "assume:floor_height_m")
        stored = (row.value or {}).get("v") if row is not None and isinstance(row.value, dict) else ASSUMPTION_DEFAULTS["floor_height_m"]
        fh = float(stored) if stored else None
    # An export carries the reading as it stands, corrections included. Leaving them out would hand back the
    # figure the reader already rejected on screen, in the file they price from.
    quantities = _load(rd, "quantities.json")
    corr = [_correction_out(c) for c in
            db.query(Correction).filter(Correction.drawing_id == j.drawing_id, Correction.undone == False).all()]  # noqa: E712
    rows = (apply_corrections(quantities["rows"], corr, quantities["scale"].get("meters_per_pdf_point"))["quantities"]
            if corr else quantities["rows"])
    # de egna markeringarna följer med Excel-filen på ett eget blad, och JSON:en under eget namn
    from .db import Markup
    marks = [{"tool": m.tool, "layer": m.layer, "designation": m.designation, "page": m.page, "text": m.text,
              "measure": m.measure, "points": m.points}
             for m in db.query(Markup).filter(Markup.drawing_id == j.drawing_id, Markup.deleted.is_(False))
             .order_by(Markup.created_at).all()]
    if fmt == "xlsx":
        return Response(exports.to_xlsx(rd, fh, include_hatched, rows, riser_source, marks, include_declared), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers=_attachment(f"{base}-mangder.xlsx"))
    if fmt == "csv":
        return Response(exports.to_csv(rd, fh, include_hatched, rows, riser_source, include_declared).encode("utf-8-sig"), media_type="text/csv", headers=_attachment(f"{base}-mangder.csv"))
    if fmt == "json":
        everything = _load_optional(rd, "all-designations.json")      # only in "Alla"
        return Response(json.dumps({**quantities, "rows": rows, "corrections_applied": len(corr), "markups": marks,
                                    **({"all_designations": everything} if everything else {})},
                                   ensure_ascii=False, indent=1).encode("utf-8"),
                        media_type="application/json",
                        headers=_attachment(f"{base}-quantities.json"))
    if fmt == "report":
        return FileResponse(os.path.join(rd, "analysis-report.md"), media_type="text/markdown", filename=f"{base}-analysrapport.md")
    if fmt == "pdf":
        return FileResponse(os.path.join(rd, "production-overlay.pdf"), media_type="application/pdf", filename=f"{base}-markerad.pdf")
    if fmt == "control":
        # the sheet with every run in how sure the reading is of it: green, yellow, red (control_pdf.py)
        from .control_pdf import render
        return Response(render(storage.path(j.drawing.storage_key), rd), media_type="application/pdf",
                        headers=_attachment(f"{base}-kontroll.pdf"))
    raise HTTPException(404, "Okänt exportformat")


# ---------------------------------------------------------------- built frontend (single-container deployment)
_STATIC = settings.static_root


def _looks_like_a_file(path: str) -> bool:
    """En adress till en fil, inte till en sida. Sista ledet har en ändelse; en vy har ingen."""
    last = path.rsplit("/", 1)[-1]
    return "." in last and not last.startswith(".")


if os.path.isfile(os.path.join(_STATIC, "index.html")):
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Sidan för vyer, filen för filer, och 404 för en fil som inte finns.

        Det sista är hela poängen. Ett bygge lägger sitt namn i filnamnet - index-CDF-0Pis.css - och sidan
        hämtar just det namnet. Frågar webbläsaren efter ett namn den här versionen inte har, och vi då svarar
        med index.html i stället för 404, får den tillbaka HTML där den bad om ett formatmall. Den vägrar då
        att använda den, tyst, och sidan visas helt utan form medan skripten fungerar - för dem låg kvar i
        cachen. Det ser ut som att formgivningen försvunnit, men det är adressen som pekar på ett bygge som
        inte längre finns.

        Därför: en adress som ser ut som en fil får aldrig sidan som svar, och sidan själv får aldrig sparas
        i cachen. Namnsatta filer får sparas för alltid - de kan ändå aldrig ändra innehåll utan att byta
        namn - och det är det som gör att ett nytt bygge slår igenom direkt i stället för i morgon.
        """
        if full_path.startswith("api/"):
            raise HTTPException(404, "Okänd API-väg")
        candidate = os.path.normpath(os.path.join(_STATIC, full_path))
        # samma sak som i lagret: under katalogen med avskiljaren emellan, inte bara ett prefix
        if full_path and candidate.startswith(_STATIC + os.sep) and os.path.isfile(candidate):
            r = FileResponse(candidate)
            r.headers["Cache-Control"] = ("public, max-age=31536000, immutable"
                                          if full_path.startswith("assets/") else "public, max-age=3600")
            return r
        if _looks_like_a_file(full_path):
            raise HTTPException(404, "Filen finns inte i det här bygget")
        r = FileResponse(os.path.join(_STATIC, "index.html"))
        r.headers["Cache-Control"] = "no-cache, must-revalidate"
        return r
