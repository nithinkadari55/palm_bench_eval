// Shared by spike-rkjs (rquickjs) and spike-rkboa (raikiri-js on Boa) through #[path].
//
// The live DOM is a raikiri_dom::Document that scripts mutate in place. Layout queries and
// the final PDF both go through the public raikiri-html pipeline that engines/rkhead uses:
// the live DOM is serialized, parsed again with parse_html_with_resources and laid out with
// raikiri_html::layout (the same resources, page defaults and @page margin rule as
// fulgur-raikiri). For layout queries every element of a clone of the live DOM gets a
// data-rkjs-n="<arena index>" attribute first, so fragments of the reparsed document map
// back to live arena indices.
#![allow(dead_code)]

use fulgur_core::units::F32Units;
use fulgur_core::{AssetBundle, Config, Margin, PageSize};
use raikiri_dom::{Document, NodeKind, QuirksMode};
use raikiri_html::{FragmentKind, LayoutConfig, LayoutOptions, LayoutStatus, PageDefaults, RenderResources, SvgRendering};
use raikiri_traits::net::{FetchOutcome, FetchedResource, NetworkError, NetworkProvider, Request};
use raikiri_traits::{
    IntrinsicBox, NodeId, PageBox, ReplacedResolver, ResolveDisposition, ResolvedIntrinsic, ResolverError,
    ResolverRequest,
};
use std::collections::hash_map::Entry;
use std::collections::HashMap;
use std::ffi::OsString;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Instant;
use url::Url;

pub const STAMP: &str = "data-rkjs-n";
const PX_TO_PT: f32 = 0.75;
const DEFAULT_FONT_STYLESHEET: &str = "@layer { :where(html) { font-family: sans-serif } }";
const SVG_NS: &str = "http://www.w3.org/2000/svg";
const MATHML_NS: &str = "http://www.w3.org/1998/Math/MathML";

// ---------------------------------------------------------------- diagnostics

pub static LOG_WARNINGS: Mutex<Vec<(String, String)>> = Mutex::new(Vec::new());

struct CollectingLogger;

impl log::Log for CollectingLogger {
    fn enabled(&self, metadata: &log::Metadata) -> bool {
        metadata.level() <= log::Level::Warn
    }

    fn log(&self, record: &log::Record) {
        if self.enabled(record.metadata()) {
            let kind = format!("{}:{}", record.level().to_string().to_lowercase(), record.target());
            if let Ok(mut w) = LOG_WARNINGS.lock() {
                if w.len() < 2000 {
                    w.push((kind, record.args().to_string()));
                }
            }
        }
    }

    fn flush(&self) {}
}

static LOGGER: CollectingLogger = CollectingLogger;

pub fn install_logger() {
    if log::set_logger(&LOGGER).is_ok() {
        log::set_max_level(log::LevelFilter::Warn);
    }
}

pub fn log_warnings() -> Vec<(String, String)> {
    LOG_WARNINGS.lock().map(|w| w.clone()).unwrap_or_default()
}

// ---------------------------------------------------------------- arguments

pub struct Args {
    pub input: PathBuf,
    pub output: PathBuf,
    pub width_px: f32,
    pub height_px: f32,
    pub margin_px: f32,
    pub geometry: Option<PathBuf>,
    pub diagnostics: Option<PathBuf>,
    pub metrics: Option<PathBuf>,
    pub dump_html: Option<PathBuf>,
}

pub const USAGE: &str = "usage: <bin> render <input.html> <output.pdf> --page-width-px <W> --page-height-px <H> \
--margin-px <M> [--geometry <g.json>] [--diagnostics <d.json>] [--metrics <m.json>] [--dump-html <out.html>]";

fn parse_num(value: Option<OsString>, name: &str) -> Result<f32, String> {
    let value = value.ok_or_else(|| format!("missing value for {name}"))?;
    let text = value.to_str().ok_or_else(|| format!("non UTF-8 value for {name}"))?;
    let v: f32 = text.trim().parse().map_err(|_| format!("invalid number for {name}: {text}"))?;
    if !v.is_finite() || v < 0.0 {
        return Err(format!("{name} must be finite and non-negative: {text}"));
    }
    Ok(v)
}

fn path_arg(value: Option<OsString>, name: &str) -> Result<PathBuf, String> {
    value.map(PathBuf::from).ok_or_else(|| format!("missing value for {name}"))
}

