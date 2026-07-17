"""Runnable demo for cactus: `python examples/demo_cactus.py`.

This file is didactic -- it *is* the usage documentation. It runs with no
arguments and no dependency beyond what the project already needs.

To experiment, edit ONE line in the configuration block below (``TERRAIN``) and
run it again. Or set ``RUN_ALL = True`` to see the summary table across every
terrain at once.

The story here
--------------

This is the *opposite* lesson from ``demo_sugarcane.py``, and it is the more
honest one. It is also the least flattering thing in this repository, which is
why it is worth keeping.

Cactus breaks if anything solid touches it, so no two cacti may be orthogonally
adjacent. On open ground the best possible answer is therefore the checkerboard
-- and the checkerboard is exactly what people already build by hand. The solver
**ties it, at +0.0%**. There is no cleverer pattern to find; it confirms what you
already knew.

It is worse than that. Give a player no pattern at all -- just let them sweep the
field planting wherever it is legal -- and that greedy sweep **also ties the
optimum on four of the five terrains**. Across everything here, the exact solver's
best win over a competent player is **+4.9%, on one terrain**.

So the honest lesson for cactus is: *do not run this*. Plant greedily. The solver
is right, provably right, and almost never worth the trouble.

That result only appeared once the baselines were made to fill their leftover
holes (see ``_fill_gaps``). Before that, they left free cells unplanted, the
optimiser looked far better than it is, and the demo was quietly lying. A
comparison is only worth as much as the opponent it picks.

Everything here uses only the public API (``optimize``, ``FarmLayout``,
``BlockType``). Nothing from the core is reimplemented. The printing plumbing
lives in ``_shared.py`` and is not worth reading.
"""

from __future__ import annotations

from collections.abc import Callable

from _shared import (
    TERRAINS,
    arrow,
    build_layout,
    gain_over,
    heading,
    indent,
    print_metrics,
    print_table,
)

from mcfarm_opt import BlockType, Cactus, Cell, FarmLayout, Grid, optimize, parse_grid

# ============================================================================
# CONFIGURATION -- edit here
# ============================================================================

TERRAIN: str = "ragged"  # options: see TERRAINS in _shared.py
SOLVER: str = "ilp"  # options: "ilp" (exact, via CP-SAT)

RUN_ALL: bool = False  # True = ignore TERRAIN, run every terrain with a summary table

# Cactus is maximum independent set on a bipartite grid graph, which is
# polynomial -- a 40x40 proves optimal in a third of a second. The limit is here
# for symmetry with the sugarcane demo; it will not be hit.
TIME_LIMIT: float | None = 30.0

# The crop is fixed. It is not a knob, because the baselines below only make
# sense for cactus -- a cactus farm has no water to lay stripes of. Run
# demo_sugarcane.py for sugarcane.
CROP = Cactus()


# ============================================================================
# BASELINES: what people actually do by hand
# ============================================================================
# Note what is *missing*: there is no stripe pattern here. Stripes are how you
# feed a crop from a water source, and cactus has no source to feed from -- it
# wants distance, not supply. Every hand strategy for cactus is about spacing.


def _prune_cactus_touching_a_wall(grid: Grid, assignment: dict[Cell, BlockType]) -> None:
    """Remove any cactus that ended up against an obstacle, in place.

    Hand patterns assume open ground. An obstacle is solid, so a cactus beside
    one would break -- a player stamping a checkerboard onto rocky terrain has
    to go back and pull those out. Without this prune the baseline would be an
    *illegal* layout claiming cacti it cannot grow, and the comparison against it
    would be a lie in the pattern's favour.

    Only obstacle-adjacency needs pruning: the pattern spaces its cacti out by
    construction, so no cactus ever touches another. The test suite checks that
    claim rather than trusting it.
    """
    for cell in grid.free_cells():
        if assignment[cell] is BlockType.CROP:
            if any(grid.is_obstacle(n) for n in grid.neighbors(cell)):
                assignment[cell] = BlockType.EMPTY


