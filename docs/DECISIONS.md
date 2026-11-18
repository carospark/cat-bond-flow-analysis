# Decisions

Dated decisions on method that the code and the write-up follow. Each
says what was decided, what it rests on, and what would reopen it.

## 2026-11-18: Phase 2 atlas conventions and the Phase 3 track choice

Five decisions taken together after the atlas groundwork and two
independent reviews of it.

1. **Band variable.** Expected loss is the primary pricing view
   (`layer_by_year_el.csv`), attachment probability the layer view
   (`layer_by_year.csv`), with the same edges. Rests on coverage: expected
   loss is stated on 87% to 100% of core issued principal every year from
   2016; attachment probability on 8% to 44% of principal in 2019 to 2021
   and is a source gap there (only 2 of 115 pages without it state one).
   An expected-loss band is a pricing band, not a layer. Any layer-overlap
   comparison uses the attachment view and only from 2022 on. Reopened if
   a continuous expected-loss adjustment of spread replaces the bands.

2. **Universe.** Six exclusive segments in the order mortgage, life and
   health, cyber, other specialty, private/lite, core property cat.
   Mixed-peril and generic-peril deals stay in the core and are flagged
   (`mixed_peril`, `generic_peril`); generic peril is left unallocated in
   the peril chart. Private/lite issuance is shown beside the core as its
   own series, never folded in. Mortgage ILS is carried at face in its own
   segment and any broader total says so. Rests on the published market
   totals depending on the universe definition, so the atlas states its
   own.

3. **Band edges.** 1, 2, 4 and 8 percent for both metrics. Counts and
   principal are reported per cell for each metric. Where sample size
   permits, spread is adjusted on continuous expected loss rather than by
   band, so a 1.99% and a 2.01% tranche are not treated as different.

4. **Loss timing.** Loss month is the default for economic principal
   outstanding; settlement month is a sensitivity. Recognition date is the
   event month as the page's loss table states it (parser HANDOFF.md,
   2026-11-18). Before settlement timing is shown as a sensitivity, the
   repay rule for a deal's unlost remainder must stop following the
   settlement month (or follow it only where the page says the notes were
   extended): 12 of the 32 differing deals differ by more than their loss
   because of that rule (`compare_loss_timing.py`, mechanism
   `remainder_held_to_settlement`).

5. **Equal peril split.** Kept for the descriptive atlas. The chart is
   titled "issued principal allocated by peril" and its caption states the
   rule. Sample selection for the hurricane event study uses the full
   peril tags and contract terms, never the split.

**Phase 3 tracks.** The hurricane event study and fund flow plus
substitution by layer. The hurricane study has run since 25 October 2026
in a third repository, `/Users/caropark/projects/milton_ian_repricing`
(public on GitHub), which reads this repository and the parser read-only:
four storms (Ian, Milton, Idalia, Beryl), CUSIP level, strict
high-confidence pairs only, windows of 45 days before and 60 after
landfall, aggregates published with suppression below five pairs. Its
HANDOFF.md is the state of record for that track. Its coverage counts
(7 and 4 CUSIPs with three customer trades each side of Ian and Milton)
are the binding constraint; `event_gate.py` here is the coarser
deal-level cross-check (10 to 12 deals trading at least once each side).
The parametric design catalogue is the stretch if public-sector
conversations become the priority. The substitution reading of the atlas
waits for the pre-registration (`docs/PREREGISTRATION.md`).
