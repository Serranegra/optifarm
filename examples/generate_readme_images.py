"""Generate the comparison images the README's Results section uses.

    python examples/generate_readme_images.py

Writes eighteen files to ``assets/results/``, in two groups. Six are the
open-ground pattern comparisons -- an SVG and a PNG of the hand pattern and of the
optimum, one field per crop. Twelve are the obstacle showcase -- sugarcane and
cactus, optimum only, on three terrains a real farm has. Re-run it after anything
that could move the numbers (a change to the model, the baselines, or the
terrains) and commit whatever moves; the README quotes these figures in prose, so
a silent drift there is a lie in the README.

Why the images are generated and not drawn
------------------------------------------

Every layout here comes out of the actual solver and, where a pattern is drawn,
the actual baseline its demo measures against -- ``baseline_stripes_1x2``,
``baseline_checkerboard`` and ``baseline_lattice``, imported, not reimplemented.
Nothing is posed. If a hand pattern in these pictures looks worse than the
optimum, that is because it *is* worse by exactly the margin printed beside it,
and running this file is how you check.

It cuts the other way too, and that is the more valuable half: on open ground the
cactus pair renders the *same picture twice*, because there the checkerboard
already is the optimum. A README that drew its own illustrations could not have
been surprised by that.

PNGs are rendered with headless Chrome. That is not a dependency the project
declares -- it is a browser that happens to be installed, used because no
SVG->PNG tool (ImageMagick, Inkscape, rsvg-convert, cairosvg) was present and
none of them is worth adding for a dozen-odd pictures. The SVGs are the real
output and need nothing; the PNGs exist only for places that will not render SVG.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from _shared import TERRAINS
from demo_cactus import baseline_checkerboard
from demo_sugarcane import baseline_stripes_1x2
from demo_wheat import TERRAINS as WHEAT_DEMO_TERRAINS
from demo_wheat import baseline_lattice

from mcfarm_opt import (
    Cactus,
    FarmLayout,
    Grid,
    Sugarcane,
    Wheat,
    optimize,
    parse_grid,
    render_layout_svg,
)
from mcfarm_opt.crops.base import CropRule
from mcfarm_opt.io.svg import CACTUS_PALETTE, PALETTE, WHEAT_PALETTE

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "results"

PNG_LONG_SIDE = 512
"""Longest side of the exported PNGs, in pixels. The SVGs are resolution-free;
this only matters for renderers that cannot read them."""

CHROME_CANDIDATES = (
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def find_browser() -> str | None:
    """Locate a Chromium-family browser to rasterise with, or None."""
    for name in ("chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def svg_size(svg: str) -> tuple[int, int]:
    """Read the viewBox back out of a rendered SVG.

    Asking the document rather than recomputing from the grid keeps the PNG in
    step with the SVG even if the renderer's spacing constants change.
    """
    match = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    if not match:
        raise ValueError("rendered SVG has no viewBox; cannot size the PNG")
    return int(match.group(1)), int(match.group(2))


def write_png(browser: str, svg_path: Path, png_path: Path, svg: str) -> None:
    """Rasterise one SVG, preserving its aspect ratio."""
    width, height = svg_size(svg)
    scale = PNG_LONG_SIDE / max(width, height)
    out_w, out_h = round(width * scale), round(height * scale)

    # Size the SVG in absolute pixels, anchored top-left -- *not* 100vw/100vh.
    # Chrome clamps the layout viewport to a minimum width, so a portrait image
    # asking for a 390px-wide window lays out in a wider one, and the SVG then
    # centres itself in that extra space: the screenshot, which does honour the
    # requested width, catches a white strip on the left and loses a column on
    # the right. Pinning the element to out_w x out_h makes the clamp harmless,
    # because the crop the screenshot takes is exactly the box the SVG fills.
    html = svg_path.with_suffix(".html")
    html.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        "html,body{margin:0;padding:0;background:none}"
        f"svg{{display:block;position:absolute;top:0;left:0;width:{out_w}px;height:{out_h}px}}"
        f"</style></head><body>{svg}</body></html>",
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--screenshot={png_path}",
                f"--window-size={out_w},{out_h}",
                html.as_uri(),
            ],
            capture_output=True,
            check=False,
            timeout=120,
        )
    finally:
        html.unlink(missing_ok=True)

    if not png_path.exists():
        raise RuntimeError(f"{browser} produced no PNG for {svg_path.name}")


def write_pair(browser: str | None, name: str, svg: str) -> None:
    """Write ``name.svg``, and ``name.png`` beside it if there is a browser."""
    svg_path = OUT_DIR / f"{name}.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(f"  wrote {svg_path.relative_to(ROOT)}")

    if browser is not None:
        png_path = svg_path.with_suffix(".png")
        write_png(browser, svg_path, png_path, svg)
        print(f"  wrote {png_path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# The two halves of the Results section
# ---------------------------------------------------------------------------
# There are two distinct claims to illustrate, and they need different pictures.
#
# On *open, symmetric* ground a hand pattern is a fair opponent -- 1x2 stripes, a
# checkerboard and a 9-lattice are exactly what a player stamps across an empty
# field, and putting the optimum beside one is an honest comparison. That is the
# first half, one open field per crop.
#
# The moment the ground stops being open there is no pattern to stamp: you cannot
# run stripes through a house or a checkerboard around a pond. So on obstacle
# terrain a pattern-vs-solver picture is the wrong comparison twice over -- it is
# unfair to the pattern (it was never built for that ground) and it flatters the
# solver (beating a crippled template proves nothing). The honest thing to show
# there is just the solver's answer, on obstacles a real farm actually has. That
# is the second half, and it draws no hand pattern at all.


def _house(size: int, wall: int) -> str:
    """An open ``size`` x ``size`` field with a solid ``wall`` x ``wall`` house centred in it."""
    lo = (size - wall) // 2
    return "\n".join(
        "".join("#" if lo <= r < lo + wall and lo <= c < lo + wall else "." for c in range(size))
        for r in range(size)
    )


def _disc(size: int, radius: float, *, obstacle_inside: bool) -> str:
    """A ``size`` x ``size`` field split by a disc of ``radius`` at its centre.

    ``obstacle_inside`` chooses which side is rock: True digs a round pond out of
    open ground; False makes the plantable field itself a circle, walling off
    everything outside it.
    """
    centre = (size - 1) / 2
    inside, outside = ("#", ".") if obstacle_inside else (".", "#")
    return "\n".join(
        "".join(
            inside if (r - centre) ** 2 + (c - centre) ** 2 <= radius**2 else outside
            for c in range(size)
        )
        for r in range(size)
    )


HOUSE = _house(15, 5)
"""15x15 open ground with a 5x5 building planted in the middle -- a farm with a
house in it, which most farms have."""

POND = _disc(15, 3.5, obstacle_inside=True)
"""15x15 open ground with a round pond dug out of the centre."""

ROUND_FIELD = _disc(15, 7, obstacle_inside=False)
"""A circular plot: a disc of soil in a 15x15 box, walled off outside it. The
boundary no rectangular pattern can follow."""

SHOWCASE_TERRAINS: tuple[tuple[str, str], ...] = (
    ("house", HOUSE),
    ("pond", POND),
    ("round_field", ROUND_FIELD),
)
"""The meaningful obstacles the README shows the optimiser solving.

