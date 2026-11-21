# Phase 4: PDF Output and Validation (krilla)

**Verdict: ready. Use krilla 0.8.2** (fulgur-raikiri currently pins 0.7.0, so the fork bumps it). Every PDF/A and PDF/UA-1 file krilla emits is validated compliant by veraPDF, and the negative controls prove the validator really fails bad files. Remaining gaps are in what our engine must emit: ActualText for complex scripts, PDF/UA-2, and forms.

Evidence: CI run [44919224110](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/44919224110), all jobs green. 17 fixtures × 17 profiles, generated directly with krilla.

| Test | krilla 0.7.0 | **krilla 0.8.2** |
|---|---|---|
| Profiles offered | none, PDF 2.0, A-1a/b, A-2a/b/u, A-3a/b/u, A-4/4f/4e, UA-1 | same, **plus combined A-2a+UA-1 and A-3a+UA-1** (and A-1a+UA-1) |
| Generation (ok or documented refusal) | 224/224 (202 ok, 22 refused) | 272/272 (236 ok, 36 refused) |
| **veraPDF 1.30.3**: claimed flavour compliant | **170/170** | **238/238** |
| veraPDF negative controls fail as expected | 6/6 | 6/6 |
| Navigation: link rects ±1 pt, URI/GoTo/named dests, 3-level outline, page labels i, ii, 1…, title/author/lang | 100% | **304/304** |
| Structure/accessibility: StructTree, Lang, alt text, artifacts, reading order, parent tree | 99.6% | **1,480/1,484** (only PDF/A-1 drops THead/TBody and TH scope, which PDF 1.4 can't express) |
| Determinism: byte-identical across TZ/locale/cwd | 100% | **236/236** |
| Font subsetting: median embedded/original | 100% subset | **0.38%** of the original size |
| Performance | 100 pages ≈ 140 ms | 1 page 2.2 ms, 10 pages 15 ms, 100 pages ≈ 150 ms |
| Robustness: no panic on extreme input | 41/48 | 41/48 (the 7 panics are API misuse: 4 documented, 3 undocumented) |

Refusals are correct and documented: transparency is refused under PDF/A-1, PostScript-style gradients under A-1/2/3, and embedded files outside A-3/A-4f. Our engine must pick the profile and fall back (for example rasterize, or choose A-2u) or report it.

## Text extraction (copy/paste fidelity), krilla 0.8.2

| Script | pdfminer | pdftotext | pypdf | PDF.js |
|---|---|---|---|---|
| Latin ligatures/diacritics, CJK SC/KR, variable fonts, emoji (bitmap and COLRv1) | 100% | 100% | 100% | 100% |
| Japanese | 100% | 100% | whitespace only | 100% |
| **Arabic** | reversed order | different | reversed order | reversed order |
| **Devanagari** | different | 100% | different | different |

Arabic and Devanagari text is stored in visual glyph order, so extraction is wrong in 3 of 4 tools. **Fix (our layer): emit `/ActualText` spans for RTL and complex-script runs.** Krilla supports ActualText through tagging/spans.

## Multi-viewer rendering

mupdf and PDF.js agree with the median on 158/164 pages. Poppler and pdfium split 2-vs-2 against them on `vector_opaque` and some image pages (116/164). These are viewer anti-aliasing/stroke differences, not a krilla defect; no viewer failed to render anything.

## Gaps (carried to the summary)

1. **ActualText for Arabic/Indic** in the fulgur-raikiri emitter (copy/paste and accessibility).
2. **No PDF/UA-2** in any krilla version (UA-1 is fully supported).
3. **No AcroForm/widgets** (krilla only has link annotations). This only matters if HTML forms must become fillable PDF forms; not required by R9.
4. **No digital signatures** (not in requirements).
5. Validate API inputs before calling krilla: glyph text ranges and tag identifiers can panic on misuse.
