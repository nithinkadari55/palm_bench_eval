"""Runs the spike cases on one engine binary and checks the PDFs with harness/pdfcheck.py.

usage: python run_cases.py --engine rkjs --bin <binary> --cases spike_js_dom/cases
           --assets <dir with shims.js/echarts.js> [--phase5 <dir of generated pages>]
           --work <dir> --out <results.json>
"""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "harness"))

import numpy as np  # noqa: E402
import pdfcheck  # noqa: E402


def run(binary, html, work, page, timeout):
    os.makedirs(work, exist_ok=True)
    out = {k: os.path.join(work, v) for k, v in (
        ("pdf", "out.pdf"), ("geometry", "geometry.json"), ("diagnostics", "diagnostics.json"),
        ("metrics", "metrics.json"), ("html", "final.html"))}
    cmd = [binary, "render", html, out["pdf"], "--page-width-px", str(page["width_px"]),
           "--page-height-px", str(page["height_px"]), "--margin-px", str(page["margin_px"]),
           "--geometry", out["geometry"], "--diagnostics", out["diagnostics"], "--metrics", out["metrics"],
           "--dump-html", out["html"]]
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".time")
    tfile.close()
    timer = ["/usr/bin/time", "-o", tfile.name, "-f", "%M %e"] if os.path.exists("/usr/bin/time") else []
    start = time.monotonic()
    proc = subprocess.Popen(timer + cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True, cwd=os.path.dirname(html))
    status = "OK"
    try:
        _, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        _, err = proc.communicate()
        status = "TIMEOUT"
    wall = time.monotonic() - start
    peak = None
    try:
        with open(tfile.name) as f:
            peak = int(f.read().strip().splitlines()[-1].split()[0])
    except Exception:  # noqa: BLE001
        pass
    os.unlink(tfile.name)
    rc = proc.returncode
    if status != "TIMEOUT":
        if rc == 0 and os.path.exists(out["pdf"]) and os.path.getsize(out["pdf"]) > 0:
            status = "OK"
        elif rc is None or rc < 0 or rc >= 100:
            status = "CRASH"
        else:
            status = "ERROR"
    with open(os.path.join(work, "stderr.txt"), "wb") as f:
        f.write(err or b"")
    return {"status": status, "rc": rc, "wall_s": round(wall, 3),
            "peak_rss_mb": round(peak / 1024, 1) if peak else None,
            "stderr_tail": (err or b"").decode("utf-8", "replace")[-1500:]}, out


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def box_by_id(geometry, ident):
    for page in geometry.get("pages", []):
        for b in page.get("boxes", []):
            if b.get("id") == ident:
                return page["index"], b
    return None, None


def close(rgb, target, tol):
    return rgb is not None and all(abs(int(a) - int(b)) <= tol for a, b in zip(rgb, target))


def raster_run(doc, page_index, box, colors, tol=40):
    """Width of the contiguous run of `colors` on the row through the middle of `box`."""
    img = doc.raster()[page_index]
    h, w = img.shape[:2]
    y = int(round(box["y"] + box["h"] / 2))
    if not 0 <= y < h:
        return None
    row = img[y]
    def match(px):
        return any(close(px, c, tol) for c in colors)
    x = max(0, int(box["x"]) - 4)
    end = min(w, int(box["x"] + box["w"]) + 40)
    while x < end and not match(row[x]):
        x += 1
    if x >= end:
        return 0
    start = x
    while x < w and match(row[x]):
        x += 1
    return x - start


def check_case(case, doc, text, diags, geometry, metrics):
    results = []
    ntext = pdfcheck.norm(text)
    for c in case.get("checks", []):
        t = c["type"]
        required = c.get("required", True)
        ok, detail = False, ""
        try:
            if t == "text":
                ok = pdfcheck.norm(c["value"]) in ntext
                desc = f"text '{c['value']}'"
            elif t == "absent":
                ok = pdfcheck.norm(c["value"]) not in ntext
                desc = f"no text '{c['value']}'"
            elif t == "regex":
                m = re.search(c["value"], text)
                ok = m is not None
                detail = m.group(0) if m else ""
                desc = f"regex /{c['value']}/"
            elif t == "order":
                pos = []
                for v in c["values"]:
                    hits = doc.find(v)
                    pos.append((hits[0]["page"], round(hits[0]["y0"]), hits[0]["x0"]) if hits else None)
                ok = all(p is not None for p in pos) and pos == sorted(pos)
                detail = str(pos)
                desc = "order " + " < ".join(c["values"])
            elif t == "pixel_near_text":
                hits = doc.find(c["text"])
                desc = c.get("desc", f"pixel near '{c['text']}'")
                if hits:
                    hit = hits[0]
                    rgb = doc.pixel(hit["page"], hit["x0"] + c.get("dx", 0), (hit["y0"] + hit["y1"]) / 2, r=1)
                    ok = close(rgb, c["rgb"], c.get("tol", 24))
                    detail = f"rgb {rgb} want {c['rgb']}"
                else:
                    detail = "text not found"
            elif t == "color_count":
                desc = c.get("desc", f"pixels near {c['rgb']}")
                n = 0
                for img in doc.raster():
                    d = np.abs(img - np.array(c["rgb"], dtype=np.int16)).max(axis=2)
                    n += int((d <= c.get("tol", 40)).sum())
                ok = n >= c["min"]
                detail = f"{n} px (min {c['min']})"
            elif t == "diag":
                desc = c.get("desc", f"diagnostic {c['kind']} ~ {c['contains']}")
                hits = [d for d in diags if d.get("kind", "").startswith(c["kind"]) and re.search(c["contains"], d.get("message", ""), re.I)]
                ok = bool(hits)
                detail = hits[0]["message"][:200] if hits else f"{len(diags)} diagnostics, none matched"
            elif t == "no_diag":
                desc = c.get("desc", f"no diagnostic {c['kind']}")
                hits = [d for d in diags if d.get("kind", "").startswith(c["kind"])]
                ok = not hits
                detail = "; ".join(h.get("message", "")[:160] for h in hits[:3])
            elif t == "width_text":
                desc = f"/{c['regex']}/ = laid-out width of #{c['id']}"
                m = re.search(c["regex"], text)
                pi, box = box_by_id(geometry, c["id"])
                parts = []
                if not m:
                    detail = "value not found in PDF text"
                elif box is None:
                    detail = f"#{c['id']} not in geometry"
                else:
                    v = float(m.group(1))
                    tol = c.get("tol", 1)
                    ok = abs(v - box["w"]) <= tol
                    parts.append(f"text {v} vs final layout {box['w']}")
                    if "expect" in c:
                        ok = ok and abs(v - c["expect"]) <= tol
                        parts.append(f"expected {c['expect']}")
                    if c.get("raster_rgb"):
                        run_w = raster_run(doc, pi, box, c["raster_rgb"])
                        ok = ok and run_w is not None and abs(v - run_w) <= tol + 0.5
                        parts.append(f"painted run {run_w}px")
                    detail = ", ".join(parts)
            elif t == "metric":
                desc = c.get("desc", f"metric {c['key']} {c['op']} {c['value']}")
                v = metrics.get(c["key"])
                ops = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}
                ok = v is not None and ops[c["op"]](v, c["value"])
                detail = f"{c['key']} = {v}"
            else:
                desc = f"unknown check {t}"
        except Exception as e:  # noqa: BLE001
            desc = locals().get("desc", t)
            detail = f"check error: {e}"
            ok = False
        results.append({"type": t, "desc": desc, "ok": bool(ok), "required": required, "detail": detail})
    return results


