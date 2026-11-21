use krilla::geom::Size;
use krilla::image::{BitsPerComponent, CustomImage, Image, ImageColorspace};
use krilla::page::PageSettings;
use krilla::Document;
use p3common::{read_raw, Raw};
use std::path::Path;
use std::sync::Arc;

/// Mirrors fulgur-raikiri `paint/raster.rs` `Pixels` + `krilla_image()` (fulgur bd6222fe, lines 29-91).
#[derive(Clone, Hash)]
struct Pixels {
    width: u32,
    height: u32,
    colors: Arc<Vec<u8>>,
    alpha: Option<Arc<Vec<u8>>>,
}

impl CustomImage for Pixels {
    fn color_channel(&self) -> &[u8] {
        self.colors.as_slice()
    }
    fn alpha_channel(&self) -> Option<&[u8]> {
        self.alpha.as_ref().map(|a| a.as_slice())
    }
    fn bits_per_component(&self) -> BitsPerComponent {
        BitsPerComponent::Eight
    }
    fn size(&self) -> (u32, u32) {
        (self.width, self.height)
    }
    fn icc_profile(&self) -> Option<&[u8]> {
        None
    }
    fn color_space(&self) -> ImageColorspace {
        ImageColorspace::Rgb
    }
}

fn fulgur_image(raw: &Raw) -> Result<Image, String> {
    if raw.channels != 4 || raw.depth != 8 {
        return Err("fulgur path expects straight RGBA8".into());
    }
    let rgba = &raw.frames[0];
    let count = rgba.len() / 4;
    let has_alpha = rgba.chunks_exact(4).any(|p| p[3] != 255);
    let mut colors = Vec::with_capacity(count * 3);
    let mut alpha = has_alpha.then(|| Vec::with_capacity(count));
    for p in rgba.chunks_exact(4) {
        colors.extend_from_slice(&p[..3]);
        if let Some(a) = &mut alpha {
            a.push(p[3]);
        }
    }
    Image::from_custom(
        Pixels { width: raw.width, height: raw.height, colors: Arc::new(colors), alpha: alpha.map(Arc::new) },
        false,
    )
}

fn native_image(bytes: Vec<u8>) -> Result<Image, String> {
    let kind = if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
        "png"
    } else if bytes.starts_with(&[0xFF, 0xD8]) {
        "jpeg"
    } else if bytes.starts_with(b"GIF8") {
        "gif"
    } else if bytes.len() > 12 && &bytes[0..4] == b"RIFF" && &bytes[8..12] == b"WEBP" {
        "webp"
    } else {
        return Err("unknown image format".into());
    };
    match kind {
        "png" => Image::from_png(bytes.into(), false),
        "jpeg" => Image::from_jpeg(bytes.into(), false),
        "gif" => Image::from_gif(bytes.into(), false),
        _ => Image::from_webp(bytes.into(), false),
    }
}

fn write_pdf(image: Image, out: &str) -> Result<(), String> {
    let (w, h) = image.size();
    let size = Size::from_wh(w as f32, h as f32).ok_or("zero-sized image")?;
    let mut doc = Document::new();
    let mut page = doc.start_page_with(PageSettings::new(size));
    let mut surface = page.surface();
    surface.draw_image(image, size);
    surface.finish();
    page.finish();
    let pdf = doc.finish().map_err(|e| format!("krilla: {e:?}"))?;
    if out != "-" {
        std::fs::write(out, pdf).map_err(|e| format!("write: {e}"))?;
    }
    Ok(())
}

fn run(sub: &str, args: &[String]) -> Result<Option<Raw>, String> {
    let image = match sub {
        "native" => native_image(std::fs::read(&args[0]).map_err(|e| format!("read: {e}"))?)?,
        "fulgur" => fulgur_image(&read_raw(Path::new(&args[0])).map_err(|e| format!("read raw: {e}"))?)?,
        other => return Err(format!("unknown subcommand {other}")),
    };
    write_pdf(image, &args[1])?;
    Ok(None)
}

fn main() {
    p3common::dispatch(run)
}
