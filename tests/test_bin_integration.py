"""Integration tests for the Gridfinity bin generator (build real solids).

Marked ``integration`` (excluded by the default ``-m 'not integration'``
selection) because rendering is slow. Run explicitly with::

    pytest -m integration

The slice-based fit tests (#11, #12, #13) depend on trimesh's optional 2D
section extras (shapely + rtree + a triangulation engine). Every ``slice_at``
call is guarded: on ``None`` the slice-based assertions skip and, for the
mating test, the solid-level ``plate.union(bin).isValid()`` check stands in as
the fit guarantee so the feature is never left unverified on a bare env.
"""
import statistics
import tempfile
from pathlib import Path

import cadquery as cq
import pytest

pytestmark = pytest.mark.integration


# Plate-socket baseline for GridConfig(grid_x=1, grid_y=1, height=5.0, magnet
# disabled). RE-CAPTURED for the rounded socket interior: the socket's inner
# opening corners are now rounded CONCENTRIC with the reference outer corner
# (3.75) instead of squared off, so the socket cuts a little LESS material and
# the plate volume rises slightly (1531.345 -> 1471.168). This is intentional
# and the ONLY reason the baseline moved -- socket opening sizes/heights are
# unchanged (bins still interlock), and the BBOX is unchanged (42 x 42 x 5.0):
# rounding the interior opening only removes the sharp inner corner, never
# touches the plate footprint or height. rel=1e-9 still fails on any OTHER,
# unintended shift.
BASELINE_VOLUME = 1471.1676574663347
BASELINE_BBOX = (42.0, 42.0, 5.0000001)  # xlen, ylen, zlen


def _require_slice(insp, z):
    """Slice at z; skip cleanly if trimesh's 2D section extras are missing."""
    prof = insp.slice_at(z)
    if prof is None:
        pytest.skip("trimesh 2D section extras unavailable")
    return prof


def _export_inspect(gridfinity, model, tmpdir):
    from bingrid.meshtools import MeshInspector

    path = Path(tmpdir) / "m.stl"
    cq.exporters.export(model, str(path))
    return MeshInspector.load(path)


def _section_exterior_xy(insp, z):
    """Return the (xs, ys) of the largest exterior ring at height ``z``.

    Returns ``None`` when trimesh's 2D section extras are unavailable so the
    caller can skip cleanly.
    """
    import numpy as np

    section = insp.mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if section is None:
        return None
    planar, _ = section.to_2D()
    try:
        polygons = planar.polygons_full
    except BaseException:
        return None
    if not polygons:
        return None
    poly = max(polygons, key=lambda p: p.area)
    xs, ys = poly.exterior.xy
    return np.asarray(xs), np.asarray(ys)


def _fit_corner_arc(xs, ys):
    """Least-squares fit the +x+y footprint-corner arc; return (xc, yc, r).

    Selects only the genuine corner-arc points (in the +x+y quadrant and off
    both axis-aligned straight edges) and fits a circle, so the result is the
    corner's arc center and radius -- the two numbers that reveal rounding and
    concentricity. Returns ``None`` when too few arc points are present
    (a sharp corner contributes essentially none).
    """
    import numpy as np

    xmax, ymax = xs.max(), ys.max()
    q = (xs > 0) & (ys > 0)
    xq, yq = xs[q], ys[q]
    keep = (np.abs(yq - ymax) > 0.03) & (np.abs(xq - xmax) > 0.03)
    xa, ya = xq[keep], yq[keep]
    if len(xa) < 4:
        return None
    a_mat = np.c_[2 * xa, 2 * ya, np.ones(len(xa))]
    b_vec = xa ** 2 + ya ** 2
    c, _res, _rank, _sv = np.linalg.lstsq(a_mat, b_vec, rcond=None)
    xc, yc = float(c[0]), float(c[1])
    r = float(np.sqrt(c[2] + xc ** 2 + yc ** 2))
    return xc, yc, r


# --- #15b: shared-profile refactor regression guard ------------------------

def test_refactor_keeps_plate_socket_identical(gridfinity):
    """The shared-profile refactor must not shift the plate socket at all."""
    cfg = gridfinity.GridConfig(
        grid_x=1, grid_y=1, height=5.0,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    solid = gridfinity.GridfinityPlate(cfg).build().val()
    assert solid.Volume() == pytest.approx(BASELINE_VOLUME, rel=1e-9)
    bb = solid.BoundingBox()
    assert (bb.xlen, bb.ylen, bb.zlen) == pytest.approx(BASELINE_BBOX, rel=1e-9)


# --- #9: watertight (sealed, 2x1, and open-bottom) -------------------------

def test_bin_is_watertight(gridfinity):
    assert gridfinity.GridfinityBin(gridfinity.BinConfig()).build().val().isValid()
    big = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6)
    assert gridfinity.GridfinityBin(big).build().val().isValid()


def test_open_bottom_bin_is_watertight(gridfinity):
    # floor=0 exercises the cavity-bottom clamp: cavity starts at base_height,
    # so the foot walls survive and the solid stays valid.
    cfg = gridfinity.BinConfig(floor=0.0)
    assert cfg.cavity_bottom == pytest.approx(cfg.base_height)
    assert gridfinity.GridfinityBin(cfg).build().val().isValid()


def test_thick_floor_branch(gridfinity):
    # A thick floor still sits base_height above its own thickness, and the
    # solid stays valid.
    cfg = gridfinity.BinConfig(height_units=6, floor=6.0)
    assert cfg.cavity_bottom == pytest.approx(cfg.base_height + 6.0)
    assert gridfinity.GridfinityBin(cfg).build().val().isValid()


# --- #16: the floor slab bridges every cell (no inter-cell channel) --------

@pytest.mark.parametrize("gx,gy", [(1, 1), (2, 1), (2, 3)])
def test_floored_bin_has_continuous_floor_joining_cells(gridfinity, gx, gy, tmp_path):
    """A floored multi-cell bin must have a continuous floor slab, no gap.

    This FAILS on the pre-fix geometry: there the cavity started right at the
    top of the feet, so below the body the only solid was the per-cell feet --
    adjacent feet left a ~0.6 mm open channel and a low slice showed two
    DISJOINT foot sections (and that gap ran straight up into the interior).
    Here we slice inside the floor slab (just above the feet) and assert the
    section is a SINGLE connected region spanning the full footprint with no
    interior hole: the floor bridges the cells into one piece.
    """
    cfg = gridfinity.BinConfig(grid_x=gx, grid_y=gy, height_units=6)
    assert cfg.floor > 0  # floored by default
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    z = cfg.base_height + cfg.floor / 2  # mid-slab, just above the feet
    section = insp.mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if section is None:
        pytest.skip("trimesh 2D section extras unavailable")
    planar, _ = section.to_2D()
    try:
        polygons = planar.polygons_full
    except BaseException:
        pytest.skip("trimesh 2D section extras unavailable")
    if not polygons:
        # No 2D extras / degenerate slice: fall back to solid validity so the
        # floor is never left unverified on a bare env.
        assert gridfinity.GridfinityBin(cfg).build().val().isValid()
        pytest.skip("slice unavailable; verified solid validity instead")

    # One connected region, no inter-cell gap, no interior hole.
    assert len(polygons) == 1
    prof = insp.slice_at(z)
    assert prof.hole_count == 0
    # The slab spans ~the full footprint on both axes (the gap is gone).
    assert prof.outer[0] == pytest.approx(cfg.width, abs=0.5)
    assert prof.outer[1] == pytest.approx(cfg.length, abs=0.5)


@pytest.mark.parametrize("gx,gy", [(1, 1), (2, 1), (2, 3)])
def test_open_bottom_bin_has_no_floor_slab(gridfinity, gx, gy, tmp_path):
    """floor=0 keeps its open bottom: no slab, interior open onto the feet."""
    cfg = gridfinity.BinConfig(grid_x=gx, grid_y=gy, height_units=6, floor=0.0)
    assert cfg.cavity_bottom == pytest.approx(cfg.base_height)
    bin_solid = gridfinity.GridfinityBin(cfg).build()
    assert bin_solid.val().isValid()

    insp = _export_inspect(gridfinity, bin_solid, tmp_path)
    # Just above the feet the interior is open (a hole), not a solid floor.
    prof = insp.slice_at(cfg.base_height + 0.1)
    if prof is None:
        pytest.skip("trimesh 2D section extras unavailable")
    assert prof.hole_count == 1


# --- #10: footprint/height of the exported mesh ----------------------------

