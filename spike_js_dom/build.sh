#!/usr/bin/env bash
# Prepares the raikiri workspace exactly like engines/rkhead/build.sh (raikiri at the rkhead
# pin as workspace root, fulgur-core + fulgur-raikiri from the same fulgur SHA, the rkhead
# overlay), then adds the spike crates as workspace members.
#   build.sh prepare           clone/copy only
#   build.sh build <crate>     cargo build --release -p <crate> and copy the binary to bin/
set -euo pipefail

SPIKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SPIKE_DIR/.." && pwd)"
RKHEAD="$ROOT/engines/rkhead"
UPSTREAM="$SPIKE_DIR/work/upstream"
MEMBERS=("crates/fulgur-core" "crates/fulgur-raikiri" "spike-rkjs" "spike-rkboa")
FULGUR_REPO="https://github.com/fulgur-rs/fulgur"
FULGUR_CRATES=("fulgur-core" "fulgur-raikiri")

REPO="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo"])' "$RKHEAD/ENGINE.json")"
SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha"])' "$RKHEAD/ENGINE.json")"
FULGUR_SHA="$(sed -n 's/^FULGUR_SHA="\([0-9a-f]\{40\}\)"$/\1/p' "$RKHEAD/build.sh")"
if [ -z "$FULGUR_SHA" ]; then
  echo "could not read FULGUR_SHA from engines/rkhead/build.sh" >&2
  exit 1
fi

prepare() {
  if [ -d "$UPSTREAM/.git" ] && [ "$(git -C "$UPSTREAM" rev-parse HEAD)" = "$SHA" ]; then
    git -C "$UPSTREAM" checkout -q -- . && git -C "$UPSTREAM" clean -qfdx -e target
  else
    rm -rf "$UPSTREAM"
    mkdir -p "$UPSTREAM"
    git -C "$UPSTREAM" init -q
    git -C "$UPSTREAM" remote add origin "$REPO"
    git -C "$UPSTREAM" fetch -q --depth 1 origin "$SHA"
    git -C "$UPSTREAM" -c advice.detachedHead=false checkout -q FETCH_HEAD
  fi
  test "$(git -C "$UPSTREAM" rev-parse HEAD)" = "$SHA"

  local fulgur_src
  fulgur_src="$(mktemp -d)"
  git init -q "$fulgur_src"
  git -C "$fulgur_src" remote add origin "$FULGUR_REPO"
  git -C "$fulgur_src" fetch -q --depth 1 origin "$FULGUR_SHA"
  git -C "$fulgur_src" -c advice.detachedHead=false checkout -q FETCH_HEAD
  test "$(git -C "$fulgur_src" rev-parse HEAD)" = "$FULGUR_SHA"
  for crate in "${FULGUR_CRATES[@]}"; do
    rm -rf "${UPSTREAM:?}/crates/$crate"
    cp -r "$fulgur_src/crates/$crate" "$UPSTREAM/crates/$crate"
  done
  rm -rf "$fulgur_src"
  cp -r "$RKHEAD/overlay/." "$UPSTREAM/"

  for crate in spike-rkjs spike-rkboa spike-common; do
    rm -rf "${UPSTREAM:?}/$crate"
    cp -r "$SPIKE_DIR/crates/$crate" "$UPSTREAM/$crate"
  done

  python3 - "$UPSTREAM/Cargo.toml" "${MEMBERS[@]}" <<'PY'
import re
import sys

path, members = sys.argv[1], sys.argv[2:]
text = open(path, encoding="utf-8").read()
m = re.search(r"(?ms)^\[workspace\].*?^members\s*=\s*\[(.*?)\]", text)
if m is None:
    sys.exit("no [workspace] members list in " + path)
inner = m.group(1)
have = set(re.findall(r'"([^"]*)"', inner))
add = [x for x in members if x not in have]
if add:
    stripped = inner.rstrip()
    sep = "" if stripped.endswith(",") or not stripped.strip() else ","
    new_inner = stripped + sep + "".join('\n    "%s",' % x for x in add) + "\n"
    text = text[: m.start(1)] + new_inner + text[m.end(1):]
open(path, "w", encoding="utf-8").write(text)
print("workspace members added:", add)
PY
  echo "raikiri $SHA, fulgur $FULGUR_SHA prepared in $UPSTREAM"
}

build() {
  local crate="$1"
  (cd "$UPSTREAM" && { rustup toolchain install >/dev/null 2>&1 || true; } && cargo build --release -p "$crate")
  local target="${CARGO_TARGET_DIR:-$UPSTREAM/target}"
  mkdir -p "$SPIKE_DIR/bin"
  cp "$target/release/$crate" "$SPIKE_DIR/bin/$crate"
}

case "${1:-}" in
  prepare) prepare ;;
  build) build "${2:?crate name}" ;;
  *) echo "usage: build.sh prepare | build <crate>" >&2; exit 2 ;;
esac
