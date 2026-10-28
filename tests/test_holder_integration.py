"""Integration tests for the pocket-holder generator (build real solids).

Marked ``integration`` (excluded by the default ``-m 'not integration'``
selection) because rendering is slow. Run explicitly with::

    pytest -m integration

Every test measures OUR OWN generated meshes against values computed from the
:class:`HolderConfig` layout properties -- NEVER a file under ``samples/``
(gitignored, license-restricted). The slice-based assertions reuse the
``_require_slice`` / ``hole_extents`` / ``statistics.median`` pattern from
``tests/test_bin_integration.py`` and skip cleanly when trimesh's optional 2D
section extras are unavailable (solid-validity checks stand in).
"""
import statistics
import tempfile
from pathlib import Path

import cadquery as cq
import pytest

pytestmark = pytest.mark.integration

# Baseline plain-bin lip-seat opening (1x1 default, from the bin tests): the
# holder must not disturb the lip, so its lip seat stays the measured 37.70.
BASELINE_LIP_SEAT = 37.70


def _require_slice(insp, z):
    prof = insp.slice_at(z)
    if prof is None:
        pytest.skip("trimesh 2D section extras unavailable")
    return prof


def _export_inspect(gridfinity, model, tmpdir, fname="m.stl"):
    from bingrid.meshtools import MeshInspector

    path = Path(tmpdir) / fname
    cq.exporters.export(model, str(path))
    return MeshInspector.load(path)


def _holder(gridfinity, holder_cfg):
    """Build a holder solid via the PocketGridFeature pipeline.

    Same feature injection the generator's ``build_and_export`` uses: the bin
    pipeline with a SOLID interior (no plain HollowInteriorFeature) into which
    ``PocketGridFeature`` cuts the pocket array.
    """
    g = gridfinity
    return g.GridfinityBin(
        holder_cfg.bin,
        features=[
            g.BinBodyFeature(),
            g.BinFootFeature(),
            g.PocketGridFeature(holder_cfg),
            g.StackingLipFeature(),
        ],
    )


def _rect_holder(gridfinity, **over):
    b = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=6)
    defaults = dict(pocket_shape="rect", item_w=26.5, item_d=17.5, fit="normal")
    defaults.update(over)
    return gridfinity.HolderConfig(bin=b, **defaults)


def _round_holder(gridfinity, **over):
    b = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=6)
    defaults = dict(pocket_shape="round", item_dia=14.5, fit="snug")
    defaults.update(over)
    return gridfinity.HolderConfig(bin=b, **defaults)


# --- valid solids ----------------------------------------------------------

def test_rect_holder_is_watertight(gridfinity):
    cfg = _rect_holder(gridfinity)
    assert cfg.pocket_count >= 1
    assert _holder(gridfinity, cfg).build().val().isValid()


def test_round_holder_is_watertight(gridfinity):
    cfg = _round_holder(gridfinity)
    assert cfg.pocket_count >= 1
    assert _holder(gridfinity, cfg).build().val().isValid()


def test_open_bottom_holder_is_watertight(gridfinity):
    # floor=0 exercises the cavity-bottom clamp under the pocket cuts.
    b = gridfinity.BinConfig(grid_x=1, grid_y=1, height_units=6, floor=0.0)
    cfg = gridfinity.HolderConfig(bin=b, pocket_shape="rect",
                                  item_w=20.0, item_d=15.0)
    assert _holder(gridfinity, cfg).build().val().isValid()


# --- pocket count matches the computed grid --------------------------------

@pytest.mark.parametrize("builder", ["rect", "round"])
def test_pocket_count_in_mesh_matches_computed(gridfinity, tmp_path, builder):
    cfg = _rect_holder(gridfinity) if builder == "rect" else _round_holder(gridfinity)
    insp = _export_inspect(gridfinity, _holder(gridfinity, cfg).build(), tmp_path)

    # Slice just above the pocket floor so every pocket reads as an interior
    # void; count the holes.
    floor_z = max(cfg.total_height - cfg.resolved_pocket_depth, cfg.cavity_bottom)
    prof = insp.slice_at(floor_z + 1.0)
    if prof is None:
        pytest.skip("trimesh 2D section extras unavailable")
    assert prof.hole_count == cfg.pocket_count


# --- pocket inner size ~ item + 2*clearance --------------------------------

def test_rect_pocket_inner_size(gridfinity, tmp_path):
    cfg = _rect_holder(gridfinity)
    insp = _export_inspect(gridfinity, _holder(gridfinity, cfg).build(), tmp_path)
    floor_z = max(cfg.total_height - cfg.resolved_pocket_depth, cfg.cavity_bottom)
    prof = insp.slice_at(floor_z + 2.0)
    if prof is None:
        pytest.skip("trimesh 2D section extras unavailable")
    assert prof.hole_count == cfg.pocket_count
    w = statistics.median(w for (w, _d) in prof.hole_extents)
    d = statistics.median(d for (_w, d) in prof.hole_extents)
    assert w == pytest.approx(cfg.pocket_w, abs=0.3)
    assert d == pytest.approx(cfg.pocket_d, abs=0.3)


