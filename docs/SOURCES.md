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
transactions**. The next WRDS pull should use the curated CUSIP universe to
query `trace_enhanced.trace_btds144a_enhanced` (or the standard 144A trade
table where necessary).

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

The other authenticated/manual handoffs, including the raw TRACE transaction
query that must wait for a curated CUSIP universe, are specified in
`docs/MANUAL_DATA_PULLS.md`.

## Acquisition and extraction gaps

| Gap | Current evidence | Resolution path |
|---|---|---|
| Bloomberg index histories | The methodology is archived, but observations are available through a licensed terminal | Export the six weekly series using the acceptance checklist in `docs/MANUAL_DATA_PULLS.md`. |
| Raw WRDS BTDS 144A transactions | The archived TRACE/FISD files are masters, not trades; the trade query depends on the curated CUSIP universe | After the independently built deal-to-CUSIP bridge is ready, query `trace_enhanced.trace_btds144a_enhanced` and preserve WRDS screens/query metadata locally. |
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
| Kalshi and Polymarket climate-event contracts | Actual event probabilities and price paths for hurricane, named-storm, and city-temperature markets | Daily Tier 1 discovery snapshots; full public history endpoints supported separately | Off-WRDS; platform/API terms must be reviewed at pull time | Puller implemented and first complete snapshots archived 2026-09-03. Daily metadata capture is scheduled separately from large historical backfills. |

## NOAA billion-dollar disasters caveat

Verified 2026-08-30: NOAA ceased operating its Billion-Dollar Weather and
Climate Disasters project in May 2025. [Climate Central now maintains the
database](https://www.climatecentral.org/climate-services/billion-dollar-disasters),
kept the peer-reviewed methodology, published a full 2025 review, and exposes
CSV/JSON/XML downloads. Treat Climate Central as the current steward, but keep
Swiss Re sigma and Munich Re NatCatSERVICE as the primary insured-loss
comparators because the billion-dollar-disaster series measures broader direct
economic losses and is not an insured-loss series.
