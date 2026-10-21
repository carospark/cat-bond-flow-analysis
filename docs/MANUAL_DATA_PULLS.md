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
queried for a curated identifier screen of 1,332 CUSIPs over the 2002-2025
request window. The screen was recovered read-only from the WRDS query
history on 2026-09-15, saved locally with hashes, and reconciled against the
bridge. It is broader than the bridge on one side (about 220 ILS securities
from known issuer programs the strict deal match does not cover) and narrower
on the other (72 bridge CUSIPs were not in it).

**Supplementary pull completed 2026-09-15** for the 93 CUSIPs the screen
missed, by reusing the saved query forms with only the identifier list
replaced. Note that the enhanced form now clamps its start date to
2003-08-02, the table's first observation, which loses no rows. Provenance
and the reconciliation are in the local manifest. The
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
into 2026. Column mapping and cleaning are handled by
`src/clean_trace_trades.py`.

## Swiss Re 2026 ILS Market Insights

Download the February and July 2026 publications through the publisher's form:

- `https://www.swissre.com/our-business/alternative-capital-partners/ils-market-insights-february-2026.html`
- `https://www.swissre.com/our-business/alternative-capital-partners/ils-market-insights-july-2026.html`

Automated requests returned HTTP 403 and no stable public PDF endpoint was
verified. After a manual browser download, confirm each file is a readable PDF,
record the landing page and download timestamp, hash it, and place it under
`data/raw/tier1/manual/swiss_re_ils/`. A landing-page response alone does not
count as an archived publication.

## UCITS cat bond fund NAV and fund-size histories

Checked 2026-10-21: no manager publishes NAV history without a gate.
Schroders' fund centre and GAM's fund pages sit behind an investor
self-certification, Fundsquare (the Luxembourg publication venue) shows only
the latest NAV without a login, the Liechtenstein venue LAFV offers its fund
API only after an onboarding request, Plenum's UCITS cat-bond fund index
downloads go through a form with non-reproduction terms, and Twelve has no
public fund page. None of these were accepted or submitted by the assistant.

The simplest route is the same Bloomberg terminal visit as the Swiss Re
indices. For each share class below, export the daily or weekly NAV
history (`FUND_NET_ASSET_VAL` or `PX_LAST` on the fund ticker) and the fund
size history (`FUND_TOTAL_ASSETS`), with currency, from inception to the
export date, retaining field names and the export timestamp. Store under
`data/raw/tier1/manual/bloomberg/ucits/` and record hashes and row
coverage in `data/MANIFEST.local.md`. One representative class per fund is
enough for returns; fund size is per fund.

| Fund | Share class | ISIN |
|---|---|---|
| Schroder GAIA Cat Bond | I Acc USD | LU0951570760 |
| Schroder GAIA Cat Bond | IF Acc USD | LU0951570687 |
| GAM Star Cat Bond (GAM Swiss Re Cat Bond) | Institutional USD Acc | see fund tree; EUR hedged IE00B6TLWG59 |
| Twelve Cat Bond Fund (Twelve Capital ICAV) | I | IE00BD2B9H19 |
| Plenum CAT Bond Defensive Fund | I EUR | LI0227305906 |
| Plenum CAT Bond Dynamic Fund | I USD | LI1115702857 |

Alternatives if the terminal is not available: accept the Schroders fund
centre disclaimer once in a Claude-in-Chrome session and let the assistant
read the historic-prices view; email LAFV (info@lafv.li) for API access,
which covers both Plenum funds and is free for third parties with a
legitimate interest; submit Plenum's index form for the "Market Survey (All
CAT Bond UCITS Funds)" and index history, which gives the whole UCITS
universe's size (16 funds, about USD 21bn, a third of the market) in one
file. Fund flow for these funds is then backed out from size and return.

## Brookmont 2026 NAV history

The issuer page currently exposes current NAV and holdings, but its embedded
historical NAV array stops at 2025-12-31. Fill the gap only from an official
issuer, administrator, or clearly documented market-data NAV feed. Exchange
closes are market prices and must remain a separate series.
