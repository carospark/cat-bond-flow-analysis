"""Offline tests for the fund registry loader and its validation rules."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fund_registry import (  # noqa: E402
    REGISTRY_PATH,
    load_registry,
    registry_sha256,
    sec_funds,
    validate_registry,
)


def _fund(**overrides):
    base = {
        "id": "x",
        "fund_name": "X Fund",
        "registrant": "X Trust",
        "cik": "0000000001",
        "series_id": None,
        "series_name_in_filing": "X Fund",
        "structure": "open-end",
        "role": "fund",
        "status": "active",
        "evidence": "test",
    }
    base.update(overrides)
    return base


class CheckedInRegistryTests(unittest.TestCase):
    def test_loads_and_validates(self):
        registry = load_registry(REGISTRY_PATH)
        self.assertEqual(registry["schema_version"], 1)
        funds = sec_funds(registry)
        ids = {fund["id"] for fund in funds}
        self.assertIn("stone_ridge_reinsurance_rrp_interval", ids)
        self.assertIn("pioneer_ils_interval", ids)
        self.assertIn("brookmont_catastrophic_bond_etf", ids)
        self.assertNotIn("sterling_capital_funds", ids)
        self.assertNotIn("stone_ridge_reinsurance_rrp_open_end", ids)

    def test_every_fund_entry_has_a_cik_and_evidence(self):
        registry = load_registry(REGISTRY_PATH)
        for entry in registry["sec_registered"]:
            if entry["role"] == "fund":
                self.assertRegex(entry["cik"], r"^\d{10}$", entry["id"])
                self.assertTrue(entry["evidence"].strip(), entry["id"])

    def test_sha256_is_stable_for_the_file(self):
        self.assertEqual(len(registry_sha256(REGISTRY_PATH)), 64)
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "r.json"
            copy.write_bytes(REGISTRY_PATH.read_bytes())
            self.assertEqual(registry_sha256(copy), registry_sha256(REGISTRY_PATH))


class ValidationTests(unittest.TestCase):
    def test_rejects_bad_cik(self):
        with self.assertRaises(ValueError):
            validate_registry({"schema_version": 1, "sec_registered": [_fund(cik="1581005")]})

    def test_rejects_bad_series_id(self):
        with self.assertRaises(ValueError):
            validate_registry({"schema_version": 1, "sec_registered": [_fund(series_id="39565")]})

    def test_rejects_duplicate_ids(self):
        with self.assertRaises(ValueError):
            validate_registry({"schema_version": 1, "sec_registered": [_fund(), _fund()]})

    def test_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            validate_registry({"schema_version": 1, "sec_registered": [_fund(status="maybe")]})

    def test_mention_only_entries_need_no_fund_fields(self):
        validate_registry({
            "schema_version": 1,
            "sec_registered": [{"id": "m", "role": "mention_only", "status": "excluded"}],
        })

    def test_sec_funds_filters_by_status(self):
        registry = {
            "schema_version": 1,
            "sec_registered": [
                _fund(id="a", status="active"),
                _fund(id="b", status="reorganized"),
                _fund(id="c", status="inactive_verify"),
                {"id": "d", "role": "mention_only", "status": "excluded"},
            ],
        }
        self.assertEqual([f["id"] for f in sec_funds(registry)], ["a", "b"])
        self.assertEqual([f["id"] for f in sec_funds(registry, statuses=("inactive_verify",))], ["c"])

    def test_round_trips_through_json(self):
        registry = load_registry(REGISTRY_PATH)
        validate_registry(json.loads(json.dumps(registry)))


if __name__ == "__main__":
    unittest.main()
