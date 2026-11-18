# Pre-registration: substitution between cat bonds and traditional reinsurance

**Status: draft with defaults filled, awaiting Caro's sign-off.**
Nothing below has been run. The point of writing it first is that the
atlas is descriptive, spread co-movement plus fund inflows is consistent
with several mechanisms, and a test that cannot lose is not a test. Every
choice below was filled from the data on 2026-11-18 with its reason in
the "Why" line; change any of them, then date and commit before the atlas
is read for substitution. Counts are core tranches with both spread and
expected loss stated.

## 1. Two hypotheses, kept apart

**H1, sponsor substitution.** Sponsors buy more cat bond protection in
the layers where traditional reinsurance became expensive, and less where
it became cheap. Evidence is in issuance and pricing: the share and the
risk-adjusted spread of cat bonds in the overlapping layers relative to
the others.

**H2, investor reallocation.** Investors move capital into cat bond
vehicles when their relative return rises. Evidence is in demand: net
subscriptions into the registered cat bond funds, and relative pricing in
comparable bonds.

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
stated and in the 2% to 8% bands; issue years 2023 to 2026. Taken from
`universe_deals.csv` (full peril tags, never the equal split) and the
parser's tranches table.

Why: indemnity US hurricane is the product a Florida or nationwide
reinsurance programme buys; the 2% to 8% attachment bands are where the
working layers of those programmes sit, the below-1% band being remote
cover reinsurance rarely writes. Tranches with spread and expected loss in
this group: 2022 5, 2023 20, 2024 22, 2025 35, 2026 41. 2022 is below the
cell minimum, so the overlap group begins in 2023, the hard-market step
year. Of the US hurricane indemnity tranches issued 2022 to 2026 with an
attachment probability, 135 of 265 fall in the 2% to 8% bands.

**Comparison group.** Primary: US hurricane tranches with an
industry-loss-index or parametric trigger, any attachment band (same
peril and cycle, a product reinsurance programmes do not buy in the same
way). Robustness: non-US perils with an attachment probability stated.
Reported but below the cell minimum: remote US hurricane indemnity layers
below 1%.

Why: the index-trigger group is the only comparison with enough tranches
every year (2022 14, 2023 14, 2024 26, 2025 27, 2026 24); non-US has 3,
11, 11, 23, 12; remote layers 2, 6, 3, 5, 8.

**Risk-adjusted spread.** Spread minus expected loss, in percentage
points, size-weighted within a cell; where a cell has at least 10
tranches with both, a continuous adjustment (spread regressed on expected
loss within the year, both groups pooled) replaces the band, and the
differential is read from the group coefficient.

**Cycle dating.** The Guy Carpenter global property-catastrophe
rate-on-line index (2000 = 100) dates the cycle: 130 at the 2021 renewal,
145 in 2022, 187 in 2023 (the step), 191 in 2024 (the peak), 178 in 2025,
156 in 2026. So: hard-market step at the 1 January 2023 renewal, peak at
1 January 2024, softening at 2025 and 2026. The global index dates the
cycle only. It cannot say that a specific reinsurance layer became cheaper
relative to its cat bond counterpart, because renewal outcomes vary by
region and attachment; the result therefore stays at the level of
differential cat bond pricing and issuance around renewals.

**Renewal windows.** 1 January, 1 June and 1 July of each year, the
June date being the Florida renewal. Issuance is assigned to the renewal
it precedes (a May deal to 1 June, a December deal to 1 January). Fund
flows are read over the quarter ending at the renewal date.

Why: those are the three dates the rate-on-line index and the Florida
programmes price on; a one-quarter flow window matches the N-PORT
quarterly cadence and avoids reading a single month's redemptions.

**Fund demand.** Net subscriptions per registered lineage per month from
the N-PORT filings, sales minus redemptions, so already free of returns
(`fund_flows_by_month.csv`). Months with a null flow stay null.

