"""Offline tests for the atlas tables: universe rule, sponsor types, layer
bands, the coverage columns, fund lineages and the mark table."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_atlas import (  # noqa: E402
    ap_band, classify_segment, classify_sponsor, fund_flows_table, guidance_mid, hazard_classes, layer_coverage_table,
    layer_table, lineage_of, marks_table, pct_to_float, peril_table, review_lists, universe_table, usd_millions, _by_year,
)


def _deals():
    return pd.DataFrame({
        "deal_slug": ["a", "b", "c", "d", "e", "f", "g"],
        "deal_url": ["u/a", "u/b", "u/c", "u/d", "u/e", "u/f", "u/g"],
        "deal_name": ["Alpha Re Ltd.", "Bellemeade Re 2018-1 Ltd.", "Vita Capital", "Lite Re", "Cairney",
                      "Mythen Re (Series 2012-2)", "Unsized Re"],
        "date_of_issue": ["Jan 2020", "Mar 2018", "Jun 2020", "Jul 2020", "Jan 2023", "Nov 2012", "May 2020"],
        "perils_covered": ["U.S. hurricane", "U.S. earthquake", "Extreme mortality", "Unknown property catastrophe risks",
                           "Cyber risks", "U.S. hurricane, UK extreme mortality", "U.S. hurricane"],
        "deal_is_private": ["", "", "", "True", "", "", ""],
        "cedent_sponsor": ["USAA", "Arch Capital Group Ltd.", "Swiss Re", "", "Beazley", "Swiss Re", "Alphabet Inc."],
        "trigger_type": ["Indemnity", "Indemnity", "Parametric index", "", "Indemnity", "Industry loss index", "Indemnity"],
        "size": ["$200m", "$500m", "€100m ($120m)", "$25m", "$140 million", "$100m", ""],
        "deal_status": ["issued"] * 7,
    })


class ParsersTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(pct_to_float("1.21%"), 1.21)
        self.assertIsNone(pct_to_float(""))
        self.assertEqual(guidance_mid("9.75% to 10.5%"), 10.125)
        self.assertEqual(guidance_mid("8%"), 8.0)
        self.assertEqual(usd_millions("$200m"), (200.0, "usd"))
        self.assertEqual(usd_millions("$1.5bn"), (1500.0, "usd"))
        self.assertEqual(usd_millions("€100m ($120m)"), (120.0, "usd_equiv"))
        self.assertEqual(usd_millions("€100m"), (None, "non_usd_unconverted"))
        self.assertEqual(usd_millions("$473.18"), (None, "unit_missing"))
        self.assertEqual(usd_millions(""), (None, "missing"))

    def test_segments(self):
        self.assertEqual(classify_segment("U.S. hurricane", "Alpha Re", ""), ("core_property_cat", False))
        self.assertEqual(classify_segment("U.S. earthquake", "Bellemeade Re 2018-1 Ltd.", ""), ("mortgage", False))
        self.assertEqual(classify_segment("Mortgage insurance risks", "X", ""), ("mortgage", False))
        self.assertEqual(classify_segment("Extreme mortality", "Vita", ""), ("life_health", False))
        self.assertEqual(classify_segment("Cyber risks", "Cairney", ""), ("cyber", False))
        self.assertEqual(classify_segment("Lottery jackpot risk", "X", ""), ("other_specialty", False))
        self.assertEqual(classify_segment("Unknown property catastrophe risks", "X", "True"), ("private_lite", False))
        self.assertEqual(classify_segment("U.S. hurricane, UK extreme mortality", "X", ""), ("core_property_cat", True))
        self.assertEqual(classify_segment("U.S. hurricane, UK extreme mortality", "X", "True"), ("private_lite", True))
        self.assertEqual(classify_segment("Life reinsurance", "L1 - Securitization", ""), ("life_health", False))
        for text in ("Credit reinsurance", "Financial guarantee risks", "Event cancellation risk", "Casualty losses",
                     "Temperature risks"):
            self.assertEqual(classify_segment(text, "X", ""), ("other_specialty", False), text)
        self.assertEqual(classify_segment("Multi peril - U.S. & Canada", "X", ""), ("core_property_cat", False))

    def test_sponsor_types(self):
        self.assertEqual(classify_sponsor("USAA"), "insurer")
        self.assertEqual(classify_sponsor("Swiss Re"), "reinsurer")
        self.assertEqual(classify_sponsor("California Earthquake Authority"), "public_sector")
        self.assertEqual(classify_sponsor("Government of Jamaica"), "public_sector")
        self.assertEqual(classify_sponsor("National Mortgage Insurance Corporation"), "insurer")
        self.assertEqual(classify_sponsor("Alphabet Inc."), "corporate_other")
        self.assertEqual(classify_sponsor(""), "unknown")
        self.assertEqual(classify_sponsor("", "True"), "undisclosed")
        self.assertEqual(classify_sponsor("Gothaer Allgemeine Versicherungs AG"), "insurer")
        self.assertEqual(classify_sponsor("PICC Property and Casualty Company Limited"), "insurer")
        self.assertEqual(classify_sponsor("PURE"), "insurer")
        self.assertEqual(classify_sponsor("GAREAT"), "public_sector")
        self.assertEqual(classify_sponsor("Asian Development Bank"), "public_sector")
        self.assertEqual(classify_sponsor("Pandemic Emergency Financing Facility (PEF)"), "public_sector")

    def test_bands(self):
        self.assertEqual(ap_band(0.5), "ap_lt_1")
        self.assertEqual(ap_band(1.0), "ap_1_2")
        self.assertEqual(ap_band(3.99), "ap_2_4")
        self.assertEqual(ap_band(8.0), "ap_8_plus")
        self.assertEqual(ap_band(None), "ap_unknown")
        self.assertEqual(ap_band(1.5, "el"), "el_1_2")
        self.assertEqual(ap_band(None, "el"), "el_unknown")


class TableTests(unittest.TestCase):
    def test_universe_and_by_year_coverage(self):
        u = universe_table(_deals())
        self.assertEqual(u["segment"].tolist(), ["core_property_cat", "mortgage", "life_health", "private_lite",
                                                 "cyber", "core_property_cat", "core_property_cat"])
        self.assertEqual(u["size_basis"].tolist()[2], "usd_equiv")
        by = _by_year(u, "segment")
        row = by[(by.issue_year == 2020) & (by.segment == "core_property_cat")].iloc[0]
        self.assertEqual((row.deals, row.deals_sized, row.issued_usd_m), (2, 1, 200.0))
        self.assertEqual(row.year_deals, 4)
        self.assertAlmostEqual(row.share_of_year_deals, 0.5)

    def test_peril_split(self):
        deals = _deals()
        deals.loc[0, "perils_covered"] = "U.S. hurricane, severe thunderstorm"
        deals.loc[6, "perils_covered"] = "Unknown property catastrophe risks"
        u = universe_table(deals)
        self.assertEqual(hazard_classes("U.S. hurricane, severe thunderstorm"), ["hurricane_or_named_storm", "severe_convective_storm"])
        self.assertEqual(hazard_classes("Unknown property catastrophe risks"), [])
        self.assertEqual(hazard_classes("Multi peril - U.S. & Canada"), ["multi_peril_unspecified"])
        self.assertEqual(hazard_classes("Worldwide all perils incl. marine & aviation"), ["multi_peril_unspecified"])
        self.assertEqual(hazard_classes("U.S. multi-peril including hurricane"), ["hurricane_or_named_storm"])
        p = peril_table(u)
        a_rows = p[p.issue_year == 2020]
        self.assertEqual(set(a_rows.hazard_class), {"hurricane_or_named_storm", "severe_convective_storm", "unmapped"})
        hurr = a_rows[a_rows.hazard_class == "hurricane_or_named_storm"].iloc[0]
        self.assertEqual(hurr.issued_usd_m_split, 100.0)
        self.assertEqual(hurr.deals_multi, 1)
        self.assertEqual(a_rows[a_rows.hazard_class == "unmapped"].iloc[0].deals, 1)
        self.assertEqual(p[p.issue_year == 2012].iloc[0].hazard_class, "hurricane_or_named_storm")

    def test_review_lists(self):
        deals = _deals()
        deals.loc[6, "perils_covered"] = "Global peak perils"
        u = universe_table(deals)
        u["hazard_classes"] = u["perils_covered"].map(lambda t: "|".join(hazard_classes(t)))
        r = review_lists(u)
        self.assertEqual(r["review_sponsor_type"]["deal_slug"].tolist(), ["g"])  # d is private: undisclosed, not listed
        self.assertEqual(u.loc[u.deal_slug.eq("d"), "sponsor_type"].iloc[0], "undisclosed")
        self.assertEqual(r["review_hazard_class"]["deal_slug"].tolist(), ["g"])
        self.assertEqual(r["review_hazard_class"]["hazard_classes"].iloc[0], "multi_peril_unspecified")
        self.assertTrue((r["review_sponsor_type"]["review"] == "").all())

    def test_layers(self):
        u = universe_table(_deals())
        t = pd.DataFrame({
            "deal_slug": ["a", "a", "b", "f"], "date_text": ["Jan 2020", "Jan 2020", "Mar 2018", "Nov 2012"],
            "tranche_id": ["Class A", "Class B", "Class M-1", "Class A"],
            "expected_loss": ["1.0%", "3.0%", "", "2.0%"], "attachment_probability": ["1.5%", "4.5%", "", "2.5%"],
            "spread_risk_margin": ["6%", "10%", "", ""], "price_guidance": ["5.5% to 6.5%", "", "", "7%"],
            "tranche_size_final": ["$100m", "$300m", "$400m", "€50m"],
        })
        el = layer_table(t, u, band_on="el")
        el2020 = el[(el.segment == "core_property_cat") & (el.issue_year == 2020)]
        self.assertEqual(set(el2020.band), {"el_1_2", "el_2_4"})
        self.assertEqual(int(el2020[el2020.band == "el_2_4"].iloc[0].n_spread), 1)
        cov = layer_coverage_table(t, u)
        c2020 = cov[(cov.segment == "core_property_cat") & (cov.issue_year == 2020)].iloc[0]
        self.assertEqual((c2020.tranches, c2020.n_el, c2020.n_ap, c2020.n_both, c2020.n_el_spread), (2, 2, 2, 2, 2))
        self.assertEqual((c2020.issued_usd_m, c2020.usd_with_el), (400.0, 400.0))
        c2012 = cov[cov.issue_year == 2012].iloc[0]
        self.assertEqual((c2012.n_el, c2012.n_ap, c2012.n_el_spread), (1, 1, 0))
        self.assertTrue(pd.isna(c2012.share_usd_with_el))  # euro size, not weighted
        out = layer_table(t, u)
        core2020 = out[(out.segment == "core_property_cat") & (out.issue_year == 2020)]
        self.assertEqual(set(core2020.band), {"ap_1_2", "ap_4_8"})
        a = core2020[core2020.band == "ap_1_2"].iloc[0]
        self.assertEqual((a.tranches, a.n_spread, a.n_guidance, a.median_guidance_mid), (1, 1, 1, 6.0))
        self.assertEqual(a.year_tranches, 2)
        unknown = out[(out.issue_year == 2018)].iloc[0]
        self.assertEqual((unknown.band, unknown.n_ap, unknown.n_sized_usd), ("ap_unknown", 0, 1))
        f = out[out.issue_year == 2012].iloc[0]
        self.assertEqual(f.n_sized_usd, 0)
        self.assertTrue(pd.isna(f.size_weighted_spread))

    def test_fund_lineage_and_nulls(self):
        registry = {"sec_registered": [
            {"id": "old", "successor_id": "new"}, {"id": "new"}, {"id": "etf"}]}
        self.assertEqual(lineage_of("old", registry), "new")
        self.assertEqual(lineage_of("etf", registry), "etf")
        flows = pd.DataFrame({
            "fund_id": ["old", "new", "etf", "etf"], "month_end": ["2022-09-30", "2022-09-30", "2022-09-30", "2022-10-31"],
            "net_flow": ["10", "5", "", "3"], "net_flow_basis": ["sales_minus_redemption"] * 2 + ["unexplained_sign", "sales_minus_redemption"],
            "net_assets_at_period_end": ["100", "", "50", "60"],
        })
        out = fund_flows_table(flows, registry)
        new = out[(out.lineage == "new") & (out.month == "2022-09")].iloc[0]
        self.assertEqual((new.funds, new.net_flow_usd, new.event_window), (2, 15.0, "ian"))
        etf_sep = out[(out.lineage == "etf") & (out.month == "2022-09")].iloc[0]
        self.assertTrue(pd.isna(etf_sep.net_flow_usd))
        self.assertEqual(etf_sep.months_null, 1)
        self.assertEqual(out[(out.lineage == "etf") & (out.month == "2022-10")].iloc[0].event_window, "ian")

    def test_marks(self):
        marks = pd.DataFrame({"cusip": ["x", "y", "z"], "period_end": ["2024-03-31", "2024-03-31", "2024-06-30"],
                              "diff_points_both": ["1.0", "-7.0", ""], "stale": ["False", "True", "False"]})
        out = marks_table(marks)
        q1 = out[out.quarter == "2024-03"].iloc[0]
        self.assertEqual((q1.pairs, q1.pairs_with_trace, q1.median_abs_gap, q1.share_abs_gap_over_5, q1.share_stale), (2, 2, 4.0, 0.5, 0.5))
        self.assertEqual(out[out.quarter == "2024-06"].iloc[0].pairs_with_trace, 0)


if __name__ == "__main__":
    unittest.main()
