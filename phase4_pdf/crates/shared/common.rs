#![allow(dead_code)]
use std::collections::BTreeMap;
use std::sync::Arc;

use krilla::color::rgb;
use krilla::geom::{Path, PathBuilder, Point, Rect};
use krilla::icc::ICCProfile;
use krilla::metadata::{DateTime, Metadata};
use krilla::num::NormalizedF32;
use krilla::outline::Outline;
use krilla::paint::{Fill, Stroke};
use krilla::surface::Surface;
use krilla::tagging::{ContentTag, Identifier, SpanTag, TagTree};
use krilla::text::{Font, GlyphId, KrillaGlyph, Tag as FontTag};
use krilla::{Data, Document};
use serde_json::{json, Value};

pub const A4: (f32, f32) = (595.2756, 841.8898);
pub const LETTER: (f32, f32) = (612.0, 792.0);
pub const TITLE_PREFIX: &str = "palm_bench_eval phase 4";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Art {
    Header,
    Footer,
    Page,
    Other,
}

pub fn variant_name(debug: &str) -> String {
    debug
        .split(|c: char| c == '(' || c == ' ' || c == '{')
        .next()
        .unwrap_or("")
        .to_string()
}

pub fn fixed_date() -> DateTime {
    DateTime::new(2026)
        .month(1)
        .day(2)
        .hour(3)
        .minute(4)
        .second(5)
        .utc_offset_hour(0)
        .utc_offset_minute(0)
}

pub struct FontAsset {
    pub role: String,
    pub font: Font,
    pub data: Arc<Vec<u8>>,
    pub index: u32,
    pub path: String,
    pub vars: Vec<(String, f32)>,
}

pub struct Assets {
    pub manifest: Value,
    pub fonts: BTreeMap<String, Arc<FontAsset>>,
    pub font_errors: BTreeMap<String, String>,
    pub cmyk: Option<ICCProfile<4>>,
    pub cmyk_error: Option<String>,
}

impl Assets {
    pub fn load(path: &str) -> Result<Assets, String> {
        let text = std::fs::read_to_string(path).map_err(|e| format!("read manifest {path}: {e}"))?;
        let manifest: Value = serde_json::from_str(&text).map_err(|e| format!("parse manifest: {e}"))?;
        let mut fonts = BTreeMap::new();
        let mut font_errors = BTreeMap::new();
        if let Some(obj) = manifest.get("fonts").and_then(|f| f.as_object()) {
            for (role, spec) in obj {
                match load_font_spec(role, spec) {
                    Ok(fa) => {
                        fonts.insert(role.clone(), Arc::new(fa));
                    }
                    Err(e) => {
                        font_errors.insert(role.clone(), e);
                    }
                }
            }
        }
        let (cmyk, cmyk_error) = match manifest.get("cmyk_icc").and_then(|v| v.as_str()) {
            Some(p) => match std::fs::read(p) {
                Ok(bytes) => match ICCProfile::<4>::new(&bytes) {
                    Some(icc) => (Some(icc), None),
                    None => (None, Some(format!("ICCProfile::<4>::new rejected {p}"))),
                },
                Err(e) => (None, Some(format!("read {p}: {e}"))),
            },
            None => (None, Some("no CMYK ICC profile in manifest".to_string())),
        };
        Ok(Assets { manifest, fonts, font_errors, cmyk, cmyk_error })
    }

    pub fn font(&self, role: &str) -> Result<Arc<FontAsset>, String> {
        self.fonts.get(role).cloned().ok_or_else(|| {
            format!(
                "font role '{role}' unavailable: {}",
                self.font_errors.get(role).cloned().unwrap_or_else(|| "not in manifest".into())
            )
        })
    }

    pub fn path(&self, section: &str, key: &str) -> Result<String, String> {
        self.manifest
            .get(section)
            .and_then(|s| s.get(key))
            .and_then(|v| v.as_str().map(|s| s.to_string()).or_else(|| v.get("path").and_then(|p| p.as_str()).map(|s| s.to_string())))
            .ok_or_else(|| format!("asset {section}.{key} missing from manifest"))
    }

    pub fn bytes(&self, section: &str, key: &str) -> Result<Vec<u8>, String> {
        let p = self.path(section, key)?;
        std::fs::read(&p).map_err(|e| format!("read {p}: {e}"))
    }
}

fn load_font_spec(role: &str, spec: &Value) -> Result<FontAsset, String> {
    let path = spec.get("path").and_then(|p| p.as_str()).ok_or("font spec without path")?.to_string();
    let index = spec.get("index").and_then(|i| i.as_u64()).unwrap_or(0) as u32;
    let mut vars = vec![];
    if let Some(v) = spec.get("variations").and_then(|v| v.as_object()) {
        for (tag, val) in v {
            vars.push((tag.clone(), val.as_f64().unwrap_or(0.0) as f32));
        }
    }
    load_font(role, &path, index, &vars)
}

