//! test262 runner shared by the engines: metadata parsing, selection, a crash-isolating
//! supervisor (worker processes, per-test hard timeout) and aggregation.
//!
//! Engines implement only `ExecFn`: run the prepared includes and the test source in a fresh
//! realm and report what was thrown and printed. Pass/fail is decided here, the same way
//! for every engine, following test262's INTERPRETING.md.
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[derive(Clone, Debug, Default)]
pub struct Meta {
    pub includes: Vec<String>,
    pub flags: Vec<String>,
    pub features: Vec<String>,
    pub negative_phase: Option<String>,
    pub negative_type: Option<String>,
}

impl Meta {
    pub fn has_flag(&self, f: &str) -> bool {
        self.flags.iter().any(|x| x == f)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Sloppy,
    Strict,
    Module,
    Raw,
}

impl Mode {
    pub fn name(&self) -> &'static str {
        match self {
            Mode::Sloppy => "sloppy",
            Mode::Strict => "strict",
            Mode::Module => "module",
            Mode::Raw => "raw",
        }
    }
}

/// Everything an engine needs to execute one test in one mode.
pub struct Job<'a> {
    pub root: &'a Path,
    pub rel: &'a str,
    pub abs: PathBuf,
    pub source: &'a str,
    pub meta: &'a Meta,
    pub mode: Mode,
    /// Harness files to evaluate first, as separate global scripts, in order.
    pub includes: Vec<(String, String)>,
    pub timeout_ms: u64,
}

/// What the engine observed.
#[derive(Default)]
pub struct Raw {
    /// Constructor name and "Name: message" of the uncaught error, if any.
    pub error: Option<(String, String)>,
    /// True when the error came from an include (harness) rather than the test.
    pub include_error: bool,
    /// Everything passed to print().
    pub printed: String,
}

pub type ExecFn = fn(&Job) -> Raw;

/// Parses the YAML front matter between `/*---` and `---*/` (the subset test262 uses).
pub fn parse_meta(src: &str) -> Meta {
    let mut m = Meta::default();
    let start = match src.find("/*---") {
        Some(i) => i + 5,
        None => return m,
    };
    let end = match src[start..].find("---*/") {
        Some(j) => start + j,
        None => return m,
    };
    let yaml = &src[start..end];
    let mut current: Option<String> = None;
    let mut in_negative = false;
    for line in yaml.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let indented = line.starts_with(' ') || line.starts_with('\t');
        if !indented {
            in_negative = false;
            current = None;
            if let Some((k, v)) = trimmed.split_once(':') {
                let key = k.trim();
                let val = v.trim();
                match key {
                    "includes" | "flags" | "features" => {
                        if val.starts_with('[') {
                            let items: Vec<String> = val
                                .trim_start_matches('[')
                                .trim_end_matches(']')
                                .split(',')
                                .map(|x| x.trim().trim_matches('"').trim_matches('\'').to_string())
                                .filter(|x| !x.is_empty())
                                .collect();
                            list_mut(&mut m, key).extend(items);
                        } else if val.is_empty() {
                            current = Some(key.to_string());
                        }
                    }
                    "negative" => in_negative = true,
                    _ => {}
                }
            }
        } else if let Some(item) = trimmed.strip_prefix("- ") {
            if let Some(key) = &current {
                let k = key.clone();
                list_mut(&mut m, &k).push(item.trim().trim_matches('"').to_string());
            }
        } else if in_negative {
            if let Some((k, v)) = trimmed.split_once(':') {
                match k.trim() {
                    "phase" => m.negative_phase = Some(v.trim().to_string()),
                    "type" => m.negative_type = Some(v.trim().to_string()),
                    _ => {}
                }
            }
        }
    }
    m
}

fn list_mut<'a>(m: &'a mut Meta, key: &str) -> &'a mut Vec<String> {
    match key {
        "includes" => &mut m.includes,
        "flags" => &mut m.flags,
        _ => &mut m.features,
    }
}

pub fn modes_for(meta: &Meta) -> Vec<Mode> {
    if meta.has_flag("module") {
        vec![Mode::Module]
    } else if meta.has_flag("raw") {
        vec![Mode::Raw]
    } else if meta.has_flag("onlyStrict") {
        vec![Mode::Strict]
    } else if meta.has_flag("noStrict") {
        vec![Mode::Sloppy]
    } else {
        vec![Mode::Sloppy, Mode::Strict]
    }
}

