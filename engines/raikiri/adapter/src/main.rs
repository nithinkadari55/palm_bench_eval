use std::path::PathBuf;
use std::process;

use anyrender::render_to_buffer;
use anyrender_vello_cpu::VelloCpuImageRenderer;
use raikiri::{
    CascadeOptions, MediaContext, MediaType, NetworkProvider, NodeKind, PageBox, PageContextQuery,
    ParseOptions, RasterBufferBudget, RenderError, RenderWarning, Url, build_cascaded_with_options,
    build_page_scene, build_rule_tree,
};
use raikiri_net::{FileNetworkProvider, ImageResolver};
use raikiri_style::property::BackgroundImage;
use raikiri_traits::{
    IntrinsicBox, ReplacedResolver, ResolveDisposition, ResolvedIntrinsic, ResolverError, ResolverRequest,
};

struct OptionalImages<'a, R>(&'a R);

impl<R: ReplacedResolver> ReplacedResolver for OptionalImages<'_, R> {
    fn resolve(&self, request: ResolverRequest<'_>) -> Result<ResolvedIntrinsic, ResolverError> {
        Ok(self.0.resolve(request).unwrap_or_else(|error| {
            ResolvedIntrinsic::new(
                IntrinsicBox::new(0.0, 0.0),
                ResolveDisposition::Fallback { reason: error.to_string() },
            )
        }))
    }
}

struct Args {
    input: PathBuf,
    output: PathBuf,
    page_width_px: f32,
    page_height_px: f32,
    geometry: Option<PathBuf>,
    diagnostics: Option<PathBuf>,
}

struct Diag {
    kind: String,
    message: String,
}

struct GeoBox {
    node: String,
    tag: String,
    id: String,
    x: f32,
    y: f32,
    w: f32,
    h: f32,
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
        return Err(format!(
            "{flag} must be a finite non-negative number, got: {raw}"
        ));
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
            "--diagnostics" => diagnostics = Some(PathBuf::from(take_value(arg, iter.next())?)),
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
    margin_px.ok_or("missing --margin-px")?;
    if page_width_px < 1.0 || page_height_px < 1.0 {
        return Err("page width and height must be at least 1 px".to_string());
    }

    Ok(Args {
        input,
        output,
        page_width_px,
        page_height_px,
        geometry,
        diagnostics,
    })
}

fn kind_name(kind_debug: &str) -> String {
    kind_debug
        .split(|c: char| c == ' ' || c == '{' || c == '(')
        .next()
        .unwrap_or("")
        .to_string()
}

fn diag_from_warning(warning: &RenderWarning) -> Diag {
    Diag {
        kind: kind_name(&format!("{:?}", warning.kind)),
        message: warning.details.clone(),
    }
}

struct FileFontLoader<'a> {
    base_url: &'a Url,
}

impl raikiri_dom::FontFaceLoader for FileFontLoader<'_> {
    fn load(&self, source: &str) -> Option<Vec<u8>> {
        let url = Url::parse(source)
            .ok()
            .or_else(|| self.base_url.join(source).ok())?;
        match url.scheme() {
            "file" => std::fs::read(url.to_file_path().ok()?).ok(),
            "data" => {
                let data = data_url::DataUrl::process(url.as_str()).ok()?;
                let decoded = data.decode_to_vec().ok()?;
                Some(decoded.0)
            }
            _ => None,
        }
    }
}

fn absolutize_img_sources(document: &mut raikiri_dom::Document, base_url: &Url) {
    let updates: Vec<_> = (0..document.node_count())
        .filter_map(|node_id| {
            let node = document.get_node(node_id)?;
            if node.tag_name() != Some("img") {
                return None;
            }
            let source = document.element_attribute(node_id, "src")?;
            if Url::parse(source).is_ok() {
                return None;
            }
            base_url
                .join(source)
                .ok()
                .map(|absolute| (node_id, absolute.to_string()))
        })
        .collect();
    for (node_id, source) in updates {
        document
            .set_element_attribute(node_id, "src", source)
            .expect("src is a valid HTML attribute name");
    }
}

