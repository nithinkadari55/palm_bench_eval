import glob
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def engine_info(engine):
    with open(os.path.join(ROOT, "engines", engine, "ENGINE.json"), encoding="utf-8") as f:
        info = json.load(f)
    info["bin"] = os.path.join(ROOT, "engines", engine, "bin", f"adapter-{engine}")
    return info


def run_adapter(info, input_path, out_path, w, h, margin, timeout, geometry=None, diagnostics=None):
    cmd = [info["bin"], "render", input_path, out_path,
           "--page-width-px", str(w), "--page-height-px", str(h), "--margin-px", str(margin)]
    if geometry:
        cmd += ["--geometry", geometry]
    if diagnostics:
        cmd += ["--diagnostics", diagnostics]
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".time")
    tfile.close()
    full = ["/usr/bin/time", "-o", tfile.name, "-f", "%M %e"] + cmd
    start = time.monotonic()
    proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True, cwd=os.path.dirname(input_path) or None)
    status = "OK"
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        status = "TIMEOUT"
    elapsed = time.monotonic() - start
    peak_kb = None
    try:
        with open(tfile.name) as f:
            line = f.read().strip().splitlines()[-1]
            peak_kb = int(line.split()[0])
    except Exception:
        pass
    os.unlink(tfile.name)
    rc = proc.returncode
    if status != "TIMEOUT":
        if rc == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            status = "OK"
        elif rc in (101, 134, 139, -6, -11) or rc < 0 or rc >= 128:
            status = "CRASH"
        else:
            status = "ERROR"
    return {
        "status": status,
        "rc": rc,
        "elapsed_s": round(elapsed, 3),
        "peak_rss_mb": round(peak_kb / 1024, 1) if peak_kb else None,
        "stderr": (err or b"").decode("utf-8", "replace")[-2000:],
    }


def rasterize(pdf_path, out_dir, dpi=96):
    os.makedirs(out_dir, exist_ok=True)
    prefix = os.path.join(out_dir, "p")
    r = subprocess.run(["pdftoppm", "-r", str(dpi), "-png", pdf_path, prefix],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("pdftoppm failed: " + r.stderr.decode("utf-8", "replace")[-500:])
    files = glob.glob(prefix + "-*.png")
    files.sort(key=lambda p: int(p.rsplit("-", 1)[1].split(".")[0]))
    return files


def load_rgb(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    return np.asarray(im.convert("RGB"), dtype=np.int16)


def compare(a, b):
    if a.shape != b.shape:
        return {"same_size": False, "max_diff": 255, "diff_pixels": int(max(a.size, b.size) // 3)}
    d = np.abs(a - b)
    per_px = d.max(axis=2)
    return {"same_size": True, "max_diff": int(per_px.max()), "diff_pixels": int((per_px > 0).sum())}


def is_blank(arr):
    return bool((arr >= 250).all())


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def clean_dir(path):
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
