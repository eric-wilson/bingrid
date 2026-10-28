"""The explicit, typed generator registry.

A thin dict wrapper (not a plugin system) that maps a generator name to its
:class:`GeneratorSpec`. Insertion order is preserved, so subparsers and the
no-arg item menu list generators in registration order.

The module-level :data:`REGISTRY` is a singleton; generators call
``REGISTRY.register(SPEC)`` at import time (see ``cli.generators``).
"""
from __future__ import annotations

from .schema import GeneratorSpec


class Registry:
    """Name -> GeneratorSpec, preserving insertion order."""

    def __init__(self) -> None:
        self._specs: dict[str, GeneratorSpec] = {}

    def register(self, spec: GeneratorSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"generator {spec.name!r} already registered")
        self._specs[spec.name] = spec

    def get(self, name: str) -> GeneratorSpec:
        return self._specs[name]

    def names(self) -> "list[str]":
        return list(self._specs)

    def specs(self) -> "list[GeneratorSpec]":
        return list(self._specs.values())


REGISTRY = Registry()
