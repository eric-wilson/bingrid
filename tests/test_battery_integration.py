"""Integration tests for the battery generator (build real solids).

Marked ``integration`` (excluded by the default ``-m 'not integration'``
selection) because rendering is slow. Every seeded battery type must build a
valid watertight solid with NO extra flags -- including the three thin coin
cells, which rely on the coin-cell proud clamp. Measures ONLY our own generated
meshes; never references anything under ``samples/``.
"""
import pytest

from bingrid.batteries import preset_names

pytestmark = pytest.mark.integration


def _battery():
    import bingrid.cli.generators.battery as m

    return m


@pytest.mark.parametrize("type_name", list(preset_names()))
def test_every_preset_builds_watertight(gridfinity, app_mod, type_name):
    import bingrid.cli.generators  # noqa: F401  ensure registration

    parser = app_mod._build_top_parser()
    args = parser.parse_args(["battery", "--type", type_name])
    battery = _battery()
    cfg = battery.build_config(args)
    g = gridfinity
    bin_ = g.GridfinityBin(
        cfg.bin,
        features=[
            g.BinBodyFeature(),
            g.BinFootFeature(),
            g.PocketGridFeature(cfg),
            g.StackingLipFeature(),
        ],
    )
    assert bin_.build().val().isValid()


def test_cli_battery_aa_writes_files(gridfinity, app_mod, tmp_path):
    rc = app_mod.main(["battery", "--type", "AA", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("*.stl"))
    assert list(tmp_path.glob("*.step"))
