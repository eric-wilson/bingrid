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

from .config import GridConfig


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
    """Cuts a through-opening in each cell, optionally with a draft angle.

    With a non-zero taper the opening is narrower at the bottom and wider at
    the top, forming a lead-in funnel. With zero taper the walls are straight.
    """

    def apply(self, model: cq.Workplane, config: GridConfig) -> cq.Workplane:
        for _i, _j, cx, cy in _cell_centers(config):
            model = model.cut(self._opening(cx, cy, config))
        return model

    @staticmethod
    def _opening(cx: float, cy: float, config: GridConfig) -> cq.Workplane:
        height = config.resolved_height
        top = config.pitch - config.wall  # Opening size at the top face

        if not config.taper.enabled:
            # Straight through-cut, slightly over-tall so it punches cleanly.
            return (
                cq.Workplane("XY")
                .center(cx, cy)
                .box(top, top, height + 2, centered=(True, True, False))
                .translate((0, 0, -1))
            )

        # Draft: shrink the bottom so walls lean outward toward the top.
        inset = 2 * height * math.tan(math.radians(config.taper.angle_deg))
        bottom = max(top - inset, 0.5)  # Never collapse the bottom to nothing

        # Build a lofted prism from the bottom rectangle up to the top one, then
        # extend 1 mm past each face so the cut punches fully through.
        solid = (
            cq.Workplane("XY")
            .rect(bottom, bottom)
            .workplane(offset=height)
            .rect(top, top)
            .loft(combine=True)
            .translate((cx, cy, 0))
        )
        over_bottom = (
            cq.Workplane("XY")
            .center(cx, cy)
            .box(bottom, bottom, 1, centered=(True, True, False))
            .translate((0, 0, -1))
        )
        over_top = (
            cq.Workplane("XY")
            .center(cx, cy)
            .box(top, top, 1, centered=(True, True, False))
            .translate((0, 0, height))
        )
        return solid.union(over_bottom).union(over_top)


class MagnetPocketFeature(PlateFeature):
    """Blind horizontal magnet pockets drilled inward from all four edges."""

    def apply(self, model: cq.Workplane, config: GridConfig) -> cq.Workplane:
        if not config.magnet.enabled:
            return model
        for origin, direction in self._pocket_placements(config):
            model = model.cut(self._pocket(origin, direction, config))
        return model

    @staticmethod
    def _pocket_placements(
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

    @staticmethod
    def _pocket(
        origin: Tuple[float, float, float],
        direction: Tuple[float, float, float],
        config: GridConfig,
    ) -> cq.Solid:
        return cq.Solid.makeCylinder(
            config.magnet.bore_radius,
            config.magnet.pocket_depth,
            cq.Vector(*origin),
            cq.Vector(*direction),
        )


class GridfinityPlate:
    """Builds a Gridfinity frame solid from a :class:`GridConfig`."""

    def __init__(self, config: GridConfig, features: List[PlateFeature] | None = None):
        self.config = config
        # Default feature pipeline; callers may inject their own ordering.
        self.features = features or [CellOpeningFeature(), MagnetPocketFeature()]

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
