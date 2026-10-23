#!/usr/bin/env sh
# Optional: install the preferred Markdown engine into a local venv.
# Without it, build_series.py falls back to a small built-in renderer.
set -eu
cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
  uv venv .venv
  uv pip install --python .venv/bin/python markdown-it-py mdit-py-plugins pygments
else
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet markdown-it-py mdit-py-plugins pygments
fi

.venv/bin/python - <<'PY'
import markdown_it, pygments
print("ok:", "markdown-it-py", markdown_it.__version__, "| pygments", pygments.__version__)
PY
