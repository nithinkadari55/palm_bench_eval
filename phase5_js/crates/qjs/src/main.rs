//! p5-qjs: phase 5 harness binary for rquickjs 0.14.0 (QuickJS-NG 0fdea21).
//!   p5-qjs cases --cases dist/cases/<g>.json --dist dist --out r.json [--only id]
//!          [--timeout-ms N] [--memory-mb N] [--stack-kb N] [--max-jobs N]
//!          [--shim-config JSON] [--canvas rust|js]
//!   p5-qjs test262 --root test262 --config t262.json --dirs test/built-ins,... --out r.json
//!          [--keep-intl] [--jobs N] [--expected-errors test262_errors.txt]
//!   p5-qjs test262-worker ...            (spawned by the supervisor)
//!   p5-qjs layout --cases dist/cases/layout.json --dist dist --out r.json
mod canvas;
mod host;
mod t262;

use host::{Limits, QjsHost};
use p5common::cases::{run_group, RunOpts};
use p5common::util::Args;
use serde_json::{json, Map, Value};
use std::time::Instant;

pub const ENGINE: &str = "rquickjs";
pub const ENGINE_VERSION: &str = "rquickjs 0.14.0 / QuickJS-NG 0fdea21 (quickjs.h 0.16.2)";

fn limits(a: &Args) -> Limits {
    Limits {
        memory_bytes: (a.num("memory-mb", 512) as usize) * 1024 * 1024,
        stack_bytes: (a.num("stack-kb", 4096) as usize) * 1024,
    }
}

fn read_json(path: &str) -> Value {
    let text = std::fs::read_to_string(path).unwrap_or_else(|e| panic!("read {path}: {e}"));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("parse {path}: {e}"))
}

fn write_json(path: &str, v: &Value) {
    std::fs::write(path, serde_json::to_string(v).expect("serialize")).unwrap_or_else(|e| panic!("write {path}: {e}"));
}

fn cmd_cases(a: &Args) {
    let group = read_json(&a.req("cases"));
    let opts = RunOpts::from_args(a);
    let native_canvas = a.get("canvas").map(|c| c != "js").unwrap_or(true);
    let lim = limits(a);
    let mut host = QjsHost::new(&lim, native_canvas);
    let mut out = run_group(&mut host, &group, &opts);
    out["engine"] = json!(ENGINE);
    out["engine_version"] = json!(ENGINE_VERSION);
    out["limits"] = json!({"memory_bytes": lim.memory_bytes, "stack_bytes": lim.stack_bytes, "case_timeout_ms": opts.case_timeout_ms, "max_jobs": opts.max_jobs, "native_canvas": native_canvas});
    write_json(&a.req("out"), &out);
    let done = out["cases"].as_array().map(|c| c.iter().filter(|x| x["status"] == "done").count()).unwrap_or(0);
    let n = out["cases"].as_array().map(|c| c.len()).unwrap_or(0);
    eprintln!("{ENGINE} {}: {done}/{n} done", group["group"].as_str().unwrap_or("?"));
}

/// Stand-in layout for the two-pass prototype: block boxes at the content width (or an
/// inline `width:` from the element's style attribute), 8 px per character, 20 px lines.
/// It replaces the real layout engine only to measure the cost and stability of the loop.
fn stub_layout(html: &str, measured: &[Value]) -> Value {
    let content_w = 768.0f64;
    let mut rects = Map::new();
    let mut y = 0.0f64;
    for m in measured {
        let key = m["key"].as_str().unwrap_or("").to_string();
        if rects.contains_key(&key) {
            continue;
        }
        let tag = m["tag"].as_str().unwrap_or("div");
        let text_len = m["textLength"].as_f64().unwrap_or(0.0);
        let mut w = content_w;
        if let Some(id) = key.strip_prefix('#') {
            let needle = format!("id=\"{id}\"");
            if let Some(i) = html.find(&needle) {
                let tag_start = html[..i].rfind('<').unwrap_or(i);
                let tag_end = html[i..].find('>').map(|j| i + j).unwrap_or(html.len());
                let open = &html[tag_start..tag_end];
                if let Some(k) = open.find("width:") {
                    let rest = open[k + 6..].trim_start();
                    let num: String = rest.chars().take_while(|c| c.is_ascii_digit() || *c == '.').collect();
                    if let Ok(n) = num.parse::<f64>() {
                        let unit = &rest[num.len()..];
                        w = if unit.starts_with('%') { content_w * n / 100.0 } else { n };
                    }
                }
            }
        }
        if tag == "span" || tag == "a" {
            w = (text_len * 8.0).min(content_w);
        }
        let lines = ((text_len * 8.0) / w.max(1.0)).ceil().max(1.0);
        let h = lines * 20.0;
        rects.insert(key, json!({"x": 0.0, "y": y, "width": w, "height": h}));
        y += h;
    }
    Value::Object(rects)
}

fn cmd_layout(a: &Args) {
    let mut group = read_json(&a.req("cases"));
    let opts = RunOpts::from_args(a);
    let lim = limits(a);
    let mut passes = Vec::new();
    let mut injected = Value::Null;
    let mut outputs: Vec<String> = Vec::new();
    for pass in 1..=3 {
        if !injected.is_null() {
            group["cases"][0]["input"]["layout"] = injected.clone();
        }
        let t = Instant::now();
        let mut host = QjsHost::new(&lim, false);
        let r = run_group(&mut host, &group, &opts);
        let js_ms = t.elapsed().as_secs_f64() * 1000.0;
        let case = r["cases"][0].clone();
        let out_s = case["output"].as_str().unwrap_or("").to_string();
        let parsed: Value = serde_json::from_str(&out_s).unwrap_or(Value::Null);
        let html = parsed["html"].as_str().unwrap_or("").to_string();
        let measured: Vec<Value> = parsed["measured"].as_array().cloned().unwrap_or_default();
        let l0 = Instant::now();
        let rects = stub_layout(&html, &measured);
        let layout_ms = l0.elapsed().as_secs_f64() * 1000.0;
        passes.push(json!({
            "pass": pass, "status": case["status"], "error": case["error"], "process_ms": js_ms,
            "load_ms": r["load_ms"], "script_ms": case["ms"], "layout_stub_ms": layout_ms,
            "measured": measured, "injected": injected, "html": html
        }));
        outputs.push(html);
        injected = rects;
    }
    let out = json!({
        "engine": ENGINE, "engine_version": ENGINE_VERSION,
        "dom": "linkedom 0.18.15 (bundled)",
        "passes": passes,
        "pass2_differs_from_pass1": outputs.len() >= 2 && outputs[0] != outputs[1],
        "stable_after_pass2": outputs.len() >= 3 && outputs[1] == outputs[2],
        "note": "pass 1 sees linkedom geometry (zeros/undefined); passes 2-3 answer getBoundingClientRect/offset*/client*/scroll* from host boxes computed by stub_layout() over the previous pass's DOM"
    });
    write_json(&a.req("out"), &out);
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
        "layout" => cmd_layout(&a),
        "test262" => p5common::test262::supervisor_main(&a, ENGINE, ENGINE_VERSION),
        "test262-worker" => p5common::test262::worker_main(&a, t262::exec),
        _ => {
            eprintln!("usage: p5-qjs cases|layout|test262|test262-worker ...");
            std::process::exit(2);
        }
    }
}
