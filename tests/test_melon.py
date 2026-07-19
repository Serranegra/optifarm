"""Melon: hydration like wheat, plus a fruit block that cannot be shared.

The hydration half is wheat's and is tested lightly here -- ``test_wheat.py``
already owns that rule. What this file is really about is the pairing: that
every stem gets a melon of its own, that the model does not quietly let two
stems share one, and that the price of the fruit is what the arithmetic says.
"""

from __future__ import annotations

import pytest

from mcfarm_opt import (
    AdjacencyCropRule,
    BlockType,
    Cell,
    CropRule,
    Melon,
    Neighborhood,
    Wheat,
    optimize,
)
from mcfarm_opt.crops.wheat import Wheat as WheatRule

from .conftest import assert_valid_melon, brute_force_melon_optimum, solve


class TestTheRule:
    """The two halves of the rule, checked one at a time."""

    def test_a_lone_cell_grows_nothing(self):
        """No room for a fruit, so no stem -- even though the cell could be
        watered. This is the constraint that ``sum(no pairs) = x[CROP]`` buys."""
        layout = solve(".", Melon())
        assert layout.metrics.n_crop == 0

    def test_a_pair_of_cells_grows_nothing(self):
        """Two cells is a stem and a fruit -- and nowhere left for the water the
        stem needs. Melon's minimum viable farm is three cells, not two."""
        layout = solve("..", Melon())
        assert layout.metrics.n_crop == 0

    def test_three_in_a_row_is_the_smallest_farm(self):
        """Water, stem, fruit. Nothing smaller works."""
        layout = solve("...", Melon())
        assert layout.metrics.n_crop == 1
        assert_valid_melon(layout)

    def test_a_stem_needs_water_within_four(self):
        """Wheat's rule, unchanged. A strip long enough to outrun hydration
        cannot be planted end to end."""
        layout = solve("." * 20, Melon())
        assert_valid_melon(layout)
        for cell in layout.cells_with(BlockType.CROP):
            in_range = layout.grid.neighbors(cell, Neighborhood.DIAGONAL, 4)
            assert any(layout.block_at(n) is BlockType.WATER for n in in_range)

    def test_an_isolated_cell_cannot_be_planted(self):
        """Walled in on all four sides: watered by the rest of the field, but
        with nowhere to put a melon."""
        terrain = "\n".join(
            [
                ".....",
                ".#.#.",
                "..#..",
                ".#.#.",
                ".....",
            ]
        )
        # (2, 2) has four obstacle neighbours.
        layout = solve(terrain, Melon())
        assert layout.block_at(Cell(2, 2)) is not BlockType.CROP
        assert_valid_melon(layout)


class TestThePairingIsExclusive:
    """The reason melon is not an ``AdjacencyCropRule``.

    Every test here would pass on a model that only required "at least one
    adjacent empty cell", which is exactly why they are worth writing.
    """

    def test_stems_and_melons_come_in_equal_numbers(self, rectangle):
        layout = solve(rectangle(6, 6), Melon())
        assert len(layout.cells_with(BlockType.CROP)) == len(layout.cells_with(BlockType.MELON))

    def test_a_three_cell_line_grows_one_stem_not_two(self):
        """The case that separates the two models. Both end cells touch the
        middle, so a shared-fruit model would grow two stems on ``C.C`` and
        claim double the yield. One fruit block is one melon."""
        assert solve("...", Melon()).metrics.n_crop == 1

    def test_a_five_cell_line_grows_two_stems_not_three(self):
        """Same argument one size up, where the shared-fruit model would find
        three stems around two gaps."""
        assert solve(".....", Melon()).metrics.n_crop == 2

    def test_every_stem_can_be_given_its_own_melon(self, rectangle):
        """The validator runs a matching and demands it be perfect."""
        for height, width in ((3, 3), (4, 5), (6, 6)):
            assert_valid_melon(solve(rectangle(height, width), Melon()))

    def test_no_melon_serves_two_stems(self, rectangle):
        """Stated directly, as a counting argument over the whole layout: if
        every stem touches a melon and the two are equinumerous, a melon serving
        two stems would leave another melon serving none."""
        layout = solve(rectangle(5, 5), Melon())
        melons = set(layout.cells_with(BlockType.MELON))
        for stem in layout.cells_with(BlockType.CROP):
            assert any(n in melons for n in layout.grid.neighbors(stem)), (
                f"stem at {stem} touches no melon at all"
            )
        assert len(melons) == len(layout.cells_with(BlockType.CROP))


