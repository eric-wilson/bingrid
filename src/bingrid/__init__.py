"""bingrid — parametric Gridfinity-style grids and the bins that fit them.

Public API:
    GridConfig, MagnetConfig, TaperConfig, GridfinityProfile, ConnectorConfig,
    BinConfig
        -- validated parameter/value objects
    GridfinityPlate  -- builds the baseplate/frame CadQuery solid
    GridfinityBin    -- builds a hollow open-top bin that plugs into a plate
    ModelExporter    -- writes STL/STEP

The general-purpose mesh inspection utilities live in ``bingrid.meshtools``.
"""
from .config import (
    BinConfig,
    ConnectorConfig,
    GridConfig,
    GridfinityProfile,
    MagnetConfig,
    Plane,
    TaperConfig,
)
from .geometry import (
    BinBodyFeature,
    BinFeature,
    BinFootFeature,
    CellOpeningFeature,
    ConnectorFeature,
    GridfinityBin,
    GridfinityPlate,
    HollowInteriorFeature,
    MagnetPocketFeature,
    PlateFeature,
    StackingLipFeature,
)
from .exporter import ModelExporter

__all__ = [
    "GridConfig",
    "MagnetConfig",
    "TaperConfig",
    "GridfinityProfile",
    "ConnectorConfig",
    "BinConfig",
    "Plane",
    "GridfinityPlate",
    "GridfinityBin",
    "ModelExporter",
    "PlateFeature",
    "CellOpeningFeature",
    "MagnetPocketFeature",
    "ConnectorFeature",
    "BinFeature",
    "BinBodyFeature",
    "BinFootFeature",
    "HollowInteriorFeature",
    "StackingLipFeature",
]
