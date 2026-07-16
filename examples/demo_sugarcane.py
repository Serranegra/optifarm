"""Runnable demo for sugarcane: `python examples/demo_sugarcane.py`.

This file is didactic -- it *is* the usage documentation. It runs with no
arguments and no dependency beyond what the project already needs.

To experiment, edit ONE line in the configuration block below (``TERRAIN``) and
run it again. Or set ``RUN_ALL = True`` to see the summary table across every
terrain at once.

The story here
--------------

Sugarcane needs water orthogonally adjacent, so a farm is a trade: every water
block costs a cell of production but can feed up to four neighbours. People solve
that trade with patterns, and **the patterns lose** -- by 13% to 31%, worst where
obstacles break them.

That number is true and slightly dishonest, so the demo does not stop there. A
pattern is not the best a person can do. A player who follows no pattern and just
digs the water that pays best (``baseline_greedy_water``) beats every pattern
here, and against *that* the exact optimum is worth **4% to 7%** -- and on
``ragged``, nothing at all.

So sugarcane is the case where this library is worth running, but the honest size
of the prize is single digits against someone thinking, not the 30% you get by
picking a template as your opponent. For the case where it is worth nothing, see
``demo_cactus.py``.

Everything here uses only the public API (``optimize``, ``FarmLayout``,
``BlockType``). Nothing from the core is reimplemented. The printing plumbing
lives in ``_shared.py`` and is not worth reading.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

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

from mcfarm_opt import BlockType, Cell, FarmLayout, Grid, Sugarcane, optimize, parse_grid

# ============================================================================
# CONFIGURATION -- edit here
# ============================================================================

TERRAIN: str = "l_shape"  # options: see TERRAINS in _shared.py
SOLVER: str = "ilp"  # options: "ilp" (exact, via CP-SAT)

RUN_ALL: bool = False  # True = ignore TERRAIN, run every terrain with a summary table

# Seconds the solver may spend before returning the best it has found.
# None = no limit. large_15x15 takes ~12s to prove optimality; the others are
# instant. If the limit runs out the result is still a valid layout -- it just
# is not provably optimal, and the demo says so rather than pretending.
TIME_LIMIT: float | None = 30.0

# The crop is fixed. It is not a knob, because the baselines below only make
# sense for sugarcane -- water stripes on a cactus farm would be nonsense, and
# nonsense that still renders. Run demo_cactus.py for cactus.
CROP = Sugarcane()


# ============================================================================
# BASELINES: the patterns people build by hand
# ============================================================================
# Two of them, and the contrast is the point. Both are legal layouts; both are
# beaten by the solver; they lose for different reasons.
#
# Note there is no "fill the leftover gaps" step here, unlike demo_cactus.py --
# and its absence is deliberate rather than forgotten. See _prune_unsupported_cane.

Orientation = Literal["rows", "columns"]


def _prune_unsupported_cane(grid: Grid, assignment: dict[Cell, BlockType]) -> None:
    """Turn any cane with no orthogonally adjacent water into EMPTY, in place.

    Hand patterns assume open ground. Drop one on a terrain with obstacles and
    some cane ends up stranded -- the '#' ate the piece of water that would have
    served it. Without this prune the baseline would be an *illegal* layout
    claiming cane it cannot grow, and every comparison against it would be a lie
    in the pattern's favour.

    One pass is enough: pruning only removes cane, and a cane cell's validity
    depends solely on its water neighbours, which never change.

    Why there is no fill afterwards
    -------------------------------

    A real player would never leave a plantable cell bare, so a fair baseline has
    to plant in the holes its prune left -- ``demo_cactus.py`` does exactly that,
    and it changes its numbers a lot.

    Here it would change nothing, and provably so. A cell is EMPTY only because
    this prune emptied it, and it emptied it precisely because the cell has *no
    adjacent water*. Planting cane there requires *adjacent water*. The condition
    that creates a hole is the negation of the condition that could fill it, so
    there is never anything to fill. These patterns are already maximal.

    That is an argument, and arguments rot. ``tests/test_demo.py`` asserts the
    property directly -- no empty cell in a sugarcane baseline has water beside
    it -- so a future pattern that *does* leave a fillable hole fails the suite
    instead of quietly flattering the solver.
    """
    for cell in grid.free_cells():
        if assignment[cell] is BlockType.CROP:
            if not any(assignment[n] is BlockType.WATER for n in grid.neighbors(cell)):
                assignment[cell] = BlockType.EMPTY


def _apply_stripes(grid: Grid, orientation: Orientation, offset: int) -> dict[Cell, BlockType]:
    """Fill the terrain with the 1x2 stripe pattern at one orientation/offset.

    The classic community layout: one stripe of water for every two rows of
    cane, repeating with period 3. Each water stripe serves the row above and
    the row below -- which is exactly cane's reach, since it only accepts water
    orthogonally adjacent.

    Args:
        grid: the terrain.
        orientation: whether the water stripes run along rows or columns.
        offset: which residue mod 3 gets water (0, 1 or 2).
    """
    assignment: dict[Cell, BlockType] = {}
    for cell in grid.cells():
        if grid.is_obstacle(cell):
            assignment[cell] = BlockType.OBSTACLE
            continue
        stripe = cell.row if orientation == "rows" else cell.col
        assignment[cell] = BlockType.WATER if stripe % 3 == offset else BlockType.CROP

    _prune_unsupported_cane(grid, assignment)
    return assignment


def _apply_checkerboard(grid: Grid, parity: int) -> dict[Cell, BlockType]:
    """Fill the terrain with alternating water and cane, like a chessboard.

    The other pattern people reach for. It is trivially *correct* -- every
    orthogonal neighbour of a cane cell is water, so no cane can ever be
    stranded -- and that safety is exactly why it is weak: it buys a guarantee
    it does not need by spending half the terrain on water. Cane only needs
    *one* adjacent water, and the checkerboard gives every cane four.
    """
    assignment: dict[Cell, BlockType] = {}
    for cell in grid.cells():
        if grid.is_obstacle(cell):
            assignment[cell] = BlockType.OBSTACLE
            continue
        is_water = (cell.row + cell.col) % 2 == parity
        assignment[cell] = BlockType.WATER if is_water else BlockType.CROP

    _prune_unsupported_cane(grid, assignment)
    return assignment


def _apply_greedy_water(grid: Grid) -> dict[Cell, BlockType]:
    """Plant no pattern: repeatedly dig the one water that creates the most cane.

    This is the thoughtful player, and it is the baseline that matters. Start
    with bare ground and ask, over and over, "if I flooded exactly one more cell,
    which one buys me the most cane?" Dig that one. Stop when no dig pays for
    itself -- a water cell costs a square of production, so it has to feed at
    least two new canes to be worth it.

    Why this and not a sweep
    ------------------------

    The obvious greedy is a sweep: walk the field, plant cane where water is
    already beside you, dig water where it is not. That one degenerates. Cell
    (0,0) has no water, so it digs; (0,1) now has water, so it plants; (0,2)
    digs again -- and the alternation propagates into precisely a **checkerboard**,
    at whichever parity the corner happened to force. It scores 40 on the 9x9
    against the checkerboard baseline's 41, because it is a checkerboard, just
    one that never got to choose its colour. Adding it to the table would mean
    adding a deliberately worse-aligned copy of a row already there, which is the
    exact strawman every other baseline here is careful to avoid.

    So the interesting greedy is this one, and it is strong: it beats the 1x2
    stripes on every terrain in the demo, and it ties the solver outright on
    `ragged`. Against it, the exact optimum is worth single digits.
    """
    free = list(grid.free_cells())
    neighbours = {cell: [n for n in grid.neighbors(cell) if grid.is_free(n)] for cell in free}
    water: set[Cell] = set()

    def cane_total(flooded: set[Cell]) -> int:
        return sum(
            1
            for cell in free
            if cell not in flooded and any(n in flooded for n in neighbours[cell])
        )

    current = 0
    while True:
        best_gain, best_cell = 0, None
        for cell in free:  # row-major, so ties break deterministically
            if cell in water:
                continue
            water.add(cell)
            gain = cane_total(water) - current
            water.discard(cell)
            if gain > best_gain:
                best_gain, best_cell = gain, cell
        if best_cell is None:
            break
        water.add(best_cell)
        current += best_gain

    assignment: dict[Cell, BlockType] = {}
    for cell in grid.cells():
        if grid.is_obstacle(cell):
            assignment[cell] = BlockType.OBSTACLE
        elif cell in water:
            assignment[cell] = BlockType.WATER
        else:
            assignment[cell] = BlockType.EMPTY

    # Every cell that ended up next to water becomes cane. By construction this
    # is the fill, and here it is doing real work rather than being a no-op.
    for cell in free:
        if assignment[cell] is BlockType.EMPTY:
            if any(assignment[n] is BlockType.WATER for n in grid.neighbors(cell)):
                assignment[cell] = BlockType.CROP
    return assignment


def baseline_stripes_1x2(grid: Grid) -> FarmLayout | None:
    """Return the best layout the hand-built 1x2 stripe pattern reaches here.

    Tries all 6 variants (2 orientations x 3 offsets) and returns the best. That
    is deliberate: a player would align the stripes to the terrain, and the
    choice matters a lot. On a 9x9 the right offset yields 54 cane and the wrong
    one 45 -- comparing the optimum against the worst variant would inflate
    optifarm's win for free.

    Returns:
        The best layout, or ``None`` if the pattern grows nothing here (a fully
        blocked grid, or one too narrow to fit a water stripe and a cane row).
    """
    candidates = [
        build_layout(grid, _apply_stripes(grid, orientation, offset), "1x2 stripes")
        for orientation in ("rows", "columns")
        for offset in (0, 1, 2)
    ]
    best = max(candidates, key=lambda layout: layout.metrics.n_crop)
    return best if best.metrics.n_crop > 0 else None


def baseline_checkerboard(grid: Grid) -> FarmLayout | None:
    """Return the best checkerboard layout here.

    Tries both colourings and keeps the better one. On an odd-celled terrain the
    two colours differ in size -- a 9x9 splits 41/40 -- so putting the cane on
    the majority colour is worth a cell or two.

    Returns:
        The best layout, or ``None`` if the pattern grows nothing (a single cell
        has no neighbour to water it).
    """
    candidates = [
        build_layout(grid, _apply_checkerboard(grid, parity), "checkerboard")
        for parity in (0, 1)
    ]
    best = max(candidates, key=lambda layout: layout.metrics.n_crop)
    return best if best.metrics.n_crop > 0 else None


def baseline_greedy_water(grid: Grid) -> FarmLayout | None:
    """Return the layout a thoughtful player reaches by digging the best water first."""
    layout = build_layout(grid, _apply_greedy_water(grid), "greedy water")
    return layout if layout.metrics.n_crop > 0 else None


# Worst-expected first, so the printed comparison reads as a progression up to
# the optimum. The last one is the one that matters: it is the strongest thing a
# person does without a solver, so it is what the solver has to beat to be worth
# running at all.
BASELINES: tuple[tuple[str, Callable[[Grid], FarmLayout | None]], ...] = (
    ("Checkerboard", baseline_checkerboard),
    ("1x2 stripes", baseline_stripes_1x2),
    ("Greedy water", baseline_greedy_water),
)


# ============================================================================
# RUNNING
# ============================================================================


def print_comparison(optimal: FarmLayout, baselines: list[tuple[str, FarmLayout | None]]) -> None:
    """Print how the optimum compares against each hand-built pattern."""
    mark = arrow()
    print()
    print("Compared against the hand-built patterns:")

    for label, layout in baselines:
        if layout is None:
            print(f"  {label + ':':<20} does not apply to this terrain (no stripe fits)")
            continue
        gain = gain_over(optimal, layout)
        verdict = (
            f"{mark} optifarm +{gain:.1f}%"
            if gain > 0
            else f"{mark} tie: this pattern is already optimal here"
            if gain == 0
            # Impossible: the optimum is by definition >= any valid layout. If
            # this fires, either the prune or the model is broken.
            else f"{mark} {gain:.1f}%  (!! the optimum should never lose)"
        )
        print(
            f"  {label + ':':<20} {layout.metrics.n_crop:3d} cane  "
            f"({layout.metrics.efficiency:5.1f}%)   {verdict}"
        )

    print(
        f"  {'Optimal (optifarm):':<20} {optimal.metrics.n_crop:3d} cane  "
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
    heading(f"Sugarcane on {name}  ({height}x{width}, {n_free} free, {n_obstacles} obstacles)")

    print()
    print("Input  ('.' free, '#' obstacle):")
    print(indent(terrain))

    for label, layout in baselines:
        if layout is None:
            continue
        print()
        print(f"{label} by hand  ('W' water, 'C' cane, '.' free but unused):")
        print(indent(layout.render()))

    print()
    print(f"Optimal layout from optifarm  (crop: {optimal.crop_name}, solver: {SOLVER}):")
    print(indent(optimal.render()))

    print()
    print("Metrics:")
    print_metrics(optimal.metrics, crop_word="cane", support_word="water")

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
    heading("Sugarcane on every terrain")
    print()
    print("This takes a few seconds -- large_15x15 alone needs ~12s to prove")
    print("optimality.")

    rows: list[tuple[str, ...]] = []
    for name in TERRAINS:
        print(f"  ... solving {name}", flush=True)
        optimal, baselines = run_one(name, verbose=False)
        by_label = dict(baselines)

        optimal_col = f"{optimal.metrics.n_crop} ({optimal.metrics.efficiency:.1f}%)"
        if not optimal.metrics.is_optimal:
            optimal_col += "*"

        rows.append(
            (
                name,
                str(optimal.metrics.n_free),
                _cell(by_label["Checkerboard"]),
                _cell(by_label["1x2 stripes"]),
                _cell(by_label["Greedy water"]),
                optimal_col,
                _gain_cell(optimal, by_label["Greedy water"]),
            )
        )

    print_table(
        ("Terrain", "Free", "Checkerboard", "1x2 stripes", "Greedy water", "Optimal", "vs greedy"),
        (14, 4, 13, 13, 13, 13, 10),
        rows,
    )

    if any(row[5].endswith("*") for row in rows):
        print()
        print("  * time limit ran out; the value is a lower bound, not a proven optimum.")

    print()
    print("  The checkerboard is safe but wasteful: it gives every cane four water")
    print("  neighbours when one would do, so it spends half the terrain on water.")
    print("  The 1x2 stripes fix that and land at 2/3 -- genuinely good, and what")
    print("  people build. But a player who follows no pattern and simply digs the")
    print("  water that pays best beats the stripes on every terrain here.")
    print()
    print("  So read 'vs greedy', not 'vs the patterns'. Beating a pattern by 20-30%")
    print("  sounds impressive and is mostly a fact about patterns. Against someone")
    print("  actually thinking, the exact optimum is worth a few percent -- real, and")
    print("  a good deal smaller. It is still worth having, which is more than can be")
    print("  said for cactus: run demo_cactus.py to see the solver earn nothing at all.")


def main() -> None:
    """Entry point: run one terrain, or all of them, per the configuration."""
    if RUN_ALL:
        run_all()
    else:
        run_one(TERRAIN)
        print()
        print("Tip: edit TERRAIN at the top of this file to try another terrain,")
        print("     or set RUN_ALL = True to compare them all at once.")
        print("     For the opposite lesson, run demo_cactus.py.")
    print()


if __name__ == "__main__":
    main()
