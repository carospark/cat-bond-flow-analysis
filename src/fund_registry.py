"""Load the fund registry and verify its SEC entries against EDGAR.

The registry at config/fund_registry.json is the identifier screen for the
fund-flow track: every N-PORT pull reads its CIK and series list from here,
and the pull manifest records this file's hash. Keeping the screen in a file
with a hash is lesson 1 in notes/pending-setup-lessons.md.

Offline use:

    from fund_registry import load_registry, sec_funds
    reg = load_registry()
    for fund in sec_funds(reg):
        ...

Online check (hits data.sec.gov; needs a User-Agent with a contact):

    ./.venv/bin/python src/fund_registry.py --verify

The check confirms each CIK resolves to the stated registrant, counts its
NPORT-P filings, and, for multi-series registrants, confirms the series ID
appears in EDGAR's series list. It changes nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "fund_registry.json"
USER_AGENT = "cat-bond-flow-analysis research (caropark4@gmail.com)"
REQUIRED_FUND_FIELDS = (
    "id",
    "fund_name",
    "registrant",
    "cik",
    "series_id",
    "series_name_in_filing",
    "structure",
    "role",
    "status",
    "evidence",
)
VALID_ROLES = {"fund", "mention_only"}
VALID_STATUSES = {"active", "inactive_verify", "reorganized", "excluded", "planned"}


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    with path.open(encoding="utf-8") as handle:
        registry = json.load(handle)
    validate_registry(registry)
    return registry


def registry_sha256(path: Path = REGISTRY_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_registry(registry: dict) -> None:
    if registry.get("schema_version") != 1:
        raise ValueError("fund registry schema_version must be 1")
    seen: set[str] = set()
    for entry in registry.get("sec_registered", []):
        role = entry.get("role")
        if role not in VALID_ROLES:
            raise ValueError(f"{entry.get('id')}: role must be one of {sorted(VALID_ROLES)}")
        if entry.get("status") not in VALID_STATUSES:
            raise ValueError(f"{entry.get('id')}: status must be one of {sorted(VALID_STATUSES)}")
        if entry["id"] in seen:
            raise ValueError(f"duplicate registry id {entry['id']}")
        seen.add(entry["id"])
        if role != "fund":
            continue
        missing = [field for field in REQUIRED_FUND_FIELDS if field not in entry]
        if missing:
            raise ValueError(f"{entry['id']}: missing fields {missing}")
        if not re.fullmatch(r"\d{10}", entry["cik"]):
            raise ValueError(f"{entry['id']}: cik must be ten digits, got {entry['cik']!r}")
        if entry["series_id"] is not None and not re.fullmatch(r"S\d{9}", entry["series_id"]):
            raise ValueError(f"{entry['id']}: series_id must look like S000000000")
    for entry in registry.get("non_sec", []):
        if entry["id"] in seen:
            raise ValueError(f"duplicate registry id {entry['id']}")
        seen.add(entry["id"])


def sec_funds(registry: dict, statuses: tuple[str, ...] = ("active", "reorganized")) -> list[dict]:
    """The SEC entries an N-PORT pull should screen on."""
    return [
        entry
        for entry in registry["sec_registered"]
        if entry["role"] == "fund" and entry["status"] in statuses
    ]


def _get(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def edgar_submissions(cik: str) -> dict:
    return json.loads(_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))


def edgar_series_ids(cik: str) -> dict[str, str]:
    page = _get(
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={int(cik):010d}&scd=series&count=100"
    ).decode("utf-8", "replace")
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    series = {}
    for index, line in enumerate(lines):
        if re.fullmatch(r"S\d{9}", line) and index + 1 < len(lines):
            series[line] = lines[index + 1]
    return series


def verify(registry: dict, pause: float = 0.4) -> list[dict]:
    """Check each SEC fund entry against EDGAR. Returns one row per entry."""
    rows = []
    series_cache: dict[str, dict[str, str]] = {}
    for entry in registry["sec_registered"]:
        if entry["role"] != "fund":
            continue
        row = {"id": entry["id"], "cik": entry["cik"], "ok": True, "problems": []}
        submissions = edgar_submissions(entry["cik"])
        row["edgar_name"] = submissions.get("name")
        forms = submissions["filings"]["recent"]["form"]
        dates = submissions["filings"]["recent"]["filingDate"]
        nport_dates = [d for f, d in zip(forms, dates) if f == "NPORT-P"]
        row["nport_filings"] = len(nport_dates)
        row["nport_filed_range"] = (min(nport_dates), max(nport_dates)) if nport_dates else None
        expected = entry["registrant"].lower().replace(",", "")
        if expected.split()[0] not in (row["edgar_name"] or "").lower():
            row["problems"].append(f"registrant mismatch: EDGAR says {row['edgar_name']!r}")
        if entry["series_id"]:
            if entry["cik"] not in series_cache:
                series_cache[entry["cik"]] = edgar_series_ids(entry["cik"])
                time.sleep(pause)
            name = series_cache[entry["cik"]].get(entry["series_id"])
            row["edgar_series_name"] = name
            if name is None:
                row["problems"].append("series_id not in EDGAR series list")
            elif name.lower() != entry["series_name_in_filing"].lower():
                row["problems"].append(f"series name differs: EDGAR says {name!r}")
        if entry["status"] in ("active", "reorganized") and not nport_dates:
            row["problems"].append("no NPORT-P filings on record")
        row["ok"] = not row["problems"]
        rows.append(row)
        time.sleep(pause)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--verify", action="store_true", help="check entries against EDGAR")
    args = parser.parse_args(argv)

    registry = load_registry(args.registry)
    funds = sec_funds(registry)
    print(f"registry {args.registry} sha256 {registry_sha256(args.registry)}")
    print(f"{len(funds)} SEC fund entries to screen; {len(registry.get('non_sec', []))} non-SEC funds planned")
    for fund in funds:
        print(f"  {fund['id']:40s} cik {fund['cik']} series {fund['series_id'] or '-':12s} {fund['status']}")
    if not args.verify:
        return 0
    print("verifying against EDGAR ...")
    failures = 0
    for row in verify(registry):
        flag = "ok " if row["ok"] else "BAD"
        print(
            f"  [{flag}] {row['id']:40s} {row['edgar_name']!r:48s} NPORT-P {row['nport_filings']:3d} "
            f"{row['nport_filed_range']}"
            + (f"  series={row.get('edgar_series_name')!r}" if "edgar_series_name" in row else "")
        )
        for problem in row["problems"]:
            print(f"        {problem}")
        failures += not row["ok"]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
