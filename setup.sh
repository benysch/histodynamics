#!/usr/bin/env bash
#
# setup.sh — initialise the repo and create the commit history from
# docs/BUILD_ORDER.md, in order, using the files present in this snapshot.
#
# Usage:
#   ./setup.sh                         # local commits only
#   ./setup.sh git@github.com:you/repo.git   # also add origin + push
#
# Commits that require the Demograph import or edits to web/index.html cannot
# be scripted (those files aren't in this snapshot) — they're listed as manual
# steps at the end.

set -euo pipefail
REMOTE="${1:-}"

command -v git >/dev/null || { echo "git not found — install git first."; exit 1; }

if [ -d .git ] && git rev-parse HEAD >/dev/null 2>&1; then
  echo "This folder already has commits. Aborting so nothing is overwritten."
  exit 1
fi

git init -q
git symbolic-ref HEAD refs/heads/main 2>/dev/null || git branch -M main 2>/dev/null || true

c () { git add "$@" >/dev/null; }                 # stage
commit () { git commit -q -m "$1"; echo "  ✓ $1"; }

echo "Creating commit history…"

# 1 — project identity
c README.md NOTICE LICENSE .gitignore requirements.txt data/README.md data/processed/.gitkeep
commit "Project identity: README, NOTICE, LICENSE, scaffolding"

# (2 — Demograph import: manual, see end)

# 3 — design spec
c docs/metric-layer.md docs/INTEGRATION.md docs/BUILD_ORDER.md docs/prototype-lens-controls.html
commit "Design spec: metric layer, integration, build order"

# 4 — raw-facts pipeline (align_territory.py is the LIVE emitter; compute_area.py
#     and emit_facts.py are superseded Demograph templates, kept for reference)
c pipeline/align_territory.py pipeline/compute_area.py pipeline/emit_facts.py
commit "Pipeline: territory + raw-facts emission (align_territory; facts/totals/polities/orders)"

# 5+6 — metric engine (lenses + simple/composite engine; this snapshot ships
#        the v2 3-component lens config, GDP included)
c web/lenses.js web/engine.js
commit "Metric engine: lenses + computeShares (simple + composite)"

# 7 — per-lens ordering
c pipeline/compute_orders.py web/order.js
commit "Per-lens stacking order (wiggle + succession fidelity) + picker"

# 8 — lens controls + adapter
c web/lens-adapter.js
commit "Lens selector + composition controls; renderer adapter"

# (9 — renderer integration into web/index.html: manual)
# (10 — polish + deploy v0.1: manual)

# 11 — v0.2 design spec
c docs/gdp-and-sensitivity.md docs/prototype-sensitivity-panel.html
commit "v0.2 spec: GDP component + sensitivity view"

# 12 — GDP component (pipeline side; lens config already shipped in the engine commit)
c pipeline/compute_gdp.py pipeline/emit_gdp_meta.py
commit "GDP component: cell-attributed GDP per polity (Maddison) + est_frac meta"

# 13 — sensitivity engine + panel
c web/sensitivity.js web/sensitivity-panel.js
commit "Sensitivity view: leader-sweep, rank stability, ternary panel"

# (14 — robustness ribbon hook in web/index.html: manual)
# (15 — polish + deploy v0.2: manual)

echo
echo "Local history created:"
git --no-pager log --oneline

if [ -n "$REMOTE" ]; then
  echo; echo "Adding origin and pushing to $REMOTE …"
  git remote add origin "$REMOTE"
  git push -u origin main
else
  echo
  echo "No remote given. To push:"
  echo "  git remote add origin https://github.com/<you>/<repo>.git"
  echo "  git push -u origin main"
fi

cat << 'NOTE'

────────────────────────────────────────────────────────────────────────
MANUAL STEPS (need files not in this snapshot — see docs/BUILD_ORDER.md):
  • Commit 2  — import Demograph's pipeline + web/index.html (CC0) as a baseline,
                BEFORE the spec commit ideally. Since history is already made,
                you can add it now as a normal commit; order in the log won't be
                perfect but the code is what matters.
  • Commit 9  — wire the adapter into web/index.html (docs/INTEGRATION.md).
  • Commit 14 — add the robustness-ribbon hook (web/sensitivity-panel.js footer).
  • Commits 10 / 15 — polish + deploy to Vercel; tag v0.1 then v0.2.

BEFORE PUSHING:
  • Project name is Histodynamics (the "Polimetric" placeholder was renamed).
  • Confirm the Demograph author name in README acknowledgements.
────────────────────────────────────────────────────────────────────────
NOTE
