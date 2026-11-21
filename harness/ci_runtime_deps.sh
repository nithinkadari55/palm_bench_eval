#!/usr/bin/env bash
set -euo pipefail
engine="$1"
wpt="${2:-}"
pkgs="poppler-utils time fontconfig fonts-dejavu-core fonts-liberation fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji"
extra=$(jq -r '(.apt_packages // []) | join(" ")' "engines/${engine}/ENGINE.json")
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $pkgs $extra >/dev/null
if [ -n "$wpt" ] && [ -f "$wpt/fonts/Ahem.ttf" ]; then
  sudo mkdir -p /usr/share/fonts/truetype/ahem
  sudo cp "$wpt"/fonts/Ahem.ttf /usr/share/fonts/truetype/ahem/
fi
sudo fc-cache -f >/dev/null
python3 -m pip install -q --break-system-packages "numpy<3" "pillow>=11.3" pdfminer.six pypdf scikit-image beautifulsoup4 fonttools brotli
python3 -c "from PIL import features; print('avif', features.check('avif'), 'webp', features.check('webp'))"
