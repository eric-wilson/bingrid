# Snug-fit holder bins — planned

**Status:** 📋 planned, not scoped yet.

## Idea

Bins that hold an arbitrary (non-grid-sized) item snugly. The bin fits the
Gridfinity grid on the outside (reusing the existing bin foot + footprint) and
adds filler geometry inside to cradle the item. The interior is driven by the
item's shape.

## Open questions / inputs needed

- The user will provide item STL samples when this work starts.
- Approach for deriving the cradle cavity from an item mesh (e.g. offset hull,
  voxel subtraction, or a parametric pocket) is undecided.
- How much clearance around the item, and whether the item orientation is an
  input.

## Reuse

Build on the shipped bin generator: the outer foot/footprint and the
`BinFeature` pipeline already exist (see `baseplate-and-bins.md`). `meshtools`
(`MeshInspector`) can measure a supplied item mesh to drive the cavity.
