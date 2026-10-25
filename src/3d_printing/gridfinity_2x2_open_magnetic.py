"""Parametric open-bottom Gridfinity-style 2x2 frame with side magnet pockets.
Run: python gridfinity_2x2_open_magnetic.py
Requires: cadquery (pip install cadquery)
Outputs: STL and STEP alongside this script.
NOTE: This is a customizable open frame, not a validated Gridfinity seating profile.
"""
from pathlib import Path
import cadquery as cq

GRID_X = 2
GRID_Y = 2
PITCH = 42.0                 # Gridfinity cell pitch, mm
HEIGHT = 8.0                 # Needed for horizontal 6mm magnet pockets
WALL = 5.0                   # Outer border and cross bars, mm
MAGNETS = True
MAGNET_DIAMETER = 6.0
MAGNET_CLEARANCE = 0.2        # Diameter clearance, mm
MAGNET_DEPTH = 2.3           # For 2mm-thick magnets and glue
MAGNETS_PER_SIDE = 2         # One at each cell center for 2x2


def make_plate():
    width = GRID_X * PITCH
    length = GRID_Y * PITCH
    model = cq.Workplane('XY').box(width, length, HEIGHT, centered=(True, True, False))
    # Openings are fully through the plate, leaving the outer rim and crossbars.
    for i in range(GRID_X):
        for j in range(GRID_Y):
            cx = -width/2 + (i + 0.5) * PITCH
            cy = -length/2 + (j + 0.5) * PITCH
            opening = (cq.Workplane('XY').center(cx, cy)
                       .box(PITCH - WALL, PITCH - WALL, HEIGHT + 2,
                            centered=(True, True, False))
                       .translate((0, 0, -1)))
            model = model.cut(opening)

    if MAGNETS:
        radius = (MAGNET_DIAMETER + MAGNET_CLEARANCE)/2
        if HEIGHT <= 2 * radius or WALL <= MAGNET_DEPTH:
            raise ValueError('Increase HEIGHT or WALL to accommodate magnet pockets')
        # Blind horizontal holes from all four outside edges.
        for i in range(GRID_X):
            x = -width/2 + (i + 0.5) * PITCH
            for y, direction in ((-length/2, (0, 1, 0)),
                                 ( length/2, (0,-1, 0))):
                pocket = cq.Solid.makeCylinder(radius, MAGNET_DEPTH,
                                                cq.Vector(x, y, HEIGHT/2),
                                                cq.Vector(*direction))
                model = model.cut(pocket)
        for j in range(GRID_Y):
            y = -length/2 + (j + 0.5) * PITCH
            for x, direction in ((-width/2, (1, 0, 0)),
                                 ( width/2, (-1,0, 0))):
                pocket = cq.Solid.makeCylinder(radius, MAGNET_DEPTH,
                                                cq.Vector(x, y, HEIGHT/2),
                                                cq.Vector(*direction))
                model = model.cut(pocket)
    return model


if __name__ == '__main__':
    plate = make_plate()
    root = Path(__file__).resolve().parent
    cq.exporters.export(plate, str(root / 'gridfinity_2x2_open_magnetic.stl'), tolerance=0.05, angularTolerance=0.15)
    cq.exporters.export(plate, str(root / 'gridfinity_2x2_open_magnetic.step'))
    print('Exported STL and STEP to', root)
