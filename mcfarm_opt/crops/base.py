"""The crop interface, and a declarative helper for adjacency-based crops.

Two layers live here.

:class:`CropRule` is the interface proper. It is deliberately low-level: a crop
receives the CP-SAT model, the variables and the grid, and may add whatever
constraints it likes. Anything expressible in CP-SAT is expressible as a crop,
which is the escape hatch for rules that no declarative scheme anticipated
(mushrooms and their light level, melons and their stem-to-fruit pairing).

:class:`AdjacencyCropRule` is the convenience layer on top, for the large family
of crops whose rule is "this cell may hold crop iff its neighbourhood contains
(or avoids) certain blocks". Such a crop declares a list of
:class:`AdjacencyRequirement` and writes no CP-SAT at all.

Modelling plantability
----------------------

Every requirement is *conditional on the cell actually holding the crop*. The
constraint is not "every cell has water next to it" -- it is

.. math:: x_{p,\\mathrm{CROP}} = 1 \\;\\Rightarrow\\; \\sum_{q \\in N(p)} x_{q,b} \\ge 1

which CP-SAT expresses natively via ``OnlyEnforceIf`` (a reified linear
constraint), so cells that stay EMPTY are left unconstrained. Writing it as an
implication rather than a hard constraint is what makes the model a *choice* of
where to farm rather than a demand that the whole terrain be farmable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ortools.sat.python import cp_model

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Cell, Grid, Neighborhood
from mcfarm_opt.core.variables import CellVars

__all__ = ["AdjacencyCropRule", "AdjacencyRequirement", "CropRule", "ObjectiveTerm"]


@dataclass(frozen=True, slots=True)
class ObjectiveTerm:
    """One weighted variable in the objective function.

    The solver maximises ``sum(weight * var)`` over the terms every crop
    returns. A weight may be negative -- that is how a future crop would say
    "water is cheap but not free", or trade a support block off against yield.
    """

    var: cp_model.IntVar
    weight: int = 1


@runtime_checkable
class CropRule(Protocol):
    """What every crop must provide.

    Implementations are expected to be stateless and cheap to construct; the
    solver may build the same rule into several models.
    """

    @property
    def name(self) -> str:
        """Human-readable crop name, used in rendering and metrics."""
        ...

    def block_types(self) -> frozenset[BlockType]:
        """The blocks this crop places: its support blocks plus its crop block.

        ``EMPTY`` and ``OBSTACLE`` are supplied by the solver and need not be
        listed. Blocks omitted here simply never appear in the layout, and any
        rule counting them counts zero.
        """
        ...

    def crop_blocks(self) -> frozenset[BlockType]:
        """The subset of :meth:`block_types` that counts as production.

        Used for metrics. The objective is defined separately by
        :meth:`objective_terms`, so a crop may count blocks it does not
        maximise, or maximise blocks it does not count.
        """
        ...

    def add_constraints(self, model: cp_model.CpModel, variables: CellVars, grid: Grid) -> None:
        """Add this crop's placement rules to ``model``.

        The one-hot "exactly one block per cell" constraint and the obstacle
        fixing are already in the model; this method adds only what makes the
        crop *this* crop.
        """
        ...

    def objective_terms(
        self, model: cp_model.CpModel, variables: CellVars, grid: Grid
    ) -> Sequence[ObjectiveTerm]:
        """The terms the solver should maximise.

        ``model`` is passed so a crop may introduce auxiliary variables (a
        "this row is fully harvestable" bonus, say) and return them here.
        """
        ...


@dataclass(frozen=True, slots=True)
class AdjacencyRequirement:
    """A bound on how many nearby cells hold one of a set of blocks.

    This single shape covers the three kinds of rule the crops in this library
    need, because sign and distance are both parameters rather than assumptions:

    * **positive, mandatory** -- sugarcane needs at least one orthogonally
      adjacent water:
      ``AdjacencyRequirement({WATER}, minimum=1)``
    * **negative** -- cactus tolerates no solid block orthogonally adjacent:
      ``AdjacencyRequirement({SAND, CROP, OBSTACLE}, maximum=0)``
    * **by radius** -- wheat wants water within 4 cells, diagonals included:
      ``AdjacencyRequirement({WATER}, Neighborhood.DIAGONAL, radius=4, minimum=1)``

    Attributes:
        blocks: the blocks being counted. Any one of them satisfies the count,
            so a set is how you say "any solid block".
        neighborhood: the metric defining the shape of the neighbourhood.
        radius: how far the requirement reaches, in that metric.
        minimum: the count must be at least this. ``None`` means no lower bound.
        maximum: the count must be at most this. ``None`` means no upper bound.
        include_obstacles: whether obstacle cells are counted. Defaults to
            ``True``: obstacles cannot hold water, so a positive requirement is
            unaffected, while a negative one *must* see them -- an obstacle is
            a solid block, and cactus cares.

    Raises:
        ValueError: on a requirement that is empty, negative, or unsatisfiable.
    """

    blocks: frozenset[BlockType]
    neighborhood: Neighborhood = Neighborhood.ORTHOGONAL
    radius: int = 1
    minimum: int | None = None
    maximum: int | None = None
    include_obstacles: bool = True

    def __post_init__(self) -> None:
        if not self.blocks:
            raise ValueError("an adjacency requirement must name at least one block")
        if self.radius < 1:
            raise ValueError(f"radius must be at least 1, got {self.radius}")
        if self.minimum is None and self.maximum is None:
            raise ValueError("an adjacency requirement needs a minimum, a maximum, or both")
        if self.minimum is not None and self.minimum < 0:
            raise ValueError(f"minimum must be non-negative, got {self.minimum}")
        if self.maximum is not None and self.maximum < 0:
            raise ValueError(f"maximum must be non-negative, got {self.maximum}")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(
                f"unsatisfiable requirement: minimum {self.minimum} > maximum {self.maximum}"
            )

    def apply(
        self,
        model: cp_model.CpModel,
        variables: CellVars,
        grid: Grid,
        cell: Cell,
        enforce_if: cp_model.IntVar,
    ) -> None:
        """Enforce this requirement on ``cell``, but only when ``enforce_if`` is true.

        Args:
            model: the model to constrain.
            variables: the layout variables.
            grid: the terrain.
            cell: the cell whose neighbourhood is counted.
            enforce_if: the literal gating the constraint, normally
                ``x[cell, CROP]``.
        """
        neighbors = grid.neighbors(
            cell,
            self.neighborhood,
            self.radius,
            include_obstacles=self.include_obstacles,
        )
        total = variables.count(neighbors, self.blocks)
        if self.minimum is not None:
            model.Add(total >= self.minimum).OnlyEnforceIf(enforce_if)
        if self.maximum is not None:
            model.Add(total <= self.maximum).OnlyEnforceIf(enforce_if)


class AdjacencyCropRule(ABC):
    """Base class for crops defined purely by neighbourhood requirements.

    A subclass declares :attr:`name`, the blocks it uses, and its
    :meth:`requirements`; this class turns those into CP-SAT constraints and a
    "maximise the crop count" objective. Subclasses that need more (an
    auxiliary variable, a global limit on water) can still override
    :meth:`add_constraints` and call ``super()``.

    The class satisfies :class:`CropRule` structurally, so it is an
    implementation convenience rather than a required base -- a crop is free to
    implement the protocol directly.
    """

    #: The block the objective counts. Subclasses may override.
    crop_block: BlockType = BlockType.CROP

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable crop name."""

    @abstractmethod
    def support_blocks(self) -> frozenset[BlockType]:
        """The non-crop blocks this crop may place, e.g. water or farmland."""

    @abstractmethod
    def requirements(self) -> Sequence[AdjacencyRequirement]:
        """The conditions a cell must meet to hold the crop.

        All requirements must hold simultaneously (they are conjunctive). An
        empty sequence means the crop grows anywhere, which is legal.
        """

    def block_types(self) -> frozenset[BlockType]:
        """The support blocks plus the crop block."""
        return self.support_blocks() | {self.crop_block}

    def crop_blocks(self) -> frozenset[BlockType]:
        """Just the crop block -- support does not count as production."""
        return frozenset({self.crop_block})

    def add_constraints(self, model: cp_model.CpModel, variables: CellVars, grid: Grid) -> None:
        """Apply every requirement to every free cell, gated on the crop being there.

        Obstacle cells are skipped: their variables are already fixed, so
        constraining them would be redundant at best and, for a ``maximum=0``
        requirement, wrong -- an obstacle next to an obstacle is terrain, not a
        violated rule.
        """
        requirements = self.requirements()
        for cell in grid.free_cells():
            planted = variables.var(cell, self.crop_block)
            for requirement in requirements:
                requirement.apply(model, variables, grid, cell, planted)

    def objective_terms(
        self, model: cp_model.CpModel, variables: CellVars, grid: Grid
    ) -> Sequence[ObjectiveTerm]:
        """Maximise the number of cells holding the crop, each worth 1."""
        return [
            ObjectiveTerm(variables.var(cell, self.crop_block), 1) for cell in grid.free_cells()
        ]

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"{type(self).__name__}()"
