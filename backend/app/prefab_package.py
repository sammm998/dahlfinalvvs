"""SmartHangers ur ett modellpaket enligt kravunderlaget: VS-, K- och A-modellen (och andra disciplinernas filer som
hinder) laddas upp tillsammans, läses i bakgrunden, valideras (V1-V11) och räknas - i den ordningen. Ett Stopp i
valideringen stoppar beräkningen tills modellen är rättad eller ett manuellt värde är angivet.

  POST /api/projects/{pid}/hanger-packages     filer + disciplin per fil (gissas ur filnamnet: 4075-V-50-..., -K-, -A-)
  POST /api/hanger-sets/{id}/package-settings  takhöjd per våning/zon, bjälklagstyp per zon, uppskattning, räkna om
  GET  /api/hanger-sets/{id}/package           läget: jobbet, filerna, kontrollrapporten, beräkningens avvikelser
  GET  /api/hanger-sets/{id}/export.{csv|dxf|bcf|rapport|artiklar}

Stora modeller (en MagiCAD-fil på några hundra MB tar en minut och några GB att läsa) läses en gång; det lästa
sparas komprimerat bredvid filerna så att en omräkning med nya höjder går på sekunder."""
from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import logging
import os
import re
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from vvs_engine.hangers import generate as HG
from vvs_engine.hangers import outputs as HO
from vvs_engine.hangers import package as PK
from vvs_engine.hangers.geometry import read_model

from . import prefab as P
from .auth import current_user
from .db import HangerSet, SessionLocal, User, get_db
from .storage import storage

log = logging.getLogger(__name__)
router = APIRouter(tags=["smarthangers"])
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hangers")
_running: set[str] = set()
_lock = threading.Lock()
DISCIPLINES = ("VS", "K", "A", "Ö")
WANT = {"VS": {"pipes", "obstacles"}, "K": {"structure"}, "A": {"architecture"}, "Ö": {"obstacles"}}


def guess_discipline(filename: str) -> str:
    """Disciplinen ur ett filnamn efter BEAst/SB11: 4075-V-50-V-30001 (V = VVS), -K- (konstruktion), -A-
    (arkitekt), -E- (el), -R- eller -L- (ventilation/luft)."""
    n = os.path.basename(filename or "").upper()
    for tok in re.findall(r"(?:^|[-_ .])([A-ZÅÄÖ]{1,3})(?=[-_ .\d])", n):
        if tok in ("V", "VS", "VVS", "S", "P"):
            return "VS"
        if tok in ("K", "KB", "KON"):
            return "K"
        if tok in ("A", "AR", "ARK"):
            return "A"
        if tok in ("E", "EL", "R", "L", "VE", "SP"):
            return "Ö"
    return "VS"


def _key(sid: str, name: str) -> str:
    return f"prefab/{sid}/{name}"


def _ifc_text(raw: bytes, name: str) -> str:
    if name.lower().endswith((".zip", ".ifczip")):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            inner = next((n for n in z.namelist() if n.lower().endswith(".ifc")), None)
            if not inner:
                raise ValueError(f"{name}: zip-filen har ingen .ifc i sig")
            raw = z.read(inner)
    return raw.decode("utf-8", "replace")


def _save_json(key: str, data: Any) -> None:
    storage.put(key, io.BytesIO(gzip.compress(json.dumps(data, ensure_ascii=False, default=float).encode("utf-8"), 5)))


def _load_json(key: str) -> Any:
    if not storage.exists(key):
        return None
    with storage.open(key) as fh:
        return json.loads(gzip.decompress(fh.read()).decode("utf-8"))


def _job(s: HangerSet, **kw) -> None:
    s.settings = {**(s.settings or {}), "job": {**((s.settings or {}).get("job") or {}), **kw,
                                                 "updated": dt.datetime.now(dt.timezone.utc).isoformat()}}


def _step(sid: str, **kw) -> None:
    with SessionLocal() as db:
        s = db.get(HangerSet, sid)
        if s:
            _job(s, **kw)
            db.commit()


def _light(m: dict[str, Any]) -> dict[str, Any]:
    """Det av en läst modell som sparas: allt utom råtexten (som aldrig sparas)."""
    return {k: v for k, v in m.items() if k not in ("text",)}


