# optifarm

Compute **provably optimal** Minecraft farm layouts. Give it a terrain and a crop;
it returns the block placement that maximises production, and a proof that nothing
better exists — via an OR-Tools CP-SAT model.

This first release implements **sugarcane**. The architecture is built so that the
next crop is a new rule file and nothing else.

## Quick start

```bash
python examples/demo.py
```

No arguments, nothing to write. It solves a terrain and shows what the optimiser
bought you over the two patterns people build by hand:

```
==================================================================
 Terrain: l_shape  (8x10, 68 free, 12 obstacles)
==================================================================

Input  ('.' free, '#' obstacle):
  ......####
  ......####
  ......####
  ..........
  ..........
  ..........
  ..........
  ..........

Checkerboard by hand  ('W' water, 'C' cane, '.' free but unused):
  WCWCWC####
  CWCWCW####
  WCWCWC####
  CWCWCWCWCW
  WCWCWCWCWC
  CWCWCWCWCW
  WCWCWCWCWC
  CWCWCWCWCW

1x2 stripes by hand  ('W' water, 'C' cane, '.' free but unused):
  WWWWWW####
  CCCCCC####
  CCCCCC####
  WWWWWWWWWW
  CCCCCCCCCC
  CCCCCCCCCC
  WWWWWWWWWW
  CCCCCCCCCC

Optimal layout from optifarm  (crop: sugarcane, solver: ilp):
  CWCCWC####
  CWCCCC####
  CCCWCW####
  WCCCCCCWCC
  CCWCWCCCCW
  WCCCCCWCCC
  CCCWCCCCWC
  CWCCCWCCWC

Metrics:
  cane ......... 51
  water ........ 17
  free, unused . 0
  efficiency ... 75.0%  (over 68 free cells, obstacles excluded)
  solver time .. 0.039s
  status ....... optimal

Compared against the hand-built patterns:
  Checkerboard:         34 cane  ( 50.0%)   → optifarm +50.0%
  1x2 stripes:          42 cane  ( 61.8%)   → optifarm +21.4%
  Optimal (optifarm):   51 cane  ( 75.0%)
```

Edit one line at the top of the file (`TERRAIN = "l_shape"`) to try another, or
set `RUN_ALL = True` for the summary across all of them:

```
  Terrain            Free    Checkerboard     1x2 stripes         Optimal   vs check    vs 1x2
  ----------------  -----  --------------  --------------  --------------  ---------  --------
  rectangle_9x9        81      41 (50.6%)      54 (66.7%)      61 (75.3%)     +48.8%    +13.0%
  l_shape              68      34 (50.0%)      42 (61.8%)      51 (75.0%)     +50.0%    +21.4%
  with_obstacles       92      46 (50.0%)      52 (56.5%)      68 (73.9%)     +47.8%    +30.8%
  large_15x15         225     113 (50.2%)     150 (66.7%)     172 (76.4%)     +52.2%    +14.7%
```

## What the comparison shows

Both hand patterns are legal layouts, and both are steelmanned — the demo tries
all 6 stripe variants and both checkerboard colourings and reports the best one.
They still lose, and *why* they lose is the argument for solving this exactly.

**The checkerboard is safe and wasteful.** Alternating water and cane can never
strand a plant: every cane gets four water neighbours. But cane only needs
**one**, so the pattern pays half the terrain for a guarantee it does not need.
It is pinned near 50% on every terrain above — obstacles barely dent it, because
its correctness is purely local.

**The 1x2 stripes are efficient and brittle.** One water stripe per two rows of
cane is exactly cane's reach, and it lands at 2/3 on open ground — genuinely good.
But it assumes open ground. Drop it on `with_obstacles` and it falls from 66.7%
to 56.5%, because a `#` sitting on a stripe strands the cane that stripe was
feeding. The checkerboard, meanwhile, holds 50.0%.

