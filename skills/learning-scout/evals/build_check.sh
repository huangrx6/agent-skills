#!/usr/bin/env sh
# Build assertion: the example must pass the quality gate and produce a linked hub.
set -eu
cd "$(dirname "$0")/.."
OUT="${TMPDIR:-/tmp}/ls-eval-build"
python3 scripts/check_notes.py --plan examples/series.plan.json
python3 scripts/build_series.py build --input examples/series.plan.json --out "$OUT" --force
test -f "$OUT/index.html"
test -f "$OUT/notes/01-先看一次真实失败.html"
test -f "$OUT/print.html"
grep -q 'href="notes/' "$OUT/index.html"
grep -q 'data-review-id' "$OUT/index.html"
echo "build check ok: $OUT"
