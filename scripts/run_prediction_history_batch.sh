#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOCK_DIR="$PROJECT_ROOT/data/.prediction-history-batch.lock"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  print -u2 "prediction history batch already running"
  exit 75
fi
trap 'rmdir "$LOCK_DIR"' EXIT INT TERM

cd "$PROJECT_ROOT"
if [[ ! -x "$PYTHON" ]]; then
  print -u2 "missing project environment: $PYTHON"
  exit 1
fi

SINCE="2016-09-03"
UNTIL="2026-09-04"
BATCH_SIZE="5000"

for platform in kalshi polymarket; do
  "$PYTHON" src/backfill_prediction_market_history.py --since "$SINCE" --until "$UNTIL" \
    --platform "$platform" --classification hurricane_or_named_storm \
    --stage prices --max-contracts "$BATCH_SIZE"
done

for platform in kalshi polymarket; do
  "$PYTHON" src/backfill_prediction_market_history.py --since "$SINCE" --until "$UNTIL" \
    --platform "$platform" --classification hurricane_or_named_storm \
    --stage trades --max-contracts "$BATCH_SIZE"
done
