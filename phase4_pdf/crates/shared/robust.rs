// Phase 4 robustness cases. Each case runs in its own process (driven by scripts/robustness.py)
// so that a panic, abort, OOM kill or hang in one case cannot hide the others.
// A case passes if it returns Ok or Err; a panic, signal or timeout is a failure.
mod common;

#[cfg(feature = "k07")]
#[path = "compat07.rs"]
mod compat;
#[cfg(feature = "k08")]
#[path = "compat08.rs"]
mod compat;

use std::hash::{Hash, Hasher};
use std::sync::Arc;
use std::time::Instant;

use krilla::annotation::{Annotation, LinkAnnotation, Target};
use krilla::destination::XyzDestination;
use krilla::geom::{PathBuilder, Point, Rect, Size, Transform};
use krilla::image::{BitsPerComponent, CustomImage, Image, ImageColorspace};
use krilla::metadata::Metadata;
use krilla::page::PageSettings;
use krilla::tagging::{ContentTag, Tag, TagGroup, TagTree};
use krilla::text::{Font, GlyphId, KrillaGlyph};
use krilla::{Data, Document, SerializeSettings};
use serde_json::json;

use common::*;

type CaseResult = Result<String, String>;

struct Case {
    name: &'static str,
    documented_panic: bool,
    note: &'static str,
    run: fn(&Assets) -> CaseResult,
}

fn settings(p: &str) -> SerializeSettings {
    compat::settings(p, None).expect("profile")
}

fn finish(doc: Document) -> CaseResult {
    match doc.finish() {
        Ok(b) => Ok(format!("{} bytes", b.len())),
        Err(e) => {
            let (k, v) = compat::describe(&e);
            let mut v = v;
            v.truncate(5);
            Err(format!("{k}: {}", v.join(" | ")))
        }
    }
}

fn latin(a: &Assets) -> Result<Arc<FontAsset>, String> {
    a.font("latin")
}

fn one_page<F: FnOnce(&mut krilla::surface::Surface)>(p: &str, w: f32, h: f32, f: F) -> CaseResult {
    let mut doc = Document::new_with(settings(p));
    let ps = PageSettings::from_wh(w, h).ok_or("PageSettings::from_wh returned None")?;
    {
        let mut page = doc.start_page_with(ps);
        let mut s = page.surface();
        f(&mut s);
        s.finish();
        page.finish();
    }
    finish(doc)
}

fn glyph_run(a: &Assets, n: usize, profile: &str) -> CaseResult {
    let fa = latin(a)?;
    let text: String = "abcdefghij".chars().cycle().take(n).collect();
    let sh = shape(&fa, &text, false, Some("en"));
    one_page(profile, A4.0, A4.1, |s| {
        s.draw_glyphs(Point::from_xy(10.0, 100.0), &sh.glyphs, fa.font.clone(), &text, 4.0, false);
    })
}

fn glyph_runs_calls(a: &Assets) -> CaseResult {
    let fa = latin(a)?;
    let sh = shape(&fa, "word", false, Some("en"));
    one_page("none", A4.0, A4.1, |s| {
        for i in 0..10_000 {
            let (x, y) = ((i % 100) as f32 * 5.5, 20.0 + (i / 100) as f32 * 8.0);
            s.draw_glyphs(Point::from_xy(x, y), &sh.glyphs, fa.font.clone(), "word", 4.0, false);
        }
    })
}

fn huge_path(n: usize) -> CaseResult {
    let mut pb = PathBuilder::new();
    pb.move_to(0.0, 0.0);
    for i in 0..n {
        let t = i as f32 / n as f32;
        pb.line_to(300.0 + 250.0 * (t * 6283.0).sin(), 400.0 + 350.0 * (t * 997.0).cos());
    }
    pb.close();
    let path = pb.finish().ok_or("PathBuilder::finish returned None")?;
    one_page("none", A4.0, A4.1, |s| {
        s.set_fill(Some(rgb_fill(0, 0, 0)));
        s.draw_path(&path);
    })
}

fn path_coords(v: f32, profile: &str) -> CaseResult {
    let mut pb = PathBuilder::new();
    pb.move_to(0.0, 0.0);
    pb.line_to(v, 10.0);
    pb.line_to(10.0, v);
    pb.close();
    let path = pb.finish().ok_or("PathBuilder::finish returned None")?;
    one_page(profile, A4.0, A4.1, |s| {
        s.set_fill(Some(rgb_fill(0, 0, 0)));
        s.draw_path(&path);
    })
}

#[derive(Clone)]
struct RawImage {
    w: u32,
    h: u32,
    color: Arc<Vec<u8>>,
    alpha: Option<Arc<Vec<u8>>>,
    cs: ImageColorspace,
}

