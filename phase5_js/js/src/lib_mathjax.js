// MathJax 4 (TeX and MathML input, SVG output) on the liteAdaptor, no DOM.
// All dynamic font ranges of mathjax-newcm-font are bundled and registered up front,
// and mathjax.asyncLoad is a synchronous no-op, so html.convert() never needs a
// promise-based file loader (no filesystem, no network).
// input: { kind: 'tex' | 'mathml', src, display }
import { mathjax } from '@mathjax/src/mjs/mathjax.js';
import { TeX } from '@mathjax/src/mjs/input/tex.js';
import { MathML } from '@mathjax/src/mjs/input/mathml.js';
import { SVG } from '@mathjax/src/mjs/output/svg.js';
import { liteAdaptor } from '@mathjax/src/mjs/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from '@mathjax/src/mjs/handlers/html.js';
import '@mathjax/src/mjs/input/tex/base/BaseConfiguration.js';
import '@mathjax/src/mjs/input/tex/ams/AmsConfiguration.js';
import '@mathjax/src/mjs/input/tex/newcommand/NewcommandConfiguration.js';
import '@mathjax/src/mjs/input/tex/noundefined/NoUndefinedConfiguration.js';
import '@mathjax/src/mjs/input/tex/color/ColorConfiguration.js';
import '@mathjax/src/mjs/input/tex/boldsymbol/BoldsymbolConfiguration.js';
import '@mathjax/src/mjs/input/tex/cancel/CancelConfiguration.js';
import '@mathjax/src/mjs/input/tex/braket/BraketConfiguration.js';
import '@mathjax/src/mjs/input/tex/mathtools/MathtoolsConfiguration.js';
import '@mathjax/src/mjs/input/tex/mhchem/MhchemConfiguration.js';
import '@mathjax/src/mjs/input/tex/amscd/AmsCdConfiguration.js';
import { MathJaxNewcmFont } from '@mathjax/mathjax-newcm-font/mjs/svg.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/PUA.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/accents-b-i.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/accents.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/arabic.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/arrows.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/braille-d.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/braille.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/calligraphic.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/cherokee.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/cyrillic-ss.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/cyrillic.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/devanagari.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/double-struck.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/fraktur.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/greek-ss.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/greek.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/hebrew.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/latin-b.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/latin-bi.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/latin-i.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/latin.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/marrows.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/math.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/monospace-ex.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/monospace-l.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/monospace.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/mshapes.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/phonetics-ss.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/phonetics.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/sans-serif-b.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/sans-serif-bi.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/sans-serif-ex.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/sans-serif-i.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/sans-serif-r.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/sans-serif.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/script.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/shapes.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/symbols-b-i.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/symbols.js';
import '@mathjax/mathjax-newcm-font/mjs/svg/dynamic/variants.js';

mathjax.asyncLoad = () => null;
mathjax.asyncIsSynchronous = true;

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const PACKAGES = ['base', 'ams', 'newcommand', 'noundefined', 'color', 'boldsymbol', 'cancel', 'braket', 'mathtools', 'mhchem', 'amscd'];
// One document with both input jax and one font instance: the dynamic-file records are
// static per font class, so two font instances with synchronous loading would leave the
// second instance without the data (MathJax 4.1.3 then recurses in FontData.getChar).
let doc = null;
function getDoc() {
  if (!doc) {
    doc = mathjax.document('', {
      InputJax: [new TeX({ packages: PACKAGES }), new MathML()],
      OutputJax: new SVG({ fontCache: 'local', font: new MathJaxNewcmFont() })
    });
  }
  return doc;
}

globalThis.__p5.register({
  name: 'mathjax',
  run(input) {
    const d = getDoc();
    // Reset equation numbering, labels and output caches so each formula is independent of order.
    d.reset({ all: true });
    const node = d.convert(input.src, { format: input.kind === 'mathml' ? 'MathML' : 'TeX', display: input.display !== false, em: 16, ex: 8, containerWidth: 640 });
    return adaptor.outerHTML(node);
  }
});
