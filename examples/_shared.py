"""Plumbing shared by the demos: terrains, printing, tables.

**You do not need to read this file.** The demos are the documentation; this is
the formatting they lean on so that neither has to carry 150 lines of ``print``
alignment. The interesting parts -- how a crop is optimised, what the hand-built
patterns are, what the comparison means -- live in ``demo_sugarcane.py`` and
``demo_cactus.py``.

The terrains live here on purpose, so both demos solve the *same* land. That is
what makes the cross-crop numbers comparable: on ``scattered``, the identical
5x5 grows 12 sugarcane and 2 cactus.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping

from mcfarm_opt import (
    BlockType,
    Cell,
    FarmLayout,
    FarmMetrics,
    Grid,
    SolveStatus,
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
    #
    # 11 wide, not 10, and the extra column is the whole point. The 1x2 stripe
    # pattern has period 3, so it only tiles a field cleanly when the width is
    # 1 (mod 3): stripes at 1, 4, 7, 10 reach columns 0 through 11. At width 10
    # the last stripe lands on 7 and column 9 falls outside every stripe's
    # reach -- ten tiles of good ground, no rock near them, dead purely to
    # arithmetic. Nobody builds a farm that shape; they build one more column
    # and the pattern fits. Measuring the solver against a pattern crippled by
    # the field size would have been a strawman, and a subtle one, because the
    # dead column looks like the obstacles' fault and is not.
    "with_obstacles": """\
...........
...##......
...........
.....#.....
..##.......
...........
......##...
...........
...#.......
.........#.
...........""",
    # Small and genuinely messy. Both crops need a terrain where no global
    # pattern fits, and this is it: the obstacles sit at odd spacings, so the
    # right answer differs from region to region. It is the terrain where the
    # cactus checkerboard finally loses.
    "ragged": """\
..#...
......
.#..#.
......
...#..""",
    # Large: 225 cells. This is the one to feel the solver's cost -- proving
    # optimality here takes seconds for sugarcane, and no time at all for cactus.
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
# BUILDING A HAND-BUILT LAYOUT
# ============================================================================


def build_layout(grid: Grid, assignment: Mapping[Cell, BlockType], name: str) -> FarmLayout:
    """Wrap a raw assignment into a FarmLayout, with its blocks counted.

    Reuses the library's own FarmMetrics, so efficiency comes out measured over
    the free cells (obstacles excluded) for free -- it is the definition the
    core already uses.
    """
    counts = dict.fromkeys(BlockType, 0)
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


# ============================================================================
# PRINTING
# ============================================================================


def arrow() -> str:
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


def indent(text: str, spaces: int = 2) -> str:
    """Indent every line, so the grid does not hug the terminal margin."""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def heading(text: str) -> None:
    """Print a section header."""
    print()
    print("=" * 66)
    print(f" {text}")
    print("=" * 66)


def print_metrics(metrics: FarmMetrics, *, crop_word: str, support_word: str | None) -> None:
    """Print a layout's metrics, one per line.

    Args:
        metrics: what to print.
        crop_word: what to call the crop ("cane", "cactus").
        support_word: what to call the support block ("water"), or ``None`` for
            a crop that places none -- cactus would only ever print "water 0",
            which is noise dressed up as information.
    """
    print(f"  {crop_word + ' ':.<14} {metrics.n_crop}")
    if support_word is not None:
        print(f"  {support_word + ' ':.<14} {metrics.n_support}")
    print(f"  {'free, unused ':.<14} {metrics.n_empty}")
    print(
        f"  {'efficiency ':.<14} {metrics.efficiency:.1f}%"
        f"  (over {metrics.n_free} free cells, obstacles excluded)"
    )
    print(f"  {'solver time ':.<14} {metrics.solve_time:.3f}s")
    print(f"  {'status ':.<14} {metrics.status.value}")
    if not metrics.is_optimal:
        print("  WARNING: the time limit ran out before optimality was proven.")
        print(f"           The layout is valid; the {crop_word} count is a lower bound.")


def print_table(
    header: tuple[str, ...], widths: tuple[int, ...], rows: list[tuple[str, ...]]
) -> None:
    """Print a summary table: first column left-aligned, the numbers right."""

    def format_row(cells: tuple[str, ...]) -> str:
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


def gain_over(optimal: FarmLayout, baseline: FarmLayout | None) -> float | None:
    """Percent more crop the optimum grows than ``baseline``.

    Returns ``None`` when there is nothing to compare against.
    """
    if baseline is None or baseline.metrics.n_crop == 0:
        return None
    return 100.0 * (optimal.metrics.n_crop - baseline.metrics.n_crop) / baseline.metrics.n_crop
