//! p5-boa: phase 5 harness binary for boa_engine 0.22.0 (annex-b, intl_bundled).
//!   p5-boa cases --cases dist/cases/<g>.json --dist dist --out r.json [--only id]
//!          [--recursion-limit N] [--stack-limit N] [--loop-limit N] [--shim-config JSON]
//!   p5-boa test262 --root test262 --config t262.json --dirs ... --out r.json [--keep-intl]
//!   p5-boa test262-worker ...
//! The Chart.js group uses the JS recording canvas here (no Rust canvas binding for Boa).
mod host;
mod t262;

use host::{BoaHost, BoaLimits};
use p5common::cases::{run_group, RunOpts};
use p5common::util::Args;
use serde_json::{json, Value};

pub const ENGINE: &str = "boa";
pub const ENGINE_VERSION: &str = "boa_engine 0.22.0 (features: default + annex-b + intl_bundled)";

fn cmd_cases(a: &Args) {
    let text = std::fs::read_to_string(a.req("cases")).expect("read cases");
    let group: Value = serde_json::from_str(&text).expect("parse cases");
    let opts = RunOpts::from_args(a);
    let lim = BoaLimits {
        recursion: a.num("recursion-limit", 4096) as usize,
        stack: a.num("stack-limit", 1024 * 1024) as usize,
        loop_iterations: a.num("loop-limit", u64::MAX),
    };
    let mut host = BoaHost::new(&lim);
    let mut out = run_group(&mut host, &group, &opts);
    out["engine"] = json!(ENGINE);
    out["engine_version"] = json!(ENGINE_VERSION);
    out["limits"] = json!({
        "recursion_limit": lim.recursion, "stack_size_limit": lim.stack, "loop_iteration_limit": lim.loop_iterations,
        "case_timeout_ms": opts.case_timeout_ms, "deadline_enforced_in_engine": false, "heap_limit": null, "max_jobs": opts.max_jobs
    });
    std::fs::write(a.req("out"), serde_json::to_string(&out).expect("serialize")).expect("write out");
    let done = out["cases"].as_array().map(|c| c.iter().filter(|x| x["status"] == "done").count()).unwrap_or(0);
    let n = out["cases"].as_array().map(|c| c.len()).unwrap_or(0);
    eprintln!("{ENGINE} {}: {done}/{n} done", group["group"].as_str().unwrap_or("?"));
}

fn main() {
    // Run on a thread with a large native stack: the engines' own stack limits are set far
    // below it, so deep JS recursion ends in a JS error instead of a native stack overflow.
    let handle = std::thread::Builder::new()
        .name("p5-main".into())
        .stack_size(256 * 1024 * 1024)
        .spawn(real_main)
        .expect("spawn main thread");
    if handle.join().is_err() {
        std::process::exit(101);
    }
}

fn real_main() {
    let raw: Vec<String> = std::env::args().skip(1).collect();
    let cmd = raw.first().cloned().unwrap_or_default();
    let a = Args::parse(&raw[1.min(raw.len())..]);
    match cmd.as_str() {
        "cases" => cmd_cases(&a),
        "test262" => p5common::test262::supervisor_main(&a, ENGINE, ENGINE_VERSION),
        "test262-worker" => p5common::test262::worker_main(&a, t262::exec),
        _ => {
            eprintln!("usage: p5-boa cases|test262|test262-worker ...");
            std::process::exit(2);
        }
    }
}