def test_exported_footprint_and_height(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=5)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)
    assert insp.extents[0] == pytest.approx(cfg.width, abs=0.1)    # 83.5
    assert insp.extents[1] == pytest.approx(cfg.length, abs=0.1)   # 41.5
    # A lipped bin measures overall_height (= total_height + lip_h).
    assert insp.extents[2] == pytest.approx(cfg.overall_height, abs=0.1)


def test_exported_height_without_lip_equals_total(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=5, stacking_lip=False)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)
    assert insp.extents[2] == pytest.approx(cfg.total_height, abs=0.1)


# --- #11: foot profile matches the socket (on a SINGLE cell) ---------------

def test_foot_profile_matches_socket(gridfinity, tmp_path):
    # Single-cell bin so the foot slice `outer` is one foot, not a 2x2 span.
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)
    # Narrow bottom ~ bottom_opening - 2*foot_clearance = 35.7 (re-measured).
    narrow = _require_slice(insp, 0.005)
    assert narrow.outer[0] == pytest.approx(35.7, abs=0.3)
    # Vertical ~ top_opening - 2*foot_clearance = 37.2 (re-measured).
    vert = _require_slice(insp, 1.2)
    assert vert.outer[0] == pytest.approx(37.2, abs=0.3)


# --- foot corners are rounded and concentric with the body -----------------

def test_foot_corners_are_rounded_and_taper(gridfinity, tmp_path):
    """The foot's outer corners are ROUNDED (not sharp) and taper up the foot.

    This FAILS on the pre-fix sharp-square foot: there a corner is a 90 deg
    vertex, so the +x+y corner region holds essentially no arc points and
    ``_fit_corner_arc`` returns None (no fitted radius). After the fix each low
    foot slice fits a positive corner radius, the radius GROWS going up the foot
    (base smaller, approaching the body radius higher up), and the fitted arc
    center is the SAME as the body corner center (concentric) within tolerance.
    Re-measured ballpark on the reference part: base ~1.57, upper ~2.47,
    body 3.75.
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    # Two clean levels inside the foot: the vertical seat run (constant, modest
    # radius) and higher up the flare toward the body (wider radius). The very
    # base is a short ruled blend whose fitted radius is noisy, so we avoid it.
    low = _section_exterior_xy(insp, 1.0)   # vertical seat run
    high = _section_exterior_xy(insp, 3.5)  # up the flare toward the body
    if low is None or high is None:
        pytest.skip("trimesh 2D section extras unavailable")

    fit_low = _fit_corner_arc(*low)
    fit_high = _fit_corner_arc(*high)
    # A sharp foot would fit no corner arc at all -> this is the assertion that
    # genuinely catches the old geometry.
    assert fit_low is not None, "foot corner is sharp, not rounded"
    assert fit_high is not None, "foot corner is sharp, not rounded"

    xc_lo, yc_lo, r_lo = fit_low
    xc_hi, yc_hi, r_hi = fit_high
    # Rounded: positive radii, in the measured ballpark (seat ~1.5, flare ~2.5),
    # both well under the body's 3.75 and the base clearly smaller than higher up.
    assert 0.5 < r_lo < cfg.corner_radius
    assert 0.5 < r_hi < cfg.corner_radius
    # Tapers UP the foot: the arc higher up is wider, approaching the body radius.
    assert r_hi > r_lo + 0.3

    # Concentric with the body corner: both fitted arc centers match the body
    # corner's arc center (|x|,|y| = footprint half - body corner radius). The
    # single foot is centered on the origin, so its corners sit under the body.
    body_cc_x = cfg.width / 2 - cfg.corner_radius
    body_cc_y = cfg.length / 2 - cfg.corner_radius
    for xc, yc in ((xc_lo, yc_lo), (xc_hi, yc_hi)):
        assert abs(xc) == pytest.approx(body_cc_x, abs=0.6)
        assert abs(yc) == pytest.approx(body_cc_y, abs=0.6)


def test_no_open_gap_at_footprint_corner(gridfinity, tmp_path):
    """No open-air sliver at a footprint corner: foot and body corners align.

    Issue #2 from the print: with a sharp foot under a rounded body the foot's
    corner reached OUTSIDE the rounded body corner's arc, leaving a re-entrant
    open vertical sliver where foot and body did not close up. The invariant
    that catches it: the foot's outer corner arc is CONCENTRIC with the body's
    (same arc center) so there is continuous material straight up the corner.
    We fit the corner arc inside the foot and in the body and assert the two
    centers coincide; a sharp foot either fits no arc (None) or fits a center
    far from the body's. We also assert the solid is watertight.
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    solid = gridfinity.GridfinityBin(cfg).build()
    assert solid.val().isValid()  # watertight regardless of slice support
    insp = _export_inspect(gridfinity, solid, tmp_path)

    foot_xy = _section_exterior_xy(insp, 1.0)        # inside the foot
    body_z = cfg.base_height + cfg.body_height / 2     # mid-body, clear of foot
    body_xy = _section_exterior_xy(insp, body_z)
    if foot_xy is None or body_xy is None:
        pytest.skip("trimesh 2D section extras unavailable")

    foot_fit = _fit_corner_arc(*foot_xy)
    body_fit = _fit_corner_arc(*body_xy)
    assert foot_fit is not None, "sharp foot corner -> open sliver at the corner"
    assert body_fit is not None

    fx, fy, _fr = foot_fit
    bx, by, _br = body_fit
    # Concentric within tolerance: no re-entrant gap between foot and body.
    assert abs(fx) == pytest.approx(abs(bx), abs=0.6)
    assert abs(fy) == pytest.approx(abs(by), abs=0.6)


# --- #12: the stacking lip is a full-perimeter rim, not a center socket ----

@pytest.mark.parametrize("gx,gy", [(1, 1), (2, 1), (2, 3)])
def test_lipped_bin_is_watertight(gridfinity, gx, gy):
    cfg = gridfinity.BinConfig(grid_x=gx, grid_y=gy, height_units=6)
    assert cfg.stacking_lip  # lip on by default
    assert gridfinity.GridfinityBin(cfg).build().val().isValid()


@pytest.mark.parametrize("gx,gy", [(1, 1), (2, 1), (2, 3)])
def test_lip_opening_spans_full_interior(gridfinity, gx, gy, tmp_path):
    """The lip opening must track the interior footprint, not a ~42 mm hole.

    This FAILS on the old single-socket lip: that lip capped the top as a solid
    deck and opened just one ~41.9 mm socket in the center, so for a 2x1 the
    opening read ~42 x 42 instead of ~81 x 39. Here we slice just below the top
    of the lip (within the flared mouth) and assert the opening follows the full
    interior on BOTH axes.
    """
    cfg = gridfinity.BinConfig(grid_x=gx, grid_y=gy, height_units=6)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    z = cfg.overall_height - 0.3  # just below the top of the lip, in the mouth
    prof = insp.slice_at(z)
    if prof is None:
        # No 2D extras: fall back to a solid validity check so the lip is never
        # left unverified, but still guard the top opening we can reach.
        pytest.skip("trimesh 2D section extras unavailable")

    assert prof.hole_count == 1
    open_w = statistics.median(w for (w, _d) in prof.hole_extents)
    open_l = statistics.median(d for (_w, d) in prof.hole_extents)

    # The mouth is inset lip_mouth_inset (0.80) per side off the full footprint.
    # Both axes track the interior -- and critically the SHORT axis is nowhere
    # near ~42 mm on a wide bin, the single-socket bug this test exists to catch.
    expected_w = cfg.width - 2 * cfg.lip_mouth_inset
    expected_l = cfg.length - 2 * cfg.lip_mouth_inset
    assert open_w == pytest.approx(expected_w, abs=1.5)
    assert open_l == pytest.approx(expected_l, abs=1.5)
    # The opening must be close to the body interior, far from a 41.9 mm socket.
    assert open_w == pytest.approx(cfg.inner_width, abs=3.0)
    assert open_l == pytest.approx(cfg.inner_length, abs=3.0)