fn resolve_or_warn(resolver: &dyn ReplacedResolver, absolute: &Url, diags: &mut Vec<Diag>) {
    if let Err(error) = resolver.resolve(ResolverRequest::new(absolute)) {
        diags.push(Diag {
            kind: "ImageResolveFailed".to_string(),
            message: format!("{absolute}: {error}"),
        });
    }
}

fn prepare_background_image(
    image: &mut BackgroundImage,
    base_url: &Url,
    resolver: &dyn ReplacedResolver,
    diags: &mut Vec<Diag>,
) {
    let (BackgroundImage::Url(source) | BackgroundImage::DensityUrl { url: source, .. }) = image
    else {
        return;
    };
    let Some(absolute) = Url::parse(source)
        .ok()
        .or_else(|| base_url.join(source).ok())
    else {
        return;
    };
    *source = absolute.as_str().into();
    resolve_or_warn(resolver, &absolute, diags);
}

fn prepare_background_layers(
    computed: &mut raikiri_style::ComputedValues,
    base_url: &Url,
    resolver: &dyn ReplacedResolver,
    diags: &mut Vec<Diag>,
) {
    if !computed.has_background_image() {
        return;
    }
    for layer in std::sync::Arc::make_mut(&mut computed.background_layers) {
        prepare_background_image(&mut layer.image, base_url, resolver, diags);
    }
}

fn prefetch_generated_content_images(
    document: &raikiri_dom::Document,
    cascade: &raikiri_style::CascadeResult,
    base_url: &Url,
    resolver: &dyn ReplacedResolver,
    diags: &mut Vec<Diag>,
) {
    let urls = cascade
        .pseudo
        .iter()
        .filter(|((owner, pseudo), computed)| {
            matches!(
                pseudo,
                raikiri_style::PseudoElem::Before | raikiri_style::PseudoElem::After
            ) && computed.content.iter().any(|component| {
                matches!(
                    component,
                    raikiri_style::property::ContentComponent::Image { .. }
                )
            }) && usize::try_from(owner.0).is_ok_and(|element| {
                raikiri_dom::generated_content::content_images_are_placed(
                    document, cascade, element, *pseudo,
                )
            })
        })
        .flat_map(|(_, computed)| {
            computed
                .content
                .iter()
                .filter_map(|component| match component {
                    raikiri_style::property::ContentComponent::Image { url, .. } => Some(url),
                    _ => None,
                })
                .take(raikiri_dom::generated_content::MAX_GENERATED_IMAGES)
        });
    for source in urls {
        if let Some(absolute) = Url::parse(source)
            .ok()
            .or_else(|| base_url.join(source).ok())
        {
            resolve_or_warn(resolver, &absolute, diags);
        }
    }
}

fn prepare_page_images(
    page: &mut raikiri_style::PageCascadeResult,
    base_url: &Url,
    resolver: &dyn ReplacedResolver,
    diags: &mut Vec<Diag>,
) {
    page.for_each_background_image_mut(|image| {
        prepare_background_image(image, base_url, resolver, diags)
    });
    for source in raikiri_dom::page_margin_box_content_image_urls(page) {
        if let Some(absolute) = Url::parse(&source)
            .ok()
            .or_else(|| base_url.join(&source).ok())
        {
            resolve_or_warn(resolver, &absolute, diags);
        }
    }
}

fn prepare_cascade_images(
    document: &raikiri_dom::Document,
    cascade: &mut raikiri_style::CascadeResult,
    base_url: &Url,
    resolver: &dyn ReplacedResolver,
    diags: &mut Vec<Diag>,
) {
    for computed in &mut cascade.computed {
        prepare_background_layers(computed, base_url, resolver, diags);
        prepare_background_image(&mut computed.border_image.source, base_url, resolver, diags);
        prepare_background_image(&mut computed.list_style_image, base_url, resolver, diags);
    }
    prefetch_generated_content_images(document, cascade, base_url, resolver, diags);
    prepare_page_images(&mut cascade.page, base_url, resolver, diags);
}

