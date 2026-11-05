"""En teknisk beskrivning utan ritningar läses till sitt material.

Beskrivningen är en tabell enligt AMA: KOD, TEXT, MÄNGD, ENHET. AMA-koden står till vänster med rubriken bredvid,
posten i fetstil med mängden till höger, och under posten fabrikat, typ, RSK-nummer, specifikation och det som hör
till den. Utanför posterna står kravtexten, och där nämns också material: upphängningsdon, märkband, en produkt med
fabrikat, något som levereras av beställaren, tid för utbildning.

Bladet här är syntetiskt men uppställt som en riktig beskrivning (12.4 Teknisk beskrivning VS, 37 sidor), med de
fall som den läsningen missade första gången: en mängd på specifikationsraden, ett intervall "1-2 st", en fet
isoleringsrad utan mängd, ett Armatec-nummer utan fabrikatnamn och en del i texten med egen modell.
"""
from __future__ import annotations

import pymupdf
import pytest

from vvs_engine.tb import read_tech_spec_bytes
from vvs_engine.tb.mail import draft
from vvs_engine.tb.match import MaterialIndex
from vvs_engine.tb.reader import find_maker, supplied_by
from vvs_engine.tb.catalog import find_pdf_link, index_pdf, unwrap_url

REG, BOLD = "helv", "hebo"


def _page(doc, rows, n, total):
    pg = doc.new_page(width=595, height=842)
    # sidhuvudet, samma på varje sida
    pg.insert_text((201, 45), "12.4 TEKNISK BESKRIVNING", fontname=BOLD, fontsize=10)
    pg.insert_text((400, 95), f"2025-09-15 {n} ({total})", fontname=REG, fontsize=10)
    pg.insert_text((60, 130), "KOD", fontname=REG, fontsize=5)
    pg.insert_text((130, 130), "TEXT", fontname=REG, fontsize=5)
    pg.insert_text((457, 130), "MÄNGD", fontname=REG, fontsize=5)
    pg.insert_text((499, 130), "ENHET", fontname=REG, fontsize=5)
    y = 160
    for r in rows:
        kind = r[0]
        if kind == "ama":
            pg.insert_text((62, y), r[1], fontname=REG, fontsize=13)
            pg.insert_text((128, y), r[2], fontname=REG, fontsize=13)
            y += 26
        elif kind == "post":
            pg.insert_text((128, y), r[1], fontname=BOLD, fontsize=10)
            if r[2]:
                pg.insert_text((488, y), r[2], fontname=REG, fontsize=10)
            y += 18
        elif kind == "bold":
            pg.insert_text((128, y), r[1], fontname=BOLD, fontsize=10)
            y += 16
        elif kind == "text":
            pg.insert_text((128, y), r[1], fontname=REG, fontsize=10)
            y += 12
        elif kind == "kv":
            pg.insert_text((128, y), r[1], fontname=REG, fontsize=10)
            pg.insert_text((241, y), r[2], fontname=REG, fontsize=10)
            if len(r) > 3:
                pg.insert_text((488, y), r[3], fontname=REG, fontsize=10)
            y += 12
        elif kind == "head":
            pg.insert_text((128, y), r[1], fontname=REG, fontsize=9)
            y += 12
        elif kind == "bullet":
            pg.insert_text((128, y), "•", fontname=REG, fontsize=10)
            pg.insert_text((145, y), r[1], fontname=REG, fontsize=10)
            y += 14
        elif kind == "value_qty":
            pg.insert_text((128, y), r[1], fontname=REG, fontsize=10)
            pg.insert_text((480, y), r[2], fontname=REG, fontsize=10)
            y += 12
        y += 2


