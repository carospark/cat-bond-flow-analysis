# Data manifest

> **Public copy.** Vendor query identifiers and file checksums are omitted
> here: the identifiers are tied to an institutional account and the checksums
> fingerprint licensed extracts. Full provenance — query ids, byte counts,
> SHA-256, timestamps — is written to `data/MANIFEST.local.md`, which is
> gitignored. This file records *what* each source is and *why* it is used.



This is the source-of-truth inventory for external and licensed data used to
build the catastrophe-bond panel, validate the Artemis parser, and support the
later fund-flow analysis. It distinguishes a **download** from an **extracted
series**: having a PDF or vendor export locally does not mean its observations
have been cleaned, classified, or reconciled.

Raw publisher files, parsed snapshots, hashes, and the append-only pull log are
stored under `data/raw/` and are deliberately gitignored. They may be subject
to publisher copyright or database rights. The tracked registry is
`config/tier1_sources.json`; do not redistribute the local archive without
checking each publisher's terms.

## Reproduce the current pull

```bash
./.venv/bin/python src/pull_tier1_sources.py --as-of YYYY-MM-DD
./.venv/bin/python src/pull_market_signals.py --as-of YYYY-MM-DD --metadata-only
./.venv/bin/python src/backfill_prediction_market_history.py \
  --since YYYY-MM-DD --until YYYY-MM-DD
./.venv/bin/python src/extract_reference_series.py
```

Use `--source SOURCE_ID` to refresh one source. Each run records the resolved
payload path, byte count, SHA-256, UTC timestamp, parser outputs, and failures
in `data/raw/tier1/pull_log.jsonl`; `latest_status.json` contains the last result
for every configured source.

On macOS, `scripts/install_macos_daily_pull.sh` installs a 02:15 local-time
LaunchAgent that snapshots Kalshi, Polymarket, Climate Central, and Brookmont.
The runner names only non-Artemis sources. Kalshi's complete open-event scan is
slow by design; each run is isolated by a lock and writes stdout/stderr under
`data/`.

## Non-Artemis refresh completed 2026-09-03

- Kalshi: 13,653 open events scanned; 728 contracts retained only when the
  event's official category is `Climate and Weather` and its title describes a
  hurricane, named storm, or city temperature. Metadata includes current
  quotes, volume, open interest, and resolution rules.
- Polymarket: 22,795 active, non-closed events scanned using the official
  keyset cursor endpoint; 3,225 still-tradable, non-expired weather contracts
  retained. The large count is mostly daily city-temperature outcome ladders.
- Climate Central: 438 event records and 47 annual observations (1980-2026)
  archived. This is an economic-loss event calendar, not insured loss.
- Brookmont: 133 holdings as of 2026-09-01 and current NAV metrics archived.
  The issuer's embedded historical NAV array remains frozen at 191 observations
  ending 2025-12-31.
- Priority broker extraction: 16 Aon annual issuance labels, 128 Aon tranche
  pricing rows, 27 Guy Carpenter ROL observations, and 23 Lane annual pricing
  rows are written locally to `data/processed/reference_series/`.

Market-signal snapshots, licensed inputs, and extracted broker observations are
gitignored. `config/market_signal_sources.json` is the tracked registry for the
three new public API sources.

### Historical prediction-market backfill

`src/backfill_prediction_market_history.py` handles resolved contracts
separately from the daily open-contract snapshot. Its default window is the
latest ten years, processed newest-to-oldest. Completed discovery, price, and
trade jobs are checkpointed in
`data/raw/tier1/prediction_market_history.sqlite3`, so interrupted runs resume
without repeating completed API calls. Kalshi contracts that are still open or
initialized are explicitly excluded even when their scheduled close timestamp
falls inside the requested window.

For Kalshi, the job discovers relevant `Climate and Weather` series and merges
recent market data with the exchange's historical tier using the current
cutoff. For Polymarket, it searches closed events in reverse-chronological
windows and batches up to 20 outcome-token price histories per request. The
price backfill also slices each batch into seven-day intervals because the
public endpoint rejects longer ranges for hourly fidelity. The
classes can be backfilled independently: hurricane/named-storm history comes
first because it is the direct cat-bond information signal; the much larger
city-temperature universe follows.

