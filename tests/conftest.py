"""Shared test helpers: independent oracles and layout validators.

The oracles deliberately share no code with the library. They are brute-force
enumerations of every possible placement, so a test comparing the two is testing
the CP-SAT model against the definition of the problem rather than against
itself. They are exponential, hence only usable on small terrains -- the larger
optima in the suite were checked once, offline, with the same method vectorised.
"""

from __future__ import annotations

from itertools import combinations

import pytest

from mcfarm_opt import BlockType, FarmLayout

ORTHOGONAL_STEPS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def _rows_of(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def free_cells_of(text: str) -> list[tuple[int, int]]:
    """The (row, col) of every '.' in a terrain string."""
    return [
        (r, c) for r, row in enumerate(_rows_of(text)) for c, char in enumerate(row) if char == "."
    ]


def obstacle_cells_of(text: str) -> set[tuple[int, int]]:
    """The (row, col) of every '#' in a terrain string."""
    return {
        (r, c) for r, row in enumerate(_rows_of(text)) for c, char in enumerate(row) if char == "#"
    }


def _check_size(text: str, max_free: int) -> list[tuple[int, int]]:
    free = free_cells_of(text)
    if len(free) > max_free:
        raise ValueError(
            f"terrain has {len(free)} free cells; brute force is exponential and "
            f"capped at {max_free}"
        )
    return free


def brute_force_sugarcane_optimum(text: str, *, max_free: int = 16) -> int:
    """Return the true maximum sugarcane count, by exhaustive enumeration.

    Tries every subset of the free cells as the water set. For each, a cell
    yields cane iff it is free, not water, and orthogonally touches water.

    Raises:
        ValueError: if the terrain has more than ``max_free`` free cells.
    """
    free = _check_size(text, max_free)
    free_set = set(free)
    best = 0
    for size in range(len(free) + 1):
        for water in combinations(free, size):
            water_set = set(water)
            count = sum(
                1
                for (r, c) in free_set - water_set
                if any((r + dr, c + dc) in water_set for dr, dc in ORTHOGONAL_STEPS)
            )
            best = max(best, count)
    return best


def brute_force_cactus_optimum(text: str, *, max_free: int = 16) -> int:
    """Return the true maximum cactus count, by exhaustive enumeration.

    Tries every subset of the free cells as the cactus set and keeps the largest
    legal one. A set is legal when no cactus touches another cactus, and no
    cactus touches an obstacle -- both are solid, and solid breaks cactus.

    Sizes are tried largest-first, so the first legal set found is the optimum.

    Raises:
        ValueError: if the terrain has more than ``max_free`` free cells.
    """
    free = _check_size(text, max_free)
    obstacles = obstacle_cells_of(text)

    def legal(cacti: set[tuple[int, int]]) -> bool:
        for r, c in cacti:
            for dr, dc in ORTHOGONAL_STEPS:
                neighbor = (r + dr, c + dc)
                if neighbor in cacti or neighbor in obstacles:
                    return False
        return True

    for size in range(len(free), -1, -1):
        for combo in combinations(free, size):
            if legal(set(combo)):
                return size
    return 0


def assert_valid_sugarcane(layout: FarmLayout) -> None:
    """Assert the layout obeys every sugarcane rule.

    Checks the four things the model promises: obstacles are untouched, free
    cells are not obstacles, every cane has orthogonal water, and the metrics
    agree with the rendered grid.
    """
    grid = layout.grid
    for cell in grid.cells():
        block = layout.block_at(cell)

        if grid.is_obstacle(cell):
            assert block is BlockType.OBSTACLE, f"obstacle at {cell} was overwritten with {block}"
            continue
        assert block is not BlockType.OBSTACLE, f"free cell {cell} was turned into an obstacle"

        if block is BlockType.CROP:
            neighbors = grid.neighbors(cell)
            assert any(layout.block_at(n) is BlockType.WATER for n in neighbors), (
                f"cane at {cell} has no orthogonally adjacent water"
            )

    metrics = layout.metrics
    assert metrics.n_crop == len(layout.cells_with(BlockType.CROP))
    assert metrics.n_support == len(layout.cells_with(BlockType.WATER))
    assert metrics.n_obstacle == len(layout.cells_with(BlockType.OBSTACLE))
    assert metrics.n_cells == len(grid)


def assert_valid_cactus(layout: FarmLayout) -> None:
    """Assert the layout obeys every cactus rule.

    The rule is the whole checklist: obstacles untouched, free cells not turned
    into obstacles, and no cactus with a solid block beside it -- where solid, at
    cactus level, means another cactus or an obstacle.
    """
    grid = layout.grid
    for cell in grid.cells():
        block = layout.block_at(cell)

        if grid.is_obstacle(cell):
            assert block is BlockType.OBSTACLE, f"obstacle at {cell} was overwritten with {block}"
            continue
        assert block is not BlockType.OBSTACLE, f"free cell {cell} was turned into an obstacle"

        if block is BlockType.CROP:
            for neighbor in grid.neighbors(cell):
                assert layout.block_at(neighbor) is not BlockType.CROP, (
                    f"cactus at {cell} touches another cactus at {neighbor}"
                )
                assert layout.block_at(neighbor) is not BlockType.OBSTACLE, (
                    f"cactus at {cell} touches an obstacle at {neighbor}"
                )

    metrics = layout.metrics
    assert metrics.n_crop == len(layout.cells_with(BlockType.CROP))
    assert metrics.n_obstacle == len(layout.cells_with(BlockType.OBSTACLE))
    assert metrics.n_cells == len(grid)


@pytest.fixture
def rectangle():
    """Build an all-free terrain string of the given size."""

    def _make(height: int, width: int) -> str:
        return "\n".join("." * width for _ in range(height))

    return _make
