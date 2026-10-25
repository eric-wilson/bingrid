"""Validation and derived-value tests for the config value objects.

These are pure-Python and require no CadQuery render, so they run under the
default (non-integration) test selection.
"""
import math

import pytest


# --- MagnetConfig ----------------------------------------------------------

def test_magnet_bore_radius_includes_clearance(config_mod):
    m = config_mod.MagnetConfig(diameter=3.0, clearance=0.2)
    assert m.bore_radius == pytest.approx((3.0 + 0.2) / 2)


def test_magnet_pocket_depth_includes_glue(config_mod):
    m = config_mod.MagnetConfig(depth=1.0, glue_gap=0.3)
    assert m.pocket_depth == pytest.approx(1.3)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"diameter": 0},
        {"diameter": -1},
        {"depth": 0},
        {"clearance": -0.1},
        {"glue_gap": -0.1},
        {"orientation": "sideways"},
        {"shape": "square"},
        {"teardrop_angle_deg": 0},
        {"teardrop_angle_deg": 90},
    ],
)
def test_magnet_rejects_bad_values(config_mod, kwargs):
    with pytest.raises(ValueError):
        config_mod.MagnetConfig(**kwargs)


def test_magnet_defaults_are_horizontal_teardrop(config_mod):
    m = config_mod.MagnetConfig()
    assert m.orientation == "horizontal"
    assert m.shape == "teardrop"


def test_magnet_teardrop_peak_at_45_degrees(config_mod):
    import math

    m = config_mod.MagnetConfig(diameter=3.0, clearance=0.2, teardrop_angle_deg=45.0)
    expected = m.bore_radius * (1.0 / math.sin(math.radians(45.0)) - 1.0)
    assert m.teardrop_peak == pytest.approx(expected)
    assert m.teardrop_peak > 0  # a real peak above the circle


# --- TaperConfig -----------------------------------------------------------

def test_taper_zero_is_disabled(config_mod):
    assert config_mod.TaperConfig(angle_deg=0).enabled is False


def test_taper_positive_is_enabled(config_mod):
    assert config_mod.TaperConfig(angle_deg=2).enabled is True


@pytest.mark.parametrize("angle", [-1, 45, 90])
def test_taper_rejects_out_of_range(config_mod, angle):
    with pytest.raises(ValueError):
        config_mod.TaperConfig(angle_deg=angle)


# --- ConnectorConfig -------------------------------------------------------

def test_connector_inner_wider_than_mouth(config_mod):
    c = config_mod.ConnectorConfig(width=8.0, flare=1.5)
    assert c.inner_width == pytest.approx(11.0)
    assert c.inner_width > c.width


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 0},
        {"depth": 0},
        {"flare": -0.1},
        {"width": 3.0, "flare": 1.5},   # flare*2 >= width -> non-positive mouth
        {"clearance": -0.1},
    ],
)
def test_connector_rejects_bad_values(config_mod, kwargs):
    with pytest.raises(ValueError):
        config_mod.ConnectorConfig(**kwargs)


# --- GridfinityProfile -----------------------------------------------------

def test_profile_total_height_sums_segments(config_mod):
    p = config_mod.GridfinityProfile(
        chamfer_top=2.2, straight=1.75, chamfer_bottom=0.85
    )
    assert p.total_height == pytest.approx(4.8)


def test_profile_mouth_wider_than_top_wider_than_bottom(config_mod):
    p = config_mod.GridfinityProfile()
    assert p.mouth_opening > p.top_opening > p.bottom_opening


def test_profile_defaults_match_bgg_reference(config_mod):
    # These defaults reproduce the measured BGG V1.0.0 reference profile.
    p = config_mod.GridfinityProfile()
    assert p.top_opening == pytest.approx(37.5)
    assert p.bottom_opening == pytest.approx(34.3)  # 37.5 - 2*1.6
    assert p.total_height == pytest.approx(4.8)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"top_opening": 0},
        {"chamfer_top": 0},
        {"straight": 0},
        {"chamfer_bottom": 0},
        {"bottom_inset": -0.1},
        {"top_opening": 2.0, "bottom_inset": 1.6},  # bottom opening <= 0
    ],
)
def test_profile_rejects_bad_values(config_mod, kwargs):
    with pytest.raises(ValueError):
        config_mod.GridfinityProfile(**kwargs)


# --- GridConfig ------------------------------------------------------------

def test_grid_dimensions_and_derived_sizes(config_mod):
    cfg = config_mod.GridConfig(grid_x=3, grid_y=2, pitch=42.0)
    assert cfg.width == pytest.approx(126.0)
    assert cfg.length == pytest.approx(84.0)


def test_resolved_height_autofits_round_magnet_when_unset(config_mod):
    # Round horizontal pocket: a large magnet drives the auto height to the
    # bore diameter plus margin (above the legacy 10 mm taper floor).
    cfg = config_mod.GridConfig(
        opening_style="taper",
        magnet=config_mod.MagnetConfig(diameter=12.0, shape="round"),
    )
    assert cfg.resolved_height == pytest.approx(2 * cfg.magnet.bore_radius + 2.0)


