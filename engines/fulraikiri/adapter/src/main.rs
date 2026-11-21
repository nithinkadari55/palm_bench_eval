use fulgur_core::units::F32Units;
use fulgur_core::{AssetBundle, Config, Margin, PageSize};
use raikiri_html::{
    FragmentKind, LayoutConfig, LayoutOptions, LayoutStatus, PageDefaults, RenderResources,
    SvgRendering,
};
use raikiri_traits::net::{FetchOutcome, FetchedResource, NetworkError, NetworkProvider, Request};
use raikiri_traits::{
    IntrinsicBox, NodeId, PageBox, ReplacedResolver, ResolveDisposition, ResolvedIntrinsic,
    ResolverError, ResolverRequest,
};
use std::ffi::OsString;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use url::Url;

const PX_TO_PT: f32 = 0.75;

const USAGE: &str = "usage: adapter-fulraikiri render <input.html> <output.pdf> \
--page-width-px <W> --page-height-px <H> --margin-px <M> \
[--geometry <geometry.json>] [--diagnostics <diag.json>]";

const DEFAULT_FONT_STYLESHEET: &str = "@layer { :where(html) { font-family: sans-serif } }";

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

fn default_config(width_px: f32, height_px: f32, margin_px: f32) -> Config {
    Config {
        page_size: PageSize {
            width: width_px * PX_TO_PT,
            height: height_px * PX_TO_PT,
        },
        margin: Margin::uniform(margin_px * PX_TO_PT),
        ..Config::default()
    }
}

fn page_defaults(config: &Config) -> PageDefaults {
    let size = if config.landscape {
        config.page_size.landscape()
    } else {
        config.page_size
    };
    let mut page_box = PageBox::new();
    page_box.width = size.width.as_pt().in_px().to_f32();
    page_box.height = size.height.as_pt().in_px().to_f32();
    PageDefaults::builder().page_box(page_box).build()
}

fn page_stylesheet(config: &Config) -> String {
    let margin = config.margin;
    format!(
        "@page {{ margin: {}pt {}pt {}pt {}pt; }}",
        margin.top, margin.right, margin.bottom, margin.left,
    )
}

#[derive(Clone)]
struct BaseDirectoryProvider {
    root: PathBuf,
    max_bytes: u64,
}

impl BaseDirectoryProvider {
    fn for_input(input: &Path) -> Result<Self, String> {
        let parent = input
            .parent()
            .filter(|path| !path.as_os_str().is_empty())
            .unwrap_or_else(|| Path::new("."));
        let root = parent
            .canonicalize()
            .map_err(|e| format!("{}: {}", parent.display(), e))?;
        if !root.is_dir() {
            return Err(format!("{} is not a directory", parent.display()));
        }
        Ok(Self {
            root,
            max_bytes: raikiri_html::DEFAULT_MAX_RESOURCE_BYTES,
        })
    }

    fn document_url(&self, input: &Path) -> Result<Url, String> {
        let name = input
            .file_name()
            .ok_or_else(|| format!("{} is not a file", input.display()))?;
        Url::from_file_path(self.root.join(name))
            .map_err(|()| format!("{} has no file URL", input.display()))
    }

    fn resolve(&self, url: &Url) -> Result<PathBuf, NetworkError> {
        if url.scheme() != "file" {
            return Err(NetworkError::Other(format!(
                "only file:// resources are read, got {url}"
            )));
        }
        let local = matches!(url.host_str(), None | Some("") | Some("localhost"));
        let path = url
            .to_file_path()
            .ok()
            .filter(|_| local)
            .ok_or_else(|| NetworkError::Other(format!("invalid file URL: {url}")))?;
        let path = path.canonicalize().map_err(NetworkError::Io)?;
        if !path.starts_with(&self.root) {
            return Err(NetworkError::Other(format!(
                "{url} is outside {}",
                self.root.display()
            )));
        }
        Ok(path)
    }
}

