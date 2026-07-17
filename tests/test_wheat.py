"""The wheat model: the closed form, known optima, and rule validity.

Wheat cannot be checked the way sugarcane and cactus are. Brute force is
exponential and wheat's interesting cases start at 81 free cells, so the oracle
only reaches 1xN strips and toy grids.

What it has instead is better: a **closed form**. On an open ``m x n`` rectangle
the optimum is exactly

    m*n - ceil(m/9) * ceil(n/9)

by a witness argument -- cells 9 apart cannot share a water source, since one
source only reaches 4, so two cells it serves are within 8 of each other. That
forces ``ceil(m/9) * ceil(n/9)`` sources, and a 9-spaced lattice achieves it.
Every open rectangle below is checked against arithmetic that owes the solver
nothing, which is a stronger guarantee than enumeration could give anyway.
"""

from __future__ import annotations

import math

import pytest

from mcfarm_opt import (
    BlockType,
    Cactus,
    Cell,
    Neighborhood,
    SolveStatus,
    Sugarcane,
    Wheat,
    optimize,
)

from .conftest import assert_valid_wheat, brute_force_wheat_optimum


def _closed_form(rows: int, cols: int) -> int:
    """The proven optimum for an open rows x cols rectangle."""
    return rows * cols - math.ceil(rows / 9) * math.ceil(cols / 9)


class TestTheHeadline:
    def test_one_water_hydrates_an_entire_9x9(self, rectangle):
        """The rule, at exactly the size it was written for.

        Water reaches 4 blocks in every direction, so a single source at the
        centre covers the whole 9x9 and every other cell grows wheat.
        """
        layout = optimize(rectangle(9, 9), crop=Wheat(), solver="ilp")
        assert layout.metrics.n_crop == 80
        assert layout.metrics.n_support == 1
        assert layout.metrics.is_optimal
        assert_valid_wheat(layout)

    def test_the_single_water_sits_where_it_reaches_everything(self, rectangle):
        """It has to be the centre: only from (4,4) is every cell within 4."""
        layout = optimize(rectangle(9, 9), crop=Wheat())
        assert layout.cells_with(BlockType.WATER) == [Cell(4, 4)]

    def test_the_9x9_is_nearly_all_wheat(self, rectangle):
        """98.8%. Water is almost free: it costs one cell and feeds eighty."""
        assert optimize(rectangle(9, 9), crop=Wheat()).metrics.efficiency == pytest.approx(
            98.8, abs=0.1
        )


class TestClosedForm:
    """m*n - ceil(m/9)*ceil(n/9), checked against the solver on open ground."""

    @pytest.mark.parametrize("rows", [1, 2, 5, 8, 9, 10, 13, 17, 18, 19])
    @pytest.mark.parametrize("cols", [1, 2, 5, 8, 9, 10, 13, 17, 18, 19])
    def test_open_rectangle_matches_the_witness_bound(self, rows, cols, rectangle):
        layout = optimize(rectangle(rows, cols), crop=Wheat(), time_limit=60.0)
        assert layout.metrics.n_crop == _closed_form(rows, cols)
        assert layout.metrics.is_optimal
        assert_valid_wheat(layout)

    @pytest.mark.parametrize(
        "size, water",
        [(9, 1), (10, 4), (18, 4), (19, 9), (27, 9)],
    )
    def test_water_count_steps_at_multiples_of_nine(self, size, water, rectangle):
        """The lattice: one source per 9x9 block, and the step is sharp.

        A 9x9 needs one source; a 10x10 needs four, because the tenth row and
        column cannot be reached from any single 9x9's centre. Nothing in
        between.
        """
        layout = optimize(rectangle(size, size), crop=Wheat(), time_limit=60.0)
        assert layout.metrics.n_support == water
        assert layout.metrics.n_crop == size * size - water


class TestAgainstBruteForce:
    """Exhaustive enumeration, where it still fits.

    1xN strips past N=9 are the smallest terrains where the covering problem is
    real: one source no longer reaches everything.
    """

    @pytest.mark.parametrize("width", range(1, 15))
    def test_1xn_strip_matches_enumeration(self, width):
        terrain = "." * width
        layout = optimize(terrain, crop=Wheat())
        assert layout.metrics.n_crop == brute_force_wheat_optimum(terrain)
        assert layout.metrics.n_crop == _closed_form(1, width)
        assert layout.metrics.is_optimal
        assert_valid_wheat(layout)

    @pytest.mark.parametrize(
        "terrain",
        [
            ".",
            "..",
            "..\n..",
            "...\n...",
            "....\n....",
            "...\n...\n...",
            ".#.\n...\n.#.",
            "#.#\n...\n#.#",
            "....\n.##.\n....",
            "###\n###",
        ],
    )
    def test_small_terrain_matches_enumeration(self, terrain):
        layout = optimize(terrain, crop=Wheat())
        assert layout.metrics.n_crop == brute_force_wheat_optimum(terrain)
        assert layout.metrics.is_optimal
        assert_valid_wheat(layout)


