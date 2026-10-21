"""Offline tests for the fund-holdings join, deal aggregation, size parsing, and mark comparison."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_fund_holdings import (  # noqa: E402
    attribute_holdings,
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
        omega = comparison[comparison["cusip"] == "ZZZ9"].iloc[0]
        self.assertAlmostEqual(omega["fund_mark"] - omega["trace_vwap"], -1.0)
        self.assertEqual(stats["share_within_2_points"], 1.0)

    def test_no_overlap_gives_empty_comparison(self):
        attributed = attribute_holdings(_holdings(), _bridge())
        trades = pd.DataFrame({"cusip_id": ["QQQ1"], "trade_date": ["2026-06-30"], "n_trades": [1], "volume": [1.0], "vwap": [100.0]})
        comparison, stats = compare_marks_to_trace(attributed, trades)
        self.assertTrue(comparison.empty)
        self.assertEqual(stats["pairs"], 0)


if __name__ == "__main__":
    unittest.main()
