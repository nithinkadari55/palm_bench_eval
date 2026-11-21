import argparse
import hashlib
import json
import os
import re
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from corpus_assets import build_assets  # noqa: E402
from corpus_gen import PAGE_H, PAGE_W, MARGIN, all_docs  # noqa: E402
from pdfcheck import PdfDoc  # noqa: E402

TIMEOUT = {"r04_stress_100_pages": 180}


def normalized_hash(path):
    with open(path, "rb") as f:
        b = f.read()
    raw = hashlib.sha256(b).hexdigest()
    s = re.sub(rb"/(CreationDate|ModDate)\s*\([^)]*\)", b"", b)
    s = re.sub(rb"/ID\s*\[\s*<[0-9A-Fa-f]*>\s*<[0-9A-Fa-f]*>\s*\]", b"", s)
    s = re.sub(rb"<xmp:(Create|Modify|Metadata)Date>[^<]*</xmp:\w+Date>", b"", s)
    s = re.sub(rb"<xmpMM:(Document|Instance)ID>[^<]*</xmpMM:\w+ID>", b"", s)
    return raw, hashlib.sha256(s).hexdigest()


def generic_checks(d, flags):
    out = []
    oob = d.out_of_bounds_chars()
    out.append({"cat": "text", "name": "[generic] no glyph outside the page", "ok": not oob, "detail": {"n": len(oob), "ex": oob[:5]}})
    if not flags.get("allow_overlap") and not flags.get("no_text"):
        n, ex = d.overlapping_lines()
        out.append({"cat": "layout", "name": "[generic] no overlapping text lines", "ok": n == 0, "detail": {"n": n, "ex": ex}})
    fonts = d.fonts()
    not_emb = [k for k, v in fonts.items() if not v["embedded"]]
    if fonts:
        out.append({"cat": "pdf", "name": "[generic] all fonts embedded", "ok": not not_emb, "detail": {"not_embedded": not_emb[:5]}})
    if not flags.get("no_text"):
        out.append({"cat": "pdf", "name": "[generic] text is extractable", "ok": any(p["chars"] for p in d.pages), "detail": {}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--work", default="/tmp/corpus")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    info = common.engine_info(a.engine)
    common.clean_dir(a.work)
    assets = build_assets(os.path.join(a.work, "assets"))
    docs = all_docs(assets)
    results = []
    for name, fn in docs.items():
        if a.only and not re.search(a.only, name):
            continue
        html, checks, flags = fn()
        src = os.path.join(a.work, name + ".html")
        with open(src, "w", encoding="utf-8") as f:
            f.write(html)
        rec = {"doc": name, "flags": flags, "checks": []}
        if info["output"] != "pdf":
            rec["status"] = "NOT_RUN"
            rec["detail"] = "engine has no PDF output"
            results.append(rec)
            continue
        out = os.path.join(a.work, name + ".pdf")
        geo = os.path.join(a.work, name + ".geometry.json")
        diag = os.path.join(a.work, name + ".diag.json")
        r = common.run_adapter(info, src, out, PAGE_W, PAGE_H, MARGIN, TIMEOUT.get(name, 60), geometry=geo, diagnostics=diag)
        rec["render"] = {k: r[k] for k in ("status", "rc", "elapsed_s", "peak_rss_mb")}
        rec["stderr"] = r["stderr"][-600:]
        if r["status"] != "OK":
            rec["status"] = r["status"]
            for c in checks:
                rec["checks"].append({"cat": c["cat"], "name": c["name"], "ok": False, "detail": {"render": r["status"]}})
            results.append(rec)
            continue
        rec["status"] = "OK"
        rec["pdf_bytes"] = os.path.getsize(out)
        for side, p in (("geometry", geo), ("diagnostics", diag)):
            try:
                with open(p, encoding="utf-8") as f:
                    j = json.load(f)
                rec[side] = "unsupported" if j.get("unsupported") else {"keys": list(j.keys())[:5], "size": os.path.getsize(p)}
            except Exception:
                rec[side] = "missing"
        try:
            d = PdfDoc(out, raster_dir=os.path.join(a.work, name + "_px"))
            rec["pages"] = d.n
            for c in checks:
                try:
                    ok, detail = c["fn"](d)
                except Exception as e:  # noqa: BLE001
                    ok, detail = False, {"check_error": repr(e)[:300]}
                rec["checks"].append({"cat": c["cat"], "name": c["name"], "ok": bool(ok), "detail": detail})
            rec["checks"] += generic_checks(d, flags)
        except Exception as e:  # noqa: BLE001
            rec["status"] = "PDF_UNREADABLE"
            rec["detail"] = traceback.format_exc()[-800:]
            for c in checks:
                rec["checks"].append({"cat": c["cat"], "name": c["name"], "ok": False, "detail": {"pdf": "unreadable"}})
        out2 = os.path.join(a.work, name + ".run2.pdf")
        r2 = common.run_adapter(info, src, out2, PAGE_W, PAGE_H, MARGIN, TIMEOUT.get(name, 60))
        if r2["status"] == "OK":
            h1, h2 = normalized_hash(out), normalized_hash(out2)
            rec["determinism"] = "byte_identical" if h1[0] == h2[0] else ("identical_after_metadata_strip" if h1[1] == h2[1] else "differs")
        else:
            rec["determinism"] = f"second_run_{r2['status']}"
        results.append(rec)
        print(name, rec["status"], sum(c["ok"] for c in rec["checks"]), "/", len(rec["checks"]), flush=True)
    common.write_json(a.out, {"engine": a.engine, "assets": {k: v for k, v in assets.items() if k != "green_data_uri"}, "results": results})


if __name__ == "__main__":
    main()