The city-temperature universe discovered on 2026-09-03 contains 197,884
resolved Kalshi contracts and 120,613 resolved Polymarket contracts. Their
history backfill was run nightly until 2026-09-14 and then deferred: these
are hourly forecast markets with no link to insured loss or any cat-bond
trigger, so they belong to a separate project. The 03:15 local-time
LaunchAgent now loops over every hazard class with a cat-bond counterpart
(see the coverage table below), running discovery, prices, and trades for each
with a moving end date, so newly resolved contracts keep being discovered.
Discovery of city temperature continues in the daily snapshot. The partial
temperature history already stored is retained; note that the Kalshi
candlestick request uses a daily interval, which returns nothing for
sub-day markets, so that partial history is trades-complete but
candle-sparse.

On 2026-09-14 the storm classifier was tightened after 55 Polymarket sports
contracts (Super Rugby Pacific and college teams named Hurricanes) had passed
the guard because "Pacific" and "Atlantic" appeared in team or league names.
Basin words now need a weather neighbour, and sports vocabulary requires an
unambiguous storm token. Those 55 contracts and their history rows were
removed from the local database; earlier raw snapshot CSVs are archives and
were left as pulled.

### Hazard coverage: cat-bond perils versus prediction markets

Reconciled 2026-09-14 against the parsed deal directory (1,311 deals; peril
strings are free text, so one deal can count under several rows), the full
Kalshi series list (14,018 series), and Polymarket keyword search. The
reinsurance comparators (Guy Carpenter, Howden, Aon rate-on-line series) are
all-peril property-cat indices with no peril split, so the mapping runs
through the cat-bond perils.

| Peril | Deals (since 2021) | Kalshi | Polymarket | Class and status |
|---|---:|---|---|---|
| U.S. hurricane / named storm | 648 (298) | Seasonal counts, major counts, tropical-storm counts, first-hurricane naming, city landfall (Miami, NYC, Orlando, New Orleans, Tampa, Houston, Charleston, Savannah, Wilmington, Jacksonville, Myrtle Beach, Hatteras, Norfolk, Texas coast, California), path markets | Seasonal named-storm counts 2021-2026, monthly and seasonal U.S. landfall, storm-specific landfall and category (Helene, Milton, Melissa, Beryl, Idalia, Lee, Imelda, Francine), CSU forecast, first-hurricane timing, Hawaii landfall | `hurricane_or_named_storm`; fully backfilled |
| U.S. earthquake (incl. California) | 454 (190) | Earthquake in California, Earthquake in LA, monthly and M7 earthquake, biggest earthquake, tsunami | LA M6.5+ before 2026, M7+ by month, weekly global M5.5+/M6.5+ counts, "where will a 6.0+ occur" with region outcomes, highest magnitude 2026, San Francisco tsunami | `earthquake`; pulled from 2026-09-14. Global counts are conditioning signals; `region:california` picks the direct ones |
| Severe convective storm | 186 (100) | Number of tornadoes | Monthly and annual U.S. tornado counts, daily city tornado risk | `severe_convective_storm`; pulled from 2026-09-14. Tornado only: no hail market exists on either exchange |
| European windstorm | 132 (28) | none | none: the only wind-speed markets are Mt. Washington (NH) and Wellington (NZ) | `windstorm`, gated to Europe and Australia; nothing exists yet, the class will catch future listings (named-storm gust markets) |
| Canada perils | 126 (81) | none | none | Canada earthquake and Canada named storm, i.e. the U.S. perils extended north. No Canada-specific market; Atlantic seasonal counts are the nearest proxy and are already pulled |
| Wildfire | 118 (74) | none | LA / Palisades event markets, January 2025 (containment, acres, spread) | `wildfire`; pulled from 2026-09-14. Event-driven only; no seasonal market |
| Winter storm / freeze | 96 (50) | Monthly city snowfall (NYC, Chicago, Denver, Dallas, Houston, Austin, Seattle, San Francisco, LA, Phoenix, Alta) | NYC and D.C. snowfall inches | `winter_storm`, gated to U.S. and Canada; pulled from 2026-09-14. Proxy only: snowfall is not freeze or ice loss |
| Japan earthquake | 86 (20) | Earthquake in Japan, July 2025 Japan event | none Japan-specific | `earthquake` with `region:japan`; pulled from 2026-09-14 |
| Volcanic eruption | 61 (35) | VEI 4, Supervolcano, Kilauea, Etna, Mount Spurr | VEI 4+ count 2026, VEI 6+ 2026, Vesuvius, Etna, Iceland 2023 | `volcanic_eruption`; pulled from 2026-09-14 |
| Mortgage insurance | 60 (27) | n/a | n/a | Not a hazard; out of scope |
| Meteorite impact | 59 (33) | none | none | Not available |
| Flood | 43 (24) | Monthly and daily city rain for 17 U.S. cities (NYC, Miami, Houston, New Orleans, Dallas, LA, Chicago, Seattle, San Francisco, Denver, Austin, Columbus, Milwaukee, Providence, Lexington, College Station, St Petersburg, D.C.) | Monthly precipitation NYC and Seattle, daily "where will it rain", White River crest August 2026, LA flooding 2023 | `precipitation`, gated to U.S. and Japan; pulled from 2026-09-14. Rainfall is the nearest proxy for NFIP-style flood exposure; London, Paris, Seoul, and Hong Kong rain markets are excluded because no deal covers them |
| Mexico / Latin America / Caribbean | 39 (18) | none | "where will a 6.0+ earthquake occur" region outcomes only | Not available beyond the earthquake region outcomes |
| Japan typhoon | 34 (11) | none | NW Pacific named-typhoon count, Typhoon Dolphin (Japan, China, landfall intensity), Saudel, Honshu landfall, China landfall count | `typhoon_or_cyclone`, gated to Japan, East Asia, and Australia; pulled from 2026-09-14 |
| Australia cyclone | 21 (4) | none | none: no Queensland, Cyclone Alfred, or Australian wind market found | `typhoon_or_cyclone` and `windstorm` both admit Australia; nothing exists yet |
| Extreme mortality / pandemic | 20 (2) | Pandemic and PHEIC declaration series by pathogen | New pandemic 2024-2028, bird flu, hantavirus, Ebola, measles, COVID pandemic declarations | `pandemic_or_mortality`; pulled from 2026-09-14. Declaration language only; case counts, boosters, and approvals are excluded |
| Medical benefit / health | 17 (6) | none | none | Not available |
| Cyber | 11 (11) | none | none on attack occurrence | Not available |
| Terrorism | 6 (5) | none | designation questions only | Not available |
| Drought / heat / crop | 3 (0) | Drought level | D4 drought by state weekly, crop and cattle drought share, Paris heat wave | Not pulled; negligible cat-bond exposure |

