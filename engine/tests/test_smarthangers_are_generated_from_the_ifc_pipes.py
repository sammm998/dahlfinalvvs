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


def _ifc(extra_valve: bool = True, mapped: bool = True, moved: float = 0.0, slab: bool = False) -> str:
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
    if slab:
        # ett bjälklag (HD/F) med underkant 3100 över rören (1000-7000 x -1000-1300), som rektangel extruderad uppåt
        p2 = a("IFCCARTESIANPOINT((0.,0.))")
        ax2 = a(f"IFCAXIS2PLACEMENT2D(#{p2},$)")
        prof = a(f"IFCRECTANGLEPROFILEDEF(.AREA.,$,#{ax2},6000.,2300.)")
        sol = a(f"IFCEXTRUDEDAREASOLID(#{prof},#{world},#{z},50.)")
        body = a(f"IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#{sol}))")
        pds = a(f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{body}))")
        lp = a(f"IFCAXIS2PLACEMENT3D(#{a('IFCCARTESIANPOINT((4000.,150.,3100.))')},#{z},#{x})")
        els.append(a(f"IFCSLAB('U',$,'HD/F 265',$,$,#{a(f'IFCLOCALPLACEMENT(#{site},#{lp})')},#{pds},$,.FLOOR.)"))
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
    assert all("takhöjd saknas - ange underkant bjälklag för våningen/zonen" in h["flags"] for h in no["hangers"])


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
    assert RL.spacing(r, "plast", 110)[0] == 1900 and RL.spacing(r, "stål", 65)[0] == 3500
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
    assert text.startswith("ISO-10303-21;") and text.count("IFCDISCRETEACCESSORY(") == len(hs)
    assert "'Pset_SmartHanger'" in text and f"'{hs[0]['id']}'" in text and "IFCLABEL('monterad')" in text
    from vvs_engine.ifc.reader import _records
    R = _records(text.splitlines())
    assert sum(1 for c, _ in R.values() if c == "IFCDISCRETEACCESSORY") == len(hs)
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
    assert {"Hängare", "Material per hängare", "Material projekt", "Kapplan", "Packlista", "Material per kolli"} <= set(wb.sheetnames)
    # referensmått från vald vägg/gridlinje, och ritningsutsnittet i montageguiden
    rs = client.post(f"/api/hanger-sets/{sid}/references", json={"references": [{"name": "Grid 1", "axis": "x", "value": 1000},
                                                                                  {"name": "Vägg A", "axis": "y", "value": -500}]}, headers=H).json()
    h0 = next(h for h in rs["hangers"] if h["id"] == hid)
    assert [l["name"] for l in h0["reference"]["lines"]] == ["Grid 1", "Vägg A"]
    assert h0["reference"]["text"].startswith(f"{abs(h0['position']['x'] - 1000):,} mm från Grid 1".replace(",", " "))
    nb = client.get(f"/api/hanger-sets/{sid}/hangers/{hid}", headers=H).json()["nearby"]
    assert nb["pipes"] and any(x["id"] == hid for x in nb["hangers"]) and len(nb["references"]) == 2
    pdf = client.get(f"/api/hanger-sets/{sid}/export.pdf", headers=H).content
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    assert doc.page_count == s["n"] and hid in doc[0].get_text()
    ifc = client.get(f"/api/hanger-sets/{sid}/export.ifc", headers=H).text
    assert ifc.count("IFCDISCRETEACCESSORY(") == s["n"]
    assert client.get(f"/api/hanger-sets/{sid}/qr/{hid}.svg", headers=H).text.startswith("<svg")
    cv2 = pytest.importorskip("cv2")
    url = ""
    for dpi in (300, 200, 400, 250):                                  # avläsningen är känslig för upplösningen
        pix = doc[0].get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        url = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))[0] or url
        if url:
            break
    assert url.endswith(f"/montage/{sid}/{hid}")                                     # etiketten öppnar hängaren
    # ny revision: rören flyttade - den monterade hängaren är kritisk
    rv = client.post(f"/api/hanger-sets/{sid}/revise", files={"file": ("vs.ifc", _ifc(moved=150.0).encode(), "application/octet-stream")}, headers=H).json()
    assert rv["revision"] == "B" and rv["diff"]["critical"] >= 1 and rv["approvals"] == {}
    calc = client.post(f"/api/hanger-sets/{sid}/calc", json={"montor_kr_h": 700}, headers=H).json()
    assert calc["assumptions"]["antal"] == rv["n"] and calc["assumptions"]["montor_kr_h"] == 700
    other = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "annan@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    assert client.get(f"/api/hanger-sets/{sid}", headers=other).status_code == 404


