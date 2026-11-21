//! Host recording Canvas2D backend, implemented in Rust and exposed to JS as
//! `__host_canvas_backend()`. It keeps the 2D state (properties, line dash, save/restore
//! stack) and records every call as an op. The rule set mirrors js/src/canvas_backend_js.js
//! exactly, so Node/Boa (JS backend) and rquickjs (this backend) must emit the same stream.
//! JS sees: call(name, ...args), set(name, value), get(name), ops(), opCount(), reset().
use rquickjs::function::Rest;
use rquickjs::{Array, Coerced, Ctx, Exception, FromJs, Function, Object, Result, Value};
use std::cell::RefCell;
use std::rc::Rc;

const MAX_OPS: usize = 1_000_000;
const MAX_STACK: usize = 100_000;
/// Rust-side only: recorded strings live outside the QuickJS heap limit, so they get their own cap.
const MAX_STRING_BYTES: usize = 256 * 1024 * 1024;

#[derive(Clone, Debug)]
enum Arg {
    Num(f64),
    Str(String),
    Bool(bool),
    Null,
    List(Vec<Arg>),
}

#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Style,
    Str,
    Pos,
    Num,
    NonNeg,
    Alpha,
    Bool,
    Enum(&'static [&'static str]),
}

struct Prop {
    name: &'static str,
    kind: Kind,
    default: Arg,
}

fn props() -> Vec<Prop> {
    let s = |v: &str| Arg::Str(v.to_string());
    vec![
        Prop { name: "fillStyle", kind: Kind::Style, default: s("#000000") },
        Prop { name: "strokeStyle", kind: Kind::Style, default: s("#000000") },
        Prop { name: "lineWidth", kind: Kind::Pos, default: Arg::Num(1.0) },
        Prop { name: "miterLimit", kind: Kind::Pos, default: Arg::Num(10.0) },
        Prop { name: "lineDashOffset", kind: Kind::Num, default: Arg::Num(0.0) },
        Prop { name: "globalAlpha", kind: Kind::Alpha, default: Arg::Num(1.0) },
        Prop { name: "shadowBlur", kind: Kind::NonNeg, default: Arg::Num(0.0) },
        Prop { name: "shadowOffsetX", kind: Kind::Num, default: Arg::Num(0.0) },
        Prop { name: "shadowOffsetY", kind: Kind::Num, default: Arg::Num(0.0) },
        Prop { name: "shadowColor", kind: Kind::Str, default: s("rgba(0, 0, 0, 0)") },
        Prop { name: "lineCap", kind: Kind::Enum(&["butt", "round", "square"]), default: s("butt") },
        Prop { name: "lineJoin", kind: Kind::Enum(&["round", "bevel", "miter"]), default: s("miter") },
        Prop { name: "font", kind: Kind::Str, default: s("10px sans-serif") },
        Prop { name: "textAlign", kind: Kind::Enum(&["start", "end", "left", "right", "center"]), default: s("start") },
        Prop { name: "textBaseline", kind: Kind::Enum(&["top", "hanging", "middle", "alphabetic", "ideographic", "bottom"]), default: s("alphabetic") },
        Prop { name: "direction", kind: Kind::Enum(&["ltr", "rtl", "inherit"]), default: s("inherit") },
        Prop { name: "globalCompositeOperation", kind: Kind::Str, default: s("source-over") },
        Prop { name: "filter", kind: Kind::Str, default: s("none") },
        Prop { name: "letterSpacing", kind: Kind::Str, default: s("0px") },
        Prop { name: "wordSpacing", kind: Kind::Str, default: s("0px") },
        Prop { name: "fontKerning", kind: Kind::Enum(&["auto", "normal", "none"]), default: s("auto") },
        Prop { name: "imageSmoothingEnabled", kind: Kind::Bool, default: Arg::Bool(true) },
    ]
}

#[derive(Clone)]
struct State {
    values: Vec<Arg>,
    dash: Vec<f64>,
}

struct Backend {
    props: Vec<Prop>,
    st: State,
    stack: Vec<State>,
    ops: Vec<(String, Vec<Arg>)>,
    gid: u32,
    string_bytes: usize,
}

impl Backend {
    fn new() -> Backend {
        let props = props();
        let values = props.iter().map(|p| p.default.clone()).collect();
        Backend { props, st: State { values, dash: Vec::new() }, stack: Vec::new(), ops: Vec::new(), gid: 0, string_bytes: 0 }
    }

