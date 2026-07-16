"""The cactus model: known optima, the closed form, and rule validity.

Every hardcoded optimum here was verified against an exhaustive enumeration of
every possible cactus placement -- the same method as
:func:`tests.conftest.brute_force_cactus_optimum`, run offline in vectorised
form for the grids too large to enumerate inside a test. They are facts about
the problem, not recordings of what the solver said.

Cactus has something sugarcane does not: a closed form. On open ground the rule
"no two cacti adjacent" is maximum independent set on a grid graph, whose answer
is exactly ``ceil(rows * cols / 2)`` -- the checkerboard. That gives a second,
fully independent check on every open rectangle.
"""

from __future__ import annotations

import math

import pytest

from mcfarm_opt import BlockType, Cactus, Cell, SolveStatus, Sugarcane, optimize

from .conftest import assert_valid_cactus, brute_force_cactus_optimum


class TestKnownOptima:
    def test_empty_5x5_is_the_13_cell_checkerboard(self, rectangle):
        """The headline case.

        No two cacti may touch, so the answer is a maximum independent set of
        the 5x5 grid graph. The grid is bipartite -- colour it like a chessboard
        -- and the larger colour has 13 of the 25 cells, every pair of which is
        diagonal rather than adjacent. 13 it is.
        """
        layout = optimize(rectangle(5, 5), crop=Cactus(), solver="ilp")
        assert layout.metrics.n_crop == 13
        assert layout.metrics.is_optimal
        assert_valid_cactus(layout)

    def test_the_5x5_answer_really_is_a_checkerboard(self, rectangle):
        """Both diagonals of the board are legal; only the 13-cell colour is optimal."""
        layout = optimize(rectangle(5, 5), crop=Cactus())
        planted = layout.cells_with(BlockType.CROP)
        parities = {(cell.row + cell.col) % 2 for cell in planted}
        assert len(parities) == 1, "an optimal 5x5 cactus layout is one colour of the board"

    def test_empty_4x4(self, rectangle):
        layout = optimize(rectangle(4, 4), crop=Cactus())
        assert layout.metrics.n_crop == 8
        assert_valid_cactus(layout)

    def test_empty_3x3(self, rectangle):
        layout = optimize(rectangle(3, 3), crop=Cactus())
        assert layout.metrics.n_crop == 5
        assert_valid_cactus(layout)

    def test_obstacle_in_the_middle_costs_exactly_one_cactus(self):
        """13 -> 12, not 13 - 5.

        An obstacle poisons its neighbours as well as its own cell, so it *can*
        cost five. Not here: the centre of a 5x5 sits on the majority colour, so
        it was planted, while its four neighbours sit on the other colour and
        were already empty. Removing it costs the one cell it occupied.
        """
        layout = optimize(".....\n.....\n..#..\n.....\n.....", crop=Cactus())
        assert layout.metrics.n_crop == 12
        assert layout.metrics.n_obstacle == 1
        assert layout.block_at(Cell(2, 2)) is BlockType.OBSTACLE
        assert_valid_cactus(layout)

    def test_l_shaped_terrain(self):
        layout = optimize("...##\n...##\n.....\n.....\n.....", crop=Cactus())
        assert layout.metrics.n_crop == 9
        assert layout.metrics.n_obstacle == 4
        assert layout.metrics.is_optimal
        assert_valid_cactus(layout)

    def test_scattered_obstacles_are_devastating(self):
        """The same terrain grows 12 sugarcane and 2 cactus.

        Six obstacles poison so much of a 5x5 that only two cells survive with
        no solid neighbour. This is the cactus rule's whole character: cane is
        drawn to features, cactus is repelled by them.
        """
        terrain = ".#.#.\n.....\n#...#\n.....\n.#.#."
        layout = optimize(terrain, crop=Cactus())
        assert layout.metrics.n_crop == 2
        assert optimize(terrain, crop=Sugarcane()).metrics.n_crop == 12
        assert_valid_cactus(layout)


class TestClosedForm:
    """On open ground the optimum is ceil(rows*cols/2) -- an independent check."""

    @pytest.mark.parametrize("rows", range(1, 7))
    @pytest.mark.parametrize("cols", range(1, 7))
    def test_open_rectangle_matches_the_checkerboard_bound(self, rows, cols, rectangle):
        layout = optimize(rectangle(rows, cols), crop=Cactus())
        assert layout.metrics.n_crop == math.ceil(rows * cols / 2)
        assert layout.metrics.is_optimal
        assert_valid_cactus(layout)

    def test_open_ground_is_always_about_half(self, rectangle):
        """Half the terrain, near enough -- and never more."""
        layout = optimize(rectangle(8, 8), crop=Cactus())
        assert layout.metrics.n_crop == 32
        assert layout.metrics.efficiency == pytest.approx(50.0)


