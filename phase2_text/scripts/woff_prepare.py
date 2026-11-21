#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import sys

from fontTools.ttLib import TTFont
from fontTools.ttLib import woff2

FONT_DIRS = ["/usr/share/fonts"]
SELECTION = [
    "DejaVuSans.ttf", "DejaVuSerif.ttf", "DejaVuSansMono.ttf", "DejaVuSans-Bold.ttf",
    "LiberationSans-Regular.ttf", "LiberationSerif-Regular.ttf", "LiberationMono-Regular.ttf", "LiberationSans-BoldItalic.ttf",
    "NotoSans-Regular.ttf", "NotoSerif-Regular.ttf", "NotoNaskhArabic-Regular.ttf", "NotoNastaliqUrdu-Regular.ttf",
    "NotoSansDevanagari-Regular.ttf", "NotoSansBengali-Regular.ttf", "NotoSansTamil-Regular.ttf", "NotoSansThai-Regular.ttf",
    "NotoSansKhmer-Regular.ttf", "NotoSansMyanmar-Regular.ttf", "NotoSansHebrew-Regular.ttf", "NotoSansMath-Regular.ttf",
    "NotoSansSymbols-Regular.ttf", "NotoColorEmoji.ttf",
    "NotoSansCJK-Regular.ttc",
    "Cantarell-Regular.otf", "Inter-Regular.otf", "NimbusSans-Regular.otf", "NimbusRoman-Regular.otf",
    "C059-Roman.otf", "NimbusMonoPS-Regular.otf", "URWBookman-Light.otf",
    "InterVariable.ttf",
]


def find(basename):
    for d in FONT_DIRS:
        for root, _, files in os.walk(d):
            if basename in files:
                return os.path.join(root, basename)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    fonts, encoded, missing, errors = [], [], [], []
    for basename in SELECTION:
        path = find(basename)
        if not path:
            missing.append(basename)
            continue
        stem = os.path.splitext(basename)[0]
        try:
            if path.endswith(".ttc"):
                f = TTFont(path, fontNumber=0, lazy=False, recalcBBoxes=False, recalcTimestamp=False)
                ext = ".otf" if "CFF " in f else ".ttf"
                orig = os.path.join(args.work, stem + "-face0" + ext)
                f.save(orig, reorderTables=False)
                f.close()
                source_note = f"{path} face 0 extracted with fontTools"
            else:
                orig = os.path.join(args.work, basename)
                shutil.copyfile(path, orig)
                source_note = path
            f = TTFont(orig, lazy=True)
            outline = "glyf" if "glyf" in f else ("CFF2" if "CFF2" in f else ("CFF " if "CFF " in f else "none"))
            variable = "fvar" in f
            num_glyphs = f["maxp"].numGlyphs
            f.close()
            fid = stem
            fonts.append({"id": fid, "original": orig, "source": source_note, "outline": outline,
                          "variable": variable, "num_glyphs": num_glyphs, "size": os.path.getsize(orig)})
            w1 = os.path.join(args.work, fid + ".woff")
            ft = TTFont(orig, recalcBBoxes=False, recalcTimestamp=False)
            ft.flavor = "woff"
            ft.save(w1, reorderTables=False)
            ft.close()
            encoded.append({"id": fid + ".woff1", "font_id": fid, "kind": "woff1", "path": w1})
            w2 = os.path.join(args.work, fid + ".woff2")
            woff2.compress(orig, w2)
            encoded.append({"id": fid + ".woff2", "font_id": fid, "kind": "woff2", "path": w2})
            if outline == "glyf":
                w3 = os.path.join(args.work, fid + ".hmtx.woff2")
                woff2.compress(orig, w3, transform_tables={"glyf", "loca", "hmtx"})
                encoded.append({"id": fid + ".woff2-hmtx", "font_id": fid, "kind": "woff2_hmtx_transform", "path": w3})
        except Exception as e:
            errors.append({"font": basename, "error": repr(e)[:500]})
    manifest = {
        "fonttools": __import__("fontTools").version,
        "fonts": fonts,
        "encoded": encoded,
        "missing": missing,
        "errors": errors,
        "has_cff": any(f["outline"] in ("CFF ", "CFF2") for f in fonts),
        "has_variable": any(f["variable"] for f in fonts),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    print(f"fonts={len(fonts)} encoded={len(encoded)} missing={missing} errors={len(errors)} cff={manifest['has_cff']} variable={manifest['has_variable']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
