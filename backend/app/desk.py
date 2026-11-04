"""Agenten som egen plats: ett samtal, filer du släpper i det, och verktyg som bara läser.

Skild från analysens agent med flit. Den agenten sitter i ett läst blad och svarar om just den läsningen; den
här börjar tomt. Du drar in en handling i samtalet och frågar - ingen projektkatalog, ingen ordning att följa.

Två saker gör den ändå till samma sorts svar som resten av systemet:

* **Filerna är riktiga ritningar.** Det du släpper i chatten blir en ritning på ditt eget skrivbord, och en
  läsning av den är ett vanligt jobb - samma motor, samma credits, samma artefakter. Därför går svaret att
  öppna i Analys, rätta, mängda och räkna vidare på. Skrivbordet är ditt; det syns inte bland projekten förrän
  du själv flyttar dit en fil.
* **Inget tal utan belägg.** Verktygen här läser filer och färdiga läsningar. Ingen av dem räknar ut en meter
  själv, och ingen av dem skriver något. Frågar någon om en siffra som inte står i handlingen blir svaret att
  den inte står där.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import operator
import os
from typing import Any, Callable

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import current_user
from .db import AnalysisJob, Drawing, Project, User, get_db
from .storage import storage

router = APIRouter(prefix="/api/desk", tags=["agent"])

DESK_MODE = "desk"                  # projektets läge: agentens eget skrivbord, inte en handling
DESK_NAME = "Agentens skrivbord"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


# ----------------------------------------------------------------------------- skrivbordet

def desk_project(db: Session, user: User, create: bool = True) -> Project | None:
    """Användarens eget skrivbord. Ett per konto, skapat första gången något släpps i chatten."""
    p = (db.query(Project).filter(Project.owner_id == user.id, Project.analysis_mode == DESK_MODE)
         .order_by(Project.created_at).first())
    if p is None and create:
        p = Project(owner_id=user.id, name=DESK_NAME, description="Filer du gett agenten i chatten.",
                    analysis_mode=DESK_MODE)
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


def _latest_job(d: Drawing) -> AnalysisJob | None:
    return max(d.jobs, key=lambda j: j.created_at) if d.jobs else None


def _file_out(d: Drawing) -> dict:
    j = _latest_job(d)
    return {"id": d.id, "filnamn": d.filename, "sidor": d.n_pages, "storlek": d.size_bytes,
            "uppladdad": d.created_at.isoformat() if d.created_at else None,
            "jobb": ({"id": j.id, "status": j.status, "steg": j.stage, "andel": j.progress} if j else None)}


class Desk:
    """Vad verktygen får röra: den här användarens filer, och de läsningar som redan gjorts av dem.

    Verktygen får ett sådant här objekt i stället för en databas, så att ingen av dem kan nå en fil som inte
    är användarens egen eller skriva något alls.
    """

    def __init__(self, db: Session, user: User, file_ids: list[str] | None = None):
        self.db = db
        self.user = user
        self.file_ids = list(file_ids or [])
        self.opened: list[str] = []          # läsningar den här turen startade, så gränssnittet kan följa dem

    def files(self) -> list[Drawing]:
        p = desk_project(self.db, self.user, create=False)
        if p is None:
            return []
        return sorted(p.drawings, key=lambda d: d.created_at)

    def file(self, file_id: str) -> Drawing:
        for d in self.files():
            if d.id == file_id or d.filename == file_id:
                return d
        raise LookupError(f"ingen fil {file_id} i samtalet")

    def result_dir(self, j: AnalysisJob) -> str:
        return storage.path(f"results/{j.drawing_id}/{j.id}")


# ----------------------------------------------------------------------------- verktygen

TOOLS: dict[str, dict] = {}


def tool(name: str, description: str, parameters: dict):
    def deco(fn: Callable):
        TOOLS[name] = {"name": name, "description": description, "parameters": parameters, "fn": fn}
        return fn
    return deco


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


_FIL = {"fil": {"type": "string", "description": "filens id eller filnamn, som det står i lista_filer"}}


@tool("lista_filer", "Filerna i det här samtalet, med om de är lästa eller inte.", _obj({}))
def _lista_filer(desk: Desk) -> dict:
    return {"filer": [_file_out(d) for d in desk.files()]}


@tool("titta_i_filen", "Vad filen är: sidor, sidstorlek och den text som står i namnrutan. Ingen mätning, "
                       "inga credits.", _obj(_FIL, ["fil"]))
def _titta(desk: Desk, fil: str) -> dict:
    import pymupdf
    from vvs_engine.pdf.glyphtext import repaired_page_text, repairs_for_page
    d = desk.file(fil)
    doc = pymupdf.open(storage.path(d.storage_key))
    pages = []
    for i, pg in enumerate(doc):
        # CAD-plottar bäddar ofta in typsnitt utan teckentabell, och då kommer namnrutan ut som
        # ersättningstecken. repaired_page_text fyller i dem ur typsnittet självt.
        fixes = repairs_for_page(pg, doc)
        words = repaired_page_text(pg, doc, fixes=fixes) or ""
        # namnrutan står nere till höger på ett byggblad; det är den text som säger vad bladet är
        r = pg.rect
        corner = repaired_page_text(pg, doc, clip=pymupdf.Rect(r.x1 * 0.62, r.y1 * 0.66, r.x1, r.y1),
                                    fixes=fixes) or ""
        pages.append({"sida": i, "bredd_pt": round(r.width, 1), "hojd_pt": round(r.height, 1),
                      "tecken": len(words.strip()),
                      "namnruta": [ln.strip() for ln in corner.splitlines() if ln.strip()][:18]})
        if i >= 9:
            break
    doc.close()
    return {"fil": d.filename, "sidor": d.n_pages, "sidor_lista": pages}


@tool("las_ritning", "Starta en läsning av filen: motorn mäter rören och skriver mängderna. Använd det här "
                     "direkt när någon frågar om mängder ur en fil som inte är läst. Motorn hittar skalan "
                     "själv ur bladets skalstock - fråga aldrig användaren om skalan innan du läst. Kostar "
                     "credits som vilken läsning som helst. Svaret säger att den startat; fråga sedan om "
                     "mängderna.",
      _obj({**_FIL, "skala": {"type": "integer",
                              "description": "nämnaren i 1:N. Skicka bara om en tidigare läsning sagt att den "
                                             "inte kunde hitta någon skala; annars åsidosätter du det motorn läste"}},
           ["fil"]))
def _las(desk: Desk, fil: str, skala: int | None = None) -> dict:
    from . import credits as credits_api
    from . import jobs as job_queue
    d = desk.file(fil)
    j = _latest_job(d)
    if j is not None and j.status in ("QUEUED", "RUNNING"):
        return {"lage": "pågår", "jobb": j.id, "steg": j.stage, "andel": j.progress}
    if j is not None and j.status == "COMPLETED" and not skala:
        return {"lage": "redan läst", "jobb": j.id, "svar": "filen är redan läst; fråga om mängderna"}
    given = None
    if skala:
        if not (1 <= int(skala) <= 20000):
            return {"fel": "skalan skrivs som nämnaren i 1:N, mellan 1 och 20000"}
        from vvs_engine.measure.scale import ratio_to_meters_per_pt
        given = {"ratio": int(skala), "page": 0, "meters_per_pdf_point": ratio_to_meters_per_pt(int(skala))}
    nj = AnalysisJob(drawing_id=d.id, status="QUEUED", stage="QUEUED", progress=0.0,
                     summary={"given_scale": given} if given else None)
    desk.db.add(nj)
    desk.db.flush()
    charged = credits_api.charge_for_reading(desk.db, desk.user, d, nj)
    if charged:
        nj.summary = {**(nj.summary or {}), "credits": charged}
    desk.db.commit()
    job_queue.submit(nj.id)
    desk.opened.append(nj.id)
    return {"lage": "startad", "jobb": nj.id, "fil": d.filename,
            "svar": "läsningen är startad; den tar en stund och syns i samtalet när den är klar"}


def _quantities(desk: Desk, d: Drawing) -> tuple[AnalysisJob, dict]:
    j = _latest_job(d)
    if j is None:
        raise LookupError(f"{d.filename} är inte läst ännu - be om las_ritning först")
    if j.status != "COMPLETED":
        raise LookupError(f"läsningen av {d.filename} är {j.status.lower()}")
    p = os.path.join(desk.result_dir(j), "quantities.json")
    if not os.path.exists(p):
        raise LookupError(f"läsningen av {d.filename} skrev inga mängder")
    return j, json.load(open(p, encoding="utf-8"))


@tool("mangder", "Mängderna ur en läst fil: beteckning, dimension och meter, som de står i tabellen.",
      _obj(_FIL, ["fil"]))
def _mangder(desk: Desk, fil: str) -> dict:
    d = desk.file(fil)
    j, q = _quantities(desk, d)
    rows = [{"beteckning": r.get("designation"), "dn": r.get("dn"),
             "horisontellt_m": round(r.get("confirmed_horizontal_m") or 0.0, 2),
             "totalt_m": round(r.get("confirmed_total_m") or 0.0, 2)} for r in (q.get("rows") or [])]
    tot = round(sum(r["horisontellt_m"] for r in rows), 1)
    sc = q.get("scale") or {}
    return {"fil": d.filename, "jobb": j.id, "skala": {"tillstand": sc.get("state"), "skal": sc.get("reason")},
            "rader": rows, "summa_horisontellt_m": tot}


@tool("fragorna", "Vad läsningen inte kunde avgöra på bladet, räknat per skäl - det som en människa behöver "
                  "titta på.", _obj(_FIL, ["fil"]))
def _fragorna(desk: Desk, fil: str) -> dict:
    from collections import Counter
    d = desk.file(fil)
    j = _latest_job(d)
    if j is None or j.status != "COMPLETED":
        return {"fel": f"{d.filename} är inte läst"}
    out: dict[str, Any] = {"fil": d.filename}
    p = os.path.join(desk.result_dir(j), "pipe-code-anchors.json")
    if os.path.exists(p):
        anc = json.load(open(p, encoding="utf-8")).get("anchors") or []
        c = Counter(a.get("reason") for a in anc if a.get("state") != "VERIFIED_PIPE_ATTACHMENT")
        out["etiketter_utan_svar"] = dict(c.most_common(8))
    p = os.path.join(desk.result_dir(j), "pipe-extent-frontiers.json")
    if os.path.exists(p):
        fr = json.load(open(p, encoding="utf-8")).get("frontiers") or []
        out["fronter"] = dict(Counter(f.get("reason") for f in fr).most_common(10))
    return out


@tool("jamfor", "Två lästa filer mot varandra: vilka beteckningar som skiljer och med hur mycket.",
      _obj({"fil_a": {"type": "string"}, "fil_b": {"type": "string"}}, ["fil_a", "fil_b"]))
def _jamfor(desk: Desk, fil_a: str, fil_b: str) -> dict:
    a, b = desk.file(fil_a), desk.file(fil_b)
    _, qa = _quantities(desk, a)
    _, qb = _quantities(desk, b)
    ma = {r.get("designation"): round(r.get("confirmed_horizontal_m") or 0.0, 2) for r in (qa.get("rows") or [])}
    mb = {r.get("designation"): round(r.get("confirmed_horizontal_m") or 0.0, 2) for r in (qb.get("rows") or [])}
    rows = []
    for k in sorted(set(ma) | set(mb)):
        x, y = ma.get(k, 0.0), mb.get(k, 0.0)
        if abs(x - y) > 0.05:
            rows.append({"beteckning": k, "a_m": x, "b_m": y, "skillnad_m": round(y - x, 2)})
    return {"a": a.filename, "b": b.filename, "skillnader": rows,
            "summa_a_m": round(sum(ma.values()), 1), "summa_b_m": round(sum(mb.values()), 1)}


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Mod: operator.mod}


def _eval(node) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("uttrycket innehåller något annat än tal och de fyra räknesätten")


@tool("rakna", "Räkna ut ett uttryck med tal du redan fått ur en fil. Bara de fyra räknesätten; inga tal "
               "hämtas härifrån.", _obj({"uttryck": {"type": "string"}}, ["uttryck"]))
def _rakna(desk: Desk, uttryck: str) -> dict:
    try:
        v = _eval(ast.parse(uttryck, mode="eval"))
    except Exception as e:                                       # noqa: BLE001
        return {"fel": f"kunde inte räkna: {e}"}
    return {"uttryck": uttryck, "svar": round(v, 4)}


@tool("material_pris", "Slå upp artiklar i materialboken på ord ur benämningen eller artikelnumret.",
      _obj({"sok": {"type": "string"}}, ["sok"]))
def _material(desk: Desk, sok: str) -> dict:
    from .main import _material as book
    rows = book()["rows"]
    words = [w for w in (sok or "").lower().split() if w]
    if not words:
        return {"fel": "skriv något att söka på"}
    hits = [r for r in rows if all(w in f'{r["n"]} {r["a"]}'.lower() for w in words)][:20]
    return {"traffar": [{"benamning": r.get("n"), "artikel": r.get("a"), "enhet": r.get("e"),
                         "pris": r.get("p"), "grupp": r.get("gr")} for r in hits]}


def schemas() -> list[dict]:
    return [{"type": "function", "name": t["name"], "description": t["description"],
             "parameters": t["parameters"]} for t in TOOLS.values()]


def run(name: str, desk: Desk, args: dict) -> dict:
    t = TOOLS.get(name)
    if t is None:
        return {"fel": f"okänt verktyg {name}", "tillgangliga": sorted(TOOLS)}
    try:
        return t["fn"](desk, **{k: v for k, v in (args or {}).items() if k != "self"})
    except LookupError as e:
        return {"fel": str(e)}
    except TypeError as e:
        return {"fel": f"fel argument till {name}: {e}"}
    except Exception as e:                                       # noqa: BLE001
        return {"fel": f"{name} kunde inte köras: {type(e).__name__}: {e}"}


# ----------------------------------------------------------------------------- vägarna in

class Ask(BaseModel):
    fraga: str
    filer: list[str] | None = None
    historik: list[dict] | None = None


@router.get("/files")
def list_files(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"filer": [_file_out(d) for d in Desk(db, user).files()]}


@router.post("/files")
async def upload(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """En fil i samtalet. Samma kontroller som en ritning i ett projekt - det är vad den blir."""
    name = os.path.basename(file.filename or "")
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Agenten läser PDF. Spara om filen som PDF och släpp den igen.")
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
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Filen är inte en giltig PDF")
    import pymupdf
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
        locked = bool(doc.needs_pass or doc.is_encrypted)
        n_pages = len(doc)
        doc.close()
    except Exception:
        raise HTTPException(400, "PDF-filen kunde inte läsas")
    if locked:
        raise HTTPException(400, "PDF-filen är lösenordsskyddad. Spara om den utan lösenord och släpp den igen.")
    if not n_pages:
        raise HTTPException(400, "PDF-filen innehåller inga sidor")
    p = desk_project(db, user)
    d = Drawing(project_id=p.id, filename=name, storage_key="", sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data), n_pages=n_pages)
    db.add(d)
    db.flush()
    key = f"drawings/{d.id}/{d.filename}"
    storage.put(key, io.BytesIO(data))
    d.storage_key = key
    db.commit()
    return _file_out(d)


@router.get("/tools")
def tools_contract(user: User = Depends(current_user)):
    """Vad agenten kan göra, så att samtalet kan visa det i stället för att lova något annat."""
    return {"verktyg": [{"namn": t["name"], "beskrivning": t["description"]} for t in TOOLS.values()]}


@router.post("/ask")
def ask(body: Ask, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """En fråga till agenten. Modellen väljer verktyg, verktygen svarar ur filerna, ingenting skrivs."""
    from .agent import run_turn
    q = (body.fraga or "").strip()
    if not q:
        raise HTTPException(422, "Skriv en fråga.")
    from . import api_budget
    api_budget.require()
    desk = Desk(db, user, body.filer)
    try:
        from tools.astra_transport import agent_transport
    except Exception as e:                                       # noqa: BLE001
        raise HTTPException(503, f"agenttransporten kunde inte laddas: {type(e).__name__}")
    files = desk.files()
    if files:
        named = ", ".join(f"{d.filename} ({d.id})" for d in files[:12])
        q = f"{q}\n\n[Filer i samtalet] {named}"
    try:
        out = run_turn(desk, agent_transport(), q, history=body.historik or [], tools=_Registry)
    except Exception as e:                                       # noqa: BLE001
        raise HTTPException(502, f"Agenten nådde inte modellen: {type(e).__name__}: {str(e)[:200]}")
    return {**out, "startade_lasningar": desk.opened,
            "filer": [_file_out(d) for d in desk.files()]}


class _Registry:
    """Verktygsregistret i den form turordningen väntar sig (samma kontrakt som motorns egna verktyg)."""

    schemas = staticmethod(schemas)
    run = staticmethod(run)
