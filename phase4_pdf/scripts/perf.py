#!/usr/bin/env python3
"""File size, generation time and peak RSS for 1/10/100-page documents (each run is a fresh `gen single` process)."""
import argparse
import json
import os
import statistics
import subprocess
import tempfile

FIXTURES = ["pages_1", "pages_10", "pages_100", "text", "vector_transparency", "images_opaque"]
PROFILES = ["none", "a2b", "a4", "ua1"]
LIMITS = {"pages_100": {"median_ms": 2000.0, "max_rss_mib": 512.0}}


def run_once(gen, manifest, fixture, profile, out_pdf):
    cmd = ["/usr/bin/time", "-f", "TIME %e %M", gen, "single", "--manifest", manifest, "--fixture", fixture, "--profile", profile, "--out", out_pdf]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    line = [l for l in p.stderr.splitlines() if l.startswith("TIME ")]
    wall, rss = (float(line[-1].split()[1]), int(line[-1].split()[2])) if line else (None, None)
    entry = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {"status": "no output", "stderr": p.stderr[-500:]}
    return entry, wall, rss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--reps", type=int, default=5)
    args = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for fx in FIXTURES:
            for pr in PROFILES:
                ms, walls, rsss, entry = [], [], [], {}
                for i in range(args.reps):
                    entry, wall, rss = run_once(args.gen, args.manifest, fx, pr, os.path.join(td, "o.pdf"))
                    if entry.get("status") != "ok":
                        break
                    ms.append(entry["ms"])
                    walls.append(wall)
                    rsss.append(rss)
                row = {"fixture": fx, "profile": pr, "status": entry.get("status"), "pages": entry.get("pages"),
                       "bytes": entry.get("bytes"), "errors": entry.get("errors")}
                if ms:
                    row.update({
                        "median_ms": statistics.median(ms), "min_ms": min(ms), "max_ms": max(ms),
                        "median_wall_s": statistics.median([w for w in walls if w is not None]) if any(w is not None for w in walls) else None,
                        "max_rss_mib": max(r for r in rsss if r is not None) / 1024.0 if any(r is not None for r in rsss) else None,
                        "bytes_per_page": entry["bytes"] / entry["pages"] if entry.get("pages") else None,
                        "asset_load_ms": entry.get("asset_load_ms"),
                    })
                lim = LIMITS.get(fx)
                if lim and ms:
                    row["pass"] = row["median_ms"] <= lim["median_ms"] and (row["max_rss_mib"] or 0) <= lim["max_rss_mib"]
                    row["limits"] = lim
                rows.append(row)
                print(fx, pr, row.get("status"), row.get("median_ms"), row.get("max_rss_mib"), row.get("bytes"))
    judged = [r for r in rows if "pass" in r]
    passed = sum(r["pass"] for r in judged)
    result = {
        "test": f"perf_{args.label}",
        "pass": passed, "fail": len(judged) - passed, "total": len(judged),
        "pass_rate": passed / len(judged) if judged else None,
        "pass_criterion": "pages_100 (100 A4 pages, ~32 tagged text lines per page, header/footer artifacts): median in-process generation time <= 2000 ms and peak RSS <= 512 MiB, per profile; other rows are informational",
        "reps": args.reps, "rows": rows,
        "first_failures": [r for r in judged if not r["pass"]][:20],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
