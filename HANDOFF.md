# Handoff

Dated checkpoints for the analysis repository, newest first. The companion
parser's handoff is `../cat-bond-issuance/HANDOFF.md`; its `PARSER_BACKLOG.md`
is the parser's state. Data under `data/` and `raw/` is never committed; the
numbers below are read from the local outputs at the time of writing.

## Checkpoint (2026-11-17): ETF month end reached, the 220 mark outliers read

Two of the open items from the 25 October list, both in this repository.

ETF reconciliation (`src/build_etf_flows.py`). The nightly job has run
across a month end: 19 observations 2026-08-27 to 2026-11-13 (was 6 to
2026-10-22), shares 4.75m -> 8.65m, implied creations $79.05m (was $41.5m).
The 31 October month end is covered (observation dated 30 October) but 30
September is not, so no month has both bounds and the reconciliation is
still `available: false`. The summary now reports
`snapshot_month_ends_covered` separately from `snapshot_months_covered`
and the reason distinguishes "one covered month end" from "none". First
full snapshot month: November 2026. First month both sources cover: November
2026, once the N-PORT filing for the quarter to 2026-12-31 is public (due by
early March 2027); EDGAR still lists five filings, latest period
2026-06-30. The 2026-11-06 pull is missing because the 2026-11-05 run slept
and finished at 10:05 on the 6th; both steps logged ok.

Deal-keyed mark outliers (`src/build_fund_holdings.py`). The 220 flagged
CUSIP-quarters were read against deal-mates, TRACE, the Artemis pages and
`losses.csv`; the classification table is in `data/MANIFEST.local.md`
("The 220 deal-keyed mark outliers, read 2026-11-17"). 190 of 220 are one
loss-affected class in a multi-class deal (90 with a `losses.csv` row, 72
with the loss on the Artemis page only, 28 with no loss record anywhere);
13 are zero-coupon discount classes priced below par at issue (Matterhorn
2020-4 B, Residential Re 2020-II 1 and 2023-II 2, Bonanza 2024-1 A, Hestia
2026-1 C); 15 are 10-to-28-point class divergences with no loss record; 1 is
a mark above par; 1 is a wrong bridge pair. No non-USD par, no fund-specific
pricing beyond one CUSIP-quarter, and TRACE staleness cannot cause a
mark-versus-mark gap. Two bridge pairs are wrong: 577092AR0 is Matterhorn Re
Argon 2022-1, not Matterhorn Re 2022-1 (strict, `high`, title "agrees" on
the series token alone); 747977AA4 is Queen Street 2023 Re DAC, not Montoya
Re 2022-2 (program bridge, nearest by date). Neither is corrected here.
`compare_marks_by_deal` gains `issuer_prefix_differs` (a CUSIP whose
six-character issuer prefix is the minority in its deal-quarter) with the
pairs listed in `fund_holdings_summary.json`; on the current data it flags
the Montoya / Queen Street pair and nothing else in 1,662 deal-quarters. The
Argon case shares its siblings' prefix and needs a program-name check in the
bridge.

Verification: offline suite 134 -> 136 tests, all passing (134 is what the
committed tree runs today; the 25 October checkpoint quoted 127 and the
difference is not traced here). `fund_holdings_summary.json` regenerated: every leaf unchanged apart
from the new `issuer_prefix_differs` block and the FX table path after the
repository move. ETF summary leaves that moved are the window, counts and
totals above plus the new field.

