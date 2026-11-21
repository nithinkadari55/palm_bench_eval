#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile

from fontTools.ttLib import TTCollection, TTFont

FONT_DIRS = ["/usr/share/fonts"]

GROUP_FONTS = {
    "latin": [("NotoSans-Regular.ttf", None), ("NotoSerif-Regular.ttf", None), ("DejaVuSans.ttf", None)],
    "arabic": [("NotoNaskhArabic-Regular.ttf", None), ("NotoSansArabic-Regular.ttf", None)],
    "hebrew": [("NotoSansHebrew-Regular.ttf", None), ("NotoSerifHebrew-Regular.ttf", None)],
    "devanagari": [("NotoSansDevanagari-Regular.ttf", None), ("NotoSerifDevanagari-Regular.ttf", None)],
    "bengali": [("NotoSansBengali-Regular.ttf", None), ("NotoSerifBengali-Regular.ttf", None)],
    "tamil": [("NotoSansTamil-Regular.ttf", None), ("NotoSerifTamil-Regular.ttf", None)],
    "telugu": [("NotoSansTelugu-Regular.ttf", None), ("NotoSerifTelugu-Regular.ttf", None)],
    "gujarati": [("NotoSansGujarati-Regular.ttf", None), ("NotoSerifGujarati-Regular.ttf", None)],
    "thai": [("NotoSansThai-Regular.ttf", None), ("NotoSerifThai-Regular.ttf", None)],
    "khmer": [("NotoSansKhmer-Regular.ttf", None), ("NotoSerifKhmer-Regular.ttf", None)],
    "myanmar": [("NotoSansMyanmar-Regular.ttf", None), ("NotoSerifMyanmar-Regular.ttf", None)],
    "sinhala": [("NotoSansSinhala-Regular.ttf", None), ("NotoSerifSinhala-Regular.ttf", None)],
    "cjk": [("NotoSansCJK-Regular.ttc", "Noto Sans CJK {cjk}"), ("NotoSerifCJK-Regular.ttc", "Noto Serif CJK {cjk}")],
    "hangul": [("NotoSansCJK-Regular.ttc", "Noto Sans CJK KR"), ("NotoSerifCJK-Regular.ttc", "Noto Serif CJK KR")],
    "emoji": [("NotoColorEmoji.ttf", None)],
}
EXTRA_FONTS = {"urd": [("NotoNastaliqUrdu-Regular.ttf", None)]}
CJK_VARIANT = {"zh-Hans": "SC", "zh-Hant": "TC", "ja": "JP", "ko": "KR"}


def find_font(basename):
    for d in FONT_DIRS:
        for root, _, files in os.walk(d):
            if basename in files:
                return os.path.join(root, basename)
    return None


def face_index(path, family):
    if family is None:
        return 0
    coll = TTCollection(path, lazy=True)
    for i, f in enumerate(coll.fonts):
        names = {n.toUnicode() for n in f["name"].names if n.nameID in (1, 16)}
        if family in names:
            return i
    return None


def run_hb(hb, font, idx, script, lang, direction, text):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tf:
        tf.write(text)
        tmp = tf.name
    try:
        cmd = [hb, f"--font-file={font}", f"--face-index={idx}", "--font-funcs=ot",
               f"--direction={direction}", f"--script={script}", f"--language={lang}",
               "--no-glyph-names", "--utf8-clusters", "--output-format=json", f"--text-file={tmp}"]
        p = subprocess.run(cmd, capture_output=True, timeout=120)
        if p.returncode != 0:
            return None, p.stderr.decode("utf-8", "replace")[:500]
        out = p.stdout.decode("utf-8").strip()
        lines = [l for l in out.splitlines() if l.strip()]
        if len(lines) != 1:
            return None, f"expected 1 output line, got {len(lines)}"
        data = json.loads(lines[0])
        return [[g["g"], g.get("cl", 0), g.get("ax", 0), g.get("ay", 0), g.get("dx", 0), g.get("dy", 0)] for g in data], None
    except Exception as e:
        return None, repr(e)[:500]
    finally:
        os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hb-shape", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    args = ap.parse_args()
    version = subprocess.run([args.hb_shape, "--version"], capture_output=True, text=True).stdout.strip()
    corpus = json.load(open(args.corpus, encoding="utf-8"))
    cases = []
    missing = []
    for e in corpus["entries"]:
        fonts = GROUP_FONTS[e["group"]] + EXTRA_FONTS.get(e["id"], [])
        texts = e["sequences"] if e["kind"] == "emoji" else e["lines"]
        for basename, family in fonts:
            if family and "{cjk}" in family:
                family = family.format(cjk=CJK_VARIANT[e["lang"]])
            path = find_font(basename)
            idx = face_index(path, family) if path else None
            if path is None or idx is None:
                missing.append({"entry": e["id"], "font": basename, "family": family})
                continue
            for n, text in enumerate(texts):
                cases.append({
                    "id": f"{e['id']}/{basename}#{idx}/{n}", "group": e["group"], "entry": e["id"],
                    "lang": e["lang"], "script": e["script"], "direction": e["direction"],
                    "font": path, "face_index": idx, "text": text,
                })
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(run_hb, args.hb_shape, c["font"], c["face_index"], c["script"], c["lang"], c["direction"], c["text"]) for c in cases]
        for c, f in zip(cases, futs):
            glyphs, err = f.result()
            c["glyphs"] = glyphs
            if err:
                c["error"] = err
    out = {"oracle": args.label, "hb_shape": args.hb_shape, "hb_version": version,
           "missing_fonts": missing, "cases": cases}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    errs = sum(1 for c in cases if c.get("error"))
    print(f"{args.label}: {version.splitlines()[0] if version else '?'}; cases={len(cases)} errors={errs} missing_fonts={len(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
