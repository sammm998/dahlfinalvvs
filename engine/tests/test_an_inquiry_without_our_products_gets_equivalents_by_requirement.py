"""En förfrågan som inte nämner våra produkter får likvärdiga alternativ ur Alterna, på krav och inte på namn.

Facit är det manuella förslaget för Ryttargården 2A: INR Core Solid XS 60 -> Alterna Isella Aqua underskåp,
INR Stage 60 -> Ariella Aqua 60, Hafa Go -> Ray elhanddukstork, INR Linc Angle -> Lusso duschhörna, Beslagdesign
Base 200 -> Picto krokar/hållare, Spegel (Okänd) -> Basic planspegel. Matchningen ska komma fram till samma sak ur
sort och mått, och säga när ett krav inte är uppfyllt (kommoden 50 cm har bara en 60 cm i facit).
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import pymupdf
import pytest

from vvs_engine.tb.equivalent import category_of, dims_of, requirements, suggest
from vvs_engine.tb.inquiry import read_inquiry
from vvs_engine.tb.legend import legend_items, read_legend
from vvs_engine.tb.rooms import read_room_description

SEED = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "app", "data", "alterna_seed.json"),
                      encoding="utf-8"))["products"]

FACIT = [  # (pos, sakvara, fabrikat, typ) -> RSK i facit
    ("11", "Spegel RWC", "", "", "8948526"),
    ("12", "Spegel WC", "", "", "8948526"),
    ("15", "WC-papperhållare", "Beslagdesign", "Base 200", "8920499"),
    ("16", "Handdukskrok 4", "Beslagdesign", "Base 200", "8920498"),
    ("17", "Handdukstork", "Hafa", "Go 1509635", "8753247"),
    ("19", "Tvättställskommod 60", "INR", "Core Solid XS 60", "8912079"),
    ("20", "Spegelskåp 60", "INR", "Stage 60", "8912081"),
    ("22", "Spegelskåp 50", "INR", "Stage 50", "8946360"),
    ("", "Duschväggar", "INR", "Linc Angle", "7333529"),
]


@pytest.mark.parametrize("pos,name,maker,typ,rsk", FACIT)
def test_the_manual_facit_is_reached_from_kind_and_size(pos, name, maker, typ, rsk):
    s = suggest({"code": pos, "name": name, "manufacturer": maker, "type": typ, "text": "", "spec": {}}, SEED)
    best = s["candidates"][0]
    assert best["rsk"] == rsk and best["state"] == "uppfyller angivna krav"
    assert "inte automatiskt fastställd" in s["disclaimer"]


def test_a_requirement_that_is_not_met_is_said_not_hidden():
    s = suggest({"name": "Tvättställskommod 50", "manufacturer": "INR", "type": "Core Solid XS 50", "text": "", "spec": {}},
                SEED)
    best = s["candidates"][0]
    assert best["rsk"] == "8912079" and best["state"] == "avviker"
    assert any(c["krav"] == "Bredd" and c["status"] == "ej uppfyllt" and "600" in c["detalj"] for c in best["checks"])


def test_kind_and_size_are_read_however_they_are_written():
    assert category_of("Spegelskåp INR, typ Stage") == "spegelskåp"          # inte en spegel
    assert category_of("Kommod INR, typ Core Solid XS") == "kommod"
    assert category_of("Handukstork, typ Hafa Go") == "handdukstork"          # som det stod, felstavat
    assert category_of("Toalettrulleshållare, typ Smedbo RS341") == "pappershållare"
    assert dims_of("Kommod INR, typ Core Solid XS, b=60 cm", "kommod") == {"bredd": 600}
    assert dims_of("planspegel 450 x 900") == {"bredd": 450, "höjd": 900}
    assert dims_of("Klädkrok, Placering +1200 ÖFG, cc 100 mm", "krok") == {}
    req = requirements({"name": "Spegelskåp", "manufacturer": "INR", "type": "Stage", "or_equal": True,
                        "text": "b=50 cm, integrerad belysning och eluttag, Svanenmärkt", "spec": {}})
    assert req["dims"] == {"bredd": 500} and req["labels"] == ["Svanen"]
    # ett miljökrav som produktdatan inte säger något om är okänt, inte uppfyllt
    best = suggest({"name": "Spegelskåp", "manufacturer": "INR", "type": "Stage", "text": "b=50 cm, Svanenmärkt",
                    "spec": {}}, SEED)["candidates"][0]
    assert best["state"] == "att verifiera" and any(c["krav"] == "Miljökrav" and c["status"] == "okänt" for c in best["checks"])


def _page(doc, lines):
    pg = doc.new_page(width=595, height=842)
    y = 60
    for t in ["TYPRUMSBESKRIVNING", "Mallnamn: Rumsbeskrivning utan AMA kod / Mallversion: 4", "KULÖR / GLANS"] + lines:
        if t:
            pg.insert_text((60, y), t, fontname="helv", fontsize=9)
        y += 13


def _room_doc():
    doc = pymupdf.open()
    _page(doc, ["STUDENTBOSTÄDER", "D 1101/1201/1301,  1102/1202/1302,", "1103/1203/1303", "", "Tambur", "", "Golv",
                "Ekparkett", ""])
    _page(doc, ["", "Badrum", "", "Golv", "Klinker 100x100 mm, el. likv.", "", "Fast inredning",
                "Kommod INR, typ Core Solid XS, b=60 cm, med slät lucka, vit kulör", "", "0500-N",
                "\"Pure White\". Vitt porslin.", "", "Spegelskåp INR, typ Stage, b=60 cm, med integrerad belysning och eluttag,",
                "vit kulör \"Pure White\".", "", "Toalettrulleshållare, typ Smedbo RS341", "Duschdraperistång", "",
                "Enl. A-ritning våtrumuppställningar", "", "Lös inredning", "Kombimaskin, vitt utseende", "", "Övrigt", "-"])
    _page(doc, ["", "WC/D (F1403, F1502)", "", "Fast inredning",
                "Kommod INR, typ Core Solid XS, b=50 cm, med slät lucka, varmgrå kulör"])
    return doc


def test_a_room_description_is_read_per_room_type_with_the_number_of_rooms():
    items = read_room_description(_room_doc())["items"]
    got = [(i["category"], i["name"], i["manufacturer"], i["type"], i["quantity"], i["spec"].get("Bredd")) for i in items]
    assert ("Badrum – Studentbostäder", "Kommod INR", "INR", "Core Solid XS", 9.0, "60 cm") in got     # 3 x 3 lägenheter
    assert ("Badrum – Studentbostäder", "Spegelskåp INR", "INR", "Stage", 9.0, "60 cm") in got
    assert ("Badrum – Studentbostäder", "Toalettrulleshållare", "Smedbo", "RS341", 9.0, None) in got
    assert ("WC/D – Studentbostäder", "Kommod INR", "INR", "Core Solid XS", 2.0, "50 cm") in got        # F1403, F1502
    assert not any("Golv" in i["subcategory"] or "Klinker" in i["name"] for i in items)
    kommod = next(i for i in items if i["name"] == "Kommod INR" and i["quantity"] == 9.0)
    assert kommod["spec"]["Kulör"] == "Pure White" and kommod["or_equal"] is False


def _legend_doc():
    doc = pymupdf.open()
    pg = doc.new_page(width=2384, height=1684)
    pg.insert_text((2048, 170), "UTRUSTNING", fontname="helv", fontsize=9.7)
    rows = [("11", "Spegel RWC, infälld, mått enligt ritning I 01"),
            ("15", "Toalettrulleshållare, typ Beslagdesign Base 200, el. likv."),
            ("19", "Kommod INR, typ Core Solid XS, b=60 cm, slät lucka,")]
    y = 181
    for n, t in rows:
        pg.insert_text((2048, y), n, fontname="helv", fontsize=9.7)
        pg.insert_text((2069, y), t, fontname="helv", fontsize=9.7)
        y += 30
    pg.insert_text((2069, y - 19), 'kulör "Warm Clay", vitt porslin. Eller likv.', fontname="helv", fontsize=9.7)
    pg.insert_text((142, 344), "TYP A - STUDENTBOSTÄDER", fontname="helv", fontsize=11.7)
    pg.insert_text((1107, 344), "TYP I - RWC 1009", fontname="helv", fontsize=11.7)
    for x, n in ((400, "15"), (430, "19")):
        pg.insert_text((x, 500), n, fontname="helv", fontsize=5.8)
    pg.insert_text((1300, 500), "11", fontname="helv", fontsize=5.8)
    pg.insert_text((400, 520), "3", fontname="helv", fontsize=7.8)           # ett vynummer, ingen position
    return doc


def test_the_equipment_legend_gives_positions_and_the_types_they_stand_in():
    lg = read_legend(_legend_doc())
    items = {i["code"]: i for i in legend_items(lg)}
    assert set(items) == {"11", "15", "19"}
    assert items["11"]["quantity"] == 1.0 and "I (RWC 1009)" in items["11"]["spec"]["Våtrumstyper"]
    assert items["15"]["manufacturer"] == "Beslagdesign" and items["15"]["quantity"] is None   # lägenhetstyp: antal okänt här
    assert items["19"]["spec"]["Bredd"] == "60 cm" and "Warm Clay" in items["19"]["text"]
    assert items["19"]["spec"]["Våtrumstyper"].startswith("A (STUDENTBOSTÄDER)")


def test_a_zip_inquiry_combines_legend_and_room_description_and_flags_conflicts():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Typrumsbeskrivning.pdf", _room_doc().tobytes())
        z.writestr("Våtrumsuppställningar.pdf", _legend_doc().tobytes())
        z.writestr("Plan.pdf", pymupdf.open().tobytes() if False else _plain())
    r = read_inquiry("förfrågan.zip", buf.getvalue())
    kinds = {d["name"]: d["kind"] for d in r["meta"]["documents"]}
    assert kinds["Typrumsbeskrivning.pdf"] == "rumsbeskrivning" and kinds["Våtrumsuppställningar.pdf"].startswith("förteckning")
    assert kinds["Plan.pdf"].startswith("ritning/plan")
    pos = {i["code"]: i for i in r["items"] if i["code"]}
    # studentbostädernas 9 lägenheter, eftersom positionen står i alla deras typer
    assert pos["15"]["quantity"] == 9.0 and pos["19"]["quantity"] == 9.0
    # rumsbeskrivningen säger Smedbo där förteckningen säger Beslagdesign: flaggat, inte en rad till
    assert pos["15"]["spec"]["Flagga"] == "handlingarna anger olika fabrikat"
    assert not any(i["manufacturer"] == "Smedbo" and "Badrum" in i["category"] for i in r["items"])


def _plain():
    d = pymupdf.open()
    d.new_page().insert_text((50, 50), "PLAN 09, DEL 1", fontname="helv", fontsize=9)
    return d.tobytes()


def test_a_product_page_is_read_from_its_structured_data_and_spec_table():
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    from app.brand_catalog import product_from_page, rows_to_products
    html = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
      "name":"Ariella Aqua 60 spegelskåp","sku":"AA60","offers":{"@type":"Offer","price":"1850.00"},
      "additionalProperty":[{"name":"Bredd","value":"60 cm"},{"name":"RSK-nummer","value":"891 20 81"}]}</script></head>
      <body><h1>Ariella Aqua 60</h1><table><tr><th>Höjd</th><td>700 mm</td></tr><tr><th>Miljömärkning</th>
      <td>Byggvarubedömningen accepterad</td></tr></table></body></html>"""
    p = product_from_page("https://alternabadrum.se/produkt/ariella-aqua-60", html)
    assert p["name"] == "Ariella Aqua 60 spegelskåp" and p["rsk"] == "8912081" and p["price"] == 1850.0
    assert p["bredd"] == 600 and p["höjd"] == 700 and "Byggvarubedömningen" in p["labels_text"][0]
    s = suggest({"name": "Spegelskåp 60", "text": "Byggvarubedömningen accepterad", "spec": {}, "manufacturer": "",
                 "type": ""}, [p])
    assert s["candidates"][0]["state"] == "uppfyller angivna krav"
    rows = [["Sortiment Alterna"], ["RSK", "Benämning", "Bredd", "Pris"], ["8912079", "Isella Aqua underskåp 60", 600, "3 200"]]
    prods = rows_to_products(rows)
    assert prods == [{"name": "Isella Aqua underskåp 60", "rsk": "8912079", "series": "", "category": "", "material": "",
                      "url": "", "price": 3200.0, "bredd": 600}]
