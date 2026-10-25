#!/bin/zsh
# Nightly prediction-market history batch (LaunchAgent
# org.catbondflow.prediction-history-batch).
#
# Everything this script says goes to stdout, which launchd appends to
# data/prediction-history-batch.stdout.log. The first line is written before
# anything can fail, so a night with no "start" line never ran at all, and a
# run that stops writes a "FAILED" line with its exit code and the step it was
# on instead of exiting silently. launchd's stderr pipe has not been reliable
# for these jobs (writes to it vanish, and a failed write under `set -e` once
# aborted the runner before it handled its lock), so stderr is folded into
# stdout first thing: Python tracebacks land in the same log as the runner's
# own lines, and every diagnostic print is non-fatal.
set -eu
exec 2>&1

JOB="prediction history batch"
LOCK_HELD=0
LOCK_DIR=""
STEP="startup"
FAILED_STEPS=()

stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { print -r -- "[$(stamp)] $JOB: $*" 2>/dev/null || true; }
warn() { log "$*"; }

on_exit() {
  local rc=$?
  if (( LOCK_HELD )); then rm -rf "$LOCK_DIR" 2>/dev/null || true; fi
  if (( rc == 0 )); then
    log "finished ok"
  elif (( rc == 75 )); then
    log "skipped: another run holds the lock"
  else
    warn "FAILED exit=$rc step=\"$STEP\" failed_steps=${#FAILED_STEPS[@]}${FAILED_STEPS:+ [${(j:, :)FAILED_STEPS}]}"
  fi
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

log "start pid=$$ host=$(hostname -s 2>/dev/null || print unknown)"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOCK_DIR="$PROJECT_ROOT/data/.prediction-history-batch.lock"

STEP="lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  # A lock left behind by a run that died without reaching its EXIT trap
  # (SIGKILL, shutdown, or the EDEADLK aborts that iCloud-evicted files
  # produce under launchd) would otherwise block every later run forever.
  # Treat the lock as stale when its recorded PID is gone.
  OWNER_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -n "$OWNER_PID" ]] && kill -0 "$OWNER_PID" 2>/dev/null; then
    warn "already running (pid $OWNER_PID)"
    exit 75
  fi
  warn "removing stale lock left by pid ${OWNER_PID:-unknown}"
  rm -rf "$LOCK_DIR"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    warn "already running (lock re-acquired by another run)"
    exit 75
  fi
fi
LOCK_HELD=1
print $$ > "$LOCK_DIR/pid"

cd "$PROJECT_ROOT"
STEP="environment"
if [[ ! -x "$PYTHON" ]]; then
  warn "missing project environment: $PYTHON"
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
  # import (EDEADLK), which otherwise aborts the whole nightly batch. A second
  # failure is recorded and the loop moves on, so one offline class no longer
  # costs the remaining classes; the run exits 1 at the end if anything failed.
  STEP="$1"; shift
  log "step start: $STEP"
  if "$PYTHON" src/backfill_prediction_market_history.py "$@"; then
    log "step ok: $STEP"
    return 0
  fi
  warn "retrying after failure: $STEP"
  sleep 30
  if "$PYTHON" src/backfill_prediction_market_history.py "$@"; then
    log "step ok after retry: $STEP"
  else
    local rc=$?
    warn "step FAILED (exit $rc): $STEP"
    FAILED_STEPS+=("$STEP")
  fi
}

for stage in discovery prices trades; do
  for class in "${CLASSES[@]}"; do
    for platform in kalshi polymarket; do
      run_step "$stage $platform $class" \
        --since "$SINCE" --until "$UNTIL" --platform "$platform" \
        --classification "$class" --stage "$stage" --max-contracts "$BATCH_SIZE"
    done
  done
done

STEP="summary"
if (( ${#FAILED_STEPS[@]} )); then
  exit 1
fi
