"""Alternas sortiment -> backend/app/data/alterna_catalog.json (läses av backend/app/brand_catalog.py).

Webbplatsen (https://alternabadrum.se/) är Drupal 10 + Drupal Commerce. sitemap.xml listar alla produktsidor
under /produkter/<kategori>/<underkategori>/<produkt>. Själva produktdatan (varianter, mått, RSK, pris,
miljömärkning) står inte i sidans HTML: en React-komponent hämtar den i webbläsaren från sajtens JSON:API.
Skriptet läser därför bara det som står i den statiska HTML:en (JSON-LD och specifikationstabeller, om sådana
finns) och tar annars data ur en exportfil (Excel/CSV med en rad per artikel, t.ex. en prislista eller
RSK-export från Alterna) med --file.

Användning:
  python tools/alterna_import.py --file alterna_prislista.xlsx     # export -> katalog
  python tools/alterna_import.py --web                             # sitemap + produktsidornas HTML
  python tools/alterna_import.py --check                           # jämför katalogen med facit

Webbläsningen respekterar robots.txt och gör högst ett anrop per 0,6 s.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html as htmllib
import io
import json
import os
import re
import sys
import time
import urllib.robotparser
from typing import Any

BASE = "https://alternabadrum.se/"
OUT = os.path.join(os.path.dirname(__file__), "..", "backend", "app", "data", "alterna_catalog.json")
UA = "Mozilla/5.0 (compatible; alterna-sortiment-import)"
DELAY = 0.6

# url-segment (underkategori) -> sakvara
CATEGORY = {
    "underskap-och-kommoder": "underskåp/kommod", "spegelskap": "spegelskåp", "speglar": "spegel",
    "vagg-och-hogskap": "vägg-/högskåp", "belysning": "belysning", "mobelpaket": "möbelpaket",
    "tillbehor-till-badrumsmobler": "möbeltillbehör",
    "elhanddukstorkar": "handdukstork", "vattenburna-torkar": "handdukstork",
    "kombinerade-vattenburen-med-elpatron": "handdukstork", "elpatroner": "elpatron",
    "reglerventiler": "reglerventil",
    "duschhornor-rak": "duschhörna", "duschhornor-rund": "duschhörna", "duschkabiner": "duschkabin",
    "nischdorrar": "duschvägg/nischdörr", "skarmvaggar": "duschvägg", "u-montage": "duschvägg",
    "vikdorrar": "duschvägg/nischdörr",
    "tvattstall": "tvättställ", "tvattstallspaket": "tvättställ", "wc-vagghangda": "wc", "wc-sitsar": "wc-sits",
    "bottenventiler": "bottenventil", "vattenlas": "vattenlås",
    "duschset": "duschset", "takduschar": "takdusch", "duschhandtag": "handdusch", "duschslangar": "duschslang",
    "ram-golvbrunn": "golvbrunnsram", "ram-med-galler-golvbrunn": "golvbrunnsram",
    "akrylbadkar": "badkar", "emaljbadkar": "badkar", "badkarsvaggar": "badkarsvägg",
}
# badrumstillbehör: sakvaran står i namnet
ACCESSORY = [("toalettpappershållare", "toalettpappershållare"), ("reservpappershållare", "reservpappershållare"),
             ("handdukskrok", "krok"), ("krok", "krok"), ("handdukshängare", "handdukshängare"),
             ("handdukshållare", "handdukshängare"), ("hylla", "hylla"), ("tvålkorg", "tvålkorg"),
             ("tvålpump", "tvålpump"), ("toalettborste", "toalettborste"), ("blandare", "blandare"),
             ("spegel", "spegel")]
LABELS = ("Byggvarubedömningen", "Svanen", "Sunda Hus", "BASTA", "Möbelfakta", "E1", "EU Ecolabel", "FSC", "PEFC",
          "Svensk Byggtjänst", "EPD", "Breeam")
FACIT = [("8948526", "Basic planspegel", {"bredd": 450, "höjd": 900}), ("8920499", "Picto toalettpappershållare", {}),
         ("8920498", "Picto handdukskrok", {}), ("8753247", "Ray elhanddukstork", {"bredd": 530, "höjd": 700}),
         ("8912079", "Isella Aqua underskåp", {}), ("8912081", "Ariella Aqua 60 spegelskåp", {"bredd": 600}),
         ("8946360", "Ariella Aqua 50 spegelskåp", {"bredd": 500}), ("7333529", "Lusso duschhörna", {"bredd": 800, "djup": 800})]


# ---------------------------------------------------------------- normalisering

def rsk_of(v: Any) -> str:
    """'894 85 26' / '8948526' -> '8948526'; annat än 7 siffror -> ''."""
    d = re.sub(r"\D", "", str(v or ""))
    return d if len(d) == 7 else ""


def mm(v: Any, unit_hint: str = "") -> int | None:
    if v in (None, ""):
        return None
    s = str(v).lower()
    m = re.search(r"\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    n = float(m.group().replace(",", "."))
    if "cm" in s or "cm" in unit_hint:
        n *= 10
    elif re.search(r"\bm\b", s) and n < 10:
        n *= 1000
    return int(round(n)) or None


def dims_from_name(name: str) -> dict[str, int]:
    """'450 x 900' -> 450x900 mm; '53x70' (cm, handdukstorkar) -> 530x700; '80 x 80' -> 800x800."""
    m = re.search(r"(\d{2,4})\s*[x×]\s*(\d{2,4})(?:\s*[x×]\s*(\d{2,4}))?", name)
    if not m:
        return {}
    vals = [int(g) for g in m.groups() if g]
    if max(vals) < 200:                    # cm
        vals = [v * 10 for v in vals]
    out = {"bredd": vals[0], "höjd": vals[1]}
    if len(vals) == 3:
        out["djup"] = vals[2]
    return out


def category_for(url: str, name: str) -> str:
    segs = [s for s in re.sub(r"^https?://[^/]+", "", url).split("/") if s]
    low = name.lower()
    if len(segs) >= 2 and segs[1] == "badrumstillbehor" or "tillbehor" in (segs[2] if len(segs) > 2 else ""):
        for word, cat in ACCESSORY:
            if word in low:
                return cat
    for s in segs[1:]:
        if s in CATEGORY:
            return CATEGORY[s]
    for word, cat in ACCESSORY:
        if word in low:
            return cat
    return segs[2] if len(segs) > 2 else ""


def labels_in(text: str) -> list[str]:
    return [l for l in LABELS if re.search(r"(?<![A-Za-zÅÄÖåäö])" + re.escape(l) + r"(?![A-Za-zÅÄÖåäö])", text)]


def product(name: str, **kw: Any) -> dict[str, Any]:
    """En produkt i katalogens form med exakt de fältnamn brand_catalog/equivalent läser."""
    p: dict[str, Any] = {"name": name.strip(), "series": kw.get("series") or "", "category": kw.get("category") or "",
                         "rsk": rsk_of(kw.get("rsk")), "article_number": str(kw.get("article_number") or "").strip(),
                         "bredd": None, "höjd": None, "djup": None, "material": kw.get("material") or "",
                         "finish": kw.get("finish") or "", "labels_text": kw.get("labels_text") or [],
                         "price": kw.get("price"), "url": kw.get("url") or "",
                         "description": re.sub(r"\s+", " ", kw.get("description") or "").strip()[:400]}
    guess = dims_from_name(p["name"])
    for k in ("bredd", "höjd", "djup"):
        p[k] = mm(kw.get(k)) or guess.get(k)
    if not p["category"]:
        p["category"] = category_for(p["url"], p["name"])
    return p


# ---------------------------------------------------------------- källa: exportfil

HEAD = {"rsk": ("rsk", "rsk-nr", "rsk nr", "rsknummer", "rsk-nummer"),
        "article_number": ("artikelnummer", "art.nr", "artnr", "art nr", "artikelnr"),
        "name": ("benämning", "namn", "produkt", "produktnamn", "artikel", "name", "beskrivning"),
        "series": ("serie", "series"), "category": ("kategori", "sort", "produktgrupp", "category"),
        "bredd": ("bredd", "bredd mm", "bredd (mm)", "b"), "höjd": ("höjd", "höjd mm", "höjd (mm)", "h"),
        "djup": ("djup", "djup mm", "djup (mm)", "d"), "material": ("material",),
        "finish": ("kulör", "färg", "finish", "ytbehandling"),
        "labels": ("miljömärkning", "miljö", "certifiering", "miljöbedömning"),
        "price": ("pris", "pris per styck", "price", "cirkapris", "ca-pris"), "url": ("url", "länk", "link")}


def from_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    norm = lambda h: re.sub(r"\s+", " ", str(h or "").strip().lower())
    head_i, cols = None, {}
    for i, r in enumerate(rows[:15]):
        found = {}
        for j, c in enumerate(r):
            k = next((k for k, names in HEAD.items() if norm(c) in names), None)
            if k and k not in found:
                found[k] = j
        if "name" in found:
            head_i, cols = i, found
            break
    if head_i is None:
        sys.exit("Hittade ingen rubrikrad med Benämning/Namn")
    out = []
    for r in rows[head_i + 1:]:
        g = lambda k: r[cols[k]] if k in cols and cols[k] < len(r) else None
        name = str(g("name") or "").strip()
        if not name:
            continue
        lab = str(g("labels") or "")
        price = g("price")
        try:
            price = float(re.sub(r"[^\d,.]", "", str(price)).replace(",", ".")) if price not in (None, "") else None
        except ValueError:
            price = None
        out.append(product(name, **{k: g(k) for k in ("rsk", "article_number", "series", "category", "bredd", "höjd",
                                                        "djup", "material", "finish", "url")},
                           labels_text=[s.strip() for s in re.split(r"[;,\n]", lab) if s.strip()], price=price))
    return out


def read_file(path: str) -> list[dict[str, Any]]:
    if path.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = [list(r) for ws in wb.worksheets for r in ws.iter_rows(values_only=True)]
    else:
        text = open(path, encoding="utf-8-sig", errors="replace").read()
        rows = list(csv.reader(io.StringIO(text), csv.Sniffer().sniff(text[:4000], delimiters=";,\t")))
    return from_rows(rows)


# ---------------------------------------------------------------- källa: webbplatsen (statisk HTML)

def _get(client, url: str, robots: urllib.robotparser.RobotFileParser):
    if not robots.can_fetch(UA, url):
        return None
    time.sleep(DELAY)
    r = client.get(url)
    return r if r.status_code == 200 else None


def product_urls(client, robots) -> list[str]:
    r = _get(client, BASE + "sitemap.xml", robots)
    locs = re.findall(r"<loc>([^<]+)</loc>", r.text if r else "")
    # produktsidor ligger på djup 4: /produkter/<kategori>/<underkategori>/<produkt>
    return [u for u in locs if re.match(re.escape(BASE) + r"produkter/[^/]+/[^/]+/.+", u)]


def from_page(url: str, html: str) -> dict[str, Any] | None:
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        for x in (d if isinstance(d, list) else d.get("@graph", [d])):
            if isinstance(x, dict) and x.get("@type") == "Product":
                offers = x.get("offers") or {}
                offers = offers[0] if isinstance(offers, list) and offers else offers
                return product(x.get("name") or "", url=url, rsk=x.get("gtin7") or x.get("sku"),
                               description=x.get("description") or "", price=offers.get("price") if offers else None,
                               labels_text=labels_in(html))
    pairs = {htmllib.unescape(re.sub(r"<[^>]+>", "", a)).strip().rstrip(":").lower():
             htmllib.unescape(re.sub(r"<[^>]+>", " ", b)).strip()
             for a, b in re.findall(r"<(?:th|dt)[^>]*>(.*?)</(?:th|dt)>\s*<(?:td|dd)[^>]*>(.*?)</(?:td|dd)>", html, re.S)}
    if not any(k.startswith(("rsk", "bredd")) for k in pairs):
        return None
    title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    pick = lambda *ws: next((v for k, v in pairs.items() if any(k.startswith(w) for w in ws)), None)
    return product(htmllib.unescape(title.group(1)) if title else "", url=url, rsk=pick("rsk"),
                   article_number=pick("artikelnummer", "art.nr"), bredd=pick("bredd"), höjd=pick("höjd"),
                   djup=pick("djup"), material=pick("material") or "", finish=pick("kulör", "färg") or "",
                   series=pick("serie") or "", labels_text=labels_in(html))


def read_web() -> list[dict[str, Any]]:
    import httpx
    robots = urllib.robotparser.RobotFileParser(BASE + "robots.txt")
    robots.read()
    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": UA}) as c:
        urls = product_urls(c, robots)
        print(f"{len(urls)} produktsidor i sitemap.xml", file=sys.stderr)
        out, empty = [], 0
        for u in urls:
            r = _get(c, u, robots)
            p = from_page(u, r.text) if r else None
            if p:
                out.append(p)
            else:
                empty += 1
    if empty:
        print(f"{empty} sidor saknade produktdata i HTML:en (den laddas i webbläsaren)", file=sys.stderr)
    return out


# ---------------------------------------------------------------- facit och utskrift

def check(products: list[dict[str, Any]]) -> list[str]:
    by = {p["rsk"]: p for p in products if p.get("rsk")}
    out = []
    for rsk, name, dims in FACIT:
        p = by.get(rsk)
        if not p:
            out.append(f"SAKNAS {rsk} {name}")
            continue
        words = [w for w in re.findall(r"[a-zåäö]+", name.lower()) if len(w) > 3]
        bad = [w for w in words if w not in p["name"].lower()]
        diff = {k: (p.get(k), v) for k, v in dims.items() if p.get(k) != v}
        out.append(f"{'OK' if not bad and not diff else 'AVVIKER'} {rsk} {p['name']}"
                   + (f" (namn saknar {bad})" if bad else "") + (f" (mått {diff})" if diff else ""))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", help="exportfil (xlsx/csv) med en rad per artikel")
    ap.add_argument("--web", action="store_true", help="läs sitemap och produktsidornas HTML")
    ap.add_argument("--check", action="store_true", help="jämför befintlig katalog med facit")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    if a.check and not (a.file or a.web):
        prods = json.load(open(a.out, encoding="utf-8"))["products"]
        print("\n".join(check(prods)))
        return
    if a.file:
        prods, source = read_file(a.file), f"fil: {os.path.basename(a.file)}"
    elif a.web:
        prods, source = read_web(), f"webb: {BASE}"
    else:
        ap.error("ange --file, --web eller --check")
    if not prods:
        sys.exit("Inga produkter lästes; katalogen skrevs inte")
    seen, uniq = set(), []
    for p in prods:                        # varianter är egna rader; dubbletter (samma RSK eller namn+url) bort
        key = p["rsk"] or (p["name"], p["url"], p["bredd"])
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    today = dt.date.today().isoformat()
    cat = {"brand": "Alterna", "source": f"{source} {today}", "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
           "products": uniq}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(cat, fh, ensure_ascii=False, indent=1)
    print(f"{len(uniq)} produkter -> {a.out}")
    print("\n".join(check(uniq)))


if __name__ == "__main__":
    main()
