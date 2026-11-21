//! boa_engine host: a job executor with a per-call budget (Boa's default executor drains
//! the whole queue, so a promise flood would never return), console sink, runtime limits.
//! Boa has no interrupt handler and no heap limit: the deadline cannot be enforced inside
//! JS, only by the supervising process.
use boa_engine::job::{Job, JobExecutor};
use boa_engine::{js_string, Context, JsError, JsResult, JsString, JsValue, NativeFunction, Source};
use p5common::cases::Host;
use serde_json::{json, Value as Json};
use std::cell::RefCell;
use std::collections::VecDeque;
use std::future::Future;
use std::path::Path;
use std::pin::Pin;
use std::rc::Rc;
use std::time::Instant;

thread_local! {
    pub static LOGS: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
}

#[derive(Default)]
pub struct BudgetExecutor {
    queue: RefCell<VecDeque<Job>>,
}

impl JobExecutor for BudgetExecutor {
    fn enqueue_job(self: Rc<Self>, job: Job, _context: &mut Context) {
        self.queue.borrow_mut().push_back(job);
    }

    fn run_jobs(self: Rc<Self>, context: &mut Context) -> JsResult<()> {
        self.run_some(usize::MAX, context).map(|_| ())
    }
}

impl BudgetExecutor {
    pub fn pending(&self) -> usize {
        self.queue.borrow().len()
    }

    /// Runs at most `max` jobs. Promise and generic jobs run directly; async jobs (module
    /// loading) are polled with a no-op waker, which is enough for the synchronous loaders
    /// used here. Timeout/interval jobs are not part of this host (timers are virtual, in JS).
    pub fn run_some(&self, max: usize, context: &mut Context) -> JsResult<usize> {
        let mut n = 0usize;
        while n < max {
            let job = self.queue.borrow_mut().pop_front();
            let job = match job {
                Some(j) => j,
                None => break,
            };
            n += 1;
            match job {
                Job::PromiseJob(p) => {
                    p.call(context)?;
                }
                Job::GenericJob(g) => {
                    g.call(context)?;
                }
                Job::AsyncJob(a) => {
                    let cell = RefCell::new(&mut *context);
                    let mut fut = a.call(&cell);
                    let mut cx = std::task::Context::from_waker(std::task::Waker::noop());
                    let mut spins = 0u32;
                    loop {
                        match Pin::new(&mut fut).poll(&mut cx) {
                            std::task::Poll::Ready(r) => {
                                r?;
                                break;
                            }
                            std::task::Poll::Pending => {
                                spins += 1;
                                if spins > 10000 {
                                    break;
                                }
                            }
                        }
                    }
                }
                _ => {}
            }
        }
        Ok(n)
    }
}

pub fn describe_value(v: &JsValue, ctx: &mut Context) -> (String, String) {
    if let Some(obj) = v.as_object() {
        let get_str = |o: &boa_engine::JsObject, k: &str, ctx: &mut Context| -> Option<String> {
            o.get(JsString::from(k), ctx).ok().and_then(|x| x.as_string().map(|s| s.to_std_string_escaped()))
        };
        let name = get_str(&obj, "name", &mut *ctx);
        let msg = get_str(&obj, "message", &mut *ctx).unwrap_or_default();
        let ctor = obj
            .get(js_string!("constructor"), ctx)
            .ok()
            .and_then(|c| c.as_object())
            .and_then(|c| get_str(&c, "name", &mut *ctx));
        let ctor_s = ctor.clone().unwrap_or_else(|| "Object".to_string());
        let n = name.or(ctor).unwrap_or_else(|| "Error".to_string());
        return (ctor_s, format!("{n}: {msg}"));
    }
    if v.is_null() || v.is_undefined() {
        return ("undefined".into(), "NullException: thrown null/undefined".into());
    }
    let s = v.to_string(ctx).map(|s| s.to_std_string_escaped()).unwrap_or_else(|_| "?".into());
    ("primitive".into(), format!("thrown: {s}"))
}

/// (constructor name, "Name: message") for any Boa error, including engine limit errors.
pub fn describe(err: &JsError, ctx: &mut Context) -> (String, String) {
    if let Some(e) = err.as_engine() {
        return ("EngineError".into(), format!("{e}"));
    }
    match err.clone().into_opaque(ctx) {
        Ok(v) => describe_value(&v, ctx),
        Err(e) => ("EngineError".into(), format!("{e}")),
    }
}

fn arg_string(args: &[JsValue], i: usize, ctx: &mut Context) -> JsResult<String> {
    let v = args.get(i).cloned().unwrap_or_else(JsValue::undefined);
    Ok(v.to_string(ctx)?.to_std_string_escaped())
}

fn host_log(_this: &JsValue, args: &[JsValue], ctx: &mut Context) -> JsResult<JsValue> {
    let level = arg_string(args, 0, ctx)?;
    let msg = arg_string(args, 1, ctx)?;
    LOGS.with(|l| {
        let mut l = l.borrow_mut();
        if l.len() < 10000 {
            l.push(format!("{level}: {msg}"));
        }
    });
    Ok(JsValue::undefined())
}

pub struct BoaLimits {
    pub recursion: usize,
    pub stack: usize,
    pub loop_iterations: u64,
}

pub struct BoaHost {
    pub ctx: Context,
    pub exec: Rc<BudgetExecutor>,
    deadline: Instant,
}

impl BoaHost {
    pub fn new(l: &BoaLimits) -> BoaHost {
        let exec = Rc::new(BudgetExecutor::default());
        let mut ctx = Context::builder().job_executor(exec.clone()).build().expect("boa context");
        ctx.runtime_limits_mut().set_recursion_limit(l.recursion);
        ctx.runtime_limits_mut().set_stack_size_limit(l.stack);
        ctx.runtime_limits_mut().set_loop_iteration_limit(l.loop_iterations);
        ctx.register_global_builtin_callable(js_string!("__host_log"), 2, NativeFunction::from_fn_ptr(host_log))
            .expect("__host_log");
        BoaHost { ctx, exec, deadline: Instant::now() }
    }
}

impl Host for BoaHost {
    fn eval(&mut self, src: &str, name: &str) -> Result<String, String> {
        let source = Source::from_bytes(src).with_path(Path::new(name));
        match self.ctx.eval(source) {
            Ok(v) => match v.to_string(&mut self.ctx) {
                Ok(s) => Ok(s.to_std_string_escaped()),
                Err(e) => Err(describe(&e, &mut self.ctx).1),
            },
            Err(e) => Err(describe(&e, &mut self.ctx).1),
        }
    }

    fn run_jobs(&mut self, max: usize) -> Result<usize, String> {
        let exec = self.exec.clone();
        match exec.run_some(max, &mut self.ctx) {
            Ok(n) => Ok(n),
            Err(e) => Err(describe(&e, &mut self.ctx).1),
        }
    }

    fn set_deadline(&mut self, deadline: Instant) {
        // Recorded only: Boa 0.22 has no interrupt hook to stop running JS.
        self.deadline = deadline;
    }

    fn extra(&mut self) -> Json {
        let logs = LOGS.with(|l| l.borrow().len());
        json!({"host_log_lines": logs, "pending_jobs": self.exec.pending(), "deadline_passed": Instant::now() > self.deadline})
    }
}
