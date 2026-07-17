"""Runnable demo for wheat: `python examples/demo_wheat.py`.

This file is didactic -- it *is* the usage documentation. It runs with no
arguments and no dependency beyond what the project already needs.

To experiment, edit ONE line in the configuration block below (``TERRAIN``) and
run it again. Or set ``RUN_ALL = True`` to see the summary table across every
terrain at once.

The story here
--------------

Wheat is the third economics, and the one that most thoroughly puts this library
out of a job.

Sugarcane is a **trade**: water costs a cell and feeds four, so where you dig
matters, and the solver is worth 4-7% over a thinking player. Cactus is
**exclusion**: no two may touch, and the solver is worth about 3%. Wheat is
**covering**: one water hydrates the 9x9 around it, so it costs one cell and
feeds *eighty*. Water is nearly free. The only question left is how few sources
blanket the field, and blanketing a field is something people are extremely good
at -- you put a source every nine blocks. That layout is not a heuristic, it is
provably optimal, and it is what everybody already builds.

So on six of the seven terrains here the solver wins **+0.0%**. On the seventh --
`rubble`, where obstacles chew the field into fragments too small and too oddly
spaced for a lattice -- it wins **0.9%** over a greedy player. That is the whole
prize.

Read `two_fields` for the other lesson. A raw 9-lattice scores 252 there against
the optimum's 320, because the lattice points land in a wall. Repair it the way
any player would -- add water where the field is dry, pull water that is
redundant -- and it scores 320. Exactly optimal. If this demo skipped the repair
it could advertise a **+27%** win for the solver, and every digit of it would be
invented. That is not a hypothetical: it is what the cactus demo used to do
before its baselines were fixed.

Everything here uses only the public API. The printing plumbing lives in
``_shared.py`` and is not worth reading.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from _shared import (
    TERRAINS as SHARED_TERRAINS,
)
from _shared import (
    arrow,
    build_layout,
    gain_over,
    heading,
    indent,
    print_metrics,
    print_table,
)

from mcfarm_opt import BlockType, Cell, FarmLayout, Grid, Neighborhood, Wheat, optimize, parse_grid

# ============================================================================
# TERRAINS
# ============================================================================
# The shared terrains, plus two that only wheat needs.
#
# Wheat reaches nine blocks. Most of the shared terrains are *smaller than one
# water source*, so a single well-placed block covers them entirely and every
# strategy ties without having to think. That is a real result -- it is most of
# why this demo concludes what it concludes -- but a table of nothing but zeros
# proves nothing about the hard cases, so two terrains below are sized for the
# crop. They are wheat-only because sugarcane cannot prove a 20x20 in any
# reasonable time, while wheat proves these in under a second.

WHEAT_TERRAINS: dict[str, str] = {
    # Two 9-wide fields split by a wall, with a second wall across the middle.
    # Sized so that a 9-lattice puts its sources *inside the walls*, where they
    # cannot go. The raw lattice scores 252 here; repaired, it scores the optimal
    # 320. This terrain exists to show what skipping the repair would cost.
    "two_fields": "\n".join(
        ("#" * 20) if row in (9, 10) else ("." * 9 + "##" + "." * 9) for row in range(20)
    ),
    # Heavy rubble: obstacles at ~35% density, so the field is a spray of
    # fragments at no regular spacing. The only terrain found where a repaired
    # lattice cannot reach the optimum -- and it misses by 2.7%.
    "rubble": """\
#.###.....##
.....#......
...#.....#..
.#....####..
.##..#...#..
.......#...#
.#.###....##
#####....#.#
...#........
...##..#.##.
#.#.....#.##
.#.#.#....##
#.###..###..
##.#.###..#.
.#.#..#..#.#
...##..#..#.""",
}

TERRAINS: dict[str, str] = {**SHARED_TERRAINS, **WHEAT_TERRAINS}

# ============================================================================
# CONFIGURATION -- edit here
# ============================================================================

TERRAIN: str = "rubble"  # options: see TERRAINS above
SOLVER: str = "ilp"  # options: "ilp" (exact, via CP-SAT)

