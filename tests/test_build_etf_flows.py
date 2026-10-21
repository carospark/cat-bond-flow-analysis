"""Offline tests for the Brookmont ETF snapshot compiler and its N-PORT reconciliation."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_etf_flows import build_series, load_snapshots, parse_snapshot, reconcile_with_nport  # noqa: E402


def _snapshot(as_of, shares, net_assets, nav, premium):
    return {
        "holdings_as_of": as_of,
        "fund_details": [
            ["Fund Detail", "Value", "Fund Detail", "Value"],
            ["Fund Listing Exchange", "Texas Stock Exchange LLC", "Fund Inception Date", "04/01/2025"],
            ["Ticker", "ILS", "Expense Ratio", "2.65%"],
            ["CUSIP", "26923N470", "Shares Outstanding", shares],
            ["Net Assets", net_assets, "Median 30-day Bid/Ask Spread", "0.0989%"],
        ],
        "current_nav_metrics": [["Metric", "Value"], ["NAV", nav], ["Daily Change ($)", "$0.00"], ["Premium / Discount (%)", premium]],
    }


class ParseTests(unittest.TestCase):
    def test_parse_snapshot_flattens_and_converts(self):
        parsed = parse_snapshot(_snapshot("10/20/2026", "6,400,000", "$129,528,960", "$20.24", "0.15%"))
        self.assertEqual(parsed["holdings_as_of"], "2026-10-20")
        self.assertEqual(parsed["shares_outstanding"], 6_400_000.0)
        self.assertEqual(parsed["net_assets"], 129_528_960.0)
        self.assertEqual(parsed["nav"], 20.24)
        self.assertEqual(parsed["premium_discount_pct"], 0.15)
        self.assertEqual(parsed["ticker"], "ILS")

    def test_missing_fields_become_none(self):
        parsed = parse_snapshot({"holdings_as_of": None, "fund_details": [], "current_nav_metrics": []})
        self.assertIsNone(parsed["shares_outstanding"])
        self.assertIsNone(parsed["nav"])


class SeriesTests(unittest.TestCase):
    def _archive(self, tmp):
        raw = Path(tmp)
        for date, args in [
            ("2026-09-03", ("09/01/2026", "4,800,000", "$97,044,480", "$20.22", "0.31%")),
            ("2026-08-30", ("08/27/2026", "4,750,000", "$95,630,325", "$20.13", "0.28%")),
            ("2026-09-14", ("09/10/2026", "5,000,000", "$101,524,000", "$20.30", "0.31%")),
        ]:
            folder = raw / date / "brookmont_ils_etf"
            folder.mkdir(parents=True)
            (folder / "fund_snapshot.json").write_text(json.dumps(_snapshot(*args)), encoding="utf-8")
        return raw

    def test_snapshots_are_sorted_and_flows_use_share_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = build_series(load_snapshots(self._archive(tmp)))
        self.assertEqual(series["snapshot_date"].tolist(), ["2026-08-30", "2026-09-03", "2026-09-14"])
        self.assertTrue(pd.isna(series["flow_usd"].iloc[0]))
        self.assertAlmostEqual(series["shares_change"].iloc[1], 50_000.0)
        self.assertAlmostEqual(series["flow_usd"].iloc[1], 50_000 * 20.22)
        self.assertEqual(series["days_since_prior"].iloc[2], 11)
        self.assertAlmostEqual(series["flow_usd"].iloc[2], 200_000 * 20.30)
        self.assertAlmostEqual(series["implied_nav"].iloc[0], 95_630_325 / 4_750_000, places=4)
        self.assertAlmostEqual(
            series["non_flow_change_usd"].iloc[1], (97_044_480 - 95_630_325) - 50_000 * 20.22
        )

    def test_empty_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = build_series(load_snapshots(Path(tmp)))
        self.assertTrue(series.empty)


class ReconciliationTests(unittest.TestCase):
    def test_reconciliation_sums_nport_quarters_and_overlap(self):
        series = pd.DataFrame({
            "snapshot_date": ["2026-08-30", "2026-09-14"],
            "flow_usd": [None, 4_060_000.0],
        })
        nport = pd.DataFrame([
            {"fund_id": "brookmont_catastrophic_bond_etf", "period_end": "2026-06-30", "month_end": "2026-04-30", "sales": 1.0, "redemption": 0.0, "net_flow": 1.0, "net_assets_at_period_end": None},
            {"fund_id": "brookmont_catastrophic_bond_etf", "period_end": "2026-06-30", "month_end": "2026-06-30", "sales": 2.0, "redemption": 0.5, "net_flow": 1.5, "net_assets_at_period_end": 76.0},
            {"fund_id": "brookmont_catastrophic_bond_etf", "period_end": "2026-09-30", "month_end": "2026-08-31", "sales": 3.0, "redemption": 0.0, "net_flow": 3.0, "net_assets_at_period_end": None},
            {"fund_id": "brookmont_catastrophic_bond_etf", "period_end": "2026-09-30", "month_end": "2026-09-30", "sales": 4.0, "redemption": 0.0, "net_flow": 4.0, "net_assets_at_period_end": 100.0},
            {"fund_id": "other_fund", "period_end": "2026-09-30", "month_end": "2026-09-30", "sales": 99.0, "redemption": 0.0, "net_flow": 99.0, "net_assets_at_period_end": 1.0},
        ])
        result = reconcile_with_nport(series, nport)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["nport_quarters"]), 2)
        self.assertEqual(result["nport_net_flow_total"], 9.5)
        self.assertEqual(result["snapshot_flow_total"], 4_060_000.0)
        self.assertEqual(result["nport_months_in_snapshot_window"], ["2026-08-31"])
        self.assertEqual(result["nport_net_flow_in_snapshot_window"], 3.0)

    def test_no_nport_rows_for_the_fund(self):
        result = reconcile_with_nport(pd.DataFrame({"snapshot_date": ["2026-08-30"], "flow_usd": [None]}),
                                      pd.DataFrame({"fund_id": ["x"], "period_end": ["2026-06-30"], "month_end": ["2026-06-30"],
                                                    "sales": [1.0], "redemption": [0.0], "net_flow": [1.0], "net_assets_at_period_end": [1.0]}))
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