That trade — safe-but-wasteful against efficient-but-brittle — is the thing a
template cannot escape and a solver never faces. The optimiser holds ~75% on all
four terrains, and its lead over the stripes is widest exactly where the stripes
break (`with_obstacles`, +30.8%). It is not using a cleverer pattern; it is using
no pattern at all.

See [`examples/README.md`](examples/README.md).

## Install

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows;  source .venv/bin/activate on Unix
pip install -e ".[dev]"
```

Requires Python 3.11+ and `ortools`.

## Usage

```python
from mcfarm_opt import optimize, Sugarcane

terrain = """\
........##
....##....
..........
.###......
..........
..........
....##....
.........."""

layout = optimize(terrain, crop=Sugarcane(), solver="ilp")
print(layout.render())
print(layout.metrics)
```

```
CWCWCCWC##
CCCC##CCWC
WCWCCCWCCC
C###WCCCCW
CCWCCCCWCC
WCWCCWCCCC
CCCC##CCWW
CWCWCCWCCC
crop=52 support=19 empty=0 obstacle=9 efficiency=73.2% status=optimal time=0.068s
```

52 sugarcane on 71 usable cells, proven optimal in 68 milliseconds.

### Input and output

Terrain in, layout out — one character per cell.

| Symbol | Input        | Output              |
|--------|--------------|---------------------|
| `.`    | free ground  | free, left unused   |
| `#`    | obstacle     | obstacle (untouched)|
| `W`    | —            | water               |
| `C`    | —            | sugarcane           |

Rows must all be the same length. Blank lines are ignored.

### Metrics

`layout.metrics` carries `n_crop`, `n_support`, `n_empty`, `n_obstacle`, `n_free`,
`n_cells`, `efficiency`, `solve_time` and `status`.

`efficiency` is crop over **free** cells, not over the whole grid — a terrain that
is mostly obstacle should not be scored as a bad farm when the layout used
everything it was given.

### On reproducibility

A terrain usually has many layouts achieving the same optimum. CP-SAT searches in
parallel, so **which** optimal layout you get varies between runs. `n_crop` is
reproducible; the exact rendering is not. Assert on the count, or on the rules the
layout must satisfy — not on a golden picture.

### Large terrains

Pass `time_limit` (seconds) to cap the search. You then get the best layout found
so far, and `metrics.is_optimal` tells you whether it was proven:

```python
layout = optimize(big_terrain, crop=Sugarcane(), time_limit=10.0)
if not layout.metrics.is_optimal:
    print(f"best found so far: {layout.metrics.n_crop} (lower bound)")
```

## The sugarcane model

A cell may hold cane iff it is free, is not itself water, and has **at least one
orthogonally adjacent water block**. Obstacles hold neither water nor cane, and
never satisfy a neighbour's requirement.

As an integer program, with `x[p,b]` = "cell *p* holds block *b*":

```
maximise    sum_p x[p, CROP]

subject to  x[p, CROP] = 1  =>  sum_{q in N(p)} x[q, WATER] >= 1    for all free p
            sum_b x[p, b] = 1                                       for all p
            x[p, OBSTACLE] = 1                                      for all blocked p
```

The plantability rule is an **implication**, not a hard constraint: it fires only
where the solver chose to plant, which is what makes this a choice of where to farm
rather than a demand that all terrain be farmable. "Not itself water" needs no
constraint — the one-hot rule already forbids a cell being two blocks at once.

The tension the solver resolves is that water both enables and consumes cells: each
water block costs one cell of production but can serve up to four neighbours.

Why an exact solver rather than a stamped-out template? On open ground the answer
looks regular, but the counts are not the ones people guess. A 5x5 tops out at
**18** cane, not the 15 that water-every-other-row gives; the optimum spends 7 cells
on water in an irregular pattern. Add obstacles and hand-reasoning degrades fast.

## Extending: adding a crop

A crop implements `CropRule`. Most crops need no CP-SAT at all — subclass
`AdjacencyCropRule` and declare requirements. The requirement shape carries the
**sign** and the **distance** as parameters, which is what lets one abstraction
cover rules that pull in opposite directions:

