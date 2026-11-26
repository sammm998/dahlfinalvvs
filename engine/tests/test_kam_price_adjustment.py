"""KAM - prisjustering för KAM-kund: samma räkning som Dahlmenyns FrmPrisJusteringKund, simulerad utan M3."""
import io

import openpyxl
import pytest

from vvs_engine import kam as K

PRICES = {"1001": {"pris": 1000.0, "grupp": "HA1413", "namn": "Rör A", "enhet": "M"},
          "1002": {"pris": 200.0, "grupp": "HA1420", "namn": "Böj B", "enhet": "STK"},
          "2001": {"pris": 500.0, "grupp": "CC2410", "namn": "Blandare C", "enhet": "STK"}}
MATRIX = {"HA1413": 40.0, "HA1420": 30.0, "CC2410": 20.0}
STATS = [{"rsk": "1001", "antal": 10, "cp": 450.0}, {"rsk": "1002", "antal": 20, "cp": 120.0},
         {"rsk": "2001", "antal": 4, "cp": 300.0}]


def test_net_is_cascaded_discounts_like_m3():
    assert K.net(1000, 40) == 600
    assert K.net(1000, 40, 10) == pytest.approx(540)
    assert K.net(None, 10) is None


def test_matrix_lookup_6_before_4_before_2():
    groups = {"HA": 10.0, "HA14": 20.0, "HA1413": 30.0}
    assert K.lookup(groups, "HA1413") == (30.0, "HA1413")
    assert K.lookup(groups, "HA1499") == (20.0, "HA14")
    assert K.lookup(groups, "HA2000") == (10.0, "HA")
    assert K.lookup(groups, "CC2410") == (None, None)


def test_simulation_with_matrix_only_has_no_change():
    sim = K.simulate(STATS, PRICES, MATRIX)
    t = sim["totals"]
    assert t["old"] == t["new"] == 10 * 600 + 20 * 140 + 4 * 400
    assert t["change_pct"] == 0 and sim["approval_level"] == "SÄLJARE"
    ln = next(x for x in sim["lines"] if x["rsk"] == "1001")
    assert ln["hbv_avtal"] == pytest.approx(25.0) and ln["source"] == "Matris HA1413"


def test_customer_deviation_and_extra_discount_change_price_and_margin():
    cust = {"rabatter": {"HA": 45.0}}
    sim = K.simulate(STATS, PRICES, MATRIX, customer=cust,
                     proposal={"avvikelser": {"HA1413": 42.0}, "extra": 2.0})
    a = next(x for x in sim["lines"] if x["rsk"] == "1001")
    b = next(x for x in sim["lines"] if x["rsk"] == "1002")
    assert a["old_net"] == pytest.approx(550) and a["new_net"] == pytest.approx(1000 * 0.58 * 0.98)
    assert b["source"] == "Kundavvikelse HA" and b["new_net"] == pytest.approx(200 * 0.55 * 0.98)
    assert {r["kg"]: r["ny_rab"] for r in sim["changes"]["avvikelser"]} == {"HA1413": 42.0}
    assert [r["kg"] for r in sim["changes"]["kvarstaende"]] == ["HA"]
    assert sim["changes"]["extra"] == {"tid": 0.0, "ny": 2.0}
    assert {g["key"] for g in sim["per_omr"]} == {"HA", "CC"}
    assert {g["key"] for g in sim["per_kg"]} == {"HA1413", "HA1420", "CC2410"}


def test_margin_floor_needs_sales_manager_and_below_cost_blocks():
    sim = K.simulate(STATS, PRICES, MATRIX, proposal={"avvikelser": {"CC": 38.0}})   # 310 kr mot CP 300
    assert "UNDER_MARGINGOLV" in next(x for x in sim["lines"] if x["rsk"] == "2001")["flags"]
    assert sim["approval_level"] == "SÄLJLEDARE"
    sim = K.simulate(STATS, PRICES, MATRIX, proposal={"avvikelser": {"CC": 45.0}})   # 275 kr < CP 300
    assert sim["totals"]["under_cost"] == ["2001"] and sim["approval_level"] == "BLOCKERAD"


