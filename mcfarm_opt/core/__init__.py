"""Crop-agnostic building blocks: terrain, block types, variables, results.

Nothing in this package knows what a crop is or what makes a cell plantable.
That knowledge lives in :mod:`mcfarm_opt.crops`.
"""

from __future__ import annotations

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Cell, Grid, Neighborhood
from mcfarm_opt.core.result import FarmLayout, FarmMetrics, SolveStatus
from mcfarm_opt.core.variables import CellVars

__all__ = [
    "BlockType",
    "Cell",
    "CellVars",
    "FarmLayout",
    "FarmMetrics",
    "Grid",
    "Neighborhood",
    "SolveStatus",
]