/// test262 INTERPRETING.md verdict for one execution.
pub fn verdict(meta: &Meta, raw: &Raw) -> (bool, String) {
    if raw.include_error {
        let e = raw.error.as_ref().map(|e| e.1.clone()).unwrap_or_default();
        return (false, format!("harness include failed: {e}"));
    }
    if let Some(ty) = &meta.negative_type {
        return match &raw.error {
            Some((ctor, msg)) if ctor == ty => {
                if msg.contains("This statement should not be evaluated") {
                    (false, format!("negative test evaluated: {msg}"))
                } else {
                    (true, String::new())
                }
            }
            Some((ctor, msg)) => (false, format!("expected {ty}, got {ctor}: {msg}")),
            None => (false, format!("expected {ty} ({}), nothing thrown", meta.negative_phase.clone().unwrap_or_default())),
        };
    }
    if let Some((_, msg)) = &raw.error {
        return (false, msg.clone());
    }
    if meta.has_flag("async") {
        if raw.printed.contains("Test262:AsyncTestFailure") {
            let line = raw.printed.lines().find(|l| l.contains("Test262:AsyncTestFailure")).unwrap_or("").to_string();
            return (false, line);
        }
        if !raw.printed.contains("Test262:AsyncTestComplete") {
            return (false, "async test did not call $DONE".into());
        }
    }
    (true, String::new())
}

#[derive(Clone, Debug)]
pub struct Config {
    pub commit: String,
    pub skip_features: HashSet<String>,
    pub harness_unsupported_features: HashSet<String>,
    pub exclude_paths: HashSet<String>,
    pub exclude_prefixes: Vec<String>,
    pub include_prefixes: Vec<String>,
    pub timeout_ms: u64,
}

impl Config {
    pub fn load(path: &Path, keep_intl: bool) -> Config {
        let v: Value = serde_json::from_str(&std::fs::read_to_string(path).expect("read test262 config")).expect("parse test262 config");
        let strs = |k: &str| -> Vec<String> {
            v.get(k)
                .and_then(|x| x.as_array())
                .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
                .unwrap_or_default()
        };
        let mut skip: HashSet<String> = strs("skip_features").into_iter().collect();
        let mut exclude_prefixes = strs("exclude_prefixes");
        if keep_intl {
            skip.retain(|f| !(f.starts_with("Intl") || f.starts_with("intl")));
            exclude_prefixes.retain(|p| !p.starts_with("test/intl402"));
        }
        Config {
            commit: v.get("test262_commit").and_then(|x| x.as_str()).unwrap_or("").to_string(),
            skip_features: skip,
            harness_unsupported_features: strs("harness_unsupported_features").into_iter().collect(),
            exclude_paths: strs("exclude_paths").into_iter().collect(),
            exclude_prefixes,
            include_prefixes: strs("include_prefixes"),
            timeout_ms: v.get("timeout_ms").and_then(|x| x.as_u64()).unwrap_or(10000),
        }
    }
}

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    let mut entries: Vec<PathBuf> = match std::fs::read_dir(dir) {
        Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
        Err(_) => return,
    };
    entries.sort();
    for p in entries {
        if p.is_dir() {
            walk(&p, out);
        } else if p.extension().map(|e| e == "js").unwrap_or(false) {
            let name = p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
            if !name.contains("_FIXTURE") {
                out.push(p);
            }
        }
    }
}

fn rel_of(root: &Path, p: &Path) -> String {
    p.strip_prefix(root).unwrap_or(p).to_string_lossy().replace('\\', "/")
}

/// Why a test is not run, or None when it runs.
pub fn skip_reason(cfg: &Config, rel: &str, src: &str, meta: &Meta) -> Option<String> {
    if cfg.exclude_paths.contains(rel) {
        return Some("config:exclude".into());
    }
    let excluded = cfg.exclude_prefixes.iter().any(|p| rel.starts_with(p.as_str()));
    let reincluded = cfg.include_prefixes.iter().any(|p| rel.starts_with(p.as_str()));
    if excluded && !reincluded {
        return Some("config:exclude-dir".into());
    }
    for f in &meta.features {
        if cfg.skip_features.contains(f) {
            return Some(format!("feature:{f}"));
        }
    }
    for f in &meta.features {
        if cfg.harness_unsupported_features.contains(f) {
            return Some(format!("harness:{f}"));
        }
    }
    if meta.has_flag("CanBlockIsFalse") {
        return Some("harness:CanBlockIsFalse".into());
    }
    if src.contains("$262.agent") {
        return Some("harness:$262.agent".into());
    }
    if src.contains("$262.createRealm") || src.contains("$262.AbstractModuleSource") {
        return Some("harness:$262.createRealm".into());
    }
    None
}

