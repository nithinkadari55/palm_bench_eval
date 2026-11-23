// Native half of the rquickjs <-> raikiri-dom binding: handle-based functions on
// globalThis.__rkdom over the live raikiri_dom::Document. prelude.js builds the DOM
// interfaces (Node, Element, Document, classList, style, ...) on top of these.
use crate::pipeline::{ms_since, Pipeline, Rect};
use raikiri_dom::{Document, DomMutationError, NodeKind};
use raikiri_style::{SelectorQuery, StyleNodeId};
use rquickjs::{Coerced, Ctx, Function, Object};
use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;
use std::time::Instant;

pub const HTML_NS: &str = "http://www.w3.org/1999/xhtml";

pub struct State {
    pub doc: Document,
    pub pipeline: Pipeline,
    /// Set by every mutation; cleared by a relayout.
    pub dirty: bool,
    pub rects: Option<HashMap<usize, Rect>>,
    pub relayout_ms: Vec<f64>,
    pub rect_queries: usize,
    pub diags: Vec<(String, String)>,
    pub last_error: String,
}

impl State {
    pub fn new(doc: Document, pipeline: Pipeline) -> Self {
        State {
            doc,
            pipeline,
            dirty: true,
            rects: None,
            relayout_ms: Vec::new(),
            rect_queries: 0,
            diags: Vec::new(),
            last_error: String::new(),
        }
    }

    fn node(&self, i: i32) -> Option<usize> {
        if i < 0 {
            return None;
        }
        let i = i as usize;
        self.doc.get_node(i).map(|_| i)
    }

    fn element(&self, i: i32) -> Option<usize> {
        let i = self.node(i)?;
        (self.kind(i) == Some(NodeKind::Element)).then_some(i)
    }

    fn kind(&self, i: usize) -> Option<NodeKind> {
        self.doc.get_node(i).map(|n| n.kind())
    }

    fn mutated(&mut self) {
        self.dirty = true;
    }

    pub fn push_diag(&mut self, kind: &str, message: String) {
        if self.diags.len() < 5000 {
            self.diags.push((kind.to_string(), message));
        }
    }
}

fn mutation_error(e: DomMutationError) -> String {
    match e {
        DomMutationError::HierarchyRequest(m) => format!("HierarchyRequestError: {m}"),
        DomMutationError::NotFound(m) => format!("NotFoundError: {m}"),
    }
}

fn node_type(kind: NodeKind) -> i32 {
    match kind {
        NodeKind::Element => 1,
        NodeKind::Text => 3,
        NodeKind::ProcessingInstruction => 7,
        NodeKind::Comment => 8,
        NodeKind::Document => 9,
        NodeKind::DocumentFragment => 11,
        _ => 0,
    }
}

/// textContent of any node: character data, or the concatenated descendant text.
fn text_of(doc: &Document, i: usize) -> String {
    let Some(node) = doc.get_node(i) else { return String::new() };
    match node.kind() {
        NodeKind::Text | NodeKind::Comment | NodeKind::ProcessingInstruction => {
            doc.character_data(i).unwrap_or("").to_string()
        }
        NodeKind::Element => doc.element_text_content(i).unwrap_or_default(),
        _ => {
            let mut out = String::new();
            let mut stack: Vec<usize> = node.children.iter().rev().copied().collect();
            while let Some(c) = stack.pop() {
                let Some(n) = doc.get_node(c) else { continue };
                if n.kind() == NodeKind::Text {
                    out.push_str(n.text_content().unwrap_or(""));
                } else if n.kind() != NodeKind::Comment {
                    stack.extend(n.children.iter().rev().copied());
                }
            }
            out
        }
    }
}

/// Element ancestors of `index`, root side first, parent last (SelectorQuery's shape).
fn element_ancestors(doc: &Document, index: usize) -> Vec<StyleNodeId> {
    let mut chain = Vec::new();
    let mut current = index;
    while let Some(parent) = doc.parent_of(current) {
        if doc.get_node(parent).map(|n| n.kind()) != Some(NodeKind::Element) {
            break;
        }
        chain.push(StyleNodeId(parent as u64));
        current = parent;
    }
    chain.reverse();
    chain
}

