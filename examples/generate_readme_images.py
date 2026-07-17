"""Generate the comparison images the README's Results section uses.

    python examples/generate_readme_images.py

Writes twenty-four files to ``assets/results/`` -- an SVG and a PNG for each of
the four sugarcane layouts, four more pairs for cactus and four for wheat. Re-run
it after anything
that could move the numbers (a change to the model, the baselines, or the
terrains) and commit whatever moves; the README quotes these figures in prose, so
a silent drift there is a lie in the README.

Why the images are generated and not drawn
------------------------------------------

Every layout here comes out of the actual solver and the actual baseline its
demo measures against -- ``baseline_stripes_1x2``, ``baseline_checkerboard`` and
``baseline_lattice``, imported, not reimplemented. Nothing is posed. If the 1x2 pattern in these
pictures looks worse than the optimum, that is because it *is* worse by exactly
the margin printed beside it, and running this file is how you check.

It cuts the other way too, and that is the more valuable half: on open ground the
cactus pair and the wheat pair each come out of those same functions and render
the *same picture twice*, because there the hand pattern already is the optimum.
A README that drew its own illustrations could not have been surprised by that.

PNGs are rendered with headless Chrome. That is not a dependency the project
declares -- it is a browser that happens to be installed, used because no
SVG->PNG tool (ImageMagick, Inkscape, rsvg-convert, cairosvg) was present and
none of them is worth adding for a dozen pictures. The SVGs are the real output and
need nothing; the PNGs exist only for places that will not render SVG.
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
from mcfarm_opt.io.svg import CACTUS_PALETTE, WHEAT_PALETTE

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "results"

TERRAIN_NAMES = ("with_obstacles", "rectangle_9x9")
"""The two the README compares. Named as they are in _shared.py -- the task that
asked for this called them "com_obstaculos" and "retangulo_9x9", from back when
the demo was one Portuguese file."""

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


RAGGED_14x10 = """\
...#....#..#..
.....#........
.......#.....#
..........#...
.......#......
.#...........#
......#.#....#
.........#.#..
......#....#.#
.......#......"""
"""A rocky 14x10, drawn to answer a question the small terrains cannot.

Why this is not in ``_shared.TERRAINS``
--------------------------------------

It illustrates the README; no demo solves it. Putting it in ``TERRAINS`` would
add a row to all three demos' summary tables, which is a real change to what they
claim and not one this picture needs. If it ever earns a place in the demos it
should move there, and the tables should move with it.

Where the rocks came from, which is the part that matters
--------------------------------------------------------

Not from taste. A hand-placed rock field is a hand-tuned result: nudge the rocks
until the solver wins big, publish the number, and the picture is an argument for
whatever it was built to argue. So the rule was fixed *before* the answer was
seen: 19 rocks -- 13.3% of 140 cells, the same fraction ``ragged`` has -- scattered
by ``random.Random(seed).sample``.

One draw would not have been enough either, and this is the trap worth naming.
The first draw taken (seed 0) scored +7.9%, and it looked like a fine result until
sixty draws showed it sitting in the top 15% of them. The spread runs from +0.0%
to +18.9%: publishing any single draw is publishing luck. So this is seed 10, and
it was chosen by rule -- the draw whose margin is the *median* of sixty, with ties
broken by the lowest seed. It is here to be typical, not to be flattering.

What sixty draws say
--------------------

That the field size, not the solver, was doing the talking. Cactus gains, over the
hand checkerboard, at 13.3% rock:

    30 cells (`ragged`)  median 0 cacti
    140 cells (this)     median 1 cactus,  +2.6%
    280 cells            median 4 cacti
    560 cells            median 10 cacti

The *absolute* win grows with area, at roughly a cactus per 60 cells. The
*percentage* does not -- it sits near +2.6% and stays there, because the crop
count grows with the field just as fast. So ``ragged``'s +14.3% was never the
solver doing well; it was a 30-cell field, where one cactus is 14% of the answer.
On 25 of those 60 draws the solver won nothing at all.

More rock does not rescue it either: the margin peaks near this density and falls
off both sides, to a median 0 at 5% (too few rocks to make the parity choice hurt)
and 0 again at 40% (so much rock that both layouts are starved alike).
"""

CACTUS_TERRAINS: tuple[tuple[str, str], ...] = (
    ("rectangle_9x9", TERRAINS["rectangle_9x9"]),
    ("ragged_14x10", RAGGED_14x10),
)
"""The two the README draws: the tie, and the exception to it.

``rectangle_9x9`` is the case the cactus demo is *about* -- open ground, where the
checkerboard is already the optimum and the solver returns the same picture.
``ragged_14x10`` is where it does not, because obstacles make the checkerboard's
global choice of colour wrong locally. One of each is the honest pair; showing
only the rocky one would advertise the exception as the rule.
"""


