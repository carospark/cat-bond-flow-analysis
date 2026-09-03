#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOCK_DIR="$PROJECT_ROOT/data/.daily-non-artemis-pull.lock"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  print -u2 "daily non-Artemis pull already running"
  exit 75
fi
trap 'rmdir "$LOCK_DIR"' EXIT INT TERM

cd "$PROJECT_ROOT"
if [[ ! -x "$PYTHON" ]]; then
  print -u2 "missing project environment: $PYTHON"
  exit 1
fi

PULL_DATE="$(date +%F)"
"$PYTHON" src/pull_market_signals.py --as-of "$PULL_DATE" --metadata-only
"$PYTHON" src/pull_tier1_sources.py --as-of "$PULL_DATE" --source brookmont_ils_etf
