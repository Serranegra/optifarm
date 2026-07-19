"""Melon: the crop that needs somewhere to *put* its fruit.

The rule
--------

A melon stem is planted on hydrated farmland, exactly like wheat, and grows its
fruit onto an **adjacent free block of dirt or grass**. So a cell may hold a
stem iff

* it has water within 4 blocks in every direction -- Chebyshev distance, the
  same 9x9 hydration square as :mod:`~mcfarm_opt.crops.wheat`; and
* it can be given an orthogonally adjacent cell, free of obstacles, to grow the
  melon onto.

The second condition is the whole of what makes melon a different problem, and
it is worth being precise about what "given" means.

Why the fruit is a block and not an adjacency rule
--------------------------------------------------

Sugarcane's sand and wheat's farmland sit *under* the crop, inside the same cell
of this top-down projection, so they are never neighbours and never need
modelling. A melon does not: the fruit lands in the cell *next door*, and while
it sits there nothing else may use that cell. It is the first block in this
library that a crop places beside itself, which is why
:data:`~mcfarm_opt.core.blocks.BlockType.MELON` exists at all.

That in turn is why the obvious rule is wrong. Written as an adjacency
requirement -- "at least one adjacent empty cell" -- two stems either side of a
single gap would both count, and the layout would claim a yield the farm cannot
sustain: one fruit block grows one melon, and until it is harvested the other
stem is stuck. Yield is not the number of stems that *could* fruit, it is the
number that can fruit *at once*.

So the model pairs them explicitly. Every stem is assigned one fruit block, and
every fruit block serves one stem -- a **matching** between stems and their
adjacent cells. That is not a count over a neighbourhood, so it is not an
:class:`~mcfarm_opt.crops.base.AdjacencyRequirement`; melon implements
:class:`~mcfarm_opt.crops.base.CropRule` directly and writes the pairing by
hand. It is the case the crop interface was given an escape hatch for.

As a model
----------

Introduce a boolean :math:`y_{p,q}` for each free cell *p* and each free
orthogonal neighbour *q*, reading "the stem at *p* fruits into *q*". With
:math:`N_4(p)` the 9x9 hydration square and :math:`N(p)` the four orthogonal
neighbours::

    maximise    sum_p x[p, CROP]
    subject to  x[p, CROP] = 1  =>  sum_{q in N_4(p)} x[q, WATER] >= 1   for all free p
                sum_{q in N(p)} y[p,q] = x[p, CROP]                     for all free p
                sum_{p in N(q)} y[p,q] = x[q, MELON]                    for all free q
                sum_b x[p, b] = 1                                       for all p
                x[p, OBSTACLE] = 1                                      for all blocked p

The two pairing equalities carry more than they look like they do. Read left to
right they say "a stem fruits into exactly one cell" and "a fruit block is
claimed by exactly one stem"; read right to left they say a cell with no stem
fruits nowhere and a cell no stem claims holds no melon, so the ``y`` variables
cannot float free. No separate linking constraint is needed. A stem with no free
neighbour at all gets ``sum(...) = 0 = x[p, CROP]``, which forbids planting it
-- correct, and it falls out rather than being special-cased.

Note the fruit block needs no water of its own. It is dirt or grass, not
farmland; hydration is a condition on the stem alone.

What it costs
-------------

Every stem spends two cells, its own and its fruit's, so melon runs at roughly
half the density of wheat on the same ground -- and the two are otherwise the
same crop, which makes the pair a clean read of what the fruit costs. On a 9x9
wheat grows 80 and melon 40.

On an ``m x n`` open rectangle the accounting is exact::

    2 * stems + water + unused = m * n

so ``stems <= floor((m*n - water) / 2)``, and the question is how few water
sources the stems can be covered by. Whether the bound is *reached* is a
matching question, and this is where the chessboard comes back: stems and fruit
alternate colours, so a layout is a matching on the grid graph, which is
bipartite. A 9x9 has 41 cells of one colour and 40 of the other; spending the
odd cell out on the water source leaves 40 and 40, a perfect matching, and 40
stems.

Do not reach for wheat's ``ceil(m/9) * ceil(n/9)`` here. That covers *every*
cell, and melon only has to cover its stems -- the fruit stands on dirt and
wants nothing. Half the field is exempt, and it is the half the layout gets to
choose, so melon is sometimes strictly cheaper to irrigate: on an 11x11 wheat
needs four sources and melon needs three, because the cells the fourth would
have covered can all be made fruit. The two subproblems are coupled, which is
why this crop has no closed form worth quoting past the identity above.

One consequence for anyone testing this: at the optimum the *stem* count is
determined but the water and unused counts are frequently not. An 8x8 grows 31
stems either way, spending its two spare cells as one water and one unused cell
or as two water. Both are optimal, the search returns whichever it reaches
first, and only ``n_crop`` is safe to assert on.
"""

from __future__ import annotations

from collections.abc import Sequence

from ortools.sat.python import cp_model

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Cell, Grid, Neighborhood
from mcfarm_opt.core.variables import CellVars
from mcfarm_opt.crops.base import AdjacencyRequirement, ObjectiveTerm

