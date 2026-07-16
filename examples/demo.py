"""Runnable demo for optifarm: `python examples/demo.py`.

This file is didactic -- it *is* the usage documentation. It runs with no
arguments and no dependency beyond what the project already needs.

To experiment, edit ONE line in the configuration block below (``TERRAIN``) and
run it again. Or set ``RUN_ALL = True`` to see the summary table across every
terrain at once.

What it shows:

1. the input terrain;
2. the layouts two hand-built patterns produce (checkerboard, 1x2 stripes);
3. the optimal layout optifarm computed;
4. the metrics, and how much the exact optimisation beats each hand pattern by.

Everything here uses only the public API (``optimize``, ``FarmLayout``,
``FarmMetrics``, ``Grid``, ``BlockType``). Nothing from the core is
reimplemented.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from typing import Literal

from mcfarm_opt import (
    BlockType,
    Cell,
    CropRule,
    FarmLayout,
    FarmMetrics,
    Grid,
    SolveStatus,
    Sugarcane,
    optimize,
    parse_grid,
)

# ============================================================================
# TERRAINS
# ============================================================================
# '.' = free ground, '#' = obstacle (rock, natural water, whatever).
# Every line of a terrain must be the same length.

TERRAINS: dict[str, str] = {
    # Empty rectangle: the simplest case, good for checking against intuition.
    "rectangle_9x9": """\
.........
.........
.........
.........
.........
.........
.........
.........
.........""",
    # L-shaped terrain: a rectangular bite out of the top-right corner.
    # Shows the solver coping with an irregular border.
    "l_shape": """\
......####
......####
......####
..........
..........
..........
..........
..........""",
    # Obstacles scattered through the middle: the case where hand patterns
    # suffer, because a '#' sitting on a water stripe strands the cane around it.
    "with_obstacles": """\
..........
...##.....
..........
.....#....
..##......
..........
......##..
..........
...#......
..........""",
    # Large: 225 cells. This is the one to feel the solver's cost -- proving
    # optimality here takes seconds, against milliseconds for the others.
    "large_15x15": """\
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............""",
}

# ============================================================================
# CONFIGURATION -- edit here
# ============================================================================

TERRAIN: str = "large_15x15"  # options: rectangle_9x9 | l_shape | with_obstacles | large_15x15
CROP: CropRule = Sugarcane()  # options: Sugarcane() (the only one implemented so far)
SOLVER: str = "ilp"  # options: "ilp" (exact, via CP-SAT)

RUN_ALL: bool = False  # True = ignore TERRAIN, run every terrain with a summary table

# Seconds the solver may spend before returning the best it has found.
# None = no limit. large_15x15 takes ~12s to prove optimality; the others are
# instant. If the limit runs out the result is still a valid layout -- it just
# is not provably optimal, and the demo says so rather than pretending.
TIME_LIMIT: float | None = 30.0


# ============================================================================
# BASELINES: the patterns people build by hand
# ============================================================================
# Two of them, and the contrast is the point. Both are legal layouts; both are
# beaten by the solver; they lose for different reasons.

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

    Args:
        grid: the terrain.
        parity: which colour of the board gets the water (0 or 1).
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


def _build_layout(
    grid: Grid, assignment: Mapping[Cell, BlockType], name: str
) -> FarmLayout:
    """Wrap a raw assignment into a FarmLayout, with its blocks counted.

    Reuses the library's own FarmMetrics, so efficiency comes out measured over
    the free cells (obstacles excluded) for free -- it is the definition the
    core already uses.
    """
    counts = {block: 0 for block in BlockType}
    for block in assignment.values():
        counts[block] += 1

    metrics = FarmMetrics(
        n_crop=counts[BlockType.CROP],
        n_support=counts[BlockType.WATER],
        n_empty=counts[BlockType.EMPTY],
        n_obstacle=counts[BlockType.OBSTACLE],
        solve_time=0.0,
        # A hand pattern is a valid layout, but nobody proved it is the best one
        # -- FEASIBLE says precisely that. Claiming OPTIMAL here would be a lie.
        status=SolveStatus.FEASIBLE,
    )
    return FarmLayout(grid=grid, assignment=dict(assignment), metrics=metrics, crop_name=name)


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
        _build_layout(grid, _apply_stripes(grid, orientation, offset), "1x2 stripes")
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
        _build_layout(grid, _apply_checkerboard(grid, parity), "checkerboard")
        for parity in (0, 1)
    ]
    best = max(candidates, key=lambda layout: layout.metrics.n_crop)
    return best if best.metrics.n_crop > 0 else None


# The hand patterns to measure against, worst-expected first so the printed
# comparison reads as a progression up to the optimum.
BASELINES: tuple[tuple[str, Callable[[Grid], FarmLayout | None]], ...] = (
    ("Checkerboard", baseline_checkerboard),
    ("1x2 stripes", baseline_stripes_1x2),
)


# ============================================================================
# PRINTING
# ============================================================================


def _arrow() -> str:
    """Return '→' if the terminal can encode it, else '->'.

    The default Windows console is cp1252, which has no U+2192: printing the
    arrow there raises UnicodeEncodeError and kills the demo mid-comparison.
    Rather than reconfiguring the whole stdout, we ask and degrade this one
    character.
    """
    try:
        "→".encode(sys.stdout.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        return "->"
    return "→"


def _indent(text: str, spaces: int = 2) -> str:
    """Indent every line, so the grid does not hug the terminal margin."""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def _heading(text: str) -> None:
    """Print a section header."""
    print()
    print("=" * 66)
    print(f" {text}")
    print("=" * 66)


def print_metrics(metrics: FarmMetrics) -> None:
    """Print a layout's metrics, one per line."""
    print(f"  cane ......... {metrics.n_crop}")
    print(f"  water ........ {metrics.n_support}")
    print(f"  free, unused . {metrics.n_empty}")
    print(
        f"  efficiency ... {metrics.efficiency:.1f}%"
        f"  (over {metrics.n_free} free cells, obstacles excluded)"
    )
    print(f"  solver time .. {metrics.solve_time:.3f}s")
    print(f"  status ....... {metrics.status.value}")
    if not metrics.is_optimal:
        print("  WARNING: the time limit ran out before optimality was proven.")
        print("           The layout is valid; the cane count is a lower bound.")