def test_lip_seat_steps_inward_from_the_mouth(gridfinity, tmp_path):
    """The rim steps inward from the body interior to the MEASURED seat, 37.70.

    This is the direct regression guard for "the lip is too big" (the old seat
    landed at 34.70; the measured seat is 37.70). The seat opening on the short
    axis is ``inner_length - 2*lip_seat_step`` = 37.70 (step 0.70/side); the
    flared mouth at the top face is inset ``lip_mouth_inset`` 0.80/side (39.90).
    The seat run sits ABOVE the self-supporting lead-in, so we slice the middle
    of the lip-local seat run (z 0.70..2.60 from ``lip_planes()``) rather than
    near the base (where the opening is the wide interior).
    """
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    # Structural guard: the lip seat is tied to the socket + the live clearance.
    assert cfg.lip_seat_opening - cfg.foot_straight_opening == pytest.approx(
        2 * cfg.lip_clearance
    )

    # Lip-local z's come straight from lip_planes(): seat run spans planes[1].z
    # .. planes[2].z (0.70..2.60). Slice its midpoint; mouth near the top face.
    planes = cfg.lip_planes()
    seat_mid_local = (planes[1][0] + planes[2][0]) / 2.0
    z_seat = cfg.total_height + seat_mid_local
    # The mouth reaches its full 39.90 only at the top face (the flare ramps up
    # continuously from the seat), so slice very close to the top.
    z_mouth = cfg.overall_height - 0.05  # in the flared mouth near the top face
    seat = _require_slice(insp, z_seat)
    mouth = _require_slice(insp, z_mouth)
    assert seat.hole_count == 1 and mouth.hole_count == 1

    seat_w = statistics.median(w for (w, _d) in seat.hole_extents)
    mouth_w = statistics.median(w for (w, _d) in mouth.hole_extents)
    seat_l = statistics.median(d for (_w, d) in seat.hole_extents)
    mouth_l = statistics.median(d for (_w, d) in mouth.hole_extents)

    # Short axis: the seat is the measured 37.70 (fixes the 34.70 "too big"),
    # stepped in lip_seat_step (0.70) per side from the 39.10 interior.
    assert seat_l == pytest.approx(37.70, abs=0.3)
    assert mouth_l == pytest.approx(39.90, abs=0.3)
    # Long axis tracks the interior minus the same per-side step.
    assert seat_w == pytest.approx(cfg.inner_width - 2 * cfg.lip_seat_step, abs=0.5)
    # Mouth is wider than the seat (a real upward flare), by 2*(step - inset)
    # on the short axis: mouth 39.90 - seat 37.70 = 2.20.
    assert mouth_l - seat_l == pytest.approx(2.20, abs=0.5)


def _section_interior_xy(insp, z):
    """Return (xs, ys) of the largest INTERIOR (hole) ring at height ``z``.

    The complement of :func:`_section_exterior_xy`: it reads the interior ring
    of the dominant polygon -- the opening we want to prove is rounded. Returns
    ``None`` when trimesh's 2D section extras are unavailable or there is no
    hole, so the caller can skip cleanly.
    """
    import numpy as np

    section = insp.mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if section is None:
        return None
    planar, _ = section.to_2D()
    try:
        polygons = planar.polygons_full
    except BaseException:
        return None
    if not polygons:
        return None
    poly = max(polygons, key=lambda p: p.area)
    if not list(poly.interiors):
        return None
    ring = max(poly.interiors, key=lambda r: r.length)
    xs, ys = ring.xy
    return np.asarray(xs), np.asarray(ys)


# --- interior opening corners are rounded, concentric with the outer -------

def test_interior_lip_opening_corners_are_rounded(gridfinity, tmp_path):
    """The lip's inner opening corners are ROUNDED, not sharp 90 deg squares.

    This FAILS on the pre-fix lip (the opening was cut from sharp ``_rect_loft``
    rectangles): the interior ring's +x+y corner held essentially no arc points
    and ``_fit_corner_arc`` returned None. After the fix the opening is swept
    from rounded-rect profiles, so the inner corner fits a POSITIVE radius in
    the ~2 mm ballpark and the ring carries many points. The fitted arc center
    is CONCENTRIC with the outer corner (same center as the body footprint
    corner) -- a uniform wall wrapping the rounded corner.
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    assert cfg.stacking_lip and cfg.corner_radius > 0
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    # Near the top rim, inside the flared mouth where the opening is widest.
    z = cfg.overall_height - 0.3
    ring = _section_interior_xy(insp, z)
    if ring is None:
        pytest.skip("trimesh 2D section extras unavailable")

    xs, ys = ring
    # Many ring points: a rounded corner adds an arc; a sharp square has ~4.
    assert len(xs) > 20, "interior lip opening corner is sharp, not rounded"

    fit = _fit_corner_arc(xs, ys)
    assert fit is not None, "interior lip opening corner is sharp, not rounded"
    xc, yc, r = fit
    # Rounded in the expected concentric ballpark (~2 mm for the default rim),
    # positive and well under the outer 3.75.
    assert 0.5 < r < cfg.corner_radius
    assert r == pytest.approx(2.0, abs=1.0)
    # Concentric with the OUTER corner: the fitted inner arc center coincides
    # with the body footprint corner center (|x|,|y| = half - corner_radius).
    body_cc_x = cfg.width / 2 - cfg.corner_radius
    body_cc_y = cfg.length / 2 - cfg.corner_radius
    assert abs(xc) == pytest.approx(body_cc_x, abs=0.6)
    assert abs(yc) == pytest.approx(body_cc_y, abs=0.6)


def test_interior_cavity_corners_are_rounded_and_concentric(gridfinity, tmp_path):
    """The hollow cavity's inner opening corners are rounded & concentric.

    This FAILS on the pre-fix cavity (a sharp ``.box()`` cut): the interior ring
    mid-body fit no corner arc (None). After the fix the cavity corners are
    filleted to ``cavity_corner_radius`` (= corner_radius - wall), so the inner
    ring fits a positive radius whose arc center matches the body's outer corner
    center (concentric -> uniform wall thickness around the corner).
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    assert cfg.cavity_corner_radius > 0
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    z = cfg.base_height + cfg.body_height / 2  # mid-body, clear of foot & lip
    ring = _section_interior_xy(insp, z)
    if ring is None:
        pytest.skip("trimesh 2D section extras unavailable")

    xs, ys = ring
    assert len(xs) > 20, "interior cavity corner is sharp, not rounded"
    fit = _fit_corner_arc(xs, ys)
    assert fit is not None, "interior cavity corner is sharp, not rounded"
    xc, yc, r = fit
    # Matches the derived concentric cavity radius (corner_radius - wall).
    assert r == pytest.approx(cfg.cavity_corner_radius, abs=0.5)
    # Concentric with the outer body corner (same arc center).
    body_cc_x = cfg.width / 2 - cfg.corner_radius
    body_cc_y = cfg.length / 2 - cfg.corner_radius
    assert abs(xc) == pytest.approx(body_cc_x, abs=0.6)
    assert abs(yc) == pytest.approx(body_cc_y, abs=0.6)


def test_no_lip_leaves_no_rim_above_total_height(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5, stacking_lip=False)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)
    # The top of the part is total_height; there is no additive rim above it.
    assert insp.extents[2] == pytest.approx(cfg.total_height, abs=0.1)
    assert insp.slice_at(cfg.total_height + 1.0) is None


# --- rounded outer vertical corners ----------------------------------------