## 3. Predictions, stated before looking

If H1 or H2 holds, after the rate-on-line peak and into the softening:

- P1. The overlap group's risk-adjusted spread falls relative to the
  comparison group's between the 2024 peak and the 2025 and 2026
  softening. Predicted sign: negative differential change. The 2023 to
  2024 step is reported too, with the prediction that the overlap group
  rose at least as much as the comparison group.
- P2. The overlap group's share of core issued principal rises relative to
  the years before the peak.
- P3. Net subscriptions into the cat bond lineages are positive in the
  quarter ending at the renewals where P1 and P2 hold, and negative or
  flat in the windows where they do not.

If H0 holds: P1 shows no differential (both groups move together), P2 is
flat, and P3 is uninformative because flows follow absolute returns.

H1 without H2: P1 and P2 hold, P3 does not. H2 without H1: P3 holds and
P1 holds in the secondary market, P2 does not.

## 4. Decision rule

- A differential is reported only where both groups have at least 10
  tranches with spread and expected loss in the cell. Fewer: the test is
  inconclusive for that window, and is reported as inconclusive, not
  omitted. At 10 per cell, the overlap group can be tested in every year
  from 2023 and the index comparison in every year from 2022; renewal-
  window cells (three a year) will often fall below it, in which case the
  year is the cell and the window result is shown as supporting detail.
- The differential is the change in the overlap group's risk-adjusted
  spread minus the change in the comparison group's, from the 2024 peak
  year to each of 2025 and 2026, and from 2023 to 2024 for the step.
  Report the number of tranches and the issued principal behind each side.
- Pre-2023 baseline: there is no attachment-probability coverage before
  2022, so a pre-hard-market baseline is read from the expected-loss
  bands instead (US hurricane indemnity tranches with expected loss 1% to
  4%, 2019 to 2022, the band that corresponds to the 2% to 8% attachment
  group where both are stated), reported as a proxy and labelled so.
- Parallel moves in both groups are reported as consistent with H0.
- A differential that disappears when the comparison is restricted to the
  same expected-loss band is reported as a composition effect, not
  substitution.

## 5. What else could produce the pattern, and what is checked

- Expected-loss mix shifting between the groups (checked by the band
  restriction above).
- Trigger mix: a move toward indemnity is itself a sponsor choice and is
  reported separately, not folded into P1.
- Issue size: larger deals price tighter; report the differential with and
  without size weighting.
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
    and its effect strengthens in hard markets. The differential is
    estimated with sponsor fixed effects, and a within-sponsor version
    (sponsors issuing in both groups) is reported beside it.
  - Hurricane seasonality moves single-peril hurricane spreads by up to
    half; the issue month is a control, and the January, June and July
    renewals are compared like with like.
  - A liquidity premium of about a fifth of the spread, larger for
    higher-risk bonds, sits inside spread minus EL and varies with layer;
    the differential is reported for primary-market spreads only, where
    the liquidity premium is set at issue and does not move between the
    groups within a window.
  - EL model vintage changes (the modelling firms' updates after Ian) raise
    stated EL on the overlap group more than on remote layers; the EL
    vendor and model version are recorded where the page states them and
    the differential is re-run on the pre-update cohort.
  - The cycle effect on spreads is state-dependent and interacts with EL
    (larger at low EL in the existing estimates), so a differential by
    layer is expected from pricing mechanics alone; the test therefore
    reads the sign of the differential against the EL x cycle interaction
    estimated on the same data, and a differential no larger than that
    interaction implies is reported as consistent with pricing mechanics,
    not substitution.
  - Investors moved to remote layers in late 2022 by their own account; a
    falling overlap share can be investor de-risking. P2 is therefore read
    together with P3 and with the share of overlap issuance that was
    upsized at pricing.

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
the differential per window with its sign and size, the flows per lineage
per window, and the inconclusive windows. The descriptive atlas is
presented as description in either case.
