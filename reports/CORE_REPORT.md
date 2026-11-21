# Phase 1: Core Layout/Pagination Engine Bake-off

**Decision: Core = raikiri, shipped through Fulgur's raikiri PDF backend (`fulgur-raikiri` → krilla). We fork it and move it to raikiri HEAD.**
**Runner-up: Takumi.** We take two things from it: its unsupported-CSS reporting (`style/ignored.rs`) and its fidelity on LLM-style pages.

Evidence: CI run [44910674737](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/44910674737), all jobs green. Every engine pinned to an exact SHA, same harness, same fonts, same WPT commit `9986bb32`.

## 1. What was tested

| Test | Size | Oracle |
|---|---|---|
| WPT reftests | 14,883 tests per PDF engine across 13 suites: CSS2, css-break, css-page, css-tables, css-flexbox, css-grid, css-inline, css-multicol, css-text, css-position, css-backgrounds, css-writing-modes, css-gcpm | Test vs reference rendered by the same engine, pixel compare with WPT fuzzy rules, reference chains, print mode (5×3 in, 0.5 in margins). Blank-vs-blank passes are counted separately. |
| Production corpus | 49 documents, about 400 checks: pagination, layout, text, fonts, images, graphics, navigation, modern CSS, robustness, JS | Independent geometry from the PDF (pdfminer glyph boxes), pixel probes at exact CSS coordinates, PDF structure (pypdf), plus determinism (render twice) |
| Real-world fidelity | 120 Design2Code real web pages + 120 WebSight LLM-generated pages | SSIM against the dataset's Chrome screenshots, plus text recall |
| Robustness/perf | 100-page document, 3000-deep DOM, 20k siblings, malformed HTML, crashtests | Status, time, peak RSS, 6 GB address-space cap |

Engines: **takumi** (`d5bf755e`), **fulgur** (Blitz backend, `bd6222fe`), **fulraikiri** (Fulgur raikiri backend, raikiri crates 0.0.6), **ironpress** (`dadedd4c`), **raikiri** HEAD (`a570d903`, screen raster only, no PDF writer), **blitz** (`6636442d`, screen raster only).

## 2. Results

### WPT pass rate (reftests run)

| Suite | fulraikiri | takumi | fulgur | ironpress | raikiri HEAD* | blitz* |
|---|---|---|---|---|---|---|
| CSS2 (6.2k) | **54.9%** | 32.4% | 29.6% | 21.6% | 83.1% | 72.9% |
| css-flexbox | **66.6%** | 34.5% | 28.0% | 17.4% | 77.6% | 84.5% |
| css-grid | **42.4%** | 30.4% | 25.3% | 16.8% | 47.7% | 43.8% |
| css-tables | **54.5%** | 47.2% | 30.9% | 23.6% | 65.7% | 41.3% |
| css-text | **69.2%** | 61.4% | 38.9% | 22.5% | 73.2% | 68.2% |
| css-page (print) | **61.6%** | 54.1% | 35.8% | 22.7% | n/a | n/a |
| css-break | **21.0%** | 7.9% | 8.1% | 5.9% | 27.8% | 8.3% |
| css-multicol | **32.2%** | 11.9% | 10.7% | 8.1% | 47.7% | 16.8% |
| css-writing-modes | 29.4% | 21.6% | 10.3% | 22.7% | 76.1% | 38.0% |
| css-position | **40.0%** | 25.1% | 18.0% | 15.7% | 34.1% | 25.8% |
| css-backgrounds | 19.0% | **21.6%** | 16.6% | 16.1% | 57.7% | 70.8% |
| **Total** | **48.2%** | 31.6% | 25.5% | 18.9% | 68.3% | 57.9% |
| Crash/timeout | 1 | 0 | 7 | 36 | 0 | 0 |

\* Screen-only engines run screen reftests only; print tests are not applicable to them. css-gcpm has no reftests at this WPT commit.

### Production corpus (checks passed)

| Category | fulraikiri | takumi | fulgur | ironpress |
|---|---|---|---|---|
| pagination | **35/37** | 33/37 | 31/37 | 34/37 |
| layout | **105/105** | 98/105 | 95/106 | 98/104 |
| text | 65/69 | **66/69** | 63/70 | 62/68 |
| css | **32/34** | **32/34** | 21/34 | 29/34 |
| graphics | **34/36** | **34/36** | 31/36 | 24/36 |
| images | **13/14** | 10/14 | 7/14 | 8/14 |
| fonts (@font-face woff/woff2/ttf) | **3/3** | **3/3** | 0/3 | 1/3 |
| pdf (embedding, extractable text) | 83/84 | 82/84 | 85/86 | 41/89 |
| navigation | 3/9 | 2/9 | 3/9 | 4/9 |
| robustness | 5/6 | 5/6 | 5/6 | 4/6 |
| **Total** | **94.3%** | 91.0% | 84.2% | 75.5% |
| 100 pages: seconds / peak RSS | 1.06 s / 319 MB | 0.47 s / 193 MB† | 0.54 s / 77 MB | 25.7 s / 90 MB |
| Deterministic output | yes, byte-identical | yes | yes | yes |