impl NetworkProvider for BaseDirectoryProvider {
    fn fetch_one_hop(&self, request: Request) -> Result<FetchOutcome, NetworkError> {
        let path = self.resolve(&request.url)?;
        let bytes = read_capped(&path, self.max_bytes)?;
        Ok(FetchOutcome::Body(
            FetchedResource::new(bytes.into(), request.url)
                .content_type(content_type(&path).map(str::to_string)),
        ))
    }
}

fn read_capped(path: &Path, max_bytes: u64) -> Result<Vec<u8>, NetworkError> {
    let file = std::fs::File::open(path).map_err(NetworkError::Io)?;
    let mut bytes = Vec::new();
    file.take(max_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(NetworkError::Io)?;
    if bytes.len() as u64 > max_bytes {
        return Err(NetworkError::Other(format!(
            "{} exceeds {max_bytes} bytes",
            path.display()
        )));
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
            ResolvedIntrinsic::new(
                IntrinsicBox::new(0.0, 0.0),
                ResolveDisposition::Fallback {
                    reason: error.to_string(),
                },
            )
        }))
    }
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
    let end = debug
        .find(|c: char| !(c.is_ascii_alphanumeric() || c == '_'))
        .unwrap_or(debug.len());
    debug[..end].to_string()
}

struct Analysis {
    geometry: serde_json::Value,
    warnings: Vec<(String, String)>,
}

fn analyze(
    input: &Path,
    config: &Config,
    svg_rendering: SvgRendering,
    svg_raster_scale: f32,
) -> Result<Analysis, String> {
    let files = BaseDirectoryProvider::for_input(input)?;
    let document_url = files.document_url(input)?;
    let network = files;
    let images = raikiri_net::ImageResolver::new(network.clone());
    let resolver = OptionalImages(&images);
    let resources = RenderResources::new()
        .replaced_resolver(&resolver)
        .image_pixel_source(&images)
        .stylesheet(DEFAULT_FONT_STYLESHEET)
        .stylesheet(page_stylesheet(config))
        .network_provider(&network)
        .base_url(document_url)
        .border_width_device_scale(Some(1.0));
    let html = std::fs::read(input).map_err(|e| format!("{}: {}", input.display(), e))?;
    let document = raikiri_html::parse_html_with_resources(html.as_slice(), &resources)
        .map_err(|e| e.to_string())?;
    let layout_options = LayoutOptions::new()
        .resources(&resources)
        .svg_rendering(svg_rendering)
        .svg_raster_scale(svg_raster_scale);
    let status = raikiri_html::layout(
        &document,
        page_defaults(config),
        LayoutConfig::default(),
        layout_options,
    )
    .map_err(|e| e.to_string())?;
    let LayoutStatus::Completed(result) = status else {
        return Err("Raikiri layout was aborted or did not complete".to_string());
    };

    let mut pages_json: Vec<serde_json::Value> = Vec::new();
    for (index, page) in result.pages().enumerate() {
        let geometry = page.geometry();
        let dom = page.dom();
        let mut boxes: Vec<serde_json::Value> = Vec::new();
        for fragment in page.fragments() {
            if matches!(fragment.kind(), FragmentKind::Text) {
                continue;
            }
            let node = fragment.node();
            let Some((label, tag, id)) = node_label(&dom, node) else {
                continue;
            };
            let rect = fragment.rect();
            boxes.push(serde_json::json!({
                "node": label,
                "tag": tag,
                "id": id,
                "x": round3(rect.x),
                "y": round3(rect.y),
                "w": round3(rect.width),
                "h": round3(rect.height),
            }));
        }
        pages_json.push(serde_json::json!({
            "index": index,
            "width": round3(geometry.page_box.width),
            "height": round3(geometry.page_box.height),
            "boxes": boxes,
        }));
    }

    let first_dom = result.page(0).map(|p| p.dom());
    let mut warnings: Vec<(String, String)> = Vec::new();
    for w in result.warnings() {
        let debug = format!("{:?}", w.kind);
        let name = warning_kind_name(&debug);
        let mut message = w.details.clone();
        if debug != name {
            message.push_str(&format!(" ({})", debug));
        }
        if let (Some(node), Some(dom)) = (w.node_id, first_dom.as_ref()) {
            if let Some((label, _, _)) = node_label(dom, node) {
                message.push_str(&format!(" [node {}]", label));
            }
        }
        warnings.push((format!("raikiri:{}", name), message));
    }

    Ok(Analysis {
        geometry: serde_json::json!({ "pages": pages_json }),
        warnings,
    })
}

