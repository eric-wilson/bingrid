# Session Handoff — bingrid

Pick-up notes for continuing in the new workspace. Delete this file once the
work below is wrapped up.

## Where things stand

The project is `bingrid` — a parametric Gridfinity grid/bin generator built on
CadQuery, with a reusable `meshtools` package for measuring reference meshes.

Recent commits (HEAD = `0b76fc4`, local `main` is 1 ahead of `origin/main`):

```
0b76fc4 🐛 fix (meshtools): degrade gracefully when 2D section extras are missing   <- not pushed
c829dbd ♾ devops (vscode): settings   <- origin/main
8d71fc1 📝 docs (licensing): drop remaining references to the BGG reference part
668d6c8 ✅ test (licensing): verify socket profile against the spec, not a third-party file
9d457d5 📝 docs (readme): drop references to the ignored samples directory
d3f2ead ♻ refactor (rename): 3d_printing -> bingrid, flatten package
960ff1b ✨ feat (magnet pockets): teardrop + vertical mounts for round holes
9559502 ✨ feat (socket profile, connectors, mesh tools): match Gridfinity baseplate
```

Features done so far:
- Gridfinity **baseplate/frame** generator: configurable grid, socket profile
  (matches the published spec), open floor by default + optional `--floor`,
  dovetail **connectors** for tiling, **magnet pockets** (teardrop horizontal
  by default so holes print round; optional vertical bottom-mount).
- `bingrid.meshtools`: `MeshInspector` + CLI for measuring any STL/OBJ/PLY.
- 89 tests (fast + integration); suite is self-contained (no third-party files).

## IMMEDIATE: one uncommitted, half-finished change

`tests/test_meshtools.py` is **modified but not committed** — this is an
in-progress fix that is NOT yet green. Finish this first.

**Problem:** `test_slice_reports_hole` built its holed-plate fixture with a
trimesh mesh boolean (`outer.difference(hole)`), which needs a boolean backend
(`manifold3d`/blender). `manifold3d` won't import on this Python 3.13 venv, so
the test errored.

**Fix in progress:** rewrote the fixture to extrude a shapely `Polygon` with an
interior ring (`trimesh.creation.extrude_polygon`), avoiding the boolean. But
that path needs a **triangulation engine** (`triangle` or `mapbox_earcut`) and
the last run still failed with a triangulation-engine error — I was about to
check whether `mapbox_earcut` is importable / wire it up when the session moved.

**Next steps to close it out:**
1. In the venv, check: `python -c "import mapbox_earcut"` and
   `python -c "import triangle"`. Install whichever is missing
   (`pip install mapbox_earcut`), or force trimesh to use the available engine.
2. Re-run: `pytest tests/test_meshtools.py -q` until green.
3. If a clean triangulation engine can't be settled quickly, an acceptable
   fallback is to generate the holed fixture with our own `GridfinityPlate`
   (CadQuery) exported to a temp STL, then load it with `MeshInspector` — that
   avoids trimesh's boolean/triangulation entirely and exercises a realistic
   mesh.
4. Commit with a message in the project's emoji style, e.g.
   `✅ test (meshtools): build holed fixture without a mesh-boolean backend`.

Note: `rtree` was added to `requirements.txt` and is needed for the 2D section
analysis (already committed in `0b76fc4`). `requirements.txt` now lists:
cadquery, trimesh, shapely, networkx, rtree.

## NEXT FEATURE: the bin generator (the main task)

Goal: generate Gridfinity **bins** that drop into the baseplates, with
configurable size (grid cells X/Y and height), an optional **stacking lip**, and
support for a **different-color top layer**. We agreed to build this as a
**workflow** (multi-file feature warranting a design + review loop).

### Measured dimensions from samples/ (DO NOT commit the samples — see Licensing)

Measured with `meshtools` from `samples/Gridfinity bin *.stl`:

- **Footprint:** `N*42 - 0.5 mm` per axis (1 cell = 41.5, 2 = 83.5, 3 = 125.5).
  The 0.25 mm per-side gap lets bins drop into the grid without binding.
- **Height:** Gridfinity height unit = **7 mm**. The "x5" samples are
  5*7 + ~3.8 mm base = **38.8 mm** tall. So a `--units 5` bin => 38.8 mm.