def test_plastic_spacing_follows_the_walraven_en806_table_and_rods_carry_the_bevego_number():
    r = RL.default()
    assert RL.spacing(r, "plast", None, "KV1", 32)[0] == 1000 and RL.spacing(r, "plast", None, "VV1", 32)[0] == 650
    assert "Walraven" in RL.spacing(r, "plast", None, "VVC1", 20)[1]
    hs = G.generate(pipes(_ifc()), {"geometry": {**r["geometry"], "max_rod": 2500}})["hangers"]
    rod = next(b for b in hs[0]["bom"] if b["part"] == "gängstång")
    size = hs[0]["rods"][0]["size"]
    assert rod.get("art") == {"M8": "51721008", "M10": "51721010"}.get(size) and "NP-101-2024" in rod.get("art_source", "")


def _reading(tmp):
    """En analyserad 2D-ritning: två parallella stålrör VS2-S13-35 och ett plaströr KV1-E17-32 i skala 1:50."""
    import json
    sh = tmp / "sheets" / "0"
    sh.mkdir(parents=True)
    (tmp / "drawing-legend.json").write_text(json.dumps({"entries": [
        {"code": "S13", "description": "STÅLRÖR/ TUNNVÄGGIGA", "role": "material"},
        {"code": "E17", "description": "PLASTRÖR/ PEN", "role": "material"}]}))
    k = 0.017638888888888885                                 # m per pdf-punkt i 1:50
    L = 6.0 / k                                              # 6 m
    pp = [{"physical_pipe_id": "a", "system": "VS2", "designation": "VS2-S13-35", "dn": 35, "evidence_state": "CONFIRMED",
           "geometry": [[[100, 100], [100 + L / 2, 100], [100 + L, 100]]]},
          {"physical_pipe_id": "b", "system": "VS2", "designation": "VS2-S13-35", "dn": 35, "evidence_state": "CONFIRMED",
           "geometry": [[[100, 100 + 0.3 / k], [100 + L, 100 + 0.3 / k]]]},
          {"physical_pipe_id": "c", "system": "KV1", "designation": "KV1-E17-32", "dn": 32, "evidence_state": "CONFIRMED",
           "geometry": [[[100, 400], [100, 400 + 3.0 / k], [100 + 2.0 / k, 400 + 3.0 / k]]]},
          {"physical_pipe_id": "d", "system": "S1", "designation": "S1-P3-110", "dn": 110, "evidence_state": "IN_HATCHED_AREA",
           "geometry": [[[0, 0], [50, 0]]]}]
    (sh / "physical-pipes.json").write_text(json.dumps({"physical_pipes": pp}))
    (sh / "quantities.json").write_text(json.dumps({"scale": {"meters_per_pdf_point": k, "state": "VERIFIED",
                                                               "evidence": [{"kind": "scale_text", "detail": {"ratio": 50}}]}}))
    return tmp


