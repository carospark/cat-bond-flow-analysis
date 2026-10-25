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
src/fund_registry.py          load and EDGAR-verify the fund registry
src/pull_nport.py             archive Form N-PORT filings per fund, with the screen used
src/parse_nport.py            N-PORT filings -> monthly flows, returns, holdings
src/build_fund_holdings.py    fund holdings joined to deals; fund marks vs TRACE
src/build_etf_flows.py        daily ETF snapshots -> shares outstanding and flow
config/tier1_sources.json     the source registry: publisher, title, URL, role
config/fund_registry.json     funds whose NAV, return, and flow series are pulled
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

Both LaunchAgents run `/bin/zsh` from `launchd`. Each runner writes a
timestamped `start` line to its stdout log before doing anything else, a line
per step, and a `FAILED exit=N step="..."` line on any non-zero exit, so a
night with no `start` line never ran and a night that stopped says where. A
lock left by a run that died without reaching its exit trap is cleared when
its recorded PID is gone. Check that the archive is current with

```bash
./.venv/bin/python scripts/check_snapshot_freshness.py
```

which prints the last snapshot date per nightly source (and the last completed
batch run per platform) and exits non-zero when any is more than two days old.

Where the project folder lives matters. If it sits under a macOS-protected
folder (Desktop, Documents, Downloads) that is also synced by iCloud Drive
with "Optimize Mac Storage", iCloud evicts files it considers cold, including
files inside `.venv/`; a `launchd` process that then reads an evicted file
fails with `OSError: [Errno 11] Resource deadlock avoided` (seen on imports,
on the certificate bundle, and on log appends) and, in the worst case, with
`can't open input file` and exit status 127 if the shell cannot read the
project at all. Keep the project outside those folders, or exclude it from
iCloud sync, or grant `/bin/zsh` Full Disk Access (System Settings > Privacy &
Security > Full Disk Access, add `/bin/zsh` via Cmd+Shift+G). Verify with
`launchctl list | grep catbondflow`: a non-zero last-exit column means the
job is still failing, and the stdout log says at which step.

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

