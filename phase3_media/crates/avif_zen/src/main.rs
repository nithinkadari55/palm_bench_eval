use p3common::Raw;
use zenpixels::{ChannelLayout, ChannelType};

fn run(sub: &str, args: &[String]) -> Result<Option<Raw>, String> {
    if sub != "decode" {
        return Err(format!("unknown subcommand {sub}"));
    }
    let bytes = std::fs::read(&args[0]).map_err(|e| format!("read: {e}"))?;
    let buf = zenavif::decode(&bytes).map_err(|e| format!("{e:?}"))?;
    let d = buf.descriptor();
    let (w, h) = (buf.width(), buf.height());
    let n = w as usize * h as usize;
    let data = buf.copy_to_contiguous_bytes();
    let channels = match d.layout() {
        ChannelLayout::Gray => 1usize,
        ChannelLayout::GrayAlpha => 2,
        ChannelLayout::Rgb => 3,
        ChannelLayout::Rgba => 4,
        other => return Err(format!("unsupported layout {other:?}")),
    };
    let wide = match d.channel_type() {
        ChannelType::U8 => false,
        ChannelType::U16 => true,
        other => return Err(format!("unsupported channel type {other:?}")),
    };
    let bps = if wide { 2 } else { 1 };
    if data.len() != n * channels * bps {
        return Err(format!("unexpected buffer size {} for {}x{}x{}x{}", data.len(), w, h, channels, bps));
    }
    let sample = |i: usize| -> u16 {
        if wide {
            u16::from_ne_bytes([data[2 * i], data[2 * i + 1]])
        } else {
            data[i] as u16
        }
    };
    let max = if wide { 65535u16 } else { 255u16 };
    let mut out: Vec<u16> = Vec::with_capacity(n * 4);
    for p in 0..n {
        let b = p * channels;
        let (r, g, bl, a) = match channels {
            1 => (sample(b), sample(b), sample(b), max),
            2 => (sample(b), sample(b), sample(b), sample(b + 1)),
            3 => (sample(b), sample(b + 1), sample(b + 2), max),
            _ => (sample(b), sample(b + 1), sample(b + 2), sample(b + 3)),
        };
        out.extend_from_slice(&[r, g, bl, a]);
    }
    if wide {
        Ok(Some(Raw::from_u16(w, h, 4, &out)))
    } else {
        Ok(Some(Raw::still(w, h, 4, 8, out.iter().map(|&v| v as u8).collect())))
    }
}

fn main() {
    p3common::dispatch(run)
}
