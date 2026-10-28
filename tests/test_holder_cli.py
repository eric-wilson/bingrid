"""Holder argparse-generation parity + layout-driver + naming tests.

Mirrors ``tests/test_bin_cli.py``: build the unified top parser, parse a holder
subcommand, and assert the produced :class:`HolderConfig`. The precheck/
validation error paths (exit code 2) are exercised in
``tests/test_cli_dispatch.py`` (they go through ``main``).
"""
import pytest


def _parse(app_mod, argv):
    import bingrid.cli.generators  # noqa: F401  ensure registration

    parser = app_mod._build_top_parser()
    return parser.parse_args(["holder", *argv])


def _holder_spec():
    import bingrid.cli.generators.holder as m

    return m


# --- defaults --------------------------------------------------------------

def test_defaults(app_mod):
    args = _parse(app_mod, [])
    assert args.pocket_shape == "rect"
    assert args.fit == "normal"
    assert args.center_grid is True
    assert args.x is None and args.y is None
    assert args.units is None
    assert args.pocket_wall == 1.2
    assert args.pocket_corner_radius == 1.0
    assert args.proud == 6.0


def test_pack_clears_center_grid(app_mod):
    args = _parse(app_mod, ["--pack"])
    assert args.center_grid is False


# --- flags feed config -----------------------------------------------------

def test_rect_item_dims_build_valid_config(app_mod):
    args = _parse(app_mod, ["--x", "1", "--y", "1", "--pocket-shape", "rect",
                            "--item-w", "26.5", "--item-d", "17.5"])
    cfg = _holder_spec().build_config(args)
    assert cfg.pocket_shape == "rect"
    assert cfg.item_w == pytest.approx(26.5)
    assert cfg.item_d == pytest.approx(17.5)
    assert cfg.bin.grid_x == 1 and cfg.bin.grid_y == 1


def test_fit_snug_resolves_clearance(app_mod):
    args = _parse(app_mod, ["--x", "1", "--y", "1", "--item-w", "20",
                            "--item-d", "15", "--fit", "snug"])
    cfg = _holder_spec().build_config(args)
    assert cfg.resolved_clearance == pytest.approx(0.25)


def test_pack_feeds_center_grid_false(app_mod):
    args = _parse(app_mod, ["--x", "1", "--y", "1", "--item-w", "20",
                            "--item-d", "15", "--pack"])
    cfg = _holder_spec().build_config(args)
    assert cfg.center_grid is False


def test_round_item_feeds_config(app_mod):
    args = _parse(app_mod, ["--x", "1", "--y", "1", "--pocket-shape", "round",
                            "--item-dia", "14.5"])
    cfg = _holder_spec().build_config(args)
    assert cfg.pocket_shape == "round"
    assert cfg.pocket_dia == pytest.approx(14.5 + 2 * 0.40)


# --- layout drivers --------------------------------------------------------

def test_fill_bin_uses_given_size(app_mod):
    args = _parse(app_mod, ["--x", "2", "--y", "1", "--item-w", "20",
                            "--item-d", "15"])
    cfg = _holder_spec().build_config(args)
    assert (cfg.bin.grid_x, cfg.bin.grid_y) == (2, 1)


def test_fit_count_picks_a_bin_that_holds_target(app_mod):
    """--count 8 with the 9V item picks a bin whose grid holds >= 8 pockets."""
    args = _parse(app_mod, ["--pocket-shape", "rect", "--item-w", "26.5",
                            "--item-d", "17.5", "--count", "8"])
    cfg = _holder_spec().build_config(args)
    assert cfg.pocket_count >= 8
    # Smallest whole-cell footprint that holds 8 (a 1x1 holds 2, a 3x1 holds 8).
    assert cfg.bin.grid_x * cfg.bin.grid_y <= 3


def test_fit_count_default_size_is_1x1(app_mod):
    args = _parse(app_mod, ["--item-w", "20", "--item-d", "15"])
    cfg = _holder_spec().build_config(args)
    assert (cfg.bin.grid_x, cfg.bin.grid_y) == (1, 1)


def test_explicit_rows_cols_with_oversize_item_grows_bin(app_mod):
    """A single big pocket (60x30) in a 1x1 cradle grows the bin to fit it.

    fit-count "holds them" means the pocket physically fits the interior, so a
    60 mm pocket (wider than a 39.10 mm 1x1 interior) picks a 2x1 bin.
    """
    args = _parse(app_mod, ["--rows", "1", "--cols", "1", "--pocket-shape",
                            "rect", "--item-w", "60", "--item-d", "30",
                            "--fit", "loose"])
    cfg = _holder_spec().build_config(args)
    assert cfg.pocket_count == 1
    assert cfg.bin.grid_x >= 2  # grew to hold the 60 mm pocket


def test_units_auto_fit_from_item_height(app_mod):
    # A 48 mm item standing 10 mm proud needs 38 mm of pocket depth; the bin
    # auto-sizes its height units up from the default 3 to hold it.
    args = _parse(app_mod, ["--x", "1", "--y", "1", "--item-w", "20",
                            "--item-d", "15", "--item-height", "48",
                            "--proud", "10"])
    cfg = _holder_spec().build_config(args)
    assert cfg.bin.height_units > 3
    assert cfg.available_depth + 1e-9 >= 48 - 10


def test_explicit_units_wins(app_mod):
    args = _parse(app_mod, ["--x", "1", "--y", "1", "--item-w", "20",
                            "--item-d", "15", "--item-height", "48",
                            "--proud", "10", "--units", "4"])
    cfg = _holder_spec().build_config(args)
    assert cfg.bin.height_units == 4


# --- verbatim default/help lift + registration -----------------------------

def _opt(spec, dest):
    return next(o for o in spec.options if o.dest == dest)


def test_holder_center_grid_is_pack_pair():
    spec = _holder_spec().SPEC
    assert _opt(spec, "center_grid").default is True
    assert _opt(spec, "center_grid").negative_flag == "--pack"


def test_holder_inherits_bin_options_verbatim():
    spec = _holder_spec().SPEC
    assert _opt(spec, "stacking_lip").negative_flag == "--no-stacking-lip"
    assert _opt(spec, "three_mf").flag == "--3mf"
    assert _opt(spec, "three_mf_paint").flag == "--3mf-paint"
    assert _opt(spec, "wall").default == 1.2


def test_holder_is_registered():
    from bingrid.cli.registry import REGISTRY
    import bingrid.cli.generators  # noqa: F401

    assert "holder" in REGISTRY.names()


# --- naming ----------------------------------------------------------------

def test_holder_default_name_rect(app_mod, gridfinity, tmp_path):
    args = _parse(app_mod, ["--x", "1", "--y", "1", "--pocket-shape", "rect",
                            "--item-w", "26.5", "--item-d", "17.5",
                            "--item-height", "48", "--proud", "10"])
    cfg = _holder_spec().build_config(args)
    e = gridfinity.ModelExporter(tmp_path)
    name = e.holder_default_name(cfg)
    assert name.startswith("holder_1x1_")
    assert "_rect_" in name
    assert name.endswith("26.5x17.5")


def test_holder_default_name_round(app_mod, gridfinity, tmp_path):
    args = _parse(app_mod, ["--x", "1", "--y", "1", "--pocket-shape", "round",
                            "--item-dia", "14.5"])
    cfg = _holder_spec().build_config(args)
    e = gridfinity.ModelExporter(tmp_path)
    name = e.holder_default_name(cfg)
    assert "_round_" in name
    assert name.endswith("dia14.5")
