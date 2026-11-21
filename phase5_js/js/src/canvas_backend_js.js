// JS recording Canvas2D backend. It mirrors, rule for rule, the Rust backend in
// crates/qjs/src/canvas.rs (installed there as globalThis.__host_canvas_backend), so
// that Node and Boa produce the op stream the Rust host would record.
// Interface: call(name, ...args), set(name, value), get(name), ops(), opCount(), reset().

export const PROPS = {
  fillStyle: ['style', '#000000'],
  strokeStyle: ['style', '#000000'],
  lineWidth: ['pos', 1],
  miterLimit: ['pos', 10],
  lineDashOffset: ['num', 0],
  globalAlpha: ['alpha', 1],
  shadowBlur: ['nonneg', 0],
  shadowOffsetX: ['num', 0],
  shadowOffsetY: ['num', 0],
  shadowColor: ['str', 'rgba(0, 0, 0, 0)'],
  lineCap: ['enum:butt|round|square', 'butt'],
  lineJoin: ['enum:round|bevel|miter', 'miter'],
  font: ['str', '10px sans-serif'],
  textAlign: ['enum:start|end|left|right|center', 'start'],
  textBaseline: ['enum:top|hanging|middle|alphabetic|ideographic|bottom', 'alphabetic'],
  direction: ['enum:ltr|rtl|inherit', 'inherit'],
  globalCompositeOperation: ['str', 'source-over'],
  filter: ['str', 'none'],
  letterSpacing: ['str', '0px'],
  wordSpacing: ['str', '0px'],
  fontKerning: ['enum:auto|normal|none', 'auto'],
  imageSmoothingEnabled: ['bool', true]
};

export const MAX_OPS = 1000000;
export const MAX_STACK = 100000;

function toNum(v) {
  if (typeof v === 'number') return v;
  if (typeof v === 'boolean') return v ? 1 : 0;
  if (v === null) return 0;
  if (typeof v === 'string') { const t = v.trim(); return t === '' ? NaN : Number(t); }
  return NaN;
}

function toArg(v, depth) {
  if (typeof v === 'number' || typeof v === 'boolean' || typeof v === 'string') return v;
  if (v === null || v === undefined) return null;
  if (Array.isArray(v)) return depth > 0 ? '[array]' : v.map((x) => toArg(x, depth + 1));
  if (typeof v === 'object') return typeof v.__p5_gid === 'number' ? 'gradient#' + v.__p5_gid : '[object]';
  return '[' + typeof v + ']';
}

export function fontPx(font) {
  // first "<number>px": scan for "px" preceded by a digit, walk back over digits and dots
  for (let i = font.indexOf('px'); i >= 0; i = font.indexOf('px', i + 1)) {
    let j = i;
    while (j > 0 && /[0-9.]/.test(font.charAt(j - 1))) j--;
    if (j < i) { const n = Number(font.slice(j, i)); if (n === n) return n; }
  }
  return 10;
}

export function createJsBackend() {
  let ops = [];
  let st = {};
  for (const k in PROPS) st[k] = PROPS[k][1];
  let dash = [];
  let stack = [];
  let gid = 0;
  function rec(op) {
    if (ops.length >= MAX_OPS) throw new RangeError('P5CanvasBudget: more than ' + MAX_OPS + ' recorded ops');
    ops.push(op);
  }
  return {
    native: false,
    call(name, ...args) {
      switch (name) {
        case 'save':
          if (stack.length >= MAX_STACK) throw new RangeError('P5CanvasBudget: save() stack deeper than ' + MAX_STACK);
          stack.push({ st: Object.assign({}, st), dash: dash.slice() });
          rec(['save']);
          return undefined;
        case 'restore': {
          const s = stack.pop();
          if (s) { st = s.st; dash = s.dash; }
          rec(['restore']);
          return undefined;
        }
        case 'setLineDash': {
          const a = args[0];
          if (!Array.isArray(a)) return undefined;
          const n = a.map(toNum);
          if (n.some((x) => !(x >= 0) || x === Infinity)) return undefined;
          dash = n.length % 2 ? n.concat(n) : n;
          rec(['setLineDash', dash.slice()]);
          return undefined;
        }
        case 'getLineDash':
          return dash.slice();
        case 'measureText': {
          const text = args.length ? String(args[0]) : 'undefined';
          const fs = fontPx(st.font);
          const w = text.length * fs * 0.55;
          rec(['measureText', text]);
          return {
            width: w, actualBoundingBoxLeft: 0, actualBoundingBoxRight: w,
            actualBoundingBoxAscent: fs * 0.8, actualBoundingBoxDescent: fs * 0.2,
            fontBoundingBoxAscent: fs * 0.8, fontBoundingBoxDescent: fs * 0.2
          };
        }
        case 'createLinearGradient':
        case 'createRadialGradient':
        case 'createConicGradient':
        case 'createPattern': {
          gid++;
          rec([name, gid].concat(args.map((x) => toArg(x, 0))));
          return gid;
        }
        default:
          rec([name].concat(args.map((x) => toArg(x, 0))));
          return undefined;
      }
    },
    set(name, value) {
      const p = PROPS[name];
      if (!p) return;
      const kind = p[0];
      let v;
      if (kind === 'style') {
        if (typeof value === 'string') v = value;
        else if (value !== null && typeof value === 'object' && typeof value.__p5_gid === 'number') v = 'gradient#' + value.__p5_gid;
        else return;
      } else if (kind === 'str') {
        if (typeof value !== 'string') return;
        v = value;
      } else if (kind.startsWith('enum:')) {
        if (typeof value !== 'string' || kind.slice(5).split('|').indexOf(value) < 0) return;
        v = value;
      } else if (kind === 'bool') {
        v = !!value;
      } else {
        v = toNum(value);
        if (!(v === v) || v === Infinity || v === -Infinity) return;
        if (kind === 'pos' && !(v > 0)) return;
        if (kind === 'nonneg' && !(v >= 0)) return;
        if (kind === 'alpha' && !(v >= 0 && v <= 1)) return;
      }
      st[name] = v;
      rec(['set', name, v]);
    },
    get(name) { return Object.prototype.hasOwnProperty.call(st, name) ? st[name] : undefined; },
    ops() { return ops; },
    opCount() { return ops.length; },
    reset() {
      ops = []; stack = []; dash = []; gid = 0; st = {};
      for (const k in PROPS) st[k] = PROPS[k][1];
    }
  };
}
