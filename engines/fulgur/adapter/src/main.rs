use fulgur::asset::AssetBundle;
use fulgur::engine::Engine;
use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

const PX_TO_PT: f32 = 0.75;

const USAGE: &str = "usage: adapter-fulgur render <input.html> <output.pdf> \
--page-width-px <W> --page-height-px <H> --margin-px <M> \
[--geometry <geometry.json>] [--diagnostics <diag.json>]";

static WARNINGS: Mutex<Vec<(String, String)>> = Mutex::new(Vec::new());

struct CollectingLogger;

impl log::Log for CollectingLogger {
    fn enabled(&self, metadata: &log::Metadata) -> bool {
        metadata.level() <= log::Level::Warn
    }

    fn log(&self, record: &log::Record) {
        if self.enabled(record.metadata()) {
            let message = record.args().to_string();
            let level = record.level().to_string().to_lowercase();
            let kind = format!("{}:{}", level, record.target());
            eprintln!("{}: {}", level, message);
            if let Ok(mut w) = WARNINGS.lock() {
                w.push((kind, message));
            }
        }
    }

    fn flush(&self) {}
}

static LOGGER: CollectingLogger = CollectingLogger;

#[cfg(unix)]
struct StdoutIsolator {
    saved_fd: libc::c_int,
}

#[cfg(unix)]
impl StdoutIsolator {
    fn install() -> Option<Self> {
        use std::io::Write;
        let _ = std::io::stdout().flush();
        let saved = unsafe { libc::dup(1) };
        if saved < 0 {
            return None;
        }
        if unsafe { libc::dup2(2, 1) } < 0 {
            unsafe { libc::close(saved) };
            return None;
        }
        Some(Self { saved_fd: saved })
    }
}

#[cfg(unix)]
impl Drop for StdoutIsolator {
    fn drop(&mut self) {
        use std::io::Write;
        let _ = std::io::stdout().flush();
        unsafe {
            libc::dup2(self.saved_fd, 1);
            libc::close(self.saved_fd);
        }
    }
}

struct Args {
    input: PathBuf,
    output: PathBuf,
    width_px: f32,
    height_px: f32,
    margin_px: f32,
    geometry: Option<PathBuf>,
    diagnostics: Option<PathBuf>,
}

fn parse_num(value: Option<OsString>, name: &str) -> Result<f32, String> {
    let value = value.ok_or_else(|| format!("missing value for {}", name))?;
    let text = value
        .to_str()
        .ok_or_else(|| format!("non UTF-8 value for {}", name))?;
    let v: f32 = text
        .trim()
        .parse()
        .map_err(|_| format!("invalid number for {}: {}", name, text))?;
    if !v.is_finite() || v < 0.0 {
        return Err(format!("{} must be finite and non-negative: {}", name, text));
    }
    Ok(v)
}

fn parse_args() -> Result<Args, String> {
    let mut it = std::env::args_os().skip(1);
    match it.next() {
        Some(cmd) if cmd.to_str() == Some("render") => {}
        _ => return Err("expected subcommand 'render'".to_string()),
    }
    let mut positional: Vec<PathBuf> = Vec::new();
    let mut width_px: Option<f32> = None;
    let mut height_px: Option<f32> = None;
    let mut margin_px: Option<f32> = None;
    let mut geometry: Option<PathBuf> = None;
    let mut diagnostics: Option<PathBuf> = None;
    while let Some(arg) = it.next() {
        let flag = arg.to_str().map(|s| s.to_string());
        match flag.as_deref() {
            Some("--page-width-px") => width_px = Some(parse_num(it.next(), "--page-width-px")?),
            Some("--page-height-px") => {
                height_px = Some(parse_num(it.next(), "--page-height-px")?)
            }
            Some("--margin-px") => margin_px = Some(parse_num(it.next(), "--margin-px")?),
            Some("--geometry") => {
                geometry = Some(PathBuf::from(
                    it.next().ok_or_else(|| "missing value for --geometry".to_string())?,
                ))
            }
            Some("--diagnostics") => {
                diagnostics = Some(PathBuf::from(
                    it.next()
                        .ok_or_else(|| "missing value for --diagnostics".to_string())?,
                ))
            }
            Some(s) if s.starts_with("--") => return Err(format!("unknown option {}", s)),
            _ => positional.push(PathBuf::from(arg)),
        }
    }
    if positional.len() != 2 {
        return Err("expected <input.html> <output.pdf>".to_string());
    }
    let output = positional.pop().unwrap();
    let input = positional.pop().unwrap();
    let width_px = width_px.ok_or_else(|| "missing --page-width-px".to_string())?;
    let height_px = height_px.ok_or_else(|| "missing --page-height-px".to_string())?;
    let margin_px = margin_px.ok_or_else(|| "missing --margin-px".to_string())?;
    if width_px <= 0.0 || height_px <= 0.0 {
        return Err("page width and height must be positive".to_string());
    }
    Ok(Args {
        input,
        output,
        width_px,
        height_px,
        margin_px,
        geometry,
        diagnostics,
    })
}