RUN_ALL: bool = False  # True = ignore TERRAIN, run every terrain with a summary table

# Wheat is a covering problem and CP-SAT eats it: every terrain here proves
# optimal in under a quarter of a second. The limit is here for symmetry with the
# other demos; it will not be hit.
TIME_LIMIT: float | None = 30.0

# The crop is fixed. It is not a knob, because the baselines below only make
# sense for wheat -- a 9-lattice of water would be a bizarre sugarcane farm and a
# nonsensical cactus one. Run demo_sugarcane.py or demo_cactus.py for those.
CROP = Wheat()

HYDRATION_RADIUS = 4
"""Water reaches 4 in every direction: the 9x9 square. Same constant as the rule."""


# ============================================================================
# BASELINES: what people actually do by hand
# ============================================================================


def _reachable(grid: Grid) -> dict[Cell, frozenset[Cell]]:
    """For each free cell, the free cells it would hydrate if it held water.

    Precomputed once: every baseline below asks this question thousands of times,
    and asking the grid each time makes the demo visibly slow.
    """
    return {
        cell: frozenset(
            n
            for n in grid.neighbors(cell, Neighborhood.DIAGONAL, HYDRATION_RADIUS)
            if grid.is_free(n)
        )
        for cell in grid.free_cells()
    }


def _wheat_count(reach: dict[Cell, frozenset[Cell]], water: Iterable[Cell]) -> int:
    """How much wheat a given set of water sources yields.

    A cell grows wheat iff something hydrates it and it is not itself water.
    """
    water = set(water)
    hydrated: set[Cell] = set()
    for source in water:
        hydrated |= reach[source]
    return len(hydrated - water)


def _repair(grid: Grid, reach: dict[Cell, frozenset[Cell]], water: set[Cell]) -> set[Cell]:
    """Fix a stamped pattern the way a player would, in place of walking away.

    Two passes, both obvious to anyone standing in the field:

    * **dig where it is dry** -- if a patch has no source in range, put one there.
      A pattern whose lattice point landed in a wall leaves exactly this.
    * **pull what is redundant** -- if a source can be removed without drying
      anything out, remove it and plant wheat in the hole. Overlapping sources
      are pure loss.

    Skipping this is how a demo lies. On `two_fields` the raw lattice scores 252
    and the repaired one scores 320 -- the proven optimum. Without the repair
    this file could claim the solver wins 27% there, and it would be fiction.
    """
    water = set(water)

    while True:  # dig where it pays
        current = _wheat_count(reach, water)
        best_gain, best_cell = 0, None
        for cell in grid.free_cells():
            if cell in water:
                continue
            water.add(cell)
            gain = _wheat_count(reach, water) - current
            water.discard(cell)
            if gain > best_gain:
                best_gain, best_cell = gain, cell
        if best_cell is None:
            break
        water.add(best_cell)

    while True:  # pull what is redundant
        current = _wheat_count(reach, water)
        for source in list(water):
            water.discard(source)
            if _wheat_count(reach, water) > current:
                break  # removing it was an improvement; keep it removed
            water.add(source)
        else:
            break

    return water


def _assignment(grid: Grid, water: set[Cell]) -> dict[Cell, BlockType]:
    """Turn a set of water sources into a full layout."""
    hydrated: set[Cell] = set()
    reach = _reachable(grid)
    for source in water:
        hydrated |= reach[source]

    assignment: dict[Cell, BlockType] = {}
    for cell in grid.cells():
        if grid.is_obstacle(cell):
            assignment[cell] = BlockType.OBSTACLE
        elif cell in water:
            assignment[cell] = BlockType.WATER
        elif cell in hydrated:
            assignment[cell] = BlockType.CROP
        else:
            assignment[cell] = BlockType.EMPTY
    return assignment


