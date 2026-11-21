#!/usr/bin/env python3
"""Test 1 (AVIF): compare AVIF decoder candidates with reference decoders.

Primary oracle : Pillow's AVIF plugin (bundled libavif, version recorded). It returns the stored pixels, reports
                 irot/imir as an EXIF orientation, and does not apply clap.
Secondary      : avifdec from Ubuntu's libavif-bin (1.0.4). Used as the reference only when Pillow cannot decode the
                 file. Agreement between the two oracles is reported per file (oracle_agreement).
Display        : files with irot/imir/clap are also given a display reference (stored pixels -> clap crop -> EXIF
                 orientation, the MIAF order). A browser shows the display form, so a candidate that returns the
                 stored pixels fails with class unsupported_feature:transform_not_applied.

Classes for failures: decode_error, unsupported_feature[:what], size_mismatch, pixel_diff.
"""
import argparse
import glob
import json
import os
import re
import struct
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

CRIT = ("decodes; same size as the reference (the display reference for irot/imir/clap files); mean |diff| <= 1.5 and "
        "<= 1% of pixels with any channel |diff| > 8 (8-bit scale). Tolerates the chroma-upsampling and YUV->RGB "
        "rounding differences between libavif versions/libyuv and the Rust converters. The strict numbers "
        "(mean <= 1.0, <= 1% of pixels > 3) are reported as strict_pass / strict_pass_rate")

SOURCE_EVIDENCE = {
    "grid": "mp4parse 0.17.0 src/lib.rs:296-312 lists Grid as unsupported and lib.rs:2801-2804 drops a grid primary "
            "item (image avif-native, decoder.rs:79 read_avif with ParseStrictness::Normal); avif-parse 2.1.0 "
            "src/lib.rs:930-931 returns Err(\"Grid-based AVIF collage is not supported\") (avif-decode).",
    "multilayer": "mp4parse 0.17.0 src/lib.rs:296-312: A1lx, A1op and Lsel (layered images) are unsupported features.",
    "transform": "No irot/imir/clap handling in image 0.25.10 src/codecs/avif/decoder.rs, avif-decode 3.0.0 or "
                 "avif-parse 2.1.0 (grep finds none); mp4parse 0.17.0 marks Clap unsupported (src/lib.rs:308). "
                 "The decoders return the stored pixels.",
    "animated": "Every candidate and both oracles decode only the first frame here; a failure is a first-frame difference.",
    "alpha": "The 64 link-u plum-blossom alpha files are rejected by both oracles (libavif BMFF parse failure) and so "
             "have no reference; see no_oracle for which candidates still decode them.",
}


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


def clap_rect(path, w, h):
    """libavif's crop rect from the first clap box: x = (W - cw)/2 + horizOff, y = (H - ch)/2 + vertOff."""
    d = open(path, "rb").read(1 << 20)
    i = d.find(b"clap")
    if i < 4:
        return None
    vals = struct.unpack(">8i", d[i + 4:i + 36])
    cwn, cwd, chn, chd, hon, hod, von, vod = vals
    if 0 in (cwd, chd, hod, vod):
        return None
    cw, ch = cwn / cwd, chn / chd
    x = (w - cw) / 2 + hon / hod
    y = (h - ch) / 2 + von / vod
    x, y, cw, ch = int(np.floor(x)), int(np.floor(y)), int(round(cw)), int(round(ch))
    if x < 0 or y < 0 or x + cw > w or y + ch > h or cw <= 0 or ch <= 0:
        return None
    return x, y, cw, ch


def pillow_ref(path):
    """Returns (stored RGBA float, display RGBA float or None, notes, partial variants) or raises."""
    from PIL import Image
    im = Image.open(path)
    im.seek(0)
    im.load()
    stored = im.convert("RGBA")
    orient = im.getexif().get(0x0112) or 1
    rect = clap_rect(path, stored.width, stored.height)
    T = Image.Transpose
    op = {2: T.FLIP_LEFT_RIGHT, 3: T.ROTATE_180, 4: T.FLIP_TOP_BOTTOM, 5: T.TRANSPOSE, 6: T.ROTATE_270,
          7: T.TRANSVERSE, 8: T.ROTATE_90}.get(orient)

    def crop(x):
        x0, y0, cw, ch = rect
        return x.crop((x0, y0, x0 + cw, y0 + ch))

    notes, partial = {}, {}
    disp = None
    if rect or op is not None:
        d = stored
        if rect:
            d = crop(d)
            notes["clap_crop"] = list(rect)
        if op is not None:
            d = d.transpose(op)
            notes["exif_orientation"] = orient
        disp = common.to_unit(np.asarray(d))[None]
        if rect and op is not None:
            partial["clap_not_applied"] = common.to_unit(np.asarray(stored.transpose(op)))[None]
            partial["orientation_not_applied"] = common.to_unit(np.asarray(crop(stored)))[None]
    return common.to_unit(np.asarray(stored))[None], disp, notes, partial


