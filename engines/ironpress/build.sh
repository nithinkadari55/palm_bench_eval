#!/usr/bin/env bash
set -euo pipefail

NAME="ironpress"
ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM="$ENGINE_DIR/upstream"
ADAPTER="adapter-$NAME"

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

rm -rf "${UPSTREAM:?}/$ADAPTER"
cp -r "$ENGINE_DIR/adapter" "$UPSTREAM/$ADAPTER"

python3 - "$UPSTREAM/Cargo.toml" "$ADAPTER" <<'PY'
import re
import sys

path, member = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    text = f.read()

header = re.search(r"(?m)^\[workspace\][ \t]*(#.*)?$", text)
if header is None:
    text = text.rstrip("\n") + '\n\n[workspace]\nmembers = [".", "%s"]\n' % member
else:
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
            sys.exit(0)
        stripped = inner.rstrip()
        trailing = inner[len(stripped):]
        if stripped.strip() == "":
            new_inner = '"%s"' % member + trailing
        else:
            sep = " " if stripped.endswith(",") else ", "
            new_inner = stripped + sep + '"%s"' % member + trailing
        section = section[: m.start(1)] + new_inner + section[m.end(1):]
    text = text[:sec_start] + section + text[sec_end:]

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
PY

(cd "$UPSTREAM" && cargo build --release -p "$ADAPTER")

TARGET_DIR="${CARGO_TARGET_DIR:-$UPSTREAM/target}"
mkdir -p "$ENGINE_DIR/bin"
cp "$TARGET_DIR/release/$ADAPTER" "$ENGINE_DIR/bin/$ADAPTER"
