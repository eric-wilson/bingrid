# Baseplate & bins — shipped

`bingrid` is a parametric Gridfinity grid/bin generator built on CadQuery, with
a reusable `meshtools` package for measuring reference meshes.

## Shared socket profile (single source of truth)

`GridfinityProfile` (`src/bingrid/config.py`) defines the standard Gridfinity
socket profile once. The baseplate socket, the bin foot, and the stacking lip
all derive from it via `profile_planes()` / `foot_planes()` and the
`_loft_profile` helper in `geometry.py`, so the three always mate. A `rel=1e-9`
volume/bbox regression guard pins the plate socket so the refactor can't shift
it (baseline socket volume 1619.095).

Dataclass profile defaults are the spec source of truth
(`chamfer_top=2.2`, `straight=1.75` → mouth 41.9, total height 4.8). Note the
plate CLI exposes slightly different defaults (2.15 / 1.8); tests build configs
directly, so they exercise the dataclass values.

## Baseplate / frame

Generator: `GridfinityPlate` (`geometry.py`), CLI `python -m bingrid.cli`.

- Configurable grid; socket profile matches the published spec.
- Open floor by default, optional `--floor`.
- Dovetail **connectors** for tiling.
- **Magnet pockets**: teardrop horizontal by default (holes print round);
  optional vertical bottom-mount.

## Bins

Generator: `GridfinityBin` with a `BinFeature` pipeline (body, foot, hollow
interior, optional stacking lip). Config: `BinConfig`. CLI:
`python -m bingrid.bin --x 2 --y 1 --units 6 --stacking-lip`.

Key dimensions (derived from the shared profile, verified against the spec):

- **Footprint:** `N*42 - 0.5 mm` per axis (0.25 mm/side drop-in gap). 2x1 = 83.5 x 41.5.
- **Height:** 7 mm per unit + ~3.8 mm base. `--units 6` body = 45.8 mm tall.
- **Foot:** the socket's **solid complement** (a male plug) — same z-orientation
  as the socket (narrow at low z, wide at high z), NOT a vertical mirror. The
  foot plugs into the plate socket.
- **Stacking lip:** an additive cap above the body that mirrors the socket, so a
  bin stacks on a bin exactly like it seats on a baseplate (~3.95 mm tall).
- Feet center on the full `grid*pitch` lattice so multi-cell bins register with
  plate sockets.

### Multi-color top (`--split-lip`)

A single STL can't carry color. `--split-lip` exports the body and the stacking
lip as two separate STL meshes (`..._body.stl`, `..._lip.stl`) sharing one
footprint, so a slicer loads them as two objects for different filaments. A
`.3mf` multi-body export is deferred.

## Tests

Fast + integration, self-contained against the published spec (see Licensing in
the features README). Coverage includes footprint/height math, the shared-profile
refactor regression guard, foot-vs-socket fit (foot measured on a single-cell
bin; `hole_extents` reduced to a scalar via the `med_open` median pattern),
stacking-lip profile, a bin seating in a 2x2 plate (`union().isValid()`), the
`floor > base_height` cavity branch, and the split-lip dual export. Slice-based
tests guard a `None` section (skip when trimesh 2D extras are missing) and fall
back to the solid validity check.

`meshtools` (`MeshInspector` + CLI) measures any STL/OBJ/PLY and backs these
spec checks. Depends on `mapbox_earcut` (declared in `requirements.txt`) for the
2D section/triangulation path.
