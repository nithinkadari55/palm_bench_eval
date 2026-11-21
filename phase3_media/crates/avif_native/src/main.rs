use image::{DynamicImage, ImageReader};
use p3common::Raw;
use std::io::Cursor;

fn to_raw(img: DynamicImage) -> Raw {
    let ct = img.color();
    let sixteen = ct.bytes_per_pixel() / ct.channel_count().max(1) > 1;
    let (w, h) = (img.width(), img.height());
    if sixteen {
        let buf = img.into_rgba16();
        Raw::from_u16(w, h, 4, buf.as_raw())
    } else {
        Raw::still(w, h, 4, 8, img.into_rgba8().into_raw())
    }
}

fn run(sub: &str, args: &[String]) -> Result<Option<Raw>, String> {
    if sub != "decode" {
        return Err(format!("unknown subcommand {sub}"));
    }
    let bytes = std::fs::read(&args[0]).map_err(|e| format!("read: {e}"))?;
    let img = ImageReader::new(Cursor::new(&bytes[..]))
        .with_guessed_format()
        .map_err(|e| e.to_string())?
        .decode()
        .map_err(|e| e.to_string())?;
    Ok(Some(to_raw(img)))
}

fn main() {
    p3common::dispatch(run)
}
