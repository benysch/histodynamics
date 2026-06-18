"""
succession.py
=============
Shared core for succession-fidelity-constrained stream ordering. No IO — pure
arrays in, order out — so both the full pipeline (align_territory.py) and the
standalone re-optimizer (reoptimize_orders.py) call the same logic, and the
tests exercise it directly.

Two streams placed adjacent read as a handoff (one ends as the next begins). We
forbid an adjacency that *looks* like a succession (A falls as B rises) unless a
real population transfer between them justifies it. The objective is lexical:
first drive the count of forbidden adjacencies to zero, then minimize wiggle.
"""
from __future__ import annotations

import numpy as np

# documented knobs (kept in sync with the docstring in compute_orders.py)
HANDOFF_CORR = 0.55    # adjacency reads as a handoff above this anti-correlation
TRANSFER_FRAC = 0.05   # ...and is "real" only if transfer >= this fraction of the
                       #    larger stream's peak width. Below both -> forbidden.


def wiggle(order, W):
    """Sum over layers of Sum_t (delta cumulative-thickness-below)^2. Lower = calmer."""
    cum = np.zeros(W.shape[0])
    total = 0.0
    for idx in order:                 # bottom -> top
        d = np.diff(cum)
        total += float(np.dot(d, d))
        cum = cum + W[:, idx]
    return total


def inside_out(W):
    """d3-style: largest streams near the centre, balanced across the two sides."""
    sums = W.sum(axis=0)
    idxs = list(np.argsort(-sums))
    tops, bottoms, ts, bs = [], [], 0.0, 0.0
    for idx in idxs:
        if ts < bs:
            tops.append(idx); ts += sums[idx]
        else:
            bottoms.append(idx); bs += sums[idx]
    return list(reversed(bottoms)) + tops


def forbidden_pairs(W, streams, pair_transfer,
                    handoff_corr=HANDOFF_CORR, transfer_frac=TRANSFER_FRAC):
    """Index pairs that would be a FALSE handoff if placed adjacent.

    W            : years x streams width matrix (displayed shares).
    streams      : list of stream names, indexed like W's columns.
    pair_transfer: dict[frozenset({name_i, name_j})] -> transferred population.
                   (Already aggregated to the stream level by the caller, so this
                   stays agnostic to how raw polities map onto streams.)
    """
    n = len(streams)
    if n < 2:
        return set()
    peak = W.max(axis=0)
    d = np.diff(W, axis=0)             # slice-to-slice change per stream
    forbidden = set()
    for i in range(n):
        for j in range(i + 1, n):
            mask = (W[:-1, i] > 0) | (W[:-1, j] > 0)
            if mask.sum() < 3:
                continue
            a, b = d[mask, i], d[mask, j]
            if a.std() < 1e-9 or b.std() < 1e-9:
                continue
            corr = float(np.corrcoef(a, -b)[0, 1])   # high => widths move opposite
            if corr < handoff_corr:
                continue
            amt = pair_transfer.get(frozenset((streams[i], streams[j])), 0.0)
            frac = amt / max(peak[i], peak[j], 1e-12)
            if frac < transfer_frac:
                forbidden.add(frozenset((i, j)))      # reads as handoff, none happened
    return forbidden


def _violations(order, forbidden):
    return sum(1 for k in range(len(order) - 1)
               if frozenset((order[k], order[k + 1])) in forbidden)


def _violating_streams(order, forbidden):
    out = set()
    for k in range(len(order) - 1):
        if frozenset((order[k], order[k + 1])) in forbidden:
            out.add(order[k]); out.add(order[k + 1])
    return out


def _reinsert_repair(order, W, forbidden, best_v, best_w):
    """Adjacent swaps can't climb out of every local minimum (clearing the last
    violation may need a temporary increase). Reinserting a violating stream at
    its best feasible position is a bigger move that escapes those."""
    changed = True
    while changed and best_v > 0:
        changed = False
        for s in list(_violating_streams(order, forbidden)):
            rest = [x for x in order if x != s]
            cand_best = None
            for pos in range(len(rest) + 1):
                cand = rest[:pos] + [s] + rest[pos:]
                cv = _violations(cand, forbidden)
                cw = wiggle(cand, W)
                if cand_best is None or (cv, cw) < (cand_best[1], cand_best[2]):
                    cand_best = (cand, cv, cw)
            if cand_best and (cand_best[1] < best_v or
                              (cand_best[1] == best_v and cand_best[2] < best_w - 1e-12)):
                order, best_v, best_w = cand_best
                changed = True
    return order, best_v, best_w


def optimize(W, forbidden=None, max_passes=16):
    """Inside-out start, then local adjacent swaps. Acceptance is lexical:
    fewer forbidden adjacencies first, then lower wiggle. A reinsertion repair
    clears violations the swap search gets stuck on. Adjacent swaps can reach any
    permutation, so reachable violations are driven to zero with wiggle as the
    tie-break keeping the result calm."""
    forbidden = forbidden or set()
    order = inside_out(W)
    best_v, best_w = _violations(order, forbidden), wiggle(order, W)
    for _ in range(max_passes):
        improved = False
        for i in range(len(order) - 1):
            cand = order[:]
            cand[i], cand[i + 1] = cand[i + 1], cand[i]
            cv = _violations(cand, forbidden)
            if cv > best_v:
                continue
            cw = wiggle(cand, W)
            if cv < best_v or cw < best_w - 1e-12:
                order, best_v, best_w, improved = cand, cv, cw, True
        if not improved:
            break
    if best_v > 0:
        order, best_v, best_w = _reinsert_repair(order, W, forbidden, best_v, best_w)
    return order, best_v


def violations(order, forbidden):
    """Public: count forbidden adjacencies in an order (for reporting/tests)."""
    return _violations(order, forbidden)
