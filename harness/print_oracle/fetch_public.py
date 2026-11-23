import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from fetch_datasets import get  # noqa: E402
from oracle_lib import xhtml_to_html  # noqa: E402

PAGEDJS_SPECS = [
    "bleed/bleed.html",
    "breaks/break-after/break-after-page/break-after-page.html",
    "breaks/break-after/break-after-avoid/break-after-avoid.html",
    "breaks/break-before/break-before-page/break-before-page.html",
    "breaks/break-before/break-before-avoid/break-before-avoid.html",
    "breaks/break-before/break-before-right/break-before-right.html",
    "breaks/break-inside/break-inside-avoid/break-inside-avoid.html",
    "breaks/breaks.html",
    "breaks/fractional-pixels/fractional-pixels.html",
    "breaks/in-top-level/in-top-level.html",
    "breaks/table/avoid-break-rowspan.html",
    "counters/counter-page/counter-page.html",
    "counters/counter-pages/counter-pages.html",
    "counters/counter-page-reset/counter-page-reset.html",
    "counters/nested/nested.html",
    "default/default.html",
    "generate-content/content-none/content-none.html",
    "margin-boxes/dimension/dimension.html",
    "margin-boxes/text-align/text-align.html",
    "margin-boxes/vertical-align/vertical-align.html",
    "margin-boxes/style/style.html",
    "media/print/print.html",
    "named-page/named-page/named-page.html",
    "named-page/page-group/page-group.html",
    "notes/footnotes/footnotes.html",
    "page-rules/size/landscape/landscape.html",
    "page-rules/size/page-size/page-size.html",
    "page-selector/first-page/first-page.html",
    "page-selector/blank-page/blank-page.html",
    "page-selector/page-nth/page-nth.html",
    "page-selector/page-spread/page-spread.html",
    "position-fixed/position-fixed.html",
    "splits/lists/lists.html",
    "splits/numbering/numbering.html",
    "splits/tables/long-table.html",
    "splits/text-align-last/text-align-last.html",
    "string/string-first.html",
    "string/string-multiple.html",
    "tables/column-overflow/column-overflow.html",
    "tables/nested/nested.html",
    "tables/rebuild/rebuild.html",
    "target/target-counter/target-counter.html",
    "widows-orphans/widows-orphans.html",
]

SOURCES = [
    {
        "key": "weasyprint",
        "repo": "https://github.com/CourtBouillon/weasyprint-samples.git",
        "sha": "6dc675b05a5cba59576dfaa8881ea6ccdccb13cc",
        "dirs": ["invoice", "letter", "poster", "report", "ticket"],
        "docs": [("invoice/invoice.html", "invoice", "public-domain"), ("letter/letter.html", "letter", "public-domain"),
                 ("poster/poster.html", "poster", "public-domain"), ("report/report.html", "report", "public-domain"),
                 ("ticket/ticket.html", "ticket", "public-domain")],
    },
    {
        "key": "pagedjs",
        "repo": "https://github.com/pagedjs/pagedjs.git",
        "sha": "bbdc7519b458c400ed1880d9d692c9bf0b394a45",
        "dirs": ["specs"],
        "docs": [("specs/" + p, "spec", "MIT") for p in PAGEDJS_SPECS],
    },
    {
        "key": "vivliostyle",
        "repo": "https://github.com/vivliostyle/vivliostyle_doc.git",
        "sha": "7af9003bd803163ac45aa5c44278f8659ed965a5",
        "dirs": ["samples/gutenberg", "samples/wood", "samples/shirouma", "samples/news", "samples/scholarly", "samples/gon",
                 "samples/fixed-page-size/TheMalayArchipelago", "samples/fixed-page-size/ja-horizontal/Takasebune"],
        "docs": [("samples/gutenberg/Alice.html", "book", "0BSD markup; text public domain (Project Gutenberg)"),
                 ("samples/wood/index.html", "book", "0BSD markup; text public domain"),
                 ("samples/shirouma/index.html", "essay-ja", "0BSD markup; text public domain (Aozora Bunko)"),
                 ("samples/news/index.html", "newspaper-ja", "0BSD markup; text CC BY 2.5 (Wikinews)"),
                 ("samples/scholarly/index.html", "article", "Apache-2.0 (samples/scholarly/LICENSE)"),
                 ("samples/gon/index.html", "vertical-ja", "0BSD markup; text public domain (Aozora Bunko)"),
                 ("samples/fixed-page-size/TheMalayArchipelago/main.xhtml", "book", "0BSD markup; text CC BY-SA (Wikipedia excerpt)"),
                 ("samples/fixed-page-size/ja-horizontal/Takasebune/main.xhtml", "book-ja", "0BSD markup; text public domain (Aozora Bunko)")],
    },
]


