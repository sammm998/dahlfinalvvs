"""En ritnings förteckning över utrustning (våtrumsuppställningar): numrerade positioner och var de står.

    UTRUSTNING
    15  Toalettrulleshållare, typ Beslagdesign Base 200, el. likv.
    16  Handdukskrok, typ Beslagdesign Base 200 4-krok, el. likv.
    19  Kommod INR, typ Core Solid XS, b=60 cm, slät lucka, kulör "Warm Clay", vitt porslin. Eller likv.

Ritningen visar också rumstyperna ("TYP A - STUDENTBOSTÄDER", "TYP K - WC 1013,1014") med positionsnumren i
vyerna. Ur det läses vilka typer en position finns i, och för typer med rumsnummer i rubriken hur många rum.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .rooms import _product

NUM = re.compile(r"^(\d{1,2})\*?$")
LEAD_NUM = re.compile(r"^(\d{1,2})\s+(\S.*)$")
TYPE_TITLE = re.compile(r"^TYP\s+([A-Z])\s*[-–]\s*(.+)$")


def _spans(page) -> list[tuple[float, float, float, float, str]]:
    out = []
    for b in page.get_text("dict").get("blocks", []):
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln.get("spans", [])).strip()
            if t:
                x0, y0, x1, _ = ln["bbox"]
                out.append((x0, y0, x1, ln["spans"][0]["size"], t))
    return out


def has_legend(doc) -> bool:
    return any(re.search(r"^\s*UTRUSTNING\s*$", p.get_text(), re.M) for p in doc)


def read_legend(doc) -> dict[str, Any]:
    """Positionerna i förteckningen, med de rumstyper de finns i."""
    positions: dict[int, dict[str, Any]] = {}
    types: dict[str, dict[str, Any]] = {}
    for page in doc:
        spans = _spans(page)
        head = [s for s in spans if s[4] == "UTRUSTNING"]
        if head:
            hx, hy = head[0][0], head[0][1]
            col = sorted([s for s in spans if hx - 15 <= s[0] <= hx + 400 and s[1] > hy], key=lambda s: (round(s[1]), s[0]))
            cur: dict[str, Any] | None = None
            for x0, y0, x1, size, t in col:
                if re.match(r"^(TM|TT|KM)\s", t) or t in ("A", "BET") or t.startswith("ENL."):
                    break
                m = NUM.match(t)
                lm = LEAD_NUM.match(t)
                if (m and x0 < hx + 20) or (lm and x0 < hx + 20):
                    n = int((m or lm).group(1))
                    cur = positions.setdefault(n, {"n": n, "text": [], "types": []})
                    if lm:
                        cur["text"].append(lm.group(2))
                    continue
                if cur is not None and x0 > hx + 10:
                    cur["text"].append(t)
        titles = []
        for x0, y0, x1, size, t in spans:
            tm = TYPE_TITLE.match(t)
            if tm:
                titles.append((x0, y0, tm.group(1), tm.group(2).strip()))
        legend_x = head[0][0] if head else page.rect.width
        for x0, y0, letter, what in titles:
            below = [ty for tx, ty, *_ in titles if abs(tx - x0) < 60 and ty > y0]
            y2 = min(below or [page.rect.height])
            right = [tx for tx, ty, *_ in titles if tx > x0 + 60 and abs(ty - y0) < 60]
            x2 = min(right or [legend_x - 5])
            nums = {int(NUM.match(t).group(1)) for sx, sy, sx1, sz, t in spans
                    if x0 - 20 <= sx < x2 and y0 < sy < y2 and NUM.match(t) and sz < 7}
            rooms = re.findall(r"(?<!\d)\d{4}(?!\d)", what)
            types[letter] = {"letter": letter, "title": what, "rooms": rooms, "positions": sorted(nums)}
            for n in nums:
                if n in positions or True:
                    positions.setdefault(n, {"n": n, "text": [], "types": []})["types"].append(letter)
    for p in positions.values():
        p["text"] = re.sub(r"\s+", " ", " ".join(p["text"])).replace(" ,", ",").strip()
    return {"positions": {n: p for n, p in positions.items() if p["text"]}, "types": types}


def legend_items(legend: dict[str, Any]) -> list[dict[str, Any]]:
    """Positionerna som poster. Antalet: summan av rummen i de typer positionen står i, när typernas rubriker
    anger rumsnummer; annars okänt här - det fylls i ur rumsbeskrivningen eller för hand."""
    types = legend["types"]
    out = []
    for n, p in sorted(legend["positions"].items()):
        in_types = sorted(set(p["types"]))
        counted = [types[t] for t in in_types if t in types]
        known = all(t["rooms"] for t in counted) and counted
        count = sum(len(t["rooms"]) for t in counted) if known else 0
        src = ("rum: " + ", ".join(f"typ {t['letter']} ({', '.join(t['rooms'])})" for t in counted)) if known else ""
        it = _product(p["text"], n, "Våtrumsuppställning", "", count, src, "Utrustning")
        it["id"], it["code"] = f"u{n}", str(n)
        it["category"] = "Utrustning enligt våtrumsuppställning"
        it["spec"]["Våtrumstyper"] = ", ".join(f"{t} ({types[t]['title']})" for t in in_types if t in types) or "–"
        if not known:
            it["quantity"] = it["total_quantity"] = None
            it["quantity_text"] = "antal per typ okänt"
            it["inferred"] = "Antalet rum per typ står inte på ritningen - hämtas ur rumsbeskrivningen eller anges"
        out.append(it)
    return out
