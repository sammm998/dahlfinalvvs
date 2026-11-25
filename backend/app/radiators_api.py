"""Radiatorerna på en ritning: mängdning per hus och korsning mot Altech, med Dahls priser.

  GET /api/drawings/{id}/radiators?temps=55/45/20&prefer=length|height
                                                      läsningen, sammanställningen och korsningen; prefer avgör
                                                      vad som väger tyngst vid en lucka i Altechs sortiment
  GET /api/drawings/{id}/radiators.xlsx               samma som Excel: sammanställning per hus, detaljlista,
                                                      Altech-korsning med skillnader och alternativ, källor

Läsningen går direkt på ritningens text (vvs_engine.radiators) och behöver ingen mängdningsanalys; den sparas per
ritning och temperatur så att den bara görs en gång. Priserna kommer ur Dahls uppladdade prisfil: Altech på sitt
RSK-nummer, den föreskrivna modellen på sin benämning (TP22-316, TPv4 22-218 ...). Saknas priset står det så."""
from __future__ import annotations

import io
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from vvs_engine import radiators as RAD

from .auth import current_user
from .db import Drawing, User, get_db
from .storage import storage

router = APIRouter(tags=["radiatorer"])
VERSION = 2


def _drawing(db: Session, user: User, did: str) -> Drawing:
    d = db.get(Drawing, did)
    if d is None or d.project.owner_id != user.id:
        raise HTTPException(404, "Ritningen finns inte")
    return d


def _temps(raw: str) -> tuple[float, float, float]:
    try:
        t = tuple(float(x.replace(",", ".")) for x in (raw or "55/45/20").split("/"))
        if len(t) != 3:
            raise ValueError
        RAD.lmtd(*t)
        return t                                                # type: ignore[return-value]
    except (ValueError, ZeroDivisionError):
        raise HTTPException(422, "Temperaturerna skrivs fram/retur/rum, t.ex. 55/45/20")


def _price_index() -> tuple[dict[str, dict], list[dict], dict[str, float]]:
    from . import offers as O
    rows = [r for r in O.data("prislista") if r.get("rsk")]
    return {str(r["rsk"]): r for r in rows}, rows, O.base_discounts()


def _price(row: dict | None, disc: dict[str, float]) -> dict[str, Any] | None:
    if not row or row.get("pris") is None:
        return None
    br = float(row["pris"])
    pct = disc.get(str(row.get("grupp") or ""))
    return {"rsk": row["rsk"], "name": str(row.get("namn") or "").strip(), "brutto": br,
            "netto": round(br * (1 - float(pct) / 100), 2) if pct is not None else None, "rabatt_pct": pct}


def _prescribed_row(x: dict[str, Any], rows: list[dict]) -> dict | None:
    """Den föreskrivna radiatorn i prisfilen på sin benämning: TPv4 22-218 står som "TP22-218 ... V4"."""
    code = f"{x['h'] // 100}{x['l'] // 100:02d}"
    if x.get("family") in ("TPV4", "TPV", "TP"):
        pat = re.compile(rf"\bTP\s?{x['type']}[-\s]{code}\b.*\bV4\b|\bTP V4\b.*\bTP{x['type']}\s{code}\b", re.I)
    elif x.get("family") in ("CV", "PCV", "FCV"):
        pat = re.compile(rf"\b{x['family']}\s?{x['type']}[-\s]{x['h'] // 100}{x['l'] // 100:02d}\b", re.I)
    else:
        pat = re.compile(rf"\b(?:PC|C){x['type']}[-\s]{x['h'] // 100}{x['l'] // 100:02d}\b", re.I)
    hits = [r for r in rows if pat.search(str(r.get("namn") or "")) and "-" not in str(r["rsk"])]
    return min(hits, key=lambda r: float(r.get("pris") or 9e9)) if hits else None


def _prefer(raw: str) -> str:
    if raw not in RAD.PREFER:
        raise HTTPException(422, "prefer är length (samma längd, högre radiator) eller height (samma höjd, längre radiator)")
    return raw


