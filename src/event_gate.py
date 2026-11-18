"""The first gate of the Phase 3 hurricane event study: how many bonds pass
all of (a) a bridge match, (b) usable TRACE prices on both sides of the
event, and (c) a storm-contract price history across the same window.

This counts; it tests nothing. The funnel per event, one row per deal:

1. ``exposed``: the deal's hazard map names ``hurricane_or_named_storm`` in
   Florida or a U.S. region containing it, with Florida not excluded
   (``classify_deals`` from ``event_check.py``, group ``exposed``).
2. ``alive_at_event``: some bridged CUSIP's TRACE issue date is on or before
   the event and its TRACE maturity on or after it.
3. ``strict_bridge`` / ``high_confidence``: the deal has a strict-bridge
   CUSIP at any confidence / at high confidence.
4. ``usable_prices``: the same rule as ``event_check.deal_changes``: a trade
   day with a volume-weighted price and positive volume in the pre-window
   (45 days) and another in the post-window (60 days). ``usable_prices_high``
   restricts the trades to high-confidence CUSIPs.
5. ``storm_history``: at least one hurricane contract (hazard class
   ``hurricane_or_named_storm``, region Florida or U.S.) carries a price on
   a day in the pre-window and one in the post-window. This is a property
   of the event, not of the bond, so every row shares it; the counts behind
   it (contracts priced each side, priced days) are in the summary.
6. ``mark_in_window``: a registered fund's N-PORT mark on the deal with a
   period end inside the window; ``mark_in_event_quarter``: a period end in
   the event's calendar quarter.

Outputs under ``data/event_gate/`` (gitignored): ``gate_<event>.csv`` and
``summary.json`` with the funnel on the strict bridge at any confidence and
on high-confidence pairs alone.

    ./.venv/bin/python src/event_gate.py
    ./.venv/bin/python src/event_gate.py --pre-days 60 --post-days 60
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from event_check import EVENTS, FLORIDA_REGIONS, HURRICANE, MARKET_REGIONS, classify_deals  # noqa: E402

TRADES_PATH = DATA / "deal_daily_trades.csv"
HAZARD_PATH = DATA / "deal_hazard_map.csv"
MARKET_PATH = DATA / "market_contract_daily.csv"
BRIDGE_PATH = DATA / "bridge.csv"
MARKS_PATH = DATA / "fund_marks_by_deal.csv"
OUTPUT_DIR = DATA / "event_gate"

FUNNEL = ["exposed", "alive_at_event", "strict_bridge", "usable_prices", "storm_history", "mark_in_window"]
FUNNEL_HIGH = ["exposed", "alive_at_event", "high_confidence", "usable_prices_high", "storm_history", "mark_in_window"]


def window(event_date: str, pre_days: int, post_days: int) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    t0 = pd.Timestamp(event_date)
    return t0 - pd.Timedelta(days=pre_days), t0, t0 + pd.Timedelta(days=post_days)


def bridge_by_deal(bridge: pd.DataFrame, event_date: str) -> pd.DataFrame:
    """Per deal: strict-bridge CUSIP counts by confidence and whether any
    CUSIP's TRACE dates straddle the event."""
    b = bridge.copy()
    t0 = pd.Timestamp(event_date)
    issue = pd.to_datetime(b["trace_issue_date"], errors="coerce")
    maturity = pd.to_datetime(b["trace_maturity_date"], errors="coerce")
    b["alive"] = issue.le(t0) & (maturity.isna() | maturity.ge(t0))
    b["high"] = b["match_confidence"].eq("high")
    g = b.groupby("deal_url")
    out = g.agg(cusips=("cusip_id", "nunique"), cusips_high=("high", "sum"), alive_at_event=("alive", "any")).reset_index()
    out["cusips_high"] = out["cusips_high"].astype(int)
    out["strict_bridge"] = out["cusips"].gt(0)
    out["high_confidence"] = out["cusips_high"].gt(0)
    return out