class TestDegenerate:
    def test_a_single_cell_grows_a_cactus(self):
        """The mirror of sugarcane, which grows nothing on 1x1.

        One cell has no neighbours at all, so nothing solid touches it: cactus
        is happy. Cane, needing a neighbour to hold water, is not.
        """
        layout = optimize(".", crop=Cactus())
        assert layout.metrics.n_crop == 1
        assert layout.render() == "C"
        assert optimize(".", crop=Sugarcane()).metrics.n_crop == 0

    @pytest.mark.parametrize("width, expected", [(1, 1), (2, 1), (3, 2), (4, 2), (7, 4), (8, 4)])
    def test_1xn_strip(self, width, expected):
        """A 1xN strip alternates: every other cell, ceil(N/2)."""
        layout = optimize("." * width, crop=Cactus())
        assert layout.metrics.n_crop == expected == math.ceil(width / 2)
        assert_valid_cactus(layout)

    def test_fully_blocked_grid_yields_nothing_without_crashing(self):
        layout = optimize("###\n###", crop=Cactus())
        assert layout.metrics.n_crop == 0
        assert layout.metrics.n_free == 0
        assert layout.metrics.efficiency == 0.0
        assert layout.render() == "###\n###"
        assert layout.metrics.is_optimal
        assert_valid_cactus(layout)

    def test_empty_terrain_yields_empty_layout(self):
        layout = optimize("", crop=Cactus())
        assert layout.render() == ""
        assert layout.metrics.n_cells == 0

    def test_a_corridor_one_cell_wide_grows_nothing(self):
        """Every free cell touches a wall, so nothing can be planted at all.

        Sugarcane manages 5 here. Cactus manages zero, and must say so rather
        than squeezing one in against the wall.
        """
        terrain = "#...#\n#.#.#\n#...#"
        layout = optimize(terrain, crop=Cactus())
        assert layout.metrics.n_crop == 0
        assert layout.metrics.is_optimal
        assert optimize(terrain, crop=Sugarcane()).metrics.n_crop == 5
        assert_valid_cactus(layout)


class TestAgainstBruteForce:
    """Cross-check the CP-SAT model against exhaustive enumeration.

    These would catch a wrong *model* rather than a wrong solver -- the oracle
    shares no code with the library.
    """

    @pytest.mark.parametrize(
        "terrain",
        [
            ".",
            "..",
            "...",
            "..\n..",
            "...\n...",
            "....\n....",
            "...\n...\n...",
            "..\n..\n..\n..",
            ".#.\n...\n.#.",
            "#..\n...\n..#",
            "....\n.##.\n....",
            "." * 12,
            ".#.#.\n.....",
            "###\n###",
            "#.#\n...\n#.#",
        ],
    )
    def test_matches_exhaustive_enumeration(self, terrain):
        layout = optimize(terrain, crop=Cactus())
        assert layout.metrics.n_crop == brute_force_cactus_optimum(terrain)
        assert layout.metrics.is_optimal
        assert_valid_cactus(layout)


class TestTheRule:
    def test_no_two_cacti_are_orthogonally_adjacent(self, rectangle):
        layout = optimize(rectangle(6, 6), crop=Cactus())
        for cell in layout.cells_with(BlockType.CROP):
            for neighbor in layout.grid.neighbors(cell):
                assert layout.block_at(neighbor) is not BlockType.CROP

    def test_no_cactus_hugs_an_obstacle(self):
        """An obstacle is a wall, and a wall breaks cactus.

        This is the case that would silently break if obstacles were dropped
        from the neighbourhood count instead of being fixed to OBSTACLE.
        """
        layout = optimize(".....\n.....\n..#..\n.....\n.....", crop=Cactus())
        for neighbor in layout.grid.neighbors(Cell(2, 2)):
            assert layout.block_at(neighbor) is not BlockType.CROP

    def test_diagonal_neighbours_are_fine(self):
        """The rule is orthogonal only -- diagonals are what make a checkerboard work."""
        layout = optimize("..\n..", crop=Cactus())
        planted = layout.cells_with(BlockType.CROP)
        assert len(planted) == 2
        a, b = planted
        assert abs(a.row - b.row) == 1 and abs(a.col - b.col) == 1

    def test_cactus_places_no_support_blocks(self, rectangle):
        """The sand is under the cactus, not beside it, so nothing is placed.

        A layout of cactus is cactus and bare ground, nothing else.
        """
        layout = optimize(rectangle(5, 5), crop=Cactus())
        assert layout.metrics.n_support == 0
        assert Cactus().support_blocks() == frozenset()
        assert set(layout.render()) <= {"C", ".", "\n"}

    def test_sand_is_not_part_of_the_model(self):
        """Cactus never places sand, so 'sand beside me' cannot arise.

        Guards the projection decision: if sand were ever added as a support
        block, it would start (wrongly) breaking the cactus beside it.
        """
        assert BlockType.SAND not in Cactus().block_types()
        assert Cactus().block_types() == frozenset({BlockType.CROP})

    def test_solid_at_cactus_level_is_narrower_than_is_solid(self):
        """Sand is a solid block, but not solid *where the cactus is*."""
        from mcfarm_opt.crops.cactus import SOLID_AT_CACTUS_LEVEL

        assert SOLID_AT_CACTUS_LEVEL == {BlockType.CROP, BlockType.OBSTACLE}
        assert BlockType.SAND.is_solid
        assert BlockType.SAND not in SOLID_AT_CACTUS_LEVEL


class TestSolverBehaviour:
    def test_the_name_is_reported(self, rectangle):
        assert optimize(rectangle(3, 3), crop=Cactus()).crop_name == "cactus"

    def test_status_is_optimal(self, rectangle):
        assert optimize(rectangle(4, 4), crop=Cactus()).metrics.status is SolveStatus.OPTIMAL

    def test_large_terrain_is_still_instant(self, rectangle):
        """Cactus is bipartite maximum independent set, so it is polynomial.

        Sugarcane cannot prove an 18x18 in 30 seconds. Cactus proves a 30x30
        without a time limit at all -- a real difference in kind, not degree.
        """
        layout = optimize(rectangle(30, 30), crop=Cactus())
        assert layout.metrics.n_crop == 450
        assert layout.metrics.is_optimal