```python
class Cactus(AdjacencyCropRule):
    """Cactus: breaks if any solid block is orthogonally adjacent."""

    @property
    def name(self) -> str:
        return "cactus"

    def support_blocks(self) -> frozenset[BlockType]:
        return frozenset({BlockType.SAND})

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        return (
            AdjacencyRequirement(                       # NEGATIVE adjacency
                blocks=frozenset({BlockType.SAND, BlockType.CROP, BlockType.OBSTACLE}),
                maximum=0,
            ),
        )
```

The three shapes the interface is designed to cover:

| Crop      | Rule                                   | Requirement                                                      |
|-----------|----------------------------------------|------------------------------------------------------------------|
| Sugarcane | needs water orthogonally adjacent      | `AdjacencyRequirement({WATER}, minimum=1)`                        |
| Cactus    | no solid block orthogonally adjacent   | `AdjacencyRequirement({SAND, CROP, OBSTACLE}, maximum=0)`          |
| Wheat     | water within radius 4, incl. diagonals | `AdjacencyRequirement({WATER}, DIAGONAL, radius=4, minimum=1)`     |

Nothing about water or adjacency is hardcoded in the core: the grid only knows
about distance metrics, and the variables only know about "exactly one block per
cell". Both cactus and wheat above are exercised in `tests/test_extensibility.py`
against the shipped core, unmodified.

For a rule no declarative scheme anticipates, implement `CropRule` directly and
write the constraints by hand — you get the model, the variables and the grid.
`tests/test_extensibility.py::HandWrittenCrop` does exactly this to impose a global
cap that no per-cell rule could express.

## Architecture

```
mcfarm_opt/
├── core/            # crop-agnostic. knows nothing about water.
│   ├── grid.py      #   cells, obstacles, neighbourhoods (Manhattan / Chebyshev)
│   ├── blocks.py    #   BlockType enum + render symbols
│   ├── variables.py #   the x[cell, block] one-hot variables
│   └── result.py    #   FarmLayout + FarmMetrics
├── crops/           # what makes a cell plantable. one module per crop.
│   ├── base.py      #   CropRule protocol + AdjacencyCropRule helper
│   └── sugarcane.py #   the only crop so far
├── solvers/         # how the model is searched
│   ├── base.py      #   Solver protocol
│   └── ilp.py       #   exact, via CP-SAT
├── io/
│   └── text.py      # parse / render
└── ...
examples/
└── demo.py          # runnable entrypoint, commented as documentation
```

`core/variables.py` is the one module not in the original design sketch. It holds
the `x[cell, block]` variables and the one-hot constraint — the vocabulary the
solver and the crop rules have to share. Putting it in `core` is what keeps crops
from importing solvers or vice versa.

## Tests

```bash
python -m pytest
```

155 tests. The interesting ones are in `tests/test_sugarcane.py::TestAgainstBruteForce`:
they check the CP-SAT model against an **exhaustive enumeration of every possible
water placement**, written in `tests/conftest.py` and sharing no code with the
library. That tests the model against the definition of the problem rather than
against itself.

Every hardcoded optimum in the suite (5x5 → 18, obstacle → 17, L-shape → 15) was
verified the same way — by brute force over all 2^25 water placements, offline,
before being written down.

`tests/test_demo.py` guards the demo's headline claim. Both baselines it compares
against are checked to be **legal** layouts, cell by cell: cane without adjacent
water would flatter the hand pattern, over-eager pruning would flatter optifarm, and
either way the comparison in this README would be a lie that nothing else would
catch. It also asserts the optimum never scores below a baseline — a baseline is a
feasible layout, so it is a lower bound on the optimum by construction, and a
solver coming in under one would mean the model is wrong.

## Not yet implemented

- Other crops (the interface is ready; the rules are not written)
- Heuristic solvers for terrains too large to solve exactly
- Graphical visualisation
- Schematic export
