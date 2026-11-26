"""KAM - prisjustering för KAM-kund (ersätter Dahlmenyns FrmPrisJusteringKund).

Flödet i dag (Excel/VBA mot M3): kundens köpta artiklar de senaste 12 månaderna hämtas med antal och
kostpris (CP), prislistans bruttopris (BP) vid gammalt och nytt prisdatum, kundens rabatter R1/R2/R3.
Nettot räknas BP x (100-R1)(100-R2)(100-R3), summeras per kalkylgrupp (6 tecken), produktgrupp (4) och
produktområde (2), och visar Ändr % och bruttovinst (Hbv%) på avtal, nytt och matris. Säljaren justerar
kundavvikelser per kalkylgrupp och extrarabatt; ett registreringsunderlag (rabattsystem KAM12/VVSKAM)
attesteras av säljare och säljledare och registreras i M3; kunden får en utskrift utan CP och marginal.

Här görs samma räkning deterministiskt. Ingen skarp koppling finns: statistiken kommer ur en uppladdad
fil (Dahlmenyns offertfil eller en enkel tabell), prislistan och grundrabatterna (matrisen) ur prisfilen,
och registreringen skriver kundens rabatter i tjänstens egna rabattdata i stället för M3.
"""
from __future__ import annotations

import io
import re
from typing import Any, Iterable

RULE_VERSION = "kam-prisjustering-0.1-simulerad"
LEVELS = (6, 4, 2)
DEFAULT_MARGIN_FLOOR = 10.0          # Hbv% under detta kräver säljledarens attest
SYSTEMS = {"DAHL12": "KAM12", "VVSC12": "VVSKAM"}


def _f(v) -> float | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if s.count(",") == 1 and s.count(".") >= 1:
        s = s.replace(".", "")
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def net(bp: float | None, *rabs: float | None) -> float | None:
    if bp is None:
        return None
    v = bp
    for r in rabs:
        v *= (100 - (r or 0)) / 100
    return v


def margin(price: float | None, cp: float | None) -> float | None:
    if price in (None, 0) or cp is None:
        return None
    return 100 * (price - cp) / price


def lookup(groups: dict[str, float], kg: str) -> tuple[float | None, str | None]:
    """Rabatt för kalkylgruppen: 6 tecken går före 4, som går före 2 (som matrisen i M3)."""
    kg = (kg or "").strip().upper()
    for n in LEVELS:
        k = kg[:n]
        if len(k) == n and k in groups:
            return groups[k], k
    return None, None


# ---------------------------------------------------------------- statistik (simulerad Y12MAN)

_HEAD = {
    "rsk": ("artnr", "art.nr", "artikelnr", "artikel", "rsk", "rsknr", "rsk-nr", "itno"),
    "antal": ("ant", "antal", "kvantitet", "fakturerad kvantitet", "antal 12 mån", "ivqt"),
    "namn": ("benämning", "benämn", "namn"),
    "brutto": ("brutto", "bruttopris", "prisl bp", "bp"),
    "r1": ("r1",), "r2": ("r2",), "r3": ("r3",),
    "netto": ("netto", "nettopris", "tot bp"),
    "grupp": ("kalk.gr", "kalkylgr", "kalkylgrupp", "pr.gr.", "pr.gr", "prod.gr", "rabattgrupp"),
    "cp": ("cp", "kostpris", "inköpspris", "inkopspris"),
    "enhet": ("enh", "enhet"),
}


def _match_head(cell: str) -> str | None:
    h = re.sub(r"\s+", " ", str(cell or "").strip().lower())
    for k, names in _HEAD.items():
        if h in names or any(h.startswith(n + " ") or h.startswith(n + ",") for n in names if len(n) > 2):
            return k
    return None


