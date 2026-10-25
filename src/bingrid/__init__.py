"""bingrid — parametric Gridfinity-style grids and the bins that fit them.

Public API:
    GridConfig, MagnetConfig, TaperConfig, GridfinityProfile, ConnectorConfig
        -- validated parameter/value objects
    GridfinityPlate  -- builds the CadQuery solid
    ModelExporter    -- writes STL/STEP

The general-purpose mesh inspection utilities live in ``bingrid.meshtools``.
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
