"""Compile the Brookmont ILS ETF's daily snapshots into a shares-outstanding and flow series.

The issuer page archived nightly by pull_tier1_sources.py (source
brookmont_ils_etf) carries, on each snapshot, shares outstanding, net
assets, the current NAV, and the premium or discount. ETF investor flow is
the change in shares outstanding times NAV, because an ETF's shares are
only created or redeemed by authorized participants against the fund's
assets. That makes this the only daily, observed flow series in the
project; the N-PORT filings give the same fund's monthly sales and
redemptions in quarterly batches and are used here as the reconciliation.

Reads  data/raw/tier1/<date>/brookmont_ils_etf/fund_snapshot.json
Writes data/processed/brookmont_ils_etf/snapshot_series.csv
       data/processed/brookmont_ils_etf/summary.json

Each observation is dated by the page's own `holdings_as_of` where it is
present, not by the night the page was pulled: the issuer updates the page
with a lag, and two pulls that show the same as-of date are one observation.
Gaps between observations are carried as `days_since_prior`; a flow row
spans the whole gap, not one day, and the per-day column divides it evenly
only as a convenience for plotting. A change in shares is valued at the
ending NAV, so a row spanning a gap is a period estimate.

Reconciliation with the N-PORT monthly flows is done on calendar months
both sources cover. A month end is covered by the snapshots when an
observation falls within `MONTH_END_TOLERANCE_DAYS` of it; the snapshot
flow for a month is the change in shares between its two covered month ends
valued at the ending NAV. The N-PORT side is the fund's `net_flow` for the
same month. For each common month the output gives the signed error
(snapshot minus N-PORT) and whether it sits inside a stated tolerance: one
creation unit at NAV plus one per cent of the N-PORT flow. When the two
sources share no month, the result is `available: false` with the reason
and both coverages written out.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = ROOT / "data" / "raw" / "tier1"
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "brookmont_ils_etf"
DEFAULT_NPORT_FLOWS = ROOT / "data" / "processed" / "nport" / "fund_flows.csv"
SOURCE_ID = "brookmont_ils_etf"
NPORT_FUND_ID = "brookmont_catastrophic_bond_etf"
MONTH_END_TOLERANCE_DAYS = 3
CREATION_UNIT_SHARES = 50_000       # shares move in multiples of 50,000 across every snapshot
TOLERANCE_SHARE_OF_FLOW = 0.01


def _number(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = re.sub(r"[,$%\s]", "", str(text))
    if cleaned in ("", "-", "N/A"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten the two-column 'Fund Detail' table and the NAV metrics table."""
    details: dict[str, str] = {}
    for row in payload.get("fund_details", [])[1:]:
        for index in (0, 2):
            if len(row) > index + 1:
                details[row[index]] = row[index + 1]
    metrics = {row[0]: row[1] for row in payload.get("current_nav_metrics", [])[1:] if len(row) > 1}
    holdings_as_of = payload.get("holdings_as_of")
    if holdings_as_of:
        try:
            holdings_as_of = dt.datetime.strptime(holdings_as_of, "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
    return {
        "holdings_as_of": holdings_as_of,
        "shares_outstanding": _number(details.get("Shares Outstanding")),
        "net_assets": _number(details.get("Net Assets")),
        "nav": _number(metrics.get("NAV")),
        "premium_discount_pct": _number(metrics.get("Premium / Discount (%)")),
        "ticker": details.get("Ticker"),
        "fund_cusip": details.get("CUSIP"),
    }


def load_snapshots(raw_root: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(raw_root.glob(f"*/{SOURCE_ID}/fund_snapshot.json")):
        snapshot_date = path.parents[1].name
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"snapshot_date": snapshot_date, **parse_snapshot(payload)})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values("snapshot_date").reset_index(drop=True)


