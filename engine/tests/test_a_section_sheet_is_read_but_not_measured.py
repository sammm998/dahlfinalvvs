"""En sektion visar planernas rör från sidan. Mätt som en plan räknades samma rör två gånger, och sektionens
lodräta linjer - stegar, väggar, schakt - lästes som rör. Bladets namnruta säger vad bladet är: står det
SEKTION eller SEKTIONER där läses bladet som ett schema. Beteckningarna och komponenterna räknas, inga meter tas,
och omdömet är SECTION.

En plan som har ett sektionsutsnitt ritat på sig bär samma ord i utsnittets rubrik, ute på ritytan. Den är fortfarande
en plan och mäts som förut.
"""
import pymupdf

from vvs_engine.coverage import completion_checks, coverage_validity
from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page, reading_coverage


def _line(shape, p0, p1, w=0.7):
    shape.draw_line(p0, p1)
    shape.finish(width=w, color=(0, 0, 0), closePath=False)


def _label(page, shape, text, at, to):
    x, y = at
    page.insert_text((x, y), text, fontsize=10, fontname="helv")
    w = 6.2 * len(text)
    _line(shape, (x, y + 2), (x + w, y + 2))
    _line(shape, (x + w, y + 2), to)
    _line(shape, (to[0] - 2.5, to[1] + 2.5), (to[0] + 2.5, to[1] - 2.5))


def _sheet(path, title_block, caption=None):
    """Two named pipes, a valve's tag on one of them, the scale in the title block, and the drawing's name there."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    shape = page.new_shape()
    page.insert_text((640, 540), title_block, fontsize=10, fontname="helv")
    page.insert_text((640, 560), "SKALA 1:50", fontsize=10, fontname="helv")
    if caption:
        page.insert_text((140, 420), caption, fontsize=12, fontname="helv")
    for y, text in ((200, "KV1-X7-40"), (320, "VV1-X7-25")):
        _line(shape, (120, y), (560, y), 1.44)
        _label(page, shape, text, (200, y - 40), (260, y))
    shape.draw_rect(pymupdf.Rect(400, 194, 412, 206))
    shape.finish(width=0.7, color=(0, 0, 0))
    _label(page, shape, "AV201-40", (430, 150), (406, 194))
    shape.commit()
    doc.save(path)
    doc.close()
    return str(path)


def _read(path):
    pa = analyze_page(extract_document(path).pages[0])
    cov = reading_coverage(pa)
    verdict = completion_checks(coverage_validity(cov, pa.anchors, None, pa.scale.state if pa.scale else None,
                                                  len(pa.measures)), pa.quantities)
    return pa, cov, verdict


def _metres(pa):
    return sum(float(r.get("confirmed_horizontal_m") or 0) for r in pa.quantities)


def test_a_section_is_read_as_a_schema_and_takes_no_metres(tmp_path):
    pa, cov, v = _read(_sheet(tmp_path / "sektion.pdf", "SEKTION A-A, B-B"))
    assert pa.scale.reason == "section_not_measured" and pa.scale.meters_per_pt is None
    assert v["verdict"] == "SECTION", v
    assert "SECTION_NOT_MEASURED" in v["reasons"]
    assert not {"NO_SCALE", "SHEET_NAMES_PIPES_BUT_NOTHING_WAS_MEASURED"} & set(v["reasons"]), v["reasons"]
    assert _metres(pa) == 0
    assert cov["section"] is True and cov["schematic"] is True and cov["missed"] == []
    assert {n["name"] for n in cov["names_on_schematic"]} == {"KV1-X7-40", "VV1-X7-25"}
    assert [(c["name"], c["count"]) for c in cov["components"]] == [("AV201-40", 1)]


def test_a_plan_with_a_section_cut_out_on_it_is_measured_as_before(tmp_path):
    pa, cov, v = _read(_sheet(tmp_path / "plan.pdf", "PLANRITNING, SEKTION, VS-INSTALLATIONER", caption="SEKTION A-A"))
    assert pa.scale.reason != "section_not_measured" and pa.scale.meters_per_pt
    assert v["verdict"] != "SECTION" and not cov.get("section")
    assert _metres(pa) > 0
