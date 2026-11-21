use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

const MAX_FAILURES: usize = 20;

fn decode(mode: &str, data: &[u8]) -> Result<Vec<u8>, String> {
    let m = match mode {
        "auto" if data.starts_with(b"wOF2") => "woff2",
        "auto" if data.starts_with(b"wOFF") => "woff1",
        "auto" => return Err("unknown magic".into()),
        m => m,
    };
    match m {
        "woff2" => wuff::decompress_woff2(data).map_err(|e| e.to_string()),
        "woff1" => wuff::decompress_woff1(data).map_err(|e| e.to_string()),
        _ => Err(format!("bad mode {m}")),
    }
}

fn decode_one(args: &[String]) -> ! {
    std::panic::set_hook(Box::new(|_| {}));
    let mode = args[0].clone();
    let data = match std::fs::read(&args[1]) {
        Ok(d) => d,
        Err(_) => std::process::exit(4),
    };
    let out = args[2].clone();
    match catch_unwind(AssertUnwindSafe(|| decode(&mode, &data))) {
        Ok(Ok(v)) => {
            if out != "-" && std::fs::write(&out, &v).is_err() {
                std::process::exit(5);
            }
            std::process::exit(0)
        }
        Ok(Err(_)) => std::process::exit(1),
        Err(_) => std::process::exit(3),
    }
}

#[cfg(unix)]
fn signal_of(st: &std::process::ExitStatus) -> Option<i32> {
    use std::os::unix::process::ExitStatusExt;
    st.signal()
}

#[cfg(not(unix))]
fn signal_of(_st: &std::process::ExitStatus) -> Option<i32> {
    None
}

fn run_child(exe: &Path, mode: &str, input: &Path, out: &str, timeout: Duration) -> (String, f64) {
    let start = Instant::now();
    let child = Command::new(exe)
        .arg("decode-one")
        .arg(mode)
        .arg(input)
        .arg(out)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
    let mut child = match child {
        Ok(c) => c,
        Err(e) => return (format!("spawn_error:{e}"), 0.0),
    };
    loop {
        match child.try_wait() {
            Ok(Some(st)) => {
                let ms = start.elapsed().as_secs_f64() * 1000.0;
                let s = match st.code() {
                    Some(0) => "ok".to_string(),
                    Some(1) => "err".to_string(),
                    Some(3) => "panic".to_string(),
                    Some(c) => format!("exit_{c}"),
                    None => format!("crash_signal_{}", signal_of(&st).unwrap_or(-1)),
                };
                return (s, ms);
            }
            Ok(None) => {
                if start.elapsed() > timeout {
                    let _ = child.kill();
                    let _ = child.wait();
                    return ("hang".to_string(), start.elapsed().as_secs_f64() * 1000.0);
                }
                std::thread::sleep(Duration::from_millis(2));
            }
            Err(e) => return (format!("wait_error:{e}"), 0.0),
        }
    }
}

struct Rng(u64);
impl Rng {
    fn new(seed: u64) -> Self {
        Rng(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }
    fn next(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
    fn below(&mut self, n: usize) -> usize {
        if n == 0 {
            0
        } else {
            (self.next() % n as u64) as usize
        }
    }
}

#[derive(Clone)]
enum Mutation {
    Truncate(usize),
    BitFlip(u64),
    HeaderBitFlip(u64),
    Burst(u64),
    Garbage { seed: u64, size: usize, magic: Option<[u8; 4]> },
}

impl Mutation {
    fn category(&self) -> &'static str {
        match self {
            Mutation::Truncate(_) => "truncated",
            Mutation::BitFlip(_) => "bit_flip",
            Mutation::HeaderBitFlip(_) => "header_bit_flip",
            Mutation::Burst(_) => "byte_burst",
            Mutation::Garbage { magic: None, .. } => "garbage",
            Mutation::Garbage { .. } => "garbage_with_magic",
        }
    }
    fn apply(&self, src: &[u8]) -> Vec<u8> {
        match self {
            Mutation::Truncate(n) => src[..(*n).min(src.len())].to_vec(),
            Mutation::BitFlip(seed) => {
                let mut v = src.to_vec();
                let mut r = Rng::new(*seed);
                if !v.is_empty() {
                    let p = r.below(v.len());
                    v[p] ^= 1 << r.below(8);
                }
                v
            }
            Mutation::HeaderBitFlip(seed) => {
                let mut v = src.to_vec();
                let mut r = Rng::new(*seed);
                let lim = v.len().min(512);
                if lim > 0 {
                    let p = r.below(lim);
                    v[p] ^= 1 << r.below(8);
                }
                v
            }
            Mutation::Burst(seed) => {
                let mut v = src.to_vec();
                let mut r = Rng::new(*seed);
                if !v.is_empty() {
                    let p = r.below(v.len());
                    for i in p..(p + 16).min(v.len()) {
                        v[i] = r.next() as u8;
                    }
                }
                v
            }
            Mutation::Garbage { seed, size, magic } => {
                let mut r = Rng::new(*seed);
                let mut v: Vec<u8> = (0..*size).map(|_| r.next() as u8).collect();
                if let Some(m) = magic {
                    for (i, b) in m.iter().enumerate() {
                        if i < v.len() {
                            v[i] = *b;
                        }
                    }
                }
                v
            }
        }
    }
    fn describe(&self) -> String {
        match self {
            Mutation::Truncate(n) => format!("truncate to {n} bytes"),
            Mutation::BitFlip(s) => format!("single bit flip seed {s}"),
            Mutation::HeaderBitFlip(s) => format!("bit flip in first 512 bytes seed {s}"),
            Mutation::Burst(s) => format!("16-byte random burst seed {s}"),
            Mutation::Garbage { seed, size, magic } => {
                format!("{size} random bytes seed {seed} magic {:?}", magic.map(|m| String::from_utf8_lossy(&m).to_string()))
            }
        }
    }
}

struct Job {
    source: Option<usize>,
    label: String,
    mode: String,
    mutation: Mutation,
}

fn parallel<T: Sync, R: Send>(items: &[T], f: impl Fn(&T, usize) -> R + Sync) -> Vec<R> {
    let n = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4).max(1);
    let next = AtomicUsize::new(0);
    let out: Mutex<Vec<Option<R>>> = Mutex::new((0..items.len()).map(|_| None).collect());
    std::thread::scope(|s| {
        for w in 0..n {
            let (next, out, f) = (&next, &out, &f);
            s.spawn(move || loop {
                let i = next.fetch_add(1, Ordering::SeqCst);
                if i >= items.len() {
                    break;
                }
                let r = f(&items[i], w);
                out.lock().unwrap()[i] = Some(r);
            });
        }
    });
    out.into_inner().unwrap().into_iter().map(|r| r.expect("job result")).collect()
}

