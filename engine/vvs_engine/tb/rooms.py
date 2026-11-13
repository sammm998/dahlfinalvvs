"""En typrumsbeskrivning (rumsbeskrivning utan AMA-kod) läst till inredning per rumstyp, med antal rum.

Mallen: varje sida är en rumstyp - "Badrum", "WC/D (F1403, F1502)", "WC/RWC 0909, 0911, ..." - under en grupp
("STUDENTBOSTÄDER D 1101/1201/1301, 1102/1202/1302, ..."). Under rumstypen står avsnitten Golv, Väggar, Tak och
Fast inredning / Lös inredning / Inredning / Övrig inredning, och i inredningen en rad per produkt:

    Kommod INR, typ Core Solid XS, b=60 cm, med slät lucka, vit kulör
    0500-N
    "Pure White". Vitt porslin.

Antalet är antalet rum av typen: rumsnumren efter rubriken när de står där, annars gruppens lägenheter (D 1101/1201/
1301 är tre lägenheter). Varje produkt räknas en gång per rum - det beskrivningen inte säger något mer om står så,
och det som ska tas ur en ritning ("se planritning") flaggas.
"""
from __future__ import annotations

import re
from typing import Any

from .reader import _brand_in, find_maker
from .rsk import find as rsk_find

TEMPLATE = re.compile(r"TYPRUMSBESKRIVNING|RUMSBESKRIVNING\s*$|Mallnamn:\s*Rumsbeskrivning", re.M)
HEAD_END = "KULÖR / GLANS"
NCS = re.compile(r"^(?:S\s?)?\d{4}-[A-Z](?:\d{2}[A-Z])?$|^A\d{2}:\d{2}$")
ROOM_NO = re.compile(r"(?<![\d/])([A-Z]?\d{4})(?![\d])")
INREDNING = re.compile(r"^(fast inredning|lös inredning|inredning|övrig inredning|övrigt|beslag|vitvaror)\s*:?$", re.I)
OTHER_SECTION = re.compile(r"^(golv|väggar|tak|socklar och foder|bänkskiva|stänkskydd|köksluckor|fönster|dörrar)\s*:?$",
                           re.I)
SKIP = re.compile(r"^(-|enl\.? a-ritning.*|enligt .*ritning.*|se .*ritning.*)$", re.I)
# rader som fortsätter föregående produkt: en kulör, ett material, en rad som börjar med gemener eller citat
CONTINUES = re.compile(r"^(?:[”\"'(]|[a-zåäö]|(?i:vitt?\s+porslin\b|svart\b|matt\b|blank\b|kulör\b))")


def is_room_description(first_pages_text: str) -> bool:
    return bool(TEMPLATE.search(first_pages_text or "")) and "KOD" not in (first_pages_text or "")[:3000]


def _units(lines: list[str]) -> int:
    """Antalet lägenheter i en grupprubrik: "1101/1201/1301" är tre, "F 1101/1201/1301/1401/1501" fem."""
    return sum(len(re.findall(r"(?<!\d)\d{4}(?!\d)", ln)) for ln in lines)


def _entries(lines: list[str]) -> list[tuple[str, str]]:
    """(avsnitt, produkttext) ur en rumstyps rader."""
    out: list[tuple[str, str]] = []
    section = ""
    cur: list[str] | None = None

    def close():
        nonlocal cur
        if cur:
            text = re.sub(r"\s+", " ", " ".join(cur)).strip(" ,")
            if text and not SKIP.match(text):
                out.append((section, text))
        cur = None

    for raw in lines:
        ln = raw.strip()
        if not ln:
            continue
        if INREDNING.match(ln):
            close()
            section = ln.rstrip(":").strip().capitalize()
            continue
        if OTHER_SECTION.match(ln):
            close()
            section = ""
            continue
        if not section:
            continue
        if NCS.match(ln):
            if cur is not None:
                cur.append(f"Kulör NCS {ln}" if "-" in ln else "")
            continue
        if SKIP.match(ln):
            close()
            continue
        if cur is not None and (CONTINUES.match(ln) or cur[-1].rstrip().endswith((",", "och"))):
            cur.append(ln)
            continue
        close()
        cur = [ln]
    close()
    return out


