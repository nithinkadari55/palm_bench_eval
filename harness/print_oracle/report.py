import argparse
import glob
import json
import os


def load_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def f(v, d=3):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{d}f}"
    return str(v)


def pc(v):
    return "–" if v is None else f"{100 * v:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="dir containing print-oracle-<engine>.json (searched recursively)")
    ap.add_argument("--corpus", default=None, help="corpus dir with manifest.json / chrome_meta.json")
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    a = ap.parse_args()
    runs = {}
    for p in sorted(glob.glob(os.path.join(a.results, "**", "print-oracle-*.json"), recursive=True)):
        j = load_json(p)
        if j and "engine" in j and "overall" in j:
            runs[j["engine"]] = j
    man = load_json(os.path.join(a.corpus, "manifest.json"), {}) if a.corpus else {}
    cmeta = load_json(os.path.join(a.corpus, "chrome_meta.json"), {}) if a.corpus else {}
    engines = sorted(runs, key=lambda e: -(runs[e]["overall"].get("score") or 0))
    L = ["# Print oracle: engines vs Chrome print output", ""]
    if cmeta:
        L.append(f"Oracle: `{cmeta.get('version')}` · flags `{' '.join(cmeta.get('flags', []))}` · {cmeta.get('ok')}/{cmeta.get('n')} docs rendered · "
                 f"probe {json.dumps(cmeta.get('probe', {}).get('backgrounds_printed'))} backgrounds, page {cmeta.get('probe', {}).get('page_pt')} pt")
    if man:
        L.append(f"Corpus: {man.get('count')} docs · by source {json.dumps(man.get('by_source'))} · injected default `{man.get('default_page_css')}`")
    L += ["", "## Leaderboard (all docs with an oracle; failures score 0)", "",
          "| # | engine | score | ok | pages exact | mean abs Δpages | page-agree (matched) | page-agree (strict) | recall | precision | seq recall | dx med/p90 | dy med/p90 | within 2px | SSIM mean | SSIM p1 | t p50/p95 s | RSS p95 MB |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, e in enumerate(engines):
        o = runs[e]["overall"]
        L.append(f"| {k + 1} | **{e}** | {f(o['score'])} | {o['ok']}/{o['n']} | {pc(o['page_exact'])} | {f(o['page_abs_delta_mean'], 2)} | {pc(o['page_agree'])} | "
                 f"{pc(o['page_agree_strict'])} | {pc(o['recall'])} | {pc(o['precision'])} | {pc(o['seq_recall'])} | {f(o['dx_med'], 1)}/{f(o['dx_p90'], 1)} | "
                 f"{f(o['dy_med'], 1)}/{f(o['dy_p90'], 1)} | {pc(o['pos_within_2px'])} | {f(o['ssim_mean'])} | {f(o['ssim_p1'])} | "
                 f"{f(o['elapsed_p50'], 2)}/{f(o['elapsed_p95'], 2)} | {f(o['rss_p95_mb'], 0)} |")
    cats = sorted({c for e in engines for c in runs[e]["by_category"]})
    for metric, title, fmt in (("score", "Score by category", f), ("page_exact", "Page count exact by category", pc),
                               ("page_agree_strict", "Page-break agreement (strict) by category", pc), ("ssim_mean", "SSIM mean by category", f)):
        L += ["", f"## {title}", "", "| category | n | " + " | ".join(engines) + " |", "|---|---|" + "---|" * len(engines)]
        for c in cats:
            n = max((runs[e]["by_category"].get(c, {}).get("n") or 0) for e in engines)
            L.append(f"| {c} | {n} | " + " | ".join(fmt(runs[e]["by_category"].get(c, {}).get(metric)) for e in engines) + " |")
    L += ["", "## Status counts", "", "| engine | " + " | ".join(["status", "skipped (no oracle)", "blank p1", "wall s"]) + " |", "|---|---|---|---|---|"]
    for e in engines:
        o = runs[e]["overall"]
        L.append(f"| {e} | {json.dumps(o['status'])} | {len(runs[e].get('skipped_no_oracle', []))} | {o['blank_p1']} | {runs[e].get('wall_s')} |")
    L += ["", "## 10 worst docs per engine (first-page PNGs in the `print-oracle-<engine>` artifact, worst/)", ""]
    for e in engines:
        L.append(f"**{e}**: " + ", ".join(f"`{w['doc']}` ({f(w['score'], 2)}, {w['pages_engine']}/{w['pages_chrome']}p)" for w in runs[e]["worst"][:10]))
        L.append("")
    L += ["## Metric definitions", "",
          "- Words: pdfminer layout (LAParams all_texts) reading order; NFKC+casefold; split at spaces/punctuation; CJK/Thai = one token per char; "
          "Arabic/Hebrew/Indic tokens canonicalised by sorting their code points (robust to visual-order / reordered-matra extraction).",
          "- Alignment: difflib SequenceMatcher on Chrome vs engine word sequences, plus multiset matching inside each replace gap (local re-ordering).",
          "- recall = matched/Chrome words · precision = matched/engine words (duplicates and junk lower it) · seq recall = in-order (LCS) matches/Chrome words.",
          "- page-agree (matched) = matched words on the same page index / matched · page-agree (strict) = same-page matches / Chrome words.",
          "- dx/dy: |Δ| of word top-left (CSS px) for same-page matches; per-doc median and p90, then median across docs. within 2px = share with |dx|≤2 and |dy|≤2.",
          "- SSIM: per page, 96 dpi pdftoppm, engine page padded/cropped to the Chrome page raster, grayscale, downscaled to 320 px width; "
          "missing/extra pages count 0. SSIM mean = mean over max(pages). SSIM p1 = first page.",
          "- score (per doc) = mean(page-agree strict, recall, precision, SSIM mean); failed docs 0; leaderboard score = mean over all docs with an oracle.", ""]
    md = "\n".join(L)
    with open(a.out_md, "w", encoding="utf-8") as fh:
        fh.write(md)
    summ = {"chrome": {k: cmeta.get(k) for k in ("version", "flags", "probe", "ok", "n")} if cmeta else None,
            "corpus": {k: man.get(k) for k in ("count", "by_source", "by_category", "default_page_css", "generator")} if man else None,
            "leaderboard": [{"engine": e, **runs[e]["overall"]} for e in engines],
            "by_category": {e: runs[e]["by_category"] for e in engines}, "by_source": {e: runs[e]["by_source"] for e in engines},
            "worst": {e: runs[e]["worst"] for e in engines}}
    with open(a.out_json, "w", encoding="utf-8") as fh:
        json.dump(summ, fh, indent=1, ensure_ascii=False)
    print(f"wrote {a.out_md} and {a.out_json}: {len(engines)} engines")


if __name__ == "__main__":
    main()
