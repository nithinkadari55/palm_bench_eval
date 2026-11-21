use raikiri_style::{
    build_rule_tree, cascade, CssColor, StyleDom, StyleElement, StyleNode, StyleNodeId, StyleNodeKind,
};
use serde_json::{json, Value};
use std::panic::{catch_unwind, AssertUnwindSafe};

struct Node {
    kind: StyleNodeKind,
    tag: String,
    style: Option<String>,
    children: Vec<usize>,
    parent: Option<usize>,
}

struct Doc {
    nodes: Vec<Node>,
}

impl Doc {
    fn new() -> Doc {
        Doc {
            nodes: vec![Node { kind: StyleNodeKind::Document, tag: String::new(), style: None, children: Vec::new(), parent: None }],
        }
    }
    fn push(&mut self, parent: usize, tag: &str, style: Option<String>) -> usize {
        let id = self.nodes.len();
        self.nodes.push(Node { kind: StyleNodeKind::Element, tag: tag.to_string(), style, children: Vec::new(), parent: Some(parent) });
        self.nodes[parent].children.push(id);
        id
    }
}

struct NodeRef<'a> {
    doc: &'a Doc,
    id: usize,
}

struct ElemRef<'a> {
    node: &'a Node,
}

struct ChildIter<'a>(std::slice::Iter<'a, usize>);

impl Iterator for ChildIter<'_> {
    type Item = StyleNodeId;
    fn next(&mut self) -> Option<StyleNodeId> {
        self.0.next().map(|&i| StyleNodeId::new(i as u64))
    }
}

impl StyleDom for Doc {
    type NodeRef<'a> = NodeRef<'a>;
    type ChildIter<'a> = ChildIter<'a>;

    fn root_id(&self) -> StyleNodeId {
        StyleNodeId::new(0)
    }
    fn node(&self, id: StyleNodeId) -> Option<NodeRef<'_>> {
        let i = id.0 as usize;
        (i < self.nodes.len()).then_some(NodeRef { doc: self, id: i })
    }
    fn child_ids(&self, id: StyleNodeId) -> ChildIter<'_> {
        let s = self.nodes.get(id.0 as usize).map(|n| n.children.as_slice()).unwrap_or(&[]);
        ChildIter(s.iter())
    }
    fn node_count(&self) -> usize {
        self.nodes.len()
    }
    fn parent_id(&self, child: StyleNodeId) -> Option<StyleNodeId> {
        self.nodes.get(child.0 as usize).and_then(|n| n.parent).map(|p| StyleNodeId::new(p as u64))
    }
}

impl<'a> StyleNode for NodeRef<'a> {
    type Element<'b>
        = ElemRef<'b>
    where
        Self: 'b;
    fn kind(&self) -> StyleNodeKind {
        self.doc.nodes[self.id].kind
    }
    fn as_element(&self) -> Option<ElemRef<'_>> {
        matches!(self.kind(), StyleNodeKind::Element).then(|| ElemRef { node: &self.doc.nodes[self.id] })
    }
    fn text_content(&self) -> Option<&str> {
        None
    }
}

impl<'a> StyleElement for ElemRef<'a> {
    fn tag_name(&self) -> &str {
        &self.node.tag
    }
    fn inline_style_source(&self) -> Option<&str> {
        self.node.style.as_deref().filter(|s| !s.is_empty())
    }
    fn attr(&self, local: &str) -> Option<&str> {
        if local == "style" {
            self.inline_style_source()
        } else {
            None
        }
    }
}

const SENTINELS: [(&str, [u8; 4]); 2] = [("rgb(1 2 3)", [1, 2, 3, 255]), ("rgb(4 5 6)", [4, 5, 6, 255])];

/// Background colors of one element per input, each declared after `sentinel`.
fn eval_chunk(current: &str, sentinel: &str, inputs: &[&str]) -> Result<Vec<CssColor>, String> {
    let mut doc = Doc::new();
    let root = doc.push(0, "html", None);
    let body = doc.push(root, "body", None);
    let mut ids = Vec::with_capacity(inputs.len());
    for inp in inputs {
        let style = format!("color: {current}; background-color: {sentinel}; background-color: {inp}");
        ids.push(doc.push(body, "div", Some(style)));
    }
    let tree = build_rule_tree(&doc);
    let result = cascade(&doc, &tree).map_err(|e| format!("cascade: {e:?}"))?;
    Ok(ids.iter().map(|&i| result.computed[i].background_color).collect())
}

fn eval_guarded(current: &str, sentinel: &str, inputs: &[&str]) -> Vec<Result<CssColor, String>> {
    match catch_unwind(AssertUnwindSafe(|| eval_chunk(current, sentinel, inputs))) {
        Ok(Ok(v)) => v.into_iter().map(Ok).collect(),
        Ok(Err(e)) if inputs.len() == 1 => vec![Err(e)],
        Err(_) if inputs.len() == 1 => vec![Err("panic".to_string())],
        _ => inputs.iter().flat_map(|i| eval_guarded(current, sentinel, &[*i])).collect(),
    }
}

fn main() {
    std::panic::set_hook(Box::new(|_| {}));
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: csscolor_raikiri <inputs.json> <out.json>");
        std::process::exit(2);
    }
    let doc: Value = serde_json::from_slice(&std::fs::read(&args[1]).expect("read inputs")).expect("parse inputs");
    let current = doc["current_color"].as_str().unwrap_or("rgb(10 20 30)").to_string();
    let cases = doc["cases"].as_array().cloned().unwrap_or_default();
    let mut out = Vec::new();
    let usable: Vec<(String, String)> = cases
        .iter()
        .map(|c| (c["id"].as_str().unwrap_or("").to_string(), c["input"].as_str().unwrap_or("").to_string()))
        .collect();
    let mut runs: Vec<Vec<Result<CssColor, String>>> = Vec::new();
    for (sentinel, _) in SENTINELS.iter() {
        let mut all = Vec::with_capacity(usable.len());
        for chunk in usable.chunks(400) {
            let inputs: Vec<&str> = chunk
                .iter()
                .map(|(_, s)| if s.contains([';', '{', '}']) { "" } else { s.as_str() })
                .collect();
            all.extend(eval_guarded(&current, sentinel, &inputs));
        }
        runs.push(all);
    }
    for (i, (id, input)) in usable.iter().enumerate() {
        if input.contains([';', '{', '}']) {
            out.push(json!({"id": id, "status": "skipped", "reason": "input contains ; { or }"}));
            continue;
        }
        match (&runs[0][i], &runs[1][i]) {
            (Ok(a), Ok(b)) => {
                let a4 = [a.r, a.g, a.b, a.a];
                let b4 = [b.r, b.g, b.b, b.a];
                if a4 == SENTINELS[0].1 && b4 == SENTINELS[1].1 {
                    out.push(json!({"id": id, "status": "invalid"}));
                } else if a4 == b4 {
                    out.push(json!({"id": id, "status": "ok", "rgba8": a4}));
                } else {
                    out.push(json!({"id": id, "status": "inconsistent", "run0": a4, "run1": b4}));
                }
            }
            (Err(e), _) | (_, Err(e)) => out.push(json!({"id": id, "status": "error", "error": e})),
        }
    }
    let result = json!({"candidate": "raikiri-style", "rev": "a570d9031237fb18cf015592960adeda906bff30", "current_color": current, "results": out});
    std::fs::write(&args[2], serde_json::to_vec_pretty(&result).unwrap()).expect("write output");
}
