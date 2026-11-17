"""Offline tests for program-level attribution of CUSIPs the strict bridge skips."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from extend_bridge import (  # noqa: E402
    attribute,
    deal_maturities,
    family_key,
    program_key,
    split_by_title,
    split_ties,
)


def deal(name, date, suffix):
    return {"issuer_name": name, "deal_url": "https://example.invalid/" + suffix,
            "sponsor": "Test sponsor", "size_text": "$100m", "date_text": date}


def security(cusip, issuer, issue):
    return {"cusip_id": cusip, "issuer_nm": issuer, "trace_issue_date": issue}


class TitleSplitTests(unittest.TestCase):
    def tied(self, cusip, *slugs):
        return {"cusip_id": cusip, "level": "program_tied", "deal_url": "",
                "tied_deal_urls": "|".join("https://example.invalid/" + s for s in slugs)}

    def test_title_naming_one_tied_deal_resolves_it(self):
        result = pd.DataFrame([
            self.tied("00000AAA1", "kilimanjaro-iii-re-ltd-series-2019-1", "kilimanjaro-iii-re-ltd-series-2019-2"),
            self.tied("00000AAB9", "kilimanjaro-iii-re-ltd-series-2019-1", "kilimanjaro-iii-re-ltd-series-2019-2"),
            self.tied("00000AAC7", "merna-re-ii-ltd-series-2022-2", "merna-re-ii-ltd-series-2022-3"),
            {"cusip_id": "00000AAD5", "level": "program_nearest", "deal_url": "https://example.invalid/x", "tied_deal_urls": ""},
        ])
        out = split_by_title(result, {"00000AAA1": "2019-1", "00000AAC7": "2022-9", "00000AAD5": "2020-1"}).set_index("cusip_id")
        self.assertEqual(out.loc["00000AAA1", "level"], "program_nport_title")
        self.assertTrue(out.loc["00000AAA1", "deal_url"].endswith("series-2019-1"))
        self.assertEqual(out.loc["00000AAA1", "tied_deal_urls"], "")
        self.assertIn("names kilimanjaro-iii-re-ltd-series-2019-1", out.loc["00000AAA1", "title_evidence"])
        self.assertEqual(out.loc["00000AAB9", "level"], "program_tied")  # no title
        self.assertEqual(out.loc["00000AAC7", "level"], "program_tied")
        self.assertIn("names none", out.loc["00000AAC7", "title_evidence"])
        self.assertEqual(out.loc["00000AAD5", "level"], "program_nearest")  # untouched

    def test_series_number_formats_compare_equal(self):
        result = pd.DataFrame([self.tied("00000AAE3", "phoenician-re-ltd-series-2020-01", "phoenician-re-ltd-series-2020-02")])
        out = split_by_title(result, {"00000AAE3": "2020-2"}).set_index("cusip_id")
        self.assertEqual(out.loc["00000AAE3", "level"], "program_nport_title")


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


class MaturitySplitTests(unittest.TestCase):
    INDEX = pd.DataFrame([
        deal("Twin Re Ltd. (Series 2021-1)", "Apr 2021", "twin-2021-1"),
        deal("Twin Re Ltd. (Series 2021-2)", "Apr 2021", "twin-2021-2"),
        deal("Blank Re Ltd. (Series 2020-1)", "Jan 2020", "blank-1"),
        deal("Blank Re Ltd. (Series 2020-2)", "Jan 2020", "blank-2"),
    ])
    DEALS = pd.DataFrame([
        {"deal_url": "https://example.invalid/twin-2021-1", "maturity_scheduled": "April 2025",
         "maturity_date": "", "maturity_date_derived": ""},
        {"deal_url": "https://example.invalid/twin-2021-2", "maturity_scheduled": "",
         "maturity_date": "Apr 2026", "maturity_date_derived": "Apr 2026"},
        {"deal_url": "https://example.invalid/blank-1", "maturity_scheduled": "Jan 2023",
         "maturity_date": "", "maturity_date_derived": ""},
        {"deal_url": "https://example.invalid/blank-2", "maturity_scheduled": "",
         "maturity_date": "", "maturity_date_derived": ""},
    ])

    def run_split(self, securities, tolerance=1):
        sec = pd.DataFrame(securities)
        tied = attribute(sec, self.INDEX, 24)
        self.assertTrue(tied.level.eq("program_tied").all())
        out = split_ties(tied, sec, deal_maturities(self.DEALS), tolerance)
        return out.set_index("cusip_id")

    def test_maturity_fields_are_read_in_preference_order(self):
        maturities = deal_maturities(self.DEALS)
        self.assertEqual(maturities["https://example.invalid/twin-2021-1"], (2025 * 12 + 4, "maturity_scheduled"))
        self.assertEqual(maturities["https://example.invalid/twin-2021-2"], (2026 * 12 + 4, "maturity_date"))
        self.assertNotIn("https://example.invalid/blank-2", maturities)

    def test_twins_split_by_stated_maturity(self):
        out = self.run_split([
            {**security("00000TA10", "TWIN RE LTD", "2021-04-05"), "trace_maturity_date": "2025-04-21"},
            {**security("00000TA28", "TWIN RE LTD", "2021-04-05"), "trace_maturity_date": "2026-05-20"},
        ])
        self.assertEqual(out.loc["00000TA10"].level, "program_maturity_split")
        self.assertTrue(out.loc["00000TA10"].deal_url.endswith("twin-2021-1"))
        self.assertEqual(out.loc["00000TA10"].tied_deal_urls, "")
        self.assertIn("maturity_scheduled", out.loc["00000TA10"].maturity_evidence)
        # One month off is within tolerance; the other twin is twelve months away.
        self.assertTrue(out.loc["00000TA28"].deal_url.endswith("twin-2021-2"))

    def test_maturity_between_twins_stays_tied(self):
        out = self.run_split([
            {**security("00000TA36", "TWIN RE LTD", "2021-04-05"), "trace_maturity_date": "2025-10-21"},
        ])
        self.assertEqual(out.loc["00000TA36"].level, "program_tied")
        self.assertIn("0 tied deals within 1 months", out.loc["00000TA36"].maturity_evidence)
        wide = self.run_split([
            {**security("00000TA36", "TWIN RE LTD", "2021-04-05"), "trace_maturity_date": "2025-10-21"},
        ], tolerance=6)
        self.assertEqual(wide.loc["00000TA36"].level, "program_tied")
        self.assertIn("2 tied deals within 6 months", wide.loc["00000TA36"].maturity_evidence)

    def test_unstated_maturity_blocks_the_split(self):
        out = self.run_split([
            {**security("00000TB18", "BLANK RE LTD", "2020-01-05"), "trace_maturity_date": "2023-01-15"},
            {**security("00000TB26", "BLANK RE LTD", "2020-01-05"), "trace_maturity_date": ""},
        ])
        self.assertEqual(out.loc["00000TB18"].level, "program_tied")
        self.assertEqual(out.loc["00000TB18"].maturity_evidence, "1 of 2 tied deals state no maturity")
        self.assertEqual(out.loc["00000TB26"].maturity_evidence, "TRACE maturity is blank")


if __name__ == "__main__":
    unittest.main()


class TitleCheckTests(unittest.TestCase):
    """Holders' titles re-point, resolve, confirm or flag program rows."""

    INDEX = pd.DataFrame([
        deal("Montoya Re Ltd. (Series 2022-2)", "Dec 2022", "montoya-re-ltd-series-2022-2"),
        deal("Queen Street 2023 Re dac", "May 2023", "queen-street-2023-re-dac"),
        deal("Merna Reinsurance II Ltd.", "Apr 2013", "merna-reinsurance-ii-ltd"),
        deal("Merna Re II Ltd. (Series 2022-2)", "Jun 2022", "merna-re-ii-ltd-series-2022-2"),
        deal("Merna Re II Ltd. (Series 2022-3)", "Jun 2022", "merna-re-ii-ltd-series-2022-3"),
        deal("Acorn Re Ltd. (Series 2021-1)", "Jun 2021", "acorn-re-ltd-series-2021-1"),
        deal("Acorn Re Ltd. (Series 2023-1)", "Jun 2023", "acorn-re-ltd-series-2023-1"),
    ])

    @staticmethod
    def row(cusip, level, issue, slug="", tied=()):
        return {"cusip_id": cusip, "level": level, "trace_issue_date": issue,
                "deal_url": "https://example.invalid/" + slug if slug else "",
                "tied_deal_urls": "|".join("https://example.invalid/" + s for s in tied),
                "artemis_issuer_name": "", "artemis_date_text": "", "month_distance": ""}

    def test_title_issuer_key(self):
        from extend_bridge import title_issuer_key
        self.assertEqual(title_issuer_key("Queen Street 2023 Re DAC"), ("QUEEN STREET 2023 RE", ""))
        self.assertEqual(title_issuer_key("Kilimanjaro III Re 2019-1 Class A-1"), ("KILIMANJARO III RE", "2019-1"))
        self.assertEqual(title_issuer_key("Residential Re 2024-II Class 2")[0], "RESIDENTIAL RE")
        self.assertEqual(title_issuer_key("CAPE LOOKOUT RE LTD REGD V/R 144A P/P SER A 3.26520900")[0], "CAPE LOOKOUT RE")

    def test_repoint_resolve_confirm_and_flag(self):
        from extend_bridge import check_titles
        result = pd.DataFrame([
            self.row("747977AA4", "program_nearest", "2023-05-11", "montoya-re-ltd-series-2022-2"),
            self.row("59013MAG7", "program_tied", "2022-06-07",
                     tied=("merna-re-ii-ltd-series-2022-2", "merna-re-ii-ltd-series-2022-3")),
            self.row("00485YAD1", "program_nearest", "2023-06-15", "acorn-re-ltd-series-2023-1"),
            self.row("00485YAE9", "program_nearest", "2023-06-15", "acorn-re-ltd-series-2023-1"),
            self.row("27954GAB9", "program_absent", "2019-01-10"),
            self.row("27954GAC7", "program_nearest", "2019-01-10", "acorn-re-ltd-series-2021-1"),
            self.row("00000AAZ9", "program_nearest", "2021-06-01", "acorn-re-ltd-series-2021-1"),
        ])
        titles = {
            "747977AA4": ["Queen Street 2023 RE DAC", "Queen Street 2023 Re DAC"],
            "59013MAG7": ["Merna Reinsurance II Ltd"],
            "00485YAD1": ["ACORN RE LTD", "Acorn Re 2023-1 Class A"],
            "00485YAE9": ["Acorn Re 2021-1 Class A"],
            "27954GAB9": ["Eden Re II"],
            "27954GAC7": ["Eden Re II"],
        }
        out = check_titles(result, self.INDEX, titles, max_months=3).set_index("cusip_id")
        # same issue month as the named deal, different issuer entity: re-pointed
        self.assertEqual(out.loc["747977AA4", "level"], "program_nport_title_repointed")
        self.assertTrue(out.loc["747977AA4", "deal_url"].endswith("queen-street-2023-re-dac"))
        self.assertEqual(out.loc["747977AA4", "artemis_date_text"], "May 2023")
        self.assertIn("was program_nearest montoya-re-ltd-series-2022-2", out.loc["747977AA4", "title_evidence"])
        self.assertEqual(out.loc["747977AA4", "title_conflict"], "")
        # a tie whose titles name a deal nine years away: kept tied, flagged
        self.assertEqual(out.loc["59013MAG7", "level"], "program_tied")
        self.assertEqual(out.loc["59013MAG7", "title_conflict"], "title_names_deal_outside_date_window")
        # one title names the series, one only the issuer: intersection confirms
        self.assertEqual(out.loc["00485YAD1", "level"], "program_nearest")
        self.assertIn("confirms acorn-re-ltd-series-2023-1", out.loc["00485YAD1", "title_evidence"])
        # title names the sibling series two years earlier: outside window, flagged not moved
        self.assertEqual(out.loc["00485YAE9", "level"], "program_nearest")
        self.assertEqual(out.loc["00485YAE9", "title_conflict"], "title_names_deal_outside_date_window")
        # issuer absent from the directory: absent row just annotated, attached row flagged
        self.assertIn("not in directory", out.loc["27954GAB9", "title_evidence"])
        self.assertEqual(out.loc["27954GAB9", "title_conflict"], "")
        self.assertEqual(out.loc["27954GAC7", "title_conflict"], "title_issuer_not_in_directory")
        self.assertEqual(out.loc["27954GAC7", "level"], "program_nearest")
        # no titles: untouched
        self.assertEqual(out.loc["00000AAZ9", "title_evidence"], "")

    def test_tie_resolved_by_issuer_only_title_within_window(self):
        from extend_bridge import check_titles
        index = pd.concat([self.INDEX, pd.DataFrame([deal("Lion Re Ltd.", "Jun 2022", "lion-re-ltd")])])
        result = pd.DataFrame([self.row("00000AAY1", "program_tied", "2022-06-10",
                                        tied=("lion-re-ltd", "merna-re-ii-ltd-series-2022-2"))])
        out = check_titles(result, index, {"00000AAY1": ["Lion Re Ltd Class A"]}).set_index("cusip_id")
        self.assertEqual(out.loc["00000AAY1", "level"], "program_nport_title")
        self.assertTrue(out.loc["00000AAY1", "deal_url"].endswith("lion-re-ltd"))

    def test_no_titles_leaves_frame_unchanged(self):
        from extend_bridge import check_titles
        result = pd.DataFrame([self.row("00000AAX3", "program_nearest", "2023-05-11", "montoya-re-ltd-series-2022-2")])
        out = check_titles(result, self.INDEX, {})
        self.assertEqual(out.loc[0, "level"], "program_nearest")
        self.assertIn("title_conflict", out.columns)
