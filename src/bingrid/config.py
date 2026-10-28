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

    # Measured carbon-copy of the reference socket (re-measured at 0.05 mm
    # z-steps). total_height = 2.1 + 1.75 + 0.80 = 4.65; bottom_opening = 37.7 -
    # 2*0.75 = 36.2; mouth_opening = 37.7 + 2*2.1 = 41.9 (< 42 pitch).
    top_opening: float = 37.7    # Inner opening along the vertical section, mm
    chamfer_top: float = 2.1     # Top lead-in chamfer height, mm
    straight: float = 1.75       # Vertical section height, mm
    chamfer_bottom: float = 0.80  # Bottom chamfer height, mm
    bottom_inset: float = 0.75   # Per-side inward step over the bottom chamfer, mm
    # Reference outer vertical corner radius the socket opening is rounded
    # CONCENTRIC with, mm; 0 = sharp (square) socket opening. Matches the real
    # Gridfinity 3.75 mm outer corner (the same radius the bin body/foot/lip use)
    # so the plate socket, the bin foot, and the bin lip stay a consistent
    # rounded family. Only affects the interior opening CURVE -- socket opening
    # sizes/heights are untouched.
    corner_radius: float = 3.75

    def __post_init__(self) -> None:
        for name in ("top_opening", "chamfer_top", "straight", "chamfer_bottom"):
            if getattr(self, name) <= 0:
                raise ValueError(f"profile {name} must be positive")
        if self.bottom_inset < 0:
            raise ValueError("profile bottom_inset cannot be negative")
        if self.bottom_opening <= 0:
            raise ValueError("profile bottom_inset too large; bottom opening <= 0")
        if self.corner_radius < 0:
            raise ValueError("profile corner_radius cannot be negative")

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

    def opening_corner_radius(self, opening: float) -> float:
        """Corner radius for a socket cross-section of width ``opening``, mm.

        The socket interior opening's corners are rounded CONCENTRIC with the
        reference outer corner (the single ``corner_radius`` -- DRY, the same
        concentric-corner thinking as :meth:`BinConfig.foot_corner_radius`).

        The widest socket plane is the mouth (``mouth_opening``); there the
        opening corner should approach the outer ``corner_radius``, so the
        mouth's corner-arc center sits at ``mouth_opening/2 - corner_radius``
        from the socket center. Rounding every narrower plane about that SAME
        center means::

            opening/2 - r == mouth_opening/2 - corner_radius

        so ``r = corner_radius - (mouth_opening - opening)/2`` -- i.e. the outer
        radius minus the opening's per-side horizontal inset below the mouth.
        The radius therefore GROWS up the socket: smallest at the narrow bottom,
        approaching ``corner_radius`` at the wide mouth, with every plane's arc
        center on one vertical line (concentric with the outer corner). Clamped
        to ``[0, opening/2]``: a sharp corner where the inset would drive it
        negative, never larger than half the opening. ``corner_radius <= 0``
        yields a sharp (square) socket opening.
        """
        if self.corner_radius <= 0:
            return 0.0
        inset = (self.mouth_opening - opening) / 2.0
        r = self.corner_radius - inset
        return max(0.0, min(r, opening / 2.0))


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
    LIP_SEAT_RUN = 1.90  # measured straight-seat run of the stacking lip, mm

    grid_x: int = 1              # Cells in X
    grid_y: int = 1              # Cells in Y
    height_units: int = 3        # Count of 7 mm Gridfinity height units
    pitch: float = 42.0          # Cell pitch, mm
    wall: float = 1.2            # Body wall thickness, mm
    floor: float = 1.0           # Floor thickness above the foot, mm; 0 = open
    corner_radius: float = 3.75  # Outer vertical corner radius, mm; 0 = sharp
    foot_clearance: float = 0.25  # Per-side gap between foot and socket, mm
    lip_clearance: float = 0.25  # Per-side seating gap inside the lip, mm
    # Outer wall of the stacking-lip rim ring, mm. ``None`` (the default)
    # derives it from the shared socket: ``(width - lip_seat_opening)/2`` = 1.90
    # for the 1x1 default. Pass a float to override. All geometry reads the
    # resolved value via ``resolved_lip_wall``, never this raw field.
    lip_wall: float | None = None
    # Library-only measured lip constants (no CLI flag): the top-face mouth
    # inset per side, the self-supporting lead-in z-rise, and the mouth flare
    # run. Measured from the reference lip sweep.
    lip_mouth_inset: float = 0.80  # Per-side inset of the flared mouth, mm
    lip_lead_h: float = 0.70       # z-rise of the self-supporting lead-in, mm
    lip_mouth_h: float = 1.20      # z-run of the mouth flare, mm
    base_overlap: float = 1.0    # mm the foot's mouth flare overlaps the body
    stacking_lip: bool = True    # Build the stacking lip
    # Painted color-band export (`--3mf-paint`). A horizontal band of the outer
    # wall is painted to a second filament/extruder via a Bambu `paint_color`
    # attribute. The band z is measured in PART z (the body base sits at
    # `base_height`, the wall top at `total_height`). `color_band_start` is the
    # z of the band bottom; leave it ``None`` to AUTO-position the band inside
    # the wall (centered in the wall span, clamped to fit) so it "just works" on
    # any bin height. Pass an explicit value to override.
    color_band_enabled: bool = False
    color_band_start: float | None = None  # z of band bottom, mm; None = auto
    color_band_height: float = 5.0   # band thickness, mm
    color_band_extruder: int = 2     # filament/extruder painted onto the band
    # Which region `--3mf-paint` colors. "lip" (the DEFAULT) paints the
    # stacking lip -- the top rim, the last region printed -- for a clean
    # two-tone "black body, colored rim" with a single color change near the
    # top. "band" paints the arbitrary mid-wall horizontal band described by the
    # `color_band_*` fields above (the explicit opt-in). Both modes assign the
    # painted faces to `color_band_extruder`.
    paint_mode: str = "lip"          # "lip" (default) or "band"
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
        # The resolved lip wall (derived from the socket, or the override) must
        # be positive. An over-large override that collapses the rim is caught
        # by the seat/mouth checks below.
        if self.resolved_lip_wall <= 0:
            raise ValueError("lip wall must be positive")
        for name in ("lip_mouth_inset", "lip_lead_h", "lip_mouth_h"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
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
            # The lip steps in from the body interior to the measured seat
            # opening, then flares out to the mouth at the top face. Guard,
            # per axis and inline (arithmetic only, no geometry render):
            #   (a) seat opening stays positive,
            #   (b) the mouth is wider than the seat (a real upward flare),
            #   (c) the straight seat run is non-negative.
            seat_w = self.inner_width - 2 * self.lip_seat_step     # 37.70
            seat_l = self.inner_length - 2 * self.lip_seat_step    # 37.70
            mouth_w = self.width - 2 * self.lip_mouth_inset        # 39.90
            mouth_l = self.length - 2 * self.lip_mouth_inset       # 39.90
            if min(seat_w, seat_l) <= 0:
                raise ValueError("wall too thin for stacking lip")
            if mouth_w <= seat_w or mouth_l <= seat_l:
                raise ValueError("stacking lip has no flare (mouth <= seat)")
            if self.lip_h - self.lip_lead_h - self.lip_mouth_h < -1e-9:
                raise ValueError("stacking lip has no seat run")
        if self.paint_mode not in ("lip", "band"):
            raise ValueError("paint_mode must be 'lip' or 'band'")
        if self.color_band_extruder < 2:
            raise ValueError("color band extruder must be >= 2")
        # Only validate the mid-wall band geometry when it is actually used --
        # i.e. the painted export is on AND band mode is selected. Lip mode
        # needs no band geometry (it paints the rim), so a lip-mode export must
        # never be rejected by band checks. The disabled defaults never reach
        # here either.
        if self.color_band_enabled and self.paint_mode == "band":
            if self.color_band_height <= 0:
                raise ValueError("color band height must be positive")
            lo, hi = self.base_height, self.total_height
            # The band itself must fit within the wall span regardless of where
            # it is placed; auto-positioning can only slide it, not shrink it.
            if self.color_band_height > (hi - lo) + 1e-9:
                raise ValueError("color band taller than the bin wall")
            start = self.resolved_color_band_start
            if start < lo - 1e-9 or start + self.color_band_height > hi + 1e-9:
                raise ValueError("color band outside the bin wall z-range")

    @property
    def foot_ref_half(self) -> float:
        """Reference half-width the foot corners are concentric about, mm.

        The foot flares to its widest at the top plane (buried in the body),
        where its corner should match the body's ``corner_radius``. Using that
        widest foot half-width as the concentric reference keeps every foot's
        corner center at ``foot_ref_half - corner_radius`` from the foot center
        -- the same place the body corner's arc center sits above it -- for ANY
        grid size (the foot sits on the pitch lattice, not the undersized
        footprint). So each foot's rounded corners line up vertically with the
        body/socket corner directly above and the transition closes gap-free.
        """
        top_size = self.profile.foot_planes(self.foot_clearance)[-1].size
        return top_size / 2.0

    @property
    def foot_straight_opening(self) -> float:
        """Outer size of the foot's straight seating section, mm.

        The socket's straight seat (``top_opening``) minus the foot clearance on
        each side = ``37.7 - 0.5 = 37.20`` for the defaults. This is the foot's
        actual contact width where it seats in a plate socket or another bin's
        lip seat.
        """
        return self.profile.top_opening - 2 * self.foot_clearance

    @property
    def lip_seat_opening(self) -> float:
        """Inner seat opening of the stacking lip, mm.

        Tied to the shared socket and the live ``lip_clearance`` so bin-in-bin
        fit matches bin-in-plate fit by construction:
        ``foot_straight_opening + 2*lip_clearance = 37.20 + 0.50 = 37.70`` --
        the same 37.70 as the baseplate socket seat. A stacked bin's foot
        (37.20 straight) drops onto this seat with 0.25 mm/side clearance.
        """
        return self.foot_straight_opening + 2 * self.lip_clearance

    @property
    def _cell_inner(self) -> float:
        """Interior opening of a SINGLE cell, mm.

        The per-cell footprint is ``pitch - 0.5`` (the same ``N*pitch - 0.5``
        rule at N=1), so one cell's interior is ``pitch - 0.5 - 2*wall`` =
        ``42 - 0.5 - 2.4 = 39.10``. The lip seat step is keyed off this so it is
        the SAME per side on every axis and every grid size (not re-derived from
        the wide ``inner_width`` of a multi-cell bin).
        """
        return self.pitch - 0.5 - 2 * self.wall

    @property
    def lip_seat_step(self) -> float:
        """Per-side inward step from the body interior to the lip seat, mm.

        ``(cell_inner - lip_seat_opening)/2`` = ``(39.10 - 37.70)/2 = 0.70``.
        Grid-independent: both axes step in by this same amount, so a 1x1 has
        ``seat_w == seat_l`` and a 1x2 short-axis seat is
        ``inner_length - 2*lip_seat_step`` (never ~42 -- the old single-socket
        bug).
        """
        return (self._cell_inner - self.lip_seat_opening) / 2.0

    @property
    def lip_seat_run(self) -> float:
        """Straight seat run of the lip, mm (read-back of ``LIP_SEAT_RUN``).

        Derived as ``lip_h - lip_lead_h - lip_mouth_h`` so it reconciles with
        the measured segments (1.90 for the defaults); the authoritative value
        is the ``LIP_SEAT_RUN`` class constant.
        """
        return self.lip_h - self.lip_lead_h - self.lip_mouth_h

    @property
    def resolved_lip_wall(self) -> float:
        """The stacking-lip rim wall, resolving ``None`` to the derived value.

        When ``lip_wall`` is ``None`` (the default) the rim wall falls out of
        the shared socket, keyed off a SINGLE cell so it is grid-independent:
        ``(cell_footprint - lip_seat_opening)/2 = (41.5 - 37.70)/2 = 1.90``
        (``cell_footprint = pitch - 0.5``). An explicit value overrides. All lip
        geometry and corner math reads this, never the raw ``lip_wall`` field.
        No cycle: ``lip_seat_opening`` derives from the socket + clearance,
        independent of ``lip_wall``.
        """
        if self.lip_wall is None:
            return (self.pitch - 0.5 - self.lip_seat_opening) / 2.0
        return self.lip_wall

    def lip_planes(self) -> tuple[tuple[float, float, float], ...]:
        """Ordered ``(z, full_width, full_length)`` from the lip base upward.

        ``z`` is LIP-LOCAL (0 at the lip base = world z=``total_height``); the
        feature offsets by ``total_height`` when building. Numeric values shown
        for the 1x1 default (width == length == 41.5):

            * z0.00 opening 39.10 (= ``inner_width``): continuous with the body
              cavity -- no downward ledge,
            * z0.70 opening 37.70: end of the self-supporting lead-in,
            * z2.60 opening 37.70: top of the straight seat run,
            * z3.80 opening 39.90: flared mouth at the top face.

        Seats are per-axis: ``seat_w == seat_l`` for a square 1x1, while a 1x2
        short-axis seat is ``inner_length - 2*lip_seat_step``. ``lead_h`` is
        clamped to ``max(lip_lead_h, lip_seat_step)`` so the lead-in underside
        never exceeds 45 deg (a no-op at the measured defaults).
        """
        inner_w, inner_l = self.inner_width, self.inner_length               # 39.10
        seat_w = self.inner_width - 2 * self.lip_seat_step                   # 37.70
        seat_l = self.inner_length - 2 * self.lip_seat_step                  # 37.70 (per-axis: inner_length - 2*step)
        mouth_w = self.width - 2 * self.lip_mouth_inset                      # 39.90
        mouth_l = self.length - 2 * self.lip_mouth_inset                     # 39.90
        lead_h = max(self.lip_lead_h, self.lip_seat_step)                    # 0.70 (>=45deg guard)
        seat_top = lead_h + self.LIP_SEAT_RUN                                # 0.70 + 1.90 = 2.60
        return (
            (0.00, inner_w, inner_l),
            (lead_h, seat_w, seat_l),
            (seat_top, seat_w, seat_l),
            (self.lip_h, mouth_w, mouth_l),
        )

    def interior_corner_radius(self, inset: float, opening: float) -> float:
        """Radius for an interior opening inset ``inset`` per side, mm.

        The interior opening corners are CONCENTRIC with the body's rounded
        outer corners (the single ``corner_radius`` reference -- DRY, no second
        radius). An outer corner of radius ``corner_radius`` on the footprint
        half-size ``H`` has its arc center at ``H - corner_radius`` from the
        bin center. An interior opening is inset ``inset`` per side, so its
        half-size is ``H - inset``; sharing the same corner center means::

            (H - inset) - r == H - corner_radius

        so ``r = corner_radius - inset``. That keeps a uniform wall thickness
        wrapping the rounded corner (the outer and inner arcs are concentric),
        and lands around ~2 mm for the default wall/rim. Clamped to
        ``[0, opening/2]``: a sharp corner where the inset would drive it
        negative, never larger than half the opening. This is the interior
        analogue of :meth:`foot_corner_radius` (same concentric-corner thinking).
        """
        if self.corner_radius <= 0:
            return 0.0
        r = self.corner_radius - inset
        return max(0.0, min(r, opening / 2.0))

    @property
    def cavity_corner_radius(self) -> float:
        """Interior corner radius of the hollow cavity, mm.

        The cavity is inset ``wall`` per side from the outer footprint, so its
        rounded corners are ``corner_radius - wall`` (concentric with the outer
        corners). Derived, not a new constant.
        """
        return self.interior_corner_radius(self.wall, min(self.inner_width, self.inner_length))

    def foot_corner_radius(self, foot_size: float) -> float:
        """Corner radius for a foot cross-section of width ``foot_size``, mm.

        The foot's rounded corners are CONCENTRIC with the body's rounded
        corners (the single ``corner_radius`` reference -- DRY, no second
        radius). A corner of radius ``r`` on a square of half-size ``h`` has its
        arc center at ``h - r`` from the foot center; the widest foot plane
        matches the body, so its corner center sits at
        ``foot_ref_half - corner_radius``. Rounding every foot plane about that
        same center means::

            foot_half - r == foot_ref_half - corner_radius

        so ``r = corner_radius - (foot_ref_half - foot_half)``. The radius
        therefore tapers up the foot -- smaller where the foot is narrow near
        the base, approaching ``corner_radius`` where the foot flares to the
        body width -- and every level stays vertically aligned with the
        body/socket corner so the foot-to-body transition closes with no open
        sliver. Clamped to ``[0, foot_half]``: a sharp corner where the taper
        would go negative, never larger than the half-width.
        """
        if self.corner_radius <= 0:
            return 0.0
        foot_half = foot_size / 2.0
        r = self.corner_radius - (self.foot_ref_half - foot_half)
        return max(0.0, min(r, foot_half))

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

        The lip is the measured sum of its three segments: a self-supporting
        lead-in (``lip_lead_h``), the straight seat run (``LIP_SEAT_RUN``), and
        the mouth flare (``lip_mouth_h``) = ``0.70 + 1.90 + 1.20 = 3.80``. The
        lead-in makes the lip underside self-supporting (<=45 deg) instead of a
        flat downward-facing ledge, so it prints clean without support. The
        body-below-seam plane (``total_height``) is unchanged, so ``build_split``
        still splits there and the lip stays purely additive above it.
        """
        if not self.stacking_lip:
            return 0.0
        return self.lip_lead_h + self.LIP_SEAT_RUN + self.lip_mouth_h

    @property
    def resolved_color_band_start(self) -> float:
        """Z of the band bottom, resolving ``None`` to an auto position, mm.

        When ``color_band_start`` is given, it is used verbatim. When it is
        ``None`` (the default), the band is centered within the wall span
        (``base_height .. total_height``) and clamped so it stays inside the
        wall -- so a painted band "just works" on any bin height without the
        caller computing a start that fits. A band taller than the wall is
        rejected in ``__post_init__`` before this is consulted for export.
        """
        if self.color_band_start is not None:
            return self.color_band_start
        lo, hi = self.base_height, self.total_height
        centered = lo + (hi - lo - self.color_band_height) / 2.0
        # Clamp into the wall span (no-op once the band fits, which validation
        # guarantees for the enabled case).
        return max(lo, min(centered, hi - self.color_band_height))

    @property
    def color_band_top(self) -> float:
        """Z of the band's top edge (resolved start + band height), mm (part coords)."""
        return self.resolved_color_band_start + self.color_band_height

    @property
    def lip_paint_bottom(self) -> float:
        """Z at/above which faces are the stacking lip, mm (part coords).

        The single lip/body seam plane: the body wall spans
        ``base_height .. total_height`` and the stacking lip spans
        ``total_height .. overall_height``, so faces with z at or above
        ``total_height`` are the lip. Lip-mode painting slices the mesh at this
        one plane and paints every face at or above it.
        """
        return self.total_height

    @property
    def overall_height(self) -> float:
        """Actual top-of-part z a mesh measures (body + lip), mm.

        The lip grows upward from ``total_height`` by ``lip_h`` (the measured
        lip height), so the body below the ``z=total_height`` mating plane is
        unchanged and ``build_split`` still splits there.
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


# Fit presets: a measured per-side pocket clearance (mm) for each named fit,
# mirroring the subjective "snug with tolerance" language of the design doc.
# ``snug`` holds the item firmly, ``normal`` (the default) drops in and is easy
# to grab, ``loose`` is very forgiving. ``HolderConfig.resolved_clearance``
# reads this (or an explicit override), the same way ``resolved_lip_wall``
# resolves the lip rim wall.
FIT_PRESETS = {"snug": 0.25, "normal": 0.40, "loose": 0.60}


@dataclass(frozen=True)
class HolderConfig:
    """A generic pocket-holder bin: a bin whose interior is a pocket grid.

    The holder is a normal :class:`BinConfig` bin (same footprint, foot, floor,
    and optional stacking lip) whose hollow interior is carved into an R x C
    array of identical pockets, each sized to one measured item plus a per-side
    fit clearance. "Hold the items directly" (many pockets) and "hold another
    container" (one big loose pocket, R=C=1) are the same engine at different
    pocket counts.

    Composition over inheritance: the holder HOLDS a validated ``bin``
    :class:`BinConfig` (a complete value object whose own tests must stay green)
    and adds the pocket fields. The handful of bin properties the geometry and
    exporter read are re-exposed here by delegating to ``self.bin``, so callers
    get one validated object.

    The pocket model (the crux -- snug WITH tolerance):

    * **Nominal item size** is what the user measures (outer ``item_w`` x
      ``item_d`` for ``rect``; ``item_dia`` for ``round``).
    * **Pocket size = nominal + 2 x clearance** (clearance per side), resolved
      from the ``fit`` preset or an explicit ``fit_clearance`` override.
    * **Pocket corner radius** rounds a rectangular pocket's internal corners
      so a boxy item is not fighting a sharp corner and the pocket prints clean.
    * **Round pockets** are a plain vertical cylinder cut (prints round, no
      teardrop needed -- the cavity opens upward).

    Layout (the single source of truth, pure arithmetic -- NO CadQuery):
    the interior opening per axis is the bin's inner opening; given a pocket
    footprint and an inter-pocket ``pocket_wall``::

        cols = floor((interior_w + pocket_wall) / (pocket_w + pocket_wall))
        rows = floor((interior_l + pocket_wall) / (pocket_d + pocket_wall))

    Explicit ``rows`` / ``cols`` override the derived counts (the fit-count
    driver). Leftover margin (what does not divide evenly) is, by default, split
    symmetrically when ``center_grid`` is on; ``--pack`` pushes the block to a
    corner so the leftover is one contiguous open strip.

    Depth never breaches the floor: a pocket's floor is clamped to
    ``cavity_bottom = base_height + floor`` -- the same rule the hollow body
    already uses.
    """

    bin: BinConfig = BinConfig()
    pocket_shape: str = "rect"           # 'rect' or 'round'
    item_w: float | None = None          # rect item width, mm
    item_d: float | None = None          # rect item depth, mm
    item_dia: float | None = None        # round item diameter, mm
    item_height: float | None = None     # item height, mm (with proud -> depth)
    fit: str = "normal"                  # 'snug' / 'normal' / 'loose' preset
    fit_clearance: float | None = None   # explicit per-side clearance, mm
    pocket_wall: float = 1.2             # rib thickness between pockets, mm
    pocket_corner_radius: float = 1.0    # rect pocket internal corner radius, mm
    pocket_depth: float | None = None    # explicit cavity depth, mm
    proud: float = 6.0                   # mm the item stands above the wall
    center_grid: bool = True             # center the grid; False = corner-pack
    # Explicit layout drivers (fit-count). ``rows`` / ``cols`` override the
    # derived counts; ``count`` is resolved by the generator into a bin size and
    # is recorded here for the summary.
    count: int | None = None
    rows: int | None = None
    cols: int | None = None

    def __post_init__(self) -> None:
        if self.pocket_shape not in ("rect", "round"):
            raise ValueError("pocket_shape must be 'rect' or 'round'")
        if self.fit not in FIT_PRESETS:
            raise ValueError("fit must be 'snug', 'normal' or 'loose'")
        # Exactly one item-size set for the shape: rect needs w AND d and must
        # NOT be given a diameter; round needs a diameter and must NOT be given
        # w/d. (The CLI precheck guards this too; validating here keeps the
        # config a self-contained value object.)
        if self.pocket_shape == "rect":
            if self.item_w is None or self.item_d is None:
                raise ValueError(
                    "rect pockets need item_w and item_d (give item_dia for round)"
                )
            if self.item_dia is not None:
                raise ValueError(
                    "rect pockets take item_w+item_d, not item_dia"
                )
        else:  # round
            if self.item_dia is None:
                raise ValueError(
                    "round pockets need item_dia (give item_w+item_d for rect)"
                )
            if self.item_w is not None or self.item_d is not None:
                raise ValueError(
                    "round pockets take item_dia, not item_w+item_d"
                )
        if self.resolved_clearance < 0:
            raise ValueError("fit clearance cannot be negative")
        if self.pocket_wall < 0:
            raise ValueError("pocket wall cannot be negative")
        if self.pocket_corner_radius < 0:
            raise ValueError("pocket corner radius cannot be negative")
        if self.proud < 0:
            raise ValueError("proud cannot be negative")
        for name in ("item_w", "item_d", "item_dia", "item_height"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("rows", "cols", "count"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be at least 1")
        # A single pocket must fit the interior on both axes.
        if self.pocket_w > self.interior_w or self.pocket_d > self.interior_l:
            raise ValueError("pocket wider than interior")
        # At least one pocket must fit.
        if self.pocket_count < 1:
            raise ValueError("no pockets fit the interior")
        # The pocket depth must be positive and never breach the floor.
        if self.resolved_pocket_depth <= 0:
            raise ValueError("pocket depth must be positive")
        if self.resolved_pocket_depth > self.available_depth + 1e-9:
            raise ValueError("pocket deeper than interior; would breach the floor")

    # --- fit resolution (mirrors resolved_lip_wall) ------------------------

    @property
    def resolved_clearance(self) -> float:
        """Per-side pocket clearance, mm.

        The explicit ``fit_clearance`` wins; otherwise the ``fit`` preset maps
        to mm via :data:`FIT_PRESETS`. Mirrors ``BinConfig.resolved_lip_wall``:
        geometry reads this, never the raw preset/override fields.
        """
        if self.fit_clearance is not None:
            return self.fit_clearance
        return FIT_PRESETS[self.fit]

    # --- pocket footprint --------------------------------------------------

    @property
    def pocket_dia(self) -> float:
        """Round pocket diameter = item diameter + 2 x clearance, mm.

        Only meaningful for ``round`` pockets; raises for ``rect`` (no diameter).
        """
        if self.pocket_shape != "round":
            raise ValueError("pocket_dia is only defined for round pockets")
        return self.item_dia + 2 * self.resolved_clearance

    @property
    def pocket_w(self) -> float:
        """Pocket footprint width, mm.

        Rect: ``item_w + 2 x clearance``. Round: the pocket diameter (a round
        pocket has a square footprint for layout -- width == depth == diameter).
        """
        if self.pocket_shape == "round":
            return self.pocket_dia
        return self.item_w + 2 * self.resolved_clearance

    @property
    def pocket_d(self) -> float:
        """Pocket footprint depth, mm (see :meth:`pocket_w`)."""
        if self.pocket_shape == "round":
            return self.pocket_dia
        return self.item_d + 2 * self.resolved_clearance

    # --- interior (delegates to the bin) -----------------------------------

    @property
    def interior_w(self) -> float:
        """Interior opening along X (the bin inner width), mm."""
        return self.bin.inner_width

    @property
    def interior_l(self) -> float:
        """Interior opening along Y (the bin inner length), mm."""
        return self.bin.inner_length

    # --- layout math (the single source of truth, no CadQuery) -------------

    @property
    def grid_cols(self) -> int:
        """Pockets across X.

        The doc formula ``floor((interior_w + pocket_wall)/(pocket_w +
        pocket_wall))``, overridden by an explicit ``cols`` when given. Floored
        at 0 so a too-wide pocket (caught in validation) never reports negative.
        """
        if self.cols is not None:
            return self.cols
        pitch = self.pocket_w + self.pocket_wall
        if pitch <= 0:
            return 0
        return max(0, int((self.interior_w + self.pocket_wall) / pitch + 1e-9))

    @property
    def grid_rows(self) -> int:
        """Pockets along Y (see :meth:`grid_cols`), overridden by ``rows``."""
        if self.rows is not None:
            return self.rows
        pitch = self.pocket_d + self.pocket_wall
        if pitch <= 0:
            return 0
        return max(0, int((self.interior_l + self.pocket_wall) / pitch + 1e-9))

    @property
    def pocket_pitch_x(self) -> float:
        """Center-to-center pocket spacing along X (pocket_w + pocket_wall), mm."""
        return self.pocket_w + self.pocket_wall

    @property
    def pocket_pitch_y(self) -> float:
        """Center-to-center pocket spacing along Y (pocket_d + pocket_wall), mm."""
        return self.pocket_d + self.pocket_wall

    @property
    def pocket_count(self) -> int:
        """Total pockets in the grid (rows x cols)."""
        return self.grid_rows * self.grid_cols

    @property
    def leftover_x(self) -> float:
        """Interior margin along X not consumed by the pocket block, mm.

        ``interior_w - (cols * pocket_w + (cols - 1) * pocket_wall)`` -- the
        "bonus" open space left over once the whole-pocket block is placed.
        """
        cols = self.grid_cols
        if cols < 1:
            return self.interior_w
        block = cols * self.pocket_w + (cols - 1) * self.pocket_wall
        return self.interior_w - block

    @property
    def leftover_y(self) -> float:
        """Interior margin along Y not consumed by the pocket block, mm."""
        rows = self.grid_rows
        if rows < 1:
            return self.interior_l
        block = rows * self.pocket_d + (rows - 1) * self.pocket_wall
        return self.interior_l - block

    # --- depth -------------------------------------------------------------

    @property
    def available_depth(self) -> float:
        """Usable pocket depth above the cavity floor, mm.

        The span between the interior floor (``cavity_bottom``) and the top of
        the body (``total_height``); a pocket deeper than this would breach the
        foot/floor, so the resolved depth is clamped to it.
        """
        return self.bin.total_height - self.bin.cavity_bottom

    @property
    def resolved_pocket_depth(self) -> float:
        """Cavity depth cut down from the top of the body interior, mm.

        Resolution order: an explicit ``pocket_depth`` wins and is used
        verbatim (so an over-deep value is caught by the floor-breach guard in
        ``__post_init__`` rather than silently shrunk); else if ``item_height``
        is given the depth is ``item_height - proud`` (so the item stands
        ``proud`` mm above the wall), clamped to the available depth because the
        units auto-fit already sizes the bin to the item; else the full
        available depth (pockets go to the floor).
        """
        if self.pocket_depth is not None:
            return self.pocket_depth
        if self.item_height is not None:
            return min(self.item_height - self.proud, self.available_depth)
        return self.available_depth

    # --- bin delegation (the properties geometry/exporter read) ------------

    @property
    def width(self) -> float:
        return self.bin.width

    @property
    def length(self) -> float:
        return self.bin.length

    @property
    def cavity_bottom(self) -> float:
        return self.bin.cavity_bottom

    @property
    def total_height(self) -> float:
        return self.bin.total_height
