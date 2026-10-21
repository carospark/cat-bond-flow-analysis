"""Join N-PORT fund holdings to the deal universe and cross-check fund marks against TRACE.

Reads the parsed holdings from parse_nport.py, the strict bridge, the
program-level bridge when present, the daily deal trades from
build_deal_panel.py, and the parsed deal directory when supplied, and writes:

    data/fund_holdings_by_deal.csv     one row per fund, quarter end, and CUSIP,
                                       with the deal it attributes to, par held,
                                       market value, share of fund net assets,
                                       and the fund's mark as a price per 100
    data/deal_holdings_quarterly.csv   one row per deal and quarter end: funds
                                       holding, par and value held, par-weighted
                                       mark, and share of the deal's issued size
    data/fund_holdings_summary.json    coverage, registered-fund exposure by
                                       quarter, unbridged holdings, and the
                                       mark-versus-TRACE comparison

Marks are only taken from debt positions reported in principal amount
(units PA, asset category DBT); fund units and equity positions have no
price per 100. The TRACE comparison takes, for each CUSIP and quarter end,
the volume-weighted price of trades within a window around that date and
compares it with the par-weighted fund mark. The two sources are
independent, so agreement is evidence that the bridge, the cleaning, and
the holdings parse are all keyed on the same securities.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_deal_panel import combine_bridges  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEFAULT_HOLDINGS = DATA / "processed" / "nport" / "fund_holdings.csv"
DEFAULT_BRIDGE = DATA / "bridge.csv"
DEFAULT_PROGRAM_BRIDGE = DATA / "bridge_program.csv"
DEFAULT_TRADES = DATA / "deal_daily_trades.csv"
SIZE_PATTERN = re.compile(r"^\s*([$€£¥]|A\$|C\$|NZ\$|CHF|JPY|EUR|GBP|USD)?\s*([\d,.]+)\s*(bn|b|m|mn|million|billion|k)?\s*$", re.I)
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "A$": "AUD", "C$": "CAD", "NZ$": "NZD"}


def parse_size(text: str | None) -> tuple[float | None, str | None]:
    """'$362m' -> (362e6, 'USD'); '€200m' -> (200e6, 'EUR'); unparseable -> (None, None)."""
    if not isinstance(text, str):
        return None, None
    match = SIZE_PATTERN.match(text)
    if not match:
        return None, None
    symbol, number, scale = match.groups()
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None, None
    scale = (scale or "").lower()
    if scale in ("bn", "b", "billion"):
        value *= 1e9
    elif scale in ("m", "mn", "million"):
        value *= 1e6
    elif scale == "k":
        value *= 1e3
    currency = CURRENCY_SYMBOLS.get(symbol or "", (symbol or "").upper() or None)
    return value, currency


def attribute_holdings(holdings: pd.DataFrame, bridge: pd.DataFrame) -> pd.DataFrame:
    """Holdings with CUSIPs, joined to deals, with par and mark where meaningful."""
    out = holdings[holdings["cusip"].notna()].copy()
    out["cusip"] = out["cusip"].astype(str).str.strip().str.upper()
    # Filers put an all-zero CUSIP on positions that have none: segregated-account
    # cells, quota shares, and some sovereign notes. Those are not bridge gaps.
    out = out[~out["cusip"].str.fullmatch(r"0+")]
    # Fiscal quarters differ by fund (Stone Ridge ends Jan/Apr/Jul/Oct, the ETF
    # Mar/Jun/Sep/Dec) and some filers date the period to the last business day,
    # so a calendar month key is kept beside the filed period end.
    out["period_month"] = pd.to_datetime(out["period_end"]).dt.to_period("M").astype(str)
    out = out.merge(
        bridge[["cusip_id", "deal_url", "match_confidence"]].rename(columns={"cusip_id": "cusip"}),
        on="cusip",
        how="left",
    )
    is_par = (out["units"] == "PA") & (out["asset_category"] == "DBT")
    out["par"] = out["balance"].where(is_par)
    out["mark_price"] = (out["value_usd"] / out["par"] * 100.0).where(is_par & (out["par"] > 0))
    # A mark far outside 0..200 is a units or currency error in the filing, not a price.
    out.loc[~out["mark_price"].between(0, 200), "mark_price"] = pd.NA
    out["mark_price"] = pd.to_numeric(out["mark_price"], errors="coerce")
    columns = [
        "fund_id", "period_end", "period_month", "filing_date", "accession", "cusip", "deal_url", "match_confidence",
        "name", "title", "par", "value_usd", "pct_net_assets", "mark_price", "currency",
        "maturity_date", "coupon_kind", "annualized_rate", "is_default", "fair_value_level",
        "asset_category", "units",
    ]
    return out[columns].sort_values(["period_end", "fund_id", "cusip"]).reset_index(drop=True)


def deal_quarterly(attributed: pd.DataFrame, deal_sizes: pd.DataFrame | None) -> pd.DataFrame:
    bridged = attributed[attributed["deal_url"].notna()].copy()
    bridged["par_x_mark"] = bridged["par"] * bridged["mark_price"]
    grouped = bridged.groupby(["deal_url", "period_month"], sort=True)
    out = grouped.agg(
        period_end=("period_end", "max"),
        n_funds=("fund_id", "nunique"),
        n_cusips=("cusip", "nunique"),
        par_held=("par", "sum"),
        value_held=("value_usd", "sum"),
        par_with_mark=("par", lambda s: s[bridged.loc[s.index, "mark_price"].notna()].sum()),
        par_x_mark=("par_x_mark", "sum"),
        funds=("fund_id", lambda s: ";".join(sorted(set(s)))),
    ).reset_index()
    out["mark_par_weighted"] = (out["par_x_mark"] / out["par_with_mark"]).where(out["par_with_mark"] > 0)
    out = out.drop(columns=["par_x_mark", "par_with_mark"])
    if deal_sizes is not None and not deal_sizes.empty:
        out = out.merge(deal_sizes, on="deal_url", how="left")
        usd = out["size_currency"].eq("USD") & (out["size_value"] > 0)
        out["share_of_size"] = (out["par_held"] / out["size_value"]).where(usd)
    return out


def deal_size_table(deals: pd.DataFrame) -> pd.DataFrame:
    parsed = deals["size"].map(parse_size)
    return pd.DataFrame(
        {
            "deal_url": deals["deal_url"],
            "size_value": [value for value, _ in parsed],
            "size_currency": [currency for _, currency in parsed],
        }
    ).dropna(subset=["size_value"]).drop_duplicates("deal_url")


def compare_marks_to_trace(attributed: pd.DataFrame, trades: pd.DataFrame, window_days: int = 15) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Par-weighted fund mark versus TRACE VWAP around each quarter end, per CUSIP."""
    marks = attributed[attributed["mark_price"].notna() & attributed["par"].gt(0)].copy()
    marks["par_x_mark"] = marks["par"] * marks["mark_price"]
    fund_marks = (
        marks.groupby(["cusip", "period_end"])
        .agg(par=("par", "sum"), par_x_mark=("par_x_mark", "sum"), n_funds=("fund_id", "nunique"))
        .reset_index()
    )
    fund_marks["fund_mark"] = fund_marks["par_x_mark"] / fund_marks["par"]
    fund_marks["period_end_dt"] = pd.to_datetime(fund_marks["period_end"])

    t = trades.rename(columns={"cusip_id": "cusip"}).copy()
    t["trade_date"] = pd.to_datetime(t["trade_date"])
    t["notional"] = t["vwap"] * t["volume"]
    rows = []
    by_cusip = {cusip: frame for cusip, frame in t.groupby("cusip")}
    for row in fund_marks.itertuples(index=False):
        frame = by_cusip.get(row.cusip)
        if frame is None:
            continue
        near = frame[(frame["trade_date"] - row.period_end_dt).abs() <= pd.Timedelta(days=window_days)]
        if near.empty or near["volume"].sum() <= 0:
            continue
        rows.append(
            {
                "cusip": row.cusip,
                "period_end": row.period_end,
                "fund_mark": row.fund_mark,
                "n_funds": row.n_funds,
                "trace_vwap": near["notional"].sum() / near["volume"].sum(),
                "trace_trades": int(near["n_trades"].sum()),
                "trace_volume": float(near["volume"].sum()),
            }
        )
    comparison = pd.DataFrame(rows)
    stats: dict[str, Any] = {"window_days": window_days, "pairs": int(len(comparison))}
    if not comparison.empty:
        diff = comparison["fund_mark"] - comparison["trace_vwap"]
        stats.update(
            {
                "cusips": int(comparison["cusip"].nunique()),
                "median_abs_diff_points": round(float(diff.abs().median()), 2),
                "mean_diff_points": round(float(diff.mean()), 2),
                "share_within_2_points": round(float((diff.abs() <= 2).mean()), 3),
                "share_within_5_points": round(float((diff.abs() <= 5).mean()), 3),
                "correlation": round(float(comparison[["fund_mark", "trace_vwap"]].corr().iloc[0, 1]), 3),
                "distressed_pairs_both_below_80": int(((comparison["fund_mark"] < 80) & (comparison["trace_vwap"] < 80)).sum()),
                "pairs_either_below_80": int(((comparison["fund_mark"] < 80) | (comparison["trace_vwap"] < 80)).sum()),
            }
        )
    return comparison, stats


