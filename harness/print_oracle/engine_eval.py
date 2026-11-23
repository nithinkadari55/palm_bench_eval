import argparse
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from oracle_lib import (MARGIN_PX, PAGE_H_PX, PAGE_W_PX, doc_score, extract_tokens, fit, load_json, ssim, text_metrics,  # noqa: E402
                        to_gray_small)

import common  # noqa: E402

TIMEOUT = 120
N_WORST = 20
_G = {}


def init(engine, work, corpus):
    _G["info"] = common.engine_info(engine)
    _G["work"] = os.path.join(work, f"w{os.getpid()}")
    _G["corpus"] = corpus
    _G["keep"] = os.path.join(work, "first_pages")
    os.makedirs(_G["keep"], exist_ok=True)
    common.clean_dir(_G["work"])


def one(e):
    info, corpus = _G["info"], _G["corpus"]
    doc = e["id"]
    html = os.path.join(corpus, e["path"])
    out = os.path.join(_G["work"], doc + ".pdf")
    r = common.run_adapter(info, html, out, PAGE_W_PX, PAGE_H_PX, MARGIN_PX, TIMEOUT)
    rec = {"doc": doc, "category": e["category"], "source": e["source"], "status": r["status"], "rc": r["rc"],
           "elapsed_s": r["elapsed_s"], "peak_rss_mb": r["peak_rss_mb"]}
    if r["status"] != "OK":
        rec["stderr"] = r["stderr"][-400:]
        return rec
    orc = load_json(os.path.join(corpus, "oracle", doc + ".json"))
    try:
        pages_e, toks_e = extract_tokens(out)
        nc, ne = len(orc["pages"]), len(pages_e)
        rec.update(pages_chrome=nc, pages_engine=ne, page_delta=ne - nc, page_exact=ne == nc)
        rec.update(text_metrics(orc["tokens"], toks_e))
        if ne:
            rec["page_size_px"] = pages_e[0]
        with np.load(os.path.join(corpus, "oracle", doc + ".npz")) as z:
            small_c = [z[f"arr_{k}"] for k in range(len(z.files))]
        rdir = os.path.join(_G["work"], doc + "_px")
        files = common.rasterize(out, rdir)
        per = []
        for k in range(max(len(small_c), len(files))):
            if k >= len(small_c) or k >= len(files):
                per.append(0.0)
                continue
            h, w = orc["raster_sizes"][k]
            img = fit(common.load_rgb(files[k]), h, w)
            if k == 0:
                rec["blank_p1"] = common.is_blank(img)
            per.append(round(ssim(to_gray_small(img), small_c[k]), 4))
        if files:
            shutil.copyfile(files[0], os.path.join(_G["keep"], doc + ".png"))
        shutil.rmtree(rdir, ignore_errors=True)
        common_n = min(len(small_c), len(files))
        rec["ssim_pages"] = per
        rec["ssim_mean"] = round(float(np.mean(per)), 4) if per else None
        rec["ssim_common"] = round(float(np.mean(per[:common_n])), 4) if common_n else None
        rec["ssim_p1"] = per[0] if per else None
    except Exception as ex:  # noqa: BLE001
        rec["status"] = "EVAL_ERROR"
        rec["detail"] = repr(ex)[:300]
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    rec["score"] = doc_score(rec)
    return rec


def mean(v):
    v = [x for x in v if x is not None]
    return round(float(np.mean(v)), 4) if v else None


def median(v):
    v = [x for x in v if x is not None]
    return round(float(np.median(v)), 3) if v else None


def pct(v, q):
    v = [x for x in v if x is not None]
    return round(float(np.percentile(v, q)), 3) if v else None


