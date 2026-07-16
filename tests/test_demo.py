"""The demos are part of the deliverable, so they get tested like one.

Three things here are worth more than "the scripts run":

* every baseline must be a **legal** layout under its own crop's rule. A
  baseline claiming crop it cannot grow would flatter the hand pattern; one
  pruning too much would flatter optifarm. Either way the comparison in the
  README would be a lie, and nothing else in the suite would notice. The
  validators from ``conftest`` do this job -- the same ones that check the
  solver's output, pointed at hand-built layouts.
* the optimum must never lose to a baseline. A baseline is a feasible layout, so
  it is a lower bound on the optimum by construction.
* the cactus demo's headline is that the checkerboard **ties** the optimum on
  open ground. That +0.0% is the whole lesson, so it is pinned here: if it ever
  drifts, either the claim or the model is wrong.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from mcfarm_opt import BlockType, Cactus, Sugarcane, optimize, parse_grid

from .conftest import assert_valid_cactus, assert_valid_sugarcane

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# The demos do `from _shared import ...`, which resolves because sys.path[0] is
# examples/ when you run them directly. Loading them from here needs the same.
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))


def _load(module_name: str):
    """Import an examples/*.py by path -- examples/ is not an installed package."""
    spec = importlib.util.spec_from_file_location(
        f"optifarm_{module_name}", EXAMPLES_DIR / f"{module_name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"optifarm_{module_name}"] = module
    spec.loader.exec_module(module)
    return module


# Plain import, not _load: the demos themselves do `from _shared import ...`,
# which resolves through sys.path to the module cached as "_shared". Loading a
# second copy under another name would give the tests a different TERRAINS
# object than the demos actually use, and monkeypatching it would silently
# no-op.
import _shared as shared  # noqa: E402

cane_demo = _load("demo_sugarcane")
cactus_demo = _load("demo_cactus")

TERRAIN_NAMES = list(shared.TERRAINS)


class TestSharedTerrains:
    def test_the_promised_terrains_exist(self):
        assert {
            "rectangle_9x9",
            "l_shape",
            "with_obstacles",
            "ragged",
            "large_15x15",
        } <= set(shared.TERRAINS)

    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_every_terrain_parses_and_has_room(self, name):
        assert len(list(parse_grid(shared.TERRAINS[name]).free_cells())) > 0

    @pytest.mark.parametrize("name", ["with_obstacles", "ragged", "l_shape"])
    def test_the_rocky_terrains_actually_have_obstacles(self, name):
        assert len(list(parse_grid(shared.TERRAINS[name]).obstacles())) > 0

    @pytest.mark.parametrize("demo", [cane_demo, cactus_demo])
    def test_the_configured_terrain_is_a_real_key(self, demo):
        """Guards against a typo in the one line each demo invites you to edit."""
        assert demo.TERRAIN in shared.TERRAINS

    def test_both_demos_solve_the_same_land(self):
        """The terrains are shared on purpose: it is what makes cane and cactus
        comparable on identical ground."""
        assert cane_demo.TERRAINS is cactus_demo.TERRAINS is shared.TERRAINS


class TestEachDemoFixesItsCrop:
    """The old single demo had a CROP knob that silently produced nonsense when
    set to a crop its baselines did not match. Each demo now fixes its own."""

    def test_sugarcane_demo_grows_sugarcane(self):
        assert isinstance(cane_demo.CROP, Sugarcane)

    def test_cactus_demo_grows_cactus(self):
        assert isinstance(cactus_demo.CROP, Cactus)


class TestBaselinesLeaveNothingOnTheTable:
    """A baseline must be *maximal*: no free cell left bare that could be planted.

    This is the strawman that is easiest to build by accident. Stamp a pattern,
    prune what broke, and walk away -- and the holes the prune left are free
    production a real player would have taken. Beating that baseline proves
    nothing about the solver and everything about the baseline.

    These tests assert the property directly on the finished layouts, for both
    crops, so neither demo can regress into flattering its own optimiser.
    """

    @pytest.mark.parametrize(
        "build",
        [
            cane_demo.baseline_checkerboard,
            cane_demo.baseline_stripes_1x2,
            cane_demo.baseline_greedy_water,
        ],
    )
    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_no_bare_cell_could_hold_more_cane(self, name, build):
        """Nothing empty has water beside it.

        For sugarcane this holds by construction -- a cell is only empty because
        the prune found it had no adjacent water, which is exactly what planting
        needs -- so the demo does no fill at all. This test is what keeps that
        argument true if the patterns ever change.
        """
        grid = parse_grid(shared.TERRAINS[name])
        layout = build(grid)
        for cell in grid.free_cells():
            if layout.block_at(cell) is BlockType.EMPTY:
                assert not any(
                    layout.block_at(n) is BlockType.WATER for n in grid.neighbors(cell)
                ), f"{build.__name__} on {name} left cane unplanted next to water at {cell}"

    @pytest.mark.parametrize(
        "build", [cactus_demo.baseline_checkerboard, cactus_demo.baseline_greedy]
    )
    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_no_bare_cell_could_hold_more_cactus(self, name, build):
        """Nothing empty is free of solid neighbours.

        Cactus does need a real fill: a pruned wall-hugger leaves a hole whose
        neighbours may all be bare, and a player would plant there. Without the
        fill the checkerboard scored 6 on `ragged` instead of 7, and the demo
        claimed a +33.3% win it had not earned.
        """
        grid = parse_grid(shared.TERRAINS[name])
        layout = build(grid)
        for cell in grid.free_cells():
            if layout.block_at(cell) is BlockType.EMPTY:
                blocked = any(
                    grid.is_obstacle(n) or layout.block_at(n) is BlockType.CROP
                    for n in grid.neighbors(cell)
                )
                assert blocked, (
                    f"{build.__name__} on {name} left {cell} bare with nothing solid "
                    f"beside it -- a player would have planted there"
                )


class TestSugarcaneBaselines:
    BUILDERS = [
        cane_demo.baseline_checkerboard,
        cane_demo.baseline_stripes_1x2,
        cane_demo.baseline_greedy_water,
    ]

    @pytest.mark.parametrize("build", BUILDERS)
    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_baseline_is_a_legal_sugarcane_layout(self, name, build):
        layout = build(parse_grid(shared.TERRAINS[name]))
        assert layout is not None
        assert_valid_sugarcane(layout)

    @pytest.mark.parametrize("build", BUILDERS)
    def test_baseline_is_not_claimed_optimal(self, build):
        assert not build(parse_grid(shared.TERRAINS["rectangle_9x9"])).metrics.is_optimal

    def test_stripes_pick_the_best_offset(self):
        """On a 9x9 the offsets give 54 and 45; the baseline must report 54.

        Comparing against the worst offset would inflate optifarm's win for free.
        """
        grid = parse_grid(shared.TERRAINS["rectangle_9x9"])
        assert cane_demo.baseline_stripes_1x2(grid).metrics.n_crop == 54

    def test_stripes_land_on_two_thirds(self):
        grid = parse_grid(shared.TERRAINS["rectangle_9x9"])
        assert cane_demo.baseline_stripes_1x2(grid).metrics.efficiency == pytest.approx(
            66.7, abs=0.1
        )

    def test_stripes_beat_the_checkerboard_on_open_ground(self):
        """The ordering the demo's narrative depends on: 2/3 beats 1/2."""
        grid = parse_grid(shared.TERRAINS["rectangle_9x9"])
        assert (
            cane_demo.baseline_stripes_1x2(grid).metrics.n_crop
            > cane_demo.baseline_checkerboard(grid).metrics.n_crop
        )

    @pytest.mark.parametrize("build", BUILDERS)
    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_optimum_never_loses(self, name, build):
        grid = parse_grid(shared.TERRAINS[name])
        optimal = optimize(shared.TERRAINS[name], crop=Sugarcane(), time_limit=30.0)
        assert optimal.metrics.n_crop >= build(grid).metrics.n_crop

    def test_the_solver_always_beats_the_patterns(self):
        """The sugarcane demo's first claim: hand patterns lose, everywhere."""
        for name in TERRAIN_NAMES:
            grid = parse_grid(shared.TERRAINS[name])
            optimal = optimize(shared.TERRAINS[name], crop=Sugarcane(), time_limit=30.0)
            stripes = cane_demo.baseline_stripes_1x2(grid)
            assert optimal.metrics.n_crop > stripes.metrics.n_crop, name

    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_greedy_water_beats_every_pattern(self, name):
        """A player who follows no pattern beats the ones who do.

        This is why the demo cannot stop at "the patterns lose by 30%": the
        patterns are not the best a person does, so beating them is mostly a
        fact about patterns.
        """
        grid = parse_grid(shared.TERRAINS[name])
        greedy = cane_demo.baseline_greedy_water(grid).metrics.n_crop
        assert greedy > cane_demo.baseline_stripes_1x2(grid).metrics.n_crop
        assert greedy > cane_demo.baseline_checkerboard(grid).metrics.n_crop

    def test_the_solvers_real_margin_over_a_thinking_player_is_single_digits(self):
        """The sugarcane demo's honest headline, pinned.

        Against the patterns the solver wins 13-31%. Against a greedy player it
        wins 4-7% -- and on ragged, nothing. If this ever widens, the demo's
        claim that the prize is single digits is wrong and must be rewritten.
        """
        for name in TERRAIN_NAMES:
            grid = parse_grid(shared.TERRAINS[name])
            greedy = cane_demo.baseline_greedy_water(grid).metrics.n_crop
            optimal = optimize(shared.TERRAINS[name], crop=Sugarcane(), time_limit=30.0)
            gain = 100.0 * (optimal.metrics.n_crop - greedy) / greedy
            assert 0.0 <= gain < 10.0, f"{name}: solver is {gain:.1f}% over greedy"

    def test_greedy_water_ties_the_optimum_on_ragged(self):
        """Even for sugarcane, there is a terrain where thinking is enough."""
        grid = parse_grid(shared.TERRAINS["ragged"])
        assert cane_demo.baseline_greedy_water(grid).metrics.n_crop == 18
        assert optimize(shared.TERRAINS["ragged"], crop=Sugarcane()).metrics.n_crop == 18

    def test_a_naive_sweep_would_just_be_a_checkerboard(self):
        """Why the demo has no "naive sweep" baseline.

        Walk the field planting cane where water already sits and digging where
        it does not, and the alternation propagates into a checkerboard at
        whichever parity the corner forced -- scoring 40 against the
        checkerboard baseline's 41. It is not a distinct strategy, it is the
        same one denied its choice of colour, so adding it would mean adding a
        deliberately worse-aligned copy of a row already in the table.
        """
        grid = parse_grid(shared.TERRAINS["rectangle_9x9"])
        cane, water = set(), set()
        for cell in grid.free_cells():  # row-major sweep
            if any(n in water for n in grid.neighbors(cell)):
                cane.add(cell)
            else:
                water.add(cell)
        # It lands on the board's colours, one cell short of the best parity.
        assert len(cane) == 40
        assert cane_demo.baseline_checkerboard(grid).metrics.n_crop == 41
        assert {(c.row + c.col) % 2 for c in cane} == {1}


class TestCactusBaselines:
    BUILDERS = [cactus_demo.baseline_checkerboard, cactus_demo.baseline_greedy]

    @pytest.mark.parametrize("build", BUILDERS)
    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_baseline_is_a_legal_cactus_layout(self, name, build):
        layout = build(parse_grid(shared.TERRAINS[name]))
        assert layout is not None
        assert_valid_cactus(layout)

    @pytest.mark.parametrize("build", BUILDERS)
    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_baseline_places_no_water(self, name, build):
        """A cactus farm has no water. This is the bug the old CROP knob had."""
        layout = build(parse_grid(shared.TERRAINS[name]))
        assert layout.metrics.n_support == 0
        assert set(layout.render()) <= {"C", ".", "#", "\n"}

    @pytest.mark.parametrize("build", BUILDERS)
    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_no_two_cacti_touch_in_a_hand_layout(self, name, build):
        """The prune only removes wall-huggers, which is only correct because
        neither strategy ever plants two cacti side by side. Checked, not
        trusted -- and the fill is the step that could break it."""
        grid = parse_grid(shared.TERRAINS[name])
        layout = build(grid)
        for cell in layout.cells_with(BlockType.CROP):
            for neighbor in grid.neighbors(cell):
                assert layout.block_at(neighbor) is not BlockType.CROP

    @pytest.mark.parametrize("name", ["rectangle_9x9", "l_shape", "large_15x15"])
    def test_the_checkerboard_ties_the_optimum_on_regular_terrain(self, name):
        """The cactus demo's first headline, pinned.

        On open ground the checkerboard is not merely good, it is optimal, and
        the solver only confirms it.
        """
        grid = parse_grid(shared.TERRAINS[name])
        hand = cactus_demo.baseline_checkerboard(grid)
        optimal = optimize(shared.TERRAINS[name], crop=Cactus())
        assert optimal.metrics.n_crop == hand.metrics.n_crop, (
            f"the checkerboard should tie the optimum on {name}"
        )

    @pytest.mark.parametrize(
        "name", ["rectangle_9x9", "l_shape", "large_15x15", "ragged"]
    )
    def test_the_greedy_sweep_ties_the_optimum_nearly_everywhere(self, name):
        """The cactus demo's second and more humbling headline, pinned.

        A player with no pattern at all, sweeping and planting wherever it is
        legal, matches the exact optimum on four of the five terrains. If this
        ever stops holding, the demo's claim that the solver is barely worth
        running for cactus is wrong and must be rewritten.
        """
        grid = parse_grid(shared.TERRAINS[name])
        greedy = cactus_demo.baseline_greedy(grid)
        optimal = optimize(shared.TERRAINS[name], crop=Cactus())
        assert greedy.metrics.n_crop == optimal.metrics.n_crop

    def test_the_solvers_best_win_over_a_greedy_player_is_tiny(self):
        """with_obstacles is the only terrain where the solver beats greedy at all.

        35 vs 34 -- under 3%. That single number is the cactus demo's thesis.
        """
        grid = parse_grid(shared.TERRAINS["with_obstacles"])
        greedy = cactus_demo.baseline_greedy(grid)
        optimal = optimize(shared.TERRAINS["with_obstacles"], crop=Cactus())
        assert greedy.metrics.n_crop == 34
        assert optimal.metrics.n_crop == 35

    def test_the_greedy_sweep_beats_the_checkerboard_on_rocky_ground(self):
        """No pattern beats a pattern once walls are involved.

        The checkerboard has to commit to one colour of the whole board;
        obstacles make that choice wrong locally and it cannot adapt.
        """
        grid = parse_grid(shared.TERRAINS["ragged"])
        assert cactus_demo.baseline_checkerboard(grid).metrics.n_crop == 7
        assert cactus_demo.baseline_greedy(grid).metrics.n_crop == 8

    def test_the_fill_is_what_makes_the_checkerboard_honest(self):
        """Without the fill the checkerboard scores 6 on ragged, not 7.

        That missing cactus is the difference between claiming +33.3% and the
        real +14.3%. Pinned so the fill cannot quietly disappear.
        """
        grid = parse_grid(shared.TERRAINS["ragged"])
        unfilled = cactus_demo._apply_checkerboard(grid, 0)
        # Undo the fill by rebuilding the raw pattern + prune only.
        raw = {
            cell: (
                BlockType.OBSTACLE
                if grid.is_obstacle(cell)
                else BlockType.CROP
                if (cell.row + cell.col) % 2 == 0
                else BlockType.EMPTY
            )
            for cell in grid.cells()
        }
        cactus_demo._prune_cactus_touching_a_wall(grid, raw)
        before = sum(1 for b in raw.values() if b is BlockType.CROP)
        after = sum(1 for b in unfilled.values() if b is BlockType.CROP)
        assert after > before, "the fill must actually add cacti on ragged terrain"

    @pytest.mark.parametrize("build", BUILDERS)
    @pytest.mark.parametrize("name", TERRAIN_NAMES)
    def test_optimum_never_loses(self, name, build):
        grid = parse_grid(shared.TERRAINS[name])
        optimal = optimize(shared.TERRAINS[name], crop=Cactus(), time_limit=30.0)
        assert optimal.metrics.n_crop >= build(grid).metrics.n_crop


class TestGracefulDegradation:
    @pytest.mark.parametrize(
        "build",
        [
            cane_demo.baseline_checkerboard,
            cane_demo.baseline_stripes_1x2,
            cane_demo.baseline_greedy_water,
            cactus_demo.baseline_checkerboard,
            cactus_demo.baseline_greedy,
        ],
    )
    @pytest.mark.parametrize("terrain", ["###\n###", "#.#\n###\n#.#"])
    def test_baseline_returns_none_instead_of_crashing(self, terrain, build):
        """Terrains where a strategy grows nothing must degrade, not raise."""
        assert build(parse_grid(terrain)) is None

    def test_a_single_cell_grows_cactus_but_no_cane(self):
        """The crops' mirror image, at the smallest possible scale."""
        assert cactus_demo.baseline_checkerboard(parse_grid(".")).metrics.n_crop == 1
        assert cactus_demo.baseline_greedy(parse_grid(".")).metrics.n_crop == 1
        assert cane_demo.baseline_stripes_1x2(parse_grid(".")) is None

    @pytest.mark.parametrize("demo", [cane_demo, cactus_demo])
    def test_comparison_handles_a_missing_baseline(self, demo, capsys):
        optimal = optimize("...\n...", crop=demo.CROP)
        demo.print_comparison(optimal, [("Whatever", None)])
        assert "Whatever" in capsys.readouterr().out

    def test_arrow_falls_back_when_the_terminal_cannot_encode_it(self):
        """The Windows console is cp1252, which has no U+2192."""
        assert shared.arrow() in {"→", "->"}

    def test_table_rejects_a_row_that_does_not_match_its_header(self):
        """A silently truncated table would hide the bug."""
        with pytest.raises(ValueError):
            shared.print_table(("A", "B"), (3, 3), [("only-one",)])


class TestOutput:
    def test_sugarcane_demo_prints_terrain_layouts_and_comparison(self, capsys):
        cane_demo.run_one("l_shape")
        out = capsys.readouterr().out
        assert "Sugarcane on l_shape" in out
        assert "Input" in out
        assert "Checkerboard by hand" in out
        assert "1x2 stripes by hand" in out
        assert "Greedy water by hand" in out
        assert "Optimal layout from optifarm" in out
        assert "cane" in out and "water" in out and "efficiency" in out

    def test_cactus_demo_prints_terrain_layouts_and_comparison(self, capsys):
        cactus_demo.run_one("ragged")
        out = capsys.readouterr().out
        assert "Cactus on ragged" in out
        assert "Checkerboard by hand" in out
        assert "Greedy sweep by hand" in out
        assert "cactus" in out and "efficiency" in out

    def test_cactus_demo_does_not_print_a_water_line(self, capsys):
        """Cactus places no support block; "water 0" would be noise."""
        cactus_demo.run_one("rectangle_9x9")
        assert "water" not in capsys.readouterr().out.lower()

    def test_cactus_demo_reports_the_tie_as_a_tie(self, capsys):
        cactus_demo.run_one("rectangle_9x9")
        assert "tie" in capsys.readouterr().out

    @pytest.mark.parametrize("demo", [cane_demo, cactus_demo])
    def test_main_runs_end_to_end(self, demo, capsys):
        demo.main()
        assert "efficiency" in capsys.readouterr().out

    def test_sugarcane_summary_table(self, capsys, monkeypatch):
        # Skip the 15x15: it costs ~12s and the rest prove the table renders.
        monkeypatch.setattr(
            shared, "TERRAINS", {k: v for k, v in shared.TERRAINS.items() if k != "large_15x15"}
        )
        monkeypatch.setattr(cane_demo, "TERRAINS", shared.TERRAINS)
        cane_demo.run_all()
        out = capsys.readouterr().out
        assert "rectangle_9x9" in out and "ragged" in out
        assert "Greedy water" in out and "vs greedy" in out

    def test_cactus_summary_table(self, capsys, monkeypatch):
        monkeypatch.setattr(cactus_demo, "TERRAINS", shared.TERRAINS)
        cactus_demo.run_all()
        out = capsys.readouterr().out
        assert "rectangle_9x9" in out and "ragged" in out
        assert "vs check" in out and "vs greedy" in out
        assert "+0.0%" in out, "the tie is the cactus demo's headline"
