# Snug-fit holder bins — design

**Status:** 📝 design (fleshed out, not yet built).

## Idea

A **generic parametric holder**: a Gridfinity bin whose **interior is a
repeating grid of item-shaped pockets**. The outside is a normal `bingrid` bin —
same footprint, foot, floor, and optional stacking lip, so it seats on a
baseplate and stacks like any other bin. The inside is carved into an R×C array
of identical pockets, each sized to one item plus a fit clearance.

The driving idea: **you give the measurements of the thing you want to store,
and the generator figures out the pocket grid** — how many fit across the bin,
how to space them, and how much to leave as leftover open space. "1, 2, 5… of
these in a single holder" is just different pocket counts from the same engine.

**The item is just a measured shape — it doesn't care what it is.** Batteries
are only the first thing we point it at. A 9V, an AA, a parts tin, a roll of
tape, a Sharpie, an SD card, or some non-Gridfinity container you want to drop
into the grid are all the same to the generator: a rectangular or round
footprint + height + clearance. That makes this one tool for two use cases that
sounded different at first:

- **Hold the items directly** — a pocket per battery / pen / bit. (Multi-pocket.)
- **Hold another container** — one big loose-fit pocket sized to a box that
  never had a Gridfinity bottom, so it now seats on the grid. (This is just the
  R=C=1, `--fit loose` case of the same engine; see the single-cradle example
  below.)

### Worked example — the battery holders in the reference photos

- **9V holder:** item footprint ≈ 26.5 × 17.5 mm. Dropped into a 1×1 Gridfinity
  cell interior (~39.1 mm), the layout formula below fits a 1×2 of pockets →
  two 9Vs per cell (two 18.3 mm-deep pockets fit across the 39.1 mm depth; a
  second column of 27.3 mm-wide pockets will not), with the batteries standing
  proud so you can grab them. (Want four per cell? That is a 2×1 bin, or two 1×1
  holders side by side — exactly what the reference photos show.)
- **AA holder:** item ⌀ ≈ 14.5 mm (round pockets). The same 1×1 interior holds a
  2×2 grid of upright AA slots (15.0 mm pockets, two per axis).

The exact counts are whatever the authoritative layout formula below produces
for the item dimensions and fit preset — the generator computes them and prints
the derived `rows×cols`; the numbers here are illustrative of that formula, not
hand-tuned targets.

Both are the **same feature** with different item dimensions, pocket shape, and
count. A "single big pocket for one odd item" (the original snug-cradle idea) is
this engine at R=C=1 with one large rectangular pocket.

## Scope — what we're building (and not)

The feature is **generic by construction** — one `holder` generator that cuts a
pocket grid from measurements. "Battery bin" and "container-for-containers" are
not separate features; they are the same generator with different numbers
(multi-pocket vs. a single loose pocket).

**In scope (v1):**

- A new `holder` generator (`bingrid holder ...`) built on the existing bin.
- **Rectangular** and **round** pockets, sized from item dimensions + clearance.
- Two layout drivers:
  1. **fit-count** — "I want N of these": give item dims + a target count (or
     explicit rows×cols); the generator picks the smallest whole-cell bin that
     holds them.
  2. **fill-bin** — "pack this bin": give item dims + a bin size (`--x`/`--y`);
     the generator lays in as many pockets as fit and reports the count.
- Pocket depth control so items stand proud (grabbable) or sit flush.
- Reuse of foot / footprint / floor / stacking lip from `BinConfig`.
- Config-derived file name + STL/STEP export; the existing `--3mf` /
  `--3mf-paint` paths keep working (they key off the body/lip split, which is
  unchanged).

**Out of scope (v1), possible follow-ups:**

- **Item presets** (`--item AA`, `--item 9V`, `--item 18650`) — a small named
  library mapping to dims + shape. Nice ergonomics, but raw dims are the MVP.
- **Cavity-from-mesh** — deriving a pocket from a supplied item STL (offset
  hull / voxel subtraction). Heavier; the parametric pocket covers the battery
  use case without it.
