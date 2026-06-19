/* order.js
 * Pick the precomputed stacking order (bottom -> top) for the active lens.
 * Load after orders.js (window.ORDERS / window.ORDER_PRESETS) and lenses.js
 * (window.LENS_BY_ID, which carries each composite's full preset weights).
 *
 * Simple lens  -> exact order by id.
 * Composite    -> nearest preset by weight, so free-dragging the weights only
 *                 RESCALES streams between presets instead of reordering them
 *                 mid-drag (which is what would look janky). Crossing the
 *                 boundary between two presets is the one moment order changes.
 *
 * The match is done in the FULL weight space (population / territory / economy),
 * not just the territory axis. Matching on wArea alone collapsed the simplex
 * onto one dimension, so e.g. population-led (wPop=1) and economy-led (wGdp=1)
 * both read as wArea=0 and shared the "Demographic" order. Comparing the whole
 * normalized weight vector keeps those orders distinct.
 *
 * Returns an array of polity ids, or null if no order is available.
 */
(function (global) {
  "use strict";

  // direction-only: the engine renormalizes weights per polity, so only the
  // blend's direction matters for picking an order, not its magnitude.
  function normalize(w, keys) {
    var sum = 0, i;
    for (i = 0; i < keys.length; i++) sum += (w[keys[i]] || 0);
    var out = {};
    for (i = 0; i < keys.length; i++) out[keys[i]] = sum > 0 ? (w[keys[i]] || 0) / sum : 0;
    return out;
  }

  // nearest preset by squared distance over the full weight vector
  function nearestPresetND(presetWeights, keys, target) {
    var t = normalize(target, keys);
    var bestKey = null, bestDist = Infinity;
    for (var name in presetWeights) {
      if (!presetWeights.hasOwnProperty(name)) continue;
      var p = normalize(presetWeights[name], keys), d = 0;
      for (var i = 0; i < keys.length; i++) {
        var diff = p[keys[i]] - t[keys[i]];
        d += diff * diff;
      }
      if (d < bestDist) { bestDist = d; bestKey = name; }
    }
    return bestKey;
  }

  // legacy 1-D fallback: ORDER_PRESETS stores a single wArea scalar per preset
  function nearestPreset1D(presets, wArea) {
    var bestKey = null, bestDist = Infinity;
    for (var name in presets) {
      if (!presets.hasOwnProperty(name)) continue;
      var dist = Math.abs(presets[name] - wArea);
      if (dist < bestDist) { bestDist = dist; bestKey = name; }
    }
    return bestKey;
  }

  // lensId: "pop" | "area" | "gdp" | "power"; params: composite weights only
  global.pickOrder = function (lensId, params) {
    var ORDERS = global.ORDERS, PRESETS = global.ORDER_PRESETS;
    if (!ORDERS) return null;

    if (ORDERS[lensId]) return ORDERS[lensId];              // simple lens

    var lens = global.LENS_BY_ID && global.LENS_BY_ID[lensId];

    // A simple lens with no baked order (e.g. a freshly added vector dimension)
    // must still render: fall back to population's order — it only loses the
    // per-lens re-stacking, never the stream set. Without this buildSeries gets
    // an empty order and the lens draws blank/stale.
    if (!(lens && lens.presets && lens.components)) {
      var presets1 = PRESETS && PRESETS[lensId];
      if (!presets1) return ORDERS.pop || null;             // not a composite -> fall back
      var wArea = (params && params.wArea != null) ? params.wArea : 0.5;
      var k1 = nearestPreset1D(presets1, wArea);
      return k1 ? (ORDERS[lensId + ":" + k1] || ORDERS.pop || null) : (ORDERS.pop || null);
    }

    // composite (full ND weight match)
    var keys = lens.components.map(function (c) { return c.weightKey; });
    var key = nearestPresetND(lens.presets, keys, params || {});
    return key ? (ORDERS[lensId + ":" + key] || ORDERS.pop || null) : (ORDERS.pop || null);
  };
})(window);