pub fn load_font(role: &str, path: &str, index: u32, vars: &[(String, f32)]) -> Result<FontAsset, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("read {path}: {e}"))?;
    let data = Arc::new(bytes);
    let kdata: Data = data.clone().into();
    let font = if vars.is_empty() {
        Font::new(kdata, index)
    } else {
        let mut coords = vec![];
        for (t, v) in vars {
            let tag = FontTag::try_from_str(t).ok_or_else(|| format!("bad axis tag {t}"))?;
            coords.push((tag, *v));
        }
        Font::new_variable(kdata, index, &coords)
    }
    .ok_or_else(|| format!("krilla Font::new rejected {path} index {index}"))?;
    Ok(FontAsset { role: role.to_string(), font, data, index, path: path.to_string(), vars: vars.to_vec() })
}

pub fn with_vars(base: &FontAsset, role: &str, vars: &[(String, f32)]) -> Result<FontAsset, String> {
    load_font(role, &base.path, base.index, vars)
}

pub struct Shaped {
    pub glyphs: Vec<KrillaGlyph>,
    pub width_em: f32,
    pub chars: usize,
    pub multi_char_clusters: usize,
    pub multi_glyph_clusters: usize,
    pub notdef: usize,
}

impl Shaped {
    pub fn width(&self, size: f32) -> f32 {
        self.width_em * size
    }
    pub fn info(&self) -> Value {
        json!({
            "glyphs": self.glyphs.len(),
            "chars": self.chars,
            "multi_char_clusters": self.multi_char_clusters,
            "multi_glyph_clusters": self.multi_glyph_clusters,
            "notdef": self.notdef,
        })
    }
}

/// Shapes one run with rustybuzz 0.20.1 (the version krilla's simple-text feature uses).
pub fn shape(fa: &FontAsset, text: &str, rtl: bool, lang: Option<&str>) -> Shaped {
    let mut face = match rustybuzz::Face::from_slice(&fa.data, fa.index) {
        Some(f) => f,
        None => {
            return Shaped { glyphs: vec![], width_em: 0.0, chars: text.chars().count(), multi_char_clusters: 0, multi_glyph_clusters: 0, notdef: 0 }
        }
    };
    if !fa.vars.is_empty() {
        let vs: Vec<rustybuzz::Variation> = fa
            .vars
            .iter()
            .filter_map(|(t, v)| format!("{t}={v}").parse().ok())
            .collect();
        face.set_variations(&vs);
    }
    let mut buf = rustybuzz::UnicodeBuffer::new();
    buf.push_str(text);
    if let Some(l) = lang {
        if let Ok(l) = l.parse::<rustybuzz::Language>() {
            buf.set_language(l);
        }
    }
    buf.guess_segment_properties();
    buf.set_direction(if rtl { rustybuzz::Direction::RightToLeft } else { rustybuzz::Direction::LeftToRight });
    let out = rustybuzz::shape(&face, &[], buf);
    let upem = face.units_per_em() as f32;
    let infos = out.glyph_infos();
    let pos = out.glyph_positions();
    let mut starts: Vec<usize> = infos.iter().map(|i| i.cluster as usize).collect();
    starts.sort_unstable();
    starts.dedup();
    let end_of = |c: usize| -> usize {
        match starts.binary_search(&c) {
            Ok(i) if i + 1 < starts.len() => starts[i + 1],
            _ => text.len(),
        }
    };
    let mut glyphs = Vec::with_capacity(infos.len());
    let mut width = 0.0;
    let mut per_cluster: BTreeMap<usize, usize> = BTreeMap::new();
    let mut notdef = 0;
    for (i, p) in infos.iter().zip(pos.iter()) {
        let c = i.cluster as usize;
        let range = c..end_of(c);
        *per_cluster.entry(c).or_insert(0) += 1;
        if i.glyph_id == 0 {
            notdef += 1;
        }
        width += p.x_advance as f32 / upem;
        glyphs.push(KrillaGlyph::new(
            GlyphId::new(i.glyph_id),
            p.x_advance as f32 / upem,
            p.x_offset as f32 / upem,
            p.y_offset as f32 / upem,
            p.y_advance as f32 / upem,
            range,
            None,
        ));
    }
    let multi_char_clusters = starts.iter().filter(|&&c| text[c..end_of(c)].chars().count() > 1).count();
    let multi_glyph_clusters = per_cluster.values().filter(|&&n| n > 1).count();
    Shaped { glyphs, width_em: width, chars: text.chars().count(), multi_char_clusters, multi_glyph_clusters, notdef }
}

pub fn black() -> Fill {
    Fill::default()
}