Left for Caro, unchanged: the bridge audit sample; the two wrong pairs above
are a bridge fix (program-name comparison for strict pairs, N-PORT title
against the program bridge's candidate) rather than a read; `losses.csv`
has no row for Caelus Re V 2017-1 and 2018-1, Residential Re 2015-I and
2016-I, Blue Halo 2016-1, FloodSmart Re 2021-1 and 2023-1, Mystic Re IV
2025-1, all carrying distressed marks.

## Checkpoint (2026-10-25, close of day): full regeneration after items 1 to 8

Every summary JSON and all six event checks were regenerated in one chain
from the committed code (parse_nport, build_bridge, extend_bridge,
resolve_ties_from_nport, build_deal_panel with and without
--high-confidence-only, build_fund_holdings, build_etf_flows, event_check for
Ian and Milton strict, --include-program with a 60-day pre-window into
event_checks/wide, and --high-confidence-only). No step failed. Each summary
was compared leaf by leaf with the copy saved before the chain ran. Both test
suites are green: flow-analysis 127 tests (98 at the start of the day),
parser 2227 checks (2175 at the start).

Numbers that moved in the flow-analysis summaries, with the cause:

| Summary | Number | Before | After | Cause |
|---|---|---:|---:|---|
| deal_panel_summary | market contracts | 6,467 | 10,129 | prediction-market database grew: the nightly batch ran again today (item 1), discovery through 2026-10-25 |
| deal_panel_summary | market contract-days | 104,300 | 121,141 | same |
| deal_panel_summary | class-region days | 19,071 | 20,115 | same |
| deal_panel_summary | market last date | 2026-09-14 | 2026-10-25 | same |
| deal_panel_summary | panel rows with same-class market activity | 6,323 | 6,326 | same |
| bridge_nport_summary | strict-bridge title agreement rate | 98.59% | 99.12% | stale output: the file predated the 2026-10-21 Galilei Re fix (18d4a1b); the three Galilei disagreements are gone, five remain (Sierra 2019-1 x2, Bonanza 2022-1, Merna Re II 2024-1 x2) |
| event_checks/wide (Ian, Milton) | deals by group, all deals | exposed 399, unexposed 162, other-hurricane 94, ambiguous 15 | 405, 164, 103, 16 | stale output: the wide runs predated the 2026-10-21 bridge rebuild (hazard map 634 -> 688 deals); the strict runs were already current |
| event_checks/wide (Ian) | other-hurricane deals both sides / median | 3 / -8.3 | 4 / -7.1 | same |
| bridge_program_summary | deals source path | ../cat-bond-issuance/... | /Users/caropark/cat-bond-issuance/... | repositories moved today |

Unchanged, leaf for leaf: bridge_summary (1,196 pairs, 700 deals; the
title-evidence counts from item 5 were already in the saved copy),
high_confidence/deal_panel_summary (468 deals, 50,608 trades),
fund_holdings_summary (2,398 mark pairs, median 0.24; 220 deal-keyed
outliers), processed/nport/summary (net flow by lineage as in item 4),
processed/brookmont_ils_etf/summary (6 observations, reconciliation not
available), the strict event checks (Ian exposed 10 at -3.7 vs unexposed 10
at -3.7; Milton 12 at +2.0 vs 6 at +0.2) and the high-confidence event
checks (Ian 10 at -3.7 vs 5 at -4.0; Milton 9 at +2.2 vs 4 at +0.3).

Numbers that moved today in the parser repository are in its HANDOFF.md
checkpoints: issuance vs publisher +3.80% -> +0.11% signed and 3.96% ->
0.55% summed absolute (item 2); outstanding vs publisher 2020-2026 from
-6.1/-5.5/-5.3/-7.4/-6.2/-4.9/-1.7bn to -4.7/-3.3/-2.5/-3.8/-2.2/+0.7/+4.1bn,
double subtraction alone 2.4 to 4.9bn (item 3); trigger-mix mean absolute
gap indemnity 3.4 -> 2.0pp.

Left for Caro: the folder move is done; `data/bridge_audit_sample.csv`
awaits a hand check; the nightly batch is running from the new root and
`scripts/check_snapshot_freshness.py` will show the two history rows go
green once it completes a run; the ETF reconciliation becomes possible only
after the nightly job has run across a month end and the September filing
is public.

## Checkpoint (2026-10-25): 663 versus 723 UN-CAT CUSIPs reconciled

No code change. Written to `data/MANIFEST.local.md` ("The 663 versus 723
UN-CAT count, reconciled 2026-10-25"). Short form: 663 is the strict
`debt_type_cd = 'UN-CAT'` count (5,236 records) and 723 is the wide ILS
screen (CAT family plus "Insurance Linked Security" descriptions without a
CAT code: 5,570 records); the 30 August audit paired the strict record count
with the wide CUSIP count and the 31 August audit says so and corrects it.
Both totals reproduce from the archived master file; one sub-statement of
the corrected audit ("123 CUSIPs" without a code; the file shows 85 on 182
records, 31 new) does not reproduce and is recorded, not explained. Of the
60 wide-only securities, 52 are in the strict bridge, 5 in the program
bridge, 56 traded; the 3 outside everything are not cat bond deals in the
directory.

## Checkpoint (2026-10-25, later still): ETF reconciliation made month-aligned

`src/build_etf_flows.py`:

- Observations are dated by the page's own `holdings_as_of` where present
  (`effective_date`, with `effective_date_source` saying which), not by the
  night of the pull; pulls that show the same as-of date collapse to one
  observation. All six distinct observations in the archive are dated this
  way (the 2026-10-24 and 2026-10-25 pulls both show 2026-10-22 and are
  one), so the series runs 2026-08-27 to 2026-10-22 with a 40-day gap, and
  the totals do not move: shares 4.75m -> 6.80m, net assets 95.6m -> 137.7m,
  implied creations $41.5m.
- `reconcile_with_nport` now aligns on calendar months. A month end is
  covered by the snapshots when an observation lies within 3 days of it; a
  month's snapshot flow is the change in shares between two consecutive
  covered month ends at the ending NAV; the N-PORT side is the fund's
  `net_flow` for the same month. Per common month it gives the signed error
  (snapshot minus N-PORT) against a stated tolerance of one creation unit
  (50,000 shares, the step every snapshot moves in) at NAV plus 1% of the
  filed flow. With no common month it returns `available: false` and the
  reason, which is the current state: N-PORT monthly flows run 2025-04-30
  to 2026-06-30 and no snapshot observation lies within 3 days of a month
  end (the nearest, 2026-08-27, is four days before August's), so even the
  September 2026 filing due in late November cannot reconcile a month until
  the nightly job has been running across a month end. The old function
  returned `available: true` with a total-against-total comparison over
  windows that did not overlap.
- Tests 123 -> 127; four mutations (dated by pull date, month-end tolerance
  ignored, tolerance band zero, non-consecutive month ends accepted) each
  turned the suite red.

## Checkpoint (2026-10-25, late): mark-versus-TRACE comparison rebuilt, deal-keyed check added

`src/build_fund_holdings.py`:

- Non-USD par is converted at the report month's monthly average rate from
  the parser's tracked `src/fx_monthly_usd.csv` (`--fx-table`, default
  `../cat-bond-issuance/src/fx_monthly_usd.csv`) before the mark is taken;
  `mark_basis` records `usd`, `fx_converted`, `fx_rate_missing` (mark null)
  or `currency_missing_assumed_usd`. In the archive every marked position is
  dollar-denominated: 14,505 `usd`, 72 with a blank currency code taken as
  USD and flagged, none converted, so the comparison's headline numbers do
  not move (2,398 pairs, median gap 0.24 points, 93.6% within 2, correlation
  0.967). The defect was latent; the guard is now tested.
- The 15-day window is split at the quarter end. Before: 1,631 pairs, median
  0.17, p90 0.92, p95 1.66, p99 10.1, 34 pairs over 5 points, 5 over 20.
  After: 1,296 pairs, median 0.35, p90 1.86, p95 3.61, p99 9.8, 44 over 5, 6
  over 20. 529 pairs have trades on both sides. Marks agree better with
  trades before the quarter end than after it, as a mark set from the last
  trade should. Both windows together: p90 1.37, p95 2.51, p99 10.07, max
  52.4; 62 pairs over 5 points, 25 over 10, 9 over 20.
- Staleness: 45.6% of pairs (1,094) have no trade within 7 days of the
  quarter end; the median distance to the nearest trade is 7 days. Stale
  pairs agree about as well as fresh ones (median 0.26 vs 0.22 points), so
  distance to the last trade is not what drives the tails.
- `compare_marks_by_deal` keys on the deal: for each held CUSIP its
  par-weighted fund mark is set against the par-weighted mark of the other
  CUSIPs of the same deal in the same quarter (`data/fund_marks_by_deal.csv`,
  3,811 rows over 1,662 deal-quarters with two or more marked CUSIPs; median
  gap 0.82 points, p95 29.8). The farthest CUSIP per deal-quarter is the
  candidate (`is_deal_outlier`): 220 CUSIP-quarters on 58 CUSIPs exceed 10
  points (146 on high-confidence pairs, 72 medium, 2 program; 144 with an
  agreeing title, 57 with none, 17 split). Every entry at the top of the
  table is a loss-affected deal whose tranches price apart on purpose:
  Caelus Re 2018-1 Class A at 93.5 against Class B at 0.26 (2025-04), the
  Residential Re 2016-1 and 2022-1 Class 10/11 notes near zero against their
  siblings in the nineties, Caelus Re V 2017-1 Class B, Pelican IV 2021-1
  Class A at 0.51 against Class B at 87.5. The screen therefore finds no
  wrong link at the top; a wrong link would show as a disagreement on a deal
  with no loss history, and the table is sorted so those surface next.
  Reading below the loss-affected deals is a follow-up for the audit sample.
- Tests 120 -> 123; four mutations (mark over local par, staleness never
  set, before and after windows swapped, every CUSIP an outlier) each turned
  the suite red.

## Checkpoint (2026-10-25, night): bridge audit counts, high-confidence-only runs, held-out sample

- `bridge_summary.json` now publishes, under `nport_title_evidence`, what the
  fund-reported titles did to the 1,196 strict pairs, and `bridge.csv`
  carries the class per pair in a new `title_evidence` column (every other
  column and the two unmatched tables are byte-identical to the previous
  build): 630 pairs built without any title evidence (`none`), 58 changed or
  split by a title (52 `split`, where the title decided between candidates,
  plus 6 `capped_not_in_directory`, kept at medium because the title names a
  series the directory lacks), 2 created by `_propagate_title_splits`
  (`propagated`), 503 confirmed by an agreeing title but not changed, 3 with
  a title and no deal series to compare. The 503 agreements are partly
  in-sample because the same titles feed the bridge.
- `--high-confidence-only` on `build_deal_panel.py` and `event_check.py`
  keeps strict pairs at high confidence only (no medium, low or program) and
  writes under `data/high_confidence/` and `data/event_checks/high_confidence/`.
  Panel: 624 -> 468 deals with trades, 1,028 -> 741 CUSIPs, 67,282 -> 50,608
  trades attributed (18,151 unattributed), 733 -> 538 bridged deals, 688 ->
  503 with a hazard map, 48,730 -> 35,740 panel rows (6,323 -> 4,551 with
  same-class market activity). Event checks, high-confidence only versus
  strict: Ian exposed 10 deals, median -3.7 points (unchanged); unexposed 10
  -> 5 deals, median -3.7 -> -4.0; Milton exposed 12 -> 9 deals, median +2.0
  -> +2.2; unexposed 6 -> 4 deals, median +0.2 -> +0.3. Neither reading
  changes; the unexposed groups thin out because the earthquake-only deals
  sit disproportionately at medium confidence.
- `src/draw_bridge_audit_sample.py` wrote `data/bridge_audit_sample.csv`
  (gitignored): 40 strict pairs, seed 20261025, all 4 low-confidence pairs,
  20 high and 16 medium spread over four issue-year buckets in proportion to
  each stratum (high: 4 to 2012, 3 in 2013-2017, 4 in 2018-2021, 9 from
  2022; medium: 5, 2, 4, 5). Title evidence in the sample: 20 agrees, 18
  none, 2 split. Every evidence column is included; `audit_verdict` and
  `audit_notes` are empty and are Caro's to fill. Not scored here.
- Tests 113 -> 120 (`tests/test_bridge_audit.py`); five mutations (split
  classed as agreement, propagated not counted, medium let through the
  high-confidence filter, event-check flag ignored, sampler seed ignored)
  each turned the suite red.

## Checkpoint (2026-10-25, evening): N-PORT flow audit

Three defects in `src/parse_nport.py`, fixed and mutation-tested:

- Sign. The parser took the absolute value of every negative flow field. The
  raw signs of all 396 flow rows in the 132 archived filings were tabulated:
  Stone Ridge (both funds), Pioneer CAT Bond (predecessor) and City National
  Rochdale reported redemptions as negatives through the 2024-01-31 report
  period and positives from 2024-04-30; Pioneer ILS Interval did so only from
  2022-01-31 to 2024-01-31; Brookmont and Victory Pioneer CAT Bond never.
  Those five ranges are now `config/nport_sign_conventions.json` (tracked,
  with the evidence), and the sign is flipped only inside them. Every raw
  value is kept (`sales_raw`, `reinvestment_raw`, `redemption_raw`). A value
  the table does not explain is left null and flagged: 4 City National
  Rochdale months with negative sales (`sign_unexpected_sales`), 6 Stone
  Ridge months with reinvestment of a few dollars negative
  (`sign_unexpected_reinvestment`, outside net flow anyway), and one SRRIX
  month (2023-04-30 filing, month 2) with a $0.28 positive redemption inside
  the negative range (`redemption_sign_conflict`). 126 rows carry
  `redemption_sign_flipped` (was 132 `sign_flipped`, which also counted the
  unexplained negatives it had silently flipped).
- Missing components. `net_flow` is null when sales or redemption is absent,
  conflicting or unexplained, and `net_flow_basis` names the reason
  (`sales_minus_redemption` otherwise). No archived filing lacks an
  attribute; the five nulls today are the CNR sales and the SRRIX conflict.
- Amendments. The puller listed only `NPORT-P`, so amendments never reached
  the archive; it now keeps `NPORT-P/A` too and records `form`. EDGAR holds
  three for these funds, all archived today: Pioneer ILS Interval 2022-01-31
  (filed 2022-07-18) and Pioneer CAT Bond 2023-07-31 and 2023-10-31 (both
  filed 2024-03-12). For each (fund, period) the latest filed accession
  stands; the others are listed in `superseded_filings` in `summary.json`.
  All three amendments are identical to their originals in net assets, every
  flow attribute, every return and the holdings count, so nothing downstream
  moves; `fund_holdings_by_deal`, the quarterly holdings, the mark-vs-TRACE
  comparison and the ETF reconciliation were rebuilt and their summaries are
  unchanged key for key.

Net flow by lineage, 2019-08 to 2026-07, $m, before -> after (lineage from
the registry's `successor_id`: the Pioneer CAT Bond predecessor rolls into
Victory Pioneer CAT Bond):

| Lineage | Before | After | Months without net flow |
|---|---:|---:|---:|
| Stone Ridge Reinsurance RRP Interval (SRRIX) | -4,049.7 | -4,057.2 | 1 |
| Stone Ridge High Yield RRP (SHRIX) | +3,324.5 | +3,324.5 | 0 |
| Victory Pioneer CAT Bond lineage | +2,107.2 | +2,107.2 | 0 |
| Pioneer ILS Interval (XILSX) | -195.8 | -195.8 | 0 |
| City National Rochdale Select Strategies | +41.1 | +32.1 | 4 |
| Brookmont Catastrophic Bond ETF | +76.9 | +76.9 | 0 |

SRRIX moves by the one nulled month (sales of 7.4m that month no longer
count because its redemption field is unusable); CNR by the four months
whose negative sales the old code had turned into inflows. The two large
figures the audit was about, SRRIX and SHRIX, and the Pioneer CAT lineage
are confirmed to within those nulls. Tests 108 -> 113 (`tests/test_nport.py`
rewritten for conventions, missing components, conflicts, amendment
selection and lineages); four mutations (flip every negative, missing as
zero, conflict as magnitude, every accession kept) each turned the suite
red.

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
  scripts (plists now point at `/Users/caropark/projects/cat-bond-flow-analysis`;
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
