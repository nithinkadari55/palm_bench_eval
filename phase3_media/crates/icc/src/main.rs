use moxcms::{ColorProfile, Layout, RenderingIntent, TransformExecutor, TransformOptions};
use p3common::{read_raw, Raw};
use std::path::Path;

fn load(args: &[String]) -> Result<(Raw, Vec<u8>, String), String> {
    if args.len() < 4 {
        return Err("usage: <moxcms|qcms> <in.raw> <out.raw> <profile.icc> <relative|perceptual>".into());
    }
    let raw = read_raw(Path::new(&args[0])).map_err(|e| format!("read raw: {e}"))?;
    if raw.depth != 8 || raw.frames.len() != 1 {
        return Err("input must be one 8-bit frame".into());
    }
    let icc = std::fs::read(&args[2]).map_err(|e| format!("read icc: {e}"))?;
    Ok((raw, icc, args[3].clone()))
}

fn mox_intents(first: &str) -> Vec<RenderingIntent> {
    let mut v = vec![if first == "perceptual" {
        RenderingIntent::Perceptual
    } else {
        RenderingIntent::RelativeColorimetric
    }];
    for i in [RenderingIntent::RelativeColorimetric, RenderingIntent::Perceptual, RenderingIntent::Saturation] {
        if !v.contains(&i) {
            v.push(i);
        }
    }
    v
}

fn moxcms_run(args: &[String]) -> Result<Option<Raw>, String> {
    let (raw, icc, intent) = load(args)?;
    let src = ColorProfile::new_from_slice(&icc).map_err(|e| format!("moxcms parse: {e:?}"))?;
    let dst = ColorProfile::new_srgb();
    let layout = match raw.channels {
        1 => Layout::Gray,
        3 => Layout::Rgb,
        4 => Layout::Rgba,
        c => return Err(format!("unsupported channel count {c}")),
    };
    let mut last_err = String::new();
    for ri in mox_intents(&intent) {
        let options = TransformOptions { rendering_intent: ri, ..TransformOptions::default() };
        match src.create_transform_8bit(layout, &dst, Layout::Rgb, options) {
            Ok(t) => {
                let n = raw.width as usize * raw.height as usize;
                let mut out = vec![0u8; n * 3];
                t.transform(&raw.frames[0], &mut out).map_err(|e| format!("moxcms transform: {e:?}"))?;
                eprintln!("intent={ri:?}");
                return Ok(Some(Raw::still(raw.width, raw.height, 3, 8, out)));
            }
            Err(e) => last_err = format!("{e:?}"),
        }
    }
    Err(format!("moxcms create_transform_8bit: {last_err}"))
}

fn qcms_run(args: &[String]) -> Result<Option<Raw>, String> {
    let (raw, icc, intent) = load(args)?;
    let src = qcms::Profile::new_from_slice(&icc, false).ok_or("qcms: profile rejected")?;
    let mut dst = qcms::Profile::new_sRGB();
    dst.precache_output_transform();
    let st = match raw.channels {
        1 => qcms::DataType::Gray8,
        3 => qcms::DataType::RGB8,
        4 => qcms::DataType::CMYK,
        c => return Err(format!("unsupported channel count {c}")),
    };
    let first = if intent == "perceptual" { qcms::Intent::Perceptual } else { qcms::Intent::RelativeColorimetric };
    let t = qcms::Transform::new_to(&src, &dst, st, qcms::DataType::RGB8, first)
        .ok_or("qcms: no transform for this profile/type")?;
    let n = raw.width as usize * raw.height as usize;
    let mut out = vec![0u8; n * 3];
    t.convert(&raw.frames[0], &mut out);
    Ok(Some(Raw::still(raw.width, raw.height, 3, 8, out)))
}

fn run(sub: &str, args: &[String]) -> Result<Option<Raw>, String> {
    match sub {
        "moxcms" => moxcms_run(args),
        "qcms" => qcms_run(args),
        other => Err(format!("unknown subcommand {other}")),
    }
}

fn main() {
    p3common::dispatch(run)
}
