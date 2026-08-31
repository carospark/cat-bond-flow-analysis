"""Archive Tier 1 reference sources and normalize the directly published tables.

Raw third-party payloads and derived snapshots are written under data/raw,
which is intentionally gitignored. The tracked source registry lives in
config/tier1_sources.json and the human-readable inventory in data/MANIFEST.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_module
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "tier1_sources.json"
DEFAULT_RAW_ROOT = ROOT / "data" / "raw" / "tier1"
USER_AGENT = (
    "catbond-map/0.1 (academic research; public source archiver; "
    "contact caropark4@gmail.com)"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_with_ils_index(html_path: Path, output_dir: Path) -> list[Path]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or script.string is None:
        raise ValueError("With Intelligence page does not contain __NEXT_DATA__")

    page_data = json.loads(script.string)
    cache = page_data["props"]["pageProps"]["ssrCache"]
    candidates = [
        value
        for value in cache.values()
        if isinstance(value, dict)
        and value.get("__typename") == "DomFundIndex"
        and value.get("id") == "11750"
        and value.get("monthlyReturns")
    ]
    if not candidates:
        raise ValueError("Could not find monthly returns for index 11750")

    monthly = candidates[0]["monthlyReturns"]
    rows = [
        {
            "date": row["date"],
            "monthly_return": row["performance"],
            "funds_calculated": row.get("calculatedFunds"),
            "constituent_fraction_reported": row.get("percentage"),
        }
        for row in monthly
    ]
    if len(rows) < 200 or rows[0]["date"] != "2006-01-01":
        raise ValueError("Unexpected With Intelligence index coverage")

    output = output_dir / "monthly_returns.csv"
    write_csv(
        output,
        [
            "date",
            "monthly_return",
            "funds_calculated",
            "constituent_fraction_reported",
        ],
        rows,
    )
    return [output]


def _table_rows(table: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows


def parse_brookmont_ils(html_path: Path, output_dir: Path) -> list[Path]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    outputs: list[Path] = []

    holdings_table = soup.find("table", id="etfg-holdings-data-table")
    if holdings_table is None:
        raise ValueError("Brookmont holdings table was not found")
    holdings_rows = _table_rows(holdings_table)
    if len(holdings_rows) < 2:
        raise ValueError("Brookmont holdings table is empty")
    holdings = output_dir / "holdings.csv"
    write_csv(
        holdings,
        ["holding_name", "ticker", "figi", "quantity", "market_value", "pct_nav"],
        [dict(zip(
            ["holding_name", "ticker", "figi", "quantity", "market_value", "pct_nav"],
            row,
        )) for row in holdings_rows[1:] if len(row) == 6],
    )
    outputs.append(holdings)

    chart = soup.find(attrs={"data-series": True, "data-ticker": "ILS"})
    if chart is None:
        raise ValueError("Brookmont NAV history data-series was not found")
    series = json.loads(html_module.unescape(chart["data-series"]))
    series.sort(key=lambda row: row["date"])
    # The issuer currently prepends a 2025-03-31 baseline observation even
    # though the stated fund inception date is 2025-04-01.
    if not series or series[0]["date"] not in {"2025-03-31", "2025-04-01"}:
        raise ValueError("Unexpected Brookmont NAV history coverage")
    nav = output_dir / "daily_nav.csv"
    write_csv(
        nav,
        ["date", "market_price", "nav", "premium_discount_pct"],
        series,
    )
    outputs.append(nav)

    details_section = soup.select_one(".etfg-details-section")
    nav_table = soup.find("table", id="etfg-nav-data-table")
    holdings_date = soup.find(id="etfg-holdings-date")
    metadata = {
        "holdings_as_of": holdings_date.get_text(" ", strip=True) if holdings_date else None,
        "fund_details": _table_rows(details_section.find("table")) if details_section else [],
        "current_nav_metrics": _table_rows(nav_table) if nav_table else [],
    }
    metadata_path = output_dir / "fund_snapshot.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    outputs.append(metadata_path)
    return outputs


PARSERS = {
    "with_ils_index": parse_with_ils_index,
    "brookmont_ils": parse_brookmont_ils,
}


def download(source: dict[str, Any], output_dir: Path, timeout: int) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / source["filename"]
    response = requests.get(
        source["url"],
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=output_dir
    )
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(response.content)
        temporary_path = Path(temporary_name)
        if destination.suffix.lower() == ".pdf":
            with temporary_path.open("rb") as handle:
                signature = handle.read(5)
            if signature != b"%PDF-":
                raise ValueError(
                    f"Expected PDF but publisher returned {response.headers.get('content-type', '')}"
                )
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return destination, response.headers.get("content-type", "")


def append_log(raw_root: Path, record: dict[str, Any]) -> None:
    raw_root.mkdir(parents=True, exist_ok=True)
    log_path = raw_root / "pull_log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    latest: dict[str, dict[str, Any]] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        latest[item["source_id"]] = item
    status_path = raw_root / "latest_status.json"
    status_path.write_text(
        json.dumps({"sources": latest}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def pull_sources(
    config_path: Path,
    raw_root: Path,
    as_of: str,
    selected: set[str] | None,
    timeout: int,
) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sources = config["sources"]
    known = {source["id"] for source in sources}
    if selected:
        unknown = selected - known
        if unknown:
            raise ValueError(f"Unknown source id(s): {', '.join(sorted(unknown))}")
        sources = [source for source in sources if source["id"] in selected]

    failures = 0
    for source in sources:
        output_dir = raw_root / as_of / source["id"]
        pulled_at = datetime.now(timezone.utc).isoformat()
        record: dict[str, Any] = {
            "source_id": source["id"],
            "stage": source["stage"],
            "url": source["url"],
            "as_of": as_of,
            "pulled_at_utc": pulled_at,
        }
        try:
            payload, content_type = download(source, output_dir, timeout)
            derived = []
            parser_name = source.get("parser")
            if parser_name:
                derived = PARSERS[parser_name](payload, output_dir)
            record.update(
                {
                    "status": "ok",
                    "content_type": content_type,
                    "payload_path": str(payload.relative_to(ROOT)),
                    "payload_bytes": payload.stat().st_size,
                    "payload_sha256": sha256_file(payload),
                    "derived_paths": [str(path.relative_to(ROOT)) for path in derived],
                    "derived_sha256": {
                        str(path.relative_to(ROOT)): sha256_file(path) for path in derived
                    },
                }
            )
            print(f"[ok] {source['id']} -> {payload.relative_to(ROOT)}")
        except Exception as exc:  # continue so one publisher cannot stop the archive
            failures += 1
            record.update(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            print(f"[error] {source['id']}: {exc}", file=sys.stderr)
        append_log(raw_root, record)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--source", action="append", help="Pull only this source id; repeatable")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--list", action="store_true", help="List configured sources and exit")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.list:
        for source in config["sources"]:
            print(f"{source['id']}\t{source['stage']}\t{source['title']}")
        return 0
    return pull_sources(
        args.config,
        args.raw_root,
        args.as_of,
        set(args.source) if args.source else None,
        args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
