# Two-color `.3mf` export — shipped

**Status:** ✅ shipped.

## Goal

Export a bin's body and stacking lip as a SINGLE `.3mf` file containing two
separate bodies/objects, pre-aligned, so a slicer (Bambu Studio / OrcaSlicer)
opens one file with both parts already separated and ready for per-part filament
assignment — no manual "add part / assemble" step.

This is the nicer version of the existing `--split-lip` dual-STL export (see
[baseplate-and-bins.md](baseplate-and-bins.md)), which requires the user to
combine two STLs by hand in the slicer.

## The `--3mf` flag

```bash
# from src/
python -m bingrid.bin --x 2 --y 1 --units 5 --stacking-lip --3mf
# writes one bin_2x1_u5_lip_floor1.0.3mf holding two bodies: "body" + "lip"
```

- `--3mf` requires the stacking lip. `--3mf --no-stacking-lip` is an error and
  exits with code 2, mirroring the `--split-lip` guard.
- `--3mf` and `--split-lip` are independent and may be combined. With both set,
  the run writes the two STLs (`..._body.stl`, `..._lip.stl`) plus the combined
  `..._.step` AND the single `..._.3mf`. With only `--3mf`, just the `.3mf` is
  written.
- Both bodies share the bin origin, so they load pre-aligned: the lip sits
  exactly on top of the body at `total_height` (e.g. body z=[0, 38.8], lip
  z=[38.8, 42.75] for a `--units 5` bin), same XY footprint.

## Mechanism (trimesh, not CadQuery)

CadQuery 2.8 cannot export `.3mf` (`Assembly.export()` only supports
STEP/XML/XBF/GLTF/VTKJS/VRML/STL; `exportType="3MF"` raises `ValueError: Unknown
format: 3MF`). The `.3mf` is instead written with **trimesh**:

1. `GridfinityBin.build_split()` returns the body and lip already aligned in
   world coordinates at `z=total_height`.
2. `ModelExporter.export_3mf()` tessellates each solid to a mesh by exporting a
   temporary STL with the exporter's STL tolerance (`stl_tolerance=0.05`,
   `stl_angular_tolerance=0.15`) so surface quality matches the STL output, then
   loads it with `trimesh.load(..., force="mesh")`.
3. Both meshes are added to a `trimesh.Scene` under distinct geometry names
   (`body`, `lip`) and `scene.export(path)` writes the `.3mf`. The temp STLs are
   removed afterward.

Reloading the file with `trimesh.load(path)` returns a `Scene` whose
`.geometry` is `{'body': ..., 'lip': ...}` with both bodies watertight and their
relative z preserved.

trimesh's 3MF writer needs `lxml`, which is declared in `requirements.txt`.

## In the slicer

Open the single `.3mf` in Bambu Studio / OrcaSlicer. Both bodies arrive already
separated and aligned as parts of one object — no "add part / load / assemble"
step. Select the **lip** part and assign it a different **filament/extruder**
than the body; on a multi-color setup (AMS) it prints as one seamless object in
two colors (e.g. a black body with a blue lip). This is the single-file
alternative to combining the two `--split-lip` STLs by hand.
