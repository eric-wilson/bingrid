"""Tests for the bin CLI parsing/naming (no rendering) and error paths."""
import pytest


def test_defaults(bin_mod):
    args = bin_mod.build_parser().parse_args([])
    assert args.x == 1 and args.y == 1
    assert args.units == 3
    assert args.stacking_lip is True
    assert args.split_lip is False
    assert args.three_mf is False
    assert args.corner_radius == 3.75


def test_corner_radius_flag_feeds_config(bin_mod):
    args = bin_mod.build_parser().parse_args(["--corner-radius", "2.0"])
    assert args.corner_radius == 2.0
    cfg = bin_mod.config_from_args(args)
    assert cfg.corner_radius == pytest.approx(2.0)


def test_no_stacking_lip_clears_the_lip(bin_mod):
    args = bin_mod.build_parser().parse_args(["--no-stacking-lip"])
    assert args.stacking_lip is False
    cfg = bin_mod.config_from_args(args)
    assert cfg.stacking_lip is False


def test_grid_and_units_feed_config(bin_mod):
    args = bin_mod.build_parser().parse_args(["--units", "6", "--x", "2", "--y", "1"])
    cfg = bin_mod.config_from_args(args)
    assert (cfg.grid_x, cfg.grid_y, cfg.height_units) == (2, 1, 6)


def test_split_lip_sets_flag(bin_mod):
    args = bin_mod.build_parser().parse_args(["--split-lip"])
    assert args.split_lip is True


def test_3mf_sets_flag(bin_mod):
    args = bin_mod.build_parser().parse_args(["--3mf"])
    assert args.three_mf is True


def test_3mf_defaults_off(bin_mod):
    args = bin_mod.build_parser().parse_args([])
    assert args.three_mf is False


def test_3mf_without_lip_returns_2_and_writes_nothing(bin_mod, tmp_path, capsys):
    rc = bin_mod.main(
        ["--3mf", "--no-stacking-lip", "--output-dir", str(tmp_path)]
    )
    assert rc == 2
    out = capsys.readouterr().out
    assert "error:" in out
    assert not list(tmp_path.glob("*.3mf"))


def test_split_lip_without_lip_returns_2_and_writes_nothing(bin_mod, tmp_path, capsys):
    rc = bin_mod.main(
        ["--split-lip", "--no-stacking-lip", "--output-dir", str(tmp_path)]
    )
    assert rc == 2
    out = capsys.readouterr().out
    assert "error:" in out
    assert not list(tmp_path.glob("*.stl"))


def test_main_reports_validation_error(bin_mod, tmp_path, capsys):
    # --x 0 is genuinely invalid for a bin (the bin has no magnet check, so
    # --wall 0.5 would be valid; use a grid error instead).
    rc = bin_mod.main(["--x", "0", "--output-dir", str(tmp_path)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "error:" in out
    assert not list(tmp_path.glob("*.stl"))


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
