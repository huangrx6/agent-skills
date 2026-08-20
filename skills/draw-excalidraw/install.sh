#!/usr/bin/env bash
set -Eeuo pipefail
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
DEST="$DSH_HOME_DIR/skills/draw-excalidraw"

echo "[draw-excalidraw] installing to $DEST"
mkdir -p "$DSH_HOME_DIR/skills"
if [ "$SRC_DIR" != "$DEST" ]; then
  rm -rf "$DEST"
  mkdir -p "$DEST"
  cp -R "$SRC_DIR"/. "$DEST"/
fi
cd "$DEST"
command -v node >/dev/null || { echo "Node.js >=20 is required" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }
npm install --omit=dev --no-audit --no-fund
node scripts/draw.mjs doctor
cat <<EOF

Installed.
DSH skill: $DEST/SKILL.md
Try:
  node "$DEST/scripts/draw.mjs" build --spec "$DEST/examples/architecture.json" --out /tmp/architecture.excalidraw --preview /tmp/architecture.svg

If DSH is already running, its skill watcher should normally pick up the new bundle. Restart dsh web if the catalog does not refresh.
EOF
