# examples/

The optifarm playground. Nothing here is imported by the library — these are
files to run, read and edit.

## `demo.py`

```bash
python examples/demo.py
```

Runs with no arguments. Shows the input terrain, the layouts two hand-built
patterns produce, the optimal layout, the metrics, and how much the exact
optimisation beats each pattern by.

To experiment, edit **one line** in the configuration block at the top:

```python
TERRAIN = "l_shape"      # options: see the TERRAINS dict above
CROP    = Sugarcane()
SOLVER  = "ilp"

RUN_ALL = False          # True = run every terrain, with a summary table
```

The terrains ship ready to use: `rectangle_9x9`, `l_shape`, `with_obstacles` and
`large_15x15` (that one takes ~12s, deliberately — it is there to feel the cost
of *proving* optimality). Adding a terrain means adding a string to the dict.

The file is commented as documentation: it is the explanation of how to use the
API, not just a demonstration.

## The baselines it compares against

Both are real layouts, both are legal, and they lose to the solver for different
reasons — which is the interesting part:

- **Checkerboard** — alternating water and cane. Trivially correct: every cane
  has four water neighbours, so none can ever be stranded. That safety is the
  weakness — cane needs *one* adjacent water, so the pattern buys a guarantee it
  does not need and pays half the terrain for it. Pinned near 50% everywhere.
- **1x2 stripes** — one water stripe per two rows of cane. Each stripe serves the
  row above and below, which is exactly cane's reach. Lands at 2/3 on open
  ground, and is the pattern the community actually builds.

Both are steelmanned rather than strawmanned: the demo tries all 6 stripe
variants (2 orientations × 3 offsets) and both checkerboard colourings, and
reports the best. On a 9x9 the right stripe offset yields 54 cane and the wrong
one 45 — comparing against the worse variant would inflate optifarm's win for
free.

`tests/test_demo.py` checks both baselines are legal layouts, cell by cell.

## Coming later

- **`cactus.py`** — once a `CactusRule` exists. It is the interesting example
  from a modelling standpoint: cane wants water nearby (positive adjacency),
  cactus wants the opposite (negative adjacency), and both fall out of the same
  `AdjacencyRequirement` with only the sign changed.
- **`benchmark.py`** — how proving time scales with terrain size, and where the
  exact solver should give way to a heuristic. The start of that curve is already
  visible: 9x9 solves in 0.07s, 12x12 in 0.9s, 15x15 in 12s, and an 18x18 does
  not close the proof within 30s.
