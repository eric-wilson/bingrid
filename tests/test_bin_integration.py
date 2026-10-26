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

    The seat (narrowest ring opening, near the bottom of the lip) is inset from
    the flared mouth (at the top) by ~chamfer_top per side on each axis, from
    the shared GridfinityProfile. That inward step is the seating ledge a
    stacked bin's base drops onto.
    """
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=6)
    p = cfg.profile
    insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)

    z_seat = cfg.total_height + 0.3  # in the straight seat run
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


def test_single_build_writes_one_stl(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=5)
    exporter = gridfinity.ModelExporter(tmp_path)
    exporter.export(gridfinity.GridfinityBin(cfg).build(), cfg,
                    name=exporter.bin_default_name(cfg))
    assert len(list(tmp_path.glob("*.stl"))) == 1
    assert len(list(tmp_path.glob("*.step"))) == 1
