"""Build the deal-level event panel.

Joins three local, gitignored inputs:

* ``data/trace_trades_clean.csv`` from ``clean_trace_trades.py``: one row per
  cleaned TRACE 144A trade.
* ``data/bridge.csv`` from ``build_bridge.py``: CUSIP to deal pairs.
* ``data/bridge_program.csv`` from ``extend_bridge.py``, optional: only its
  ``program_nearest`` rows carry a deal, and they join with confidence
  ``program`` so they can be filtered out of any test that needs identity.
* The parsed deal directory (``deals.csv`` from the companion parser), for
  each deal's covered perils. Pass its path with ``--deals``; it is optional,
  and the peril attachment is skipped when it is absent.

plus the prediction-market history database for the hazard series.

Outputs, all under ``data/`` and gitignored:

* ``deal_daily_trades.csv``: one row per deal, CUSIP, and execution date with
  trade count, volume, volume-weighted price, last price, high and low, and
  the dealer-sell (customer buys) and dealer-buy (customer sells) volumes.
* ``deal_hazard_map.csv``: one row per deal and hazard class it maps to, with
  the region tags derived from the peril text. Only when ``--deals`` is given.
* ``market_contract_daily.csv``: one row per contract and date with the last
  price of the day and traded size, from the prediction-market database.
* ``market_class_daily.csv``: one row per hazard class, region, and date with
  the number of contracts priced that day and total traded size. This is an
  activity index, not a probability: contracts on different questions are not
  averaged.
* ``deal_panel.csv``: the deal-day trade rows with, for each hazard class the
  deal maps to, that day's class-and-region activity in ``market_*`` columns.
  Only when the hazard map exists.

Dealer side is TRACE's reporting-side convention: ``S`` means the dealer sold,
so the customer bought.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pull_market_signals import classify_regions, hazard_classes  # noqa: E402

DATA = ROOT / "data"
TRADES_PATH = DATA / "trace_trades_clean.csv"
BRIDGE_PATH = DATA / "bridge.csv"
PROGRAM_BRIDGE_PATH = DATA / "bridge_program.csv"
ATTRIBUTION_COLUMNS = ["cusip_id", "deal_url", "match_confidence"]
DEALS_PATH = DATA / "deals.csv"
DB_PATH = DATA / "raw" / "tier1" / "prediction_market_history.sqlite3"

# Peril text in the deal directory is free text. Each entry maps a phrase to a
# hazard class; the region comes from the same text via classify_regions, with
# a default when the phrase names no place.
PERIL_LEXICON = [
    (re.compile(r"typhoon|australia\w* (?:tropical )?cyclone|australian cyclone", re.I),
     "typhoon_or_cyclone", None),
    (re.compile(r"hurricane|named storm|tropical cyclone|tropical storm|wind(?:storm)?(?! ?farm)", re.I),
     "hurricane_or_named_storm", "us"),
    (re.compile(r"european windstorm|europe\w* wind", re.I), "windstorm", "europe"),
    (re.compile(r"earthquake|seismic|quake", re.I), "earthquake", "us"),
    (re.compile(r"severe (?:thunder)?storm|severe convective|severe weather|hail|tornado", re.I),
     "severe_convective_storm", "us"),
    (re.compile(r"wildfire|bushfire|fire following|brush ?fire", re.I), "wildfire", "us"),
    (re.compile(r"winter storm|winter weather|freeze|ice storm", re.I), "winter_storm", "us"),
    (re.compile(r"flood", re.I), "precipitation", "us"),
    (re.compile(r"volcan", re.I), "volcanic_eruption", None),
    (re.compile(r"mortality|pandemic|longevity", re.I), "pandemic_or_mortality", None),
]

# "European windstorm" contains "wind", which the hurricane rule would catch.
# Classes whose text is claimed by an earlier, more specific rule are skipped.
EXCLUSIVE = {"hurricane_or_named_storm": ("windstorm",)}


def map_perils(text: str) -> list[tuple[str, str]]:
    """Return (hazard_class, region) pairs for one deal's peril text."""
    if not isinstance(text, str) or not text.strip():
        return []
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for clause in re.split(r"[;,/]|\band\b|\bplus\b|\(|\)", text):
        clause = clause.strip()
        if not clause:
            continue
        regions = classify_regions(clause)
        matched = []
        for pattern, hazard, default in PERIL_LEXICON:
            if pattern.search(clause):
                matched.append((hazard, default))
        names = {hazard for hazard, _ in matched}
        for hazard, default in matched:
            if any(other in names for other in EXCLUSIVE.get(hazard, ())):
                continue
            region_set = regions or ({default} if default else {"global"})
            # A US sub-region implies US; keep the specific one for the join.
            region_set = region_set - {"us"} if region_set - {"us"} else region_set
            for region in sorted(region_set):
                if (hazard, region) not in seen:
                    seen.add((hazard, region))
                    pairs.append((hazard, region))
    return pairs