fn default_page_css(width_px: f32, height_px: f32, margin_px: f32) -> String {
    format!(
        "@page {{ size: {}px {}px; margin: {}px; }}",
        width_px, height_px, margin_px
    )
}

const IMAGE_EXTENSIONS: &[&str] = &["png", "jpg", "jpeg", "gif", "svg"];
const MAX_WALK_DEPTH: usize = 8;
const MAX_WALK_ENTRIES: usize = 20_000;
const MAX_CSS_FILE_BYTES: u64 = 4 * 1024 * 1024;
const MAX_CSS_TOTAL_BYTES: usize = 32 * 1024 * 1024;

struct WalkState {
    entries: usize,
    images: Vec<(String, PathBuf)>,
    css_text: String,
}

fn walk_dir(base: &Path, dir: &Path, depth: usize, state: &mut WalkState) {
    if depth > MAX_WALK_DEPTH {
        return;
    }
    let Ok(read) = std::fs::read_dir(dir) else {
        return;
    };
    let mut entries: Vec<std::fs::DirEntry> = read.filter_map(|e| e.ok()).collect();
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        state.entries += 1;
        if state.entries > MAX_WALK_ENTRIES {
            return;
        }
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        if name.starts_with('.') {
            continue;
        }
        let path = entry.path();
        let Ok(meta) = std::fs::metadata(&path) else {
            continue;
        };
        if meta.is_dir() {
            walk_dir(base, &path, depth + 1, state);
            continue;
        }
        if !meta.is_file() {
            continue;
        }
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_ascii_lowercase())
            .unwrap_or_default();
        if ext == "css" {
            if meta.len() <= MAX_CSS_FILE_BYTES && state.css_text.len() < MAX_CSS_TOTAL_BYTES {
                if let Ok(text) = std::fs::read_to_string(&path) {
                    state.css_text.push('\n');
                    state.css_text.push_str(&text);
                }
            }
            continue;
        }
        if !IMAGE_EXTENSIONS.contains(&ext.as_str()) {
            continue;
        }
        let Ok(rel) = path.strip_prefix(base) else {
            continue;
        };
        let mut parts: Vec<&str> = Vec::new();
        let mut ok = true;
        for comp in rel.components() {
            match comp.as_os_str().to_str() {
                Some(s) => parts.push(s),
                None => {
                    ok = false;
                    break;
                }
            }
        }
        if ok && !parts.is_empty() {
            state.images.push((parts.join("/"), path.clone()));
        }
    }
}

fn percent_encode_path(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        let keep = b.is_ascii_alphanumeric()
            || matches!(
                b,
                b'-' | b'.'
                    | b'_'
                    | b'~'
                    | b'/'
                    | b'!'
                    | b'$'
                    | b'&'
                    | b'\''
                    | b'('
                    | b')'
                    | b'*'
                    | b'+'
                    | b','
                    | b';'
                    | b'='
                    | b':'
                    | b'@'
                    | b'%'
                    | b'['
                    | b']'
                    | b'|'
                    | b'^'
                    | b'\\'
            );
        if keep {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{:02X}", b));
        }
    }
    out
}

fn register_local_images(bundle: &mut AssetBundle, base_dir: &Path, html: &str) {
    let mut state = WalkState {
        entries: 0,
        images: Vec::new(),
        css_text: String::new(),
    };
    walk_dir(base_dir, base_dir, 0, &mut state);
    let mut haystack = String::with_capacity(html.len() + state.css_text.len() + 1);
    haystack.push_str(html);
    haystack.push('\n');
    haystack.push_str(&state.css_text);
    for (rel, path) in state.images {
        let file_name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .to_string();
        if file_name.is_empty() {
            continue;
        }
        let encoded_name = percent_encode_path(&file_name);
        if !haystack.contains(file_name.as_str()) && !haystack.contains(encoded_name.as_str()) {
            continue;
        }
        if let Err(e) = bundle.add_image_file(rel.clone(), &path) {
            eprintln!("adapter-fulgur: failed to bundle image {}: {}", path.display(), e);
            continue;
        }
        let encoded_rel = percent_encode_path(&rel);
        if encoded_rel != rel {
            if let Err(e) = bundle.add_image_file(encoded_rel, &path) {
                eprintln!("adapter-fulgur: failed to bundle image {}: {}", path.display(), e);
            }
        }
    }
}

