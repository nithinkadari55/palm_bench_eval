use image::{ImageDecoder, ImageReader};
use p3common::Raw;
use raikiri_net::{FileNetworkProvider, ImageResolver};
use raikiri_traits::{ImagePixelSource, ReplacedResolver, ResolverRequest};
use std::io::Cursor;
use url::Url;

fn file_url(path: &str) -> Result<Url, String> {
    let abs = std::fs::canonicalize(path).map_err(|e| format!("canonicalize: {e}"))?;
    Url::from_file_path(&abs).map_err(|_| "bad file path".to_string())
}

fn decode(path: &str) -> Result<Raw, String> {
    let url = file_url(path)?;
    let resolver = ImageResolver::new(FileNetworkProvider);
    resolver
        .resolve(ResolverRequest::new(&url))
        .map_err(|e| e.to_string())?;
    let img = resolver
        .get_decoded(&url)
        .ok_or_else(|| "resolver returned no pixels".to_string())?;
    Ok(Raw::still(img.width, img.height, 4, 8, img.rgba.clone()))
}

fn orientation(path: &str) -> Result<u8, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("read: {e}"))?;
    let mut decoder = ImageReader::new(Cursor::new(&bytes[..]))
        .with_guessed_format()
        .map_err(|e| e.to_string())?
        .into_decoder()
        .map_err(|e| e.to_string())?;
    let o = decoder.orientation().map_err(|e| e.to_string())?;
    Ok(o.to_exif())
}

fn run(sub: &str, args: &[String]) -> Result<Option<Raw>, String> {
    match sub {
        "decode" => Ok(Some(decode(&args[0])?)),
        "orient" => {
            let o = orientation(&args[0])?;
            eprintln!("orientation={o}");
            Ok(None)
        }
        other => Err(format!("unknown subcommand {other}")),
    }
}

fn main() {
    p3common::dispatch(run)
}
