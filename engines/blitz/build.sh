#!/usr/bin/env bash
set -euo pipefail

ENGINE=blitz
REPO=https://github.com/DioxusLabs/blitz
SHA=6636442d30ebe29289ebfbb8a3bf53ddfd640a0e

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM="$ENGINE_DIR/upstream"
MEMBER="adapter-$ENGINE"

sudo apt-get update
sudo apt-get install -y libfontconfig1-dev pkg-config

if [ -d "$UPSTREAM/.git" ] && [ "$(git -C "$UPSTREAM" rev-parse HEAD)" = "$SHA" ]; then
  echo "upstream already at $SHA"
else
  rm -rf "$UPSTREAM"
  git clone "$REPO" "$UPSTREAM"
  git -C "$UPSTREAM" checkout --detach "$SHA"
fi

rm -rf "$UPSTREAM/$MEMBER"
cp -r "$ENGINE_DIR/adapter" "$UPSTREAM/$MEMBER"

python3 - "$UPSTREAM/Cargo.toml" "$MEMBER" <<'PY'
import re
import sys

path, member = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    text = f.read()

ws = re.search(r'(?m)^\[workspace\]\s*$', text)
if ws is None:
    sys.exit("no [workspace] section in " + path)
nxt = re.search(r'(?m)^\[', text[ws.end():])
section_end = ws.end() + nxt.start() if nxt else len(text)
section = text[ws.end():section_end]

m = re.search(r'(?ms)^members\s*=\s*\[(.*?)\]', section)
if m is None:
    sys.exit("no members list in [workspace] of " + path)

entries = re.findall(r'"([^"]*)"', m.group(1))
if member in entries:
    print(member + " already a workspace member")
    sys.exit(0)

insert_at = ws.end() + m.start(1)
text = text[:insert_at] + '\n    "' + member + '",' + text[insert_at:]
with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
print("added " + member + " to workspace members")
PY

(cd "$UPSTREAM" && cargo build --release -p "$MEMBER")

mkdir -p "$ENGINE_DIR/bin"
cp "$UPSTREAM/target/release/$MEMBER" "$ENGINE_DIR/bin/$MEMBER"
