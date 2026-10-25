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
price per 100. A position whose principal is not in dollars has its par
converted at the monthly average rate of the report month before the mark
is taken (the companion parser's tracked ECB/BoE table, passed with
--fx-table); `mark_basis` records `usd`, `fx_converted` or `fx_rate_missing`,
and a mark with no rate is null rather than a dollar value over a
local-currency par.

The TRACE comparison takes, for each CUSIP and quarter end, the volume-
weighted price of trades in the window before the quarter end and in the
window after it, separately and together, and compares each with the
par-weighted fund mark. The output reports the tails of the gap
distribution (90th, 95th, 99th percentiles, counts over 5, 10 and 20
points) and the share of pairs whose nearest trade is more than a week from
the quarter end (stale). The two sources are independent, so agreement is
evidence that the trade cleaning and the holdings parse are keyed on the
same securities. It is not a check on the bridge: a CUSIP attached to the
wrong deal shows the same agreement. For that, `compare_marks_by_deal` keys
on the deal: for every CUSIP a fund holds, its mark is set against the
par-weighted mark of the *other* CUSIPs of the same deal in the same
quarter. Tranches of one deal can price apart, so the table is a screen for
a human, not a verdict; a wrong link should surface as a large gap carrying
a medium confidence or a title that only agrees in-sample.
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
DEFAULT_FX_TABLE = ROOT.parent / "cat-bond-issuance" / "src" / "fx_monthly_usd.csv"
STALE_DAYS = 7
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


def load_fx_table(path: Path | None) -> dict[tuple[str, str], float]:
    """{(currency, 'YYYY-MM'): USD per unit} from the parser's monthly table, or {}."""
    if path is None or not Path(path).exists():
        return {}
    table = pd.read_csv(path, comment="#", dtype={"month": str, "currency": str})
    return {(row.currency, row.month): float(row.usd_per_unit) for row in table.itertuples(index=False)}


