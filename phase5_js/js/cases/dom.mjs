// DOM templating cases (LLM-style scripts) and the layout-feedback case.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const script = (n) => readFileSync(join(here, 'dom', n + '.js'), 'utf8');
const page = (body, title) => `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>${title || 'Doc'}</title><style>.num{text-align:right}.card{border:1px solid #ccc}</style></head><body>${body}</body></html>`;

export const template = [
  { id: 'invoice', html: page('<div class="invoice" data-invoice="INV-2026-0042"><h1>Invoice</h1><table id="items"><thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead><tbody></tbody><tfoot><tr><td colspan="3">Subtotal</td><td id="subtotal"></td></tr><tr><td colspan="3">Tax</td><td id="tax"></td></tr><tr><td colspan="3">Total</td><td id="grand"></td></tr></tfoot></table></div>', 'Invoice'), script: script('invoice') },
  { id: 'kpi-cards', html: page('<h1>Dashboard</h1><div id="kpis" class="grid"></div>', 'KPIs'), script: script('kpi_cards') },
  { id: 'toc', html: page('<nav id="toc"></nav><main><h2>Introduction</h2><p>Text.</p><h3>Scope &amp; goals</h3><p>Text.</p><h3>Non-goals</h3><h2>Design</h2><h3>Layout</h3><h3>Layout</h3><h2>Results (2026)</h2></main>', 'TOC'), script: script('toc') },
  { id: 'product-grid', html: page('<p id="count"></p><div id="products"></div><template id="product-tpl"><article class="card"><h3 class="name"></h3><p class="price"></p><div class="tags"></div></article></template>', 'Products'), script: script('product_grid') },
  { id: 'report-locale', html: page('<h1>Quarterly report</h1><p id="generated"></p><table id="report"><tr><th>Region</th><th>Actual</th><th>Progress</th></tr></table><p>Total: <strong id="total"></strong></p>', 'Report'), script: script('report_locale') }
].map((c) => ({ id: c.id, input: { html: c.html, script: c.script, mode: 'template' } }));

export const layoutCase = {
  id: 'layout-feedback',
  input: {
    mode: 'layout',
    html: page('<main id="main"><h1 id="title">A deliberately long report title that may not fit in its box</h1><div class="cards"><div class="card" id="c1">Short</div><div class="card" id="c2">A much longer card body with several sentences of text that wraps onto multiple lines when laid out.</div><div class="card" id="c3">Medium length text here.</div></div><div id="bar" style="width:62%">bar</div><span id="bar-label"></span></main>', 'Layout'),
    script: script('layout_feedback')
  }
};

export default template;
