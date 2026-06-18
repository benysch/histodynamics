# Wiring the metric layer into Demograph's renderer

Demograph's `web/index.html` is a single large static page. It builds its
stream **once** from a precomputed global (in `web/data.js`) and redraws on
sidebar changes. We don't replace its renderer — we regenerate that global from
the active lens and call its redraw. Its controls live in `#sidebar` as `.sb-sec`
sections built from `.seg`/`.opt`; our lens controls mount the same way and
inherit the palette.

## Two names to confirm first

Open `web/index.html` and find:

1. **The data global** — what `web/data.js` assigns and the draw reads. Likely
   `window.DATA` / `STREAMS` / `LAYERS`: an array of per-polity objects, each
   with a values-per-slice array. Note its exact field names.
2. **The redraw entry point** — the function that (re)renders the stream from
   that global when a sidebar control changes (e.g. `draw()` / `render()` /
   `update()`). That's what we'll call after swapping the data.

Everything else below is mechanical.

## Load order

In `<head>`, before Demograph's own `<script>` (and its `data.js`):

```html
<script src="polities.js"></script>
<script src="facts.js"></script>
<script src="totals.js"></script>
<script src="orders.js"></script>
<script src="lenses.js"></script>
<script src="engine.js"></script>
<script src="order.js"></script>
<script src="lens-adapter.js"></script>
```

`data.js` becomes optional — we generate its structure at runtime. Keep it only
if you want a no-JS fallback.

## The four edits

### 1. One adapter from our shape to Demograph's

`buildSeries()` returns clean layers (see its header). Map them to whatever
`data.js` provides. If Demograph already groups by polity with a `values` array,
this is nearly an identity:

```js
function adaptToDemograph(series) {
  // series.layers are bottom→top, each { id, name, civ, values:[per-year] }
  return series.layers.map(function (L) {
    return {
      id: L.id,
      name: L.name,
      civ: L.civ,              // Demograph's color fn keys off civ — reuse it
      values: L.values         // rename to match data.js's field if different
    };
  });
  // also hand series.residual to whatever draws the gray "unmapped" band,
  // and series.years to the x-scale if it isn't already fixed.
}
```

Leave Demograph's color, labels, focus, palettes, minimap, and export untouched
— they key off `id`/`civ`, which we preserve.

### 2. Hold the active lens and rebuild from it

Replace the one-time `DATA = (data.js global)` with:

```js
var current = { lensId: "pop", params: { wPop: 1, wArea: 0 }, widthMode: "share" };

function rebuild() {
  var series = buildSeries(current.lensId, current.params,
                           { widthMode: current.widthMode });
  DATA = adaptToDemograph(series);   // <- the global the draw reads
  draw();                            // <- Demograph's redraw entry point
}
```

### 3. Mount the lens controls into the sidebar

```js
mountLensControls({
  container: document.getElementById("sidebar"),
  onChange: function (s) {
    current.lensId   = s.lensId;
    current.params   = s.params;
    current.widthMode = s.widthMode;
    scheduleRebuild();               // debounced — see edit 4
  }
});
rebuild();                           // initial paint
```

If Demograph already has a width-mode toggle, either let ours drive `current`
and hide theirs, or bind theirs to `current.widthMode` and drop ours — don't run
both.

### 4. Debounce the slider drag

The composite balance fires on every step; redrawing ~68 slices each time is the
janky path. `order.js` already keeps the **stacking order stable** between
presets (only widths change mid-drag), so the redraw is cheap — but still coalesce:

```js
var raf = null;
function scheduleRebuild() {
  if (raf) cancelAnimationFrame(raf);
  raf = requestAnimationFrame(function () { raf = null; rebuild(); });
}
```

## Sanity checks after wiring

- Switch lens **Population → Territory**: streams keep their colors, ranking
  changes, order swaps instantly (precomputed).
- **Relative power**, drag toward Territory: Steppe rises, Han falls; the order
  holds steady until you cross a preset midpoint, then snaps once.
- **Absolute** greys out under Relative power, with the one-line reason.
- The gray residual band tracks the lens (largest under Territory, where much
  land is unmapped) — and is a *readout*, not a band, under the composite.
