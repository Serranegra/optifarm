"""The 2D terrain grid: cells, obstacles and neighbourhoods.

The grid knows nothing about crops. It only answers two kinds of question:

* is this cell free or blocked?
* which cells lie within distance *r* of this one, under a given metric?

Everything crop-specific (what counts as a valid neighbour, how far water
reaches) lives in :mod:`mcfarm_opt.crops`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum

__all__ = ["Cell", "Grid", "Neighborhood"]


@dataclass(frozen=True, slots=True, order=True)
class Cell:
    """A position on the grid, indexed from the top-left corner."""

    row: int
    col: int

    def __str__(self) -> str:  # pragma: no cover - debugging convenience
        return f"({self.row},{self.col})"


class Neighborhood(Enum):
    """The distance metric used to decide which cells are "near" a cell.

    The two metrics differ only in whether diagonal steps cost anything:

    ``ORTHOGONAL``
        Manhattan distance, ``|dr| + |dc| <= radius`` (a von Neumann
        neighbourhood). At ``radius=1`` this is the four N/S/E/W cells --
        the relationship sugarcane needs with water.

    ``DIAGONAL``
        Chebyshev distance, ``max(|dr|, |dc|) <= radius`` (a Moore
        neighbourhood). At ``radius=1`` this is the eight surrounding cells;
        at ``radius=4`` it is the 9x9 square that matches Minecraft's farmland
        hydration range, which is what wheat will need.

    Both metrics exclude the centre cell itself.
    """

    ORTHOGONAL = "orthogonal"
    DIAGONAL = "diagonal"

    def distance(self, a: Cell, b: Cell) -> int:
        """Return the distance between ``a`` and ``b`` under this metric."""
        dr = abs(a.row - b.row)
        dc = abs(a.col - b.col)
        if self is Neighborhood.ORTHOGONAL:
            return dr + dc
        return max(dr, dc)


class Grid:
    """A rectangular terrain of free and blocked cells.

    Args:
        blocked: the set of cells that are obstacles.
        height: number of rows.
        width: number of columns.

    A grid is immutable once built. Use :meth:`from_text` (or
    :func:`mcfarm_opt.io.text.parse_grid`) to build one from the text format.
    """

    __slots__ = ("_blocked", "_height", "_width")

    def __init__(self, height: int, width: int, blocked: frozenset[Cell] = frozenset()) -> None:
        if height < 0 or width < 0:
            raise ValueError(f"grid dimensions must be non-negative, got {height}x{width}")
        self._height = height
        self._width = width
        self._blocked = frozenset(blocked)
        for cell in self._blocked:
            if not self.contains(cell):
                raise ValueError(f"blocked cell {cell} is outside a {height}x{width} grid")

    @classmethod
    def from_text(cls, text: str) -> Grid:
        """Parse a grid from the multi-line text format.

        See :func:`mcfarm_opt.io.text.parse_grid`, which this delegates to.
        """
        from mcfarm_opt.io.text import parse_grid

        return parse_grid(text)

    @property
    def height(self) -> int:
        """Number of rows."""
        return self._height

    @property
    def width(self) -> int:
        """Number of columns."""
        return self._width

    @property
    def shape(self) -> tuple[int, int]:
        """``(height, width)``."""
        return self._height, self._width

    def __len__(self) -> int:
        """Total number of cells, free and blocked."""
        return self._height * self._width

    def contains(self, cell: Cell) -> bool:
        """Whether ``cell`` lies inside the grid bounds."""
        return 0 <= cell.row < self._height and 0 <= cell.col < self._width

    def is_obstacle(self, cell: Cell) -> bool:
        """Whether ``cell`` is blocked terrain.

        Cells outside the grid are *not* obstacles; they simply do not exist
        and are never returned by :meth:`cells` or :meth:`neighbors`.
        """
        return cell in self._blocked

    def is_free(self, cell: Cell) -> bool:
        """Whether ``cell`` is inside the grid and not an obstacle."""
        return self.contains(cell) and cell not in self._blocked

    def cells(self) -> Iterator[Cell]:
        """Every cell, in row-major order, obstacles included."""
        for row in range(self._height):
            for col in range(self._width):
                yield Cell(row, col)

    def free_cells(self) -> Iterator[Cell]:
        """Every non-obstacle cell, in row-major order."""
        return (cell for cell in self.cells() if cell not in self._blocked)

    def obstacles(self) -> Iterator[Cell]:
        """Every obstacle cell, in row-major order."""
        return (cell for cell in self.cells() if cell in self._blocked)

    def neighbors(
        self,
        cell: Cell,
        neighborhood: Neighborhood = Neighborhood.ORTHOGONAL,
        radius: int = 1,
        *,
        include_obstacles: bool = True,
    ) -> list[Cell]:
        """Return the in-bounds cells within ``radius`` of ``cell``.

        The centre cell is never included. Results are in row-major order, so
        the output is deterministic -- which in turn makes the CP-SAT model
        built from it deterministic.

        Args:
            cell: the centre cell. It need not be free, or even in bounds.
            neighborhood: the metric deciding what "within radius" means.
            radius: the maximum distance, in the given metric.
            include_obstacles: if ``False``, obstacle cells are filtered out.
                Crops that count *positive* support (sugarcane looking for
                water) do not care either way, since an obstacle can never
                hold water. Crops that count *negative* support (cactus
                avoiding solids) very much do -- an obstacle is a solid.

        Raises:
            ValueError: if ``radius`` is negative.
        """
        if radius < 0:
            raise ValueError(f"radius must be non-negative, got {radius}")

        found: list[Cell] = []
        for dr in range(-radius, radius + 1):
            row = cell.row + dr
            if not 0 <= row < self._height:
                continue
            if neighborhood is Neighborhood.ORTHOGONAL:
                span = radius - abs(dr)
            else:
                span = radius
            for dc in range(-span, span + 1):
                col = cell.col + dc
                if not 0 <= col < self._width:
                    continue
                if dr == 0 and dc == 0:
                    continue
                candidate = Cell(row, col)
                if not include_obstacles and candidate in self._blocked:
                    continue
                found.append(candidate)
        return found

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"Grid(height={self._height}, width={self._width}, obstacles={len(self._blocked)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Grid):
            return NotImplemented
        return (
            self._height == other._height
            and self._width == other._width
            and self._blocked == other._blocked
        )

    def __hash__(self) -> int:
        return hash((self._height, self._width, self._blocked))
