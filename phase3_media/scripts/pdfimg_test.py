#!/usr/bin/env python3
"""Test 7: image embedding in PDF with krilla 0.7.0.

Two paths per image:
  native : krilla Image::from_png / from_jpeg / from_gif / from_webp (JPEG kept as DCTDecode).
  fulgur : what fulgur-raikiri does (paint/raster.rs krilla_image): raikiri decodes to straight RGBA8
           (raikiri-net ImageResolver, here `rkpipe decode`), then Image::from_custom(RGB + optional alpha).
Each PDF has one page of W x H pt with the image drawn at full size; pdftoppm -r 72 rasterises it 1 pt = 1 px.
Pixels are compared with an independent decode (pypng for PNG, Pillow for the rest) composited on white.
Structure is read with pypdf: filter, bits per component, SMask, Decode array, and JPEG byte identity.
"""
import argparse
import hashlib
import io
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import raster_test  # noqa: E402

PIX_CRIT = ("pdftoppm -r 72 raster vs the reference decode composited on white: mean |diff| <= 2.0 and <= 1% of pixels "
            "with a channel |diff| > 16 (8-bit scale); CMYK JPEGs: mean deltaE2000 <= 5 vs the naive Adobe-inverted "
            "conversion (rasteriser DeviceCMYK conversions differ)")


def image_list(data, work):
    from PIL import Image
    ps = os.path.join(data, "pngsuite")
    jt = os.path.join(data, "libjpeg-turbo", "testimages")
    wp = os.path.join(data, "libwebp-test-data")
    cm = os.path.join(data, "cmyk-jpeg")
    items = []
    for n, tag in (("basn0g08", "png gray8"), ("basn0g16", "png gray16"), ("basn2c08", "png rgb8"),
                   ("basn2c16", "png rgb16"), ("basn3p08", "png palette8"), ("basn3p04", "png palette4"),
                   ("basn4a08", "png gray+alpha8"), ("basn4a16", "png gray+alpha16"), ("basn6a08", "png rgba8"),
                   ("basn6a16", "png rgba16"), ("tbrn2c08", "png rgb8 tRNS"), ("tbbn3p08", "png palette tRNS"),
                   ("basi6a08", "png rgba8 interlaced")):
        items.append((os.path.join(ps, n + ".png"), tag))
    os.makedirs(work, exist_ok=True)
    src = Image.open(os.path.join(jt, "testorig.ppm"))
    prog = os.path.join(work, "testorig.progressive.jpg")
    src.save(prog, quality=85, progressive=True)
    gray = os.path.join(work, "testorig.gray.jpg")
    src.convert("L").save(gray, quality=85)
    s444 = os.path.join(work, "testorig.444.jpg")
    src.save(s444, quality=92, subsampling=0)
    items += [(os.path.join(jt, "testorig.jpg"), "jpeg baseline 4:2:0"), (os.path.join(jt, "testimgint.jpg"), "jpeg baseline"),
              (prog, "jpeg progressive"), (gray, "jpeg gray"), (s444, "jpeg 4:4:4"),
              (os.path.join(jt, "testimgari.jpg"), "jpeg arithmetic"), (os.path.join(jt, "monkey12.jpg"), "jpeg 12-bit"),
              (os.path.join(cm, "mozilla_jpg-cmyk-1.jpg"), "jpeg cmyk adobe-inverted"),
              (os.path.join(cm, "jpeg-js_tree-cmyk.jpg"), "jpeg ycck"),
              (os.path.join(cm, "jpeg-js_tree-cmyk-notransform.jpg"), "jpeg cmyk adobe-inverted")]
    d = open(os.path.join(cm, "mozilla_jpg-cmyk-1.jpg"), "rb").read()
    from cmyk_test import describe
    _, app14 = describe(d)
    if app14:
        x = app14[0]
        p = os.path.join(work, "mozilla_jpg-cmyk-1.no-app14.jpg")
        open(p, "wb").write(d[:x[1]] + d[x[1] + x[2]:])
        items.append((p, "jpeg cmyk non-inverted (no APP14)"))
    items += [(os.path.join(wp, "test.webp"), "webp lossy"), (os.path.join(wp, "lossless1.webp"), "webp lossless"),
              (os.path.join(wp, "lossy_alpha1.webp"), "webp lossy+alpha"),
              (os.path.join(wp, "lossless_big_random_alpha.webp"), "webp lossless+alpha")]
    items += [(os.path.join(data, "pygif", "test-suite", "four-colors.gif"), "gif"),
              (os.path.join(data, "image-gif", "tests", "samples", "sample_1.gif"), "gif"),
              (os.path.join(data, "image-gif", "tests", "samples", "alpha_gif_a.gif"), "gif transparency")]
    return [(p, t) for p, t in items if os.path.exists(p)]


