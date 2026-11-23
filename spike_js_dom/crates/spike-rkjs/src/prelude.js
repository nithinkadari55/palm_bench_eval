// DOM facade for the rquickjs spike. Every node lives in the raikiri-dom arena owned by
// Rust; JS wrappers hold only the arena index. Natives are on globalThis.__rkdom
// (see dom.rs). Evaluated once before any page script.
(function (g) {
  'use strict';
  var N = g.__rkdom;
  var IDX = Symbol('rkIndex');
  var cache = new Map();
  var HTML_NS = 'http://www.w3.org/1999/xhtml';

  function DOMException(message, name) {
    var e = new Error(message);
    Object.setPrototypeOf(e, DOMException.prototype);
    e.name = name || 'Error';
    return e;
  }
  DOMException.prototype = Object.create(Error.prototype);
  DOMException.prototype.constructor = DOMException;
  if (typeof g.DOMException !== 'function') g.DOMException = DOMException;

  function check(err, name) {
    if (err) throw new g.DOMException(err, name || 'HierarchyRequestError');
  }
  function idx(node, what) {
    if (node === null || node === undefined || node[IDX] === undefined) {
      throw new TypeError((what || 'argument') + ' is not a Node');
    }
    return node[IDX];
  }
  function wrap(i) {
    if (i === undefined || i === null || i < 0) return null;
    var w = cache.get(i);
    if (w) return w;
    var k = N.kind(i);
    var proto;
    if (k === 1) proto = N.ns(i) === HTML_NS || N.ns(i) === '' ? HTMLElement.prototype : Element.prototype;
    else if (k === 3) proto = Text.prototype;
    else if (k === 8) proto = Comment.prototype;
    else if (k === 9) proto = Document.prototype;
    else if (k === 11) proto = DocumentFragment.prototype;
    else proto = Node.prototype;
    w = Object.create(proto);
    Object.defineProperty(w, IDX, { value: i });
    cache.set(i, w);
    return w;
  }
  function list(indices) {
    var out = indices.map(wrap);
    out.item = function (n) { return out[n] === undefined ? null : out[n]; };
    return out;
  }
  function toNode(v) {
    if (v !== null && typeof v === 'object' && v[IDX] !== undefined) return v;
    return document.createTextNode(String(v));
  }

  // ------------------------------------------------------------------ Node
  function Node() { throw new TypeError('Illegal constructor'); }
  Node.ELEMENT_NODE = 1; Node.TEXT_NODE = 3; Node.COMMENT_NODE = 8;
  Node.DOCUMENT_NODE = 9; Node.DOCUMENT_FRAGMENT_NODE = 11;
  function accessor(proto, name, get, set) {
    Object.defineProperty(proto, name, { get: get, set: set, configurable: true, enumerable: true });
  }
  var NP = Node.prototype;
  accessor(NP, 'nodeType', function () { return N.kind(this[IDX]); });
  accessor(NP, 'nodeName', function () {
    var k = N.kind(this[IDX]);
    if (k === 1) return this.tagName;
    return { 3: '#text', 8: '#comment', 9: '#document', 11: '#document-fragment' }[k] || '';
  });
  accessor(NP, 'parentNode', function () { return wrap(N.parent(this[IDX])); });
  accessor(NP, 'parentElement', function () {
    var p = N.parent(this[IDX]);
    return p >= 0 && N.kind(p) === 1 ? wrap(p) : null;
  });
  accessor(NP, 'childNodes', function () { return list(N.children(this[IDX])); });
  accessor(NP, 'firstChild', function () { var c = N.children(this[IDX]); return c.length ? wrap(c[0]) : null; });
  accessor(NP, 'lastChild', function () { var c = N.children(this[IDX]); return c.length ? wrap(c[c.length - 1]) : null; });
  function sibling(node, step, elementsOnly) {
    var i = node[IDX];
    var p = N.parent(i);
    if (p < 0) return null;
    var c = N.children(p);
    for (var k = c.indexOf(i) + step; k >= 0 && k < c.length; k += step) {
      if (!elementsOnly || N.kind(c[k]) === 1) return wrap(c[k]);
    }
    return null;
  }
  accessor(NP, 'nextSibling', function () { return sibling(this, 1, false); });
  accessor(NP, 'previousSibling', function () { return sibling(this, -1, false); });
  accessor(NP, 'ownerDocument', function () { return N.kind(this[IDX]) === 9 ? null : document; });
  accessor(NP, 'isConnected', function () {
    var i = this[IDX];
    var root = N.root();
    while (i >= 0) { if (i === root) return true; i = N.parent(i); }
    return false;
  });
  accessor(NP, 'textContent', function () {
    var k = N.kind(this[IDX]);
    return k === 9 ? null : N.getText(this[IDX]);
  }, function (v) {
    check(N.setText(this[IDX], v === null || v === undefined ? '' : String(v)), 'InvalidStateError');
  });
  accessor(NP, 'nodeValue', function () {
    var k = N.kind(this[IDX]);
    return k === 3 || k === 8 ? N.getText(this[IDX]) : null;
  }, function (v) {
    var k = N.kind(this[IDX]);
    if (k === 3 || k === 8) check(N.setText(this[IDX], String(v)));
  });
  NP.hasChildNodes = function () { return N.children(this[IDX]).length > 0; };
  NP.appendChild = function (child) {
    check(N.insert(this[IDX], idx(child, 'child'), -1));
    return child;
  };
  NP.insertBefore = function (child, ref) {
    var r = ref === null || ref === undefined ? -1 : idx(ref, 'reference child');
    check(N.insert(this[IDX], idx(child, 'child'), r));
    return child;
  };
  NP.removeChild = function (child) {
    check(N.remove(this[IDX], idx(child, 'child')), 'NotFoundError');
    return child;
  };
  NP.replaceChild = function (newChild, oldChild) {
    this.insertBefore(newChild, oldChild);
    return this.removeChild(oldChild);
  };
  NP.contains = function (other) {
    if (!other) return false;
    var i = other[IDX];
    while (i >= 0) { if (i === this[IDX]) return true; i = N.parent(i); }
    return false;
  };
  NP.cloneNode = function (deep) {
    var c = N.clone(this[IDX], !!deep);
    if (c < 0) throw new g.DOMException(N.lastError(), 'NotSupportedError');
    return wrap(c);
  };
  // Events: listeners are kept per wrapper. Paged rendering has no user input, so only
  // synthetic dispatchEvent and the host's DOMContentLoaded/load reach them.
  var listeners = new Map();
  function addListener(target, type, fn) {
    if (typeof fn !== 'function' && !(fn && typeof fn.handleEvent === 'function')) return;
    var m = listeners.get(target);
    if (!m) { m = {}; listeners.set(target, m); }
    (m[type] = m[type] || []).push(fn);
  }
  function removeListener(target, type, fn) {
    var m = listeners.get(target);
    if (!m || !m[type]) return;
    m[type] = m[type].filter(function (f) { return f !== fn; });
  }
  function callListeners(target, event) {
    var m = listeners.get(target);
    var fns = m && m[event.type] ? m[event.type].slice() : [];
    var handler = target['on' + event.type];
    if (typeof handler === 'function') fns.push(handler);
    for (var k = 0; k < fns.length; k++) {
      event.currentTarget = target;
      try {
        if (typeof fns[k] === 'function') fns[k].call(target, event);
        else fns[k].handleEvent(event);
      } catch (e) { reportError(e, 'listener for ' + event.type); }
      if (event._stopImmediate) break;
    }
  }
  function Event(type, init) {
    this.type = String(type);
    this.bubbles = !!(init && init.bubbles);
    this.cancelable = !!(init && init.cancelable);
    this.detail = init && init.detail !== undefined ? init.detail : null;
    this.defaultPrevented = false;
    this.target = null;
    this.currentTarget = null;
    this.timeStamp = 0;
  }
  Event.prototype.preventDefault = function () { if (this.cancelable) this.defaultPrevented = true; };
  Event.prototype.stopPropagation = function () { this._stop = true; };
  Event.prototype.stopImmediatePropagation = function () { this._stop = true; this._stopImmediate = true; };
  g.Event = Event;
  g.CustomEvent = function CustomEvent(type, init) { Event.call(this, type, init); };
  g.CustomEvent.prototype = Object.create(Event.prototype);
  function dispatch(target, event) {
    event.target = target;
    var path = [target];
    if (target !== g && target[IDX] !== undefined) {
      for (var p = target.parentNode; p; p = p.parentNode) path.push(p);
      if (event.type !== 'load') path.push(g);
    }
    for (var k = 0; k < path.length; k++) {
      if (k > 0 && !event.bubbles) break;
      callListeners(path[k], event);
      if (event._stop) break;
    }
    return !event.defaultPrevented;
  }
  NP.addEventListener = function (type, fn) { addListener(this, type, fn); };
  NP.removeEventListener = function (type, fn) { removeListener(this, type, fn); };
  NP.dispatchEvent = function (event) { return dispatch(this, event); };

  // --------------------------------------------------------- ParentNode mixin
  function parentNodeMixin(proto) {
    accessor(proto, 'children', function () {
      return list(N.children(this[IDX]).filter(function (c) { return N.kind(c) === 1; }));
    });
    accessor(proto, 'childElementCount', function () { return this.children.length; });
    accessor(proto, 'firstElementChild', function () { return this.children[0] || null; });
    accessor(proto, 'lastElementChild', function () { var c = this.children; return c[c.length - 1] || null; });
    proto.querySelector = function (sel) {
      var r = N.query(this[IDX], String(sel), false);
      if (r === undefined) throw new g.DOMException(N.lastError(), 'SyntaxError');
      return r.length ? wrap(r[0]) : null;
    };
    proto.querySelectorAll = function (sel) {
      var r = N.query(this[IDX], String(sel), true);
      if (r === undefined) throw new g.DOMException(N.lastError(), 'SyntaxError');
      return list(r);
    };
    proto.getElementsByTagName = function (tag) { return this.querySelectorAll(String(tag)); };
    proto.getElementsByClassName = function (names) {
      var sel = String(names).trim().split(/\s+/).filter(Boolean).map(function (c) { return '.' + cssEscape(c); }).join('');
      return sel ? this.querySelectorAll(sel) : list([]);
    };
    proto.append = function () {
      for (var k = 0; k < arguments.length; k++) this.appendChild(toNode(arguments[k]));
    };
    proto.prepend = function () {
      var first = this.firstChild;
      for (var k = 0; k < arguments.length; k++) this.insertBefore(toNode(arguments[k]), first);
    };
    proto.replaceChildren = function () {
      var c = N.children(this[IDX]);
      for (var k = 0; k < c.length; k++) N.remove(this[IDX], c[k]);
      this.append.apply(this, arguments);
    };
  }
  function cssEscape(s) {
    return String(s).replace(/([^a-zA-Z0-9_\u00a0-\uffff-])/g, '\\$1').replace(/^(\d)/, '\\3$1 ');
  }
  if (!g.CSS) g.CSS = {};
  if (!g.CSS.escape) g.CSS.escape = cssEscape;

  // ------------------------------------------------------- CharacterData
  function CharacterData() { throw new TypeError('Illegal constructor'); }
  CharacterData.prototype = Object.create(NP);
  accessor(CharacterData.prototype, 'data', function () { return N.getText(this[IDX]); },
    function (v) { check(N.setText(this[IDX], String(v))); });
  accessor(CharacterData.prototype, 'length', function () { return N.getText(this[IDX]).length; });
  function Text() { throw new TypeError('Illegal constructor'); }
  Text.prototype = Object.create(CharacterData.prototype);
  accessor(Text.prototype, 'wholeText', function () { return N.getText(this[IDX]); });
  function Comment() { throw new TypeError('Illegal constructor'); }
  Comment.prototype = Object.create(CharacterData.prototype);
  function childNodeMixin(proto) {
    proto.remove = function () { var p = N.parent(this[IDX]); if (p >= 0) N.remove(p, this[IDX]); };
    proto.before = function () {
      var p = this.parentNode; if (!p) return;
      for (var k = 0; k < arguments.length; k++) p.insertBefore(toNode(arguments[k]), this);
    };
    proto.after = function () {
      var p = this.parentNode; if (!p) return;
      var next = this.nextSibling;
      for (var k = 0; k < arguments.length; k++) p.insertBefore(toNode(arguments[k]), next);
    };
    proto.replaceWith = function () {
      var p = this.parentNode; if (!p) return;
      var next = this.nextSibling;
      p.removeChild(this);
      for (var k = 0; k < arguments.length; k++) p.insertBefore(toNode(arguments[k]), next);
    };
  }
  childNodeMixin(CharacterData.prototype);

  // ------------------------------------------------------------ Element
  function Element() { throw new TypeError('Illegal constructor'); }
  var EP = Element.prototype = Object.create(NP);
  parentNodeMixin(EP);
  childNodeMixin(EP);
  accessor(EP, 'localName', function () { return N.tag(this[IDX]); });
  accessor(EP, 'tagName', function () {
    var t = N.tag(this[IDX]);
    var ns = N.ns(this[IDX]);
    return ns === HTML_NS || ns === '' ? t.toUpperCase() : t;
  });
  accessor(EP, 'namespaceURI', function () { return N.ns(this[IDX]) || null; });
  function reflect(name, attr) {
    accessor(EP, name, function () { var v = N.getAttr(this[IDX], attr); return v === undefined ? '' : v; },
      function (v) { check(N.setAttr(this[IDX], attr, String(v)), 'InvalidCharacterError'); });
  }
  reflect('id', 'id');
  reflect('className', 'class');
  reflect('title', 'title');
  reflect('lang', 'lang');
  reflect('dir', 'dir');
  reflect('name', 'name');
  reflect('href', 'href');
  reflect('src', 'src');
  reflect('alt', 'alt');
  reflect('type', 'type');
  reflect('rel', 'rel');
  reflect('target', 'target');
  reflect('placeholder', 'placeholder');
  accessor(EP, 'hidden', function () { return N.getAttr(this[IDX], 'hidden') !== undefined; },
    function (v) { if (v) N.setAttr(this[IDX], 'hidden', ''); else N.removeAttr(this[IDX], 'hidden'); });
  accessor(EP, 'value', function () {
    var v = N.getAttr(this[IDX], 'value');
    return v === undefined ? (N.tag(this[IDX]) === 'textarea' ? N.getText(this[IDX]) : '') : v;
  }, function (v) {
    if (N.tag(this[IDX]) === 'textarea') N.setText(this[IDX], String(v));
    else N.setAttr(this[IDX], 'value', String(v));
  });
  EP.getAttribute = function (name) { var v = N.getAttr(this[IDX], String(name)); return v === undefined ? null : v; };
  EP.setAttribute = function (name, value) { check(N.setAttr(this[IDX], String(name), String(value)), 'InvalidCharacterError'); };
  EP.setAttributeNS = function (ns, name, value) {
    var local = String(name).split(':').pop();
    check(N.setAttr(this[IDX], local, String(value)), 'InvalidCharacterError');
  };
  EP.getAttributeNS = function (ns, name) { return this.getAttribute(name); };
  EP.removeAttribute = function (name) { N.removeAttr(this[IDX], String(name)); };
  EP.hasAttribute = function (name) { return N.getAttr(this[IDX], String(name)) !== undefined; };
  EP.toggleAttribute = function (name, force) {
    var has = this.hasAttribute(name);
    var want = force === undefined ? !has : !!force;
    if (want && !has) this.setAttribute(name, '');
    if (!want && has) this.removeAttribute(name);
    return want;
  };
  EP.getAttributeNames = function () { return N.attrNames(this[IDX]); };
  accessor(EP, 'attributes', function () {
    var self = this;
    return list([]).concat(N.attrNames(this[IDX]).map(function (n) {
      return { name: n, localName: n, value: N.getAttr(self[IDX], n) };
    }));
  });
  accessor(EP, 'innerHTML', function () { return N.getHTML(this[IDX]); },
    function (v) { check(N.setHTML(this[IDX], v === null ? '' : String(v)), 'SyntaxError'); });
  accessor(EP, 'outerHTML', function () {
    var self = this;
    var tag = N.tag(this[IDX]);
    var attrs = N.attrNames(this[IDX]).map(function (n) {
      return ' ' + n + '="' + String(N.getAttr(self[IDX], n)).replace(/&/g, '&amp;').replace(/"/g, '&quot;') + '"';
    }).join('');
    var voids = /^(area|base|br|col|embed|hr|img|input|link|meta|source|track|wbr)$/;
    return '<' + tag + attrs + '>' + (voids.test(tag) ? '' : N.getHTML(this[IDX]) + '</' + tag + '>');
  }, function (v) {
    var p = this.parentNode;
    if (!p) return;
    this.insertAdjacentHTML('beforebegin', String(v));
    p.removeChild(this);
  });
  accessor(EP, 'innerText', function () { return N.getText(this[IDX]); },
    function (v) { check(N.setText(this[IDX], String(v))); });
  function parseInto(contextIndex, html) {
    var holder = N.create(N.tag(contextIndex) || 'div');
    if (holder < 0) holder = N.create('div');
    check(N.setHTML(holder, html), 'SyntaxError');
    return N.children(holder);
  }
  EP.insertAdjacentHTML = function (pos, html) {
    pos = String(pos).toLowerCase();
    var p = N.parent(this[IDX]);
    var nodes;
    if (pos === 'beforebegin' || pos === 'afterend') {
      if (p < 0) throw new g.DOMException('element has no parent', 'NoModificationAllowedError');
      nodes = parseInto(p, String(html));
    } else {
      nodes = parseInto(this[IDX], String(html));
    }
    var ref;
    var parent;
    if (pos === 'beforebegin') { parent = p; ref = this[IDX]; }
    else if (pos === 'afterbegin') { parent = this[IDX]; var c = N.children(this[IDX]); ref = c.length ? c[0] : -1; }
    else if (pos === 'beforeend') { parent = this[IDX]; ref = -1; }
    else if (pos === 'afterend') { parent = p; var next = sibling(this, 1, false); ref = next ? next[IDX] : -1; }
    else throw new g.DOMException('invalid position ' + pos, 'SyntaxError');
    for (var k = 0; k < nodes.length; k++) check(N.insert(parent, nodes[k], ref));
  };
  EP.insertAdjacentElement = function (pos, el) {
    pos = String(pos).toLowerCase();
    if (pos === 'beforebegin') this.parentNode.insertBefore(el, this);
    else if (pos === 'afterbegin') this.insertBefore(el, this.firstChild);
    else if (pos === 'beforeend') this.appendChild(el);
    else if (pos === 'afterend') this.parentNode.insertBefore(el, this.nextSibling);
    return el;
  };
  EP.insertAdjacentText = function (pos, text) { this.insertAdjacentElement(pos, document.createTextNode(String(text))); };
  EP.matches = function (sel) {
    var r = N.matches(this[IDX], String(sel));
    if (r < 0) throw new g.DOMException(N.lastError(), 'SyntaxError');
    return r === 1;
  };
  EP.webkitMatchesSelector = EP.matches;
  EP.closest = function (sel) {
    for (var e = this; e && e.nodeType === 1; e = e.parentElement) if (e.matches(sel)) return e;
    return null;
  };
  accessor(EP, 'nextElementSibling', function () { return sibling(this, 1, true); });
  accessor(EP, 'previousElementSibling', function () { return sibling(this, -1, true); });

  // classList (DOMTokenList over the class attribute)
  function tokenList(el, attr) {
    function read() { var v = N.getAttr(el[IDX], attr); return v ? v.split(/\s+/).filter(Boolean) : []; }
    function write(t) { check(N.setAttr(el[IDX], attr, t.join(' '))); }
    function valid(t) {
      t = String(t);
      if (t === '') throw new g.DOMException('empty token', 'SyntaxError');
      if (/\s/.test(t)) throw new g.DOMException('token contains whitespace', 'InvalidCharacterError');
      return t;
    }
    var api = {
      add: function () { var t = read(); for (var k = 0; k < arguments.length; k++) { var s = valid(arguments[k]); if (t.indexOf(s) < 0) t.push(s); } write(t); },
      remove: function () { var t = read(); for (var k = 0; k < arguments.length; k++) { var s = valid(arguments[k]); t = t.filter(function (x) { return x !== s; }); } write(t); },
      toggle: function (s, force) {
        s = valid(s);
        var t = read();
        var has = t.indexOf(s) >= 0;
        var want = force === undefined ? !has : !!force;
        if (want && !has) t.push(s);
        if (!want && has) t = t.filter(function (x) { return x !== s; });
        write(t);
        return want;
      },
      contains: function (s) { return read().indexOf(String(s)) >= 0; },
      replace: function (a, b) { var t = read(); var k = t.indexOf(valid(a)); if (k < 0) return false; t[k] = valid(b); write(t); return true; },
      item: function (n) { var t = read(); return n < t.length ? t[n] : null; },
      forEach: function (fn, self) { read().forEach(fn, self); },
      toString: function () { return read().join(' '); },
      entries: function () { return read().entries(); },
      values: function () { return read().values(); },
      keys: function () { return read().keys(); }
    };
    accessor(api, 'length', function () { return read().length; });
    accessor(api, 'value', function () { var v = N.getAttr(el[IDX], attr); return v === undefined ? '' : v; },
      function (v) { check(N.setAttr(el[IDX], attr, String(v))); });
    api[Symbol.iterator] = function () { return read()[Symbol.iterator](); };
    return api;
  }
  accessor(EP, 'classList', function () { return tokenList(this, 'class'); },
    function (v) { check(N.setAttr(this[IDX], 'class', String(v))); });
  accessor(EP, 'relList', function () { return tokenList(this, 'rel'); });

  // dataset
  function camelToData(p) { return 'data-' + p.replace(/[A-Z]/g, function (c) { return '-' + c.toLowerCase(); }); }
  function dataToCamel(n) { return n.slice(5).replace(/-([a-z])/g, function (m, c) { return c.toUpperCase(); }); }
  accessor(EP, 'dataset', function () {
    var el = this;
    return new Proxy({}, {
      get: function (t, p) { if (typeof p !== 'string') return undefined; var v = N.getAttr(el[IDX], camelToData(p)); return v; },
      set: function (t, p, v) { check(N.setAttr(el[IDX], camelToData(String(p)), String(v)), 'InvalidCharacterError'); return true; },
      has: function (t, p) { return typeof p === 'string' && N.getAttr(el[IDX], camelToData(p)) !== undefined; },
      deleteProperty: function (t, p) { N.removeAttr(el[IDX], camelToData(String(p))); return true; },
      ownKeys: function () { return N.attrNames(el[IDX]).filter(function (n) { return n.indexOf('data-') === 0; }).map(dataToCamel); },
      getOwnPropertyDescriptor: function (t, p) {
        var v = typeof p === 'string' ? N.getAttr(el[IDX], camelToData(p)) : undefined;
        return v === undefined ? undefined : { value: v, writable: true, enumerable: true, configurable: true };
      }
    });
  });

  // style: CSSStyleDeclaration over the inline style attribute. Values are not validated
  // (raikiri-style parses them at layout time and drops invalid ones).
  function splitDecls(text) {
    var out = [];
    var cur = '';
    var depth = 0;
    var quote = null;
    for (var k = 0; k < text.length; k++) {
      var c = text[k];
      if (quote) { if (c === quote && text[k - 1] !== '\\') quote = null; cur += c; continue; }
      if (c === '"' || c === "'") { quote = c; cur += c; continue; }
      if (c === '(') depth++;
      if (c === ')') depth = Math.max(0, depth - 1);
      if (c === ';' && depth === 0) { out.push(cur); cur = ''; continue; }
      cur += c;
    }
    out.push(cur);
    var decls = [];
    out.forEach(function (d) {
      var k = d.indexOf(':');
      if (k <= 0) return;
      var name = d.slice(0, k).trim();
      if (name.indexOf('--') !== 0) name = name.toLowerCase();
      var value = d.slice(k + 1).trim();
      var important = false;
      var m = /!\s*important\s*$/i.exec(value);
      if (m) { important = true; value = value.slice(0, m.index).trim(); }
      if (name) decls.push([name, value, important]);
    });
    return decls;
  }
  function kebab(p) {
    if (p === 'cssFloat') return 'float';
    if (p.indexOf('--') === 0) return p;
    var s = p.replace(/[A-Z]/g, function (c) { return '-' + c.toLowerCase(); });
    if (/^(webkit|moz|ms|o)-/.test(s)) s = '-' + s;
    return s;
  }
  function styleDecl(el) {
    function read() { var v = N.getAttr(el[IDX], 'style'); return v ? splitDecls(v) : []; }
    function write(d) {
      var s = d.map(function (x) { return x[0] + ': ' + x[1] + (x[2] ? ' !important' : ''); }).join('; ');
      if (s) check(N.setAttr(el[IDX], 'style', s)); else N.removeAttr(el[IDX], 'style');
    }
    function norm(n) { n = String(n).trim(); return n.indexOf('--') === 0 ? n : n.toLowerCase(); }
    var api = {
      setProperty: function (name, value, priority) {
        name = norm(name);
        if (value === null || value === undefined || String(value).trim() === '') { api.removeProperty(name); return; }
        var d = read();
        var e = [name, String(value).trim(), String(priority || '').toLowerCase() === 'important'];
        var k = -1;
        for (var j = 0; j < d.length; j++) if (d[j][0] === name) k = j;
        if (k >= 0) d[k] = e; else d.push(e);
        write(d);
      },
      getPropertyValue: function (name) {
        name = norm(name);
        var d = read();
        for (var j = d.length - 1; j >= 0; j--) if (d[j][0] === name) return d[j][1];
        return '';
      },
      getPropertyPriority: function (name) {
        name = norm(name);
        var d = read();
        for (var j = d.length - 1; j >= 0; j--) if (d[j][0] === name) return d[j][2] ? 'important' : '';
        return '';
      },
      removeProperty: function (name) {
        name = norm(name);
        var old = api.getPropertyValue(name);
        write(read().filter(function (x) { return x[0] !== name; }));
        return old;
      },
      item: function (n) { var d = read(); return n < d.length ? d[n][0] : ''; }
    };
    accessor(api, 'cssText', function () { var v = N.getAttr(el[IDX], 'style'); return v === undefined ? '' : v; },
      function (v) { write(splitDecls(String(v))); });
    accessor(api, 'length', function () { return read().length; });
    return new Proxy(api, {
      get: function (t, p) {
        if (typeof p !== 'string' || p in t) return Reflect.get(t, p);
        if (/^\d+$/.test(p)) return t.item(+p);
        return t.getPropertyValue(kebab(p));
      },
      set: function (t, p, v) {
        if (typeof p !== 'string' || p in t) return Reflect.set(t, p, v);
        t.setProperty(kebab(p), v);
        return true;
      }
    });
  }
  accessor(EP, 'style', function () { return styleDecl(this); },
    function (v) { styleDecl(this).cssText = String(v); });

  // Geometry: answered from a synchronous raikiri relayout of the current DOM (dom.rs).
  function rectOf(el) {
    var r = N.rect(el[IDX]);
    var x = r.length ? r[0] : 0, y = r.length ? r[1] : 0, w = r.length ? r[2] : 0, h = r.length ? r[3] : 0;
    return { x: x, y: y, width: w, height: h, left: x, top: y, right: x + w, bottom: y + h,
      toJSON: function () { return { x: x, y: y, width: w, height: h, left: x, top: y, right: x + w, bottom: y + h }; } };
  }
  g.DOMRect = function DOMRect(x, y, w, h) {
    this.x = this.left = x || 0; this.y = this.top = y || 0; this.width = w || 0; this.height = h || 0;
    this.right = this.x + this.width; this.bottom = this.y + this.height;
  };
  EP.getBoundingClientRect = function () { return rectOf(this); };
  EP.getClientRects = function () { var r = N.rect(this[IDX]); return r.length ? [rectOf(this)] : []; };
  accessor(EP, 'offsetWidth', function () { return Math.round(rectOf(this).width); });
  accessor(EP, 'offsetHeight', function () { return Math.round(rectOf(this).height); });
  accessor(EP, 'offsetLeft', function () {
    var p = this.offsetParent;
    return Math.round(rectOf(this).left - (p ? rectOf(p).left : 0));
  });
  accessor(EP, 'offsetTop', function () {
    var p = this.offsetParent;
    return Math.round(rectOf(this).top - (p ? rectOf(p).top : 0));
  });
  accessor(EP, 'offsetParent', function () {
    for (var e = this.parentElement; e; e = e.parentElement) {
      var pos = e.style.position;
      if (pos && pos !== 'static') return e;
      if (e.tagName === 'BODY') return e;
    }
    return null;
  });
  accessor(EP, 'clientWidth', function () { return Math.round(rectOf(this).width); });
  accessor(EP, 'clientHeight', function () { return Math.round(rectOf(this).height); });
  accessor(EP, 'scrollWidth', function () { return Math.round(rectOf(this).width); });
  accessor(EP, 'scrollHeight', function () { return Math.round(rectOf(this).height); });
  accessor(EP, 'clientTop', function () { return 0; });
  accessor(EP, 'clientLeft', function () { return 0; });
  EP.scrollTop = 0;
  EP.scrollLeft = 0;
  EP.scrollIntoView = function () {};
  EP.focus = function () {};
  EP.blur = function () {};
  EP.click = function () { dispatch(this, new Event('click', { bubbles: true, cancelable: true })); };

  function HTMLElement() { throw new TypeError('Illegal constructor'); }
  HTMLElement.prototype = Object.create(EP);
  accessor(HTMLElement.prototype, 'content', function () {
    var c = N.templateContent(this[IDX]);
    return c >= 0 ? wrap(c) : undefined;
  });
  // <canvas> has no backing store in this spike: getContext returns null.
  HTMLElement.prototype.getContext = function () { return null; };

  // ------------------------------------------------------- Document(Fragment)
  function DocumentFragment() { throw new TypeError('Illegal constructor'); }
  DocumentFragment.prototype = Object.create(NP);
  parentNodeMixin(DocumentFragment.prototype);
  DocumentFragment.prototype.getElementById = function (id) { return this.querySelector('#' + cssEscape(id)); };

  function Document() { throw new TypeError('Illegal constructor'); }
  var DP = Document.prototype = Object.create(NP);
  parentNodeMixin(DP);
  accessor(DP, 'documentElement', function () {
    var c = N.children(this[IDX]).filter(function (i) { return N.kind(i) === 1; });
    return c.length ? wrap(c[0]) : null;
  });
  function htmlChild(tag) {
    var html = document.documentElement;
    if (!html) return null;
    var c = N.children(html[IDX]);
    for (var k = 0; k < c.length; k++) if (N.kind(c[k]) === 1 && N.tag(c[k]) === tag) return wrap(c[k]);
    return null;
  }
  accessor(DP, 'head', function () { return htmlChild('head'); });
  accessor(DP, 'body', function () { return htmlChild('body'); });
  accessor(DP, 'title', function () { var t = this.querySelector('title'); return t ? t.textContent.trim() : ''; },
    function (v) {
      var t = this.querySelector('title');
      if (!t) { var h = this.head; if (!h) return; t = this.createElement('title'); h.appendChild(t); }
      t.textContent = String(v);
    });
  var readyState = 'loading';
  accessor(DP, 'readyState', function () { return readyState; });
  accessor(DP, 'defaultView', function () { return g; });
  accessor(DP, 'currentScript', function () { return null; });
  DP.getElementById = function (id) { return wrap(N.byId(this[IDX], String(id))); };
  DP.getElementsByName = function (name) { return this.querySelectorAll('[name="' + String(name).replace(/"/g, '\\"') + '"]'); };
  DP.createElement = function (tag) {
    var i = N.create(String(tag).toLowerCase());
    if (i < 0) throw new g.DOMException(N.lastError(), 'InvalidCharacterError');
    return wrap(i);
  };
  DP.createElementNS = function (ns, qname) {
    var local = String(qname).split(':').pop();
    var i = ns === null || ns === undefined || ns === HTML_NS ? N.create(local.toLowerCase()) : N.createNS(String(ns), local);
    if (i < 0) throw new g.DOMException(N.lastError(), 'InvalidCharacterError');
    return wrap(i);
  };
  DP.createTextNode = function (data) { return wrap(N.text(String(data))); };
  DP.createComment = function (data) { return wrap(N.comment(String(data))); };
  DP.createDocumentFragment = function () { return wrap(N.fragment()); };
  DP.importNode = function (node, deep) { return node.cloneNode(deep); };
  DP.adoptNode = function (node) { return node; };
  DP.hasFocus = function () { return false; };
  DP.write = DP.writeln = function () { reportError(new Error('document.write is not supported'), 'document.write'); };
  accessor(DP, 'fonts', function () { return { ready: Promise.resolve(), check: function () { return true; }, load: function () { return Promise.resolve([]); } }; });

  var document = wrap(N.root());
  g.Node = Node; g.Element = Element; g.HTMLElement = HTMLElement; g.Text = Text; g.Comment = Comment;
  g.CharacterData = CharacterData; g.Document = Document; g.DocumentFragment = DocumentFragment;
  g.document = document;
  g.window = g; g.self = g;

  // ------------------------------------------------------------ console
  function fmt(a) {
    if (typeof a === 'string') return a;
    if (a instanceof Error) return (a.name || 'Error') + ': ' + a.message;
    try { var s = JSON.stringify(a); return s === undefined ? String(a) : s; } catch (e) { return String(a); }
  }
  function emit(level) {
    return function () { N.log(level, Array.prototype.map.call(arguments, fmt).join(' ')); };
  }
  // phase5_js shims.js routes its own console through this sink when it is loaded.
  g.__host_log = function (level, text) { N.log(String(level), String(text)); };
  g.console = { log: emit('log'), info: emit('info'), warn: emit('warn'), error: emit('error'), debug: emit('debug'),
    trace: emit('debug'), dir: emit('log'), table: emit('log'), group: emit('log'), groupEnd: function () {},
    assert: function (c) { if (!c) N.log('error', 'Assertion failed: ' + Array.prototype.slice.call(arguments, 1).map(fmt).join(' ')); },
    time: function () {}, timeEnd: function () {}, count: function () {} };
  function reportError(e, where) {
    var msg = e && typeof e === 'object' ? (e.name || 'Error') + ': ' + e.message : 'thrown: ' + String(e);
    var stack = e && e.stack ? String(e.stack).split('\n').slice(0, 2).join(' | ') : '';
    N.log('uncaught', (where ? where + ': ' : '') + msg + (stack ? ' [' + stack.trim() + ']' : ''));
  }

  // ------------------------------------------------------- window and timers
  var vp = N.viewport();
  g.innerWidth = vp[0]; g.innerHeight = vp[1]; g.outerWidth = vp[0]; g.outerHeight = vp[1];
  g.devicePixelRatio = 1; g.scrollX = g.scrollY = g.pageXOffset = g.pageYOffset = 0;
  g.scrollTo = g.scroll = g.scrollBy = function () {};
  g.navigator = { userAgent: 'raikiri-spike', language: 'en-US', languages: ['en-US'] };
  g.location = { href: 'about:blank', protocol: 'about:', host: '', hostname: '', pathname: 'blank', search: '', hash: '' };
  g.matchMedia = function (q) {
    var m = /print/.test(String(q));
    return { matches: m, media: String(q), addListener: function () {}, removeListener: function () {},
      addEventListener: function () {}, removeEventListener: function () {} };
  };
  g.getComputedStyle = function (el) {
    // Inline declarations only: the cascade is not exposed to script in this spike.
    var s = el.style;
    return new Proxy({}, { get: function (t, p) {
      if (p === 'getPropertyValue') return function (n) { return s.getPropertyValue(n); };
      return typeof p === 'string' ? s[p] : undefined;
    } });
  };
  g.addEventListener = function (type, fn) { addListener(g, type, fn); };
  g.removeEventListener = function (type, fn) { removeListener(g, type, fn); };
  g.dispatchEvent = function (event) { return dispatch(g, event); };
  var vt = 0;
  var seq = 0;
  var timers = [];
  var timerCallbacks = 0;
  function addTimer(fn, delay, args, repeat) {
    if (typeof fn !== 'function') { var src = String(fn); fn = function () { (0, eval)(src); }; }
    var id = ++seq;
    delay = Math.max(0, Number(delay) || 0);
    timers.push({ id: id, due: vt + delay, seq: id, fn: fn, args: args, repeat: repeat ? Math.max(1, delay) : 0 });
    return id;
  }
  g.setTimeout = function (fn, delay) { return addTimer(fn, delay, Array.prototype.slice.call(arguments, 2), false); };
  g.setInterval = function (fn, delay) { return addTimer(fn, delay, Array.prototype.slice.call(arguments, 2), true); };
  g.clearTimeout = g.clearInterval = function (id) { timers = timers.filter(function (t) { return t.id !== id; }); };
  g.requestAnimationFrame = function (fn) { return addTimer(function () { fn(vt); }, 16, [], false); };
  g.cancelAnimationFrame = g.clearTimeout;
  g.setImmediate = function (fn) { return addTimer(fn, 0, Array.prototype.slice.call(arguments, 1), false); };
  if (typeof g.queueMicrotask !== 'function') {
    g.queueMicrotask = function (fn) { Promise.resolve().then(fn); };
  }
  var perf = {};
  try { Object.defineProperty(perf, 'now', { value: function () { return vt; }, enumerable: true }); } catch (e) {}
  try { Object.defineProperty(g, 'performance', { value: perf, writable: true, configurable: true }); } catch (e) {
    try { Object.defineProperty(g.performance, 'now', { value: function () { return vt; }, configurable: true }); } catch (e2) {}
  }

  // Host entry points (called from Rust after the page scripts).
  g.__rk = {
    setReady: function (s) { readyState = s; },
    fire: function (type) {
      var ev = new Event(type, { bubbles: false });
      if (type === 'DOMContentLoaded') {
        ev.bubbles = true;
        ev.target = document;
        callListeners(document, ev);
        if (!ev._stop) callListeners(g, ev);
      } else if (type === 'load') {
        ev.target = document;
        callListeners(g, ev);
        var body = document.body;
        var attr = body ? body.getAttribute('onload') : null;
        if (attr && typeof g.onload !== 'function') {
          try { (0, eval)(attr); } catch (e) { reportError(e, 'body onload'); }
        }
      }
    },
    // Runs the earliest timer on the virtual clock. Returns false when none is left or a
    // budget is hit; the host drains promise jobs between calls.
    runTimer: function (maxCallbacks, maxVirtualMs) {
      if (!timers.length) return false;
      if (timerCallbacks >= maxCallbacks) {
        reportError(new Error('timer callback budget reached with ' + timers.length + ' timers pending'), 'timers');
        timers = [];
        return false;
      }
      var best = 0;
      for (var k = 1; k < timers.length; k++) {
        var a = timers[k], b = timers[best];
        if (a.due < b.due || (a.due === b.due && a.seq < b.seq)) best = k;
      }
      var t = timers[best];
      if (t.due > maxVirtualMs) {
        reportError(new Error('virtual time budget reached with ' + timers.length + ' timers pending'), 'timers');
        timers = [];
        return false;
      }
      vt = Math.max(vt, t.due);
      if (t.repeat) { t.due += t.repeat; t.seq = ++seq; } else timers.splice(best, 1);
      timerCallbacks++;
      try { t.fn.apply(g, t.args); } catch (e) { reportError(e, 'timer'); }
      return true;
    },
    pending: function () { return timers.length; },
    reportError: reportError
  };
})(globalThis);