def _product(text: str, n: int, room: str, group: str, count: int, count_from: str, section: str) -> dict[str, Any]:
    brand, raw, typ = find_maker(text)
    if not brand:
        brand, raw, typ = _brand_in(text)
    m = re.search(r"\btyp\s+([^,]+)", text, re.I)
    if m:
        typ = m.group(1).strip()
        if brand and typ.lower().startswith(brand.lower()):
            typ = typ[len(brand):].strip()
        t_brand, t_raw, t_typ = _brand_in(m.group(1))
        if t_brand and not brand:
            brand, raw, typ = t_brand, t_raw, t_typ
    name = re.split(r",|\s+typ\s+|\s+från\s+", text, maxsplit=1, flags=re.I)[0].strip()
    if raw and name.lower().endswith(" " + raw.lower()):
        name = name[: -len(raw)].strip()
    spec: dict[str, str] = {}
    b = re.search(r"\bb\s*=\s*(\d{2,4})\s*(cm|mm)?", text, re.I)
    if b:
        spec["Bredd"] = f"{b.group(1)} {b.group(2) or 'cm'}"
    col = re.search(r"[”\"]([^”\"]+)[”\"]", text)
    if col:
        spec["Kulör"] = col.group(1)
    ncs = re.search(r"Kulör NCS (\S+)", text)
    if ncs:
        spec["NCS"] = ncs.group(1)
    per_plan = bool(re.search(r"se planritning|enl\.? planritning|enligt planritning", text, re.I))
    return {"id": f"r{n}", "kind": "post", "code": "", "name": name[:1].upper() + name[1:120],
            "quantity": float(count) if count else None, "unit": "st" if count else "",
            "quantity_text": (f"1 per rum × {count} rum" if count else "antal rum okänt"),
            "manufacturer": brand, "manufacturer_text": raw, "type": (typ or "")[:120], "rsk": rsk_find(text),
            "art_nr": [], "or_equal": bool(re.search(r"el\.?\s*likv|eller\s+likvärd", text, re.I)), "spec": spec,
            "text": text, "category": f"{room}" + (f" – {group.title()}" if group else ""), "subcategory": section,
            "ama_code": "", "ama_path": [], "section": group, "page": 0, "parent": "",
            "total_quantity": float(count) if count else None, "supplied_by": "",
            "inferred": (f"Antal = antal rum ({count_from})" + ("; antal enligt planritning - kontrollera" if per_plan else ""))}


def read_room_description(doc) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    group, group_units = "", 0
    for pno, page in enumerate(doc):
        text = page.get_text()
        if HEAD_END not in text:
            continue
        body = [ln.rstrip() for ln in text.split(HEAD_END, 1)[1].splitlines()]
        lines = [ln for ln in body]
        nonblank = [ln.strip() for ln in lines if ln.strip()]
        if not nonblank or nonblank[0].upper() == "REGISTER":
            continue
        i = 0
        first = nonblank[0]
        # en grupp: rubrik i versaler, och lägenhetsnumren på raderna under
        if first.isupper() and len(first) > 6 and not ROOM_NO.search(first):
            group = first.strip()
            j = 1
            unit_lines = []
            while j < len(nonblank) and (ROOM_NO.search(nonblank[j]) or re.match(r"^[A-Z]\s+\d{4}", nonblank[j])):
                unit_lines.append(nonblank[j])
                j += 1
            group_units = _units(unit_lines)
            i = j
        if i >= len(nonblank):
            continue
        room = nonblank[i]
        room_numbers = ROOM_NO.findall(room)
        room = re.sub(r"\s*\(.*\)\s*$", "", room).strip()
        nxt = nonblank[i + 1] if i + 1 < len(nonblank) else ""
        if not room_numbers and re.fullmatch(r"[\d,\s–\-A-Za-z()]+", nxt) and len(ROOM_NO.findall(nxt)) >= 1:
            room_numbers = ROOM_NO.findall(nxt)
        if room_numbers:
            count, count_from = len(room_numbers), "rumsnummer: " + ", ".join(room_numbers[:12]) + (
                " …" if len(room_numbers) > 12 else "")
        else:
            count, count_from = group_units, f"{group.title()}: {group_units} lägenheter" if group_units else ""
        start = lines.index(next(ln for ln in lines if ln.strip() == nonblank[i])) + 1
        for section, entry in _entries(lines[start:]):
            items.append(_product(entry, len(items) + 1, room, group, count, count_from, section))
            items[-1]["page"] = pno + 1
    stats = {"items": len(items), "posts": len(items), "accessories": 0, "mentioned": 0,
             "with_rsk": sum(1 for i in items if i["rsk"]), "categories": len({i["category"] for i in items}),
             "manufacturers": len({i["manufacturer"] for i in items if i["manufacturer"]})}
    return {"meta": {"title": "", "n_pages": len(doc), "template": "rumsbeskrivning"}, "items": items, "stats": stats}
