"""Utdata enligt kravunderlaget, utöver IFC-filen (ifc_export) och etiketterna:

- punktlistan (ID, x/y/z, våning, zon, gängstång kapad och beräknad, avstånd till vägg och undertak, artiklar)
- artikellistan per zon, med artikelnummer och pris när en uppslagsfunktion ger dem
- kontrollrapporten som PDF och som BCF 2.1 (ett ärende per regelavvikelse, med GlobalId på rör eller hängare)
- ritunderlaget som DXF: punkterna, pendlarna och ID per våning som lager

Ingen av funktionerna gissar fram en artikel eller ett pris: hittar uppslaget inget står raden kvar utan, och
syns i listan som "artikel saknas"."""
from __future__ import annotations

import csv
import io
import time
import uuid
import zipfile
from collections import defaultdict
from typing import Any, Callable
from xml.sax.saxutils import escape

from .ifc_export import guid

POINT_COLUMNS = ["ID", "Våning", "Zon", "Typ", "X", "Y", "Z underkant bjälklag", "Höjdkälla", "Bjälklagstyp", "Infästning",
                 "Gängstång", "Kaplängd mm", "Beräknad längd mm", "Takjärn mm", "Avstånd vägg mm", "Vägg",
                 "Avstånd undertak mm", "Last kN", "Punktlast kg", "Rör (GlobalId)", "Rör", "Artiklar", "Placerad",
                 "Status", "Kolli", "Flaggor", "IFC GlobalId"]


def _rod(h: dict[str, Any]) -> dict[str, Any]:
    return (h.get("rods") or [{}])[0]


def point_rows(hangers: list[dict[str, Any]], project: str = "") -> list[list[Any]]:
    out = []
    for h in hangers:
        r, p = _rod(h), h.get("position") or {}
        out.append([
            h["id"], h.get("storey"), h.get("zone"), h.get("kind"), p.get("x"), p.get("y"), p.get("z"),
            h.get("height_source"), (h.get("slab") or {}).get("type"), h.get("anchor"),
            r.get("size"), r.get("length_mm"), r.get("calc_mm"), (h.get("takjarn") or {}).get("length_mm"),
            (h.get("wall") or {}).get("mm"), (h.get("wall") or {}).get("name") or (h.get("wall") or {}).get("id"),
            (h.get("ceiling_clearance") or {}).get("mm"), h.get("load_kn"), h.get("point_load_kg"),
            ", ".join(str(pp.get("id")) for pp in h.get("pipes") or []),
            ", ".join(f"{pp.get('material')} {pp.get('dn') or pp.get('od')}" for pp in h.get("pipes") or []),
            "; ".join(f"{b['qty']} x {b['text']}" + (f" {b['length_mm']} mm" if b.get("length_mm") else "") for b in h.get("bom") or []),
            h.get("placed_because"), h.get("status"), (h.get("pack") or {}).get("kolli"), "; ".join(h.get("flags") or []),
            guid(f"{project}:{h['id']}"),
        ])
    return out


def point_csv(hangers: list[dict[str, Any]], project: str = "") -> str:
    """Punktlistan som CSV med semikolon (svensk Excel öppnar den direkt)."""
    b = io.StringIO()
    w = csv.writer(b, delimiter=";")
    w.writerow(POINT_COLUMNS)
    w.writerows(point_rows(hangers, project))
    return "﻿" + b.getvalue()


Lookup = Callable[[dict[str, Any]], "dict[str, Any] | None"]


