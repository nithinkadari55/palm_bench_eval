#!/usr/bin/env python3
"""Test 1 (robustness): invalid / corrupt images must give Err, never panic, crash or hang.

Every case runs in its own child process (p3common batch) with a timeout; the workflow step sets
`ulimit -v` so the parent and every child share the address-space limit.
"""
import argparse
import glob
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

SAFE = {"ok", "err"}


def seeds(data, work):
    s = {"png": [], "jpeg": [], "gif": [], "webp": [], "avif": []}
    png = sorted(f for f in glob.glob(os.path.join(data, "pngsuite", "*.png")) if not os.path.basename(f).startswith("x"))
    s["png"] = png[::6]
    jt = os.path.join(data, "libjpeg-turbo", "testimages")
    s["jpeg"] = [os.path.join(jt, n) for n in ("testorig.jpg", "testimgint.jpg", "testimgari.jpg", "monkey12.jpg")]
    s["jpeg"] += sorted(glob.glob(os.path.join(data, "exif-orientation", "Landscape_6.jpg")))
    s["jpeg"] += sorted(glob.glob(os.path.join(data, "cmyk-jpeg", "mozilla_jpg-cmyk-1.jpg")))
    try:
        from PIL import Image
        prog = os.path.join(work, "seed_progressive.jpg")
        Image.open(os.path.join(jt, "testorig.ppm")).save(prog, quality=80, progressive=True)
        s["jpeg"].append(prog)
    except Exception as e:  # noqa: BLE001
        print("progressive seed:", e, file=sys.stderr)
    w = os.path.join(data, "libwebp-test-data")
    s["webp"] = [os.path.join(w, n) for n in ("test.webp", "lossless1.webp", "lossy_alpha1.webp", "lossless_vec_1_0.webp",
                                              "alpha_filter_2_method_1.webp", "vp80-00-comprehensive-007.webp",
                                              "near_lossless_75.webp", "bug3.webp")]
    g = os.path.join(data, "pygif", "test-suite")
    s["gif"] = [os.path.join(g, n + ".gif") for n in ("four-colors", "interlace", "animation", "high-color",
                                                       "dispose-restore-previous", "large-codes", "max-codes")]
    s["gif"] += sorted(glob.glob(os.path.join(data, "image-gif", "tests", "samples", "sample_1.gif")))
    lu = os.path.join(data, "avif-link-u")
    s["avif"] = [os.path.join(lu, n) for n in ("hato.profile0.8bpc.yuv420.avif", "hato.profile2.10bpc.yuv422.avif",
                                               "plum-blossom-small.profile0.8bpc.yuv420.alpha-full.avif",
                                               "fox.profile1.8bpc.yuv444.avif", "star-8bpc.avifs")]
    s["avif"] += sorted(glob.glob(os.path.join(data, "av1-avif", "testFiles", "Microsoft", "Monochrome.avif")))
    s["avif"] += sorted(glob.glob(os.path.join(data, "av1-avif", "testFiles", "Microsoft", "still_picture.avif")))
    for k in s:
        s[k] = [f for f in s[k] if os.path.exists(f)]
    return s


MAGIC = {"png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff\xe0", "gif": b"GIF89a",
         "webp": b"RIFF\x00\x10\x00\x00WEBPVP8 ", "avif": b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00avifmif1"}


def mutate(fmt, path, outdir):
    data = open(path, "rb").read()
    base = os.path.basename(path)
    rng = random.Random(f"{fmt}:{base}")
    cases = []

    def emit(cat, tag, blob, expect):
        p = os.path.join(outdir, f"{fmt}.{base}.{tag}.bin")
        with open(p, "wb") as fh:
            fh.write(blob)
        cases.append({"fmt": fmt, "category": cat, "seed": base, "mutation": tag, "path": p, "expect_err": expect})

    n = len(data)
    cuts = sorted({8, 16, 33, 64} | {int(n * f) for f in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99)})
    for c in cuts:
        if 0 < c < n:
            emit("truncated", f"trunc{c}", data[:c], True)
    for i in range(12):
        b = bytearray(data)
        p = rng.randrange(n)
        bit = rng.randrange(8)
        b[p] ^= 1 << bit
        emit("bit_flip", f"flip{p}.{bit}", bytes(b), False)
    for i in range(6):
        b = bytearray(data)
        p = rng.randrange(min(n, 64))
        bit = rng.randrange(8)
        b[p] ^= 1 << bit
        emit("header_bit_flip", f"hflip{p}.{bit}", bytes(b), False)
    for i in range(4):
        b = bytearray(data)
        p = rng.randrange(max(1, n - 16))
        for j in range(16):
            if p + j < n:
                b[p + j] = rng.randrange(256)
        emit("byte_burst", f"burst{p}", bytes(b), False)
    return cases


