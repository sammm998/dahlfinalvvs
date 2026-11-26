"""Acceptanstester T01-T15 ur Dahl Radiator- och korsreferensagent v1.0 (Golden Standard)."""
import io
from datetime import date

import openpyxl
import pytest

from vvs_engine.radiators import golden as G

# Representativ testfil (02_Testdata_Representativ_Indata.xlsx), utan priser.
TESTDATA = [
    {"id": "TEST-001", "article": "51113041", "text": "GRAD 40 V 11-304", "qty": 2, "location": "Plan 10"},
    {"id": "TEST-002", "article": "5111311", "text": "GRAD 40 H 11-311", "qty": 1, "location": "Plan 10"},
    {"id": "TEST-003", "article": "5121304", "text": "GRAD 40 21-304", "qty": 3, "location": "Plan 11"},
    {"id": "TEST-004", "article": "5121311", "text": "GRAD 40 21-311", "qty": 5, "location": "Plan 11"},
    {"id": "TEST-005", "article": "5122212", "text": "GRAD 40 22-212", "qty": 2, "location": "Plan 12"},
    {"id": "TEST-006", "article": "51332111", "text": "GRAD 40 V 33-211", "qty": 4, "location": "Plan 12"},
    {"id": "TEST-007", "article": "5133308", "text": "GRAD 40 H 33-308", "qty": 1, "location": "Plan 13"},
    {"id": "TEST-008", "article": "51119071", "text": "GRAD 40 V 11-907", "qty": 3, "location": "Plan 13"},
    {"id": "TEST-009", "article": "TILLB-01", "text": "Termostat, exempelrad", "qty": 8, "location": "Plan 13"},
]


def one(text, qty=1, **kw):
    return G.cross_row({"id": "X", "text": text, "qty": qty, **kw})


def test_t01_exact_left():
    x = one("GRAD 40 V 11-304")
    assert (x["selected"]["model"], x["selected"]["height"], x["selected"]["length"]) == ("D11", 300, 400)
    assert x["rsk"] == "6672135" and x["length_diff_mm"] == 0 and x["power_diff_w"] == 10
    assert x["match_status"] == "EXACT_MATCH" and x["approval_status"] == "APPROVED_DIMENSION_MATCH"


def test_t02_nearest_shorter_right():
    x = one("GRAD 40 H 11-311")
    assert x["selected"]["length"] == 1000 and x["rsk"] == "6672140"
    assert x["length_diff_mm"] == -100 and x["power_diff_w"] == -2 and x["match_status"] == "NEAREST_SHORTER"
    assert x["approval_status"] == "REVIEW_REQUIRED"


def test_t03_reversible_exact():
    x = one("GRAD 40 21-304")
    assert x["selected"]["model"] == "D21" and x["rsk"] == "6672226" and x["power_diff_w"] == -1
    assert x["orientation"] == "VÄNDBAR" and "E005" not in x["deviations"]


def test_t04_reversible_shorter():
    x = one("GRAD 40 21-311")
    assert x["rsk"] == "6672229" and x["length_diff_mm"] == -100 and x["power_diff_w"] == -39


def test_t05_convector_22_with_bracket_pair_not_multiplied():
    r = G.run([{"id": "TEST-005", "text": "GRAD 40 22-212", "qty": 2}])
    assert r["prixel"][0] == {"Artnr": "6739434", "Ant": 2, "Kontrollkälla": "TEST-005 | GRAD 40 22-212"}
    assert r["prixel"][1]["Artnr"] == "6739888" and r["prixel"][1]["Ant"] == 1
    assert r["results"][0]["match_status"] == "H200_EXACT"


def test_t06_convector_33_shorter_with_bracket():
    r = G.run([{"id": "TEST-006", "text": "GRAD 40 V 33-211", "qty": 4}])
    assert [(p["Artnr"], p["Ant"]) for p in r["prixel"]] == [("6739467", 4), ("6712064", 1)]
    assert r["results"][0]["match_status"] == "H200_NEAREST_SHORTER"


def test_t07_d33_right_shorter():
    x = one("GRAD 40 H 33-308")
    assert x["selected"]["length"] == 700 and x["rsk"] == "6672336"
    assert x["length_diff_mm"] == -100 and x["power_diff_w"] == -152


def test_t08_no_match_goes_to_deviations_not_prixel():
    r = G.run([{"id": "TEST-008", "text": "GRAD 40 V 11-907", "qty": 3}])
    x = r["results"][0]
    assert x["match_status"] == "NO_MATCH" and x["rsk"] is None and "E002" in x["deviations"]
    assert r["prixel"] == [] and any(d["code"] == "E002" for d in r["deviations"])