__all__ = ["Melon"]

HYDRATION_RADIUS = 4
"""How far water reaches, in Chebyshev distance. The same 9x9 square as wheat --
melon stems stand on farmland and farmland is farmland."""


class Melon:
    """Melon, whose stems must each be given a cell to grow a fruit into.

    The first crop here that is not an
    :class:`~mcfarm_opt.crops.base.AdjacencyCropRule`. Its hydration half is an
    ordinary :class:`~mcfarm_opt.crops.base.AdjacencyRequirement` -- byte for
    byte wheat's -- but its fruit half is a matching between stems and adjacent
    cells, which no count over a neighbourhood can express. See the module
    docstring for why the count would overstate the yield.

    Example:
        >>> from mcfarm_opt import Melon, optimize
        >>> layout = optimize("\\n".join(["." * 9] * 9), crop=Melon())
        >>> layout.metrics.n_crop        # 40 stems, each with its own melon
        40
        >>> layout.metrics.n_support     # the 40 melons, plus one water source
        41
    """

    #: The stem. This is what the objective counts and what metrics report as
    #: crop -- stems and melons stand in bijection, so counting either gives the
    #: yield, and counting the stem keeps melon's objective the same shape as
    #: every other crop's.
    stem_block: BlockType = BlockType.CROP

    #: The fruit. Placed by the model, in a cell of its own.
    fruit_block: BlockType = BlockType.MELON

    @property
    def name(self) -> str:
        """``"melon"``."""
        return "melon"

    def block_types(self) -> frozenset[BlockType]:
        """Water, the stem, and the melon.

        The farmland under the stem stays implicit, as wheat's does -- it is in
        the same cell as the stem, not beside it. The melon is the exception
        that earns its listing: it is beside the stem, so it costs a cell and
        the model has to choose which.
        """
        return frozenset({BlockType.WATER, self.stem_block, self.fruit_block})

    def crop_blocks(self) -> frozenset[BlockType]:
        """Just the stem.

        Counting both stem and fruit would double every yield, since the pairing
        makes them equinumerous. The melon therefore falls into ``n_support``
        alongside the water, which is the honest reading: it is the cell the
        stem spends to produce.
        """
        return frozenset({self.stem_block})

    def hydration(self) -> AdjacencyRequirement:
        """Water within Chebyshev distance 4 -- the 9x9 square, same as wheat."""
        return AdjacencyRequirement(
            blocks=frozenset({BlockType.WATER}),
            neighborhood=Neighborhood.DIAGONAL,
            radius=HYDRATION_RADIUS,
            minimum=1,
        )

    def add_constraints(self, model: cp_model.CpModel, variables: CellVars, grid: Grid) -> None:
        """Hydrate every stem, and pair every stem with a fruit block of its own.

        Obstacle cells take part in neither half: their variables are already
        fixed, and an obstacle can hold neither a stem nor a melon.
        """
        hydration = self.hydration()
        for cell in grid.free_cells():
            hydration.apply(model, variables, grid, cell, variables.var(cell, self.stem_block))

        self._add_pairing(model, variables, grid)

    def _add_pairing(self, model: cp_model.CpModel, variables: CellVars, grid: Grid) -> None:
        """Match each stem to one adjacent fruit block, and each fruit to one stem.

        Builds one boolean per (stem cell, adjacent free cell) pair and ties the
        two marginals of that matching to the stem and melon variables. See the
        module docstring for why both equalities are equalities.
        """
        fruits_of: dict[Cell, list[cp_model.IntVar]] = {c: [] for c in grid.free_cells()}
        stems_of: dict[Cell, list[cp_model.IntVar]] = {c: [] for c in grid.free_cells()}

        for stem in fruits_of:
            for fruit in grid.neighbors(stem, Neighborhood.ORTHOGONAL, 1, include_obstacles=False):
                pair = model.NewBoolVar(f"y[{stem.row},{stem.col}->{fruit.row},{fruit.col}]")
                fruits_of[stem].append(pair)
                stems_of[fruit].append(pair)

        for cell in grid.free_cells():
            # A stem fruits into exactly one cell -- and a cell with no stem
            # into none, which is what forbids a stem with nowhere to fruit.
            model.Add(
                cp_model.LinearExpr.Sum(fruits_of[cell]) == variables.var(cell, self.stem_block)
            )
            # A melon is claimed by exactly one stem. This is the constraint
            # that stops two stems sharing a fruit block.
            model.Add(
                cp_model.LinearExpr.Sum(stems_of[cell]) == variables.var(cell, self.fruit_block)
            )

    def objective_terms(
        self, model: cp_model.CpModel, variables: CellVars, grid: Grid
    ) -> Sequence[ObjectiveTerm]:
        """Maximise the number of stems, each worth 1.

        Equivalently the number of melons, since the pairing makes the two
        counts equal.
        """
        return [
            ObjectiveTerm(variables.var(cell, self.stem_block), 1) for cell in grid.free_cells()
        ]

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"{type(self).__name__}()"
