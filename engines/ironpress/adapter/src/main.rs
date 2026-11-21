use std::path::{Path, PathBuf};
use std::process;

use ironpress::{HtmlConverter, Margin, PageSize};

const PX_TO_PT: f32 = 72.0 / 96.0;
const UNSUPPORTED_JSON: &str = "{\"unsupported\":true}\n";

struct Args {
    input: PathBuf,
    output: PathBuf,
    page_width_px: f32,
    page_height_px: f32,
    margin_px: f32,
    geometry: Option<PathBuf>,
    diagnostics: Option<PathBuf>,
}

fn take_value<'a>(flag: &str, value: Option<&'a String>) -> Result<&'a String, String> {
    value.ok_or_else(|| format!("{flag} requires a value"))
}

fn take_number(flag: &str, value: Option<&String>) -> Result<f32, String> {
    let raw = take_value(flag, value)?;
    let parsed: f32 = raw
        .parse()
        .map_err(|_| format!("{flag} requires a number, got: {raw}"))?;
    if !parsed.is_finite() || parsed < 0.0 {
        return Err(format!("{flag} must be a finite non-negative number, got: {raw}"));
    }
    Ok(parsed)
}

fn parse_args(argv: &[String]) -> Result<Args, String> {
    let mut iter = argv.iter();
    match iter.next().map(String::as_str) {
        Some("render") => {}
        Some(other) => return Err(format!("unknown subcommand: {other}")),
        None => return Err("missing subcommand: render".to_string()),
    }

    let mut positional: Vec<PathBuf> = Vec::new();
    let mut page_width_px: Option<f32> = None;
    let mut page_height_px: Option<f32> = None;
    let mut margin_px: Option<f32> = None;
    let mut geometry: Option<PathBuf> = None;
    let mut diagnostics: Option<PathBuf> = None;

    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--page-width-px" => page_width_px = Some(take_number(arg, iter.next())?),
            "--page-height-px" => page_height_px = Some(take_number(arg, iter.next())?),
            "--margin-px" => margin_px = Some(take_number(arg, iter.next())?),
            "--geometry" => geometry = Some(PathBuf::from(take_value(arg, iter.next())?)),
            "--diagnostics" => {
                diagnostics = Some(PathBuf::from(take_value(arg, iter.next())?))
            }
            other if other.starts_with("--") => return Err(format!("unknown option: {other}")),
            _ => positional.push(PathBuf::from(arg)),
        }
    }

    if positional.len() != 2 {
        return Err(format!(
            "expected 2 positional arguments <input.html> <output>, got {}",
            positional.len()
        ));
    }
    let output = positional.pop().ok_or("missing <output>")?;
    let input = positional.pop().ok_or("missing <input.html>")?;

    let page_width_px = page_width_px.ok_or("missing --page-width-px")?;
    let page_height_px = page_height_px.ok_or("missing --page-height-px")?;
    let margin_px = margin_px.ok_or("missing --margin-px")?;
    if page_width_px <= 0.0 || page_height_px <= 0.0 {
        return Err("page width and height must be positive".to_string());
    }

    Ok(Args {
        input,
        output,
        page_width_px,
        page_height_px,
        margin_px,
        geometry,
        diagnostics,
    })
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

fn pdf_page_count(pdf: &[u8]) -> Option<u64> {
    let pages_at = find(pdf, b"/Type /Pages ")?;
    let rest = &pdf[pages_at..];
    let count_at = find(rest, b"/Count ")? + b"/Count ".len();
    let digits: Vec<u8> = rest[count_at..]
        .iter()
        .take_while(|b| b.is_ascii_digit())
        .copied()
        .collect();
    std::str::from_utf8(&digits).ok()?.parse().ok()
}

fn run(args: Args) -> i32 {
    if let Some(path) = &args.geometry {
        if let Err(e) = std::fs::write(path, UNSUPPORTED_JSON) {
            eprintln!("failed to write {}: {e}", path.display());
            return 2;
        }
    }
    if let Some(path) = &args.diagnostics {
        if let Err(e) = std::fs::write(path, UNSUPPORTED_JSON) {
            eprintln!("failed to write {}: {e}", path.display());
            return 2;
        }
    }

    let html = match std::fs::read_to_string(&args.input) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("failed to read {}: {e}", args.input.display());
            return 2;
        }
    };
    let input_abs = match std::fs::canonicalize(&args.input) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("failed to resolve {}: {e}", args.input.display());
            return 2;
        }
    };
    let base_dir: PathBuf = input_abs
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("/"));

    let converter = HtmlConverter::new()
        .page_size(PageSize::new(
            args.page_width_px * PX_TO_PT,
            args.page_height_px * PX_TO_PT,
        ))
        .margin(Margin::uniform(args.margin_px * PX_TO_PT))
        .base_path(&base_dir)
        .resource_root(Path::new("/"));

    let pdf = match converter.convert(&html) {
        Ok(bytes) => bytes,
        Err(e) => {
            eprintln!("ironpress error: {e}");
            return 2;
        }
    };

    if let Err(e) = std::fs::write(&args.output, &pdf) {
        eprintln!("failed to write {}: {e}", args.output.display());
        return 2;
    }

    if let Some(pages) = pdf_page_count(&pdf) {
        println!("{{\"pages\":{pages}}}");
    }
    0
}

fn main() {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let args = match parse_args(&argv) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("usage error: {e}");
            eprintln!(
                "usage: adapter-ironpress render <input.html> <output.pdf> --page-width-px <W> --page-height-px <H> --margin-px <M> [--geometry <geometry.json>] [--diagnostics <diag.json>]"
            );
            process::exit(1);
        }
    };
    process::exit(run(args));
}
