"""Generate the comparison images the README's Results section uses.

    python examples/generate_readme_images.py

Writes eight files to ``assets/results/`` -- an SVG and a PNG for each of the
four layouts. Re-run it after anything that could move the numbers (a change to
the model, the baselines, or the terrains) and commit whatever moves; the README
quotes these figures in prose, so a silent drift there is a lie in the README.

Why the images are generated and not drawn
------------------------------------------

Every layout here comes out of the actual solver and the actual baseline the
sugarcane demo measures against. Nothing is posed. If the 1x2 pattern in these
pictures looks worse than the optimum, that is because it *is* worse by exactly
the margin printed beside it, and running this file is how you check.

PNGs are rendered with headless Chrome. That is not a dependency the project
declares -- it is a browser that happens to be installed, used because no
SVG->PNG tool (ImageMagick, Inkscape, rsvg-convert, cairosvg) was present and
none of them is worth adding for four pictures. The SVGs are the real output and
need nothing; the PNGs exist only for places that will not render SVG.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from _shared import TERRAINS
from demo_sugarcane import baseline_stripes_1x2

from mcfarm_opt import Sugarcane, optimize, parse_grid, render_layout_svg

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

    html = svg_path.with_suffix(".html")
    html.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        "html,body{margin:0;padding:0}svg{display:block;width:100vw;height:100vh}"
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
            svg = render_layout_svg(layout)
            svg_path = OUT_DIR / f"{name}_{label}.svg"
            svg_path.write_text(svg, encoding="utf-8")
            print(f"  wrote {svg_path.relative_to(ROOT)}")

            if browser is not None:
                png_path = svg_path.with_suffix(".png")
                write_png(browser, svg_path, png_path, svg)
                print(f"  wrote {png_path.relative_to(ROOT)}")

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

    print("Numbers the README must quote:")
    print(f"  {'terrain':16} {'1x2':>12} {'optimal':>12} {'gain':>8}")
    print(f"  {'-' * 16} {'-' * 12} {'-' * 12} {'-' * 8}")
    for name, m_n, m_eff, o_n, o_eff, gain in rows:
        print(
            f"  {name:16} {f'{m_n} ({m_eff:.1f}%)':>12} "
            f"{f'{o_n} ({o_eff:.1f}%)':>12} {f'+{gain:.1f}%':>8}"
        )

    print()
    print("Reminder: the 1x2 pattern is not the strongest thing a person does.")
    print("Run demo_sugarcane.py with RUN_ALL=True for the honest comparison")
    print("against a player who digs the water that pays best -- there the")
    print("solver's margin is single digits, not thirty percent.")


if __name__ == "__main__":
    sys.exit(main())