class TestDegenerate:
    def test_a_single_cell_grows_nothing(self):
        """Water does not hydrate the cell it occupies.

        One cell can be water (no wheat) or bare (no water in range, so no
        wheat). Either way zero -- the same trap sugarcane hits on 1x1, and the
        opposite of cactus, which is happy alone.
        """
        assert optimize(".", crop=Wheat()).metrics.n_crop == 0
        assert optimize(".", crop=Cactus()).metrics.n_crop == 1

    def test_two_cells_cost_one_water(self):
        assert optimize("..", crop=Wheat()).metrics.n_crop == 1

    def test_fully_blocked_grid_yields_nothing_without_crashing(self):
        layout = optimize("###\n###", crop=Wheat())
        assert layout.metrics.n_crop == 0
        assert layout.metrics.n_free == 0
        assert layout.metrics.efficiency == 0.0
        assert layout.render() == "###\n###"
        assert layout.metrics.is_optimal
        assert_valid_wheat(layout)

    def test_empty_terrain_yields_empty_layout(self):
        layout = optimize("", crop=Wheat())
        assert layout.render() == ""
        assert layout.metrics.n_cells == 0

    def test_two_pockets_out_of_reach_cannot_share_a_source(self):
        """Cells 10 apart: neither can hydrate the other, and each is alone.

        Whichever pocket takes the water, the other has none within 4 -- so the
        terrain grows nothing at all, despite having two perfectly good cells.
        """
        layout = optimize(".#########.", crop=Wheat())
        assert layout.metrics.n_crop == 0
        assert_valid_wheat(layout)


class TestTheRule:
    def test_hydration_reaches_exactly_four_blocks_diagonally(self):
        """The corner of the 9x9 is in range; one step further is not.

        A 9x9 with the water forced into a corner: Chebyshev distance means the
        opposite corner sits at exactly 8, out of reach.
        """
        layout = optimize("\n".join(["." * 9] * 9), crop=Wheat())
        water = layout.cells_with(BlockType.WATER)[0]
        for cell in layout.cells_with(BlockType.CROP):
            assert Neighborhood.DIAGONAL.distance(cell, water) <= 4

    def test_a_10x10_cannot_be_served_by_one_source(self, rectangle):
        """The witness argument, at the smallest size where it bites.

        (0,0) and (0,9) are 9 apart; a source within 4 of both would put them
        within 8 of each other. So one source cannot do it, and by symmetry
        neither can two or three -- it takes four.
        """
        layout = optimize(rectangle(10, 10), crop=Wheat())
        assert layout.metrics.n_support == 4
        assert layout.metrics.n_crop == 96

    def test_obstacles_do_not_block_hydration(self):
        """Minecraft checks distance, not line of sight.

        A wall of obstacles between the water and the wheat shades nothing, so
        every free cell on both sides of it still grows.
        """
        terrain = ".....\n#####\n.....\n#####\n....."
        layout = optimize(terrain, crop=Wheat())
        # 15 free cells, one becomes water, the other 14 are all within 4.
        assert layout.metrics.n_support == 1
        assert layout.metrics.n_crop == 14
        assert_valid_wheat(layout)

    def test_wheat_places_only_water(self, rectangle):
        """The farmland is under the wheat, not beside it, so it is never placed."""
        layout = optimize(rectangle(9, 9), crop=Wheat())
        assert Wheat().support_blocks() == frozenset({BlockType.WATER})
        assert Wheat().block_types() == frozenset({BlockType.WATER, BlockType.CROP})
        assert BlockType.FARMLAND not in Wheat().block_types()
        assert set(layout.render()) <= {"W", "C", ".", "\n"}


class TestAgainstTheOtherCrops:
    """Three rules, one core, three different answers on identical ground."""

    def test_reach_decides_the_yield(self, rectangle):
        """Same 9x9. Cactus 41, sugarcane 61, wheat 80.

        Nothing separates these but the adjacency rule: cactus forbids a
        neighbour, cane needs one within 1, wheat needs one within 4. The
        further the reach, the cheaper the support, and the yield follows.
        """
        terrain = rectangle(9, 9)
        assert optimize(terrain, crop=Cactus()).metrics.n_crop == 41
        assert optimize(terrain, crop=Sugarcane()).metrics.n_crop == 61
        assert optimize(terrain, crop=Wheat()).metrics.n_crop == 80

    def test_wheat_needs_far_less_water_than_sugarcane(self, rectangle):
        """One source per 81 cells, against one per four."""
        terrain = rectangle(9, 9)
        assert optimize(terrain, crop=Wheat()).metrics.n_support == 1
        assert optimize(terrain, crop=Sugarcane()).metrics.n_support == 20


class TestSolverBehaviour:
    def test_the_name_is_reported(self, rectangle):
        assert optimize(rectangle(9, 9), crop=Wheat()).crop_name == "wheat"

    def test_status_is_optimal(self, rectangle):
        assert optimize(rectangle(9, 9), crop=Wheat()).metrics.status is SolveStatus.OPTIMAL

    def test_large_terrain_is_still_quick(self, rectangle):
        """A 30x30 proves optimal without a time limit, despite 80-term constraints."""
        layout = optimize(rectangle(30, 30), crop=Wheat())
        assert layout.metrics.n_crop == _closed_form(30, 30)
        assert layout.metrics.is_optimal