def summarize(attributed: pd.DataFrame, quarterly: pd.DataFrame, bridge: pd.DataFrame, mark_stats: dict[str, Any]) -> dict[str, Any]:
    bridged = attributed[attributed["deal_url"].notna()]
    unbridged = attributed[attributed["deal_url"].isna()]
    by_quarter = (
        attributed.assign(bridged=attributed["deal_url"].notna())
        .groupby("period_month")
        .agg(
            funds=("fund_id", "nunique"),
            cusips=("cusip", "nunique"),
            value_usd=("value_usd", "sum"),
            value_bridged=("value_usd", lambda s: s[attributed.loc[s.index, "deal_url"].notna()].sum()),
            par_bridged=("par", lambda s: s[attributed.loc[s.index, "deal_url"].notna()].sum()),
        )
    )
    by_quarter["bridged_value_share"] = (by_quarter["value_bridged"] / by_quarter["value_usd"]).round(3)
    top_unbridged = (
        unbridged.groupby(["cusip", "name"])["value_usd"].sum().sort_values(ascending=False).head(25)
    )
    latest = quarterly[quarterly["period_month"] == quarterly["period_month"].max()] if not quarterly.empty else quarterly
    summary = {
        "holding_rows_with_cusip": int(len(attributed)),
        "holding_rows_bridged": int(len(bridged)),
        "distinct_cusips": int(attributed["cusip"].nunique()),
        "distinct_cusips_bridged": int(bridged["cusip"].nunique()),
        "bridge_cusips_total": int(bridge["cusip_id"].nunique()),
        "deals_with_any_fund_holding": int(bridged["deal_url"].nunique()),
        "deals_in_bridge": int(bridge["deal_url"].nunique()),
        "bridged_by_confidence": {k: int(v) for k, v in bridged["match_confidence"].value_counts().items()},
        "value_by_quarter_usd": {
            period: {col: (round(float(val), 3) if isinstance(val, float) else int(val)) for col, val in row.items()}
            for period, row in by_quarter.to_dict("index").items()
        },
        "latest_quarter": quarterly["period_month"].max() if not quarterly.empty else None,
        "latest_quarter_deals_held": int(len(latest)),
        "latest_quarter_median_share_of_size": (
            round(float(latest["share_of_size"].median()), 3) if "share_of_size" in latest and latest["share_of_size"].notna().any() else None
        ),
        "latest_quarter_deals_over_half_held": (
            int((latest["share_of_size"] > 0.5).sum()) if "share_of_size" in latest else None
        ),
        "top_unbridged_holdings_by_value": [
            {"cusip": cusip, "name": name, "value_usd": round(float(value), 0)} for (cusip, name), value in top_unbridged.items()
        ],
        "mark_vs_trace": mark_stats,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--holdings", type=Path, default=DEFAULT_HOLDINGS)
    parser.add_argument("--bridge", type=Path, default=DEFAULT_BRIDGE)
    parser.add_argument("--program-bridge", type=Path, default=DEFAULT_PROGRAM_BRIDGE)
    parser.add_argument("--trades", type=Path, default=DEFAULT_TRADES)
    parser.add_argument("--deals", type=Path, default=None, help="parsed deal directory, for issued sizes")
    parser.add_argument("--out-dir", type=Path, default=DATA)
    parser.add_argument("--window-days", type=int, default=15)
    args = parser.parse_args(argv)

    holdings = pd.read_csv(args.holdings, low_memory=False)
    bridge = pd.read_csv(args.bridge, dtype={"cusip_id": str})
    program = pd.read_csv(args.program_bridge, dtype={"cusip_id": str}) if args.program_bridge and args.program_bridge.exists() else None
    combined = combine_bridges(bridge, program)
    attributed = attribute_holdings(holdings, combined)

    deal_sizes = None
    if args.deals and args.deals.exists():
        deal_sizes = deal_size_table(pd.read_csv(args.deals, dtype=str, usecols=["deal_url", "size"]))
    quarterly = deal_quarterly(attributed, deal_sizes)

    comparison, mark_stats = pd.DataFrame(), {"pairs": 0, "note": "no trades file"}
    if args.trades and args.trades.exists():
        trades = pd.read_csv(args.trades, dtype={"cusip_id": str})
        comparison, mark_stats = compare_marks_to_trace(attributed, trades, args.window_days)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    attributed.to_csv(args.out_dir / "fund_holdings_by_deal.csv", index=False)
    quarterly.to_csv(args.out_dir / "deal_holdings_quarterly.csv", index=False)
    comparison.to_csv(args.out_dir / "fund_marks_vs_trace.csv", index=False)
    summary = summarize(attributed, quarterly, combined, mark_stats)
    summary["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (args.out_dir / "fund_holdings_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    printable = {k: v for k, v in summary.items() if k not in ("value_by_quarter_usd", "top_unbridged_holdings_by_value")}
    print(json.dumps(printable, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