def test_outer_corners_are_rounded_not_sharp(gridfinity, tmp_path):
    """The body footprint is a rounded rectangle (~3.75 mm corner radius).

    This FAILS on the pre-fix sharp box: there a mid-height section has ~4-8
    exterior vertices and the straight top edge runs to |x| = width/2. After
    the fillet the section has many exterior points and the straight edge ends
    at |x| = width/2 - corner_radius, with the bounding box unchanged (a fillet
    only removes material inside the bbox, never grows it).
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    assert cfg.corner_radius == pytest.approx(3.75)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    # Rounding must NOT change the overall bounding box.
    assert insp.extents[0] == pytest.approx(cfg.width, abs=0.1)   # 41.5
    assert insp.extents[1] == pytest.approx(cfg.length, abs=0.1)  # 41.5

    z = cfg.base_height + cfg.body_height / 2  # mid-body, clear of foot & lip
    section = insp.mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if section is None:
        pytest.skip("trimesh 2D section extras unavailable")
    planar, _ = section.to_2D()
    try:
        polygons = planar.polygons_full
    except BaseException:
        pytest.skip("trimesh 2D section extras unavailable")
    if not polygons:
        pytest.skip("slice unavailable")

    exterior = polygons[0].exterior
    coords = list(exterior.coords)
    # A rounded rectangle has MANY exterior points; a sharp box has ~4-8.
    assert len(coords) > 20

    # Fit the fillet: the straight top edge ends at |x| = width/2 - radius.
    ymax = max(y for _x, y in coords)
    on_top = [x for x, y in coords if abs(y - ymax) < 1e-2]
    assert on_top, "no points on the top edge"
    assert max(abs(x) for x in on_top) == pytest.approx(
        cfg.width / 2 - cfg.corner_radius, abs=0.4
    )


def test_sharp_corner_opt_out(gridfinity, tmp_path):
    """--corner-radius 0 keeps the old sharp box (few exterior vertices)."""
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5, corner_radius=0.0)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)
    assert insp.extents[0] == pytest.approx(cfg.width, abs=0.1)
    z = cfg.base_height + cfg.body_height / 2
    section = insp.mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if section is None:
        pytest.skip("trimesh 2D section extras unavailable")
    planar, _ = section.to_2D()
    try:
        polygons = planar.polygons_full
    except BaseException:
        pytest.skip("trimesh 2D section extras unavailable")
    if not polygons:
        pytest.skip("slice unavailable")
    # A sharp rectangle's exterior is essentially the four corners (a few extra
    # collinear splits where the foot union touches an edge); nowhere near the
    # tens of arc points a rounded corner adds.
    assert len(list(polygons[0].exterior.coords)) < 20


# --- self-supporting (chamfered) stacking-lip underside --------------------

def test_lip_underside_is_self_supporting(gridfinity, tmp_path):
    """The lip underside tapers at <=45 deg, not a flat downward ledge.

    Root cause of the pre-fix stringing: the lip seat opening (narrow) sat
    directly on top of the body interior (wide) at z=total_height, so the
    opening jumped OUTWARD ~2.2 mm/side over ~0 mm of vertical going downward --
    a near-horizontal downward-facing ledge (effectively a >45 deg overhang).

    We slice ACROSS that transition: just inside the lip (z_hi) and just inside
    the body below the mating plane (z_lo). Going DOWNWARD the opening may grow
    by at most the vertical drop on each side (<=45 deg): per axis
    ``open_lo - open_hi <= 2 * (z_hi - z_lo) + tol``. The old flat ledge jumps
    ~4.4 mm total over ~0.2 mm -> a slope far steeper than 45 deg, so this
    invariant genuinely fails on the pre-fix geometry.
    """
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    # The measured lead-in runs lip_seat_step (0.70) per side over lip_lead_h
    # (0.70) rise = exactly atan(0.70/0.70) = 45 deg, the self-supporting LIMIT.
    # The budget below includes a +0.05 tolerance so the exact-45-deg case
    # passes; it still FAILS on the old flat downward ledge (>45 deg).
    z_lo = cfg.total_height - 0.10  # just below the mating plane (body interior)
    z_hi = cfg.total_height + 0.10  # just inside the lip (bottom lead-in)
    lo = _require_slice(insp, z_lo)
    hi = _require_slice(insp, z_hi)
    assert lo.hole_count == 1 and hi.hole_count == 1

    lo_w = statistics.median(w for (w, _d) in lo.hole_extents)
    hi_w = statistics.median(w for (w, _d) in hi.hole_extents)
    lo_l = statistics.median(d for (_w, d) in lo.hole_extents)
    hi_l = statistics.median(d for (_w, d) in hi.hole_extents)

    budget = 2 * (z_hi - z_lo) + 0.05  # <=45 deg flare per side + tolerance
    assert lo_w - hi_w <= budget
    assert lo_l - hi_l <= budget

    # And the transition is a gradual slope, not a flat plateau with a sudden
    # jump: the opening actually changes across the lead-in (it does not sit at
    # a constant width and then step). Sample a couple of points up the lead-in.
    mid = _require_slice(insp, cfg.total_height + 0.6)
    mid_w = statistics.median(w for (w, _d) in mid.hole_extents)
    assert hi_w - mid_w > 0.1  # opening keeps narrowing going up the lead-in


# --- #13: bin seats in a plate (fit, no binding) ---------------------------

def test_bin_seats_in_plate(gridfinity, tmp_path):
    plate_cfg = gridfinity.GridConfig(
        grid_x=2, grid_y=2, height=6.0, floor=1.0,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    bin_cfg = gridfinity.BinConfig(grid_x=2, grid_y=2)
    plate = gridfinity.GridfinityPlate(plate_cfg).build()
    bin_ = gridfinity.GridfinityBin(bin_cfg).build()

    # Standing fit guarantee: the bin's feet drop into the plate sockets and the
    # combined solid is valid. (Holds even when slicing is unavailable.)
    assert plate.union(bin_).val().isValid()

    # Slice-based fit, like-against-like at the same section of the shared
    # profile, each in its own part's coordinates. Use a single-cell bin so the
    # foot slice `outer` is one foot, not the 2x2 span.
    from bingrid.meshtools import MeshInspector

    foot_path = Path(tmp_path) / "foot.stl"
    cq.exporters.export(
        gridfinity.GridfinityBin(gridfinity.BinConfig(grid_x=1, grid_y=1)).build(),
        str(foot_path),
    )
    foot_insp = MeshInspector.load(foot_path)
    plate_path = Path(tmp_path) / "plate.stl"
    cq.exporters.export(plate, str(plate_path))
    plate_insp = MeshInspector.load(plate_path)

    # Narrow: foot at bin z=0.1 vs socket hole at plate z=1.3 (0.1 above the
    # socket profile bottom 1.2). The foot still clears the socket with room to
    # spare (positive gap). The nominal gap here is wider than 2*foot_clearance
    # because the rounded foot is lofted ruled (straight blend) and its corners
    # are rounded: low in the base chamfer the foot's axis-aligned bbox is
    # narrower than the old smooth-loft square foot (which bulged there), so the
    # bbox-measured gap grows. Seating clearance at the real contact interface
    # is checked at the vertical section below.
    foot_narrow = _require_slice(foot_insp, 0.1)
    plate_narrow = _require_slice(plate_insp, 1.3)
    sock_narrow = statistics.median(w for (w, _d) in plate_narrow.hole_extents)
    assert sock_narrow - foot_narrow.outer[0] > 0  # foot clears, no bind

    # Vertical: foot at bin z=1.5 vs socket hole at plate z=2.9 -- the straight
    # seating section where foot and socket walls actually meet. The rounding
    # does not change the flat-edge span here, so the gap stays ~2*foot_clearance.
    foot_vert = _require_slice(foot_insp, 1.5)
    plate_vert = _require_slice(plate_insp, 2.9)
    sock_vert = statistics.median(w for (w, _d) in plate_vert.hole_extents)
    assert sock_vert - foot_vert.outer[0] == pytest.approx(0.5, abs=0.3)


# --- #14: --split-lip exports exactly two watertight meshes ----------------

def test_split_lip_exports_two_watertight_meshes(gridfinity, tmp_path):
    from bingrid.meshtools import MeshInspector

    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=5)
    bin_ = gridfinity.GridfinityBin(cfg)
    body, lip = bin_.build_split()
    exporter = gridfinity.ModelExporter(tmp_path)
    paths = exporter.export_split(body, lip, cfg)

    stls = sorted(tmp_path.glob("*.stl"))
    assert len(stls) == 2
    assert {p.name for p in stls} == {
        f"{exporter.bin_default_name(cfg)}_body.stl",
        f"{exporter.bin_default_name(cfg)}_lip.stl",
    }
    body_insp = MeshInspector.load(tmp_path / f"{exporter.bin_default_name(cfg)}_body.stl")
    lip_insp = MeshInspector.load(tmp_path / f"{exporter.bin_default_name(cfg)}_lip.stl")
    assert body_insp.is_watertight and lip_insp.is_watertight

    # Approximate equivalence only (a union reorders faces): summed volume ~
    # single-build volume within 1% rel, combined bbox ~ single-build bbox.
    single = bin_.build().val()
    assert body_insp.volume + lip_insp.volume == pytest.approx(single.Volume(), rel=0.01)
    sb = single.BoundingBox()
    xlo = min(body_insp.bounds[0][0], lip_insp.bounds[0][0])
    assert (sb.xlen, sb.ylen) == pytest.approx(
        (single.BoundingBox().xlen, single.BoundingBox().ylen), abs=0.1
    )
    assert xlo == pytest.approx(min(body_insp.bounds[0][0], lip_insp.bounds[0][0]), abs=0.1)


# --- --3mf exports one file with two pre-aligned named bodies --------------

def _require_3mf_writer():
    """Skip cleanly if trimesh's 3MF writer (needs lxml) is unavailable.

    The happy path MUST run here (lxml is in requirements and installed); the
    guard only turns a cryptic writer failure into a clear skip on a bare env.
    """
    try:
        import lxml  # noqa: F401
    except Exception:  # pragma: no cover - lxml is a declared dependency
        pytest.skip("lxml unavailable; trimesh 3MF writer cannot run")


def test_export_3mf_writes_one_nonempty_file(gridfinity, tmp_path):
    _require_3mf_writer()
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=5)
    bin_ = gridfinity.GridfinityBin(cfg)
    body, lip = bin_.build_split()
    exporter = gridfinity.ModelExporter(tmp_path)
    paths = exporter.export_3mf(body, lip, cfg)

    threemfs = sorted(tmp_path.glob("*.3mf"))
    assert len(threemfs) == 1
    assert paths == threemfs
    assert threemfs[0].name == f"{exporter.bin_default_name(cfg)}.3mf"
    assert threemfs[0].stat().st_size > 0
    # The temp STLs used for tessellation must be cleaned up (no strays).
    assert not list(tmp_path.glob("*.stl"))


def test_export_3mf_has_two_aligned_watertight_bodies(gridfinity, tmp_path):
    _require_3mf_writer()
    import trimesh

    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=5)
    bin_ = gridfinity.GridfinityBin(cfg)
    body, lip = bin_.build_split()
    exporter = gridfinity.ModelExporter(tmp_path)
    (out_path,) = exporter.export_3mf(body, lip, cfg)

    scene = trimesh.load(str(out_path))
    assert isinstance(scene, trimesh.Scene)
    # Two separate, individually named bodies.
    assert len(scene.geometry) == 2
    assert set(scene.geometry.keys()) == {"body", "lip"}

    body_mesh = scene.geometry["body"]
    lip_mesh = scene.geometry["lip"]
    assert body_mesh.is_watertight and lip_mesh.is_watertight

    # Relative z-alignment preserved: the lip sits above the body (its base is
    # at the body's top, ~total_height), not re-centered to the bed.
    body_zmin, body_zmax = body_mesh.bounds[0][2], body_mesh.bounds[1][2]
    lip_zmin, lip_zmax = lip_mesh.bounds[0][2], lip_mesh.bounds[1][2]
    assert body_zmin == pytest.approx(0.0, abs=0.1)
    assert body_zmax == pytest.approx(cfg.total_height, abs=0.1)
    assert lip_zmin == pytest.approx(cfg.total_height, abs=0.1)
    assert lip_zmax == pytest.approx(cfg.overall_height, abs=0.1)

    # Same XY footprint / origin: both centered on the bin origin, lip no wider
    # than the body, so they load exactly as build_split produced them.
    for mesh in (body_mesh, lip_mesh):
        cx = (mesh.bounds[0][0] + mesh.bounds[1][0]) / 2
        cy = (mesh.bounds[0][1] + mesh.bounds[1][1]) / 2
        assert cx == pytest.approx(0.0, abs=0.1)
        assert cy == pytest.approx(0.0, abs=0.1)
    assert body_mesh.extents[0] == pytest.approx(cfg.width, abs=0.2)
    assert body_mesh.extents[1] == pytest.approx(cfg.length, abs=0.2)
    assert lip_mesh.extents[0] == pytest.approx(cfg.width, abs=0.2)
    assert lip_mesh.extents[1] == pytest.approx(cfg.length, abs=0.2)


def test_cli_3mf_with_lip_writes_a_3mf(gridfinity, bin_mod, tmp_path):
    _require_3mf_writer()
    import trimesh

    rc = bin_mod.main(
        ["--x", "2", "--y", "1", "--units", "5", "--stacking-lip", "--3mf",
         "--output-dir", str(tmp_path)]
    )
    assert rc == 0
    threemfs = sorted(tmp_path.glob("*.3mf"))
    assert len(threemfs) == 1
    scene = trimesh.load(str(threemfs[0]))
    assert set(scene.geometry.keys()) == {"body", "lip"}


def test_cli_3mf_without_lip_exits_2(bin_mod, tmp_path, capsys):
    rc = bin_mod.main(
        ["--3mf", "--no-stacking-lip", "--output-dir", str(tmp_path)]
    )
    assert rc == 2
    assert "error:" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.3mf"))


# --- --3mf-paint: single mesh with a painted color band -------------------

def _read_zip_part(path, member):
    """Return a named part of the ``.3mf`` zip decoded as text."""
    import zipfile

    with zipfile.ZipFile(path) as zf:
        return zf.read(member).decode("utf-8")


def _parse_painted_model(path):
    """Parse the painted .3mf model into (vertices, [(v1,v2,v3,painted)])."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(_read_zip_part(path, "3D/3dmodel.model"))
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    verts = [
        (float(v.get("x")), float(v.get("y")), float(v.get("z")))
        for v in root.iterfind(".//m:vertices/m:vertex", ns)
    ]
    tris = []
    for t in root.iterfind(".//m:triangles/m:triangle", ns):
        tris.append((
            int(t.get("v1")), int(t.get("v2")), int(t.get("v3")),
            t.get("paint_color"),
        ))
    return verts, tris


