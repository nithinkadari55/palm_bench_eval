use std::num::{NonZeroU16, NonZeroU32};

use krilla::action::{Action, LinkAction};
use krilla::annotation::{Annotation, LinkAnnotation, Target};
use krilla::blend::BlendMode;
use krilla::color::rgb;
use krilla::destination::{NamedDestination, XyzDestination};
use krilla::embed::{AssociationKind, EmbeddedFile, MimeType};
use krilla::error::KrillaResult;
use krilla::geom::{PathBuilder, Point, Rect, Size, Transform};
use krilla::image::Image;
use krilla::mask::{Mask, MaskType};
use krilla::num::NormalizedF32;
use krilla::outline::{Outline, OutlineNode};
use krilla::page::{NumberingStyle, PageLabel, PageSettings};
use krilla::paint::{
    Fill, FillRule, LineCap, LineJoin, LinearGradient, Pattern, RadialGradient, SpreadMethod, Stop, Stroke,
    StrokeDash, SweepGradient,
};
use krilla::surface::Surface;
use krilla::tagging::{ContentTag, ListNumbering, TableHeaderScope, Tag, TagGroup, TagTree};
use krilla::{Data, Document, SerializeSettings};
use serde_json::{json, Value};

use crate::common::*;

pub type BuildResult = Result<KrillaResult<Vec<u8>>, String>;

pub struct Fixture {
    pub name: &'static str,
    pub build: fn(&Assets, SerializeSettings, &mut Value) -> BuildResult,
}

pub const FIXTURES: &[Fixture] = &[
    Fixture { name: "text", build: text },
    Fixture { name: "text_emoji", build: text_emoji },
    Fixture { name: "vector_opaque", build: vector_opaque },
    Fixture { name: "vector_transparency", build: vector_transparency },
    Fixture { name: "vector_postscript", build: vector_postscript },
    Fixture { name: "images_opaque", build: images_opaque },
    Fixture { name: "images_alpha", build: images_alpha },
    Fixture { name: "images_cmyk", build: images_cmyk },
    Fixture { name: "images_16bit", build: images_16bit },
    Fixture { name: "navigation", build: navigation },
    Fixture { name: "structure", build: structure },
    Fixture { name: "embedded_file", build: embedded_file },
    Fixture { name: "page_sizes", build: page_sizes },
    Fixture { name: "pages_1", build: pages_1 },
    Fixture { name: "pages_10", build: pages_10 },
    Fixture { name: "pages_100", build: pages_100 },
];

pub const UNSUPPORTED: &[(&str, &str)] = &[(
    "form_field",
    "krilla exposes only link annotations (krilla::annotation::AnnotationType has the single variant Link); there is no AcroForm or widget-annotation API in 0.7.0 or 0.8.2",
)];

fn a4_page(label: Option<PageLabel>) -> PageSettings {
    let ps = PageSettings::from_wh(A4.0, A4.1).unwrap();
    match label {
        Some(l) => ps.with_page_label(l),
        None => ps,
    }
}

fn arabic_label(n: u32) -> PageLabel {
    PageLabel::new(Some(NumberingStyle::Arabic), None, NonZeroU32::new(n))
}

fn heading(level: u16, text: &str) -> TagGroup {
    TagGroup::new(Tag::Hn(NonZeroU16::new(level).unwrap(), Some(text.to_string())))
}

fn top_dest(page: usize, y: f32) -> XyzDestination {
    XyzDestination::new(page, Point::from_xy(0.0, y))
}

fn figure<F: FnOnce(&mut Surface)>(s: &mut Surface, tree: &mut TagTree, alt: &str, f: F) {
    let id = s.start_tagged(ContentTag::Other);
    f(s);
    s.end_tagged();
    let mut g = TagGroup::new(Tag::Figure(Some(alt.to_string())));
    g.push(id);
    tree.push(g);
}

fn figure_alt<F: FnOnce(&mut Surface)>(s: &mut Surface, tree: &mut TagTree, alts: &mut Vec<String>, alt: &str, f: F) {
    alts.push(alt.to_string());
    figure(s, tree, alt, f);
}

fn stop(offset: f32, c: (u8, u8, u8), opacity: f32) -> Stop {
    Stop {
        offset: NormalizedF32::new(offset).unwrap(),
        color: rgb::Color::new(c.0, c.1, c.2).into(),
        opacity: NormalizedF32::new(opacity).unwrap(),
    }
}

fn title_block(s: &mut Surface, tree: &mut TagTree, a: &Assets, text: &str) -> Result<(), String> {
    let latin = a.font("latin")?;
    let (id, _) = tagged_run(s, &latin, text, 50.0, 60.0, 20.0, Some("en"), false);
    let mut h = heading(1, text);
    h.push(id);
    tree.push(h);
    Ok(())
}

// ---------------------------------------------------------------- text

struct Sample {
    id: &'static str,
    role: &'static str,
    text: &'static str,
    lang: &'static str,
    rtl: bool,
    size: f32,
}

const SAMPLES: &[Sample] = &[
    Sample { id: "latin_ligatures", role: "latin_lig", text: "office affinity flow fjord baffled shuffle", lang: "en", rtl: false, size: 22.0 },
    Sample { id: "latin_diacritics", role: "latin", text: "Ångström naïve façade Œuvre Straße Đặng Việt", lang: "en", rtl: false, size: 20.0 },
    Sample { id: "arabic", role: "arabic", text: "مرحبا بالعالم هذا نص عربي للاختبار", lang: "ar", rtl: true, size: 24.0 },
    Sample { id: "devanagari", role: "devanagari", text: "हिन्दी में किताब पढ़िए और क्षत्रिय", lang: "hi", rtl: false, size: 24.0 },
    Sample { id: "cjk_sc", role: "cjk_sc", text: "简体中文排版测试，标点符号。", lang: "zh-Hans", rtl: false, size: 24.0 },
    Sample { id: "cjk_jp", role: "cjk_jp", text: "日本語の組版テストです。カタカナ", lang: "ja", rtl: false, size: 24.0 },
    Sample { id: "cjk_kr", role: "cjk_kr", text: "한국어 조판 시험 문장입니다", lang: "ko", rtl: false, size: 24.0 },
];

// Emoji live in their own fixture so that a refusal caused by colour glyphs (Type3 fonts, bitmap
// transparency) does not hide the results for the other scripts.
const EMOJI_SAMPLES: &[Sample] = &[
    Sample { id: "emoji_bitmap", role: "emoji_cbdt", text: "😀🎉👍🏽👨‍👩‍👧🇮🇳", lang: "en", rtl: false, size: 28.0 },
    Sample { id: "emoji_colrv1", role: "emoji_colrv1", text: "😀🎉👍🏽👨‍👩‍👧🇮🇳", lang: "en", rtl: false, size: 28.0 },
];

