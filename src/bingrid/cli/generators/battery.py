"""Battery generator spec: a holder preloaded with a known battery type.

A thin, user-friendly front door over the ``holder`` generator. The user picks
a known battery type (``--type AA`` / ``9V`` / ``CR2032`` / ...) and the
generator factory-loads that preset's shape + measured item footprint + height
onto the namespace, then delegates to holder's resolution, export, and summary
helpers (DRY -- the battery generator carries no pocket math of its own).

The option list is holder's, with the four raw item-dimension flags
(``--item-w``/``--item-d``/``--item-dia``/``--item-height``) removed and a
single ``--type`` CHOICE inserted near the front; the preset supplies all four
removed values. Coin cells (CR20xx) are only a couple of mm tall, so a coin-cell
proud clamp shrinks ``--proud`` to leave a minimum pocket depth, letting every
seeded type -- including the thin coins -- build with no extra flags.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from ... import batteries
from ...config import HolderConfig
from ...exporter import ModelExporter
from ..registry import REGISTRY
from ..schema import GeneratorSpec, OptionSpec, OptionType
from . import holder

# Minimum pocket depth (mm) a coin cell keeps after the proud clamp, so even a
# 1.6 mm CR2016 leaves a real cavity to drop into.
MIN_POCKET_DEPTH = 2.5

# The item-dimension flags the preset replaces: dropped from the battery option
# list so the battery CLI never exposes a raw --item-* flag.
_REMOVED_DESTS = frozenset({"item_w", "item_d", "item_dia", "item_height"})

_TYPE_OPTION = OptionSpec(
    "type", "--type", OptionType.CHOICE,
    batteries.type_help(),
    default="AA", choices=batteries.preset_names(),
)


def _build_options() -> "tuple[OptionSpec, ...]":
    """Holder's options minus the raw item flags, plus a leading ``--type``.

    The ``--type`` CHOICE is inserted just after holder's ``--x``/``--y`` so it
    reads near the front of the menu; every other holder option is kept verbatim
    (including ``--pocket-shape``, whose value is overridden by the preset in
    ``build_config`` -- it is kept only so the gate structure stays identical).
    """
    kept = [o for o in holder.OPTIONS if o.dest not in _REMOVED_DESTS]
    # Insert --type right after the leading --x/--y pair (index 2 in holder's
    # order); fall back to the front if that shape ever changes.
    insert_at = 0
    for i, opt in enumerate(kept):
        if opt.dest in ("x", "y"):
            insert_at = i + 1
    kept.insert(insert_at, _TYPE_OPTION)
    return tuple(kept)


OPTIONS = _build_options()


def build_config(args: Namespace) -> HolderConfig:
    preset = batteries.PRESETS[args.type]

    # Factory-load the preset onto the namespace so holder's resolution path
    # sees it exactly as if the user had typed the raw item flags.
    args.pocket_shape = preset.shape
    if preset.shape == "round":
        args.item_dia = preset.item_dia
        args.item_w = None
        args.item_d = None
    else:
        args.item_w = preset.item_w
        args.item_d = preset.item_d
        args.item_dia = None
    args.item_height = preset.height

    # Coin-cell proud clamp: a thin cell (e.g. CR2016 at 1.6 mm) would otherwise
    # resolve a non-positive pocket depth under the 6 mm default proud. Clamp
    # proud so at least MIN_POCKET_DEPTH of depth remains, never raising it.
    args.proud = min(args.proud, max(preset.height - MIN_POCKET_DEPTH, 0.0))

    # Delegate to holder's resolution path verbatim (DRY).
    units_hint = holder._resolve_units(args, 1, 1)
    grid_x, grid_y = holder._resolve_bin_size(args, units_hint)
    units = holder._resolve_units(args, grid_x, grid_y)
    bin_cfg = holder._make_bin(args, grid_x, grid_y, units)
    return holder._make_holder(bin_cfg, args)


def precheck(args: Namespace) -> "str | None":
    # No item-shape guard: the preset is always well-formed. Only the shared
    # lip/paint guards apply.
    return holder.lip_paint_guards(args)


def build_and_export(
    config: HolderConfig, args: Namespace, exporter: ModelExporter
) -> "list[Path]":
    name = args.name or exporter.battery_default_name(config, args.type)
    return holder.build_and_export_named(config, args, exporter, name)


def _recover_type(config: HolderConfig) -> "str | None":
    """Recover the battery type name from a resolved holder config.

    The dispatcher calls ``summary(config, paths)`` without the namespace, and
    :class:`HolderConfig` has no type field, so the chosen type is recovered by
    matching the config's pocket shape + item footprint against the preset
    table. Returns the matching name or ``None`` if nothing matches.
    """
    for name, preset in batteries.PRESETS.items():
        if preset.shape != config.pocket_shape:
            continue
        if preset.shape == "round":
            if config.item_dia == preset.item_dia:
                return name
        elif config.item_w == preset.item_w and config.item_d == preset.item_d:
            return name
    return None


def summary(config: HolderConfig, paths: "list[Path]") -> str:
    type_name = _recover_type(config)
    head = f"Battery type: {type_name}" if type_name else "Battery type: custom"
    return head + "\n" + holder.summary(config, paths)


SPEC = GeneratorSpec(
    name="battery",
    help="Generate a Gridfinity holder preloaded with a known battery type.",
    options=OPTIONS,
    build_config=build_config,
    build_and_export=build_and_export,
    summary=summary,
    precheck=precheck,
)

REGISTRY.register(SPEC)
