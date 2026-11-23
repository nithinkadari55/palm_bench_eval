// spike-rkjs: QuickJS-NG (rquickjs 0.14.0) bound to raikiri's live DOM, then the PDF through
// the fulgur-raikiri path of engines/rkhead. Same CLI as adapter-rkhead plus --metrics.
#[path = "../../spike-common/pipeline.rs"]
mod pipeline;
mod dom;

use pipeline::{diagnostics_json, ms_since, parse_args, write_json, Pipeline, USAGE};
use raikiri_dom::{Document, NodeKind};
use rquickjs::context::EvalOptions;
use rquickjs::{Context, Ctx, Error, Object, Runtime, Value};
use std::cell::{Cell, RefCell};
use std::rc::Rc;
use std::time::{Duration, Instant};

const PRELUDE: &str = include_str!("prelude.js");
const MEMORY_LIMIT: usize = 512 * 1024 * 1024;
const STACK_LIMIT: usize = 4 * 1024 * 1024;
const JS_DEADLINE: Duration = Duration::from_secs(30);
const MAX_JOBS: usize = 1_000_000;
const MAX_TIMER_CALLBACKS: u32 = 10_000;
const MAX_VIRTUAL_MS: u32 = 30_000;

fn describe_value<'js>(v: &Value<'js>) -> String {
    if let Some(obj) = v.as_object() {
        let name: Option<String> = obj.get::<_, Option<String>>("name").ok().flatten();
        let msg: Option<String> = obj.get::<_, Option<String>>("message").ok().flatten();
        let stack: Option<String> = obj.get::<_, Option<String>>("stack").ok().flatten();
        let mut out = format!("{}: {}", name.unwrap_or_else(|| "Error".to_string()), msg.unwrap_or_default());
        if let Some(stack) = stack {
            let first: Vec<&str> = stack.lines().map(str::trim).filter(|l| !l.is_empty()).take(2).collect();
            if !first.is_empty() {
                out.push_str(&format!(" [{}]", first.join(" | ")));
            }
        }
        return out;
    }
    if let Some(s) = v.as_string() {
        return format!("thrown: {}", s.to_string().unwrap_or_default());
    }
    if let Some(n) = v.as_number() {
        return format!("thrown: {n}");
    }
    format!("thrown: <{}>", v.type_name())
}

fn describe_error<'js>(ctx: &Ctx<'js>, e: Error) -> String {
    match e {
        Error::Exception => describe_value(&ctx.catch()),
        Error::Allocation => "OutOfMemory: allocation failed".to_string(),
        other => format!("HostError: {other}"),
    }
}

fn is_javascript_type(t: Option<&str>) -> bool {
    match t.map(|t| t.trim().to_ascii_lowercase()) {
        None => true,
        Some(t) => matches!(
            t.as_str(),
            "" | "text/javascript" | "application/javascript" | "application/ecmascript" | "text/ecmascript"
                | "application/x-javascript" | "text/jscript"
        ),
    }
}

/// Classic <script> elements in tree order, collected once before any of them runs.
fn collect_scripts(doc: &Document) -> Vec<usize> {
    let mut out = Vec::new();
    let mut stack = vec![doc.root_index()];
    while let Some(i) = stack.pop() {
        let Some(n) = doc.get_node(i) else { continue };
        if n.kind() == NodeKind::Element
            && n.tag_name() == Some("script")
            && doc.element_namespace_uri(i).map_or(true, |ns| ns == dom::HTML_NS)
        {
            out.push(i);
        }
        stack.extend(n.children.iter().rev().copied());
    }
    out
}

struct Engine {
    rt: Runtime,
    ctx: Context,
    state: Rc<RefCell<dom::State>>,
    jobs: usize,
}

impl Engine {
    fn eval(&self, source: &str, name: &str) -> Result<(), String> {
        self.ctx.with(|ctx| {
            let mut opts = EvalOptions::default();
            opts.global = true;
            opts.strict = false;
            opts.filename = Some(name.to_string());
            match ctx.eval_with_options::<Value, _>(source, opts) {
                Ok(_) => Ok(()),
                Err(e) => Err(describe_error(&ctx, e)),
            }
        })
    }

