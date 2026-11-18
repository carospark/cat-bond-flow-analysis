# Literature: do cat bonds substitute for reinsurance?

Assembled 18 November 2026 by a web-research pass for section 6 of
`docs/PREREGISTRATION.md`. Verification key, as reported by that pass:
**[read]** the paper, working paper or slides was read in full;
**[abstract]** verified from the publisher, RePEc or repository abstract;
**[biblio]** citation verified, content from search snippets or secondary
summaries only; **[memory]** not verified. Ordered by relevance to the
planned design (spread minus expected loss by layer overlap around the
2023 hard-market peak, the Guy Carpenter rate-on-line index as the cycle
clock, registered cat bond fund net subscriptions as demand). Treat every
entry marked below [read] as needing a check against the source before it
is cited.

## A. Closest to the planned design

1. **Yu, M.-T. and Zhao, Y. (2025). "Cat Bonds and Reinsurance Market
   Dynamics."** Working paper, 13 January 2025, EFMA 2025. [read]
   NAIC panel of US P&C insurers 2009 to 2019 (5,018 insurer-years), 374
   cat bonds from Artemis, Aon and Lane; reinsurance ceded ratio on
   outstanding cat bond amount per cedent; cycle = year-on-year change in
   the Guy Carpenter US property-cat ROL index. Cat bond use reduces
   reinsurance use in hard-market years and not in soft ones; in hard
   markets it reduces affiliate reinsurance but increases external
   reinsurance. A cedent-level quantity test with the same cycle clock, so
   "substitution is stronger in hard markets" is an existing finding. No
   spreads, no layers, no 2023, no investor flows. Unpublished.
2. **Götze, T. and Gürtler, M. (2022). "Risk transfer beyond reinsurance:
   the added value of CAT bonds."** Geneva Papers 47(1), 125-171. [abstract]
   US P&C insurers' statements merged with cat bond use. Substitution
   comes mainly from non-indemnity bonds, most valuable when reinsurer
   default risk is high, basis risk low, and the insurer is exposed in
   high-risk layers. Conditions on layer riskiness, so "cat bonds
   substitute in some layers" is not novel.
3. **Suttakulpiboon, I. (2025/2026). "An Empirical Analysis of Recent
   Dynamics of Catastrophe Bonds."** Journal of Accountancy and
   Management, Mahasarakham University 18(2). [read]
   696 primary tranches 2011 to March 2025 (Artemis plus Bloomberg);
   coupon minus collateral yield on Braun (2016) controls including the GC
   ROL index level; break tests at end-2019 and end-2021. The ROL
   coefficient is positive in pooled OLS and insignificant with time fixed
   effects; the 2022 break reads as a supply-side capacity shock; EL
   pricing is strongly convex. Already regresses issue spreads on the ROL
   index through the 2023 peak. No layer classification, no spread minus
   EL, no demand measure. Non-specialist venue; treat estimates with care.
4. **Chen, X., Li, H., Lu, Y. and Zhou, R. (2024). "Unveiling Nonlinear
   Dynamics in Catastrophe Bond Pricing."** arXiv:2405.00697. [read]
   765 primary tranches 1999 to March 2021; Lane ROLX and GC indices;
   XGBoost. Spread sensitivity to the cycle is small in soft markets and
   large in hard ones, with a negative EL x cycle interaction (a 20-point
   ROLX rise adds about 140 bp at 2% EL and 60 bp at 8% EL). The cycle
   effect is state-dependent and interacts with EL, which is the mechanism
   the planned design wants, but by EL level rather than layer overlap and
   without 2023.

## B. Spread determinants at issue (the baseline the test must nest)

5. **Braun, A. (2016). "Pricing in the Primary Market for Cat Bonds."**
   Journal of Risk and Insurance 83(4), 811-847. [abstract] Tranches June
   1997 to December 2012. Expected loss dominates; territory, sponsor, the
   reinsurance cycle and comparable corporate spreads matter. The cycle
   index is not named in the abstract (the replication in item 3 lists the
   GC index; not confirmed in the paper).
6. **Lane, M. and Mahul, O. (2008). "Catastrophe Risk Pricing: An
   Empirical Analysis."** World Bank PRWP 4765. [abstract] About 250
   bonds; price about 2.69 x EL, 2.33 x EL cycle-adjusted; peak perils
   carry higher multiples.
