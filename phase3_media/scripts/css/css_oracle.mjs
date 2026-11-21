// Test 5 oracle: evaluate every CSS <color> input with colorjs.io 0.7.1 and score the candidates.
//
// colorjs.io parses hex, named, rgb/hsl/hwb, lab/lch/oklab/oklch and color(); it has no color-mix() or relative
// colour syntax (src/parse.js), so those are evaluated here per CSS Color 5 using colorjs conversions only.
// Output colours are mapped to sRGB per CSS Color 4: legacy sRGB functions (hex, named, rgb, hsl, hwb) clip, every
// other result uses the CSS Color 4 gamut-mapping algorithm (colorjs toGamut method "css").
//
// usage: node css_oracle.mjs <inputs.json> <raikiri.json> <libs.json> <results-dir>
import Color from "colorjs.io";
import fs from "node:fs";
import path from "node:path";

const [inputsPath, raikiriPath, libsPath, outDir] = process.argv.slice(2);
const inputs = JSON.parse(fs.readFileSync(inputsPath, "utf8"));
const CURRENT = inputs.current_color;

const SPACE = {
  srgb: "srgb", "srgb-linear": "srgb-linear", "display-p3": "p3", "display-p3-linear": "p3-linear",
  "a98-rgb": "a98rgb", "prophoto-rgb": "prophoto", rec2020: "rec2020", xyz: "xyz-d65", "xyz-d65": "xyz-d65",
  "xyz-d50": "xyz-d50", lab: "lab", lch: "lch", oklab: "oklab", oklch: "oklch", hsl: "hsl", hwb: "hwb",
};
const LEGACY_FN = new Set(["rgb", "rgba", "hsl", "hsla", "hwb"]);
const HUE_INDEX = { hsl: 0, hwb: 0, lch: 2, oklch: 2 };

class Unsupported extends Error {}
class Invalid extends Error {}

