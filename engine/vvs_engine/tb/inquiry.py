"""En förfrågan som flera handlingar (en zip): rumsbeskrivning, ritningar med förteckning, AMA-beskrivning.

Varje PDF läses med den läsare som passar: en typrumsbeskrivning (rooms), en ritning med en förteckning över
utrustning (legend), eller en AMA-beskrivning (reader). Planer och översikter utan förteckning läses inte till
poster - de står i redovisningen som lästa men utan material.

När förteckningen och rumsbeskrivningen nämner samma sak (samma sort och bredd i samma slags rum) blir det en
position, inte två. Säger de olika saker - Beslagdesign i förteckningen, Smedbo i rumsbeskrivningen - står båda,
och raden flaggas: handlingarna motsäger varandra.
"""
from __future__ import annotations

import io
import re
import zipfile
from typing import Any

import pymupdf

from .equivalent import category_of, dims_of
from .legend import has_legend, legend_items, read_legend
from .rooms import is_room_description, read_room_description


def _pdfs(name: str, data: bytes) -> list[tuple[str, bytes]]:
    if data[:2] == b"PK":
        out = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                n = info.filename
                if n.lower().endswith(".pdf") and not n.startswith("__MACOSX") and info.file_size < 300 * 1024 * 1024:
                    out.append((n.rsplit("/", 1)[-1], z.read(info)))
        return out
    return [(name, data)]


def _key(it: dict[str, Any]) -> tuple[str | None, int | None]:
    cat = category_of(it.get("name") or "", it.get("text") or "")
    w = dims_of(" ".join(f"{k} {v}" for k, v in (it.get("spec") or {}).items()) + " " + (it.get("text") or ""), cat)
    return cat, w.get("bredd")


def _group_counts(room_items: list[dict[str, Any]]) -> dict[str, int]:
    """Lägenheter per grupp ur rumsbeskrivningen: {"STUDENTBOSTÄDER": 30, "TRYGGHETSBOSTÄDER": 29}."""
    out: dict[str, int] = {}
    for it in room_items:
        g = (it.get("section") or "").strip().upper()
        m = re.search(r"(\d+) lägenheter", it.get("inferred") or "")
        if g and m:
            out[g] = max(out.get(g, 0), int(m.group(1)))
    return out


def _fill_from_groups(items: list[dict[str, Any]], legend: dict[str, Any], groups: dict[str, int]) -> None:
    """Positioner i lägenhetstyper: står positionen i alla typer av en grupp räknas gruppens alla lägenheter."""
    types = legend["types"]
    by_group: dict[str, list[str]] = {}
    for letter, t in types.items():
        if t["rooms"] or not t["positions"]:
            continue
        g = next((name for name in groups if name[:5] == re.sub(r"[^A-ZÅÄÖ]", "", t["title"].upper())[:5]), None)
        by_group.setdefault(g or "?", []).append(letter)
    for it in items:
        if it.get("quantity") is not None:
            continue
        present = {s.split(" ")[0] for s in (it["spec"].get("Våtrumstyper") or "").split(", ") if s and s != "–"}
        total, notes, partial = 0, [], []
        for g, letters in by_group.items():
            hit = present & set(letters)
            if not hit:
                continue
            if g == "?":
                partial.append(f"typ {', '.join(sorted(hit))} ({types[sorted(hit)[0]]['title']}) hör inte till någon grupp i rumsbeskrivningen")
            elif hit == set(letters):
                total += groups[g]
                notes.append(f"{g.title()}: {groups[g]} lägenheter (alla typer {', '.join(letters)})")
            else:
                partial.append(f"{g.title()}: står i typ {', '.join(sorted(hit))} men inte i "
                               f"{', '.join(sorted(set(letters) - hit))} - antalet per typ står inte i handlingarna")
        if total:
            it["quantity"] = it["total_quantity"] = float(total)
            it["unit"] = "st"
            it["quantity_text"] = f"{total} st"
        it["inferred"] = "; ".join(["Antal = " + " + ".join(notes)] if notes else []) + (
            ("; " if notes else "") + "Kontrollera: " + "; ".join(partial) if partial else "")
        if partial or not total:
            it["spec"]["Flagga"] = "antal att kontrollera"


