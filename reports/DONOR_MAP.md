# Donor Map: what each engine does better than our core (rkhead)

Source: per-test results from the final core run [44915583450](https://github.com/nithinkadari55/palm_bench_eval/actions/runs/44915583450). For every WPT reftest and corpus check that **rkhead fails**, this lists which engines pass it. That gives the list of algorithms to study or port into our fork.

- rkhead fails 6,160 of 14,883 reftests.
- **3,135 (51%) of those are passed by at least one other engine.** Ported, they would take rkhead from 58.6% to an upper bound of about 79.7%.
- Caveat: Blitz and raikiri pass some of these only in screen mode (for example fixed positioning relative to the viewport), so not all of them carry over to paged output.

## WPT donors

| Donor | rkhead-failing tests it passes | Where its advantage is (top areas) | How we use it |
|---|---|---|---|
| **raikiri's own painter** (screen) | 1,685 | CSS2 positioning 125, backgrounds 121, borders 104, background-size 104, normal-flow 62, css1 56, **css-break/grid 45**, floats-clear 41, linebox 29, **css-break/table 23** | Same layout engine, so the gap is in **fulgur-raikiri's krilla painter**. Port raikiri-paint's background/border/positioning painting into the PDF painter. Biggest, cheapest win. |
| **Blitz** | 1,832 | background-size 195, CSS2 positioning 159, backgrounds 131, **white-space 92**, normal-flow 83, borders 56, tables 50, visufx 44, floats 41 | Reference for backgrounds, borders and white-space (Stylo-correct behaviour). Algorithm reference only (Blitz has no pagination). |
| **Takumi** | 658 | **CSS2 tables 74**, **subgrid 35**, syntax 33, white-space 30, text 26, generated-content 19, grid-model 17, fonts 14, visudet 14 | Port table layout fixes, subgrid, and CSS syntax/generated-content handling. Also take its `ignored.rs` diagnostics. |
| **Fulgur (Blitz backend)** | 521 | white-space 73, grid-lanes 48, borders 26, subgrid 22, **css-break/flexbox 20**, text-box-trim 19 | Flexbox fragmentation and text-box-trim references. |
| **Ironpress** | 521 | grid-lanes (masonry) 86, **CSS2 tables 37**, white-space 33, fonts 11, grid alignment 9 | Table and white-space references. |
| fulraikiri (raikiri 0.0.6) | 67 | CSS2 borders 16, tables 6 | Regressions between 0.0.6 and HEAD: check these 67 tests in our fork. |

## Production-corpus donors (checks rkhead fails)

| Failing check | Who passes | Action |
|---|---|---|
| Bookmarks from headings (order, targets) | **Ironpress** | Port its outline generation, or build it on krilla's outline API. |
| `target-counter()` TOC page numbers | **Ironpress** | Port its two-pass page-reference resolution. |
| `position: fixed` repeats on every page | **Fulgur, Ironpress** | Port Fulgur's `bands.rs`-style per-page repetition. |
| `writing-mode: vertical-rl` in PDF | **Ironpress** (layout); Takumi/Fulgur (extractable text) | Fix vertical glyph emission in the painter. |
| 3D `rotateY` with perspective | Ironpress | Painter transform handling. |
| GCPM `bookmark-level`, `string-set`, PDF Author, `@layer`, `outline`, AVIF, hyphenation overflow, DOM depth > 512, Indic copy/paste, JS | **nobody** | Our own work (see the phase reports). |

## Fine-tuning plan (in order of payoff)

1. **Painter parity:** bring fulgur-raikiri's krilla painter up to raikiri-paint for backgrounds, borders, positioning and vertical text (about 1,000+ tests).
2. **Tables and subgrid:** Takumi, Ironpress and Blitz algorithms (about 200 tests).
3. **White-space / text:** Blitz and Fulgur behaviour (about 150 tests).
4. **Fragmentation:** css-break grid/table/flexbox from raikiri-screen, Fulgur and Takumi (about 90 tests).
5. **Paged-media features:** bookmarks, target-counter, fixed repetition (Ironpress, Fulgur), plus our own string-set, bookmark-level and metadata.

Every port is gated by re-running this bake-off: no regression allowed, and each targeted test must flip to PASS.
