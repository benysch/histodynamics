# Metric Layer — Design Spec (v1)

> **Note — superseded in part by v2.** This v1 spec describes a two-component
> (population + territory) "relative power" lens. The shipped lens is **v2**:
> three components (population, territory, **GDP**), default weights
> 0.34/0.33/0.33, presets Demographic / Balanced / Sparks-led / Economic. For
> the current schema and composite math see
> [`gdp-and-sensitivity.md`](gdp-and-sensitivity.md) and `web/lenses.js`. The
> §2 `Fact` / `SliceTotals` interfaces below also omit `gdp_int_usd` / `gdp`,
> which the live code emits and reads.

A swappable-metric histomap. Same stream-graph machinery as Demograph; the
*metric* is a first-class, user-switchable dimension. Switching lenses reorders
and rescales the whole chart live — including an honest, **user-defined**
"relative power" lens that Demograph deliberately refused to ship.

---

## 1. The one move

Insert a **metric layer** between the raw data and the renderer:

```
raw facts ──▶ [ LENS: (polity, slice) → value ] ──▶ normalize per slice ──▶ stream order ──▶ draw
                         ▲
                    swappable
```

Everything Demograph already does — civilizational color, focus/click, palettes,
minimap, SVG/PNG export — sits *downstream* of this seam and never changes. A new
metric is a new lens, nothing else.

**Invariant:** lenses are pure and read **raw, additive facts only** (people, km²,
dollars). They never see shares, colors, or order. Normalization is the engine's
job, not the lens's. This is what keeps "add a metric" cheap.

---

## 2. Data schema

Keep the fact table **raw and unitful**. No derived metrics, no shares, no nulls-as-zero
(missing = unknown, which feeds the honest residual band).

```ts
type SliceYear = number;   // negative = BCE
type PolityId  = string;

interface Polity {
  id: PolityId;
  name: string;
  civ: string;             // civilization family key → drives color (lens-independent)
  founded?: SliceYear;
  meta?: Record<string, unknown>;
}

// Raw additive facts ONLY. Add fields here as you add data sources.
interface Fact {
  population?: number;     // persons        (HYDE × Cliopatria)
  area_km2?:   number;     // square km      (Cliopatria polygon area)
  // v2 slots, same shape:
  // gdp_int_usd?: number; // Maddison (needs polity↔country mapping — see §8)
  // mil_spend?:   number;
}

// facts[year][polityId] → Fact.  Absent key = UNKNOWN, not zero.
type FactTable = Record<SliceYear, Record<PolityId, Fact>>;

// Exogenous per-slice world totals, for honest residuals (§6).
interface SliceTotals { population?: number; area_km2?: number; }
type TotalsTable = Record<SliceYear, SliceTotals>;
```

---

## 3. Lens interface

Two kinds. A **simple** lens reads one fact; a **composite** lens blends other
lenses' within-slice shares with adjustable weights. The composite is the whole
point — it makes "relative power" a knob, not an assertion.

```ts
interface LensParamSpec {           // auto-renders a slider in the UI
  key: string; label: string;
  min: number; max: number; step: number; default: number;
}

// One raw fact, normalized by the engine.
interface SimpleLens {
  kind: 'simple';
  id: string; label: string; description: string;
  unit: string;                     // present ⇒ "absolute" width mode allowed (§5)
  extract: (f: Fact) => number | null;
  totalKey?: keyof SliceTotals;     // which exogenous total defines the residual (§6)
}

// Weighted blend of OTHER lenses' per-slice shares.
interface CompositeLens {
  kind: 'composite';
  id: string; label: string; description: string;
  // no `unit` ⇒ share-only; absolute mode disabled (§5)
  components: { lensId: string; weightKey: string }[];
  params: LensParamSpec[];          // the weights → sliders
  presets?: Record<string, Record<string /*weightKey*/, number>>;
}

type Lens = SimpleLens | CompositeLens;
```

---

## 4. Normalization & the composite math

The subtle part. Components live on different scales (people vs km²), so you
**normalize each component to a within-slice share first**, *then* weight. Weights
become unit-free and the sliders mean what users expect.

For slice `s`, polity `p`:

**Simple lens** `L`:
```
raw[p]   = L.extract(facts[s][p])              // null → skip
denom    = totals[s][L.totalKey]  ??  Σ raw    // exogenous total if given, else sum
share[p] = raw[p] / denom
residual = 1 − Σ share                         // honest gap (§6)
```

**Composite lens** `C` with weights `w`:
```
for each component c:  cShare_c[p] = simpleShareOf(c.lensId, s, p)   // recurse into §4 simple
for each polity p:
   avail  = components where cShare_c[p] != null
   wsum   = Σ_{c∈avail} w[c.weightKey]          // RE-NORMALIZE weights over available
   blend[p] = Σ_{c∈avail} (w[c.weightKey]/wsum) · cShare_c[p]
share[p]  = blend[p] / Σ blend
residual  = Σ_c (w[c.weightKey]/Σw) · residual_c    // weighted blend of component gaps
```

Re-normalizing weights *per polity* over the components it actually has means a
polity with population but no GDP isn't silently penalized — it's scored on what's
known. Same honesty principle as the residual band, applied to the weighting.

