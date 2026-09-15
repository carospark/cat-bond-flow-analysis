"""Archive time-sensitive prediction-market and disaster-calendar data.

This module is deliberately independent of the Artemis parser. It discovers
open weather contracts on Kalshi and Polymarket, archives their metadata, and
backfills public price/trade histories. It also archives Climate Central's
billion-dollar-disaster annual CSV and derives an event calendar from the
publisher's server-rendered events page.

All outputs are local-only under ``data/raw`` and are gitignored.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "market_signal_sources.json"
DEFAULT_RAW_ROOT = ROOT / "data" / "raw" / "tier1"
USER_AGENT = (
    "cat-bond-flow-analysis/0.1 (academic research; public data archiver)"
)

WEATHER_PATTERNS = {
    "hurricane_or_named_storm": re.compile(
        r"\b(?:hurricanes?|named storms?|tropical (?:storms?|cyclones?)|"
        r"atlantic storms?|pacific storms?)\b",
        re.IGNORECASE,
    ),
    "city_temperature": re.compile(
        r"\b(?:daily (?:high|low) temperature|"
        r"highest temperature|lowest temperature|temperature in|"
        r"(?:high|low) temp(?:erature)? in|hourly directional [a-z ]+ temperature|"
        r"average (?:daily )?(?:minimum|maximum) temperature)\b",
        re.IGNORECASE,
    ),
}

SPORTS_HURRICANE_PATTERN = re.compile(
    r"\b(?:NHL|NCAA|NFL|NBA|MLB|Stanley Cup|playoffs?|conference|division|team|"
    r"Carolina Hurricanes|Miami Hurricanes|Tulsa Golden Hurricane|Golden Hurricane|"
    r"Super Rugby|rugby|football|basketball|hockey|cricket|soccer|"
    r"match|draw|vs\.?|versus|win\?|winner|score|spread|moneyline|BTTS)\b",
    re.IGNORECASE,
)

# A storm-context token must describe weather, not a place name inside a team
# name. Bare "atlantic" or "pacific" is not enough: Florida Atlantic and Super
# Rugby Pacific both contain them.
WEATHER_STORM_CONTEXT = re.compile(
    r"\b(?:atlantic|pacific|gulf)\s+(?:hurricanes?|storms?|basins?|seasons?|ocean|"
    r"coast|tropical|named|cyclones?|typhoons?)\b|"
    r"\b(?:central|eastern|western|east|west|north|south|northwest)\s+"
    r"(?:atlantic|pacific)\b|"
    r"\b(?:in|of|across|for)\s+the\s+(?:atlantic|pacific|gulf)\b|"
    r"\b(?:tropical|weather|wind speed|landfall|category [1-5]|cat [1-5]\+?|"
    r"named storm|storm season|hurricane season|major hurricane|typhoons?|"
    r"national hurricane center|NHC|NOAA|CSU)\b|"
    r"\bhurricanes?\s+(?:hits?|makes? landfall|forms?|season|count|total|"
    r"named|reaches?|becomes?|strengthens?|peaks?)\b|"
    r"\b(?:how many|number of|first|next|major|another|any)\s+"
    r"(?:atlantic |pacific )?hurricanes?\b",
    re.IGNORECASE,
)

# When sports vocabulary is present, only an unambiguous storm token keeps the
# contract.
STRONG_STORM_TOKEN = re.compile(
    r"\b(?:landfall|named storms?|tropical storms?|tropical cyclones?|wind speed|"
    r"category [1-5]|hurricane season|major hurricane|national hurricane center)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Geography tags. Each contract is tagged "region:<name>" for every region its
# text mentions, so a class can be restricted to the geographies where the deal
# directory actually has exposure, and so downstream joins can pick, say,
# California earthquake markets rather than global counts.
# ---------------------------------------------------------------------------

_I = re.IGNORECASE
REGION_PATTERNS = {
    "california": re.compile(
        r"\b(?:california|los angeles|\bLA\b|san francisco|san diego|sacramento|"
        r"palisades|malibu|santa monica|beverly hills|hollywood|bay area|"
        r"san jose|oakland|northstar|heavenly)\b", _I),
    "florida": re.compile(
        r"\b(?:florida|miami|tampa|orlando|jacksonville|st\.? petersburg|key west|"
        r"fort lauderdale|pensacola|tallahassee)\b", _I),
    "texas": re.compile(
        r"\b(?:texas|houston|dallas|austin|san antonio|college station|galveston|"
        r"corpus christi)\b", _I),
    "gulf_coast": re.compile(
        r"\b(?:louisiana|new orleans|mississippi|alabama|gulf coast|mobile,? al|"
        r"jackson,? ms|jackson\b)\b", _I),
    "southeast_us": re.compile(
        r"\b(?:north carolina|south carolina|carolinas?|charleston|wilmington|"
        r"myrtle beach|hatteras|outer banks|georgia|savannah|atlanta|virginia|"
        r"norfolk|tennessee|kentucky|lexington|louisville)\b", _I),
    "northeast_us": re.compile(
        r"\b(?:new york|nyc|central park|manhattan|new jersey|boston|philadelphia|"
        r"providence|washington,? d\.?c\.?|\bd\.?c\.?\b|mt\.? washington|"
        r"new england|northeast|connecticut|massachusetts|pennsylvania|maryland|"
        r"buffalo|stowe|vermont|maine)\b", _I),
    "midwest_us": re.compile(
        r"\b(?:chicago|illinois|ohio|columbus|michigan|detroit|wisconsin|milwaukee|"
        r"minnesota|minneapolis|iowa|des moines|missouri|st\.? louis|kansas|"
        r"nebraska|oklahoma|indiana|indianapolis|midwest|tornado alley|"
        r"rapid city|south dakota|north dakota)\b", _I),
    "mountain_west_us": re.compile(
        r"\b(?:colorado|denver|utah|salt lake|alta|park city|arizona|phoenix|"
        r"nevada|las vegas|lake mead|new mexico|idaho|montana|wyoming|"
        r"jackson hole|yellowstone|washington state|seattle|oregon|portland|"
        r"vail|breckenridge|keystone|beaver creek)\b", _I),
    "hawaii": re.compile(r"\b(?:hawaii|honolulu|maui|oahu|central pacific)\b", _I),
    "us": re.compile(
        r"\b(?:u\.?s\.?a?\.?|united states|america|american|lower 48|contiguous|"
        r"fema|nws|noaa|national weather service|usgs)\b", _I),
    "canada": re.compile(
        r"\b(?:canada|canadian|toronto|vancouver|montreal|british columbia|"
        r"quebec|ontario|alberta|calgary|halifax|nova scotia)\b", _I),
    "japan": re.compile(
        r"\b(?:japan|japanese|honshu|tokyo|osaka|kyushu|okinawa|hokkaido|"
        r"shikoku|nankai|JMA)\b", _I),
    "east_asia": re.compile(
        r"\b(?:china|chinese|taiwan|hong kong|philippines|korea|seoul|vietnam|"
        r"northwest pacific|western pacific|west pacific|south china sea)\b", _I),
    "mexico": re.compile(r"\b(?:mexico|mexican|baja|yucat[aá]n|acapulco)\b", _I),
    "south_america": re.compile(
        r"\b(?:chile|chilean|peru|peruvian|colombia|ecuador|argentina|brazil|"
        r"south america)\b", _I),
    "caribbean": re.compile(
        r"\b(?:caribbean|puerto rico|jamaica|bahamas|virgin islands|cuba|"
        r"dominican|haiti|bermuda|cayman|barbados|antilles)\b", _I),
    "europe": re.compile(
        r"\b(?:europe|european|\bUK\b|u\.k\.|britain|british|england|london|"
        r"ireland|irish|dublin|scotland|wales|france|french|paris|germany|german|"
        r"berlin|netherlands|dutch|amsterdam|belgium|denmark|danish|norway|"
        r"sweden|scandinavia|italy|italian|vesuvius|etna|iceland|mediterranean|"
        r"spain|portugal|switzerland|austria|poland|met office)\b", _I),
    "australia": re.compile(
        r"\b(?:australia|australian|queensland|brisbane|sydney|melbourne|perth|"
        r"darwin|cairns|new south wales|northern territory)\b", _I),
    "global": re.compile(r"\b(?:worldwide|global|globally|world'?s|anywhere|in the world)\b", _I),
}

US_SUBREGIONS = frozenset({
    "california", "florida", "texas", "gulf_coast", "southeast_us",
    "northeast_us", "midwest_us", "mountain_west_us", "hawaii",
})
US_REGIONS = US_SUBREGIONS | {"us"}


def classify_regions(text: str) -> set[str]:
    regions = {name for name, pattern in REGION_PATTERNS.items() if pattern.search(text)}
    if regions & US_SUBREGIONS:
        regions.add("us")
    return regions


# ---------------------------------------------------------------------------
# Hazard classes beyond hurricane and temperature. Each entry maps a cat-bond
# peril to the prediction-market vocabulary that describes it.
#   pattern  - what selects the class
#   guard    - non-hazard uses of the same words (teams, companies, politics)
#   strong   - a guarded text keeps the class only when this also matches
#   exclude  - always drops the class, whatever else matches
#   regions  - restrict to geographies where the deal directory has exposure;
#              None keeps every geography
# ---------------------------------------------------------------------------

def _spec(pattern, guard=None, strong=None, regions=None, exclude=None):
    return {
        "pattern": re.compile(pattern, _I),
        "guard": re.compile(guard, _I) if guard else None,
        "strong": re.compile(strong, _I) if strong else None,
        "regions": frozenset(regions) if regions else None,
        "exclude": re.compile(exclude, _I) if exclude else None,
    }


HAZARD_CLASSES = {
    "earthquake": _spec(
        r"\b(?:earthquakes?|quakes?|seismic|magnitude\s*\d|tsunamis?|richter)\b",
        guard=r"\b(?:san jose earthquakes|blue tsunami|red tsunami|silver tsunami|"
              r"vs\.?|versus|win\?|winner|MLS)\b",
        strong=r"\b(?:magnitude|richter|USGS|seismic|M\s?\d\.\d)\b",
    ),
    "severe_convective_storm": _spec(
        r"\b(?:tornado(?:es)?|hail(?:storm)?s?|derechos?|severe (?:thunder)?storms?|"
        r"supercells?)\b",
        guard=r"\b(?:hail mary|hail to|iowa state|cyclones|vs\.?|versus|win\?|"
              r"MLS|NFL|NCAA|NBA|golden tornadoes|talladega|king university)\b",
        strong=r"\b(?:NWS|storm prediction center|SPC|EF-?\d|tornado (?:risk|count|"
               r"warning|watch|outbreak)|(?:how many|number of) tornado(?:es)?|"
               r"tornado(?:es)? in the)\b",
    ),
    "wildfire": _spec(
        r"\b(?:wildfires?|bushfires?|brush fires?|forest fires?|"
        r"acres (?:burned|will burn|burn)|"
        r"(?:palisades|eaton|sunset|hughes|camp|dixie|caldor|park) fires?|"
        r"fire (?:season|containment|perimeter))\b",
        guard=r"\b(?:trump|visits?|arson|arrested|charged|chicago fire|fired|"
              r"ceasefire|firefighters? union)\b",
        strong=r"\b(?:acres|contain(?:ed|ment)|evacuat\w*|burn(?:ed|s)?)\b",
    ),
    "winter_storm": _spec(
        r"\b(?:snowfall|inches of snow|total snow|will it snow|where will it snow|"
        r"first snow|snow (?:in|on|at)|blizzards?|ice storms?|winter storms?|"
        r"nor'?easters?|freezing rain)\b",
        guard=r"\b(?:snowflake|snowboard|snowdown|snow white|blizzard entertainment|"
              r"activision|warcraft|overwatch|resort (?:opening|closing)|"
              r"ski resort|LoL|esports)\b",
        strong=r"\b(?:inches|snowfall|blizzard warning|NWS)\b",
        regions=US_REGIONS | {"canada"},
    ),
    "volcanic_eruption": _spec(
        r"\b(?:volcan(?:o|oes|ic)|eruptions?|erupts?|VEI\s?≥?\s?\d|supervolcano|"
        r"vesuvius|etna|yellowstone caldera|kilauea|mauna loa|campi flegrei)\b",
        guard=r"\b(?:erupt(?:s|ed|ion)? (?:in|into) (?:violence|protest|war|conflict)|"
              r"volcano (?:bowl|club|bay))\b",
        strong=r"\b(?:VEI|volcan\w*|vesuvius|etna|lava|ash)\b",
    ),
    "typhoon_or_cyclone": _spec(
        r"\b(?:typhoons?|cyclones?)\b",
        guard=r"\b(?:iowa state|vs\.?|versus|win\?|winner|NCAA|football|basketball)\b",
        strong=r"\b(?:typhoon|landfall|tropical cyclone|JMA|category)\b",
        regions={"japan", "east_asia", "australia"},
    ),
    "precipitation": _spec(
        r"\b(?:rain(?:fall|s)?|precipitation|flood(?:s|ing|ed)?|flash floods?|"
        r"river (?:crest|stage|level|peak)|atmospheric rivers?|"
        r"(?:will|does|did) it rain|inches of rain)\b",
        guard=r"\b(?:sophie rain|rain man|purple rain|grand prix|\bF1\b|race|tennis|"
              r"golf|delay|hamas|tunnels?|flood the zone|flooded with|parade|"
              r"rain on (?:his|her|their))\b",
        strong=r"\b(?:inches|precipitation|rainfall|river|crest|flood(?:ing|s)?|"
               r"NWS|gauge)\b",
        regions=US_REGIONS | {"japan"},
    ),
    "windstorm": _spec(
        r"\b(?:windstorms?|wind (?:speeds?|gusts?)|gusts?|gales?|gale[- ]force|"
        r"storm[- ]force winds?|extratropical|"
        r"storm (?:[ée]owyn|darragh|ciar[áa]n|eunice|isha|bert|conall|floris|"
        r"amy|benjamin|bram|babet|arwen|malik|kathleen|jocelyn|henk|pia))\b",
        guard=r"\b(?:windsor|windows|winds of|tailwind|headwind|offshore wind|"
              r"wind (?:farm|project|lease|energy|power|turbine)|desert storm|"
              r"brainstorm|firestorm)\b",
        strong=r"\b(?:mph|km/h|knots|gusts?|gale|windstorm)\b",
        regions={"europe", "australia"},
    ),
    # Mortality bonds trigger on declared pandemics and excess deaths, not on
    # case counts, boosters, or drug approvals, so only declaration language
    # qualifies.
    "pandemic_or_mortality": _spec(
        r"\b(?:pandemics?|PHEIC|public health emergenc(?:y|ies)|"
        r"global health emergenc(?:y|ies)|excess (?:mortality|deaths))\b",
        guard=r"\b(?:vaccine|vaccination|booster|mandate|lab leak|lockdown|fauci|"
              r"stock|shares|earnings|\bvs\.?\b)\b",
        strong=r"\b(?:declared?|named|PHEIC|excess (?:mortality|deaths))\b",
        exclude=r"\bzombie\b",
    ),
    "disaster_declaration": _spec(
        r"\b(?:FEMA|disaster declarations?|declares? (?:a )?(?:major |natural )?disasters?|"
        r"(?:natural )?disasters? (?:hits?|in|strikes?)|states? of emergency|"
        r"billion[- ]dollar (?:weather|climate|disasters?)|natural disasters?)\b",
        guard=r"\b(?:administrator|head of fema|fired|resign|abolish\w*|eliminat\w*|"
              r"trump|biden|nominat\w*|confirm\w*|budget|funding|congress|bill|"
              r"senate|house|say during|rally|podcast)\b",
        strong=r"\b(?:declar\w*|hits|billion[- ]dollar|natural disaster in 20\d\d)\b",
    ),
    "enso": _spec(
        r"\b(?:el ni[ñn]o|la ni[ñn]a|ENSO|RONI|oceanic ni[ñn]o index)\b",
    ),
}

HAZARD_CLASS_NAMES = tuple(WEATHER_PATTERNS) + tuple(HAZARD_CLASSES)


def classify_weather_contract(*parts: Any, strict_regions: bool = True) -> list[str]:
    """Return the hazard classes for a contract's text, plus region tags.

    ``strict_regions=False`` skips the geography restriction; use it for
    series-level titles such as "Where will it rain daily", whose markets
    carry the city name individually.
    """
    text = " ".join(str(part or "") for part in parts)
    matches = [name for name, pattern in WEATHER_PATTERNS.items() if pattern.search(text)]
    if "hurricane_or_named_storm" in matches:
        if (not WEATHER_STORM_CONTEXT.search(text)
                or (SPORTS_HURRICANE_PATTERN.search(text)
                    and not STRONG_STORM_TOKEN.search(text))):
            matches.remove("hurricane_or_named_storm")
    regions = classify_regions(text)
    for name, spec in HAZARD_CLASSES.items():
        if not spec["pattern"].search(text):
            continue
        if spec["exclude"] and spec["exclude"].search(text):
            continue
        if spec["guard"] and spec["guard"].search(text):
            if not (spec["strong"] and spec["strong"].search(text)):
                continue
        if strict_regions and spec["regions"] and not (regions & spec["regions"]):
            continue
        matches.append(name)
    if not matches:
        return []
    return matches + sorted(f"region:{region}" for region in regions)


def hazard_classes(classification: str | list[str] | None) -> list[str]:
    """Strip region tags from a stored ';'-joined classification."""
    if not classification:
        return []
    items = classification.split(";") if isinstance(classification, str) else classification
    return [item for item in items if item and not item.startswith("region:")]


# Kalshi categories that carry hazard series. Pandemic and public-health
# markets sit outside "Climate and Weather".
KALSHI_HAZARD_CATEGORIES = frozenset({
    "Climate and Weather", "Health", "Science and Technology", "World",
})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


class PublicClient:
    def __init__(self, timeout: int = 60, retries: int = 4) -> None:
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    def get(self, url: str, params: dict[str, Any] | None = None) -> requests.Response:
        for attempt in range(self.retries):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < self.retries:
                        time.sleep(2**attempt)
                        continue
                response.raise_for_status()
                return response
            except requests.RequestException:
                if attempt + 1 == self.retries:
                    raise
                time.sleep(2**attempt)
        raise RuntimeError("request retries exhausted")

    def json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        return self.get(url, params=params).json()


def _paginate_cursor(
    client: PublicClient,
    url: str,
    collection: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = ""
    while True:
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        payload = client.json(url, query)
        rows.extend(payload.get(collection, []))
        cursor = payload.get("cursor") or ""
        if not cursor:
            return rows


def _paginate_offset(
    client: PublicClient,
    url: str,
    params: dict[str, Any],
    page_size: int = 500,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    prior_fingerprint: tuple[Any, ...] | None = None
    while True:
        query = {**params, "limit": page_size, "offset": offset}
        page = client.json(url, query)
        if not isinstance(page, list):
            raise ValueError(f"Expected a list from {url}")
        if not page:
            return rows
        fingerprint = tuple(str(row.get("id", "")) for row in page[:3])
        if fingerprint == prior_fingerprint:
            raise ValueError(f"Offset pagination did not advance for {url}")
        prior_fingerprint = fingerprint
        rows.extend(page)
        # Some APIs silently cap the requested page size. Advance by the
        # number actually returned and request one more page to prove EOF.
        offset += len(page)


def _paginate_keyset(
    client: PublicClient,
    url: str,
    collection: str,
    params: dict[str, Any],
    page_size: int = 500,
) -> list[dict[str, Any]]:
    """Read a stable cursor-paginated Gamma collection to exhaustion."""
    rows: list[dict[str, Any]] = []
    cursor = ""
    seen_cursors: set[str] = set()
    while True:
        query = {**params, "limit": page_size}
        if cursor:
            query["after_cursor"] = cursor
        payload = client.json(url, query)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected an object from {url}")
        page = payload.get(collection, [])
        if not isinstance(page, list):
            raise ValueError(f"Expected {collection} list from {url}")
        rows.extend(page)
        cursor = str(payload.get("next_cursor") or "")
        if not cursor:
            return rows
        if cursor in seen_cursors:
            raise ValueError(f"Keyset pagination did not advance for {url}")
        seen_cursors.add(cursor)


def _epoch(value: Any, fallback: int) -> int:
    if not value:
        return fallback
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return fallback


def _flatten_price(prefix: str, value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {f"{prefix}_{key}": value.get(f"{key}_dollars") for key in
            ("open", "low", "high", "close", "mean", "previous", "min", "max")}


def pull_kalshi(
    client: PublicClient, output_dir: Path, histories: bool = True,
    reuse_discovery: bool = False,
) -> dict[str, Any]:
    base = "https://external-api.kalshi.com/trade-api/v2"
    events_path = output_dir / "open_events_raw.json"
    if reuse_discovery and events_path.exists():
        events = json.loads(events_path.read_text(encoding="utf-8"))["events"]
    else:
        events = _paginate_cursor(
            client, f"{base}/events", "events",
            {"status": "open", "limit": 200, "with_nested_markets": "true"},
        )
        _write_json(events_path, {"events": events})

    contracts: list[dict[str, Any]] = []
    candles: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    history_errors: list[dict[str, str]] = []
    now_ts = int(datetime.now(timezone.utc).timestamp())

    for event in events:
        if event.get("category") not in KALSHI_HAZARD_CATEGORIES:
            continue
        for market in event.get("markets", []):
            classes = classify_weather_contract(
                event.get("title"), event.get("sub_title"), market.get("title"),
                market.get("subtitle"), market.get("yes_sub_title"),
            )
            if not classes:
                continue
            series = str(event.get("series_ticker") or "")
            event_ticker = str(event.get("event_ticker") or "")
            ticker = market.get("ticker")
            contracts.append({
                "platform": "kalshi",
                "classification": ";".join(classes),
                "series_ticker": series,
                "event_ticker": event_ticker,
                "market_ticker": ticker,
                "event_title": event.get("title"),
                "market_title": market.get("title"),
                "subtitle": market.get("subtitle") or market.get("yes_sub_title"),
                "status": market.get("status"),
                "open_time": market.get("open_time"),
                "close_time": market.get("close_time"),
                "yes_bid": market.get("yes_bid_dollars"),
                "yes_ask": market.get("yes_ask_dollars"),
                "last_price": market.get("last_price_dollars"),
                "volume": market.get("volume_fp"),
                "volume_24h": market.get("volume_24h_fp"),
                "open_interest": market.get("open_interest_fp"),
                "rules_primary": market.get("rules_primary"),
                "rules_secondary": market.get("rules_secondary"),
            })
            if not histories or not ticker or not series:
                continue
            start_ts = _epoch(market.get("open_time") or market.get("created_time"), now_ts - 94608000)
            try:
                payload = client.json(
                    f"{base}/series/{series}/markets/{ticker}/candlesticks",
                    {"start_ts": start_ts, "end_ts": now_ts,
                     "period_interval": 1440, "include_latest_before_start": "false"},
                )
                for candle in payload.get("candlesticks", []):
                    row = {
                        "platform": "kalshi", "market_ticker": ticker,
                        "end_period_ts": candle.get("end_period_ts"),
                        "end_period_utc": datetime.fromtimestamp(
                            candle.get("end_period_ts", 0), timezone.utc
                        ).isoformat(),
                        "volume": candle.get("volume_fp"),
                        "open_interest": candle.get("open_interest_fp"),
                    }
                    row.update(_flatten_price("price", candle.get("price")))
                    row.update(_flatten_price("yes_bid", candle.get("yes_bid")))
                    row.update(_flatten_price("yes_ask", candle.get("yes_ask")))
                    candles.append(row)

                market_trades = _paginate_cursor(
                    client, f"{base}/markets/trades", "trades",
                    {"ticker": ticker, "min_ts": start_ts, "max_ts": now_ts, "limit": 1000},
                )
                for trade in market_trades:
                    trades.append({"platform": "kalshi", **trade})
            except (requests.RequestException, ValueError) as exc:
                history_errors.append({"market_ticker": str(ticker), "error": str(exc)})

    contract_fields = [
        "platform", "classification", "series_ticker", "event_ticker", "market_ticker",
        "event_title", "market_title", "subtitle", "status", "open_time", "close_time",
        "yes_bid", "yes_ask", "last_price", "volume", "volume_24h", "open_interest",
        "rules_primary", "rules_secondary",
    ]
    candle_fields = [
        "platform", "market_ticker", "end_period_ts", "end_period_utc", "volume",
        "open_interest", "price_open", "price_low", "price_high", "price_close",
        "price_mean", "price_previous", "price_min", "price_max", "yes_bid_open",
        "yes_bid_low", "yes_bid_high", "yes_bid_close", "yes_ask_open", "yes_ask_low",
        "yes_ask_high", "yes_ask_close",
    ]
    trade_fields = [
        "platform", "trade_id", "ticker", "count_fp", "yes_price_dollars",
        "no_price_dollars", "taker_outcome_side", "taker_book_side", "created_time",
        "is_block_trade", "taker_side",
    ]
    _write_csv(output_dir / "contracts.csv", contract_fields, contracts)
    _write_csv(output_dir / "daily_candlesticks.csv", candle_fields, candles)
    _write_csv(output_dir / "trades.csv", trade_fields, trades)
    _write_json(output_dir / "history_errors.json", history_errors)
    return {
        "open_events_seen": len(events),
        "contracts_matched": len(contracts),
        "daily_candlesticks": len(candles), "trades": len(trades),
        "history_errors": len(history_errors),
    }


def _polymarket_contracts(
    events: list[dict[str, Any]], current_ts: int | None = None
) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for event in events:
        if event.get("active") is False:
            continue
        for market in event.get("markets", []):
            if (market.get("active") is False or market.get("closed") is True
                    or market.get("acceptingOrders") is False):
                continue
            end_value = market.get("endDate") or event.get("endDate")
            if current_ts is not None and end_value and _epoch(end_value, current_ts) < current_ts:
                continue
            classes = classify_weather_contract(
                event.get("title"), event.get("description"), market.get("question"),
                market.get("description"), market.get("groupItemTitle"),
            )
            if not classes:
                continue
            outcomes = _json_list(market.get("outcomes"))
            prices = _json_list(market.get("outcomePrices"))
            token_ids = _json_list(market.get("clobTokenIds"))
            contracts.append({
                "platform": "polymarket",
                "classification": ";".join(classes),
                "event_id": event.get("id"),
                "event_slug": event.get("slug"),
                "market_id": market.get("id"),
                "condition_id": market.get("conditionId"),
                "question": market.get("question"),
                "description": market.get("description") or event.get("description"),
                "resolution_source": market.get("resolutionSource") or event.get("resolutionSource"),
                "start_date": market.get("startDate") or event.get("startDate"),
                "end_date": market.get("endDate") or event.get("endDate"),
                "active": market.get("active"),
                "closed": market.get("closed"),
                "accepting_orders": market.get("acceptingOrders"),
                "outcomes_json": json.dumps(outcomes, separators=(",", ":")),
                "outcome_prices_json": json.dumps(prices, separators=(",", ":")),
                "token_ids_json": json.dumps(token_ids, separators=(",", ":")),
                "last_trade_price": market.get("lastTradePrice"),
                "best_bid": market.get("bestBid"),
                "best_ask": market.get("bestAsk"),
                "volume": market.get("volumeNum", market.get("volume")),
                "volume_24h": market.get("volume24hr"),
                "liquidity": market.get("liquidityNum", market.get("liquidity")),
            })
    return contracts


def _polymarket_trades(
    client: PublicClient, condition_id: str, start_ts: int, end_ts: int
) -> list[dict[str, Any]]:
    url = "https://data-api.polymarket.com/trades"
    output: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    window_end = end_ts
    while window_end >= start_ts:
        page = client.json(url, {
            "market": condition_id, "start": start_ts, "end": window_end,
            "limit": 10000, "offset": 0, "takerOnly": "false",
        })
        if not isinstance(page, list):
            raise ValueError("Expected a list from Polymarket trades")
        for trade in page:
            key = (trade.get("transactionHash"), trade.get("asset"),
                   trade.get("timestamp"), trade.get("side"), trade.get("size"))
            if key not in seen:
                seen.add(key)
                output.append(trade)
        if len(page) < 10000:
            break
        timestamps = [int(row["timestamp"]) for row in page if row.get("timestamp")]
        next_end = min(timestamps) - 1 if timestamps else window_end - 86400
        if next_end >= window_end:
            raise ValueError("Polymarket trade pagination did not advance")
        window_end = next_end
    return output


def pull_polymarket(
    client: PublicClient, output_dir: Path, histories: bool = True,
    reuse_discovery: bool = False,
) -> dict[str, Any]:
    raw_path = output_dir / "open_events_raw.json"
    if reuse_discovery and raw_path.exists():
        events = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        events = _paginate_keyset(
            client, "https://gamma-api.polymarket.com/events/keyset", "events",
            {"closed": "false", "active": "true"}, page_size=500,
        )
        _write_json(raw_path, events)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    contracts = _polymarket_contracts(events, now_ts)

    prices: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    history_errors: list[dict[str, str]] = []
    for contract in contracts:
        start_ts = _epoch(contract.get("start_date"), now_ts - 94608000)
        token_ids = _json_list(contract.get("token_ids_json"))
        outcomes = _json_list(contract.get("outcomes_json"))
        if histories:
            for index, token_id in enumerate(token_ids):
                try:
                    payload = client.json(
                        "https://clob.polymarket.com/prices-history",
                        {"market": token_id, "startTs": start_ts, "endTs": now_ts,
                         "fidelity": 60},
                    )
                    for point in payload.get("history", []):
                        ts = point.get("t")
                        prices.append({
                            "platform": "polymarket", "event_id": contract["event_id"],
                            "market_id": contract["market_id"],
                            "condition_id": contract["condition_id"], "token_id": token_id,
                            "outcome": outcomes[index] if index < len(outcomes) else index,
                            "timestamp": ts,
                            "timestamp_utc": datetime.fromtimestamp(ts, timezone.utc).isoformat()
                            if ts else None,
                            "price": point.get("p"),
                        })
                except (requests.RequestException, ValueError) as exc:
                    history_errors.append({"market_id": str(contract["market_id"]),
                                           "token_id": str(token_id), "error": str(exc)})
            condition_id = contract.get("condition_id")
            if condition_id:
                try:
                    for trade in _polymarket_trades(client, condition_id, start_ts, now_ts):
                        trades.append({
                            "platform": "polymarket", "market_id": contract["market_id"],
                            "condition_id": condition_id, "asset": trade.get("asset"),
                            "side": trade.get("side"), "size": trade.get("size"),
                            "price": trade.get("price"), "timestamp": trade.get("timestamp"),
                            "outcome": trade.get("outcome"),
                            "outcome_index": trade.get("outcomeIndex"),
                            "transaction_hash": trade.get("transactionHash"),
                        })
                except (requests.RequestException, ValueError) as exc:
                    history_errors.append({"market_id": str(contract["market_id"]),
                                           "condition_id": str(condition_id), "error": str(exc)})

    contract_fields = [
        "platform", "classification", "event_id", "event_slug", "market_id",
        "condition_id", "question", "description", "resolution_source", "start_date",
        "end_date", "active", "closed", "accepting_orders", "outcomes_json",
        "outcome_prices_json", "token_ids_json", "last_trade_price", "best_bid", "best_ask",
        "volume", "volume_24h", "liquidity",
    ]
    price_fields = [
        "platform", "event_id", "market_id", "condition_id", "token_id", "outcome",
        "timestamp", "timestamp_utc", "price",
    ]
    trade_fields = [
        "platform", "market_id", "condition_id", "asset", "side", "size", "price",
        "timestamp", "outcome", "outcome_index", "transaction_hash",
    ]
    _write_csv(output_dir / "contracts.csv", contract_fields, contracts)
    _write_csv(output_dir / "price_history.csv", price_fields, prices)
    _write_csv(output_dir / "trades.csv", trade_fields, trades)
    _write_json(output_dir / "history_errors.json", history_errors)
    return {
        "open_events_seen": len(events), "contracts_matched": len(contracts),
        "price_observations": len(prices), "trades": len(trades),
        "history_errors": len(history_errors),
    }


def _extract_json_array(text: str, marker: str) -> list[dict[str, Any]]:
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"Marker not found: {marker}")
    start = text.find("[", start + len(marker))
    if start < 0:
        raise ValueError("Array start not found")
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                value = json.loads(text[start:index + 1])
                if not isinstance(value, list):
                    raise ValueError("Extracted event payload is not a list")
                return value
    raise ValueError("Array end not found")


def parse_climate_central_events(html_text: str) -> list[dict[str, Any]]:
    fragments: list[str] = []
    pattern = re.compile(r"self\.__next_f\.push\(\[1,(\"(?:\\.|[^\"\\])*\")\]\)")
    for match in pattern.finditer(html_text):
        fragments.append(json.loads(match.group(1)))
    decoded = "".join(fragments)
    if not decoded:
        raise ValueError("Climate Central Next.js data stream was not found")
    return _extract_json_array(decoded, '"initialData":{"events":')


def pull_climate_central(client: PublicClient, output_dir: Path) -> dict[str, Any]:
    events_url = "https://www.climatecentral.org/climate-services/billion-dollar-disasters/events"
    annual_url = (
        "https://www.climatecentral.org/climate-services/billion-dollar-disasters/"
        "time-series/data?format=csv"
    )
    html_response = client.get(events_url)
    annual_response = client.get(annual_url)
    html_path = output_dir / "events.html"
    annual_path = output_dir / "annual_time_series.csv"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_bytes(html_response.content)
    annual_path.write_bytes(annual_response.content)

    events = parse_climate_central_events(html_response.text)
    rows = []
    for event in events:
        begin = str(event.get("begDate") or "")
        end = str(event.get("endDate") or "")
        summary = event.get("summary")
        rows.append({
            "event_id": event.get("id"), "event_name": event.get("name"),
            "disaster_type": event.get("disaster"),
            "begin_date": f"{begin[:4]}-{begin[4:6]}-{begin[6:8]}" if len(begin) == 8 else begin,
            "end_date": f"{end[:4]}-{end[4:6]}-{end[6:8]}" if len(end) == 8 else end,
            "cost_billions_adjusted": event.get("costBillionsAdjRaw", event.get("costBillionsAdj")),
            "cost_billions_unadjusted": event.get("costBillionsUnadjRaw", event.get("costBillionsUnadj")),
            "deaths": event.get("deaths"),
            "affected_states": ";".join(event.get("affectedStates") or []),
            "affected_regions": ";".join(event.get("affectedRegions") or []),
            "summary": "" if isinstance(summary, str) and summary.startswith("$") else summary,
            "summary_reference": summary if isinstance(summary, str) and summary.startswith("$") else "",
        })
    if len(rows) < 400 or not any(str(row["begin_date"]).startswith("1980") for row in rows):
        raise ValueError("Unexpected Climate Central event coverage")
    event_fields = [
        "event_id", "event_name", "disaster_type", "begin_date", "end_date",
        "cost_billions_adjusted", "cost_billions_unadjusted", "deaths",
        "affected_states", "affected_regions", "summary", "summary_reference",
    ]
    _write_csv(output_dir / "events.csv", event_fields, rows)
    return {"events": len(rows), "annual_rows": max(0, len(annual_response.text.splitlines()) - 1)}


PULLERS = {
    "kalshi_weather_markets": pull_kalshi,
    "polymarket_weather_markets": pull_polymarket,
    "climate_central_billion_dollar_disasters": pull_climate_central,
}


def append_log(raw_root: Path, record: dict[str, Any]) -> None:
    raw_root.mkdir(parents=True, exist_ok=True)
    log_path = raw_root / "market_signal_pull_log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    latest: dict[str, dict[str, Any]] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        latest[item["source_id"]] = item
    _write_json(raw_root / "market_signal_latest_status.json", {"sources": latest})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--source", action="append", choices=sorted(PULLERS))
    parser.add_argument("--metadata-only", action="store_true",
                        help="Archive discovery snapshots without price/trade backfill")
    parser.add_argument("--reuse-discovery", action="store_true",
                        help="Reprocess an existing raw discovery response for this date")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    configured = {source["id"] for source in config["sources"]}
    selected = set(args.source or configured)
    if selected - configured:
        raise ValueError(f"Unconfigured sources: {sorted(selected - configured)}")

    client = PublicClient(timeout=args.timeout)
    failures = 0
    for source_id in sorted(selected):
        output_dir = args.raw_root / args.as_of / source_id
        record: dict[str, Any] = {
            "source_id": source_id, "as_of": args.as_of,
            "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            if source_id == "climate_central_billion_dollar_disasters":
                counts = PULLERS[source_id](client, output_dir)
            else:
                counts = PULLERS[source_id](
                    client, output_dir, not args.metadata_only, args.reuse_discovery
                )
            files = sorted(path for path in output_dir.iterdir() if path.is_file())
            record.update({
                "status": "ok", "counts": counts,
                "files": [str(path.relative_to(ROOT)) for path in files],
                "sha256": {str(path.relative_to(ROOT)): sha256_file(path) for path in files},
            })
            print(f"[ok] {source_id}: {counts}")
        except Exception as exc:
            failures += 1
            record.update({"status": "error", "error_type": type(exc).__name__, "error": str(exc)})
            print(f"[error] {source_id}: {exc}")
        append_log(args.raw_root, record)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
