"""Backward-compatible entry point for the original 2x2 magnetic frame.

The real, configurable implementation now lives in the ``bingrid`` package.
This shim preserves the old behaviour and run command:

    python gridfinity_2x2_open_magnetic.py

For full configurability (grid size, magnets, taper), prefer the CLI:

    python -m bingrid.cli --help
"""
from pathlib import Path

try:  # Allow running both as a module and as a loose script.
    from . import GridConfig, GridfinityPlate, MagnetConfig, ModelExporter
except ImportError:  # pragma: no cover - script-style execution fallback
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from bingrid import GridConfig, GridfinityPlate, MagnetConfig, ModelExporter


def default_config() -> GridConfig:
    """The original 2x2 open magnetic frame, now with the Gridfinity socket."""
    return GridConfig(
        grid_x=2,
        grid_y=2,
        pitch=42.0,
        wall=5.0,
        height=5.0,
        magnet=MagnetConfig(diameter=3.0, depth=1.0),
    )


if __name__ == "__main__":
    config = default_config()
    model = GridfinityPlate(config).build()
    exporter = ModelExporter(Path(__file__).resolve().parents[2] / ".output")
    for path in exporter.export(model, config):
        print("Exported", path)