def combine_bridges(bridge: pd.DataFrame, program: pd.DataFrame | None) -> pd.DataFrame:
    """Strict bridge pairs plus the program-level pairs that name one deal.

    The strict bridge wins for any CUSIP present in both. Program rows without
    a single deal (tied, program-only, absent) attribute nothing here.
    """
    strict = bridge[ATTRIBUTION_COLUMNS].copy()
    combined = strict.reset_index(drop=True)
    if program is not None and not program.empty:
        nearest = program[program["level"].eq("program_nearest")
                          & program["deal_url"].fillna("").astype(str).str.strip().ne("")
                          & ~program["cusip_id"].isin(strict["cusip_id"])]
        nearest = nearest[["cusip_id", "deal_url"]].assign(match_confidence="program")
        combined = pd.concat([strict, nearest], ignore_index=True)
    if not combined["cusip_id"].is_unique:
        duplicates = combined[combined["cusip_id"].duplicated()]["cusip_id"].tolist()
        raise ValueError("a CUSIP may attribute to only one deal: %s" % duplicates[:5])
    return combined


def build_hazard_map(deals: pd.DataFrame, bridge: pd.DataFrame) -> pd.DataFrame:
    deals = deals[deals["deal_url"].isin(bridge["deal_url"])]
    rows = []
    for _, deal in deals.iterrows():
        for hazard, region in map_perils(deal.get("perils_covered")):
            rows.append({
                "deal_url": deal["deal_url"], "hazard_class": hazard, "region": region,
                "perils_covered": deal.get("perils_covered"),
            })
    return pd.DataFrame(rows, columns=["deal_url", "hazard_class", "region", "perils_covered"])


def aggregate_trades(trades: pd.DataFrame, bridge: pd.DataFrame) -> pd.DataFrame:
    keyed = trades.merge(bridge[ATTRIBUTION_COLUMNS], on="cusip_id", how="inner")
    keyed["notional"] = keyed["price"] * keyed["volume"]
    keyed["dealer_sell_volume"] = keyed["volume"].where(keyed["dealer_side"] == "S", 0.0)
    keyed["dealer_buy_volume"] = keyed["volume"].where(keyed["dealer_side"] == "B", 0.0)
    keyed = keyed.sort_values(["deal_url", "cusip_id", "trade_date", "trade_time"])
    grouped = keyed.groupby(["deal_url", "cusip_id", "trade_date"], sort=True)
    panel = grouped.agg(
        n_trades=("price", "size"),
        volume=("volume", "sum"),
        notional=("notional", "sum"),
        last_price=("price", "last"),
        high_price=("price", "max"),
        low_price=("price", "min"),
        dealer_sell_volume=("dealer_sell_volume", "sum"),
        dealer_buy_volume=("dealer_buy_volume", "sum"),
        capped_volume_rows=("volume_capped", "sum"),
        match_confidence=("match_confidence", "first"),
    ).reset_index()
    panel["vwap"] = (panel["notional"] / panel["volume"]).where(panel["volume"] > 0)
    return panel.drop(columns=["notional"])


