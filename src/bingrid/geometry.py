"""CadQuery geometry construction for Gridfinity frames.

Responsibility boundary: this module turns a validated :class:`GridConfig`
into a CadQuery solid. It performs no I/O and no argument parsing.

Design:
    * ``PlateFeature`` is an abstraction (Open/Closed Principle). Each feature
      knows how to apply itself to the running solid. Adding a new feature
      (feet, labels, stacking lips, connectors) means adding a class, not
      editing the builder.
    * ``GridfinityPlate`` orchestrates the base box and the feature list.
    * Cell-center iteration lives in one helper (DRY) so every feature walks
      the grid the same way.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Iterator, List, Tuple

import cadquery as cq

from .config import BinConfig, GridConfig, Plane


def _loft_profile(
    planes: Tuple[Plane, ...],
    *,
    base_z: float,
    center: Tuple[float, float] = (0.0, 0.0),
) -> cq.Workplane:
    """Loft a square profile from its ordered ``planes``, bottom-up.

    This is the single CadQuery call chain behind the baseplate socket, the bin
    foot, and the stacking lip, so all three stay geometrically consistent by
    construction. The call chain is pinned exactly: one leading
    ``.workplane(offset=base_z)`` on a fresh ``cq.Workplane("XY")`` then the
    first rect (the first plane's z is folded into ``base_z``, never issued as a
    separate zero offset), one ``.workplane(offset=Δz).rect(...)`` per
    subsequent plane, one ``.loft(combine=True)``, and always one final
    ``.translate((cx, cy, 0))`` (a no-op translate is still emitted so socket,
    foot, and lip share an identical chain).
    """
    if planes[0].z != 0:
        raise ValueError("first profile plane must sit at z=0")

    size0 = planes[0].size
    wp = cq.Workplane("XY").workplane(offset=base_z).rect(size0, size0)
    for prev, plane in zip(planes, planes[1:]):
        wp = wp.workplane(offset=plane.z - prev.z).rect(plane.size, plane.size)
    return wp.loft(combine=True).translate((center[0], center[1], 0))


class PlateFeature(ABC):
    """A transformation applied to the plate solid."""

    @abstractmethod
    def apply(self, model: cq.Workplane, config: GridConfig) -> cq.Workplane:
        """Return a new solid with this feature applied."""
        raise NotImplementedError


def _cell_centers(config: GridConfig) -> Iterator[Tuple[int, int, float, float]]:
    """Yield (i, j, cx, cy) for every cell, centered on the origin."""
    for i in range(config.grid_x):
        for j in range(config.grid_y):
            cx = -config.width / 2 + (i + 0.5) * config.pitch
            cy = -config.length / 2 + (j + 0.5) * config.pitch
            yield i, j, cx, cy


class CellOpeningFeature(PlateFeature):
    """Cuts a cell opening in each cell.

    Two styles are supported (``config.opening_style``):

    * ``socket`` (default) reproduces the standard Gridfinity baseplate socket
      measured from the reference part: a 45 deg lead-in chamfer at the mouth,
      a straight vertical section, then a 45 deg chamfer down to the narrow
      bottom. This is what lets a bin foot seat and stay compatible across
      tiled plates.
    * ``taper`` is the legacy simple full-height draft funnel.

    When ``config.floor`` is 0 the opening punches fully through (open floor);
    otherwise it stops at the top of the floor, leaving a solid base.
    """

    def apply(self, model: cq.Workplane, config: GridConfig) -> cq.Workplane:
        for _i, _j, cx, cy in _cell_centers(config):
            model = model.cut(self._opening(cx, cy, config))
        return model

    def _opening(self, cx: float, cy: float, config: GridConfig) -> cq.Workplane:
        if config.opening_style == "socket":
            return self._socket_opening(cx, cy, config)
        return self._taper_opening(cx, cy, config)

    @staticmethod
    def _floor_top(config: GridConfig) -> float:
        """Z of the cut's lower limit: the top of the floor (0 if open)."""
        return config.floor

    @classmethod
    def _socket_opening(
        cls, cx: float, cy: float, config: GridConfig
    ) -> cq.Workplane:
        p = config.profile
        height = config.resolved_height
        floor_top = cls._floor_top(config)

        # The socket profile stacks from its narrow bottom up to the wide mouth
        # at the top face. Everything below the bottom chamfer is cut straight
        # down to the floor (or 1mm past the base for an open floor) so a bin
        # foot clears and the piece prints cleanly.
        mouth = p.mouth_opening
        bottom = p.bottom_opening

        z_prof_bot = height - p.total_height  # bottom of lower chamfer

        # Lofted socket from the shared profile: bottom (narrow) -> vertical
        # (top_opening) -> mouth (wide) at the top face. Using the shared
        # ``_loft_profile`` helper keeps the socket, foot, and lip in lockstep.
        socket = _loft_profile(
            p.profile_planes(), base_z=z_prof_bot, center=(cx, cy)
        )

        # Straight shaft from the floor top up to the bottom of the socket, at
        # the socket's narrowest size, so the whole opening is continuous.
        shaft_bottom = floor_top if config.floor > 0 else -1.0
        shaft_height = z_prof_bot - shaft_bottom
        parts = [socket]
        if shaft_height > 1e-6:
            shaft = (
                cq.Workplane("XY")
                .center(cx, cy)
                .box(bottom, bottom, shaft_height, centered=(True, True, False))
                .translate((0, 0, shaft_bottom))
            )
            parts.append(shaft)

        # Over-cut 1mm above the top face so the mouth punches cleanly.
        over_top = (
            cq.Workplane("XY")
            .center(cx, cy)
            .box(mouth, mouth, 1, centered=(True, True, False))
            .translate((0, 0, height))
        )
        parts.append(over_top)

        result = parts[0]
        for part in parts[1:]:
            result = result.union(part)
        return result

    @staticmethod
    def _taper_opening(cx: float, cy: float, config: GridConfig) -> cq.Workplane:
        height = config.resolved_height
        floor_top = config.floor
        top = config.pitch - config.wall  # Opening size at the top face
        span = height - floor_top          # Cut only above the floor

        if not config.taper.enabled:
            # Straight cut from the floor up, slightly over-tall at the top.
            box_h = span + 1 + (1 if config.floor == 0 else 0)
            z0 = floor_top - (1 if config.floor == 0 else 0)
            return (
                cq.Workplane("XY")
                .center(cx, cy)
                .box(top, top, box_h, centered=(True, True, False))
                .translate((0, 0, z0))
            )

        # Draft: shrink the bottom so walls lean outward toward the top.
        inset = 2 * span * math.tan(math.radians(config.taper.angle_deg))
        bottom = max(top - inset, 0.5)  # Never collapse the bottom to nothing

        solid = (
            cq.Workplane("XY")
            .workplane(offset=floor_top)
            .rect(bottom, bottom)
            .workplane(offset=span)
            .rect(top, top)
            .loft(combine=True)
            .translate((cx, cy, 0))
        )
        over_top = (
            cq.Workplane("XY")
            .center(cx, cy)
            .box(top, top, 1, centered=(True, True, False))
            .translate((0, 0, height))
        )
        result = solid.union(over_top)
        if config.floor == 0:
            over_bottom = (
                cq.Workplane("XY")
                .center(cx, cy)
                .box(bottom, bottom, 1, centered=(True, True, False))
                .translate((0, 0, -1))
            )
            result = result.union(over_bottom)
        return result


