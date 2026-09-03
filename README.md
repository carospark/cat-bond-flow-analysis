# Catastrophe Bond Flow Analysis

Joins structured catastrophe bond issuance to secondary-market and fund data,
to get from *what was issued* to *how capital actually moved*.

**Status: early. The joins are being built and validated; the flow model is not.**

Companion to [`cat_bond_fund_flow`](https://github.com/carospark/cat_bond_fund_flow),
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
src/pull_tier1_sources.py     archive external reference sources, with checksums
src/pull_market_signals.py    archive weather-market and disaster snapshots
src/backfill_prediction_market_history.py  resumable closed-market history
src/extract_reference_series.py  extract Aon, Guy Carpenter, and Lane series
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
03:15 local-time LaunchAgent. Each run processes up to 5,000 of the newest
remaining city-temperature contracts per platform for prices, then trades.
Completed or publisher-unavailable jobs are skipped automatically.

## Data

**No third-party or licensed data is stored here.** Cloning this will not give
you a runnable pipeline — you need your own access to the deal directory and
your own research-data subscription. See [`DATA_POLICY.md`](DATA_POLICY.md).
Local raw snapshots and extracted tables are stored under `data/` and remain
gitignored; only pullers, schemas, tests, and public provenance are tracked.
