"""Archive Form N-PORT filings for the funds in config/fund_registry.json.

Each run writes the identifier screen it used, so the pull can be audited
and re-run from a file rather than a memory (lesson 1 in
notes/pending-setup-lessons.md):

    data/raw/sec_nport/screens/<as_of>_fund_screen.json   funds, CIKs, series IDs,
                                                           registry sha256
    data/raw/sec_nport/filings/<fund_id>/<accession>.xml   primary_doc.xml as served
    data/raw/sec_nport/filings/<fund_id>/filings.json      accession, dates, period,
                                                           series name, sha256
    data/raw/sec_nport/pull_log.jsonl                      one record per run
    data/raw/sec_nport/latest_status.json                  last outcome per fund

Filings are listed per series through EDGAR's company browser with the
series ID as the CIK parameter, which is what makes the multi-series trusts
(Stone Ridge Trust has 123 series, ETF Opportunities Trust 652) tractable.
Single-series registrants are listed by CIK. Every downloaded XML is checked
against the registry's series name, and a mismatch is recorded rather than
silently kept.

The pull is resumable: an accession whose XML is already on disk is skipped.
SEC asks for a User-Agent with contact details and at most ten requests a
second; this sends one request every 150 ms and backs off on 429 and 503.

Usage:

    ./.venv/bin/python src/pull_nport.py --as-of 2026-10-21
    ./.venv/bin/python src/pull_nport.py --fund stone_ridge_reinsurance_rrp_interval --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fund_registry import REGISTRY_PATH, USER_AGENT, load_registry, registry_sha256, sec_funds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = ROOT / "data" / "raw" / "sec_nport"
REQUEST_INTERVAL_SECONDS = 0.15
BROWSE_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ident}"
    "&type=NPORT-P&dateb=&owner=include&count=100&start={start}&output=atom"
)
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/primary_doc.xml"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class EdgarClient:
    """Rate-limited GET with the SEC's required User-Agent and retry on throttling."""

    def __init__(self, interval: float = REQUEST_INTERVAL_SECONDS, retries: int = 4) -> None:
        self.interval = interval
        self.retries = retries
        self._last = 0.0
        self.requests = 0

    def get(self, url: str) -> bytes:
        for attempt in range(self.retries + 1):
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = response.read()
                self._last = time.monotonic()
                self.requests += 1
                return payload
            except urllib.error.HTTPError as error:
                self._last = time.monotonic()
                if error.code in (429, 503) and attempt < self.retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise


def parse_atom_filings(payload: bytes) -> list[dict[str, str]]:
    """Accession numbers and filing dates from an EDGAR Atom filing list."""
    text = payload.decode("utf-8", "replace")
    entries = []
    for block in re.findall(r"<entry>(.*?)</entry>", text, flags=re.S):
        accession = re.search(r"<accession-number>([\d-]+)</accession-number>", block)
        filed = re.search(r"<filing-date>([\d-]+)</filing-date>", block)
        form = re.search(r'term="([^"]+)"', block)
        if accession and filed:
            entries.append(
                {
                    "accession": accession.group(1),
                    "filing_date": filed.group(1),
                    "form": form.group(1) if form else "",
                }
            )
    return entries


def list_filings(client: EdgarClient, identifier: str) -> list[dict[str, str]]:
    """All public N-PORT filings for a CIK or series ID, newest first."""
    filings: list[dict[str, str]] = []
    start = 0
    while True:
        page = parse_atom_filings(client.get(BROWSE_URL.format(ident=identifier, start=start)))
        page = [entry for entry in page if entry["form"] == "NPORT-P"]
        filings.extend(page)
        if len(page) < 100:
            break
        start += 100
    seen = set()
    unique = []
    for entry in filings:
        if entry["accession"] not in seen:
            seen.add(entry["accession"])
            unique.append(entry)
    return unique


def strip_namespaces(root: ET.Element) -> ET.Element:
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    return root


def filing_header(payload: bytes) -> dict[str, str | None]:
    """Series name, series ID, and report period from a primary_doc.xml."""
    root = strip_namespaces(ET.fromstring(payload))

    def text(tag: str) -> str | None:
        element = root.find(f".//{tag}")
        return element.text.strip() if element is not None and element.text else None

    return {
        "series_name": text("seriesName"),
        "series_id": text("seriesId") or None,
        "period_end": text("repPdDate"),
        "registrant": text("regName"),
    }


def write_screen(raw_root: Path, as_of: str, funds: list[dict[str, Any]], registry_path: Path) -> Path:
    screen_dir = raw_root / "screens"
    screen_dir.mkdir(parents=True, exist_ok=True)
    screen = {
        "as_of": as_of,
        "registry_path": str(registry_path.relative_to(ROOT)) if registry_path.is_relative_to(ROOT) else str(registry_path),
        "registry_sha256": registry_sha256(registry_path),
        "funds": [
            {
                "fund_id": fund["id"],
                "cik": fund["cik"],
                "series_id": fund["series_id"],
                "series_name_in_filing": fund["series_name_in_filing"],
                "edgar_identifier": fund["series_id"] or fund["cik"],
            }
            for fund in funds
        ],
    }
    path = screen_dir / f"{as_of}_fund_screen.json"
    path.write_text(json.dumps(screen, indent=2) + "\n", encoding="utf-8")
    return path