def aggregate(rs):
    ok = [r for r in rs if r["status"] == "OK"]
    n = len(rs)
    return {
        "n": n, "ok": len(ok), "ok_rate": round(len(ok) / n, 4) if n else None, "status": dict(Counter(r["status"] for r in rs)),
        "score": round(sum(r.get("score", 0.0) for r in rs) / n, 4) if n else None,
        "page_exact": round(sum(1 for r in ok if r.get("page_exact")) / n, 4) if n else None,
        "page_abs_delta_mean": mean([abs(r["page_delta"]) for r in ok if "page_delta" in r]),
        "page_agree": mean([r.get("page_agree") for r in ok]),
        "page_agree_strict": mean([r.get("page_agree_strict") for r in ok]),
        "recall": mean([r.get("recall") for r in ok]),
        "precision": mean([r.get("precision") for r in ok]),
        "seq_recall": mean([r.get("seq_recall") for r in ok]),
        "dx_med": median([r.get("dx_med") for r in ok]), "dx_p90": median([r.get("dx_p90") for r in ok]),
        "dy_med": median([r.get("dy_med") for r in ok]), "dy_p90": median([r.get("dy_p90") for r in ok]),
        "pos_within_2px": mean([r.get("pos_within_2px") for r in ok]),
        "ssim_mean": mean([r.get("ssim_mean") for r in ok]), "ssim_p1": mean([r.get("ssim_p1") for r in ok]),
        "ssim_common": mean([r.get("ssim_common") for r in ok]),
        "blank_p1": sum(1 for r in ok if r.get("blank_p1")),
        "elapsed_p50": pct([r["elapsed_s"] for r in ok], 50), "elapsed_p95": pct([r["elapsed_s"] for r in ok], 95),
        "rss_p95_mb": pct([r["peak_rss_mb"] for r in ok], 95),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--worst-dir", required=True)
    ap.add_argument("--work", default="/tmp/print-oracle")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    man = load_json(os.path.join(a.corpus, "manifest.json"))
    cmeta = load_json(os.path.join(a.corpus, "chrome_meta.json"), {})
    chrome_ok = {r["id"] for r in cmeta.get("results", []) if r["status"] == "OK"}
    docs = [e for e in man["docs"] if e["id"] in chrome_ok]
    skipped = [e["id"] for e in man["docs"] if e["id"] not in chrome_ok]
    if a.limit:
        docs = docs[:a.limit]
    common.clean_dir(a.work)
    t0 = time.monotonic()
    res = []
    with mp.Pool(a.jobs, initializer=init, initargs=(a.engine, a.work, a.corpus)) as pool:
        for k, rec in enumerate(pool.imap_unordered(one, docs, chunksize=1)):
            res.append(rec)
            if rec["status"] != "OK" or k % 50 == 0:
                print(k, rec["doc"], rec["status"], rec.get("score"), rec["elapsed_s"], flush=True)
    res.sort(key=lambda r: r["doc"])
    by_cat, by_src = defaultdict(list), defaultdict(list)
    for r in res:
        by_cat[r["category"]].append(r)
        by_src[r["source"]].append(r)
    common.clean_dir(a.worst_dir)
    ok = sorted([r for r in res if r["status"] == "OK"], key=lambda r: (r["score"], r["doc"]))
    worst = []
    for r in ok[:N_WORST]:
        doc = r["doc"]
        src = os.path.join(a.work, "first_pages", doc + ".png")
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(a.worst_dir, f"{doc}__{a.engine}.png"))
        try:
            files = common.rasterize(os.path.join(a.corpus, "chrome", doc + ".pdf"), os.path.join(a.work, "chrome_px", doc))
            if files:
                shutil.copyfile(files[0], os.path.join(a.worst_dir, f"{doc}__chrome.png"))
        except Exception as ex:  # noqa: BLE001
            print("chrome raster failed", doc, ex)
        worst.append({k: r.get(k) for k in ("doc", "category", "score", "pages_chrome", "pages_engine", "page_agree_strict", "recall", "precision", "ssim_mean")})
    out = {"engine": a.engine, "engine_info": {k: v for k, v in common.engine_info(a.engine).items() if k in ("name", "repo", "sha", "license")},
           "chrome_version": cmeta.get("version"), "wall_s": round(time.monotonic() - t0, 1), "skipped_no_oracle": skipped,
           "overall": aggregate(res), "by_category": {k: aggregate(v) for k, v in sorted(by_cat.items())},
           "by_source": {k: aggregate(v) for k, v in sorted(by_src.items())}, "worst": worst, "results": res}
    common.write_json(a.out, out)
    print(json.dumps(out["overall"], indent=1))


if __name__ == "__main__":
    main()
