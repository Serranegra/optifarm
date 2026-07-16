"""The public API: optimize(), metrics, and the error messages."""

from __future__ import annotations

import pytest

from mcfarm_opt import (
    BlockType,
    Cell,
    FarmMetrics,
    Grid,
    ILPSolver,
    SolveStatus,
    Sugarcane,
    optimize,
)


class TestOptimizeSignature:
    def test_accepts_a_terrain_string(self, rectangle):
        assert optimize(rectangle(3, 3), crop=Sugarcane(), solver="ilp").metrics.n_crop == 6

    def test_accepts_a_prebuilt_grid(self, rectangle):
        grid = Grid.from_text(rectangle(3, 3))
        assert optimize(grid, crop=Sugarcane()).metrics.n_crop == 6

    def test_crop_defaults_to_sugarcane(self, rectangle):
        assert optimize(rectangle(3, 3)).crop_name == "sugarcane"

    def test_solver_defaults_to_ilp(self, rectangle):
        assert optimize(rectangle(3, 3)).metrics.is_optimal

    def test_accepts_a_configured_solver_instance(self, rectangle):
        layout = optimize(rectangle(4, 4), crop=Sugarcane(), solver=ILPSolver(workers=1))
        assert layout.metrics.n_crop == 12

    def test_unknown_solver_name_rejected(self, rectangle):
        with pytest.raises(ValueError, match="unknown solver"):
            optimize(rectangle(3, 3), crop=Sugarcane(), solver="annealing")

    def test_malformed_terrain_rejected(self):
        with pytest.raises(ValueError, match="rectangular"):
            optimize("...\n..", crop=Sugarcane())

    def test_layout_keeps_the_grid_and_crop_name(self, rectangle):
        layout = optimize(rectangle(3, 3), crop=Sugarcane())
        assert layout.grid.shape == (3, 3)
        assert layout.crop_name == "sugarcane"

    def test_nonpositive_time_limit_rejected(self, rectangle):
        with pytest.raises(ValueError, match="time_limit must be positive"):
            optimize(rectangle(3, 3), crop=Sugarcane(), time_limit=0)

    def test_worker_count_must_be_positive(self):
        with pytest.raises(ValueError, match="workers must be at least 1"):
            ILPSolver(workers=0)

    def test_solver_is_deterministic_with_one_worker(self, rectangle):
        renders = {
            optimize(rectangle(5, 5), crop=Sugarcane(), solver=ILPSolver(workers=1)).render()
            for _ in range(3)
        }
        assert len(renders) == 1


class TestMetrics:
    def test_counts_partition_the_grid(self):
        m = optimize("...##\n...##\n.....", crop=Sugarcane()).metrics
        assert m.n_crop + m.n_support + m.n_empty == m.n_free
        assert m.n_free + m.n_obstacle == m.n_cells == 15

    def test_efficiency_is_crop_over_free_terrain(self):
        m = FarmMetrics(
            n_crop=12, n_support=4, n_empty=4, n_obstacle=80, solve_time=0.0,
            status=SolveStatus.OPTIMAL,
        )
        assert m.n_free == 20
        assert m.efficiency == pytest.approx(60.0)

    def test_efficiency_of_a_terrain_with_no_free_cells_is_zero(self):
        assert optimize("###\n###", crop=Sugarcane()).metrics.efficiency == 0.0

    def test_is_optimal_tracks_status(self):
        def metrics(status):
            return FarmMetrics(0, 0, 0, 0, 0.0, status)

        assert metrics(SolveStatus.OPTIMAL).is_optimal
        assert not metrics(SolveStatus.FEASIBLE).is_optimal
        assert metrics(SolveStatus.FEASIBLE).status.is_solved
        assert not metrics(SolveStatus.INFEASIBLE).status.is_solved

    def test_str_is_readable(self, rectangle):
        text = str(optimize(rectangle(3, 3), crop=Sugarcane()).metrics)
        assert "crop=6" in text and "efficiency=" in text and "status=optimal" in text


class TestLayoutAccessors:
    def test_block_at_and_cells_with_agree(self, rectangle):
        layout = optimize(rectangle(4, 4), crop=Sugarcane())
        water = layout.cells_with(BlockType.WATER)
        assert all(layout.block_at(cell) is BlockType.WATER for cell in water)
        assert len(water) == layout.metrics.n_support

    def test_cells_with_is_row_major(self, rectangle):
        layout = optimize(rectangle(5, 5), crop=Sugarcane())
        crops = layout.cells_with(BlockType.CROP)
        assert crops == sorted(crops)

    def test_block_at_outside_the_grid_raises(self, rectangle):
        with pytest.raises(KeyError, match="not part of this"):
            optimize(rectangle(2, 2), crop=Sugarcane()).block_at(Cell(9, 9))


class TestBlockType:
    def test_symbols_are_unique(self):
        symbols = [block.symbol for block in BlockType]
        assert len(symbols) == len(set(symbols))

    def test_symbol_round_trip(self):
        for block in BlockType:
            assert BlockType.from_symbol(block.symbol) is block

    def test_unknown_symbol_rejected(self):
        with pytest.raises(ValueError, match="no block type with symbol"):
            BlockType.from_symbol("Z")

    def test_water_and_empty_are_not_solid(self):
        assert not BlockType.WATER.is_solid
        assert not BlockType.EMPTY.is_solid
        assert BlockType.OBSTACLE.is_solid
        assert BlockType.SAND.is_solid
