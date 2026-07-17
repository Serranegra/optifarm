"""Rendering a layout as an SVG image, in the project's own visual style.

The text renderer in :mod:`mcfarm_opt.io.text` answers "what did the solver
decide". This one answers "what does it look like" -- same layout, drawn rather
than spelled.

The style is the project logo's, and that is not a coincidence: the logo *is* a
farm. It is the proven optimal 3x3 sugarcane layout, ``CCC / WWW / CCC`` -- six
cane, one water strip, 66.7%. Rendering that layout through this module
reproduces ``assets/logo.svg`` almost exactly, which is the cheapest possible
test that the style has not drifted, and ``tests/test_svg.py`` uses it as one.

The look is deliberately pixel-art: flat fills, and borders drawn as *stepped
square blocks* rather than smooth diagonal bevels, with
``shape-rendering="crispEdges"`` so no renderer softens them back. Water is flat
and merges across the gaps into continuous sheets, because water in a farm is a
body, not a set of tiles.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.grid import Cell
from mcfarm_opt.core.result import FarmLayout

__all__ = [
    "CACTUS_PALETTE",
    "PALETTE",
    "WHEAT_PALETTE",
    "BlockStyle",
    "dressed_for",
    "render_layout_svg",
]

BACKGROUND = "#101828"
"""The dark slate the whole image sits on. Straight from the logo."""


@dataclass(frozen=True, slots=True)
class BlockStyle:
    """How one block type is drawn.

    Attributes:
        fill: the flat base colour.
        highlight: the top/left border colour, or ``None`` for a flat block.
        shadow: the bottom/right border colour, or ``None`` for a flat block.
        merge: whether neighbouring cells of this same type should grow across
            the gap between them and read as one continuous surface. True for
            water, which is a body rather than a set of tiles; false for
            everything else, where the grid should stay legible.
    """

    fill: str
    highlight: str | None = None
    shadow: str | None = None
    merge: bool = False


PALETTE: dict[BlockType, BlockStyle] = {
    # The crop, with the logo's stepped light/shadow border.
    BlockType.CROP: BlockStyle(fill="#22c55e", highlight="#86efac", shadow="#15803d"),
    # Water: flat, no border, and merged into sheets.
    BlockType.WATER: BlockStyle(fill="#0ea5e9", merge=True),
    # Free ground the layout chose not to use. Quiet, near the background.
    BlockType.EMPTY: BlockStyle(fill="#1e293b"),
    # Terrain the layout could not touch. Lighter than EMPTY so the two read
    # apart at a glance: "unused" and "unusable" are different failures.
    BlockType.OBSTACLE: BlockStyle(fill="#334155"),
    # No shipped crop places these -- sand and farmland live *under* the crop in
    # this 2D projection, never beside it. They are here so a future crop that
    # does place them renders instead of raising.
    BlockType.SAND: BlockStyle(fill="#e0c068", highlight="#f5e6b3", shadow="#a08040"),
    BlockType.FARMLAND: BlockStyle(fill="#6b4423", highlight="#8b5a2b", shadow="#4a2f18"),
}


def dressed_for(*, crop: BlockStyle, ground: BlockStyle) -> dict[BlockType, BlockStyle]:
    """The house palette with the two entries a crop is allowed to repaint.

    The house style is one crop's: :data:`PALETTE` was drawn from a *sugarcane*
    logo, where green means cane and a bare cell means nothing much. Another crop
    is a different plant standing on different ground, and that is the whole of
    the difference -- so a crop palette overrides exactly two entries and
    inherits the rest. The cell size, the border ratio, the seams, the
    background, the water and the obstacle colour stay where the logo put them,
    which is what keeps every picture in the README the same picture.

    ``ground`` is :attr:`~mcfarm_opt.core.blocks.BlockType.EMPTY`, and it means
    something sharper here than it does by default. In :data:`PALETTE`, EMPTY is
    "ground the layout declined to use" and is drawn quiet, near the background.
    In a crop palette it is the material the farm is built on, showing through
    where nothing was planted -- sand for cactus, farmland for wheat. That is the
    same projection argument the crop rules make: the block a crop stands on sits
    *under* it, inside the cell, never beside it, so the bare cells are the only
    place you ever see it. Being a real material, it is allowed to be a colour.

    Args:
        crop: how this crop's own block is drawn.
        ground: what a planted-nothing cell shows.

    Returns:
        A palette covering every block type, safe to pass to
        :func:`render_layout_svg`.
    """
    return {**PALETTE, BlockType.CROP: crop, BlockType.EMPTY: ground}


CACTUS_PALETTE: dict[BlockType, BlockStyle] = dressed_for(
    # Cactus, not cane: a darker, mossier green, so the two never read as the
    # same plant in a README that shows both. Same stepped border as ``cane-px``,
    # two tones either side of the base -- the logo's block in another colour,
    # not another block.
    crop=BlockStyle(fill="#166534", highlight="#16a34a", shadow="#052e16"),
    # Sand. Flat and merged, exactly like water and for the same reason: a
    # stretch of sand is a body, not a set of tiles.
    ground=BlockStyle(fill="#d4a76a", merge=True),
)
"""The house palette, dressed for a cactus farm: dark green on sand.

Example:
    >>> from mcfarm_opt import Cactus, optimize
    >>> svg = render_layout_svg(optimize("...", crop=Cactus()), palette=CACTUS_PALETTE)
    >>> "#166534" in svg
    True
