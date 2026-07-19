"""Shared test helpers: independent oracles, layout validators, and a solve cache.

The oracles deliberately share no code with the library. They are brute-force
enumerations of every possible placement, so a test comparing the two is testing
the CP-SAT model against the definition of the problem rather than against
itself. They are exponential, hence only usable on small terrains -- the larger
optima in the suite were checked once, offline, with the same method vectorised.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from itertools import combinations

import pytest

from mcfarm_opt import (
    BlockType,
    Cactus,
    CropRule,
    FarmLayout,
    Grid,
    Melon,
    Neighborhood,
    Sugarcane,
    Wheat,
    optimize,
)

ORTHOGONAL_STEPS = ((-1, 0), (1, 0), (0, -1), (0, 1))


# ============================================================================
# Memoised solving
# ============================================================================
# Half this suite's runtime used to be spent re-deriving answers it already had.
# The 15x15 sugarcane optimum takes 12.8s to prove and five different tests each
# asked for it -- 64s of solving for 12.8s of information, on a suite that ran
# in 116s. Measured, not guessed: a plugin counted every optimize() call and
# found 58 of the 80 seconds inside the solver were recomputes.
#
# Caching costs nothing real here. These tests assert *values* -- "the optimum
# is 172", "the optimum beats the baseline" -- and a value does not change for
# being looked up twice. What caching would cost is the ability to notice the
# solver returning different answers on identical input, and that is covered
# on purpose elsewhere, by test_api.py::test_solver_is_deterministic_with_one_worker,
# which calls optimize() directly and must keep doing so.
#
# One consequence worth knowing: callers now share FarmLayout objects. They are
# frozen dataclasses over an immutable Grid, and nothing in the suite writes to
# an assignment, so sharing is safe -- but it is a real coupling, and a test that
# starts mutating a layout would poison every other test that asked for the same
# one.
#
# Under xdist each worker process keeps its own cache, so the same solve can
# still happen once per worker. That is fine: those repeats run in parallel,
# which is exactly what the workers are for.

_CROP_TYPES: dict[str, type[CropRule]] = {
    "sugarcane": Sugarcane,
    "cactus": Cactus,
    "wheat": Wheat,
    "melon": Melon,
}


@cache
def _solve_cached(terrain: str, crop_name: str, time_limit: float | None) -> FarmLayout:
    return optimize(terrain, crop=_CROP_TYPES[crop_name](), time_limit=time_limit)


def solve(terrain: str, crop: CropRule, *, time_limit: float | None = None) -> FarmLayout:
    """Optimise ``terrain`` for ``crop``, reusing the answer if it is already known.

    A drop-in for :func:`mcfarm_opt.optimize` in tests that only read the result.
    Keyed on the terrain text and the crop's name rather than the crop object,
    since crops are constructed fresh at every call site and would otherwise miss
    the cache every time.

    Do **not** use this to test the solver itself -- determinism, timing, status
    under a time limit. Call ``optimize`` directly for those.
    """
    return _solve_cached(terrain, crop.name, time_limit)


@cache
def _baseline_cached(build: Callable[[Grid], FarmLayout | None], grid: Grid) -> FarmLayout | None:
    return build(grid)


def baseline(build: Callable[[Grid], FarmLayout | None], grid: Grid) -> FarmLayout | None:
    """Run a demo's hand-built baseline, reusing the answer if it is already known.

    The same argument as :func:`solve`, for the other expensive half. The greedy
    sugarcane player costs 4.6s on the 15x15 and five tests want it. ``Grid`` is
    hashable and immutable, and the builders are module-level functions, so both
    make sound cache keys.
    """
    return _baseline_cached(build, grid)


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


def brute_force_wheat_optimum(text: str, *, max_free: int = 14) -> int:
    """Return the true maximum wheat count, by exhaustive enumeration.

    Tries every subset of the free cells as the water set. A cell yields wheat
    iff it is free, not water, and some water lies within Chebyshev distance 4 --
    the 9x9 hydration square.

    The cap is tighter than the other oracles because wheat's interesting cases
    start at 81 free cells and ``2**81`` is not a number. This oracle only
    reaches 1xN strips and toy grids; the real independent check on wheat is the
    closed form ``m*n - ceil(m/9)*ceil(n/9)`` in ``test_wheat.py``, which needs
    no enumeration at all.

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
                if any(max(abs(r - wr), abs(c - wc)) <= 4 for (wr, wc) in water_set)
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


def _max_matching(edges: dict[tuple[int, int], list[tuple[int, int]]]) -> int:
    """Return the size of a maximum matching, by augmenting paths (Kuhn's).

    ``edges`` maps each cell of one side of the bipartition to the cells of the
    other side it may pair with. The grid graph is bipartite -- colour it like a
    chessboard -- so callers split on ``(r + c) % 2`` and pass one colour in.

    Written out here rather than imported because it is half of melon's oracle,
    and an oracle that borrowed the library's reasoning would be checking the
    model against itself.
    """
    partner: dict[tuple[int, int], tuple[int, int]] = {}

    def augment(cell: tuple[int, int], seen: set[tuple[int, int]]) -> bool:
        for other in edges[cell]:
            if other in seen:
                continue
            seen.add(other)
            if other not in partner or augment(partner[other], seen):
                partner[other] = cell
                return True
        return False

    return sum(augment(cell, set()) for cell in edges)


