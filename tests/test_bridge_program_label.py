"""Offline test: a sub-programme label in the directory name ("Matterhorn Re
Ltd. (Argon 2022-1)") is matched against the holders' N-PORT titles, so a
title naming the label outranks the unlabelled twin that states the same
series and sits one month closer."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_bridge import _label_in_title, match_frames, program_label  # noqa: E402


def security(cusip, issuer, issue, maturity):
    return {
        "cusip_id": cusip, "issuer_nm": issuer, "issuer_variants": issuer,
        "scrty_ds": "Unsecured Insurance Linked Security", "trace_debt_type_codes": "",
        "trace_ever_un_cat": True, "trace_history_rows": 1, "trace_issue_date": issue,
        "trace_last_end_date": issue, "trace_maturity_date": maturity, "trace_coupon_min": 5.0,
        "trace_coupon_max": 5.0, "trace_coupon_observation_count": 1, "issuer_name_source": "master",
        "trace_usable_coupon_min": 5.0, "trace_usable_coupon_max": 5.0, "trace_usable_coupon_observation_count": 1,
    }


def deal(name, date, suffix):
    return {"issuer_name": name, "deal_url": "https://example.invalid/" + suffix,
            "sponsor": "Test sponsor", "size_text": "$100m", "date_text": date}


MATTERHORN = pd.DataFrame([
    deal("Matterhorn Re Ltd. (Series 2022-1)", "Mar 2022", "matterhorn-series-2022-1"),
    deal("Matterhorn Re Ltd. (Argon 2022-1)", "Apr 2022", "matterhorn-argon-2022-1"),
])
ARGON_NOTE = pd.DataFrame([security("577092AR0", "MATTERHORN RE LTD", "2022-03-31", "2027-01-25")])
SERIES_NOTE = pd.DataFrame([security("577092AP4", "MATTERHORN RE LTD", "2022-03-10", "2025-03-24")])


class ProgramLabelTests(unittest.TestCase):
    def test_label_extraction(self):
        self.assertEqual(program_label("Matterhorn Re Ltd. (Argon 2022-1)"), ("ARGON",))
        self.assertEqual(program_label("London Bridge 2 PCC Limited (Fuchsia 2 – 2024-1)"), ("FUCHSIA", "2"))
        self.assertEqual(program_label("Sailfish Re Ltd. (Koi Re – Series 2025-1)"), ("KOI", "RE"))
        self.assertEqual(program_label("Everglades Re II Ltd. (Series 2023-1 & 2023-2)"), ())
        self.assertEqual(program_label("Citrus Re Ltd. (Series 2016-1)"), ())
        self.assertEqual(program_label("Gator Re Ltd."), ())

    def test_label_in_title(self):
        self.assertTrue(_label_in_title(("ARGON",), "Matterhorn Re Argon 2022-1 Class A"))
        self.assertFalse(_label_in_title(("ARGON",), "Matterhorn Re Ltd SR2022-1 Class B"))
        self.assertTrue(_label_in_title(("FUCHSIA", "2"), "London Bridge 2 PCC Fuchsia 2 2024-1"))
        self.assertFalse(_label_in_title(("FUCHSIA", "3"), "London Bridge 2 PCC Fuchsia 2 2024-1"))
        self.assertFalse(_label_in_title((), "anything"))

    def test_without_titles_the_closer_month_wins(self):
        bridge, _, _ = match_frames(MATTERHORN, ARGON_NOTE)
        self.assertEqual(len(bridge), 1)
        self.assertTrue(bridge.iloc[0].deal_url.endswith("series-2022-1"))

    def test_title_naming_the_label_repoints_the_match(self):
        bridge, _, _ = match_frames(MATTERHORN, ARGON_NOTE, {"577092AR0": "2022-1"},
                                    {"577092AR0": "Matterhorn Re Argon 2022-1 Class A"})
        self.assertEqual(len(bridge), 1)
        row = bridge.iloc[0]
        self.assertTrue(row.deal_url.endswith("argon-2022-1"))
        self.assertIn("nport_title_label", row.match_method)
        self.assertIn("programme label 'ARGON'", row.series_evidence)

    def test_title_without_the_label_leaves_the_series_deal(self):
        bridge, _, _ = match_frames(MATTERHORN, SERIES_NOTE, {"577092AP4": "2022-1"},
                                    {"577092AP4": "Matterhorn Re Ltd SR2022-1 Class A | Matterhorn Re Ltd"})
        self.assertEqual(len(bridge), 1)
        self.assertTrue(bridge.iloc[0].deal_url.endswith("series-2022-1"))
        self.assertNotIn("nport_title_label", bridge.iloc[0].match_method)


if __name__ == "__main__":
    unittest.main()
