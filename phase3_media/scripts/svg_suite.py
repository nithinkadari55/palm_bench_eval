#!/usr/bin/env python3
"""Test 6a: resvg's own integration suite at a pinned tag, with the repository's own comparison rule.

Runs `cargo test --release --locked -p resvg --test integration --no-fail-fast` in a checkout of linebender/resvg and
maps every generated test (crates/resvg/tests/integration/render.rs) back to its SVG path and top-level category.
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

RULES = {
    "v0.45.1": "integration/main.rs:73-89,242-247: un-premultiply the tiny-skia pixmap, then a pixel differs when any "
               "RGBA channel differs by more than 1 from the reference PNG; a test passes with 0 differing pixels",
    "v0.48.1": "integration/main.rs:136,151-226: DIFF_THRESHOLD = 1 per RGBA channel after un-premultiplying; pixels "
               "transparent in both images are ignored, pixels outside either image count as different; 0 differing "
               "pixels passes",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()
    head = subprocess.run(["git", "-C", args.repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != args.sha:
        raise SystemExit(f"resvg HEAD {head} != {args.sha}")
    render_rs = open(os.path.join(args.repo, "crates", "resvg", "tests", "integration", "render.rs"), encoding="utf-8").read()
    name_to_path = dict(re.findall(r'fn (\w+)\(\) \{ assert_eq!\(render\("tests/([^"]+)"\), 0\); \}', render_rs))
    cmd = ["cargo", "test", "--release", "--locked", "-p", "resvg", "--test", "integration", "--no-fail-fast"]
    p = subprocess.run(cmd, cwd=args.repo, capture_output=True, text=True)
    log = p.stdout + "\n----- stderr -----\n" + p.stderr
    with open(args.log, "w", encoding="utf-8") as fh:
        fh.write(log)
    status = {}
    for m in re.finditer(r"^test (\S+) \.\.\. (ok|FAILED|ignored)", p.stdout, re.M):
        status[m.group(1)] = m.group(2)
    diffs = {}
    for m in re.finditer(r"^---- (\S+) stdout ----\n(.*?)(?=^---- |\Z|^failures:)", p.stdout, re.M | re.S):
        lm = re.search(r"left: (\d+)", m.group(2))
        diffs[m.group(1)] = int(lm.group(1)) if lm else m.group(2).strip()[:300]
    cases, per_cat, ignored = [], {}, []
    for full, st in sorted(status.items()):
        mod, _, fn = full.rpartition("::")
        if st == "ignored":
            ignored.append(full)
            continue
        path = name_to_path.get(fn)
        cat = path.split("/")[0] if (mod.endswith("render") and path) else ("extra" if "extra" in mod else "other")
        case = {"id": path or full, "category": cat, "pass": st == "ok"}
        if st != "ok":
            case["differing_pixels_or_panic"] = diffs.get(full)
        cases.append(case)
        pc = per_cat.setdefault(cat, {"pass": 0, "total": 0})
        pc["total"] += 1
        pc["pass"] += int(st == "ok")
    extra = {"tag": args.tag, "sha": args.sha, "per_category": per_cat, "ignored": ignored,
             "generated_tests_in_render_rs": len(name_to_path), "cargo_exit_code": p.returncode,
             "command": " ".join(cmd)}
    if not cases:
        extra["error"] = "no test results parsed (build failure?); see log"
    common.write_result(args.out, f"svg_resvg_{args.tag.lstrip('v')}", RULES.get(args.tag, "resvg integration suite"),
                        cases, extra)
    return 0


if __name__ == "__main__":
    sys.exit(main())
