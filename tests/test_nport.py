"""Offline tests for the N-PORT puller's listing and screen logic and the parser."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from parse_nport import month_ends, parse_archive, parse_filing, summarize  # noqa: E402
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

    def test_flows_align_to_months_and_net_flow_excludes_reinvestment(self):
        flows = self.parsed["flows"]
        self.assertEqual([f["month_end"] for f in flows], ["2026-05-31", "2026-06-30", "2026-07-31"])
        self.assertAlmostEqual(flows[0]["net_flow"], 42.5 - 92.0)
        self.assertEqual(flows[0]["redemption"], 92.0)
        self.assertTrue(flows[0]["sign_flipped"])
        self.assertFalse(flows[1]["sign_flipped"])
        self.assertEqual(flows[1]["net_flow"], 20.0)
        self.assertIsNone(flows[2]["redemption"])
        self.assertEqual(flows[2]["reinvestment"], 1.0)
        self.assertEqual(flows[2]["net_flow"], 29.0)

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
            flows, returns, holdings, filings = parse_archive(raw_root)
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
            self.assertEqual(summary["distinct_cusips"], 1)
            self.assertEqual(summary["distinct_cusips_in_strict_bridge"], 1)
            self.assertEqual(summary["latest_net_assets"]["test_fund"]["period_end"], "2026-07-31")
            self.assertAlmostEqual(summary["net_flow_by_fund"]["test_fund"], 2 * (42.5 - 92.0 + 20.0 + 29.0))


if __name__ == "__main__":
    unittest.main()
