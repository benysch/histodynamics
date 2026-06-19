"""
build_clio_urbanization.py
==========================
Stage data/raw/clio_infra_urbanization.csv (country_iso, year, urban_pct) from
the raw Clio Infra "Urbanization Ratio" workbook, the format compute_complexity.py
expects.

The workbook (data/raw/Urbanization_ratio-historical.xlsx) is wide: one row per
mapped entity, columns 1500..2015 holding the urban share. Modern-country rows
carry an ISO-numeric `ccode` (840 = USA, ...); historical `geacron/*` rows have
none and are skipped (their land is attributed via polity_country_pop already).
We melt to long, map ISO-numeric -> ISO-A3 via Natural Earth, and interpolate
each country onto the histomap slice years (the merge in compute_complexity is
exact on (country_iso, year)).

Note: Clio stores the ratio as a 0-1 fraction despite the "percentage" label;
compute_complexity divides urban_pct by 100, so we emit percent (fraction*100).
A constant factor cancels in the lens's share anyway.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "data" / "raw" / "Urbanization_ratio-historical.xlsx"
NE = ROOT / "data" / "raw" / "ne_50m_admin_0_countries.zip"
POP = ROOT / "data" / "processed" / "population_shares.csv"
OUT = ROOT / "data" / "raw" / "clio_infra_urbanization.csv"


def main():
    slices = [int(y) for y in sorted(pd.read_csv(POP, usecols=["year"])["year"].unique()) if y >= 1500]

    ne = gpd.read_file(NE)
    isonum_to_a3 = {int(r.ISO_N3): r.ISO_A3 for _, r in ne.iterrows()
                    if r.ISO_A3 and r.ISO_A3 != "-99" and str(r.ISO_N3).isdigit()}

    df = pd.read_excel(XLSX, sheet_name="Data", header=2)
    df = df[df["ccode"].notna()].copy()
    df["country_iso"] = df["ccode"].astype(int).map(isonum_to_a3)
    df = df[df["country_iso"].notna()]
    yearcols = [c for c in df.columns if isinstance(c, (int, float)) and 1500 <= c <= 2015]

    long = (df.melt(id_vars=["country_iso"], value_vars=yearcols,
                    var_name="year", value_name="r")
              .dropna(subset=["r"]))
    long["year"] = long["year"].astype(int)
    long = long.groupby(["country_iso", "year"], as_index=False)["r"].mean()

    rows = []
    for iso, g in long.groupby("country_iso"):
        s = g.set_index("year")["r"].sort_index()
        s = s[~s.index.duplicated()]
        lo, hi = s.index.min(), s.index.max()
        within = [y for y in slices if lo <= y <= hi]
        if not within:
            continue
        idx = sorted(set(s.index) | set(within))
        interp = s.reindex(idx).interpolate(method="index")
        last = float(s.iloc[-1])
        for y in slices:
            if y < lo:
                continue                        # no back-extrapolation: pre-1500 has no source
            val = float(interp.loc[y]) if y <= hi else last  # hold latest (Clio ends ~2000) to 2015
            rows.append((iso, y, round(val * 100.0, 3)))      # fraction -> percent

    out = pd.DataFrame(rows, columns=["country_iso", "year", "urban_pct"])
    out.to_csv(OUT, index=False)
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(out):,} rows, "
          f"{out.country_iso.nunique()} countries, years {out.year.min()}..{out.year.max()})")


if __name__ == "__main__":
    main()
