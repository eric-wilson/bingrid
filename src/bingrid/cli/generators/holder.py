"""Holder generator spec: a generic pocket-holder bin.

Mirrors ``generators/bin.py`` exactly in shape -- an ordered :class:`OptionSpec`
list (holder group first, then the inherited bin options copied VERBATIM),
``build_config`` -> :class:`HolderConfig`, a ``precheck`` for the item-size /
shape guards (plus the ported bin lip/paint guards), ``build_and_export``
reusing the bin's split/3mf/paint branches verbatim (the holder's body/lip split
is the SAME shape as a bin), and a ``summary`` that additionally reports the
derived pocket grid, count, and leftover margin.

Two layout drivers resolve the bin size (see the design doc):

* **fill-bin** -- ``--x``/``--y`` set the bin; the pocket grid is packed into
  the interior and the count reported.
* **fit-count** -- ``--count`` (or explicit ``--rows``/``--cols``) with no
  ``--x``/``--y`` picks the smallest whole-cell bin that holds the pockets.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ...config import FIT_PRESETS, BinConfig, GridfinityProfile, HolderConfig
from ...exporter import ModelExporter
from ...geometry import (
    BinBodyFeature,
    BinFootFeature,
    GridfinityBin,
    PocketGridFeature,
    StackingLipFeature,
)
from ..registry import REGISTRY
from ..schema import BoolStyle, GeneratorSpec, OptionSpec, OptionType

OPTIONS = (
    # --- holder group ------------------------------------------------------
    OptionSpec(
        "x", "--x", OptionType.INT,
        "cells in X (default: auto in fit-count mode, else 1)", default=None,
    ),
    OptionSpec(
        "y", "--y", OptionType.INT,
        "cells in Y (default: auto in fit-count mode, else 1)", default=None,
    ),
    OptionSpec(
        "pocket_shape", "--pocket-shape", OptionType.CHOICE,
        "pocket shape: rect or round (default: rect)", default="rect",
        choices=("rect", "round"),
    ),
    OptionSpec(
        "item_w", "--item-w", OptionType.FLOAT,
        "rect item footprint width, mm", default=None, required=True,
        prompt_when=(("pocket_shape", "rect"),),
    ),
    OptionSpec(
        "item_d", "--item-d", OptionType.FLOAT,
        "rect item footprint depth, mm", default=None, required=True,
        prompt_when=(("pocket_shape", "rect"),),
    ),
    OptionSpec(
        "item_dia", "--item-dia", OptionType.FLOAT,
        "round item diameter, mm", default=None, required=True,
        prompt_when=(("pocket_shape", "round"),),
    ),
    OptionSpec(
        "item_height", "--item-height", OptionType.FLOAT,
        "item height, mm; with --proud drives the pocket depth / bin height",
        default=None,
    ),
    OptionSpec(
        "count", "--count", OptionType.INT,
        "fit-count: total pockets wanted; picks the bin size", default=None,
    ),
    OptionSpec(
        "rows", "--rows", OptionType.INT,
        "fit-count: explicit pocket rows (along Y) instead of --count",
        default=None,
    ),
    OptionSpec(
        "cols", "--cols", OptionType.INT,
        "fit-count: explicit pocket cols (along X) instead of --count",
        default=None,
    ),
    OptionSpec(
        "fit", "--fit", OptionType.CHOICE,
        "clearance preset: snug (0.25) / normal (0.40) / loose (0.60) mm per "
        "side (default: normal)",
        default="normal", choices=("snug", "normal", "loose"),
    ),
    OptionSpec(
        "fit_clearance", "--fit-clearance", OptionType.FLOAT,
        "explicit per-side clearance, mm; overrides --fit", default=None,
    ),
    OptionSpec(
        "pocket_wall", "--pocket-wall", OptionType.FLOAT,
        "rib thickness between pockets, mm (default: 1.2)", default=1.2,
    ),
    OptionSpec(
        "pocket_corner_radius", "--pocket-corner-radius", OptionType.FLOAT,
        "rect pocket internal corner radius, mm (default: 1.0)", default=1.0,
        prompt_when=(("pocket_shape", "rect"),),
    ),
    OptionSpec(
        "pocket_depth", "--pocket-depth", OptionType.FLOAT,
        "explicit cavity depth, mm (default: auto)", default=None,
    ),
    OptionSpec(
        "proud", "--proud", OptionType.FLOAT,
        "mm the item stands above the wall (with --item-height) (default: 6.0)",
        default=6.0,
    ),
    OptionSpec(
        "center_grid", "--center-grid", OptionType.BOOL,
        "center the pocket grid; --pack pushes it to a corner (default: center)",
        default=True, bool_style=BoolStyle.PAIR, negative_flag="--pack",
        prompt_label="Center the pocket grid",
        prompt_help="center the pocket grid (off = pack into a corner)",
    ),
    OptionSpec(
        "units", "--units", OptionType.INT,
        "count of 7 mm Gridfinity height units (default: auto / 3)",
        default=None,
    ),
    # --- inherited bin group (copied VERBATIM from generators/bin.py) ------
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
    # opening profile group (SAME five defaults/help as bin)
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
        "export the single holder as one mesh with the stacking LIP painted "
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


def _bin_size_sequence() -> "list[tuple[int, int]]":
    """Whole-cell bin sizes to try in fit-count mode, smallest footprint first.

    Ordered by cell count then by the more-square shape, so the generator grows
    the bin as little as possible before it holds the requested pockets:
    1x1, 2x1, 1x2, 2x2, 3x2, 2x3, 3x3, ... up to a sane 6x6 ceiling.
    """
    sizes: "list[tuple[int, int]]" = []
    for total in range(1, 13):
        for gx in range(1, total + 1):
            if total % gx:
                continue
            gy = total // gx
            if gx <= 6 and gy <= 6:
                sizes.append((gx, gy))
    # De-duplicate while preserving order (1x1, then 2x1/1x2, 3x1/1x3, 2x2, ...).
    seen = set()
    ordered = []
    for size in sizes:
        if size not in seen:
            seen.add(size)
            ordered.append(size)
    return ordered


def _clearance(args: Namespace) -> float:
    """Resolve per-side clearance from args (explicit override or preset).

    Mirrors ``HolderConfig.resolved_clearance`` so the fit-count driver can
    size pockets before a validated ``HolderConfig`` exists.
    """
    if args.fit_clearance is not None:
        return args.fit_clearance
    return FIT_PRESETS[args.fit]


def _pocket_footprint(args: Namespace) -> "tuple[float, float]":
    """Pocket (width, depth) in mm from args (for the fit-count probe).

    Round pockets have a square footprint of the clearance-grown diameter;
    rect pockets add 2 x clearance to each item dimension. Mirrors the
    ``HolderConfig.pocket_w/pocket_d`` properties.
    """
    c = _clearance(args)
    if args.pocket_shape == "round":
        dia = args.item_dia + 2 * c
        return (dia, dia)
    return (args.item_w + 2 * c, args.item_d + 2 * c)


def _axis_count(interior: float, pocket: float, wall: float) -> int:
    """Pockets along one axis -- the doc formula, floored at 0 (for probing)."""
    pitch = pocket + wall
    if pitch <= 0:
        return 0
    return max(0, int((interior + wall) / pitch + 1e-9))


def _make_bin(args: Namespace, grid_x: int, grid_y: int, units: int) -> BinConfig:
    """Build the inner :class:`BinConfig` from the namespace + resolved size."""
    return BinConfig(
        grid_x=grid_x,
        grid_y=grid_y,
        height_units=units,
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


def _make_holder(bin_cfg: BinConfig, args: Namespace) -> HolderConfig:
    """Wrap a :class:`BinConfig` in a :class:`HolderConfig` with pocket fields."""
    return HolderConfig(
        bin=bin_cfg,
        pocket_shape=args.pocket_shape,
        item_w=args.item_w,
        item_d=args.item_d,
        item_dia=args.item_dia,
        item_height=args.item_height,
        fit=args.fit,
        fit_clearance=args.fit_clearance,
        pocket_wall=args.pocket_wall,
        pocket_corner_radius=args.pocket_corner_radius,
        pocket_depth=args.pocket_depth,
        proud=args.proud,
        center_grid=args.center_grid,
        count=args.count,
        rows=args.rows,
        cols=args.cols,
    )


def _resolve_units(args: Namespace, bin_grid_x: int, bin_grid_y: int) -> int:
    """Height units: explicit ``--units`` wins, else auto-fit from the item.

    When ``--units`` is given it is used verbatim. Otherwise, if an item height
    is given, pick the smallest ``height_units`` whose body leaves at least
    ``item_height - proud`` of pocket depth above the cavity floor (so the item
    sits with ``proud`` mm standing clear); failing that, fall back to the bin
    default of 3.
    """
    if args.units is not None:
        return args.units
    if args.item_height is None:
        return 3

    needed_depth = max(args.item_height - args.proud, 0.0)
    for units in range(1, 21):
        probe = _make_bin(args, bin_grid_x, bin_grid_y, units)
        available = probe.total_height - probe.cavity_bottom
        if available + 1e-9 >= needed_depth:
            return units
    return 3


def _resolve_bin_size(args: Namespace, units_hint: int) -> "tuple[int, int]":
    """Resolve the bin cell size from the two layout drivers.

    * fill-bin: ``--x``/``--y`` given -> use them (default the missing axis to 1).
    * fit-count: neither ``--x`` nor ``--y`` given, but ``--count`` or explicit
      ``--rows``/``--cols`` given -> grow the bin (``_bin_size_sequence``) until
      the pocket grid holds the target, first fit wins.
    * default: 1x1 when nothing pins the size.

    Returns ``(grid_x, grid_y)``. Raises ``ValueError`` when fit-count cannot
    satisfy the target within the size ceiling.
    """
    if args.x is not None or args.y is not None:
        return (args.x if args.x is not None else 1,
                args.y if args.y is not None else 1)

    # fit-count target: an explicit rows*cols, else --count, else nothing.
    explicit_grid = args.rows is not None and args.cols is not None
    if explicit_grid:
        target = args.rows * args.cols
    elif args.count is not None:
        target = args.count
    else:
        return (1, 1)

    pw, pd = _pocket_footprint(args)
    for gx, gy in _bin_size_sequence():
        probe_bin = _make_bin(args, gx, gy, units_hint)
        iw, il = probe_bin.inner_width, probe_bin.inner_length
        # The bin "holds them" only when the pockets physically fit the interior
        # (not merely when the requested count is reached): a single large pocket
        # needs a bin wide enough for it. When rows/cols are explicit, require
        # the whole requested block to fit; otherwise require the derived count.
        if pw > iw or pd > il:
            continue
        if explicit_grid:
            block_w = args.cols * pw + (args.cols - 1) * args.pocket_wall
            block_l = args.rows * pd + (args.rows - 1) * args.pocket_wall
            if block_w <= iw + 1e-9 and block_l <= il + 1e-9:
                return (gx, gy)
        else:
            cols = _axis_count(iw, pw, args.pocket_wall)
            rows = _axis_count(il, pd, args.pocket_wall)
            if rows * cols >= target:
                return (gx, gy)
    raise ValueError(
        f"could not fit {target} pockets within the maximum bin size; "
        "reduce the count or the item size"
    )


def build_config(args: Namespace) -> HolderConfig:
    # Units are resolved on the eventual bin size; the size resolver needs a
    # units hint for its fit-count probes. Interior width (hence pocket count)
    # is independent of height units, so a provisional hint is safe: resolve
    # units on a 1x1 first, resolve the size with that hint, then re-resolve
    # units on the chosen size (a no-op unless --units auto-fit depends on it).
    units_hint = _resolve_units(args, 1, 1)
    grid_x, grid_y = _resolve_bin_size(args, units_hint)
    units = _resolve_units(args, grid_x, grid_y)
    bin_cfg = _make_bin(args, grid_x, grid_y, units)
    return _make_holder(bin_cfg, args)


def lip_paint_guards(args: Namespace) -> "str | None":
    """The lip/paint prechecks shared by the holder and battery generators.

    Ported bin lip/paint guards (verbatim intent): --split-lip and --3mf each
    need the stacking lip, and --3mf-paint needs a lip unless --color-band moves
    the paint to a mid-wall band. Returns an error string (dispatcher maps it to
    exit 2) or ``None`` when clean.
    """
    if args.split_lip and not args.stacking_lip:
        return "--split-lip requires the stacking lip"
    if args.three_mf and not args.stacking_lip:
        return "--3mf requires the stacking lip"
    if args.three_mf_paint and not args.color_band and not args.stacking_lip:
        return (
            "--3mf-paint paints the stacking lip; use --color-band to "
            "paint a mid-wall band without a lip"
        )
    return None


def precheck(args: Namespace) -> "str | None":
    # Exactly one valid item-size set for the shape (mirrors the config guard,
    # but reported as an error string -> the dispatcher maps it to exit 2).
    if args.pocket_shape == "rect":
        if args.item_w is None or args.item_d is None:
            return "rect pockets need --item-w and --item-d"
        if args.item_dia is not None:
            return "rect pockets take --item-w/--item-d, not --item-dia"
    else:  # round
        if args.item_dia is None:
            return "round pockets need --item-dia"
        if args.item_w is not None or args.item_d is not None:
            return "round pockets take --item-dia, not --item-w/--item-d"

    return lip_paint_guards(args)


def build_and_export_named(
    config: HolderConfig, args: Namespace, exporter: ModelExporter, name: str
) -> "list[Path]":
    """Build the holder solid and export it under the resolved ``name``.

    The holder is a bin whose interior is carved into pockets. It keeps a
    SOLID interior (the pockets ARE the hollowing -- the locked subtractive
    decision): the body/foot are built, then PocketGridFeature cuts the R x C
    pocket array from the solid, leaving ribs between pockets, and the lip is
    added. The plain HollowInteriorFeature is deliberately NOT in the pipeline
    (a full cavity cut would leave nothing for the pockets to carve). The
    cavity-bottom clamp is reused inside PocketGridFeature so a pocket never
    breaches the foot/floor. GridfinityBin is driven by the inner BinConfig;
    the pocket feature carries the holder config it needs.

    The export branches (split STLs / two-body .3mf / painted .3mf / plain
    STL+STEP) are the SAME as a bin's, so ``export_split`` / ``export_3mf`` /
    ``export_3mf_painted`` operate on ``config.bin``. Factored out so the
    ``battery`` generator reuses the identical pipeline with its own
    battery-tagged ``name``.
    """
    bin_ = GridfinityBin(
        config.bin,
        features=[
            BinBodyFeature(),
            BinFootFeature(),
            PocketGridFeature(config),
            StackingLipFeature(),
        ],
    )

    paths = []
    if args.split_lip or args.three_mf:
        body, lip = bin_.build_split()
        if args.split_lip:
            paths += exporter.export_split(body, lip, config.bin, name=name)
        if args.three_mf:
            paths += exporter.export_3mf(body, lip, config.bin, name=name)
    if args.three_mf_paint:
        model = bin_.build()
        paths += exporter.export_3mf_painted(model, config.bin, name=name)
    if not (args.split_lip or args.three_mf or args.three_mf_paint):
        model = bin_.build()
        paths = exporter.export(model, config.bin, name=name)
    return paths


def build_and_export(
    config: HolderConfig, args: Namespace, exporter: ModelExporter
) -> "list[Path]":
    name = args.name or exporter.holder_default_name(config)
    return build_and_export_named(config, args, exporter, name)


def summary(config: HolderConfig, paths: "list[Path]") -> str:
    b = config.bin
    lines = [
        f"Built gridfinity holder {b.grid_x}x{b.grid_y} "
        f"(height {b.overall_height:.1f} mm)",
        f"  pockets {config.grid_rows}x{config.grid_cols} "
        f"= {config.pocket_count} ({config.pocket_shape})",
        f"  leftover margin x {config.leftover_x:.1f} mm, "
        f"y {config.leftover_y:.1f} mm",
    ]
    lines += [f"  wrote {path}" for path in paths]
    return "\n".join(lines)


SPEC = GeneratorSpec(
    name="holder",
    help="Generate a generic pocket-holder Gridfinity bin.",
    options=OPTIONS,
    build_config=build_config,
    build_and_export=build_and_export,
    summary=summary,
    precheck=precheck,
)

REGISTRY.register(SPEC)
