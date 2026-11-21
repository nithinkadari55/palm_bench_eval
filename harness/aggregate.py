import argparse
import glob
import json
import os
from collections import defaultdict


def load(pattern):
    out = []
    for p in sorted(glob.glob(pattern, recursive=True)):
        try:
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            pass
    return out


def pct(a, b):
    return f"{100.0 * a / b:.1f}%" if b else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    a = ap.parse_args()
    engines = set()
    lines = ["# Core engine bake-off results", ""]
    agg = {"wpt": {}, "corpus": {}, "fidelity": {}, "builds": {}}

    for b in load(os.path.join(a.results, "**", "build-*.json")):
        agg["builds"][b["engine"]] = b
        engines.add(b["engine"])
    if agg["builds"]:
        lines += ["## Builds", "", "| Engine | Status | Build s | Binary MB | SHA |", "|---|---|---|---|---|"]
        for e, b in sorted(agg["builds"].items()):
            lines.append(f"| {e} | {b.get('status')} | {b.get('build_s')} | {b.get('binary_mb')} | {str(b.get('sha'))[:10]} |")
        lines.append("")

    wpt = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in load(os.path.join(a.results, "**", "wpt-*.json")):
        e = r["engine"]
        engines.add(e)
        for res in r["results"]:
            s = wpt[e][res["suite"]]
            s["total"] += 1
            s[res["status"]] += 1
            if res["kind"] == "reftest" and res["status"] != "NOT_RUN":
                s["reftests_run"] += 1
                if res["status"] == "PASS":
                    s["reftest_pass"] += 1
                    if res.get("blank"):
                        s["pass_blank"] += 1
                if not res["has_script"]:
                    s["ns_run"] += 1
                    s["ns_pass"] += res["status"] == "PASS"
            if res["kind"] == "crashtest":
                s["crash_run"] += 1
                s["crash_pass"] += res["status"] == "PASS"
            if res["status"] in ("CRASH", "TIMEOUT") or (res["kind"] == "crashtest" and res["status"] == "FAIL"):
                s["crashes"] += 1
    if wpt:
        suites = sorted({s for e in wpt for s in wpt[e]})
        lines += ["## WPT reftests: pass rate (pass excluding blank-vs-blank) over run reftests", "",
                  "| Suite | " + " | ".join(sorted(wpt)) + " |", "|---|" + "---|" * len(wpt)]
        for su in suites:
            row = [su.replace("css/", "")]
            for e in sorted(wpt):
                s = wpt[e].get(su)
                if not s or not s["reftests_run"]:
                    row.append("n/a")
                else:
                    real = s["reftest_pass"] - s["pass_blank"]
                    row.append(f"{pct(s['reftest_pass'], s['reftests_run'])} ({pct(real, s['reftests_run'])}) n={s['reftests_run']}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
        lines += ["### WPT totals", "", "| Engine | Reftests run | Pass | Pass excl. blank | No-script pass | Crash/timeout | Crashtests pass |", "|---|---|---|---|---|---|---|"]
        for e in sorted(wpt):
            t = defaultdict(int)
            for s in wpt[e].values():
                for k, v in s.items():
                    t[k] += v
            agg["wpt"][e] = dict(t)
            lines.append(f"| {e} | {t['reftests_run']} | {pct(t['reftest_pass'], t['reftests_run'])} | {pct(t['reftest_pass'] - t['pass_blank'], t['reftests_run'])} | {pct(t['ns_pass'], t['ns_run'])} | {t['crashes']} | {pct(t['crash_pass'], t['crash_run'])} |")
        lines.append("")

    corpus = load(os.path.join(a.results, "**", "corpus-*.json"))
    if corpus:
        cats = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        per_doc = defaultdict(dict)
        perf = {}
        det = defaultdict(lambda: defaultdict(int))
        for c in corpus:
            e = c["engine"]
            engines.add(e)
            for d in c["results"]:
                if d.get("status") == "NOT_RUN":
                    continue
                ok = sum(ch["ok"] for ch in d["checks"])
                per_doc[d["doc"]][e] = f"{ok}/{len(d['checks'])}" + ("" if d["status"] == "OK" else f" {d['status']}")
                for ch in d["checks"]:
                    cats[e][ch["cat"]][0] += ch["ok"]
                    cats[e][ch["cat"]][1] += 1
                if d["doc"] == "r04_stress_100_pages" and d.get("render"):
                    perf[e] = d["render"]
                det[e][d.get("determinism", "n/a")] += 1
        es = sorted(cats)
        allcats = sorted({k for e in es for k in cats[e]})
        lines += ["## Production corpus: checks passed by category", "", "| Category | " + " | ".join(es) + " |", "|---|" + "---|" * len(es)]
        for k in allcats:
            lines.append(f"| {k} | " + " | ".join(f"{cats[e][k][0]}/{cats[e][k][1]} ({pct(*cats[e][k])})" for e in es) + " |")
        tot = {e: [sum(v[0] for v in cats[e].values()), sum(v[1] for v in cats[e].values())] for e in es}
        lines.append("| **TOTAL** | " + " | ".join(f"**{tot[e][0]}/{tot[e][1]} ({pct(*tot[e])})**" for e in es) + " |")
        lines += ["", "### Per document", "", "| Doc | " + " | ".join(es) + " |", "|---|" + "---|" * len(es)]
        for doc in sorted(per_doc):
            lines.append(f"| {doc} | " + " | ".join(per_doc[doc].get(e, "-") for e in es) + " |")
        lines += ["", "### 100-page stress + determinism", "", "| Engine | Status | Seconds | Peak RSS MB | Determinism |", "|---|---|---|---|---|"]
        for e in es:
            p = perf.get(e, {})
            lines.append(f"| {e} | {p.get('status')} | {p.get('elapsed_s')} | {p.get('peak_rss_mb')} | {dict(det[e])} |")
        lines.append("")
        agg["corpus"] = {"categories": {e: dict(cats[e]) for e in es}, "per_doc": per_doc, "perf": perf, "determinism": {e: dict(det[e]) for e in es}}

    fid = load(os.path.join(a.results, "**", "fidelity-*.json"))
    if fid:
        lines += ["## Real-world / LLM-written pages vs Chrome screenshots", "",
                  "| Engine | Dataset | OK/N | Status | SSIM mean | SSIM median | Text recall | Blank | p50 s | p95 s | RSS p95 MB |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for f in fid:
            engines.add(f["engine"])
            for ds, s in f["summary"].items():
                lines.append(f"| {f['engine']} | {ds} | {s['ok']}/{s['n']} | {s['status']} | {s['ssim_mean']} | {s['ssim_median']} | {s['text_recall_mean']} | {s['blank']} | {s['elapsed_p50']} | {s['elapsed_p95']} | {s['rss_p95_mb']} |")
            agg["fidelity"][f["engine"]] = f["summary"]
        lines.append("")

    with open(a.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(a.out_json, "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
