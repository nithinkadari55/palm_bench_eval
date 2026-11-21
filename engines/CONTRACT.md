# Engine adapter contract

Every candidate engine gets a thin adapter binary in `engines/<name>/`: its own standalone Cargo project, with no shared workspace. The harness calls every adapter the same way. Adapters are built and run only in GitHub Actions on `ubuntu-24.04` with stable Rust.

## Build (adapter compiled inside the engine's own workspace)
The adapter must resolve dependencies exactly as upstream does: same Cargo.lock, same `[patch]` sections, same toolchain. So it is built as an extra member of the upstream workspace:
- `engines/<name>/ENGINE.json`: `{"name","repo","sha","commit_date","license","output":"pdf"|"png","supports":{...},"apt_packages":[...],"toolchain":"stable|<version>","notes":"..."}`.
- `engines/<name>/adapter/Cargo.toml` + `engines/<name>/adapter/src/main.rs`: package and binary name `adapter-<name>`. Engine crates are referenced by `path = "../<crate-dir>"`, relative to the upstream workspace root, because the adapter dir is copied to `<upstream>/adapter-<name>/`. Use `workspace = true` dependencies where the upstream workspace defines them. Extra dependencies (`serde_json` etc.) only if already in upstream's Cargo.lock, or the smallest standard crates.
- `engines/<name>/build.sh` (bash, `set -euo pipefail`, run from the repo root):
  1. Install the apt packages listed in ENGINE.json (`sudo apt-get install -y ...`).
  2. `git clone` the repo to `engines/<name>/upstream` and `git checkout <sha>` (skip if already present at that SHA).
  3. Copy `engines/<name>/adapter` to `engines/<name>/upstream/adapter-<name>`.
  4. Add `"adapter-<name>"` to `[workspace] members` in `upstream/Cargo.toml` with a small inline `python3` script (handle `members = [...]` across multiple lines; must be idempotent).
  5. Use the upstream `rust-toolchain.toml` if present (rustup picks it up automatically from the upstream dir).
  6. `cd upstream && cargo build --release -p adapter-<name>`. Do not use `--locked`, since the new member adds lock entries. Keep the upstream Cargo.lock otherwise.
  7. Copy the binary to `engines/<name>/bin/adapter-<name>`.

## Invocation

```
adapter-<name> render <input.html> <output> \
    --page-width-px <W> --page-height-px <H> --margin-px <M> \
    [--geometry <geometry.json>] [--diagnostics <diag.json>]
```

- `<input.html>` is a local UTF-8 file. Relative URLs (CSS `<link>`, `@import`, `url()`, `<img src>`, `@font-face src`) must resolve against the file's own directory as a `file://` base. Every resource lives on local disk; there is no network.
- **PDF-capable engines:** `<output>` ends in `.pdf`. Write a multi-page PDF. `W`, `H`, `M` (CSS px at 96/in) are the default page size and uniform margin; an author `@page` rule in the document overrides them when the engine supports `@page`.
- **Raster-only engines (no PDF backend):** `<output>` ends in `.png`. Render a single viewport-sized image of `W x H` CSS px at scale 1 (1 CSS px = 1 image px), white background, ignoring `M`. The harness uses these engines only for screen-mode tests.
- `--geometry`: if the engine exposes element geometry, write JSON: `{"pages":[{"index":0,"width":..,"height":..,"boxes":[{"node":"<id or tag#id.class>","tag":"div","id":"..","x":..,"y":..,"w":..,"h":..}]}]}` in CSS px with the origin at the page's top-left. If unsupported, write `{"unsupported": true}`.
- `--diagnostics`: if the engine reports warnings (unsupported CSS, ignored properties, overflow), write `{"warnings":[{"kind":"..","message":".."}]}`. If unsupported, write `{"unsupported": true}`.

## Exit codes and output
- 0 means success and the output file exists.
- 2 means the engine returned an error (message on stderr).
- Any panic must not be caught silently: let it exit non-zero (101 is fine).
- Write nothing to stdout except an optional final single-line JSON `{"pages":N}`.
- No interactive prompts, no network, no writing outside the given output paths.

## Fonts
Use the engine's default font discovery. CI installs `fonts-dejavu-core`, `fonts-liberation`, `fonts-noto-core`, `fonts-noto-cjk` and `fonts-noto-color-emoji`. If the engine can't use system fonts, load every font from `/usr/share/fonts` at startup, or document what it needs in ENGINE.json.
