import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from backfill_prediction_market_history import (  # noqa: E402
    Store,
    backwards_epoch_windows,
    backwards_windows,
    historical_polymarket_rows,
)


class WindowTests(unittest.TestCase):
    def test_windows_run_newest_to_oldest_without_overlap(self):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 11, tzinfo=timezone.utc)
        windows = list(backwards_windows(start, end, 4))
        self.assertEqual(windows[0], (
            datetime(2025, 1, 7, tzinfo=timezone.utc), end,
        ))
        self.assertEqual(windows[-1][0], start)
        self.assertEqual(windows[0][0], windows[1][1])

    def test_epoch_windows_are_newest_first_and_do_not_overlap(self):
        windows = list(backwards_epoch_windows(0, 200_000, 1))
        self.assertEqual(
            windows, [(113_600, 200_000), (27_199, 113_599), (0, 27_198)]
        )


class HistoricalContractTests(unittest.TestCase):
    def test_closed_polymarket_weather_market_is_retained(self):
        events = [{
            "id": "e1", "title": "Highest temperature in New York",
            "markets": [{
                "id": "m1", "question": "Highest temperature in New York?",
                "startDate": "2025-01-01T00:00:00Z",
                "endDate": "2025-01-02T00:00:00Z",
                "clobTokenIds": '["yes","no"]', "closed": True,
            }],
        }]
        rows = historical_polymarket_rows(
            events, datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["outcome_ids_json"]), ["yes", "no"])
        self.assertNotIn("markets", json.loads(rows[0]["metadata_json"])["event"])


class StoreTests(unittest.TestCase):
    def test_completed_jobs_are_resumable_and_sorted_newest_first(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / "history.sqlite3")
            for identifier, closed in (("old", "2025-01-02T00:00:00+00:00"),
                                       ("new", "2025-01-03T00:00:00+00:00")):
                store.upsert_contract({
                    "platform": "polymarket", "contract_id": identifier,
                    "event_id": "e", "series_id": "", "classification": "city_temperature",
                    "title": identifier, "opened_at": "2025-01-01T00:00:00+00:00",
                    "closed_at": closed, "outcome_ids_json": '["yes","no"]',
                    "metadata_json": "{}", "discovered_at": closed,
                })
            store.connection.commit()
            pending = store.contracts(
                "polymarket", "2025-01-01T00:00:00+00:00",
                "2025-01-04T00:00:00+00:00", "prices",
            )
            self.assertEqual([row["contract_id"] for row in pending], ["new", "old"])
            hurricane_only = store.contracts(
                "polymarket", "2025-01-01T00:00:00+00:00",
                "2025-01-04T00:00:00+00:00", "prices",
                classification="hurricane_or_named_storm",
            )
            self.assertEqual(hurricane_only, [])
            store.history_result("polymarket", "new", "prices", "complete", 2)
            store.history_result(
                "polymarket", "old", "prices", "unavailable", 0, "publisher gap"
            )
            pending = store.contracts(
                "polymarket", "2025-01-01T00:00:00+00:00",
                "2025-01-04T00:00:00+00:00", "prices",
            )
            self.assertEqual(pending, [])
            store.close()


if __name__ == "__main__":
    unittest.main()