Cross-cutting signals pulled alongside the peril markets from 2026-09-14:
`disaster_declaration` covers Kalshi's FEMA state-declaration counts and its
"natural disaster hits <city>" series for 14 U.S. cities, plus Polymarket's
"Natural Disaster in 2026" and billion-dollar-disaster record markets; `enso`
covers El Niño declaration and RONI on both exchanges. These condition the
season rather than a single peril.

Searches that came up empty on 2026-09-14, so their classes exist but hold
nothing: wind speed or gust markets for Europe or Australia (only Mt.
Washington and Wellington exist), any Canadian hazard market, any Australian
cyclone or bushfire market, and any hail market.

## Licensed WRDS inputs archived 2026-08-31

The following Penn WRDS exports were queried on 2026-08-30 and copied into
`data/raw/wrds/2026-08-30/` on 2026-08-31. The originals were left in place.
These files are licensed research inputs: they remain gitignored and must not
be committed or redistributed. The saved HTML is context and provenance, not
a data table.

| Local file | WRDS source / query | Rows | Coverage and role | SHA-256 |
|---|---|---:|---|---|
| `wrds_trace_camasterfile_144a.csv` | `trace_standard.camasterfile`; `ind_144a = 'Y'`; all 18 fields | 413,936 | `stdt`/`enddt` span 2002-07-01 to 2026-06-05. Primary security-master input for constructing the ILS CUSIP universe. | (recorded locally) |
| `wrds_fisd_issue_bermuda_cayman_144a.csv` | `fisd_fisd.fisd_issue`; Bermuda or Cayman and `rule_144a = 'Y'`; 32 selected fields | 1,794 | Offering dates 1991-06-24 to 2026-06-23. Negative-coverage check and identifier/terms control, not the main cat-bond issue source: only Four Lakes Re 2020-1 and Logistics Re 2021-1 are cat bonds. | (recorded locally) |
| `wrds_fisd_issuer.csv` | `fisd_fisd.fisd_issuer`; complete 10-field issuer file | 17,417 | Issuer reference for domicile, parent, NAICS, and FISD joins; 358 issuers are Bermuda- or Cayman-domiciled. | (recorded locally) |
| `wrds_access_audit.html` | Saved Penn WRDS access/query audit; checked 2026-08-30 and saved 2026-08-31 | n/a | Documents subscribed products, query-form behavior, diagnostic query IDs, coverage limitations, and proposed use of TRACE/FISD. | (recorded locally) |

### Prediction-market-adjacent WRDS inputs archived 2026-08-31

These files were queried and downloaded from Penn WRDS on 2026-08-31 and
copied into `data/raw/wrds/2026-08-31/` the same day. The originals remain in
`~/Downloads`. They are licensed research inputs and remain gitignored.

