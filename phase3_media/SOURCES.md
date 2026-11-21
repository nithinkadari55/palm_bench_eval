# Sources downloaded in CI

All downloads happen in `.github/workflows/phase3-media.yml` or in `scripts/fetch_corpus.py`. Git corpora are fetched as shallow, sparse checkouts of a pinned commit, and the script checks `HEAD` against the pin. Nothing listed here is committed or redistributed. Every file is used only as test input.

## Test corpora

| what | URL | pinned | licence | used by |
|---|---|---|---|---|
| PngSuite 2017jul19 (175 test PNGs, 14 intentionally corrupt `x*.png`) | http://www.schaik.com/pngsuite/PngSuite-2017jul19.tgz | sha256 `0294b244c95a8342c01b00010cf34abdcabc7c6a34fd0fe1bd963917537bfdc8` | PngSuite.LICENSE: "Permission to use, copy, modify and distribute these images for any purpose and without fee is hereby granted." (c) Willem van Schaik | raster_png, robustness, pdf_images |
| libjpeg-turbo `testimages/` (testorig, testimgint, testimgari = arithmetic, monkey12 = 12-bit, sources testorig.ppm, vgl_*.bmp, shira_bird8.bmp, test1/test3.icc) | https://github.com/libjpeg-turbo/libjpeg-turbo | tag 3.2.1 = `7b4993786d856cbccabfc0ed2f923ba000e326cc` | testimages/LICENSE.txt: testorig*/testimg* under the IJG License (README.ijg); test1.icc/test3.icc Little CMS (MIT); sRGB2014.icc embedded in some files ("may be copied, distributed, embedded, made, used, and sold without restriction"); other images BSD-3-Clause | raster_jpeg, robustness, icc (photo input, LUT profiles), pdf_images |
| libwebp-test-data (131 .webp: lossy, lossy+ALPH, VP8L lossless; no animated files) | https://github.com/webmproject/libwebp-test-data (mirror of https://chromium.googlesource.com/webm/libwebp-test-data) | `06ddd96e276c2c638a72d39d3c0f340afd61978c` | No LICENSE file. test_dwebp.sh: "distributed under the same terms as libwebp" (BSD-3-Clause). No explicit licence for the images; CI-only use | raster_webp, robustness, pdf_images |
| GIF test suite (84 tests with expected RGBA frames) | https://github.com/robert-ancell/pygif, `test-suite/` | `741b282047e0dde112e5ac2df0c7f8f923cb5df6` | test-suite/README.md: CC-BY-SA-4.0 (repository code LGPL-3.0) | raster_gif, raster_webp (gif2webp sources), robustness, pdf_images |
| image-gif samples | https://github.com/image-rs/image-gif, `tests/samples/` | `a5f89ddc2b29424334244c97456b4a26e208aa7d` | MIT OR Apache-2.0 | raster_gif, raster_webp, robustness, pdf_images |
| AVIF samples (8/10/12-bit, 4:2:0/4:2:2/4:4:4, alpha, monochrome, odd sizes, irot/imir/clap, ICC, animated .avifs) | https://github.com/link-u/avif-sample-images | `c666a368b73006246694919b5dbcc078317af6cc` | README.md: "Most images are licensed under CC-BY-SA 4.0"; plum-blossom and star CC-BY 4.0; red-at-12-oclock LGPL-2.1 or BSD-2-Clause | avif, robustness |
| AOMedia AVIF test files: `testFiles/{Microsoft,Apple,Netflix/avif,Netflix/avis,Xiph}` (grid, alpha, 10-bit, HDR PQ BT.2020, monochrome, multilayer, animated, non-compliant) | https://github.com/AOMediaCodec/av1-avif | `bf4c18d1f3971069b75e87d6ee469790589f4f09` | Root BSD-2-Clause (spec). Apple/: CC-BY-SA-4.0; Microsoft/: per-file attributions in ReadMe.md (Chimera CC BY-NC-ND 4.0, bbb CC-BY 3.0); Netflix/: CC BY-NC-ND 4.0; Xiph/: CC BY-SA 3.0 / CC BY 3.0 per COPYING. Non-commercial files are used only as unmodified CI test input | avif, robustness |
| EXIF orientation examples (Landscape/Portrait _0.._8) | https://github.com/recurser/exif-orientation-examples | `219294e144531b0c01247913cb58b6f5531b5081` | MIT ("Copyright (c) 2010 Dave Perrett") | exif_orientation, robustness |
| Compact ICC profiles (Adobe RGB compatible, Display P3, ProPhoto, Rec.2020, Rec.709/601, sRGB, sGrey, CGATS001 CMYK; v2 and v4) | https://github.com/saucecontrol/Compact-ICC-Profiles, `profiles/` | `bdd84663061bc4ae95ca70decff54f581e27f702` | readme.md: "released to the public domain under the Creative Commons CC0 license" | icc |
| CMYK / YCCK JPEGs: `ycck.jpg`, `mozilla/jpg-cmyk-1.jpg`, `mozilla/jpg-cmyk-2.jpg` | https://github.com/image-rs/jpeg-decoder, `tests/reftest/images/` | `eb2d7c0f6a2d0298aba7a7f8b9ca1440353e8f8c` | repository MIT OR Apache-2.0; the Mozilla reftest images come from mozilla-central image/test/reftest/jpeg and ycck.jpg from Wikimedia Commons (licences of those originals not verified); CI-only use | cmyk_jpeg, robustness, pdf_images |
| CMYK / YCCK JPEGs: `tree-cmyk.jpg`, `tree-cmyk-notransform.jpg`, `cmyktest.jpg`, `cmyk-grey.jpg` (progressive YCCK), `plusshelf-drawing.jpg` | https://github.com/jpeg-js/jpeg-js, `test/fixtures/` | `1031ccd7a63c641c16afb2430279d1598530a85c` | BSD-3-Clause | cmyk_jpeg, pdf_images |
| `pil_sample_cmyk.jpg` (YCCK) | https://github.com/python-pillow/Pillow, `Tests/images/` | `5cdbe88ccc3db2067235f6c22d553abb61654997` | MIT-CMU | cmyk_jpeg |
| `baseline_cmyk.jpg` (Adobe transform 0) | https://github.com/etemesi254/zune-image, `test-images/jpeg/app14/` | `692520ae7b6fb2098a25c7ee92521eda5b4425a9` | MIT / Apache-2.0 / Zlib | cmyk_jpeg |
| `xmp_test.jpg` (embedded Adobe RGB (1998) profile) | https://github.com/python-pillow/Pillow, `Tests/images/` | `5cdbe88ccc3db2067235f6c22d553abb61654997` | MIT-CMU | icc_raikiri |
| WPT `css/css-color/parsing/*.html` (literal arguments of test_computed_value / fuzzy_test_computed_color / test_valid_value / fuzzy_test_valid_color / test_invalid_value for `color`) | https://github.com/web-platform-tests/wpt | `9986bb32c9e97707eff870ab284ebc5cc7ae8d21` | BSD-3-Clause ("Copyright © web-platform-tests contributors") | css_color_* |
| resvg integration suite (SVG + reference PNG per test, fonts in tests/fonts with their own licences) | https://github.com/linebender/resvg | tag v0.48.1 = `68b14c4c3bccdb60344c777406486b54c36ec1a4` (full shallow checkout); tag v0.45.1 = `1b6c2fddbcbeffa8135df4323b02aaae84890907` (full checkout for the suite, sparse `crates/resvg/tests/**` for the PDF path) | Apache-2.0 OR MIT; test fonts under their own licence files (OFL/Apache) | svg_resvg_0.48.1, svg_resvg_0.45.1, svg_krilla_pdf_* |
| CMYK profiles `FOGRA39L_coated.icc` (default for CMYK JPEGs without a profile) and the other colord profiles | Ubuntu 24.04 package `colord-data` 1.4.7 (`/usr/share/color/icc/colord/`) | apt (version recorded in `results/apt-packages-color-images.txt`) | Debian copyright: data/profiles/* CC0-1.0; GRACoL/SWOP "CC0-1.0 and NPES" (CGATS characterization data must be identified as the source) | cmyk_jpeg, icc |
| icc-profiles-free (`/usr/share/color/icc/*.icc`, incl. Gray, compatibleWithAdobeRGB1998, sRGB) | Ubuntu 24.04 package `icc-profiles-free` 2.0.1 | apt | Zlib | icc |

## Oracles and tools

| tool | version / pin | licence | role |
|---|---|---|---|
| pypng | 0.20220715.0 (PyPI) | MIT | PNG oracle (pure Python, raw samples) |
| Pillow | 13.0.0 (PyPI wheel; bundles libjpeg-turbo, libwebp, libavif, LittleCMS 2) | MIT-CMU | primary AVIF oracle (bundled libavif), GIF/WebP-animation/JPEG sample oracle, LittleCMS (ImageCms) for CMYK and ICC |
| numpy | 2.5.5 | BSD-3-Clause | comparisons |
| pypdf | 7.1.1 | BSD-3-Clause | PDF structure checks |
| djpeg / cjpeg | Ubuntu 24.04 `libjpeg-turbo-progs` (2.1.5) | IJG / BSD-3-Clause / Zlib | JPEG oracle and variant encoder |
| dwebp / gif2webp | Ubuntu 24.04 `webp` (libwebp 1.3.2) | BSD-3-Clause | WebP oracle; animated WebP generator |
| avifdec | Ubuntu 24.04 `libavif-bin` (libavif 1.0.4) | BSD-2-Clause | secondary AVIF oracle (reference only when Pillow cannot decode) |
| libdav1d | Ubuntu 24.04 `libdav1d-dev` (1.4.1) | BSD-2-Clause | C AV1 decoder linked by image's `avif-native` |
| pdftoppm / pdftocairo | Ubuntu 24.04 `poppler-utils` (24.02) | GPL-2.0-or-later (tool only, not linked) | PDF rasteriser |
| colorjs.io | 0.7.1 (npm, `scripts/css/package.json`) | MIT | CSS colour oracle |
| Node.js | 22 (actions/setup-node) | MIT | runs colorjs.io |

Exact apt versions are written to `results/apt-packages-<group>.txt` in each run.
