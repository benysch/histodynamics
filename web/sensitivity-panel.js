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
    var foot = document.createElement("div");
    foot.className = "sb-note"; foot.style.marginTop = "6px"; foot.style.opacity = ".7";
    foot.textContent = "\u201CLeads\u201D = top single polity; catch-all bundles (Unrecorded / Smaller) are excluded.";
    sec.appendChild(foot);

    // robustness ribbon: the focused leader's share band across ALL weightings,
    // over time — how much its prominence depends on how you define power.
    var ribLabel = document.createElement("div");
    ribLabel.className = "sb-label"; ribLabel.style.marginTop = "14px";
    var rib = svg("svg", { viewBox: "0 0 300 84", style: "width:100%;height:auto" });
    var ribNote = document.createElement("div");
    ribNote.className = "sb-note"; ribNote.style.opacity = ".7"; ribNote.style.marginTop = "2px";
    ribNote.textContent = "Shaded = share range over every weighting; line = your current weights.";
    sec.appendChild(ribLabel); sec.appendChild(rib); sec.appendChild(ribNote);
    opts.container.appendChild(sec);

    var cur = { year: null, params: {}, focusId: null };

    function update(s) {
      cur = Object.assign(cur, s);
      paint();
    }

    function paint() {
      tri.innerHTML = "";
      // Precompute the components' within-slice shares ONCE for this year; every
      // cell is then colored by a cheap weight-blend (math stays in sensitivity.js).
      // This used to call the full composite engine per cell —
      // O(cells x polities x components) on every repaint of the slider.
      var leaderAt = global.Sensitivity.prepareLeader(lensId, cur.year);
      var seen = {};
      for (var i = 0; i < R_FILL; i++) {
        for (var j = 0; i + j < R_FILL; j++) {
          cell(latBary(i, j, R_FILL), latBary(i+1, j, R_FILL), latBary(i, j+1, R_FILL), seen, leaderAt);
          if (i + j < R_FILL - 1)
            cell(latBary(i+1, j, R_FILL), latBary(i, j+1, R_FILL), latBary(i+1, j+1, R_FILL), seen, leaderAt);
        }
      }
      vlabel("Population", V[0][0], V[0][1] - 7, "middle");
      vlabel("Territory", V[1][0] - 2, V[1][1] + 16, "start");
      vlabel("Economy",  V[2][0] + 2, V[2][1] + 16, "end");
      marker();
      summary.textContent = global.Sensitivity.summarize(lensId, cur.focusId, cur.year, R_FILL);
      paintCaveat();
      paintLegend(seen);
      paintRibbon();
    }

    // share band of the focused leader across the whole weight simplex, per year
    function paintRibbon() {
      rib.innerHTML = "";
      if (!cur.focusId) { ribLabel.textContent = ""; return; }
      var pts = global.Sensitivity.robustnessRibbon(lensId, cur.focusId, cur.params, 10);
      if (!pts.length) return;
      ribLabel.textContent = "How robust is " + global.Sensitivity.nameOf(cur.focusId) + "?";
      var W = 300, H = 84, padL = 4, padR = 4, padT = 8, padB = 16;
      var y0 = pts[0].year, y1 = pts[pts.length - 1].year;
      var maxShare = 0;
      pts.forEach(function (p) { if (p.max > maxShare) maxShare = p.max; });
      maxShare = Math.max(maxShare, 1e-6);
      function X(yr) { return padL + (yr - y0) / ((y1 - y0) || 1) * (W - padL - padR); }
      function Y(sh) { return (H - padB) - sh / maxShare * (H - padT - padB); }
      var color = global.Sensitivity.colorOf(cur.focusId, "#888");

      // band (min..max)
      var top = pts.map(function (p) { return X(p.year) + "," + Y(p.max); });
      var bot = pts.slice().reverse().map(function (p) { return X(p.year) + "," + Y(p.min); });
      rib.appendChild(svg("path", { d: "M" + top.join("L") + "L" + bot.join("L") + "Z",
        fill: color, "fill-opacity": "0.22", stroke: "none" }));
      // current-weights line
      rib.appendChild(svg("path", {
        d: "M" + pts.map(function (p) { return X(p.year) + "," + Y(p.current); }).join("L"),
        fill: "none", stroke: color, "stroke-width": "1.5" }));
      // baseline + endpoint year ticks
      rib.appendChild(svg("line", { x1: padL, y1: H - padB, x2: W - padR, y2: H - padB,
        stroke: "var(--grid)", "stroke-width": "1" }));
      [[y0, "start", padL], [y1, "end", W - padR]].forEach(function (t) {
        var tx = svg("text", { x: t[2], y: H - 4, "text-anchor": t[1],
          "font-family": '"Segoe UI",system-ui,sans-serif', "font-size": "9", fill: "var(--muted)" });
        tx.textContent = (t[0] < 0 ? (-t[0]) + " BCE" : t[0] + " CE"); rib.appendChild(tx);
      });
    }

    function cell(a, b, c, seen, leaderAt) {
      // full 3-component centroid — the third coordinate (Economy) was dropped
      // before, so cells were colored as if economy weight were ~0 regardless of
      // their position toward the Economy vertex.
      var cen = [(a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3, (a[2]+b[2]+c[2])/3];
      var who = leaderAt(cen);
      seen[who] = 1;
      var pa = cart(a), pb = cart(b), pc = cart(c);
      tri.appendChild(svg("polygon", {
        points: pa[0]+","+pa[1]+" "+pb[0]+","+pb[1]+" "+pc[0]+","+pc[1],
        fill: global.Sensitivity.colorOf(who, "#ccc"), "fill-opacity": "0.9",
        "shape-rendering": "crispEdges"
      }));
    }

    // leader probing now uses Sensitivity.prepareLeader (see paint), which
    // precomputes component shares once per slice instead of per cell.

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
 * The robustness band is now drawn as a sparkline inside the panel itself
 * (paintRibbon, above): the focused leader's share range across every weighting,
 * over time. That path is self-contained and needs no renderer changes.
 *
 * OPTIONAL — overlay it ON the main chart's focused stream instead. `ribbonPath`
 * returns an SVG "d" given x(year)->px and y(share)->px. NOTE this chart is
 * VERTICAL: time is yScale(year) and width is xScale(share), and a focused
 * region is drawn split around its `anchor` stream with a silhouette offset — so
 * a from-origin band won't line up. To hug the drawn stream you'd pass the
 * focused region's own edge scales (not xScale from 0) and swap the coordinate
 * order so points read (sharePx, yearPx). Verify alignment in the browser before
 * relying on it — that geometry can't be checked headless.
 *
 *   sens.update({ year: hoveredYear, params: current.params, focusId: focusedId });
 * ------------------------------------------------------------------------- */