def brute_force_melon_optimum(text: str, *, max_free: int = 12) -> int:
    """Return the true maximum melon-stem count, by exhaustive enumeration.

    Tries every subset of the free cells as the water set. For each, the stems
    and their fruit form a **matching** on the remaining cells: an orthogonal
    pair may be used when at least one of the two is hydrated, since that one
    becomes the stem and the other takes the melon. The best layout for that
    water set is the maximum matching, which the chessboard colouring makes a
    bipartite problem.

    Note this is genuinely two nested searches, which is why the cap is tighter
    than sugarcane's: melon is a covering problem *and* a matching problem, and
    unlike wheat it has no closed form to check against instead.

    Raises:
        ValueError: if the terrain has more than ``max_free`` free cells.
    """
    free = _check_size(text, max_free)
    free_set = set(free)
    best = 0

    for size in range(len(free) + 1):
        for water in combinations(free, size):
            water_set = set(water)
            usable = free_set - water_set
            hydrated = {
                (r, c)
                for (r, c) in usable
                if any(max(abs(r - wr), abs(c - wc)) <= 4 for (wr, wc) in water_set)
            }
            if not hydrated:
                continue
            # One side of the chessboard; every edge crosses to the other.
            edges = {
                (r, c): [
                    (r + dr, c + dc)
                    for dr, dc in ORTHOGONAL_STEPS
                    if (r + dr, c + dc) in usable
                    # the pair is only usable if one end can hold the stem
                    and ((r, c) in hydrated or (r + dr, c + dc) in hydrated)
                ]
                for (r, c) in usable
                if (r + c) % 2 == 0
            }
            best = max(best, _max_matching(edges))
    return best


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


def assert_valid_wheat(layout: FarmLayout) -> None:
    """Assert the layout obeys every wheat rule.

    Same shape as the sugarcane validator, with the reach turned up: water must
    lie within Chebyshev distance 4 (the 9x9 square) rather than orthogonally
    adjacent. Nothing blocks hydration -- Minecraft checks distance, not line of
    sight -- so an obstacle in between is not consulted.
    """
    grid = layout.grid
    for cell in grid.cells():
        block = layout.block_at(cell)

        if grid.is_obstacle(cell):
            assert block is BlockType.OBSTACLE, f"obstacle at {cell} was overwritten with {block}"
            continue
        assert block is not BlockType.OBSTACLE, f"free cell {cell} was turned into an obstacle"

        if block is BlockType.CROP:
            in_range = grid.neighbors(cell, Neighborhood.DIAGONAL, 4)
            assert any(layout.block_at(n) is BlockType.WATER for n in in_range), (
                f"wheat at {cell} has no water within 4 blocks"
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


def assert_valid_melon(layout: FarmLayout) -> None:
    """Assert the layout obeys every melon rule.

    Three things, the third being the one melon exists to test:

    * obstacles untouched, free cells not turned into obstacles;
    * every stem has water within Chebyshev distance 4, exactly as wheat does;
    * every stem can be given a melon of its **own**. Checked by matching the
      stems against their adjacent melons and demanding the matching be
      perfect -- an assertion that each stem merely *touches* a melon would pass
      on the very layout the pairing constraint exists to forbid, two stems
      either side of one fruit.
    """
    grid = layout.grid
    stems: list[tuple[int, int]] = []
    melons: set[tuple[int, int]] = set()

    for cell in grid.cells():
        block = layout.block_at(cell)

        if grid.is_obstacle(cell):
            assert block is BlockType.OBSTACLE, f"obstacle at {cell} was overwritten with {block}"
            continue
        assert block is not BlockType.OBSTACLE, f"free cell {cell} was turned into an obstacle"

        if block is BlockType.CROP:
            in_range = grid.neighbors(cell, Neighborhood.DIAGONAL, 4)
            assert any(layout.block_at(n) is BlockType.WATER for n in in_range), (
                f"melon stem at {cell} has no water within 4 blocks"
            )
            stems.append((cell.row, cell.col))
        elif block is BlockType.MELON:
            melons.add((cell.row, cell.col))

    assert len(melons) == len(stems), (
        f"{len(stems)} stems but {len(melons)} melons; the pairing is not a bijection"
    )

    # Stems and melons are disjoint by construction, so they are already the two
    # sides of the bipartition and the matching can be taken as it stands.
    edges = {
        stem: [
            (stem[0] + dr, stem[1] + dc)
            for dr, dc in ORTHOGONAL_STEPS
            if (stem[0] + dr, stem[1] + dc) in melons
        ]
        for stem in stems
    }
    assert _max_matching(edges) == len(stems), (
        "some stem cannot be given a melon of its own -- two stems are sharing one fruit"
    )

    metrics = layout.metrics
    assert metrics.n_crop == len(stems)
    assert metrics.n_support == len(layout.cells_with(BlockType.WATER)) + len(melons)
    assert metrics.n_obstacle == len(layout.cells_with(BlockType.OBSTACLE))
    assert metrics.n_cells == len(grid)


@pytest.fixture
def rectangle():
    """Build an all-free terrain string of the given size."""

    def _make(height: int, width: int) -> str:
        return "\n".join("." * width for _ in range(height))

    return _make