PAGES = [
    [("ama", "PN", "RÖRLEDNINGAR M.M."),
     ("bold", "MATERIAL- OCH VARUKRAV"),
     ("text", "Rörledning ska monteras med erforderliga och anpassade fästdon."),
     ("text", "I entreprenaden ska erforderliga upphängningsdon, pendlar och glidbyglar ingå."),
     ("text", "Kompressor levereras av Beställare typ Kaeser Premium 660/90D."),
     ("text", "Oljeavskiljare levereras av markentreprenör."),
     ("ama", "PNU.31", "Ledningar av raka kopparrör"),
     ("post", "KV01-K1  Tappkallvatten", "Enl ritn"),
     ("post", "VV01-K1  Tappvarmvatten", "Enl ritn"),
     ("text", "Raka koppar rör av fabrikat Geberits Mapress eller likvärdig."),
     ("ama", "PMB.211", "Silfilter"),
     ("post", "SIL101", ""),
     ("text", "För tappvatten."),
     ("text", "Smutsfilter AT 4003A, G25, hus av rödgods, PN 10."),
     ("head", "Ansl. nr."),
     ("value_qty", "25", "1 st")],
    [("ama", "PRB.1", "Golvbrunnar"),
     ("ama", "PRB.12", "Golvbrunnar av rostfritt stål"),
     ("post", "B202B", "1 st"),
     ("text", "Golvbrunn av fabrikat Furhoffs typ FURO typ 142. Storlek 273x273x250."),
     ("text", "Bottenutlopp. Utloppsdimension 110mm. Levereras med vattenlås."),
     ("head", "Specifikation"),
     ("kv", "Storlek", "273 x 273 x 250mm"),
     ("kv", "Golvmaterial", "Halkskyddad epoxibeläggning"),
     ("ama", "PRB.15", "Golvbrunnar av plast"),
     ("post", "B101P", "2 st"),
     ("text", "Golvbrunn av fabrikat Purus typ Brage. Golvtyp plastmatta."),
     ("ama", "PUC.1", "Tvättställ"),
     ("post", "TS101", "2 st"),
     ("text", "IFÖs typ Cera 23220, RSK 7606418"),
     ("text", "Härtill:"),
     ("bullet", "1st ettgreppsblandare FMM 9000E EcoSafe typ 8060-0000, med"),
     ("bullet", "2 st. avstängningsventiler Broens typ Ballofix, förkromad."),
     ("ama", "PAK.514", "Kylkompressoraggregat"),
     ("post", "Mitsubishi Electric RAC", "2st"),
     ("bold", "Utomhusdel typ MUZ-FT25VGHZ(-SC)"),
     ("text", "MARKSTATIV DP-900 – Rostfritt markstativ med dropptråg")],
    [("ama", "RBA.14", "Sammansatt termisk isolering med rörskålar"),
     ("bold", "KV01 isoleras med diff.tät rörskål 30mm. Synliga rör ytbekläds."),
     ("ama", "UGE", "MÄTARE FÖR FLÖDE"),
     ("post", "VM101", ""),
     ("text", "För tappkallvatten."),
     ("text", "Vattenmätare levereras av kommunen."),
     ("head", "Storlek"),
     ("value_qty", "DN XX", "1-2 st"),
     ("text", "Flödesmätarutrustning bestående av:"),
     ("bullet", "VSE leverar vattenmätarkonsol."),
     ("ama", "YGB.5", "Märkning av vvs-installationer"),
     ("text", "Märkband ska vara av självhäftande plast med beständig text."),
     ("text", "Huvudkomponent, till exempel pump eller kompressor, ska märkas med märkskylt."),
     ("ama", "YKB.5", "Utbildning och information"),
     ("text", "Tid för utbildning och information: 2 tim.")],
]


@pytest.fixture(scope="module")
def spec():
    doc = pymupdf.open()
    for i, rows in enumerate(PAGES):
        _page(doc, rows, i + 1, len(PAGES))
    data = doc.tobytes()
    doc.close()
    return read_tech_spec_bytes(data)


def _by(spec, **kw):
    return [it for it in spec["items"] if all(it.get(k) == v for k, v in kw.items())]


def test_a_post_carries_code_quantity_maker_type_and_specification(spec):
    b = _by(spec, code="B202B", kind="post")[0]
    assert b["name"] == "Golvbrunn" and b["quantity"] == 1 and b["unit"] == "st"
    assert b["manufacturer"] == "Furhoff" and b["manufacturer_text"] == "Furhoffs" and b["type"] == "FURO 142"
    assert b["spec"] == {"Storlek": "273 x 273 x 250mm", "Golvmaterial": "Halkskyddad epoxibeläggning"}
    assert b["page"] == 2


def test_floor_drains_of_steel_and_of_plastic_are_one_category(spec):
    """Kategorin är AMA-rubriken på fjärde nivån: PRB.1 Golvbrunnar, oavsett material."""
    b202, b101 = _by(spec, code="B202B")[0], _by(spec, code="B101P")[0]
    assert b202["category"] == b101["category"] == "Golvbrunnar"
    assert b202["subcategory"] == "Golvbrunnar av rostfritt stål" and b101["subcategory"] == "Golvbrunnar av plast"
    assert b101["manufacturer"] == "Purus" and b101["type"] == "Brage" and b101["quantity"] == 2


def test_the_header_repeated_on_every_page_is_not_material(spec):
    assert not any("TEKNISK BESKRIVNING" in it["text"] for it in spec["items"])