def git_sparse(repo, sha, dirs, dst):
    if os.path.isdir(os.path.join(dst, ".git")):
        head = subprocess.run(["git", "-C", dst, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if head == sha:
            return
        shutil.rmtree(dst)
    os.makedirs(dst, exist_ok=True)
    run = lambda *a: subprocess.run(["git", "-C", dst, *a], check=True, capture_output=True, text=True)  # noqa: E731
    run("init", "-q")
    run("remote", "add", "origin", repo)
    run("config", "core.sparseCheckout", "true")
    run("sparse-checkout", "set", "--no-cone", *[f"/{d}/" for d in dirs])
    run("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", sha)
    run("checkout", "-q", "FETCH_HEAD")


def fetch_public(cache, corpus):
    entries = []
    for src in SOURCES:
        clone = os.path.join(cache, "git", src["key"])
        try:
            git_sparse(src["repo"], src["sha"], src["dirs"], clone)
        except Exception as e:  # noqa: BLE001
            print("public source failed", src["key"], repr(e)[:300])
            continue
        base = os.path.join(corpus, "pub", src["key"])
        for d in src["dirs"]:
            s = os.path.join(clone, d)
            if os.path.isdir(s):
                shutil.copytree(s, os.path.join(base, d), dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "*.pdf", "node_modules"))
        for rel, kind, lic in src["docs"]:
            p = os.path.join(base, rel)
            if not os.path.exists(p):
                print("missing", src["key"], rel)
                continue
            if p.endswith(".xhtml"):
                with open(p, encoding="utf-8", errors="replace") as f:
                    s = f.read()
                rel = rel[:-6] + ".po.html"
                with open(os.path.join(base, rel), "w", encoding="utf-8", newline="\n") as f:
                    f.write(xhtml_to_html(s))
            slug = rel.replace("specs/", "").replace("samples/", "").rsplit(".", 1)[0].replace(".po", "")
            slug = "".join(ch if ch.isalnum() else "_" for ch in slug).strip("_")
            dedup = []
            for x in slug.split("_"):
                if x and x not in dedup:
                    dedup.append(x)
            entries.append({"id": f"pub_{src['key']}_{'_'.join(dedup)[:60]}", "category": f"public-{src['key']}", "kind": kind,
                            "source": src["key"], "license": lic, "upstream": f"{src['repo'][:-4]}/blob/{src['sha']}/{rel.replace('.po.html', '.xhtml')}",
                            "path": os.path.relpath(os.path.join(base, rel), corpus).replace(os.sep, "/")})
    return entries


def fetch_websight(cache, corpus, n, stride=997, start=0, max_tries=None):
    rawdir = os.path.join(cache, "websight")
    os.makedirs(rawdir, exist_ok=True)
    out = os.path.join(corpus, "docs")
    os.makedirs(out, exist_ok=True)
    entries = []
    offset = start
    tries = 0
    max_tries = max_tries or n * 2
    while len(entries) < n and tries < max_tries:
        tries += 1
        raw = os.path.join(rawdir, f"{offset:07d}.html")
        if not os.path.exists(raw):
            url = ("https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode(
                {"dataset": "HuggingFaceM4/WebSight", "config": "v0.1", "split": "train", "offset": offset, "length": 1}))
            try:
                row = json.loads(get(url))["rows"][0]["row"]
                with open(raw, "w", encoding="utf-8", newline="\n") as f:
                    f.write(row["text"])
            except Exception as e:  # noqa: BLE001
                print("skip websight", offset, repr(e)[:200])
                offset += stride
                continue
        nm = f"ws_{offset:07d}"
        shutil.copyfile(raw, os.path.join(out, nm + ".html"))
        entries.append({"id": nm, "category": "websight", "source": "websight-v0.1", "license": "CC-BY-4.0",
                        "upstream": f"HuggingFaceM4/WebSight v0.1 train offset {offset}", "path": f"docs/{nm}.html"})
        offset += stride
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--websight", type=int, default=100)
    a = ap.parse_args()
    pub = fetch_public(a.cache, a.corpus)
    ws = fetch_websight(a.cache, a.corpus, a.websight)
    print(json.dumps({"public": len(pub), "websight": len(ws)}))


if __name__ == "__main__":
    main()
