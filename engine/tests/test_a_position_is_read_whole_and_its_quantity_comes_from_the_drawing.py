"""All text som hör till en position läses, var underlaget än kommer ifrån, och mängden hämtas från ritningen.

Från ett prov på ett riktigt underlag:
  - Fabrikat och RSK står ofta i brödtexten under raden (Grundfos, Thermia). Det ska kopplas till raden - också när
    underlaget kommer i ett mejl.
  - Rörlängder och antal komponenter (RB201) ska hämtas från ritningen när den finns.
"""
from __future__ import annotations

import io
import json
import os
import sys

import pymupdf
import pytest

from vvs_engine.tb import read_tech_spec
from vvs_engine.tb.drawing_link import apply, collect, link, system_key
from vvs_engine.tb.listing import read_material_list

sys.path.insert(0, os.path.dirname(__file__))
from test_a_technical_description_is_read_to_its_materials import _page  # noqa: E402


def test_maker_type_and_rsk_in_the_text_under_the_row_belong_to_the_row():
    rows = [("ama", "PSB", "PUMPAR"), ("ama", "PSB.1", "Cirkulationspumpar"),
            ("post", "PB101", "1 st"), ("text", "Cirkulationspump för VVC-systemet, varvtalsstyrd."),
            ("text", "Fabrikat: Grundfos"), ("text", "Typ: Magna3 25-60 180"), ("text", "RSK 573 24 87"),
            ("post", "VP01", "1 st"), ("text", "Värmepump mark/vatten."), ("text", "Thermia Atlas 12 kW,"),
            ("text", "RSK 621 73 05 eller likvärdig."),
            ("post", "SIL501", "2 st"), ("text", "Smutsfilter DN25 av mässing. Monteras enligt Grundfos anvisningar."),
            ("text", "Art.nr AT 4003A25")]
    doc = pymupdf.open()
    _page(doc, rows, 1, 1)
    items = {it["code"]: it for it in read_tech_spec(doc)["items"]}
    assert (items["PB101"]["manufacturer"], items["PB101"]["type"], items["PB101"]["rsk"]) == \
        ("Grundfos", "Magna3 25-60 180", ["5732487"])
    assert items["VP01"]["manufacturer"] == "Thermia" and items["VP01"]["rsk"] == ["6217305"]
    # ett fabrikat i förbigående ("enligt Grundfos anvisningar") är ingen förskrivning
    assert items["SIL501"]["manufacturer"] == "Armatec" and items["SIL501"]["art_nr"] == ["AT 4003A25"]


MAIL = """Subject: =?utf-8?q?F=C3=B6rfr=C3=A5gan_material?=
Content-Type: text/plain; charset=utf-8

Hej,

Vi behöver pris på följande:

3 st cirkulationspump
Grundfos Magna3 25-60 180, RSK 573 24 87

VP01 1 st Värmepump mark/vatten
Thermia Atlas 12 kW, RSK 621 7305

12 m Kopparrör 22x1,0 raka längder

Med vänliga hälsningar
Kalle
> 5 st något ur ett tidigare mejl
"""


def test_a_mail_is_read_position_by_position_with_the_lines_under_each():
    r = read_material_list("förfrågan.eml", MAIL.encode("utf-8"))
    assert r["meta"]["title"] == "Förfrågan material"
    got = [(it["code"], it["quantity"], it["unit"], it["manufacturer"], it["rsk"]) for it in r["items"]]
    assert got == [("", 3.0, "st", "Grundfos", ["5732487"]), ("VP01", 1.0, "st", "Thermia", ["6217305"]),
                   ("", 12.0, "m", "", [])]
    assert r["items"][0]["name"] == "Cirkulationspump" and "22x1,0" in r["items"][2]["name"]


def test_a_spreadsheet_bom_is_read_by_its_header_row():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Materiallista Brf Tallen"])
    ws.append(["Pos", "Benämning", "Fabrikat", "Typ", "RSK-nr", "Antal", "Enhet"])
    ws.append(["1", "Cirkulationspump", "Grundfos", "Magna3 25-60", "573 24 87", 3, "st"])
    ws.append(["2", "Kulventil", "Beulco", "BA 107 DN20", "", 14, "st"])
    buf = io.BytesIO()
    wb.save(buf)
    items = read_material_list("bom.xlsx", buf.getvalue())["items"]
    assert [(i["code"], i["name"], i["manufacturer"], i["rsk"], i["quantity"]) for i in items] == [
        ("1", "Cirkulationspump", "Grundfos", ["5732487"], 3.0), ("2", "Kulventil", "Beulco", [], 14.0)]


def test_an_outlook_msg_is_refused_with_what_to_do_instead():
    with pytest.raises(ValueError, match=".eml"):
        read_material_list("mejl.msg", b"\xd0\xcf\x11\xe0")


