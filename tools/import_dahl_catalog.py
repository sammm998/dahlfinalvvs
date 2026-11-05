"""Dahls produktkatalog 2026 -> backend/app/data/dahl_catalog.json.gz (samma form som material.json.gz).

Katalogen ligger i en iPaper-bläddringsvy på katalog.dahl.se. Själva PDF:en nås via
<vy>/GetPDF.ashx, som omdirigerar till cdn.ipaper.io. Där den värden inte går att nå läser skriptet
i stället sidtexterna som vyn bäddar in i sin HTML (window.staticSettings.pageTexts, en text per sida).

Hur artiklarna tas fram:
  1. Artikelnummerregistret (sidorna som börjar med "Artikelnummerregister") ger för varje artikel
     art.nr, kalkylgrupp och flik:sida. Det är källan till vilka artiklar som finns.
  2. flik:sida översätts till bläddringsvyns sidnummer med hjälp av sidfötterna ("19:4" sist på sidan).
  3. På artikelns sida letas art.nr upp i tabellerna ("Art.nr 1965604 1965605 Dim 10xG15 12xG10" eller
     "Art.nr Dim 1966438 10 1966439 12"). Benämningen tas ur texten före tabellen och dimensionen ur
     tabellens kolumner.
  4. Kapitel = flikens namn (flikregistret i början av katalogen), produktgrupp = rubriken i flikens
     innehållsförteckning som pekar på sidan.

En del av katalogtexten har ett typsnitt med förskjuten teckenkodning (t.ex. "EO\\IULDY]LQNQLQJ" för
"blyfriavzinkning"). Sådana ord avkodas (decode_shifted). Mellanslag och siffror försvinner i de partierna.
Det går inte att återställa.

Användning:
  python tools/import_dahl_catalog.py                    # hämtar vyn från katalog.dahl.se
  python tools/import_dahl_catalog.py --html sida.html   # en sparad kopia av vyn
  python tools/import_dahl_catalog.py --pdf katalog.pdf  # PDF:en (sidtext via pymupdf), om den gick att hämta
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import urllib.request

URL = "https://katalog.dahl.se/dahl-sverige-ab/dahl-produktkatalog-2026pdf/"
SOURCE = "Dahls produktkatalog 2026"
OUT = os.path.join(os.path.dirname(__file__), "..", "backend", "app", "data", "dahl_catalog.json.gz")

ART = re.compile(r"K?\d{5,7}")
GRP = re.compile(r"[A-Z]{2}\d{4}")
FLIK = re.compile(r"(\d{1,2}):(\d{1,3})")
ARTNR_LABELS = ("Art.nr", "Artikelnr")


# ---------------------------------------------------------------- källor

def load_page_texts_from_html(html: str) -> list[str]:
    i = html.find("staticSettings")
    if i < 0:
        raise SystemExit("hittar inte window.staticSettings i sidan")
    j = html.find("{", i)
    settings, _ = json.JSONDecoder().raw_decode(html[j:])
    return list(settings["pageTexts"])


def load_page_texts_from_pdf(path: str) -> list[str]:
    import pymupdf  # finns i backend/requirements.txt
    doc = pymupdf.open(path)
    try:
        return [re.sub(r"\s+", " ", p.get_text("text")).strip() for p in doc]
    finally:
        doc.close()


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "dahl-catalog-import"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- förskjuten teckenkodning

_LIG = {"ȴ": "fi", "ȵ": "fl", "΍": "ff", "Ζ": "I", "Ȃ": "–", "ȋ": ""}


def _shift(ch: str) -> str:
    o = ord(ch)
    if ch in _LIG:
        return _LIG[ch]
    if 33 <= o <= 93:
        return chr(o + 29)
    if 94 <= o <= 193:
        return chr(o + 62)
    return ch


def decode_shifted(tok: str) -> str:
    return "".join(_shift(c) for c in tok)


_SV = set("abcdefghijklmnopqrstuvwxyzåäöé")


def is_shifted(tok: str) -> bool:
    """Ett ord i det förskjutna typsnittet: avkodat ser det ut som svensk text, det ursprungliga gör det inte."""
    if len(tok) < 4 or re.search(r"[a-qt-zåäöÅÄÖéABC]", tok) or re.fullmatch(r"[\d\W]+", tok):
        return False
    dec = decode_shifted(tok)
    letters = sum(c.lower() in _SV for c in dec)
    vowels = sum(c.lower() in "aeiouyåäöé" for c in dec)
    return letters / len(dec) >= 0.7 and vowels / len(dec) >= 0.2


def clean_tokens(text: str) -> list[str]:
    """Orden på en sida, med förskjutna ord avkodade. Mellanslagen saknas i de partierna; ett nytt ord
    antas börja där en gemen följs av en versal ("StålrörochStåldelar" -> "Stålröroch Ståldelar")."""
    out: list[str] = []
    for t in text.split():
        if is_shifted(t):
            w = re.sub(r"(?<=[a-zåäöé])(?=[A-ZÅÄÖ])", " ", decode_shifted(t))
            w = re.sub(r"(?<=[a-zåäöé])och(?= |$)", " och", w)  # "Stålröroch Ståldelar"
            out.extend(w.split())
        else:
            out.append(t)
    return out


# ---------------------------------------------------------------- sidor och register

def footers(T: list[str], first: int) -> dict[int, tuple[int, int]]:
    """Sidfot "flik:sida" -> sidindex. Bara sidor efter registret räknas (registret är fullt av flik:sida)."""
    anchors: dict[int, tuple[int, int]] = {}
    rx = re.compile(r"(?:^|\s)(\d{1,2}):(\d{1,3})(?:\s+\d{1,4})?(?:\s+www\.dahl\.se)?\s*$")
    for i in range(first, len(T)):
        m = rx.search(T[i])
        if not m:
            continue
        fl, s = int(m.group(1)), int(m.group(2))
        if fl in anchors:
            i0, s0 = anchors[fl]
            if i - i0 != s - s0:  # en sidfot som inte stämmer med flikens övriga (t.ex. ett årtal) räknas inte
                continue
        else:
            anchors[fl] = (i, s)
    return anchors


def page_index(anchors, fl: int, s: int, n: int) -> int | None:
    if fl not in anchors:
        return None
    i0, s0 = anchors[fl]
    i = i0 + (s - s0)
    return i if 0 <= i < n else None


def footers_of(T, i: int, anchors) -> tuple[int, int] | None:
    for fl, (i0, s0) in anchors.items():
        nxt = min((j for f2, (j, _) in anchors.items() if j > i0), default=len(T))
        if i0 <= i < nxt:
            return fl, s0 + (i - i0)
    return None


def register(T: list[str]) -> tuple[list[dict], list[int], list[str]]:
    """Artikelnummerregistret: [{dahl, grp, flik, sida}], registrets sidor och varningar."""
    rows: list[dict] = []
    pages = [i for i, p in enumerate(T) if p.lstrip().startswith("Artikelnummerregister")]
    warn: list[str] = []
    for i in pages:
        toks = T[i].split()
        A = [x for x in toks if ART.fullmatch(x)]
        G = [x for x in toks if GRP.fullmatch(x)]
        F = [x for x in toks if FLIK.fullmatch(x)]
        if len(A) == len(G) == len(F):
            for a, g, f in zip(A, G, F):
                fl, s = map(int, f.split(":"))
                rows.append({"dahl": a, "grp": g, "flik": fl, "sida": s, "reg_page": i + 1})
        else:
            warn.append(f"registersida {i + 1}: {len(A)} art.nr, {len(G)} kalkylgrupper, {len(F)} flik:sida")
            rows.extend(_register_partial(i, A, G, F, warn))
    return rows, pages, warn


def _register_partial(i, A, G, F, warn) -> list[dict]:
    """Registersida där kolumnerna inte har lika många värden. Om art.nr och kalkylgrupp stämmer men en
    flik:sida saknas tas flik:sida bara med där ordningen säkert stämmer (räknat från början och från slutet
    ger samma värde); annars lämnas den tom."""
    out = []
    if len(A) == len(G) and len(F) == len(A) - 1:
        fwd = F + [None]
        bwd = [None] + F
        for a, g, f1, f2 in zip(A, G, fwd, bwd):
            f = f1 if f1 == f2 else None
            fl, s = (map(int, f.split(":")) if f else (None, None))
            out.append({"dahl": a, "grp": g, "flik": fl, "sida": s, "reg_page": i + 1})
        return out
    if len(G) == len(F) and len(A) < len(G):
        # art.nr saknas i texten (t.ex. i ett annat typsnitt): raderna går inte att para ihop säkert
        # art.nr saknas i texten (t.ex. i ett annat typsnitt): kolumnerna går inte att para ihop säkert.
        # Artiklarna tas med utan flik:sida; sidan letas upp på produktsidorna i stället.
        warn.append(f"registersida {i + 1}: {len(G) - len(A)} art.nr saknas i sidtexten; "
                    f"{len(A)} art.nr tas med utan registrets flik:sida")
        return [{"dahl": a, "grp": None, "flik": None, "sida": None, "reg_page": i + 1} for a in A]
    warn.append(f"registersida {i + 1}: hoppas över")
    return out


# ---------------------------------------------------------------- kapitel och produktgrupper

def chapters(T: list[str]) -> dict[int, str]:
    """Flikarnas namn ur flikregistret ("Tryckrör Avloppsystem 1 Stålrör och Ståldelar 2 ...")."""
    for p in T[:20]:
        if "Artikelnummer register" in p or "Artikelnummerregister" in p[:40] and " 1 " in p:
            toks = clean_tokens(p)
            if "register" not in toks:
                continue
            toks = toks[toks.index("register") + 1:]
            out, cur, want = {}, [], 1
            for t in toks:
                if t == str(want):
                    out[want] = " ".join(cur).strip()
                    cur, want = [], want + 1
                else:
                    cur.append(t)
            if len(out) >= 20:
                # Flikregistret har namn på två rader; i sidtexten hamnar andra raden av flik 15 före
                # flik 16:s namn ("Oljebrännare och Tillbehör Radiatorer 16"). Flikarnas innehåll
                # (pannor, brännare respektive radiatorer) visar var gränsen går.
                if out.get(16, "").startswith("Oljebrännare") and out[16].endswith("Radiatorer"):
                    out[15] = out.get(15, "") + ", " + out[16][: -len("Radiatorer")].strip()
                    out[16] = "Radiatorer"
                return out
    return {}


def toc(T: list[str], first: int) -> dict[int, list[tuple[int, str]]]:
    """Flikarnas innehållsförteckningar: flik -> [(sida, rubrik)]."""
    out: dict[int, list[tuple[int, str]]] = {}
    rx = re.compile(r"\s*\.?\s*(\d{1,2}):(\d{1,3})")
    for i in range(first, len(T)):
        p = T[i]
        if "Innehållsförteckning" not in p[:40]:
            continue
        body = p[p.index("Innehållsförteckning") + len("Innehållsförteckning"):]
        pos = 0
        for m in rx.finditer(body):
            name = " ".join(clean_tokens(body[pos:m.start()])).strip(" .")
            name = re.sub(r"^\d{1,2}\s+", "", name)
            pos = m.end()
            if re.search(r"[A-Za-zÅÄÖåäö]{3}", name) and not re.search(r"\d{3,}", name):
                out.setdefault(int(m.group(1)), []).append((int(m.group(2)), name))
    return out


def product_group(tocs, fl: int | None, s: int | None) -> str:
    """Rubriken i innehållsförteckningen som pekar på sidan, annars närmaste rubrik före."""
    if fl is None or fl not in tocs:
        return ""
    exact = sorted({n for ss, n in tocs[fl] if ss == s})
    if exact:
        return exact[0] if len(exact) == 1 else " / ".join(exact[:3])
    before = [(ss, n) for ss, n in tocs[fl] if ss <= s]
    if not before:
        return ""
    best = max(ss for ss, _ in before)
    return sorted(n for ss, n in before if ss == best)[0]


# ---------------------------------------------------------------- tabeller på produktsidorna

def _has_digit(t: str) -> bool:
    return bool(re.search(r"\d", t))


def _is_value(t: str) -> bool:
    if re.search(r"[=;\[\]]", t):  # bildkoder i sidtexten ("[item=rectangle; filename=...]")
        return False
    return _has_digit(t) or t in ("x", "X", "-", "–", "/", "Ja", "Nej")


def parse_page(text: str, arts_here: set[str]) -> dict[str, dict]:
    """art.nr -> {heading, cols: [(rubrik, värde)], unit} för de artiklar som står i klartext på sidan."""
    toks = clean_tokens(text)
    found: dict[str, dict] = {}
    labels = [k for k, t in enumerate(toks) if t in ARTNR_LABELS]
    prev_end = 0
    for k in labels:
        context = toks[prev_end:k]
        j = k + 1
        is_art = lambda t: t in arts_here
        if j < len(toks) and is_art(toks[j]):
            # kolumnvis: Art.nr A1 A2 A3 Dim D1 D2 D3 [Längd m L1 L2 L3]
            arts = []
            while j < len(toks) and is_art(toks[j]):
                arts.append(toks[j]); j += 1
            cols_per_art: list[list[tuple[str, str]]] = [[] for _ in arts]
            for _ in range(3):
                h = []
                while j < len(toks) and len(h) < 5 and not _is_value(toks[j]) and toks[j] not in ARTNR_LABELS:
                    h.append(toks[j]); j += 1
                if not h:
                    break
                run = []
                while j < len(toks) and _is_value(toks[j]) and not is_art(toks[j]):
                    run.append(toks[j]); j += 1
                n = len(arts)
                vals = None
                if run and len(run) == n:
                    vals = run
                elif run and len(run) % n == 0:
                    w = len(run) // n
                    vals = [" ".join(run[q * w:(q + 1) * w]) for q in range(n)]
                if vals is None:
                    j -= len(run) + len(h)  # kolumnen gick inte att läsa: lämna texten till nästa rubrik
                    break
                for q in range(n):
                    cols_per_art[q].append((" ".join(h), vals[q]))
            for a, cols in zip(arts, cols_per_art):
                found.setdefault(a, {"context": context, "cols": cols})
        else:
            # radvis: Art.nr Dim [mm] A1 D1 A2 D2 ...
            h = []
            while j < len(toks) and len(h) < 6 and not is_art(toks[j]) and not _is_value(toks[j]) \
                    and toks[j] not in ARTNR_LABELS:
                h.append(toks[j]); j += 1
            heads = _split_heads(h)
            while j < len(toks) and is_art(toks[j]):
                a = toks[j]; j += 1
                vals = []
                while j < len(toks) and _is_value(toks[j]) and not is_art(toks[j]):
                    vals.append(toks[j]); j += 1
                cols = []
                if heads and len(vals) == len(heads):
                    cols = list(zip(heads, vals))
                elif heads and vals:
                    cols = [(" ".join(h), " ".join(vals))]
                found.setdefault(a, {"context": context, "cols": cols})
        prev_end = max(j, k + 1)
    return found


def _split_heads(h: list[str]) -> list[str]:
    """"Dim mm Längd m" -> ["Dim mm", "Längd m"]: en enhet hör till rubriken före."""
    units = {"mm", "m", "cm", "l", "g", "kg", "kW", "W", "V", "bar", "l/s", "l/min", "°C", "tum", "st"}
    out: list[str] = []
    for t in h:
        if out and (t in units or t.lower() in ("x",) or (out[-1].endswith(" x") )):
            out[-1] += " " + t
        else:
            out.append(t)
    return out


_HEAD_STOP = {"Art.nr", "Artikelnr", "Dim", "mm", "www.dahl.se"}


def _usable(w: str) -> bool:
    """Ett ord som kan ingå i en benämning: har bokstäver, är inte märkkod för en QR-kod eller sidfot."""
    if not re.search(r"[A-Za-zÅÄÖåäöé]", w) or re.search(r"[=;\[\]{}]", w):
        return False
    return w not in _HEAD_STOP and not FLIK.fullmatch(w) and not ART.fullmatch(w)


def heading(context: list[str]) -> str:
    """Benämningen ur texten före tabellen: första meningen, högst tio ord."""
    words = list(context)
    # siffror och mått som blev över från förra tabellen hör inte till rubriken
    while words and not _usable(words[0]):
        words.pop(0)
    words = [w for w in words if _usable(w) or _is_value(w) and not re.search(r"[=;\[\]]", w)]
    text = " ".join(words)
    m = re.search(r"^(.*?)(?:\.\s|\.$|:\s)", text)
    first = (m.group(1) if m else text).strip()
    return " ".join(first.split()[:10]).strip(" ,;–-")


def unit_from(context: list[str]) -> str | None:
    t = " ".join(context)
    m = re.search(r"Enhet:?\s*(Meter|meter|Par|par|styck|Styck|stk|m)\b", t)
    if not m:
        return None
    v = m.group(1).lower()
    return {"meter": "m", "m": "m", "par": "par", "styck": "st", "stk": "st"}[v]


def dim_text(cols: list[tuple[str, str]]) -> str:
    parts = []
    for h, v in cols:
        if not _has_digit(v):
            continue
        hl = h.split()
        if hl and hl[0] in ("Dim", "Dimension"):
            unit = " ".join(hl[1:])
            parts.append(f"{v} {unit}".strip())
        else:
            parts.append(f"{h} {v}".strip())
    return ", ".join(parts)


# ---------------------------------------------------------------- huvudprogram

def build(T: list[str], origin: str) -> tuple[dict, dict]:
    reg, reg_pages, warn = register(T)
    first = (max(reg_pages) + 1) if reg_pages else 0
    anchors = footers(T, first)
    chaps = chapters(T)
    tocs = toc(T, first)

    by_page: dict[int, set[str]] = {}
    occurs: dict[str, list[int]] = {}
    for i in range(first, len(T)):
        for t in set(T[i].split()):
            if ART.fullmatch(t):
                occurs.setdefault(t, []).append(i)
    for r in reg:
        r["idx"] = page_index(anchors, r["flik"], r["sida"], len(T)) if r["flik"] else None
        if r["idx"] is None and len(occurs.get(r["dahl"], [])) == 1:
            # flik:sida saknas i registret: artikelnumret står på exakt en produktsida
            r["idx"] = occurs[r["dahl"]][0]
            fs = footers_of(T, r["idx"], anchors)
            if fs:
                r["flik"], r["sida"] = fs
        if r["idx"] is not None:
            by_page.setdefault(r["idx"], set()).add(r["dahl"])
    parsed = {i: parse_page(T[i], arts) for i, arts in by_page.items()}

    rows, seen = [], set()
    stats = {"register": len(reg), "dubbletter": 0, "i_klartext": 0, "med_dim": 0, "utan_sida": 0}
    for r in reg:
        a = r["dahl"]
        if a in seen:
            stats["dubbletter"] += 1
            continue
        seen.add(a)
        i = r["idx"]
        info = parsed.get(i, {}).get(a) if i is not None else None
        pg = product_group(tocs, r["flik"], r["sida"])
        chap = chaps.get(r["flik"], "") if r["flik"] else ""
        unit = "st"  # "Grundenheten är styck, om inget annat anges." (sidfoten på varje produktsida)
        if info:
            stats["i_klartext"] += 1
            name = heading(info["context"]) or pg
            d = dim_text(info["cols"])
            if d:
                stats["med_dim"] += 1
                name = f"{name} {d}".strip()
            unit = unit_from(info["context"]) or unit
        else:
            name = pg
        if i is None:
            stats["utan_sida"] += 1
        rsk = a if re.fullmatch(r"\d{7}", a) else ""
        gr = " – ".join(x for x in (chap, pg) if x)
        rows.append({
            "a": rsk or a, "n": name, "e": unit, "p": None, "r": None, "w": None, "co2": None,
            "gr": gr, "y": "", "k": "", "pre": "",
            "dahl": a, "rsk": rsk, "page": (i + 1) if i is not None else None,
        })
    data = {"n": len(rows), "source": SOURCE, "origin": origin, "rows": rows}
    stats["varningar"] = warn
    stats["sidor"] = len(T)
    stats["kapitel"] = chaps
    return data, stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", help="sparad kopia av bläddringsvyn (annars hämtas den)")
    ap.add_argument("--pdf", help="katalogens PDF; sidtexten läses med pymupdf")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--stats", help="skriv statistik som JSON hit")
    a = ap.parse_args()
    if a.pdf:
        T, origin = load_page_texts_from_pdf(a.pdf), a.url + "GetPDF.ashx"
    else:
        html = open(a.html, encoding="utf-8").read() if a.html else fetch(a.url)
        T, origin = load_page_texts_from_html(html), a.url
    data, stats = build(T, origin)
    with gzip.open(a.out, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    if a.stats:
        with open(a.stats, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=1)
    print(f"{data['n']} artiklar -> {a.out}", file=sys.stderr)
    for w in stats["varningar"]:
        print("varning:", w, file=sys.stderr)


if __name__ == "__main__":
    main()