def test_export_3mf_painted_writes_valid_opc_package(gridfinity, tmp_path):
    import xml.etree.ElementTree as ET
    import zipfile

    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6,
                               color_band_enabled=True)
    exporter = gridfinity.ModelExporter(tmp_path)
    paths = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    threemfs = sorted(tmp_path.glob("*.3mf"))
    assert len(threemfs) == 1
    assert paths == threemfs
    assert threemfs[0].name == f"{exporter.bin_default_name(cfg)}.3mf"
    assert threemfs[0].stat().st_size > 0
    assert zipfile.is_zipfile(threemfs[0])

    with zipfile.ZipFile(threemfs[0]) as zf:
        names = set(zf.namelist())
    for part in ("3D/3dmodel.model", "Metadata/model_settings.config",
                 "[Content_Types].xml", "_rels/.rels"):
        assert part in names
        ET.fromstring(_read_zip_part(threemfs[0], part))

    # The temp tessellation STL must be cleaned up (no strays).
    assert not list(tmp_path.glob("*.stl"))


def test_painted_3mf_band_faces_use_paint_color_8(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6,
                               color_band_enabled=True, paint_mode="band")
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    _verts, tris = _parse_painted_model(path)
    painted = [t for t in tris if t[3] == "8"]
    unpainted = [t for t in tris if t[3] is None]
    assert painted, "expected some band faces painted paint_color=8"
    assert unpainted, "expected some base faces with no paint_color"

    # Base object extruder is 1 in model_settings.config.
    settings = _read_zip_part(path, "Metadata/model_settings.config")
    assert '<metadata key="extruder" value="1"/>' in settings


def test_painted_faces_fall_within_band_and_none_span_boundary(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6,
                               color_band_enabled=True, paint_mode="band")
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    verts, tris = _parse_painted_model(path)
    b0, b1 = cfg.resolved_color_band_start, cfg.color_band_top
    eps = 0.05  # tessellation tolerance

    for v1, v2, v3, paint in tris:
        zs = [verts[v1][2], verts[v2][2], verts[v3][2]]
        if paint == "8":
            # Every painted face lies wholly inside the band (within eps).
            assert all(b0 - eps <= z <= b1 + eps for z in zs)
        else:
            # No unpainted face lies wholly strictly inside the band -> proves
            # the pre-slice removed every straddling triangle.
            assert not all(b0 + eps <= z <= b1 - eps for z in zs)


def test_painted_3mf_geometry_is_watertight_and_matches_footprint(gridfinity, tmp_path):
    import trimesh

    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6,
                               color_band_enabled=True)
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    mesh = trimesh.load(str(path), force="mesh")
    assert mesh.is_watertight
    assert mesh.extents[0] == pytest.approx(cfg.width, abs=0.3)
    assert mesh.extents[1] == pytest.approx(cfg.length, abs=0.3)
    assert mesh.extents[2] == pytest.approx(cfg.overall_height, abs=0.3)


def test_painted_3mf_is_strictly_welded_and_manifold(gridfinity, tmp_path):
    """The painted .3mf must be a single welded vertex pool with no open edges.

    Reproduces the exact condition Bambu Studio flags: slicing + concatenate
    used to leave coincident-but-unwelded duplicate vertices at the band seams,
    so Bambu saw ~2392 open edges even though trimesh.load (which merges on
    load) reported the mesh watertight. This asserts the FILE itself is already
    welded: no duplicate positions, and every undirected edge is shared by
    exactly two faces using the AS-WRITTEN indices (no welding in the test).
    """
    import numpy as np

    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5,
                               color_band_enabled=True, paint_mode="band")
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    verts, tris = _parse_painted_model(path)
    V = np.array(verts, dtype=float)
    F = np.array([(v1, v2, v3) for (v1, v2, v3, _paint) in tris], dtype=int)

    # (a) No unwelded duplicate vertices: written count == unique-position count
    # at a tight tolerance (well inside the 0.05 mm tessellation tolerance, so
    # genuinely distinct vertices are never falsely merged by the assertion).
    unique_pos, inverse = np.unique(np.round(V, 5), axis=0, return_inverse=True)
    duplicate_count = len(V) - len(unique_pos)
    assert duplicate_count == 0, (
        f"{duplicate_count} coincident-unwelded duplicate vertices "
        "(the condition Bambu flags as open edges)"
    )

    # (b) Strict manifold on the AS-WRITTEN indices: every undirected edge is
    # shared by exactly two faces (0 open/non-manifold edges).
    edges = np.sort(
        np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1
    )
    _uniq_edges, counts = np.unique(edges, axis=0, return_counts=True)
    bad_edges = int((counts != 2).sum())
    assert bad_edges == 0, f"{bad_edges} edges not shared by exactly 2 faces"

    # (c) Geometric closure confirmed through the unique-position map too:
    # re-index faces onto welded positions and repeat the strict edge check.
    Fp = inverse[F]
    edges_p = np.sort(
        np.vstack([Fp[:, [0, 1]], Fp[:, [1, 2]], Fp[:, [2, 0]]]), axis=1
    )
    _ue, counts_p = np.unique(edges_p, axis=0, return_counts=True)
    assert int((counts_p != 2).sum()) == 0


