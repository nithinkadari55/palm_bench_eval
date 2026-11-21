use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::str::FromStr;

const HARFRUST_VERSION: &str = "0.16.1";
const MAX_FAILURES: usize = 20;

#[derive(Default)]
struct Stats {
    total: u64,
    exact: u64,
    oracle_error: u64,
    harfrust_error: u64,
    panics: u64,
    kinds: BTreeMap<String, u64>,
}

impl Stats {
    fn to_json(&self) -> Value {
        json!({
            "total": self.total,
            "exact": self.exact,
            "exact_rate": if self.total > 0 { self.exact as f64 / self.total as f64 } else { 0.0 },
            "oracle_errors": self.oracle_error,
            "harfrust_errors": self.harfrust_error,
            "panics": self.panics,
            "mismatch_kinds": self.kinds,
        })
    }
}

type Glyph = [i64; 6];

fn shape(font: &harfrust::Font, text: &str, script: &str, lang: &str, dir: &str) -> Result<Vec<Glyph>, String> {
    let sf = harfrust::ShaperFont::new(font);
    let mut buf = harfrust::Buffer::new();
    buf.push_str(text);
    buf.set_direction(harfrust::Direction::from_str(dir).map_err(|e| e.to_string())?);
    buf.set_script(harfrust::Script::from_str(script).ok());
    buf.set_language(harfrust::Language::from_str(lang).ok());
    harfrust::shape(&sf, &mut buf, harfrust::ShapeOptions::new()).map_err(|e| format!("{e:?}"))?;
    let infos = buf.glyph_infos();
    let positions = buf.glyph_positions();
    Ok(infos
        .iter()
        .zip(positions.iter())
        .map(|(i, p)| {
            [
                i.glyph_id as i64,
                i.cluster as i64,
                p.x_advance as i64,
                p.y_advance as i64,
                p.x_offset as i64,
                p.y_offset as i64,
            ]
        })
        .collect())
}

fn compare(hb: &[Glyph], hr: &[Glyph]) -> (Vec<&'static str>, Option<usize>) {
    let mut kinds = Vec::new();
    let mut first = None;
    if hb.len() != hr.len() {
        kinds.push("glyph_count");
    }
    let (mut g, mut c, mut a, mut o) = (false, false, false, false);
    for (i, (x, y)) in hb.iter().zip(hr.iter()).enumerate() {
        if x != y && first.is_none() {
            first = Some(i);
        }
        g |= x[0] != y[0];
        c |= x[1] != y[1];
        a |= x[2] != y[2] || x[3] != y[3];
        o |= x[4] != y[4] || x[5] != y[5];
    }
    if first.is_none() && hb.len() != hr.len() {
        first = Some(hb.len().min(hr.len()));
    }
    if g {
        kinds.push("glyph_id");
    }
    if c {
        kinds.push("cluster");
    }
    if a {
        kinds.push("advance");
    }
    if o {
        kinds.push("offset");
    }
    (kinds, first)
}

