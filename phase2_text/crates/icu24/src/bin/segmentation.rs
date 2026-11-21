use icu_properties::props::{GeneralCategory, LineBreak};
use icu_properties::CodePointMapData;
use icu_segmenter::{GraphemeClusterSegmenter, LineSegmenter, WordSegmenter};
use serde_json::{json, Value};
use std::path::Path;

const MAX_FAILURES: usize = 20;

struct Case {
    line_no: usize,
    source: String,
    cps: Vec<u32>,
    breaks: Vec<usize>,
}

fn parse(path: &Path) -> Result<Vec<Case>, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut out = Vec::new();
    for (i, raw) in text.lines().enumerate() {
        let data = raw.split('#').next().unwrap_or("").trim();
        if data.is_empty() {
            continue;
        }
        let mut cps = Vec::new();
        let mut breaks = Vec::new();
        for (n, tok) in data.split_whitespace().enumerate() {
            if n % 2 == 1 {
                cps.push(u32::from_str_radix(tok, 16).map_err(|e| format!("line {}: {e}", i + 1))?);
            } else if tok == "\u{00f7}" {
                breaks.push(cps.len());
            } else if tok != "\u{00d7}" {
                return Err(format!("line {}: unexpected token {tok}", i + 1));
            }
        }
        out.push(Case { line_no: i + 1, source: data.to_string(), cps, breaks });
    }
    Ok(out)
}

fn lb1_sa_replace(c: char) -> char {
    let lb = CodePointMapData::<LineBreak>::new().get(c);
    if lb != LineBreak::ComplexContext {
        return c;
    }
    let gc = CodePointMapData::<GeneralCategory>::new().get(c);
    let mark = gc == GeneralCategory::NonspacingMark || gc == GeneralCategory::SpacingMark;
    match (mark, c.len_utf8()) {
        (true, 2) => '\u{0300}',
        (true, 3) => '\u{081C}',
        (true, 4) => '\u{101FD}',
        (false, 2) => '\u{00C0}',
        (false, 3) => '\u{0800}',
        (false, 4) => '\u{10000}',
        _ => c,
    }
}

