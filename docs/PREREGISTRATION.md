# Pre-registration: substitution between cat bonds and traditional reinsurance

**Status: frozen for signature on 2026-11-19 after three reviews.
No further edits except by a dated, signed amendment. The substitution
analysis is paused until section 8 is signed.**
Nothing below has been run. The point of writing it first is that the
atlas is descriptive, spread co-movement plus fund inflows is consistent
with several mechanisms, and a test that cannot lose is not a test. The
deciding test is a differential in primary-market pricing and issuance
(H1). Fund flows and secondary-market prices are descriptive context
with their tabulation rules fixed here; they do not decide anything in
this design. Every choice carries the count behind it; change any of
them, then date and commit before the atlas is read for substitution.
Counts are core tranches with both spread and expected loss stated unless
a line says otherwise. Where a choice had two candidate rules, one is
primary and the other a labelled sensitivity; sensitivities are reported
but never decide.

## 1. Two hypotheses, kept apart

**H1, sponsor substitution.** Sponsors buy more cat bond protection in
the layers where traditional reinsurance became expensive, and less where
it became cheap. Evidence is in issuance and pricing: the share and the
risk-adjusted spread of cat bonds in the overlapping layers relative to
the others. This is the hypothesis the design tests.

**H2, investor reallocation.** Investors move capital into cat bond
vehicles when their relative return rises. Evidence would be in demand:
net subscriptions into the registered cat bond funds, and relative
pricing in comparable bonds in the secondary market. This design does
not decide H2: the secondary-market price series is not a spread series
(section 2) and the registered funds are a small slice of the investor
base. Both are tabulated as context under fixed rules, and section 7
says what a test of H2 would need.

**H0, common capital cycle.** One reinsurance capital cycle moves cat
bond pricing and traditional pricing together, in every layer, with no
differential. This is the result the test must be able to return.

**Not testable here.** Whether the same capital left traditional
reinsurance and entered cat bonds. That needs a source-of-funds link this
data does not have. The write-up says so and does not infer it.

## 2. Definitions fixed in advance

**Overlap group.** Core property-cat tranches whose terms match where
traditional reinsurance programmes attach: peril US hurricane, alone or
within a US multi-peril deal (hazard class contains
`hurricane_or_named_storm`); trigger indemnity; attachment probability
stated and in the 2% to 8% bands (2% inclusive, 8% exclusive); issue
years 2023 to 2026. Taken from `universe_deals.csv` (full peril tags,
never the equal split) and the parser's tranches table.

Why: indemnity US hurricane is the product a Florida or nationwide
reinsurance programme buys; the 2% to 8% attachment bands are where the
working layers of those programmes sit, the below-1% band being remote
cover reinsurance rarely writes. Tranches with spread and expected loss in
this group: 2022 5, 2023 20, 2024 22, 2025 35, 2026 41, from 15, 18, 26
and 29 deals in 2023 to 2026. 2022 is below the cell minimum, so the
overlap group begins in 2023, the hard-market step year. Of the US
hurricane indemnity tranches issued 2022 to 2026 with an attachment
probability, 135 of 265 fall in the 2% to 8% bands.

