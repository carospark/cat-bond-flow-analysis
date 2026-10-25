"""Offline tests for the N-PORT puller's listing and screen logic and the parser."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from parse_nport import convention_for, lineages, month_ends, normalise_flow, parse_archive, parse_filing, select_standing, summarize  # noqa: E402
from pull_nport import filing_header, parse_atom_filings, write_screen  # noqa: E402

ATOM = b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><category label="form type" scheme="https://www.sec.gov/" term="NPORT-P" />
<content type="text/xml"><accession-number>0001193125-26-406990</accession-number>
<filing-date>2026-09-29</filing-date></content></entry>
<entry><category label="form type" scheme="https://www.sec.gov/" term="NPORT-P" />
<content type="text/xml"><accession-number>0001193125-26-287701</accession-number>
<filing-date>2026-06-29</filing-date></content></entry>
<entry><category label="form type" scheme="https://www.sec.gov/" term="N-CEN" />
<content type="text/xml"><accession-number>0001193125-26-000001</accession-number>
<filing-date>2026-03-01</filing-date></content></entry>
</feed>"""

XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/nport" xmlns:com="http://www.sec.gov/edgar/common">
<formData>
<genInfo><regName>Test Trust</regName><seriesName>Test Cat Bond Fund</seriesName>
<seriesId>S000000001</seriesId><repPdEnd>2026-10-31</repPdEnd><repPdDate>2026-07-31</repPdDate>
<isFinalFiling>N</isFinalFiling></genInfo>
<fundInfo><totAssets>1100.5</totAssets><totLiabs>100.5</totLiabs><netAssets>1000</netAssets>
<returnInfo><monthlyTotReturns>
<monthlyTotReturn classId="C000000009" rtn1="1.27" rtn2="1.64" rtn3=".97"/>
</monthlyTotReturns>
<mon1Flow sales="42.5" reinvestment=".0" redemption="-92.0"/>
<mon2Flow sales="20" reinvestment="0" redemption="0"/>
<mon3Flow sales="29" reinvestment="1" redemption="N/A"/>
</returnInfo></fundInfo>
<invstOrSecs>
<invstOrSec><name>Aquila Re I Ltd.</name><lei>N/A</lei><title>Aquila Re I 2024-1 A</title>
<cusip>03840AAB1</cusip><identifiers><isin value="USG0384AAB13"/></identifiers>
<balance>250000</balance><units>PA</units><curCd>USD</curCd><valUSD>251000</valUSD>
<pctVal>25.1</pctVal><payoffProfile>Long</payoffProfile><assetCat>ABS-O</assetCat>
<issuerCat>CORP</issuerCat><invCountry>BM</invCountry><isRestrictedSec>Y</isRestrictedSec>
<fairValLevel>2</fairValLevel>
<debtSec><maturityDt>2027-06-07</maturityDt><couponKind>Floating</couponKind>
<annualizedRt>9.25</annualizedRt><isDefault>N</isDefault></debtSec></invstOrSec>
<invstOrSec><name>Cash sweep</name><cusip>N/A</cusip><valUSD>749000</valUSD><pctVal>74.9</pctVal>
<assetCat>STIV</assetCat></invstOrSec>
</invstOrSecs>
</formData></edgarSubmission>"""


class AtomTests(unittest.TestCase):
    def test_parses_accessions_and_dates_and_keeps_form(self):
        entries = parse_atom_filings(ATOM)
        self.assertEqual([e["accession"] for e in entries],
                         ["0001193125-26-406990", "0001193125-26-287701", "0001193125-26-000001"])
        self.assertEqual(entries[0]["filing_date"], "2026-09-29")
        self.assertEqual([e["form"] for e in entries], ["NPORT-P", "NPORT-P", "N-CEN"])


class HeaderTests(unittest.TestCase):
    def test_header_reads_series_and_period(self):
        header = filing_header(XML)
        self.assertEqual(header["series_name"], "Test Cat Bond Fund")
        self.assertEqual(header["series_id"], "S000000001")
        self.assertEqual(header["period_end"], "2026-07-31")
        self.assertEqual(header["registrant"], "Test Trust")


class ScreenTests(unittest.TestCase):
    def test_screen_records_registry_hash_and_identifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp)
            registry_path = raw_root / "registry.json"
            registry_path.write_text("{}", encoding="utf-8")
            funds = [
                {"id": "a", "cik": "0000000001", "series_id": None, "series_name_in_filing": "A"},
                {"id": "b", "cik": "0000000002", "series_id": "S000000002", "series_name_in_filing": "B"},
            ]
            path = write_screen(raw_root, "2026-10-21", funds, registry_path)
            screen = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(screen["registry_sha256"]), 64)
            self.assertEqual([f["edgar_identifier"] for f in screen["funds"]], ["0000000001", "S000000002"])
            self.assertTrue(path.name.startswith("2026-10-21"))


class MonthAlignmentTests(unittest.TestCase):
    def test_month_ends_run_backwards_from_period_end(self):
        self.assertEqual(month_ends("2026-07-31"), ["2026-05-31", "2026-06-30", "2026-07-31"])
        self.assertEqual(month_ends("2026-03-31"), ["2026-01-31", "2026-02-28", "2026-03-31"])
        self.assertEqual(month_ends("2024-02-29"), ["2023-12-31", "2024-01-31", "2024-02-29"])


class ParseFilingTests(unittest.TestCase):
    def setUp(self):
        self.parsed = parse_filing(XML)

    def test_header_numbers(self):
        header = self.parsed["header"]
        self.assertEqual(header["net_assets"], 1000.0)
        self.assertEqual(header["total_assets"], 1100.5)
        self.assertEqual(header["period_end"], "2026-07-31")

    def test_flows_without_a_convention_keep_raw_signs_and_null_the_unexplained(self):
        flows = self.parsed["flows"]
        self.assertEqual([f["month_end"] for f in flows], ["2026-05-31", "2026-06-30", "2026-07-31"])
        # A negative redemption with no documented convention is not flipped.
        self.assertEqual(flows[0]["redemption_raw"], -92.0)
        self.assertIsNone(flows[0]["redemption"])
        self.assertIsNone(flows[0]["net_flow"])
        self.assertEqual(flows[0]["net_flow_basis"], "sign_unexpected_redemption")
        self.assertFalse(flows[0]["sign_flipped"])
        self.assertEqual(flows[1]["net_flow"], 20.0)
        self.assertEqual(flows[1]["net_flow_basis"], "sales_minus_redemption")
        self.assertEqual(flows[1]["flow_flags"], "")
        # "N/A" is a missing component: net flow is null and says why.
        self.assertIsNone(flows[2]["redemption"])
        self.assertIsNone(flows[2]["redemption_raw"])
        self.assertEqual(flows[2]["reinvestment"], 1.0)
        self.assertIsNone(flows[2]["net_flow"])
        self.assertEqual(flows[2]["net_flow_basis"], "redemption_missing")

    def test_documented_convention_flips_only_inside_its_range(self):
        conventions = [{"fund_id": "f", "field": "redemption", "sign": "negative",
                        "from_period_end": "2026-01-31", "to_period_end": "2026-07-31"}]
        flows = parse_filing(XML, "f", conventions)["flows"]
        self.assertEqual(flows[0]["redemption"], 92.0)
        self.assertTrue(flows[0]["sign_flipped"])
        self.assertEqual(flows[0]["flow_flags"], "redemption_sign_flipped")
        self.assertAlmostEqual(flows[0]["net_flow"], 42.5 - 92.0)
        self.assertEqual(flows[0]["redemption_raw"], -92.0)
        # Outside the range nothing is flipped; a different fund is untouched.
        self.assertIsNone(parse_filing(XML, "f", [{**conventions[0], "to_period_end": "2026-04-30"}])["flows"][0]["redemption"])
        self.assertIsNone(parse_filing(XML, "other", conventions)["flows"][0]["redemption"])
        self.assertIsNone(convention_for(conventions, "f", "sales", "2026-07-31"))
        self.assertEqual(convention_for(conventions, "f", "redemption", "2026-07-31"), "negative")

    def test_sign_conflict_and_missing_components_null_net_flow(self):
        conventions = [{"fund_id": "f", "field": "redemption", "sign": "negative",
                        "from_period_end": "2020-01-31", "to_period_end": "2024-01-31"}]
        conflict = normalise_flow({"sales": 10.0, "reinvestment": 0.0, "redemption": 5.0}, "f", "2023-04-30", conventions)
        self.assertIsNone(conflict["redemption"])
        self.assertIsNone(conflict["net_flow"])
        self.assertEqual(conflict["net_flow_basis"], "redemption_sign_conflict")
        self.assertEqual(conflict["redemption_raw"], 5.0)
        zero = normalise_flow({"sales": 10.0, "reinvestment": 0.0, "redemption": 0.0}, "f", "2023-04-30", conventions)
        self.assertEqual((zero["redemption"], zero["net_flow"], zero["sign_flipped"]), (0.0, 10.0, False))
        missing = normalise_flow({"sales": None, "reinvestment": 0.0, "redemption": 3.0}, "f", "2025-01-31", conventions)
        self.assertIsNone(missing["net_flow"])
        self.assertEqual(missing["net_flow_basis"], "sales_missing")
        self.assertEqual(missing["redemption"], 3.0)
        negative_sales = normalise_flow({"sales": -4.0, "reinvestment": -0.5, "redemption": 1.0}, "f", "2025-01-31", conventions)
        self.assertIsNone(negative_sales["sales"])
        self.assertIsNone(negative_sales["reinvestment"])
        self.assertEqual(negative_sales["sales_raw"], -4.0)
        self.assertEqual(negative_sales["net_flow_basis"], "sign_unexpected_sales")
        self.assertEqual(negative_sales["flow_flags"], "sign_unexpected_sales;sign_unexpected_reinvestment")

    def test_returns_per_class_and_month(self):
        returns = self.parsed["returns"]
        self.assertEqual(len(returns), 3)
        self.assertEqual(returns[2], {"class_id": "C000000009", "month_index": 3, "month_end": "2026-07-31", "return_pct": 0.97})

    def test_holdings_fields(self):
        holdings = self.parsed["holdings"]
        self.assertEqual(len(holdings), 2)
        bond = holdings[0]
        self.assertEqual(bond["cusip"], "03840AAB1")
        self.assertEqual(bond["isin"], "USG0384AAB13")
        self.assertEqual(bond["maturity_date"], "2027-06-07")
        self.assertEqual(bond["annualized_rate"], 9.25)
        self.assertEqual(bond["value_usd"], 251000.0)
        self.assertIsNone(bond["lei"])
        self.assertIsNone(holdings[1]["cusip"])
        self.assertIsNone(holdings[1]["maturity_date"])


class ArchiveTests(unittest.TestCase):
    def test_parse_archive_and_summary_with_bridge_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp)
            fund_dir = raw_root / "filings" / "test_fund"
            fund_dir.mkdir(parents=True)
            (fund_dir / "0001-26-000001.xml").write_bytes(XML)
            (fund_dir / "0001-26-000002.xml").write_bytes(XML.replace(b"2026-07-31", b"2026-04-30"))
            (fund_dir / "0001-26-000003.xml").write_bytes(XML)
            (fund_dir / "filings.json").write_text(json.dumps([
                {"accession": "0001-26-000001", "filing_date": "2026-09-29"},
                {"accession": "0001-26-000002", "filing_date": "2026-06-29"},
                {"accession": "0001-26-000003", "filing_date": "2026-09-30", "series_mismatch": True},
            ]), encoding="utf-8")
            conventions = [{"fund_id": "test_fund", "field": "redemption", "sign": "negative",
                            "from_period_end": "2026-01-31", "to_period_end": "2026-07-31"}]
            flows, returns, holdings, filings = parse_archive(raw_root, conventions)
            self.assertEqual(len(flows), 6)
            self.assertEqual(len(returns), 6)
            self.assertEqual(len(holdings), 4)
            self.assertEqual(flows["filing_date"].iloc[0], "2026-09-29")
            self.assertEqual(sorted(flows["month_end"]), ["2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31"])
            bridge = raw_root / "bridge.csv"
            pd.DataFrame({"cusip": ["03840AAB1", "ZZZZZZZZZ"], "deal_url": ["a", "b"]}).to_csv(bridge, index=False)
            summary = summarize(flows, returns, holdings, filings, bridge)
            self.assertEqual(summary["filings_parsed"], 2)
            self.assertEqual(len(summary["filings_skipped"]), 1)
            self.assertEqual(summary["superseded_filings"], [])
            self.assertEqual(summary["distinct_cusips"], 1)
            self.assertEqual(summary["distinct_cusips_in_strict_bridge"], 1)
            self.assertEqual(summary["latest_net_assets"]["test_fund"]["period_end"], "2026-07-31")
            # Month 3 has an N/A redemption in both filings, so two months carry
            # no net flow and the fund total is the other four months.
            self.assertAlmostEqual(summary["net_flow_by_fund"]["test_fund"], 2 * (42.5 - 92.0 + 20.0))
            self.assertEqual(summary["flow_rows_without_net_flow"], {"test_fund": 2})
            self.assertEqual(summary["flow_flags"]["redemption_missing"], 2)

    def test_amendment_supersedes_the_original_for_its_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp)
            fund_dir = raw_root / "filings" / "test_fund"
            fund_dir.mkdir(parents=True)
            original = XML
            amended = XML.replace(b'<netAssets>1000</netAssets>', b'<netAssets>1234</netAssets>').replace(b'sales="20"', b'sales="25"')
            (fund_dir / "0001-26-000001.xml").write_bytes(original)
            (fund_dir / "0001-26-000009.xml").write_bytes(amended)
            (fund_dir / "0001-26-000002.xml").write_bytes(XML.replace(b"2026-07-31", b"2026-04-30"))
            (fund_dir / "filings.json").write_text(json.dumps([
                {"accession": "0001-26-000001", "form": "NPORT-P", "filing_date": "2026-09-29"},
                {"accession": "0001-26-000009", "form": "NPORT-P/A", "filing_date": "2026-10-15"},
                {"accession": "0001-26-000002", "form": "NPORT-P", "filing_date": "2026-06-29"},
            ]), encoding="utf-8")
            flows, returns, holdings, filings = parse_archive(raw_root, [])
            # Two periods, one filing each: the amendment stands for 2026-07-31.
            self.assertEqual(len(flows), 6)
            self.assertEqual(sorted(set(flows["accession"])), ["0001-26-000002", "0001-26-000009"])
            self.assertEqual(sorted(set(holdings["accession"])), ["0001-26-000002", "0001-26-000009"])
            july = flows[(flows["period_end"] == "2026-07-31") & (flows["month_index"] == 2)].iloc[0]
            self.assertEqual(july["sales"], 25.0)
            self.assertEqual(july["form"], "NPORT-P/A")
            self.assertEqual(flows[flows["month_index"] == 3].set_index("period_end")["net_assets_at_period_end"]["2026-07-31"], 1234.0)
            summary = summarize(flows, returns, holdings, filings, None)
            self.assertEqual(summary["filings_parsed"], 2)
            self.assertEqual(summary["superseded_filings"], [{
                "fund_id": "test_fund", "accession": "0001-26-000001", "form": "NPORT-P",
                "filing_date": "2026-09-29", "period_end": "2026-07-31", "superseded_by": "0001-26-000009"}])

    def test_select_standing_prefers_latest_filing_then_amendment(self):
        rows = [
            {"fund_id": "f", "period_end": "2026-07-31", "accession": "a", "filing_date": "2026-09-29", "form": "NPORT-P"},
            {"fund_id": "f", "period_end": "2026-07-31", "accession": "b", "filing_date": "2026-09-29", "form": "NPORT-P/A"},
            {"fund_id": "f", "period_end": "2026-04-30", "accession": "c", "filing_date": "2026-06-29", "form": "NPORT-P"},
            {"fund_id": "g", "period_end": "2026-07-31", "accession": "d", "filing_date": "2026-09-01", "form": "NPORT-P"},
        ]
        self.assertEqual(select_standing(rows), {"a": "b", "b": None, "c": None, "d": None})

    def test_lineages_follow_successor_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps({"sec_registered": [
                {"id": "old", "successor_id": "new"}, {"id": "new"}, {"id": "solo"}]}))
            self.assertEqual(lineages(path), {"old": "new", "new": "new", "solo": "solo"})


if __name__ == "__main__":
    unittest.main()