def reference(path, tag):
    """Straight RGBA in [0,1] for the first frame; CMYK JPEGs also return the naive conversion."""
    from PIL import Image
    if path.endswith(".png"):
        return raster_test.pypng_decode(path), None
    im = Image.open(path)
    im.load()
    if im.mode == "CMYK":
        cmyk = np.asarray(im).astype(np.float64)
        if "non-inverted" in tag:
            cmyk = 255.0 - cmyk
        c, m, y, k = (cmyk[..., i] for i in range(4))
        rgb = np.stack([(255 - c) * (255 - k), (255 - m) * (255 - k), (255 - y) * (255 - k)], -1) / 65025.0
        return np.concatenate([rgb, np.ones(rgb.shape[:2] + (1,))], -1), "cmyk"
    return common.to_unit(np.asarray(im.convert("RGBA"))), None


def pdf_structure(pdf_path):
    from pypdf import PdfReader
    r = PdfReader(pdf_path)
    page = r.pages[0]
    xo = page["/Resources"].get("/XObject")
    if xo is None:
        return None
    xo = xo.get_object()
    for _, ref in xo.items():
        obj = ref.get_object()
        if obj.get("/Subtype") != "/Image":
            continue
        filt = obj.get("/Filter")
        if filt is not None and not isinstance(filt, str):
            filt = [str(f) for f in filt]
        elif filt is not None:
            filt = str(filt)
        smask = obj.get("/SMask")
        cs = obj.get("/ColorSpace")
        cs = cs.get_object() if cs is not None and hasattr(cs, "get_object") else cs
        if cs is not None and not isinstance(cs, str):
            cs = str(cs[0])
        decode = obj.get("/Decode")
        info = {"filter": filt, "bits_per_component": int(obj.get("/BitsPerComponent", 0)),
                "width": int(obj.get("/Width", 0)), "height": int(obj.get("/Height", 0)),
                "colorspace": None if cs is None else str(cs),
                "decode": [float(x) for x in decode] if decode is not None else None,
                "smask": smask is not None}
        if smask is not None:
            info["smask_bits"] = int(smask.get_object().get("/BitsPerComponent", 0))
        raw = obj._data if hasattr(obj, "_data") else b""
        info["stream_sha256"] = hashlib.sha256(raw).hexdigest()
        info["stream_bytes"] = len(raw)
        return info
    return None