def test_hangers_from_a_2d_drawing_when_there_is_no_ifc(tmp_path):
    from vvs_engine.hangers.from_drawing import ceilings_from, pipes_from_reading, sheets_in_reading
    root = _reading(tmp_path)
    assert sheets_in_reading(str(root))[0] == {"name": "Blad 1", "page": 0, "confirmed": 3, "pipes": 4, "m": 0.0,
                                               "scale": "1:50", "scale_state": "VERIFIED", "usable": True}
    m = pipes_from_reading(str(root), {"ceiling_mm": 2700, "drop_mm": 300}, "VS.pdf")
    assert len(m["pipes"]) == 4                              # a rak (två punkter i linje blir en bit), b, c i två bitar
    assert any("inte bekräftat" in s["why"] for s in m["skipped"])
    a = next(p for p in m["pipes"] if p["id"].startswith("a:"))
    assert abs((a["end"][0] - a["start"][0]) - 6000) < 1 and a["material"].startswith("STÅL") and a["start"][2] == 2700 - 300 + 17.5
    r = G.generate(m, None, ceilings_from(m))
    hs = r["hangers"]
    assert hs[0]["id"].startswith("B1-") and all(h["height_source"] == "antagen (2D-ritning)" for h in hs)
    assert all("höjd ur 2D-ritning - mät på plats innan produktion" in h["flags"] for h in hs)
    steel = [h for h in hs if any(p["system"] == "VS2" for p in h["pipes"])]
    assert all(h["kind"] == "takjärn" and len(h["pipes"]) == 2 for h in steel)
    # rören vilar på takjärnet med underkanten 300 mm under taket: pendeln = 300 + 30 + 41 + 40, uppåt till 10 mm
    assert steel[0]["rods"][0]["length_mm"] == 420 and not any("högre" in f for f in steel[0]["flags"])
    xs = sorted(h["position"]["x"] for h in steel)
    assert max(b - a for a, b in zip(xs, xs[1:])) <= RL.spacing(RL.default(), "stål", 35)[0]
    kv = [h for h in hs if any(p["system"] == "KV1" for p in h["pipes"])]
    assert kv and "Walraven" in kv[0]["pipes"][0]["spacing_rule"]                     # plast kallvatten 32: 1000 mm


def test_the_service_makes_hangers_from_a_project_drawing(client, tmp_path):
    import uuid
    from app.db import AnalysisJob, Drawing, SessionLocal
    from app.storage import storage
    H = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "ritning@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    p = client.post("/api/projects", json={"name": "Kv Ritning", "contract_form": "ABT06"}, headers=H).json()
    key = f"results/{uuid.uuid4().hex}"
    import os
    import shutil
    dst = storage.path(key)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(_reading(tmp_path / "r"), dst)
    with SessionLocal() as db:
        d = Drawing(project_id=p["id"], filename="VS-plan.pdf", storage_key="x", sha256="0" * 64, size_bytes=1)
        db.add(d)
        db.flush()
        db.add(AnalysisJob(drawing_id=d.id, status="COMPLETED", result_key=key))
        db.commit()
        did = d.id
    lst = client.get(f"/api/projects/{p['id']}/hangers/drawings", headers=H).json()
    assert lst[0]["drawing_id"] == did and lst[0]["sheets"][0]["confirmed"] == 3
    r = client.post(f"/api/projects/{p['id']}/hangers/from-drawing", json={"drawing_id": did, "ceiling_mm": 2700, "drop_mm": 300}, headers=H)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["n"] > 0 and s["settings"]["source"] == "2D-ritning" and s["hangers"][0]["height_source"] == "antagen (2D-ritning)"
    rod = s["hangers"][0]["rods"][0]["length_mm"]
    s2 = client.post(f"/api/hanger-sets/{s['id']}/regenerate", json={"heights": {"Blad 1": 3000}, "drop_mm": 500}, headers=H).json()
    assert s2["hangers"][0]["rods"][0]["length_mm"] == rod + 200                       # 500 mm under taket i stället för 300



def test_the_ceiling_height_is_read_from_the_slab_or_ceiling_in_the_model():
    m = pipes(_ifc(slab=True))
    assert m["ceilings"] and m["ceilings"][0]["zmin"] == 3100.0 and m["ceilings"][0]["kind"] == "slab"
    assert m["ceilings"][0]["slab_type"] == "HD/F"
    hs = G.generate(m)["hangers"]
    assert all(h["ceiling_z"] == 3100 and h["height_source"].startswith("modell: slab") for h in hs)
    assert hs[0]["rods"][0]["length_mm"] == 680 - 150                                 # 150 mm lägre tak än beräknat
    man = G.generate(m, None, {"Plan 10": 3300})["hangers"]                           # inmatat går före modellen
    assert all(h["height_source"].startswith("manuell") for h in man)


