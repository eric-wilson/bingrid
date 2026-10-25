"""CLI for inspecting mesh files.

    python -m bingrid.meshtools.cli samples/part.stl
    python -m bingrid.meshtools.cli samples/part.stl --profile --axis z --step 0.25
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .inspector import MeshInspector


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect a mesh file (STL/OBJ/PLY/3MF): size, volume, profile.",
    )
    parser.add_argument("path", type=Path, help="path to the mesh file")
    parser.add_argument(
        "--profile", action="store_true",
        help="print a cross-section profile sweep along --axis",
    )
    parser.add_argument(
        "--axis", choices=["x", "y", "z"], default="z",
        help="slice axis for --profile (default: z)",
    )
    parser.add_argument(
        "--step", type=float, default=0.25,
        help="profile sampling interval in model units (default: 0.25)",
    )
    parser.add_argument(
        "--no-normalize", dest="normalize", action="store_false",
        help="do not recenter/drop the mesh to the origin before measuring",
    )
    parser.set_defaults(normalize=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.path.exists():
        print(f"error: file not found: {args.path}")
        return 2

    inspector = MeshInspector.load(args.path, normalize=args.normalize)

    ext = inspector.extents
    lo, hi = inspector.bounds
    print(f"file:        {args.path}")
    print(f"extents:     {ext[0]:.3f} x {ext[1]:.3f} x {ext[2]:.3f}")
    print(f"bounds min:  ({lo[0]:.3f}, {lo[1]:.3f}, {lo[2]:.3f})")
    print(f"bounds max:  ({hi[0]:.3f}, {hi[1]:.3f}, {hi[2]:.3f})")
    print(f"volume:      {inspector.volume:.2f}")
    print(f"watertight:  {inspector.is_watertight}")

    if args.profile:
        print(f"\nprofile along {args.axis} (step {args.step}):")
        print(f"{'pos':>8}  {'outer_a':>8}  {'outer_b':>8}  {'holes':>5}  {'area':>10}")
        for p in inspector.profile(axis=args.axis, step=args.step):
            print(f"{p.position:8.3f}  {p.outer[0]:8.3f}  {p.outer[1]:8.3f}  "
                  f"{p.hole_count:5d}  {p.solid_area:10.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
