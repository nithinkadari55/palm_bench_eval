//! test262 execution on rquickjs: fresh runtime per (test, mode), harness includes as
//! separate global scripts, `$262` host object, file-based module loader.
use crate::host::{ctor_name, describe_value};
use p5common::test262::{Job, Mode, Raw};
use rquickjs::context::EvalOptions;
use rquickjs::loader::{ImportAttributes, Loader, Resolver};
use rquickjs::module::Declared;
use rquickjs::promise::PromiseState;
use rquickjs::function::Rest;
use rquickjs::{ArrayBuffer, Coerced, Context, Ctx, Error, Function, Module, Runtime, Value};
use std::cell::{Cell, RefCell};
use std::path::{Component, Path, PathBuf};
use std::rc::Rc;
use std::time::{Duration, Instant};

const PRELUDE_262: &str = r#"
var $262 = {
  global: globalThis,
  gc: function () { __t262_gc(); },
  evalScript: function (src) { return __t262_evalScript(String(src)); },
  detachArrayBuffer: function (ab) { __t262_detach(ab); return null; },
  createRealm: function () { throw new Test262Error('createRealm is not supported by this harness'); },
  agent: {}
};
"#;

fn normalize(p: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for c in p.components() {
        match c {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    out
}

struct T262Resolver;

impl Resolver for T262Resolver {
    fn resolve<'js>(&mut self, _ctx: &Ctx<'js>, base: &str, name: &str, _attributes: Option<ImportAttributes<'js>>) -> rquickjs::Result<String> {
        let dir = Path::new(base).parent().map(|p| p.to_path_buf()).unwrap_or_default();
        Ok(normalize(&dir.join(name)).to_string_lossy().into_owned())
    }
}

struct T262Loader;

impl Loader for T262Loader {
    fn load<'js>(&mut self, ctx: &Ctx<'js>, name: &str, attributes: Option<ImportAttributes<'js>>) -> rquickjs::Result<Module<'js, Declared>> {
        let src = std::fs::read_to_string(name).map_err(|e| Error::new_loading_message(name, e.to_string()))?;
        let ty = attributes.and_then(|a| a.get_type().ok().flatten());
        let code = match ty.as_deref() {
            Some("json") => format!("export default {};", src.trim()),
            _ => src,
        };
        Module::declare(ctx.clone(), name, code)
    }
}

fn eval_script<'js>(ctx: &Ctx<'js>, src: &str, name: &str) -> rquickjs::Result<Value<'js>> {
    let mut opts = EvalOptions::default();
    opts.global = true;
    opts.strict = false;
    opts.filename = Some(name.to_string());
    ctx.eval_with_options::<Value<'js>, _>(src, opts)
}

fn caught<'js>(ctx: &Ctx<'js>, e: Error) -> (String, String) {
    match e {
        Error::Exception => {
            let v = ctx.catch();
            (ctor_name(&v), describe_value(&v))
        }
        other => ("HostError".to_string(), format!("HostError: {other}")),
    }
}

fn drain<'js>(ctx: &Ctx<'js>, deadline: Instant) {
    let mut n = 0u64;
    while ctx.execute_pending_job() {
        n += 1;
        if n % 1000 == 0 && Instant::now() > deadline {
            break;
        }
    }
}

fn install_host<'js>(ctx: &Ctx<'js>, printed: Rc<RefCell<String>>) -> rquickjs::Result<()> {
    let g = ctx.globals();
    let p = printed;
    g.set(
        "print",
        Function::new(ctx.clone(), move |args: Rest<Coerced<String>>| {
            let mut s = p.borrow_mut();
            let line: Vec<String> = args.0.into_iter().map(|c| c.0).collect();
            s.push_str(&line.join(" "));
            s.push('\n');
        })?,
    )?;
    g.set(
        "__t262_evalScript",
        Function::new(ctx.clone(), |ctx: Ctx<'js>, src: Coerced<String>| -> rquickjs::Result<Value<'js>> {
            eval_script(&ctx, &src.0, "evalScript.js")
        })?,
    )?;
    g.set("__t262_gc", Function::new(ctx.clone(), |ctx: Ctx<'js>| ctx.run_gc())?)?;
    g.set("__t262_detach", Function::new(ctx.clone(), |mut ab: ArrayBuffer<'js>| ab.detach())?)?;
    eval_script(ctx, PRELUDE_262, "prelude262.js")?;
    Ok(())
}

pub fn exec(job: &Job) -> Raw {
    let rt = match Runtime::new() {
        Ok(r) => r,
        Err(e) => return Raw { error: Some(("HostError".into(), format!("HostError: runtime: {e}"))), include_error: true, printed: String::new() },
    };
    rt.set_memory_limit(1024 * 1024 * 1024);
    rt.set_max_stack_size(2 * 1024 * 1024);
    let deadline = Instant::now() + Duration::from_millis(job.timeout_ms);
    let dl = Rc::new(Cell::new(deadline));
    let d2 = dl.clone();
    rt.set_interrupt_handler(Some(Box::new(move || Instant::now() > d2.get())));
    rt.set_loader(T262Resolver, T262Loader);
    let context = match Context::full(&rt) {
        Ok(c) => c,
        Err(e) => return Raw { error: Some(("HostError".into(), format!("HostError: context: {e}"))), include_error: true, printed: String::new() },
    };
    let printed = Rc::new(RefCell::new(String::new()));
    let abs = job.abs.to_string_lossy().into_owned();
    context.with(|ctx| {
        let mut raw = Raw::default();
        let setup = install_host(&ctx, printed.clone());
        if let Err(e) = setup {
            raw.error = Some(caught(&ctx, e));
            raw.include_error = true;
            return raw;
        }
        for (name, src) in &job.includes {
            if let Err(e) = eval_script(&ctx, src, name) {
                raw.error = Some(caught(&ctx, e));
                raw.include_error = true;
                raw.printed = printed.borrow().clone();
                return raw;
            }
        }
        let result: rquickjs::Result<()> = match job.mode {
            Mode::Module => match Module::declare(ctx.clone(), abs.clone(), job.source) {
                Err(e) => Err(e),
                Ok(m) => match m.eval() {
                    Err(e) => Err(e),
                    Ok((_m, promise)) => {
                        drain(&ctx, dl.get());
                        match promise.state() {
                            PromiseState::Rejected => match promise.result::<Value>() {
                                Some(Err(e)) => Err(e),
                                _ => Ok(()),
                            },
                            _ => Ok(()),
                        }
                    }
                },
            },
            Mode::Strict => eval_script(&ctx, &format!("\"use strict\";\n{}", job.source), &abs).map(|_| ()),
            Mode::Sloppy | Mode::Raw => eval_script(&ctx, job.source, &abs).map(|_| ()),
        };
        if let Err(e) = result {
            raw.error = Some(caught(&ctx, e));
        }
        drain(&ctx, dl.get());
        if Instant::now() > dl.get() && raw.error.is_none() && job.meta.has_flag("async") && !printed.borrow().contains("Test262:Async") {
            raw.error = Some(("Timeout".into(), "Timeout: async test did not finish".into()));
        }
        raw.printed = printed.borrow().clone();
        raw
    })
}