class MagnetPocketFeature(PlateFeature):
    """Magnet pockets, horizontal (edge) or vertical (bottom face).

    Horizontal pockets are drilled inward from the four outer edges so magnets
    pull neighbouring tiles together. Because a horizontal hole is an overhang,
    it prints oval unless shaped: the default ``teardrop`` shape adds a pointed
    roof (a printable overhang) above the circle so the bore stays round where
    the magnet seats. A ``round`` shape is available for comparison.

    Vertical pockets are drilled up into the bottom face (axis along Z); each
    layer is a flat circle, so they print perfectly round with no overhang.
    """

    def apply(self, model: cq.Workplane, config: GridConfig) -> cq.Workplane:
        if not config.magnet.enabled:
            return model
        if config.magnet.orientation == "horizontal":
            for origin, direction in self._horizontal_placements(config):
                model = model.cut(self._horizontal_pocket(origin, direction, config))
        else:
            for cx, cy in self._vertical_placements(config):
                model = model.cut(self._vertical_pocket(cx, cy, config))
        return model

    # --- horizontal (edge) pockets ----------------------------------------

    @staticmethod
    def _horizontal_placements(
        config: GridConfig,
    ) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
        """One placement per edge cell, on each of the four outer edges.

        A single generator for all four edges removes the near-duplicate loops
        the original script had (DRY).
        """
        z = config.resolved_height / 2
        placements: List[
            Tuple[Tuple[float, float, float], Tuple[float, float, float]]
        ] = []

        half_w, half_l = config.width / 2, config.length / 2

        # Bottom and top edges (vary X), pointing inward along Y.
        for i in range(config.grid_x):
            x = -half_w + (i + 0.5) * config.pitch
            placements.append(((x, -half_l, z), (0, 1, 0)))
            placements.append(((x, half_l, z), (0, -1, 0)))

        # Left and right edges (vary Y), pointing inward along X.
        for j in range(config.grid_y):
            y = -half_l + (j + 0.5) * config.pitch
            placements.append(((-half_w, y, z), (1, 0, 0)))
            placements.append(((half_w, y, z), (-1, 0, 0)))

        return placements

    @classmethod
    def _horizontal_pocket(
        cls,
        origin: Tuple[float, float, float],
        direction: Tuple[float, float, float],
        config: GridConfig,
    ) -> cq.Solid:
        m = config.magnet
        cylinder = cq.Solid.makeCylinder(
            m.bore_radius,
            m.pocket_depth,
            cq.Vector(*origin),
            cq.Vector(*direction),
        )
        if m.shape != "teardrop":
            return cylinder
        return cylinder.fuse(cls._teardrop_roof(origin, direction, config))

    @staticmethod
    def _teardrop_roof(
        origin: Tuple[float, float, float],
        direction: Tuple[float, float, float],
        config: GridConfig,
    ) -> cq.Solid:
        """A wedge above the bore whose apex points up (+Z).

        The roof is a triangular prism extruded along the pocket axis. Its base
        spans the bore diameter at the circle's horizontal mid-line and rises to
        a point above, so the printed overhang never exceeds the teardrop angle.
        """
        m = config.magnet
        r = m.bore_radius
        peak = r + m.teardrop_peak  # apex height above the bore center
        ox, oy, oz = origin
        dx, dy, dz = direction

        # Cross-section triangle in the plane perpendicular to the axis, defined
        # in (horizontal-tangent u, vertical z). Base at z=0 across the diameter,
        # apex at z=peak. The axis is horizontal, so u is the in-plane horizontal
        # tangent: perpendicular to both the axis and world Z.
        ux, uy = -dy, dx  # horizontal tangent (axis is in XY, so this is in XY)

        def pt(u: float, z: float) -> cq.Vector:
            return cq.Vector(ox + ux * u, oy + uy * u, oz + z)

        tri = [pt(-r, 0.0), pt(r, 0.0), pt(0.0, peak)]
        wire = cq.Wire.makePolygon(tri + [tri[0]])
        face = cq.Face.makeFromWires(wire)
        return cq.Solid.extrudeLinear(
            face, cq.Vector(dx, dy, dz) * m.pocket_depth
        )

    # --- vertical (bottom-face) pockets -----------------------------------

    @staticmethod
    def _vertical_placements(config: GridConfig) -> List[Tuple[float, float]]:
        """Pockets in the solid crossbars, offset from each cell center.

        A vertical pocket must land in material, not in a cell opening. We place
        four per cell, offset toward the cell corners by ``corner_offset`` so
        they sit in the crossbar/rim walls that surround each opening. This
        mirrors the Gridfinity convention of magnets near the base corners.
        """
        # Offset from a cell center to its magnet ring: just inside the wall so
        # the bore stays within the solid border around the opening.
        half_open = (config.pitch - config.wall) / 2
        offset = half_open + config.wall / 2 - config.magnet.bore_radius - 0.5
        offset = max(offset, 0.0)

        placements: List[Tuple[float, float]] = []
        for _i, _j, cx, cy in _cell_centers(config):
            for sx in (-1, 1):
                for sy in (-1, 1):
                    placements.append((cx + sx * offset, cy + sy * offset))
        return placements

    @staticmethod
    def _vertical_pocket(cx: float, cy: float, config: GridConfig) -> cq.Solid:
        m = config.magnet
        # Drill up from z=0 (bottom face) by the pocket depth.
        return cq.Solid.makeCylinder(
            m.bore_radius,
            m.pocket_depth,
            cq.Vector(cx, cy, 0.0),
            cq.Vector(0, 0, 1),
        )


