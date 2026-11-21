use cssparser::{Parser, ToCss};
use serde_json::{json, Value};
use std::panic::{catch_unwind, AssertUnwindSafe};

fn guarded<F: FnOnce() -> Value>(f: F) -> Value {
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(v) => v,
        Err(_) => json!({"status": "panic"}),
    }
}

fn finite(v: [f32; 4]) -> Value {
    if v.iter().all(|x| x.is_finite()) {
        json!({"status": "ok", "srgb": v})
    } else {
        json!({"status": "ok_nonfinite", "srgb": v.iter().map(|x| x.to_string()).collect::<Vec<_>>()})
    }
}

fn linebender_color(input: &str) -> Value {
    guarded(|| match color::parse_color(input) {
        Ok(c) => finite(c.to_alpha_color::<color::Srgb>().components),
        Err(e) => json!({"status": "invalid", "error": e.to_string()}),
    })
}

fn csscolorparser_color(input: &str) -> Value {
    guarded(|| match csscolorparser::parse(input) {
        Ok(c) => finite([c.r, c.g, c.b, c.a]),
        Err(e) => json!({"status": "invalid", "error": e.to_string()}),
    })
}

fn cssparser_color(input: &str) -> Value {
    guarded(|| {
        let mut parser = Parser::new(input);
        match parser.parse_entirely(|p| cssparser_color::Color::parse(p)) {
            Ok(c) => json!({"status": "ok", "css": c.to_css_string()}),
            Err(e) => json!({"status": "invalid", "error": format!("{:?}", e.kind)}),
        }
    })
}

fn main() {
    std::panic::set_hook(Box::new(|_| {}));
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: csscolor_libs <inputs.json> <out.json>");
        std::process::exit(2);
    }
    let doc: Value = serde_json::from_slice(&std::fs::read(&args[1]).expect("read inputs")).expect("parse inputs");
    let cases = doc["cases"].as_array().cloned().unwrap_or_default();
    let mut color_out = Vec::new();
    let mut ccp_out = Vec::new();
    let mut cpc_out = Vec::new();
    for c in &cases {
        let id = c["id"].clone();
        let input = c["input"].as_str().unwrap_or("");
        let mut a = linebender_color(input);
        a["id"] = id.clone();
        color_out.push(a);
        let mut b = csscolorparser_color(input);
        b["id"] = id.clone();
        ccp_out.push(b);
        let mut d = cssparser_color(input);
        d["id"] = id;
        cpc_out.push(d);
    }
    let result = json!({
        "candidates": {
            "color": {"crate": "color", "version": "0.3.3", "output": "srgb floats via DynamicColor::to_alpha_color::<Srgb>() (missing components as 0, no gamut mapping)", "results": color_out},
            "csscolorparser": {"crate": "csscolorparser", "version": "0.9.2", "output": "srgb floats from Color{r,g,b,a}", "results": ccp_out},
            "cssparser-color": {"crate": "cssparser-color", "version": "0.6.0", "output": "parse only; re-serialized with ToCss and converted to sRGB by the colorjs.io oracle", "results": cpc_out},
        }
    });
    std::fs::write(&args[2], serde_json::to_vec_pretty(&result).unwrap()).expect("write output");
}