def test_t09_temperature_regime_mismatch_leaves_diff_empty():
    x = one("GRAD 40 22-212")  # konvektorn har bara effekt vid 75/65/20
    assert x["technical_comparison_status"] == "TEMPERATURE_REGIME_MISMATCH"
    assert x["power_diff_w"] is None and x["power_diff_pct"] is None and "E006" in x["deviations"]
    y = one("GRAD 40 V 11-304", program="75/65/20", power=180)
    assert y["power_diff_w"] is None and y["technical_comparison_status"] != "COMPARABLE"


def test_t10_representative_file_21_radiators_thermostat_excluded():
    r = G.run(TESTDATA, project="Test")
    assert r["summary"]["radiators"] == 21 and r["summary"]["excluded_accessories"] == 1
    assert not any("TEST-009" in p["Kontrollkälla"] for p in r["prixel"])
    assert [p["Artnr"] for p in r["prixel"]] == ["6672135", "6672140", "6672226", "6672229", "6739434", "6739888",
                                                  "6739467", "6712064", "6672336"]


def test_t11_prixel_sheet_has_only_values_and_text_rsk():
    r = G.run(TESTDATA, project="Test", day=date(2026, 11, 26))
    wb = openpyxl.load_workbook(io.BytesIO(G.to_xlsx(r)))
    assert wb.sheetnames == G.SHEETS
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                assert not (isinstance(c.value, str) and c.value.startswith("=")), (ws.title, c.coordinate)
                assert c.data_type != "e"
    px = wb["Prixel import"]
    for (a,) in px.iter_rows(min_row=2, max_col=1):
        assert isinstance(a.value, str) and a.value.isdigit()
    assert r["filename"] == "Test_Grad-IN_G40_korsad_mot_Altech_inkl_Prixel_2026-11-26_v01.xlsx"
    assert {c["id"]: c["status"] for c in r["qa"]}["H"] == "PASS"
    assert not r["export_blocked"]


@pytest.mark.parametrize("length,phys,pairs", [(800, 2, 1), (1200, 2, 1), (1400, 3, 1.5), (1800, 3, 1.5),
                                                (2200, 4, 2), (2600, 5, 2.5)])
def test_t12_t13_bracket_table(length, phys, pairs):
    assert G.brackets(length) == (phys, pairs)


def test_t12_convector_1400_gives_ant_1_5():
    r = G.run([{"text": "GRAD 40 22-214", "qty": 4}])
    assert [(p["Artnr"], p["Ant"]) for p in r["prixel"]] == [("6739435", 4), ("6739888", 1.5)]


def test_t13_convector_2600_gives_ant_2_5():
    r = G.run([{"text": "GRAD 40 22-226", "qty": 1}])
    assert r["results"][0]["bracket"]["physical_per_convector"] == 5
    assert r["prixel"][1]["Ant"] == 2.5


def test_t14_same_model_h_and_v_give_different_rsk():
    assert one("GRAD 40 V 11-304")["rsk"] != one("GRAD 40 H 11-304")["rsk"]
    assert one("GRAD 40 V 21-304")["rsk"] == one("GRAD 40 H 21-304")["rsk"]  # vändbar


def test_unknown_orientation_on_separate_hv_type_gives_e005_and_no_prixel():
    r = G.run([{"text": "GRAD 40 11-304", "qty": 1}])
    assert r["results"][0]["rsk"] is None and "E005" in r["results"][0]["deviations"] and r["prixel"] == []


def test_t15_longer_model_without_approval_is_refused():
    x = one("GRAD 40 H 11-311", override={"rsk": "6672142"})  # D11 L1200 utan godkännare
    assert x["selected"]["length"] == 1000 and x["match_status"] == "NEAREST_SHORTER"
    assert any("vägras" in n for n in x["notes"])
    y = one("GRAD 40 H 11-311", override={"rsk": "6672142", "approved_by": "Projektledare"})
    assert y["selected"]["length"] == 1200 and y["match_status"] == "OVERRIDE"


def test_duplicate_rows_flagged_e009_and_not_double_counted_in_prixel():
    r = G.run([{"text": "GRAD 40 V 11-304", "qty": 2, "location": "Plan 10"},
               {"text": "GRAD 40 V 11-304", "qty": 2, "location": "Plan 10"}])
    assert "E009" in r["results"][1]["deviations"] and len(r["prixel"]) == 1
    assert {c["id"]: c["status"] for c in r["qa"]}["B"] == "FAIL" and r["export_blocked"]