def attribute_holdings(holdings: pd.DataFrame, bridge: pd.DataFrame, fx: dict[tuple[str, str], float] | None = None) -> pd.DataFrame:
    """Holdings with CUSIPs, joined to deals, with par and mark where meaningful.

    `fx` converts non-USD par to dollars at the report month's rate before the
    mark is taken; without a rate the mark is null (`mark_basis`
    fx_rate_missing). A blank currency is taken as USD and flagged.
    """
    fx = fx or {}
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
    currency = out["currency"].fillna("").astype(str).str.strip().str.upper()
    out["par_currency"] = currency.where(currency.ne(""), "USD")
    rates = [
        1.0 if ccy == "USD" else fx.get((ccy, month))
        for ccy, month in zip(out["par_currency"], out["period_month"])
    ]
    out["fx_usd_per_unit"] = pd.to_numeric(pd.Series(rates, index=out.index), errors="coerce")
    out["par_usd"] = out["par"] * out["fx_usd_per_unit"]
    basis = pd.Series("usd", index=out.index)
    basis = basis.mask(currency.eq(""), "currency_missing_assumed_usd")
    basis = basis.mask(out["par_currency"].ne("USD") & out["fx_usd_per_unit"].notna(), "fx_converted")
    basis = basis.mask(out["par_currency"].ne("USD") & out["fx_usd_per_unit"].isna(), "fx_rate_missing")
    out["mark_basis"] = basis.where(is_par, None)
    out["mark_price"] = (out["value_usd"] / out["par_usd"] * 100.0).where(is_par & (out["par_usd"] > 0))
    # A mark far outside 0..200 is a units or currency error in the filing, not a price.
    out.loc[~out["mark_price"].between(0, 200), "mark_price"] = pd.NA
    out["mark_price"] = pd.to_numeric(out["mark_price"], errors="coerce")
    columns = [
        "fund_id", "period_end", "period_month", "filing_date", "accession", "cusip", "deal_url", "match_confidence",
        "name", "title", "par", "par_currency", "fx_usd_per_unit", "par_usd", "value_usd", "pct_net_assets",
        "mark_price", "mark_basis", "currency",
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


def _tail_stats(diff: pd.Series) -> dict[str, Any]:
    diff = diff.dropna()
    if diff.empty:
        return {"pairs": 0}
    a = diff.abs()
    return {
        "pairs": int(len(diff)),
        "median_abs_diff_points": round(float(a.median()), 2),
        "mean_diff_points": round(float(diff.mean()), 2),
        "p90_abs_points": round(float(a.quantile(0.90)), 2),
        "p95_abs_points": round(float(a.quantile(0.95)), 2),
        "p99_abs_points": round(float(a.quantile(0.99)), 2),
        "max_abs_points": round(float(a.max()), 2),
        "share_within_2_points": round(float((a <= 2).mean()), 3),
        "share_within_5_points": round(float((a <= 5).mean()), 3),
        "pairs_over_5_points": int((a > 5).sum()),
        "pairs_over_10_points": int((a > 10).sum()),
        "pairs_over_20_points": int((a > 20).sum()),
    }


def compare_marks_to_trace(attributed: pd.DataFrame, trades: pd.DataFrame, window_days: int = 15,
                           stale_days: int = STALE_DAYS) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Par-weighted fund mark versus TRACE VWAP around each quarter end, per CUSIP.

    Three VWAPs per pair: trades in [quarter end - window, quarter end]
    (`trace_vwap_before`), in (quarter end, quarter end + window]
    (`trace_vwap_after`), and both (`trace_vwap`). `days_to_nearest_trade`
    and `stale` (nearest trade more than `stale_days` away) qualify each
    pair. Marks are only used where `par_usd` is known.
    """
    marks = attributed[attributed["mark_price"].notna() & attributed["par_usd"].gt(0)].copy()
    marks["par_x_mark"] = marks["par_usd"] * marks["mark_price"]
    fund_marks = (
        marks.groupby(["cusip", "period_end"])
        .agg(par=("par_usd", "sum"), par_x_mark=("par_x_mark", "sum"), n_funds=("fund_id", "nunique"))
        .reset_index()
    )
    fund_marks["fund_mark"] = fund_marks["par_x_mark"] / fund_marks["par"]
    fund_marks["period_end_dt"] = pd.to_datetime(fund_marks["period_end"])

    t = trades.rename(columns={"cusip_id": "cusip"}).copy()
    t["trade_date"] = pd.to_datetime(t["trade_date"])
    t["notional"] = t["vwap"] * t["volume"]
    rows = []
    by_cusip = {cusip: frame for cusip, frame in t.groupby("cusip")}

    def vwap(frame: pd.DataFrame) -> float | None:
        return float(frame["notional"].sum() / frame["volume"].sum()) if not frame.empty and frame["volume"].sum() > 0 else None

    for row in fund_marks.itertuples(index=False):
        frame = by_cusip.get(row.cusip)
        if frame is None:
            continue
        offset = (frame["trade_date"] - row.period_end_dt).dt.days
        near = frame[offset.abs() <= window_days]
        if near.empty or near["volume"].sum() <= 0:
            continue
        before = near[offset.loc[near.index] <= 0]
        after = near[offset.loc[near.index] > 0]
        nearest = int(offset.loc[near.index].abs().min())
        rows.append(
            {
                "cusip": row.cusip,
                "period_end": row.period_end,
                "fund_mark": row.fund_mark,
                "n_funds": row.n_funds,
                "trace_vwap": vwap(near),
                "trace_vwap_before": vwap(before),
                "trace_vwap_after": vwap(after),
                "trace_trades": int(near["n_trades"].sum()),
                "trace_trades_before": int(before["n_trades"].sum()),
                "trace_trades_after": int(after["n_trades"].sum()),
                "trace_volume": float(near["volume"].sum()),
                "days_to_nearest_trade": nearest,
                "stale": nearest > stale_days,
            }
        )
    comparison = pd.DataFrame(rows)
    stats: dict[str, Any] = {"window_days": window_days, "stale_days": stale_days, "pairs": int(len(comparison))}
    if not comparison.empty:
        for col in ("trace_vwap", "trace_vwap_before", "trace_vwap_after"):
            comparison["diff_" + col.replace("trace_vwap", "points")] = comparison["fund_mark"] - comparison[col]
        comparison = comparison.rename(columns={"diff_points": "diff_points_both"})
        diff = comparison["diff_points_both"]
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
                "windows": {
                    "both": _tail_stats(comparison["diff_points_both"]),
                    "before_quarter_end": _tail_stats(comparison["diff_points_before"]),
                    "after_quarter_end": _tail_stats(comparison["diff_points_after"]),
                    "pairs_with_trades_both_sides": int((comparison["trace_vwap_before"].notna() & comparison["trace_vwap_after"].notna()).sum()),
                },
                "stale": {
                    "share_of_pairs": round(float(comparison["stale"].mean()), 3),
                    "pairs": int(comparison["stale"].sum()),
                    "median_abs_diff_stale": round(float(diff[comparison["stale"]].abs().median()), 2) if comparison["stale"].any() else None,
                    "median_abs_diff_fresh": round(float(diff[~comparison["stale"]].abs().median()), 2) if (~comparison["stale"]).any() else None,
                    "median_days_to_nearest_trade": float(comparison["days_to_nearest_trade"].median()),
                },
            }
        )
    return comparison, stats


def compare_marks_by_deal(attributed: pd.DataFrame, title_evidence: pd.DataFrame | None = None,
                          gap_points: float = 10.0) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Each held CUSIP's fund mark against the other CUSIPs of the same deal.

    Keyed on the deal, not the CUSIP, so a CUSIP attached to the wrong deal
    appears as a mark that disagrees with the rest of the deal's tranches in
    the same quarter. One row per (deal, quarter end, CUSIP) where the deal
    has at least two marked CUSIPs; `gap_points` is the screening threshold.
    """
    marks = attributed[attributed["deal_url"].notna() & attributed["mark_price"].notna() & attributed["par_usd"].gt(0)].copy()
    marks["par_x_mark"] = marks["par_usd"] * marks["mark_price"]
    per_cusip = (
        marks.groupby(["deal_url", "period_end", "cusip"])
        .agg(par=("par_usd", "sum"), par_x_mark=("par_x_mark", "sum"), n_funds=("fund_id", "nunique"),
             funds=("fund_id", lambda s: ";".join(sorted(set(s)))), title=("title", "first"),
             match_confidence=("match_confidence", "first"))
        .reset_index()
    )
    per_cusip["cusip_mark"] = per_cusip["par_x_mark"] / per_cusip["par"]
    deal_tot = per_cusip.groupby(["deal_url", "period_end"]).agg(deal_par=("par", "sum"), deal_par_x_mark=("par_x_mark", "sum"),
                                                                  n_cusips=("cusip", "nunique")).reset_index()
    out = per_cusip.merge(deal_tot, on=["deal_url", "period_end"])
    out = out[out["n_cusips"] >= 2].copy()
    other_par = out["deal_par"] - out["par"]
    out["others_mark"] = ((out["deal_par_x_mark"] - out["par_x_mark"]) / other_par).where(other_par > 0)
    out["gap_points"] = out["cusip_mark"] - out["others_mark"]
    # One wrong link also pulls the reference away from its true siblings, so
    # the candidate in each deal-quarter is the CUSIP farthest from the rest.
    out["is_deal_outlier"] = out["gap_points"].abs().eq(out.groupby(["deal_url", "period_end"])["gap_points"].transform(lambda s: s.abs().max()))
    if title_evidence is not None and not title_evidence.empty:
        out = out.merge(title_evidence.rename(columns={"cusip_id": "cusip"})[["cusip", "title_evidence"]].drop_duplicates("cusip"),
                        on="cusip", how="left")
    else:
        out["title_evidence"] = None
    out = out.drop(columns=["par_x_mark", "deal_par_x_mark"]).sort_values("gap_points", key=lambda s: s.abs(), ascending=False)
    columns = ["deal_url", "period_end", "cusip", "title", "match_confidence", "title_evidence", "n_funds", "funds",
               "par", "cusip_mark", "n_cusips", "deal_par", "others_mark", "gap_points", "is_deal_outlier"]
    out = out[columns].reset_index(drop=True)
    stats: dict[str, Any] = {"gap_threshold_points": gap_points, "rows": int(len(out))}
    if not out.empty:
        gap = out["gap_points"].abs()
        deal_periods = out.groupby(["deal_url", "period_end"])["gap_points"].apply(lambda s: s.abs().max())
        flagged = out[(gap > gap_points) & out["is_deal_outlier"]]
        stats.update(
            {
                "deal_quarters_with_two_or_more_cusips": int(len(deal_periods)),
                "deal_quarters_max_gap_over_threshold": int((deal_periods > gap_points).sum()),
                "rows_over_threshold": int((gap > gap_points).sum()),
                "cusips_over_threshold": int(flagged["cusip"].nunique()),
                "cusip_quarters_over_threshold": int(len(flagged)),
                "median_abs_gap_points": round(float(gap.median()), 2),
                "p95_abs_gap_points": round(float(gap.quantile(0.95)), 2),
                "flagged_by_confidence": {k: int(v) for k, v in flagged["match_confidence"].value_counts().items()},
                "flagged_by_title_evidence": {str(k): int(v) for k, v in flagged["title_evidence"].fillna("unknown").value_counts().items()},
                "top_disagreements": [
                    {"deal_url": r.deal_url, "period_end": r.period_end, "cusip": r.cusip, "title": r.title,
                     "match_confidence": r.match_confidence, "title_evidence": r.title_evidence,
                     "cusip_mark": round(float(r.cusip_mark), 2), "others_mark": round(float(r.others_mark), 2),
                     "gap_points": round(float(r.gap_points), 2)}
                    for r in flagged.head(15).itertuples(index=False)
                ],
            }
        )
    return out, stats


def summarize(attributed: pd.DataFrame, quarterly: pd.DataFrame, bridge: pd.DataFrame, mark_stats: dict[str, Any],
              deal_mark_stats: dict[str, Any] | None = None) -> dict[str, Any]:
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
        "mark_basis_counts": {str(k): int(v) for k, v in attributed["mark_basis"].dropna().value_counts().items()},
        "mark_vs_trace": mark_stats,
        "mark_vs_deal": deal_mark_stats or {},
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
    parser.add_argument("--fx-table", type=Path, default=DEFAULT_FX_TABLE,
                        help="monthly USD-per-unit table for non-USD par (the parser's src/fx_monthly_usd.csv)")
    args = parser.parse_args(argv)

    holdings = pd.read_csv(args.holdings, low_memory=False)
    bridge = pd.read_csv(args.bridge, dtype={"cusip_id": str})
    program = pd.read_csv(args.program_bridge, dtype={"cusip_id": str}) if args.program_bridge and args.program_bridge.exists() else None
    combined = combine_bridges(bridge, program)
    fx = load_fx_table(args.fx_table)
    attributed = attribute_holdings(holdings, combined, fx)

    deal_sizes = None
    if args.deals and args.deals.exists():
        deal_sizes = deal_size_table(pd.read_csv(args.deals, dtype=str, usecols=["deal_url", "size"]))
    quarterly = deal_quarterly(attributed, deal_sizes)

    comparison, mark_stats = pd.DataFrame(), {"pairs": 0, "note": "no trades file"}
    if args.trades and args.trades.exists():
        trades = pd.read_csv(args.trades, dtype={"cusip_id": str})
        comparison, mark_stats = compare_marks_to_trace(attributed, trades, args.window_days)

    title_evidence = bridge[["cusip_id", "title_evidence"]] if "title_evidence" in bridge.columns else None
    by_deal, deal_mark_stats = compare_marks_by_deal(attributed, title_evidence)
    deal_mark_stats["fx_table"] = str(args.fx_table) if fx else "none: non-USD par cannot be marked"

    args.out_dir.mkdir(parents=True, exist_ok=True)
    attributed.to_csv(args.out_dir / "fund_holdings_by_deal.csv", index=False)
    quarterly.to_csv(args.out_dir / "deal_holdings_quarterly.csv", index=False)
    comparison.to_csv(args.out_dir / "fund_marks_vs_trace.csv", index=False)
    by_deal.to_csv(args.out_dir / "fund_marks_by_deal.csv", index=False)
    summary = summarize(attributed, quarterly, combined, mark_stats, deal_mark_stats)
    summary["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (args.out_dir / "fund_holdings_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    printable = {k: v for k, v in summary.items() if k not in ("value_by_quarter_usd", "top_unbridged_holdings_by_value")}
    printable["mark_vs_deal"] = {k: v for k, v in summary["mark_vs_deal"].items() if k != "top_disagreements"}
    print(json.dumps(printable, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
