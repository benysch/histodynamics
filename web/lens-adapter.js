/* lens-adapter.js
 * The seam between the metric layer and Demograph's existing D3 renderer.
 *
 * Demograph builds its stream once from a precomputed global (web/data.js) and
 * redraws on control changes. We don't replace that renderer — we regenerate
 * its input from the active lens and call its redraw. This file does two jobs:
 *
 *   buildSeries(lensId, params, opts)  -> the per-layer structure for a lens
 *   mountLensControls(opts)            -> a native sidebar section that emits
 *                                         { lensId, params, widthMode }
 *
 * Load order: polities.js, facts.js, totals.js, orders.js, lenses.js,
 *             engine.js, order.js, lens-adapter.js, then Demograph's script.
 *
 * Controls use Demograph's own classes (.sb-sec/.sb-label/.seg/.opt) so they
 * inherit its palette — the dark "instrument" demo earlier was only for
 * evaluating the UX; inside the app the controls should look native.
 */
(function (global) {
  "use strict";

  /* ---------------------------------------------------- buildSeries -------
   * Returns:
   *   { lensId, mode, years:[...], order:[polityId...bottom→top],
   *     layers:[ {id, name, civ, values:[per-year]} ],   // in stack order
   *     residual:[per-year] }                            // gray unmapped band
   *
   * `values` are shares (sum→1 for composite; sum+residual→1 for simple), or
   * raw units when mode === 'absolute' (simple lenses only — the trumpet bell).
   */
  function buildSeries(lensId, params, opts) {
    opts = opts || {};
    var lens = global.LENS_BY_ID[lensId];
    var engine = global.Engine;
    var years = engine.sliceYears();
    var order = global.pickOrder(lensId, params) || [];

    var absolute = opts.widthMode === "absolute" && global.supportsAbsolute(lens);

    var perYear = years.map(function (y) {
      if (absolute) return { shares: engine.computeAbsolute(lens, y), residual: 0 };
      return engine.computeSlice(lens, y, params);
    });

    var byId = {};
    (global.POLITIES || []).forEach(function (p) { byId[p.id] = p; });

    var layers = order.map(function (id) {
      var p = byId[id] || { id: id, name: id, civ: "unknown" };
      return {
        id: id, name: p.name, civ: p.civ,
        values: perYear.map(function (r) { return r.shares[id] || 0; })
      };
    });

    return {
      lensId: lensId,
      mode: absolute ? "absolute" : "share",
      years: years,
      order: order,
      layers: layers,
      residual: perYear.map(function (r) { return r.residual || 0; })
    };
  }

  /* ------------------------------------------------ mountLensControls -----
   * opts: { container, onChange }   onChange({ lensId, params, widthMode })
   */
  var POP = "#B5762E", TERR = "#2E7D74"; // population / territory accents (cream-safe)

  function mountLensControls(opts) {
    var host = opts.container;
    var state = { lensId: "pop", territoryWeight: 50, widthMode: "share" };
    var lenses = global.LENSES;
    var powerLens = global.LENS_BY_ID.power;

    var sec = el("div", "sb-sec");
    sec.appendChild(el("div", "sb-label", "Measure by"));

    // lens selector (Demograph .seg idiom)
    var seg = el("div", "seg");
    lenses.forEach(function (lens) {
      var o = el("div", "opt", lens.label);
      o.dataset.id = lens.id;
      o.onclick = function () { selectLens(lens.id); };
      seg.appendChild(o);
    });
    sec.appendChild(seg);

    // composition (composite only)
    var comp = el("div", "lens-comp");
    comp.style.marginTop = "10px";
    comp.style.display = "none";
    var lead = el("div", "sb-note", "Define what power means — drag to shift its source.");
    var bal = document.createElement("input");
    bal.type = "range"; bal.min = 0; bal.max = 100; bal.step = 5; bal.value = 50;
    bal.style.width = "100%";
    bal.setAttribute("aria-label", "Power composition: 0 all population, 100 all territory");
    bal.oninput = function () { setBalance(+bal.value); };
    var readout = el("div", "sb-note");
    readout.style.display = "flex";
    readout.style.justifyContent = "space-between";
    var rPop = el("span", null, "Population 50%"); rPop.style.color = POP;
    var rTerr = el("span", null, "Territory 50%"); rTerr.style.color = TERR;
    readout.appendChild(rPop); readout.appendChild(rTerr);
    var presets = el("div", "seg");
    Object.keys(powerLens.presets).forEach(function (name) {
      var o = el("div", "opt", name);
      o.dataset.w = String(powerLens.presets[name].wArea * 100);
      o.onclick = function () { setBalance(+o.dataset.w); };
      presets.appendChild(o);
    });
    comp.appendChild(lead); comp.appendChild(bal);
    comp.appendChild(readout); comp.appendChild(presets);
    sec.appendChild(comp);

    // width mode
    var wlabel = el("div", "sb-label", "Width shows");
    wlabel.style.marginTop = "12px";
    var wseg = el("div", "seg");
    var wShare = el("div", "opt active", "Share");
    var wAbs = el("div", "opt", "Absolute");
    wShare.onclick = function () { setWidth("share"); };
    wAbs.onclick = function () { setWidth("absolute"); };
    wseg.appendChild(wShare); wseg.appendChild(wAbs);
    var why = el("div", "sb-note");
    sec.appendChild(wlabel); sec.appendChild(wseg); sec.appendChild(why);

    host.appendChild(sec);

    function selectLens(id) {
      state.lensId = id;
      mark(seg, "id", id);
      var composite = global.LENS_BY_ID[id].kind === "composite";
      comp.style.display = composite ? "block" : "none";
      wAbs.style.opacity = composite ? ".4" : "";
      wAbs.style.pointerEvents = composite ? "none" : "";
      if (composite && state.widthMode === "absolute") setWidth("share");
      updateWhy(); emit();
    }
    function setBalance(v) {
      state.territoryWeight = v; bal.value = v;
      rPop.textContent = "Population " + (100 - v) + "%";
      rTerr.textContent = "Territory " + v + "%";
      markVal(presets, "w", String(v));
      emit();
    }
    function setWidth(mode) {
      if (mode === "absolute" && wAbs.style.pointerEvents === "none") return;
      state.widthMode = mode;
      wShare.classList.toggle("active", mode === "share");
      wAbs.classList.toggle("active", mode === "absolute");
      updateWhy(); emit();
    }
    function updateWhy() {
      why.textContent = (wAbs.style.pointerEvents === "none")
        ? "Absolute needs one unit — a blend of shares has none."
        : (state.widthMode === "absolute"
            ? "Columns grow with the raw total — the chart flares as population climbs."
            : "");
    }
    function emit() {
      var params = {
        wPop: (100 - state.territoryWeight) / 100,
        wArea: state.territoryWeight / 100
      };
      opts.onChange({ lensId: state.lensId, params: params, widthMode: state.widthMode });
    }

    setBalance(50); selectLens("pop");
    return { state: state };
  }

  // --- tiny DOM helpers ---
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function mark(seg, key, val) {
    Array.prototype.forEach.call(seg.children, function (o) {
      o.classList.toggle("active", o.dataset[key] === val);
    });
  }
  function markVal(seg, key, val) {
    Array.prototype.forEach.call(seg.children, function (o) {
      o.classList.toggle("active", o.dataset[key] === val);
    });
  }

  global.buildSeries = buildSeries;
  global.mountLensControls = mountLensControls;
})(window);
