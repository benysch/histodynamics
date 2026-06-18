# Polimetric

**A histomap you can re-measure.** Four thousand years of world history as a
single vertical stream graph — but the *metric* setting the width of each stream
is a dimension you switch live. Population share, territory share, or a
**relative power** lens whose definition you set yourself, watching the whole
chart reorder as you slide the weights.

> Working title — rename throughout before going public if you pick another.

🔗 **Live demo:** _(add your Vercel URL)_ · or open [`web/index.html`](web/index.html) — static, no build step.

---

## Why this exists

John B. Sparks's 1931 *Histomap* sized each civilization by an undefined notion
of "relative power" — its most-criticized flaw. The brilliant
[Demograph](https://github.com/alexandrosm/Demograph) project answered that by
**replacing** power with one defensible metric: share of world population under
each polity.

Polimetric takes the opposite tack on the same critique. Instead of banishing
"relative power," it makes the **metric itself the variable**:

- Power was never undefinable — only *unspecified*. So you specify it.
- A composite lens blends population and territory (and later GDP, military
  spend, …) with **weights you control**. Slide them and the chart re-ranks in
  real time: territory-heavy empires trade places with populous ones.
- Ship it next to the rigorous lenses, honestly labeled "defined by you," so the
  contrast between *a metric you can defend* and *a metric you can shape* is the
  insight — not a footnote.

Everything downstream of the metric — civilizational color, region focus,
palettes, annotations, export — is derived from data, in the Demograph spirit.

## Lenses

| Lens | Width = | Notes |
|------|---------|-------|
| **Population share** | share of world population under each polity | the Demograph metric |
| **Territory share** | share of mapped land area | free from polygon area at rasterization |
| **Economic share** | share of world GDP (Maddison) | low confidence before ~1500; degrades toward population there |
| **Relative power** | weighted blend of the three above, **your weights** | presets: Demographic · Balanced · Sparks-led · Economic |

The composite iterates its components generically, so adding a metric (military
spend, …) is a new lens in `lenses.js` with **no engine change** — see the
design doc.

## Architecture

A **metric layer** sits between raw facts and the renderer: lenses read only
raw, additive facts (people, km²); the engine does all normalization and the
composite weighting. Adding a metric is a new lens, nothing else.

See [`docs/metric-layer.md`](docs/metric-layer.md) for the full schema, lens
signatures, and composite math.

```
raw facts ─▶ [ lens: (polity, slice) → value ] ─▶ normalize per slice ─▶ stream order ─▶ draw
                        ▲ swappable
```

## Run it

The visualization is a single static page — clone and open
[`web/index.html`](web/index.html), or visit the live demo. No bundler, no
server.

- [`web/index.html`](web/index.html) — the **real** Demograph renderer over the
  full historical dataset (population share). The borrowed foundation.
- [`web/preview.html`](web/preview.html) — a **multi-lens prototype** that drives
  the metric layer (population / territory / economy / relative power) over
  illustrative [`web/sample-data.js`](web/sample-data.js). It exists to demo
  lens-switching until the metric layer is wired into the real renderer per
  [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — a banner makes the distinction
  clear.

## Rebuild the data

The pipeline emits **raw facts**, not pre-baked shares — the frontend turns them
into whichever lens is selected.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip

# 1. Foundation, imported from Demograph (CC0 — see NOTICE; not vendored here yet):
#    download_hyde.py + compute_shares.py  -> population (persons) per polity per slice.
#    Place Cliopatria & Natural Earth in data/raw/ first.

# 2. This repo's metric-layer pipeline:
python pipeline/compute_area.py                   # territory (km²) per polity per slice
python pipeline/compute_gdp.py                    # GDP (Maddison) per polity per slice
python pipeline/compute_orders.py                 # baked per-lens stacking orders -> web/orders.js
python pipeline/emit_facts.py                     # -> web/facts.js, web/totals.js, web/polities.js
```

## Data & credits

This project reuses Demograph's pipeline and rendering and stands on the same
upstream historical data. Demograph is public-domain (CC0); the underlying data
sources are not all CC0 and ask for credit. See [`NOTICE`](NOTICE) for the full
attribution — please carry it forward if you reuse this.

## License

[CC0 1.0 Universal](LICENSE) — same as upstream Demograph; imposes nothing.
Note the data-source attributions in [`NOTICE`](NOTICE) and please carry them
forward if you reuse this.

## Acknowledgements

- [Demograph](https://github.com/alexandrosm/Demograph) by Alexandros Marinos —
  the pipeline, the rendering, and the framing this builds on.
- [HYDE 3.2.1](https://doi.org/10.17026/dans-25g-gez3) — gridded population
  reconstruction.
- [Cliopatria](https://github.com/Seshat-Global-History-Databank/cliopatria) —
  historical border polygons.
- [Natural Earth](https://www.naturalearthdata.com/) — modern region boundaries.
- John B. Sparks, *Histomap* (1931) — the original, homage not reproduced.
