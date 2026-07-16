# optifarm

Compute **provably optimal** Minecraft farm layouts. Give it a terrain and a crop;
it returns the block placement that maximises production, and a proof that nothing
better exists — via an OR-Tools CP-SAT model.

Implements **sugarcane** and **cactus** — rules that pull in opposite directions
(cane needs water beside it, cactus needs nothing solid beside it) and share every
line of the core. Adding the next crop is a new rule file and nothing else.

## Quick start

```bash
python examples/demo_sugarcane.py     # hand patterns lose. use the solver.
python examples/demo_cactus.py        # hand pattern already wins. mostly don't.
```

No arguments, nothing to write. Each solves a terrain and shows what the
optimiser bought you over the patterns people build by hand — and for cactus,
the honest answer is often *nothing*, which is the point. Sugarcane first:

```
==================================================================
 Sugarcane on l_shape  (8x10, 68 free, 12 obstacles)
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
  Terrain         Free   Checkerboard    1x2 stripes   Greedy water        Optimal   vs greedy
  --------------  ----  -------------  -------------  -------------  -------------  ----------
  rectangle_9x9     81     41 (50.6%)     54 (66.7%)     57 (70.4%)     61 (75.3%)       +7.0%
  l_shape           68     34 (50.0%)     42 (61.8%)     49 (72.1%)     51 (75.0%)       +4.1%
  with_obstacles    92     46 (50.0%)     52 (56.5%)     64 (69.6%)     68 (73.9%)       +6.2%
  ragged            26     13 (50.0%)     14 (53.8%)     18 (69.2%)     18 (69.2%)       +0.0%
  large_15x15      225    113 (50.2%)    150 (66.7%)    164 (72.9%)    172 (76.4%)       +4.9%
```

Read the last column, not the pattern columns. Beating the 1×2 stripes by 13–31%
sounds impressive and is mostly a fact about stripes. **Greedy water** is a player
following no pattern at all, just digging whichever cell buys the most cane — they
beat every pattern here, and against them the exact optimum is worth **4–7%**.
Real, worth having, and a good deal smaller than the headline a template opponent
would have handed us.

Now run `demo_cactus.py` on the same land, and it says the opposite:

```
  Terrain            Free    Checkerboard    Greedy sweep         Optimal   vs check   vs greedy
  ----------------  -----  --------------  --------------  --------------  ---------  ----------
  rectangle_9x9        81      41 (50.6%)      41 (50.6%)      41 (50.6%)      +0.0%       +0.0%
  l_shape              68      31 (45.6%)      31 (45.6%)      31 (45.6%)      +0.0%       +0.0%
  with_obstacles       92      33 (35.9%)      34 (37.0%)      35 (38.0%)      +6.1%       +2.9%
  ragged               26       7 (26.9%)       8 (30.8%)       8 (30.8%)     +14.3%       +0.0%
  large_15x15         225     113 (50.2%)     113 (50.2%)     113 (50.2%)      +0.0%       +0.0%
```

**+0.0%.** For cactus on open ground the checkerboard people already build *is*
the optimum, and the solver only confirms it. Worse: a player with no pattern at
all — sweeping the field, planting wherever it is legal — ties the optimum on four
of the five terrains. The exact solver's best win over that player is **+2.9%, on
one map**.

So the two crops bracket the answer: for sugarcane the solver is worth a real but
single-digit margin over someone thinking; for cactus it is worth essentially
nothing. Saying so is the most useful thing it does. More on that below.

## What the comparison shows

Every baseline here is a legal layout, steelmanned rather than strawmanned: all 6
stripe variants and both checkerboard colourings are tried and the best reported,
and — the part that is easy to get wrong — each one **fills its leftover holes**.
A pattern that prunes what broke and walks away leaves free production on the
table that a real player would take; beating *that* proves nothing about the
solver and everything about the baseline. (For cactus the fill is worth up to a
cactus per map; for sugarcane it provably never fires, since a cell is only empty
because it has no water beside it, which is exactly what planting would need.)

The other half of a fair fight is picking a real opponent. A *pattern* is not the
best a person can do, so each demo also measures against a player who follows no
pattern at all — and in both cases that player beats every pattern, and shrinks
the solver's margin to single digits. Those are the numbers to judge this by.

The sugarcane patterns still lose, and *why* they lose is worth understanding.

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
template cannot escape and a solver never faces. The optimiser holds ~75% on every
terrain. It is not using a cleverer pattern; it is using no pattern at all.