def usable_prices(trades: pd.DataFrame, event_date: str, pre_days: int, post_days: int,
                  high_only: bool = False) -> pd.DataFrame:
    """Per deal: trade days with a price on each side of the event, the
    ``deal_changes`` rule (vwap present, volume positive, inside the window)."""
    lo, t0, hi = window(event_date, pre_days, post_days)
    f = trades.copy()
    f["date"] = pd.to_datetime(f["trade_date"])
    f = f[(f["date"] >= lo) & (f["date"] <= hi) & f["vwap"].notna() & f["volume"].gt(0)]
    f = f[f["match_confidence"].ne("program")]
    if high_only:
        f = f[f["match_confidence"].eq("high")]
    f["side"] = "pre"
    f.loc[f["date"] > t0, "side"] = "post"
    f = f[f["date"] != t0]
    counts = f.groupby(["deal_url", "side"]).size().unstack(fill_value=0)
    for side in ("pre", "post"):
        if side not in counts:
            counts[side] = 0
    suffix = "_high" if high_only else ""
    out = counts.rename(columns={"pre": f"pre_trade_days{suffix}", "post": f"post_trade_days{suffix}"}).reset_index()
    out[f"usable_prices{suffix}"] = out[f"pre_trade_days{suffix}"].gt(0) & out[f"post_trade_days{suffix}"].gt(0)
    return out


def storm_history(market: pd.DataFrame, event_date: str, pre_days: int, post_days: int) -> dict:
    """Hurricane contracts in Florida or U.S. regions with a price on each side."""
    lo, t0, hi = window(event_date, pre_days, post_days)
    m = market.copy()
    m["date"] = pd.to_datetime(m["date"])
    hazards = m["hazard_classes"].fillna("").str.split(";")
    regions = m["regions"].fillna("").str.split(";")
    keep = hazards.map(lambda h: HURRICANE in h) & regions.map(lambda r: bool(MARKET_REGIONS & set(r)))
    m = m[keep & (m["date"] >= lo) & (m["date"] <= hi) & m["last_price"].notna()]
    pre = m[m["date"] < t0]
    post = m[m["date"] > t0]
    both = set(pre["contract_id"]) & set(post["contract_id"])
    return {
        "contracts_priced_pre": int(pre["contract_id"].nunique()),
        "contracts_priced_post": int(post["contract_id"].nunique()),
        "contracts_priced_both_sides": len(both),
        "priced_days_pre": int(pre["date"].nunique()),
        "priced_days_post": int(post["date"].nunique()),
        "platforms": sorted(set(m["platform"])),
        "passes": len(both) > 0,
    }


def marks_by_deal(marks: pd.DataFrame, event_date: str, pre_days: int, post_days: int) -> pd.DataFrame:
    lo, t0, hi = window(event_date, pre_days, post_days)
    m = marks.copy()
    m["period"] = pd.to_datetime(m["period_end"])
    quarter = t0.to_period("Q")
    m["in_window"] = (m["period"] >= lo) & (m["period"] <= hi)
    m["in_quarter"] = m["period"].dt.to_period("Q").eq(quarter)
    g = m.groupby("deal_url")
    out = g.agg(mark_in_window=("in_window", "any"), mark_in_event_quarter=("in_quarter", "any"),
                marks_in_window=("in_window", "sum")).reset_index()
    out["marks_in_window"] = out["marks_in_window"].astype(int)
    return out