/// Directory key used for "pass rate by feature directory": test/<a>/<b>.
pub fn dir_key(rel: &str, depth: usize) -> String {
    let parts: Vec<&str> = rel.split('/').collect();
    if parts.len() < 3 {
        return parts.join("/");
    }
    let n = (depth + 2).min(parts.len() - 1).max(2);
    parts[1..n].join("/")
}

// ------------------------------------------------------------------ worker

pub fn worker_main(args: &crate::util::Args, exec: ExecFn) {
    let root = absolute(&args.req("root"));
    let list = std::fs::read_to_string(args.req("list")).expect("read list");
    let timeout_ms = args.num("timeout-ms", 10000);
    let mut harness: HashMap<String, String> = HashMap::new();
    let stdout = std::io::stdout();
    for (idx, rel) in list.lines().enumerate() {
        if rel.is_empty() {
            continue;
        }
        {
            let mut o = stdout.lock();
            let _ = writeln!(o, "S\t{idx}");
            let _ = o.flush();
        }
        let abs = root.join(rel);
        let source = std::fs::read_to_string(&abs).unwrap_or_default();
        let meta = parse_meta(&source);
        let mut results = Vec::new();
        for mode in modes_for(&meta) {
            let mut names: Vec<String> = Vec::new();
            if mode != Mode::Raw {
                names.push("assert.js".into());
                names.push("sta.js".into());
            }
            if meta.has_flag("async") {
                names.push("doneprintHandle.js".into());
            }
            for i in &meta.includes {
                if !names.contains(i) {
                    names.push(i.clone());
                }
            }
            let mut includes = Vec::new();
            for n in names {
                let src = harness
                    .entry(n.clone())
                    .or_insert_with(|| std::fs::read_to_string(root.join("harness").join(&n)).unwrap_or_default())
                    .clone();
                includes.push((n, src));
            }
            let job = Job { root: &root, rel, abs: abs.clone(), source: &source, meta: &meta, mode, includes, timeout_ms };
            let raw = exec(&job);
            let (pass, msg) = verdict(&meta, &raw);
            let short: String = msg.chars().take(300).collect();
            results.push(json!({"mode": mode.name(), "pass": pass, "msg": short}));
        }
        let mut o = stdout.lock();
        let _ = writeln!(o, "R\t{idx}\t{}", Value::Array(results));
        let _ = o.flush();
    }
}

// ------------------------------------------------------------------ supervisor

enum Line {
    Started(usize),
    Result(usize, Value),
    Eof,
}

struct Chunk {
    tests: Vec<String>,
    base: usize,
}

