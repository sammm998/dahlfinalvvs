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
            cfg: dict | None = None) -> float | None:
    """What a request cost, in kronor; None when the model has no price. tokens_in counts every input token,
    the cached ones included, as the providers report them."""
    cfg = cfg or {}
    p = price_for(model, cfg.get("prices") or PRICE_DEFAULTS)
    if p is None:
        return None
    tin, tout = max(0, int(tokens_in or 0)), max(0, int(tokens_out or 0))
    cached, write = max(0, int(cached or 0)), max(0, int(cache_write or 0))
    fresh = max(0, tin - cached - write)
    usd = (fresh * float(p["in"]) + tout * float(p["out"]) + cached * float(p.get("cached", p["in"]))
           + write * float(p.get("cache_write", p["in"]))) / 1e6
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
           source: str = "") -> float:
    """After a request: write what it cost. Returns the kronor; a request with no tokens costs nothing."""
    if not _ACTIVE or not (tokens_in or tokens_out):
        return 0.0
    from sqlalchemy.exc import SQLAlchemyError
    from .db import ApiSpend
    db = _db()
    try:
        cfg = settings_of(db)
        kr = cost_kr(model, tokens_in, tokens_out, cached, cache_write, cfg)
        price = dict(price_for(model, cfg["prices"]) or {}, usd_sek=cfg["usd_sek"])
        db.add(ApiSpend(source=source[:32], model=(model or "")[:64], tokens_in=int(tokens_in or 0),
                        tokens_out=int(tokens_out or 0), cached_tokens=int(cached or 0),
                        cache_write_tokens=int(cache_write or 0), kr=float(kr or 0.0), price=price))
        db.commit()
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