def test_accessories_are_their_own_items_multiplied_by_their_post(spec):
    acc = _by(spec, kind="tillbehor", code="TS101")
    names = {a["name"]: a for a in acc}
    assert names["Ettgreppsblandare"]["manufacturer"] == "FMM" and "8060-0000" in names["Ettgreppsblandare"]["type"]
    v = names["Avstängningsventiler"]
    assert v["manufacturer"] == "Broen" and v["type"] == "Ballofix"
    assert v["quantity"] == 2 and v["total_quantity"] == 4          # 2 per tvättställ, två tvättställ
    assert _by(spec, code="TS101", kind="post")[0]["rsk"] == ["7606418"]


def test_rows_without_text_share_the_text_that_follows(spec):
    """KV01-K1 och VV01-K1 står var för sig, och texten under gäller båda."""
    for code in ("KV01-K1", "VV01-K1"):
        it = _by(spec, code=code)[0]
        assert it["manufacturer"] == "Geberit" and it["type"] == "Mapress" and it["or_equal"]
        assert it["quantity_text"] == "Enl ritn" and it["quantity"] is None


def test_a_quantity_written_on_the_specification_row_belongs_to_the_post(spec):
    sil = _by(spec, code="SIL101")[0]
    assert sil["quantity"] == 1
    assert sil["name"] == "Smutsfilter"
    assert sil["manufacturer"] == "Armatec" and sil["type"] == "AT 4003A" and "AT 4003A" in sil["inferred"]


def test_a_range_counts_its_upper_bound_and_keeps_what_was_written(spec):
    vm = _by(spec, code="VM101", kind="post")[0]
    assert vm["quantity"] == 2 and vm["quantity_text"] == "1-2 st"
    assert vm["name"] == "Vattenmätare" and vm["supplied_by"] == "Kommunen"
    konsol = _by(spec, code="VM101", kind="tillbehor")[0]
    assert konsol["name"] == "Vattenmätarkonsol" and konsol["supplied_by"] == ""   # VS-entreprenören levererar


def test_a_bold_insulation_line_is_the_insulation_post(spec):
    kv = _by(spec, code="KV01")[0]
    assert kv["kind"] == "post" and kv["name"] == "Diff.tät rörskål 30mm"


def test_a_part_with_its_own_model_in_the_text_is_an_accessory(spec):
    ute = _by(spec, kind="post", manufacturer="Mitsubishi Electric")[0]
    assert ute["quantity"] == 2 and "MUZ-FT25VGHZ(-SC)" in ute["type"]
    stativ = [a for a in _by(spec, kind="tillbehor") if a["parent"] == ute["id"]]
    assert stativ and stativ[0]["name"] == "Markstativ" and stativ[0]["type"] == "DP-900"


def test_requirement_text_names_generic_material_and_who_delivers(spec):
    krav = {it["name"]: it for it in _by(spec, kind="krav")}
    assert {"Fästdon", "Upphängningsdon", "Pendlar", "Glidbyglar", "Märkband", "Märkskylt"} <= set(krav)
    assert krav["Oljeavskiljare"]["supplied_by"] == "Markentreprenör"
    # ett exempel i en mening om märkning är inte en vara
    assert "Pump" not in krav and not any(k.startswith("Kompressor") for k in krav)


def test_a_product_named_in_the_requirement_text_is_mentioned_with_its_maker(spec):
    k = _by(spec, kind="omnamnd", manufacturer="Kaeser")[0]
    assert k["type"] == "Premium 660/90D" and k["supplied_by"] == "Beställare"


def test_time_the_description_sets_is_work(spec):
    w = _by(spec, kind="arbete")[0]
    assert w["quantity"] == 2 and w["unit"] == "tim"


@pytest.mark.parametrize("text,maker", [
    ("Golvbrunn av fabrikat Furhoffs typ FURO 152. Golvtyp stålslipat", ("Furhoff", "FURO 152")),
    ("Fabrikat Armatec AT3700 eller AT3701 där det är isolerat.", ("Armatec", "AT3700 eller AT3701")),
    ("IFÖs typ Spira 6261-0931-1010, RSK 7811054, i vit färg.", ("IFÖ", "Spira 6261-0931-1010")),
    ("Fabrikat Beulco typ BA 107 eller likvärdig.", ("Beulco", "BA 107")),
    ("Återströmningsskyddet är av typ EA.", ("", "")),
    ("Skyddsmodul med skyddsdon typ BA med dubbla backventiler.", ("", "")),
])
def test_the_maker_is_read_in_the_three_ways_a_description_writes_it(text, maker):
    brand, _, typ = find_maker(text)
    assert (brand, typ) == maker


def test_who_delivers():
    assert supplied_by("Oljeavskiljare levereras utav markentreprenör.") == "Markentreprenör"
    assert supplied_by("Beställaren tillhandahåller kompressor och högtryckstvätt.") == "Beställare"
    assert supplied_by("Utföres av EE.") == "Elentreprenör"
    assert supplied_by("Vattenmätarkonsol levereras utav VSE.") == ""


