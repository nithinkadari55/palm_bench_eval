// spike-rkboa: raikiri's own crates/raikiri-js (Boa 0.22) driven the same way as spike-rkjs:
// a DocumentHost over the same live raikiri_dom::Document, the same synchronous relayout for
// geometry (spike-common/pipeline.rs) and the same fulgur-raikiri PDF path.
#[path = "../../spike-common/pipeline.rs"]
mod pipeline;

use pipeline::{diagnostics_json, ms_since, parse_args, write_json, Pipeline, Rect, USAGE};
use raikiri_dom::Document;
use raikiri_js::runtime::{BoxGeometry, DocumentHost, DomRect, DomRuntime, HostError, PositionKind};
use std::any::Any;
use std::collections::HashMap;
use std::time::Instant;

struct SpikeHost {
    doc: Document,
    pipeline: Pipeline,
    rects: HashMap<usize, Rect>,
    relayout_ms: Vec<f64>,
    geometry_queries: usize,
    diags: Vec<(String, String)>,
}

fn dom_rect(r: &Rect) -> DomRect {
    DomRect { left: r.x, top: r.y, right: r.x + r.w, bottom: r.y + r.h, width: r.w, height: r.h }
}

impl DocumentHost for SpikeHost {
    fn document(&self) -> &Document {
        &self.doc
    }

    fn document_mut(&mut self) -> &mut Document {
        &mut self.doc
    }

    /// The runtime calls this only when a mutation happened since the last flush.
    fn flush(&mut self) -> Result<(), HostError> {
        let t = Instant::now();
        let result = self.pipeline.layout_live(&self.doc);
        self.relayout_ms.push(ms_since(t));
        match result {
            Ok(snapshot) => {
                self.rects = snapshot.rects;
                Ok(())
            }
            Err(e) => {
                self.diags.push(("js:relayout-error".to_string(), e.clone()));
                Err(HostError(e))
            }
        }
    }

    fn box_geometry(&mut self, node: usize) -> Result<Option<BoxGeometry>, HostError> {
        self.geometry_queries += 1;
        Ok(self.rects.get(&node).map(|r| {
            let rect = dom_rect(r);
            BoxGeometry {
                border_box: rect,
                padding_box: rect,
                scroll_width: r.w,
                scroll_height: r.h,
                position: PositionKind::Static,
                is_inline: false,
            }
        }))
    }

    fn viewport_size(&mut self) -> Result<Option<(f64, f64)>, HostError> {
        Ok(Some((self.pipeline.width_px as f64, self.pipeline.height_px as f64)))
    }

    fn computed_value(&mut self, _node: usize, _property: &str) -> Result<Option<String>, HostError> {
        Ok(None)
    }

    fn parse_fragment(&mut self, context_tag: &str, context_ns: &str, markup: &str) -> Result<Document, HostError> {
        let options = raikiri_html::ParseOptions::new();
        raikiri_html::parse_fragment(markup.as_bytes(), &options, context_tag, context_ns, false)
            .map(|fragment| fragment.dom)
            .map_err(|e| HostError(format!("fragment parse failed: {e}")))
    }

    fn document_url(&self) -> Option<String> {
        Some(self.pipeline.document_url.to_string())
    }

    fn fetch_script(&mut self, url: &str) -> Result<String, HostError> {
        let parsed = url::Url::parse(url).map_err(|e| HostError(format!("{url}: {e}")))?;
        self.pipeline.read_script_url(&parsed).map_err(HostError)
    }

    fn as_any(&self) -> &dyn Any {
        self
    }

    fn as_any_mut(&mut self) -> &mut dyn Any {
        self
    }

    fn into_any(self: Box<Self>) -> Box<dyn Any> {
        self
    }
}

/// Script evaluation and the synchronous relayouts it triggers share one native stack, so
/// the whole render runs on a thread with a large stack.
fn main() {
    let child = std::thread::Builder::new()
        .name("render".to_string())
        .stack_size(256 * 1024 * 1024)
        .spawn(run_main)
        .expect("spawn render thread");
    if child.join().is_err() {
        eprintln!("spike-rkboa: render thread panicked");
        std::process::exit(101);
    }
}