    fn rec(&mut self, name: &str, args: Vec<Arg>) -> std::result::Result<(), String> {
        if self.ops.len() >= MAX_OPS {
            return Err(format!("P5CanvasBudget: more than {MAX_OPS} recorded ops"));
        }
        let bytes: usize = args.iter().map(arg_bytes).sum::<usize>() + name.len();
        self.string_bytes += bytes;
        if self.string_bytes > MAX_STRING_BYTES {
            return Err(format!("P5CanvasBudget: more than {MAX_STRING_BYTES} bytes recorded"));
        }
        self.ops.push((name.to_string(), args));
        Ok(())
    }

    fn index(&self, name: &str) -> Option<usize> {
        self.props.iter().position(|p| p.name == name)
    }
}

fn arg_bytes(a: &Arg) -> usize {
    match a {
        Arg::Str(s) => s.len(),
        Arg::List(l) => l.iter().map(arg_bytes).sum(),
        _ => 8,
    }
}

/// Number coercion of the JS mirror (`toNum` in canvas_backend_js.js).
fn to_num<'js>(v: &Value<'js>) -> f64 {
    if let Some(n) = v.as_number() {
        n
    } else if let Some(b) = v.as_bool() {
        if b {
            1.0
        } else {
            0.0
        }
    } else if v.is_null() {
        0.0
    } else if let Some(s) = v.as_string() {
        let t = s.to_string().unwrap_or_default();
        let t = t.trim();
        if t.is_empty() {
            f64::NAN
        } else {
            t.parse::<f64>().unwrap_or(f64::NAN)
        }
    } else {
        f64::NAN
    }
}

fn fmt_gid(g: f64) -> String {
    if g.fract() == 0.0 && g.abs() < 1e15 {
        format!("{}", g as i64)
    } else {
        format!("{g}")
    }
}

/// Argument conversion of the JS mirror (`toArg`). May read `__p5_gid` (JS getter), so it
/// runs before the backend is borrowed.
fn to_arg<'js>(v: &Value<'js>, depth: u32) -> Arg {
    if let Some(n) = v.as_number() {
        return Arg::Num(n);
    }
    if let Some(b) = v.as_bool() {
        return Arg::Bool(b);
    }
    if let Some(s) = v.as_string() {
        return Arg::Str(s.to_string().unwrap_or_default());
    }
    if v.is_null() || v.is_undefined() {
        return Arg::Null;
    }
    if let Some(a) = v.as_array() {
        if depth > 0 {
            return Arg::Str("[array]".into());
        }
        let mut out = Vec::new();
        for i in 0..a.len() {
            match a.get::<Value<'js>>(i) {
                Ok(x) => out.push(to_arg(&x, depth + 1)),
                Err(_) => out.push(Arg::Null),
            }
        }
        return Arg::List(out);
    }
    if v.is_function() {
        return Arg::Str("[function]".into());
    }
    if let Some(o) = v.as_object() {
        if let Ok(Some(g)) = o.get::<_, Option<f64>>("__p5_gid") {
            return Arg::Str(format!("gradient#{}", fmt_gid(g)));
        }
        return Arg::Str("[object]".into());
    }
    if v.is_symbol() {
        return Arg::Str("[symbol]".into());
    }
    if v.is_big_int() {
        return Arg::Str("[bigint]".into());
    }
    Arg::Str(format!("[{}]", v.type_name()))
}

fn to_js<'js>(ctx: &Ctx<'js>, a: &Arg) -> Result<Value<'js>> {
    Ok(match a {
        Arg::Num(n) => Value::new_number(ctx.clone(), *n),
        Arg::Str(s) => rquickjs::String::from_str(ctx.clone(), s)?.into_value(),
        Arg::Bool(b) => Value::new_bool(ctx.clone(), *b),
        Arg::Null => Value::new_null(ctx.clone()),
        Arg::List(l) => {
            let arr = Array::new(ctx.clone())?;
            for (i, x) in l.iter().enumerate() {
                arr.set(i, to_js(ctx, x)?)?;
            }
            arr.into_value()
        }
    })
}

/// First "<number>px" in a CSS font string (same scan as `fontPx` in the JS mirror).
fn font_px(font: &str) -> f64 {
    let bytes = font.as_bytes();
    let mut from = 0usize;
    while let Some(off) = font[from..].find("px") {
        let i = from + off;
        let mut j = i;
        while j > 0 && (bytes[j - 1].is_ascii_digit() || bytes[j - 1] == b'.') {
            j -= 1;
        }
        if j < i {
            if let Ok(n) = font[j..i].parse::<f64>() {
                if !n.is_nan() {
                    return n;
                }
            }
        }
        from = i + 1;
    }
    10.0
}