fn round3(v: f32) -> f64 {
    ((v as f64) * 1000.0).round() / 1000.0
}

struct PageGeom {
    width_px: f32,
    height_px: f32,
    margin_left_px: f32,
    margin_top_px: f32,
    boxes: Vec<serde_json::Value>,
}

fn build_geometry(
    engine: &Engine,
    html: &str,
    base_dir: &Path,
    notes: &mut Vec<(String, String)>,
) -> fulgur::Result<serde_json::Value> {
    let layout = engine.layout(html)?;
    let config = engine.config();

    let empty_fonts: Vec<Arc<Vec<u8>>> = Vec::new();
    let (combined_css, fonts): (String, &[Arc<Vec<u8>>]) = match engine.assets() {
        Some(a) => (a.combined_css(), a.fonts.as_slice()),
        None => (String::new(), empty_fonts.as_slice()),
    };
    let combined_css = fulgur::blitz_adapter::rewrite_marker_content_url(&combined_css);
    let mut gcpm = fulgur::gcpm::parser::parse_gcpm(&combined_css);
    let rewritten_html = fulgur::blitz_adapter::rewrite_marker_content_url_in_html(html);
    let (doc, link_gcpm, _column_css) = fulgur::blitz_adapter::parse_html_with_local_resources(
        &rewritten_html,
        config.content_width() / PX_TO_PT,
        (config.page_height() / PX_TO_PT) as u32,
        fonts,
        true,
        Some(base_dir),
    );
    gcpm.extend_from(link_gcpm);
    let inline_gcpm = fulgur::blitz_adapter::extract_gcpm_from_inline_styles(&doc);
    gcpm.extend_from(inline_gcpm);

    let page_count = fulgur::pagination_layout::implied_page_count(&layout.geometry).max(1);
    let rtl = layout.drawables.root_dir_rtl;
    let body_dy_px = layout.drawables.body_offset_pt.1.to_f32() / PX_TO_PT;

    let mut pages: Vec<PageGeom> = Vec::with_capacity(page_count as usize);
    for idx in 0..page_count {
        let (size, margin, landscape) = fulgur::gcpm::page_settings::resolve_page_settings(
            &gcpm.page_settings,
            idx as usize + 1,
            page_count as usize,
            config,
            rtl,
        );
        let size = if landscape { size.landscape() } else { size };
        pages.push(PageGeom {
            width_px: size.width / PX_TO_PT,
            height_px: size.height / PX_TO_PT,
            margin_left_px: margin.left / PX_TO_PT,
            margin_top_px: margin.top / PX_TO_PT,
            boxes: Vec::new(),
        });
    }

    let mut mismatches: usize = 0;
    for (node_id, geom) in layout.geometry.iter() {
        if layout.drawables.inline_box_subtree_skip.contains(node_id) {
            continue;
        }
        let Some(node) = doc.get_node(*node_id) else {
            continue;
        };
        let Some(elem) = node.element_data() else {
            continue;
        };
        let tag: &str = elem.name.local.as_ref();
        let id: &str = fulgur::blitz_adapter::get_attr(elem, "id").unwrap_or("");
        let class: &str = fulgur::blitz_adapter::get_attr(elem, "class").unwrap_or("");

        let drawn_id: Option<&str> = layout
            .drawables
            .block_styles
            .get(node_id)
            .and_then(|b| b.id.as_deref())
            .map(|s| s.as_str())
            .or_else(|| {
                layout
                    .drawables
                    .paragraphs
                    .get(node_id)
                    .and_then(|p| p.id.as_deref())
                    .map(|s| s.as_str())
            });
        if let Some(d) = drawn_id {
            if d != id {
                mismatches += 1;
                continue;
            }
        }

        let mut label = tag.to_string();
        if !id.is_empty() {
            label.push('#');
            label.push_str(id);
        }
        for c in class.split_whitespace() {
            label.push('.');
            label.push_str(c);
        }

        for frag in &geom.fragments {
            let p = frag.page_index as usize;
            let Some(page) = pages.get_mut(p) else {
                continue;
            };
            let mut y = page.margin_top_px + frag.y.to_f32();
            if p == 0 {
                y += body_dy_px;
            }
            let x = page.margin_left_px + frag.x.to_f32();
            page.boxes.push(serde_json::json!({
                "node": label,
                "tag": tag,
                "id": id,
                "x": round3(x),
                "y": round3(y),
                "w": round3(frag.width.to_f32()),
                "h": round3(frag.height.to_f32()),
            }));
        }
    }
    if mismatches > 0 {
        notes.push((
            "adapter:geometry-node-mapping".to_string(),
            format!(
                "{} geometry node(s) dropped: DOM re-parse id attribute disagreed with layout drawables",
                mismatches
            ),
        ));
    }

    let pages_json: Vec<serde_json::Value> = pages
        .into_iter()
        .enumerate()
        .map(|(i, p)| {
            serde_json::json!({
                "index": i,
                "width": round3(p.width_px),
                "height": round3(p.height_px),
                "boxes": p.boxes,
            })
        })
        .collect();
    Ok(serde_json::json!({ "pages": pages_json }))
}

