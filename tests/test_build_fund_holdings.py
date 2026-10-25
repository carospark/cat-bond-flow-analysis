"""Offline tests for the fund-holdings join, deal aggregation, size parsing, and mark comparison."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_fund_holdings import (  # noqa: E402
    attribute_holdings,
    compare_marks_by_deal,
    compare_marks_to_trace,
    deal_quarterly,
    deal_size_table,
    parse_size,
)


def _holdings():
    return pd.DataFrame([
        # Two funds hold the same bridged bond at slightly different marks.
        {"fund_id": "f1", "period_end": "2026-06-30", "filing_date": "2026-08-29", "accession": "a1", "cusip": "AAA1",
         "name": "Alpha Re", "title": "Alpha Re 2025-1 A", "balance": 1_000_000.0, "units": "PA", "asset_category": "DBT",
         "value_usd": 1_020_000.0, "pct_net_assets": 1.0, "currency": "USD", "maturity_date": "2028-06-07",
         "coupon_kind": "Floating", "annualized_rate": 9.0, "is_default": "N", "fair_value_level": "2"},
        {"fund_id": "f2", "period_end": "2026-06-30", "filing_date": "2026-08-29", "accession": "a2", "cusip": "aaa1",
         "name": "Alpha Re", "title": "Alpha Re 2025-1 A", "balance": 3_000_000.0, "units": "PA", "asset_category": "DBT",
         "value_usd": 3_000_000.0, "pct_net_assets": 3.0, "currency": "USD", "maturity_date": "2028-06-07",
         "coupon_kind": "Floating", "annualized_rate": 9.0, "is_default": "N", "fair_value_level": "2"},
        # Unbridged bond.
        {"fund_id": "f1", "period_end": "2026-06-30", "filing_date": "2026-08-29", "accession": "a1", "cusip": "ZZZ9",
         "name": "Omega Re", "title": "Omega Re B", "balance": 500_000.0, "units": "PA", "asset_category": "DBT",
         "value_usd": 450_000.0, "pct_net_assets": 0.5, "currency": "USD", "maturity_date": None,
         "coupon_kind": None, "annualized_rate": None, "is_default": "N", "fair_value_level": "3"},
        # Fund units: no par, no mark.
        {"fund_id": "f1", "period_end": "2026-06-30", "filing_date": "2026-08-29", "accession": "a1", "cusip": "FFF1",
         "name": "Money Fund", "title": None, "balance": 10_000.0, "units": "NS", "asset_category": "STIV",
         "value_usd": 10_000.0, "pct_net_assets": 0.01, "currency": "USD", "maturity_date": None,
         "coupon_kind": None, "annualized_rate": None, "is_default": None, "fair_value_level": "1"},
        # A filing with a units error: value per par of 5,000 is not a price.
        {"fund_id": "f2", "period_end": "2026-06-30", "filing_date": "2026-08-29", "accession": "a2", "cusip": "BBB2",
         "name": "Beta Re", "title": "Beta Re A", "balance": 100.0, "units": "PA", "asset_category": "DBT",
         "value_usd": 5_000.0, "pct_net_assets": 0.0, "currency": "USD", "maturity_date": None,
         "coupon_kind": None, "annualized_rate": None, "is_default": "N", "fair_value_level": "2"},
        # All-zero placeholder CUSIP: dropped, not a bridge gap.
        {"fund_id": "f1", "period_end": "2026-06-30", "filing_date": "2026-08-29", "accession": "a1", "cusip": "000000000",
         "name": "Rondout (Artex Segregated Account Company)", "title": None, "balance": 1.0, "units": "NS", "asset_category": "EP",
         "value_usd": 4_000_000_000.0, "pct_net_assets": 40.0, "currency": "USD", "maturity_date": None,
         "coupon_kind": None, "annualized_rate": None, "is_default": None, "fair_value_level": "3"},
        # No CUSIP: dropped.
        {"fund_id": "f1", "period_end": "2026-06-30", "filing_date": "2026-08-29", "accession": "a1", "cusip": None,
         "name": "Artex SAC", "title": None, "balance": 1.0, "units": "NS", "asset_category": "EP",
         "value_usd": 99.0, "pct_net_assets": 0.0, "currency": "USD", "maturity_date": None,
         "coupon_kind": None, "annualized_rate": None, "is_default": None, "fair_value_level": "3"},
    ])


def _bridge():
    return pd.DataFrame([
        {"cusip_id": "AAA1", "deal_url": "https://x/alpha-re-2025-1/", "match_confidence": "high"},
        {"cusip_id": "BBB2", "deal_url": "https://x/beta-re/", "match_confidence": "program"},
    ])


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.out = attribute_holdings(_holdings(), _bridge())

    def test_drops_rows_without_cusip_and_normalizes_case(self):
        self.assertEqual(len(self.out), 5)
        self.assertEqual(set(self.out["cusip"]), {"AAA1", "ZZZ9", "FFF1", "BBB2"})
        self.assertNotIn("000000000", set(self.out["cusip"]))
        self.assertEqual(set(self.out["period_month"]), {"2026-06"})

    def test_joins_deals_and_keeps_confidence(self):
        alpha = self.out[self.out["cusip"] == "AAA1"]
        self.assertEqual(set(alpha["deal_url"]), {"https://x/alpha-re-2025-1/"})
        self.assertEqual(set(alpha["match_confidence"]), {"high"})
        self.assertTrue(self.out[self.out["cusip"] == "ZZZ9"]["deal_url"].isna().all())

    def test_marks_only_for_par_debt_and_sane_values(self):
        marks = self.out.set_index(["fund_id", "cusip"])["mark_price"]
        self.assertAlmostEqual(marks[("f1", "AAA1")], 102.0)
        self.assertAlmostEqual(marks[("f2", "AAA1")], 100.0)
        self.assertAlmostEqual(marks[("f1", "ZZZ9")], 90.0)
        self.assertTrue(pd.isna(marks[("f1", "FFF1")]))
        self.assertTrue(pd.isna(marks[("f2", "BBB2")]))
        self.assertTrue(pd.isna(self.out.set_index(["fund_id", "cusip"])["par"][("f1", "FFF1")]))
        self.assertEqual(self.out.set_index(["fund_id", "cusip"])["mark_basis"][("f1", "AAA1")], "usd")

    def test_non_usd_par_is_converted_before_the_mark(self):
        rows = _holdings().iloc[:1].copy()
        rows["currency"] = "EUR"
        rows["balance"] = 1_000_000.0          # EUR par
        rows["value_usd"] = 1_080_000.0        # worth par at 1.08 USD per EUR
        fx = {("EUR", "2026-06"): 1.08}
        out = attribute_holdings(rows, _bridge(), fx).iloc[0]
        self.assertEqual(out["par_currency"], "EUR")
        self.assertAlmostEqual(out["par_usd"], 1_080_000.0)
        self.assertAlmostEqual(out["mark_price"], 100.0)
        self.assertEqual(out["mark_basis"], "fx_converted")
        # Without a rate the mark is null, not value over local par.
        out = attribute_holdings(rows, _bridge(), {}).iloc[0]
        self.assertTrue(pd.isna(out["mark_price"]))
        self.assertTrue(pd.isna(out["par_usd"]))
        self.assertEqual(out["mark_basis"], "fx_rate_missing")
        # A blank currency is taken as USD and says so.
        rows["currency"] = None
        rows["value_usd"] = 1_000_000.0
        out = attribute_holdings(rows, _bridge(), {}).iloc[0]
        self.assertAlmostEqual(out["mark_price"], 100.0)
        self.assertEqual(out["mark_basis"], "currency_missing_assumed_usd")


class QuarterlyTests(unittest.TestCase):
    def test_aggregates_per_deal_with_par_weighted_mark_and_share_of_size(self):
        attributed = attribute_holdings(_holdings(), _bridge())
        sizes = pd.DataFrame({"deal_url": ["https://x/alpha-re-2025-1/"], "size_value": [10e6], "size_currency": ["USD"]})
        q = deal_quarterly(attributed, sizes).set_index("deal_url")
        alpha = q.loc["https://x/alpha-re-2025-1/"]
        self.assertEqual(alpha["n_funds"], 2)
        self.assertEqual(alpha["par_held"], 4_000_000.0)
        self.assertAlmostEqual(alpha["mark_par_weighted"], (1e6 * 102 + 3e6 * 100) / 4e6)
        self.assertAlmostEqual(alpha["share_of_size"], 0.4)
        self.assertEqual(alpha["funds"], "f1;f2")
        beta = q.loc["https://x/beta-re/"]
        self.assertTrue(pd.isna(beta["mark_par_weighted"]))
        self.assertTrue(pd.isna(beta["share_of_size"]))


class SizeTests(unittest.TestCase):
    def test_parse_size(self):
        self.assertEqual(parse_size("$362m"), (362e6, "USD"))
        self.assertEqual(parse_size("$1.1bn"), (1.1e9, "USD"))
        self.assertEqual(parse_size("€200m"), (200e6, "EUR"))
        self.assertEqual(parse_size("A$150m"), (150e6, "AUD"))
        self.assertEqual(parse_size("Undisclosed"), (None, None))
        self.assertEqual(parse_size(None), (None, None))

    def test_deal_size_table_drops_unparseable(self):
        deals = pd.DataFrame({"deal_url": ["a", "b", "a"], "size": ["$100m", "n/a", "$100m"]})
        table = deal_size_table(deals)
        self.assertEqual(table["deal_url"].tolist(), ["a"])
        self.assertEqual(table["size_value"].iloc[0], 100e6)


class MarkComparisonTests(unittest.TestCase):
    def test_compares_par_weighted_mark_to_windowed_vwap(self):
        attributed = attribute_holdings(_holdings(), _bridge())
        trades = pd.DataFrame([
            {"cusip_id": "AAA1", "trade_date": "2026-06-25", "n_trades": 2, "volume": 1_000_000.0, "vwap": 101.0},
            {"cusip_id": "AAA1", "trade_date": "2026-07-10", "n_trades": 1, "volume": 3_000_000.0, "vwap": 99.0},
            {"cusip_id": "AAA1", "trade_date": "2026-09-01", "n_trades": 1, "volume": 9_000_000.0, "vwap": 50.0},
            {"cusip_id": "ZZZ9", "trade_date": "2026-06-30", "n_trades": 1, "volume": 100_000.0, "vwap": 91.0},
        ])
        comparison, stats = compare_marks_to_trace(attributed, trades, window_days=15)
        self.assertEqual(stats["pairs"], 2)
        alpha = comparison[comparison["cusip"] == "AAA1"].iloc[0]
        self.assertAlmostEqual(alpha["fund_mark"], 100.5)
        self.assertAlmostEqual(alpha["trace_vwap"], (101 * 1e6 + 99 * 3e6) / 4e6)
        self.assertEqual(alpha["trace_trades"], 3)
        # The window is split at the quarter end: before holds the June trade,
        # after the July trade; the September trade is outside both.
        self.assertAlmostEqual(alpha["trace_vwap_before"], 101.0)
        self.assertAlmostEqual(alpha["trace_vwap_after"], 99.0)
        self.assertEqual((alpha["trace_trades_before"], alpha["trace_trades_after"]), (2, 1))
        self.assertAlmostEqual(alpha["diff_points_before"], -0.5)
        self.assertAlmostEqual(alpha["diff_points_after"], 1.5)
        self.assertEqual(alpha["days_to_nearest_trade"], 5)
        self.assertFalse(alpha["stale"])
        omega = comparison[comparison["cusip"] == "ZZZ9"].iloc[0]
        self.assertAlmostEqual(omega["fund_mark"] - omega["trace_vwap"], -1.0)
        self.assertTrue(pd.isna(omega["trace_vwap_after"]))
        self.assertEqual(stats["share_within_2_points"], 1.0)
        self.assertEqual(stats["windows"]["both"]["pairs"], 2)
        self.assertEqual(stats["windows"]["after_quarter_end"]["pairs"], 1)
        self.assertEqual(stats["windows"]["pairs_with_trades_both_sides"], 1)
        self.assertEqual(stats["windows"]["both"]["pairs_over_5_points"], 0)
        self.assertEqual(stats["stale"]["pairs"], 0)

    def test_stale_pairs_and_tails_are_reported(self):
        attributed = attribute_holdings(_holdings(), _bridge())
        trades = pd.DataFrame([
            # Only trade is 12 days after the quarter end, 30 points away.
            {"cusip_id": "AAA1", "trade_date": "2026-07-12", "n_trades": 1, "volume": 1_000_000.0, "vwap": 70.5},
            {"cusip_id": "ZZZ9", "trade_date": "2026-06-29", "n_trades": 1, "volume": 100_000.0, "vwap": 90.0},
        ])
        comparison, stats = compare_marks_to_trace(attributed, trades, window_days=15, stale_days=7)
        alpha = comparison[comparison["cusip"] == "AAA1"].iloc[0]
        self.assertTrue(alpha["stale"])
        self.assertEqual(alpha["days_to_nearest_trade"], 12)
        self.assertEqual(stats["stale"]["pairs"], 1)
        self.assertEqual(stats["stale"]["share_of_pairs"], 0.5)
        self.assertEqual(stats["stale"]["median_abs_diff_stale"], 30.0)
        self.assertEqual(stats["stale"]["median_abs_diff_fresh"], 0.0)
        self.assertEqual(stats["windows"]["both"]["pairs_over_20_points"], 1)
        self.assertEqual(stats["windows"]["both"]["max_abs_points"], 30.0)
        self.assertEqual(stats["windows"]["before_quarter_end"]["pairs"], 1)

    def test_deal_keyed_comparison_flags_a_cusip_that_disagrees_with_its_deal(self):
        holdings = _holdings().iloc[:2].copy()
        extra = holdings.iloc[:1].copy()
        extra["cusip"] = "AAA2"; extra["title"] = "Alpha Re 2025-1 B"; extra["balance"] = 2_000_000.0
        extra["value_usd"] = 1_200_000.0                        # marked 60 while the deal's other tranche is ~100.5
        same_deal_quiet = holdings.iloc[:1].copy()
        same_deal_quiet["cusip"] = "AAA3"; same_deal_quiet["balance"] = 1_000_000.0; same_deal_quiet["value_usd"] = 1_005_000.0
        bridge = pd.DataFrame([
            {"cusip_id": "AAA1", "deal_url": "https://x/alpha-re-2025-1/", "match_confidence": "high"},
            {"cusip_id": "AAA2", "deal_url": "https://x/alpha-re-2025-1/", "match_confidence": "medium"},
            {"cusip_id": "AAA3", "deal_url": "https://x/alpha-re-2025-1/", "match_confidence": "high"},
        ])
        title_evidence = pd.DataFrame({"cusip_id": ["AAA1", "AAA2", "AAA3"], "title_evidence": ["agrees", "none", "agrees"]})
        attributed = attribute_holdings(pd.concat([holdings, extra, same_deal_quiet]), bridge)
        table, stats = compare_marks_by_deal(attributed, title_evidence, gap_points=10)
        self.assertEqual(stats["deal_quarters_with_two_or_more_cusips"], 1)
        # Every tranche is far from a reference that the bad one contaminates;
        # only the farthest in the deal-quarter is the candidate.
        self.assertEqual(stats["rows_over_threshold"], 3)
        self.assertEqual(stats["cusip_quarters_over_threshold"], 1)
        self.assertEqual(table["is_deal_outlier"].tolist(), [True, False, False])
        top = table.iloc[0]
        self.assertEqual(top["cusip"], "AAA2")
        self.assertEqual(top["title_evidence"], "none")
        self.assertEqual(top["match_confidence"], "medium")
        self.assertAlmostEqual(top["cusip_mark"], 60.0)
        # The others' mark is the par-weighted mark of AAA1 (4m par at 100.5) and AAA3 (1m at 100.5).
        self.assertAlmostEqual(top["others_mark"], 100.5)
        self.assertAlmostEqual(top["gap_points"], -40.5)
        self.assertEqual(stats["flagged_by_title_evidence"], {"none": 1})
        self.assertEqual(stats["top_disagreements"][0]["cusip"], "AAA2")
        # A deal with one marked CUSIP has nothing to compare against.
        single, single_stats = compare_marks_by_deal(attribute_holdings(_holdings(), _bridge()), None)
        self.assertTrue(single.empty)
        self.assertEqual(single_stats["rows"], 0)

    def test_no_overlap_gives_empty_comparison(self):
        attributed = attribute_holdings(_holdings(), _bridge())
        trades = pd.DataFrame({"cusip_id": ["QQQ1"], "trade_date": ["2026-06-30"], "n_trades": [1], "volume": [1.0], "vwap": [100.0]})
        comparison, stats = compare_marks_to_trace(attributed, trades)
        self.assertTrue(comparison.empty)
        self.assertEqual(stats["pairs"], 0)


if __name__ == "__main__":
    unittest.main()