- **Mixed pocket sizes in one bin** (e.g. big pockets on one half, small on the
  other). v1 is one pocket spec per bin; combine by printing two 1×1 holders
  side by side (exactly what the reference photos show — a 9V holder next to an
  AA holder).
- **Finger-scoop cutaways** on deep pockets — worth a flag later; noted below.

## The pocket model (the crux: snug *with tolerance*)

The thing that makes this useful or useless is the fit, so it's explicit and
mirrors the clearance scheme already used for the foot/socket (0.25 mm/side) and
magnets (`--magnet-clearance`).

- **Nominal item size** is what the user measures (outer W×D for rectangular,
  diameter for round).
- **Pocket size = nominal + 2 × fit clearance** (clearance applied per side).
- **Fit presets** instead of raw mm, since "snug with tolerance" is subjective:
  - `--fit snug` → 0.25 mm/side (firm, item held in place)
  - `--fit normal` → 0.40 mm/side (default — drops in, easy to grab)
  - `--fit loose` → 0.60 mm/side (very forgiving)
  - `--fit-clearance <mm>` overrides the preset with an explicit per-side value.
- **Pocket corner radius** for rectangular pockets (default small, e.g. 1.0 mm)
  so a boxy item isn't fighting a sharp internal corner, and so the pocket
  prints cleanly.
- **Round pockets** are a plain vertical cylinder cut (no overhang — it's a
  cavity opening upward, so it prints round with no teardrop needed, unlike the
  horizontal magnet holes).

### Depth / "stand proud"

From the photos the batteries stick up above the rib walls so you can pinch
them out. Two depth controls:

- `--pocket-depth <mm>` — explicit cavity depth measured down from the top of
  the body interior.
- `--item-height <mm>` + `--proud <mm>` — alternative: cut the pocket so the
  item sits with `--proud` mm exposed above the wall. The generator sizes the
  bin height (units) to suit, or honors an explicit `--units`.

A pocket never cuts into the foot/floor region: its floor is clamped to
`cavity_bottom = base_height + floor`, same rule the hollow body already uses.

## Layout: deriving the grid from measurements

Interior available per axis is the bin's inner opening (`footprint − 2·wall`,
accounting for the rounded interior corners already modelled). Given a pocket
footprint `pw × pd` and an **inter-pocket wall** `--pocket-wall` (default ~1.2
mm, matching the body wall so ribs look consistent with the photos):

```
cols = floor( (inner_width  + pocket_wall) / (pw + pocket_wall) )
rows = floor( (inner_length + pocket_wall) / (pd + pocket_wall) )
```

- **fill-bin mode:** `--x`/`--y` set the bin; `cols`/`rows` computed as above;
  the summary prints the resulting pocket count and the leftover margin.
- **fit-count mode:** `--count N` (or `--rows R --cols C`); the generator tries
  increasing whole-cell bin sizes (1×1, 2×1, 2×2, …) until `rows·cols ≥ N`, then
  centers the grid and reports the chosen bin size.
- **Leftover space** (the margin that doesn't divide evenly) is, by default,
  left as open interior on one side — the "bonus pocket" from the original idea.
  `--center-grid` (default on) centers the pocket block; `--pack start` pushes it
  to a corner so the leftover is one contiguous open strip.

Pockets register to the bin interior, not the 42 mm lattice, so a multi-cell
holder gets one continuous pocket field across cell seams (just like the hollow
body spans cells today).

## CLI surface (`bingrid holder`)

Reuses the bin's grid/wall/floor/profile/lip/output options verbatim (same
`OptionSpec` entries), plus a holder group. Sketch:

