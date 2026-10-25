"""Value objects describing a Gridfinity frame.

Each config is a small, immutable dataclass with a single responsibility:
holding validated parameters. Keeping validation in ``__post_init__`` means an
invalid configuration can never reach the geometry builder.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MagnetConfig:
    """Horizontal magnet-pocket parameters.

    Pockets are blind cylinders drilled inward from the outer edges so magnets
    sit flush against neighbouring tiles.
    """

    enabled: bool = True
    diameter: float = 3.0        # Nominal magnet diameter, mm
    depth: float = 1.0           # Nominal magnet depth, mm
    clearance: float = 0.2       # Added to diameter for a slip fit, mm
    glue_gap: float = 0.3        # Extra pocket depth for glue, mm

    def __post_init__(self) -> None:
        if self.diameter <= 0:
            raise ValueError("magnet diameter must be positive")
        if self.depth <= 0:
            raise ValueError("magnet depth must be positive")
        if self.clearance < 0:
            raise ValueError("magnet clearance cannot be negative")
        if self.glue_gap < 0:
            raise ValueError("magnet glue gap cannot be negative")

    @property
    def bore_radius(self) -> float:
        """Radius of the drilled pocket (nominal diameter + clearance)."""
        return (self.diameter + self.clearance) / 2.0

    @property
    def pocket_depth(self) -> float:
        """How deep the pocket is drilled (magnet depth + glue allowance)."""
        return self.depth + self.glue_gap


@dataclass(frozen=True)
class TaperConfig:
    """Draft applied to the inner walls of each cell opening.

    A small draft angle makes each opening slightly narrower at the bottom and
    wider at the top, giving a lead-in funnel for easier, more forgiving seating.
    An angle of 0 produces straight walls (the original behaviour).
    """

    angle_deg: float = 2.0       # Draft angle from vertical, degrees

    def __post_init__(self) -> None:
        if not 0 <= self.angle_deg < 45:
            raise ValueError("taper angle must be in the range [0, 45) degrees")

    @property
    def enabled(self) -> bool:
        return self.angle_deg > 0


@dataclass(frozen=True)
class GridConfig:
    """Overall frame geometry plus its feature configs."""

    grid_x: int = 2              # Cells in X
    grid_y: int = 2              # Cells in Y
    pitch: float = 42.0          # Gridfinity cell pitch, mm
    wall: float = 5.0            # Border and crossbar thickness, mm
    height: float | None = None  # Plate height, mm; auto-derived when None
    magnet: MagnetConfig = MagnetConfig()
    taper: TaperConfig = TaperConfig()

    def __post_init__(self) -> None:
        if self.grid_x < 1 or self.grid_y < 1:
            raise ValueError("grid dimensions must be at least 1x1")
        if self.pitch <= 0:
            raise ValueError("pitch must be positive")
        if self.wall <= 0:
            raise ValueError("wall must be positive")
        if self.wall >= self.pitch:
            raise ValueError("wall must be smaller than pitch (no opening left)")
        if self.height is not None and self.height <= 0:
            raise ValueError("height must be positive")

        # Cross-feature validation: pockets must physically fit.
        if self.magnet.enabled:
            if self.resolved_height <= 2 * self.magnet.bore_radius:
                raise ValueError(
                    "height too small for magnet pockets; increase height or "
                    "shrink the magnet"
                )
            if self.wall <= self.magnet.pocket_depth:
                raise ValueError(
                    "wall too thin for magnet pockets; increase wall or shrink "
                    "the magnet"
                )

    @property
    def resolved_height(self) -> float:
        """Plate height, auto-sized to fit horizontal magnet pockets if unset."""
        if self.height is not None:
            return self.height
        if self.magnet.enabled:
            return self.magnet.diameter + 2.0
        return 10.0

    @property
    def width(self) -> float:
        return self.grid_x * self.pitch

    @property
    def length(self) -> float:
        return self.grid_y * self.pitch
