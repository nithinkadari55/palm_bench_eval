# Phase 2: text and fonts

Measures each text/font building block of the browser-free HTML->PDF engine against an independent oracle. Every test writes `results/<test>.json` with `pass`, `fail`, `total`, `pass_rate`, `pass_criterion` and up to 20 `first_failures`. The workflow `.github/workflows/phase2-text.yml` runs everything on GitHub Actions (ubuntu-24.04). A summary job writes a markdown table to the run's step summary and uploads `phase2-results-all`.

## Layout

| path | content |
|---|---|
| `crates/shaping` | `shaping`: HarfRust 0.16.1 vs hb-shape |
| `crates/icu24` | `segmentation`: icu_segmenter 2.4.0; `bidi`: unicode-bidi 0.3.18 (hardcoded data and ICU4X data) |
| `crates/hyph` | `hyphenation`: hypher 0.1.8 vs pyphen |
| `crates/woff` | `woff`: wuff 0.2.10 decode, round-trip driver and robustness fuzzer |
| `crates/parley13` | `fallback` (fontique 0.13.0 + skrifa 0.50.0), `parley_layout` (parley 0.13.0), `bidi_parley` (parley_engine 0.13.0 resolver) |
| `scripts/` | Python helpers: corpus download, hb-shape oracle, HarfRust suite runner, hyphenation references and licence inventory, WOFF encode/compare, summary |
| `SOURCES.md` | every downloaded artifact with URL and licence |

The crates are independent packages, not one workspace: parley 0.13.0 requires `icu_segmenter ~2.3.0`, which cannot coexist in one lockfile with `icu_segmenter =2.4.0`. Separate packages also keep a compile failure in one test from blocking the others. All crate versions are pinned with `=`. No `Cargo.lock` is committed (no local toolchain); CI uploads each generated lockfile as the `phase2-cargo-lock-<group>` artifact.

## Tests and pass criteria

### 1. Shaping: HarfRust vs HarfBuzz (`shaping_apt.json`, `shaping_hb-matched.json`)
- Text: the first 50 `<title>`/`<para>` lines of UDHR translations (eng, fra, deu_1996, vie, arb, pes_1, urd, heb, hin, ben, tam, tel, guj, tha, khm, mya, sin, cmn_hans, cmn_hant, jpn, kor), plus every RGI emoji ZWJ sequence of Emoji 16.0 (one case per sequence).
- Fonts: Noto Sans/Serif per script, DejaVu Sans for Latin ligatures/kerning, Noto Nastaliq Urdu, Noto Sans/Serif CJK (TTC face selected by family name: SC, TC, JP, KR), Noto Color Emoji.
- Oracles: `hb-shape` 8.3.0 from apt `libharfbuzz-bin` (as requested), and `hb-shape` built from the HarfBuzz 15.2.0 release, the version HarfRust 0.16.1 states it matches. The 8.3.0 gap is large, so mismatches against apt alone can be HarfBuzz changes rather than HarfRust bugs; compare both files.
- Both shapers get the same font file, face index, text, ISO 15924 script, BCP 47 language and direction; `--font-funcs=ot`, default features, cluster level 0, UTF-8 byte clusters (`--utf8-clusters`, matching `Buffer::push_str`), font units (no scale).
- Pass: glyph count, glyph ids, clusters, x/y advances and x/y offsets all identical. `per_script` gives the exact-match rate per script; `mismatch_kinds` splits failures into glyph_count, glyph_id, cluster, advance, offset.

### 2. HarfRust's own test suite (`harfrust_suite.json`)
`cargo test --no-fail-fast` in a clone of harfbuzz/harfrust at tag 0.16.1 (SHA verified), as upstream CI runs it. Pass and fail are the summed `test result:` counts; ignored tests are reported separately. The full log is `harfrust_suite.log`.

### 3. Segmentation (`segmentation.json`)
icu_segmenter 2.4.0 ships Unicode 18.0.0 property data, but its constructors implement different rule versions: the stable `LineSegmenter` implements UAX #14 of Unicode 15.1.0, `*_17_*` implements 17.0.0, `*_neo_*` implements 18.0.0 (`unstable` feature); stable word and grapheme segmenters correspond to 17.0.0 and `*_neo` to 18.0.0. Each constructor is therefore run against its own test file and also against the 18.0.0 file:

| variant | test file |
|---|---|
| line stable | LineBreakTest 15.1.0 (raw, and with LB1 SA replacement as upstream does), 18.0.0 |
| line `_17_` | LineBreakTest 17.0.0 (raw and LB1 SA) |
| line neo | LineBreakTest 18.0.0 |
| word stable / neo | WordBreakTest 17.0.0, 18.0.0 / 18.0.0 |
| grapheme stable / neo | GraphemeBreakTest 17.0.0, 18.0.0 / 18.0.0 |

