/* order.js
 * Pick the precomputed stacking order (bottom -> top) for the active lens.
 * Load after orders.js (which sets window.ORDERS and window.ORDER_PRESETS).
 *
 * Simple lens  -> exact order by id.
 * Composite    -> nearest preset by weight, so free-dragging the balance only
 *                 RESCALES streams between presets instead of reordering them
 *                 mid-drag (which is what would look janky). Crossing the
 *                 midpoint between two presets is the one moment order changes.
 *
 * Returns an array of polity ids, or null if no order is available.
 */
(function (global) {
  "use strict";

  function nearestPreset(presets, wArea) {
    var bestKey = null, bestDist = Infinity;
    for (var name in presets) {
      if (!presets.hasOwnProperty(name)) continue;
      var dist = Math.abs(presets[name] - wArea);
      if (dist < bestDist) { bestDist = dist; bestKey = name; }
    }
    return bestKey;
  }

  // lensId: "pop" | "area" | "power"; params: { wPop, wArea } (composite only)
  global.pickOrder = function (lensId, params) {
    var ORDERS = global.ORDERS, PRESETS = global.ORDER_PRESETS;
    if (!ORDERS) return null;

    if (ORDERS[lensId]) return ORDERS[lensId];              // simple lens

    var presets = PRESETS && PRESETS[lensId];               // composite lens
    if (!presets) return null;
    var wArea = (params && params.wArea != null) ? params.wArea : 0.5;
    var key = nearestPreset(presets, wArea);
    return key ? (ORDERS[lensId + ":" + key] || null) : null;
  };
})(window);
