# SUMMARY: Are we ready to build the tool?

**Verdict: YES. Ready to start development.** Every building block has been tested in CI against independent oracles. No further research is required. What remains is a known engineering backlog (below) plus two legal decisions.

Date: 2026-11-23 · Test repo: `nithinkadari55/palm_bench_eval` · Detailed reports in `reports/`.

## 1. The chosen stack (every block measured)

| Layer | Choice | Licence | Key evidence |
|---|---|---|---|
| Layout + pagination core | **raikiri HEAD `0fc0ba9f`** + Fulgur's raikiri PDF backend, ported to HEAD by us (`rkhead`) | MIT/Apache | WPT 58.6% (Takumi 32.6%, others ≤26%), 0 crashes. Production corpus 94.8%. Agent print docs vs Chrome 0.929 (Takumi 0.940). |
| Fallback / donor engine | Takumi | MIT/Apache | Best Chrome likeness; table pagination and diagnostics worth porting |
| Text shaping | HarfRust 0.16.1 | MIT | 3,818/3,818 identical to HarfBuzz 8.3 and 15.2; 7,434/7,434 upstream tests |
| Line/word/grapheme breaking | ICU4X icu_segmenter 2.4 (`_17`/`neo`) | Unicode-3.0 | 100% on the official Unicode test files |
| Bidi | unicode-bidi 0.3.18 | MIT/Apache | 2,585,844/2,585,844 BidiTest cases |
| Font fallback / decoding | fontique 0.13, skrifa, wuff 0.2.10 | MIT/Apache | 100% script coverage (22 scripts); WOFF/WOFF2 84/84; 0 panics on 6,772 corrupt inputs |
| Hyphenation | hypher 0.1.8 | code MIT/Apache; **patterns mixed** | 80,000/80,000 identical to an independent Liang implementation |
| Images | `image` 0.25 (png, zune-jpeg, gif, image-webp), moxcms 0.8.1 (ICC), dav1d-native (AVIF) | MIT/Apache, BSD-2, MPL (mp4parse) | PNG 100%, WebP 98%, JPEG 93%, EXIF 34/34, ICC 98.8% |
| SVG | resvg/usvg 0.48 (raikiri's) | MIT/Apache | 1,730/1,730 of resvg's suite |
| CSS colour | raikiri-style's parser | MIT/Apache | 100% on hex/rgb/hsl/hwb/named/oklab; best of 4 candidates |
| PDF writer | **krilla 0.8.2** | MIT/Apache | veraPDF 238/238 (PDF/A-1…4 and UA-1), negative controls 6/6; deterministic; subset fonts at 0.38% of original size |
| JavaScript | **QuickJS-NG via rquickjs 0.14.0** | MIT | test262 99.85%. ECharts/MathJax/Chart.js output identical to Node. 17/17 escape attempts blocked; 24/24 runaway scripts contained. |
| JS ↔ DOM | **Our rquickjs binding to raikiri's DOM** (spike) | ours | **11/11 agent-style scripts end to end**, including real-layout `getBoundingClientRect` and ECharts SVG painted in the PDF; about 30 ms and 35 MB per document |
| Interface | Python package (PyO3) exposing a LangChain tool | — | Per REQUIREMENTS.md |
| CI validation | veraPDF, pdfminer/pypdf, poppler, WPT, Chrome (test oracle only) | GPL/MPL tools run, never linked | — |

## 2. What was tested

| Phase | Scale | Report |
|---|---|---|
| 1 Core bake-off (7 engines) | 14,883 WPT reftests per engine, 49 production docs (about 400 checks), 240 real/LLM web pages | `reports/CORE_REPORT.md` |
| 1b Print oracle | 456 agent-style and public print documents vs Chrome print output | `reports/PRINT_ORACLE_REPORT.md` |
| 1c Donor map | Per-test list of where each engine beats the core | `reports/DONOR_MAP.md` |
| 2 Text and fonts | Official Unicode/HarfBuzz/fontTools oracles, about 4.3M cases | `reports/PHASE2_TEXT_REPORT.md` |
| 3 Images, colour, SVG | PngSuite, libjpeg-turbo, libwebp, AVIF, ICC, WPT css-color, resvg suites, 5,850 corrupt files | `reports/PHASE3_MEDIA_REPORT.md` |
| 4 PDF output | 17 fixtures × 17 conformance profiles, veraPDF, 4 extractors, 4 viewers | `reports/PHASE4_PDF_REPORT.md` |
| 5 JavaScript | test262 (82k), 165 real-library cases, 41 sandbox cases | `reports/PHASE5_JS_REPORT.md` |
| Spike: JS ↔ DOM | 11 agent-style scripts end to end to PDF | `spike_js_dom/` (CI run 45175803351) |

## 3. Engineering backlog (known work; no research)

Ordered by impact on agent documents. Effort figures are estimates.

| # | Item | Source of the solution | Est. |
|---|---|---|---|
| 1 | Fork setup: raikiri + fulgur-raikiri as our workspace; bump to the tested versions (harfrust 0.16, icu 2.4, fontique 0.13, wuff 0.2.10, krilla 0.8.2); re-run the bake-off as the CI gate | done in `engines/rkhead` | 1 wk |
| 2 | **Chrome-equivalent default font mapping** plus a bundled font pack (Liberation, DejaVu, Noto incl. CJK, Nastaliq, COLR emoji) | Print oracle: 0.900 → 0.929 | 1 wk |
| 3 | **PDF painter parity** with raikiri-paint (backgrounds, borders, positioning, vertical writing) | Donor map: about 1,000+ WPT tests | 3–5 wk |
| 4 | **Production JS ↔ DOM binding** (from the spike): `#[class]` bindings, getComputedStyle, template, live collections, async/defer, observers as stubs, fetch blocked with a diagnostic, incremental relayout | `spike_js_dom/` + raikiri-js algorithms | 6–10 wk |
| 5 | Intl on ICU4X for QuickJS (NumberFormat, DateTimeFormat, PluralRules, toLocale*) | ICU4X already in the stack | 2 wk |
| 6 | Paged-media features: bookmarks from headings and `bookmark-level`, `target-counter()`, `string-set`, `position:fixed` per page, PDF Author | Ironpress/Fulgur algorithms; krilla outline API | 2–3 wk |
| 7 | Table pagination to match Chrome (data tables: 82% vs 98% page-break agreement) | Takumi `layout/table/fragmentation.rs` | 2 wk |
| 8 | ActualText for Arabic/Indic (copy/paste), PDF/A profile selection with fallback | krilla tagging API | 1 wk |
| 9 | Image hardening: decode only via the guarded path; AVIF transforms; YCCK/arithmetic JPEG reported as unsupported | Phase 3 | 1 wk |
| 10 | raikiri colour bugs: `color()` spaces, `color-mix` hue interpolation | moxcms / CSS Color 5 | 0.5 wk |
| 11 | **Diagnostics API** (the product's differentiator): per-page element boxes, overflow/clipping, unsupported CSS, missing glyphs, JS errors, source lines; strict mode | raikiri fragments/warnings + Takumi `ignored.rs` design | 3–4 wk |
| 12 | Sandbox/worker process with OS limits; resource caps; deterministic settle rule | Phase 5 supervisor | 1–2 wk |
| 13 | LangChain tool: PyO3 package, schema, versioned API, docs of supported features | REQUIREMENTS.md R12 | 1–2 wk |
| 14 | Regression CI: the bake-off, print oracle and phase suites as gates | already built | ongoing |

Total estimate: roughly 25–35 engineer-weeks for a production v1, with parallel tracks possible (layout/painter, JS, PDF/diagnostics, packaging).

## 4. Decisions needed from you (not research)

1. **Hyphenation pattern licences:** 21 of 48 languages, including **en, nl, pt, ru**, have no MIT/Apache option. Choose between legal approval, shipping only the 27 permissive languages, or sourcing en-US patterns separately.
2. **MathJax font licence:** `@mathjax/mathjax-newcm-font` has no LICENSE file. Confirm before bundling math support.
3. **MPL-2.0 components:** cssparser, selectors and mp4parse are file-level copyleft. They are fine commercially but must be listed. Confirm the licence policy.

## 5. Risks (accepted, with mitigations)

| Risk | Mitigation |
|---|---|
| raikiri is effectively a one-developer project changing fast | We own a pinned fork; upstream syncs happen only through the bake-off gate. |
| QuickJS-NG issues no CVEs; its C assertions abort | Run JS in an isolated worker process with OS limits (proven in phase 5). |
| Krilla has no PDF/UA-2 or forms | Not in the requirements; PDF/UA-1 is fully validated. |
| The core is behind Chrome on some print layouts (tables, brochures) | Backlog items 2, 3 and 7, measured by the print oracle on every change. |
