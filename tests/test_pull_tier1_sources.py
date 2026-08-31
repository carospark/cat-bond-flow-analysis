import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pull_tier1_sources import parse_brookmont_ils, parse_with_ils_index


class Tier1ParserTests(unittest.TestCase):
    def test_parse_with_ils_index(self):
        monthly = [
            {
                "__typename": "DomFundIndexMonthlyReturn",
                "date": f"{2006 + index // 12:04d}-{index % 12 + 1:02d}-01",
                "performance": 0.01,
                "calculatedFunds": 12,
                "percentage": 1,
            }
            for index in range(204)
        ]
        page_data = {
            "props": {
                "pageProps": {
                    "ssrCache": {
                        "DomFundIndex:test": {
                            "__typename": "DomFundIndex",
                            "id": "11750",
                            "monthlyReturns": monthly,
                        }
                    }
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            page = tmp_path / "index.html"
            page.write_text(
                f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(page_data)}</script>',
                encoding="utf-8",
            )

            outputs = parse_with_ils_index(page, tmp_path / "out")

            rows = outputs[0].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 205)
            self.assertTrue(rows[1].startswith("2006-01-01,0.01,12,1"))

    def test_parse_brookmont_ils(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            page = tmp_path / "ils.html"
            page.write_text(
                """
                <section class="etfg-details-section"><table><tr><th>Fund Detail</th><th>Value</th></tr>
                <tr><td>Ticker</td><td>ILS</td></tr></table></section>
                <table id="etfg-nav-data-table"><tr><th>Metric</th><th>Value</th></tr>
                <tr><td>NAV</td><td>$20.00</td></tr></table>
                <span id="etfg-holdings-date">08/27/2026</span>
                <table id="etfg-holdings-data-table">
                  <tr><th>Holding Name</th><th>Ticker</th><th>FIGI</th><th>Quantity</th><th>Market Value</th><th>% of NAV</th></tr>
                  <tr><td>Test Bond</td><td>TEST</td><td>BBG123</td><td>10</td><td>$100</td><td>1%</td></tr>
                </table>
                <div data-ticker="ILS" data-series='[{"date":"2025-04-01","market_price":20.1,"nav":19.99,"premium_discount_pct":0.55}]'></div>
                """,
                encoding="utf-8",
            )

            outputs = parse_brookmont_ils(page, tmp_path / "out")

            self.assertEqual(
                {path.name for path in outputs},
                {"holdings.csv", "daily_nav.csv", "fund_snapshot.json"},
            )
            self.assertIn("Test Bond", (tmp_path / "out" / "holdings.csv").read_text())
            metadata = json.loads((tmp_path / "out" / "fund_snapshot.json").read_text())
            self.assertEqual(metadata["holdings_as_of"], "08/27/2026")


if __name__ == "__main__":
    unittest.main()