def statistics_from_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Artikelrader ur en tabell (Dahlmenyns offertflik eller en egen statistikfil)."""
    head, cols = None, {}
    for i, r in enumerate(rows[:30]):
        found: dict[str, int] = {}
        for j, c in enumerate(r):
            k = _match_head(c)
            if k and k not in found:
                found[k] = j
        if "rsk" in found and "antal" in found:
            head, cols = i, found
            break
    if head is None:
        return []
    out: dict[str, dict[str, Any]] = {}
    for r in rows[head + 1:]:
        g = {k: (r[j] if j < len(r) else None) for k, j in cols.items()}
        rsk = re.sub(r"\.0$", "", str(g.get("rsk") or "").strip())
        qty = _f(g.get("antal"))
        if not rsk or not re.match(r"^[A-Z0-9][\w\-]{2,}$", rsk, re.I) or not qty:
            continue
        rec = out.setdefault(rsk, {"rsk": rsk, "antal": 0.0, "namn": str(g.get("namn") or "").strip(),
                                   "grupp": str(g.get("grupp") or "").strip().upper(), "enhet": str(g.get("enhet") or "").strip(),
                                   "brutto": _f(g.get("brutto")), "r1": _f(g.get("r1")), "r2": _f(g.get("r2")),
                                   "r3": _f(g.get("r3")), "netto": _f(g.get("netto")), "cp": _f(g.get("cp"))})
        rec["antal"] += qty
    return list(out.values())


def statistics_from_xlsx(data: bytes) -> list[dict[str, Any]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    names = [ws.title for ws in wb.worksheets]
    order = sorted(names, key=lambda n: (n.lower() not in ("offert", "statistik", "artiklar"), names.index(n)))
    for n in order:
        rows = [list(r) for r in wb[n].iter_rows(values_only=True)]
        st = statistics_from_rows(rows)
        if st:
            return st
    return []


# ---------------------------------------------------------------- simulering

def simulate(stats: Iterable[dict[str, Any]], prices: dict[str, dict[str, Any]], matrix: dict[str, float],
             customer: dict[str, Any] | None = None, proposal: dict[str, Any] | None = None,
             cost: dict[str, float] | None = None, group_names: dict[str, str] | None = None) -> dict[str, Any]:
    """Prisjusteringen för en kund.

    stats     kundens artiklar: rsk, antal, [grupp, brutto, r1, r2, r3, netto, cp]  (gammalt pris = statistiken)
    prices    ny prislista per rsk: pris (BP), grupp, namn, enhet
    matrix    grundrabatt (matris) per kalkylgrupp
    customer  nuvarande avtal: rabatter (kundavvikelser per grupp), netto (nettopris per rsk), extra (R2 %)
    proposal  ändringen: avvikelser {grupp: % eller None för att ta bort}, extra %, netto {rsk: pris},
              list_change_pct (simulerad prisändring där ny prislista saknar artikeln), margin_floor
    cost      kostpris (CP) per rsk där statistiken saknar det
    """
    customer = customer or {}
    proposal = proposal or {}
    cost = cost or {}
    group_names = group_names or {}
    cur_dev = {k.upper(): v for k, v in (customer.get("rabatter") or {}).items() if v is not None}
    cur_net = dict(customer.get("netto") or {})
    cur_extra = customer.get("extra") or 0.0
    new_dev = dict(cur_dev)
    for k, v in (proposal.get("avvikelser") or {}).items():
        if v in (None, ""):
            new_dev.pop(k.upper(), None)
        else:
            new_dev[k.upper()] = float(v)
    new_extra = cur_extra if proposal.get("extra") in (None, "") else float(proposal["extra"])
    new_net = {**cur_net, **{k: float(v) for k, v in (proposal.get("netto") or {}).items() if v not in (None, "")}}
    for k, v in (proposal.get("netto") or {}).items():
        if v in (None, ""):
            new_net.pop(k, None)
    chg = proposal.get("list_change_pct")
    source = proposal.get("price_source") or "prisfil"      # prisfil | index
    floor = float(proposal.get("margin_floor") or DEFAULT_MARGIN_FLOOR)

    lines = []
    for s in stats:
        rsk = s["rsk"]
        p = prices.get(rsk) or {}
        kg = (p.get("grupp") or s.get("grupp") or "").upper()
        flags: list[str] = []
        # gammalt: det kunden betalar i dag
        old_bp = s.get("brutto") if s.get("brutto") is not None else p.get("pris")
        mat_old, _ = lookup(matrix, kg)
        dev_old, _ = lookup(cur_dev, kg)
        if s.get("netto") is not None:                       # det kunden faktiskt betalat
            old_r1, old_r2, old_net = s.get("r1"), s.get("r2"), s["netto"]
        elif rsk in cur_net:
            old_r1, old_r2, old_net = None, None, cur_net[rsk]
        else:
            old_r1 = dev_old if dev_old is not None else mat_old
            old_r2 = cur_extra
            old_net = net(old_bp, old_r1, old_r2)
        # nytt pris: ny prislista, annars (eller om så valts) den simulerade prisändringen
        if source == "index" and old_bp is not None:
            new_bp = old_bp * (1 + float(chg or 0) / 100)
            flags.append("SIMULERAT_LISTPRIS")
        elif p.get("pris") is not None:
            new_bp = p["pris"]
        elif old_bp is not None and chg not in (None, ""):
            new_bp = old_bp * (1 + float(chg) / 100)
            flags.append("SIMULERAT_LISTPRIS")
        else:
            new_bp = old_bp
            flags.append("SAKNAS_I_NY_PRISLISTA")
        mat, mat_level = lookup(matrix, kg)
        dev, dev_level = lookup(new_dev, kg)
        if rsk in new_net:
            r1, r2, nnet, src = None, None, new_net[rsk], "Nettopris"
        else:
            keep = dev is None and s.get("r1") is not None
            r1 = dev if dev is not None else (s["r1"] if keep else mat)
            r2 = new_extra if new_extra else (s.get("r2") if keep else new_extra)
            nnet = net(new_bp, r1, r2)
            src = (f"Kundavvikelse {dev_level}" if dev is not None else "Nuvarande rabatt" if keep
                   else f"Matris {mat_level}" if mat is not None else "Ingen rabatt")
        cp = s.get("cp") if s.get("cp") is not None else cost.get(rsk)
        mat_net = net(new_bp, mat)
        m_new = margin(nnet, cp)
        if cp is None:
            flags.append("CP_SAKNAS")
        if nnet is not None and cp is not None and nnet < cp:
            flags.append("UNDER_KOSTPRIS")
        elif m_new is not None and m_new < floor:
            flags.append("UNDER_MARGINGOLV")
        lines.append({
            "omr": kg[:2], "pgr": kg[:4], "kg": kg, "rsk": rsk, "namn": p.get("namn") or s.get("namn") or "",
            "antal": s["antal"], "enhet": p.get("enhet") or s.get("enhet") or "", "cp": cp,
            "old_bp": old_bp, "old_r1": old_r1, "old_r2": old_r2, "old_net": old_net,
            "new_bp": new_bp, "matris": mat, "new_r1": r1, "new_r2": r2, "new_net": nnet, "source": src,
            "change_pct": None if not old_net or nnet is None else 100 * (nnet - old_net) / old_net,
            "hbv_avtal": margin(old_net, cp), "hbv_nytt": m_new, "hbv_matris": margin(mat_net, cp),
            "flags": flags,
        })

    def agg(key: str) -> list[dict[str, Any]]:
        g: dict[str, dict[str, Any]] = {}
        for ln in lines:
            k = ln[key] or "-"
            a = g.setdefault(k, {"key": k, "name": group_names.get(k, ""), "rows": 0, "old": 0.0, "new": 0.0,
                                 "matris": 0.0, "cp": 0.0, "cp_known_old": 0.0, "cp_known_new": 0.0,
                                 "cp_known_mat": 0.0, "flags": set()})
            q = ln["antal"]
            a["rows"] += 1
            a["old"] += (ln["old_net"] or 0) * q
            a["new"] += (ln["new_net"] or 0) * q
            mn = net(ln["new_bp"], ln["matris"])
            a["matris"] += (mn or 0) * q
            if ln["cp"] is not None:
                a["cp"] += ln["cp"] * q
                a["cp_known_old"] += (ln["old_net"] or 0) * q
                a["cp_known_new"] += (ln["new_net"] or 0) * q
                a["cp_known_mat"] += (mn or 0) * q
            a["flags"].update(f for f in ln["flags"] if f in ("UNDER_KOSTPRIS", "UNDER_MARGINGOLV"))
        out = []
        for a in sorted(g.values(), key=lambda x: x["key"]):
            m = lambda tot: None if not tot else 100 * (tot - a["cp"]) / tot
            out.append({"key": a["key"], "name": a["name"], "rows": a["rows"], "old": round(a["old"], 2),
                        "new": round(a["new"], 2), "change_pct": None if not a["old"] else round(100 * (a["new"] - a["old"]) / a["old"], 2),
                        "hbv_avtal": _r(m(a["cp_known_old"])), "hbv_nytt": _r(m(a["cp_known_new"])),
                        "hbv_matris": _r(m(a["cp_known_mat"])), "flags": sorted(a["flags"])})
        return out

    tot_old = sum((ln["old_net"] or 0) * ln["antal"] for ln in lines)
    tot_new = sum((ln["new_net"] or 0) * ln["antal"] for ln in lines)
    cp_lines = [ln for ln in lines if ln["cp"] is not None]
    cp_tot = sum(ln["cp"] * ln["antal"] for ln in cp_lines)
    old_k = sum((ln["old_net"] or 0) * ln["antal"] for ln in cp_lines)
    new_k = sum((ln["new_net"] or 0) * ln["antal"] for ln in cp_lines)
    blocking = [ln["rsk"] for ln in lines if "UNDER_KOSTPRIS" in ln["flags"]]
    below = [ln["rsk"] for ln in lines if "UNDER_MARGINGOLV" in ln["flags"]]
    totals = {
        "rows": len(lines), "old": round(tot_old, 2), "new": round(tot_new, 2),
        "change_pct": None if not tot_old else round(100 * (tot_new - tot_old) / tot_old, 2),
        "hbv_avtal": _r(margin(old_k, cp_tot) if cp_lines else None),
        "hbv_nytt": _r(margin(new_k, cp_tot) if cp_lines else None),
        "rows_without_cp": len(lines) - len(cp_lines),
        "rows_simulated_price": sum(1 for ln in lines if "SIMULERAT_LISTPRIS" in ln["flags"]),
        "rows_missing_in_new_list": sum(1 for ln in lines if "SAKNAS_I_NY_PRISLISTA" in ln["flags"]),
        "under_cost": blocking, "under_floor": below, "margin_floor": floor,
    }
    approval = "BLOCKERAD" if blocking else ("SÄLJLEDARE" if below else "SÄLJARE")
    return {"rule_version": RULE_VERSION, "lines": lines, "per_omr": agg("omr"), "per_pgr": agg("pgr"),
            "per_kg": agg("kg"), "totals": totals, "approval_level": approval,
            "new_terms": {"avvikelser": new_dev, "extra": new_extra, "netto": new_net},
            "changes": changes(cur_dev, new_dev, cur_extra, new_extra, cur_net, new_net, matrix, group_names)}


def _r(v):
    return None if v is None else round(v, 2)


def changes(cur_dev, new_dev, cur_extra, new_extra, cur_net, new_net, matrix, names) -> dict[str, Any]:
    """Registreringsunderlaget: ändrade och kvarstående kundavvikelser, extrarabatt och nettopriser."""
    rows, keep = [], []
    for k in sorted(set(cur_dev) | set(new_dev)):
        mat, _ = lookup(matrix, k)
        r = {"kg": k, "name": names.get(k, ""), "prio": len(k), "tid_rab": cur_dev.get(k), "ny_rab": new_dev.get(k),
             "matris": mat}
        (rows if cur_dev.get(k) != new_dev.get(k) else keep).append(r)
    nets = [{"rsk": k, "tid": cur_net.get(k), "ny": new_net.get(k)} for k in sorted(set(cur_net) | set(new_net))
            if cur_net.get(k) != new_net.get(k)]
    return {"avvikelser": rows, "kvarstaende": keep, "netto": nets,
            "extra": None if cur_extra == new_extra else {"tid": cur_extra, "ny": new_extra}}


# ---------------------------------------------------------------- Excel

def to_xlsx(case: dict[str, Any], sim: dict[str, Any], kind: str = "analys") -> bytes:
    """analys (internt, med CP och Hbv%), registrering (attestunderlag) eller kund (utan CP och marginal)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws0 = wb.active
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")
    sim_note = "SIMULERAD - ingen M3-koppling. Statistik, prislista och matris ur uppladdade filer."

    def sheet(ws, title, head, rows, meta=()):
        ws.title = title
        for m in meta:
            ws.append(list(m))
        if meta:
            ws.append([])
        ws.append(head)
        for c in ws[ws.max_row]:
            c.font, c.fill = bold, fill
        for r in rows:
            ws.append([round(v, 2) if isinstance(v, float) else v for v in r])
        for i in range(1, len(head) + 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = 14
        return ws

    meta = [("Kund", case.get("kundnr"), case.get("kundnamn")), ("Rabattsystem", case.get("rabattsystem")),
            ("Prisdatum gammalt/nytt", case.get("old_period"), case.get("new_period")), ("Status", case.get("status")),
            ("Regelversion", sim["rule_version"]), ("Obs", sim_note)]
    t = sim["totals"]
    if kind == "kund":
        sheet(ws0, "Prisjustering", ["Kalkylgrupp", "Benämning", "R1 %", "R2 %"],
              [[g["kg"], g["name"], g["ny_rab"], None] for g in sim["changes"]["avvikelser"] if g["ny_rab"] is not None]
              + [[g["kg"], g["name"], g["tid_rab"], None] for g in sim["changes"]["kvarstaende"]]
              + ([["Extrarabatt", "", None, sim["new_terms"]["extra"]]] if sim["new_terms"]["extra"] else []),
              meta=meta[:3])
        if sim["changes"]["netto"]:
            sheet(wb.create_sheet(), "Nettopriser", ["Artikel", "Nettopris"],
                  [[n["rsk"], n["ny"]] for n in sim["changes"]["netto"] if n["ny"] is not None])
    elif kind == "registrering":
        c = sim["changes"]
        sheet(ws0, "Registreringsunderlag", ["Kalkgrp", "Benämning", "Prio", "Tid rab", "Ny rab", "Matris"],
              [[r["kg"], r["name"], r["prio"], r["tid_rab"], r["ny_rab"], r["matris"]] for r in c["avvikelser"]],
              meta=meta + [("Underlag för registrering av rabatter",), ("Ändring kundavvikelser",)])
        ws0.append([])
        ws0.append(["Ändring extrarabatt", (c["extra"] or {}).get("tid"), (c["extra"] or {}).get("ny")])
        ws0.append([])
        ws0.append(["Följande kundavvikelser kvarstår sedan tidigare"])
        for r in c["kvarstaende"]:
            ws0.append([r["kg"], r["name"], r["prio"], r["tid_rab"], r["tid_rab"], r["matris"]])
        if c["netto"]:
            ws0.append([])
            ws0.append(["Ändrade nettopriser", "Tid netto", "Ny netto"])
            for n in c["netto"]:
                ws0.append([n["rsk"], n["tid"], n["ny"]])
        ws0.append([])
        ws0.append(["Attesteras:"])
        ws0.append(["Säljare:", case.get("attest_saljare") or ""])
        ws0.append(["Säljledare:", case.get("attest_saljledare") or ""])
        ws0.append(["Attestnivå som krävs:", sim["approval_level"]])
    else:
        sheet(ws0, "Summering", ["Nivå", "Grupp", "Benämning", "Rader", "Gammalt netto", "Nytt netto", "Ändr %",
                                 "Hbv% avtal", "Hbv% nytt", "Hbv% matris", "Flaggor"],
              [[lvl, g["key"], g["name"], g["rows"], g["old"], g["new"], g["change_pct"], g["hbv_avtal"], g["hbv_nytt"],
                g["hbv_matris"], ", ".join(g["flags"])] for lvl, key in (("Pr.omr", "per_omr"), ("Pr.gr", "per_pgr"),
                                                                       ("Kalkylgr", "per_kg")) for g in sim[key]]
              + [["Totalt", "", "", t["rows"], t["old"], t["new"], t["change_pct"], t["hbv_avtal"], t["hbv_nytt"], None,
                  f"Attest: {sim['approval_level']}"]], meta=meta)
        sheet(wb.create_sheet(), "Artiklar", ["Pr.omr", "Pr.gr", "Kalkylgr", "Rsknr", "Benämn", "Antal", "Enh", "CP",
                                              "Prisl BP gammal", "R1", "R2", "Netto gammal", "Prisl BP ny", "Matris",
                                              "R1 ny", "R2 ny", "Netto ny", "Källa", "Ändr %", "Hbv% avtal", "Hbv% nytt",
                                              "Hbv% matris", "Flaggor"],
              [[ln["omr"], ln["pgr"], ln["kg"], ln["rsk"], ln["namn"], ln["antal"], ln["enhet"], ln["cp"], ln["old_bp"],
                ln["old_r1"], ln["old_r2"], ln["old_net"], ln["new_bp"], ln["matris"], ln["new_r1"], ln["new_r2"],
                ln["new_net"], ln["source"], ln["change_pct"], ln["hbv_avtal"], ln["hbv_nytt"], ln["hbv_matris"],
                ", ".join(ln["flags"])] for ln in sim["lines"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
