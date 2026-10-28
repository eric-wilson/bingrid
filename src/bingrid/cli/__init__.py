"""Unified ``bingrid`` command-line interface.

The CLI is schema-driven: each generator registers one :class:`GeneratorSpec`
whose ordered :class:`OptionSpec` list is the single source of truth for BOTH
the argparse subparser and the interactive prompter. See ``app.main`` for the
dispatcher.

Importing this package exposes :func:`main` (the console-script target) but does
NOT register any generator — registration is a side effect of importing
``bingrid.cli.generators`` (which ``app.main`` does internally). Tests that
inspect the registry must import ``bingrid.cli.generators`` first (or call
``main``).
"""
from __future__ import annotations

from .app import main

__all__ = ["main"]
