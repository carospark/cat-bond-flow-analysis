import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_snapshot_freshness as fresh  # noqa: E402


def _snapshot(raw_root: Path, day: str, source: str, content: bytes = b"x") -> None:
    target = raw_root / day / source
    target.mkdir(parents=True, exist_ok=True)
    (target / "payload.csv").write_bytes(content)


def _history_db(path: Path, rows) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE run_log (id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT,"
        " arguments_json TEXT, status TEXT, summary_json TEXT)"
    )
    for finished_at, platforms, status in rows:
        connection.execute(
            "INSERT INTO run_log(started_at, finished_at, arguments_json, status) VALUES (?, ?, ?, ?)",
            (finished_at, finished_at, json.dumps({"platforms": platforms}), status),
        )
    connection.commit()
    connection.close()


class SnapshotDateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "tier1"
        self.raw.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_newest_dated_directory_with_content_wins(self):
        _snapshot(self.raw, "2026-10-21", "kalshi_weather_markets")
        _snapshot(self.raw, "2026-10-24", "kalshi_weather_markets")
        _snapshot(self.raw, "2026-10-25", "polymarket_weather_markets")
        self.assertEqual(fresh.last_snapshot_date(self.raw, "kalshi_weather_markets"), date(2026, 10, 24))
        self.assertEqual(fresh.last_snapshot_date(self.raw, "polymarket_weather_markets"), date(2026, 10, 25))

    def test_empty_source_directory_does_not_count(self):
        _snapshot(self.raw, "2026-10-22", "brookmont_ils_etf")
        _snapshot(self.raw, "2026-10-25", "brookmont_ils_etf", content=b"")
        (self.raw / "2026-10-26" / "brookmont_ils_etf").mkdir(parents=True)
        self.assertEqual(fresh.last_snapshot_date(self.raw, "brookmont_ils_etf"), date(2026, 10, 22))

    def test_non_date_directories_and_missing_sources_are_ignored(self):
        (self.raw / "wrds").mkdir()
        (self.raw / "wrds" / "screen.txt").write_text("x")
        self.assertIsNone(fresh.last_snapshot_date(self.raw, "kalshi_weather_markets"))
        self.assertIsNone(fresh.last_snapshot_date(self.raw / "absent", "kalshi_weather_markets"))


class HistoryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "history.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_completed_runs_for_the_platform_count(self):
        _history_db(self.db, [
            ("2026-10-22T13:43:30+00:00", ["kalshi"], "error"),
            ("2026-10-22T11:02:50+00:00", ["polymarket"], "complete"),
            ("2026-10-21T09:00:00+00:00", ["kalshi"], "complete"),
        ])
        self.assertEqual(fresh.last_history_run(self.db, "kalshi"), date(2026, 10, 21))
        self.assertEqual(fresh.last_history_run(self.db, "polymarket"), date(2026, 10, 22))

    def test_missing_database_is_none(self):
        self.assertIsNone(fresh.last_history_run(self.db, "kalshi"))


class AssessmentTests(unittest.TestCase):
    def test_age_boundary(self):
        as_of = date(2026, 10, 25)
        self.assertFalse(fresh.assess("s", date(2026, 10, 23), as_of, 2).stale)
        self.assertTrue(fresh.assess("s", date(2026, 10, 22), as_of, 2).stale)
        missing = fresh.assess("s", None, as_of, 2)
        self.assertTrue(missing.stale)
        self.assertEqual(missing.status, "MISSING")


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.raw = base / "tier1"
        self.raw.mkdir()
        self.db = base / "history.sqlite3"
        self.market = base / "market.json"
        self.market.write_text(json.dumps({"sources": [{"id": "kalshi_weather_markets"}]}))
        self.tier1 = base / "tier1.json"
        self.tier1.write_text(json.dumps({"sources": [
            {"id": "brookmont_ils_etf", "refresh": "daily"},
            {"id": "lane_financial_ils_2024", "refresh": "annual"},
        ]}))
        self.lock = base / "runner.lock"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, as_of: str):
        return fresh.main([
            "--raw-root", str(self.raw), "--database", str(self.db),
            "--market-config", str(self.market), "--tier1-config", str(self.tier1),
            "--as-of", as_of, "--lock", str(self.lock),
        ])

    def test_daily_sources_exclude_non_daily_tier1(self):
        self.assertEqual(
            fresh.daily_source_ids(self.market, self.tier1),
            ["brookmont_ils_etf", "kalshi_weather_markets"],
        )

    def test_exit_zero_when_everything_is_fresh(self):
        _snapshot(self.raw, "2026-10-24", "kalshi_weather_markets")
        _snapshot(self.raw, "2026-10-25", "brookmont_ils_etf")
        _history_db(self.db, [
            ("2026-10-24T05:00:00+00:00", ["kalshi"], "complete"),
            ("2026-10-23T05:00:00+00:00", ["polymarket"], "complete"),
        ])
        self.assertEqual(self._run("2026-10-25"), 0)

    def test_exit_one_when_a_source_is_stale_or_missing(self):
        _snapshot(self.raw, "2026-10-22", "kalshi_weather_markets")
        _snapshot(self.raw, "2026-10-25", "brookmont_ils_etf")
        _history_db(self.db, [
            ("2026-10-24T05:00:00+00:00", ["kalshi", "polymarket"], "complete"),
        ])
        self.assertEqual(self._run("2026-10-25"), 1)
        self.assertEqual(self._run("2026-10-24"), 0)

    def test_dead_pid_lock_is_reported_without_failing(self):
        _snapshot(self.raw, "2026-10-25", "kalshi_weather_markets")
        _snapshot(self.raw, "2026-10-25", "brookmont_ils_etf")
        _history_db(self.db, [("2026-10-25T05:00:00+00:00", ["kalshi", "polymarket"], "complete")])
        self.lock.mkdir()
        (self.lock / "pid").write_text("999999\n")
        self.assertIn("dead pid 999999", fresh.lock_state(self.lock))
        self.assertEqual(self._run("2026-10-25"), 0)


if __name__ == "__main__":
    unittest.main()
