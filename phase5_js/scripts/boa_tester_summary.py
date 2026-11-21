#!/usr/bin/env python3
"""Reduces boa_tester's latest.json (keys: c, u, r={n, a={t,o,i,p}, s=[suites]}) to a
pass-rate table by suite directory (two levels below test/)."""
import argparse
import glob
import json
import os
import sys


def walk(suite, prefix, depth, out):
    name = suite.get("n", "")
    path = f"{prefix}/{name}" if prefix else name
    a = suite.get("a", {})
    if depth <= 2:
        out[path] = {"total": a.get("t", 0), "passed": a.get("o", 0), "ignored": a.get("i", 0), "panic": a.get("p", 0)}
    for s in suite.get("s", []) or []:
        walk(s, path, depth + 1, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boa-tag", default="")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, "**", "latest.json"), recursive=True))
    if not files:
        json.dump({"error": "latest.json not found"}, open(a.out, "w"))
        return 1
    d = json.load(open(files[0], encoding="utf-8"))
    r = d.get("r", {})
    stats = r.get("a", {})
    by = {}
    for s in r.get("s", []) or []:
        walk(s, "", 1, by)
    run = stats.get("t", 0) - stats.get("i", 0)
    out = {
        "tool": "boa_tester", "boa_tag": a.boa_tag, "test262_commit": d.get("u"),
        "total": stats.get("t"), "passed": stats.get("o"), "ignored": stats.get("i"), "panic": stats.get("p"),
        "pass_rate_of_run": (stats.get("o", 0) / run) if run else None,
        "pass_criterion": "boa_tester's own: a test passes when every applicable mode passes; ignored = Boa's test262_config.toml",
        "by_suite": {k: dict(v, pass_rate=(v["passed"] / (v["total"] - v["ignored"]) if v["total"] - v["ignored"] > 0 else None)) for k, v in by.items()},
        "source_file": os.path.relpath(files[0], a.dir),
    }
    json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: out[k] for k in ("total", "passed", "ignored", "panic", "pass_rate_of_run")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
