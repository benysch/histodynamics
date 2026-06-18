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
  full historical dataset, with the metric layer wired in: a "Measure by"
  selector drives `render()` through the engine. **Population**, **territory**,
  and **relative power** (a population↔territory blend with live weight sliders)
  are all live; **economy** is mounted but disabled until GDP facts land. Switch
  to Territory and the Steppe swells while densely-populated regions shrink — the
  re-measurement the project is about. The seam is reversible — absent
  `web/facts.js` it falls back to the population-only chart. See
  [`docs/INTEGRATION.md`](docs/INTEGRATION.md).
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

# 2. Territory, aligned to Demograph's 262 aggregated streams and emitted as the
#    metric-layer globals the renderer consumes. Downloads Cliopatria (~44 MB,
#    ephemeral, gitignored under data/raw/):
curl -L https://raw.githubusercontent.com/Seshat-Global-History-Databank/cliopatria/main/cliopatria.geojson.zip \
     -o data/raw/cliopatria.geojson.zip && (cd data/raw && unzip -o cliopatria.geojson.zip)
python pipeline/align_territory.py   # -> web/polities.js, facts.js, totals.js, orders.js
```

`align_territory.py` reproduces `export_web.py`'s raw→stream mapping (prominent
polities by name; the rest rolled into per-family "Smaller X" bundles via the
same classifier) so area shares the renderer's keys. It supersedes the flat
`compute_area.py`/`emit_facts.py` template, which assumed a single `polity_id`
taxonomy that never reconciled with the aggregated streams.

Area is **exclusive** (overlaps resolved): polygons are rasterized largest-first
onto an equal-area grid (EPSG:6933, 5 km) so a contested cell counts once, for
the smallest polity covering it — `compute_area.py`'s smaller-wins rule, done on
a grid (needs `rasterio`). Removing double-counts drops average mapped land from
33.6M to 29.7M km²/slice; the modern world reaches ~135M km² (most land is in
states), so the per-slice denominator still tracks the mapped total there.

`align_territory.py` also threads in GDP (step 3) when `gdp_intusd.csv` exists,
emitting `facts.js` with population + territory + economy in one pass.

```bash
# 3. Economy (GDP). Downloads Maddison (~1.8 MB) + Natural Earth 50m (~0.8 MB),
#    builds compute_gdp's inputs, attributes GDP, then re-runs align (which now
#    threads gdp_int_usd into facts.js):
curl -L https://www.rug.nl/ggdc/historicaldevelopment/maddison/data/mpd2020.xlsx -o data/raw/mpd2020.xlsx
curl -L https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip -o data/raw/ne_50m_admin_0_countries.zip
python pipeline/build_gdp_inputs.py    # -> maddison_gdppc / region_for_country / polity_country_pop
python pipeline/compute_gdp.py         # -> data/processed/gdp_intusd.csv
python pipeline/align_territory.py     # re-emit facts.js with population + area + GDP
```

GDP method (`docs/gdp-and-sensitivity.md`): each polity's population is split
across the modern countries its territory covers, each country-share valued at
that country's Maddison GDP-per-capita for the year, summed. The documented
method uses HYDE rasterization for the split; `build_gdp_inputs.py` approximates
it by **territory** area-fraction (Cliopatria × Natural Earth) since HYDE isn't
vendored. Maddison gdp-per-capita is interpolated onto the slice years within
each country's observed span.

**Honesty (built in):** most countries' Maddison series start in the 1800s, so
pre-1900 GDP rests largely on regional/world-mean fallbacks (`est_frac` ≈ 1) and
the Economy lens degrades toward Population — a true statement about what's
knowable. Where real figures exist (China from antiquity, Europe from ~1500) it
diverges sharply: at 2000 the USA is 23% of world GDP but 5% of population.

Each lens also gets its own **wiggle-minimized stacking order** (population keeps
Demograph's; territory, economy, and each power preset are recomputed in
`align_territory.py`), so switching lens *re-stacks* the chart rather than only
re-scaling it — the Steppe rises from the edge to the centre under Territory.
The composite snaps to its nearest preset's order while you drag (`order.js`),
so weights only rescale streams between presets.

**Known limits:** the area-weighted GDP population split (vs HYDE-weighted)
mainly affects multi-country empires in the modern era; exclusive area is
grid-resolved at 5 km, so polities smaller than a few cells are undercounted;
the succession-fidelity constraint on stream adjacency (`compute_orders.py`) is
skipped. All are future refinements.

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
