/* sensitivity-panel.js
 * Renders the ternary "who leads" phase diagram into Demograph's sidebar and
 * computes the robustness ribbon for the focused stream. Pure view layer over
 * window.Sensitivity (sensitivity.js) — no math duplicated.
 *
 * Load after sensitivity.js. Uses Demograph's palette via CSS vars, so it sits
 * native in the cream/serif sidebar.
 *
 *   mountSensitivity({ container, lensId, onWeights })  -> { update }
 *     update({ year, params, focusId }) repaints. onWeights(params) fires when
 *     the user clicks a point in the triangle (links back to the lens controls).
 *
 *   ribbonPath(lensId, focusId, params, x, y, R)  -> SVG path "d" for the
 *     min/max band, given the chart's x(year) and y(share) scales. Draw it
 *     behind the focused stream (see the hook at the bottom).
 */
(function (global) {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  // barycentric vertices: Population (top), Territory (bl), Economy (br)
  var V = [[160, 20], [22, 286], [298, 286]];
  var R_FILL = 22;

  function cart(b) {
    return [b[0]*V[0][0] + b[1]*V[1][0] + b[2]*V[2][0],
            b[0]*V[0][1] + b[1]*V[1][1] + b[2]*V[2][1]];
  }
  function latBary(i, j, R) { return [i/R, j/R, (R - i - j)/R]; }
  function svg(tag, attrs) {
    var el = document.createElementNS(NS, tag);
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  function mountSensitivity(opts) {
    var lensId = opts.lensId || "power";
    var lens = global.LENS_BY_ID[lensId];
    var k = lens.components.length;            // 2 -> strip, 3 -> triangle

    var sec = document.createElement("div");
    sec.className = "sb-sec";
    var label = document.createElement("div");
    label.className = "sb-label"; label.textContent = "Who leads, by how you define power";
    sec.appendChild(label);

    var tri = svg("svg", { viewBox: "0 0 320 312", style: "width:100%;height:auto;cursor:crosshair" });
    sec.appendChild(tri);

    var summary = document.createElement("div");
    summary.className = "sb-note"; summary.style.marginTop = "8px"; summary.style.fontSize = "12.5px";
    var caveat = document.createElement("div");
    caveat.className = "sb-note"; caveat.style.color = "#9a5a2e"; caveat.style.display = "none";
    var legend = document.createElement("div");
    legend.className = "sb-note"; legend.style.marginTop = "8px";
    legend.style.display = "flex"; legend.style.flexWrap = "wrap"; legend.style.gap = "4px 12px";
    sec.appendChild(summary); sec.appendChild(caveat); sec.appendChild(legend);
    opts.container.appendChild(sec);

    var cur = { year: null, params: {}, focusId: null };

    function update(s) {
      cur = Object.assign(cur, s);
      paint();
    }

    function paint() {
      tri.innerHTML = "";
      var sweep = global.Sensitivity.leaderSweep(lensId, cur.year, R_FILL);
      // index sweep results by a grid lookup isn't needed — recolor by cell centroid
      var seen = {};
      for (var i = 0; i < R_FILL; i++) {
        for (var j = 0; i + j < R_FILL; j++) {
          cell(latBary(i, j, R_FILL), latBary(i+1, j, R_FILL), latBary(i, j+1, R_FILL), seen);
          if (i + j < R_FILL - 1)
            cell(latBary(i+1, j, R_FILL), latBary(i, j+1, R_FILL), latBary(i+1, j+1, R_FILL), seen);
        }
      }
      vlabel("Population", V[0][0], V[0][1] - 7, "middle");
      vlabel("Territory", V[1][0] - 2, V[1][1] + 16, "start");
      vlabel("Economy",  V[2][0] + 2, V[2][1] + 16, "end");
      marker();
      summary.textContent = global.Sensitivity.summarize(lensId, cur.focusId, cur.year, R_FILL);
      paintCaveat();
      paintLegend(seen);
    }

    function cell(a, b, c, seen) {
      var cen = [(a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3];
      var who = leaderAt(cen);
      seen[who] = 1;
      var pa = cart(a), pb = cart(b), pc = cart(c);
      tri.appendChild(svg("polygon", {
        points: pa[0]+","+pa[1]+" "+pb[0]+","+pb[1]+" "+pc[0]+","+pc[1],
        fill: global.Sensitivity.colorOf(who, "#ccc"), "fill-opacity": "0.9",
        "shape-rendering": "crispEdges"
      }));
    }

    // leader at one barycentric weight, via the same blend the engine uses
    function leaderAt(bary) {
      var params = {};
      lens.components.forEach(function (comp, idx) { params[comp.weightKey] = bary[idx]; });
      // reuse engine through a single-point sweep would be wasteful; ask Sensitivity
      var s = global.Sensitivity.leaderSweep; // (kept for parity; inline below)
      return leaderViaEngine(params);
    }
    function leaderViaEngine(params) {
      var r = global.Engine.computeSlice(lens, cur.year, params).shares;
      var best = null, bv = -Infinity;
      for (var p in r) if (r[p] > bv) { bv = r[p]; best = p; }
      return best;
    }

    function vlabel(t, x, y, anchor) {
      var el = svg("text", { x: x, y: y, "text-anchor": anchor,
        "font-family": '"Segoe UI",system-ui,sans-serif', "font-size": "11",
        "letter-spacing": "1.5", fill: "var(--muted)" });
      el.textContent = t.toUpperCase(); tri.appendChild(el);
    }

    function marker() {
      var bary = lens.components.map(function (c) { return cur.params[c.weightKey] || 0; });
      var sum = bary.reduce(function (a, b) { return a + b; }, 0) || 1;
      bary = bary.map(function (v) { return v / sum; });
      var p = cart(bary);
      tri.appendChild(svg("circle", { cx: p[0], cy: p[1], r: 7, fill: "none",
        stroke: "var(--ink)", "stroke-width": "1", opacity: "0.4" }));
      tri.appendChild(svg("circle", { cx: p[0], cy: p[1], r: 4, fill: "var(--ink)",
        stroke: "#fff", "stroke-width": "2" }));
    }

    function paintCaveat() {
      if (global.Sensitivity.lowConfidence(lensId, cur.params, cur.year)) {
        caveat.style.display = "block";
        caveat.textContent = "Economy is weighted heavily in " + cur.year +
          " CE, where GDP is an educated guess — read this region with care.";
      } else caveat.style.display = "none";
    }

    function paintLegend(seen) {
      legend.innerHTML = "";
      Object.keys(seen).forEach(function (id) {
        var item = document.createElement("span");
        item.style.display = "inline-flex"; item.style.alignItems = "center"; item.style.gap = "5px";
        item.innerHTML = '<span style="width:11px;height:11px;border-radius:2px;border:1px solid var(--outline);background:' +
          global.Sensitivity.colorOf(id, "#ccc") + '"></span>' + global.Sensitivity.nameOf(id);
        legend.appendChild(item);
      });
    }

    // click a point -> adopt those weights
    tri.addEventListener("click", function (e) {
      var pt = tri.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
      var loc = pt.matrixTransform(tri.getScreenCTM().inverse());
      var b = toBary(loc.x, loc.y);
      if (!b || !opts.onWeights) return;
      var params = {};
      lens.components.forEach(function (c, i) { params[c.weightKey] = b[i]; });
      opts.onWeights(params);   // lens controls re-emit -> rebuild + update()
    });

    return { update: update };
  }

  function toBary(x, y) {
    var d = (V[1][1]-V[2][1])*(V[0][0]-V[2][0]) + (V[2][0]-V[1][0])*(V[0][1]-V[2][1]);
    var a = ((V[1][1]-V[2][1])*(x-V[2][0]) + (V[2][0]-V[1][0])*(y-V[2][1])) / d;
    var b = ((V[2][1]-V[0][1])*(x-V[2][0]) + (V[0][0]-V[2][0])*(y-V[2][1])) / d;
    var c = 1 - a - b;
    if (a < -0.02 || b < -0.02 || c < -0.02) return null;
    a = Math.max(0, a); b = Math.max(0, b); c = Math.max(0, c);
    var s = a + b + c; return [a/s, b/s, c/s];
  }

  /* robustness ribbon path for the focused stream.
   * x: fn(year)->px ; y: fn(share)->px (Demograph's scales). Returns an SVG
   * "d" for a min..max band; draw it behind the focused stream. */
  function ribbonPath(lensId, focusId, params, x, y, R) {
    var pts = global.Sensitivity.robustnessRibbon(lensId, focusId, params, R || 10);
    var top = pts.map(function (p) { return x(p.year) + "," + y(p.max); });
    var bot = pts.slice().reverse().map(function (p) { return x(p.year) + "," + y(p.min); });
    return "M" + top.join("L") + "L" + bot.join("L") + "Z";
  }

  global.mountSensitivity = mountSensitivity;
  global.ribbonPath = ribbonPath;
})(window);

/* ---------------------------------------------------------------------------
 * FOCUS-DRAW HOOK (one edit in Demograph's renderer, see docs/INTEGRATION.md)
 *
 * When a polity is focused, draw the robustness band before its stream so the
 * uncertainty sits behind the solid line:
 *
 *   var band = window.ribbonPath(current.lensId, focusedId, current.params,
 *                                xScale, yScaleForFocusedStream);
 *   focusGroup.insert("path", ":first-child")
 *             .attr("d", band)
 *             .attr("fill", "var(--ink)").attr("fill-opacity", 0.10).attr("stroke", "none");
 *
 * Mount the panel alongside the lens controls:
 *
 *   var sens = window.mountSensitivity({
 *     container: document.getElementById("sidebar"),
 *     lensId: "power",
 *     onWeights: function (params) {          // user clicked the triangle
 *       current.params = params; rebuild();   // rebuild() also calls sens.update()
 *     }
 *   });
 *   // in rebuild(), after redraw:
 *   sens.update({ year: hoveredYear, params: current.params, focusId: focusedId });
 * ------------------------------------------------------------------------- */
