# Print-oracle corpus sources and licence decisions

All documents are generated or fetched at CI time (`build_corpus.py`) and are never committed. Public samples are fetched at pinned commits with `git fetch --depth 1 --filter=blob:none` and a sparse checkout. Rule: include a source only if its licence is stated clearly at that commit.

Every document then gets the same preprocessing, for Chrome and for every engine (`oracle_lib.prepare_html`):
- `<script>`, `<noscript>` and `<base>` removed.
- Remote `<link>`, remote `@import` and remote `url(...)` removed (they become `none`).
- Remote `<img src>` points at a local grey placeholder PNG.
- `<style id="print-oracle-default">@page{size:A4;margin:15mm}</style>` is inserted as the first child of `<head>`, so author `@page` rules still win.
- XHTML samples are converted to HTML (XML declaration dropped, non-void self-closing tags expanded) and saved as `*.po.html`.

## Included

| source | pinned commit | docs | licence |
|---|---|---|---|
| Generated (`gen_docs.py`, `gen_lib.py`, `gen_i18n.py`, `gen_parts.py`) | this repo | 300 | Our own synthetic content (CC0). Names, companies and numbers are random. |
| [CourtBouillon/weasyprint-samples](https://github.com/CourtBouillon/weasyprint-samples) | `6dc675b05a5cba59576dfaa8881ea6ccdccb13cc` | 5: invoice, letter, poster, report, ticket | README.rst, "License": "Everything else from the samples is in the public domain". The bundled fonts have their own licences: Source Sans 3, Pacifico, Fira Sans, Barlow Condensed, Libre Barcode 128 and Archivo Black are OFL-1.1; Coming Soon is Apache-2.0. They are used only for rendering in CI. |
| [pagedjs/pagedjs](https://github.com/pagedjs/pagedjs) `specs/` | `bbdc7519b458c400ed1880d9d692c9bf0b394a45` | 43 spec pages (list in `fetch_public.PAGEDJS_SPECS`): breaks, counters, margin boxes, named pages, page selectors, splits, strings, tables, target-counter, widows/orphans, footnotes, page sizes | MIT (`LICENSE.md`, Copyright (c) 2018 Adam Hyde). The Paged.js polyfill `<script>` is stripped, so both renderers see the plain print CSS. |
| [vivliostyle/vivliostyle_doc](https://github.com/vivliostyle/vivliostyle_doc) `samples/` | `7af9003bd803163ac45aa5c44278f8659ed965a5` | 8 | Repository `LICENSE` is 0BSD. Per sample: `gutenberg/Alice.html` (Project Gutenberg text, public domain); `wood/index.html` (R. J. Beedham, *Wood Engraving*, public domain); `shirouma/index.html` and `gon/index.html` (Aozora Bunko texts, public domain); `fixed-page-size/ja-horizontal/Takasebune/main.xhtml` (Mori Ōgai, public domain); `news/index.html` (Wikinews content, CC BY 2.5, as stated in the page); `scholarly/index.html` (Apache-2.0, `samples/scholarly/LICENSE`); `fixed-page-size/TheMalayArchipelago/main.xhtml` (Wikipedia-derived intro, CC BY-SA). |
| [HuggingFaceM4/WebSight](https://huggingface.co/datasets/HuggingFaceM4/WebSight) v0.1 | datasets-server rows API, train split, offsets 0, 997, 1994, … (same stride as `fetch_datasets.py`) | 100 | CC-BY-4.0. These are screen pages, printed here on A4 through the injected default `@page`. |

## Excluded

| source | reason |
|---|---|
| print-css.rocks ([zopyx/print-css-rocks](https://github.com/zopyx/print-css-rocks) @ `7d97ac55e6d7095f08981b444f69cac4856e92bf`) | No LICENSE file and no licence statement in README.md or README.rst. The only licence files in the tree belong to bundled third-party fonts and libraries, so the lesson content has no clear licence. |
| weasyprint-samples `book/` | README: "The text of the 'All Cats Are Beautiful' book is the full property of Madcats". |
| vivliostyle_doc `samples/webmag/` | The JBpress articles are "used with permission from Japan Business Press". That is permission for the sample, not a redistribution licence. |
| vivliostyle_doc `adaptive-layout/`, `niimi*/`, `gingatetsudo/`, `variable-page-size/`, `gutenberg/Fang.html` and `gutenberg/Sherlock.html` | Allowed by their licences but left out: `-epubx-*` adaptive-layout extensions that only Vivliostyle supports, EPUB packaging, near-duplicates of included samples, or very long runtimes (Sherlock is 600 KB of HTML). |
| vivliostyle.js and vivliostyle-cli test files | AGPL-3.0, which is incompatible with redistributing them as a test corpus. |
| pagedjs `examples/` and font-demo pages | Interactive viewers or font specimen pages, not print documents. |
| pagedjs specs `hooks`, `script-elements`, `infinite-loop`, `math/mathjax`, `filters/*`, `issues/*` | These need JavaScript, test the polyfill itself, or are degenerate cases. |
