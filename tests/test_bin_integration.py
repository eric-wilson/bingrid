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


def test_floor_above_base_height_branch(gridfinity):
    # base_height < floor < total_height: cavity_bottom tracks floor.
    cfg = gridfinity.BinConfig(height_units=6, floor=6.0)
    assert cfg.cavity_bottom == pytest.approx(6.0)
    assert gridfinity.GridfinityBin(cfg).build().val().isValid()


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


# --- #12: stacking lip mirrors the socket, via the bin's own foot ----------

def test_lip_mirrors_socket_via_own_foot(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=5)
    p = cfg.profile
    bin_insp = _export_inspect(gridfinity, gridfinity.GridfinityBin(cfg).build(), tmp_path)
    # (a) The lip seating cut ~ top_opening = 37.5 (one interior hole). Sample
    # near the bottom of the vertical seat (just above the mouth chamfer); the
    # loft pinches ~0.2 at the exact mid-seat, so the seat edge is the faithful
    # reading of the 37.5 vertical.
    z_seat = cfg.total_height + p.chamfer_top + 0.1
    seat = _require_slice(bin_insp, z_seat)
    assert seat.hole_count == 1
    lip_cut = statistics.median(w for (w, _d) in seat.hole_extents)
    assert lip_cut == pytest.approx(p.top_opening, abs=0.3)   # 37.5
    # (b) The bin's own foot vertical ~ 37.0, so the lip cut clears it by ~0.5.
    # Build a foot-only solid (single cell, centered at origin) and measure it.
    foot_only = gridfinity.GridfinityBin(cfg, features=[gridfinity.BinFootFeature()])
    foot_insp = _export_inspect(gridfinity, foot_only.build(), tmp_path)
    foot_vert = _require_slice(foot_insp, 1.2)
    assert foot_vert.outer[0] == pytest.approx(37.0, abs=0.2)
    assert lip_cut - foot_vert.outer[0] == pytest.approx(0.5, abs=0.2)


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


def test_single_build_writes_one_stl(gridfinity, tmp_path):
    cfg = gridfinity.BinConfig(grid_x=2, grid_y=1, height_units=5)
    exporter = gridfinity.ModelExporter(tmp_path)
    exporter.export(gridfinity.GridfinityBin(cfg).build(), cfg,
                    name=exporter.bin_default_name(cfg))
    assert len(list(tmp_path.glob("*.stl"))) == 1
    assert len(list(tmp_path.glob("*.step"))) == 1