impl Hash for RawImage {
    fn hash<H: Hasher>(&self, st: &mut H) {
        self.w.hash(st);
        self.h.hash(st);
        self.color.len().hash(st);
        self.color.get(..4096.min(self.color.len())).hash(st);
    }
}

impl CustomImage for RawImage {
    fn color_channel(&self) -> &[u8] {
        &self.color
    }
    fn alpha_channel(&self) -> Option<&[u8]> {
        self.alpha.as_ref().map(|a| a.as_slice())
    }
    fn bits_per_component(&self) -> BitsPerComponent {
        BitsPerComponent::Eight
    }
    fn size(&self) -> (u32, u32) {
        (self.w, self.h)
    }
    fn icc_profile(&self) -> Option<&[u8]> {
        None
    }
    fn color_space(&self) -> ImageColorspace {
        self.cs
    }
}

fn draw_image_case(img: Image) -> CaseResult {
    one_page("none", A4.0, A4.1, |s| {
        s.push_transform(&Transform::from_translate(10.0, 10.0));
        s.draw_image(img, Size::from_wh(500.0, 500.0).unwrap());
        s.pop();
    })
}

fn image_16k_luma(_: &Assets) -> CaseResult {
    let n = 16384usize;
    let mut v = vec![0u8; n * n];
    for (i, px) in v.iter_mut().enumerate() {
        *px = ((i % n) ^ (i / n)) as u8;
    }
    let img = Image::from_custom(RawImage { w: n as u32, h: n as u32, color: Arc::new(v), alpha: None, cs: ImageColorspace::Luma }, false)?;
    draw_image_case(img)
}

fn image_16k_rgba8(_: &Assets) -> CaseResult {
    let n = 16384usize;
    let mut v = vec![0u8; n * n * 4];
    for (i, px) in v.chunks_exact_mut(4).enumerate() {
        px[0] = (i % n) as u8;
        px[1] = (i / n) as u8;
        px[2] = 128;
        px[3] = 255;
    }
    draw_image_case(Image::from_rgba8(v, n as u32, n as u32))
}

fn image_file(a: &Assets, key: &str, jpeg: bool, mutate: fn(Vec<u8>) -> Vec<u8>) -> CaseResult {
    let bytes = mutate(a.bytes("images", key)?);
    let img = (if jpeg { Image::from_jpeg(Data::from(bytes), false) } else { Image::from_png(Data::from(bytes), false) })?;
    draw_image_case(img)
}

fn truncate_half(v: Vec<u8>) -> Vec<u8> {
    let n = v.len() / 2;
    v[..n].to_vec()
}
fn identity(v: Vec<u8>) -> Vec<u8> {
    v
}
fn garbage(_: Vec<u8>) -> Vec<u8> {
    (0..4096u32).map(|i| (i.wrapping_mul(2654435761) >> 13) as u8).collect()
}
fn empty(_: Vec<u8>) -> Vec<u8> {
    vec![]
}

fn font_bytes(bytes: Vec<u8>) -> CaseResult {
    match Font::new(Data::from(bytes), 0) {
        None => Err("Font::new returned None".into()),
        Some(f) => one_page("none", A4.0, A4.1, |s| {
            let g = [KrillaGlyph::new(GlyphId::new(1), 0.5, 0.0, 0.0, 0.0, 0..1, None)];
            s.draw_glyphs(Point::from_xy(50.0, 50.0), &g, f, "a", 12.0, false);
        }),
    }
}

fn font_size(a: &Assets, size: f32) -> CaseResult {
    let fa = latin(a)?;
    let sh = shape(&fa, "Hello", false, Some("en"));
    one_page("none", A4.0, A4.1, |s| {
        s.draw_glyphs(Point::from_xy(50.0, 400.0), &sh.glyphs, fa.font.clone(), "Hello", size, false);
    })
}

fn nesting(depth: usize, profile: &str) -> CaseResult {
    one_page(profile, A4.0, A4.1, |s| {
        for i in 0..depth {
            if i % 2 == 0 {
                s.push_transform(&Transform::from_translate(0.01, 0.01));
            } else {
                s.push_clip_path(&rect_path(0.0, 0.0, 500.0, 500.0), &krilla::paint::FillRule::NonZero);
            }
        }
        s.set_fill(Some(rgb_fill(0, 0, 0)));
        s.draw_path(&rect_path(10.0, 10.0, 50.0, 50.0));
        for _ in 0..depth {
            s.pop();
        }
    })
}

