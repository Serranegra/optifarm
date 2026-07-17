"""Wheat: grows wherever water reaches, and water reaches a long way.

The rule
--------

A cell may hold wheat iff it is free, is not itself water, and has water within
**4 blocks in every direction** -- Chebyshev distance, so a single water source
hydrates the 9x9 square centred on it. That is 80 cells fed by one.

What counts as "within 4 in every direction"
--------------------------------------------

Chebyshev distance, ``max(|dr|, |dc|) <= 4``, which is
:attr:`~mcfarm_opt.core.grid.Neighborhood.DIAGONAL` at radius 4. Diagonals cost
the same as straight lines here, which is exactly what makes the reachable set a
9x9 *square* rather than a diamond. Compare sugarcane, which uses
``ORTHOGONAL`` at radius 1 -- same abstraction, both parameters different.

Hydration ignores what is in the way. Minecraft checks distance, not line of
sight, so an obstacle sitting between the water and the farmland does not shade
it. That falls out for free here: the requirement counts water in the
neighbourhood, and an obstacle simply cannot hold water.

The farmland the wheat grows on is implicit, exactly as sugarcane's sand is. It
sits *under* the wheat, inside the same cell of this top-down projection, so it
is never a neighbour and never needs modelling. Hence
:meth:`Wheat.support_blocks` is water and nothing else.

As a model
----------

With :math:`N_4(p)` the 9x9 square around *p*::

    maximise    sum_p x[p, CROP]
    subject to  x[p, CROP] = 1  =>  sum_{q in N_4(p)} x[q, WATER] >= 1   for all free p
                sum_b x[p, b] = 1                                        for all p
                x[p, OBSTACLE] = 1                                       for all blocked p

Structurally identical to sugarcane. Economically nothing like it.

Sugarcane is a *trade*: a water block costs one cell of production and feeds at
most four, so water is expensive and the optimum hovers around 75%. Wheat is a
*covering* problem: a water block still costs one cell but feeds up to eighty, so
water is nearly free and the only question is how few sources cover the field.
The optimum runs to about 98%.

On an open ``m x n`` rectangle the answer is closed-form::

    wheat = m*n - ceil(m/9) * ceil(n/9)

The lower bound on water is a witness argument: take the cells at rows
0, 9, 18, ... and columns 0, 9, 18, ... Any two of them are at Chebyshev
distance >= 9, and one water can only serve cells within distance 4 of itself --
so two cells it serves are within 8 of each other. No water can serve two
witnesses, and every witness needs one (itself, if nothing else). That forces
``ceil(m/9) * ceil(n/9)`` sources. Placing them on a 9-spaced lattice achieves
it, so the bound is tight.
"""

from __future__ import annotations

from collections.abc import Sequence

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Neighborhood
from mcfarm_opt.crops.base import AdjacencyCropRule, AdjacencyRequirement

__all__ = ["Wheat"]

HYDRATION_RADIUS = 4
"""How far water reaches, in Chebyshev distance. Radius 4 gives the 9x9 square."""


class Wheat(AdjacencyCropRule):
    """Wheat, which grows on any cell within 4 blocks of water in every direction.

    The third shape of adjacency rule, and the one that shows the abstraction was
    worth building: sugarcane needs a neighbour (``minimum=1`` at radius 1),
    cactus forbids one (``maximum=0``), wheat needs one *far away*
    (``minimum=1`` at radius 4, Chebyshev). Same
    :class:`~mcfarm_opt.crops.base.AdjacencyRequirement`, three parameters
    turned.

    Example:
        >>> from mcfarm_opt import Wheat, optimize
        >>> layout = optimize("\\n".join(["." * 9] * 9), crop=Wheat())
        >>> layout.metrics.n_crop        # one water at the centre feeds the rest
        80
        >>> layout.metrics.n_support
        1
    """

    crop_block = BlockType.CROP

    @property
    def name(self) -> str:
        """``"wheat"``."""
        return "wheat"

    def support_blocks(self) -> frozenset[BlockType]:
        """Water. The farmland the wheat stands on is implicit -- this is a 2D model."""
        return frozenset({BlockType.WATER})

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        """At least one water block within Chebyshev distance 4 -- the 9x9 square."""
        return (
            AdjacencyRequirement(
                blocks=frozenset({BlockType.WATER}),
                neighborhood=Neighborhood.DIAGONAL,
                radius=HYDRATION_RADIUS,
                minimum=1,
            ),
        )
