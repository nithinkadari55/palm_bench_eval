"""DOM/host API usage in LLM-written HTML, to rank the interfaces a production binding needs.

Sources:
  * phase5_js/js/cases/dom/*.js (the phase 5 LLM-style DOM scripts)
  * a WebSight sample (HuggingFaceM4/WebSight v0.1 and v0.2, CC-BY-4.0) read through the
    datasets-server rows API in batches spread evenly over each split (cached on disk)
  * spike_js_dom/cases/*.html
Counts are document frequencies over <script> bodies (inline and on* attributes), plus the
hosts of external <script src>.

usage: python api_usage.py --root <repo> --cache <dir> --out <json> [--batches 30] [--offline]
"""
import argparse
import glob
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter

UA = {"User-Agent": "bench-harness/1.0"}

# (label, regex, supported by the spike prelude, supported by raikiri-js)
APIS = [
    ("document.getElementById", r"\bgetElementById\s*\(", True, True),
    ("querySelector", r"\bquerySelector\s*\(", True, True),
    ("querySelectorAll", r"\bquerySelectorAll\s*\(", True, True),
    ("getElementsByClassName/TagName/Name", r"\bgetElementsBy(?:ClassName|TagName|Name)\s*\(", True, True),
    ("createElement", r"\bcreateElement\s*\(", True, True),
    ("createElementNS", r"\bcreateElementNS\s*\(", True, True),
    ("createTextNode", r"\bcreateTextNode\s*\(", True, True),
    ("createDocumentFragment", r"\bcreateDocumentFragment\s*\(", True, True),
    ("appendChild", r"\.appendChild\s*\(", True, True),
    ("insertBefore", r"\.insertBefore\s*\(", True, True),
    ("removeChild", r"\.removeChild\s*\(", True, True),
    ("append/prepend (ParentNode)", r"\.(?:append|prepend)\s*\(", True, True),
    ("remove() (ChildNode)", r"\.remove\s*\(\s*\)", True, True),
    ("replaceChild/replaceWith", r"\.(?:replaceChild|replaceWith)\s*\(", True, True),
    ("cloneNode", r"\.cloneNode\s*\(", True, True),
    ("innerHTML", r"\.innerHTML\b", True, True),
    ("outerHTML", r"\.outerHTML\b", True, False),
    ("insertAdjacentHTML", r"\.insertAdjacentHTML\s*\(", True, False),
    ("textContent", r"\.textContent\b", True, True),
    ("innerText", r"\.innerText\b", True, False),
    ("setAttribute/getAttribute", r"\.(?:set|get|remove|has)Attribute\s*\(", True, True),
    ("dataset", r"\.dataset\b", True, False),
    ("classList", r"\.classList\b", True, True),
    ("className", r"\.className\b", True, True),
    ("element.style.x / setProperty", r"\.style\.(?:[a-zA-Z]+\s*=|setProperty\s*\(|cssText)", True, True),
    ("element.id / value / checked", r"\.(?:value|checked|selected)\b", False, False),
    ("addEventListener", r"\.addEventListener\s*\(", True, True),
    ("DOMContentLoaded", r"DOMContentLoaded", True, True),
    ("window.onload / body onload", r"(?:window\.onload|\bonload\s*=)", True, True),
    ("event handlers (click/submit/input)", r"addEventListener\s*\(\s*['\"](?:click|submit|input|change|keyup|keydown|mouseover|mouseenter|scroll|resize)", False, False),
    ("event.preventDefault/target", r"\b(?:preventDefault|stopPropagation)\s*\(|\b(?:e|ev|event)\.target\b", False, True),
    ("getBoundingClientRect", r"\bgetBoundingClientRect\s*\(", True, True),
    ("offset*/client*/scroll* metrics", r"\.(?:offset|client|scroll)(?:Width|Height|Top|Left)\b", True, True),
    ("getComputedStyle", r"\bgetComputedStyle\s*\(", False, True),
    ("scrollTo/scrollIntoView/scrollBy", r"\b(?:scrollTo|scrollIntoView|scrollBy)\s*\(", True, True),
    ("setTimeout/setInterval", r"\bset(?:Timeout|Interval)\s*\(", True, True),
    ("requestAnimationFrame", r"\brequestAnimationFrame\s*\(", True, True),
    ("Promise/async", r"\bnew Promise\b|\basync\s+function\b|\bawait\b|\.then\s*\(", True, True),
    ("fetch/XMLHttpRequest", r"\bfetch\s*\(|XMLHttpRequest", False, False),
    ("localStorage/sessionStorage", r"\b(?:local|session)Storage\b", False, False),
    ("document.write", r"\bdocument\.write(?:ln)?\s*\(", False, True),
    ("matchMedia", r"\bmatchMedia\s*\(", True, False),
    ("IntersectionObserver/MutationObserver/ResizeObserver", r"\b(?:Intersection|Mutation|Resize)Observer\b", False, False),
    ("canvas getContext", r"\.getContext\s*\(", False, True),
    ("toLocaleString/Intl", r"\btoLocale(?:String|DateString|TimeString)\s*\(|\bIntl\.", False, False),
    ("Date", r"\bnew Date\b|\bDate\.now\s*\(", True, True),
    ("Math.random", r"\bMath\.random\s*\(", True, True),
    ("JSON.parse/stringify", r"\bJSON\.(?:parse|stringify)\s*\(", True, True),
    ("alert/confirm/prompt", r"\b(?:alert|confirm|prompt)\s*\(", False, False),
    ("location/history", r"\b(?:window\.location|location\.href|history\.(?:push|replace)State)\b", False, True),
    ("form elements (form.submit, elements, reset)", r"\.(?:submit|reset)\s*\(|\.elements\b", False, False),
    ("focus/blur", r"\.(?:focus|blur)\s*\(\s*\)", True, True),
    ("jQuery $()", r"(?:^|[^\w$.])\$\s*\(", False, False),
    ("Chart.js new Chart", r"\bnew Chart\s*\(", False, False),
    ("echarts.init", r"\becharts\.init\s*\(", False, False),
    ("d3.select", r"\bd3\.select", False, False),
]

SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.S | re.I)
SRC_RE = re.compile(r"\bsrc\s*=\s*['\"]?([^'\" >]+)", re.I)
ONATTR_RE = re.compile(r"\son[a-z]+\s*=\s*\"([^\"]*)\"", re.I)


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def websight_docs(cache, batches, offline):
    docs = []
    meta = []
    for config, total in (("v0.1", 822987), ("v0.2", 1922671)):
        step = total // batches
        for b in range(batches):
            offset = b * step
            path = os.path.join(cache, f"websight_{config}_{offset}.json")
            if not os.path.exists(path):
                if offline:
                    continue
                url = "https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode(
                    {"dataset": "HuggingFaceM4/WebSight", "config": config, "split": "train", "offset": offset, "length": 100})
                try:
                    text = get(url)
                    json.loads(text)
                except Exception as e:  # noqa: BLE001
                    meta.append({"config": config, "offset": offset, "error": str(e)[:200]})
                    continue
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            with open(path, encoding="utf-8") as f:
                rows = json.load(f).get("rows", [])
            for r in rows:
                docs.append((f"websight-{config}-{r.get('row_idx')}", r["row"]["text"]))
            meta.append({"config": config, "offset": offset, "rows": len(rows)})
    return docs, meta


def scripts_of(html):
    bodies = []
    hosts = []
    for attrs, body in SCRIPT_RE.findall(html):
        m = SRC_RE.search(attrs)
        if m:
            u = urllib.parse.urlparse(m.group(1))
            hosts.append(u.netloc or "(relative)")
        t = re.search(r"\btype\s*=\s*['\"]?([^'\" >]+)", attrs, re.I)
        if t and not re.search(r"javascript|ecmascript|module", t.group(1), re.I):
            continue
        if body.strip():
            bodies.append(body)
    bodies.extend(ONATTR_RE.findall(html))
    return "\n".join(bodies), hosts


def tally(docs):
    with_script = 0
    with_src = 0
    counts = Counter()
    hosts = Counter()
    for _, html in docs:
        js, srcs = scripts_of(html)
        for h in set(srcs):
            hosts[h] += 1
        if srcs:
            with_src += 1
        if not js.strip():
            continue
        with_script += 1
        for label, rx, _, _ in APIS:
            if re.search(rx, js, re.M):
                counts[label] += 1
    return {"docs": len(docs), "docs_with_inline_js": with_script, "docs_with_script_src": with_src,
            "api_doc_freq": dict(counts.most_common()), "script_src_hosts": dict(hosts.most_common(25))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--batches", type=int, default=30)
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    p5 = []
    for f in sorted(glob.glob(os.path.join(a.root, "phase5_js", "js", "cases", "dom", "*.js"))):
        with open(f, encoding="utf-8") as fh:
            p5.append((os.path.basename(f), "<script>" + fh.read() + "</script>"))
    spike = []
    for f in sorted(glob.glob(os.path.join(a.root, "spike_js_dom", "cases", "*.html"))):
        with open(f, encoding="utf-8") as fh:
            spike.append((os.path.basename(f), fh.read()))
    ws, ws_meta = websight_docs(a.cache, a.batches, a.offline)
    result = {
        "apis": [{"api": l, "spike_prelude": s, "raikiri_js": r} for l, _, s, r in APIS],
        "phase5_dom_cases": tally(p5),
        "websight": tally(ws),
        "websight_batches": ws_meta,
        "spike_cases": tally(spike),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    w = result["websight"]
    print(f"websight docs {w['docs']}, with inline js {w['docs_with_inline_js']}, with script src {w['docs_with_script_src']}")
    for k, v in list(w["api_doc_freq"].items())[:40]:
        print(f"  {v:5d}  {k}")
    print("phase5:", result["phase5_dom_cases"]["api_doc_freq"])


if __name__ == "__main__":
    main()
