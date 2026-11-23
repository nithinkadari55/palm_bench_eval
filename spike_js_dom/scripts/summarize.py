"""Builds the spike summary (markdown + JSON) from the per-engine results.

usage: python summarize.py --results <dir with results_*.json, build_*.json, api_usage.json>
           --out-md <summary.md> --out-json <summary.json>
"""
import argparse
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SPIKE = os.path.dirname(HERE)

LOC_FILES = {
    "rquickjs natives (spike-rkjs/src/dom.rs)": "crates/spike-rkjs/src/dom.rs",
    "JS DOM facade (spike-rkjs/src/prelude.js)": "crates/spike-rkjs/src/prelude.js",
    "script runner + event loop host (spike-rkjs/src/main.rs)": "crates/spike-rkjs/src/main.rs",
    "relayout + PDF pipeline, shared (spike-common/pipeline.rs)": "crates/spike-common/pipeline.rs",
    "Boa DocumentHost driver (spike-rkboa/src/main.rs)": "crates/spike-rkboa/src/main.rs",
}


def loc(path):
    total = code = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            total += 1
            s = line.strip()
            if s and not s.startswith("//"):
                code += 1
    return total, code


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def fmt(v, nd=1):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    a = ap.parse_args()
    engines = {}
    for p in sorted(glob.glob(os.path.join(a.results, "results_*.json"))):
        r = load(p)
        if r:
            engines[r["engine"]] = r
    builds = {}
    for p in sorted(glob.glob(os.path.join(a.results, "build_*.json"))):
        b = load(p)
        if b:
            builds[b["crate"]] = b
    usage = load(os.path.join(a.results, "api_usage.json"))
    locs = {k: loc(os.path.join(SPIKE, v)) for k, v in LOC_FILES.items() if os.path.exists(os.path.join(SPIKE, v))}

    md = ["# spike-js-dom: rquickjs <-> raikiri DOM binding", ""]
    md.append("## Build")
    md.append("| crate | status | seconds | binary MB |")
    md.append("|---|---|---|---|")
    for crate, b in builds.items():
        md.append(f"| {crate} | {b.get('status')} | {b.get('build_s')} | {b.get('binary_mb')} |")
    md.append("")

    keys = []
    for r in engines.values():
        for c in r["cases"]:
            k = (c["group"], c["case"])
            if k not in keys:
                keys.append(k)
    names = list(engines)
    md.append("## Pass/fail per case")
    md.append("| group | case | " + " | ".join(names) + " |")
    md.append("|---|---|" + "---|" * len(names))
    for k in keys:
        row = []
        for n in names:
            c = next((c for c in engines[n]["cases"] if (c["group"], c["case"]) == k), None)
            if c is None:
                row.append("-")
                continue
            checks = c.get("checks", [])
            req = [x for x in checks if x["required"]]
            row.append(f"{'PASS' if c.get('pass') else 'FAIL'} {sum(x['ok'] for x in req)}/{len(req)}"
                       + ("" if c.get("status") == "OK" else f" ({c.get('status')})"))
        md.append(f"| {k[0]} | {k[1]} | " + " | ".join(row) + " |")
    md.append("")
    md.append("Totals: " + ", ".join(
        f"{n} {sum(1 for c in engines[n]['cases'] if c.get('pass'))}/{len(engines[n]['cases'])}" for n in names))
    md.append("")

    md.append("## Time and memory per case")
    md.append("| engine | case | JS ms (incl. relayout) | relayouts | relayout ms total | final render ms | final layout ms | total ms | peak RSS MB | QuickJS malloc MB |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for n in names:
        for c in engines[n]["cases"]:
            m = c.get("metrics", {}) or {}
            qjs = m.get("qjs_malloc_size")
            md.append(f"| {n} | {c['case']} | {fmt(m.get('js_ms'))} | {fmt(m.get('relayout_count'))} | {fmt(m.get('relayout_ms_total'))} | "
                      f"{fmt(m.get('render_ms'))} | {fmt(m.get('final_layout_ms'))} | {fmt(m.get('total_ms'))} | "
                      f"{fmt(c.get('peak_rss_mb'))} | {fmt(qjs / 1048576 if qjs else None)} |")
    md.append("")

    md.append("## Failed checks")
    any_fail = False
    for n in names:
        for c in engines[n]["cases"]:
            for x in c.get("checks", []):
                if not x["ok"]:
                    any_fail = True
                    md.append(f"- {n} {c['case']}: {'FAIL' if x['required'] else 'info'} {x['desc']} -- {x['detail']}")
    if not any_fail:
        md.append("- none")
    md.append("")

    md.append("## Prototype binding size (lines / code lines)")
    md.append("| part | lines | code lines |")
    md.append("|---|---|---|")
    for k, (t, c) in locs.items():
        md.append(f"| {k} | {t} | {c} |")
    md.append("")

    if usage:
        md.append("## DOM API usage in LLM-written HTML (document frequency)")
        w = usage.get("websight", {})
        p5 = usage.get("phase5_dom_cases", {})
        md.append(f"WebSight sample: {w.get('docs')} docs, {w.get('docs_with_inline_js')} with inline JS. Phase 5 DOM cases: {p5.get('docs')} scripts.")
        md.append("")
        md.append("| API | phase 5 cases | WebSight | spike prelude | raikiri-js |")
        md.append("|---|---|---|---|---|")
        for api in usage.get("apis", []):
            n5 = p5.get("api_doc_freq", {}).get(api["api"], 0)
            nw = w.get("api_doc_freq", {}).get(api["api"], 0)
            if n5 or nw:
                md.append(f"| {api['api']} | {n5} | {nw} | {'yes' if api['spike_prelude'] else 'no'} | {'yes' if api['raikiri_js'] else 'no'} |")
        md.append("")

    text = "\n".join(md) + "\n"
    with open(a.out_md, "w", encoding="utf-8") as f:
        f.write(text)
    with open(a.out_json, "w", encoding="utf-8") as f:
        json.dump({"builds": builds, "engines": engines, "loc": {k: {"lines": t, "code": c} for k, (t, c) in locs.items()},
                   "api_usage": usage}, f, indent=1)
    print(text)


if __name__ == "__main__":
    main()
