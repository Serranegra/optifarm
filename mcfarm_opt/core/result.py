"""The output of an optimisation run: the chosen layout plus its metrics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Cell, Grid

__all__ = ["FarmLayout", "FarmMetrics", "SolveStatus"]


class SolveStatus(Enum):
    """How the solver finished.

    ``OPTIMAL``
        The reported layout is provably the best possible one.
    ``FEASIBLE``
        A valid layout, but the solver hit its time limit before proving
        optimality. The crop count is a lower bound on the true optimum.
    ``INFEASIBLE``
        No valid layout exists at all. For the crops modelled here this cannot
        happen -- leaving every cell EMPTY is always valid -- but a future crop
        with mandatory placement could trigger it.
    ``UNKNOWN``
        The solver found nothing before running out of time.
    """

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"

    @property
    def is_solved(self) -> bool:
        """Whether a usable layout was produced."""
        return self in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)


@dataclass(frozen=True, slots=True)
class FarmMetrics:
    """Summary numbers for a layout.

    Attributes:
        n_crop: cells holding the harvested crop. This is the objective value.
        n_support: cells holding a support block the crop needed (water, sand,
            farmland...). Not counted as production, but they are the cost of it.
        n_empty: free cells the layout left unused.
        n_obstacle: blocked cells. Fixed by the terrain, not by the solver.
        n_free: cells the solver was free to assign, i.e. everything but obstacles.
        solve_time: wall-clock seconds spent inside the solver.
        status: how the solver finished.
    """

    n_crop: int
    n_support: int
    n_empty: int
    n_obstacle: int
    solve_time: float
    status: SolveStatus

    @property
    def n_free(self) -> int:
        """Cells the solver could assign: crop + support + empty."""
        return self.n_crop + self.n_support + self.n_empty

    @property
    def n_cells(self) -> int:
        """Every cell of the terrain, obstacles included."""
        return self.n_free + self.n_obstacle

    @property
    def efficiency(self) -> float:
        """Percentage of *usable* terrain that ended up growing crop.

        The denominator is the free cells, not the whole grid: a terrain that is
        90% obstacle should not be reported as a 10%-efficient farm when the
        layout in fact used every square it was given. A grid with no free cells
        at all scores 0.0 rather than raising.
        """
        if self.n_free == 0:
            return 0.0
        return 100.0 * self.n_crop / self.n_free

    @property
    def is_optimal(self) -> bool:
        """Whether ``n_crop`` is proven maximal."""
        return self.status is SolveStatus.OPTIMAL

    def __str__(self) -> str:
        return (
            f"crop={self.n_crop} support={self.n_support} empty={self.n_empty} "
            f"obstacle={self.n_obstacle} efficiency={self.efficiency:.1f}% "
            f"status={self.status.value} time={self.solve_time:.3f}s"
        )


@dataclass(frozen=True, slots=True)
class FarmLayout:
    """A block assignment over a grid, with the metrics that describe it.

    Attributes:
        grid: the terrain that was optimised.
        assignment: the block chosen for every cell of ``grid``.
        metrics: the summary numbers, see :class:`FarmMetrics`.
        crop_name: the crop this layout grows, for display.
    """

    grid: Grid
    assignment: Mapping[Cell, BlockType]
    metrics: FarmMetrics
    crop_name: str

    def block_at(self, cell: Cell) -> BlockType:
        """Return the block assigned to ``cell``.

        Raises:
            KeyError: if ``cell`` is not part of the grid.
        """
        try:
            return self.assignment[cell]
        except KeyError:
            raise KeyError(f"cell {cell} is not part of this {self.grid!r}") from None

    def cells_with(self, block: BlockType) -> list[Cell]:
        """Every cell holding ``block``, in row-major order."""
        return [cell for cell in self.grid.cells() if self.assignment[cell] is block]

    def render(self) -> str:
        """Render the layout as a multi-line string.

        See :func:`mcfarm_opt.io.text.render_layout`, which this delegates to.
        """
        from mcfarm_opt.io.text import render_layout

        return render_layout(self)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.render()