class ConnectorFeature(PlateFeature):
    """Vertical dovetail connectors for tiling frames together.

    A female slot is cut into the +X and +Y outer edges; a male tab is added
    to the -X and -Y edges. Because both are generated from one profile helper,
    a tab on one tile mates the slot on the next by construction. The male tab
    is shrunk by ``clearance`` per side so it slides rather than jams.
    """

    def apply(self, model: cq.Workplane, config: GridConfig) -> cq.Workplane:
        if not config.connector.enabled:
            return model

        half_w, half_l = config.width / 2, config.length / 2

        # Each edge is described by its midpoint and its outward normal. A slot
        # digs inward (opposite the normal); a tab grows outward (along it), so
        # the tab on one tile's -X edge mates the slot on its neighbour's +X.
        edges = {
            # edge:   (center,          outward normal)
            "+x": ((half_w, 0.0), (1.0, 0.0)),
            "+y": ((0.0, half_l), (0.0, 1.0)),
            "-x": ((-half_w, 0.0), (-1.0, 0.0)),
            "-y": ((0.0, -half_l), (0.0, -1.0)),
        }

        # Female slots on +X and +Y; male tabs on -X and -Y.
        for edge in ("+x", "+y"):
            center, normal = edges[edge]
            model = model.cut(self._dovetail(config, center, normal, male=False))
        for edge in ("-x", "-y"):
            center, normal = edges[edge]
            model = model.union(self._dovetail(config, center, normal, male=True))
        return model

    @staticmethod
    def _dovetail(
        config: GridConfig,
        center: Tuple[float, float],
        outward: Tuple[float, float],
        male: bool,
    ) -> cq.Workplane:
        """Build one dovetail prism (trapezoid extruded through the height).

        ``outward`` is the edge's outward unit normal. A male tab extrudes along
        it (projecting past the edge); a female slot extrudes against it (biting
        into the wall). The trapezoid is narrow at the mouth (the edge line) and
        wide at depth, so a tab locks into a slot. Sharing one profile keeps tab
        and slot complementary by construction.
        """
        c = config.connector
        depth = c.depth
        # Male tab is undersized per side for a sliding fit; slot stays nominal.
        shrink = c.clearance if male else 0.0
        half_mouth = (c.width - 2 * shrink) / 2
        half_inner = (c.inner_width - 2 * shrink) / 2
        cx, cy = center
        nx, ny = outward
        height = config.resolved_height

        # A tab points outward (+depth); a slot points inward (-depth).
        reach = depth if male else -depth
        # Edge-tangent unit vector (perpendicular to the normal) runs along u.
        tx, ty = -ny, nx

        # Local trapezoid points as (u along edge, v along normal direction).
        pts_local = [
            (-half_mouth, 0.0),
            (half_mouth, 0.0),
            (half_inner, reach),
            (-half_inner, reach),
        ]
        world_pts = [
            (cx + tx * u + nx * v, cy + ty * u + ny * v) for u, v in pts_local
        ]

        return (
            cq.Workplane("XY")
            .polyline(world_pts)
            .close()
            .extrude(height)
        )