The two downloaded CSV filenames were reversed relative to their contents:
`WRDS_ravenpack.csv` is the MarketPsych extract, while
`WRDS_marketpsyche.csv` is the RavenPack taxonomy. The archive uses
content-correct names and preserves the source-name discrepancy here for
auditability.

| Local file | WRDS source / query | Rows | Coverage and role | SHA-256 |
|---|---|---:|---|---|
| `wrds_marketpsych_country_sentiment_us_gb.csv` | `mpsych_locations`; country sentiment for `COU_US` and `COU_GB`, limited to overall, natural-disaster, and weather-event buzz/sentiment fields | 41,230 | Daily observations from 1998-01-01 through 2025-12-31, separated where available into News, PressR, and Social sources. Market-attention and sentiment control for event studies; not a prediction-market price series. The disaster fields are populated on 16,750 rows and weather-event fields on 10,968 rows. | (recorded locally) |
| `wrds_ravenpack_rpa_1_taxonomy.csv` | `ravenpack_common`; complete RavenPack RPA 1.0 taxonomy | 6,895 | Taxonomy/reference file with topic, group, event type/sub-type, fact level, category, description, scheduling flag, and valid entity types. Use it to define catastrophe-warning and warning-lifted event filters before a later RavenPack event-data pull; it contains no timestamped news events itself. | (recorded locally) |
| `wrds_access_audit_prediction_markets.html` | Expanded Penn WRDS access/query audit; checked 2026-08-30 through 2026-08-31 | n/a | Adds query IDs and interpretation for RavenPack, MarketPsych, OptionMetrics, and off-WRDS prediction-market sources. Records that WRDS has belief proxies but no event-probability trading dataset. | (recorded locally) |

These additions support a four-clock event-study design: prediction-market
probabilities, option-implied insurer risk, TRACE cat-bond prices, and news or
sentiment measures. Only the last clock is represented in the two CSVs above.
The RavenPack file is preparatory metadata, and the MarketPsych file is a daily
country-level signal. Actual RavenPack event observations, OptionMetrics data,
and off-WRDS prediction-market histories remain separate future pulls.

### What the WRDS files establish

- TRACE is the usable security master. Every exported row is flagged 144A,
  413,639 rows have a nonblank CUSIP, and there are 62,713 distinct nonblank
  CUSIPs in the full export.
- `debt_type_cd = 'UN-CAT'` identifies 5,236 master-file rows and 663 distinct
  nonblank `cusip_id` values in the delivered CSV. The saved access audit says
  723 distinct CUSIPs for those same 5,236 rows. Until that difference is
  reproduced from the original query logic, use **663** as the file-backed
  count and retain 723 only as an unreconciled audit claim.
- The `UN-CAT` classification begins in 2021, so it cannot define the historic
  universe by itself. Pre-2021 coverage still requires issuer/program-name
  screening followed by validation against Artemis or another deal list.
- FISD's 1,794-row offshore 144A screen contains only two cat bonds. It is a
  useful control and source of terms for those matches, but it cannot serve as
  the issue-characteristics backbone for the ILS panel.
- The WRDS cleaned TRACE and Bond Returns products depend on FISD matching and
  therefore exclude nearly all cat bonds. Trade analysis must start from raw
  BTDS 144A data and apply cancellation, correction, reversal, and
  double-counting filters locally.

These three exports are security and issuer masters; they contain **no TRACE
transactions**. The transaction pull was completed on 2026-09-03 against a
curated cat-bond CUSIP screen of 1,332 identifiers, recovered read-only from
the WRDS query history on 2026-09-15 and reconciled: it covers most of the
bridge, most UN-CAT-labelled securities the bridge left unmatched, and about
220 further ILS securities from known issuer programs (Sector Re, Pioneer,
Successor, Vita Capital, Residential Re and others) that the strict bridge
does not match. 72 bridge CUSIPs were not in the screen and need a
supplementary pull. The queries used `trace_enhanced.trace_btds144a_enhanced`
for the 2002-2025 request (observed trades run from January 2011 to early December
2025, where the enhanced table currently ends), plus the standard 144A trade
table for the tail through early June 2026. Both were pulled in four CUSIP
batches per table. The files are raw disseminated messages and keep the
cancellation, correction, reversal, and sequence fields; no cleaning has been
applied. Query identifiers, row counts, and checksums are in the local
manifest.

### TRACE cleaning and the deal panel

`src/clean_trace_trades.py` turns the raw enhanced and standard TRACE 144A
messages into one trade table. The rules follow Dick-Nielsen (2009, 2014),
but the record linkage was verified empirically on these files rather than
assumed, because the post-2012 enhanced format does not match the usual
description:

