"""Model export: turns a built solid into STL/STEP files on disk.

Separated from geometry so the builder stays I/O-free and the file-naming
convention lives in exactly one place (DRY / Single Responsibility).
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

import cadquery as cq

from .config import BinConfig, GridConfig


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

    def bin_default_name(self, config: BinConfig) -> str:
        """Descriptive, reproducible base file name for a bin config.

        A separate method (not an overload of ``default_name``) so the plate
        path stays byte-stable. Pattern: ``bin_{x}x{y}_u{units}`` + ``_lip`` /
        ``_nolip`` + ``_floor{floor}`` (float form, e.g. ``floor1.0``) only when
        ``floor > 0``; the ``_floor`` tag is omitted entirely when floor == 0.
        """
        name = f"bin_{config.grid_x}x{config.grid_y}_u{config.height_units}"
        name += "_lip" if config.stacking_lip else "_nolip"
        if config.floor > 0:
            name += f"_floor{config.floor}"
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

    def export_split(
        self,
        body: cq.Workplane,
        lip: cq.Workplane,
        config: BinConfig,
        name: str | None = None,
    ) -> List[Path]:
        """Export the bin body and lip as SEPARATE STL meshes.

        Writes ``{base}_body.stl`` + ``{base}_lip.stl`` (STL is per-body) plus a
        combined ``{base}.step`` for reference. Returns the paths written.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        base = name or self.bin_default_name(config)

        body_path = self.output_dir / f"{base}_body.stl"
        lip_path = self.output_dir / f"{base}_lip.stl"
        step_path = self.output_dir / f"{base}.step"

        cq.exporters.export(
            body,
            str(body_path),
            tolerance=self.stl_tolerance,
            angularTolerance=self.stl_angular_tolerance,
        )
        cq.exporters.export(
            lip,
            str(lip_path),
            tolerance=self.stl_tolerance,
            angularTolerance=self.stl_angular_tolerance,
        )
        cq.exporters.export(body.union(lip), str(step_path))
        return [body_path, lip_path, step_path]

    def export_3mf(
        self,
        body: cq.Workplane,
        lip: cq.Workplane,
        config: BinConfig,
        name: str | None = None,
    ) -> List[Path]:
        """Export the bin body and lip as TWO named bodies in ONE ``.3mf``.

        Writes a single ``{base}.3mf`` 3D Manufacturing Format package holding
        two separate, pre-aligned bodies named ``body`` and ``lip``. Opened in a
        slicer (Bambu Studio / OrcaSlicer) the parts arrive already separated and
        aligned, ready for per-body filament assignment — the single-file
        alternative to the dual-STL :meth:`export_split`.

        CadQuery 2.8 cannot emit ``.3mf`` itself, so each solid is tessellated to
        a mesh via trimesh (reusing the exporter's STL tolerance so surface
        quality matches the STL output) and the two named meshes are written with
        trimesh's 3MF writer. Both bodies share the bin origin, so they load
        pre-aligned (the lip sits exactly on top of the body).

        trimesh's 3MF writer needs ``lxml`` (declared in ``requirements.txt``);
        importing trimesh here keeps the heavy dependency out of the import path
        of the STL/STEP exporters.
        """
        import trimesh

        self.output_dir.mkdir(parents=True, exist_ok=True)
        base = name or self.bin_default_name(config)
        out_path = self.output_dir / f"{base}.3mf"

        # Tessellate each solid through a temp STL (same tolerances as the STL
        # output) and load it as a trimesh mesh, then clean the temp files up.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            scene = trimesh.Scene()
            for geom_name, solid in (("body", body), ("lip", lip)):
                stl_tmp = tmp_dir / f"{geom_name}.stl"
                cq.exporters.export(
                    solid,
                    str(stl_tmp),
                    tolerance=self.stl_tolerance,
                    angularTolerance=self.stl_angular_tolerance,
                )
                mesh = trimesh.load(str(stl_tmp), force="mesh")
                scene.add_geometry(mesh, geom_name=geom_name)
            scene.export(str(out_path))

        return [out_path]
