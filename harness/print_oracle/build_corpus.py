import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_docs  # noqa: E402
from oracle_lib import DEFAULT_PAGE_CSS, prepare_html, write_placeholder  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="corpus directory (recreated)")
    ap.add_argument("--cache", default=None, help="download cache for public samples / WebSight")
    ap.add_argument("--websight", type=int, default=100)
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()
    shutil.rmtree(a.out, ignore_errors=True)
    os.makedirs(os.path.join(a.out, "docs"))
    ph = os.path.join(a.out, "assets", "placeholder.png")
    write_placeholder(ph)
    entries = []
    for e in gen_docs.generate(os.path.join(a.out, "docs"), a.scale):
        e["path"] = "docs/" + e.pop("file")
        entries.append(e)
    if not a.no_network:
        import fetch_public
        cache = a.cache or os.path.join(a.out, "_cache")
        entries += fetch_public.fetch_public(cache, a.out)
        entries += fetch_public.fetch_websight(cache, a.out, a.websight)
    seen = set()
    for e in entries:
        assert e["id"] not in seen, e["id"]
        seen.add(e["id"])
        p = os.path.join(a.out, e["path"])
        with open(p, encoding="utf-8", errors="replace") as f:
            s = f.read()
        rel = os.path.relpath(ph, os.path.dirname(p)).replace(os.sep, "/")
        s = prepare_html(s, rel)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(s)
        e["sha256"] = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
        e["bytes"] = len(s.encode("utf-8"))
    man = {"generator": gen_docs.GEN_VERSION, "default_page_css": DEFAULT_PAGE_CSS, "count": len(entries),
           "by_source": dict(Counter(e["source"] for e in entries)), "by_category": dict(Counter(e["category"] for e in entries)),
           "docs": entries}
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: man[k] for k in ("count", "by_source", "by_category")}, indent=1))


if __name__ == "__main__":
    main()
