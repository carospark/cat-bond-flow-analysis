"""Offline tests for the bridge audit additions: title-evidence classes, the
high-confidence selections, and the held-out sample draw."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_bridge import title_evidence_class, title_evidence_counts  # noqa: E402
from build_deal_panel import high_confidence_only  # noqa: E402
from draw_bridge_audit_sample import allocate, draw_sample, year_bucket  # noqa: E402
from event_check import select_trades  # noqa: E402


class TitleEvidenceTests(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(title_evidence_class("exact_normalized_issuer", "missing_or_not_stated"), "none")
        self.assertEqual(title_evidence_class("exact_normalized_issuer", "exact_series; nport_title 2019-1 agrees"), "agrees")
        self.assertEqual(title_evidence_class("exact_normalized_issuer+nport_title_split", "missing_or_not_stated; nport_title 2026-2 agrees"), "split")
        self.assertEqual(title_evidence_class("canonical_alias_issuer", "missing_or_not_stated; nport_title 2024-2 not in directory for this issuer"), "capped_not_in_directory")
        self.assertEqual(title_evidence_class("exact_normalized_issuer", "missing_or_not_stated; nport_title 2020-1, deal series not stated"), "series_not_stated")
        self.assertEqual(title_evidence_class("exact_normalized_issuer+maturity_group_of_title_split",
                                              "missing_or_not_stated; follows title-split siblings X with maturity 2021-01-08"), "propagated")

    def test_counts(self):
        bridge = pd.DataFrame({"title_evidence": ["none", "none", "agrees", "split", "capped_not_in_directory", "propagated", "series_not_stated"]})
        counts = title_evidence_counts(bridge)
        self.assertEqual(counts["pairs_without_title_evidence"], 2)
        self.assertEqual(counts["pairs_changed_or_split_by_title"], 2)
        self.assertEqual(counts["pairs_created_by_title_propagation"], 1)
        self.assertEqual(counts["pairs_title_agrees_unchanged"], 1)
        self.assertEqual(sum(counts["by_class"].values()), len(bridge))
        self.assertEqual(title_evidence_counts(pd.DataFrame())["pairs_without_title_evidence"], 0)


class HighConfidenceTests(unittest.TestCase):
    def setUp(self):
        self.rows = pd.DataFrame({
            "cusip_id": list("ABCD"), "deal_url": ["d"] * 4,
            "match_confidence": ["high", "medium", "low", "program"],
        })

    def test_bridge_filter_keeps_only_high(self):
        self.assertEqual(high_confidence_only(self.rows)["cusip_id"].tolist(), ["A"])

    def test_event_check_selection(self):
        self.assertEqual(select_trades(self.rows, False, False)["cusip_id"].tolist(), ["A", "B", "C"])
        self.assertEqual(select_trades(self.rows, True, False)["cusip_id"].tolist(), ["A", "B", "C", "D"])
        self.assertEqual(select_trades(self.rows, False, True)["cusip_id"].tolist(), ["A"])


class SampleTests(unittest.TestCase):
    def _bridge(self):
        rows = []
        k = 0
        for confidence, n in (("high", 300), ("medium", 100), ("low", 3)):
            for i in range(n):
                year = 2004 + (k % 23)
                rows.append({"deal_url": f"d{k}", "artemis_issuer_name": f"Issuer {k}", "artemis_date_text": f"Jun {year}",
                             "cusip_id": f"C{k:05d}", "match_confidence": confidence, "match_method": "exact_normalized_issuer",
                             "title_evidence": "none", "series_evidence": "", "artemis_size_text": "$100m"})
                k += 1
        return pd.DataFrame(rows)

    def test_year_bucket(self):
        self.assertEqual(year_bucket("Jun 2012"), "to_2012")
        self.assertEqual(year_bucket("Dec 2013"), "2013_2017")
        self.assertEqual(year_bucket("Jan 2021"), "2018_2021")
        self.assertEqual(year_bucket("May 2026"), "2022_on")
        self.assertEqual(year_bucket(""), "unknown")

    def test_allocate_respects_total_minimum_and_capacity(self):
        alloc = allocate(pd.Series({"a": 50, "b": 30, "c": 1, "d": 0}), 10)
        self.assertEqual(sum(alloc.values()), 10)
        self.assertEqual(alloc["c"], 1)
        self.assertNotIn("d", alloc)
        self.assertEqual(allocate(pd.Series({"a": 0}), 5), {})

    def test_draw_is_sized_stratified_reproducible_and_unscored(self):
        bridge = self._bridge()
        sample = draw_sample(bridge, 40, seed=1)
        self.assertEqual(len(sample), 40)
        self.assertEqual((sample["match_confidence"] == "low").sum(), 3)
        self.assertEqual((sample["match_confidence"] == "high").sum(), 20)
        self.assertEqual((sample["match_confidence"] == "medium").sum(), 17)
        self.assertEqual(sample["cusip_id"].nunique(), 40)
        self.assertTrue(set(sample["stratum"].str.split(":").str[1]) >= {"to_2012", "2013_2017", "2018_2021", "2022_on"})
        self.assertTrue((sample["audit_verdict"] == "").all() and (sample["audit_notes"] == "").all())
        self.assertEqual(sample["sample_id"].tolist(), list(range(1, 41)))
        again = draw_sample(bridge, 40, seed=1)
        self.assertEqual(sample["cusip_id"].tolist(), again["cusip_id"].tolist())
        self.assertNotEqual(sample["cusip_id"].tolist(), draw_sample(bridge, 40, seed=2)["cusip_id"].tolist())


if __name__ == "__main__":
    unittest.main()
