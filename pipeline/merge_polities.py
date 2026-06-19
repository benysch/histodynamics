"""
merge_polities.py
=================
Cliopatria splits some continuous states into several regime-phase names that
share ONE Wikidata entity (Brazil = Q155: "Brazilian Republic" + "Republic of
Brazil" + bundled "Unitary/Federated…"; Japan = Q188712; Pandya = Q844910). The
histomap then renders the same country as two streams that blink in and out.
This consolidates the *curated* true-duplicate groups into one stream each.

NOT merged (deliberately): same Wikidata ID but genuinely distinct — Wikidata
tagging errors (Han Q1068371 vs Chauhan, ~3400 km apart), intentional successions
the histomap shows on purpose (Roman vs Eastern Roman/Byzantine; Northern vs
Southern Song), real political splits (Kushan Empire vs Eastern/Western Kushans,
which coexist), and empire-vs-aggregate pairs (Holy Roman Empire vs its Minor
States). Each was checked by centroid distance, active spans, and name root.

Effects:
  - web/data.js: alias streams' population is folded into the canonical stream
    (shares recomputed against the unchanged world total); aliases are dropped
    from order/colorOrder/regions/subfamilies/series/lineage.
  - data/processed/polity_aliases.json: alias -> canonical, which
    align_territory.py applies so area/economy/urban/culture for the alias
    Cliopatria names route to the same canonical stream.
Re-run pipeline/align_territory.py afterwards to re-emit the web/*.js facts.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DATA_JS = WEB / "data.js"
ALIASES_OUT = ROOT / "data" / "processed" / "polity_aliases.json"

# canonical stream  <-  duplicate names to fold in (all share its Wikidata id)
MERGE = {
    "Republic of Brazil": ["Brazilian Republic"],   # Q155
    "Japan":              ["Empire of Japan"],       # Q188712
    "Pandya Dynasty":     ["Pandya Empire"],         # Q844910
}


def load():
    txt = DATA_JS.read_text(encoding="utf-8").strip()
    return json.loads(txt.replace("const HISTOMAP_DATA = ", "", 1).rstrip(";\n").rstrip(";"))


def apply_to_web_files(aliases):
    """Keep the other vendored web data in sync with the merge, so the visual
    map stays consistent with the streams. Idempotent."""
    # minimap.js (year frames) + events.js (anchors) + gdp_meta.js (est_frac per
    # polity-year): rename the alias to the canonical — the alias's entries were in
    # disjoint years, so they now attach to the merged stream rather than dangling.
    for fn in ("minimap.js", "events.js", "gdp_meta.js"):
        p = WEB / fn
        txt = p.read_text(encoding="utf-8")
        for old, new in aliases.items():
            txt = txt.replace(f'"{old}"', f'"{new}"')
        p.write_text(txt, encoding="utf-8")
        print(f"  synced {fn} (alias -> canonical)")

    # regions.js (REGION_FOCUS): names are object KEYS and the canonical already
    # exists, so renaming would collide — drop the alias keys instead (the
    # canonical keeps its own home/family/region-grid entry).
    p = WEB / "regions.js"
    prefix = "const REGION_FOCUS = "
    obj = json.loads(p.read_text(encoding="utf-8").strip()[len(prefix):].rstrip(";\n").rstrip(";"))
    drop = set(aliases)

    def prune(x):
        if isinstance(x, dict):
            for k in list(x):
                if k in drop:
                    del x[k]
                else:
                    prune(x[k])
        elif isinstance(x, list):
            for it in x:
                prune(it)

    prune(obj)
    p.write_text(prefix + json.dumps(obj) + ";\n", encoding="utf-8")
    print("  synced regions.js (dropped alias keys)")


def main():
    D = load()
    order = D["order"]; residual = D["residual"]; series = D["series"]
    n = len(D["years"])
    world = [sum((series[k][i]["pop"] or 0.0) for k in order) for i in range(n)]

    drop = set()
    for canon, aliases in MERGE.items():
        present = [a for a in aliases if a in series]
        if canon not in series or not present:
            print(f"skip {canon}: canonical or all aliases absent")
            continue
        for i in range(n):
            pop = (series[canon][i]["pop"] or 0.0) + sum(series[a][i]["pop"] or 0.0 for a in present)
            series[canon][i]["pop"] = pop
            series[canon][i]["share"] = (pop / world[i]) if world[i] else 0.0
        drop.update(present)
        print(f"merged {present} -> {canon} "
              f"(now active {sum(1 for s in series[canon] if s['pop']>0)} slices)")

    # remove dropped aliases everywhere they appear
    D["order"] = [k for k in D["order"] if k not in drop]
    if "colorOrder" in D:
        D["colorOrder"] = [k for k in D["colorOrder"] if k not in drop]
    for key in ("regions", "subfamilies", "series", "lineage"):
        if key in D:
            for a in drop:
                D[key].pop(a, None)

    DATA_JS.write_text("const HISTOMAP_DATA = " + json.dumps(D) + ";\n", encoding="utf-8")
    print(f"wrote {DATA_JS.relative_to(ROOT)} ({len(D['order'])} streams, was {len(order)})")

    aliases = {a: canon for canon, al in MERGE.items() for a in al}
    ALIASES_OUT.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {ALIASES_OUT.relative_to(ROOT)} ({len(aliases)} aliases)")

    print("syncing other web data files with the merge:")
    apply_to_web_files(aliases)


if __name__ == "__main__":
    main()
