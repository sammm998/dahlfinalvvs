"""Credits: vad en läsning kostar, vad ett konto har, och vad som hänt med det.

Priset sätts före läsningen och står i credits, aldrig i kronor: kronorna hör till paketen man köper credits
med, och de kan ändras utan att en läsning byter pris mitt i. Priset för ett blad följer det som faktiskt
avgör vad bladet kostar att läsa - pappersytan och mängden bläck (antal banor) - så att en A0-plan med
fyrtiotusen banor kostar mer än ett A3-blad med tusen. Talen är uppmätta (results/*-kostnad/KOSTNAD.md) och
prislistan kan flyttas av en administratör; det som står här är utgångsläget.

Två löften till den som betalar:

1. Priset visas innan läsningen körs, och det är det priset som dras. Ingen efterdebitering.
2. En läsning som inte kunde ge en enda meter - för att bladet saknar skala eller för att läsningen gick
   fel - kostar ingenting. Den betalas tillbaka av sig själv, med skälet i reskontran.

Reskontran är sanningen: saldot är summan av raderna. Kontot äger potten när användaren hör till ett konto,
annars användaren själv. Administratörer betalar inte för sina egna läsningar - det är tjänstens egna prov.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from .auth import current_admin, current_user
from .config import settings
from .db import Account, AnalysisJob, ContactMessage, CreditEntry, Drawing, ServiceSetting, User, get_db
from .storage import storage

router = APIRouter(tags=["credits"])

# ------------------------------------------------------------------------------------------------------------
# Prislistan
# ------------------------------------------------------------------------------------------------------------

# Storleksklass efter pappersyta, i m². A3 = 0,125, A2 = 0,25, A1 = 0,5, A0 = 1,0. Gränserna ligger mitt emellan
# formaten så att ett blad som skurits några millimeter ändå hamnar i sitt format.
SIZE_CLASSES = (("A3", 0.18), ("A2", 0.36), ("A1", 0.72), ("A0", 1.45), ("A0+", float("inf")))

PRICE_DEFAULTS: dict[str, Any] = {
    "sheet": {"A3": 1.0, "A2": 1.0, "A1": 2.0, "A0": 3.0, "A0+": 4.0},   # credits per sida efter format
    "ink_step_paths": 30000,           # banor per steg utöver det första steget ...
    "ink_step_credits": 0.5,           # ... och vad varje steg kostar
    "ink_cap_credits": 3.0,            # taket för bläcktillägget per sida
    "vision_page": 1.0,                # en andra blick med syn på en sida
    "raster_page": 1.0,                # tillägg för en sida som läses ur bildpunkter: en skanning eller en bild
    "rooms_factor": 1.0,               # ABT 06: rumsläsning av en A-plan, som andel av bladpriset
    "trial_credits": 5.0,              # vad ett nytt konto får att prova med
    "refund_when_unmeasured": True,    # en läsning utan en enda meter betalas tillbaka
    "packages": [
        {"id": "start", "name": "Start", "credits": 25, "kr": 249, "lead": "Ett par ritningar. Räcker för att jämföra med en handmängdning."},
        {"id": "kontor", "name": "Kontor", "credits": 100, "kr": 890, "lead": "Ett litet kontor en månad. Bästa värdet för de flesta."},
        {"id": "projekt", "name": "Projekt", "credits": 500, "kr": 3900, "lead": "En hel handling - alla plan, alla system."},
        {"id": "storkund", "name": "Storkund", "credits": 2000, "kr": 12900, "lead": "Löpande mängdning över flera projekt. Faktureras."},
    ],
}

# Vad en läsning kostar tjänsten - utgångsläget är uppmätt på korpusen och står med sina antaganden i
# results/*-kostnad/KOSTNAD.md. En administratör kan flytta talen; marginalen på adminsidan räknas ur dem.
COST_DEFAULTS: dict[str, Any] = {
    # Uppmätt 2026-09-12 på 296 blad (results/2026-09-12-kostnad/KOSTNAD.md): minsta kvadrat över bladen.
    "cpu_kr_per_hour": 1.03,           # en använd kärntimme, inklusive tomgång (VM 1 200 kr/mån, 4 vCPU, 40 % nyttjande)
    "cpu_s_per_1000_paths": 1.47,      # sekunder CPU per tusen banor
    "cpu_s_base": 17.4,                # fast del per sida: öppna, läsa namnruta, skala, skriva utdata
    "llm_kr_per_question": 0.052,      # andra läsaren: en avgränsad fråga, låg ansträngning, ~600 utmatade token
    "llm_questions_base": 1.7,         # frågor per sida oavsett storlek ...
    "llm_questions_per_1000_paths": 0.048,   # ... och per tusen banor
    "storage_kr_per_sheet": 0.03,      # utdata (median 10 MB) i lagret i tolv månader
    "payment_fee_pct": 1.5,            # kortavgift eller fakturering
    "vision_kr_per_page": 0.9,         # en synfråga med sidbilder
}


def _setting(db: Session, key: str, defaults: dict) -> dict:
    row = db.get(ServiceSetting, key)
    v = (row.value or {}).get("v") if row is not None and isinstance(row.value, dict) else None
    out = dict(defaults)
    if isinstance(v, dict):
        out.update(v)
    return out


def price_list(db: Session) -> dict:
    return _setting(db, "price:list", PRICE_DEFAULTS)


def cost_model(db: Session) -> dict:
    return _setting(db, "cost:model", COST_DEFAULTS)


def size_class(area_m2: float) -> str:
    for name, upper in SIZE_CLASSES:
        if area_m2 <= upper:
            return name
    return "A0+"


def _cc(credits: float) -> int:
    return int(round(credits * 100))


# ------------------------------------------------------------------------------------------------------------
# Vad ett blad kostar
# ------------------------------------------------------------------------------------------------------------

_MEASURED: dict[str, list[dict]] = {}   # sha256 -> per sida {area_m2, paths}; samma fil kostar samma sak


def measure_pages(path: str, sha: str | None = None) -> list[dict]:
    """Pappersyta och antal banor per sida - det som avgör priset, läst ur filen själv."""
    if sha and sha in _MEASURED:
        return _MEASURED[sha]
    import pymupdf
    from vvs_engine.pdf.classify import classify_page
    out = []
    with pymupdf.open(path) as doc:
        for pg in doc:
            area = pg.rect.width * pg.rect.height * (25.4 / 72 / 1000) ** 2
            drawings = pg.get_drawings()
            out.append({"area_m2": round(area, 4), "paths": len(drawings),
                        "mode": classify_page(pg, drawings=drawings).mode})
    # Sidorna läses ur bildpunkterna bara när handlingen inte har en enda vektorsida (vvs_engine/raster): det är då
    # skanningarna och bilderna kostar sitt tillägg. En skannad sida bland vektorsidor läses inte, och kostar inget extra.
    from_pixels = not any(p["mode"] in ("vector", "mixed") for p in out)
    for p in out:
        p["raster"] = from_pixels and p.pop("mode") == "raster"
    if sha:
        _MEASURED[sha] = out
    return out


def quote_pages(pages: list[dict], pl: dict) -> dict:
    """Priset i credits för de här sidorna, och hur det räknades - så att det kan visas, inte bara dras."""
    rows = []
    total = 0.0
    step = max(1, int(pl.get("ink_step_paths") or 30000))
    for i, p in enumerate(pages):
        sc = size_class(p["area_m2"])
        base = float((pl.get("sheet") or {}).get(sc, 2.0))
        steps = max(0, (int(p["paths"]) - 1) // step)
        ink = min(float(pl.get("ink_cap_credits") or 3.0), steps * float(pl.get("ink_step_credits") or 0.5))
        raster = float(pl.get("raster_page", 1.0) or 0.0) if p.get("raster") else 0.0
        rows.append({"page": i, "size_class": sc, "area_m2": p["area_m2"], "paths": p["paths"],
                     "base": base, "ink": round(ink, 2), "raster": round(raster, 2),
                     "credits": round(base + ink + raster, 2)})
        total += base + ink + raster
    return {"credits": round(total, 2), "pages": rows}


def quote_drawing(db: Session, d: Drawing) -> dict:
    pl = price_list(db)
    pages = measure_pages(storage.path(d.storage_key), d.sha256)
    q = quote_pages(pages, pl)
    q["drawing_id"] = d.id
    q["reason"] = "; ".join(f"sida {r['page'] + 1}: {r['size_class']} {r['base']:g} + bläck {r['ink']:g}"
                            + (f" + skannad {r['raster']:g}" if r.get("raster") else "") for r in q["pages"])
    return q


# ------------------------------------------------------------------------------------------------------------
# Reskontran
# ------------------------------------------------------------------------------------------------------------

def owner_key(user: User) -> str:
    return f"account:{user.account_id}" if user.account_id else f"user:{user.id}"


def balance_cc(db: Session, key: str) -> int:
    return int(db.query(func.coalesce(func.sum(CreditEntry.delta_cc), 0)).filter(CreditEntry.owner_key == key).scalar() or 0)


def balance(db: Session, user: User) -> float:
    return balance_cc(db, owner_key(user)) / 100.0


def is_exempt(user: User) -> bool:
    """Ingen läsning dras från ett konto längre. Alla konton delar en gemensam budget på 10 000 kr för det som
    faktiskt kostar pengar - anropen till språkmodeller (api_budget.py) - och den syns för alla under Credits.
    Läsning utan AI kostar ingenting."""
    return True


def post(db: Session, user: User | None, key: str, credits: float, kind: str, ref: str | None = None,
         note: str = "", status: str = "", amount_ore: int = 0) -> CreditEntry:
    e = CreditEntry(owner_key=key, user_id=user.id if user else None, delta_cc=_cc(credits), kind=kind, ref=ref,
                    note=note, status=status, amount_ore=amount_ore)
    db.add(e)
    db.flush()
    return e


def grant_trial(db: Session, user: User) -> None:
    """Ett nytt konto får sina provcredits en gång - kontrollerat i reskontran, inte i minnet."""
    pl = price_list(db)
    trial = float(pl.get("trial_credits") or 0)
    key = owner_key(user)
    if is_exempt(user) or trial <= 0 or db.query(CreditEntry).filter(CreditEntry.owner_key == key, CreditEntry.kind == "prov").first():
        return
    post(db, user, key, trial, "prov", note="Provcredits vid registrering")


def charge_for_reading(db: Session, user: User, d: Drawing, job: AnalysisJob) -> dict | None:
    """Dra priset för en läsning innan den startar. Returnerar det som skrivs på jobbet, eller None om inget dras.

    Räcker inte saldot stoppas jobbet innan det skapats, med priset och saldot i svaret så att sidan kan säga
    exakt vad som fattas.
    """
    if is_exempt(user):
        return None
    q = quote_drawing(db, d)
    key = owner_key(user)
    have = balance_cc(db, key)
    need = _cc(q["credits"])
    if have < need:
        raise HTTPException(402, {"message": f"Läsningen kostar {q['credits']:g} credits och kontot har {have / 100:g}.",
                                  "credits": q["credits"], "balance": have / 100, "missing": (need - have) / 100})
    post(db, user, key, -q["credits"], "lasning", ref=job.id,
         note=f"Läsning av {d.filename}: {q['reason']}")
    return {"charged": q["credits"], "owner": key, "pages": q["pages"]}


def refund_reading(db: Session, job: AnalysisJob, why: str) -> float:
    """Betala tillbaka en läsning som inte gav något - en gång, aldrig två."""
    debit = db.query(CreditEntry).filter(CreditEntry.ref == job.id, CreditEntry.kind == "lasning").first()
    if debit is None or db.query(CreditEntry).filter(CreditEntry.ref == job.id, CreditEntry.kind == "aterbetalning").first():
        return 0.0
    credits = -debit.delta_cc / 100.0
    post(db, None, debit.owner_key, credits, "aterbetalning", ref=job.id, note=why)
    return credits


def settle_after_reading(db: Session, job: AnalysisJob) -> None:
    """Efter en läsning: har den gett något? Annars kostar den ingenting.

    Ett blad utan fastställd skala ger inga meter, och en läsning som gick fel ger ingenting alls. Båda betalas
    tillbaka, och skälet står i reskontran så att ingen behöver fråga varför saldot hoppade upp.
    """
    pl = price_list(db)
    if not pl.get("refund_when_unmeasured", True):
        return
    if job.status == "FAILED":
        refund_reading(db, job, "Läsningen gick inte att genomföra")
        return
    # det som står på jobbet är summarize(): skalans tillstånd och läsningens täckning för första bladet
    from .jobs import sheet_coverage
    s = job.summary or {}
    cov = sheet_coverage(s)
    with_m = int(cov.get("pipe_names_with_metres") or 0)
    scale_state = s.get("scale") if isinstance(s.get("scale"), str) else cov.get("scale_state")
    unsettled = cov.get("scale_settled") is False or scale_state in (None, "NONE", "CONFLICT")
    if with_m == 0:
        why = ("Bladet är en sektion: rören mängdas på planritningarna" if cov.get("section")
               else "Bladet är ett schema, som inte ritas i skala: rören mängdas på planritningarna" if cov.get("schematic")
               else "Bladets skala är inte fastställd, så inga meter kunde ges" if unsettled
               else "Läsningen kunde inte ge någon beteckning en meter")
        refund_reading(db, job, why)


def charge_vision(db: Session, user: User, job: AnalysisJob, page: int) -> None:
    if is_exempt(user):
        return
    pl = price_list(db)
    price = float(pl.get("vision_page") or 0)
    if price <= 0:
        return
    key = owner_key(user)
    have = balance_cc(db, key)
    if have < _cc(price):
        raise HTTPException(402, {"message": f"En andra blick kostar {price:g} credits och kontot har {have / 100:g}.",
                                  "credits": price, "balance": have / 100, "missing": price - have / 100})
    post(db, user, key, -price, "syn", ref=job.id, note=f"Andra blick med syn, sida {page + 1}")
    db.commit()


# ------------------------------------------------------------------------------------------------------------
# Vad det kostar tjänsten, och marginalen
# ------------------------------------------------------------------------------------------------------------

def cost_of_pages(pages: list[dict], cm: dict) -> dict:
    """Kronor för att läsa de här sidorna, ur kostnadsmodellen. Ingen kredit här - bara kostnad."""
    cpu_s = sum(float(cm["cpu_s_base"]) + float(cm["cpu_s_per_1000_paths"]) * p["paths"] / 1000.0 for p in pages)
    cpu_kr = cpu_s / 3600.0 * float(cm["cpu_kr_per_hour"])
    questions = sum(float(cm.get("llm_questions_base") or 0.0) + float(cm["llm_questions_per_1000_paths"]) * p["paths"] / 1000.0 for p in pages)
    llm_kr = questions * float(cm["llm_kr_per_question"])
    storage_kr = float(cm["storage_kr_per_sheet"]) * len(pages)
    return {"cpu_s": round(cpu_s, 1), "cpu_kr": round(cpu_kr, 4), "llm_questions": round(questions, 1),
            "llm_kr": round(llm_kr, 3), "storage_kr": round(storage_kr, 3),
            "kr": round(cpu_kr + llm_kr + storage_kr, 3)}


def margin_table(pl: dict, cm: dict) -> list[dict]:
    """Typblad per format: pris i credits, kostnad i kronor, och marginalen vid varje pakets kronor per credit."""
    typical = {"A3": 4000, "A2": 9000, "A1": 18000, "A0": 30000, "A0+": 60000}
    out = []
    for sc, paths in typical.items():
        area = {"A3": 0.125, "A2": 0.25, "A1": 0.5, "A0": 1.0, "A0+": 2.0}[sc]
        q = quote_pages([{"area_m2": area, "paths": paths}], pl)
        c = cost_of_pages([{"area_m2": area, "paths": paths}], cm)
        row = {"size_class": sc, "paths": paths, "credits": q["credits"], "cost_kr": c["kr"], "per_package": []}
        for p in pl.get("packages") or []:
            kr_per_credit = float(p["kr"]) / float(p["credits"]) if p.get("credits") else 0.0
            revenue = q["credits"] * kr_per_credit
            fee = revenue * float(cm.get("payment_fee_pct") or 0) / 100.0
            row["per_package"].append({"id": p["id"], "kr_per_credit": round(kr_per_credit, 2),
                                       "revenue_kr": round(revenue, 2),
                                       "margin_kr": round(revenue - fee - c["kr"], 2),
                                       "margin_pct": round(100 * (revenue - fee - c["kr"]) / revenue, 1) if revenue else None})
        out.append(row)
    return out


# ------------------------------------------------------------------------------------------------------------
# Vägar
# ------------------------------------------------------------------------------------------------------------

def _entry_out(e: CreditEntry) -> dict:
    return {"id": e.id, "credits": e.delta_cc / 100.0, "kind": e.kind, "ref": e.ref, "note": e.note,
            "status": e.status, "kr": e.amount_ore / 100.0 if e.amount_ore else None, "created_at": e.created_at}


def _public_prices(pl: dict) -> dict:
    return {"sheet": pl.get("sheet"), "ink_step_paths": pl.get("ink_step_paths"), "ink_step_credits": pl.get("ink_step_credits"),
            "ink_cap_credits": pl.get("ink_cap_credits"), "vision_page": pl.get("vision_page"),
            "trial_credits": pl.get("trial_credits"), "refund_when_unmeasured": pl.get("refund_when_unmeasured", True),
            "packages": pl.get("packages") or []}


@router.get("/api/public/pricing")
def public_pricing(db: Session = Depends(get_db)):
    return _public_prices(price_list(db))


@router.get("/api/credits")
def my_credits(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Den gemensamma budgeten: samma svar för alla inloggade, oavsett konto."""
    from . import api_budget
    b = api_budget.shared(db)
    return {"shared": True, "budget": b, "balance": b["remaining_kr"], "exempt": True,
            "local_installation": settings.local_installation, "me": user.email}


