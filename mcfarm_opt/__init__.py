"""optifarm -- optimal Minecraft farm layouts.

Given a terrain and a crop, compute the block layout that maximises production,
exactly, with an OR-Tools CP-SAT model.

Example:
    >>> from mcfarm_opt import optimize, Sugarcane
    >>> layout = optimize(".....\\n.....\\n.....", crop=Sugarcane(), solver="ilp")
    >>> layout.metrics.n_crop
    11
    >>> layout.metrics.is_optimal
    True
    >>> print(layout.render())  # doctest: +SKIP
    CCWCC
    WCCCW
    CCWCC

Note:
    A terrain usually has many layouts achieving the optimum, and which one the
    parallel search returns varies between runs. ``metrics.n_crop`` is
    reproducible; the exact rendering is not. Assert on the count, not on the
    picture. (``ILPSolver(workers=1)`` *is* deterministic, but it gives up the
    solver's portfolio and is orders of magnitude slower -- a 10x8 terrain it
    cannot finish in a minute takes 0.06s on the default. It is not a
    reproducibility knob worth reaching for.)

The library is organised so that a new crop is a new
:class:`~mcfarm_opt.crops.base.CropRule` and nothing else:

* :mod:`mcfarm_opt.core` -- terrain, blocks, variables, results. Crop-agnostic.
* :mod:`mcfarm_opt.crops` -- what makes a cell plantable. One module per crop.
* :mod:`mcfarm_opt.solvers` -- how the model is searched.
* :mod:`mcfarm_opt.io` -- text in, text out.
"""

from __future__ import annotations

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Cell, Grid, Neighborhood
from mcfarm_opt.core.result import FarmLayout, FarmMetrics, SolveStatus
from mcfarm_opt.core.variables import CellVars
from mcfarm_opt.crops.base import (
    AdjacencyCropRule,
    AdjacencyRequirement,
    CropRule,
    ObjectiveTerm,
)
from mcfarm_opt.crops.cactus import Cactus
from mcfarm_opt.crops.sugarcane import Sugarcane
from mcfarm_opt.crops.wheat import Wheat
from mcfarm_opt.io.svg import render_layout_svg
from mcfarm_opt.io.text import parse_grid, render_grid, render_layout
from mcfarm_opt.solvers.base import Solver
from mcfarm_opt.solvers.ilp import ILPSolver

__all__ = [
    "AdjacencyCropRule",
    "AdjacencyRequirement",
    "BlockType",
    "Cactus",
    "Cell",
    "CellVars",
    "CropRule",
    "FarmLayout",
    "FarmMetrics",
    "Grid",
    "ILPSolver",
    "Neighborhood",
    "ObjectiveTerm",
    "SolveStatus",
    "Solver",
    "Sugarcane",
    "Wheat",
    "optimize",
    "parse_grid",
    "render_grid",
    "render_layout",
    "render_layout_svg",
]

__version__ = "0.1.0"

_SOLVERS: dict[str, type] = {"ilp": ILPSolver}


def optimize(
    terrain: str | Grid,
    crop: CropRule | None = None,
    solver: str | Solver = "ilp",
    *,
    time_limit: float | None = None,
) -> FarmLayout:
    """Compute the best layout of ``crop`` on ``terrain``.

    Args:
        terrain: the terrain, either as a multi-line string in the text format
            (``'.'`` free, ``'#'`` obstacle) or as an already-parsed
            :class:`~mcfarm_opt.core.grid.Grid`.
        crop: the crop to grow. Defaults to :class:`Sugarcane`.
        solver: either a registered solver name (``"ilp"``) or a
            :class:`~mcfarm_opt.solvers.base.Solver` instance, which is how you
            pass a configured solver such as ``ILPSolver(workers=1)``.
        time_limit: seconds to search before giving up on proving optimality.
            ``None``, the default, means search to completion. Check
            :attr:`layout.metrics.is_optimal <FarmMetrics.is_optimal>` when you
            set one.

    Returns:
        The layout, its metrics, and the terrain it was computed for. A terrain
        with no plantable cell yields a layout of zero crops rather than an
        error.

    Raises:
        ValueError: if the terrain is malformed, or ``solver`` names a solver
            that does not exist.
    """
    grid = parse_grid(terrain) if isinstance(terrain, str) else terrain
    rule = crop if crop is not None else Sugarcane()

    if isinstance(solver, str):
        try:
            engine: Solver = _SOLVERS[solver]()
        except KeyError:
            raise ValueError(
                f"unknown solver {solver!r}; available: {sorted(_SOLVERS)}"
            ) from None
    else:
        engine = solver

    return engine.solve(grid, rule, time_limit=time_limit)
