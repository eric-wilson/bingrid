"""Integration tests that build real CadQuery solids and export files.

Marked ``integration`` (and so excluded by the default ``-m 'not integration'``
selection) because rendering is comparatively slow. Run them explicitly with::

    pytest -m integration
"""
import pytest

pytestmark = pytest.mark.integration


def _build(gridfinity, **overrides):
    cfg = gridfinity.GridConfig(**overrides)
    return cfg, gridfinity.GridfinityPlate(cfg).build()


def test_basic_socket_plate_is_watertight(gridfinity):
    # Default style is socket, open floor.
    _cfg, model = _build(gridfinity, grid_x=2, grid_y=2)
    assert model.val().isValid()


def test_socket_plate_with_floor_is_watertight(gridfinity):
    cfg, model = _build(
        gridfinity,
        grid_x=2,
        grid_y=2,
        floor=1.0,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    assert model.val().isValid()
    # A floored plate holds more material than the same open one.
    open_cfg = gridfinity.GridConfig(
        grid_x=2, grid_y=2, height=cfg.resolved_height,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    open_vol = gridfinity.GridfinityPlate(open_cfg).build().val().Volume()
    assert model.val().Volume() > open_vol


def test_tapered_plate_is_watertight(gridfinity):
    _cfg, model = _build(
        gridfinity,
        grid_x=2,
        grid_y=2,
        opening_style="taper",
        taper=gridfinity.TaperConfig(angle_deg=3.0),
    )
    assert model.val().isValid()


def test_no_magnet_plate_builds(gridfinity):
    cfg, model = _build(
        gridfinity,
        grid_x=1,
        grid_y=1,
        height=8.0,
        opening_style="taper",
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    assert model.val().isValid()


# Published Gridfinity baseplate socket dimensions (facts, not a third-party
# file). A 3x3 plate is 126 x 126 mm at 42 mm pitch; the cell socket opening is
# ~37.5 mm along the vertical, widening to the mouth and narrowing to the foot.
# We verify our generated mesh against these numbers so the test owns no
# third-party asset and stays self-contained.
_GF_PITCH = 42.0
_GF_CELLS = 3
_GF_FOOTPRINT = _GF_PITCH * _GF_CELLS          # 126.0 mm
_GF_VERTICAL_OPENING = 37.5                    # inner opening along the vertical


def test_socket_profile_matches_gridfinity_spec(gridfinity):
    """A 3x3 socket plate reproduces the published Gridfinity baseplate socket.

    Measured against the spec dimensions, not against any third-party file, so
    the test is self-contained and carries no licensing baggage.
    """
    import statistics
    import tempfile
    from importlib import import_module
    from pathlib import Path

    import cadquery as cq

    mt = import_module("bingrid.meshtools")
    cfg = gridfinity.GridConfig(
        grid_x=_GF_CELLS, grid_y=_GF_CELLS, height=5.0, pitch=_GF_PITCH,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    model = gridfinity.GridfinityPlate(cfg).build()

    with tempfile.TemporaryDirectory() as d:
        ours_path = Path(d) / "ours.stl"
        cq.exporters.export(model, str(ours_path))
        ours = mt.MeshInspector.load(ours_path)

        # Footprint and height match the spec (tile compatibility).
        assert ours.extents[0] == pytest.approx(_GF_FOOTPRINT, abs=0.1)
        assert ours.extents[1] == pytest.approx(_GF_FOOTPRINT, abs=0.1)
        assert ours.extents[2] == pytest.approx(5.0, abs=0.05)

        def med_open(z):
            p = ours.slice_at(z)
            return statistics.median(w for (w, _l) in p.hole_extents)

        # Nine cells punch through the body.
        assert ours.slice_at(2.5).hole_count == _GF_CELLS * _GF_CELLS

        # The vertical section seats the bin foot at the spec opening; the
        # mouth is wider (lead-in) and the foot narrower.
        vertical = med_open(2.0)
        mouth = med_open(4.9)
        foot = med_open(0.1)
        assert vertical == pytest.approx(_GF_VERTICAL_OPENING, abs=0.3)
        assert mouth > vertical > foot


@pytest.mark.skip(
    reason="Local-only: compares against a third-party reference file "
    "(Standard Digital File License) that must not be committed. Drop the "
    "file in and remove this skip to run it on your own machine."
)
def test_socket_profile_matches_local_reference(gridfinity):
    """Optional local check against a reference STL you supply yourself.

    The reference is NOT distributed with this repo because of its license.
    Place a file at the path below and remove the ``skip`` marker to compare.
    """
    import statistics
    import tempfile
    from importlib import import_module
    from pathlib import Path

    import cadquery as cq

    reference = Path.home() / "gridfinity-references" / "baseplate_3x3.stl"
    if not reference.exists():
        pytest.skip(f"reference file not found: {reference}")

    mt = import_module("bingrid.meshtools")
    cfg = gridfinity.GridConfig(
        grid_x=3, grid_y=3, height=5.0,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    model = gridfinity.GridfinityPlate(cfg).build()

    with tempfile.TemporaryDirectory() as d:
        ours_path = Path(d) / "ours.stl"
        cq.exporters.export(model, str(ours_path))
        ours = mt.MeshInspector.load(ours_path)
        ref = mt.MeshInspector.load(reference)

        assert ours.extents[0] == pytest.approx(ref.extents[0], abs=0.1)
        assert ours.extents[1] == pytest.approx(ref.extents[1], abs=0.1)
        assert ours.extents[2] == pytest.approx(ref.extents[2], abs=0.05)

        def med_open(insp, z):
            p = insp.slice_at(z)
            return statistics.median(w for (w, _l) in p.hole_extents)

        assert med_open(ours, 0.1) == pytest.approx(med_open(ref, 0.1), abs=0.3)
        assert med_open(ours, 1.5) == pytest.approx(med_open(ref, 1.5), abs=0.3)
        assert med_open(ours, 4.9) == pytest.approx(med_open(ref, 4.9), abs=0.5)


def test_teardrop_magnet_roof_points_up(gridfinity):
    """A horizontal teardrop pocket must reach higher above its axis than below,
    so the roof is a printable overhang (the fix for oval magnet holes)."""
    from importlib import import_module

    geom = import_module("bingrid.geometry")
    cfg = gridfinity.GridConfig(grid_x=1, grid_y=1, height=6.0)
    mpf = geom.MagnetPocketFeature()

    z0 = 3.0
    pocket = mpf._horizontal_pocket((0.0, -21.0, z0), (0.0, 1.0, 0.0), cfg)
    bb = pocket.BoundingBox()
    above = bb.zmax - z0
    below = z0 - bb.zmin
    assert above > below  # roof points up
    assert (above - below) == pytest.approx(cfg.magnet.teardrop_peak, abs=1e-6)


def test_teardrop_plate_is_watertight(gridfinity):
    _cfg, model = _build(gridfinity, grid_x=2, grid_y=2, height=6.0)
    assert model.val().isValid()


def test_vertical_magnet_plate_is_watertight(gridfinity):
    cfg, model = _build(
        gridfinity,
        grid_x=2,
        grid_y=2,
        floor=2.0,
        magnet=gridfinity.MagnetConfig(orientation="vertical"),
    )
    assert model.val().isValid()
    # Bottom-drilled pockets start at the base (z=0).
    bb = model.val().BoundingBox()
    assert bb.zmin == pytest.approx(0.0, abs=1e-6)


def test_connector_tab_projects_past_edge(gridfinity):
    cfg, model = _build(
        gridfinity,
        grid_x=2,
        grid_y=2,
        connector=gridfinity.ConnectorConfig(enabled=True, depth=4.0),
    )
    bb = model.val().BoundingBox()
    # Male tabs live on the -X and -Y edges and must overhang by ~depth.
    assert (-cfg.width / 2) - bb.xmin == pytest.approx(4.0, abs=1e-6)
    assert (-cfg.length / 2) - bb.ymin == pytest.approx(4.0, abs=1e-6)
    # Slots on +X/+Y must not extend past the nominal edge.
    assert bb.xmax == pytest.approx(cfg.width / 2, abs=1e-6)
    assert bb.ymax == pytest.approx(cfg.length / 2, abs=1e-6)


def test_two_tiles_mate_into_valid_solid(gridfinity):
    """A tile's -X tab should seat in its +X neighbour's slot."""
    cfg = gridfinity.GridConfig(
        grid_x=2, grid_y=2,
        connector=gridfinity.ConnectorConfig(enabled=True),
    )
    a = gridfinity.GridfinityPlate(cfg).build()
    b = gridfinity.GridfinityPlate(cfg).build().translate((cfg.width, 0, 0))
    combined = a.union(b)
    assert combined.val().isValid()


def test_exporter_writes_both_files(gridfinity, tmp_path):
    cfg, model = _build(gridfinity, grid_x=1, grid_y=1)
    exporter = gridfinity.ModelExporter(tmp_path)
    paths = exporter.export(model, cfg)
    assert len(paths) == 2
    assert {p.suffix for p in paths} == {".stl", ".step"}
    for p in paths:
        assert p.exists() and p.stat().st_size > 0


def test_exporter_name_reflects_socket_and_connectors(gridfinity, tmp_path):
    cfg = gridfinity.GridConfig(
        grid_x=2, grid_y=2,
        connector=gridfinity.ConnectorConfig(enabled=True),
    )
    name = gridfinity.ModelExporter(tmp_path).default_name(cfg)
    assert name == "gridfinity_2x2_open_socket_mag_3.0x1.0_connect"


def test_exporter_name_reflects_floor_and_taper(gridfinity, tmp_path):
    cfg = gridfinity.GridConfig(
        grid_x=2, grid_y=2,
        floor=1.0,
        opening_style="taper",
        taper=gridfinity.TaperConfig(angle_deg=2.0),
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    name = gridfinity.ModelExporter(tmp_path).default_name(cfg)
    assert name == "gridfinity_2x2_floor_taper2.0"
