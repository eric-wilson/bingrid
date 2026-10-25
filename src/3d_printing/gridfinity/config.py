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
class GridfinityProfile:
    """The standard Gridfinity baseplate socket profile for a cell opening.

    Measured from the ``BGG V1.0.0`` reference and matching the published
    Gridfinity spec. Reading from the top face downward the cell wall is:

        * ``chamfer_top`` of 45 deg flare (the lead-in mouth),
        * ``straight`` vertical section,
        * ``chamfer_bottom`` of 45 deg flare down to the narrow bottom.

    ``top_opening`` is the inner size at the top of the vertical section (where
    the top chamfer begins); the mouth at the very top face is wider, and the
    bottom of the lower chamfer is narrower, both by the 45 deg run over the
    chamfer heights. These defaults reproduce the reference part at any grid
    size, so tiled plates stay compatible and bins seat across seams.
    """

    top_opening: float = 37.5    # Inner opening along the vertical section, mm
    chamfer_top: float = 2.2     # Top lead-in chamfer height, mm
    straight: float = 1.75       # Vertical section height, mm
    chamfer_bottom: float = 0.85  # Bottom chamfer height, mm
    bottom_inset: float = 1.6    # Per-side inward step over the bottom chamfer, mm

    def __post_init__(self) -> None:
        for name in ("top_opening", "chamfer_top", "straight", "chamfer_bottom"):
            if getattr(self, name) <= 0:
                raise ValueError(f"profile {name} must be positive")
        if self.bottom_inset < 0:
            raise ValueError("profile bottom_inset cannot be negative")
        if self.bottom_opening <= 0:
            raise ValueError("profile bottom_inset too large; bottom opening <= 0")

    @property
    def total_height(self) -> float:
        """Natural height of the full socket profile, mm."""
        return self.chamfer_top + self.straight + self.chamfer_bottom

    @property
    def mouth_opening(self) -> float:
        """Inner size at the very top face (widest), mm.

        The top chamfer is ~45 deg, opening by its height on each side.
        """
        return self.top_opening + 2 * self.chamfer_top

    @property
    def bottom_opening(self) -> float:
        """Inner size at the bottom of the lower chamfer (narrowest), mm."""
        return self.top_opening - 2 * self.bottom_inset


@dataclass(frozen=True)
class ConnectorConfig:
    """Dovetail connectors on the outer edges for tiling frames together.

    A vertical dovetail is placed at the midpoint of each outer edge. Two edges
    (+X, +Y) receive female slots; the opposite edges (-X, -Y) receive male
    tabs. Pushing two tiles together mates a male tab of one into the female
    slot of its neighbour. The male tab is undersized by ``clearance`` so it
    slides without a press fit.
    """

    enabled: bool = False
    width: float = 8.0           # Dovetail mouth width, mm
    depth: float = 4.0           # How far the dovetail projects/recesses, mm
    flare: float = 1.5           # Half-difference between inner and mouth width, mm
    clearance: float = 0.15      # Per-side gap subtracted from the male tab, mm

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("connector width must be positive")
        if self.depth <= 0:
            raise ValueError("connector depth must be positive")
        if self.flare < 0:
            raise ValueError("connector flare cannot be negative")
        if self.flare * 2 >= self.width:
            raise ValueError("connector flare too large; mouth would be non-positive")
        if self.clearance < 0:
            raise ValueError("connector clearance cannot be negative")

    @property
    def inner_width(self) -> float:
        """Width at the base of the dovetail (wider than the mouth)."""
        return self.width + 2 * self.flare


@dataclass(frozen=True)
class GridConfig:
    """Overall frame geometry plus its feature configs."""

    grid_x: int = 2              # Cells in X
    grid_y: int = 2              # Cells in Y
    pitch: float = 42.0          # Gridfinity cell pitch, mm
    wall: float = 5.0            # Border and crossbar thickness, mm
    height: float | None = None  # Plate height, mm; auto-derived when None
    opening_style: str = "socket"  # 'socket' (Gridfinity) or 'taper' (legacy)
    floor: float = 0.0           # Floor thickness, mm; 0 = open floor
    profile: GridfinityProfile = GridfinityProfile()
    magnet: MagnetConfig = MagnetConfig()
    taper: TaperConfig = TaperConfig()
    connector: ConnectorConfig = ConnectorConfig()

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
        if self.opening_style not in ("socket", "taper"):
            raise ValueError("opening_style must be 'socket' or 'taper'")
        if self.floor < 0:
            raise ValueError("floor cannot be negative")
        if self.floor >= self.resolved_height:
            raise ValueError("floor must be less than the plate height")

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

        if self.opening_style == "socket":
            # The socket profile (plus floor) must fit within the plate height.
            if self.profile.total_height + self.floor > self.resolved_height + 1e-9:
                raise ValueError(
                    "height too small for the socket profile plus floor; "
                    "increase height or reduce the profile/floor"
                )
            # The widest point (the mouth) must leave material in the wall.
            if self.profile.mouth_opening >= self.pitch:
                raise ValueError(
                    "socket mouth wider than pitch; reduce profile chamfer/top "
                    "opening or increase pitch"
                )

        if self.connector.enabled:
            # The widest part of the dovetail must fit along the shorter edge.
            shortest_edge = min(self.width, self.length)
            if self.connector.inner_width >= shortest_edge:
                raise ValueError(
                    "connector too wide for the frame edge; shrink connector "
                    "width/flare or enlarge the grid"
                )
            # A female slot must not eat through the wall into the cell opening.
            if self.connector.depth >= self.wall:
                raise ValueError(
                    "connector depth must be less than wall thickness"
                )

    @property
    def resolved_height(self) -> float:
        """Plate height, auto-sized when ``height`` is unset.

        Auto-sizing takes the largest of: the socket profile height (when used),
        the room needed for horizontal magnet pockets, and a sensible floor, so
        the default plate always fully contains its features.
        """
        if self.height is not None:
            return self.height

        candidates = []
        if self.opening_style == "socket":
            candidates.append(self.profile.total_height + self.floor)
        if self.magnet.enabled:
            candidates.append(self.magnet.diameter + 2.0)
        candidates.append(10.0 if self.opening_style != "socket" else 0.0)
        return max(candidates)

    @property
    def width(self) -> float:
        return self.grid_x * self.pitch

    @property
    def length(self) -> float:
        return self.grid_y * self.pitch
