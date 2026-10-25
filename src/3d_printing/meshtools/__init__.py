"""Reusable mesh inspection utilities built on trimesh.

General-purpose tools for analyzing STL/OBJ/PLY/3MF meshes: bounding box,
volume, watertightness, and cross-section profiles along an axis. Handy for
reverse-engineering a reference part's dimensions.

Public API:
    MeshInspector  -- load a mesh and query its geometry
    SliceProfile   -- per-height cross-section measurements
"""
from .inspector import MeshInspector, SliceProfile

__all__ = ["MeshInspector", "SliceProfile"]
