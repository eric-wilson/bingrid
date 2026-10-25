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

from .config import GridConfig, MagnetConfig, TaperConfig
from .exporter import ModelExporter
from .geometry import GridfinityPlate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a parametric Gridfinity-style open frame.",
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
        help="plate height in mm (default: auto-fit to magnets)",
    )

    taper = parser.add_argument_group("taper")
    taper.add_argument(
        "--taper-angle", type=float, default=2.0,
        help="inner-wall draft angle in degrees; 0 = straight (default: 2)",
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
    parser.set_defaults(magnets=True)

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
        magnet=MagnetConfig(
            enabled=args.magnets,
            diameter=args.magnet_diameter,
            depth=args.magnet_depth,
            clearance=args.magnet_clearance,
            glue_gap=args.magnet_glue_gap,
        ),
        taper=TaperConfig(angle_deg=args.taper_angle),
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
