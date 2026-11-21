// Host-API shims for the phase 5 JS runtime bench.
// Evaluated as a classic script before any library bundle, identically in
// rquickjs (QuickJS-NG), boa_engine and Node. Configuration comes from
// globalThis.__P5_SHIM_CONFIG = { disable: [name...], force: [name...], seed, epochMs }.
//  - "deterministic" shims (timers, requestAnimationFrame, console, performance_now,
//    Math_random, Date) always replace the native API, also in Node, so that every
//    engine sees the same virtual clock, PRNG and diagnostics channel;
//  - "polyfill" shims (queueMicrotask, atob_btoa, TextEncoder_Decoder, URL,
//    structuredClone, Intl) are installed only when the engine lacks the API,
//    unless listed in `force`.
// `disable` removes a shim completely (ablation runs). Every shim counts its calls
// in __p5.usage so the report can say which library touched which shim.
(function (g) {
  'use strict';
  var cfg = g.__P5_SHIM_CONFIG || {};
  var disabled = {};
  var forced = {};
  (cfg.disable || []).forEach(function (n) { disabled[n] = true; });
  (cfg.force || []).forEach(function (n) { forced[n] = true; });
  var SEED = cfg.seed === undefined ? 0x5eed1234 : cfg.seed >>> 0;
  var EPOCH = cfg.epochMs === undefined ? 1767225600000 : cfg.epochMs; // 2026-01-01T00:00:00Z

  var LIMITS = {
    maxPendingTimers: cfg.maxPendingTimers || 10000,
    maxTimerCallbacks: cfg.maxTimerCallbacks || 100000,
    maxVirtualMs: cfg.maxVirtualMs || 3600000,
    maxDiagnostics: cfg.maxDiagnostics || 1000,
    maxDiagnosticChars: cfg.maxDiagnosticChars || 2000
  };

  var usage = Object.create(null);
  var installed = Object.create(null);
  var nativePresent = Object.create(null);
  function use(name) { usage[name] = (usage[name] || 0) + 1; }
  function active(name) { return !disabled[name]; }
  function needPolyfill(name, present) {
    nativePresent[name] = !!present;
    if (disabled[name]) return false;
    return !present || !!forced[name];
  }
  function define(obj, key, value) {
    Object.defineProperty(obj, key, { value: value, writable: true, configurable: true, enumerable: false });
  }

  // ---------------------------------------------------------------- virtual clock
  // vt advances only when a timer fires; every clock read adds 1 microsecond so busy-wait
  // loops on Date.now()/performance.now() terminate, deterministically.
  var clock = { vt: 0, perfCalls: 0 };
  function clockNow() { clock.perfCalls++; return clock.vt + clock.perfCalls * 0.001; }

  // ---------------------------------------------------------------- Math_random (sfc32)
  var rng = { a: 0, b: 0, c: 0, d: 0 };
  function seedRng(seed) {
    rng.a = 0x9e3779b9; rng.b = 0x243f6a88; rng.c = 0xb7e15162; rng.d = seed >>> 0;
    for (var i = 0; i < 15; i++) nextRandom();
  }
  function nextRandom() {
    var t = (rng.a + rng.b | 0) + rng.d | 0;
    rng.d = rng.d + 1 | 0;
    rng.a = rng.b ^ rng.b >>> 9;
    rng.b = rng.c + (rng.c << 3) | 0;
    rng.c = rng.c << 21 | rng.c >>> 11;
    rng.c = rng.c + t | 0;
    return (t >>> 0) / 4294967296;
  }
  seedRng(SEED);
  nativePresent.Math_random = true;
  if (active('Math_random')) {
    define(Math, 'random', function random() { use('Math_random'); return nextRandom(); });
    installed.Math_random = true;
  }

  // ---------------------------------------------------------------- performance_now
  nativePresent.performance_now = typeof g.performance === 'object' && g.performance !== null && typeof g.performance.now === 'function';
  if (active('performance_now')) {
    var perf = nativePresent.performance_now ? g.performance : {};
    var perfNow = function now() { use('performance_now'); return clockNow(); };
    try { define(perf, 'now', perfNow); } catch (e) { perf = { now: perfNow }; }
    if (typeof perf.timeOrigin !== 'number') { try { define(perf, 'timeOrigin', EPOCH); } catch (e) { /* read-only */ } }
    if (!nativePresent.performance_now || g.performance !== perf) define(g, 'performance', perf);
    installed.performance_now = true;
  }

  // ---------------------------------------------------------------- Date (fixed epoch + virtual time)
  nativePresent.Date = typeof g.Date === 'function';
  if (active('Date')) {
    var NativeDate = g.Date;
    var dateNow = function () { return EPOCH + Math.floor(clockNow()); };
    var P5Date = function Date(a, b, c, d, e, f, h) {
      var n = arguments.length;
      if (!new.target) { use('Date'); return new NativeDate(dateNow()).toString(); }
      var args;
      if (n === 0) { use('Date'); args = [dateNow()]; }
      else args = Array.prototype.slice.call(arguments);
      return Reflect.construct(NativeDate, args, new.target);
    };
    P5Date.prototype = NativeDate.prototype;
    define(P5Date, 'now', function now() { use('Date'); return dateNow(); });
    define(P5Date, 'parse', NativeDate.parse);
    define(P5Date, 'UTC', NativeDate.UTC);
    Object.defineProperty(P5Date, 'length', { value: 7, configurable: true });
    define(NativeDate.prototype, 'constructor', P5Date);
    define(g, 'Date', P5Date);
    installed.Date = true;
  }

  // ---------------------------------------------------------------- console -> diagnostics
  var diagnostics = [];
  var diagDropped = 0;
  function fmt(v, depth) {
    if (typeof v === 'string') return v;
    if (v instanceof Error) return (v.name || 'Error') + ': ' + v.message;
    if (typeof v === 'function') return '[function ' + (v.name || 'anonymous') + ']';
    if (typeof v === 'symbol' || typeof v === 'bigint') return String(v);
    if (v === null || typeof v !== 'object') return String(v);
    if ((depth || 0) > 2) return '[object]';
    try {
      var seen = [];
      return JSON.stringify(v, function (k, x) {
        if (typeof x === 'object' && x !== null) { if (seen.indexOf(x) >= 0) return '[circular]'; seen.push(x); }
        if (typeof x === 'bigint') return String(x);
        if (typeof x === 'function') return '[function]';
        return x;
      });
    } catch (e) { return '[unserializable]'; }
  }
  function emit(level, args) {
    use('console');
    var text = Array.prototype.map.call(args, function (a) { return fmt(a, 0); }).join(' ');
    if (text.length > LIMITS.maxDiagnosticChars) text = text.slice(0, LIMITS.maxDiagnosticChars) + '...';
    if (diagnostics.length >= LIMITS.maxDiagnostics) { diagDropped++; return; }
    diagnostics.push({ level: level, text: text, vt: clock.vt });
    if (typeof g.__host_log === 'function') { try { g.__host_log(level, text); } catch (e) { /* host refused */ } }
  }
  nativePresent.console = typeof g.console === 'object' && g.console !== null;
  if (active('console')) {
    var counters = Object.create(null);
    var timersC = Object.create(null);
    var con = {};
    ['log', 'info', 'debug', 'warn', 'error', 'trace', 'dir', 'dirxml', 'table'].forEach(function (lvl) {
      con[lvl] = function () { emit(lvl === 'dir' || lvl === 'dirxml' || lvl === 'table' ? 'log' : lvl, arguments); };
    });
    con.assert = function (cond) { if (!cond) emit('error', ['Assertion failed:'].concat(Array.prototype.slice.call(arguments, 1))); };
    con.count = function (l) { l = l === undefined ? 'default' : String(l); counters[l] = (counters[l] || 0) + 1; emit('log', [l + ': ' + counters[l]]); };
    con.countReset = function (l) { counters[l === undefined ? 'default' : String(l)] = 0; };
    con.group = con.groupCollapsed = function () { if (arguments.length) emit('log', arguments); };
    con.groupEnd = function () {};
    con.time = function (l) { timersC[l === undefined ? 'default' : String(l)] = clock.vt; };
    con.timeLog = con.timeEnd = function (l) { l = l === undefined ? 'default' : String(l); emit('log', [l + ': ' + (clock.vt - (timersC[l] || 0)) + 'ms']); };
    con.clear = function () {};
    define(g, 'console', con);
    installed.console = true;
  }

  // ---------------------------------------------------------------- timers (virtual time)
  var timers = [];
  var timerSeq = 0;
  var timerIds = 0;
  var timerCallbacks = 0;
  function addTimer(fn, ms, args, interval, kind) {
    if (typeof fn !== 'function') throw new TypeError('P5: ' + kind + ' requires a function (string callbacks are not supported)');
    if (timers.length >= LIMITS.maxPendingTimers) throw new RangeError('P5TimerBudget: more than ' + LIMITS.maxPendingTimers + ' pending timers');
    ms = Number(ms); if (!(ms >= 0)) ms = 0;
    var id = ++timerIds;
    timers.push({ id: id, at: clock.vt + ms, seq: ++timerSeq, fn: fn, args: args, interval: interval ? Math.max(ms, 1) : -1 });
    return id;
  }
  function clearTimer(id) {
    for (var i = 0; i < timers.length; i++) if (timers[i].id === id) { timers.splice(i, 1); return; }
  }
  nativePresent.timers = typeof g.setTimeout === 'function';
  if (active('timers')) {
    define(g, 'setTimeout', function setTimeout(fn, ms) { use('timers'); return addTimer(fn, ms, Array.prototype.slice.call(arguments, 2), false, 'setTimeout'); });
    define(g, 'setInterval', function setInterval(fn, ms) { use('timers'); return addTimer(fn, ms, Array.prototype.slice.call(arguments, 2), true, 'setInterval'); });
    define(g, 'clearTimeout', function clearTimeout(id) { use('timers'); clearTimer(id); });
    define(g, 'clearInterval', function clearInterval(id) { use('timers'); clearTimer(id); });
    define(g, 'setImmediate', function setImmediate(fn) { use('timers'); return addTimer(fn, 0, Array.prototype.slice.call(arguments, 1), false, 'setImmediate'); });
    define(g, 'clearImmediate', function clearImmediate(id) { use('timers'); clearTimer(id); });
    installed.timers = true;
  }
  nativePresent.requestAnimationFrame = typeof g.requestAnimationFrame === 'function';
  if (active('requestAnimationFrame')) {
    define(g, 'requestAnimationFrame', function requestAnimationFrame(fn) {
      use('requestAnimationFrame');
      var next = (Math.floor(clock.vt / 16) + 1) * 16;
      return addTimer(function () { fn(clock.vt); }, next - clock.vt, [], false, 'requestAnimationFrame');
    });
    define(g, 'cancelAnimationFrame', function cancelAnimationFrame(id) { use('requestAnimationFrame'); clearTimer(id); });
    installed.requestAnimationFrame = true;
  }
  function tick() {
    if (!timers.length) return false;
    var best = 0;
    for (var i = 1; i < timers.length; i++) {
      var t = timers[i], b = timers[best];
      if (t.at < b.at || (t.at === b.at && t.seq < b.seq)) best = i;
    }
    var tm = timers[best];
    if (tm.at > LIMITS.maxVirtualMs) throw new RangeError('P5TimerBudget: virtual time limit ' + LIMITS.maxVirtualMs + ' ms exceeded');
    if (++timerCallbacks > LIMITS.maxTimerCallbacks) throw new RangeError('P5TimerBudget: more than ' + LIMITS.maxTimerCallbacks + ' timer callbacks');
    if (tm.at > clock.vt) clock.vt = tm.at;
    if (tm.interval >= 0) { tm.at = clock.vt + tm.interval; tm.seq = ++timerSeq; } else timers.splice(best, 1);
    try { tm.fn.apply(undefined, tm.args); }
    catch (e) {
      // Browser semantics: an exception in a timer callback is reported, not fatal.
      // Budget violations stay fatal.
      if (e && typeof e.message === 'string' && e.message.indexOf('P5TimerBudget') === 0) throw e;
      emit('error', ['Uncaught (in timer callback)', e]);
    }
    return true;
  }

  // ---------------------------------------------------------------- queueMicrotask
  if (needPolyfill('queueMicrotask', typeof g.queueMicrotask === 'function')) {
    define(g, 'queueMicrotask', function queueMicrotask(fn) {
      use('queueMicrotask');
      if (typeof fn !== 'function') throw new TypeError('queueMicrotask requires a function');
      Promise.resolve().then(function () { fn(); });
    });
    installed.queueMicrotask = true;
  }

  // ---------------------------------------------------------------- atob / btoa
  var B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  function domError(name, msg) { var e = new Error(msg); e.name = name; return e; }
  if (needPolyfill('atob_btoa', typeof g.atob === 'function' && typeof g.btoa === 'function')) {
    define(g, 'btoa', function btoa(s) {
      use('atob_btoa');
      s = String(s);
      var out = '';
      for (var i = 0; i < s.length; i += 3) {
        var a = s.charCodeAt(i), b = s.charCodeAt(i + 1), c = s.charCodeAt(i + 2);
        if (a > 255 || b > 255 || c > 255) throw domError('InvalidCharacterError', 'btoa: character outside Latin1');
        var n = (a << 16) | ((b || 0) << 8) | (c || 0);
        out += B64.charAt(n >> 18 & 63) + B64.charAt(n >> 12 & 63) +
          (i + 1 < s.length ? B64.charAt(n >> 6 & 63) : '=') + (i + 2 < s.length ? B64.charAt(n & 63) : '=');
      }
      return out;
    });
    define(g, 'atob', function atob(s) {
      use('atob_btoa');
      s = String(s).replace(/[\t\n\f\r ]/g, '');
      if (s.length % 4 === 0) s = s.replace(/==?$/, '');
      if (s.length % 4 === 1 || /[^A-Za-z0-9+/]/.test(s)) throw domError('InvalidCharacterError', 'atob: invalid base64');
      var out = '', buf = 0, bits = 0;
      for (var i = 0; i < s.length; i++) {
        buf = (buf << 6) | B64.indexOf(s.charAt(i)); bits += 6;
        if (bits >= 8) { bits -= 8; out += String.fromCharCode((buf >> bits) & 255); }
      }
      return out;
    });
    installed.atob_btoa = true;
  }

  // ---------------------------------------------------------------- TextEncoder / TextDecoder (UTF-8)
  if (needPolyfill('TextEncoder_Decoder', typeof g.TextEncoder === 'function' && typeof g.TextDecoder === 'function')) {
    var TE = function TextEncoder() { if (!new.target) throw new TypeError("Constructor TextEncoder requires 'new'"); use('TextEncoder_Decoder'); };
    define(TE.prototype, 'encode', function encode(input) {
      use('TextEncoder_Decoder');
      var s = input === undefined ? '' : String(input);
      var out = [];
      for (var i = 0; i < s.length; i++) {
        var c = s.charCodeAt(i);
        if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
          var d = s.charCodeAt(i + 1);
          if (d >= 0xdc00 && d <= 0xdfff) { c = 0x10000 + ((c - 0xd800) << 10) + (d - 0xdc00); i++; } else c = 0xfffd;
        } else if (c >= 0xd800 && c <= 0xdfff) c = 0xfffd;
        if (c < 0x80) out.push(c);
        else if (c < 0x800) out.push(0xc0 | c >> 6, 0x80 | c & 63);
        else if (c < 0x10000) out.push(0xe0 | c >> 12, 0x80 | c >> 6 & 63, 0x80 | c & 63);
        else out.push(0xf0 | c >> 18, 0x80 | c >> 12 & 63, 0x80 | c >> 6 & 63, 0x80 | c & 63);
      }
      return new Uint8Array(out);
    });
    Object.defineProperty(TE.prototype, 'encoding', { get: function () { return 'utf-8'; }, configurable: true });
    var TD = function TextDecoder(label, opts) {
      if (!new.target) throw new TypeError("Constructor TextDecoder requires 'new'");
      use('TextEncoder_Decoder');
      label = label === undefined ? 'utf-8' : String(label).trim().toLowerCase();
      if (label !== 'utf-8' && label !== 'utf8' && label !== 'unicode-1-1-utf-8') throw new RangeError('P5 TextDecoder supports utf-8 only, got ' + label);
      this.fatal = !!(opts && opts.fatal);
      this.ignoreBOM = !!(opts && opts.ignoreBOM);
    };
    define(TD.prototype, 'decode', function decode(input) {
      use('TextEncoder_Decoder');
      if (input === undefined) return '';
      var b = input instanceof ArrayBuffer ? new Uint8Array(input)
        : ArrayBuffer.isView(input) ? new Uint8Array(input.buffer, input.byteOffset, input.byteLength) : null;
      if (!b) throw new TypeError('TextDecoder.decode: expected a BufferSource');
      var out = '', i = 0, self = this;
      if (!this.ignoreBOM && b.length >= 3 && b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) i = 3;
      function bad() { if (self.fatal) throw new TypeError('TextDecoder: invalid utf-8'); return 0xfffd; }
      while (i < b.length) {
        var c = b[i], cp, need, min;
        if (c < 0x80) { cp = c; need = 0; }
        else if (c >= 0xc2 && c <= 0xdf) { cp = c & 31; need = 1; min = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { cp = c & 15; need = 2; min = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { cp = c & 7; need = 3; min = 0x10000; }
        else { out += String.fromCharCode(bad()); i++; continue; }
        var j = 1;
        for (; j <= need; j++) {
          var x = b[i + j];
          if (x === undefined || (x & 0xc0) !== 0x80) break;
          cp = (cp << 6) | (x & 63);
        }
        if (j <= need || (need && (cp < min || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)))) { out += String.fromCharCode(bad()); i += Math.max(1, j); continue; }
        i += need + 1;
        out += String.fromCodePoint(cp);
      }
      return out;
    });
    Object.defineProperty(TD.prototype, 'encoding', { get: function () { return 'utf-8'; }, configurable: true });
    define(g, 'TextEncoder', TE);
    define(g, 'TextDecoder', TD);
    installed.TextEncoder_Decoder = true;
  }

  // ---------------------------------------------------------------- URL / URLSearchParams (special schemes subset)
  if (needPolyfill('URL', typeof g.URL === 'function' && typeof g.URLSearchParams === 'function')) {
    var USP = function URLSearchParams(init) {
      if (!new.target) throw new TypeError("Constructor URLSearchParams requires 'new'");
      use('URL');
      this._list = [];
      this._url = null;
      if (typeof init === 'string') this._parse(init);
      else if (init && typeof init === 'object') {
        if (typeof init[Symbol.iterator] === 'function') { for (var p of init) this._list.push([String(p[0]), String(p[1])]); }
        else Object.keys(init).forEach(function (k) { this._list.push([k, String(init[k])]); }, this);
      }
    };
    var dec = function (s) { try { return decodeURIComponent(s.replace(/\+/g, ' ')); } catch (e) { return s; } };
    var enc = function (s) { return encodeURIComponent(s).replace(/%20/g, '+').replace(/[!'()~]/g, function (c) { return '%' + c.charCodeAt(0).toString(16).toUpperCase(); }); };
    USP.prototype._parse = function (s) {
      this._list = [];
      if (s.charAt(0) === '?') s = s.slice(1);
      s.split('&').forEach(function (kv) { if (!kv) return; var i = kv.indexOf('='); this._list.push(i < 0 ? [dec(kv), ''] : [dec(kv.slice(0, i)), dec(kv.slice(i + 1))]); }, this);
    };
    USP.prototype._update = function () { if (this._url) { var q = this.toString(); this._url._query = q ? '?' + q : ''; } };
    USP.prototype.append = function (k, v) { this._list.push([String(k), String(v)]); this._update(); };
    USP.prototype['delete'] = function (k) { k = String(k); this._list = this._list.filter(function (p) { return p[0] !== k; }); this._update(); };
    USP.prototype.get = function (k) { k = String(k); for (var i = 0; i < this._list.length; i++) if (this._list[i][0] === k) return this._list[i][1]; return null; };
    USP.prototype.getAll = function (k) { k = String(k); return this._list.filter(function (p) { return p[0] === k; }).map(function (p) { return p[1]; }); };
    USP.prototype.has = function (k) { return this.get(k) !== null; };
    USP.prototype.set = function (k, v) {
      k = String(k); v = String(v); var found = false;
      this._list = this._list.filter(function (p) { if (p[0] !== k) return true; if (found) return false; found = true; p[1] = v; return true; });
      if (!found) this._list.push([k, v]); this._update();
    };
    USP.prototype.sort = function () { this._list.sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; }); this._update(); };
    USP.prototype.forEach = function (cb, thisArg) { this._list.forEach(function (p) { cb.call(thisArg, p[1], p[0], this); }, this); };
    USP.prototype.keys = function () { return this._list.map(function (p) { return p[0]; })[Symbol.iterator](); };
    USP.prototype.values = function () { return this._list.map(function (p) { return p[1]; })[Symbol.iterator](); };
    USP.prototype.entries = function () { return this._list.map(function (p) { return [p[0], p[1]]; })[Symbol.iterator](); };
    USP.prototype[Symbol.iterator] = USP.prototype.entries;
    USP.prototype.toString = function () { return this._list.map(function (p) { return enc(p[0]) + '=' + enc(p[1]); }).join('&'); };
    Object.defineProperty(USP.prototype, 'size', { get: function () { return this._list.length; }, configurable: true });

    var DEFAULT_PORTS = { 'http:': '80', 'https:': '443', 'ws:': '80', 'wss:': '443', 'ftp:': '21' };
    var RE = /^([a-zA-Z][a-zA-Z0-9+.\-]*:)(\/\/(?:([^:@\/?#]*)(?::([^@\/?#]*))?@)?(\[[^\]]*\]|[^:\/?#]*)(?::(\d*))?)?([^?#]*)(\?[^#]*)?(#.*)?$/;
    var normPath = function (p) {
      var out = [];
      p.split('/').forEach(function (seg, i, arr) {
        if (seg === '..') { if (out.length > 1) out.pop(); if (i === arr.length - 1) out.push(''); }
        else if (seg === '.') { if (i === arr.length - 1) out.push(''); }
        else out.push(seg);
      });
      var r = out.join('/');
      return r.charAt(0) === '/' ? r : '/' + r;
    };
    var U = function URL(url, base) {
      if (!new.target) throw new TypeError("Constructor URL requires 'new'");
      use('URL');
      url = String(url).trim();
      var m = RE.exec(url);
      if (!m) {
        if (base === undefined) throw new TypeError('Invalid URL: ' + url);
        var b = base instanceof U ? base : new U(String(base));
        var r = Object.create(U.prototype);
        r._protocol = b._protocol; r._username = b._username; r._password = b._password; r._hostname = b._hostname; r._port = b._port;
        var hm = /^([^?#]*)(\?[^#]*)?(#.*)?$/.exec(url);
        var path = hm[1], q = hm[2], h = hm[3];
        if (url.slice(0, 2) === '//') return new U(b._protocol + url);
        if (path === '') { r._path = b._path; r._query = q !== undefined ? q : b._query; }
        else { r._path = normPath(path.charAt(0) === '/' ? path : b._path.replace(/[^\/]*$/, '') + path); r._query = q || ''; }
        r._hash = h || '';
        r._sp = null;
        return r;
      }
      this._protocol = m[1].toLowerCase();
      this._username = m[3] || ''; this._password = m[4] || '';
      this._hostname = (m[5] || '').toLowerCase();
      this._port = m[6] && m[6] !== DEFAULT_PORTS[this._protocol] ? m[6] : '';
      this._path = m[2] !== undefined ? normPath(m[7] || '/') : (m[7] || '');
      this._query = m[8] && m[8] !== '?' ? m[8] : '';
      this._hash = m[9] && m[9] !== '#' ? m[9] : '';
      this._sp = null;
    };
    var acc = function (name, get, set) { Object.defineProperty(U.prototype, name, { get: get, set: set, configurable: true, enumerable: true }); };
    acc('protocol', function () { return this._protocol; }, function (v) { this._protocol = String(v).replace(/:?$/, ':').toLowerCase(); });
    acc('username', function () { return this._username; }, function (v) { this._username = String(v); });
    acc('password', function () { return this._password; }, function (v) { this._password = String(v); });
    acc('hostname', function () { return this._hostname; }, function (v) { this._hostname = String(v).toLowerCase(); });
    acc('port', function () { return this._port; }, function (v) { v = String(v); this._port = v === DEFAULT_PORTS[this._protocol] ? '' : v; });
    acc('host', function () { return this._hostname + (this._port ? ':' + this._port : ''); }, function (v) { var p = String(v).split(':'); this._hostname = p[0].toLowerCase(); this._port = p[1] || ''; });
    acc('origin', function () { return DEFAULT_PORTS[this._protocol] !== undefined || this._protocol === 'file:' ? this._protocol + '//' + this.host : 'null'; });
    acc('pathname', function () { return this._path; }, function (v) { this._path = normPath(String(v)); });
    acc('search', function () { return this._query; }, function (v) { v = String(v); this._query = v && v !== '?' ? (v.charAt(0) === '?' ? v : '?' + v) : ''; if (this._sp) this._sp._parse(this._query); });
    acc('hash', function () { return this._hash; }, function (v) { v = String(v); this._hash = v && v !== '#' ? (v.charAt(0) === '#' ? v : '#' + v) : ''; });
    acc('searchParams', function () { if (!this._sp) { this._sp = new USP(this._query); this._sp._url = this; } return this._sp; });
    acc('href', function () {
      var auth = this._username ? this._username + (this._password ? ':' + this._password : '') + '@' : '';
      var special = this._hostname !== '' || DEFAULT_PORTS[this._protocol] !== undefined || this._protocol === 'file:';
      return this._protocol + (special ? '//' + auth + this.host : '') + this._path + this._query + this._hash;
    }, function (v) { var n = new U(String(v)); for (var k in n) if (Object.prototype.hasOwnProperty.call(n, k)) this[k] = n[k]; });
    U.prototype.toString = function () { return this.href; };
    U.prototype.toJSON = function () { return this.href; };
    define(U, 'canParse', function canParse(u, b) { try { new U(u, b); return true; } catch (e) { return false; } });
    define(g, 'URL', U);
    define(g, 'URLSearchParams', USP);
    installed.URL = true;
  }

  // ---------------------------------------------------------------- structuredClone
  if (needPolyfill('structuredClone', typeof g.structuredClone === 'function')) {
    define(g, 'structuredClone', function structuredClone(value) {
      use('structuredClone');
      var seen = new Map();
      function clone(v) {
        if (v === null || typeof v !== 'object') {
          if (typeof v === 'function' || typeof v === 'symbol') throw domError('DataCloneError', 'structuredClone: ' + typeof v + ' could not be cloned');
          return v;
        }
        if (seen.has(v)) return seen.get(v);
        var out, tag = Object.prototype.toString.call(v);
        if (tag === '[object Date]') out = new Date(v.getTime());
        else if (tag === '[object RegExp]') out = new RegExp(v.source, v.flags);
        else if (tag === '[object Boolean]') out = Object(v.valueOf());
        else if (tag === '[object Number]') out = Object(v.valueOf());
        else if (tag === '[object String]') out = Object(v.valueOf());
        else if (tag === '[object ArrayBuffer]') out = v.slice(0);
        else if (ArrayBuffer.isView(v)) { var ctor = v.constructor; seen.set(v, null); out = tag === '[object DataView]' ? new DataView(clone(v.buffer), v.byteOffset, v.byteLength) : new ctor(clone(v.buffer), v.byteOffset, v.length); }
        else if (tag === '[object Map]') { out = new Map(); seen.set(v, out); v.forEach(function (x, k) { out.set(clone(k), clone(x)); }); return out; }
        else if (tag === '[object Set]') { out = new Set(); seen.set(v, out); v.forEach(function (x) { out.add(clone(x)); }); return out; }
        else if (tag === '[object Error]') { out = new Error(v.message); out.name = v.name; if (v.stack !== undefined) out.stack = String(v.stack); }
        else if (Array.isArray(v)) { out = new Array(v.length); seen.set(v, out); for (var i = 0; i < v.length; i++) if (i in v) out[i] = clone(v[i]); return out; }
        else if (tag === '[object Object]') { out = {}; seen.set(v, out); Object.keys(v).forEach(function (k) { out[k] = clone(v[k]); }); return out; }
        else throw domError('DataCloneError', 'structuredClone: ' + tag + ' could not be cloned');
        seen.set(v, out);
        return out;
      }
      return clone(value);
    });
    installed.structuredClone = true;
  }

  // ---------------------------------------------------------------- Intl (en-US subset)
  if (needPolyfill('Intl', typeof g.Intl === 'object' && g.Intl !== null)) {
    var group3 = function (intStr) { return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, ','); };
    var NF = function NumberFormat(locales, options) {
      if (!(this instanceof NF)) return new NF(locales, options);
      use('Intl');
      var o = options || {};
      this._o = {
        locale: 'en-US', numberingSystem: 'latn', style: o.style || 'decimal',
        notation: o.notation || 'standard', useGrouping: o.useGrouping === undefined ? true : !!o.useGrouping,
        minimumIntegerDigits: o.minimumIntegerDigits || 1
      };
      var pct = this._o.style === 'percent';
      var minF = o.minimumFractionDigits, maxF = o.maximumFractionDigits;
      if (minF === undefined) minF = this._o.style === 'currency' ? 2 : 0;
      if (maxF === undefined) maxF = Math.max(minF, this._o.notation === 'compact' ? 0 : pct ? 0 : this._o.style === 'currency' ? 2 : 3);
      if (maxF < minF) throw new RangeError('maximumFractionDigits value is out of range.');
      this._o.minimumFractionDigits = minF; this._o.maximumFractionDigits = maxF;
      this._o.currency = o.currency; this._o.unit = o.unit;
    };
    NF.prototype.resolvedOptions = function () { var r = {}; for (var k in this._o) if (this._o[k] !== undefined) r[k] = this._o[k]; return r; };
    NF.prototype.format = function (n) {
      use('Intl');
      var o = this._o; n = Number(n);
      if (n !== n) return 'NaN';
      var neg = n < 0 || (n === 0 && 1 / n < 0); var a = Math.abs(n);
      if (a === Infinity) return (neg ? '-' : '') + '∞';
      if (o.style === 'percent') a *= 100;
      var suffix = '';
      if (o.notation === 'scientific' || o.notation === 'engineering') {
        var e = a === 0 ? 0 : Math.floor(Math.log10(a));
        if (o.notation === 'engineering') e -= ((e % 3) + 3) % 3;
        var mant = a / Math.pow(10, e);
        var s = fix(mant, o.minimumFractionDigits, o.maximumFractionDigits);
        if (Number(s) >= (o.notation === 'engineering' ? 1000 : 10)) { e += o.notation === 'engineering' ? 3 : 1; s = fix(a / Math.pow(10, e), o.minimumFractionDigits, o.maximumFractionDigits); }
        return (neg && Number(s) !== 0 ? '-' : neg ? '-' : '') + s + 'E' + e;
      }
      if (o.notation === 'compact') {
        var units = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']];
        for (var i = 0; i < units.length; i++) if (a >= units[i][0]) { a /= units[i][0]; suffix = units[i][1]; break; }
        var c = fix(a, 0, a < 100 && suffix ? 1 : 0);
        return (neg ? '-' : '') + c + suffix;
      }
      var str = fix(a, o.minimumFractionDigits, o.maximumFractionDigits);
      var parts = str.split('.');
      while (parts[0].length < o.minimumIntegerDigits) parts[0] = '0' + parts[0];
      if (o.useGrouping) parts[0] = group3(parts[0]);
      str = parts.join('.');
      if (neg && /[1-9]/.test(str)) str = '-' + str; else if (neg && n !== 0) str = '-' + str;
      if (o.style === 'percent') str += '%';
      if (o.style === 'currency') str = (o.currency === 'USD' ? '$' : (o.currency || '') + ' ') + str;
      return str;
    };
    function fix(a, minF, maxF) {
      var s = a.toFixed(maxF);
      if (maxF > minF && s.indexOf('.') >= 0) {
        s = s.replace(/0+$/, '');
        var frac = s.split('.')[1] || '';
        while (frac.length < minF) frac += '0';
        s = s.split('.')[0] + (frac ? '.' + frac : '');
      }
      return s;
    }
    NF.prototype.formatToParts = function (n) { return [{ type: 'literal', value: this.format(n) }]; };
    NF.supportedLocalesOf = function () { return ['en-US']; };
    var DTF = function DateTimeFormat(locales, options) {
      if (!(this instanceof DTF)) return new DTF(locales, options);
      use('Intl'); this._o = options || {};
    };
    DTF.prototype.format = function (d) {
      use('Intl');
      d = d === undefined ? new Date() : new Date(d);
      var tz = this._o.timeZone === 'UTC';
      var y = tz ? d.getUTCFullYear() : d.getFullYear(), m = (tz ? d.getUTCMonth() : d.getMonth()) + 1, day = tz ? d.getUTCDate() : d.getDate();
      return m + '/' + day + '/' + y;
    };
    DTF.prototype.formatToParts = function (d) { return [{ type: 'literal', value: this.format(d) }]; };
    DTF.prototype.resolvedOptions = function () { return { locale: 'en-US', calendar: 'gregory', numberingSystem: 'latn', timeZone: this._o.timeZone || 'UTC' }; };
    DTF.supportedLocalesOf = function () { return ['en-US']; };
    var Coll = function Collator() { if (!(this instanceof Coll)) return new Coll(); use('Intl'); };
    Coll.prototype.compare = function (a, b) { a = String(a); b = String(b); return a < b ? -1 : a > b ? 1 : 0; };
    Coll.prototype.resolvedOptions = function () { return { locale: 'en-US', usage: 'sort', sensitivity: 'variant' }; };
    var PR = function PluralRules() { if (!(this instanceof PR)) throw new TypeError("Constructor PluralRules requires 'new'"); use('Intl'); };
    PR.prototype.select = function (n) { return Number(n) === 1 ? 'one' : 'other'; };
    PR.prototype.resolvedOptions = function () { return { locale: 'en-US', type: 'cardinal' }; };
    define(g, 'Intl', { NumberFormat: NF, DateTimeFormat: DTF, Collator: Coll, PluralRules: PR, getCanonicalLocales: function () { return ['en-US']; }, __p5shim: true });
    installed.Intl = true;
  }

  // ---------------------------------------------------------------- driver API used by every host
  var lib = null;
  var state = { status: 'idle', result: undefined, error: undefined };
  function resetCase() {
    seedRng(SEED);
    clock.vt = 0; clock.perfCalls = 0;
    timers.length = 0; timerCallbacks = 0;
    diagnostics.length = 0; diagDropped = 0;
    for (var k in usage) delete usage[k];
  }
  function errText(e) {
    if (e && typeof e === 'object') {
      var name = e.name || (e.constructor && e.constructor.name) || 'Error';
      return name + ': ' + e.message + (e.stack ? '\n' + String(e.stack).split('\n').slice(0, 8).join('\n') : '');
    }
    return 'thrown: ' + String(e);
  }
  var api = {
    version: 1,
    usage: usage,
    installed: installed,
    nativePresent: nativePresent,
    limits: LIMITS,
    info: {},
    register: function (l) { lib = l; },
    // Starts one case. The library's run() may return a string or a promise.
    start: function (input) {
      resetCase();
      state = { status: 'pending', result: undefined, error: undefined };
      if (!lib) { state = { status: 'error', error: 'no library registered' }; return; }
      var p;
      try { p = Promise.resolve(lib.run(input)); }
      catch (e) { state = { status: 'error', error: errText(e) }; return; }
      p.then(function (r) { state.status = 'done'; state.result = typeof r === 'string' ? r : JSON.stringify(r); },
        function (e) { state.status = 'error'; state.error = errText(e); });
    },
    // 'pending' | 'done' | 'error'
    status: function () { return state.status; },
    // Runs the earliest virtual timer. Returns false when no timer is queued.
    tick: function () {
      try { return tick(); }
      catch (e) { if (state.status !== 'error') { state.status = 'error'; state.error = errText(e); } return false; }
    },
    pendingTimers: function () { return timers.length; },
    take: function () {
      return JSON.stringify({
        status: state.status, result: state.result === undefined ? null : state.result,
        error: state.error === undefined ? null : state.error,
        usage: usage, timers_pending: timers.length, timer_callbacks: timerCallbacks, virtual_ms: clock.vt,
        diagnostics: diagnostics.slice(0, 50), diagnostics_total: diagnostics.length + diagDropped
      });
    },
    environment: function () {
      return JSON.stringify({ installed: installed, native: nativePresent, disabled: Object.keys(disabled), forced: Object.keys(forced), info: api.info, library: lib ? lib.name : null });
    },
    resetCase: resetCase
  };
  define(g, '__p5', api);
})(globalThis);
