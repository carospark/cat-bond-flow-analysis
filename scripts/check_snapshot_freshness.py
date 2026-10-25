#!/usr/bin/env python3
"""Report the last snapshot date per nightly source and fail when one is stale.

The two LaunchAgents write dated directories under ``data/raw/tier1/<date>/``
(the daily snapshot) and completed runs into the ``run_log`` table of the
prediction-market history database (the batch). This script reads only
those local artefacts, prints one line per source with the last date seen and
its age, and exits non-zero when any source is older than ``--max-age-days``
(default two days) or has never been seen. It never touches the network.

Usage::

    ./.venv/bin/python scripts/check_snapshot_freshness.py
    ./.venv/bin/python scripts/check_snapshot_freshness.py --as-of 2026-10-25

A dated directory counts as a snapshot for a source only when the source's
subdirectory holds at least one non-empty file, so a run that created the
directory and died before writing does not count.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_ROOT = ROOT / "data" / "raw" / "tier1"
DEFAULT_DATABASE = DEFAULT_RAW_ROOT / "prediction_market_history.sqlite3"
DEFAULT_MARKET_CONFIG = ROOT / "config" / "market_signal_sources.json"
DEFAULT_TIER1_CONFIG = ROOT / "config" / "tier1_sources.json"
DEFAULT_LOCKS = (
    ROOT / "data" / ".daily-non-artemis-pull.lock",
    ROOT / "data" / ".prediction-history-batch.lock",
)
DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HISTORY_PLATFORMS = ("kalshi", "polymarket")


@dataclass
class Freshness:
    source: str
    last_date: Optional[date]
    age_days: Optional[int]
    stale: bool

    @property
    def status(self) -> str:
        if self.last_date is None:
            return "MISSING"
        return "STALE" if self.stale else "ok"


def daily_source_ids(market_config: Path, tier1_config: Path) -> list[str]:
    """Sources the nightly runner is responsible for: every market-signal
    source plus the Tier 1 sources whose refresh cadence says daily."""
    ids: list[str] = []
    if market_config.exists():
        payload = json.loads(market_config.read_text(encoding="utf-8"))
        ids.extend(source["id"] for source in payload["sources"])
    if tier1_config.exists():
        payload = json.loads(tier1_config.read_text(encoding="utf-8"))
        sources = payload["sources"] if isinstance(payload, dict) else payload
        ids.extend(
            source["id"] for source in sources
            if "daily" in str(source.get("refresh", source.get("frequency", ""))).lower()
        )
    return sorted(dict.fromkeys(ids))


def _has_content(directory: Path) -> bool:
    return any(path.is_file() and path.stat().st_size > 0 for path in directory.iterdir())


def last_snapshot_date(raw_root: Path, source_id: str) -> Optional[date]:
    """Newest dated directory under raw_root whose source folder has content."""
    if not raw_root.is_dir():
        return None
    candidates = sorted(
        (child for child in raw_root.iterdir() if child.is_dir() and DATE_DIR.match(child.name)),
        key=lambda child: child.name,
        reverse=True,
    )
    for child in candidates:
        source_dir = child / source_id
        if source_dir.is_dir() and _has_content(source_dir):
            return date.fromisoformat(child.name)
    return None


def last_history_run(database: Path, platform: str) -> Optional[date]:
    """Date of the newest completed batch run that named the platform."""
    if not database.is_file():
        return None
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT finished_at, arguments_json FROM run_log "
            "WHERE status = 'complete' AND finished_at IS NOT NULL "
            "ORDER BY finished_at DESC"
        ).fetchall()
    except sqlite3.DatabaseError:
        return None
    finally:
        connection.close()
    for finished_at, arguments_json in rows:
        try:
            platforms = json.loads(arguments_json).get("platforms") or list(HISTORY_PLATFORMS)
        except (TypeError, ValueError):
            platforms = list(HISTORY_PLATFORMS)
        if platform in platforms:
            return datetime.fromisoformat(finished_at).date()
    return None


def assess(source: str, last: Optional[date], as_of: date, max_age_days: int) -> Freshness:
    if last is None:
        return Freshness(source, None, None, True)
    age = (as_of - last).days
    return Freshness(source, last, age, age > max_age_days)


def check(
    raw_root: Path,
    database: Path,
    as_of: date,
    max_age_days: int,
    daily_sources: Iterable[str],
) -> list[Freshness]:
    results = [
        assess(source, last_snapshot_date(raw_root, source), as_of, max_age_days)
        for source in daily_sources
    ]
    results.extend(
        assess(
            f"prediction_market_history:{platform}",
            last_history_run(database, platform),
            as_of,
            max_age_days,
        )
        for platform in HISTORY_PLATFORMS
    )
    return results


def lock_state(lock_dir: Path) -> Optional[str]:
    """Describe a runner lock: absent, held by a live pid, or left by a dead one."""
    if not lock_dir.exists():
        return None
    try:
        pid = int((lock_dir / "pid").read_text().strip())
    except (OSError, ValueError):
        return f"{lock_dir.name}: present, no readable pid (stale; the runner will clear it)"
    try:
        import os
        os.kill(pid, 0)
    except ProcessLookupError:
        return f"{lock_dir.name}: left by dead pid {pid} (stale; the runner will clear it)"
    except PermissionError:
        pass
    return f"{lock_dir.name}: held by live pid {pid}"


def render(results: list[Freshness], as_of: date, max_age_days: int) -> str:
    width = max(len(item.source) for item in results)
    lines = [f"snapshot freshness as of {as_of.isoformat()} (stale after {max_age_days} days)"]
    for item in results:
        last = item.last_date.isoformat() if item.last_date else "never"
        age = f"{item.age_days:>3}d" if item.age_days is not None else "   -"
        lines.append(f"  {item.source:<{width}}  {last}  {age}  {item.status}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--market-config", type=Path, default=DEFAULT_MARKET_CONFIG)
    parser.add_argument("--tier1-config", type=Path, default=DEFAULT_TIER1_CONFIG)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--max-age-days", type=int, default=2)
    parser.add_argument("--lock", type=Path, action="append", default=None,
                        help="runner lock directories to describe (default: both runners')")
    args = parser.parse_args(argv)

    sources = daily_source_ids(args.market_config, args.tier1_config)
    results = check(args.raw_root, args.database, args.as_of, args.max_age_days, sources)
    print(render(results, args.as_of, args.max_age_days))
    for lock_dir in (args.lock if args.lock is not None else DEFAULT_LOCKS):
        state = lock_state(lock_dir)
        if state:
            print(f"  lock {state}")
    failing = [item for item in results if item.stale]
    if failing:
        print(f"{len(failing)} of {len(results)} sources stale or missing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
