"""KAM - årlig prisförhandling (ersätter Excel-filen med Justeringsvy och Varukorgsanalys).

Räkningen per artikel är densamma som i arbetsboken (bladet Varukorgsanalys):

  Prisgrund nu/NY        ur Nya priser; NY = nu om priset är <= 0,01, saknas eller gruppen har månadspris/kvartalspris
  Stöttning nu/NY        ur Stöttningar på artikel, annars kalkylgrupp, annars leverantör; < 1 är andel, annars kronor
  Inpris (prisgrund inkl stöttning) = prisgrund x (1 - stöttning)  eller  prisgrund - stöttning
  Brutto NY              kundunikt BP NY om sådant finns, annars Nya priser (med samma undantag som prisgrunden)
  Rabatt nu              ur rabattbrevet på nuvarande kalkylgrupp (6 tecken, annars 4, annars 2)
  Rabatt NY              justeringen på ny kalkylgrupp (förvalt: rabattbrevets rabatt för den nya gruppen)
  Bonus nu/NY            scenario för gruppen ur bonusförutsättningarna (anskaffning+område, anskaffning, artikel,
                         grupp 6/4/2), annars Scenario 1
  F-netto                kundunikt nettopris om sådant finns, annars (kundunikt BP eller brutto) x (1 - rabatt)
  Netnet                 F-netto x (1 - bonus)
  BRV                    (netnet - inpris) / netnet
  Totaler                x antal sålda R12 i varje varukorg (kunden, riksåterförsäljare, en tredje korg)

Justeringsvyn summerar per ny kalkylgrupp. För att justeringen ska kunna räknas om direkt i webbläsaren sparas för
varje grupp och korg netnet NY som en rät linje i rabatten: netnet_NY(X) = A x (1 - X/100) + F, där A är summan av
de artiklar som får rabatten och F summan av kundunika nettopriser (som inte påverkas).
"""
from __future__ import annotations

import io
import math
import re
from collections import defaultdict
from typing import Any, Iterable

RULE_VERSION = "kam-prisforhandling-1.0"
BASKETS = ("kund", "riks", "korg3")
BASKET_NAMES = {"kund": "Varukorg (kund)", "riks": "Varukorg riksåterförsäljare", "korg3": "Varukorg 3"}
LEVELS = (6, 4, 2)


def _f(v) -> float | None:
    if v in (None, "", "---"):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(" ", "")
    pct = s.endswith("%")
    s = re.sub(r"[^\d,.\-]", "", s)
    if s.count(",") == 1 and s.count(".") >= 1:
        s = s.replace(".", "")
    try:
        x = float(s.replace(",", "."))
    except ValueError:
        return None
    return x / 100 if pct else x


def _code(v) -> str:
    s = str(v if v is not None else "").strip()
    return re.sub(r"\.0$", "", s).upper()


def lookup(table: dict[str, Any], kg: str, default=None):
    """6 tecken före 4 före 2 (som rabattbrevet och försäljningsvillkoren i M3)."""
    kg = (kg or "").strip().upper()
    for n in LEVELS:
        k = kg[:n]
        if len(k) == n and k in table:
            return table[k]
    return default


def lookup_level(table: dict[str, Any], kg: str) -> str | None:
    kg = (kg or "").strip().upper()
    for n in LEVELS:
        k = kg[:n]
        if len(k) == n and k in table:
            return k
    return None


# ================================================================ indata

def empty_inputs() -> dict[str, Any]:
    return {"articles": {}, "group_names": {}, "rabattbrev": {}, "gamla_rabatter": {}, "kund_bp": {}, "kund_netto": {},
            "bonus": {"nu": {"scenarios": {}, "map": {}}, "ny": {"scenarios": {}, "map": {}}},
            "support": [], "monthly": {}, "baskets": {b: {} for b in BASKETS}, "segments": {},
            "supplier_info": [], "hierarchy": {}}


def bonus_for(bonus: dict[str, Any], anskaffn: str, artnr: str, kg: str) -> tuple[float, str]:
    m, sc = bonus.get("map") or {}, bonus.get("scenarios") or {}
    keys = [anskaffn + kg[:2], anskaffn, artnr, kg[:6], kg[:4], kg[:2]]
    name = next((m[k] for k in keys if k and k in m), "Scenario 1")
    return float(sc.get(name) or 0.0), name


def support_for(support_index: dict[str, tuple], artnr: str, kg: str, levnr: str) -> tuple[float, float]:
    for k in (artnr, kg, levnr):
        if k and k in support_index:
            return support_index[k]
    return 0.0, 0.0


