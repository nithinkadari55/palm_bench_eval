#!/usr/bin/env python3
"""Writes the phase 5 markdown summary (GitHub step summary) from the results directory."""
import argparse
import glob
import json
import os
import sys


def load(results, name):
    p = os.path.join(results, name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def pct(x):
    return f"{100.0 * x:.2f}%" if isinstance(x, (int, float)) else "-"


def num(x, fmt="{:.0f}"):
    return fmt.format(x) if isinstance(x, (int, float)) else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    R = a.results
    md = ["# Phase 5: JavaScript runtime", ""]

    # 1. test262
    md += ["## 1. ECMAScript conformance (test262)", "", "| run | engine | commit | executions | pass | fail | crash | timeout | pass rate | files skipped |",
           "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    t262 = {}
    for name in ("test262_qjs", "test262_boa", "test262_intl402_qjs", "test262_intl402_boa"):
        r = load(R, name + ".json")
        t262[name] = r
        if not r:
            md.append(f"| {name} | - | - | - | - | - | - | - | missing | - |")
            continue
        md.append(f"| {name} | {r.get('engine')} | {str(r.get('test262_commit'))[:8]} | {r.get('total')} | {r.get('pass')} | {r.get('assertion_fail')} | "
                  f"{r.get('crash')} | {r.get('timeout')} | {pct(r.get('pass_rate'))} | {sum((r.get('skipped_files') or {}).values())} |")
    bt = load(R, "test262_boa_tester.json")
    if bt and "total" in bt:
        md.append(f"| boa_tester (own runner, own config) | boa {bt.get('boa_tag')} | {str(bt.get('test262_commit'))[:8]} | {bt.get('total')} | {bt.get('passed')} | - | "
                  f"panic {bt.get('panic')} | - | {pct(bt.get('pass_rate_of_run'))} | ignored {bt.get('ignored')} |")
    md.append("")
    q = t262.get("test262_qjs")
    if q and q.get("upstream_expected_failures"):
        u = q["upstream_expected_failures"]
        md += [f"Harness check against QuickJS-NG's own `test262_errors.txt`: {u['failed_here_too']}/{u['listed_and_run']} listed failures reproduced, "
               f"{u['unexpected_failures']} unexpected failures, {u['unexpected_passes']} unexpected passes.", ""]
    b = t262.get("test262_boa")
    if q or b:
        dirs = sorted(set((q or {}).get("by_dir", {})) | set((b or {}).get("by_dir", {})))
        md += ["### Pass rate by feature directory", "", "| directory | rquickjs | boa |", "|---|---:|---:|"]
        for d in dirs:
            qa = (q or {}).get("by_dir", {}).get(d, {})
            ba = (b or {}).get("by_dir", {}).get(d, {})
            md.append(f"| {d} | {pct(qa.get('pass_rate'))} ({qa.get('pass', '-')}/{qa.get('total', '-')}) | {pct(ba.get('pass_rate'))} ({ba.get('pass', '-')}/{ba.get('total', '-')}) |")
        md.append("")
    for name in ("test262_intl402_qjs", "test262_intl402_boa"):
        r = t262.get(name)
        if r:
            md += [f"### {name}: top failure messages", "", "| count | message |", "|---:|---|"]
            for m in r.get("top_failure_messages", [])[:10]:
                md.append(f"| {m['count']} | `{m['msg'][:100]}` |")
            md.append("")

    # 2. libraries
    cmp = load(R, "compare.json")
    if cmp:
        md += ["## 2. Libraries in the embedded runtime", "", "| group | pair | byte-equal | normalized-equal | total |", "|---|---|---:|---:|---:|"]
        for g, v in cmp.get("groups", {}).items():
            for p, x in v["pairs"].items():
                md.append(f"| {g} | {p} | {x['byte_equal']} | {x['normalized_equal']} | {x['total']} |")
        md.append("")
        for g, v in cmp.get("groups", {}).items():
            for p, x in v["pairs"].items():
                if x["mismatches"]:
                    md.append(f"- {g} {p}: " + "; ".join(f"`{m['id']}` {json.dumps(m['detail'])[:160]}" for m in x["mismatches"][:3]))
        md += ["", "### Cost per group (median case ms, process peak RSS)", "", "| engine | group | load ms | case ms median | case ms max | peak RSS MB (group process) | isolated peak RSS MB median / max |",
               "|---|---|---:|---:|---:|---:|---:|"]
        for e, groups in cmp.get("cost", {}).items():
            for g, c in groups.items():
                mx = c.get("process_peak_rss_kb_max")
                md.append(f"| {e} | {g} | {num(c.get('load_ms_median'))} | {num(c.get('case_ms_median'), '{:.1f}')} | {num(c.get('case_ms_max'), '{:.1f}')} | "
                          f"{num(mx / 1024 if mx else None, '{:.1f}')} | {num((c.get('isolated_peak_rss_kb_median') or 0) / 1024 or None, '{:.1f}')} / {num((c.get('isolated_peak_rss_kb_max') or 0) / 1024 or None, '{:.1f}')} |")
        md.append("")

    # 3. shims
    for e in ("qjs", "boa", "node"):
        ab = load(R, f"ablation_{e}.json")
        if not ab:
            continue
        shims = ab["shims"]
        md += [f"## 3. Host-API shims ({e}): needed = disabling it breaks or changes output; (n) = calls", "", "| library | " + " | ".join(shims) + " |", "|---|" + "---|" * len(shims)]
        for g, v in ab["groups"].items():
            cells = []
            for s in shims:
                x = v["ablation"].get(s, {})
                needed = x.get("differs", 0) + x.get("error", 0) > 0
                calls = v["usage_calls"].get(s)
                cells.append(("**needed**" if needed else "-") + (f" ({calls})" if calls else ""))
            md.append(f"| {g} | " + " | ".join(cells) + " |")
        md.append("")

    # 4. sandbox
    if cmp and cmp.get("sandbox"):
        md += ["## 4. Sandbox and limits", ""]
        for e, sb in cmp["sandbox"].items():
            for g, v in sb.items():
                md += [f"### {e} {g}: {v['pass']}/{v['total']} pass", ""]
                if g == "sandbox_limits":
                    md += ["| case | pass | got | expected | wall s | exit/signal/killed |", "|---|---|---|---|---:|---|"]
                    for r in v["rows"]:
                        md.append(f"| {r['id']} | {'yes' if r['pass'] else 'NO'} | {r['got']} | {','.join(r['expect'])} | {r['wall_s']} | {r['exit']}/{r['signal']}/{r['killed']} |")
                else:
                    md += ["| case | pass | result |", "|---|---|---|"]
                    for r in v["rows"]:
                        md.append(f"| {r['id']} | {'yes' if r['pass'] else 'NO'} | `{r['output'][:110]}` |")
                md.append("")

    # 5. determinism
    if cmp and cmp.get("determinism"):
        md += ["## 5. Determinism (3 runs, identical outputs)", "", "| engine | group | identical | total |", "|---|---|---:|---:|"]
        for e, groups in cmp["determinism"].items():
            for g, d in groups.items():
                md.append(f"| {e} | {g} | {d['identical_3_of_3']} | {d['total']} |")
        md.append("")

    # 6. layout
    if cmp and cmp.get("layout_apis"):
        md += ["## 6. Layout APIs without layout (pass 1)", "", "| engine / DOM | API | values returned |", "|---|---|---|"]
        for e, apis in cmp["layout_apis"].items():
            for k, v in apis.items():
                md.append(f"| {e} | {k} | `{'; '.join(v)[:160]}` |")
        md.append("")
    lay = load(R, "layout_qjs.json")
    if lay:
        md += ["### Two-pass prototype (rquickjs + linkedom, stub layout)", "", "| pass | status | script ms | process ms | layout stub ms | measured calls |", "|---:|---|---:|---:|---:|---:|"]
        for p in lay.get("passes", []):
            md.append(f"| {p['pass']} | {p['status']} | {num(p.get('script_ms'), '{:.1f}')} | {num(p.get('process_ms'), '{:.1f}')} | {num(p.get('layout_stub_ms'), '{:.3f}')} | {len(p.get('measured') or [])} |")
        md += ["", f"pass 2 differs from pass 1: {lay.get('pass2_differs_from_pass1')}; stable after pass 2: {lay.get('stable_after_pass2')}", ""]

    # licences
    bundles = load(R, "bundles.json")
    if bundles:
        md += ["## Bundled packages and licences", "", "| package | version | licence |", "|---|---|---|"]
        for p, v in sorted(bundles.get("licenses", {}).items()):
            md.append(f"| {p} | {v.get('version')} | {v.get('license')}{' (not bundled)' if v.get('not_bundled') else ''} |")
        md.append("")
    with open(a.out, "a", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
