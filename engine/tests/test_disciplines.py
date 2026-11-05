"""The discipline register: VVS is today's reading with nothing overridden, the others are data until they are built."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest  # noqa: E402

from vvs_engine import disciplines as D  # noqa: E402
from vvs_engine.disciplines import measures as M  # noqa: E402


def test_every_discipline_is_described_and_vvs_and_alla_are_built():
    reg = D.registry()
    assert list(reg)[:4] == ["vvs", "sprinkler", "kyla", "ventilation"] and {"el", "bygg", "alla"} <= set(reg)
    for d in reg.values():
        assert d.status in D.STATUSES and d.kind in D.KINDS and set(d.measures) <= set(M.UNITS)
    # alla discipliner går att välja; de som läser mer än VVS-rören läser bladet vidgat och skriver registret
    assert [d.id for d in reg.values() if d.status == D.ACTIVE] == ["vvs", "sprinkler", "kyla", "ventilation", "el", "bygg", "alla"]
    assert D.selectable("vvs") and D.selectable("") and D.selectable("alla") and D.selectable("ventilation")
    assert not D.selectable("x")
    assert not reg["vvs"].reads_all and all(reg[k].reads_all for k in ("sprinkler", "kyla", "ventilation", "el", "bygg", "alla"))
    assert {k: reg[k].engine.get("register.FOCUS") for k in ("ventilation", "el", "bygg")} == \
        {"ventilation": "ledning", "el": "komponent", "bygg": "rum"}


def test_alla_reads_the_pipes_as_vvs_does():
    """"Alla" lists every designation beside the takeoff; the pipes under it are VVS's reading, unchanged."""
    assert D.get("alla").engine == {} and D.get("alla").kind == "all"
    assert set(D.get("alla").measures) == {"LENGTH", "COUNT", "AREA"}


def test_vvs_overrides_nothing_so_the_reading_sees_its_own_constants():
    assert D.get("vvs").engine == {}
    assert D.current().id == "vvs"
    sentinel = object()
    assert D.value("direction.GRAVITY_SYSTEMS", sentinel) is sentinel


def test_a_discipline_is_bound_to_one_reading_and_an_unknown_one_is_refused():
    with D.using("kyla"):
        assert D.current().id == "kyla"
    assert D.current().id == "vvs"
    with D.using(""):
        assert D.current().id == "vvs"          # a project from before disciplines is VVS
    with pytest.raises(KeyError):
        with D.using("rymdfart"):
            pass


def test_a_vvs_row_and_a_markup_seen_as_common_rows_without_changing_them():
    row = {"designation": "KV1-X7-40", "dn": 40, "confirmed_horizontal_m": 12.5, "vertical_m": "UNKNOWN",
           "ambiguous_m": 0.75, "state": "CONFIRMED", "pipe_ids": ["p1"]}
    before = dict(row)
    v = M.vvs_row_view(row)
    assert row == before
    assert v["source_type"] == M.UPPMATT and v["system"] == "KV1" and v["dimension"] == {"format": "DN", "value": 40}
    assert [(m["type"], m["unit"], m["value"], m["state"]) for m in v["measures"]] == [
        ("LENGTH", "m", 12.5, "CONFIRMED"), ("LENGTH", "m", 0.75, "AMBIGUOUS")]
    mk = M.markup_row_view({"id": "m1", "designation": None, "measure": {"kvm": 4.2}, "status": "oppen", "page": 0})
    assert mk["source_type"] == M.MANUELL and [(m["type"], m["unit"], m["value"]) for m in mk["measures"]] == [("AREA", "m²", 4.2)]
    with pytest.raises(ValueError):
        M.measure("TID", 1)
