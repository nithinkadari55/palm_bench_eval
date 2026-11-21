#!/usr/bin/env bash
set -euo pipefail

NAME="rkhead"
ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM="$ENGINE_DIR/upstream"
ADAPTER="adapter-$NAME"

FULGUR_REPO="https://github.com/fulgur-rs/fulgur"
FULGUR_SHA="bd6222fe10c5e4278af385c9a78f3ea0d46f48b5"
FULGUR_CRATES=("fulgur-core" "fulgur-raikiri")

REPO="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo"])' "$ENGINE_DIR/ENGINE.json")"
SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha"])' "$ENGINE_DIR/ENGINE.json")"
APT_PACKAGES="$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1])).get("apt_packages", [])))' "$ENGINE_DIR/ENGINE.json")"

if [ -n "$APT_PACKAGES" ]; then
  sudo apt-get update -qq
  # shellcheck disable=SC2086
  sudo apt-get install -y $APT_PACKAGES
fi

if [ -d "$UPSTREAM/.git" ]; then
  if [ "$(git -C "$UPSTREAM" rev-parse HEAD)" != "$SHA" ]; then
    git -C "$UPSTREAM" fetch origin
    git -C "$UPSTREAM" -c advice.detachedHead=false checkout --quiet "$SHA"
  fi
else
  rm -rf "$UPSTREAM"
  git clone "$REPO" "$UPSTREAM"
  git -C "$UPSTREAM" -c advice.detachedHead=false checkout --quiet "$SHA"
fi

FULGUR_SRC="$(mktemp -d)"
trap 'rm -rf "$FULGUR_SRC"' EXIT
git init -q "$FULGUR_SRC"
git -C "$FULGUR_SRC" remote add origin "$FULGUR_REPO"
git -C "$FULGUR_SRC" fetch -q --depth 1 origin "$FULGUR_SHA"
git -C "$FULGUR_SRC" -c advice.detachedHead=false checkout -q FETCH_HEAD
if [ "$(git -C "$FULGUR_SRC" rev-parse HEAD)" != "$FULGUR_SHA" ]; then
  echo "fulgur checkout is not at $FULGUR_SHA" >&2
  exit 1
fi

for crate in "${FULGUR_CRATES[@]}"; do
  if [ -e "$UPSTREAM/crates/$crate" ] && [ ! -f "$UPSTREAM/crates/$crate/.from-fulgur" ]; then
    echo "$UPSTREAM/crates/$crate exists in raikiri; refusing to overwrite it" >&2
    exit 1
  fi
  rm -rf "${UPSTREAM:?}/crates/$crate"
  cp -r "$FULGUR_SRC/crates/$crate" "$UPSTREAM/crates/$crate"
  printf '%s %s\n' "$FULGUR_REPO" "$FULGUR_SHA" > "$UPSTREAM/crates/$crate/.from-fulgur"
done

cp -r "$ENGINE_DIR/overlay/." "$UPSTREAM/"

for crate in "${FULGUR_CRATES[@]}"; do
  if grep -nE '^[[:space:]]*raikiri-[a-z-]+[[:space:]]*=[[:space:]]*"' "$UPSTREAM/crates/$crate/Cargo.toml"; then
    echo "crates/$crate/Cargo.toml still depends on a published raikiri crate" >&2
    exit 1
  fi
  if grep -nE '\.workspace[[:space:]]*=[[:space:]]*true' "$UPSTREAM/crates/$crate/Cargo.toml"; then
    echo "crates/$crate/Cargo.toml still inherits from the fulgur workspace" >&2
    exit 1
  fi
done

rm -rf "${UPSTREAM:?}/$ADAPTER"
cp -r "$ENGINE_DIR/adapter" "$UPSTREAM/$ADAPTER"

python3 - "$UPSTREAM/Cargo.toml" "crates/fulgur-core" "crates/fulgur-raikiri" "$ADAPTER" <<'PY'
import re
import sys

path, members = sys.argv[1], sys.argv[2:]
with open(path, encoding="utf-8") as f:
    text = f.read()


def add_member(text, member):
    header = re.search(r"(?m)^\[workspace\][ \t]*(#.*)?$", text)
    if header is None:
        return text.rstrip("\n") + '\n\n[workspace]\nmembers = [".", "%s"]\n' % member
    sec_start = header.end()
    nxt = re.search(r"(?m)^\[", text[sec_start:])
    sec_end = sec_start + nxt.start() if nxt else len(text)
    section = text[sec_start:sec_end]
    m = re.search(r"(?ms)^[ \t]*members[ \t]*=[ \t]*\[(.*?)\]", section)
    if m is None:
        section = '\nmembers = ["%s"]' % member + section
    else:
        inner = m.group(1)
        if member in re.findall(r'"([^"]*)"', inner):
            return text
        stripped = inner.rstrip()
        trailing = inner[len(stripped):]
        if stripped.strip() == "":
            new_inner = '"%s"' % member + trailing
        else:
            sep = " " if stripped.endswith(",") else ", "
            new_inner = stripped + sep + '"%s"' % member + trailing
        section = section[: m.start(1)] + new_inner + section[m.end(1):]
    return text[:sec_start] + section + text[sec_end:]


for member in members:
    text = add_member(text, member)

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
PY

if command -v rustup >/dev/null 2>&1; then
  (cd "$UPSTREAM" && { rustup toolchain install || rustup show active-toolchain; })
fi

(cd "$UPSTREAM" && cargo build --release -p "$ADAPTER")

TARGET_DIR="${CARGO_TARGET_DIR:-$UPSTREAM/target}"
mkdir -p "$ENGINE_DIR/bin"
cp "$TARGET_DIR/release/$ADAPTER" "$ENGINE_DIR/bin/$ADAPTER"
