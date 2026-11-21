use serde_json::{json, Value};
use std::io::{Read, Write};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

pub struct Raw {
    pub width: u32,
    pub height: u32,
    pub channels: u8,
    pub depth: u8,
    pub frames: Vec<Vec<u8>>,
}

impl Raw {
    pub fn still(width: u32, height: u32, channels: u8, depth: u8, data: Vec<u8>) -> Raw {
        Raw { width, height, channels, depth, frames: vec![data] }
    }

    pub fn from_u16(width: u32, height: u32, channels: u8, samples: &[u16]) -> Raw {
        let mut data = Vec::with_capacity(samples.len() * 2);
        for s in samples {
            data.extend_from_slice(&s.to_le_bytes());
        }
        Raw::still(width, height, channels, 16, data)
    }

    pub fn frame_len(&self) -> usize {
        self.width as usize * self.height as usize * self.channels as usize * (self.depth as usize / 8)
    }

    pub fn samples_u16(&self, frame: usize) -> Vec<u16> {
        let d = &self.frames[frame];
        if self.depth == 16 {
            d.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).collect()
        } else {
            d.iter().map(|&v| v as u16).collect()
        }
    }
}

pub fn write_raw(path: &Path, raw: &Raw) -> std::io::Result<()> {
    let expected = raw.frame_len();
    for f in &raw.frames {
        if f.len() != expected {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("frame has {} bytes, expected {}", f.len(), expected),
            ));
        }
    }
    let mut out = Vec::with_capacity(16 + expected * raw.frames.len());
    out.extend_from_slice(b"P3R1");
    out.extend_from_slice(&raw.width.to_le_bytes());
    out.extend_from_slice(&raw.height.to_le_bytes());
    out.push(raw.channels);
    out.push(raw.depth);
    out.extend_from_slice(&(raw.frames.len() as u16).to_le_bytes());
    for f in &raw.frames {
        out.extend_from_slice(f);
    }
    std::fs::write(path, out)
}

pub fn read_raw(path: &Path) -> std::io::Result<Raw> {
    let mut buf = Vec::new();
    std::fs::File::open(path)?.read_to_end(&mut buf)?;
    if buf.len() < 16 || &buf[0..4] != b"P3R1" {
        return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "not a P3R1 file"));
    }
    let width = u32::from_le_bytes([buf[4], buf[5], buf[6], buf[7]]);
    let height = u32::from_le_bytes([buf[8], buf[9], buf[10], buf[11]]);
    let channels = buf[12];
    let depth = buf[13];
    let nframes = u16::from_le_bytes([buf[14], buf[15]]) as usize;
    let mut raw = Raw { width, height, channels, depth, frames: Vec::new() };
    let fl = raw.frame_len();
    if buf.len() != 16 + fl * nframes {
        return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "P3R1 size mismatch"));
    }
    for i in 0..nframes {
        raw.frames.push(buf[16 + i * fl..16 + (i + 1) * fl].to_vec());
    }
    Ok(raw)
}

pub type ChildFn = fn(&str, &[String]) -> Result<Option<Raw>, String>;

