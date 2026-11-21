# Phase 4: PDF output and validation

Tests the PDF writer of the chosen core. raikiri reaches PDF through `fulgur-raikiri`, which writes with **krilla**. fulgur pins `krilla = "0.7.0"`; the newest release is 0.8.2, so everything runs twice, once per version. Every test writes `results/<test>_<k07|k08>.json` with `pass`, `fail`, `total`, `pass_rate`, `pass_criterion` and `first_failures`. The workflow `.github/workflows/phase4-pdf.yml` runs on GitHub Actions (ubuntu-24.04). A summary job writes markdown tables to the run's step summary and uploads `phase4-results-all`.

## Layout

| path | content |
|---|---|
| `crates/k07`, `crates/k08` | Two packages that build the same sources against `krilla =0.7.0` and `krilla =0.8.2`. Each has the binaries `gen` (fixture corpus) and `robust` (robustness cases) |
| `crates/shared/gen.rs` | Generator CLI: `gen corpus`, `gen single`, `gen list` |
| `crates/shared/fixtures.rs` | The fixtures, written directly against krilla |
| `crates/shared/common.rs` | Asset loading, rustybuzz 0.20.1 shaping into `KrillaGlyph`s, tagging and drawing helpers |
| `crates/shared/compat07.rs`, `compat08.rs` | The only version-specific code: profile to `Configuration`, artifact tags, error formatting |
| `crates/shared/robust.rs` | Extreme-input cases. Each case runs in its own process |
| `scripts/` | Python drivers: asset preparation, veraPDF, text extraction, rendering, structure, navigation, perf, determinism, subsetting, robustness, summary |
| `js/` | PDF.js text extraction and rendering (pdfjs-dist 6.4.299 with @napi-rs/canvas 1.0.13) |
| `SOURCES.md` | Every downloaded artifact, with pin, checksum and licence |

The packages are separate, not one workspace, because a workspace cannot lock two krilla versions for the same source. `[[bin]]` paths point to `../shared/`, and a cargo feature (`k07` or `k08`) selects the compat module. Versions are pinned with `=`. No `Cargo.lock` is committed (there is no local toolchain); CI uploads each lockfile as `phase4-cargo-lock-<k>`.

## Corpus

Every fixture is tagged: text runs are `Span` marked content inside `P`/`H1`–`H3`/`TH`/`TD`/`Lbl`/`LBody`/`Link` elements, graphics and images are `Figure` with `/Alt`, and decorations are `/Artifact`. Every fixture also has a title, an author, `Lang en`, a fixed creation date (2026-01-02T03:04:05Z) and an outline. As a result, a profile refuses a fixture because of its content, never because tags or metadata are missing. Each fixture writes `expected.json`, the generator's own record of what it intended (texts, rects, targets, alt texts, scopes, reading order). The checks compare the PDF against that file.

| fixture | content |
|---|---|
| `text` | One page per script: Latin ligatures (DejaVu Sans `fi`/`ffi`/`fl`), Latin diacritics, Arabic (RTL), Devanagari (reordering, conjuncts), CJK SC/JP/KR (CFF faces from the Noto CJK TTC), and a variable font (Inter, `wght` 100/400/900 instances via `Font::new_variable`). Text is shaped with rustybuzz and drawn with `Surface::draw_glyphs`, the path a layout engine uses |
| `text_emoji` | The same emoji string in Noto Color Emoji (CBDT bitmap) and Noto-COLRv1 (vector COLRv1): skin tone, ZWJ family, flag |
| `vector_opaque` | Even-odd star, cubic circle, dashed quad with round caps, miter/round/bevel joins, opaque linear and radial gradients (pad), non-zero and even-odd clip paths, nested rotate/skew transforms, tiling pattern |
| `vector_transparency` | Fill and stroke opacity, gradient with stop opacity, all 16 blend modes, luminosity and alpha masks, an isolated group with opacity |
| `vector_postscript` | Sweep gradient, linear `Repeat`, radial `Reflect` (krilla needs PostScript functions for these) |
| `images_opaque` / `images_alpha` / `images_cmyk` / `images_16bit` | RGB PNG, grey PNG, RGB JPEG / RGBA PNG / CMYK (Adobe-inverted) JPEG / 16-bit RGB PNG |
| `navigation` | 6 pages labelled i, ii, 1, 2, 3, 4. Has an explicit XYZ link, a named-destination link and a URI link, each a tagged `Link` with `/Contents`; a 3-level outline; and the named destinations `chapter-1`, `chapter-2`, `appendix` |
| `structure` | 3 pages with H1–H3, P, a numbered L/LI/Lbl/LBody list, Table/THead/TBody/TR/TH(Column/Row scope)/TD, a Figure with Alt, a Link (OBJR), a `Lang fr` Span, header/footer `/Artifact` on every page, and page labels |
| `embedded_file` | `data.xml` with MIME type, description, date and `AFRelationship Data` |
| `page_sizes` | A4 portrait/landscape, Letter, Legal, 400x250, 72x72, 2000x300 |
| `pages_1`, `pages_10`, `pages_100` | 32 tagged text lines per page, running header/footer artifacts, one outline entry per page |
| `form_field` | **Not generated.** krilla 0.7.0 and 0.8.2 have no form/widget API: `AnnotationType` has the single variant `Link`. It is recorded in `generation_*.json` under `unsupported_features` |

