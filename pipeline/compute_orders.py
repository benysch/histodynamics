"""
compute_orders.py
=================
SUPERSEDED — not part of the live pipeline, and its presets are stale (only
pop/area, scalar weights 0.0/0.5/0.7). The shipped web/orders.js is produced by
the inline lens_order() in pipeline/align_territory.py, whose presets
(Demographic/Balanced/Sparks-led/Economic, with GDP) match web/lenses.js. Kept
for reference; do not run.

Precompute the stacking order (bottom -> top) that minimizes "wiggle" for each
lens, plus one order per composite preset. Emits web/orders.js so the frontend
swaps order instantly on lens change instead of re-solving in the browser.

Why per-lens: order minimizes wiggle of the *displayed* widths, and those widths
differ by lens. Why per-preset (not per weight): re-solving on every slider step
is the janky path. Instead we bake an order at each preset; when the user free-
drags, the frontend snaps to the nearest preset's order (order.js) so the streams
only rescale between presets — smooth. Live re-optimization is a v2 option.

The objective is exactly Demograph's phrasing: "a stream's width change displaces
everything stacked after it." For each layer we sum the squared slice-to-slice
change of the cumulative thickness below it; the total over layers is the wiggle.

Succession fidelity: two streams placed adjacent read as a handoff (one ends, the
next begins). We forbid an adjacency that *looks* like a succession (A falls as B
rises) unless the transfer matrix shows real population actually moved between
them. Without a transfer matrix the constraint is simply skipped.

INPUT ASSUMPTIONS (rename to match your processed files):
  data/processed/population_shares.csv  -> polity_id, year, population (raw persons)
  data/processed/area_km2.csv           -> polity_id, year, area_km2
  data/processed/world_population.csv    -> year, population (exogenous total)
  data/processed/transfer_matrix.csv     -> from_id, to_id, amount   (OPTIONAL)
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# --- keep in sync with web/lenses.js -------------------------------------
SIMPLE_LENSES = {
    "pop":  {"fact": "population", "exo": "population"},   # exo total per slice
    "area": {"fact": "area_km2",   "exo": "land"},         # exo total = constant land
}
POWER_PRESETS = {           # territory weight (wArea); wPop = 1 - wArea
    "Demographic": 0.0,
    "Balanced":    0.5,
    "Sparks-led":  0.7,
}
WORLD_LAND_KM2 = 104_000_000.0

# succession-fidelity thresholds (documented knobs)
HANDOFF_CORR = 0.55   # adjacency reads as a handoff above this anti-correlation
TRANSFER_FRAC = 0.05  # ...and is "real" only if transfer >= this fraction of the
                      #    larger stream's peak. Below both -> forbidden adjacency.


# ---------------------------------------------------------------- loaders
def pivot(df, value_col):
    """long -> (years × polity) matrix, missing = 0 for width purposes."""
    m = df.pivot_table(index="year", columns="polity_id", values=value_col, aggfunc="sum")
    return m.sort_index()


def load():
    pop = pd.read_csv("data/processed/population_shares.csv")
    area = pd.read_csv("data/processed/area_km2.csv")
    wpop = pd.read_csv("data/processed/world_population.csv").set_index("year")["population"]
    pop_m = pivot(pop, "population")
    area_m = pivot(area, "area_km2")
    # align on the same year × polity grid
    years = pop_m.index.union(area_m.index)
    cols = pop_m.columns.union(area_m.columns)
    pop_m = pop_m.reindex(index=years, columns=cols)
    area_m = area_m.reindex(index=years, columns=cols)
    wpop = wpop.reindex(years)

    pop_share = pop_m.div(wpop, axis=0)
    area_share = area_m / WORLD_LAND_KM2

    transfer = None
    tpath = Path("data/processed/transfer_matrix.csv")
    if tpath.exists():
        transfer = pd.read_csv(tpath)
    return pop_share, area_share, transfer


# ---------------------------------------------------------- width per lens
def width_simple(share_m):
    return share_m.fillna(0.0).to_numpy(), list(share_m.columns)


def width_composite(pop_share, area_share, w_area):
    """Per-cell renormalized blend, then per-slice normalize to sum 1."""
    w_pop = 1.0 - w_area
    P = pop_share.to_numpy()
    A = area_share.to_numpy()
    has_p = ~np.isnan(P)
    has_a = ~np.isnan(A)
    p = np.nan_to_num(P)
    a = np.nan_to_num(A)
    # renormalize weights over the components each cell actually has
    wp = np.where(has_p, w_pop, 0.0)
    wa = np.where(has_a, w_area, 0.0)
    wsum = wp + wa
    blend = np.divide(wp * p + wa * a, wsum, out=np.zeros_like(p), where=wsum > 0)
    row = blend.sum(axis=1, keepdims=True)
    norm = np.divide(blend, row, out=np.zeros_like(blend), where=row > 0)
    return norm, list(pop_share.columns)


# --------------------------------------------------------------- ordering
def wiggle(order, W):
    """Σ over layers of Σ_t (Δ cumulative-thickness-below)^2. Lower = calmer."""
    cum = np.zeros(W.shape[0])
    total = 0.0
    for idx in order:           # bottom -> top
        d = np.diff(cum)
        total += float(np.dot(d, d))
        cum = cum + W[:, idx]
    return total


def inside_out(W):
    """d3-style: balance two sides so the largest streams sit near the center."""
    sums = W.sum(axis=0)
    idxs = list(np.argsort(-sums))
    tops, bottoms, ts, bs = [], [], 0.0, 0.0
    for idx in idxs:
        if ts < bs:
            tops.append(idx); ts += sums[idx]
        else:
            bottoms.append(idx); bs += sums[idx]
    return list(reversed(bottoms)) + tops   # bottom -> top


def forbidden_pairs(W, cols, transfer):
    """Unordered index pairs that would be a FALSE handoff if placed adjacent."""
    if transfer is None:
        return set()
    idx_of = {c: i for i, c in enumerate(cols)}
    # peak width per stream, for normalizing transfer significance
    peak = W.max(axis=0)
    # transfer lookup (symmetric significance)
    tf = {}
    for r in transfer.itertuples(index=False):
        if r.from_id in idx_of and r.to_id in idx_of:
            key = frozenset((idx_of[r.from_id], idx_of[r.to_id]))
            tf[key] = tf.get(key, 0.0) + float(r.amount)

    forbidden = set()
    n = len(cols)
    d = np.diff(W, axis=0)  # slice-to-slice change per stream
    for i in range(n):
        for j in range(i + 1, n):
            di, dj = d[:, i], d[:, j]
            mask = (W[:-1, i] > 0) | (W[:-1, j] > 0)
            if mask.sum() < 3:
                continue
            # does A fall as B rises (and vice versa)? -> looks like succession
            a, b = di[mask], dj[mask]
            if a.std() < 1e-9 or b.std() < 1e-9:
                continue
            corr = float(np.corrcoef(a, -b)[0, 1])  # high => anti-correlated widths
            if corr < HANDOFF_CORR:
                continue
            # real transfer between them, relative to the larger peak?
            key = frozenset((i, j))
            frac = tf.get(key, 0.0) / max(peak[i], peak[j], 1e-12)
            if frac < TRANSFER_FRAC:
                forbidden.add(key)   # reads as handoff but none happened
    return forbidden


def violates(order, forbidden):
    for k in range(len(order) - 1):
        if frozenset((order[k], order[k + 1])) in forbidden:
            return True
    return False


def optimize(W, cols, transfer, max_passes=12):
    forbidden = forbidden_pairs(W, cols, transfer)
    order = inside_out(W)
    # nudge off any starting violations by local reinsertion
    best = wiggle(order, W)
    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(len(order) - 1):
            cand = order[:]
            cand[i], cand[i + 1] = cand[i + 1], cand[i]
            if violates(cand, forbidden):
                continue
            c = wiggle(cand, W)
            if c < best - 1e-12:
                order, best, improved = cand, c, True
    return order, forbidden


# ------------------------------------------------------------------- main
def emit_js(orders, presets, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "window.ORDERS = " + json.dumps(orders, separators=(",", ":")) + ";\n"
        "window.ORDER_PRESETS = " + json.dumps(presets, separators=(",", ":")) + ";\n"
    )
    out_path.write_text(body, encoding="utf-8")
    print(f"wrote {len(orders)} orders -> {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/orders.js")
    args = ap.parse_args()

    pop_share, area_share, transfer = load()
    orders = {}

    # simple lenses
    W, cols = width_simple(pop_share)
    order, _ = optimize(W, cols, transfer)
    orders["pop"] = [cols[i] for i in order]

    W, cols = width_simple(area_share)
    order, _ = optimize(W, cols, transfer)
    orders["area"] = [cols[i] for i in order]

    # composite, one per preset
    for name, w_area in POWER_PRESETS.items():
        W, cols = width_composite(pop_share, area_share, w_area)
        order, _ = optimize(W, cols, transfer)
        orders[f"power:{name}"] = [cols[i] for i in order]

    emit_js(orders, {"power": POWER_PRESETS}, Path(args.out))


if __name__ == "__main__":
    main()
