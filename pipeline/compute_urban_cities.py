"""
compute_urban_cities.py
=======================
Urban population per polity per slice from city-level data, covering the WHOLE
timeline (3700 BC - AD 2000) — unlike Clio Infra urbanization, which starts at
1500 and left the Structural-complexity lens blank for antiquity.

Source: Reba, Reitsma & Seto (2016), "Spatializing 6,000 years of global
urbanization" (figshare 10.6084/m9.figshare.2059500 and siblings). Three wide
CSVs — Chandler, Modelski Ancient, Modelski Modern — each row a city with
Latitude/Longitude and a population at benchmark years (columns BC_2250, AD_100,
…). Point data, so we attribute it to polities the same way compute_culture.py
does: a spatial+temporal join onto Cliopatria's historical polygons.

Method:
  1. Melt every file to (lat, lon, year, pop); combine, de-dup a city-year across
     sources by max population.
  2. Per city, linearly interpolate population onto the histomap slice years,
     within that city's observed span (no extrapolation — a city contributes only
     between its first and last attestation).
  3. Spatial-join cities -> polygons (within); for each city-slice keep the
     polygon whose [FromYear, ToYear] covers the slice (narrowest interval wins
     when polygons overlap).
  4. Sum urban population per (polity, slice).

OUTPUT:
  data/processed/vectors/urban_pop.csv  -> polity_id, year, urban_pop
       (same file/column the Structural-complexity lens already reads; picked up
        by align_territory.py's vector scanner. Supersedes the Clio Infra path in
        compute_complexity.py, which only covered 1500+.)
"""
import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = [
    ROOT / "data/raw/reba_chandler.csv",
    ROOT / "data/raw/reba_modelski_ancient.csv",
    ROOT / "data/raw/reba_modelski_modern.csv",
]
_YEAR = re.compile(r"^(AD|BC)_(\d+)$")


def _to_year(col: str):
    m = _YEAR.match(col)
    if not m:
        return None
    return int(m.group(2)) * (-1 if m.group(1) == "BC" else 1)


def _melt(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="latin-1")   # Reba files carry Latin-1 names (Coruña, …)
    ycols = [c for c in df.columns if _to_year(c) is not None]
    long = df.melt(id_vars=["Latitude", "Longitude"], value_vars=ycols,
                   var_name="ycol", value_name="pop")
    long["pop"] = pd.to_numeric(long["pop"], errors="coerce")   # some cells carry notes
    long = long.dropna(subset=["pop"])
    long = long[long["pop"] > 0].copy()
    long["year"] = long["ycol"].map(_to_year)
    return long[["Latitude", "Longitude", "year", "pop"]]


def _slice_years(path: Path) -> list:
    return [int(y) for y in sorted(pd.read_csv(path, usecols=["year"])["year"].unique())]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="+", default=[str(p) for p in DEFAULT_FILES])
    ap.add_argument("--polygons", default=str(ROOT / "data/raw/cliopatria_polities_only.geojson"))
    ap.add_argument("--slices-from", default=str(ROOT / "data/processed/population_shares.csv"))
    ap.add_argument("--out", default=str(ROOT / "data/processed/vectors/urban_pop.csv"))
    args = ap.parse_args()

    import geopandas as gpd

    paths = [Path(p) for p in args.cities]
    for p in paths + [Path(args.polygons)]:
        if not p.exists():
            raise SystemExit(f"raw file not found: {p}\nStage it and re-run.")

    long = pd.concat([_melt(p) for p in paths], ignore_index=True)
    # de-dup the same city-year appearing in multiple sources -> keep the max
    long = (long.groupby(["Latitude", "Longitude", "year"], as_index=False)["pop"].max())
    slices = _slice_years(Path(args.slices_from))
    print(f"{len(long):,} city-year observations; year range {long.year.min()}..{long.year.max()}")

    # interpolate each city's population onto the slice years (within its span)
    rows = []
    for (lat, lon), g in long.groupby(["Latitude", "Longitude"]):
        s = g.set_index("year")["pop"].sort_index()
        s = s[~s.index.duplicated()]
        lo, hi = s.index.min(), s.index.max()
        within = [y for y in slices if lo <= y <= hi]
        if not within:
            continue
        idx = sorted(set(s.index) | set(within))
        interp = s.reindex(idx).interpolate(method="index")
        last = float(s.iloc[-1])
        for y in within:
            rows.append((lat, lon, y, float(interp.loc[y])))
        # carry a still-living city's last value to the next slice only (e.g.
        # 2000 -> 2015), without resurrecting cities whose record ends centuries back
        for y in slices:
            if hi < y <= hi + 20:
                rows.append((lat, lon, y, last))
    city_slices = pd.DataFrame(rows, columns=["Latitude", "Longitude", "year", "urban_pop"])

    # unique city points -> polygon membership (spatial), then keep the polygon
    # whose interval covers each slice (narrowest interval wins on overlap)
    pts = (city_slices[["Latitude", "Longitude"]].drop_duplicates().reset_index(drop=True))
    gpts = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.Longitude, pts.Latitude),
                            crs="EPSG:4326")
    polys = gpd.read_file(args.polygons)
    polys = polys[polys["Type"] == "POLITY"][["Name", "FromYear", "ToYear", "geometry"]].to_crs("EPSG:4326")
    pairs = gpd.sjoin(gpts, polys, predicate="within", how="inner")[
        ["Latitude", "Longitude", "Name", "FromYear", "ToYear"]]
    pairs["width"] = pairs["ToYear"] - pairs["FromYear"]

    m = city_slices.merge(pairs, on=["Latitude", "Longitude"])
    m = m[(m.FromYear <= m.year) & (m.year <= m.ToYear)]
    # one polity per city-slice: the most specific (narrowest) interval
    m = m.sort_values("width").drop_duplicates(["Latitude", "Longitude", "year"])

    out = (m.groupby(["Name", "year"], as_index=False)["urban_pop"].sum()
             .rename(columns={"Name": "polity_id"})
             .sort_values(["polity_id", "year"]).reset_index(drop=True))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    pre = out[out.year < 1500]
    print(f"wrote {out_path}  ({len(out):,} polity-slices across "
          f"{out.polity_id.nunique()} polities; {len(pre):,} are pre-1500 — "
          f"antiquity now filled)")


if __name__ == "__main__":
    main()