def _apply_lattice(grid: Grid, row_offset: int, col_offset: int) -> set[Cell]:
    """Water every ninth row and every ninth column -- the pattern people build.

    One source per 9x9 block is not a rule of thumb, it is the proven optimum on
    open ground: cells nine apart cannot share a source, so you need at least
    this many, and this many suffice. Obstacles are the only thing that spoils
    it, by swallowing the cell a source was supposed to occupy.
    """
    return {
        cell
        for cell in grid.free_cells()
        if cell.row % 9 == row_offset and cell.col % 9 == col_offset
    }


def baseline_lattice(grid: Grid) -> FarmLayout | None:
    """Return the best 9-lattice here: best of all 81 alignments, then repaired.

    All 81 offsets are tried because a player would slide the lattice until it
    fits the terrain rather than anchoring it at the corner and shrugging. Then
    it is repaired, because a player would not leave a field dry or a source
    doubled up. Both steps matter: skip the alignment search and this loses on
    every rocky map; skip the repair and it loses 27% on `two_fields`.
    """
    reach = _reachable(grid)
    best_water: set[Cell] = set()
    best_score = -1
    for row_offset in range(9):
        for col_offset in range(9):
            water = _apply_lattice(grid, row_offset, col_offset)
            if not water:
                continue
            score = _wheat_count(reach, water)
            if score > best_score:
                best_water, best_score = water, score

    if not best_water:
        return None
    water = _repair(grid, reach, best_water)
    layout = build_layout(grid, _assignment(grid, water), "9-lattice")
    return layout if layout.metrics.n_crop > 0 else None


def baseline_greedy(grid: Grid) -> FarmLayout | None:
    """Return the layout from digging the source that covers the most, repeatedly.

    No pattern at all: put water where it hydrates the most dry ground, stop when
    no source pays for itself. On `rubble` this beats the lattice, because rubble
    has no spacing for a lattice to follow.
    """
    reach = _reachable(grid)
    water = _repair(grid, reach, set())
    if not water:
        return None
    layout = build_layout(grid, _assignment(grid, water), "greedy")
    return layout if layout.metrics.n_crop > 0 else None


# Worst-expected first, so the printed comparison reads as a progression.
BASELINES: tuple[tuple[str, Callable[[Grid], FarmLayout | None]], ...] = (
    ("9-lattice", baseline_lattice),
    ("Greedy water", baseline_greedy),
)


# ============================================================================
# RUNNING
# ============================================================================


def print_comparison(optimal: FarmLayout, baselines: list[tuple[str, FarmLayout | None]]) -> None:
    """Print how the optimum compares against each hand strategy.

    A tie is the expected result here, not a failure, and is reported as one.
    """
    mark = arrow()
    print()
    print("Compared against the hand-built strategies:")

    for label, layout in baselines:
        if layout is None:
            print(f"  {label + ':':<20} grows nothing on this terrain")
            continue
        gain = gain_over(optimal, layout)
        verdict = (
            f"{mark} optifarm +{gain:.1f}%"
            if gain > 0
            else f"{mark} tie: already optimal, the solver only confirms it"
            if gain == 0
            # Impossible: the optimum is by definition >= any valid layout.
            else f"{mark} {gain:.1f}%  (!! the optimum should never lose)"
        )
        print(
            f"  {label + ':':<20} {layout.metrics.n_crop:4d} wheat  "
            f"({layout.metrics.efficiency:5.1f}%)   {verdict}"
        )

    print(
        f"  {'Optimal (optifarm):':<20} {optimal.metrics.n_crop:4d} wheat  "
        f"({optimal.metrics.efficiency:5.1f}%)"
    )