def read_inquiry(name: str, data: bytes) -> dict[str, Any]:
    docs, room_items, legends, ama_items = [], [], [], []
    for fname, pdf in _pdfs(name, data):
        try:
            doc = pymupdf.open(stream=pdf, filetype="pdf")
        except Exception:                                   # noqa: BLE001
            docs.append({"name": fname, "kind": "kunde inte läsas", "items": 0})
            continue
        try:
            head = "".join(doc[i].get_text() for i in range(min(3, len(doc))))
            if has_legend(doc):
                lg = read_legend(doc)
                items = legend_items(lg)
                for it in items:
                    it["spec"]["Handling"] = fname
                legends.append((lg, items))
                docs.append({"name": fname, "kind": "förteckning (våtrumsuppställningar)", "pages": len(doc),
                             "items": len(items)})
            elif is_room_description(head):
                r = read_room_description(doc)
                for it in r["items"]:
                    it["spec"]["Handling"] = fname
                room_items += r["items"]
                docs.append({"name": fname, "kind": "rumsbeskrivning", "pages": len(doc), "items": len(r["items"])})
            elif has_legend(doc):
                lg = read_legend(doc)
                items = legend_items(lg)
                for it in items:
                    it["spec"]["Handling"] = fname
                legends.append((lg, items))
                docs.append({"name": fname, "kind": "förteckning (våtrumsuppställningar)", "pages": len(doc),
                             "items": len(items)})
            else:
                from .reader import read_tech_spec
                r = read_tech_spec(doc)
                if r["items"] and r["stats"].get("posts", 0) >= 3:
                    ama_items += r["items"]
                    docs.append({"name": fname, "kind": "AMA-beskrivning", "pages": len(doc), "items": len(r["items"])})
                else:
                    docs.append({"name": fname, "kind": "ritning/plan utan förteckning - inte läst till material",
                                 "pages": len(doc), "items": 0})
        finally:
            doc.close()
    groups = _group_counts(room_items)
    items: list[dict[str, Any]] = []
    for lg, its in legends:
        _fill_from_groups(its, lg, groups)
        items += its
    # rumsbeskrivningens rader som förteckningen redan har blir inte en position till; säger de olika fabrikat
    # står rumsbeskrivningens sak på positionen och raden flaggas
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for it in items:
        by_key.setdefault(_key(it), []).append(it)
    for it in room_items:
        k = _key(it)
        if k[0] and k in by_key:
            targets = [pos for pos in by_key[k] if not (pos.get("inferred") or "").startswith("Antal = antal rum (rum:")]
            if not targets:
                items.append(it)
                continue
            for pos in targets:
                pos.setdefault("_room_counts", []).append((it["quantity"] or 0, it["category"]))
                said = " ".join(x for x in (it["manufacturer"], it["type"]) if x)
                mine = " ".join(x for x in (pos["manufacturer"], pos["type"]) if x)
                pos["spec"].setdefault("Rumsbeskrivningen", "")
                pos["spec"]["Rumsbeskrivningen"] = "; ".join(x for x in (
                    pos["spec"]["Rumsbeskrivningen"], f"{it['category']}: {it['name']} {said} ({it['quantity_text']})") if x)
                if said and mine and said.split()[0].lower() != mine.split()[0].lower():
                    pos["spec"]["Flagga"] = "handlingarna anger olika fabrikat"
            continue
        items.append(it)
    # en position som ritningen inte ger ett antal för får rumsbeskrivningens rum, flaggad
    for it in items:
        rc = it.pop("_room_counts", None)
        if rc and it.get("quantity") is None and sum(q for q, _ in rc):
            total = sum(q for q, _ in rc)
            it["quantity"] = it["total_quantity"] = float(total)
            it["unit"], it["quantity_text"] = "st", f"{total:g} st"
            it["inferred"] = ("Antal ur rumsbeskrivningen: " + " + ".join(f"{c} ({q:g})" for q, c in rc) + "; "
                              + (it.get("inferred") or ""))
            it["spec"]["Flagga"] = it["spec"].get("Flagga") or "antal att kontrollera"
    items += ama_items
    for n, it in enumerate(items, 1):
        it["id"] = f"q{n}"
    stats = {"items": len(items), "posts": len(items), "accessories": 0, "mentioned": 0,
             "with_rsk": sum(1 for i in items if i["rsk"]), "categories": len({i["category"] for i in items}),
             "manufacturers": len({i["manufacturer"] for i in items if i["manufacturer"]}),
             "flagged": sum(1 for i in items if (i.get("spec") or {}).get("Flagga"))}
    return {"meta": {"title": name.rsplit(".", 1)[0], "n_pages": sum(d.get("pages", 0) for d in docs), "documents": docs,
                     "groups": groups}, "items": items, "stats": stats}