† Takumi's adapter loads every system font on each run, so its time includes font loading. Its warm-process time would be lower.

### Real-world fidelity vs Chrome screenshots

| Engine | Design2Code: OK / SSIM / text recall | WebSight: OK / SSIM / text recall |
|---|---|---|
| takumi | 115/120 / 0.652 / 0.840 | 120/120 / **0.910** / **0.989** |
| fulraikiri | 119/120 / 0.648 / **0.856** | 120/120 / 0.827 / 0.978 |
| fulgur | 119/120 (1 crash) / 0.645 / 0.779 | 120/120 / 0.856 / 0.975 |
| ironpress | 120/120 / 0.611 / 0.761 | 120/120 / 0.806 / 0.951 |
| raikiri HEAD | 119/120 / **0.695** / n/a | 120/120 / 0.827 / n/a |

## 3. Decisive findings (from the evidence)

**Takumi**
- Hard-fails the whole PDF on `filter: blur(0px)`: 5 of 120 real pages produced no output.
- Defaults to `box-sizing: border-box`, a CSS spec violation that breaks plain-CSS layouts (l07 box model 5/10).
- No multi-column layout (text spans the full width), no vertical writing, no `outline`, no EXIF/CMYK/AVIF.
- Refuses DOM depth over 512 instead of recovering.
- No element geometry API (page geometry is `pub(crate)`).
- Strengths: best LLM-page fidelity, strong unsupported-CSS diagnostics, tagged PDF.

**fulraikiri (raikiri)**
- Best PDF-engine conformance on every layout suite except backgrounds.
- Best production corpus result: layout 100%, footnotes, orphans/widows, repeated thead/tfoot, multicol.
- Exposes per-page fragment geometry and structured warnings.
- Built on old raikiri 0.0.6 crates. raikiri HEAD scores 68.3% on screen reftests vs 48.2% here, so moving to HEAD is the biggest single gain available.

**Fulgur (Blitz backend)**
- Lays out once and slices into pages; WPT 25.5%.
- No @font-face loading, multicol drops content, `<img src=svg>` and WebP not painted.
- Superseded by its own raikiri backend.

**Ironpress**
- Lowest conformance; ignores `<link rel=stylesheet>`; 36 crashes/timeouts.
- 25.7 s for 100 pages; fonts not embedded in some outputs.

**Blitz**
- Good screen conformance, but no pagination and no PDF writer. Not a core.

## 4. Gaps no engine covers yet (carried into later phases)

| Gap | Status in chosen core | Plan |
|---|---|---|
| JavaScript execution | none | Phase 5: QuickJS-NG bound to the DOM |
| PDF bookmarks/outline (auto from headings and GCPM `bookmark-level`) | missing | Implement in our PDF layer (krilla supports outlines) |
| `target-counter()` TOC page numbers, `string-set` running headers | missing (`running()` elements work) | Port from Fulgur GCPM / WeasyPrint |
| PDF Author metadata, AVIF, hyphenation (`hyphens:auto`) | missing | Phases 2–4 |
| `writing-mode: vertical-rl` in PDF path | fails | Check after the raikiri HEAD upgrade |
| DOM depth > 512 | errors | Flatten like browsers do (our code) |
| `@layer` ordering | wrong | Check after the HEAD upgrade |

## 5. Risks and next actions for the core

1. **Upgrade gate (first task):** fork fulgur-raikiri, move it to raikiri HEAD, and re-run this bake-off. Target: PDF reftests at least 60%, with no corpus regression.
2. **Bus factor:** raikiri is effectively one developer plus agents, with very high velocity and `#[doc(hidden)]` APIs. Mitigation: pinned fork, our own interface layer, upstream sync only through this bake-off.
3. **License:** fulgur, raikiri and krilla are MIT/Apache. The CSS-parser family (cssparser/selectors, MPL-2.0) needs confirming in the license phase.
4. Takumi is kept as the fallback core and as the source to port `ignored.rs`-style diagnostics from.
