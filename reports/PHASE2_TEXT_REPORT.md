# Phase 2: Text and Fonts Building Blocks

**Verdict: ready. Every text block passes its official conformance oracle at or near 100%. The one open item is legal: hyphenation pattern licences.**

Evidence: CI run [44912553709](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/44912553709), raw JSON in `phase2-results-all`.

The chosen core (raikiri) builds its text stack (`shodo` 0.0.44) on exactly these blocks: harfrust, icu_segmenter/icu_properties, unicode-bidi, fontique, skrifa and wuff. Shodo's line layout itself is measured by WPT css-text in Phase 1 (73.2% on raikiri HEAD).

| Block (version tested) | Oracle | Result |
|---|---|---|
| **HarfRust 0.16.1** (shaping) | `hb-shape`: HarfBuzz 8.3.0 (apt) and 15.2.0 (built from the pinned release). UDHR text in 21 languages and 1,469 emoji ZWJ sequences. Compares glyph ids, clusters, advances and offsets. | **3,818/3,818 identical to both oracles (100%)**. Covers Arabic, Urdu Nastaliq, Hebrew, Devanagari, Bengali, Tamil, Telugu, Gujarati, Thai, Khmer, Myanmar, Sinhala, CJK, Hangul and emoji. 0 panics. |
| HarfRust upstream suite | `cargo test` on the full workspace | **7,434/7,434 pass** (16 ignored by upstream) |
| **icu_segmenter 2.4** (line/word/grapheme) | Official LineBreakTest / WordBreakTest / GraphemeBreakTest | `_17`/`neo` line segmenters 100% (17.0 / 18.0). Stable line segmenter 99.67% against its own 15.1 rules (34 cases) and 98.3% against 18.0. Word and grapheme 100%. |
| **unicode-bidi 0.3.18** (UAX #9) | BidiTest.txt + BidiCharacterTest.txt, all paragraph levels | **2,585,844/2,585,844 (100%)**, with both the built-in and ICU4X class data |
| Parley's bidi resolver | Same files | 1,723,896/1,723,896 (100%) |
| **fontique 0.13** (font fallback) | Every character of each sample covered by the resolved fallback chain (skrifa cmap) | **2,620/2,620 (100%)** across 22 scripts and emoji. 243 system families. |
| **wuff 0.2.10** (WOFF/WOFF2) | fontTools round-trip of 31 fonts (incl. CFF and a variable font): tables, every glyph outline, cmap, hmtx | **84/84 identical (100%)**. Corrupted inputs: 6,772 cases, **0 panics/hangs/aborts**. 17% of bit-flipped files decode without error, because the format has no checksum. |
| **hypher 0.1.8** (hyphenation) | pyphen's independent Liang implementation with identical patterns, 80k words in en/de/fr/es/it/pt/nl/ru | **80,000/80,000 identical**. 97.2% agreement with LibreOffice dictionaries. |
| Parley 0.13 (line layout, reference) | Lines tile the text in order, no line exceeds the width | 3,591/3,591. 0 notdef except 3 in Urdu. Tamil/Telugu long words overflow at 160 px (unbreakable without hyphenation). Mean 286 ms per 1k paragraphs. |

## Findings to act on

1. **Hyphenation licences (blocker for bundling):** 21 of 48 hypher languages have no MIT/Apache option. They include **en, nl, pt, ru**, plus af, bg, ca, el, gl, hr, hu, is, ka, ku, no, sa, sk, sr, sv, tr and uk (LPPL/GPL/MPL-style terms). Action: legal review, or ship only the 27 permissive languages, or source the en-US patterns separately (hyph-en-us is available under permissive terms).
2. **Version alignment:** raikiri HEAD locks harfrust 0.15 / icu 2.3 / fontique 0.11.1 / wuff 0.2.9. The tested versions are harfrust 0.16.1 / icu 2.4 / fontique 0.13 / wuff 0.2.10. Action: the core fork bumps to the tested versions, and Phase 1 is re-run after the bump.
3. **Line breaking:** use ICU4X's `_17`/`neo` line segmenter (100%) instead of the stable one (99.67%) where the API allows.
4. **Long-word overflow in Tamil/Telugu** needs hyphenation or `overflow-wrap`. The engine must report it (diagnostics).
5. **Urdu Nastaliq:** 3 glyphs had no fallback coverage. Add Noto Nastaliq to the bundled font set.
6. **Licence note:** raikiri depends on `cssparser 0.37` / `selectors 0.40`, which are MPL-2.0 (file-level copyleft). That's acceptable for commercial use, but they must be listed in the licence report.