| Flag | Default | Description |
|------|---------|-------------|
| `--x`, `--y` | auto / `1` | Bin size in cells. Omitted in fit-count mode (derived); required-ish in fill-bin mode. |
| `--pocket-shape` | `rect` | `rect` or `round`. |
| `--item-w`, `--item-d` | — | Item footprint for `rect` (mm). |
| `--item-dia` | — | Item diameter for `round` (mm). |
| `--item-height` | — | Item height (mm); with `--proud` drives bin height. |
| `--count` | — | fit-count: total pockets wanted; picks the bin size. |
| `--rows`, `--cols` | — | fit-count: explicit layout instead of `--count`. |
| `--fit` | `normal` | `snug` / `normal` / `loose` clearance preset. |
| `--fit-clearance` | — | explicit per-side clearance (mm); overrides `--fit`. |
| `--pocket-wall` | `1.2` | rib thickness between pockets (mm). |
| `--pocket-corner-radius` | `1.0` | rect pocket internal corner radius (mm). |
| `--pocket-depth` | auto | explicit cavity depth (mm). |
| `--proud` | `6.0` | mm the item stands above the wall (with `--item-height`). |
| `--center-grid` / `--pack` | center | where leftover margin goes. |
| `--units` | auto | height units; auto-fit from item height + proud unless set. |
| (inherited) | — | `--pitch --wall --floor --corner-radius --foot-clearance --stacking-lip --lip-* --3mf --3mf-paint --output-dir --name` |

Exactly one item-size set must be given for the chosen shape (`rect` → w+d,
`round` → dia); mismatches exit with code 2 via `precheck`, same pattern as the
existing lip/paint guards.

### Examples

```bash
# from src/
# Fill a 1x1 bin with 9V pockets, batteries standing proud to grab
bingrid holder --x 1 --y 1 --pocket-shape rect \
    --item-w 26.5 --item-d 17.5 --item-height 48 --proud 10 --fit normal

# "I want 8 nine-volts" -> generator picks the bin size (likely 2x1)
bingrid holder --pocket-shape rect --item-w 26.5 --item-d 17.5 --count 8

# AA holder: round pockets, fill a 1x1
bingrid holder --x 1 --y 1 --pocket-shape round --item-dia 14.5 \
    --item-height 50 --proud 12 --fit snug

# One big loose cradle to drop a non-Gridfinity container onto the grid
# (R=C=1) -- e.g. a 60x30 mm parts tin that never had a Gridfinity bottom.
# No --x/--y: this is the fit-count path, so the generator grows the bin to
# the smallest whole-cell size that holds the 60 mm pocket (a 2x1 here).
bingrid holder --rows 1 --cols 1 \
    --pocket-shape rect --item-w 60 --item-d 30 --fit loose

# NOTE: in fill-bin mode an explicit --x/--y is authoritative (it sets the bin
# and is never silently resized). So `--x 1 --y 1 ... --item-w 60` is correctly
# REJECTED with exit 2 ("pocket wider than interior") -- a 60 mm item cannot fit
# a 1x1 interior (~39.1 mm). Drop --x/--y (as above) to let the generator pick a
# bin that holds the item, or give an --x/--y large enough (e.g. `--x 2 --y 1`).
```

## Implementation plan

Follows the existing SOLID/DRY shape — a new config, a new interior `BinFeature`,
a new generator spec. No change to the plate or to the bin's foot/footprint math.

1. **`HolderConfig`** (`config.py`) — a frozen dataclass composed WITH (or
   extending) `BinConfig`, adding the pocket fields above. `__post_init__`
   validates: a complete item-size set for the shape, clearance ≥ 0, pocket
   fits the interior (`pw + 2·fit ≤ inner_width`, likewise depth), at least one
   pocket fits, pocket depth leaves the floor intact. Clearance preset → mm
   resolved via a property (mirrors `resolved_lip_wall` / `resolved_height`).
   The layout math (`rows`, `cols`, `pocket_pitch_*`, `leftover_*`) lives here as
   derived properties — the single source of truth, unit-testable with no CadQuery.

2. **`PocketGridFeature`** (`geometry.py`) — a `BinFeature` that, after the
   hollow-body cut, subtracts the R×C array of pockets from the interior solid
   (or, alternatively, builds the rib lattice additively inside an un-hollowed
   body — decide at build time; subtractive is simpler and reuses the cavity
   clamp). Round pockets: `cq ...cylinder` cut array. Rect pockets: filleted
   rectangle cut array. Honors `cavity_bottom`; centers/packs per config.
   Added as a pipeline class — the builder itself is untouched (Open/Closed).