**But neither does a decent player, and that is the honest measurement.** Dig the
water that pays best, repeat: that beats the stripes on every terrain (70–73% vs
56–67%) and lands within 4–7% of proven optimal — dead level with it on `ragged`.
The solver's real prize for sugarcane is those few percent, not the 30% you get by
choosing a template as your opponent.

**And then cactus says the opposite, which matters more.** Cactus forbids
neighbours rather than needing them, so the best layout is a checkerboard — and
that is already what people build. The solver ties it at +0.0% on every regular
terrain. It pulls ahead only where obstacles turn irregular (`ragged`, +14.3%),
because a checkerboard has to commit to one colour of the board *globally* while
obstacles make that choice wrong *locally*.

**And a player who uses no pattern beats the pattern.** Sweeping the field and
planting wherever it is legal commits to nothing, so it adapts to walls that a
checkerboard cannot. That greedy sweep ties the exact optimum on four of five
terrains; the solver's entire advantage over it is +2.9%, once.

So the honest summary is not "always optimise". It is: **for sugarcane the solver
buys you a few percent over a thoughtful player; for cactus it buys you nothing.**
A tool worth trusting is one that will tell you when to leave it in the drawer,
and the demos say that out loud instead of burying a +0.0% in a table.

Every number above got smaller as the baselines got fairer, and that history is
worth stating plainly:

- The hand patterns did not fill the holes their pruning left, so they threw away
  cane and cactus a real player would have planted.
- The cactus demo had a "sparse grid" opponent scoring +64% for the solver. Fill
  its holes and it simply *is* the checkerboard. The +64% was fiction.
- Both demos measured the solver against *patterns*, when a player who follows no
  pattern does better than any of them. That alone cut sugarcane's headline from
  13–31% down to 4–7%, and cactus's from +33% to +0%.

None of those were rounding errors; each one was the measurement flattering the
thing being measured. A comparison is worth exactly as much as the opponent it
picks.

See [`examples/README.md`](examples/README.md) for why the demos are split per
crop rather than sharing a `CROP` switch.

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

## The cactus model

The mirror image, and the reason the abstraction carries its sign as a parameter.
A cell may hold cactus iff it is free and **no solid block is orthogonally
adjacent**. Cane is drawn to a feature; cactus is repelled by one. In the model
that difference is `minimum=1` versus `maximum=0`.

```
maximise    sum_p x[p, CROP]
subject to  x[p, CROP] = 1  =>  sum_{q in N(p)} (x[q, CROP] + x[q, OBSTACLE]) = 0
```

Stated once per cell, and it needs no mirror: if two adjacent cells both held
cactus, each one's own constraint would already be violated.

**What counts as solid** is the judgement call, and it decides every number. The
grid is a top-down projection, so the question is what sits at the *cactus's own
level* in a neighbouring cell:

- **another cactus** — solid, breaks it.
- **an obstacle** — modelled as solid, so cactus cannot hug it. The terrain
  format has one `#`, so this reads every obstacle as a wall rather than a pit —
  the conservative choice, since a layout valid against a wall is also valid
  against a hole, but not the reverse.
- **sand** — *not* solid at cactus level. The sand a cactus stands on is one block
  **underneath** it, inside the same cell of the projection, never a neighbour.
  This is why `Cactus.support_blocks()` is empty and why real checkerboard cactus
  farms work at all. Note this is deliberately narrower than `BlockType.is_solid`,
  which answers "is sand a solid block?" (yes) rather than "is sand solid *where
  the cactus is*?" (no).

Two consequences worth knowing, both verified:

**Cactus is easy where sugarcane is hard.** This is maximum independent set on a
grid graph. Grid graphs are bipartite, and MIS on a bipartite graph is polynomial
— by König's theorem it is `n - maximum matching` — so the LP relaxation is
integral and CP-SAT closes the proof at the root instead of searching. Sugarcane
cannot prove an 18×18 in 30 seconds; cactus proves a **40×40 in 0.34s**.

**Obstacles are brutal.** A sugarcane obstacle costs about the cell itself. A
cactus obstacle also poisons its up-to-four neighbours, since none may touch it.
On the same 5×5 with six scattered obstacles, sugarcane grows 12 and cactus grows
**2**; in a one-cell-wide corridor, sugarcane grows 5 and cactus grows **0**,
because every free cell touches a wall.

On open ground the answer is the checkerboard everyone already builds —
`ceil(rows*cols/2)`, about 50%, and the solver confirms it rather than discovers
it. The solver earns its keep on irregular terrain, where *which half of the
board* stops being a global choice.

