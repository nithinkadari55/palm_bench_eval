#!/usr/bin/env python3
import argparse
import glob
import json
import os
import sys

EXPECTED = ["raster_png", "raster_jpeg", "raster_webp", "raster_gif", "avif_avif_native", "avif_avif_pure",
            "avif_avif_zen", "robustness", "cmyk_jpeg", "exif_orientation", "icc_moxcms", "icc_qcms", "icc_raikiri",
            "css_color_raikiri", "css_color_color", "css_color_csscolorparser", "css_color_cssparser-color",
            "css_oracle_selfcheck", "svg_resvg_0.48.1", "svg_resvg_0.45.1", "svg_krilla_pdf_strict",
            "svg_krilla_pdf_relaxed", "pdf_images", "pdf_images_structure"]
NO_TOTALS = {"avif_candidates"}


def pct(x):
    return f"{100.0 * x:.2f}%" if isinstance(x, (int, float)) else "-"


def cat_table(md, title, per):
    md += [f"### {title}", "", "| category | pass | total | rate |", "|---|---:|---:|---:|"]
    for k, v in sorted(per.items()):
        md.append(f"| {k} | {v['pass']} | {v['total']} | {pct(v['pass'] / v['total'] if v['total'] else None)} |")
    md.append("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    res = {}
    for p in sorted(glob.glob(os.path.join(args.results, "*.json"))):
        name = os.path.splitext(os.path.basename(p))[0]
        if name.startswith("corpus-"):
            continue
        try:
            res[name] = json.load(open(p, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            res[name] = {"error": repr(e)}
    md = ["# Phase 3: images, colour, SVG", "", "| test | pass | fail | total | pass rate |", "|---|---:|---:|---:|---:|"]
    for name in EXPECTED + sorted(set(res) - set(EXPECTED) - NO_TOTALS):
        r = res.get(name)
        if r is None:
            md.append(f"| {name} | - | - | - | missing (step failed or not built) |")
            continue
        md.append(f"| {name} | {r.get('pass', '-')} | {r.get('fail', '-')} | {r.get('total', '-')} | {pct(r.get('pass_rate'))} |")
    md.append("")
    a = res.get("avif_candidates")
    if a:
        md += ["## AVIF decoder candidates", "", f"oracle: {a.get('oracle', '')}", "",
               f"oracle agreement (avifdec vs Pillow): {a.get('oracle_agreement', '')}", "",
               "| candidate | crate | licence | pure Rust | build | status | pass/total (tolerant) | strict pass | failure classes | safety failures |",
               "|---|---|---|---|---|---|---:|---:|---|---|"]
        for k, v in a.get("candidates", {}).items():
            md.append(f"| {k} | {v.get('crate', '')} | {v.get('licence', '')} | {v.get('pure_rust', '')} | {v.get('build', '')} | "
                      f"{v.get('status', '')} | {v.get('pass', '-')}/{v.get('total', '-')} | {v.get('strict_pass', '-')} | "
                      f"{v.get('failure_classes', '')} | {v.get('safety_failures', '')} |")
        md.append("")
        pa = a.get("pairwise_agreement") or {}
        if pa:
            md += ["| candidate pair | both decoded | agree (tolerant) | size mismatch |", "|---|---:|---:|---:|"]
            for k, v in pa.items():
                md.append(f"| {k} | {v['both_decoded']} | {v['agree_tolerant']} | {v['size_mismatch']} |")
            md.append("")
        for k in a.get("candidates", {}):
            r = res.get(f"avif_{k}")
            if r and r.get("per_tag"):
                cat_table(md, f"avif {k} per feature", r["per_tag"])
    r = res.get("robustness")
    if r and "decoders" in r:
        md += ["## Robustness (child process per case)", "", "| decoder | safety pass / total | strict Err rate | statuses |",
               "|---|---:|---:|---|"]
        for k, d in r["decoders"].items():
            if d.get("status") != "ran":
                md.append(f"| {k} | {d.get('status')} | - | - |")
                continue
            md.append(f"| {k} | {d['safety_pass']}/{d['total']} | {pct(d.get('strict_err_rate'))} | "
                      f"{', '.join(f'{a}:{b}' for a, b in d['by_status'].items())} |")
        md.append("")
    for name, key, title in (("raster_webp", "per_kind", "webp per kind"), ("exif_orientation", "per_format", "exif per format"),
                             ("icc_moxcms", "per_colour_space", "moxcms per colour space"),
                             ("icc_qcms", "per_colour_space", "qcms per colour space")):
        r = res.get(name)
        if r and r.get(key):
            per = {k: ({"pass": v["pass"], "total": v.get("total", v["pass"] + v.get("fail", 0))}) for k, v in r[key].items()}
            cat_table(md, title, per)
    for name in ("css_color_raikiri", "css_color_color", "css_color_csscolorparser", "css_color_cssparser-color"):
        r = res.get(name)
        if r and r.get("per_category"):
            st = r.get("de2000_stats") or {}
            md.append(f"deltaE2000 over compared cases ({name}): n={st.get('n')}, mean={st.get('mean')}, p95={st.get('p95')}, max={st.get('max')}")
            md.append("")
            cat_table(md, name + " per category", r["per_category"])
            md.append(f"clip-oracle variant: {r.get('pass_clip_oracle')}/{r.get('total')}")
            md.append("")
            if r.get("per_gamut"):
                md += ["| gamut bucket | pass (CSS gamut mapping) | pass (clip oracle) | total |", "|---|---:|---:|---:|"]
                for k, v in r["per_gamut"].items():
                    md.append(f"| {k} | {v['pass']} | {v['pass_clip_oracle']} | {v['total']} |")
                md.append("")
            mr = r.get("mix_relative")
            if mr:
                md.append(f"color-mix / relative: {mr['pass']}/{mr['total']} pass; failures: {mr['fail']} "
                          f"(reference WPT expected {mr['fail_reference_wpt_expected']}, colorjs evaluator "
                          f"{mr['fail_reference_colorjs_evaluator']}, in known oracle gap {mr['fail_in_known_oracle_gap']}, "
                          f"pass with clip oracle {mr['fail_but_pass_with_clip_oracle']})")
                md.append("")
    for name in ("svg_resvg_0.48.1", "svg_resvg_0.45.1", "svg_krilla_pdf_strict", "svg_krilla_pdf_relaxed"):
        r = res.get(name)
        if r and r.get("per_category"):
            cat_table(md, name + " per category", r["per_category"])
    with open(args.out, "a", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
