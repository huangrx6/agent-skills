#!/usr/bin/env sh
# Optional: install the preferred Markdown engine into this project's home.
# Without it, build_series.py falls back to a small built-in renderer.
set -eu

HOME_DIR="${AGENT_SKILLS_HOME:-$HOME/.agent-skills}"
VENV="${LEARNING_SCOUT_VENV:-$HOME_DIR/data/learning-scout/venv}"

mkdir -p "$(dirname "$VENV")"
if command -v uv >/dev/null 2>&1; then
  uv venv "$VENV"
  uv pip install --python "$VENV/bin/python" markdown-it-py mdit-py-plugins pygments
else
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet markdown-it-py mdit-py-plugins pygments
fi

"$VENV/bin/python" - <<'PY'
import markdown_it, pygments
print("ok:", "markdown-it-py", markdown_it.__version__, "| pygments", pygments.__version__)
PY
echo "venv: $VENV"