7. **Gürtler, M., Hibbeln, M. and Winkelvos, C. (2016). "The Impact of
   the Financial Crisis and Natural Catastrophes on CAT Bonds."** JRI
   83(3), 579-612. [abstract] Secondary premiums rose in the crisis and
   after Katrina, the latter mainly through higher EL from the modelling
   firms. Spread minus EL is sensitive to EL model vintage.
8. **Galeotti, M., Gürtler, M. and Winkelvos, C. (2013). "Accuracy of
   Premium Calculation Models for CAT Bonds."** JRI 80(2), 401-421.
   [abstract] A linear spread-EL model fits as well as anything; supports
   a simple risk-adjusted spread.
9. **Götze, T. and Gürtler, M. (2020). "Hard markets, hard times: On the
   inefficiency of the CAT bond market."** Journal of Corporate Finance
   62, 101553. [abstract] Sponsor tenure, coverage, rating, CDS spread and
   on-the-run issuance move premiums, more so in hard markets. Sponsor
   effects are needed in any 2023 comparison.
10. **Chatoro, M., Mitra, S., Pantelous, A. A. and Shao, J. (2023).
    "Catastrophe bond pricing in the primary market: The issuer effect and
    pricing factors."** International Review of Financial Analysis 85,
    102431. [abstract] Issuer identity explains about 26% of price
    variation 1997 to 2020.
11. **Herrmann, M. and Hibbeln, M. (2023). "Trading and liquidity in the
    catastrophe bond market."** JRI 90(2), 283-328. [abstract] 9,393 TRACE
    trades 2015 to 2019; about 21% of the yield spread is a liquidity
    premium, larger for high-risk bonds. Spread minus EL carries a
    liquidity component that varies with layer.
12. **Herrmann, M. and Hibbeln, M. (2021). "Seasonality in catastrophe
    bonds and market-implied catastrophe arrival frequencies."** JRI
    88(3), 785-818. [abstract] Up to 47% of secondary spread fluctuation on
    single-peril hurricane bonds is seasonal. Issue-date timing within the
    year must be controlled.
13. **Trottier, D.-A., Lai, V. S. and Charest, A.-S. (2018). "CAT Bond
    Spreads via HARA Utility and Nonparametric Tests."** Journal of Fixed
    Income 28(1), 75-99. [biblio, abstract] A multiples-based alternative.
14. **Papachristou, D. (2011). "Statistical Analysis of the Spreads of
    Catastrophe Bonds at the Time of Issue."** ASTIN Bulletin 41(1),
    251-277. [abstract] GAM on 2003 to 2008 issues.
15. **Dieckmann, S. (2010). "By Force of Nature: Explaining the Yield
    Spread on Catastrophe Bonds."** SSRN 1082879. [biblio only]

## C. Theory and evidence on substitution versus complementarity

16. **Finken, S. and Laux, C. (2009).** JRI 76(3), 579-605. [abstract]
    Index triggers give low-risk insurers an outside option and discipline
    reinsurance prices at the margin.
17. **Subramanian, A. and Wang, J. (2018). "Reinsurance versus
    securitization of catastrophe risk."** IME 82, 55-72. [abstract]
    Signalling model: substitution by risk level, that is by layer.
18. **Trottier, D.-A. and Lai, V. S. (2017). "Reinsurance or CAT Bond? How
    to Optimally Combine Both."** SSRN 2735954. [abstract] Optimal
    programme: reinsurance for lower layers, a cat bond above; the overlap
    is where they compete.
19. **Lakdawalla, D. and Zanjani, G. (2012).** JRI 79(2), 449-476.
    [abstract] Collateralised cat bonds as complements as much as
    substitutes.
20. **Cummins, J. D. and Trainar, P. (2009).** JRI 76(3), 463-492.
    [abstract] Securitisation takes over as loss magnitude and correlation
    rise.
21. **Cummins, J. D. and Weiss, M. A. (2009).** JRI 76(3), 493-545.
    [abstract] Survey; the underwriting cycle as a driver of convergence.
22. **Froot, K. A. (2001). "The market for catastrophe risk: a clinical
    examination."** JFE 60(2-3), 529-571. [abstract] Insurers buy little
    high-layer cover at premiums far above EL; capital-market supply
    restrictions and reinsurer market power best supported. The planned
    premise is Froot's market-power channel.