Each fixture is written under every profile the krilla version offers:

| profile id | k07 (0.7.0) | k08 (0.8.2) | veraPDF flavour |
|---|---|---|---|
| `none` (PDF 1.7), `pdf20` (PDF 2.0, no validator) | yes | yes | - |
| `a1a` `a1b` `a2a` `a2b` `a2u` `a3a` `a3b` `a3u` `a4` `a4f` `a4e` | yes | yes | `1a` ... `4e` |
| `ua1` | yes | yes | `ua1` |
| `a1a+ua1`, `a2a+ua1`, `a3a+ua1` | not offered (one validator per document) | yes (`ConfigurationBuilder` takes one archival and one accessibility validator) | both |
| `ua2` | not offered | not offered | - |

Fixtures use `Surface::draw_glyphs` with glyphs shaped by rustybuzz. `cmyk_profile` comes from colord-data's `FOGRA39L_coated.icc` (CMYK, for PDF/A with CMYK images).

## Tests and pass criteria

### 0. Generation (`generation_*.json`)
Every fixture × profile. Pass: krilla returns the PDF, or refuses it with `KrillaError::Validation` (or `SixteenBitImage` / `Limit`). A refusal is krilla's documented contract for content the profile forbids. A panic, any other `KrillaError` or a missing asset fails. The report has the full matrix, every validation error string (with the validator that raised it in 0.8.2), and an index from refusal reason to fixture@profile.

### 1. veraPDF (`verapdf_*.json`)
veraPDF greenfield CLI 1.30.3 (installer zip pinned by SHA-256, IzPack auto-install, Temurin JRE 21.0.13+9). Each generated PDF is validated with `--flavour <claimed>` `--format json`, in batches of 25. If JSON parsing fails, the same batch is re-run with `--format xml` and parsed from that. Combined profiles are validated against both flavours.
- Positive pass: `compliant` is true for every claimed flavour. The report gives the profile × fixture matrix (`pass` / `fail` / `refused` by krilla / `error`) and failed-rule counts by specification, clause and test.
- Negative controls (pass = veraPDF reports non-compliant; `expected_rule_hit` checks that the expected clause is among the failures):
  1. A-2b `vector_transparency` with XMP `pdfaid:part` patched 2 to 1, validated as 1b (expects 6.4 transparency).
  2. The `none` output validated as 2b (expects 6.6.x metadata/identification).
  3. The A-2u `text` file with every `/ToUnicode` removed, validated as 2u (expects 6.2.11.7).
  4. The UA-1 `structure` file with `/StructTreeRoot` and `/MarkInfo` deleted, validated as ua1.
  5. The A-2b output patched to claim part 4, validated as 4 (expects 6.1.x header version).
  6. The A-3b `embedded_file` patched to claim part 2, validated as 2b (expects 6.8 non-PDF/A attachment).

### 2. Text extraction (`text_extraction_*.json`)
Every generated `text` and `text_emoji` PDF, all profiles (the profile changes whether krilla uses `/ActualText` spans). The extractors are pdfminer.six 20260107, `pdftotext` (poppler 24.02 from Ubuntu), PDF.js (pdfjs-dist 6.4.299 `getTextContent`) and pypdf 7.0.0. Pass: the page text equals the source string after collapsing whitespace runs. Each failure is also classified as `nfkc_whitespace`, `reversed` (visual-order RTL), `same_chars_other_order` (reordering), `empty` or `different`. The report gives exact-match rates per extractor × script, per extractor and per extractor × profile, plus the shaping statistics (glyphs, multi-char clusters = ligatures, multi-glyph clusters) for each sample.

### 3. Rendering (`render_*.json`, `render_failures_*/`)
Profiles `none,pdf20,a1b,a2b,a4,ua1`, first 3 pages of every generated fixture, 96 dpi. Viewers: `pdftoppm` (poppler 24.02), `mutool draw` (MuPDF 1.23.10), PDFium (pypdfium2 5.14.0 wheel), PDF.js 6.4.299 on @napi-rs/canvas. krilla has no rasteriser, so the reference is the per-pixel median of all viewers that rendered the page. Pass per viewer-page: at most 1% of pixels differ from the consensus by more than 48/255 (max channel, after a 3x3 box blur that absorbs anti-aliasing). A render error fails. For up to 80 failing viewer-pages, the viewer image, the consensus and a diff heat map are saved. Pairwise viewer disagreement counts are reported as well.