**Worked micro-example** (one slice, weights pop=0.3, territory=0.7):

| polity | pop share | area share | blend = .3·pop + .7·area | final share |
|--------|-----------|-----------|--------------------------|-------------|
| Rome   | 0.20      | 0.35      | 0.305                    | 0.43        |
| Han    | 0.30      | 0.25      | 0.265                    | 0.37        |
| (rest) | 0.50      | 0.40      | 0.430→ (residual etc.)   | 0.20        |

Slide territory→population and Rome shrinks, Han grows: that live reorder is the
insight you wanted to be able to *see*.

---

## 5. Width mode × lens

Demograph's "share vs absolute" toggle interacts with the lens:

- **Simple lens** has a `unit` → both modes valid. Absolute uses `raw[p]` in its
  native unit (the trumpet-bell effect for population).
- **Composite lens** has no `unit` (a blend of shares has no natural unit) →
  **absolute disabled**, toggle greyed with a tooltip. Share mode only. Don't fake
  an absolute scale here; it would be the exact undefinedness Demograph criticized.

---

## 6. Missing data & residuals (keep Demograph's honesty)

- Missing fact = unknown, never zero. Unknowns drop out of the numerator and show
  up as the gray **residual / unmapped** band = `1 − Σ mapped shares`.
- Prefer an **exogenous** denominator when you have one (`totals[s].population` from
  HYDE is independent of how much Cliopatria mapped that year), so the residual
  reflects *real* unmapped population rather than being defined away.
- For `area_km2`, the denominator is fixed habitable land — also exogenous.
- Composite residual = weighted blend of its components' residuals (formula above).

---

## 7. Reference lenses for v1 (zero new data)

All three run off `population` + `area_km2`, both already produced by the
Demograph pipeline — no new sources needed to ship.

```ts
const POPULATION: SimpleLens = {
  kind: 'simple', id: 'pop', label: 'Population share',
  description: "Share of world population under each polity (Demograph's metric).",
  unit: 'persons', totalKey: 'population',
  extract: f => f.population ?? null,
};

const TERRITORY: SimpleLens = {
  kind: 'simple', id: 'area', label: 'Territory share',
  description: 'Share of mapped land area under each polity.',
  unit: 'km²', totalKey: 'area_km2',
  extract: f => f.area_km2 ?? null,
};

const RELATIVE_POWER: CompositeLens = {
  kind: 'composite', id: 'power', label: 'Relative power (defined by you)',
  description:
    'Sparks shipped this metric undefined. Here you define it: a weighted blend ' +
    'of population and territory. Slide the weights and watch the chart reorder.',
  components: [
    { lensId: 'pop',  weightKey: 'wPop'  },
    { lensId: 'area', weightKey: 'wArea' },
  ],
  params: [
    { key: 'wPop',  label: 'Population', min: 0, max: 1, step: 0.05, default: 0.5 },
    { key: 'wArea', label: 'Territory',  min: 0, max: 1, step: 0.05, default: 0.5 },
  ],
  presets: {
    'Demographic (= Demograph)': { wPop: 1.0, wArea: 0.0 },
    'Balanced':                  { wPop: 0.5, wArea: 0.5 },
    'Sparks-ish (territory-led)':{ wPop: 0.3, wArea: 0.7 },
  },
};
```

v2 lenses (`gdp`, `mil`) slot into `RELATIVE_POWER.components` and the preset rows
without touching the engine.

---

## 8. How it plugs into Demograph

What **stays**: civ classification & color, focus/click, palettes, minimap, export,
the whole HYDE×Cliopatria pipeline that produces population.

What **changes / gets added**:

1. **Pipeline emits raw facts, not pre-baked shares.** Today Demograph ships
   `web/data.js` with population already turned into a stream. Instead emit:
   - `web/polities.js` → `Polity[]`
   - `web/facts.js`    → `FactTable` (population **and** `area_km2` — area is just
     polygon area you already have at rasterization time, ~free to add)
   - `web/totals.js`   → `TotalsTable`
   - `web/lenses.js`   → the lens config above (pure frontend, no data)

2. **Stream order is now per-lens.** Order minimizes wiggle of the *displayed*
   widths, which differ by lens. Cheapest robust option for v1: precompute order
   in the pipeline for each simple lens **and each composite preset**, ship
   `orders[lensId|presetName]`, and swap instantly on lens change. Free-dragging
   the composite sliders then reuses the nearest preset's order (good enough; live
   re-optimization is a v2 nicety). Color stays order-independent — Demograph
   already decoupled them, which is what makes this work.

3. **UI:** a lens selector + (for composite) auto-generated weight sliders from
   `params` and a preset dropdown. Grey out the absolute toggle when the active
   lens has no `unit`.

---

## 9. Build order (suggested commits)

1. Schema + `facts.js`/`totals.js`/`polities.js` emit from pipeline (add area).
2. Engine: `computeShares(lens, slice)` for simple lenses + residuals (§4, §6).
3. Composite engine + re-normalized weights (§4).
4. Lens config (§7) + selector UI + sliders/presets.
5. Per-lens precomputed orders (§8.2) and instant swap.
6. Absolute-mode gating (§5).

Static page throughout — drops onto Vercel with no build step, same as Demograph.