fn run_chunk(exe: &Path, root: &Path, work: &Path, chunk: &Chunk, timeout_ms: u64, extra: &[String], results: &Mutex<Vec<Option<Value>>>, tag: usize) {
    let mut next = 0usize;
    let mut attempt = 0usize;
    while next < chunk.tests.len() {
        attempt += 1;
        let list_path = work.join(format!("list-{tag}-{attempt}.txt"));
        std::fs::write(&list_path, chunk.tests[next..].join("\n")).expect("write list");
        let mut child = match Command::new(exe)
            .arg("test262-worker")
            .arg("--root")
            .arg(root)
            .arg("--list")
            .arg(&list_path)
            .arg("--timeout-ms")
            .arg(timeout_ms.to_string())
            .args(extra)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                let mut r = results.lock().unwrap();
                for i in next..chunk.tests.len() {
                    r[chunk.base + i] = Some(json!([{"mode": "-", "pass": false, "msg": format!("spawn failed: {e}"), "kind": "crash"}]));
                }
                return;
            }
        };
        let stdout = child.stdout.take().expect("stdout");
        let (tx, rx) = mpsc::channel::<Line>();
        let reader = std::thread::spawn(move || {
            let br = BufReader::new(stdout);
            for line in br.lines() {
                let line = match line {
                    Ok(l) => l,
                    Err(_) => break,
                };
                let mut parts = line.splitn(3, '\t');
                let tag = parts.next().unwrap_or("");
                let idx = parts.next().and_then(|x| x.parse::<usize>().ok());
                match (tag, idx) {
                    ("S", Some(i)) => {
                        let _ = tx.send(Line::Started(i));
                    }
                    ("R", Some(i)) => {
                        let v = parts.next().and_then(|x| serde_json::from_str::<Value>(x).ok()).unwrap_or(Value::Null);
                        let _ = tx.send(Line::Result(i, v));
                    }
                    _ => {}
                }
            }
            let _ = tx.send(Line::Eof);
        });
        let offset = next;
        let mut current: Option<usize> = None;
        let hard = Duration::from_millis(timeout_ms + 10000);
        let mut last = Instant::now();
        let mut restart_from: Option<usize> = None;
        loop {
            match rx.recv_timeout(Duration::from_millis(500)) {
                Ok(Line::Started(i)) => {
                    current = Some(offset + i);
                    last = Instant::now();
                }
                Ok(Line::Result(i, v)) => {
                    let gi = offset + i;
                    results.lock().unwrap()[chunk.base + gi] = Some(v);
                    current = None;
                    next = gi + 1;
                    last = Instant::now();
                }
                Ok(Line::Eof) => {
                    let status = child.wait().map(|s| format!("{s:?}")).unwrap_or_else(|e| e.to_string());
                    if let Some(c) = current {
                        results.lock().unwrap()[chunk.base + c] =
                            Some(json!([{"mode": "-", "pass": false, "msg": format!("worker crashed: {status}"), "kind": "crash"}]));
                        restart_from = Some(c + 1);
                    } else if next < chunk.tests.len() {
                        // exited between tests: mark the next one, continue after it
                        results.lock().unwrap()[chunk.base + next] =
                            Some(json!([{"mode": "-", "pass": false, "msg": format!("worker exited early: {status}"), "kind": "crash"}]));
                        restart_from = Some(next + 1);
                    }
                    break;
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    if current.is_some() && last.elapsed() > hard {
                        let _ = child.kill();
                        let _ = child.wait();
                        let c = current.unwrap();
                        results.lock().unwrap()[chunk.base + c] =
                            Some(json!([{"mode": "-", "pass": false, "msg": format!("hard timeout {} ms (worker killed)", hard.as_millis()), "kind": "timeout"}]));
                        restart_from = Some(c + 1);
                        // drain the reader until EOF
                        while let Ok(l) = rx.recv_timeout(Duration::from_secs(5)) {
                            if let Line::Eof = l {
                                break;
                            }
                        }
                        break;
                    }
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
        let _ = reader.join();
        let _ = std::fs::remove_file(&list_path);
        match restart_from {
            Some(r) => next = r,
            None => {
                if next < chunk.tests.len() {
                    // reader ended without EOF bookkeeping; avoid an endless loop
                    let mut r = results.lock().unwrap();
                    for i in next..chunk.tests.len() {
                        if r[chunk.base + i].is_none() {
                            r[chunk.base + i] = Some(json!([{"mode": "-", "pass": false, "msg": "not executed", "kind": "crash"}]));
                        }
                    }
                    return;
                }
            }
        }
    }
}

/// Parses QuickJS-NG's test262_errors.txt: lines "test262/test/<path>:<line>: [strict mode: ]msg".
pub fn parse_expected_errors(text: &str) -> HashSet<(String, bool)> {
    let mut set = HashSet::new();
    for line in text.lines() {
        let l = line.trim();
        let l = l.strip_prefix("test262/").unwrap_or(l);
        if let Some(i) = l.find(".js:") {
            let path = l[..i + 3].to_string();
            let rest = &l[i + 4..];
            let strict = rest.splitn(2, ": ").nth(1).map(|r| r.starts_with("strict mode:")).unwrap_or(false);
            set.insert((path, strict));
        }
    }
    set
}

/// Canonical absolute path (module loaders resolve specifiers against absolute referrers).
pub fn absolute(p: &str) -> PathBuf {
    std::fs::canonicalize(p).unwrap_or_else(|_| PathBuf::from(p))
}

pub fn supervisor_main(args: &crate::util::Args, engine: &str, engine_version: &str) {
    let root = absolute(&args.req("root"));
    let cfg = Config::load(Path::new(&args.req("config")), args.flag("keep-intl"));
    let out_path = PathBuf::from(args.req("out"));
    let work = PathBuf::from(args.get("work").unwrap_or_else(|| "work/t262".into()));
    std::fs::create_dir_all(&work).expect("work dir");
    let dirs: Vec<String> = args.req("dirs").split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
    let jobs = args.num("jobs", std::thread::available_parallelism().map(|n| n.get() as u64).unwrap_or(2)) as usize;
    let timeout_ms = args.num("timeout-ms", cfg.timeout_ms);
    let limit = args.num("limit", 0) as usize;
    let extra: Vec<String> = args.get("worker-args").map(|s| s.split_whitespace().map(String::from).collect()).unwrap_or_default();
    let exe = std::env::current_exe().expect("current_exe");
    let t0 = Instant::now();

    let mut files = Vec::new();
    for d in &dirs {
        walk(&root.join(d), &mut files);
    }
    let mut run: Vec<String> = Vec::new();
    let mut metas: HashMap<String, Meta> = HashMap::new();
    let mut skipped: BTreeMap<String, u64> = BTreeMap::new();
    let mut skipped_by_dir: BTreeMap<String, u64> = BTreeMap::new();
    for p in &files {
        let rel = rel_of(&root, p);
        let src = std::fs::read_to_string(p).unwrap_or_default();
        let meta = parse_meta(&src);
        match skip_reason(&cfg, &rel, &src, &meta) {
            Some(r) => {
                *skipped.entry(r).or_insert(0) += 1;
                *skipped_by_dir.entry(dir_key(&rel, 1)).or_insert(0) += 1;
            }
            None => {
                run.push(rel.clone());
                metas.insert(rel, meta);
            }
        }
    }
    if limit > 0 && run.len() > limit {
        run.truncate(limit);
    }
    let n = run.len();
    let results: Arc<Mutex<Vec<Option<Value>>>> = Arc::new(Mutex::new(vec![None; n]));
    let mut queue = VecDeque::new();
    let chunk_size = args.num("chunk", 200) as usize;
    let mut base = 0;
    while base < n {
        let end = (base + chunk_size).min(n);
        queue.push_back(Chunk { tests: run[base..end].to_vec(), base });
        base = end;
    }
    let queue = Arc::new(Mutex::new(queue));
    std::thread::scope(|scope| {
        for t in 0..jobs.max(1) {
            let queue = Arc::clone(&queue);
            let results = Arc::clone(&results);
            let exe = exe.clone();
            let root = root.clone();
            let work = work.clone();
            let extra = extra.clone();
            scope.spawn(move || {
                let mut k = 0usize;
                loop {
                    let chunk = { queue.lock().unwrap().pop_front() };
                    let chunk = match chunk {
                        Some(c) => c,
                        None => break,
                    };
                    k += 1;
                    run_chunk(&exe, &root, &work, &chunk, timeout_ms, &extra, &results, t * 100000 + k);
                }
            });
        }
    });

    // aggregate
    let expected = args
        .get("expected-errors")
        .and_then(|p| std::fs::read_to_string(p).ok())
        .map(|t| parse_expected_errors(&t));
    let results = results.lock().unwrap();
    let mut pass = 0u64;
    let mut fail = 0u64;
    let mut crash = 0u64;
    let mut timeout = 0u64;
    let mut by_dir: BTreeMap<String, [u64; 2]> = BTreeMap::new();
    let mut by_dir3: BTreeMap<String, [u64; 2]> = BTreeMap::new();
    let mut by_feature: BTreeMap<String, [u64; 2]> = BTreeMap::new();
    let mut msgs: BTreeMap<String, u64> = BTreeMap::new();
    let mut failures: Vec<Value> = Vec::new();
    let mut fail_lines: Vec<String> = Vec::new();
    let mut ours_failed: HashSet<(String, bool)> = HashSet::new();
    let mut files_all_pass = 0u64;
    for (i, rel) in run.iter().enumerate() {
        let r = results[i].clone().unwrap_or_else(|| json!([{"mode": "-", "pass": false, "msg": "no result", "kind": "crash"}]));
        let mut arr = r.as_array().cloned().unwrap_or_default();
        if arr.is_empty() {
            arr.push(json!({"mode": "-", "pass": false, "msg": "no parseable result from worker", "kind": "crash"}));
        }
        let mut file_ok = true;
        for m in &arr {
            let ok = m.get("pass").and_then(|x| x.as_bool()).unwrap_or(false);
            let mode = m.get("mode").and_then(|x| x.as_str()).unwrap_or("-").to_string();
            let kind = m.get("kind").and_then(|x| x.as_str()).unwrap_or("");
            let msg = m.get("msg").and_then(|x| x.as_str()).unwrap_or("").to_string();
            let idx = if ok { 0 } else { 1 };
            by_dir.entry(dir_key(rel, 1)).or_insert([0, 0])[idx] += 1;
            by_dir3.entry(dir_key(rel, 2)).or_insert([0, 0])[idx] += 1;
            if let Some(meta) = metas.get(rel) {
                for f in &meta.features {
                    by_feature.entry(f.clone()).or_insert([0, 0])[idx] += 1;
                }
            }
            if ok {
                pass += 1;
            } else {
                file_ok = false;
                match kind {
                    "crash" => crash += 1,
                    "timeout" => timeout += 1,
                    _ => fail += 1,
                }
                let head: String = msg.chars().take(80).collect();
                *msgs.entry(head).or_insert(0) += 1;
                if failures.len() < 300 {
                    failures.push(json!({"path": rel, "mode": mode, "msg": msg}));
                }
                fail_lines.push(format!("{rel}\t{mode}\t{msg}"));
                ours_failed.insert((rel.clone(), mode == "strict"));
            }
        }
        if file_ok {
            files_all_pass += 1;
        }
    }
    let total = pass + fail + crash + timeout;
    let rate = |a: &[u64; 2]| if a[0] + a[1] > 0 { a[0] as f64 / (a[0] + a[1]) as f64 } else { 0.0 };
    let table = |m: &BTreeMap<String, [u64; 2]>| -> Value {
        let mut o = Map::new();
        for (k, v) in m {
            o.insert(k.clone(), json!({"pass": v[0], "fail": v[1], "total": v[0] + v[1], "pass_rate": rate(v)}));
        }
        Value::Object(o)
    };
    let mut top_msgs: Vec<(String, u64)> = msgs.into_iter().collect();
    top_msgs.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    top_msgs.truncate(40);
    let mut out = json!({
        "engine": engine,
        "engine_version": engine_version,
        "test262_commit": cfg.commit,
        "dirs": dirs,
        "keep_intl_features": args.flag("keep-intl"),
        "files_discovered": files.len(),
        "files_run": n,
        "files_all_modes_pass": files_all_pass,
        "skipped_files": skipped,
        "skipped_files_by_dir": skipped_by_dir,
        "pass": pass, "fail": fail + crash + timeout, "total": total,
        "assertion_fail": fail, "crash": crash, "timeout": timeout,
        "pass_rate": if total > 0 { pass as f64 / total as f64 } else { 0.0 },
        "pass_criterion": "per (file, mode) execution: no uncaught error and $DONE completion for async tests; negative tests must throw the declared constructor (test262 INTERPRETING.md)",
        "by_dir": table(&by_dir),
        "by_dir3": table(&by_dir3),
        "by_feature": table(&by_feature),
        "top_failure_messages": top_msgs.iter().map(|(m, c)| json!({"msg": m, "count": c})).collect::<Vec<_>>(),
        "first_failures": failures,
        "wall_s": t0.elapsed().as_secs_f64(),
        "jobs": jobs,
        "timeout_ms": timeout_ms
    });
    if let Some(exp) = expected {
        // only paths that were run can be compared
        let ran: HashSet<&String> = run.iter().collect();
        let exp_run: HashSet<(String, bool)> = exp.iter().filter(|(p, _)| ran.contains(p)).cloned().collect();
        let matched = ours_failed.intersection(&exp_run).count();
        let mut unexpected_fail: Vec<String> = ours_failed.difference(&exp_run).map(|(p, s)| format!("{p}{}", if *s { " [strict]" } else { "" })).collect();
        let mut unexpected_pass: Vec<String> = exp_run.difference(&ours_failed).map(|(p, s)| format!("{p}{}", if *s { " [strict]" } else { "" })).collect();
        unexpected_fail.sort();
        unexpected_pass.sort();
        out["upstream_expected_failures"] = json!({
            "source": "quickjs-ng test262_errors.txt vendored in rquickjs-sys 0.14.0",
            "listed_and_run": exp_run.len(),
            "failed_here_too": matched,
            "unexpected_failures": unexpected_fail.len(),
            "unexpected_passes": unexpected_pass.len(),
            "unexpected_failures_list": unexpected_fail.into_iter().take(200).collect::<Vec<_>>(),
            "unexpected_passes_list": unexpected_pass.into_iter().take(100).collect::<Vec<_>>()
        });
    }
    std::fs::write(&out_path, serde_json::to_string_pretty(&out).unwrap()).expect("write result");
    let mut fl = out_path.clone();
    fl.set_extension("failures.txt");
    let _ = std::fs::write(&fl, fail_lines.join("\n"));
    eprintln!("{engine}: {pass}/{total} pass ({} files run, {} skipped) in {:.0}s", n, files.len() - n, t0.elapsed().as_secs_f64());
}