def garbage(fmt, outdir, count=12):
    rng = random.Random("garbage:" + fmt)
    out = []
    for i in range(count):
        size = rng.choice([1, 7, 100, 1000, 20000])
        blob = MAGIC[fmt] + bytes(rng.randrange(256) for _ in range(size))
        p = os.path.join(outdir, f"{fmt}.garbage{i}.bin")
        with open(p, "wb") as fh:
            fh.write(blob)
        out.append({"fmt": fmt, "category": "garbage_with_magic", "seed": "-", "mutation": f"garbage{i}", "path": p,
                    "expect_err": True})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--decoder", action="append", default=[],
                    help="name=binary=subcommand=formats(comma list), e.g. raster=/x/raster=decode=png,jpeg,gif,webp")
    ap.add_argument("--timeout-ms", type=int, default=20000)
    args = ap.parse_args()
    work = os.path.abspath(args.work)
    mut = os.path.join(work, "mutations")
    os.makedirs(mut, exist_ok=True)
    allcases = []
    for f in sorted(glob.glob(os.path.join(args.data, "pngsuite", "x*.png"))):
        allcases.append({"fmt": "png", "category": "pngsuite_x_corrupt", "seed": os.path.basename(f), "mutation": "official",
                         "path": f, "expect_err": True})
    for fmt, files in seeds(args.data, work).items():
        for f in files:
            allcases += mutate(fmt, f, mut)
        allcases += garbage(fmt, mut)
    for i, c in enumerate(allcases):
        c["id"] = f"{i:05d}"
    decoders, results, failures = {}, [], []
    for spec in args.decoder:
        name, binp, sub, fmts = spec.split("=", 3)
        fmts = set(fmts.split(","))
        if not os.path.exists(binp):
            decoders[name] = {"status": "not built"}
            continue
        cases = [c for c in allcases if c["fmt"] in fmts]
        batch = [{"id": c["id"], "input": c["path"], "out": "-", "args": []} for c in cases]
        res = common.run_batch(binp, sub, batch, os.path.join(work, f"{name}_manifest.json"),
                               os.path.join(work, f"{name}_batch.json"), timeout_ms=args.timeout_ms)
        d = {"status": "ran", "subcommand": sub, "formats": sorted(fmts), "total": 0, "safety_pass": 0,
             "strict_total": 0, "strict_err": 0, "by_category": {}, "by_status": {}}
        for c in cases:
            r = res.get(c["id"]) or {"status": "missing", "message": ""}
            st = r["status"]
            safe = st in SAFE
            d["total"] += 1
            d["safety_pass"] += int(safe)
            d["by_status"][st] = d["by_status"].get(st, 0) + 1
            cat = d["by_category"].setdefault(f'{c["fmt"]}/{c["category"]}', {})
            cat[st] = cat.get(st, 0) + 1
            if c["expect_err"]:
                d["strict_total"] += 1
                d["strict_err"] += int(st == "err")
            case = {"id": f'{name}:{c["fmt"]}:{c["seed"]}:{c["mutation"]}', "pass": safe, "decoder": name,
                    "category": c["category"], "status": st, "ms": round(r.get("ms", 0), 1)}
            if not safe:
                case["message"] = r.get("message", "")
                failures.append(case)
            results.append(case)
        d["strict_err_rate"] = d["strict_err"] / d["strict_total"] if d["strict_total"] else None
        decoders[name] = d
    common.write_result(args.out, "robustness",
                        "every case returns ok or Err in its child process: no panic, abort/signal, timeout "
                        f"({args.timeout_ms} ms) or other exit, under the step's ulimit -v. "
                        "strict_err_rate = share of must-fail inputs (PngSuite x*, truncations, random data with magic) "
                        "that returned Err (lenient partial decodes count as ok, not as safety failures)",
                        results, {"decoders": decoders, "cases_per_decoder_formats": len(allcases)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
