"""Från matchade poster till offertrader: artikel, antal, pris för kunden, inköp och marginal, och montörstid.

Två slags offert:

  materialoffert  allt material i underlaget (beskrivning, ritning, materiallista, BOM, IFC), prissatt för kunden
  kalkyloffert    materialet och montörstimmarna: helheten för en entreprenad

Artikeln för en rad väljs i den här ordningen, och raden säger vilken väg den gick:

  1. det förskrivna: RSK eller artikelnummer som finns i registret, eller förskrivet fabrikat som hittades
  2. AI-valet bland kandidaterna (märkt AI)
  3. RSK-förslaget när det är entydigt
  4. för rör: korsreferenslistan - fabrikatet finns inte, men material och dimension gör det (vår likvärdiga)
  5. det egna varumärkets likvärdiga, när offerten ska ta det (och det inte avviker)
  6. annars ingen artikel: raden flaggas för manuell hantering. Systemet gissar aldrig tyst.

Rör med mängd från ritning delas per dimension, och storleken väljs ur seriens storlekar efter ritningen. Går
storleken inte att avgöra flaggas raden.

Priset: bruttopris ur registret, minus kundens rabatt för artikelns rabattgrupp ur kundens rabattmatris - eller
kundens nettopris för artikeln när det finns. Inköpspris och marginal räknas per rad och totalt, men hör till det
interna underlaget och skrivs aldrig ut på kundens offert.
"""
from __future__ import annotations

import re
from typing import Any

from . import normtid as NT
from .tb.rsk import normalize as rsk_norm

# montörstid per styck ur normtidsboken (Sanitära enheter, s. 33), efter vad raden är
SANITARY_HOURS: tuple[tuple[str, str], ...] = (
    (r"badkar", "Badkar inkl. väggblandare och duschstång"),
    (r"utslagsback|tvättbänk", "Utslagsback och tvättbänk inkl. blandare"),
    (r"tvättställ|kommod|underskåp", "Tvättställspaket"),
    (r"inbyggnadscistern|fixtur.*skål", "Inbyggnadscistern komplett med fixtur, tryckknapp och skål"),
    (r"duschblandare|duschset|bidé", "Duschblandare med duschstång; bidé inkl. blandare och dusch"),
    (r"diskbänk|disko|brandkran", "Ink. blandare/vattenlås till diskbänk; brandkran inkl. slang och skåp"),
    (r"\bwc\b|klosett|toalettstol|handdukstork|handukstork|nöddusch", "Vattenklosett; handdukstork; nödduschar"),
    (r"vattenutkastare", "Väggvattenutkastare"),
    (r"tvättställsblandare|blandare.*tvättställ|bottenventil", "Montering av blandare och bottenventil på tvättställ"),
    (r"tappkran|slanghylla|hållare|krok|fixtur|papper|spegel(?!skåp)|duschdraperi|tvåldispenser|dispenser",
     "Tappkran; slanghylla; fixturer"),
)


def hours_per_unit(item: dict[str, Any]) -> tuple[float | None, str]:
    """Normtid per styck för en post, och var den kom ifrån - eller ingen tid och varför."""
    name = " ".join(str(item.get(k) or "") for k in ("name", "subcategory", "category")).lower()
    if (item.get("unit") or "") == "m" or re.search(r"\brör\b|ledning", name):
        return None, "rör: timmar ur kalkylen per meter och dimension"
    table = NT.BY_ID["sanitet"]
    for pattern, row_text in SANITARY_HOURS:
        if re.search(pattern, name):
            for t, text in table.rows:
                if text == row_text:
                    return float(t), f"Normtid VVS, {table.source}: {text}"
    return None, "ingen normtid i boken för den här sortens post - ange tid"


# ---------------------------------------------------------------- artikel

def _ref(hit: dict[str, Any] | None) -> str:
    return (hit or {}).get("ref") or ""


def pick_article(item: dict[str, Any], use_house_brand: bool = False) -> dict[str, Any]:
    """Vilken artikel raden får, och varför. {"rsk", "name", "route", "flag"}."""
    m = item.get("match") or {}
    hits = m.get("hits") or []
    basis = m.get("basis") or ""
    if m.get("status") == "hittad" and hits:
        return {"rsk": _ref(hits[0]), "name": hits[0].get("name", ""), "route": "förskrivet", "flag": ""}
    rsk = m.get("rsk") or {}
    if rsk.get("kind") == "ai" and rsk.get("value"):
        return {"rsk": rsk["value"], "name": rsk.get("name", ""), "route": "AI-val",
                "flag": "" if rsk.get("sure") else "AI-val att kontrollera"}
    if m.get("status") == "möjlig" and basis.startswith("förskrivet") and rsk.get("value"):
        return {"rsk": rsk["value"], "name": rsk.get("name", ""), "route": "förskrivet fabrikat", "flag": ""}
    if rsk.get("kind") == "storlek":
        return {"rsk": "", "name": rsk.get("name", ""), "route": "", "flag": "storlek inom serien går inte att avgöra",
                "variants": rsk.get("variants") or []}
    xr = m.get("crossref")
    if xr and xr.get("rsk"):
        return {"rsk": xr["rsk"], "name": xr.get("name", ""), "route": "korsreferens (vår likvärdiga)", "flag": ""}
    eq = (m.get("equivalent") or {}).get("candidates") or []
    if use_house_brand and eq and eq[0].get("state") != "avviker":
        return {"rsk": eq[0].get("rsk") or "", "name": eq[0].get("name", ""), "route": "eget varumärke (likvärdigt)",
                "flag": "" if eq[0].get("state") == "uppfyller angivna krav" else "likvärdighet att verifiera",
                "price": eq[0].get("price")}
    return {"rsk": "", "name": "", "route": "", "flag": "ingen artikel - manuell hantering"}


