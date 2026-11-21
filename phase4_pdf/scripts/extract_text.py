#!/usr/bin/env python3
"""Text extraction fidelity (ToUnicode / ActualText) of the `text` fixture with four independent extractors."""
import argparse
import json
import os
import subprocess
import tempfile
import unicodedata
from collections import Counter

import pdfminer
import pypdf
from pdfminer.high_level import extract_text as pdfminer_extract

FIXTURES = ["text", "text_emoji"]


def ws(s):
    return " ".join((s or "").split())


def nospace_nfkc(s):
    return "".join(unicodedata.normalize("NFKC", s or "").split())


def classify(extracted, expected):
    if ws(extracted) == ws(expected):
        return "exact"
    a, b = nospace_nfkc(extracted), nospace_nfkc(expected)
    if a == b:
        return "nfkc_whitespace"
    if a[::-1] == b:
        return "reversed"
    if Counter(a) == Counter(b):
        return "same_chars_other_order"
    if not a:
        return "empty"
    return "different"


def ex_pdfminer(path, n):
    return [pdfminer_extract(path, page_numbers=[i]) for i in range(n)]


def ex_pypdf(path, n):
    r = pypdf.PdfReader(path)
    return [r.pages[i].extract_text() for i in range(n)]


def ex_pdftotext(path, n):
    p = subprocess.run(["pdftotext", "-enc", "UTF-8", path, "-"], capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:500])
    pages = p.stdout.decode("utf-8", "replace").split("\f")
    return (pages + [""] * n)[:n]


def tool_versions(js_dir):
    v = {"pdfminer.six": pdfminer.__version__, "pypdf": pypdf.__version__}
    p = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True)
    v["pdftotext"] = (p.stderr or p.stdout).strip().splitlines()[0] if (p.stderr or p.stdout) else "?"
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--js", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    gen = json.load(open(os.path.join(args.corpus, "generation.json"), encoding="utf-8"))
    expected = {}
    for fx in FIXTURES:
        p = os.path.join(args.corpus, fx, "expected.json")
        if os.path.exists(p):
            expected[fx] = json.load(open(p, encoding="utf-8"))["pages"]
    pdfs = [(e["fixture"], e["profile"], os.path.abspath(os.path.join(args.corpus, e["file"]))) for e in gen["entries"]
            if e["fixture"] in expected and e["status"] == "ok"]

    with tempfile.TemporaryDirectory() as td:
        out_js = os.path.join(td, "pdfjs.json")
        p = subprocess.run(["node", os.path.join(args.js, "extract.mjs"), out_js] + [f for _, _, f in pdfs],
                           capture_output=True, text=True, timeout=1800)
        pdfjs = json.load(open(out_js, encoding="utf-8")) if os.path.exists(out_js) else {"files": {}, "error": p.stderr[-2000:]}

    def ex_pdfjs(f, n):
        entry = pdfjs["files"].get(f)
        if not entry or "pages" not in entry:
            raise RuntimeError((entry or {}).get("error") or pdfjs.get("error") or "no pdf.js output")
        return entry["pages"]

    extractors = {"pdfminer": ex_pdfminer, "pdftotext": ex_pdftotext, "pypdf": ex_pypdf, "pdfjs": ex_pdfjs}
    rows = []
    for fx, profile, f in pdfs:
        pages = expected[fx]
        n = len(pages)
        for name, fn in extractors.items():
            try:
                got = fn(f, n)
                err = None
            except Exception as e:
                got, err = [""] * n, repr(e)[:500]
            for i, pg in enumerate(pages):
                text = got[i] if i < len(got) else ""
                cls = "extractor_error" if err else classify(text, pg["text"])
                rows.append({"fixture": fx, "profile": profile, "extractor": name, "script": pg["script"], "class": cls,
                             "expected": pg["text"], "extracted": (text or "")[:400], "error": err})
    pages = [pg for fx in FIXTURES for pg in expected.get(fx, [])]

    def agg(keyf):
        d = {}
        for r in rows:
            k = keyf(r)
            a = d.setdefault(k, {"total": 0, "exact": 0, "classes": Counter()})
            a["total"] += 1
            a["exact"] += r["class"] == "exact"
            a["classes"][r["class"]] += 1
        for a in d.values():
            a["exact_rate"] = a["exact"] / a["total"] if a["total"] else None
            a["classes"] = dict(a["classes"])
        return d

    per_es = agg(lambda r: f"{r['extractor']}|{r['script']}")
    table = {}
    for k, v in per_es.items():
        e, s = k.split("|")
        table.setdefault(e, {})[s] = v
    passed = sum(r["class"] == "exact" for r in rows)
    fails = [r for r in rows if r["class"] != "exact"]
    result = {
        "test": f"text_extraction_{args.label}",
        "tools": {**tool_versions(args.js), "pdfjs-dist": pdfjs.get("pdfjs_version")},
        "pass": passed, "fail": len(rows) - passed, "total": len(rows),
        "pass_rate": passed / len(rows) if rows else None,
        "pass_criterion": "extracted page text equals the source string after collapsing whitespace runs (exact); classes nfkc_whitespace / reversed / same_chars_other_order / empty / different are diagnostics",
        "profiles": sorted({p for _, p, _ in pdfs}),
        "per_extractor_script": table,
        "per_extractor": agg(lambda r: r["extractor"]),
        "per_extractor_profile": agg(lambda r: f"{r['extractor']}|{r['profile']}"),
        "shaping": {pg["script"]: pg.get("shaping") or pg.get("instances") for pg in pages},
        "first_failures": fails[:40],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    print(f"text extraction: {passed}/{len(rows)} exact")


if __name__ == "__main__":
    main()
