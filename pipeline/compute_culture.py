"""
compute_culture.py
=================
Turn point data (birthplaces of globally-translated historical figures) into an
EXTENSIVE per-polity count, via a spatial+temporal crosswalk onto Cliopatria's
historical polygons.

  data/raw/cliopatria_polities_only.geojson  -> historical polities (Type==POLITY,
       EPSG:4326), each with Name, FromYear, ToYear.
  data/raw/pantheon_1.csv                     -> MIT Pantheon 1.0 figures with
       lon, lat, birth_year (kaggle.com/datasets/mit/pantheon-project).

Method:
  1. Build a GeoDataFrame of figures from (lon, lat), EPSG:4326.
  2. Inner spatial join (within) figures -> polygons.
  3. Keep rows where the figure's birth_year is inside the polygon's
     [FromYear, ToYear] interval (a polygon is one historical interval).
  4. Snap each figure's birth_year to the histomap slice it falls in, then count
     figures per (polity, slice). This is a birth-FLOW proxy for cultural
     centrality; a cumulative-stock variant is a future refinement.

"Cultural centrality" measures soft power without subjective ranking: whose ideas
and leaders crossed enough borders to be translated into 25+ languages, and where
they were born. The engine then normalizes the counts into a share like any other
extensive fact.

OUTPUT:
  data/processed/vectors/culture.csv  -> polity_id, year, cultural_figures
       (picked up automatically by align_territory.py's vector scanner.)
"""

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# Pantheon ships under a few column spellings; normalize the ones we need.
COL_ALIASES = {
    "lon": ["lon", "LON", "longitude", "Longitude"],
    "lat": ["lat", "LAT", "latitude", "Latitude"],
    "birth_year": ["birth_year", "birthyear", "BirthYear", "birth_yr"],
}


def _pick(df: pd.DataFrame, canonical: str) -> str:
    for cand in COL_ALIASES[canonical]:
        if cand in df.columns:
            return cand
    raise SystemExit(f"pantheon file missing a '{canonical}' column "
                     f"(looked for {COL_ALIASES[canonical]})")


def _slice_years(path: Path) -> list:
    """The histomap's slice grid, taken from the canonical population table."""
    ys = sorted(pd.read_csv(path, usecols=["year"])["year"].unique())
    return [int(y) for y in ys]


def _snap(birth_year: int, slices: list) -> int:
    """Largest slice <= birth_year (the slice in effect at birth); clamps to the
    first slice for figures born before the grid begins."""
    lo = slices[0]
    for y in slices:
        if y > birth_year:
            break
        lo = y
    return lo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--polygons", default=str(ROOT / "data/raw/cliopatria_polities_only.geojson"))
    ap.add_argument("--pantheon", default=str(ROOT / "data/raw/pantheon_1.csv"))
    ap.add_argument("--slices-from", default=str(ROOT / "data/processed/population_shares.csv"))
    ap.add_argument("--out", default=str(ROOT / "data/processed/vectors/culture.csv"))
    args = ap.parse_args()

    poly_path, pan_path = Path(args.polygons), Path(args.pantheon)
    for p in (poly_path, pan_path):
        if not p.exists():
            raise SystemExit(f"raw file not found: {p}\nStage it and re-run. "
                             f"This script does not fetch data.")

    import geopandas as gpd  # imported late so Phase 1 doesn't need geopandas

    polys = gpd.read_file(str(poly_path))
    polys = polys[polys["Type"] == "POLITY"].to_crs("EPSG:4326")

    pan = pd.read_csv(pan_path)
    lon, lat, byr = _pick(pan, "lon"), _pick(pan, "lat"), _pick(pan, "birth_year")
    pan = pan.dropna(subset=[lon, lat, byr])
    figures = gpd.GeoDataFrame(
        pan, geometry=gpd.points_from_xy(pan[lon], pan[lat]), crs="EPSG:4326")

    joined = gpd.sjoin(figures, polys, predicate="within", how="inner")
    in_interval = (joined[byr] >= joined["FromYear"]) & (joined[byr] <= joined["ToYear"])
    joined = joined[in_interval].copy()

    slices = _slice_years(Path(args.slices_from))
    joined["slice_year"] = joined[byr].astype(int).map(lambda b: _snap(b, slices))

    out = (joined.groupby(["Name", "slice_year"]).size()
                 .reset_index(name="cultural_figures")
                 .rename(columns={"Name": "polity_id", "slice_year": "year"}))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)   # Phase 5 guardrail
    out.to_csv(out_path, index=False)
    print(f"wrote {out_path}  ({len(out):,} polity-slices, "
          f"{int(out['cultural_figures'].sum()):,} figures placed)")


if __name__ == "__main__":
    main()
