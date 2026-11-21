//! The case driver: loads shims + one library bundle into an engine and runs a case group
//! with the host loop every engine shares (microtask drain, virtual timers, budgets).
use crate::util::{classify, rss_kb};
use serde_json::{json, Map, Value};
use std::path::PathBuf;
use std::time::{Duration, Instant};

/// What an engine must provide to the driver.
pub trait Host {
    /// Evaluates a classic (sloppy-mode) script; returns String(completion value) or the
    /// thrown error as "Name: message".
    fn eval(&mut self, src: &str, name: &str) -> Result<String, String>;
    /// Runs up to `max` pending promise jobs; returns how many ran.
    fn run_jobs(&mut self, max: usize) -> Result<usize, String>;
    /// Wall-clock deadline enforced inside the engine where it can (interrupt handler).
    fn set_deadline(&mut self, deadline: Instant);
    /// Engine-specific facts recorded after each case (e.g. heap usage).
    fn extra(&mut self) -> Value {
        Value::Null
    }
}

pub struct RunOpts {
    pub dist: PathBuf,
    pub shim_config: Value,
    pub only: Option<String>,
    pub case_timeout_ms: u64,
    pub load_timeout_ms: u64,
    pub max_jobs: u64,
}

impl RunOpts {
    pub fn from_args(a: &crate::util::Args) -> RunOpts {
        let shim_config = a
            .get("shim-config")
            .and_then(|s| serde_json::from_str::<Value>(&s).ok())
            .unwrap_or_else(|| json!({}));
        RunOpts {
            dist: PathBuf::from(a.req("dist")),
            shim_config,
            only: a.get("only"),
            case_timeout_ms: a.num("timeout-ms", 20000),
            load_timeout_ms: a.num("load-timeout-ms", 120000),
            max_jobs: a.num("max-jobs", 5_000_000),
        }
    }
}

fn s(v: &Value, k: &str) -> String {
    v.get(k).and_then(|x| x.as_str()).unwrap_or("").to_string()
}

/// Runs one case group. `group` is a parsed dist/cases/<group>.json.
pub fn run_group<H: Host>(host: &mut H, group: &Value, opts: &RunOpts) -> Value {
    let mut out = Map::new();
    let group_name = s(group, "group");
    let bundle = s(group, "bundle");
    out.insert("group".into(), json!(group_name));
    out.insert("bundle".into(), json!(bundle));
    out.insert("shim_config".into(), opts.shim_config.clone());
    let drain_all = group_name.starts_with("sandbox");
    let t0 = Instant::now();
    host.set_deadline(t0 + Duration::from_millis(opts.load_timeout_ms));

    let cfg = format!("globalThis.__P5_SHIM_CONFIG = {}; 0", opts.shim_config);
    let mut fatal: Option<String> = host.eval(&cfg, "config.js").err();
    if fatal.is_none() {
        match std::fs::read_to_string(opts.dist.join("shims.js")) {
            Ok(src) => fatal = host.eval(&src, "shims.js").err().map(|e| format!("shims: {e}")),
            Err(e) => fatal = Some(format!("read shims.js: {e}")),
        }
    }
    let l0 = Instant::now();
    if fatal.is_none() {
        match std::fs::read_to_string(opts.dist.join(format!("{bundle}.js"))) {
            Ok(src) => fatal = host.eval(&src, &format!("{bundle}.js")).err().map(|e| format!("bundle: {e}")),
            Err(e) => fatal = Some(format!("read bundle: {e}")),
        }
    }
    out.insert("load_ms".into(), json!(l0.elapsed().as_secs_f64() * 1000.0));
    let (rss, hwm) = rss_kb();
    out.insert("after_load_rss_kb".into(), json!(rss));
    out.insert("after_load_hwm_kb".into(), json!(hwm));
    if fatal.is_none() {
        match host.eval("__p5.environment()", "env.js") {
            Ok(env) => {
                out.insert("environment".into(), serde_json::from_str::<Value>(&env).unwrap_or(Value::Null));
            }
            Err(e) => fatal = Some(format!("environment: {e}")),
        }
    }
    let mut records = Vec::new();
    let empty = Vec::new();
    let cases = group.get("cases").and_then(|c| c.as_array()).unwrap_or(&empty);
    for case in cases {
        let id = s(case, "id");
        if let Some(only) = &opts.only {
            if &id != only {
                continue;
            }
        }
        if let Some(f) = &fatal {
            records.push(json!({"id": id, "status": "error", "error": f, "error_type": classify(f), "ms": 0.0}));
            continue;
        }
        records.push(run_case(host, case, opts, drain_all));
    }
    if let Some(f) = &fatal {
        out.insert("fatal".into(), json!(f));
    }
    out.insert("cases".into(), Value::Array(records));
    out.insert("total_ms".into(), json!(t0.elapsed().as_secs_f64() * 1000.0));
    let (rss, hwm) = rss_kb();
    out.insert("final_rss_kb".into(), json!(rss));
    out.insert("peak_rss_kb".into(), json!(hwm));
    Value::Object(out)
}

