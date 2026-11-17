"""SmartHangers: rören i IFC-modellen blir prefabricerade hängare med ID, höjd, materiallista, kapning, kollin,
QR-etikett, IFC-export och revisionsjämförelse. Reglerna är data och värdena exempel tills de verifieras."""
from __future__ import annotations

import numpy as np
import pytest

from vvs_engine.hangers import calc as C
from vvs_engine.hangers import generate as G
from vvs_engine.hangers import ifc_export as X
from vvs_engine.hangers import qr as Q
from vvs_engine.hangers import rules as RL
from vvs_engine.hangers.geometry import pipes


def _ifc(extra_valve: bool = True, mapped: bool = True, moved: float = 0.0) -> str:
    """Två parallella kopparrör 22 mm, 6 m långa, 300 mm isär på 2,7 m höjd. Det ena som en mappad representation
    (Revits typexport), det andra som en vanlig extrudering. En ventil på det första röret."""
    L = []

    def a(s):
        L.append(f"#{len(L) + 1}={s};")
        return len(L)
    o = a("IFCCARTESIANPOINT((0.,0.,0.))")
    z = a("IFCDIRECTION((0.,0.,1.))")
    x = a("IFCDIRECTION((1.,0.,0.))")
    world = a(f"IFCAXIS2PLACEMENT3D(#{o},#{z},#{x})")
    a("IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)")
    site = a(f"IFCLOCALPLACEMENT($,#{world})")
    s0 = a(f"IFCBUILDINGSTOREY('s0',$,'Plan 10',$,$,#{site},$,$,.ELEMENT.,0.)")
    s1 = a(f"IFCBUILDINGSTOREY('s1',$,'Plan 11',$,$,#{site},$,$,.ELEMENT.,3500.)")
    els = []

    def pipe(gid, y, use_map):
        circ = a("IFCCIRCLEPROFILEDEF(.AREA.,$,$,11.)")
        if use_map:
            # röret ritat längs z i sin egen typ, vridet till x och flyttat med operatorn
            sol = a(f"IFCEXTRUDEDAREASOLID(#{circ},#{world},#{z},6000.)")
            rep = a(f"IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#{sol}))")
            mo = a(f"IFCAXIS2PLACEMENT3D(#{o},$,$)")
            rmap = a(f"IFCREPRESENTATIONMAP(#{mo},#{rep})")
            op = a(f"IFCCARTESIANTRANSFORMATIONOPERATOR3D(#{a('IFCDIRECTION((0.,0.,-1.))')},#{a('IFCDIRECTION((0.,1.,0.))')},#{a('IFCCARTESIANPOINT((0.,0.,0.))')},1.,#{a('IFCDIRECTION((1.,0.,0.))')})")
            item = a(f"IFCMAPPEDITEM(#{rmap},#{op})")
            body = a(f"IFCSHAPEREPRESENTATION($,'Body','MappedRepresentation',(#{item}))")
        else:
            pos = a(f"IFCAXIS2PLACEMENT3D(#{o},#{x},#{z})")
            sol = a(f"IFCEXTRUDEDAREASOLID(#{circ},#{pos},#{z},6000.)")
            body = a(f"IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#{sol}))")
        pds = a(f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{body}))")
        lp = a(f"IFCAXIS2PLACEMENT3D(#{a(f'IFCCARTESIANPOINT((1000.,{y + moved},2700.))')},#{z},#{x})")
        pl = a(f"IFCLOCALPLACEMENT(#{site},#{lp})")
        e = a(f"IFCPIPESEGMENT('{gid}',$,'Kopparrör 22',$,$,#{pl},#{pds},$,.RIGIDSEGMENT.)")
        v1 = a("IFCPROPERTYSINGLEVALUE('Material',$,IFCLABEL('Koppar'),$)")
        v2 = a("IFCPROPERTYSINGLEVALUE('Nominal Diameter',$,IFCLENGTHMEASURE(22.),$)")
        v3 = a("IFCPROPERTYSINGLEVALUE('System Name',$,IFCLABEL('VV1'),$)")
        ps = a(f"IFCPROPERTYSET('ps{gid}',$,'Pset',$,(#{v1},#{v2},#{v3}))")
        a(f"IFCRELDEFINESBYPROPERTIES('r{gid}',$,$,$,(#{e}),#{ps})")
        els.append(e)
    pipe("A", 0.0, mapped)
    pipe("B", 300.0, False)
    if extra_valve:
        bx = a("IFCBLOCK")  # obrukbar post: läsaren ska tåla den
        tri = a("IFCCARTESIANPOINTLIST3D(((3990.,-15.,2690.),(4010.,-15.,2690.),(4010.,15.,2710.),(3990.,15.,2710.)))")
        fs = a(f"IFCTRIANGULATEDFACESET(#{tri},$,$,((1,2,3),(1,3,4)),$)")
        body = a(f"IFCSHAPEREPRESENTATION($,'Body','Tessellation',(#{fs}))")
        pds = a(f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{body}))")
        pl = a(f"IFCLOCALPLACEMENT(#{site},#{world})")
        els.append(a(f"IFCVALVE('V',$,'Avstängningsventil',$,$,#{pl},#{pds},$,$)"))
        del bx
    a(f"IFCRELCONTAINEDINSPATIALSTRUCTURE('c',$,$,$,({','.join('#%d' % e for e in els)}),#{s0})")
    a(f"IFCRELAGGREGATES('ag',$,$,$,#{site},(#{s0},#{s1}))")
    return "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n" + "\n".join(L) + "\nENDSEC;\nEND-ISO-10303-21;\n"


