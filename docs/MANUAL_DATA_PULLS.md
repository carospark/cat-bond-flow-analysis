# Manual and authenticated data pulls

These sources cannot be completed by the public pullers. Raw files and exact
account-linked provenance stay local and gitignored.

## Bloomberg: Swiss Re Cat Bond Indices

At a licensed Bloomberg terminal, export weekly date/value history from the
earliest available date through the export date for:

- `SRCATTRR` and `SRCATPRC`: aggregate total- and price-return indices.
- `SRBBTRR` and `SRBBPRC`: BB-rated total- and price-return indices.
- `SRUSWTRR` and `SRUSWPRC`: U.S.-wind total- and price-return indices.

The Swiss Re methodology says coverage begins in January 2002. Confirm at the
terminal whether the originally requested `SRCATPRR` is now an alias for
`SRCATPRC`; do not merge the two names without that check. Preserve ticker,
field name, frequency, currency/unit, terminal export timestamp, and any
missing-value flags. Store the export under
`data/raw/tier1/manual/bloomberg/` and record its hash and row coverage in
`data/MANIFEST.local.md`.

Acceptance checks: dates parse and sort uniquely; all six series are weekly;
the aggregate series start near January 2002; values are not silently
forward-filled; and price-return is not mislabeled total-return.

## WRDS: raw TRACE 144A transactions

**Completed 2026-09-03.** The archived TRACE and FISD extracts are
security/issuer masters, not trades. Once the independently produced cat-bond
CUSIP universe was available, `trace_enhanced.trace_btds144a_enhanced` was
queried for a curated identifier screen over the 2002-2025 request window.
That screen was broader than the deal-to-CUSIP bridge and its exact list was
not saved; recovering it from the WRDS query history is an open follow-up. The
enhanced table ended in early December 2025 at pull time, so the standard 144A
trade table was used for the tail through early June 2026, as this document
allowed. Each table was pulled in four CUSIP batches.

The exports live under `data/raw/tier1/wrds/` and remain gitignored. Query
IDs, export timestamps, row counts, observed date ranges, distinct-CUSIP
counts, and SHA-256 hashes are recorded in `data/MANIFEST.local.md`. The
cancellation, correction, reversal, dissemination, and sequence fields were
preserved so cleaning can be audited; no cleaning has been applied. Do not
commit or redistribute the export.

Follow-ups: re-pull the tail from the enhanced table once its coverage extends
into 2026, and map the enhanced and standard column sets explicitly before
stacking them.

## Swiss Re 2026 ILS Market Insights

Download the February and July 2026 publications through the publisher's form:

- `https://www.swissre.com/our-business/alternative-capital-partners/ils-market-insights-february-2026.html`
- `https://www.swissre.com/our-business/alternative-capital-partners/ils-market-insights-july-2026.html`

Automated requests returned HTTP 403 and no stable public PDF endpoint was
verified. After a manual browser download, confirm each file is a readable PDF,
record the landing page and download timestamp, hash it, and place it under
`data/raw/tier1/manual/swiss_re_ils/`. A landing-page response alone does not
count as an archived publication.

## Brookmont 2026 NAV history

The issuer page currently exposes current NAV and holdings, but its embedded
historical NAV array stops at 2025-12-31. Fill the gap only from an official
issuer, administrator, or clearly documented market-data NAV feed. Exchange
closes are market prices and must remain a separate series.