fn run_case<H: Host>(host: &mut H, case: &Value, opts: &RunOpts, drain_all: bool) -> Value {
    let id = s(case, "id");
    let input = case.get("input").cloned().unwrap_or(Value::Null).to_string();
    let start = Instant::now();
    let deadline = start + Duration::from_millis(opts.case_timeout_ms);
    host.set_deadline(deadline);
    let mut host_error: Option<String> = None;
    let mut jobs_total: u64 = 0;
    let mut steps: u64 = 0;
    if let Err(e) = host.eval(&format!("__p5.start({input}); 0"), "start.js") {
        host_error = Some(e);
    }
    'outer: while host_error.is_none() {
        // 1. drain the microtask queue
        loop {
            if Instant::now() > deadline {
                host_error = Some("Timeout: host deadline reached while running promise jobs".into());
                break 'outer;
            }
            match host.run_jobs(1000) {
                Ok(0) => break,
                Ok(n) => {
                    jobs_total += n as u64;
                    if jobs_total > opts.max_jobs {
                        host_error = Some(format!("JobBudget: more than {} promise jobs", opts.max_jobs));
                        break 'outer;
                    }
                }
                Err(e) => {
                    host_error = Some(e);
                    break 'outer;
                }
            }
        }
        // 2. settled?
        let st = match host.eval("__p5.status()", "status.js") {
            Ok(v) => v,
            Err(e) => {
                host_error = Some(e);
                break;
            }
        };
        if st == "error" || (st == "done" && !drain_all) {
            break;
        }
        if Instant::now() > deadline {
            host_error = Some("Timeout: host deadline".into());
            break;
        }
        steps += 1;
        // 3. advance virtual time to the next timer
        match host.eval("__p5.tick()", "tick.js") {
            Ok(t) if t == "true" => {}
            Ok(_) => {
                if st == "pending" {
                    // no timer left: one last drain, then it must have settled
                    match host.run_jobs(100000) {
                        Ok(n) => jobs_total += n as u64,
                        Err(e) => host_error = Some(e),
                    }
                    if host_error.is_none() {
                        if let Ok(st2) = host.eval("__p5.status()", "status.js") {
                            if st2 == "pending" {
                                host_error = Some("NeverSettled: no promise jobs or timers left".into());
                            }
                        }
                    }
                }
                break;
            }
            Err(e) => {
                host_error = Some(e);
                break;
            }
        }
    }
    let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
    host.set_deadline(Instant::now() + Duration::from_secs(10));
    let mut take_error = String::new();
    let taken: Value = match host.eval("__p5.take()", "take.js") {
        Ok(t) => serde_json::from_str::<Value>(&t).unwrap_or(Value::Null),
        Err(e) => {
            take_error = e;
            Value::Null
        }
    };
    let (rss, hwm) = rss_kb();
    let mut rec = Map::new();
    rec.insert("id".into(), json!(id));
    let taken_status = taken.get("status").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
    let error = match &host_error {
        Some(e) => Some(e.clone()),
        None if taken_status == "error" => Some(s(&taken, "error")),
        None if taken_status == "unknown" => Some(format!("HostError: __p5.take() failed: {take_error}")),
        None => None,
    };
    let status = if error.is_some() { "error" } else { taken_status.as_str() };
    rec.insert("status".into(), json!(status));
    if let Some(e) = &error {
        rec.insert("error_type".into(), json!(classify(e)));
        let short: String = e.chars().take(2000).collect();
        rec.insert("error".into(), json!(short));
    } else if let Some(r) = taken.get("result") {
        rec.insert("output".into(), r.clone());
    }
    rec.insert("ms".into(), json!(elapsed_ms));
    rec.insert("jobs".into(), json!(jobs_total));
    rec.insert("timer_steps".into(), json!(steps));
    for k in ["usage", "timer_callbacks", "virtual_ms", "diagnostics_total"] {
        if let Some(v) = taken.get(k) {
            rec.insert(k.into(), v.clone());
        }
    }
    if let Some(d) = taken.get("diagnostics").and_then(|d| d.as_array()) {
        rec.insert("diagnostics".into(), Value::Array(d.iter().take(5).cloned().collect()));
    }
    rec.insert("rss_kb".into(), json!(rss));
    rec.insert("hwm_kb".into(), json!(hwm));
    let extra = host.extra();
    if !extra.is_null() {
        rec.insert("engine".into(), extra);
    }
    if let Some(e) = case.get("expect") {
        rec.insert("expect".into(), e.clone());
    }
    Value::Object(rec)
}