def test_resolved_height_autofits_teardrop_magnet_when_unset(config_mod):
    # Teardrop pocket needs extra room for the roof peak.
    cfg = config_mod.GridConfig(
        opening_style="taper",
        magnet=config_mod.MagnetConfig(diameter=12.0, shape="teardrop"),
    )
    m = cfg.magnet
    assert cfg.resolved_height == pytest.approx(
        2 * m.bore_radius + m.teardrop_peak + 2.0
    )
    # And the teardrop reserves strictly more height than a round bore.
    round_cfg = config_mod.GridConfig(
        opening_style="taper",
        magnet=config_mod.MagnetConfig(diameter=12.0, shape="round"),
    )
    assert cfg.resolved_height > round_cfg.resolved_height


def test_resolved_height_respects_explicit_value(config_mod):
    cfg = config_mod.GridConfig(height=12.0)
    assert cfg.resolved_height == pytest.approx(12.0)


def test_resolved_height_default_socket_without_magnets(config_mod):
    # Socket style auto-sizes to the profile height when nothing else is larger.
    cfg = config_mod.GridConfig(
        magnet=config_mod.MagnetConfig(enabled=False), height=None
    )
    assert cfg.resolved_height == pytest.approx(
        cfg.profile.total_height
    )


def test_resolved_height_default_taper_without_magnets(config_mod):
    cfg = config_mod.GridConfig(
        opening_style="taper",
        taper=config_mod.TaperConfig(angle_deg=2.0),
        magnet=config_mod.MagnetConfig(enabled=False),
        height=None,
    )
    assert cfg.resolved_height == pytest.approx(10.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"grid_x": 0},
        {"grid_y": 0},
        {"pitch": 0},
        {"wall": 0},
        {"wall": 42.0},          # wall >= pitch leaves no opening
        {"height": -1},
    ],
)
def test_grid_rejects_bad_values(config_mod, kwargs):
    with pytest.raises(ValueError):
        config_mod.GridConfig(**kwargs)


def test_grid_rejects_wall_too_thin_for_magnet(config_mod):
    with pytest.raises(ValueError, match="wall too thin"):
        config_mod.GridConfig(
            wall=0.5, magnet=config_mod.MagnetConfig(depth=1.0, glue_gap=0.3)
        )


def test_grid_rejects_height_too_small_for_magnet(config_mod):
    with pytest.raises(ValueError, match="height too small"):
        config_mod.GridConfig(
            height=1.0, magnet=config_mod.MagnetConfig(diameter=3.0)
        )


def test_grid_rejects_connector_deeper_than_wall(config_mod):
    with pytest.raises(ValueError, match="less than wall"):
        config_mod.GridConfig(
            wall=5.0,
            magnet=config_mod.MagnetConfig(enabled=False),
            connector=config_mod.ConnectorConfig(enabled=True, depth=6.0),
        )


def test_grid_default_style_is_socket_open_floor(config_mod):
    cfg = config_mod.GridConfig()
    assert cfg.opening_style == "socket"
    assert cfg.floor == 0.0


def test_grid_rejects_unknown_opening_style(config_mod):
    with pytest.raises(ValueError, match="opening_style"):
        config_mod.GridConfig(opening_style="banana")


def test_grid_rejects_negative_floor(config_mod):
    with pytest.raises(ValueError, match="floor cannot be negative"):
        config_mod.GridConfig(floor=-1.0)


def test_grid_rejects_floor_thicker_than_height(config_mod):
    with pytest.raises(ValueError, match="floor must be less"):
        config_mod.GridConfig(
            height=5.0, floor=6.0, magnet=config_mod.MagnetConfig(enabled=False)
        )


def test_grid_rejects_height_too_small_for_socket(config_mod):
    with pytest.raises(ValueError, match="socket profile"):
        config_mod.GridConfig(
            height=2.0,
            magnet=config_mod.MagnetConfig(enabled=False),
            profile=config_mod.GridfinityProfile(),  # total 4.8 > 2.0
        )


def test_grid_rejects_socket_mouth_wider_than_pitch(config_mod):
    with pytest.raises(ValueError, match="mouth wider than pitch"):
        config_mod.GridConfig(
            pitch=42.0,
            magnet=config_mod.MagnetConfig(enabled=False),
            profile=config_mod.GridfinityProfile(top_opening=41.0, chamfer_top=1.0),
        )


def test_grid_floor_adds_to_autosized_height(config_mod):
    cfg = config_mod.GridConfig(
        floor=2.0, magnet=config_mod.MagnetConfig(enabled=False)
    )
    assert cfg.resolved_height == pytest.approx(cfg.profile.total_height + 2.0)


def test_grid_rejects_vertical_magnet_deeper_than_plate(config_mod):
    with pytest.raises(ValueError, match="vertical magnet pocket deeper"):
        config_mod.GridConfig(
            grid_x=2, grid_y=2, height=3.0, floor=1.0,
            opening_style="taper",
            magnet=config_mod.MagnetConfig(
                orientation="vertical", depth=3.0, glue_gap=0.3
            ),
        )


def test_grid_accepts_vertical_magnet_with_floor(config_mod):
    # Should construct without error.
    cfg = config_mod.GridConfig(
        grid_x=2, grid_y=2, floor=2.0,
        magnet=config_mod.MagnetConfig(orientation="vertical"),
    )
    assert cfg.magnet.orientation == "vertical"


def test_grid_rejects_connector_wider_than_edge(config_mod):
    with pytest.raises(ValueError, match="too wide"):
        config_mod.GridConfig(
            grid_x=1, grid_y=1, pitch=42.0, wall=5.0,
            magnet=config_mod.MagnetConfig(enabled=False),
            connector=config_mod.ConnectorConfig(
                enabled=True, width=40.0, flare=1.0, depth=4.0
            ),
        )
