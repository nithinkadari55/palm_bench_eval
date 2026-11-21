# Phase 5: JavaScript Runtime

**Verdict: QuickJS-NG via rquickjs 0.14.0 is the runtime.** Boa is rejected for CPU/memory sandboxing and speed. A Node sidecar is rejected because it can't be sandboxed in-process (fetch, WebSocket and process.env are reachable).

Evidence: CI run [44919250015](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/44919250015).

| Test | **rquickjs / QuickJS-NG** | boa_engine 0.22 | Node 24 (baseline) |
|---|---|---|---|
| test262 (42,912 files, both modes, Intl excluded) | **81,869/81,992 = 99.85%**, 0 crashes | 80,065/81,979 = 97.67%, 13 crashes | (reference) |
| test262 intl402 | 1.9% (**no Intl object**) | 55.6% | full |
| ECharts 6 SSR SVG, 20 charts | **20/20 byte-identical to Node** | 20/20 | — |
| MathJax 4, 100 TeX + 20 MathML to SVG | **120/120 byte-identical** | 120/120 | — |
| Chart.js 4 on a Rust recording canvas, 10 types | **10/10 identical op streams** | 10/10 | — |
| D3 7 on linkedom, 10 visualizations | 9/10 byte-identical, **10/10 after float normalization** (1-ulp libm) | same | — |
| LLM-style DOM templating, 5 scripts | 4/5 (1 differs only through locale formatting, since there is no Intl) | 4/5 | — |
| Determinism, 3 runs | **100% identical** | 100% | 100% |
| Sandbox escapes (require, import, fetch, std/os, process, …) | **17/17 blocked** | 17/17 | **14/17** (fetch, WebSocket, env leak) |
| Resource limits (infinite loop, ReDoS, memory bombs, deep recursion, promise flood, timer bomb) | **24/24 contained**: 21 with the exact error class, 3 contained with a different error class | 12/24 (no interrupt hook: infinite loops can't be stopped in-process) | n/a |
| ECharts per chart / runtime load / peak RSS | 9.3 ms / 151 ms / **31 MB** | 54 ms / 1,253 ms / 196 MB | 11.6 ms / 74 ms / 110 MB |
| MathJax per formula / load / RSS | 2.6 ms / 301 ms / **69 MB** | 13.5 ms / 662 ms / 221 MB | 1.7 ms / 178 ms / 189 MB |

The two-pass layout-feedback prototype (run JS, lay out, answer `getBoundingClientRect`/`offset*`, re-run) is stable after pass 2.

## Gaps (our work, carried to the summary)

1. **Intl**: QuickJS-NG has none. Implement `Intl.NumberFormat`/`DateTimeFormat`/`PluralRules`/`Collator` and `toLocale*` on ICU4X (already in the stack) as host objects. Chart.js currently runs on an en-US shim.
2. **Real DOM binding:** today the tests use linkedom inside QuickJS (no geometry). Production needs a QuickJS binding to raikiri's DOM with synchronous layout queries. Raikiri has a Boa-based `raikiri-js` and OxidePage has a WebIDL→rquickjs generator; port one of these. This is the largest remaining JS work item.
3. **Host API shims:** virtual-time timers, rAF, microtasks, console→diagnostics, atob/btoa, TextEncoder, URL, structuredClone, a seeded Math.random and a fixed Date. These are implemented in the bench and must move into the engine.
4. **Hardening:** QuickJS-NG issues no CVEs and its C assertions abort. Run JS in a worker process with OS limits (the bench supervisor shows how). Map the OOM, `null`-throw and timer-bomb cases to typed errors.
5. **Canvas:** the Rust recording canvas covers Chart.js. Extend it to full Canvas2D, with a raster fallback for `getImageData`.
6. **Licence item:** `@mathjax/mathjax-newcm-font` ships without a LICENSE file (New Computer Modern glyph data). Confirm before bundling.