Pass: the full boundary list (byte offsets, including 0 and the end) equals the ÷ positions. ICU4X always reports a line boundary at 0 (ICU4X issue #3283), so 0 is added to the expected line breaks.

Tailorings that legitimately differ from the default rules and are therefore not exercised: CSS `line-break` strictness and `word-break` options, ja/zh content-locale line rules, and dictionary/LSTM segmentation of Thai, Lao, Khmer, Myanmar and CJK. The rule-based `*_for_non_complex_scripts` constructors with default options are used. They do not implement LB1 for SA characters, hence the `lb1sa` variants.

### 4. Bidi (`bidi.json`, `bidi_parley.json`)
- unicode-bidi 0.3.18 with its hardcoded data (Unicode 16.0.0) against BidiTest/BidiCharacterTest 16.0.0 and 18.0.0.
- unicode-bidi 0.3.18 with ICU4X Bidi_Class data (icu_properties 2.4.0, Unicode 18.0.0, `unicode_bidi` feature) against the 18.0.0 files. ICU4X has no bidi algorithm of its own.
- Parley's own resolver (`parley_engine::Analyzer`, `Analysis::bidi_levels`) against the 17.0.0 and 18.0.0 files. Parley performs L1 trailing-whitespace reset and L2 reordering inside line layout, so the harness applies L1 clause 4 and uses unicode-bidi's `reorder_visual` for order.
- BidiTest is evaluated for every paragraph level in the bitset (auto-LTR, LTR, RTL).
- Pass: levels equal at non-`x` positions, visual order equal with `x` positions dropped, and for BidiCharacterTest the paragraph level equal. `levels_pass_rate` and `reorder_pass_rate` are reported separately.

### 5. Hyphenation (`hyphenation_licences.json`, `hyphenation.json`)
- (a) Licences: the crates.io package excludes `patterns/`, so the inventory parses the `licence:` header of every `patterns/*.tex` in typst/hypher at the commit recorded in the package's `.cargo_vcs_info.json` (d81cc506). It maps each file to its hypher language through `tests/generate.rs`. A language fails (`flag: true`) when neither MIT nor Apache-2.0 is among its licence options. LPPL, MPL, GPL, LGPL, BSD, Unlicense, FSF all-permissive and custom texts are listed per language.
- (b) Quality: 10,000 lower-case alphabetic words of five or more letters per language (en, de, fr, es, it, pt, nl, ru), sampled deterministically from the Ubuntu hunspell dictionaries. The reference is pyphen 0.18.1, an independent Liang implementation, loaded with hypher's identical TeX patterns and the same left/right minimums (`hypher::Lang::bounds`). Pass: identical hyphenation points. Also reported: agreement, precision and recall against pyphen's bundled LibreOffice dictionaries (different pattern revisions), and the effect of hypher ignoring `\hyphenation{}` exception lists.

### 6. WOFF/WOFF2 (`woff.json`, `woff_robustness.json`)
- 31 system fonts: Noto, DejaVu and Liberation TrueType; CFF OpenType (URW base35, Cantarell, Inter, Noto Sans CJK face 0); the variable font InterVariable; and the CBDT Noto Color Emoji font. Each is encoded with fontTools to WOFF1, WOFF2 (glyf/loca transform) and, for glyf fonts, WOFF2 with the hmtx transform.
- wuff decodes each file in a child process. fontTools then compares the result with the original: table set (fontTools' WOFF2 encoder always drops DSIG, so that is allowed), RecordingPen outlines plus TrueType instructions for every glyph, every cmap subtable, and hmtx. Pass requires all four. Byte identity of all other tables and `head` (ignoring checkSumAdjustment and flags bit 11) is reported but does not gate.
- Robustness: deterministic truncations (about 30 cut points), 24 single-bit flips, 16 header-area bit flips and 8 byte bursts per encoded file, plus 220 garbage inputs (random, and random with `wOFF`/`wOF2` magic). Each runs in a child process under `ulimit -v 6000000` with a 20 s timeout. Strict pass: `Err`. Safety failures (panic, signal or abort, hang) are counted separately. A flipped bit inside compressed data may legitimately decode, which shows up as `ok`.

### 7. Font fallback (`fallback.json`)
For each sample, the chain is fontique's fallback family for (script, language) (the generic emoji family for emoji), then the generic sans-serif families. A character is covered if some font in the chain maps it (skrifa charmap of the family's default font). Default-ignorable code points and controls are not required. Pass and fail count (sample, distinct character) pairs. The report gives coverage percentages and the uncovered characters.

### 8. Parley line layout (`parley_layout.json`)
Each UDHR paragraph and emoji line is laid out at 160, 320 and 640 px, 16 px sans-serif, with the language locale set (parley `complex-scripts` enabled). Pass per (paragraph, width) requires all of:
- line text ranges tile the paragraph in order;
- the clusters of each line tile its range;
- no line's advance minus hanging whitespace exceeds the width by more than 0.5 px, unless the line has no internal soft-wrap opportunity (per `parley_engine::Analyzer`). Those lines count as unbreakable overflows: reported, not failed.

Also reported: `.notdef` glyph counts, and milliseconds per 1,000 paragraphs (build + `break_all_lines`, single thread, release build).

## Running locally (Linux)
```
pip install -r phase2_text/requirements.txt
python3 phase2_text/scripts/fetch_corpus.py --out phase2_text/data/corpus.json
cargo build --release --manifest-path phase2_text/crates/<crate>/Cargo.toml
```
Then follow the step order in the workflow.
