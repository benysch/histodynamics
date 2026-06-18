/* sample-data.js
 * ⚠️  ILLUSTRATIVE SAMPLE DATA — NOT the historical dataset.
 *
 * This file stands in for the four globals the pipeline is meant to emit
 * (polities.js, facts.js, totals.js, orders.js) so index.html is a live,
 * openable page before the Demograph foundation + pipeline output land.
 * The numbers are hand-picked world-fractions chosen to make ranks FLIP
 * between lenses (Steppe dominates territory; East/South Asia dominate
 * population and economy) — they are not real measurements.
 *
 * Replace this single <script> with the emitted polities.js / facts.js /
 * totals.js / orders.js and nothing else in index.html needs to change.
 *
 * Shapes (see docs/metric-layer.md):
 *   POLITIES      [{ id, name, civ }]
 *   FACTS         { "<year>": { "<id>": { population, area_km2, gdp_int_usd } } }
 *   TOTALS        { "<year>": { population, area_km2, gdp } }   (world denominators)
 *   ORDERS        { "<lensId>": [id…bottom→top], "power:<preset>": [id…] }
 *   ORDER_PRESETS { "power": { "<preset name>": wAreaValue } }
 */
(function (global) {
  "use strict";

  global.SAMPLE_DATA = true; // index.html shows a banner while this is set

  global.POLITIES = [
    { id: "eastasia",  name: "East Asia",      civ: "eastasia"  },
    { id: "southasia", name: "South Asia",     civ: "southasia" },
    { id: "europe",    name: "Europe & Med.",  civ: "europe"    },
    { id: "steppe",    name: "Steppe",         civ: "steppe"    },
    { id: "mideast",   name: "Middle East",    civ: "mideast"   },
    { id: "americas",  name: "Americas",       civ: "americas"  }
  ];

  // Values are world-fractions (raw ÷ world total). Column sums are < 1 on
  // purpose so the engine reports an honest "unmapped" residual.
  var YEARS = [-1000, 1, 1000, 1500, 1800, 2000];

  // per-metric fraction tables, indexed [polity][yearIndex]
  var POP = {
    eastasia:  [0.22, 0.27, 0.24, 0.26, 0.30, 0.30],
    southasia: [0.25, 0.26, 0.22, 0.24, 0.20, 0.22],
    europe:    [0.08, 0.14, 0.10, 0.13, 0.15, 0.10],
    steppe:    [0.04, 0.04, 0.05, 0.04, 0.02, 0.01],
    mideast:   [0.12, 0.08, 0.09, 0.06, 0.04, 0.05],
    americas:  [0.05, 0.04, 0.05, 0.07, 0.03, 0.12]
  };
  var AREA = {
    eastasia:  [0.07, 0.09, 0.10, 0.11, 0.12, 0.09],
    southasia: [0.04, 0.05, 0.05, 0.06, 0.07, 0.04],
    europe:    [0.05, 0.13, 0.08, 0.10, 0.18, 0.15],
    steppe:    [0.20, 0.22, 0.25, 0.20, 0.10, 0.06],
    mideast:   [0.08, 0.10, 0.12, 0.09, 0.06, 0.07],
    americas:  [0.03, 0.02, 0.03, 0.05, 0.10, 0.16]
  };
  var GDP = {
    eastasia:  [0.20, 0.26, 0.25, 0.28, 0.28, 0.22],
    southasia: [0.24, 0.28, 0.24, 0.25, 0.16, 0.07],
    europe:    [0.07, 0.15, 0.09, 0.14, 0.22, 0.25],
    steppe:    [0.02, 0.02, 0.03, 0.02, 0.01, 0.01],
    mideast:   [0.14, 0.09, 0.10, 0.05, 0.03, 0.05],
    americas:  [0.04, 0.03, 0.04, 0.05, 0.04, 0.25]
  };

  var FACTS = {};
  YEARS.forEach(function (y, i) {
    var slice = {};
    global.POLITIES.forEach(function (p) {
      slice[p.id] = {
        population:  POP[p.id][i],
        area_km2:    AREA[p.id][i],
        gdp_int_usd: GDP[p.id][i]
      };
    });
    FACTS[String(y)] = slice;
  });
  global.FACTS = FACTS;

  // World denominators = 1 (values are already fractions). The shortfall to 1
  // becomes the residual the engine surfaces.
  var TOTALS = {};
  YEARS.forEach(function (y) { TOTALS[String(y)] = { population: 1, area_km2: 1, gdp: 1 }; });
  global.TOTALS = TOTALS;

  // Baked stacking orders (bottom→top). Each lens reorders the stream.
  var byPop  = ["steppe", "americas", "mideast", "europe", "southasia", "eastasia"];
  var byArea = ["southasia", "americas", "eastasia", "mideast", "europe", "steppe"];
  var byGdp  = ["steppe", "mideast", "americas", "europe", "southasia", "eastasia"];
  var byMix  = ["steppe", "americas", "mideast", "europe", "southasia", "eastasia"];

  global.ORDERS = {
    pop:  byPop,
    area: byArea,
    gdp:  byGdp,
    "power:Demographic (= Demograph)": byPop,
    "power:Balanced":                  byMix,
    "power:Sparks-led (territory)":    byArea,
    "power:Economic":                  byGdp
  };

  // Maps each composite preset to its territory weight, so order.js can pick the
  // nearest baked order while you drag the balance. Must match lenses.js presets.
  global.ORDER_PRESETS = {
    power: {
      "Demographic (= Demograph)": 0.0,
      "Balanced":                  0.33,
      "Sparks-led (territory)":    0.55,
      "Economic":                  0.15
    }
  };
})(window);
