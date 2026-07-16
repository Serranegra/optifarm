"""The decision variables shared between the solver and the crop rules.

Mathematical model
------------------

The layout problem is modelled as a *one-hot assignment* problem. For every
cell ``p`` of the grid and every block type ``b`` the crop is allowed to use,
there is a boolean variable

.. math:: x_{p,b} \\in \\{0, 1\\}

meaning "cell *p* holds block *b*". Exactly one block occupies each cell:

.. math:: \\sum_{b} x_{p,b} = 1 \\quad \\forall p

Obstacles are not decisions -- they are data. An obstacle cell has
``x[p, OBSTACLE]`` fixed to 1 and every other variable fixed to 0; a free cell
has ``x[p, OBSTACLE]`` fixed to 0. Fixing rather than omitting the variables is
what lets a crop rule write "no solid block orthogonally adjacent" as one
uniform sum, without special-casing the grid border or obstacles.

This module owns *only* the variables and the one-hot constraint. Which blocks
exist, and what makes a cell plantable, come from the
:class:`~mcfarm_opt.crops.base.CropRule`; the objective comes from it too. That
split is what keeps the core crop-agnostic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from ortools.sat.python import cp_model

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Cell, Grid

__all__ = ["CellVars"]


class CellVars:
    """The ``x[cell, block]`` boolean variables of one layout model.

    Instances are built by the solver and handed to the crop rule. A rule
    should treat them as read-only lookups -- it adds *constraints over* these
    variables, it never creates the variables itself.
    """

    __slots__ = ("_blocks", "_grid", "_model", "_vars")

    def __init__(self, model: cp_model.CpModel, grid: Grid, blocks: Iterable[BlockType]) -> None:
        """Create one variable per (cell, block) pair and tie down the obstacles.

        Args:
            model: the CP-SAT model to add the variables to.
            grid: the terrain being solved.
            blocks: the block types the crop may place. ``EMPTY`` and
                ``OBSTACLE`` are added automatically if absent.
        """
        self._model = model
        self._grid = grid
        self._blocks = frozenset(blocks) | {BlockType.EMPTY, BlockType.OBSTACLE}

        self._vars: dict[tuple[Cell, BlockType], cp_model.IntVar] = {}
        for cell in grid.cells():
            for block in sorted(self._blocks, key=lambda b: b.name):
                self._vars[cell, block] = model.NewBoolVar(f"x[{cell.row},{cell.col},{block.name}]")

        for cell in grid.cells():
            obstacle = grid.is_obstacle(cell)
            # An obstacle is OBSTACLE and nothing else; a free cell is never
            # OBSTACLE. Both are facts about the terrain, not choices.
            model.Add(self._vars[cell, BlockType.OBSTACLE] == int(obstacle))
            if obstacle:
                for block in self._blocks:
                    if block is not BlockType.OBSTACLE:
                        model.Add(self._vars[cell, block] == 0)
            # One block per cell.
            model.AddExactlyOne(self._vars[cell, block] for block in self._blocks)

    @property
    def blocks(self) -> frozenset[BlockType]:
        """The block types this model can assign, including EMPTY and OBSTACLE."""
        return self._blocks

    @property
    def grid(self) -> Grid:
        """The terrain these variables describe."""
        return self._grid

    def var(self, cell: Cell, block: BlockType) -> cp_model.IntVar:
        """Return the boolean variable "``cell`` holds ``block``".

        Raises:
            KeyError: if ``cell`` is out of bounds, or ``block`` is not one of
                the types this crop declared.
        """
        try:
            return self._vars[cell, block]
        except KeyError:
            if not self._grid.contains(cell):
                raise KeyError(f"cell {cell} is outside the grid") from None
            raise KeyError(
                f"block {block.name} is not used by this crop "
                f"(available: {sorted(b.name for b in self._blocks)})"
            ) from None

    def count(self, cells: Sequence[Cell], blocks: Iterable[BlockType]) -> cp_model.LinearExpr:
        """Return the linear expression counting how many of ``cells`` hold any of ``blocks``.

        Out-of-bounds cells contribute nothing, so a rule can pass a raw
        neighbourhood without clipping it to the border first. Block types the
        crop does not use also contribute nothing: if a crop never places sand,
        "how many neighbours are sand" is identically zero, which is the
        mathematically correct answer rather than an error.

        This is the workhorse for adjacency requirements of every sign:
        ``count(...) >= 1`` is mandatory support, ``count(...) == 0`` is a
        forbidden neighbour, and the ``cells`` argument carries the radius.
        """
        wanted = [b for b in blocks if b in self._blocks]
        terms = [
            self._vars[cell, block]
            for cell in cells
            if self._grid.contains(cell)
            for block in wanted
        ]
        if not terms:
            return cp_model.LinearExpr.Sum([])
        return cp_model.LinearExpr.Sum(terms)

    def extract(self, solver: cp_model.CpSolver) -> Mapping[Cell, BlockType]:
        """Read the block assigned to each cell out of a solved model.

        Raises:
            RuntimeError: if a cell has no block set, which would mean the
                one-hot constraint was violated -- a bug in this library.
        """
        assignment: dict[Cell, BlockType] = {}
        for cell in self._grid.cells():
            for block in self._blocks:
                if solver.Value(self._vars[cell, block]):
                    assignment[cell] = block
                    break
            else:  # pragma: no cover - guarded by AddExactlyOne
                raise RuntimeError(f"no block assigned to {cell}; one-hot constraint broken")
        return assignment
