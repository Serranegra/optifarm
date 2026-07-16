"""The demo is part of the deliverable, so it gets tested like one.

Two things here are worth more than "the script runs":

* every baseline must be a **legal** layout. If one counted cane without
  adjacent water it would flatter the hand pattern; if it pruned too much it
  would flatter optifarm. Either way the demo's headline comparison would be a
  lie, and nothing else in the suite would notice.
* the optimum must never lose to a baseline. A baseline is a feasible layout,
  so it is a lower bound on the optimum by construction -- if the solver ever
  came back under one, the model would be wrong.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from mcfarm_opt import BlockType, Grid, Sugarcane, optimize, parse_grid

DEMO_PATH = Path(__file__).resolve().parent.parent / "examples" / "demo.py"


def _load_demo():
    """Import examples/demo.py by path -- examples/ is not an installed package."""
    spec = importlib.util.spec_from_file_location("optifarm_demo", DEMO_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["optifarm_demo"] = module
    spec.loader.exec_module(module)
    return module


demo = _load_demo()

BASELINE_BUILDERS = [demo.baseline_checkerboard, demo.baseline_stripes_1x2]


def _cane_is_valid(layout, grid: Grid) -> bool:
    """Whether every cane in the layout has orthogonally adjacent water."""
    return all(
        any(layout.block_at(n) is BlockType.WATER for n in grid.neighbors(cell))
        for cell in grid.free_cells()
        if layout.block_at(cell) is BlockType.CROP
    )


class TestTerrains:
    def test_the_four_promised_terrains_exist(self):
        assert {"rectangle_9x9", "l_shape", "with_obstacles", "large_15x15"} <= set(demo.TERRAINS)

    @pytest.mark.parametrize("name", list(demo.TERRAINS))
    def test_every_terrain_parses(self, name):
        grid = parse_grid(demo.TERRAINS[name])
        assert len(list(grid.free_cells())) > 0

    def test_the_configured_terrain_is_a_real_key(self):
        """Guards against a typo in the one line the user is invited to edit."""
        assert demo.TERRAIN in demo.TERRAINS

    def test_with_obstacles_actually_has_obstacles(self):
        grid = parse_grid(demo.TERRAINS["with_obstacles"])
        assert len(list(grid.obstacles())) > 0


class TestBaselinesAreLegal:
    @pytest.mark.parametrize("build", BASELINE_BUILDERS)
    @pytest.mark.parametrize("name", list(demo.TERRAINS))
    def test_baseline_obeys_the_sugarcane_rule(self, name, build):
        grid = parse_grid(demo.TERRAINS[name])
        layout = build(grid)
        assert layout is not None
        assert _cane_is_valid(layout, grid), f"{build.__name__} on {name} has cane with no water"

    @pytest.mark.parametrize("build", BASELINE_BUILDERS)
    @pytest.mark.parametrize("name", list(demo.TERRAINS))
    def test_baseline_respects_obstacles(self, name, build):
        grid = parse_grid(demo.TERRAINS[name])
        layout = build(grid)
        assert all(layout.block_at(c) is BlockType.OBSTACLE for c in grid.obstacles())
        assert all(layout.block_at(c) is not BlockType.OBSTACLE for c in grid.free_cells())

    @pytest.mark.parametrize("build", BASELINE_BUILDERS)
    def test_baseline_metrics_match_the_rendered_grid(self, build):
        grid = parse_grid(demo.TERRAINS["with_obstacles"])
        layout = build(grid)
        assert layout.metrics.n_crop == len(layout.cells_with(BlockType.CROP))
        assert layout.metrics.n_support == len(layout.cells_with(BlockType.WATER))
        assert layout.metrics.n_free + layout.metrics.n_obstacle == len(grid)

    @pytest.mark.parametrize("build", BASELINE_BUILDERS)
    def test_baseline_is_not_claimed_to_be_optimal(self, build):
        """A hand pattern is not a proof. Saying OPTIMAL would be a lie."""
        assert not build(parse_grid(demo.TERRAINS["rectangle_9x9"])).metrics.is_optimal

    @pytest.mark.parametrize("build", BASELINE_BUILDERS)
    def test_pruning_removes_cane_stranded_by_an_obstacle(self, build):
        """A '#' eating the water must strand the cane beside it, not leave an
        illegal layout behind."""
        grid = parse_grid("...\n###\n...")
        layout = build(grid)
        if layout is not None:
            assert _cane_is_valid(layout, grid)


class TestBaselinesAreFair:
    """Each baseline must be the best its pattern can do, not a strawman."""

    def test_stripes_pick_the_best_offset(self):
        """On a 9x9 the offsets give 54 and 45; the baseline must report 54.

        Comparing the optimum against the worst offset would inflate optifarm's
        win for free.
        """
        grid = parse_grid(demo.TERRAINS["rectangle_9x9"])
        assert demo.baseline_stripes_1x2(grid).metrics.n_crop == 54

    def test_stripes_land_on_two_thirds(self):
        """1x2 is two rows of cane per row of water: 66.7% on open ground."""
        grid = parse_grid(demo.TERRAINS["rectangle_9x9"])
        assert demo.baseline_stripes_1x2(grid).metrics.efficiency == pytest.approx(66.7, abs=0.1)

    def test_checkerboard_picks_the_majority_colour(self):
        """A 9x9 splits 41/40, so the cane goes on the 41-cell colour."""
        grid = parse_grid(demo.TERRAINS["rectangle_9x9"])
        assert demo.baseline_checkerboard(grid).metrics.n_crop == 41

    def test_checkerboard_lands_on_half(self):
        """Every other cell is water, so it cannot exceed ~50% by construction."""
        grid = parse_grid(demo.TERRAINS["rectangle_9x9"])
        assert demo.baseline_checkerboard(grid).metrics.efficiency == pytest.approx(50.6, abs=0.1)

    def test_checkerboard_never_strands_cane_on_open_ground(self):
        """Its whole trade: every cane gets four water neighbours, so nothing is
        ever pruned -- which is exactly why it wastes half the terrain."""
        grid = parse_grid(demo.TERRAINS["rectangle_9x9"])
        assert demo.baseline_checkerboard(grid).metrics.n_empty == 0

    def test_stripes_beat_the_checkerboard_on_open_ground(self):
        """The ordering the demo's narrative depends on: 2/3 beats 1/2."""
        grid = parse_grid(demo.TERRAINS["rectangle_9x9"])
        assert (
            demo.baseline_stripes_1x2(grid).metrics.n_crop
            > demo.baseline_checkerboard(grid).metrics.n_crop
        )

    @pytest.mark.parametrize("build", BASELINE_BUILDERS)
    @pytest.mark.parametrize("name", list(demo.TERRAINS))
    def test_optimum_never_loses_to_a_baseline(self, name, build):
        grid = parse_grid(demo.TERRAINS[name])
        layout = build(grid)
        optimal = optimize(demo.TERRAINS[name], crop=Sugarcane(), time_limit=30.0)
        assert optimal.metrics.n_crop >= layout.metrics.n_crop


