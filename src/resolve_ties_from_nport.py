"""Use fund-reported security titles from N-PORT to resolve program-level ties and check the strict bridge.

Funds describe each position in Form N-PORT Part C with a free-text title,
and many of them name the series: "Kilimanjaro III Re 2019-1 Class A-1",
"Merna Re II 2022-2 Class A", "Phoenician Re Ltd. 2020-2 Class A". That is
exactly the evidence the program bridge lacks when two same-month series
twins differ only in tenor and the parsed directory gives them the same or
no maturity.

This script never modifies bridge.csv or bridge_program.csv. It writes:

    data/bridge_program_nport_resolutions.csv   one row per tied or
        program-only CUSIP whose fund-reported titles name exactly one of
        its candidate deals, with the titles and funds as evidence
    data/bridge_nport_series_check.csv          one row per strict-bridge
        CUSIP whose titles name a series, with whether it matches the
        bridged deal's series
    data/bridge_nport_summary.json

A title has to state the series as a year and number (2019-1); class
letters alone (A-1, B-2) are not used, because the letter-to-series
convention differs by program. All titles for a CUSIP must agree before it
counts as resolved.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SERIES_IN_TITLE = re.compile(r"\b(20\d\d)\s*-\s*(\d{1,2})\b")
# Directory slugs carry the series as "...-series-2019-1/", "...-titania-re-2026-1/",
# or, for an entry covering two series at once, "...-series-2020-1-2020-2/".
SERIES_IN_SLUG = re.compile(r"(20\d\d)-(\d{1,2})(?!\d)")


def series_from_title(title: str | None) -> str | None:
    """'Kilimanjaro III Re 2019-1 Class A-1' -> '2019-1'; None when absent."""
    if not isinstance(title, str):
        return None
    match = SERIES_IN_TITLE.search(title)
    return f"{match.group(1)}-{int(match.group(2))}" if match else None


def series_from_deal_url(url: str | None) -> list[str]:
    """Every series a directory slug names, e.g. ['2020-1', '2020-2']; [] when none."""
    if not isinstance(url, str):
        return []
    slug = url.strip().rstrip("/").rsplit("/", 1)[-1]
    return [f"{year}-{int(number)}" for year, number in SERIES_IN_SLUG.findall(slug)]


def normalize_series(series: str | None) -> str:
    """'2024-01' and '2024-1' compare equal; a trailing letter is kept."""
    if not isinstance(series, str) or "-" not in series:
        return ""
    year, number = series.split("-", 1)
    digits = re.match(r"(\d+)([A-Za-z]?)", number)
    if not digits:
        return series
    return f"{year}-{int(digits.group(1))}{digits.group(2).upper()}"


def title_series_map(holdings_path: Path) -> dict[str, str]:
    """CUSIP -> the one series every fund-reported title for it names.

    Used by build_bridge and extend_bridge as evidence. CUSIPs whose titles
    disagree, or name no series, are absent, so a caller can treat presence
    as unanimous.
    """
    if not holdings_path.exists():
        return {}
    holdings = pd.read_csv(holdings_path, low_memory=False, usecols=["fund_id", "accession", "cusip", "title"])
    titles = titles_by_cusip(holdings)
    return {
        row.cusip: normalize_series(row.series_named[0])
        for row in titles.itertuples(index=False)
        if len(row.series_named) == 1
    }


def titles_by_cusip(holdings: pd.DataFrame) -> pd.DataFrame:
    """Distinct fund-reported titles per CUSIP, with the series each names."""
    rows = holdings[holdings["cusip"].notna()].copy()
    rows["cusip"] = rows["cusip"].astype(str).str.strip().str.upper()
    rows["title_series"] = rows["title"].map(series_from_title)
    rows = rows[rows["title_series"].notna()]
    grouped = rows.groupby("cusip").agg(
        series_named=("title_series", lambda s: sorted(set(s))),
        titles=("title", lambda s: sorted(set(s))),
        funds=("fund_id", lambda s: sorted(set(s))),
        filings=("accession", "nunique"),
    )
    return grouped.reset_index()


def resolve_program_rows(program: pd.DataFrame, titles: pd.DataFrame) -> pd.DataFrame:
    """Tied and program-only rows whose titles name exactly one candidate deal."""
    candidates = program[program["level"].isin(["program_tied", "program_only"])].copy()
    out = []
    by_cusip = titles.set_index("cusip")
    for row in candidates.itertuples(index=False):
        if row.cusip_id not in by_cusip.index:
            continue
        info = by_cusip.loc[row.cusip_id]
        named = info["series_named"]
        if len(named) != 1:
            out.append({"cusip_id": row.cusip_id, "level": row.level, "outcome": "titles_disagree",
                        "series_named": "|".join(named), "titles": " || ".join(info["titles"]),
                        "funds": ";".join(info["funds"]), "deal_url": None})
            continue
        series = named[0]
        pool = str(row.tied_deal_urls or "").split("|") if row.level == "program_tied" else str(row.program_deals or "").split("|")
        pool = [url.strip() for url in pool if url.strip()]
        matches = [url for url in pool if series in series_from_deal_url(url)]
        if len(matches) == 1:
            outcome = "resolved"
        elif not matches:
            outcome = "series_not_in_candidates"
        else:
            outcome = "ambiguous"
        out.append({
            "cusip_id": row.cusip_id, "level": row.level, "outcome": outcome, "series_named": series,
            "deal_url": matches[0] if len(matches) == 1 else None, "candidates": "|".join(pool),
            "titles": " || ".join(info["titles"]), "funds": ";".join(info["funds"]), "filings": int(info["filings"]),
            "evidence": f"nport_title:{series}",
        })
    return pd.DataFrame(out)


def check_strict_bridge(bridge: pd.DataFrame, titles: pd.DataFrame) -> pd.DataFrame:
    merged = bridge[["cusip_id", "deal_url", "match_confidence", "match_method"]].merge(
        titles.rename(columns={"cusip": "cusip_id"}), on="cusip_id", how="inner"
    )
    merged["deal_series"] = merged["deal_url"].map(series_from_deal_url)
    merged["agrees"] = [
        (bool(set(named) & set(deal)) if deal else None)
        for named, deal in zip(merged["series_named"], merged["deal_series"])
    ]
    merged["deal_series"] = merged["deal_series"].map("|".join)
    merged["series_named"] = merged["series_named"].map("|".join)
    merged["titles"] = merged["titles"].map(" || ".join)
    merged["funds"] = merged["funds"].map(";".join)
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--holdings", type=Path, default=DATA / "processed" / "nport" / "fund_holdings.csv")
    parser.add_argument("--bridge", type=Path, default=DATA / "bridge.csv")
    parser.add_argument("--program-bridge", type=Path, default=DATA / "bridge_program.csv")
    parser.add_argument("--out-dir", type=Path, default=DATA)
    args = parser.parse_args(argv)

    holdings = pd.read_csv(args.holdings, low_memory=False)
    titles = titles_by_cusip(holdings)
    program = pd.read_csv(args.program_bridge, dtype=str)
    bridge = pd.read_csv(args.bridge, dtype=str)

    resolutions = resolve_program_rows(program, titles)
    check = check_strict_bridge(bridge, titles)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    resolutions.to_csv(args.out_dir / "bridge_program_nport_resolutions.csv", index=False)
    check.to_csv(args.out_dir / "bridge_nport_series_check.csv", index=False)

    decided = check[check["agrees"].notna()]
    summary: dict[str, Any] = {
        "cusips_with_series_in_title": int(len(titles)),
        "program_rows_considered": int(program["level"].isin(["program_tied", "program_only"]).sum()),
        "program_rows_with_titles": int(len(resolutions)),
        "outcomes": {k: int(v) for k, v in resolutions["outcome"].value_counts().items()} if not resolutions.empty else {},
        "resolved_by_level": {k: int(v) for k, v in resolutions[resolutions["outcome"] == "resolved"]["level"].value_counts().items()} if not resolutions.empty else {},
        "strict_bridge_cusips_checked": int(len(decided)),
        "strict_bridge_agreement_rate": round(float(decided["agrees"].mean()), 4) if len(decided) else None,
        "strict_bridge_disagreements": decided[~decided["agrees"].astype(bool)][["cusip_id", "deal_url", "series_named", "match_confidence", "match_method"]].to_dict("records"),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (args.out_dir / "bridge_nport_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "strict_bridge_disagreements"}, indent=2))
    print(f"strict bridge disagreements: {len(summary['strict_bridge_disagreements'])}")
    for row in summary["strict_bridge_disagreements"][:15]:
        print("  ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
