# Print Oracle: 456 agent-style print documents vs Chrome print output

**Result: rkhead and Takumi are statistically close (0.929 vs 0.940). The core decision stands (rkhead), and Takumi's table pagination is added to the donor list.**

Evidence: CI run [45151937844](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/45151937844) with the Chrome-equivalent font mapping. The baseline without it is [45148252835](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/45148252835). Chrome 157 is used only as a CI oracle.

## Corpus

- **300 generated documents** across 20 categories: invoices, receipts, quotes, reports, resumes, contracts, papers, newsletters, brochures, certificates, menus, tickets, data tables, dashboards, letters, i18n, spec sheets, minutes, timetables, and 20–60-page long-form documents.
- **56 public print-CSS samples:** Paged.js specs (MIT), Vivliostyle docs, WeasyPrint samples.
- **100 WebSight LLM pages** printed to A4.
- Every document gets the same default `@page{size:A4;margin:15mm}`.

## Leaderboard (font mapping matched to Chrome's Linux defaults)

| Engine | Score | Pages exact | Page-break agreement | Text recall / precision | Position dx / dy median (p90) | Within 2 px | SSIM | Time p50 | RSS p95 |
|---|---|---|---|---|---|---|---|---|---|
| takumi | **0.940** | 89.7% | **92.8%** | 96.8% / **98.7%** | 0.5 / 0.5 (0.8) | **67.5%** | **0.878** | 0.14 s | 184 MB |
| **rkhead** | 0.929 | **90.3%** | 92.2% | 96.6% / 96.8% | **0.4** / 0.7 (1.5) | 64.9% | 0.860 | **0.06 s** | **68 MB** |
| fulraikiri | 0.920 | 89.2% | 91.1% | 96.6% / 96.8% | 0.5 / 0.9 (7.9) | 58.4% | 0.835 | 0.06 s | 74 MB |
| fulgur | 0.873 | 79.6% | 83.7% | 94.5% / 96.0% | 0.6 / 3.7 (28.0) | 37.7% | 0.749 | 0.05 s | 58 MB |
| ironpress | 0.846 | 75.0% | 81.2% | 95.5% / 93.8% | 6.5 / 20.0 (62.0) | 15.6% | 0.676 | 0.23 s | 97 MB |

All 456 documents rendered on every engine, with no crashes or timeouts.

**Key finding:** generic font mapping matters more than layout here. With fontconfig defaults (sans-serif → DejaVu Sans), rkhead scored 0.900, with dy median 9.3 px and 84% exact pages. Mapping `sans-serif`/`serif`/`monospace` to Chrome's Linux defaults (Liberation Sans/Serif, DejaVu Sans Mono) raised it to 0.929, with dy 0.7 px and 90% exact pages. **The product must ship a Chrome-equivalent default font mapping**; Takumi's adapter already did this.

## Per category (score: takumi / rkhead)

- **rkhead ahead:**
  - dashboards 0.845 / **0.967**
  - reports 0.929 / **0.967**
  - newsletters 0.764 / **0.814**
  - WeasyPrint samples 0.848 / **0.854**
- **Even:** invoices 0.994 / 0.982, contracts 0.969 / 0.960, long-form 0.987 / 0.979, WebSight 0.960 / 0.960.
- **Takumi ahead:**
  - data tables 0.977 / 0.860 (page-break agreement 98.4% vs 82.2%)
  - brochures 0.988 / 0.907
  - i18n 0.933 / 0.870
  - Vivliostyle samples 0.822 / 0.617

## Why rkhead stays the core

- **Overall:** near-tie with Chrome on agent documents (−0.011), while it leads by +26 points on WPT spec conformance and +3.8 on the production corpus.
- **Robustness:** no whole-document failures. Takumi fails on `blur()` filters and DOM depth over 512.
- **Cost:** 2.3× faster median, 2.7× less memory.
- **Agent feedback:** exposes per-page geometry, which Takumi does not.

## Added to the donor list

1. **Table pagination** (repeated thead, row splitting) to match Chrome: port from Takumi's LayoutNG-derived `layout/table/fragmentation.rs`.
2. **Brochure/i18n deltas:** inspect the 20 worst-case PNG pairs (artifact `print-oracle-rkhead`).
3. **Text precision** (96.8% vs 98.7%): find where rkhead emits duplicate text.
