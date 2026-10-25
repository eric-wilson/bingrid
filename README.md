# bingrid

Parametric, configurable [Gridfinity](https://gridfinity.xyz/)-style grid
generator built on [CadQuery](https://cadquery.readthedocs.io/) — grids and the
bins that fit into them. Describe the grid you want on the command line and get
printable STL and STEP files.

The default cell opening reproduces the standard Gridfinity baseplate socket
profile, so bins seat correctly and plates stay compatible when tiled together
at any grid size.

## Features

- **Configurable grid** — any X×Y cell count, cell pitch, wall thickness, and height.
- **Gridfinity socket profile** (default) — each cell opening has the standard
  lead-in chamfer → vertical → bottom chamfer socket so a bin foot seats cleanly.
  A legacy simple-taper style is also available.
- **Open floor by default, optional floor** — openings punch through by default;
  add `--floor <mm>` for a solid base.
- **Magnet pockets** — horizontal (edge) or vertical (bottom-face) mounts.
  Horizontal pockets default to a teardrop shape so they print round instead of
  oval; vertical pockets print perfectly round.
- **Dovetail connectors** — optional tabs and slots on the outer edges so frames
  tile together; push two frames edge-to-edge and the tab seats into the slot.
- **STL + STEP export** with config-derived file names.
- **Mesh inspection tool** (`meshtools`) — reusable utility for measuring any
  STL/OBJ/PLY mesh: size, volume, and cross-section profiles.

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/bingrid.git
cd bingrid

# Set up the virtual environment (installs dependencies, incl. cadquery)
./pysetup.sh

# Activate it
source activate.sh
```

Dependencies: `cadquery` (modeling), plus `trimesh`, `shapely`, and `networkx`
(mesh inspection). All are listed in `requirements.txt`.

## Usage

The generator is driven by a CLI. Run it as a module from the `src` directory
(or with `src` on `PYTHONPATH`):

```bash
cd src
python -m bingrid.cli --help
```

### Examples

```bash
# Default 2x2 frame: Gridfinity socket profile, open floor, magnets
python -m bingrid.cli

# A 3x3 frame matching the BGG reference footprint (126 x 126 x 5 mm)
python -m bingrid.cli --x 3 --y 3 --no-magnets --height 5

# Add a 1.2 mm solid floor
python -m bingrid.cli --floor 1.2

# Legacy simple taper instead of the socket profile
python -m bingrid.cli --style taper --taper-angle 2

# Larger magnets and a thicker wall
python -m bingrid.cli --magnet-diameter 6 --magnet-depth 2 --wall 6

# Tileable frames with dovetail connectors
python -m bingrid.cli --x 2 --y 2 --connectors

# Vertical (bottom-face) magnets instead of edge magnets (needs a floor)
python -m bingrid.cli --magnet-orientation vertical --floor 2

# Plain round horizontal pockets instead of teardrop
python -m bingrid.cli --magnet-shape round
```

Output is written to `.output/` by default (override with `--output-dir`), with
a name derived from the configuration, e.g.
`gridfinity_3x3_open_socket_mag_3.0x1.0.stl`.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--x`, `--y` | `2` | Cells in X and Y |
| `--pitch` | `42.0` | Gridfinity cell pitch (mm) |
| `--wall` | `5.0` | Border / crossbar thickness (mm) |
| `--height` | auto | Plate height (mm); auto-fits the profile and magnets when omitted |
| `--floor` | `0.0` | Floor thickness (mm); `0` = open floor |
| `--style` | `socket` | Opening style: `socket` (Gridfinity) or `taper` (legacy) |
| `--profile-top-opening` | `37.5` | Socket: inner opening along the vertical (mm) |
| `--profile-chamfer-top` | `2.2` | Socket: top lead-in chamfer height (mm) |
| `--profile-straight` | `1.75` | Socket: vertical section height (mm) |
| `--profile-chamfer-bottom` | `0.85` | Socket: bottom chamfer height (mm) |
| `--profile-bottom-inset` | `1.6` | Socket: per-side inward step over the bottom chamfer (mm) |
| `--taper-angle` | `2.0` | Taper style: draft angle in degrees; `0` = straight |
| `--no-magnets` | — | Disable magnet pockets |
| `--magnet-diameter` | `3.0` | Magnet diameter (mm) |
| `--magnet-depth` | `1.0` | Magnet depth (mm) |
| `--magnet-clearance` | `0.2` | Added to diameter for fit (mm) |
| `--magnet-glue-gap` | `0.3` | Extra pocket depth for glue (mm) |
| `--magnet-orientation` | `horizontal` | `horizontal` (edge) or `vertical` (bottom face) |
| `--magnet-shape` | `teardrop` | Horizontal pocket shape: `teardrop` (print-safe) or `round` |
| `--magnet-teardrop-angle` | `45.0` | Teardrop roof half-angle (degrees) |
| `--connectors` | off | Add dovetail connectors for tiling frames |
| `--connector-width` | `8.0` | Dovetail mouth width (mm) |
| `--connector-depth` | `4.0` | Dovetail depth (mm); must be `< wall` |
| `--connector-flare` | `1.5` | Dovetail flare, half the mouth/base difference (mm) |
| `--connector-clearance` | `0.15` | Per-side sliding gap on the male tab (mm) |
| `--output-dir` | `.output` | Output directory |
| `--name` | derived | Base file name |

### Backward-compatible script

The original entry point still works and now builds the default 2x2 frame with
the Gridfinity socket profile:

```bash
python -m bingrid.gridfinity_2x2_open_magnetic
```

## The Gridfinity socket profile

The default opening reproduces the standard Gridfinity baseplate socket. Reading
a cell wall from the top face downward:

1. a 45° lead-in chamfer (`--profile-chamfer-top`, the mouth),
2. a straight vertical section (`--profile-straight`),
3. a bottom chamfer (`--profile-chamfer-bottom`) down to the narrow foot.

The defaults match the standard Gridfinity baseplate profile. Because the outer
footprint stays flush at `pitch × cells`, tiled plates line up on the 42 mm grid
and a bin spanning a seam still seats.

## Magnet pockets and printing round holes

Magnets can mount two ways:

- **Horizontal** (default) — blind pockets drilled inward from the four outer
  edges, so magnets pull neighbouring frames together edge-to-edge.
- **Vertical** (`--magnet-orientation vertical`) — pockets drilled up into the
  bottom face, matching the Gridfinity convention of magnets near the base.
  Requires a floor (`--floor`) to seat into.

A horizontal hole is printed as an overhang: the top of the circle is
unsupported and sags, so the bore comes out oval ("smushed") and a magnet may
not fit. Two things address this:

1. **Teardrop shape (default).** The pocket gets a pointed roof at
   `--magnet-teardrop-angle` (45° by default). The sloped roof is a printable
   overhang, so nothing sags and the round lower part still seats the magnet.
   Use `--magnet-shape round` to get a plain cylinder instead.
2. **Vertical mount.** Bottom-face pockets print as flat circles on each layer,
   so they stay perfectly round with no overhang — the most robust option.

Print-side tips (no design change) that also help: enable your slicer's **hole
horizontal expansion** (Bambu Studio: Quality → Precision), slow down and cool
the bridging layers, orient the part so holes point up where practical, or ream
the hole to size after printing as a fallback.

## Connectors

Connectors are vertical dovetails placed at the midpoint of each outer edge:
the `+X` and `+Y` edges receive female slots; the `-X` and `-Y` edges receive
male tabs. Because the tab and slot are generated from the same profile, a tab
on one frame mates the slot on its neighbour by construction. The male tab is
undersized by `--connector-clearance` per side so it slides rather than jams.

## Mesh inspection tool

`meshtools` is a general-purpose, reusable mesh analyzer (built on `trimesh`)
for measuring reference parts. It reports bounding box, volume, watertightness,
and cross-section profiles along an axis — useful for reverse-engineering a
part's dimensions.

```bash
cd src

# Summary of any mesh
python -m bingrid.meshtools.cli path/to/part.stl

# Cross-section profile sweep along Z
python -m bingrid.meshtools.cli path/to/part.stl --profile --axis z --step 0.5
```

From code:

```python
from bingrid.meshtools import MeshInspector

insp = MeshInspector.load("part.stl")
print(insp.extents, insp.volume, insp.is_watertight)
for slice_ in insp.profile(axis="z", step=0.25):
    print(slice_.position, slice_.solid_area, slice_.hole_count)
```

## Architecture

The package follows SOLID/DRY principles with clear responsibility boundaries:

```
src/bingrid/
├── __init__.py       # Public API (GridConfig, GridfinityPlate, ...)
├── config.py         # Validated value objects (GridConfig, GridfinityProfile,
│                     #   MagnetConfig, TaperConfig, ConnectorConfig)
├── geometry.py       # GridfinityPlate + pluggable PlateFeature classes
│                     #   (CellOpeningFeature, MagnetPocketFeature, ConnectorFeature)
├── exporter.py       # ModelExporter — STL/STEP output and file naming
├── cli.py            # Argument parsing and composition root
└── meshtools/
    ├── inspector.py  # MeshInspector — mesh measurement and profiling
    └── cli.py        # Mesh inspection CLI
```

Each feature is a `PlateFeature` applied to the running solid, so new features
(stacking lips, labels, baseplate feet) can be added as classes without
modifying the builder (Open/Closed Principle).

## Development

```bash
# Fast tests (pure logic + mesh measurement, no CadQuery render)
pytest

# Integration tests that build and export solids, incl. the BGG profile match
pytest -m integration
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
We welcome bug reports and feature requests.

## License

Add your license here.