## Extending: adding a crop

A crop implements `CropRule`. Most crops need no CP-SAT at all — subclass
`AdjacencyCropRule` and declare requirements. The requirement shape carries the
**sign** and the **distance** as parameters, which is what lets one abstraction
cover rules that pull in opposite directions:

`Cactus` is the whole of it — the shipped rule, in full:

```python
class Cactus(AdjacencyCropRule):
    """Cactus, which grows on any cell no solid block touches."""

    @property
    def name(self) -> str:
        return "cactus"

    def support_blocks(self) -> frozenset[BlockType]:
        return frozenset()          # the sand is *under* the cactus, not beside it

    def requirements(self) -> Sequence[AdjacencyRequirement]:
        return (
            AdjacencyRequirement(                       # NEGATIVE adjacency
                blocks=SOLID_AT_CACTUS_LEVEL,           # {CROP, OBSTACLE}
                maximum=0,
            ),
        )
```

That is the entire diff for a crop that pulls in the opposite direction from
sugarcane. No core file was touched to add it.

The three shapes the interface is designed to cover:

| Crop      | Rule                                   | Requirement                                                   | Status |
|-----------|----------------------------------------|---------------------------------------------------------------|--------|
| Sugarcane | needs water orthogonally adjacent      | `AdjacencyRequirement({WATER}, minimum=1)`                     | shipped |
| Cactus    | no solid block orthogonally adjacent   | `AdjacencyRequirement({CROP, OBSTACLE}, maximum=0)`            | shipped |
| Wheat     | water within radius 4, incl. diagonals | `AdjacencyRequirement({WATER}, DIAGONAL, radius=4, minimum=1)` | not yet |

Nothing about water or adjacency is hardcoded in the core: the grid only knows
about distance metrics, and the variables only know about "exactly one block per
cell". Sugarcane and cactus prove that in shipped code; wheat's radius rule is
exercised in `tests/test_extensibility.py` against the same core, unmodified.

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
│   ├── sugarcane.py #   positive adjacency: needs water beside it
│   └── cactus.py    #   negative adjacency: needs nothing solid beside it
├── solvers/         # how the model is searched
│   ├── base.py      #   Solver protocol
│   └── ilp.py       #   exact, via CP-SAT
├── io/
│   └── text.py      # parse / render
└── ...
examples/
├── _shared.py          # terrains + print plumbing. not worth reading.
├── demo_sugarcane.py   # runnable, commented as documentation
└── demo_cactus.py      # ditto, and it argues the opposite case
```

`core/variables.py` is the one module not in the original design sketch. It holds
the `x[cell, block]` variables and the one-hot constraint — the vocabulary the
solver and the crop rules have to share. Putting it in `core` is what keeps crops
from importing solvers or vice versa.

## Tests

```bash
python -m pytest
```

329 tests. The interesting ones are in `tests/test_sugarcane.py::TestAgainstBruteForce`:
they check the CP-SAT model against an **exhaustive enumeration of every possible
water placement**, written in `tests/conftest.py` and sharing no code with the
library. That tests the model against the definition of the problem rather than
against itself.

Every hardcoded optimum in the suite (5x5 → 18, obstacle → 17, L-shape → 15) was
verified the same way — by brute force over all 2^25 water placements, offline,
before being written down.

`tests/test_cactus.py` gets the same treatment, plus a bonus: cactus has a **closed
form**. On open ground the answer is provably `ceil(rows*cols/2)`, so every open
rectangle from 1×1 to 6×6 is checked against arithmetic that owes the solver
nothing. Its brute-force oracle is separate from sugarcane's — same discipline,
different rule.

`tests/test_demo.py` guards the demos' headline claims. Every baseline they compare
against is checked to be a **legal** layout under its own crop's rule — using the
same validators that check the solver's own output. A pattern claiming crop it
cannot grow would flatter the hand pattern; over-eager pruning would flatter
optifarm; either way the tables in this README would be a lie that nothing else
would catch. It also asserts the optimum never scores below a baseline (a baseline
is feasible, so it is a lower bound by construction), and it pins the cactus
**+0.0% tie** — that tie is the whole lesson of `demo_cactus.py`, so if it ever
drifts, either the claim or the model is wrong.

## Not yet implemented

- Wheat, melons, mushrooms (the interface is ready; the rules are not written)
- Heuristic solvers for terrains too large to solve exactly
- Graphical visualisation
- Schematic export
