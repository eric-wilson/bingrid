"""Render-free tests for geometry placement logic.

These exercise the pure math helpers (cell centers, magnet-pocket placements)
without building a CadQuery solid, so they stay in the fast test selection.
"""
import pytest


def test_cell_centers_count_and_symmetry(geometry_mod, config_mod):
    cfg = config_mod.GridConfig(grid_x=3, grid_y=2, pitch=42.0)
    centers = list(geometry_mod._cell_centers(cfg))
    assert len(centers) == 6  # 3 * 2

    # Centers are symmetric about the origin: their mean is ~ (0, 0).
    mean_x = sum(cx for _, _, cx, _ in centers) / len(centers)
    mean_y = sum(cy for _, _, _, cy in centers) / len(centers)
    assert mean_x == pytest.approx(0.0)
    assert mean_y == pytest.approx(0.0)


def test_cell_centers_spacing_equals_pitch(geometry_mod, config_mod):
    cfg = config_mod.GridConfig(grid_x=2, grid_y=1, pitch=42.0)
    centers = list(geometry_mod._cell_centers(cfg))
    xs = sorted({round(cx, 6) for _, _, cx, _ in centers})
    assert xs[1] - xs[0] == pytest.approx(42.0)


def test_horizontal_magnet_placements_one_per_edge_cell(geometry_mod, config_mod):
    cfg = config_mod.GridConfig(grid_x=3, grid_y=2)
    placements = geometry_mod.MagnetPocketFeature._horizontal_placements(cfg)
    # Two X-edges * grid_x + two Y-edges * grid_y = 2*3 + 2*2 = 10
    assert len(placements) == 2 * cfg.grid_x + 2 * cfg.grid_y == 10


def test_horizontal_magnet_placements_point_inward(geometry_mod, config_mod):
    cfg = config_mod.GridConfig(grid_x=1, grid_y=1)
    placements = geometry_mod.MagnetPocketFeature._horizontal_placements(cfg)
    for (ox, oy, oz), (dx, dy, dz) in placements:
        # Direction is a unit axis vector.
        assert abs(dx) + abs(dy) + abs(dz) == pytest.approx(1.0)
        # Z of every pocket is at mid-height.
        assert oz == pytest.approx(cfg.resolved_height / 2)


def test_vertical_magnet_placements_four_per_cell_in_material(
    geometry_mod, config_mod
):
    cfg = config_mod.GridConfig(
        grid_x=2, grid_y=2, floor=2.0,
        magnet=config_mod.MagnetConfig(orientation="vertical"),
    )
    placements = geometry_mod.MagnetPocketFeature._vertical_placements(cfg)
    assert len(placements) == 4 * cfg.grid_x * cfg.grid_y  # 4 per cell

    # Each pocket must sit in solid border, i.e. its bore must not fall inside
    # a cell's open area (|offset from the nearest cell center| keeps the bore
    # clear of the opening half-width).
    half_open = (cfg.pitch - cfg.wall) / 2
    r = cfg.magnet.bore_radius
    for (px, py) in placements:
        # distance from nearest cell center along each axis
        import math
        # nearest cell center grid
        cxs = [-cfg.width / 2 + (i + 0.5) * cfg.pitch for i in range(cfg.grid_x)]
        cys = [-cfg.length / 2 + (j + 0.5) * cfg.pitch for j in range(cfg.grid_y)]
        ncx = min(cxs, key=lambda c: abs(c - px))
        ncy = min(cys, key=lambda c: abs(c - py))
        # at least one axis offset must clear the opening (bore in the wall)
        clears = (abs(px - ncx) + r >= half_open) or (abs(py - ncy) + r >= half_open)
        assert clears


def test_feature_pipeline_default_includes_connector(geometry_mod, config_mod):
    cfg = config_mod.GridConfig()
    plate = geometry_mod.GridfinityPlate(cfg)
    kinds = [type(f).__name__ for f in plate.features]
    assert kinds == [
        "CellOpeningFeature",
        "MagnetPocketFeature",
        "ConnectorFeature",
    ]


def test_feature_pipeline_is_injectable(geometry_mod, config_mod):
    cfg = config_mod.GridConfig()
    only_openings = [geometry_mod.CellOpeningFeature()]
    plate = geometry_mod.GridfinityPlate(cfg, features=only_openings)
    assert plate.features is only_openings
