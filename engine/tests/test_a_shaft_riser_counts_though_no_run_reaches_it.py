"""Stigare i ett schakt räknas, fast inget liggande rör når dem - och bladets täckning räknas på rätt namn.

V50-01-2711 ritar schaktet som en rad ringar, en per stigare som passerar bjälklaget, och etiketterna bredvid pekar
på dem: KB01-6-80, VB01-2-125, VS01-2-65. Inget rör ritas in i ringarna, eftersom rören går lodrätt genom planen.
Kopplingen letade efter rörgeometri vid ledarens slut, hittade ingen, och schaktets stigare fanns inte i mängden.
De tunna stigarna ritas som små dubbelringar (rör och isolering); en ensam liten ring är en ändpunkt.

Täckningen - hur många av bladets rörnamn som fick mängd - räknade förklaringslistans rader (DS4, S3, VVCXX-3) som
rör läsningen missat, och ett par skrivet åt andra hållet (KV02-3-/VV02-3-15 mot VV02-3-/KV02-3-15) som ett annat
namn. På bladet steg andelen från 47 % till 84 % när det räknades på det bladet faktiskt namnger.
"""
from __future__ import annotations

from types import SimpleNamespace

import pymupdf

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import _pair_key, _shaft_risers


def test_a_pair_is_one_pair_whichever_way_it_is_written():
    assert _pair_key("KV02-3-/VV02-3-15") == _pair_key("VV02-3-/KV02-3-15") == (("KV02-3", "VV02-3"), "15")
    assert _pair_key("KVO1-3-/VV01-3-28") == _pair_key("VV01-3-/KV01-3-28")          # O read for 0
    assert _pair_key("KV02-3-/VV02-3-15") != _pair_key("KV02-3-/VV02-3-22")          # the size keeps them apart
    assert _pair_key("KV01-3/VV01-3") == (("KV01-3", "VV01-3"), "")                   # an identity key: no size
    assert _pair_key("KB02-3-35") is None


def _shaft_pdf(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=300, height=200)
    # varje ring sin egen bana, som en ritning skriver dem
    for c, r in (((100, 100), 1.4), ((100, 100), 0.9),        # en tunn stigare: dubbelring
                 ((140, 100), 1.4),                           # en ensam liten ring: en ändpunkt
                 ((180, 100), 4.0)):                          # en grov stigare
        sh = pg.new_shape()
        sh.draw_circle(c, r)
        sh.finish(color=(0, 0, 0), width=0.3)
        sh.commit()
    path = tmp_path / "schakt.pdf"
    doc.save(path)
    return extract_document(str(path)).pages[0]


def _anchor(aid, text, dn, end, state="NO_PIPE_ATTACHMENT"):
    return SimpleNamespace(anchor_id=aid, designation_id="d" + aid, designation=text, designation_display=text,
                           system_token=text.split("-")[0], dn=dn, multiplier=1, endpoint=end, state=state)


def _des(aid, text):
    return SimpleNamespace(did="d" + aid, text=text, system_token=text.split("-")[0])


class _Legend:
    def names_a_pipe(self, d):
        return not d.text.startswith("AV")        # en ventil är ingen stigare


def test_a_label_at_a_double_ring_or_a_large_ring_is_a_riser(tmp_path):
    page = _shaft_pdf(tmp_path)
    anchors = [_anchor("1", "KB01-6-80", 80, (100.8, 100.3)), _anchor("2", "VS01-2-65", 65, (140.5, 100.0)),
               _anchor("3", "VB01-2-125", 125, (181.0, 101.0)), _anchor("4", "AV201-40", 40, (180.0, 99.0)),
               _anchor("5", "KB02-3-35", 35, (100.0, 100.0), state="VERIFIED_PIPE_ATTACHMENT")]
    des = [_des(a.anchor_id, a.designation) for a in anchors]
    out = _shaft_risers(page, set(), set(), anchors, des, _Legend(), {})
    found = {r["designation"].split("-")[0]: r for lst in out.values() for r in lst}
    assert set(found) == {"KB01", "VB01"}                 # inte den ensamma lilla ringen, inte ventilen
    assert found["KB01"]["point"] == [100.0, 100.0] and found["KB01"]["source"] == "label_at_shaft_ring"


def test_a_ring_another_riser_already_has_is_not_counted_twice(tmp_path):
    page = _shaft_pdf(tmp_path)
    taken = {"X": [{"point": [180.0, 100.0]}]}
    out = _shaft_risers(page, set(), set(), [_anchor("3", "VB01-2-125", 125, (181.0, 101.0))],
                        [_des("3", "VB01-2-125")], _Legend(), taken)
    assert out == {}