### 4. Structure and accessibility (`structure_*.json`)
Run on every generated PDF, with pikepdf 10.17.0 for the tree, pypdf 7.0.0 as an independent second walk, and pdfminer.six to map marked content to text. Checks:
- all fixtures: `/StructTreeRoot` and `/MarkInfo /Marked true`; catalog `/Lang en`; no text outside tagged or artifact marked content; pypdf and pikepdf produce the same role/depth/alt sequence; `/DisplayDocTitle` for PDF/UA.
- where defined: every `Figure` alt text, page labels, header/footer text only inside `/Artifact` on every page (and `/Subtype /Header` at PDF ≥ 1.7), and the `/Lang` of each script's paragraph.
- `structure`: all required roles present; `THead`/`TBody` kept; reading order (structure-tree DFS text sequence) equal to the generator's tagging order; TH `/Scope` Column/Row as intended; heading `/T` titles; the `Lang fr` span; each Link element has an OBJR whose annotation's `/StructParent` resolves to it through the ParentTree; `/StructParents` on every page.

The report gives per-check and per-profile counts and a check × profile matrix for `structure`. PDF 1.4 profiles are expected to lose THead/TBody (krilla falls back to `P`) and TH scope. That is reported as a failure, because it is a real accessibility loss.

### 5. Navigation (`navigation_*.json`)
Every generated `navigation` PDF, checked with pypdf 7.0.0 (pikepdf for XMP). Link `/Rect` must be within 1 pt of the intended rect. The URI action, the explicit `/XYZ` destination (page and top) and the named destination (resolved through `/Names /Dests` to page and top) must match, and so must the link's `/Contents`. The outline must match in titles, hierarchy, pages and tops. The registered named destinations must resolve. Page labels must be `i, ii, 1, 2, 3, 4`. The page size, the Info or XMP title and author, and the catalog `/Lang` must match. The URI link of `structure` is checked too.

### 6. Size, performance, determinism, subsetting
- `perf_*.json`: `gen single` in a fresh process, 5 repetitions, `/usr/bin/time` for peak RSS, krilla's in-process time for generation. Rows: `pages_1/10/100`, `text`, `vector_transparency`, `images_opaque` × `none/a2b/a4/ua1`. Bytes and bytes/page are also reported. Pass (pages_100 only): median ≤ 2000 ms and peak RSS ≤ 512 MiB.
- `determinism_*.json`: the whole corpus is generated a second time in another process with `TZ=Pacific/Kiritimati`, `LC_ALL=C.UTF-8` and a different working directory. Pass: every PDF is byte-identical. krilla reads no clock (verified in source), and the generator fixes all dates.
- `subsetting_*.json`: every embedded font program in `text`, `text_emoji`, `pages_100` and `structure` (selected profiles) is compared with the original face: bytes (TTC faces are measured by their own tables), glyph count and the presence of CIDSet. Type3 colour fonts are reported. Pass: every TrueType/CFF program is smaller than its original face.

### 7. Robustness (`robustness_*.json`)
48 cases, each in its own process under `ulimit -v 8000000` and a 240 s timeout. They cover 10k/100k-glyph runs, 10k `draw_glyphs` calls, a 10k-glyph TJ under PDF 1.4, a 1M-segment path, NaN/inf/1e30 coordinates, 0×0/0×100/negative/NaN/200k-pt pages, a zero-area media box, 16k×16k images (256 MiB grey `CustomImage`, 1 GiB `from_rgba8`, a PNG file), wrong-length image buffers, truncated/garbage/empty PNG and JPEG, garbage/truncated fonts, font sizes 0/−12/1e6/NaN, empty and out-of-range glyph runs, 1000 nested q/clip, 10k pages, 10k links on a page, a link to a missing page, misuse of tag identifiers and of start/end_tagged, a 40k-character title under PDF/A-2b, and an empty document. Pass: Ok or Err. A panic, signal/abort (including the memory limit), crash or hang fails. Cases whose panic krilla documents (API misuse: wrong-length `CustomImage`, link to a non-existent page, nested or unbalanced `start_tagged`) are marked `documented_panic` and listed separately from `undocumented_failures`.

## Running locally (Linux)
```
sudo apt-get install fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji fonts-dejavu-core fonts-inter-variable colord-data time poppler-utils mupdf-tools
pip install -r phase4_pdf/requirements.txt
curl -o Noto-COLRv1.ttf https://raw.githubusercontent.com/googlefonts/noto-emoji/f3ae03f5e9b3b8516fa151f7168159ca1a3e7515/fonts/Noto-COLRv1.ttf
python3 phase4_pdf/scripts/prepare_assets.py --out work/assets --colrv1 Noto-COLRv1.ttf --manifest work/assets/manifest.json
CARGO_TARGET_DIR=phase4_pdf/target cargo build --release --manifest-path phase4_pdf/crates/k07/Cargo.toml
phase4_pdf/target/release/gen corpus --manifest work/assets/manifest.json --out work/corpus
```
Then follow the step order in the workflow.
