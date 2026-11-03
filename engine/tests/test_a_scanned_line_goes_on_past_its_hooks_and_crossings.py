"""En inskannad linje går vidare förbi spårarens krokar.

Spåraren gör något med en linje på ett inskannat blad som ingen ritare gjort: linjens sista pixel eller två böjer
av mot ett hörn av bläcket, så varje ände slutar i en krok - ett streck på en halv punkt i fyrtio graders vinkel.
Sett från änden pekade varje linje då åt fel håll, och inget glapp i den överbryggades: inte där en hänvisningslinje
korsade och bläcket blev tjockare, inte mellan streck och prick. Rören på en inskannad plan blev en tredjedels
meter långa och planen mätte 73 m. Riktningen är strecket kroken hänger i.

Exporterade vektorer har inga krokar; där är änden det ritaren drog, och den läses som förut.
"""
from vvs_engine.geometry.core import Seg
from vvs_engine.pipes.representation import RASTER_TOL, VECTOR_TOL, Prim, build_graph

FAM = "|s|w2.16|c(0.0, 0.0, 0.0)"


def _path(pid, pts, start_id):
    return [Prim(prim_id=start_id + i, pid=pid, seg_index=i, seg=Seg(a[0], a[1], b[0], b[1]), family=FAM, layer="",
                 width=2.16) for i, (a, b) in enumerate(zip(pts, pts[1:]))]


def _line_broken_at_a_crossing(gap=2.1):
    # one vertical line, x = 100, broken by the tracer where a leader crossed it; each piece ends in a hook
    upper = _path("p1", [(100.0, 100.0), (100.0, 194.5), (99.8, 194.9)], 0)
    lower = _path("p2", [(100.2, 194.9 + gap), (100.0, 195.3 + gap), (100.0, 300.0)], 10)
    return upper + lower


def _joined(g):
    return any(len(n.prims) == 2 and {g.prims[p].pid for p in n.prims} == {"p1", "p2"} for n in g.nodes.values())


def test_a_scanned_line_is_one_line_across_the_tracers_break():
    assert _joined(build_graph(_line_broken_at_a_crossing(), FAM, RASTER_TOL))


def test_the_hook_is_not_read_as_the_lines_direction_on_an_exported_sheet():
    assert not _joined(build_graph(_line_broken_at_a_crossing(), FAM, VECTOR_TOL))


def test_a_real_gap_in_a_scanned_line_stays_a_gap():
    # two lines end to end with a hand's breadth between them: no hook makes that one line
    assert not _joined(build_graph(_line_broken_at_a_crossing(gap=15.0), FAM, RASTER_TOL))
