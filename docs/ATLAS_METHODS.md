# Market atlas: method, weights and annualisation

The atlas (`src/build_atlas.py`, rendered by `src/render_atlas.py` to
`data/atlas/atlas.html`) describes the cat bond market from the parsed
Artemis tables and the joins already built in this repository. It is
descriptive. It is not evidence for substitution or for any other
hypothesis, and the Phase 3 reading of it should be stated in advance
(what pattern would distinguish investor reallocation from a common
capital-cycle effect) before the charts are read for it.

This page states the conventions every atlas table uses, so that a chart's
number can be reproduced and its coverage read beside it.

## Universe

One row per directory deal (`deals.csv`, 1,311 at the last build). Every
deal is in exactly one segment, decided in this order from the peril text
and the issuer name:

1. `mortgage`: the peril names mortgage insurance, or the issuer is a known
   mortgage ILS programme (Bellemeade, Oaktown, Eagle Re, Radnor, Home Re,
   Triangle Re, Cherry Blossom, Greystone, Sierra, Splitrock).
2. `life_health`: mortality, longevity, medical, health, pandemic, life
   insurance or life reinsurance, lapse.
3. `cyber`.
4. `other_specialty`: terror, lottery, aviation, marine, energy, crop and
   agriculture, liability, workers' compensation, operational risk,
   satellite and space, motor and auto physical damage, shipping, credit
   (trade credit, credit reinsurance), financial guarantee, event
   cancellation, casualty, temperature.
5. `private_lite`: the directory marks the deal private and none of the
   above applies.
6. `core_property_cat`: everything else, including peril text that only
   says "property catastrophe risks".

A deal whose peril text names both a specialty line and a property
catastrophe peril ("U.S. hurricane, UK extreme mortality") stays in the
core (or in private/lite if private) with `mixed_peril` set. Mortgage
always wins. The core is the study universe; the other five are reported
beside it and never folded in.

## Sponsor type

A keyword classification of the parsed sponsor name, tried in the order
public sector, reinsurer, insurer; a name matching none is
`corporate_other`. A blank sponsor on a private deal is `undisclosed`
(the sponsor is not published); a blank on any other deal is `unknown`.
The rules are the regular expressions in `build_atlas.py`. The rows the
rules leave as `corporate_other` or `unknown` are written to
`data/atlas/review_sponsor_type.csv` with a blank `review` column for a
hand check; a reviewed value belongs in the rules, not in the CSV.

## Hazard classes and the peril split

