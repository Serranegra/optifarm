"""Block types that can occupy a cell of the farm layout.

A layout assigns exactly one :class:`BlockType` to every cell of the grid.
Each crop declares (via :meth:`~mcfarm_opt.crops.base.CropRule.block_types`)
which subset of these types its model is allowed to place; the solver always
adds :data:`BlockType.EMPTY` and :data:`BlockType.OBSTACLE` on top of that,
since every layout needs a way to say "nothing here" and "terrain blocked".
"""

from __future__ import annotations

from enum import Enum

__all__ = ["BlockType"]


class BlockType(Enum):
    """A block that may occupy a cell.

    The value of each member is the single character used when rendering a
    layout back to text, so ``BlockType.WATER.symbol`` is ``'W'``.
    """

    EMPTY = "."
    """Free terrain that the layout chose to leave unused."""

    OBSTACLE = "#"
    """Terrain the layout may not touch. Fixed by the input, never chosen."""

    WATER = "W"
    """Water source block. Support block for sugarcane and wheat."""

    SAND = "S"
    """Sand. Support block for sugarcane and cactus placement variants."""

    FARMLAND = "F"
    """Tilled farmland. Support block for wheat, melon, etc."""

    CROP = "C"
    """The harvested crop itself. This is what the objective counts."""

    MELON = "M"
    """A grown melon. Unlike sand or farmland, this block sits *beside* the crop
    rather than under it: a melon stem grows its fruit onto an adjacent cell, so
    the fruit occupies a cell of its own and the model must place it. See
    :mod:`mcfarm_opt.crops.melon`."""

    @property
    def symbol(self) -> str:
        """The character used to render this block in a text grid."""
        return self.value

    @classmethod
    def from_symbol(cls, symbol: str) -> BlockType:
        """Return the block whose :attr:`symbol` is ``symbol``.

        Raises:
            ValueError: if no block uses that symbol.
        """
        for block in cls:
            if block.value == symbol:
                return block
        raise ValueError(f"no block type with symbol {symbol!r}")

    @property
    def is_solid(self) -> bool:
        """Whether this block is a solid, walkable block.

        Useful for crops with *negative* adjacency requirements: cactus, for
        example, breaks when any solid block is orthogonally adjacent to it.
        """
        return self in _SOLID


_SOLID: frozenset[BlockType] = frozenset(
    {BlockType.OBSTACLE, BlockType.SAND, BlockType.FARMLAND, BlockType.CROP, BlockType.MELON}
)
