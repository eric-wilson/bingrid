"""Grid (plate) generator spec. Ported verbatim from the old ``bingrid.cli``.

The ordered :class:`OptionSpec` list lifts every default and help string from
the old ``build_parser`` byte-for-byte; ``build_config`` is the old
``config_from_args``; ``build_and_export`` and ``summary`` are the old
``main()`` tail split in two. ``precheck`` is None (grid has no cross-option
rules).
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ...config import (
    ConnectorConfig,
    GridConfig,
    GridfinityProfile,
    MagnetConfig,
    TaperConfig,
)
from ...exporter import ModelExporter
from ...geometry import GridfinityPlate
from ..registry import REGISTRY
from ..schema import BoolStyle, GeneratorSpec, OptionSpec, OptionType

OPTIONS = (
    # grid group
    OptionSpec("x", "--x", OptionType.INT, "cells in X (default: 2)", default=2),
    OptionSpec("y", "--y", OptionType.INT, "cells in Y (default: 2)", default=2),
    OptionSpec(
        "pitch", "--pitch", OptionType.FLOAT,
        "cell pitch in mm (default: 42)", default=42.0,
    ),
    OptionSpec(
        "wall", "--wall", OptionType.FLOAT,
        "border/crossbar thickness in mm (default: 5)", default=5.0,
    ),
    OptionSpec(
        "height", "--height", OptionType.FLOAT,
        "plate height in mm (default: auto-fit to profile and magnets)",
        default=None,
    ),
    OptionSpec(
        "floor", "--floor", OptionType.FLOAT,
        "floor thickness in mm; 0 = open floor (default: 0)", default=0.0,
    ),
    # opening profile group
    OptionSpec(
        "style", "--style", OptionType.CHOICE,
        "cell opening style: 'socket' = Gridfinity profile, "
        "'taper' = simple draft (default: socket)",
        default="socket", choices=("socket", "taper"),
    ),
    OptionSpec(
        "profile_top_opening", "--profile-top-opening", OptionType.FLOAT,
        "socket: inner opening at top of the vertical, mm (default: 37.7)",
        default=37.7,
    ),
    OptionSpec(
        "profile_chamfer_top", "--profile-chamfer-top", OptionType.FLOAT,
        "socket: top 45 deg lead-in height, mm (default: 2.1)", default=2.1,
    ),
    OptionSpec(
        "profile_straight", "--profile-straight", OptionType.FLOAT,
        "socket: vertical section height, mm (default: 1.75)", default=1.75,
    ),
    OptionSpec(
        "profile_chamfer_bottom", "--profile-chamfer-bottom", OptionType.FLOAT,
        "socket: bottom chamfer height, mm (default: 0.80)", default=0.80,
    ),
    OptionSpec(
        "profile_bottom_inset", "--profile-bottom-inset", OptionType.FLOAT,
        "socket: per-side inward step over the bottom chamfer, mm "
        "(default: 0.75)",
        default=0.75,
    ),
    # taper group
    OptionSpec(
        "taper_angle", "--taper-angle", OptionType.FLOAT,
        "taper style: draft angle in degrees; 0 = straight (default: 2)",
        default=2.0,
    ),
    # magnet group
    OptionSpec(
        "magnets", "--no-magnets", OptionType.BOOL,
        "disable magnet pockets", default=True,
        bool_style=BoolStyle.NEGATIVE_OFF,
    ),
    OptionSpec(
        "magnet_diameter", "--magnet-diameter", OptionType.FLOAT,
        "magnet diameter in mm (default: 3.0)", default=3.0,
    ),
    OptionSpec(
        "magnet_depth", "--magnet-depth", OptionType.FLOAT,
        "magnet depth in mm (default: 1.0)", default=1.0,
    ),
    OptionSpec(
        "magnet_clearance", "--magnet-clearance", OptionType.FLOAT,
        "added to diameter for fit, mm (default: 0.2)", default=0.2,
    ),
    OptionSpec(
        "magnet_glue_gap", "--magnet-glue-gap", OptionType.FLOAT,
        "extra pocket depth for glue, mm (default: 0.3)", default=0.3,
    ),
    OptionSpec(
        "magnet_orientation", "--magnet-orientation", OptionType.CHOICE,
        "pocket mount: 'horizontal' = edge, 'vertical' = bottom face "
        "(default: horizontal)",
        default="horizontal", choices=("horizontal", "vertical"),
    ),
    OptionSpec(
        "magnet_shape", "--magnet-shape", OptionType.CHOICE,
        "horizontal pocket shape: 'teardrop' prints round-bored without "
        "support, 'round' is a plain cylinder (default: teardrop)",
        default="teardrop", choices=("teardrop", "round"),
    ),
    OptionSpec(
        "magnet_teardrop_angle", "--magnet-teardrop-angle", OptionType.FLOAT,
        "teardrop roof half-angle in degrees (default: 45)", default=45.0,
    ),
    # connector group
    OptionSpec(
        "connectors", "--connectors", OptionType.BOOL,
        "add dovetail connectors for tiling frames together", default=False,
        bool_style=BoolStyle.POSITIVE_ON,
    ),
    OptionSpec(
        "connector_width", "--connector-width", OptionType.FLOAT,
        "dovetail mouth width in mm (default: 8.0)", default=8.0,
    ),
    OptionSpec(
        "connector_depth", "--connector-depth", OptionType.FLOAT,
        "dovetail depth in mm; must be < wall (default: 4.0)", default=4.0,
    ),
    OptionSpec(
        "connector_flare", "--connector-flare", OptionType.FLOAT,
        "dovetail flare (half the mouth/base difference), mm (default: 1.5)",
        default=1.5,
    ),
    OptionSpec(
        "connector_clearance", "--connector-clearance", OptionType.FLOAT,
        "per-side sliding gap on the male tab, mm (default: 0.15)", default=0.15,
    ),
    # output group
    OptionSpec(
        "output_dir", "--output-dir", OptionType.PATH,
        "directory for STL/STEP output (default: .output)",
        default=Path(".output"),
    ),
    OptionSpec(
        "name", "--name", OptionType.STR,
        "base file name (default: derived from config)", default=None,
    ),
)


def build_config(args: Namespace) -> GridConfig:
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


def build_and_export(
    config: GridConfig, args: Namespace, exporter: ModelExporter
) -> "list[Path]":
    model = GridfinityPlate(config).build()
    return exporter.export(model, config, name=args.name)


def summary(config: GridConfig, paths: "list[Path]") -> str:
    lines = [
        f"Built gridfinity {config.grid_x}x{config.grid_y} "
        f"(height {config.resolved_height:.1f} mm)"
    ]
    lines += [f"  wrote {path}" for path in paths]
    return "\n".join(lines)


SPEC = GeneratorSpec(
    name="grid",
    help="Generate a parametric Gridfinity-style frame.",
    options=OPTIONS,
    build_config=build_config,
    build_and_export=build_and_export,
    summary=summary,
    precheck=None,
)

REGISTRY.register(SPEC)
