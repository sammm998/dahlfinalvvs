"""Kalkylen och anbudet: från mängd till pris.

En mängd är meter och antal. Ett anbud är tid och pengar. Det här är bron, i två steg som hålls isär så att
varje krona går att spåra tillbaka till en rad på ritningen:

  * **Material.** Varje beteckning matchas mot materialboken - bladets egen förklaringslista säger vad
    materialkoden betyder, dimensionen står i beteckningen - och får en artikel med nettopris. Matchningen är
    ett FÖRSLAG med alternativ bredvid; den som räknar väljer, och valet sparas.
  * **Arbete.** Timmarna kommer ur Normtid VVS (`vvs_engine.normtid`): grundtid per meter efter dimension och
    material, tillägg för skarvmetod och höjd, och avvikelseanalysens bedömning av objektet. Där boken inte har
    någon tid står det - en gissad normtid är värre än ingen, för den ser ut som ett besked.

Sedan spill, påslag och moms, allt utskrivet. Anbudet är samma tal i en form en beställare kan läsa, med
förutsättningarna och förbehållen på samma papper som summan.

Ingenting här rör läsningen. Kalkylen läser mängderna med kundens rättelser ovanpå - samma meter som står på
bladet - och skriver aldrig tillbaka.
"""
from __future__ import annotations

import datetime as dt
import html
import io
import json
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .config import settings
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from vvs_engine import normtid as NT

from .auth import current_user
from .db import AnalysisJob, Calculation, User, get_db
from .storage import storage

router = APIRouter(prefix="/api/jobs", tags=["kalkyl"])

# ------------------------------------------------------------------------------------------------------------
# antaganden
# ------------------------------------------------------------------------------------------------------------
DEFAULTS = {
    "timpris": 650.0,            # kr per timme, montör
    "spill_pct": 5.0,            # kalkylmängd = netto + spill (lathunden §28)
    "paslag_material_pct": 12.0,
    "paslag_arbete_pct": 10.0,
    "moms_pct": 25.0,
    "floor_height_m": 2.8,       # en stigare räknas som en våningshöjd när ritningen inte säger höjden (facit räknar 2,80 m)
    "supplements": ["pressfog"],  # normtidens tillägg: skarvmetod, höjd, ombyggnad
    "factors": {},               # avvikelseanalysen: faktor-id -> -4..+4
    "valid_days": 30,
    "regelverk": "ABT 06",       # avtalsvillkoren anbudet lämnas under: ABT 06, AB 04, ABS 18, Hantverkarformuläret 17, eller inget
    "betalning": "30 dagar netto mot faktura, enligt betalningsplan",
    "company": "", "customer": "", "reference": "", "intro": "",
}

# Standardavtalen en svensk VVS-entreprenör lämnar anbud under, och vad var och ett brukar innebära för anbudet.
# Klausulerna är anbudets EGNA förbehåll under respektive regelverk - inte återgivningar av avtalstexten - och den
# som räknar kan byta regelverk eller stryka dem i förhandsgranskningen innan anbudet lämnas.
REGELVERK: dict[str, dict] = {
    "ABT 06": {
        "label": "ABT 06 - Allmänna bestämmelser för totalentreprenader",
        "clauses": [
            "Anbudet lämnas enligt ABT 06 med de ändringar och tillägg som anges i förfrågningsunderlaget.",
            "Ändringar, tilläggs- och avgående arbeten (ÄTA) regleras enligt ABT 06 kap. 2 och ersätts enligt "
            "à-prislista eller på löpande räkning om inte annat avtalas skriftligt.",
            "Garantitid enligt ABT 06 kap. 4 § 7: fem år för entreprenaden, två år för material och varor.",
            "Funktionsansvaret omfattar de funktionskrav som anges i förfrågningsunderlaget; projektering ingår "
            "i den omfattning handlingarna anger.",
        ],
    },
    "AB 04": {
        "label": "AB 04 - Allmänna bestämmelser för utförandeentreprenader",
        "clauses": [
            "Anbudet lämnas enligt AB 04 med de ändringar och tillägg som anges i förfrågningsunderlaget.",
            "Ändringar, tilläggs- och avgående arbeten (ÄTA) regleras enligt AB 04 kap. 2 och ersätts enligt "
            "à-prislista eller på löpande räkning om inte annat avtalas skriftligt.",
            "Garantitid enligt AB 04 kap. 4 § 7: fem år för arbetsprestation, två år för material och varor.",
            "Entreprenaden utförs enligt beställarens handlingar; ansvaret för projekteringen ligger hos beställaren.",
        ],
    },
    "ABS 18": {
        "label": "ABS 18 - Allmänna bestämmelser för småhusentreprenader",
        "clauses": [
            "Anbudet lämnas enligt ABS 18; konsumenttjänstlagen gäller och kan inte avtalas bort till konsumentens nackdel.",
            "Ändringar och tilläggsarbeten beställs skriftligt och prissätts innan de påbörjas.",
            "Garantitid enligt ABS 18: två år från slutbesiktningen, med ansvar för fel enligt konsumenttjänstlagen därefter.",
        ],
    },
    "Hantverkarformuläret 17": {
        "label": "Hantverkarformuläret 17 - reparations- och ombyggnadsarbeten åt konsument",
        "clauses": [
            "Anbudet lämnas enligt Hantverkarformuläret 17; konsumenttjänstlagen gäller.",
            "Tilläggsarbeten utförs efter överenskommelse och ersätts enligt angivet timpris och materialpris.",
            "ROT-avdrag hanteras enligt gällande regler och förutsätter att beställaren uppfyller villkoren.",
        ],
    },
}

