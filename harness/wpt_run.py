import argparse
import hashlib
import json
import multiprocessing as mp
import os
import re
import shutil
import sys
import time
from urllib.parse import urlsplit, unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from wpt_prep import classify  # noqa: E402

SCREEN = (800, 600, 0)
PRINT = (480, 288, 48)
RENDER_TIMEOUT = 30

_G = {}


def init_worker(engine, wpt_root, work_root, evidence_dir):
    _G["info"] = common.engine_info(engine)
    _G["wpt"] = wpt_root
    _G["work"] = os.path.join(work_root, f"w{os.getpid()}")
    _G["evidence"] = evidence_dir
    _G["aa"] = os.environ.get("WPT_PDF_AA", "0") == "1"
    _G["cache"] = {}
    common.clean_dir(_G["work"])


def render_pages(rel_path, mode):
    key = (rel_path, mode)
    if key in _G["cache"]:
        return _G["cache"][key]
    info = _G["info"]
    src = os.path.join(_G["wpt"], rel_path)
    h = hashlib.sha1(f"{rel_path}|{mode}".encode()).hexdigest()[:16]
    w, hgt, m = PRINT if mode == "print" else SCREEN
    is_pdf = info["output"] == "pdf"
    out = os.path.join(_G["work"], h + (".pdf" if is_pdf else ".png"))
    res = {"render": None, "pages": [], "error": None}
    if not os.path.exists(src):
        res["error"] = "missing_file"
        _G["cache"][key] = res
        return res
    r = common.run_adapter(info, src, out, w, hgt, m, RENDER_TIMEOUT)
    res["render"] = r
    if r["status"] == "OK":
        try:
            if is_pdf:
                res["pages"] = common.rasterize(out, os.path.join(_G["work"], h + "_px"), antialias=_G["aa"])
            else:
                res["pages"] = [out]
        except Exception as e:  # noqa: BLE001
            res["error"] = f"rasterize: {e}"
    _G["cache"][key] = res
    return res


def resolve(test_rel, href):
    parts = urlsplit(href)
    if parts.scheme or href.startswith("//"):
        return None
    p = unquote(parts.path)
    if p.startswith("/"):
        return p.lstrip("/")
    base = os.path.dirname(test_rel)
    return os.path.normpath(os.path.join(base, p)).replace("\\", "/")


def parse_pages(spec, n):
    if not spec:
        return list(range(n))
    sel = set()
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            lo, hi = item.split("-", 1)
            lo = int(lo) if lo.strip() else 1
            hi = int(hi) if hi.strip() else n
            sel.update(range(lo - 1, min(hi, n)))
        else:
            k = int(item) - 1
            if k < n:
                sel.add(k)
    return sorted(sel)


def fuzzy_for(fuzzy_list, ref_href):
    default = None
    for f in fuzzy_list:
        if f["ref"]:
            if os.path.basename(f["ref"]) == os.path.basename(ref_href):
                return f
        elif default is None:
            default = f
    return default


def check_pass(maxd, npx, relation, fz):
    if not fz or (fz["maxDifference"] == [0, 0] and fz["totalPixels"] == [0, 0]):
        equal = maxd == 0 and npx == 0
    else:
        apc, adf = fz["maxDifference"], fz["totalPixels"]
        equal = ((npx == 0 and adf[0] == 0) or (maxd == 0 and apc[0] == 0)
                 or (apc[0] <= maxd <= apc[1] and adf[0] <= npx <= adf[1]))
    return equal if relation == "match" else not equal


def compare_docs(test_res, ref_res, mode, relation, fz, pages_spec):
    tp, rp = test_res["pages"], ref_res["pages"]
    if mode == "print":
        if len(tp) != len(rp):
            ok = relation == "mismatch"
            return ok, {"reason": "page_count", "test_pages": len(tp), "ref_pages": len(rp)}, False
        idx = parse_pages(pages_spec, len(tp))
    else:
        idx = [0]
        if not tp or not rp:
            return False, {"reason": "no_pages"}, False
    worst = {"max_diff": 0, "diff_pixels": 0}
    all_blank = True
    results = []
    for i in idx:
        a, b = common.load_rgb(tp[i]), common.load_rgb(rp[i])
        if not (common.is_blank(a) and common.is_blank(b)):
            all_blank = False
        c = common.compare(a, b)
        results.append(check_pass(c["max_diff"], c["diff_pixels"], "match", fz))
        worst["max_diff"] = max(worst["max_diff"], c["max_diff"])
        worst["diff_pixels"] = max(worst["diff_pixels"], c["diff_pixels"])
        if not c["same_size"]:
            worst["size_mismatch"] = True
    equal_all = all(results)
    ok = equal_all if relation == "match" else not equal_all
    return ok, worst, all_blank


