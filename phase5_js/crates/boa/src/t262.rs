//! test262 execution on boa_engine with the same harness as rquickjs: fresh context per
//! (test, mode), includes as separate global scripts, `$262`, SimpleModuleLoader rooted
//! at the test262 checkout.
use crate::host::{describe, describe_value, BudgetExecutor};
use boa_engine::builtins::promise::PromiseState;
use boa_engine::module::{Module, SimpleModuleLoader};
use boa_engine::object::builtins::JsArrayBuffer;
use boa_engine::{js_string, Context, JsNativeError, JsResult, JsValue, NativeFunction, Source};
use p5common::test262::{Job, Mode, Raw};
use std::cell::RefCell;
use std::path::Path;
use std::rc::Rc;

thread_local! {
    static PRINTED: RefCell<String> = const { RefCell::new(String::new()) };
}

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

fn print(_this: &JsValue, args: &[JsValue], ctx: &mut Context) -> JsResult<JsValue> {
    let mut parts = Vec::new();
    for a in args {
        parts.push(a.to_string(ctx)?.to_std_string_escaped());
    }
    PRINTED.with(|p| {
        let mut p = p.borrow_mut();
        p.push_str(&parts.join(" "));
        p.push('\n');
    });
    Ok(JsValue::undefined())
}

fn eval_script_fn(_this: &JsValue, args: &[JsValue], ctx: &mut Context) -> JsResult<JsValue> {
    let src = args.first().cloned().unwrap_or_else(JsValue::undefined).to_string(ctx)?.to_std_string_escaped();
    ctx.eval(Source::from_bytes(&src))
}

fn gc_fn(_this: &JsValue, _args: &[JsValue], _ctx: &mut Context) -> JsResult<JsValue> {
    boa_engine::gc::force_collect();
    Ok(JsValue::undefined())
}

fn detach_fn(_this: &JsValue, args: &[JsValue], _ctx: &mut Context) -> JsResult<JsValue> {
    let obj = args
        .first()
        .and_then(|v| v.as_object())
        .ok_or_else(|| JsNativeError::typ().with_message("detachArrayBuffer: not an object"))?;
    let ab = JsArrayBuffer::from_object(obj)?;
    ab.detach(&JsValue::undefined())?;
    Ok(JsValue::undefined())
}

fn eval_src(ctx: &mut Context, src: &str, path: &Path) -> JsResult<JsValue> {
    ctx.eval(Source::from_bytes(src).with_path(path))
}

pub fn exec(job: &Job) -> Raw {
    PRINTED.with(|p| p.borrow_mut().clear());
    let mut raw = Raw::default();
    let exec = Rc::new(BudgetExecutor::default());
    let loader = match SimpleModuleLoader::new(job.root) {
        Ok(l) => Rc::new(l),
        Err(e) => {
            raw.error = Some(("HostError".into(), format!("HostError: module loader: {e}")));
            raw.include_error = true;
            return raw;
        }
    };
    let mut ctx = match Context::builder().job_executor(exec.clone()).module_loader(loader).build() {
        Ok(c) => c,
        Err(e) => {
            raw.error = Some(("HostError".into(), format!("HostError: context: {e}")));
            raw.include_error = true;
            return raw;
        }
    };
    let setup = (|| -> JsResult<()> {
        ctx.register_global_builtin_callable(js_string!("print"), 1, NativeFunction::from_fn_ptr(print))?;
        ctx.register_global_builtin_callable(js_string!("__t262_evalScript"), 1, NativeFunction::from_fn_ptr(eval_script_fn))?;
        ctx.register_global_builtin_callable(js_string!("__t262_gc"), 0, NativeFunction::from_fn_ptr(gc_fn))?;
        ctx.register_global_builtin_callable(js_string!("__t262_detach"), 1, NativeFunction::from_fn_ptr(detach_fn))?;
        eval_src(&mut ctx, PRELUDE_262, Path::new("prelude262.js"))?;
        Ok(())
    })();
    if let Err(e) = setup {
        raw.error = Some(describe(&e, &mut ctx));
        raw.include_error = true;
        return raw;
    }
    for (name, src) in &job.includes {
        if let Err(e) = eval_src(&mut ctx, src, Path::new(name)) {
            raw.error = Some(describe(&e, &mut ctx));
            raw.include_error = true;
            raw.printed = PRINTED.with(|p| p.borrow().clone());
            return raw;
        }
    }
    let abs = job.abs.clone();
    let result: Result<(), (String, String)> = match job.mode {
        Mode::Module => match Module::parse(Source::from_bytes(job.source).with_path(&abs), None, &mut ctx) {
            Err(e) => Err(describe(&e, &mut ctx)),
            Ok(m) => {
                let promise = m.load_link_evaluate(&mut ctx);
                let _ = exec.run_some(1_000_000, &mut ctx);
                match promise.state() {
                    PromiseState::Rejected(v) => Err(describe_value(&v, &mut ctx)),
                    _ => Ok(()),
                }
            }
        },
        Mode::Strict => {
            let src = format!("\"use strict\";\n{}", job.source);
            eval_src(&mut ctx, &src, &abs).map(|_| ()).map_err(|e| describe(&e, &mut ctx))
        }
        Mode::Sloppy | Mode::Raw => eval_src(&mut ctx, job.source, &abs).map(|_| ()).map_err(|e| describe(&e, &mut ctx)),
    };
    if let Err(e) = result {
        raw.error = Some(e);
    }
    if let Err(e) = exec.run_some(1_000_000, &mut ctx) {
        if raw.error.is_none() {
            raw.error = Some(describe(&e, &mut ctx));
        }
    }
    raw.printed = PRINTED.with(|p| p.borrow().clone());
    raw
}