fn window(v: &[Glyph], at: usize) -> Vec<Glyph> {
    let s = at.saturating_sub(3);
    let e = (at + 4).min(v.len());
    if s >= e {
        return Vec::new();
    }
    v[s..e].to_vec()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: shaping <oracle.json> <results.json>");
        std::process::exit(2);
    }
    std::panic::set_hook(Box::new(|_| {}));
    let oracle: Value = serde_json::from_str(&std::fs::read_to_string(&args[1]).expect("read oracle")).expect("parse oracle");
    let empty = Vec::new();
    let cases = oracle["cases"].as_array().unwrap_or(&empty);
    let mut fonts: HashMap<(String, u32), Option<harfrust::Font>> = HashMap::new();
    let mut overall = Stats::default();
    let mut per_script: BTreeMap<String, Stats> = BTreeMap::new();
    let mut per_font: BTreeMap<String, Stats> = BTreeMap::new();
    let mut failures = Vec::new();
    let started = std::time::Instant::now();

    for case in cases {
        let s = |k: &str| case[k].as_str().unwrap_or("").to_string();
        let (group, font_path, text, script, lang, dir) = (s("group"), s("font"), s("text"), s("script"), s("lang"), s("direction"));
        let idx = case["face_index"].as_u64().unwrap_or(0) as u32;
        let font_label = format!(
            "{}#{}",
            std::path::Path::new(&font_path).file_name().map(|f| f.to_string_lossy().to_string()).unwrap_or_default(),
            idx
        );
        let mut kinds_out: Vec<String> = Vec::new();
        let mut detail = Value::Null;
        let outcome: &str;

        let hb: Option<Vec<Glyph>> = case["glyphs"].as_array().map(|arr| {
            arr.iter()
                .map(|g| {
                    let a = g.as_array().cloned().unwrap_or_default();
                    let mut r = [0i64; 6];
                    for (i, v) in a.iter().take(6).enumerate() {
                        r[i] = v.as_i64().unwrap_or(0);
                    }
                    r
                })
                .collect()
        });

        if let Some(hb) = hb {
            let font = fonts
                .entry((font_path.clone(), idx))
                .or_insert_with(|| std::fs::read(&font_path).ok().and_then(|b| harfrust::Font::new(b, idx)));
            match font {
                None => {
                    outcome = "harfrust_error";
                    kinds_out.push("font_load".into());
                }
                Some(font) => {
                    let r = catch_unwind(AssertUnwindSafe(|| shape(font, &text, &script, &lang, &dir)));
                    match r {
                        Err(_) => {
                            outcome = "panic";
                            kinds_out.push("panic".into());
                        }
                        Ok(Err(e)) => {
                            outcome = "harfrust_error";
                            kinds_out.push(format!("shape_error:{e}"));
                        }
                        Ok(Ok(hr)) => {
                            let (kinds, first) = compare(&hb, &hr);
                            if kinds.is_empty() {
                                outcome = "exact";
                            } else {
                                outcome = "mismatch";
                                kinds_out.extend(kinds.iter().map(|k| k.to_string()));
                                let at = first.unwrap_or(0);
                                detail = json!({
                                    "first_diff_index": at,
                                    "hb_len": hb.len(),
                                    "harfrust_len": hr.len(),
                                    "hb_window": window(&hb, at),
                                    "harfrust_window": window(&hr, at),
                                    "glyph_fields": ["gid", "cluster", "x_advance", "y_advance", "x_offset", "y_offset"],
                                });
                            }
                        }
                    }
                }
            }
        } else {
            outcome = "oracle_error";
            kinds_out.push(format!("oracle_error:{}", case["error"].as_str().unwrap_or("")));
        }

        for st in [&mut overall, per_script.entry(group.clone()).or_default(), per_font.entry(format!("{group}/{font_label}")).or_default()] {
            st.total += 1;
            match outcome {
                "exact" => st.exact += 1,
                "oracle_error" => st.oracle_error += 1,
                "harfrust_error" => st.harfrust_error += 1,
                "panic" => st.panics += 1,
                _ => {}
            }
            if outcome == "mismatch" {
                for k in &kinds_out {
                    *st.kinds.entry(k.clone()).or_default() += 1;
                }
            }
        }
        if outcome != "exact" && failures.len() < MAX_FAILURES {
            failures.push(json!({
                "id": case["id"],
                "group": group,
                "lang": lang,
                "script": script,
                "direction": dir,
                "font": font_label,
                "text": text.chars().take(300).collect::<String>(),
                "outcome": outcome,
                "kinds": kinds_out,
                "detail": detail,
            }));
        }
    }

    let result = json!({
        "test": "shaping",
        "oracle": oracle["oracle"],
        "hb_version": oracle["hb_version"],
        "harfrust_version": HARFRUST_VERSION,
        "pass": overall.exact,
        "fail": overall.total - overall.exact,
        "total": overall.total,
        "pass_rate": if overall.total > 0 { overall.exact as f64 / overall.total as f64 } else { 0.0 },
        "pass_criterion": "glyph ids, clusters (UTF-8 byte offsets), x/y advances and x/y offsets identical to hb-shape for every glyph",
        "summary": overall.to_json(),
        "per_script": per_script.iter().map(|(k, v)| (k.clone(), v.to_json())).collect::<serde_json::Map<_, _>>(),
        "per_font": per_font.iter().map(|(k, v)| (k.clone(), v.to_json())).collect::<serde_json::Map<_, _>>(),
        "missing_fonts": oracle["missing_fonts"],
        "elapsed_s": started.elapsed().as_secs_f64(),
        "first_failures": failures,
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&result).unwrap()).expect("write results");
    println!(
        "shaping[{}]: {}/{} exact",
        oracle["oracle"].as_str().unwrap_or("?"),
        overall.exact,
        overall.total
    );
}
