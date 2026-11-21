#!/usr/bin/env python3
"""Byte-identity of two independent corpus generations (separate processes, different TZ/locale/working directory)."""
import argparse
import hashlib
import json
import os


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def first_diff(a, b):
    da, db = open(a, "rb").read(), open(b, "rb").read()
    n = min(len(da), len(db))
    for i in range(n):
        if da[i] != db[i]:
            return {"offset": i, "a": da[max(0, i - 40):i + 40].decode("latin-1"), "b": db[max(0, i - 40):i + 40].decode("latin-1"),
                    "len_a": len(da), "len_b": len(db)}
    return {"offset": n, "len_a": len(da), "len_b": len(db)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    rows = []
    for dirpath, _, files in os.walk(args.a):
        for f in sorted(files):
            if not f.endswith(".pdf"):
                continue
            pa = os.path.join(dirpath, f)
            rel = os.path.relpath(pa, args.a)
            pb = os.path.join(args.b, rel)
            if not os.path.exists(pb):
                rows.append({"file": rel, "identical": False, "detail": "missing in second run"})
                continue
            ha, hb = sha(pa), sha(pb)
            row = {"file": rel, "identical": ha == hb, "sha256": ha}
            if ha != hb:
                row["detail"] = first_diff(pa, pb)
            rows.append(row)
    rows.sort(key=lambda r: r["file"])
    passed = sum(r["identical"] for r in rows)
    result = {
        "test": f"determinism_{args.label}",
        "pass": passed, "fail": len(rows) - passed, "total": len(rows),
        "pass_rate": passed / len(rows) if rows else None,
        "pass_criterion": "every PDF of the corpus is byte-identical between two generator processes run with different TZ, LC_ALL and working directory (metadata dates are fixed by the generator; krilla reads no clock)",
        "first_failures": [r for r in rows if not r["identical"]][:20],
        "rows": rows,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(f"determinism: {passed}/{len(rows)} identical")


if __name__ == "__main__":
    main()