def test_packing_follows_the_delivery_stage_and_the_volume():
    hs = G.generate(pipes(_ifc()))["hangers"]
    for h in hs[:2]:
        h["zone"] = "stråk A"
    k = G.pack(hs, {"packing": {"max_per_kolli": 50, "max_kg_per_kolli": 100.0, "max_volume_l_per_kolli": 1e6}},
               etapper={"Plan 10|stråk A": "Etapp 1", "Plan 10": "Etapp 2"})
    assert [x["etapp"] for x in k] == ["Etapp 1", "Etapp 2"] and len(k[0]["hangers"]) == 2
    assert hs[0]["pack"]["etapp"] == "Etapp 1"
    small = G.pack(hs, {"packing": {"max_per_kolli": 50, "max_kg_per_kolli": 100.0,
                                    "max_volume_l_per_kolli": G.volume_l(hs[0]) * 2 + 0.01}})
    assert all(len(x["hangers"]) <= 2 for x in small) and all(x["l"] <= G.volume_l(hs[0]) * 2 + 0.01 for x in small)


def test_roles_decide_who_may_do_what(client):
    owner = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "agare@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    fitter = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "montor2@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    p = client.post("/api/projects", json={"name": "Roller", "contract_form": "ABT06"}, headers=owner).json()
    s = client.post(f"/api/projects/{p['id']}/hangers", files={"file": ("vs.ifc", _ifc().encode(), "application/octet-stream")},
                    data={"heights": "{}"}, headers=owner).json()
    sid, hid = s["id"], s["hangers"][0]["id"]
    assert client.get(f"/api/hanger-sets/{sid}", headers=fitter).status_code == 404          # inte inbjuden
    assert client.put(f"/api/hanger-sets/{sid}/members", json={"members": {"x@dahl.se": ["chef"]}}, headers=owner).status_code == 422
    assert client.put(f"/api/hanger-sets/{sid}/members", json={"members": {"Montor2@dahl.se": ["montor"]}}, headers=owner).json()["members"] == {"montor2@dahl.se": ["montor"]}
    got = client.get(f"/api/hanger-sets/{sid}/hangers/{hid}", headers=fitter).json()
    assert got["my_roles"] == ["montor"]
    assert [x["id"] for x in client.get("/api/hanger-sets-shared", headers=fitter).json()] == [sid]
    no = client.patch(f"/api/hanger-sets/{sid}/hangers/{hid}", json={"position": {"x": 1}}, headers=fitter)
    assert no.status_code == 403 and "granskare" in no.json()["detail"].lower()
    assert client.post(f"/api/hanger-sets/{sid}/approve", json={"kind": "konstruktion"}, headers=fitter).status_code == 403
    assert client.patch(f"/api/hanger-sets/{sid}/hangers/{hid}", json={"status": "producerad"}, headers=fitter).status_code == 403
    ok = client.patch(f"/api/hanger-sets/{sid}/hangers/{hid}", json={"status": "monterad", "comment": "klar"}, headers=fitter)
    assert ok.status_code == 200 and ok.json()["hanger"]["history"][-1]["user"] == "montor2@dahl.se"
    assert client.patch(f"/api/hanger-sets/{sid}/hangers/{hid}", json={"deviation": "ej möjlig"}, headers=fitter).status_code == 200
    assert client.delete(f"/api/hanger-sets/{sid}", headers=fitter).status_code == 403
    pk = client.post(f"/api/hanger-sets/{sid}/packing", json={"max_per_kolli": 2, "etapper": {"Plan 10": "Etapp 1"}}, headers=owner).json()
    assert all(len(k["hangers"]) <= 2 and k["etapp"] == "Etapp 1" for k in pk["kollin"])


