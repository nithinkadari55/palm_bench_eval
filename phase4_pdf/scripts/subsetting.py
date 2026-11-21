#!/usr/bin/env python3
"""Font subsetting effectiveness: embedded font program bytes and glyph counts vs the original font face."""
import argparse
import io
import json
import os

import pikepdf
from fontTools.cffLib import CFFFontSet
from fontTools.ttLib import TTFont

TARGETS = [("text", "none"), ("text_emoji", "none"), ("text", "a2b"), ("text", "pdf20"), ("pages_100", "none"), ("structure", "ua1")]


def face_bytes(path, index):
    f = TTFont(path, fontNumber=index, lazy=True) if path.lower().endswith(".ttc") else TTFont(path, lazy=True)
    return sum(e.length for e in f.reader.tables.values())


def glyphs_in_program(data, kind):
    try:
        if kind == "CIDFontType0C" or kind == "Type1C":
            c = CFFFontSet()
            c.decompile(io.BytesIO(data), None)
            return len(c[c.fontNames[0]].CharStrings)
        return TTFont(io.BytesIO(data), lazy=True)["maxp"].numGlyphs
    except Exception as e:
        return f"unparsed: {e!r}"[:120]


def fonts_of(pdf):
    seen = {}
    for pi, page in enumerate(pdf.pages):
        res = page.obj.get("/Resources", {})
        for name, f in res.get("/Font", {}).items():
            if f.objgen in seen:
                continue
            seen[f.objgen] = f
    return list(seen.values())


def describe(f):
    sub = str(f.get("/Subtype"))
    d = {"subtype": sub, "base_font": str(f.get("/BaseFont", ""))[1:] or None}
    if sub == "/Type3":
        procs = f.get("/CharProcs", {})
        d["glyphs"] = len(procs)
        d["embedded_bytes"] = sum(len(p.read_bytes()) for _, p in procs.items())
        xo = f.get("/Resources", {}).get("/XObject", {})
        d["xobject_bytes"] = sum(len(x.read_raw_bytes()) for _, x in xo.items())
        return d
    desc_font = f["/DescendantFonts"][0] if sub == "/Type0" else f
    fd = desc_font.get("/FontDescriptor")
    if fd is None:
        d["error"] = "no FontDescriptor"
        return d
    for key in ("/FontFile2", "/FontFile3", "/FontFile"):
        if key in fd:
            s = fd[key]
            data = s.read_bytes()
            kind = str(s.get("/Subtype", key))[1:]
            d.update({"program": key[1:], "program_subtype": kind, "embedded_bytes": len(data), "compressed_bytes": len(s.read_raw_bytes()),
                      "glyphs": glyphs_in_program(data, kind)})
            break
    else:
        d["error"] = "font program not embedded"
    if "/CIDSet" in fd:
        d["has_cidset"] = True
    return d


def match_original(base_font, manifest):
    if not base_font:
        return None, None
    ps = base_font.split("+", 1)[-1]
    best = None
    for role, info in manifest["fonts"].items():
        pn = info.get("postscript_name") or ""
        if pn and (ps == pn or ps.startswith(pn) or pn.startswith(ps)):
            if best is None or len(pn) > len(best[1].get("postscript_name") or ""):
                best = (role, info)
    return best if best else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    manifest = json.load(open(args.manifest, encoding="utf-8"))
    gen = json.load(open(os.path.join(args.corpus, "generation.json"), encoding="utf-8"))
    fid = {p["id"]: p["file_id"] for p in gen["profiles"]}
    rows = []
    for fx, pr in TARGETS:
        path = os.path.join(args.corpus, fx, fid.get(pr, pr) + ".pdf")
        if not os.path.exists(path):
            rows.append({"fixture": fx, "profile": pr, "error": "not generated"})
            continue
        with pikepdf.open(path) as pdf:
            for f in fonts_of(pdf):
                d = describe(f)
                d.update({"fixture": fx, "profile": pr})
                role, info = match_original(d.get("base_font"), manifest)
                if info:
                    d["role"] = role
                    d["original_file_bytes"] = info["bytes"]
                    d["original_face_bytes"] = face_bytes(info["path"], info["index"])
                    d["original_glyphs"] = info["num_glyphs"]
                    if isinstance(d.get("embedded_bytes"), int):
                        d["ratio_vs_face"] = d["embedded_bytes"] / d["original_face_bytes"]
                rows.append(d)
    judged = [r for r in rows if "ratio_vs_face" in r]
    passed = sum(r["ratio_vs_face"] < 1.0 for r in judged)
    result = {
        "test": f"subsetting_{args.label}",
        "pass": passed, "fail": len(judged) - passed, "total": len(judged),
        "pass_rate": passed / len(judged) if judged else None,
        "pass_criterion": "every embedded TrueType/CFF font program is smaller than the original font face it came from (Type3 colour-emoji fonts are reported, not judged)",
        "summary": {
            "median_ratio": sorted(r["ratio_vs_face"] for r in judged)[len(judged) // 2] if judged else None,
            "embedded_bytes_total": sum(r.get("embedded_bytes") or 0 for r in rows if isinstance(r.get("embedded_bytes"), int)),
            "unembedded": [r for r in rows if r.get("error")],
        },
        "rows": rows,
        "first_failures": [r for r in judged if r["ratio_vs_face"] >= 1.0][:20],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, default=str)
    print(f"subsetting: {passed}/{len(judged)} programs smaller than the original face")


if __name__ == "__main__":
    main()
