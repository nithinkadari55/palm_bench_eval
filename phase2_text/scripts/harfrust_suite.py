#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import time

RESULT_RE = re.compile(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out")
FAILED_RE = re.compile(r"^test (\S+) \.\.\. FAILED", re.M)
RUNNING_RE = re.compile(r"^\s*Running (?:unittests )?(\S+)", re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()
    cmd = ["cargo", "test", "--no-fail-fast"]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=args.repo, capture_output=True, text=True)
    elapsed = time.time() - t0
    log = p.stdout + "\n" + p.stderr
    with open(args.log, "w", encoding="utf-8") as fh:
        fh.write(log)
    passed = failed = ignored = 0
    suites = []
    for m in RESULT_RE.finditer(log):
        passed += int(m.group(2))
        failed += int(m.group(3))
        ignored += int(m.group(4))
        suites.append({"status": m.group(1), "passed": int(m.group(2)), "failed": int(m.group(3)), "ignored": int(m.group(4))})
    names = RUNNING_RE.findall(p.stderr)
    for i, s in enumerate(suites):
        if i < len(names):
            s["binary"] = names[i]
    failures = FAILED_RE.findall(log)
    build_failed = p.returncode != 0 and not suites
    result = {
        "test": "harfrust_suite",
        "harfrust_tag": args.tag,
        "harfrust_sha": args.sha,
        "command": " ".join(cmd),
        "exit_code": p.returncode,
        "build_failed": build_failed,
        "pass": passed,
        "fail": failed,
        "ignored": ignored,
        "total": passed + failed,
        "pass_rate": passed / (passed + failed) if passed + failed else 0.0,
        "pass_criterion": "every non-ignored test in the upstream workspace passes under `cargo test --no-fail-fast`",
        "suites": suites,
        "elapsed_s": elapsed,
        "first_failures": failures[:20] if failures else ([log[-3000:]] if build_failed else []),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    print(f"harfrust suite: passed={passed} failed={failed} ignored={ignored} exit={p.returncode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
