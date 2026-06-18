"""
reoptimize_orders.py
====================
Re-emit web/orders.js with succession fidelity ON, working entirely from data
already in the repo — no raw Cliopatria/HYDE download, no rasterio:

  inputs : web/facts.js, web/totals.js, web/orders.js  (emitted shares + stream set)
           data/processed/transfer_matrix.csv          (succession transfers)
  output : web/orders.js                                (same format)

It rebuilds each lens's displayed widths exactly as engine.js does (component
shares over TOTALS, composite = per-stream weight-renormalized blend), maps the
transfer matrix onto the stream set, and runs the constrained optimizer from
succession.py. Population keeps Demograph's order (as align_territory.py does);
territory, economy, and each power preset are re-stacked under the constraint.

Coverage note: the transfer matrix is keyed by *raw* polity names. Here we map
the ones that are already stream names (the prominent streams — the ones that
actually risk reading as a false handoff with another single stream); sub-
threshold raw polities that roll into "Smaller/Unrecorded" bundles are dropped.
The full pipeline (align_territory.py) maps 100% via its name->stream classifier;
this standalone covers the majority of the transfer mass and is what regenerates
orders.js without the raw data in hand.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import succession

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
TRANSFERS = ROOT / "data" / "processed" / "transfer_matrix.csv"

# label -> (wPop, wArea, wGdp); must match web/lenses.js and align_territory.py
PRESETS = {
    "Demographic (= Demograph)": (1.0, 0.0, 0.0),
    "Balanced":                  (0.34, 0.33, 0.33),
    "Sparks-led (territory)":    (0.25, 0.55, 0.20),
    "Economic":                  (0.25, 0.15, 0.60),
}


# ----------------------------------------------------------------- loaders
def load_global(path: Path, name: str):
    """Parse a `window.NAME = {...};` file into a Python object (it's pure JSON)."""
    txt = path.read_text(encoding="utf-8")
    m = re.search(r"window\." + name + r"\s*=\s*(\{.*?\}|\[.*?\])\s*;", txt, re.S)
    if not m:
        raise ValueError(f"could not find window.{name} in {path}")
    return json.loads(m.group(1))


def component_shares(facts, totals, streams, years):
    """engine.js simpleSlice for each component: fact / TOTALS[key], per stream."""
    def share(fact_key, total_key):
        out = {s: np.zeros(len(years)) for s in streams}
        for i, y in enumerate(years):
            denom = totals[str(y)].get(total_key) or 0.0
            if denom <= 0:
                continue
            slc = facts[str(y)]
            for s in streams:
                f = slc.get(s)
                if f and f.get(fact_key) is not None:
                    out[s][i] = f[fact_key] / denom
        return out
    return (share("population", "population"),
            share("area_km2", "area_km2"),
            share("gdp_int_usd", "gdp"))


def present_flags(facts, streams, years):
    """Which components each stream carries per slice (for weight renorm)."""
    has = {k: {s: np.zeros(len(years), bool) for s in streams}
           for k in ("population", "area_km2", "gdp_int_usd")}
    for i, y in enumerate(years):
        for s, f in facts[str(y)].items():
            if s not in has["population"]:
                continue
            for k in has:
                if f.get(k) is not None:
                    has[k][s][i] = True
    return has


def blend_widths(pop, area, gdp, has, streams, years, wp, wa, wg):
    """engine.js compositeSlice: per-stream weight renorm over present components,
    then per-slice normalize to sum 1."""
    W = np.zeros((len(years), len(streams)))
    for i in range(len(years)):
        col = np.zeros(len(streams))
        for j, s in enumerate(streams):
            comps = []
            if has["population"][s][i]: comps.append((wp, pop[s][i]))
            if has["area_km2"][s][i]:   comps.append((wa, area[s][i]))
            if has["gdp_int_usd"][s][i]: comps.append((wg, gdp[s][i]))
            wsum = sum(w for w, _ in comps)
            col[j] = sum(w * sh for w, sh in comps) / wsum if wsum > 0 else 0.0
        tot = col.sum()
        if tot > 0:
            col /= tot
        W[i] = col
    return W


def stream_transfers(streams):
    """Aggregate transfer_matrix.csv onto stream pairs (exact name match)."""
    sset = set(streams)
    pair = {}
    if not TRANSFERS.exists():
        return pair
    tf = pd.read_csv(TRANSFERS)
    for a, b, p in zip(tf["from"], tf["to"], tf["population"]):
        if a in sset and b in sset and a != b:
            key = frozenset((a, b))
            pair[key] = pair.get(key, 0.0) + float(p)
    return pair


def mat(share_dict, streams, years):
    return np.array([share_dict[s] for s in streams]).T  # years x streams


# -------------------------------------------------------------------- main
def main():
    facts = load_global(WEB / "facts.js", "FACTS")
    totals = load_global(WEB / "totals.js", "TOTALS")
    streams = load_global(WEB / "orders.js", "ORDERS")["pop"]  # Demograph's order
    years = sorted(int(y) for y in facts.keys())

    pop, area, gdp = component_shares(facts, totals, streams, years)
    has = present_flags(facts, streams, years)
    pair = stream_transfers(streams)
    print(f"streams: {len(streams)}  years: {len(years)}  "
          f"stream-level transfer pairs: {len(pair)}")

    def order_for(W):
        forb = succession.forbidden_pairs(W, streams, pair)
        base = succession.inside_out(W)
        order, viol = succession.optimize(W, forb)
        names = [streams[i] for i in order]
        print(f"   forbidden pairs: {len(forb):3d}  "
              f"violations baseline->final: {succession.violations(base, forb)}->{viol}  "
              f"wiggle {succession.wiggle(order, W):.4g}")
        return names

    orders = {"pop": streams}  # keep Demograph's wiggle-optimized population order
    print("area:");    orders["area"] = order_for(mat(area, streams, years))
    print("gdp:");     orders["gdp"]  = order_for(mat(gdp, streams, years))
    for label, (wp, wa, wg) in PRESETS.items():
        print(f"power:{label}:")
        W = blend_widths(pop, area, gdp, has, streams, years, wp, wa, wg)
        orders[f"power:{label}"] = order_for(W)

    body = ("window.ORDERS = " + json.dumps(orders, separators=(",", ":")) + ";\n" +
            "window.ORDER_PRESETS = " +
            json.dumps({"power": {k: v[1] for k, v in PRESETS.items()}},
                       separators=(",", ":")) + ";\n")
    (WEB / "orders.js").write_text(body, encoding="utf-8")
    print(f"wrote {len(orders)} orders -> {WEB / 'orders.js'}")


if __name__ == "__main__":
    main()
