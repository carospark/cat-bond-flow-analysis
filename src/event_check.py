"""End-to-end check of the joins around one hurricane.

This is a validation gate, not a result. It asks one question the whole
pipeline should be able to answer if the bridge, the trade cleaning, the
peril mapping, and the market join are all right: around a Florida landfall,
do the secondary prices of Florida-exposed cat bonds fall while bonds with no
hurricane exposure stay flat, and does hurricane-contract activity on the
prediction markets pick up at the same time?

Inputs, all local outputs of ``build_deal_panel.py``:

* ``data/deal_daily_trades.csv``: deal, CUSIP, day trade aggregates.
* ``data/deal_hazard_map.csv``: deal to hazard class and region pairs.
* ``data/market_class_daily.csv``: hazard class, region, day market activity.

Groups, by the deal's hazard map:

* ``exposed``: a ``hurricane_or_named_storm`` pair whose region is Florida or a
  U.S. region that contains it (``us``, ``southeast_us``, ``gulf_coast``),
  unless the peril text excludes Florida, in which case the deal is
  ``ambiguous`` and dropped.
* ``unexposed``: no ``hurricane_or_named_storm`` pair at all (earthquake,
  European windstorm, mortality, and so on).
* ``other_hurricane``: hurricane exposure somewhere else (Texas only, the
  Northeast only, Japan, Mexico); dropped from both groups.

For each deal with trades on both sides of the event the pre price is the
volume-weighted mean over the pre-window and the post price the same over the
post-window; the deal's change is post minus pre in price points. Weekly
series take, per group, the median across deals of that week's volume-weighted
price minus the deal's own pre-event mean, so deals at different price levels
are comparable.

Outputs go to ``data/event_checks/`` (gitignored): a per-deal table, the
weekly series, a summary JSON, and a two-panel chart.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TRADES_PATH = DATA / "deal_daily_trades.csv"
HAZARD_PATH = DATA / "deal_hazard_map.csv"
MARKET_PATH = DATA / "market_class_daily.csv"
OUTPUT_DIR = DATA / "event_checks"

HURRICANE = "hurricane_or_named_storm"
FLORIDA_REGIONS = {"florida", "us", "southeast_us", "gulf_coast"}
EXCLUDES_FLORIDA = r"(?:exclud\w*|ex-?|excl\.?|without)\s+(?:\w+\s+){0,3}florida|florida\s+(?:is\s+)?exclud"
MARKET_REGIONS = {"florida", "us"}
THIN_WEEK_DEALS = 3


def _compact(value, _position=None):
    if abs(value) >= 1e6:
        return "%.1fM" % (value / 1e6)
    if abs(value) >= 1e3:
        return "%.0fk" % (value / 1e3)
    return "%.0f" % value

EVENTS = {
    "ian": {"date": "2022-09-28", "label": "Hurricane Ian, Florida landfall 28 Sep 2022"},
    "milton": {"date": "2024-10-09", "label": "Hurricane Milton, Florida landfall 9 Oct 2024"},
}


def classify_deals(hazard_map: pd.DataFrame) -> pd.Series:
    """deal_url -> exposed | unexposed | ambiguous | other_hurricane."""
    out = {}
    for url, rows in hazard_map.groupby("deal_url"):
        hurricane = rows[rows.hazard_class.eq(HURRICANE)]
        if hurricane.empty:
            out[url] = "unexposed"
            continue
        florida = hurricane[hurricane.region.isin(FLORIDA_REGIONS)]
        if florida.empty:
            out[url] = "other_hurricane"
            continue
        text = " ".join(florida.perils_covered.fillna("").astype(str))
        if pd.Series([text]).str.contains(EXCLUDES_FLORIDA, case=False, regex=True).iloc[0]:
            out[url] = "ambiguous"
        else:
            out[url] = "exposed"
    return pd.Series(out, name="group")


def _vw_price(frame: pd.DataFrame) -> float:
    volume = frame["volume"].sum()
    if volume <= 0:
        return float("nan")
    return float((frame["vwap"] * frame["volume"]).sum() / volume)


def deal_changes(trades: pd.DataFrame, groups: pd.Series, event_date: str,
                 pre_days: int, post_days: int) -> pd.DataFrame:
    """One row per deal with trades on both sides of the event."""
    t0 = pd.Timestamp(event_date)
    frame = trades.copy()
    frame["date"] = pd.to_datetime(frame["trade_date"])
    frame = frame[(frame["date"] >= t0 - pd.Timedelta(days=pre_days))
                  & (frame["date"] <= t0 + pd.Timedelta(days=post_days))]
    frame = frame[frame["vwap"].notna() & frame["volume"].gt(0)]
    frame["group"] = frame["deal_url"].map(groups).fillna("unmapped")
    rows = []
    for url, deal in frame.groupby("deal_url"):
        pre = deal[deal["date"] < t0]
        post = deal[deal["date"] > t0]
        if pre.empty or post.empty:
            continue
        pre_price, post_price = _vw_price(pre), _vw_price(post)
        rows.append({
            "deal_url": url, "group": deal["group"].iloc[0],
            "pre_trade_days": int(len(pre)), "post_trade_days": int(len(post)),
            "pre_volume": float(pre["volume"].sum()), "post_volume": float(post["volume"].sum()),
            "pre_price": pre_price, "post_price": post_price,
            "change_points": post_price - pre_price,
            "post_low": float(post["low_price"].min()),
            "trough_points": float(post["low_price"].min()) - pre_price,
        })
    columns = ["deal_url", "group", "pre_trade_days", "post_trade_days", "pre_volume",
               "post_volume", "pre_price", "post_price", "change_points", "post_low",
               "trough_points"]
    return pd.DataFrame(rows, columns=columns)


def weekly_series(trades: pd.DataFrame, groups: pd.Series, changes: pd.DataFrame,
                  event_date: str, pre_days: int, post_days: int) -> pd.DataFrame:
    """Per group and week: median across deals of (weekly VW price - deal pre mean)."""
    t0 = pd.Timestamp(event_date)
    frame = trades.copy()
    frame["date"] = pd.to_datetime(frame["trade_date"])
    frame = frame[(frame["date"] >= t0 - pd.Timedelta(days=pre_days))
                  & (frame["date"] <= t0 + pd.Timedelta(days=post_days))]
    frame = frame[frame["vwap"].notna() & frame["volume"].gt(0)]
    frame = frame[frame["deal_url"].isin(changes["deal_url"])]
    frame["group"] = frame["deal_url"].map(groups)
    frame["week"] = ((frame["date"] - t0).dt.days // 7).astype(int)
    frame["pre_price"] = frame["deal_url"].map(changes.set_index("deal_url")["pre_price"])
    rows = []
    for (group, week), chunk in frame.groupby(["group", "week"]):
        per_deal = chunk.groupby("deal_url").apply(
            lambda d: _vw_price(d) - d["pre_price"].iloc[0], include_groups=False)
        rows.append({"group": group, "week": int(week), "deals": int(per_deal.size),
                     "median_change_points": float(per_deal.median()),
                     "volume": float(chunk["volume"].sum())})
    return pd.DataFrame(rows, columns=["group", "week", "deals", "median_change_points", "volume"])


def weekly_market(market: pd.DataFrame, event_date: str, pre_days: int, post_days: int) -> pd.DataFrame:
    t0 = pd.Timestamp(event_date)
    frame = market[market["hazard_class"].eq(HURRICANE) & market["region"].isin(MARKET_REGIONS)].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[(frame["date"] >= t0 - pd.Timedelta(days=pre_days))
                  & (frame["date"] <= t0 + pd.Timedelta(days=post_days))]
    frame["week"] = ((frame["date"] - t0).dt.days // 7).astype(int)
    out = frame.groupby("week").agg(
        contracts_traded=("contracts_traded", "sum"), n_trades=("n_trades", "sum"),
        traded_size=("traded_size", "sum")).reset_index()
    return out


def summarise(changes: pd.DataFrame) -> dict:
    out = {}
    for group, chunk in changes.groupby("group"):
        out[group] = {
            "deals": int(len(chunk)),
            "median_change_points": round(float(chunk["change_points"].median()), 3),
            "q25_change_points": round(float(chunk["change_points"].quantile(0.25)), 3),
            "q75_change_points": round(float(chunk["change_points"].quantile(0.75)), 3),
            "median_trough_points": round(float(chunk["trough_points"].median()), 3),
            "share_down_2_points": round(float(chunk["change_points"].lt(-2).mean()), 3),
        }
    return out


def plot(event: dict, weekly: pd.DataFrame, market_weekly: pd.DataFrame,
         summary: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    surface, ink, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
    series = {"exposed": ("#2a78d6", "Florida-exposed"), "unexposed": ("#eb6834", "No hurricane exposure")}
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(9, 7), sharex=True,
                                      gridspec_kw={"height_ratios": [3, 1.4], "hspace": 0.12})
    fig.patch.set_facecolor(surface)
    for ax in (top, bottom):
        ax.set_facecolor(surface)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(grid)
        ax.tick_params(colors=muted, labelsize=9)
        ax.yaxis.grid(True, color=grid, linewidth=1)
        ax.set_axisbelow(True)
        ax.axvline(0, color=muted, linewidth=1)
    ends = []
    for group, (colour, label) in series.items():
        chunk = weekly[weekly["group"].eq(group)].sort_values("week")
        if chunk.empty:
            continue
        top.plot(chunk["week"], chunk["median_change_points"], color=colour, linewidth=2,
                 solid_joinstyle="round", solid_capstyle="round", label=label)
        # A week with fewer than three deals is one or two prices, not a median:
        # hollow marker so the eye discounts it.
        solid = chunk[chunk["deals"].ge(THIN_WEEK_DEALS)]
        thin = chunk[chunk["deals"].lt(THIN_WEEK_DEALS)]
        top.scatter(solid["week"], solid["median_change_points"], s=64, color=colour,
                    edgecolors=surface, linewidths=2, zorder=3)
        top.scatter(thin["week"], thin["median_change_points"], s=64, facecolors=surface,
                    edgecolors=colour, linewidths=2, zorder=3)
        last = chunk.iloc[-1]
        ends.append([last["week"], last["median_change_points"],
                     "%s (%d deals)" % (label, summary.get(group, {}).get("deals", 0))])
    # Nudge end labels apart when they would overlap.
    span = max(abs(weekly["median_change_points"]).max(), 1.0)
    ends.sort(key=lambda e: e[1])
    for first, second in zip(ends, ends[1:]):
        gap = 0.06 * span
        if second[1] - first[1] < gap:
            first[1] -= (gap - (second[1] - first[1])) / 2
            second[1] += (gap - (second[1] - first[1]))
    for week, value, text in ends:
        top.annotate(text, (week, value), xytext=(6, 0), textcoords="offset points",
                     color=ink, fontsize=9, va="center")
    top.axhline(0, color=grid, linewidth=1)
    top.set_ylabel("Median price change vs pre-event mean, points", color=muted, fontsize=9)
    top.set_title(event["label"], loc="left", color=ink, fontsize=12, fontweight="bold", pad=26)
    top.legend(frameon=False, fontsize=9, loc="lower left", labelcolor=ink)
    top.annotate("Weekly volume-weighted price per deal, less that deal's mean over the pre-window; "
                 "median across deals with trades on both sides. Hollow: fewer than %d deals that week."
                 % THIN_WEEK_DEALS,
                 (0, 1.02), xycoords="axes fraction", color=muted, fontsize=8.5, va="bottom")
    bottom.bar(market_weekly["week"], market_weekly["traded_size"], width=0.7,
               color="#2a78d6", edgecolor=surface, linewidth=2)
    bottom.set_ylabel("Hurricane contract\ntraded size, weekly", color=muted, fontsize=9)
    bottom.set_xlabel("Weeks from landfall", color=muted, fontsize=9)
    bottom.yaxis.set_major_formatter(FuncFormatter(_compact))
    bottom.annotate("Kalshi and Polymarket contracts classed hurricane or named storm, Florida and U.S. regions.",
                    (0, 1.04), xycoords="axes fraction", color=muted, fontsize=8.5, va="bottom")
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=surface)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--event", choices=sorted(EVENTS), default="ian")
    parser.add_argument("--date", help="override the event date (YYYY-MM-DD)")
    parser.add_argument("--pre-days", type=int, default=45)
    parser.add_argument("--post-days", type=int, default=60)
    parser.add_argument("--include-program", action="store_true",
                        help="also use trades attributed at program level")
    parser.add_argument("--trades", type=Path, default=TRADES_PATH)
    parser.add_argument("--hazards", type=Path, default=HAZARD_PATH)
    parser.add_argument("--market", type=Path, default=MARKET_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    event = dict(EVENTS[args.event])
    if args.date:
        event["date"] = args.date
    args.output_dir.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(args.trades, dtype={"cusip_id": str})
    if not args.include_program:
        trades = trades[trades["match_confidence"].ne("program")]
    hazard_map = pd.read_csv(args.hazards)
    market = pd.read_csv(args.market)

    groups = classify_deals(hazard_map)
    changes = deal_changes(trades, groups, event["date"], args.pre_days, args.post_days)
    kept = changes[changes["group"].isin(["exposed", "unexposed"])]
    weekly = weekly_series(trades, groups, kept, event["date"], args.pre_days, args.post_days)
    market_weekly = weekly_market(market, event["date"], args.pre_days, args.post_days)
    summary = {
        "event": event, "pre_days": args.pre_days, "post_days": args.post_days,
        "include_program": args.include_program,
        "deals_by_group_all": groups.value_counts().to_dict(),
        "deals_with_trades_both_sides_by_group": changes["group"].value_counts().to_dict(),
        "groups": summarise(changes),
        "market_weeks": int(len(market_weekly)),
        "market_traded_size_pre": float(market_weekly.loc[market_weekly["week"].lt(0), "traded_size"].sum()),
        "market_traded_size_post": float(market_weekly.loc[market_weekly["week"].ge(0), "traded_size"].sum()),
    }
    stem = args.output_dir / args.event
    changes.sort_values(["group", "change_points"]).to_csv(stem.with_name(stem.name + "_deals.csv"), index=False)
    weekly.to_csv(stem.with_name(stem.name + "_weekly.csv"), index=False)
    market_weekly.to_csv(stem.with_name(stem.name + "_market_weekly.csv"), index=False)
    stem.with_name(stem.name + "_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    plot(event, weekly, market_weekly, summary["groups"], stem.with_suffix(".png"))
    print(json.dumps(summary, indent=2))
    print("wrote", stem.with_suffix(".png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