class GridfinityPlate:
    """Builds a Gridfinity frame solid from a :class:`GridConfig`."""

    def __init__(self, config: GridConfig, features: List[PlateFeature] | None = None):
        self.config = config
        # Default feature pipeline; callers may inject their own ordering.
        # Connectors run last so tabs attach to the finished outer wall.
        self.features = features or [
            CellOpeningFeature(),
            MagnetPocketFeature(),
            ConnectorFeature(),
        ]

    def build(self) -> cq.Workplane:
        model = cq.Workplane("XY").box(
            self.config.width,
            self.config.length,
            self.config.resolved_height,
            centered=(True, True, False),
        )
        for feature in self.features:
            model = feature.apply(model, self.config)
        return model


# =========================================================================
# Gridfinity bin builder
# =========================================================================


class BinFeature(ABC):
    """A transformation applied to the bin solid.

    A sibling of :class:`PlateFeature` typed against :class:`BinConfig` rather
    than :class:`GridConfig`, so each builder's feature list stays type-correct
    and self-documenting. Adding a bin feature means adding a class.
    """

    @abstractmethod
    def apply(self, model: cq.Workplane, config: BinConfig) -> cq.Workplane:
        """Return a new solid with this feature applied."""
        raise NotImplementedError


def _bin_cell_centers(config: BinConfig) -> Iterator[Tuple[int, int, float, float]]:
    """Yield (i, j, cx, cy) for every bin cell, centered on the origin.

    Foot centers use the full ``grid*pitch`` PITCH lattice (NOT the undersized
    bin ``width = grid_x*pitch - 0.5``) so a multi-cell bin's feet register with
    the plate's sockets, which sit on the pitch lattice.
    """
    for i in range(config.grid_x):
        for j in range(config.grid_y):
            cx = -config.grid_x * config.pitch / 2 + (i + 0.5) * config.pitch
            cy = -config.grid_y * config.pitch / 2 + (j + 0.5) * config.pitch
            yield i, j, cx, cy


