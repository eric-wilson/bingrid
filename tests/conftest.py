"""Shared test fixtures.

The distribution package is named ``3d_printing``; it starts with a digit, so
it cannot be imported with the normal ``import`` statement. Tests import it via
:func:`importlib.import_module` and receive the module through these fixtures.
``pyproject.toml`` puts ``src`` on ``pythonpath`` so the import resolves.
"""
from importlib import import_module

import pytest


@pytest.fixture(scope="session")
def gridfinity():
    return import_module("3d_printing.gridfinity")


@pytest.fixture(scope="session")
def config_mod():
    return import_module("3d_printing.gridfinity.config")


@pytest.fixture(scope="session")
def geometry_mod():
    return import_module("3d_printing.gridfinity.geometry")


@pytest.fixture(scope="session")
def cli_mod():
    return import_module("3d_printing.gridfinity.cli")