fn write_json(path: &Path, value: &serde_json::Value) -> Result<(), String> {
    let text = serde_json::to_string(value).map_err(|e| e.to_string())?;
    std::fs::write(path, text).map_err(|e| format!("{}: {}", path.display(), e))
}

fn diagnostics_json(log_count: usize, extra: &[(String, String)]) -> serde_json::Value {
    let mut items: Vec<serde_json::Value> = Vec::new();
    if let Ok(w) = WARNINGS.lock() {
        for (kind, message) in w.iter().take(log_count) {
            items.push(serde_json::json!({ "kind": kind, "message": message }));
        }
    }
    for (kind, message) in extra {
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
            eprintln!("adapter-fulraikiri: {}", e);
            eprintln!("{}", USAGE);
            std::process::exit(1);
        }
    };

    if !args.input.is_file() {
        eprintln!(
            "adapter-fulraikiri: cannot read {}: not a file",
            args.input.display()
        );
        std::process::exit(1);
    }

    let config = default_config(args.width_px, args.height_px, args.margin_px);
    let assets = AssetBundle::new();
    let defaults = fulgur_raikiri::RenderOptions::default();
    let options = fulgur_raikiri::RenderOptions {
        assets: Some(&assets),
        system_fonts: true,
        svg_rendering: defaults.svg_rendering,
        svg_raster_scale: defaults.svg_raster_scale,
    };

    #[cfg(unix)]
    let isolator = StdoutIsolator::install();

    let pdf = match config
        .validate()
        .and_then(|()| fulgur_raikiri::render_with_options(&args.input, &config, &options))
    {
        Ok(p) => p,
        Err(e) => {
            eprintln!("adapter-fulraikiri: render failed: {}", e);
            if let Some(ref d) = args.diagnostics {
                let count = warning_count();
                let _ = write_json(d, &diagnostics_json(count, &[]));
            }
            std::process::exit(2);
        }
    };
    let log_count = warning_count();

    if let Err(e) = std::fs::write(&args.output, &pdf) {
        eprintln!(
            "adapter-fulraikiri: cannot write {}: {}",
            args.output.display(),
            e
        );
        std::process::exit(1);
    }

    if args.geometry.is_some() || args.diagnostics.is_some() {
        let analysis = match analyze(
            &args.input,
            &config,
            options.svg_rendering,
            options.svg_raster_scale,
        ) {
            Ok(a) => a,
            Err(e) => {
                eprintln!("adapter-fulraikiri: layout for geometry/diagnostics failed: {}", e);
                if let Some(ref d) = args.diagnostics {
                    let _ = write_json(d, &diagnostics_json(log_count, &[]));
                }
                std::process::exit(2);
            }
        };
        if let Some(ref g) = args.geometry {
            if let Err(e) = write_json(g, &analysis.geometry) {
                eprintln!("adapter-fulraikiri: cannot write geometry: {}", e);
                std::process::exit(1);
            }
        }
        if let Some(ref d) = args.diagnostics {
            if let Err(e) = write_json(d, &diagnostics_json(log_count, &analysis.warnings)) {
                eprintln!("adapter-fulraikiri: cannot write diagnostics: {}", e);
                std::process::exit(1);
            }
        }
    }

    #[cfg(unix)]
    drop(isolator);

    if let Ok(doc) = lopdf::Document::load_mem(&pdf) {
        println!("{{\"pages\":{}}}", doc.get_pages().len());
    }
}
