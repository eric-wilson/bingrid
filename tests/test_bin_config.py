"""Validation and derived-value tests for BinConfig and the shared profile.

Pure-Python (no CadQuery render), so they run under the default selection.
All numbers are the RE-MEASURED carbon-copy socket, now the DATACLASS profile
defaults (top_opening=37.7, chamfer_top=2.1, straight=1.75, chamfer_bottom=0.80,
bottom_inset=0.75 -> total_height=4.65, mouth_opening=41.9, bottom_opening=36.2).
Never references samples/ by name.
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
    # re-measured: base_height = profile.total_height (4.65) - base_overlap (1.0) = 3.65
    assert cfg.base_height == pytest.approx(3.65, abs=0.01)
    # total = 3.65 + 35.0 = 38.65
    assert cfg.total_height == pytest.approx(38.65, abs=0.2)
    # The lip is the measured sum of its three segments: lead-in 0.70 + seat
    # run 1.90 + mouth flare 1.20 = 3.80 mm (re-measured carbon-copy lip).
    assert cfg.lip_h == pytest.approx(3.80, abs=0.01)
    assert cfg.overall_height == pytest.approx(38.65 + 3.80, abs=0.2)


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
    # (re-measured base_height=3.65), so base_height..base_height+floor stays
    # solid: the continuous floor slab that joins every cell.
    assert config_mod.BinConfig(floor=0.5).cavity_bottom == pytest.approx(4.15, abs=0.01)
    assert config_mod.BinConfig(floor=1.0).cavity_bottom == pytest.approx(4.65, abs=0.01)
    # Open bottom (floor=0) -> cavity starts right at base_height, no slab.
    assert config_mod.BinConfig(floor=0.0).cavity_bottom == pytest.approx(3.65, abs=0.01)
    # A thick floor still sits base_height above its own thickness.
    assert config_mod.BinConfig(floor=6.0, height_units=6).cavity_bottom == pytest.approx(9.65, abs=0.01)


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
        # explicit lip_wall override of 0 is rejected via resolved_lip_wall
        ({"lip_wall": 0}, "lip wall must be positive"),
        # measured lip segment constants must be positive
        ({"lip_mouth_inset": 0}, "lip_mouth_inset must be positive"),
        ({"lip_lead_h": 0}, "lip_lead_h must be positive"),
        ({"lip_mouth_h": 0}, "lip_mouth_h must be positive"),
        ({"base_overlap": -1}, "base overlap cannot be negative"),
        ({"base_overlap": 5.0}, "base overlap must be less than"),
        ({"wall": 21.0}, "no interior left"),
        ({"floor": 100.0, "height_units": 1}, "floor must be less than"),
        ({"foot_clearance": 20.0}, "foot collapses"),
        # color band geometry validation (only enforced in band mode)
        ({"color_band_enabled": True, "paint_mode": "band",
          "color_band_height": 0}, "color band height"),
        ({"color_band_enabled": True, "paint_mode": "band",
          "color_band_start": 9000.0}, "outside the bin wall"),
        # extruder is validated in both paint modes
        ({"color_band_enabled": True, "color_band_extruder": 1}, "color band extruder"),
        # paint_mode must be a known value
        ({"paint_mode": "nope"}, "paint_mode must be"),
    ],
)
def test_bin_config_rejects_bad_values(config_mod, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        config_mod.BinConfig(**kwargs)


# --- color band defaults + valid enabled band ------------------------------

def test_color_band_defaults(config_mod):
    cfg = config_mod.BinConfig()
    assert cfg.color_band_enabled is False
    assert cfg.color_band_start is None            # None = auto-position
    assert cfg.color_band_height == pytest.approx(5.0)
    assert cfg.color_band_extruder == 2
    assert cfg.paint_mode == "lip"           # paint the lip by default


def test_color_band_auto_centers_in_wall(config_mod):
    # With no explicit start, the band auto-centers in the wall span and fits
    # for ANY bin height -- including short bins where a fixed 35 mm would not.
    for units in (1, 3, 5, 8):
        cfg = config_mod.BinConfig(height_units=units, color_band_enabled=True)
        lo, hi = cfg.base_height, cfg.total_height
        start = cfg.resolved_color_band_start
        assert lo - 1e-9 <= start
        assert cfg.color_band_top <= hi + 1e-9
        # Centered: equal margin above and below the band within the wall span.
        assert start - lo == pytest.approx(hi - cfg.color_band_top, abs=1e-6)


def test_color_band_explicit_start_used_verbatim(config_mod):
    cfg = config_mod.BinConfig(height_units=6, color_band_enabled=True,
                               color_band_start=20.0)
    assert cfg.resolved_color_band_start == pytest.approx(20.0)
    assert cfg.color_band_top == pytest.approx(25.0)


def test_color_band_taller_than_wall_rejected(config_mod):
    # A band thicker than the whole wall can't fit no matter where it sits.
    with pytest.raises(ValueError, match="taller than the bin wall"):
        config_mod.BinConfig(height_units=1, color_band_enabled=True,
                             paint_mode="band", color_band_height=100.0)


# --- stacking-lip derivation (measured carbon-copy) ------------------------

def test_lip_derivation_matches_measured_profile(config_mod):
    """The lip seat/step/wall/height fall out of the shared socket + clearance.

    These are pure arithmetic (no render): the seat opening equals the measured
    37.70 (and the baseplate socket seat), the per-side step is 0.70, the rim
    wall derives to 1.90, and the lip is the 3.80 measured sum of its segments.
    """
    cfg = config_mod.BinConfig()  # 1x1 default
    assert cfg.foot_straight_opening == pytest.approx(37.20)
    assert cfg.lip_seat_opening == pytest.approx(37.70)
    assert cfg.resolved_lip_wall == pytest.approx(1.90)
    assert cfg.lip_seat_step == pytest.approx(0.70)
    assert cfg.lip_h == pytest.approx(3.80)
    assert cfg.lip_seat_run == pytest.approx(1.90)
    # Bin-in-bin stacking gap is structurally tied to the live lip_clearance.
    assert cfg.lip_seat_opening - cfg.foot_straight_opening == pytest.approx(
        2 * cfg.lip_clearance
    )
    # lip_planes(): continuous 39.10 base, 37.70 seat run, 39.90 flared mouth.
    planes = cfg.lip_planes()
    assert [tuple(round(x, 2) for x in pl) for pl in planes] == [
        (0.00, 39.10, 39.10),
        (0.70, 37.70, 37.70),
        (2.60, 37.70, 37.70),
        (3.80, 39.90, 39.90),
    ]
    assert planes[-1][1] > planes[1][1]  # mouth wider than seat (real flare)


def test_lip_step_and_wall_are_grid_independent(config_mod):
    """A wide bin keeps the SAME per-side step (0.70) and rim wall (1.90).

    The seat tracks each axis's interior minus a fixed step, so a 1x2 short-axis
    seat is inner_length - 2*step (37.70), never ~42 (the old single-socket
    bug). The step/wall are keyed off a single cell, not the wide interior.
    """
    cfg = config_mod.BinConfig(grid_x=2, grid_y=1, height_units=6)
    assert cfg.lip_seat_step == pytest.approx(0.70)
    assert cfg.resolved_lip_wall == pytest.approx(1.90)
    planes = cfg.lip_planes()
    # seat plane: long axis 79.70, short axis 37.70 (= inner_length - 2*step).
    assert planes[1][1] == pytest.approx(cfg.inner_width - 2 * 0.70)   # 79.70
    assert planes[1][2] == pytest.approx(cfg.inner_length - 2 * 0.70)  # 37.70
    assert planes[1][2] == pytest.approx(37.70)


def test_lip_wall_override_is_honored(config_mod):
    """An explicit lip_wall overrides the derived value via resolved_lip_wall."""
    cfg = config_mod.BinConfig(lip_wall=2.5)
    assert cfg.resolved_lip_wall == pytest.approx(2.5)
    # The derivation is used only when the field is None.
    assert config_mod.BinConfig(lip_wall=None).resolved_lip_wall == pytest.approx(1.90)


# --- shared profile guards -------------------------------------------------

def test_profile_planes_regression(config_mod):
    planes = config_mod.GridfinityProfile().profile_planes()
    # re-measured carbon-copy socket: bottom 36.2, straight 37.7, mouth 41.9,
    # total 4.65 (chamfer_bottom 0.80 + straight 1.75 -> 2.55).
    expected = [(0.0, 36.2), (0.80, 37.7), (2.55, 37.7), (4.65, 41.9)]
    assert len(planes) == 4
    for p, (z, size) in zip(planes, expected):
        assert p.z == pytest.approx(z)
        assert p.size == pytest.approx(size)


# --- foot corner rounding (concentric with the body) -----------------------

def test_foot_corner_radius_is_concentric_and_tapers(config_mod):
    """Foot corner radius tapers up the profile, concentric with the body.

    Each foot plane's corner arc center must land at the SAME place as the body
    corner's arc center (``foot_ref_half - corner_radius``), so the foot corners
    sit directly under the body corners and the transition closes with no gap.
    That means ``r = corner_radius - (foot_ref_half - foot_half)`` per plane,
    which GROWS as the foot widens toward the body.
    """
    cfg = config_mod.BinConfig(grid_x=1, grid_y=1, height_units=5)
    planes = cfg.profile.foot_planes(cfg.foot_clearance)
    R = cfg.corner_radius
    ref = cfg.foot_ref_half

    radii = [cfg.foot_corner_radius(p.size) for p in planes]
    # Tapers up: non-decreasing from base to top, base small, top ~ body radius.
    assert radii == sorted(radii)
    assert radii[0] < radii[-1]
    # The widest (top) foot plane matches the body corner radius exactly.
    assert radii[-1] == pytest.approx(R, abs=1e-6)
    # Mid-foot is a modest positive radius (rounded, not sharp), in the measured
    # ballpark (base small ~0-1.5, mid ~1.5, top 3.75).
    assert 0.0 < radii[1] < R

    # Concentric: every nonzero-radius plane's corner center is at the shared
    # body-corner center ``ref - R`` (within float tolerance).
    for p, r in zip(planes, radii):
        if r > 0:
            foot_half = p.size / 2.0
            assert foot_half - r == pytest.approx(ref - R, abs=1e-6)


def test_foot_corner_radius_clamps_and_opts_out(config_mod):
    cfg = config_mod.BinConfig(grid_x=1, grid_y=1)
    # Clamped to >= 0 when the taper would go negative (very narrow plane).
    assert cfg.foot_corner_radius(1.0) == 0.0
    # Never exceeds the plane half-width.
    assert cfg.foot_corner_radius(2.0) <= 1.0
    # corner_radius=0 opts every foot plane out (sharp), keeping the old foot.
    sharp = config_mod.BinConfig(grid_x=1, grid_y=1, corner_radius=0.0)
    planes = sharp.profile.foot_planes(sharp.foot_clearance)
    assert all(sharp.foot_corner_radius(p.size) == 0.0 for p in planes)


def test_foot_planes_derive_from_socket(config_mod):
    prof = config_mod.GridfinityProfile()
    socket = prof.profile_planes()
    foot = prof.foot_planes(0.25)
    assert len(foot) == len(socket)
    for f, s in zip(foot, socket):
        assert f.z == pytest.approx(s.z)          # no z flip
        assert f.size == pytest.approx(s.size - 0.5)  # each minus 2*0.25
    # Spot-check the derived sizes (re-measured): 35.7 / 37.2 / 37.2 / 41.4
    assert [round(f.size, 2) for f in foot] == [35.7, 37.2, 37.2, 41.4]
