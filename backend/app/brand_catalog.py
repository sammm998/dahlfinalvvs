"""Det egna varumärkets sortiment (Alterna): produkterna som likvärdiga alternativ föreslås ur.

Alternas produkter står inte i beskrivningarna, varken med namn eller nummer. Varje produkt bär därför det
matchningen går på: sort, mått (bredd, höjd, djup i mm), material, miljömärkning, RSK, pris och länk.

Sortimentet kommer från:
  - en uppladdad fil (Excel eller CSV) med en rad per produkt; rubrikraden säger vilken kolumn som är vad
  - webbplatsen (VVS_HOUSE_BRAND_URL, standard https://alternabadrum.se/): produktsidorna läses på servern
    (sitemap -> produktsidor -> strukturerad produktdata och specifikationstabeller)
  - annars ett litet startsortiment: de produkter som står i det manuella facit för Ryttargården

Kolumner i en uppladdad fil (rubriker, valfri ordning): RSK, Benämning, Serie, Kategori, Bredd, Höjd, Djup,
Material, Miljömärkning, Pris, URL.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import os
import re
import threading
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from .auth import current_admin, current_user
from .db import User
from .storage import storage

router = APIRouter(tags=["eget varumärke"])
log = logging.getLogger("vvs.brand")
KEY = "brands/house.json"
BRAND = os.environ.get("VVS_HOUSE_BRAND", "Alterna")
URL = os.environ.get("VVS_HOUSE_BRAND_URL", "https://alternabadrum.se/")
SEED = os.path.join(os.path.dirname(__file__), "data", "alterna_seed.json")

_CACHE: dict[str, Any] = {}
_JOB: dict[str, Any] = {"state": "idle"}


def catalog() -> dict[str, Any]:
    if "c" not in _CACHE:
        if storage.exists(KEY):
            with storage.open(KEY) as fh:
                _CACHE["c"] = json.load(fh)
        else:
            with open(SEED, encoding="utf-8") as fh:
                _CACHE["c"] = json.load(fh)
    return _CACHE["c"]


def products() -> list[dict[str, Any]]:
    return catalog().get("products") or []


def _save(c: dict[str, Any]) -> None:
    storage.put(KEY, io.BytesIO(json.dumps(c, ensure_ascii=False).encode("utf-8")))
    _CACHE["c"] = c


def _status() -> dict[str, Any]:
    c = catalog()
    return {"brand": c.get("brand") or BRAND, "n": len(c.get("products") or []), "source": c.get("source"),
            "updated_at": c.get("updated_at"), "url": URL, "import": dict(_JOB)}


@router.get("/api/brand-catalog")
def brand_status(user: User = Depends(current_user)):
    return _status()


@router.get("/api/brand-catalog/products")
def brand_products(user: User = Depends(current_user)):
    return {"brand": catalog().get("brand") or BRAND, "products": products()}


# ---------------------------------------------------------------- fil

HEAD = {"rsk": ("rsk", "rsk-nr", "rsk nr", "rsknummer"), "name": ("benämning", "namn", "produkt", "artikel", "name"),
        "series": ("serie", "series"), "category": ("kategori", "sort", "produktgrupp", "category"),
        "bredd": ("bredd", "b", "bredd mm", "bredd (mm)"), "höjd": ("höjd", "h", "höjd mm", "höjd (mm)"),
        "djup": ("djup", "d", "djup mm", "djup (mm)"), "material": ("material",),
        "labels": ("miljömärkning", "miljö", "miljökrav", "certifiering"), "price": ("pris", "pris per styck", "price"),
        "url": ("url", "länk", "link")}


def _col(h: str) -> str | None:
    h = re.sub(r"\s+", " ", (h or "").strip().lower())
    return next((k for k, names in HEAD.items() if h in names), None)


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(re.sub(r"[^\d,.\-]", "", str(v)).replace(",", "."))
    except ValueError:
        return None


def rows_to_products(rows: list[list[Any]]) -> list[dict[str, Any]]:
    head_i, cols = None, {}
    for i, r in enumerate(rows[:10]):
        found = {}
        for j, c in enumerate(r):
            k = _col(str(c or ""))
            if k and k not in found:
                found[k] = j
        if "name" in found:
            head_i, cols = i, found
            break
    if head_i is None:
        raise HTTPException(422, "Hittade ingen rubrikrad med Benämning (och gärna RSK, Bredd, Höjd, Pris)")
    out = []
    for r in rows[head_i + 1:]:
        g = lambda k: (r[cols[k]] if k in cols and cols[k] < len(r) else None)
        name = str(g("name") or "").strip()
        if not name:
            continue
        p: dict[str, Any] = {"name": name, "rsk": re.sub(r"\D", "", str(g("rsk") or ""))[:7] or "",
                             "series": str(g("series") or ""), "category": str(g("category") or ""),
                             "material": str(g("material") or ""), "url": str(g("url") or ""),
                             "price": _num(g("price"))}
        for k in ("bredd", "höjd", "djup"):
            v = _num(g(k))
            if v:
                p[k] = int(v * 10) if v < 200 and k == "bredd" and "cm" in str(g(k)) else int(v)
        lab = str(g("labels") or "")
        if lab:
            p["labels_text"] = [lab]
        out.append(p)
    return out


@router.post("/api/brand-catalog/upload")
async def brand_upload(file: UploadFile = File(...), admin: User = Depends(current_admin)):
    data = await file.read()
    name = (file.filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        rows = [list(r) for ws in wb.worksheets[:1] for r in ws.iter_rows(values_only=True)]
    elif name.endswith((".csv", ".txt")):
        text = data.decode("utf-8-sig", "replace")
        rows = list(csv.reader(io.StringIO(text), csv.Sniffer().sniff(text[:4000], delimiters=";,\t")))
    else:
        raise HTTPException(400, "Sortimentet ska vara Excel (.xlsx) eller CSV")
    prods = rows_to_products(rows)
    if not prods:
        raise HTTPException(422, "Inga produkter i filen")
    _save({"brand": BRAND, "source": f"fil: {file.filename}", "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
           "products": prods})
    return _status()


# ---------------------------------------------------------------- webbplatsen

def _jsonld_products(html: str) -> list[dict[str, Any]]:
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if "@graph" in d:
                    stack += d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]]
                t = d.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    out.append(d)
    return out


def _spec_pairs(html: str) -> dict[str, str]:
    """Specifikationstabeller: <th>/<td>, <dt>/<dd>, och "Etikett: värde" i listor."""
    from html import unescape
    pairs = {}
    for a, b in re.findall(r"<(?:th|dt)[^>]*>(.*?)</(?:th|dt)>\s*<(?:td|dd)[^>]*>(.*?)</(?:td|dd)>", html, re.S | re.I):
        k = unescape(re.sub(r"<[^>]+>", "", a)).strip().rstrip(":").lower()
        v = unescape(re.sub(r"<[^>]+>", " ", b)).strip()
        if k and v and len(k) < 40:
            pairs.setdefault(k, re.sub(r"\s+", " ", v))
    for k, v in re.findall(r"<li[^>]*>\s*(?:<[^>]+>)*\s*([A-Za-zÅÄÖåäö \-]{3,30}):\s*(?:</[^>]+>)?\s*([^<]{1,80})</li>", html):
        pairs.setdefault(k.strip().lower(), v.strip())
    return pairs


def product_from_page(url: str, html: str) -> dict[str, Any] | None:
    lds = _jsonld_products(html)
    pairs = _spec_pairs(html)
    if not lds and not any(k in pairs for k in ("bredd", "rsk", "rsk-nummer", "artikelnummer")):
        return None
    d = lds[0] if lds else {}
    name = d.get("name") or (re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S) or [None, ""])[1]
    name = re.sub(r"<[^>]+>|\s+", " ", str(name)).strip()
    if not name:
        return None
    props = {str(p.get("name", "")).lower(): str(p.get("value", "")) for p in d.get("additionalProperty") or []
             if isinstance(p, dict)}
    allp = {**pairs, **props}
    rsk = next((re.sub(r"\D", "", v)[:7] for k, v in allp.items() if "rsk" in k and re.sub(r"\D", "", v)), "") \
        or (re.search(r"RSK[^0-9]{0,15}(\d{3}\s?\d{2}\s?\d{2})", html) or [None, ""])[1].replace(" ", "")
    offers = d.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    p: dict[str, Any] = {"name": name, "rsk": rsk, "url": url, "price": _num(offers.get("price")),
                         "category": str(d.get("category") or ""), "description": re.sub(r"<[^>]+>", " ", str(d.get("description") or ""))[:600],
                         "material": next((v for k, v in allp.items() if "material" in k), ""),
                         "series": next((v for k, v in allp.items() if k in ("serie", "series")), "")}
    for key, words in (("bredd", ("bredd", "width")), ("höjd", ("höjd", "height")), ("djup", ("djup", "depth"))):
        v = next((v for k, v in allp.items() if any(k.startswith(w) for w in words)), None)
        n = _num(v)
        if n:
            p[key] = int(n * 10) if "cm" in str(v).lower() else int(n)
    labels = [v for k, v in allp.items() if any(w in k for w in ("miljö", "certifi", "märkning"))]
    if labels:
        p["labels_text"] = labels
    return p


def _crawl(base: str) -> None:
    import httpx
    from xml.etree import ElementTree as ET
    _JOB.update(state="running", started=dt.datetime.now(dt.timezone.utc).isoformat(), done=0, found=0, error="")
    try:
        with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": "Mozilla/5.0 (compatible; sortiment)"}) as c:
            urls: list[str] = []
            seen_maps: set[str] = set()
            todo = [base.rstrip("/") + p for p in ("/sitemap.xml", "/sitemap_index.xml", "/product-sitemap.xml")]
            while todo and len(seen_maps) < 40:
                sm = todo.pop(0)
                if sm in seen_maps:
                    continue
                seen_maps.add(sm)
                r = c.get(sm)
                if r.status_code != 200 or "<" not in r.text[:200]:
                    continue
                try:
                    root = ET.fromstring(r.content)
                except ET.ParseError:
                    continue
                locs = [e.text.strip() for e in root.iter() if e.tag.endswith("loc") and e.text]
                for loc in locs:
                    if loc.endswith(".xml"):
                        todo.append(loc)
                    elif re.search(r"/(produkt|product|produkter|products)/", loc):
                        urls.append(loc)
            urls = list(dict.fromkeys(urls))[:3000]
            _JOB["total"] = len(urls)
            if not urls:
                raise RuntimeError("Hittade inga produktsidor i webbplatsens sitemap")
            prods = []
            for u in urls:
                try:
                    r = c.get(u)
                    if r.status_code == 200:
                        p = product_from_page(u, r.text)
                        if p:
                            prods.append(p)
                except Exception:                                    # noqa: BLE001
                    pass
                _JOB["done"] += 1
                _JOB["found"] = len(prods)
            if not prods:
                raise RuntimeError("Produktsidorna hade ingen produktdata som gick att läsa")
            _save({"brand": BRAND, "source": f"webb: {base}", "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "products": prods})
            _JOB["state"] = "done"
    except Exception as e:                                           # noqa: BLE001
        log.warning("Sortimentet kunde inte läsas från webben", exc_info=True)
        _JOB.update(state="failed", error=str(e)[:300])


class ImportIn(BaseModel):
    url: str = ""


@router.post("/api/brand-catalog/import")
def brand_import(body: ImportIn, admin: User = Depends(current_admin)):
    """Läs sortimentet från webbplatsen. Tar några minuter; följ förloppet med GET /api/brand-catalog."""
    if _JOB.get("state") == "running":
        raise HTTPException(409, "Inläsningen pågår redan")
    url = (body.url or URL).strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "Länken ska börja med https://")
    threading.Thread(target=_crawl, args=(url,), daemon=True, name="sortiment").start()
    return _status()