fn encode_png_on_white(mut rgba: Vec<u8>, width: u32, height: u32) -> Result<Vec<u8>, String> {
    let expected = (width as usize) * (height as usize) * 4;
    if rgba.len() != expected {
        return Err(format!(
            "raster buffer has {} bytes, expected {expected}",
            rgba.len()
        ));
    }
    for px in rgba.chunks_exact_mut(4) {
        let inv = 255u16 - px[3] as u16;
        for c in px.iter_mut().take(3) {
            *c = (*c as u16 + inv).min(255) as u8;
        }
        px[3] = 255;
    }
    let mut out = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut out, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder
            .write_header()
            .map_err(|e| format!("PNG header: {e}"))?;
        writer
            .write_image_data(&rgba)
            .map_err(|e| format!("PNG data: {e}"))?;
        writer.finish().map_err(|e| format!("PNG finish: {e}"))?;
    }
    Ok(out)
}

fn json_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn json_num(v: f32) -> String {
    if v.is_finite() {
        format!("{v}")
    } else {
        "0".to_string()
    }
}

fn geometry_json(width: u32, height: u32, boxes: &[GeoBox]) -> String {
    let items: Vec<String> = boxes
        .iter()
        .map(|b| {
            format!(
                "{{\"node\":{},\"tag\":{},\"id\":{},\"x\":{},\"y\":{},\"w\":{},\"h\":{}}}",
                json_str(&b.node),
                json_str(&b.tag),
                json_str(&b.id),
                json_num(b.x),
                json_num(b.y),
                json_num(b.w),
                json_num(b.h)
            )
        })
        .collect();
    format!(
        "{{\"pages\":[{{\"index\":0,\"width\":{width},\"height\":{height},\"boxes\":[{}]}}]}}\n",
        items.join(",")
    )
}

fn diagnostics_json(diags: &[Diag]) -> String {
    let items: Vec<String> = diags
        .iter()
        .map(|d| {
            format!(
                "{{\"kind\":{},\"message\":{}}}",
                json_str(&d.kind),
                json_str(&d.message)
            )
        })
        .collect();
    format!("{{\"warnings\":[{}]}}\n", items.join(","))
}

