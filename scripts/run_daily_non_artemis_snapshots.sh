#!/bin/zsh
# Nightly non-Artemis snapshot runner (LaunchAgent org.catbondflow.non-artemis-daily).
#
# Everything this script says goes to stdout, which launchd appends to
# data/daily-non-artemis-pull.stdout.log. The first line is written before
# anything can fail, so a night with no "start" line never ran at all, and a
# run that stops writes a "FAILED" line with its exit code and the step it was
# on instead of exiting silently. launchd's stderr pipe has not been reliable
# for these jobs (writes to it vanish, and a failed write under `set -e` once
# aborted the runner before it handled its lock), so stderr is folded into
# stdout first thing: Python tracebacks land in the same log as the runner's
# own lines, and every diagnostic print is non-fatal.
set -eu
exec 2>&1

JOB="daily non-Artemis pull"
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
LOCK_DIR="$PROJECT_ROOT/data/.daily-non-artemis-pull.lock"

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

PULL_DATE="$(date +%F)"

run_step() {
  # Each source is pulled even when an earlier one fails, so an offline
  # Kalshi scan no longer costs the night's ETF snapshot. Failures are
  # collected and reported together at exit.
  STEP="$1"; shift
  log "step start: $STEP"
  if "$@"; then
    log "step ok: $STEP"
  else
    local rc=$?
    warn "step FAILED (exit $rc): $STEP"
    FAILED_STEPS+=("$STEP")
  fi
}

run_step "market signals $PULL_DATE" \
  "$PYTHON" src/pull_market_signals.py --as-of "$PULL_DATE" --metadata-only
run_step "brookmont ETF snapshot $PULL_DATE" \
  "$PYTHON" src/pull_tier1_sources.py --as-of "$PULL_DATE" --source brookmont_ils_etf

STEP="summary"
if (( ${#FAILED_STEPS[@]} )); then
  exit 1
fi