def build_series(snapshots: pd.DataFrame) -> pd.DataFrame:
    """One row per effective date (holdings_as_of, else snapshot_date), the
    latest pull kept where several pulls show the same as-of date."""
    if snapshots.empty:
        return snapshots
    out = snapshots.copy()
    out["effective_date"] = out["holdings_as_of"].where(out["holdings_as_of"].notna(), out["snapshot_date"])
    out["effective_date_source"] = out["holdings_as_of"].notna().map({True: "holdings_as_of", False: "snapshot_date"})
    out = out.sort_values(["effective_date", "snapshot_date"]).drop_duplicates("effective_date", keep="last").reset_index(drop=True)
    out["implied_nav"] = out["net_assets"] / out["shares_outstanding"]
    out["shares_change"] = out["shares_outstanding"].diff()
    out["flow_usd"] = out["shares_change"] * out["nav"]
    out["days_since_prior"] = pd.to_datetime(out["effective_date"]).diff().dt.days
    out["flow_usd_per_day"] = out["flow_usd"] / out["days_since_prior"]
    out["net_assets_change"] = out["net_assets"].diff()
    # The part of the net-asset change that is not creations or redemptions
    # is performance plus distributions over the gap.
    out["non_flow_change_usd"] = out["net_assets_change"] - out["flow_usd"]
    return out


def month_end_observations(series: pd.DataFrame, tolerance_days: int = MONTH_END_TOLERANCE_DAYS) -> pd.DataFrame:
    """Shares outstanding and NAV at each calendar month end the snapshots
    cover: the latest observation on or before the month end, accepted only
    when it lies within `tolerance_days` of it."""
    if series.empty:
        return pd.DataFrame(columns=["month_end", "effective_date", "shares_outstanding", "nav", "net_assets", "days_before_month_end"])
    obs = series.assign(effective_dt=pd.to_datetime(series["effective_date"])).sort_values("effective_dt")
    first, last = obs["effective_dt"].iloc[0], obs["effective_dt"].iloc[-1]
    month_ends = pd.date_range(first - pd.offsets.MonthEnd(1), last + pd.offsets.MonthEnd(1), freq="ME")
    rows = []
    for month_end in month_ends:
        before = obs[obs["effective_dt"] <= month_end]
        if before.empty:
            continue
        row = before.iloc[-1]
        lag = int((month_end - row["effective_dt"]).days)
        if lag <= tolerance_days:
            rows.append({"month_end": month_end.date().isoformat(), "effective_date": row["effective_date"],
                         "shares_outstanding": row["shares_outstanding"], "nav": row["nav"],
                         "net_assets": row["net_assets"], "days_before_month_end": lag})
    return pd.DataFrame(rows, columns=["month_end", "effective_date", "shares_outstanding", "nav", "net_assets", "days_before_month_end"])


def snapshot_monthly_flows(series: pd.DataFrame, tolerance_days: int = MONTH_END_TOLERANCE_DAYS) -> pd.DataFrame:
    """Monthly creation/redemption flow from the snapshots for months whose
    two bounding month ends are both covered, valued at the ending NAV."""
    ends = month_end_observations(series, tolerance_days)
    if len(ends) < 2:
        return pd.DataFrame(columns=["month_end", "shares_change", "nav", "snapshot_flow_usd", "start_effective_date", "end_effective_date"])
    ends = ends.assign(month=pd.to_datetime(ends["month_end"]).dt.to_period("M"))
    rows = []
    for prev, cur in zip(ends.itertuples(index=False), ends.iloc[1:].itertuples(index=False)):
        if (cur.month - prev.month).n != 1:
            continue
        change = cur.shares_outstanding - prev.shares_outstanding
        rows.append({"month_end": cur.month_end, "shares_change": change, "nav": cur.nav,
                     "snapshot_flow_usd": change * cur.nav,
                     "start_effective_date": prev.effective_date, "end_effective_date": cur.effective_date})
    return pd.DataFrame(rows, columns=["month_end", "shares_change", "nav", "snapshot_flow_usd", "start_effective_date", "end_effective_date"])


