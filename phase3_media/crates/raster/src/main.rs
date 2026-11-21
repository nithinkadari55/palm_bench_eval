use image::codecs::gif::GifDecoder;
use image::codecs::webp::WebPDecoder;
use image::{AnimationDecoder, DynamicImage, ImageFormat, ImageReader};
use p3common::Raw;
use std::io::Cursor;

const MAX_FRAMES: usize = 300;

pub fn to_raw(img: DynamicImage) -> Raw {
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

fn read(path: &str) -> Result<Vec<u8>, String> {
    std::fs::read(path).map_err(|e| format!("read: {e}"))
}

fn decode(bytes: &[u8]) -> Result<DynamicImage, String> {
    ImageReader::new(Cursor::new(bytes))
        .with_guessed_format()
        .map_err(|e| e.to_string())?
        .decode()
        .map_err(|e| e.to_string())
}

fn frames(bytes: &[u8]) -> Result<Raw, String> {
    let fmt = image::guess_format(bytes).map_err(|e| e.to_string())?;
    let collected = match fmt {
        ImageFormat::Gif => GifDecoder::new(Cursor::new(bytes))
            .map_err(|e| e.to_string())?
            .into_frames()
            .take(MAX_FRAMES)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| e.to_string())?,
        ImageFormat::WebP => {
            let d = WebPDecoder::new(Cursor::new(bytes)).map_err(|e| e.to_string())?;
            if d.has_animation() {
                d.into_frames()
                    .take(MAX_FRAMES)
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(|e| e.to_string())?
            } else {
                return Ok(to_rgba8_raw(decode(bytes)?));
            }
        }
        _ => return Ok(to_rgba8_raw(decode(bytes)?)),
    };
    if collected.is_empty() {
        return Err("no frames".into());
    }
    let (w, h) = collected[0].buffer().dimensions();
    let mut raw = Raw { width: w, height: h, channels: 4, depth: 8, frames: Vec::new() };
    for f in collected {
        let b = f.into_buffer();
        if b.dimensions() != (w, h) {
            return Err("frame size differs from canvas".into());
        }
        raw.frames.push(b.into_raw());
    }
    Ok(raw)
}

fn to_rgba8_raw(img: DynamicImage) -> Raw {
    let (w, h) = (img.width(), img.height());
    Raw::still(w, h, 4, 8, img.into_rgba8().into_raw())
}

fn run(sub: &str, args: &[String]) -> Result<Option<Raw>, String> {
    let bytes = read(&args[0])?;
    match sub {
        "decode" => Ok(Some(to_raw(decode(&bytes)?))),
        "frames" => Ok(Some(frames(&bytes)?)),
        other => Err(format!("unknown subcommand {other}")),
    }
}

fn main() {
    p3common::dispatch(run)
}