/// Descendant elements of `root` (never `root` itself) matching `query`, in tree order.
fn query_tree(doc: &Document, root: usize, query: &SelectorQuery, all: bool) -> Vec<i32> {
    let Some(root_node) = doc.get_node(root) else { return Vec::new() };
    let scope = (root_node.kind() == NodeKind::Element).then_some(StyleNodeId(root as u64));
    let matcher = query.matcher(doc, scope);
    let mut ancestors = element_ancestors(doc, root);
    if scope.is_some() {
        ancestors.push(StyleNodeId(root as u64));
    }
    let base = ancestors.len();
    let mut stack: Vec<(usize, usize)> = root_node.children.iter().rev().map(|&c| (c, base)).collect();
    let mut out = Vec::new();
    while let Some((node, depth)) = stack.pop() {
        ancestors.truncate(depth);
        let Some(n) = doc.get_node(node) else { continue };
        let child_depth = if n.kind() == NodeKind::Element {
            if matcher.matches(StyleNodeId(node as u64), &ancestors) {
                out.push(node as i32);
                if !all {
                    break;
                }
            }
            ancestors.push(StyleNodeId(node as u64));
            depth + 1
        } else {
            depth
        };
        stack.extend(n.children.iter().rev().map(|&c| (c, child_depth)));
    }
    out
}

fn find_by_id(doc: &Document, root: usize, id: &str) -> i32 {
    let Some(root_node) = doc.get_node(root) else { return -1 };
    let mut stack: Vec<usize> = root_node.children.iter().rev().copied().collect();
    while let Some(i) = stack.pop() {
        let Some(n) = doc.get_node(i) else { continue };
        if n.kind() == NodeKind::Element && doc.element_attribute(i, "id") == Some(id) {
            return i as i32;
        }
        stack.extend(n.children.iter().rev().copied());
    }
    -1
}

/// Brings the geometry snapshot up to date (one raikiri relayout when the DOM changed).
fn ensure_layout(st: &mut State) {
    if !st.dirty && st.rects.is_some() {
        return;
    }
    let t = Instant::now();
    let result = st.pipeline.layout_live(&st.doc);
    st.relayout_ms.push(ms_since(t));
    match result {
        Ok(snapshot) => st.rects = Some(snapshot.rects),
        Err(e) => {
            st.push_diag("js:relayout-error", e);
            st.rects = Some(HashMap::new());
        }
    }
    st.dirty = false;
}

