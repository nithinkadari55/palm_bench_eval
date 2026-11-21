#!/usr/bin/env python3
"""Test 3: EXIF orientation through the raikiri image path.

raikiri-net image_decoder.rs (a570d903) reads the tag with image's ImageDecoder::orientation() (line 44) and applies
it with DynamicImage::apply_orientation() (line 56); no kamadak-exif. `rkpipe decode` runs that exact path
(raikiri-net ImageResolver<FileNetworkProvider>), `rkpipe orient` reports the tag value image reads.

Corpus: recurser/exif-orientation-examples (Landscape_0..8, Portrait_0..8; JPEG). Oracle: Pillow
ImageOps.exif_transpose on the same file. Extra: PNG (eXIf) and WebP (EXIF chunk) files generated from the upright
Landscape_0 by storing inverse-transformed pixels with tag N, so the expected result is the upright image exactly.
"""
import argparse
import glob
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rkpipe", required=True)
    args = ap.parse_args()
    from PIL import Image, ImageOps
    T = Image.Transpose
    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    items = []
    for f in sorted(glob.glob(os.path.join(args.data, "exif-orientation", "*_[0-8].jpg"))):
        n = int(re.search(r"_(\d)\.jpg$", f).group(1))
        im = Image.open(f)
        exp = np.asarray(ImageOps.exif_transpose(im).convert("RGBA"))
        items.append({"id": os.path.basename(f), "path": f, "tag": n if n else 1, "digit": n, "expected": exp, "exact": False,
                      "format": "jpeg"})
    up_path = os.path.join(args.data, "exif-orientation", "Landscape_0.jpg")
    upright = Image.open(up_path).convert("RGB")
    upright = upright.resize((upright.width // 4, upright.height // 4), Image.Resampling.BOX)
    inverse = {2: T.FLIP_LEFT_RIGHT, 3: T.ROTATE_180, 4: T.FLIP_TOP_BOTTOM, 5: T.TRANSPOSE, 6: T.ROTATE_90,
               7: T.TRANSVERSE, 8: T.ROTATE_270}
    for n in range(1, 9):
        stored = upright.transpose(inverse[n]) if n in inverse else upright.copy()
        ex = Image.Exif()
        ex[0x0112] = n
        for fmt, ext, kw in (("png", "png", {}), ("webp", "webp", {"lossless": True})):
            p = os.path.join(work, f"gen_orient{n}.{ext}")
            stored.save(p, exif=ex.tobytes(), **kw)
            chk = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
            assert np.array_equal(np.asarray(chk), np.asarray(upright)), f"generator self-check failed for {p}"
            items.append({"id": os.path.basename(p), "path": p, "tag": n,
                          "expected": np.asarray(upright.convert("RGBA")), "exact": True, "format": fmt})
    dec = [{"id": it["id"], "input": it["path"], "out": os.path.join(work, it["id"] + ".raw"), "args": []} for it in items]
    res = common.run_batch(args.rkpipe, "decode", dec, os.path.join(work, "decode_manifest.json"),
                           os.path.join(work, "decode_batch.json"))
    ori = common.run_batch(args.rkpipe, "orient", [dict(c, out="-") for c in dec], os.path.join(work, "orient_manifest.json"),
                           os.path.join(work, "orient_batch.json"))
    results, per_format = [], {}
    for it, c in zip(items, dec):
        r = res.get(it["id"]) or {"status": "missing"}
        o = ori.get(it["id"]) or {"status": "missing"}
        m = re.search(r"orientation=(\d)", o.get("message", ""))
        read_tag = int(m.group(1)) if m else None
        case = {"id": it["id"], "format": it["format"], "tag_expected": it["tag"], "tag_read_by_image": read_tag}
        if r["status"] != "ok":
            case.update({"pass": False, "error": f'{r["status"]}: {r.get("message", "")}'})
        else:
            got = common.read_raw(c["out"])[0]
            exp = it["expected"]
            if got.shape != exp.shape:
                case.update({"pass": False, "reason": "shape", "got": list(got.shape), "expected": list(exp.shape)})
            else:
                st = common.diff_stats(common.to_unit(got), common.to_unit(exp))
                px_ok = st["max_abs"] <= 1.0 if it["exact"] else st["mean_abs"] <= 2.0
                tag_ok = read_tag == it["tag"] or (it.get("digit") == 0 and read_tag in (0, 1))
                case.update({"pass": px_ok and tag_ok, **st})
        results.append(case)
        pf = per_format.setdefault(it["format"], {"pass": 0, "total": 0})
        pf["total"] += 1
        pf["pass"] += int(case["pass"])
    common.write_result(args.out, "exif_orientation",
                        "image reports the expected tag (file-name digit; the _0 files carry the invalid value 0, read as 0 or 1) and the decoded, oriented "
                        "pixels have the upright size and match: JPEG mean |diff| <= 2.0 vs Pillow exif_transpose; "
                        "generated PNG/WebP lossless every channel within 1/255 of the upright source",
                        results, {"per_format": per_format, "pipeline": "raikiri-net ImageResolver (a570d903)"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