def pull_fund(
    client: EdgarClient, raw_root: Path, fund: dict[str, Any], dry_run: bool = False
) -> dict[str, Any]:
    fund_dir = raw_root / "filings" / fund["id"]
    index_path = fund_dir / "filings.json"
    existing: dict[str, dict[str, Any]] = {}
    if index_path.exists():
        existing = {row["accession"]: row for row in json.loads(index_path.read_text(encoding="utf-8"))}

    identifier = fund["series_id"] or fund["cik"]
    listed = list_filings(client, identifier)
    record: dict[str, Any] = {
        "fund_id": fund["id"],
        "edgar_identifier": identifier,
        "listed": len(listed),
        "downloaded": 0,
        "skipped_existing": 0,
        "series_mismatch": [],
        "errors": [],
    }
    if dry_run:
        record["status"] = "dry_run"
        return record

    fund_dir.mkdir(parents=True, exist_ok=True)
    expected_name = fund["series_name_in_filing"].lower()
    for entry in listed:
        accession = entry["accession"]
        xml_path = fund_dir / f"{accession}.xml"
        if accession in existing and xml_path.exists():
            record["skipped_existing"] += 1
            continue
        url = ARCHIVE_URL.format(cik=int(fund["cik"]), accession_nodash=accession.replace("-", ""))
        try:
            payload = client.get(url)
            header = filing_header(payload)
        except (urllib.error.URLError, ET.ParseError) as error:
            record["errors"].append({"accession": accession, "error": str(error)})
            continue
        xml_path.write_bytes(payload)
        row = {
            "accession": accession,
            "filing_date": entry["filing_date"],
            "period_end": header["period_end"],
            "series_name": header["series_name"],
            "series_id": header["series_id"],
            "registrant": header["registrant"],
            "url": url,
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }
        if (header["series_name"] or "").lower() != expected_name:
            row["series_mismatch"] = True
            record["series_mismatch"].append({"accession": accession, "series_name": header["series_name"]})
        existing[accession] = row
        record["downloaded"] += 1

    rows = sorted(existing.values(), key=lambda row: (row.get("period_end") or "", row["accession"]))
    index_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    periods = [row["period_end"] for row in rows if row.get("period_end")]
    record["on_disk"] = len(rows)
    record["period_range"] = [min(periods), max(periods)] if periods else None
    record["status"] = "ok" if not record["errors"] else "partial"
    return record


def append_log(raw_root: Path, record: dict[str, Any]) -> None:
    raw_root.mkdir(parents=True, exist_ok=True)
    with (raw_root / "pull_log.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    status_path = raw_root / "latest_status.json"
    latest = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    for fund_record in record["funds"]:
        latest[fund_record["fund_id"]] = {
            "as_of": record["as_of"],
            "status": fund_record["status"],
            "on_disk": fund_record.get("on_disk"),
            "period_range": fund_record.get("period_range"),
        }
    status_path.write_text(json.dumps(latest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--as-of", default=dt.date.today().isoformat())
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--fund", action="append", help="registry id; repeatable; default all active")
    parser.add_argument("--dry-run", action="store_true", help="list filings, download nothing")
    args = parser.parse_args(argv)

    registry = load_registry(args.registry)
    funds = sec_funds(registry)
    if args.fund:
        funds = [fund for fund in funds if fund["id"] in set(args.fund)]
        missing = set(args.fund) - {fund["id"] for fund in funds}
        if missing:
            parser.error(f"unknown or inactive fund ids: {sorted(missing)}")

    screen_path = write_screen(args.raw_root, args.as_of, funds, args.registry)
    print(f"screen {screen_path} (registry sha256 {registry_sha256(args.registry)[:12]})")

    client = EdgarClient()
    run: dict[str, Any] = {
        "as_of": args.as_of,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "screen": str(screen_path.relative_to(ROOT)) if screen_path.is_relative_to(ROOT) else str(screen_path),
        "screen_sha256": sha256_bytes(screen_path.read_bytes()),
        "dry_run": args.dry_run,
        "funds": [],
    }
    for fund in funds:
        record = pull_fund(client, args.raw_root, fund, dry_run=args.dry_run)
        run["funds"].append(record)
        flag = "ok" if record["status"] in ("ok", "dry_run") else record["status"].upper()
        print(
            f"[{flag}] {fund['id']:40s} listed {record['listed']:3d} "
            f"new {record['downloaded']:3d} existing {record['skipped_existing']:3d} "
            f"range {record.get('period_range')}"
            + (f" MISMATCH {len(record['series_mismatch'])}" if record["series_mismatch"] else "")
            + (f" errors {len(record['errors'])}" if record["errors"] else "")
        )
    run["requests"] = client.requests
    if not args.dry_run:
        append_log(args.raw_root, run)
    return 1 if any(record["errors"] for record in run["funds"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