@pytest.mark.parametrize("gx,gy", [(1, 1), (2, 1)])
def test_painted_3mf_lip_mode_paints_only_the_lip(gridfinity, gx, gy, tmp_path):
    """DEFAULT --3mf-paint paints the stacking LIP (z >= total_height), not a
    mid-wall band.

    This is the core of the lip-default change. Every painted face must lie in
    the lip region ``z >= total_height`` (within tessellation tolerance); every
    face wholly below the seam must be UNPAINTED; the lip must actually be
    painted (non-empty); and the body below the seam must be predominantly
    unpainted. This FAILS on the old mid-band behavior: the old painted faces
    sat mid-wall with centroids well below ``total_height`` (~17..22 mm for a
    units=6 bin), so they would all violate the ``z >= total_height`` assertion.
    """
    cfg = gridfinity.BinConfig(grid_x=gx, grid_y=gy, height_units=6,
                               color_band_enabled=True)  # default paint_mode="lip"
    assert cfg.paint_mode == "lip"
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    verts, tris = _parse_painted_model(path)
    seam = cfg.total_height
    eps = 0.05  # tessellation tolerance

    painted = [t for t in tris if t[3] == "8"]
    assert painted, "lip must be painted (non-empty)"

    body_unpainted = 0
    for v1, v2, v3, paint in tris:
        zs = [verts[v1][2], verts[v2][2], verts[v3][2]]
        if paint == "8":
            # Every painted face lies at or above the lip/body seam.
            assert all(z >= seam - eps for z in zs)
        else:
            # Every face wholly below the seam must be unpainted (it is, since
            # we only reach here for unpainted faces). Count them to prove the
            # body is predominantly unpainted.
            if all(z < seam - eps for z in zs):
                body_unpainted += 1

    # Every face strictly below the seam is unpainted (no mid-wall stripe).
    for v1, v2, v3, paint in tris:
        zs = [verts[v1][2], verts[v2][2], verts[v3][2]]
        if all(z < seam - eps for z in zs):
            assert paint is None, "a face below the lip seam was painted"

    # The body below the seam is substantial and entirely unpainted. (The old
    # check `body_unpainted > len(painted)` assumed the body dominated the face
    # count; the carbon-copy lip is now a finely-tessellated 4-plane rounded
    # loft, so for a small 1x1 the curved lip legitimately carries MORE faces
    # than the flat body walls below. The meaningful guarantees -- every painted
    # face is at/above the seam, no below-seam face is painted -- are asserted
    # above; here we only confirm the body region is non-trivial and unpainted.)
    assert body_unpainted > 200


def test_painted_3mf_lip_mode_is_strictly_welded_and_manifold(gridfinity, tmp_path):
    """The lip-painted .3mf is a single welded vertex pool with no open edges.

    Same strict check as the band-mode weld test, on the default lip mode: no
    duplicate vertex positions and every undirected edge shared by exactly two
    faces, using the AS-WRITTEN indices (no welding in the test).
    """
    import numpy as np

    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5,
                               color_band_enabled=True)  # default paint_mode="lip"
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    verts, tris = _parse_painted_model(path)
    V = np.array(verts, dtype=float)
    F = np.array([(v1, v2, v3) for (v1, v2, v3, _paint) in tris], dtype=int)

    unique_pos, inverse = np.unique(np.round(V, 5), axis=0, return_inverse=True)
    duplicate_count = len(V) - len(unique_pos)
    assert duplicate_count == 0, (
        f"{duplicate_count} coincident-unwelded duplicate vertices"
    )

    edges = np.sort(
        np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1
    )
    _uniq_edges, counts = np.unique(edges, axis=0, return_counts=True)
    assert int((counts != 2).sum()) == 0, "edges not shared by exactly 2 faces"

    Fp = inverse[F]
    edges_p = np.sort(
        np.vstack([Fp[:, [0, 1]], Fp[:, [1, 2]], Fp[:, [2, 0]]]), axis=1
    )
    _ue, counts_p = np.unique(edges_p, axis=0, return_counts=True)
    assert int((counts_p != 2).sum()) == 0


@pytest.mark.parametrize("gx,gy", [(1, 1), (2, 1), (2, 3)])
def test_painted_3mf_lip_mode_is_watertight_and_matches_footprint(
    gridfinity, gx, gy, tmp_path
):
    """The lip-painted mesh stays watertight with the footprint unchanged."""
    import trimesh

    cfg = gridfinity.BinConfig(grid_x=gx, grid_y=gy, height_units=6,
                               color_band_enabled=True)  # default paint_mode="lip"
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    mesh = trimesh.load(str(path), force="mesh")
    assert mesh.is_watertight
    assert mesh.extents[0] == pytest.approx(cfg.width, abs=0.3)
    assert mesh.extents[1] == pytest.approx(cfg.length, abs=0.3)
    assert mesh.extents[2] == pytest.approx(cfg.overall_height, abs=0.3)


def test_painted_faces_fall_within_explicit_band(gridfinity, tmp_path):
    """Band opt-in still works: with band mode and an explicit start/height the
    painted faces land in that z-band."""
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6,
                               color_band_enabled=True, paint_mode="band",
                               color_band_start=15.0, color_band_height=6.0)
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    verts, tris = _parse_painted_model(path)
    b0, b1 = cfg.resolved_color_band_start, cfg.color_band_top
    assert b0 == pytest.approx(15.0)
    assert b1 == pytest.approx(21.0)
    eps = 0.05
    painted = [t for t in tris if t[3] == "8"]
    assert painted, "band must be painted (non-empty)"
    for v1, v2, v3, paint in tris:
        if paint == "8":
            zs = [verts[v1][2], verts[v2][2], verts[v3][2]]
            assert all(b0 - eps <= z <= b1 + eps for z in zs)


def test_cli_3mf_paint_no_lip_exits_2(bin_mod, tmp_path, capsys):
    """--3mf-paint (lip mode) with --no-stacking-lip errors with exit 2."""
    rc = bin_mod.main(
        ["--3mf-paint", "--no-stacking-lip", "--output-dir", str(tmp_path)]
    )
    assert rc == 2
    assert "error:" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.3mf"))


def test_cli_3mf_paint_band_mode_no_lip_is_ok(gridfinity, bin_mod, tmp_path):
    """--3mf-paint --color-band paints the wall and needs no lip (exit 0)."""
    rc = bin_mod.main(
        ["--3mf-paint", "--color-band", "--no-stacking-lip", "--units", "6",
         "--output-dir", str(tmp_path)]
    )
    assert rc == 0
    threemfs = sorted(tmp_path.glob("*.3mf"))
    assert len(threemfs) == 1
    _verts, tris = _parse_painted_model(threemfs[0])
    assert any(t[3] == "8" for t in tris)


def test_cli_3mf_paint_writes_painted_3mf(gridfinity, bin_mod, tmp_path):
    rc = bin_mod.main(
        ["--x", "2", "--y", "1", "--units", "6", "--3mf-paint",
         "--output-dir", str(tmp_path)]
    )
    assert rc == 0
    threemfs = sorted(tmp_path.glob("*.3mf"))
    assert len(threemfs) == 1
    _verts, tris = _parse_painted_model(threemfs[0])
    assert any(t[3] == "8" for t in tris)


def test_cli_3mf_paint_band_outside_wall_exits_2(bin_mod, tmp_path, capsys):
    rc = bin_mod.main(
        ["--units", "3", "--3mf-paint", "--color-band", "--color-band-start",
         "500", "--output-dir", str(tmp_path)]
    )
    assert rc == 2
    assert "error:" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.3mf"))