const VAR_WEIGHTS: &[f32] = &[100.0, 400.0, 900.0];

fn text(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    text_doc("text", SAMPLES, true, a, settings, exp)
}

fn text_emoji(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    text_doc("text_emoji", EMOJI_SAMPLES, false, a, settings, exp)
}

fn text_doc(name: &str, samples: &[Sample], with_variable: bool, a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let mut outline = Outline::new();
    let mut pages = vec![];
    for (i, smp) in samples.iter().enumerate() {
        let fa = a.font(smp.role)?;
        let mut page = doc.start_page_with(a4_page(None));
        let mut s = page.surface();
        let x = 50.0;
        let sh_probe = shape(&fa, smp.text, smp.rtl, Some(smp.lang));
        let x = if smp.rtl { A4.0 - 50.0 - sh_probe.width(smp.size) } else { x };
        let (id, sh) = tagged_run(&mut s, &fa, smp.text, x, 120.0, smp.size, Some(smp.lang), smp.rtl);
        s.finish();
        page.finish();
        let mut p = TagGroup::new(Tag::P.with_lang(Some(smp.lang.to_string())));
        p.push(id);
        tree.push(p);
        outline.push_child(OutlineNode::new(smp.id.to_string(), top_dest(i, 0.0)));
        pages.push(json!({
            "page": i, "script": smp.id, "text": smp.text, "lang": smp.lang, "rtl": smp.rtl,
            "font_role": smp.role, "font_path": fa.path, "font_index": fa.index, "shaping": sh.info(),
        }));
    }
    if !with_variable {
        let n = samples.len();
        *exp = json!({"title": expected_title(name), "pages": pages, "page_count": n});
        return Ok(finish_doc(doc, name, tree, outline));
    }
    // variable font page
    let base = a.font("variable")?;
    let idx = samples.len();
    let mut lines = vec![];
    let mut infos = vec![];
    {
        let mut page = doc.start_page_with(a4_page(None));
        let mut s = page.surface();
        let mut ids = vec![];
        for (k, w) in VAR_WEIGHTS.iter().enumerate() {
            let inst = with_vars(&base, "variable", &[("wght".to_string(), *w)])?;
            let line = format!("Variable font weight {}", *w as u32);
            let (id, sh) = tagged_run(&mut s, &inst, &line, 50.0, 120.0 + 40.0 * k as f32, 24.0, Some("en"), false);
            ids.push(id);
            infos.push(json!({"wght": w, "shaping": sh.info()}));
            lines.push(line);
        }
        s.finish();
        page.finish();
        for id in ids {
            let mut p = TagGroup::new(Tag::P);
            p.push(id);
            tree.push(p);
        }
    }
    outline.push_child(OutlineNode::new("variable".to_string(), top_dest(idx, 0.0)));
    pages.push(json!({
        "page": idx, "script": "variable", "text": lines.join("\n"), "lang": "en", "rtl": false,
        "font_role": "variable", "font_path": base.path, "font_index": base.index, "instances": infos,
    }));
    *exp = json!({"title": expected_title(name), "pages": pages, "page_count": idx + 1});
    Ok(finish_doc(doc, name, tree, outline))
}

// ---------------------------------------------------------------- vectors

