// Bundles each library entry into one classic script (IIFE) for embedded engines.
// Output: dist/<name>.js plus dist/shims.js and dist/bundles.json (sizes, licences).
import { build } from 'esbuild';
import { readFileSync, writeFileSync, mkdirSync, readdirSync, copyFileSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, 'dist');
mkdirSync(dist, { recursive: true });

// Every dynamic font range must be imported by the MathJax entry (no runtime loader exists).
const dyn = join(here, 'node_modules/@mathjax/mathjax-newcm-font/mjs/svg/dynamic');
const mj = readFileSync(join(here, 'src/lib_mathjax.js'), 'utf8');
const missing = readdirSync(dyn).filter((f) => f.endsWith('.js') && !mj.includes(`/dynamic/${f}'`));
if (missing.length) throw new Error('lib_mathjax.js misses dynamic font files: ' + missing.join(', '));

const ENTRIES = ['echarts', 'mathjax', 'chartjs', 'd3', 'dom', 'probe', 'sandbox'];
const info = { esbuild: (await import('esbuild')).version, bundles: {} };
for (const name of ENTRIES) {
  const outfile = join(dist, `${name}.js`);
  const res = await build({
    entryPoints: [join(here, `src/lib_${name}.js`)],
    outfile,
    bundle: true,
    format: 'iife',
    platform: 'neutral',
    target: 'es2022',
    mainFields: ['module', 'main'],
    conditions: ['import', 'default'],
    define: { 'process.env.NODE_ENV': '"production"' },
    alias: { canvas: join(here, 'node_modules/linkedom/commonjs/canvas-shim.cjs') },
    legalComments: 'eof',
    charset: 'utf8',
    minify: false,
    metafile: true,
    logLevel: 'warning'
  });
  const inputs = Object.keys(res.metafile.inputs);
  const pkgs = new Set();
  for (const p of inputs) {
    const m = /node_modules\/((?:@[^/]+\/)?[^/]+)\//.exec(p.replace(/\\/g, '/'));
    if (m) pkgs.add(m[1]);
  }
  const bytes = readFileSync(outfile);
  info.bundles[name] = {
    bytes: statSync(outfile).size,
    sha256: createHash('sha256').update(bytes).digest('hex'),
    packages: [...pkgs].sort()
  };
}
copyFileSync(join(here, 'src/shims.js'), join(dist, 'shims.js'));

// Case files: dist/cases/<group>.json = { group, bundle, compare, cases: [{ id, input }] }.
const echartsCases = (await import('./cases/echarts.mjs')).default;
const mathjaxMod = await import('./cases/mathjax.mjs');
const chartjsCases = (await import('./cases/chartjs.mjs')).default;
const d3Cases = (await import('./cases/d3.mjs')).default;
const domMod = await import('./cases/dom.mjs');
const sandboxMod = await import('./cases/sandbox.mjs');
if (echartsCases.length !== 20 || mathjaxMod.counts.tex !== 100 || mathjaxMod.counts.mathml !== 20 || chartjsCases.length !== 10 || d3Cases.length !== 10) {
  throw new Error('case counts changed');
}
const GROUPS = [
  { group: 'echarts', bundle: 'echarts', compare: 'svg', cases: echartsCases },
  { group: 'mathjax', bundle: 'mathjax', compare: 'svg', cases: mathjaxMod.default },
  { group: 'chartjs', bundle: 'chartjs', compare: 'ops', cases: chartjsCases },
  { group: 'd3', bundle: 'd3', compare: 'svg', cases: d3Cases },
  { group: 'dom', bundle: 'dom', compare: 'html', cases: domMod.template },
  { group: 'layout', bundle: 'dom', compare: 'none', cases: [domMod.layoutCase] },
  { group: 'probe', bundle: 'probe', compare: 'none', cases: [{ id: 'probe', input: {} }] },
  { group: 'sandbox_limits', bundle: 'sandbox', compare: 'none', cases: sandboxMod.limits.map((c) => ({ id: c.id, expect: c.expect, input: { script: c.script } })) },
  { group: 'sandbox_escapes', bundle: 'sandbox', compare: 'none', cases: sandboxMod.escapes.map((c) => ({ id: c.id, input: { script: c.script } })) }
];
mkdirSync(join(dist, 'cases'), { recursive: true });
for (const g of GROUPS) writeFileSync(join(dist, 'cases', g.group + '.json'), JSON.stringify(g));
info.groups = GROUPS.map((g) => ({ group: g.group, bundle: g.bundle, compare: g.compare, cases: g.cases.length }));

// Licences of every bundled package, read from node_modules/<pkg>/package.json.
const lic = {};
for (const b of Object.values(info.bundles)) {
  for (const p of b.packages) {
    if (lic[p]) continue;
    const pj = JSON.parse(readFileSync(join(here, 'node_modules', p, 'package.json'), 'utf8'));
    const files = readdirSync(join(here, 'node_modules', p)).filter((f) => /^(licen[cs]e|copying|notice)/i.test(f));
    lic[p] = { version: pj.version, license: pj.license || (pj.licenses && pj.licenses.map((l) => l.type).join(' OR ')) || null, license_files: files };
  }
}
for (const p of ['jsdom', 'esbuild']) {
  const pj = JSON.parse(readFileSync(join(here, 'node_modules', p, 'package.json'), 'utf8'));
  lic[p] = { version: pj.version, license: pj.license, license_files: readdirSync(join(here, 'node_modules', p)).filter((f) => /^(licen[cs]e|copying|notice)/i.test(f)), not_bundled: true };
}
info.licenses = lic;
writeFileSync(join(dist, 'bundles.json'), JSON.stringify(info, null, 2));
console.log(JSON.stringify(Object.fromEntries(Object.entries(info.bundles).map(([k, v]) => [k, v.bytes]))));
