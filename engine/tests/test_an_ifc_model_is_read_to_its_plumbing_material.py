"""En IFC-modell läses till VVS-material: varje produkttyp en post, antalet är antalet objekt.

Modellen här är liten men byggd som Revits export (IFC4): objekt med Revits "familj:typ:id", typobjekt, rum som
hör till våningar, egenskaper och mängder. Det som prövas är löftena: rätt antal per typ och våning, fabrikat och
serie ur familjenamnet, rörlängd ur modellens egna längder (i millimeter), åäö avkodade, ett rör utan längd räknat
i styck och sagt, och att arkitekturen (väggar, dörrar) inte blir material.
"""
from __future__ import annotations

import io
import os
import sys
import zipfile

import pytest

from vvs_engine.ifc import read_ifc_bytes
from vvs_engine.ifc.reader import _decode

HEAD = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [ReferenceView_V1.2]'),'2;1');
FILE_NAME('Prov - IFC4.ifc','2026-01-08T17:35:45+01:00',(''),(''),'','Autodesk Revit','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#19=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#30=IFCBUILDINGSTOREY('s1',#18,'Plan 10',$,'Level',$,$,'Plan 10',.ELEMENT.,3000.);
#31=IFCBUILDINGSTOREY('s2',#18,'Plan 11',$,'Level',$,$,'Plan 11',.ELEMENT.,6000.);
#40=IFCSPACE('r1',#18,'1-101',$,$,$,$,'WC/Tv\\X\\E4tt',.ELEMENT.,.INTERNAL.,$);
#41=IFCSPACE('r2',#18,'2-101',$,$,$,$,'Bad',.ELEMENT.,.INTERNAL.,$);
#42=IFCRELAGGREGATES('a1',#18,$,$,#30,(#40));
#43=IFCRELAGGREGATES('a2',#18,$,$,#31,(#41));
"""


def _model(extra_rows: str = "") -> bytes:
    rows = []
    n = 100
    contained_r1, contained_r2, basins = [], [], []
    for k in range(3):                                   # 3 tvättställ: 1 på plan 10, 2 på plan 11
        rows.append(f"#{n}=IFCSANITARYTERMINAL('b{k}',#18,'Sanitary_Wash-Basins_Svedbergs_Washbasin-Munka-60x35:"
                    f"Washbasin Munka 60x35:{k}',$,'Sanitary_Wash-Basins_Svedbergs_Washbasin-Munka-60x35:Washbasin "
                    f"Munka 60x35',$,$,'{k}',.WASHHANDBASIN.);")
        (contained_r1 if k == 0 else contained_r2).append(n)
        basins.append(n)
        n += 1
    taps = []
    for k in range(2):
        rows.append(f"#{n}=IFCVALVE('v{k}',#18,'ARC_Plumbing Fixtures_FM Mattsson_Siljan_Tv\\X\\E4ttst\\X\\E4llsblandare:"
                    f"G3/8\":{k}',$,'ARC_Plumbing Fixtures_FM Mattsson_Siljan_Tv\\X\\E4ttst\\X\\E4llsblandare:G3/8\"',"
                    f"$,$,'{k}',.MIXING.);")
        contained_r2.append(n)
        taps.append(n)
        n += 1
    pipes = []
    for k, length in enumerate((2500.0, 1500.0)):
        rows.append(f"#{n}=IFCPIPESEGMENT('p{k}',#18,'VS_Pipe_Geberit_Mapress:Mapress 22:{k}',$,'VS_Pipe_Geberit_Mapress:"
                    f"Mapress 22',$,$,'{k}',.RIGIDSEGMENT.);")
        rows.append(f"#{n + 500}=IFCQUANTITYLENGTH('Length',$,$,{length},$);")
        rows.append(f"#{n + 600}=IFCELEMENTQUANTITY('q{k}',#18,'Qto_PipeSegmentBaseQuantities',$,$,(#{n + 500}));")
        rows.append(f"#{n + 700}=IFCRELDEFINESBYPROPERTIES('d{k}',#18,$,$,(#{n}),#{n + 600});")
        pipes.append(n)
        n += 1
    rows.append(f"#{n}=IFCPIPESEGMENT('p9',#18,'VS_Pipe_Uponor_PEX:PEX 16:9',$,'VS_Pipe_Uponor_PEX:PEX 16',$,$,'9',.RIGIDSEGMENT.);")
    pipes.append(n)
    n += 1
    rows.append(f"#{n}=IFCWALL('w1',#18,'Basic Wall:Innervägg:1',$,'Basic Wall:Innervägg',$,$,'1',.STANDARD.);")
    rows.append(f"#{n + 1}=IFCDOOR('d1',#18,'Door:Dörr 9x21:1',$,$,$,$,'1',$,$,$,$,$);")
    # fabrikat ur egenskaperna går före namnet
    rows.append("#900=IFCPROPERTYSINGLEVALUE('Manufacturer',$,IFCLABEL('Svedbergs'),$);")
    rows.append("#901=IFCPROPERTYSET('ps',#18,'Pset_ManufacturerTypeInformation',$,(#900));")
    rows.append("#902=IFCRELDEFINESBYPROPERTIES('dp',#18,$,$,(" + ",".join(f"#{b}" for b in basins) + "),#901);")
    rows.append("#950=IFCRELCONTAINEDINSPATIALSTRUCTURE('c1',#18,$,$,(" + ",".join(f"#{x}" for x in contained_r1) + "),#40);")
    rows.append("#951=IFCRELCONTAINEDINSPATIALSTRUCTURE('c2',#18,$,$,(" + ",".join(f"#{x}" for x in contained_r2) + "),#41);")
    rows.append("#952=IFCRELCONTAINEDINSPATIALSTRUCTURE('c3',#18,$,$,(" + ",".join(f"#{x}" for x in pipes) + "),#30);")
    return (HEAD + "\n".join(rows) + extra_rows + "\nENDSEC;\nEND-ISO-10303-21;\n").encode("latin-1")


def _by_name(items, word):
    return next(it for it in items if word.lower() in it["name"].lower())


def test_every_product_type_is_one_post_with_its_count_per_storey():
    r = read_ifc_bytes(_model())
    items = r["items"]
    assert r["meta"]["schema"] == "IFC4" and r["meta"]["storeys"] == ["Plan 10", "Plan 11"]
    assert r["meta"]["n_elements"] == 8                     # väggen och dörren är inte VVS
    basin = _by_name(items, "Munka")
    assert basin["quantity"] == 3 and basin["unit"] == "st" and basin["manufacturer"] == "Svedbergs"
    assert basin["spec"]["Per våning"] == "Plan 10: 1 · Plan 11: 2" and basin["subcategory"] == "Tvättställ"
    assert basin["spec"]["I rum"] == "2" and basin["category"] == "Sanitet"
    tap = _by_name(items, "blandare")
    assert tap["quantity"] == 2 and tap["manufacturer"] == "FM Mattsson" and "Tvättställsblandare" in tap["name"]
    assert "Siljan" in tap["type"]                          # serien ur familjen: det katalogen söks på
    assert tap["kind"] == "post" and tap["page"] == 0 and tap["quantity_text"] == "2 st"


def test_a_pipe_is_the_sum_of_the_models_own_lengths_and_without_them_it_is_counted_and_said():
    items = read_ifc_bytes(_model())["items"]
    mapress = _by_name(items, "Mapress")
    assert mapress["unit"] == "m" and mapress["quantity"] == 4.0          # 2500 + 1500 mm
    assert mapress["manufacturer"] == "Geberit" and mapress["spec"]["Antal rör"] == "2"
    pex = _by_name(items, "PEX")
    assert pex["unit"] == "st" and pex["quantity"] == 1 and "saknas i modellen" in pex["spec"]["Längd"]


def test_strings_are_decoded_and_a_zip_is_opened():
    assert _decode("Tv\\X\\E4ttst\\X\\E4ll") == "Tvättställ"
    assert _decode("\\X2\\00E500F6\\X0\\") == "åö" and _decode("Ett ''citat''") == "Ett 'citat'"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("modell/Prov - IFC4.ifc", _model())
    r = read_ifc_bytes(buf.getvalue())
    assert r["meta"]["inner"] == "modell/Prov - IFC4.ifc" and len(r["items"]) == 4
    with pytest.raises(ValueError):
        read_ifc_bytes(b"%PDF-1.7 inte en modell")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ifc")
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


def test_an_ifc_model_is_uploaded_to_any_project_matched_and_kept_apart_from_descriptions(client):
    r = client.post("/api/auth/register", json={"email": "ifc@example.com", "password": "hemligt1"})
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    p = client.post("/api/projects", json={"name": "Kv Modell", "contract_form": "AB04"}, headers=H).json()
    up = client.post(f"/api/projects/{p['id']}/ifc", files={"file": ("Prov - IFC4.ifc", _model(), "application/octet-stream")},
                     headers=H)
    assert up.status_code == 200, up.text
    s = up.json()
    assert s["status"] == "COMPLETED" and s["source"] == "ifc" and s["stats"]["elements"] == 8
    assert client.post(f"/api/projects/{p['id']}/ifc", files={"file": ("igen.ifc", _model(), "application/octet-stream")},
                       headers=H).json()["duplicate"]
    assert [x["id"] for x in client.get(f"/api/projects/{p['id']}/tech-specs?source=ifc", headers=H).json()] == [s["id"]]
    assert client.get(f"/api/projects/{p['id']}/tech-specs", headers=H).json() == []      # inte en beskrivning
    got = client.get(f"/api/tech-specs/{s['id']}", headers=H).json()
    assert {it["match"]["status"] for it in got["items"]} <= {"hittad", "möjlig", "saknas"}
    tap = _by_name(got["items"], "blandare")
    assert tap["match"]["hits"] and any("Siljan" in h["name"] for h in tap["match"]["hits"])   # FM Mattssons Siljan
    csv = client.get(f"/api/tech-specs/{s['id']}/items.csv", headers=H)
    assert csv.status_code == 200 and "Munka" in csv.text
    mail = client.post(f"/api/tech-specs/{s['id']}/mail", json={}, headers=H)
    assert mail.status_code in (200, 422)
    bad = client.post(f"/api/projects/{p['id']}/ifc", files={"file": ("x.pdf", b"%PDF", "application/pdf")}, headers=H)
    assert bad.status_code == 400
    notifc = client.post(f"/api/projects/{p['id']}/ifc", files={"file": ("x.ifc", b"hej", "application/octet-stream")}, headers=H)
    assert notifc.status_code == 400 and "IFC" in notifc.json()["detail"]
    empty = (HEAD + "#5=IFCWALL('w',#18,'Vägg',$,$,$,$,'1',.STANDARD.);\nENDSEC;\nEND-ISO-10303-21;\n").encode("latin-1")
    e = client.post(f"/api/projects/{p['id']}/ifc", files={"file": ("ark.ifc", empty, "application/octet-stream")}, headers=H).json()
    assert e["status"] == "FAILED" and "inga VVS-objekt" in e["error"]
    assert client.delete(f"/api/tech-specs/{s['id']}", headers=H).json()["ok"]