def _support_index(rows: Iterable[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for r in rows:
        k = _code(r.get("key"))
        if k and k not in out:
            out[k] = (float(r.get("now") or 0), float(r.get("new") or 0))
    return out


def with_support(pg: float, st: float) -> float:
    return pg * (1 - st) if st < 1 else pg - st


# ================================================================ beräkning per artikel

def compute_articles(inp: dict[str, Any], adjustments: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """En rad per artikel med alla mellanled, som Varukorgsanalys. Bara artiklar med antal i någon korg tas med."""
    adjustments = {k.upper(): float(v) for k, v in (adjustments or {}).items() if v is not None}
    rab = inp["rabattbrev"]
    monthly = inp["monthly"]
    sup = _support_index(inp["support"])
    kbp, knet = inp["kund_bp"], inp["kund_netto"]
    bonus = inp["bonus"]
    baskets = inp["baskets"]
    wanted = set()
    for b in BASKETS:
        wanted.update(k for k, q in (baskets.get(b) or {}).items() if q)
    out = []
    for artnr in wanted:
        a = inp["articles"].get(artnr)
        if not a or a.get("priced") is False or (a.get("pg_nu") is None and not a.get("brutto_nu")):
            continue                                        # utan prisunderlag räknas artikeln inte (som i Excel)
        kg_nu = a.get("kg_nu") or a.get("kg_ny") or ""
        kg_ny = a.get("kg_ny") or kg_nu
        month = lookup(monthly, kg_ny) is not None
        m = a.get("pg_nu") or 0.0
        n_raw = a.get("pg_ny")
        pg_ny = m if (m <= 0.01 or month or n_raw is None or n_raw <= 0.01) else n_raw
        st_nu = support_for(sup, artnr, kg_nu, a.get("levnr") or "")[0]
        st_ny = support_for(sup, artnr, kg_ny, a.get("levnr") or "")[1]
        q_nu, q_ny = with_support(m, st_nu), with_support(pg_ny, st_ny)
        s = a.get("brutto_nu") or 0.0
        bp_nu, bp_ny = (kbp.get(artnr) or (0.0, 0.0))
        t_raw = a.get("brutto_ny")
        if bp_ny and bp_ny > 0:
            t = bp_ny
        else:
            t = s if (s <= 0.01 or month or t_raw is None or t_raw <= 0.01) else t_raw
        w = lookup(rab, kg_nu, 0.0)
        x = adjustments.get(kg_ny, lookup(rab, kg_ny, 0.0))
        z, _ = bonus_for(bonus["nu"], a.get("anskaffn") or "", artnr, kg_nu)
        aa, _ = bonus_for(bonus["ny"], a.get("anskaffn") or "", artnr, kg_ny)
        net_nu, net_ny = (knet.get(artnr) or (0.0, 0.0))
        base_nu = bp_nu if bp_nu and bp_nu > 0 else s
        base_ny = bp_ny if bp_ny and bp_ny > 0 else t
        fn_nu = net_nu if net_nu and net_nu > 0 else base_nu * (1 - w / 100)
        fn_ny = net_ny if net_ny and net_ny > 0 else base_ny * (1 - x / 100)
        nn_nu, nn_ny = fn_nu * (1 - z), fn_ny * (1 - aa)
        out.append({
            "artnr": artnr, "namn": a.get("namn") or "", "kg_nu": kg_nu, "kg_ny": kg_ny, "moved": kg_nu != kg_ny,
            "levnr": a.get("levnr") or "", "levnamn": a.get("levnamn") or "", "anskaffn": a.get("anskaffn") or "",
            "month": month, "pg_nu": m, "pg_ny": pg_ny, "st_nu": st_nu, "st_ny": st_ny, "in_nu": q_nu, "in_ny": q_ny,
            "brutto_nu": s, "brutto_ny": t, "kbp_nu": bp_nu, "kbp_ny": bp_ny, "rab_nu": w, "rab_ny": x,
            "bonus_nu": z, "bonus_ny": aa, "fn_nu": fn_nu, "fn_ny": fn_ny, "knet_nu": net_nu, "knet_ny": net_ny,
            "nn_nu": nn_nu, "nn_ny": nn_ny,
            "brv_nu": (nn_nu - q_nu) / nn_nu if nn_nu else 0.0, "brv_ny": (nn_ny - q_ny) / nn_ny if nn_ny else 0.0,
            # netnet NY som linje i rabatten: nn_ny = lin_a * (1 - X/100) + lin_f
            "lin_a": 0.0 if (net_ny and net_ny > 0) else base_ny * (1 - aa),
            "lin_f": net_ny * (1 - aa) if (net_ny and net_ny > 0) else 0.0,
            "qty": {b: max(0.0, float((baskets.get(b) or {}).get(artnr) or 0)) for b in BASKETS},
        })
    return out


def _ratio(a: float, b: float) -> float | None:
    return None if not b else a / b


def basket_totals(rows: list[dict[str, Any]], basket: str) -> dict[str, float | None]:
    t = defaultdict(float)
    for r in rows:
        q = r["qty"][basket]
        if not q:
            continue
        t["in_nu"] += r["in_nu"] * q
        t["in_ny"] += r["in_ny"] * q
        t["fn_nu"] += r["fn_nu"] * q
        t["fn_ny"] += r["fn_ny"] * q
        t["nn_nu"] += r["nn_nu"] * q
        t["nn_ny"] += r["nn_ny"] * q
    out: dict[str, float | None] = dict(t)
    out["brv_nu"] = _ratio(t["nn_nu"] - t["in_nu"], t["nn_nu"])
    out["brv_ny"] = _ratio(t["nn_ny"] - t["in_ny"], t["nn_ny"])
    out["brv_diff"] = None if out["brv_nu"] is None or out["brv_ny"] is None else out["brv_ny"] - out["brv_nu"]
    out["prisdiff"] = None if not t["nn_nu"] else t["nn_ny"] / t["nn_nu"] - 1
    out["inprisdiff"] = None if not t["in_nu"] else t["in_ny"] / t["in_nu"] - 1
    return out


# ================================================================ justeringsvyn

def set_adjustments(grs: list[dict[str, Any]], adjustments: dict[str, float] | None = None,
                    netto: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """Sätter rabatt NY och nettoprisjustering på cachade grupper (räkningen är linjär i dem)."""
    adjustments = {k.upper(): float(v) for k, v in (adjustments or {}).items() if v is not None}
    netto = {k.upper(): float(v) for k, v in (netto or {}).items() if v is not None}
    for gr in grs:
        gr["rab_ny"] = adjustments.get(gr["kg"], gr["rab_nu"])
        gr["netto_pct"] = netto.get(gr["kg"], 0.0)
    return grs


def groups(inp: dict[str, Any], rows: list[dict[str, Any]], adjustments: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """En rad per ny kalkylgrupp med summor per korg och den räta linjen för netnet NY."""
    adjustments = {k.upper(): float(v) for k, v in (adjustments or {}).items() if v is not None}
    rab = inp["rabattbrev"]
    old = inp.get("gamla_rabatter") or {}
    names = inp.get("group_names") or {}
    hier = inp.get("hierarchy") or {}
    g: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = r["kg_ny"]
        x = g.setdefault(k, {"kg": k, "n_articles": 0, "moved": 0, "month": r["month"], "levs": defaultdict(float),
                             "b": {b: defaultdict(float) for b in BASKETS}})
        x["n_articles"] += 1
        x["moved"] += 1 if r["moved"] else 0
        for b in BASKETS:
            q = r["qty"][b]
            if not q:
                continue
            s = x["b"][b]
            s["qty"] += q
            s["in_nu"] += r["in_nu"] * q
            s["in_ny"] += r["in_ny"] * q
            s["nn_nu"] += r["nn_nu"] * q
            s["nn_ny"] += r["nn_ny"] * q
            s["pg_nu"] += r["pg_nu"] * q
            s["pg_ny"] += r["pg_ny"] * q
            s["lin_a"] += r["lin_a"] * q
            s["lin_f"] += r["lin_f"] * q
            s["n"] += 1
            if b == "kund":
                x["levs"][r["levnamn"].strip() or r["levnr"]] += r["nn_nu"] * q
    out = []
    for k, x in g.items():
        rab_nu = lookup(rab, k, 0.0)
        lvl = lookup_level(rab, k)
        h = hier.get(k) or {}
        levs = sorted(x["levs"].items(), key=lambda t: -t[1])
        row = {
            "kg": k, "name": (names.get(k) or "").strip(), "omr": k[:2], "kat": k[:4],
            "omr_name": h.get("omr_name") or (names.get(k[:2]) or "").strip(),
            "kat_name": h.get("kat_name") or (names.get(k[:4]) or "").strip(),
            "affomr": h.get("affomr") or "", "forhomr": h.get("forhomr") or "",
            "leverantor": levs[0][0] if levs else "", "n_articles": x["n_articles"], "moved": x["moved"],
            "month": x["month"], "rab_nu": rab_nu, "rab_level": lvl, "new_group": lvl is None or len(lvl) < len(k) and len(k) == 6,
            "rab_ny": adjustments.get(k, rab_nu), "rab_old": old.get(k),
            "b": {b: {kk: round(v, 4) for kk, v in x["b"][b].items()} for b in BASKETS},
        }
        out.append(row)
    out.sort(key=lambda r: r["kg"])
    return out


def apply_rab(gr: dict[str, Any], basket: str, x: float | None = None,
              netto_pct: float | None = None) -> dict[str, float | None]:
    """Gruppens nyckeltal i en korg vid rabatten x (samma räkning som webbläsaren gör)."""
    s = gr["b"][basket]
    x = gr["rab_ny"] if x is None else x
    netto_pct = (gr.get("netto_pct") or 0.0) if netto_pct is None else netto_pct
    nn_nu, in_nu, in_ny = s.get("nn_nu", 0.0), s.get("in_nu", 0.0), s.get("in_ny", 0.0)
    nn_ny = s.get("lin_a", 0.0) * (1 - x / 100) + s.get("lin_f", 0.0) * (1 + netto_pct)
    brv_nu = _ratio(nn_nu - in_nu, nn_nu)
    brv_ny = _ratio(nn_ny - in_ny, nn_ny)
    return {"nn_nu": nn_nu, "nn_ny": nn_ny, "in_nu": in_nu, "in_ny": in_ny, "brv_nu": brv_nu, "brv_ny": brv_ny,
            "brv_diff": None if brv_nu is None or brv_ny is None else brv_ny - brv_nu,
            "prisdiff": None if not nn_nu else nn_ny / nn_nu - 1, "inprisdiff": None if not in_nu else in_ny / in_nu - 1}


def totals(grs: list[dict[str, Any]], basket: str) -> dict[str, float | None]:
    t = defaultdict(float)
    for gr in grs:
        a = apply_rab(gr, basket)
        for k in ("nn_nu", "nn_ny", "in_nu", "in_ny"):
            t[k] += a[k]
    out: dict[str, float | None] = dict(t)
    out["brv_nu"] = _ratio(t["nn_nu"] - t["in_nu"], t["nn_nu"])
    out["brv_ny"] = _ratio(t["nn_ny"] - t["in_ny"], t["nn_ny"])
    out["brv_diff"] = None if out["brv_nu"] is None or out["brv_ny"] is None else out["brv_ny"] - out["brv_nu"]
    out["prisdiff"] = None if not t["nn_nu"] else t["nn_ny"] / t["nn_nu"] - 1
    out["inprisdiff"] = None if not t["in_nu"] else t["in_ny"] / t["in_nu"] - 1
    return out


# ================================================================ intelligens: avvikelser och förslag

def rab_for_target(gr: dict[str, Any], basket: str, nn_target: float) -> float | None:
    """Rabatten som ger netnet NY = målet: X = 100 x (1 - (mål - F) / A)."""
    s = gr["b"][basket]
    a = s.get("lin_a", 0.0)
    if a <= 0:
        return None
    return 100 * (1 - (nn_target - s.get("lin_f", 0.0) * (1 + (gr.get("netto_pct") or 0.0))) / a)


def _round_half(x: float) -> float:
    return math.floor(x * 2 + 0.5) / 2


def segment_brv(inp: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    """Segmentens (korgfilernas) BRV och försäljning per ny kalkylgrupp."""
    kg_of = {r["artnr"]: r["kg_ny"] for r in rows}
    art = inp["articles"]
    out: dict[str, dict[str, dict[str, float]]] = {}
    for name, seg in (inp.get("segments") or {}).items():
        acc: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for artnr, v in seg.items():
            kg = kg_of.get(artnr) or (art.get(artnr) or {}).get("kg_ny")
            if not kg:
                continue
            netto, brv, qty = v.get("netto"), v.get("brv"), v.get("antal") or 0
            if brv is None or not -1 <= brv <= 1 or qty <= 0:
                continue                                    # returer och orimliga BRV vägs inte in
            price = (art.get(artnr) or {}).get("brutto_nu") or 0
            w = netto if netto is not None and netto > 0 else qty * price
            if w <= 0:
                continue
            a = acc[kg]
            a["w"] += w
            a["netto"] += netto if netto is not None else 0
            a["qty"] += qty
            a["brv_w"] += brv * w
        out[name] = {k: {"netto": v["netto"], "qty": v["qty"], "weight": v["w"], "brv": v["brv_w"] / v["w"] if v["w"] else None}
                     for k, v in acc.items()}
    return out


def insights(grs: list[dict[str, Any]], seg: dict[str, dict[str, dict[str, float]]] | None = None,
             settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Grupper att titta på, med orsak och förslag på ny rabatt. Deterministiskt; ingen gissning.

    * Under kostpris          BRV NY < 0                                            -> rabatt som ger BRV nu
    * Marginaltapp            BRV NY sjunker mer än gränsen (förvalt 1 %-enhet)       -> rabatt som behåller BRV
    * Höjer mer än inpriset   prisdiff mer än inprisdiff + gränsen                    -> rabatt där priset följer inpriset
    * Tappar försäljning      kundens andel av gruppen är långt under riksåterförsäljarnas (andel < 50 %),
                              eller kunden betalar högre BRV än segmentet (korgfilerna) -> priset följer inpriset
    * Ny grupp / flytt        gruppen saknar egen rabatt i rabattbrevet, eller artiklar har bytt kalkylgrupp
    * Avviker från förra året rabatt nu skiljer sig från rabatten vid förra prisuppdateringen
    """
    st = {"brv_drop": 0.01, "price_gap": 0.01, "share_ratio": 0.5, "seg_gap": 0.03, "max_step": 5.0, "min_volume": 10000.0,
          "min_brv": 0.05}
    st.update(settings or {})
    seg = seg or {}
    tk = sum(gr["b"]["kund"].get("nn_nu", 0.0) for gr in grs) or 0.0
    tr_ = sum(gr["b"]["riks"].get("nn_nu", 0.0) for gr in grs) or 0.0
    out = []
    for gr in grs:
        k = apply_rab(gr, "kund")
        r = apply_rab(gr, "riks")
        flags: list[dict[str, str]] = []
        sugg = None
        vol = k["nn_nu"] or 0.0
        if k["nn_ny"] and k["brv_ny"] is not None and k["brv_ny"] < 0:
            flags.append({"code": "UNDER_KOSTPRIS", "sev": "high", "text": f"BRV NY {k['brv_ny']:.1%} - under inpris"})
        if k["brv_diff"] is not None and k["brv_diff"] < -st["brv_drop"] and vol >= st["min_volume"]:
            flags.append({"code": "MARGINALTAPP", "sev": "mid", "text": f"BRV sjunker {k['brv_diff'] * 100:.1f} %-enheter"})
        if (k["prisdiff"] is not None and k["inprisdiff"] is not None and vol >= st["min_volume"]
                and k["prisdiff"] > k["inprisdiff"] + st["price_gap"]):
            txt = (f"Priset höjs {k['prisdiff']:.1%} mot inpris {k['inprisdiff']:+.1%}" if k["prisdiff"] >= 0 else
                   f"Priset sänks bara {-k['prisdiff']:.1%} när inpriset sänks {-k['inprisdiff']:.1%}")
            flags.append({"code": "HOJER_MER_AN_INPRIS", "sev": "mid", "text": txt})
        share_k = vol / tk if tk else 0
        share_r = (r["nn_nu"] or 0) / tr_ if tr_ else 0
        if share_r > 0.0005 and share_k < share_r * st["share_ratio"]:
            flags.append({"code": "TAPPAR_FORSALJNING", "sev": "mid",
                          "text": f"Kundens andel {share_k:.2%} mot riksåterförsäljarnas {share_r:.2%} - köper troligen annanstans"})
        for name, sg in seg.items():
            sgr = sg.get(gr["kg"])
            if sgr and sgr.get("brv") is not None and k["brv_ny"] is not None and vol >= st["min_volume"] \
                    and not gr["month"] and (sgr.get("weight") or 0) >= st["min_volume"] \
                    and k["brv_ny"] > sgr["brv"] + st["seg_gap"]:
                flags.append({"code": "DYRARE_AN_SEGMENT", "sev": "mid",
                              "text": f"BRV NY {k['brv_ny']:.1%} mot {name} {sgr['brv']:.1%} - risk att tappa"})
        if gr["new_group"] and vol > 0:
            flags.append({"code": "NY_GRUPP", "sev": "low", "text": "Gruppen saknar egen rad i rabattbrevet"})
        if gr["moved"]:
            flags.append({"code": "KALKGR_FLYTT", "sev": "low", "text": f"{gr['moved']} artiklar har bytt kalkylgrupp"})
        if gr.get("rab_old") is not None and abs((gr["rab_old"] or 0) - gr["rab_nu"]) > 0.001:
            flags.append({"code": "AVVIKER_FG_AR", "sev": "low", "text": f"Rabatt vid förra uppdateringen {gr['rab_old']} %"})
        if gr["month"]:
            flags.append({"code": "MANADSPRIS", "sev": "info", "text": "Månads-/kvartalspris - priset justeras löpande"})
        if not flags:
            continue
        codes = {f["code"] for f in flags}
        target = None
        why = ""
        if "UNDER_KOSTPRIS" in codes and k["in_ny"]:
            goal = max(k["brv_nu"] or 0.0, st["min_brv"])
            target = k["in_ny"] / (1 - goal)
            why = f"Lyfter BRV till {goal:.0%}"
        elif "MARGINALTAPP" in codes and k["brv_nu"] is not None and k["brv_nu"] < 1 and k["in_ny"]:
            target = k["in_ny"] / (1 - k["brv_nu"])
            why = "Behåller BRV nu"
        elif codes & {"HOJER_MER_AN_INPRIS", "TAPPAR_FORSALJNING", "DYRARE_AN_SEGMENT"} and k["inprisdiff"] is not None:
            target = k["nn_nu"] * (1 + k["inprisdiff"])
            why = "Kundpriset följer inpriset"
        s_k = gr["b"]["kund"]
        if target and vol and s_k.get("lin_a", 0) <= 0 and s_k.get("lin_f", 0) > 0 and k["nn_ny"] \
                and abs(target / k["nn_ny"] - 1) >= 0.005:
            # bara kundunika nettopriser i gruppen: rabatten biter inte, nettopriserna ska justeras
            sugg = {"type": "netto", "pct": target / k["nn_ny"] - 1, "why": why + " - justera kundunika nettopriser",
                    "nn_ny": target, "brv_ny": (target - k["in_ny"]) / target if target else None,
                    "prisdiff": target / k["nn_nu"] - 1 if k["nn_nu"] else None}
        elif target and vol and not gr["month"]:
            x = rab_for_target(gr, "kund", target)
            if x is not None:
                raw = _round_half(x)
                x = max(gr["rab_nu"] - st["max_step"], min(gr["rab_nu"] + st["max_step"], raw))
                if x != raw:
                    why += f" (begränsat till ±{st['max_step']:g} %-enheter, behövs {raw:g} %)"
                x = max(0.0, min(99.0, x))
                if abs(x - gr["rab_ny"]) >= 0.5:
                    eff = apply_rab(gr, "kund", x)
                    sugg = {"type": "rabatt", "rab": x, "why": why, "nn_ny": eff["nn_ny"], "brv_ny": eff["brv_ny"],
                            "prisdiff": eff["prisdiff"]}
        sev = min(({"high": 0, "mid": 1, "low": 2, "info": 3}[f["sev"]] for f in flags))
        out.append({"kg": gr["kg"], "name": gr["name"], "omr": gr["omr"], "volume": vol, "flags": flags,
                    "severity": ["high", "mid", "low", "info"][sev], "suggestion": sugg})
    out.sort(key=lambda i: ({"high": 0, "mid": 1, "low": 2, "info": 3}[i["severity"]], -i["volume"]))
    return out


# ================================================================ kundpresentation och export

def by_area(grs: list[dict[str, Any]], basket: str = "kund") -> list[dict[str, Any]]:
    acc: dict[str, dict[str, Any]] = {}
    for gr in grs:
        a = apply_rab(gr, basket)
        x = acc.setdefault(gr["omr"], {"omr": gr["omr"], "name": gr["omr_name"], "nn_nu": 0.0, "nn_ny": 0.0, "in_nu": 0.0, "in_ny": 0.0})
        for k in ("nn_nu", "nn_ny", "in_nu", "in_ny"):
            x[k] += a[k]
        if not x["name"] and gr["omr_name"]:
            x["name"] = gr["omr_name"]
    out = []
    for x in acc.values():
        if not x["nn_nu"] and not x["nn_ny"]:
            continue
        x["prisdiff"] = None if not x["nn_nu"] else x["nn_ny"] / x["nn_nu"] - 1
        x["inprisdiff"] = None if not x["in_nu"] else x["in_ny"] / x["in_nu"] - 1
        x["brv_nu"] = _ratio(x["nn_nu"] - x["in_nu"], x["nn_nu"])
        x["brv_ny"] = _ratio(x["nn_ny"] - x["in_ny"], x["nn_ny"])
        out.append(x)
    out.sort(key=lambda x: -x["nn_nu"])
    return out


def rabattbrev_txt(grs: list[dict[str, Any]], inp: dict[str, Any], only_changed: bool = False) -> str:
    """Rabattbrevet i samma fasta format som M3-utskriften: kalkylgrupp (9), benämning (30), rabatt."""
    rab = dict(inp["rabattbrev"])
    names = inp.get("group_names") or {}
    changed = {gr["kg"]: gr["rab_ny"] for gr in grs if abs(gr["rab_ny"] - gr["rab_nu"]) > 1e-9 or gr["new_group"]}
    if only_changed:
        rab = {}
    rab.update(changed)
    lines = []
    for k in sorted(rab):
        lines.append(f"{k:<9}{(names.get(k) or '')[:30]:<30}{rab[k]:.1f}")
    return "\r\n".join(lines) + "\r\n"


def to_xlsx(meta: dict[str, Any], inp: dict[str, Any], grs: list[dict[str, Any]], kind: str = "intern",
            ins: list[dict[str, Any]] | None = None) -> bytes:
    """intern: justeringsvy, korgar, insikter. kund: prisjusteringen per område och nytt rabattbrev - aldrig inpris
    eller BRV."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    bold, head = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")

    def sheet(title, header, rows, widths=None, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill = bold, head
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for r in rows:
            ws.append(r)
        for i, w in enumerate(widths or [], 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
        ws.freeze_panes = "A2"
        return ws

    pct = lambda v: None if v is None else round(v * 100, 2)
    if kind == "kund":
        t = totals(grs, "kund")
        sheet("Prisjustering", ["", ""], [
            ["Kund", meta.get("customer") or ""], ["Avser", meta.get("name") or ""],
            ["Giltig från", meta.get("valid_from") or ""],
            ["Er inköpsvolym R12 (nuvarande priser), kr", round(t["nn_nu"] or 0)],
            ["Samma volym med nya priser, kr", round(t["nn_ny"] or 0)],
            ["Prisförändring på er varukorg, %", pct(t["prisdiff"])],
        ], [44, 40], first=True)
        sheet("Per produktområde", ["Område", "Benämning", "Volym R12 nu (kr)", "Volym R12 ny (kr)", "Prisförändring %"],
              [[a["omr"], a["name"], round(a["nn_nu"]), round(a["nn_ny"]), pct(a["prisdiff"])] for a in by_area(grs)],
              [10, 40, 18, 18, 16])
        if inp.get("supplier_info"):
            sheet("Leverantörernas prisförändringar", ["Leverantör", "Prisförändring %", "Volym", "Kommentar"],
                  [[s.get("leverantor"), pct(s.get("change")), s.get("volym"), s.get("kommentar")] for s in inp["supplier_info"]],
                  [24, 16, 12, 90])
        sheet("Nytt rabattbrev", ["Kalkylgrupp", "Benämning", "Rabatt %"],
              [[gr["kg"], gr["name"], gr["rab_ny"]] for gr in grs if gr["b"]["kund"].get("nn_nu") or gr["rab_ny"] != gr["rab_nu"]],
              [12, 40, 10])
    else:
        rows = []
        for gr in grs:
            k, r3 = apply_rab(gr, "kund"), apply_rab(gr, "riks")
            rows.append([gr["kg"], gr["name"], gr["omr"], gr["leverantor"], gr["rab_old"], gr["rab_nu"], gr["rab_ny"],
                         round(gr["rab_ny"] - gr["rab_nu"], 2), "x" if gr["new_group"] else "", gr["moved"] or "",
                         "Månadspris" if gr["month"] else "", round(k["in_nu"]), round(k["in_ny"]), round(k["nn_nu"]), round(k["nn_ny"]),
                         pct(k["brv_nu"]), pct(k["brv_ny"]), pct(k["brv_diff"]), pct(k["prisdiff"]), pct(k["inprisdiff"]),
                         round(r3["nn_nu"]), round(r3["nn_ny"]), pct(r3["brv_nu"]), pct(r3["brv_ny"]), pct(r3["prisdiff"])])
        sheet("Justeringsvy", ["Kalkgr NY", "Benämning", "Område", "Största leverantör", "Rabatt fg år", "Rabatt nu", "Rabatt NY",
                               "Rabatt diff", "Ny grupp", "Kalkgrflyttar", "Fsg-villkor", "Inpris nu (kund)", "Inpris NY (kund)",
                               "Netnet nu (kund)", "Netnet NY (kund)", "BRV nu %", "BRV NY %", "BRV diff %-e", "Prisdiff %",
                               "Inprisdiff %", "Netnet nu (riks)", "Netnet NY (riks)", "BRV nu % (riks)", "BRV NY % (riks)",
                               "Prisdiff % (riks)"], rows, [10, 34, 7, 26] + [11] * 21, first=True)
        summ = []
        for b in BASKETS:
            t = totals(grs, b)
            summ.append([BASKET_NAMES[b], round(t["nn_nu"] or 0), round(t["nn_ny"] or 0), pct(t["brv_nu"]), pct(t["brv_ny"]),
                         pct(t["prisdiff"]), pct(t["inprisdiff"])])
        sheet("Sammanfattning", ["Varukorg", "Netnet nu", "Netnet NY", "BRV nu %", "BRV NY %", "Prisdiff %", "Inprisdiff %"],
              summ, [30, 16, 16, 10, 10, 10, 12])
        if ins:
            sheet("Insikter", ["Kalkgr", "Benämning", "Volym kund (kr)", "Allvar", "Avvikelser", "Föreslagen rabatt", "Motiv"],
                  [[i["kg"], i["name"], round(i["volume"]), i["severity"], "; ".join(f["text"] for f in i["flags"]),
                    (i["suggestion"] or {}).get("rab"), (i["suggestion"] or {}).get("why")] for i in ins],
                  [10, 34, 14, 8, 80, 12, 24])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


# ================================================================ inläsning av filer

def _rows_xlsx(data: bytes, sheet: str | None = None) -> dict[str, list[list[Any]]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        if sheet and ws.title != sheet:
            continue
        out[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    return out


def _rows_xlsb(data: bytes) -> dict[str, list[list[Any]]]:
    from pyxlsb import open_workbook
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".xlsb", delete=False) as fh:
        fh.write(data)
        path = fh.name
    try:
        out = {}
        with open_workbook(path) as wb:
            for s in wb.sheets:
                with wb.get_sheet(s) as sh:
                    out[s] = [[c.v for c in r] for r in sh.rows()]
        return out
    finally:
        os.unlink(path)


def _norm(h) -> str:
    return re.sub(r"\s+", " ", str(h or "").strip().lower())


def _find_header(rows: list[list[Any]], need: Iterable[str], scan: int = 15) -> tuple[int, dict[str, int]] | None:
    need = list(need)
    for i, r in enumerate(rows[:scan]):
        hs = [_norm(c) for c in r]
        if all(any(h == n or h.startswith(n) for h in hs) for n in need):
            cols = {}
            for j, h in enumerate(hs):
                if h and h not in cols:
                    cols[h] = j
            return i, cols
    return None


def _col(cols: dict[str, int], *names: str) -> int | None:
    for n in names:
        if n in cols:
            return cols[n]
    for n in names:
        for h, j in cols.items():
            if h.startswith(n):
                return j
    return None


def parse_rabattbrev_txt(text: str) -> tuple[dict[str, float], dict[str, str]]:
    """M3:s rabattbrev: kalkylgrupp i början, benämning (30 tecken), rabatten sist."""
    rab, names = {}, {}
    for ln in text.splitlines():
        ln = ln.rstrip()
        # fasta kolumner: grupp (9), benämning (30), rabatt - benämningen kan sluta på en siffra ("M10")
        if len(ln) > 39 and re.fullmatch(r"[A-Z0-9]{2,6}\s*", ln[:9]) and re.fullmatch(r"\s*-?\d+(?:[.,]\d+)?", ln[39:]):
            k = ln[:9].strip().upper()
            rab[k] = float(ln[39:].strip().replace(",", "."))
            if ln[9:39].strip():
                names[k] = ln[9:39].strip()
            continue
        m = re.match(r"^([A-Z0-9]{2,6})\s+(.*?)\s(-?\d+(?:[.,]\d+)?)\s*$", ln)
        if not m:
            continue
        k, name, v = m.group(1).upper(), m.group(2).strip(), float(m.group(3).replace(",", "."))
        rab[k] = v
        if name:
            names[k] = name
    return rab, names


def detect_and_parse(name: str, data: bytes) -> list[tuple[str, Any]]:
    """Känner igen en fil och returnerar [(sort, innehåll)]. En arbetsbok kan ge flera sorter."""
    low = name.lower()
    if low.endswith(".txt") or low.endswith(".csv") and b";" not in data[:2000]:
        text = data.decode("cp1252", errors="replace") if not data[:3] == b"\xef\xbb\xbf" else data.decode("utf-8-sig")
        rab, names = parse_rabattbrev_txt(text)
        if rab:
            return [("rabattbrev", {"rab": rab, "names": names})]
        return []
    sheets = _rows_xlsb(data) if low.endswith(".xlsb") else _rows_xlsx(data)
    return parse_sheets(sheets, name)


def parse_sheets(sheets: dict[str, list[list[Any]]], fname: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for title, rows in sheets.items():
        if not rows:
            continue
        t = title.strip().lower()
        # ---- Nya priser
        h = _find_header(rows, ["artnr", "kalkgr ny", "prisgrund nu", "prisgrund ny", "brutto ny"])
        if h:
            i, c = h
            arts, names = {}, {}
            for r in rows[i + 1:]:
                a = _code(r[c["artnr"]]) if c["artnr"] < len(r) else ""
                if not a:
                    continue
                kg = _code(r[_col(c, "kalkgr ny")])
                arts[a] = {"kg_ny": kg, "pg_nu": _f(r[_col(c, "prisgrund nu")]), "pg_ny": _f(r[_col(c, "prisgrund ny")]),
                           "brutto_ny": _f(r[_col(c, "brutto ny")])}
                j = _col(c, "kalkgr benämn ny")
                if j is not None and kg and r[j]:
                    names[kg] = str(r[j]).strip()
            out.append(("nya_priser", {"articles": arts, "names": names}))
            continue
        # ---- Varukorgsanalys (artikelbas: nuvarande grupp, leverantör, anskaffning, brutto nu)
        h = _find_header(rows, ["artikelnr", "kalkgr nu", "brutto nu", "levnr"])
        if h:
            i, c = h
            arts, names = {}, {}
            for r in rows[i + 1:]:
                a = _code(r[c["artikelnr"]]) if r and r[0] is not None else ""
                if not a:
                    continue
                g = lambda *n: (r[_col(c, *n)] if _col(c, *n) is not None and _col(c, *n) < len(r) else None)
                kg = _code(g("kalkgr nu"))
                arts[a] = {"namn": str(g("benämn") or "").strip(), "kg_nu": kg, "levnr": _code(g("levnr")),
                           "levnamn": str(g("levnamn") or "").strip(), "anskaffn": _code(g("anskaffn")),
                           "status": _code(g("status")), "brutto_nu": _f(g("brutto nu"))}
                if kg and g("kalkgr benämn nu"):
                    names[kg] = str(g("kalkgr benämn nu")).strip()
            out.append(("artikelbas", {"articles": arts, "names": names}))
            continue
        # ---- Dahlpris (kundens prisfil: rsknr, rabattgrupp, bruttopris GNP)
        h = _find_header(rows, ["rsknr", "rabgr", "gnp"])
        if h:
            i, c = h
            arts = {}
            for r in rows[i + 1:]:
                a = _code(r[c["rsknr"]]) if r and r[0] is not None else ""
                if a and a != "RSKNR":
                    arts[a] = {"namn": str(r[_col(c, "benämning")] or "").strip(), "kg_nu": _code(r[c["rabgr"]]),
                               "brutto_nu": _f(r[c["gnp"]])}
            if arts:
                out.append(("bruttolista", {"articles": arts}))
            continue
        # ---- Artikeldata / artikelregister (hierarkin)
        h = _find_header(rows, ["artikelnr", "produktområde nr", "kalkylgrupp nr"])
        if h:
            i, c = h
            arts, hier, names = {}, {}, {}
            for r in rows[i + 1:]:
                g = lambda *n: (r[_col(c, *n)] if _col(c, *n) is not None and _col(c, *n) < len(r) else None)
                a = _code(g("artikelnr"))
                if not a or a in ("DELTOTALER", "TOTALER"):
                    continue
                kg = _code(g("kalkylgrupp nr"))
                arts[a] = {"namn": str(g("artikel") or "").strip(), "kg_master": kg, "levnamn": str(g("leverantör") or "").strip(),
                           "anskaffn": _code(g("anskaffningsgrupp kod")), "status": _code(g("artikelstatus"))}
                if kg and kg not in hier:
                    hier[kg] = {"omr_name": str(g("produktområde") or "").strip(), "kat_name": str(g("produktkategori") or "").strip(),
                                "affomr": str(g("affärsområde") or g("affärsområde nr") or "").strip(),
                                "forhomr": str(g("förhandlingsområde") or "").strip()}
                    names[kg] = str(g("kalkylgrupp") or "").strip()
                    if g("produktområde nr"):
                        names.setdefault(_code(g("produktområde nr")), str(g("produktområde") or "").strip())
                    if g("produktkategori nr"):
                        names.setdefault(_code(g("produktkategori nr")), str(g("produktkategori") or "").strip())
            out.append(("artikeldata", {"articles": arts, "hierarchy": hier, "names": names}))
            continue
        # ---- Prisgrund (xlsb: artnr, kalkylgrp, prisgrund)
        h = _find_header(rows, ["artnr", "kalkylgrp", "prisgrund"])
        if h:
            i, c = h
            arts, names = {}, {}
            for r in rows[i + 1:]:
                a = _code(r[c["artnr"]]) if r and r[0] is not None else ""
                if not a:
                    continue
                kg = _code(r[c["kalkylgrp"]])
                arts[a] = {"namn": str(r[_col(c, "benämn")] or "").strip(), "kg_nu": kg, "pg_nu": _f(r[c["prisgrund"]])}
                j = _col(c, "kalkgr benämn")
                if j is not None and r[j]:
                    names[kg] = str(r[j]).strip()
            out.append(("prisgrund", {"articles": arts, "names": names}))
            continue
        # ---- Rabattbrev som blad (Prod.gr / Benämning / Rabatt, och uppslagslistan X:Y)
        if "rabattbrev" in t:
            rab, names = {}, {}
            for r in rows:
                for j in range(len(r) - 2):
                    k = _code(r[j])
                    if re.fullmatch(r"[A-Z]{2}(\d{2}|\d{4})?", k or "") and _f(r[j + 2]) is not None and isinstance(r[j + 1], str):
                        rab.setdefault(k, _f(r[j + 2]))
                        names.setdefault(k, r[j + 1].strip())
                # uppslagslistan (kalkylgrupp, rabatt) som formlerna använder går först
                if len(r) >= 25 and re.fullmatch(r"[A-Z]{2}\d{0,4}", _code(r[23]) or "-") and _f(r[24]) is not None:
                    rab[_code(r[23])] = _f(r[24])
            if rab:
                out.append(("rabattbrev", {"rab": rab, "names": names}))
            continue
        # ---- Kundunika BP & nettopriser
        h = _find_header(rows, ["artikelnr", "kundunikt bp nu"]) or _find_header(rows, ["artikelnr", "kundunikt netto nu"])
        if h:
            i, _ = h
            hs = [_norm(x) for x in rows[i]]
            bp, net = {}, {}
            for j, x in enumerate(hs):
                if x == "kundunikt bp nu":
                    tgt, a_col = bp, max(k for k in range(j) if hs[k] == "artikelnr")
                elif x == "kundunikt netto nu":
                    tgt, a_col = net, max(k for k in range(j) if hs[k] == "artikelnr")
                else:
                    continue
                for r in rows[i + 1:]:
                    if a_col < len(r) and r[a_col] not in (None, ""):
                        # som LETARAD i arbetsboken: första raden för artikeln gäller
                        tgt.setdefault(_code(r[a_col]), (_f(r[j]) or 0.0, _f(r[j + 1]) or 0.0))
            out.append(("kundunika", {"bp": bp, "netto": net}))
            continue
        # ---- Bonusförutsättningar (nu till vänster, NY till höger)
        if "bonus" in t or any(_norm(r[0]) == "avvikelse grupper" for r in rows if r):
            res = {"nu": {"scenarios": {}, "map": {}}, "ny": {"scenarios": {}, "map": {}}}
            starts = sorted({j for r in rows for j, x in enumerate(r) if _norm(x) == "scenario"})
            sides = [s for s in starts if s == 0 or s >= 5][:2] or [0]
            for side, off in zip(("nu", "ny"), sides):
                mode = None
                for r in rows:
                    a = r[off] if off < len(r) else None
                    b = r[off + 1] if off + 1 < len(r) else None
                    if _norm(a) == "avvikelse grupper":
                        mode = "map"
                        continue
                    if _norm(a) in ("rabatt", "bonus"):
                        mode = None if mode == "map" else mode
                        continue
                    if isinstance(a, str) and a.strip().lower().startswith("scenario") and _f(b) is not None and mode != "map":
                        res[side]["scenarios"][a.strip()] = _f(b)
                    elif mode == "map" and a and isinstance(b, str) and b.strip().lower().startswith("scenario"):
                        res[side]["map"][_code(a)] = b.strip()
            if res["nu"]["scenarios"]:
                if not res["ny"]["scenarios"]:
                    res["ny"] = res["nu"]
                out.append(("bonus", res))
            continue
        # ---- Stöttningar
        h = _find_header(rows, ["styrande stöttningsnivå", "stöttning nu", "stöttning ny"])
        if h:
            i, c = h
            sup = []
            for r in rows[i + 1:]:
                k = _code(r[c["styrande stöttningsnivå"]]) if r else ""
                if k:
                    sup.append({"key": k, "leverantor": str(r[_col(c, "leverantörsnamn")] or "").strip(),
                                "now": _f(r[c["stöttning nu"]]) or 0.0, "new": _f(r[c["stöttning ny"]]) or 0.0,
                                "kund": str(r[_col(c, "kund")] or "").strip() if _col(c, "kund") is not None else ""})
            out.append(("stottningar", sup))
            continue
        # ---- Antal sålda (upp till tre varukorgar sida vid sida)
        h = _find_header(rows, ["artnr", "antal sålda"])
        if h:
            i, _ = h
            hs = [_norm(x) for x in rows[i]]
            pairs = [j for j, x in enumerate(hs) if x == "artnr" and j + 1 < len(hs) and hs[j + 1].startswith("antal")]
            res = {b: {} for b in BASKETS}
            for b, j in zip(BASKETS, pairs):
                for r in rows[i + 1:]:
                    if j < len(r) and r[j] not in (None, ""):
                        q = _f(r[j + 1]) or 0.0
                        a = _code(r[j])
                        res[b][a] = res[b].get(a, 0.0) + q
            out.append(("antal_salda", res))
            continue
        # ---- Korgfiler per segment (R12)
        h = _find_header(rows, ["artikelnr", "brv % akt r12"])
        if h:
            i, c = h
            seg = {}
            for r in rows[i + 1:]:
                a = _code(r[c["artikelnr"]]) if c["artikelnr"] < len(r) else ""
                if not a or a in ("TOTALER", "DELTOTALER"):
                    continue
                j = _col(c, "netto fsg total akt r12")
                seg[a] = {"netto": _f(r[j]) if j is not None else None, "brv": (_f(r[c["brv % akt r12"]]) or 0) / 100,
                          "antal": _f(r[_col(c, "antal total akt r12")]) if _col(c, "antal total akt r12") is not None else None}
            label = re.sub(r"\.(xlsx|xlsm|xls|csv)$", "", fname, flags=re.I).strip() or title
            out.append(("segment", {"name": label, "rows": seg}))
            continue
        # ---- Försäljningsvillkor (månadspris/kvartalspris)
        h = _find_header(rows, ["grupp", "rörligt"])
        if h:
            i, c = h
            mon = {}
            for r in rows[i + 1:]:
                if r and r[0]:
                    mon[_code(r[0])] = str(r[1] or "").strip() or "Månadspris"
            out.append(("forsaljningsvillkor", mon))
            continue
        # ---- Leverantörernas prisförändringar
        h = _find_header(rows, ["leverantör", "prisförändring"], scan=30)
        if h:
            i, c = h
            info = []
            for r in rows[i + 1:]:
                lj = _col(c, "leverantör")
                if lj is None or lj >= len(r) or not r[lj]:
                    continue
                info.append({"leverantor": str(r[lj]).strip(), "change": _f(r[_col(c, "prisförändring")]),
                             "volym": str(r[_col(c, "volym")] or "").strip() if _col(c, "volym") is not None else "",
                             "kommentar": str(r[_col(c, "kommentar")] or "").strip() if _col(c, "kommentar") is not None else ""})
            if info:
                out.append(("leverantorsinfo", info))
            continue
        # ---- Justeringsvy: gamla rabatter och sparade justeringar
        if t == "justeringsvy":
            h = _find_header(rows, ["kalkgr ny", "rabatt ny", "rabatt nu"], scan=12)
            if h:
                i, c = h
                old, adj = {}, {}
                jo = _col(c, "gml rabatter")
                for r in rows[i + 1:]:
                    kg = _code(r[c["kalkgr ny"]]) if c["kalkgr ny"] < len(r) else ""
                    if not re.fullmatch(r"[A-Z]{2}\d{4}", kg or ""):
                        continue
                    ny, nu = _f(r[c["rabatt ny"]]), _f(r[c["rabatt nu"]])
                    if ny is not None and nu is not None and abs(ny - nu) > 1e-9:
                        adj[kg] = ny
                    if jo is not None and jo < len(r) and _f(r[jo]) is not None:
                        old[kg] = _f(r[jo])
                out.append(("justeringsvy", {"adjustments": adj, "gamla_rabatter": old}))
            continue
    return out


def merge(inp: dict[str, Any], kind: str, content: Any) -> None:
    """Lägger in en inläst fil i underlaget."""
    arts = inp["articles"]

    def upd(src: dict[str, dict[str, Any]], keep: Iterable[str] | None = None):
        for a, v in src.items():
            d = arts.setdefault(a, {})
            for k, x in v.items():
                if x is None or x == "":
                    continue
                if keep and k in keep and d.get(k):
                    continue
                d[k] = x

    def mark(src, priced: bool):
        for a in src:
            if priced:
                arts[a]["priced"] = True
            elif "priced" not in arts[a]:
                arts[a]["priced"] = False          # bara i prisgrunden/registret: räknas inte (som i Excel)

    if kind == "nya_priser":
        upd(content["articles"])
        mark(content["articles"], True)
        inp["group_names"].update(content["names"])
    elif kind == "artikelbas":
        upd(content["articles"])
        mark(content["articles"], True)
        for k, v in content["names"].items():
            inp["group_names"].setdefault(k, v)
    elif kind == "bruttolista":
        upd(content["articles"], keep=("kg_nu", "namn", "brutto_nu"))
        mark(content["articles"], True)
    elif kind == "prisgrund":
        upd(content["articles"], keep=("kg_nu", "namn", "pg_nu"))
        mark(content["articles"], False)
        for k, v in content["names"].items():
            inp["group_names"].setdefault(k, v)
    elif kind == "artikeldata":
        # artikelregistret ger hierarkin; prisunderlagets uppgifter (anskaffning, leverantör) går före
        for a, v in content["articles"].items():
            d = arts.get(a)
            if d is None or d.get("pg_nu") is None:
                d = arts.setdefault(a, {})
                d.setdefault("priced", False)
                for k, x in v.items():
                    if x not in (None, "") and not d.get(k):
                        d[k] = x
            else:
                if v.get("kg_master"):
                    d["kg_master"] = v["kg_master"]
                if not d.get("namn") and v.get("namn"):
                    d["namn"] = v["namn"]
        inp["hierarchy"].update(content["hierarchy"])
        for k, v in content["names"].items():
            inp["group_names"].setdefault(k, v)
    elif kind == "rabattbrev":
        inp["rabattbrev"] = content["rab"]
        for k, v in content["names"].items():
            inp["group_names"].setdefault(k, v)
    elif kind == "kundunika":
        inp["kund_bp"].update(content["bp"])
        inp["kund_netto"].update(content["netto"])
    elif kind == "bonus":
        inp["bonus"] = content
    elif kind == "stottningar":
        inp["support"] = content
    elif kind == "antal_salda":
        for b in BASKETS:
            if content.get(b):
                inp["baskets"][b] = content[b]
    elif kind == "segment":
        inp["segments"][content["name"]] = content["rows"]
    elif kind == "forsaljningsvillkor":
        inp["monthly"] = content
    elif kind == "leverantorsinfo":
        inp["supplier_info"] = content
    elif kind == "justeringsvy":
        inp["gamla_rabatter"].update(content["gamla_rabatter"])
    for a in arts.values():
        if not a.get("kg_ny") and a.get("kg_nu"):
            a["kg_ny"] = a["kg_nu"]
        if not a.get("kg_nu") and a.get("kg_master"):
            a["kg_nu"] = a["kg_master"]


def status(inp: dict[str, Any]) -> dict[str, Any]:
    arts = inp["articles"]
    priced = lambda a: a is not None and a.get("priced") is not False and (a.get("pg_nu") is not None or a.get("brutto_nu"))
    return {
        "missing_in_price_base": {b: sum(1 for k, q in (inp["baskets"].get(b) or {}).items() if q and not priced(arts.get(k)))
                                  for b in BASKETS},
        "articles": len(arts), "with_pg": sum(1 for a in arts.values() if a.get("pg_nu") is not None),
        "with_brutto_nu": sum(1 for a in arts.values() if a.get("brutto_nu")),
        "with_brutto_ny": sum(1 for a in arts.values() if a.get("brutto_ny") is not None),
        "rabattbrev": len(inp["rabattbrev"]), "kund_bp": len(inp["kund_bp"]), "kund_netto": len(inp["kund_netto"]),
        "bonus_scenarios": len(inp["bonus"]["nu"]["scenarios"]), "support": len(inp["support"]),
        "monthly": len(inp["monthly"]), "baskets": {b: len(inp["baskets"].get(b) or {}) for b in BASKETS},
        "segments": {k: len(v) for k, v in (inp.get("segments") or {}).items()},
        "supplier_info": len(inp.get("supplier_info") or []), "hierarchy": len(inp.get("hierarchy") or {}),
        "gamla_rabatter": len(inp.get("gamla_rabatter") or {}),
    }


WORKBOOK_SHEETS = ("Nya priser", "Rabattbrev", "Kundunika BP & Nettopriser", "Bonusförutsättningar", "Stöttningar",
                   "Antal sålda", "Försäljningsvillkor", "Justeringsvy", "Blad2")


def parse_workbook_path(path: str, progress=None) -> list[tuple[str, Any]]:
    """Den befintliga Excel-filen (.xlsm) för prisförhandlingen: indatabladen och artikelbasen ur Varukorgsanalys.

    Läses strömmande och blad för blad - de beräknade bladen (Varukorgsanalys är ensamt över en gigabyte XML)
    läses bara i de kolumner som är indata (A-S)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    names = {ws.title.strip(): ws.title for ws in wb.worksheets}
    out: list[tuple[str, Any]] = []
    for want in WORKBOOK_SHEETS:
        real = names.get(want)
        if not real:
            continue
        if progress:
            progress(f"Läser {want}")
        ws = wb[real]
        rows = [list(r) for r in ws.iter_rows(values_only=True, max_col=80 if want == "Justeringsvy" else 30)]
        out += parse_sheets({real: rows}, "")
    real = names.get("Varukorgsanalys")
    if real:
        if progress:
            progress("Läser artikelbasen ur Varukorgsanalys")
        rows = [list(r) for r in wb[real].iter_rows(values_only=True, max_col=19)]
        out += parse_sheets({"Varukorgsanalys": rows}, "")
    wb.close()
    return out
