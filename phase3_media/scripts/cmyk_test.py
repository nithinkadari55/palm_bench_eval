#!/usr/bin/env python3
"""Test 2: CMYK / YCCK JPEG decoding (image 0.25.10 + zune-jpeg 0.5.15, and the raikiri pipeline).

Oracles (Pillow 13 with libjpeg-turbo + LittleCMS):
  naive : Pillow's CMYK samples (it applies the Adobe inversion) -> RGB = (255-C)(255-K)/255, computed here.
  icc   : the same samples through LittleCMS (ImageCms) with the embedded CMYK profile, or FOGRA39 (colord) if none,
          relative colorimetric, to sRGB.
  primary = icc when the file embeds a CMYK profile (what a colour-managed browser shows), else naive.
Non-inverted CMYK: no public sample exists, so each Adobe transform=0 file is also tested with its APP14 segment
removed. Without APP14, JFIF/libjpeg semantics say the samples are plain (not inverted) CMYK, so the oracle uses
255 - Pillow's samples (Pillow always assumes Adobe inversion).
"""
import argparse
import glob
import io
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

CRIT = "mean deltaE2000 <= 2.0 and p95 <= 5.0 against the primary oracle (sRGB, D65 Lab)"


def segments(d):
    pos, out = 2, []
    while pos + 4 <= len(d) and d[pos] == 0xFF:
        m = d[pos + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            pos += 2
            continue
        ln = struct.unpack(">H", d[pos + 2:pos + 4])[0]
        out.append((m, pos, ln + 2, d[pos + 4:pos + 2 + ln]))
        if m == 0xDA:
            break
        pos += 2 + ln
    return out


def describe(d):
    s = segments(d)
    app14 = [x for x in s if x[0] == 0xEE and x[3][:5] == b"Adobe"]
    sof = [x for x in s if 0xC0 <= x[0] <= 0xCF and x[0] not in (0xC4, 0xC8, 0xCC)]
    return {"adobe_transform": app14[0][3][11] if app14 and len(app14[0][3]) > 11 else None,
            "components": sof[0][3][5] if sof else None,
            "progressive": bool(sof) and sof[0][0] in (0xC2, 0xC6, 0xCA)}, app14


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--raster", required=True)
    ap.add_argument("--rkpipe", required=True)
    ap.add_argument("--default-cmyk-icc", required=True)
    args = ap.parse_args()
    from PIL import Image, ImageCms
    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    files = []
    for f in sorted(glob.glob(os.path.join(args.data, "cmyk-jpeg", "*.jpg"))):
        d = open(f, "rb").read()
        info, app14 = describe(d)
        files.append((os.path.basename(f), f, info, False))
        if info["adobe_transform"] == 0:
            x = app14[0]
            stripped = d[:x[1]] + d[x[1] + x[2]:]
            p = os.path.join(work, os.path.basename(f)[:-4] + ".no-app14.jpg")
            open(p, "wb").write(stripped)
            files.append((os.path.basename(p), p, dict(info, adobe_transform=None), True))
    default_icc = ImageCms.getOpenProfile(args.default_cmyk_icc)
    srgb = ImageCms.createProfile("sRGB")
    oracles = {}
    for cid, f, info, stripped in files:
        im = Image.open(f)
        im.load()
        cmyk = np.asarray(im.convert("CMYK")).astype(np.float64)
        if stripped:
            cmyk = 255.0 - cmyk
        c, m, y, k = (cmyk[..., i] for i in range(4))
        naive = np.stack([(255 - c) * (255 - k), (255 - m) * (255 - k), (255 - y) * (255 - k)], -1) / (255.0 * 255.0)
        alt = np.stack([c * k, m * k, y * k], -1) / (255.0 * 255.0)
        icc_bytes = im.info.get("icc_profile")
        prof, prof_src = default_icc, os.path.basename(args.default_cmyk_icc)
        if icc_bytes:
            try:
                p = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
                if p.profile.xcolor_space.strip() == "CMYK":
                    prof, prof_src = p, "embedded"
            except Exception:  # noqa: BLE001
                pass
        h, w = cmyk.shape[:2]
        src_im = Image.frombytes("CMYK", (w, h), np.clip(cmyk, 0, 255).astype(np.uint8).tobytes())
        icc_rgb = ImageCms.profileToProfile(src_im, prof, srgb, renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                                            outputMode="RGB")
        icc = np.asarray(icc_rgb).astype(np.float64) / 255.0
        oracles[cid] = {"naive": naive, "alt": alt, "icc": icc, "profile": prof_src,
                        "primary": "icc" if prof_src == "embedded" else "naive"}
    out = []
    for dec, binp in (("image", args.raster), ("raikiri", args.rkpipe)):
        cases = [{"id": cid, "input": f, "out": os.path.join(work, f"{dec}_{cid}.raw"), "args": []}
                 for cid, f, _, _ in files]
        res = common.run_batch(binp, "decode", cases, os.path.join(work, f"{dec}_manifest.json"),
                               os.path.join(work, f"{dec}_batch.json"))
        for (cid, f, info, stripped), c in zip(files, cases):
            o = oracles[cid]
            r = res.get(cid) or {"status": "missing"}
            base = {"id": f"{dec}:{cid}", "decoder": dec, "file_info": info, "app14_stripped": stripped,
                    "icc_profile_used_by_oracle": o["profile"], "primary_oracle": o["primary"]}
            if r["status"] != "ok":
                out.append(dict(base, **{"pass": False, "error": f'{r["status"]}: {r.get("message", "")}'}))
                continue
            got = common.to_unit(common.read_raw(c["out"]))[0][..., :3]
            if got.shape != o["naive"].shape:
                out.append(dict(base, **{"pass": False, "reason": "shape", "got": list(got.shape),
                                         "expected": list(o["naive"].shape)}))
                continue
            de_naive = common.de_stats(common.de2000_srgb(got, o["naive"]))
            de_icc = common.de_stats(common.de2000_srgb(got, o["icc"]))
            inv = common.de_stats(common.de2000_srgb(got, o["alt"]))
            prim = de_icc if o["primary"] == "icc" else de_naive
            ok = prim["mean"] <= 2.0 and prim["p95"] <= 5.0
            out.append(dict(base, **{"pass": ok, "de2000_vs_naive": de_naive, "de2000_vs_icc": de_icc,
                                     "de2000_vs_opposite_inversion": inv}))
    from PIL import features
    common.write_result(args.out, "cmyk_jpeg", CRIT, out, {
        "oracle": f"Pillow {__import__('PIL').__version__} (libjpeg-turbo {features.version('jpg')}) CMYK samples; "
                  f"naive formula; LittleCMS {features.version('littlecms2')}",
        "default_cmyk_profile": os.path.basename(args.default_cmyk_icc)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
