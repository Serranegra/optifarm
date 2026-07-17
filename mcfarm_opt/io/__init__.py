"""Text in, text out.

Note:
    This package shadows the standard library's ``io`` only inside its own
    dotted path. Python 3 resolves ``import io`` absolutely, so modules here
    still get the standard library module -- importing this one requires the
    full ``mcfarm_opt.io`` path.
"""

from __future__ import annotations

from mcfarm_opt.io.svg import (
    CACTUS_PALETTE,
    PALETTE,
    WHEAT_PALETTE,
    BlockStyle,
    dressed_for,
    render_layout_svg,
)
from mcfarm_opt.io.text import (
    FREE_SYMBOL,
    OBSTACLE_SYMBOL,
    parse_grid,
    render_grid,
    render_layout,
)

__all__ = [
    "CACTUS_PALETTE",
    "FREE_SYMBOL",
    "OBSTACLE_SYMBOL",
    "PALETTE",
    "WHEAT_PALETTE",
    "BlockStyle",
    "dressed_for",
    "parse_grid",
    "render_grid",
    "render_layout",
    "render_layout_svg",
]