- A cancellation (`trc_st = X`) is a copy of the cancelled trade sharing its
  `msg_seq_nb` on the same report date; both go.
- A correction is a triple: the original, a `C` copy of it flagging the
  correction, and an `R` record carrying the corrected values that points at
  the original through `orig_msg_seq_nb`. The `R` is the trade that survives.
- A reversal (`trc_st = Y`, `asof_cd = R`) names a trade reported on an
  earlier day; both go, matched by pointer, or by characteristics when the
  pointer does not resolve.
- Pre-2012 rows use `C` for cancellations, `W` for corrections carrying the
  new values, and `asof_cd = R` on plain trades for reversals.
- Inter-dealer trades appear once per dealer; the sell-side copy is dropped.
- In the standard-table tail, `function = C` cancels the message named in
  `orig_msg_seq_nb`, `function = N` corrects it with the old values kept in
  `orig_*` columns, and volumes above the dissemination cap arrive as `1MM+`
  and are stored capped with a flag.

About nine per cent of raw rows are removed. Drop counts by rule, and the
share of clean trades that the bridge attributes to deals, are in the local
manifest. The remaining trades belong to CUSIPs in the WRDS screen that the
bridge does not cover, which is why recovering that screen list matters.

`src/build_deal_panel.py` then aggregates the clean trades to deal, CUSIP,
and execution day (count, volume, volume-weighted price, last, high, low, and
dealer-buy versus dealer-sell volume), builds a daily series per prediction
market contract and an activity index per hazard class and region (contracts
priced, contracts traded, trade count, traded size; contracts on different
questions are not averaged into a probability), maps each deal's free-text
perils to hazard classes and regions with the same region vocabulary the
market classifier uses, and joins the two on class, region, and date. The
peril mapping needs the companion parser's `deals.csv`, passed with
`--deals`; without it the trade and market tables are still written.

## Pull completed 2026-08-30

All 13 automatable Tier 1 endpoints and the time-sensitive Tier 2 Artemis
directory snapshot were archived successfully. These are the immutable payload
hashes for this pull (first 12 SHA-256 characters shown here; full hashes are in
the local pull log).

| Source ID | Result | Bytes | SHA-256 prefix | Normalized output |
|---|---:|---:|---|---|
| `swiss_re_cat_bond_index_methodology` | downloaded | 2,411,023 | `2d75fdf7f68e` | none; methodology only |
| `with_intelligence_ils_index` | downloaded + parsed | 2,094,989 | `80452504e6d8` | 247 monthly returns, 2006-01 through 2026-07 |
| `brookmont_ils_etf` | downloaded + parsed | 225,665 | `885ee2438249` | 133 holdings; 191 NAV observations; fund snapshot |
| `guy_carpenter_rol_1990_2020` | downloaded | 5,558,484 | `2bfc856e661c` | chart extraction pending |
| `guy_carpenter_rol_2000_2026` | downloaded | 128,993 | `82e601a10387` | 27 annual vector-digitized observations, 2000-2026 |
| `howden_renewal_2026` | downloaded | 279,708 | `c1d509d88790` | page text only; index-level extraction pending |
| `aon_reinsurance_market_dynamics_jan_2026` | downloaded | 10,561,069 | `e78bc878589a` | PDF extraction pending |
| `aon_reinsurance_market_dynamics_apr_2026` | downloaded | 13,994,580 | `75b60340ea15` | PDF extraction pending |
| `aon_reinsurance_market_dynamics_midyear_2026` | downloaded | 3,972,722 | `e15ca5348e89` | PDF extraction pending |
| `aon_securities_ils_annual_2025` | downloaded | 775,823 | `fee46b4a8d41` | 16 annual issuance labels; 128 tranche pricing rows |
| `swiss_re_ils_market_insights_feb_2025` | downloaded | 7,627,927 | `310168d35346` | broker-series extraction pending |
| `gallagher_securities_ils_2025` | downloaded | 2,322,647 | `9dff6bb5817e` | broker-series extraction pending |
| `lane_financial_ils_2024` | downloaded | 3,775,293 | `aa0cc9cafa7e` | 23 annual issuance/spread/EL/multiple rows |
| `artemis_ils_fund_managers_snapshot` | downloaded | 143,796 | `f51d48dd7813` | current-state page archived |

Brookmont caveat: the refreshed holdings table is dated 2026-09-01, but its
embedded NAV chart still stops at 2025-12-31. The parser preserves what the
issuer served and does not fill the missing 2026 observations. Exchange closes
must remain separately labelled market-price observations, not substituted NAV.

