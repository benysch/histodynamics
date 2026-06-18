"""
emit_facts.py
=============
SUPERSEDED — not part of the live pipeline. This is the vendored Demograph
template; it assumes a flat polity_id taxonomy and emits only population + area
(no GDP, no vectors), reading inputs that aren't in this repo. The shipped
web/facts.js / totals.js / polities.js / orders.js are produced by
pipeline/align_territory.py (keyed by aggregated streams, with GDP + dynamic
vectors threaded in). Kept for reference; do not run.

Join the processed per-polity tables into the three JS files the static
frontend loads. Emits RAW facts only; the frontend turns them into per-lens
shares (see docs/metric-layer.md).

Outputs (assigned to globals so the page needs no build step / no fetch):
  web/polities.js   ->  window.POLITIES = [ {id, name, civ, founded?}, ... ]
  web/facts.js      ->  window.FACTS    = { "<year>": { "<polityId>": {population, area_km2} } }
  web/totals.js     ->  window.TOTALS   = { "<year>": {population, area_km2} }

INPUT ASSUMPTIONS (rename columns to match your processed files):
  population:  data/processed/population_shares.csv  -> polity_id, year, population
               (Demograph's compute_shares.py output. If it stores a *share*
               instead of raw persons, multiply by the world total for that
               year here, or change compute_shares.py to emit raw persons. The
               frontend wants raw.)
  area:        data/processed/area_km2.csv           -> polity_id, year, area_km2
  metadata:    data/processed/polities.csv           -> polity_id, name, civ[, founded]
  world pop:   data/processed/world_population.csv    -> year, population
               (exogenous HYDE world total per slice, used for the honest
               residual band on the population lens.)
"""

import argparse
import json
from pathlib import Path

import pandas as pd

# Exogenous denominator for the territory lens: total ice-free land area.
# Constant across slices (continents don't move on this timescale); used so the
# "unmapped land" residual is honest rather than defined away. Tweak to taste.
WORLD_LAND_KM2 = 104_000_000.0  # ~ice-free land; ~149M incl. ice sheets


def _read(path: Path, cols: set) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = cols - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} missing columns: {missing}")
    return df


def emit_js(var: str, obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    path.write_text(f"window.{var} = {payload};\n", encoding="utf-8")
    print(f"wrote {path}  ({path.stat().st_size:,} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pop", default="data/processed/population_shares.csv")
    ap.add_argument("--area", default="data/processed/area_km2.csv")
    ap.add_argument("--meta", default="data/processed/polities.csv")
    ap.add_argument("--world-pop", default="data/processed/world_population.csv")
    ap.add_argument("--out-dir", default="web")
    args = ap.parse_args()

    pop = _read(Path(args.pop), {"polity_id", "year", "population"})
    area = _read(Path(args.area), {"polity_id", "year", "area_km2"})
    meta = _read(Path(args.meta), {"polity_id", "name", "civ"})
    wpop = _read(Path(args.world_pop), {"year", "population"})

    out_dir = Path(args.out_dir)

    # --- polities.js -------------------------------------------------------
    cols = ["polity_id", "name", "civ"] + (["founded"] if "founded" in meta else [])
    polities = [
        {("id" if k == "polity_id" else k): (None if pd.isna(v) else v)
         for k, v in row.items()}
        for row in meta[cols].to_dict("records")
    ]
    emit_js("POLITIES", polities, out_dir / "polities.js")

    # --- facts.js : { year: { polityId: {population, area_km2} } } ---------
    facts: dict[str, dict[str, dict]] = {}

    def slot(year, pid) -> dict:
        return facts.setdefault(str(int(year)), {}).setdefault(str(pid), {})

    for r in pop.itertuples(index=False):
        if pd.notna(r.population):
            slot(r.year, r.polity_id)["population"] = float(r.population)
    for r in area.itertuples(index=False):
        if pd.notna(r.area_km2):
            slot(r.year, r.polity_id)["area_km2"] = float(r.area_km2)

    emit_js("FACTS", facts, out_dir / "facts.js")

    # --- totals.js : exogenous per-slice denominators ----------------------
    totals = {
        str(int(r.year)): {
            "population": float(r.population),
            "area_km2": WORLD_LAND_KM2,
        }
        for r in wpop.itertuples(index=False)
    }
    emit_js("TOTALS", totals, out_dir / "totals.js")


if __name__ == "__main__":
    main()
