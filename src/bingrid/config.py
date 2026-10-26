"""Value objects describing a Gridfinity frame.

Each config is a small, immutable dataclass with a single responsibility:
holding validated parameters. Keeping validation in ``__post_init__`` means an
invalid configuration can never reach the geometry builder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


class Plane(NamedTuple):
    """One horizontal cross-section of a socket/foot/lip profile.

    ``z`` is the offset measured from the profile bottom; ``size`` is the square
    opening at that height. Returned as a ``NamedTuple`` so consumers can read
    ``plane.z`` / ``plane.size`` while still unpacking/indexing like a tuple.
    """

    z: float
    size: float


@dataclass(frozen=True)
class MagnetConfig:
    """Horizontal magnet-pocket parameters.

    Two mount orientations are supported:

    * ``horizontal`` (default) drills blind pockets inward from the outer edges,
      so magnets pull tiles together edge-to-edge. Horizontal holes print as an
      overhang and tend to sag at the top (the hole comes out oval), so the
      default pocket ``shape`` is ``teardrop``: a circle with a ~45 deg pointed
      roof that prints without support while the round lower part still seats
      the magnet.
    * ``vertical`` drills pockets up into the bottom face (axis along Z). These
      print perfectly round (each layer is a flat circle) and match the
      Gridfinity convention of magnets in the base; use them to hold a plate
      down to a surface or to a baseplate below.
    """

    enabled: bool = True
    diameter: float = 3.0        # Nominal magnet diameter, mm
    depth: float = 1.0           # Nominal magnet depth, mm
    clearance: float = 0.2       # Added to diameter for a slip fit, mm
    glue_gap: float = 0.3        # Extra pocket depth for glue, mm
    orientation: str = "horizontal"  # 'horizontal' (edge) or 'vertical' (bottom)
    shape: str = "teardrop"      # 'teardrop' (print-safe) or 'round'
    teardrop_angle_deg: float = 45.0  # Roof half-angle for the teardrop peak

    def __post_init__(self) -> None:
        if self.diameter <= 0:
            raise ValueError("magnet diameter must be positive")
        if self.depth <= 0:
            raise ValueError("magnet depth must be positive")
        if self.clearance < 0:
            raise ValueError("magnet clearance cannot be negative")
        if self.glue_gap < 0:
            raise ValueError("magnet glue gap cannot be negative")
        if self.orientation not in ("horizontal", "vertical"):
            raise ValueError("magnet orientation must be 'horizontal' or 'vertical'")
        if self.shape not in ("teardrop", "round"):
            raise ValueError("magnet shape must be 'teardrop' or 'round'")
        if not 0 < self.teardrop_angle_deg < 90:
            raise ValueError("teardrop angle must be in (0, 90) degrees")

    @property
    def bore_radius(self) -> float:
        """Radius of the drilled pocket (nominal diameter + clearance)."""
        return (self.diameter + self.clearance) / 2.0

    @property
    def pocket_depth(self) -> float:
        """How deep the pocket is drilled (magnet depth + glue allowance)."""
        return self.depth + self.glue_gap

    @property
    def teardrop_peak(self) -> float:
        """Extra radial reach of the teardrop point beyond the bore radius, mm.

        The peak sits at the apex where the two 45 deg (by default) roof lines
        meet above the circle. For a roof half-angle ``a`` measured from the
        vertical the apex is ``r / sin(a)`` from the center, so the extra reach
        beyond the plain radius is ``r * (1/sin(a) - 1)``.
        """
        import math

        return self.bore_radius * (1.0 / math.sin(math.radians(self.teardrop_angle_deg)) - 1.0)


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

    Matches the published Gridfinity baseplate spec. Reading from the top face
    downward the cell wall is:

        * ``chamfer_top`` of 45 deg flare (the lead-in mouth),
        * ``straight`` vertical section,
        * ``chamfer_bottom`` of 45 deg flare down to the narrow bottom.

    ``top_opening`` is the inner size at the top of the vertical section (where
    the top chamfer begins); the mouth at the very top face is wider, and the
    bottom of the lower chamfer is narrower, both by the 45 deg run over the
    chamfer heights. These defaults reproduce the standard profile at any grid
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

    def profile_planes(self) -> tuple[Plane, ...]:
        """The socket cross-section as ordered (z, size) planes, bottom-up.

        This is the single source of truth for the socket shape. The baseplate
        socket, the bin foot (:meth:`foot_planes`), and the stacking lip all
        derive from these four planes, so they mate by construction. ``z`` is
        measured from the profile bottom:

            * bottom of the lower chamfer (narrowest, ``bottom_opening``),
            * bottom of the vertical section (``top_opening``),
            * top of the vertical section (``top_opening``),
            * the mouth at the top face (widest, ``mouth_opening``).
        """
        return (
            Plane(0.0, self.bottom_opening),
            Plane(self.chamfer_bottom, self.top_opening),
            Plane(self.chamfer_bottom + self.straight, self.top_opening),
            Plane(self.total_height, self.mouth_opening),
        )

    def foot_planes(self, clearance: float) -> tuple[Plane, ...]:
        """The bin foot profile: the socket's solid mate, minus clearance.

        The foot is the socket's solid complement (a male plug for the female
        socket). It shares the socket's z orientation exactly -- narrow at low
        z, wide at high z -- and each square ``size`` is reduced by
        ``2*clearance`` so the foot drops into the socket with ``clearance`` of
        gap per side. The ``z`` values are identical to :meth:`profile_planes`;
        there is NO vertical flip (the "inverse" relationship is solid-vs-void,
        not a z-mirror).
        """
        return tuple(
            Plane(p.z, p.size - 2 * clearance) for p in self.profile_planes()
        )


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
            m = self.magnet
            if m.orientation == "horizontal":
                # The hole's full diameter (plus the teardrop peak) must fit in
                # the plate height, and the pocket must not break through the wall.
                needed_height = 2 * m.bore_radius
                if m.shape == "teardrop":
                    needed_height += m.teardrop_peak
                if self.resolved_height <= needed_height:
                    raise ValueError(
                        "height too small for horizontal magnet pockets; "
                        "increase height or shrink the magnet"
                    )
                if self.wall <= m.pocket_depth:
                    raise ValueError(
                        "wall too thin for magnet pockets; increase wall or "
                        "shrink the magnet"
                    )
            else:  # vertical (bottom-face) pockets
                # Drilled up from the bottom: must fit under the floor+profile
                # and leave material, and fit within a cell footprint.
                if m.pocket_depth >= self.resolved_height:
                    raise ValueError(
                        "vertical magnet pocket deeper than the plate; increase "
                        "height or shrink the magnet depth"
                    )
                if 2 * m.bore_radius >= self.pitch - self.wall:
                    raise ValueError(
                        "vertical magnet too wide for the cell; shrink the "
                        "magnet or increase pitch"
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
        the room needed for the magnet pockets, and a sensible floor, so the
        default plate always fully contains its features.
        """
        if self.height is not None:
            return self.height

        candidates = []
        if self.opening_style == "socket":
            candidates.append(self.profile.total_height + self.floor)
        if self.magnet.enabled:
            if self.magnet.orientation == "horizontal":
                # Enough height to contain the hole diameter (+ teardrop peak).
                need = 2 * self.magnet.bore_radius
                if self.magnet.shape == "teardrop":
                    need += self.magnet.teardrop_peak
                candidates.append(need + 2.0)
            else:
                # Pocket drilled up from the bottom, plus a little material over it.
                candidates.append(self.magnet.pocket_depth + self.floor + 1.0)
        candidates.append(10.0 if self.opening_style != "socket" else 0.0)
        return max(candidates)

    @property
    def width(self) -> float:
        return self.grid_x * self.pitch

    @property
    def length(self) -> float:
        return self.grid_y * self.pitch