fn call<'js>(ctx: &Ctx<'js>, b: &Rc<RefCell<Backend>>, name: &str, args: &[Value<'js>]) -> Result<Value<'js>> {
    let undefined = Value::new_undefined(ctx.clone());
    let budget = |r: std::result::Result<(), String>| -> Result<()> {
        match r {
            Ok(()) => Ok(()),
            Err(m) => Err(Exception::throw_range(ctx, &m)),
        }
    };
    match name {
        "save" => {
            let mut be = b.borrow_mut();
            if be.stack.len() >= MAX_STACK {
                return Err(Exception::throw_range(ctx, &format!("P5CanvasBudget: save() stack deeper than {MAX_STACK}")));
            }
            let s = be.st.clone();
            be.stack.push(s);
            budget(be.rec("save", Vec::new()))?;
            Ok(undefined)
        }
        "restore" => {
            let mut be = b.borrow_mut();
            if let Some(s) = be.stack.pop() {
                be.st = s;
            }
            budget(be.rec("restore", Vec::new()))?;
            Ok(undefined)
        }
        "setLineDash" => {
            let arr = match args.first().and_then(|v| v.as_array()) {
                Some(a) => a.clone(),
                None => return Ok(undefined),
            };
            let mut n = Vec::new();
            for i in 0..arr.len() {
                let x: Value<'js> = arr.get(i).unwrap_or_else(|_| Value::new_undefined(ctx.clone()));
                n.push(to_num(&x));
            }
            if n.iter().any(|x| !(*x >= 0.0) || x.is_infinite()) {
                return Ok(undefined);
            }
            if n.len() % 2 == 1 {
                let copy = n.clone();
                n.extend(copy);
            }
            let mut be = b.borrow_mut();
            be.st.dash = n.clone();
            budget(be.rec("setLineDash", vec![Arg::List(n.into_iter().map(Arg::Num).collect())]))?;
            Ok(undefined)
        }
        "getLineDash" => {
            let dash = b.borrow().st.dash.clone();
            to_js(ctx, &Arg::List(dash.into_iter().map(Arg::Num).collect()))
        }
        "measureText" => {
            let text = match args.first() {
                Some(v) => <Coerced<String> as FromJs>::from_js(ctx, v.clone())?.0,
                None => "undefined".to_string(),
            };
            let (w, fs) = {
                let mut be = b.borrow_mut();
                let font_idx = be.index("font").unwrap_or(0);
                let font = match &be.st.values[font_idx] {
                    Arg::Str(s) => s.clone(),
                    _ => String::from("10px sans-serif"),
                };
                let fs = font_px(&font);
                let w = text.encode_utf16().count() as f64 * fs * 0.55;
                budget(be.rec("measureText", vec![Arg::Str(text)]))?;
                (w, fs)
            };
            let o = Object::new(ctx.clone())?;
            o.set("width", w)?;
            o.set("actualBoundingBoxLeft", 0.0)?;
            o.set("actualBoundingBoxRight", w)?;
            o.set("actualBoundingBoxAscent", fs * 0.8)?;
            o.set("actualBoundingBoxDescent", fs * 0.2)?;
            o.set("fontBoundingBoxAscent", fs * 0.8)?;
            o.set("fontBoundingBoxDescent", fs * 0.2)?;
            Ok(o.into_value())
        }
        "createLinearGradient" | "createRadialGradient" | "createConicGradient" | "createPattern" => {
            let conv: Vec<Arg> = args.iter().map(|v| to_arg(v, 0)).collect();
            let mut be = b.borrow_mut();
            be.gid += 1;
            let gid = be.gid;
            let mut a = vec![Arg::Num(gid as f64)];
            a.extend(conv);
            budget(be.rec(name, a))?;
            Ok(Value::new_number(ctx.clone(), gid as f64))
        }
        _ => {
            let conv: Vec<Arg> = args.iter().map(|v| to_arg(v, 0)).collect();
            budget(b.borrow_mut().rec(name, conv))?;
            Ok(undefined)
        }
    }
}

fn set<'js>(ctx: &Ctx<'js>, b: &Rc<RefCell<Backend>>, name: &str, value: &Value<'js>) -> Result<()> {
    let idx = match b.borrow().index(name) {
        Some(i) => i,
        None => return Ok(()),
    };
    let kind = b.borrow().props[idx].kind;
    let v: Arg = match kind {
        Kind::Style => {
            if let Some(s) = value.as_string() {
                Arg::Str(s.to_string()?)
            } else if let Some(o) = value.as_object() {
                match o.get::<_, Option<f64>>("__p5_gid") {
                    Ok(Some(g)) if !value.is_function() => Arg::Str(format!("gradient#{}", fmt_gid(g))),
                    _ => return Ok(()),
                }
            } else {
                return Ok(());
            }
        }
        Kind::Str => match value.as_string() {
            Some(s) => Arg::Str(s.to_string()?),
            None => return Ok(()),
        },
        Kind::Enum(allowed) => match value.as_string() {
            Some(s) => {
                let s = s.to_string()?;
                if !allowed.contains(&s.as_str()) {
                    return Ok(());
                }
                Arg::Str(s)
            }
            None => return Ok(()),
        },
        Kind::Bool => {
            let t = <Coerced<bool> as FromJs>::from_js(ctx, value.clone())?.0;
            Arg::Bool(t)
        }
        _ => {
            let n = to_num(value);
            if n.is_nan() || n.is_infinite() {
                return Ok(());
            }
            let ok = match kind {
                Kind::Pos => n > 0.0,
                Kind::NonNeg => n >= 0.0,
                Kind::Alpha => (0.0..=1.0).contains(&n),
                _ => true,
            };
            if !ok {
                return Ok(());
            }
            Arg::Num(n)
        }
    };
    let mut be = b.borrow_mut();
    be.st.values[idx] = v.clone();
    match be.rec("set", vec![Arg::Str(name.to_string()), v]) {
        Ok(()) => Ok(()),
        Err(m) => Err(Exception::throw_range(ctx, &m)),
    }
}

