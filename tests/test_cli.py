"""Tests for CLI argument parsing and config assembly (no rendering)."""
import pytest


def test_defaults_build_valid_config(cli_mod):
    args = cli_mod.build_parser().parse_args([])
    cfg = cli_mod.config_from_args(args)
    assert cfg.grid_x == 2 and cfg.grid_y == 2
    assert cfg.magnet.enabled is True
    assert cfg.opening_style == "socket"   # Gridfinity socket by default
    assert cfg.floor == 0.0                # open floor by default
    assert cfg.connector.enabled is False  # off unless requested


def test_style_and_floor_flags(cli_mod):
    args = cli_mod.build_parser().parse_args(
        ["--style", "taper", "--floor", "1.5", "--no-magnets"]
    )
    cfg = cli_mod.config_from_args(args)
    assert cfg.opening_style == "taper"
    assert cfg.floor == pytest.approx(1.5)


def test_profile_flags_feed_config(cli_mod):
    args = cli_mod.build_parser().parse_args(
        ["--profile-top-opening", "37.0", "--profile-straight", "2.0"]
    )
    cfg = cli_mod.config_from_args(args)
    assert cfg.profile.top_opening == pytest.approx(37.0)
    assert cfg.profile.straight == pytest.approx(2.0)


def test_grid_and_taper_flags(cli_mod):
    args = cli_mod.build_parser().parse_args(
        ["--x", "4", "--y", "3", "--taper-angle", "0"]
    )
    cfg = cli_mod.config_from_args(args)
    assert (cfg.grid_x, cfg.grid_y) == (4, 3)
    assert cfg.taper.enabled is False


def test_no_magnets_flag(cli_mod):
    args = cli_mod.build_parser().parse_args(["--no-magnets", "--height", "8"])
    cfg = cli_mod.config_from_args(args)
    assert cfg.magnet.enabled is False


def test_connector_flags(cli_mod):
    args = cli_mod.build_parser().parse_args(
        ["--connectors", "--connector-width", "10", "--connector-depth", "3"]
    )
    cfg = cli_mod.config_from_args(args)
    assert cfg.connector.enabled is True
    assert cfg.connector.width == pytest.approx(10.0)
    assert cfg.connector.depth == pytest.approx(3.0)


def test_main_reports_validation_error_without_crashing(cli_mod, tmp_path, capsys):
    # wall too thin for magnets -> config raises -> main returns code 2.
    rc = cli_mod.main(["--wall", "0.5", "--output-dir", str(tmp_path)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "error:" in out
    assert not list(tmp_path.glob("*.stl"))  # nothing written on failure
