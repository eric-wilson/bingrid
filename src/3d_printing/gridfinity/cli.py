"""Command-line interface: args -> config -> build -> export.

This is the composition root. It is the only module that knows about argparse
and about where output goes, keeping the geometry and config layers reusable
from code, tests, or a future GUI.

Run:
    python -m 3d_printing.gridfinity.cli --x 3 --y 2 --taper-angle 2
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .config import (
    ConnectorConfig,
    GridConfig,
    GridfinityProfile,
    MagnetConfig,
    TaperConfig,
)
from .exporter import ModelExporter
from .geometry import GridfinityPlate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a parametric Gridfinity-style frame.",
    )

    grid = parser.add_argument_group("grid")
    grid.add_argument("--x", type=int, default=2, help="cells in X (default: 2)")
    grid.add_argument("--y", type=int, default=2, help="cells in Y (default: 2)")
    grid.add_argument(
        "--pitch", type=float, default=42.0, help="cell pitch in mm (default: 42)"
    )
    grid.add_argument(
        "--wall", type=float, default=5.0,
        help="border/crossbar thickness in mm (default: 5)",
    )
    grid.add_argument(
        "--height", type=float, default=None,
        help="plate height in mm (default: auto-fit to profile and magnets)",
    )
    grid.add_argument(
        "--floor", type=float, default=0.0,
        help="floor thickness in mm; 0 = open floor (default: 0)",
    )

    opening = parser.add_argument_group("opening profile")
    opening.add_argument(
        "--style", choices=["socket", "taper"], default="socket",
        help="cell opening style: 'socket' = Gridfinity profile, "
             "'taper' = simple draft (default: socket)",
    )
    opening.add_argument(
        "--profile-top-opening", type=float, default=37.5,
        help="socket: inner opening at top of the vertical, mm (default: 37.5)",
    )
    opening.add_argument(
        "--profile-chamfer-top", type=float, default=2.15,
        help="socket: top 45 deg lead-in height, mm (default: 2.15)",
    )
    opening.add_argument(
        "--profile-straight", type=float, default=1.8,
        help="socket: vertical section height, mm (default: 1.8)",
    )
    opening.add_argument(
        "--profile-chamfer-bottom", type=float, default=0.85,
        help="socket: bottom chamfer height, mm (default: 0.85)",
    )
    opening.add_argument(
        "--profile-bottom-inset", type=float, default=1.6,
        help="socket: per-side inward step over the bottom chamfer, mm "
             "(default: 1.6)",
    )

    taper = parser.add_argument_group("taper (legacy style)")
    taper.add_argument(
        "--taper-angle", type=float, default=2.0,
        help="taper style: draft angle in degrees; 0 = straight (default: 2)",
    )

    magnet = parser.add_argument_group("magnets")
    magnet.add_argument(
        "--no-magnets", dest="magnets", action="store_false",
        help="disable magnet pockets",
    )
    magnet.add_argument(
        "--magnet-diameter", type=float, default=3.0,
        help="magnet diameter in mm (default: 3.0)",
    )
    magnet.add_argument(
        "--magnet-depth", type=float, default=1.0,
        help="magnet depth in mm (default: 1.0)",
    )
    magnet.add_argument(
        "--magnet-clearance", type=float, default=0.2,
        help="added to diameter for fit, mm (default: 0.2)",
    )
    magnet.add_argument(
        "--magnet-glue-gap", type=float, default=0.3,
        help="extra pocket depth for glue, mm (default: 0.3)",
    )
    magnet.add_argument(
        "--magnet-orientation", choices=["horizontal", "vertical"],
        default="horizontal",
        help="pocket mount: 'horizontal' = edge, 'vertical' = bottom face "
             "(default: horizontal)",
    )
    magnet.add_argument(
        "--magnet-shape", choices=["teardrop", "round"], default="teardrop",
        help="horizontal pocket shape: 'teardrop' prints round-bored without "
             "support, 'round' is a plain cylinder (default: teardrop)",
    )
    magnet.add_argument(
        "--magnet-teardrop-angle", type=float, default=45.0,
        help="teardrop roof half-angle in degrees (default: 45)",
    )
    parser.set_defaults(magnets=True)

    connector = parser.add_argument_group("connectors")
    connector.add_argument(
        "--connectors", dest="connectors", action="store_true",
        help="add dovetail connectors for tiling frames together",
    )
    connector.add_argument(
        "--connector-width", type=float, default=8.0,
        help="dovetail mouth width in mm (default: 8.0)",
    )
    connector.add_argument(
        "--connector-depth", type=float, default=4.0,
        help="dovetail depth in mm; must be < wall (default: 4.0)",
    )
    connector.add_argument(
        "--connector-flare", type=float, default=1.5,
        help="dovetail flare (half the mouth/base difference), mm (default: 1.5)",
    )
    connector.add_argument(
        "--connector-clearance", type=float, default=0.15,
        help="per-side sliding gap on the male tab, mm (default: 0.15)",
    )
    parser.set_defaults(connectors=False)

    out = parser.add_argument_group("output")
    out.add_argument(
        "--output-dir", type=Path, default=Path(".output"),
        help="directory for STL/STEP output (default: .output)",
    )
    out.add_argument(
        "--name", type=str, default=None,
        help="base file name (default: derived from config)",
    )

    return parser


def config_from_args(args: argparse.Namespace) -> GridConfig:
    return GridConfig(
        grid_x=args.x,
        grid_y=args.y,
        pitch=args.pitch,
        wall=args.wall,
        height=args.height,
        opening_style=args.style,
        floor=args.floor,
        profile=GridfinityProfile(
            top_opening=args.profile_top_opening,
            chamfer_top=args.profile_chamfer_top,
            straight=args.profile_straight,
            chamfer_bottom=args.profile_chamfer_bottom,
            bottom_inset=args.profile_bottom_inset,
        ),
        magnet=MagnetConfig(
            enabled=args.magnets,
            diameter=args.magnet_diameter,
            depth=args.magnet_depth,
            clearance=args.magnet_clearance,
            glue_gap=args.magnet_glue_gap,
            orientation=args.magnet_orientation,
            shape=args.magnet_shape,
            teardrop_angle_deg=args.magnet_teardrop_angle,
        ),
        taper=TaperConfig(angle_deg=args.taper_angle),
        connector=ConnectorConfig(
            enabled=args.connectors,
            width=args.connector_width,
            depth=args.connector_depth,
            flare=args.connector_flare,
            clearance=args.connector_clearance,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = config_from_args(args)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2

    model = GridfinityPlate(config).build()
    exporter = ModelExporter(args.output_dir)
    paths = exporter.export(model, config, name=args.name)

    print(f"Built gridfinity {config.grid_x}x{config.grid_y} "
          f"(height {config.resolved_height:.1f} mm)")
    for path in paths:
        print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
