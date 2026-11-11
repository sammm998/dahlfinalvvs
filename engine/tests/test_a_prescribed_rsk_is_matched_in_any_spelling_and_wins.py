"""Ett förskrivet RSK-nummer läses i alla skrivsätt och går före egna förslag.

Från ett prov på ett riktigt underlag: "573 24 87" (Grundfos) lästes inte, och systemet föreslog i stället en egen
pump utifrån eldata och effekt. Reglerna:

  - RSK normaliseras innan något jämförs: mellanslag, punkter och bindestreck bort, exakt sju siffror kvar.
  - Finns ett förskrivet RSK eller fabrikat matchas det exakt. Egna förslag står bara när ingen förskrivning
    hittas, i en egen kolumn märkt som förslag, för teknisk granskning.
"""
from __future__ import annotations

import pytest

from vvs_engine.tb.match import MaterialIndex
from vvs_engine.tb.rsk import find, normalize, pretty


@pytest.mark.parametrize("text", ["RSK 573 24 87", "RSK 573 2487", "RSK-nr: 5732487", "RSK nr. 573.24.87",
                                  "RSK 573-24-87", "Grundfos Magna3 25-60, 573 24 87", "rsk 5732487"])
def test_every_spelling_is_the_same_number(text):
    assert find(text) == ["5732487"]


@pytest.mark.parametrize("text", ["DN 110 25 30", "Mått 120 20 30 mm", "Projekt 1234567", "tel 070 123 45 67"])
def test_measures_and_other_numbers_are_not_rsk(text):
    assert find(text) == []


def test_normalize_demands_exactly_seven_digits():
    assert normalize("573 24 87") == "5732487" and normalize("573.24.87") == "5732487"
    assert normalize("57324870") is None and normalize("573 24") is None and normalize(None) is None
    assert pretty("5732487") == "573 24 87"


def _index():
    ix = MaterialIndex()
    ix.add_material_book([
        {"a": "5732487", "n": "Cirkulationspump Grundfos Magna3 25-60 180", "rsk": "573 24 87", "gr": "Pumpar Grundfos"},
        {"a": "5739001", "n": "Cirkulationspump Wilo Stratos 25/1-6 230V 50 W", "gr": "Pumpar Wilo"},
        {"a": "5739002", "n": "Cirkulationspump Grundfos Alpha2 25-60 230V 50 W", "gr": "Pumpar Grundfos"},
        {"a": "7601001", "n": "Golvbrunn Purus Brage 150 75/110", "gr": "Golvbrunnar Purus"},
    ], label="katalog", source="katalog")
    return ix


def _post(**kw):
    base = {"name": "Cirkulationspump", "manufacturer": "", "type": "", "rsk": [], "art_nr": [], "text": "",
            "spec": {"Eleffekt": "50 W", "Spänning": "230V"}, "category": "Pumpar", "subcategory": "Pumpar"}
    return {**base, **kw}


def test_the_grundfos_pump_from_the_test_is_matched_by_its_rsk():
    m = _index().match(_post(manufacturer="Grundfos", type="Magna3 25-60", rsk=find("RSK 573 24 87")))
    assert m["status"] == "hittad" and m["hits"][0]["ref"] == "5732487" and m["basis"] == "förskrivet nummer"
    assert m["suggestions"] == []


def test_a_prescribed_number_that_is_not_in_the_catalog_is_missing_not_replaced():
    m = _index().match(_post(manufacturer="Grundfos", rsk=["5730000"]))
    assert m["status"] == "saknas" and m["hits"] == [] and "573 00 00" in m["note"]
    assert all(s["ref"] != "5730000" for s in m["suggestions"])      # det som liknar är bara förslag


def test_a_prescribed_maker_is_matched_only_by_that_maker_and_others_are_suggestions():
    m = _index().match(_post(manufacturer="Grundfos", type="Alpha2"))
    assert m["basis"] == "förskrivet fabrikat"
    assert all("Grundfos" in h["name"] for h in m["hits"])
    assert all("Grundfos" not in s["name"] for s in m["suggestions"])


def test_without_a_prescription_the_match_is_an_own_suggestion_for_review():
    m = _index().match({"name": "Golvbrunnar", "manufacturer": "", "type": "", "rsk": [], "art_nr": [],
                        "text": "Golvbrunn 150 med ansl 75/110", "spec": {}, "category": "Golvbrunnar",
                        "subcategory": "Golvbrunnar"})
    assert m["status"] in ("förslag", "saknas")
    if m["status"] == "förslag":
        assert m["hits"] == [] and m["suggestions"] and m["basis"] == "eget förslag"