fn vector_opaque(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let mut alts: Vec<String> = vec![];
    {
        let mut page = doc.start_page_with(a4_page(None));
        let mut s = page.surface();
        title_block(&mut s, &mut tree, a, "Vector graphics (opaque)")?;
        figure_alt(&mut s, &mut tree, &mut alts, "Red five-pointed star filled with the even-odd rule", |s| {
            s.set_fill(Some(Fill { rule: FillRule::EvenOdd, ..rgb_fill(220, 30, 30) }));
            s.set_stroke(None);
            s.draw_path(&star_path(110.0, 160.0, 55.0));
        });
        figure_alt(&mut s, &mut tree, &mut alts, "Blue circle built from four cubic Bezier curves with a black outline", |s| {
            s.set_fill(Some(rgb_fill(30, 60, 220)));
            s.set_stroke(Some(rgb_stroke(0, 0, 0, 3.0)));
            s.draw_path(&circle_path(260.0, 160.0, 50.0));
        });
        figure_alt(&mut s, &mut tree, &mut alts, "Green dashed quadratic curve with round caps", |s| {
            let mut pb = PathBuilder::new();
            pb.move_to(340.0, 200.0);
            pb.quad_to(410.0, 80.0, 500.0, 200.0);
            s.set_fill(None);
            s.set_stroke(Some(Stroke {
                width: 6.0,
                line_cap: LineCap::Round,
                dash: Some(StrokeDash { array: vec![14.0, 10.0], offset: 0.0 }),
                ..rgb_stroke(20, 150, 40, 6.0)
            }));
            s.draw_path(&pb.finish().unwrap());
        });
        figure_alt(&mut s, &mut tree, &mut alts, "Three thick zig-zag polylines showing miter, round and bevel joins", |s| {
            for (k, join) in [LineJoin::Miter, LineJoin::Round, LineJoin::Bevel].into_iter().enumerate() {
                let mut pb = PathBuilder::new();
                let x0 = 60.0 + 160.0 * k as f32;
                pb.move_to(x0, 320.0);
                pb.line_to(x0 + 40.0, 260.0);
                pb.line_to(x0 + 80.0, 320.0);
                pb.line_to(x0 + 120.0, 260.0);
                s.set_fill(None);
                s.set_stroke(Some(Stroke { line_join: join, line_cap: LineCap::Square, ..rgb_stroke(120, 60, 0, 12.0) }));
                s.draw_path(&pb.finish().unwrap());
            }
        });
        figure_alt(&mut s, &mut tree, &mut alts, "Rectangle filled with an opaque linear gradient from orange to purple", |s| {
            let lg = LinearGradient {
                x1: 50.0, y1: 0.0, x2: 270.0, y2: 0.0, transform: Transform::identity(),
                spread_method: SpreadMethod::Pad,
                stops: vec![stop(0.0, (255, 140, 0), 1.0), stop(0.5, (240, 240, 60), 1.0), stop(1.0, (120, 30, 160), 1.0)],
                anti_alias: false,
            };
            s.set_fill(Some(Fill { paint: lg.into(), ..Default::default() }));
            s.set_stroke(None);
            s.draw_path(&rect_path(50.0, 360.0, 220.0, 90.0));
        });
        figure_alt(&mut s, &mut tree, &mut alts, "Circle filled with an opaque radial gradient from white to teal", |s| {
            let rg = RadialGradient {
                fx: 390.0, fy: 395.0, fr: 0.0, cx: 400.0, cy: 405.0, cr: 55.0, transform: Transform::identity(),
                spread_method: SpreadMethod::Pad,
                stops: vec![stop(0.0, (255, 255, 255), 1.0), stop(1.0, (0, 128, 128), 1.0)],
                anti_alias: false,
            };
            s.set_fill(Some(Fill { paint: rg.into(), ..Default::default() }));
            s.set_stroke(None);
            s.draw_path(&circle_path(400.0, 405.0, 55.0));
        });
        figure_alt(&mut s, &mut tree, &mut alts, "Horizontal stripes clipped to a circle with the non-zero rule", |s| {
            s.push_clip_path(&circle_path(110.0, 540.0, 55.0), &FillRule::NonZero);
            for k in 0..12 {
                let c = if k % 2 == 0 { (200, 0, 120) } else { (255, 220, 0) };
                s.set_fill(Some(rgb_fill(c.0, c.1, c.2)));
                s.set_stroke(None);
                s.draw_path(&rect_path(50.0, 485.0 + 10.0 * k as f32, 120.0, 10.0));
            }
            s.pop();
        });
        figure_alt(&mut s, &mut tree, &mut alts, "Solid square clipped to a ring with the even-odd rule", |s| {
            let mut pb = PathBuilder::new();
            pb.push_rect(Rect::from_xywh(210.0, 485.0, 110.0, 110.0).unwrap());
            pb.push_rect(Rect::from_xywh(240.0, 515.0, 50.0, 50.0).unwrap());
            s.push_clip_path(&pb.finish().unwrap(), &FillRule::EvenOdd);
            s.set_fill(Some(rgb_fill(0, 90, 160)));
            s.set_stroke(None);
            s.draw_path(&rect_path(200.0, 475.0, 130.0, 130.0));
            s.pop();
        });
        figure_alt(&mut s, &mut tree, &mut alts, "Rotated and skewed rectangles drawn with nested transforms", |s| {
            s.push_transform(&Transform::from_rotate_at(25.0, 430.0, 540.0));
            s.set_fill(Some(rgb_fill(90, 170, 90)));
            s.set_stroke(None);
            s.draw_path(&rect_path(390.0, 510.0, 80.0, 60.0));
            s.push_transform(&Transform::from_skew(0.3, 0.0));
            s.set_fill(Some(rgb_fill(40, 40, 40)));
            s.draw_path(&rect_path(400.0, 520.0, 30.0, 20.0));
            s.pop();
            s.pop();
        });
        // tiling pattern (built outside the closure helper because it needs the stream builder)
        {
            let alt = "Rectangle filled with a red and blue checkerboard tiling pattern";
            alts.push(alt.to_string());
            let id = s.start_tagged(ContentTag::Other);
            let stream = {
                let mut sb = s.stream_builder();
                let mut ps = sb.surface();
                ps.set_fill(Some(rgb_fill(200, 0, 0)));
                ps.draw_path(&rect_path(0.0, 0.0, 10.0, 10.0));
                ps.set_fill(Some(rgb_fill(0, 0, 200)));
                ps.draw_path(&rect_path(10.0, 10.0, 10.0, 10.0));
                ps.finish();
                sb.finish()
            };
            let pattern = Pattern { stream, transform: Transform::identity(), width: 20.0, height: 20.0 };
            s.set_fill(Some(Fill { paint: pattern.into(), ..Default::default() }));
            s.set_stroke(Some(rgb_stroke(0, 0, 0, 1.0)));
            s.draw_path(&rect_path(50.0, 640.0, 220.0, 120.0));
            s.end_tagged();
            let mut g = TagGroup::new(Tag::Figure(Some(alt.to_string())));
            g.push(id);
            tree.push(g);
        }
        s.finish();
        page.finish();
    }
    let mut outline = Outline::new();
    outline.push_child(OutlineNode::new("Vector graphics (opaque)".into(), top_dest(0, 0.0)));
    *exp = json!({"title": expected_title("vector_opaque"), "figure_alts": alts, "page_count": 1});
    Ok(finish_doc(doc, "vector_opaque", tree, outline))
}

const BLEND_MODES: &[(BlendMode, &str)] = &[
    (BlendMode::Normal, "Normal"), (BlendMode::Multiply, "Multiply"), (BlendMode::Screen, "Screen"),
    (BlendMode::Overlay, "Overlay"), (BlendMode::Darken, "Darken"), (BlendMode::Lighten, "Lighten"),
    (BlendMode::ColorDodge, "ColorDodge"), (BlendMode::ColorBurn, "ColorBurn"), (BlendMode::HardLight, "HardLight"),
    (BlendMode::SoftLight, "SoftLight"), (BlendMode::Difference, "Difference"), (BlendMode::Exclusion, "Exclusion"),
    (BlendMode::Hue, "Hue"), (BlendMode::Saturation, "Saturation"), (BlendMode::Color, "Color"),
    (BlendMode::Luminosity, "Luminosity"),
];

