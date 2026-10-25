"""Parametric, configurable Gridfinity-style frame generator.

Public API:
    GridConfig, MagnetConfig, TaperConfig, ConnectorConfig  -- parameter objects
    GridfinityPlate                                         -- builds the solid
    ModelExporter                                           -- writes STL/STEP
"""
from .config import (
    ConnectorConfig,
    GridConfig,
    GridfinityProfile,
    MagnetConfig,
    TaperConfig,
)
from .geometry import (
    CellOpeningFeature,
    ConnectorFeature,
    GridfinityPlate,
    MagnetPocketFeature,
    PlateFeature,
)
from .exporter import ModelExporter

__all__ = [
    "GridConfig",
    "MagnetConfig",
    "TaperConfig",
    "GridfinityProfile",
    "ConnectorConfig",
    "GridfinityPlate",
    "ModelExporter",
    "PlateFeature",
    "CellOpeningFeature",
    "MagnetPocketFeature",
    "ConnectorFeature",
]