# ---------------------------------------------------------------- mot materialboken och katalogen

BOOK = [
    {"a": "7606418", "n": "Ifö 2322 tvst Cera, vitt", "e": "st", "p": 1131.57},
    {"a": "7115125", "n": "Furo 142 273x273 110B btg", "e": "st", "p": 4200.0},
    {"a": "7115126", "n": "Furo 142 273x273 75B massa", "e": "st", "p": 4100.0},
    {"a": "4501063", "n": "25 Beulco BA 107 kulventil", "e": "st", "p": 310.0},
    {"a": "1199999", "n": "Disponibel artikel", "e": "st", "p": None},
    {"a": "2201234", "n": "Nibe Eminent-CU 55 vvb", "e": "st", "p": 9800.0},
    {"a": "9999999", "n": "Indisponibel nibelung 55", "e": "st", "p": 1.0},
]


@pytest.fixture(scope="module")
def index():
    ix = MaterialIndex()
    ix.add_material_book(BOOK)
    ix.add_catalog({"pages": [{"page": 214, "lines": ["Purus Brage golvbrunn 200x200 75 PP", "RSK 7811054 Ifö Spira wc"]}]})
    return ix


def test_an_rsk_number_finds_the_same_article(index, spec):
    m = index.match(_by(spec, code="TS101", kind="post")[0])
    assert m["status"] == "hittad" and m["hits"][0]["ref"] == "7606418" and "RSK" in m["hits"][0]["why"]


def test_maker_and_model_suggest_articles_ranked_by_the_specification(index, spec):
    m = index.match(_by(spec, code="B202B")[0])
    assert m["status"] == "möjlig"
    assert m["hits"][0]["ref"] == "7115125"          # 273x273 och 110 ur specifikationen


def test_the_catalog_page_is_where_a_product_stands(index, spec):
    m = index.match(_by(spec, code="B101P")[0])
    assert m["status"] == "möjlig" and m["in_catalog"] and m["hits"][0]["page"] == 214


def test_a_word_matches_a_word_not_a_piece_of_one(index):
    """'nibe' är inte 'indisponibel' och inte 'nibelung'."""
    m = index.match({"manufacturer": "Nibe", "type": "Eminent 55", "text": "", "spec": {}})
    assert [h["ref"] for h in m["hits"]] == ["2201234"]


def test_what_is_nowhere_is_missing_and_gets_a_draft(index, spec):
    furo152 = {**_by(spec, code="B202B")[0], "type": "FURO 152", "code": "B201B", "rsk": []}
    m = index.match(furo152)
    assert m["status"] == "saknas" and not m["hits"]
    d = draft([furo152], project="Tvätthall Årjäng", document="12.4 Teknisk beskrivning", to="inkop@example.com")
    assert d["subject"].startswith("Förfrågan: Golvbrunn")
    assert "B201B – Golvbrunn, 1 st" in d["body"] and "Fabrikat: Furhoff typ FURO 152" in d["body"]
    assert "Storlek 273 x 273 x 250mm" in d["body"] and "sida 2" in d["body"]
    assert d["mailto"].startswith("mailto:inkop%40example.com?subject=")


def test_a_catalog_link_from_a_mail_is_unwrapped_and_its_pdf_found():
    wrapped = ("https://www.google.com/url?q=https://katalog.dahl.se/dahl-sverige-ab/dahl-produktkatalog-2026pdf/"
               "?_gl%3D1*1w&source=gmail&ust=1&usg=x")
    assert unwrap_url(wrapped).startswith("https://katalog.dahl.se/dahl-sverige-ab/dahl-produktkatalog-2026pdf/")
    html = '<a class="dl" href="/files/dahl-produktkatalog-2026.pdf?v=3">Ladda ner</a>'
    assert find_pdf_link(html, "https://katalog.dahl.se/x/") == "https://katalog.dahl.se/files/dahl-produktkatalog-2026.pdf?v=3"
    assert find_pdf_link("<html>ingen länk</html>", "https://katalog.dahl.se/") is None


def test_a_catalog_pdf_is_indexed_line_by_line_with_its_pages():
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((50, 80), "Furo 142 golvbrunn 273x273", fontname=REG, fontsize=10)
    pg.insert_text((50, 95), "7115125", fontname=REG, fontsize=10)
    idx = index_pdf(doc.tobytes(), origin="test")
    assert idx["pages"][0]["page"] == 1
    assert idx["pages"][0]["lines"] == ["Furo 142 golvbrunn 273x273 7115125"]   # numret hör till raden före
