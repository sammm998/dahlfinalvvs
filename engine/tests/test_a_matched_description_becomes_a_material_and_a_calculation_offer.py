"""Den färdiga matchningen blir en offert: kund med kundnummer, rabattmatris, bonus, inköp och marginal internt.

Ersätter Excel med Prixel och Dahlmenyn: kunden väljs med kundnummer och dess rabattmatris läses in; priset per rad
är bruttopriset minus kundens rabatt för artikelns rabattgrupp (eller kundens nettopris); bonusen hämtas med en
knapp; inköpspris och marginal visas per rad och totalt i det interna underlaget men aldrig på kundens offert.
Materialoffert är materialet i underlaget; kalkyloffert lägger till montörstimmarna ur normtidsboken.
"""
from __future__ import annotations

import io
import os
import sys

import openpyxl
import pymupdf
import pytest

from vvs_engine import offer as OF
from vvs_engine.tb.crossref import for_item, material_of

sys.path.insert(0, os.path.dirname(__file__))
from test_a_technical_description_is_read_to_its_materials import PAGES, _page  # noqa: E402


BOOK = {"7606418": {"a": "7606418", "n": "Tvättställ IFÖ Cera", "p": 2000.0, "k": "4200"},
        "5732487": {"a": "5732487", "n": "Cirkulationspump Grundfos", "p": 6000.0, "k": "3100"},
        "1111115": {"a": "1111115", "n": "15 Kopparrör", "p": 100.0, "k": "1000"},
        "1111122": {"a": "1111122", "n": "22 Kopparrör", "p": 150.0, "k": "1000"}}


def _item(**kw):
    base = {"id": "p1", "code": "", "kind": "post", "name": "Tvättställ", "manufacturer": "IFÖ", "type": "Cera",
            "quantity": 3.0, "total_quantity": 3.0, "unit": "st", "spec": {}, "text": "", "category": "Tvättställ",
            "subcategory": "", "supplied_by": "",
            "match": {"status": "hittad", "hits": [{"ref": "7606418", "name": "Tvättställ IFÖ Cera"}], "basis": "förskrivet nummer"}}
    return {**base, **kw}


def test_the_customer_price_is_the_list_price_less_the_customers_discount_for_the_group():
    cust = {"rabatter": {"4200": 40.0}, "netto": {"5732487": 3500.0}}
    p = OF.customer_price("7606418", BOOK, cust)
    assert p["brutto"] == 2000.0 and p["rabatt_pct"] == 40.0 and p["netto"] == 1200.0 and p["rabattgrupp"] == "4200"
    assert OF.customer_price("5732487", BOOK, cust)["netto"] == 3500.0       # kundens nettopris går före rabatten
    none = OF.customer_price("1111115", BOOK, cust)
    assert none["netto"] == 100.0 and "finns inte i kundens rabattmatris" in none["pris_enligt"]


def test_purchase_and_margin_are_counted_per_row_and_in_total():
    rows = OF.build_rows([_item()], BOOK, {"rabatter": {"4200": 40.0}}, {"7606418": 900.0})
    r = rows[0]
    assert (r["antal"], r["netto"], r["summa"], r["inkop_summa"], r["marginal_kr"], r["marginal_pct"]) == \
        (3.0, 1200.0, 3600.0, 2700.0, 900.0, 25.0)
    t = OF.totals(rows, bonus_pct=2.0)
    assert t["material"] == 3600.0 and t["marginal_kr"] == 900.0 and t["bonus_kr"] == 72.0


def test_an_item_without_an_article_is_flagged_never_guessed():
    it = _item(match={"status": "saknas", "hits": [], "basis": "förskrivet fabrikat"})
    r = OF.build_rows([it], BOOK, None, {})[0]
    assert r["rsk"] == "" and "ingen artikel - manuell hantering" in r["flaggor"] and r["summa"] is None


def test_the_calculation_offer_adds_fitter_hours_from_the_norm_time_book():
    rows = OF.build_rows([_item(), _item(id="p2", name="Spegelskåp", category="Spegelskåp", match={"status": "saknas", "hits": []})], BOOK,
                         None, {}, kind="kalkyloffert", hourly_rate=600.0)
    assert rows[0]["tim_per_enhet"] == 1.4 and rows[0]["timmar"] == 4.2 and rows[0]["arbete_kr"] == 2520.0
    assert "Tvättställspaket" in rows[0]["tim_kalla"]
    assert rows[1]["tim_per_enhet"] is None and "montörstid saknas" in rows[1]["flaggor"]   # ingen gissad tid
    t = OF.totals(rows, hourly_rate=600.0)
    assert t["timmar"] == 4.2 and t["arbete"] == 2520.0


CROSSREF = [{"material": "Koppar", "dimension": "15", "fabrikat": "Cupori", "rsk": "1111115", "benamning": "15 Kopparrör",
             "pris_saknas": False},
            {"material": "Koppar", "dimension": "22", "fabrikat": "", "rsk": "1111122", "benamning": "22 Kopparrör",
             "pris_saknas": False}]