def article_list(hangers: list[dict[str, Any]], lookup: Lookup | None = None) -> list[dict[str, Any]]:
    """Materialet per zon: varje del med längd och antal, och - när uppslaget hittar den - artikelnummer,
    benämning och pris (netto före brutto). Gängstång och takjärn räknas i meter; resten i styck."""
    acc: dict[tuple, dict[str, Any]] = {}
    for h in hangers:
        zone = h.get("zone") or "-"
        for b in h.get("bom") or []:
            k = (h.get("storey") or "", zone, b["part"], b["text"], b.get("length_mm"))
            a = acc.setdefault(k, {"storey": k[0], "zone": zone, "part": b["part"], "text": b["text"],
                                   "length_mm": b.get("length_mm"), "qty": 0, "hangers": 0})
            a["qty"] += b["qty"]
            a["hangers"] += 1
    rows = sorted(acc.values(), key=lambda a: (a["storey"], a["zone"], a["part"], a["text"], a["length_mm"] or 0))
    cache: dict[tuple, Any] = {}
    for a in rows:
        metres = a["part"] in ("gängstång", "takjärn") and a["length_mm"]
        a["unit"] = "m" if metres else "st"
        a["amount"] = round(a["qty"] * a["length_mm"] / 1000, 2) if metres else a["qty"]
        key = (a["part"], a["text"])
        if key not in cache:
            cache[key] = lookup({"part": a["part"], "text": a["text"]}) if lookup else None
        art = cache[key]
        if art:
            price = art.get("netto") if art.get("netto") is not None else art.get("brutto")
            a.update(article=art.get("a"), article_name=art.get("n"), article_unit=art.get("e"), price=price,
                     price_kind="netto" if art.get("netto") is not None else ("brutto" if price is not None else None),
                     article_source=art.get("source") or "Dahls katalog")
            # artikeln säljs per styck i lagerlängd: priset gäller per längd, inte per meter
            if price is not None:
                per = a["amount"] if (a["unit"] == (art.get("e") or "st")) else a["qty"]
                a["sum"] = round(per * float(price), 2)
        else:
            a.update(article=None, article_name=None, price=None, sum=None, article_source="artikel saknas")
    return rows


def article_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_zone: dict[str, float] = defaultdict(float)
    missing = 0
    for r in rows:
        if r.get("sum") is not None:
            by_zone[f"{r['storey']} {r['zone']}".strip()] += r["sum"]
        else:
            missing += 1
    return {"by_zone": {k: round(v, 2) for k, v in by_zone.items()}, "total": round(sum(by_zone.values()), 2),
            "rows_without_price": missing}


# ---------------------------------------------------------------- kontrollrapport

def issues(validation: list[dict[str, Any]], findings: list[dict[str, Any]], hangers: list[dict[str, Any]],
           project: str = "") -> list[dict[str, Any]]:
    """Ett ärende per regelavvikelse: valideringens (per fil eller per rör) och beräkningens (per hängare)."""
    out = []
    for f in list(validation or []) + list(findings or []):
        out.append({"rule": f["rule"], "level": f["level"], "title": f["title"], "text": f.get("text") or "",
                    "guids": list(f.get("guids") or []), "file": f.get("file") or "", "at": f.get("at")})
    for h in hangers:
        for fl in h.get("flags") or []:
            rule = fl.split(":")[0] if fl[:1] == "V" and ":" in fl[:5] else "Hängare"
            out.append({"rule": rule, "level": "varning", "title": f"{h['id']}: {fl[:90]}", "text": fl,
                        "guids": [guid(f"{project}:{h['id']}")] + [str(p["id"]) for p in h.get("pipes") or []],
                        "file": "", "at": [h["position"]["x"], h["position"]["y"], h["position"].get("z") or 0],
                        "hanger": h["id"]})
    order = {"stopp": 0, "varning": 1, "info": 2}
    out.sort(key=lambda i: (order.get(i["level"], 3), i["rule"]))
    return out


