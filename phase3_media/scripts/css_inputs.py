#!/usr/bin/env python3
"""Build the CSS <color> input list: hand-written LLM-style values plus literal values from WPT css/css-color/parsing."""
import argparse
import glob
import json
import os
import re
import sys

CURRENT = "rgb(10 20 30)"

# (category, input, valid)
HAND = [
    # hex
    ("hex", "#f00", True), ("hex", "#F00", True), ("hex", "#ff0000", True), ("hex", "#FF8800", True),
    ("hex", "#f008", True), ("hex", "#ff000080", True), ("hex", "#12345678", True), ("hex", "#abc", True),
    ("hex", "#AbCdEf", True), ("hex", "#000", True), ("hex", "#fff", True), ("hex", "#3b82f6", True),
    ("hex", "#1e293b", True), ("hex", "#0f172acc", True),
    ("hex", "#ff00", True), ("invalid", "#12345", False), ("invalid", "#1234567", False), ("invalid", "#ggg", False),
    ("invalid", "ff0000", False), ("invalid", "#", False),
    # rgb legacy
    ("rgb-legacy", "rgb(255, 0, 0)", True), ("rgb-legacy", "rgb(255,128,0)", True), ("rgb-legacy", "rgba(255, 0, 0, 0.5)", True),
    ("rgb-legacy", "rgba(0, 0, 0, .25)", True), ("rgb-legacy", "rgb(100%, 50%, 0%)", True), ("rgb-legacy", "rgba(100%, 0%, 0%, 50%)", True),
    ("rgb-legacy", "rgb(300, -20, 128)", True), ("rgb-legacy", "rgb(12.5, 99.9, 200.4)", True), ("rgb-legacy", "rgba(59, 130, 246, 0.1)", True),
    ("rgb-legacy", "RGB(255, 255, 255)", True), ("rgb-legacy", "rgba(255, 255, 255, 1)", True), ("rgb-legacy", "rgb(255, 0, 0, 0.3)", True),
    ("rgb-legacy", "rgba(255, 0, 0)", True),
    ("invalid", "rgb(255, 0)", False), ("invalid", "rgb(255 0, 0)", False), ("invalid", "rgb(100%, 0, 0)", False),
    ("invalid", "rgba(255, 0, 0, 0.5, 1)", False), ("invalid", "rgb(255, 0, 0,)", False), ("invalid", "rgb(none, 0, 0)", False),
    # rgb modern
    ("rgb-modern", "rgb(255 0 0)", True), ("rgb-modern", "rgb(255 0 0 / 0.5)", True), ("rgb-modern", "rgb(255 0 0 / 50%)", True),
    ("rgb-modern", "rgb(100% 50% 25%)", True), ("rgb-modern", "rgb(59 130 246 / .5)", True), ("rgb-modern", "rgba(255 0 0 / 0.5)", True),
    ("rgb-modern", "rgb(255 50% 0)", True), ("rgb-modern", "rgb(none 128 255)", True), ("rgb-modern", "rgb(255 0 0 / none)", True),
    ("rgb-modern", "rgb(calc(100 + 55) 0 0)", True), ("rgb-modern", "rgb(255 0 0 / calc(0.25 * 2))", True),
    ("invalid", "rgb(255 0 0 0.5)", False), ("invalid", "rgb(255 / 0 0)", False),
    # hsl
    ("hsl", "hsl(0, 100%, 50%)", True), ("hsl", "hsl(120, 100%, 25%)", True), ("hsl", "hsla(240, 100%, 50%, 0.5)", True),
    ("hsl", "hsl(217 91% 60%)", True), ("hsl", "hsl(217deg 91% 60% / 0.8)", True), ("hsl", "hsl(0.5turn 50% 50%)", True),
    ("hsl", "hsl(3.14159rad 50% 50%)", True), ("hsl", "hsl(200grad 50% 50%)", True), ("hsl", "hsl(-120 100% 50%)", True),
    ("hsl", "hsl(480 100% 50%)", True), ("hsl", "hsl(120 50 50)", True), ("hsl", "hsl(none 0% 50%)", True),
    ("hsl", "hsl(120 none 50%)", True), ("hsl", "hsl(0 0% 100%)", True), ("hsl", "hsla(0, 0%, 0%, 0)", True),
    ("hsl", "hsl(210, 40%, 96.1%)", True), ("hsl", "hsl(222.2 84% 4.9%)", True), ("hsl", "hsl(120 150% 50%)", True),
    ("invalid", "hsl(120, 50, 50)", False), ("invalid", "hsl(120deg, 50%)", False), ("invalid", "hsl(120 50% 50%, 0.5)", False),
    # hwb
    ("hwb", "hwb(0 0% 0%)", True), ("hwb", "hwb(120 20% 30%)", True), ("hwb", "hwb(240deg 10% 10% / 0.5)", True),
    ("hwb", "hwb(90 60% 60%)", True), ("hwb", "hwb(none 20% 20%)", True), ("hwb", "hwb(300 0 0)", True),
    ("invalid", "hwb(120, 20%, 30%)", False),
    # lab / lch
    ("lab", "lab(50% 40 59.5)", True), ("lab", "lab(29.2345 39.3825 20.0664)", True), ("lab", "lab(52.2345% 40.1645 59.9971 / .5)", True),
    ("lab", "lab(100 0 0)", True), ("lab", "lab(0 0 0)", True), ("lab", "lab(60 -80 90)", True), ("lab", "lab(50 100% -100%)", True),
    ("lab", "lab(none 20 30)", True), ("lab", "lab(110 0 0)", True),
    ("lch", "lch(52.2345% 72.2 56.2)", True), ("lch", "lch(29.2345% 44.2 27)", True), ("lch", "lch(50 100 270deg)", True),
    ("lch", "lch(70 45 none)", True), ("lch", "lch(60 150 120 / 0.3)", True), ("lch", "lch(50 50% 0.25turn)", True),
    # oklab / oklch
    ("oklab", "oklab(59.686% 0.1009 0.1192)", True), ("oklab", "oklab(0.4 -0.1 0.1)", True), ("oklab", "oklab(0.7 0.1 -0.1 / 0.5)", True),
    ("oklab", "oklab(100% 0 0)", True), ("oklab", "oklab(0.5 40% -40%)", True),
    ("oklch", "oklch(60% 0.15 50)", True), ("oklch", "oklch(0.628 0.258 29.23)", True), ("oklch", "oklch(70% 0.1 200 / 50%)", True),
    ("oklch", "oklch(0.9 0.4 145)", True), ("oklch", "oklch(0.5 none 0)", True), ("oklch", "oklch(62.8% 0.2577 29.2339deg)", True),
    ("oklch", "oklch(0.75 50% 330)", True), ("oklch", "oklch(0.985 0.002 247.839)", True), ("oklch", "oklch(0.21 0.034 264.665)", True),
    ("invalid", "oklch(60%, 0.15, 50)", False), ("invalid", "lab(50% 40)", False),
    # color()
    ("color-fn", "color(srgb 1 0 0)", True), ("color-fn", "color(srgb 100% 50% 0%)", True), ("color-fn", "color(srgb 0.5 0.5 0.5 / 0.5)", True),
    ("color-fn", "color(srgb-linear 0.2 0.5 0.8)", True), ("color-fn", "color(display-p3 1 0 0)", True), ("color-fn", "color(display-p3 0.3 0.8 0.4)", True),
    ("color-fn", "color(display-p3 0 1 0 / 0.8)", True), ("color-fn", "color(a98-rgb 0.4 0.6 0.2)", True), ("color-fn", "color(prophoto-rgb 0.5 0.3 0.7)", True),
    ("color-fn", "color(rec2020 0.8 0.2 0.1)", True), ("color-fn", "color(rec2020 0 1 0)", True), ("color-fn", "color(xyz 0.3 0.4 0.5)", True),
    ("color-fn", "color(xyz-d50 0.4 0.3 0.2)", True), ("color-fn", "color(xyz-d65 0.95 1 1.09)", True), ("color-fn", "color(srgb 1.2 -0.1 0.5)", True),
    ("color-fn", "color(srgb none 0.5 1)", True),
    ("invalid", "color(display-p3 1 0)", False), ("invalid", "color(foo 1 0 0)", False), ("invalid", "color(srgb, 1, 0, 0)", False),
    # color-mix
    ("color-mix", "color-mix(in srgb, red, blue)", True), ("color-mix", "color-mix(in srgb, red 25%, blue)", True),
    ("color-mix", "color-mix(in srgb, red, blue 70%)", True), ("color-mix", "color-mix(in srgb, red 30%, blue 30%)", True),
    ("color-mix", "color-mix(in srgb, red 80%, blue 80%)", True), ("color-mix", "color-mix(in srgb-linear, red, blue)", True),
    ("color-mix", "color-mix(in oklab, #3b82f6, white)", True), ("color-mix", "color-mix(in oklab, #3b82f6 20%, transparent)", True),
    ("color-mix", "color-mix(in oklch, red, blue)", True), ("color-mix", "color-mix(in oklch longer hue, red, blue)", True),
    ("color-mix", "color-mix(in oklch increasing hue, red, blue)", True), ("color-mix", "color-mix(in oklch decreasing hue, red, blue)", True),
    ("color-mix", "color-mix(in hsl, red, lime)", True), ("color-mix", "color-mix(in hsl shorter hue, hsl(350 100% 50%), hsl(10 100% 50%))", True),
    ("color-mix", "color-mix(in hwb, red, blue)", True), ("color-mix", "color-mix(in lab, red, blue)", True), ("color-mix", "color-mix(in lch, red, blue)", True),
    ("color-mix", "color-mix(in xyz, red, blue)", True), ("color-mix", "color-mix(in xyz-d50, red, blue)", True),
    ("color-mix", "color-mix(in display-p3, red, blue)", True), ("color-mix", "color-mix(in srgb, rgb(255 0 0 / 0.5), blue)", True),
    ("color-mix", "color-mix(in srgb, currentcolor 50%, white)", True), ("color-mix", "color-mix(in oklab, black 10%, #f8fafc)", True),
    ("color-mix", "color-mix(in srgb, color-mix(in srgb, red, blue), white)", True),
    ("invalid", "color-mix(red, blue)", False), ("invalid", "color-mix(in srgb, red)", False),
    ("invalid", "color-mix(in srgb, red 0%, blue 0%)", False), ("invalid", "color-mix(in foo, red, blue)", False),
    ("invalid", "color-mix(in srgb longer hue, red, blue)", False),
    # relative colours
    ("relative", "rgb(from red r g b)", True), ("relative", "rgb(from red r g b / 50%)", True), ("relative", "rgb(from #3b82f6 r g b / 0.5)", True),
    ("relative", "rgb(from red calc(r / 2) g b)", True), ("relative", "rgb(from rebeccapurple b g r)", True),
    ("relative", "hsl(from red h s l)", True), ("relative", "hsl(from red calc(h + 180) s l)", True), ("relative", "hsl(from #3b82f6 h s calc(l - 20))", True),
    ("relative", "hwb(from red h w b)", True), ("relative", "lab(from red l a b)", True), ("relative", "lab(from blue l a b / alpha)", True),
    ("relative", "lch(from red l c calc(h + 90))", True), ("relative", "oklab(from red l a b)", True), ("relative", "oklch(from red l c h)", True),
    ("relative", "oklch(from #3b82f6 calc(l * 0.8) c h)", True), ("relative", "oklch(from red l 0 h)", True),
    ("relative", "oklch(from blue l c calc(h + 180) / 0.5)", True), ("relative", "color(from red srgb r g b)", True),
    ("relative", "color(from red display-p3 r g b)", True), ("relative", "rgb(from currentcolor r g b / 0.5)", True),
    ("relative", "rgb(from rgb(10 20 30 / 0.5) r g b / alpha)", True), ("relative", "hsl(from green h s l / 0.25)", True),
    ("invalid", "rgb(from red r g)", False), ("invalid", "rgb(from red x y z)", False), ("invalid", "hsl(from red h s)", False),
    # currentcolor / transparent / named
    ("currentcolor", "currentcolor", True), ("currentcolor", "currentColor", True), ("currentcolor", "CURRENTCOLOR", True),
    ("named", "transparent", True), ("named", "Transparent", True), ("named", "REBECCAPURPLE", True), ("named", "DarkSlateGray", True),
    ("invalid", "notacolor", False), ("invalid", "red blue", False), ("invalid", "", False),
    # light-dark (CSS Color 5)
    ("light-dark", "light-dark(white, black)", True), ("light-dark", "light-dark(#fff, #000)", True),
]

