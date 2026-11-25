"""Radiatorer på en VS-planritning: beteckningen (TPv4 22-218) och projekterad effekt (650W-57l/h-Kv0,25) läses
ihop, räknas per hus ur bladets HUS-rubriker och lägenhetsnummer, och korsas mot Altech enligt reglerna i
vvs_engine.radiators. Ritningen byggs här, med samma textform som en riktig bygghandling."""
from __future__ import annotations

import io
import os
import sys

import pymupdf
import pytest

from vvs_engine import radiators as R


def _sheet(path: str) -> str:
    doc = pymupdf.open()
    p = doc.new_page(width=1200, height=800)
    t = lambda x, y, s, size=5: p.insert_text((x, y), s, fontsize=size)
    t(250, 780, "HUS 1", 12)
    t(850, 780, "HUS 2", 12)
    t(200, 300, "LGH 141")
    t(350, 300, "LGH 142")
    t(800, 300, "LGH 241")
    t(950, 300, "LGH 242")
    t(180, 260, "SOVRUM 1")
    rads = [(150, 250, "TPv4 22-218", "650W-57l/h-Kv0,25"), (300, 250, "TPv4 22-212", "430W-37l/h-Kv0,16"),
            (380, 330, "2xTPv4 22-206", "150W-13l/h-Kv0,06"), (760, 250, "TPv4 22-218", "500W-44l/h-Kv0,19"),
            (900, 330, "TPv4 22-316", "780W-68l/h-Kv0,3"), (1000, 250, "TPv4 22-220", "")]
    for x, y, d, e in rads:
        t(x, y, d)
        if e:
            t(x + 2, y + 8, e)
    t(600, 60, "FÖRTECKNING 4xKV-X32-16 2xAV21")        # en annan beteckning: inte en radiator
    t(600, 70, "S1-P20 110")
    doc.save(path)
    return path


def test_labels_and_effects_are_read_and_counted_per_house(tmp_path):
    res = R.read_pdf(_sheet(str(tmp_path / "plan.pdf")))
    rs = res["radiators"]
    assert [r["designation"] for r in rs] == ["TPv4 22-218", "TPv4 22-212", "TPv4 22-206", "TPv4 22-218", "TPv4 22-316", "TPv4 22-220"]
    first = rs[0]
    assert (first["type"], first["h"], first["l"], first["w"], first["flow_lh"], first["kv"]) == ("22", 200, 1800, 650, 57.0, 0.25)
    assert first["maker"] == "Purmo" and first["kind"] == "ventil" and first["zone"] == "Hus 1" and first["room"] == "SOVRUM 1"
    assert rs[2]["count"] == 2 and rs[5]["w"] is None
    s = res["summary"]
    assert s["zones"] == ["Hus 1", "Hus 2"] and s["per_zone"] == {"Hus 1": 4, "Hus 2": 3} and s["total"] == 7
    row = next(r for r in s["rows"] if r["designation"] == "TPv4 22-218")
    assert row["per_zone"] == {"Hus 1": 1, "Hus 2": 1} and row["w_total"] == 1150
    assert next(r for r in s["rows"] if r["designation"] == "TPv4 22-220")["without_effect"] == 1


def test_designations_in_both_forms():
    assert R.parse_designation("CV22-512")[0]["designation"] == "CV 22-512"
    mm = R.parse_designation("C22-300-1200")[0]
    assert (mm["kind"], mm["h"], mm["l"]) == ("kompakt", 300, 1200)
    assert R.parse_designation("KV1-X32-16") == [] and R.parse_designation("S1-P20 110") == []
    assert R.parse_effect("650W-57l/h-Kv0,25") == {"w": 650, "flow_lh": 57.0, "kv": 0.25}


