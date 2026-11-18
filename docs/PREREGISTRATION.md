# Pre-registration: substitution between cat bonds and traditional reinsurance

**Status: draft for Caro to edit.** Nothing below has been run. The
point of writing it first is that the atlas is descriptive, spread
co-movement plus fund inflows is consistent with several mechanisms, and
a test that cannot lose is not a test. Fill the bracketed choices, cut
what you disagree with, then date and commit it before the atlas is read
for substitution.

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
traditional reinsurance programmes attach: peril [US hurricane, or US
multi-peril including hurricane], trigger [indemnity], attachment
probability stated and in [the 2% to 8% bands], issue years [2022 to
2026], where attachment probability covers at least half of issued
principal. Taken from `layer_by_year.csv` and `universe_deals.csv` with
the full peril tags, never from the equal split.

**Comparison group.** Core tranches of the same years outside the
overlap: [remote layers below 1%; industry-loss and parametric triggers;
non-US perils]. State which of these is the primary comparison and which
are robustness.

**Risk-adjusted spread.** Spread minus expected loss, in percentage
points, size-weighted within a cell; where a cell has at least [10]
tranches with both, a continuous adjustment (spread regressed on expected
loss within the year) replaces the band.

**Cycle dating.** The Guy Carpenter global property-catastrophe
rate-on-line index dates the cycle: the hard-market peak at the [1
January 2023] renewal, softening from [2024]. The global index dates the
cycle only. It cannot say that a specific reinsurance layer became cheaper
relative to its cat bond counterpart, because renewal outcomes vary by
region and attachment; the result therefore stays at the level of
differential cat bond pricing and issuance around renewals.

**Renewal windows.** [1 January, 1 June, 1 July] of each year. Issuance
is assigned to the window it precedes. Fund flows are read with a lag of
[one quarter] before the window.

**Fund demand.** Net subscriptions per registered lineage per month from
the N-PORT filings, sales minus redemptions, so already free of returns
(`fund_flows_by_month.csv`). Months with a null flow stay null.

## 3. Predictions, stated before looking

If H1 or H2 holds, after the rate-on-line peak and into the softening:

- P1. The overlap group's risk-adjusted spread falls relative to the
  comparison group's. Predicted sign: [negative differential change].
- P2. The overlap group's share of core issued principal rises relative to
  the years before the peak.
- P3. Net subscriptions into the cat bond lineages are positive in the
  [quarter] before the renewals where P1 and P2 hold, and negative or flat
  in the windows where they do not.

If H0 holds: P1 shows no differential (both groups move together), P2 is
flat, and P3 is uninformative because flows follow absolute returns.

H1 without H2: P1 and P2 hold, P3 does not. H2 without H1: P3 holds and
P1 holds in the secondary market, P2 does not.

## 4. Decision rule

- A differential is reported only where both groups have at least [10]
  tranches with spread and expected loss in the cell. Fewer: the test is
  inconclusive for that window, and is reported as inconclusive, not
  omitted.
- The differential is the change in the overlap group's risk-adjusted
  spread minus the change in the comparison group's, between [the window
  before the peak] and [each window after]. Report the number of tranches
  and the issued principal behind each side.
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
- Florida-specific changes: the [2022 and 2023 Florida legislative
  reforms] shift the demand for Florida layers for reasons unrelated to
  reinsurance pricing; the Florida share of the overlap group is reported
  per window.
- Retrocession and collateralised reinsurance pricing, which the data
  does not hold; named as an unobserved alternative.

## 6. Literature to search before the write-up

To be done before the atlas is read, so that the design can be adjusted
and no novelty is claimed that the literature already has: the cat bond
spread determinants literature (expected loss, peril, trigger, cycle) and
the work on cat bonds as substitutes or complements for reinsurance.
List the papers read, with what each measured, here: [ ].

## 7. What is reported regardless of outcome

The overlap and comparison definitions, the counts behind every cell,
the differential per window with its sign and size, the flows per lineage
per window, and the inconclusive windows. The descriptive atlas is
presented as description in either case.
