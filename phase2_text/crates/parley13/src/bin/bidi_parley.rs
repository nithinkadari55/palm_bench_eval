use parley_engine::{Analysis, AnalysisDataSources, AnalysisOptions, Analyzer, BaseDirection};
use serde_json::{json, Value};
use std::path::Path;
use unicode_bidi::{format_chars, BidiClass, BidiInfo, Level};

const MAX_FAILURES: usize = 20;

fn class_of_name(name: &str) -> Option<(char, BidiClass)> {
    use BidiClass::*;
    Some(match name {
        "AL" => ('\u{060B}', AL),
        "AN" => ('\u{0605}', AN),
        "B" => ('\u{000A}', B),
        "BN" => ('\u{2060}', BN),
        "CS" => ('\u{2044}', CS),
        "EN" => ('\u{06F9}', EN),
        "ES" => ('\u{208B}', ES),
        "ET" => ('\u{20CF}', ET),
        "FSI" => (format_chars::FSI, FSI),
        "L" => ('\u{02B8}', L),
        "LRE" => (format_chars::LRE, LRE),
        "LRI" => (format_chars::LRI, LRI),
        "LRO" => (format_chars::LRO, LRO),
        "NSM" => ('\u{0300}', NSM),
        "ON" => ('\u{03F6}', ON),
        "PDF" => (format_chars::PDF, PDF),
        "PDI" => (format_chars::PDI, PDI),
        "R" => ('\u{0590}', R),
        "RLE" => (format_chars::RLE, RLE),
        "RLI" => (format_chars::RLI, RLI),
        "RLO" => (format_chars::RLO, RLO),
        "S" => ('\u{001F}', S),
        "WS" => ('\u{200A}', WS),
        _ => return None,
    })
}

fn removed_by_x9(c: BidiClass) -> bool {
    matches!(c, BidiClass::BN | BidiClass::LRE | BidiClass::RLE | BidiClass::LRO | BidiClass::RLO | BidiClass::PDF)
}

struct Outcome {
    para_level: u8,
    levels: Vec<u8>,
}

fn run_parley(analyzer: &mut Analyzer, text: &str, classes: &[BidiClass], base: BaseDirection) -> Outcome {
    let opts = AnalysisOptions { base_direction: base, ..Default::default() };
    let mut analysis = Analysis::new();
    analyzer.analyze(text, &opts, &mut analysis, &AnalysisDataSources::default());
    let para = analysis.paragraph_level().to_u8();
    let n = text.chars().count();
    let mut levels: Vec<u8> = if analysis.bidi_levels().is_empty() {
        vec![para; n]
    } else {
        analysis.bidi_levels().iter().map(|l| l.to_u8()).collect()
    };
    // Harness-applied UAX #9 L1 clause 4 (trailing whitespace/isolates at end of line); Parley applies it during line layout.
    for i in (0..levels.len().min(classes.len())).rev() {
        let c = classes[i];
        if removed_by_x9(c) || matches!(c, BidiClass::WS | BidiClass::FSI | BidiClass::LRI | BidiClass::RLI | BidiClass::PDI) {
            levels[i] = para;
        } else {
            break;
        }
    }
    Outcome { para_level: para, levels }
}

#[derive(Default)]
struct Tally {
    total: u64,
    pass: u64,
    levels_ok: u64,
    reorder_ok: u64,
    para_ok: u64,
    failures: Vec<Value>,
}

fn check(t: &mut Tally, o: Outcome, exp_levels: &[Option<u8>], exp_order: &[usize], exp_para: Option<u8>, ctx: Value) {
    t.total += 1;
    let levels_ok = o.levels.len() == exp_levels.len() && o.levels.iter().zip(exp_levels).all(|(a, e)| e.map_or(true, |e| e == *a));
    let lv: Vec<Level> = o.levels.iter().map(|&l| Level::new(l.min(125)).unwrap_or(Level::ltr())).collect();
    let order: Vec<usize> = BidiInfo::reorder_visual(&lv).into_iter().filter(|&i| exp_levels.get(i).copied().flatten().is_some()).collect();
    let reorder_ok = order == exp_order;
    let para_ok = exp_para.map_or(true, |p| p == o.para_level);
    t.levels_ok += levels_ok as u64;
    t.reorder_ok += reorder_ok as u64;
    t.para_ok += para_ok as u64;
    if levels_ok && reorder_ok && para_ok {
        t.pass += 1;
    } else if t.failures.len() < MAX_FAILURES {
        t.failures.push(json!({
            "ctx": ctx,
            "expected_levels": exp_levels.iter().map(|l| l.map_or("x".to_string(), |v| v.to_string())).collect::<Vec<_>>(),
            "actual_levels": o.levels,
            "expected_order": exp_order,
            "actual_order": order,
            "expected_para_level": exp_para,
            "actual_para_level": o.para_level,
        }));
    }
}

fn parse_levels(s: &str) -> Vec<Option<u8>> {
    s.split_whitespace().map(|x| if x == "x" { None } else { x.parse().ok() }).collect()
}

fn parse_order(s: &str) -> Vec<usize> {
    s.split_whitespace().filter_map(|x| x.parse().ok()).collect()
}