def _reading(tmp_path, name, pages):
    """En läsning som tjänsten skriver den: sheets/<n>/component-tags.json och document-quantities.json."""
    root = tmp_path / name
    for page, texts in pages.items():
        d = root / "sheets" / str(page)
        d.mkdir(parents=True)
        (d / "component-tags.json").write_text(json.dumps({"rows": [
            {"text": t, "bbox": [10.0 * i, 20.0, 10.0 * i + 30, 26.0], "page": page} for i, t in enumerate(texts)]}))
    (root / "document-quantities.json").write_text(json.dumps({"rows": [
        {"designation": "KV1-X74-32/S2", "dn": 32, "confirmed_total_m": 41.5, "review_m": 2.0, "state": "MEASURED"},
        {"designation": "KV1-X72-20", "dn": 20, "confirmed_total_m": 12.25, "review_m": 0.0, "state": "MEASURED"},
        {"designation": "VV1-X76/S3", "dn": 32, "confirmed_total_m": 30.0, "review_m": 0.0, "state": "MEASURED"},
        {"designation": "Onämnt rör (x)", "dn": None, "confirmed_total_m": 5.0},
    ]}))
    return {"dir": str(root), "drawing": name}


def test_components_are_counted_and_pipes_measured_on_the_drawings(tmp_path):
    a = _reading(tmp_path, "V-50-01.pdf", {0: ["RB201", "RB201", "SIL501", "RV602-20", "KV1", "S1-P5"],
                                           1: ["RB201", "RV602-15LF"]})
    found = collect([a])
    assert found["tags"]["RB201"]["count"] == 3 and found["tags"]["RV602"]["count"] == 2
    assert "KV1" not in found["tags"] and "S1" not in found["tags"]     # system, inga komponenter
    assert found["pipes"]["KV1"]["m"] == 53.75 and found["pipes"]["KV1"]["by_dn"] == {"20": 12.25, "32": 41.5}
    assert system_key("KV01") == "KV1" == system_key("kv1")

    rb = {"code": "RB201", "name": "Rensbrunn", "quantity": 1.0, "total_quantity": 1.0, "unit": "st"}
    fd = link(rb, found)
    assert fd["kind"] == "antal" and fd["quantity"] == 3.0
    out = apply(rb, fd)
    assert out["total_quantity"] == 3.0 and out["description_quantity"] == 1.0 and out["quantity_from"] == "ritning"

    kv = {"code": "KV01-K1", "name": "Tappkallvatten", "subcategory": "Ledningar av kopparrör",
          "quantity": None, "total_quantity": None, "unit": ""}
    out = apply(kv, link(kv, found))
    assert out["total_quantity"] == 53.75 and out["unit"] == "m" and out["from_drawing"]["review_m"] == 2.0
    # det ritningen inte säger något om står kvar som det stod i underlaget
    other = {"code": "PB101", "name": "Cirkulationspump", "quantity": 1.0, "total_quantity": 1.0, "unit": "st"}
    assert link(other, found) is None and apply(other, None) == other
    assert link(rb, {}) is None


# ---------------------------------------------------------------- genom tjänsten

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lista")
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


def test_a_mail_and_pasted_text_become_lists_in_any_project(client):
    r = client.post("/api/auth/register", json={"email": "lista@example.com", "password": "hemligt1"})
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    p = client.post("/api/projects", json={"name": "Brf Tallen"}, headers=H).json()
    up = client.post(f"/api/projects/{p['id']}/material-list", files={"file": ("förfrågan.eml", MAIL.encode(), "message/rfc822")},
                     headers=H)
    assert up.status_code == 200, up.text
    s = up.json()
    assert s["status"] == "COMPLETED" and s["source"] == "lista" and s["stats"]["with_rsk"] == 2
    got = client.get(f"/api/tech-specs/{s['id']}", headers=H).json()
    pump = next(it for it in got["items"] if it["manufacturer"] == "Grundfos")
    assert pump["rsk"] == ["5732487"] and pump["match"]["basis"] == "förskrivet nummer"
    pasted = client.post(f"/api/projects/{p['id']}/material-list/text",
                         json={"text": "2 st Smutsfilter Armatec AT 4003A25\n14 st Kulventil Beulco BA 107 DN20"}, headers=H).json()
    assert pasted["status"] == "COMPLETED" and pasted["stats"]["items"] == 2
    listed = client.get(f"/api/projects/{p['id']}/tech-specs?source=ifc", headers=H).json()
    assert {x["id"] for x in listed} == {s["id"], pasted["id"]}
    assert client.get(f"/api/projects/{p['id']}/tech-specs", headers=H).json() == []
    assert client.post(f"/api/projects/{p['id']}/material-list", files={"file": ("x.pdf", b"%PDF", "application/pdf")},
                       headers=H).status_code == 400
    csv = client.get(f"/api/tech-specs/{s['id']}/items.csv", headers=H).text
    assert "Antal ur ritning" in csv and "573 24 87" in csv