def test_a_model_package_is_read_validated_and_calculated_in_the_background(client):
    import io
    import os
    import time
    import zipfile

    import openpyxl
    os.environ["VVS_HANGERS_INLINE"] = "1"
    try:
        H = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "paket@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        p = client.post("/api/projects", json={"name": "Paket", "contract_form": "ABT06"}, headers=H).json()
        # bara VS: inget bjälklag och ingen höjd - Stopp, inga hängare
        r = client.post(f"/api/projects/{p['id']}/hanger-packages",
                        files=[("files", ("4075-V-50-V-1.ifc", _ifc(slab=False).encode(), "application/octet-stream"))], headers=H)
        assert r.status_code == 200, r.text
        st = client.get(f"/api/hanger-sets/{r.json()['id']}/package", headers=H).json()
        assert st["job"]["state"] == "stoppad" and st["n"] == 0 and any(f["rule"] == "V6" and f["level"] == "stopp" for f in st["validation"])
        assert st["storeys"] == ["Plan 10"] and st["pipe_count"] > 0          # våningen att ange takhöjd för, trots stoppet
        # en uppskattad höjd släpper beräkningen, märkt som uppskattad
        st2 = client.post(f"/api/hanger-sets/{st['id']}/package-settings", json={"estimate_above": 400}, headers=H).json()
        pk = client.get(f"/api/hanger-sets/{st2['id']}/package", headers=H).json()
        assert pk["job"]["state"] == "klar" and pk["n"] > 0
        assert client.post(f"/api/hanger-sets/{st['id']}/package-settings", json={"zone_slab_types": {"x": "Lera"}}, headers=H).status_code == 422
        # VS + K: bjälklaget ur K-modellen, ankare ur bjälklagstypen
        r = client.post(f"/api/projects/{p['id']}/hanger-packages",
                        files=[("files", ("4075-V-50-V-1.ifc", _ifc(slab=False).encode(), "application/octet-stream")),
                               ("files", ("4075-K-50-K-1.ifc", _ifc(slab=True).encode(), "application/octet-stream"))], headers=H)
        sid = r.json()["id"]
        pk = client.get(f"/api/hanger-sets/{sid}/package", headers=H).json()
        assert [f["discipline"] for f in pk["files"]] == ["VS", "K"] and pk["job"]["state"] == "klar" and pk["has"]["K"]
        s = client.get(f"/api/hanger-sets/{sid}", headers=H).json()
        h = s["hangers"][0]
        assert h["height_source"].startswith("modell: slab") and h["slab"]["type"] == "HD/F" and "HD/F" in h["anchor"]
        csv_ = client.get(f"/api/hanger-sets/{sid}/export.csv", headers=H).content.decode("utf-8-sig")
        assert csv_.splitlines()[0].startswith("ID;Våning;Zon") and len(csv_.splitlines()) == len(s["hangers"]) + 1
        assert client.get(f"/api/hanger-sets/{sid}/export.dxf", headers=H).text.rstrip().endswith("EOF")
        z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/hanger-sets/{sid}/export.bcf", headers=H).content))
        assert "bcf.version" in z.namelist()
        assert client.get(f"/api/hanger-sets/{sid}/export.rapport", headers=H).content[:4] == b"%PDF"
        wb = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/hanger-sets/{sid}/export.artiklar", headers=H).content))
        assert wb.sheetnames == ["Artiklar per zon", "Summa per zon"] and wb.active.max_row > 2
        wb2 = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/hanger-sets/{sid}/export.xlsx", headers=H).content))
        assert "Punktlista" in wb2.sheetnames
        tj = next((h for h in s["hangers"] if h["kind"] == "takjärn"), None)
        if tj:
            client.post(f"/api/hanger-sets/{sid}/groups", json={"split": [tj["id"]]}, headers=H)
            s2 = client.get(f"/api/hanger-sets/{sid}", headers=H).json()
            assert s2["settings"]["groups"]["split"] and not any(h["kind"] == "takjärn" and {p["id"] for p in h["pipes"]} & set(s2["settings"]["groups"]["split"]) for h in s2["hangers"])
            assert client.post(f"/api/hanger-sets/{sid}/groups", json={"reset": True}, headers=H).status_code == 200
        a = client.get(f"/api/hanger-sets/{sid}/articles", headers=H).json()
        assert a["rows"] and "total" in a["totals"]
    finally:
        os.environ.pop("VVS_HANGERS_INLINE", None)


