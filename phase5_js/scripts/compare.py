#!/usr/bin/env python3
"""Cross-engine comparison of library outputs, determinism and cost.

Inputs (from run_cases.py): cases_<engine>.json and outputs_<engine>_<group>_rep<k>.json.
Output: compare.json with, per group and engine pair, byte-equal and normalized-equal
counts plus the first differing token of each mismatch.

Normalization (structural equality):
  svg/html: parsed with html.parser into (start tag, sorted attributes)/text/end tokens;
            whitespace collapsed, entities decoded, every number rounded to 6 significant
            digits, style declarations split/trimmed/sorted with #rrggbb -> rgb(r, g, b),
            self-closing and void elements given explicit end tokens.
  ops:      Chart.js op streams compared as JSON with |a-b| <= 1e-9 * max(1, |a|, |b|).
"""
import argparse
import glob
import json
import math
import os
import re
import statistics
import sys
from html.parser import HTMLParser

NUM = re.compile(r"-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ENGINES = ["qjs", "boa", "node", "node-jsdom"]


def rnum(m):
    try:
        v = float(m.group(0))
    except ValueError:
        return m.group(0)
    if v == 0:
        return "0"
    return "%.6g" % v


def hex2rgb(m):
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "rgb(%d, %d, %d)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def norm_text(s):
    return NUM.sub(rnum, " ".join(s.split()))


def norm_style(v):
    decls = []
    for d in v.split(";"):
        if ":" in d:
            k, _, val = d.partition(":")
            decls.append(k.strip().lower() + ":" + norm_text(HEX.sub(hex2rgb, val.strip())))
    return ";".join(sorted(decls))


class Tok(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.toks = []

    def _attrs(self, attrs):
        out = []
        for k, v in attrs:
            v = "" if v is None else v
            out.append((k.lower(), norm_style(v) if k.lower() == "style" else norm_text(v)))
        return tuple(sorted(out))

    def handle_starttag(self, tag, attrs):
        self.toks.append(("<", tag, self._attrs(attrs)))
        if tag in VOID:
            self.toks.append((">", tag))

    def handle_startendtag(self, tag, attrs):
        self.toks.append(("<", tag, self._attrs(attrs)))
        self.toks.append((">", tag))

    def handle_endtag(self, tag):
        if tag not in VOID:
            self.toks.append((">", tag))

    def handle_data(self, data):
        t = norm_text(data)
        if t:
            if self.toks and self.toks[-1][0] == "t":
                self.toks[-1] = ("t", self.toks[-1][1] + " " + t)
            else:
                self.toks.append(("t", t))

    def handle_decl(self, decl):
        self.toks.append(("!", decl.lower()))


def tokens(s):
    p = Tok()
    p.feed(s)
    p.close()
    return p.toks


def first_diff_tokens(a, b):
    ta, tb = tokens(a), tokens(b)
    for i in range(min(len(ta), len(tb))):
        if ta[i] != tb[i]:
            return {"index": i, "a": str(ta[i])[:300], "b": str(tb[i])[:300], "tokens": [len(ta), len(tb)]}
    if len(ta) != len(tb):
        return {"index": min(len(ta), len(tb)), "a": "len %d" % len(ta), "b": "len %d" % len(tb), "tokens": [len(ta), len(tb)]}
    return None


def num_close(x, y):
    return abs(x - y) <= 1e-9 * max(1.0, abs(x), abs(y))


def json_close(a, b, path="$"):
    if isinstance(a, bool) or isinstance(b, bool):
        return None if a == b else path
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return None if num_close(float(a), float(b)) else path
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return path + ".length"
        for i, (x, y) in enumerate(zip(a, b)):
            d = json_close(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return path + ".keys"
        for k in a:
            d = json_close(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    return None if a == b else path


def compare_outputs(kind, a, b):
    """Returns (byte_equal, normalized_equal, detail)."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False, False, {"missing": [a is None, b is None]}
    if a == b:
        return True, True, None
    if kind == "ops":
        try:
            ja, jb = json.loads(a), json.loads(b)
        except Exception as e:
            return False, False, {"parse": repr(e)}
        d = json_close(ja, jb)
        if d is None:
            return False, True, None
        ops_a, ops_b = ja.get("ops", []), jb.get("ops", [])
        idx = next((i for i, (x, y) in enumerate(zip(ops_a, ops_b)) if json_close(x, y)), None)
        return False, False, {"path": d, "op_index": idx, "a": json.dumps(ops_a[idx])[:200] if idx is not None else None,
                              "b": json.dumps(ops_b[idx])[:200] if idx is not None else None, "op_count": [len(ops_a), len(ops_b)]}
    d = first_diff_tokens(a, b)
    if d is None:
        return False, True, None
    return False, False, d


def load_outputs(results, engine, group, rep=1):
    p = os.path.join(results, f"outputs_{engine}_{group}_rep{rep}.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def median(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.median(xs) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cases = {}
    for e in ENGINES:
        p = os.path.join(a.results, f"cases_{e}.json")
        if os.path.exists(p):
            cases[e] = json.load(open(p, encoding="utf-8"))
    report = {"engines": sorted(cases), "groups": {}, "determinism": {}, "cost": {}, "sandbox": {}}
    lib_groups = ["echarts", "mathjax", "chartjs", "d3", "dom"]
    pairs = [("qjs", "node"), ("boa", "node"), ("qjs", "boa"), ("qjs", "node-jsdom"), ("node", "node-jsdom")]
    for g in lib_groups:
        kind = None
        ids = None
        for e in cases:
            gr = cases[e]["groups"].get(g)
            if gr:
                kind = gr.get("compare")
                ids = ids or gr.get("case_ids")
        if not ids:
            continue
        gout = {"compare": kind, "cases": len(ids), "pairs": {}}
        outs = {e: load_outputs(a.results, e, g) for e in cases}
        for x, y in pairs:
            if g != "dom" and "node-jsdom" in (x, y):
                continue
            ox, oy = outs.get(x), outs.get(y)
            if ox is None or oy is None:
                continue
            byte = normd = 0
            mism = []
            for cid in ids:
                b, n, d = compare_outputs(kind, ox.get(cid), oy.get(cid))
                byte += b
                normd += n
                if not n and len(mism) < 25:
                    mism.append({"id": cid, "detail": d})
            gout["pairs"][f"{x}_vs_{y}"] = {"byte_equal": byte, "normalized_equal": normd, "total": len(ids),
                                            "byte_rate": byte / len(ids), "normalized_rate": normd / len(ids), "mismatches": mism}
        report["groups"][g] = gout
    # determinism + cost
    for e, data in cases.items():
        det = {}
        cost = {}
        for g, gr in data["groups"].items():
            if g.startswith("sandbox"):
                continue
            ok = total = 0
            nondet = []
            for cid, c in gr.get("cases", {}).items():
                shas = c.get("sha256", [])
                statuses = c.get("status", [])
                total += 1
                if len(shas) == data["reps"] and len(set(shas)) == 1 and shas[0] is not None and all(s == "done" for s in statuses):
                    ok += 1
                else:
                    nondet.append({"id": cid, "status": statuses, "distinct_outputs": len(set(shas)), "error": c.get("error")})
            det[g] = {"identical_3_of_3": ok, "total": total, "rate": ok / total if total else 0.0, "not_identical": nondet[:20]}
            ms = [m for c in gr.get("cases", {}).values() for m in (c.get("ms") or [])]
            reps = gr.get("reps", [])
            iso = gr.get("isolated", {})
            cost[g] = {
                "case_ms_median": median(ms), "case_ms_max": max([m for m in ms if isinstance(m, (int, float))], default=None),
                "load_ms_median": median([r.get("load_ms") for r in reps]),
                "process_wall_s_median": median([r["process"]["wall_s"] for r in reps]),
                "process_peak_rss_kb_max": max([r["process"]["maxrss_kb"] for r in reps], default=None),
                "isolated_cases": len(iso),
                "isolated_peak_rss_kb_median": median([v.get("maxrss_kb") for v in iso.values()]),
                "isolated_peak_rss_kb_max": max([v.get("maxrss_kb") or 0 for v in iso.values()], default=None),
                "per_case": {cid: {"ms_median": median(c.get("ms") or []), "isolated_maxrss_kb": iso.get(cid, {}).get("maxrss_kb"),
                                   "isolated_wall_s": iso.get(cid, {}).get("wall_s")} for cid, c in gr.get("cases", {}).items()}
            }
        report["determinism"][e] = det
        report["cost"][e] = cost
        # sandbox
        sb = {}
        for g in ("sandbox_limits", "sandbox_escapes"):
            gr = data["groups"].get(g)
            if not gr:
                continue
            rows = []
            passed = 0
            for cid, c in gr["cases"].items():
                proc, r = c["process"], c["result"] or {}
                crashed = proc["signal"] is not None or (proc["exit"] not in (0, None)) or proc["killed"]
                if g == "sandbox_limits":
                    expect = r.get("expect") or []
                    got = r.get("error_type") if r.get("status") == "error" else ("ok" if r.get("status") == "done" else "none")
                    within = proc["wall_s"] <= 5.0 * 2 + 5
                    ok = (not crashed) and got in expect and within
                    if r.get("status") == "done" and isinstance(r.get("output"), str) and r["output"].startswith("absent"):
                        ok = (not crashed) and "absent" in expect
                        got = "absent"
                    rows.append({"id": cid, "pass": ok, "got": got, "expect": expect, "wall_s": round(proc["wall_s"], 3), "exit": proc["exit"],
                                 "result_written_before_exit": bool(r.get("status")),
                                 "signal": proc["signal"], "killed": proc["killed"], "maxrss_kb": proc["maxrss_kb"], "error": (r.get("error") or "")[:200]})
                else:
                    out = r.get("output") if r.get("status") == "done" else None
                    ok = (not crashed) and isinstance(out, str) and (out.startswith("blocked") or out.startswith("absent") or out.startswith("present: WebAssembly"))
                    rows.append({"id": cid, "pass": ok, "output": (out or r.get("error") or "")[:200], "exit": proc["exit"], "signal": proc["signal"], "killed": proc["killed"]})
                passed += ok
            sb[g] = {"pass": passed, "total": len(rows), "rows": rows}
        if sb:
            report["sandbox"][e] = sb
    # layout APIs: what each DOM answers for getBoundingClientRect / offset* (pass 1, no host layout)
    lay = {}
    for e in cases:
        o = load_outputs(a.results, e, "layout")
        if not o:
            continue
        try:
            d = json.loads(o.get("layout-feedback") or "{}")
        except Exception:
            continue
        seen = {}
        for m in d.get("measured", []):
            k = m["api"]
            v = m["value"]
            seen.setdefault(k, set()).add(json.dumps(v, sort_keys=True) if isinstance(v, dict) else str(v))
        lay[e] = {k: sorted(v)[:3] for k, v in seen.items()}
    report["layout_apis"] = lay
    json.dump(report, open(a.out, "w", encoding="utf-8"), indent=1)
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