pub fn parse_args() -> Result<Args, String> {
    let mut it = std::env::args_os().skip(1);
    match it.next() {
        Some(cmd) if cmd.to_str() == Some("render") => {}
        _ => return Err("expected subcommand 'render'".to_string()),
    }
    let mut positional: Vec<PathBuf> = Vec::new();
    let (mut w, mut h, mut m) = (None, None, None);
    let (mut geometry, mut diagnostics, mut metrics, mut dump_html) = (None, None, None, None);
    while let Some(arg) = it.next() {
        let flag = arg.to_str().map(|s| s.to_string());
        match flag.as_deref() {
            Some("--page-width-px") => w = Some(parse_num(it.next(), "--page-width-px")?),
            Some("--page-height-px") => h = Some(parse_num(it.next(), "--page-height-px")?),
            Some("--margin-px") => m = Some(parse_num(it.next(), "--margin-px")?),
            Some("--geometry") => geometry = Some(path_arg(it.next(), "--geometry")?),
            Some("--diagnostics") => diagnostics = Some(path_arg(it.next(), "--diagnostics")?),
            Some("--metrics") => metrics = Some(path_arg(it.next(), "--metrics")?),
            Some("--dump-html") => dump_html = Some(path_arg(it.next(), "--dump-html")?),
            Some(s) if s.starts_with("--") => return Err(format!("unknown option {s}")),
            _ => positional.push(PathBuf::from(arg)),
        }
    }
    if positional.len() != 2 {
        return Err("expected <input.html> <output.pdf>".to_string());
    }
    let output = positional.pop().unwrap();
    let input = positional.pop().unwrap();
    let width_px = w.ok_or("missing --page-width-px")?;
    let height_px = h.ok_or("missing --page-height-px")?;
    let margin_px = m.ok_or("missing --margin-px")?;
    if width_px <= 0.0 || height_px <= 0.0 {
        return Err("page width and height must be positive".to_string());
    }
    Ok(Args { input, output, width_px, height_px, margin_px, geometry, diagnostics, metrics, dump_html })
}

// ---------------------------------------------------------------- config (as rkhead)

fn default_config(width_px: f32, height_px: f32, margin_px: f32) -> Config {
    Config {
        page_size: PageSize { width: width_px * PX_TO_PT, height: height_px * PX_TO_PT },
        margin: Margin::uniform(margin_px * PX_TO_PT),
        ..Config::default()
    }
}

fn page_defaults(config: &Config) -> PageDefaults {
    let size = if config.landscape { config.page_size.landscape() } else { config.page_size };
    let mut page_box = PageBox::new();
    page_box.width = size.width.as_pt().in_px().to_f32();
    page_box.height = size.height.as_pt().in_px().to_f32();
    PageDefaults::builder().page_box(page_box).build()
}

fn page_stylesheet(config: &Config) -> String {
    let margin = config.margin;
    format!("@page {{ margin: {}pt {}pt {}pt {}pt; }}", margin.top, margin.right, margin.bottom, margin.left)
}

// ---------------------------------------------------------------- sandboxed files (as rkhead)

#[derive(Clone)]
pub struct BaseDirectoryProvider {
    root: PathBuf,
    max_bytes: u64,
}

impl BaseDirectoryProvider {
    fn for_input(input: &Path) -> Result<Self, String> {
        let parent = input.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or_else(|| Path::new("."));
        let root = parent.canonicalize().map_err(|e| format!("{}: {}", parent.display(), e))?;
        if !root.is_dir() {
            return Err(format!("{} is not a directory", parent.display()));
        }
        Ok(Self { root, max_bytes: raikiri_html::DEFAULT_MAX_RESOURCE_BYTES })
    }

    fn document_url(&self, input: &Path) -> Result<Url, String> {
        let name = input.file_name().ok_or_else(|| format!("{} is not a file", input.display()))?;
        Url::from_file_path(self.root.join(name)).map_err(|()| format!("{} has no file URL", input.display()))
    }