3. **`holder` generator spec** (`cli/generators/holder.py`) — ordered
   `OptionSpec` list (inherit the shared bin options, add the holder group),
   `build_config` → `HolderConfig`, `build_and_export` reusing the bin's
   split/3mf/paint branches verbatim (the holder's body/lip split is the same
   shape), `summary` that also prints the derived `rows×cols`, pocket count, and
   leftover margin so fill-bin/fit-count results are visible. `precheck` for the
   item-size/shape guards. `REGISTRY.register(SPEC)` at import.

4. **File naming** (`exporter.py`) — a `holder_default_name(config)` alongside
   `bin_default_name`, composing bin size, pocket grid, shape, units, and the
   item dims: `holder_{x}x{y}_{rows}x{cols}_{shape}_u{units}_{dims}`. v1 ships
   raw dims (not a named item preset), so a 9V rect holder is
   `holder_1x1_2x1_rect_u6_26.5x17.5.stl` and an AA round holder is
   `holder_1x1_2x2_round_u6_dia14.5.stl`. (A named `9v`/`AA` item tag is the
   deferred item-preset follow-up, not v1.)

5. **meshtools** stays the backing measurement tool — handy for a user to
   measure a reference item mesh when they don't have calipers, and for tests.

## Test plan (self-contained, per the features README)

No sample files; measure our own generated meshes against computed expectations.

- **Layout math (fast, pure):** `rows`/`cols`/leftover for known item + bin
  sizes; fit-count picks the expected bin size; validation rejects an item
  wider than the interior, zero pockets, negative clearance.
- **Clearance resolution:** each `--fit` preset maps to the right mm; explicit
  `--fit-clearance` overrides.
- **Geometry (integration):** a built holder is a valid solid; pocket count in
  the mesh matches the computed `rows·cols` (count interior voids via
  `MeshInspector`/section hole count, the `hole_extents`/`med_open` pattern
  already used for the foot test); pocket inner size ≈ item + 2·clearance; the
  pocket floor sits at/above `cavity_bottom` (foot/floor never breached);
  bounding box still `N·pitch − 0.5` (pockets only remove interior material).
- **Still seats + stacks:** a holder unions into a 2×2 plate validly; with a lip,
  the lip profile is unchanged from the plain bin (regression guard reused).
- **Export branches:** `--3mf` / `--3mf-paint` still produce the expected bodies
  (the holder reuses the bin split, so these should pass unchanged).

## Reuse summary

- **Footprint, foot, floor, rounded corners, stacking lip** — all from
  `BinConfig` / `GridfinityBin`, unchanged.
- **Schema-driven CLI** — one `OptionSpec` list feeds both argparse and the
  interactive prompter; the holder group gets `prompt_when` gates (e.g.
  `--item-dia` only when `--pocket-shape round`) exactly like the lip/paint
  sub-options.
- **Export** — split / `.3mf` / painted `.3mf` paths are shape-agnostic and come
  along for free.

## Decisions (locked for v1)

1. **Subtractive pockets.** Cut the pocket array from a solid interior (reusing
   the cavity-bottom clamp), rather than building an additive rib lattice.
   Simpler and consistent with how the hollow body is already made. Revisit
   additive ribs later if the walls feel bulky or filament-heavy.
2. **Center the grid by default.** Leftover margin is split symmetrically on
   both sides; `--pack start` pushes the block to a corner so the leftover is
   one contiguous open "bonus pocket" strip.

### Deferred to follow-ups (not in v1)

3. **Finger access** — optional scoop/cutaway on a pocket wall for deep pockets
   (`--finger-scoop`). The `--proud` stand-up height covers the common case for
   now.
4. **Item presets** — a named library (`--item 9V`, `--item AA`, `--item 18650`)
   mapping to dims + shape. v1 ships raw dims only.
