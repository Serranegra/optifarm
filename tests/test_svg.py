"""The SVG renderer, checked against the logo it borrows its style from.

The headline test here is unusual and worth explaining. ``assets/logo.svg`` was
drawn by hand, but what it draws is not decoration -- it is the proven optimal
3x3 sugarcane layout, ``CCC / WWW / CCC``. So the renderer, pointed at that
layout, has something exact to be compared against: it should paint the same
picture, pixel for pixel.

It cannot be a string comparison -- the logo factors its cane block into a
``<defs>``/``<use>`` pair and draws its water as one wide rect, while the
renderer emits flat rects per cell and merges water across the seams. Different
documents, same image. So the test rasterises both with a tiny painter's
algorithm (stdlib only, no browser, no cairo) and compares the resulting pixels.

That is what keeps the house style honest: if anyone edits the palette, the
border ratio, the spacing or the merge rule, this fails.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from mcfarm_opt import BlockType, Sugarcane, optimize, render_layout_svg
from mcfarm_opt.io.svg import BACKGROUND, PALETTE, BlockStyle

LOGO = Path(__file__).resolve().parent.parent / "assets" / "logo.svg"

SVG_NS = "{http://www.w3.org/2000/svg}"


def _tag(element: ET.Element) -> str:
    return element.tag.removeprefix(SVG_NS)


def _rects_of(element: ET.Element, defs: dict[str, ET.Element], dx: float, dy: float):
    """Yield (x, y, w, h, fill) for a subtree, expanding <use> against ``defs``."""
    for child in element:
        name = _tag(child)
        if name == "defs":
            continue
        if name == "rect":
            yield (
                float(child.get("x", 0)) + dx,
                float(child.get("y", 0)) + dy,
                float(child.get("width", 0)),
                float(child.get("height", 0)),
                child.get("fill", "none"),
            )
        elif name == "use":
            ref = child.get("href", child.get(f"{SVG_NS}href", "")).lstrip("#")
            group = defs[ref]
            ox, oy = float(child.get("x", 0)), float(child.get("y", 0))
            yield from _rects_of(group, defs, dx + ox, dy + oy)
        elif name in ("g", "svg"):
            ox, oy = float(child.get("x", 0)), float(child.get("y", 0))
            yield from _rects_of(child, defs, dx + ox, dy + oy)


def rasterise(svg_text: str) -> tuple[tuple[str, ...], ...]:
    """Paint an SVG of flat rects into a grid of colours, painter's algorithm.

    Only understands what these documents contain: axis-aligned ``<rect>``,
    ``<g>``, ``<defs>`` and ``<use>``. That is deliberate -- a general SVG
    rasteriser would be a dependency, and this needs twenty lines.
    """
    root = ET.fromstring(svg_text)
    _, _, width, height = (int(v) for v in root.get("viewBox").split())

    defs: dict[str, ET.Element] = {}
    for defs_node in root.iter(f"{SVG_NS}defs"):
        for child in defs_node:
            if child.get("id"):
                defs[child.get("id")] = child

    canvas = [["none"] * width for _ in range(height)]
    for x, y, w, h, fill in _rects_of(root, defs, 0, 0):
        for row in range(int(y), min(int(y + h), height)):
            for col in range(int(x), min(int(x + w), width)):
                canvas[row][col] = fill
    return tuple(tuple(row) for row in canvas)


class TestItReproducesTheLogo:
    """The logo is the optimal 3x3 farm. The renderer should redraw it exactly."""

    def test_rendering_the_optimal_3x3_repaints_the_logo(self):
        """Pixel for pixel, against the hand-authored file.

        If this fails, either the house style drifted or the 3x3 optimum did.
        Both are worth stopping for.
        """
        layout = optimize("...\n...\n...", crop=Sugarcane())
        assert layout.render() == "CCC\nWWW\nCCC"

        rendered = rasterise(render_layout_svg(layout))
        logo = rasterise(LOGO.read_text(encoding="utf-8"))
        assert rendered == logo

    def test_the_logo_is_a_farm_not_a_drawing(self):
        """The premise of the test above: what the logo draws is the real optimum."""
        assert optimize("...\n...\n...", crop=Sugarcane()).metrics.n_crop == 6

    def test_the_two_documents_are_not_merely_identical_text(self):
        """Guards the test above from being trivially true.

        The logo factors its blocks through <defs>/<use> and draws water as one
        rect; the renderer emits per-cell rects. Same image, different source --
        which is why the comparison has to rasterise.
        """
        layout = optimize("...\n...\n...", crop=Sugarcane())
        assert render_layout_svg(layout) != LOGO.read_text(encoding="utf-8")
        assert "<use" in LOGO.read_text(encoding="utf-8")
        assert "<use" not in render_layout_svg(layout)


class TestDocument:
    def test_it_is_a_standalone_svg(self, rectangle):
        svg = render_layout_svg(optimize(rectangle(3, 3), crop=Sugarcane()))
        assert svg.startswith("<svg")
        assert svg.rstrip().endswith("</svg>")
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg

    def test_it_parses(self, rectangle):
        ET.fromstring(render_layout_svg(optimize(rectangle(4, 5), crop=Sugarcane())))

    def test_crisp_edges_is_set(self, rectangle):
        """Without it a renderer antialiases the stepped borders back into
        gradients, which is the one thing the style is not."""
        assert 'shape-rendering="crispEdges"' in render_layout_svg(
            optimize(rectangle(3, 3), crop=Sugarcane())
        )

    def test_output_is_deterministic(self, rectangle):
        """Same layout in, same bytes out -- so regenerating the README images
        produces no diff unless something real changed."""
        layout = optimize(rectangle(3, 3), crop=Sugarcane())
        assert render_layout_svg(layout) == render_layout_svg(layout)


class TestGeometry:
    def test_the_canvas_grows_with_the_terrain(self):
        """Blocks stay one size; the image gets bigger. A 3x3 and a 10x10 draw
        the same block, so every picture in the README matches."""
        svg = render_layout_svg(optimize("\n".join(["." * 10] * 4), crop=Sugarcane()))
        # margin*2 + cols*cell + (cols-1)*gap
        width = 33 * 2 + 10 * 76 + 9 * 3
        height = 33 * 2 + 4 * 76 + 3 * 3
        assert f'viewBox="0 0 {width} {height}"' in svg

    def test_a_1x1_terrain_is_one_block_of_margin(self):
        svg = render_layout_svg(optimize(".", crop=Sugarcane()))
        assert f'viewBox="0 0 {33 * 2 + 76} {33 * 2 + 76}"' in svg

    def test_an_empty_terrain_renders_the_margins_and_nothing_else(self):
        svg = render_layout_svg(optimize("", crop=Sugarcane()))
        assert 'viewBox="0 0 66 66"' in svg
        ET.fromstring(svg)

    def test_water_merges_across_the_seam(self):
        """A run of water is a body, not tiles. The logo draws its strip as one
        rect; the renderer grows each cell over the gap to the same effect."""
        layout = optimize("...\n...\n...", crop=Sugarcane())
        assert layout.render() == "CCC\nWWW\nCCC"
        svg = render_layout_svg(layout)
        # left and middle water grow by the 3-unit gap; the last has no
        # right-hand neighbour to join.
        assert '<rect x="33" y="112" width="79" height="76" fill="#0ea5e9"/>' in svg
        assert '<rect x="191" y="112" width="76" height="76" fill="#0ea5e9"/>' in svg

    def test_cane_does_not_merge(self, rectangle):
        """The grid should stay legible for everything that is not water.

        Every cane rect is exactly one cell wide -- never grown over the seam
        the way water is.
        """
        # The 3x3 is the case with adjacent water to contrast against: its strip
        # merges (see test_water_merges_across_the_seam) while its cane does not.
        svg = render_layout_svg(optimize("...\n...\n...", crop=Sugarcane()))
        root = ET.fromstring(svg)
        cane = [r for r in root if r.get("fill") == PALETTE[BlockType.CROP].fill]
        assert len(cane) == 6, "the 3x3 optimum grows six cane"
        assert {r.get("width") for r in cane} == {"76"}


class TestPalette:
    def test_every_block_a_shipped_crop_can_place_has_a_style(self):
        """A layout that renders as a KeyError would be worse than ugly."""
        from mcfarm_opt import Cactus, Wheat

        for crop in (Sugarcane(), Cactus(), Wheat()):
            for block in crop.block_types() | {BlockType.EMPTY, BlockType.OBSTACLE}:
                assert block in PALETTE, f"{crop.name} can place {block.name}"

    def test_the_whole_enum_is_covered(self):
        assert set(PALETTE) == set(BlockType)

    def test_colours_come_from_the_logo(self):
        """Not a style choice made here -- a style borrowed, deliberately."""
        logo = LOGO.read_text(encoding="utf-8")
        for colour in (BACKGROUND, "#22c55e", "#86efac", "#15803d", "#0ea5e9"):
            assert colour in logo

    def test_unused_and_unusable_are_told_apart(self):
        """'The layout skipped this' and 'the terrain forbade this' are different
        failures, so they cannot be the same colour."""
        assert PALETTE[BlockType.EMPTY].fill != PALETTE[BlockType.OBSTACLE].fill

    def test_water_is_flat_and_cane_is_not(self):
        water, cane = PALETTE[BlockType.WATER], PALETTE[BlockType.CROP]
        assert water.highlight is None and water.shadow is None
        assert water.merge
        assert cane.highlight is not None and cane.shadow is not None
        assert not cane.merge

    def test_a_terrain_with_obstacles_uses_the_obstacle_colour(self):
        svg = render_layout_svg(optimize(".#.\n...\n.#.", crop=Sugarcane()))
        assert PALETTE[BlockType.OBSTACLE].fill in svg

    def test_a_custom_palette_is_honoured(self, rectangle):
        plain = dict(PALETTE)
        plain[BlockType.CROP] = BlockStyle(fill="#ff0000")
        svg = render_layout_svg(optimize(rectangle(2, 2), crop=Sugarcane()), palette=plain)
        assert "#ff0000" in svg
        assert "#22c55e" not in svg

    def test_a_palette_missing_a_used_block_fails_loudly(self, rectangle):
        holed = {b: s for b, s in PALETTE.items() if b is not BlockType.CROP}
        with pytest.raises(ValueError, match="no style for CROP"):
            render_layout_svg(optimize(rectangle(3, 3), crop=Sugarcane()), palette=holed)


class TestArguments:
    def test_cell_size_scales_the_border_with_it(self):
        """The border is 9/76 of the block in the logo, and stays that ratio.

        Doubling the cell to 152 doubles the border to 18. A 1x1 terrain would
        prove nothing here -- sugarcane grows nothing on it, so there would be
        no bordered block to measure.
        """
        svg = render_layout_svg(optimize("...\n...\n...", crop=Sugarcane()), cell=152)
        highlight = PALETTE[BlockType.CROP].highlight
        root = ET.fromstring(svg)
        bars = [r for r in root if r.get("fill") == highlight]
        assert bars, "the 3x3 optimum grows bordered cane"
        # each block contributes a 152x18 top bar and an 18x152 left bar
        assert {(r.get("width"), r.get("height")) for r in bars} == {("152", "18"), ("18", "152")}

    def test_a_tiny_cell_still_gets_a_visible_border(self):
        """Rounding must not round the border away to nothing."""
        svg = render_layout_svg(optimize("...\n...\n...", crop=Sugarcane()), cell=4)
        assert 'height="1"' in svg

    @pytest.mark.parametrize("cell", [0, -1])
    def test_non_positive_cell_rejected(self, cell):
        with pytest.raises(ValueError, match="cell must be positive"):
            render_layout_svg(optimize(".", crop=Sugarcane()), cell=cell)

    def test_negative_gap_rejected(self):
        with pytest.raises(ValueError, match="gap must be non-negative"):
            render_layout_svg(optimize(".", crop=Sugarcane()), gap=-1)

    def test_zero_gap_is_allowed(self, rectangle):
        svg = render_layout_svg(optimize(rectangle(2, 2), crop=Sugarcane()), gap=0)
        assert f'viewBox="0 0 {33 * 2 + 152} {33 * 2 + 152}"' in svg