class TestAgainstTheOracle:
    """Against an independent brute force: every water set, then a matching."""

    @pytest.mark.parametrize(
        "terrain",
        [
            "...",
            ".....",
            "...\n...",
            "..\n..\n..",
            ".#.\n...\n.#.",
            "....\n....",
            "##..\n....\n..##",
        ],
    )
    def test_the_solver_finds_the_true_optimum(self, terrain):
        layout = solve(terrain, Melon())
        assert layout.metrics.n_crop == brute_force_melon_optimum(terrain)
        assert_valid_melon(layout)


class TestOpenGround:
    """The arithmetic of an unobstructed rectangle.

    ``2 * stems + water + unused = m * n`` is an identity, so these assert the
    stem count and derive the rest -- never the other way round. The water and
    unused counts are genuinely *not* determined at the optimum (see
    ``test_only_the_stem_count_is_determined``), so nothing here may lean on
    them.
    """

    @pytest.mark.parametrize(
        ("height", "width", "expected"),
        [
            (3, 3, 4),
            (4, 4, 7),
            (5, 5, 12),
            (8, 8, 31),
            (9, 9, 40),
            (10, 10, 49),
        ],
    )
    def test_known_optima(self, rectangle, height, width, expected):
        layout = solve(rectangle(height, width), Melon())
        assert layout.metrics.n_crop == expected
        assert layout.metrics.is_optimal
        assert_valid_melon(layout)

    def test_the_nine_by_nine_is_a_perfect_matching(self, rectangle):
        """The clean case, and the one the class docstring quotes.

        A 9x9 is 41 cells of one chessboard colour and 40 of the other. One
        water source sits on the odd cell out, leaving 40 and 40 -- a perfect
        matching, 40 stems, 40 melons, and not one cell wasted.
        """
        layout = solve(rectangle(9, 9), Melon())
        assert layout.metrics.n_crop == 40
        assert layout.metrics.n_support == 41  # 40 melons + 1 water
        assert layout.metrics.n_empty == 0

    def test_the_accounting_identity_holds(self, rectangle):
        """Every cell is a stem, its fruit, water, or wasted."""
        for height, width in ((4, 4), (5, 5), (7, 6), (9, 9)):
            layout = solve(rectangle(height, width), Melon())
            m = layout.metrics
            water = len(layout.cells_with(BlockType.WATER))
            assert 2 * m.n_crop + water + m.n_empty == height * width


class TestAgainstWheat:
    """Melon is wheat plus a fruit block, so wheat is the control."""

    def test_melon_runs_at_about_half_of_wheat(self, rectangle):
        """Same terrain, same hydration rule; the only difference is that a
        melon stem has to spend a second cell. On a 9x9 that is 80 against 40."""
        terrain = rectangle(9, 9)
        assert solve(terrain, Wheat()).metrics.n_crop == 80
        assert solve(terrain, Melon()).metrics.n_crop == 40

    def test_melon_never_beats_wheat(self, rectangle):
        """It cannot: any melon layout's stems are a legal wheat field."""
        for height, width in ((3, 3), (5, 5), (6, 7), (9, 9)):
            terrain = rectangle(height, width)
            assert solve(terrain, Melon()).metrics.n_crop <= solve(terrain, Wheat()).metrics.n_crop

    def test_melon_can_need_less_water_than_wheat(self, rectangle):
        """The claim in the module docstring, and the counter-intuitive one.

        Wheat must hydrate every cell it plants; melon only has to hydrate its
        stems, and the fruit -- half the field -- stands on plain dirt and wants
        nothing. So melon's covering problem is strictly easier, and on an 11x11
        it is strictly cheaper: four sources for wheat, three for melon.

        This is why melon must not borrow wheat's ``ceil(m/9) * ceil(n/9)``.
        """
        terrain = rectangle(11, 11)
        wheat_water = len(solve(terrain, Wheat()).cells_with(BlockType.WATER))
        melon_water = len(solve(terrain, Melon()).cells_with(BlockType.WATER))
        assert wheat_water == 4
        assert melon_water == 3


