"""The CropRule interface must express more than sugarcane.

The whole point of the architecture is that a new crop is a new rule and
nothing else -- no edits to the grid, the variables or the solver. These tests
define throwaway crops covering the shapes named in the design, and assert the
existing machinery solves them.

The crops here are test fixtures, not shipped features: they exercise the
interface rather than modelling anything real.

Two rules have graduated out of this file. Negative adjacency belongs to
:class:`~mcfarm_opt.crops.cactus.Cactus` and radius adjacency to
:class:`~mcfarm_opt.crops.wheat.Wheat`; both ship, both are tested in their own
files, so the fixtures that used to stand in for them are gone rather than left
here restating the same rule a second time. What remains is deliberately what no
shipped crop does: a reach nothing in Minecraft uses, conjunctive requirements,
and a hand-written global constraint. If a fixture here ever becomes a copy of a
shipped crop, delete it -- a duplicate model is a model that can disagree with
itself.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from ortools.sat.python import cp_model

from mcfarm_opt import (
    AdjacencyCropRule,
    AdjacencyRequirement,
    BlockType,
    CellVars,
    CropRule,
    Grid,
    Neighborhood,
    ObjectiveTerm,
    optimize,
)


class FarReachingCrop(AdjacencyCropRule):
    """RADIUS adjacency, at a reach no shipped crop uses.

    Water within 7 in every direction -- a 15x15 hydration square. Nothing in
    Minecraft works this way; the point is that the radius is a *parameter*, so
    a crop can pick any reach without the core knowing. Wheat's real radius-4
    rule ships in ``crops/wheat.py`` and is tested in ``test_wheat.py``.
    """

    @property
    def name(self) -> str:
        return "far-reaching"

    def support_blocks(self) -> frozenset[BlockType]:
        return frozenset({BlockType.WATER})

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        return (
            AdjacencyRequirement(
                blocks=frozenset({BlockType.WATER}),
                neighborhood=Neighborhood.DIAGONAL,
                radius=7,
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


class TestRadiusAdjacency:
    """The radius is a parameter, and a user-defined crop can set it freely."""

    def test_one_water_covers_the_whole_15x15(self):
        """Radius 7 means a 15x15 square: one source, 224 crops."""
        layout = optimize("\n".join(["." * 15] * 15), crop=FarReachingCrop())
        assert layout.metrics.n_crop == 224
        assert layout.metrics.n_support == 1
        assert layout.metrics.is_optimal

    def test_range_is_finite(self):
        """A 17x17 needs more: its corners sit outside any single 15x15."""
        layout = optimize("\n".join(["." * 17] * 17), crop=FarReachingCrop())
        assert layout.metrics.n_support >= 2

    def test_a_longer_reach_beats_a_shorter_one(self, rectangle):
        """Radius 7 against wheat's shipped radius 4, on the same ground."""
        from mcfarm_opt import Wheat

        terrain = rectangle(15, 15)
        assert (
            optimize(terrain, crop=FarReachingCrop()).metrics.n_crop
            > optimize(terrain, crop=Wheat()).metrics.n_crop
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
        """Shipped crops and user-defined ones satisfy the same protocol."""
        from mcfarm_opt import Cactus, Sugarcane, Wheat

        assert isinstance(Sugarcane(), CropRule)
        assert isinstance(Cactus(), CropRule)
        assert isinstance(Wheat(), CropRule)
        assert isinstance(FarReachingCrop(), CropRule)
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
        """FarReachingCrop never places sand, so 'sand nearby' is vacuously zero.

        Every cell of a 2x3 is within radius 7 of every other, so the only cost
        is the one water block the rule insists on: 5 crops, not 6.
        """
        layout = optimize("...\n...", crop=FarReachingCrop())
        assert layout.metrics.n_crop == 5
        assert layout.metrics.n_support == 1