Deliberately not random scatters. A random rockfield is the wrong thing to put a
pattern against (unfair) and the wrong thing to show the solver on (the rocks look
arbitrary). A house, a pond and a circular plot are obstacles a real farm has, and
they are where fitting the crop to the terrain -- with no template to fall back on
-- is the whole job. No hand pattern is drawn beside them, because none applies;
the comparison the pictures invite is between the two crops on identical ground.

Like ``RAGGED`` before them these live here, not in ``_shared.TERRAINS``, because
they illustrate the README and no demo solves them.
"""


def write_comparisons(
    browser: str | None,
    *,
    crop: CropRule,
    palette: dict,
    hand: Callable[[Grid], FarmLayout | None],
    hand_label: str,
    terrains: tuple[tuple[str, str], ...],
) -> list[tuple[str, int, float, int, float]]:
    """Draw a crop's hand pattern against its proven optimum, on each terrain.

    One function for cactus and wheat because the picture is the same argument
    twice: stamp what a person builds, solve what is provable, render both
    through the same style, and let the pair speak. The hand builders come from
    the demos -- this file must not grow its own idea of what a person would do,
    or the images would stop agreeing with the tables.

    Args:
        browser: rasteriser for the PNGs, or None for SVGs only.
        crop: the rule to optimise for.
        palette: the crop's dress of the house style.
        hand: the demo's baseline builder.
        hand_label: what to call it in the filename.
        terrains: ``(name, terrain)`` pairs to draw.

    Returns:
        One ``(terrain, hand n, hand %, optimal n, optimal %)`` row per terrain,
        for the table :func:`main` prints at the end.
    """
    rows: list[tuple[str, int, float, int, float]] = []

    for name, terrain in terrains:
        grid = parse_grid(terrain)

        optimal = optimize(terrain, crop=crop, solver="ilp")
        built = hand(grid)
        if built is None:  # pragma: no cover - both patterns grow on both terrains
            raise RuntimeError(f"the {hand_label} grows no {crop.name} on {name}")

        for label, layout in ((hand_label, built), ("optimal", optimal)):
            svg = render_layout_svg(layout, palette=palette)
            write_pair(browser, f"{crop.name}_{name}_{label}", svg)

        if built.render() == optimal.render():
            # The two SVGs still differ by one line -- the comment naming which
            # of the two produced it. Every rect is identical, so the PNGs come
            # out byte for byte the same file, which is the point of the pair.
            print("  the hand pattern and the optimum are the same layout. That is the result.")
        rows.append(
            (
                name,
                built.metrics.n_crop,
                built.metrics.efficiency,
                optimal.metrics.n_crop,
                optimal.metrics.efficiency,
            )
        )
        print()

    return rows


def write_showcase(
    browser: str | None,
    terrains: tuple[tuple[str, str], ...],
) -> list[tuple[str, str, int, float, int]]:
    """Draw each crop's proven optimum on obstacle terrain -- and nothing else.

    No hand pattern, on purpose: these are the terrains where a pattern does not
    apply, so there is nothing legitimate to put beside the optimum. Both shipped
    crops are drawn on identical ground instead, because *that* is the comparison
    worth making here -- sugarcane threading water around the house, cactus holding
    a one-cell moat from it, on the same field.

    Returns:
        One ``(terrain, crop, n_crop, efficiency, n_free)`` row per crop per
        terrain, for the table :func:`main` prints at the end.
    """
    rows: list[tuple[str, str, int, float, int]] = []

    for name, terrain in terrains:
        for crop, palette in ((Sugarcane(), PALETTE), (Cactus(), CACTUS_PALETTE)):
            optimal = optimize(terrain, crop=crop, solver="ilp")
            svg = render_layout_svg(optimal, palette=palette)
            write_pair(browser, f"{crop.name}_{name}_optimal", svg)
            rows.append(
                (
                    name,
                    crop.name,
                    optimal.metrics.n_crop,
                    optimal.metrics.efficiency,
                    optimal.metrics.n_free,
                )
            )
        print()

    return rows


def _print_comparison_table(title: str, hand_col: str, rows) -> None:
    """One 'Numbers the README must quote' block for a pattern-vs-optimum run."""
    print(title)
    print(f"  {'terrain':16} {hand_col:>14} {'optimal':>12} {'gain':>8}")
    print(f"  {'-' * 16} {'-' * 14} {'-' * 12} {'-' * 8}")
    for name, h_n, h_eff, o_n, o_eff in rows:
        gain = 100.0 * (o_n - h_n) / h_n
        print(
            f"  {name:16} {f'{h_n} ({h_eff:.1f}%)':>14} "
            f"{f'{o_n} ({o_eff:.1f}%)':>12} {f'+{gain:.1f}%':>8}"
        )
    print()


def main() -> None:
    """Draw the open-ground pattern comparisons, then the obstacle showcase."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    browser = find_browser()
    if browser is None:
        print("No Chromium-family browser found, so no PNGs will be written.")
        print("The SVGs below are the real output and are enough for the README;")
        print("install Chrome or Edge, or add cairosvg, if you need the PNGs.")
    else:
        print(f"Rasterising PNGs with: {browser}")
    print()

    # --- First half: on open ground, the popular pattern against the optimum.
    # One field per crop; wheat needs a 15x15 because its reach swallows a 9x9.
    sugar_rows = write_comparisons(
        browser,
        crop=Sugarcane(),
        palette=PALETTE,
        hand=baseline_stripes_1x2,
        hand_label="1x2",
        terrains=(("rectangle_9x9", TERRAINS["rectangle_9x9"]),),
    )
    cactus_rows = write_comparisons(
        browser,
        crop=Cactus(),
        palette=CACTUS_PALETTE,
        hand=baseline_checkerboard,
        hand_label="checkerboard",
        terrains=(("rectangle_9x9", TERRAINS["rectangle_9x9"]),),
    )
    wheat_rows = write_comparisons(
        browser,
        crop=Wheat(),
        palette=WHEAT_PALETTE,
        hand=baseline_lattice,
        hand_label="lattice",
        terrains=(("large_15x15", WHEAT_DEMO_TERRAINS["large_15x15"]),),
    )

    # --- Second half: the solver alone, on obstacles a real farm has.
    showcase_rows = write_showcase(browser, SHOWCASE_TERRAINS)

    _print_comparison_table(
        "Numbers the README must quote, sugarcane (vs the 1x2 stripes):", "1x2", sugar_rows
    )
    _print_comparison_table(
        "Numbers the README must quote, cactus (vs the checkerboard):", "checkerboard", cactus_rows
    )
    _print_comparison_table(
        "Numbers the README must quote, wheat (vs the 9-lattice):", "9-lattice", wheat_rows
    )

    print("Numbers the README must quote, obstacle showcase (solver only):")
    print(f"  {'terrain':14} {'crop':10} {'crop':>8} {'efficiency':>12} {'free':>6}")
    print(f"  {'-' * 14} {'-' * 10} {'-' * 8} {'-' * 12} {'-' * 6}")
    for name, crop, n_crop, eff, n_free in showcase_rows:
        print(f"  {name:14} {crop:10} {n_crop:>8} {f'{eff:.1f}%':>12} {n_free:>6}")

    print()
    print("Reminder: the pattern is not the strongest thing a person does, and on")
    print("open ground a thinking player comes within single digits of the optimum.")
    print("Run each demo with RUN_ALL=True for that honest comparison.")


if __name__ == "__main__":
    sys.exit(main())