def compute(d: Drawing, temps: tuple[float, float, float], prefer: str = "length") -> dict[str, Any]:
    key = f"radiators/{d.id}/{d.sha256[:16]}-{'-'.join(f'{t:g}' for t in temps)}-{prefer}-v{VERSION}.json"
    if storage.exists(key):
        with storage.open(key) as fh:
            res = json.load(fh)
    else:
        res = RAD.read_pdf(storage.path(d.storage_key))
        res["cross"] = RAD.cross_all(res, temps, prefer)
        res["temps"] = "/".join(f"{t:g}" for t in temps)
        res["prefer"] = prefer
        storage.put(key, io.BytesIO(json.dumps(res, ensure_ascii=False).encode("utf-8")))
    # priserna läggs på vid varje fråga: prisfilen kan ha bytts sedan läsningen
    by_rsk, rows, disc = _price_index()
    fam_of = {r["designation"]: r["family"] for r in res["radiators"]}
    tot_pres = tot_alt = same_alt = 0.0
    missing = n_pres = 0
    for x in res["cross"]:
        x["family_written"] = fam_of.get(x["designation"])
        pres = _price(_prescribed_row({**x, "family": x["family_written"]}, rows), disc) if rows else None
        x["prescribed_price"] = pres
        a = x.get("altech") or {}
        a["price"] = next((p for p in (_price(by_rsk.get(str(r)), disc) for r in a.get("rsk") or []) if p), None)
        for al in x.get("alternatives") or []:
            al["price"] = next((p for p in (_price(by_rsk.get(str(r)), disc) for r in al.get("rsk") or []) if p), None)
        unit = lambda p: (p["netto"] if p["netto"] is not None else p["brutto"]) if p else None
        if unit(a.get("price")) is not None:
            tot_alt += unit(a["price"]) * x["count"]
        else:
            missing += 1
        if unit(pres) is not None:
            tot_pres += unit(pres) * x["count"]
            n_pres += 1
            if unit(a.get("price")) is not None:
                same_alt += unit(a["price"]) * x["count"]
    # det föreskrivna har pris bara där prisfilen har modellen: jämförelsen görs på just de beteckningarna
    res["totals"] = {"altech": round(tot_alt, 2), "prescribed": round(tot_pres, 2), "altech_rows_without_price": missing,
                     "prescribed_designations_with_price": n_pres, "designations": len(res["cross"]),
                     "altech_same_designations": round(same_alt, 2), "price_list": bool(rows)}
    res["source"] = RAD.altech()["source"]
    return res


