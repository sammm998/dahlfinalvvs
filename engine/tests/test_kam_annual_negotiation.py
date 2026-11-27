"""KAM - årlig prisförhandling: samma räkning som arbetsboken (Justeringsvy/Varukorgsanalys), på påhittade data."""
import io
import time

import openpyxl
import pytest

from vvs_engine import kam_pricing as K


def inputs():
    inp = K.empty_inputs()
    inp["articles"] = {
        # vanlig artikel, rabatt på 6-ställig grupp
        "100": {"namn": "Rör A", "kg_nu": "HA1413", "kg_ny": "HA1413", "levnr": "L1", "levnamn": "Lev Ett", "anskaffn": "LAG",
                "pg_nu": 60.0, "pg_ny": 63.0, "brutto_nu": 100.0, "brutto_ny": 105.0},
        # byter kalkylgrupp, rabatt på 4-ställig nivå, stöttning i kronor på leverantören
        "200": {"namn": "Böj B", "kg_nu": "HA1420", "kg_ny": "HA1421", "levnr": "L2", "levnamn": "Lev Två", "anskaffn": "TRA",
                "pg_nu": 40.0, "pg_ny": 41.0, "brutto_nu": 80.0, "brutto_ny": 82.0},
        # månadspris: varken prisgrund eller brutto ändras
        "300": {"namn": "Kopparrör C", "kg_nu": "DB1010", "kg_ny": "DB1010", "levnr": "L3", "levnamn": "Lev Tre", "anskaffn": "LAG",
                "pg_nu": 50.0, "pg_ny": 55.0, "brutto_nu": 90.0, "brutto_ny": 99.0},
        # kundunikt nettopris
        "400": {"namn": "Blandare D", "kg_nu": "CC2410", "kg_ny": "CC2410", "levnr": "L4", "levnamn": "Lev Fyra", "anskaffn": "LAG",
                "pg_nu": 300.0, "pg_ny": 310.0, "brutto_nu": 600.0, "brutto_ny": 620.0},
        # kundunikt BP
        "500": {"namn": "Ventil E", "kg_nu": "CC2410", "kg_ny": "CC2410", "levnr": "L4", "levnamn": "Lev Fyra", "anskaffn": "LAG",
                "pg_nu": 20.0, "pg_ny": 21.0, "brutto_nu": 50.0, "brutto_ny": 52.0},
        # finns i korgen men saknar prisunderlag
    }
    inp["group_names"] = {"HA1413": "Rör", "HA1420": "Böjar", "HA1421": "Böjar ny", "DB1010": "Kopparrör", "CC2410": "Blandare"}
    inp["rabattbrev"] = {"HA": 20.0, "HA14": 30.0, "HA1413": 40.0, "DB": 10.0, "CC": 25.0}
    inp["kund_bp"] = {"500": (48.0, 51.0)}
    inp["kund_netto"] = {"400": (420.0, 430.0)}
    inp["bonus"] = {"nu": {"scenarios": {"Scenario 1": 0.05, "Scenario 2": 0.10}, "map": {"TRAHA": "Scenario 2", "CC": "Scenario 2"}},
                    "ny": {"scenarios": {"Scenario 1": 0.05, "Scenario 2": 0.12}, "map": {"TRAHA": "Scenario 2", "CC": "Scenario 2"}}}
    inp["support"] = [{"key": "100", "now": 0.1, "new": 0.1}, {"key": "L2", "now": 2.0, "new": 3.0}]
    inp["monthly"] = {"DB10": "Månadspris"}
    inp["baskets"] = {"kund": {"100": 10, "200": 5, "300": 2, "400": 1, "500": 4, "999": 3},
                      "riks": {"100": 100, "200": 50, "300": 20, "400": 10, "500": 40}, "korg3": {}}
    return inp


def by(rows):
    return {r["artnr"]: r for r in rows}


