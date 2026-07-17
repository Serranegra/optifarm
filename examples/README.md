# examples/

The optifarm playground. Nothing here is imported by the library — these are
files to run, read and edit.

```bash
python examples/demo_sugarcane.py     # +4-7% over a thinking player. worth it.
python examples/demo_cactus.py        # +4.9% at best. barely.
python examples/demo_wheat.py         # +0.0% on 6 of 7 maps. don't bother.
```

All three run with no arguments. Each shows the input terrain, the layouts people
build by hand, the optimal layout, the metrics, and the comparison. To
experiment, edit **one line** at the top of any of them:

```python
TERRAIN = "l_shape"      # options: see TERRAINS in _shared.py
SOLVER  = "ilp"

RUN_ALL = False          # True = run every terrain, with a summary table
```

## Why two files and not one crop switch

There used to be one `demo.py` with a `CROP` knob. It was a trap: the baselines
are hand-written patterns, not solver output, so setting `CROP = Cactus()` laid
**water stripes on a cactus farm** and rendered the nonsense without complaint.

The deeper reason is that the demos teach opposite lessons, and a demo's job is to
teach one:

- **`demo_sugarcane.py`** — the hand patterns lose by 13–29%, but a player who
  follows no pattern beats every pattern, and against *them* the solver wins
  **4–7%**. Worth running, for less than the headline suggests.
- **`demo_cactus.py`** — the hand checkerboard *is* the optimum on open ground,
  and a player who just plants greedily ties the optimum on 4 of 5 terrains. The
  solver's best win over them is **+4.9%**. Don't bother.
- **`demo_wheat.py`** — water hydrates 80 cells and costs one, so wheat is a
  covering problem, and a source every nine blocks solves it *exactly*. The solver
  wins **+0.0%** on six of seven terrains. Really don't bother.

One parameterised file tells both badly: cactus's headline `+0.0%` reads as a
failure inside a narrative built around "the solver wins big". Each demo now
fixes its own crop, so the trap cannot be re-armed.

`_shared.py` holds the terrains and the print formatting. You do not need to read
it. The terrains live there so every demo solves the *same* land — that is what
makes the cross-crop numbers mean anything: the identical 9×9 grows 41 cactus, 61
sugarcane and 80 wheat, and nothing separates those but the adjacency rule.

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
| Wheat | 9-lattice | **Nothing, on open ground** — it is the proven optimum. Only rubble, where there is no spacing to lock onto, beats it (by 2.7%). |
| Wheat | Greedy water | **Nothing on 6 of 7 maps.** Loses 0.9% on rubble. |

### Pick a real opponent

A *pattern* is not the best a person can do, so measuring only against patterns
flatters the solver. Every demo therefore includes a no-pattern player, and in each
case that player beats or matches the patterns and cuts the solver's margin to
single digits. Those are the numbers to judge this library by.

Picking the *field* fairly matters too, and is easier to get wrong. `with_obstacles`
is 11 wide, not 10, because the 1×2 pattern has period 3 and only tiles a width of
1 (mod 3). At 10 the stripes fall a column short and ten tiles of good ground die
with no rock anywhere near them — and the solver posts a 30% win that is really a
fact about the field size. It looks like the obstacles' fault. It is not.

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
- **Wheat**: the fill has two shapes, because a dry cell cannot just be planted —
  it needs a *source*, which costs a cell of its own. So the repair both **digs
  where it is dry** and **pulls sources that are redundant**. On `two_fields` a
  raw 9-lattice scores 252 because its sources land inside a wall; repaired, it
  scores the optimal 320. Skipping that would have let the demo advertise +27%.

`tests/test_demo.py` checks every baseline is a *legal* layout under its own
crop's rule — using the same validators that check the solver's own output — and
separately that every baseline is **maximal**, so neither demo can regress into
flattering its own optimiser.

## The terrains

`_shared.py` holds five, and all three demos solve them, which is what makes the
crops comparable on identical ground: the same 9×9 grows 41 cactus, 61 sugarcane
and 80 wheat.

`demo_wheat.py` adds two of its own. Wheat reaches nine blocks, so most of the
shared terrains fit inside a *single water source* and every strategy ties without
having to think. That tie is most of wheat's argument, so the terrains stay — but a
table of nothing but zeros proves nothing about the hard cases, so `two_fields`
(20×20, walls where the lattice wants its sources) and `rubble` (35% obstacles, no
spacing to lock onto) are sized for the crop. They are wheat-only because sugarcane
cannot prove a 20×20 in any reasonable time, while wheat proves both in under a
second.

## Coming later

- **`benchmark.py`** — how proving time scales, and where the exact solver should
  give way to a heuristic. The curve is already visible for sugarcane: 9×9 in
  0.07s, 12×12 in 0.9s, 15×15 in 12s, and an 18×18 does not close in 30s. The
  other two are control groups — cactus is bipartite maximum independent set and
  wheat is a covering problem on a lattice, so both prove a 40×40 in about a
  second and their curves are flat.
