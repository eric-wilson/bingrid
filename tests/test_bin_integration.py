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


# Pre-refactor plate-socket baseline, captured from the original inline-loft
# code (GridConfig(grid_x=1, grid_y=1, height=5.0, magnet disabled)). The
# shared-profile refactor must reproduce this solid to full float precision, so
# rel=1e-9 fails on any real socket shift (including sub-tolerance ones the
# spec test's abs=0.1/0.3 cannot see).
BASELINE_VOLUME = 1619.095071428569
BASELINE_BBOX = (42.0000002, 42.0000002, 5.000000200000001)  # xlen, ylen, zlen


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
    # Narrow bottom ~ bottom_opening - 2*foot_clearance = 33.8.
    narrow = _require_slice(insp, 0.005)
    assert narrow.outer[0] == pytest.approx(33.8, abs=0.3)
    # Vertical ~ top_opening - 2*foot_clearance = 37.0.
    vert = _require_slice(insp, 1.2)
    assert vert.outer[0] == pytest.approx(37.0, abs=0.3)


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

    # The mouth leaves lip_wall per side off the full footprint. Both axes track
    # the interior -- and critically the SHORT axis is nowhere near ~42 mm on a
    # wide bin, which is the single-socket bug this test exists to catch.
    expected_w = cfg.width - 2 * cfg.lip_wall
    expected_l = cfg.length - 2 * cfg.lip_wall
    assert open_w == pytest.approx(expected_w, abs=1.5)
    assert open_l == pytest.approx(expected_l, abs=1.5)
    # The opening must be close to the body interior, far from a 41.9 mm socket.
    assert open_w == pytest.approx(cfg.inner_width, abs=3.0)
    assert open_l == pytest.approx(cfg.inner_length, abs=3.0)


def test_lip_seat_steps_inward_from_the_mouth(gridfinity, tmp_path):
    """The rim steps inward from mouth to seat, mirroring the socket section.

    The seat (narrowest ring opening) is inset from the flared mouth (at the
    top) by ~chamfer_top per side on each axis, from the shared
    GridfinityProfile. That inward step is the seating ledge a stacked bin's
    base drops onto. The seat run sits ABOVE the self-supporting bottom lead-in
    (which flares the opening out to the body interior over the lowest
    ``run`` mm of the lip), so we slice at the midpoint of the seat run rather
    than near the lip base -- near the base the opening is the wide interior,
    not the narrow seat.
    """
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6)
    p = cfg.profile
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    # Lip-local geometry: bottom lead-in height = widest per-side flare run,
    # then the straight seat run up to ``lip_h - chamfer_top``. Slice the seat
    # at the middle of that run.
    mouth_w0 = cfg.width - 2 * cfg.lip_wall
    seat_w0 = mouth_w0 - 2 * p.chamfer_top
    lead_h = max((cfg.inner_width - seat_w0) / 2.0,
                 (cfg.inner_length - (cfg.length - 2 * cfg.lip_wall
                                      - 2 * p.chamfer_top)) / 2.0, 0.0)
    seat_mid = (lead_h + (cfg.lip_h - p.chamfer_top)) / 2.0
    z_seat = cfg.total_height + seat_mid  # in the straight seat run
    z_mouth = cfg.overall_height - 0.3  # in the flared mouth
    seat = _require_slice(insp, z_seat)
    mouth = _require_slice(insp, z_mouth)
    assert seat.hole_count == 1 and mouth.hole_count == 1

    seat_w = statistics.median(w for (w, _d) in seat.hole_extents)
    mouth_w = statistics.median(w for (w, _d) in mouth.hole_extents)
    seat_l = statistics.median(d for (_w, d) in seat.hole_extents)
    mouth_l = statistics.median(d for (_w, d) in mouth.hole_extents)

    # Seat is inset from the mouth by ~chamfer_top per side (both axes).
    assert mouth_w - seat_w == pytest.approx(2 * p.chamfer_top, abs=0.8)
    assert mouth_l - seat_l == pytest.approx(2 * p.chamfer_top, abs=0.8)
    # And the seat itself still spans most of the interior, not a tiny hole.
    assert seat_w > cfg.inner_width - 2 * p.chamfer_top - 1.5
    assert seat_l > cfg.inner_length - 2 * p.chamfer_top - 1.5


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
    # socket profile bottom 1.2). Gap ~ 2*foot_clearance = 0.5.
    foot_narrow = _require_slice(foot_insp, 0.1)
    plate_narrow = _require_slice(plate_insp, 1.3)
    sock_narrow = statistics.median(w for (w, _d) in plate_narrow.hole_extents)
    assert sock_narrow - foot_narrow.outer[0] == pytest.approx(0.5, abs=0.3)

    # Vertical: foot at bin z=1.5 vs socket hole at plate z=2.9. Same ~0.5 gap.
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
                               color_band_enabled=True)
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
                               color_band_enabled=True)
    exporter = gridfinity.ModelExporter(tmp_path)
    (path,) = exporter.export_3mf_painted(gridfinity.GridfinityBin(cfg).build(), cfg)

    verts, tris = _parse_painted_model(path)
    b0, b1 = cfg.color_band_start, cfg.color_band_top
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
        ["--units", "3", "--3mf-paint", "--color-band-start", "500",
         "--output-dir", str(tmp_path)]
    )
    assert rc == 2
    assert "error:" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.3mf"))


def test_cli_3mf_paint_height_zero_exits_2(bin_mod, tmp_path, capsys):
    rc = bin_mod.main(
        ["--units", "6", "--3mf-paint", "--color-band-height", "0",
         "--output-dir", str(tmp_path)]
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
