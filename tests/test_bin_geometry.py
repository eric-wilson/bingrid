"""Fast (non-render) tests for the bin builder's pipeline shape."""


def test_default_feature_pipeline_order(geometry_mod, config_mod):
    cfg = config_mod.BinConfig()
    kinds = [type(f).__name__ for f in geometry_mod.GridfinityBin(cfg).features]
    assert kinds == [
        "BinBodyFeature",
        "BinFootFeature",
        "HollowInteriorFeature",
        "StackingLipFeature",
    ]


def test_feature_pipeline_is_injectable(geometry_mod, config_mod):
    cfg = config_mod.BinConfig()
    only_body = [geometry_mod.BinBodyFeature()]
    bin_ = geometry_mod.GridfinityBin(cfg, features=only_body)
    assert bin_.features is only_body


def test_bin_cell_centers_use_pitch_lattice(geometry_mod, config_mod):
    # Foot centers must span the full grid*pitch lattice, NOT the undersized
    # bin width (grid*pitch - 0.5), so multi-cell feet register with sockets.
    cfg = config_mod.BinConfig(grid_x=2, grid_y=1)
    centers = list(geometry_mod._bin_cell_centers(cfg))
    xs = sorted(cx for _i, _j, cx, _cy in centers)
    # 2 cells at pitch 42: centers at -21 and +21 (full 84 span), not -41.75..
    assert xs == [-21.0, 21.0]
    # A single cell is centered at the origin.
    one = list(geometry_mod._bin_cell_centers(config_mod.BinConfig(grid_x=1, grid_y=1)))
    assert [(cx, cy) for _i, _j, cx, cy in one] == [(0.0, 0.0)]
