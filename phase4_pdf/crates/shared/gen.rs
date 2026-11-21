// Phase 4 fixture generator: builds every fixture under every conformance profile with krilla
// directly and records which profiles krilla refuses, with its validation errors.
mod common;
mod fixtures;

#[cfg(feature = "k07")]
#[path = "compat07.rs"]
mod compat;
#[cfg(feature = "k08")]
#[path = "compat08.rs"]
mod compat;

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};
use std::time::Instant;

use serde_json::{json, Value};

use common::Assets;
use fixtures::{Fixture, FIXTURES, UNSUPPORTED};

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

fn file_id(profile: &str) -> String {
    profile.replace('+', "_")
}

fn panic_message(p: &Box<dyn std::any::Any + Send>) -> String {
    if let Some(s) = p.downcast_ref::<&str>() {
        s.to_string()
    } else if let Some(s) = p.downcast_ref::<String>() {
        s.clone()
    } else {
        "non-string panic payload".to_string()
    }
}

struct Outcome {
    entry: Value,
    pdf: Option<Vec<u8>>,
    expected: Value,
}

fn build_one(a: &Assets, fx: &Fixture, profile: &str) -> Outcome {
    let mut entry = json!({
        "fixture": fx.name, "profile": profile, "file": format!("{}/{}.pdf", fx.name, file_id(profile)),
        "krilla": compat::KRILLA_VERSION,
    });
    let settings = match compat::settings(profile, a.cmyk.clone()) {
        Ok(s) => s,
        Err(e) => {
            entry["status"] = json!("config_invalid");
            entry["errors"] = json!([e]);
            return Outcome { entry, pdf: None, expected: Value::Null };
        }
    };
    entry["pdf_version"] = json!(compat::version_str(&settings));
    entry["validators"] = json!(compat::validators_str(&settings));
    let mut expected = Value::Null;
    let t0 = Instant::now();
    let res = catch_unwind(AssertUnwindSafe(|| (fx.build)(a, settings, &mut expected)));
    let ms = t0.elapsed().as_secs_f64() * 1000.0;
    entry["ms"] = json!((ms * 1000.0).round() / 1000.0);
    let mut pdf = None;
    match res {
        Err(p) => {
            entry["status"] = json!("panic");
            entry["errors"] = json!([panic_message(&p)]);
        }
        Ok(Err(asset)) => {
            entry["status"] = json!("asset_error");
            entry["errors"] = json!([asset]);
        }
        Ok(Ok(Err(kerr))) => {
            let (kind, errs) = compat::describe(&kerr);
            // Validation, SixteenBitImage (16-bit image under PDF 1.4) and Limit (0.8.x version limits) are
            // krilla refusing content that the selected profile/version cannot carry, not failures.
            let refusal = matches!(kind.as_str(), "Validation" | "SixteenBitImage" | "Limit");
            let status = if refusal { "refused" } else { "error" };
            entry["status"] = json!(status);
            entry["error_kind"] = json!(kind);
            let mut kinds: Vec<String> = errs.iter().map(|e| common::variant_name(e)).collect();
            kinds.sort();
            kinds.dedup();
            entry["error_variants"] = json!(kinds);
            entry["errors"] = json!(errs);
        }
        Ok(Ok(Ok(bytes))) => {
            entry["status"] = json!("ok");
            entry["bytes"] = json!(bytes.len());
            pdf = Some(bytes);
        }
    }
    if let Some(pc) = expected.get("page_count") {
        entry["pages"] = pc.clone();
    }
    Outcome { entry, pdf, expected }
}

