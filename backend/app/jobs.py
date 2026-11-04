"""Background analysis jobs: a thread-pool worker executes the engine; stages reflect real pipeline stages."""
from __future__ import annotations

import datetime as dt
import os
import time
import json
import sys
import threading
import logging
from concurrent.futures import ThreadPoolExecutor

from .config import settings
from .db import AnalysisJob, Drawing, SessionLocal
from .storage import storage

log = logging.getLogger(__name__)

ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "engine"))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

STAGE_ORDER = ["QUEUED", "READING_PDF", "DISCOVERING_DRAWING_GRAMMAR", "EXTRACTING_VECTORS", "RECONSTRUCTING_TEXT",
               "RESOLVING_UNREADABLE_TEXT", "READING_DESIGNATIONS",
               "FINDING_LEADERS", "RESOLVING_PIPE_REPRESENTATION", "ATTACHING_PIPES", "BUILDING_TOPOLOGY", "PIPESTUDIO_EXTRACT", "PIPESTUDIO_PROFILE", "PIPESTUDIO_DETECT",
               "PIPESTUDIO_OCR", "PIPESTUDIO_VECTOR_STAGES", "BUILDING_PHYSICAL_PIPES",
               "MEASURING", "REVIEWING", "GENERATING_OVERLAYS", "COMPLETED"]

_executor = ThreadPoolExecutor(max_workers=max(1, settings.worker_threads))
# Projektanalysen läser namnrutor: sekunder per blad, och ingen av den tunga geometrin. Mängdningen kan ta en
# halvtimme per blad. Delar de kö hamnar den billiga läsningen bakom varje dyr - en användare som laddat upp
# trettio blad och startat mängdningen får vänta ut alla trettio innan handlingsförteckningen ens börjar - och
# åt andra hållet håller en trehundrabladig projektläsning mängdningen stilla. Två köer, för det är två sorters
# arbete som inte konkurrerar om samma sak.
_reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="handling")
# Agenten som arbetar vidare efter en färdig läsning har en egen kö. I mängdningens kö höll den nästa ritning
# stilla i upp till tjugo minuter, fast läsningen redan var klar och visad.
_agent = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent")
# Spärren för lärda regler läser kontrollerade blad igen under en regel. Den får aldrig stå i vägen för en
# kunds läsning, så den har en egen kö med en tråd.
_rules = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rules")


def submit_rule_gate(rule_id: str) -> None:
    def _gate():
        try:
            from .learned_rules import gate
            gate(rule_id)
        except Exception:                                  # noqa: BLE001
            log.exception("Spärren föll för regel %s", rule_id)
    _rules.submit(_gate)
_lock = threading.Lock()


def _set(job_id: str, **fields) -> None:
    with SessionLocal() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        db.commit()


def _progress_cb(job_id: str):
    def cb(stage: str):
        # a stage may carry a detail after its name ("RESOLVING_UNREADABLE_TEXT ruta 3/7"); the name is what
        # places it in the order, and without this split a slow step reported itself as no progress at all
        name = stage.split(" ")[0]
        idx = STAGE_ORDER.index(name) if name in STAGE_ORDER else 0
        # Engine completion precedes result persistence and credit settlement.
        # Only run_job may publish COMPLETED after those transactions succeed.
        _set(job_id, stage=stage if name != "COMPLETED" else "GENERATING_OVERLAYS",
             progress=min(.99, round(idx / (len(STAGE_ORDER) - 1), 3)), status="RUNNING")
    return cb


def _film_sink(out_dir: str):
    """Write each stage's frame as it lands, so the browser can watch the reading happen.

    The whole film is rewritten every frame: a frame is a few hundred shapes, the sheet has a dozen stages, and
    a single replace is cheaper to reason about than an append the reader might catch half-written.
    """
    frames: list[dict] = []
    path = os.path.join(out_dir, "film.json")

    def sink(stage: str, payload: dict) -> None:
        frames.append({"stage": stage, "at": round(time.time(), 2), **payload})
        os.makedirs(out_dir, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"frames": frames}, fh, ensure_ascii=False)
        os.replace(tmp, path)

    return sink


