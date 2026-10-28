"""bingrid — parametric Gridfinity-style grids and the bins that fit them.

Public API:
    GridConfig, MagnetConfig, TaperConfig, GridfinityProfile, ConnectorConfig,
    BinConfig, HolderConfig
        -- validated parameter/value objects
    GridfinityPlate  -- builds the baseplate/frame CadQuery solid
    GridfinityBin    -- builds a hollow open-top bin that plugs into a plate
    ModelExporter    -- writes STL/STEP

The general-purpose mesh inspection utilities live in ``bingrid.meshtools``.
"""
from .config import (
    FIT_PRESETS,
    BinConfig,
    ConnectorConfig,
    GridConfig,
    GridfinityProfile,
    HolderConfig,
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
    PocketGridFeature,
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
    "HolderConfig",
    "FIT_PRESETS",
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
    "PocketGridFeature",
    "StackingLipFeature",
]