Both builders also read the fund-reported security titles from the parsed
N-PORT holdings when `data/processed/nport/fund_holdings.csv` exists.
Holders name the series outright for about 640 CUSIPs. In the strict
bridge a unanimous title decides between candidates that differ only in
series when the directory has the named series, which is what separates
adjacent-month twins that share a TRACE issue month; when the directory
lacks the named series the match stands, capped at medium, with the
disagreement in the series evidence. In the program bridge a title that
names exactly one tied deal resolves the tie at level
`program_nport_title` before the maturity split runs. Locally the title
evidence split 49 pairs, raised the strict bridge from 677 to 699 deals,
and cut the same-month ambiguities from 26 deals to 6; the event checks
are unchanged.

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
./.venv/bin/python src/event_check.py --event ian --high-confidence-only
```

`--high-confidence-only`, on both `event_check.py` and `build_deal_panel.py`,
restricts to strict-bridge pairs at high confidence (no medium, low or
program rows) and writes under a `high_confidence/` sub-folder, so every
result can be shown beside its high-confidence-only version. The bridge
summary publishes how the N-PORT titles touched the pairs (built without any
title evidence, changed or split by a title, created by the sibling
propagation, confirmed unchanged), and `bridge.csv` carries the class per
pair in `title_evidence`. `src/draw_bridge_audit_sample.py` draws a
seed-fixed sample of pairs stratified by confidence and issue year, with
every evidence column and empty verdict columns, for a hand check that is
independent of the titles feeding the bridge.

Both storms pass. Around Ian the known loss-bearing deals fall by tens of
points while the diversified exposed deals and the earthquake-only deals
share a uniform few-point decline, which is the market-wide repricing of
late 2022 rather than an attribution error. Around Milton only exposed deals
move at all: one sells off into landfall and recovers, the rest rally once
the season's peak has passed, and the unexposed deals stay within a fraction
of a point. Contract activity leads Ian's landfall by a week and peaks in
Milton's landfall week. Outputs are gitignored under `data/event_checks/`;
the figures are in the local manifest.

## Fund flow

The fund-flow track starts from `config/fund_registry.json`, the list of
funds whose NAV, return, and flow series are pulled. The SEC entries were
resolved from EDGAR full-text search over Form N-PORT filings and each
registrant's series list, and every entry carries the evidence that put it
there. The registry is the identifier screen for the N-PORT pull, so its
hash goes into the local manifest with each pull.

```bash
./.venv/bin/python src/fund_registry.py            # list the screen and its hash
./.venv/bin/python src/fund_registry.py --verify   # check every entry against EDGAR
```

Form N-PORT Part B reports, for each of the preceding three months, net
assets, total return per class, and the value of shares sold, reinvested,
and redeemed. For the registered interval funds that is observed
subscriptions and redemptions, not an inference from the AUM identity.
Part C holdings carry CUSIPs that join to the bridge. UCITS funds are listed
as planned; their flow has to be backed out from fund size and return.

```bash
./.venv/bin/python src/pull_nport.py --as-of YYYY-MM-DD   # archive every public filing
./.venv/bin/python src/parse_nport.py                     # flows, returns, holdings
```

The puller writes the screen it used, with the registry's hash, under
`data/raw/sec_nport/screens/`, lists filings per series through EDGAR's
company browser so multi-series trusts resolve to one fund, checks every
downloaded XML against the registry's series name, and is resumable. The
parser writes `fund_flows.csv`, `fund_returns.csv`, and `fund_holdings.csv`
under `data/processed/nport/` with a summary that reports bridge overlap.
Three things it handles that the raw filings do not make obvious. Month 3 of
each filing is the report month (verified against the Brookmont ETF's daily
NAV). Some filers reported redemptions as negative numbers for a stretch
(Stone Ridge, Pioneer and City National Rochdale, through the January 2024
report period); the sign is flipped only inside the ranges documented per
fund in `config/nport_sign_conventions.json`, every raw value is kept in a
`*_raw` column, and a value whose sign the table does not explain is left
null and flagged, which also nulls that month's net flow (`net_flow_basis`
says why; a missing component does the same). Amended filings (NPORT-P/A)
are archived beside the originals and the latest filed stands for its
period, with the superseded accessions listed in the summary. Only the
quarter-end filing is public, so the monthly series arrives in quarterly
batches with a 60-day lag. One series the form does
not carry is distributions: total return includes them and net assets lose
the cash part, so the AUM identity closes only once they are added back.
They can be backed out as the residual of the identity quarter by quarter,
which is large in December for the Stone Ridge funds and steady for the
monthly payers, or taken from N-CSR.

```bash
./.venv/bin/python src/build_fund_holdings.py --deals /path/to/deals.csv
```

The holdings join attributes each fund position to a deal through the same
combined bridge the deal panel uses, keeps the fund's own mark as a price
per 100 for debt positions reported in principal amount, aggregates to deal
and quarter with the share of issued size held, and compares the
par-weighted fund mark with the TRACE volume-weighted price in the window
before and in the window after each quarter end, separately and together,
reporting the tails of the gap distribution and the share of pairs whose
nearest trade is more than a week away. Non-USD par is converted at the
report month's rate (the parser's tracked ECB/BoE table, `--fx-table`)
before a mark is taken. The two price sources are independent, so their
agreement is a check on the cleaning and the holdings parse. It is not a
check on the bridge, because it is keyed on the CUSIP; a second comparison
keyed on the deal sets each held CUSIP's mark against the other CUSIPs of
the same deal in the same quarter (`data/fund_marks_by_deal.csv`), where a
wrong CUSIP-to-deal link would surface as a tranche that disagrees with its
siblings. Locally the median gap to TRACE is a quarter of a point across
more than two thousand CUSIP-quarter pairs. The remaining large gaps, and
every large within-deal disagreement found so far, are loss-affected bonds
where tranches genuinely price apart, which is itself a research object.
Positions filed with an all-zero CUSIP, which are segregated-account cells
and quota shares, are dropped rather than reported as bridge gaps.

```bash
./.venv/bin/python src/build_etf_flows.py
```

The ILS ETF is the one fund with a daily, observed flow series. Each
nightly issuer snapshot records shares outstanding, net assets, and NAV;
an ETF's shares change only through creations and redemptions, so the
change in shares times NAV is investor flow. The compiler walks every
archived snapshot into one series, splits each net-asset change into flow
and non-flow, and reconciles against the same fund's N-PORT monthly flows
once a quarter's filing is public. A gap between snapshots is carried as
one row spanning the gap, not spread over days.

```bash
./.venv/bin/python src/resolve_ties_from_nport.py
```

Funds describe each position with a free-text title, and many titles name
the series outright ("Kilimanjaro III Re 2019-1 Class A-1"). That is the
evidence the program bridge lacks when same-month twins differ only in
tenor. The resolver collects every title per CUSIP, requires the series to
be stated as a year and number rather than inferred from a class letter,
requires all titles for a CUSIP to agree, and writes a resolution table
with the titles and funds as evidence. It never modifies the bridge
tables. It also checks every strict-bridge CUSIP whose titles name a
series against the bridged deal's series and lists the disagreements, which
is where a wrong match would show up first.

## Data

**No third-party or licensed data is stored here.** Cloning this will not give
you a runnable pipeline — you need your own access to the deal directory and
your own research-data subscription. See [`DATA_POLICY.md`](DATA_POLICY.md).
Local raw snapshots and extracted tables are stored under `data/` and remain
gitignored; only pullers, schemas, tests, and public provenance are tracked.
