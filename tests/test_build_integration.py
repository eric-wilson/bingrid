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


def test_socket_profile_matches_bgg_reference(gridfinity):
    """A 3x3 socket plate should reproduce the BGG reference dimensions."""
    import statistics
    from importlib import import_module
    from pathlib import Path

    mt = import_module("3d_printing.meshtools")
    sample = (
        Path(__file__).resolve().parents[1]
        / "samples" / "BGG V1.0.0 standard.stl.stl"
    )
    if not sample.exists():
        pytest.skip("BGG reference sample not present")

    cfg = gridfinity.GridConfig(
        grid_x=3, grid_y=3, height=5.0,
        magnet=gridfinity.MagnetConfig(enabled=False),
    )
    model = gridfinity.GridfinityPlate(cfg).build()

    import tempfile
    import cadquery as cq
    with tempfile.TemporaryDirectory() as d:
        ours_path = Path(d) / "ours.stl"
        cq.exporters.export(model, str(ours_path))
        ours = mt.MeshInspector.load(ours_path)
        bgg = mt.MeshInspector.load(sample)

        # Overall footprint and height must match (tile compatibility).
        assert ours.extents[0] == pytest.approx(bgg.extents[0], abs=0.1)
        assert ours.extents[1] == pytest.approx(bgg.extents[1], abs=0.1)
        assert ours.extents[2] == pytest.approx(bgg.extents[2], abs=0.05)

        def med_open(insp, z):
            p = insp.slice_at(z)
            return statistics.median(w for (w, _l) in p.hole_extents)

        # Key seating dimensions must be close (within print tolerance).
        assert med_open(ours, 0.1) == pytest.approx(med_open(bgg, 0.1), abs=0.3)   # foot
        assert med_open(ours, 1.5) == pytest.approx(med_open(bgg, 1.5), abs=0.3)   # vertical
        assert med_open(ours, 4.9) == pytest.approx(med_open(bgg, 4.9), abs=0.5)   # mouth


def test_teardrop_magnet_roof_points_up(gridfinity):
    """A horizontal teardrop pocket must reach higher above its axis than below,
    so the roof is a printable overhang (the fix for oval magnet holes)."""
    from importlib import import_module

    geom = import_module("3d_printing.gridfinity.geometry")
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
