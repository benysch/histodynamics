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
  4. Snap each figure's birth_year to the histomap slice it falls in.
  5. Aggregate per (polity, slice), in one of two models (--mode):
       stock (default) — cumulative. A figure adds to its polity's count from its
            birth slice onward, for every slice the polity is active (union of its
            polygon intervals, so gaps in existence are respected). Models soft
            power as ACCUMULATED cultural capital — Athens in 400 BCE reflects a
            century of prior figures, not just those born in that 50-year slice.
       flow — a one-slice birth pulse: each figure counts only in its birth slice.
            Sparser and spikier; kept for comparison.

"Cultural centrality" measures soft power without subjective ranking: whose ideas
and leaders crossed enough borders to be translated into 25+ languages, and where
they were born. The engine then normalizes the counts into a share like any other
extensive fact.

Caveat: a polity's cultural legacy does not transfer to successor states here —
stock lives only within the polity's own active window. Cross-polity inheritance
(territorial succession) is a deliberately harder problem left for later.

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


def _active_slices(intervals, slices: list) -> list:
    """Slice years covered by ANY of a polity's [FromYear, ToYear] intervals, so
    a polity that existed, lapsed, and revived doesn't carry stock through the gap."""
    active = set()
    for r in intervals.itertuples(index=False):
        active.update(y for y in slices if r.FromYear <= y <= r.ToYear)
    return sorted(active)


def build_vector(flow, intervals, slices: list, mode: str):
    """Turn the birth-flow (Name, slice_year, born) into the per-(polity, year)
    cultural_figures vector. `intervals` is (Name, FromYear, ToYear)."""
    if mode == "flow":
        out = flow.rename(columns={"Name": "polity_id", "slice_year": "year",
                                   "born": "cultural_figures"})
    else:
        # cumulative STOCK: carry every figure forward across the slices its
        # polity is active. Active window = union of that polity's polygon
        # intervals (so stock persists through quiet slices but not through gaps
        # in existence).
        rows = []
        for name, g in flow.groupby("Name"):
            born_at = dict(zip(g["slice_year"], g["born"]))
            born_slices = sorted(born_at)
            for s in _active_slices(intervals[intervals["Name"] == name], slices):
                cum = sum(born_at[b] for b in born_slices if b <= s)
                if cum > 0:
                    rows.append((name, s, cum))
        out = pd.DataFrame(rows, columns=["polity_id", "year", "cultural_figures"])

    return (out[["polity_id", "year", "cultural_figures"]]
            .sort_values(["polity_id", "year"]).reset_index(drop=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--polygons", default=str(ROOT / "data/raw/cliopatria_polities_only.geojson"))
    ap.add_argument("--pantheon", default=str(ROOT / "data/raw/pantheon_1.csv"))
    ap.add_argument("--slices-from", default=str(ROOT / "data/processed/population_shares.csv"))
    ap.add_argument("--out", default=str(ROOT / "data/processed/vectors/culture.csv"))
    ap.add_argument("--mode", choices=["stock", "flow"], default="stock",
                    help="stock: cumulative cultural capital (default); flow: birth-slice pulse")
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

    # birth-FLOW: figures born in each (polity, slice)
    flow = joined.groupby(["Name", "slice_year"]).size().reset_index(name="born")
    intervals = polys[["Name", "FromYear", "ToYear"]].drop_duplicates()
    out = build_vector(flow, intervals, slices, args.mode)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)   # Phase 5 guardrail
    out.to_csv(out_path, index=False)
    print(f"wrote {out_path}  [{args.mode}]  ({len(out):,} polity-slices, "
          f"{len(joined):,} figures placed across {out['polity_id'].nunique()} polities)")


if __name__ == "__main__":
    main()
