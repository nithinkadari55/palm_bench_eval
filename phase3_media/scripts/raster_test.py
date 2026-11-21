#!/usr/bin/env python3
"""Test 1: raster decoders (image 0.25.10: png / zune-jpeg / gif / image-webp) against independent oracles.

  png  : PngSuite (175 valid files) vs pypng (pure-Python PNG decoder, raw samples, no sBIT/gamma)
  jpeg : libjpeg-turbo testimages + cjpeg-encoded variants of its test sources vs djpeg (libjpeg-turbo)
  webp : libwebp-test-data (131 files) vs dwebp (libwebp); animated WebP (gif2webp from the GIF suite) vs Pillow
  gif  : Robert Ancell's GIF test suite (expected RGBA frames) + image-gif samples vs Pillow
"""
import argparse
import configparser
import glob
import os
import shutil
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

LOSSY_TOL = "mean |diff| <= 1.0 (8-bit scale) and <= 1% of pixels with any channel |diff| > 3"


def compare_frames(got, exp, exact_tol=None):
    """got/exp: (n, h, w, 4) float unit arrays. Colour is compared only where either alpha > 0."""
    if got.shape != exp.shape:
        return False, {"reason": "shape", "got": list(got.shape), "expected": list(exp.shape)}
    mask = (np.maximum(got[..., 3], exp[..., 3]) > 0)[..., None]
    g = np.where(mask, got, np.concatenate([np.zeros_like(got[..., :3]), got[..., 3:]], axis=-1))
    e = np.where(mask, exp, np.concatenate([np.zeros_like(exp[..., :3]), exp[..., 3:]], axis=-1))
    st = common.diff_stats(g, e)
    if exact_tol is not None:
        ok = st["max_abs"] <= exact_tol + 1e-9
    else:
        ok = st["mean_abs"] <= 1.0 and st["pct_gt3"] <= 1.0
    return ok, st


def rust_frames(res, out_path):
    if res is None:
        return None, "no result"
    if res["status"] != "ok":
        return None, f"{res['status']}: {res.get('message', '')}"
    a = common.read_raw(out_path)
    return common.to_unit(a), None


# ---------------- PNG ----------------

def pypng_decode(path):
    import png  # pypng
    w, h, rows, info = png.Reader(filename=path).read()
    a = np.array([np.asarray(r, dtype=np.int64) for r in rows])
    planes, bd = info["planes"], info["bitdepth"]
    maxv = float(2 ** bd - 1)
    a = a.reshape(h, w, planes)
    if "palette" in info and planes == 1 and not info["greyscale"]:
        pal = np.array([list(p) + [255] * (4 - len(p)) for p in info["palette"]], dtype=np.float64) / 255.0
        if a.max(initial=0) >= len(pal):
            raise ValueError("palette index out of range")
        return pal[a[..., 0]]
    out = np.zeros((h, w, 4))
    if info["greyscale"]:
        g = a[..., 0] / maxv
        out[..., 0] = out[..., 1] = out[..., 2] = g
        if info["alpha"]:
            out[..., 3] = a[..., 1] / maxv
        else:
            t = info.get("transparent")
            out[..., 3] = 1.0 if t is None else (a[..., 0] != t[0]).astype(np.float64)
    else:
        out[..., :3] = a[..., :3] / maxv
        if info["alpha"]:
            out[..., 3] = a[..., 3] / maxv
        else:
            t = info.get("transparent")
            out[..., 3] = 1.0 if t is None else (~np.all(a[..., :3] == np.array(t), axis=-1)).astype(np.float64)
    return out


def test_png(args):
    files = sorted(f for f in glob.glob(os.path.join(args.data, "pngsuite", "*.png"))
                   if not os.path.basename(f).startswith("x"))
    cases, meta = [], {}
    for f in files:
        cid = os.path.basename(f)
        out = os.path.join(args.work, "png", cid + ".raw")
        cases.append({"id": cid, "input": f, "out": out, "args": []})
        meta[cid] = (f, out)
    res = common.run_batch(args.bin, "decode", cases, os.path.join(args.work, "png_manifest.json"),
                           os.path.join(args.work, "png_batch.json"))
    results = []
    for cid, (f, out) in meta.items():
        got, err = rust_frames(res.get(cid), out)
        exp = pypng_decode(f)[None]
        if got is None:
            results.append({"id": cid, "pass": False, "error": err})
            continue
        ok, st = compare_frames(got, exp, exact_tol=1.0)
        results.append({"id": cid, "pass": ok, **st})
    return results, "decodes, same size, every channel within 1/255 of pypng (16-bit compared on the 8-bit scale; colour ignored where both alpha = 0)", {
        "oracle": "pypng 0.20220715.0 Reader.read() raw samples (no sBIT/gAMA applied, as image does not apply them)",
        "corpus": "PngSuite 2017jul19, all files not starting with x"}


