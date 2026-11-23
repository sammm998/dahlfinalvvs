"""Kravunderlaget för Smart Hangers: VS-, K- och A-modell i ett paket, validering V1-V11 före beräkning, och
upphängningarnas geometri, last och infästning enligt formeln

    L = Z_UK,bjälklag - Z_CL,rör - D_ytter/2 - t_isolering - h_klammer - h_ankare

Modellerna byggs här som de läses (geometry.read_model), så att varje regel prövas för sig."""
from __future__ import annotations

from vvs_engine.hangers import generate as G
from vvs_engine.hangers import package as PK
from vvs_engine.hangers import rules as RL
from vvs_engine.hangers.geometry import slab_type


def _vs(**kw):
    pipes = kw.pop("pipes", None) or [
        {"id": "A", "name": "Kopparrör", "start": [0, 0, 2700], "end": [6000, 0, 2700], "od": 22.0, "dn": 22,
         "material": "SS EN 1057-R290", "code": "K2", "system": "VV1", "insulation_mm": 25.0, "fall_per_mill": None,
         "storey": "Plan 1"}]
    return {"discipline": "VS", "header": {"file_name": "VS.ifc", "timestamp": "2026-11-01", "revision": "B", "frozen": False},
            "unit_found": True, "site": {"origin": [0, 0, 0], "map": None}, "pipes": pipes, "fittings": kw.pop("fittings", []),
            "storeys": [{"name": "Plan 1", "elevation": 0.0}], "skipped": [], "ceilings": [], "openings": [], "walls": [],
            "suspended": [], "obstacles": [], "channels": [], **kw}


def _k(**kw):
    return {"discipline": "K", "header": {"file_name": "K.ifc", "timestamp": "2026-11-01", "revision": "C"},
            "unit_found": True, "site": {"origin": [0, 0, 0], "map": None}, "pipes": [], "fittings": [],
            "storeys": [{"name": "Plan 1", "elevation": 0.0}], "skipped": [],
            "ceilings": kw.pop("ceilings", [{"id": "S1", "kind": "slab", "name": "HD/F 265", "zmin": 3200.0, "zmax": 3465.0,
                                              "xy": [-1000, -2000, 8000, 2000], "bbox": [-1000, -2000, 3200, 8000, 2000, 3465],
                                              "type_text": "HD/F 265", "slab_type": "HD/F"}]),
            "openings": kw.pop("openings", []), "walls": [], "suspended": [], "obstacles": [], "channels": kw.pop("channels", []), **kw}


def _a(**kw):
    return {"discipline": "A", "header": {"file_name": "A.ifc", "timestamp": "2026-11-01", "revision": "A"},
            "unit_found": True, "site": {"origin": [0, 0, 0], "map": None}, "pipes": [], "fittings": [],
            "storeys": [{"name": "Plan 1", "elevation": 0.0}], "skipped": [], "ceilings": [], "openings": [],
            "walls": kw.pop("walls", [{"id": "W1", "name": "Vägg A", "bbox": [-200, 500, 0, 7000, 700, 3200],
                                       "segment": [[-200, 600], [7000, 600]], "thickness": 200.0}]),
            "suspended": kw.pop("suspended", [{"id": "U1", "bbox": [-1000, -2000, 2400, 8000, 2000, 2450], "ztop": 2450}]),
            "obstacles": [], "channels": [], **kw}


def test_the_rod_follows_the_formula_with_insulation_clamp_and_anchor():
    m = PK.combine([_vs(), _k(), _a()])
    hs = G.generate(m)["hangers"]
    h = hs[0]
    r = RL.default()
    od_eff = 22 + 2 * 25
    h_kl = RL.table(r["formula"]["clamp_height"], od_eff)
    expected = 3200 - 2700 - od_eff / 2 - h_kl - 15                                 # HD/F-ankaret är 15 mm
    assert h["rods"][0]["calc_mm"] == round(expected)
    assert h["rods"][0]["length_mm"] == G._up(expected + r["formula"]["adjust_margin_mm"], 10)   # kapad med justermarginal
    assert h["height_source"].startswith("modell: slab") and h["slab"]["type"] == "HD/F"
    assert "HD/F-ankare" in h["anchor"] and any("mellan kanalerna" in f for f in h["flags"])
    assert h["wall"]["mm"] == 500 and "från vägg Vägg A" in h["reference"]["text"]  # A-modellens vägg
    assert h["ceiling_clearance"]["mm"] == round(2700 - od_eff / 2 - 2450)          # avstånd till undertaket
    assert any(b["text"].startswith("Rörklammer 72 mm") for b in h["bom"])          # klammer med isolering


def test_points_move_off_openings_and_snap_to_cast_in_channels():
    base = G.generate(PK.combine([_vs(), _k(), _a()]))["hangers"]
    x0 = base[0]["position"]["x"]
    k = _k(openings=[{"id": "O1", "bbox": [x0 - 60, -200, 3100, x0 + 60, 200, 3500]}])
    moved = G.generate(PK.combine([_vs(), k, _a()]))["hangers"]
    assert all(abs(h["position"]["x"] - x0) > 100 for h in moved[:1]) and "håltagning O1" in moved[0]["placed_because"]
    ch = _k(channels=[{"id": "HTA1", "start": [2300, -500, 3200], "end": [2300, 500, 3200]}])
    snapped = G.generate(PK.combine([_vs(), ch, _a()]))["hangers"]
    assert any(abs(h["position"]["x"] - 2300) < 2 and "ingjutningsskena HTA1" in h["placed_because"] for h in snapped)