def test_net_price_goes_before_discount_and_can_be_removed():
    sim = K.simulate(STATS, PRICES, MATRIX, customer={"netto": {"1002": 150.0}}, proposal={"netto": {"1002": 160.0}})
    b = next(x for x in sim["lines"] if x["rsk"] == "1002")
    assert b["old_net"] == 150 and b["new_net"] == 160 and b["source"] == "Nettopris"
    sim = K.simulate(STATS, PRICES, MATRIX, customer={"netto": {"1002": 150.0}}, proposal={"netto": {"1002": None}})
    assert next(x for x in sim["lines"] if x["rsk"] == "1002")["new_net"] == pytest.approx(140)


def test_index_simulation_and_current_discount_kept_from_statistics():
    stats = [{"rsk": "9999", "antal": 2, "brutto": 1000.0, "r1": 10.0, "netto": 900.0, "grupp": "BC1110", "cp": 700.0}]
    sim = K.simulate(stats, {}, {}, proposal={"price_source": "index", "list_change_pct": 5})
    ln = sim["lines"][0]
    assert ln["new_bp"] == pytest.approx(1050) and ln["new_net"] == pytest.approx(945)
    assert ln["source"] == "Nuvarande rabatt" and "SIMULERAT_LISTPRIS" in ln["flags"]
    assert sim["totals"]["change_pct"] == pytest.approx(5.0)


def test_statistics_are_read_from_a_dahlmenyn_offer_sheet():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Offert"
    ws.append(["Artnr", "Ant", "Benämning           Dahl  , BP", "Brutto", "R1", "R2", "Netto", "Enh", "Total",
               "Kalk.gr", "Cp", "HBRV%"])
    ws.append([None, None, "Vi är glada att offerera"])
    ws.append(["8311260", 2, "KÖKBLANDARE", 3520, 6.2, None, 3301.76, "STK", 6603.52, "CX2420", 2686.57, 18.6])
    ws.append(["8311260", 1, "KÖKBLANDARE", 3520, 6.2, None, 3301.76, "STK", 3301.76, "CX2420", 2686.57, 18.6])
    ws.append(["56000-VVX201", None, "Rubrik"])
    buf = io.BytesIO()
    wb.save(buf)
    st = K.statistics_from_xlsx(buf.getvalue())
    assert len(st) == 1 and st[0]["antal"] == 3 and st[0]["grupp"] == "CX2420" and st[0]["cp"] == pytest.approx(2686.57)


@pytest.mark.parametrize("kind,first", [("analys", "Summering"), ("registrering", "Registreringsunderlag"),
                                        ("kund", "Prisjustering")])
def test_exports(kind, first):
    sim = K.simulate(STATS, PRICES, MATRIX, proposal={"avvikelser": {"HA1413": 42.0}})
    wb = openpyxl.load_workbook(io.BytesIO(K.to_xlsx({"kundnr": "830102", "kundnamn": "Kund", "status": "utkast"}, sim, kind)))
    assert wb.sheetnames[0] == first
    text = " ".join(str(c) for ws in wb for r in ws.iter_rows(values_only=True) for c in r if c is not None)
    if kind == "kund":
        assert "Hbv" not in text and "CP" not in text and "450" not in text   # aldrig kostpris eller marginal till kund
    if kind == "registrering":
        assert "Säljledare" in text and "HA1413" in text


