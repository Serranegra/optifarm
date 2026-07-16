"""Sugarcane: the first concrete crop.

The rule
--------

A cell may hold sugarcane iff it is free terrain, is not itself water, and has
at least one water block orthogonally adjacent (N/S/E/W). Obstacles can hold
neither water nor cane, and so never help a neighbour qualify.

As a model
----------

Let :math:`x_{p,\\mathrm{CROP}}` and :math:`x_{p,\\mathrm{WATER}}` be the
one-hot variables from :mod:`mcfarm_opt.core.variables`, and :math:`N(p)` the
orthogonal neighbours of *p*. Then::

    maximise    sum_p x[p, CROP]
    subject to  x[p, CROP] = 1  =>  sum_{q in N(p)} x[q, WATER] >= 1     for all free p
                sum_b x[p, b] = 1                                        for all p
                x[p, OBSTACLE] = 1                                       for all blocked p

"is not itself water" needs no constraint of its own: the one-hot constraint
already forbids a cell from being both CROP and WATER. "is free" is likewise
implicit, since a blocked cell has ``x[p, CROP]`` fixed to 0.

The tension the solver resolves is that water both enables and consumes cells:
every water block bought costs one cell of production but can pay for up to four
neighbours. Optimal layouts therefore tend towards stripes of water spaced two
apart, though on irregular terrain the exact answer is far from obvious --
which is the reason for using an exact solver rather than a template.
"""

from __future__ import annotations

from collections.abc import Sequence

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Neighborhood
from mcfarm_opt.crops.base import AdjacencyCropRule, AdjacencyRequirement

__all__ = ["Sugarcane"]


class Sugarcane(AdjacencyCropRule):
    """Sugarcane, which grows on any cell with orthogonally adjacent water.

    Example:
        >>> from mcfarm_opt import optimize, Sugarcane
        >>> optimize(".....\\n.....", crop=Sugarcane()).metrics.n_crop
        7
    """

    crop_block = BlockType.CROP

    @property
    def name(self) -> str:
        """``"sugarcane"``."""
        return "sugarcane"

    def support_blocks(self) -> frozenset[BlockType]:
        """Water. The sand cane stands on is implicit -- this is a 2D model."""
        return frozenset({BlockType.WATER})

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        """At least one orthogonally adjacent water block."""
        return (
            AdjacencyRequirement(
                blocks=frozenset({BlockType.WATER}),
                neighborhood=Neighborhood.ORTHOGONAL,
                radius=1,
                minimum=1,
            ),
        )