def test_article_formulas_follow_the_workbook():
    r = by(K.compute_articles(inputs()))
    assert "999" not in r                                         # utan prisunderlag räknas inte
    a = r["100"]
    assert a["in_nu"] == pytest.approx(54.0) and a["in_ny"] == pytest.approx(56.7)       # stöttning 10 %
    assert a["rab_nu"] == 40 and a["fn_nu"] == pytest.approx(60) and a["nn_nu"] == pytest.approx(57)   # bonus scenario 1
    assert a["fn_ny"] == pytest.approx(63) and a["nn_ny"] == pytest.approx(59.85)
    b = r["200"]
    assert b["moved"] and b["rab_nu"] == 30 and b["rab_ny"] == 30                       # HA14 på båda grupperna
    assert b["in_nu"] == pytest.approx(38.0) and b["in_ny"] == pytest.approx(38.0)      # stöttning i kronor 2 resp 3
    assert b["bonus_nu"] == 0.10 and b["bonus_ny"] == 0.12                              # anskaffning + område
    c = r["300"]
    assert c["month"] and c["pg_ny"] == 50 and c["brutto_ny"] == 90                     # månadspris: oförändrat
    d = r["400"]
    assert d["fn_nu"] == 420 and d["fn_ny"] == 430 and d["lin_a"] == 0 and d["lin_f"] == pytest.approx(430 * 0.88)
    e = r["500"]
    assert e["brutto_ny"] == 51 and e["fn_nu"] == pytest.approx(48 * 0.75) and e["fn_ny"] == pytest.approx(51 * 0.75)


def test_linear_recompute_equals_full_recompute():
    inp = inputs()
    adj = {"HA1413": 43.5, "CC2410": 22.0}
    full = K.basket_totals(K.compute_articles(inp, adj), "kund")
    grs = K.set_adjustments(K.groups(inp, K.compute_articles(inp)), adj)
    fast = K.totals(grs, "kund")
    for k in ("nn_nu", "nn_ny", "in_nu", "in_ny", "brv_nu", "brv_ny", "prisdiff", "inprisdiff"):
        assert fast[k] == pytest.approx(full[k], rel=1e-9), k


def test_groups_flags_new_group_and_moves():
    grs = {g["kg"]: g for g in K.groups(inputs(), K.compute_articles(inputs()))}
    assert grs["HA1421"]["new_group"] and grs["HA1421"]["moved"] == 1 and grs["HA1421"]["rab_level"] == "HA14"
    assert not grs["HA1413"]["new_group"] and grs["DB1010"]["month"]


def test_insights_flag_and_suggest():
    inp = inputs()
    inp["articles"]["100"]["pg_ny"] = 70.0                       # inpriset rusar: marginalen sjunker
    grs = K.groups(inp, K.compute_articles(inp))
    ins = {i["kg"]: i for i in K.insights(grs, settings={"min_volume": 0, "max_step": 20})}
    i = ins["HA1413"]
    assert "MARGINALTAPP" in {f["code"] for f in i["flags"]}
    s = i["suggestion"]
    assert s["type"] == "rabatt" and s["rab"] < 40
    g = next(g for g in grs if g["kg"] == "HA1413")
    assert K.apply_rab(g, "kund", s["rab"])["brv_ny"] == pytest.approx(K.apply_rab(g, "kund")["brv_nu"], abs=0.01)


def test_net_price_groups_get_net_price_suggestions():
    inp = inputs()
    inp["kund_netto"]["400"] = (420.0, 300.0)                    # nytt nettopris under inpris
    inp["baskets"]["kund"].pop("500")
    grs = K.groups(inp, K.compute_articles(inp))
    i = next(i for i in K.insights(grs, settings={"min_volume": 0}) if i["kg"] == "CC2410")
    assert "UNDER_KOSTPRIS" in {f["code"] for f in i["flags"]} and i["suggestion"]["type"] == "netto"
    g = K.set_adjustments(grs, netto={"CC2410": i["suggestion"]["pct"]})
    cc = next(x for x in g if x["kg"] == "CC2410")
    k = K.apply_rab(cc, "kund")
    assert k["brv_ny"] == pytest.approx(max(k["brv_nu"], 0.05), abs=1e-6)       # golvet är BRV nu, minst 5 %


def test_sales_loss_compares_share_with_national_basket():
    inp = inputs()
    inp["baskets"]["riks"]["300"] = 5000                         # riksåterförsäljarna köper mycket kopparrör
    grs = K.groups(inp, K.compute_articles(inp))
    ins = {i["kg"]: i for i in K.insights(grs, settings={"min_volume": 0})}
    assert "TAPPAR_FORSALJNING" in {f["code"] for f in ins["DB1010"]["flags"]}


