# Spike: JavaScript bound to raikiri's DOM

Feasibility spike for the riskiest open item of the engine: LLM-written scripts must mutate the DOM before layout and read real geometry. The PDF comes out of the same rkhead path (raikiri `0fc0ba9f` + fulgur-raikiri `bd6222fe`). The workflow is `.github/workflows/spike-js-dom.yml`. Results are in the `spike-js-dom-results` artifact and the step summary.

## Engines

| binary | JS engine | DOM binding |
|---|---|---|
| `spike-rkjs` | QuickJS-NG through rquickjs `=0.14.0` (features `std`) | This spike: native handle functions in `crates/spike-rkjs/src/dom.rs` plus the JS facade in `src/prelude.js` |
| `spike-rkboa` | boa_engine 0.22 | raikiri's own `crates/raikiri-js` (`DomRuntime`), driven through a `DocumentHost` in `crates/spike-rkboa/src/main.rs` |

Both binaries share `crates/spike-common/pipeline.rs`, which provides the CLI, the rkhead config, the sandboxed file provider, relayout and the PDF. Each binary uses the same CLI as `adapter-rkhead`, plus `--metrics` and `--dump-html`.

## Design

1. `raikiri_html::parse` builds the live `raikiri_dom::Document`. Scripts mutate this arena in place with `pre_insert`, `pre_remove`, `set_element_attribute`, `set_element_text_content`, `replace_children_from` and the other mutation calls.
2. Classic `<script>` elements are collected in tree order and run one by one. An external `src` is read through the same sandbox, limited to the input directory. A microtask checkpoint follows each script. The host then fires `DOMContentLoaded` and `load`, and drains the virtual timers.
3. Geometry queries (`getBoundingClientRect`, `offset*`, `client*`) use a dirty flag. The first query after a mutation clones the live DOM and stamps every element with `data-rkjs-n=<arena index>`. It then serializes the clone, parses it again and lays it out with `raikiri_html::layout`, using the same resources and page defaults as fulgur-raikiri. Fragments map back to live nodes through the stamp. Later queries reuse that snapshot until the next mutation.
4. After the scripts, the live DOM is serialized and rendered by `fulgur_raikiri::render_html_with_options`, with the input directory as the base directory. Geometry and diagnostics come from a layout of that same final HTML.
5. Diagnostics combine `js:uncaught`, `js:console.<level>`, `js:fetch-error`, `js:relayout-error` and `js:timeout` with raikiri layout warnings.

## Cases

The pages are in `cases/` and their assertions in `cases/checks.json`. The checks read the PDF with `harness/pdfcheck.py` (pdfminer text and poppler raster) and compare against the final geometry.

1. `01_templating`: a table built from a JSON array, and cards made with `createElement` and `classList`.
2. `02_innerhtml`: a list and an inline-styled section injected with `innerHTML`.
3. `03_echarts_svg`: an ECharts SSR SVG inserted with `innerHTML`. The SVG is made in the same runtime by the `phase5_js/js/build.mjs` bundle. If that bundle is missing, the page uses `cases/assets/echarts_fallback.js`, which `scripts/gen_echarts_fallback.mjs` pre-generates from the same option.
4. `04_layout_query`: a width is set through `style`, then `getBoundingClientRect().width` and `offsetWidth` are written into text. Each value must match the final layout and the painted run of pixels within ±1 px.
5. `05_script_error`: a null dereference, a syntax error and an error thrown in a timer. The render must survive, and each error must appear in the diagnostics.

The phase 5 LLM-style DOM scripts (`phase5_js/js/cases/dom/*.js`) also run on both engines as pages.

## Local logic check

`node scripts/prelude_mock.mjs phase5_js/js/node_modules/linkedom cases/*.html` runs `prelude.js` against linkedom, which emulates the natives. The mock checks only the DOM logic: its geometry is fake.