def _run(sid: str, reread: bool) -> None:
    try:
        with SessionLocal() as db:
            s = db.get(HangerSet, sid)
            files = list((s.settings or {}).get("files") or [])
        if reread or not storage.exists(_key(sid, "models.json.gz")):
            models = []
            for i, f in enumerate(files):
                _step(sid, state="läser", step=f"läser {f['name']} ({f['discipline']}, {i + 1} av {len(files)})")
                with storage.open(f["key"]) as fh:
                    text = _ifc_text(fh.read(), f["name"])
                m = read_model(text, f["discipline"], WANT.get(f["discipline"]))
                del text
                m["header"] = {**(m.get("header") or {}), "file_name": f["name"]}
                models.append(_light(m))
            _save_json(_key(sid, "models.json.gz"), models)
        else:
            models = _load_json(_key(sid, "models.json.gz"))
        _step(sid, state="validerar", step="kontrollerar modellerna (V1-V11)")
        with SessionLocal() as db:
            s = db.get(HangerSet, sid)
            st = s.settings or {}
            r = P.rules()
            merged = PK.combine(models)
            report = PK.validate(models, merged, r, {"manual_heights": st.get("manual_heights") or {},
                                                     "estimate_above": st.get("estimate_above")})
            stop = PK.blocking(report)
            files_info = [{**(m.get("header") or {}), "discipline": m.get("discipline"), "pipes": len(m.get("pipes") or []),
                           "ceilings": len(m.get("ceilings") or []), "walls": len(m.get("walls") or []),
                           "openings": len(m.get("openings") or [])} for m in models]
            s.settings = {**st, "validation": report[:400], "validation_summary": PK.summary(report), "files_read": files_info,
                          "has": merged.get("has")}
            _save_json(_key(sid, "validation.json.gz"), report)
            if stop:
                s.hangers = []
                _job(s, state="stoppad", step=f"{len(stop)} stopp i kontrollrapporten - rätta modellen eller ange värden",
                     done=True)
                db.commit()
                return
            _job(s, state="räknar", step=f"räknar {len(merged['pipes'])} rör")
            db.commit()
            res = HG.generate(merged, r, st.get("manual_heights") or {}, project=s.name, revision=s.revision,
                              zone_slab_types=st.get("zone_slab_types") or None, estimate_above=st.get("estimate_above"),
                              groups=st.get("groups"))
            P._pack(s, res["hangers"], r)
            HG.apply_references(res["hangers"], st.get("references"))
            _save_json(_key(sid, "findings.json.gz"), res["findings"])
            fsum: dict[str, int] = {}
            for f in res["findings"]:
                fsum[f"{f['rule']} {f['level']}"] = fsum.get(f"{f['rule']} {f['level']}", 0) + 1
            s.hangers = res["hangers"]
            s.pipes = {"pipes": [{k: p.get(k) for k in ("id", "name", "start", "end", "od", "dn", "material", "system",
                                                         "insulation_mm", "storey")} for p in merged["pipes"]],
                       "fittings": [], "storeys": merged.get("storeys") or [], "skipped": res["skipped"],
                       "source": "modellpaket", "ceilings": []}
            s.settings = {**s.settings, "rules_version": r.get("version"), "rules_verified": bool(r.get("verified")),
                          "ceilings": res.get("ceilings"), "findings": res["findings"][:300], "findings_summary": fsum}
            _job(s, state="klar", step=f"{len(res['hangers'])} hängare", done=True)
            s.log = (s.log or []) + [{"at": P._now(), "user": "tjänsten", "action": "genererad ur modellpaket", "hanger": None, "n": len(res["hangers"])}]
            P._touch(s)
            db.commit()
    except Exception as e:                                  # noqa: BLE001
        log.exception("SmartHangers-paketet %s föll", sid)
        _step(sid, state="fel", step=f"{type(e).__name__}: {e}"[:400], done=True)
    finally:
        with _lock:
            _running.discard(sid)


def submit(sid: str, reread: bool = True) -> None:
    with _lock:
        if sid in _running:
            raise HTTPException(409, "Paketet räknas redan - vänta tills det är klart")
        _running.add(sid)
    if os.environ.get("VVS_HANGERS_INLINE") == "1":
        _run(sid, reread)
    else:
        _pool.submit(_run, sid, reread)


