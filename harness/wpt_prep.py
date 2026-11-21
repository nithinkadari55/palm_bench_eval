import argparse
import json
import os
import re

TEST_EXT = (".html", ".htm", ".xht", ".xhtml")
REWRITE_EXT = (".html", ".htm", ".xht", ".xhtml", ".css", ".svg", ".xml")
SKIP_DIRS = {"support", "resources", "reference", "tools", "META.yml", "__dir__", "crashtests-support"}

ATTR_RE = re.compile(r"""(\b(?:href|src|xlink:href|data|poster|srcset)\s*=\s*["'])/(?!/)""", re.I)
URL_RE = re.compile(r"""(url\(\s*["']?)/(?!/)""", re.I)
IMPORT_RE = re.compile(r"""(@import\s+["'])/(?!/)""", re.I)
LINK_RE = re.compile(r"""<link\b[^>]*>""", re.I | re.S)
META_RE = re.compile(r"""<meta\b[^>]*>""", re.I | re.S)
ATTRV_RE = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.S)


def attrs(tag):
    out = {}
    for m in ATTRV_RE.finditer(tag):
        out[m.group(1).lower()] = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else m.group(4))
    return out


def rewrite_tree(wpt_root):
    count = 0
    for dirpath, _, files in os.walk(wpt_root):
        if "/.git" in dirpath.replace("\\", "/"):
            continue
        rel = os.path.relpath(wpt_root, dirpath).replace("\\", "/")
        prefix = "" if rel == "." else rel + "/"
        for fn in files:
            if not fn.lower().endswith(REWRITE_EXT):
                continue
            p = os.path.join(dirpath, fn)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    s = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            s2 = ATTR_RE.sub(lambda m: m.group(1) + prefix, s)
            s2 = URL_RE.sub(lambda m: m.group(1) + prefix, s2)
            s2 = IMPORT_RE.sub(lambda m: m.group(1) + prefix, s2)
            if s2 != s:
                with open(p, "w", encoding="utf-8", newline="") as f:
                    f.write(s2)
                count += 1
    return count


def parse_fuzzy(content):
    ref = None
    c = content.strip()
    m = re.match(r"^([^:;=]+\.(?:html?|xht|xhtml|svg)):(.*)$", c)
    if m:
        ref, c = m.group(1), m.group(2)
    parts = [p.strip() for p in c.split(";") if p.strip()]
    vals = {}
    pos = ["maxDifference", "totalPixels"]
    for i, p in enumerate(parts):
        if "=" in p:
            k, v = p.split("=", 1)
            k = k.strip()
        else:
            k, v = pos[i] if i < 2 else f"x{i}", p
        v = v.strip()
        if "-" in v:
            lo, hi = v.split("-", 1)
        else:
            lo = hi = v
        try:
            vals[k] = [int(lo), int(hi)]
        except ValueError:
            pass
    return {"ref": ref, "maxDifference": vals.get("maxDifference", [0, 0]), "totalPixels": vals.get("totalPixels", [0, 0])}


def classify(path, rel, text):
    low = rel.lower()
    name = os.path.basename(low)
    info = {"path": rel}
    base = name.rsplit(".", 1)[0]
    info["print"] = base.endswith("-print") or "/print/" in "/" + low
    info["tentative"] = ".tentative." in name or "/tentative/" in low
    info["has_script"] = bool(re.search(r"<script\b", text, re.I))
    info["reftest_wait"] = bool(re.search(r"""class\s*=\s*["'][^"']*\breftest-wait\b""", text, re.I))
    refs = []
    for tag in LINK_RE.findall(text):
        a = attrs(tag)
        relv = (a.get("rel") or "").lower().split()
        if "match" in relv or "mismatch" in relv:
            refs.append({"rel": "match" if "match" in relv else "mismatch", "href": a.get("href", "")})
    fuzzy = []
    pages = None
    for tag in META_RE.findall(text):
        a = attrs(tag)
        n = (a.get("name") or "").lower()
        if n == "fuzzy" and a.get("content"):
            fuzzy.append(parse_fuzzy(a["content"]))
        elif n == "reftest-pages" and a.get("content"):
            pages = a["content"]
    info["refs"] = refs
    info["fuzzy"] = fuzzy
    info["pages"] = pages
    if "/crashtests/" in "/" + low or base.endswith("-crash"):
        info["kind"] = "crashtest"
    elif "-manual" in base:
        info["kind"] = "manual"
    elif refs:
        info["kind"] = "reftest"
    elif re.search(r"testharness\.js", text):
        info["kind"] = "testharness"
    else:
        info["kind"] = "other"
    return info


def is_reference_file(rel):
    low = rel.lower()
    name = os.path.basename(low).rsplit(".", 1)[0]
    return ("-ref" in name or name.endswith("ref") or "/reference/" in "/" + low or "/ref/" in "/" + low
            or name.startswith("ref-") or "-notref" in name)


def build_manifest(wpt_root, suites):
    tests = []
    for suite in suites:
        sdir = os.path.join(wpt_root, suite)
        for dirpath, dirnames, files in os.walk(sdir):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in sorted(files):
                if not fn.lower().endswith(TEST_EXT):
                    continue
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, wpt_root).replace("\\", "/")
                if is_reference_file(rel):
                    continue
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                info = classify(p, rel, text)
                info["suite"] = suite
                tests.append(info)
    return tests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wpt", required=True)
    ap.add_argument("--suites", required=True, help="comma-separated, e.g. css/css-break,css/css-page")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-rewrite", action="store_true")
    a = ap.parse_args()
    if not a.no_rewrite:
        n = rewrite_tree(a.wpt)
        print(f"rewrote root-relative URLs in {n} files")
    tests = build_manifest(a.wpt, [s.strip() for s in a.suites.split(",") if s.strip()])
    kinds = {}
    for t in tests:
        kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
    print(json.dumps({"total": len(tests), "kinds": kinds}))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(tests, f, indent=0)


if __name__ == "__main__":
    main()
