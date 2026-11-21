#!/usr/bin/env python3
"""Shim ablation: for every library group, run once with all shims (baseline) and once per
shim with that shim disabled. A shim is "needed" by a library when disabling it makes a
case fail or changes its output. Usage counts come from the baseline (__p5.usage)."""
import argparse
import json
import os
import subprocess
import sys

SHIMS = ["timers", "requestAnimationFrame", "queueMicrotask", "console", "atob_btoa", "TextEncoder_Decoder",
         "URL", "structuredClone", "performance_now", "Math_random", "Date", "Intl"]


def run(a, group, shim_config, tag):
    out = os.path.join(a.work, f"abl_{a.engine}_{group}_{tag}.json")
    if a.engine in ("qjs", "boa"):
        cmd = [a.bin, "cases", "--cases", os.path.join(a.dist, "cases", group + ".json"), "--dist", a.dist, "--out", out]
    else:
        cmd = ["node", os.path.join(a.js, "node_runner.mjs"), "--cases", os.path.join(a.dist, "cases", group + ".json"), "--dist", a.dist, "--out", out]
    cmd += ["--shim-config", json.dumps(shim_config)]
    try:
        subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=a.timeout_s)
    except subprocess.TimeoutExpired:
        return {"process_error": "timeout"}
    try:
        return json.load(open(out, encoding="utf-8"))
    except Exception as e:
        return {"process_error": repr(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["qjs", "boa", "node"])
    ap.add_argument("--bin", default="")
    ap.add_argument("--js", default="phase5_js/js")
    ap.add_argument("--dist", default="phase5_js/js/dist")
    ap.add_argument("--groups", default="echarts,mathjax,chartjs,d3,dom")
    ap.add_argument("--timeout-s", type=float, default=900)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    res = {"engine": a.engine, "shims": SHIMS, "groups": {}}
    for g in a.groups.split(","):
        base = run(a, g, {}, "baseline")
        bcases = {c["id"]: c for c in base.get("cases", [])}
        usage = {}
        for c in bcases.values():
            for k, v in (c.get("usage") or {}).items():
                usage[k] = usage.get(k, 0) + v
        entry = {"baseline_done": sum(1 for c in bcases.values() if c.get("status") == "done"), "cases": len(bcases),
                 "environment": base.get("environment"), "usage_calls": usage, "ablation": {}, "needed": [], "used": sorted(usage)}
        for shim in SHIMS:
            r = run(a, g, {"disable": [shim]}, "no_" + shim)
            same = differs = error = 0
            first = None
            for c in r.get("cases", []):
                b = bcases.get(c["id"], {})
                if c.get("status") != "done":
                    error += 1
                    first = first or f"{c['id']}: {(c.get('error') or '')[:200]}"
                elif c.get("output") == b.get("output"):
                    same += 1
                else:
                    differs += 1
                    first = first or f"{c['id']}: output differs"
            if r.get("process_error") or r.get("fatal"):
                first = r.get("process_error") or r.get("fatal")
                error = max(error, 1)
            entry["ablation"][shim] = {"same": same, "differs": differs, "error": error, "first": first}
            if differs or error:
                entry["needed"].append(shim)
            print(f"{a.engine} {g} -{shim}: same={same} differs={differs} error={error}", flush=True)
        res["groups"][g] = entry
    json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