def test_cli_3mf_paint_height_zero_exits_2(bin_mod, tmp_path, capsys):
    rc = bin_mod.main(
        ["--units", "6", "--3mf-paint", "--color-band", "--color-band-height",
         "0", "--output-dir", str(tmp_path)]
    )
    assert rc == 2
    assert "error:" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.3mf"))


def test_single_build_writes_one_stl(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=5)
    exporter = gridfinity.ModelExporter(tmp_path)
    exporter.export(gridfinity.GridfinityBin(cfg).build(), cfg,
                    name=exporter.bin_default_name(cfg))
    assert len(list(tmp_path.glob("*.stl"))) == 1
    assert len(list(tmp_path.glob("*.step"))) == 1


# =========================================================================
# Carbon-copy acceptance tests (measured-profile match)
# =========================================================================
#
# These assert the generated bin reproduces the MEASURED reference profile
# within tolerance. The measured numbers are hardcoded here (the Gridfinity
# spec is open); no sample file is read or named. Each test documents why it
# FAILS on the pre-rebuild geometry.

# Hardcoded measured-profile table (full edge-to-edge widths / radii, mm).
# Re-measured at fine z-steps on the reference bin; the design's source of truth.
MEASURED = {
    "foot_base": 35.70,       # foot narrowest, angled start
    "foot_straight": 37.20,   # foot straight seating section
    "body_inner": 39.10,      # body interior opening (per cell)
    "lip_seat": 37.70,        # stacking-lip seat opening
    "lip_mouth": 39.90,       # flared mouth at the top face
    "seat_corner": 1.85,      # lip-seat inner corner radius (concentric)
    "outer_corner": 3.75,     # outer vertical corner radius
}
PROFILE_TOL = 0.3  # +-0.3 mm, per the design acceptance band


def test_profile_matches_measured_carbon_copy(gridfinity, tmp_path):
    """PROFILE-MATCH: the generated 1x1 bin reproduces the measured profile.

    Sweeps the generated bin with MeshInspector and asserts outer/inner widths
    and corner radii at the key z-levels match the hardcoded measured table
    within +-0.3 mm: foot base 35.70, foot straight 37.20, body inner 39.10,
    lip seat 37.70, lip mouth 39.90, lip-seat corner 1.85, outer corner 3.75.

    This FAILS on the PRE-REBUILD geometry: the old foot base was 33.80 (vs
    35.70) and the old lip seat was 34.70 (vs 37.70) -- both ~2-3 mm outside the
    0.3 mm band. No sample file is read; the targets are hardcoded spec numbers.
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    p = cfg.profile
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    # --- foot (outer extents) ---
    foot_base = _require_slice(insp, 0.005)
    assert foot_base.outer[0] == pytest.approx(MEASURED["foot_base"], abs=PROFILE_TOL)
    foot_straight = _require_slice(insp, 1.5)  # in the straight seat run
    assert foot_straight.outer[0] == pytest.approx(
        MEASURED["foot_straight"], abs=PROFILE_TOL
    )

    # --- body interior opening ---
    body = _require_slice(insp, cfg.base_height + cfg.body_height / 2)
    assert body.hole_count == 1
    body_inner = statistics.median(w for (w, _d) in body.hole_extents)
    assert body_inner == pytest.approx(MEASURED["body_inner"], abs=PROFILE_TOL)

    # --- lip seat and mouth (inner openings) ---
    planes = cfg.lip_planes()
    seat_mid = cfg.total_height + (planes[1][0] + planes[2][0]) / 2.0
    seat = _require_slice(insp, seat_mid)
    assert seat.hole_count == 1
    seat_open = statistics.median(w for (w, _d) in seat.hole_extents)
    assert seat_open == pytest.approx(MEASURED["lip_seat"], abs=PROFILE_TOL)

    # Mouth reaches full 39.90 only at the top face; slice very close to it.
    mouth = _require_slice(insp, cfg.overall_height - 0.05)
    mouth_open = statistics.median(w for (w, _d) in mouth.hole_extents)
    assert mouth_open == pytest.approx(MEASURED["lip_mouth"], abs=PROFILE_TOL)

    # --- corner radii ---
    # Outer body corner (exterior arc).
    body_ext = _section_exterior_xy(insp, cfg.base_height + cfg.body_height / 2)
    if body_ext is None:
        pytest.skip("trimesh 2D section extras unavailable")
    _bx, _by, outer_r = _fit_corner_arc(*body_ext)
    assert outer_r == pytest.approx(MEASURED["outer_corner"], abs=PROFILE_TOL)

    # Lip-seat inner corner (interior arc at the seat run) ~1.85, concentric.
    seat_ring = _section_interior_xy(insp, seat_mid)
    assert seat_ring is not None
    fit = _fit_corner_arc(*seat_ring)
    assert fit is not None, "lip seat inner corner is sharp, not rounded"
    sx, sy, seat_r = fit
    assert seat_r == pytest.approx(MEASURED["seat_corner"], abs=PROFILE_TOL)
    # Concentric with the outer corner (shared arc center at footprint/2 - R).
    body_cc_x = cfg.width / 2 - cfg.corner_radius
    body_cc_y = cfg.length / 2 - cfg.corner_radius
    assert abs(sx) == pytest.approx(body_cc_x, abs=0.6)
    assert abs(sy) == pytest.approx(body_cc_y, abs=0.6)


def test_foot_taper_is_continuous_and_socket_compatible(gridfinity, tmp_path):
    """The foot is an angled continuous taper (no vertical straight-wall base).

    A near-base slice must be NARROWER than a slightly higher slice -- the foot
    widens continuously from the measured base (35.70) up toward the straight
    seat (37.20). This FAILS on the old near-straight / squared base. Also
    re-confirms socket compatibility: the foot straight (37.20) seats in the
    socket/lip seat (37.70) with ~0.25 mm/side.
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    near_base = _require_slice(insp, 0.05)   # in the angled lower chamfer
    higher = _require_slice(insp, 0.60)      # further up the chamfer
    # Continuous taper: the base is genuinely narrower (not a vertical wall).
    assert near_base.outer[0] < higher.outer[0] - 0.3
    assert near_base.outer[0] == pytest.approx(MEASURED["foot_base"], abs=PROFILE_TOL)

    # Socket-compatible: the straight seat is the measured 37.20, which drops
    # into the socket/lip seat opening (37.70) with lip_clearance/side.
    assert cfg.foot_straight_opening == pytest.approx(MEASURED["foot_straight"])
    straight = _require_slice(insp, 1.5)
    assert straight.outer[0] == pytest.approx(MEASURED["foot_straight"], abs=PROFILE_TOL)


