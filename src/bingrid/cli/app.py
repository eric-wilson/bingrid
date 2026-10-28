"""Dispatcher / entry point for the unified ``bingrid`` command.

``main(argv)`` resolves argv, populates the registry (by importing
``cli.generators``), builds the top parser from the registry, and routes to one
of four invocation modes via a raw-argv pre-scan (so "user passed nothing" is
distinguishable from "user passed values equal to defaults"):

1. subcommand + options  -> non-interactive run
2. no subcommand         -> interactive item menu, else error (no sensible default)
3. subcommand, no options -> interactive walkthrough, else schema defaults
4. subcommand + options  -> same as mode 1

Module scope imports ONLY schema/registry/argparse_builder/prompter — NOT
``cli.generators`` — so importing this module (or ``bingrid.cli``) exposes
``main`` without registering any generator.
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from ..exporter import ModelExporter
from . import argparse_builder
from .registry import REGISTRY
from .schema import GeneratorSpec


def _build_top_parser() -> argparse.ArgumentParser:
    # --no-input is defined ONCE on a shared add_help=False parent attached to
    # both the top parser and every subparser, so the token is accepted in
    # either position. Its parsed value is never consulted for control flow.
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--no-input", dest="no_input", action="store_true", default=False,
        help="never prompt; use defaults / fail cleanly (for non-TTY/CI)",
    )

    parser = argparse.ArgumentParser(
        prog="bingrid",
        description="Generate parametric Gridfinity models.",
        parents=[parent],
    )
    subparsers = parser.add_subparsers(dest="item")
    for spec in REGISTRY.specs():
        # The shared parent re-defines --no-input on each subparser so
        # `bingrid bin --no-input` also parses.
        argparse_builder.add_subparser(subparsers, spec, parents=[parent])
    return parser


def _find_subcommand_index(argv: Sequence[str], names: Sequence[str]) -> int:
    """Index of the first non-dash token that is a registered name, else -1."""
    for i, token in enumerate(argv):
        if not token.startswith("-") and token in names:
            return i
    return -1


def _run_tail(spec: GeneratorSpec, ns: argparse.Namespace) -> int:
    """precheck -> build_config (ValueError guard) -> build_and_export -> summary."""
    if spec.precheck is not None:
        message = spec.precheck(ns)
        if message is not None:
            print(f"error: {message}")
            return 2
    try:
        config = spec.build_config(ns)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    paths = spec.build_and_export(config, ns, ModelExporter(ns.output_dir))
    print(spec.summary(config, paths))
    return 0


def main(argv: "Sequence[str] | None" = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)

    # Populate the registry (import-time side effect of cli.generators).
    from . import generators  # noqa: F401

    parser = _build_top_parser()
    names = REGISTRY.names()

    # Pre-scan the raw argv to decide the mode BEFORE parse_args fills defaults.
    no_input = "--no-input" in argv
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not no_input

    i = _find_subcommand_index(argv, names)

    if i < 0:
        # No subcommand token. Any top-level option other than --no-input
        # (e.g. -h/--help, or an unknown flag) is handed to argparse so it can
        # print help or its standard usage error.
        leftover = [t for t in argv if t != "--no-input"]
        if leftover:
            parser.parse_args(argv)  # -h exits; unknown flag -> usage error, exit 2
            # A bare positional that is not a registered name reaches here only
            # if argparse accepted it; fall through to the no-item error.
        # Mode 2: no subcommand.
        if interactive:
            from . import prompter

            name = prompter.select_item(REGISTRY.specs())
            spec = REGISTRY.get(name)
            ns = prompter.walk_options(spec)
            return _run_tail(spec, ns)
        print(
            f"error: no item given; choose one of: {', '.join(names)}",
            file=sys.stderr,
        )
        return 2

    # A subcommand was found; everything after it (minus --no-input) decides
    # Mode 3 vs Mode 1/4.
    rest = [t for t in argv[i + 1:] if t != "--no-input"]
    spec = REGISTRY.get(argv[i])

    if not rest:
        # Mode 3: subcommand, no options.
        if interactive:
            from . import prompter

            ns = prompter.walk_options(spec)
            return _run_tail(spec, ns)
        ns = parser.parse_args([spec.name])
        return _run_tail(spec, ns)

    # Mode 1/4: subcommand + options; non-interactive regardless of TTY.
    ns = parser.parse_args(argv)
    return _run_tail(spec, ns)