# Ytterdiameter för en nominell dimension. Metallrör: DN -> dy enligt gängse rörtabell; plaströr (avlopp) har
# ytterdiametern som beteckning, så där är DN redan dy. Normtidens tabeller går på dy.
DN_TO_DY_METAL = {10: 12.0, 12: 15.0, 15: 18.0, 16: 18.0, 18: 18.0, 20: 22.0, 22: 22.0, 25: 28.0, 28: 28.0,
                  32: 35.0, 35: 35.0, 40: 42.0, 42: 42.0, 50: 54.0, 54: 54.0, 65: 76.1, 80: 88.9, 100: 114.3,
                  125: 139.7, 150: 168.3, 200: 219.1}
PLASTIC_LETTERS = ("P", "R", "E", "G")     # PP, PEM/PE, PVC ... - avlopps- och markrör i plast
STOP = {"och", "med", "för", "av", "i", "till", "enligt", "typ", "el", "eller", "samt", "mm", "m", "st",
        "ledningar", "ledning", "rör", "röret"}

# Materialklasser: vad förklaringens ord betyder, och vilka ord boken använder för samma sak. Förklaringen på
# bladet säger "LEDNINGAR AV ROSTFRIA RÖR"; boken säger "rostfritt rör", "rf AISI 304" eller "1.4432". Ingen
# av dem använder den andras ord, så klassen är bron: ett mönster för förklaringen, ett för artikelnamnet.
MATERIAL_CLASSES: list[tuple[str, str, str, bool]] = [
    # (klass, mönster i förklaringen, mönster i artikelnamnet, plaströr)
    ("pex",     r"pe-?x|ipe-?x|\brir\b|rör.?i.?rör|multipex|sanipex", r"pex|pe-x|\brir\b|rör i rör|kombirör", True),
    ("koppar",  r"koppar|\bcu\b",                                   r"koppar|cupori|\bcu\b",                  False),
    ("rostfri", r"rostfri|syrafast|\brf\b|aisi|1[.,]44",               r"rostfri|syrafast|\brf\b|aisi|1[.,]44",   False),
    ("pp",      r"\bpp\b|pp-|polypropen|\bhtp\b",                    r"\bpp\b|pp-|polypropen|\bhtp\b",         True),
    ("pe",      r"\bpem\b|\bpeh\b|\bpe\s?\d{2,3}\b|polyet(en|ylen)",  r"\bpem\b|\bpeh\b|\bpe\d{2,3}|pe-rör|\bpe\b", True),
    ("pvc",     r"pvc",                                                r"pvc",                                     True),
    ("gjut",    r"gjut|\bgjj\b|segjärn|\bsml\b|\bma-?rör",              r"\bgjj\b|gjut|segjärn|\bsml\b|ma-rör",      False),
    ("galv",    r"förzink|galv",                                       r"förzink|galv",                            False),
    ("stal",    r"stål|svart|tunnvägg|mapress|kolstål|\bsms\b",         r"stål|svartrör|tunnvägg|mapress|kolstål",   False),
]
_CLASS = {c[0]: c for c in MATERIAL_CLASSES}


def _legend_text(code: str, legend: list[dict]) -> str:
    code = (code or "").upper()
    for e in legend or []:
        c = str(e.get("code") or e.get("kod") or "").upper()
        if c and c == code:
            return str(e.get("description") or e.get("text") or e.get("label") or "")
    return ""


def _material_class(text: str) -> str | None:
    """Klassen ur förklaringens ord - eller ingen. En bokstav utan förklaring säger inte vad röret är gjort av
    (R8 var rostfritt på ett blad och skulle kunna vara PE på nästa), så här gissas inget."""
    t = (text or "").lower()
    for klass, in_legend, _, _ in MATERIAL_CLASSES:
        if re.search(in_legend, t):
            return klass
    return None


def _material_words(code: str, legend: list[dict]) -> list[str]:
    """Orden som visar vad raden matchades på: klassen först, sedan förklaringens egna ord."""
    text = _legend_text(code, legend)
    klass = _material_class(text)
    words = [w for w in re.findall(r"[a-zåäöA-ZÅÄÖ][a-zåäö0-9A-ZÅÄÖ-]{2,}", text.lower()) if w not in STOP and w != klass]
    return ([klass] if klass else []) + words[:3]


def _is_plastic(code: str, klass: str | None = None) -> bool:
    if klass and klass in _CLASS:
        return _CLASS[klass][3]
    return (code or "").upper()[:1] in PLASTIC_LETTERS


def _split(base: str) -> tuple[str, str]:
    """System och materialkod ur beteckningens stam: KV01-X7-W40 -> (KV01, X7)."""
    parts = [p for p in (base or "").split("-") if p]
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")


def _book() -> dict:
    from .main import _material_book
    return _material_book()


def _leading_dim(name: str) -> float | None:
    """Dimensionen ett artikelnamn börjar med: '18x1,0 Cupori', '75 Blücher', 'Dy48 ...', '76,1x3,0 rör'."""
    m = re.match(r"\s*(?:dy|dn|d|ø)?\s*(\d+(?:[.,]\d+)?)(?![.,]?\d)", name or "", re.I)
    if not m:
        m = re.search(r"\b(\d+(?:[.,]\d+)?)x\d", name or "")
    return float(m.group(1).replace(",", ".")) if m else None


def _dims_for(dn: int | None, plastic: bool) -> set[float]:
    """Talen boken kan skriva för en nominell dimension: DN själv, och för metallrör ytterdiametern."""
    if not dn:
        return set()
    out = {float(dn)}
    if not plastic and dn in DN_TO_DY_METAL:
        out.add(DN_TO_DY_METAL[dn])
    return out


