"""Command-line interface for Gridfinity bins: args -> config -> build -> export.

Mirrors ``bingrid.cli`` (the plate CLI) so the two are runnable side by side as
``python -m bingrid.cli`` / ``python -m bingrid.bin``. This module is the
composition root for the bin: the only place that knows about argparse and
output paths, keeping the config and geometry layers reusable.

Run:
    python -m bingrid.bin --x 2 --y 1 --units 6 --stacking-lip
    python -m bingrid.bin --x 2 --y 1 --units 6 --split-lip
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .config import BinConfig, GridfinityProfile
from .exporter import ModelExporter
from .geometry import GridfinityBin


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a parametric Gridfinity bin.",
    )

    grid = parser.add_argument_group("grid")
    grid.add_argument("--x", type=int, default=1, help="cells in X (default: 1)")
    grid.add_argument("--y", type=int, default=1, help="cells in Y (default: 1)")
    grid.add_argument(
        "--units", type=int, default=3,
        help="count of 7 mm Gridfinity height units (default: 3)",
    )
    grid.add_argument(
        "--pitch", type=float, default=42.0, help="cell pitch in mm (default: 42)"
    )
    grid.add_argument(
        "--wall", type=float, default=1.2,
        help="body wall thickness in mm (default: 1.2)",
    )
    grid.add_argument(
        "--floor", type=float, default=1.0,
        help="floor thickness in mm; 0 = open bottom (default: 1.0)",
    )
    grid.add_argument(
        "--foot-clearance", type=float, default=0.25,
        help="per-side gap between foot and socket, mm (default: 0.25)",
    )

    # Profile group: same five flags as the plate CLI (verbatim defaults) so a
    # bin can match a custom plate. Note these CLI defaults (2.15/1.8) differ
    # from the GridfinityProfile dataclass defaults (2.2/1.75) by design.
    opening = parser.add_argument_group("opening profile")
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

    lip = parser.add_argument_group("stacking lip")
    lip.add_argument(
        "--stacking-lip", dest="stacking_lip", action="store_true",
        help="build the stacking lip (default: on)",
    )
    lip.add_argument(
        "--no-stacking-lip", dest="stacking_lip", action="store_false",
        help="omit the stacking lip",
    )
    lip.add_argument(
        "--lip-clearance", type=float, default=0.25,
        help="per-side seating gap inside the lip, mm (default: 0.25)",
    )
    lip.add_argument(
        "--lip-wall", type=float, default=1.2,
        help="outer wall of the stacking-lip rim ring, mm (default: 1.2)",
    )
    lip.add_argument(
        "--base-overlap", type=float, default=1.0,
        help="mm the foot's mouth flare overlaps the body (default: 1.0)",
    )
    lip.add_argument(
        "--split-lip", action="store_true",
        help="export the body and lip as separate STL meshes",
    )
    parser.set_defaults(stacking_lip=True)

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


def config_from_args(args: argparse.Namespace) -> BinConfig:
    return BinConfig(
        grid_x=args.x,
        grid_y=args.y,
        height_units=args.units,
        pitch=args.pitch,
        wall=args.wall,
        floor=args.floor,
        foot_clearance=args.foot_clearance,
        lip_clearance=args.lip_clearance,
        lip_wall=args.lip_wall,
        base_overlap=args.base_overlap,
        stacking_lip=args.stacking_lip,
        profile=GridfinityProfile(
            top_opening=args.profile_top_opening,
            chamfer_top=args.profile_chamfer_top,
            straight=args.profile_straight,
            chamfer_bottom=args.profile_chamfer_bottom,
            bottom_inset=args.profile_bottom_inset,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.split_lip and not args.stacking_lip:
        print("error: --split-lip requires the stacking lip")
        return 2

    try:
        config = config_from_args(args)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2

    bin_ = GridfinityBin(config)
    exporter = ModelExporter(args.output_dir)

    name = args.name or exporter.bin_default_name(config)
    if args.split_lip:
        body, lip = bin_.build_split()
        paths = exporter.export_split(body, lip, config, name=name)
    else:
        model = bin_.build()
        paths = exporter.export(model, config, name=name)

    print(f"Built gridfinity bin {config.grid_x}x{config.grid_y} "
          f"(height {config.overall_height:.1f} mm)")
    for path in paths:
        print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
