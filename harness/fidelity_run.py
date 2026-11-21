import argparse
import json
import multiprocessing as mp
import os
import re
import sys
from collections import Counter

import numpy as np
from bs4 import BeautifulSoup
from PIL import Image
from skimage.metrics import structural_similarity

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

TIMEOUT = 60
_G = {}
WORD = re.compile(r"[^\W_]+", re.U)


def visible_words(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "template", "head"]):
        t.decompose()
    return Counter(w.lower() for w in WORD.findall(soup.get_text(" ")))


def to_gray_small(arr, width=320):
    im = Image.fromarray(arr.astype(np.uint8))
    h = max(8, int(im.height * width / im.width))
    return np.asarray(im.convert("L").resize((width, h), Image.BILINEAR), dtype=np.float64)


def init(engine, work):
    _G["info"] = common.engine_info(engine)
    _G["work"] = os.path.join(work, f"w{os.getpid()}")
    common.clean_dir(_G["work"])


def one(args):
    src_html, ref_png = args
    info = _G["info"]
    name = os.path.basename(src_html)[:-5]
    ref = common.load_rgb(ref_png)
    H, W = ref.shape[:2]
    is_pdf = info["output"] == "pdf"
    out = os.path.join(_G["work"], name + (".pdf" if is_pdf else ".png"))
    r = common.run_adapter(info, src_html, out, W, H, 0, TIMEOUT)
    rec = {"doc": name, "status": r["status"], "elapsed_s": r["elapsed_s"], "peak_rss_mb": r["peak_rss_mb"]}
    if r["status"] != "OK":
        rec["stderr"] = r["stderr"][-300:]
        return rec
    try:
        if is_pdf:
            pages = common.rasterize(out, os.path.join(_G["work"], name + "_px"))
            rec["pages"] = len(pages)
            img = common.load_rgb(pages[0])
        else:
            img = common.load_rgb(out)
        if img.shape[:2] != (H, W):
            canvas = np.full((H, W, 3), 255, dtype=np.int16)
            hh, ww = min(H, img.shape[0]), min(W, img.shape[1])
            canvas[:hh, :ww] = img[:hh, :ww]
            img = canvas
        a, b = to_gray_small(img), to_gray_small(ref)
        rec["ssim"] = round(float(structural_similarity(a, b, data_range=255)), 4)
        rec["mean_abs_diff"] = round(float(np.abs(img - ref).mean()), 2)
        rec["blank"] = common.is_blank(img)
        if is_pdf:
            from pdfcheck import PdfDoc
            d = PdfDoc(out)
            got = Counter(w.lower() for w in WORD.findall(d.all_text()))
            with open(src_html, encoding="utf-8", errors="replace") as f:
                want = visible_words(f.read())
            tot = sum(want.values())
            hit = sum(min(c, got.get(w, 0)) for w, c in want.items())
            rec["text_recall"] = round(hit / tot, 4) if tot else None
    except Exception as e:  # noqa: BLE001
        rec["status"] = "EVAL_ERROR"
        rec["detail"] = repr(e)[:300]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", default="/tmp/fidelity")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    items = []
    for fn in sorted(os.listdir(a.data)):
        if fn.endswith(".html"):
            png = os.path.join(a.data, fn[:-5] + ".png")
            if os.path.exists(png):
                items.append((os.path.join(a.data, fn), png))
    common.clean_dir(a.work)
    with mp.Pool(a.jobs, initializer=init, initargs=(a.engine, a.work)) as pool:
        res = list(pool.imap(one, items, chunksize=2))
    summ = {}
    for prefix in ("d2c", "ws"):
        rs = [r for r in res if r["doc"].startswith(prefix)]
        ok = [r for r in rs if r["status"] == "OK"]
        summ[prefix] = {
            "n": len(rs),
            "ok": len(ok),
            "status": dict(Counter(r["status"] for r in rs)),
            "ssim_mean": round(float(np.mean([r["ssim"] for r in ok])), 4) if ok else None,
            "ssim_median": round(float(np.median([r["ssim"] for r in ok])), 4) if ok else None,
            "text_recall_mean": round(float(np.mean([r["text_recall"] for r in ok if r.get("text_recall") is not None])), 4) if any(r.get("text_recall") is not None for r in ok) else None,
            "blank": sum(1 for r in ok if r.get("blank")),
            "elapsed_p50": round(float(np.median([r["elapsed_s"] for r in ok])), 3) if ok else None,
            "elapsed_p95": round(float(np.percentile([r["elapsed_s"] for r in ok], 95)), 3) if ok else None,
            "rss_p95_mb": round(float(np.percentile([r["peak_rss_mb"] or 0 for r in ok], 95)), 1) if ok else None,
        }
    common.write_json(a.out, {"engine": a.engine, "summary": summ, "results": res})
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