The chart is titled "issued principal allocated by peril" because that is
what it is: an accounting allocation. Core deals only. The peril text is mapped with the panel builder's lexicon
(`map_perils` in `src/build_deal_panel.py`), which names a hazard class and
a region per phrase. A deal naming k classes counts once in each class and
its issued size is split k ways, equally; `deals_multi` in
`peril_by_year.csv` says how many of a cell's deals were split. Text that
names no hazard but calls the deal multi-peril ("Multi peril", "Worldwide
all perils", "Global peak perils") is one class, `multi_peril_unspecified`;
text the lexicon does not recognise at all is `unmapped`. Both are listed
in `data/atlas/review_hazard_class.csv`, and both set `generic_peril` on
the deal in `universe_deals.csv`.

The equal split is a convention, not an estimate of exposure. A deal
covering US hurricane and US earthquake is almost always mostly hurricane
by expected loss, and the split does not know that. Expected-loss
weighting by peril would need the per-peril contribution the deal pages
sometimes state and the parser does not yet read.

## Issue year and annual tables

The issue year is the four-digit year in the directory's date-of-issue
text. Annual tables (`*_by_year.csv`) count deals by issue year and sum
issued principal in USD millions. Every annual row also carries the year's
total deals and the row's share of them, so a chart can state its coverage.

## Sizes and weights

Issued principal is the directory's deal size, converted as follows:
`usd` when stated in dollars; `usd_equiv` when the page gives a dollar
equivalent in brackets after a non-USD size; `non_usd_unconverted` when it
does not (32 deals, counted but not summed); `missing` when no size is
parsed (11). No FX conversion is done in the atlas; the roll-forward uses
its own monthly FX table on the parser side.

Tranche-level statistics in `layer_by_year.csv` are reported two ways:

- **Equal weight across tranches**: the medians (`median_ap`, `median_el`,
  `median_spread`, `median_guidance_mid`). Each tranche counts once.
- **Size weight**: `size_weighted_spread`, the spread weighted by the
  tranche's final size in USD, over the tranches that have both a spread
  and a dollar size. Non-USD tranche sizes are counted in `tranches` but
  excluded from the weighting.

Every cell carries `n_ap`, `n_el`, `n_spread`, `n_guidance` and
`n_sized_usd` beside `tranches`, so the number behind a median is always
visible. Spread is the parsed risk-margin spread at pricing; the
price-guidance midpoint is reported beside it with its own count and is
not a substitute for it.

## Bands: expected loss as the pricing view, attachment probability as the layer view

Two band tables share the same edges, in percent: below 1, 1 to 2, 2 to
4, 4 to 8, 8 and above, lower edge inclusive, `<metric>_unknown` where the
value is not stated.

- `layer_by_year_el.csv` bands on **expected loss**. This is the primary
  pricing view: expected loss is stated on 1,037 of 2,052 tranches and on
  87% to 100% of core issued principal in every year from 2016. It is not a
  layer. Expected loss folds the chance of attachment and the severity
  given attachment together, so two bonds in one band can attach at very
  different probabilities.
- `layer_by_year.csv` bands on **attachment probability**, the layer
  language. It is a source gap, not a parser gap, for 2019 to 2021: the
  pages of those years state it on 6 to 13 of 43 to 73 core tranches (8%
  to 44% of principal), and only 2 of 115 pages without it name one at
  all. From 2022 it covers 56% of principal and from 2023 90% or more. Any
  layer-overlap comparison against reinsurance pricing should use this
  view, and only in years whose coverage supports it.

`layer_coverage_by_year.csv` gives, per segment and year, the tranches
and issued USD with expected loss, with attachment probability, with both
(740 core tranches), and with expected loss plus a settled spread, so a
chart can state which years each view can carry. Where sample size
permits, a continuous expected-loss adjustment of spread is preferable to
the bands, which put a 1.99% and a 2.01% tranche in different cells.

## Outstanding principal by segment

The parser's roll-forward ledger (`src/roll_forward.py` in the parser
repository), run by the parser's own interpreter, with TRACE maturities
from `data/bridge.csv` and class-level repayment from
`data/bridge_cusip_classes.csv`. Each deal is issued at its issue month,
written down at the loss month of a settled loss (the default
`--loss-timing loss`; `settlement` is the alternative and is not uniformly
closer to the publisher), recovered where the page states a recovery, and
repaid at its maturity. The stock is the closing balance at December of
each year and at the as-of month for the last year (2026-08 at the last
build). The segment is the deal's atlas segment. Mortgage ILS amortise and
are carried at face to maturity, so that segment is an upper bound.

## Fund flows

Net subscriptions per SEC-registered fund lineage per month from the
N-PORT filings (`data/processed/nport/fund_flows.csv`), predecessor and
successor funds collapsed to one lineage. Flows are monthly sums, not
annualised; a month in which any fund of the lineage has no flow is left
null, not zero, and `months_null` says how many. Event windows (Ian
2022-08 to 2022-11, Milton 2024-09 to 2024-12) are marked, not tested.

## Marks versus trades

Per quarter: the number of fund-position and TRACE pairs, the median and
the median absolute gap between the fund's mark and the TRACE
volume-weighted price in the window, the 90th percentile of the absolute
gap, the share of marks flagged stale, and the share with an absolute gap
over 5 points. Built from `data/fund_marks_vs_trace.csv`.

## Comparators

The Guy Carpenter rate-on-line index, Lane's weighted premium and expected
loss, and Aon's property-cat issuance are shown in their own panels, in
their own units, with the number of years each covers. They are not
rescaled onto the atlas's axes.

## Reproduction

    ./.venv/bin/python src/build_atlas.py      # tables and summary.json under data/atlas/
    ./.venv/bin/python src/render_atlas.py     # data/atlas/atlas.html
    ./.venv/bin/python -m unittest tests.test_build_atlas

`summary.json` records the coverage counts behind every table and which
interpreter built the roll-forward book.