# ---------------- JPEG ----------------

CJPEG_VARIANTS = [
    ("q75-420", ["-quality", "75"]),
    ("q95-444", ["-quality", "95", "-sample", "1x1"]),
    ("q90-422", ["-quality", "90", "-sample", "2x1"]),
    ("q90-440", ["-quality", "90", "-sample", "1x2"]),
    ("q90-411", ["-quality", "90", "-sample", "4x1"]),
    ("q100-444", ["-quality", "100", "-sample", "1x1"]),
    ("q10-420", ["-quality", "10"]),
    ("gray", ["-quality", "85", "-grayscale"]),
    ("progressive", ["-quality", "85", "-progressive"]),
    ("progressive-444", ["-quality", "85", "-progressive", "-sample", "1x1"]),
    ("optimize", ["-quality", "85", "-optimize"]),
    ("restart1", ["-quality", "85", "-restart", "1"]),
    ("restart-b7", ["-quality", "85", "-restart", "7b"]),
    ("arithmetic", ["-quality", "85", "-arithmetic"]),
    ("dct-float", ["-quality", "85", "-dct", "float"]),
    ("dct-fast", ["-quality", "85", "-dct", "fast"]),
    ("rgb", ["-quality", "90", "-rgb"]),
    ("smooth", ["-quality", "85", "-smooth", "30"]),
]


def pnm_read(path):
    from PIL import Image
    im = Image.open(path)
    im.load()
    return common.to_unit(np.asarray(im.convert("RGBA")))[None]


def test_jpeg(args):
    src_dir = os.path.join(args.data, "libjpeg-turbo", "testimages")
    gen = os.path.join(args.work, "jpeg_src")
    os.makedirs(gen, exist_ok=True)
    files = sorted(glob.glob(os.path.join(src_dir, "*.jpg")))
    sources = [os.path.join(src_dir, n) for n in ("testorig.ppm", "vgl_6434_0018a.bmp", "vgl_6548_0026a.bmp",
                                                    "shira_bird8.bmp")]
    sources = [s for s in sources if os.path.exists(s)]
    for s in sources:
        base = os.path.splitext(os.path.basename(s))[0]
        for tag, opts in CJPEG_VARIANTS:
            outp = os.path.join(gen, f"{base}.{tag}.jpg")
            r = subprocess.run(["cjpeg"] + opts + ["-outfile", outp, s], capture_output=True)
            if r.returncode == 0:
                files.append(outp)
    cases, meta = [], {}
    for f in files:
        cid = os.path.relpath(f, args.work) if f.startswith(args.work) else os.path.basename(f)
        cid = cid.replace(os.sep, "/")
        out = os.path.join(args.work, "jpeg", os.path.basename(f) + ".raw")
        cases.append({"id": cid, "input": f, "out": out, "args": []})
        meta[cid] = (f, out)
    os.makedirs(os.path.join(args.work, "jpeg_ref"), exist_ok=True)
    res = common.run_batch(args.bin, "decode", cases, os.path.join(args.work, "jpeg_manifest.json"),
                           os.path.join(args.work, "jpeg_batch.json"))
    results, no_oracle = [], []
    for cid, (f, out) in meta.items():
        ref = os.path.join(args.work, "jpeg_ref", os.path.basename(f) + ".pnm")
        r = subprocess.run(["djpeg", "-pnm", "-outfile", ref, f], capture_output=True)
        got, err = rust_frames(res.get(cid), out)
        if r.returncode != 0:
            no_oracle.append({"id": cid, "djpeg": r.stderr.decode(errors="replace")[:200],
                              "rust": "ok" if got is not None else err})
            continue
        exp = pnm_read(ref)
        if got is None:
            results.append({"id": cid, "pass": False, "error": err})
            continue
        ok, st = compare_frames(got, exp)
        results.append({"id": cid, "pass": ok, **st})
    djv = subprocess.run(["djpeg", "-version"], capture_output=True, text=True)
    return results, f"decodes, same size, {LOSSY_TOL} vs djpeg default (islow IDCT, fancy upsampling)", {
        "oracle": "djpeg " + (djv.stderr or djv.stdout).strip().splitlines()[0] if (djv.stderr or djv.stdout) else "djpeg",
        "corpus": "libjpeg-turbo 3.2.1 testimages/*.jpg plus cjpeg variants of testorig.ppm / vgl_*.bmp / shira_bird8.bmp: "
                  + ", ".join(t for t, _ in CJPEG_VARIANTS),
        "no_oracle": no_oracle}


# ---------------- WebP ----------------