def _second_reader():
    """The second reader, if this installation is configured for one and can actually reach it.

    Returns None otherwise, which is what the engine expects: without a transport nothing is asked, the reading
    is deterministic and runs with no network at all. A configuration that asks for a second reader and cannot
    reach one says so in the log rather than failing an analysis over it - the takeoff does not depend on it.
    """
    on, why = second_reader_state()
    if not on:
        return None
    try:
        from tools.readers import panel_transport
    except Exception:
        return None
    return panel_transport()


def second_reader_state() -> tuple[bool, str]:
    """Whether a model may settle a case *during the measurement*, and the reason.

    This is not the same question as whether the agent may answer a question about a finished reading. The agent
    only reads, and turning this off is a promise about the takeoff, not a gag order.

    Unset means yes where a key is present. Explicitly on means yes wherever the transport can reach the model at
    all, which includes a machine behind a proxy that attaches the credential and holds no key itself.
    """
    if settings.second_reader is False:
        return False, "avstängd i den här installationen (VVS_SECOND_READER=false)"
    try:
        from tools.readers import state, wanted
    except Exception as e:                                      # noqa: BLE001
        return False, f"transporten kunde inte laddas: {type(e).__name__}"
    keys = [k for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY") if os.environ.get(k, "").strip()]
    use = wanted()
    if settings.second_reader is None:
        if not keys:
            return False, ("ingen OPENAI_API_KEY och ingen ANTHROPIC_API_KEY i miljön; sätt en av dem, "
                           "eller VVS_SECOND_READER=true bakom en proxy")
        return True, _panel_why(use, keys)
    if not use:
        return False, "påslagen men ingen läsare går att nå: " + "; ".join(
            f"{r['name']}: {r['why']}" for r in state())
    return True, _panel_why(use, keys)


def _panel_why(use: tuple[str, ...], keys: list[str]) -> str:
    """Vad en läsare av statussidan behöver veta: vilka som svarar, och vad två av dem innebär."""
    who = ", ".join(use) if use else "ingen"
    if len(use) > 1:
        return f"{who} - ett fall avgörs bara när båda väljer samma kandidat ({', '.join(keys) or 'via proxy'})"
    return f"{who} ({', '.join(keys) or 'via proxy'})"


# A pen has to be stated this often, and this consistently, before another sheet may lean on it. One stray
# label on one drawing is not an office's habit; two hundred agreeing ones are.
PROJECT_MIN_TIMES = 3
PROJECT_MIN_SHARE = 0.8


def project_system_families(db, drawing) -> dict[str, str]:
    """What the rest of this project's drawings have already stated: drawn family -> system.

    A set of drawings is one office drawing one building. Where a sheet labels a run on its own, it says which
    pen that office uses for that system - and on a sheet whose bundles are symmetric, that is the fixpoint that
    settles them. It is a fact read off other drawings, never something a person was asked for.
    """
    from .project_memory import family_consensus, latest_sources
    rows = (db.query(AnalysisJob, Drawing)
            .join(Drawing, AnalysisJob.drawing_id == Drawing.id)
            .filter(Drawing.project_id == drawing.project_id, AnalysisJob.status == "COMPLETED",
                    AnalysisJob.drawing_id != drawing.id, AnalysisJob.result_key.isnot(None))
            .order_by(AnalysisJob.finished_at.desc(), AnalysisJob.created_at.desc(), AnalysisJob.id.desc()).all())
    documents = []
    for job, _ in latest_sources(rows, drawing.sha256):
        path = os.path.join(storage.path(job.result_key), "drawn-system-families.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                document = json.load(fh)
        except Exception:                                       # noqa: BLE001
            continue
        documents.append(document)
    return family_consensus(documents, PROJECT_MIN_TIMES, PROJECT_MIN_SHARE)


def project_legend(db, drawing):
    """The designation list the rest of this project already read, for a drawing that carries none.

    A project is one office's set for one building, and it writes its vocabulary once. Uploading the plan sheets
    without the sheet that carries the list left every one of them with no vocabulary at all - so every label
    passed as possibly a pipe, and the review list filled with door marks. The list is a fact read off the other
    drawings' own artifacts, never something a person was asked for.

    Only a list a drawing carried itself counts, so a borrowed list is never re-lent; and where two drawings
    disagree about what a code is, the code is dropped rather than settled by whichever was read first.
    """
    from collections import defaultdict
    from .project_memory import latest_sources

    from vvs_engine.semantics.legend import DrawingLegend, LegendEntry
    rows = (db.query(AnalysisJob, Drawing)
            .join(Drawing, AnalysisJob.drawing_id == Drawing.id)
            .filter(Drawing.project_id == drawing.project_id, AnalysisJob.status == "COMPLETED",
                    AnalysisJob.drawing_id != drawing.id, AnalysisJob.result_key.isnot(None))
            .order_by(AnalysisJob.finished_at.desc(), AnalysisJob.created_at.desc(), AnalysisJob.id.desc()).all())
    seen: dict[str, dict] = {}
    roles: dict[str, set] = defaultdict(set)
    for job, _ in latest_sources(rows, drawing.sha256):
        path = os.path.join(storage.path(job.result_key), "drawing-legend.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:                                       # noqa: BLE001
            continue
        for e in doc.get("entries") or []:
            code = str(e.get("code") or "").strip()
            if not code or e.get("role_from") == "other_sheet":
                continue
            roles[code.upper()].add(e.get("role"))
            seen.setdefault(code.upper(), e)
    entries = [LegendEntry(code=e["code"], description=e.get("description") or "", heading=e.get("heading") or "",
                           bbox=(0.0, 0.0, 0.0, 0.0), role=e.get("role") or "material", role_from="other_sheet")
               for c, e in sorted(seen.items()) if len(roles[c]) == 1]
    return DrawingLegend(own=False, entries=entries) if entries else None


def account_rules(db, drawing) -> dict:
    """The rules this account has moved, for the reading about to run.

    Read once, here, and bound to the thread that does the reading. Jobs share a process, so a rule set globally
    would hold for whatever else is being read at the same moment - and a takeoff measured under someone else's
    settings is the worst kind of wrong, because nothing on the page says it happened.
    """
    from .db import Project, RuleSetting, ServiceSetting
    out: dict = {}
    for row in db.query(ServiceSetting).filter(ServiceSetting.key.like("rule:%")).all():
        out[row.key[5:]] = (row.value or {}).get("v")          # what the administrator moved for the service
    proj = db.get(Project, drawing.project_id)
    if proj is None:
        return out
    for r in db.query(RuleSetting).filter(RuleSetting.user_id == proj.owner_id).all():
        out[r.rule_id] = r.value                               # what this account moved back when it could
    return out


def _keep_upright(summary: dict, out_dir: str, pdf_path: str) -> None:
    """Replace the stored drawing with the copy the reading turned upright, when it turned any page."""
    name = (summary or {}).get("upright_file")
    if not name or not (summary or {}).get("turned_pages"):
        return
    turned = os.path.join(out_dir, name)
    if os.path.isfile(turned):
        import shutil
        tmp = pdf_path + ".upright"
        shutil.copyfile(turned, tmp)
        os.replace(tmp, pdf_path)


def _run_agent(job_id: str, out_dir: str, pdf_path: str, ai_model: str | None) -> None:
    # First the rules the system has learned and an admin has approved - they need no model and run on every
    # reading - then the agent, on what they left open.
    solved = {}
    try:
        from .learned_rules import apply_active
        solved = apply_active(job_id, out_dir, pdf_path)
    except Exception:                                      # noqa: BLE001
        log.exception("De lärda reglerna kunde inte köras efter analysen")
    try:
        from .solver import run_for_job
        run_for_job(job_id, out_dir, pdf_path, ai_model, solved)
    except Exception:                                      # noqa: BLE001
        log.exception("Agenten kunde inte köras efter analysen")


def run_job(job_id: str) -> None:
    from vvs_engine import rules as engine_rules
    from .analysis_worker import analyze_isolated
    from vvs_engine.pdf.extract import UnsupportedInputError
    with SessionLocal() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return
        drawing = db.get(Drawing, job.drawing_id)
        pdf_path = storage.path(drawing.storage_key)
        result_key = f"results/{drawing.id}/{job.id}"
        known = project_system_families(db, drawing)
        vocab = project_legend(db, drawing)
        moved = account_rules(db, drawing)
        # vad den här tjänsten kör, läst medan sessionen finns kvar - OCR-passen kostar tid och är valbara
        from .main import RUN_KEYS, run_setting
        run_ocr = {k: run_setting(db, k) for k in RUN_KEYS}
        # att jobbet kördes om efter en omstart är en del av dess historia och följer med in i det färdiga svaret,
        # och likaså den skala någon skrev in för hand innan det kördes: en mängd ska bära hur den blev mätbar
        carried = {k: v for k, v in (job.summary or {}).items()
                   if k in ("resubmitted_after_restart", "given_scale", "credits", "assignment_mode", "source_style",
                            "ai_model")}
        ai_model = (job.summary or {}).get("ai_model")
        gs = (job.summary or {}).get("given_scale") or None
        by_hand = {int(gs["page"]): float(gs["meters_per_pdf_point"])} if gs else None
        job.status = "RUNNING"; job.started_at = dt.datetime.now(dt.timezone.utc); job.result_key = result_key
        db.commit()
    out_dir = storage.path(result_key)
    try:
        # a full disk is found out here, in plain words, not half-way through the reading as "Errno 28"
        from .disk_space import ensure_room
        ensure_room(storage.path(""), storage.path("results"))
        # the account's own rules, bound to this thread and to nothing else
        with engine_rules.using(moved):
            summary = analyze_isolated(pdf_path, out_dir, name=os.path.splitext(drawing.filename)[0],
                                rule_values=moved,
                                label_audit=settings.label_audit,
                                deadline_s=settings.analysis_deadline_s, determinism=settings.run_determinism,
                                contamination=True, progress=_progress_cb(job_id),
                                review=settings.run_review, review_ocr=run_ocr["review_ocr"],
                                ocr_assist=run_ocr["ocr_assist"], film_sink=_film_sink(out_dir),
                                second_reader_enabled=second_reader_state()[0], known_families=known, known_legend=vocab,
                                given_scale=by_hand, source_mode="combined", native_detection=True,
                                native_cache_dir=storage.path(f"cache/native/{drawing.project_id}"),
                                source_style="auto", ai_model=ai_model, discipline=job.discipline or "")
            # Ett blad som låg på sidan lästes vridet upprätt, och dess koordinater gäller det vridna bladet. Ritningen
            # som visas byts mot den vridna - samma innehåll, bara /Rotate ändrad - så att markeringarna hamnar rätt.
            _keep_upright(summary, out_dir, pdf_path)
            from .ai_usage import read_usage
            summary["summary"]["ai_usage"] = read_usage(out_dir, ai_model)
            from .diagnostic_storage import compress_native_diagnostics
            compress_native_diagnostics(out_dir)
            from .disk_space import link_sheet_copies
            link_sheet_copies(out_dir)
            # which readers this installation actually had available, and by what name - a reading that quietly used a
            # model, or quietly did without one, is not a reading anyone can check
            on, why = second_reader_state()
            sr = dict(summary["summary"].get("second_reader") or {})
            sr.update({"enabled": on, "why": why,
                     "model": os.environ.get("VVS_SECOND_READER_MODEL", "gpt-6-astra") if on else None})
            # Hur långt läsningen kom på bladet, sparat på jobbet och inte bara i artefakten.
            #
            # Portalen ritar en kurva över täckningen per dygn och kallar den den enda som säger om systemet
            # blir bättre. Den läste `summary["coverage"]["named_vs_measured"]`, som bara byggdes i
            # resultatsvaret - på jobbet fanns den aldrig, så kolumnen och kurvan stod tomma hur många blad som
            # än lästes. Talet hör hemma där frågan ställs.
            #
            # Raden skrivs platt, som läsningen själv skriver den. Att i stället lägga den under ett eget namn
            # kostade pengar: återbetalningsregeln läser samma rad, hittade inga rörnamn med meter där den
            # letade, och betalade tillbaka varenda läsning. En rad, en form, och `sheet_coverage` läser den.
            # Avräkningen görs innan läsningen visas som klar, inte efter.
            #
            # Förut stod ordningen tvärtom: jobbet sattes till COMPLETED och avräknades i ett finally efteråt.
            # Mellan de två fanns ett glapp där den som laddat upp ett blad utan skala såg "klar" och en credit
            # borta - återbetalningen kom en stund senare. Under belastning är glappet långt nog att synas, och
            # dör processen i det kommer återbetalningen aldrig: pengen är då bara borta. Nu skrivs det
            # läsningen kom fram till först, avräkningen görs på det, och först när den ligger i reskontran
            # flyttas jobbet till COMPLETED. Ingen ser en läsning som är klar och obetald på en gång.
            done = {"total_seconds": summary["total_seconds"], **summary["summary"], "second_reader": sr,
                    "source_assignment": summary.get("source_assignment"),
                    "coverage": _first_sheet_coverage(out_dir) or (summary["summary"].get("coverage") or {}),
                    **carried}
            _set(job_id, summary=done)
            _settle_credits(job_id)
            _set(job_id, status="COMPLETED", stage="COMPLETED", progress=1.0,
                 finished_at=dt.datetime.now(dt.timezone.utc), summary=done)
        # With a model chosen, the agent works on what the reading's own checks left open. The reading is complete
        # and shown already; what the agent changes arrives as corrections marked as its own.
        _agent.submit(_run_agent, job_id, out_dir, pdf_path, ai_model)
    except UnsupportedInputError as e:
        # not a defect: no page carries a drawing - no vector geometry, and no scan or image to read either
        _set(job_id, status="FAILED", stage="FAILED", finished_at=dt.datetime.now(dt.timezone.utc),
             error="Ritningen innehåller inget som går att läsa: ingen sida har vektorgeometri, och ingen är en "
                   "skanning eller bild att läsa ur bildpunkterna. Kontrollera att rätt fil laddades upp. "
                   f"Klassificering: {e}")
    except Exception as e:  # noqa: BLE001
        # Felet som skrivs på jobbet visas för den som laddade upp ritningen. En stackspårning där är två fel
        # på en gång: den säger ingenting till en mängdare, och den lämnar ut serverns filvägar och moduler.
        # Spårningen hör hemma i loggen, där den som driver tjänsten kan läsa den.
        log.exception("Analysen misslyckades för jobb %s", job_id)
        _set(job_id, status="FAILED", stage="FAILED",
             error=f"Analysen kunde inte slutföras: {type(e).__name__}: {e}"[:600],
             finished_at=dt.datetime.now(dt.timezone.utc))


def _first_sheet_coverage(out_dir: str) -> dict:
    """Bladets täckningsrad ur läsningens egen artefakt: hur många rörnamn som fick meter, och hur mycket."""
    try:
        with open(os.path.join(out_dir, "reading-coverage.json"), encoding="utf-8") as fh:
            sheets = (json.load(fh) or {}).get("sheets") or []
    except (OSError, ValueError):
        return {}
    if not sheets:
        return {}
    s = sheets[0]
    keep = ("pipe_names", "pipe_names_with_metres", "share", "drawn_m", "confirmed_m", "ambiguous_m", "unowned_m",
            "scale_state", "scale_settled", "markup_set_aside", "names_from", "missed", "schematic", "section")
    return {k: s[k] for k in keep if k in s}


def sheet_coverage(summary: dict | None) -> dict:
    """Täckningsraden för första bladet ur ett jobbs sammanfattning, vilken form den än skrevs i.

    Raden skrivs platt under `coverage`. Under en period skrevs den i stället under `coverage.named_vs_measured`,
    och de jobben ligger kvar i reskontran och i portalens historik. Båda läses här, så att en kurva inte får ett
    hål och en läsning inte avräknas fel för att den gjordes en viss vecka."""
    cov = (summary or {}).get("coverage") or {}
    inner = cov.get("named_vs_measured")
    return inner if isinstance(inner, dict) else cov


def _settle_credits(job_id: str) -> None:
    """När läsningen är över: en läsning som inte gav något kostar ingenting."""
    try:
        from .credits import settle_after_reading
        with SessionLocal() as db:
            job = db.get(AnalysisJob, job_id)
            if job is not None:
                settle_after_reading(db, job)
                db.commit()
    except Exception:  # noqa: BLE001
        log.exception("Kunde inte avräkna credits för jobb %s", job_id)


def submit(job_id: str) -> None:
    def _run():
        try:
            run_job(job_id)
        finally:
            # Nätet under: en läsning som föll, eller som avbröts innan sin egen avräkning hann göras, ska ändå
            # inte kosta något. refund_reading betalar tillbaka en gång och bara en gång, så den här andra
            # omgången är gratis när den första redan gjort sitt.
            _settle_credits(job_id)
    _executor.submit(_run)


def resubmit_unfinished() -> int:
    """Jobb som var på väg när tjänsten senast stängde: kör dem igen, från början.

    Ett jobb körs i en tråd i processen. Startar processen om - en utrullning, en krasch, en maskin som
    byts - står jobbet kvar som RUNNING i databasen och ingen kör det; den som laddade upp ritningen ser en
    mätare som aldrig rör sig. Läsningen är deterministisk och skriver sitt resultat under jobbets egen nyckel,
    så att köra den igen är säkert: samma svar, samma plats. Det som inte får hända är att den försvinner.
    """
    with SessionLocal() as db:
        stale = db.query(AnalysisJob).filter(AnalysisJob.status.in_(("QUEUED", "RUNNING"))).all()
        ids = []
        stopped = []
        for job in stale:
            restarts = int((job.summary or {}).get("resubmitted_after_restart", 0))
            interrupted = job.status == "RUNNING"
            if interrupted and restarts >= 2:
                job.status, job.stage = "FAILED", "FAILED"
                job.finished_at = dt.datetime.now(dt.timezone.utc)
                job.error = ("Analysen avbröts vid upprepade serveromstarter. Automatisk omkörning har stoppats. "
                             "Kontrollera serverns minne och logg innan analysen startas igen. Ingen ofullständig mängd publiceras.")
                stopped.append(job.id)
                continue
            job.status, job.stage, job.progress, job.error = "QUEUED", "QUEUED", 0.0, None
            job.started_at, job.finished_at = None, None
            job.summary = {**(job.summary or {}), "resubmitted_after_restart": restarts + int(interrupted)}
            ids.append(job.id)
        db.commit()
    for jid in stopped:
        _settle_credits(jid)
    for jid in ids:
        log.warning("Jobb %s var oavslutat när tjänsten startade om: körs igen", jid)
        submit(jid)
    return len(ids)
