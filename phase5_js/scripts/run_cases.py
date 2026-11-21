#!/usr/bin/env python3
"""Runs case groups on one engine as child processes and records outputs, timing and
per-process peak RSS (os.wait4 ru_maxrss).

  group mode   : one process per (group, repetition); --reps 3 for the determinism check
  isolated mode: one process per case (--only <id>) for per-case peak RSS
  sandbox      : always one process per case, external wall-clock kill, RLIMIT_AS cap

Engines: qjs | boa (Rust binaries, `cases` subcommand), node | node-jsdom (node_runner.mjs).
Writes <out>/cases_<engine>.json plus outputs_<engine>_<group>_rep<k>.json.
"""
import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import sys
import time

SANDBOX = ("sandbox_limits", "sandbox_escapes")


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest() if isinstance(s, str) else None


def run_child(cmd, timeout_s, as_limit_mb, log_path=None):
    """Runs cmd; returns exit code, signal, killed flag, wall time and ru_maxrss (KiB)."""
    def limits():
        if as_limit_mb:
            b = as_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        os.setsid()
    t0 = time.monotonic()
    log_path = log_path or os.devnull
    log = open(log_path, "wb")
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, preexec_fn=limits)
    killed = False
    while True:
        pid, status, ru = os.wait4(p.pid, os.WNOHANG)
        if pid:
            break
        if time.monotonic() - t0 > timeout_s:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            killed = True
            pid, status, ru = os.wait4(p.pid, 0)
            break
        time.sleep(0.02)
    wall = time.monotonic() - t0
    log.close()
    try:
        err = open(log_path, "rb").read()[-2000:].decode("utf-8", "replace") if log_path != os.devnull else ""
    except Exception:
        err = ""
    p.returncode = 0
    sig = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None
    code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else None
    return {"exit": code, "signal": sig, "killed": killed, "wall_s": wall, "maxrss_kb": ru.ru_maxrss, "stderr_tail": err}


def engine_cmd(a, group_file, out_file, only=None, shim_config=None, extra=None):
    if a.engine in ("qjs", "boa"):
        cmd = [a.bin, "cases", "--cases", group_file, "--dist", a.dist, "--out", out_file]
    else:
        cmd = ["node", os.path.join(a.js, "node_runner.mjs"), "--cases", group_file, "--dist", a.dist, "--out", out_file]
        if a.engine == "node-jsdom":
            cmd += ["--dom-impl", "jsdom"]
    if only:
        cmd += ["--only", only]
    if shim_config:
        cmd += ["--shim-config", json.dumps(shim_config)]
    cmd += extra or []
    return cmd


