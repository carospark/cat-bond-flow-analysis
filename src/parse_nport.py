"""Parse archived Form N-PORT filings into monthly flow, return, and holdings tables.

Reads data/raw/sec_nport/filings/<fund_id>/*.xml (written by pull_nport.py)
and writes, under data/processed/nport/:

    fund_flows.csv      one row per fund and month: sales, reinvestment,
                        redemptions, net flow, and period-end net assets
    fund_returns.csv    one row per fund, class, and month: total return, pct
    fund_holdings.csv   one row per fund, period, and position, with CUSIP,
                        ISIN, value, share of net assets, and maturity
    summary.json        counts, date ranges, and bridge overlap

Part B of the form reports three months per filing. The form labels them
Month 1 through Month 3 "for each of the preceding three months"; Month 3
is the report month and Month 1 is two months earlier. Verified 2026-10-21
against the Brookmont ETF's issuer-published daily NAV: the filed Month 1
and Month 2 returns for July, August, October, and November 2025 equal the
monthly NAV returns to the basis point, and the Month 3 differences are the
quarter-end distributions a price return omits.

Filers are inconsistent about sign. Form N-PORT's flow fields are magnitudes,
but Stone Ridge, Pioneer and City National Rochdale reported redemptions as
negative numbers for documented stretches (through the 2024-01-31 report
period; Pioneer ILS only from 2022-01-31). The ranges are in
config/nport_sign_conventions.json with the evidence; the sign is flipped
only where that table says so, every raw value is kept in a `*_raw` column,
and a value whose sign contradicts the table (or a negative where no
convention is documented) is not normalised: the field is null and the row
is flagged, which also nulls net flow. net_flow is sales minus redemptions
when both are reported; a missing component makes it null and
`net_flow_basis` says which one. Reinvested distributions are kept in their
own column and left out of net flow because they are not new money.

When a period has more than one filing (an NPORT-P/A amendment beside the
original) the latest filed stands for the period and the others are
recorded as superseded, in `superseded_filings` in the summary and in the
`superseded_by` column of fund_flows.csv; flows, returns and holdings are all
taken from the standing filing only.

Only the quarter-end filing of each fund is public, so the monthly series
is complete but arrives in quarterly batches with a 60-day lag.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = ROOT / "data" / "raw" / "sec_nport"
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "nport"
DEFAULT_BRIDGE = ROOT / "data" / "bridge.csv"
DEFAULT_CONVENTIONS = ROOT / "config" / "nport_sign_conventions.json"
DEFAULT_REGISTRY = ROOT / "config" / "fund_registry.json"
FLOW_FIELDS = ("sales", "reinvestment", "redemption")
MONTH_ALIGNMENT = (
    "mon3 is the report month; mon1 is two months earlier. Verified 2026-10-21 against "
    "Brookmont ETF daily NAV for Jul, Aug, Oct, Nov 2025."
)


def strip_namespaces(root: ET.Element) -> ET.Element:
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    return root


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if value in ("", "N/A"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _text(element: ET.Element | None, tag: str) -> str | None:
    if element is None:
        return None
    found = element.find(tag)
    if found is None or found.text is None:
        return None
    text = found.text.strip()
    return text if text and text != "N/A" else None


def load_conventions(path: Path | None = DEFAULT_CONVENTIONS) -> list[dict[str, str]]:
    """Documented sign conventions: fund, field, sign, inclusive period range."""
    if path is None or not Path(path).exists():
        return []
    return json.loads(Path(path).read_text(encoding="utf-8")).get("conventions", [])


def convention_for(conventions: list[dict[str, str]], fund_id: str | None, field: str, period_end: str | None) -> str | None:
    """'negative' when the filer reported `field` with a negative sign in the
    filing whose report period ends `period_end`, else None."""
    if not fund_id or not period_end:
        return None
    for row in conventions:
        if row["fund_id"] == fund_id and row["field"] == field and row["from_period_end"] <= period_end <= row["to_period_end"]:
            return row["sign"]
    return None


def normalise_flow(raw: dict[str, float | None], fund_id: str | None, period_end: str | None, conventions: list[dict[str, str]]) -> dict[str, Any]:
    """Raw flow attributes -> normalised magnitudes, flags, net flow and its basis.

    A documented negative convention flips the sign of non-positive values.
    A positive value inside such a range, or a negative value outside any
    convention, is left null and flagged rather than guessed at.
    """
    out: dict[str, Any] = {}
    flags: list[str] = []
    for field in FLOW_FIELDS:
        value = raw.get(field)
        out[f"{field}_raw"] = value
        convention = convention_for(conventions, fund_id, field, period_end)
        if value is None:
            out[field] = None
            flags.append(f"{field}_missing")
        elif convention == "negative":
            if value <= 0:
                out[field] = -value
                if value < 0:
                    flags.append(f"{field}_sign_flipped")
            else:
                out[field] = None
                flags.append(f"{field}_sign_conflict")
        elif value < 0:
            out[field] = None
            flags.append(f"sign_unexpected_{field}")
        else:
            out[field] = value
    missing = [f for f in ("sales", "redemption") if out[f] is None]
    if missing:
        out["net_flow"] = None
        reasons = []
        for f in missing:
            reasons.append(next(flag for flag in flags if flag.startswith(f) or flag.endswith(f)))
        out["net_flow_basis"] = ";".join(reasons)
    else:
        out["net_flow"] = out["sales"] - out["redemption"]
        out["net_flow_basis"] = "sales_minus_redemption"
    out["flow_flags"] = ";".join(flags)
    out["sign_flipped"] = any(flag.endswith("_sign_flipped") for flag in flags)
    return out


def month_ends(period_end: str) -> list[str]:
    """Month-end dates for Month 1, 2, 3 given the report period end."""
    end = pd.Timestamp(period_end)
    return [(end - pd.DateOffset(months=offset) + pd.offsets.MonthEnd(0)).date().isoformat() for offset in (2, 1, 0)]


def parse_filing(payload: bytes, fund_id: str | None = None, conventions: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Header, flows, returns, and holdings from one primary_doc.xml.

    `fund_id` and `conventions` select the documented sign convention for the
    flow fields; without them every value is taken as reported and negatives
    are flagged rather than flipped."""
    conventions = conventions if conventions is not None else []
    root = strip_namespaces(ET.fromstring(payload))
    gen = root.find(".//genInfo")
    fund_info = root.find(".//fundInfo")
    header = {
        "submission_type": _text(root.find(".//headerData"), "submissionType"),
        "registrant": _text(gen, "regName"),
        "series_name": _text(gen, "seriesName"),
        "series_id": _text(gen, "seriesId"),
        "period_end": _text(gen, "repPdDate"),
        "fiscal_year_end": _text(gen, "repPdEnd"),
        "is_final_filing": _text(gen, "isFinalFiling"),
        "total_assets": _num(_text(fund_info, "totAssets")),
        "total_liabilities": _num(_text(fund_info, "totLiabs")),
        "net_assets": _num(_text(fund_info, "netAssets")),
    }
    months = month_ends(header["period_end"]) if header["period_end"] else [None, None, None]

    flows = []
    for index, tag in enumerate(("mon1Flow", "mon2Flow", "mon3Flow")):
        element = root.find(f".//{tag}")
        if element is None:
            continue
        raw = {field: _num(element.get(field)) for field in FLOW_FIELDS}
        flows.append(
            {
                "month_index": index + 1,
                "month_end": months[index],
                **normalise_flow(raw, fund_id, header["period_end"], conventions),
            }
        )

    returns = []
    for element in root.iter("monthlyTotReturn"):
        class_id = element.get("classId") or "fund"
        for index, attr in enumerate(("rtn1", "rtn2", "rtn3")):
            value = _num(element.get(attr))
            if value is None:
                continue
            returns.append(
                {"class_id": class_id, "month_index": index + 1, "month_end": months[index], "return_pct": value}
            )

    holdings = []
    for inv in root.iter("invstOrSec"):
        identifiers = inv.find("identifiers")
        isin = None
        other_ids = []
        if identifiers is not None:
            isin_el = identifiers.find("isin")
            isin = isin_el.get("value") if isin_el is not None else None
            for other in identifiers.findall("other"):
                other_ids.append(f"{other.get('otherDesc')}:{other.get('value')}")
        debt = inv.find("debtSec")
        holdings.append(
            {
                "name": _text(inv, "name"),
                "lei": _text(inv, "lei"),
                "title": _text(inv, "title"),
                "cusip": _text(inv, "cusip"),
                "isin": isin,
                "other_ids": ";".join(other_ids) if other_ids else None,
                "balance": _num(_text(inv, "balance")),
                "units": _text(inv, "units"),
                "currency": _text(inv, "curCd"),
                "value_usd": _num(_text(inv, "valUSD")),
                "pct_net_assets": _num(_text(inv, "pctVal")),
                "payoff_profile": _text(inv, "payoffProfile"),
                "asset_category": _text(inv, "assetCat"),
                "issuer_category": _text(inv, "issuerCat"),
                "country": _text(inv, "invCountry"),
                "is_restricted": _text(inv, "isRestrictedSec"),
                "fair_value_level": _text(inv, "fairValLevel"),
                "maturity_date": _text(debt, "maturityDt"),
                "coupon_kind": _text(debt, "couponKind"),
                "annualized_rate": _num(_text(debt, "annualizedRt")),
                "is_default": _text(debt, "isDefault"),
            }
        )
    return {"header": header, "flows": flows, "returns": returns, "holdings": holdings}