fn vector_transparency(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let mut alts: Vec<String> = vec![];
    {
        let mut page = doc.start_page_with(a4_page(None));
        let mut s = page.surface();
        title_block(&mut s, &mut tree, a, "Vector graphics (transparency)")?;
        let alt = "Three overlapping circles in red, green and blue at 50 percent fill opacity";
        alts.push(alt.into());
        figure(&mut s, &mut tree, alt, |s| {
            for (k, c) in [(255, 0, 0), (0, 200, 0), (0, 0, 255)].into_iter().enumerate() {
                s.set_fill(Some(rgb_fill_a(c.0, c.1, c.2, 0.5)));
                s.set_stroke(Some(Stroke { opacity: NormalizedF32::new(0.3).unwrap(), ..rgb_stroke(0, 0, 0, 4.0) }));
                s.draw_path(&circle_path(100.0 + 35.0 * k as f32, 150.0 + if k == 1 { 40.0 } else { 0.0 }, 50.0));
            }
        });
        let alt = "Rectangle with a linear gradient fading from opaque navy to transparent";
        alts.push(alt.into());
        figure(&mut s, &mut tree, alt, |s| {
            let lg = LinearGradient {
                x1: 300.0, y1: 0.0, x2: 540.0, y2: 0.0, transform: Transform::identity(),
                spread_method: SpreadMethod::Pad,
                stops: vec![stop(0.0, (0, 0, 128), 1.0), stop(1.0, (0, 0, 128), 0.1)],
                anti_alias: false,
            };
            s.set_fill(Some(Fill { paint: lg.into(), ..Default::default() }));
            s.set_stroke(None);
            s.draw_path(&rect_path(300.0, 110.0, 240.0, 90.0));
        });
        for (k, (mode, name)) in BLEND_MODES.iter().enumerate() {
            let alt = format!("Blend mode {name}: an orange circle composited over a blue square");
            alts.push(alt.clone());
            let (col, row) = (k % 4, k / 4);
            let (x, y) = (60.0 + 125.0 * col as f32, 250.0 + 95.0 * row as f32);
            figure(&mut s, &mut tree, &alt, |s| {
                s.set_fill(Some(rgb_fill(40, 90, 200)));
                s.set_stroke(None);
                s.draw_path(&rect_path(x, y, 70.0, 70.0));
                s.push_blend_mode(*mode);
                s.set_fill(Some(rgb_fill(250, 150, 30)));
                s.draw_path(&circle_path(x + 60.0, y + 45.0, 35.0));
                s.pop();
            });
        }
        let alt = "Green rectangle shown through a radial luminosity mask";
        alts.push(alt.into());
        figure(&mut s, &mut tree, alt, |s| {
            let stream = {
                let mut sb = s.stream_builder();
                let mut ms = sb.surface();
                let rg = RadialGradient {
                    fx: 130.0, fy: 690.0, fr: 0.0, cx: 130.0, cy: 690.0, cr: 70.0, transform: Transform::identity(),
                    spread_method: SpreadMethod::Pad,
                    stops: vec![stop(0.0, (255, 255, 255), 1.0), stop(1.0, (0, 0, 0), 1.0)],
                    anti_alias: false,
                };
                ms.set_fill(Some(Fill { paint: rg.into(), ..Default::default() }));
                ms.draw_path(&rect_path(60.0, 620.0, 140.0, 140.0));
                ms.finish();
                sb.finish()
            };
            s.push_mask(Mask::new(stream, MaskType::Luminosity));
            s.set_fill(Some(rgb_fill(0, 160, 60)));
            s.set_stroke(None);
            s.draw_path(&rect_path(60.0, 620.0, 140.0, 140.0));
            s.pop();
        });
        let alt = "Purple rectangle shown through an alpha mask made of two semi-transparent stripes";
        alts.push(alt.into());
        figure(&mut s, &mut tree, alt, |s| {
            let stream = {
                let mut sb = s.stream_builder();
                let mut ms = sb.surface();
                ms.set_fill(Some(rgb_fill_a(0, 0, 0, 1.0)));
                ms.draw_path(&rect_path(230.0, 620.0, 140.0, 60.0));
                ms.set_fill(Some(rgb_fill_a(0, 0, 0, 0.35)));
                ms.draw_path(&rect_path(230.0, 700.0, 140.0, 60.0));
                ms.finish();
                sb.finish()
            };
            s.push_mask(Mask::new(stream, MaskType::Alpha));
            s.set_fill(Some(rgb_fill(130, 0, 160)));
            s.set_stroke(None);
            s.draw_path(&rect_path(230.0, 620.0, 140.0, 140.0));
            s.pop();
        });
        let alt = "Isolated transparency group at 40 percent opacity containing two overlapping squares";
        alts.push(alt.into());
        figure(&mut s, &mut tree, alt, |s| {
            s.push_opacity(NormalizedF32::new(0.4).unwrap());
            s.push_isolated();
            s.set_fill(Some(rgb_fill(200, 0, 0)));
            s.set_stroke(None);
            s.draw_path(&rect_path(400.0, 620.0, 90.0, 90.0));
            s.set_fill(Some(rgb_fill(0, 0, 0)));
            s.draw_path(&rect_path(440.0, 660.0, 90.0, 90.0));
            s.pop();
            s.pop();
        });
        s.finish();
        page.finish();
    }
    let mut outline = Outline::new();
    outline.push_child(OutlineNode::new("Vector graphics (transparency)".into(), top_dest(0, 0.0)));
    *exp = json!({"title": expected_title("vector_transparency"), "figure_alts": alts, "page_count": 1});
    Ok(finish_doc(doc, "vector_transparency", tree, outline))
}

fn vector_postscript(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let mut alts: Vec<String> = vec![];
    {
        let mut page = doc.start_page_with(a4_page(None));
        let mut s = page.surface();
        title_block(&mut s, &mut tree, a, "Gradients that need PostScript functions")?;
        let alt = "Circle filled with a sweep (conic) gradient cycling red, yellow, blue and back to red";
        alts.push(alt.into());
        figure(&mut s, &mut tree, alt, |s| {
            let sg = SweepGradient {
                cx: 150.0, cy: 220.0, start_angle: 0.0, end_angle: 360.0, transform: Transform::identity(),
                spread_method: SpreadMethod::Pad,
                stops: vec![stop(0.0, (255, 0, 0), 1.0), stop(0.33, (255, 230, 0), 1.0), stop(0.66, (0, 60, 255), 1.0), stop(1.0, (255, 0, 0), 1.0)],
                anti_alias: false,
            };
            s.set_fill(Some(Fill { paint: sg.into(), ..Default::default() }));
            s.set_stroke(None);
            s.draw_path(&circle_path(150.0, 220.0, 90.0));
        });
        let alt = "Rectangle with a linear gradient repeated four times (repeat spread)";
        alts.push(alt.into());
        figure(&mut s, &mut tree, alt, |s| {
            let lg = LinearGradient {
                x1: 300.0, y1: 0.0, x2: 360.0, y2: 0.0, transform: Transform::identity(),
                spread_method: SpreadMethod::Repeat,
                stops: vec![stop(0.0, (0, 0, 0), 1.0), stop(1.0, (255, 255, 255), 1.0)],
                anti_alias: false,
            };
            s.set_fill(Some(Fill { paint: lg.into(), ..Default::default() }));
            s.set_stroke(None);
            s.draw_path(&rect_path(300.0, 140.0, 240.0, 160.0));
        });
        let alt = "Square with a radial gradient reflected outward (reflect spread)";
        alts.push(alt.into());
        figure(&mut s, &mut tree, alt, |s| {
            let rg = RadialGradient {
                fx: 200.0, fy: 480.0, fr: 0.0, cx: 200.0, cy: 480.0, cr: 30.0, transform: Transform::identity(),
                spread_method: SpreadMethod::Reflect,
                stops: vec![stop(0.0, (0, 120, 0), 1.0), stop(1.0, (230, 255, 230), 1.0)],
                anti_alias: false,
            };
            s.set_fill(Some(Fill { paint: rg.into(), ..Default::default() }));
            s.set_stroke(None);
            s.draw_path(&rect_path(80.0, 360.0, 240.0, 240.0));
        });
        s.finish();
        page.finish();
    }
    let mut outline = Outline::new();
    outline.push_child(OutlineNode::new("PostScript gradients".into(), top_dest(0, 0.0)));
    *exp = json!({"title": expected_title("vector_postscript"), "figure_alts": alts, "page_count": 1});
    Ok(finish_doc(doc, "vector_postscript", tree, outline))
}

