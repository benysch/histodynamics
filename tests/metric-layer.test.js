/* tests/metric-layer.test.js
 * Zero-dependency regression tests for the metric layer. No build, no install —
 * just the Node 18+ built-in runner:
 *
 *   node --test
 *
 * The web modules are browser IIFEs that attach to `window`; we give them a
 * minimal global and require them in load order, exactly as index.html does
 * (then re-create the Engine once the data globals are in place).
 *
 * What these lock:
 *   - prepareLeader (the phase-diagram fast path) is IDENTICAL to the engine's
 *     argmax at every weight — so the optimization can't silently drift from the
 *     composite math it's meant to mirror.
 *   - pickOrder distinguishes population-, territory-, and economy-led weights,
 *     so the 3-D preset matching doesn't regress back to the wArea-only collapse.
 *   - composite shares are a proper distribution (sum to 1) and the economy axis
 *     actually resolves a leader (guards the dropped-coordinate class of bug).
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

// --- load the web globals into a fake window ----------------------------------
global.window = {};
const WEB = path.join(__dirname, "..", "web");
for (const f of ["polities.js", "facts.js", "totals.js", "orders.js",
                 "lenses.js", "engine.js", "order.js", "sensitivity.js"]) {
  require(path.join(WEB, f));
}
const win = global.window;
win.Engine = win.createEngine();           // bind to the now-loaded data globals

// --- helpers ------------------------------------------------------------------
const POWER = win.LENS_BY_ID.power;
const KEYS = POWER.components.map((c) => c.weightKey);

function weightsFromBary(bary) {
  const w = {};
  POWER.components.forEach((c, i) => { w[c.weightKey] = bary[i]; });
  return w;
}

function engineLeader(year, bary) {
  // apply the same leadership policy (leaderOf) so parity tests the BLEND math,
  // not the policy: prepareLeader and the engine path must rank identically.
  const shares = win.Engine.computeSlice(POWER, year, weightsFromBary(bary)).shares;
  return win.Sensitivity.leaderOf(shares);
}

function spread(arr, n) {
  if (arr.length <= n) return arr.slice();
  const out = [];
  for (let i = 0; i < n; i++) out.push(arr[Math.floor((i * (arr.length - 1)) / (n - 1))]);
  return out;
}

const YEARS = win.Engine.sliceYears();
const SAMPLE_YEARS = spread(YEARS, 6);
const GRID = win.Sensitivity._simplexGrid(POWER.components.length, 16); // ~153 pts

// --- tests --------------------------------------------------------------------
test("prepareLeader matches the engine's argmax across the weight simplex", () => {
  let checked = 0;
  for (const year of SAMPLE_YEARS) {
    const fast = win.Sensitivity.prepareLeader("power", year);
    for (const bary of GRID) {
      assert.equal(
        fast(bary), engineLeader(year, bary),
        `leader mismatch at year ${year}, weights ${JSON.stringify(weightsFromBary(bary))}`
      );
      checked++;
    }
  }
  assert.ok(checked > 0, "grid produced no comparisons");
});

test("pickOrder gives distinct orders for population-, territory-, economy-led weights", () => {
  const pop  = win.pickOrder("power", { wPop: 1, wArea: 0, wGdp: 0 });
  const terr = win.pickOrder("power", { wPop: 0, wArea: 1, wGdp: 0 });
  const econ = win.pickOrder("power", { wPop: 0, wArea: 0, wGdp: 1 });

  assert.ok(Array.isArray(pop) && pop.length, "population-led order missing");
  assert.ok(Array.isArray(terr) && terr.length, "territory-led order missing");
  assert.ok(Array.isArray(econ) && econ.length, "economy-led order missing");

  // The whole point of the 3-D fix: economy-led must not collapse onto the
  // population order the way matching on wArea alone did.
  assert.notDeepEqual(pop, econ, "population- and economy-led share an order");
  assert.notDeepEqual(pop, terr, "population- and territory-led share an order");
});

test("composite shares sum to 1 per slice (proper distribution)", () => {
  const params = win.defaultParams(POWER);
  for (const year of YEARS) {
    const shares = win.Engine.computeSlice(POWER, year, params).shares;
    const ids = Object.keys(shares);
    if (!ids.length) continue;               // empty slice — nothing to normalize
    const sum = ids.reduce((a, k) => a + shares[k], 0);
    assert.ok(Math.abs(sum - 1) < 1e-9, `shares at year ${year} sum to ${sum}, not 1`);
  }
});

test("no catch-all bundle ('Unrecorded' / 'Smaller') is ever crowned leader", () => {
  for (const year of SAMPLE_YEARS) {
    const fast = win.Sensitivity.prepareLeader("power", year);
    for (const bary of GRID) {
      const leader = fast(bary);
      assert.notEqual(leader, null, `no leader at year ${year}`);
      assert.ok(
        !win.Sensitivity.isAggregate(leader),
        `aggregate "${leader}" led at year ${year}, weights ${JSON.stringify(weightsFromBary(bary))}`
      );
    }
  }
});

test("every simplex vertex resolves a leader, including pure economy", () => {
  // The dropped-third-coordinate bug made the economy corner unresolvable.
  for (const year of SAMPLE_YEARS) {
    const fast = win.Sensitivity.prepareLeader("power", year);
    assert.notEqual(fast([0, 0, 1]), null, `pure-economy weights leaderless at year ${year}`);
    assert.notEqual(fast([1, 0, 0]), null, `pure-population weights leaderless at year ${year}`);
    assert.notEqual(fast([0, 1, 0]), null, `pure-territory weights leaderless at year ${year}`);
  }
});
