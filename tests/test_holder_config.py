"""Validation and derived-value tests for HolderConfig (pure, no CadQuery).

Mirrors ``tests/test_bin_config.py`` style and the ``config_mod`` fixture. All
layout numbers are hand-computed from the doc's formula
(``cols = floor((interior + wall)/(pocket + wall))``) against the re-measured
1x1 interior of 39.10 mm. No sample file is read or named.
"""
import pytest


def _bin(config_mod, **kw):
    return config_mod.BinConfig(**kw)


# --- fit-preset resolution (mirrors resolved_lip_wall) ---------------------

@pytest.mark.parametrize("fit,mm", [("snug", 0.25), ("normal", 0.40), ("loose", 0.60)])
def test_fit_preset_resolves_to_mm(config_mod, fit, mm):
    h = config_mod.HolderConfig(
        bin=_bin(config_mod), pocket_shape="rect",
        item_w=20.0, item_d=15.0, fit=fit,
    )
    assert h.resolved_clearance == pytest.approx(mm)


def test_explicit_fit_clearance_overrides_preset(config_mod):
    h = config_mod.HolderConfig(
        bin=_bin(config_mod), pocket_shape="rect",
        item_w=20.0, item_d=15.0, fit="snug", fit_clearance=0.5,
    )
    assert h.resolved_clearance == pytest.approx(0.5)


def test_fit_presets_table(config_mod):
    assert config_mod.FIT_PRESETS == {"snug": 0.25, "normal": 0.40, "loose": 0.60}


# --- pocket footprint ------------------------------------------------------

def test_rect_pocket_footprint_is_item_plus_two_clearance(config_mod):
    # 9V footprint 26.5 x 17.5, fit normal (0.40/side) -> 27.3 x 18.3.
    h = config_mod.HolderConfig(
        bin=_bin(config_mod), pocket_shape="rect",
        item_w=26.5, item_d=17.5, fit="normal",
    )
    assert h.pocket_w == pytest.approx(27.3)
    assert h.pocket_d == pytest.approx(18.3)


def test_round_pocket_dia_is_item_plus_two_clearance(config_mod):
    # AA diameter 14.5, fit snug (0.25/side) -> 15.0; square footprint.
    h = config_mod.HolderConfig(
        bin=_bin(config_mod), pocket_shape="round",
        item_dia=14.5, fit="snug",
    )
    assert h.pocket_dia == pytest.approx(15.0)
    assert h.pocket_w == pytest.approx(15.0)
    assert h.pocket_d == pytest.approx(15.0)


# --- layout math (the single source of truth) ------------------------------

def test_layout_9v_fills_1x1_as_computed(config_mod):
    """9V 26.5x17.5 rect, fit normal, in a 1x1 (interior 39.10).

    pocket 27.3 x 18.3; cols = floor((39.10 + 1.2)/(27.3 + 1.2)) = floor(1.41) = 1;
    rows = floor((39.10 + 1.2)/(18.3 + 1.2)) = floor(2.07) = 2. So 2 pockets.
    (The doc's "2x2" prose is physically impossible in a single 1x1 cell -- two
    27.3 mm pockets would need 55.8 mm against the 39.10 mm interior; the
    authoritative Layout *formula* governs, and gives 2x1.)
    """
    h = config_mod.HolderConfig(
        bin=_bin(config_mod, grid_x=1, grid_y=1), pocket_shape="rect",
        item_w=26.5, item_d=17.5, fit="normal",
    )
    assert h.interior_w == pytest.approx(39.10)
    assert h.interior_l == pytest.approx(39.10)
    assert h.grid_cols == 1
    assert h.grid_rows == 2
    assert h.pocket_count == 2
    # leftover_x = 39.10 - 27.3 = 11.80; leftover_y = 39.10 - (2*18.3 + 1*1.2) = 1.30
    assert h.leftover_x == pytest.approx(11.80, abs=1e-6)
    assert h.leftover_y == pytest.approx(1.30, abs=1e-6)


def test_layout_round_aa_fills_1x1(config_mod):
    """AA dia 14.5, fit snug -> pocket 15.0; cols=rows=floor((39.10+1.2)/16.2)=2."""
    h = config_mod.HolderConfig(
        bin=_bin(config_mod, grid_x=1, grid_y=1), pocket_shape="round",
        item_dia=14.5, fit="snug",
    )
    assert h.grid_cols == 2
    assert h.grid_rows == 2
    assert h.pocket_count == 4
    # block = 2*15.0 + 1*1.2 = 31.2; leftover = 39.10 - 31.2 = 7.90 on both axes.
    assert h.leftover_x == pytest.approx(7.90, abs=1e-6)
    assert h.leftover_y == pytest.approx(7.90, abs=1e-6)


def test_explicit_rows_cols_override_derived(config_mod):
    h = config_mod.HolderConfig(
        bin=_bin(config_mod, grid_x=1, grid_y=1), pocket_shape="round",
        item_dia=14.5, fit="snug", rows=1, cols=1,
    )
    assert h.grid_rows == 1
    assert h.grid_cols == 1
    assert h.pocket_count == 1


def test_pocket_pitch_is_footprint_plus_wall(config_mod):
    h = config_mod.HolderConfig(
        bin=_bin(config_mod), pocket_shape="rect",
        item_w=20.0, item_d=15.0, fit="normal", pocket_wall=1.5,
    )
    assert h.pocket_pitch_x == pytest.approx(20.8 + 1.5)  # 20.0 + 0.8 + 1.5
    assert h.pocket_pitch_y == pytest.approx(15.8 + 1.5)


# --- depth / proud ---------------------------------------------------------

