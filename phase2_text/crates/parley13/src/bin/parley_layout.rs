use p2_parley13::load_corpus;
use parley::{FontContext, Language, Layout, LayoutContext, StyleProperty};
use parley_engine::{AnalysisDataSources, AnalysisOptions, Analyzer, Analysis, LineBreakConfig};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::time::Instant;

const MAX_FAILURES: usize = 20;
const WIDTHS: [f32; 3] = [160.0, 320.0, 640.0];
const FONT_SIZE: f32 = 16.0;
const EPS: f32 = 0.5;
const TIMING_PARAGRAPHS: usize = 1000;
const TIMING_WIDTH: f32 = 320.0;

fn build(lcx: &mut LayoutContext<()>, fcx: &mut FontContext, text: &str, lang: Option<Language>) -> Layout<()> {
    let mut b = lcx.ranged_builder(fcx, text, 1.0, true);
    b.push_default(StyleProperty::FontSize(FONT_SIZE));
    b.push_default(StyleProperty::Locale(lang));
    b.build(text)
}

fn soft_wrap_offsets(analyzer: &mut Analyzer, text: &str, lang: Option<Language>) -> Vec<usize> {
    let cfg = [(0..text.len(), LineBreakConfig { language: lang, ..Default::default() })];
    let opts = AnalysisOptions { line_break: &cfg, ..Default::default() };
    let mut analysis = Analysis::new();
    analyzer.analyze(text, &opts, &mut analysis, &AnalysisDataSources::default());
    text.char_indices()
        .zip(analysis.char_info().iter())
        .filter(|(_, info)| info.is_soft_wrap_opportunity())
        .map(|((b, _), _)| b)
        .collect()
}

