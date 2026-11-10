"""Taket på vad tjänsten får lägga på språkmodeller, och reskontran som håller räkningen.

Varje anrop till en språkmodell - tilldelningen under en analys, kompletteringsfrågorna och svepet, agenten,
röstassistentens svar, andra läsaren - frågar först `check(model)` och skriver efteråt vad det kostade med
`charge(...)`. Kostnaden räknas ur anropets egna tokens gånger modellens listpris och växelkursen, och raden bär
priset den räknades med. När summan sedan den senaste nollställningen når taket svarar `check` nej:
AI låses för hela tjänsten och det står att alla krediter för AI är förbrukade. Läsning utan AI går som vanligt.

En modell vars pris saknas i prislistan får inte anropas: en kostnad som inte går att räkna kan inte hållas under
ett tak. Priset fylls i under Administration.

Mätaren fungerar i varje process som når databasen, också analysens egen process, så att ett pågående jobb
slutar fråga när taket nås. Det enda som kan gå över taket är de anrop som redan var på väg när det nåddes.
"""
from __future__ import annotations

import datetime as dt
import logging
from contextvars import ContextVar
from typing import Any

from sqlalchemy import func

# Listpriser i USD per miljon tokens, med källa och datum. Hämtade 2026-11-04; en administratör kan ändra dem.
# in = vanliga indata, cached = indata lästa ur leverantörens cache, out = utdata (där resonemang ingår),
# cache_write = skrivning till cachen där leverantören tar betalt för den.
PRICE_DEFAULTS: dict[str, dict[str, Any]] = {
    "gpt-6-astra": {"in": 10.0, "cached": 1.0, "out": 50.0,
                    "source": "OpenAI, ChatGPT Rate Card (help.openai.com/en/articles/20001415)", "date": "2026-11-04"},
    "gpt-6.1-sol": {"in": 2.0, "cached": 0.10, "out": 10.0,
                    "source": "docs.apiyi.com/en/news/gpt-6-1-sol-launch (tredjepartskälla - kontrollera mot OpenAI)",
                    "date": "2026-11-04"},
    "claude-opus-5-5": {"in": 4.0, "cached": 0.20, "out": 20.0, "cache_write": 5.0,
                        "source": "tjänstens egen prislista för Claude (claude_model.PRICES)", "date": "2026-11-04"},
    # Röstsamtalet: ljud kostar mer än text. audio_in/audio_out gäller ljudtokens, in/out texttokens.
    "gpt-realtime": {"in": 4.0, "cached": 0.40, "out": 16.0, "audio_in": 32.0, "audio_out": 64.0,
                     "source": "OpenAI, listpris för gpt-realtime (openai.com/api/pricing) - kontrollera för den "
                               "version som körs (VVS_REALTIME_MODEL)", "date": "2026-11-05"},
    "gpt-4o-mini-transcribe": {"in": 1.25, "out": 5.0, "audio_in": 3.0,
                               "source": "OpenAI, listpris för gpt-4o-mini-transcribe (openai.com/api/pricing)",
                               "date": "2026-11-05"},
    "claude-fable-5-2": {"in": 8.0, "cached": 0.20, "out": 40.0, "cache_write": 10.0,
                         "source": "Anthropics prislista för Claude Fable 5.2 (claude_model.PRICES)", "date": "2026-11-10"},
    "gemini-pro-latest": {"in": 2.0, "cached": 0.20, "out": 12.0,
                          "source": "trevorfox.com/tools/calculators/llm-cost/google-gemini/gemini-3.1-pro "
                                    "(tredjepartskälla för Gemini 3.1 Pro - kontrollera mot ai.google.dev)",
                          "date": "2026-11-04"},
}
USD_SEK_DEFAULT = 9.69          # valutafx.com, 2026-09-10 (senaste noterade kurs som gick att hitta 2026-11-04)
LIMIT_KR_DEFAULT = 10000.0
SETTING = "api:budget"

EXHAUSTED = "Alla krediter för AI är förbrukade."
log = logging.getLogger("vvs.api_budget")
# The meter holds where the service runs: switched on by the service at start-up and in an analysis's own process
# (install_meter). Code that builds a transport for itself - a test with a stand-in model, a script - asks freely.
_ACTIVE = False


