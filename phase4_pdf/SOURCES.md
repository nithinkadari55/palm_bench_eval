# Sources downloaded in CI

All downloads happen in `.github/workflows/phase4-pdf.yml` or in the scripts it calls. Nothing listed here is committed or redistributed. The fixtures are synthesised by the generator and by `scripts/prepare_assets.py`, so no third-party documents are used.

| what | URL | pinned | licence | used by |
|---|---|---|---|---|
| krilla 0.7.0 (version fulgur-raikiri pins) | https://static.crates.io/crates/krilla/krilla-0.7.0.crate (via cargo) | `krilla = "=0.7.0"` in `crates/k07/Cargo.toml`; MSRV 1.89 | MIT OR Apache-2.0 | generator, robustness |
| krilla 0.8.2 (latest release) | https://static.crates.io/crates/krilla/krilla-0.8.2.crate (via cargo) | `krilla = "=0.8.2"` in `crates/k08/Cargo.toml`; MSRV 1.92 | MIT OR Apache-2.0 | generator, robustness |
| rustybuzz 0.20.1 | https://static.crates.io/crates/rustybuzz/rustybuzz-0.20.1.crate | `=0.20.1` (the version krilla's `simple-text` feature uses) | MIT | shaping text into `KrillaGlyph`s |
| serde_json 1.0.154 | crates.io | `=1.0.154` | MIT OR Apache-2.0 | generator output |
| Transitive crates (pdf-writer, subsetter, skrifa, xmp-writer, png, zune-jpeg, ...) | crates.io | resolved by cargo; lockfiles uploaded as `phase4-cargo-lock-<k>` | per crate (krilla's dependency tree is MIT/Apache-2.0/Zlib/BSD) | krilla |
| veraPDF greenfield 1.30.3 installer | https://software.verapdf.org/releases/1.30/verapdf-greenfield-1.30.3-installer.zip | sha256 `b512bf24945503a33fc10738ecffc1f2dccaaf8593a448e94ee9ac86a9559a59` (released 2026-10-07; IzPack packs: 0 GUI, 1 CLI, 2 Documentation, 3 Sample Plugins, read from the installer's `resources/packs.info`) | GPL-3.0-or-later OR MPL-2.0 | veraPDF validation |
| Eclipse Temurin JRE | actions/setup-java (Adoptium) | `21.0.13+9` | GPL-2.0 with Classpath Exception | veraPDF |
| Noto COLRv1 emoji font | https://raw.githubusercontent.com/googlefonts/noto-emoji/f3ae03f5e9b3b8516fa151f7168159ca1a3e7515/fonts/Noto-COLRv1.ttf | commit f3ae03f5 (v2.051); sha256 `0ae57fe58645638523ba35f388d93739d292539a9acb84df5700c81b1e1a28d2`; tables COLR, CPAL, glyf | SIL OFL 1.1 (fonts/LICENSE in the same repository) | `text_emoji` (COLRv1) |
| pdfjs-dist | https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.4.299.tgz | `6.4.299` (exact in `js/package.json`; lockfile uploaded) | Apache-2.0 | PDF.js text extraction and rendering |
| @napi-rs/canvas | npm | `1.0.13` (exact; the platform binary package `@napi-rs/canvas-linux-x64-gnu` 1.0.13 comes from its optionalDependencies) | MIT | canvas for PDF.js under Node |
| Node.js | actions/setup-node | `22.23.4` (pdfjs-dist 6.4.299 requires node >= 22.13.0) | MIT | PDF.js |
| Python packages | https://pypi.org (pip) | fonttools==4.68.0, pillow==13.0.0, numpy==2.5.4, pypdf==7.0.0, pikepdf==10.17.0, pdfminer.six==20260107, pypdfium2==5.14.0 | fonttools MIT; Pillow MIT-CMU; numpy BSD-3-Clause (and bundled licences); pypdf BSD-3-Clause; pikepdf MPL-2.0 (bundles qpdf, Apache-2.0); pdfminer.six MIT; pypdfium2 Apache-2.0 / BSD-3-Clause (bundles PDFium, BSD-3-Clause) | assets, structure, navigation, text, rendering, subsetting |
| Ubuntu packages | Ubuntu 24.04 archive (apt on the GitHub runner) | versions recorded per run in `results/apt-packages-*.txt` | fonts-noto-core / fonts-noto-cjk / fonts-noto-color-emoji: SIL OFL 1.1; fonts-dejavu-core: Bitstream Vera / DejaVu licence; fonts-inter-variable: SIL OFL 1.1; colord-data (FOGRA39L_coated.icc CMYK profile): terms in `/usr/share/doc/colord-data/copyright`, copied to `results/colord-data-copyright.txt` and used only as a CI test input; poppler-utils: GPL-2.0-or-later; mupdf-tools: AGPL-3.0-or-later; time: GPL-3.0-or-later | fonts for the corpus, CMYK output intent, pdftotext, pdftoppm, mutool draw, peak RSS |

The PDF viewers and validators (poppler, MuPDF, PDFium, PDF.js, veraPDF) are CI-only test tools. They are not linked into or shipped with the engine.
