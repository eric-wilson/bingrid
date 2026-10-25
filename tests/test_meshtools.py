"""Tests for the reusable mesh inspection tool.

Uses the bundled BGG reference sample when present; otherwise builds a tiny
mesh in-memory so the core measurements are still exercised.
"""
from importlib import import_module
from pathlib import Path

import pytest

SAMPLE = (
    Path(__file__).resolve().parents[1] / "samples" / "BGG V1.0.0 standard.stl.stl"
)


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


@pytest.mark.skipif(not SAMPLE.exists(), reason="BGG sample not present")
def test_bgg_reference_summary(meshtools):
    insp = meshtools.MeshInspector.load(SAMPLE)
    # Known reference: 3x3 baseplate, 126 x 126 x 5 mm.
    assert insp.extents[0] == pytest.approx(126.0, abs=0.1)
    assert insp.extents[1] == pytest.approx(126.0, abs=0.1)
    assert insp.extents[2] == pytest.approx(5.0, abs=0.05)
    # Nine cells -> nine holes through the body.
    prof = insp.slice_at(2.0, axis="z")
    assert prof.hole_count == 9