def pam_read(path):
    with open(path, "rb") as fh:
        data = fh.read()
    hdr_end = data.index(b"ENDHDR\n") + len(b"ENDHDR\n")
    hdr = dict(l.split(" ", 1) for l in data[:hdr_end].decode().splitlines()[1:-1] if " " in l)
    w, h, d = int(hdr["WIDTH"]), int(hdr["HEIGHT"]), int(hdr["DEPTH"])
    a = np.frombuffer(data, dtype=np.uint8, offset=hdr_end).reshape(h, w, d)
    if d == 3:
        a = np.concatenate([a, np.full((h, w, 1), 255, np.uint8)], axis=2)
    return common.to_unit(a)[None]


def webp_kind(path):
    with open(path, "rb") as fh:
        d = fh.read()
    chunks, pos = [], 12
    while pos + 8 <= len(d):
        fourcc = d[pos:pos + 4]
        size = int.from_bytes(d[pos + 4:pos + 8], "little")
        chunks.append(fourcc)
        pos += 8 + size + (size & 1)
    if b"ANIM" in chunks:
        return "animated"
    if b"VP8L" in chunks:
        return "lossless"
    if b"ALPH" in chunks:
        return "lossy_alpha"
    return "lossy"


def pillow_frames(path, limit=300):
    from PIL import Image, ImageSequence
    im = Image.open(path)
    frames = []
    for i, fr in enumerate(ImageSequence.Iterator(im)):
        if i >= limit:
            break
        frames.append(np.asarray(fr.convert("RGBA")))
    return common.to_unit(np.stack(frames))


def test_webp(args):
    files = sorted(glob.glob(os.path.join(args.data, "libwebp-test-data", "*.webp")))
    anim_dir = os.path.join(args.work, "webp_anim")
    os.makedirs(anim_dir, exist_ok=True)
    anim = []
    if shutil.which("gif2webp"):
        for n in ("animation", "animation-speed", "dispose-none", "dispose-keep", "dispose-restore-background",
                  "dispose-restore-previous", "animation-multi-image", "loop-once"):
            g = os.path.join(args.data, "pygif", "test-suite", n + ".gif")
            if os.path.exists(g):
                for mode, opt in (("lossless", []), ("lossy", ["-lossy"])):
                    o = os.path.join(anim_dir, f"{n}.{mode}.webp")
                    if subprocess.run(["gif2webp"] + opt + ["-o", o, g], capture_output=True).returncode == 0:
                        anim.append(o)
        for g in sorted(glob.glob(os.path.join(args.data, "image-gif", "tests", "samples", "*.gif"))):
            o = os.path.join(anim_dir, os.path.basename(g)[:-4] + ".gif2webp.webp")
            if subprocess.run(["gif2webp", "-o", o, g], capture_output=True).returncode == 0:
                anim.append(o)
    cases, meta = [], {}
    for f in files + anim:
        cid = os.path.basename(f)
        out = os.path.join(args.work, "webp", cid + ".raw")
        sub_is_anim = f in anim
        cases.append({"id": cid, "input": f, "out": out, "args": []})
        meta[cid] = (f, out, sub_is_anim)
    res_still = common.run_batch(args.bin, "decode", [c for c in cases if not meta[c["id"]][2]],
                                 os.path.join(args.work, "webp_manifest.json"), os.path.join(args.work, "webp_batch.json"))
    res_anim = common.run_batch(args.bin, "frames", [c for c in cases if meta[c["id"]][2]],
                                os.path.join(args.work, "webp_anim_manifest.json"),
                                os.path.join(args.work, "webp_anim_batch.json")) if anim else {}
    os.makedirs(os.path.join(args.work, "webp_ref"), exist_ok=True)
    results, by_kind = [], {}
    for cid, (f, out, is_anim) in meta.items():
        kind = "animated" if is_anim else webp_kind(f)
        got, err = rust_frames((res_anim if is_anim else res_still).get(cid), out)
        if is_anim:
            exp = pillow_frames(f)
            oracle = "Pillow (libwebp WebPAnimDecoder)"
        else:
            ref = os.path.join(args.work, "webp_ref", cid + ".pam")
            r = subprocess.run(["dwebp", f, "-pam", "-o", ref], capture_output=True)
            if r.returncode != 0:
                results.append({"id": cid, "kind": kind, "pass": got is None, "oracle": "dwebp rejected",
                                "rust": "err" if got is None else "ok", "note": "dwebp rejects this file"})
                by_kind.setdefault(kind, [0, 0])[0 if got is None else 1] += 1
                continue
            exp = pam_read(ref)
            oracle = "dwebp"
        if got is None:
            results.append({"id": cid, "kind": kind, "pass": False, "error": err})
            by_kind.setdefault(kind, [0, 0])[1] += 1
            continue
        exact = 1.0 if kind in ("lossless",) else None
        ok, st = compare_frames(got, exp, exact_tol=exact)
        results.append({"id": cid, "kind": kind, "oracle": oracle, "pass": ok, **st})
        by_kind.setdefault(kind, [0, 0])[0 if ok else 1] += 1
    return results, ("lossless: every channel within 1/255 of dwebp; lossy / lossy+alpha: " + LOSSY_TOL
                     + " vs dwebp; animated: same frame count and every frame " + LOSSY_TOL + " vs Pillow"), {
        "per_kind": {k: {"pass": v[0], "fail": v[1]} for k, v in by_kind.items()},
        "corpus": "libwebp-test-data 06ddd96e (131 files, no animated files) + animated WebP made with gif2webp from the GIF suites"}