// ---------------------------------------------------------------- images

#[derive(Clone, Copy)]
enum ImgKind {
    Png,
    Jpeg,
}

fn images_fixture(
    name: &str,
    title: &str,
    items: &[(&str, ImgKind, &str)],
    a: &Assets,
    settings: SerializeSettings,
    exp: &mut Value,
) -> BuildResult {
    let mut decoded = vec![];
    for (key, kind, alt) in items {
        let bytes = a.bytes("images", key)?;
        let img = match kind {
            ImgKind::Png => Image::from_png(Data::from(bytes), false),
            ImgKind::Jpeg => Image::from_jpeg(Data::from(bytes), false),
        }
        .map_err(|e| format!("image {key} rejected by krilla: {e}"))?;
        decoded.push((key.to_string(), img, alt.to_string()));
    }
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let mut info = vec![];
    {
        let mut page = doc.start_page_with(a4_page(None));
        let mut s = page.surface();
        title_block(&mut s, &mut tree, a, title)?;
        let mut y = 100.0;
        for (key, img, alt) in decoded {
            let (w, h) = img.size();
            let scale = (240.0 / w as f32).min(200.0 / h as f32);
            let (dw, dh) = (w as f32 * scale, h as f32 * scale);
            info.push(json!({"key": key, "px": [w, h], "pt_rect_pdf": pdf_rect(60.0, y, dw, dh, A4.1), "alt": alt}));
            figure(&mut s, &mut tree, &alt, |s| {
                s.push_transform(&Transform::from_translate(60.0, y));
                s.draw_image(img, Size::from_wh(dw, dh).unwrap());
                s.pop();
            });
            y += dh + 25.0;
        }
        s.finish();
        page.finish();
    }
    let mut outline = Outline::new();
    outline.push_child(OutlineNode::new(title.to_string(), top_dest(0, 0.0)));
    *exp = json!({
        "title": expected_title(name), "images": info, "page_count": 1,
        "cmyk_profile_available": a.cmyk.is_some(), "cmyk_profile_error": a.cmyk_error,
        "figure_alts": items.iter().map(|i| i.2).collect::<Vec<_>>(),
    });
    Ok(finish_doc(doc, name, tree, outline))
}

fn images_opaque(a: &Assets, st: SerializeSettings, exp: &mut Value) -> BuildResult {
    images_fixture("images_opaque", "Opaque raster images", &[
        ("rgb_png", ImgKind::Png, "Opaque RGB PNG test card with colour bars"),
        ("gray_png", ImgKind::Png, "Greyscale PNG ramp from black to white"),
        ("jpeg_rgb", ImgKind::Jpeg, "Baseline RGB JPEG test card"),
    ], a, st, exp)
}

fn images_alpha(a: &Assets, st: SerializeSettings, exp: &mut Value) -> BuildResult {
    images_fixture("images_alpha", "PNG with alpha channel", &[
        ("rgba_png", ImgKind::Png, "RGBA PNG: colour bars fading to transparent"),
    ], a, st, exp)
}

fn images_cmyk(a: &Assets, st: SerializeSettings, exp: &mut Value) -> BuildResult {
    images_fixture("images_cmyk", "CMYK JPEG", &[
        ("jpeg_cmyk", ImgKind::Jpeg, "CMYK JPEG with cyan, magenta, yellow and black patches"),
    ], a, st, exp)
}

fn images_16bit(a: &Assets, st: SerializeSettings, exp: &mut Value) -> BuildResult {
    images_fixture("images_16bit", "16-bit PNG", &[
        ("rgb16_png", ImgKind::Png, "16 bits per channel RGB PNG gradient"),
    ], a, st, exp)
}

// ---------------------------------------------------------------- navigation