fn load_manifest(p: &str) -> Value {
    serde_json::from_str(&std::fs::read_to_string(p).expect("read manifest")).expect("parse manifest")
}

fn roundtrip(args: &[String]) {
    let manifest = load_manifest(&args[0]);
    let outdir = PathBuf::from(&args[1]);
    std::fs::create_dir_all(&outdir).expect("mkdir");
    let exe = std::env::current_exe().expect("exe");
    let encoded = manifest["encoded"].as_array().cloned().unwrap_or_default();
    let results = parallel(&encoded, |e, _| {
        let id = e["id"].as_str().unwrap_or("").to_string();
        let path = PathBuf::from(e["path"].as_str().unwrap_or(""));
        let out = outdir.join(format!("{id}.decoded.otf"));
        let (status, ms) = run_child(&exe, "auto", &path, out.to_str().unwrap_or("-"), Duration::from_secs(60));
        let size = std::fs::metadata(&out).map(|m| m.len()).unwrap_or(0);
        json!({
            "id": id, "font_id": e["font_id"], "kind": e["kind"], "input": path.display().to_string(),
            "status": status, "decode_ms": ms,
            "decoded": if status == "ok" { Value::String(out.display().to_string()) } else { Value::Null },
            "decoded_size": size,
        })
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&json!({"wuff_version": "0.2.10", "results": results})).unwrap()).expect("write");
    let ok = results.iter().filter(|r| r["status"] == "ok").count();
    println!("wuff roundtrip decode: {ok}/{} ok", results.len());
}