def test_pocket_depth_defaults_to_full_available(config_mod):
    h = config_mod.HolderConfig(
        bin=_bin(config_mod, grid_x=1, grid_y=1), pocket_shape="rect",
        item_w=20.0, item_d=15.0,
    )
    assert h.resolved_pocket_depth == pytest.approx(h.available_depth)


def test_explicit_pocket_depth_wins(config_mod):
    h = config_mod.HolderConfig(
        bin=_bin(config_mod, grid_x=1, grid_y=1, height_units=6),
        pocket_shape="rect", item_w=20.0, item_d=15.0, pocket_depth=10.0,
    )
    assert h.resolved_pocket_depth == pytest.approx(10.0)


def test_item_height_and_proud_drive_depth(config_mod):
    # item 40, proud 6 -> depth 34 (clamped to available on a tall enough bin).
    h = config_mod.HolderConfig(
        bin=_bin(config_mod, grid_x=1, grid_y=1, height_units=6),
        pocket_shape="rect", item_w=20.0, item_d=15.0,
        item_height=40.0, proud=6.0,
    )
    assert h.resolved_pocket_depth == pytest.approx(34.0)


def test_item_height_depth_clamped_to_available(config_mod):
    # The item-height path is clamped to available (units auto-fit normally
    # sizes the bin to the item, so this only guards a hand-built short bin).
    h = config_mod.HolderConfig(
        bin=_bin(config_mod, grid_x=1, grid_y=1, height_units=1),
        pocket_shape="rect", item_w=20.0, item_d=15.0,
        item_height=1000.0, proud=6.0,
    )
    assert h.resolved_pocket_depth == pytest.approx(h.available_depth)


# --- bin delegation --------------------------------------------------------

def test_delegates_bin_geometry(config_mod):
    b = _bin(config_mod, grid_x=2, grid_y=1, height_units=5)
    h = config_mod.HolderConfig(
        bin=b, pocket_shape="rect", item_w=20.0, item_d=15.0,
    )
    assert h.width == pytest.approx(b.width)
    assert h.length == pytest.approx(b.length)
    assert h.cavity_bottom == pytest.approx(b.cavity_bottom)
    assert h.total_height == pytest.approx(b.total_height)


# --- validation rejection --------------------------------------------------

@pytest.mark.parametrize(
    "kwargs,msg",
    [
        # rect missing a dimension
        ({"pocket_shape": "rect", "item_w": 20.0}, "rect pockets need"),
        ({"pocket_shape": "rect", "item_d": 20.0}, "rect pockets need"),
        # rect given a diameter
        ({"pocket_shape": "rect", "item_w": 20.0, "item_d": 15.0,
          "item_dia": 10.0}, "not item_dia"),
        # round missing a diameter
        ({"pocket_shape": "round"}, "round pockets need"),
        # round given rect dims
        ({"pocket_shape": "round", "item_dia": 14.5, "item_w": 10.0},
         "not item_w"),
        # bad shape / fit
        ({"pocket_shape": "oval", "item_w": 20.0, "item_d": 15.0},
         "pocket_shape must be"),
        ({"pocket_shape": "rect", "item_w": 20.0, "item_d": 15.0,
          "fit": "firm"}, "fit must be"),
        # negative clearance
        ({"pocket_shape": "rect", "item_w": 20.0, "item_d": 15.0,
          "fit_clearance": -0.1}, "fit clearance cannot be negative"),
        # negative pocket wall / corner radius
        ({"pocket_shape": "rect", "item_w": 20.0, "item_d": 15.0,
          "pocket_wall": -1.0}, "pocket wall cannot be negative"),
        ({"pocket_shape": "rect", "item_w": 20.0, "item_d": 15.0,
          "pocket_corner_radius": -1.0}, "pocket corner radius cannot be"),
        # item wider than the interior (39.10)
        ({"pocket_shape": "rect", "item_w": 60.0, "item_d": 15.0},
         "pocket wider than interior"),
        ({"pocket_shape": "round", "item_dia": 60.0},
         "pocket wider than interior"),
        # explicit pocket depth deeper than the interior breaches the floor
        ({"pocket_shape": "rect", "item_w": 20.0, "item_d": 15.0,
          "pocket_depth": 1000.0}, "would breach the floor"),
        # non-positive explicit depth
        ({"pocket_shape": "rect", "item_w": 20.0, "item_d": 15.0,
          "pocket_depth": 0.0}, "pocket depth must be positive"),
        # negative item dimension
        ({"pocket_shape": "rect", "item_w": -1.0, "item_d": 15.0},
         "item_w must be positive"),
    ],
)
def test_holder_config_rejects_bad_values(config_mod, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        config_mod.HolderConfig(bin=_bin(config_mod, grid_x=1, grid_y=1), **kwargs)


def test_item_wider_than_interior_is_rejected(config_mod):
    """An item wider than the interior (zero/negative leftover) is rejected."""
    with pytest.raises(ValueError, match="pocket wider than interior"):
        config_mod.HolderConfig(
            bin=_bin(config_mod, grid_x=1, grid_y=1), pocket_shape="rect",
            item_w=50.0, item_d=15.0,
        )


def test_explicit_depth_breaching_floor_is_rejected(config_mod):
    """An explicit pocket depth past the available interior depth is rejected.

    The resolved depth is used verbatim for an explicit ``pocket_depth`` (never
    silently clamped), so the floor-breach guard fires instead of quietly
    shrinking the cavity onto the foot/floor.
    """
    cfg = _bin(config_mod, grid_x=1, grid_y=1, height_units=1)
    available = cfg.total_height - cfg.cavity_bottom
    with pytest.raises(ValueError, match="would breach the floor"):
        config_mod.HolderConfig(
            bin=cfg, pocket_shape="rect", item_w=20.0, item_d=15.0,
            pocket_depth=available + 5.0,
        )
