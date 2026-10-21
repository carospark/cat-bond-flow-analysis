#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOCK_DIR="$PROJECT_ROOT/data/.daily-non-artemis-pull.lock"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  # A lock left behind by a crashed run (for example the EDEADLK aborts that
  # macOS protected folders produce under launchd) would otherwise block every
  # later run forever. Treat the lock as stale when its recorded PID is gone.
  OWNER_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -n "$OWNER_PID" ]] && kill -0 "$OWNER_PID" 2>/dev/null; then
    print -u2 "daily non-Artemis pull already running (pid $OWNER_PID)"
    exit 75
  fi
  print -u2 "removing stale lock left by pid ${OWNER_PID:-unknown}"
  rm -rf "$LOCK_DIR"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    print -u2 "daily non-Artemis pull already running"
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

PULL_DATE="$(date +%F)"
"$PYTHON" src/pull_market_signals.py --as-of "$PULL_DATE" --metadata-only
"$PYTHON" src/pull_tier1_sources.py --as-of "$PULL_DATE" --source brookmont_ils_etf
