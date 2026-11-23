// Logic check of crates/spike-rkjs/src/prelude.js without Rust: the __rkdom natives are
// emulated over linkedom (same handle-based contract as dom.rs), the prelude and the page
// scripts run in a node:vm context, and the serialized document plus the diagnostics are
// printed as JSON. Geometry is fake (inline px width/height), so only DOM logic is checked.
// usage: node prelude_mock.mjs <linkedom-module-dir> <case.html>...
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const [linkedomDir, ...cases] = process.argv.slice(2);
const { parseHTML } = await import(pathToFileURL(join(resolve(linkedomDir), 'esm', 'index.js')).href);
const prelude = readFileSync(join(here, '..', 'crates', 'spike-rkjs', 'src', 'prelude.js'), 'utf8');

function runCase(file) {
  const html = readFileSync(file, 'utf8');
  const { document } = parseHTML(html);
  const nodes = [];
  const ids = new Map();
  const id = (n) => {
    if (!n) return -1;
    if (!ids.has(n)) { ids.set(n, nodes.length); nodes.push(n); }
    return ids.get(n);
  };
  const at = (i) => nodes[i];
  const logs = [];
  let lastError = '';
  const tryMsg = (f) => { try { f(); return ''; } catch (e) { return String(e && e.message || e); } };
  const N = {
    root: () => id(document),
    kind: (i) => at(i) ? at(i).nodeType : -1,
    tag: (i) => at(i) && at(i).nodeType === 1 ? at(i).localName : '',
    ns: (i) => at(i) && at(i).nodeType === 1 ? (at(i).namespaceURI || 'http://www.w3.org/1999/xhtml') : '',
    parent: (i) => id(at(i).parentNode),
    children: (i) => Array.from(at(i).childNodes).map(id),
    create: (t) => { try { return id(document.createElement(t)); } catch (e) { lastError = e.message; return -1; } },
    createNS: (ns, t) => id(document.createElementNS(ns, t)),
    text: (d) => id(document.createTextNode(d)),
    comment: (d) => id(document.createComment(d)),
    fragment: () => id(document.createDocumentFragment()),
    insert: (p, n, b) => tryMsg(() => at(p).insertBefore(at(n), b < 0 ? null : at(b))),
    remove: (p, c) => tryMsg(() => at(p).removeChild(at(c))),
    getText: (i) => at(i).nodeType === 1 || at(i).nodeType === 11 ? at(i).textContent : at(i).data,
    setText: (i, s) => tryMsg(() => { if (at(i).nodeType === 1) at(i).textContent = s; else at(i).data = s; }),
    getHTML: (i) => at(i).innerHTML,
    setHTML: (i, s) => tryMsg(() => { at(i).innerHTML = s; }),
    getAttr: (i, n) => { const v = at(i).getAttribute(n); return v === null ? undefined : v; },
    setAttr: (i, n, v) => tryMsg(() => at(i).setAttribute(n, v)),
    removeAttr: (i, n) => tryMsg(() => at(i).removeAttribute(n)),
    attrNames: (i) => Array.from(at(i).attributes).map((a) => a.name),
    byId: (r, s) => id(document.getElementById(s)),
    query: (r, s, all) => {
      try { return Array.from(at(r).querySelectorAll(s)).slice(0, all ? undefined : 1).map(id); }
      catch (e) { lastError = e.message; return undefined; }
    },
    matches: (i, s) => { try { return at(i).matches(s) ? 1 : 0; } catch (e) { lastError = e.message; return -1; } },
    clone: (i, deep) => id(at(i).cloneNode(deep)),
    templateContent: (i) => at(i).content ? id(at(i).content) : -1,
    rect: (i) => {
      const s = at(i).getAttribute && at(i).getAttribute('style') || '';
      const w = /(?:^|;)\s*width:\s*([\d.]+)px/.exec(s);
      const h = /(?:^|;)\s*height:\s*([\d.]+)px/.exec(s);
      return [0, 0, w ? +w[1] : 0, h ? +h[1] : 0];
    },
    viewport: () => [794, 1123],
    log: (level, msg) => { logs.push([level, msg]); },
    lastError: () => lastError
  };
  const ctx = vm.createContext({ __rkdom: N });
  vm.runInContext(prelude, ctx, { filename: 'prelude.js' });
  const scripts = Array.from(document.querySelectorAll('script'));
  for (const s of scripts) {
    let src = s.textContent;
    const ext = s.getAttribute('src');
    if (ext) {
      const p = join(dirname(file), ext);
      if (!existsSync(p)) { logs.push(['fetch', ext + ': missing']); continue; }
      src = readFileSync(p, 'utf8');
    }
    try { vm.runInContext(src, ctx, { filename: ext || 'inline' }); }
    catch (e) { logs.push(['uncaught', String(e && e.name) + ': ' + String(e && e.message)]); }
  }
  vm.runInContext("__rk.setReady('interactive'); __rk.fire('DOMContentLoaded'); __rk.setReady('complete'); __rk.fire('load'); while (__rk.runTimer(10000, 30000)) {}", ctx);
  return { case: file, logs, html: document.toString() };
}

for (const c of cases) console.log(JSON.stringify(runCase(c)));
