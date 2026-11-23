# Phase 3: Images, Color, SVG

**Verdict: the blocks are usable. Two must be hardened (a corrupt-image crash path and AVIF) and two raikiri color bugs fixed. No new resource is needed.**

Evidence: CI runs [44920721167](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/44920721167) and [44922902310](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/44922902310) (oracle fixes).

| Block | Oracle / corpus | Result |
|---|---|---|
| PNG decode (`image` 0.25 / png 0.18, raikiri's stack) | PngSuite vs Pillow | **162/162 (100%)** |
| WebP decode (image-webp 0.2.4) | libwebp test vectors vs dwebp | **156/159 (98.1%)** |
| JPEG decode (zune-jpeg 0.5.15) | libjpeg-turbo testimages vs djpeg | 70/75 (93.3%). All 5 failures are **arithmetic-coded JPEGs** (unsupported; rare on the web). |
| GIF decode (gif 0.14) | GIF test set vs Pillow | 84/97 (86.6%). Failures are zero-size/no-data malformed files and multi-frame compositing. The first frame is what's used for PDF. |
| **EXIF orientation** (raikiri image path) | All 8 orientations | **34/34 (100%)** |
| **ICC → sRGB**: moxcms 0.8.1 (raikiri's CMS) | LittleCMS, mean/p95 ΔE2000 | **167/169 (98.8%)**. qcms 166/169. raikiri path 222/226. Gray and CMYK profiles are skipped by raikiri. |
| CMYK / YCCK JPEG | Pillow + LittleCMS | 18/28. Adobe CMYK OK. **YCCK fails** in both `image` and raikiri; the non-inverted synthetic cases are ambiguous. |
| AVIF (dav1d-native vs pure-Rust rav1d vs zenavif) | avifdec 1.0.4 | All three decoders agree with each other, and every one deviates from the old avifdec identically (chroma-upsampling oracle artifact). **Real gaps:** grid, multilayer and irot/imir/clap transforms are unsupported in the dav1d and rav1d paths. **zenavif is AGPL, so rejected.** |
| **SVG: resvg 0.48.1 (raikiri's renderer)** | resvg's own suite, its own rule | **1,730/1,730 (100%)** (0.45.1: 1,704/1,704) |
| SVG → PDF via krilla-svg 0.7 | Same refs, rasterized by poppler | Strict rule 587/1,689 (34.7%); SVG text 4/363. **Not the production path:** fulgur-raikiri paints raikiri's own vector scene. Phase 1 corpus SVG checks passed. |
| Raster images in krilla PDFs | PngSuite/JPEG vs decoded pixels | Structure (DCT pass-through, SMask alpha) 57/58. Pixel compare 6/60 is **inconclusive**: native and fulgur paths fail identically on PngSuite gradients (a resampling-oracle suspect). Phase 1 pixel probes on real images passed. |
| **Robustness**: corrupt inputs (5,850, child processes) | No panic/abort/hang | 5,791/5,850. **krilla's WebP path aborts with a 16 GB allocation on one corrupted header.** rav1d (pure-Rust AVIF) panics on corrupt files. |

## CSS color (raikiri-style's own parser vs colorjs.io)

| Category | raikiri | Best library (csscolorparser) |
|---|---|---|
| hex, rgb (legacy/modern), hsl, hwb, named, oklab, currentcolor, light-dark | **100%** | lower |
| In-gamut colors (all sources) | 1,509/2,347 | — |
| Out-of-gamut, CSS gamut-map oracle / per-channel clip oracle | 204/1,017 / **451/1,017** | — |
| **Overall** (gamut-map / clip oracle) | **53.6% / 60.3%** | 34.2% / 44.8% |

raikiri is the best candidate. Two real bugs:
1. `color(display-p3|a98-rgb|prophoto-rgb|rec2020|xyz …)` values are passed through unconverted (`color(xyz .3 .4 .5)` comes out as rgb(.3,.4,.5)).
2. `color-mix()` hue interpolation is wrong (`color-mix(in hwb, red, blue)` gives green).

raikiri resolves all colors to 8-bit sRGB, so there's no wide-gamut output. That's acceptable for PDF/sRGB.

## Actions (carried to the summary)

1. **Never hand untrusted image bytes to krilla's own decoders.** Decode through raikiri's guarded path (`image` + limits) and pass RGBA to krilla, as fulgur-raikiri already does. JPEG pass-through only after validating with zune-jpeg.
2. **AVIF:** use `image` avif-native (dav1d, BSD-2; mp4parse is MPL-2.0) inside the worker sandbox. Implement irot/imir/clap ourselves (a few lines on the decoded buffer). Grid/multilayer are a known gap.
3. **Fix the two raikiri color bugs** above (color() spaces through moxcms/`color` conversion; hue interpolation per CSS Color 5).
4. YCCK and arithmetic JPEG are rare: report them as unsupported-image diagnostics.