SYSTEM = ["AccentColor", "AccentColorText", "ActiveText", "ButtonBorder", "ButtonFace", "ButtonText", "Canvas", "CanvasText",
          "Field", "FieldText", "GrayText", "Highlight", "HighlightText", "LinkText", "Mark", "MarkText", "SelectedItem",
          "SelectedItemText", "VisitedText", "ActiveBorder", "ActiveCaption", "AppWorkspace", "Background", "ButtonHighlight",
          "ButtonShadow", "CaptionText", "InactiveBorder", "InactiveCaption", "InactiveCaptionText", "InfoBackground",
          "InfoText", "Menu", "MenuText", "Scrollbar", "ThreeDDarkShadow", "ThreeDFace", "ThreeDHighlight",
          "ThreeDLightShadow", "ThreeDShadow", "Window", "WindowFrame", "WindowText"]

CALLS = {
    "test_computed_value": ("computed", True),
    "fuzzy_test_computed_color": ("computed", False),
    "test_valid_value": ("valid", True),
    "fuzzy_test_valid_color": ("valid", False),
    "test_invalid_value": ("invalid", True),
}


def js_args(src, start):
    """Parse a JS argument list starting after '('. Returns (list of literal strings | None, end)."""
    args, i, depth, cur_lit, ok = [], start, 0, None, True
    n = len(src)
    while i < n:
        ch = src[i]
        if ch in "\"'`":
            q = ch
            j = i + 1
            buf = []
            while j < n and src[j] != q:
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j + 1])
                    j += 2
                    continue
                buf.append(src[j])
                j += 1
            lit = "".join(buf)
            if q == "`" and "${" in lit:
                ok = False
            if depth == 0:
                cur_lit = lit if ok else None
            elif depth == 1 and cur_lit is None and src[start:i].rstrip().endswith("["):
                cur_lit = lit if ok else None
            i = j + 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                args.append(cur_lit)
                return args, i
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(cur_lit)
            cur_lit, ok = None, True
        elif depth == 0 and not ch.isspace():
            if cur_lit is None and ch not in "[":
                ok = False
        i += 1
    return None, n