pub fn install<'js>(ctx: &Ctx<'js>, state: &Rc<RefCell<State>>) -> rquickjs::Result<()> {
    let n = Object::new(ctx.clone())?;

    let s = state.clone();
    n.set("root", Function::new(ctx.clone(), move || -> i32 { s.borrow().doc.root_index() as i32 })?)?;

    let s = state.clone();
    n.set(
        "kind",
        Function::new(ctx.clone(), move |i: i32| -> i32 {
            let st = s.borrow();
            st.node(i).and_then(|i| st.kind(i)).map(node_type).unwrap_or(-1)
        })?,
    )?;

    let s = state.clone();
    n.set(
        "tag",
        Function::new(ctx.clone(), move |i: i32| -> String {
            let st = s.borrow();
            st.element(i)
                .and_then(|i| st.doc.get_node(i))
                .and_then(|n| n.tag_name())
                .unwrap_or("")
                .to_string()
        })?,
    )?;

    let s = state.clone();
    n.set(
        "ns",
        Function::new(ctx.clone(), move |i: i32| -> String {
            let st = s.borrow();
            match st.element(i) {
                Some(i) => st.doc.element_namespace_uri(i).unwrap_or(HTML_NS).to_string(),
                None => String::new(),
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "parent",
        Function::new(ctx.clone(), move |i: i32| -> i32 {
            let st = s.borrow();
            st.node(i).and_then(|i| st.doc.parent_of(i)).map(|p| p as i32).unwrap_or(-1)
        })?,
    )?;

    let s = state.clone();
    n.set(
        "children",
        Function::new(ctx.clone(), move |i: i32| -> Vec<i32> {
            let st = s.borrow();
            st.node(i)
                .and_then(|i| st.doc.get_node(i))
                .map(|n| n.children.iter().map(|&c| c as i32).collect())
                .unwrap_or_default()
        })?,
    )?;

    let s = state.clone();
    n.set(
        "templateContent",
        Function::new(ctx.clone(), move |i: i32| -> i32 {
            let st = s.borrow();
            st.element(i)
                .and_then(|i| st.doc.get_node(i))
                .and_then(|n| n.template_contents())
                .map(|c| c as i32)
                .unwrap_or(-1)
        })?,
    )?;

    let s = state.clone();
    n.set(
        "create",
        Function::new(ctx.clone(), move |tag: Coerced<String>| -> i32 {
            let mut st = s.borrow_mut();
            match st.doc.create_detached_element(&tag.0) {
                Ok(i) => {
                    st.mutated();
                    i as i32
                }
                Err(e) => {
                    st.last_error = e;
                    -1
                }
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "createNS",
        Function::new(ctx.clone(), move |ns: Coerced<String>, tag: Coerced<String>| -> i32 {
            let mut st = s.borrow_mut();
            match st.doc.create_detached_element(&tag.0) {
                Ok(i) => {
                    st.doc.set_element_namespace(i, Some(ns.0.as_str().into()));
                    st.mutated();
                    i as i32
                }
                Err(e) => {
                    st.last_error = e;
                    -1
                }
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "text",
        Function::new(ctx.clone(), move |data: Coerced<String>| -> i32 {
            let mut st = s.borrow_mut();
            let i = st.doc.create_detached_text(&data.0);
            st.mutated();
            i as i32
        })?,
    )?;

    let s = state.clone();
    n.set(
        "comment",
        Function::new(ctx.clone(), move |data: Coerced<String>| -> i32 {
            let mut st = s.borrow_mut();
            let i = st.doc.create_detached_comment(&data.0);
            i as i32
        })?,
    )?;

    let s = state.clone();
    n.set(
        "fragment",
        Function::new(ctx.clone(), move || -> i32 {
            let mut st = s.borrow_mut();
            st.doc.create_detached_fragment() as i32
        })?,
    )?;

    let s = state.clone();
    n.set(
        "insert",
        Function::new(ctx.clone(), move |parent: i32, node: i32, before: i32| -> String {
            let mut st = s.borrow_mut();
            let (Some(p), Some(c)) = (st.node(parent), st.node(node)) else {
                return "NotFoundError: invalid node".to_string();
            };
            let before = if before < 0 {
                None
            } else {
                match st.node(before) {
                    Some(b) => Some(b),
                    None => return "NotFoundError: invalid reference node".to_string(),
                }
            };
            match st.doc.pre_insert(p, c, before) {
                Ok(()) => {
                    st.mutated();
                    String::new()
                }
                Err(e) => mutation_error(e),
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "remove",
        Function::new(ctx.clone(), move |parent: i32, child: i32| -> String {
            let mut st = s.borrow_mut();
            let (Some(p), Some(c)) = (st.node(parent), st.node(child)) else {
                return "NotFoundError: invalid node".to_string();
            };
            match st.doc.pre_remove(p, c) {
                Ok(()) => {
                    st.mutated();
                    String::new()
                }
                Err(e) => mutation_error(e),
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "getText",
        Function::new(ctx.clone(), move |i: i32| -> String {
            let st = s.borrow();
            st.node(i).map(|i| text_of(&st.doc, i)).unwrap_or_default()
        })?,
    )?;

    let s = state.clone();
    n.set(
        "setText",
        Function::new(ctx.clone(), move |i: i32, text: Coerced<String>| -> String {
            let mut st = s.borrow_mut();
            let Some(i) = st.node(i) else { return "invalid node".to_string() };
            let result = match st.kind(i) {
                Some(NodeKind::Element) => st.doc.set_element_text_content(i, text.0.as_str()),
                Some(NodeKind::Text) | Some(NodeKind::Comment) => st.doc.set_character_data(i, &text.0),
                _ => Err("textContent is only supported on elements and character data".to_string()),
            };
            match result {
                Ok(()) => {
                    st.mutated();
                    String::new()
                }
                Err(e) => e,
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "getHTML",
        Function::new(ctx.clone(), move |i: i32| -> String {
            let mut st = s.borrow_mut();
            let Some(i) = st.node(i) else { return String::new() };
            match st.doc.serialize_inner_html(i) {
                Ok(html) => html,
                Err(e) => {
                    st.last_error = e;
                    String::new()
                }
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "setHTML",
        Function::new(ctx.clone(), move |i: i32, markup: Coerced<String>| -> String {
            let mut st = s.borrow_mut();
            let Some(i) = st.element(i) else { return "innerHTML target is not an element".to_string() };
            let tag = st.doc.get_node(i).and_then(|n| n.tag_name()).unwrap_or("div").to_string();
            let ns = st.doc.element_namespace_uri(i).unwrap_or(HTML_NS).to_string();
            let options = raikiri_html::ParseOptions::new();
            match raikiri_html::parse_fragment(markup.0.as_bytes(), &options, &tag, &ns, false) {
                Ok(fragment) => {
                    let root = fragment.dom.root_index();
                    st.doc.replace_children_from(i, &fragment.dom, root);
                    st.mutated();
                    String::new()
                }
                Err(e) => format!("fragment parse failed: {e}"),
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "getAttr",
        Function::new(ctx.clone(), move |i: i32, name: Coerced<String>| -> Option<String> {
            let st = s.borrow();
            let i = st.element(i)?;
            st.doc.element_attribute(i, &name.0).map(str::to_string)
        })?,
    )?;

    let s = state.clone();
    n.set(
        "setAttr",
        Function::new(ctx.clone(), move |i: i32, name: Coerced<String>, value: Coerced<String>| -> String {
            let mut st = s.borrow_mut();
            let Some(i) = st.element(i) else { return "setAttribute target is not an element".to_string() };
            match st.doc.set_element_attribute(i, name.0.as_str(), value.0.as_str()) {
                Ok(()) => {
                    st.mutated();
                    String::new()
                }
                Err(e) => e,
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "removeAttr",
        Function::new(ctx.clone(), move |i: i32, name: Coerced<String>| -> String {
            let mut st = s.borrow_mut();
            let Some(i) = st.element(i) else { return "removeAttribute target is not an element".to_string() };
            match st.doc.remove_element_attribute(i, &name.0) {
                Ok(_) => {
                    st.mutated();
                    String::new()
                }
                Err(e) => e,
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "attrNames",
        Function::new(ctx.clone(), move |i: i32| -> Vec<String> {
            let st = s.borrow();
            st.element(i).map(|i| st.doc.element_attribute_names(i)).unwrap_or_default()
        })?,
    )?;

    let s = state.clone();
    n.set(
        "byId",
        Function::new(ctx.clone(), move |root: i32, id: Coerced<String>| -> i32 {
            let st = s.borrow();
            st.node(root).map(|r| find_by_id(&st.doc, r, &id.0)).unwrap_or(-1)
        })?,
    )?;

    let s = state.clone();
    n.set(
        "query",
        Function::new(ctx.clone(), move |root: i32, selector: Coerced<String>, all: bool| -> Option<Vec<i32>> {
            let mut st = s.borrow_mut();
            let query = match SelectorQuery::parse(&selector.0) {
                Ok(q) => q,
                Err(e) => {
                    st.last_error = format!("'{}' is not a valid selector: {e}", selector.0);
                    return None;
                }
            };
            let Some(root) = st.node(root) else { return Some(Vec::new()) };
            st.doc.mark_in_document_flags();
            Some(query_tree(&st.doc, root, &query, all))
        })?,
    )?;

    let s = state.clone();
    n.set(
        "matches",
        Function::new(ctx.clone(), move |i: i32, selector: Coerced<String>| -> i32 {
            let mut st = s.borrow_mut();
            let query = match SelectorQuery::parse(&selector.0) {
                Ok(q) => q,
                Err(e) => {
                    st.last_error = format!("'{}' is not a valid selector: {e}", selector.0);
                    return -1;
                }
            };
            let Some(i) = st.element(i) else { return 0 };
            st.doc.mark_in_document_flags();
            let ancestors = element_ancestors(&st.doc, i);
            i32::from(query.matches(&st.doc, StyleNodeId(i as u64), &ancestors))
        })?,
    )?;

    let s = state.clone();
    n.set(
        "clone",
        Function::new(ctx.clone(), move |i: i32, deep: bool| -> i32 {
            let mut st = s.borrow_mut();
            let Some(i) = st.node(i) else { return -1 };
            match st.doc.clone_node(i, deep) {
                Some(c) => {
                    st.mutated();
                    c as i32
                }
                None => {
                    st.last_error = "node cannot be cloned".to_string();
                    -1
                }
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "rect",
        Function::new(ctx.clone(), move |i: i32| -> Vec<f64> {
            let mut guard = s.borrow_mut();
            let st = &mut *guard;
            st.rect_queries += 1;
            let Some(i) = st.element(i) else { return Vec::new() };
            ensure_layout(st);
            match st.rects.as_ref().and_then(|r| r.get(&i)) {
                Some(r) => vec![r.x, r.y, r.w, r.h],
                None => Vec::new(),
            }
        })?,
    )?;

    let s = state.clone();
    n.set(
        "viewport",
        Function::new(ctx.clone(), move || -> Vec<f64> {
            let st = s.borrow();
            vec![st.pipeline.width_px as f64, st.pipeline.height_px as f64]
        })?,
    )?;

    let s = state.clone();
    n.set(
        "log",
        Function::new(ctx.clone(), move |level: Coerced<String>, message: Coerced<String>| {
            let mut st = s.borrow_mut();
            let kind = if level.0 == "uncaught" { "js:uncaught".to_string() } else { format!("js:console.{}", level.0) };
            st.push_diag(&kind, message.0);
        })?,
    )?;

    let s = state.clone();
    n.set("lastError", Function::new(ctx.clone(), move || -> String { s.borrow().last_error.clone() })?)?;

    ctx.globals().set("__rkdom", n)?;
    Ok(())
}
