# Phase 1: Core Layout/Pagination Engine Bake-off (final)

**Decision: Core = raikiri HEAD (`0fc0ba9f`) + Fulgur's raikiri PDF backend (`fulgur-raikiri` → krilla), ported by us to HEAD = engine `rkhead`.**
**Runner-up: Takumi.** It stays as the fallback, and we port its unsupported-CSS diagnostics (`style/ignored.rs`).

Final evidence: CI run [44915583450](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/44915583450), 136 jobs green. Every engine is pinned to an exact SHA and run with the same harness, the same fonts and the same WPT commit (`9986bb32`). Raw output is in `core_raw_summary.md`.

## 1. What was tested

| Test | Size | Oracle |
|---|---|---|
| WPT reftests | 14,883 per PDF engine across 13 suites (CSS2, break, page, tables, flexbox, grid, inline, multicol, text, position, backgrounds, writing-modes, gcpm) | Test vs reference rendered by the same engine; WPT fuzzy rules, reference chains, print mode 5×3 in with 0.5 in margins. PDFs rasterized at 96 dpi with antialiasing off for exact-pixel compare. Blank-vs-blank passes are counted separately. |
| Production corpus | 49 documents, about 400 checks | Glyph geometry from the PDF (pdfminer), pixel probes at exact CSS coordinates, PDF structure (pypdf), determinism (two renders) |
| Real-world fidelity | 120 Design2Code pages + 120 WebSight LLM pages | SSIM against Chrome screenshots, plus text recall |
| Robustness/perf | 100 pages, 3000-deep DOM, 20k siblings, malformed HTML, crashtests | Status, time, RSS, 6 GB cap |

## 2. Results

### WPT pass rate

| Suite | **rkhead** | fulraikiri (raikiri 0.0.6) | takumi | fulgur | ironpress | raikiri HEAD (screen)* | blitz (screen)* |
|---|---|---|---|---|---|---|---|
| CSS2 (6.2k) | **73.9%** | 72.7% | 33.9% | 30.3% | 21.9% | 83.1% | 72.9% |
| css-flexbox | **73.2%** | 72.2% | 35.5% | 29.3% | 17.9% | 77.6% | 84.5% |
| css-text | **73.2%** | 72.3% | 62.4% | 38.9% | 22.6% | 73.2% | 68.2% |
| css-page (print) | **63.3%** | 62.4% | 54.6% | 36.2% | 24.0% | n/a | n/a |
| css-tables | **58.4%** | 55.6% | 47.2% | 30.9% | 23.6% | 65.7% | 41.3% |
| css-grid | **44.1%** | 43.1% | 30.4% | 25.4% | 16.9% | 47.7% | 43.8% |
| css-multicol | **43.7%** | 40.3% | 11.9% | 11.1% | 8.1% | 47.7% | 16.8% |
| css-position | **41.6%** | 40.8% | 25.5% | 18.0% | 15.7% | 34.1% | 25.8% |
| css-writing-modes | **36.0%** | 34.7% | 22.8% | 10.3% | 22.7% | 76.1% | 38.0% |
| css-backgrounds | **25.4%** | 25.0% | 22.6% | 17.4% | 16.4% | 57.7% | 70.8% |
| css-inline | 23.5% | 23.5% | 21.6% | **27.9%** | 17.2% | 19.4% | 17.4% |
| css-break | **22.7%** | 21.6% | 8.0% | 8.1% | 5.9% | 27.8% | 8.3% |
| **Total** | **58.6%** | 57.5% | 32.6% | 25.9% | 19.1% | 68.3% | 57.9% |
| Crash/timeout | **0** | 1 | 0 | 7 | 36 | 0 | 0 |

\* Screen-only engines have no PDF writer and run only screen reftests.

### Production corpus

