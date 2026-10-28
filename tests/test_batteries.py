"""Battery preset library (data) tests: order, well-formedness, seeded dims."""
import pytest

from bingrid.batteries import PRESETS, preset_names, type_help

EXPECTED_ORDER = [
    "AA", "AAA", "C", "D", "9V", "CR2032", "CR2025", "CR2016", "18650",
]


def test_presets_have_all_names_in_order():
    assert list(PRESETS) == EXPECTED_ORDER
    assert preset_names() == tuple(EXPECTED_ORDER)


def test_every_entry_is_well_formed():
    for name, preset in PRESETS.items():
        assert preset.name == name
        assert preset.height > 0
        if preset.shape == "round":
            assert preset.item_dia is not None
            assert preset.item_w is None and preset.item_d is None
        else:
            assert preset.shape == "rect"
            assert preset.item_w is not None and preset.item_d is not None
            assert preset.item_dia is None


def test_seeded_dimensions_match():
    assert PRESETS["AA"].item_dia == pytest.approx(14.5)
    assert PRESETS["AA"].height == pytest.approx(50.5)
    assert PRESETS["9V"].shape == "rect"
    assert PRESETS["9V"].item_w == pytest.approx(26.5)
    assert PRESETS["9V"].item_d == pytest.approx(17.5)
    assert PRESETS["9V"].height == pytest.approx(48.5)
    assert PRESETS["CR2032"].item_dia == pytest.approx(20.0)
    assert PRESETS["CR2032"].height == pytest.approx(3.2)
    assert PRESETS["18650"].item_dia == pytest.approx(18.6)
    assert PRESETS["18650"].height == pytest.approx(65.2)


def test_type_help_mentions_every_type_and_holder_note():
    text = type_help()
    for name in EXPECTED_ORDER:
        assert name in text
    assert "holder" in text
