# Baseplate & bins — shipped

`bingrid` is a parametric Gridfinity grid/bin generator built on CadQuery, with
a reusable `meshtools` package for measuring reference meshes.

## Shared socket profile (single source of truth)

`GridfinityProfile` (`src/bingrid/config.py`) defines the standard Gridfinity
socket profile once. The baseplate socket, the bin foot, and the stacking lip
all derive from it via `profile_planes()` / `foot_planes()` and the
`_loft_profile` helper in `geometry.py`, so the three always mate. A `rel=1e-9`
volume/bbox regression guard pins the plate socket (baseline socket volume
1531.345 for a 1x1 at height 5.0).

The profile is a **measured carbon-copy** of the reference Gridfinity part
(re-measured at fine z-steps). Dataclass profile defaults — now matched exactly
by both the plate CLI (`bingrid grid`) and the bin CLI
(`bingrid bin`):

- `top_opening = 37.7` (straight-section seat opening),
- `chamfer_top = 2.1` (mouth flare → `mouth_opening = 37.7 + 2*2.1 = 41.9`,
  kept strictly below the 42 mm pitch so the plate wall survives),
- `straight = 1.75` (vertical seat run),
- `chamfer_bottom = 0.80` (lower lead-in),
- `bottom_inset = 0.75` (per-side narrowing → `bottom_opening = 36.2`),
- so `total_height = 2.1 + 1.75 + 0.80 = 4.65 mm`.

Because the socket is shared, correcting these constants deliberately moved the
**plate socket** too (in lockstep with the bin foot and lip) — the baseplate
generator's geometry code is unchanged; only the shared constants moved.

## Baseplate / frame

Generator: `GridfinityPlate` (`geometry.py`), CLI `bingrid grid`.

- Configurable grid; socket profile matches the published spec.
- Open floor by default, optional `--floor`.
- Dovetail **connectors** for tiling.
- **Magnet pockets**: teardrop horizontal by default (holes print round);
  optional vertical bottom-mount.
