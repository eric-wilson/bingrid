"""Bin generator spec. Ported verbatim from the old ``bingrid.bin``.

The ordered :class:`OptionSpec` list lifts every default and help string from
the old ``build_parser`` byte-for-byte (the five ``--profile-*`` options share
the SAME defaults/help as the grid generator). ``build_config`` is the old
``config_from_args``; ``build_and_export`` is the old ``main()`` output
branching; ``summary`` is the old "Built …" block; ``precheck`` ports the three
cross-option guards.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ...config import BinConfig, GridfinityProfile
from ...exporter import ModelExporter
from ...geometry import GridfinityBin
from ..registry import REGISTRY
from ..schema import BoolStyle, GeneratorSpec, OptionSpec, OptionType

OPTIONS = (
    # grid group
    OptionSpec("x", "--x", OptionType.INT, "cells in X (default: 1)", default=1),
    OptionSpec("y", "--y", OptionType.INT, "cells in Y (default: 1)", default=1),
    OptionSpec(
        "units", "--units", OptionType.INT,
        "count of 7 mm Gridfinity height units (default: 3)", default=3,
    ),
    OptionSpec(
        "pitch", "--pitch", OptionType.FLOAT,
        "cell pitch in mm (default: 42)", default=42.0,
    ),
    OptionSpec(
        "wall", "--wall", OptionType.FLOAT,
        "body wall thickness in mm (default: 1.2)", default=1.2,
    ),
    OptionSpec(
        "floor", "--floor", OptionType.FLOAT,
        "floor thickness in mm; 0 = open bottom (default: 1.0)", default=1.0,
    ),
    OptionSpec(
        "corner_radius", "--corner-radius", OptionType.FLOAT,
        "outer vertical corner radius in mm, 0 = sharp (default: 3.75)",
        default=3.75,
    ),
    OptionSpec(
        "foot_clearance", "--foot-clearance", OptionType.FLOAT,
        "per-side gap between foot and socket, mm (default: 0.25)", default=0.25,
    ),
    # opening profile group (SAME five defaults/help as grid)
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
    # stacking lip group
    OptionSpec(
        "stacking_lip", "--stacking-lip", OptionType.BOOL,
        "build the stacking lip (default: on)", default=True,
        bool_style=BoolStyle.PAIR, negative_flag="--no-stacking-lip",
        prompt_label="Stacking lip",
        prompt_help="build the stacking lip on top of the bin",
    ),
    OptionSpec(
        "lip_clearance", "--lip-clearance", OptionType.FLOAT,
        "per-side seating gap inside the lip, mm (default: 0.25)", default=0.25,
        prompt_when=(("stacking_lip", True),),
    ),
    OptionSpec(
        "lip_wall", "--lip-wall", OptionType.FLOAT,
        "outer wall of the stacking-lip rim ring, mm "
        "(default: derived from the socket, ~1.90)",
        default=None,
        prompt_when=(("stacking_lip", True),),
    ),
    OptionSpec(
        "base_overlap", "--base-overlap", OptionType.FLOAT,
        "mm the foot's mouth flare overlaps the body (default: 1.0)",
        default=1.0,
        prompt_when=(("stacking_lip", True),),
    ),
    OptionSpec(
        "split_lip", "--split-lip", OptionType.BOOL,
        "export the body and lip as separate STL meshes", default=False,
        bool_style=BoolStyle.POSITIVE_ON,
        prompt_label="Split body/lip STLs",
        prompt_help="export the body and lip as separate STL meshes",
        prompt_when=(("stacking_lip", True),),
    ),
    OptionSpec(
        "three_mf", "--3mf", OptionType.BOOL,
        "export the body and lip as two named bodies in one .3mf file "
        "(single-file two-color alternative to --split-lip)",
        default=False, bool_style=BoolStyle.POSITIVE_ON,
        prompt_label="Two-body .3mf",
        prompt_help="export the body and lip as two named bodies in one .3mf "
                    "file (single-file two-color alternative to split STLs)",
        prompt_when=(("stacking_lip", True),),
    ),
    # color band group
    OptionSpec(
        "three_mf_paint", "--3mf-paint", OptionType.BOOL,
        "export the single bin as one mesh with the stacking LIP painted "
        "to filament 2 (Bambu paint_color .3mf): a clean two-tone body + "
        "colored rim, one color change near the top. Requires a stacking "
        "lip unless --color-band is given",
        default=False, bool_style=BoolStyle.POSITIVE_ON,
        prompt_label="Painted two-color .3mf",
        prompt_help="export one painted mesh (Bambu paint_color .3mf): the "
                    "stacking lip painted to filament 2 for a two-tone print. "
                    "Needs a stacking lip unless the color band is on",
    ),
    OptionSpec(
        "color_band", "--color-band", OptionType.BOOL,
        "with --3mf-paint, paint a mid-wall horizontal color band instead "
        "of the stacking lip (uses --color-band-start / "
        "--color-band-height); no lip required",
        default=False, bool_style=BoolStyle.POSITIVE_ON,
        prompt_label="Mid-wall color band",
        prompt_help="with painted .3mf, paint a mid-wall horizontal band "
                    "instead of the lip (no stacking lip required)",
        prompt_when=(("three_mf_paint", True),),
    ),
    OptionSpec(
        "color_band_start", "--color-band-start", OptionType.FLOAT,
        "z of the band bottom in part coords, mm "
        "(default: auto -- centered in the bin wall)",
        default=None,
        prompt_when=(("three_mf_paint", True), ("color_band", True)),
    ),
    OptionSpec(
        "color_band_height", "--color-band-height", OptionType.FLOAT,
        "color band thickness, mm (default: 5.0)", default=5.0,
        prompt_when=(("three_mf_paint", True), ("color_band", True)),
    ),
    OptionSpec(
        "color_band_extruder", "--color-band-extruder", OptionType.INT,
        "filament/extruder painted onto the band (default: 2)", default=2,
        prompt_when=(("three_mf_paint", True), ("color_band", True)),
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


def build_config(args: Namespace) -> BinConfig:
    return BinConfig(
        grid_x=args.x,
        grid_y=args.y,
        height_units=args.units,
        pitch=args.pitch,
        wall=args.wall,
        floor=args.floor,
        corner_radius=args.corner_radius,
        foot_clearance=args.foot_clearance,
        lip_clearance=args.lip_clearance,
        lip_wall=args.lip_wall,
        base_overlap=args.base_overlap,
        stacking_lip=args.stacking_lip,
        color_band_enabled=args.three_mf_paint,
        color_band_start=args.color_band_start,
        color_band_height=args.color_band_height,
        color_band_extruder=args.color_band_extruder,
        paint_mode="band" if args.color_band else "lip",
        profile=GridfinityProfile(
            top_opening=args.profile_top_opening,
            chamfer_top=args.profile_chamfer_top,
            straight=args.profile_straight,
            chamfer_bottom=args.profile_chamfer_bottom,
            bottom_inset=args.profile_bottom_inset,
        ),
    )


def precheck(args: Namespace) -> "str | None":
    if args.split_lip and not args.stacking_lip:
        return "--split-lip requires the stacking lip"

    if args.three_mf and not args.stacking_lip:
        return "--3mf requires the stacking lip"

    # Lip-mode --3mf-paint paints the stacking lip, so it needs one. Band mode
    # (--color-band) paints the wall and works without a lip.
    if args.three_mf_paint and not args.color_band and not args.stacking_lip:
        return (
            "--3mf-paint paints the stacking lip; use --color-band to "
            "paint a mid-wall band without a lip"
        )
    return None


def build_and_export(
    config: BinConfig, args: Namespace, exporter: ModelExporter
) -> "list[Path]":
    bin_ = GridfinityBin(config)

    name = args.name or exporter.bin_default_name(config)
    # --split-lip and --3mf both need the body/lip split; they may be requested
    # together (write both the two STLs AND the .3mf) or independently.
    # --3mf-paint is a separate single-mesh path (independent of the lip). When
    # none of the three is set, write the single combined STL/STEP.
    paths = []
    if args.split_lip or args.three_mf:
        body, lip = bin_.build_split()
        if args.split_lip:
            paths += exporter.export_split(body, lip, config, name=name)
        if args.three_mf:
            paths += exporter.export_3mf(body, lip, config, name=name)
    if args.three_mf_paint:
        model = bin_.build()
        paths += exporter.export_3mf_painted(model, config, name=name)
    if not (args.split_lip or args.three_mf or args.three_mf_paint):
        model = bin_.build()
        paths = exporter.export(model, config, name=name)
    return paths


def summary(config: BinConfig, paths: "list[Path]") -> str:
    lines = [
        f"Built gridfinity bin {config.grid_x}x{config.grid_y} "
        f"(height {config.overall_height:.1f} mm)"
    ]
    lines += [f"  wrote {path}" for path in paths]
    return "\n".join(lines)


SPEC = GeneratorSpec(
    name="bin",
    help="Generate a parametric Gridfinity bin.",
    options=OPTIONS,
    build_config=build_config,
    build_and_export=build_and_export,
    summary=summary,
    precheck=precheck,
)

REGISTRY.register(SPEC)