fn render(args: &Args) -> Result<(), String> {
    let input_abs = std::fs::canonicalize(&args.input)
        .map_err(|e| format!("failed to resolve {}: {e}", args.input.display()))?;
    let bytes = std::fs::read(&input_abs)
        .map_err(|e| format!("failed to read {}: {e}", input_abs.display()))?;
    let doc_url = Url::from_file_path(&input_abs)
        .map_err(|()| format!("cannot convert {} to a file URL", input_abs.display()))?;

    let size = RasterBufferBudget::new()
        .reserve_pixels(
            args.page_width_px.round() as u32,
            args.page_height_px.round() as u32,
        )
        .map_err(|e| format!("raster size rejected: {e}"))?;
    let width = size.width();
    let height = size.height();

    let network = FileNetworkProvider::default();
    let network_ref: &dyn NetworkProvider = &network;
    let options = ParseOptions::new()
        .network(Some(network_ref))
        .base_url(Some(doc_url.clone()));
    let mut uncascaded =
        raikiri::parse(&bytes[..], &options).map_err(|e| format!("HTML parse failed: {e}"))?;

    let mut diags: Vec<Diag> = uncascaded.warnings.iter().map(diag_from_warning).collect();

    let media_context = MediaContext::with_viewport(MediaType::Screen, width, height);
    let base_url =
        raikiri_html::effective_document_base_url(&uncascaded, Some(&doc_url)).unwrap_or(doc_url);
    absolutize_img_sources(&mut uncascaded.dom, &base_url);

    let font_faces = build_rule_tree(&uncascaded).font_faces_for(&media_context);
    let shared_fonts = raikiri_dom::system_font_collection();
    if font_faces.is_empty() {
        uncascaded.dom.set_font_collection(shared_fonts);
    } else {
        let loader = FileFontLoader {
            base_url: &base_url,
        };
        let (fonts, report) =
            raikiri_dom::build_inline_document_fonts(&shared_fonts, &font_faces, &loader);
        for family in &report.skipped {
            diags.push(Diag {
                kind: "FontFaceSkipped".to_string(),
                message: format!("@font-face family {family:?} has no usable source"),
            });
        }
        uncascaded.dom.set_font_collection(fonts);
    }

    let mut cascade_options = CascadeOptions::default();
    cascade_options.border_width_device_scale = Some(1.0);
    let mut cascade = build_cascaded_with_options(
        &uncascaded,
        &media_context,
        &PageContextQuery::default(),
        &[],
        &cascade_options,
    )
    .map_err(|e| format!("cascade failed: {e}"))?;

    let image_resolver = ImageResolver::new(FileNetworkProvider::default());
    prepare_cascade_images(
        &uncascaded.dom,
        &mut cascade,
        &base_url,
        &image_resolver,
        &mut diags,
    );
    uncascaded
        .dom
        .prepare_list_marker_images(&cascade, &image_resolver, Some(&base_url));

    let mut page_box = PageBox::new();
    page_box.width = width as f32;
    page_box.height = height as f32;
    raikiri_dom::layout_single_page_with_resolver_and_base_url(
        &mut uncascaded.dom,
        &cascade,
        page_box,
        &OptionalImages(&image_resolver),
        Some(&base_url),
    )
    .map_err(|e| format!("layout failed: {e}"))?;

    let dom = &uncascaded.dom;
    let mut paint_result: Result<Vec<RenderWarning>, RenderError> = Ok(Vec::new());
    let rgba = render_to_buffer::<VelloCpuImageRenderer, _>(
        |painter| {
            paint_result = raikiri_paint::paint_single_page_with_images_and_warnings(
                painter,
                dom,
                &cascade,
                page_box,
                &image_resolver,
            );
        },
        width,
        height,
    );
    let paint_warnings = paint_result.map_err(|e| format!("paint failed: {e}"))?;
    diags.extend(paint_warnings.iter().map(diag_from_warning));

    let png_bytes = encode_png_on_white(rgba, width, height)?;
    std::fs::write(&args.output, &png_bytes)
        .map_err(|e| format!("failed to write {}: {e}", args.output.display()))?;

    if let Some(path) = &args.geometry {
        let scene = build_page_scene(dom, &cascade, page_box);
        let (ox, oy) = scene.body_offset_pt;
        let mut boxes: Vec<GeoBox> = Vec::new();
        for (node_id, fragments) in &scene.fragments {
            let idx = node_id.0 as usize;
            let Some(node) = dom.get_node(idx) else {
                continue;
            };
            if !matches!(node.kind(), NodeKind::Element) {
                continue;
            }
            let tag = node.tag_name().unwrap_or("").to_ascii_lowercase();
            let id = dom.element_attribute(idx, "id").unwrap_or("").to_string();
            let class = dom.element_attribute(idx, "class").unwrap_or("");
            let mut label = tag.clone();
            if !id.is_empty() {
                label.push('#');
                label.push_str(&id);
            }
            for cls in class.split_ascii_whitespace() {
                label.push('.');
                label.push_str(cls);
            }
            for fragment in fragments {
                boxes.push(GeoBox {
                    node: label.clone(),
                    tag: tag.clone(),
                    id: id.clone(),
                    x: fragment.x + ox,
                    y: fragment.y + oy,
                    w: fragment.width,
                    h: fragment.height,
                });
            }
        }
        std::fs::write(path, geometry_json(width, height, &boxes))
            .map_err(|e| format!("failed to write {}: {e}", path.display()))?;
    }

    if let Some(path) = &args.diagnostics {
        std::fs::write(path, diagnostics_json(&diags))
            .map_err(|e| format!("failed to write {}: {e}", path.display()))?;
    }

    Ok(())
}

fn main() {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let args = match parse_args(&argv) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("usage error: {e}");
            eprintln!(
                "usage: adapter-raikiri render <input.html> <output.png> --page-width-px <W> --page-height-px <H> --margin-px <M> [--geometry <geometry.json>] [--diagnostics <diag.json>]"
            );
            process::exit(1);
        }
    };
    match render(&args) {
        Ok(()) => {
            println!("{{\"pages\":1}}");
        }
        Err(e) => {
            eprintln!("raikiri error: {e}");
            process::exit(2);
        }
    }
}
