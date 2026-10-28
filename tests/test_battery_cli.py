"""Battery generator CLI tests: preset loading, clamps, naming, registration.

Mirrors ``tests/test_holder_cli.py``: build the unified top parser, parse a
``battery`` subcommand, and assert the produced :class:`HolderConfig`. The
preset factory-loads shape + item dims + height onto the namespace, so these
tests confirm each known type resolves to a valid holder config.
"""
import io
from contextlib import redirect_stdout

import pytest


def _parse(app_mod, argv):
    import bingrid.cli.generators  # noqa: F401  ensure registration

    parser = app_mod._build_top_parser()
    return parser.parse_args(["battery", *argv])


def _battery_spec():
    import bingrid.cli.generators.battery as m

    return m


# --- defaults --------------------------------------------------------------

def test_default_type_is_aa(app_mod):
    args = _parse(app_mod, [])
    assert args.type == "AA"


# --- preset loading --------------------------------------------------------

def test_9v_builds_rect_config(app_mod):
    args = _parse(app_mod, ["--type", "9V"])
    cfg = _battery_spec().build_config(args)
    assert cfg.pocket_shape == "rect"
    assert cfg.item_w == pytest.approx(26.5)
    assert cfg.item_d == pytest.approx(17.5)
    assert cfg.item_dia is None


def test_aa_builds_round_full_height_config(app_mod):
    args = _parse(app_mod, ["--type", "AA"])
    cfg = _battery_spec().build_config(args)
    assert cfg.pocket_shape == "round"
    assert cfg.item_dia == pytest.approx(14.5)
    # 50.5 mm cell minus the clamped proud auto-fits a tall bin (> default 3).
    assert cfg.bin.height_units > 3


@pytest.mark.parametrize("coin", ["CR2032", "CR2025", "CR2016"])
def test_coin_cells_build_with_positive_pocket_depth(app_mod, coin):
    args = _parse(app_mod, ["--type", coin])
    cfg = _battery_spec().build_config(args)
    assert cfg.resolved_pocket_depth > 0


# --- holder pass-through flags still feed config ---------------------------

def test_fit_snug_resolves_clearance(app_mod):
    args = _parse(app_mod, ["--type", "AA", "--fit", "snug"])
    cfg = _battery_spec().build_config(args)
    assert cfg.resolved_clearance == pytest.approx(0.25)


def test_pack_feeds_center_grid_false(app_mod):
    args = _parse(app_mod, ["--type", "AA", "--pack"])
    cfg = _battery_spec().build_config(args)
    assert cfg.center_grid is False


def test_explicit_units_overrides_auto_fit(app_mod):
    args = _parse(app_mod, ["--type", "AA", "--units", "4"])
    cfg = _battery_spec().build_config(args)
    assert cfg.bin.height_units == 4


# --- naming ----------------------------------------------------------------

def test_battery_default_name(app_mod, gridfinity, tmp_path):
    args = _parse(app_mod, ["--type", "AA"])
    cfg = _battery_spec().build_config(args)
    e = gridfinity.ModelExporter(tmp_path)
    name = e.battery_default_name(cfg, "AA")
    assert name.startswith("battery_AA_")
    assert "_round_" in name
    assert "dia14.5" in name


# --- registration + help ---------------------------------------------------

def test_battery_is_registered(app_mod):
    from bingrid.cli.registry import REGISTRY
    import bingrid.cli.generators  # noqa: F401

    assert "battery" in REGISTRY.names()


def test_battery_help_lists_known_types(app_mod):
    parser = app_mod._build_top_parser()
    buf = io.StringIO()
    with pytest.raises(SystemExit):
        with redirect_stdout(buf):
            parser.parse_args(["battery", "--help"])
    text = buf.getvalue()
    for name in ("AA", "9V", "CR2032", "18650"):
        assert name in text
    assert "holder" in text


# --- no raw item-dimension flags -------------------------------------------

def test_no_raw_item_flags_in_spec():
    spec = _battery_spec().SPEC
    dests = {o.dest for o in spec.options}
    assert dests.isdisjoint({"item_w", "item_d", "item_dia", "item_height"})


def test_raw_item_flag_is_rejected(app_mod):
    with pytest.raises(SystemExit):
        _parse(app_mod, ["--item-w", "5"])


# --- interactive menu (CHOICE renders as the type menu) --------------------

def test_interactive_type_menu_selects_type(monkeypatch):
    import bingrid.cli.generators.battery as battery
    import bingrid.cli.prompter as prompter

    pretty = {o.dest: prompter._pretty_name(o.flag) for o in battery.SPEC.options}

    monkeypatch.setattr(
        prompter, "_ask_text", lambda label, default_display: "",
    )
    monkeypatch.setattr(
        prompter, "_ask_choice",
        lambda label, choices, default: "9V"
        if label == pretty["type"] else default,
    )
    monkeypatch.setattr(prompter, "_ask_bool", lambda label, default: default)

    ns = prompter.walk_options(battery.SPEC)
    assert ns.type == "9V"
    cfg = battery.build_config(ns)
    assert cfg.pocket_shape == "rect"
    assert cfg.item_w == pytest.approx(26.5)
