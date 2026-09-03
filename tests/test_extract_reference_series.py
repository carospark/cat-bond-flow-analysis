import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from extract_reference_series import extract_aon, extract_gc, extract_lane  # noqa: E402


class ReferenceExtractionTests(unittest.TestCase):
    def test_priority_pdf_extractions(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            aon = extract_aon(output)
            gc = extract_gc(output)
            lane = extract_lane(output)
            self.assertEqual(aon["annual_rows"], 16)
            self.assertEqual(aon["tranche_rows"], 128)
            self.assertEqual(aon["missing_initial_spread_rows"], 4)
            self.assertEqual(gc["rows"], 27)
            self.assertEqual(lane["tranche_total"], 977)
            self.assertEqual(lane["issuer_total_usd_mn"], 137622)


if __name__ == "__main__":
    unittest.main()