# ---------------- GIF ----------------

def test_gif(args):
    suite = os.path.join(args.data, "pygif", "test-suite")
    tests = [l.strip() for l in open(os.path.join(suite, "TESTS"), encoding="utf-8") if l.strip()]
    cases, meta = [], {}
    for t in tests:
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
        cp.read(os.path.join(suite, t + ".conf"), encoding="utf-8")
        cfg = cp["config"]
        f = os.path.join(suite, cfg.get("input"))
        frames = [x.strip() for x in cfg.get("frames", "").split(",") if x.strip()]
        w, h = int(cfg.get("width", "0")), int(cfg.get("height", "0"))
        exp = []
        for fr in frames:
            px = cp[fr].get("pixels")
            raw = np.fromfile(os.path.join(suite, px), dtype=np.uint8)
            exp.append(raw.reshape(h, w, 4))
        cid = "pygif/" + t
        out = os.path.join(args.work, "gif", t + ".raw")
        cases.append({"id": cid, "input": f, "out": out, "args": []})
        meta[cid] = (out, ("expected", exp, w, h))
    for g in sorted(glob.glob(os.path.join(args.data, "image-gif", "tests", "samples", "*.gif"))):
        cid = "image-gif/" + os.path.basename(g)
        out = os.path.join(args.work, "gif", "imagegif_" + os.path.basename(g) + ".raw")
        cases.append({"id": cid, "input": g, "out": out, "args": []})
        meta[cid] = (out, ("pillow", g, 0, 0))
    res = common.run_batch(args.bin, "frames", cases, os.path.join(args.work, "gif_manifest.json"),
                           os.path.join(args.work, "gif_batch.json"))
    results = []
    for cid, (out, (kind, ref, w, h)) in meta.items():
        got, err = rust_frames(res.get(cid), out)
        if kind == "expected":
            if not ref:
                ok = got is None or got.shape[0] == 0
                results.append({"id": cid, "pass": ok, "expected": "no frames (decoder should reject)",
                                "rust": "err" if got is None else f"{got.shape[0]} frame(s)"})
                continue
            exp = common.to_unit(np.stack(ref))
        else:
            try:
                exp = pillow_frames(ref)
            except Exception as e:  # noqa: BLE001
                results.append({"id": cid, "pass": got is None, "note": f"Pillow rejects: {e}"})
                continue
        if got is None:
            results.append({"id": cid, "pass": False, "error": err, "expected_frames": int(exp.shape[0])})
            continue
        ok, st = compare_frames(got, exp, exact_tol=1.0)
        results.append({"id": cid, "pass": ok, "frames": int(got.shape[0]), "expected_frames": int(exp.shape[0]), **st})
    return results, ("pygif suite: same frame count and size, every composited RGBA frame within 1/255 of the expected "
                     ".rgba (zero-frame tests must be rejected); image-gif samples: same vs Pillow composited frames"), {
        "corpus": "robert-ancell/pygif test-suite 741b2820 (84 tests, CC-BY-SA-4.0) + image-rs/image-gif tests/samples a5f89ddc"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", required=True, choices=["png", "jpeg", "webp", "gif"])
    ap.add_argument("--bin", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    args.work = os.path.abspath(args.work)
    for d in ("png", "jpeg", "webp", "gif"):
        os.makedirs(os.path.join(args.work, d), exist_ok=True)
    fn = {"png": test_png, "jpeg": test_jpeg, "webp": test_webp, "gif": test_gif}[args.format]
    results, crit, extra = fn(args)
    extra = dict(extra or {})
    extra["decoder"] = "image 0.25.10 (default-features off; gif, jpeg (zune-jpeg 0.5.15), png 0.18.1, webp (image-webp 0.2.4))"
    common.write_result(args.out, f"raster_{args.format}", crit, results, extra)
    return 0


if __name__ == "__main__":
    sys.exit(main())
