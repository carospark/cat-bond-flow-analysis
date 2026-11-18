"""Offline tests for the hurricane event-study gate on synthetic frames."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from event_gate import bridge_by_deal, gate_table, marks_by_deal, storm_history, usable_prices  # noqa: E402

EVENT = "2022-09-28"
A, B, C, D = ("u/a", "u/b", "u/c", "u/d")


def _hazards():
    return pd.DataFrame({
        "deal_url": [A, B, C, D],
        "hazard_class": ["hurricane_or_named_storm", "hurricane_or_named_storm", "earthquake", "hurricane_or_named_storm"],
        "region": ["florida", "us", "california", "japan"],
        "perils_covered": ["Florida hurricane", "U.S. hurricane", "California earthquake", "Japan typhoon"],
    })


def _bridge():
    return pd.DataFrame({
        "deal_url": [A, A, B, D],
        "cusip_id": ["A1", "A2", "B1", "D1"],
        "match_confidence": ["high", "medium", "medium", "high"],
        "trace_issue_date": ["2021-06-01", "2021-06-01", "2022-10-15", "2020-01-01"],
        "trace_maturity_date": ["2025-06-01", "2025-06-01", "2026-01-01", "2021-01-01"],
    })


def _trades():
    rows = [
        (A, "A1", "2022-09-01", 99.0, 1e6, "high"), (A, "A1", "2022-10-05", 90.0, 1e6, "high"),
        (A, "A2", "2022-09-10", 98.0, 1e6, "medium"),
        (B, "B1", "2022-09-20", 97.0, 1e6, "medium"), (B, "B1", "2022-09-28", 96.0, 1e6, "medium"),  # event day: neither side
        (C, "C1", "2022-09-02", 100.0, 1e6, "program"), (C, "C1", "2022-10-02", 100.0, 1e6, "program"),
        (D, "D1", "2022-08-01", 95.0, 0.0, "high"), (D, "D1", "2022-10-01", 95.0, 1e6, "high"),
    ]
    return pd.DataFrame(rows, columns=["deal_url", "cusip_id", "trade_date", "vwap", "volume", "match_confidence"])


def _market(priced_post=True):
    rows = [
        ("kalshi", "K1", "2022-09-01", 0.4, "hurricane_or_named_storm", "florida;us"),
        ("kalshi", "K1", "2022-10-03", 0.9 if priced_post else None, "hurricane_or_named_storm", "florida;us"),
        ("kalshi", "K2", "2022-09-05", 0.2, "hurricane_or_named_storm", "japan"),
        ("kalshi", "K3", "2022-09-05", 0.2, "earthquake", "us"),
    ]
    return pd.DataFrame(rows, columns=["platform", "contract_id", "date", "last_price", "hazard_classes", "regions"])


def _marks():
    return pd.DataFrame({"deal_url": [A, A, B], "period_end": ["2022-07-31", "2022-10-31", "2023-01-31"], "cusip": ["A1", "A1", "B1"]})


class GateTests(unittest.TestCase):
    def test_bridge_by_deal(self):
        b = bridge_by_deal(_bridge(), EVENT).set_index("deal_url")
        self.assertEqual((b.loc[A, "cusips"], b.loc[A, "cusips_high"]), (2, 1))
        self.assertTrue(b.loc[A, "alive_at_event"])
        self.assertFalse(b.loc[B, "alive_at_event"])  # issued after the event
        self.assertFalse(b.loc[D, "alive_at_event"])  # matured before
        self.assertTrue(b.loc[B, "strict_bridge"] and not b.loc[B, "high_confidence"])

    def test_usable_prices(self):
        u = usable_prices(_trades(), EVENT, 45, 60).set_index("deal_url")
        self.assertTrue(u.loc[A, "usable_prices"])
        self.assertEqual((u.loc[A, "pre_trade_days"], u.loc[A, "post_trade_days"]), (2, 1))
        self.assertFalse(u.loc[B, "usable_prices"])  # event-day trade counts for neither side
        self.assertNotIn(C, u.index)  # program rows excluded
        self.assertFalse(u.loc[D, "usable_prices"])  # zero-volume pre day
        h = usable_prices(_trades(), EVENT, 45, 60, high_only=True).set_index("deal_url")
        self.assertEqual(h.loc[A, "pre_trade_days_high"], 1)
        self.assertTrue(h.loc[A, "usable_prices_high"])

    def test_storm_history(self):
        s = storm_history(_market(), EVENT, 45, 60)
        self.assertEqual((s["contracts_priced_pre"], s["contracts_priced_post"], s["contracts_priced_both_sides"]), (1, 1, 1))
        self.assertTrue(s["passes"])
        self.assertFalse(storm_history(_market(priced_post=False), EVENT, 45, 60)["passes"])

    def test_marks(self):
        m = marks_by_deal(_marks(), EVENT, 45, 60).set_index("deal_url")
        self.assertTrue(m.loc[A, "mark_in_window"])  # 2022-10-31 is 33 days after
        self.assertTrue(m.loc[A, "mark_in_event_quarter"])  # 2022-07-31 is Q3
        self.assertEqual(m.loc[A, "marks_in_window"], 1)
        self.assertFalse(m.loc[B, "mark_in_window"])

    def test_gate_table_funnels(self):
        table, summary = gate_table(_hazards(), _bridge(), _trades(), _market(), _marks(), EVENT, 45, 60)
        self.assertEqual(summary["funnel_strict_any_confidence"],
                         {"exposed": 2, "alive_at_event": 1, "strict_bridge": 1, "usable_prices": 1, "storm_history": 1, "mark_in_window": 1})
        self.assertEqual(summary["funnel_high_confidence"]["usable_prices_high"], 1)
        self.assertEqual(summary["passing_strict"], 1)
        self.assertEqual(summary["any_hurricane_deals"], 3)
        row = table.set_index("deal_url").loc[A]
        self.assertTrue(row["passes_high"])
        self.assertEqual(table["deal_url"].iloc[0], A)  # passing rows sort first
        self.assertEqual(table.set_index("deal_url").loc[C, "group"], "unexposed")


if __name__ == "__main__":
    unittest.main()
