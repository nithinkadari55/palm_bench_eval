#!/usr/bin/env python3
"""Runs every `robust` case in its own process under a memory limit and timeout and classifies the outcome."""
import argparse
import json
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robust", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--mem-kb", type=int, default=8_000_000)
    args = ap.parse_args()
    listing = json.loads(subprocess.run([args.robust, "list"], capture_output=True, text=True, check=True).stdout)
    rows = []
    for c in listing["cases"]:
        cmd = f'ulimit -v {args.mem_kb}; exec "{args.robust}" case "{c["name"]}" --manifest "{args.manifest}"'
        row = {"case": c["name"], "note": c["note"], "documented_panic": c["documented_panic"]}
        try:
            p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=args.timeout)
            out = p.stdout.strip().splitlines()
            js = None
            if out:
                try:
                    js = json.loads(out[-1])
                except json.JSONDecodeError:
                    js = None
            if p.returncode == 0 and js:
                row.update({"outcome": js["outcome"], "detail": js["detail"][:400], "ms": round(js["ms"], 1)})
            elif "panicked" in p.stderr:
                msg = [l for l in p.stderr.splitlines() if "panicked" in l or l.startswith("  ")]
                row.update({"outcome": "panic", "detail": " ".join(p.stderr.split("\n")[0:3])[:400], "rc": p.returncode})
            elif p.returncode < 0 or p.returncode > 128:
                row.update({"outcome": "signal", "detail": f"rc={p.returncode} {p.stderr[-300:]}", "rc": p.returncode})
            else:
                row.update({"outcome": "crash", "detail": f"rc={p.returncode} {p.stderr[-300:]}", "rc": p.returncode})
        except subprocess.TimeoutExpired:
            row.update({"outcome": "timeout", "detail": f"> {args.timeout} s"})
        row["pass"] = row["outcome"] in ("ok", "err")
        rows.append(row)
        print(f"{c['name']:<36} {row['outcome']:<8} {row.get('detail', '')[:100]}")
    passed = sum(r["pass"] for r in rows)
    result = {
        "test": f"robustness_{args.label}",
        "krilla_version": listing.get("krilla_version"),
        "pass": passed, "fail": len(rows) - passed, "total": len(rows),
        "pass_rate": passed / len(rows) if rows else None,
        "pass_criterion": f"the case returns Ok or Err; a panic, abort/signal (including the {args.mem_kb // 1000} MB ulimit -v), crash or a hang over {args.timeout} s fails. documented_panic marks API-misuse cases whose panic krilla documents",
        "undocumented_failures": [r["case"] for r in rows if not r["pass"] and not r["documented_panic"]],
        "rows": rows,
        "first_failures": [r for r in rows if not r["pass"]][:20],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