fn write_json(path: &Path, value: &serde_json::Value) -> Result<(), String> {
    let text = serde_json::to_string(value).map_err(|e| e.to_string())?;
    std::fs::write(path, text).map_err(|e| format!("{}: {}", path.display(), e))
}

fn diagnostics_json(render_warning_count: usize, notes: &[(String, String)]) -> serde_json::Value {
    let mut items: Vec<serde_json::Value> = Vec::new();
    if let Ok(w) = WARNINGS.lock() {
        for (kind, message) in w.iter().take(render_warning_count) {
            items.push(serde_json::json!({ "kind": kind, "message": message }));
        }
    }
    for (kind, message) in notes {
        items.push(serde_json::json!({ "kind": kind, "message": message }));
    }
    serde_json::json!({ "warnings": items })
}

fn warning_count() -> usize {
    WARNINGS.lock().map(|w| w.len()).unwrap_or(0)
}

fn main() {
    if log::set_logger(&LOGGER).is_ok() {
        log::set_max_level(log::LevelFilter::Warn);
    }

    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("adapter-fulgur: {}", e);
            eprintln!("{}", USAGE);
            std::process::exit(1);
        }
    };

    let html = match std::fs::read_to_string(&args.input) {
        Ok(h) => h,
        Err(e) => {
            eprintln!("adapter-fulgur: cannot read {}: {}", args.input.display(), e);
            std::process::exit(1);
        }
    };
    let input_abs = match args.input.canonicalize() {
        Ok(p) => p,
        Err(e) => {
            eprintln!(
                "adapter-fulgur: cannot resolve {}: {}",
                args.input.display(),
                e
            );
            std::process::exit(1);
        }
    };
    let base_dir = input_abs
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("/"));

    let mut bundle = AssetBundle::new();
    bundle.add_css(default_page_css(args.width_px, args.height_px, args.margin_px));
    register_local_images(&mut bundle, &base_dir, &html);

    let engine = Engine::builder()
        .base_path(base_dir.clone())
        .assets(bundle)
        .build();

    #[cfg(unix)]
    let isolator = StdoutIsolator::install();

    let mut notes: Vec<(String, String)> = Vec::new();

    let pdf = match engine.render(&html) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("adapter-fulgur: render failed: {}", e);
            if let Some(ref d) = args.diagnostics {
                let count = warning_count();
                let _ = write_json(d, &diagnostics_json(count, &notes));
            }
            std::process::exit(2);
        }
    };
    let render_warning_count = warning_count();

    if let Err(e) = std::fs::write(&args.output, &pdf) {
        eprintln!(
            "adapter-fulgur: cannot write {}: {}",
            args.output.display(),
            e
        );
        std::process::exit(1);
    }

    if let Some(ref g) = args.geometry {
        match build_geometry(&engine, &html, &base_dir, &mut notes) {
            Ok(value) => {
                if let Err(e) = write_json(g, &value) {
                    eprintln!("adapter-fulgur: cannot write geometry: {}", e);
                    std::process::exit(1);
                }
            }
            Err(e) => {
                eprintln!("adapter-fulgur: layout for geometry failed: {}", e);
                std::process::exit(2);
            }
        }
    }

    if let Some(ref d) = args.diagnostics {
        if let Err(e) = write_json(d, &diagnostics_json(render_warning_count, &notes)) {
            eprintln!("adapter-fulgur: cannot write diagnostics: {}", e);
            std::process::exit(1);
        }
    }

    #[cfg(unix)]
    drop(isolator);

    if let Ok(doc) = lopdf::Document::load_mem(&pdf) {
        println!("{{\"pages\":{}}}", doc.get_pages().len());
    }
}
