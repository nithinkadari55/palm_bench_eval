# Sources downloaded in CI

All downloads happen in `.github/workflows/phase5-js.yml` or in the tools it calls (npm, cargo). Nothing listed here is committed or redistributed. The bundles in `js/dist/` are build outputs uploaded only as CI artifacts. `dist/bundles.json` records each bundle's sha256 and the exact packages it contains.

## Test suites and reference sources

| what | URL | pinned | licence | used by |
|---|---|---|---|---|
| test262 | https://github.com/tc39/test262.git | commit 5ef1e5723be95296f36afb0386676fed0205869c (the submodule of QuickJS-NG 0fdea21; verified with `git rev-parse`) | BSD-3-Clause (Ecma International), https://github.com/tc39/test262/blob/main/LICENSE | test262 runs (rquickjs, boa), intl402 |
| test262 (Boa pin) | https://github.com/tc39/test262.git | commit d86b2294eb0a17eaa281ff12c73c473ec864c72f (`commit =` in Boa v0.22 `test262_config.toml`) | BSD-3-Clause | boa_tester reference run |
| rquickjs-sys crate (for `quickjs/test262.conf` and `quickjs/test262_errors.txt`) | https://static.crates.io/crates/rquickjs-sys/rquickjs-sys-0.14.0.crate | sha256 cee271d0eeba64f0915b846cb7ae02e16faf3dfdffdca91731101d9d30fe3423 (equal to the crates.io index `cksum`) | MIT (QuickJS-NG: MIT) | test262 config and expected-failure list |
| Boa repository | https://github.com/boa-dev/boa.git | tag v0.22 = 337a3668a0dc86dd401ea20906e782249a64a228 (verified) | MIT OR Unlicense | boa_tester (built from that tree; its dependencies are fetched by cargo, lockfile uploaded as `boa-upstream.Cargo.lock`) |

## Rust crates (crates.io via cargo; `=` pins in `crates/*/Cargo.toml`)

| crate | version | licence | notes |
|---|---|---|---|
| rquickjs | 0.14.0 | MIT | features `std`, `loader`. It pulls rquickjs-core 0.14.0 and rquickjs-sys 0.14.0. rquickjs-sys vendors QuickJS-NG at commit 0fdea21ff1090084e91dad812b343d92e79ba9d9 (rquickjs commit d7ef5eeae702fea24c03643064de454f1c1dd4b0, `sys/quickjs` submodule). QuickJS-NG is MIT (Bellard, Gordon, Noordhuis). |
| boa_engine | 0.22.0 | Unlicense OR MIT | features: default (`float16`, `xsum`, `temporal`) plus `annex-b` and `intl_bundled` (ICU4X data via boa_icu_provider; licence per its crate metadata, see the uploaded lockfile) |
| serde_json | 1.0.154 | MIT OR Apache-2.0 | all crates |
| transitive crates | per generated `Cargo.lock` | see the lockfiles uploaded as `phase5-cargo-lock-*` | |

## npm packages (registry.npmjs.org via `npm ci`; exact pins in `js/package.json`, full tree in `js/package-lock.json`)

Bundled into the engine scripts (read from each package's `package.json` by `build.mjs` into `dist/bundles.json`):

| package | version | licence | bundle |
|---|---|---|---|
| echarts | 6.1.0 | Apache-2.0 (embedded d3 portions BSD-3-Clause, per its LICENSE) | echarts |
| zrender | 6.1.0 | BSD-3-Clause | echarts |
| tslib | 2.3.0 | 0BSD | echarts |
| @mathjax/src | 4.1.3 | Apache-2.0 | mathjax |
| @mathjax/mathjax-newcm-font | 4.1.3 | Apache-2.0 per its package.json; the npm tarball contains no LICENSE file, and the glyph data derive from the New Computer Modern fonts, whose upstream licence is not verified here (open item) | mathjax |
| mhchemparser | 4.2.1 | Apache-2.0 | mathjax |
| chart.js | 4.6.1 | MIT | chartjs |
| @kurkle/color | 0.3.4 | MIT | chartjs |
| d3 (and d3-* modules) | 7.9.2 (modules as locked) | ISC (d3-ease: BSD-3-Clause) | d3 |
| linkedom | 0.18.15 | ISC | d3, dom |
| htmlparser2 | 10.1.0 | MIT | d3, dom (via linkedom) |
| css-select / css-what / nth-check / boolbase | 7.0.0 / 8.0.0 / 3.0.1 / 2.0.0 | BSD-2-Clause / BSD-2-Clause / BSD-2-Clause / ISC | d3, dom |
| domhandler / domutils / domelementtype / dom-serializer / entities | as locked | BSD-2-Clause / BSD-2-Clause / BSD-2-Clause / MIT / BSD-2-Clause | d3, dom |
| cssomnom | 0.1.12 | Apache-2.0 | d3, dom |
| html-escaper / uhyphen | 3.0.3 / 0.2.0 | MIT / ISC | d3, dom |

Used in CI but not bundled:

| package | version | licence | used by |
|---|---|---|---|
| jsdom | 31.0.1 | MIT (plus notices for its cdoublev/css derivation, CSSTree MIT and W3C Software and Document License data) | Node + JSDOM baseline (`node_runner.mjs --dom-impl jsdom`) |
| esbuild | 0.28.2 | MIT | bundling (`build.mjs`) |

The `licenses` table in `dist/bundles.json`, which is also copied to the results as `bundles.json`, is the authoritative per-run record. The rows above are what `build.mjs` reported locally on 2026-11-21.

## Tooling on the runner

| what | source | pinned |
|---|---|---|
| Node | actions/setup-node | 24.22.1 |
| Python | actions/setup-python | 3.12 (standard library only) |
| Rust | rustup stable on the runner | version printed in the logs. rustc ≥ 1.91 is required by boa_engine 0.22.0 and ≥ 1.87 by rquickjs 0.14.0 |
| C compiler for QuickJS-NG | ubuntu-24.04 gcc (cc crate) | runner image |