23. **Hagendorff, B., Hagendorff, J., Keasey, K. and Gonzalez, A. (2014).**
    JCF 25, 387-402. [abstract] Issuers are not random.
24. **Zhao, Y., Lee, J.-P. and Yu, M.-T. (2021).** China Finance Review
    International 11(4), 449-473. [abstract] Review.

## D. Returns, the cycle, 2023, investor demand

25. **Braun, A. and Kousky, C. (2021). "Catastrophe Bonds."** Wharton Risk
    Center primer. [read] "Both a complement and a substitute", used for
    the highest layers.
26. **Tomunen, T. "Failure to Share Natural Disaster Risk."** Slides April
    2024; listed as Review of Financial Studies, DOI 10.1093/rfs/hhaf055,
    not opened. [slides read] 71% of security-level variation in expected
    returns explained by the marginal utility of specialist ILS fund
    intermediaries. The closest academic support for fund flows as a
    demand shifter, using intermediary wealth rather than subscriptions.
27. **Braun, A., Ben Ammar, S. and Eling, M. (2019).** JBF 102, 59-78.
    [abstract] ILS fund return factors; returns, not flows.
28. **Carayannopoulos, P. and Perez, M. F. (2015).** Geneva Papers 40(1),
    1-28. [abstract] Zero beta only outside crises.
29. **Practitioner, 2022 to 2024.** Swiss Re Capital Markets ILS Market
    Insights, March 2023 [read]: Q4 2022 new-issue multiples at record
    highs, "ILS allocations have shifted toward more remote layers",
    sponsors paused deals. Artemis Q4 2023 [fetched]: 2023 average
    multiple 4.54x, highest in 20 years. Lane Financial via Artemis,
    November 2023 and April 2024 [fetched]: hardest in January 2023, "no
    longer hard" by late 2023, neutral by March 2024. Guy Carpenter press
    release 28 December 2023 [read]: at 1 January 2024 pressure greatest
    at the lower ends of programmes, decreases near the top; the global
    index +5.4% at 2024, first decline (-6.6%) at 2025.
30. **Fund flows: a gap.** No peer-reviewed study measures investor flows
    into ILS or cat bond funds. One unverified thesis (Aalto, "Intermediary
    capital and CAT bond pricing") reports a negative relation between
    capital flows and issue spreads at a two-quarter lag on 39
    observations [biblio only]. Nothing uses N-PORT subscriptions.

## What the planned study would add, and what argues against it

Nothing in the list compares spread minus EL and issuance shares between
layers that overlap with reinsurance programmes and layers that do not,
around the 2023 peak, with a demand measure from registered-fund net
subscriptions. The novelty, in decreasing order of strength: the
layer-overlap classification as the treatment (items 2, 17 and 18 predict
a layer-specific margin but test it only through EL or cedent-level
quantities); registered-fund subscriptions as demand (no precedent); the
2023 window (item 3 already runs a break test at end-2021 with the GC
index). Not novel: the ROL index as a cycle regressor on issue spreads
(5, 4, 3), spread minus EL as the price (6 onward), and substitution being
stronger in hard markets (1, with the same cycle clock).

Against the design:

- The GC index is annual and its effect vanishes under time fixed
  effects (3), so a single 2023 window with the index as the only cycle
  measure is one hard-market episode confounded with Ian loss creep, SOFR
  collateral yields, the Fed cycle and EL model updates.
- The layer comparison is confounded by EL level: a negative EL x cycle
  interaction (4) and convex EL pricing (3) mean overlapping, higher-EL
  layers mechanically respond differently from remote layers without any
  substitution; the cycle itself moved most at lower layers (29).
- Spread minus EL carries non-risk components that vary with layer and
  date: liquidity (11), hurricane seasonality (12), sponsor effects that
  strengthen in hard markets (9, 10), EL vintage shifts (7).
- Supply versus demand: investors deliberately moved to remote layers in
  late 2022 (29), so a falling overlap share can be investor de-risking;
  flows chase returns, and registered US funds are a small slice of the
  specialist-fund base that prices the market (26).
- Selection: issuers are not random (23, 9); layer comparisons need
  sponsor fixed effects or a within-sponsor design.
- Substitution is not one-directional even at the cedent level (1).