fn many_links(n: usize, profile: &str) -> CaseResult {
    let mut doc = Document::new_with(settings(profile));
    {
        let mut page = doc.start_page_with(PageSettings::from_wh(A4.0, A4.1).unwrap());
        for i in 0..n {
            let (x, y) = ((i % 100) as f32 * 5.0, (i / 100) as f32 * 5.0 + 5.0);
            let r = Rect::from_xywh(x, y, 4.0, 4.0).unwrap();
            page.add_annotation(LinkAnnotation::new(r, Target::Destination(XyzDestination::new(0, Point::from_xy(0.0, 0.0)).into())).into());
        }
        page.finish();
    }
    finish(doc)
}

fn tagged_doc(variant: &str, a: &Assets) -> CaseResult {
    let fa = latin(a)?;
    let mut doc = Document::new_with(settings("none"));
    let mut tree = TagTree::new();
    {
        let mut page = doc.start_page_with(PageSettings::from_wh(A4.0, A4.1).unwrap());
        let mut s = page.surface();
        let (id, _) = tagged_run(&mut s, &fa, "tagged", 50.0, 50.0, 12.0, Some("en"), false);
        match variant {
            "twice" => {
                let mut g1 = TagGroup::new(Tag::P);
                g1.push(id);
                let mut g2 = TagGroup::new(Tag::P);
                g2.push(id);
                tree.push(g1);
                tree.push(g2);
            }
            "unused" => {}
            "nested_start" => {
                s.start_tagged(ContentTag::Other);
                s.start_tagged(ContentTag::Other);
                s.end_tagged();
                s.end_tagged();
            }
            "end_without_start" => {
                s.end_tagged();
            }
            _ => {}
        }
        s.finish();
        page.finish();
    }
    doc.set_tag_tree(tree);
    finish(doc)
}

fn link_missing_page(_: &Assets) -> CaseResult {
    let mut doc = Document::new_with(settings("none"));
    {
        let mut page = doc.start_page_with(PageSettings::from_wh(A4.0, A4.1).unwrap());
        let r = Rect::from_xywh(10.0, 10.0, 50.0, 20.0).unwrap();
        page.add_annotation(Annotation::new_link(LinkAnnotation::new(r, Target::Destination(XyzDestination::new(99, Point::from_xy(0.0, 0.0)).into())), Some("broken".into())));
        page.finish();
    }
    finish(doc)
}

fn long_title(_: &Assets) -> CaseResult {
    let mut doc = Document::new_with(settings("a2b"));
    doc.set_metadata(Metadata::new().title("x".repeat(40_000)).creation_date(fixed_date()));
    doc.start_page_with(PageSettings::from_wh(A4.0, A4.1).unwrap()).finish();
    finish(doc)
}

fn many_pages(n: usize) -> CaseResult {
    let mut doc = Document::new_with(settings("none"));
    for _ in 0..n {
        let mut page = doc.start_page_with(PageSettings::from_wh(200.0, 200.0).unwrap());
        let mut s = page.surface();
        s.set_fill(Some(rgb_fill(0, 0, 0)));
        s.draw_path(&rect_path(10.0, 10.0, 20.0, 20.0));
        s.finish();
        page.finish();
    }
    finish(doc)
}