class BinBodyFeature(BinFeature):
    """The outer body box, spanning z=base_height..total_height.

    MUST be the first feature: ``GridfinityBin.build`` seeds an empty workplane,
    so this feature disregards the (empty) incoming model and returns a freshly
    built box. Every later feature unions/cuts onto a non-empty solid.
    """

    def apply(self, model: cq.Workplane, config: BinConfig) -> cq.Workplane:
        return (
            cq.Workplane("XY")
            .box(
                config.width,
                config.length,
                config.body_height,
                centered=(True, True, False),
            )
            .translate((0, 0, config.base_height))
        )


class BinFootFeature(BinFeature):
    """The foot plug under each cell: the socket's solid mate.

    The foot shares the socket's z orientation (narrow at low z, wide at high
    z); it is the socket's SOLID complement, not a z-flipped profile. Lofted
    over z=0..profile.total_height at each pitch-lattice cell center, its top
    ``base_overlap`` is buried in the body so only ``base_height`` protrudes to
    plug into the socket.
    """

    def apply(self, model: cq.Workplane, config: BinConfig) -> cq.Workplane:
        planes = config.profile.foot_planes(config.foot_clearance)
        for _i, _j, cx, cy in _bin_cell_centers(config):
            foot = _loft_profile(planes, base_z=0.0, center=(cx, cy))
            model = model.union(foot)
        return model


class HollowInteriorFeature(BinFeature):
    """Cuts the open-top cavity from ``cavity_bottom`` up through the mouth.

    The cut box is ``inner_width x inner_length`` and runs from
    ``config.cavity_bottom`` (= max(floor, base_height)) up to the top face
    plus a 1 mm over-cut so the mouth punches cleanly. The lip sits above
    ``total_height`` so the cavity cut never touches it.
    """

    def apply(self, model: cq.Workplane, config: BinConfig) -> cq.Workplane:
        bottom = config.cavity_bottom
        height = config.total_height - bottom + 1.0  # +1 mm over-cut
        cavity = (
            cq.Workplane("XY")
            .box(
                config.inner_width,
                config.inner_length,
                height,
                centered=(True, True, False),
            )
            .translate((0, 0, bottom))
        )
        return model.cut(cavity)


def _rect_loft(
    sizes: Tuple[Tuple[float, float, float], ...],
    *,
    base_z: float,
    center: Tuple[float, float] = (0.0, 0.0),
) -> cq.Workplane:
    """Loft a rectangular profile from ordered ``(z, w, l)`` planes, bottom-up.

    The rectangular sibling of :func:`_loft_profile` (which lofts squares). The
    perimeter stacking-lip opening is not square -- a 2x1 bin's interior is
    ~81 x 39 mm -- so the lip's rectangular socket cross-section is swept with
    this helper. The call chain mirrors ``_loft_profile``: one leading
    ``.workplane(offset=base_z)`` then one ``.rect`` per plane, a single
    ``.loft(combine=True)``, and a final ``.translate``.
    """
    z0, w0, l0 = sizes[0]
    if z0 != 0:
        raise ValueError("first profile plane must sit at z=0")
    wp = cq.Workplane("XY").workplane(offset=base_z).rect(w0, l0)
    for (pz, _pw, _pl), (z, w, l) in zip(sizes, sizes[1:]):
        wp = wp.workplane(offset=z - pz).rect(w, l)
    return wp.loft(combine=True).translate((center[0], center[1], 0))