def reconcile_with_nport(series: pd.DataFrame, nport_flows: pd.DataFrame | None,
                         tolerance_days: int = MONTH_END_TOLERANCE_DAYS) -> dict[str, Any]:
    """Month-by-month comparison of snapshot flow with the fund's N-PORT net
    flow over the calendar months both cover. `available` is False, with
    the reason, when there is no such month."""
    if series.empty:
        return {"available": False, "reason": "no snapshots"}
    monthly = snapshot_monthly_flows(series, tolerance_days)
    month_ends_covered = month_end_observations(series, tolerance_days)["month_end"].tolist()
    base: dict[str, Any] = {
        "month_end_tolerance_days": tolerance_days,
        "tolerance_rule": "one creation unit (%d shares) at the month-end NAV plus %.0f%% of the N-PORT flow"
                          % (CREATION_UNIT_SHARES, 100 * TOLERANCE_SHARE_OF_FLOW),
        # A month end is covered when an observation lies within the tolerance of
        # it; a month's flow needs both of its bounding month ends covered.
        "snapshot_month_ends_covered": month_ends_covered,
        "snapshot_months_covered": monthly["month_end"].tolist(),
    }
    if nport_flows is None or nport_flows.empty:
        return {"available": False, "reason": "no N-PORT flows file", **base}
    fund = nport_flows[nport_flows["fund_id"] == NPORT_FUND_ID].copy()
    if fund.empty:
        return {"available": False, "reason": "no N-PORT rows for %s" % NPORT_FUND_ID, **base}
    fund = fund[fund["net_flow"].notna()].sort_values("month_end")
    base["nport_months_covered"] = [fund["month_end"].min(), fund["month_end"].max()] if not fund.empty else None
    base["nport_net_flow_total"] = round(float(fund["net_flow"].sum()), 2) if not fund.empty else None
    common = monthly.merge(fund[["month_end", "sales", "redemption", "net_flow"]], on="month_end", how="inner")
    if common.empty:
        if monthly.empty and month_ends_covered:
            snapshot_side = "month ends with an observation %s but no two consecutive ones, so no monthly flow yet" % month_ends_covered
        elif monthly.empty:
            snapshot_side = "none (no observation within %d days of a month end)" % tolerance_days
        else:
            snapshot_side = str(monthly["month_end"].tolist())
        reason = "no calendar month is covered by both sources: N-PORT monthly flows %s; snapshot months covered %s" % (
            "run %s to %s" % tuple(base["nport_months_covered"]) if base["nport_months_covered"] else "absent", snapshot_side)
        return {"available": False, "reason": reason, **base}
    common["signed_error_usd"] = common["snapshot_flow_usd"] - common["net_flow"]
    common["tolerance_usd"] = CREATION_UNIT_SHARES * common["nav"] + TOLERANCE_SHARE_OF_FLOW * common["net_flow"].abs()
    common["within_tolerance"] = common["signed_error_usd"].abs() <= common["tolerance_usd"]
    return {
        "available": True,
        **base,
        "months_compared": int(len(common)),
        "months_within_tolerance": int(common["within_tolerance"].sum()),
        "signed_error_total_usd": round(float(common["signed_error_usd"].sum()), 2),
        "mean_abs_error_usd": round(float(common["signed_error_usd"].abs().mean()), 2),
        "months": [
            {k: (round(float(v), 2) if isinstance(v, float) else (bool(v) if isinstance(v, (bool,)) else v))
             for k, v in row.items()}
            for row in common.to_dict("records")
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--nport-flows", type=Path, default=DEFAULT_NPORT_FLOWS)
    args = parser.parse_args(argv)

    snapshots = load_snapshots(args.raw_root)
    series = build_series(snapshots)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    series.to_csv(args.out_dir / "snapshot_series.csv", index=False)
    nport = pd.read_csv(args.nport_flows) if args.nport_flows and args.nport_flows.exists() else None
    summary: dict[str, Any] = {
        "snapshots": int(len(series)),
        "window": [series["snapshot_date"].iloc[0], series["snapshot_date"].iloc[-1]] if not series.empty else None,
        "shares_outstanding_first_last": [series["shares_outstanding"].iloc[0], series["shares_outstanding"].iloc[-1]] if not series.empty else None,
        "net_assets_first_last": [series["net_assets"].iloc[0], series["net_assets"].iloc[-1]] if not series.empty else None,
        "flow_usd_total": round(float(series["flow_usd"].sum(skipna=True)), 2) if not series.empty else None,
        "observations_dated_by": ({str(k): int(v) for k, v in series["effective_date_source"].value_counts().items()}
                                  if not series.empty else {}),
        "pulls_collapsed_to_same_as_of_date": int(len(snapshots) - len(series)),
        "largest_gap_days": int(series["days_since_prior"].max()) if len(series) > 1 else None,
        "reconciliation": reconcile_with_nport(series, nport),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