def pipe_rows(item: dict[str, Any], crossref: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Ett rör med mängd från ritning blir en rad per dimension; storleken väljs ur seriens storlekar."""
    fd = item.get("from_drawing") or {}
    by_dn = {int(k): float(v) for k, v in (fd.get("by_dn") or {}).items() if float(v or 0) > 0}
    if fd.get("kind") != "meter" or len(by_dn) < 1:
        return [item]
    variants = ((item.get("match") or {}).get("rsk") or {}).get("variants") or []
    out = []
    for dn, metres in sorted(by_dn.items()):
        v = next((x for x in variants if str(x.get("size") or "") == str(dn)), None)
        row = {**item, "id": f"{item.get('id')}-dn{dn}", "name": f"{item.get('name')} DN{dn}",
               "total_quantity": round(metres, 2), "unit": "m", "_dn": dn}
        m = item.get("match") or {}
        if v:
            row["_article"] = {"rsk": v["rsk"], "name": v.get("name", ""), "route": f"storlek ur ritningen (DN{dn})",
                               "flag": ""}
        elif m.get("status") != "hittad" and crossref:
            from .tb.crossref import for_item
            xr = for_item(item, crossref, str(dn))
            row["_article"] = ({"rsk": xr["rsk"], "name": xr["name"], "route": f"korsreferens DN{dn} (vår likvärdiga)",
                                "flag": "pris saknas enligt korsreferensen" if xr["price_missing"] else ""} if xr else
                               {"rsk": "", "name": "", "route": "", "flag": f"DN{dn}: varken fabrikat eller material och "
                                                                            "dimension i katalogen - manuell hantering"})
        else:
            row["_article"] = {"rsk": "", "name": "", "route": "",
                               "flag": f"DN{dn}: storleken finns inte bland seriens storlekar - manuell hantering"}
        out.append(row)
    return out


# ---------------------------------------------------------------- pris

def customer_price(rsk: str, book: dict[str, dict[str, Any]], customer: dict[str, Any] | None,
                   fallback_price: float | None = None) -> dict[str, Any]:
    """Brutto, kundens rabatt och netto för en artikel. customer = {"rabatter": {grupp: pct}, "netto": {rsk: kr}}."""
    r = book.get(rsk_norm(rsk) or rsk) or {}
    brutto = r.get("p") if r.get("p") is not None else fallback_price
    group = str(r.get("k") or "")
    cust = customer or {}
    if rsk and (cust.get("netto") or {}).get(rsk) is not None:
        net = float(cust["netto"][rsk])
        return {"brutto": brutto, "rabattgrupp": group, "rabatt_pct": None, "netto": net, "pris_enligt": "kundens nettopris"}
    pct = (cust.get("rabatter") or {}).get(group)
    if brutto is None:
        return {"brutto": None, "rabattgrupp": group, "rabatt_pct": pct, "netto": None, "pris_enligt": "pris saknas"}
    if pct is None:
        return {"brutto": brutto, "rabattgrupp": group, "rabatt_pct": 0.0, "netto": round(float(brutto), 2),
                "pris_enligt": "bruttopris (gruppen finns inte i kundens rabattmatris)" if customer else "bruttopris"}
    return {"brutto": brutto, "rabattgrupp": group, "rabatt_pct": float(pct),
            "netto": round(float(brutto) * (1 - float(pct) / 100.0), 2), "pris_enligt": f"rabattgrupp {group}"}


def build_rows(items: list[dict[str, Any]], book: dict[str, dict[str, Any]], customer: dict[str, Any] | None,
               purchase: dict[str, float], kind: str = "materialoffert", hourly_rate: float = 0.0,
               use_house_brand: bool = False, crossref: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for it in items:
        if it.get("kind") in ("krav", "arbete") or (it.get("supplied_by") and not str(it["supplied_by"]).startswith("Ingår")):
            continue
        for sub in pipe_rows(it, crossref):
            art = sub.pop("_article", None) or pick_article(sub, use_house_brand)
            qty = sub.get("total_quantity") if sub.get("total_quantity") is not None else sub.get("quantity")
            price = customer_price(art["rsk"], book, customer, art.get("price"))
            inkop = purchase.get(rsk_norm(art["rsk"]) or art["rsk"]) if art["rsk"] else None
            flags = [f for f in (art.get("flag"), (sub.get("spec") or {}).get("Flagga")) if f]
            if qty is None:
                flags.append("antal saknas")
            if price["netto"] is None and art["rsk"]:
                flags.append("pris saknas")
            flags += [f for f in sub.get("quantity_flags") or [] if f not in flags]
            row = {"id": sub.get("id"), "pos": sub.get("code") or "", "text": sub.get("name") or "",
                   "foreskrift": " ".join(x for x in (sub.get("manufacturer"), sub.get("type")) if x),
                   "rsk": art["rsk"], "artikel": art.get("name") or "", "val": art.get("route") or "",
                   "antal": qty, "enhet": sub.get("unit") or "st", **price, "inkop": inkop,
                   "flaggor": flags, "kalla": sub.get("category") or "",
                   "option": bool(sub.get("option")), "mangd_kalla": sub.get("quantity_source") or "",
                   "reglerbar": bool(sub.get("adjustable")), "artikelstatus": sub.get("article_status") or ""}
            if kind == "kalkyloffert":
                per, src = hours_per_unit(sub)
                row["tim_per_enhet"], row["tim_kalla"] = per, src
                if per is None and "rör" not in src:
                    flags.append("montörstid saknas")
            rows.append(compute(row, hourly_rate))
    return rows


def compute(row: dict[str, Any], hourly_rate: float = 0.0) -> dict[str, Any]:
    """Summor för en rad: kundens belopp, inköp, marginal, och för kalkylofferten timmar och arbetskostnad."""
    q = float(row.get("antal") or 0)
    net = row.get("netto")
    row["summa"] = round(q * float(net), 2) if net is not None else None
    row["inkop_summa"] = round(q * float(row["inkop"]), 2) if row.get("inkop") is not None else None
    if row["summa"] is not None and row["inkop_summa"] is not None:
        row["marginal_kr"] = round(row["summa"] - row["inkop_summa"], 2)
        row["marginal_pct"] = round(100 * row["marginal_kr"] / row["summa"], 1) if row["summa"] else None
    else:
        row["marginal_kr"] = row["marginal_pct"] = None
    if row.get("tim_per_enhet") is not None:
        row["timmar"] = round(q * float(row["tim_per_enhet"]), 2)
        row["arbete_kr"] = round(row["timmar"] * float(hourly_rate or 0), 2)
    return row


def totals(rows: list[dict[str, Any]], bonus_pct: float | None = None, extra_hours: float = 0.0,
           hourly_rate: float = 0.0) -> dict[str, Any]:
    """Grundomfattningen. Optionerna räknas för sig och ingår inte i totalen."""
    opts = [r for r in rows if r.get("option")]
    out = _totals([r for r in rows if not r.get("option")], bonus_pct, extra_hours, hourly_rate)
    if opts:
        o = _totals(opts, None, 0.0, hourly_rate)
        out["optioner"] = {"material": o["material"], "arbete": o["arbete"], "timmar": o["timmar"], "total": o["total"],
                           "rader": o["rader"]}
    out["rader"] += len(opts)
    out["flaggade"] += sum(1 for r in opts if r.get("flaggor"))
    return out


def _totals(rows: list[dict[str, Any]], bonus_pct: float | None = None, extra_hours: float = 0.0,
            hourly_rate: float = 0.0) -> dict[str, Any]:
    material = sum(r["summa"] or 0 for r in rows)
    inkop = sum(r["inkop_summa"] or 0 for r in rows if r.get("inkop_summa") is not None)
    with_cost = sum(r["summa"] or 0 for r in rows if r.get("inkop_summa") is not None)
    timmar = sum(r.get("timmar") or 0 for r in rows) + float(extra_hours or 0)
    arbete = round(timmar * float(hourly_rate or 0), 2)
    total = round(material + arbete, 2)
    bonus = round(material * float(bonus_pct) / 100.0, 2) if bonus_pct else 0.0
    return {"material": round(material, 2), "arbete": arbete, "timmar": round(timmar, 2), "total": total,
            "inkop": round(inkop, 2), "marginal_kr": round(with_cost - inkop, 2) if inkop else None,
            "marginal_pct": round(100 * (with_cost - inkop) / with_cost, 1) if inkop and with_cost else None,
            "inkop_tackning": f"{sum(1 for r in rows if r.get('inkop_summa') is not None)} av {len(rows)} rader",
            "bonus_pct": bonus_pct, "bonus_kr": bonus,
            "flaggade": sum(1 for r in rows if r.get("flaggor")), "rader": len(rows)}
