#!/usr/bin/env python3
"""Test 6b: the PDF path usvg 0.45.1 -> krilla-svg 0.7.0 -> krilla 0.7.0 -> PDF, rasterised with poppler and compared
with the reference PNGs of resvg's suite at v0.45.1 (the usvg version krilla-svg 0.7.0 uses).

strict : pdftocairo -png -transp at the reference size; resvg v0.45.1's own rule (integration/main.rs:242-247):
         a pixel differs when any RGBA channel differs by more than 1; pass = 0 differing pixels.
relaxed: pdftoppm (Splash) at the reference size, reference composited on white; pass when at most 1% of pixels
         have a channel difference above 16 (anti-aliasing and rasteriser differences tolerated).
"""
import argparse
import concurrent.futures as cf
import os
import re
import struct
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    return struct.unpack(">II", head[16:24])


def rasterise(job):
    pdf, w, h, out_cairo, out_splash = job
    r1 = subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-scale-to-x", str(w), "-scale-to-y", str(h),
                         pdf, out_cairo], capture_output=True, timeout=120)
    r2 = subprocess.run(["pdftoppm", "-png", "-singlefile", "-scale-to-x", str(w), "-scale-to-y", str(h),
                         pdf, out_splash], capture_output=True, timeout=120)
    return r1.returncode, r2.returncode


def compare(ref_path, cairo_png, splash_png):
    from PIL import Image
    ref = np.asarray(Image.open(ref_path).convert("RGBA")).astype(np.int32)
    out = {}
    try:
        cai = np.asarray(Image.open(cairo_png).convert("RGBA")).astype(np.int32)
        if cai.shape != ref.shape:
            out["strict_pixels"] = None
            out["strict_reason"] = f"size {cai.shape} vs {ref.shape}"
        else:
            out["strict_pixels"] = int((np.abs(cai - ref).max(axis=-1) > 1).sum())
    except Exception as e:  # noqa: BLE001
        out["strict_pixels"] = None
        out["strict_reason"] = str(e)[:120]
    try:
        spl = np.asarray(Image.open(splash_png).convert("RGB")).astype(np.float64)
        a = ref[..., 3:4] / 255.0
        refw = ref[..., :3] * a + 255.0 * (1 - a)
        if spl.shape != refw.shape:
            out["relaxed_pct"] = None
        else:
            d = np.abs(spl - refw).max(axis=-1)
            out["relaxed_pct"] = round(100.0 * float((d > 16).mean()), 4)
            out["relaxed_mean_abs"] = round(float(np.abs(spl - refw).mean()), 3)
    except Exception as e:  # noqa: BLE001
        out["relaxed_pct"] = None
        out["relaxed_reason"] = str(e)[:120]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", required=True, help="resvg checkout's crates/resvg/tests directory (v0.45.1)")
    ap.add_argument("--svgpdf", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    work = os.path.abspath(args.work)
    tests = os.path.abspath(args.tests)
    render_rs = open(os.path.join(tests, "integration", "render.rs"), encoding="utf-8").read()
    paths = re.findall(r'render\("tests/([^"]+)"\)', render_rs)
    fonts = os.path.join(tests, "fonts")
    cases, meta = [], {}
    for p in paths:
        svg = os.path.join(tests, p + ".svg")
        ref = os.path.join(tests, p + ".png")
        if not (os.path.exists(svg) and os.path.exists(ref)):
            continue
        w, h = png_size(ref)
        safe = p.replace("/", "__")
        pdf = os.path.join(work, "pdf", safe + ".pdf")
        cases.append({"id": p, "input": svg, "out": pdf, "args": [str(w), str(h), fonts]})
        meta[p] = (ref, pdf, w, h, os.path.join(work, "cairo", safe), os.path.join(work, "splash", safe))
    for d in ("pdf", "cairo", "splash"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    res = common.run_batch(args.svgpdf, "svg", cases, os.path.join(work, "svgpdf_manifest.json"),
                           os.path.join(work, "svgpdf_batch.json"), timeout_ms=60000)
    jobs = [(m[1], m[2], m[3], m[4], m[5]) for p, m in meta.items() if (res.get(p) or {}).get("status") == "ok"]
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        list(ex.map(rasterise, jobs))
    strict, relaxed = [], []
    cat_s, cat_r = {}, {}
    for p, (ref, pdf, w, h, cbase, sbase) in meta.items():
        cat = p.split("/")[0]
        r = res.get(p) or {"status": "missing"}
        if r["status"] != "ok":
            err = f'{r["status"]}: {r.get("message", "")}'
            s_case = {"id": p, "category": cat, "pass": False, "error": err}
            r_case = dict(s_case)
        else:
            c = compare(ref, cbase + ".png", sbase + ".png")
            s_ok = c.get("strict_pixels") == 0
            r_ok = c.get("relaxed_pct") is not None and c["relaxed_pct"] <= 1.0
            s_case = {"id": p, "category": cat, "pass": s_ok, "differing_pixels": c.get("strict_pixels"),
                      **({"reason": c["strict_reason"]} if "strict_reason" in c else {})}
            r_case = {"id": p, "category": cat, "pass": r_ok, "pct_pixels_gt16": c.get("relaxed_pct"),
                      "mean_abs": c.get("relaxed_mean_abs")}
        strict.append(s_case)
        relaxed.append(r_case)
        for coll, case in ((cat_s, s_case), (cat_r, r_case)):
            pc = coll.setdefault(cat, {"pass": 0, "total": 0})
            pc["total"] += 1
            pc["pass"] += int(case["pass"])
    pv = subprocess.run(["pdftocairo", "-v"], capture_output=True, text=True)
    poppler = (pv.stderr or pv.stdout).strip().splitlines()[0] if (pv.stderr or pv.stdout) else "poppler"
    base = {"pipeline": "usvg 0.45.1 -> krilla-svg 0.7.0 (SvgSettings::default) -> krilla 0.7.0", "poppler": poppler,
            "reference": "linebender/resvg v0.45.1 crates/resvg/tests (render.rs list)"}
    common.write_result(os.path.join(args.results, "svg_krilla_pdf_strict.json"), "svg_krilla_pdf_strict",
                        "pdftocairo -transp raster equals the reference PNG under resvg v0.45.1's rule (no pixel with "
                        "any RGBA channel |diff| > 1)", strict, dict(base, per_category=cat_s))
    common.write_result(os.path.join(args.results, "svg_krilla_pdf_relaxed.json"), "svg_krilla_pdf_relaxed",
                        "pdftoppm raster vs reference composited on white: <= 1% of pixels with a channel |diff| > 16",
                        relaxed, dict(base, per_category=cat_r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
