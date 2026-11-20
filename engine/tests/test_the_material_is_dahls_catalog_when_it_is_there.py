"""Materialet är Dahls produktkatalog - den gamla materialboken från före Dahl finns inte.

Katalogen (backend/app/data/dahl_catalog.json.gz, tools/import_dahl_catalog.py) bär Dahls artikelnummer,
RSK-numret och sidan i katalogen. Priset kommer ur Dahls prislista (offertdata "prislista") och märks så; en
artikel utan pris där har inget pris.
"""
from __future__ import annotations

import gzip
import json
import os
import sys

import pytest


def _write(path, obj):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh)


@pytest.fixture()
def main(tmp_path, monkeypatch):
    st = tmp_path / "storage" / "offer"
    st.mkdir(parents=True)
    (st / "prislista.json").write_text(json.dumps({"rows": [{"rsk": "7115125", "pris": 4200.0, "grupp": "4200"}]}))
    monkeypatch.setenv("VVS_STORAGE_ROOT", str(tmp_path / "storage"))
    _write(tmp_path / "dahl_catalog.json.gz", {"n": 2, "source": "Dahls produktkatalog 2026", "origin": "https://katalog.dahl.se/", "rows": [
        {"a": "7115125", "n": "Furhoff golvbrunn Furo 142 273x273 110B", "e": "st", "p": None, "r": None, "w": None,
         "co2": None, "gr": "Golvbrunnar", "y": "", "k": "", "pre": "", "dahl": "1234567", "rsk": "7115125", "page": 412},
        {"a": "9999999", "n": "Kulventil 15", "e": "st", "p": 199.0, "r": None, "w": None, "co2": None,
         "gr": "Ventiler", "y": "", "k": "", "pre": "", "dahl": "7654321", "rsk": "9999999", "page": 600}]})
    monkeypatch.setenv("VVS_MATERIAL_DIR", str(tmp_path))
    backend = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
    sys.path.insert(0, os.path.abspath(backend))
    import app.main as m
    from app import storage as stg
    monkeypatch.setattr(stg.storage, "root", str(tmp_path / "storage"), raising=False)
    monkeypatch.setattr(m, "_MATERIAL", None)
    yield m
    m._MATERIAL = None


def test_the_catalog_is_the_material_and_keeps_its_own_numbers(main):
    book = main._material()
    assert book["kind"] == "dahl" and book["source"] == "Dahls produktkatalog 2026" and book["n"] == 2
    furo = next(r for r in book["rows"] if r["rsk"] == "7115125")
    assert furo["dahl"] == "1234567" and furo["page"] == 412


def test_a_price_comes_from_dahls_price_list_and_says_so(main):
    rows = {r["rsk"]: r for r in main._material()["rows"]}
    assert rows["7115125"]["p"] == 4200.0 and rows["7115125"]["p_src"] == "prislista" and rows["7115125"]["k"] == "4200"
    assert rows["9999999"]["p"] == 199.0 and rows["9999999"]["p_src"] == "katalog"


def test_the_search_finds_dahls_own_article_number(main):
    out = main.materials(q="1234567", user=None)
    assert out["total"] == 1 and out["book"]["kind"] == "dahl"


def test_the_calculation_prices_from_the_catalog_with_the_price_list(main):
    """Kalkylen och offerten räknar på katalogen med prislistans priser - aldrig på en gammal materialbok."""
    book = main._material_book()
    assert book["kind"] == "dahl" and book["priced"] == 2
    assert not os.path.exists(os.path.join(os.path.dirname(main.__file__), "data", "material.json.gz"))
