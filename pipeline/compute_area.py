"""
compute_area.py
===============
SUPERSEDED — not part of the live pipeline. Territory area for the shipped data
is computed inside pipeline/align_territory.py (exclusive_area, keyed by the
aggregated streams). This flat-polity version is kept for reference; do not run.

Emit raw territory (km^2) per polity per time slice from Cliopatria border
polygons -> data/processed/area_km2.csv

Design notes
------------
- Output is RAW area in km^2, never a share. The frontend computes shares per
  lens (see docs/metric-layer.md). This keeps territory comparable to population
  as a swappable component of the "relative power" composite.
- Overlap resolution mirrors the population pipeline's "smaller polities burn
  last, so they win overlaps". Vector equivalent: process polities smallest-
  first, and each polity's exclusive area = its geometry minus the union of all
  strictly-smaller polities already claimed. So every patch of land is counted
  once, attributed to the smallest polity covering it.
- Area is measured in an equal-area projection (EPSG:6933, World Cylindrical
  Equal Area) so km^2 are honest at every latitude.

INPUT ASSUMPTION (adjust to match your Cliopatria load):
  A GeoDataFrame with columns: polity_id, year, geometry
  one row per (polity, slice). If Cliopatria gives validity ranges instead of
  discrete slices, expand to your SLICE_YEARS first (same slices the population
  pipeline uses).
"""

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

EQUAL_AREA_CRS = "EPSG:6933"  # World Cylindrical Equal Area, units = metres
M2_PER_KM2 = 1_000_000.0


def load_polygons(path: Path) -> gpd.GeoDataFrame:
    """Load Cliopatria polygons. Expected columns: polity_id, year, geometry.

    Adjust this loader to your vendored Cliopatria format. If your source keeps
    one geometry per polity with a (start_year, end_year) validity, expand it to
    one row per SLICE_YEAR here so downstream code sees discrete slices.
    """
    gdf = gpd.read_file(path)
    required = {"polity_id", "year", "geometry"}
    missing = required - set(gdf.columns)
    if missing:
        raise ValueError(f"Cliopatria input missing columns: {missing}")
    return gdf.to_crs(EQUAL_AREA_CRS)


def area_for_slice(slice_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Exclusive km^2 per polity for one year, smaller-polity-wins on overlap."""
    # raw area, used only to order smallest-first
    slice_gdf = slice_gdf.copy()
    slice_gdf["_raw_m2"] = slice_gdf.geometry.area
    slice_gdf = slice_gdf.sort_values("_raw_m2")  # smallest first => wins overlaps

    claimed = None  # union of all smaller polities already assigned
    rows = []
    for _, r in slice_gdf.iterrows():
        geom = r.geometry
        exclusive = geom if claimed is None else geom.difference(claimed)
        rows.append((r.polity_id, exclusive.area / M2_PER_KM2))
        claimed = geom if claimed is None else claimed.union(geom)

    out = pd.DataFrame(rows, columns=["polity_id", "area_km2"])
    # collapse any multipart duplicates of the same polity in this slice
    return out.groupby("polity_id", as_index=False)["area_km2"].sum()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--polygons", default="data/raw/cliopatria.gpkg",
                    help="Cliopatria polygons (polity_id, year, geometry)")
    ap.add_argument("--out", default="data/processed/area_km2.csv")
    args = ap.parse_args()

    gdf = load_polygons(Path(args.polygons))

    frames = []
    for year, slice_gdf in gdf.groupby("year"):
        a = area_for_slice(slice_gdf)
        a["year"] = year
        frames.append(a)

    result = pd.concat(frames, ignore_index=True)[["polity_id", "year", "area_km2"]]
    result = result.sort_values(["year", "polity_id"]).reset_index(drop=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    print(f"wrote {len(result):,} rows -> {out}")


if __name__ == "__main__":
    main()