def phase5_checks(expect):
    checks = []
    for e in expect:
        if e.startswith("re:"):
            checks.append({"type": "regex", "value": e[3:]})
        elif e.startswith("!"):
            checks.append({"type": "absent", "value": e[1:]})
        else:
            checks.append({"type": "text", "value": e})
    checks.append({"type": "no_diag", "kind": "js:uncaught", "required": False, "desc": "no uncaught script errors"})
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--bin", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--phase5")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    spec = load_json(os.path.join(a.cases, "checks.json"), {})
    page = spec["page"]
    timeout = spec.get("timeout_s", 120)
    jobs = []
    for cid, case in spec["cases"].items():
        jobs.append(("spike", cid, os.path.join(a.cases, cid + ".html"), case))
    if a.phase5 and os.path.isdir(a.phase5):
        for pid, expect in spec.get("phase5_dom", {}).items():
            path = os.path.join(a.phase5, pid + ".html")
            if os.path.exists(path):
                jobs.append(("phase5_dom", pid, path, {"title": "phase 5 DOM case " + pid, "checks": phase5_checks(expect)}))
    results = {"engine": a.engine, "binary": a.bin, "binary_exists": os.path.exists(a.bin), "cases": []}
    for group, cid, src, case in jobs:
        work = os.path.join(a.work, a.engine, group, cid)
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        html = os.path.join(work, "input.html")
        shutil.copy(src, html)
        for asset in case.get("assets", []):
            for d in (a.assets, os.path.join(a.cases, "assets")):
                p = os.path.join(d, asset)
                if os.path.exists(p):
                    shutil.copy(p, os.path.join(work, asset))
                    break
        entry = {"group": group, "case": cid, "title": case.get("title", cid)}
        if not os.path.exists(a.bin):
            entry.update({"status": "NO_BINARY", "pass": False, "checks": [
                {"type": "binary", "desc": "engine binary built", "ok": False, "required": True, "detail": a.bin}]})
            results["cases"].append(entry)
            continue
        info, out = run(a.bin, html, work, page, timeout)
        entry.update(info)
        diags = load_json(out["diagnostics"], {}).get("warnings", [])
        geometry = load_json(out["geometry"], {})
        metrics = load_json(out["metrics"], {})
        entry["metrics"] = metrics
        entry["js_diagnostics"] = [d for d in diags if d.get("kind", "").startswith("js:")][:40]
        if info["status"] == "OK":
            try:
                doc = pdfcheck.PdfDoc(out["pdf"], raster_dir=os.path.join(work, "raster"))
                text = doc.all_text()
                entry["checks"] = check_case(case, doc, text, diags, geometry, metrics)
                entry["pdf_text_head"] = text[:600]
            except Exception as e:  # noqa: BLE001
                entry["checks"] = [{"type": "pdf", "desc": "PDF readable", "ok": False, "required": True, "detail": str(e)}]
        else:
            entry["checks"] = [{"type": "render", "desc": "render exits 0 with a PDF", "ok": False, "required": True,
                                "detail": f"{info['status']} rc={info['rc']}"}]
        entry["pass"] = info["status"] == "OK" and all(c["ok"] for c in entry["checks"] if c["required"])
        results["cases"].append(entry)
        print(f"[{a.engine}] {group}/{cid}: {'PASS' if entry['pass'] else 'FAIL'} "
              f"({sum(c['ok'] for c in entry['checks'])}/{len(entry['checks'])} checks, {info['status']}, {info['wall_s']} s)")
        for c in entry["checks"]:
            if not c["ok"]:
                print(f"    {'FAIL' if c['required'] else 'info'}: {c['desc']} -- {c['detail']}")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
