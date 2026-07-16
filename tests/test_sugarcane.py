"""The sugarcane model: known optima, degenerate terrains, and rule validity.

The hardcoded optima in this file were each verified against an exhaustive
enumeration of every water placement -- the same method as
:func:`tests.conftest.brute_force_optimum`, run offline in vectorised form for
the grids too large to enumerate inside a test. They are facts about the
problem, not recordings of what the solver said.
"""

from __future__ import annotations

import pytest

from mcfarm_opt import BlockType, Cell, SolveStatus, Sugarcane, optimize

from .conftest import assert_valid_sugarcane, brute_force_sugarcane_optimum


class TestKnownOptima:
    def test_empty_5x5_reaches_18(self, rectangle):
        """The headline case.

        The bound: with *w* water on 25 cells, cane is capped both by the cells
        left over (25 - w) and by coverage, since each water serves at most 4
        neighbours (4w). Those cross at w=5, c=20 -- but 20 is unreachable,
        because a corner's only neighbours are edge cells, and an edge water
        covers at most 3. The true optimum is 18, with 7 water.
        """
        layout = optimize(rectangle(5, 5), crop=Sugarcane(), solver="ilp")
        assert layout.metrics.n_crop == 18
        assert layout.metrics.n_support == 7
        assert layout.metrics.is_optimal
        assert_valid_sugarcane(layout)

    def test_obstacle_in_the_middle_costs_exactly_one_cane(self, rectangle):
        """The blocked centre cell is one fewer cane and no more: 17, not 16.

        The centre of a 5x5 is a cell the optimum plants rather than floods, so
        removing it removes a cane but does not force the water to rearrange.
        """
        layout = optimize(".....\n.....\n..#..\n.....\n.....", crop=Sugarcane())
        assert layout.metrics.n_crop == 17
        assert layout.metrics.n_obstacle == 1
        assert layout.block_at(Cell(2, 2)) is BlockType.OBSTACLE
        assert_valid_sugarcane(layout)

    def test_l_shaped_terrain(self):
        """An L: a 5x5 with a 2x2 bite taken out of the top-right corner."""
        layout = optimize("...##\n...##\n.....\n.....\n.....", crop=Sugarcane())
        assert layout.metrics.n_crop == 15
        assert layout.metrics.n_obstacle == 4
        assert layout.metrics.n_free == 21
        assert layout.metrics.is_optimal
        assert_valid_sugarcane(layout)

    def test_scattered_obstacles(self):
        layout = optimize(".#.#.\n.....\n#...#\n.....\n.#.#.", crop=Sugarcane())
        assert layout.metrics.n_crop == 12
        assert_valid_sugarcane(layout)

    def test_empty_4x4(self, rectangle):
        layout = optimize(rectangle(4, 4), crop=Sugarcane())
        assert layout.metrics.n_crop == 12
        assert_valid_sugarcane(layout)


class TestDegenerate:
    @pytest.mark.parametrize(
        "width, expected",
        [(1, 0), (2, 1), (3, 2), (4, 2), (5, 3), (6, 4), (7, 4), (8, 5), (9, 6)],
    )
    def test_1xn_strip(self, width, expected):
        """A 1xN strip.

        In one dimension each water covers at most its 2 sides, so cane is
        capped by both ``2w`` and ``N - w``, giving ``floor(2N/3)``. The single
        cell case is the sharp end: one cell has no neighbour, so it can never
        be both water and served -- zero cane, not one.
        """
        layout = optimize("." * width, crop=Sugarcane())
        assert layout.metrics.n_crop == expected == 2 * width // 3
        assert_valid_sugarcane(layout)

    def test_1x1_cannot_grow_anything(self):
        layout = optimize(".", crop=Sugarcane())
        assert layout.metrics.n_crop == 0
        assert layout.render() in {".", "W"}
        assert layout.metrics.is_optimal

    def test_nx1_column_matches_1xn_row(self, rectangle):
        assert optimize(rectangle(7, 1), crop=Sugarcane()).metrics.n_crop == 4

    def test_fully_blocked_grid_yields_nothing_without_crashing(self):
        layout = optimize("###\n###", crop=Sugarcane())
        assert layout.metrics.n_crop == 0
        assert layout.metrics.n_free == 0
        assert layout.metrics.n_obstacle == 6
        assert layout.metrics.efficiency == 0.0
        assert layout.render() == "###\n###"
        assert layout.metrics.is_optimal
        assert_valid_sugarcane(layout)

    def test_empty_terrain_yields_empty_layout(self):
        layout = optimize("", crop=Sugarcane())
        assert layout.render() == ""
        assert layout.metrics.n_cells == 0
        assert layout.metrics.efficiency == 0.0

    def test_isolated_free_cells_grow_nothing(self):
        """Free cells that no water can reach are left alone, not forced."""
        layout = optimize(".#.\n###\n.#.", crop=Sugarcane())
        assert layout.metrics.n_crop == 0
        assert_valid_sugarcane(layout)


class TestAgainstBruteForce:
    """Cross-check the CP-SAT model against exhaustive enumeration.

    These are the tests that would catch a wrong *model* rather than a wrong
    solver -- the oracle shares no code with the library.
    """

    @pytest.mark.parametrize(
        "terrain",
        [
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
            ".....\n.....",
            ".....\n.....\n.....",
        ],
    )
    def test_matches_exhaustive_enumeration(self, terrain):
        layout = optimize(terrain, crop=Sugarcane())
        assert layout.metrics.n_crop == brute_force_sugarcane_optimum(terrain)
        assert layout.metrics.is_optimal
        assert_valid_sugarcane(layout)


class TestRendering:
    def test_render_uses_the_documented_alphabet(self, rectangle):
        rendered = optimize(rectangle(4, 4), crop=Sugarcane()).render()
        assert set(rendered) <= {"W", "C", ".", "\n"}

    def test_render_preserves_shape_and_obstacles(self):
        terrain = "...##\n...##\n....."
        rendered = optimize(terrain, crop=Sugarcane()).render()
        assert [len(r) for r in rendered.splitlines()] == [5, 5, 5]
        for r, row in enumerate(terrain.splitlines()):
            for c, char in enumerate(row):
                if char == "#":
                    assert rendered.splitlines()[r][c] == "#"

    def test_str_is_render(self, rectangle):
        layout = optimize(rectangle(3, 3), crop=Sugarcane())
        assert str(layout) == layout.render()


class TestSolverBehaviour:
    def test_time_limit_still_returns_a_valid_layout(self, rectangle):
        layout = optimize(rectangle(6, 6), crop=Sugarcane(), time_limit=5.0)
        assert layout.metrics.status.is_solved
        assert_valid_sugarcane(layout)

    def test_solve_time_is_recorded(self, rectangle):
        assert optimize(rectangle(5, 5), crop=Sugarcane()).metrics.solve_time >= 0.0

    def test_status_is_optimal_for_a_completed_search(self, rectangle):
        assert optimize(rectangle(3, 3), crop=Sugarcane()).metrics.status is SolveStatus.OPTIMAL