def avifdec_ref(path, ref_png):
    r = subprocess.run(["avifdec", "-d", "8", path, ref_png], capture_output=True, timeout=300)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).decode(errors="replace")[-300:]
    from PIL import Image
    return common.to_unit(np.asarray(Image.open(ref_png).convert("RGBA")))[None], None


def judge(got, exp):
    if got.shape != exp.shape:
        return None
    s = common.diff_stats(got, exp)
    d = np.abs(got - exp).max(axis=-1) * 255.0
    s["pct_gt8"] = round(100.0 * float((d > 8.0).mean()), 4)
    s["pass"] = s["mean_abs"] <= 1.5 and s["pct_gt8"] <= 1.0
    s["strict_pass"] = s["mean_abs"] <= 1.0 and s["pct_gt3"] <= 1.0
    return s


UNSUPPORTED_RE = re.compile(r"unsupported|not supported|grid|a1lx|a1op|lsel|layer", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--candidate", action="append", default=[], help="name=path-to-binary (missing file = build failed)")
    ap.add_argument("--build", action="append", default=[], help="name=step-outcome")
    args = ap.parse_args()
    from PIL import features
    work = os.path.abspath(args.work)
    os.makedirs(os.path.join(work, "ref"), exist_ok=True)
    ids = {os.path.relpath(f, args.data).replace(os.sep, "/"): f for f in corpus(args.data)}

    refs, oracle_rows, no_ref = {}, [], {}
    for rel, f in ids.items():
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", rel)
        p_stored = p_disp = p_err = None
        notes, partial = {}, {}
        try:
            p_stored, p_disp, notes, partial = pillow_ref(f)
        except Exception as e:  # noqa: BLE001
            p_err = f"{type(e).__name__}: {e}"[:200]
        try:
            a_img, a_err = avifdec_ref(f, os.path.join(work, "ref", safe + ".png"))
        except subprocess.TimeoutExpired:
            a_img, a_err = None, "avifdec timeout"
        except OSError as e:
            a_img, a_err = None, f"avifdec unavailable: {e}"
        row = {"id": rel, "pillow": "ok" if p_stored is not None else p_err, "avifdec": "ok" if a_img is not None else a_err}
        if p_stored is not None and a_img is not None:
            j = judge(a_img, p_stored)
            row["avifdec_vs_pillow"] = j if j else {"size": [list(a_img.shape), list(p_stored.shape)]}
        oracle_rows.append(row)
        if p_stored is not None:
            refs[rel] = {"stored": p_stored, "display": p_disp, "oracle": "pillow", "notes": notes, "avifdec": a_img,
                         "partial": partial}
        elif a_img is not None:
            refs[rel] = {"stored": a_img, "display": None, "oracle": "avifdec (Pillow could not decode)", "notes": {},
                         "avifdec": None, "partial": {}}
        else:
            no_ref[rel] = {"pillow": p_err, "avifdec": a_err}
    agree = [r for r in oracle_rows if isinstance(r.get("avifdec_vs_pillow"), dict) and "pass" in r["avifdec_vs_pillow"]]
    oracle_summary = {
        "files_both_decode": len(agree),
        "avifdec_agrees_tolerant": sum(1 for r in agree if r["avifdec_vs_pillow"]["pass"]),
        "avifdec_agrees_strict": sum(1 for r in agree if r["avifdec_vs_pillow"]["strict_pass"]),
        "size_disagreements": [r["id"] for r in oracle_rows if isinstance(r.get("avifdec_vs_pillow"), dict)
                               and "size" in r["avifdec_vs_pillow"]],
    }
    try:
        av = subprocess.run(["avifdec", "--version"], capture_output=True, text=True)
    except OSError:
        av = subprocess.CompletedProcess([], 1, "", "not installed")
    oracle_desc = {"primary": f"Pillow {__import__('PIL').__version__} AVIF plugin, libavif {features.version('avif')}",
                   "secondary": "avifdec " + " ".join((av.stdout or av.stderr).split())[:200]}

    builds = dict(b.split("=", 1) for b in args.build)
    summary = {"oracle": oracle_desc, "oracle_agreement": oracle_summary, "candidates": {}, "source_evidence": SOURCE_EVIDENCE}
    outputs = {}
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
        outputs[name] = {}
        results, per_tag, no_oracle, safety, classes = [], {}, [], {}, {}
        strict_pass = 0
        for c in cases:
            rel = c["id"]
            r = res.get(rel) or {"status": "missing", "message": ""}
            st = r["status"]
            if st not in ("ok", "err"):
                safety[st] = safety.get(st, 0) + 1
            tags = tags_for(rel)
            got = None
            if st == "ok":
                try:
                    got = common.to_unit(common.read_raw(c["out"]))[:1]
                    outputs[name][rel] = c["out"]
                except Exception as e:  # noqa: BLE001
                    st, r = "bad_output", {"message": str(e)}
            if rel not in refs:
                no_oracle.append({"id": rel, "oracles": no_ref.get(rel), "candidate": st, "message": r.get("message", "")})
                continue
            ref = refs[rel]
            case = {"id": rel, "tags": tags, "oracle": ref["oracle"], **({"transform": ref["notes"]} if ref["notes"] else {})}
            if got is None:
                msg = r.get("message", "")
                case.update({"pass": False, "class": "unsupported_feature" if UNSUPPORTED_RE.search(msg) else "decode_error",
                             "error": f"{st}: {msg}"})
            else:
                target = ref["display"] if ref["display"] is not None else ref["stored"]
                j = judge(got, target)
                if j and j["pass"]:
                    case.update(j)
                    case["class"] = "ok"
                elif ref["display"] is not None and (js := judge(got, ref["stored"])) and js["pass"]:
                    case.update({"pass": False, "class": "unsupported_feature:transform_not_applied",
                                 "matches_stored_pixels": js})
                elif any((jp := judge(got, v)) and jp["pass"] for v in ref["partial"].values()):
                    which = next(k for k, v in ref["partial"].items() if (jp := judge(got, v)) and jp["pass"])
                    case.update({"pass": False, "class": "unsupported_feature:" + which})
                elif j is None:
                    case.update({"pass": False, "class": "size_mismatch", "got": list(got.shape), "expected": list(target.shape)})
                else:
                    case.update(j)
                    case["class"] = "pixel_diff"
                if ref.get("avifdec") is not None and ref["display"] is None:
                    ja = judge(got, ref["avifdec"])
                    if ja:
                        case["vs_avifdec"] = {k: ja[k] for k in ("mean_abs", "pct_gt3", "pct_gt8", "pass", "strict_pass")}
            strict_pass += int(bool(case.get("strict_pass")))
            classes[case["class"]] = classes.get(case["class"], 0) + 1
            results.append(case)
            for t in tags:
                pt = per_tag.setdefault(t, {"pass": 0, "total": 0, "classes": {}})
                pt["total"] += 1
                pt["pass"] += int(case["pass"])
                pt["classes"][case["class"]] = pt["classes"].get(case["class"], 0) + 1
        zero = {t: {"classes": v["classes"], "files": [c["id"] for c in results if t in c["tags"]][:12],
                    "source_evidence": SOURCE_EVIDENCE.get(t)}
                for t, v in per_tag.items() if v["pass"] == 0}
        doc = common.write_result(os.path.join(args.results, f"avif_{name}.json"), f"avif_{name}", CRIT, results,
                                  {"candidate": info, "per_tag": per_tag, "failure_classes": classes,
                                   "strict_pass": strict_pass,
                                   "strict_pass_rate": strict_pass / len(results) if results else None,
                                   "zero_pass_tags": zero, "no_oracle": no_oracle, "safety_failures": safety,
                                   "oracle": oracle_desc,
                                   "cases": [{k: c.get(k) for k in ("id", "pass", "class", "mean_abs", "pct_gt3", "pct_gt8")}
                                             for c in results]})
        info.update({"status": "ran", "pass": doc["pass"], "total": doc["total"], "pass_rate": doc["pass_rate"],
                     "strict_pass": strict_pass, "failure_classes": classes, "safety_failures": safety})
        summary["candidates"][name] = info

    # pairwise agreement between candidates on every file both decode
    names = sorted(outputs)
    pairs = {}
    for i in range(len(names)):
        for k in range(i + 1, len(names)):
            a, b = names[i], names[k]
            both = sorted(set(outputs[a]) & set(outputs[b]))
            n_same, n_size, rows = 0, 0, []
            for rel in both:
                ga = common.to_unit(common.read_raw(outputs[a][rel]))[:1]
                gb = common.to_unit(common.read_raw(outputs[b][rel]))[:1]
                j = judge(ga, gb)
                if j is None:
                    n_size += 1
                    rows.append({"id": rel, "size": [list(ga.shape), list(gb.shape)]})
                elif j["pass"]:
                    n_same += 1
                else:
                    rows.append({"id": rel, "mean_abs": j["mean_abs"], "pct_gt8": j["pct_gt8"]})
            pairs[f"{a}~{b}"] = {"both_decoded": len(both), "agree_tolerant": n_same, "size_mismatch": n_size,
                                 "first_disagreements": rows[:20]}
    summary["pairwise_agreement"] = pairs
    summary["corpus_files"] = len(ids)
    summary["no_reference"] = no_ref
    summary["oracle_rows"] = oracle_rows
    with open(os.path.join(args.results, "avif_candidates.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, default=common._json_default)
    return 0


if __name__ == "__main__":
    sys.exit(main())