def gate_table(hazard_map: pd.DataFrame, bridge: pd.DataFrame, trades: pd.DataFrame, market: pd.DataFrame,
               marks: pd.DataFrame, event_date: str, pre_days: int, post_days: int) -> tuple[pd.DataFrame, dict]:
    groups = classify_deals(hazard_map)
    table = pd.DataFrame({"deal_url": groups.index, "group": groups.values})
    table["exposed"] = table["group"].eq("exposed")
    table = table.merge(bridge_by_deal(bridge, event_date), on="deal_url", how="left")
    for col in ("cusips", "cusips_high"):
        table[col] = table[col].fillna(0).astype(int)
    for col in ("alive_at_event", "strict_bridge", "high_confidence"):
        table[col] = table[col].fillna(False).astype(bool)
    for high in (False, True):
        table = table.merge(usable_prices(trades, event_date, pre_days, post_days, high), on="deal_url", how="left")
    for col in ("pre_trade_days", "post_trade_days", "pre_trade_days_high", "post_trade_days_high"):
        table[col] = table[col].fillna(0).astype(int)
    for col in ("usable_prices", "usable_prices_high"):
        table[col] = table[col].fillna(False).astype(bool)
    storm = storm_history(market, event_date, pre_days, post_days)
    table["storm_history"] = bool(storm["passes"])
    table = table.merge(marks_by_deal(marks, event_date, pre_days, post_days), on="deal_url", how="left")
    table["marks_in_window"] = table["marks_in_window"].fillna(0).astype(int)
    for col in ("mark_in_window", "mark_in_event_quarter"):
        table[col] = table[col].fillna(False).astype(bool)

    def funnel(steps):
        mask = pd.Series(True, index=table.index)
        out = {}
        for step in steps:
            mask = mask & table[step]
            out[step] = int(mask.sum())
        return out

    table["passes_strict"] = table[FUNNEL[:-1]].all(axis=1)
    table["passes_high"] = table[FUNNEL_HIGH[:-1]].all(axis=1)
    summary = {
        "funnel_strict_any_confidence": funnel(FUNNEL),
        "funnel_high_confidence": funnel(FUNNEL_HIGH),
        "passing_strict": int(table["passes_strict"].sum()),
        "passing_high": int(table["passes_high"].sum()),
        "passing_strict_with_mark_in_event_quarter": int((table["passes_strict"] & table["mark_in_event_quarter"]).sum()),
        "passing_high_with_mark_in_event_quarter": int((table["passes_high"] & table["mark_in_event_quarter"]).sum()),
        "any_hurricane_deals": int(table["group"].isin(["exposed", "other_hurricane", "ambiguous"]).sum()),
        "storm_history": storm,
    }
    cols = ["deal_url", "group"] + FUNNEL[:3] + ["high_confidence", "cusips", "cusips_high", "pre_trade_days",
            "post_trade_days", "usable_prices", "pre_trade_days_high", "post_trade_days_high", "usable_prices_high",
            "storm_history", "marks_in_window", "mark_in_window", "mark_in_event_quarter", "passes_strict", "passes_high"]
    return table[cols].sort_values(["passes_high", "passes_strict", "deal_url"], ascending=[False, False, True]).reset_index(drop=True), summary


def build(pre_days: int = 45, post_days: int = 60, output_dir: Path = OUTPUT_DIR) -> dict:
    hazard_map = pd.read_csv(HAZARD_PATH)
    bridge = pd.read_csv(BRIDGE_PATH, dtype={"cusip_id": str})
    trades = pd.read_csv(TRADES_PATH, dtype={"cusip_id": str})
    market = pd.read_csv(MARKET_PATH, dtype={"contract_id": str})
    marks = pd.read_csv(MARKS_PATH, dtype={"cusip": str})
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "pre_days": pre_days, "post_days": post_days,
               "usable_price_rule": "a trade day with vwap and volume > 0 before the event and another after it, "
                                    "inside the window, program rows excluded (event_check.deal_changes)",
               "events": {}}
    for name, event in EVENTS.items():
        table, event_summary = gate_table(hazard_map, bridge, trades, market, marks, event["date"], pre_days, post_days)
        table.to_csv(output_dir / f"gate_{name}.csv", index=False)
        summary["events"][name] = {"date": event["date"], "label": event["label"], **event_summary}
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pre-days", type=int, default=45)
    parser.add_argument("--post-days", type=int, default=60)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = build(args.pre_days, args.post_days, args.output_dir)
    for name, ev in summary["events"].items():
        print(name, "strict:", ev["funnel_strict_any_confidence"])
        print(name, "high:  ", ev["funnel_high_confidence"])
    print("wrote", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