fn navigation(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let latin = a.font("latin")?;
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let labels: Vec<PageLabel> = vec![
        PageLabel::new(Some(NumberingStyle::LowerRoman), None, NonZeroU32::new(1)),
        PageLabel::new(Some(NumberingStyle::LowerRoman), None, NonZeroU32::new(2)),
        arabic_label(1), arabic_label(2), arabic_label(3), arabic_label(4),
    ];
    let expected_labels = ["i", "ii", "1", "2", "3", "4"];
    let titles = ["Contents", "Preface", "Chapter 1", "Chapter 1 continued", "Chapter 2", "Appendix"];
    let h = A4.1;
    let mut links = vec![];
    for (i, label) in labels.into_iter().enumerate() {
        let mut page = doc.start_page_with(a4_page(Some(label)));
        let mut pending: Vec<(Rect, Target, String, krilla::tagging::Identifier, String)> = vec![];
        {
            let mut s = page.surface();
            let (hid, _) = tagged_run(&mut s, &latin, titles[i], 50.0, 70.0, 22.0, Some("en"), false);
            let mut hg = heading(1, titles[i]);
            hg.push(hid);
            tree.push(hg);
            if i == 2 || i == 3 {
                let sec = if i == 2 { "Section 1.1" } else { "Section 1.2" };
                let (sid, _) = tagged_run(&mut s, &latin, sec, 50.0, 400.0, 16.0, Some("en"), false);
                let mut sg = heading(2, sec);
                sg.push(sid);
                tree.push(sg);
                if i == 3 {
                    let (tid, _) = tagged_run(&mut s, &latin, "Subsection 1.2.1", 50.0, 600.0, 13.0, Some("en"), false);
                    let mut tg = heading(3, "Subsection 1.2.1");
                    tg.push(tid);
                    tree.push(tg);
                }
            }
            if i == 0 {
                let entries: Vec<(&str, Target, String)> = vec![
                    ("Go to Chapter 1 (explicit destination)", Target::Destination(top_dest(2, 0.0).into()), "goto".into()),
                    ("Go to Chapter 2 (named destination)", Target::Destination(NamedDestination::new("chapter-2".into(), top_dest(4, 0.0)).into()), "named".into()),
                    ("Visit https://example.com/phase4?q=1 (URI action)", Target::Action(Action::Link(LinkAction::new("https://example.com/phase4?q=1".into()))), "uri".into()),
                ];
                for (k, (txt, target, kind)) in entries.into_iter().enumerate() {
                    let y = 140.0 + 40.0 * k as f32;
                    let (id, sh) = tagged_run(&mut s, &latin, txt, 60.0, y, 14.0, Some("en"), false);
                    let w = sh.width(14.0);
                    let rect = Rect::from_xywh(58.0, y - 14.0, w + 4.0, 19.0).unwrap();
                    pending.push((rect, target, kind, id, txt.to_string()));
                }
            }
            s.finish();
        }
        for (rect, target, kind, id, txt) in pending {
            let rect_pdf = pdf_rect(rect.left(), rect.top(), rect.width(), rect.height(), h);
            let mut entry = json!({"page": i, "rect_pdf": rect_pdf, "kind": kind, "text": txt});
            match kind.as_str() {
                "goto" => { entry["target_page"] = json!(2); entry["target_top_pdf"] = json!(round2(h)); }
                "named" => { entry["name"] = json!("chapter-2"); entry["target_page"] = json!(4); entry["target_top_pdf"] = json!(round2(h)); }
                _ => { entry["uri"] = json!("https://example.com/phase4?q=1"); }
            }
            links.push(entry);
            let annot_id = page.add_tagged_annotation(Annotation::new_link(LinkAnnotation::new(rect, target), Some(txt.clone())));
            let mut link = TagGroup::new(Tag::Link);
            link.push(id);
            link.push(annot_id);
            let mut p = TagGroup::new(Tag::P);
            p.push(link);
            tree.push(p);
        }
        page.finish();
    }
    let nd = |name: &str, page: usize, y: f32| NamedDestination::new(name.to_string(), top_dest(page, y));
    let _ = doc.register_named_destination(nd("chapter-1", 2, 0.0));
    let _ = doc.register_named_destination(nd("appendix", 5, 0.0));

    let mut outline = Outline::new();
    let mut front = OutlineNode::new("Front matter".into(), top_dest(0, 0.0));
    front.push_child(OutlineNode::new("Contents".into(), top_dest(0, 0.0)));
    front.push_child(OutlineNode::new("Preface".into(), top_dest(1, 0.0)));
    let mut ch1 = OutlineNode::new("Chapter 1".into(), top_dest(2, 0.0));
    ch1.push_child(OutlineNode::new("Section 1.1".into(), top_dest(2, 380.0)));
    let mut s12 = OutlineNode::new("Section 1.2".into(), top_dest(3, 380.0));
    s12.push_child(OutlineNode::new("Subsection 1.2.1".into(), top_dest(3, 580.0)));
    ch1.push_child(s12);
    outline.push_child(front);
    outline.push_child(ch1);
    outline.push_child(OutlineNode::new("Chapter 2".into(), top_dest(4, 0.0)));
    outline.push_child(OutlineNode::new("Appendix".into(), top_dest(5, 0.0)));
    let o = |t: &str, p: usize, y: f32, c: Vec<Value>| json!({"title": t, "page": p, "top_pdf": round2(h - y), "children": c});
    let exp_outline = vec![
        o("Front matter", 0, 0.0, vec![o("Contents", 0, 0.0, vec![]), o("Preface", 1, 0.0, vec![])]),
        o("Chapter 1", 2, 0.0, vec![o("Section 1.1", 2, 380.0, vec![]), o("Section 1.2", 3, 380.0, vec![o("Subsection 1.2.1", 3, 580.0, vec![])])]),
        o("Chapter 2", 4, 0.0, vec![]),
        o("Appendix", 5, 0.0, vec![]),
    ];
    *exp = json!({
        "title": expected_title("navigation"), "author": "palm_bench_eval", "lang": "en",
        "page_count": 6, "page_labels": expected_labels, "links": links, "outline": exp_outline,
        "named_destinations": {"chapter-1": 2, "chapter-2": 4, "appendix": 5},
        "page_size": [round2(A4.0), round2(A4.1)],
    });
    Ok(finish_doc(doc, "navigation", tree, outline))
}

// ---------------------------------------------------------------- structure