def eval_reftest(rel, info, mode, depth=0):
    test_res = render_pages(rel, mode)
    if test_res["render"] is None or test_res["render"]["status"] != "OK" or test_res["error"]:
        st = test_res["render"]["status"] if test_res["render"] else "ERROR"
        if test_res["error"] and st == "OK":
            st = "ERROR"
        return {"status": st, "detail": test_res["error"] or (test_res["render"] or {}).get("stderr", "")[-300:]}
    matches = [r for r in info["refs"] if r["rel"] == "match"]
    mismatches = [r for r in info["refs"] if r["rel"] == "mismatch"]
    details = []
    blank = True
    any_match_ok = not matches
    for group, relation in ((matches, "match"), (mismatches, "mismatch")):
        for ref in group:
            rrel = resolve(rel, ref["href"])
            if rrel is None:
                details.append({"ref": ref["href"], "skip": "external"})
                continue
            ref_res = render_pages(rrel, mode)
            if ref_res["render"] is None or ref_res["render"]["status"] != "OK" or ref_res["error"]:
                details.append({"ref": rrel, "ref_status": (ref_res["render"] or {}).get("status", "ERROR"), "err": ref_res["error"]})
                if relation == "mismatch":
                    return {"status": "ERROR", "detail": f"ref failed: {rrel}", "refs": details}
                continue
            ok, stats, all_blank = compare_docs(test_res, ref_res, mode, relation, fuzzy_for(info["fuzzy"], ref["href"]), info.get("pages"))
            if ok and depth < 3:
                try:
                    with open(os.path.join(_G["wpt"], rrel), encoding="utf-8", errors="replace") as f:
                        rinfo = classify(rrel, rrel, f.read())
                    if rinfo["refs"]:
                        sub = eval_reftest(rrel, rinfo, mode, depth + 1)
                        ok = sub["status"] == "PASS"
                        stats["chain"] = sub["status"]
                except OSError:
                    pass
            details.append({"ref": rrel, "rel": relation, "ok": ok, **stats})
            blank = blank and all_blank
            if relation == "match" and ok:
                any_match_ok = True
            if relation == "mismatch" and not ok:
                return {"status": "FAIL", "refs": details, "blank": blank}
    if matches and not any(d.get("rel") == "match" for d in details):
        return {"status": "ERROR", "detail": "no renderable match reference", "refs": details}
    return {"status": "PASS" if any_match_ok else "FAIL", "refs": details, "blank": blank}


def save_evidence(rel, mode, result):
    ev = _G["evidence"]
    if not ev or result["status"] != "FAIL":
        return
    if len(os.listdir(ev)) > 400:
        return
    tag = hashlib.sha1(rel.encode()).hexdigest()[:10]
    t = render_pages(rel, mode)
    if t["pages"]:
        shutil.copy(t["pages"][0], os.path.join(ev, f"{tag}_test.png"))
    for d in result.get("refs", []):
        if d.get("rel") == "match" and "ref" in d:
            r = render_pages(d["ref"], mode)
            if r["pages"]:
                shutil.copy(r["pages"][0], os.path.join(ev, f"{tag}_ref.png"))
            break
    result["evidence"] = tag


def run_one(t):
    rel = t["path"]
    mode = "print" if t["print"] else "screen"
    start = time.monotonic()
    base = {"path": rel, "suite": t["suite"], "kind": t["kind"], "mode": mode,
            "has_script": t["has_script"], "reftest_wait": t["reftest_wait"], "tentative": t["tentative"]}
    if t["kind"] in ("testharness", "manual", "other"):
        return {**base, "status": "NOT_RUN", "detail": t["kind"]}
    if mode == "print" and _G["info"]["output"] != "pdf":
        return {**base, "status": "NOT_RUN", "detail": "engine has no pagination"}
    try:
        if t["kind"] == "crashtest":
            r = render_pages(rel, mode)
            st = r["render"]["status"] if r["render"] else "ERROR"
            res = {"status": "PASS" if st == "OK" else ("FAIL" if st in ("CRASH", "TIMEOUT") else "ERROR"),
                   "detail": st}
        else:
            res = eval_reftest(rel, t, mode)
            save_evidence(rel, mode, res)
    except Exception as e:  # noqa: BLE001
        res = {"status": "HARNESS_ERROR", "detail": repr(e)[:500]}
    rr = (_G["cache"].get((rel, mode)) or {}).get("render") or {}
    res.update(base)
    res["elapsed_s"] = rr.get("elapsed_s")
    res["peak_rss_mb"] = rr.get("peak_rss_mb")
    res["wall_s"] = round(time.monotonic() - start, 3)
    if len(_G["cache"]) > 3000:
        _G["cache"].clear()
        common.clean_dir(_G["work"])
    return res


def summarize(results):
    s = {}
    for r in results:
        k = r["suite"]
        d = s.setdefault(k, {"total": 0})
        d["total"] += 1
        d[r["status"]] = d.get(r["status"], 0) + 1
        if r["status"] == "PASS" and r.get("blank"):
            d["PASS_BLANK"] = d.get("PASS_BLANK", 0) + 1
        if r["kind"] == "reftest" and not r["has_script"]:
            d["noscript_reftests"] = d.get("noscript_reftests", 0) + 1
            if r["status"] == "PASS":
                d["noscript_pass"] = d.get("noscript_pass", 0) + 1
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--wpt", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--suite", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", default="/tmp/wptwork")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--shard", default="1/1")
    a = ap.parse_args()
    with open(a.manifest, encoding="utf-8") as f:
        tests = [t for t in json.load(f) if t["suite"] == a.suite]
    k, n = (int(x) for x in a.shard.split("/"))
    tests = [t for i, t in enumerate(sorted(tests, key=lambda t: t["path"])) if i % n == k - 1]
    evidence = os.path.join(os.path.dirname(a.out), "evidence")
    os.makedirs(evidence, exist_ok=True)
    common.clean_dir(a.work)
    t0 = time.monotonic()
    with mp.Pool(a.jobs, initializer=init_worker, initargs=(a.engine, a.wpt, a.work, evidence)) as pool:
        results = list(pool.imap(run_one, tests, chunksize=8))
    summary = summarize(results)
    common.write_json(a.out, {"engine": a.engine, "suite": a.suite, "shard": a.shard,
                              "duration_s": round(time.monotonic() - t0, 1), "summary": summary, "results": results})
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
