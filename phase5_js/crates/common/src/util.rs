use std::collections::HashMap;

/// Minimal `--key value` / `--flag` argument parser (no external crates).
pub struct Args {
    pub positional: Vec<String>,
    named: HashMap<String, String>,
}

impl Args {
    pub fn parse(raw: &[String]) -> Args {
        let mut positional = Vec::new();
        let mut named = HashMap::new();
        let mut i = 0;
        while i < raw.len() {
            let a = &raw[i];
            if let Some(k) = a.strip_prefix("--") {
                if i + 1 < raw.len() && !raw[i + 1].starts_with("--") {
                    named.insert(k.to_string(), raw[i + 1].clone());
                    i += 2;
                } else {
                    named.insert(k.to_string(), String::from("true"));
                    i += 1;
                }
            } else {
                positional.push(a.clone());
                i += 1;
            }
        }
        Args { positional, named }
    }

    pub fn get(&self, k: &str) -> Option<String> {
        self.named.get(k).cloned()
    }

    pub fn req(&self, k: &str) -> String {
        match self.named.get(k) {
            Some(v) => v.clone(),
            None => {
                eprintln!("missing --{k}");
                std::process::exit(2);
            }
        }
    }

    pub fn num(&self, k: &str, default: u64) -> u64 {
        self.named
            .get(k)
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(default)
    }

    pub fn flag(&self, k: &str) -> bool {
        self.named.get(k).map(|v| v == "true").unwrap_or(false)
    }
}

/// (VmRSS, VmHWM) of this process in KiB, read from /proc/self/status (Linux only).
pub fn rss_kb() -> (Option<u64>, Option<u64>) {
    let text = match std::fs::read_to_string("/proc/self/status") {
        Ok(t) => t,
        Err(_) => return (None, None),
    };
    let field = |name: &str| -> Option<u64> {
        text.lines()
            .find(|l| l.starts_with(name))
            .and_then(|l| l.split_whitespace().nth(1))
            .and_then(|v| v.parse::<u64>().ok())
    };
    (field("VmRSS:"), field("VmHWM:"))
}

/// Maps an engine error message to the typed error names used in the report.
pub fn classify(message: &str) -> &'static str {
    let m = message;
    if m.contains("P5TimerBudget") {
        "TimerBudget"
    } else if m.contains("P5CanvasBudget") {
        "CanvasBudget"
    } else if m.starts_with("JobBudget") {
        "JobBudget"
    } else if m.starts_with("Timeout") || m.contains("interrupted") {
        "Timeout"
    } else if m.contains("maximum number of iteration loops") {
        // boa_engine RuntimeLimitError::LoopIteration (iteration cap, not a clock)
        "Timeout"
    } else if m.contains("out of memory") || m.starts_with("OutOfMemory") || m.contains("memory allocation") {
        "OutOfMemory"
    } else if m.contains("Maximum call stack size exceeded")
        || m.contains("stack overflow")
        || m.contains("Maximum call stack")
        || m.contains("maximum number of recursive calls")
        || m.contains("maximum stack size")
    {
        "StackOverflow"
    } else if m.starts_with("NeverSettled") {
        "NeverSettled"
    } else if let Some(i) = m.find(':') {
        let head = m[..i].trim();
        match head {
            "TypeError" => "TypeError",
            "RangeError" => "RangeError",
            "ReferenceError" => "ReferenceError",
            "SyntaxError" => "SyntaxError",
            "InternalError" => "InternalError",
            "EvalError" => "EvalError",
            "URIError" => "URIError",
            "Error" => "Error",
            _ => "JsError",
        }
    } else {
        "JsError"
    }
}

/// JSON-escapes a string for embedding in generated JavaScript source.
pub fn js_string_literal(s: &str) -> String {
    serde_json::Value::String(s.to_string()).to_string()
}