# Vem som frågar: satt per anrop till tjänsten (main.py) och i en analys egen process (analysis_worker.py), så att
# varje rad i reskontran säger vems budgetanvändning den var. Budgeten är gemensam; raden visar vem.
WHO: ContextVar[str | None] = ContextVar("api_budget_who", default=None)


class BudgetExhausted(RuntimeError):
    """The service may not call a language model: the ceiling is reached, or the model has no price."""


def _db():
    from .db import SessionLocal
    return SessionLocal()


def settings_of(db) -> dict[str, Any]:
    from .db import ServiceSetting
    row = db.get(ServiceSetting, SETTING)
    v = (row.value or {}).get("v") if row is not None and isinstance(row.value, dict) else None
    v = v if isinstance(v, dict) else {}
    prices = {k: dict(p) for k, p in PRICE_DEFAULTS.items()}
    for k, p in (v.get("prices") or {}).items():
        if p is None:
            prices.pop(k, None)
        elif isinstance(p, dict):
            prices[k] = {**prices.get(k, {}), **p}
    return {"limit_kr": float(v.get("limit_kr", LIMIT_KR_DEFAULT)),
            "usd_sek": float(v.get("usd_sek", USD_SEK_DEFAULT)),
            "reset_at": v.get("reset_at"),
            "prices": prices}