def report_pdf(project: str, revision: str, validation: list[dict[str, Any]], findings: list[dict[str, Any]],
               hangers: list[dict[str, Any]], summary: dict[str, Any] | None = None, files: list[dict[str, Any]] | None = None) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    W, H, M = 595, 842, 40
    state = {"page": None, "y": 0.0}

    def new():
        state["page"] = doc.new_page(width=W, height=H)
        state["y"] = M

    def line(text: str, size: float = 9, bold: bool = False, indent: float = 0, color=(0, 0, 0)):
        width = int((W - 2 * M - indent) / (size * 0.5))
        parts = [text[i:i + width] for i in range(0, max(len(text), 1), width)] or [""]
        for part in parts:
            if state["page"] is None or state["y"] > H - M:
                new()
            state["page"].insert_text((M + indent, state["y"] + size), part, fontsize=size,
                                      fontname="hebo" if bold else "helv", color=color)
            state["y"] += size * 1.45

    new()
    line(f"Kontrollrapport SmartHangers - {project}", 16, True)
    line(f"Revision {revision} · {time.strftime('%Y-%m-%d %H:%M')}", 9)
    state["y"] += 6
    iss = issues(validation, findings, hangers, project)
    n = defaultdict(int)
    for i in iss:
        n[i["level"]] += 1
    line(f"Stopp: {n['stopp']}   Varning: {n['varning']}   Info: {n['info']}", 11, True,
         color=(0.7, 0, 0) if n["stopp"] else (0, 0, 0))
    if summary:
        line(f"Hängare: {summary.get('hangers', len(hangers))} · per typ: " +
             ", ".join(f"{k} {v}" for k, v in (summary.get("by_kind") or {}).items()), 9)
    for f in files or []:
        line(f"{f.get('discipline') or '?'}: {f.get('file_name') or ''} · {f.get('timestamp') or ''} · "
             f"{f.get('application') or ''} · rev {f.get('revision') or '-'}", 8)
    state["y"] += 8
    colors = {"stopp": (0.7, 0, 0), "varning": (0.6, 0.4, 0), "info": (0.2, 0.2, 0.5)}
    shown = 0
    for i in iss:
        if shown >= 1500:
            line(f"... och {len(iss) - shown} ärenden till (alla finns i BCF-filen)", 9, True)
            break
        line(f"[{i['level'].upper()}] {i['rule']} {i['title']}", 9, True, color=colors.get(i["level"], (0, 0, 0)))
        if i["text"] and i["text"] != i["title"]:
            line(i["text"], 8, indent=10)
        if i["guids"]:
            g = i["guids"]
            line("GlobalId: " + ", ".join(g[:8]) + (f" (+{len(g) - 8})" if len(g) > 8 else ""), 7, indent=10, color=(0.3, 0.3, 0.3))
        shown += 1
    return doc.tobytes()


def bcf_zip(project: str, revision: str, validation: list[dict[str, Any]], findings: list[dict[str, Any]],
            hangers: list[dict[str, Any]], limit: int = 2000) -> bytes:
    """BCF 2.1: ett ärende (topic) per avvikelse, med de berörda objektens GlobalId som komponenter i vypunkten
    så att samordnaren hittar dem i Solibri, BIMcollab, Navisworks eller Revit."""
    b = io.BytesIO()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bcf.version", '<?xml version="1.0" encoding="UTF-8"?>\n'
                                  '<Version VersionId="2.1"><DetailedVersion>2.1</DetailedVersion></Version>')
        z.writestr("project.bcfp", '<?xml version="1.0" encoding="UTF-8"?>\n<ProjectExtension><Project ProjectId="'
                   + str(uuid.uuid5(uuid.NAMESPACE_URL, "smarthangers:" + project)) + f'"><Name>{escape(project)}</Name></Project>'
                   "<ExtensionSchema></ExtensionSchema></ProjectExtension>")
        for k, i in enumerate(issues(validation, findings, hangers, project)[:limit]):
            tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"smarthangers:{project}:{revision}:{k}:{i['title']}"))
            vid = str(uuid.uuid5(uuid.NAMESPACE_URL, "vp:" + tid))
            status = "Open"
            z.writestr(f"{tid}/markup.bcf", f"""<?xml version="1.0" encoding="UTF-8"?>
<Markup>
  <Topic Guid="{tid}" TopicType="{'Error' if i['level'] == 'stopp' else ('Warning' if i['level'] == 'varning' else 'Info')}" TopicStatus="{status}">
    <Title>{escape(i['rule'] + ' ' + i['title'])[:250]}</Title>
    <Priority>{escape(i['level'])}</Priority>
    <Labels>{escape(i['rule'])}</Labels>
    <CreationDate>{stamp}</CreationDate>
    <CreationAuthor>Dahl SmartHangers</CreationAuthor>
    <Description>{escape(i['text'] + (' (' + i['file'] + ')' if i['file'] else ''))}</Description>
  </Topic>
  <Viewpoints Guid="{vid}"><Viewpoint>viewpoint.bcfv</Viewpoint></Viewpoints>
</Markup>""")
            comps = "".join(f'<Component IfcGuid="{escape(g)}"/>' for g in i["guids"][:200] if len(str(g)) == 22)
            cam = ""
            if i.get("at"):
                x, y, zz = (float(v) / 1000 for v in i["at"])
                cam = (f"<PerspectiveCamera><CameraViewPoint><X>{x - 4}</X><Y>{y - 4}</Y><Z>{zz + 3}</Z></CameraViewPoint>"
                       "<CameraDirection><X>0.58</X><Y>0.58</Y><Z>-0.58</Z></CameraDirection>"
                       "<CameraUpVector><X>0</X><Y>0</Y><Z>1</Z></CameraUpVector><FieldOfView>60</FieldOfView></PerspectiveCamera>")
            z.writestr(f"{tid}/viewpoint.bcfv", f"""<?xml version="1.0" encoding="UTF-8"?>
<VisualizationInfo Guid="{vid}"><Components><Selection>{comps}</Selection>
<Visibility DefaultVisibility="true"/></Components>{cam}</VisualizationInfo>""")
    return b.getvalue()