class StackingLipFeature(BinFeature):
    """An additive perimeter rim that mirrors the Gridfinity socket cross-section.

    Entirely additive above z=total_height: a solid rim ring (outer =
    width x length) occupies z=total_height..total_height+lip_h, and a
    rectangular socket-shaped cavity -- swept around the WHOLE perimeter rather
    than stamped once in the center -- is cut from it. The cavity opening spans
    nearly the full interior footprint (close to inner_width x inner_length), so
    the bin is genuinely open-top across its whole footprint, not capped by a
    solid deck with one small hole.

    The rim steps inward from the outer wall to form a seating ledge, exactly
    the socket cross-section seen around the perimeter: narrow seat at the
    bottom, a straight vertical section, then a flared mouth at the top face.
    Because the seat is reached by stepping in ``chamfer_top`` from the wider
    mouth, a stacked bin's base seats on the ledge the same way a foot seats in
    a plate socket. The vertical seating run (``straight`` + ``chamfer_top``)
    comes straight from the shared :class:`GridfinityProfile`, keeping the
    baseplate socket, the bin foot, and the bin lip in lockstep (DRY).

    Self-skips when the config disables the lip. Runs last so it attaches to the
    finished wall.
    """

    def apply(self, model: cq.Workplane, config: BinConfig) -> cq.Workplane:
        if not config.stacking_lip:
            return model
        return model.union(self.lip_solid(config))

    @staticmethod
    def lip_solid(config: BinConfig) -> cq.Workplane:
        """The lip rim (outer ring minus the perimeter socket cavity).

        Built in world coordinates so :meth:`GridfinityBin.build_split` can hand
        back a lip that is already aligned to the body at z=total_height.
        """
        p = config.profile
        z0 = config.total_height
        ring = (
            cq.Workplane("XY")
            .box(
                config.width,
                config.length,
                config.lip_h,
                centered=(True, True, False),
            )
            .translate((0, 0, z0))
        )
        # The perimeter socket cavity, bottom-up over z=0..lip_h:
        #   * seat (narrowest) at the bottom, held across the straight run,
        #   * flared mouth (widest) at the top face.
        # The mouth leaves ``lip_wall`` of rim at the top on every side; the
        # seat steps in a further ``chamfer_top`` per side, which is the ledge a
        # stacked bin's base drops onto. Both axes are offset from the full
        # footprint, so the opening tracks the interior (~inner_width x
        # inner_length) instead of a single centered hole.
        mouth_w = config.width - 2 * config.lip_wall
        mouth_l = config.length - 2 * config.lip_wall
        seat_w = mouth_w - 2 * p.chamfer_top
        seat_l = mouth_l - 2 * p.chamfer_top
        sizes = (
            (0.0, seat_w, seat_l),
            (p.straight, seat_w, seat_l),
            (config.lip_h, mouth_w, mouth_l),
        )
        cavity = _rect_loft(sizes, base_z=z0, center=(0.0, 0.0))
        # Over-cut 1 mm above the ring top so the mouth punches cleanly.
        over_top = (
            cq.Workplane("XY")
            .box(mouth_w, mouth_l, 1.0, centered=(True, True, False))
            .translate((0, 0, z0 + config.lip_h))
        )
        return ring.cut(cavity).cut(over_top)


class GridfinityBin:
    """Builds a hollow open-top Gridfinity bin solid from a :class:`BinConfig`."""

    def __init__(self, config: BinConfig, features: List[BinFeature] | None = None):
        self.config = config
        # Default pipeline. BinBodyFeature MUST stay first (it builds the body
        # from an empty seed); every later feature unions/cuts onto it. The lip
        # feature self-skips when stacking_lip is False.
        self.features = features or [
            BinBodyFeature(),
            BinFootFeature(),
            HollowInteriorFeature(),
            StackingLipFeature(),
        ]

    def build(self) -> cq.Workplane:
        """Full bin: body + foot + hollow interior + optional lip."""
        model = cq.Workplane("XY")
        for feature in self.features:
            model = feature.apply(model, self.config)
        return model

    def build_split(self) -> Tuple[cq.Workplane, cq.Workplane]:
        """Return (body_without_lip, lip) split along the z=total_height plane.

        The body runs the pipeline with :class:`StackingLipFeature` omitted; the
        lip is built standalone in world coordinates so the two meshes load
        pre-aligned. Raises ``ValueError`` when there is no lip to split.
        """
        if not self.config.stacking_lip:
            raise ValueError("no stacking lip to split")
        body_features = [
            f for f in self.features if not isinstance(f, StackingLipFeature)
        ]
        body = cq.Workplane("XY")
        for feature in body_features:
            body = feature.apply(body, self.config)
        lip = StackingLipFeature.lip_solid(self.config)
        return body, lip
