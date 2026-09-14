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
    hazard_classes,
    parse_climate_central_events,
)


class WeatherFilterTests(unittest.TestCase):
    def test_positive_weather_contracts(self):
        self.assertEqual(
            hazard_classes(classify_weather_contract("How many named storms in the Atlantic?")),
            ["hurricane_or_named_storm"],
        )
        self.assertEqual(
            hazard_classes(classify_weather_contract("Highest temperature in New York today")),
            ["city_temperature"],
        )
        self.assertEqual(
            hazard_classes(classify_weather_contract("Daily high temperature in Chicago")),
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
            self.assertEqual(hazard_classes(classify_weather_contract(text)),
                             ["hurricane_or_named_storm"], text)

    def test_region_tags_follow_the_classes(self):
        self.assertEqual(
            classify_weather_contract("Highest temperature in New York today"),
            ["city_temperature", "region:northeast_us", "region:us"],
        )
        # No class, no tags.
        self.assertEqual(classify_weather_contract("Mayor of New York"), [])


class HazardClassTests(unittest.TestCase):
    def classes(self, *parts, **kwargs):
        return hazard_classes(classify_weather_contract(*parts, **kwargs))

    def test_earthquake_markets(self):
        self.assertEqual(self.classes("Earthquake in California"), ["earthquake"])
        self.assertIn("region:california", classify_weather_contract("Earthquake in California"))
        self.assertEqual(self.classes("Magnitude 6.5+ earthquake in LA before 2026?"), ["earthquake"])
        self.assertEqual(self.classes("How many 6.5 or above earthquakes worldwide September 7 - 13?"),
                         ["earthquake"])
        self.assertEqual(self.classes("Where will a 6.0+ magnitude earthquake occur by end of September?"),
                         ["earthquake"])
        self.assertEqual(self.classes("Tsunami flooding in downtown San Francisco?"),
                         ["earthquake", "precipitation"])
        # Sports and politics.
        self.assertEqual(self.classes("San Jose Earthquakes vs. LA Galaxy"), [])
        self.assertEqual(self.classes("Will there be a blue tsunami?"), [])

    def test_tornado_and_hail(self):
        self.assertEqual(self.classes("How many Tornadoes in the US in 2026?"), ["severe_convective_storm"])
        self.assertEqual(self.classes("Which cities face tornado risk on August 19?"), ["severe_convective_storm"])
        self.assertEqual(self.classes("Number of Tornadoes"), ["severe_convective_storm"])
        self.assertEqual(self.classes("Iowa State Cyclones vs. Kansas"), [])
        self.assertEqual(self.classes("Talladega Tornadoes vs. Alabama A&M Bulldogs (W)"), [])
        self.assertEqual(self.classes("Geneva Golden Tornadoes vs. Robert Morris Colonials"), [])
        self.assertEqual(self.classes('"Project Hail Mary" Rotten Tomatoes score?'), [])
        self.assertEqual(self.classes("Madrid Open: Hailey Baptiste vs Jasmine Paolini"), [])

    def test_wildfire(self):
        self.assertEqual(self.classes("How many acres will Palisades wildfire burn in total?"), ["wildfire"])
        self.assertEqual(self.classes("When will the Palisades wildfire be fully contained?"), ["wildfire"])
        self.assertEqual(self.classes("Trump visits wildfires"), [])
        self.assertEqual(self.classes("Arsonists arrested in connection with LA wildfires?"), [])

    def test_winter_storm_is_limited_to_deal_geographies(self):
        self.assertEqual(self.classes("How many inches of snow in NYC in January?"), ["winter_storm"])
        self.assertEqual(self.classes("Denver snowfall monthly"), ["winter_storm"])
        self.assertEqual(self.classes("Will it snow in Seoul on Christmas?"), [])
        self.assertEqual(self.classes("Will Snowflake (SNOW) beat quarterly earnings?"), [])
        self.assertEqual(self.classes("Winter Games 2026: Snowboard Halfpipe - Women's"), [])
        # Series-level titles skip the geography gate; markets carry the city.
        self.assertEqual(self.classes("Where will it snow this December?", strict_regions=False),
                         ["winter_storm"])
        self.assertEqual(self.classes("Where will it snow this December?"), [])

    def test_volcano_typhoon_pandemic(self):
        self.assertEqual(self.classes("How many large volcano eruptions (VEI ≥4) in 2026?"), ["volcanic_eruption"])
        self.assertEqual(self.classes("Vesuvius eruption with 1+ VEI in 2026?"), ["volcanic_eruption"])
        self.assertEqual(self.classes("Will Super Typhoon Dolphin hit Japan?"), ["typhoon_or_cyclone"])
        self.assertEqual(self.classes("How many named typhoons in Northwest Pacific in 2025?"),
                         ["typhoon_or_cyclone"])
        # A Pacific-basin hurricane market is not a Japan or Australia cyclone proxy.
        self.assertEqual(
            self.classes("Will a tropical cyclone form in either the Pacific or Central Pacific basins by August 14?"),
            ["hurricane_or_named_storm"],
        )
        self.assertEqual(self.classes("Hantavirus pandemic in 2026?"), ["pandemic_or_mortality"])
        self.assertEqual(self.classes("New bird flu pandemic"), ["pandemic_or_mortality"])
        self.assertEqual(self.classes("New zombie virus public health emergency"), [])
        self.assertEqual(self.classes("Bird flu declared PHEIC"), ["pandemic_or_mortality"])
        # Case counts, boosters, and approvals are not mortality triggers.
        self.assertEqual(self.classes("NYC COVID daily case average"), [])
        self.assertEqual(self.classes("COVID boosters this month"), [])
        self.assertEqual(self.classes("FDA approves COVID pill"), [])
        self.assertEqual(self.classes("Measles cases in U.S. by April 30?"), [])

    def test_precipitation_and_wind_are_geography_gated(self):
        self.assertEqual(self.classes("Rain Houston"), ["precipitation"])
        self.assertEqual(self.classes("Precipitation in NYC in September?"), ["precipitation"])
        self.assertEqual(self.classes("What will the White River at Indianapolis peak at during the August 2026 floods?"),
                         ["precipitation"])
        self.assertEqual(self.classes("Precipitation in London in March?"), [])
        self.assertEqual(self.classes("Precipitation in Hong Kong in April?"), [])
        self.assertEqual(self.classes("Daily Rain - Paris"), [])
        self.assertEqual(self.classes("Will it rain during the Dutch Grand Prix?"), [])
        self.assertEqual(self.classes("Will Israel start flooding Hamas tunnels by December 15?"), [])
        # Wind: only Europe and Australia have windstorm and cyclone deals.
        self.assertEqual(self.classes("Highest Mt. Washington wind speed in September?"), [])
        self.assertEqual(self.classes("Peak wind gust in the world's windiest city in August"), [])
        self.assertEqual(self.classes("Will Storm Eowyn bring 100 mph gusts to Ireland?"), ["windstorm"])
        self.assertEqual(self.classes("Peak wind gust in Brisbane during Cyclone Alfred?"),
                         ["typhoon_or_cyclone", "windstorm"])
        self.assertEqual(self.classes("Will an Atlantic Shores offshore wind lease be terminated?"), [])

    def test_disaster_declarations_and_enso(self):
        self.assertEqual(self.classes("States that declare natural disasters"), ["disaster_declaration"])
        self.assertEqual(self.classes("Natural disaster hits Houston"), ["disaster_declaration"])
        self.assertEqual(self.classes("Natural Disaster in 2026?"), ["disaster_declaration"])
        self.assertEqual(
            self.classes("Will the US break its record for billion-dollar weather and climate disasters in 2026?"),
            ["disaster_declaration"],
        )
        self.assertEqual(self.classes("Will head of FEMA be fired/resign before November?"), [])
        self.assertEqual(self.classes("Trump FEMA Administrator"), [])
        self.assertEqual(self.classes("Will El Niño conditions be declared?"), ["enso"])
        self.assertEqual(self.classes("What will the peak RONI be for the 2026–27 El Niño?"), ["enso"])


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