def test_the_pipe_axis_is_read_through_placements_and_mapped_items():
    m = pipes(_ifc())
    got = {p["id"]: p for p in m["pipes"]}
    assert set(got) == {"A", "B"}
    for gid, y in (("A", 0.0), ("B", 300.0)):
        s, e = np.array(got[gid]["start"]), np.array(got[gid]["end"])
        assert np.allclose(sorted([s[0], e[0]]), [1000, 7000], atol=1) and np.allclose([s[1], e[1], s[2], e[2]], [y, y, 2700, 2700], atol=1)
        assert got[gid]["dn"] == 22 and got[gid]["material"] == "Koppar" and got[gid]["storey"] == "Plan 10"
    assert m["fittings"] and np.allclose(m["fittings"][0]["at"][:2], [4000, 0], atol=5)


def test_parallel_pipes_share_a_trapeze_at_the_rule_spacing():
    r = G.generate(pipes(_ifc(extra_valve=False)), project="Test")
    hs = r["hangers"]
    assert r["runs"] == 1 and all(h["kind"] == "takjärn" and len(h["pipes"]) == 2 for h in hs)
    xs = sorted(h["position"]["x"] for h in hs)
    assert xs[0] - 1000 <= 500 and 7000 - xs[-1] <= 500                     # ände högst 500 mm
    assert max(b - a for a, b in zip(xs, xs[1:])) <= 1800                    # koppar 22: 1800 mm (exempel)
    h = hs[0]
    assert h["id"] == "P10-001" and h["ceiling_z"] == 3250 and h["height_source"].startswith("beräknad")
    # takjärnets ovansida 30 mm under rörens underkant, pendeln till taket med 40 mm under profilen
    assert h["takjarn"]["length_mm"] == 450 and h["rods"][0]["length_mm"] == 680 and len(h["rods"]) == 2
    parts = {b["part"] for b in h["bom"]}
    assert {"takjärn", "gängstång", "rörklammer", "infästning", "mutter"} <= parts
    assert all(p["spacing_rule"].startswith("koppar") for p in h["pipes"])


def test_a_valve_gets_a_hanger_close_by_and_heights_can_be_set_by_hand():
    r = G.generate(pipes(_ifc()), manual_heights={"Plan 10": 3000})
    xs = [h["position"]["x"] for h in r["hangers"]]
    assert min(abs(x - 4000) for x in xs) <= 300
    assert any(h["placed_because"] == "nära ventil/rördel" for h in r["hangers"])
    assert all(h["height_source"] == "manuell" and h["ceiling_z"] == 3000 for h in r["hangers"])
    no = G.generate({"pipes": pipes(_ifc())["pipes"], "storeys": [{"name": "Plan 10", "elevation": 0.0}]})
    assert all("takhöjd saknas - ange takhöjd för våningen" in h["flags"] for h in no["hangers"])