    fn resolve(&self, url: &Url) -> Result<PathBuf, NetworkError> {
        if url.scheme() != "file" {
            return Err(NetworkError::Other(format!("only file:// resources are read, got {url}")));
        }
        let local = matches!(url.host_str(), None | Some("") | Some("localhost"));
        let path = url
            .to_file_path()
            .ok()
            .filter(|_| local)
            .ok_or_else(|| NetworkError::Other(format!("invalid file URL: {url}")))?;
        let path = path.canonicalize().map_err(NetworkError::Io)?;
        if !path.starts_with(&self.root) {
            return Err(NetworkError::Other(format!("{url} is outside {}", self.root.display())));
        }
        Ok(path)
    }
}

impl NetworkProvider for BaseDirectoryProvider {
    fn fetch_one_hop(&self, request: Request) -> Result<FetchOutcome, NetworkError> {
        let path = self.resolve(&request.url)?;
        let bytes = read_capped(&path, self.max_bytes)?;
        Ok(FetchOutcome::Body(
            FetchedResource::new(bytes.into(), request.url).content_type(content_type(&path).map(str::to_string)),
        ))
    }
}

fn read_capped(path: &Path, max_bytes: u64) -> Result<Vec<u8>, NetworkError> {
    let file = std::fs::File::open(path).map_err(NetworkError::Io)?;
    let mut bytes = Vec::new();
    file.take(max_bytes.saturating_add(1)).read_to_end(&mut bytes).map_err(NetworkError::Io)?;
    if bytes.len() as u64 > max_bytes {
        return Err(NetworkError::Other(format!("{} exceeds {max_bytes} bytes", path.display())));
    }
    Ok(bytes)
}

fn content_type(path: &Path) -> Option<&'static str> {
    let extension = path.extension()?.to_str()?.to_ascii_lowercase();
    Some(match extension.as_str() {
        "css" => "text/css",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "svg" => "image/svg+xml",
        "ttf" => "font/ttf",
        "otf" => "font/otf",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        _ => return None,
    })
}

struct OptionalImages<'a, R>(&'a R);

impl<R: ReplacedResolver> ReplacedResolver for OptionalImages<'_, R> {
    fn resolve(&self, request: ResolverRequest<'_>) -> Result<ResolvedIntrinsic, ResolverError> {
        Ok(self.0.resolve(request).unwrap_or_else(|error| {
            ResolvedIntrinsic::new(IntrinsicBox::new(0.0, 0.0), ResolveDisposition::Fallback { reason: error.to_string() })
        }))
    }
}

// ---------------------------------------------------------------- serialization

/// The live DOM as an HTML document string, with the doctype its quirks mode needs.
pub fn serialize_document(doc: &Document) -> Result<String, String> {
    let markup = doc.serialize_inner_html(doc.root_index())?;
    let doctype = match doc.quirks_mode() {
        QuirksMode::NoQuirks => "<!DOCTYPE html>",
        QuirksMode::LimitedQuirks => {
            "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.01 Transitional//EN\" \"http://www.w3.org/TR/html4/loose.dtd\">"
        }
        _ => "",
    };
    Ok(format!("{doctype}{markup}"))
}

/// Serialization of a clone of `doc` whose connected elements carry STAMP = arena index.
/// Elements inside <svg>/<math> are not stamped (they never get CSS boxes of their own).
pub fn stamped_html(doc: &Document) -> Result<String, String> {
    let mut clone = doc.clone();
    let mut elements = Vec::new();
    let mut stack = vec![clone.root_index()];
    while let Some(i) = stack.pop() {
        let Some(node) = clone.get_node(i) else { continue };
        if node.kind() == NodeKind::Element {
            elements.push(i);
            let ns = clone.element_namespace_uri(i).unwrap_or("");
            if ns == SVG_NS || ns == MATHML_NS {
                continue;
            }
        }
        stack.extend(node.children.iter().copied());
    }
    for i in elements {
        clone.set_element_attribute(i, STAMP, i.to_string())?;
    }
    serialize_document(&clone)
}

// ---------------------------------------------------------------- layout

#[derive(Clone, Copy, Debug, Default)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
    pub page: usize,
}

pub struct Snapshot {
    /// Live arena index -> border box (CSS px; y is page-local plus the heights of the
    /// pages before), first page the element appears on, union of its fragments there.
    pub rects: HashMap<usize, Rect>,
    pub geometry: serde_json::Value,
    pub warnings: Vec<(String, String)>,
    pub pages: usize,
    pub ms: f64,
}