fn structure(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let latin = a.font("latin")?;
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let mut order: Vec<Value> = vec![];
    let header = "Phase 4 structure fixture - running header";
    let mut headers = vec![];
    let mut footers = vec![];
    let mut alts = vec![];
    let mut th_scopes = vec![];
    let mut span_langs = vec![];
    let mut links = vec![];
    let n_pages = 3;
    for pi in 0..n_pages {
        let mut page = doc.start_page_with(a4_page(Some(arabic_label(pi as u32 + 1))));
        let mut pending_link: Option<(Rect, krilla::tagging::Identifier, krilla::tagging::Identifier)> = None;
        let mut pending_fr: Option<TagGroup> = None;
        {
            let mut s = page.surface();
            artifact_run(&mut s, &latin, header, 50.0, 30.0, 9.0, Art::Header);
            let footer = format!("Page {} of {}", pi + 1, n_pages);
            artifact_run(&mut s, &latin, &footer, 50.0, A4.1 - 25.0, 9.0, Art::Footer);
            headers.push(header.to_string());
            footers.push(footer);
            // decorative rule under the header, marked as an artifact
            s.start_tagged(crate::compat::artifact(Art::Other));
            s.set_fill(Some(rgb_fill(180, 180, 180)));
            s.draw_path(&rect_path(50.0, 38.0, A4.0 - 100.0, 1.0));
            s.end_tagged();

            let run = |s: &mut Surface, t: &str, x: f32, y: f32, size: f32, kind: &str, order: &mut Vec<Value>| {
                let (id, sh) = tagged_run(s, &latin, t, x, y, size, Some("en"), false);
                order.push(json!({"type": kind, "text": t}));
                (id, sh)
            };
            match pi {
                0 => {
                    let (id, _) = run(&mut s, "Structure test document", 50.0, 80.0, 22.0, "H1", &mut order);
                    let mut g = heading(1, "Structure test document");
                    g.push(id);
                    tree.push(g);
                    let (id, _) = run(&mut s, "This paragraph introduces a list and a table.", 50.0, 110.0, 12.0, "P", &mut order);
                    let mut g = TagGroup::new(Tag::P);
                    g.push(id);
                    tree.push(g);
                    let (id, _) = run(&mut s, "A numbered list", 50.0, 150.0, 16.0, "H2", &mut order);
                    let mut g = heading(2, "A numbered list");
                    g.push(id);
                    tree.push(g);
                    let mut list = TagGroup::new(Tag::L(ListNumbering::Decimal));
                    for (k, item) in ["First item", "Second item", "Third item"].iter().enumerate() {
                        let y = 180.0 + 22.0 * k as f32;
                        let lbl = format!("{}.", k + 1);
                        let (lid, _) = run(&mut s, lbl.as_str(), 60.0, y, 12.0, "Lbl", &mut order);
                        let (bid, _) = run(&mut s, *item, 80.0, y, 12.0, "LBody", &mut order);
                        let mut li = TagGroup::new(Tag::LI);
                        let mut l = TagGroup::new(Tag::Lbl);
                        l.push(lid);
                        let mut b = TagGroup::new(Tag::LBody);
                        b.push(bid);
                        li.push(l);
                        li.push(b);
                        list.push(li);
                    }
                    tree.push(list);
                    let (id, _) = run(&mut s, "A table with header scopes", 50.0, 270.0, 16.0, "H2", &mut order);
                    let mut g = heading(2, "A table with header scopes");
                    g.push(id);
                    tree.push(g);
                    let rows: [[&str; 2]; 4] = [["Item", "Count"], ["Apples", "3"], ["Pears", "5"], ["Plums", "8"]];
                    let mut table = TagGroup::new(Tag::Table);
                    let mut thead = TagGroup::new(Tag::THead);
                    let mut tbody = TagGroup::new(Tag::TBody);
                    for (r, row) in rows.iter().enumerate() {
                        let y = 300.0 + 24.0 * r as f32;
                        let mut tr = TagGroup::new(Tag::TR);
                        for (c, cell) in row.iter().enumerate() {
                            let x = 60.0 + 140.0 * c as f32;
                            if r == 0 || c == 0 {
                                let scope = if r == 0 { TableHeaderScope::Column } else { TableHeaderScope::Row };
                                let scope_name = if r == 0 { "Column" } else { "Row" };
                                th_scopes.push(json!({"text": cell, "scope": scope_name}));
                                let (id, _) = run(&mut s, *cell, x, y, 12.0, "TH", &mut order);
                                let mut th = TagGroup::new(Tag::TH(scope));
                                th.push(id);
                                tr.push(th);
                            } else {
                                let (id, _) = run(&mut s, *cell, x, y, 12.0, "TD", &mut order);
                                let mut td = TagGroup::new(Tag::TD);
                                td.push(id);
                                tr.push(td);
                            }
                        }
                        if r == 0 { thead.push(tr) } else { tbody.push(tr) }
                    }
                    // table rules are artifacts
                    s.start_tagged(crate::compat::artifact(Art::Other));
                    s.set_fill(None);
                    s.set_stroke(Some(rgb_stroke(0, 0, 0, 0.75)));
                    for r in 0..=4 {
                        let mut pb = PathBuilder::new();
                        let y = 284.0 + 24.0 * r as f32;
                        pb.move_to(55.0, y);
                        pb.line_to(335.0, y);
                        s.draw_path(&pb.finish().unwrap());
                    }
                    s.end_tagged();
                    table.push(thead);
                    table.push(tbody);
                    tree.push(table);
                }
                1 => {
                    let (id, _) = run(&mut s, "A figure with alternate text", 50.0, 80.0, 16.0, "H2", &mut order);
                    let mut g = heading(2, "A figure with alternate text");
                    g.push(id);
                    tree.push(g);
                    let (id, _) = run(&mut s, "Bar chart details", 50.0, 110.0, 13.0, "H3", &mut order);
                    let mut g = heading(3, "Bar chart details");
                    g.push(id);
                    tree.push(g);
                    let alt = "Bar chart with three bars of heights 3, 5 and 8";
                    alts.push(alt.to_string());
                    order.push(json!({"type": "Figure", "alt": alt}));
                    figure(&mut s, &mut tree, alt, |s| {
                        for (k, v) in [3.0f32, 5.0, 8.0].iter().enumerate() {
                            s.set_fill(Some(rgb_fill(40, 100 + 40 * k as u8, 200)));
                            s.set_stroke(None);
                            s.draw_path(&rect_path(70.0 + 50.0 * k as f32, 300.0 - 20.0 * v, 35.0, 20.0 * v));
                        }
                    });
                    let (pid, _) = run(&mut s, "Read more at", 50.0, 340.0, 12.0, "P", &mut order);
                    let (lid, sh) = run(&mut s, "example.org", 128.0, 340.0, 12.0, "Link", &mut order);
                    let rect = Rect::from_xywh(126.0, 328.0, sh.width(12.0) + 4.0, 16.0).unwrap();
                    links.push(json!({"page": pi, "uri": "https://example.org/", "rect_pdf": pdf_rect(rect.left(), rect.top(), rect.width(), rect.height(), A4.1)}));
                    pending_link = Some((rect, pid, lid));
                    let fr = "Bonjour tout le monde";
                    let id = {
                        let fa = &latin;
                        let (id, _) = tagged_run(&mut s, fa, fr, 50.0, 380.0, 12.0, Some("fr"), false);
                        order.push(json!({"type": "Span", "text": fr, "lang": "fr"}));
                        id
                    };
                    span_langs.push(json!({"text": fr, "lang": "fr"}));
                    let mut p = TagGroup::new(Tag::P);
                    let mut sp = TagGroup::new(Tag::Span.with_lang(Some("fr".to_string())));
                    sp.push(id);
                    p.push(sp);
                    // pushed after the link paragraph below to keep reading order
                    pending_fr = Some(p);
                }
                _ => {
                    let (id, _) = run(&mut s, "Conclusion", 50.0, 80.0, 16.0, "H2", &mut order);
                    let mut g = heading(2, "Conclusion");
                    g.push(id);
                    tree.push(g);
                    let (id, _) = run(&mut s, "The structure tree should list every element in this order.", 50.0, 110.0, 12.0, "P", &mut order);
                    let mut g = TagGroup::new(Tag::P);
                    g.push(id);
                    tree.push(g);
                }
            }
            s.finish();
        }
        if let Some((rect, pid, lid)) = pending_link {
            let target = Target::Action(Action::Link(LinkAction::new("https://example.org/".into())));
            let annot = page.add_tagged_annotation(Annotation::new_link(LinkAnnotation::new(rect, target), Some("example.org".into())));
            let mut p = TagGroup::new(Tag::P);
            p.push(pid);
            let mut link = TagGroup::new(Tag::Link);
            link.push(lid);
            link.push(annot);
            p.push(link);
            tree.push(p);
        }
        if let Some(p) = pending_fr.take() {
            tree.push(p);
        }
        page.finish();
    }
    let mut outline = Outline::new();
    outline.push_child(OutlineNode::new("Structure test document".into(), top_dest(0, 0.0)));
    outline.push_child(OutlineNode::new("A figure with alternate text".into(), top_dest(1, 0.0)));
    outline.push_child(OutlineNode::new("Conclusion".into(), top_dest(2, 0.0)));
    *exp = json!({
        "title": expected_title("structure"), "lang": "en", "page_count": n_pages,
        "reading_order": order, "headers": headers, "footers": footers, "figure_alts": alts,
        "th_scopes": th_scopes, "span_langs": span_langs, "links": links,
        "page_labels": ["1", "2", "3"],
        "required_roles": ["H1", "H2", "H3", "P", "L", "LI", "Lbl", "LBody", "Table", "TR", "TH", "TD", "Figure", "Link", "Span"],
        "optional_roles": ["THead", "TBody"],
    });
    Ok(finish_doc(doc, "structure", tree, outline))
}

