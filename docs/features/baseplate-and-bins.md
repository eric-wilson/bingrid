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
- **Rounded corners:** a **3.75 mm outer vertical corner radius** gives the bin a
  rounded-rectangle footprint (real Gridfinity), so bins stack and seat cleanly.
  Applied to both the body and the stacking-lip rim (they share the outer
  footprint). Configurable via `--corner-radius` (default 3.75, `0` = sharp);
  rounding only removes material inside the footprint, so the bounding box stays
  `N*42 - 0.5` unchanged.
- **Height:** 7 mm per unit + ~3.8 mm base. `--units 6` body = 45.8 mm tall.
- **Foot:** the socket's **solid complement** (a male plug) — same z-orientation
  as the socket (narrow at low z, wide at high z), NOT a vertical mirror. The
  foot plugs into the plate socket.
- **Floor:** with `floor > 0` (default), a **continuous full-footprint slab**
  joins all cells into one solid; the interior cavity is cut a full `floor`
  thickness above the feet (`cavity_bottom = base_height + floor`). `floor = 0`
  keeps the intentional open bottom. (An earlier bug left an inter-cell channel
  because the per-cell feet never got a bridging floor; fixed.)
- **Stacking lip:** an additive **full-perimeter rim** above the body whose
  opening tracks the interior footprint (≈ `inner_width × inner_length`), so the
  bin stays open-top across its whole footprint. The rim is the **full shared
  socket cross-section** mirrored into the perimeter — a bottom chamfer lead-in,
  a straight vertical seat run, and a flared top mouth — so its height is
  `profile.total_height` (≈ 4.8 mm) and a bin stacks on a bin exactly like it
  seats on a baseplate. The **underside is chamfered (≤45°, self-supporting)**
  rather than a flat downward-facing ledge: at the `z = total_height` mating
  plane the lip opening equals the body interior and tapers inward going up, so
  the lip prints clean without support and without stringing. (The lip is the
  socket cross-section swept around the rectangular perimeter — NOT a single
  socket stamped in the center; that earlier bug left a solid top deck with one
  small hole and was fixed. An earlier lip also omitted the bottom chamfer,
  leaving a flat overhanging ledge under the seat; adding the full profile makes
  it self-supporting.)
- Feet center on the full `grid*pitch` lattice so multi-cell bins register with
  plate sockets.

### Multi-color top (`--split-lip`)

A single STL can't carry color. `--split-lip` exports the body and the stacking
lip as two separate STL meshes (`..._body.stl`, `..._lip.stl`) sharing one
footprint and origin, so a slicer loads them pre-aligned (the lip sits exactly
on top of the body) for a two-filament print — e.g. a black body with a blue
lip.

```bash
# from src/
python -m bingrid.bin --x 2 --y 1 --units 5 --stacking-lip --split-lip
# writes ..._body.stl + ..._lip.stl (+ a combined .step for reference)
```

#### Combining the two STLs in Bambu Studio / OrcaSlicer

The two meshes already share an origin, so do NOT re-center or "drop to bed"
them individually — that shifts one relative to the other. Just combine them:

- **Load body, add lip as a part:** import `..._body.stl`, then right-click it
  in the object list → **Add part** → **Load...** → pick `..._lip.stl`. The lip
  lands on top at its original coordinates. The result is one object with two
  parts.
- **Or import both, then assemble:** import both STLs (they load aligned),
  shift-select them in the object list, right-click → **Assemble** (some
  versions: *Merge into object parts*). This fuses them into one object without
  moving them.

Then select the **lip** part and assign it a different **filament/extruder**
than the body. On a multi-color setup (AMS) it prints as one seamless object in
two colors. If the lip ever looks offset, use **Assemble** to snap both back to
their original coordinates.

For the single-file alternative, `--3mf` writes one `.3mf` holding both bodies
pre-separated and color-assignable (no manual combine step) — see
[two-color-3mf-export.md](two-color-3mf-export.md).

```bash
# from src/
python -m bingrid.bin --x 2 --y 1 --units 5 --stacking-lip --3mf
# writes one .3mf with two named bodies ("body" + "lip"), pre-aligned
```

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
