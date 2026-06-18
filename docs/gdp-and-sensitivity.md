# GDP component + sensitivity view — design

Two features that make "relative power" both deeper and self-examining: a third
component (GDP) so the metric stops being "big + wide," and a sensitivity view
that shows how much any ranking depends on the weights you chose.

---

## Part A — GDP as a third component

### The attribution problem

Maddison (MPD 2023) is keyed by **modern country**, not historical polity. So
GDP can't be read off a polity directly — it has to be attributed. The honest
method reuses the rasterization that already produces population and area:

> A cell's GDP = its HYDE population × the GDP-per-capita of the **modern
> country** that cell sits in, for that year (Maddison). A polity's GDP = the
> sum over the cells assigned to it.

So GDP rides on the same cell→polity assignment as population. It needs one new
ingredient per cell: which modern country it's in (Natural Earth — already
loaded for region focus), joined to Maddison gdp-per-capita.

### Being honest about it

Maddison's per-capita estimates are real for the modern era and **educated
guesses before ~1500**, hovering near a subsistence floor. So:

- Pre-modern, GDP-per-capita is near-flat, which means **the GDP lens degrades
  to roughly the population lens** before ~1500. That's not a bug to hide — it's
  a true statement about what we can know, and the view should say so (a "low
  confidence before 1500" note on the GDP lens and in tooltips).
- Where Maddison has no figure for a country-year, fall back to a region or
  world-mean gdp-per-capita and **flag those cells as estimated**, feeding a GDP
  residual the same way unmapped land feeds the territory residual.

### What changes (and what doesn't)

| File | Change |
|------|--------|
| `pipeline/compute_gdp.py` | **new** — cell-GDP attribution → `gdp_int_usd.csv` |
| `pipeline/align_territory.py` | add `gdp_int_usd` to facts; add world GDP to totals (this is the live emitter — see its note below) |
| `web/lenses.js` | add the `gdp` simple lens + a third composite component |
| `web/engine.js` | **none** — composite already iterates N components |
| `pipeline/align_territory.py` | generalize composite to N components; new presets (the inline `lens_order`) |
| `web/order.js` | unchanged — still snaps to the nearest preset by the single territory weight `wArea` (see note) |
| `web/lens-adapter.js` | ≥3 components → weight bars instead of the balance bar |

`engine.js` needing no change is the architecture paying off.

> **Implementation notes (doc kept honest with the shipped code):**
> - The live emitter is **`pipeline/align_territory.py`**, not `emit_facts.py`
>   (which is a superseded Demograph template). It threads GDP and any
>   `data/processed/vectors/*.csv` into `web/facts.js` / `totals.js`, and bakes
>   per-lens orders via its inline `lens_order`, not `compute_orders.py`.
> - **`order.js` was *not* changed to a full-weight-vector distance.** It still
>   keys on the scalar territory weight `wArea` (matching the scalar
>   `ORDER_PRESETS` that `align_territory.py` emits). The "surgical patch" below
>   documents an option that was considered but not adopted.

### Surgical patches

**`order.js`** — nearest preset over the full weight vector:

```js
function nearestPreset(presets, params) {
  var bestKey = null, bestDist = Infinity;
  for (var name in presets) {
    if (!presets.hasOwnProperty(name)) continue;
    var w = presets[name], d = 0;          // w is { wPop, wArea, wGdp, ... }
    for (var k in w) d += Math.pow((w[k] || 0) - (params[k] || 0), 2);
    if (d < bestDist) { bestDist = d; bestKey = name; }
  }
  return bestKey;
}
// pickOrder(): pass the whole params object to nearestPreset(presets, params)
```

**`compute_orders.py`** — generalize the blend and presets:

```python
# territory/pop/gdp weights per preset (fractions, summing to 1)
POWER_PRESETS = {
    "Demographic": {"wPop": 1.0, "wArea": 0.0, "wGdp": 0.0},
    "Balanced":    {"wPop": 0.34, "wArea": 0.33, "wGdp": 0.33},
    "Sparks-led":  {"wPop": 0.25, "wArea": 0.55, "wGdp": 0.20},
    "Economic":    {"wPop": 0.25, "wArea": 0.15, "wGdp": 0.60},
}
COMPONENTS = {"wPop": "pop_share", "wArea": "area_share", "wGdp": "gdp_share"}

def width_composite_n(shares_by_key, weights):
    """shares_by_key: {weightKey: DataFrame(year×polity share)}. Per-cell weight
    renormalization over available components, then per-slice normalize."""
    import numpy as np
    keys = list(weights)
    mats = {k: shares_by_key[k].to_numpy() for k in keys}
    has = {k: ~np.isnan(mats[k]) for k in keys}
    val = {k: np.nan_to_num(mats[k]) for k in keys}
    wsum = sum(np.where(has[k], weights[k], 0.0) for k in keys)
    blend = sum(np.where(has[k], weights[k], 0.0) * val[k] for k in keys)
    blend = np.divide(blend, wsum, out=np.zeros_like(blend), where=wsum > 0)
    row = blend.sum(axis=1, keepdims=True)
    return np.divide(blend, row, out=np.zeros_like(blend), where=row > 0)
```

(Build `gdp_share` from `gdp_int_usd.csv` ÷ world-GDP-per-year, exactly like
`pop_share`.)

**`lens-adapter.js`** — pick the control by component count:

```js
var composite = LENS_BY_ID[id];
if (composite.components && composite.components.length >= 3) {
  renderWeightBars(composite);   // one labeled slider per component, auto-normalized
} else {
  renderBalanceBar();            // the bipolar Pop↔Territory control
}
```

For weight bars, normalize on input so the displayed weights always sum to 100%
(drag one, the rest yield proportionally) — keeps the composite honest and the
sliders legible.

---

## Part B — The sensitivity view

The thesis feature. Because *you* define the metric, the project can show how
fragile or robust a ranking is to that choice — turning the weights from a toy
into an analytical instrument.

### The insight that makes it cheap

A composite share is a **linear blend** of the components' within-slice shares,
before the final per-slice normalization. For any polity that has all
components, `blend_p(w) = Σ_c w_c · cShare_{c,p}` is linear in `w`, and the
leader at weights `w` is `argmax_p blend_p` (the normalizer is shared). So:

- "Who leads" as `w` varies over the weight simplex is the **upper envelope of
  planes** — the simplex partitions into convex regions, one per polity. No
  dense simulation needed in principle.
- For v1 we sample the simplex on a coarse grid (a few hundred dot products on
  the precomputed component shares — milliseconds, no engine recompute). The
  exact convex-region rendering is a clean upgrade later.

### What it computes (all client-side, `sensitivity.js`)

- `leaderSweep(lens, year, R)` — over a simplex grid, the leading polity at each
  weight point. 2 components → a 1-D strip; 3 → a ternary triangle.
- `rankStability(lens, polityId, year, R)` — fraction of the weight space where
  the focused polity holds each rank, plus its share range. Drives the readout:
  *"India leads across 41% of how you could define power; Han across 33%."*
- `robustnessRibbon(lens, polityId, R)` — per slice, the min/max share of the
  focused polity across all swept weights. Drives a translucent band around the
  focused stream: how much its width depends on your choice.

### The UI

A small panel, linked to the focused polity and the hovered year:

- **2 components** — a horizontal Population↔Territory strip, segmented and
  colored by leader, with a marker at your current weights.
- **3 components** — a **ternary triangle** (vertices Population / Territory /
  GDP), filled by leader color, your current weights shown as a dot. Drag the
  weight bars and watch the dot cross between regions; the chart reorders in
  lockstep. This diagram *is* the argument: it shows that "who was most powerful"
  is a function of a definition, and draws the definition's geography.
- **Readout line** — the rank-stability sentence above.
- **Robustness ribbon** — drawn on the focused stream by the renderer, fed by
  `robustnessRibbon`. (One hook in Demograph's focus-draw; everything else is
  self-contained.)

### Honesty carries through

When the GDP weight is high and the year is pre-1500, the panel notes that the
GDP axis is low-confidence there — so a dramatic "economic power" reordering of
antiquity is shown for what it is: an artifact of weighting a guess.
