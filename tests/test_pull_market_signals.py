import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pull_market_signals import (  # noqa: E402
    _extract_json_array,
    _paginate_keyset,
    _polymarket_contracts,
    classify_weather_contract,
    parse_climate_central_events,
)


class WeatherFilterTests(unittest.TestCase):
    def test_positive_weather_contracts(self):
        self.assertEqual(
            classify_weather_contract("How many named storms in the Atlantic?"),
            ["hurricane_or_named_storm"],
        )
        self.assertEqual(
            classify_weather_contract("Highest temperature in New York today"),
            ["city_temperature"],
        )
        self.assertEqual(
            classify_weather_contract("Daily high temperature in Chicago"),
            ["city_temperature"],
        )

    def test_non_weather_contracts_are_not_selected(self):
        self.assertEqual(classify_weather_contract("Storm wins the basketball final"), [])
        self.assertEqual(classify_weather_contract("temporary Prime Minister"), [])
        self.assertEqual(classify_weather_contract("Carolina Hurricanes win the NHL?"), [])
        self.assertEqual(classify_weather_contract("Miami Hurricanes win the Atlantic Coast Conference?"), [])
        self.assertEqual(classify_weather_contract("Cochin Hurricanes win the cricket match?"), [])
        self.assertEqual(classify_weather_contract("Will Tyra Hurricane Black advance?"), [])
        self.assertEqual(classify_weather_contract("Official daily high price of crude oil"), [])
        self.assertEqual(classify_weather_contract("Global warming policy enacted?"), [])

    def test_team_names_with_basin_words_are_not_selected(self):
        # Super Rugby Pacific: "Pacific" in the event description is a league, not a basin.
        self.assertEqual(
            classify_weather_contract(
                "Hurricanes vs Blues", "Super Rugby Pacific round 4 match between the "
                "Hurricanes and the Blues.", "Will Hurricanes win?",
            ),
            [],
        )
        self.assertEqual(
            classify_weather_contract(
                "Hurricanes vs Blues", "Super Rugby Pacific match.",
                "Will the match end in a draw?",
            ),
            [],
        )
        # College sports: "Florida Atlantic" is a university.
        self.assertEqual(
            classify_weather_contract("Florida Atlantic Owls vs. Miami Hurricanes (W)"), [],
        )
        self.assertEqual(
            classify_weather_contract("Tulsa Golden Hurricane vs. Florida Atlantic Owls"), [],
        )

    def test_real_storm_contracts_survive_the_sports_guard(self):
        for text in (
            "Will the next Pacific hurricane form between August 27 and August 31, 2026?",
            "Will Winnie be the first named hurricane in the Central Pacific in 2026?",
            "Will there be more than 25 named storms during Atlantic Hurricane Season?",
            "Will Tropical Storm Saudel peak as a \"Violent Typhoon\"?",
            "Will Idalia hit Florida as a major hurricane?",
            "Cat 3+ hurricane hits Miami in 2025?",
            "Will a hurricane make landfall in the US in September?",
            "Where will a hurricane make landfall in the US during the 2026 hurricane season?",
        ):
            self.assertEqual(classify_weather_contract(text), ["hurricane_or_named_storm"], text)


class PolymarketTests(unittest.TestCase):
    def test_keyset_pagination_uses_returned_cursor(self):
        class Client:
            def __init__(self):
                self.calls = []

            def json(self, _url, params):
                self.calls.append(params)
                if "after_cursor" not in params:
                    return {"events": [{"id": "one"}], "next_cursor": "next"}
                return {"events": [{"id": "two"}], "next_cursor": ""}

        client = Client()
        rows = _paginate_keyset(client, "https://example.test", "events", {"closed": "false"})
        self.assertEqual([row["id"] for row in rows], ["one", "two"])
        self.assertEqual(client.calls[1]["after_cursor"], "next")

    def test_nested_market_strings_are_normalized(self):
        events = [{
            "id": "event-1", "slug": "atlantic-hurricane", "title": "Atlantic hurricane",
            "markets": [{
                "id": "market-1", "conditionId": "0xabc", "question": "A hurricane?",
                "outcomes": '["Yes", "No"]', "outcomePrices": '["0.3", "0.7"]',
                "clobTokenIds": '["yes-token", "no-token"]',
            }],
        }]
        rows = _polymarket_contracts(events)
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["token_ids_json"]), ["yes-token", "no-token"])

    def test_expired_market_is_not_an_open_snapshot_contract(self):
        events = [{"active": True, "title": "Temperature in Boston", "markets": [{
            "active": True, "closed": False, "acceptingOrders": True,
            "endDate": "2025-01-01T00:00:00Z", "question": "Highest temperature in Boston?",
        }]}]
        self.assertEqual(_polymarket_contracts(events, current_ts=1_800_000_000), [])


class ClimateCentralTests(unittest.TestCase):
    def test_array_scanner_ignores_brackets_in_strings(self):
        text = 'prefix"events":[{"summary":"a [bracket]","id":"one"}]suffix'
        self.assertEqual(_extract_json_array(text, '"events":')[0]["id"], "one")

    def test_next_flight_event_payload(self):
        fragment = 'x"initialData":{"events":[{"id":"one","summary":"ok"}],"other":1}y'
        html = '<script>self.__next_f.push([1,%s])</script>' % json.dumps(fragment)
        rows = parse_climate_central_events(html)
        self.assertEqual(rows, [{"id": "one", "summary": "ok"}])


if __name__ == "__main__":
    unittest.main()