def select_standing(parsed_filings: list[dict[str, Any]]) -> dict[str, str | None]:
    """For each (fund, period_end) the latest filed accession stands; every
    other accession for that period maps to the one that superseded it.
    Ties on filing date go to the amendment, then the higher accession."""
    standing: dict[str, str | None] = {}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in parsed_filings:
        groups.setdefault((row["fund_id"], row["period_end"] or ""), []).append(row)
    for rows in groups.values():
        rows = sorted(rows, key=lambda r: (r.get("filing_date") or "", r.get("form") == "NPORT-P/A", r["accession"]))
        winner = rows[-1]["accession"]
        for row in rows:
            standing[row["accession"]] = None if row["accession"] == winner else winner
    return standing


def parse_archive(raw_root: Path, conventions: list[dict[str, str]] | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    conventions = load_conventions() if conventions is None else conventions
    flow_rows, return_rows, holding_rows, filings = [], [], [], []
    filings_dir = raw_root / "filings"
    parsed_all: list[dict[str, Any]] = []
    for fund_dir in sorted(path for path in filings_dir.iterdir() if path.is_dir()) if filings_dir.exists() else []:
        index_path = fund_dir / "filings.json"
        index = {row["accession"]: row for row in json.loads(index_path.read_text(encoding="utf-8"))} if index_path.exists() else {}
        for xml_path in sorted(fund_dir.glob("*.xml")):
            accession = xml_path.stem
            meta = index.get(accession, {})
            if meta.get("series_mismatch"):
                filings.append({"fund_id": fund_dir.name, "accession": accession, "skipped": "series_mismatch"})
                continue
            parsed = parse_filing(xml_path.read_bytes(), fund_dir.name, conventions)
            header = parsed["header"]
            parsed_all.append({
                "fund_id": fund_dir.name, "accession": accession, "filing_date": meta.get("filing_date"),
                "form": meta.get("form") or header.get("submission_type") or "NPORT-P",
                "period_end": header["period_end"], "parsed": parsed,
            })
    standing = select_standing(parsed_all)
    for item in parsed_all:
        parsed, header = item["parsed"], item["parsed"]["header"]
        superseded_by = standing.get(item["accession"])
        base = {
            "fund_id": item["fund_id"],
            "accession": item["accession"],
            "form": item["form"],
            "filing_date": item["filing_date"],
            "period_end": header["period_end"],
            "series_name": header["series_name"],
        }
        record = {**base, "net_assets": header["net_assets"], "holdings": len(parsed["holdings"])}
        if superseded_by:
            record["superseded_by"] = superseded_by
            filings.append(record)
            continue
        filings.append(record)
        for flow in parsed["flows"]:
            flow_rows.append(
                {
                    **base,
                    **flow,
                    "net_assets_at_period_end": header["net_assets"] if flow["month_index"] == 3 else None,
                    "total_assets_at_period_end": header["total_assets"] if flow["month_index"] == 3 else None,
                }
            )
        for ret in parsed["returns"]:
            return_rows.append({**base, **ret})
        for holding in parsed["holdings"]:
            holding_rows.append({**base, **holding})
    return pd.DataFrame(flow_rows), pd.DataFrame(return_rows), pd.DataFrame(holding_rows), filings


def lineages(registry_path: Path | None = DEFAULT_REGISTRY) -> dict[str, str]:
    """fund_id -> lineage id. A fund with a successor joins the successor's
    lineage (Pioneer CAT Bond Fund -> Victory Pioneer CAT Bond Fund)."""
    if registry_path is None or not Path(registry_path).exists():
        return {}
    funds = json.loads(Path(registry_path).read_text(encoding="utf-8")).get("sec_registered", [])
    successor = {f["id"]: f.get("successor_id") for f in funds}
    out = {}
    for fund_id in successor:
        head = fund_id
        seen = set()
        while successor.get(head) and head not in seen:
            seen.add(head)
            head = successor[head]
        out[fund_id] = head
    return out


def summarize(
    flows: pd.DataFrame, returns: pd.DataFrame, holdings: pd.DataFrame, filings: list[dict[str, Any]], bridge_path: Path | None
) -> dict[str, Any]:
    parsed = [row for row in filings if "skipped" not in row and "superseded_by" not in row]
    superseded = [row for row in filings if "superseded_by" in row]
    summary: dict[str, Any] = {
        "month_alignment_assumption": MONTH_ALIGNMENT,
        "sign_conventions": str(DEFAULT_CONVENTIONS.relative_to(ROOT)),
        "filings_parsed": len(parsed),
        "filings_skipped": [row for row in filings if "skipped" in row],
        "superseded_filings": [
            {k: row[k] for k in ("fund_id", "accession", "form", "filing_date", "period_end", "superseded_by")} for row in superseded
        ],
        "funds": sorted({row["fund_id"] for row in parsed}),
        "flow_rows": int(len(flows)),
        "return_rows": int(len(returns)),
        "holding_rows": int(len(holdings)),
    }
    if not flows.empty:
        summary["flow_month_range"] = [flows["month_end"].min(), flows["month_end"].max()]
        summary["flow_rows_sign_flipped_by_fund"] = {
            fund: int(value) for fund, value in flows.groupby("fund_id")["sign_flipped"].sum().items() if value
        }
        summary["flow_rows_without_net_flow"] = {
            fund: int(value) for fund, value in flows.groupby("fund_id")["net_flow"].apply(lambda s: s.isna().sum()).items() if value
        }
        summary["flow_flags"] = {
            flag: int(count) for flag, count in flows["flow_flags"].str.split(";").explode().replace("", pd.NA).dropna().value_counts().items()
        }
        summary["net_flow_by_fund"] = {
            fund: round(float(value), 2) for fund, value in flows.groupby("fund_id")["net_flow"].sum(min_count=1).items()
        }
        lineage = lineages()
        if lineage:
            by_lineage = flows.assign(lineage=flows["fund_id"].map(lambda f: lineage.get(f, f)))
            summary["net_flow_by_lineage"] = {
                name: round(float(value), 2) for name, value in by_lineage.groupby("lineage")["net_flow"].sum(min_count=1).items()
            }
            summary["months_without_net_flow_by_lineage"] = {
                name: int(value) for name, value in by_lineage.groupby("lineage")["net_flow"].apply(lambda s: s.isna().sum()).items() if value
            }
        latest = flows[flows["month_index"] == 3].sort_values("period_end").groupby("fund_id").tail(1)
        summary["latest_net_assets"] = {
            row.fund_id: {"period_end": row.period_end, "net_assets": row.net_assets_at_period_end}
            for row in latest.itertuples()
        }
    if not holdings.empty:
        with_cusip = holdings["cusip"].notna()
        summary["holdings_with_cusip"] = int(with_cusip.sum())
        summary["distinct_cusips"] = int(holdings.loc[with_cusip, "cusip"].nunique())
        if bridge_path is not None and bridge_path.exists():
            bridge = pd.read_csv(bridge_path, dtype=str)
            cusip_col = next((col for col in bridge.columns if col.lower() in ("cusip", "cusip_id")), None)
            if cusip_col:
                bridged = set(bridge[cusip_col].dropna().str.strip())
                held = set(holdings.loc[with_cusip, "cusip"].str.strip())
                summary["distinct_cusips_in_strict_bridge"] = len(held & bridged)
                summary["bridge_cusips_held_by_any_fund_pct"] = round(100.0 * len(held & bridged) / max(len(bridged), 1), 1)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--bridge", type=Path, default=DEFAULT_BRIDGE)
    parser.add_argument("--conventions", type=Path, default=DEFAULT_CONVENTIONS)
    args = parser.parse_args(argv)

    flows, returns, holdings, filings = parse_archive(args.raw_root, load_conventions(args.conventions))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    flows.to_csv(args.out_dir / "fund_flows.csv", index=False)
    returns.to_csv(args.out_dir / "fund_returns.csv", index=False)
    holdings.to_csv(args.out_dir / "fund_holdings.csv", index=False)
    summary = summarize(flows, returns, holdings, filings, args.bridge)
    summary["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("filings_skipped",)}, indent=2))
    if summary["filings_skipped"]:
        print(f"skipped {len(summary['filings_skipped'])} filings flagged as series mismatches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