function splitTop(s, sepRe) {
  const out = [];
  let depth = 0, cur = "";
  for (const ch of s) {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    if (depth === 0 && sepRe.test(ch)) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out.map(x => x.trim()).filter((x, i, a) => x !== "" || a.length === 1);
}

// ---- tiny calc() evaluator for relative colour components ----
function tokenize(s) {
  const re = /\s*(-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(%|deg|rad|grad|turn)?|\s*([a-z][a-z-]*)\s*\(|\s*([a-z][a-z-]*)|\s*([()+\-*/,])/iy;
  const toks = [];
  let m;
  re.lastIndex = 0;
  while (re.lastIndex < s.length) {
    if (/^\s*$/.test(s.slice(re.lastIndex))) break;
    m = re.exec(s);
    if (!m) throw new Unsupported("calc token at " + s.slice(re.lastIndex));
    if (m[1] !== undefined) toks.push({ t: "num", v: parseFloat(m[1]), u: (m[2] || "").toLowerCase() });
    else if (m[3] !== undefined) toks.push({ t: "fn", v: m[3].toLowerCase() });
    else if (m[4] !== undefined) toks.push({ t: "id", v: m[4].toLowerCase() });
    else toks.push({ t: "op", v: m[5] });
  }
  return toks;
}

function evalExpr(src, env, pctScale) {
  const toks = tokenize(src);
  let i = 0;
  const peek = () => toks[i];
  const unit = (n) => {
    switch (n.u) {
      case "%": return n.v * pctScale / 100;
      case "deg": case "": return n.v;
      case "rad": return n.v * 180 / Math.PI;
      case "grad": return n.v * 0.9;
      case "turn": return n.v * 360;
    }
    throw new Unsupported("unit " + n.u);
  };
  function primary() {
    const tk = toks[i++];
    if (!tk) throw new Unsupported("eof");
    if (tk.t === "num") return unit(tk);
    if (tk.t === "id") {
      if (tk.v in env) return env[tk.v];
      if (tk.v === "pi") return Math.PI;
      if (tk.v === "e") return Math.E;
      throw new Invalid("unknown keyword " + tk.v);
    }
    if (tk.t === "fn") {
      const args = [expr()];
      while (peek() && peek().v === ",") { i++; args.push(expr()); }
      if (!peek() || peek().v !== ")") throw new Unsupported("missing )");
      i++;
      switch (tk.v) {
        case "calc": return args[0];
        case "min": return Math.min(...args);
        case "max": return Math.max(...args);
        case "clamp": return Math.min(Math.max(args[1], args[0]), args[2]);
        case "abs": return Math.abs(args[0]);
        case "round": return Math.round(args[0]);
      }
      throw new Unsupported("function " + tk.v);
    }
    if (tk.v === "(") {
      const v = expr();
      if (!peek() || peek().v !== ")") throw new Unsupported("missing )");
      i++;
      return v;
    }
    if (tk.v === "-") return -primary();
    if (tk.v === "+") return primary();
    throw new Unsupported("unexpected " + tk.v);
  }
  function term() {
    let v = primary();
    while (peek() && (peek().v === "*" || peek().v === "/")) {
      const op = toks[i++].v;
      const r = primary();
      v = op === "*" ? v * r : v / r;
    }
    return v;
  }
  function expr() {
    let v = term();
    while (peek() && (peek().v === "+" || peek().v === "-") && peek().t === "op") {
      const op = toks[i++].v;
      const r = term();
      v = op === "+" ? v + r : v - r;
    }
    return v;
  }
  const v = expr();
  if (i !== toks.length) throw new Unsupported("trailing tokens in " + src);
  return v;
}

// ---- colour evaluation ----
function evalColor(str) {
  const s = str.trim().toLowerCase();
  const m = /^([a-z-]+)\((.*)\)$/s.exec(s);
  if (m) {
    const fn = m[1], inner = m[2];
    if (fn === "color-mix") return { color: colorMix(inner), legacy: false, how: "color-mix (CSS Color 5, colorjs conversions)" };
    if (fn === "light-dark" || fn === "contrast-color" || fn === "alpha" || fn === "color-layers") throw new Unsupported(fn);
    if (/^\s*from\s/.test(inner)) return { color: relative(fn, inner), legacy: false, how: "relative colour (CSS Color 5, colorjs conversions)" };
    return { color: new Color(s), legacy: LEGACY_FN.has(fn), how: "colorjs parse" };
  }
  return { color: new Color(s), legacy: true, how: "colorjs parse" };
}

function colorMix(inner) {
  const parts = splitTop(inner, /,/);
  const head = /^in\s+([a-z0-9-]+)(?:\s+(shorter|longer|increasing|decreasing)\s+hue)?$/.exec(parts[0]);
  if (!head) throw new Invalid("color-mix head " + parts[0]);
  const spaceId = SPACE[head[1]];
  if (!spaceId) throw new Invalid("color-mix space " + head[1]);
  const hueIdx = HUE_INDEX[spaceId];
  if (head[2] && hueIdx === undefined) throw new Invalid("hue method on rectangular space");
  const method = head[2] || "shorter";
  const items = parts.slice(1).map(p => {
    const toks = splitTop(p, /\s/);
    let pct = null;
    const colorToks = [];
    for (const t of toks) {
      if (/%$/.test(t) && !/\(/.test(t)) pct = parseFloat(t);
      else if (/^calc\(/.test(t) && /%/.test(t)) pct = evalExpr(t, {}, 100);
      else colorToks.push(t);
    }
    if (colorToks.length !== 1) throw new Invalid("color-mix item " + p);
    return { c: evalColor(colorToks[0]).color, p: pct };
  });
  if (items.length === 0) throw new Invalid("no colours");
  if (items.length > 2) throw new Unsupported("color-mix with more than two colours");
  for (const it of items) if (it.p !== null && (it.p < 0 || it.p > 100)) throw new Invalid("percentage range");
  if (items.length === 1) {
    const c = Color.to(items[0].c, spaceId);
    const p = items[0].p === null ? 100 : items[0].p;
    return new Color(spaceId, c.coords, (c.alpha === null ? 1 : c.alpha) * p / 100);
  }
  let [p1, p2] = [items[0].p, items[1].p];
  if (p1 === null && p2 === null) { p1 = 50; p2 = 50; }
  else if (p2 === null) p2 = 100 - p1;
  else if (p1 === null) p1 = 100 - p2;
  const sum = p1 + p2;
  if (sum === 0) throw new Invalid("percentages sum to zero");
  const mult = sum < 100 ? sum / 100 : 1;
  const t = p2 / sum;
  const a = Color.to(items[0].c, spaceId), b = Color.to(items[1].c, spaceId);
  let ca = powerless(items[0].c, spaceId, a.coords.slice()), cb = powerless(items[1].c, spaceId, b.coords.slice());
  let aa = a.alpha, ab = b.alpha;
  for (let k = 0; k < 3; k++) {
    if (ca[k] === null && cb[k] !== null) ca[k] = cb[k];
    if (cb[k] === null && ca[k] !== null) cb[k] = ca[k];
  }
  if (aa === null && ab !== null) aa = ab;
  if (ab === null && aa !== null) ab = aa;
  const alphaMissing = aa === null && ab === null;
  if (alphaMissing) { aa = 1; ab = 1; }
  if (hueIdx !== undefined && ca[hueIdx] !== null && cb[hueIdx] !== null) {
    let h1 = ((ca[hueIdx] % 360) + 360) % 360, h2 = ((cb[hueIdx] % 360) + 360) % 360;
    const d = h2 - h1;
    if (method === "shorter") { if (d > 180) h1 += 360; else if (d < -180) h2 += 360; }
    else if (method === "longer") { if (d > 0 && d < 180) h1 += 360; else if (d > -180 && d <= 0) h2 += 360; }
    else if (method === "increasing") { if (d < 0) h2 += 360; }
    else if (method === "decreasing") { if (d > 0) h1 += 360; }
    ca[hueIdx] = h1; cb[hueIdx] = h2;
  }
  const out = [0, 1, 2].map(k => {
    if (ca[k] === null) return null;
    if (k === hueIdx) return ca[k] * (1 - t) + cb[k] * t;
    return ca[k] * aa * (1 - t) + cb[k] * ab * t;
  });
  const alpha = aa * (1 - t) + ab * t;
  for (let k = 0; k < 3; k++) {
    if (out[k] !== null && k !== hueIdx) out[k] = alpha === 0 ? out[k] : out[k] / alpha;
  }
  if (hueIdx !== undefined && out[hueIdx] !== null) out[hueIdx] = ((out[hueIdx] % 360) + 360) % 360;
  return new Color(spaceId, out, alphaMissing ? null : alpha * mult);
}

// CSS Color 4 §4.4.1: a hue that is powerless after converting into the interpolation space is missing.
function powerless(orig, spaceId, coords) {
  const hueIdx = HUE_INDEX[spaceId];
  if (hueIdx === undefined || orig.space.id === spaceId || coords[hueIdx] === null) return coords;
  const [x, y, z] = coords.map(v => v ?? 0);
  let p = false;
  if (spaceId === "hsl") p = Math.abs(y) < 1e-3 || z <= 1e-3 || z >= 100 - 1e-3;
  else if (spaceId === "hwb") p = y + z >= 100 - 1e-3;
  else if (spaceId === "lch") p = Math.abs(y) < 1e-2;
  else if (spaceId === "oklch") p = Math.abs(y) < 1e-4;
  if (p) coords[hueIdx] = null;
  return coords;
}

const REL = {
  rgb: { space: "srgb", ch: ["r", "g", "b"], scale: [255, 255, 255], pct: [255, 255, 255] },
  rgba: { space: "srgb", ch: ["r", "g", "b"], scale: [255, 255, 255], pct: [255, 255, 255] },
  hsl: { space: "hsl", ch: ["h", "s", "l"], scale: [1, 1, 1], pct: [1, 100, 100] },
  hsla: { space: "hsl", ch: ["h", "s", "l"], scale: [1, 1, 1], pct: [1, 100, 100] },
  hwb: { space: "hwb", ch: ["h", "w", "b"], scale: [1, 1, 1], pct: [1, 100, 100] },
  lab: { space: "lab", ch: ["l", "a", "b"], scale: [1, 1, 1], pct: [100, 125, 125] },
  lch: { space: "lch", ch: ["l", "c", "h"], scale: [1, 1, 1], pct: [100, 150, 1] },
  oklab: { space: "oklab", ch: ["l", "a", "b"], scale: [1, 1, 1], pct: [1, 0.4, 0.4] },
  oklch: { space: "oklch", ch: ["l", "c", "h"], scale: [1, 1, 1], pct: [1, 0.4, 1] },
};

function relative(fn, inner) {
  const toks = splitTop(inner, /\s/);
  if (toks[0] !== "from" || toks.length < 3) throw new Invalid("relative syntax");
  const origin = evalColor(toks[1]).color;
  let rest = toks.slice(2);
  let spec;
  if (fn === "color") {
    const sid = SPACE[rest[0]];
    if (!sid || ["lab", "lch", "oklab", "oklch", "hsl", "hwb"].includes(rest[0])) throw new Invalid("color() space " + rest[0]);
    const xyz = sid.startsWith("xyz");
    spec = { space: sid, ch: xyz ? ["x", "y", "z"] : ["r", "g", "b"], scale: [1, 1, 1], pct: [1, 1, 1] };
    rest = rest.slice(1);
  } else {
    spec = REL[fn];
    if (!spec) throw new Invalid("relative function " + fn);
  }
  // re-split so that "/" separates alpha even without surrounding spaces
  const joined = rest.join(" ");
  const slash = splitTop(joined, /\//);
  if (slash.length > 2) throw new Invalid("multiple /");
  const comps = splitTop(slash[0], /\s/);
  if (comps.length !== 3) throw new Invalid("expected three components");
  const conv = Color.to(origin, spec.space);
  const env = {};
  spec.ch.forEach((k, idx) => { env[k] = (conv.coords[idx] ?? 0) * spec.scale[idx]; });
  env.alpha = conv.alpha ?? 0;
  const coords = comps.map((c, idx) => {
    if (c === "none") return null;
    return evalExpr(c, env, spec.pct[idx]) / spec.scale[idx];
  });
  let alpha = env.alpha;
  if (slash.length === 2) alpha = slash[1] === "none" ? null : evalExpr(slash[1], env, 1);
  if (alpha !== null) alpha = Math.min(1, Math.max(0, alpha));
  return new Color(spec.space, coords, alpha);
}

function toSrgb(res) {
  let c = Color.to(res.color, "srgb");
  const coords = c.coords.map(v => v ?? 0);
  c = new Color("srgb", coords, res.color.alpha ?? 0);
  if (res.legacy) {
    return { coords: coords.map(v => Math.min(1, Math.max(0, v))), alpha: c.alpha, mapping: "clip" };
  }
  const g = c.toGamut({ space: "srgb", method: "css" }).to("srgb");
  return { coords: g.coords.map(v => Math.min(1, Math.max(0, v ?? 0))), alpha: c.alpha, mapping: "css-gamut-map" };
}

function oracleFor(cs) {
  const subst = cs.input.replace(/currentcolor/gi, CURRENT);
  const o = { valid: cs.valid };
  if (!cs.valid) return o;
  try {
    const r = evalColor(subst);
    o.srgb = toSrgb(r);
    o.source = r.how;
  } catch (e) {
    o.colorjs_error = String(e.message || e).slice(0, 160);
  }
  if (cs.expected) {
    try {
      const r = evalColor(cs.expected.replace(/currentcolor/gi, CURRENT));
      o.wpt = toSrgb(r);
      // WPT's expected computed value is the spec authors' answer: when colorjs can read it, it is the reference.
      o.input_eval = o.srgb;
      o.input_eval_source = o.source;
      o.srgb = o.wpt;
      o.source = "WPT expected computed value, converted by colorjs";
    } catch (e) { /* expected value not evaluable */ }
  }
  return o;
}

function de(a, b) {
  const ca = new Color("srgb", a.coords, 1), cb = new Color("srgb", b.coords, 1);
  return ca.deltaE2000(cb);
}

function score(name, getResult) {
  const cases = [], perCat = {};
  let totalDe = [], noOracle = 0, excluded = 0;
  for (const cs of inputs.cases) {
    const o = oracles.get(cs.id);
    const r = getResult(cs);
    if (r && r.status === "skipped") { excluded++; continue; }
    const c = { id: cs.id, input: cs.input, category: cs.category, source: cs.source, expected_valid: cs.valid };
    let pass;
    if (!r) {
      c.candidate = "missing";
      pass = false;
    } else if (!cs.valid) {
      pass = r.status === "invalid";
      c.candidate = r.status;
    } else if (r.status !== "ok") {
      pass = false;
      c.candidate = r.status;
      if (r.error) c.error = r.error;
    } else if (!o.srgb || !r.srgb) {
      pass = true;
      c.colour_check = r.srgb ? "no oracle colour (parse acceptance only)" : "candidate colour not evaluable";
      if (!r.srgb) pass = false;
      noOracle += o.srgb ? 0 : 1;
      if (o.colorjs_error) c.oracle_error = o.colorjs_error;
      if (r.srgb) c.candidate_srgb = r.srgb.coords.map(v => +v.toFixed(4));
    } else {
      const d = (o.srgb.alpha === 0 && r.srgb.alpha === 0) ? 0 : de(o.srgb, r.srgb);
      const da = Math.abs((o.srgb.alpha ?? 0) - (r.srgb.alpha ?? 0));
      pass = d <= 1.0 && da <= 0.01;
      c.de2000 = +d.toFixed(4);
      c.alpha_diff = +da.toFixed(4);
      c.oracle_srgb = o.srgb.coords.map(v => +v.toFixed(4));
      c.oracle_alpha = o.srgb.alpha;
      c.oracle_source = o.source;
      c.oracle_mapping = o.srgb.mapping;
      c.candidate_srgb = r.srgb.coords.map(v => +v.toFixed(4));
      c.candidate_alpha = r.srgb.alpha;
      if (o.input_eval) c.de2000_vs_colorjs_eval_of_input = +de(o.input_eval, r.srgb).toFixed(4);
      totalDe.push(d);
    }
    c.pass = pass;
    cases.push(c);
    const pc = perCat[cs.category] ??= { pass: 0, total: 0 };
    pc.total++;
    pc.pass += pass ? 1 : 0;
  }
  const npass = cases.filter(c => c.pass).length;
  totalDe.sort((x, y) => x - y);
  const doc = {
    test: "css_color_" + name, pass: npass, fail: cases.length - npass, total: cases.length,
    pass_rate: cases.length ? npass / cases.length : null,
    pass_criterion: "invalid inputs rejected; valid inputs accepted and, where colorjs.io (or the WPT computed value) gives a colour, " +
      "deltaE2000 <= 1.0 (colorjs deltaE2000, CIE Lab D50) and |alpha diff| <= 0.01 after CSS Color 4 sRGB mapping " +
      "(clip for legacy sRGB syntax, css gamut mapping otherwise); currentcolor = " + CURRENT,
    per_category: perCat,
    de2000_stats: totalDe.length ? { n: totalDe.length, mean: totalDe.reduce((a, b) => a + b, 0) / totalDe.length,
      p95: totalDe[Math.floor(0.95 * (totalDe.length - 1))], max: totalDe[totalDe.length - 1] } : null,
    cases_without_oracle_colour: noOracle,
    excluded_by_harness: excluded,
    first_failures: cases.filter(c => !c.pass).slice(0, 20),
  };
  fs.writeFileSync(path.join(outDir, `css_color_${name}.json`), JSON.stringify(doc, null, 1));
  console.error(`${name}: ${npass}/${cases.length}`);
}

const oracles = new Map(inputs.cases.map(cs => [cs.id, oracleFor(cs)]));

// raikiri: rgba8 from the cascade
const rk = JSON.parse(fs.readFileSync(raikiriPath, "utf8"));
const rkById = new Map(rk.results.map(r => [r.id, r]));
score("raikiri", cs => {
  const r = rkById.get(cs.id);
  if (!r) return null;
  if (r.status !== "ok") return r;
  return { status: "ok", srgb: { coords: r.rgba8.slice(0, 3).map(v => v / 255), alpha: r.rgba8[3] / 255 } };
});

const libs = JSON.parse(fs.readFileSync(libsPath, "utf8")).candidates;
for (const [name, cand] of Object.entries(libs)) {
  const byId = new Map(cand.results.map(r => [r.id, r]));
  score(name, cs => {
    const r = byId.get(cs.id);
    if (!r) return null;
    if (r.status === "ok_nonfinite") return { status: "ok_nonfinite" };
    if (r.status !== "ok") return r;
    if (r.srgb) {
      return { status: "ok", srgb: { coords: r.srgb.slice(0, 3).map(v => Math.min(1, Math.max(0, v))), alpha: r.srgb[3] } };
    }
    try {
      const res = evalColor(r.css.replace(/currentcolor/gi, CURRENT));
      return { status: "ok", srgb: toSrgb(res) };
    } catch (e) {
      return { status: "ok", srgb: null, error: "serialized value not evaluable: " + r.css };
    }
  });
}

// Self-check of the oracle: for WPT computed-value cases, the colour evaluated from the input must match the
// colour of WPT's expected value.
{
  const rows = [];
  let agree = 0, n = 0;
  for (const cs of inputs.cases) {
    if (cs.category !== "wpt-computed" || !cs.expected) continue;
    const o = oracles.get(cs.id);
    if (!o.input_eval || !o.wpt) continue;
    n++;
    const d = de(o.input_eval, o.wpt);
    const da = Math.abs((o.input_eval.alpha ?? 0) - (o.wpt.alpha ?? 0));
    const ok = (o.input_eval.alpha === 0 && o.wpt.alpha === 0) || (d <= 1.0 && da <= 0.01);
    if (ok) agree++; else rows.push({ input: cs.input, expected: cs.expected, de2000: +d.toFixed(3), alpha_diff: +da.toFixed(3), via: o.input_eval_source });
  }
  fs.writeFileSync(path.join(outDir, "css_oracle_selfcheck.json"), JSON.stringify({
    test: "css_oracle_selfcheck", pass: agree, fail: n - agree, total: n, pass_rate: n ? agree / n : null,
    pass_criterion: "diagnostic only (the WPT expected value is the reference for these cases): colorjs evaluation of the WPT input agrees with WPT's expected computed value (deltaE2000 <= 1, alpha <= 0.01)",
    first_failures: rows.slice(0, 20) }, null, 1));
  console.error(`oracle self-check: ${agree}/${n}`);
}
