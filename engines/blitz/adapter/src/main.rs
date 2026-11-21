use std::fs::File;
use std::io::BufWriter;
use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

use anyrender::{AntiAliasing, ImageRenderer, PaintScene};
use anyrender_vello_cpu::VelloCpuImageRenderer;
use blitz_dom::util::Color;
use blitz_dom::{BaseDocument, DocumentConfig};
use blitz_html::HtmlDocument;
use blitz_paint::paint_scene;
use blitz_traits::net::{Bytes, NetHandler, NetProvider, Request, Url};
use blitz_traits::shell::{ColorScheme, Viewport};
use peniko::Fill;
use peniko::kurbo::Rect;
use serde_json::{Value, json};

const MAX_RESOLVE_PASSES: usize = 64;

struct Options {
    input: PathBuf,
    output: PathBuf,
    width: u32,
    height: u32,
    geometry: Option<PathBuf>,
    diagnostics: Option<PathBuf>,
}

struct FileNetProvider {
    fetches: AtomicUsize,
}

impl FileNetProvider {
    fn new() -> Self {
        Self {
            fetches: AtomicUsize::new(0),
        }
    }

    fn fetch_count(&self) -> usize {
        self.fetches.load(Ordering::SeqCst)
    }
}

fn load_url(url: &Url) -> Result<Vec<u8>, String> {
    match url.scheme() {
        "file" => {
            let path = url
                .to_file_path()
                .map_err(|_| format!("invalid file url: {url}"))?;
            std::fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))
        }
        "data" => {
            let data = data_url::DataUrl::process(url.as_str()).map_err(|e| e.to_string())?;
            let (body, _) = data.decode_to_vec().map_err(|e| e.to_string())?;
            Ok(body)
        }
        other => Err(format!("scheme '{other}' not allowed (no network): {url}")),
    }
}

impl NetProvider for FileNetProvider {
    fn fetch(&self, _doc_id: usize, request: Request, handler: Box<dyn NetHandler>) {
        self.fetches.fetch_add(1, Ordering::SeqCst);
        let url = request.url.clone();
        match load_url(&url) {
            Ok(bytes) => handler.bytes(url.to_string(), Bytes::from(bytes)),
            Err(err) => {
                eprintln!("adapter-blitz: resource load failed: {err}");
                handler.error(url.to_string(), err);
            }
        }
    }
}

fn parse_px(name: &str, value: &str) -> Result<f64, String> {
    let v: f64 = value
        .parse()
        .map_err(|_| format!("invalid value for {name}: {value}"))?;
    if !v.is_finite() || v < 0.0 {
        return Err(format!("invalid value for {name}: {value}"));
    }
    Ok(v)
}

fn parse_dimension(name: &str, value: &str) -> Result<u32, String> {
    let v = parse_px(name, value)?.round();
    if v < 1.0 || v > 65535.0 {
        return Err(format!("{name} out of range (1..=65535): {value}"));
    }
    Ok(v as u32)
}

fn parse_args(args: &[String]) -> Result<Options, String> {
    let usage = "usage: adapter-blitz render <input.html> <output.png> --page-width-px <W> --page-height-px <H> --margin-px <M> [--geometry <geometry.json>] [--diagnostics <diag.json>]";
    if args.first().map(String::as_str) != Some("render") {
        return Err(usage.to_string());
    }
    let mut positional: Vec<String> = Vec::new();
    let mut width: Option<u32> = None;
    let mut height: Option<u32> = None;
    let mut margin: Option<f64> = None;
    let mut geometry: Option<PathBuf> = None;
    let mut diagnostics: Option<PathBuf> = None;

    let mut i = 1;
    while i < args.len() {
        let arg = &args[i];
        if let Some(flag) = arg.strip_prefix("--") {
            let (name, value) = match flag.split_once('=') {
                Some((n, v)) => (n.to_string(), v.to_string()),
                None => {
                    i += 1;
                    let v = args
                        .get(i)
                        .ok_or_else(|| format!("missing value for --{flag}"))?;
                    (flag.to_string(), v.clone())
                }
            };
            match name.as_str() {
                "page-width-px" => width = Some(parse_dimension("--page-width-px", &value)?),
                "page-height-px" => height = Some(parse_dimension("--page-height-px", &value)?),
                "margin-px" => margin = Some(parse_px("--margin-px", &value)?),
                "geometry" => geometry = Some(PathBuf::from(value)),
                "diagnostics" => diagnostics = Some(PathBuf::from(value)),
                _ => return Err(format!("unknown option --{name}\n{usage}")),
            }
        } else {
            positional.push(arg.clone());
        }
        i += 1;
    }

    if positional.len() != 2 {
        return Err(usage.to_string());
    }
    let _ = margin.ok_or_else(|| format!("missing --margin-px\n{usage}"))?;
    let width = width.ok_or_else(|| format!("missing --page-width-px\n{usage}"))?;
    let height = height.ok_or_else(|| format!("missing --page-height-px\n{usage}"))?;
    let mut positional = positional.into_iter();
    let input = PathBuf::from(positional.next().unwrap_or_default());
    let output = PathBuf::from(positional.next().unwrap_or_default());

    Ok(Options {
        input,
        output,
        width,
        height,
        geometry,
        diagnostics,
    })
}

