// CanvasRenderingContext2D-shaped facade over a recording backend.
// The backend is the Rust host object (globalThis.__host_canvas_backend(), rquickjs)
// or the JS mirror (canvas_backend_js.js, Node/Boa). The facade is identical in both,
// so differences in the op stream come from the backend only.
import { PROPS, createJsBackend } from './canvas_backend_js.js';

export const METHODS = [
  'save', 'restore', 'beginPath', 'closePath', 'moveTo', 'lineTo', 'quadraticCurveTo', 'bezierCurveTo',
  'arc', 'arcTo', 'ellipse', 'rect', 'roundRect', 'fill', 'stroke', 'clip', 'fillRect', 'strokeRect',
  'clearRect', 'fillText', 'strokeText', 'measureText', 'drawImage', 'setLineDash', 'getLineDash',
  'translate', 'rotate', 'scale', 'transform', 'setTransform', 'resetTransform', 'reset'
];

export function makeBackend() {
  if (typeof globalThis.__host_canvas_backend === 'function') {
    const b = globalThis.__host_canvas_backend();
    b.native = true;
    return b;
  }
  return createJsBackend();
}

export function createRecordingCanvas(width, height, backend) {
  const ctx = {};
  const canvas = {
    nodeName: 'CANVAS', tagName: 'CANVAS', id: '', width: width, height: height,
    style: { getPropertyValue() { return ''; }, setProperty() {}, removeProperty() {} },
    ownerDocument: null, parentNode: null,
    getContext(type) { return type === '2d' ? ctx : null; },
    getAttribute() { return null; }, setAttribute() {}, removeAttribute() {},
    addEventListener() {}, removeEventListener() {},
    getBoundingClientRect() { return { x: 0, y: 0, left: 0, top: 0, right: width, bottom: height, width: width, height: height }; },
    toDataURL() { return 'data:,'; }
  };
  ctx.canvas = canvas;
  for (const m of METHODS) {
    if (m === 'reset') { ctx.reset = function () { return backend.call('resetContext'); }; continue; }
    ctx[m] = function () { return backend.call(m, ...arguments); };
  }
  const gradient = (kind) => function () {
    const id = backend.call(kind, ...arguments);
    return { __p5_gid: id, addColorStop(offset, color) { backend.call('addColorStop', id, offset, color); } };
  };
  ctx.createLinearGradient = gradient('createLinearGradient');
  ctx.createRadialGradient = gradient('createRadialGradient');
  ctx.createConicGradient = gradient('createConicGradient');
  ctx.createPattern = gradient('createPattern');
  ctx.isPointInPath = () => false;
  ctx.isPointInStroke = () => false;
  ctx.getTransform = () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 });
  for (const p of Object.keys(PROPS)) {
    Object.defineProperty(ctx, p, {
      get() { return backend.get(p); },
      set(v) { backend.set(p, v); },
      enumerable: true, configurable: true
    });
  }
  return canvas;
}
