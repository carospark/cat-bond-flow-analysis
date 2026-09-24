# Catastrophe Bond Flow Analysis

Joins structured catastrophe bond issuance to secondary-market and fund data,
to get from *what was issued* to *how capital actually moved*.

**Status: early. The joins are being built and validated; the flow model is not.**

Companion to [`cat-bond-issuance`](https://github.com/carospark/cat-bond-issuance),
which parses the issuance side. This repository consumes its output.

---

## The problem

Issuance data is not flow data. A deal directory records primary-market
supply — what was brought to market, at what size and spread. It does not
record subscriptions, redemptions, secondary trading, or fund AUM. So the
headline question cannot be answered from issuance alone:

```
AUM change = investor net flow + investment performance + FX
```

Answering it needs at least three things joined: a deal universe with stable
identifiers, secondary-market transactions, and fund-level NAV and returns.

## The identifier problem

Secondary transaction data is keyed on security identifiers; the deal directory
is keyed on issuer names and dates. Nothing joins them directly.

Worse, the obvious shortcut is incomplete: the transaction data's own
catastrophe-bond classification only begins in 2021. Anything earlier has to be
identified from a deal list — which is exactly what the parser produces. That
makes the issuance side load-bearing rather than merely descriptive.

`src/build_bridge.py` builds that mapping conservatively: matching on more than
the name, since issuer families reuse names across years and series, and
carrying an explicit confidence and evidence for every matched pair. **A wrong
identifier match is worse than an unmatched deal**, because it silently
attributes another security's trades to a deal.

## What is here

```
src/build_bridge.py           deal universe -> security identifiers, with evidence
src/extend_bridge.py          program-level attribution for what the bridge refuses
src/pull_tier1_sources.py     archive external reference sources, with checksums
src/pull_market_signals.py    archive weather-market and disaster snapshots
src/backfill_prediction_market_history.py  resumable closed-market history
src/extract_reference_series.py  extract Aon, Guy Carpenter, and Lane series
src/clean_trace_trades.py     raw TRACE messages -> one clean trade table
src/build_deal_panel.py       deal-day trades joined to hazard-market activity
src/event_check.py            end-to-end check of the joins around one hurricane
config/tier1_sources.json     the source registry: publisher, title, URL, role
config/market_signal_sources.json  public API registry for market signals
docs/SOURCES.md               what each source is and why it is used
docs/MANUAL_DATA_PULLS.md     terminal/form-gated pulls and acceptance checks
scripts/run_daily_non_artemis_snapshots.sh  daily non-Artemis snapshot runner
scripts/run_prediction_history_batch.sh  resumable historical batch runner
tests/                        offline tests
DATA_POLICY.md                what may never be committed here
```

## What can and cannot be supported

Realistically supportable from these sources:

- Primary-market absorption — upsize share, final spread against guidance
  midpoint, spread multiple over expected loss
- Gross and net issuance, once maturities and payouts are accounted for
- Secondary-market activity for the identifiable universe
- Fund-level flows where NAV and return series exist, via the identity above

Not supportable, and worth stating plainly:

- Private-fund subscriptions and redemptions
- Investor-level allocations or breakdowns
- Any causal claim about what drove a flow

## Setup

Python ≥ 3.9. The PDF reference extractor also requires Poppler command-line
tools (`pdftotext` and `pdftocairo`).

```bash
python3 -m venv .venv && ./.venv/bin/python -m pip install -e .
./.venv/bin/python -m unittest \
  tests.test_pull_tier1_sources \
  tests.test_pull_market_signals \
  tests.test_backfill_prediction_market_history \
  tests.test_extract_reference_series -v
```

`tests/test_bridge.py` is a data-backed integration check and needs the local
deal index plus licensed TRACE/FISD files. Run it only after those gitignored
inputs are present.

Pull the public non-Artemis snapshots and extract the local broker-series
validation tables with:

```bash
./.venv/bin/python src/pull_market_signals.py --as-of YYYY-MM-DD --metadata-only
./.venv/bin/python src/extract_reference_series.py
```

On macOS, `scripts/install_macos_daily_pull.sh` installs a LaunchAgent that
runs the metadata snapshot plus Brookmont refresh at 02:15 local time. It does
not invoke any Artemis code. Price/trade-history backfills are available by
omitting `--metadata-only` for the current open universe. For resolved markets,
run the checkpointed backfill separately:

```bash
./.venv/bin/python src/backfill_prediction_market_history.py \
  --since 2016-09-03 --until 2026-09-04 \
  --classification hurricane_or_named_storm
```

It discovers closed contracts newest-to-oldest, batches Polymarket price
histories, routes Kalshi records across its live/historical cutoff, and resumes
completed work from a gitignored SQLite database.

`scripts/install_macos_prediction_history_backfill.sh` installs a separate
03:15 local-time LaunchAgent. Each run discovers, then prices, then trades,
up to 5,000 of the newest remaining contracts per platform for every hazard
class with a cat-bond counterpart: hurricane and named storm, earthquake,
severe convective storm, wildfire, winter storm, volcanic eruption, typhoon
and cyclone, precipitation, windstorm, pandemic and mortality, disaster
declarations, and ENSO. The end date moves daily so newly resolved contracts
keep being discovered. Completed or publisher-unavailable jobs are skipped.
City-temperature contracts are still discovered and archived daily, but their
history backfill is deferred: they are hourly forecast markets with no link to
insured loss, and belong to a separate project.

Every contract also carries `region:<name>` tags (for example
`region:california`, `region:japan`, `region:europe`). Precipitation and
winter-storm markets are kept only for U.S., Canadian, and Japanese
geographies, and windstorm markets only for Europe and Australia, because
those are the only places the deal directory has the matching exposure. The
mapping from cat-bond perils to markets is in `docs/SOURCES.md`.

Both LaunchAgents run `/bin/zsh` from `launchd`, which has no access to
macOS-protected folders (Desktop, Documents, Downloads, iCloud Drive). If the
project lives in one of those, the jobs fail every night with `can't open
input file` and exit status 127. Either grant `/bin/zsh` Full Disk Access
(System Settings > Privacy & Security > Full Disk Access, add `/bin/zsh`
via Cmd+Shift+G), or keep the project outside a protected folder. Verify with
`launchctl list | grep catbondflow`: a non-zero last-exit column means the
job is still failing.

## Clean and join

Once the TRACE exports and the bridge are present locally:

```bash
./.venv/bin/python src/clean_trace_trades.py
./.venv/bin/python src/extend_bridge.py --deals /path/to/deals.csv
./.venv/bin/python src/build_deal_panel.py --deals /path/to/deals.csv
```

The cleaner removes cancellations, corrections, reversals, and inter-dealer
double reports from the raw enhanced and standard TRACE messages, following
Dick-Nielsen (2009, 2014) as checked against how the status codes actually
link in these files; every drop is counted by rule in a summary JSON. The
panel builder aggregates clean trades to deal, CUSIP, and day through the
bridge, builds daily activity series per hazard class and region from the
prediction-market database, and, when the parsed deal directory is supplied,
maps each deal's covered perils to those classes and regions and joins the
two. Offline tests cover every cleaning rule and the peril mapping.

The strict bridge leaves real ILS securities unattributed when the directory
has the issuer program but no deal within a month, several deals in the same
month, or no deal at all. `src/extend_bridge.py` records those cases
explicitly rather than forcing them through the strict path: for every
screened CUSIP outside `bridge.csv` it finds the issuer program, the nearest
directory deal by issue month, and writes a separate table with confidence
`program` and a level (`program_nearest`, `program_maturity_split`,
`program_tied`, `program_only`, `program_absent`). Same-month twins that
differ only in tenor are split by the maturity the parsed directory states,
when both twins state one and the TRACE maturity matches exactly one. It
never modifies `bridge.csv`. The panel builder joins only the rows that name
one deal, with match confidence `program`, so any test that needs identity
rather than program membership can filter them out.

## Checking the joins

`src/event_check.py` is a validation gate, not a result. Around one Florida
landfall it splits the traded deals by the hazard map into Florida-exposed
and no-hurricane groups, takes each deal's volume-weighted price before and
after the event, and plots the weekly median path of each group above the
weekly hurricane-contract activity from the prediction markets. If the
bridge, the cleaning, the peril mapping, and the market join are all right,
exposed bonds move and unexposed bonds do not.

```bash
./.venv/bin/python src/event_check.py --event ian
./.venv/bin/python src/event_check.py --event milton --include-program --pre-days 60
```

Both storms pass. Around Ian the known loss-bearing deals fall by tens of
points while the diversified exposed deals and the earthquake-only deals
share a uniform few-point decline, which is the market-wide repricing of
late 2022 rather than an attribution error. Around Milton only exposed deals
move at all: one sells off into landfall and recovers, the rest rally once
the season's peak has passed, and the unexposed deals stay within a fraction
of a point. Contract activity leads Ian's landfall by a week and peaks in
Milton's landfall week. Outputs are gitignored under `data/event_checks/`;
the figures are in the local manifest.

## Data

**No third-party or licensed data is stored here.** Cloning this will not give
you a runnable pipeline — you need your own access to the deal directory and
your own research-data subscription. See [`DATA_POLICY.md`](DATA_POLICY.md).
Local raw snapshots and extracted tables are stored under `data/` and remain
gitignored; only pullers, schemas, tests, and public provenance are tracked.