- **Base (bottom-up):** the INVERSE of our baseplate socket — narrow foot
  (~35.8) -> bottom chamfer -> vertical (~37.2) -> top chamfer flaring to the
  full body (~41.5). The bin foot plugs into the plate socket we already build.
- **Stacking lip (top rim, top-down):** a miniature socket profile built into
  the rim. Measured on the 1x1: main wall inner ~39.1 (wall ~1.2 mm), then the
  lip steps inward to inner ~37.7 over ~0.8 mm, holds ~37.7 for ~1.8 mm, then an
  outer chamfer opens the very top rim. Net effect: a bin stacks on another bin
  exactly like it seats on a baseplate (lip mirrors the socket).

### Agreed design

- Reuse the existing `PlateFeature`-style pluggable pattern.
- **Extract the socket profile into a shared module** so the baseplate (socket),
  the bin base (foot), and the stacking lip all derive from ONE source of truth
  (DRY) — this guarantees they always mate. This refactor touches
  `src/bingrid/config.py` (`GridfinityProfile`) and `geometry.py`.
- New `BinConfig` value object: `grid_x`, `grid_y`, `height_units` (7 mm units),
  `wall`, optional `floor`, feature toggles (stacking lip on/off). Validate like
  the other configs.
- New `GridfinityBin` builder parallel to `GridfinityPlate`, with features:
  base/foot, body walls, hollow interior, optional stacking lip.
- Bins are **hollow open-top containers** (configurable wall + floor), matching
  the samples.
- New CLI: `python -m bingrid.bin --x 2 --y 1 --units 6 --stacking-lip` (mirror
  the plate CLI's structure).
- **Multi-color top:** a single STL can't carry color. Decision: start with a
  `--split-lip` option that exports the body and the stacking lip as SEPARATE
  STL meshes (`..._body.stl`, `..._lip.stl`), so they load as two objects in the
  slicer and get different filaments. A `.3mf` multi-body export can come later.
- Tests (fast + integration): footprint/height math, base profile matches the
  socket, stacking-lip profile, a bin seats in a plate (union/validity), lip
  split exports two meshes. Verify against the published spec numbers, NOT a
  sample file.

### How to launch the workflow

Use a `run_workflow` `workflowPrompt` brief (not hand-authored JSON). Put all of
the above (measured dims + agreed design + file paths) into the brief so the
step agents have full context. Suggested worktree-less; it's additive. Include a
design pass and an implement+review loop given the size. Reuse the shared socket
profile; keep everything consistent with the existing config/geometry/exporter/
cli structure under `src/bingrid/`.

## PHASE 2 (later): snug-fit holder bins

Idea: bins that hold an arbitrary (non-grid-sized) item snugly — the bin fits
the grid on the outside and adds filler geometry inside to cradle the item.
Driven by the item's shape. User will provide item STL samples when we start
this. Not scoped yet.

## Licensing — IMPORTANT

- `samples/` is **gitignored** and must stay out of the repo. The reference
  files (incl. the MakerWorld baseplate and these bins) are under a **Standard
  Digital File License** that forbids redistribution/hosting. Do not commit
  them, and do not reference them by name in committed code/docs.
- All tests must stay self-contained (measure our own generated meshes vs. the
  published Gridfinity spec). A local-only comparison test exists but is
  `@pytest.mark.skip`'d and points at a user-supplied path outside the repo.

## Environment notes

- venv at `.venv` (Python 3.13.2, cadquery 2.8.0, trimesh 5.2.0).
- Run CLIs from `src/`: `python -m bingrid.cli ...`,
  `python -m bingrid.meshtools.cli ...`. `import bingrid` works as a normal
  import now (package was flattened from the old digit-prefixed `3d_printing`).
- Tests: `pytest` (fast), `pytest -m integration` (builds solids). pyproject
  puts `src` on pythonpath and deselects integration by default.
- The repo directory on disk is still named `3d-printing/`; the package/project
  is `bingrid`. Renaming the directory is optional and up to you.
- Commit style: emoji + type + (scope): short description, e.g.
  `✨ feat (bins): ...`. Commit only when asked.
```
