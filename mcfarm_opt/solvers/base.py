"""The solver interface.

A solver takes a terrain and a crop and returns the best layout it can find.
Only an exact CP-SAT solver ships today (:mod:`mcfarm_opt.solvers.ilp`);
heuristic solvers for terrains too large to solve exactly will implement this
same protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mcfarm_opt.core.grid import Grid
from mcfarm_opt.core.result import FarmLayout
from mcfarm_opt.crops.base import CropRule

__all__ = ["Solver"]


@runtime_checkable
class Solver(Protocol):
    """Something that can lay out a farm."""

    @property
    def name(self) -> str:
        """Human-readable solver name."""
        ...

    def solve(
        self,
        grid: Grid,
        crop: CropRule,
        *,
        time_limit: float | None = None,
    ) -> FarmLayout:
        """Return the best layout of ``crop`` on ``grid`` that this solver finds.

        Args:
            grid: the terrain to fill.
            crop: the crop whose rules constrain the layout.
            time_limit: seconds to search before returning the best layout so
                far. ``None`` means no limit. An exact solver that is cut short
                reports :attr:`~mcfarm_opt.core.result.SolveStatus.FEASIBLE`
                rather than ``OPTIMAL``; a heuristic never reports ``OPTIMAL``
                at all.

        A solver must always return a layout for a satisfiable problem, and an
        empty terrain is always satisfiable -- leaving every cell EMPTY is a
        valid, if useless, farm. Implementations should not raise merely
        because the answer is zero crops.
        """
        ...
