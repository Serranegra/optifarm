"""The PNG renderer, checked by decoding its own output back into pixels.

``render_layout_png`` and ``render_layout_svg`` share one source of truth for
*what* to draw -- ``iter_layout_rects`` -- so this file is not re-litigating
the house style the way ``test_svg.py`` does against the logo. What it has to
prove instead is narrower and just as load-bearing: that the bytes coming out
the other end are actually a valid PNG whose pixels are the rects it was
handed, which nothing but a decoder can confirm.

The decoder here is intentionally independent of ``png.py``'s own chunk
plumbing -- it walks the chunks and unfilters the scanlines itself, using only
``struct`` and ``zlib``, so a bug in the encoder's framing has something
other than itself to be caught by.
"""

from __future__ import annotations

import struct
import zlib

import pytest

from mcfarm_opt import Cactus, Sugarcane, Wheat, optimize, render_layout_png, render_layout_svg
from mcfarm_opt.io.svg import BACKGROUND, PALETTE, iter_layout_rects


def _decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Minimal PNG decoder: returns (width, height, raw RGB pixel bytes).

    Assumes what ``render_layout_png`` always produces -- 8-bit truecolour,
    no interlacing, a single IDAT stream -- since that is the only shape this
    project's encoder ever emits.
    """
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    pos = 8
    idat = bytearray()
    width = height = None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            width, height, depth, color_type = struct.unpack(">IIBB", chunk[:10])
            assert depth == 8
            assert color_type == 2  # truecolour, no alpha
        elif tag == b"IDAT":
            idat.extend(chunk)
        pos += 8 + length + 4  # length + tag + data + crc

    assert width is not None and height is not None
    raw = zlib.decompress(bytes(idat))

    # Unfilter: every row is prefixed with a filter-type byte. render_layout_png
    # only ever writes filter type 0 ("none"), but real decoders still have to
    # read past the byte to find the next row.
    stride = width * 3
    pixels = bytearray(width * height * 3)
    offset = 0
    for row in range(height):
        filter_type = raw[offset]
        assert filter_type == 0
        offset += 1
        pixels[row * stride : (row + 1) * stride] = raw[offset : offset + stride]
        offset += stride

    return width, height, bytes(pixels)


def _pixel(pixels: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    i = (y * width + x) * 3
    return pixels[i], pixels[i + 1], pixels[i + 2]


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


@pytest.fixture
def logo_layout():
    """The 3x3 sugarcane layout the project logo draws: CCC / WWW / CCC."""
    return optimize("...\n...\n...", crop=Sugarcane())


def test_png_starts_with_signature(logo_layout):
    assert render_layout_png(logo_layout).startswith(b"\x89PNG\r\n\x1a\n")


def test_png_dimensions_match_svg(logo_layout):
    """Same layout, same cell/gap/margin defaults -- the canvas size must agree."""
    width, height, _ = _decode_png(render_layout_png(logo_layout))
    svg_width, svg_height, _ = iter_layout_rects(logo_layout)
    assert (width, height) == (svg_width, svg_height)


def test_png_background_corner(logo_layout):
    """The margin around the grid is background-coloured, same as the SVG."""
    width, _, pixels = _decode_png(render_layout_png(logo_layout))
    assert _pixel(pixels, width, 0, 0) == _hex_to_rgb(BACKGROUND)


def test_png_matches_rects_exactly(logo_layout):
    """Decoded pixels equal an independent scanline rasterisation of the same
    rects render_layout_svg draws -- the two renderers must agree pixel for
    pixel, not just in size."""
    width, height, rects = iter_layout_rects(logo_layout)
    expected = bytearray(width * height * 3)
    for x, y, w, h, fill in rects:
        r, g, b = _hex_to_rgb(fill)
        for py in range(round(y), round(y + h)):
            for px in range(round(x), round(x + w)):
                i = (py * width + px) * 3
                expected[i], expected[i + 1], expected[i + 2] = r, g, b

    _, _, pixels = _decode_png(render_layout_png(logo_layout))
    assert pixels == bytes(expected)


@pytest.mark.parametrize("crop", [Sugarcane(), Cactus(), Wheat()])
def test_png_roundtrips_every_crop(crop):
    """Every shipped crop's palette should encode and decode cleanly."""
    layout = optimize("......\n......\n......\n......", crop=crop)
    width, height, pixels = _decode_png(render_layout_png(layout))
    assert width > 0 and height > 0
    assert len(pixels) == width * height * 3


def test_png_rejects_negative_cell(logo_layout):
    with pytest.raises(ValueError, match="cell must be positive"):
        render_layout_png(logo_layout, cell=-1)


def test_png_rejects_negative_gap(logo_layout):
    with pytest.raises(ValueError, match="gap must be non-negative"):
        render_layout_png(logo_layout, gap=-1)


def test_png_rejects_incomplete_palette(logo_layout):
    incomplete = {k: v for k, v in PALETTE.items() if k.name != "OBSTACLE"}
    layout = optimize("..#\n...\n...", crop=Sugarcane())
    with pytest.raises(ValueError, match="no style for OBSTACLE"):
        render_layout_png(layout, palette=incomplete)


def test_png_custom_cell_size_scales_canvas(logo_layout):
    small_w, small_h, _ = _decode_png(render_layout_png(logo_layout, cell=10, margin=0, gap=0))
    big_w, big_h, _ = _decode_png(render_layout_png(logo_layout, cell=20, margin=0, gap=0))
    assert (big_w, big_h) == (small_w * 2, small_h * 2)


def test_svg_and_png_agree_on_rects(logo_layout):
    """Both renderers are thin wrappers over the same geometry -- the SVG's own
    rect count should equal the PNG rasteriser's."""
    _, _, rects = iter_layout_rects(logo_layout)
    svg = render_layout_svg(logo_layout)
    # Every rect in iter_layout_rects becomes exactly one <rect .../> in the SVG.
    assert svg.count("<rect ") == len(rects)