def test_crossing_follows_the_rules():
    rad = lambda h, l, t="22", kind="ventil", fam="TPV4": {"kind": kind, "type": t, "h": h, "l": l, "family": fam}
    # exakt: Altech D22 300x1200 finns och ger 540 W vid 55/45/20
    x = R.cross(rad(300, 1200), 500)
    assert x["status"] == "exakt" and x["altech"]["rsk"] == ["6672285"] and x["altech"]["w"] == 540
    # lucka i höjd: Altech saknar 200 mm -> närmaste höjd 300 i samma längd, och den låga konvektorn som alternativ
    x = R.cross(rad(200, 1800), 650)
    a = x["altech"]
    assert x["status"] == "närmaste" and (a["h"], a["l"], a["type"]) == (300, 1800, "22") and a["dh_mm"] == 100 and a["dl_mm"] == 0
    assert a["dw_need"] == 160 and any("högre" in n for n in a["notes"])
    pres, src = R.prescribed_effect(rad(200, 1800), R.DEFAULT_TEMPS)
    assert abs(pres - 662) < 10 and "Purmo Thermopanel V4" in src                  # Purmos tabell, ~ Dahls 662 W
    assert x["prescribed_w"] == pres and a["dw_prescribed"] == a["w"] - pres
    assert any(al["family"] == "KONV" for al in x["alternatives"])
    # samma storlek ger för lite: TPv4 22-316 (780 W) mot Altech D22 300x1600 (720 W) -> närmaste som räcker
    x = R.cross(rad(300, 1600), 780)
    assert x["status"] == "närmaste" and x["altech"]["w"] >= 780 and x["altech"]["notes"][0].startswith("samma storlek finns")
    assert (x["altech"]["h"], x["altech"]["l"]) == (400, 1600)                    # standard: samma längd, högre
    y = R.cross(rad(300, 1600), 780, prefer="height")
    assert (y["altech"]["h"], y["altech"]["l"]) == (300, 1800) and y["prefer"].startswith("samma höjd")   # samma höjd, längre
    assert any(al["why"] == "kraftigare typ, samma längd" for al in x["alternatives"])
    assert R.prescribed_effect(rad(600, 1200), R.DEFAULT_TEMPS)[0] > 900            # fler storlekar än 200/300 nu
    # kompakt mot typ K, och omräkning till andra temperaturer med n
    k = R.cross(rad(500, 1000, kind="kompakt", fam="C"), None)
    assert k["family"] == "K" and k["status"] == "exakt"
    w60, how = R.effect_at(x["altech"] | {"w_55_45": 810, "w_60_45": 898, "n": 1.31}, (60, 45, 20))
    assert w60 == 898 and how == "katalog 60/45/20"
    w45, how = R.effect_at({"w_55_45": 810, "w_60_45": 898, "n": 1.31}, (45, 35, 20))
    assert 400 < w45 < 500 and "n = 1.31" in how
    # räcker ingen: flaggad
    assert R.cross(rad(300, 400), 99999)["status"] == "räcker inte"


def test_the_service_reads_crosses_prices_and_exports(tmp_path_factory, monkeypatch):
    import openpyxl
    tmp = tmp_path_factory.mktemp("rad")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    for m in list(sys.modules):
        if m == "app" or m.startswith("app."):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    from app import offers as O
    price = [{"rsk": "T6672288", "namn": "x", "pris": 1.0}, {"rsk": "6672288", "namn": "ALTECH RAD 40CC INT 22- 318 VH", "pris": 1000.0, "grupp": "G1"},
             {"rsk": "T100", "namn": "TP22-218 VÄNDBAR RADIATOR M V4", "pris": 1200.0, "grupp": "G1"}]
    monkeypatch.setattr(O, "data", lambda kind: price if kind == "prislista" else [{"grupp": "G1", "pct": 20.0}])
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "rad@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        p = c.post("/api/projects", json={"name": "Najaden", "contract_form": "ABT06"}, headers=H).json()
        pdf = open(_sheet(str(tmp / "plan.pdf")), "rb").read()
        from app.db import Drawing, SessionLocal
        from app.storage import storage
        storage.put("drawings/x/plan.pdf", io.BytesIO(pdf))
        with SessionLocal() as db:
            d = Drawing(project_id=p["id"], filename="VS-500-1-014.pdf", storage_key="drawings/x/plan.pdf", sha256="a" * 64,
                        size_bytes=len(pdf), n_pages=1)
            db.add(d)
            db.commit()
            did = d.id
        r = c.get(f"/api/drawings/{did}/radiators", headers=H).json()
        assert r["summary"]["total"] == 7 and r["temps"] == "55/45/20"
        x = next(x for x in r["cross"] if x["designation"] == "TPv4 22-218")
        assert x["altech"]["price"]["netto"] == 800.0 and x["prescribed_price"]["netto"] == 960.0
        assert r["totals"]["altech"] >= 1600 and r["totals"]["price_list"]
        assert c.get(f"/api/drawings/{did}/radiators?temps=20/45", headers=H).status_code == 422
        wb = openpyxl.load_workbook(io.BytesIO(c.get(f"/api/drawings/{did}/radiators.xlsx", headers=H).content))
        assert wb.sheetnames == ["Sammanställning", "Detaljlista", "Altech-korsning", "Alternativ", "Regler och källor"]
        rows = list(wb["Sammanställning"].iter_rows(values_only=True))
        assert rows[2][4:6] == ("Hus 1", "Hus 2") and rows[-4 if rows[-1][0] and "utan" in str(rows[-1][0]) else -3][6] == 7
        # radiatorerna går in i offerten som Altech-rader med antal ur ritningen och pris ur prisfilen
        o = c.post(f"/api/projects/{p['id']}/offers", json={"kind": "materialoffert"}, headers=H)
        assert o.status_code == 200, o.text
        rad = next(r for r in o.json()["rows"] if "TPv4 22-218" in r["text"])
        assert rad["rsk"] == "6672288" and rad["antal"] == 2 and rad["netto"] == 800.0 and rad["summa"] == 1600.0
        assert any("närmaste Altech" in f for f in rad["flaggor"])
        other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "annan@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        assert c.get(f"/api/drawings/{did}/radiators", headers=other).status_code == 404
