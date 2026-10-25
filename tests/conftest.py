"""Shared test fixtures.

The package is importable as ``bingrid`` (``pyproject.toml`` puts ``src`` on
``pythonpath``). The config/geometry/exporter/cli modules live at the package
root after the flatten; ``meshtools`` is a sub-package.
"""
import pytest


@pytest.fixture(scope="session")
def gridfinity():
    import bingrid

    return bingrid


@pytest.fixture(scope="session")
def config_mod():
    import bingrid.config as m

    return m


@pytest.fixture(scope="session")
def geometry_mod():
    import bingrid.geometry as m

    return m


@pytest.fixture(scope="session")
def cli_mod():
    import bingrid.cli as m

    return m
