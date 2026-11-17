"""Offline tests for the Brookmont ETF snapshot compiler and its N-PORT reconciliation."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_etf_flows import (  # noqa: E402
    build_series, load_snapshots, month_end_observations, parse_snapshot, reconcile_with_nport, snapshot_monthly_flows,
)


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
        # Dated by the page's own as-of date, not the pull date.
        self.assertEqual(series["effective_date"].tolist(), ["2026-08-27", "2026-09-01", "2026-09-10"])
        self.assertEqual(set(series["effective_date_source"]), {"holdings_as_of"})
        self.assertTrue(pd.isna(series["flow_usd"].iloc[0]))
        self.assertAlmostEqual(series["shares_change"].iloc[1], 50_000.0)
        self.assertAlmostEqual(series["flow_usd"].iloc[1], 50_000 * 20.22)
        self.assertEqual(series["days_since_prior"].iloc[1], 5)
        self.assertEqual(series["days_since_prior"].iloc[2], 9)
        self.assertAlmostEqual(series["flow_usd"].iloc[2], 200_000 * 20.30)
        self.assertAlmostEqual(series["implied_nav"].iloc[0], 95_630_325 / 4_750_000, places=4)
        self.assertAlmostEqual(
            series["non_flow_change_usd"].iloc[1], (97_044_480 - 95_630_325) - 50_000 * 20.22
        )

    def test_pulls_with_the_same_as_of_date_collapse_to_one_observation(self):
        snapshots = pd.DataFrame([
            {"snapshot_date": "2026-10-24", "holdings_as_of": "2026-10-22", "shares_outstanding": 6_800_000.0, "net_assets": 137_748_280.0, "nav": 20.26},
            {"snapshot_date": "2026-10-25", "holdings_as_of": "2026-10-22", "shares_outstanding": 6_800_000.0, "net_assets": 137_748_280.0, "nav": 20.26},
            {"snapshot_date": "2026-10-21", "holdings_as_of": "2026-10-20", "shares_outstanding": 6_400_000.0, "net_assets": 129_528_960.0, "nav": 20.24},
            {"snapshot_date": "2026-10-27", "holdings_as_of": None, "shares_outstanding": 6_850_000.0, "net_assets": 139_000_000.0, "nav": 20.30},
        ])
        series = build_series(snapshots)
        self.assertEqual(series["effective_date"].tolist(), ["2026-10-20", "2026-10-22", "2026-10-27"])
        self.assertEqual(series["snapshot_date"].tolist(), ["2026-10-21", "2026-10-25", "2026-10-27"])
        self.assertEqual(series["effective_date_source"].tolist(), ["holdings_as_of", "holdings_as_of", "snapshot_date"])
        self.assertAlmostEqual(series["flow_usd"].iloc[1], 400_000 * 20.26)
        self.assertEqual(series["days_since_prior"].iloc[1], 2)

    def test_empty_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            series = build_series(load_snapshots(Path(tmp)))
        self.assertTrue(series.empty)


def _series(rows):
    frame = pd.DataFrame(rows, columns=["effective_date", "shares_outstanding", "nav", "net_assets"])
    frame["snapshot_date"] = frame["effective_date"]
    frame["holdings_as_of"] = frame["effective_date"]
    return build_series(frame)


def _nport(month_flows):
    return pd.DataFrame([
        {"fund_id": "brookmont_catastrophic_bond_etf", "period_end": "2026-09-30", "month_end": month, "sales": max(flow, 0.0),
         "redemption": max(-flow, 0.0), "net_flow": flow, "net_assets_at_period_end": None}
        for month, flow in month_flows
    ] + [{"fund_id": "other_fund", "period_end": "2026-09-30", "month_end": "2026-09-30", "sales": 99.0, "redemption": 0.0,
          "net_flow": 99.0, "net_assets_at_period_end": 1.0}])


class ReconciliationTests(unittest.TestCase):
    def test_month_end_observations_need_a_nearby_observation(self):
        series = _series([("2026-07-30", 4_000_000, 20.0, 80e6), ("2026-08-27", 4_750_000, 20.1, 95e6),
                          ("2026-09-01", 4_800_000, 20.2, 97e6), ("2026-09-29", 5_000_000, 20.3, 101e6)])
        ends = month_end_observations(series, tolerance_days=3)
        self.assertEqual(ends["month_end"].tolist(), ["2026-07-31", "2026-09-30"])
        self.assertEqual(ends["days_before_month_end"].tolist(), [1, 1])
        # August's last observation is four days before the month end: not covered at 3, covered at 5.
        self.assertIn("2026-08-31", month_end_observations(series, tolerance_days=5)["month_end"].tolist())

    def test_monthly_flows_need_two_consecutive_covered_month_ends(self):
        series = _series([("2026-07-31", 4_000_000, 20.0, 80e6), ("2026-08-31", 4_500_000, 20.2, 90.9e6),
                          ("2026-10-31", 5_000_000, 20.4, 102e6)])
        monthly = snapshot_monthly_flows(series)
        self.assertEqual(monthly["month_end"].tolist(), ["2026-08-31"])     # September is not covered, so October has no start
        self.assertAlmostEqual(monthly["snapshot_flow_usd"].iloc[0], 500_000 * 20.2)

    def test_reconciliation_on_common_months_with_signed_error_and_tolerance(self):
        series = _series([("2026-06-30", 3_750_000, 20.0, 75e6), ("2026-07-31", 4_000_000, 20.1, 80.4e6),
                          ("2026-08-31", 4_500_000, 20.2, 90.9e6), ("2026-09-30", 4_500_000, 20.3, 91.35e6)])
        nport = _nport([("2026-07-31", 5_000_000.0), ("2026-08-31", 12_000_000.0), ("2026-09-30", -500_000.0), ("2026-10-31", 1.0)])
        result = reconcile_with_nport(series, nport)
        self.assertTrue(result["available"])
        self.assertEqual(result["months_compared"], 3)
        self.assertEqual(result["snapshot_months_covered"], ["2026-07-31", "2026-08-31", "2026-09-30"])
        july, august, september = result["months"]
        self.assertAlmostEqual(july["snapshot_flow_usd"], 250_000 * 20.1)
        self.assertAlmostEqual(july["signed_error_usd"], 250_000 * 20.1 - 5_000_000)   # +25,000
        self.assertAlmostEqual(july["tolerance_usd"], 50_000 * 20.1 + 0.01 * 5_000_000)
        self.assertTrue(july["within_tolerance"])
        self.assertAlmostEqual(august["signed_error_usd"], 500_000 * 20.2 - 12_000_000)  # -1,900,000
        self.assertFalse(august["within_tolerance"])
        self.assertAlmostEqual(september["signed_error_usd"], 500_000.0)
        self.assertEqual(result["months_within_tolerance"], 2)
        self.assertAlmostEqual(result["signed_error_total_usd"], 25_000 - 1_900_000 + 500_000)
        self.assertEqual(result["nport_months_covered"], ["2026-07-31", "2026-10-31"])

    def test_no_common_month_is_reported_with_the_reason(self):
        series = _series([("2026-08-27", 4_750_000, 20.1, 95e6), ("2026-09-10", 5_000_000, 20.3, 101e6)])
        nport = _nport([("2026-05-31", 1.0), ("2026-06-30", 2.0)])
        result = reconcile_with_nport(series, nport)
        self.assertFalse(result["available"])
        self.assertIn("no calendar month is covered by both sources", result["reason"])
        self.assertIn("2026-06-30", result["reason"])
        self.assertEqual(result["snapshot_months_covered"], [])
        self.assertEqual(result["nport_months_covered"], ["2026-05-31", "2026-06-30"])
        # Snapshots that do cover months, but none the filings reach, are still not available.
        series = _series([("2026-07-31", 4_000_000, 20.0, 80e6), ("2026-08-31", 4_500_000, 20.2, 90.9e6)])
        result = reconcile_with_nport(series, nport)
        self.assertFalse(result["available"])
        self.assertEqual(result["snapshot_months_covered"], ["2026-08-31"])
        self.assertEqual(result["snapshot_month_ends_covered"], ["2026-07-31", "2026-08-31"])

    def test_one_covered_month_end_is_reported_as_not_yet_a_month(self):
        # The live case on 2026-11-17: daily pulls since late October cover the
        # 31 October month end (observation dated 30 October) but September's
        # last observation was the 10th, so no month has both bounds.
        series = _series([("2026-08-27", 4_750_000, 20.1, 95e6), ("2026-09-10", 5_000_000, 20.3, 101e6),
                          ("2026-10-30", 7_800_000, 20.3, 158e6), ("2026-11-13", 8_650_000, 20.3, 175e6)])
        result = reconcile_with_nport(series, _nport([("2026-05-31", 1.0), ("2026-06-30", 2.0)]))
        self.assertFalse(result["available"])
        self.assertEqual(result["snapshot_month_ends_covered"], ["2026-10-31"])
        self.assertEqual(result["snapshot_months_covered"], [])
        self.assertIn("no two consecutive ones", result["reason"])
        self.assertIn("2026-10-31", result["reason"])

    def test_no_nport_rows_for_the_fund(self):
        series = _series([("2026-08-30", 4_750_000, 20.1, 95e6)])
        result = reconcile_with_nport(series, pd.DataFrame({"fund_id": ["x"], "period_end": ["2026-06-30"], "month_end": ["2026-06-30"],
                                                            "sales": [1.0], "redemption": [0.0], "net_flow": [1.0], "net_assets_at_period_end": [1.0]}))
        self.assertFalse(result["available"])
        self.assertIn("no N-PORT rows", result["reason"])


if __name__ == "__main__":
    unittest.main()
