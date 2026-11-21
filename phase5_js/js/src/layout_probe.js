// Layout-API probe shared by linkedom (bundled) and JSDOM (Node runner).
// Wraps getBoundingClientRect and offset/client/scroll sizes so the report can list which
// elements a script measured and what the DOM returned. With `injected`
// ({ "<key>": {x, y, width, height} }) it answers from host-measured boxes instead:
// that is the second pass of the two-pass prototype.
export function keyOf(el) {
  if (el.id) return '#' + el.id;
  const cls = typeof el.className === 'string' ? el.className.trim() : '';
  return el.tagName.toLowerCase() + (cls ? '.' + cls.split(/\s+/).join('.') : '');
}

function owner(proto, name) {
  for (let p = proto; p; p = Object.getPrototypeOf(p)) {
    if (Object.prototype.hasOwnProperty.call(p, name)) return p;
  }
  return null;
}

export function installLayoutProbe(document, injected, log) {
  const sample = document.createElement('div');
  const base = Object.getPrototypeOf(sample);
  const rectProto = owner(base, 'getBoundingClientRect') || base;
  const nativeRect = rectProto.getBoundingClientRect;
  const lookup = (el) => (injected && Object.prototype.hasOwnProperty.call(injected, keyOf(el)) ? injected[keyOf(el)] : null);
  const record = (el, api, value) => {
    log.push({ key: keyOf(el), api, value: value === undefined ? 'undefined' : value, textLength: (el.textContent || '').length, tag: el.tagName.toLowerCase() });
    return value;
  };
  Object.defineProperty(rectProto, 'getBoundingClientRect', {
    configurable: true, writable: true,
    value: function getBoundingClientRect() {
      const r = lookup(this);
      let v;
      if (r) {
        const x = r.x || 0, y = r.y || 0;
        v = { x, y, left: x, top: y, width: r.width, height: r.height, right: x + r.width, bottom: y + r.height };
      } else if (typeof nativeRect === 'function') {
        const n = nativeRect.call(this);
        v = { x: n.x, y: n.y, left: n.left, top: n.top, width: n.width, height: n.height, right: n.right, bottom: n.bottom };
      }
      record(this, 'getBoundingClientRect', v);
      return v;
    }
  });
  const dims = { offsetWidth: 'width', offsetHeight: 'height', clientWidth: 'width', clientHeight: 'height', scrollWidth: 'width', scrollHeight: 'height' };
  for (const name of Object.keys(dims)) {
    const p = owner(base, name) || rectProto;
    const desc = Object.getOwnPropertyDescriptor(p, name);
    Object.defineProperty(p, name, {
      configurable: true,
      get() {
        const r = lookup(this);
        const v = r ? Math.round(r[dims[name]]) : desc && desc.get ? desc.get.call(this) : undefined;
        return record(this, name, v);
      }
    });
  }
}
