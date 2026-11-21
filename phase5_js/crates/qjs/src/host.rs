//! rquickjs host: runtime limits, interrupt-based deadline, console sink and the optional
//! Rust recording canvas, behind the engine-independent `Host` trait.
use p5common::cases::Host;
use rquickjs::context::EvalOptions;
use rquickjs::{Coerced, Context, Ctx, Error, Function, Object, Runtime, Value};
use serde_json::{json, Value as Json};
use std::cell::{Cell, RefCell};
use std::rc::Rc;
use std::time::{Duration, Instant};

pub struct Limits {
    pub memory_bytes: usize,
    pub stack_bytes: usize,
}

pub struct QjsHost {
    pub rt: Runtime,
    pub ctx: Context,
    deadline: Rc<Cell<Instant>>,
    pub logs: Rc<RefCell<Vec<String>>>,
    memory_limit: usize,
}

/// "Name: message" for a thrown value, read without running user code where possible.
pub fn describe_value<'js>(v: &Value<'js>) -> String {
    if let Some(obj) = v.as_object() {
        let name: Option<String> = obj.get::<_, Option<String>>("name").ok().flatten();
        let msg: Option<String> = obj.get::<_, Option<String>>("message").ok().flatten();
        let ctor: Option<String> = obj
            .get::<_, Option<Object<'js>>>("constructor")
            .ok()
            .flatten()
            .and_then(|c| c.get::<_, Option<String>>("name").ok().flatten());
        let n = name.or(ctor).unwrap_or_else(|| "Error".to_string());
        return format!("{n}: {}", msg.unwrap_or_default());
    }
    if v.is_null() || v.is_undefined() {
        return format!("NullException: exception value is {}", v.type_name());
    }
    if let Some(s) = v.as_string() {
        return format!("thrown: {}", s.to_string().unwrap_or_default());
    }
    if let Some(n) = v.as_number() {
        return format!("thrown: {n}");
    }
    format!("thrown: <{}>", v.type_name())
}

/// Constructor name of a thrown value (test262 negative tests compare it).
pub fn ctor_name<'js>(v: &Value<'js>) -> String {
    if let Some(obj) = v.as_object() {
        if let Some(c) = obj.get::<_, Option<Object<'js>>>("constructor").ok().flatten() {
            if let Some(n) = c.get::<_, Option<String>>("name").ok().flatten() {
                return n;
            }
        }
        return "Object".to_string();
    }
    v.type_name().to_string()
}

pub fn describe_error<'js>(ctx: &Ctx<'js>, e: Error) -> String {
    match e {
        Error::Exception => describe_value(&ctx.catch()),
        Error::Allocation => "OutOfMemory: allocation failed".to_string(),
        other => format!("HostError: {other}"),
    }
}

impl QjsHost {
    pub fn new(limits: &Limits, native_canvas: bool) -> QjsHost {
        let rt = Runtime::new().expect("QuickJS runtime");
        rt.set_memory_limit(limits.memory_bytes);
        rt.set_max_stack_size(limits.stack_bytes);
        let deadline = Rc::new(Cell::new(Instant::now() + Duration::from_secs(3600)));
        let d = deadline.clone();
        rt.set_interrupt_handler(Some(Box::new(move || Instant::now() > d.get())));
        let ctx = Context::full(&rt).expect("QuickJS context");
        let logs: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
        let sink = logs.clone();
        ctx.with(|ctx| {
            let g = ctx.globals();
            let f = Function::new(ctx.clone(), move |level: Coerced<String>, msg: Coerced<String>| {
                let mut l = sink.borrow_mut();
                if l.len() < 10000 {
                    l.push(format!("{}: {}", level.0, msg.0));
                }
            })
            .expect("__host_log");
            g.set("__host_log", f).expect("set __host_log");
            if native_canvas {
                crate::canvas::install(&ctx).expect("install canvas");
            }
        });
        QjsHost { rt, ctx, deadline, logs, memory_limit: limits.memory_bytes }
    }

    fn fix_oom(&self, msg: String) -> String {
        if msg.starts_with("NullException") || msg.starts_with("HostError") {
            let m = self.rt.memory_usage();
            if self.memory_limit > 0 && (m.malloc_size as f64) > 0.85 * self.memory_limit as f64 {
                return format!("OutOfMemory: {msg} (malloc_size {} of limit {})", m.malloc_size, self.memory_limit);
            }
        }
        msg
    }
}

impl Host for QjsHost {
    fn eval(&mut self, src: &str, name: &str) -> Result<String, String> {
        let r = self.ctx.with(|ctx| {
            let mut opts = EvalOptions::default();
            opts.global = true;
            opts.strict = false;
            opts.filename = Some(name.to_string());
            match ctx.eval_with_options::<Coerced<String>, _>(src, opts) {
                Ok(v) => Ok(v.0),
                Err(e) => Err(describe_error(&ctx, e)),
            }
        });
        r.map_err(|m| self.fix_oom(m))
    }

    fn run_jobs(&mut self, max: usize) -> Result<usize, String> {
        let mut n = 0usize;
        while n < max {
            if !self.rt.is_job_pending() {
                break;
            }
            match self.rt.execute_pending_job() {
                Ok(true) => n += 1,
                Ok(false) => break,
                Err(job) => {
                    // Reaction jobs turn normal throws into rejections, so an error here is
                    // uncatchable: interrupt (deadline) or out-of-memory.
                    let msg = job.0.with(|ctx| describe_value(&ctx.catch()));
                    return Err(self.fix_oom(msg));
                }
            }
        }
        Ok(n)
    }

    fn set_deadline(&mut self, deadline: Instant) {
        self.deadline.set(deadline);
    }

    fn extra(&mut self) -> Json {
        let m = self.rt.memory_usage();
        json!({
            "malloc_size": m.malloc_size,
            "memory_used_size": m.memory_used_size,
            "obj_count": m.obj_count,
            "str_size": m.str_size,
            "host_log_lines": self.logs.borrow().len()
        })
    }
}
