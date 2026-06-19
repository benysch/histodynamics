# data/raw/ — upstream sources (not committed)

These files are large and/or licensed separately, so they are git-ignored. Stage
them here, then run the pipeline. Nothing in the repo fetches them automatically.

## For the territory / economy lenses (existing)

| File | Source | Used by |
|------|--------|---------|
| `cliopatria_polities_only.geojson` | [Cliopatria](https://github.com/Seshat-Global-History-Databank/cliopatria) (Type==POLITY, EPSG:4326) | `align_territory.py`, `compute_culture.py` |
| HYDE grids | [HYDE 3.3](https://www.pbl.nl/en/image/links/hyde) (range-fetched by the pipeline) | population rasterization |
| Maddison + Natural Earth | for GDP attribution | `compute_gdp.py` |

## For the new data-gated lenses

**Structural complexity** — city-level urban population (all eras)
- Source: Reba, Reitsma & Seto (2016), *Spatializing 6,000 years of global
  urbanization* — three wide CSVs on figshare
  ([Chandler `10.6084/m9.figshare.2059494`](https://doi.org/10.6084/m9.figshare.2059494),
  Modelski Ancient `…2059497`, Modelski Modern `…2059500`). Stage them as
  `reba_chandler.csv`, `reba_modelski_ancient.csv`, `reba_modelski_modern.csv`.
  Also needs `cliopatria_polities_only.geojson` (above).
- Then: `python pipeline/compute_urban_cities.py` → `data/processed/vectors/urban_pop.csv`.
  Cities are interpolated onto the slice years and spatially joined to the polity
  active at each slice — **coverage 3700 BC – AD 2000** (the 2015 slice carries the
  2000 value forward for still-living cities), so the lens is populated across the
  whole histomap.
- *Modern-only alternative:* [Clio Infra](https://clio-infra.eu/) Urbanization Ratio
  ([IISG `hdl:10622/LZ0Y36`](https://datasets.iisg.amsterdam/dataset.xhtml?persistentId=hdl:10622/LZ0Y36))
  via `build_clio_urbanization.py` + `compute_complexity.py` — country urbanization×
  population, but **1500+ only**. Superseded by the city data above; kept for
  comparison.

**Cultural centrality** — `pantheon_1.csv`
- Source: [MIT Pantheon 1.0](https://www.kaggle.com/datasets/mit/pantheon-project)
  (figures with biographies in 25+ languages).
- Columns required: `lon, lat, birth_year` (common spellings like `LON`/`LAT`/`birthyear`
  are auto-normalized).
- Also needs `cliopatria_polities_only.geojson` (above).
- Then: `python pipeline/compute_culture.py` → `data/processed/vectors/culture.csv`
  (cumulative **stock** of cultural capital by default; `--mode flow` for the
  one-slice birth-pulse version).

After staging and running the two scripts, re-run `pipeline/align_territory.py` to
re-emit `web/facts.js` / `web/totals.js` with the new facts attached; the lenses
then light up in the UI automatically.