fn bidi_test(an: &mut Analyzer, path: &Path) -> Result<Tally, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut t = Tally::default();
    let (mut lv, mut ord): (Vec<Option<u8>>, Vec<usize>) = (Vec::new(), Vec::new());
    for (i, line) in text.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(r) = line.strip_prefix("@Levels:") {
            lv = parse_levels(r);
            continue;
        }
        if let Some(r) = line.strip_prefix("@Reorder:") {
            ord = parse_order(r);
            continue;
        }
        if line.starts_with('@') {
            continue;
        }
        let mut parts = line.split(';');
        let names: Vec<&str> = parts.next().unwrap_or("").split_whitespace().collect();
        let bitset = u8::from_str_radix(parts.next().unwrap_or("0").trim(), 16).unwrap_or(0);
        let pairs: Option<Vec<(char, BidiClass)>> = names.iter().map(|n| class_of_name(n)).collect();
        let Some(pairs) = pairs else {
            return Err(format!("line {}: unknown class", i + 1));
        };
        let s: String = pairs.iter().map(|p| p.0).collect();
        let classes: Vec<BidiClass> = pairs.iter().map(|p| p.1).collect();
        for (bit, base, label) in [(1u8, BaseDirection::Auto, "auto"), (2, BaseDirection::Ltr, "LTR"), (4, BaseDirection::Rtl, "RTL")] {
            if bitset & bit == 0 {
                continue;
            }
            let o = run_parley(an, &s, &classes, base);
            check(&mut t, o, &lv, &ord, None, json!({"line": i + 1, "input": names.join(" "), "paragraph": label}));
        }
    }
    Ok(t)
}

fn bidi_char_test(an: &mut Analyzer, path: &Path) -> Result<Tally, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut t = Tally::default();
    for (i, line) in text.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let f: Vec<&str> = line.split(';').collect();
        if f.len() < 5 {
            continue;
        }
        let chars: Option<Vec<char>> = f[0].split_whitespace().map(|h| u32::from_str_radix(h, 16).ok().and_then(char::from_u32)).collect();
        let Some(chars) = chars else {
            t.total += 1;
            continue;
        };
        let s: String = chars.iter().collect();
        let classes: Vec<BidiClass> = chars.iter().map(|&c| unicode_bidi::bidi_class(c)).collect();
        let base = match f[1].trim() {
            "0" => BaseDirection::Ltr,
            "1" => BaseDirection::Rtl,
            _ => BaseDirection::Auto,
        };
        let o = run_parley(an, &s, &classes, base);
        check(&mut t, o, &parse_levels(f[3]), &parse_order(f[4]), f[2].trim().parse().ok(), json!({"line": i + 1, "input": f[0].trim(), "paragraph": f[1].trim()}));
    }
    Ok(t)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: bidi_parley <ucd_dir> <results.json>");
        std::process::exit(2);
    }
    let ucd = Path::new(&args[1]);
    let mut an = Analyzer::new();
    let mut variants = Vec::new();
    for ver in ["17.0.0", "18.0.0"] {
        for file in ["BidiTest.txt", "BidiCharacterTest.txt"] {
            let path = ucd.join(ver).join(file);
            let name = format!("parley_vs_{ver}_{}", file.trim_end_matches(".txt"));
            let r = if file == "BidiTest.txt" { bidi_test(&mut an, &path) } else { bidi_char_test(&mut an, &path) };
            let v = match r {
                Ok(t) => {
                    let rate = |n: u64| if t.total > 0 { n as f64 / t.total as f64 } else { 0.0 };
                    json!({
                        "name": name, "file": path.display().to_string(),
                        "total": t.total, "pass": t.pass, "fail": t.total - t.pass, "pass_rate": rate(t.pass),
                        "levels_pass": t.levels_ok, "levels_pass_rate": rate(t.levels_ok),
                        "reorder_pass": t.reorder_ok, "reorder_pass_rate": rate(t.reorder_ok),
                        "para_level_pass": t.para_ok,
                        "first_failures": t.failures,
                    })
                }
                Err(e) => json!({"name": name, "error": e, "pass": 0, "fail": 0, "total": 0}),
            };
            println!("{}: {}/{}", name, v["pass"], v["total"]);
            variants.push(v);
        }
    }
    let (mut pass, mut fail) = (0u64, 0u64);
    let mut first = Vec::new();
    for v in &variants {
        pass += v["pass"].as_u64().unwrap_or(0);
        fail += v["fail"].as_u64().unwrap_or(0);
        for f in v["first_failures"].as_array().cloned().unwrap_or_default() {
            if first.len() < MAX_FAILURES {
                let mut f = f;
                f["variant"] = v["name"].clone();
                first.push(f);
            }
        }
    }
    let total = pass + fail;
    let result = json!({
        "test": "bidi_parley",
        "parley_engine_version": "0.13.0",
        "pass": pass, "fail": fail, "total": total,
        "pass_rate": if total > 0 { pass as f64 / total as f64 } else { 0.0 },
        "pass_criterion": "per test case: Parley's resolved levels (parley_engine::Analyzer, plus harness-applied L1 trailing-whitespace reset) equal the expected levels at non-x positions, unicode-bidi's L2 reorder_visual over those levels gives the expected order, and for BidiCharacterTest the paragraph level matches",
        "notes": [
            "Parley resolves bidi internally (parley_engine/src/bidi.rs) with its own baked Unicode data (icu 2.3 generation); only levels are exposed, reordering happens inside line layout, so L2 is applied with unicode-bidi's reorder_visual here.",
            "Parley defers L1 clause 4 (trailing whitespace at end of line) to line layout; the harness applies it using the test's own classes (BidiTest) or unicode-bidi's Bidi_Class (BidiCharacterTest).",
            "When Parley skips resolution (pure-LTR text, LTR/auto paragraph) all levels are taken as the paragraph level."
        ],
        "variants": variants,
        "first_failures": first,
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&result).unwrap()).expect("write results");
}