pub struct Pipeline {
    pub input: PathBuf,
    pub base_dir: PathBuf,
    pub document_url: Url,
    pub config: Config,
    pub width_px: f32,
    pub height_px: f32,
    files: BaseDirectoryProvider,
    images: raikiri_net::ImageResolver<BaseDirectoryProvider>,
    svg_rendering: SvgRendering,
    svg_raster_scale: f32,
}

fn round3(v: f32) -> f64 {
    ((v as f64) * 1000.0).round() / 1000.0
}

fn node_label(dom: &raikiri_html::DomView<'_>, node: NodeId) -> Option<(String, String, String)> {
    let tag = dom.local_name(node)?.to_string();
    let id = dom.attr(node, "id").unwrap_or("").to_string();
    let class = dom.attr(node, "class").unwrap_or("");
    let mut label = tag.clone();
    if !id.is_empty() {
        label.push('#');
        label.push_str(&id);
    }
    for c in class.split_whitespace() {
        label.push('.');
        label.push_str(c);
    }
    Some((label, tag, id))
}

fn warning_kind_name(debug: &str) -> String {
    let end = debug.find(|c: char| !(c.is_ascii_alphanumeric() || c == '_')).unwrap_or(debug.len());
    debug[..end].to_string()
}

impl Pipeline {
    pub fn new(args: &Args) -> Result<Self, String> {
        let files = BaseDirectoryProvider::for_input(&args.input)?;
        let document_url = files.document_url(&args.input)?;
        let images = raikiri_net::ImageResolver::new(files.clone());
        let defaults = fulgur_raikiri::RenderOptions::default();
        Ok(Self {
            input: args.input.clone(),
            base_dir: files.root.clone(),
            document_url,
            config: default_config(args.width_px, args.height_px, args.margin_px),
            width_px: args.width_px,
            height_px: args.height_px,
            files,
            images,
            svg_rendering: defaults.svg_rendering,
            svg_raster_scale: defaults.svg_raster_scale,
        })
    }

    /// Reads a classic script's source for `src` (relative to the document), sandboxed to the
    /// input directory like every other resource.
    pub fn read_script(&self, src: &str) -> Result<String, String> {
        let url = self.document_url.join(src).map_err(|e| format!("{src}: {e}"))?;
        self.read_script_url(&url)
    }

    pub fn read_script_url(&self, url: &Url) -> Result<String, String> {
        let path = self.files.resolve(url).map_err(|e| format!("{url}: {e}"))?;
        let bytes = read_capped(&path, self.files.max_bytes).map_err(|e| format!("{url}: {e}"))?;
        String::from_utf8(bytes).map_err(|_| format!("{url}: not UTF-8"))
    }

