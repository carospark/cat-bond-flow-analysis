"""Offline tests for resolving program-bridge ties from N-PORT titles."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from resolve_ties_from_nport import (  # noqa: E402
    check_strict_bridge,
    resolve_program_rows,
    series_from_deal_url,
    series_from_title,
    titles_by_cusip,
)


class SeriesParsingTests(unittest.TestCase):
    def test_series_from_title(self):
        self.assertEqual(series_from_title("Kilimanjaro III Re 2019-1 Class A-1"), "2019-1")
        self.assertEqual(series_from_title("Merna Re II 2022-2 Class A"), "2022-2")
        self.assertEqual(series_from_title("Phoenician Re Ltd. 2020-12 Class A"), "2020-12")
        self.assertIsNone(series_from_title("KILIMANJARO II RE LTD REGD V/R 144A P/P SER A-1 12.373"))
        self.assertIsNone(series_from_title("Merna Reinsurance II Ltd"))
        self.assertIsNone(series_from_title(None))

    def test_series_from_deal_url(self):
        self.assertEqual(series_from_deal_url("https://www.artemis.bm/deal-directory/kilimanjaro-iii-re-ltd-series-2019-1/"), ["2019-1"])
        self.assertEqual(series_from_deal_url("https://x/merna-re-ii-ltd-series-2022-02"), ["2022-2"])
        self.assertEqual(series_from_deal_url("https://x/london-bridge-2-pcc-limited-titania-re-2026-1/"), ["2026-1"])
        self.assertEqual(series_from_deal_url("https://x/caelus-re-vi-ltd-series-2020-1-2020-2/"), ["2020-1", "2020-2"])
        self.assertEqual(series_from_deal_url("https://x/vita-capital-ii-ltd/"), [])
        self.assertEqual(series_from_deal_url("https://x/residential-reinsurance-2021-limited-series-2021-1/"), ["2021-1"])


def _holdings():
    return pd.DataFrame([
        {"fund_id": "f1", "accession": "a1", "cusip": "K3A", "title": "Kilimanjaro III Re 2019-1 Class A-1"},
        {"fund_id": "f2", "accession": "a2", "cusip": "k3a", "title": "Kilimanjaro III Re 2019-1 Class A-1"},
        {"fund_id": "f1", "accession": "a1", "cusip": "K3C", "title": "Kilimanjaro III Re 2019-2 Class A-2"},
        {"fund_id": "f1", "accession": "a1", "cusip": "K3C", "title": "Kilimanjaro III Re 2019-1 Class A-2"},
        {"fund_id": "f1", "accession": "a1", "cusip": "MRN", "title": "Merna Reinsurance II Ltd"},
        {"fund_id": "f1", "accession": "a1", "cusip": "PHX", "title": "Phoenician Re Ltd. 2020-9 Class A"},
        {"fund_id": "f1", "accession": "a1", "cusip": "STR", "title": "Residential Re 2021-1 Class 11"},
        {"fund_id": "f1", "accession": "a1", "cusip": "STW", "title": "Sanders Re II 2021-2 Class A"},
    ])


def _program():
    k = "https://www.artemis.bm/deal-directory/kilimanjaro-iii-re-ltd-series-2019-1/|https://www.artemis.bm/deal-directory/kilimanjaro-iii-re-ltd-series-2019-2/"
    p = "https://www.artemis.bm/deal-directory/phoenician-re-ltd-series-2020-1/|https://www.artemis.bm/deal-directory/phoenician-re-ltd-series-2020-2/"
    return pd.DataFrame([
        {"cusip_id": "K3A", "level": "program_tied", "tied_deal_urls": k, "program_deals": k},
        {"cusip_id": "K3C", "level": "program_tied", "tied_deal_urls": k, "program_deals": k},
        {"cusip_id": "MRN", "level": "program_tied", "tied_deal_urls": "https://x/merna-re-ii-ltd-series-2022-2/|https://x/merna-re-ii-ltd-series-2022-3/", "program_deals": ""},
        {"cusip_id": "PHX", "level": "program_only", "tied_deal_urls": "", "program_deals": p},
        {"cusip_id": "NOT", "level": "program_nearest", "tied_deal_urls": "", "program_deals": p},
    ])


class ResolutionTests(unittest.TestCase):
    def test_titles_by_cusip_normalizes_and_collects(self):
        titles = titles_by_cusip(_holdings()).set_index("cusip")
        self.assertEqual(titles.loc["K3A", "series_named"], ["2019-1"])
        self.assertEqual(titles.loc["K3A", "funds"], ["f1", "f2"])
        self.assertEqual(titles.loc["K3C", "series_named"], ["2019-1", "2019-2"])
        self.assertNotIn("MRN", titles.index)

    def test_resolve_program_rows_outcomes(self):
        out = resolve_program_rows(_program(), titles_by_cusip(_holdings())).set_index("cusip_id")
        self.assertEqual(out.loc["K3A", "outcome"], "resolved")
        self.assertEqual(out.loc["K3A", "deal_url"], "https://www.artemis.bm/deal-directory/kilimanjaro-iii-re-ltd-series-2019-1/")
        self.assertEqual(out.loc["K3A", "evidence"], "nport_title:2019-1")
        self.assertEqual(out.loc["K3C", "outcome"], "titles_disagree")
        self.assertEqual(out.loc["PHX", "outcome"], "series_not_in_candidates")
        self.assertNotIn("MRN", out.index)
        self.assertNotIn("NOT", out.index)

    def test_check_strict_bridge_flags_disagreement(self):
        bridge = pd.DataFrame([
            {"cusip_id": "STR", "deal_url": "https://x/residential-reinsurance-2021-limited-series-2021-1/", "match_confidence": "high", "match_method": "exact"},
            {"cusip_id": "STW", "deal_url": "https://x/sanders-re-ii-ltd-series-2021-1/", "match_confidence": "medium", "match_method": "fuzzy"},
            {"cusip_id": "VIT", "deal_url": "https://x/vita-capital-ii-ltd/", "match_confidence": "medium", "match_method": "fuzzy"},
        ])
        check = check_strict_bridge(bridge, titles_by_cusip(_holdings())).set_index("cusip_id")
        self.assertEqual(check.loc["STR", "agrees"], True)
        self.assertEqual(check.loc["STW", "agrees"], False)
        self.assertNotIn("VIT", check.index)


if __name__ == "__main__":
    unittest.main()
