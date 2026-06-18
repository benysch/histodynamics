"""
build_gdp_inputs.py
===================
Build the three inputs compute_gdp.py expects, WITHOUT the HYDE rasterization
(which this repo doesn't vendor). The documented method splits a polity's
population across modern countries by rasterized HYDE cells; here we approximate
that split by the *area* fraction of the polity that falls in each modern
country (Natural Earth), then scale by the polity's known population for the
slice (population_shares.csv). Pre-1500 GDP rests on regional/subsistence
fallbacks regardless, so the area-vs-population approximation mostly affects
multi-country empires in the modern era — a documented limitation.

Outputs (data/processed/):
  maddison_gdppc.csv     country_iso, year, gdppc   (Maddison, interpolated to slices)
  region_for_country.csv country_iso, region        (Natural Earth SUBREGION)
  polity_country_pop.csv year, polity_id, country_iso, population
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
EQUAL_AREA = "EPSG:6933"


def slice_years():
    txt = (ROOT / "web" / "data.js").read_text(encoding="utf-8").strip()
    return json.loads(txt.replace("const HISTOMAP_DATA = ", "", 1).rstrip(";\n").rstrip(";"))["years"]


def build_maddison(years):
    """Maddison gdppc per country, linearly interpolated onto the slice years
    (only within each country's observed span; outside -> left to fallback)."""
    df = pd.read_excel(RAW / "mpd2020.xlsx", sheet_name="Full data")
    df = df[["countrycode", "year", "gdppc"]].dropna(subset=["gdppc"])
    out = []
    for iso, g in df.groupby("countrycode"):
        s = g.set_index("year")["gdppc"].sort_index()
        s = s[~s.index.duplicated()]
        lo, hi = s.index.min(), s.index.max()
        targets = [y for y in years if lo <= y <= hi]
        if not targets:
            continue
        idx = sorted(set(s.index) | set(targets))
        interp = s.reindex(idx).interpolate(method="index")
        for y in targets:
            out.append((iso, y, float(interp.loc[y])))
    md = pd.DataFrame(out, columns=["country_iso", "year", "gdppc"])
    md.to_csv(PROC / "maddison_gdppc.csv", index=False)
    print(f"maddison_gdppc.csv: {len(md):,} rows, {md.country_iso.nunique()} countries, "
          f"slice-years {md.year.min()}..{md.year.max()}")
    return md


def load_ne():
    ne = gpd.read_file(RAW / "ne_50m_admin_0_countries.zip")
    iso = ne["ISO_A3"].where(ne["ISO_A3"] != "-99", ne["ISO_A3_EH"])
    iso = iso.where(iso != "-99", ne.get("ADM0_ISO"))
    ne = ne.assign(country_iso=iso, region=ne["SUBREGION"])
    ne = ne[ne.country_iso.str.len() == 3].copy()
    ne[["country_iso", "region"]].drop_duplicates("country_iso").to_csv(
        PROC / "region_for_country.csv", index=False)
    print(f"region_for_country.csv: {ne.country_iso.nunique()} countries")
    return ne[["country_iso", "geometry"]]


def build_polity_country_pop(years, ne):
    # Cliopatria geometries (POLITY only), one per (Name, FromYear, ToYear)
    clio = gpd.read_file(RAW / "cliopatria_polities_only.geojson")
    clio = clio[clio["Type"] == "POLITY"][["Name", "FromYear", "ToYear", "geometry"]]
    print(f"overlaying {len(clio):,} polity intervals x {len(ne)} countries ...")

    inter = gpd.overlay(clio, ne, how="intersection", keep_geom_type=True)
    inter["a"] = inter.to_crs(EQUAL_AREA).geometry.area
    # area fraction of each interval that lies in each modern country
    frac = (inter.groupby(["Name", "FromYear", "ToYear", "country_iso"])["a"]
                 .sum().reset_index())
    tot = frac.groupby(["Name", "FromYear", "ToYear"])["a"].transform("sum")
    frac["frac"] = frac["a"] / tot
    frac = frac[frac.frac > 0]
    print(f"  {len(frac):,} (interval, country) fractions")

    # polity population per slice year (raw names == Cliopatria Names)
    ps = pd.read_csv(PROC / "population_shares.csv")[["year", "name", "population"]]
    ps = ps[ps.year.isin(years)]

    rows = []
    # index fractions by Name for interval lookup
    by_name = {n: g for n, g in frac.groupby("Name")}
    for r in ps.itertuples(index=False):
        g = by_name.get(r.name)
        if g is None:
            continue
        iv = g[(g.FromYear <= r.year) & (g.ToYear >= r.year)]
        if iv.empty:
            continue
        # if multiple intervals bracket the year, use the one with most coverage
        if iv[["FromYear", "ToYear"]].drop_duplicates().shape[0] > 1:
            key = iv.groupby(["FromYear", "ToYear"]).frac.sum().idxmax()
            iv = iv[(iv.FromYear == key[0]) & (iv.ToYear == key[1])]
        for c in iv.itertuples(index=False):
            rows.append((r.year, r.name, c.country_iso, r.population * c.frac))

    pcp = pd.DataFrame(rows, columns=["year", "polity_id", "country_iso", "population"])
    pcp.to_csv(PROC / "polity_country_pop.csv", index=False)
    print(f"polity_country_pop.csv: {len(pcp):,} rows, "
          f"{pcp.polity_id.nunique()} polities, {pcp.country_iso.nunique()} countries")


def main():
    years = slice_years()
    build_maddison(years)
    ne = load_ne()
    build_polity_country_pop(years, ne)


if __name__ == "__main__":
    main()
