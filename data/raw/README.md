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

**Structural complexity** — `clio_infra_urbanization.csv`
- Source: [Clio Infra](https://clio-infra.eu/) urbanization ratio.
- Columns required: `country_iso, year, urban_pct`.
- Then: `python pipeline/compute_complexity.py` → `data/processed/vectors/urban_pop.csv`.

**Cultural centrality** — `pantheon_1.csv`
- Source: [MIT Pantheon 1.0](https://www.kaggle.com/datasets/mit/pantheon-project)
  (figures with biographies in 25+ languages).
- Columns required: `lon, lat, birth_year` (common spellings like `LON`/`LAT`/`birthyear`
  are auto-normalized).
- Also needs `cliopatria_polities_only.geojson` (above).
- Then: `python pipeline/compute_culture.py` → `data/processed/vectors/culture.csv`.

After staging and running the two scripts, re-run `pipeline/align_territory.py` to
re-emit `web/facts.js` / `web/totals.js` with the new facts attached; the lenses
then light up in the UI automatically.
