"""Cactus: grows anywhere nothing solid touches it.

The rule
--------

A cell may hold cactus iff it is free and **no orthogonally adjacent cell holds
a solid block**. That is the whole rule -- cactus needs no support nearby, it
only needs to be left alone.

What counts as solid, in a 2D model
-----------------------------------

This is the one judgement call, and it decides every number this module
produces, so it is worth being explicit.

The grid is a *top-down projection*: one cell, one column of the world. A cactus
breaks when something solid touches it **at the cactus's own level**, so the
question for each neighbouring cell is what sits at that level:

* another **cactus** -- solid, breaks it. This is the constraint that shapes the
  whole layout.
* an **obstacle** -- modelled as solid, so cactus cannot hug it. The terrain
  format has a single ``'#'``, so this treats every obstacle as a wall rather
  than a pit. It is the conservative reading: a layout that is valid against a
  wall is also valid against a hole, but not the reverse. If a future terrain
  format distinguishes solid obstacles from voids, this is the line to revisit.
* **sand** -- *not* solid at cactus level, and deliberately absent below. The
  sand a cactus stands on is one block **underneath** it, not beside it; in a
  top-down projection it is inside the same cell, not a neighbour. This is why
  :meth:`Cactus.support_blocks` is empty, exactly as sugarcane leaves the sand
  it stands on implicit. Real cactus farms rely on this: a checkerboard of cacti
  sits on solid sand and grows fine, because the sand never reaches cactus
  level.

So the blocks that are solid *at cactus level* are cactus and obstacle. Note
this is narrower than :attr:`~mcfarm_opt.core.blocks.BlockType.is_solid`, which
answers the block-type question ("is sand a solid block?" -- yes) rather than
the projection question ("is sand solid *where the cactus is*?" -- no).

As a model
----------

With :math:`N(p)` the orthogonal neighbours of *p*::

    maximise    sum_p x[p, CROP]
    subject to  x[p, CROP] = 1  =>  sum_{q in N(p)} (x[q, CROP] + x[q, OBSTACLE]) = 0
                sum_b x[p, b] = 1                                       for all p
                x[p, OBSTACLE] = 1                                      for all blocked p

The requirement is stated once per cell and needs no mirror: if two adjacent
cells both held cactus, each one's own constraint would already be violated.

This is **maximum independent set** on the grid graph, minus the cells an
obstacle poisons. That makes it a genuinely different shape of problem from
sugarcane, in two ways worth knowing:

* It is *easy*. Grid graphs are bipartite (colour them like a chessboard), and
  maximum independent set on a bipartite graph is polynomial -- by König's
  theorem it is ``n - maximum matching``. The LP relaxation is integral, so
  CP-SAT closes the proof at the root instead of searching. Where sugarcane on a
  15x15 takes seconds, cactus is instant.
* Obstacles are **expensive**. A sugarcane obstacle costs roughly the cell
  itself. A cactus obstacle also poisons its up-to-4 neighbours, since none of
  them may touch it -- one blocked cell can cost five.

On open ground the answer is the checkerboard everyone already builds:
``ceil(rows * cols / 2)``, about 50%. The solver earns its keep on irregular
terrain, where "which half of the board" stops being a global choice.
"""

from __future__ import annotations

from collections.abc import Sequence

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Neighborhood
from mcfarm_opt.crops.base import AdjacencyCropRule, AdjacencyRequirement

__all__ = ["Cactus"]

#: The blocks that are solid *at cactus level* in this top-down projection.
#: Deliberately not ``{b for b in BlockType if b.is_solid}``: that set includes
#: sand and farmland, which in this model sit one block below the crop rather
#: than beside it. See the module docstring.
SOLID_AT_CACTUS_LEVEL: frozenset[BlockType] = frozenset(
    {BlockType.CROP, BlockType.OBSTACLE}
)


class Cactus(AdjacencyCropRule):
    """Cactus, which grows on any cell no solid block touches.

    The mirror image of :class:`~mcfarm_opt.crops.sugarcane.Sugarcane`, and the
    reason :class:`~mcfarm_opt.crops.base.AdjacencyRequirement` carries its sign
    as a parameter: cane demands a neighbour, cactus forbids one, and the two
    rules differ only in ``minimum=1`` versus ``maximum=0``.

    Example:
        >>> from mcfarm_opt import Cactus, optimize
        >>> layout = optimize("....\\n....", crop=Cactus())
        >>> layout.metrics.n_crop
        4
        >>> layout.metrics.is_optimal
        True
    """

    crop_block = BlockType.CROP

    @property
    def name(self) -> str:
        """``"cactus"``."""
        return "cactus"

    def support_blocks(self) -> frozenset[BlockType]:
        """None. Cactus needs nothing placed beside it.

        The sand it stands on is implicit -- it sits under the cactus, inside
        the same cell of this 2D projection, so it is never a neighbour and
        never breaks anything. See the module docstring.
        """
        return frozenset()

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        """No solid block orthogonally adjacent."""
        return (
            AdjacencyRequirement(
                blocks=SOLID_AT_CACTUS_LEVEL,
                neighborhood=Neighborhood.ORTHOGONAL,
                radius=1,
                maximum=0,
                # Obstacles must be counted: an obstacle is a wall, and a wall
                # breaks a cactus. Dropping them here would silently let cactus
                # hug the terrain.
                include_obstacles=True,
            ),
        )
