"""
emit_gdp_meta.py
================
Emit the per-polity, per-slice GDP *estimation fraction* the tooltip uses to be
honest about Maddison's pre-modern guesswork. Kept out of facts.js (which is raw
facts the engine consumes) because est_frac is presentation metadata only — the
GDP lens reads gdp_int_usd, the tooltip reads this.

  data/processed/gdp_intusd.csv  -> polity_id, year, gdp_int_usd, est_frac
       est_frac = share of the polity's GDP that rested on a fallback gdppc
                  (1.0 = entirely an educated guess; ~0 = real modern data).

Output (assigned to a global so the page needs no build step / no fetch):
  web/gdp_meta.js  ->  window.GDP_EST = { "<year>": { "<polity>": estFrac } }

Only entries with est_frac above MIN_FRAC are written; a missing entry means the
figure rests on real data (no note shown). Values are rounded to keep the file
small — a tooltip never needs more than whole percent.
"""

import argparse
import csv
import json
from pathlib import Path

MIN_FRAC = 0.005  # below this we show no "estimated" note, so don't ship it


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gdp", default="data/processed/gdp_intusd.csv")
    ap.add_argument("--out", default="web/gdp_meta.js")
    args = ap.parse_args()

    out: dict[str, dict[str, float]] = {}
    kept = 0
    with open(args.gdp, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ef = row.get("est_frac")
            if ef in (None, ""):
                continue
            try:
                frac = float(ef)
            except ValueError:
                continue
            if frac < MIN_FRAC:
                continue
            year = str(int(float(row["year"])))
            out.setdefault(year, {})[row["polity_id"]] = round(frac, 2)
            kept += 1

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
    path.write_text(f"window.GDP_EST = {payload};\n", encoding="utf-8")
    print(f"wrote {path}  ({path.stat().st_size:,} bytes, {kept} entries)")


if __name__ == "__main__":
    main()
