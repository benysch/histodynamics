/* lenses.js  (v2 — adds GDP as a third power component)
 * Swappable metric definitions. Pure config — no normalization, no rendering.
 * See docs/metric-layer.md and docs/gdp-and-sensitivity.md.
 *
 * Load order: polities.js, facts.js, totals.js, lenses.js, engine.js, ...
 * Exposes: window.LENSES (ordered, for the selector) and window.LENS_BY_ID.
 */
(function (global) {
  "use strict";

  var POPULATION = {
    kind: "simple", id: "pop", label: "Population share",
    description: "Share of world population under each polity (Demograph's metric).",
    unit: "persons", totalKey: "population",
    extract: function (f) { return f && f.population != null ? f.population : null; }
  };

  var TERRITORY = {
    kind: "simple", id: "area", label: "Territory share",
    description: "Share of mapped land area under each polity.",
    unit: "km\u00B2", totalKey: "area_km2",
    extract: function (f) { return f && f.area_km2 != null ? f.area_km2 : null; }
  };

  var GDP = {
    kind: "simple", id: "gdp", label: "Economic share",
    description: "Share of world GDP under each polity (Maddison). " +
                 "Low confidence before ~1500, where it degrades toward population.",
    unit: "int$", totalKey: "gdp",
    lowConfidenceBefore: 1500,   // surfaced by the sensitivity view + tooltips
    extract: function (f) { return f && f.gdp_int_usd != null ? f.gdp_int_usd : null; }
  };

  // Composite: weighted blend of the three components' within-slice shares.
  // No `unit` => share-only; absolute mode disabled (spec §5).
  // engine.js iterates `components` generically, so adding GDP needs no engine change.
  var RELATIVE_POWER = {
    kind: "composite", id: "power", label: "Relative power (defined by you)",
    description:
      "Sparks left this metric undefined. Here you define it: a weighted blend " +
      "of population, territory, and economy. Shift the weights and watch the " +
      "chart reorder.",
    components: [
      { lensId: "pop",  weightKey: "wPop"  },
      { lensId: "area", weightKey: "wArea" },
      { lensId: "gdp",  weightKey: "wGdp"  }
    ],
    params: [
      { key: "wPop",  label: "Population", min: 0, max: 1, step: 0.05, default: 0.34 },
      { key: "wArea", label: "Territory",  min: 0, max: 1, step: 0.05, default: 0.33 },
      { key: "wGdp",  label: "Economy",    min: 0, max: 1, step: 0.05, default: 0.33 }
    ],
    presets: {
      "Demographic (= Demograph)": { wPop: 1.0,  wArea: 0.0,  wGdp: 0.0 },
      "Balanced":                  { wPop: 0.34, wArea: 0.33, wGdp: 0.33 },
      "Sparks-led (territory)":    { wPop: 0.25, wArea: 0.55, wGdp: 0.20 },
      "Economic":                  { wPop: 0.25, wArea: 0.15, wGdp: 0.60 }
    }
  };

  var LENSES = [POPULATION, TERRITORY, GDP, RELATIVE_POWER];
  var LENS_BY_ID = {};
  LENSES.forEach(function (l) { LENS_BY_ID[l.id] = l; });

  global.LENSES = LENSES;
  global.LENS_BY_ID = LENS_BY_ID;
})(window);
