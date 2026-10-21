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

Filers are inconsistent about sign: Stone Ridge and Pioneer reported
redemptions as negative numbers until early 2024 and positive after, and
City National Rochdale has done both for sales. All three flow fields are
stored as magnitudes, with a `sign_flipped` flag on rows where a negative
was normalized, and net flow is sales minus redemptions. Reinvested
distributions are kept in their own column and left out of net flow because
they are not new money.

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


def month_ends(period_end: str) -> list[str]:
    """Month-end dates for Month 1, 2, 3 given the report period end."""
    end = pd.Timestamp(period_end)
    return [(end - pd.DateOffset(months=offset) + pd.offsets.MonthEnd(0)).date().isoformat() for offset in (2, 1, 0)]


def parse_filing(payload: bytes) -> dict[str, Any]:
    """Header, flows, returns, and holdings from one primary_doc.xml."""
    root = strip_namespaces(ET.fromstring(payload))
    gen = root.find(".//genInfo")
    fund_info = root.find(".//fundInfo")
    header = {
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
        raw = {field: _num(element.get(field)) for field in ("sales", "reinvestment", "redemption")}
        sign_flipped = any(value is not None and value < 0 for value in raw.values())
        sales = abs(raw["sales"]) if raw["sales"] is not None else None
        reinvestment = abs(raw["reinvestment"]) if raw["reinvestment"] is not None else None
        redemption = abs(raw["redemption"]) if raw["redemption"] is not None else None
        flows.append(
            {
                "month_index": index + 1,
                "month_end": months[index],
                "sales": sales,
                "reinvestment": reinvestment,
                "redemption": redemption,
                "net_flow": (sales or 0.0) - (redemption or 0.0) if sales is not None or redemption is not None else None,
                "sign_flipped": sign_flipped,
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


def parse_archive(raw_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    flow_rows, return_rows, holding_rows, filings = [], [], [], []
    filings_dir = raw_root / "filings"
    for fund_dir in sorted(path for path in filings_dir.iterdir() if path.is_dir()) if filings_dir.exists() else []:
        index_path = fund_dir / "filings.json"
        index = {row["accession"]: row for row in json.loads(index_path.read_text(encoding="utf-8"))} if index_path.exists() else {}
        for xml_path in sorted(fund_dir.glob("*.xml")):
            accession = xml_path.stem
            meta = index.get(accession, {})
            if meta.get("series_mismatch"):
                filings.append({"fund_id": fund_dir.name, "accession": accession, "skipped": "series_mismatch"})
                continue
            parsed = parse_filing(xml_path.read_bytes())
            header = parsed["header"]
            base = {
                "fund_id": fund_dir.name,
                "accession": accession,
                "filing_date": meta.get("filing_date"),
                "period_end": header["period_end"],
                "series_name": header["series_name"],
            }
            filings.append({**base, "net_assets": header["net_assets"], "holdings": len(parsed["holdings"])})
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


def summarize(
    flows: pd.DataFrame, returns: pd.DataFrame, holdings: pd.DataFrame, filings: list[dict[str, Any]], bridge_path: Path | None
) -> dict[str, Any]:
    parsed = [row for row in filings if "skipped" not in row]
    summary: dict[str, Any] = {
        "month_alignment_assumption": MONTH_ALIGNMENT,
        "filings_parsed": len(parsed),
        "filings_skipped": [row for row in filings if "skipped" in row],
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
        summary["net_flow_by_fund"] = {
            fund: round(float(value), 2) for fund, value in flows.groupby("fund_id")["net_flow"].sum().items()
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
    args = parser.parse_args(argv)

    flows, returns, holdings, filings = parse_archive(args.raw_root)
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