    fn eval_bool(&self, source: &str) -> Result<bool, String> {
        self.ctx.with(|ctx| match ctx.eval::<bool, _>(source) {
            Ok(b) => Ok(b),
            Err(e) => Err(describe_error(&ctx, e)),
        })
    }

    /// Microtask checkpoint: runs queued promise jobs.
    fn drain_jobs(&mut self) {
        while self.jobs < MAX_JOBS && self.rt.is_job_pending() {
            match self.rt.execute_pending_job() {
                Ok(true) => self.jobs += 1,
                Ok(false) => break,
                Err(job) => {
                    let msg = job.0.with(|ctx| describe_value(&ctx.catch()));
                    self.state.borrow_mut().push_diag("js:uncaught", format!("promise job: {msg}"));
                    break;
                }
            }
        }
    }

    fn diag(&self, kind: &str, message: String) {
        self.state.borrow_mut().push_diag(kind, message);
    }
}

struct JsReport {
    scripts_run: usize,
    scripts_failed: usize,
    prelude_ms: f64,
    js_ms: f64,
    malloc_size: i64,
    memory_used_size: i64,
    jobs: usize,
}

fn run_scripts(state: &Rc<RefCell<dom::State>>) -> Result<JsReport, String> {
    let rt = Runtime::new().map_err(|e| format!("QuickJS runtime: {e}"))?;
    rt.set_memory_limit(MEMORY_LIMIT);
    rt.set_max_stack_size(STACK_LIMIT);
    let deadline = Rc::new(Cell::new(Instant::now() + JS_DEADLINE));
    let d = deadline.clone();
    rt.set_interrupt_handler(Some(Box::new(move || Instant::now() > d.get())));
    let ctx = Context::full(&rt).map_err(|e| format!("QuickJS context: {e}"))?;
    let t0 = Instant::now();
    ctx.with(|ctx| -> Result<(), String> {
        dom::install(&ctx, state).map_err(|e| format!("install natives: {e}"))?;
        let mut opts = EvalOptions::default();
        opts.global = true;
        opts.strict = false;
        opts.filename = Some("prelude.js".to_string());
        ctx.eval_with_options::<Value, _>(PRELUDE, opts).map_err(|e| format!("prelude: {}", describe_error(&ctx, e)))?;
        let _: Object = ctx.globals().get("__rk").map_err(|e| format!("prelude did not define __rk: {e}"))?;
        Ok(())
    })?;
    let prelude_ms = ms_since(t0);
    let mut engine = Engine { rt, ctx, state: state.clone(), jobs: 0 };

    let t1 = Instant::now();
    let scripts = collect_scripts(&state.borrow().doc);
    let (mut run, mut failed) = (0usize, 0usize);
    for (k, &index) in scripts.iter().enumerate() {
        let (src_attr, type_attr, inline) = {
            let st = state.borrow();
            (
                st.doc.element_attribute(index, "src").map(str::to_string),
                st.doc.element_attribute(index, "type").map(str::to_string),
                st.doc.element_text_content(index).unwrap_or_default(),
            )
        };
        if !is_javascript_type(type_attr.as_deref()) {
            if type_attr.as_deref().map(|t| t.trim().eq_ignore_ascii_case("module")) == Some(true) {
                engine.diag("js:skipped", format!("script #{k}: type=module is not supported"));
            }
            continue;
        }
        let (source, name) = match src_attr {
            Some(src) => {
                let read = state.borrow().pipeline.read_script(&src);
                match read {
                    Ok(text) => (text, src),
                    Err(e) => {
                        engine.diag("js:fetch-error", e);
                        continue;
                    }
                }
            }
            None => (inline, format!("inline-script-{k}")),
        };
        run += 1;
        if let Err(e) = engine.eval(&source, &name) {
            failed += 1;
            engine.diag("js:uncaught", format!("{name}: {e}"));
        }
        engine.drain_jobs();
    }

    let host_steps = [
        "__rk.setReady('interactive'); __rk.fire('DOMContentLoaded');",
        "__rk.setReady('complete'); __rk.fire('load');",
    ];
    for step in host_steps {
        if let Err(e) = engine.eval(step, "host") {
            engine.diag("js:host", e);
        }
        engine.drain_jobs();
    }
    let timer_call = format!("__rk.runTimer({MAX_TIMER_CALLBACKS}, {MAX_VIRTUAL_MS})");
    loop {
        match engine.eval_bool(&timer_call) {
            Ok(true) => engine.drain_jobs(),
            Ok(false) => break,
            Err(e) => {
                engine.diag("js:host", format!("timers: {e}"));
                break;
            }
        }
    }
    if Instant::now() > deadline.get() {
        engine.diag("js:timeout", format!("script deadline of {} s reached", JS_DEADLINE.as_secs()));
    }
    let js_ms = ms_since(t1);
    let m = engine.rt.memory_usage();
    Ok(JsReport {
        scripts_run: run,
        scripts_failed: failed,
        prelude_ms,
        js_ms,
        malloc_size: m.malloc_size as i64,
        memory_used_size: m.memory_used_size as i64,
        jobs: engine.jobs,
    })
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
        eprintln!("spike-rkjs: render thread panicked");
        std::process::exit(101);
    }
}

