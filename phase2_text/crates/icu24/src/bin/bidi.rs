use icu_properties::CodePointMapData;
use serde_json::{json, Value};
use std::path::Path;
use unicode_bidi::{format_chars, BidiDataSource, BidiInfo, HardcodedBidiData, Level};

const MAX_FAILURES: usize = 20;

fn class_char(name: &str) -> Option<char> {
    Some(match name {
        "AL" => '\u{060B}',
        "AN" => '\u{0605}',
        "B" => '\u{000A}',
        "BN" => '\u{2060}',
        "CS" => '\u{2044}',
        "EN" => '\u{06F9}',
        "ES" => '\u{208B}',
        "ET" => '\u{20CF}',
        "FSI" => format_chars::FSI,
        "L" => '\u{02B8}',
        "LRE" => format_chars::LRE,
        "LRI" => format_chars::LRI,
        "LRO" => format_chars::LRO,
        "NSM" => '\u{0300}',
        "ON" => '\u{03F6}',
        "PDF" => format_chars::PDF,
        "PDI" => format_chars::PDI,
        "R" => '\u{0590}',
        "RLE" => format_chars::RLE,
        "RLI" => format_chars::RLI,
        "RLO" => format_chars::RLO,
        "S" => '\u{001F}',
        "WS" => '\u{200A}',
        _ => return None,
    })
}

const CLASSES: &[&str] = &[
    "AL", "AN", "B", "BN", "CS", "EN", "ES", "ET", "FSI", "L", "LRE", "LRI", "LRO", "NSM", "ON", "PDF", "PDI", "R", "RLE", "RLI", "RLO", "S", "WS",
];

struct Outcome {
    para_level: u8,
    levels: Vec<u8>,
    order_e2e: Vec<usize>,
}

fn run_ub<D: BidiDataSource>(ds: &D, text: &str, base: Option<Level>) -> Result<Outcome, String> {
    let info = BidiInfo::new_with_data_source(ds, text, base);
    if info.paragraphs.len() != 1 {
        return Err(format!("{} paragraphs", info.paragraphs.len()));
    }
    let para = &info.paragraphs[0];
    let levels = info.reordered_levels_per_char(para, para.range.clone());
    let order = BidiInfo::reorder_visual(&levels);
    Ok(Outcome { para_level: para.level.number(), levels: levels.iter().map(|l| l.number()).collect(), order_e2e: order })
}

fn filtered_order(levels: &[u8], expected_levels: &[Option<u8>]) -> Vec<usize> {
    let keep: Vec<usize> = (0..levels.len()).filter(|&i| expected_levels.get(i).copied().flatten().is_some()).collect();
    let lv: Vec<Level> = keep.iter().map(|&i| Level::new(levels[i]).unwrap_or(Level::ltr())).collect();
    BidiInfo::reorder_visual(&lv).into_iter().map(|v| keep[v]).collect()
}

#[derive(Default)]
struct Tally {
    total: u64,
    pass: u64,
    levels_ok: u64,
    reorder_ok: u64,
    reorder_filtered_ok: u64,
    para_level_ok: u64,
    errors: u64,
    failures: Vec<Value>,
}

impl Tally {
    fn json(&self, name: &str, file: &str, data: &str) -> Value {
        let r = |n: u64| if self.total > 0 { n as f64 / self.total as f64 } else { 0.0 };
        json!({
            "name": name, "file": file, "data_source": data,
            "total": self.total, "pass": self.pass, "fail": self.total - self.pass,
            "pass_rate": r(self.pass),
            "levels_pass": self.levels_ok, "levels_pass_rate": r(self.levels_ok),
            "reorder_pass": self.reorder_ok, "reorder_pass_rate": r(self.reorder_ok),
            "reorder_filtered_pass": self.reorder_filtered_ok,
            "para_level_pass": self.para_level_ok,
            "errors": self.errors,
            "first_failures": self.failures,
        })
    }
}