def test_round_pocket_inner_size(gridfinity, tmp_path):
    cfg = _round_holder(gridfinity)
    insp = _export_inspect(gridfinity, _holder(gridfinity, cfg).build(), tmp_path)
    floor_z = max(cfg.total_height - cfg.resolved_pocket_depth, cfg.cavity_bottom)
    prof = insp.slice_at(floor_z + 2.0)
    if prof is None:
        pytest.skip("trimesh 2D section extras unavailable")
    assert prof.hole_count == cfg.pocket_count
    w = statistics.median(w for (w, _d) in prof.hole_extents)
    d = statistics.median(d for (_w, d) in prof.hole_extents)
    assert w == pytest.approx(cfg.pocket_dia, abs=0.3)
    assert d == pytest.approx(cfg.pocket_dia, abs=0.3)


# --- pocket floor at/above cavity_bottom (floor never breached) ------------

def test_pocket_floor_at_or_above_cavity_bottom(gridfinity, tmp_path):
    cfg = _rect_holder(gridfinity)
    insp = _export_inspect(gridfinity, _holder(gridfinity, cfg).build(), tmp_path)
    floor_z = max(cfg.total_height - cfg.resolved_pocket_depth, cfg.cavity_bottom)
    assert floor_z >= cfg.cavity_bottom - 1e-9

    # Below the floor slab (inside base_height..cavity_bottom) there is no
    # pocket void: the floor/foot region is solid. Slice just below the pocket
    # floor and assert no interior hole there.
    probe = cfg.cavity_bottom - 0.3
    if probe <= 0.3:
        pytest.skip("floor region too thin to slice distinctly")
    prof = insp.slice_at(probe)
    if prof is None:
        pytest.skip("trimesh 2D section extras unavailable")
    assert prof.hole_count == 0


# --- bounding box unchanged (pockets only remove interior material) --------

def test_bounding_box_unchanged(gridfinity, tmp_path):
    cfg = _rect_holder(gridfinity)
    insp = _export_inspect(gridfinity, _holder(gridfinity, cfg).build(), tmp_path)
    assert insp.extents[0] == pytest.approx(cfg.width, abs=0.1)
    assert insp.extents[1] == pytest.approx(cfg.length, abs=0.1)
    assert insp.extents[2] == pytest.approx(cfg.bin.overall_height, abs=0.1)
    # width/length are still N*pitch - 0.5.
    assert cfg.width == pytest.approx(cfg.bin.grid_x * cfg.bin.pitch - 0.5)
    assert cfg.length == pytest.approx(cfg.bin.grid_y * cfg.bin.pitch - 0.5)


# --- still seats / unions into a plate --------------------------------------

def test_holder_unions_into_2x2_plate(gridfinity):
    plate_cfg = gridfinity.GridConfig(
        grid_x=2, grid_y=2, height=6.0, floor=1.0,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    b = gridfinity.BinConfig(grid_x=2, grid_y=2)
    holder_cfg = gridfinity.HolderConfig(
        bin=b, pocket_shape="rect", item_w=26.5, item_d=17.5,
    )
    plate = gridfinity.GridfinityPlate(plate_cfg).build()
    holder = _holder(gridfinity, holder_cfg).build()
    assert plate.union(holder).val().isValid()


# --- lip profile unchanged with a lip --------------------------------------

def test_lip_profile_unchanged_by_pockets(gridfinity, tmp_path):
    """A lipped holder's lip seat is still the measured 37.70 (pockets only cut
    the interior, never the additive lip above total_height)."""
    cfg = _rect_holder(gridfinity)
    assert cfg.bin.stacking_lip
    insp = _export_inspect(gridfinity, _holder(gridfinity, cfg).build(), tmp_path)

    planes = cfg.bin.lip_planes()
    seat_mid = cfg.bin.total_height + (planes[1][0] + planes[2][0]) / 2.0
    seat = insp.slice_at(seat_mid)
    if seat is None:
        pytest.skip("trimesh 2D section extras unavailable")
    assert seat.hole_count == 1
    seat_l = statistics.median(d for (_w, d) in seat.hole_extents)
    assert seat_l == pytest.approx(BASELINE_LIP_SEAT, abs=0.3)


# --- CLI end-to-end (writes files) -----------------------------------------

def test_cli_holder_fill_bin_writes_files(gridfinity, app_mod, tmp_path):
    rc = app_mod.main(
        ["holder", "--x", "1", "--y", "1", "--pocket-shape", "rect",
         "--item-w", "26.5", "--item-d", "17.5", "--item-height", "48",
         "--proud", "10", "--fit", "normal", "--output-dir", str(tmp_path)]
    )
    assert rc == 0
    assert list(tmp_path.glob("*.stl"))
    assert list(tmp_path.glob("*.step"))


def test_cli_holder_round_writes_files(gridfinity, app_mod, tmp_path):
    rc = app_mod.main(
        ["holder", "--x", "1", "--y", "1", "--pocket-shape", "round",
         "--item-dia", "14.5", "--item-height", "50", "--proud", "12",
         "--fit", "snug", "--output-dir", str(tmp_path)]
    )
    assert rc == 0
    assert list(tmp_path.glob("*.stl"))
