"""Resumably backfill historical weather prediction-market data.

The daily snapshot job records open contracts. This separate job discovers
closed contracts newest-to-oldest and stores daily price histories and public
trades in SQLite. It is intentionally independent of every Artemis input.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from pull_market_signals import (
    PublicClient,
    _epoch,
    _json_list,
    _paginate_cursor,
    _paginate_keyset,
    _polymarket_trades,
    classify_weather_contract,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "raw" / "tier1" / "prediction_market_history.sqlite3"
KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB = "https://clob.polymarket.com"
POLYMARKET_SEARCH_TERMS = (
    "temperature", "hurricane", "named storm", "tropical storm", "tropical cyclone",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_day(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def backwards_windows(start: datetime, end: datetime, days: int) -> Iterable[tuple[datetime, datetime]]:
    cursor = end
    while cursor > start:
        window_start = max(start, cursor - timedelta(days=days))
        yield window_start, cursor
        cursor = window_start


def backwards_epoch_windows(start: int, end: int, days: int) -> Iterable[tuple[int, int]]:
    cursor = end
    window_seconds = days * 86400
    while cursor >= start:
        window_start = max(start, cursor - window_seconds)
        yield window_start, cursor
        cursor = window_start - 1


class HistoryClient(PublicClient):
    def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        for attempt in range(self.retries):
            try:
                response = self.session.post(url, json=payload, timeout=self.timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < self.retries:
                        time.sleep(2**attempt)
                        continue
                response.raise_for_status()
                return response.json()
            except requests.RequestException:
                if attempt + 1 == self.retries:
                    raise
                time.sleep(2**attempt)
        raise RuntimeError("request retries exhausted")


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS contracts (
                platform TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                event_id TEXT,
                series_id TEXT,
                classification TEXT NOT NULL,
                title TEXT,
                opened_at TEXT,
                closed_at TEXT,
                outcome_ids_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                PRIMARY KEY (platform, contract_id)
            );
            CREATE INDEX IF NOT EXISTS contracts_closed_at
                ON contracts(platform, closed_at DESC);
            CREATE TABLE IF NOT EXISTS discovery_jobs (
                platform TEXT NOT NULL,
                job_key TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                rows_found INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (platform, job_key)
            );
            CREATE TABLE IF NOT EXISTS history_jobs (
                platform TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                rows_found INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (platform, contract_id, stage)
            );
            CREATE TABLE IF NOT EXISTS price_points (
                platform TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                outcome_id TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                price TEXT,
                raw_json TEXT NOT NULL,
                PRIMARY KEY (platform, contract_id, outcome_id, timestamp)
            );
            CREATE TABLE IF NOT EXISTS trades (
                platform TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                trade_id TEXT NOT NULL,
                timestamp TEXT,
                side TEXT,
                price TEXT,
                size TEXT,
                raw_json TEXT NOT NULL,
                PRIMARY KEY (platform, contract_id, trade_id)
            );
            CREATE TABLE IF NOT EXISTS run_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                arguments_json TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def job_done(self, table: str, platform: str, key: str, stage: str | None = None) -> bool:
        if table == "discovery_jobs":
            row = self.connection.execute(
                "SELECT status FROM discovery_jobs WHERE platform=? AND job_key=?",
                (platform, key),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT status FROM history_jobs WHERE platform=? AND contract_id=? AND stage=?",
                (platform, key, stage),
            ).fetchone()
        return bool(row and row["status"] == "complete")

    def discovery_result(self, platform: str, key: str, status: str, rows: int, error: str | None = None) -> None:
        self.connection.execute(
            """INSERT INTO discovery_jobs(platform,job_key,status,attempts,rows_found,error,updated_at)
               VALUES(?,?,?,1,?,?,?)
               ON CONFLICT(platform,job_key) DO UPDATE SET
                 status=excluded.status, attempts=discovery_jobs.attempts+1,
                 rows_found=excluded.rows_found, error=excluded.error,
                 updated_at=excluded.updated_at""",
            (platform, key, status, rows, error, utc_now()),
        )
        self.connection.commit()

    def history_result(self, platform: str, key: str, stage: str, status: str,
                       rows: int, error: str | None = None) -> None:
        self.connection.execute(
            """INSERT INTO history_jobs(platform,contract_id,stage,status,attempts,rows_found,error,updated_at)
               VALUES(?,?,?,?,1,?,?,?)
               ON CONFLICT(platform,contract_id,stage) DO UPDATE SET
                 status=excluded.status, attempts=history_jobs.attempts+1,
                 rows_found=excluded.rows_found, error=excluded.error,
                 updated_at=excluded.updated_at""",
            (platform, key, stage, status, rows, error, utc_now()),
        )
        self.connection.commit()

    def upsert_contract(self, row: dict[str, Any]) -> None:
        self.connection.execute(
            """INSERT INTO contracts(
                 platform,contract_id,event_id,series_id,classification,title,
                 opened_at,closed_at,outcome_ids_json,metadata_json,discovered_at)
               VALUES(:platform,:contract_id,:event_id,:series_id,:classification,:title,
                 :opened_at,:closed_at,:outcome_ids_json,:metadata_json,:discovered_at)
               ON CONFLICT(platform,contract_id) DO UPDATE SET
                 event_id=excluded.event_id, series_id=excluded.series_id,
                 classification=excluded.classification, title=excluded.title,
                 opened_at=excluded.opened_at, closed_at=excluded.closed_at,
                 outcome_ids_json=excluded.outcome_ids_json,
                 metadata_json=excluded.metadata_json,
                 discovered_at=excluded.discovered_at""",
            row,
        )

    def contracts(self, platform: str, start: str, end: str, stage: str,
                  limit: int | None = None, classification: str | None = None) -> list[sqlite3.Row]:
        sql = """SELECT c.* FROM contracts c
                 LEFT JOIN history_jobs j ON j.platform=c.platform
                   AND j.contract_id=c.contract_id AND j.stage=?
                 WHERE c.platform=? AND c.closed_at>=? AND c.closed_at<?
                   AND COALESCE(j.status,'') NOT IN ('complete','unavailable')"""
        params: list[Any] = [stage, platform, start, end]
        if classification:
            sql += " AND (';'||c.classification||';') LIKE ?"
            params.append(f"%;{classification};%")
        sql += " ORDER BY c.closed_at DESC, c.contract_id"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.connection.execute(sql, params))

    def add_price_points(self, rows: Iterable[tuple[Any, ...]]) -> int:
        before = self.connection.total_changes
        self.connection.executemany(
            """INSERT OR IGNORE INTO price_points
               (platform,contract_id,outcome_id,timestamp,price,raw_json)
               VALUES(?,?,?,?,?,?)""",
            rows,
        )
        return self.connection.total_changes - before

    def add_trades(self, rows: Iterable[tuple[Any, ...]]) -> int:
        before = self.connection.total_changes
        self.connection.executemany(
            """INSERT OR IGNORE INTO trades
               (platform,contract_id,trade_id,timestamp,side,price,size,raw_json)
               VALUES(?,?,?,?,?,?,?,?)""",
            rows,
        )
        return self.connection.total_changes - before

    def start_run(self, arguments: dict[str, Any]) -> int:
        cursor = self.connection.execute(
            "INSERT INTO run_log(started_at,arguments_json,status) VALUES(?,?,?)",
            (utc_now(), json.dumps(arguments, sort_keys=True), "running"),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, summary: dict[str, Any]) -> None:
        self.connection.execute(
            "UPDATE run_log SET finished_at=?,status=?,summary_json=? WHERE id=?",
            (utc_now(), status, json.dumps(summary, sort_keys=True), run_id),
        )
        self.connection.commit()

    def summary(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for table in ("contracts", "price_points", "trades"):
            result[table] = {
                row["platform"]: row["count"]
                for row in self.connection.execute(
                    f"SELECT platform,COUNT(*) AS count FROM {table} GROUP BY platform"
                )
            }
        result["pending_or_failed"] = [
            dict(row) for row in self.connection.execute(
                """SELECT platform,stage,status,COUNT(*) AS count FROM history_jobs
                   WHERE status NOT IN ('complete','unavailable')
                   GROUP BY platform,stage,status"""
            )
        ]
        return result


def effective_close(metadata: dict[str, Any]) -> str:
    return str(
        metadata.get("settlement_ts") or metadata.get("close_time")
        or metadata.get("endDate") or metadata.get("expiration_time") or ""
    )


def in_window(value: str, start: datetime, end: datetime) -> bool:
    if not value:
        return False
    timestamp = _epoch(value, -1)
    return int(start.timestamp()) <= timestamp < int(end.timestamp())


def discover_kalshi(store: Store, client: HistoryClient, start: datetime, end: datetime,
                    classification: str | None = None) -> int:
    payload = client.json(f"{KALSHI_BASE}/series", {"category": "Climate and Weather"})
    series_rows = []
    for series in payload.get("series", []):
        classes = classify_weather_contract(series.get("title"), series.get("ticker"))
        if classes and (not classification or classification in classes):
            series_rows.append(series)
    inserted = 0
    for number, series in enumerate(sorted(series_rows, key=lambda row: str(row.get("ticker"))), 1):
        series_id = str(series.get("ticker") or "")
        job_key = f"{classification or 'all'}:{series_id}"
        if not series_id or store.job_done("discovery_jobs", "kalshi", job_key):
            continue
        try:
            archived = _paginate_cursor(
                client, f"{KALSHI_BASE}/historical/markets", "markets",
                {"series_ticker": series_id, "limit": 1000},
            )
            recent = _paginate_cursor(
                client, f"{KALSHI_BASE}/markets", "markets",
                {"series_ticker": series_id, "limit": 1000},
            )
            markets = {str(row.get("ticker")): row for row in [*archived, *recent] if row.get("ticker")}
            found = 0
            for market in markets.values():
                closed_at = effective_close(market)
                if not in_window(closed_at, start, end):
                    continue
                classes = classify_weather_contract(
                    series.get("title"), market.get("title"), market.get("subtitle"),
                    market.get("yes_sub_title"), market.get("rules_primary"),
                )
                if not classes:
                    continue
                if classification and classification not in classes:
                    continue
                store.upsert_contract({
                    "platform": "kalshi", "contract_id": str(market["ticker"]),
                    "event_id": str(market.get("event_ticker") or ""),
                    "series_id": series_id, "classification": ";".join(classes),
                    "title": market.get("title"),
                    "opened_at": market.get("open_time") or market.get("created_time"),
                    "closed_at": closed_at, "outcome_ids_json": "[]",
                    "metadata_json": json.dumps(market, sort_keys=True),
                    "discovered_at": utc_now(),
                })
                found += 1
            store.connection.commit()
            store.discovery_result("kalshi", job_key, "complete", found)
            inserted += found
            print(f"[discover kalshi {number}/{len(series_rows)}] {series_id}: {found}", flush=True)
        except Exception as exc:
            store.discovery_result("kalshi", job_key, "error", 0, str(exc))
            print(f"[discover kalshi error] {series_id}: {exc}", flush=True)
    return inserted


def historical_polymarket_rows(events: list[dict[str, Any]], start: datetime,
                               end: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        event_metadata = {key: value for key, value in event.items() if key != "markets"}
        for market in event.get("markets", []):
            closed_at = str(market.get("endDate") or event.get("endDate") or "")
            if not in_window(closed_at, start, end):
                continue
            classes = classify_weather_contract(
                event.get("title"), event.get("description"), market.get("question"),
                market.get("description"), market.get("groupItemTitle"),
            )
            if not classes:
                continue
            token_ids = [str(value) for value in _json_list(market.get("clobTokenIds"))]
            rows.append({
                "platform": "polymarket", "contract_id": str(market.get("id") or ""),
                "event_id": str(event.get("id") or ""), "series_id": "",
                "classification": ";".join(classes),
                "title": market.get("question") or event.get("title"),
                "opened_at": market.get("startDate") or event.get("startDate")
                    or market.get("createdAt") or event.get("creationDate"),
                "closed_at": closed_at,
                "outcome_ids_json": json.dumps(token_ids, separators=(",", ":")),
                "metadata_json": json.dumps(
                    {"event": event_metadata, "market": market}, sort_keys=True
                ),
                "discovered_at": utc_now(),
            })
    return [row for row in rows if row["contract_id"]]


def discover_polymarket(store: Store, client: HistoryClient, start: datetime,
                        end: datetime, window_days: int,
                        classification: str | None = None) -> int:
    inserted = 0
    search_terms = POLYMARKET_SEARCH_TERMS
    if classification == "city_temperature":
        search_terms = ("temperature",)
    elif classification == "hurricane_or_named_storm":
        search_terms = tuple(term for term in search_terms if term != "temperature")
    for window_start, window_end in backwards_windows(start, end, window_days):
        key = f"{classification or 'all'}:{window_start.date()}_{window_end.date()}"
        if store.job_done("discovery_jobs", "polymarket", key):
            continue
        try:
            event_map: dict[str, dict[str, Any]] = {}
            for search_term in search_terms:
                matches = _paginate_keyset(
                    client, f"{POLYMARKET_GAMMA}/events/keyset", "events",
                    {
                        "closed": "true", "end_date_min": window_start.isoformat(),
                        "end_date_max": window_end.isoformat(), "order": "endDate",
                        "ascending": "false", "title_search": search_term,
                    }, page_size=500,
                )
                for event in matches:
                    event_id = str(event.get("id") or event.get("slug") or "")
                    if event_id:
                        event_map[event_id] = event
            events = list(event_map.values())
            rows = historical_polymarket_rows(events, window_start, window_end)
            if classification:
                rows = [
                    row for row in rows
                    if classification in row["classification"].split(";")
                ]
            for row in rows:
                store.upsert_contract(row)
            store.connection.commit()
            store.discovery_result("polymarket", key, "complete", len(rows))
            inserted += len(rows)
            print(f"[discover polymarket] {key}: {len(events)} events, {len(rows)} contracts", flush=True)
        except Exception as exc:
            store.discovery_result("polymarket", key, "error", 0, str(exc))
            print(f"[discover polymarket error] {key}: {exc}", flush=True)
    return inserted


def paginated_trades(client: HistoryClient, url: str, collection: str,
                     params: dict[str, Any]) -> list[dict[str, Any]]:
    return _paginate_cursor(client, url, collection, {**params, "limit": 1000})


def backfill_kalshi(store: Store, client: HistoryClient, start: datetime,
                    end: datetime, stages: set[str], limit: int | None,
                    classification: str | None) -> None:
    cutoff = client.json(f"{KALSHI_BASE}/historical/cutoff")
    market_cutoff = _epoch(cutoff.get("market_settled_ts"), 0)
    trade_cutoff = _epoch(cutoff.get("trades_created_ts"), 0)
    for stage in sorted(stages):
        contracts = store.contracts(
            "kalshi", start.isoformat(), end.isoformat(), stage, limit, classification
        )
        for number, contract in enumerate(contracts, 1):
            contract_id = contract["contract_id"]
            opened = _epoch(contract["opened_at"], int(start.timestamp()))
            closed = _epoch(contract["closed_at"], int(end.timestamp()))
            try:
                if stage == "prices":
                    historical_url = (
                        f"{KALSHI_BASE}/historical/markets/{contract_id}/candlesticks"
                    )
                    recent_url = (
                        f"{KALSHI_BASE}/series/{contract['series_id']}/markets/"
                        f"{contract_id}/candlesticks"
                    )
                    if closed < market_cutoff:
                        url, alternate_url = historical_url, recent_url
                    else:
                        url, alternate_url = recent_url, historical_url
                    candle_params = {
                        "start_ts": opened, "end_ts": closed, "period_interval": 1440,
                    }
                    try:
                        payload = client.json(url, candle_params)
                    except requests.HTTPError as exc:
                        if exc.response is None or exc.response.status_code != 404:
                            raise
                        payload = client.json(alternate_url, candle_params)
                    points = []
                    for candle in payload.get("candlesticks", []):
                        timestamp = int(candle.get("end_period_ts") or 0)
                        if not timestamp:
                            continue
                        price = candle.get("price") or {}
                        points.append((
                            "kalshi", contract_id, "yes", timestamp,
                            price.get("close_dollars", price.get("close")),
                            json.dumps(candle, sort_keys=True),
                        ))
                    added = store.add_price_points(points)
                else:
                    trade_rows: list[dict[str, Any]] = []
                    if opened < trade_cutoff:
                        trade_rows.extend(paginated_trades(
                            client, f"{KALSHI_BASE}/historical/trades", "trades",
                            {"ticker": contract_id, "min_ts": opened,
                             "max_ts": min(closed, trade_cutoff - 1)},
                        ))
                    if closed >= trade_cutoff:
                        trade_rows.extend(paginated_trades(
                            client, f"{KALSHI_BASE}/markets/trades", "trades",
                            {"ticker": contract_id, "min_ts": max(opened, trade_cutoff),
                             "max_ts": closed},
                        ))
                    rows = []
                    for trade in trade_rows:
                        trade_id = str(trade.get("trade_id") or "")
                        if not trade_id:
                            continue
                        rows.append((
                            "kalshi", contract_id, trade_id, trade.get("created_time"),
                            trade.get("taker_side") or trade.get("taker_outcome_side"),
                            trade.get("yes_price_dollars"), trade.get("count_fp"),
                            json.dumps(trade, sort_keys=True),
                        ))
                    added = store.add_trades(rows)
                store.history_result("kalshi", contract_id, stage, "complete", added)
                print(f"[kalshi {stage} {number}/{len(contracts)}] {contract_id}: {added}", flush=True)
            except requests.HTTPError as exc:
                if stage == "prices" and exc.response is not None and exc.response.status_code == 404:
                    store.history_result(
                        "kalshi", contract_id, stage, "unavailable", 0,
                        "No candlestick archive in either Kalshi tier (HTTP 404)",
                    )
                    print(f"[kalshi {stage} unavailable] {contract_id}: HTTP 404", flush=True)
                    continue
                store.history_result("kalshi", contract_id, stage, "error", 0, str(exc))
                print(f"[kalshi {stage} error] {contract_id}: {exc}", flush=True)
            except Exception as exc:
                store.history_result("kalshi", contract_id, stage, "error", 0, str(exc))
                print(f"[kalshi {stage} error] {contract_id}: {exc}", flush=True)


def polymarket_price_batches(contracts: list[sqlite3.Row], size: int = 20) -> Iterable[list[sqlite3.Row]]:
    batch: list[sqlite3.Row] = []
    token_count = 0
    for contract in contracts:
        count = len(_json_list(contract["outcome_ids_json"]))
        if batch and token_count + count > size:
            yield batch
            batch, token_count = [], 0
        batch.append(contract)
        token_count += count
    if batch:
        yield batch


def backfill_polymarket_prices(store: Store, client: HistoryClient, start: datetime,
                               end: datetime, limit: int | None,
                               classification: str | None) -> None:
    contracts = store.contracts(
        "polymarket", start.isoformat(), end.isoformat(), "prices", limit, classification
    )
    for number, batch in enumerate(polymarket_price_batches(contracts), 1):
        tokens = [
            str(token) for contract in batch
            for token in _json_list(contract["outcome_ids_json"])
        ]
        if not tokens:
            for contract in batch:
                store.history_result("polymarket", contract["contract_id"], "prices", "complete", 0)
            continue
        try:
            batch_start = max(
                int(start.timestamp()),
                min(_epoch(contract["opened_at"], int(start.timestamp())) for contract in batch),
            )
            batch_end = min(
                int(end.timestamp()),
                max(_epoch(contract["closed_at"], int(end.timestamp())) for contract in batch),
            )
            histories: dict[str, list[dict[str, Any]]] = {token: [] for token in tokens}
            for window_start, window_end in backwards_epoch_windows(
                    batch_start, batch_end, 7):
                payload = client.post_json(f"{POLYMARKET_CLOB}/batch-prices-history", {
                    "markets": tokens, "start_ts": window_start,
                    "end_ts": window_end, "fidelity": 60,
                })
                for token, points in payload.get("history", {}).items():
                    histories.setdefault(str(token), []).extend(points)
            for contract in batch:
                rows = []
                for token in _json_list(contract["outcome_ids_json"]):
                    for point in histories.get(str(token), []):
                        timestamp = int(point.get("t") or 0)
                        if timestamp:
                            rows.append((
                                "polymarket", contract["contract_id"], str(token), timestamp,
                                point.get("p"), json.dumps(point, sort_keys=True),
                            ))
                added = store.add_price_points(rows)
                store.history_result(
                    "polymarket", contract["contract_id"], "prices", "complete", added
                )
            print(f"[polymarket prices batch {number}] {len(batch)} contracts, {len(tokens)} tokens", flush=True)
        except Exception as exc:
            for contract in batch:
                store.history_result(
                    "polymarket", contract["contract_id"], "prices", "error", 0, str(exc)
                )
            print(f"[polymarket prices error] {exc}", flush=True)


def backfill_polymarket_trades(store: Store, client: HistoryClient, start: datetime,
                               end: datetime, limit: int | None,
                               classification: str | None) -> None:
    contracts = store.contracts(
        "polymarket", start.isoformat(), end.isoformat(), "trades", limit, classification
    )
    for number, contract in enumerate(contracts, 1):
        metadata = json.loads(contract["metadata_json"])
        condition_id = str(metadata.get("market", {}).get("conditionId") or "")
        if not condition_id:
            store.history_result("polymarket", contract["contract_id"], "trades", "complete", 0)
            continue
        try:
            payload = _polymarket_trades(
                client, condition_id, int(start.timestamp()), int(end.timestamp())
            )
            rows = []
            for trade in payload:
                trade_id = ":".join(
                    str(trade.get(field) or "") for field in
                    ("transactionHash", "asset", "timestamp", "side", "size")
                )
                rows.append((
                    "polymarket", contract["contract_id"], trade_id,
                    str(trade.get("timestamp") or ""), trade.get("side"),
                    trade.get("price"), trade.get("size"), json.dumps(trade, sort_keys=True),
                ))
            added = store.add_trades(rows)
            store.history_result("polymarket", contract["contract_id"], "trades", "complete", added)
            print(f"[polymarket trades {number}/{len(contracts)}] {contract['contract_id']}: {added}", flush=True)
        except Exception as exc:
            store.history_result("polymarket", contract["contract_id"], "trades", "error", 0, str(exc))
            print(f"[polymarket trades error] {contract['contract_id']}: {exc}", flush=True)


def main() -> int:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--since", default=f"{today.year - 10:04d}-{today.month:02d}-{today.day:02d}")
    parser.add_argument("--until", default=(today + timedelta(days=1)).isoformat())
    parser.add_argument("--platform", action="append", choices=("kalshi", "polymarket"))
    parser.add_argument("--stage", choices=("discovery", "prices", "trades", "all"), default="all")
    parser.add_argument("--discovery-window-days", type=int, default=180)
    parser.add_argument("--max-contracts", type=int, default=0,
                        help="Limit each platform/stage for a smoke run; zero means all")
    parser.add_argument(
        "--classification", choices=("hurricane_or_named_storm", "city_temperature"),
        help="Backfill one class after discovering the complete weather universe",
    )
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    start, end = parse_day(args.since), parse_day(args.until)
    if start >= end:
        parser.error("--since must be earlier than --until")
    platforms = set(args.platform or ("kalshi", "polymarket"))
    stages = {"prices", "trades"} if args.stage == "all" else {args.stage}
    limit = args.max_contracts or None
    store = Store(args.database)
    client = HistoryClient(timeout=args.timeout)
    run_id = store.start_run({
        "since": args.since, "until": args.until, "platforms": sorted(platforms),
        "stage": args.stage, "max_contracts": args.max_contracts,
        "classification": args.classification,
    })
    status = "complete"
    try:
        if args.stage in ("all", "discovery"):
            if "kalshi" in platforms:
                discover_kalshi(store, client, start, end, args.classification)
            if "polymarket" in platforms:
                discover_polymarket(
                    store, client, start, end, args.discovery_window_days,
                    args.classification,
                )
        if args.stage != "discovery":
            if "kalshi" in platforms:
                backfill_kalshi(
                    store, client, start, end, stages, limit, args.classification
                )
            if "polymarket" in platforms:
                if "prices" in stages:
                    backfill_polymarket_prices(
                        store, client, start, end, limit, args.classification
                    )
                if "trades" in stages:
                    backfill_polymarket_trades(
                        store, client, start, end, limit, args.classification
                    )
    except KeyboardInterrupt:
        status = "interrupted"
        print("Interrupted; completed jobs are checkpointed and will be skipped on resume.", flush=True)
    except Exception as exc:
        status = "error"
        print(f"Fatal error: {exc}", flush=True)
    summary = store.summary()
    store.finish_run(run_id, status, summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    store.close()
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