fn check(
    t: &mut Tally,
    res: Result<Outcome, String>,
    exp_levels: &[Option<u8>],
    exp_order: &[usize],
    exp_para: Option<u8>,
    ctx: Value,
) {
    t.total += 1;
    let o = match res {
        Ok(o) => o,
        Err(e) => {
            t.errors += 1;
            if t.failures.len() < MAX_FAILURES {
                t.failures.push(json!({"ctx": ctx, "error": e}));
            }
            return;
        }
    };
    let levels_ok = o.levels.len() == exp_levels.len()
        && o.levels.iter().zip(exp_levels).all(|(a, e)| e.map_or(true, |e| e == *a));
    let order: Vec<usize> = o.order_e2e.iter().copied().filter(|&i| exp_levels.get(i).copied().flatten().is_some()).collect();
    let reorder_ok = order == exp_order;
    let filt_ok = filtered_order(&o.levels, exp_levels) == exp_order;
    let para_ok = exp_para.map_or(true, |p| p == o.para_level);
    if levels_ok {
        t.levels_ok += 1;
    }
    if reorder_ok {
        t.reorder_ok += 1;
    }
    if filt_ok {
        t.reorder_filtered_ok += 1;
    }
    if para_ok {
        t.para_level_ok += 1;
    }
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

fn bidi_test<D: BidiDataSource>(ds: &D, path: &Path) -> Result<Tally, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut t = Tally::default();
    let mut exp_levels: Vec<Option<u8>> = Vec::new();
    let mut exp_order: Vec<usize> = Vec::new();
    for (i, line) in text.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(rest) = line.strip_prefix("@Levels:") {
            exp_levels = parse_levels(rest);
            continue;
        }
        if let Some(rest) = line.strip_prefix("@Reorder:") {
            exp_order = parse_order(rest);
            continue;
        }
        if line.starts_with('@') {
            continue;
        }
        let mut parts = line.split(';');
        let classes: Vec<&str> = parts.next().unwrap_or("").split_whitespace().collect();
        let bitset = u8::from_str_radix(parts.next().unwrap_or("0").trim(), 16).unwrap_or(0);
        let s: Option<String> = classes.iter().map(|c| class_char(c)).collect();
        let Some(s) = s else {
            return Err(format!("line {}: unknown class", i + 1));
        };
        for (bit, base, label) in [(1u8, None, "auto"), (2, Some(Level::ltr()), "LTR"), (4, Some(Level::rtl()), "RTL")] {
            if bitset & bit == 0 {
                continue;
            }
            let ctx = json!({"line": i + 1, "input": classes.join(" "), "paragraph": label});
            check(&mut t, run_ub(ds, &s, base), &exp_levels, &exp_order, None, ctx);
        }
    }
    Ok(t)
}

fn bidi_char_test<D: BidiDataSource>(ds: &D, path: &Path) -> Result<Tally, String> {
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
        let s: Option<String> = f[0].split_whitespace().map(|h| u32::from_str_radix(h, 16).ok().and_then(char::from_u32)).collect();
        let Some(s) = s else {
            t.total += 1;
            t.errors += 1;
            continue;
        };
        let base = match f[1].trim() {
            "0" => Some(Level::ltr()),
            "1" => Some(Level::rtl()),
            _ => None,
        };
        let exp_para: Option<u8> = f[2].trim().parse().ok();
        let ctx = json!({"line": i + 1, "input": f[0].trim(), "paragraph": f[1].trim()});
        check(&mut t, run_ub(ds, &s, base), &parse_levels(f[3]), &parse_order(f[4]), exp_para, ctx);
    }
    Ok(t)
}

