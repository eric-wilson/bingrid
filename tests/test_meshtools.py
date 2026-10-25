"""Tests for the reusable mesh inspection tool.

All fixtures are built in-memory with trimesh, so the tests own no third-party
asset and run anywhere.
"""
from importlib import import_module

import pytest


@pytest.fixture(scope="module")
def meshtools():
    return import_module("bingrid.meshtools")


def test_inspector_box_extents_and_volume(meshtools):
    import trimesh

    box = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
    insp = meshtools.MeshInspector(box)
    assert insp.extents == pytest.approx((10.0, 20.0, 5.0))
    assert insp.volume == pytest.approx(1000.0)
    assert insp.is_watertight is True


def test_inspector_normalizes_to_origin(meshtools):
    import trimesh

    box = trimesh.creation.box(extents=(4.0, 4.0, 4.0))
    box.apply_translation([100.0, 100.0, 100.0])
    insp = meshtools.MeshInspector(box)  # normalize=True by default
    lo, hi = insp.bounds
    assert lo[2] == pytest.approx(0.0)          # base dropped to z=0
    assert lo[0] == pytest.approx(-2.0)         # centered in X
    assert hi[0] == pytest.approx(2.0)


def test_slice_reports_hole(meshtools):
    import trimesh

    # A plate with a hole: slicing mid-height should report one interior hole.
    outer = trimesh.creation.box(extents=(20.0, 20.0, 4.0))
    hole = trimesh.creation.box(extents=(6.0, 6.0, 10.0))
    plate = outer.difference(hole)
    insp = meshtools.MeshInspector(plate)
    prof = insp.slice_at(2.0, axis="z")
    assert prof is not None
    assert prof.hole_count == 1
    assert prof.hole_extents[0] == pytest.approx((6.0, 6.0), abs=1e-6)


def test_profile_sweep_covers_height(meshtools):
    import trimesh

    box = trimesh.creation.box(extents=(10.0, 10.0, 6.0))
    insp = meshtools.MeshInspector(box)
    slices = insp.profile(axis="z", step=1.0)
    assert len(slices) >= 2
    # Positions run from the base upward, strictly increasing.
    positions = [s.position for s in slices]
    assert positions == sorted(positions)
    assert positions[0] >= 0.0
    assert positions[-1] <= 6.0