fn cases() -> Vec<Case> {
    vec![
    Case { name: "glyphs_single_run_10k", documented_panic: false, note: "one draw_glyphs call with 10,000 glyphs", run: |a| glyph_run(a, 10_000, "none") },
    Case { name: "glyphs_single_run_100k", documented_panic: false, note: "one draw_glyphs call with 100,000 glyphs", run: |a| glyph_run(a, 100_000, "none") },
    Case { name: "glyphs_single_run_10k_a1b", documented_panic: false, note: "10,000-glyph TJ under PDF 1.4 (array limit 8191)", run: |a| glyph_run(a, 10_000, "a1b") },
    Case { name: "glyph_runs_10k_calls", documented_panic: false, note: "10,000 separate draw_glyphs calls on one page", run: glyph_runs_calls },
    Case { name: "path_1m_segments", documented_panic: false, note: "one path with 1,000,000 line segments", run: |_| huge_path(1_000_000) },
    Case { name: "path_nan_coords", documented_panic: false, note: "NaN coordinate", run: |_| path_coords(f32::NAN, "none") },
    Case { name: "path_inf_coords", documented_panic: false, note: "infinite coordinate", run: |_| path_coords(f32::INFINITY, "none") },
    Case { name: "path_1e30_coords", documented_panic: false, note: "coordinate 1e30", run: |_| path_coords(1e30, "none") },
    Case { name: "path_1e30_coords_a1b", documented_panic: false, note: "coordinate 1e30 under PDF 1.4 (float limit 32767)", run: |_| path_coords(1e30, "a1b") },
    Case { name: "page_zero_size", documented_panic: false, note: "0 x 0 page", run: |_| one_page("none", 0.0, 0.0, |_| {}) },
    Case { name: "page_zero_width", documented_panic: false, note: "0 x 100 page", run: |_| one_page("none", 0.0, 100.0, |_| {}) },
    Case { name: "page_negative_size", documented_panic: false, note: "-100 x -100 page", run: |_| one_page("none", -100.0, -100.0, |_| {}) },
    Case { name: "page_nan_size", documented_panic: false, note: "NaN page size", run: |_| one_page("none", f32::NAN, 100.0, |_| {}) },
    Case { name: "page_200k_square", documented_panic: false, note: "200,000 pt page", run: |_| one_page("none", 200_000.0, 200_000.0, |s| { s.set_fill(Some(rgb_fill(0, 0, 0))); s.draw_path(&rect_path(10.0, 10.0, 100.0, 100.0)); }) },
    Case { name: "page_200k_square_a1b", documented_panic: false, note: "200,000 pt page under PDF 1.4", run: |_| one_page("a1b", 200_000.0, 200_000.0, |_| {}) },
    Case { name: "media_box_zero_area", documented_panic: false, note: "media box with zero area", run: |_| {
        let r = Rect::from_xywh(0.0, 0.0, 0.0, 0.0).ok_or("Rect::from_xywh returned None")?;
        let mut doc = Document::new_with(settings("none"));
        doc.start_page_with(PageSettings::from_wh(100.0, 100.0).unwrap().with_media_box(Some(r))).finish();
        finish(doc)
    } },
    Case { name: "image_16k_luma_custom", documented_panic: false, note: "16384 x 16384 8-bit grey CustomImage (256 MiB)", run: image_16k_luma },
    Case { name: "image_16k_rgba8", documented_panic: false, note: "16384 x 16384 RGBA from_rgba8 (1 GiB)", run: image_16k_rgba8 },
    Case { name: "image_16k_png", documented_panic: false, note: "16384 x 16384 PNG file decoded by krilla", run: |a| image_file(a, "png_16k", false, identity) },
    Case { name: "image_custom_wrong_len", documented_panic: true, note: "CustomImage whose buffer is shorter than w*h (from_custom docs: panics)", run: |_| {
        let img = Image::from_custom(RawImage { w: 100, h: 100, color: Arc::new(vec![0u8; 10]), alpha: None, cs: ImageColorspace::Luma }, false)?;
        draw_image_case(img)
    } },
    Case { name: "image_rgba8_short_buffer", documented_panic: false, note: "from_rgba8 with 10 bytes for a 100x100 image", run: |_| draw_image_case(Image::from_rgba8(vec![0u8; 10], 100, 100)) },
    Case { name: "image_rgba8_zero_size", documented_panic: false, note: "from_rgba8 0 x 0", run: |_| draw_image_case(Image::from_rgba8(vec![], 0, 0)) },
    Case { name: "png_truncated", documented_panic: false, note: "PNG cut in half", run: |a| image_file(a, "rgb_png", false, truncate_half) },
    Case { name: "png_garbage", documented_panic: false, note: "4 KiB of pseudo-random bytes as PNG", run: |a| image_file(a, "rgb_png", false, garbage) },
    Case { name: "png_empty", documented_panic: false, note: "zero-byte PNG", run: |a| image_file(a, "rgb_png", false, empty) },
    Case { name: "jpeg_truncated", documented_panic: false, note: "JPEG cut in half", run: |a| image_file(a, "jpeg_rgb", true, truncate_half) },
    Case { name: "jpeg_garbage", documented_panic: false, note: "4 KiB of pseudo-random bytes as JPEG", run: |a| image_file(a, "jpeg_rgb", true, garbage) },
    Case { name: "font_garbage", documented_panic: false, note: "pseudo-random bytes as a font", run: |_| font_bytes(garbage(vec![])) },
    Case { name: "font_truncated", documented_panic: false, note: "first 2 KiB of the Latin font", run: |a| {
        let p = latin(a)?.path.clone();
        let b = std::fs::read(&p).map_err(|e| e.to_string())?;
        font_bytes(b[..2048.min(b.len())].to_vec())
    } },
    Case { name: "font_size_zero", documented_panic: false, note: "font size 0", run: |a| font_size(a, 0.0) },
    Case { name: "font_size_negative", documented_panic: false, note: "font size -12", run: |a| font_size(a, -12.0) },
    Case { name: "font_size_1e6", documented_panic: false, note: "font size 1e6", run: |a| font_size(a, 1e6) },
    Case { name: "font_size_nan", documented_panic: false, note: "font size NaN", run: |a| font_size(a, f32::NAN) },
    Case { name: "glyph_empty_run", documented_panic: false, note: "draw_glyphs with no glyphs", run: |a| {
        let fa = latin(a)?;
        let g: [KrillaGlyph; 0] = [];
        one_page("none", A4.0, A4.1, |s| s.draw_glyphs(Point::from_xy(0.0, 0.0), &g, fa.font.clone(), "", 12.0, false))
    } },
    Case { name: "glyph_text_range_out_of_bounds", documented_panic: false, note: "glyph text_range 0..1000 on a 1-byte string", run: |a| {
        let fa = latin(a)?;
        let g = [KrillaGlyph::new(GlyphId::new(36), 0.5, 0.0, 0.0, 0.0, 0..1000, None)];
        one_page("none", A4.0, A4.1, |s| s.draw_glyphs(Point::from_xy(50.0, 50.0), &g, fa.font.clone(), "a", 12.0, false))
    } },
    Case { name: "glyph_id_out_of_range", documented_panic: false, note: "glyph id 65000 (beyond the font's glyph count)", run: |a| {
        let fa = latin(a)?;
        let g = [KrillaGlyph::new(GlyphId::new(65000), 0.5, 0.0, 0.0, 0.0, 0..1, None)];
        one_page("none", A4.0, A4.1, |s| s.draw_glyphs(Point::from_xy(50.0, 50.0), &g, fa.font.clone(), "a", 12.0, false))
    } },
    Case { name: "nesting_1000", documented_panic: false, note: "1000 nested transforms/clips", run: |_| nesting(1000, "none") },
    Case { name: "nesting_1000_a2b", documented_panic: false, note: "1000 nested transforms/clips under PDF/A-2b (q limit 28)", run: |_| nesting(1000, "a2b") },
    Case { name: "pages_10k", documented_panic: false, note: "10,000 pages (100x the product cap)", run: |_| many_pages(10_000) },
    Case { name: "links_10k_one_page", documented_panic: false, note: "10,000 link annotations on one page", run: |_| many_links(10_000, "none") },
    Case { name: "links_10k_one_page_a1b", documented_panic: false, note: "10,000 annotations under PDF 1.4 (array limit 8191)", run: |_| many_links(10_000, "a1b") },
    Case { name: "link_to_missing_page", documented_panic: true, note: "XyzDestination to page 99 of a 1-page document (krilla source: panics)", run: link_missing_page },
    Case { name: "tag_identifier_twice", documented_panic: false, note: "one identifier placed in two tag groups", run: |a| tagged_doc("twice", a) },
    Case { name: "tag_identifier_unused", documented_panic: false, note: "identifier never placed in the tag tree", run: |a| tagged_doc("unused", a) },
    Case { name: "tag_nested_start", documented_panic: true, note: "start_tagged inside start_tagged (docs: panics)", run: |a| tagged_doc("nested_start", a) },
    Case { name: "tag_end_without_start", documented_panic: true, note: "end_tagged without start_tagged (docs: panics)", run: |a| tagged_doc("end_without_start", a) },
    Case { name: "title_40k_chars_a2b", documented_panic: false, note: "40,000-character title under PDF/A-2b (string limit 32767)", run: long_title },
    Case { name: "empty_document", documented_panic: false, note: "document with no pages", run: |_| finish(Document::new()) },
    ]
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(|s| s.as_str()) {
        Some("list") => {
            let v: Vec<_> = cases().iter().map(|c| json!({"name": c.name, "documented_panic": c.documented_panic, "note": c.note})).collect();
            println!("{}", json!({"krilla_version": compat::KRILLA_VERSION, "cases": v}));
        }
        Some("case") => {
            let name = args.get(2).expect("case name");
            let manifest = args.iter().position(|a| a == "--manifest").and_then(|i| args.get(i + 1)).expect("--manifest");
            let a = Assets::load(manifest).expect("manifest");
            let all = cases();
            let c = all.iter().find(|c| c.name == name.as_str()).expect("unknown case");
            let t0 = Instant::now();
            let r = (c.run)(&a);
            let ms = t0.elapsed().as_secs_f64() * 1000.0;
            let (outcome, detail) = match r {
                Ok(d) => ("ok", d),
                Err(e) => ("err", e),
            };
            println!("{}", json!({"case": c.name, "outcome": outcome, "detail": detail, "ms": ms}));
        }
        _ => {
            eprintln!("usage: robust list | robust case NAME --manifest M");
            std::process::exit(2);
        }
    }
}
