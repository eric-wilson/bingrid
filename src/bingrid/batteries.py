"""Battery preset library: known battery dimensions as plain DATA.

A single insertion-ordered table of measured battery footprints and heights,
consumed by the ``battery`` generator to factory-load a :class:`HolderConfig`
without the user measuring anything. This module is DATA only -- it imports
neither CadQuery nor the CLI, so it stays cheap to import and trivial to test.

Each :class:`BatteryPreset` carries the pocket SHAPE ('rect' or 'round') and the
raw item footprint the holder's pocket model grows by the fit clearance: a
round cell tags a diameter; a rectangular cell (the 9V block) tags width x
depth. ``height`` is the battery's long axis, which drives the holder's
height-unit auto-fit and pocket depth.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatteryPreset:
    """One known battery type's measured footprint + height, in mm.

    ``shape`` selects the holder pocket model: ``'round'`` cells carry
    ``item_dia`` (``item_w``/``item_d`` must be ``None``); ``'rect'`` cells carry
    ``item_w`` and ``item_d`` (``item_dia`` must be ``None``). ``height`` is the
    battery length, always positive. The structural invariant is enforced here
    so a malformed table entry fails at import, the same way the schema and the
    frozen configs validate themselves.
    """

    name: str
    shape: str
    item_w: float | None
    item_d: float | None
    item_dia: float | None
    height: float

    def __post_init__(self) -> None:
        if self.shape not in ("rect", "round"):
            raise ValueError(
                f"battery {self.name!r} shape must be 'rect' or 'round'"
            )
        if self.shape == "rect":
            if self.item_w is None or self.item_d is None:
                raise ValueError(
                    f"battery {self.name!r} rect preset needs item_w and item_d"
                )
            if self.item_dia is not None:
                raise ValueError(
                    f"battery {self.name!r} rect preset must not set item_dia"
                )
        else:  # round
            if self.item_dia is None:
                raise ValueError(
                    f"battery {self.name!r} round preset needs item_dia"
                )
            if self.item_w is not None or self.item_d is not None:
                raise ValueError(
                    f"battery {self.name!r} round preset must not set "
                    f"item_w/item_d"
                )
        if self.height <= 0:
            raise ValueError(f"battery {self.name!r} height must be positive")


def _round(name: str, dia: float, height: float) -> BatteryPreset:
    return BatteryPreset(
        name=name, shape="round", item_w=None, item_d=None,
        item_dia=dia, height=height,
    )


def _rect(name: str, width: float, depth: float, height: float) -> BatteryPreset:
    return BatteryPreset(
        name=name, shape="rect", item_w=width, item_d=depth,
        item_dia=None, height=height,
    )


# Insertion order is the menu / --help order: the common cylindrical cells
# first, the 9V block, then the coin cells, then the 18650. Dimensions are
# nominal manufacturer footprints in mm (diameter x length, or W x D x length
# for the rectangular 9V).
PRESETS: "dict[str, BatteryPreset]" = {
    "AA": _round("AA", 14.5, 50.5),
    "AAA": _round("AAA", 10.5, 44.5),
    "C": _round("C", 26.2, 50.0),
    "D": _round("D", 34.2, 61.5),
    "9V": _rect("9V", 26.5, 17.5, 48.5),
    "CR2032": _round("CR2032", 20.0, 3.2),
    "CR2025": _round("CR2025", 20.0, 2.5),
    "CR2016": _round("CR2016", 20.0, 1.6),
    "18650": _round("18650", 18.6, 65.2),
}


def preset_names() -> "tuple[str, ...]":
    """The known battery type names, in menu/`--help` order."""
    return tuple(PRESETS)


def type_help() -> str:
    """A human-readable listing of every known type for the ``--type`` help.

    One line per battery with its shape and measured dimensions, plus a trailing
    note pointing custom items at ``bingrid holder``. The argparse builder lifts
    an option's ``help`` verbatim and has no epilog, so the full type table is
    surfaced through this string.
    """
    lines = ["known battery types (diameter or WxD, x height, mm):"]
    for preset in PRESETS.values():
        if preset.shape == "round":
            dims = f"round dia {preset.item_dia:g}"
        else:
            dims = f"rect {preset.item_w:g}x{preset.item_d:g}"
        lines.append(f"  {preset.name}: {dims} x {preset.height:g}")
    lines.append("for a custom item, use `bingrid holder` with --item-* flags")
    return "\n".join(lines)
