#!/usr/bin/env python3
"""Writes the Phase 4 markdown summary (GitHub step summary) from results/*.json."""
import argparse
import glob
import json
import os

LABELS = ["k07", "k08"]
TESTS = ["generation", "verapdf", "text_extraction", "render", "structure", "navigation", "perf", "determinism", "subsetting", "robustness"]


def pct(x):
    return f"{100.0 * x:.1f}%" if isinstance(x, (int, float)) else "-"


def load(results):
    res = {}
    for p in sorted(glob.glob(os.path.join(results, "*.json"))):
        name = os.path.splitext(os.path.basename(p))[0]
        try:
            res[name] = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            res[name] = {"error": repr(e)}
    return res


def cell(s):
    if s == "ok":
        return "ok"
    if s.startswith("refused"):
        return "R: " + s.split(":", 1)[1].strip().replace("|", "/")[:90]
    return s.split(":")[0].upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    res = load(args.results)
    md = ["# Phase 4: PDF output and validation (krilla)", "", "| test | krilla | pass | fail | total | pass rate |", "|---|---|---:|---:|---:|---:|"]
    for t in TESTS:
        for lb in LABELS:
            r = res.get(f"{t}_{lb}")
            if r is None:
                md.append(f"| {t} | {lb} | - | - | - | missing (job or step failed) |")
            else:
                md.append(f"| {t} | {lb} | {r.get('pass', '-')} | {r.get('fail', '-')} | {r.get('total', '-')} | {pct(r.get('pass_rate'))} |")
    md.append("")
    for lb in LABELS:
        g = res.get(f"generation_{lb}")
        if not g or "matrix" not in g:
            continue
        fixtures = sorted({f for row in g["matrix"].values() for f in row})
        md += [f"## krilla {g.get('krilla_version')} ({lb}): what krilla writes or refuses", "",
               f"Profiles not offered: {', '.join(g.get('profiles_not_offered', [])) or '-'}. Unsupported: " +
               "; ".join(f"{u['feature']} ({u['reason']})" for u in g.get("unsupported_features", [])), "",
               "| profile | " + " | ".join(fixtures) + " |", "|---|" + "---|" * len(fixtures)]
        for prof, row in g["matrix"].items():
            md.append(f"| {prof} | " + " | ".join(cell(row.get(f, "-")) for f in fixtures) + " |")
        md.append("")
    for lb in LABELS:
        v = res.get(f"verapdf_{lb}")
        if not v or "matrix" not in v:
            continue
        fixtures = sorted({f for row in v["matrix"].values() for f in row})
        md += [f"## veraPDF ({v.get('verapdf_version', '').splitlines()[0] if v.get('verapdf_version') else ''}) {lb}: profile x fixture", "",
               "| profile | " + " | ".join(fixtures) + " |", "|---|" + "---|" * len(fixtures)]
        for prof, row in v["matrix"].items():
            md.append(f"| {prof} | " + " | ".join(row.get(f, "-") for f in fixtures) + " |")
        md += ["", "| negative control | flavour | result | expected rule hit | failed rules |", "|---|---|---|---|---|"]
        for c in v.get("negative_controls", {}).get("controls", []):
            rules = ", ".join(f"{r.get('clause')}-{r.get('test')}" for r in c.get("failed_rules", [])[:5])
            md.append(f"| {c['id']} | {c['flavour']} | {c['result']} | {c.get('expected_rule_hit', '-')} | {rules} |")
        top = list(v.get("failed_rule_counts", {}).items())[:12]
        if top:
            md += ["", "Most frequent failed rules: " + "; ".join(f"{k} x{n}" for k, n in top)]
        md.append("")
    for lb in LABELS:
        t = res.get(f"text_extraction_{lb}")
        if not t or "per_extractor_script" not in t:
            continue
        scripts = sorted({s for e in t["per_extractor_script"].values() for s in e})
        md += [f"## Text extraction exact-match rate ({lb})", "", "| extractor | " + " | ".join(scripts) + " |", "|---|" + "---:|" * len(scripts)]
        for ex, row in t["per_extractor_script"].items():
            md.append(f"| {ex} | " + " | ".join(pct(row[s]["exact_rate"]) if s in row else "-" for s in scripts) + " |")
        md.append("")
    for lb in LABELS:
        r = res.get(f"render_{lb}")
        if not r or "per_renderer" not in r:
            continue
        md += [f"## Rendering consistency ({lb})", "", "| renderer | pages | agree | disagree | render error |", "|---|---:|---:|---:|---:|"]
        for k, a in r["per_renderer"].items():
            md.append(f"| {k} | {a['pages']} | {a['agree']} | {a['disagree']} | {a['render_error']} |")
        md += ["", "| pair | pages | disagree | mean fraction over threshold |", "|---|---:|---:|---:|"]
        for k, a in r.get("pairwise", {}).items():
            md.append(f"| {k} | {a['pages']} | {a['disagree']} | {pct(a['mean_frac_over'])} |")
        md.append("")
    for name, key in (("structure", "per_check"), ("navigation", "per_check")):
        for lb in LABELS:
            r = res.get(f"{name}_{lb}")
            if not r or key not in r:
                continue
            md += [f"## {name.capitalize()} checks ({lb})", "", "| check | pass | total |", "|---|---:|---:|"]
            for k, a in r[key].items():
                md.append(f"| {k} | {a['pass']} | {a['total']} |")
            md.append("")
    for lb in LABELS:
        r = res.get(f"perf_{lb}")
        if not r or "rows" not in r:
            continue
        md += [f"## Size and performance ({lb})", "", "| fixture | profile | pages | bytes | bytes/page | median ms | max RSS MiB | status |", "|---|---|---:|---:|---:|---:|---:|---|"]
        for row in r["rows"]:
            md.append(f"| {row['fixture']} | {row['profile']} | {row.get('pages', '-')} | {row.get('bytes', '-')} | "
                      f"{round(row['bytes_per_page']) if row.get('bytes_per_page') else '-'} | {row.get('median_ms', '-')} | "
                      f"{round(row['max_rss_mib'], 1) if row.get('max_rss_mib') else '-'} | {row.get('status')} |")
        md.append("")
    for lb in LABELS:
        r = res.get(f"subsetting_{lb}")
        if not r or "rows" not in r:
            continue
        md += [f"## Font subsetting ({lb})", "", "| fixture/profile | font | program | embedded bytes | original face bytes | ratio | glyphs | original glyphs |", "|---|---|---|---:|---:|---:|---:|---:|"]
        for row in r["rows"]:
            if row.get("error") == "not generated":
                continue
            md.append(f"| {row['fixture']}/{row['profile']} | {row.get('base_font')} | {row.get('program', row.get('subtype'))} | {row.get('embedded_bytes', '-')} | "
                      f"{row.get('original_face_bytes', '-')} | {pct(row.get('ratio_vs_face'))} | {row.get('glyphs', '-')} | {row.get('original_glyphs', '-')} |")
        md.append("")
    rob = {lb: res.get(f"robustness_{lb}") for lb in LABELS}
    if any(rob.values()):
        cases = []
        for r in rob.values():
            for row in (r or {}).get("rows", []):
                if row["case"] not in cases:
                    cases.append(row["case"])
        md += ["## Robustness", "", "| case | " + " | ".join(LABELS) + " |", "|---|" + "---|" * len(LABELS)]
        for c in cases:
            vals = []
            for lb in LABELS:
                row = next((x for x in (rob[lb] or {}).get("rows", []) if x["case"] == c), None)
                vals.append(f"{row['outcome']}{' (documented)' if row and row['documented_panic'] and not row['pass'] else ''}" if row else "-")
            md.append(f"| {c} | " + " | ".join(vals) + " |")
        md.append("")
    for lb in LABELS:
        d = res.get(f"determinism_{lb}")
        if d and d.get("first_failures"):
            md += [f"## Determinism failures ({lb})", ""] + [f"- {f['file']}: {json.dumps(f.get('detail'))[:300]}" for f in d["first_failures"][:10]] + [""]
    with open(args.out, "a", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