fn class_name_check<D: BidiDataSource>(ds: &D) -> Vec<Value> {
    let mut out = Vec::new();
    for c in CLASSES {
        let ch = class_char(c).unwrap();
        let got = format!("{:?}", ds.bidi_class(ch));
        if got != *c {
            out.push(json!({"class": c, "char": format!("U+{:04X}", ch as u32), "data_source_class": got}));
        }
    }
    out
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: bidi <ucd_dir> <results.json>");
        std::process::exit(2);
    }
    let ucd = Path::new(&args[1]);
    let icu = CodePointMapData::<icu_properties::props::BidiClass>::new();
    let hard = HardcodedBidiData;
    let ub_ver = unicode_bidi::UNICODE_VERSION;
    let ub_label = format!("unicode-bidi 0.3.18 hardcoded data (Unicode {}.{}.{})", ub_ver.0, ub_ver.1, ub_ver.2);
    let icu_label = "unicode-bidi 0.3.18 algorithm + icu_properties 2.4.0 Bidi_Class data (Unicode 18.0.0); bracket pairs from unicode-bidi defaults".to_string();

    let mut variants: Vec<Value> = Vec::new();
    let runs: Vec<(&str, &str, &str, bool)> = vec![
        ("hardcoded_vs_16.0_BidiTest", "16.0.0", "BidiTest.txt", false),
        ("hardcoded_vs_16.0_BidiCharacterTest", "16.0.0", "BidiCharacterTest.txt", false),
        ("hardcoded_vs_18.0_BidiTest", "18.0.0", "BidiTest.txt", false),
        ("hardcoded_vs_18.0_BidiCharacterTest", "18.0.0", "BidiCharacterTest.txt", false),
        ("icu4x_data_vs_18.0_BidiTest", "18.0.0", "BidiTest.txt", true),
        ("icu4x_data_vs_18.0_BidiCharacterTest", "18.0.0", "BidiCharacterTest.txt", true),
    ];
    for (name, ver, file, use_icu) in runs {
        let path = ucd.join(ver).join(file);
        let is_char = file.starts_with("BidiCharacter");
        let label = if use_icu { &icu_label } else { &ub_label };
        let r = match (use_icu, is_char) {
            (false, false) => bidi_test(&hard, &path),
            (false, true) => bidi_char_test(&hard, &path),
            (true, false) => bidi_test(&icu, &path),
            (true, true) => bidi_char_test(&icu, &path),
        };
        let v = match r {
            Ok(t) => t.json(name, &path.display().to_string(), label),
            Err(e) => json!({"name": name, "file": path.display().to_string(), "error": e, "pass": 0, "fail": 0, "total": 0}),
        };
        println!("{}: {}/{}", name, v["pass"], v["total"]);
        variants.push(v);
    }
    let (mut pass, mut fail) = (0u64, 0u64);
    let mut first_failures = Vec::new();
    for v in &variants {
        pass += v["pass"].as_u64().unwrap_or(0);
        fail += v["fail"].as_u64().unwrap_or(0);
        for f in v["first_failures"].as_array().cloned().unwrap_or_default() {
            if first_failures.len() < MAX_FAILURES {
                let mut f = f;
                f["variant"] = v["name"].clone();
                first_failures.push(f);
            }
        }
    }
    let total = pass + fail;
    let result = json!({
        "test": "bidi",
        "unicode_bidi_version": "0.3.18",
        "unicode_bidi_unicode_version": format!("{}.{}.{}", ub_ver.0, ub_ver.1, ub_ver.2),
        "icu_properties_version": "2.4.0",
        "pass": pass, "fail": fail, "total": total,
        "pass_rate": if total > 0 { pass as f64 / total as f64 } else { 0.0 },
        "pass_criterion": "per test case: resolved levels equal (x positions ignored), visual order equal (x positions dropped from the crate's full reorder_visual map, as upstream conformance_tests.rs does), and for BidiCharacterTest the resolved paragraph level equal",
        "notes": [
            "BidiTest base-level bitset is evaluated for all three values (auto-LTR, LTR, RTL). Upstream conformance_tests.rs only evaluates auto because of an operator-precedence bug in gen_base_levels_for_base_tests.",
            "BidiTest inputs are generated from one representative character per Bidi_Class (same table as upstream); representative_class_mismatches lists any character whose class differs in the data source.",
            "reorder_filtered_pass reorders only the non-X9 characters (levels taken from the crate) and is reported for information.",
            "ICU4X has no bidi algorithm of its own; it supplies Bidi_Class data to unicode-bidi through icu_properties' unicode_bidi feature. Parley's own resolver is measured separately in bidi_parley.json."
        ],
        "representative_class_mismatches": {
            "hardcoded": class_name_check(&hard),
            "icu4x": class_name_check(&icu),
        },
        "variants": variants,
        "first_failures": first_failures,
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&result).unwrap()).expect("write results");
}