def _fill_gaps(grid: Grid, assignment: dict[Cell, BlockType]) -> None:
    """Plant a cactus in every leftover cell that can legally take one, in place.

    This is the step that makes the comparison honest, and it is easy to forget.
    Stamping a pattern and pruning what broke leaves *holes* -- and a real player
    looking at a hole with nothing solid around it plants a cactus in it. A
    baseline that walks away from free production is not a player, it is a
    strawman, and beating it would prove nothing.

    Order matters here, unlike the sugarcane fill: planting a cactus blocks its
    four neighbours from ever being planted. Row-major is what a person sweeping
    the field would do. Choosing the *best* order is not a fill any more -- it is
    the maximum independent set problem, which is to say, it is the solver.
    """
    for cell in grid.free_cells():
        if assignment[cell] is not BlockType.EMPTY:
            continue
        blocked = any(
            grid.is_obstacle(n) or assignment[n] is BlockType.CROP
            for n in grid.neighbors(cell)
        )
        if not blocked:
            assignment[cell] = BlockType.CROP


def _apply_checkerboard(grid: Grid, parity: int) -> dict[Cell, BlockType]:
    """Plant cactus on one colour of the board, then prune and fill.

    The pattern every cactus farm uses, and for good reason: two cells of the
    same colour are never orthogonally adjacent, only diagonal, so the rule is
    satisfied while still using half the terrain. On open ground this is not
    merely good, it is provably optimal, and the fill below finds nothing to add.
    On rocky terrain the walls punch holes in it, and then the fill matters.

    Args:
        grid: the terrain.
        parity: which colour of the board gets the cacti (0 or 1).
    """
    assignment: dict[Cell, BlockType] = {}
    for cell in grid.cells():
        if grid.is_obstacle(cell):
            assignment[cell] = BlockType.OBSTACLE
            continue
        is_cactus = (cell.row + cell.col) % 2 == parity
        assignment[cell] = BlockType.CROP if is_cactus else BlockType.EMPTY

    _prune_cactus_touching_a_wall(grid, assignment)
    _fill_gaps(grid, assignment)
    return assignment


def _apply_greedy(grid: Grid) -> dict[Cell, BlockType]:
    """Plant no pattern at all: just sweep the field and plant wherever it is legal.

    The other thing people do, and it turns out to be the stronger one. It
    commits to nothing globally, so obstacles cost it only what they actually
    block, while a checkerboard has to pick one colour of the board for the whole
    terrain and eat whatever that costs locally.

    There used to be a third baseline here, a "sparse grid" that left a gap in
    both directions around each cactus. It is gone, because once you fill its
    holes it stops being a sparse grid -- the fill turns it into exactly the
    checkerboard on open ground, and into this greedy sweep on rocky ground. It
    was never a distinct strategy, only an unfilled one.
    """
    assignment: dict[Cell, BlockType] = {
        cell: (BlockType.OBSTACLE if grid.is_obstacle(cell) else BlockType.EMPTY)
        for cell in grid.cells()
    }
    _fill_gaps(grid, assignment)
    return assignment


def baseline_checkerboard(grid: Grid) -> FarmLayout | None:
    """Return the best checkerboard layout here.

    Tries both colourings and keeps the better one. On an odd-celled terrain the
    two colours differ in size -- a 9x9 splits 41/40 -- and on rocky terrain one
    colour may lose more cacti to the walls than the other. A player would pick
    the better side; comparing the optimum against the worse one would inflate
    optifarm's win for free.

    Returns:
        The best layout, or ``None`` if the pattern grows nothing at all.
    """
    candidates = [
        build_layout(grid, _apply_checkerboard(grid, parity), "checkerboard")
        for parity in (0, 1)
    ]
    best = max(candidates, key=lambda layout: layout.metrics.n_crop)
    return best if best.metrics.n_crop > 0 else None


def baseline_greedy(grid: Grid) -> FarmLayout | None:
    """Return the layout a player gets by sweeping and planting wherever legal."""
    layout = build_layout(grid, _apply_greedy(grid), "greedy")
    return layout if layout.metrics.n_crop > 0 else None


