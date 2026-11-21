#!/usr/bin/env python3
"""Test 4: ICC colour management to sRGB, pure-Rust CMS candidates vs LittleCMS (Pillow ImageCms).

Candidates (crates/icc): moxcms 0.8.1 (raikiri's CMS) and qcms 0.3.0 (Firefox's CMS), each converting identical
8-bit device values with a profile to sRGB (relative colorimetric, falling back like raikiri does).
Oracle: LittleCMS through Pillow ImageCms, relative colorimetric, built-in sRGB output profile, no BPC.
raikiri pipeline: images embedding the profile (PNG iCCP, JPEG APP2, WebP ICCP) decoded with raikiri-net
ImageResolver, which converts only RGB profiles (raikiri-traits image.rs:178-233).
"""
import argparse
import glob
import io
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

CRIT = "mean deltaE2000 <= 1.0 and p95 <= 2.0 vs LittleCMS (sRGB, D65 Lab)"
MODES = {"RGB": ("RGB", 3), "GRAY": ("L", 1), "CMYK": ("CMYK", 4)}


def grid(n, ch):
    lv = np.round(np.linspace(0, 255, n)).astype(np.uint8)
    mesh = np.stack(np.meshgrid(*([lv] * ch), indexing="ij"), -1).reshape(-1, ch)
    side = n ** (ch // 2)
    return mesh.reshape(side, -1, ch)


def discover(dirs):
    from PIL import ImageCms
    out = []
    seen = set()
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "*.icc")) + glob.glob(os.path.join(d, "*.icm"))):
            try:
                p = ImageCms.getOpenProfile(f).profile
            except Exception:  # noqa: BLE001
                continue
            cs = p.xcolor_space.strip()
            if cs not in MODES or p.device_class not in ("mntr", "scnr", "prtr", "spac"):
                continue
            key = (os.path.basename(f), os.path.getsize(f))
            if key in seen:
                continue
            seen.add(key)
            out.append({"path": f, "name": os.path.basename(os.path.dirname(f)) + "/" + os.path.basename(f), "cs": cs,
                        "version": p.version, "class": p.device_class})
    return out