fn run_main() {
    pipeline::install_logger();
    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("spike-rkboa: {e}\n{USAGE}");
            std::process::exit(1);
        }
    };
    let total = Instant::now();
    let pipeline = match Pipeline::new(&args) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("spike-rkboa: {e}");
            std::process::exit(1);
        }
    };
    let html = match std::fs::read(&args.input) {
        Ok(h) => h,
        Err(e) => {
            eprintln!("spike-rkboa: {}: {e}", args.input.display());
            std::process::exit(1);
        }
    };
    let t_parse = Instant::now();
    let parsed = match raikiri_html::parse(html.as_slice(), &raikiri_html::ParseOptions::new()) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("spike-rkboa: parse failed: {e}");
            std::process::exit(2);
        }
    };
    let parse_ms = ms_since(t_parse);
    let host = SpikeHost {
        doc: parsed.dom,
        pipeline,
        rects: HashMap::new(),
        relayout_ms: Vec::new(),
        geometry_queries: 0,
        diags: Vec::new(),
    };

    let t_init = Instant::now();
    let mut runtime = match DomRuntime::new(host) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("spike-rkboa: runtime: {e}");
            std::process::exit(2);
        }
    };
    let init_ms = ms_since(t_init);
    let t_js = Instant::now();
    let report = runtime.run_document();
    let js_ms = ms_since(t_js);
    let mut host: SpikeHost = match runtime.try_into_host::<SpikeHost>() {
        Ok(h) => h,
        Err(_) => {
            eprintln!("spike-rkboa: could not recover the document host");
            std::process::exit(2);
        }
    };

    for e in &report.uncaught_errors {
        host.diags.push(("js:uncaught".to_string(), e.clone()));
    }
    for e in &report.fetch_errors {
        host.diags.push(("js:fetch-error".to_string(), e.clone()));
    }
    for e in &report.host_failures {
        host.diags.push(("js:host".to_string(), e.clone()));
    }
    for (level, message) in &report.console {
        host.diags.push((format!("js:console.{level}"), message.clone()));
    }
    if let Some(abort) = &report.aborted {
        host.diags.push(("js:abort".to_string(), abort.to_string()));
    }

    let t_ser = Instant::now();
    let final_html = match pipeline::serialize_document(&host.doc) {
        Ok(h) => h,
        Err(e) => {
            eprintln!("spike-rkboa: serialize failed: {e}");
            std::process::exit(2);
        }
    };
    let serialize_ms = ms_since(t_ser);
    if let Some(p) = &args.dump_html {
        let _ = std::fs::write(p, &final_html);
    }
    let t_render = Instant::now();
    let pdf = host.pipeline.render_pdf(&final_html);
    let render_ms = ms_since(t_render);
    let final_layout = host.pipeline.layout_html(&final_html);

    let mut diags = host.diags.clone();
    let (geometry, final_layout_ms, pages) = match final_layout {
        Ok(snapshot) => {
            diags.extend(snapshot.warnings.iter().cloned());
            (snapshot.geometry, snapshot.ms, snapshot.pages)
        }
        Err(e) => {
            diags.push(("raikiri:layout-error".to_string(), e));
            (serde_json::json!({ "pages": [] }), 0.0, 0)
        }
    };
    diags.extend(pipeline::log_warnings());

    let relayout_total: f64 = host.relayout_ms.iter().sum();
    let metrics = serde_json::json!({
        "engine": "raikiri-js (boa_engine 0.22)",
        "parse_ms": parse_ms,
        "prelude_ms": init_ms,
        "js_ms": js_ms,
        "js_ms_excluding_relayout": js_ms - relayout_total,
        "relayout_count": host.relayout_ms.len(),
        "relayout_ms_total": relayout_total,
        "relayout_ms": host.relayout_ms,
        "rect_queries": host.geometry_queries,
        "scripts_run": report.scripts_run,
        "scripts_failed": report.uncaught_errors.len(),
        "dom_nodes": host.doc.node_count(),
        "serialize_ms": serialize_ms,
        "render_ms": render_ms,
        "final_layout_ms": final_layout_ms,
        "pages": pages,
        "total_ms": ms_since(total),
        "peak_rss_kib": pipeline::peak_rss_kib(),
        "render_ok": pdf.is_ok(),
    });
    if let Some(p) = &args.metrics {
        let _ = write_json(p, &metrics);
    }
    if let Some(p) = &args.geometry {
        let _ = write_json(p, &geometry);
    }
    if let Some(p) = &args.diagnostics {
        let _ = write_json(p, &diagnostics_json(&diags));
    }
    match pdf {
        Ok(bytes) => {
            if let Err(e) = std::fs::write(&args.output, &bytes) {
                eprintln!("spike-rkboa: cannot write {}: {e}", args.output.display());
                std::process::exit(1);
            }
        }
        Err(e) => {
            eprintln!("spike-rkboa: render failed: {e}");
            std::process::exit(2);
        }
    }
}
