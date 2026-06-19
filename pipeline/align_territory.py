"""
align_territory.py
==================
Bridge Cliopatria territory to Demograph's aggregated streams, then emit the
metric layer's data globals (web/polities.js, facts.js, totals.js, orders.js).

Why this exists
---------------
The vendored compute_area.py / emit_facts.py assume a flat `polity_id` taxonomy,
but Demograph's renderer (HISTOMAP_DATA) uses 261 *aggregated* streams: prominent
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
import numpy as np
import pandas as pd
import pyogrio

import succession   # shared wiggle + succession-fidelity ordering core

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

CLIO = ROOT / "data" / "raw" / "cliopatria_polities_only.geojson"
POP_SHARES = ROOT / "data" / "processed" / "population_shares.csv"
GDP_CSV = ROOT / "data" / "processed" / "gdp_intusd.csv"   # optional (pipeline/compute_gdp.py)
VEC_DIR = ROOT / "data" / "processed" / "vectors"          # optional extra dimensions (one CSV per fact)
DATA_JS = ROOT / "web" / "data.js"
FP_JSON = ROOT / "data" / "raw" / "wikidata_fingerprint.json"
WEB = ROOT / "web"

WORLD_LAND_KM2 = 104_000_000.0  # matches pipeline/emit_facts.py
EQUAL_AREA = "EPSG:6933"         # World Cylindrical Equal Area (metres)

BUNDLE_NAMES = {
    "classical": "Smaller classical states", "americas": "Smaller American states",
    "westeurope": "Smaller Western states", "africa": "Smaller African states",
    "orthodox": "Smaller Orthodox states", "ancientne": "Smaller ancient Near East states",
    "islam": "Smaller Islamic states", "steppe": "Smaller steppe powers",
    "dharmic": "Smaller Indic states", "sinic": "Smaller East Asian states",
    "japan": "Smaller Japanese states",
}


# --- per-lens stacking order: wiggle minimization + succession fidelity ----
#     Wiggle math lives in succession.py now; this adds the constraint that two
#     streams aren't placed adjacent as a false handoff (A falls as B rises) with
#     no real population transfer between them. Transfers come from
#     data/processed/transfer_matrix.csv (pipeline/transfer_matrix.py), mapped
#     onto streams with the SAME name->stream classifier used everywhere here.
def stream_transfers(name_to_stream):
    path = ROOT / "data" / "processed" / "transfer_matrix.csv"
    pair = {}
    if not path.exists():
        return pair
    tf = pd.read_csv(path)
    for a, b, pop in zip(tf["from"], tf["to"], tf["population"]):
        sa, sb = name_to_stream.get(a), name_to_stream.get(b)
        if sa and sb and sa != sb:
            key = frozenset((sa, sb))
            pair[key] = pair.get(key, 0.0) + float(pop)
    return pair


def lens_order(streams, share_rows, pair):
    """share_rows: dict stream -> [share per year]. Returns streams bottom->top,
    minimizing wiggle subject to no false-handoff adjacency (succession.py)."""
    W = np.array([share_rows[s] for s in streams]).T   # years x streams
    forbidden = succession.forbidden_pairs(W, streams, pair)
    order, _ = succession.optimize(W, forbidden)
    return [streams[i] for i in order]


def exclusive_area(years, name_to_stream, res_m=5000):
    """Exclusive km^2 per stream per slice, overlaps resolved smaller-wins, via
    equal-area rasterization (EPSG:6933). Polygons are painted largest-first so
    smaller polities overwrite and every cell is counted once for the smallest
    polity covering it -- the vector difference in compute_area.py, done on a
    grid (fast, and how the population pipeline assigns cells too)."""
    from rasterio import features
    from rasterio.transform import from_origin

    # EPSG:6933 world extent (metres)
    XMIN, XMAX, YMIN, YMAX = -17367530.45, 17367530.45, -7314540.83, 7314540.83
    cols = int(round((XMAX - XMIN) / res_m))
    rows = int(round((YMAX - YMIN) / res_m))
    transform = from_origin(XMIN, YMAX, res_m, res_m)
    cell_km2 = (res_m * res_m) / 1e6
    print(f"rasterizing exclusive area at {res_m/1000:.0f} km ({cols}x{rows}) ...")

    g = gpd.read_file(CLIO)
    g = g[g["Type"] == "POLITY"][["Name", "FromYear", "ToYear", "Area", "geometry"]]
    g = g.to_crs(EQUAL_AREA)

    area = {y: {} for y in years}
    for y in years:
        sl = g[(g.FromYear <= y) & (g.ToYear >= y)]
        if sl.empty:
            continue
        sl = sl.sort_values("Area", ascending=False)        # largest first -> smaller wins
        names = sl.Name.tolist()
        shapes = ((geom, i + 1) for i, geom in enumerate(sl.geometry.values))
        arr = features.rasterize(shapes, out_shape=(rows, cols), transform=transform,
                                 fill=0, dtype="int32", all_touched=False)
        counts = np.bincount(arr.ravel())
        for i, name in enumerate(names):
            v = i + 1
            if v < len(counts) and counts[v]:
                stream = name_to_stream.get(name)
                if stream is not None:
                    area[y][stream] = area[y].get(stream, 0.0) + counts[v] * cell_km2
    return area


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

    # curated duplicate-stream merges (pipeline/merge_polities.py): route an alias
    # Cliopatria name to the canonical stream its population was folded into.
    aliases = {}
    apath = ROOT / "data" / "processed" / "polity_aliases.json"
    if apath.exists():
        aliases = json.loads(apath.read_text(encoding="utf-8"))

    # --- map every Cliopatria polity name -> stream ---
    name_to_stream = {}
    for name in clio.Name.unique():
        if name in aliases and aliases[name] in kept:
            name_to_stream[name] = aliases[name]  # merged duplicate -> canonical
            continue
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

    # --- exclusive area per stream per slice year (overlaps resolved) ---
    area = exclusive_area(years, name_to_stream)

    mapped_avg = sum(sum(area[y].values()) for y in years) / len(years)
    print(f"avg mapped land per slice: {mapped_avg/1e6:.1f}M km^2 "
          f"({mapped_avg/WORLD_LAND_KM2:.0%} of {WORLD_LAND_KM2/1e6:.0f}M ice-free)")

    # --- optional GDP (data/processed/gdp_intusd.csv from compute_gdp.py),
    #     aggregated to streams with the same raw->stream mapping; world total
    #     for the slice is all attributed GDP (so unattributed GDP is a residual). ---
    gdp = {y: {} for y in years}      # stream -> int$
    gdp_world = {y: 0.0 for y in years}
    if GDP_CSV.exists():
        gd = pd.read_csv(GDP_CSV)
        for r in gd.itertuples(index=False):
            if r.year not in gdp_world:
                continue
            gdp_world[r.year] += float(r.gdp_int_usd)
            stream = name_to_stream.get(r.polity_id)
            if stream is not None:
                gdp[r.year][stream] = gdp[r.year].get(stream, 0.0) + float(r.gdp_int_usd)
        print(f"GDP: {len(gd):,} polity-years aggregated; world GDP "
              f"{gdp_world[years[-1]]/1e12:.1f}T int$ at {years[-1]}")
    else:
        print("GDP: gdp_intusd.csv absent — economy lens stays disabled")

    # --- dynamic vectors: data/processed/vectors/*.csv -> extra extensive facts ---
    # Each CSV is (polity_id, year, <value>); the value column NAMES the fact
    # written into web/facts.js (e.g. urban_pop, cultural_figures), so adding a
    # dimension is adding a file here — no code change downstream. Aggregated to
    # streams with the same name_to_stream mapping GDP uses; the per-slice world
    # total is all attributed value, so unattributed value is an honest residual.
    # Placed AFTER name_to_stream is fully populated and BEFORE the FACTS emit.
    vectors = {}       # fact_key -> {year -> {stream -> value}}
    vec_world = {}     # fact_key -> {year -> total}
    if VEC_DIR.exists():
        for csv_path in sorted(VEC_DIR.glob("*.csv")):
            vdf = pd.read_csv(csv_path)
            value_cols = [c for c in vdf.columns if c not in ("polity_id", "year")]
            if not value_cols:
                print(f"vectors: {csv_path.name} has no value column — skipped")
                continue
            key = value_cols[0]
            vectors[key] = {y: {} for y in years}
            vec_world[key] = {y: 0.0 for y in years}
            placed = 0
            for r in vdf.itertuples(index=False):
                y = int(r.year)
                if y not in vectors[key]:
                    continue
                val = getattr(r, key)
                if pd.isna(val):
                    continue
                val = float(val)
                vec_world[key][y] += val
                stream = name_to_stream.get(r.polity_id)
                if stream is not None:
                    vectors[key][y][stream] = vectors[key][y].get(stream, 0.0) + val
                    placed += 1
            print(f"vectors: {csv_path.name} -> fact '{key}' "
                  f"({placed:,} stream-years attributed)")
    else:
        print("vectors: data/processed/vectors/ absent — no extra dimensions")

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
            if s in gdp[y]:
                entry["gdp_int_usd"] = round(gdp[y][s], 1)
            for key, vy in vectors.items():
                if s in vy[y]:
                    entry[key] = round(vy[y][s], 3)
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
        t = {"population": world_pop, "area_km2": max(WORLD_LAND_KM2, mapped)}
        if gdp_world[y] > 0:
            t["gdp"] = gdp_world[y]
        for key, wy in vec_world.items():
            if wy[y] > 0:
                t[key] = wy[y]
        totals[str(y)] = t
    emit_js("TOTALS", totals, WEB / "totals.js")

    # --- per-lens stacking orders ----------------------------------------
    # Population keeps Demograph's wiggle-optimized order (streams == D.order);
    # territory, economy, and each power preset get their own order so the chart
    # RE-STACKS on lens change, not just re-scales. Presets carry their full
    # 3-weight blend; order.js snaps to the nearest by territory weight (wArea).
    ny = len(years)
    pop_sh  = {s: [pop_series[s][i]["pop"] or 0.0 for i in range(ny)] for s in streams}
    pden = [sum((pop_series[s][i]["pop"] or 0.0) for s in order) for i in range(ny)]
    aden = [max(WORLD_LAND_KM2, sum(area[years[i]].values())) for i in range(ny)]
    gden = [gdp_world[years[i]] for i in range(ny)]
    pop_sh  = {s: [(pop_series[s][i]["pop"] or 0.0) / pden[i] if pden[i] else 0.0 for i in range(ny)] for s in streams}
    area_sh = {s: [area[years[i]].get(s, 0.0) / aden[i] if aden[i] else 0.0 for i in range(ny)] for s in streams}
    gdp_sh  = {s: [gdp[years[i]].get(s, 0.0) / gden[i] if gden[i] else 0.0 for i in range(ny)] for s in streams}

    def blend(wp, wa, wg):
        """Per-cell weight-renormalized blend over available components, then
        per-slice normalized to sum 1 (mirrors engine.js compositeSlice)."""
        rows = {s: [0.0] * ny for s in streams}
        for i in range(ny):
            tot = 0.0
            for s in streams:
                comps = [(wp, pop_sh[s][i])]              # population: present for all streams
                if s in area[years[i]]: comps.append((wa, area_sh[s][i]))
                if s in gdp[years[i]]:  comps.append((wg, gdp_sh[s][i]))
                wsum = sum(w for w, _ in comps)
                v = sum(w * sh for w, sh in comps) / wsum if wsum > 0 else 0.0
                rows[s][i] = v; tot += v
            if tot > 0:
                for s in streams: rows[s][i] /= tot
        return rows

    presets = {  # label -> (wPop, wArea, wGdp); matches web/lenses.js
        "Demographic (= Demograph)": (1.0, 0.0, 0.0),
        "Balanced":                  (0.34, 0.33, 0.33),
        "Sparks-led (territory)":    (0.25, 0.55, 0.20),
        "Economic":                  (0.25, 0.15, 0.60),
    }
    orders = {"pop": streams}                     # keep Demograph's optimized order
    pair = stream_transfers(name_to_stream)
    print(f"optimizing per-lens orders (succession-aware; {len(pair)} stream transfer pairs) ...")
    orders["area"] = lens_order(streams, area_sh, pair)
    orders["gdp"]  = lens_order(streams, gdp_sh, pair)
    for label, (wp, wa, wg) in presets.items():
        orders[f"power:{label}"] = lens_order(streams, blend(wp, wa, wg), pair)
    # vector lenses (urban, culture, …) need their own order too, else the
    # frontend's buildSeries gets no layers and the lens renders blank/stale.
    VECTOR_LENS = {"urban_pop": "urban", "cultural_figures": "culture"}
    for key, lensid in VECTOR_LENS.items():
        if key not in vectors:
            continue
        vw = vec_world[key]
        sh = {s: [(vectors[key][years[i]].get(s, 0.0) / vw[years[i]]) if vw[years[i]] else 0.0
                  for i in range(ny)] for s in streams}
        orders[lensid] = lens_order(streams, sh, pair)
        print(f"  per-lens order for '{lensid}' ({key})")
    emit_js("ORDERS", orders, WEB / "orders.js")
    with (WEB / "orders.js").open("a", encoding="utf-8") as f:
        f.write("window.ORDER_PRESETS = " +
                json.dumps({"power": {k: v[1] for k, v in presets.items()}},
                           separators=(",", ":")) + ";\n")
    print("appended window.ORDER_PRESETS")


if __name__ == "__main__":
    main()