"""

WHEAT_PALETTE: dict[BlockType, BlockStyle] = dressed_for(
    # Ripe wheat: amber, the one warm crop colour that cannot be mistaken for
    # either green. Same stepped border, same two-tones-either-side rule.
    crop=BlockStyle(fill="#f59e0b", highlight="#fcd34d", shadow="#b45309"),
    # Tilled farmland, and the same brown :data:`PALETTE` already reserves for
    # it -- one brown in the project, not two. Flat and merged like the sand and
    # the water: a worked field is a surface, not a grid of tiles.
    ground=BlockStyle(fill=PALETTE[BlockType.FARMLAND].fill, merge=True),
)
"""The house palette, dressed for a wheat farm: amber on farmland.

Water keeps the logo's blue here, and that matters more for wheat than for any
other crop: wheat's whole result is *how few sources cover the field*, so the
blue blocks are the thing to count. On ``rubble`` the hand lattice needs six and
the optimum needs four, and the picture says so without a caption.

Example:
    >>> from mcfarm_opt import Wheat, optimize
    >>> svg = render_layout_svg(optimize("...", crop=Wheat()), palette=WHEAT_PALETTE)
    >>> "#f59e0b" in svg
    True
"""

CELL = 76
"""Side of one block, in SVG units. The logo's, so the styles line up."""

GAP = 3
"""Dark seam between blocks. The logo's."""

MARGIN = 33
"""Border of background around the grid. The logo's."""

_BORDER_RATIO = 9 / 76
"""The logo's border is 9 units on a 76 unit block. Kept as a ratio so a caller
who changes the cell size gets a border that scales with it."""


def _rect(x: float, y: float, width: float, height: float, fill: str) -> str:
    return (
        f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(width)}" '
        f'height="{_n(height)}" fill="{fill}"/>'
    )


def _n(value: float) -> str:
    """Format a number without a trailing ``.0``, to keep the SVG readable."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def render_layout_svg(
    layout: FarmLayout,
    *,
    cell: int = CELL,
    gap: int = GAP,
    margin: int = MARGIN,
    palette: dict[BlockType, BlockStyle] | None = None,
) -> str:
    """Render ``layout`` as a standalone SVG document.

    The image grows with the terrain rather than squeezing into a fixed box: a
    10x10 farm is drawn at the same block size as a 3x3, just on a bigger canvas.
    That keeps the blocks looking identical across every image in the README,
    which is the point of having a house style at all. Scale at the point of use
    (``<img width=...>``), not here.

    Args:
        layout: the solved layout to draw.
        cell: side of one block, in SVG units.
        gap: seam between blocks.
        margin: background border around the grid.
        palette: block styles, defaulting to :data:`PALETTE`.

    Returns:
        A complete ``<svg>`` document as a string, ready to write to a file.

    Raises:
        ValueError: if ``cell`` or ``gap`` is negative, or the palette has no
            style for a block the layout actually uses.

    Example:
        >>> from mcfarm_opt import Sugarcane, optimize
        >>> svg = render_layout_svg(optimize("...\\n...\\n...", crop=Sugarcane()))
        >>> svg.startswith("<svg")
        True
    """
    if cell <= 0:
        raise ValueError(f"cell must be positive, got {cell}")
    if gap < 0:
        raise ValueError(f"gap must be non-negative, got {gap}")

    styles = palette if palette is not None else PALETTE
    grid = layout.grid
    rows, cols = grid.shape

    width = margin * 2 + cols * cell + max(cols - 1, 0) * gap
    height = margin * 2 + rows * cell + max(rows - 1, 0) * gap
    border = max(1, round(cell * _BORDER_RATIO))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"'
        f' shape-rendering="crispEdges">',
        f"  <!-- {layout.crop_name}: {layout.metrics.n_crop} crop on {rows}x{cols},"
        f" {layout.metrics.efficiency:.1f}% of usable ground -->",
        f"  {_rect(0, 0, width, height, BACKGROUND)}",
    ]

    for row in range(rows):
        for col in range(cols):
            here = Cell(row, col)
            block = layout.block_at(here)
            try:
                style = styles[block]
            except KeyError:
                raise ValueError(
                    f"no style for {block.name}; palette covers "
                    f"{sorted(b.name for b in styles)}"
                ) from None

            x = margin + col * (cell + gap)
            y = margin + row * (cell + gap)
            w = h = cell

            # Grow across the seam toward an identical neighbour, so a run of
            # water reads as one sheet. Only right and down: the neighbour's own
            # rect starts exactly where this one now ends, so runs join without
            # overlapping.
            if style.merge:
                right = Cell(row, col + 1)
                below = Cell(row + 1, col)
                if grid.contains(right) and layout.block_at(right) is block:
                    w += gap
                if grid.contains(below) and layout.block_at(below) is block:
                    h += gap

            parts.append(f"  {_rect(x, y, w, h, style.fill)}")

            # The logo's border: top and left in the highlight, then bottom and
            # right in the shadow drawn *over* them, so the shadow takes the two
            # shared corners. Order is load-bearing.
            if style.highlight is not None:
                parts.append(f"  {_rect(x, y, cell, border, style.highlight)}")
                parts.append(f"  {_rect(x, y, border, cell, style.highlight)}")
            if style.shadow is not None:
                parts.append(f"  {_rect(x, y + cell - border, cell, border, style.shadow)}")
                parts.append(f"  {_rect(x + cell - border, y, border, cell, style.shadow)}")

    parts.append("</svg>")
    return "\n".join(parts) + "\n"
