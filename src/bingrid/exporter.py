"""Model export: turns a built solid into STL/STEP files on disk.

Separated from geometry so the builder stays I/O-free and the file-naming
convention lives in exactly one place (DRY / Single Responsibility).
"""
from __future__ import annotations

import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import List
from xml.sax.saxutils import quoteattr

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

    def export_3mf_painted(
        self,
        model: cq.Workplane,
        config: BinConfig,
        name: str | None = None,
    ) -> List[Path]:
        """Export the single bin solid as a Bambu-compatible painted ``.3mf``.

        The whole bin is ONE mesh. A horizontal band of the outer wall
        (``config.color_band_start .. config.color_band_top`` in part z) is
        painted to a second filament/extruder via a Bambu per-triangle
        ``paint_color`` attribute, the way a real Gridfinity bin paints its
        colored rim. The base object is filament/extruder 1; band faces carry
        ``paint_color="8"`` (extruder 2). This is the single-mesh alternative to
        the two-body :meth:`export_3mf`.

        Algorithm:

        1. Tessellate the solid to a trimesh mesh through a temp STL (same
           tolerances as the STL output, so surface quality matches).
        2. Slice the mesh at the two band z-planes so NO triangle spans a band
           boundary: for each plane, split into the pieces below and above and
           concatenate them back. Faces that crossed a plane get subdivided
           along it; the closed solid is preserved.
        3. Classify each face by centroid z; faces whose centroid falls inside
           the band get the simple whole-face paint code. Because slicing
           removed every straddling triangle, centroid and all-vertex
           classification agree, so each band face is just ``paint_color="8"``.
        4. Write the OPC (zip) ``.3mf`` by hand (:meth:`_write_painted_3mf`):
           trimesh's generic 3MF writer emits neither Bambu ``paint_color`` nor
           ``Metadata/model_settings.config``, so it cannot carry the band.

        The writer itself uses only stdlib ``zipfile`` / ElementTree-free string
        XML + ``uuid``; trimesh is used only to tessellate and slice.
        """
        import numpy as np
        import trimesh

        self.output_dir.mkdir(parents=True, exist_ok=True)
        base = name or self.bin_default_name(config)
        out_path = self.output_dir / f"{base}.3mf"

        with tempfile.TemporaryDirectory() as tmp:
            stl_tmp = Path(tmp) / "painted.stl"
            cq.exporters.export(
                model,
                str(stl_tmp),
                tolerance=self.stl_tolerance,
                angularTolerance=self.stl_angular_tolerance,
            )
            mesh = trimesh.load(str(stl_tmp), force="mesh")

        b0 = config.resolved_color_band_start
        b1 = config.color_band_top
        mesh = self._slice_at_z(trimesh, mesh, b0)
        mesh = self._slice_at_z(trimesh, mesh, b1)

        # Weld coincident vertices BEFORE classifying/writing. Slicing +
        # concatenate leaves two independent vertex pools, so every seam vertex
        # (and every vertex each half already had) exists twice: adjacent
        # triangles across a seam reference different-but-coincident indices.
        # trimesh.load merges these on load so is_watertight reports true, but
        # Bambu's strict manifold check does NOT weld and sees each such shared
        # edge as two boundary (open) edges. merge_vertices() collapses the
        # coincident duplicates into one shared pool and process() normalizes
        # winding, so the emitted mesh matches a real single-pool Bambu mesh.
        # Classification MUST run after this, since welding changes the face
        # indices and vertex count.
        mesh.merge_vertices()
        mesh.process(validate=True)

        # Classify by face-centroid z. After the two slices no triangle spans a
        # boundary, so centroid classification matches the all-vertex test.
        eps = 1e-6
        centroid_z = np.asarray(mesh.triangles_center)[:, 2]
        in_band = (centroid_z >= b0 - eps) & (centroid_z <= b1 + eps)

        # Post-slice consistency guard: every face lies wholly on one side of
        # each plane (all three vertices classify the same as the centroid).
        tri_z = np.asarray(mesh.triangles)[:, :, 2]
        vert_in = (tri_z >= b0 - eps) & (tri_z <= b1 + eps)
        assert np.array_equal(vert_in.all(axis=1), in_band), (
            "slice left a triangle straddling a band boundary"
        )

        # Bambu whole-face paint code: filament/extruder N -> (N << 2) in hex.
        # The unpainted base is filament 1 (no attribute); filament 2 -> 2<<2 =
        # 0b1000 -> "8" (the simple whole-face code this exporter emits).
        paint_code = format(config.color_band_extruder << 2, "X")

        self._write_painted_3mf(
            out_path,
            vertices=np.asarray(mesh.vertices, dtype=float),
            faces=np.asarray(mesh.faces, dtype=int),
            in_band=in_band,
            paint_code=paint_code,
            object_name=base,
        )
        return [out_path]

    @staticmethod
    def _slice_at_z(trimesh, mesh, z: float):
        """Return a copy of ``mesh`` with faces split along the plane z=``z``.

        Keeps the WHOLE closed solid (not a clip): slice once keeping the part
        at or above the plane and once keeping the part at or below it (both
        uncapped), then concatenate. Faces crossing z=``z`` are subdivided along
        the plane; faces already on one side are preserved unchanged.
        """
        upper = trimesh.intersections.slice_mesh_plane(
            mesh, plane_normal=[0, 0, 1], plane_origin=[0, 0, z], cap=False
        )
        lower = trimesh.intersections.slice_mesh_plane(
            mesh, plane_normal=[0, 0, -1], plane_origin=[0, 0, z], cap=False
        )
        return trimesh.util.concatenate([lower, upper])

    @staticmethod
    def _write_painted_3mf(
        out_path: Path,
        vertices,
        faces,
        in_band,
        paint_code: str,
        object_name: str,
    ) -> None:
        """Write the minimal valid Bambu painted ``.3mf`` OPC package.

        Parts written:

        * ``[Content_Types].xml`` / ``_rels/.rels`` — standard OPC plumbing.
        * ``3D/3dmodel.model`` — one object with an inline mesh; in-band
          triangles carry ``paint_color`` = ``paint_code``; one build item.
        * ``Metadata/model_settings.config`` — the object with base
          ``extruder="1"`` and a single part, so the file loads mesh + paint
          without the "invalid config" warning. No print/printer profile is
          written (that is version-sensitive and the user applies their own).
        """
        name_attr = quoteattr(object_name)
        obj_uuid = str(uuid.uuid4())
        part_uuid = str(uuid.uuid4())
        build_uuid = str(uuid.uuid4())
        item_uuid = str(uuid.uuid4())
        face_count = len(faces)

        verts_xml = "".join(
            f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>'
            for x, y, z in vertices
        )
        tri_parts = []
        for i, (v1, v2, v3) in enumerate(faces):
            paint = f' paint_color="{paint_code}"' if bool(in_band[i]) else ""
            tri_parts.append(f'<triangle v1="{v1}" v2="{v2}" v3="{v3}"{paint}/>')
        tris_xml = "".join(tri_parts)

        model_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">\n'
            ' <metadata name="Application">bingrid</metadata>\n'
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
            ' <resources>\n'
            f'  <object id="1" p:UUID="{obj_uuid}" type="model">\n'
            '   <mesh>\n'
            f'    <vertices>{verts_xml}</vertices>\n'
            f'    <triangles>{tris_xml}</triangles>\n'
            '   </mesh>\n'
            '  </object>\n'
            ' </resources>\n'
            f' <build p:UUID="{build_uuid}">\n'
            f'  <item objectid="1" p:UUID="{item_uuid}" '
            'transform="1 0 0 0 1 0 0 0 1 0 0 0" printable="1"/>\n'
            ' </build>\n'
            '</model>\n'
        )

        settings_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<config>\n'
            '  <object id="1">\n'
            f'    <metadata key="name" value={name_attr}/>\n'
            '    <metadata key="extruder" value="1"/>\n'
            f'    <metadata face_count="{face_count}"/>\n'
            f'    <part id="1" subtype="normal_part" uuid="{part_uuid}">\n'
            f'      <metadata key="name" value={name_attr}/>\n'
            '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            '    </part>\n'
            '  </object>\n'
            '</config>\n'
        )

        content_types = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
            '</Types>\n'
        )

        rels = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            '</Relationships>\n'
        )

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", rels)
            zf.writestr("3D/3dmodel.model", model_xml)
            zf.writestr("Metadata/model_settings.config", settings_xml)
