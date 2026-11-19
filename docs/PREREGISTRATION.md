# Pre-registration: substitution between cat bonds and traditional reinsurance

**Status: revised 2026-11-19 with every analysis choice resolved to one
rule; awaiting Caro's sign-off (section 8). The substitution analysis is
paused until then.**
Nothing below has been run. The point of writing it first is that the
atlas is descriptive, spread co-movement plus fund inflows is consistent
with several mechanisms, and a test that cannot lose is not a test. Every
choice below was filled from the data on 2026-11-18 and resolved on
2026-11-19 with its reason in the "Why" line and its count behind it;
change any of them, then date and commit before the atlas is read for
substitution. Counts are core tranches with both spread and expected loss
stated. Where a choice had two candidate rules, one is now primary and
the other is a labelled sensitivity; sensitivities are reported but never
decide.

## 1. Two hypotheses, kept apart

**H1, sponsor substitution.** Sponsors buy more cat bond protection in
the layers where traditional reinsurance became expensive, and less where
it became cheap. Evidence is in issuance and pricing: the share and the
risk-adjusted spread of cat bonds in the overlapping layers relative to
the others.

**H2, investor reallocation.** Investors move capital into cat bond
vehicles when their relative return rises. Evidence is in demand: net
subscriptions into the registered cat bond funds, and relative pricing in
comparable bonds in the secondary market.

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
this group: 2022 5, 2023 20, 2024 22, 2025 35, 2026 41. 2022 is below the
cell minimum, so the overlap group begins in 2023, the hard-market step
year. Of the US hurricane indemnity tranches issued 2022 to 2026 with an
attachment probability, 135 of 265 fall in the 2% to 8% bands.