fn make_backend<'js>(ctx: &Ctx<'js>) -> Result<Object<'js>> {
    let b = Rc::new(RefCell::new(Backend::new()));
    let obj = Object::new(ctx.clone())?;
    {
        let b = b.clone();
        obj.set(
            "call",
            Function::new(ctx.clone(), move |ctx: Ctx<'js>, name: Coerced<String>, args: Rest<Value<'js>>| -> Result<Value<'js>> {
                call(&ctx, &b, &name.0, &args.0)
            })?,
        )?;
    }
    {
        let b = b.clone();
        obj.set(
            "set",
            Function::new(ctx.clone(), move |ctx: Ctx<'js>, name: Coerced<String>, value: Value<'js>| -> Result<()> {
                set(&ctx, &b, &name.0, &value)
            })?,
        )?;
    }
    {
        let b = b.clone();
        obj.set(
            "get",
            Function::new(ctx.clone(), move |ctx: Ctx<'js>, name: Coerced<String>| -> Result<Value<'js>> {
                let v = {
                    let be = b.borrow();
                    be.index(&name.0).map(|i| be.st.values[i].clone())
                };
                match v {
                    Some(a) => to_js(&ctx, &a),
                    None => Ok(Value::new_undefined(ctx.clone())),
                }
            })?,
        )?;
    }
    {
        let b = b.clone();
        obj.set(
            "ops",
            Function::new(ctx.clone(), move |ctx: Ctx<'js>| -> Result<Value<'js>> {
                let ops: Vec<(String, Vec<Arg>)> = b.borrow().ops.clone();
                let arr = Array::new(ctx.clone())?;
                for (i, (name, args)) in ops.iter().enumerate() {
                    let mut l = vec![Arg::Str(name.clone())];
                    l.extend(args.iter().cloned());
                    arr.set(i, to_js(&ctx, &Arg::List(l))?)?;
                }
                Ok(arr.into_value())
            })?,
        )?;
    }
    {
        let b = b.clone();
        obj.set("opCount", Function::new(ctx.clone(), move || -> usize { b.borrow().ops.len() })?)?;
    }
    {
        let b = b.clone();
        obj.set(
            "reset",
            Function::new(ctx.clone(), move || {
                *b.borrow_mut() = Backend::new();
            })?,
        )?;
    }
    Ok(obj)
}

/// Defines `globalThis.__host_canvas_backend()`.
pub fn install<'js>(ctx: &Ctx<'js>) -> Result<()> {
    let f = Function::new(ctx.clone(), |ctx: Ctx<'js>| -> Result<Object<'js>> { make_backend(&ctx) })?;
    ctx.globals().set("__host_canvas_backend", f)?;
    Ok(())
}
