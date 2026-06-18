"""
align_territory.py
==================
Bridge Cliopatria territory to Demograph's aggregated streams, then emit the
metric layer's data globals (web/polities.js, facts.js, totals.js, orders.js).

Why this exists
---------------
The vendored compute_area.py / emit_facts.py assume a flat `polity_id` taxonomy,
but Demograph's renderer (HISTOMAP_DATA) uses 262 *aggregated* streams: prominent
polities kept by name, sub-threshold ones rolled into per-family "Smaller X"
bundles, plus population-only "Unrecorded X" overlays and a residual. To make a
territory lens line up with that renderer, area must be keyed by those same
streams. This script reproduces export_web.py's raw->stream mapping:

  - A Cliopatria polity whose Name is a kept stream  -> that stream (identity).
  - Any other polity            -> "Smaller {family} states", family from the
    SAME classifier export_web used. Sub-threshold polities were never in the
    Wikidata fingerprint (fetch_fingerprint only covered prominent streams), so
    an empty fingerprint reproduces their original geographic-fallback family.

Population comes straight from HISTOMAP_DATA (already aligned). Area is summed
from Cliopatria's per-interval `Area` column (verified to be exact km^2),
attributed to the slice years the polity's [FromYear, ToYear] interval covers.

Outputs (keyed by stream name; consumed by web/index.html's metric layer):
  web/polities.js  window.POLITIES = [{id,name,civ}, ...]
  web/facts.js     window.FACTS    = {"<year>": {"<stream>": {population, area_km2}}}
  web/totals.js    window.TOTALS   = {"<year>": {population, area_km2}}
  web/orders.js    window.ORDERS / window.ORDER_PRESETS
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

CLIO = ROOT / "data" / "raw" / "cliopatria_polities_only.geojson"
POP_SHARES = ROOT / "data" / "processed" / "population_shares.csv"
DATA_JS = ROOT / "web" / "data.js"
FP_JSON = ROOT / "data" / "raw" / "wikidata_fingerprint.json"
WEB = ROOT / "web"

WORLD_LAND_KM2 = 104_000_000.0  # matches pipeline/emit_facts.py

BUNDLE_NAMES = {
    "classical": "Smaller classical states", "americas": "Smaller American states",
    "westeurope": "Smaller Western states", "africa": "Smaller African states",
    "orthodox": "Smaller Orthodox states", "ancientne": "Smaller ancient Near East states",
    "islam": "Smaller Islamic states", "steppe": "Smaller steppe powers",
    "dharmic": "Smaller Indic states", "sinic": "Smaller East Asian states",
    "japan": "Smaller Japanese states",
}


def load_histomap():
    txt = DATA_JS.read_text(encoding="utf-8").strip()
    txt = txt.replace("const HISTOMAP_DATA = ", "", 1).rstrip(";\n").rstrip(";")
    return json.loads(txt)


def emit_js(var, obj, path):
    payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    path.write_text(f"window.{var} = {payload};\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")


def main():
    D = load_histomap()
    years = D["years"]
    order = D["order"]
    residual = D["residual"]
    regions = D["regions"]                       # stream -> family (kept streams)
    streams = [s for s in order if s != residual]
    kept = set(streams)                          # every stream name (incl. bundles/unrecorded)
    pop_series = D["series"]                     # stream -> [{year,share,pop}]

    # --- classifier (empty fingerprint -> geographic fallback, as in the
    #     original run for sub-threshold polities) ---
    if not FP_JSON.exists():
        FP_JSON.parent.mkdir(parents=True, exist_ok=True)
        FP_JSON.write_text("{}", encoding="utf-8")
    from fingerprint import Classifier
    clf = Classifier()

    # --- per-polity lon/lat/first/last for classification (as export_web does) ---
    ps = pd.read_csv(POP_SHARES)
    agg = ps.groupby("name").agg(lon=("lon", "mean"), lat=("lat", "mean"),
                                 first=("year", "min"), last=("year", "max"))

    # --- Cliopatria intervals (attributes only; Area is exact km^2) ---
    clio = pyogrio.read_dataframe(str(CLIO), read_geometry=False)
    clio = clio[clio["Type"] == "POLITY"].copy()
    print(f"{len(clio):,} POLITY intervals, {clio.Name.nunique():,} distinct polities")

    # centroid fallback for polities missing from population_shares
    missing = sorted(set(clio.Name.unique()) - set(agg.index))
    print(f"{len(missing)} Cliopatria polities absent from population_shares "
          f"(centroid fallback)")
    if missing:
        gsub = gpd.read_file(str(CLIO),
                             where="Name IN (" + ",".join(f"'{m.replace(chr(39), chr(39)*2)}'" for m in missing) + ")")
        gsub = gsub[gsub["Type"] == "POLITY"]
        cen = gsub.dissolve("Name").geometry.representative_point()
        cen = gpd.GeoSeries(cen, crs=gsub.crs)
        for name, pt in cen.items():
            agg.loc[name] = {"lon": pt.x, "lat": pt.y,
                             "first": int(gsub[gsub.Name == name].FromYear.min()),
                             "last": int(gsub[gsub.Name == name].ToYear.max())}

    # --- map every Cliopatria polity name -> stream ---
    name_to_stream = {}
    for name in clio.Name.unique():
        if name in kept:
            name_to_stream[name] = name           # prominent: identity
            continue
        r = agg.loc[name] if name in agg.index else None
        if r is None:
            continue
        fam, _ = clf.classify(name, float(r.lon), float(r.lat),
                              int(r["first"]), int(r["last"]))
        bundle = BUNDLE_NAMES.get(fam)
        if bundle in kept:
            name_to_stream[name] = bundle          # sub-threshold: family bundle

    # --- area per stream per slice year ---
    # one polity has at most one interval covering a given year; sum per stream
    area = {y: {} for y in years}
    rows = clio[["Name", "FromYear", "ToYear", "Area"]].itertuples(index=False)
    for name, fy, ty, a in rows:
        stream = name_to_stream.get(name)
        if stream is None or not (a and a > 0):
            continue
        for y in years:
            if fy <= y <= ty:
                area[y][stream] = area[y].get(stream, 0.0) + float(a)

    mapped_avg = sum(sum(area[y].values()) for y in years) / len(years)
    print(f"avg mapped land per slice: {mapped_avg/1e6:.1f}M km^2 "
          f"({mapped_avg/WORLD_LAND_KM2:.0%} of {WORLD_LAND_KM2/1e6:.0f}M ice-free)")

    # --- emit web/polities.js ---
    polities = [{"id": s, "name": s, "civ": regions.get(s, "unknown")} for s in streams]
    emit_js("POLITIES", polities, WEB / "polities.js")

    # --- emit web/facts.js : {year: {stream: {population, area_km2}}} ---
    facts = {}
    for i, y in enumerate(years):
        slot = {}
        for s in streams:
            pop = pop_series[s][i]["pop"] or 0.0
            entry = {}
            if pop:
                entry["population"] = pop
            if s in area[y]:
                entry["area_km2"] = round(area[y][s], 3)
            if entry:
                slot[s] = entry
        facts[str(y)] = slot
    emit_js("FACTS", facts, WEB / "facts.js")

    # --- emit web/totals.js ---
    # Territory denominator is the larger of total ice-free land and the land
    # actually mapped that slice. In antiquity little is governed, so the
    # denominator is WORLD_LAND_KM2 and the residual shows honest unmapped land;
    # in the modern era nearly all land is in states (and raw Cliopatria areas
    # overlap, since exclusive-area resolution is a future refinement), so the
    # denominator follows the mapped total and the residual closes to ~0 instead
    # of letting shares exceed 100%.
    totals = {}
    for i, y in enumerate(years):
        world_pop = sum((pop_series[s][i]["pop"] or 0.0) for s in order)  # incl. residual
        mapped = sum(area[y].values())
        totals[str(y)] = {"population": world_pop,
                          "area_km2": max(WORLD_LAND_KM2, mapped)}
    emit_js("TOTALS", totals, WEB / "totals.js")

    # --- emit web/orders.js : reuse Demograph's wiggle-optimized order for every
    #     lens (streams keep position; widths re-scale per lens). Per-lens baked
    #     orders are a future refinement (pipeline/compute_orders.py). ---
    presets = {
        "Demographic (= Demograph)": 0.0, "Balanced": 0.33,
        "Sparks-led (territory)": 0.55, "Economic": 0.15,
    }
    orders = {"pop": streams, "area": streams, "gdp": streams}
    for label in presets:
        orders[f"power:{label}"] = streams
    emit_js("ORDERS", orders, WEB / "orders.js")
    # ORDER_PRESETS lives in the same file (one extra line)
    with (WEB / "orders.js").open("a", encoding="utf-8") as f:
        f.write("window.ORDER_PRESETS = " +
                json.dumps({"power": presets}, separators=(",", ":")) + ";\n")
    print("appended window.ORDER_PRESETS")


if __name__ == "__main__":
    main()
