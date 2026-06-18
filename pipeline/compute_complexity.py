"""
compute_complexity.py
=====================
Massify an INTENSIVE rate (urbanization %) into an EXTENSIVE mass (urban
persons) the metric layer can sum, then key it to polities.

  data/processed/polity_country_pop.csv  -> year, polity_id, country_iso, population
       (one row per polity x modern-country intersection per slice)
  data/raw/clio_infra_urbanization.csv   -> country_iso, year, urban_pct
       (urbanization rate per modern country per year; Clio Infra, clio-infra.eu)

The engine works strictly on extensive (additive) facts; a percentage is not
additive across countries, so we convert it first:

  urban_pop = population * (urban_pct / 100)

and sum the result per polity per slice. The frontend's URBANIZATION lens then
divides by world urban population to get a share -- the same path GDP and area
take. Urbanization is a reliable proxy for structural complexity: institutional
maturity and the shift from agrarian subsistence toward dense, specialized hubs.

OUTPUT:
  data/processed/vectors/urban_pop.csv   -> polity_id, year, urban_pop
       (picked up automatically by align_territory.py's vector scanner -- a new
        dimension is a new file here, no code change downstream.)
"""

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pop", default=str(ROOT / "data/processed/polity_country_pop.csv"))
    ap.add_argument("--urban", default=str(ROOT / "data/raw/clio_infra_urbanization.csv"))
    ap.add_argument("--out", default=str(ROOT / "data/processed/vectors/urban_pop.csv"))
    args = ap.parse_args()

    pop_path, urban_path = Path(args.pop), Path(args.urban)
    if not urban_path.exists():
        raise SystemExit(
            f"raw urbanization file not found: {urban_path}\n"
            f"Stage it (columns: country_iso, year, urban_pct) and re-run. "
            f"This script does not fetch data."
        )

    pop = pd.read_csv(pop_path)          # year, polity_id, country_iso, population
    urb = pd.read_csv(urban_path)        # country_iso, year, urban_pct

    merged = pop.merge(urb, on=["country_iso", "year"], how="inner")
    merged["urban_pop"] = merged["population"] * (merged["urban_pct"] / 100.0)

    out = (merged.groupby(["polity_id", "year"], as_index=False)["urban_pop"]
                 .sum())

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)   # Phase 5 guardrail
    out.to_csv(out_path, index=False)
    print(f"wrote {out_path}  ({len(out):,} polity-years, "
          f"{out['urban_pop'].sum()/1e6:.1f}M urban persons total)")


if __name__ == "__main__":
    main()