def _shape(r: dict) -> dict:
    p = r.get("p")
    net = None if p is None else round(float(p) * (1 - float(r.get("r") or 0)), 2)
    return {"a": r["a"], "n": r["n"], "e": r.get("e"), "brutto": p, "netto": net, "w": r.get("w"), "co2": r.get("co2")}


def _find_articles(words: list[str], dn: int | None, unit: str = "m", limit: int = 6,
                   klass: str | None = None, plastic: bool = False) -> list[dict]:
    """Metervaror i rätt material och rätt dimension, bäst först.

    Materialet är ett krav när klassen är känd, dimensionen ett krav när den står i beteckningen. Bland dem som
    klarar båda går ett riktigt pris före ett tomt, sedan vinner den som bär flest av förklaringens egna ord
    (säger förklaringen RIR vinner rör-i-rör), sedan ett rör före annat, sedan det billigaste. Utan känd klass
    returneras rör i rätt dimension som ALTERNATIV att välja bland - inget väljs åt någon."""
    rows = _book()["rows"]
    if klass is None and words:
        klass = _material_class(" ".join(words))
    in_name = re.compile(_CLASS[klass][2], re.I) if klass else None
    dims = _dims_for(dn, plastic if klass is None else _CLASS[klass][3])
    extra = [w for w in words if w != klass and len(w) >= 3]
    scored = []
    for r in rows:
        if (r.get("e") or "").lower() != unit:
            continue
        n = r.get("n") or ""
        if in_name is not None and not in_name.search(n):
            continue
        if in_name is None and "rör" not in n.lower():
            continue
        if dims:
            d = _leading_dim(n)
            if d is None or not any(abs(d - x) <= 0.6 for x in dims):
                continue
        low = n.lower()
        hits = sum(1 for w in extra if w in low)
        price = float(r.get("p") or 0.0)
        scored.append((price < 1.0, -hits, "rör" not in low, price, len(n), r))
    scored.sort(key=lambda t: t[:5])
    return [_shape(r) for *_, r in scored[:limit]]


def _article_by_number(a: str) -> dict | None:
    for r in _book()["rows"]:
        if r["a"] == a:
            return _shape(r)
    return None


def _norm_hours_per_m(dn: int | None, plastic: bool, riser: bool) -> tuple[float | None, str]:
    """Grundtid per meter ur boken, och vilken tabell den kom ur. Ingen tid är ett svar."""
    if dn is None:
        return None, "dimension saknas"
    # Plaströr och rostfria avloppsrör (75, 110, 160) bär ytterdiametern som beteckning; för övriga metallrör
    # står DN på bladet och boken går på dy. En DN utanför rörtabellen läses som dy - det är vad den är på de
    # blad som skriver så, och boken svarar ändå bara inom sina egna band.
    dy = float(dn) if plastic else DN_TO_DY_METAL.get(int(dn), float(dn))
    if not riser and not plastic and dy <= 35.0:
        t = NT.base_time("kopplingsledning", dy, 1)
        if t is not None:
            return t, "Kopplingsledningar (s. 33)"
    t = NT.base_time("stammar", dy, 2 if plastic else 1)
    return (t, "Stammar (s. 30)") if t is not None else (None, f"boken har ingen tid för dy {dy:g}")


def _deviation_pct(factors: dict) -> float:
    total = 0.0
    for fid, v in (factors or {}).items():
        f = NT.FACTOR_BY_ID.get(fid)
        if f is None:
            continue
        try:
            v = int(v)
        except (TypeError, ValueError):
            continue
        if v in f.scale:
            total += v
    return total


