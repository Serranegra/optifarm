"""Rendering a layout as a PNG image, without depending on anything to do it.

:mod:`mcfarm_opt.io.svg` already draws the house style; this module just
rasterises the same rects onto a pixel grid and wraps them in the PNG file
format by hand. That "by hand" is deliberate, not an oversight: the project's
own images are produced by ``examples/generate_readme_images.py`` handing the
SVG to *whatever browser is lying around* to rasterise, precisely because
nothing here wants to depend on a renderer. A PNG encoder built from
:mod:`struct` and :mod:`zlib` -- both standard library -- keeps that promise
for people who want a bitmap instead of an SVG (to paste into a chat, a wiki
page, anywhere that does not render vector markup) without adding Pillow, or a
browser, as a dependency of a farm-layout solver.

The pixels themselves are not reinvented: :func:`~mcfarm_opt.io.svg.iter_layout_rects`
is the single source of truth for what the house style draws, so a palette or
border-ratio change made for the SVG renderer is picked up here for free, and
the two formats cannot silently drift apart.
"""

from __future__ import annotations

import struct
import zlib

from mcfarm_opt.core.blocks import BlockType
from mcfarm_opt.core.result import FarmLayout
from mcfarm_opt.io.svg import CELL, GAP, MARGIN, BlockStyle, iter_layout_rects

__all__ = ["render_layout_png"]

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, data: bytes) -> bytes:
    """One length-prefixed, CRC-suffixed PNG chunk."""
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def render_layout_png(
    layout: FarmLayout,
    *,
    cell: int = CELL,
    gap: int = GAP,
    margin: int = MARGIN,
    palette: dict[BlockType, BlockStyle] | None = None,
) -> bytes:
    """Render ``layout`` as a standalone PNG image.

    Same picture as :func:`~mcfarm_opt.io.svg.render_layout_svg` -- same cell
    size, gap, margin and palette defaults -- just encoded as an 8-bit RGB
    bitmap instead of vector markup. Useful anywhere a raster image is easier
    to drop in than an SVG document.

    Args:
        layout: the solved layout to draw.
        cell: side of one block, in pixels.
        gap: seam between blocks, in pixels.
        margin: background border around the grid, in pixels.
        palette: block styles, defaulting to :data:`~mcfarm_opt.io.svg.PALETTE`.

    Returns:
        The complete bytes of a PNG file, ready to write with
        ``Path(...).write_bytes(...)``.

    Raises:
        ValueError: if ``cell`` or ``gap`` is negative, or the palette has no
            style for a block the layout actually uses.

    Example:
        >>> from mcfarm_opt import Sugarcane, optimize
        >>> png = render_layout_png(optimize("...\\n...\\n...", crop=Sugarcane()))
        >>> png.startswith(b"\\x89PNG")
        True
    """
    width, height, rects = iter_layout_rects(
        layout, cell=cell, gap=gap, margin=margin, palette=palette
    )

    # Flat RGB canvas, painted in the same painter's-algorithm order the rects
    # were produced in: later rects (borders) overwrite earlier ones (fills)
    # exactly as the SVG's stacked <rect> elements do.
    canvas = bytearray(width * height * 3)
    for x, y, w, h, fill in rects:
        r, g, b = _hex_to_rgb(fill)
        x0, y0 = round(x), round(y)
        x1, y1 = round(x + w), round(y + h)
        for py in range(y0, y1):
            row = py * width * 3
            for px in range(x0, x1):
                offset = row + px * 3
                canvas[offset] = r
                canvas[offset + 1] = g
                canvas[offset + 2] = b

    # Raw scanlines: PNG wants a filter-type byte (0 = "none") before each row.
    raw = bytearray()
    for py in range(height):
        raw.append(0)
        start = py * width * 3
        raw.extend(canvas[start : start + width * 3])

    ihdr = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,  # bit depth
        2,  # colour type: truecolour (RGB, no alpha)
        0,  # compression method (always 0)
        0,  # filter method (always 0)
        0,  # interlace method: none
    )

    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + _chunk(b"IEND", b"")
    )
