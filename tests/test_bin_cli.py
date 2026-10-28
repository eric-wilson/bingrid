"""Bin argparse-generation parity + naming tests against the unified surface.

Preserves the assertions of the old ``tests/test_bin_cli.py`` by building the
unified top parser and asserting the produced ``BinConfig``. The precheck/
validation error paths are exercised in ``tests/test_cli_dispatch.py`` (they go
through ``main``).
"""
import pytest


def _parse(app_mod, argv):
    import bingrid.cli.generators  # noqa: F401  ensure registration

    parser = app_mod._build_top_parser()
    return parser.parse_args(["bin", *argv])


def _bin_spec():
    import bingrid.cli.generators.bin as m

    return m


def test_defaults(app_mod):
    args = _parse(app_mod, [])
    assert args.x == 1 and args.y == 1
    assert args.units == 3
    assert args.stacking_lip is True
    assert args.split_lip is False
    assert args.three_mf is False
    assert args.corner_radius == 3.75


def test_corner_radius_flag_feeds_config(app_mod):
    args = _parse(app_mod, ["--corner-radius", "2.0"])
    assert args.corner_radius == 2.0
    cfg = _bin_spec().build_config(args)
    assert cfg.corner_radius == pytest.approx(2.0)


def test_no_stacking_lip_clears_the_lip(app_mod):
    args = _parse(app_mod, ["--no-stacking-lip"])
    assert args.stacking_lip is False
    cfg = _bin_spec().build_config(args)
    assert cfg.stacking_lip is False


def test_grid_and_units_feed_config(app_mod):
    args = _parse(app_mod, ["--units", "6", "--x", "2", "--y", "1"])
    cfg = _bin_spec().build_config(args)
    assert (cfg.grid_x, cfg.grid_y, cfg.height_units) == (2, 1, 6)


def test_split_lip_sets_flag(app_mod):
    args = _parse(app_mod, ["--split-lip"])
    assert args.split_lip is True


def test_3mf_sets_flag(app_mod):
    args = _parse(app_mod, ["--3mf"])
    assert args.three_mf is True


def test_3mf_defaults_off(app_mod):
    args = _parse(app_mod, [])
    assert args.three_mf is False


def test_3mf_paint_sets_flag(app_mod):
    args = _parse(app_mod, ["--3mf-paint"])
    assert args.three_mf_paint is True


def test_3mf_paint_defaults_off(app_mod):
    args = _parse(app_mod, [])
    assert args.three_mf_paint is False


def test_color_band_flags_feed_config(app_mod):
    args = _parse(
        app_mod,
        ["--3mf-paint", "--color-band", "--units", "6", "--color-band-start",
         "20", "--color-band-height", "6", "--color-band-extruder", "3"],
    )
    cfg = _bin_spec().build_config(args)
    assert cfg.color_band_enabled is True
    assert cfg.paint_mode == "band"
    assert cfg.color_band_start == pytest.approx(20.0)
    assert cfg.color_band_height == pytest.approx(6.0)
    assert cfg.color_band_extruder == 3


def test_3mf_paint_defaults_to_lip_mode(app_mod):
    args = _parse(app_mod, ["--3mf-paint"])
    assert args.color_band is False
    cfg = _bin_spec().build_config(args)
    assert cfg.paint_mode == "lip"


# --- verbatim default/help lift locked --------------------------------------

def _opt(spec, dest):
    return next(o for o in spec.options if o.dest == dest)


def test_bin_defaults_and_help_are_verbatim():
    spec = _bin_spec().SPEC
    assert _opt(spec, "x").default == 1
    assert _opt(spec, "units").default == 3
    assert _opt(spec, "units").help == (
        "count of 7 mm Gridfinity height units (default: 3)"
    )
    assert _opt(spec, "corner_radius").default == 3.75
    assert _opt(spec, "stacking_lip").default is True
    assert _opt(spec, "stacking_lip").negative_flag == "--no-stacking-lip"
    assert _opt(spec, "lip_wall").default is None
    assert _opt(spec, "three_mf").flag == "--3mf"
    assert _opt(spec, "three_mf_paint").flag == "--3mf-paint"


# --- naming ----------------------------------------------------------------

def test_bin_default_name_floor_float_form(gridfinity, tmp_path):
    e = gridfinity.ModelExporter(tmp_path)
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6, floor=1.0)
    assert e.bin_default_name(cfg) == "bin_2x1_u6_lip_floor1.0"


def test_bin_default_name_omits_floor_when_zero(gridfinity, tmp_path):
    e = gridfinity.ModelExporter(tmp_path)
    assert "_floor" not in e.bin_default_name(gridfinity.BinConfig(floor=0))


def test_bin_default_name_nolip(gridfinity, tmp_path):
    e = gridfinity.ModelExporter(tmp_path)
    assert "_nolip" in e.bin_default_name(gridfinity.BinConfig(stacking_lip=False))
