"""En etikett som räknar upp ett stigarschakts tre tappvattenrör namnger alla tre.

På V50-01-2711 står vid schaktet `KV01-53-,VV01-53-32,VVC01-53-20`: kallvatten, varmvatten och VVC i samma
etikett. Tre rör med var sin avstängningsventil går därifrån, och inget av dem fick en meter. Tre saker
samverkade:

1. Läsaren läste kommatecknen som `/` - den sammansatta etikett resten av läsningen förstår - men ordet blev 31
   tecken, och en kod fick vara högst 24. Hela etiketten togs för prosa.
2. Där kommatecknet inte lästes som `/` blev det `?`. Ett ritat komma är ett kort streck vid radens fot, en
   femtedel av radhöjden, och det poängsattes strax utanför vad läsaren kallar ett tecken.
3. `SS4-75` (spillvatten, PP-rör) läses `S54-75`: S och 5 är samma form. Bladets lista skriver SS4, ingen etikett
   öppnade med SS4, och fjorton spillvattenetiketter togs för något annat än rör.
"""
from vvs_engine.semantics.annotation import _read_commas
from vvs_engine.semantics.grammar import is_code_like
from vvs_engine.semantics.legend import code_matches, number_as_listed, opens_as_twin, opens_with
from vvs_engine.text.model import Glyph

ROW_H = 3.24


def test_a_trio_label_is_a_code_though_longer_than_one():
    assert is_code_like("KVO1-53-/VVO1-53-32/VVCO1-53-16")
    assert is_code_like("KV01-53-/VV01-53-32/VVC01-53-20")


def test_the_limit_still_holds_for_each_code_and_for_a_single_word():
    assert not is_code_like("ABCDEFGHIJKLMNOPQRSTUVWXY1")                 # 26 characters, no slash
    assert not is_code_like("KV01-53-/ABCDEFGHIJKLMNOPQRSTUVWXY1")        # one part past the limit
    assert not is_code_like("A1/B2/C3/D4/E5")                            # five parts is a list, not a label


def _g(ch, x, w=1.6, h=ROW_H, alts=()):
    return Glyph(gid=f"g{x}", char=ch, bbox=(x, 100.0, x + w, 100.0 + h), source="stroke", alternatives=list(alts))


def _word(text):
    """Glyfer för en text där `?` är ett kommastort streck med komma och snedstreck bland läsarens gissningar."""
    out = []
    for i, ch in enumerate(text):
        if ch == "?":
            out.append(_g("?", i * 2.0, w=0.12, h=0.72, alts=[("/", 0.158), (",", 0.162), ("I", 0.17)]))
        else:
            out.append(_g(ch, i * 2.0))
    return out


def _text(glyphs):
    return "".join(g.char for g in glyphs)


def test_a_comma_between_two_codes_reads_as_the_slash_of_a_compound():
    w = _word("VVCO1-53-16?VVO1-53-20?KVO1-53-20")
    assert _read_commas(w, ROW_H) == 2
    assert _text(w) == "VVCO1-53-16/VVO1-53-20/KVO1-53-20"
    assert is_code_like(_text(w))


def test_a_comma_after_a_dash_opens_the_next_code():
    w = _word("KVO1-53-?VVO1-53-32")
    _read_commas(w, ROW_H)
    assert _text(w) == "KVO1-53-/VVO1-53-32"


def test_a_comma_that_ends_the_word_is_a_comma():
    w = _word("AV21-32?")
    _read_commas(w, ROW_H)
    assert _text(w) == "AV21-32,"


def test_a_tick_between_two_digits_is_not_this_rules_call():
    """Det kan vara en decimal."""
    w = _word("32?5")
    assert _read_commas(w, ROW_H) == 0
    assert _text(w) == "32?5"


def test_an_unknown_glyph_of_full_height_is_left_unknown():
    """Ett okänt tecken i full höjd är en siffra eller bokstav läsaren inte kände igen, inte ett komma."""
    w = [_g(c, i * 2.0) for i, c in enumerate("S5")] + [_g("?", 4.0, alts=[("4", 0.14), ("/", 0.2)])] \
        + [_g(c, 6.0 + i * 2.0) for i, c in enumerate("-75")]
    assert _read_commas(w, ROW_H) == 0
    assert _text(w) == "S5?-75"


def test_a_tick_the_reader_did_not_take_for_a_comma_is_left_alone():
    w = _word("KV01-3-?VV01-3-15")
    w[7].alternatives = [("I", 0.15), (")", 0.16), ("1", 0.17)]
    assert _read_commas(w, ROW_H) == 0


def test_a_list_code_read_through_its_twins_opens_the_label():
    assert opens_as_twin("S54-75", "SS4")
    assert opens_with("S54-75", "SS4")
    assert opens_with("S54-110", "SS4")


def test_a_twin_does_not_stretch_a_short_code_over_a_longer_word():
    assert not opens_as_twin("S35-110", "S3")            # 53 is the start of 535, but S3 ends before the 5
    assert not opens_as_twin("S", "SS4")
    assert not opens_as_twin("S54-75", "S")              # a one-letter code is compared letter for letter only
    assert not opens_as_twin("KV02-3-15", "KVXX-3")      # placeholder codes have their own comparison
    assert not code_matches("S54-75", "SS4")             # the component comparison is unchanged


def test_the_label_is_written_the_way_the_list_writes_it():
    assert number_as_listed("S54-75", ["SS4"]) == "SS4-75"
    assert number_as_listed("SS4-75", ["SS4"]) == "SS4-75"
    assert number_as_listed("S54-75", ["S3", "S6"]) == "S54-75"