/// Child protocol: `<exe> <subcmd> <input> <out|-> [extra...]`.
/// Exit 0 = Ok (raw written unless out is "-"), 1 = Err (message on stderr),
/// 3 = panic, 4 = cannot read input, 5 = cannot write output, 2 = usage.
pub fn child_main(sub: &str, args: &[String], f: ChildFn) -> ! {
    std::panic::set_hook(Box::new(|_| {}));
    if args.len() < 2 {
        eprintln!("usage: <subcmd> <input> <out|-> [extra...]");
        std::process::exit(2);
    }
    let out = args[1].clone();
    let sub_owned = sub.to_string();
    let args_owned: Vec<String> = args.to_vec();
    match catch_unwind(AssertUnwindSafe(|| f(&sub_owned, &args_owned))) {
        Ok(Ok(raw)) => {
            if let Some(raw) = raw {
                if out != "-" {
                    if let Err(e) = write_raw(Path::new(&out), &raw) {
                        eprintln!("write error: {e}");
                        std::process::exit(5);
                    }
                }
            }
            std::process::exit(0)
        }
        Ok(Err(msg)) => {
            let mut s = msg.replace('\n', " ");
            s.truncate(400);
            let _ = writeln!(std::io::stderr(), "{s}");
            std::process::exit(1)
        }
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

pub fn run_child(exe: &Path, args: &[String], timeout: Duration) -> (String, f64, String) {
    let start = Instant::now();
    let child = Command::new(exe)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn();
    let mut child = match child {
        Ok(c) => c,
        Err(e) => return (format!("spawn_error:{e}"), 0.0, String::new()),
    };
    loop {
        match child.try_wait() {
            Ok(Some(st)) => {
                let ms = start.elapsed().as_secs_f64() * 1000.0;
                let mut msg = String::new();
                if let Some(mut e) = child.stderr.take() {
                    let _ = e.read_to_string(&mut msg);
                }
                msg.truncate(400);
                let s = match st.code() {
                    Some(0) => "ok".to_string(),
                    Some(1) => "err".to_string(),
                    Some(3) => "panic".to_string(),
                    Some(c) => format!("exit_{c}"),
                    None => format!("crash_signal_{}", signal_of(&st).unwrap_or(-1)),
                };
                return (s, ms, msg.trim().to_string());
            }
            Ok(None) => {
                if start.elapsed() > timeout {
                    let _ = child.kill();
                    let _ = child.wait();
                    return ("hang".to_string(), start.elapsed().as_secs_f64() * 1000.0, String::new());
                }
                std::thread::sleep(Duration::from_millis(2));
            }
            Err(e) => return (format!("wait_error:{e}"), 0.0, String::new()),
        }
    }
}

/// `<exe> batch <subcmd> <manifest.json> <results.json> [timeout_ms] [jobs]`
///
/// The manifest is `{"cases": [{"id": str, "input": str, "out": str|null, "args": [str]}]}`.
/// Every case runs as `<exe> <subcmd> <input> <out|-> args...` in its own process.
pub fn batch_main(args: &[String]) -> i32 {
    if args.len() < 3 {
        eprintln!("usage: batch <subcmd> <manifest.json> <results.json> [timeout_ms] [jobs]");
        return 2;
    }
    let sub = args[0].clone();
    let manifest: Value = match std::fs::read(&args[1]).ok().and_then(|b| serde_json::from_slice(&b).ok()) {
        Some(v) => v,
        None => {
            eprintln!("cannot read manifest {}", args[1]);
            return 2;
        }
    };
    let timeout_ms: u64 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(30_000);
    let jobs: usize = args
        .get(4)
        .and_then(|s| s.parse().ok())
        .unwrap_or_else(|| std::thread::available_parallelism().map(|n| n.get()).unwrap_or(2));
    let exe: PathBuf = std::env::current_exe().expect("current_exe");
    let cases: Vec<Value> = manifest["cases"].as_array().cloned().unwrap_or_default();
    let n = cases.len();
    let results: Arc<Mutex<Vec<Value>>> = Arc::new(Mutex::new(vec![Value::Null; n]));
    let next = Arc::new(AtomicUsize::new(0));
    let cases = Arc::new(cases);
    let mut handles = Vec::new();
    for _ in 0..jobs.max(1) {
        let results = results.clone();
        let next = next.clone();
        let cases = cases.clone();
        let exe = exe.clone();
        let sub = sub.clone();
        handles.push(std::thread::spawn(move || loop {
            let i = next.fetch_add(1, Ordering::SeqCst);
            if i >= cases.len() {
                break;
            }
            let c = &cases[i];
            let input = c["input"].as_str().unwrap_or("").to_string();
            let out = c["out"].as_str().unwrap_or("-").to_string();
            let mut a = vec![sub.clone(), input, out];
            if let Some(extra) = c["args"].as_array() {
                for e in extra {
                    if let Some(s) = e.as_str() {
                        a.push(s.to_string());
                    }
                }
            }
            let (status, ms, msg) = run_child(&exe, &a, Duration::from_millis(timeout_ms));
            let r = json!({"id": c["id"].clone(), "status": status, "ms": ms, "message": msg});
            results.lock().unwrap()[i] = r;
        }));
    }
    for h in handles {
        let _ = h.join();
    }
    let results = results.lock().unwrap().clone();
    let doc = json!({"subcmd": sub, "timeout_ms": timeout_ms, "results": results});
    match std::fs::write(&args[2], serde_json::to_vec_pretty(&doc).unwrap()) {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("cannot write {}: {e}", args[2]);
            2
        }
    }
}

/// Shared `main` for the decoder binaries.
pub fn dispatch(f: ChildFn) -> ! {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: {} batch ... | <subcmd> <input> <out|-> [extra...]", args[0]);
        std::process::exit(2);
    }
    if args[1] == "batch" {
        std::process::exit(batch_main(&args[2..]));
    }
    child_main(&args[1].clone(), &args[2..], f)
}