def wpt_cases(wpt_dir):
    out = []
    for f in sorted(glob.glob(os.path.join(wpt_dir, "*.html"))):
        src = open(f, encoding="utf-8").read()
        base = os.path.basename(f)
        for name, (kind, has_prop) in CALLS.items():
            for m in re.finditer(r"\b" + name + r"\s*\(", src):
                args, _ = js_args(src, m.end())
                if not args:
                    continue
                if has_prop:
                    if args[0] != "color" or len(args) < 2:
                        continue
                    args = args[1:]
                inp = args[0]
                if inp is None or "var(" in inp:
                    continue
                exp = args[1] if len(args) > 1 else None
                out.append({"source": "wpt:" + base, "category": "wpt-" + kind, "input": inp,
                            "valid": kind != "invalid", "expected": exp if kind == "computed" else None})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wpt", required=True, help="css/css-color/parsing directory")
    ap.add_argument("--keywords", required=True, help="colorjs.io src/keywords.js (named colour list)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cases = [{"source": "hand", "category": c, "input": i, "valid": v, "expected": None} for c, i, v in HAND]
    names = re.findall(r"^\s*([a-z]+)\s*:", open(args.keywords, encoding="utf-8").read(), re.M)
    cases += [{"source": "named-keywords", "category": "named", "input": n, "valid": True, "expected": None} for n in names]
    cases += [{"source": "css-color-4 system colors", "category": "system", "input": s, "valid": True, "expected": None}
              for s in SYSTEM]
    cases += wpt_cases(args.wpt)
    seen, uniq = set(), []
    for c in cases:
        key = (c["input"], c["source"].split(":")[0], c["category"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    for i, c in enumerate(uniq):
        c["id"] = f"c{i:05d}"
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"current_color": CURRENT, "cases": uniq}, fh, indent=1)
    cats = {}
    for c in uniq:
        cats[c["category"]] = cats.get(c["category"], 0) + 1
    print(json.dumps(cats), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