@dataclass(frozen=True)
class BinConfig:
    """A Gridfinity bin: a hollow open-top container that plugs into a plate.

    The bin's foot is the socket's solid mate (:meth:`GridfinityProfile.foot_planes`)
    and its optional stacking lip is a perimeter rim whose opening mirrors the
    socket cross-section swept around the whole top edge, so a bin stacks on a
    bin much as it seats on a baseplate. Footprint is ``N*pitch - 0.5``
    (0.25 mm per-side grid gap) so the bin drops into the plate opening --
    deliberately 0.5 mm smaller than ``GridConfig.width``.
    """

    HEIGHT_UNIT = 7.0  # mm per Gridfinity height unit

    grid_x: int = 1              # Cells in X
    grid_y: int = 1              # Cells in Y
    height_units: int = 3        # Count of 7 mm Gridfinity height units
    pitch: float = 42.0          # Cell pitch, mm
    wall: float = 1.2            # Body wall thickness, mm
    floor: float = 1.0           # Floor thickness above the foot, mm; 0 = open
    corner_radius: float = 3.75  # Outer vertical corner radius, mm; 0 = sharp
    foot_clearance: float = 0.25  # Per-side gap between foot and socket, mm
    lip_clearance: float = 0.25  # Per-side seating gap inside the lip, mm
    lip_wall: float = 1.2        # Outer wall of the stacking-lip rim ring, mm
    base_overlap: float = 1.0    # mm the foot's mouth flare overlaps the body
    stacking_lip: bool = True    # Build the stacking lip
    profile: GridfinityProfile = GridfinityProfile()

    def __post_init__(self) -> None:
        if self.grid_x < 1 or self.grid_y < 1:
            raise ValueError("grid dimensions must be at least 1x1")
        if self.height_units < 1:
            raise ValueError("height_units must be at least 1")
        if self.pitch <= 0:
            raise ValueError("pitch must be positive")
        if self.wall <= 0:
            raise ValueError("wall must be positive")
        if self.floor < 0:
            raise ValueError("floor cannot be negative")
        if self.corner_radius < 0:
            raise ValueError("corner radius cannot be negative")
        # A fillet can only remove material inside the footprint; a radius at or
        # beyond half the shorter side would consume the whole edge.
        if 2 * self.corner_radius >= min(self.width, self.length):
            raise ValueError("corner radius too large for footprint")
        if self.foot_clearance < 0:
            raise ValueError("foot clearance cannot be negative")
        if self.lip_clearance < 0:
            raise ValueError("lip clearance cannot be negative")
        if self.lip_wall <= 0:
            raise ValueError("lip wall must be positive")
        if self.base_overlap < 0:
            raise ValueError("base overlap cannot be negative")
        if self.base_overlap >= self.profile.total_height:
            raise ValueError(
                "base overlap must be less than the profile height"
            )
        if 2 * self.wall >= min(self.width, self.length):
            raise ValueError("wall too thick; no interior left")
        if self.inner_width <= 0 or self.inner_length <= 0:
            raise ValueError("wall too thick; no interior left")
        # The floor slab sits on top of the feet, inside the body stack
        # (z = base_height .. base_height + floor). It must leave usable body
        # above it, so floor must be strictly less than the body height.
        if self.floor >= self.body_height:
            raise ValueError("floor must be less than the body height")
        if self.foot_clearance * 2 >= self.profile.bottom_opening:
            raise ValueError("foot clearance too large; foot collapses")
        if self.stacking_lip:
            # The lip is a perimeter rim, not a central socket: its opening
            # tracks the footprint minus the rim wall and the mouth->seat step.
            # The seat (narrowest ring opening) must stay positive on both axes.
            step = 2 * self.lip_wall + 2 * self.profile.chamfer_top
            if min(self.width, self.length) - step <= 0:
                raise ValueError("wall too thin for stacking lip")

    @property
    def base_height(self) -> float:
        """Height of the exposed foot that plugs into the socket, mm.

        The foot is lofted over the full ``profile.total_height``; its top
        ``base_overlap`` is buried inside the body, so only this much protrudes.
        """
        return self.profile.total_height - self.base_overlap

    @property
    def body_height(self) -> float:
        """The usable body height (the Gridfinity height units), mm."""
        return self.height_units * self.HEIGHT_UNIT

    @property
    def total_height(self) -> float:
        """Top-of-body z (excludes the additive lip), mm."""
        return self.base_height + self.body_height

    @property
    def lip_h(self) -> float:
        """Height of the additive stacking lip (0 when disabled), mm.

        The lip is the full shared socket cross-section mirrored into the rim --
        top mouth flare, vertical seat run, and a bottom chamfer lead-in -- so
        its height is ``profile.total_height`` (DRY: the same single source of
        truth as the baseplate socket and the bin foot). The bottom chamfer is
        what makes the lip underside self-supporting (<=45 deg) instead of a
        flat downward-facing ledge, so it prints clean without support.
        """
        if not self.stacking_lip:
            return 0.0
        return self.profile.total_height

    @property
    def overall_height(self) -> float:
        """Actual top-of-part z a mesh measures (body + lip), mm.

        The lip grows upward from ``total_height`` by ``lip_h`` (the full socket
        profile height), so the body below the ``z=total_height`` mating plane
        is unchanged and ``build_split`` still splits there.
        """
        return self.total_height + self.lip_h

    @property
    def width(self) -> float:
        return self.grid_x * self.pitch - 0.5

    @property
    def length(self) -> float:
        return self.grid_y * self.pitch - 0.5

    @property
    def inner_width(self) -> float:
        return self.width - 2 * self.wall

    @property
    def inner_length(self) -> float:
        return self.length - 2 * self.wall

    @property
    def cavity_bottom(self) -> float:
        """Z where the hollow interior starts.

        The hollow is cut out of the full-width body, which spans
        ``base_height .. total_height``. The cut starts a floor slab's thickness
        above the top of the feet, so a continuous full-footprint floor slab
        (``base_height .. base_height + floor``) is left solid, bridging every
        cell into one piece -- there is no open channel between adjacent feet.

        For ``floor == 0`` (open bottom) the cut starts right at ``base_height``,
        so no slab is left and the interior stays open down onto the feet, which
        is the intended open-bottom behaviour. Starting no lower than
        ``base_height`` also means the cut never punches through the narrower
        foot side walls (which would leave a non-manifold base).
        """
        return self.base_height + self.floor
