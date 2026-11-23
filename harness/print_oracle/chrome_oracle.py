import argparse
import json
import multiprocessing as mp
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from oracle_lib import extract_tokens, to_gray_small  # noqa: E402

import common  # noqa: E402

CHROME_FLAGS = ["--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer", "--virtual-time-budget=5000"]
EXTRA_FLAGS = ["--host-resolver-rules=MAP * ~NOTFOUND", "--no-first-run", "--no-default-browser-check", "--disable-extensions"]
TIMEOUT = 120
_G = {}


def chrome_bin():
    for b in (os.environ.get("CHROME_BIN"), "google-chrome", "google-chrome-stable", "chromium", "msedge"):
        if b and shutil.which(b):
            return shutil.which(b)
    raise SystemExit("no chrome binary found")


def chrome_version(binary):
    r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip()


def render(binary, html_path, pdf_path, profile):
    if os.path.exists(pdf_path):
        os.unlink(pdf_path)
    cmd = [binary, *CHROME_FLAGS, *EXTRA_FLAGS, f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}",
           pathlib.Path(os.path.abspath(html_path)).as_uri()]
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    status = "OK"
    try:
        _, err = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            proc.kill()
        _, err = proc.communicate()
        status = "TIMEOUT"
    el = round(time.monotonic() - t0, 3)
    if status == "OK" and not (os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0):
        status = "ERROR"
    return status, el, (err or b"").decode("utf-8", "replace")[-600:]


def init(binary, work):
    _G["bin"] = binary
    _G["profile"] = tempfile.mkdtemp(prefix=f"chrome-prof-{os.getpid()}-", dir=work)


def oracle_data(pdf, out_dir, doc_id):
    pages, toks = extract_tokens(pdf)
    rdir = os.path.join(out_dir, "_px", doc_id)
    files = common.rasterize(pdf, rdir)
    small, sizes = [], []
    for f in files:
        img = common.load_rgb(f)
        sizes.append([int(img.shape[0]), int(img.shape[1])])
        small.append(to_gray_small(img))
    shutil.rmtree(rdir, ignore_errors=True)
    np.savez_compressed(os.path.join(out_dir, doc_id + ".npz"), *small)
    with open(os.path.join(out_dir, doc_id + ".json"), "w", encoding="utf-8") as f:
        json.dump({"pages": pages, "raster_sizes": sizes, "tokens": toks}, f, ensure_ascii=False, separators=(",", ":"))
    return len(pages), len(toks)


def one(args):
    corpus, e = args
    html = os.path.join(corpus, e["path"])
    pdf = os.path.join(corpus, "chrome", e["id"] + ".pdf")
    status, el, err = render(_G["bin"], html, pdf, _G["profile"])
    rec = {"id": e["id"], "status": status, "elapsed_s": el}
    if status != "OK":
        rec["stderr"] = err
        return rec
    try:
        n, nt = oracle_data(pdf, os.path.join(corpus, "oracle"), e["id"])
        rec["pages"] = n
        rec["words"] = nt
    except Exception as ex:  # noqa: BLE001
        rec["status"] = "EXTRACT_ERROR"
        rec["detail"] = repr(ex)[:300]
    return rec


def probe(binary, work):
    """Check that Chrome's CLI print path keeps backgrounds and applies the injected A4 @page."""
    from oracle_lib import prepare_html
    html = os.path.join(work, "probe.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write(prepare_html('<!DOCTYPE html><html><head></head><body><div style="background:#ff0000;height:300px">x</div></body></html>', "x.png"))
    pdf = os.path.join(work, "probe.pdf")
    status, _, err = render(binary, html, pdf, tempfile.mkdtemp(dir=work))
    out = {"status": status}
    if status == "OK":
        from pypdf import PdfReader
        mb = PdfReader(pdf).pages[0].mediabox
        out["page_pt"] = [round(float(mb.width), 2), round(float(mb.height), 2)]
        files = common.rasterize(pdf, os.path.join(work, "probe_px"))
        img = common.load_rgb(files[0])
        y, x = 57 + 100, 57 + 100
        out["pixel_at_bg"] = [int(v) for v in img[y, x]]
        out["backgrounds_printed"] = bool(img[y, x, 0] > 200 and img[y, x, 1] < 80)
    else:
        out["stderr"] = err
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    with open(os.path.join(a.corpus, "manifest.json"), encoding="utf-8") as f:
        man = json.load(f)
    binary = chrome_bin()
    work = a.work or tempfile.mkdtemp(prefix="po-chrome-")
    os.makedirs(work, exist_ok=True)
    for d in ("chrome", "oracle"):
        common.clean_dir(os.path.join(a.corpus, d))
    ver = chrome_version(binary)
    print("chrome:", binary, ver, flush=True)
    pr = probe(binary, work)
    print("probe:", json.dumps(pr), flush=True)
    items = [(a.corpus, e) for e in man["docs"]]
    t0 = time.monotonic()
    with mp.Pool(a.jobs, initializer=init, initargs=(binary, work)) as pool:
        res = []
        for k, rec in enumerate(pool.imap(one, items, chunksize=1)):
            res.append(rec)
            if rec["status"] != "OK" or k % 50 == 0:
                print(k, rec["id"], rec["status"], rec.get("pages"), rec["elapsed_s"], flush=True)
    meta = {"binary": binary, "version": ver, "flags": CHROME_FLAGS + EXTRA_FLAGS, "probe": pr, "wall_s": round(time.monotonic() - t0, 1),
            "ok": sum(1 for r in res if r["status"] == "OK"), "n": len(res), "results": res}
    common.write_json(os.path.join(a.corpus, "chrome_meta.json"), meta)
    print(json.dumps({k: meta[k] for k in ("version", "ok", "n", "wall_s")}))


if __name__ == "__main__":
    main()