@router.get("/api/drawings/{drawing_id}/radiators")
def radiators(drawing_id: str, temps: str = "55/45/20", prefer: str = "length", user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    return compute(_drawing(db, user, drawing_id), _temps(temps), _prefer(prefer))


def to_xlsx(d: Drawing, res: dict[str, Any]) -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    bold = Font(bold=True)
    head = PatternFill("solid", fgColor="DDE7F3")

    def header(ws, cols):
        ws.append(cols)
        for c in ws[ws.max_row]:
            c.font, c.fill = bold, head

    s = res["summary"]
    ws = wb.active
    ws.title = "Sammanställning"
    ws.append([f"Radiatormängdning – {d.filename}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"Underlag: {d.filename}. Effekt och korsning vid {res['temps']} °C."])
    header(ws, ["Beteckning", "Tillverkare", "Typ", "Höjd×Längd (mm)", *s["zones"], "Totalt", "Proj. effekt totalt (W)"])
    for r in s["rows"]:
        ws.append([r["designation"], f"{r['maker']} {r['series']}".strip(), r["type"], f"{r['h']}×{r['l']}",
                   *[r["per_zone"].get(z, 0) for z in s["zones"]], r["total"], r["w_total"]])
    ws.append(["Summa", "", "", "", *[s["per_zone"].get(z, 0) for z in s["zones"]], s["total"], s["w_total"]])
    for c in ws[ws.max_row]:
        c.font = bold
    zinfo = next((sh.get("zones") for sh in res["sheets"] if sh.get("zones")), {}) or {}
    ws.append([])
    ws.append([f"Husindelning: {zinfo.get('method', '-')}"])
    if any(r["without_effect"] for r in s["rows"]):
        ws.append(["Radiatorer utan läst effekt: " + ", ".join(f"{r['designation']} ({r['without_effect']})"
                                                             for r in s["rows"] if r["without_effect"])])

    w2 = wb.create_sheet("Detaljlista")
    header(w2, ["Nr", "Sida", "Hus", "Lägenhet", "Närmaste rum", "Beteckning", "Höjd (mm)", "Längd (mm)", "Antal",
                "Proj. effekt (W)", "Flöde (l/h)", "Kv"])
    for r in res["radiators"]:
        w2.append([r["nr"], r["page"] + 1, r["zone"], r["apartment"], r["room"], r["designation"], r["h"], r["l"], r["count"],
                   r["w"], r["flow_lh"], r["kv"]])

    w3 = wb.create_sheet("Altech-korsning")
    header(w3, ["Föreskriven", "Antal", "Proj. effekt min–max (W)", "Föreskriven katalogeffekt (W)", "Korsning",
                "Altech", "RSK", "Altech effekt (W)", "Effekt mot projekterad (W)", "(%)", "Effekt mot föreskriven (W)",
                "Δ längd (mm)", "Δ höjd (mm)", "Att kontrollera", "Pris föreskriven (st)", "Pris Altech (st)",
                "Summa Altech", "Radiatorer där Altech ger för lite"])
    for x in res["cross"]:
        a = x.get("altech") or {}
        pp, ap = x.get("prescribed_price"), a.get("price")
        unit = lambda p: (p["netto"] if p.get("netto") is not None else p["brutto"]) if p else None
        w3.append([x["designation"], x["count"], f"{x.get('w_min') or '-'}–{x.get('w_max') or '-'}", x.get("prescribed_w"),
                   x["status"], a.get("name"), ", ".join(a.get("rsk") or []), a.get("w"), a.get("dw_need"), a.get("dw_need_pct"),
                   a.get("dw_prescribed"), a.get("dl_mm"), a.get("dh_mm"), "; ".join(a.get("notes") or []),
                   unit(pp), unit(ap), round(unit(ap) * x["count"], 2) if unit(ap) is not None else None,
                   ", ".join(str(n) for n in x.get("radiators_under") or [])])
    w3.append([])
    t = res.get("totals") or {}
    w3.append(["Summa Altech, alla", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", t.get("altech")])
    if t.get("prescribed_designations_with_price"):
        w3.append([f"Jämförbart: de {t['prescribed_designations_with_price']} av {t.get('designations')} beteckningar där "
                   "prisfilen har den föreskrivna modellen", "", "", "", "", "", "", "", "", "", "", "", "", "",
                   t.get("prescribed"), "", t.get("altech_same_designations")])
    for c in w3[w3.max_row]:
        c.font = bold
    if not t.get("price_list"):
        w3.append(["Ingen prisfil uppladdad: priser saknas (Administration → Offertdata → Prislista)."])

    w4 = wb.create_sheet("Alternativ")
    header(w4, ["Föreskriven", "Varför", "Altech", "RSK", "Effekt (W)", "Mot projekterad (W)", "Δ längd", "Δ höjd",
                "Att kontrollera", "Pris (st)"])
    for x in res["cross"]:
        for al in x.get("alternatives") or []:
            p = al.get("price")
            w4.append([x["designation"], al.get("why"), al["name"], ", ".join(al["rsk"]), al["w"], al.get("dw_need"),
                       al["dl_mm"], al["dh_mm"], "; ".join(al["notes"]),
                       (p["netto"] if p and p.get("netto") is not None else (p or {}).get("brutto"))])

    w5 = wb.create_sheet("Regler och källor")
    for line in [
        "Korsningsregler (i ordning):",
        "1. Exakt: Altech har samma utförande (ventil/kompakt), typ, höjd och längd och den ger minst den projekterade effekten.",
        "2. Lucka: bland Altechs modeller som ger minst den projekterade effekten väljs samma typ före kraftigare typ, "
        "sedan enligt inställningen samma längd före samma höjd (radiatorn blir högre) eller samma höjd före samma "
        "längd (radiatorn blir längre), kortare före längre, minsta överskott sist.",
        f"Vald inställning: {RAD.PREFER.get(res.get('prefer') or 'length')}.",
        "3. Räcker ingen: den med högst effekt, flaggad.",
        "Ventilradiator (TPv4, CV, FCV, TP) korsas mot Altech typ D (integrerad ventil); kompakt (C, PC) mot Altech typ K.",
        "Vid föreskriven höjd 200 mm eller lägre visas Altechs låga konvektor som alternativ.",
        "Effekt vid andra temperaturer: Φ = Φ(55/45/20) · (ΔTln/ΔTln,ref)^n med radiatorns n ur Altechs katalog.",
        "",
        f"Altech: {res.get('source')}",
        f"Föreskriven modells katalogeffekt (Purmo Thermopanel V4): {RAD.purmo_reference()['source']}",
        "Priser: Dahls uppladdade prisfil, netto efter grundrabatt per kalkylgrupp där sådan finns.",
    ]:
        w5.append([line])
    for wsx in wb.worksheets:
        for col in wsx.columns:
            letter = col[0].column_letter
            wsx.column_dimensions[letter].width = min(60, max(10, *(len(str(c.value or "")) * 0.9 for c in col[:200])))
        for row in wsx.iter_rows():
            for c in row:
                c.alignment = Alignment(vertical="top", wrap_text=wsx.title in ("Altech-korsning", "Alternativ", "Regler och källor"))
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


@router.get("/api/drawings/{drawing_id}/radiators.xlsx")
def radiators_xlsx(drawing_id: str, temps: str = "55/45/20", prefer: str = "length", user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    d = _drawing(db, user, drawing_id)
    res = compute(d, _temps(temps), _prefer(prefer))
    base = re.sub(r"\.pdf$", "", d.filename or "ritning", flags=re.I)
    return Response(to_xlsx(d, res), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{base}-radiatorer.xlsx"'})
