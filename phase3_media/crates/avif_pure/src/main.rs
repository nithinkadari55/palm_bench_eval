use avif_decode::{Decoder, Image};
use p3common::Raw;

fn rgba8(w: usize, h: usize, px: impl Iterator<Item = [u8; 4]>) -> Raw {
    let mut d = Vec::with_capacity(w * h * 4);
    for p in px {
        d.extend_from_slice(&p);
    }
    Raw::still(w as u32, h as u32, 4, 8, d)
}

fn rgba16(w: usize, h: usize, px: impl Iterator<Item = [u16; 4]>) -> Raw {
    let mut s = Vec::with_capacity(w * h * 4);
    for p in px {
        s.extend_from_slice(&p);
    }
    Raw::from_u16(w as u32, h as u32, 4, &s)
}

fn run(sub: &str, args: &[String]) -> Result<Option<Raw>, String> {
    if sub != "decode" {
        return Err(format!("unknown subcommand {sub}"));
    }
    let bytes = std::fs::read(&args[0]).map_err(|e| format!("read: {e}"))?;
    let img = Decoder::from_avif(&bytes)
        .map_err(|e| e.to_string())?
        .to_image()
        .map_err(|e| e.to_string())?;
    let raw = match img {
        Image::Rgb8(i) => rgba8(i.width(), i.height(), i.pixels().map(|p| [p.r, p.g, p.b, 255])),
        Image::Rgba8(i) => rgba8(i.width(), i.height(), i.pixels().map(|p| [p.r, p.g, p.b, p.a])),
        Image::Gray8(i) => rgba8(
            i.width(),
            i.height(),
            i.pixels().map(|p| {
                let v = p.value();
                [v, v, v, 255]
            }),
        ),
        Image::Rgb16(i) => rgba16(i.width(), i.height(), i.pixels().map(|p| [p.r, p.g, p.b, 65535])),
        Image::Rgba16(i) => rgba16(i.width(), i.height(), i.pixels().map(|p| [p.r, p.g, p.b, p.a])),
        Image::Gray16(i) => rgba16(
            i.width(),
            i.height(),
            i.pixels().map(|p| {
                let v = p.value();
                [v, v, v, 65535]
            }),
        ),
    };
    Ok(Some(raw))
}

fn main() {
    p3common::dispatch(run)
}