fn write_png(path: &PathBuf, buffer: &[u8], width: u32, height: u32) -> Result<(), String> {
    let file = File::create(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut encoder = png::Encoder::new(BufWriter::new(file), width, height);
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    let mut writer = encoder.write_header().map_err(|e| e.to_string())?;
    writer.write_image_data(buffer).map_err(|e| e.to_string())?;
    writer.finish().map_err(|e| e.to_string())?;
    Ok(())
}

fn node_label(tag: &str, id: &str, class: &str) -> String {
    let mut label = tag.to_string();
    if !id.is_empty() {
        label.push('#');
        label.push_str(id);
    }
    for c in class.split_ascii_whitespace() {
        label.push('.');
        label.push_str(c);
    }
    label
}

fn collect_geometry(doc: &BaseDocument, width: u32, height: u32) -> Value {
    let mut boxes: Vec<Value> = Vec::new();
    let mut stack = vec![doc.root_node().id];
    while let Some(node_id) = stack.pop() {
        let Some(node) = doc.get_node(node_id) else {
            continue;
        };
        if node.is_element()
            && let Some(el) = node.element_data()
            && let Some(rect) = doc.get_client_bounding_rect(node_id)
        {
            let tag = el.name.local.to_string();
            let id = el.attr(blitz_dom::local_name!("id")).unwrap_or("");
            let class = el.attr(blitz_dom::local_name!("class")).unwrap_or("");
            boxes.push(json!({
                "node": node_label(&tag, id, class),
                "tag": tag,
                "id": id,
                "x": rect.x,
                "y": rect.y,
                "w": rect.width,
                "h": rect.height,
            }));
        }
        for &child in node.children.iter().rev() {
            stack.push(child);
        }
    }
    json!({
        "pages": [{
            "index": 0,
            "width": width,
            "height": height,
            "boxes": boxes,
        }]
    })
}

fn write_json(path: &PathBuf, value: &Value) -> Result<(), String> {
    let text = serde_json::to_string(value).map_err(|e| e.to_string())?;
    std::fs::write(path, text).map_err(|e| format!("{}: {e}", path.display()))
}

fn run(opts: &Options) -> Result<(), String> {
    let input = std::fs::canonicalize(&opts.input)
        .map_err(|e| format!("{}: {e}", opts.input.display()))?;
    let html_bytes = std::fs::read(&input).map_err(|e| format!("{}: {e}", input.display()))?;
    let html = String::from_utf8_lossy(&html_bytes).into_owned();
    let base_url = Url::from_file_path(&input)
        .map_err(|_| format!("cannot build file url for {}", input.display()))?;

    let width = opts.width;
    let height = opts.height;
    let net = Arc::new(FileNetProvider::new());

    let config = DocumentConfig {
        base_url: Some(base_url.to_string()),
        net_provider: Some(Arc::clone(&net) as Arc<dyn NetProvider>),
        viewport: Some(Viewport::new(width, height, 1.0, ColorScheme::Light)),
        ..Default::default()
    };

    let mut doc: BaseDocument = HtmlDocument::from_html(&html, config).into();

    let mut settled = false;
    for _ in 0..MAX_RESOLVE_PASSES {
        let before = net.fetch_count();
        doc.resolve(0.0);
        if net.fetch_count() == before && !doc.has_pending_critical_resources() {
            settled = true;
            break;
        }
    }
    if !settled {
        eprintln!(
            "adapter-blitz: warning: resource loading did not settle after {MAX_RESOLVE_PASSES} passes"
        );
    }
    doc.resolve(0.0);

    let mut renderer = VelloCpuImageRenderer::new(width, height);
    let mut buffer: Vec<u8> = Vec::new();
    renderer.render_to_vec(
        |scene| {
            scene.fill(
                Fill::NonZero,
                Default::default(),
                Color::WHITE,
                Default::default(),
                &Rect::new(0.0, 0.0, width as f64, height as f64),
                AntiAliasing::Enabled,
            );
            paint_scene(scene, &mut doc, 1.0, width, height, 0, 0);
        },
        &mut buffer,
    );

    let expected = width as usize * height as usize * 4;
    if buffer.len() != expected {
        return Err(format!(
            "renderer produced {} bytes, expected {expected}",
            buffer.len()
        ));
    }

    write_png(&opts.output, &buffer, width, height)?;

    if let Some(path) = &opts.geometry {
        write_json(path, &collect_geometry(&doc, width, height))?;
    }
    if let Some(path) = &opts.diagnostics {
        write_json(path, &json!({ "unsupported": true }))?;
    }
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let opts = match parse_args(&args) {
        Ok(opts) => opts,
        Err(err) => {
            eprintln!("adapter-blitz: {err}");
            return ExitCode::from(2);
        }
    };
    match run(&opts) {
        Ok(()) => {
            println!("{{\"pages\":1}}");
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("adapter-blitz: {err}");
            ExitCode::from(2)
        }
    }
}
