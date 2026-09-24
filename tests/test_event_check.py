"""Offline tests for the hurricane event check: grouping and pre/post arithmetic."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from event_check import classify_deals, deal_changes, weekly_market, weekly_series  # noqa: E402


class GroupingTests(unittest.TestCase):
    def test_groups(self):
        hazard_map = pd.DataFrame([
            {"deal_url": "fl", "hazard_class": "hurricane_or_named_storm", "region": "florida",
             "perils_covered": "Florida named storm"},
            {"deal_url": "us", "hazard_class": "hurricane_or_named_storm", "region": "us",
             "perils_covered": "U.S. named storm, U.S. earthquake"},
            {"deal_url": "us", "hazard_class": "earthquake", "region": "us",
             "perils_covered": "U.S. named storm, U.S. earthquake"},
            {"deal_url": "exfl", "hazard_class": "hurricane_or_named_storm", "region": "us",
             "perils_covered": "U.S. named storms (excluding Florida), U.S. earthquake"},
            {"deal_url": "tx", "hazard_class": "hurricane_or_named_storm", "region": "texas",
             "perils_covered": "Texas named storms"},
            {"deal_url": "jp", "hazard_class": "earthquake", "region": "japan",
             "perils_covered": "Japan earthquake"},
            {"deal_url": "eu", "hazard_class": "windstorm", "region": "europe",
             "perils_covered": "European windstorm"},
        ])
        groups = classify_deals(hazard_map)
        self.assertEqual(groups["fl"], "exposed")
        self.assertEqual(groups["us"], "exposed")
        self.assertEqual(groups["exfl"], "ambiguous")
        self.assertEqual(groups["tx"], "other_hurricane")
        self.assertEqual(groups["jp"], "unexposed")
        self.assertEqual(groups["eu"], "unexposed")


class ChangeTests(unittest.TestCase):
    def setUp(self):
        self.groups = pd.Series({"fl": "exposed", "jp": "unexposed", "one": "exposed"})
        self.trades = pd.DataFrame([
            # fl: pre mean 100 (equal volume), post VW = (90*3 + 94*1)/4 = 91, low 88
            {"deal_url": "fl", "cusip_id": "A", "trade_date": "2022-09-01", "vwap": 101.0, "volume": 1e6, "low_price": 101.0, "match_confidence": "high"},
            {"deal_url": "fl", "cusip_id": "A", "trade_date": "2022-09-20", "vwap": 99.0, "volume": 1e6, "low_price": 99.0, "match_confidence": "high"},
            {"deal_url": "fl", "cusip_id": "A", "trade_date": "2022-10-03", "vwap": 90.0, "volume": 3e6, "low_price": 88.0, "match_confidence": "high"},
            {"deal_url": "fl", "cusip_id": "A", "trade_date": "2022-11-10", "vwap": 94.0, "volume": 1e6, "low_price": 94.0, "match_confidence": "high"},
            # jp: flat
            {"deal_url": "jp", "cusip_id": "B", "trade_date": "2022-09-10", "vwap": 100.0, "volume": 1e6, "low_price": 100.0, "match_confidence": "high"},
            {"deal_url": "jp", "cusip_id": "B", "trade_date": "2022-10-10", "vwap": 100.5, "volume": 1e6, "low_price": 100.5, "match_confidence": "high"},
            # one: trades only before the event, so it is dropped
            {"deal_url": "one", "cusip_id": "C", "trade_date": "2022-09-10", "vwap": 100.0, "volume": 1e6, "low_price": 100.0, "match_confidence": "high"},
            # on the event day itself: neither side
            {"deal_url": "fl", "cusip_id": "A", "trade_date": "2022-09-28", "vwap": 50.0, "volume": 9e6, "low_price": 50.0, "match_confidence": "high"},
            # outside the window
            {"deal_url": "fl", "cusip_id": "A", "trade_date": "2022-06-01", "vwap": 10.0, "volume": 9e6, "low_price": 10.0, "match_confidence": "high"},
        ])

    def test_deal_changes(self):
        changes = deal_changes(self.trades, self.groups, "2022-09-28", 45, 60).set_index("deal_url")
        self.assertEqual(sorted(changes.index), ["fl", "jp"])
        self.assertAlmostEqual(changes.loc["fl", "pre_price"], 100.0)
        self.assertAlmostEqual(changes.loc["fl", "post_price"], 91.0)
        self.assertAlmostEqual(changes.loc["fl", "change_points"], -9.0)
        self.assertAlmostEqual(changes.loc["fl", "trough_points"], -12.0)
        self.assertAlmostEqual(changes.loc["jp", "change_points"], 0.5)
        self.assertEqual(changes.loc["fl", "group"], "exposed")

    def test_weekly_series_is_relative_to_each_deal(self):
        changes = deal_changes(self.trades, self.groups, "2022-09-28", 45, 60)
        weekly = weekly_series(self.trades, self.groups, changes, "2022-09-28", 45, 60)
        fl = weekly[weekly["group"].eq("exposed")].set_index("week")
        # Week 0 holds the landfall day and 2022-10-03: VW of 50 (9m) and 90 (3m)
        # is 60, so -40 against the pre mean. The landfall day counts in the
        # weekly series but on neither side of the pre/post arithmetic.
        self.assertAlmostEqual(fl.loc[0, "median_change_points"], -40.0)
        self.assertAlmostEqual(fl.loc[6, "median_change_points"], -6.0)    # 2022-11-10 is week 6
        self.assertAlmostEqual(fl.loc[-4, "median_change_points"], 1.0)    # 2022-09-01 is week -4
        self.assertNotIn(-17, fl.index)                                     # June trade is outside the window

    def test_weekly_market_filters_class_and_region(self):
        market = pd.DataFrame([
            {"hazard_class": "hurricane_or_named_storm", "region": "florida", "date": "2022-09-30",
             "contracts_priced": 3, "contracts_traded": 2, "n_trades": 10, "traded_size": 500.0},
            {"hazard_class": "hurricane_or_named_storm", "region": "us", "date": "2022-10-01",
             "contracts_priced": 3, "contracts_traded": 1, "n_trades": 4, "traded_size": 100.0},
            {"hazard_class": "hurricane_or_named_storm", "region": "japan", "date": "2022-10-01",
             "contracts_priced": 3, "contracts_traded": 1, "n_trades": 4, "traded_size": 999.0},
            {"hazard_class": "earthquake", "region": "us", "date": "2022-10-01",
             "contracts_priced": 3, "contracts_traded": 1, "n_trades": 4, "traded_size": 999.0},
        ])
        out = weekly_market(market, "2022-09-28", 45, 60).set_index("week")
        self.assertEqual(list(out.index), [0])
        self.assertAlmostEqual(out.loc[0, "traded_size"], 600.0)
        self.assertEqual(out.loc[0, "contracts_traded"], 3)


if __name__ == "__main__":
    unittest.main()