## Tier 1 source inventory

### Secondary market and returns

| Dataset | Canonical source | Frequency | Published coverage | Access / license | Pull state |
|---|---|---|---|---|---|
| Swiss Re Cat Bond Indices | [Swiss Re methodology](https://www.swissre.com/dam/jcr%3A307452ca-9664-4772-96f9-7c11f80109b2/2014_08_ils_cat_bond_indices_methodology.pdf) and Bloomberg | Weekly | January 2002 onward requested | Bloomberg history is licensed/manual; Swiss Re PDF is publisher-copyrighted | Methodology archived. Full Bloomberg export remains manual. |
| With Intelligence ILS Index - USD Hedged (formerly Eurekahedge ILS Advisers Index) | [Index 11750](https://platform.withintelligence.com/performance/indices/11750) | Monthly | January 2006 onward; December 2005 base | Headline index page is public; constituents are restricted; publisher terms apply | Archived and parsed through July 2026. |
| Brookmont Catastrophic Bond ETF (`ILS`) | [Issuer fund page](https://ilsetf.com/ils) | Daily NAV; daily holdings snapshot | April 1, 2025 onward | Public issuer disclosure; publisher/fund terms apply | Page, holdings, NAV history, and snapshot archived. Refresh daily. |

Ticker correction to verify at the Bloomberg terminal: Swiss Re's published
methodology lists aggregate total return `SRCATTRR` and aggregate price return
`SRCATPRC`, plus `SRBBTRR` / `SRBBPRC` and `SRUSWTRR` / `SRUSWPRC` for the
BB-rated and US-wind sub-indices. The requested `SRCATPRR` does not match that
methodology.

### Reinsurance comparator

| Dataset | Canonical source | Frequency | Published coverage | Access / license | Pull state |
|---|---|---|---|---|---|
| Guy Carpenter Global Property Catastrophe ROL Index | [Renewal hub](https://www.guycarp.com/insights/renewal-hub.html) | Annual, January | Historical anchor 1990-2020; current chart 2000-Jan 2026 | Public reports; Guy Carpenter copyright | Current vector chart digitized to 27 annual points with a 0.4-index-point uncertainty flag; historical-anchor reconciliation remains. |
| Howden risk-adjusted global property-cat ROL | [2026 renewal page](https://www.howdengroup.com/ph-en/news/howden-renewal-report-112026) | Annual, January | Page reports annual change and charts from 2012-2026 | Public page; Howden copyright | Page archived; full report download is contact-gated and no table is exposed. |
| Aon Reinsurance Market Dynamics | [Report library](https://www.aon.com/en/insights/reports/reinsurance-market-dynamics) | January, April, June/July | Current reports plus publisher archive | Public reports; Aon copyright | January, April, and midyear 2026 PDFs archived. |
| Aon and Guy Carpenter alternative-capital breakdowns | Same Aon and Guy Carpenter report libraries | Annual / semi-annual | Exhibit-dependent | Public reports; publisher copyright | Aon's latest structure/capital exhibits archived in the reports above; extraction pending. GC has no current machine-readable structure table. |

### Primary-market cross-checks

| Dataset | Canonical source | Frequency | Published coverage | Access / license | Pull state |
|---|---|---|---|---|---|
| Aon Securities ILS reports | [2025 annual report](https://assets.aon.com/-/media/files/aon/insights/2025/aon-securities-2025-annual-report.pdf) | Annual; prior quarterly updates vary | July 2024-June 2025, with selected history | Public PDF; Aon copyright | Annual issuance labels and tranche size/EL/spread extracted; spread-to-EL multiple derived. The report has no aggregate price-versus-guidance table. |
| Swiss Re Capital Markets ILS reports | [ILS Market Insights](https://www.swissre.com/our-business/alternative-capital-partners/ils-market-insights-february-2026.html) | Semi-annual | Selected history; current edition covers 2025 | Public report pages/PDFs; Swiss Re copyright | February 2025 PDF archived. Current 2026 landing pages verified, but their direct PDF endpoints are not publicly exposed to this puller. |
| GC Securities reports | [Guy Carpenter insights](https://www.guycarp.com/insights.html) | Historically quarterly / ad hoc | Varies | Public pages/reports; Guy Carpenter copyright | No current standalone quarterly GC Securities report was discoverable; use GC renewal material as available and keep this as a documented gap. |
| Gallagher Securities ILS reports | [May 2025 ILS white paper](https://www.ajg.com/gallagherre/-/media/files/gallagher/gallagherre/news-and-insights/2025/may/gallagherre-insurance-linked-securities.pdf) | Ad hoc / annual | Through April 1, 2025; selected history to 2010 | Public PDF; Gallagher copyright | White paper archived; the publisher does not currently expose a quarterly series. |
| Lane Financial reports | [Publisher site](http://www.lanefinancialllc.com/) | Quarterly / annual | Latest located report covers 2001-2023 | Public PDF; Lane Financial copyright | Table 1 extracted: 23 annual rows with issuance, spread, SSST/WSST EL, and multiples. No later first-party PDF was discoverable. |

## Manual Tier 1 action

The Bloomberg series cannot be fetched from this repository. At a Wharton
terminal, export weekly date/value history for `SRCATTRR`, `SRCATPRC`,
`SRBBTRR`, `SRBBPRC`, `SRUSWTRR`, and `SRUSWPRC`, retaining Bloomberg field
names and export metadata. Store the licensed file under
`data/raw/tier1/manual/bloomberg/`; that directory is ignored. Before export,
confirm whether Bloomberg now aliases `SRCATPRR` to `SRCATPRC`.

The other authenticated/manual handoffs are specified in
`docs/MANUAL_DATA_PULLS.md`. The raw TRACE transaction query listed there was
completed on 2026-09-03.

## Acquisition and extraction gaps

| Gap | Current evidence | Resolution path |
|---|---|---|
| Bloomberg index histories | The methodology is archived, but observations are available through a licensed terminal | Export the six weekly series using the acceptance checklist in `docs/MANUAL_DATA_PULLS.md`. |
| Raw WRDS BTDS 144A transactions | Pulled 2026-09-03 for a 1,332-CUSIP screen, recovered and reconciled 2026-09-15; 72 bridge CUSIPs were outside it: enhanced table through early December 2025, standard table for the tail through early June 2026; files are uncleaned | Run the supplementary query for the CUSIPs the screen missed (list in the local manifest); extend the bridge to the issuer programs the screen covers but the deal match does not. Cleaning is done by `src/clean_trace_trades.py`. Re-pull the tail from the enhanced table once it covers 2026, and reconcile the two tables' column sets explicitly. |
| Swiss Re 2026 ILS Market Insights PDFs | February and July landing pages are live; automated requests returned HTTP 403 and no stable public PDF endpoint was exposed | Download both through their publication forms, verify the files, and archive them as manual pulls. |
| Brookmont 2026 historical NAV | The 2026-09-03 issuer snapshot has current NAV and 2026 holdings, but its embedded daily history still ends 2025-12-31 | Use an official administrator or issuer history feed when one becomes available. Keep exchange prices separately labelled. |
| Aon aggregate price-versus-guidance | The 2025 annual report publishes tranche size, expected loss, and initial spread, but no aggregate guidance series | Retain as a documented source limitation; do not manufacture an aggregate. |
| GC quarterly and Howden full reports | No current standalone GC Securities quarterly series was found; Howden's full report is contact-gated | Retain these as explicit access gaps until first-party files are obtained. |

## Tier 2 inventory

Pull these when their analysis track begins, except for snapshot-only sources,
which must be archived immediately and repeatedly.

| Track | Dataset | Canonical source | Frequency / coverage | Access / license | State |
|---|---|---|---|---|---|
| Fund flow | Form N-PORT holdings for cat-bond interval funds | [SEC EDGAR search](https://www.sec.gov/edgar/search-and-access) | Quarterly; filing-dependent | U.S. government filing data; obey SEC rate limits | Planned for holder track. |
| Fund flow | Form ADV for ILS managers | [SEC IAPD](https://adviserinfo.sec.gov/) | Annual | Public regulatory filings; SEC terms/rate limits | Planned for holder track. |
| Fund flow | Artemis ILS manager directory | [Artemis directory](https://www.artemis.bm/ils-fund-managers/) | Current-state snapshot only | Artemis copyright/database rights; local archive only | First snapshot archived 2026-08-30; refresh monthly and submit URLs to the Wayback Machine separately. |
| Event studies | PCS industry-loss estimates and revision paths | [Verisk PCS](https://www.verisk.com/insurance/products/property-claim-services/) | Event-driven; headline estimates often public, full data paid | Mixed public/paywalled | Planned; capture each estimate with publication date. |
| Event studies | Swiss Re sigma insured-loss aggregates | [Swiss Re sigma research](https://www.swissre.com/institute/research/sigma-research.html) | Annual | Public reports; Swiss Re copyright | Planned; primary aggregate series. |
| Event studies | Munich Re NatCatSERVICE aggregates | [NatCatSERVICE](https://www.munichre.com/en/solutions/for-industry-clients/natcatservice.html) | Annual | Public summaries; detailed access terms vary | Planned; primary aggregate series. |
| Event studies | HURDAT2 and IBTrACS | [NOAA HURDAT2](https://www.nhc.noaa.gov/data/#hurdat), [NOAA IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive) | Best-track releases | U.S. government/open-data terms | Already available outside this pull. |
| Event studies | CSU and NOAA seasonal outlooks; ONI ENSO | [CSU forecasts](https://tropical.colostate.edu/forecasting.html), [NOAA outlook](https://www.cpc.ncep.noaa.gov/products/outlooks/hurricane.shtml), [NOAA ONI](https://origin.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php) | Forecast issue dates / monthly | Public; source terms apply | Planned; retain original issue timestamps for event studies. |
| Event studies | Verisk and Moody's RMS model release dates | [Verisk newsroom](https://www.verisk.com/newsroom/), [Moody's RMS newsroom](https://www.rms.com/newsroom) | Event-driven | Public press releases; publisher copyright | Planned; derive version-change events from text. |
| Parametric catalog | World Bank IBRD cat-bond terms and releases | [World Bank capital-at-risk notes](https://treasury.worldbank.org/en/about/unit/treasury/ibrd-financial-products/capital-at-risk-notes) | Event-driven | Public documents; World Bank terms | Planned. |
| Parametric catalog | ARC, CCRIF, and PCRIC payout history | [ARC](https://www.arc.int/), [CCRIF](https://www.ccrif.org/), [PCRIC](https://pcric.org/) | Annual reports / event releases | Public documents; publisher terms | Planned; payouts require text derivation. |
| Parametric catalog | BMA and Cayman SPI registers | [BMA registered entities](https://www.bma.bm/registered-entities), [CIMA insurance](https://www.cima.ky/insurance) | Current-state registers | Public regulator data; terms apply | Snapshot source: archive when track starts. |
| Adaptation | NFIP policies/claims and FEMA mitigation grants | [OpenFEMA](https://www.fema.gov/about/openfema/data-sets) | Dataset-dependent | U.S. government/open-data terms | Planned. |
| Adaptation | ISO BCEGS snapshot | [FEMA BCEGS page](https://www.fema.gov/emergency-managers/risk-management/building-science/building-code-save-study) | Snapshot / irregular | Public FEMA material; underlying ISO ratings may have restrictions | Planned; confirm redistributability before storage. |

### Prediction and market-belief signals

| Dataset | Signal and intended use | Frequency / coverage | Access / license | State |
|---|---|---|---|---|
| MarketPsych Country Sentiment | Daily natural-disaster and weather-event buzz/sentiment for aligning media attention with probability and price changes | Daily, 1998-01-01 through 2025-12-31 in the current US/UK pull | Licensed Penn WRDS research input; do not redistribute | US/UK country extract archived. City-level NYC/London coverage remains a possible later pull. |
| RavenPack RPA 1.0 | Intraday warning and warning-lifted event taxonomy for defining ex-ante catastrophe information shocks | Taxonomy current at pull; underlying event data described as 2000 onward | Licensed Penn WRDS research input; do not redistribute | Full taxonomy archived. Entity mapping and timestamped Global Macro events are not yet pulled. |
| OptionMetrics IvyDB US | Option-implied tail risk for insurers, reinsurers, and insurance ETFs | Daily, 1996 onward according to the saved WRDS audit | Licensed Penn WRDS research input | Planned; no data export archived yet. |
| Kalshi and Polymarket climate-event contracts | Actual event probabilities and price paths for hurricane, named-storm, and city-temperature markets | Daily Tier 1 discovery snapshots; full public history endpoints supported separately | Off-WRDS; platform/API terms must be reviewed at pull time | Puller implemented and first complete snapshots archived 2026-09-03. Daily metadata capture is scheduled separately from historical backfills. Storm class fully backfilled; temperature history deferred 2026-09-14. See the hazard coverage table for perils not yet covered. |

## NOAA billion-dollar disasters caveat

Verified 2026-08-30: NOAA ceased operating its Billion-Dollar Weather and
Climate Disasters project in May 2025. [Climate Central now maintains the
database](https://www.climatecentral.org/climate-services/billion-dollar-disasters),
kept the peer-reviewed methodology, published a full 2025 review, and exposes
CSV/JSON/XML downloads. Treat Climate Central as the current steward, but keep
Swiss Re sigma and Munich Re NatCatSERVICE as the primary insured-loss
comparators because the billion-dollar-disaster series measures broader direct
economic losses and is not an insured-loss series.