def load_market_daily(db_path: Path) -> pd.DataFrame:
    connection = sqlite3.connect(db_path)
    contracts = pd.read_sql_query(
        "SELECT platform, contract_id, classification, title, closed_at FROM contracts "
        "WHERE classification NOT LIKE '%city_temperature%'", connection)
    prices = pd.read_sql_query(
        "SELECT platform, contract_id, outcome_id, timestamp, price FROM price_points", connection)
    trades = pd.read_sql_query(
        "SELECT platform, contract_id, timestamp, size FROM trades", connection)
    connection.close()
    prices = prices.merge(contracts[["platform", "contract_id"]], on=["platform", "contract_id"])
    prices["price"] = pd.to_numeric(prices["price"], errors="coerce")
    prices["date"] = pd.to_datetime(prices["timestamp"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    prices = prices.sort_values(["platform", "contract_id", "outcome_id", "timestamp"])
    # The first outcome is "yes" on Kalshi and the first listed token on
    # Polymarket; keep one series per contract.
    first_outcome = prices.groupby(["platform", "contract_id"])["outcome_id"].transform("min")
    prices = prices[prices["outcome_id"] == first_outcome]
    daily_price = prices.groupby(["platform", "contract_id", "date"]).agg(
        last_price=("price", "last"), n_price_points=("price", "size")).reset_index()

    trades = trades.merge(contracts[["platform", "contract_id"]], on=["platform", "contract_id"])
    stamp = pd.to_datetime(trades["timestamp"], utc=True, errors="coerce", format="mixed")
    numeric = pd.to_numeric(trades["timestamp"], errors="coerce")
    stamp = stamp.fillna(pd.to_datetime(numeric, unit="s", utc=True, errors="coerce"))
    trades["date"] = stamp.dt.strftime("%Y-%m-%d")
    trades["size"] = pd.to_numeric(trades["size"], errors="coerce").fillna(0.0)
    daily_trades = trades.groupby(["platform", "contract_id", "date"]).agg(
        n_trades=("size", "size"), traded_size=("size", "sum")).reset_index()

    daily = daily_price.merge(daily_trades, on=["platform", "contract_id", "date"], how="outer")
    daily = daily.merge(contracts[["platform", "contract_id", "classification", "title"]],
                        on=["platform", "contract_id"], how="left")
    daily["hazard_classes"] = daily["classification"].map(lambda c: ";".join(hazard_classes(c)))
    daily["regions"] = daily["classification"].map(
        lambda c: ";".join(sorted(t.split(":", 1)[1] for t in str(c).split(";") if t.startswith("region:"))))
    return daily.sort_values(["platform", "contract_id", "date"]).reset_index(drop=True)


def aggregate_market_classes(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for record in daily.itertuples(index=False):
        classes = [c for c in str(record.hazard_classes).split(";") if c]
        regions = [r for r in str(record.regions).split(";") if r] or ["none"]
        for hazard in classes:
            for region in regions:
                rows.append((hazard, region, record.date, record.platform, record.contract_id,
                             record.last_price, record.n_trades, record.traded_size))
    frame = pd.DataFrame(rows, columns=["hazard_class", "region", "date", "platform", "contract_id",
                                        "last_price", "n_trades", "traded_size"])
    grouped = frame.groupby(["hazard_class", "region", "date"]).agg(
        contracts_priced=("last_price", lambda s: int(s.notna().sum())),
        contracts_traded=("n_trades", lambda s: int((s.fillna(0) > 0).sum())),
        n_trades=("n_trades", "sum"),
        traded_size=("traded_size", "sum"),
    ).reset_index()
    return grouped


def attach_hazards(deal_daily: pd.DataFrame, hazard_map: pd.DataFrame,
                   class_daily: pd.DataFrame) -> pd.DataFrame:
    joined = deal_daily.merge(hazard_map[["deal_url", "hazard_class", "region"]], on="deal_url", how="left")
    market = class_daily.rename(columns={
        "date": "trade_date", "contracts_priced": "market_contracts_priced",
        "contracts_traded": "market_contracts_traded", "n_trades": "market_n_trades",
        "traded_size": "market_traded_size",
    })
    joined = joined.merge(market, on=["hazard_class", "region", "trade_date"], how="left")
    for column in ("market_contracts_priced", "market_contracts_traded",
                   "market_n_trades", "market_traded_size"):
        joined[column] = joined[column].fillna(0)
    return joined


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--trades", type=Path, default=TRADES_PATH)
    parser.add_argument("--bridge", type=Path, default=BRIDGE_PATH)
    parser.add_argument("--program-bridge", type=Path, default=PROGRAM_BRIDGE_PATH,
                        help="program-level attribution table (optional); only its "
                             "program_nearest rows are used, with confidence 'program'")
    parser.add_argument("--deals", type=Path, default=DEALS_PATH,
                        help="parsed deal directory with a perils_covered column (optional)")
    parser.add_argument("--database", type=Path, default=DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DATA)
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {}

    trades = pd.read_csv(args.trades, dtype={"cusip_id": str, "msg_seq_nb": str})
    strict = pd.read_csv(args.bridge, dtype={"cusip_id": str})
    program = None
    if args.program_bridge.exists():
        program = pd.read_csv(args.program_bridge, dtype={"cusip_id": str})
    bridge = combine_bridges(strict, program)
    deal_daily = aggregate_trades(trades, bridge)
    deal_daily.to_csv(out / "deal_daily_trades.csv", index=False)
    by_confidence = deal_daily.groupby("match_confidence")["n_trades"].sum()
    summary["deal_daily_trades"] = {
        "rows": int(len(deal_daily)), "deals": int(deal_daily["deal_url"].nunique()),
        "cusips": int(deal_daily["cusip_id"].nunique()),
        "trades_matched_to_deals": int(deal_daily["n_trades"].sum()),
        "trades_by_match_confidence": {k: int(v) for k, v in by_confidence.items()},
        "program_bridge": (str(args.program_bridge) if program is not None
                           else "skipped: %s not found" % args.program_bridge),
        "trades_unmatched": int(len(trades) - deal_daily["n_trades"].sum()),
        "first_date": str(deal_daily["trade_date"].min()), "last_date": str(deal_daily["trade_date"].max()),
    }

    market_daily = load_market_daily(args.database)
    market_daily.to_csv(out / "market_contract_daily.csv", index=False)
    class_daily = aggregate_market_classes(market_daily)
    class_daily.to_csv(out / "market_class_daily.csv", index=False)
    summary["market"] = {
        "contract_days": int(len(market_daily)), "contracts": int(market_daily["contract_id"].nunique()),
        "class_region_days": int(len(class_daily)),
        "first_date": str(market_daily["date"].min()), "last_date": str(market_daily["date"].max()),
    }

    if args.deals.exists():
        deals = pd.read_csv(args.deals, low_memory=False)
        hazard_map = build_hazard_map(deals, bridge)
        hazard_map.to_csv(out / "deal_hazard_map.csv", index=False)
        panel = attach_hazards(deal_daily, hazard_map, class_daily)
        panel.to_csv(out / "deal_panel.csv", index=False)
        summary["deal_hazard_map"] = {
            "bridged_deals": int(bridge["deal_url"].nunique()),
            "strict_bridge_deals": int(strict["deal_url"].nunique()),
            "deals_with_hazard": int(hazard_map["deal_url"].nunique()),
            "pairs_by_class": hazard_map["hazard_class"].value_counts().to_dict(),
            "pairs_by_region": hazard_map["region"].value_counts().to_dict(),
        }
        summary["deal_panel"] = {
            "rows": int(len(panel)),
            "rows_with_market_activity": int((panel["market_contracts_priced"] > 0).sum()),
        }
    else:
        summary["deal_hazard_map"] = f"skipped: {args.deals} not found; pass --deals"
    (out / "deal_panel_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