def lcms(arr, mode, profile_path):
    from PIL import Image, ImageCms
    h, w = arr.shape[:2]
    im = Image.frombytes(mode, (w, h), np.ascontiguousarray(arr).tobytes())
    src = ImageCms.getOpenProfile(profile_path)
    t = ImageCms.buildTransform(src, ImageCms.createProfile("sRGB"), mode, "RGB",
                                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
    return np.asarray(ImageCms.applyTransform(im, t)).astype(np.float64) / 255.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--icc", required=True, help="crates/icc binary")
    ap.add_argument("--rkpipe", required=True)
    ap.add_argument("--profile-dir", action="append", default=[])
    args = ap.parse_args()
    from PIL import Image, ImageCms, features
    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    photo = np.asarray(Image.open(os.path.join(args.data, "libjpeg-turbo", "testimages", "testorig.ppm")).convert("RGB"))
    photo_l = np.asarray(Image.open(os.path.join(args.data, "libjpeg-turbo", "testimages", "testorig.ppm")).convert("L"))[..., None]
    inputs = {"RGB": {"grid17": grid(17, 3), "photo": photo},
              "GRAY": {"ramp256": np.arange(256, dtype=np.uint8).reshape(16, 16, 1), "photo": photo_l},
              "CMYK": {"grid9": grid(9, 4)}}
    raw_paths = {}
    for cs, d in inputs.items():
        for k, a in d.items():
            p = os.path.join(work, f"in_{cs}_{k}.raw")
            common.write_raw(p, a)
            raw_paths[(cs, k)] = p
    dirs = [os.path.join(args.data, "compact-icc", "profiles"), os.path.join(args.data, "libjpeg-turbo", "testimages")]
    profiles = discover(dirs + args.profile_dir)
    oracle, no_oracle = {}, []
    for pr in profiles:
        mode = MODES[pr["cs"]][0]
        for k, a in inputs[pr["cs"]].items():
            try:
                oracle[(pr["name"], k)] = lcms(a, mode, pr["path"])
            except Exception as e:  # noqa: BLE001
                no_oracle.append({"profile": pr["name"], "input": k, "error": str(e)[:200]})
    for cand in ("moxcms", "qcms"):
        cases, meta = [], {}
        for pr in profiles:
            for k in inputs[pr["cs"]]:
                if (pr["name"], k) not in oracle:
                    continue
                cid = f'{pr["name"]}|{k}'
                out = os.path.join(work, cand, cid.replace("/", "_").replace("|", "__") + ".raw")
                cases.append({"id": cid, "input": raw_paths[(pr["cs"], k)], "out": out,
                              "args": [pr["path"], "relative"]})
                meta[cid] = (pr, k, out)
        os.makedirs(os.path.join(work, cand), exist_ok=True)
        res = common.run_batch(args.icc, cand, cases, os.path.join(work, f"{cand}_manifest.json"),
                               os.path.join(work, f"{cand}_batch.json"))
        results, per_cs = [], {}
        for cid, (pr, k, out) in meta.items():
            r = res.get(cid) or {"status": "missing"}
            case = {"id": cid, "profile": pr["name"], "colour_space": pr["cs"], "icc_version": pr["version"],
                    "class": pr["class"], "input": k}
            if r["status"] != "ok":
                case.update({"pass": False, "error": f'{r["status"]}: {r.get("message", "")}'})
            else:
                got = common.to_unit(common.read_raw(out))[0]
                de = common.de_stats(common.de2000_srgb(got, oracle[(pr["name"], k)]))
                case.update({"pass": de["mean"] <= 1.0 and de["p95"] <= 2.0, "de2000": de,
                             "intent_used": r.get("message", "").replace("intent=", "") or None})
            results.append(case)
            pc = per_cs.setdefault(pr["cs"], {"pass": 0, "total": 0})
            pc["total"] += 1
            pc["pass"] += int(case["pass"])
        licence = {"moxcms": "BSD-3-Clause OR Apache-2.0", "qcms": "MIT"}[cand]
        version = {"moxcms": "0.8.1", "qcms": "0.3.0"}[cand]
        common.write_result(os.path.join(args.results, f"icc_{cand}.json"), f"icc_{cand}", CRIT, results,
                            {"candidate": f"{cand} {version}", "licence": licence, "per_colour_space": per_cs,
                             "oracle": f"LittleCMS {features.version('littlecms2')} via Pillow {__import__('PIL').__version__}",
                             "profiles": len(profiles), "no_oracle": no_oracle})
    # ---- raikiri pipeline with embedded profiles ----
    emb, emb_meta = [], {}
    rgb_img = grid(17, 3)
    gray_img = np.arange(256, dtype=np.uint8).reshape(16, 16, 1)
    for pr in profiles:
        if pr["cs"] not in ("RGB", "GRAY"):
            continue
        icc = open(pr["path"], "rb").read()
        mode = MODES[pr["cs"]][0]
        a = rgb_img if pr["cs"] == "RGB" else gray_img
        h, w = a.shape[:2]
        im = Image.frombytes(mode, (w, h), np.ascontiguousarray(a).tobytes())
        fmts = [("png", {}), ("jpg", {"quality": 100, "subsampling": 0})]
        if pr["cs"] == "RGB":
            fmts.append(("webp", {"lossless": True}))
        for ext, kw in fmts:
            p = os.path.join(work, "embedded", pr["name"].replace("/", "_") + "." + ext)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            im.save(p, icc_profile=icc, **kw)
            stored = Image.open(p)
            stored.load()
            if stored.info.get("icc_profile") != icc:
                continue
            arr = np.asarray(stored.convert(mode))
            if arr.ndim == 2:
                arr = arr[..., None]
            cid = f'{pr["name"]}|{ext}'
            try:
                exp = lcms(arr, mode, pr["path"])
            except Exception:  # noqa: BLE001
                continue
            emb.append({"id": cid, "input": p, "out": p + ".raw", "args": []})
            emb_meta[cid] = (pr, ext, exp)
    real = sorted(glob.glob(os.path.join(args.data, "icc-real", "*.jpg")))
    for f in real:
        im = Image.open(f)
        icc = im.info.get("icc_profile")
        if not icc:
            continue
        exp = np.asarray(ImageCms.profileToProfile(im.convert("RGB"), ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                                   ImageCms.createProfile("sRGB"),
                                                   renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                                                   outputMode="RGB")).astype(np.float64) / 255.0
        cid = "real|" + os.path.basename(f)
        emb.append({"id": cid, "input": f, "out": os.path.join(work, os.path.basename(f) + ".raw"), "args": []})
        emb_meta[cid] = ({"name": os.path.basename(f), "cs": "RGB"}, "jpg", exp)
    res = common.run_batch(args.rkpipe, "decode", emb, os.path.join(work, "rk_manifest.json"),
                           os.path.join(work, "rk_batch.json"))
    results = []
    for c in emb:
        pr, ext, exp = emb_meta[c["id"]]
        r = res.get(c["id"]) or {"status": "missing"}
        case = {"id": c["id"], "profile": pr["name"], "colour_space": pr["cs"], "container": ext}
        if r["status"] != "ok":
            case.update({"pass": False, "error": f'{r["status"]}: {r.get("message", "")}'})
        else:
            got = common.to_unit(common.read_raw(c["out"]))[0][..., :3]
            if got.shape != exp.shape:
                case.update({"pass": False, "reason": "shape"})
            else:
                de = common.de_stats(common.de2000_srgb(got, exp))
                case.update({"pass": de["mean"] <= 1.0 and de["p95"] <= 2.0, "de2000": de})
        results.append(case)
    common.write_result(os.path.join(args.results, "icc_raikiri.json"), "icc_raikiri", CRIT, results,
                        {"pipeline": "raikiri-net ImageResolver (a570d903): image icc_profile() + raikiri_traits::image::"
                                     "convert_rgba8_to_srgb (moxcms, RGB profiles only, 8-bit, after into_rgba8)"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
