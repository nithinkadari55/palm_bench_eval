#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

SKIP_RAW = {"glyf", "loca", "hmtx", "head", "DSIG"}


def h(obj):
    return hashlib.sha1(repr(obj).encode("utf-8")).hexdigest()


def signature(path):
    f = TTFont(path, lazy=False, recalcBBoxes=False, recalcTimestamp=False)
    tags = sorted(f.reader.keys())
    sig = {"tables": tags}
    order = f.getGlyphOrder()
    outlines = {}
    if any(t in f for t in ("glyf", "CFF ", "CFF2")):
        gs = f.getGlyphSet()
        glyf = f["glyf"] if "glyf" in f else None
        for name in order:
            pen = RecordingPen()
            gs[name].draw(pen)
            item = [pen.value]
            if glyf is not None:
                g = glyf[name]
                prog = g.program.getBytecode() if hasattr(g, "program") else b""
                item.append(bytes(prog))
            outlines[name] = h(item)
    sig["outlines"] = outlines
    cm = {}
    if "cmap" in f:
        for t in f["cmap"].tables:
            key = f"{t.platformID}/{t.platEncID}/{t.format}"
            cm[key] = h((sorted(t.cmap.items()) if t.cmap else [], sorted((getattr(t, "uvsDict", None) or {}).items())))
    sig["cmap"] = cm
    sig["hmtx"] = h(sorted(f["hmtx"].metrics.items())) if "hmtx" in f else None
    head = {}
    if "head" in f:
        hd = f["head"]
        for k, v in sorted(vars(hd).items()):
            if k in ("checkSumAdjustment", "tableTag"):
                continue
            if k == "flags":
                v = v & ~0x0800
            head[k] = v
    sig["head"] = h(head)
    sig["raw"] = {t: hashlib.sha1(f.reader[t]).hexdigest() for t in tags if t not in SKIP_RAW}
    f.close()
    return sig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--wuff", required=True)
    ap.add_argument("--robustness", required=False)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    manifest = json.load(open(args.manifest, encoding="utf-8"))
    wuff = json.load(open(args.wuff, encoding="utf-8"))
    fonts = {f["id"]: f for f in manifest["fonts"]}
    orig_sigs = {}
    items = []
    for r in wuff["results"]:
        font = fonts[r["font_id"]]
        rec = {"id": r["id"], "font_id": r["font_id"], "kind": r["kind"], "outline": font["outline"],
               "variable": font["variable"], "num_glyphs": font["num_glyphs"], "wuff_status": r["status"],
               "decode_ms": r["decode_ms"]}
        if r["status"] != "ok":
            rec["pass"] = False
            rec["reason"] = f"wuff decode status {r['status']}"
            items.append(rec)
            continue
        try:
            if r["font_id"] not in orig_sigs:
                orig_sigs[r["font_id"]] = signature(font["original"])
            o = orig_sigs[r["font_id"]]
            d = signature(r["decoded"])
        except Exception as e:
            rec["pass"] = False
            rec["reason"] = f"fontTools failed to parse: {e!r}"[:500]
            items.append(rec)
            continue
        allowed_missing = {"DSIG"} if r["kind"].startswith("woff2") else set()
        missing = sorted(set(o["tables"]) - set(d["tables"]) - allowed_missing)
        extra = sorted(set(d["tables"]) - set(o["tables"]))
        mism = [n for n in o["outlines"] if o["outlines"][n] != d["outlines"].get(n)]
        mism += [n for n in d["outlines"] if n not in o["outlines"]]
        raw_diff = sorted(t for t in o["raw"] if t in d["raw"] and o["raw"][t] != d["raw"][t])
        rec.update({
            "table_set_equal": not missing and not extra,
            "missing_tables": missing,
            "extra_tables": extra,
            "dropped_dsig": "DSIG" in o["tables"] and "DSIG" not in d["tables"],
            "glyphs_compared": len(o["outlines"]),
            "outlines_equal": not mism,
            "outline_mismatch_count": len(mism),
            "outline_mismatch_examples": mism[:5],
            "cmap_equal": o["cmap"] == d["cmap"],
            "hmtx_equal": o["hmtx"] == d["hmtx"],
            "head_equal_except_checksum_and_flag11": o["head"] == d["head"],
            "other_tables_byte_identical": not raw_diff,
            "other_tables_differing": raw_diff,
        })
        rec["pass"] = rec["table_set_equal"] and rec["outlines_equal"] and rec["cmap_equal"] and rec["hmtx_equal"]
        items.append(rec)
        print(f"{rec['id']}: pass={rec['pass']}")
    passed = sum(1 for i in items if i["pass"])
    failures = [i for i in items if not i["pass"]][:20]
    robustness = None
    if args.robustness:
        try:
            rb = json.load(open(args.robustness, encoding="utf-8"))
            robustness = {k: rb.get(k) for k in ("pass", "fail", "total", "pass_rate", "safety_failures", "safety_pass_rate", "by_category")}
        except Exception as e:
            robustness = {"error": repr(e)}
    result = {
        "test": "woff",
        "wuff_version": wuff.get("wuff_version"),
        "fonttools_version": manifest.get("fonttools"),
        "pass": passed,
        "fail": len(items) - passed,
        "total": len(items),
        "pass_rate": passed / len(items) if items else 0.0,
        "pass_criterion": "wuff decodes the fontTools-encoded WOFF/WOFF2 and, compared with the original via fontTools: same table set (DSIG may be dropped for WOFF2, as fontTools' encoder always drops it), identical RecordingPen outlines (plus TrueType instructions) for every glyph at the default location, identical cmap subtables and identical hmtx",
        "fonts": len(manifest["fonts"]),
        "fonts_missing": manifest.get("missing"),
        "encode_errors": manifest.get("errors"),
        "has_cff": manifest.get("has_cff"),
        "has_variable": manifest.get("has_variable"),
        "by_kind": {k: {"pass": sum(1 for i in items if i["kind"] == k and i["pass"]), "total": sum(1 for i in items if i["kind"] == k)} for k in sorted({i["kind"] for i in items})},
        "robustness_summary": robustness,
        "items": items,
        "first_failures": failures,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    print(f"woff roundtrip: {passed}/{len(items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