- **Rounded socket interior opening:** the socket cavity's **inner** opening
  corners are rounded **concentric with the reference outer corner** (the same
  3.75 mm family the bin body/foot/lip use), not left squared off — matching the
  Gridfinity reference, whose open base curves on its inner corners all the way
  up. The per-plane radius **GROWS up the socket** (concentric with the outer):
  it is `corner_radius - (mouth_opening - opening)/2` (the outer radius minus
  that plane's per-side inset below the mouth, clamped ≥ 0), so it is **~0.9 mm
  at the narrow bottom → ~1.65 mm through the straight seat → ~3.75 mm at the
  wide mouth** — derived from the single `GridfinityProfile.corner_radius` (no
  magic numbers). This **only curves the interior**; the socket opening
  **sizes/heights are unchanged**, so the flat opening span a bin foot seats
  against is identical and bins still interlock with plates (foot, lip, and
  socket stay one consistent rounded family). `corner_radius = 0` opts back out
  to a sharp (square) socket opening. Rounding the interior removes a little more
  material, so the plate volume drops slightly (1531.345 -> 1471.168); the plate
  footprint and height (bounding box) are unchanged (42 x 42 x 5.0).

## Bins

Generator: `GridfinityBin` with a `BinFeature` pipeline (body, foot, hollow
interior, optional stacking lip). Config: `BinConfig`. CLI:
`bingrid bin --x 2 --y 1 --units 6 --stacking-lip`.

Key dimensions (derived from the shared profile, verified against the spec):

- **Footprint:** `N*42 - 0.5 mm` per axis (0.25 mm/side drop-in gap). 2x1 = 83.5 x 41.5.
- **Rounded corners:** a **3.75 mm outer vertical corner radius** gives the bin a
  rounded-rectangle footprint (real Gridfinity), so bins stack and seat cleanly.
  Applied to the body, the stacking-lip rim, **and the foot** (they share the
  outer footprint / corner center). Configurable via `--corner-radius`
  (default 3.75, `0` = sharp); rounding only removes material inside the
  footprint, so the bounding box stays `N*42 - 0.5` unchanged.
- **Body wall & interior:** the body wall is **1.2 mm/side**, so the interior
  opening is **39.10 mm** per cell (`footprint - 2.4`).
- **Rounded interior opening:** the **inner** opening corners — the hollow
  cavity *and* the stacking-lip's inner opening — are also **rounded concentric
  with the outer corners** (real Gridfinity), not left sharp 90° squares, so the
  wall keeps a uniform thickness wrapping each corner. Each interior radius is
  **derived** from the single `corner_radius` by subtracting that opening's
  per-side inset (same concentric-corner thinking as the foot, no second radius
  constant): the cavity inner corner is `corner_radius - wall = 3.75 - 1.2 =`
  **2.54 mm**, and the **lip-seat inner corner is ≈ 1.85 mm**
  (`corner_radius - resolved_lip_wall = 3.75 - 1.90`) — a larger, measured curve
  than the pre-rebuild rim. Clamped to ≥ 0 (a thick wall/sharp outer falls back
  to a square interior).
- **Height:** 7 mm per unit + ~3.65 mm base. `--units 5` → body 35 mm,
  `total_height` 38.65 mm. Relative to the pre-rebuild bin the carbon-copy
  profile lowers the overall height by **1.15 mm** — the lip height drops 1.0 mm
  (4.80 → 3.80) and the base height drops 0.15 mm (profile `total_height`
  4.80 → 4.65). (The overall-height **model** — base + units*7 + lip — still
  differs from how the reference bin encodes height, so a generated U5 bin is
  ~42.45 mm tall vs the reference's 38.80 mm. That pre-existing height-model
  mismatch is a tracked backlog item, out of scope for the carbon-copy profile.)
- **Foot (measured angled taper):** the socket's **solid complement** (a male
  plug) — same z-orientation as the socket (narrow at low z, wide at high z),
  NOT a vertical mirror. The foot is a **continuous angled taper**, not a near-
  straight wall: it widens from a **35.70 mm base** up through an angled lower
  lead-in to a **37.20 mm straight seating section** (held over ~0.80–2.55 mm),
  then flares to the body footprint. The 37.20 straight seat drops into the plate
  socket seat (37.70) — and into another bin's lip seat (also 37.70) — with
  0.25 mm/side clearance. Its corners are **rounded concentric with the body
  corners**: the per-level radius tapers up the foot (base **~1.57 mm**, upper
  **~2.47 mm**, approaching the body's 3.75 mm where the foot flares into the
  body), computed as `corner_radius - (foot_ref_half - foot_half)` so every foot
  plane's corner arc shares the body corner's center — so the foot seats without
  binding and the foot-to-body transition closes with no open-air corner sliver.
- **Floor:** with `floor > 0` (default), a **continuous full-footprint slab**
  joins all cells into one solid; the interior cavity is cut a full `floor`
  thickness above the feet (`cavity_bottom = base_height + floor`). `floor = 0`
  keeps the intentional open bottom. (An earlier bug left an inter-cell channel
  because the per-cell feet never got a bridging floor; fixed.)
- **Stacking lip (measured seat ledge):** an additive **full-perimeter rim**
  above the body whose opening tracks the interior footprint, so the bin stays
  open-top across its whole footprint. Its cross-section is the **measured lip
  profile** (`lip_planes()`): continuous with the body interior (39.10) at the
  base, a **self-supporting lead-in** (0.70 mm/side over a 0.70 mm rise = exactly
  45°, the limit) down to the **seat opening 37.70**, a straight **seat run
  (1.90 mm)** — the ledge a stacked bin's foot drops onto — then a flared **mouth
  (39.90, inset `lip_mouth_inset` 0.80/side)** at the top face. Total lip height
  is **3.80 mm** (lead 0.70 + seat 1.90 + mouth 1.20). The **seat opening 37.70
  is the same as the baseplate socket seat** (`foot_straight_opening +
  2*lip_clearance`), so a bin stacks on a bin exactly like it seats on a
  baseplate, and the pre-rebuild "inner lip too big" (the old seat opened to
  34.70) is fixed. The rim wall is `resolved_lip_wall` **≈ 1.90 mm** (derived
  `(cell_footprint - lip_seat_opening)/2`, or overridden with `--lip-wall`). The
  new `lip_mouth_inset` / `lip_lead_h` / `lip_mouth_h` are library-only measured
  constants (no CLI flag); only `--lip-wall` and `--lip-clearance` are
  user-facing lip knobs.
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
bingrid bin --x 2 --y 1 --units 5 --stacking-lip --split-lip
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
bingrid bin --x 2 --y 1 --units 5 --stacking-lip --3mf
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