def test_thermopanel_codes_are_read():
    c = G.parse_code("TP 22 V4-218")
    assert (c["family"], c["type"], c["height"], c["length"]) == ("Thermopanel V4", 22, 200, 1800)
    x = one("TP 22 V4-618")
    assert x["selected"]["family"] == "Altech Typ D" and x["original_power_w"] is not None


def test_customer_list_is_read_from_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Test-ID", "Kundens artikelnummer", "Kundens benämning", "Antal", "Placering", "Kommentar"])
    for t in TESTDATA:
        ws.append([t["id"], t["article"], t["text"], t["qty"], t["location"], ""])
    buf = io.BytesIO()
    wb.save(buf)
    rows = G.rows_from_xlsx(buf.getvalue())
    assert len(rows) == 9 and rows[0]["text"] == "GRAD 40 V 11-304" and rows[0]["qty"] == 2
    assert G.run(rows)["summary"]["radiators"] == 21


def test_drawing_reader_rows_are_crossed_by_structured_code():
    read = {"summary": {"rows": [
        {"designation": "TPv4 22-218", "maker": "Purmo", "series": "TPv4", "kind": "ventil", "type": "22", "h": 200,
         "l": 1800, "per_zone": {"A": 2}, "total": 2},
        {"designation": "TP 11-605", "maker": "Purmo", "series": "TP", "kind": "kompakt", "type": "11", "h": 600,
         "l": 500, "per_zone": {"A": 1}, "total": 1}]}}
    r = G.run(G.rows_from_reader(read))
    a, b = r["results"]
    assert a["rsk"] == "6739437" and a["match_status"] == "H200_EXACT" and a["location"] == "A: 2"
    assert b["rsk"] is None and "E002" in b["deviations"]


def test_service_golden_from_list_and_drawing(tmp_path_factory):
    import os
    import sys

    from test_radiators_are_counted_per_house_and_crossed_to_altech import _sheet

    tmp = tmp_path_factory.mktemp("gold")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    for m in list(sys.modules):
        if m == "app" or m.startswith("app."):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Test-ID", "Kundens artikelnummer", "Kundens benämning", "Antal", "Placering"])
    for t in TESTDATA:
        ws.append([t["id"], t["article"], t["text"], t["qty"], t["location"]])
    buf = io.BytesIO()
    wb.save(buf)
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "gold@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        f = {"file": ("lista.xlsx", buf.getvalue(), "application/octet-stream")}
        r = c.post("/api/radiators/golden", files=f, data={"project": "Explora"}, headers=H)
        assert r.status_code == 200, r.text
        assert r.json()["summary"]["radiators"] == 21 and not r.json()["export_blocked"]
        x = c.post("/api/radiators/golden", files=f, data={"project": "Explora", "fmt": "xlsx"}, headers=H)
        assert x.status_code == 200 and "Explora_Grad-IN_G40_korsad_mot_Altech_inkl_Prixel_" in x.headers["content-disposition"]
        assert openpyxl.load_workbook(io.BytesIO(x.content)).sheetnames == G.SHEETS
        dup = '[{"text":"GRAD 40 V 11-304","qty":1},{"text":"GRAD 40 V 11-304","qty":1}]'
        assert c.post("/api/radiators/golden", data={"rows": dup, "fmt": "xlsx"}, headers=H).status_code == 409
        assert c.post("/api/radiators/golden", data={"rows": "[]"}).status_code == 401

        p = c.post("/api/projects", json={"name": "Najaden", "contract_form": "ABT06"}, headers=H).json()
        pdf = open(_sheet(str(tmp / "plan.pdf")), "rb").read()
        from app.db import Drawing, SessionLocal
        from app.storage import storage
        storage.put("drawings/g/plan.pdf", io.BytesIO(pdf))
        with SessionLocal() as db:
            d = Drawing(project_id=p["id"], filename="VS-500-1-014.pdf", storage_key="drawings/g/plan.pdf",
                        sha256="b" * 64, size_bytes=len(pdf), n_pages=1)
            db.add(d)
            db.commit()
            did = d.id
        g = c.get(f"/api/drawings/{did}/radiators/golden", headers=H)
        assert g.status_code == 200, g.text
        assert g.json()["summary"]["radiators"] == 7 and g.json()["notice"] is None
