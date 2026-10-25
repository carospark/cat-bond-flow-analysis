# Handoff

Dated checkpoints for the analysis repository, newest first. The companion
parser's handoff is `../cat-bond-issuance/HANDOFF.md`; its `PARSER_BACKLOG.md`
is the parser's state. Data under `data/` and `raw/` is never committed; the
numbers below are read from the local outputs at the time of writing.

## Addendum (2026-10-25, afternoon): repository moved out of iCloud

Caro moved this repository from `~/Desktop/cat-bond-flow-analysis` to
`~/cat-bond-flow-analysis`. The parser stays at `~/Desktop/cat-bond-issuance`,
so the two are no longer siblings: pass
`--deals /Users/caropark/Desktop/cat-bond-issuance/data/deals.csv` where the
README writes `/path/to/deals.csv`, and read the manifest's
`../cat-bond-issuance/...` as that path.

Checked and done after the move:

- Git intact at 66da5ec on `main`; no iCloud xattrs on the new location;
  0 evicted files under `.venv/` and `data/raw/` (were 107 and 20).
- Both LaunchAgents re-installed from the new root with the two install
  scripts (plists now point at `/Users/caropark/cat-bond-flow-analysis`;
  launchd run counters reset to 0, stderr target refreshed). No lock
  directories were carried over.
- The venv's 14 console scripts, `pyvenv.cfg` and the editable-install
  record still embedded the Desktop path; rewritten in place
  (`./.venv/bin/pip` works again). Offline suite at the new path: 108 tests,
  OK.
- Daily job kickstarted under launchd from the new root: `start`, both
  steps `ok`, `finished ok`, exit 0, 13.5 minutes (the Polymarket scan is
  the slow part), lock released. Freshness check afterwards: all four daily
  sources at 2026-10-25; the batch rows still STALE at 2026-10-22.
- Batch job then kickstarted under launchd from the new root and left
  running: lock pid 79486, run 98 (discovery kalshi hurricane) complete,
  run 99 running. Stop it with `kill -INT <python pid>` followed by
  `kill -TERM <runner pid>` if it must not run in the daytime; it resumes
  from its checkpoints at 03:15.
- Parser golden suite still runs from the Desktop (2175/2175 in 22 s), but
  that repository is still iCloud-synced with 185 of 1,320 `raw/` pages and
  6,008 `.venv/` files evicted; reads materialise them online and fail
  offline. Moving it the same way is recommended before the offline golden
  runs are relied on.

## Checkpoint (2026-10-25): nightly jobs diagnosed, runners made loud, freshness check added

Diagnosis, from `data/*.log`, `launchctl print`, the batch's own `run_log`
table and two throwaway launchd probes (bootstrapped from the scratch folder,
run once, booted out):

