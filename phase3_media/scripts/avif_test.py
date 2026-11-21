#!/usr/bin/env python3
"""Test 1 (AVIF): compare AVIF decoder candidates with avifdec (libavif reference CLI)."""
import argparse
import glob
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

CANDIDATES = {
    "avif_native": {"crate": "image 0.25.10 feature avif-native (mp4parse 0.17 + dav1d 0.11 -> system libdav1d)",
                    "licence": "image: MIT OR Apache-2.0; mp4parse: MPL-2.0; dav1d crate: MIT; libdav1d (C): BSD-2-Clause",
                    "pure_rust": False},
    "avif_pure": {"crate": "avif-decode 3.0.0 (avif-parse 2.1.0 + rav1d 1.1.0)",
                  "licence": "avif-decode: BSD-3-Clause; avif-parse: MPL-2.0; rav1d: BSD-2-Clause (x86 asm needs nasm at build time)",
                  "pure_rust": True},
    "avif_zen": {"crate": "zenavif 0.1.6 (rav1d-safe + zenavif-parse)",
                 "licence": "AGPL-3.0-only OR LicenseRef-Imazen-Commercial (not usable closed-source without a commercial licence)",
                 "pure_rust": True},
}

CRIT = "decodes, same size as avifdec, mean |diff| <= 1.0 and <= 1% of pixels with any channel |diff| > 3 (8-bit scale)"


def tags_for(path):
    n = os.path.basename(path).lower()
    p = path.replace("\\", "/").lower()
    t = []
    m = re.search(r"(8|10|12)bpc", n)
    if m:
        t.append(m.group(1) + "bit")
    elif "10bit" in n or "cicp9-16" in n:
        t.append("10bit")
    if "alpha" in n:
        t.append("alpha")
    if "monochrome" in n:
        t.append("monochrome")
    if "grid" in n:
        t.append("grid")
    if "cicp9-16" in n or "hdr" in n:
        t.append("hdr_pq")
    if n.endswith(".avifs") or "/avis/" in p:
        t.append("animated")
    if "multilayer" in n or "layer" in n:
        t.append("multilayer")
    if "odd-" in n:
        t.append("odd_size")
    if "rotate" in n or "mirror" in n or "crop" in n or "clap" in n:
        t.append("transform")
    for y in ("yuv420", "yuv422", "yuv444"):
        if y in n:
            t.append(y)
    if "lossless" in n:
        t.append("lossless")
    if "non_compliant" in p or "truncated" in n:
        t.append("non_compliant")
    return t or ["other"]


def corpus(data):
    files = sorted(glob.glob(os.path.join(data, "avif-link-u", "*.avif")) +
                   glob.glob(os.path.join(data, "avif-link-u", "*.avifs")))
    files += sorted(glob.glob(os.path.join(data, "av1-avif", "testFiles", "**", "*.avif"), recursive=True))
    return files


def oracle(path, ref_png):
    r = subprocess.run(["avifdec", "-d", "8", path, ref_png], capture_output=True, timeout=300)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).decode(errors="replace")[-300:]
    from PIL import Image
    im = Image.open(ref_png)
    return common.to_unit(np.asarray(im.convert("RGBA")))[None], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--candidate", action="append", default=[], help="name=path-to-binary (missing file = build failed)")
    ap.add_argument("--build", action="append", default=[], help="name=step-outcome")
    args = ap.parse_args()
    work = os.path.abspath(args.work)
    os.makedirs(os.path.join(work, "ref"), exist_ok=True)
    files = corpus(args.data)
    ids = {}
    for f in files:
        rel = os.path.relpath(f, args.data).replace(os.sep, "/")
        ids[rel] = f
    refs, ref_err = {}, {}
    for rel, f in ids.items():
        png = os.path.join(work, "ref", re.sub(r"[^A-Za-z0-9._-]", "_", rel) + ".png")
        try:
            a, e = oracle(f, png)
        except subprocess.TimeoutExpired:
            a, e = None, "avifdec timeout"
        if a is None:
            ref_err[rel] = e
        else:
            refs[rel] = a
    av = subprocess.run(["avifdec", "--version"], capture_output=True, text=True)
    builds = dict(b.split("=", 1) for b in args.build)
    summary = {"oracle": "avifdec " + " ".join((av.stdout or av.stderr).split())[:300], "candidates": {}}
    for spec in args.candidate:
        name, binp = spec.split("=", 1)
        info = dict(CANDIDATES.get(name, {}))
        info["build"] = builds.get(name, "unknown")
        if not os.path.exists(binp):
            info["status"] = "not built"
            summary["candidates"][name] = info
            continue
        cases = []
        for rel, f in ids.items():
            out = os.path.join(work, name, re.sub(r"[^A-Za-z0-9._-]", "_", rel) + ".raw")
            cases.append({"id": rel, "input": f, "out": out, "args": []})
        os.makedirs(os.path.join(work, name), exist_ok=True)
        res = common.run_batch(binp, "decode", cases, os.path.join(work, name + "_manifest.json"),
                               os.path.join(work, name + "_batch.json"), timeout_ms=120000)
        results, per_tag, no_oracle, safety = [], {}, [], {}
        for c in cases:
            rel = c["id"]
            r = res.get(rel) or {"status": "missing"}
            st = r["status"]
            if st not in ("ok", "err"):
                safety[st] = safety.get(st, 0) + 1
            tags = tags_for(rel)
            if rel not in refs:
                no_oracle.append({"id": rel, "avifdec": ref_err.get(rel), "candidate": st, "message": r.get("message", "")})
                continue
            if st != "ok":
                case = {"id": rel, "pass": False, "tags": tags, "error": f"{st}: {r.get('message', '')}"}
            else:
                got = common.to_unit(common.read_raw(c["out"]))[:1]
                exp = refs[rel]
                if got.shape != exp.shape:
                    case = {"id": rel, "pass": False, "tags": tags, "reason": "shape", "got": list(got.shape),
                            "expected": list(exp.shape)}
                else:
                    s = common.diff_stats(got, exp)
                    case = {"id": rel, "pass": s["mean_abs"] <= 1.0 and s["pct_gt3"] <= 1.0, "tags": tags, **s}
            results.append(case)
            for t in tags:
                pt = per_tag.setdefault(t, {"pass": 0, "total": 0})
                pt["total"] += 1
                pt["pass"] += int(case["pass"])
        doc = common.write_result(os.path.join(args.results, f"avif_{name}.json"), f"avif_{name}", CRIT, results,
                                  {"candidate": info, "per_tag": per_tag, "no_oracle": no_oracle,
                                   "safety_failures": safety, "oracle": summary["oracle"]})
        info.update({"status": "ran", "pass": doc["pass"], "total": doc["total"], "pass_rate": doc["pass_rate"],
                     "safety_failures": safety})
        summary["candidates"][name] = info
    summary["corpus_files"] = len(ids)
    summary["avifdec_rejected"] = ref_err
    with open(os.path.join(args.results, "avif_candidates.json"), "w", encoding="utf-8") as fh:
        import json
        json.dump(summary, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