def evaluate(work, i, p, tag, path_name, res, dec, ref, kind, ref_err, src_bytes, src_sha, pix, struct_cases, no_oracle):
    from PIL import Image
    r = res.get(i)
    if path_name == "fulgur" and r is None:
        d = dec.get(i) or {}
        r = {"status": "decode_" + d.get("status", "missing"), "message": d.get("message", "")}
    r = r or {"status": "missing"}
    cid = f"{path_name}:{i}"
    if r["status"] != "ok":
        if ref is None:
            no_oracle.append({"id": cid, "kind": tag, "oracle_error": ref_err,
                              "candidate": f'{r["status"]}: {r.get("message", "")}'})
        else:
            pix.append({"id": cid, "kind": tag, "pass": False, "error": f'{r["status"]}: {r.get("message", "")}'})
        return
    pdf = os.path.join(work, path_name, i + ".pdf")
    out = os.path.join(work, "ras", f"{path_name}_{i}")
    subprocess.run(["pdftoppm", "-r", "72", "-png", "-singlefile", pdf, out], capture_output=True, timeout=120)
    got = None
    try:
        got = np.asarray(Image.open(out + ".png").convert("RGB")).astype(np.float64) / 255.0
        ras_err = None
    except Exception as e:  # noqa: BLE001
        ras_err = f"rasterise: {e}"
    if ref is None:
        no_oracle.append({"id": cid, "kind": tag, "oracle_error": ref_err, "candidate": "ok (PDF written)",
                          "rasterised": got is not None})
    elif got is None:
        pix.append({"id": cid, "kind": tag, "pass": False, "error": ras_err})
    else:
        exp = common.flatten_on_white(ref)
        if got.shape != exp.shape:
            case = {"id": cid, "kind": tag, "pass": False, "reason": "shape", "got": list(got.shape),
                    "expected": list(exp.shape)}
        elif kind == "cmyk":
            de = common.de_stats(common.de2000_srgb(got, exp))
            case = {"id": cid, "kind": tag, "pass": de["mean"] <= 5.0, "de2000_vs_naive": de}
        else:
            st = common.diff_stats(got, exp)
            d16 = float((np.abs(got - exp).max(axis=-1) * 255 > 16).mean()) * 100
            case = {"id": cid, "kind": tag, "pass": st["mean_abs"] <= 2.0 and d16 <= 1.0, **st,
                    "pct_gt16": round(d16, 4)}
        pix.append(case)
    s = pdf_structure(pdf)
    pdf_bytes = os.path.getsize(pdf)
    sc = {"id": cid, "kind": tag, "pdf_bytes": pdf_bytes, "source_bytes": src_bytes,
          "size_ratio": round(pdf_bytes / src_bytes, 3), "image": s}
    checks = {}
    if s is None:
        checks["image_xobject_found"] = False
    else:
        filt = s["filter"]
        is_dct = filt == "/DCTDecode" or (isinstance(filt, list) and "/DCTDecode" in filt)
        if tag.startswith("jpeg"):
            if path_name == "native":
                checks["jpeg_dctdecode_passthrough"] = is_dct and s["stream_sha256"] == src_sha
                if "cmyk" in tag or "ycck" in tag:
                    want_inv = "non-inverted" not in tag
                    has_inv = s["decode"] is not None and s["decode"][:2] == [1.0, 0.0]
                    checks["cmyk_decode_array_matches_inversion"] = has_inv == want_inv
            else:
                checks["jpeg_reencoded_not_dct (fulgur path, informational)"] = not is_dct
        if ref is not None:
            has_alpha = bool(np.any(ref[..., 3] < 1.0))
            if has_alpha:
                checks["alpha_becomes_smask"] = s["smask"]
            else:
                checks["no_smask_for_opaque_image (informational)"] = not s["smask"]
        if "16" in tag.split()[-1] and path_name == "native":
            checks["16bit_kept"] = s["bits_per_component"] == 16
    sc["checks"] = checks
    gating = {k: v for k, v in checks.items() if "informational" not in k}
    sc["pass"] = all(gating.values()) if gating else True
    struct_cases.append(sc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--pdfimg", required=True)
    ap.add_argument("--rkpipe", required=True)
    args = ap.parse_args()
    work = os.path.abspath(args.work)
    items = image_list(args.data, os.path.join(work, "gen"))
    ids = {}
    for p, tag in items:
        ids[os.path.basename(p)] = (p, tag)
    for d in ("native", "fulgur", "raw", "ras"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    nat = common.run_batch(args.pdfimg, "native",
                           [{"id": i, "input": p, "out": os.path.join(work, "native", i + ".pdf"), "args": []}
                            for i, (p, _) in ids.items()],
                           os.path.join(work, "native_manifest.json"), os.path.join(work, "native_batch.json"))
    dec = common.run_batch(args.rkpipe, "decode",
                           [{"id": i, "input": p, "out": os.path.join(work, "raw", i + ".raw"), "args": []}
                            for i, (p, _) in ids.items()],
                           os.path.join(work, "rk_manifest.json"), os.path.join(work, "rk_batch.json"))
    ful = common.run_batch(args.pdfimg, "fulgur",
                           [{"id": i, "input": os.path.join(work, "raw", i + ".raw"),
                             "out": os.path.join(work, "fulgur", i + ".pdf"), "args": []}
                            for i in ids if (dec.get(i) or {}).get("status") == "ok"],
                           os.path.join(work, "fulgur_manifest.json"), os.path.join(work, "fulgur_batch.json"))
    pix, struct_cases = [], []
    no_oracle, harness_errors = [], []
    for i, (p, tag) in ids.items():
        try:
            ref, kind = reference(p, tag)
            ref_err = None
        except Exception as e:  # noqa: BLE001  (e.g. 12-bit JPEG: Pillow cannot decode it)
            ref, kind, ref_err = None, None, f"{type(e).__name__}: {e}"[:200]
        src_bytes = os.path.getsize(p)
        src_sha = common.sha256_file(p)
        for path_name, res in (("native", nat), ("fulgur", ful)):
            cid = f"{path_name}:{i}"
            try:
                evaluate(work, i, p, tag, path_name, res, dec, ref, kind, ref_err, src_bytes, src_sha,
                         pix, struct_cases, no_oracle)
            except Exception as e:  # noqa: BLE001  one input must never abort the test
                harness_errors.append({"id": cid, "kind": tag, "error": f"{type(e).__name__}: {e}"[:300]})
    common.write_result(os.path.join(args.results, "pdf_images.json"), "pdf_images", PIX_CRIT, pix,
                        {"no_oracle": no_oracle, "harness_errors": harness_errors,
                         "krilla": "0.7.0 (raster-images)", "paths": "native = Image::from_png/jpeg/gif/webp; fulgur = "
                         "raikiri RGBA8 -> Image::from_custom (fulgur-raikiri paint/raster.rs:29-91)"})
    common.write_result(os.path.join(args.results, "pdf_images_structure.json"), "pdf_images_structure",
                        "native JPEG: /DCTDecode stream byte-identical to the source file; CMYK JPEG: /Decode [1 0 ...] "
                        "exactly when the file uses Adobe inversion; any image with alpha < 1: /SMask present; 16-bit PNG "
                        "native: BitsPerComponent 16 (an SMask on a fully opaque image is reported, not gated)", struct_cases,
                        {"harness_errors": harness_errors})
    return 0


if __name__ == "__main__":
    sys.exit(main())
