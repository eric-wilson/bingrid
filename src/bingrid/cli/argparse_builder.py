"""Generate an argparse subparser from a :class:`GeneratorSpec`.

One argument is emitted per :class:`OptionSpec` according to its ``type``; the
PAIR boolean emission (positive store_true, negative store_false, then a single
``set_defaults`` after both) is load-bearing and reproduces the old bin CLI
exactly.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .schema import BoolStyle, GeneratorSpec, OptionSpec, OptionType

_SCALAR_ARGPARSE_TYPE = {
    OptionType.INT: int,
    OptionType.FLOAT: float,
    OptionType.STR: str,
    OptionType.PATH: Path,
}


def dest_for(spec: OptionSpec) -> str:
    """Return the argparse dest for an option (explicit, equals default rule)."""

    return spec.dest


def add_subparser(
    subparsers: "argparse._SubParsersAction",
    spec: GeneratorSpec,
    parents: "list[argparse.ArgumentParser] | None" = None,
) -> argparse.ArgumentParser:
    """Create and return the subparser for ``spec`` with all its arguments."""

    sub = subparsers.add_parser(spec.name, help=spec.help, parents=parents or [])
    for opt in spec.options:
        _add_option(sub, opt)
    return sub


def _add_option(sub: argparse.ArgumentParser, opt: OptionSpec) -> None:
    dest = dest_for(opt)

    if opt.type in _SCALAR_ARGPARSE_TYPE:
        sub.add_argument(
            opt.flag,
            dest=dest,
            type=_SCALAR_ARGPARSE_TYPE[opt.type],
            default=opt.default,
            help=opt.help,
        )
        return

    if opt.type is OptionType.CHOICE:
        sub.add_argument(
            opt.flag,
            dest=dest,
            type=str,
            choices=list(opt.choices),
            default=opt.default,
            help=opt.help,
        )
        return

    if opt.type is OptionType.BOOL:
        if opt.bool_style is BoolStyle.POSITIVE_ON:
            sub.add_argument(
                opt.flag, dest=dest, action="store_true", default=False,
                help=opt.help,
            )
        elif opt.bool_style is BoolStyle.NEGATIVE_OFF:
            sub.add_argument(
                opt.flag, dest=dest, action="store_false", default=True,
                help=opt.help,
            )
        elif opt.bool_style is BoolStyle.PAIR:
            # Load-bearing ordering: NO default= on either add_argument; add the
            # positive (store_true) then the negative (store_false), then set the
            # dest default ONCE, AFTER both, so the result is independent of
            # which action argparse saw last.
            sub.add_argument(
                opt.flag, dest=dest, action="store_true", help=opt.help,
            )
            sub.add_argument(
                opt.negative_flag, dest=dest, action="store_false",
                help=argparse.SUPPRESS,
            )
            sub.set_defaults(**{dest: opt.default})
        else:  # pragma: no cover - BoolStyle is a closed enum
            raise ValueError(f"unknown BoolStyle {opt.bool_style!r}")
        return

    raise ValueError(f"unknown OptionType {opt.type!r}")  # pragma: no cover