def test_cut_plan_packing_and_project_bom():
    hs = G.generate(pipes(_ifc()))["hangers"]
    cuts = G.cut_plan(hs)
    rods = cuts["gängstång"][0]
    assert rods["pieces"] == 2 * len(hs) and rods["n_bars"] == -(-rods["pieces"] // 2)    # 680 mm: två per 2 m
    for b in cuts["takjärn"][0]["bars"]:
        assert sum(c["mm"] + 3 for c in b["cuts"]) <= 3000
    kollin = G.pack(hs, {"packing": {"max_per_kolli": 2, "max_kg_per_kolli": 25.0}})
    assert all(len(k["hangers"]) <= 2 for k in kollin) and all(h["pack"]["kolli"] >= 1 for h in hs)
    tot = {(b["text"], b["length_mm"]): b["qty"] for b in G.bom_total(hs)}
    assert tot[("Takjärn 41x41 (U-profil)", 450)] == len(hs)


def test_a_revision_shows_what_moved_and_which_produced_hangers_are_critical():
    old = pipes(_ifc())["pipes"]
    hs = G.generate(pipes(_ifc()))["hangers"]
    hs[0]["status"] = "producerad"
    d = G.diff(old, pipes(_ifc(moved=120.0))["pipes"], hs)
    assert {m["pipe"] for m in d["moved"]} == {"A", "B"} and d["critical"] == 1
    assert d["affected"][0]["critical"] and len(d["affected"]) == len(hs)


def test_rules_are_examples_until_verified_and_the_heavier_load_flags():
    r = RL.default()
    assert r["verified"] is False and "EXEMPEL" in r["note"]
    assert RL.spacing(r, "plast", 110)[0] == 1400 and RL.spacing(r, "stål", 65)[0] == 3500
    assert RL.material_key("PEX-rör") == "plast" and RL.material_key("Kopparrör") == "koppar"
    weak = {"load": {**r["load"], "rod_capacity_kn": {"M8": 0.001}}}
    hs = G.generate(pipes(_ifc()), weak)["hangers"]
    assert all(any("överstiger" in f for f in h["flags"]) for h in hs)


def test_qr_codes_decode():
    cv2 = pytest.importorskip("cv2")
    for text in ("P2-014", "https://dahl.example/montage/9f8e7d6c-1234-4abc-9def-0123456789ab?h=P16-123&rev=B"):
        m = np.array(Q.matrix(text), dtype=np.uint8)
        ok = False
        for f in (4, 6, 8, 10):
            img = cv2.resize((np.pad(1 - m, 4, constant_values=1) * 255).astype(np.uint8), None, fx=f, fy=f,
                             interpolation=cv2.INTER_NEAREST)
            ok = ok or cv2.QRCodeDetector().detectAndDecode(img)[0] == text
        assert ok, text


def test_the_ifc_export_reads_back_with_ids_and_status():
    hs = G.generate(pipes(_ifc()))["hangers"]
    hs[1]["status"] = "monterad"
    text = X.export(hs, "Test", "B")
    assert text.startswith("ISO-10303-21;") and text.count("IFCBUILDINGELEMENTPROXY(") == len(hs)
    assert "'Pset_SmartHanger'" in text and f"'{hs[0]['id']}'" in text and "IFCLABEL('monterad')" in text
    from vvs_engine.ifc.reader import _records
    R = _records(text.splitlines())
    assert sum(1 for c, _ in R.values() if c == "IFCBUILDINGELEMENTPROXY") == len(hs)
    assert X.guid("a") == X.guid("a") and len(X.guid("a")) == 22


def test_the_calculation_shows_its_assumptions():
    r = C.compute({"antal": 400})
    assert r["assumptions"]["label"].startswith("RÄKNEEXEMPEL") and r["assumptions"]["antal"] == 400
    assert r["frigjorda_montorstimmar"] == round(400 * (0.60 - 0.20), 1)
    assert r["besparing_kr"] == round(r["traditionell_kr"] - r["smarthangers_kr"], 0)
    assert r["lonsamhetsgrans_antal"] and r["lonsamhetsgrans_antal"] > 0 and len(r["kanslighet"]) == 8


# ---------------------------------------------------------------- genom tjänsten

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    import sys
    tmp = tmp_path_factory.mktemp("prefab")
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


def test_the_prefab_flow_from_ifc_to_mounted(client):
    import io
    import openpyxl
    import pymupdf
    admin = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "admin@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    H = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "montor@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    p = client.post("/api/projects", json={"name": "Kv Prefab", "contract_form": "ABT06"}, headers=H).json()
    r = client.post(f"/api/projects/{p['id']}/hangers", files={"file": ("vs.ifc", _ifc().encode(), "application/octet-stream")},
                    data={"heights": '{"Plan 10": 3200}'}, headers=H)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["n"] >= 4 and s["revision"] == "A" and s["rules_verified"] is False
    assert all(h["height_source"] == "manuell" for h in s["hangers"])
    sid, hid = s["id"], s["hangers"][0]["id"]
    # granskning: flytta, kommentera; produktion går inte före frisläppning
    g = client.patch(f"/api/hanger-sets/{sid}/hangers/{hid}", json={"position": {"x": 1600}, "comment": "flyttad från balk"}, headers=H).json()
    assert g["hanger"]["position"]["x"] == 1600 and g["hanger"]["history"][-1]["comment"] == "flyttad från balk"
    assert client.patch(f"/api/hanger-sets/{sid}/hangers/{hid}", json={"status": "producerad"}, headers=H).status_code == 409
    assert client.post(f"/api/hanger-sets/{sid}/approve", json={"kind": "konstruktion"}, headers=H).status_code == 200
    blocked = client.post(f"/api/hanger-sets/{sid}/approve", json={"kind": "produktion"}, headers=H)
    assert blocked.status_code == 409 and "verifierade" in blocked.json()["detail"]
    # en tekniskt ansvarig verifierar reglerna; uppsättningen räknas om med dem
    assert client.post("/api/prefab/rules/verify", headers=H).status_code == 403
    assert client.post("/api/prefab/rules/verify", headers=admin).json()["verified"] is True
    s = client.post(f"/api/hanger-sets/{sid}/regenerate", json={"heights": {"Plan 10": 3200}}, headers=H).json()
    assert s["rules_verified"] is True and s["approvals"] == {}
    client.post(f"/api/hanger-sets/{sid}/approve", json={"kind": "konstruktion"}, headers=H)
    assert client.post(f"/api/hanger-sets/{sid}/approve", json={"kind": "produktion"}, headers=H).json()["approvals"]["produktion"]
    for st in ("producerad", "packad", "levererad", "monterad"):
        assert client.patch(f"/api/hanger-sets/{sid}/hangers/{hid}", json={"status": st}, headers=H).status_code == 200
    m = client.get(f"/api/hanger-sets/{sid}/hangers/{hid}", headers=H).json()
    assert m["hanger"]["status"] == "monterad" and m["next"] and m["index"] == 1
    ph = client.post(f"/api/hanger-sets/{sid}/hangers/{hid}/photo", files={"file": ("a.jpg", b"\xff\xd8bild", "image/jpeg")},
                     data={"comment": "monterad"}, headers=H)
    assert ph.json()["n"] == 1 and client.get(f"/api/hanger-sets/{sid}/hangers/{hid}/photo/1", headers=H).content == b"\xff\xd8bild"
    # ut: material, kapplan, packlista; etiketter med QR; IFC
    wb = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/hanger-sets/{sid}/export.xlsx", headers=H).content))
    assert {"Hängare", "Material per hängare", "Material projekt", "Kapplan", "Packlista"} <= set(wb.sheetnames)
    pdf = client.get(f"/api/hanger-sets/{sid}/export.pdf", headers=H).content
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    assert doc.page_count == s["n"] and hid in doc[0].get_text()
    ifc = client.get(f"/api/hanger-sets/{sid}/export.ifc", headers=H).text
    assert ifc.count("IFCBUILDINGELEMENTPROXY(") == s["n"]
    assert client.get(f"/api/hanger-sets/{sid}/qr/{hid}.svg", headers=H).text.startswith("<svg")
    cv2 = pytest.importorskip("cv2")
    pix = doc[0].get_pixmap(dpi=300)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    url = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))[0]
    assert url.endswith(f"/montage/{sid}/{hid}")                                     # etiketten öppnar hängaren
    # ny revision: rören flyttade - den monterade hängaren är kritisk
    rv = client.post(f"/api/hanger-sets/{sid}/revise", files={"file": ("vs.ifc", _ifc(moved=150.0).encode(), "application/octet-stream")}, headers=H).json()
    assert rv["revision"] == "B" and rv["diff"]["critical"] >= 1 and rv["approvals"] == {}
    calc = client.post(f"/api/hanger-sets/{sid}/calc", json={"montor_kr_h": 700}, headers=H).json()
    assert calc["assumptions"]["antal"] == rv["n"] and calc["assumptions"]["montor_kr_h"] == 700
    other = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "annan@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    assert client.get(f"/api/hanger-sets/{sid}", headers=other).status_code == 404