def test_valve_point_load_risers_and_collisions():
    vs = _vs(pipes=_vs()["pipes"] + [
        {"id": "R1", "start": [3000, 1000, 0], "end": [3000, 1000, 3000], "od": 54.0, "dn": 54, "material": "koppar",
         "system": "KV1", "insulation_mm": 0.0, "storey": "Plan 1"},
        {"id": "X", "start": [2167, -500, 3000], "end": [2167, 500, 3000], "od": 110.0, "dn": 110, "material": "PP",
         "system": "S1", "insulation_mm": 0.0, "storey": "Plan 1"}],
        fittings=[{"id": "V1", "kind": "ventil", "at": [1500, 0, 2700], "dn": 22, "mass_kg": 8.0, "bbox": [0] * 6}])
    r = G.generate(PK.combine([vs, _k(), _a()]))
    hs = r["hangers"]
    near_valve = min((h for h in hs if h["kind"] != "stigare" and h["pipes"][0]["id"] == "A"), key=lambda h: abs(h["position"]["x"] - 1500))
    assert near_valve["point_load_kg"] == 8.0
    riser = [h for h in hs if h["kind"] == "stigare"]
    assert len(riser) == 1 and not riser[0]["rods"] and any(b["part"] == "fixpunkt" for b in riser[0]["bom"])
    hit = [h for h in hs if "X" in h["collisions"]]
    assert hit and any(f.startswith("V9") for f in hit[0]["flags"]) and any(f["rule"] == "V9" for f in r["findings"])


def test_without_k_model_no_slab_above_is_a_stop_and_a_manual_height_is_marked():
    m = PK.combine([_vs()])
    rep = PK.validate([_vs()], m, None, {})
    assert [f["rule"] for f in PK.blocking(rep)] == ["V6"]
    rep2 = PK.validate([_vs()], m, None, {"manual_heights": {"Plan 1": 3200}})
    assert not PK.blocking(rep2) and any(f["rule"] == "V6" and f["level"] == "varning" for f in rep2)
    h = G.generate(m, None, {"Plan 1": 3200})["hangers"][0]
    assert h["height_source"] == "manuell" and h["slab"]["type"] == "Platsgjutet"
    k_without_slab_here = _k(ceilings=[{"id": "S9", "kind": "slab", "zmin": 3200.0, "zmax": 3400.0, "xy": [50000, 0, 60000, 10],
                                        "bbox": [50000, 0, 3200, 60000, 10, 3400], "slab_type": None}])
    r = G.generate(PK.combine([_vs(), k_without_slab_here]))
    assert any(f["rule"] == "V6" and f["level"] == "stopp" for f in r["findings"])


def test_validation_rules_v1_to_v11():
    vs, k, a = _vs(), _k(), _a()
    k["site"] = {"origin": [25, 0, 0], "map": None}                                    # V1: 25 mm fel nollpunkt
    a["storeys"] = [{"name": "Plan 1", "elevation": 12.0}]                             # V2: 12 mm fel våningshöjd
    a["unit_found"] = False                                                             # V3
    vs["pipes"].append({"id": "B", "start": [0, 0, 2700], "end": [3000, 0, 2700], "od": 22.0, "dn": 22, "material": "",
                        "code": "", "system": "", "insulation_mm": None, "storey": "Plan 1"})   # V4 och V5
    k["ceilings"].append({"id": "S2", "kind": "slab", "zmin": 3200, "xy": [0, 0, 1, 1], "slab_type": None})  # V7
    rep = PK.validate([vs, k, a], PK.combine([vs, k, a]))
    rules = {(f["rule"], f["level"]) for f in rep}
    assert {("V1", "stopp"), ("V2", "stopp"), ("V3", "stopp"), ("V4", "stopp"), ("V5", "varning"), ("V7", "varning"),
            ("V8", "varning"), ("V10", "info")} <= rules
    v4 = next(f for f in rep if f["rule"] == "V4")
    assert v4["guids"] == ["B"] and v4.get("per_pipe")                                 # GlobalId att rätta i modellen
    r = G.generate(PK.combine([vs, k, a]))
    assert any(s["pipe"] == "B" and s["why"].startswith("V4") for s in r["skipped"])
    flat = [{"id": f"P{i}", "start": [i * 1000, 0, 2700], "end": [i * 1000 + 900, 0, 2700], "od": 110, "dn": 110,
             "material": "PP", "system": "S1", "fall_per_mill": 0, "storey": "Plan 1"} for i in range(25)]
    v11 = PK.zone_model_check(flat)
    assert {f["title"].split(":")[0] for f in v11} == {"Möjlig zonmodell", "Spillvatten utan fall"}


def test_slab_types_are_read_from_names_and_materials():
    assert slab_type("HD/F 120/27") == "HD/F" and slab_type("Bjälklag KL-trä 240") == "KL-trä"
    assert slab_type("TRP 45 trapetsplåt") == "Trapetsplåt" and slab_type("Platsgjuten betong 250") == "Platsgjutet"
    assert slab_type("Golv") is None
