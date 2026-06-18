# Build order

A commit sequence that reads cleanly: identity first, then the borrowed
foundation (clearly marked), then the novel metric layer built bottom-up, then
the integration that makes it visible. Each commit stands on its own.

---

### 1 — Project identity
`README.md` · `NOTICE` · `LICENSE` · `.gitignore`
> What this is and what it borrows. The project is named **Histodynamics**
> (an earlier "Polimetric" placeholder was renamed throughout). Confirm the
> Demograph author name in README acknowledgements.

### 2 — Import the foundation (CC0, from Demograph)
`web/index.html` · `pipeline/download_hyde.py` · `pipeline/compute_shares.py` ·
`pipeline/fingerprint.py` · region/transfer scripts · `requirements.txt` · `data/processed/*`
> One commit, message like "Import Demograph pipeline + renderer (CC0)". Keeps
> the borrowed code as a single legible baseline so every later diff is *your*
> work. Don't mix new code into this one.

### 3 — Design spec
`docs/metric-layer.md` · `docs/INTEGRATION.md` · `docs/BUILD_ORDER.md`
> The plan before the code. Optionally `docs/prototype-lens-controls.html` (the
> standalone UX demo) as a design reference — it's not part of the app.

### 4 — Raw-facts pipeline
`pipeline/compute_area.py` · `pipeline/emit_facts.py`
> Add territory; emit `web/facts.js`, `web/totals.js`, `web/polities.js`. Change
> `compute_shares.py` here if it emits shares rather than raw persons. Verify the
> emitted JS loads. (= design doc commit 1.)

### 5 — Metric engine: simple lenses
`web/lenses.js` (population + territory) · `web/engine.js` (simple + residual)
> `Engine.computeAll('pop')` returns correct per-slice shares with an honest
> residual. Unit-test the simple path. (= design doc commit 2.)

### 6 — Metric engine: composite
extend `web/lenses.js` (relative-power) · extend `web/engine.js` (composite)
> The weighted blend with per-polity weight renormalization. Unit-test the
> composite math against the worked example in the design doc — this is the
> subtle part. (= design doc commit 3.)

### 7 — Per-lens ordering
`pipeline/compute_orders.py` · `web/order.js`
> Emit `web/orders.js`; `pickOrder()` resolves a lens/preset to a baked order.
> Tune the two succession-fidelity thresholds against real output.

### 8 — Lens controls + adapter
`web/lens-adapter.js`
> `buildSeries()` + `mountLensControls()`. Renders the sidebar section; not yet
> wired to the chart. Confirm the control emits the right `{lensId, params,
> widthMode}` in the console.

### 9 — Renderer integration
edits to `web/index.html` per `docs/INTEGRATION.md`
> The four edits: `adaptToDemograph`, `rebuild()`, mount controls, debounce.
> Confirm the two names (data global, redraw fn) first. This is the commit where
> switching lenses visibly reorders the chart. Run the sanity checks.

### 10 — Polish & deploy
> Residual band wiring, absolute-mode gating check, reduced-motion, mobile
> sidebar, then connect Vercel. Tag `v0.1` — the core multi-lens histomap.

---

## v0.2 — deepen the lens (GDP + sensitivity)

These make relative power both deeper and self-auditing. They sit on top of a
shipped v0.1, so the core is provable before this tier lands.

### 11 — v0.2 design spec
`docs/gdp-and-sensitivity.md`
> Spec before code again. Documents the GDP attribution method, its honesty
> rules, and the sensitivity view's linearity insight.

### 12 — GDP as a third component
`pipeline/compute_gdp.py` · `web/lenses.js` (v2) · `emit_facts.py` (+gdp, +world GDP total) ·
generalize `pipeline/compute_orders.py`, `web/order.js`, `web/lens-adapter.js` (≥3 → weight bars)
> One coherent commit. `engine.js` is untouched — the composite already iterates
> N components, which is the architecture paying off. Verify the GDP lens
> degrades toward population pre-1500 (the honest tell).

### 13 — Sensitivity engine + panel
`web/sensitivity.js` · `web/sensitivity-panel.js`
> Leader-sweep, rank stability, robustness ribbon (all client-side dot products),
> plus the ternary phase diagram mounted in the sidebar. Optionally keep
> `docs/prototype-sensitivity-panel.html` as a design reference.

### 14 — Robustness ribbon in the renderer
edit to `web/index.html` (focus-draw hook per `sensitivity-panel.js`)
> Insert `ribbonPath()` as the first child of the focus group so the uncertainty
> band sits behind the solid stream. The one place this tier touches draw code.

### 15 — Polish & deploy v0.2
> Throttle the triangle's per-year repaint (cache component shares per year),
> GDP tooltips with `est_frac`, low-confidence note. Tag `v0.2`.

---

**Order discipline:** every commit from 4 on depends only on the ones before, so
you can stop at any point with a working tree. The core novel work is 4–9 (ships
as v0.1); the depth tier is 11–14 (v0.2). Everything a reviewer needs to
understand the idea is in the two spec commits, 3 and 11.