# Worst-expected first, so the printed comparison reads as a progression.
BASELINES: tuple[tuple[str, Callable[[Grid], FarmLayout | None]], ...] = (
    ("Checkerboard", baseline_checkerboard),
    ("Greedy sweep", baseline_greedy),
)


# ============================================================================
# RUNNING
# ============================================================================


def print_comparison(optimal: FarmLayout, baselines: list[tuple[str, FarmLayout | None]]) -> None:
    """Print how the optimum compares against each hand-built pattern.

    A tie is a real result here, not a failure, and is reported as one.
    """
    mark = arrow()
    print()
    print("Compared against the hand-built patterns:")

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
            # Impossible: the optimum is by definition >= any valid layout. If
            # this fires, either the prune or the model is broken.
            else f"{mark} {gain:.1f}%  (!! the optimum should never lose)"
        )
        print(
            f"  {label + ':':<20} {layout.metrics.n_crop:3d} cactus  "
            f"({layout.metrics.efficiency:5.1f}%)   {verdict}"
        )

    print(
        f"  {'Optimal (optifarm):':<20} {optimal.metrics.n_crop:3d} cactus  "
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
    heading(f"Cactus on {name}  ({height}x{width}, {n_free} free, {n_obstacles} obstacles)")

    print()
    print("Input  ('.' free, '#' obstacle):")
    print(indent(terrain))

    for label, layout in baselines:
        if layout is None:
            continue
        print()
        print(f"{label} by hand  ('C' cactus, '.' bare ground):")
        print(indent(layout.render()))

    print()
    print(f"Optimal layout from optifarm  (crop: {optimal.crop_name}, solver: {SOLVER}):")
    print(indent(optimal.render()))

    print()
    print("Metrics:")
    # No support_word: cactus places no support block. The sand it stands on is
    # under it, inside the same cell, so a "water 0" line would be noise.
    print_metrics(optimal.metrics, crop_word="cactus", support_word=None)

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
    """Run every terrain and print a summary table: each baseline vs the optimum."""
    heading("Cactus on every terrain")
    print()
    print("This is quick. Cactus is maximum independent set on a bipartite grid,")
    print("so every one of these proves optimal in milliseconds.")

    rows: list[tuple[str, ...]] = []
    for name in TERRAINS:
        print(f"  ... solving {name}", flush=True)
        optimal, baselines = run_one(name, verbose=False)
        by_label = dict(baselines)

        rows.append(
            (
                name,
                str(optimal.metrics.n_free),
                _cell(by_label["Checkerboard"]),
                _cell(by_label["Greedy sweep"]),
                f"{optimal.metrics.n_crop} ({optimal.metrics.efficiency:.1f}%)",
                _gain_cell(optimal, by_label["Checkerboard"]),
                _gain_cell(optimal, by_label["Greedy sweep"]),
            )
        )

    print_table(
        ("Terrain", "Free", "Checkerboard", "Greedy sweep", "Optimal", "vs check", "vs greedy"),
        (16, 5, 14, 14, 14, 9, 10),
        rows,
    )

    print()
    print("  Read the last column. 'vs greedy' is what the solver is worth against a")
    print("  player who just sweeps the field planting wherever it is legal -- and the")
    print("  answer is mostly +0.0%. On open ground the checkerboard is already the")
    print("  optimum; on rocky ground the greedy sweep catches what the checkerboard")
    print("  drops, because a checkerboard must pick one colour of the board globally")
    print("  and obstacles make that choice wrong locally.")
    print()
    print("  The exact solver's best win over a competent player, across every terrain")
    print("  here, is a single-digit percent on one map. For cactus, this library is")
    print("  the wrong tool, and the useful thing it can tell you is exactly that.")
    print("  Run demo_sugarcane.py to see the case where it is the right one.")


def main() -> None:
    """Entry point: run one terrain, or all of them, per the configuration."""
    if RUN_ALL:
        run_all()
    else:
        run_one(TERRAIN)
        print()
        print("Tip: edit TERRAIN at the top of this file to try another terrain,")
        print("     or set RUN_ALL = True to compare them all at once.")
        print("     Try 'rectangle_9x9' to see the solver tie the hand pattern.")
    print()


if __name__ == "__main__":
    main()