def print_comparison(optimal: FarmLayout, baselines: list[tuple[str, FarmLayout | None]]) -> None:
    """Print how the optimum compares against each hand-built pattern.

    Degrades gracefully: a pattern that does not apply to this terrain is
    reported as such rather than crashing or being silently dropped.
    """
    arrow = _arrow()
    print()
    print("Compared against the hand-built patterns:")

    for label, layout in baselines:
        if layout is None:
            print(f"  {label + ':':<20} does not apply to this terrain (no stripe fits)")
            continue
        n = layout.metrics.n_crop
        gain = 100.0 * (optimal.metrics.n_crop - n) / n
        verdict = (
            f"{arrow} optifarm +{gain:.1f}%"
            if gain > 0
            else f"{arrow} tie: this pattern is already optimal here"
            if gain == 0
            # Impossible: the optimum is by definition >= any valid layout. If
            # this fires, either the prune or the model is broken.
            else f"{arrow} {gain:.1f}%  (!! the optimum should never lose)"
        )
        print(f"  {label + ':':<20} {n:3d} cane  ({layout.metrics.efficiency:5.1f}%)   {verdict}")

    print(
        f"  {'Optimal (optifarm):':<20} {optimal.metrics.n_crop:3d} cane  "
        f"({optimal.metrics.efficiency:5.1f}%)"
    )


# ============================================================================
# RUNNING
# ============================================================================


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
    _heading(f"Terrain: {name}  ({height}x{width}, {n_free} free, {n_obstacles} obstacles)")

    print()
    print("Input  ('.' free, '#' obstacle):")
    print(_indent(terrain))

    for label, layout in baselines:
        if layout is None:
            continue
        print()
        print(f"{label} by hand  ('W' water, 'C' cane, '.' free but unused):")
        print(_indent(layout.render()))

    print()
    print(f"Optimal layout from optifarm  (crop: {optimal.crop_name}, solver: {SOLVER}):")
    print(_indent(optimal.render()))

    print()
    print("Metrics:")
    print_metrics(optimal.metrics)

    print_comparison(optimal, baselines)
    return optimal, baselines


def _column(layout: FarmLayout | None) -> str:
    """Format one baseline's cell for the summary table."""
    if layout is None:
        return "n/a"
    return f"{layout.metrics.n_crop} ({layout.metrics.efficiency:.1f}%)"


def _gain(optimal: FarmLayout, layout: FarmLayout | None) -> str:
    """Format the optimum's gain over one baseline, for the summary table."""
    if layout is None or layout.metrics.n_crop == 0:
        return "n/a"
    gain = 100.0 * (optimal.metrics.n_crop - layout.metrics.n_crop) / layout.metrics.n_crop
    return f"+{gain:.1f}%"


def run_all() -> None:
    """Run every terrain and print a summary table: each baseline vs the optimum."""
    _heading("Running every terrain")
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
                _column(by_label["Checkerboard"]),
                _column(by_label["1x2 stripes"]),
                optimal_col,
                _gain(optimal, by_label["Checkerboard"]),
                _gain(optimal, by_label["1x2 stripes"]),
            )
        )

    header = ("Terrain", "Free", "Checkerboard", "1x2 stripes", "Optimal", "vs check", "vs 1x2")
    widths = (16, 5, 14, 14, 14, 9, 8)

    def format_row(cells: tuple[str, ...]) -> str:
        """First column left-aligned (it is a name), the numbers right-aligned."""
        parts = [
            f"{cell:<{width}}" if i == 0 else f"{cell:>{width}}"
            # strict: a row that does not match the header is a bug, and a
            # silently truncated table would hide it.
            for i, (cell, width) in enumerate(zip(cells, widths, strict=True))
        ]
        return "  " + "  ".join(parts)

    print()
    print(format_row(header))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print(format_row(row))

    if any(row[4].endswith("*") for row in rows):
        print()
        print("  * time limit ran out; the value is a lower bound, not a proven optimum.")

    print()
    print("  The checkerboard is safe but wasteful: it gives every cane four water")
    print("  neighbours when one would do, so it spends half the terrain on water.")
    print("  The 1x2 stripes fix that and land at 2/3. The solver does better still,")
    print("  and its lead is widest where obstacles break the hand patterns' stripes.")


def main() -> None:
    """Entry point: run one terrain, or all of them, per the configuration."""
    if RUN_ALL:
        run_all()
    else:
        run_one(TERRAIN)
        print()
        print("Tip: edit TERRAIN at the top of this file to try another terrain,")
        print("     or set RUN_ALL = True to compare them all at once.")
    print()


if __name__ == "__main__":
    main()
