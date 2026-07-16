"""The CropRule interface must express more than sugarcane.

The whole point of the architecture is that a new crop is a new rule and
nothing else -- no edits to the grid, the variables or the solver. These tests
define throwaway crops covering the three shapes named in the design, and
assert the existing machinery solves them.

The crops here are test fixtures, not shipped features: they exercise the
interface, they are not the real cactus/wheat/mushroom models.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from ortools.sat.python import cp_model

from mcfarm_opt import (
    AdjacencyCropRule,
    AdjacencyRequirement,
    BlockType,
    Cell,
    CellVars,
    CropRule,
    Grid,
    Neighborhood,
    ObjectiveTerm,
    optimize,
)


class FakeCactus(AdjacencyCropRule):
    """NEGATIVE adjacency: cactus breaks if any solid block orthogonally touches it."""

    @property
    def name(self) -> str:
        return "fake-cactus"

    def support_blocks(self) -> frozenset[BlockType]:
        return frozenset({BlockType.SAND})

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        return (
            AdjacencyRequirement(
                blocks=frozenset({BlockType.SAND, BlockType.CROP, BlockType.OBSTACLE}),
                neighborhood=Neighborhood.ORTHOGONAL,
                radius=1,
                maximum=0,
            ),
        )


class FakeWheat(AdjacencyCropRule):
    """RADIUS adjacency: wheat wants water within 4 cells, diagonals included."""

    @property
    def name(self) -> str:
        return "fake-wheat"

    def support_blocks(self) -> frozenset[BlockType]:
        return frozenset({BlockType.WATER})

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        return (
            AdjacencyRequirement(
                blocks=frozenset({BlockType.WATER}),
                neighborhood=Neighborhood.DIAGONAL,
                radius=4,
                minimum=1,
            ),
        )


class FakeCombo(AdjacencyCropRule):
    """Conjunctive requirements: needs water near, tolerates no obstacle adjacent."""

    @property
    def name(self) -> str:
        return "fake-combo"

    def support_blocks(self) -> frozenset[BlockType]:
        return frozenset({BlockType.WATER})

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        return (
            AdjacencyRequirement(frozenset({BlockType.WATER}), minimum=1),
            AdjacencyRequirement(frozenset({BlockType.OBSTACLE}), maximum=0),
        )


class HandWrittenCrop:
    """A crop bypassing the declarative layer, implementing CropRule directly.

    Grows anywhere, but caps the total at 3 -- a global constraint that no
    per-cell adjacency rule could express. This is the escape hatch working.
    """

    @property
    def name(self) -> str:
        return "capped"

    def block_types(self) -> frozenset[BlockType]:
        return frozenset({BlockType.CROP})

    def crop_blocks(self) -> frozenset[BlockType]:
        return frozenset({BlockType.CROP})

    def add_constraints(self, model: cp_model.CpModel, variables: CellVars, grid: Grid) -> None:
        planted = [variables.var(cell, BlockType.CROP) for cell in grid.free_cells()]
        model.Add(sum(planted) <= 3)

    def objective_terms(
        self, model: cp_model.CpModel, variables: CellVars, grid: Grid
    ) -> Sequence[ObjectiveTerm]:
        return [ObjectiveTerm(variables.var(cell, BlockType.CROP), 1) for cell in grid.free_cells()]


class TestNegativeAdjacency:
    def test_cactus_never_touches_a_solid(self):
        layout = optimize("\n".join(["....."] * 5), crop=FakeCactus())
        for cell in layout.grid.cells():
            if layout.block_at(cell) is BlockType.CROP:
                for neighbor in layout.grid.neighbors(cell):
                    assert not layout.block_at(neighbor).is_solid, (
                        f"cactus at {cell} touches a solid at {neighbor}"
                    )

    def test_cactus_on_open_ground_is_a_checkerboard(self):
        """No two cacti orthogonally adjacent on a 5x5 means the 13-cell colour."""
        layout = optimize("\n".join(["....."] * 5), crop=FakeCactus())
        assert layout.metrics.n_crop == 13
        assert layout.metrics.is_optimal

    def test_cactus_avoids_obstacles_too(self):
        """An obstacle is a solid, so the cells around it must stay bare.

        This is the case that would silently break if obstacles were left out
        of the neighbourhood count rather than fixed to OBSTACLE.
        """
        layout = optimize(".....\n.....\n..#..\n.....\n.....", crop=FakeCactus())
        for neighbor in layout.grid.neighbors(Cell(2, 2)):
            assert layout.block_at(neighbor) is not BlockType.CROP


class TestRadiusAdjacency:
    def test_one_water_hydrates_the_whole_9x9(self):
        """A 9x9 with water at the centre: 80 wheat off a single water block."""
        layout = optimize("\n".join(["." * 9] * 9), crop=FakeWheat())
        assert layout.metrics.n_crop == 80
        assert layout.metrics.n_support == 1
        assert layout.metrics.is_optimal

    def test_range_is_finite(self):
        """An 11x11 needs a second water: the corners sit outside any single 9x9."""
        layout = optimize("\n".join(["." * 11] * 11), crop=FakeWheat())
        assert layout.metrics.n_support >= 2

    def test_wheat_reaches_further_than_sugarcane(self, rectangle):
        from mcfarm_opt import Sugarcane

        terrain = rectangle(9, 9)
        assert (
            optimize(terrain, crop=FakeWheat()).metrics.n_crop
            > optimize(terrain, crop=Sugarcane()).metrics.n_crop
        )


class TestConjunctiveRequirements:
    def test_all_requirements_hold_at_once(self):
        layout = optimize(".....\n..#..\n.....", crop=FakeCombo())
        for cell in layout.grid.cells():
            if layout.block_at(cell) is BlockType.CROP:
                neighbors = layout.grid.neighbors(cell)
                assert any(layout.block_at(n) is BlockType.WATER for n in neighbors)
                assert all(layout.block_at(n) is not BlockType.OBSTACLE for n in neighbors)


class TestRawInterface:
    def test_hand_written_crop_with_a_global_constraint(self):
        layout = optimize("\n".join(["....."] * 5), crop=HandWrittenCrop())
        assert layout.metrics.n_crop == 3
        assert layout.metrics.is_optimal

    def test_protocol_is_satisfied_structurally(self):
        from mcfarm_opt import Sugarcane

        assert isinstance(Sugarcane(), CropRule)
        assert isinstance(FakeCactus(), CropRule)
        assert isinstance(HandWrittenCrop(), CropRule)


class TestRequirementValidation:
    def test_requirement_needs_a_block(self):
        with pytest.raises(ValueError, match="at least one block"):
            AdjacencyRequirement(frozenset(), minimum=1)

    def test_requirement_needs_a_bound(self):
        with pytest.raises(ValueError, match="minimum, a maximum, or both"):
            AdjacencyRequirement(frozenset({BlockType.WATER}))

    def test_radius_must_be_positive(self):
        with pytest.raises(ValueError, match="radius must be at least 1"):
            AdjacencyRequirement(frozenset({BlockType.WATER}), radius=0, minimum=1)

    def test_contradictory_bounds_rejected(self):
        with pytest.raises(ValueError, match="unsatisfiable"):
            AdjacencyRequirement(frozenset({BlockType.WATER}), minimum=3, maximum=1)

    def test_counting_a_block_the_crop_never_places_is_zero_not_an_error(self):
        """FakeWheat never places sand, so 'sand nearby' is vacuously zero.

        Every cell of a 2x3 is within radius 4 of every other, so the only cost
        is the one water block the rule insists on: 5 wheat, not 6.
        """
        layout = optimize("...\n...", crop=FakeWheat())
        assert layout.metrics.n_crop == 5
        assert layout.metrics.n_support == 1