def save(db, change: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:
    from .db import ServiceSetting
    row = db.get(ServiceSetting, SETTING)
    cur = dict(((row.value or {}).get("v") or {}) if row is not None and isinstance(row.value, dict) else {})
    if "prices" in change:
        cur["prices"] = {**(cur.get("prices") or {}), **(change.get("prices") or {})}
    for k in ("limit_kr", "usd_sek", "reset_at"):
        if k in change:
            cur[k] = change[k]
    if row is None:
        row = ServiceSetting(key=SETTING, value={"v": cur})
        db.add(row)
    else:
        row.value = {"v": cur}
    if hasattr(row, "updated_by") and user_id:
        row.updated_by = user_id
    db.commit()
    return settings_of(db)


def price_for(model: str | None, prices: dict[str, dict]) -> dict | None:
    """The price of a model: its own entry, or the longest listed name it begins with (a dated model id)."""
    m = (model or "").strip()
    if not m:
        return None
    best = None
    for name, p in prices.items():
        if (m == name or m.startswith(name)) and isinstance(p, dict) and p.get("in") is not None \
                and p.get("out") is not None and (best is None or len(name) > len(best[0])):
            best = (name, p)
    return best[1] if best else None


def cost_kr(model: str | None, tokens_in: int, tokens_out: int, cached: int = 0, cache_write: int = 0,
            cfg: dict | None = None, audio_in: int = 0, audio_out: int = 0) -> float | None:
    """What a request cost, in kronor; None when the model has no price. tokens_in counts every input token,
    the cached ones included, as the providers report them."""
    cfg = cfg or {}
    p = price_for(model, cfg.get("prices") or PRICE_DEFAULTS)
    if p is None:
        return None
    tin, tout = max(0, int(tokens_in or 0)), max(0, int(tokens_out or 0))
    cached, write = max(0, int(cached or 0)), max(0, int(cache_write or 0))
    # ljudtokens ingår i totalerna, som leverantören räknar dem, men har sitt eget pris
    ain, aout = min(max(0, int(audio_in or 0)), tin), min(max(0, int(audio_out or 0)), tout)
    fresh = max(0, tin - cached - write - ain)
    usd = (fresh * float(p["in"]) + (tout - aout) * float(p["out"]) + cached * float(p.get("cached", p["in"]))
           + write * float(p.get("cache_write", p["in"]))
           + ain * float(p.get("audio_in", p["in"])) + aout * float(p.get("audio_out", p["out"]))) / 1e6
    return round(usd * float(cfg.get("usd_sek", USD_SEK_DEFAULT)), 4)


def spent_kr(db, cfg: dict | None = None) -> float:
    from .db import ApiSpend
    cfg = cfg or settings_of(db)
    q = db.query(func.coalesce(func.sum(ApiSpend.kr), 0.0))
    if cfg.get("reset_at"):
        q = q.filter(ApiSpend.created_at >= dt.datetime.fromisoformat(cfg["reset_at"]))
    return float(q.scalar() or 0.0)


def status(db) -> dict[str, Any]:
    from .db import ApiSpend
    cfg = settings_of(db)
    spent = spent_kr(db, cfg)
    q = db.query(ApiSpend.source, ApiSpend.model, func.count(ApiSpend.id), func.sum(ApiSpend.kr))
    if cfg.get("reset_at"):
        q = q.filter(ApiSpend.created_at >= dt.datetime.fromisoformat(cfg["reset_at"]))
    rows = [{"source": s, "model": m, "requests": int(n), "kr": round(float(k or 0), 2)}
            for s, m, n, k in q.group_by(ApiSpend.source, ApiSpend.model).all()]
    return {"limit_kr": cfg["limit_kr"], "spent_kr": round(spent, 2),
            "remaining_kr": round(max(0.0, cfg["limit_kr"] - spent), 2),
            "exhausted": spent >= cfg["limit_kr"], "usd_sek": cfg["usd_sek"], "reset_at": cfg["reset_at"],
            "prices": cfg["prices"], "by_source": sorted(rows, key=lambda r: -r["kr"])}


# Vad varje del heter för den som läser Credits. Nyckeln är det som står på raden i reskontran.
LABELS = {
    "agent": "Agenten",
    "andra_läsaren": "Andra läsaren (analys)",
    "granskning": "Andra blick (syngranskning)",
    "tilldelning": "AI-tilldelning i analysen",
    "röst": "Röstsamtal",
    "röst_transkribering": "Röstsamtal – transkribering",
    "röst_text": "Samtalsagent i text",
    "tb": "Teknisk beskrivning (AI)",
}


def label(source: str | None) -> str:
    return LABELS.get(source or "", source or "Övrigt")


def _period(db, since=None, until=None, who: str | None = None, source: str | None = None, cfg=None):
    from .db import ApiSpend
    cfg = cfg or settings_of(db)
    q = db.query(ApiSpend)
    if cfg.get("reset_at"):
        q = q.filter(ApiSpend.created_at >= dt.datetime.fromisoformat(cfg["reset_at"]))
    if since is not None:
        q = q.filter(ApiSpend.created_at >= since)
    if until is not None:
        q = q.filter(ApiSpend.created_at < until)
    if who is not None:
        q = q.filter(ApiSpend.user_email == ("" if who == "-" else who))
    if source:
        q = q.filter(ApiSpend.source == source)
    return q


def rows(db, since=None, until=None, who=None, source=None, limit: int | None = None) -> list[dict[str, Any]]:
    from .db import ApiSpend
    q = _period(db, since, until, who, source).order_by(ApiSpend.created_at.desc())
    if limit:
        q = q.limit(limit)
    return [{"at": r.created_at, "user": r.user_email or "", "source": r.source, "label": label(r.source),
             "model": r.model, "tokens_in": int(r.tokens_in or 0), "tokens_out": int(r.tokens_out or 0),
             "tokens": int((r.tokens_in or 0) + (r.tokens_out or 0)), "kr": round(float(r.kr or 0), 4)}
            for r in q.all()]


def shared(db, recent: int = 60, since=None, until=None, who=None, source=None) -> dict[str, Any]:
    """Den gemensamma budgeten som alla inloggade ser: taket, vad som gått åt och vad som är kvar (alltid för hela
    budgetperioden), och tabellerna per del, per person och per modell för det urval som filtren ger."""
    from .db import ApiSpend
    cfg = settings_of(db)
    st = status(db)
    whole = _period(db, cfg=cfg)
    base = _period(db, since, until, who, source, cfg)

    def grouped(col, named=None):
        q = base.with_entities(col, func.count(ApiSpend.id), func.sum(ApiSpend.kr)).group_by(col)
        out = [{"key": k or "", "requests": int(n), "kr": round(float(s or 0), 2)} for k, n, s in q.all()]
        for r in out:
            r["label"] = named(r["key"]) if named else r["key"]
        return sorted(out, key=lambda r: -r["kr"])

    first = whole.with_entities(func.min(ApiSpend.created_at)).scalar()
    pct = round(100.0 * st["spent_kr"] / st["limit_kr"], 1) if st["limit_kr"] > 0 else 100.0
    people = sorted({e or "" for (e,) in whole.with_entities(ApiSpend.user_email).distinct().all()})
    sources = sorted({s or "" for (s,) in whole.with_entities(ApiSpend.source).distinct().all()})
    filtered = base.with_entities(func.count(ApiSpend.id), func.coalesce(func.sum(ApiSpend.kr), 0.0)).one()
    return {"limit_kr": st["limit_kr"], "spent_kr": st["spent_kr"], "remaining_kr": st["remaining_kr"],
            "exhausted": st["exhausted"], "used_pct": pct, "warning": warning_level(pct),
            "since": cfg.get("reset_at") or (first.isoformat() if first else None),
            "requests": int(whole.count()),
            "filtered": {"requests": int(filtered[0]), "kr": round(float(filtered[1] or 0), 2)},
            "people": people, "sources": [{"key": k, "label": label(k)} for k in sources],
            "by_source": grouped(ApiSpend.source, label), "by_user": grouped(ApiSpend.user_email),
            "by_model": grouped(ApiSpend.model),
            "recent": rows(db, since, until, who, source, limit=recent)}


# Varningar: alla ser en banner från 80 %, och administratörerna får ett meddelande (och ett mejl, om SMTP är
# inställt) en gång per nivå och budgetperiod.
LEVELS = (80, 95, 100)
ALERTS = "api:budget:alerts"
SHARED_START = "api:budget:shared_start"


def warning_level(pct: float) -> int:
    return max((lv for lv in LEVELS if pct >= lv), default=0)


def _mail_admins(db, subject: str, body: str) -> int:
    """Skicka till alla administratörer om VVS_SMTP_HOST är satt. Returnerar antalet mottagare."""
    import os
    host = os.environ.get("VVS_SMTP_HOST", "").strip()
    if not host:
        return 0
    import smtplib
    from email.message import EmailMessage
    from .db import User
    to = [u.email for u in db.query(User).filter(User.role == "admin").all() if u.email]
    if not to:
        return 0
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, os.environ.get("VVS_SMTP_FROM") or to[0], ", ".join(to)
    msg.set_content(body)
    port = int(os.environ.get("VVS_SMTP_PORT", "587"))
    with (smtplib.SMTP_SSL(host, port, timeout=20) if port == 465 else smtplib.SMTP(host, port, timeout=20)) as s:
        if port != 465:
            s.starttls()
        if os.environ.get("VVS_SMTP_USER"):
            s.login(os.environ["VVS_SMTP_USER"], os.environ.get("VVS_SMTP_PASSWORD", ""))
        s.send_message(msg)
    return len(to)


def alert(db) -> int | None:
    """Efter en bokförd kostnad: har budgeten gått över en ny nivå i den här perioden, säg det till
    administratörerna. Returnerar nivån som meddelades, eller None."""
    from .db import ContactMessage, ServiceSetting
    st = status(db)
    cfg = settings_of(db)
    pct = 100.0 * st["spent_kr"] / st["limit_kr"] if st["limit_kr"] > 0 else 100.0
    lv = warning_level(pct)
    if not lv:
        return None
    row = db.get(ServiceSetting, ALERTS)
    seen = dict((row.value or {}).get("v") or {}) if row is not None and isinstance(row.value, dict) else {}
    period = f"{cfg.get('reset_at') or ''}|{st['limit_kr']}"      # ett nytt tak eller en nollställning börjar om
    if seen.get("period") != period:
        seen = {"period": period, "sent": []}
    if lv in (seen.get("sent") or []):
        return None
    seen["sent"] = sorted(set(seen.get("sent") or []) | {lv})
    if row is None:
        db.add(ServiceSetting(key=ALERTS, value={"v": seen}))
    else:
        row.value = {"v": seen}
    subject = ("AI-budgeten är slut" if lv >= 100 else f"AI-budgeten: {lv} % använd")
    body = (f"Den gemensamma AI-budgeten har använt {st['spent_kr']:.2f} kr av {st['limit_kr']:.0f} kr "
            f"({pct:.1f} %). Kvar: {st['remaining_kr']:.2f} kr.\n\n"
            + ("AI-funktionerna är pausade för alla tills taket höjs eller räkningen nollställs under "
               "Administration -> AI-kostnad.\n" if lv >= 100 else
               "Alla inloggade ser en varning. Taket höjs eller räkningen nollställs under Administration -> AI-kostnad.\n")
            + "Vem som använt vad står under Credits.")
    db.add(ContactMessage(name="Dahl – AI-budget", email="", subject=subject, body=body, status="ny"))
    db.commit()
    try:
        _mail_admins(db, subject, body)
    except Exception:                                       # noqa: BLE001 - meddelandet står kvar i Administration
        log.warning("Mejlet om AI-budgeten kunde inte skickas", exc_info=True)
    return lv


def shared_start(db) -> bool:
    """En gång, första gången den gemensamma budgeten startar: taket blir 10 000 kr och räkningen börjar om, så att
    kostnader från provkörningar inte räknas. Raderna står kvar i reskontran. Returnerar True om det gjordes nu."""
    from .db import ServiceSetting
    if db.get(ServiceSetting, SHARED_START) is not None:
        return False
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    save(db, {"limit_kr": LIMIT_KR_DEFAULT, "reset_at": now})
    db.add(ServiceSetting(key=SHARED_START, value={"v": {"at": now}}))
    db.commit()
    return True


def blocked(model: str | None = None, db=None) -> str | None:
    """Why the service may not call `model` now, or None when it may."""
    if not _ACTIVE:
        return None
    from sqlalchemy.exc import SQLAlchemyError
    own = db is None
    db = db or _db()
    try:
        cfg = settings_of(db)
        if spent_kr(db, cfg) >= cfg["limit_kr"]:
            return EXHAUSTED
        if model is not None and price_for(model, cfg["prices"]) is None:
            return f"Priset för {model} saknas i prislistan - fyll i det under Administration."
        return None
    except SQLAlchemyError:
        # a database that cannot be read stops more than this; what is known about the price still holds
        log.warning("API-reskontran kunde inte läsas", exc_info=True)
        if model is not None and price_for(model, PRICE_DEFAULTS) is None:
            return f"Priset för {model} saknas i prislistan - fyll i det under Administration."
        return None
    finally:
        if own:
            db.close()


def require(model: str | None = None) -> None:
    """For an endpoint about to ask a language model: 402 with the reason when it may not."""
    why = blocked(model)
    if why:
        from fastapi import HTTPException
        raise HTTPException(402, why)


def check(model: str | None) -> None:
    """Before a request: raise BudgetExhausted when the service may not make it."""
    why = blocked(model)
    if why:
        raise BudgetExhausted(why)


def charge(model: str | None, tokens_in: int = 0, tokens_out: int = 0, cached: int = 0, cache_write: int = 0,
           source: str = "", audio_in: int = 0, audio_out: int = 0) -> float:
    """After a request: write what it cost. Returns the kronor; a request with no tokens costs nothing."""
    if not _ACTIVE or not (tokens_in or tokens_out):
        return 0.0
    from sqlalchemy.exc import SQLAlchemyError
    from .db import ApiSpend
    db = _db()
    try:
        cfg = settings_of(db)
        kr = cost_kr(model, tokens_in, tokens_out, cached, cache_write, cfg, audio_in, audio_out)
        price = dict(price_for(model, cfg["prices"]) or {}, usd_sek=cfg["usd_sek"])
        uid = WHO.get() or ""
        email = ""
        if uid:
            from .db import User
            u = db.get(User, uid)
            email = (u.email if u else "")[:255]
        db.add(ApiSpend(user_id=uid[:32], user_email=email, source=source[:32], model=(model or "")[:64],
                        tokens_in=int(tokens_in or 0),
                        tokens_out=int(tokens_out or 0), cached_tokens=int(cached or 0),
                        cache_write_tokens=int(cache_write or 0), kr=float(kr or 0.0), price=price))
        db.commit()
        try:
            alert(db)
        except Exception:                                   # noqa: BLE001 - en varning får aldrig fälla ett anrop
            log.warning("Varningen om AI-budgeten kunde inte skickas", exc_info=True)
        return float(kr or 0.0)
    except SQLAlchemyError:
        log.exception("API-kostnaden kunde inte bokföras")
        return 0.0
    finally:
        db.close()


def install_meter() -> None:
    """Switch the meter on in this process, and let the engine's own transports (engine/tools) ask and pay
    through this ledger."""
    global _ACTIVE
    _ACTIVE = True
    try:
        from tools import meter
    except ImportError:
        return
    meter.install(check, charge)


def uninstall_meter() -> None:
    """The service is stopping: nothing in this process asks through the ledger any more."""
    global _ACTIVE
    _ACTIVE = False
    try:
        from tools import meter
    except ImportError:
        return
    meter.install(None, None)