**Comparison group.** Primary: US hurricane tranches whose trigger is
industry loss index, parametric, parametric index or modelled loss (the
parser's `trigger_type` values; "Multiple trigger types" is excluded),
any attachment band, issue years 2022 to 2026. Same peril and cycle, a
product reinsurance programmes do not buy in the same way. Robustness
groups, reported but never deciding: non-US perils with an attachment
probability stated; remote US hurricane indemnity layers below 1%.

Why: the index-trigger group is the only comparison with enough tranches
every year (2022 16, 2023 15, 2024 26, 2025 27, 2026 22; 100
industry-loss-index and 6 parametric tranches); non-US has 3, 11, 11,
23, 12; remote layers 2, 6, 3, 5, 8.

**Risk-adjusted spread and the differential.** One pooled regression
over the overlap and comparison tranches issued 2023 to 2026 (the
comparison group's 2022 tranches appear in the detail tables only),
estimated by ordinary least squares, one tranche one observation:

    spread_i = sum_y a_y * Y_iy
             + sum_y b_y * (Y_iy * EL_i)
             + sum_y g_y * (Y_iy * overlap_i)
             + m_{month(i)} + f * AIR_i + e_i

where Y_iy is the indicator for issue year y in {2023, 2024, 2025,
2026}, EL_i is expected loss in percentage points, overlap_i is 1 for the
overlap group and 0 for the comparison group, m_{month(i)} is a fixed
effect for the calendar month of issue (12 levels, present for every
tranche), and AIR_i is 1 where the modelling firm stated on the page is
AIR (95 of the overlap tranches; RMS, KatRisk and unstated form the
base). The group coefficient g_y is the expected-loss-adjusted gap
between the groups in year y, net of month and firm. Because b_y is
year-specific, a change in the slope of spread on expected loss between
years (the expected-loss-by-cycle interaction the literature reports) is
absorbed and does not enter the differential; no further adjustment is
subtracted.

The sign conditions of section 4 read g_2025 - g_2024 and g_2026 -
g_2024 (softening) and g_2024 - g_2023 (step) from this fit. The
deciding interval is on the pooled softening differential D from a
second fit of the same equation in which the two softening-year group
terms are replaced by one, g_soft * (S_i * overlap_i) with S_i = 1 for
issue years 2025 and 2026, all year intercepts a_y and year-specific
slopes b_y kept, so that

    D = g_soft - g_2024.

Three specification sensitivities are reported beside the primary fit,
each with the same controls: (i) log expected loss in place of expected
loss, since a linear slope misfits if the true relation is curved and
the groups sit at different expected-loss levels; (ii) group-specific
slopes, b_y differing by group, with g_y evaluated at the overlap group's
mean expected loss for that year; (iii) the band comparison, spread
minus expected loss averaged within a cell with no controls. Size
weighting of the primary fit is a fourth sensitivity. Every overlap and
comparison cell has at least 10 tranches from 2023 (overlap 20, 22, 35,
41; comparison 15, 26, 27, 22), 218 tranches in the fit.

Why: the comparison group carries higher expected loss (median 2.5 to 4.4
by year against 2.3 to 2.5 in the overlap group), so a band average would
mix layer with risk level; and final tranche size is stated for 77% of
overlap tranches, so weighting would drop the rest.

**Cycle dating.** The Guy Carpenter global property-catastrophe
rate-on-line index (2000 = 100) dates the cycle: 130 at the 2021 renewal,
145 in 2022, 187 in 2023 (the step), 191 in 2024 (the peak), 178 in 2025,
156 in 2026. So: hard-market step at the 1 January 2023 renewal, peak at
1 January 2024, softening at 2025 and 2026. The global index dates the
cycle only. It cannot say that a specific reinsurance layer became cheaper
relative to its cat bond counterpart, because renewal outcomes vary by
region and attachment; the result therefore stays at the level of
differential cat bond pricing and issuance around renewals.

**Cell and windows.** The issue year is the cell that decides. Renewal
windows are supporting detail: 1 January (issues of July to December,
assigned to the renewal they precede) and mid-year (issues of January to
June, the Florida 1 June renewal and the 1 July renewal taken together).

Why: the 1 July window on its own is empty for the overlap group (0, 0, 0
and 1 tranche in 2023 to 2026) and the 1 January window is at or below
the cell minimum (9, 8, 11, 1), while the mid-year window carries most
issuance (11, 14, 24, 40); only the year is populated enough to decide.

**Issuance share (P2).** One definition for every year, 2020 to 2026,
because attachment probability is not on the page before 2022 and a
series that switches from an expected-loss definition to an attachment
definition would move with the definition. The proxy group is US
hurricane indemnity tranches with expected loss stated and in the 1% to
4% band (1% inclusive, 4% exclusive), the expected-loss band that holds
110 of the 129 overlap tranches of 2023 to 2026. Numerator: the sum of
final tranche size in US dollars for proxy-group tranches; where a
tranche has no final size, its deal's size divided equally among the
deal's tranches is used, and the share so filled is reported (20 of 235
proxy tranches 2020 to 2026 lack a final size). Denominator: core
property-cat issued principal in US dollars for the year, from
`universe_by_year.csv` (deal sizes; 2 to 7 core deals a year carry no
dollar size and are excluded from both sides, 35 of 834 overall, 26 of
them non-USD deals not converted). Proxy tranches with expected loss but
no spread stay in P2, so its counts are 19, 17, 25, 33, 34, 53, 54 for
2020 to 2026 (12, 15, 19, 27, 23, 32, 34 deals). The attachment-defined
overlap group's share is reported from 2023 beside the proxy series as
detail.

**Data cutoff and the 2026 cell.** The directory was crawled on
2026-08-29 and the parsed deals run to August 2026; TRACE runs to
2026-06-05; N-PORT flows run to July 2026. The 2026 cell is therefore
partial and is labelled so everywhere. Rules: for P1 the 2026 cell uses
every 2026 tranche in hand (all overlap tranches of 2026 were issued
January to July), with issue month as a control in the pooled
regression; as a sensitivity, 2024 and 2025 are restricted to January to
August issues. For P2 the primary 2026 comparison restricts every prior
year to January to August issues, and the full-year series stops at 2025.
Flows and secondary prices stop at their own cutoffs, with prior years
restricted to the same months where a comparison is drawn. If the
directory is re-crawled before the analysis runs, the 2026 cell is
re-cut at the re-crawl date and that date replaces 2026-08-29 in the
results; otherwise 2026-08-29 stands.

**Fund demand, descriptive.** Net subscriptions per registered lineage
per month from the N-PORT filings, sales minus redemptions, so already
free of returns (`fund_flows_by_month.csv`). Months with a null flow stay
null. Tabulation: the sum across the six lineages (Stone Ridge interval,
Stone Ridge high yield, Pioneer ILS interval, Victory Pioneer cat bond,
CNR select strategies, Brookmont ETF) by quarter and by year; a quarter
or year is reported as complete only when every lineage alive in it has
no null month, otherwise it is shown with the null count and the
lineages missing; the Stone Ridge interval fund is also shown alone,
because the atlas has already established (Figure 13 of the walkthrough)
that capital moved out of it and into the higher-yield and pure cat bond
vehicles from 2023. "Flat" means an aggregate net flow within 1% of the
lineages' combined net assets at the start of the period; "positive" and
"negative" are beyond that band. Coverage from 2022: four lineages
complete or near complete (at most 3 null months), Victory Pioneer from
November 2022, the ETF from April 2025.

**Secondary-market prices, descriptive.** Customer trades (TRACE contra
party C) on CUSIPs bridged at high confidence to overlap or comparison
deals, monthly volume-weighted average price per CUSIP, the change in the
group mean between windows, shown only where at least 10 CUSIPs trade in
both windows. This is a price series, not a spread series: a traded price
moves with coupon, remaining term, the floating leg, seasonality inside
the risk period and accrued loss expectations, none of which is adjusted
here, so it is shown as context and read for nothing. Coverage: 48 of
the 80 overlap deals and 46 of the 68 comparison deals are bridged at
high confidence (106 and 73 CUSIPs); CUSIPs with customer trades in 2023
to 2026 are 15, 37, 58, 67 for the overlap group and 22, 39, 54, 42 for
the comparison group.

## 3. Predictions, stated before looking

If H1 holds, after the rate-on-line peak and into the softening:

- P1. The overlap group's expected-loss-adjusted spread falls relative to
  the comparison group's between the 2024 peak and the 2025 and 2026
  softening: g_2025 - g_2024 < 0 and g_2026 - g_2024 < 0. The 2023 to
  2024 step is reported too, with the prediction that the overlap group
  rose at least as much as the comparison group, g_2024 - g_2023 >= 0.
- P2. The proxy group's share of core issued principal in 2025 and 2026
  (January to August) is above its 2020 to 2022 mean by more than two
  percentage points in both years. P2 is a disclosed, non-blind
  supplementary condition (see the disclosure below): it gates the
  "pattern consistent with H1" state in section 4 and decides nothing
  on its own.

If H0 holds: P1 shows no differential (both groups move together) and P2
is flat.

Disclosure: the P2 proxy series was computed on 2026-11-19 while its
coverage and the missing-size fill were being checked, and the author of
this document saw the share by year. P2 is therefore not blind at
sign-off. Its rule is kept as written and its status is fixed as a
disclosed, non-blind supplementary condition: it is one of the
conditions for the "pattern consistent with H1" state and nothing else
rests on it. P1 has not been estimated in any form and is the deciding
test. The write-up states this wherever P2 is shown.

Context, not predictions: P3, the fund-flow tabulation, and the
secondary-market price tabulation of section 2 are shown for the same
windows. A reading where P1 and P2 hold while registered-fund flows are
negative or flat is described as sponsor-side; one where flows are
strongly positive is described as consistent with either hypothesis; no
reading of H2 is made.

## 4. Decision rule

- A differential is reported only where both groups have at least 10
  tranches with spread and expected loss in the cell. Fewer: the test is
  inconclusive for that window, and is reported as inconclusive, not
  omitted. At 10 per cell the year is populated for the overlap group
  from 2023 and for the comparison group from 2022; renewal windows are
  shown as supporting detail and never decide.
- Uncertainty: a cluster bootstrap by deal, 2,000 resamples, drawing
  deals with replacement within each year and group and keeping every
  tranche of a drawn deal, so that tranches of one deal (same sponsor,
  date, modeller and prose) are never treated as independent. A 90%
  percentile interval is reported for each differential and for the
  pooled softening differential (2025 and 2026 together against 2024,
  a year indicator for 2026 included). Deals behind the overlap cells:
  15, 18, 26, 29.
- Reading, in three states and no others:
  - **Pattern consistent with H1**: g_2025 - g_2024 and g_2026 - g_2024
    both negative in the primary fit, the 90% cluster-bootstrap interval
    for D excludes zero, and P2 holds (the disclosed, non-blind
    supplementary condition of section 3).
  - **Pattern contrary to H1**: both softening differentials non-negative.
  - **Inconclusive**: anything else, including both negative with an
    interval for D that covers zero, one year each way, or P1 holding
    while P2 is flat or mixed.
  The primary comparison group and the primary fit decide; the
  robustness groups and every sensitivity (log expected loss, group
  slopes, band, size-weighted, sponsor fixed effects, the composition
  check, the January-to-August restriction) are reported beside them and
  may add a stated qualification to the write-up but never change the
  state. No significance threshold other than the interval rule is used.
- P2's reference level is the proxy share's mean over 2020 to 2022, on
  January to August issuance for the 2026 comparison and on full years
  for 2025. Three mutually exclusive outcomes: P2 "holds" if both 2025
  and 2026 exceed that mean by more than two percentage points; P2 "is
  flat" if both lie within two percentage points of it (above or below);
  P2 is "mixed" otherwise, including both years more than two points
  below the mean. The two-point width is the rounding of the share to
  whole points plus the filled-size share, not an effect size.
- Parallel moves in both groups are reported as consistent with H0.
- Composition check: the primary fit is re-run with the comparison group
  restricted to the overlap group's expected-loss band (1% to 4%). This
  is a sensitivity and does not change the formal state. If the
  differential changes sign or its restricted interval covers zero, the
  write-up carries the qualification "not robust to the expected-loss
  band restriction" next to the state, states that a composition effect
  cannot be excluded, and shows both fits. The restricted comparison
  cells hold 13, 13, 19 and 8 tranches in 2023 to 2026, so the 2026
  restricted check is inconclusive by the cell rule and is said to be.

## 5. What else could produce the pattern, and what is checked

- Expected-loss mix shifting between the groups (handled by the
  regression, with the log and group-slope specifications and the
  composition check of section 4 as qualifying sensitivities).
- Trigger mix: a move toward indemnity is itself a sponsor choice and is
  reported separately, not folded into P1.
- Issue size: larger deals price tighter; the size-weighted differential
  is the sensitivity.
- Florida-specific changes: the Florida legislative reforms of December
  2022 (SB 2-A) and the 2023 session changed litigation and the state
  reinsurance backstop, shifting demand for Florida layers for reasons
  unrelated to reinsurance pricing; the Florida share of the overlap
  group is reported per window (19% of overlap tranches from 2022 name
  Florida in their peril text).
- Retrocession and collateralised reinsurance pricing, which the data
  does not hold; named as an unobserved alternative.
- Added from the literature (section 6):
  - Sponsor identity explains about a quarter of issue-price variation
    and its effect strengthens in hard markets. A within-sponsor
    comparison is not feasible and is dropped: no sponsor issues in both
    groups in the same year in 2023, 2024 or 2026 and two do in 2025;
    pooled over the four years, 5 of the 50 overlap sponsors appear in
    the comparison group. The sensitivity instead is the pooled
    regression with sponsor fixed effects and year-by-group terms,
    identified from the 24 of 50 overlap sponsors with two or more
    tranches.
  - Hurricane seasonality moves single-peril hurricane spreads by up to
    half; the issue-month fixed effect in the primary fit is the control.
  - A liquidity premium of about a fifth of the spread, larger for
    higher-risk bonds, sits inside spread minus EL and varies with layer;
    the differential is on primary-market spreads only, where the
    liquidity premium is set at issue and does not move between the
    groups within a window.
  - EL model vintage changes (the modelling firms' updates after Ian)
    raise stated EL on the overlap group more than on remote layers. The
    model version is never stated on the pages and a pre-update cohort
    cannot be formed; the modelling firm is stated for 99% of overlap
    tranches (AIR 95, RMS 18, KatRisk 4), so the AIR indicator in the
    primary fit is the control and the differential is also shown for
    the AIR-modelled tranches alone. The vintage effect is named as an
    unobserved alternative in the write-up.
  - The cycle effect on spreads is state-dependent and interacts with EL,
    so a differential by layer could arise from pricing mechanics alone;
    the year-specific slope b_y in the regression is the rule, and the
    log and group-slope specifications are its checks.
  - Investors moved to remote layers in late 2022 by their own account; a
    falling overlap share can be investor de-risking. P2 is therefore read
    with the flow tabulation beside it. The share of overlap issuance
    upsized at pricing is reported as context only: a size change at
    pricing is recorded for 43% of overlap tranches, nearly all upsizes,
    and the absence of a record is not evidence that the size held, so
    the share is not a rule input.

## 6. Literature

The list is in `docs/LITERATURE.md` (30 entries, each marked by how it
was verified). What it settles for the design, before anything is run:

- Not novel, and not to be claimed: the rate-on-line index as a cycle
  regressor on issue spreads (Braun 2016; Chen et al. 2024;
  Suttakulpiboon 2025, who already runs a break test at end-2021 on the
  same index); spread minus EL as the risk-adjusted price (Lane and Mahul
  2008 onward); substitution being stronger in hard markets at the cedent
  level, dated with the same Guy Carpenter index (Yu and Zhao 2025).
- What would be new: the layer-overlap classification as the treatment
  (Götze and Gürtler 2022, Subramanian and Wang 2018 and Trottier and Lai
  2017 predict a layer-specific margin but do not construct it), and
  registered-fund net subscriptions as a demand measure (no precedent at
  all; the one thesis found is unverified).
- What the list argues against: a single 2023 window with an annual index
  as the only cycle measure is one episode confounded with Ian loss
  creep, collateral yields and EL model updates; the layer comparison is
  confounded by EL level; registered US funds are a small slice of the
  specialist-fund base that prices the market (Tomunen 2024); and
  substitution is not one-directional even at the cedent level, since
  cat bonds reduced affiliate reinsurance but increased external
  reinsurance in hard markets (Yu and Zhao 2025). The controls added to
  section 5 answer the second and third; the first and fourth are
  limits the write-up states, not ones the design removes.

## 7. What is reported regardless of outcome, and what H2 would need

Reported in every case: the overlap, comparison and proxy definitions,
the counts and deals behind every cell, each differential with its sign,
size and 90% interval, the three-state reading and which rule produced
it, every sensitivity beside the primary estimate, the P2 series with its
filled share, the flow and secondary-price tabulations with their
completeness flags, the inconclusive windows, and the data cutoff used.
The descriptive atlas is presented as description in either case.

A test of H2 would need, and this design does not have: a secondary
spread series (traded price converted with coupon, remaining term and
the floating leg, which the bridge's TRACE coupon fields and the parser's
maturity fields could supply for bridged CUSIPs, not yet built); a demand
measure covering the specialist funds that hold most of the market, which
the registered-fund filings do not; and a pre-registered rule for both.
If those are built, they get their own pre-registration.

## 8. Choices resolved, for sign-off

Each line is one rule the analysis will follow. The alternative named is
reported as a sensitivity, never used to decide. Strike or amend any
line, date it, and commit; the analysis starts only after this section is
signed. Rows 1 to 12 were resolved on 2026-11-19 in the morning; rows
marked (r) were revised and rows 13 to 16 added after the second review;
rows 2, 8 and 9 were tightened and row 17 added after the third review,
at which point the document was frozen. P1 has not been estimated in any
form at freezing.

| # | Choice | Rule | Alternative, demoted to sensitivity | Count behind it |
|---|---|---|---|---|
| 1 | Comparison trigger list | Industry loss index, parametric, parametric index, modelled loss | Non-US perils; remote US hurricane indemnity below 1% | 16, 15, 26, 27, 22 tranches 2022 to 2026 |
| 2 (r) | Risk adjustment | One pooled OLS fit, 2023 to 2026: year intercepts, year-specific expected-loss slopes, year-specific group gaps, issue-month fixed effects, AIR indicator; D = g_soft - g_2024 from the restricted fit decides | Log expected loss; group-specific slopes at the overlap mean; band average; size-weighted | 218 tranches; every cell at least 10 |
| 3 | Weighting | Unweighted, one tranche one observation | Size-weighted | Final size stated for 77% of overlap tranches |
| 4 | Deciding cell | Issue year | 1 January and mid-year renewal windows as detail; 1 July folded into mid-year | 1 July window holds 0, 0, 0, 1 overlap tranches |
| 5 (r) | Fund flows | Descriptive only: six-lineage sum by quarter and year, complete only with no null month, Stone Ridge interval fund also alone, flat = within 1% of start net assets | None; H2 not decided | Four lineages complete from 2022; Victory Pioneer from Nov 2022; ETF from Apr 2025 |
| 6 (r) | Secondary prices | Descriptive only: monthly VWAP of customer trades on high-confidence CUSIPs, minimum 10 CUSIPs; a price series, not a spread series | None; H2 not decided | 15 to 67 overlap and 22 to 54 comparison CUSIPs a year |
| 7 (r) | Expected-loss-by-cycle interaction | Absorbed by the year-specific slope; the former extra subtraction is removed as double-adjusting | Log and group-slope specifications | Comparison EL median 2.5 to 4.4 against overlap 2.3 to 2.5 |
| 8 (r) | Reading | Three states: pattern consistent with H1 (both softening gaps negative, 90% interval for D excludes zero, P2 holds); pattern contrary to H1 (both non-negative); inconclusive otherwise. Sensitivities, the composition check included, add a stated qualification and never change the state | None | |
| 9 (r) | Issuance share, P2 | Disclosed, non-blind supplementary condition gating the consistent state only. One proxy definition for 2020 to 2026: US hurricane indemnity, expected loss 1% to 4%; holds = both years more than two points above the 2020 to 2022 mean; flat = both within two points; mixed otherwise | Attachment-defined share from 2023 as detail | 110 of 129 overlap tranches sit in the proxy band |
| 10 | Sponsor control | Pooled regression with sponsor fixed effects as sensitivity; within-sponsor comparison dropped | Within-sponsor (infeasible) | 0, 0, 2, 0 sponsors in both groups by year; 5 of 50 pooled |
| 11 | Model vintage | Modelling-firm indicator; AIR-only differential shown; version unobserved and said so | Pre-update cohort (infeasible) | Firm stated for 99% of overlap tranches; AIR 95, RMS 18 |
| 12 | Upsizing | Reported as context, not a rule input | None | Size change recorded for 43% of overlap tranches |
| 13 | P2 numerator and denominator | Final tranche size in USD, missing filled by deal size split equally across the deal's tranches and the filled share reported; over core property-cat issued principal in USD for the year | Unfilled numerator | 20 of 235 proxy tranches unsized; 35 of 834 core deals carry no USD size |
| 14 | 2026 cutoff | Directory crawl of 2026-08-29 (re-cut if re-crawled before the run); P1 uses all 2026 tranches with issue-month control; P2 compares January to August across years; flows to July 2026, TRACE to 2026-06-05; 2026 labelled partial | Prior years restricted to January to August for P1 | 2026 overlap issues span January to July |
| 15 | Uncertainty | Cluster bootstrap by deal, 2,000 resamples, 90% percentile interval, pooled softening differential | None | Overlap deals per cell 15, 18, 26, 29 |
| 16 | P2 blindness | Disclosed: the proxy share series was seen on 2026-11-19 during the coverage check; P2 is a non-blind supplementary condition; P1 is blind and decides | None | |
| 17 | Composition check | Sensitivity only: a sign change or an interval covering zero under the expected-loss band restriction adds the qualification "not robust to the band restriction" and never changes the state | None | Restricted comparison cells 13, 13, 19, 8 |

Signed: ____________________  Date: __________