#[derive(Default)]
struct GroupStats {
    layouts: u64,
    pass: u64,
    lines: u64,
    overflow_violations: u64,
    unbreakable_overflows: u64,
    order_errors: u64,
    notdef_glyphs: u64,
    glyphs: u64,
    ms_per_1k: f64,
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: parley_layout <corpus.json> <results.json>");
        std::process::exit(2);
    }
    let corpus = load_corpus(&args[1]);
    let mut fcx = FontContext::new();
    let mut lcx: LayoutContext<()> = LayoutContext::new();
    let mut analyzer = Analyzer::new();
    let mut per_entry: BTreeMap<String, GroupStats> = BTreeMap::new();
    let mut failures = Vec::new();
    let mut unbreakable_examples = Vec::new();

    for e in &corpus {
        let lang = Language::parse(&e.lang).ok();
        let st = per_entry.entry(e.id.clone()).or_default();
        for (pi, text) in e.lines.iter().enumerate() {
            let opportunities = soft_wrap_offsets(&mut analyzer, text, lang);
            let mut layout = build(&mut lcx, &mut fcx, text, lang);
            for &w in &WIDTHS {
                layout.break_all_lines(Some(w));
                st.layouts += 1;
                let mut ok = true;
                let mut problems: Vec<Value> = Vec::new();
                let mut expected_start = 0usize;
                for (li, line) in layout.lines().enumerate() {
                    st.lines += 1;
                    let r = line.text_range();
                    if r.start != expected_start {
                        ok = false;
                        st.order_errors += 1;
                        problems.push(json!({"line": li, "kind": "text_gap_or_overlap", "expected_start": expected_start, "range": [r.start, r.end]}));
                    }
                    expected_start = r.end;
                    let mut clusters: Vec<(usize, usize)> = Vec::new();
                    for run in line.runs() {
                        for cl in run.clusters() {
                            let cr = cl.text_range();
                            clusters.push((cr.start, cr.end));
                            for g in cl.glyphs() {
                                st.glyphs += 1;
                                if g.id == 0 {
                                    st.notdef_glyphs += 1;
                                }
                            }
                        }
                    }
                    clusters.sort_unstable();
                    let mut pos = r.start;
                    let mut covered = true;
                    for (s, en) in &clusters {
                        if *s != pos {
                            covered = false;
                            break;
                        }
                        pos = *en;
                    }
                    if !clusters.is_empty() && pos != r.end {
                        covered = false;
                    }
                    if !covered {
                        ok = false;
                        st.order_errors += 1;
                        problems.push(json!({"line": li, "kind": "clusters_do_not_tile_line", "range": [r.start, r.end]}));
                    }
                    let m = line.metrics();
                    let content = m.advance - m.hanging_advance;
                    if content > w + EPS {
                        let trimmed_end = text[r.start..r.end].trim_end().len() + r.start;
                        let internal = opportunities.iter().any(|&b| b > r.start && b < trimmed_end);
                        if internal {
                            ok = false;
                            st.overflow_violations += 1;
                            problems.push(json!({"line": li, "kind": "overflow_with_break_opportunity", "width": w, "content_advance": content, "text": &text[r.start..r.end]}));
                        } else {
                            st.unbreakable_overflows += 1;
                            if unbreakable_examples.len() < MAX_FAILURES {
                                unbreakable_examples.push(json!({"entry": e.id, "paragraph": pi, "width": w, "content_advance": content, "text": &text[r.start..r.end]}));
                            }
                        }
                    }
                }
                if expected_start != text.len() {
                    ok = false;
                    st.order_errors += 1;
                    problems.push(json!({"kind": "text_not_fully_laid_out", "laid_out_to": expected_start, "text_len": text.len()}));
                }
                if ok {
                    st.pass += 1;
                } else if failures.len() < MAX_FAILURES {
                    failures.push(json!({"entry": e.id, "paragraph": pi, "width": w, "problems": problems.into_iter().take(5).collect::<Vec<_>>()}));
                }
            }
        }
        if !e.lines.is_empty() {
            let t0 = Instant::now();
            let mut sink = 0usize;
            for i in 0..TIMING_PARAGRAPHS {
                let text = &e.lines[i % e.lines.len()];
                let mut layout = build(&mut lcx, &mut fcx, text, lang);
                layout.break_all_lines(Some(TIMING_WIDTH));
                sink += layout.len();
            }
            st.ms_per_1k = t0.elapsed().as_secs_f64() * 1000.0 * (1000.0 / TIMING_PARAGRAPHS as f64);
            std::hint::black_box(sink);
        }
        println!("{}: {}/{} layouts ok, {:.1} ms per 1k paragraphs", e.id, st.pass, st.layouts, st.ms_per_1k);
    }

    let (mut pass, mut total, mut ms_sum, mut n_ms) = (0u64, 0u64, 0f64, 0u64);
    let mut entries = serde_json::Map::new();
    for (id, s) in &per_entry {
        pass += s.pass;
        total += s.layouts;
        if s.ms_per_1k > 0.0 {
            ms_sum += s.ms_per_1k;
            n_ms += 1;
        }
        entries.insert(id.clone(), json!({
            "layouts": s.layouts, "pass": s.pass, "lines": s.lines,
            "overflow_violations": s.overflow_violations,
            "unbreakable_overflows": s.unbreakable_overflows,
            "order_errors": s.order_errors,
            "glyphs": s.glyphs, "notdef_glyphs": s.notdef_glyphs,
            "ms_per_1k_paragraphs": s.ms_per_1k,
        }));
    }
    let result = json!({
        "test": "parley_layout",
        "parley_version": "0.13.0",
        "features": ["system", "complex-scripts"],
        "font_size_px": FONT_SIZE,
        "widths_px": WIDTHS,
        "pass": pass,
        "fail": total - pass,
        "total": total,
        "pass_rate": if total > 0 { pass as f64 / total as f64 } else { 0.0 },
        "pass_criterion": "per (paragraph, width): line text ranges tile the paragraph in order from 0 to its end, the clusters of each line tile the line's range, and no line's advance (excluding hanging whitespace) exceeds the width by more than 0.5 px unless the line has no internal soft-wrap opportunity (then it is an unbreakable overflow, reported but not failed)",
        "mean_ms_per_1k_paragraphs": if n_ms > 0 { ms_sum / n_ms as f64 } else { 0.0 },
        "timing_method": format!("build + break_all_lines at {TIMING_WIDTH} px for {TIMING_PARAGRAPHS} paragraphs cycled from each sample, single thread, release build, shared FontContext/LayoutContext"),
        "notes": [
            "Soft-wrap opportunities used to classify overflowing lines come from parley_engine::Analyzer with the same language, i.e. Parley's own UAX #14 analysis.",
            "notdef_glyphs counts glyph id 0 in the output, i.e. characters Parley's font fallback could not cover."
        ],
        "entries": entries,
        "unbreakable_overflow_examples": unbreakable_examples,
        "first_failures": failures,
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&result).unwrap()).expect("write results");
}