@router.get("/api/drawings/{drawing_id}/price")
def drawing_price(drawing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.get(Drawing, drawing_id)
    if d is None or d.project.owner_id != user.id:
        raise HTTPException(404, "Ritningen finns inte")
    q = quote_drawing(db, d)
    have = balance(db, user)
    return {**q, "balance": have, "exempt": is_exempt(user), "enough": is_exempt(user) or have + 1e-9 >= q["credits"]}


class PurchaseIn(BaseModel):
    package_id: str


@router.post("/api/credits/purchase")
def purchase(body: PurchaseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Köp ett paket. Credits finns på kontot direkt; kronorna faktureras, och köpet står som fakturerat tills
    en administratör markerar det betalt. Ingen kortbetalning i den här vägen - den är byggd för firmor."""
    raise HTTPException(410, "Credits köps inte längre. Alla delar en gemensam budget på 10 000 kr, som syns under Credits.")
    pl = price_list(db)
    p = next((x for x in (pl.get("packages") or []) if x.get("id") == body.package_id), None)
    if p is None:
        raise HTTPException(404, "Paketet finns inte")
    key = owner_key(user)
    e = post(db, user, key, float(p["credits"]), "kop", ref=p["id"], status="fakturerad",
             amount_ore=int(round(float(p["kr"]) * 100)), note=f"Paketet {p['name']}: {p['credits']} credits för {p['kr']} kr exkl. moms")
    db.commit()
    return {"balance": balance_cc(db, key) / 100.0, "entry": _entry_out(e)}


class ContactIn(BaseModel):
    name: str
    email: EmailStr
    company: str = ""
    subject: str = ""
    message: str


@router.post("/api/public/contact")
def contact(body: ContactIn, db: Session = Depends(get_db)):
    text = body.message.strip()
    if len(text) < 5:
        raise HTTPException(422, "Skriv några ord om vad det gäller.")
    m = ContactMessage(name=body.name.strip()[:255], email=str(body.email).lower(), company=body.company.strip()[:255],
                       subject=body.subject.strip()[:255], body=text[:8000])
    db.add(m); db.commit()
    return {"ok": True, "id": m.id}


# --- administration -------------------------------------------------------------------------------------------

@router.get("/api/admin/pricing")
def admin_pricing(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    pl, cm = price_list(db), cost_model(db)
    return {"prices": pl, "costs": cm, "defaults": {"prices": PRICE_DEFAULTS, "costs": COST_DEFAULTS},
            "margin": margin_table(pl, cm)}


class PricingIn(BaseModel):
    prices: dict | None = None
    costs: dict | None = None
    note: str = ""


@router.put("/api/admin/pricing")
def admin_set_pricing(body: PricingIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    for key, val, defaults in (("price:list", body.prices, PRICE_DEFAULTS), ("cost:model", body.costs, COST_DEFAULTS)):
        if val is None:
            continue
        clean = {k: v for k, v in val.items() if k in defaults}
        if "packages" in clean:
            pk = []
            for p in clean["packages"] or []:
                try:
                    pk.append({"id": str(p["id"])[:32], "name": str(p.get("name") or p["id"])[:64],
                               "credits": max(1, int(p["credits"])), "kr": max(0.0, float(p["kr"])),
                               "lead": str(p.get("lead") or "")[:200]})
                except (KeyError, TypeError, ValueError):
                    raise HTTPException(422, "Ett paket behöver id, credits och kr.")
            clean["packages"] = pk
        for k, v in list(clean.items()):
            if k in ("sheet",) and isinstance(v, dict):
                clean[k] = {sc: max(0.0, float(v.get(sc, defaults[k][sc]))) for sc in defaults[k]}
            elif isinstance(defaults[k], bool):
                clean[k] = bool(v)
            elif isinstance(defaults[k], (int, float)):
                try:
                    clean[k] = max(0.0, float(v))
                except (TypeError, ValueError):
                    raise HTTPException(422, f"{k} ska vara ett tal.")
        row = db.get(ServiceSetting, key)
        if row is None:
            row = ServiceSetting(key=key, value={"v": clean}, note=body.note, updated_by=admin.id)
            db.add(row)
        else:
            row.value = {"v": {**((row.value or {}).get("v") or {}), **clean}}
            row.note = body.note or row.note
            row.updated_by = admin.id
    db.commit()
    return admin_pricing(admin, db)


@router.get("/api/admin/credits")
def admin_credits(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """Reskontran över alla konton: saldo, köp att fakturera, och vad läsningarna dragit."""
    by_owner = (db.query(CreditEntry.owner_key, func.sum(CreditEntry.delta_cc))
                .group_by(CreditEntry.owner_key).all())
    accounts = {a.id: a for a in db.query(Account).all()}
    users = {u.id: u for u in db.query(User).all()}
    owners = []
    for key, s in by_owner:
        kind, _, ident = key.partition(":")
        name = (accounts[ident].name if kind == "account" and ident in accounts else
                users[ident].email if kind == "user" and ident in users else key)
        owners.append({"owner": key, "name": name, "balance": (s or 0) / 100.0})
    owners.sort(key=lambda o: -o["balance"])
    purchases = (db.query(CreditEntry).filter(CreditEntry.kind == "kop")
                 .order_by(CreditEntry.created_at.desc()).limit(200).all())
    month = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
    used = db.query(func.coalesce(func.sum(CreditEntry.delta_cc), 0)).filter(CreditEntry.kind.in_(("lasning", "syn"))).scalar() or 0
    refunded = db.query(func.coalesce(func.sum(CreditEntry.delta_cc), 0)).filter(CreditEntry.kind == "aterbetalning").scalar() or 0
    sold_ore = db.query(func.coalesce(func.sum(CreditEntry.amount_ore), 0)).filter(CreditEntry.kind == "kop", CreditEntry.status != "makulerad").scalar() or 0
    return {"owners": owners, "purchases": [_entry_out(e) for e in purchases],
            "totals": {"credits_used": -used / 100.0, "credits_refunded": refunded / 100.0, "sold_kr": sold_ore / 100.0, "month": month}}


class GrantIn(BaseModel):
    owner: str            # "account:<id>" | "user:<id>" | en e-postadress
    credits: float
    note: str = ""


@router.post("/api/admin/credits/grant")
def admin_grant(body: GrantIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    key = body.owner.strip()
    if "@" in key:
        u = db.query(User).filter(User.email == key.lower()).first()
        if u is None:
            raise HTTPException(404, "Ingen användare med den adressen")
        key = owner_key(u)
    if not key.startswith(("account:", "user:")):
        raise HTTPException(422, "Ägaren skrivs som account:<id>, user:<id> eller en e-postadress")
    if abs(body.credits) < 0.01:
        raise HTTPException(422, "Ange ett antal credits skilt från noll")
    e = post(db, admin, key, float(body.credits), "tilldelning", note=body.note or f"Tilldelat av {admin.email}")
    db.commit()
    return {"entry": _entry_out(e), "balance": balance_cc(db, key) / 100.0}


class PurchaseStatusIn(BaseModel):
    status: str


@router.put("/api/admin/credits/purchases/{entry_id}")
def admin_purchase_status(entry_id: str, body: PurchaseStatusIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    e = db.get(CreditEntry, entry_id)
    if e is None or e.kind != "kop":
        raise HTTPException(404, "Köpet finns inte")
    if body.status not in ("fakturerad", "betald", "makulerad"):
        raise HTTPException(422, "Status är fakturerad, betald eller makulerad")
    if body.status == "makulerad" and e.status != "makulerad":
        # ett makulerat köp tar tillbaka sina credits - som en egen rad, så att historien står kvar
        post(db, admin, e.owner_key, -e.delta_cc / 100.0, "tilldelning", ref=e.id, note=f"Köpet {e.ref} makulerat")
    e.status = body.status
    db.commit()
    return _entry_out(e)


@router.get("/api/admin/contact")
def admin_contact(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    rows = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(300).all()
    return {"rows": [{"id": m.id, "name": m.name, "email": m.email, "company": m.company, "subject": m.subject,
                      "body": m.body, "status": m.status, "created_at": m.created_at} for m in rows]}


class ContactStatusIn(BaseModel):
    status: str


@router.put("/api/admin/contact/{message_id}")
def admin_contact_status(message_id: str, body: ContactStatusIn, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    m = db.get(ContactMessage, message_id)
    if m is None:
        raise HTTPException(404, "Meddelandet finns inte")
    if body.status not in ("ny", "besvarad", "stangd"):
        raise HTTPException(422, "Status är ny, besvarad eller stangd")
    m.status = body.status
    db.commit()
    return {"id": m.id, "status": m.status}
