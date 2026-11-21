// LLM-style DOM templating scripts on linkedom.
// input: { html, script, mode?, layout? }
//   mode 'template' (default): run the script with document/window as globals and return the
//     serialized document ('<!DOCTYPE html>' + documentElement.outerHTML).
//   mode 'layout': also return what the geometry APIs answered (layout_probe.js); with
//     input.layout the probe answers from host-measured boxes (two-pass prototype).
import { parseHTML } from 'linkedom';
import { installLayoutProbe } from './layout_probe.js';

function serialize(document) {
  return '<!DOCTYPE html>' + document.documentElement.outerHTML;
}

globalThis.__p5.register({
  name: 'dom',
  run(input) {
    const { window, document } = parseHTML(input.html);
    const measured = [];
    if (input.mode === 'layout') installLayoutProbe(document, input.layout || null, measured);
    const g = globalThis;
    const hadWindow = Object.prototype.hasOwnProperty.call(g, 'window');
    const hadDocument = Object.prototype.hasOwnProperty.call(g, 'document');
    const saved = { window: g.window, document: g.document };
    g.window = window;
    g.document = document;
    try {
      (0, eval)(input.script);
    } finally {
      if (hadWindow) g.window = saved.window; else delete g.window;
      if (hadDocument) g.document = saved.document; else delete g.document;
    }
    if (input.mode === 'layout') return JSON.stringify({ html: serialize(document), measured });
    return serialize(document);
  }
});