def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return {"load_error": repr(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["qjs", "boa", "node", "node-jsdom"])
    ap.add_argument("--bin", default="")
    ap.add_argument("--js", default="phase5_js/js")
    ap.add_argument("--dist", default="phase5_js/js/dist")
    ap.add_argument("--groups", required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--isolated", type=int, default=0, help="per-case processes for the first N cases of each group (0 = none, -1 = all)")
    ap.add_argument("--timeout-s", type=float, default=900)
    ap.add_argument("--sandbox-timeout-ms", type=int, default=5000)
    ap.add_argument("--as-limit-mb", type=int, default=0)
    ap.add_argument("--extra", default="", help="extra engine args, space separated")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    extra = a.extra.split() if a.extra else []
    path = os.path.join(a.out, f"cases_{a.engine}.json")
    result = {"engine": a.engine, "reps": a.reps, "groups": {}}
    if os.path.exists(path):
        # successive invocations (libraries, sandbox, layout) merge into one file per engine
        prev = load(path)
        if isinstance(prev, dict) and prev.get("engine") == a.engine:
            result["groups"] = prev.get("groups", {})
    for g in [x for x in a.groups.split(",") if x]:
        gfile = os.path.join(a.dist, "cases", g + ".json")
        group = json.load(open(gfile, encoding="utf-8"))
        ids = [c["id"] for c in group["cases"]]
        gres = {"compare": group.get("compare"), "bundle": group.get("bundle"), "case_ids": ids, "reps": [], "cases": {}, "isolated": {}}
        if g in SANDBOX:
            # one process per case; the engine's own budget is --timeout-ms, the supervisor
            # kills at 6x that (a hang is a failure).
            for cid in ids:
                out = os.path.join(a.work, f"{a.engine}_{g}_{cid}.json")
                if os.path.exists(out):
                    os.remove(out)
                ex = extra + ["--timeout-ms", str(a.sandbox_timeout_ms)] + (["--memory-mb", "256", "--stack-kb", "1024"] if a.engine == "qjs" else [])
                proc = run_child(engine_cmd(a, gfile, out, only=cid, extra=ex), a.sandbox_timeout_ms / 1000 * 6 + 5, a.as_limit_mb, out + '.log')
                r = load(out) if os.path.exists(out) else {}
                case = (r.get("cases") or [{}])[0] if isinstance(r, dict) else {}
                gres["cases"][cid] = {"process": proc, "result": case}
                print(f"{a.engine} {g} {cid}: exit={proc['exit']} sig={proc['signal']} killed={proc['killed']} {case.get('status')} {case.get('error_type')} {proc['wall_s']:.2f}s", flush=True)
            result["groups"][g] = gres
            continue
        for rep in range(1, a.reps + 1):
            out = os.path.join(a.work, f"{a.engine}_{g}_rep{rep}.json")
            if os.path.exists(out):
                os.remove(out)
            proc = run_child(engine_cmd(a, gfile, out, extra=extra), a.timeout_s, a.as_limit_mb, out + '.log')
            r = load(out) if os.path.exists(out) else {"missing": True}
            outputs = {}
            for c in r.get("cases", []) if isinstance(r, dict) else []:
                cid = c.get("id")
                outputs[cid] = c.get("output")
                e = gres["cases"].setdefault(cid, {"status": [], "sha256": [], "ms": [], "error": None, "error_type": None, "usage": None})
                e["status"].append(c.get("status"))
                e["sha256"].append(sha(c.get("output")))
                e["ms"].append(c.get("ms"))
                if c.get("error") and not e["error"]:
                    e["error"] = c.get("error")[:500]
                    e["error_type"] = c.get("error_type")
                if rep == 1:
                    e["usage"] = c.get("usage")
                    e["bytes"] = len(c["output"]) if isinstance(c.get("output"), str) else None
                    e["rss_kb"] = c.get("rss_kb") or c.get("max_rss_kb")
                    e["engine"] = c.get("engine")
                    e["diagnostics_total"] = c.get("diagnostics_total")
            json.dump(outputs, open(os.path.join(a.out, f"outputs_{a.engine}_{g}_rep{rep}.json"), "w", encoding="utf-8"))
            meta = {k: r.get(k) for k in ("load_ms", "total_ms", "peak_rss_kb", "after_load_rss_kb", "fatal", "engine_version", "environment", "limits", "v8", "jsdom_version")} if isinstance(r, dict) else {}
            gres["reps"].append({"process": proc, **meta})
            print(f"{a.engine} {g} rep{rep}: exit={proc['exit']} sig={proc['signal']} killed={proc['killed']} wall={proc['wall_s']:.1f}s maxrss={proc['maxrss_kb']}KB "
                  f"done={sum(1 for c in r.get('cases', []) if c.get('status') == 'done') if isinstance(r, dict) else 0}/{len(ids)}", flush=True)
        n_iso = len(ids) if a.isolated < 0 else min(a.isolated, len(ids))
        for cid in ids[:n_iso]:
            out = os.path.join(a.work, f"{a.engine}_{g}_iso_{cid}.json")
            if os.path.exists(out):
                os.remove(out)
            proc = run_child(engine_cmd(a, gfile, out, only=cid, extra=extra), a.timeout_s, a.as_limit_mb, out + '.log')
            r = load(out) if os.path.exists(out) else {}
            c = (r.get("cases") or [{}])[0] if isinstance(r, dict) else {}
            gres["isolated"][cid] = {"maxrss_kb": proc["maxrss_kb"], "wall_s": proc["wall_s"], "exit": proc["exit"], "signal": proc["signal"],
                                     "killed": proc["killed"], "case_ms": c.get("ms"), "load_ms": r.get("load_ms") if isinstance(r, dict) else None,
                                     "status": c.get("status"), "sha256": sha(c.get("output"))}
        result["groups"][g] = gres
    json.dump(result, open(path, "w", encoding="utf-8"))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
