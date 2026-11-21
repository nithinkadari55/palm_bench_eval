use serde_json::{json, Value};

const MAX_EXAMPLES: usize = 20;

fn positions(word: &str, lang: hypher::Lang, left: usize, right: usize) -> Vec<u64> {
    let mut out = Vec::new();
    let mut acc = 0u64;
    let syllables: Vec<&str> = hypher::hyphenate_bounded(word, lang, left, right).collect();
    for (i, s) in syllables.iter().enumerate() {
        if i + 1 == syllables.len() {
            break;
        }
        acc += s.chars().count() as u64;
        out.push(acc);
    }
    out
}

fn as_positions(v: &Value) -> Vec<u64> {
    v.as_array().map(|a| a.iter().filter_map(|x| x.as_u64()).collect()).unwrap_or_default()
}

fn mark(word: &str, pos: &[u64]) -> String {
    let mut s = String::new();
    for (i, c) in word.chars().enumerate() {
        if pos.contains(&(i as u64)) {
            s.push('-');
        }
        s.push(c);
    }
    s
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: hyphenation <hyph_ref.json> <results.json>");
        std::process::exit(2);
    }
    let reference: Value = serde_json::from_str(&std::fs::read_to_string(&args[1]).expect("read ref")).expect("parse ref");
    let mut per_lang = Vec::new();
    let (mut pass_a, mut total_a, mut pass_b) = (0u64, 0u64, 0u64);
    let mut first_failures = Vec::new();
    for l in reference["languages"].as_array().cloned().unwrap_or_default() {
        let iso = l["iso"].as_str().unwrap_or("").to_string();
        let bytes = iso.as_bytes();
        let lang = if bytes.len() == 2 { hypher::Lang::from_iso([bytes[0], bytes[1]]) } else { None };
        let Some(lang) = lang else {
            per_lang.push(json!({"iso": iso, "error": "hypher has no such language"}));
            continue;
        };
        let bounds = as_positions(&l["bounds"]);
        let (left, right) = (bounds.first().copied().unwrap_or(2) as usize, bounds.get(1).copied().unwrap_or(2) as usize);
        let crate_bounds = lang.bounds();
        let words = l["words"].as_array().cloned().unwrap_or_default();
        let ref_a = l["ref_same_patterns"].as_array().cloned().unwrap_or_default();
        let ref_b = l["ref_pyphen_dictionary"].as_array().cloned().unwrap_or_default();
        let (mut a_ok, mut b_ok) = (0u64, 0u64);
        let (mut a_ex, mut b_ex) = (Vec::new(), Vec::new());
        let (mut hy_points, mut a_points, mut b_points, mut b_common) = (0u64, 0u64, 0u64, 0u64);
        for (i, w) in words.iter().enumerate() {
            let w = w.as_str().unwrap_or("");
            let hy = positions(w, lang, left, right);
            let a = as_positions(&ref_a[i]);
            let b = as_positions(&ref_b[i]);
            hy_points += hy.len() as u64;
            a_points += a.len() as u64;
            b_points += b.len() as u64;
            b_common += hy.iter().filter(|p| b.contains(p)).count() as u64;
            if hy == a {
                a_ok += 1;
            } else if a_ex.len() < MAX_EXAMPLES {
                a_ex.push(json!({"word": w, "hypher": mark(w, &hy), "reference": mark(w, &a)}));
            }
            if hy == b {
                b_ok += 1;
            } else if b_ex.len() < MAX_EXAMPLES {
                b_ex.push(json!({"word": w, "hypher": mark(w, &hy), "reference": mark(w, &b)}));
            }
        }
        let mut exc_total = 0u64;
        let mut exc_agree = 0u64;
        let mut exc_ex = Vec::new();
        if let Some(m) = l["tex_exceptions_in_wordlist"].as_object() {
            for (w, p) in m {
                exc_total += 1;
                let hy = positions(w, lang, left, right);
                let e = as_positions(p);
                if hy == e {
                    exc_agree += 1;
                } else if exc_ex.len() < MAX_EXAMPLES {
                    exc_ex.push(json!({"word": w, "hypher": mark(w, &hy), "tex_exception": mark(w, &e)}));
                }
            }
        }
        let n = words.len() as u64;
        total_a += n;
        pass_a += a_ok;
        pass_b += b_ok;
        for ex in a_ex.iter().take(3) {
            if first_failures.len() < MAX_EXAMPLES {
                let mut ex = ex.clone();
                ex["iso"] = json!(iso);
                ex["reference_kind"] = json!("pyphen engine + hypher's own TeX patterns");
                first_failures.push(ex);
            }
        }
        let r = |k: u64| if n > 0 { k as f64 / n as f64 } else { 0.0 };
        per_lang.push(json!({
            "iso": iso,
            "pattern_file": l["pattern_file"],
            "words": n,
            "wordlist_source": l["wordlist_source"],
            "bounds_used": [left, right],
            "crate_default_bounds": [crate_bounds.0, crate_bounds.1],
            "bounds_match_crate": crate_bounds == (left, right),
            "same_patterns": {"agree": a_ok, "rate": r(a_ok), "mismatch_examples": a_ex},
            "pyphen_dictionary": {
                "dictionary": l["pyphen_dictionary"],
                "agree": b_ok,
                "rate": r(b_ok),
                "hypher_points": hy_points,
                "reference_points": b_points,
                "common_points": b_common,
                "precision": if hy_points > 0 { b_common as f64 / hy_points as f64 } else { 0.0 },
                "recall": if b_points > 0 { b_common as f64 / b_points as f64 } else { 0.0 },
                "mismatch_examples": b_ex
            },
            "same_patterns_points": {"hypher": hy_points, "reference": a_points},
            "tex_exceptions_ignored_by_hypher": {"words_in_list": exc_total, "hypher_agrees": exc_agree, "examples": exc_ex},
        }));
        println!("{iso}: same-patterns {a_ok}/{n}, pyphen-dict {b_ok}/{n}");
    }
    for l in &per_lang {
        if let Some(arr) = l["pyphen_dictionary"]["mismatch_examples"].as_array() {
            for ex in arr.iter().take(1) {
                if first_failures.len() < MAX_EXAMPLES {
                    let mut ex = ex.clone();
                    ex["iso"] = l["iso"].clone();
                    ex["reference_kind"] = json!("pyphen bundled LibreOffice dictionary");
                    first_failures.push(ex);
                }
            }
        }
    }
    let result = json!({
        "test": "hyphenation",
        "hypher_version": "0.1.8",
        "pyphen_version": reference["pyphen_version"],
        "pass": pass_a,
        "fail": total_a - pass_a,
        "total": total_a,
        "pass_rate": if total_a > 0 { pass_a as f64 / total_a as f64 } else { 0.0 },
        "pass_criterion": "a word passes when hypher's hyphenation points equal those of pyphen's independent Liang implementation loaded with the identical TeX patterns (hypher/patterns/*.tex at the crate commit) and identical left/right minimums",
        "agreement_with_pyphen_dictionaries": if total_a > 0 { pass_b as f64 / total_a as f64 } else { 0.0 },
        "notes": [
            "Word lists: lower-case alphabetic stems (length >= 5) from the Ubuntu hunspell dictionaries, deterministically sampled to at most 10000 per language.",
            "pyphen_dictionary compares against pyphen's bundled LibreOffice hyph_*.dic files, which derive from the TeX patterns but are different revisions with extra patterns; disagreement there measures pattern-set differences, not engine bugs.",
            "hypher ignores \\hyphenation{} exception lists in the TeX files; tex_exceptions_ignored_by_hypher measures the impact on listed words."
        ],
        "languages": per_lang,
        "first_failures": first_failures,
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&result).unwrap()).expect("write results");
}