# ---------------------------------------------------------------- ritunderlag

def dxf(hangers: list[dict[str, Any]], pipes: list[dict[str, Any]] | None = None) -> str:
    """Ritunderlaget i DXF (R12, mm): ett lager per våning för punkterna (cirkel + ID + pendellängd) och ett för
    rören, så att det kan läggas som referens i AutoCAD/MagiCAD och mätas ut."""
    L = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]

    def lay(name: str) -> str:
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(name or "0"))[:60] or "0"

    def ent(*pairs):
        for c, v in pairs:
            L.extend([str(c), str(v)])

    for p in pipes or []:
        s, e = p.get("start"), p.get("end")
        if not s or not e:
            continue
        ent((0, "LINE"), (8, "ROR_" + lay(p.get("storey"))), (62, 8), (10, round(s[0], 1)), (20, round(s[1], 1)),
            (30, round(s[2] if len(s) > 2 else 0, 1)), (11, round(e[0], 1)), (21, round(e[1], 1)), (31, round(e[2] if len(e) > 2 else 0, 1)))
    for h in hangers:
        p = h["position"]
        layer = "HANGARE_" + lay(h.get("storey"))
        col = 1 if h.get("flags") else 3
        ent((0, "CIRCLE"), (8, layer), (62, col), (10, p["x"]), (20, p["y"]), (30, p.get("z") or 0), (40, 60))
        tj = h.get("takjarn")
        if tj and tj.get("length_mm"):
            # takjärnet tvärs stråket: riktningen ur referensen (stråkets början mot punkten)
            ent((0, "TEXT"), (8, layer), (62, col), (10, p["x"] + 80), (20, p["y"] - 160), (30, 0), (40, 70),
                (1, f"takjarn {tj['length_mm']}"))
        r = _rod(h)
        ent((0, "TEXT"), (8, layer), (62, col), (10, p["x"] + 80), (20, p["y"] + 40), (30, 0), (40, 100), (1, h["id"]))
        if r.get("length_mm"):
            ent((0, "TEXT"), (8, layer), (62, col), (10, p["x"] + 80), (20, p["y"] - 60), (30, 0), (40, 70),
                (1, f"{r.get('size')} L={r['length_mm']}"))
    L.extend(["0", "ENDSEC", "0", "EOF"])
    return "\n".join(L) + "\n"