@router.post("/api/projects/{project_id}/hanger-packages")
async def create_package(project_id: str, files: list[UploadFile] = File(...), disciplines: str = Form("[]"),
                         name: str = Form(""), heights: str = Form("{}"), estimate_above: str = Form(""),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = P._project(db, user, project_id)
    try:
        given = json.loads(disciplines or "[]")
    except ValueError:
        raise HTTPException(422, "Disciplinerna ska vara en lista: [\"VS\", \"K\", \"A\"]")
    s = HangerSet(project_id=p.id, name=name or p.name, revision="A", created_by=user.email, approvals={}, log=[], hangers=[],
                  source_filename=", ".join(os.path.basename(f.filename or "") for f in files)[:250])
    db.add(s)
    db.flush()
    stored = []
    for i, f in enumerate(files):
        fname = os.path.basename(f.filename or f"modell{i}.ifc")
        if not fname.lower().endswith((".ifc", ".zip", ".ifczip")):
            raise HTTPException(400, f"{fname}: modellerna ska vara .ifc (eller .zip med en .ifc)")
        disc = (given[i] if i < len(given) and given[i] else guess_discipline(fname)).upper()
        disc = {"V": "VS", "VVS": "VS", "O": "Ö", "ÖVRIGT": "Ö"}.get(disc, disc)
        if disc not in DISCIPLINES:
            raise HTTPException(422, f"{fname}: disciplinen ska vara VS, K, A eller Ö (övrig)")
        key = _key(s.id, f"files/{i}-{disc}-{re.sub(r'[^A-Za-z0-9._-]', '_', fname)}")
        storage.put(key, f.file)                                  # strömmas till disk, inte in i minnet
        stored.append({"name": fname, "discipline": disc, "key": key})
    if not any(f["discipline"] == "VS" for f in stored):
        raise HTTPException(422, "Paketet behöver en VS-modell (rören)")
    try:
        est = float(estimate_above) if estimate_above not in ("", None) else None
    except ValueError:
        raise HTTPException(422, "Uppskattningen är ett avstånd i mm")
    s.settings = {"files": stored, "manual_heights": P._heights(heights), "estimate_above": est, "source": "modellpaket"}
    _job(s, state="köad", step="väntar på att läsas", done=False)
    P._log(s, user, "modellpaket uppladdat", files=[f"{f['discipline']}: {f['name']}" for f in stored])
    P._touch(s)
    db.commit()
    submit(s.id, True)
    db.refresh(s)
    return P._out(s)


@router.post("/api/hanger-sets/{set_id}/package-settings")
def package_settings(set_id: str, body: dict[str, Any], user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Takhöjd (underkant bjälklag) per våning eller "våning|zon", bjälklagstyp per zon, och om höjden får
    uppskattas ur grannrören (estimate_above, mm ovan högsta rör). Räknar om ur det redan lästa paketet."""
    s = P._set(db, user, set_id, ("projektadmin", "granskare"))
    if not (s.settings or {}).get("files"):
        raise HTTPException(400, "Uppsättningen kommer inte ur ett modellpaket")
    if any(h.get("status") in ("producerad", "packad", "levererad", "monterad") for h in s.hangers or []):
        raise HTTPException(409, "Hängare är redan producerade - gör en ny revision i stället")
    st = dict(s.settings or {})
    if "manual_heights" in body:
        st["manual_heights"] = {str(k): float(v) for k, v in (body.get("manual_heights") or {}).items() if v not in (None, "")}
    if "zone_slab_types" in body:
        ok = set((P.rules().get("anchors") or {}).keys())
        zt = {str(k): str(v) for k, v in (body.get("zone_slab_types") or {}).items() if v}
        bad = [v for v in zt.values() if v not in ok]
        if bad:
            raise HTTPException(422, f"Okänd bjälklagstyp: {', '.join(bad)} (finns: {', '.join(sorted(ok))})")
        st["zone_slab_types"] = zt
    if "estimate_above" in body:
        v = body.get("estimate_above")
        st["estimate_above"] = float(v) if v not in (None, "", False) else None
    s.settings = st
    s.approvals = {}
    _job(s, state="köad", step="räknar om med de nya värdena", done=False)
    P._log(s, user, "paketinställningar", **{k: body[k] for k in body if k in ("manual_heights", "zone_slab_types", "estimate_above")})
    P._touch(s)
    db.commit()
    submit(s.id, False)
    db.refresh(s)
    return P._out(s)


@router.post("/api/hanger-sets/{set_id}/groups")
def regroup(set_id: str, body: dict[str, Any], user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Trapetsgrupperingen för hand: {"split": [hängar-ID]} hänger hängarnas rör var för sig (pendlar),
    {"merge": [hängar-ID, ...]} lägger rören på de hängarna på samma takjärn, {"reset": true} tar bort
    ändringarna. Sparas per rör (GlobalId) och gäller vid varje omräkning; räknar om i bakgrunden."""
    s = P._set(db, user, set_id, ("projektadmin", "granskare"))
    if not (s.settings or {}).get("files"):
        raise HTTPException(400, "Uppsättningen kommer inte ur ett modellpaket")
    if any(h.get("status") in ("producerad", "packad", "levererad", "monterad") for h in s.hangers or []):
        raise HTTPException(409, "Hängare är redan producerade - gör en ny revision i stället")
    by_id = {h["id"]: h for h in s.hangers or []}
    pipes_of = lambda ids: [str(p["id"]) for i in ids for p in (by_id[i]["pipes"] if i in by_id else [])]
    g = dict((s.settings or {}).get("groups") or {})
    if body.get("reset"):
        g = {}
    if body.get("split"):
        missing = [i for i in body["split"] if i not in by_id]
        if missing:
            raise HTTPException(404, f"Hängaren finns inte: {', '.join(missing)}")
        ids = set(pipes_of(body["split"]))
        g["split"] = sorted(set(g.get("split") or []) | ids)
        g["merge"] = [[x for x in m if x not in ids] for m in g.get("merge") or []]
    if body.get("merge"):
        ids = pipes_of(body["merge"])
        if len(set(ids)) < 2:
            raise HTTPException(422, "Välj hängare med minst två olika rör att lägga på samma takjärn")
        g["split"] = [x for x in g.get("split") or [] if x not in ids]
        g["merge"] = [m for m in g.get("merge") or [] if not set(m) & set(ids)] + [sorted(set(ids))]
    g["merge"] = [m for m in g.get("merge") or [] if len(m) > 1]
    s.settings = {**(s.settings or {}), "groups": g}
    s.approvals = {}
    _job(s, state="köad", step="räknar om med den nya grupperingen", done=False)
    P._log(s, user, "trapetsgruppering", **{k: body[k] for k in ("split", "merge", "reset") if k in body})
    P._touch(s)
    db.commit()
    submit(s.id, False)
    db.refresh(s)
    return P._out(s)


@router.get("/api/hanger-sets/{set_id}/package")
def package_status(set_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = P._set(db, user, set_id)
    st = s.settings or {}
    job = dict(st.get("job") or {})
    if job and not job.get("done") and s.id not in _running:
        job.update(state="avbruten", step="tjänsten startades om under läsningen - kör om", done=True)
    storeys = sorted({h.get("storey") for h in s.hangers or [] if h.get("storey")} |
                     {p.get("storey") for p in (s.pipes or {}).get("pipes") or [] if p.get("storey")})
    zones = sorted({f"{h.get('storey')}|{h.get('zone')}" for h in s.hangers or [] if h.get("zone") and h.get("kind") != "stigare"})
    return {"id": s.id, "job": job, "files": [{"name": f["name"], "discipline": f["discipline"]} for f in st.get("files") or []],
            "files_read": st.get("files_read") or [], "has": st.get("has") or {},
            "validation": st.get("validation") or [], "validation_summary": st.get("validation_summary") or {},
            "findings": st.get("findings") or [], "findings_summary": st.get("findings_summary") or {},
            "manual_heights": st.get("manual_heights") or {}, "zone_slab_types": st.get("zone_slab_types") or {},
            "estimate_above": st.get("estimate_above"), "storeys": storeys, "zones": zones, "groups": st.get("groups") or {},
            "slab_types": sorted((P.rules().get("anchors") or {}).keys()), "n": len(s.hangers or [])}


@router.post("/api/hanger-sets/{set_id}/package-rerun")
def package_rerun(set_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Läs filerna igen (efter ett avbrott eller en ny läsare)."""
    s = P._set(db, user, set_id, ("projektadmin",))
    if not (s.settings or {}).get("files"):
        raise HTTPException(400, "Uppsättningen kommer inte ur ett modellpaket")
    _job(s, state="köad", step="läser om filerna", done=False)
    db.commit()
    submit(s.id, True)
    return package_status(set_id, user, db)


# ---------------------------------------------------------------- artiklar och priser

# Delarna mot Dahls prisfil (offertdata "prislista": Artnr, Benämning, Kalkylgr, Enh, Bruttopris). Benämningarna där
# är korta och regelbundna ("GÄNGSTÅNG M10X1000 FZB NOVIPRO", "RÖRKLAMMER KSB2 GUMMI 20-23MM", "STRUTSKENA
# 41X41X1,5 3M FFZV"), så varje del har ett mönster med storleken i. Förzinkat (FZB/FZV) före syrafast (A4), Novipro
# före andra, sedan det billigaste. Gängstång och skena säljs per längd: priset räknas om till kronor per meter.
_PRICE_PARTS: dict[str, tuple[str, str]] = {
    "gängstång": (r"^GÄNGSTÅNG {M}X(?P<len>\d+)\b", r"A4|SYRA|INV"),
    "skarvmutter": (r"SKARVMUTTER (?:FZB|FZV) {M}X", r"A4"),
    "mutter": (r"^MUTTER M6M {M}\b", r"A4|FÖRP"),
    "bricka": (r"^BRICKA BRB {M}(?:X\d+)?\b", r"A4|FÖRP"),
    "kanalmutter": (r"GLIDMUTTER {M}\b|FJÄDERMUTTER STRUT.*\b{M}\b", r"A4"),
    "takjärn": (r"^STRUTSKENA {P}X[\d,]+ (?P<m>\d+)M\b", r"A4"),
    "rörklammer": (r"^RÖRKLAMMER (?:KSB2|BIFIX|2S)(?: GUMMI)? (?P<lo>\d+)-(?P<hi>\d+)", r"A4"),
    "infästning": (r"^BETONGSKRUV .*-IT .*\b{M}\b|^BETONGSKRUV .*\bM8/M10\b", r"A4"),
    "balkklammer": (r"BALKKLAMMER {M}\b", r"A4"),
}


def _price_rows() -> list[dict[str, Any]]:
    from . import offers as O
    return [r for r in O.data("prislista") if r.get("namn") and r.get("pris") is not None]


def _from_price_list(part: str, text: str) -> dict[str, Any] | None:
    from . import offers as O
    low = text.lower()
    if part == "infästning" and "balkklammer" in low:
        part = "balkklammer"
    if part == "infästning" and not re.search(r"betong|hd/f", low):
        return None                                        # KL-trä och trapetsplåt: inget säkert i prisfilen
    spec = _PRICE_PARTS.get(part)
    if not spec:
        return None
    size = (re.search(r"\bM\d{1,2}\b", text) or [""])[0].upper()
    prof = (re.search(r"(\d{2})x(\d{2})", low) or None)
    pat = spec[0].replace("{M}", re.escape(size) if size else r"M\d+").replace("{P}", f"{prof.group(1)}X{prof.group(2)}" if prof else "41X41")
    want, avoid = re.compile(pat), re.compile(spec[1])
    od = None
    if part == "rörklammer":
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", text)
        od = float(m.group(1).replace(",", ".")) if m else None
        if od is None:
            return None
    disc = O.base_discounts()
    best = None
    for r in _price_rows():
        n = str(r["namn"]).upper()
        m = want.search(n)
        if not m or avoid.search(n):
            continue
        if od is not None and not (float(m.group("lo")) <= od <= float(m.group("hi"))):
            continue
        unit = (r.get("enhet") or "st").strip().lower()
        if unit not in ("stk", "st"):
            continue                                       # förpackning eller par: antalet per enhet är okänt
        price = float(r["pris"])
        per_m = None
        if "len" in m.groupdict() and m.group("len"):
            per_m = float(m.group("len")) / 1000
        elif "m" in m.groupdict() and m.group("m"):
            per_m = float(m.group("m"))
        score = ("NOVIPRO" not in n, "FZ" not in n, price / (per_m or 1))
        if best is None or score < best[0]:
            best = (score, r, per_m)
    if not best:
        return None
    _, r, per_m = best
    pct = disc.get(str(r.get("grupp") or ""))
    brutto = float(r["pris"]) / (per_m or 1)
    netto = round(brutto * (1 - float(pct) / 100), 2) if pct is not None else None
    return {"a": r["rsk"], "n": str(r["namn"]).strip() + (f" (pris per m ur {per_m:g} m)" if per_m else ""),
            "e": "m" if per_m else "st", "brutto": round(brutto, 2), "netto": netto,
            "source": "förslag ur Dahls prisfil - kontrollera" + (f", grundrabatt {pct:g} %" if pct is not None else "")}


def hanger_article(item: dict[str, Any]) -> dict[str, Any] | None:
    """En del på hängarens materiallista till en artikel med pris: först reglernas artikelnummer (verifierade mot
    tillverkaren), sedan Dahls uppladdade prisfil där benämningen bär delen och storleken (M10, klammerns mått,
    skenans profil). Hittas ingen sådan står delen kvar utan artikel - ingenting gissas. Saknade artiklar läggs in i
    regelverkets "articles" ({"rörklammer M10": {"art": "...", "supplier": "Novipro"}}) och gäller då alla projekt."""
    from . import calc as C
    from . import offers as O
    text, part = item["text"], item["part"]
    low = text.lower()
    for k, a in (P.rules().get("articles") or {}).items():
        toks = [t for t in k.lower().split() if not t.isdigit()]
        if toks and all(t in low for t in toks):
            row = next((r for r in _price_rows() if str(r.get("rsk")) == str(a.get("art"))), None)
            if row:
                pct = O.base_discounts().get(str(row.get("grupp") or ""))
                br = float(row["pris"])
                out = {"a": row["rsk"], "n": str(row["namn"]).strip(), "e": "st", "brutto": br,
                       "netto": round(br * (1 - float(pct) / 100), 2) if pct is not None else None}
                return {**out, "source": f"regelverket ({a.get('supplier') or ''})".strip()}
            hit = C._article_by_number(str(a.get("art")))
            if hit and hit.get("brutto") is not None:
                return {**hit, "source": f"regelverket ({a.get('supplier') or ''})".strip()}
            # regelverkets artikel finns inte i Dahls prisfil: Dahls egen artikel med pris före en utan
            return _from_price_list(part, text) or {"a": a.get("art"), "n": k, "e": "st", "brutto": None, "netto": None,
                                                    "source": f"regelverket ({a.get('supplier') or ''}) - pris saknas i prisfilen"}
    return _from_price_list(part, text)


def _articles_xlsx(s: HangerSet) -> bytes:
    import openpyxl
    from openpyxl.styles import Font
    rows = HO.article_list(s.hangers or [], hanger_article)
    tot = HO.article_totals(rows)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Artiklar per zon"
    ws.append([f"Artikellista {s.name} - revision {s.revision}", "", "", f"Summa {tot['total']:,.2f} kr".replace(",", " "),
               f"{tot['rows_without_price']} rader utan artikel eller pris"])
    ws.append(["Våning", "Zon", "Del", "Benämning", "Längd mm", "Antal", "Mängd", "Enhet", "Artikelnr", "Artikel",
               "Á-pris", "Pris", "Summa", "Källa"])
    for c in ws[2]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r["storey"], r["zone"], r["part"], r["text"], r["length_mm"], r["qty"], r["amount"], r["unit"],
                   r.get("article"), r.get("article_name"), r.get("price"), r.get("price_kind"), r.get("sum"), r.get("article_source")])
    w2 = wb.create_sheet("Summa per zon")
    w2.append(["Zon", "Summa kr"])
    for k, v in tot["by_zone"].items():
        w2.append([k, v])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


@router.get("/api/hanger-sets/{set_id}/articles")
def articles(set_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = P._set(db, user, set_id)
    rows = HO.article_list(s.hangers or [], hanger_article)
    return {"rows": rows[:3000], "totals": HO.article_totals(rows)}


def export_more(s: HangerSet, fmt: str) -> Response | None:
    """De format kravunderlaget lägger till; None för ett okänt format."""
    fname = f"smarthangers-{s.name or 'projekt'}-rev{s.revision}".replace(" ", "_")
    hs = s.hangers or []
    val = _load_json(_key(s.id, "validation.json.gz")) or (s.settings or {}).get("validation") or []
    fnd = _load_json(_key(s.id, "findings.json.gz")) or (s.settings or {}).get("findings") or []
    att = lambda ext: {"Content-Disposition": f'attachment; filename="{fname}{ext}"'}
    if fmt == "csv":
        return Response(HO.point_csv(hs, s.name).encode("utf-8"), media_type="text/csv; charset=utf-8", headers=att("-punktlista.csv"))
    if fmt == "dxf":
        return Response(HO.dxf(hs, (s.pipes or {}).get("pipes") or []), media_type="application/dxf", headers=att(".dxf"))
    if fmt == "bcf":
        return Response(HO.bcf_zip(s.name, s.revision, val, fnd, hs), media_type="application/octet-stream", headers=att(".bcfzip"))
    if fmt == "rapport":
        files = (s.settings or {}).get("files_read") or []
        return Response(HO.report_pdf(s.name, s.revision, val, fnd, hs, HG.summary(hs, P.rules()), files),
                        media_type="application/pdf", headers=att("-kontrollrapport.pdf"))
    if fmt == "artiklar":
        return Response(_articles_xlsx(s), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers=att("-artiklar.xlsx"))
    return None