class TestGracefulDegradation:
    @pytest.mark.parametrize("build", BASELINE_BUILDERS)
    @pytest.mark.parametrize("terrain", ["###\n###", ".", "#", "#.#"])
    def test_baseline_returns_none_instead_of_crashing(self, terrain, build):
        """Terrains where a pattern grows nothing must degrade, not raise.

        A single cell has no neighbour to water it; a fully blocked grid has no
        cells at all. Both are None, not an exception.
        """
        assert build(parse_grid(terrain)) is None

    def test_a_1x2_terrain_is_not_degenerate(self):
        """The narrowest terrain the patterns *do* fit: one water, one cane."""
        assert demo.baseline_stripes_1x2(parse_grid("..")).metrics.n_crop == 1
        assert demo.baseline_checkerboard(parse_grid("..")).metrics.n_crop == 1

    def test_comparison_handles_a_missing_baseline(self, capsys):
        optimal = optimize("...\n...", crop=Sugarcane())
        demo.print_comparison(optimal, [("Checkerboard", None)])
        assert "does not apply" in capsys.readouterr().out

    def test_arrow_falls_back_when_the_terminal_cannot_encode_it(self):
        """The Windows console is cp1252, which has no U+2192."""
        assert demo._arrow() in {"→", "->"}


class TestOutput:
    def test_running_one_terrain_prints_terrain_layouts_and_comparison(self, capsys):
        demo.run_one("l_shape")
        out = capsys.readouterr().out
        assert "Input" in out
        assert "Optimal layout from optifarm" in out
        assert "Metrics" in out
        assert "efficiency" in out
        assert "Checkerboard:" in out
        assert "1x2 stripes:" in out
        assert "Optimal (optifarm):" in out

    def test_every_baseline_is_rendered(self, capsys):
        demo.run_one("rectangle_9x9")
        out = capsys.readouterr().out
        assert "Checkerboard by hand" in out
        assert "1x2 stripes by hand" in out

    def test_main_runs_end_to_end(self, capsys):
        demo.main()
        assert "cane" in capsys.readouterr().out

    def test_summary_table_covers_every_terrain_and_baseline(self, capsys, monkeypatch):
        # Skip the 15x15 here: it costs ~12s and the other terrains prove the
        # table renders. Its numbers are covered by the tests above.
        monkeypatch.setattr(
            demo, "TERRAINS", {k: v for k, v in demo.TERRAINS.items() if k != "large_15x15"}
        )
        demo.run_all()
        out = capsys.readouterr().out
        assert "rectangle_9x9" in out and "l_shape" in out and "with_obstacles" in out
        assert "Checkerboard" in out and "1x2 stripes" in out
        assert "vs check" in out and "vs 1x2" in out
