"""Importing this package registers every generator (import order == order).

Grid is imported FIRST, then bin, then holder, so the registry (and thus
subparsers and the item menu) list them as ``["grid", "bin", "holder"]``.
Adding a future generator is
exactly: create its module with a ``GeneratorSpec`` + ``REGISTRY.register`` call
and add one import line here. No other CLI module changes.
"""
from __future__ import annotations

from . import grid  # noqa: F401  registers "grid" first
from . import bin  # noqa: F401  registers "bin" second
from . import holder  # noqa: F401  registers "holder" third