**Comparison group.** Primary: US hurricane tranches whose trigger is
industry loss index, parametric, parametric index or modelled loss (the
parser's `trigger_type` values; "Multiple trigger types" is excluded),
any attachment band, issue years 2022 to 2026. Same peril and cycle, a
product reinsurance programmes do not buy in the same way. Robustness
groups, reported but never deciding: non-US perils with an attachment
probability stated; remote US hurricane indemnity layers below 1%.

Why: the index-trigger group is the only comparison with enough tranches
every year (recounted 2026-11-19 with the trigger list above: 2022 16,
2023 15, 2024 26, 2025 27, 2026 22; 100 industry-loss-index and 6
parametric tranches); non-US has 3, 11, 11, 23, 12; remote layers 2, 6,
3, 5, 8.

**Risk-adjusted spread.** Spread minus expected loss, in percentage
points. Resolved: the primary estimate is the continuous adjustment, a
regression of spread on expected loss within each issue year with both
groups pooled and a group indicator, the differential read from the
change in the group coefficient between windows; it is estimable in every
year from 2023 because every overlap and comparison cell has at least 10
tranches. The band comparison (spread minus expected loss averaged within
a cell) is the sensitivity. Resolved: cells are unweighted, one tranche
one observation; size weighting is a sensitivity.

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

**Cell and windows.** Resolved: the issue year is the cell that decides.
Renewal windows are supporting detail: 1 January (issues of July to
December, assigned to the renewal they precede) and mid-year (issues of
January to June, the Florida 1 June renewal and the 1 July renewal taken
together). Fund flows are read over the calendar quarter ending at the
renewal date.

Why: the 1 July window on its own is empty for the overlap group (0, 0, 0
and 1 tranche in 2023 to 2026) and the 1 January window is at or below
the cell minimum (9, 8, 11, 1), while the mid-year window carries most
issuance (11, 14, 24, 40); only the year is populated enough to decide. A
one-quarter flow window matches the N-PORT quarterly cadence and avoids
reading a single month's redemptions.

**Fund demand.** Net subscriptions per registered lineage per month from
the N-PORT filings, sales minus redemptions, so already free of returns
(`fund_flows_by_month.csv`). Months with a null flow stay null. Resolved:
P3 is read on the sum across the six lineages (Stone Ridge interval,
Stone Ridge high yield, Pioneer ILS interval, Victory Pioneer cat bond,
CNR select strategies, Brookmont ETF) for the months that are non-null,
with the Stone Ridge interval fund also shown on its own because the
atlas has already established (Figure 13 of the walkthrough) that capital
moved out of it and into the higher-yield and pure cat bond vehicles from
2023, a reallocation inside the registered universe that an aggregate
would hide. Coverage from 2022: four lineages complete or near complete
(at most 3 null months), Victory Pioneer from November 2022, the ETF from
April 2025.

**Secondary-market prices.** For the secondary-market version of P1 (the
test that separates H2 from H1): customer trades (TRACE contra party C)
on CUSIPs bridged at high confidence to overlap or comparison deals,
monthly volume-weighted average price per CUSIP, the change in the group
mean between windows. A cell needs at least 10 CUSIPs with a customer
trade in both windows. Coverage: 48 of the 80 overlap deals and 46 of the
68 comparison deals are bridged at high confidence (106 and 73 CUSIPs);
CUSIPs with customer trades in 2023 to 2026 are 15, 37, 58, 67 for the
overlap group and 22, 39, 54, 42 for the comparison group (2026 is a half
year).

## 3. Predictions, stated before looking

If H1 or H2 holds, after the rate-on-line peak and into the softening:

- P1. The overlap group's risk-adjusted spread falls relative to the
  comparison group's between the 2024 peak and the 2025 and 2026
  softening. Predicted sign: negative differential change. The 2023 to
  2024 step is reported too, with the prediction that the overlap group
  rose at least as much as the comparison group (differential change
  non-negative).
- P2. The overlap group's share of core issued principal rises relative to
  the years before the peak.
- P3. Net subscriptions into the cat bond lineages are positive in the
  quarter ending at the renewals where P1 and P2 hold, and negative or
  flat in the windows where they do not.

If H0 holds: P1 shows no differential (both groups move together), P2 is
flat, and P3 is uninformative because flows follow absolute returns.

H1 without H2: P1 and P2 hold in the primary market, P3 does not. H2
without H1: P3 holds and P1 holds in the secondary market (section 2),
P2 does not.

## 4. Decision rule

- A differential is reported only where both groups have at least 10
  tranches with spread and expected loss in the cell. Fewer: the test is
  inconclusive for that window, and is reported as inconclusive, not
  omitted. At 10 per cell the year is populated for the overlap group
  from 2023 and for the comparison group from 2022; renewal windows are
  shown as supporting detail and never decide.
- The differential is the change in the overlap group's risk-adjusted
  spread minus the change in the comparison group's, from the 2024 peak
  year to each of 2025 and 2026, and from 2023 to 2024 for the step,
  estimated as in section 2. Report the number of tranches and the
  issued principal behind each side.
- Resolved, the mechanical threshold: cycle effects on spread interact
  with expected loss, so part of any differential is pricing mechanics.
  Before P1 is read, the within-year slope of spread on expected loss is
  estimated on the comparison group alone for the peak year and the
  softening year; the change in that slope times the difference in mean
  expected loss between the groups is the differential pricing mechanics
  alone would produce. P1 is read on the differential net of that
  amount. A differential no larger in magnitude than that amount is
  reported as consistent with pricing mechanics, not substitution.
- Resolved, what counts: H1 is supported if P1 is negative net of the
  mechanical threshold in both 2025 and 2026 and P2 rises; H1 is not
  supported if P1 is non-negative in both years; one year each way is
  reported as inconclusive. The primary comparison group decides; the
  robustness groups and the sensitivities (band, size-weighted, sponsor
  fixed effects) are reported beside it and may qualify the reading but
  do not overturn it. No significance threshold is used; the sign, the
  size and the counts are reported, with a bootstrap interval over
  tranches for the primary estimate.
- Resolved, the pre-2023 baseline: there is no attachment-probability
  coverage before 2022, so a pre-hard-market baseline is read from the
  expected-loss bands instead (US hurricane indemnity tranches with
  expected loss 1% to 4%, the band that corresponds to the 2% to 8%
  attachment group where both are stated), pooled over 2020 to 2022 (16,
  17 and 20 tranches; 2019 has 5 and is excluded), reported as a proxy
  and labelled so. It gives P2 its "years before the peak" level and is
  not used for P1.
- Parallel moves in both groups are reported as consistent with H0.
- A differential that disappears when the comparison is restricted to the
  same expected-loss band is reported as a composition effect, not
  substitution. The restricted comparison cells (expected loss 1% to 4%)
  hold 13, 13, 19 and 8 tranches in 2023 to 2026, so the 2026 restricted
  check is inconclusive by the cell rule and is said to be.

## 5. What else could produce the pattern, and what is checked

- Expected-loss mix shifting between the groups (handled by the
  continuous adjustment and checked by the band restriction above).
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
    and its effect strengthens in hard markets. Resolved: a within-sponsor
    comparison is not feasible and is dropped. No sponsor issues in both
    groups in the same year in 2023, 2024 or 2026 and two do in 2025;
    pooled over the four years, 5 of the 50 overlap sponsors appear in
    the comparison group. The sensitivity instead is the pooled
    regression with sponsor fixed effects and year-by-group terms,
    identified from the 24 of 50 overlap sponsors with two or more
    tranches; it is reported beside the primary estimate.
  - Hurricane seasonality moves single-peril hurricane spreads by up to
    half; the issue month is a control in the pooled regression, and the
    year cell compares both groups over the same months.
  - A liquidity premium of about a fifth of the spread, larger for
    higher-risk bonds, sits inside spread minus EL and varies with layer;
    the primary differential is on primary-market spreads only, where the
    liquidity premium is set at issue and does not move between the
    groups within a window. The secondary-market version in section 2 is
    read for H2 and is stated to carry this premium.
  - EL model vintage changes (the modelling firms' updates after Ian)
    raise stated EL on the overlap group more than on remote layers.
    Resolved: the model version is never stated on the pages and a
    pre-update cohort cannot be formed; the modelling firm is stated for
    99% of overlap tranches (AIR 95, RMS 18, KatRisk 4), so a firm
    indicator enters the pooled regression and the differential is also
    shown for the AIR-modelled tranches alone. The vintage effect is
    named as an unobserved alternative in the write-up.
  - The cycle effect on spreads is state-dependent and interacts with EL,
    so a differential by layer is expected from pricing mechanics alone;
    the mechanical threshold in section 4 is the explicit rule.
  - Investors moved to remote layers in late 2022 by their own account; a
    falling overlap share can be investor de-risking. P2 is therefore read
    together with P3. The share of overlap issuance upsized at pricing is
    reported as context only: a size change at pricing is recorded for
    43% of overlap tranches, nearly all upsizes, and the absence of a
    record is not evidence that the size held, so the share is not a
    rule input.

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

## 7. What is reported regardless of outcome

The overlap and comparison definitions, the counts behind every cell,
the differential per window with its sign and size, the mechanical
threshold it is read against, the flows per lineage per window, the
inconclusive windows, and every sensitivity beside the primary estimate.
The descriptive atlas is presented as description in either case.

## 8. Choices resolved on 2026-11-19, for sign-off

Each line is one rule the analysis will follow. The alternative named is
reported as a sensitivity, never used to decide. Strike or amend any
line, date it, and commit; the analysis starts only after this section is
signed.

| # | Choice | Rule | Alternative, demoted to sensitivity | Count behind it |
|---|---|---|---|---|
| 1 | Comparison trigger list | Industry loss index, parametric, parametric index, modelled loss | Non-US perils; remote US hurricane indemnity below 1% | 16, 15, 26, 27, 22 tranches 2022 to 2026 |
| 2 | Risk adjustment | Continuous: spread on expected loss within year, pooled, group coefficient | Band average of spread minus expected loss | Every cell has at least 10 tranches from 2023 |
| 3 | Weighting | Unweighted, one tranche one observation | Size-weighted | Final size stated for 77% of overlap tranches |
| 4 | Deciding cell | Issue year | 1 January and mid-year renewal windows as detail; 1 July folded into mid-year | 1 July window holds 0, 0, 0, 1 overlap tranches |
| 5 | Fund demand | Sum of six lineages on non-null months, Stone Ridge interval fund also shown alone | Per-lineage reading | Four lineages complete from 2022; Victory Pioneer from Nov 2022; ETF from Apr 2025 |
| 6 | Secondary-market P1 | Monthly VWAP of customer trades on high-confidence CUSIPs; minimum 10 CUSIPs per cell | None | 15 to 67 overlap and 22 to 54 comparison CUSIPs a year |
| 7 | Mechanical threshold | Comparison-group EL slope change times the groups' mean EL gap; P1 read net of it | None | Comparison EL median 2.5 to 4.4 against overlap 2.3 to 2.5 |
| 8 | Support rule | H1 supported only if P1 negative in both 2025 and 2026 net of #7 and P2 rises; non-negative in both refutes; split is inconclusive | None; no significance threshold, bootstrap interval reported | |
| 9 | Pre-2023 baseline | Expected loss 1% to 4% US hurricane indemnity, pooled 2020 to 2022, used for P2 only | None | 16, 17, 20 tranches; 2019 excluded at 5 |
| 10 | Sponsor control | Pooled regression with sponsor fixed effects as sensitivity; within-sponsor comparison dropped | Within-sponsor (infeasible) | 0, 0, 2, 0 sponsors in both groups by year; 5 of 50 pooled |
| 11 | Model vintage | Modelling-firm indicator; AIR-only differential shown; version unobserved and said so | Pre-update cohort (infeasible) | Firm stated for 99% of overlap tranches; AIR 95, RMS 18 |
| 12 | Upsizing | Reported as context, not a rule input | None | Size change recorded for 43% of overlap tranches |

Signed: ____________________  Date: __________