// ---------------------------------------------------------------- embedded file

fn embedded_file(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let latin = a.font("latin")?;
    let xml = a.bytes("files", "embed_xml")?;
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    {
        let mut page = doc.start_page_with(a4_page(None));
        let mut s = page.surface();
        let t = "This document embeds data.xml as an associated file.";
        let (id, _) = tagged_run(&mut s, &latin, t, 50.0, 80.0, 12.0, Some("en"), false);
        let mut p = TagGroup::new(Tag::P);
        p.push(id);
        tree.push(p);
        s.finish();
        page.finish();
    }
    let size = xml.len();
    let ok = doc.embed_file(EmbeddedFile {
        path: "data.xml".to_string(),
        mime_type: MimeType::new("text/xml"),
        description: Some("Sample XML data attached to the fixture".to_string()),
        association_kind: AssociationKind::Data,
        data: Data::from(xml),
        modification_date: Some(fixed_date()),
        compress: Some(true),
        location: None,
    });
    let mut outline = Outline::new();
    outline.push_child(OutlineNode::new("Embedded file".into(), top_dest(0, 0.0)));
    *exp = json!({
        "title": expected_title("embedded_file"), "page_count": 1, "embed_accepted": ok.is_some(),
        "embedded": [{"name": "data.xml", "mime": "text/xml", "size": size, "relationship": "Data"}],
    });
    Ok(finish_doc(doc, "embedded_file", tree, outline))
}

// ---------------------------------------------------------------- page sizes

const SIZES: &[(&str, f32, f32)] = &[
    ("A4 portrait", 595.2756, 841.8898),
    ("A4 landscape", 841.8898, 595.2756),
    ("US Letter", 612.0, 792.0),
    ("US Legal", 612.0, 1008.0),
    ("Custom 400 x 250", 400.0, 250.0),
    ("Tiny 72 x 72", 72.0, 72.0),
    ("Wide 2000 x 300", 2000.0, 300.0),
];

fn page_sizes(a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let latin = a.font("latin")?;
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let mut outline = Outline::new();
    let mut sizes = vec![];
    for (i, (name, w, h)) in SIZES.iter().enumerate() {
        let mut page = doc.start_page_with(PageSettings::from_wh(*w, *h).unwrap());
        let mut s = page.surface();
        s.start_tagged(crate::compat::artifact(Art::Page));
        s.set_fill(None);
        s.set_stroke(Some(rgb_stroke(200, 0, 0, 1.0)));
        s.draw_path(&rect_path(2.0, 2.0, w - 4.0, h - 4.0));
        s.end_tagged();
        let size = if *w < 100.0 { 5.0 } else { 14.0 };
        let (id, _) = tagged_run(&mut s, &latin, name, 6.0, size * 2.0, size, Some("en"), false);
        s.finish();
        page.finish();
        let mut p = TagGroup::new(Tag::P);
        p.push(id);
        tree.push(p);
        outline.push_child(OutlineNode::new(name.to_string(), top_dest(i, 0.0)));
        sizes.push(json!({"name": name, "w": round2(*w), "h": round2(*h)}));
    }
    *exp = json!({"title": expected_title("page_sizes"), "page_count": SIZES.len(), "sizes": sizes});
    Ok(finish_doc(doc, "page_sizes", tree, outline))
}

// ---------------------------------------------------------------- long documents

fn pages_n(n: usize, a: &Assets, settings: SerializeSettings, exp: &mut Value) -> BuildResult {
    let latin = a.font("latin")?;
    let name = format!("pages_{n}");
    let mut doc = Document::new_with(settings);
    let mut tree = TagTree::new().with_lang(Some("en".to_string()));
    let mut outline = Outline::new();
    let header = "palm_bench_eval phase 4 - running header";
    let mut texts = vec![];
    for pi in 0..n {
        let mut page = doc.start_page_with(a4_page(Some(arabic_label(pi as u32 + 1))));
        let mut s = page.surface();
        artifact_run(&mut s, &latin, header, 50.0, 30.0, 9.0, Art::Header);
        artifact_run(&mut s, &latin, &format!("Page {} of {}", pi + 1, n), 50.0, A4.1 - 25.0, 9.0, Art::Footer);
        let title = format!("Section {}", pi + 1);
        let (hid, _) = tagged_run(&mut s, &latin, &title, 50.0, 70.0, 16.0, Some("en"), false);
        let mut hg = heading(if pi == 0 { 1 } else { 2 }, &title);
        hg.push(hid);
        tree.push(hg);
        let mut y = 100.0;
        for para in 0..4 {
            let mut p = TagGroup::new(Tag::P);
            for line in 0..8 {
                let t = format!(
                    "Page {} paragraph {} line {}: the quick brown fox jumps over the lazy dog.",
                    pi + 1, para + 1, line + 1
                );
                let (id, _) = tagged_run(&mut s, &latin, &t, 50.0, y, 10.0, Some("en"), false);
                p.push(id);
                if pi == 0 && para == 0 {
                    texts.push(t);
                }
                y += 14.0;
            }
            tree.push(p);
            y += 20.0;
        }
        s.finish();
        page.finish();
        outline.push_child(OutlineNode::new(title, top_dest(pi, 0.0)));
    }
    let labels: Vec<String> = (1..=n).map(|i| i.to_string()).collect();
    *exp = json!({"title": expected_title(&name), "page_count": n, "page_labels": labels, "header": header, "first_paragraph": texts});
    Ok(finish_doc(doc, &name, tree, outline))
}

fn pages_1(a: &Assets, st: SerializeSettings, exp: &mut Value) -> BuildResult {
    pages_n(1, a, st, exp)
}
fn pages_10(a: &Assets, st: SerializeSettings, exp: &mut Value) -> BuildResult {
    pages_n(10, a, st, exp)
}
fn pages_100(a: &Assets, st: SerializeSettings, exp: &mut Value) -> BuildResult {
    pages_n(100, a, st, exp)
}
