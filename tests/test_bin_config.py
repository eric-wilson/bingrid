"""Validation and derived-value tests for BinConfig and the shared profile.

Pure-Python (no CadQuery render), so they run under the default selection.
All numbers are the published Gridfinity spec reduced to the DATACLASS profile
defaults (top_opening=37.5, chamfer_top=2.2, straight=1.75, chamfer_bottom=0.85,
bottom_inset=1.6 -> total_height=4.8, mouth_opening=41.9, bottom_opening=34.3),
NOT the plate CLI defaults (2.15/1.8). Never references samples/ by name.
"""
import pytest


# --- footprint math (N*42 - 0.5) -------------------------------------------

@pytest.mark.parametrize(
    "gx,gy,exp_w,exp_l",
    [
        (1, 1, 41.5, 41.5),
        (2, 1, 83.5, 41.5),
        (3, 2, 125.5, 83.5),
    ],
)
def test_footprint_is_n_times_pitch_minus_half(config_mod, gx, gy, exp_w, exp_l):
    cfg = config_mod.BinConfig(grid_x=gx, grid_y=gy)
    assert cfg.width == pytest.approx(exp_w)
    assert cfg.length == pytest.approx(exp_l)


# --- height math (units*7 + base) ------------------------------------------

def test_height_math_matches_spec(config_mod):
    cfg = config_mod.BinConfig(height_units=5)
    assert cfg.body_height == pytest.approx(35.0)
    # base_height = profile.total_height (4.8) - base_overlap (1.0) = 3.8
    assert cfg.base_height == pytest.approx(3.8, abs=0.01)
    # total = 3.8 + 35.0 = 38.8 (tight tolerance: spec number, not masked error)
    assert cfg.total_height == pytest.approx(38.8, abs=0.2)
    # The lip is the full socket cross-section mirrored into the rim, so it adds
    # profile.total_height = chamfer_top + straight + chamfer_bottom
    # = 2.2 + 1.75 + 0.85 = 4.8 mm. (The earlier 3.95 mm value omitted the
    # bottom chamfer, which is exactly the self-supporting lead-in; 4.8 mm is
    # the correct, full-profile lip.)
    assert cfg.lip_h == pytest.approx(4.8, abs=0.01)
    assert cfg.overall_height == pytest.approx(38.8 + 4.8, abs=0.2)


def test_overall_height_without_lip_equals_total(config_mod):
    cfg = config_mod.BinConfig(height_units=5, stacking_lip=False)
    assert cfg.lip_h == pytest.approx(0.0)
    assert cfg.overall_height == pytest.approx(cfg.total_height)


def test_corner_radius_default_is_spec_value(config_mod):
    # Published Gridfinity outer vertical corner radius.
    assert config_mod.BinConfig().corner_radius == pytest.approx(3.75)


def test_units_six_gives_body_42(config_mod):
    cfg = config_mod.BinConfig(height_units=6)
    assert cfg.body_height == pytest.approx(42.0)


# --- cavity ----------------------------------------------------------------

def test_inner_cavity_is_width_minus_two_walls(config_mod):
    cfg = config_mod.BinConfig()
    assert cfg.inner_width == pytest.approx(cfg.width - 2 * cfg.wall)
    assert cfg.inner_length == pytest.approx(cfg.length - 2 * cfg.wall)
    assert cfg.inner_width > 0 and cfg.inner_length > 0


def test_cavity_bottom_sits_a_floor_above_the_feet(config_mod):
    # The cavity starts a floor slab's thickness above the top of the feet
    # (base_height=3.8), so base_height..base_height+floor stays solid: the
    # continuous floor slab that joins every cell.
    assert config_mod.BinConfig(floor=0.5).cavity_bottom == pytest.approx(4.3, abs=0.01)
    assert config_mod.BinConfig(floor=1.0).cavity_bottom == pytest.approx(4.8, abs=0.01)
    # Open bottom (floor=0) -> cavity starts right at base_height, no slab.
    assert config_mod.BinConfig(floor=0.0).cavity_bottom == pytest.approx(3.8, abs=0.01)
    # A thick floor still sits base_height above its own thickness.
    assert config_mod.BinConfig(floor=6.0, height_units=6).cavity_bottom == pytest.approx(9.8, abs=0.01)


# --- validation ------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs,msg",
    [
        ({"grid_x": 0}, "grid dimensions"),
        ({"grid_y": 0}, "grid dimensions"),
        ({"height_units": 0}, "height_units"),
        ({"pitch": 0}, "pitch must be positive"),
        ({"wall": 0}, "wall must be positive"),
        ({"floor": -1}, "floor cannot be negative"),
        ({"corner_radius": -1}, "corner radius cannot be negative"),
        # 25 mm radius > 41.5/2 for the default 1x1 footprint.
        ({"corner_radius": 25.0}, "corner radius too large"),
        ({"foot_clearance": -1}, "foot clearance cannot be negative"),
        ({"lip_clearance": -1}, "lip clearance cannot be negative"),
        ({"lip_wall": 0}, "lip wall must be positive"),
        ({"base_overlap": -1}, "base overlap cannot be negative"),
        ({"base_overlap": 5.0}, "base overlap must be less than"),
        ({"wall": 21.0}, "no interior left"),
        ({"floor": 100.0, "height_units": 1}, "floor must be less than"),
        ({"foot_clearance": 20.0}, "foot collapses"),
        # lip rim wall so thick the perimeter seat opening collapses (<=0)
        ({"lip_wall": 20.0}, "wall too thin for stacking lip"),
    ],
)
def test_bin_config_rejects_bad_values(config_mod, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        config_mod.BinConfig(**kwargs)


# --- shared profile guards -------------------------------------------------

def test_profile_planes_regression(config_mod):
    planes = config_mod.GridfinityProfile().profile_planes()
    expected = [(0.0, 34.3), (0.85, 37.5), (2.6, 37.5), (4.8, 41.9)]
    assert len(planes) == 4
    for p, (z, size) in zip(planes, expected):
        assert p.z == pytest.approx(z)
        assert p.size == pytest.approx(size)


def test_foot_planes_derive_from_socket(config_mod):
    prof = config_mod.GridfinityProfile()
    socket = prof.profile_planes()
    foot = prof.foot_planes(0.25)
    assert len(foot) == len(socket)
    for f, s in zip(foot, socket):
        assert f.z == pytest.approx(s.z)          # no z flip
        assert f.size == pytest.approx(s.size - 0.5)  # each minus 2*0.25
    # Spot-check the derived sizes: 33.8 / 37.0 / 37.0 / 41.4
    assert [round(f.size, 2) for f in foot] == [33.8, 37.0, 37.0, 41.4]