class TestObstacles:
    def test_obstacles_are_never_overwritten(self):
        terrain = "\n".join([".#....", "..#...", "....#.", "#....."])
        assert_valid_melon(solve(terrain, Melon()))

    def test_a_corridor_one_wide_still_grows(self):
        """A 1xN corridor is the tightest interesting shape: stem and fruit have
        to alternate along the line, so it grows about a third of its cells."""
        layout = solve("#######\n#.....#\n#######", Melon())
        assert layout.metrics.n_crop == 2
        assert_valid_melon(layout)

    def test_a_walled_single_cell_grows_nothing(self):
        layout = solve("###\n#.#\n###", Melon())
        assert layout.metrics.n_crop == 0

    def test_an_empty_terrain_is_not_an_error(self):
        assert solve("###\n###", Melon()).metrics.n_crop == 0


class TestTheCropInterface:
    """Melon implements ``CropRule`` by hand, so the protocol is worth pinning."""

    def test_it_satisfies_the_protocol(self):
        assert isinstance(Melon(), CropRule)

    def test_it_is_not_an_adjacency_crop(self):
        """A matching is not a count over a neighbourhood. If melon ever becomes
        an ``AdjacencyCropRule`` the pairing has been lost."""
        assert not isinstance(Melon(), AdjacencyCropRule)

    def test_it_places_water_stem_and_fruit(self):
        assert Melon().block_types() == frozenset(
            {BlockType.WATER, BlockType.CROP, BlockType.MELON}
        )

    def test_only_the_stem_counts_as_production(self):
        """Counting the fruit too would double every yield, since the pairing
        makes them equinumerous."""
        assert Melon().crop_blocks() == frozenset({BlockType.CROP})

    def test_the_melon_is_reported_as_support(self, rectangle):
        """It is a cell the stem spends, so it belongs with the water."""
        layout = solve(rectangle(5, 5), Melon())
        water = len(layout.cells_with(BlockType.WATER))
        melons = len(layout.cells_with(BlockType.MELON))
        assert layout.metrics.n_support == water + melons

    def test_the_name_is_melon(self):
        assert Melon().name == "melon"

    def test_hydration_matches_wheat(self):
        """Not "resembles" -- the same requirement object. If wheat's reach ever
        changes, melon's must move with it or this fails."""
        assert Melon().hydration() in WheatRule().requirements()


class TestOnlyTheStemCountIsDetermined:
    """The tie the module docstring warns about, asserted so it stays known."""

    def test_an_eight_by_eight_spends_its_spare_cells_either_way(self, rectangle):
        """64 cells, 31 stems, 31 melons, two cells left over. They may be one
        water and one unused cell, or two water -- both optimal, and the search
        returns whichever it reaches first. Only ``n_crop`` is safe to assert."""
        terrain = rectangle(8, 8)
        seen = set()
        for _ in range(8):
            layout = optimize(terrain, crop=Melon())
            assert layout.metrics.n_crop == 31
            water = len(layout.cells_with(BlockType.WATER))
            seen.add((water, layout.metrics.n_empty))
            assert water + layout.metrics.n_empty == 2
        assert seen <= {(1, 1), (2, 0)}
