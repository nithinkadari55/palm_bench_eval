# Phase 5: JavaScript runtime

Measures whether agent-written JavaScript can run before layout without a browser. The candidate runtime is **QuickJS-NG embedded through rquickjs**. It is compared with **boa_engine** (pure Rust) and with a **Node sidecar** (the same bundles on Node, plus JSDOM for DOM scripts) as the fallback baseline. The workflow `.github/workflows/phase5-js.yml` runs everything on GitHub Actions (ubuntu-24.04). The summary job writes the step summary and uploads `phase5-results-all`.

## Versions under test

| component | pinned version | where |
|---|---|---|
| rquickjs | 0.14.0 (`=0.14.0`, features `std`, `loader`) | `crates/qjs/Cargo.toml` |
| QuickJS-NG | commit 0fdea21 (2026-09-13; `quickjs.h` says 0.16.2), vendored by rquickjs-sys 0.14.0 | rquickjs repo commit d7ef5eea, submodule `sys/quickjs` |
| boa_engine | 0.22.0 (`=0.22.0`, default features + `annex-b` + `intl_bundled`) | `crates/boa/Cargo.toml` |
| boa_tester | Boa tag v0.22 (337a3668), its own `test262_config.toml` | workflow `conformance (boa-tester)` |
| test262 | 5ef1e5723be95296f36afb0386676fed0205869c (the submodule of QuickJS-NG 0fdea21) | workflow env `TEST262_SHA` |
| test262 for boa_tester | d86b2294eb0a17eaa281ff12c73c473ec864c72f (Boa v0.22's pin) | workflow env `BOA_TEST262_SHA` |
| Node | 24.22.1 | workflow env `NODE_VERSION` |
| npm packages | exact versions in `js/package.json`, full tree in `js/package-lock.json` | see SOURCES.md |

## Layout

| path | content |
|---|---|
| `js/src/shims.js` | Host-API shims and the case driver API (`__p5.start/status/tick/take`). It is loaded first in every engine, Node included. |
| `js/src/lib_*.js` | Library entries: `echarts`, `mathjax`, `chartjs`, `d3`, `dom` (linkedom + LLM-style scripts), `probe`, `sandbox` |
| `js/src/canvas_backend_js.js`, `canvas_adapter.js` | Recording Canvas2D. The JS backend (Node/Boa) mirrors the Rust backend in `crates/qjs/src/canvas.rs` rule for rule. |
| `js/src/layout_probe.js` | Wraps getBoundingClientRect/offset*/client*/scroll* to record what a DOM returns, or to answer from injected host boxes |
| `js/cases/*.mjs`, `js/cases/dom/*.js` | Case definitions. `node build.mjs` writes `dist/cases/<group>.json`. |
| `js/build.mjs` | esbuild bundles (IIFE, `platform=neutral`, `target=es2022`), case files, `dist/bundles.json` (sizes, sha256, licences) |
| `js/node_runner.mjs` | Node baseline. It uses the same shims, bundles and host loop. `--dom-impl jsdom` runs the DOM scripts on JSDOM. |
| `crates/common` | Engine-independent Rust code: case driver (`Host` trait), test262 metadata parser, crash-isolating supervisor, verdicts, aggregation |
| `crates/qjs` | `p5-qjs`: rquickjs host (limits, interrupt deadline, console sink, Rust recording canvas), test262 exec, two-pass layout prototype |
| `crates/boa` | `p5-boa`: boa_engine host (budgeted job executor, console sink, runtime limits), test262 exec |
| `scripts/` | `t262_config.py`, `run_cases.py`, `ablation.py`, `compare.py`, `boa_tester_summary.py`, `summarize.py` |

The crates are separate packages, not one workspace, so a compile failure in one engine does not block the other. No `Cargo.lock` is committed (there is no local toolchain). CI uploads each generated lockfile as `phase5-cargo-lock-*`.

## Host loop (identical in every engine)

`__p5.start(input)` calls the library's `run(input)`, which may return a promise. The host then repeats three steps: drain promise jobs (at most 1,000 per batch, 5,000,000 per case), check `__p5.status()`, and fire the next virtual timer with `__p5.tick()`. It stops when the case settles or a budget is hit. It finishes with `__p5.take()`, which returns the result, the shim usage counts and the diagnostics. Time is virtual. `vt` advances only when a timer fires, and every clock read adds 1 µs, so busy-wait loops end deterministically. Per-case resets restore the PRNG seed, the clock, the timers and the diagnostics.

## Tests and pass criteria

### 1. ECMAScript conformance (`test262_qjs.json`, `test262_boa.json`, `test262_intl402_*.json`, `test262_boa_tester.json`)
- **Harness:** one Rust harness for both engines (`crates/common/src/test262.rs`).
  - Every (file, mode) runs in a fresh runtime/context. `assert.js` and `sta.js` (plus `doneprintHandle.js` for async tests, plus the `includes:`) are evaluated first as separate global scripts.
  - Modes follow the flags: sloppy + strict by default; `onlyStrict`, `noStrict`, `raw` and `module` select one mode. Strict mode prepends `"use strict";`.
  - Modules use a file loader rooted at the checkout. `with {type:'json'}` imports are served as JSON modules.
  - `$262` provides `global`, `evalScript` (a native global-script eval), `gc`, `detachArrayBuffer` (native) and `createRealm` (throws).
- **Verdict** (test262 INTERPRETING.md):
  - Normal test: no uncaught error. Async test: `Test262:AsyncTestComplete` printed and no `AsyncTestFailure`.
  - Negative test: the declared constructor is thrown, and the `$DONOTEVALUATE` message must not appear.
- **Isolation:**
  - Workers are child processes that each take 200 tests. A crash marks the running test `crash`, and the worker restarts after it.
  - rquickjs stops a test with its interrupt handler after 10 s. The supervisor also kills a worker that is silent for 20 s (`timeout`). This is the only stop for Boa, which has no interrupt hook.
- **Selection:**
  - `test/built-ins`, `test/language`, `test/annexB` and `test/staging`, with QuickJS-NG's own `test262.conf` at 0fdea21: its 29 `=skip` features and its `[exclude]` list, which drops `staging/` except `explicit-resource-management/` and excludes `intl402/`.
  - The config is converted by `scripts/t262_config.py` from the copy inside the sha256-verified rquickjs-sys 0.14.0 crate. Boa runs the identical selection.
  - Features the harness cannot host (`IsHTMLDDA`, `cross-realm`, `import-text`, `import-bytes`), plus tests that use `$262.agent` or `$262.createRealm`, are skipped and counted under `harness:*`.
- **Reported:**
  - Pass rate per execution, `by_dir` (test/<a>/<b>), `by_dir3` and `by_feature`.
  - Top failure messages and the first 300 failures. The full list is in `*.failures.txt`.
  - For rquickjs, a harness check against QuickJS-NG's `test262_errors.txt`: listed failures reproduced, unexpected failures and unexpected passes.
- **Intl gap:**
  - `test/intl402` is run with every `Intl*` feature enabled (`--keep-intl`). QuickJS-NG has no `Intl` object, so the run measures the gap. `top_failure_messages` shows what fails.
  - Boa is built with `intl_bundled`, so its row shows what an ICU4X-backed Intl gives.
- **boa_tester:** Boa's own runner, ignore list and test262 pin. It is a reference number for Boa, not apples-to-apples with our harness.
- **Pass:**
  - rquickjs main run: pass rate ≥ 99.5% of executions.
  - Every unexpected failure, relative to `test262_errors.txt`, must be explained as a harness gap or a vendored-version difference.
  - Boa and intl402 are reported, not gated.

### 2. Real libraries in the embedded runtime (`cases_<engine>.json`, `outputs_*`, `compare.json`)
Bundles are built from npm at pinned versions. `dist/bundles.json` lists every bundled package with its version and licence.

| group | cases | input | output compared |
|---|---|---|---|
| echarts | 20 options: bar/stacked/horizontal, line/area/step+markLine, pie/rose, scatter+visualMap, radar, funnel, gauge, heatmap, treemap, sunburst, sankey, force graph (seeded random), boxplot dataset transform, candlestick + dataZoom, parallel | `echarts.init(null, null, {renderer:'svg', ssr:true})` → `renderToSVGString()` | SVG |
| mathjax | 100 TeX formulas (base, ams, newcommand, noundefined, color, boldsymbol, cancel, braket, mathtools, mhchem, amscd; one deliberately undefined macro) + 20 MathML | liteAdaptor, SVG output, `mathjax-newcm-font` with all 40 dynamic ranges bundled and `asyncLoad` a synchronous no-op | SVG (`mjx-container`) |
| chartjs | 10 types: bar, horizontal stacked bar, line (dash, tension), filled area, pie, doughnut, polarArea, radar, scatter (log y), bubble | Chart.js BasicPlatform on the recording Canvas2D: the Rust backend in rquickjs, the JS backend in Node/Boa | op stream (`[name, ...args]`, property sets as `['set', prop, value]`) and op counts |
| d3 | 10: bar+axes, time line, stacked area, donut, log scatter with symbols, treemap, pack, tree, chord, force (300 ticks) | D3 7 on linkedom | SVG `outerHTML` |
| dom | 5 LLM-style scripts: invoice (innerHTML + template literals + classList), KPI cards (createElement/dataset/append), TOC (querySelectorAll, ids, insertAdjacentHTML), product grid (`<template>` cloning, closest), locale report (style, toLocaleString, Date, Intl) | linkedom in the engine, and JSDOM 31 in Node | serialized document |

- **Comparison:**
  - Byte equality first.
  - Then structural equality after normalization: SVG/HTML tokens with sorted attributes, collapsed whitespace, numbers at 6 significant digits, and style declarations sorted with `#rrggbb`→`rgb()`.
  - Op streams use relative tolerance 1e-9.
  - Pairs: qjs↔node, boa↔node, qjs↔boa. For DOM also qjs-linkedom↔node-JSDOM and node-linkedom↔node-JSDOM, which separates DOM-implementation differences from engine differences.
- **Cost:**
  - Each group runs 3 times, one process per run, giving per-case ms, bundle load ms and process peak RSS (`wait4` ru_maxrss).
  - Every case also runs alone in its own process for per-case peak RSS. That is every case for qjs and Node, and the first 5 per group for Boa.
- **Pass:**
  - echarts, mathjax, chartjs and d3: 100% of cases normalized-equal between qjs and Node.
  - dom: qjs-linkedom byte-equal to node-linkedom. Differences to JSDOM are reported as findings.
  - The `report-locale` case is expected to differ on QuickJS-NG, because `toLocaleString` without Intl gives a different result.

### 3. Host-API shim completeness (`ablation_<engine>.json`, `probe` group)
`shims.js` implements the following:
- **Always replace the native API (determinism):**
  - `setTimeout`/`setInterval`/`setImmediate` on virtual time, with budgets of 10,000 pending timers, 100,000 callbacks and 1 h of virtual time.
  - `requestAnimationFrame` on a 16 ms virtual frame.
  - `console` → diagnostics (`__host_log` native sink, at most 1,000 entries kept).
  - `performance.now`.
  - Seeded `Math.random` (sfc32).
  - `Date` fixed at 2026-01-01T00:00:00Z plus virtual time.
- **Installed only when missing:** `queueMicrotask`, `atob`/`btoa`, UTF-8 `TextEncoder`/`TextDecoder`, `URL`/`URLSearchParams`, `structuredClone`, and an en-US `Intl` subset (NumberFormat, DateTimeFormat, Collator, PluralRules).

The ablation disables one shim at a time (`--shim-config '{"disable":[...]}'`). It runs on rquickjs for all five library groups, and on Boa for every group except mathjax (CI time). A shim is **needed** by a library when disabling it makes a case fail or changes its output. The baseline's usage counters show which shims each library calls at all. The `probe` group records which APIs each engine has natively.

**Pass:** every library group runs with the shim set, and the needed-by matrix is reported per engine.

### 4. Sandbox and limits (`cases_<engine>.json` groups `sandbox_limits`, `sandbox_escapes`; `compare.json` → `sandbox`)
Each case runs in its own process under `RLIMIT_AS` 4 GiB. Engine budgets are 5 s per case. rquickjs also gets a 256 MiB heap limit and a 1 MiB stack. The supervisor kills the process at 35 s.
- **24 limit cases:**
  - CPU: infinite loop, a loop that swallows the interrupt in `catch`, busy-wait on `Date.now`, ReDoS, a looping sort comparator.
  - Memory: memory bombs (arrays, Map, typed arrays, `Array.join` of 1e9 elements).
  - Stack: deep recursion, recursion that catches and retries, Proxy get recursion, `JSON.stringify` of a 1e6-deep object.
  - Strings: string doubling, `repeat(2**31)`.
  - Job and timer floods: promise floods (chain and fan-out), `queueMicrotask` flood, timer fan-out, `setInterval(0)`, rAF loop.
  - Other: `Atomics.wait` forever, canvas op flood, console flood.
  - **Pass:** the process exits normally, the result is one of the listed typed errors (`Timeout`, `OutOfMemory`, `StackOverflow`, `TimerBudget`, `JobBudget`, `CanvasBudget`, `RangeError`, ...), and the wall time is ≤ 15 s. A crash, a signal or a supervisor kill is a failure.
- **17 escape cases:**
  - `require('fs')`.
  - `import()` of `fs`, `std`, `os`, `qjs:std`, `qjs:os`, `file://` and `http://127.0.0.1:9/`.
  - A static `import` in a classic script.
  - `fetch` (a request is attempted only if `fetch` exists, and only to 127.0.0.1:9).
  - XHR/WebSocket/Worker, `process.env`, Deno/Bun/std/os globals, `std.loadFile`, `os.exec`, WebAssembly, and the Function-constructor global.
  - **Pass:** every result starts with `blocked` or `absent` (WebAssembly may be `present`; it is compute only). Node is run as an informational baseline: its `fetch`, `WebSocket` and `process.env` are reachable.
- **Supporting facts:**
  - rquickjs-sys compiles only `quickjs.c`, `libregexp.c`, `libunicode.c` and `dtoa.c`, not `quickjs-libc.c`, so std/os do not exist.
  - The case runner installs no module loader, so every `import()` is rejected.
  - Boa has no interrupt hook and no heap limit. Its CPU and memory cases are expected to end by kill or abort, which is a finding.

### 5. Determinism (`compare.json` → `determinism`)
Every library case runs 3 times, each run a fresh process. **Pass:** 3/3 identical outputs (sha256) for every case on every engine.

### 6. Layout feedback, exploratory (`layout_qjs.json`, `layout` group, `compare.json` → `layout_apis`)
`cases/dom/layout_feedback.js` reads `offsetHeight`, `getBoundingClientRect`, `scrollWidth`/`clientWidth` and takes decisions from them: equal-height cards, a wide/narrow class, a truncation flag and a label.
- The `layout` group records what each approach returns: linkedom (qjs, boa, node) and JSDOM (node). linkedom gives a zero rect and `undefined` for offset/client/scroll. JSDOM gives zeros.
- `p5-qjs layout` measures a two-pass prototype:
  - Pass 1 runs the script and logs the measured elements.
  - A stub layout in Rust (block boxes at 768 px, inline `width:` honoured, 8 px per character, 20 px lines) computes boxes, which pass 2 injects through the probe.
  - Pass 3 repeats the step to check stability.
- The prototype reports the time per pass, whether pass 2 changes the DOM, and whether pass 3 equals pass 2. No pass criterion.

## Running locally (Linux)
```
cd phase5_js/js && npm ci && node build.mjs && cd ../..
CARGO_TARGET_DIR=phase5_js/target cargo build --release --manifest-path phase5_js/crates/qjs/Cargo.toml
python3 phase5_js/scripts/run_cases.py --engine qjs --bin phase5_js/target/release/p5-qjs --groups echarts --reps 3 --work /tmp/p5 --out /tmp/p5r
```
Then follow the step order in the workflow.
