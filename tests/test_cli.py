"""Grid argparse-generation parity tests against the unified CLI surface.

These preserve the assertions of the old ``tests/test_cli.py`` (which parsed the
old ``bingrid.cli`` parser) by building the unified top parser and asserting the
produced ``GridConfig`` for the same flag sets. The expected default/help
literals are captured here so the verbatim lift is locked.
"""
import pytest


def _parse(generators_mod, app_mod, argv):
    """Parse ``["grid", *argv]`` through the unified top parser."""
    import bingrid.cli.generators  # noqa: F401  ensure registration

    parser = app_mod._build_top_parser()
    return parser.parse_args(["grid", *argv])


def _grid_spec():
    import bingrid.cli.generators.grid as m

    return m


def test_defaults_build_valid_config(generators_mod, app_mod):
    args = _parse(generators_mod, app_mod, [])
    cfg = _grid_spec().build_config(args)
    assert cfg.grid_x == 2 and cfg.grid_y == 2
    assert cfg.magnet.enabled is True
    assert cfg.opening_style == "socket"   # Gridfinity socket by default
    assert cfg.floor == 0.0                # open floor by default
    assert cfg.connector.enabled is False  # off unless requested


def test_style_and_floor_flags(generators_mod, app_mod):
    args = _parse(
        generators_mod, app_mod,
        ["--style", "taper", "--floor", "1.5", "--no-magnets"],
    )
    cfg = _grid_spec().build_config(args)
    assert cfg.opening_style == "taper"
    assert cfg.floor == pytest.approx(1.5)


def test_profile_flags_feed_config(generators_mod, app_mod):
    args = _parse(
        generators_mod, app_mod,
        ["--profile-top-opening", "37.0", "--profile-straight", "2.0"],
    )
    cfg = _grid_spec().build_config(args)
    assert cfg.profile.top_opening == pytest.approx(37.0)
    assert cfg.profile.straight == pytest.approx(2.0)


def test_grid_and_taper_flags(generators_mod, app_mod):
    args = _parse(
        generators_mod, app_mod, ["--x", "4", "--y", "3", "--taper-angle", "0"]
    )
    cfg = _grid_spec().build_config(args)
    assert (cfg.grid_x, cfg.grid_y) == (4, 3)
    assert cfg.taper.enabled is False


def test_no_magnets_flag(generators_mod, app_mod):
    args = _parse(generators_mod, app_mod, ["--no-magnets", "--height", "8"])
    cfg = _grid_spec().build_config(args)
    assert cfg.magnet.enabled is False


def test_connector_flags(generators_mod, app_mod):
    args = _parse(
        generators_mod, app_mod,
        ["--connectors", "--connector-width", "10", "--connector-depth", "3"],
    )
    cfg = _grid_spec().build_config(args)
    assert cfg.connector.enabled is True
    assert cfg.connector.width == pytest.approx(10.0)
    assert cfg.connector.depth == pytest.approx(3.0)


def test_main_reports_validation_error_without_crashing(app_mod, tmp_path, capsys):
    # wall too thin for magnets -> config raises -> main returns code 2.
    rc = app_mod.main(["grid", "--wall", "0.5", "--output-dir", str(tmp_path)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "error:" in out
    assert not list(tmp_path.glob("*.stl"))  # nothing written on failure


# --- verbatim default/help lift locked --------------------------------------

def _opt(spec, dest):
    return next(o for o in spec.options if o.dest == dest)


def test_grid_defaults_and_help_are_verbatim():
    spec = _grid_spec().SPEC
    assert _opt(spec, "x").default == 2
    assert _opt(spec, "x").help == "cells in X (default: 2)"
    assert _opt(spec, "wall").default == 5.0
    assert _opt(spec, "wall").help == "border/crossbar thickness in mm (default: 5)"
    assert _opt(spec, "height").default is None
    assert _opt(spec, "style").default == "socket"
    assert _opt(spec, "style").choices == ("socket", "taper")
    assert _opt(spec, "magnets").default is True
    assert _opt(spec, "connectors").default is False
