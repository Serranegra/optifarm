"""Parsing terrain from text and rendering layouts back to it.

The input alphabet is deliberately tiny -- terrain is either free or it is not::

    .  free
    #  obstacle

The output alphabet is the block symbols of :class:`~mcfarm_opt.core.blocks.BlockType`::

    W  water        C  crop
    .  free, unused  #  obstacle
    S  sand         F  farmland
    M  melon

Blank lines are ignored and trailing whitespace is stripped, so a grid can be
written as an indented triple-quoted string in a test without ceremony. Rows
must all be the same length: a ragged grid is far more likely to be a typo than
an intent, and there is no sensible way to guess the missing cells.
"""

from __future__ import annotations

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Cell, Grid
from mcfarm_opt.core.result import FarmLayout

__all__ = ["FREE_SYMBOL", "OBSTACLE_SYMBOL", "parse_grid", "render_grid", "render_layout"]

FREE_SYMBOL = "."
"""Input character for free terrain."""

OBSTACLE_SYMBOL = "#"
"""Input character for blocked terrain."""


def parse_grid(text: str) -> Grid:
    """Parse a multi-line terrain string into a :class:`Grid`.

    Args:
        text: the terrain. ``'.'`` marks a free cell, ``'#'`` an obstacle.
            Leading/trailing blank lines are ignored; each line is stripped of
            trailing whitespace before parsing.

    Returns:
        The parsed grid. An empty or all-blank string yields a 0x0 grid, which
        every solver handles as "no cells, no crops".

    Raises:
        ValueError: if rows have differing lengths, or an unknown character
            appears.

    Example:
        >>> from mcfarm_opt import Cell, parse_grid
        >>> grid = parse_grid(".#.\\n...")
        >>> grid.shape
        (2, 3)
        >>> grid.is_obstacle(Cell(0, 1))
        True
    """
    lines = [line.rstrip() for line in text.splitlines()]
    rows = [line for line in lines if line.strip()]
    if not rows:
        return Grid(height=0, width=0)

    width = len(rows[0])
    blocked: set[Cell] = set()
    for r, row in enumerate(rows):
        if len(row) != width:
            raise ValueError(
                f"row {r} has {len(row)} cells but row 0 has {width}; "
                f"the terrain must be rectangular"
            )
        for c, char in enumerate(row):
            if char == OBSTACLE_SYMBOL:
                blocked.add(Cell(r, c))
            elif char != FREE_SYMBOL:
                raise ValueError(
                    f"unknown terrain character {char!r} at row {r}, column {c}; "
                    f"expected {FREE_SYMBOL!r} (free) or {OBSTACLE_SYMBOL!r} (obstacle)"
                )

    return Grid(height=len(rows), width=width, blocked=frozenset(blocked))


def render_grid(grid: Grid) -> str:
    """Render bare terrain back to the input format.

    The result round-trips: ``parse_grid(render_grid(g)) == g``.
    """
    return "\n".join(
        "".join(
            OBSTACLE_SYMBOL if grid.is_obstacle(Cell(r, c)) else FREE_SYMBOL
            for c in range(grid.width)
        )
        for r in range(grid.height)
    )


def render_layout(layout: FarmLayout) -> str:
    """Render a solved layout to text, one character per cell.

    Each cell shows the symbol of the block assigned to it. A 0x0 grid renders
    as the empty string.

    Note:
        Ties between equally-optimal layouts are broken by the parallel search,
        so the exact characters vary between runs on the same terrain. Test
        against ``metrics.n_crop``, or against the rules the layout must obey --
        not against a golden rendering.

    Example:
        >>> from mcfarm_opt import optimize, Sugarcane
        >>> print(optimize("..\\n..", crop=Sugarcane()).render())  # doctest: +SKIP
        CW
        WC
    """
    grid = layout.grid
    return "\n".join(
        "".join(
            layout.assignment.get(Cell(r, c), BlockType.EMPTY).symbol for c in range(grid.width)
        )
        for r in range(grid.height)
    )