- The archive held daily snapshots for 2026-08-30, 09-03, 09-14, 10-21,
  10-22 (Climate Central only; Kalshi and Polymarket failed on DNS, the
  laptop was offline, and the runner's `set -e` then skipped the ETF pull),
  10-23, 10-24 and 10-25. The daily job has run cleanly since the 2026-10-21
  stale-lock fix (launchd: 53 runs, last exit 0).
- The batch job (launchd: 54 runs, last exit 1) last did work on 2026-10-22
  (runs 89 to 95, 03:21 to 09:43 local; run 95 errored on DNS). Its lock
  `data/.prediction-history-batch.lock` survived with pid 46920, long dead,
  and every later night exited 1 without touching it or writing a line.
- Cause of the silent exit 1: the runner's very first write was
  `print -u2` to launchd's stderr pipe, and under `set -e` a failed write
  there exits the script before the stale-lock branch runs. Reproduced in a
  scratch copy of the old runner: with stderr unwritable it exits 1 and
  leaves the lock; with stderr open it clears the lock and proceeds. The
  real job's stderr is in fact dead: the batch stderr log was last written
  2026-09-18 and the daily one 2026-10-05, a kickstart of the real job today
  wrote nothing to it even from the new runner, while a freshly bootstrapped
  probe job writing to the same file succeeds. launchd keeps a stale stderr
  target for the long-lived job definitions; re-running the two install
  scripts would refresh it, but the runners no longer depend on it.
- `Resource deadlock avoided` (errno 11, EDEADLK) is iCloud, not TCC alone.
  `~/Desktop` is synced by iCloud Drive (xattr `com.apple.icloud.desktop`,
  File Provider domain) and 107 of 7,672 files under `.venv/` plus 20 of 292
  under `data/raw/` are currently evicted (size > 0, zero blocks), including
  `pandas/__init__.py`. The September tracebacks fail exactly on such reads
  (`urllib3/util/connection.py` at import, the certifi bundle inside an
  SSLError, the pull-log append). A launchd process that cannot get the file
  materialised gets EDEADLK. Today launchd's `/bin/zsh` reads the Desktop
  project fine (probe and real runs both confirm), so Full Disk Access is
  not the binding constraint at the moment.
- The 02:15 and 03:15 jobs actually start when the laptop wakes (06:37 on
  2026-10-25); nights it is asleep or offline still produce nothing.

Changes in this commit:

- `scripts/run_daily_non_artemis_snapshots.sh` and
  `scripts/run_prediction_history_batch.sh`: `exec 2>&1` first, a
  timestamped `start pid=` line before anything can fail, a `step start` /
  `step ok` / `step FAILED (exit N)` line per step, and an EXIT trap that
  writes `FAILED exit=N step="..." failed_steps=K [...]` on any non-zero
  exit (INT and TERM are turned into exits 130 and 143 so the trap runs).
  The lock is removed only by the run that holds it; a stale lock is cleared
  when its pid is dead; a live lock exits 75 with `skipped`. Steps no longer
  abort the night: the daily runner pulls the ETF snapshot even when the
  market scan fails, the batch runner records a class that fails twice and
  moves on, and both exit 1 at the end if anything failed.
- `scripts/check_snapshot_freshness.py` (10 tests in
  `tests/test_check_snapshot_freshness.py`): last snapshot date per nightly
  source (every market-signal source plus Tier 1 sources marked `daily`),
  last completed batch run per platform from `run_log`, age in days, lock
  state; exit 1 when anything is more than `--max-age-days` (default 2) old
  or has never been seen. Offline; `--as-of` for tests.
- README: the LaunchAgent paragraph now describes the logging contract, the
  freshness check, and the iCloud eviction mechanism beside the TCC one.
- Stale lock cleared by hand after re-checking pid 46920 was dead.

Verification: offline suite 98 -> 108 tests, all passing. Scratch harness
with a fake interpreter: stale lock + closed stderr -> cleared, exit 0; one
failing step -> other step still runs, `FAILED exit=1 ... failed_steps=1`,
lock removed; live lock -> exit 75, lock kept; batch with one class failing
twice -> 73 interpreter calls (72 steps + 1 retry), exit 1; TERM mid-step ->
`FAILED exit=143`, lock removed; old runner under the same closed-stderr
condition -> exit 1, lock left (the bug). Real job kickstarted twice under
launchd and interrupted: `start`, `step start`, Python output and traceback,
`FAILED exit=143 step="discovery kalshi hurricane_or_named_storm"` all in
the stdout log, lock removed, `launchctl` last exit 143, no leftover
processes. Those tests left `run_log` rows 96 (`interrupted`) and 97
(`running`, killed inside `store.summary()` after the discovery step had
completed; the backfill script computes its summary outside its try block,
which is a pre-existing gap).

Before and after: no data moved. Snapshot dates per daily source are
2026-10-25 for all four; the batch's last completed run is still 2026-10-22
for both platforms, so `check_snapshot_freshness.py` currently exits 1 with
those two rows STALE, which is the correct reading until tonight's 03:15 run
(or a manual `launchctl kickstart gui/$(id -u)/org.catbondflow.prediction-history-batch`).

What to move or grant (not done here): take the project out of the
iCloud-synced `~/Desktop` (for example `~/Projects/cat-bond-flow-analysis`,
then re-run both `scripts/install_macos_*.sh` so the plists point at the new
root), or exclude it from iCloud Drive / turn off "Optimize Mac Storage";
the EDEADLK failures will recur on any evicted file otherwise. Re-running the
installers also refreshes launchd's dead stderr target. If the snapshot
series matters, the machine has to be awake and online at 02:15 and 03:15,
or the jobs moved to a host that is.