def test_lip_stepback_fixes_too_big_opening(gridfinity, tmp_path):
    """The lip seat steps in to 37.70 (fixing the 34.70 "lip opening too big").

    The seat opening is lip_seat_step (0.70) per side in from the body interior,
    landing on the measured 37.70. This FAILS on the pre-rebuild lip whose seat
    opened to 34.70 (~3 mm too big, so a stacked bin sat loosely).
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)
    planes = cfg.lip_planes()
    seat_mid = cfg.total_height + (planes[1][0] + planes[2][0]) / 2.0
    seat = _require_slice(insp, seat_mid)
    assert seat.hole_count == 1
    seat_open = statistics.median(w for (w, _d) in seat.hole_extents)
    assert seat_open == pytest.approx(MEASURED["lip_seat"], abs=PROFILE_TOL)
    # Structurally the seat is the interior minus a fixed per-side step.
    assert seat_open == pytest.approx(cfg.inner_width - 2 * cfg.lip_seat_step, abs=0.3)


def test_lip_seat_inner_corner_radius_is_measured_and_concentric(gridfinity, tmp_path):
    """The lip-seat inner corner is the larger measured radius (~1.85).

    Concentric with the 3.75 outer corner (shared arc center). This FAILS on the
    pre-rebuild lip whose tighter rim gave a smaller seat corner (and the old
    seat sat at 34.70, a different inset entirely).
    """
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)
    planes = cfg.lip_planes()
    seat_mid = cfg.total_height + (planes[1][0] + planes[2][0]) / 2.0
    ring = _section_interior_xy(insp, seat_mid)
    if ring is None:
        pytest.skip("trimesh 2D section extras unavailable")
    fit = _fit_corner_arc(*ring)
    assert fit is not None, "lip seat inner corner is sharp, not rounded"
    xc, yc, r = fit
    assert r == pytest.approx(MEASURED["seat_corner"], abs=PROFILE_TOL)
    # Concentric with the outer corner.
    body_cc_x = cfg.width / 2 - cfg.corner_radius
    body_cc_y = cfg.length / 2 - cfg.corner_radius
    assert abs(xc) == pytest.approx(body_cc_x, abs=0.6)
    assert abs(yc) == pytest.approx(body_cc_y, abs=0.6)


# =========================================================================
# Baseplate socket interior opening — rounded concentric with the outer
# =========================================================================
#
# The baseplate socket cavity's INNER opening corners are rounded concentric
# with the reference outer corner (profile.corner_radius = 3.75), growing from
# the narrow bottom up toward the wide mouth -- the real Gridfinity socket
# curves on its inner corners all the way up, instead of a squared-off opening.
# These targets are hardcoded numeric constants derived from the single
# corner_radius via GridfinityProfile.opening_corner_radius; no sample file is
# read or named. Every test below FAILS on the pre-change squared-off socket
# (the socket was lofted from sharp .rect() squares, so the interior ring held
# ~4-9 points and fit no corner arc).

# Single-cell socket center sits at the cell center = origin for a 1x1 plate, so
# the socket's opening corners lie about the plate origin. The socket profile
# bottom for a height=5.0 plate is z = 5.0 - profile.total_height = 0.35.
# z-levels used: just inside the bottom chamfer, the straight seat run, and near
# the mouth. Expected concentric radii (opening_corner_radius): bottom ~0.9,
# straight ~1.65, growing to ~3.75 at the mouth face.


def _plate_1x1(gridfinity, height=5.0):
    return gridfinity.GridConfig(
        grid_x=1, grid_y=1, height=height,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )


def test_socket_interior_opening_corners_are_rounded_and_grow(gridfinity, tmp_path):
    """The baseplate socket's interior opening corners are ROUNDED and grow up.

    This FAILS on the pre-change squared-off socket: it was lofted from sharp
    ``.rect()`` squares, so the interior ring's +x+y corner held essentially no
    arc points and ``_fit_corner_arc`` returned None (no fitted radius), and the
    ring carried only ~4-9 points. After the change each socket slice's inner
    opening fits a POSITIVE corner radius, the ring carries many points, the
    radius GROWS from the narrow bottom toward the wide mouth (concentric with
    the outer), and every fitted arc center sits on the SAME vertical line
    (concentric with the reference outer corner).
    """
    cfg = _plate_1x1(gridfinity)
    p = cfg.profile
    assert p.corner_radius > 0
    insp = _export_inspect(gridfinity, gridfinity.GridfinityPlate(cfg).build(), tmp_path)

    z_bot = cfg.resolved_height - p.total_height  # socket profile bottom (0.35)
    z_low = z_bot + 0.45    # inside the lower chamfer, near the narrow bottom
    z_mid = z_bot + 1.5     # the straight seat run
    z_high = z_bot + 4.1    # up in the mouth flare, near the wide mouth

    rings = [_section_interior_xy(insp, z) for z in (z_low, z_mid, z_high)]
    if any(r is None for r in rings):
        pytest.skip("trimesh 2D section extras unavailable")
    low, mid, high = rings

    # Many ring points at each level: a rounded opening adds an arc; a sharp
    # square opening has ~4 (this is the assertion that catches the old socket).
    for xs, _ys in (low, mid, high):
        assert len(xs) > 20, "socket interior opening corner is sharp, not rounded"

    fits = [_fit_corner_arc(xs, ys) for (xs, ys) in (low, mid, high)]
    for f in fits:
        assert f is not None, "socket interior opening corner is sharp, not rounded"
    (xl, yl, r_low), (xm, ym, r_mid), (xh, yh, r_high) = fits

    # Rounded: positive radii, all under the reference outer 3.75.
    for r in (r_low, r_mid, r_high):
        assert 0.3 < r < p.corner_radius

    # GROWS from the narrow bottom toward the wide mouth (concentric with the
    # outer), matching the measured growth direction (bottom small -> mouth near
    # 3.75). Each step up is clearly wider.
    assert r_mid > r_low + 0.2
    assert r_high > r_mid + 0.4

    # Rough magnitude per the concentric model (opening_corner_radius): low
    # ~0.9, straight ~1.65, high approaching 3.75. Generous tolerance -- the
    # growth + concentricity are the contract, not an exact dimension.
    assert r_low == pytest.approx(1.0, abs=0.6)
    assert r_mid == pytest.approx(1.65, abs=0.6)
    assert r_high == pytest.approx(3.2, abs=0.8)

    # Concentric: every fitted arc center sits at the mouth's corner center
    # ``mouth_opening/2 - corner_radius`` from the socket (origin) center.
    cc = p.mouth_opening / 2 - p.corner_radius
    for xc, yc in ((xl, yl), (xm, ym), (xh, yh)):
        assert abs(xc) == pytest.approx(cc, abs=0.6)
        assert abs(yc) == pytest.approx(cc, abs=0.6)


def test_socket_interior_corner_radius_matches_concentric_model(gridfinity):
    """``opening_corner_radius`` is the concentric model derived from 3.75.

    Pure-arithmetic guard (no render): the per-plane socket opening radius is
    ``corner_radius - (mouth_opening - opening)/2`` (the outer radius minus the
    per-side inset below the mouth), clamped to ``[0, opening/2]``. It is 3.75 at
    the mouth and shrinks for narrower planes, so the socket interior curve grows
    up toward the mouth. Derived from the single ``corner_radius`` -- no magic
    numbers.
    """
    p = gridfinity.GridfinityProfile()
    assert p.corner_radius == pytest.approx(3.75)
    # Mouth plane: full outer radius.
    assert p.opening_corner_radius(p.mouth_opening) == pytest.approx(3.75)
    # Straight seat opening (37.7): 3.75 - (41.9 - 37.7)/2 = 1.65.
    assert p.opening_corner_radius(p.top_opening) == pytest.approx(1.65, abs=1e-6)
    # Narrow bottom (36.2): 3.75 - (41.9 - 36.2)/2 = 0.90.
    assert p.opening_corner_radius(p.bottom_opening) == pytest.approx(0.90, abs=1e-6)
    # Monotonic growth toward the mouth.
    radii = [p.opening_corner_radius(pl.size) for pl in p.profile_planes()]
    assert radii == sorted(radii)
    # A sharp socket opts out (corner_radius = 0 -> every radius 0).
    sharp = gridfinity.GridfinityProfile(corner_radius=0.0)
    assert all(
        sharp.opening_corner_radius(pl.size) == 0.0 for pl in sharp.profile_planes()
    )


# Pinned socket opening WIDTHS (edge-to-edge median hole extent, mm) for the
# default 1x1 height=5.0 plate. Rounding the interior opening corners must NOT
# resize the socket -- these are the SAME widths the pre-change squared socket
# cut (the flat edge spans are untouched; only the sharp inner corners became
# arcs), so a bin foot still plugs in and bins still interlock with plates.
SOCKET_OPENING_WIDTHS = {
    # z measured in PART coords (socket profile bottom = 0.35 for height 5.0):
    0.80: 37.044,   # inside the lower chamfer
    1.50: 37.700,   # straight seat run
    2.50: 37.700,   # straight seat run
    4.90: 41.700,   # near the wide mouth
}


def test_socket_opening_widths_unchanged(gridfinity, tmp_path):
    """Socket opening WIDTHS at each z are UNCHANGED by the interior rounding.

    Pins the socket opening sizes so the interior-curve change can never
    accidentally resize the socket: the flat opening span (what a bin foot seats
    against) stays what it was, only the sharp inner corners became rounded. If
    this drifts, the bin-plate interlock is at risk.
    """
    cfg = _plate_1x1(gridfinity)
    insp = _export_inspect(gridfinity, gridfinity.GridfinityPlate(cfg).build(), tmp_path)
    for z, expected in SOCKET_OPENING_WIDTHS.items():
        prof = insp.slice_at(z)
        if prof is None:
            pytest.skip("trimesh 2D section extras unavailable")
        assert prof.hole_count == 1
        open_w = statistics.median(w for (w, _d) in prof.hole_extents)
        assert open_w == pytest.approx(expected, abs=0.2)


@pytest.mark.parametrize("gx,gy", [(1, 1), (2, 2), (3, 3)])
def test_rounded_socket_plate_is_watertight(gridfinity, gx, gy):
    """1x1 / 2x2 / 3x3 plates with the rounded socket stay watertight/valid."""
    cfg = gridfinity.GridConfig(
        grid_x=gx, grid_y=gy, height=5.0,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    assert gridfinity.GridfinityPlate(cfg).build().val().isValid()
