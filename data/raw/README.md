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
- Source: [Clio Infra](https://clio-infra.eu/) Urbanization Ratio
  ([IISG Dataverse `hdl:10622/LZ0Y36`](https://datasets.iisg.amsterdam/dataset.xhtml?persistentId=hdl:10622/LZ0Y36),
  `Urbanization_ratio-historical.xlsx`).
- Columns required: `country_iso, year, urban_pct`.
- Build it from the raw workbook: `python pipeline/build_clio_urbanization.py`
  (reshapes wide→long, maps ISO-numeric→ISO-A3 via Natural Earth, interpolates to
  slice years).
- Then: `python pipeline/compute_complexity.py` → `data/processed/vectors/urban_pop.csv`.
- **Coverage: 1500–2015 only.** Clio's series runs 1500–2000 (the 2015 slice holds
  the 2000 value forward); there is no source for pre-1500 urbanization here, so the
  lens is blank before 1500 — it is a modern-era metric by construction. (A global
  pre-1500 fill would need city-level data such as Reba et al. 2016.)

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
