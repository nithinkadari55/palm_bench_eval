#!/usr/bin/env python3
import argparse
import glob
import json
import os
import sys

EXPECTED = ["shaping_apt", "shaping_hb-matched", "harfrust_suite", "segmentation", "bidi", "bidi_parley",
            "hyphenation_licences", "hyphenation", "woff", "woff_robustness", "fallback", "parley_layout"]


def pct(x):
    return f"{100.0 * x:.2f}%" if isinstance(x, (int, float)) else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    res = {}
    for p in sorted(glob.glob(os.path.join(args.results, "*.json"))):
        name = os.path.splitext(os.path.basename(p))[0]
        try:
            res[name] = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            res[name] = {"error": repr(e)}
    md = ["# Phase 2: text and fonts", "", "| test | pass | fail | total | pass rate |", "|---|---:|---:|---:|---:|"]
    for name in EXPECTED + sorted(set(res) - set(EXPECTED)):
        r = res.get(name)
        if r is None:
            md.append(f"| {name} | - | - | - | missing (step failed) |")
            continue
        md.append(f"| {name} | {r.get('pass', '-')} | {r.get('fail', '-')} | {r.get('total', '-')} | {pct(r.get('pass_rate'))} |")
    md.append("")
    for name in ("shaping_apt", "shaping_hb-matched"):
        r = res.get(name)
        if r and "per_script" in r:
            md += [f"## {name} ({(r.get('hb_version') or '').splitlines()[0] if r.get('hb_version') else ''})", "",
                   "| script | cases | exact | rate | mismatch kinds |", "|---|---:|---:|---:|---|"]
            for k, v in r["per_script"].items():
                md.append(f"| {k} | {v['total']} | {v['exact']} | {pct(v['exact_rate'])} | {', '.join(f'{a}:{b}' for a, b in v['mismatch_kinds'].items())} |")
            md.append("")
    for name in ("segmentation", "bidi", "bidi_parley"):
        r = res.get(name)
        if r and "variants" in r:
            md += [f"## {name}", "", "| variant | pass | total | rate |", "|---|---:|---:|---:|"]
            for v in r["variants"]:
                md.append(f"| {v.get('name')} | {v.get('pass')} | {v.get('total')} | {pct(v.get('pass_rate'))} |")
            md.append("")
    r = res.get("hyphenation")
    if r and "languages" in r:
        md += ["## hyphenation", "", "| lang | words | same-pattern agreement | pyphen-dictionary agreement |", "|---|---:|---:|---:|"]
        for l in r["languages"]:
            if "same_patterns" in l:
                md.append(f"| {l['iso']} | {l['words']} | {pct(l['same_patterns']['rate'])} | {pct(l['pyphen_dictionary']['rate'])} |")
        md.append("")
    r = res.get("hyphenation_licences")
    if r and "inventory" in r:
        flagged = [f"{i['iso']} ({'/'.join(i['licences'])})" for i in r["inventory"] if i["flag"]]
        md += ["## hyphenation pattern licences", "", f"No MIT/Apache option: {', '.join(flagged) or 'none'}", ""]
    r = res.get("woff_robustness")
    if r and "by_category" in r:
        md += ["## woff robustness", "", f"safety failures (panic/crash/hang): {r.get('safety_failures')}", "",
               "| category | outcomes |", "|---|---|"]
        for k, v in r["by_category"].items():
            md.append(f"| {k} | {', '.join(f'{a}:{b}' for a, b in v.items())} |")
        md.append("")
    r = res.get("fallback")
    if r and "entries" in r:
        md += ["## font fallback", "", "| sample | coverage | uncovered |", "|---|---:|---|"]
        for e in r["entries"]:
            unc = " ".join(u["cp"] for u in e["uncovered"][:12])
            md.append(f"| {e['entry']} | {e['coverage_pct_full_chain']:.2f}% | {unc} |")
        md.append("")
    r = res.get("parley_layout")
    if r and "entries" in r:
        md += ["## parley layout", "", f"mean ms per 1k paragraphs: {r.get('mean_ms_per_1k_paragraphs', 0):.1f}", "",
               "| sample | layouts ok | unbreakable overflows | notdef glyphs | ms/1k |", "|---|---:|---:|---:|---:|"]
        for k, v in r["entries"].items():
            md.append(f"| {k} | {v['pass']}/{v['layouts']} | {v['unbreakable_overflows']} | {v['notdef_glyphs']} | {v['ms_per_1k_paragraphs']:.1f} |")
        md.append("")
    with open(args.out, "a", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
