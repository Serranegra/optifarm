# examples/

The optifarm playground. Nothing here is imported by the library — these are
files to run, read and edit.

```bash
python examples/demo_sugarcane.py     # hand patterns lose. use the solver.
python examples/demo_cactus.py        # hand pattern already wins. mostly don't.
```

Both run with no arguments. Each shows the input terrain, the layouts people
build by hand, the optimal layout, the metrics, and the comparison. To
experiment, edit **one line** at the top of either file:

```python
TERRAIN = "l_shape"      # options: see TERRAINS in _shared.py
SOLVER  = "ilp"

RUN_ALL = False          # True = run every terrain, with a summary table
```

## Why two files and not one crop switch

There used to be one `demo.py` with a `CROP` knob. It was a trap: the baselines
are hand-written patterns, not solver output, so setting `CROP = Cactus()` laid
**water stripes on a cactus farm** and rendered the nonsense without complaint.

The deeper reason is that the two demos teach opposite lessons, and a demo's job
is to teach one:

- **`demo_sugarcane.py`** — the hand patterns lose by 13–31%, but a player who
  follows no pattern beats every pattern, and against *them* the solver wins
  **4–7%**. Worth running, for less than the headline suggests.
- **`demo_cactus.py`** — the hand checkerboard *is* the optimum on open ground,
  and a player who just plants greedily ties the optimum on 4 of 5 terrains. The
  solver's best win over them is **+2.9%**. Don't bother.

One parameterised file tells both badly: cactus's headline `+0.0%` reads as a
failure inside a narrative built around "the solver wins big". Each demo now
fixes its own crop, so the trap cannot be re-armed.

`_shared.py` holds the terrains and the print formatting. You do not need to read
it. The terrains live there so both demos solve the *same* land — that is what
makes the cross-crop numbers mean anything (on `scattered`, the identical 5×5
grows 12 sugarcane and 2 cactus).

## The baselines

Each demo measures against what real players do, and steelmans it — every
alignment is tried and the best reported, because comparing against a
badly-aligned pattern would inflate optifarm's win for free.

| Demo | Strategy | What it gets wrong |
|------|----------|--------------------|
| Sugarcane | Checkerboard | Safe but wasteful: gives every cane 4 water neighbours when 1 would do. Pinned near 50%. |
| Sugarcane | 1×2 stripes | Efficient (2/3) but brittle: a `#` on a stripe strands the cane it fed. |
| Sugarcane | Greedy water | **Little.** No pattern — just dig the cell that buys the most cane. Beats both patterns; within 4–7% of optimal. |
| Cactus | Checkerboard | Only its *globality*: it must pick one colour of the board for the whole map, and walls make that wrong locally. Optimal on open ground. |
| Cactus | Greedy sweep | **Almost nothing.** Ties the optimum on 4 of 5 terrains. |

### Pick a real opponent

A *pattern* is not the best a person can do, so measuring only against patterns
flatters the solver. Both demos therefore include a no-pattern player, and in both
cases that player beats every pattern and cuts the solver's margin to single
digits. Those are the numbers to judge this library by.

There is no "naive sweep" baseline for sugarcane, and the reason is worth knowing:
it degenerates. Walk the field planting cane where water already sits and digging
where it does not, and the alternation propagates into precisely a **checkerboard**
— at whichever parity the corner forced, scoring 40 against the checkerboard's 41.
It is not a distinct strategy, it is the same one denied its choice of colour, so
adding it would mean adding a deliberately worse-aligned copy of a row already in
the table. (For cactus the same sweep is *near-optimal* — which is exactly why
cactus is the easy problem and sugarcane is not.)

### Filling the holes

Stamping a pattern and pruning what broke leaves *holes* — and a player looking at
a plantable hole plants in it. A baseline that walks away from free production is
a strawman, so both demos fill their gaps before being measured.

This matters more than it sounds:

- **Cactus**: the fill is worth a cactus or two per map. It is also what killed a
  third baseline. There used to be a "sparse grid" (a gap in both directions
  around each cactus) that scored 25 on a 9×9 and made the solver look +64%
  better. Fill its holes and it becomes *exactly* the checkerboard — 41. It was
  never a distinct strategy, only an unfilled one, and the +64% was fiction.
- **Sugarcane**: the fill provably never fires, so the demo does none. A cell is
  only empty because the prune found it had **no adjacent water** — which is
  precisely what planting cane there would require. The condition that creates a
  hole is the negation of the one that could fill it.

`tests/test_demo.py` checks every baseline is a *legal* layout under its own
crop's rule — using the same validators that check the solver's own output — and
separately that every baseline is **maximal**, so neither demo can regress into
flattering its own optimiser.

## Coming later

- **`benchmark.py`** — how proving time scales, and where the exact solver should
  give way to a heuristic. The curve is already visible for sugarcane: 9×9 in
  0.07s, 12×12 in 0.9s, 15×15 in 12s, and an 18×18 does not close in 30s. Cactus
  is the control group — bipartite maximum independent set, so a 40×40 proves in
  0.34s and the curve is flat.
- **`wheat.py`** — once a `WheatRule` exists. Its radius-4 hydration is the third
  shape of adjacency rule, and the one no current demo shows.
