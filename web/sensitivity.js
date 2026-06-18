/* sensitivity.js
 * How much does a ranking depend on the weights you chose? Because a composite
 * share is a LINEAR blend of the components' within-slice shares (before the
 * final per-slice normalization), the leader at weights w is argmax_p of a
 * linear function of w — so sweeping the weight simplex is just dot products on
 * precomputed component shares. No engine recompute, milliseconds.
 *
 * Depends on: window.Engine, window.LENS_BY_ID, window.POLITIES.
 * Exposes: window.Sensitivity with leaderSweep / rankStability / robustnessRibbon
 *          and helpers to drive the panel.
 *
 * See docs/gdp-and-sensitivity.md, Part B.
 */
(function (global) {
  "use strict";

  function compShares(lens, year) {
    // [{ weightKey, shares:{polity:share} }] for each component, at one slice
    return lens.components.map(function (c) {
      return {
        weightKey: c.weightKey,
        shares: global.Engine.computeSlice(global.LENS_BY_ID[c.lensId], year).shares
      };
    });
  }

  // mirrors engine.js composite: per-polity weight renormalization, then norm
  function blend(comps, weights) {
    var ids = {};
    comps.forEach(function (c) { for (var p in c.shares) ids[p] = 1; });
    var out = {}, sum = 0;
    Object.keys(ids).forEach(function (pid) {
      var avail = comps.filter(function (c) { return c.shares[pid] != null; });
      var wsum = avail.reduce(function (a, c) { return a + (weights[c.weightKey] || 0); }, 0);
      if (wsum <= 0) return;
      var v = 0;
      avail.forEach(function (c) { v += (weights[c.weightKey] / wsum) * c.shares[pid]; });
      out[pid] = v; sum += v;
    });
    if (sum > 0) for (var p in out) out[p] /= sum;
    return out;
  }

  // integer compositions of R into k parts -> barycentric grid over the simplex
  function simplexGrid(k, R) {
    var pts = [];
    (function rec(rem, depth, acc) {
      if (depth === k - 1) { pts.push(acc.concat(rem / R)); return; }
      for (var i = 0; i <= rem; i++) rec(rem - i, depth + 1, acc.concat(i / R));
    })(R, 0, []);
    return pts; // each entry sums to 1, length k
  }

  function weightsFrom(lens, bary) {
    var w = {};
    lens.components.forEach(function (c, i) { w[c.weightKey] = bary[i]; });
    return w;
  }

  function argmax(shares) {
    var best = null, bv = -Infinity;
    for (var p in shares) if (shares[p] > bv) { bv = shares[p]; best = p; }
    return best;
  }

  // Catch-all bundles ("Unrecorded X states", "Smaller X states") are residual
  // aggregates, not single polities. Because the composite renormalizes weights
  // per polity over the components it actually has, a population-only bundle can
  // out-score fully-attributed polities in GDP-sparse eras and falsely "lead" the
  // phase diagram. Exclude them from leadership only — they still render with
  // their honest blended widths in the chart.
  function isAggregate(id) { return /^(Unrecorded|Smaller)\b/.test(id); }

  // top single (non-aggregate) polity; falls back to aggregates only if a slice
  // somehow contains nothing else, so the diagram never goes blank.
  function leaderOf(shares) {
    var best = null, bv = -Infinity, p;
    for (p in shares) if (!isAggregate(p) && shares[p] > bv) { bv = shares[p]; best = p; }
    if (best == null) for (p in shares) if (shares[p] > bv) { bv = shares[p]; best = p; }
    return best;
  }

  /* who leads at each grid point. 2 comps -> strip; 3 -> ternary triangle. */
  function leaderSweep(lensId, year, R) {
    var lens = global.LENS_BY_ID[lensId];
    var comps = compShares(lens, year);
    return simplexGrid(lens.components.length, R || 16).map(function (bary) {
      var s = blend(comps, weightsFrom(lens, bary));
      var leader = leaderOf(s);
      return { bary: bary, leader: leader, share: leader ? s[leader] : 0 };
    });
  }

  /* Fast leader probe for one slice. Precomputes each component's within-slice
   * shares ONCE, then returns leader(bary) as a cheap weight-blend + argmax — no
   * per-call engine recompute. Use this to color a phase-diagram grid: the
   * component shares are identical at every weight, only the blend changes. */
  function prepareLeader(lensId, year) {
    var lens = global.LENS_BY_ID[lensId];
    var comps = compShares(lens, year);
    return function (bary) {
      return leaderOf(blend(comps, weightsFrom(lens, bary)));
    };
  }

  /* fraction of the weight space where `polityId` holds each rank + share range */
  function rankStability(lensId, polityId, year, R) {
    var lens = global.LENS_BY_ID[lensId];
    var comps = compShares(lens, year);
    var grid = simplexGrid(lens.components.length, R || 16);
    var rankCount = {}, n = grid.length, sMin = Infinity, sMax = 0, leadCount = 0;
    grid.forEach(function (bary) {
      var s = blend(comps, weightsFrom(lens, bary));
      var mine = s[polityId] || 0;
      sMin = Math.min(sMin, mine); sMax = Math.max(sMax, mine);
      var rank = 1;
      for (var p in s) if (!isAggregate(p) && s[p] > mine + 1e-12) rank++;
      rankCount[rank] = (rankCount[rank] || 0) + 1;
      if (rank === 1) leadCount++;
    });
    var rankFrac = {};
    for (var r in rankCount) rankFrac[r] = rankCount[r] / n;
    return { rankFrac: rankFrac, leadFrac: leadCount / n,
             shareMin: sMin === Infinity ? 0 : sMin, shareMax: sMax };
  }

  /* per-slice min/max share of `polityId` across the swept weights + current */
  function robustnessRibbon(lensId, polityId, params, R) {
    var lens = global.LENS_BY_ID[lensId];
    var years = global.Engine.sliceYears();
    var grid = simplexGrid(lens.components.length, R || 10);
    return years.map(function (year) {
      var comps = compShares(lens, year);
      var lo = Infinity, hi = 0;
      grid.forEach(function (bary) {
        var v = blend(comps, weightsFrom(lens, bary))[polityId] || 0;
        if (v < lo) lo = v; if (v > hi) hi = v;
      });
      var cur = blend(comps, params)[polityId] || 0;
      return { year: year, min: lo === Infinity ? 0 : lo, max: hi, current: cur };
    });
  }

  /* one-line summary for the readout */
  function summarize(lensId, polityId, year, R) {
    var st = rankStability(lensId, polityId, year, R);
    var name = nameOf(polityId);
    var pct = Math.round(st.leadFrac * 100);
    if (pct >= 50) return name + " leads across " + pct + "% of how you could define power.";
    if (pct > 0)  return name + " can lead, but only in " + pct + "% of the weight space.";
    return name + " never leads, however you weight it.";
  }

  function nameOf(id) {
    var p = (global.POLITIES || []).find(function (x) { return x.id === id; });
    return p ? p.name : id;
  }
  function colorOf(id, fallback) {
    var p = (global.POLITIES || []).find(function (x) { return x.id === id; });
    return (p && p.color) || fallback || "#888";
  }

  /* low-confidence flag: GDP-weighted view of a pre-1500 slice */
  function lowConfidence(lensId, params, year) {
    var lens = global.LENS_BY_ID[lensId];
    if (!lens.components) return false;
    return lens.components.some(function (c) {
      var sub = global.LENS_BY_ID[c.lensId];
      return sub.lowConfidenceBefore && year < sub.lowConfidenceBefore
             && (params[c.weightKey] || 0) > 0.25;
    });
  }

  global.Sensitivity = {
    leaderSweep: leaderSweep,
    prepareLeader: prepareLeader,
    leaderOf: leaderOf,
    isAggregate: isAggregate,
    rankStability: rankStability,
    robustnessRibbon: robustnessRibbon,
    summarize: summarize,
    lowConfidence: lowConfidence,
    nameOf: nameOf,
    colorOf: colorOf,
    _simplexGrid: simplexGrid
  };
})(window);
