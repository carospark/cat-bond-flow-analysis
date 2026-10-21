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

Gaps between snapshots are carried as `days_since_prior`; a flow row spans
the whole gap, not one day, and the per-day column divides it evenly only
as a convenience for plotting.
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
    if snapshots.empty:
        return snapshots
    out = snapshots.copy()
    out["implied_nav"] = out["net_assets"] / out["shares_outstanding"]
    out["shares_change"] = out["shares_outstanding"].diff()
    out["flow_usd"] = out["shares_change"] * out["nav"]
    out["days_since_prior"] = pd.to_datetime(out["snapshot_date"]).diff().dt.days
    out["flow_usd_per_day"] = out["flow_usd"] / out["days_since_prior"]
    out["net_assets_change"] = out["net_assets"].diff()
    # The part of the net-asset change that is not creations or redemptions
    # is performance plus distributions over the gap.
    out["non_flow_change_usd"] = out["net_assets_change"] - out["flow_usd"]
    return out


def reconcile_with_nport(series: pd.DataFrame, nport_flows: pd.DataFrame | None) -> dict[str, Any]:
    if nport_flows is None or nport_flows.empty or series.empty:
        return {"available": False}
    fund = nport_flows[nport_flows["fund_id"] == NPORT_FUND_ID].copy()
    if fund.empty:
        return {"available": False}
    fund = fund.sort_values("month_end")
    quarterly = (
        fund.groupby("period_end")
        .agg(sales=("sales", "sum"), redemption=("redemption", "sum"), net_flow=("net_flow", "sum"),
             net_assets=("net_assets_at_period_end", "max"))
        .reset_index()
    )
    first, last = series.iloc[0], series.iloc[-1]
    overlap = fund[(fund["month_end"] >= first["snapshot_date"][:7] + "-01") & (fund["month_end"] <= last["snapshot_date"])]
    return {
        "available": True,
        "nport_quarters": quarterly.to_dict("records"),
        "nport_net_flow_total": round(float(fund["net_flow"].sum()), 2),
        "snapshot_window": [first["snapshot_date"], last["snapshot_date"]],
        "snapshot_flow_total": round(float(series["flow_usd"].sum(skipna=True)), 2),
        "nport_net_flow_in_snapshot_window": round(float(overlap["net_flow"].sum()), 2) if not overlap.empty else None,
        "nport_months_in_snapshot_window": overlap["month_end"].tolist(),
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
        "largest_gap_days": int(series["days_since_prior"].max()) if len(series) > 1 else None,
        "reconciliation": reconcile_with_nport(series, nport),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