fn run_variant(
    name: &str,
    file: &Path,
    constructor: &str,
    sa_replace: bool,
    seg: &dyn Fn(&str) -> Vec<usize>,
) -> Value {
    let cases = match parse(file) {
        Ok(c) => c,
        Err(e) => {
            return json!({"name": name, "file": file.display().to_string(), "error": e, "pass": 0, "fail": 0, "total": 0});
        }
    };
    let (mut pass, mut fail, mut skipped) = (0u64, 0u64, 0u64);
    let mut failures = Vec::new();
    for c in &cases {
        let chars: Option<Vec<char>> = c.cps.iter().map(|&u| char::from_u32(u)).collect();
        let Some(chars) = chars else {
            skipped += 1;
            continue;
        };
        let chars: Vec<char> = if sa_replace { chars.into_iter().map(lb1_sa_replace).collect() } else { chars };
        let s: String = chars.iter().collect();
        let mut offsets = Vec::with_capacity(chars.len() + 1);
        let mut acc = 0usize;
        offsets.push(0);
        for ch in &chars {
            acc += ch.len_utf8();
            offsets.push(acc);
        }
        let mut expected: Vec<usize> = c.breaks.iter().map(|&i| offsets[i]).collect();
        if expected.first() != Some(&0) {
            expected.insert(0, 0);
        }
        let actual = seg(&s);
        if actual == expected {
            pass += 1;
        } else {
            fail += 1;
            if failures.len() < MAX_FAILURES {
                let to_cp = |v: &Vec<usize>| -> Vec<usize> { v.iter().filter_map(|b| offsets.iter().position(|o| o == b)).collect() };
                failures.push(json!({
                    "line": c.line_no,
                    "input": c.source,
                    "expected_breaks_cp_index": to_cp(&expected),
                    "actual_breaks_cp_index": to_cp(&actual),
                }));
            }
        }
    }
    let total = pass + fail;
    json!({
        "name": name,
        "file": file.display().to_string(),
        "constructor": constructor,
        "lb1_sa_replacement": sa_replace,
        "pass": pass,
        "fail": fail,
        "skipped_invalid_scalar": skipped,
        "total": total,
        "pass_rate": if total > 0 { pass as f64 / total as f64 } else { 0.0 },
        "first_failures": failures,
    })
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: segmentation <ucd_dir> <results.json>");
        std::process::exit(2);
    }
    let ucd = Path::new(&args[1]);
    let f = |ver: &str, name: &str| ucd.join(ver).join(name);

    let line_stable = LineSegmenter::new_for_non_complex_scripts(Default::default());
    let line_17 = LineSegmenter::new_17_for_non_complex_scripts(Default::default());
    let line_neo = LineSegmenter::new_neo_for_non_complex_scripts(Default::default());
    let word_stable = WordSegmenter::new_for_non_complex_scripts(Default::default());
    let word_neo = WordSegmenter::new_neo_for_non_complex_scripts(Default::default());
    let gr_stable = GraphemeClusterSegmenter::new();
    let gr_neo = GraphemeClusterSegmenter::new_neo();

    let ls = |s: &str| line_stable.segment_str(s).collect::<Vec<usize>>();
    let l17 = |s: &str| line_17.segment_str(s).collect::<Vec<usize>>();
    let lneo = |s: &str| line_neo.segment_str(s).collect::<Vec<usize>>();
    let ws = |s: &str| word_stable.segment_str(s).collect::<Vec<usize>>();
    let wneo = |s: &str| word_neo.segment_str(s).collect::<Vec<usize>>();
    let gs = |s: &str| gr_stable.segment_str(s).collect::<Vec<usize>>();
    let gneo = |s: &str| gr_neo.segment_str(s).collect::<Vec<usize>>();

    let variants = vec![
        ("line", run_variant("line_stable_vs_15.1_lb1sa", &f("15.1.0", "LineBreakTest.txt"), "LineSegmenter::new_for_non_complex_scripts", true, &ls)),
        ("line", run_variant("line_stable_vs_15.1_raw", &f("15.1.0", "LineBreakTest.txt"), "LineSegmenter::new_for_non_complex_scripts", false, &ls)),
        ("line", run_variant("line_17_vs_17.0_lb1sa", &f("17.0.0", "LineBreakTest.txt"), "LineSegmenter::new_17_for_non_complex_scripts (unstable)", true, &l17)),
        ("line", run_variant("line_17_vs_17.0_raw", &f("17.0.0", "LineBreakTest.txt"), "LineSegmenter::new_17_for_non_complex_scripts (unstable)", false, &l17)),
        ("line", run_variant("line_neo_vs_18.0", &f("18.0.0", "LineBreakTest.txt"), "LineSegmenter::new_neo_for_non_complex_scripts (unstable)", false, &lneo)),
        ("line", run_variant("line_stable_vs_18.0", &f("18.0.0", "LineBreakTest.txt"), "LineSegmenter::new_for_non_complex_scripts", false, &ls)),
        ("word", run_variant("word_stable_vs_17.0", &f("17.0.0", "WordBreakTest.txt"), "WordSegmenter::new_for_non_complex_scripts", false, &ws)),
        ("word", run_variant("word_neo_vs_18.0", &f("18.0.0", "WordBreakTest.txt"), "WordSegmenter::new_neo_for_non_complex_scripts (unstable)", false, &wneo)),
        ("word", run_variant("word_stable_vs_18.0", &f("18.0.0", "WordBreakTest.txt"), "WordSegmenter::new_for_non_complex_scripts", false, &ws)),
        ("grapheme", run_variant("grapheme_stable_vs_17.0", &f("17.0.0", "GraphemeBreakTest.txt"), "GraphemeClusterSegmenter::new", false, &gs)),
        ("grapheme", run_variant("grapheme_neo_vs_18.0", &f("18.0.0", "GraphemeBreakTest.txt"), "GraphemeClusterSegmenter::new_neo (unstable)", false, &gneo)),
        ("grapheme", run_variant("grapheme_stable_vs_18.0", &f("18.0.0", "GraphemeBreakTest.txt"), "GraphemeClusterSegmenter::new", false, &gs)),
    ];

    let mut pass = 0u64;
    let mut fail = 0u64;
    let mut first_failures = Vec::new();
    let mut by_kind = serde_json::Map::new();
    for (kind, v) in &variants {
        pass += v["pass"].as_u64().unwrap_or(0);
        fail += v["fail"].as_u64().unwrap_or(0);
        if let Some(arr) = v["first_failures"].as_array() {
            for x in arr {
                if first_failures.len() < MAX_FAILURES {
                    let mut x = x.clone();
                    x["variant"] = v["name"].clone();
                    first_failures.push(x);
                }
            }
        }
        by_kind
            .entry(kind.to_string())
            .or_insert_with(|| json!([]))
            .as_array_mut()
            .unwrap()
            .push(json!({"name": v["name"], "pass": v["pass"], "fail": v["fail"], "pass_rate": v["pass_rate"]}));
    }
    let total = pass + fail;
    let result = json!({
        "test": "segmentation",
        "icu_segmenter_version": "2.4.0",
        "icu_data_unicode_version": "18.0.0",
        "pass": pass,
        "fail": fail,
        "total": total,
        "pass_rate": if total > 0 { pass as f64 / total as f64 } else { 0.0 },
        "pass_criterion": "the full list of boundaries (byte offsets, including 0 and end) equals the ÷ positions of the official test line; ICU4X always reports a boundary at 0 for line breaking (issue #3283), so 0 is added to the expected list for LineBreakTest",
        "notes": [
            "icu_segmenter 2.4.0 documents: stable LineSegmenter implements UAX #14 rules of Unicode 15.1.0; *_17_* constructors implement 17.0.0; *_neo_* constructors implement 18.0.0 (unstable feature). Property data is Unicode 18.0.0 for all constructors.",
            "Stable word and grapheme segmenters correspond to Unicode 17.0.0 rules (upstream spec_test.rs pairs them with the *_17 test files); *_neo constructors correspond to 18.0.0.",
            "lb1sa variants replace Line_Break=SA characters per LB1 before segmentation, exactly as upstream spec_test.rs does, because the rule-based (non-complex) line segmenter does not implement LB1 for SA; raw variants do not.",
            "ICU4X tailorings that legitimately differ from default UAX rules (CSS line-break strictness, word-break, ja/zh content locale, dictionary/LSTM breaking for Thai/Lao/Khmer/Myanmar/CJK) are not exercised: default options with the *_for_non_complex_scripts constructors are used."
        ],
        "by_kind": by_kind,
        "variants": variants.iter().map(|(_, v)| v.clone()).collect::<Vec<_>>(),
        "first_failures": first_failures,
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&result).unwrap()).expect("write results");
    for (_, v) in &variants {
        println!("{}: {}/{}", v["name"].as_str().unwrap_or(""), v["pass"], v["total"]);
    }
}