def run_one(
    name: str, *, verbose: bool = True
) -> tuple[FarmLayout, list[tuple[str, FarmLayout | None]]]:
    """Optimise one terrain and print everything: input, layouts, metrics, comparison.

    Args:
        name: the key of the terrain in TERRAINS.
        verbose: if False, compute without printing (used by the summary table).

    Returns:
        The optimal layout, and the (label, layout) pair for each baseline.

    Raises:
        KeyError: if the name is not in TERRAINS.
    """
    try:
        terrain = TERRAINS[name]
    except KeyError:
        raise KeyError(f"no terrain named {name!r}; options: {sorted(TERRAINS)}") from None

    grid = parse_grid(terrain)

    # --- the actual computation. This IS the library. Everything else is display.
    optimal = optimize(terrain, crop=CROP, solver=SOLVER, time_limit=TIME_LIMIT)
    baselines = [(label, build(grid)) for label, build in BASELINES]

    if not verbose:
        return optimal, baselines

    height, width = grid.shape
    n_free = len(list(grid.free_cells()))
    n_obstacles = len(list(grid.obstacles()))
    heading(f"Wheat on {name}  ({height}x{width}, {n_free} free, {n_obstacles} obstacles)")

    print()
    print("Input  ('.' free, '#' obstacle):")
    print(indent(terrain))

    for label, layout in baselines:
        if layout is None:
            continue
        print()
        print(f"{label} by hand  ('W' water, 'C' wheat, '.' dry and unused):")
        print(indent(layout.render()))

    print()
    print(f"Optimal layout from optifarm  (crop: {optimal.crop_name}, solver: {SOLVER}):")
    print(indent(optimal.render()))

    print()
    print("Metrics:")
    print_metrics(optimal.metrics, crop_word="wheat", support_word="water")

    print_comparison(optimal, baselines)
    return optimal, baselines


def _cell(layout: FarmLayout | None) -> str:
    """Format one baseline's cell for the summary table."""
    if layout is None:
        return "n/a"
    return f"{layout.metrics.n_crop} ({layout.metrics.efficiency:.1f}%)"


def _gain_cell(optimal: FarmLayout, layout: FarmLayout | None) -> str:
    gain = gain_over(optimal, layout)
    return "n/a" if gain is None else f"+{gain:.1f}%"


def run_all() -> None:
    """Run every terrain and print a summary table: each strategy vs the optimum."""
    heading("Wheat on every terrain")
    print()
    print("This is quick. Wheat is a covering problem on a lattice, so every one")
    print("of these proves optimal in a fraction of a second.")

    rows: list[tuple[str, ...]] = []
    for name in TERRAINS:
        print(f"  ... solving {name}", flush=True)
        optimal, baselines = run_one(name, verbose=False)
        by_label = dict(baselines)

        rows.append(
            (
                name,
                str(optimal.metrics.n_free),
                _cell(by_label["9-lattice"]),
                _cell(by_label["Greedy water"]),
                f"{optimal.metrics.n_crop} ({optimal.metrics.efficiency:.1f}%)",
                _gain_cell(optimal, by_label["9-lattice"]),
                _gain_cell(optimal, by_label["Greedy water"]),
            )
        )

    print_table(
        ("Terrain", "Free", "9-lattice", "Greedy water", "Optimal", "vs latt", "vs greedy"),
        (14, 4, 13, 13, 13, 8, 10),
        rows,
    )

    print()
    print("  Almost every row is +0.0%, and that is the result. Water hydrates 80")
    print("  cells and costs one, so wheat is not really an optimisation problem --")
    print("  it is a covering problem, and a source every nine blocks solves it")
    print("  exactly. People have been building that layout for years without a")
    print("  solver, and they were right to.")
    print()
    print("  The exception is 'rubble', where obstacles shred the field into")
    print("  fragments no lattice can follow. There the solver wins 0.9% over a")
    print("  greedy player. That is the entire prize, on the one terrain built to")
    print("  be hostile.")
    print()
    print("  For the crop where this library actually earns its keep, run")
    print("  demo_sugarcane.py -- and even there the honest number is 4-7%.")


def main() -> None:
    """Entry point: run one terrain, or all of them, per the configuration."""
    if RUN_ALL:
        run_all()
    else:
        run_one(TERRAIN)
        print()
        print("Tip: edit TERRAIN at the top of this file to try another terrain,")
        print("     or set RUN_ALL = True to compare them all at once.")
        print("     Try 'rectangle_9x9' to watch one water block feed 80 wheat.")
    print()


if __name__ == "__main__":
    main()