    /// Parses and lays out `html` exactly as fulgur-raikiri does for the PDF.
    pub fn layout_html(&self, html: &str) -> Result<Snapshot, String> {
        let start = Instant::now();
        let resolver = OptionalImages(&self.images);
        let resources = RenderResources::new()
            .replaced_resolver(&resolver)
            .image_pixel_source(&self.images)
            .stylesheet(DEFAULT_FONT_STYLESHEET)
            .stylesheet(page_stylesheet(&self.config))
            .network_provider(&self.files)
            .base_url(self.document_url.clone())
            .border_width_device_scale(Some(1.0));
        let document =
            raikiri_html::parse_html_with_resources(html.as_bytes(), &resources).map_err(|e| e.to_string())?;
        let layout_options = LayoutOptions::new()
            .resources(&resources)
            .svg_rendering(self.svg_rendering)
            .svg_raster_scale(self.svg_raster_scale);
        let status = raikiri_html::layout(&document, page_defaults(&self.config), LayoutConfig::default(), layout_options)
            .map_err(|e| e.to_string())?;
        let LayoutStatus::Completed(result) = status else {
            return Err("Raikiri layout was aborted or did not complete".to_string());
        };

        let mut rects: HashMap<usize, Rect> = HashMap::new();
        let mut pages_json: Vec<serde_json::Value> = Vec::new();
        let mut y_offset = 0.0f64;
        let mut pages = 0usize;
        for (index, page) in result.pages().enumerate() {
            pages += 1;
            let geometry = page.geometry();
            let dom = page.dom();
            let mut boxes: Vec<serde_json::Value> = Vec::new();
            for fragment in page.fragments() {
                if matches!(fragment.kind(), FragmentKind::Text) {
                    continue;
                }
                let node = fragment.node();
                let rect = fragment.rect();
                if let Some(live) = dom.attr(node, STAMP).and_then(|s| s.parse::<usize>().ok()) {
                    let r = Rect {
                        x: rect.x as f64,
                        y: rect.y as f64 + y_offset,
                        w: rect.width as f64,
                        h: rect.height as f64,
                        page: index,
                    };
                    match rects.entry(live) {
                        Entry::Vacant(slot) => {
                            slot.insert(r);
                        }
                        Entry::Occupied(mut slot) => {
                            let old = slot.get_mut();
                            if old.page == index {
                                let x0 = old.x.min(r.x);
                                let y0 = old.y.min(r.y);
                                let x1 = (old.x + old.w).max(r.x + r.w);
                                let y1 = (old.y + old.h).max(r.y + r.h);
                                *old = Rect { x: x0, y: y0, w: x1 - x0, h: y1 - y0, page: index };
                            }
                        }
                    }
                }
                let Some((label, tag, id)) = node_label(&dom, node) else { continue };
                boxes.push(serde_json::json!({
                    "node": label, "tag": tag, "id": id,
                    "x": round3(rect.x), "y": round3(rect.y), "w": round3(rect.width), "h": round3(rect.height),
                }));
            }
            pages_json.push(serde_json::json!({
                "index": index,
                "width": round3(geometry.page_box.width),
                "height": round3(geometry.page_box.height),
                "boxes": boxes,
            }));
            y_offset += geometry.page_box.height as f64;
        }

        let first_dom = result.page(0).map(|p| p.dom());
        let mut warnings: Vec<(String, String)> = Vec::new();
        for w in result.warnings() {
            let debug = format!("{:?}", w.kind);
            let name = warning_kind_name(&debug);
            let mut message = w.details.clone();
            if debug != name {
                message.push_str(&format!(" ({debug})"));
            }
            if let (Some(node), Some(dom)) = (w.node_id, first_dom.as_ref()) {
                if let Some((label, _, _)) = node_label(dom, node) {
                    message.push_str(&format!(" [node {label}]"));
                }
            }
            warnings.push((format!("raikiri:{name}"), message));
        }
        Ok(Snapshot {
            rects,
            geometry: serde_json::json!({ "pages": pages_json }),
            warnings,
            pages,
            ms: start.elapsed().as_secs_f64() * 1000.0,
        })
    }

    /// Layout of the live DOM for script geometry queries.
    pub fn layout_live(&self, doc: &Document) -> Result<Snapshot, String> {
        let html = stamped_html(doc)?;
        self.layout_html(&html)
    }

    /// The PDF, through the same fulgur-raikiri path rkhead uses (render_html_with_options
    /// with the input directory as the sandboxed base directory).
    pub fn render_pdf(&self, html: &str) -> Result<Vec<u8>, String> {
        let assets = AssetBundle::new();
        let options = fulgur_raikiri::RenderOptions {
            assets: Some(&assets),
            system_fonts: true,
            svg_rendering: self.svg_rendering,
            svg_raster_scale: self.svg_raster_scale,
        };
        self.config
            .validate()
            .and_then(|()| {
                fulgur_raikiri::render_html_with_options(html, Some(self.base_dir.as_path()), &self.config, &options)
            })
            .map_err(|e| e.to_string())
    }
}

// ---------------------------------------------------------------- output helpers

pub fn write_json(path: &Path, value: &serde_json::Value) -> Result<(), String> {
    let text = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
    std::fs::write(path, text).map_err(|e| format!("{}: {}", path.display(), e))
}

pub fn diagnostics_json(items: &[(String, String)]) -> serde_json::Value {
    let list: Vec<serde_json::Value> =
        items.iter().map(|(k, m)| serde_json::json!({ "kind": k, "message": m })).collect();
    serde_json::json!({ "warnings": list })
}

/// Peak resident set size of this process in KiB (Linux VmHWM), if readable.
pub fn peak_rss_kib() -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|l| l.starts_with("VmHWM:"))?;
    line.split_whitespace().nth(1)?.parse().ok()
}

pub fn ms_since(t: Instant) -> f64 {
    t.elapsed().as_secs_f64() * 1000.0
}