def test_rabattbrev_text_round_trip():
    inp = inputs()
    grs = K.set_adjustments(K.groups(inp, K.compute_articles(inp)), {"HA1413": 41.5})
    txt = K.rabattbrev_txt(grs, inp)
    rab, names = K.parse_rabattbrev_txt(txt)
    assert rab["HA1413"] == 41.5 and rab["HA14"] == 30 and rab["HA1421"] == 30
    rab2, _ = K.parse_rabattbrev_txt("AA1010   Värmepumpar berg, jord, sjö CT29.5\nAA1011   Värmepumpar fastighet  31.0\n")
    assert rab2 == {"AA1010": 29.5, "AA1011": 31.0}


def _xlsx(sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def workbook_like():
    return {
        "Nya priser": [["Artnr", "Kalkgr NY", "Kalkgr Benämn NY", "Prisgrund nu", "Prisgrund NY", "Brutto NY"],
                       ["100", "HA1413", "Rör", 60, 63, 105], ["200", "HA1421", "Böjar ny", 40, 41, 82]],
        "Varukorgsanalys": [[], [], [], [], [], [], [], ["Artikelnr", "Benämn", "Kalkgr nu", "Kalkgr benämn nu", "Kalkgr NY",
                                                       "Kalkgr benämn NY", "Byter kalkgr", "Kalkgr NY+Byter grupp", "Levnr",
                                                       "Levnamn", "Anskaffn", "Status", "Prisgrund nu", "Prisgrund NY",
                                                       "Stöttning nu", "Stöttning NY", "Q", "R", "Brutto nu"],
                            ["100", "Rör A", "HA1413", "Rör", "HA1413", "Rör", "---", "", "L1", "Lev Ett", "LAG", "20", 60, 63, 0, 0, 0, 0, 100],
                            ["200", "Böj B", "HA1420", "Böjar", "HA1421", "Böjar ny", "JA", "", "L2", "Lev Två", "TRA", "20", 40, 41, 0, 0, 0, 0, 80]],
        "Rabattbrev": [["Rabattbrev"], ["Prodgr", "Benämn", "Rab1"], ["HA", "VVS-rör", 20], ["HA14", "Rör", 30], ["HA1413", "Rör", 40]],
        "Antal sålda": [["VARUKORG (KUND)", None, None, "VARUKORG RIKSARE"], ["Artnr", "Antal sålda", None, "Artnr", "Antal sålda"],
                        ["100", 10, None, "100", 100], ["200", 5, None, "200", 50], ["100", 2]],
        "Bonusförutsättningar": [["Bonus nu", None, None, None, None, None, None, "Bonus NY"],
                                 ["Scenario", "Bonus", "Bonusförutsättningar", None, None, None, None, "Scenario", "Bonus"],
                                 ["Scenario 1", 0.05, "Lager", None, None, None, None, "Scenario 1", 0.05],
                                 ["Scenario 2", 0.10, "TRA", None, None, None, None, "Scenario 2", 0.12],
                                 ["Avvikelse grupper", "Scenario", None, None, None, None, None, "Avvikelse grupper", "Scenario"],
                                 ["TRAHA", "Scenario 2", None, None, None, None, None, "TRAHA", "Scenario 2"]],
        "Stöttningar": [[None, None, None, "Prio 1"], ["Styrande stöttningsnivå", "Leverantörsnamn", "Sortiment", "Artikelnr", "Kalkgr",
                                                      "Levnr", "Kund", "Stöttning nu", "Stöttning NY", "Kommentar"],
                        ["100", "Lev Ett", "", "100", "", "", "ALLA", 0.1, 0.1], ["L2", "Lev Två", "Hela", "", "", "L2", "", 2, 3]],
        "Försäljningsvillkor": [["Grupp", "Rörligt (Månadspris/Kvartalspris)"], ["DB10", "Månadspris"]],
        "Kundunika BP & Nettopriser": [["Artikelnr", "Benämning", "Kundunikt BP nu", "Kundunikt BP NY", None, "Artikelnr", "Benämning",
                                        "Kundunikt Netto nu", "Kundunikt Netto NY"],
                                       ["500", "Ventil", 48, 51, None, "400", "Blandare", 420, 430],
                                       [None, None, None, None, None, "400", "Blandare", 999, 999]],
        "Justeringsvy": [[], [None, "KOMMENTARER/INFO"], [], [], [],
                         [None, "Kommentar", "Grupper", "Egen notering 2", "Nyskapad grupp (x)", "Innehåller kalkgrflyttar (x)",
                          "Rabatt NY", "Rabatt diff", "Kalkgr NY", "Kalkgr benämn NY", "Månadspris/kvartalspris", "Rabatt nu "],
                         [None, None, None, None, None, None, 42, 2, "HA1413", "Rör", "---", 40]],
        "Blad2": [[], [], [], ["Leverantör ", "Prisförändring ", "Volym Dahl R12", "Kommentar "], ["Lev Ett", 0.05, "2M", "Energi"]],
    }


def test_sheets_are_recognised_and_merged():
    inp = K.empty_inputs()
    parts = K.parse_sheets({k: v for k, v in workbook_like().items()})
    kinds = [k for k, _ in parts]
    for k in ("nya_priser", "artikelbas", "rabattbrev", "antal_salda", "bonus", "stottningar", "forsaljningsvillkor",
              "kundunika", "justeringsvy", "leverantorsinfo"):
        assert k in kinds, k
    for k, c in parts:
        K.merge(inp, k, c)
    assert inp["articles"]["200"]["kg_nu"] == "HA1420" and inp["articles"]["200"]["kg_ny"] == "HA1421"
    assert inp["articles"]["100"]["brutto_nu"] == 100 and inp["baskets"]["kund"]["100"] == 12   # dubbelrad summeras
    assert inp["kund_netto"]["400"] == (420, 430)                     # första raden gäller, som LETARAD
    assert inp["bonus"]["ny"]["scenarios"]["Scenario 2"] == 0.12 and inp["bonus"]["nu"]["map"]["TRAHA"] == "Scenario 2"
    assert dict(parts)["justeringsvy"]["adjustments"] == {"HA1413": 42.0}
    assert inp["supplier_info"][0]["change"] == 0.05


def test_customer_export_never_shows_cost_or_margin():
    inp = inputs()
    inp["supplier_info"] = [{"leverantor": "Lev Ett", "change": 0.05, "volym": "2M", "kommentar": "Energi"}]
    grs = K.set_adjustments(K.groups(inp, K.compute_articles(inp)), {"HA1413": 41})
    wb = openpyxl.load_workbook(io.BytesIO(K.to_xlsx({"customer": "Kund AB"}, inp, grs, "kund")))
    text = " ".join(str(c) for ws in wb for r in ws.iter_rows(values_only=True) for c in r if c is not None)
    assert "BRV" not in text and "Inpris" not in text and "Prisgrund" not in text and "Stöttning" not in text
    assert "Prisförändring" in text and "41" in text
    wb = openpyxl.load_workbook(io.BytesIO(K.to_xlsx({}, inp, grs, "intern", K.insights(grs, settings={"min_volume": 0}))))
    assert wb.sheetnames[:2] == ["Justeringsvy", "Sammanfattning"]


def test_service_negotiation_flow(tmp_path_factory):
    import os
    import sys
    tmp = tmp_path_factory.mktemp("kamneg")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    for m in list(sys.modules):
        if m == "app" or m.startswith("app."):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal, User

    book = _xlsx(workbook_like())
    korg = _xlsx({"Blad1": [["Artikelnr", "Artikel", "Netto FSG total Akt R12", "BRV % Akt R12", "Antal total Akt R12"],
                            ["Totaler", "Totaler", 1, 1, 1], ["100", "Rör A", 50000, 5.0, 900]]})
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "kam@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        A = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "chef@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        with SessionLocal() as db:
            db.query(User).filter(User.email == "chef@dahl.se").first().role = "admin"
            db.commit()
        assert c.post("/api/kam/negotiations", json={}, headers=H).status_code == 422
        n = c.post("/api/kam/negotiations", json={"customer": "Kund AB", "kundnr": "100001", "valid_from": "2027-02-01"}, headers=H).json()
        nid = n["id"]
        files = [("files", ("prisforhandling.xlsx", book, "application/octet-stream")),
                 ("files", ("Korg 1 B.xlsx", korg, "application/octet-stream")),
                 ("files", ("Rabattbrev kund.txt", "HA1421   Böjar ny                      33.0\r\n".encode("cp1252"), "text/plain"))]
        r = c.post(f"/api/kam/negotiations/{nid}/files", files=files, headers=H)
        assert r.status_code == 200, r.text
        for _ in range(100):
            j = c.get(f"/api/kam/negotiations/{nid}", headers=H).json()
            if j["job"].get("state") in ("done", "error"):
                break
            time.sleep(0.1)
        assert j["job"]["state"] == "done", j["job"]
        assert j["data_status"]["computed_articles"] == 2 and j["data_status"]["segments"] == {"Korg 1 B": 1}
        assert j["totals"]["kund"]["nn_nu"] > 0
        g = c.get(f"/api/kam/negotiations/{nid}/groups", headers=H).json()
        grs = {x["kg"]: x for x in g["groups"]}
        assert grs["HA1413"]["rab_ny"] == 42.0                          # justeringen ur arbetsbokens Justeringsvy
        assert g["supplier_info"][0]["leverantor"] == "Lev Ett"
        r = c.put(f"/api/kam/negotiations/{nid}/adjustments", json={"rab": {"HA1421": 35}, "comments": {"HA1421": "Kampanj"}}, headers=H)
        assert r.status_code == 200
        assert c.put(f"/api/kam/negotiations/{nid}/adjustments", json={"rab": {"HA1421": 120}}, headers=H).status_code == 422
        arts = c.get(f"/api/kam/negotiations/{nid}/groups/HA1421/articles", headers=H).json()
        assert arts["rab_ny"] == 35 and arts["articles"][0]["artnr"] == "200"
        ins = c.get(f"/api/kam/negotiations/{nid}/insights", headers=H).json()
        assert isinstance(ins["insights"], list)
        p = c.get(f"/api/kam/negotiations/{nid}/presentation", headers=H).json()
        assert p["customer"] == "Kund AB" and p["areas"][0]["omr"] == "HA" and "in_nu" not in p["totals"]
        assert any(x["kg"] == "HA1421" and x["rab_ny"] == 35 for x in p["changed_groups"])
        for kind in ("intern", "kund"):
            x = c.get(f"/api/kam/negotiations/{nid}/export.xlsx?kind={kind}", headers=H)
            assert x.status_code == 200 and "Prisjustering_Kund_AB" in x.headers["content-disposition"]
        txt = c.get(f"/api/kam/negotiations/{nid}/rabattbrev.txt", headers=H).content.decode("cp1252")
        assert "HA1421" in txt and "35.0" in txt
        assert c.post(f"/api/kam/negotiations/{nid}/submit", headers=H).json()["status"] == "attest"
        assert c.put(f"/api/kam/negotiations/{nid}/adjustments", json={"rab": {"HA1421": 36}}, headers=H).status_code == 409
        assert c.post(f"/api/kam/negotiations/{nid}/approve", json={}, headers=H).status_code == 403
        assert c.post(f"/api/kam/negotiations/{nid}/approve", json={}, headers=A).json()["status"] == "godkand"
        assert c.post(f"/api/kam/negotiations/{nid}/register", headers=A).json()["status"] == "registrerad"
        assert c.get("/api/customers/100001", headers=H).json()["rabatter"]["HA1421"] == 35
        other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "x@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        assert c.get(f"/api/kam/negotiations/{nid}", headers=other).status_code == 404


def test_rabattbrev_fixed_width_names_ending_in_digits():
    line = "GA4610   Bult & mutter Strut M10       71.0"
    assert len(line[:39]) == 39
    assert K.parse_rabattbrev_txt(line)[0] == {"GA4610": 71.0}


def test_price_basis_alone_does_not_bring_articles_into_the_basket():
    inp = inputs()
    K.merge(inp, "prisgrund", {"articles": {"999": {"namn": "Okänd", "kg_nu": "HA1413", "pg_nu": 10.0}}, "names": {}})
    assert "999" not in {r["artnr"] for r in K.compute_articles(inp)}
    K.merge(inp, "bruttolista", {"articles": {"999": {"brutto_nu": 20.0}}})
    assert "999" in {r["artnr"] for r in K.compute_articles(inp)}