fn run_main() {
    pipeline::install_logger();
    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("spike-rkjs: {e}\n{USAGE}");
            std::process::exit(1);
        }
    };
    let total = Instant::now();
    let pipeline = match Pipeline::new(&args) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("spike-rkjs: {e}");
            std::process::exit(1);
        }
    };
    let html = match std::fs::read(&args.input) {
        Ok(h) => h,
        Err(e) => {
            eprintln!("spike-rkjs: {}: {e}", args.input.display());
            std::process::exit(1);
        }
    };
    let t_parse = Instant::now();
    let parsed = match raikiri_html::parse(html.as_slice(), &raikiri_html::ParseOptions::new()) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("spike-rkjs: parse failed: {e}");
            std::process::exit(2);
        }
    };
    let parse_ms = ms_since(t_parse);
    let state = Rc::new(RefCell::new(dom::State::new(parsed.dom, pipeline)));

    let js = run_scripts(&state);
    // The QuickJS runtime is gone; no script can borrow the state any more.
    let mut guard = state.borrow_mut();
    let st = &mut *guard;
    let js = match js {
        Ok(r) => Some(r),
        Err(e) => {
            st.push_diag("js:engine-error", e);
            None
        }
    };

    let t_ser = Instant::now();
    let final_html = match pipeline::serialize_document(&st.doc) {
        Ok(h) => h,
        Err(e) => {
            eprintln!("spike-rkjs: serialize failed: {e}");
            std::process::exit(2);
        }
    };
    let serialize_ms = ms_since(t_ser);
    if let Some(p) = &args.dump_html {
        let _ = std::fs::write(p, &final_html);
    }

    let t_render = Instant::now();
    let pdf = st.pipeline.render_pdf(&final_html);
    let render_ms = ms_since(t_render);
    let final_layout = st.pipeline.layout_html(&final_html);

    let mut diags = st.diags.clone();
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

    let relayout_total: f64 = st.relayout_ms.iter().sum();
    let metrics = serde_json::json!({
        "engine": "rquickjs-0.14.0",
        "parse_ms": parse_ms,
        "prelude_ms": js.as_ref().map(|j| j.prelude_ms),
        "js_ms": js.as_ref().map(|j| j.js_ms),
        "js_ms_excluding_relayout": js.as_ref().map(|j| j.js_ms - relayout_total),
        "relayout_count": st.relayout_ms.len(),
        "relayout_ms_total": relayout_total,
        "relayout_ms": st.relayout_ms,
        "rect_queries": st.rect_queries,
        "scripts_run": js.as_ref().map(|j| j.scripts_run),
        "scripts_failed": js.as_ref().map(|j| j.scripts_failed),
        "promise_jobs": js.as_ref().map(|j| j.jobs),
        "qjs_malloc_size": js.as_ref().map(|j| j.malloc_size),
        "qjs_memory_used_size": js.as_ref().map(|j| j.memory_used_size),
        "dom_nodes": st.doc.node_count(),
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
                eprintln!("spike-rkjs: cannot write {}: {e}", args.output.display());
                std::process::exit(1);
            }
        }
        Err(e) => {
            eprintln!("spike-rkjs: render failed: {e}");
            std::process::exit(2);
        }
    }
}
