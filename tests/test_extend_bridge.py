"""Offline tests for program-level attribution of CUSIPs the strict bridge skips."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from extend_bridge import attribute, family_key, program_key  # noqa: E402


def deal(name, date, suffix):
    return {"issuer_name": name, "deal_url": "https://example.invalid/" + suffix,
            "sponsor": "Test sponsor", "size_text": "$100m", "date_text": date}


def security(cusip, issuer, issue):
    return {"cusip_id": cusip, "issuer_nm": issuer, "trace_issue_date": issue}


class ProgramKeyTests(unittest.TestCase):
    def test_trailing_numerals_are_dropped(self):
        self.assertEqual(program_key("Sector Re V Ltd. (Series 2020-1)", "artemis"), "SECTOR RE")
        self.assertEqual(program_key("SECTOR RE V LTD", "trace"), "SECTOR RE")
        self.assertEqual(program_key("Successor X Ltd. (Series 2011-1)", "artemis"), "SUCCESSOR")

    def test_program_year_is_dropped(self):
        self.assertEqual(program_key("Pioneer 2002 Ltd.", "artemis"), "PIONEER")
        self.assertEqual(program_key("PIONEER 2002 LTD", "trace"), "PIONEER")

    def test_family_key_skips_generic_tokens(self):
        self.assertEqual(family_key("SECTOR RE"), "SECTOR")
        self.assertEqual(family_key("BLUE WINGS"), "WINGS")
        self.assertEqual(family_key("RE"), "")
        self.assertEqual(family_key("EDEN RE"), "")  # four letters is too short to be distinctive


class AttributeTests(unittest.TestCase):
    INDEX = pd.DataFrame([
        deal("Sector Re V Ltd. (Series 2019-1)", "Apr 2019", "sector-2019"),
        deal("Sector Re V Ltd. (Series 2021-1)", "Apr 2021", "sector-2021"),
        deal("Sector Re V Ltd. (Series 2021-2)", "Apr 2021", "sector-2021b"),
        deal("Pioneer 2002 Ltd.", "Jun 2002", "pioneer"),
    ])

    def attribute(self, securities, max_months=24):
        rows = attribute(pd.DataFrame(securities), self.INDEX, max_months)
        return rows.set_index("cusip_id")

    def test_nearest_single_deal_is_attached(self):
        out = self.attribute([security("00000AAA1", "SECTOR RE V LTD", "2019-05-15")])
        row = out.loc["00000AAA1"]
        self.assertEqual(row.level, "program_nearest")
        self.assertTrue(row.deal_url.endswith("sector-2019"))
        self.assertEqual(row.month_distance, 1)
        self.assertEqual(row.match_confidence, "program")

    def test_equally_near_deals_tie_without_choosing(self):
        out = self.attribute([security("00000AAB9", "SECTOR RE V LTD", "2021-04-20")])
        row = out.loc["00000AAB9"]
        self.assertEqual(row.level, "program_tied")
        self.assertEqual(row.deal_url, "")
        self.assertEqual(row.tied_deal_urls.count("|"), 1)

    def test_program_without_deal_in_window(self):
        out = self.attribute([security("00000AAC7", "PIONEER 2002 LTD", "2005-06-15")])
        self.assertEqual(out.loc["00000AAC7"].level, "program_only")
        wide = self.attribute([security("00000AAC7", "PIONEER 2002 LTD", "2005-06-15")],
                              max_months=48)
        self.assertEqual(wide.loc["00000AAC7"].level, "program_nearest")

    def test_program_absent_from_directory(self):
        out = self.attribute([security("00000AAD5", "VITA CAPITAL LTD", "2010-01-15")])
        row = out.loc["00000AAD5"]
        self.assertEqual(row.level, "program_absent")
        self.assertEqual(row.program_deals, 0)
        self.assertEqual(row.match_basis, "")


if __name__ == "__main__":
    unittest.main()
