use krilla::geom::Size;
use krilla::page::PageSettings;
use krilla::Document;
use krilla_svg::{SurfaceExt, SvgSettings};
use p3common::Raw;
use std::path::Path;
use std::sync::Arc;
use usvg::fontdb;

/// `svg <in.svg> <out.pdf> <width_px> <height_px> <fonts_dir>`
///
/// Font setup and usvg::Options copy resvg's integration harness at v0.45.1
/// (crates/resvg/tests/integration/main.rs:17-45).
fn svg(args: &[String]) -> Result<Option<Raw>, String> {
    if args.len() < 5 {
        return Err("usage: svg <in.svg> <out.pdf> <width_px> <height_px> <fonts_dir>".into());
    }
    let w: f32 = args[2].parse().map_err(|_| "bad width")?;
    let h: f32 = args[3].parse().map_err(|_| "bad height")?;
    let mut db = fontdb::Database::new();
    db.load_fonts_dir(&args[4]);
    db.set_serif_family("Noto Serif");
    db.set_sans_serif_family("Noto Sans");
    db.set_cursive_family("Yellowtail");
    db.set_fantasy_family("Sedgwick Ave Display");
    db.set_monospace_family("Noto Mono");
    let svg_path = Path::new(&args[0]);
    let opt = usvg::Options {
        resources_dir: svg_path.parent().map(|p| p.to_path_buf()),
        fontdb: Arc::new(db),
        ..usvg::Options::default()
    };
    let data = std::fs::read(svg_path).map_err(|e| format!("read: {e}"))?;
    let tree = usvg::Tree::from_data(&data, &opt).map_err(|e| format!("usvg: {e}"))?;
    let size = Size::from_wh(w, h).ok_or("zero size")?;
    let mut doc = Document::new();
    let mut page = doc.start_page_with(PageSettings::new(size));
    let mut surface = page.surface();
    let drawn = surface.draw_svg(&tree, size, SvgSettings::default());
    surface.finish();
    page.finish();
    if drawn.is_none() {
        return Err("krilla-svg draw_svg returned None".into());
    }
    let pdf = doc.finish().map_err(|e| format!("krilla: {e:?}"))?;
    std::fs::write(&args[1], pdf).map_err(|e| format!("write: {e}"))?;
    Ok(None)
}

fn run(sub: &str, args: &[String]) -> Result<Option<Raw>, String> {
    match sub {
        "svg" => svg(args),
        other => Err(format!("unknown subcommand {other}")),
    }
}

fn main() {
    p3common::dispatch(run)
}