fn robust(args: &[String]) {
    let manifest = load_manifest(&args[0]);
    let workdir = PathBuf::from(&args[1]);
    std::fs::create_dir_all(&workdir).expect("mkdir");
    let exe = std::env::current_exe().expect("exe");
    let encoded = manifest["encoded"].as_array().cloned().unwrap_or_default();
    let mut sources: Vec<(String, Arc<Vec<u8>>)> = Vec::new();
    for e in &encoded {
        if let Ok(b) = std::fs::read(e["path"].as_str().unwrap_or("")) {
            sources.push((e["id"].as_str().unwrap_or("").to_string(), Arc::new(b)));
        }
    }
    let mut jobs = Vec::new();
    for (si, (id, data)) in sources.iter().enumerate() {
        let len = data.len();
        let mut cuts: Vec<usize> = vec![0, 1, 3, 4, 8, 12, 16, 20, 24, 32, 44, 48, 64, 100];
        for k in 1..16 {
            cuts.push(len * k / 16);
        }
        cuts.push(len.saturating_sub(1));
        cuts.sort_unstable();
        cuts.dedup();
        cuts.retain(|&c| c < len);
        for c in cuts {
            jobs.push(Job { source: Some(si), label: id.clone(), mode: "auto".into(), mutation: Mutation::Truncate(c) });
        }
        let base = (si as u64 + 1) * 1_000_003;
        for k in 0..24u64 {
            jobs.push(Job { source: Some(si), label: id.clone(), mode: "auto".into(), mutation: Mutation::BitFlip(base + k) });
        }
        for k in 0..16u64 {
            jobs.push(Job { source: Some(si), label: id.clone(), mode: "auto".into(), mutation: Mutation::HeaderBitFlip(base + 100 + k) });
        }
        for k in 0..8u64 {
            jobs.push(Job { source: Some(si), label: id.clone(), mode: "auto".into(), mutation: Mutation::Burst(base + 200 + k) });
        }
    }
    let sizes = [0usize, 1, 4, 16, 44, 48, 64, 128, 512, 4096, 65536];
    for (k, size) in sizes.iter().cycle().take(55).enumerate() {
        let seed = 7_000_000 + k as u64;
        for mode in ["woff1", "woff2"] {
            jobs.push(Job { source: None, label: "garbage".into(), mode: mode.into(), mutation: Mutation::Garbage { seed, size: *size, magic: None } });
        }
        jobs.push(Job { source: None, label: "garbage".into(), mode: "auto".into(), mutation: Mutation::Garbage { seed, size: *size, magic: Some(*b"wOF2") } });
        jobs.push(Job { source: None, label: "garbage".into(), mode: "auto".into(), mutation: Mutation::Garbage { seed, size: *size, magic: Some(*b"wOFF") } });
    }
    let started = Instant::now();
    let results = parallel(&jobs, |j, w| {
        let data = match j.source {
            Some(si) => j.mutation.apply(&sources[si].1),
            None => j.mutation.apply(&[]),
        };
        let p = workdir.join(format!("mut_{w}.bin"));
        if std::fs::write(&p, &data).is_err() {
            return ("io_error".to_string(), 0.0, data.len());
        }
        let (s, ms) = run_child(&exe, &j.mode, &p, "-", Duration::from_secs(20));
        (s, ms, data.len())
    });
    let elapsed = started.elapsed().as_secs_f64();
    let mut by_cat: BTreeMap<String, BTreeMap<String, u64>> = BTreeMap::new();
    let (mut strict_pass, mut safety_fail, mut total) = (0u64, 0u64, 0u64);
    let mut failures = Vec::new();
    let mut max_ms = 0f64;
    for (j, (status, ms, len)) in jobs.iter().zip(results.iter()) {
        total += 1;
        if *ms > max_ms {
            max_ms = *ms;
        }
        let category = j.mutation.category();
        *by_cat.entry(category.to_string()).or_default().entry(status.clone()).or_default() += 1;
        let unsafe_outcome = status == "panic" || status == "hang" || status.starts_with("crash") || status.starts_with("exit_");
        if status == "err" {
            strict_pass += 1;
        }
        if unsafe_outcome {
            safety_fail += 1;
        }
        if status != "err" && failures.len() < MAX_FAILURES {
            failures.push(json!({"source": j.label, "category": category, "mode": j.mode, "mutation": j.mutation.describe(), "input_len": len, "status": status, "ms": ms}));
        }
    }
    let result = json!({
        "test": "woff_robustness",
        "wuff_version": "0.2.10",
        "pass": strict_pass,
        "fail": total - strict_pass,
        "total": total,
        "pass_rate": if total > 0 { strict_pass as f64 / total as f64 } else { 0.0 },
        "pass_criterion": "every corrupted input returns Err (strict). Safety criterion: no panic, abort, signal or hang (>20 s), counted in safety_failures. Each input is decoded in a separate child process so aborts and hangs are observable.",
        "safety_failures": safety_fail,
        "safety_pass_rate": if total > 0 { (total - safety_fail) as f64 / total as f64 } else { 0.0 },
        "notes": [
            "A bit flip or byte burst inside compressed table data can legitimately produce a decodable font, since WOFF2 does not require per-table checksums to be verified; those cases appear as status 'ok' in by_category.",
            "Status codes: ok = Ok(_), err = Err(_), panic = caught panic, crash_signal_N = killed by signal N (e.g. abort/OOM under the step's ulimit), hang = exceeded 20 s and was killed."
        ],
        "by_category": by_cat,
        "max_decode_ms": max_ms,
        "elapsed_s": elapsed,
        "first_failures": failures,
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&result).unwrap()).expect("write");
    println!("woff robustness: strict {strict_pass}/{total}, safety failures {safety_fail}");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("decode-one") if args.len() == 5 => decode_one(&args[2..]),
        Some("roundtrip") if args.len() == 5 => roundtrip(&args[2..]),
        Some("robust") if args.len() == 5 => robust(&args[2..]),
        _ => {
            eprintln!("usage: woff decode-one <auto|woff1|woff2> <in> <out|->\n       woff roundtrip <manifest.json> <outdir> <out.json>\n       woff robust <manifest.json> <workdir> <out.json>");
            std::process::exit(2);
        }
    }
}
