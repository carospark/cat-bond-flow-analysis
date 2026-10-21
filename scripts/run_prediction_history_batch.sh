#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOCK_DIR="$PROJECT_ROOT/data/.prediction-history-batch.lock"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  # A lock left behind by a crashed run (for example the EDEADLK aborts that
  # macOS protected folders produce under launchd) would otherwise block every
  # later run forever. Treat the lock as stale when its recorded PID is gone.
  OWNER_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -n "$OWNER_PID" ]] && kill -0 "$OWNER_PID" 2>/dev/null; then
    print -u2 "prediction history batch already running (pid $OWNER_PID)"
    exit 75
  fi
  print -u2 "removing stale lock left by pid ${OWNER_PID:-unknown}"
  rm -rf "$LOCK_DIR"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    print -u2 "prediction history batch already running"
    exit 75
  fi
fi
print $$ > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

cd "$PROJECT_ROOT"
if [[ ! -x "$PYTHON" ]]; then
  print -u2 "missing project environment: $PYTHON"
  exit 1
fi

SINCE="2016-09-03"
# A moving end date keeps the newest discovery window fresh each night;
# completed windows and contracts are skipped from the SQLite checkpoints.
UNTIL="$(date -v+1d +%F)"
BATCH_SIZE="5000"

# Every hazard class with a cat-bond counterpart. City temperature is
# discovered by the daily snapshot but its history is deferred.
CLASSES=(
  hurricane_or_named_storm earthquake severe_convective_storm wildfire
  winter_storm volcanic_eruption typhoon_or_cyclone precipitation windstorm
  pandemic_or_mortality disaster_declaration enso
)

run_step() {
  # One retry covers transient failures such as a macOS file lock during
  # import (EDEADLK), which otherwise aborts the whole nightly batch.
  if ! "$PYTHON" src/backfill_prediction_market_history.py "$@"; then
    print -u2 "retrying after failure: $*"
    sleep 30
    "$PYTHON" src/backfill_prediction_market_history.py "$@"
  fi
}

for stage in discovery prices trades; do
  for class in "${CLASSES[@]}"; do
    for platform in kalshi polymarket; do
      run_step --since "$SINCE" --until "$UNTIL" --platform "$platform" \
        --classification "$class" --stage "$stage" --max-contracts "$BATCH_SIZE"
    done
  done
done