WHEAT_TERRAINS: tuple[tuple[str, str], ...] = (
    ("with_obstacles", WHEAT_DEMO_TERRAINS["with_obstacles"]),
    ("rubble", WHEAT_DEMO_TERRAINS["rubble"]),
)
"""The same pair of cases for wheat: the tie, and the exception to it.

``with_obstacles`` is the tie, and it is picked over the terrains that tie more
photogenically. ``rectangle_9x9`` would be the obvious choice and is worthless as
an illustration: one source hydrates the whole 9x9 and exactly one cell reaches
every other, so there is a single legal answer and the two *cannot* disagree. It
does not show a hand pattern matching a solver, it shows a problem with one move
in it. ``two_fields`` looks better and is the same trick four times over -- its
wall cross cuts the field into four 9x9 quadrants, each with that same forced
answer.

The 11x11 is a real tie: 9 rocks, four sources to place, and enough freedom that
the lattice and the solver arrive at *visibly different* layouts worth exactly the
same 108. That is what a tie looks like in a covering problem, and it is also the
field the sugarcane pictures above use -- same land, two rules, 75.0% against
96.4%.

``rubble`` is the only terrain in the wheat demo where the solver wins anything,
because 35% obstacles leave no spacing for a lattice to follow. It was built to be
hostile to the pattern, and the README says so rather than passing it off as
typical ground.
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


def main() -> None:
    """Solve both terrains, render both strategies for each, write the files."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    browser = find_browser()
    if browser is None:
        print("No Chromium-family browser found, so no PNGs will be written.")
        print("The SVGs below are the real output and are enough for the README;")
        print("install Chrome or Edge, or add cairosvg, if you need the PNGs.")
    else:
        print(f"Rasterising PNGs with: {browser}")
    print()

    rows: list[tuple[str, int, float, int, float, float]] = []

    for name in TERRAIN_NAMES:
        terrain = TERRAINS[name]
        grid = parse_grid(terrain)

        optimal = optimize(terrain, crop=Sugarcane(), solver="ilp")
        manual = baseline_stripes_1x2(grid)
        if manual is None:  # pragma: no cover - not true of these two terrains
            raise RuntimeError(f"the 1x2 pattern does not apply to {name}")

        for label, layout in (("1x2", manual), ("optimal", optimal)):
            write_pair(browser, f"{name}_{label}", render_layout_svg(layout))

        gain = 100.0 * (optimal.metrics.n_crop - manual.metrics.n_crop) / manual.metrics.n_crop
        rows.append(
            (
                name,
                manual.metrics.n_crop,
                manual.metrics.efficiency,
                optimal.metrics.n_crop,
                optimal.metrics.efficiency,
                gain,
            )
        )
        print()

    cactus_rows = write_comparisons(
        browser,
        crop=Cactus(),
        palette=CACTUS_PALETTE,
        hand=baseline_checkerboard,
        hand_label="checkerboard",
        terrains=CACTUS_TERRAINS,
    )
    wheat_rows = write_comparisons(
        browser,
        crop=Wheat(),
        palette=WHEAT_PALETTE,
        hand=baseline_lattice,
        hand_label="lattice",
        terrains=WHEAT_TERRAINS,
    )

    print("Numbers the README must quote, sugarcane (vs the 1x2 stripes):")
    print(f"  {'terrain':16} {'1x2':>12} {'optimal':>12} {'gain':>8}")
    print(f"  {'-' * 16} {'-' * 12} {'-' * 12} {'-' * 8}")
    for name, m_n, m_eff, o_n, o_eff, gain in rows:
        print(
            f"  {name:16} {f'{m_n} ({m_eff:.1f}%)':>12} "
            f"{f'{o_n} ({o_eff:.1f}%)':>12} {f'+{gain:.1f}%':>8}"
        )

    print()
    print("Numbers the README must quote, cactus (vs the checkerboard):")
    print(f"  {'terrain':16} {'checkerboard':>14} {'optimal':>12} {'gain':>8}")
    print(f"  {'-' * 16} {'-' * 14} {'-' * 12} {'-' * 8}")
    for name, h_n, h_eff, o_n, o_eff in cactus_rows:
        gain = 100.0 * (o_n - h_n) / h_n
        print(
            f"  {name:16} {f'{h_n} ({h_eff:.1f}%)':>14} "
            f"{f'{o_n} ({o_eff:.1f}%)':>12} {f'+{gain:.1f}%':>8}"
        )

    print()
    print("Numbers the README must quote, wheat (vs the 9-lattice):")
    print(f"  {'terrain':16} {'9-lattice':>14} {'optimal':>12} {'gain':>8}")
    print(f"  {'-' * 16} {'-' * 14} {'-' * 12} {'-' * 8}")
    for name, h_n, h_eff, o_n, o_eff in wheat_rows:
        gain = 100.0 * (o_n - h_n) / h_n
        print(
            f"  {name:16} {f'{h_n} ({h_eff:.1f}%)':>14} "
            f"{f'{o_n} ({o_eff:.1f}%)':>12} {f'+{gain:.1f}%':>8}"
        )

    print()
    print("Reminder: the 1x2 pattern is not the strongest thing a person does.")
    print("Run demo_sugarcane.py with RUN_ALL=True for the honest comparison")
    print("against a player who digs the water that pays best -- there the")
    print("solver's margin is single digits, not thirty percent.")


if __name__ == "__main__":
    sys.exit(main())
