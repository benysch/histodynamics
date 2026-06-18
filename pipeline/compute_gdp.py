"""
compute_gdp.py
==============
Attribute GDP to historical polities and emit raw GDP per polity per slice ->
data/processed/gdp_intusd.csv  (international dollars, Maddison basis).

Method (reuses the population rasterization; see docs/gdp-and-sensitivity.md):
  cell GDP   = cell population (HYDE) * gdp-per-capita of the cell's MODERN
               country that year (Maddison).
  polity GDP = sum of cell GDP over the cells assigned to that polity.

In practice we don't re-rasterize here: we consume a per-(year, polity, country)
population breakdown that the rasterization can emit alongside the polity
assignment (add the Natural Earth country id when burning cells). GDP is then a
weighted sum over that breakdown.

Honesty: Maddison gdp-per-capita is real for the modern era and an educated
guess before ~1500, near a subsistence floor. Where a country-year is missing we
fall back to a region/world mean and mark that population as ESTIMATED, which
feeds a GDP residual. Pre-1500 the GDP lens therefore degrades toward the
population lens by construction -- a true statement about what is knowable.

INPUTS (rename to match your processed files):
  data/processed/polity_country_pop.csv  -> year, polity_id, country_iso, population
       (one row per polity x modern-country intersection per slice)
  data/processed/maddison_gdppc.csv        -> country_iso, year, gdppc   (int$)
  data/processed/region_for_country.csv    -> country_iso, region        (for fallback)
OUTPUT:
  data/processed/gdp_intusd.csv            -> polity_id, year, gdp_int_usd, est_frac
       est_frac = share of the polity's GDP that rested on a fallback gdppc.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SUBSISTENCE_GDPPC = 600.0  # int$ floor when no estimate exists at all (~Maddison subsistence)


def load(args):
    pcp = pd.read_csv(args.polity_country_pop)   # year, polity_id, country_iso, population
    gpc = pd.read_csv(args.gdppc)                # country_iso, year, gdppc
    reg = pd.read_csv(args.region)               # country_iso, region
    return pcp, gpc, reg


def build_fallbacks(gpc, reg):
    """Region-mean and world-mean gdppc per year, for missing country-years."""
    g = gpc.merge(reg, on="country_iso", how="left")
    region_mean = (g.groupby(["region", "year"])["gdppc"].mean()
                     .rename("gdppc_region").reset_index())
    world_mean = (gpc.groupby("year")["gdppc"].mean()
                    .rename("gdppc_world").reset_index())
    return region_mean, world_mean


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--polity-country-pop", default="data/processed/polity_country_pop.csv")
    ap.add_argument("--gddpc", "--gdppc", dest="gdppc", default="data/processed/maddison_gdppc.csv")
    ap.add_argument("--region", default="data/processed/region_for_country.csv")
    ap.add_argument("--out", default="data/processed/gdp_intusd.csv")
    args = ap.parse_args()

    pcp, gpc, reg = load(args)
    region_mean, world_mean = build_fallbacks(gpc, reg)

    # attach the best available gdppc to each (country, year), tracking whether
    # it came from a real figure or a fallback.
    df = pcp.merge(reg, on="country_iso", how="left")
    df = df.merge(gpc, on=["country_iso", "year"], how="left")            # gdppc (real)
    df = df.merge(region_mean, on=["region", "year"], how="left")        # gdppc_region
    df = df.merge(world_mean, on=["year"], how="left")                   # gdppc_world

    real = df["gdppc"].notna()
    gdppc = df["gdppc"]
    gdppc = gdppc.fillna(df["gdppc_region"]).fillna(df["gdppc_world"]).fillna(SUBSISTENCE_GDPPC)

    df["cell_gdp"] = df["population"] * gdppc
    df["cell_gdp_est"] = np.where(real, 0.0, df["cell_gdp"])  # GDP resting on a fallback

    out = (df.groupby(["polity_id", "year"])
             .agg(gdp_int_usd=("cell_gdp", "sum"),
                  gdp_est=("cell_gdp_est", "sum"))
             .reset_index())
    out["est_frac"] = np.divide(out["gdp_est"], out["gdp_int_usd"],
                                out=np.zeros(len(out)), where=out["gdp_int_usd"] > 0)
    out = out[["polity_id", "year", "gdp_int_usd", "est_frac"]]
    out = out.sort_values(["year", "polity_id"]).reset_index(drop=True)

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(p, index=False)
    print(f"wrote {len(out):,} rows -> {p}  "
          f"(median est_frac {out['est_frac'].median():.2f})")


if __name__ == "__main__":
    main()