def test_the_discipline_is_read_from_the_file_name():
    import os
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    from app.prefab_package import guess_discipline
    assert guess_discipline("4075-V-50-V-30001.ifc") == "VS" and guess_discipline("4075-K-40-K-1001.ifc") == "K"
    assert guess_discipline("Proj_A_Plan2.ifc") == "A" and guess_discipline("4075-E-60-E-1.ifc") == "Ö"


def test_hanger_parts_get_dahl_articles_and_prices_from_the_price_list(client, monkeypatch):
    from app import offers as O
    from app import prefab_package as PP
    price = [{"rsk": "T1001", "namn": "GÄNGSTÅNG M10X1000 FZB NOVIPRO", "pris": 100.0, "grupp": "G1", "enhet": "STK"},
             {"rsk": "T1002", "namn": "GÄNGSTÅNG M10X2000 8.8 FZV", "pris": 90.0, "grupp": "G1", "enhet": "STK"},
             {"rsk": "T1003", "namn": "BRICKA BRB M10X20 A4 2343", "pris": 5.0, "grupp": "G2", "enhet": "STK"},
             {"rsk": "T1004", "namn": "BRICKA BRB M10X22 FZB A", "pris": 3.0, "grupp": "G2", "enhet": "STK"},
             {"rsk": "T1005", "namn": "RÖRKLAMMER KSB2 GUMMI 20-23MM", "pris": 10.0, "grupp": "G3", "enhet": "STK"},
             {"rsk": "T1006", "namn": "20,5-22 TUDEL KLAMMA DK22 FZV", "pris": 10.0, "grupp": "G3", "enhet": "PAR"},
             {"rsk": "T1007", "namn": "STRUTSKENA 41X41X1,5 3M FFZV", "pris": 300.0, "grupp": "G4", "enhet": "STK"}]
    monkeypatch.setattr(O, "data", lambda kind: price if kind == "prislista" else [{"grupp": "G1", "pct": 25.0}])
    rod = PP.hanger_article({"part": "gängstång", "text": "Gängstång M10 förzinkad"})
    assert rod["a"] == "T1001" and rod["e"] == "m" and rod["brutto"] == 100.0 and rod["netto"] == 75.0   # Novipro, 25 % grundrabatt
    assert PP.hanger_article({"part": "bricka", "text": "Bricka M10"})["a"] == "T1004"                    # förzinkad, inte A4
    assert PP.hanger_article({"part": "rörklammer", "text": "Rörklammer 22 mm med gummiinlägg M8-anslutning"})["a"] == "T1005"
    assert PP.hanger_article({"part": "rörklammer", "text": "Rörklammer 160 mm M10-anslutning"}) is None       # inget i måttet
    rail = PP.hanger_article({"part": "takjärn", "text": "Takjärn 41x41 (U-profil)"})
    assert rail["a"] == "T1007" and abs(rail["brutto"] - 300 / 3) < 0.01                                    # kr per meter
    assert PP.hanger_article({"part": "infästning", "text": "Träskruv med gängad hylsa M8"}) is None


def test_a_project_with_hangers_and_offers_can_be_deleted(client):
    H = {"Authorization": "Bearer " + client.post("/api/auth/register", json={"email": "bort@dahl.se", "password": "hemligt1"}).json()["access_token"]}
    p = client.post("/api/projects", json={"name": "Bort", "contract_form": "ABT06"}, headers=H).json()
    s = client.post(f"/api/projects/{p['id']}/hangers", files={"file": ("vs.ifc", _ifc().encode(), "application/octet-stream")},
                    data={"heights": "{}"}, headers=H)
    assert s.status_code == 200
    r = client.delete(f"/api/projects/{p['id']}", headers=H)
    assert r.status_code == 200, r.text
    assert client.get(f"/api/hanger-sets/{s.json()['id']}", headers=H).status_code == 404
