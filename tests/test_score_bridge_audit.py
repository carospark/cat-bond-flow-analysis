"""Offline tests for the audit worksheet renderer and the audit scorer."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from render_bridge_audit_worksheet import attach_sources, render, tenor_check  # noqa: E402
from score_bridge_audit import format_report, score, wilson  # noqa: E402


def _sample():
    return pd.DataFrame({
        "sample_id": ["1", "2", "3", "4", "5", "6"],
        "stratum": ["high:2022_on", "high:2022_on", "medium:to_2012", "medium:to_2012", "low:to_2012", "low:to_2012"],
        "deal_url": ["https://example.test/a"] * 6,
        "artemis_issuer_name": ["A Re Ltd. (Series 2022-1)", "B Re", "C <Re>", "D", "E", "F"],
        "cusip_id": ["000000AA0", "000000AB8", "000000AC6", "000000AD4", "000000AE2", "000000AF9"],
        "audit_verdict": ["correct", "correct", "correct", "wrong", "undecidable", ""],
        "audit_notes": ["", "", "", "sibling series", "", ""],
    })


class WilsonTests(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(wilson(0, 0), (None, None))
        lo, hi = wilson(10, 10)
        self.assertGreater(lo, 0.7)
        self.assertAlmostEqual(hi, 1.0)
        lo, hi = wilson(5, 10)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)


class ScoreTests(unittest.TestCase):
    def test_tallies(self):
        result = score(_sample())
        overall = result["overall"]
        self.assertEqual((overall["correct"], overall["wrong"], overall["undecidable"], overall["unread"]), (3, 1, 1, 1))
        self.assertAlmostEqual(overall["precision"], 0.75)
        self.assertEqual(result["by_confidence"]["high"]["precision"], 1.0)
        self.assertEqual(result["by_confidence"]["medium"]["precision"], 0.5)
        self.assertIsNone(result["by_confidence"]["low"]["precision"])
        self.assertNotIn("weighted", result)

    def test_weighting_uses_bridge_shares(self):
        bridge = pd.DataFrame({"match_confidence": ["high"] * 90 + ["medium"] * 8 + ["low"] * 2})
        result = score(_sample(), bridge)
        w = result["weighted"]
        # low has no decided pairs, so only high (0.90) and medium (0.08) carry weight
        self.assertAlmostEqual(w["share_of_bridge_covered_by_decided_strata"], 0.98)
        self.assertAlmostEqual(w["precision"], (0.90 * 1.0 + 0.08 * 0.5) / 0.98)
        self.assertLessEqual(w["normal95"][1], 1.0)

    def test_rejects_unknown_verdict(self):
        bad = _sample()
        bad.loc[0, "audit_verdict"] = "maybe"
        with self.assertRaises(ValueError):
            score(bad)

    def test_report_mentions_unread(self):
        text = format_report(score(_sample()))
        self.assertIn("1 pairs have no verdict yet", text)
        self.assertIn("high:2022_on", text)


class SourceJoinTests(unittest.TestCase):
    def test_attach_and_tenor_check(self):
        sample = _sample()
        sample["trace_issue_date"] = ["2022-01-10", "2022-01-10", "2010-06-01", "", "2009-01-01", "2009-01-01"]
        sample["trace_maturity_date"] = ["2025-01-08", "2025-06-08", "2013-06-01", "2013-01-01", "2012-01-01", "2012-01-01"]
        deals = pd.DataFrame({"deal_url": ["https://example.test/a"], "maturity_scheduled": ["January 2025"],
                              "maturity_date": ["January 2025"], "term_length": [""], "size": ["$100m"],
                              "date_of_issue": ["Jan 2022"], "deal_status": [""], "tranche_structure": ["one tranche"]})
        holdings = pd.DataFrame({"cusip": ["000000AA0", "000000AA0", "000000AB8"], "fund_id": ["f1", "f2", "f1"],
                                 "title": ["A Re 2022-1 Class A", "A RE LTD", "B Re"], "maturity_date": ["2025-01-08", "2025-01-08", ""]})
        out = attach_sources(sample, deals, holdings)
        self.assertEqual(out.loc[0, "dir_maturity_scheduled"], "January 2025")
        self.assertEqual(out.loc[0, "nport_titles"], "A RE LTD | A Re 2022-1 Class A")
        self.assertEqual(out.loc[0, "nport_funds"], "2 funds, 2 filing rows")
        self.assertIn("no registered fund", out.loc[2, "nport_titles"])
        text, warn = tenor_check(out.loc[0])
        self.assertFalse(warn)
        self.assertIn("agrees", text)
        text, warn = tenor_check(out.loc[1])
        self.assertTrue(warn)
        self.assertIn("+5 months", text)
        self.assertTrue(tenor_check(out.loc[3])[1])
        page = render(out)
        self.assertIn("Maturity check", page)
        self.assertNotIn("dir_maturity_scheduled", page.split("<main>")[1].split("</main>")[0].replace('"dir_maturity_scheduled"', ""))


class WorksheetTests(unittest.TestCase):
    def test_every_pair_rendered_and_escaped(self):
        page = render(_sample())
        for sid in "123456":
            self.assertIn('id="card-%s"' % sid, page)
        self.assertIn("C &lt;Re&gt;", page)
        self.assertIn("Export CSV", page)
        self.assertIn('"audit_notes"', page)


if __name__ == "__main__":
    unittest.main()
