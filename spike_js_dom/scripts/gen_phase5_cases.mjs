// Writes the phase 5 LLM-style DOM cases (phase5_js/js/cases/dom.mjs: page + script) as
// standalone pages with the script inlined at the end of <body>.
// usage: node gen_phase5_cases.mjs <phase5_js/js/cases/dom.mjs> <out-dir>
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [mod, out] = process.argv.slice(2);
const dom = await import(pathToFileURL(resolve(mod)).href);
mkdirSync(out, { recursive: true });
const cases = [...dom.template, dom.layoutCase];
for (const c of cases) {
  // A replacer function, so '$' sequences in the script are not replacement patterns.
  const html = c.input.html.replace('</body>', () => '<script>\n' + c.input.script + '\n</script></body>');
  writeFileSync(join(out, c.id + '.html'), html);
}
console.log('wrote', cases.length, 'pages to', out);
