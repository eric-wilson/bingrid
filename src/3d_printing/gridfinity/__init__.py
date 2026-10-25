"""Parametric, configurable Gridfinity-style frame generator.

Public API:
    GridConfig, MagnetConfig, TaperConfig  -- parameter/value objects
    GridfinityPlate                        -- builds the CadQuery solid
    ModelExporter                          -- writes STL/STEP
"""
from .config import GridConfig, MagnetConfig, TaperConfig
from .geometry import GridfinityPlate
from .exporter import ModelExporter

__all__ = [
    "GridConfig",
    "MagnetConfig",
    "TaperConfig",
    "GridfinityPlate",
    "ModelExporter",
]