def test_service_case_flow_simulated(tmp_path_factory):
    import os
    import sys
    tmp = tmp_path_factory.mktemp("kam")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    for m in list(sys.modules):
        if m == "app" or m.startswith("app."):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app

    def xlsx(rows):
        wb = openpyxl.Workbook()
        for r in rows:
            wb.active.append(r)
        b = io.BytesIO()
        wb.save(b)
        return b.getvalue()

    pris = xlsx([["Artnr", "Benämning", "Kalkylgr", "Enh", "Bruttopris"],
                 *[[k, v["namn"], v["grupp"], v["enhet"], v["pris"]] for k, v in PRICES.items()]])
    matris = xlsx([["Prod.gr", "Benämning", "Rabatt"], *[[k, f"Grupp {k}", v] for k, v in MATRIX.items()]])
    stat = xlsx([["Artnr", "Ant", "Benämning", "Kalk.gr", "Cp"], ["1001", 10, "Rör A", "HA1413", 450],
                 ["1002", 20, "Böj B", "HA1420", 120], ["2001", 4, "Blandare C", "CC2410", 300]])
    XL = "application/octet-stream"
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "kam@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        A = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "chef@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        from app.db import SessionLocal, User
        db = SessionLocal()
        db.query(User).filter(User.email == "chef@dahl.se").first().role = "admin"
        db.query(User).filter(User.email == "kam@dahl.se").first().role = "admin"     # även en admin-säljare
        db.commit()
        db.close()
        # prisfilen: två flikar som i "Prisfil för test", plus matrisen som egen fil
        wb = openpyxl.load_workbook(io.BytesIO(pris))
        ws2 = wb.create_sheet("Grupper_rabatter")
        for r in openpyxl.load_workbook(io.BytesIO(matris)).active.iter_rows(values_only=True):
            ws2.append(list(r))
        b = io.BytesIO()
        wb.save(b)
        assert c.post("/api/offer-data/prislista", files={"file": ("prisfil.xlsx", b.getvalue(), XL)}, headers=A).status_code == 200
        st = c.get("/api/kam/status", headers=H).json()
        assert st["simulated"] and st["prislista"] == 3 and st["matris"] == 3

        assert c.post("/api/kam/cases", json={"kundnr": "x"}, headers=H).status_code == 422
        assert c.post("/api/kam/cases", json={"kundnr": "830102", "new_period": "2613"}, headers=H).status_code == 422
        case = c.post("/api/kam/cases", json={"kundnr": "830102", "old_period": "2601", "new_period": "2701"}, headers=H).json()
        cid = case["id"]
        assert case["rabattsystem"] == "KAM12" and case["simulation"] is None
        assert c.post(f"/api/kam/cases/{cid}/submit", headers=H).status_code == 409          # ingen statistik ännu
        r = c.post(f"/api/kam/cases/{cid}/statistics", files={"file": ("stat.xlsx", stat, XL)}, headers=H)
        assert r.status_code == 200, r.text
        sim = r.json()["simulation"]
        assert sim["totals"]["old"] == sim["totals"]["new"] == 10 * 600 + 20 * 140 + 4 * 400

        assert c.put(f"/api/kam/cases/{cid}/proposal", json={"avvikelser": {"HA141": 10}}, headers=H).status_code == 422
        bad = c.put(f"/api/kam/cases/{cid}/proposal", json={"avvikelser": {"CC": 45}}, headers=H).json()
        assert bad["simulation"]["approval_level"] == "BLOCKERAD"
        assert c.post(f"/api/kam/cases/{cid}/submit", headers=H).status_code == 409
        ok = c.put(f"/api/kam/cases/{cid}/proposal", json={"avvikelser": {"HA1413": 42, "CC": 38}, "extra": 1}, headers=H).json()
        assert ok["simulation"]["approval_level"] == "SÄLJLEDARE"
        assert c.post(f"/api/kam/cases/{cid}/submit", headers=H).json()["status"] == "attest"
        assert c.put(f"/api/kam/cases/{cid}/proposal", json={}, headers=H).status_code == 409
        assert c.post(f"/api/kam/cases/{cid}/approve", json={}, headers=H).status_code == 403   # säljaren attesterar inte själv
        assert c.post(f"/api/kam/cases/{cid}/register", headers=A).status_code == 409
        assert c.post(f"/api/kam/cases/{cid}/approve", json={"comment": "ok"}, headers=A).json()["status"] == "godkand"
        for kind in ("analys", "registrering", "kund"):
            x = c.get(f"/api/kam/cases/{cid}/export.xlsx?kind={kind}", headers=H)
            assert x.status_code == 200 and f"KAM_830102_{kind}_" in x.headers["content-disposition"]
        reg = c.post(f"/api/kam/cases/{cid}/register", headers=A).json()
        assert reg["status"] == "registrerad" and reg["terms"]["rabatter"] == {"HA1413": 42.0, "CC": 38.0}
        assert reg["terms"]["extra"] == 1.0
        assert c.get("/api/customers/830102", headers=H).json()["rabatter"]["HA1413"] == 42.0   # gäller i offerterna
        assert c.delete(f"/api/kam/cases/{cid}", headers=H).status_code == 409
        other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "annan@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        assert c.get(f"/api/kam/cases/{cid}", headers=other).status_code == 404
        assert len(c.get("/api/kam/cases", headers=A).json()["cases"]) == 1
        assert c.get("/api/kam/cases", headers=other).json()["cases"] == []
