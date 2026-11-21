#!/usr/bin/env python3
"""Rasterise fixtures with poppler, MuPDF, PDFium and PDF.js and flag pages where a viewer disagrees with the others.

krilla has no rasteriser of its own, so the reference is the per-pixel median of all viewers that rendered the
page (the consensus). Each viewer is compared with the consensus and pairwise with every other viewer.
"""
import argparse
import glob
import importlib.metadata
import json
import os
import re
import shutil
import subprocess

import numpy as np
import pypdfium2 as pdfium
from PIL import Image

RENDERERS = ["poppler", "mupdf", "pdfium", "pdfjs"]


def render_poppler(pdf, out, dpi, n):
    os.makedirs(out, exist_ok=True)
    prefix = os.path.join(out, "p")
    p = subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-f", "1", "-l", str(n), pdf, prefix],
                       capture_output=True, text=True, timeout=600)
    files = {}
    for f in glob.glob(prefix + "-*.png"):
        m = re.search(r"-(\d+)\.png$", f)
        files[int(m.group(1))] = f
    return files, (p.stderr.strip()[-500:] if p.returncode else None)


def render_mupdf(pdf, out, dpi, n):
    os.makedirs(out, exist_ok=True)
    p = subprocess.run(["mutool", "draw", "-q", "-r", str(dpi), "-o", os.path.join(out, "p-%d.png"), pdf, f"1-{n}"],
                       capture_output=True, text=True, timeout=600)
    files = {int(re.search(r"-(\d+)\.png$", f).group(1)): f for f in glob.glob(os.path.join(out, "p-*.png"))}
    return files, (p.stderr.strip()[-500:] if p.returncode else None)


def render_pdfium(pdf, out, dpi, n):
    os.makedirs(out, exist_ok=True)
    files, err = {}, None
    try:
        doc = pdfium.PdfDocument(pdf)
        for i in range(min(n, len(doc))):
            img = doc[i].render(scale=dpi / 72.0).to_pil().convert("RGB")
            f = os.path.join(out, f"p-{i + 1}.png")
            img.save(f)
            files[i + 1] = f
        doc.close()
    except Exception as e:
        err = repr(e)[:500]
    return files, err


def render_pdfjs_batch(pdfs, out, dpi, n, js_dir):
    os.makedirs(out, exist_ok=True)
    p = subprocess.run(["node", os.path.join(js_dir, "render.mjs"), out, str(dpi / 72.0), str(n)] + pdfs,
                       capture_output=True, text=True, timeout=7200)
    st_path = os.path.join(out, "status.json")
    status = json.load(open(st_path, encoding="utf-8")) if os.path.exists(st_path) else {"files": {}}
    res = {}
    for idx, pdf in enumerate(pdfs):
        files = {}
        for f in glob.glob(os.path.join(out, f"{idx}-p*.png")):
            files[int(re.search(r"-p(\d+)\.png$", f).group(1))] = f
        st = status["files"].get(pdf, {})
        errs = st.get("errors") or ([] if files else [p.stderr[-500:] or "no output"])
        res[pdf] = (files, "; ".join(errs)[:500] if errs else None)
    return res, status.get("pdfjs_version")


def safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        return {}, repr(e)[:500]


def load(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)


def box3(a):
    p = np.pad(a, 1, mode="edge").astype(np.float32)
    s = sum(p[dy:dy + a.shape[0], dx:dx + a.shape[1]] for dy in range(3) for dx in range(3))
    return s / 9.0


def diff_metrics(a, b, threshold):
    d = np.abs(a - b).max(axis=2).astype(np.float32)
    db = box3(d)
    return {"mean_abs": float(d.mean() / 255.0), "frac_over": float((db > threshold).mean())}, db


def save_failure(out_dir, tag, img, ref, db):
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray(img.astype(np.uint8)).save(os.path.join(out_dir, f"{tag}_viewer.png"))
    Image.fromarray(ref.astype(np.uint8)).save(os.path.join(out_dir, f"{tag}_consensus.png"))
    heat = np.clip(db * 3, 0, 255).astype(np.uint8)
    Image.fromarray(np.stack([heat, np.zeros_like(heat), np.zeros_like(heat)], axis=2)).save(os.path.join(out_dir, f"{tag}_diff.png"))