def test_the_pipe_rule_takes_the_maker_then_our_equivalent_then_flags():
    pipe = _item(name="Tappkallvatten", subcategory="Ledningar av kopparrör", manufacturer="Cupori", type="",
                 text="Raka kopparrör av fabrikat Cupori", unit="m", quantity=None, total_quantity=None,
                 match={"status": "saknas", "hits": [], "basis": "förskrivet fabrikat"},
                 from_drawing={"kind": "meter", "quantity": 40.0, "by_dn": {"15": 30.0, "22": 8.0, "28": 2.0}})
    assert material_of(pipe["text"]) == "koppar"
    rows = OF.build_rows([pipe], BOOK, None, {}, crossref=CROSSREF)
    got = {r["id"]: (r["antal"], r["rsk"], r["val"], r["flaggor"]) for r in rows}
    assert got["p1-dn15"][:2] == (30.0, "1111115") and "korsreferens" in got["p1-dn15"][2]      # b)
    assert got["p1-dn22"][:2] == (8.0, "1111122")
    assert got["p1-dn28"][1] == "" and any("manuell hantering" in f for f in got["p1-dn28"][3])  # c)
    # a) en storlek ur seriens storlekar efter ritningen går före korsreferensen
    serie = {**pipe, "match": {"status": "möjlig", "hits": [], "basis": "förskrivet fabrikat",
                               "rsk": {"kind": "storlek", "variants": [{"rsk": "9990015", "size": "15", "name": "15 Cupori"}]}}}
    r15 = next(r for r in OF.build_rows([serie], BOOK, None, {}, crossref=CROSSREF) if r["id"] == "p1-dn15")
    assert r15["rsk"] == "9990015" and "storlek ur ritningen" in r15["val"]
    assert for_item({"name": "Kopparrör 22x1,0", "text": "", "spec": {}}, CROSSREF)["rsk"] == "1111122"


# ---------------------------------------------------------------- genom tjänsten

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("offert")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def _xlsx(rows):
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_the_offer_flow_from_customer_number_to_customer_pdf(client):
    admin = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "admin@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    H = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "saljare@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    from app.main import _material_book
    book = {r["a"]: r for r in _material_book()["rows"]}
    group = book["7606418"]["k"]
    up = lambda kind, rows, hdr=admin: client.post(f"/api/offer-data/{kind}", files={"file": (f"{kind}.xlsx", _xlsx(rows), "application/octet-stream")}, headers=hdr)
    assert up("kunder", [["Kundnr", "Namn", "Bonus %"], [10234, "Rörfirman AB", 2.5]]).json()["n"] == 1
    assert up("rabatter", [["Kundnr", "Rabattgrupp", "Rabatt %"], [10234, group, 35]]).json()["n"] == 1
    assert up("inkopspriser", [["RSK", "Inköpspris"], ["760 64 18", 500]]).json()["n"] == 1
    assert up("kunder", [["Kundnr", "Namn"], [1, "x"]], H).status_code == 403          # bara administratören
    assert client.get("/api/customers?q=rör", headers=H).json()["customers"] == [{"kundnr": "10234", "namn": "Rörfirman AB"}]

    p = client.post("/api/projects", json={"name": "Tvätthall", "contract_form": "ABT06", "tech_spec": True}, headers=H).json()
    doc = pymupdf.open()
    for i, rows in enumerate(PAGES):
        _page(doc, rows, i + 1, len(PAGES))
    s = client.post(f"/api/projects/{p['id']}/tech-specs", files={"file": ("tb.pdf", doc.tobytes(), "application/pdf")}, headers=H).json()
    o = client.post(f"/api/projects/{p['id']}/offers", json={"kind": "materialoffert", "customer_no": "10234"}, headers=H)
    assert o.status_code == 200, o.text
    o = o.json()
    assert o["customer_name"] == "Rörfirman AB" and o["sources"] == [s["id"]] and o["rows"]
    ts = next(r for r in o["rows"] if r["rsk"] == "7606418")
    assert ts["rabatt_pct"] == 35.0 and ts["netto"] == round(book["7606418"]["p"] * 0.65, 2)
    assert ts["inkop"] == 500.0 and ts["marginal_kr"] is not None
    assert any("manuell hantering" in " ".join(r["flaggor"]) for r in o["rows"])         # det som saknas syns

    b = client.post(f"/api/offers/{o['id']}/bonus", headers=H).json()
    assert b["settings"]["bonus_pct"] == 2.5 and b["totals"]["bonus_kr"] > 0
    ch = client.patch(f"/api/offers/{o['id']}", json={"rows": [{"id": ts["id"], "antal": 7}]}, headers=H).json()
    assert next(r for r in ch["rows"] if r["id"] == ts["id"])["antal"] == 7

    cust = client.get(f"/api/offers/{o['id']}/export.xlsx", headers=H)
    wb = openpyxl.load_workbook(io.BytesIO(cust.content))
    text = " ".join(str(c.value) for row in wb.active.iter_rows() for c in row if c.value is not None)
    assert "Rörfirman" in text and "Inköp" not in text and "Marginal" not in text          # aldrig på kundens offert
    internal = client.get(f"/api/offers/{o['id']}/export.xlsx?internal=true", headers=H)
    wbi = openpyxl.load_workbook(io.BytesIO(internal.content))
    assert "Marginal kr" in " ".join(str(c.value) for row in wbi.active.iter_rows() for c in row if c.value)
    pdf = client.get(f"/api/offers/{o['id']}/export.pdf", headers=H)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "Inköp" not in pymupdf.open(stream=pdf.content, filetype="pdf")[0].get_text()

    k = client.post(f"/api/projects/{p['id']}/offers", json={"kind": "kalkyloffert", "customer_no": "10234",
                                                             "hourly_rate": 650}, headers=H).json()
    assert k["totals"]["timmar"] > 0 and k["totals"]["arbete"] == round(k["totals"]["timmar"] * 650, 2)
    other = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "annan@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    assert client.get(f"/api/offers/{o['id']}", headers=other).status_code == 404