# ------------------------------------------------------------------------------------------------------------
# kalkylen
# ------------------------------------------------------------------------------------------------------------
def build(rows: list[dict], legend: list[dict], assumptions: dict, overrides: dict) -> dict:
    """Kalkylen ur mängdraderna. Varje rad bär sina egna steg, så en krona går att spåra till en meter."""
    A = {**DEFAULTS, **{k: v for k, v in (assumptions or {}).items() if k in DEFAULTS}}
    dev = _deviation_pct(A.get("factors") or {})
    sup = [s for s in (A.get("supplements") or []) if s in NT.SUPPLEMENT_BY_ID]
    out_rows = []
    caveats: list[str] = []
    for q in rows:
        name = q.get("designation") or ""
        if not name:
            continue
        ov = (overrides or {}).get(name) or {}
        system, mcode = _split(q.get("base") or name)
        dn = q.get("dn")
        words = _material_words(mcode, legend)
        klass = words[0] if words and words[0] in _CLASS else None
        plastic = _is_plastic(mcode, klass)
        horiz = float(q.get("confirmed_horizontal_m") or 0.0)
        risers = int(max(q.get("riser_count") or 0, q.get("riser_count_from_labels") or 0))
        vert = risers * float(q.get("riser_height_m") or A["floor_height_m"])   # en radiatoranslutning är 1,0 m
        netto_m = horiz + vert
        kalkyl_m = netto_m * (1 + float(A["spill_pct"]) / 100.0)

        # material: förslaget, alternativen, eller det som valdes. Utan känd materialklass föreslås inget -
        # alternativen finns att välja bland, men ett rör i fel material prissatt med säker min är värre än en
        # tom ruta.
        alts = _find_articles(words, dn, klass=klass, plastic=plastic) if (klass or dn) else []
        art = _article_by_number(ov["artikel"]) if ov.get("artikel") else (alts[0] if alts and klass else None)
        unit_price = None if art is None else art.get("netto")
        material_kr = round(unit_price * kalkyl_m, 2) if unit_price is not None else None

        # arbete: grundtid ur boken, tillägg, avvikelse - eller en timme någon skrev själv
        base, source = _norm_hours_per_m(dn, plastic, riser=False)
        base_r, source_r = _norm_hours_per_m(dn, plastic, riser=True)
        if ov.get("timmar") is not None:
            timmar = float(ov["timmar"]); steps = {"timmar": timmar}; source = "angiven för hand"
        elif base is not None:
            steps_h = NT.hours(base, horiz, sup, dev)
            steps_v = NT.hours(base_r, vert, sup, dev) if base_r is not None and vert else {"timmar": 0.0}
            timmar = round(steps_h["timmar"] + steps_v["timmar"], 3)
            steps = {"grundtid_per_m": base, "grundtid": steps_h["grundtid"], "tillagg_pct": steps_h["tillagg_pct"],
                     "avvikelse_pct": steps_h["avvikelse_pct"], "stigare_timmar": steps_v["timmar"], "timmar": timmar}
        else:
            timmar = None; steps = {}
        arbete_kr = round(timmar * float(A["timpris"]), 2) if timmar is not None else None

        row = {"designation": name, "system": system, "material_kod": mcode, "dn": dn,
               "material_ord": words, "plast": plastic,
               "horisontellt_m": round(horiz, 2), "stigare": risers, "vertikalt_m": round(vert, 2),
               "netto_m": round(netto_m, 2), "kalkyl_m": round(kalkyl_m, 2),
               "artikel": art, "alternativ": alts, "a_pris": unit_price, "material_kr": material_kr,
               "normtid_kalla": source, "steg": steps, "timmar": timmar, "arbete_kr": arbete_kr,
               "summa_kr": round((material_kr or 0) + (arbete_kr or 0), 2),
               "vald_artikel": bool(ov.get("artikel")), "timmar_for_hand": ov.get("timmar") is not None}
        out_rows.append(row)
        if art is None and klass is None:
            caveats.append(f"{name}: materialet framgår inte av bladets förklaring ({mcode or 'ingen kod'}) - välj artikel.")
        elif art is None:
            caveats.append(f"{name}: ingen artikel i materialboken för {klass} DN{dn or '?'} - välj en.")
        if timmar is None:
            caveats.append(f"{name}: normtid saknas ({source}) - ange timmar.")

    mat = sum(r["material_kr"] or 0 for r in out_rows)
    hrs = sum(r["timmar"] or 0 for r in out_rows)
    arb = sum(r["arbete_kr"] or 0 for r in out_rows)
    pm = mat * float(A["paslag_material_pct"]) / 100.0
    pa = arb * float(A["paslag_arbete_pct"]) / 100.0
    netto = mat + arb + pm + pa
    moms = netto * float(A["moms_pct"]) / 100.0
    totals = {"material_kr": round(mat, 2), "timmar": round(hrs, 2), "arbete_kr": round(arb, 2),
              "paslag_material_kr": round(pm, 2), "paslag_arbete_kr": round(pa, 2),
              "netto_kr": round(netto, 2), "moms_kr": round(moms, 2), "brutto_kr": round(netto + moms, 2),
              "rader": len(out_rows), "utan_artikel": sum(1 for r in out_rows if r["artikel"] is None),
              "utan_normtid": sum(1 for r in out_rows if r["timmar"] is None)}
    return {"assumptions": A, "avvikelse_pct": dev, "rows": out_rows, "totals": totals, "caveats": caveats}


# ------------------------------------------------------------------------------------------------------------
# underlaget ur läsningen
# ------------------------------------------------------------------------------------------------------------
def _job(db: Session, user: User, job_id: str) -> AnalysisJob:
    j = db.get(AnalysisJob, job_id)
    if j is None or j.drawing.project.owner_id != user.id:
        raise HTTPException(404, "Analysen finns inte")
    if j.status != "COMPLETED" or not j.result_key:
        raise HTTPException(409, "Analysen är inte klar - kalkylen räknar på det som lästs, aldrig på något annat")
    return j


def _inputs(db: Session, j: AnalysisJob) -> tuple[list[dict], list[dict]]:
    from .projects_api import _rows_of
    rows = _rows_of(db, j)
    rd = storage.path(j.result_key)
    legend = []
    p = os.path.join(rd, "drawing-legend.json")
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8") as fh:
            legend = (json.load(fh) or {}).get("entries") or []
    return rows, legend


class CalcIn(BaseModel):
    assumptions: dict = Field(default_factory=dict)
    overrides: dict = Field(default_factory=dict)      # beteckning -> {artikel, timmar}


