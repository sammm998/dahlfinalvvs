"""Förklaringen på bladet och materialboken talar inte samma språk - klassen är bron.

Bladet säger "LEDNINGAR AV ROSTFRIA RÖR"; boken säger "rostfritt rör", "rf AISI 304" eller "EN1.4432". Ingen
av dem använder den andras ord. Kalkylen läser förklaringen till en materialklass och söker boken på klassens
egna ord, i rätt dimension, som metervara. Och där förklaringen inte säger vad röret är gjort av väljs inget
åt någon: alternativen finns, förslaget inte - ett rör i fel material prissatt med säker min är värre än en
tom ruta.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
os.environ.setdefault("VVS_SECRET_KEY", "test")
os.environ.setdefault("VVS_DEV", "1")

from app import calc as C  # noqa: E402

# Dahls katalog i testets form: metervaror med dimensionen i benämningen och priser ur prislistan
CATALOG = [
    {"a": "R75", "n": "75 Rostfritt avloppsrör EN 1.4404 3 m", "e": "m", "p": 420.0},
    {"a": "R75b", "n": "75 Rostfritt avloppsrör EN 1.4301 6 m", "e": "m", "p": None},
    {"a": "R110", "n": "110 Rostfritt avloppsrör EN 1.4404", "e": "m", "p": 610.0},
    {"a": "X16", "n": "16 PEX-rör RIR i skyddsrör", "e": "m", "p": 22.0},
    {"a": "X16b", "n": "16 PEX-rör", "e": "m", "p": 15.0},
    {"a": "P110", "n": "110 PP-rör slätt avlopp", "e": "m", "p": 95.0},
    {"a": "P110b", "n": "110 PP avloppsrör", "e": "m", "p": None},
    {"a": "P75", "n": "75 PP-rör slätt avlopp", "e": "m", "p": 70.0},
    {"a": "K18", "n": "Kopparrör hårda raka enligt EN 18 mm, Gods tjlek. 1,0", "e": "m", "p": 80.0},
    {"a": "S22", "n": "22 Stålrör förzinkat", "e": "m", "p": 50.0},
]


@pytest.fixture(autouse=True)
def _catalog(monkeypatch):
    monkeypatch.setattr(C, "_book", lambda: {"rows": CATALOG, "kind": "dahl"})

LEGEND = [
    {"code": "X31", "description": "LEDNINGAR AV PEX IPE-XAI MED RIR", "role": "material"},
    {"code": "R8", "description": "LEDNINGAR AV ROSTFRIA RÖR", "role": "material"},
    {"code": "P2", "description": "LEDNINGAR AV PP-RÖR/ SLÄTA", "role": "material"},
    {"code": "K1", "description": "KOPPARRÖR", "role": "material"},
    {"code": "S3", "description": "SPILLVATTEN FRÅN STORKÖK", "role": "system"},
]


def _row(designation, base, dn, m=10.0):
    return {"designation": designation, "base": base, "dn": dn, "confirmed_horizontal_m": m}


def test_the_legend_words_become_a_material_class():
    assert C._material_class("LEDNINGAR AV ROSTFRIA RÖR") == "rostfri"
    assert C._material_class("LEDNINGAR AV PEX IPE-XAI MED RIR") == "pex"
    assert C._material_class("LEDNINGAR AV PP-RÖR/ SLÄTA") == "pp"
    assert C._material_class("KOPPARRÖR") == "koppar"
    assert C._material_class("PEM TRYCKRÖR") == "pe"
    assert C._material_class("SPILLVATTEN FRÅN STORKÖK") is None, "ett system är inget material"
    assert C._material_class("") is None


def test_the_articles_carry_the_class_and_the_dimension():
    """Rostfritt DN 75 ger ett rostfritt 75-rör; PEX 16 med RIR ger ett rör-i-rör; PP 110 ger ett PP-rör."""
    rf = C._find_articles(["rostfri", "rostfria"], 75, klass="rostfri")
    assert rf, "boken har rostfria 75-rör"
    for a in rf:
        assert 75.0 in ({C._leading_dim(a["n"])} | C._named_dims(a["n"])), a
        assert a["e"] == "m"
    import re
    assert all(re.search(C._CLASS["rostfri"][2], a["n"], re.I) for a in rf)
    assert rf[0]["netto"] and rf[0]["netto"] >= 1.0, "förslaget bär ett riktigt pris"

    pex = C._find_articles(["pex", "ipe-xai", "rir"], 16, klass="pex")
    assert pex and C._leading_dim(pex[0]["n"]) == 16.0
    assert "rir" in pex[0]["n"].lower(), "säger förklaringen RIR vinner rör-i-rör"

    pp = C._find_articles(["pp", "pp-rör", "släta"], 110, klass="pp")
    assert pp and C._leading_dim(pp[0]["n"]) == 110.0 and re.search(r"\bpp\b|pp-", pp[0]["n"], re.I)
    priced = [a for a in pp if (a["netto"] or 0) >= 1.0]
    unpriced = [a for a in pp if (a["netto"] or 0) < 1.0]
    assert pp[: len(priced)] == priced, "ett riktigt pris går före ett tomt"
    assert not unpriced or pp[-len(unpriced):] == unpriced


def test_a_metal_dn_is_looked_up_as_its_outer_diameter():
    """Kopparrör DN 15 ligger på dy 18 i boken; stålrör DN 100 på 114,3."""
    cu = C._find_articles(["koppar"], 15, klass="koppar")
    assert cu and all(({C._leading_dim(a["n"])} | C._named_dims(a["n"])) & {15.0, 18.0} for a in cu)
    assert C._dims_for(100, plastic=False) == {100.0, 114.3}
    assert C._dims_for(110, plastic=True) == {110.0}


def test_the_calculation_prices_every_row_the_legend_explains_and_none_it_does_not():
    rows = [_row("KV1-X31-16", "KV1-X31", 16), _row("S3-R8-110", "S3-R8", 110), _row("S1-P2-75", "S1-P2", 75),
            _row("VS1-Q9-22", "VS1-Q9", 22)]
    calc = C.build(rows, LEGEND, dict(C.DEFAULTS), {})
    by = {r["designation"]: r for r in calc["rows"]}
    for name, klass, plastic in (("KV1-X31-16", "pex", True), ("S3-R8-110", "rostfri", False), ("S1-P2-75", "pp", True)):
        r = by[name]
        assert r["artikel"] is not None and r["material_kr"] and r["material_kr"] > 0, name
        assert r["material_ord"][0] == klass and r["plast"] is plastic, name
        assert r["material_ord"].count(klass) == 1, "klassen står en gång"
    q = by["VS1-Q9-22"]
    assert q["artikel"] is None and q["material_kr"] is None, "okänd materialkod: inget förslag"
    assert q["alternativ"], "men alternativ i rätt dimension att välja bland"
    assert any("framgår inte" in c for c in calc["caveats"])
    assert calc["totals"]["utan_artikel"] == 1

    # den som väljer en artikel för hand får den, även där förslaget saknades
    pick = q["alternativ"][0]["a"]
    again = C.build(rows, LEGEND, dict(C.DEFAULTS), {"VS1-Q9-22": {"artikel": pick}})
    q2 = next(r for r in again["rows"] if r["designation"] == "VS1-Q9-22")
    assert q2["artikel"]["a"] == pick and q2["vald_artikel"] and q2["material_kr"] > 0


def test_a_stainless_drain_pipe_carries_its_outer_diameter_as_dn_and_gets_a_norm_time():
    """R8-75/110/160 är rostfria avloppsrör med ytterdiametern som beteckning: boken svarar på 76,1/114,3/168,3."""
    for dn in (75, 110, 160):
        base, source = C._norm_hours_per_m(dn, plastic=False, riser=False)
        assert base is not None and source.startswith("Stammar"), (dn, base, source)
    base, source = C._norm_hours_per_m(300, plastic=False, riser=False)
    assert base is None, "över bokens största band finns ingen tid - den hittas inte på"
    base15, src15 = C._norm_hours_per_m(15, plastic=False, riser=False)
    assert base15 is not None and src15.startswith("Kopplingsledningar"), "koppar DN 15 (dy 18) är en kopplingsledning"
