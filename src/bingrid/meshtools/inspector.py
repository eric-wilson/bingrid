"""Mesh inspection built on trimesh.

``MeshInspector`` wraps a loaded mesh and exposes the measurements that matter
when reverse-engineering a physical part: overall size, volume, and how the
cross-section changes along an axis (which reveals chamfers, drafts, and
straight sections).

Design notes:
    * trimesh does the heavy lifting (loading, sectioning, 2D polygon math) so
      we do not re-implement mesh algorithms.
    * The class holds a mesh centered at the XY origin with its base at z=0,
      which makes slice coordinates easy to reason about.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import trimesh


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


@dataclass(frozen=True)
class SliceProfile:
    """One cross-section perpendicular to an axis.

    Attributes:
        position: coordinate along the slice axis.
        outer: (width, depth) bounding extent of the section, in the two axes
            orthogonal to the slice axis.
        solid_area: total filled area of the section.
        hole_count: number of interior holes (enclosed voids) in the section.
        hole_extents: bounding (width, depth) of each interior hole.
    """

    position: float
    outer: Tuple[float, float]
    solid_area: float
    hole_count: int
    hole_extents: Tuple[Tuple[float, float], ...]


class MeshInspector:
    """Loads a mesh and answers geometric questions about it."""

    def __init__(self, mesh: trimesh.Trimesh, *, normalize: bool = True):
        if isinstance(mesh, trimesh.Scene):
            mesh = mesh.dump(concatenate=True)
        self.mesh = mesh
        if normalize:
            self._normalize()

    @classmethod
    def load(cls, path: str | Path, *, normalize: bool = True) -> "MeshInspector":
        mesh = trimesh.load(str(path))
        return cls(mesh, normalize=normalize)

    def _normalize(self) -> None:
        """Center in XY and drop the base to z=0 for readable slice coords."""
        bounds = self.mesh.bounds
        cx = (bounds[0][0] + bounds[1][0]) / 2
        cy = (bounds[0][1] + bounds[1][1]) / 2
        self.mesh.apply_translation([-cx, -cy, -bounds[0][2]])

    # --- summary -----------------------------------------------------------

    @property
    def extents(self) -> Tuple[float, float, float]:
        e = self.mesh.extents
        return (float(e[0]), float(e[1]), float(e[2]))

    @property
    def bounds(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        b = self.mesh.bounds
        return (tuple(map(float, b[0])), tuple(map(float, b[1])))

    @property
    def volume(self) -> float:
        return float(self.mesh.volume)

    @property
    def is_watertight(self) -> bool:
        return bool(self.mesh.is_watertight)

    # --- cross-section profiling ------------------------------------------

    def slice_at(self, position: float, axis: str = "z") -> Optional[SliceProfile]:
        """Measure a single cross-section at ``position`` along ``axis``."""
        idx = _AXIS_INDEX[axis]
        normal = [0.0, 0.0, 0.0]
        normal[idx] = 1.0
        origin = [0.0, 0.0, 0.0]
        origin[idx] = position

        section = self.mesh.section(plane_origin=origin, plane_normal=normal)
        if section is None:
            return None
        planar, _ = section.to_2D()

        # ``polygons_full`` needs trimesh's optional 2D extras (shapely, rtree).
        # If they are missing or the section is degenerate, treat the slice as
        # empty rather than crashing the whole sweep.
        try:
            polygons = planar.polygons_full
        except BaseException:  # trimesh raises a lazily-constructed ImportError
            return None
        if not polygons:
            return None

        b = planar.bounds
        outer = (float(b[1][0] - b[0][0]), float(b[1][1] - b[0][1]))
        solid_area = float(sum(p.area for p in polygons))

        hole_extents: List[Tuple[float, float]] = []
        for poly in polygons:
            for ring in poly.interiors:
                xs, ys = ring.xy
                hole_extents.append((float(max(xs) - min(xs)),
                                     float(max(ys) - min(ys))))

        return SliceProfile(
            position=float(position),
            outer=outer,
            solid_area=solid_area,
            hole_count=len(hole_extents),
            hole_extents=tuple(hole_extents),
        )

    def profile(
        self,
        axis: str = "z",
        step: float = 0.25,
        margin: float = 0.05,
        positions: Optional[Sequence[float]] = None,
    ) -> List[SliceProfile]:
        """Sample cross-sections along ``axis`` from base to top.

        ``step`` sets the sampling interval; ``margin`` keeps slices off the
        exact end faces (where a section can be degenerate). Pass explicit
        ``positions`` to override the automatic sweep.
        """
        idx = _AXIS_INDEX[axis]
        lo = self.mesh.bounds[0][idx]
        hi = self.mesh.bounds[1][idx]

        if positions is None:
            start, end = lo + margin, hi - margin
            if end <= start:
                positions = [(lo + hi) / 2]
            else:
                n = max(int((end - start) / step) + 1, 2)
                positions = list(np.linspace(start, end, n))

        results = []
        for pos in positions:
            prof = self.slice_at(pos, axis=axis)
            if prof is not None:
                results.append(prof)
        return results