pub fn rgb_fill(r: u8, g: u8, b: u8) -> Fill {
    Fill { paint: rgb::Color::new(r, g, b).into(), ..Default::default() }
}

pub fn rgb_fill_a(r: u8, g: u8, b: u8, a: f32) -> Fill {
    Fill { paint: rgb::Color::new(r, g, b).into(), opacity: NormalizedF32::new(a).unwrap(), ..Default::default() }
}

pub fn rgb_stroke(r: u8, g: u8, b: u8, w: f32) -> Stroke {
    Stroke { paint: rgb::Color::new(r, g, b).into(), width: w, ..Default::default() }
}

pub fn rect_path(x: f32, y: f32, w: f32, h: f32) -> Path {
    let mut pb = PathBuilder::new();
    pb.push_rect(Rect::from_xywh(x, y, w, h).unwrap());
    pb.finish().unwrap()
}

pub fn circle_path(cx: f32, cy: f32, r: f32) -> Path {
    let k = 0.552_284_8 * r;
    let mut pb = PathBuilder::new();
    pb.move_to(cx + r, cy);
    pb.cubic_to(cx + r, cy + k, cx + k, cy + r, cx, cy + r);
    pb.cubic_to(cx - k, cy + r, cx - r, cy + k, cx - r, cy);
    pb.cubic_to(cx - r, cy - k, cx - k, cy - r, cx, cy - r);
    pb.cubic_to(cx + k, cy - r, cx + r, cy - k, cx + r, cy);
    pb.close();
    pb.finish().unwrap()
}

pub fn star_path(cx: f32, cy: f32, r: f32) -> Path {
    let mut pb = PathBuilder::new();
    for i in 0..5 {
        let a = -std::f32::consts::FRAC_PI_2 + i as f32 * 4.0 * std::f32::consts::PI / 5.0;
        let (x, y) = (cx + r * a.cos(), cy + r * a.sin());
        if i == 0 {
            pb.move_to(x, y)
        } else {
            pb.line_to(x, y)
        }
    }
    pb.close();
    pb.finish().unwrap()
}

/// Draws one shaped run inside a tagged Span marked-content sequence and returns its identifier.
pub fn tagged_run(
    s: &mut Surface,
    fa: &FontAsset,
    text: &str,
    x: f32,
    y: f32,
    size: f32,
    lang: Option<&str>,
    rtl: bool,
) -> (Identifier, Shaped) {
    let sh = shape(fa, text, rtl, lang);
    let id = s.start_tagged(ContentTag::Span(SpanTag::empty().with_lang(lang)));
    s.set_fill(Some(black()));
    s.set_stroke(None);
    s.draw_glyphs(Point::from_xy(x, y), &sh.glyphs, fa.font.clone(), text, size, false);
    s.end_tagged();
    (id, sh)
}

/// Draws an untagged-in-structure artifact run (headers, footers).
pub fn artifact_run(s: &mut Surface, fa: &FontAsset, text: &str, x: f32, y: f32, size: f32, kind: Art) {
    let sh = shape(fa, text, false, Some("en"));
    s.start_tagged(crate::compat::artifact(kind));
    s.set_fill(Some(rgb_fill(90, 90, 90)));
    s.set_stroke(None);
    s.draw_glyphs(Point::from_xy(x, y), &sh.glyphs, fa.font.clone(), text, size, false);
    s.end_tagged();
}

/// Applies the metadata, outline and tag tree every fixture carries, then serialises.
pub fn finish_doc(
    mut doc: Document,
    title: &str,
    tree: TagTree,
    outline: Outline,
) -> krilla::error::KrillaResult<Vec<u8>> {
    let md = Metadata::new()
        .title(format!("{TITLE_PREFIX}: {title}"))
        .authors(vec!["palm_bench_eval".to_string()])
        .description(format!("Fixture '{title}' generated directly with krilla {}", crate::compat::KRILLA_VERSION))
        .keywords(vec!["phase4".to_string(), title.to_string()])
        .language("en".to_string())
        .creator("palm_bench_eval phase4 gen".to_string())
        .creation_date(fixed_date());
    doc.set_metadata(md);
    doc.set_outline(outline);
    doc.set_tag_tree(tree);
    doc.finish()
}

pub fn expected_title(title: &str) -> String {
    format!("{TITLE_PREFIX}: {title}")
}

/// Converts a krilla (top-left origin) rect to PDF user space for a page of height `h`.
pub fn pdf_rect(x: f32, y: f32, w: f32, hgt: f32, h: f32) -> Value {
    json!([round2(x), round2(h - y - hgt), round2(x + w), round2(h - y)])
}

pub fn round2(v: f32) -> f64 {
    ((v as f64) * 100.0).round() / 100.0
}
