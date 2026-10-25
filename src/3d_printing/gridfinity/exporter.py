"""Model export: turns a built solid into STL/STEP files on disk.

Separated from geometry so the builder stays I/O-free and the file-naming
convention lives in exactly one place (DRY / Single Responsibility).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import cadquery as cq

from .config import GridConfig


class ModelExporter:
    """Writes a solid to STL and STEP using a config-derived file name."""

    def __init__(
        self,
        output_dir: Path,
        stl_tolerance: float = 0.05,
        stl_angular_tolerance: float = 0.15,
    ):
        self.output_dir = Path(output_dir)
        self.stl_tolerance = stl_tolerance
        self.stl_angular_tolerance = stl_angular_tolerance

    def default_name(self, config: GridConfig) -> str:
        """Descriptive, reproducible base file name from the config."""
        floor_tag = "floor" if config.floor > 0 else "open"
        name = f"gridfinity_{config.grid_x}x{config.grid_y}_{floor_tag}"
        if config.opening_style == "socket":
            name += "_socket"
        elif config.taper.enabled:
            name += f"_taper{config.taper.angle_deg}"
        if config.magnet.enabled:
            name += f"_mag_{config.magnet.diameter}x{config.magnet.depth}"
            if config.magnet.orientation == "vertical":
                name += "_vmag"
            elif config.magnet.shape == "round":
                name += "_round"
        if config.connector.enabled:
            name += "_connect"
        return name

    def export(
        self,
        model: cq.Workplane,
        config: GridConfig,
        name: str | None = None,
    ) -> List[Path]:
        """Export STL and STEP; returns the paths written."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        base = name or self.default_name(config)

        stl_path = self.output_dir / f"{base}.stl"
        step_path = self.output_dir / f"{base}.step"

        cq.exporters.export(
            model,
            str(stl_path),
            tolerance=self.stl_tolerance,
            angularTolerance=self.stl_angular_tolerance,
        )
        cq.exporters.export(model, str(step_path))
        return [stl_path, step_path]
