/* engine.js
 * The metric layer's compute core. Turns raw facts + a lens into per-slice
 * shares + an honest residual. No rendering, no colors, no stream order.
 * See docs/metric-layer.md §4 (normalization & composite math), §6 (residuals).
 *
 * Exposes window.createEngine(ctx?) -> engine, and a default window.Engine
 * bound to the page globals (FACTS / TOTALS / LENS_BY_ID).
 *
 * Contract note (read before wiring the renderer):
 *   - SIMPLE lens   -> shares + residual ≈ 1. Draw `residual` as the gray
 *                      "unmapped" band; shares + band fill the column.
 *   - COMPOSITE lens -> shares sum to 1 (streams fill the column). `residual`
 *                      is reported as a *diagnostic* (weighted blend of the
 *                      components' unmapped fractions), not a band. Surface it
 *                      as a readout, don't add it on top of the shares.
 */
(function (global) {
  "use strict";

  function num(v) { return (v == null || isNaN(v)) ? null : +v; }

  function sumValues(obj) {
    var s = 0;
    for (var k in obj) if (obj.hasOwnProperty(k)) s += obj[k];
    return s;
  }

  function createEngine(ctx) {
    ctx = ctx || {};
    var FACTS = ctx.facts || global.FACTS || {};
    var TOTALS = ctx.totals || global.TOTALS || {};
    var LENS_BY_ID = ctx.lensById || global.LENS_BY_ID || {};

    // --- simple lens: one raw fact, normalized within the slice -----------
    function simpleSlice(lens, year) {
      var facts = FACTS[String(year)] || {};
      var raw = {}, sum = 0, pid, v;
      for (pid in facts) {
        if (!facts.hasOwnProperty(pid)) continue;
        v = num(lens.extract(facts[pid]));
        if (v != null) { raw[pid] = v; sum += v; }
      }
      var totals = TOTALS[String(year)] || {};
      var denom = (lens.totalKey && totals[lens.totalKey] != null)
        ? totals[lens.totalKey] : sum;

      var shares = {};
      if (denom > 0) for (pid in raw) if (raw.hasOwnProperty(pid)) shares[pid] = raw[pid] / denom;

      var residual = Math.max(0, 1 - sumValues(shares));
      return { shares: shares, residual: residual, raw: raw, denom: denom };
    }

    // --- composite: weighted blend of components' within-slice shares -----
    function compositeSlice(lens, year, params) {
      params = params || defaultParams(lens);

      var comps = lens.components.map(function (c) {
        return { weightKey: c.weightKey, res: simpleSlice(LENS_BY_ID[c.lensId], year) };
      });

      var totalW = lens.components.reduce(function (a, c) {
        return a + (params[c.weightKey] || 0);
      }, 0);

      // union of polities present in any component
      var ids = {};
      comps.forEach(function (c) {
        for (var pid in c.res.shares) if (c.res.shares.hasOwnProperty(pid)) ids[pid] = true;
      });

      var blend = {}, blendSum = 0;
      Object.keys(ids).forEach(function (pid) {
        // weights re-normalized over the components THIS polity actually has
        var avail = comps.filter(function (c) { return c.res.shares[pid] != null; });
        var wsum = avail.reduce(function (a, c) { return a + (params[c.weightKey] || 0); }, 0);
        if (wsum <= 0) return;
        var v = 0;
        avail.forEach(function (c) {
          v += (params[c.weightKey] / wsum) * c.res.shares[pid];
        });
        blend[pid] = v; blendSum += v;
      });

      var shares = {};
      if (blendSum > 0) for (var p in blend) if (blend.hasOwnProperty(p)) shares[p] = blend[p] / blendSum;

      // diagnostic only (see contract note up top)
      var residual = 0;
      if (totalW > 0) comps.forEach(function (c) {
        residual += ((params[c.weightKey] || 0) / totalW) * c.res.residual;
      });

      return { shares: shares, residual: residual };
    }

    // --- public ------------------------------------------------------------
    function computeSlice(lens, year, params) {
      return lens.kind === "composite"
        ? compositeSlice(lens, year, params)
        : simpleSlice(lens, year);
    }

    function computeAll(lens, params, years) {
      years = years || sliceYears();
      return years.map(function (y) {
        var r = computeSlice(lens, y, params);
        return { year: y, shares: r.shares, residual: r.residual };
      });
    }

    // raw absolute values for the "absolute width" mode (simple lenses only)
    function computeAbsolute(lens, year) {
      if (!supportsAbsolute(lens)) {
        throw new Error("absolute mode unsupported for lens '" + lens.id + "' (no unit)");
      }
      return simpleSlice(lens, year).raw; // { polityId: rawValue } in lens.unit
    }

    function sliceYears() {
      return Object.keys(FACTS).map(Number).sort(function (a, b) { return a - b; });
    }

    return {
      computeSlice: computeSlice,
      computeAll: computeAll,
      computeAbsolute: computeAbsolute,
      sliceYears: sliceYears
    };
  }

  // --- lens helpers (no engine state needed) -------------------------------
  function supportsAbsolute(lens) { return lens.kind === "simple" && !!lens.unit; }

  function defaultParams(lens) {
    var p = {};
    (lens.params || []).forEach(function (spec) { p[spec.key] = spec.default; });
    return p;
  }

  global.createEngine = createEngine;
  global.supportsAbsolute = supportsAbsolute;
  global.defaultParams = defaultParams;

  // default engine bound to page globals; safe to call before data loads since
  // it reads the globals lazily on each call.
  global.Engine = createEngine();
})(window);