| Category | **rkhead** | fulraikiri | takumi | fulgur | ironpress |
|---|---|---|---|---|---|
| pagination | **35/37** | 35/37 | 33/37 | 31/37 | 34/37 |
| layout | **105/105** | 105/105 | 98/105 | 95/106 | 98/104 |
| text | **66/69** | 65/69 | 66/69 | 63/70 | 62/68 |
| css | **33/34** | 32/34 | 32/34 | 21/34 | 29/34 |
| graphics | **34/36** | 34/36 | 34/36 | 31/36 | 24/36 |
| images | **13/14** | 13/14 | 10/14 | 7/14 | 8/14 |
| fonts (@font-face woff/woff2/ttf) | **3/3** | 3/3 | 3/3 | 0/3 | 1/3 |
| pdf | 83/84 | 83/84 | 82/84 | 85/86 | 41/89 |
| navigation | 3/9 | 3/9 | 2/9 | 3/9 | 4/9 |
| robustness | 5/6 | 5/6 | 5/6 | 5/6 | 4/6 |
| **Total** | **94.8%** | 94.3% | 91.0% | 84.2% | 75.5% |
| 100 pages: time / RSS | 1.04 s / 236 MB | 1.54 s / 318 MB | 0.49 s / 193 MB† | 0.54 s / 77 MB | 25.7 s / 90 MB |
| Deterministic | byte-identical | byte-identical | byte-identical | byte-identical | byte-identical |

† Takumi's time includes loading every system font per process.

### Real-world fidelity vs Chrome screenshots

| Engine | Design2Code: OK / SSIM / text recall | WebSight: OK / SSIM / text recall |
|---|---|---|
| **rkhead** | 119/120 / 0.652 / 0.853 | 120/120 / 0.828 / 0.978 |
| takumi | 115/120 / 0.652 / 0.840 | 120/120 / **0.910** / **0.989** |
| fulgur | 119/120 / 0.645 / 0.779 | 120/120 / 0.856 / 0.975 |
| ironpress | 120/120 / 0.611 / 0.761 | 120/120 / 0.806 / 0.951 |

## 3. Why rkhead

- **Best PDF-engine conformance in 11 of 12 suites.** It is 26 points ahead of Takumi overall and has 0 crashes.
- **Best on production documents:** layout 100%, footnotes, orphans/widows, repeated thead/tfoot, multicol, named pages.
- **Agent feedback built in:** per-page fragment geometry and structured warnings are exposed (`raikiri_html::layout`). Takumi keeps its page geometry `pub(crate)`.
- **Port to HEAD was cheap:** the raikiri-html public API is unchanged since 0.0.6; only 4 small edits were needed (see `engines/rkhead`).

## 4. Why not Takumi

- Fails the whole PDF on `filter: blur(0px)` (5 of 120 real pages).
- Defaults to `box-sizing: border-box`, which violates the CSS spec.
- No multi-column, no vertical writing, no `outline`, no EXIF/CMYK/AVIF.
- Errors at DOM depth over 512.
- No geometry API.

Its WebSight fidelity (0.91) is the best of all engines, which is why it stays the fallback.

## 5. Known gaps in rkhead (our integration work)

| Gap | Evidence | Owner |
|---|---|---|
| Background painting in the PDF path (25% vs 58% for raikiri's own painter) | css-backgrounds | Fix the fulgur-raikiri krilla painter |
| Vertical writing modes in PDF (36% vs 76% on screen) | css-writing-modes, corpus t09 | Painter / text emission |
| PDF bookmarks/outline (auto and GCPM `bookmark-level`), `target-counter()`, `string-set`, PDF Author | corpus n01/n02/n03/p13 | Our PDF/GCPM layer (krilla has outlines) |
| JavaScript | corpus j01 | Phase 5 |
| AVIF, `@layer`/logical properties, DOM depth > 512 | corpus i01/c01/r02 | Phases 3 and 4, plus upstream |

## 6. Risks

1. **Bus factor:** raikiri is effectively one developer plus agents, with very fast change. Mitigation: a pinned fork, our own interface layer, and upstream syncs gated by this bake-off.
2. **Licences:** raikiri, fulgur and krilla are MIT/Apache. cssparser/selectors are MPL-2.0 (file-level), which is acceptable but must be listed.
3. **Toolchain:** raikiri pins Rust 1.95.0; the fulgur crates compile under it (verified in CI).