@router.get("/{job_id}/calc/underlag")
def underlag(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Normtidsunderlaget och standardantagandena, så att gränssnittet kan visa vad som går att ställa in."""
    _job(db, user, job_id)
    return {"defaults": DEFAULTS, "normtid": NT.catalogue(),
            "regelverk": [{"id": k, "label": v["label"], "clauses": v["clauses"]} for k, v in REGELVERK.items()]}


@router.post("/{job_id}/calc/preview")
def preview(job_id: str, body: CalcIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = _job(db, user, job_id)
    rows, legend = _inputs(db, j)
    return build(rows, legend, body.assumptions, body.overrides)


@router.put("/{job_id}/calc")
def save(job_id: str, body: CalcIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Spara kalkylen: antagandena och valen. Talen räknas om ur läsningen varje gång - de är aldrig lagrade fakta."""
    j = _job(db, user, job_id)
    rows, legend = _inputs(db, j)
    calc = build(rows, legend, body.assumptions, body.overrides)
    c = db.query(Calculation).filter(Calculation.job_id == j.id).order_by(Calculation.created_at.desc()).first()
    if c is None:
        c = Calculation(job_id=j.id, user_id=user.id)
        db.add(c)
    c.assumptions, c.overrides, c.totals = calc["assumptions"], body.overrides, calc["totals"]
    db.commit()
    return {**calc, "saved_at": c.updated_at.isoformat() if c.updated_at else None}


@router.get("/{job_id}/calc")
def latest(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = _job(db, user, job_id)
    c = db.query(Calculation).filter(Calculation.job_id == j.id).order_by(Calculation.created_at.desc()).first()
    if c is None:
        return {"status": "NONE"}
    rows, legend = _inputs(db, j)
    return {"status": "SAVED", **build(rows, legend, c.assumptions or {}, c.overrides or {}),
            "saved_at": c.updated_at.isoformat() if c.updated_at else None}


# ------------------------------------------------------------------------------------------------------------
# anbudet
# ------------------------------------------------------------------------------------------------------------
def _kr(v: float | None) -> str:
    if v is None:
        return "–"
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " kr"


def _num(v: float | None, d: int = 2) -> str:
    return "–" if v is None else f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


# Anbudet är satt i Liberation Sans. Typsnittet installeras i bilden (fonts-liberation i Dockerfile), men om
# det ändå saknas ska anbudet skrivas i läsarens eget Helvetica i stället för att inte skrivas alls: ett anbud
# som ser en aning annorlunda ut går att lämna, ett anbud som inte går att hämta gör det inte. Det var precis
# det som hände - bilden bar inga typsnitt alls, och varje anbudsanrop svarade med fel.
FONT_DIRS = ("/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/liberation2",
             "/usr/share/fonts/liberation", "/usr/share/fonts/liberation-sans")
FONT_DIR = FONT_DIRS[0]
FONT_REGULAR = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")


def font_dir() -> str | None:
    """Katalogen där båda snitten ligger, eller None: då sätts anbudet i ett inbyggt snitt."""
    for d in FONT_DIRS:
        if all(os.path.isfile(os.path.join(d, f"LiberationSans-{w}.ttf")) for w in ("Regular", "Bold")):
            return d
    return None


def _font_file(bold: bool) -> str | None:
    d = font_dir()
    return None if d is None else os.path.join(d, f"LiberationSans-{'Bold' if bold else 'Regular'}.ttf")


def _css(base: str = "") -> str:
    """Anbudets CSS. Utan typsnittsfiler faller den tillbaka på ett snitt läsaren alltid har."""
    css = base or TENDER_CSS
    if font_dir() is not None:
        return css
    return (css.replace("@font-face { font-family: Lib; src: url(LiberationSans-Regular.ttf); }", "")
               .replace("@font-face { font-family: Lib; font-weight: bold; src: url(LiberationSans-Bold.ttf); }", "")
               .replace("font-family: Lib", "font-family: sans-serif"))
INK = (0.09, 0.12, 0.15)          # #171f27
NAVY = (0.06, 0.16, 0.23)         # #0f2a3a
TEAL = (0.07, 0.62, 0.69)         # #129eb0
MUTED = (0.42, 0.47, 0.52)
LINE = (0.86, 0.88, 0.90)


def tender_meta(calc: dict, meta: dict) -> dict:
    """Det anbudet skriver i sitt huvud: parter, objekt, datum, giltighet, nummer."""
    A = calc["assumptions"]
    today = dt.date.today()
    return {
        "company": A.get("company") or meta.get("company") or settings.app_name,
        "customer": A.get("customer") or "–",
        "project": meta.get("project") or "–",
        "drawing": meta.get("drawing") or "",
        "reference": A.get("reference") or "–",
        "number": f"A-{today:%Y%m%d}-{(meta.get('job') or 'X')[:8]}",
        "date": today.isoformat(),
        "valid": (today + dt.timedelta(days=int(A.get("valid_days") or 30))).isoformat(),
        "regelverk": A.get("regelverk") if A.get("regelverk") in REGELVERK else "",
    }


def tender_html(calc: dict, meta: dict) -> str:
    """Anbudets kropp: samma tal som kalkylen, i en form en beställare läser. Inledning, specifikation rad för
    rad, vad summan förutsätter, vad som förbehålls, och plats för underskrift. Huvudet och summeringen ritas
    ovanpå av tender_pdf; i webbläsaren skrivs de av anbud_html."""
    A = calc["assumptions"]; T = calc["totals"]; M = tender_meta(calc, meta)
    e = html.escape
    sup_labels = [NT.SUPPLEMENT_BY_ID[s].label for s in A.get("supplements") or [] if s in NT.SUPPLEMENT_BY_ID]
    rows_html = "".join(
        f"<tr><td class='n'>{i + 1}</td><td><b>{e(r['designation'])}</b><br><span class='muted'>"
        f"{e(r['artikel']['n']) if r['artikel'] else 'artikel ej vald'}</span></td>"
        f"<td class='r'>{_num(r['kalkyl_m'])} m</td><td class='r'>{_kr(r['material_kr'])}</td>"
        f"<td class='r'>{_num(r['timmar'])}</td><td class='r'>{_kr(r['arbete_kr'])}</td>"
        f"<td class='r'><b>{_kr(r['summa_kr'])}</b></td></tr>"
        for i, r in enumerate(calc["rows"]))
    caveats = "".join(f"<li>{e(c)}</li>" for c in calc["caveats"])
    rules = REGELVERK.get(M["regelverk"], {}).get("clauses", [])
    rules_html = "".join(f"<li>{e(c)}</li>" for c in rules)
    intro = e(A.get("intro") or
              "Vi tackar för förfrågan och lämnar härmed anbud på rörinstallationer enligt bifogad handling. "
              "Mängderna är lästa ur ritningens egna vektorer och kan spåras rad för rad till bladet; "
              "förutsättningarna och förbehållen står nedan, på samma papper som summan.")
    return f"""<html><body>
<p class="intro">{intro}</p>
<h2>Specifikation</h2>
<table class="spec"><tr><th class='n'>#</th><th>Post</th><th class='r'>Kalkylmängd</th><th class='r'>Material</th>
<th class='r'>Timmar</th><th class='r'>Arbete</th><th class='r'>Summa</th></tr>{rows_html}
<tr class="sum"><td></td><td>Material och arbete</td><td></td><td class='r'>{_kr(T['material_kr'])}</td>
<td class='r'>{_num(T['timmar'])}</td><td class='r'>{_kr(T['arbete_kr'])}</td><td class='r'>{_kr(T['material_kr'] + T['arbete_kr'])}</td></tr>
<tr><td></td><td>Påslag material {_num(A['paslag_material_pct'], 0)} %</td><td></td><td></td><td></td><td></td><td class='r'>{_kr(T['paslag_material_kr'])}</td></tr>
<tr><td></td><td>Påslag arbete {_num(A['paslag_arbete_pct'], 0)} %</td><td></td><td></td><td></td><td></td><td class='r'>{_kr(T['paslag_arbete_kr'])}</td></tr>
<tr class="sum"><td></td><td><b>Anbudssumma exkl. moms</b></td><td></td><td></td><td></td><td></td><td class='r'><b>{_kr(T['netto_kr'])}</b></td></tr>
<tr><td></td><td>Moms {_num(A['moms_pct'], 0)} %</td><td></td><td></td><td></td><td></td><td class='r'>{_kr(T['moms_kr'])}</td></tr>
<tr class="sum"><td></td><td><b>Att betala inkl. moms</b></td><td></td><td></td><td></td><td></td><td class='r'><b>{_kr(T['brutto_kr'])}</b></td></tr>
</table>
<h2>Förutsättningar</h2>
<ul>
<li>Timpris {_kr(A['timpris'])} per montörtimme. Normtider enligt Normtid VVS: grundtid per meter efter dimension och material.</li>
<li>Tillägg: {e(', '.join(sup_labels) or 'inga')}. Avvikelseanalys: {_num(calc['avvikelse_pct'], 0)} %.</li>
<li>Kalkylmängd = nettomängd + {_num(A['spill_pct'], 0)} % spill. Stigare räknade som {_num(A['floor_height_m'], 1)} m per stigare där ritningen inte anger höjd.</li>
<li>Materialpriser är nettopriser ur materialboken på anbudsdagen. Betalning: {e(A.get('betalning') or '30 dagar netto')}.</li>
<li>Anbudet är giltigt till {M['valid']}.</li>
</ul>
{"<h2>Avtalsvillkor · " + e(M["regelverk"]) + "</h2><ul>" + rules_html + "</ul>" if rules else ""}
<h2>Förbehåll</h2>
<ul>{caveats or '<li>Inga förbehåll ur läsningen.</li>'}
<li>Rör som ingen beteckning på ritningen når ingår inte i mängden; de redovisas som onämnda i läsningen.</li>
<li>Fittings, genomföringar, isolering som egen post och rivning ingår inte om de inte står som egna rader.</li>
</ul>
<table class="sign"><tr><td>Ort och datum<br><br><br>______________________________</td><td>För {e(M['company'])}<br><br><br>______________________________</td></tr></table>
</body></html>"""


# Kroppens stil. Ingen fyllning någonstans: Story ritar om ett blocks bakgrund överst på varje följande sida, så
# allt som ska vara fyllt (huvudet, summeringskortet) ritas med sid-API:et efteråt.
TENDER_CSS = """
@font-face { font-family: Lib; src: url(LiberationSans-Regular.ttf); }
@font-face { font-family: Lib; font-weight: bold; src: url(LiberationSans-Bold.ttf); }
body { font-family: Lib; font-size: 9.5pt; color: #171f27; line-height: 1.35; }
b { font-weight: bold; }
.intro { margin: 0 0 12pt 0; line-height: 1.45; color: #2b3640; }
h2 { font-family: Lib; font-size: 8pt; font-weight: bold; margin: 16pt 0 5pt 0; letter-spacing: 1.4pt;
     text-transform: uppercase; color: #129eb0; }
.spec { width: 100%; border-collapse: collapse; }
.spec th { text-align: left; font-size: 7pt; letter-spacing: 0.9pt; text-transform: uppercase; color: #6b7885;
           border-bottom: 1pt solid #171f27; padding: 4pt 4pt 5pt 4pt; font-weight: bold; }
.spec td { padding: 5pt 4pt; border-bottom: 0.5pt solid #dfe3e7; vertical-align: top; }
.spec .r, .spec th.r { text-align: right; white-space: nowrap; }
.spec .n { width: 12pt; color: #9aa4ad; }
.spec tr.sum td { border-top: 1pt solid #171f27; border-bottom: none; padding-top: 6pt; }
.muted { color: #6b7885; font-size: 8pt; }
ul { margin: 2pt 0 0 11pt; padding: 0; line-height: 1.4; }
li { margin: 0 0 3pt 0; }
.sign { width: 100%; margin-top: 26pt; }
.sign td { width: 50%; font-size: 8.5pt; color: #4a5560; }
"""

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN = 46.0
HEAD_1 = 232.0       # sidan 1: huvudblocket och summeringskortet
HEAD_N = 52.0        # följande sidor: en rad och en linje
FOOT = 44.0


def _body_pdf(html_doc: str) -> bytes:
    """Kroppen som flödande sidor, med plats reserverad för huvud och fot."""
    import pymupdf
    d = font_dir()
    story = (pymupdf.Story(html=html_doc, user_css=_css(), archive=pymupdf.Archive(d)) if d
             else pymupdf.Story(html=html_doc, user_css=_css()))
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    rect = pymupdf.Rect(0, 0, PAGE_W, PAGE_H)
    more, n = True, 0
    while more:
        dev = writer.begin_page(rect)
        top = HEAD_1 if n == 0 else HEAD_N
        more, _ = story.place(pymupdf.Rect(MARGIN, top, PAGE_W - MARGIN, PAGE_H - FOOT))
        story.draw(dev)
        writer.end_page()
        n += 1
        if n > 60:
            break
    writer.close()
    return buf.getvalue()


def _text(page, x, y, s, size=9, bold=False, color=INK, align="left", width=None):
    """En textrad med det typsnitt anbudet är satt i, vänster- eller högerställd mot x. Med `width` kortas
    raden med en ellips tills den ryms - ett huvud som skriver över sig självt är värre än ett kortat namn."""
    import pymupdf
    file = _font_file(bold)
    if file is not None:
        font = pymupdf.Font(fontfile=file)
        fname = "LibB" if bold else "LibR"
        page.insert_font(fontname=fname, fontfile=file)
    else:
        # base-14: snittet finns i varje PDF-läsare och behöver ingen fil i bilden
        fname = "hebo" if bold else "helv"
        font = pymupdf.Font(fontname=fname)
    if width is not None:
        while len(s) > 1 and font.text_length(s, fontsize=size) > width:
            s = s[:-2].rstrip() + "…"
    w = font.text_length(s, fontsize=size)
    if align == "right":
        x = x - w
    elif align == "center":
        x = x - w / 2
    page.insert_text(pymupdf.Point(x, y), s, fontsize=size, fontname=fname, color=color)
    return w


def _decorate(pdf: bytes, calc: dict, meta: dict) -> bytes:
    """Huvud, summeringskort och fot på varje sida - ritade, inte flödade, så de ligger där de ska."""
    import pymupdf
    T = calc["totals"]; A = calc["assumptions"]; M = tender_meta(calc, meta)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    n_pages = len(doc)
    for i, page in enumerate(doc):
        sh = page.new_shape()
        if i == 0:
            # huvudblocket: mörkt, fullbredd, med en smal accent under
            sh.draw_rect(pymupdf.Rect(0, 0, PAGE_W, 150)); sh.finish(color=None, fill=NAVY)
            sh.draw_rect(pymupdf.Rect(0, 150, PAGE_W, 153)); sh.finish(color=None, fill=TEAL)
            # summeringskortet: vitt, med en mjuk kant, delvis över blockets nederkant
            card = pymupdf.Rect(MARGIN, 118, PAGE_W - MARGIN, 210)
            sh.draw_rect(card + (2, 3, 2, 3)); sh.finish(color=None, fill=(0.80, 0.84, 0.87))
            sh.draw_rect(card); sh.finish(color=LINE, fill=(1, 1, 1), width=0.6)
            # tre kolumner i kortet, skilda av hårfina linjer
            cw = card.width / 3
            for k in (1, 2):
                x = card.x0 + cw * k
                sh.draw_line(pymupdf.Point(x, card.y0 + 14), pymupdf.Point(x, card.y1 - 14)); sh.finish(color=LINE, width=0.5)
            sh.commit()
            _text(page, MARGIN, 40, M["company"].upper(), 8, True, (0.55, 0.85, 0.90), width=250)
            _text(page, MARGIN, 80, "Anbud", 34, True, (1, 1, 1))
            _text(page, MARGIN, 100, f"{M['project']}", 10.5, False, (0.92, 0.95, 0.96), width=270)
            if M["drawing"]:
                _text(page, MARGIN, 113, M["drawing"], 8, False, (0.70, 0.78, 0.82), width=270)
            # högerspalten i huvudet
            # högerspalten i huvudet: etiketten i en egen smal kolumn, värdet högerställt och kortat om det
            # inte ryms - de två får aldrig mötas
            rx = PAGE_W - MARGIN
            for j, (k, v) in enumerate((("Anbudsnummer", M["number"]), ("Datum", M["date"]),
                                        ("Giltigt till", M["valid"]), ("Beställare", M["customer"]),
                                        ("Referens", M["reference"]))):
                y = 38 + j * 16
                _text(page, rx - 212, y, k.upper(), 6.5, True, (0.55, 0.85, 0.90))
                _text(page, rx, y, v, 8.5, False, (1, 1, 1), align="right", width=146)
            # kortets tal
            for k, (lab, val, sub) in enumerate((
                    ("Anbudssumma exkl. moms", _kr(T["netto_kr"]), f"{T['rader']} poster · {_num(T['timmar'], 1)} timmar"),
                    (f"Moms {_num(A['moms_pct'], 0)} %", _kr(T["moms_kr"]), "tillkommer"),
                    ("Att betala inkl. moms", _kr(T["brutto_kr"]), M["regelverk"] or "utan standardavtal"))):
                x = card.x0 + cw * k + 14
                _text(page, x, card.y0 + 28, lab.upper(), 6.5, True, MUTED)
                _text(page, x, card.y0 + 54, val, 15 if k != 0 else 17, True, INK if k != 2 else TEAL)
                _text(page, x, card.y0 + 72, sub, 7.5, False, MUTED)
        else:
            sh.draw_line(pymupdf.Point(MARGIN, 34), pymupdf.Point(PAGE_W - MARGIN, 34)); sh.finish(color=LINE, width=0.6)
            sh.commit()
            _text(page, MARGIN, 27, "ANBUD", 7.5, True, TEAL)
            _text(page, MARGIN + 44, 27, f"{M['project']} · {M['number']}", 7.5, False, MUTED)
        # foten: linje, avsändare, sidnummer
        fs = page.new_shape()
        fs.draw_line(pymupdf.Point(MARGIN, PAGE_H - 30), pymupdf.Point(PAGE_W - MARGIN, PAGE_H - 30)); fs.finish(color=LINE, width=0.6)
        fs.commit()
        _text(page, MARGIN, PAGE_H - 18, f"{M['company']} · Anbud {M['number']} · {M['date']}", 7, False, MUTED)
        _text(page, PAGE_W - MARGIN, PAGE_H - 18, f"Sida {i + 1} av {n_pages}", 7, False, MUTED, align="right")
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


def tender_pdf(html_doc: str, calc: dict | None = None, meta: dict | None = None) -> bytes:
    """Anbudet som PDF: kroppen flödad av Story, huvud, summering och fot ritade ovanpå."""
    body = _body_pdf(html_doc)
    if calc is None:
        return body
    return _decorate(body, calc, meta or {})


def tender_pages(pdf: bytes, dpi: int = 110) -> list[bytes]:
    """Sidorna som PNG, för förhandsgranskningen i appen - samma dokument som skickas, inte en efterlikning."""
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return [pg.get_pixmap(dpi=dpi).tobytes("png") for pg in doc]


def _tender(db: Session, user: User, job_id: str) -> tuple[str, dict]:
    j = _job(db, user, job_id)
    c = db.query(Calculation).filter(Calculation.job_id == j.id).order_by(Calculation.created_at.desc()).first()
    if c is None:
        raise HTTPException(409, "Spara kalkylen först - anbudet skrivs ur den sparade kalkylen.")
    rows, legend = _inputs(db, j)
    calc = build(rows, legend, c.assumptions or {}, c.overrides or {})
    meta = {"project": j.drawing.project.name, "drawing": j.drawing.filename, "job": j.id[:8].upper(),
            "company": (user.name or "") or None}
    return tender_html(calc, meta), meta, calc


def _tender_pdf(db: Session, user: User, job_id: str) -> tuple[bytes, dict]:
    doc, meta, calc = _tender(db, user, job_id)
    return tender_pdf(doc, calc, meta), meta


@router.get("/{job_id}/calc/anbud.html")
def anbud_html(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Anbudet som HTML, för den som vill läsa det som text: samma kropp, huvudet skrivet i stället för ritat."""
    doc, meta, calc = _tender(db, user, job_id)
    M = tender_meta(calc, meta); T = calc["totals"]; e = html.escape
    head = (f"<div class='hd'><div class='co'>{e(M['company'])}</div><div class='ttl'>ANBUD</div>"
            f"<div class='pr'>{e(M['project'])} · {e(M['drawing'])}</div>"
            f"<div class='mt'>Anbudsnummer {e(M['number'])} · {M['date']} · giltigt till {M['valid']} · "
            f"beställare {e(M['customer'])} · referens {e(M['reference'])}</div></div>"
            f"<div class='sum'><div><span>Anbudssumma exkl. moms</span><b>{_kr(T['netto_kr'])}</b></div>"
            f"<div><span>Moms</span><b>{_kr(T['moms_kr'])}</b></div><div><span>Att betala inkl. moms</span><b>{_kr(T['brutto_kr'])}</b></div></div>")
    # i webbläsaren finns ingen arkivfil att peka på: snittet namnges och läsaren väljer det den har
    css = (TENDER_CSS.replace("@font-face { font-family: Lib; src: url(LiberationSans-Regular.ttf); }", "")
           .replace("@font-face { font-family: Lib; font-weight: bold; src: url(LiberationSans-Bold.ttf); }", "")
           .replace("font-family: Lib", "font-family: 'Liberation Sans', Arial, Helvetica, sans-serif"))
    css += ("body{max-width:820px;margin:24px auto;padding:0 20px;font-size:13px}"
            ".hd{background:#0f2a3a;color:#fff;padding:26px 28px;border-radius:10px;border-bottom:4px solid #129eb0}"
            ".hd .co{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#8dd9e0}"
            ".hd .ttl{font-size:38px;font-weight:bold;margin:6px 0 2px}.hd .pr{font-size:14px}.hd .mt{font-size:11px;color:#b6c6cd;margin-top:8px}"
            ".sum{display:flex;gap:12px;margin:14px 0 22px}.sum>div{flex:1;border:1px solid #dfe3e7;border-radius:10px;padding:12px 14px}"
            ".sum span{display:block;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#6b7885}.sum b{font-size:20px}"
            "h2{font-size:12px}")
    return Response(f"<style>{css}</style>{head}{doc}", media_type="text/html; charset=utf-8")


@router.get("/{job_id}/calc/anbud")
def anbud_info(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Hur många sidor anbudet har, så att förhandsgranskningen kan hämta dem en och en."""
    pdf, meta = _tender_pdf(db, user, job_id)
    import pymupdf
    n = len(pymupdf.open(stream=pdf, filetype="pdf"))
    return {"pages": n, "regelverk": sorted(REGELVERK), "project": meta["project"]}


@router.get("/{job_id}/calc/anbud/sida-{n}.png")
def anbud_page(job_id: str, n: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Sidan n av anbudet som bild: det dokument som skickas, inte en efterlikning av det."""
    pdf, _ = _tender_pdf(db, user, job_id)
    pages = tender_pages(pdf)
    if n < 1 or n > len(pages):
        raise HTTPException(404, "Ingen sådan sida i anbudet")
    return Response(pages[n - 1], media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/calc/anbud.pdf")
def anbud_pdf(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .main import _attachment
    pdf, meta = _tender_pdf(db, user, job_id)
    name = f"Anbud {meta['project']} {dt.date.today().isoformat()}.pdf"
    return Response(pdf, media_type="application/pdf", headers=_attachment(name))
