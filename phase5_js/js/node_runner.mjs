// Node baseline runner. Runs a case group with the same shims, bundle and host loop as the
// Rust runners (crates/qjs, crates/boa) and writes the same JSON schema.
//   node node_runner.mjs --cases dist/cases/echarts.json --dist dist --out r.json
//        [--only <id>] [--dom-impl linkedom|jsdom] [--shim-config '<json>'] [--label node]
// --dom-impl jsdom runs the dom/layout groups on JSDOM instead of the bundled linkedom.
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import vm from 'node:vm';

// Capture real host facilities before the shims replace the globals.
const hr = process.hrtime.bigint.bind(process.hrtime);
const realSetImmediate = setImmediate;
const realConsole = console;
const flush = () => new Promise((r) => realSetImmediate(r));

const args = process.argv.slice(2);
const opt = (name, def) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : def; };
const casesFile = opt('cases');
const distDir = opt('dist', 'dist');
const outFile = opt('out');
const only = opt('only', null);
const domImpl = opt('dom-impl', 'linkedom');
const label = opt('label', domImpl === 'jsdom' ? 'node-jsdom' : 'node');
const shimConfig = JSON.parse(opt('shim-config', '{}'));
const MAX_STEPS = 1000000;
const CASE_TIMEOUT_MS = Number(opt('timeout-ms', '20000'));

const group = JSON.parse(readFileSync(casesFile, 'utf8'));
const shimsSrc = readFileSync(join(distDir, 'shims.js'), 'utf8');
const cases = group.cases.filter((c) => !only || c.id === only);
const rssKb = () => Math.round(process.memoryUsage().rss / 1024);
const maxRssKb = () => process.resourceUsage().maxRSS;
const ms = (a, b) => Number(b - a) / 1e6;

async function drive(p5, deadline) {
  let steps = 0;
  for (;;) {
    await flush();
    const st = p5.status();
    if (st !== 'pending') return null;
    if (Number(hr()) / 1e6 > deadline) return 'Timeout: host deadline';
    if (++steps > MAX_STEPS) return 'JobBudget: host step budget';
    if (!p5.tick()) {
      await flush();
      return p5.status() === 'pending' ? 'NeverSettled: no timers or jobs left' : null;
    }
  }
}

const result = {
  engine: label, engine_version: process.version, v8: process.versions.v8, group: group.group,
  bundle: group.bundle, dom_impl: domImpl, shim_config: shimConfig, cases: []
};
const t0 = hr();

if (domImpl === 'jsdom' && (group.group === 'dom' || group.group === 'layout')) {
  const { JSDOM } = await import('jsdom');
  const { installLayoutProbe } = await import('./src/layout_probe.js');
  result.jsdom_version = JSON.parse(readFileSync(new URL('./node_modules/jsdom/package.json', import.meta.url), 'utf8')).version;
  result.load_ms = ms(t0, hr());
  for (const c of cases) {
    const c0 = hr();
    const rec = { id: c.id };
    try {
      const dom = new JSDOM(c.input.html, { runScripts: 'outside-only' });
      const w = dom.window;
      w.__P5_SHIM_CONFIG = shimConfig;
      w.eval(shimsSrc);
      w.__p5.resetCase();
      const measured = [];
      if (c.input.mode === 'layout') installLayoutProbe(w.document, c.input.layout || null, measured);
      w.eval(c.input.script);
      const html = '<!DOCTYPE html>' + w.document.documentElement.outerHTML;
      rec.status = 'done';
      rec.output = c.input.mode === 'layout' ? JSON.stringify({ html, measured }) : html;
      rec.usage = JSON.parse(w.__p5.take()).usage;
      w.close();
    } catch (e) {
      rec.status = 'error';
      rec.error = (e && e.name ? e.name + ': ' + e.message : String(e));
    }
    rec.ms = ms(c0, hr());
    rec.rss_kb = rssKb();
    rec.max_rss_kb = maxRssKb();
    result.cases.push(rec);
  }
} else {
  // Node >= 21 exposes a global `navigator` whose platform is the host OS; ECharts reads it
  // to pick a default font ('Microsoft YaHei' on Windows). Embedded engines have no
  // navigator, so it is removed to keep the baseline host-independent.
  result.node_navigator_removed = delete globalThis.navigator;
  globalThis.__P5_SHIM_CONFIG = shimConfig;
  vm.runInThisContext(shimsSrc, { filename: 'shims.js' });
  const p5 = globalThis.__p5;
  const l0 = hr();
  vm.runInThisContext(readFileSync(join(distDir, group.bundle + '.js'), 'utf8'), { filename: group.bundle + '.js' });
  result.load_ms = ms(l0, hr());
  result.environment = JSON.parse(p5.environment());
  for (const c of cases) {
    const c0 = hr();
    const deadline = Number(c0) / 1e6 + CASE_TIMEOUT_MS;
    let hostError = null;
    try {
      p5.start(c.input);
      hostError = await drive(p5, deadline);
    } catch (e) {
      hostError = 'HostException: ' + (e && e.name) + ': ' + (e && e.message);
    }
    const elapsed = ms(c0, hr());
    const taken = JSON.parse(p5.take());
    const rec = { id: c.id, status: hostError ? 'error' : taken.status, ms: elapsed, rss_kb: rssKb(), max_rss_kb: maxRssKb() };
    if (hostError) rec.error = hostError;
    else if (taken.status === 'error') rec.error = taken.error;
    if (taken.status === 'done' && !hostError) rec.output = taken.result;
    rec.usage = taken.usage;
    rec.timer_callbacks = taken.timer_callbacks;
    rec.virtual_ms = taken.virtual_ms;
    rec.diagnostics_total = taken.diagnostics_total;
    rec.diagnostics = taken.diagnostics.slice(0, 5);
    if (c.expect) rec.expect = c.expect;
    result.cases.push(rec);
  }
}

result.total_ms = ms(t0, hr());
result.peak_rss_kb = maxRssKb();
writeFileSync(outFile, JSON.stringify(result));
realConsole.log(`${label} ${group.group}: ${result.cases.filter((c) => c.status === 'done').length}/${result.cases.length} done, ${result.total_ms.toFixed(0)} ms, peak ${result.peak_rss_kb} KB`);