fn select<'a>(all: &'a [&'a str], filter: &Option<String>) -> Vec<&'a str> {
    match filter {
        None => all.to_vec(),
        Some(f) => {
            let want: Vec<&str> = f.split(',').map(|s| s.trim()).collect();
            all.iter().copied().filter(|x| want.contains(x)).collect()
        }
    }
}

fn corpus(args: &[String]) -> Result<(), String> {
    let manifest = arg(args, "--manifest").ok_or("--manifest required")?;
    let out = PathBuf::from(arg(args, "--out").ok_or("--out required")?);
    let a = Assets::load(&manifest)?;
    let fixture_names: Vec<&str> = FIXTURES.iter().map(|f| f.name).collect();
    let profile_ids: Vec<&str> = compat::PROFILES.iter().map(|p| p.id).collect();
    let fsel = select(&fixture_names, &arg(args, "--fixtures"));
    let psel = select(&profile_ids, &arg(args, "--profiles"));
    std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let mut entries = vec![];
    for fx in FIXTURES.iter().filter(|f| fsel.contains(&f.name)) {
        let dir = out.join(fx.name);
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let mut wrote_expected = false;
        for p in compat::PROFILES.iter().filter(|p| psel.contains(&p.id)) {
            let o = build_one(&a, fx, p.id);
            eprintln!("{:<22} {:<10} {}", fx.name, p.id, o.entry["status"].as_str().unwrap_or("?"));
            if let Some(bytes) = &o.pdf {
                std::fs::write(dir.join(format!("{}.pdf", file_id(p.id))), bytes).map_err(|e| e.to_string())?;
            }
            if !wrote_expected && !o.expected.is_null() {
                let s = serde_json::to_string_pretty(&o.expected).unwrap();
                std::fs::write(dir.join("expected.json"), s).map_err(|e| e.to_string())?;
                wrote_expected = true;
            }
            entries.push(o.entry);
        }
    }
    let fonts: serde_json::Map<String, Value> = a
        .fonts
        .iter()
        .map(|(k, v)| (k.clone(), json!({"path": v.path, "index": v.index})))
        .collect();
    let report = json!({
        "krilla_version": compat::KRILLA_VERSION,
        "profiles": compat::PROFILES.iter().map(|p| json!({"id": p.id, "file_id": file_id(p.id), "verapdf": p.verapdf})).collect::<Vec<_>>(),
        "profiles_not_offered": compat::NOT_OFFERED,
        "fixtures": fixture_names,
        "unsupported_features": UNSUPPORTED.iter().map(|(n, r)| json!({"feature": n, "reason": r})).collect::<Vec<_>>(),
        "assets": {"font_errors": a.font_errors, "cmyk_error": a.cmyk_error, "fonts": fonts},
        "entries": entries,
    });
    std::fs::write(out.join("generation.json"), serde_json::to_string_pretty(&report).unwrap()).map_err(|e| e.to_string())?;
    Ok(())
}

fn single(args: &[String]) -> Result<(), String> {
    let manifest = arg(args, "--manifest").ok_or("--manifest required")?;
    let fixture = arg(args, "--fixture").ok_or("--fixture required")?;
    let profile = arg(args, "--profile").unwrap_or_else(|| "none".into());
    let out = arg(args, "--out");
    let t_load = Instant::now();
    let a = Assets::load(&manifest)?;
    let load_ms = t_load.elapsed().as_secs_f64() * 1000.0;
    let fx = FIXTURES.iter().find(|f| f.name == fixture).ok_or("unknown fixture")?;
    let mut o = build_one(&a, fx, &profile);
    o.entry["asset_load_ms"] = json!(load_ms);
    if let (Some(path), Some(bytes)) = (out, &o.pdf) {
        std::fs::write(Path::new(&path), bytes).map_err(|e| e.to_string())?;
    }
    println!("{}", o.entry);
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let cmd = args.get(1).map(|s| s.as_str()).unwrap_or("");
    let r = match cmd {
        "corpus" => corpus(&args),
        "single" => single(&args),
        "list" => {
            println!(
                "{}",
                json!({
                    "krilla_version": compat::KRILLA_VERSION,
                    "fixtures": FIXTURES.iter().map(|f| f.name).collect::<Vec<_>>(),
                    "profiles": compat::PROFILES.iter().map(|p| p.id).collect::<Vec<_>>(),
                    "profiles_not_offered": compat::NOT_OFFERED,
                })
            );
            Ok(())
        }
        _ => Err("usage: gen corpus --manifest M --out DIR [--fixtures a,b] [--profiles x,y] | gen single --manifest M --fixture F [--profile P] [--out F.pdf] | gen list".into()),
    };
    if let Err(e) = r {
        eprintln!("error: {e}");
        std::process::exit(2);
    }
}
