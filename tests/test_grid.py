"""Grid parsing, geometry and neighbourhoods."""

from __future__ import annotations

import pytest

from mcfarm_opt import Cell, Grid, Neighborhood, parse_grid, render_grid


class TestParsing:
    def test_parses_shape_and_obstacles(self):
        grid = parse_grid(".#.\n...")
        assert grid.shape == (2, 3)
        assert len(grid) == 6
        assert grid.is_obstacle(Cell(0, 1))
        assert not grid.is_obstacle(Cell(0, 0))
        assert list(grid.obstacles()) == [Cell(0, 1)]
        assert len(list(grid.free_cells())) == 5

    def test_ignores_blank_lines_and_trailing_space(self):
        assert parse_grid("\n\n..  \n..\n\n") == parse_grid("..\n..")

    def test_empty_text_is_empty_grid(self):
        grid = parse_grid("   \n\n")
        assert grid.shape == (0, 0)
        assert list(grid.cells()) == []

    def test_ragged_rows_rejected(self):
        with pytest.raises(ValueError, match="rectangular"):
            parse_grid("...\n..")

    def test_unknown_character_rejected(self):
        with pytest.raises(ValueError, match="unknown terrain character"):
            parse_grid(".W.\n...")

    def test_round_trips_through_render(self):
        text = ".#.#.\n.....\n#...#"
        assert render_grid(parse_grid(text)) == text

    def test_grid_equality_and_hash(self):
        assert parse_grid(".#\n..") == parse_grid(".#\n..")
        assert parse_grid(".#\n..") != parse_grid("..\n..")
        assert len({parse_grid(".#\n.."), parse_grid(".#\n..")}) == 1


class TestConstruction:
    def test_negative_dimensions_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            Grid(height=-1, width=3)

    def test_out_of_bounds_obstacle_rejected(self):
        with pytest.raises(ValueError, match="outside"):
            Grid(height=2, width=2, blocked=frozenset({Cell(5, 5)}))

    def test_cell_outside_grid_is_not_an_obstacle(self):
        grid = parse_grid("..\n..")
        assert not grid.contains(Cell(9, 9))
        assert not grid.is_obstacle(Cell(9, 9))
        assert not grid.is_free(Cell(9, 9))


class TestNeighbors:
    def test_orthogonal_radius_1_is_the_four_sides(self):
        grid = parse_grid("...\n...\n...")
        assert grid.neighbors(Cell(1, 1)) == [Cell(0, 1), Cell(1, 0), Cell(1, 2), Cell(2, 1)]

    def test_diagonal_radius_1_is_the_eight_surrounding(self):
        grid = parse_grid("...\n...\n...")
        found = grid.neighbors(Cell(1, 1), Neighborhood.DIAGONAL)
        assert len(found) == 8
        assert Cell(0, 0) in found and Cell(2, 2) in found
        assert Cell(1, 1) not in found

    def test_neighborhood_is_clipped_to_the_border(self):
        grid = parse_grid("...\n...\n...")
        assert grid.neighbors(Cell(0, 0)) == [Cell(0, 1), Cell(1, 0)]

    def test_centre_cell_is_never_its_own_neighbor(self):
        grid = parse_grid("...\n...\n...")
        for neighborhood in Neighborhood:
            for radius in (1, 2, 5):
                assert Cell(1, 1) not in grid.neighbors(Cell(1, 1), neighborhood, radius)

    def test_orthogonal_radius_is_manhattan_distance(self):
        grid = parse_grid("\n".join(["....."] * 5))
        found = grid.neighbors(Cell(2, 2), Neighborhood.ORTHOGONAL, radius=2)
        assert Cell(0, 2) in found  # distance 2
        assert Cell(1, 1) in found  # distance 2
        assert Cell(0, 0) not in found  # distance 4

    def test_diagonal_radius_is_chebyshev_distance(self):
        grid = parse_grid("\n".join(["....."] * 5))
        found = grid.neighbors(Cell(2, 2), Neighborhood.DIAGONAL, radius=2)
        assert len(found) == 24  # the whole 5x5 minus the centre
        assert Cell(0, 0) in found  # Chebyshev distance 2

    def test_wheat_sized_radius_covers_the_9x9_hydration_square(self):
        grid = parse_grid("\n".join(["." * 9] * 9))
        found = grid.neighbors(Cell(4, 4), Neighborhood.DIAGONAL, radius=4)
        assert len(found) == 80

    def test_obstacles_can_be_excluded(self):
        grid = parse_grid(".#.\n...\n...")
        assert Cell(0, 1) in grid.neighbors(Cell(1, 1))
        assert Cell(0, 1) not in grid.neighbors(Cell(1, 1), include_obstacles=False)

    def test_neighbors_are_row_major_and_deterministic(self):
        grid = parse_grid("\n".join(["....."] * 5))
        found = grid.neighbors(Cell(2, 2), Neighborhood.DIAGONAL, radius=2)
        assert found == sorted(found)

    def test_negative_radius_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            parse_grid("..\n..").neighbors(Cell(0, 0), radius=-1)

    def test_metric_distances(self):
        a, b = Cell(0, 0), Cell(2, 3)
        assert Neighborhood.ORTHOGONAL.distance(a, b) == 5
        assert Neighborhood.DIAGONAL.distance(a, b) == 3