def version(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return ((p.stdout or "") + (p.stderr or "")).strip().splitlines()[0]
    except Exception as e:
        return repr(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--js", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--failures", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--profiles", default="none,pdf20,a1b,a2b,a4,ua1")
    ap.add_argument("--dpi", type=int, default=96)
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=48.0, help="per-pixel channel difference (0-255) after a 3x3 box blur")
    ap.add_argument("--max-frac", type=float, default=0.01, help="fraction of pixels allowed over the threshold")
    ap.add_argument("--max-saved", type=int, default=80)
    args = ap.parse_args()
    gen = json.load(open(os.path.join(args.corpus, "generation.json"), encoding="utf-8"))
    profiles = set(args.profiles.split(","))
    items = [e for e in gen["entries"] if e["status"] == "ok" and e["profile"] in profiles]
    pdfs = [os.path.abspath(os.path.join(args.corpus, e["file"])) for e in items]
    shutil.rmtree(args.work, ignore_errors=True)
    try:
        pdfjs_res, pdfjs_ver = render_pdfjs_batch(pdfs, os.path.join(args.work, "pdfjs"), args.dpi, args.max_pages, args.js)
    except Exception as e:
        pdfjs_res, pdfjs_ver = {p: ({}, repr(e)[:500]) for p in pdfs}, None

    rows, saved, pair_tot = [], 0, {}
    for e, pdf in zip(items, pdfs):
        n = min(args.max_pages, int(e.get("pages") or args.max_pages))
        key = f"{e['fixture']}/{e['profile']}"
        base = os.path.join(args.work, e["fixture"], e["profile"].replace("+", "_"))
        rendered = {
            "poppler": safe(render_poppler, pdf, os.path.join(base, "poppler"), args.dpi, n),
            "mupdf": safe(render_mupdf, pdf, os.path.join(base, "mupdf"), args.dpi, n),
            "pdfium": safe(render_pdfium, pdf, os.path.join(base, "pdfium"), args.dpi, n),
            "pdfjs": pdfjs_res.get(pdf, ({}, "missing")),
        }
        for page in range(1, n + 1):
            imgs, errs = {}, {}
            for r in RENDERERS:
                files, err = rendered[r]
                if page in files:
                    try:
                        imgs[r] = load(files[page])
                    except Exception as ex:
                        errs[r] = repr(ex)
                else:
                    errs[r] = err or "page not rendered"
            if imgs:
                h = min(i.shape[0] for i in imgs.values())
                w = min(i.shape[1] for i in imgs.values())
                sizes = {r: list(i.shape[:2]) for r, i in imgs.items()}
                imgs = {r: i[:h, :w] for r, i in imgs.items()}
                stack = np.stack(list(imgs.values()))
                ref = np.median(stack, axis=0)
            for r in RENDERERS:
                row = {"fixture": e["fixture"], "profile": e["profile"], "page": page, "renderer": r}
                if r in errs:
                    row.update({"status": "render_error", "error": errs[r][:300]})
                elif len(imgs) < 2:
                    row.update({"status": "no_peer"})
                else:
                    m, db = diff_metrics(imgs[r], ref, args.threshold)
                    row.update(m)
                    row["size_px"] = sizes[r]
                    bad = m["frac_over"] > args.max_frac
                    row["status"] = "disagree" if bad else "agree"
                    if bad and saved < args.max_saved:
                        save_failure(os.path.join(args.failures, e["fixture"], e["profile"].replace("+", "_")), f"p{page}_{r}", imgs[r], ref, db)
                        row["saved"] = True
                        saved += 1
                rows.append(row)
            names = sorted(imgs)
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    m, _ = diff_metrics(imgs[names[i]], imgs[names[j]], args.threshold)
                    k = f"{names[i]}~{names[j]}"
                    t = pair_tot.setdefault(k, {"pages": 0, "disagree": 0, "mean_frac_over": 0.0})
                    t["pages"] += 1
                    t["disagree"] += m["frac_over"] > args.max_frac
                    t["mean_frac_over"] += m["frac_over"]
    for t in pair_tot.values():
        t["mean_frac_over"] = t["mean_frac_over"] / t["pages"] if t["pages"] else None

    per_renderer = {}
    for r in rows:
        a = per_renderer.setdefault(r["renderer"], {"pages": 0, "agree": 0, "disagree": 0, "render_error": 0, "no_peer": 0})
        a["pages"] += 1
        a[r["status"]] += 1
    per_fixture = {}
    for r in rows:
        a = per_fixture.setdefault(r["fixture"], {})
        b = a.setdefault(r["renderer"], {"agree": 0, "total": 0})
        b["total"] += 1
        b["agree"] += r["status"] == "agree"
    judged = [r for r in rows if r["status"] != "no_peer"]
    passed = sum(r["status"] == "agree" for r in judged)
    result = {
        "test": f"render_{args.label}",
        "tools": {"poppler": version(["pdftoppm", "-v"]), "mupdf": version(["mutool", "-v"]),
                  "pypdfium2": importlib.metadata.version("pypdfium2"),
                  "pdfium": str(getattr(pdfium, "PDFIUM_INFO", getattr(pdfium, "V_LIBPDFIUM", None))), "pdfjs-dist": pdfjs_ver},
        "settings": {"dpi": args.dpi, "max_pages": args.max_pages, "threshold": args.threshold, "max_frac": args.max_frac, "profiles": sorted(profiles)},
        "pass": passed, "fail": len(judged) - passed, "total": len(judged),
        "pass_rate": passed / len(judged) if judged else None,
        "pass_criterion": f"each viewer's page raster differs from the per-pixel median of all viewers by more than {args.threshold:.0f}/255 (max channel, after a 3x3 box blur) on at most {args.max_frac:.1%} of pixels; render errors fail",
        "per_renderer": per_renderer,
        "per_fixture": per_fixture,
        "pairwise": pair_tot,
        "failures_saved": saved,
        "first_failures": [r for r in rows if r["status"] in ("disagree", "render_error")][:40],
        "rows": rows,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(f"render: {passed}/{len(judged)} viewer-pages agree with consensus; {saved} failure image sets saved")


if __name__ == "__main__":
    main()
