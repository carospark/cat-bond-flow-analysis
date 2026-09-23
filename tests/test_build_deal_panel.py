"""Offline tests for the deal panel: peril mapping, trade aggregation, joins."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_deal_panel import (  # noqa: E402
    aggregate_market_classes,
    aggregate_trades,
    attach_hazards,
    build_hazard_map,
    combine_bridges,
    map_perils,
)


class PerilMappingTests(unittest.TestCase):
    def test_us_multi_peril(self):
        pairs = map_perils("U.S. named storm, U.S. earthquake, Canada earthquake, severe thunderstorm, wildfire")
        self.assertIn(("hurricane_or_named_storm", "us"), pairs)
        self.assertIn(("earthquake", "us"), pairs)
        self.assertIn(("earthquake", "canada"), pairs)
        self.assertIn(("severe_convective_storm", "us"), pairs)
        self.assertIn(("wildfire", "us"), pairs)

    def test_specific_geographies(self):
        self.assertEqual(map_perils("California earthquake"), [("earthquake", "california")])
        self.assertEqual(map_perils("Japan typhoon"), [("typhoon_or_cyclone", "japan")])
        self.assertEqual(map_perils("Japan earthquake"), [("earthquake", "japan")])
        self.assertEqual(map_perils("Florida named storm"), [("hurricane_or_named_storm", "florida")])
        self.assertEqual(map_perils("Australia cyclone"), [("typhoon_or_cyclone", "australia")])

    def test_european_windstorm_is_not_a_hurricane(self):
        self.assertEqual(map_perils("European windstorm"), [("windstorm", "europe")])
        pairs = map_perils("U.S. hurricane, European windstorm, Japan earthquake")
        self.assertEqual(sorted(pairs), [
            ("earthquake", "japan"), ("hurricane_or_named_storm", "us"), ("windstorm", "europe"),
        ])

    def test_unmapped_perils(self):
        self.assertEqual(map_perils("mortgage insurance risks"), [])
        self.assertEqual(map_perils("meteorite impact"), [])
        self.assertEqual(map_perils(None), [])
        self.assertEqual(map_perils("extreme mortality"), [("pandemic_or_mortality", "global")])
        self.assertEqual(map_perils("U.S. flood risk (from named storms)"),
                         [("precipitation", "us"), ("hurricane_or_named_storm", "us")])


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.bridge = pd.DataFrame({
            "cusip_id": ["C1", "C2"], "deal_url": ["d1", "d1"], "match_confidence": ["high", "medium"],
        })
        self.trades = pd.DataFrame({
            "cusip_id": ["C1", "C1", "C1", "C9"],
            "trade_date": ["2024-09-26", "2024-09-26", "2024-09-27", "2024-09-26"],
            "trade_time": ["10:00:00", "15:00:00", "09:00:00", "09:00:00"],
            "price": [98.0, 96.0, 97.0, 100.0],
            "volume": [1_000_000.0, 3_000_000.0, 500_000.0, 1.0],
            "dealer_side": ["S", "B", "S", "S"],
            "volume_capped": [False, True, False, False],
        })

    def test_deal_daily_aggregation(self):
        panel = aggregate_trades(self.trades, self.bridge)
        self.assertEqual(len(panel), 2)
        day = panel.iloc[0]
        self.assertEqual(day["n_trades"], 2)
        self.assertEqual(day["volume"], 4_000_000.0)
        self.assertAlmostEqual(day["vwap"], 96.5)
        self.assertEqual(day["last_price"], 96.0)
        self.assertEqual(day["dealer_sell_volume"], 1_000_000.0)
        self.assertEqual(day["dealer_buy_volume"], 3_000_000.0)
        self.assertEqual(day["capped_volume_rows"], 1)

    def test_program_nearest_rows_join_with_program_confidence(self):
        program = pd.DataFrame({
            "cusip_id": ["C9", "C1", "C8", "C7", "C6"],
            "level": ["program_nearest", "program_nearest", "program_tied", "program_only",
                      "program_maturity_split"],
            "deal_url": ["d2", "d9", "", "", "d3"],
        })
        combined = combine_bridges(self.bridge, program)
        self.assertEqual(combined["cusip_id"].tolist(), ["C1", "C2", "C9", "C6"])
        self.assertEqual(combined["match_confidence"].tolist(), ["high", "medium", "program", "program"])
        self.assertEqual(combined.set_index("cusip_id").loc["C1", "deal_url"], "d1")  # strict wins
        self.assertEqual(combined.set_index("cusip_id").loc["C9", "match_confidence"], "program")
        panel = aggregate_trades(self.trades, combined)
        self.assertEqual(panel[panel["deal_url"] == "d2"]["match_confidence"].tolist(), ["program"])
        self.assertEqual(panel[panel["deal_url"] == "d1"]["n_trades"].sum(), 3)
        self.assertTrue(combine_bridges(self.bridge, None).equals(
            combine_bridges(self.bridge, program.iloc[0:0])))
        with self.assertRaises(ValueError):
            combine_bridges(pd.concat([self.bridge, self.bridge]), None)

    def test_hazard_map_and_attach(self):
        deals = pd.DataFrame({"deal_url": ["d1", "d2"],
                              "perils_covered": ["Florida named storm, U.S. earthquake", "Japan typhoon"]})
        hazard_map = build_hazard_map(deals, self.bridge)
        self.assertEqual(set(hazard_map["deal_url"]), {"d1"})
        self.assertEqual(sorted(zip(hazard_map["hazard_class"], hazard_map["region"])),
                         [("earthquake", "us"), ("hurricane_or_named_storm", "florida")])
        market = pd.DataFrame({
            "platform": ["kalshi", "kalshi", "polymarket"], "contract_id": ["k1", "k1", "p1"],
            "date": ["2024-09-26", "2024-09-27", "2024-09-26"],
            "last_price": [0.4, 0.7, None], "n_price_points": [3, 2, 0],
            "n_trades": [5, 0, 2], "traded_size": [100.0, 0.0, 20.0],
            "classification": ["hurricane_or_named_storm;region:florida;region:us"] * 2 + ["earthquake;region:us"],
            "title": ["a", "a", "b"],
            "hazard_classes": ["hurricane_or_named_storm"] * 2 + ["earthquake"],
            "regions": ["florida;us"] * 2 + ["us"],
        })
        class_daily = aggregate_market_classes(market)
        florida = class_daily[(class_daily["hazard_class"] == "hurricane_or_named_storm")
                              & (class_daily["region"] == "florida")]
        self.assertEqual(florida["contracts_priced"].tolist(), [1, 1])
        self.assertEqual(florida["contracts_traded"].tolist(), [1, 0])
        panel = attach_hazards(aggregate_trades(self.trades, self.bridge), hazard_map, class_daily)
        row = panel[(panel["trade_date"] == "2024-09-26") & (panel["hazard_class"] == "hurricane_or_named_storm")].iloc[0]
        self.assertEqual(row["region"], "florida")
        self.assertEqual(row["market_contracts_priced"], 1)
        self.assertEqual(row["market_traded_size"], 100.0)
        self.assertEqual(row["n_trades"], 2)  # the deal's own trade count survives
        quake = panel[(panel["trade_date"] == "2024-09-26") & (panel["hazard_class"] == "earthquake")].iloc[0]
        self.assertEqual(quake["market_contracts_priced"], 0)
        self.assertEqual(quake["market_traded_size"], 20.0)


if __name__ == "__main__":
    unittest.main()
