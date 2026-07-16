"""Exact solver built on OR-Tools CP-SAT.

Why CP-SAT and not an LP relaxation
-----------------------------------

The model is a pure 0/1 program -- a cell either holds a block or it does not,
and "at least one adjacent water" is a disjunction. Its LP relaxation is weak
(fractional half-water everywhere satisfies every adjacency constraint at half
the cost), so a branch-and-bound over that relaxation explores a lot of useless
territory. CP-SAT propagates the reified constraints directly and proves
optimality on realistic terrains in well under a second.

The name ``ilp`` is kept because the *formulation* is an integer program; the
engine underneath is a lazy-clause-generation CP solver.
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Grid
from mcfarm_opt.core.result import FarmLayout, FarmMetrics, SolveStatus
from mcfarm_opt.core.variables import CellVars
from mcfarm_opt.crops.base import CropRule

__all__ = ["ILPSolver"]

_STATUS_MAP: dict[int, SolveStatus] = {
    cp_model.OPTIMAL: SolveStatus.OPTIMAL,
    cp_model.FEASIBLE: SolveStatus.FEASIBLE,
    cp_model.INFEASIBLE: SolveStatus.INFEASIBLE,
    cp_model.MODEL_INVALID: SolveStatus.UNKNOWN,
    cp_model.UNKNOWN: SolveStatus.UNKNOWN,
}


class ILPSolver:
    """Solves the layout problem exactly with CP-SAT.

    Args:
        workers: search threads. Leave this alone unless you have measured a
            reason not to. CP-SAT runs a *portfolio* of different strategies
            across its workers, not one strategy split N ways, and the
            bound-proving strategies live on the higher workers -- so dropping
            to ``workers=1`` does not cost a factor of 8, it costs the
            strategies that close the proof. Measured on a 10x8 terrain: 0.06s
            to proven optimality with 8 workers, still unproven after 60s with
            1. ``workers=1`` buys only run-to-run determinism, and only pay for
            it on terrains small enough not to notice.
        log_search: stream CP-SAT's search log to stdout. For debugging a slow
            model.

    Example:
        >>> from mcfarm_opt import Grid, Sugarcane
        >>> from mcfarm_opt.solvers.ilp import ILPSolver
        >>> layout = ILPSolver().solve(Grid.from_text("...\\n...\\n"), Sugarcane())
        >>> layout.metrics.is_optimal
        True
    """

    def __init__(self, *, workers: int = 8, log_search: bool = False) -> None:
        if workers < 1:
            raise ValueError(f"workers must be at least 1, got {workers}")
        self._workers = workers
        self._log_search = log_search

    @property
    def name(self) -> str:
        """``"ilp"``."""
        return "ilp"

    def solve(
        self,
        grid: Grid,
        crop: CropRule,
        *,
        time_limit: float | None = None,
    ) -> FarmLayout:
        """Build the model, solve it, and package the answer.

        See :meth:`mcfarm_opt.solvers.base.Solver.solve` for the contract.

        Raises:
            ValueError: if ``time_limit`` is not positive.
            RuntimeError: if CP-SAT reports the model itself is invalid, which
                would mean a crop rule emitted something malformed.
        """
        if time_limit is not None and time_limit <= 0:
            raise ValueError(f"time_limit must be positive, got {time_limit}")

        model = cp_model.CpModel()
        variables = CellVars(model, grid, crop.block_types())
        crop.add_constraints(model, variables, grid)

        terms = crop.objective_terms(model, variables, grid)
        if terms:
            model.Maximize(sum(term.weight * term.var for term in terms))

        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = self._workers
        solver.parameters.log_search_progress = self._log_search
        if time_limit is not None:
            solver.parameters.max_time_in_seconds = time_limit

        raw_status = solver.Solve(model)
        if raw_status == cp_model.MODEL_INVALID:  # pragma: no cover - defensive
            raise RuntimeError(
                f"CP-SAT rejected the model built for {crop.name!r}: "
                f"{model.Validate()}"
            )
        status = _STATUS_MAP.get(raw_status, SolveStatus.UNKNOWN)

        # An unsolved model has no values to read, so fall back to the empty
        # layout -- every free cell EMPTY -- rather than crashing the caller.
        if status.is_solved:
            assignment = dict(variables.extract(solver))
        else:
            assignment = {
                cell: BlockType.OBSTACLE if grid.is_obstacle(cell) else BlockType.EMPTY
                for cell in grid.cells()
            }

        return FarmLayout(
            grid=grid,
            assignment=assignment,
            metrics=self._metrics(grid, crop, assignment, solver.WallTime(), status),
            crop_name=crop.name,
        )

    @staticmethod
    def _metrics(
        grid: Grid,
        crop: CropRule,
        assignment: dict,
        wall_time: float,
        status: SolveStatus,
    ) -> FarmMetrics:
        """Count the blocks of a finished assignment.

        Support is "placed, and not the crop itself" rather than a fixed list,
        so a crop that grows on farmland reports its farmland without this
        function having to know what farmland is.
        """
        crop_blocks = crop.crop_blocks()
        support_blocks = crop.block_types() - crop_blocks

        n_crop = n_support = n_empty = n_obstacle = 0
        for block in assignment.values():
            if block in crop_blocks:
                n_crop += 1
            elif block in support_blocks:
                n_support += 1
            elif block is BlockType.OBSTACLE:
                n_obstacle += 1
            else:
                n_empty += 1

        return FarmMetrics(
            n_crop=n_crop,
            n_support=n_support,
            n_empty=n_empty,
            n_obstacle=n_obstacle,
            solve_time=wall_time,
            status=status,
        )
