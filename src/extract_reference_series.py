"""Extract the three priority non-Artemis validation series from archived PDFs.

The output is local-only under data/processed/reference_series.  Exact tables
remain distinct from values digitized from a chart, and every output records
the source page and extraction method.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "tier1" / "2026-08-30"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "reference_series"

AON_PDF = RAW / "aon_securities_ils_annual_2025" / "aon_securities_ils_annual_2025.pdf"
GC_PDF = RAW / "guy_carpenter_rol_2000_2026" / "guy_carpenter_rol_2000_2026.pdf"
LANE_PDF = RAW / "lane_financial_ils_2024" / "lane_financial_natural_catastrophe_ils_2001_2023.pdf"

AON_ANNUAL_ISSUANCE = [
    (2010, 4850), (2011, 4270), (2012, 5855), (2013, 7141),
    (2014, 8027), (2015, 6221), (2016, 5590), (2017, 10161),
    (2018, 9494), (2019, 5383), (2020, 11023), (2021, 12482),
    (2022, 9359), (2023, 15384), (2024, 17037), (2025, 16898),
]

# Exact transcription of Lane Table 1, visually checked against PDF page 5.
# The first five years predate WSST; the publisher repeats SSST in those cells.
LANE_ROWS = [
    (2001,964,11,"7/17/2001","12/17/2003",88,5.35,1.06,.66,62.5,8.1,1.06,.66,62.5,8.1,2.4,2.4),
    (2002,956,20,"7/17/2002","4/27/2005",48,4.57,1.09,.76,70.0,6.0,1.09,.76,70.0,6.0,2.8,2.8),
    (2003,1720,29,"9/8/2003","4/25/2007",59,4.41,1.11,.87,78.3,5.1,1.11,.87,78.3,5.1,3.6,3.6),
    (2004,1143,16,"9/3/2004","11/12/2007",71,5.34,1.79,1.32,73.5,4.1,1.79,1.32,73.5,4.1,3.2,3.2),
    (2005,1588,15,"8/25/2005","3/2/2008",106,6.35,1.94,1.54,79.2,4.1,1.94,1.54,79.2,4.1,2.5,2.5),
    (2006,4581,61,"8/1/2006","2/6/2009",75,8.93,2.47,1.84,74.56,4.9,2.77,2.08,75.14,4.3,2.5,2.5),
    (2007,7031,60,"7/20/2007","5/29/2010",117,5.85,1.90,1.39,72.95,4.2,2.03,1.48,73.18,3.9,2.9,2.9),
    (2008,2636,26,"5/23/2008","3/15/2011",101,6.78,2.07,1.46,70.63,4.6,2.26,1.59,70.24,4.3,2.8,2.8),
    (2009,3398,31,"8/15/2009","6/1/2012",110,10.61,2.46,1.99,80.93,5.3,2.71,2.17,80.36,4.9,2.8,2.8),
    (2010,4799,40,"8/6/2010","8/22/2013",120,7.22,2.20,1.66,75.63,4.3,2.40,1.81,75.76,4.0,3.0,3.0),
    (2011,4270,33,"8/11/2011","11/26/2014",129,8.79,2.75,2.16,78.43,4.1,2.96,2.32,78.35,3.8,3.3,3.3),
    (2012,5455,42,"6/17/2012","9/3/2015",130,9.57,2.42,1.94,80.53,4.9,2.62,2.11,80.49,4.5,3.2,3.2),
    (2013,7210,40,"7/19/2013","10/20/2016",180,5.58,2.13,1.64,76.74,3.4,2.40,1.85,77.01,3.0,3.3,3.3),
    (2014,8026,35,"6/29/2014","1/24/2018",229,4.76,2.19,1.56,71.53,3.0,2.41,1.74,72.08,2.7,3.6,3.6),
    (2015,6218,30,"6/20/2015","11/26/2018",207,5.36,2.99,2.08,69.77,2.6,3.26,2.27,69.81,2.4,3.4,3.4),
    (2016,5590,37,"7/15/2016","3/12/2020",151,5.71,3.48,2.63,75.43,2.2,3.86,2.91,75.46,2.0,3.7,3.7),
    (2017,10111,66,"6/1/2017","12/10/2020",153,5.39,3.48,2.61,74.93,2.1,3.77,2.82,74.93,1.9,3.5,3.5),
    (2018,9594,47,"5/11/2018","12/12/2021",204,4.93,2.90,2.17,74.75,2.3,3.08,2.30,74.84,2.1,3.6,3.6),
    (2019,5284,33,"7/28/2019","4/14/2023",160,8.26,4.16,3.20,77.00,2.6,4.51,3.47,76.97,2.4,3.7,3.7),
    (2020,11023,75,"6/23/2020","8/5/2023",147,7.02,3.10,2.36,76.10,3.0,3.38,2.56,75.92,2.7,3.1,3.1),
    (2021,12397,73,"6/27/2021","12/17/2024",170,5.89,3.12,2.31,74.07,2.5,3.35,2.48,73.99,2.4,3.5,2.5),
    (2022,8713,63,"5/24/2022","7/22/2025",138,7.91,2.82,2.22,78.72,3.6,3.07,2.42,78.57,3.3,3.2,1.6),
    (2023,14915,94,"7/12/2023","8/11/2026",159,8.59,2.49,1.91,76.92,4.5,2.68,2.05,76.71,4.2,3.1,.5),
]

LANE_FIELDS = [
    "year", "annual_limit_issued_usd_mn", "tranches", "weighted_issue_date",
    "weighted_maturity_date", "average_principal_usd_mn", "weighted_premium_pct",
    "ssst_pfl_pct", "ssst_el_pct", "ssst_cel_lgd_pct", "ssst_multiple",
    "wsst_pfl_pct", "wsst_el_pct", "wsst_cel_lgd_pct", "wsst_multiple",
    "weighted_term_years", "term_to_2023_12_31_years",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def page_text(pdf: Path, page: int) -> str:
    return subprocess.check_output(
        ["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"],
        text=True,
    )


def extract_aon(output: Path) -> dict:
    annual = [{
        "year": year,
        "period_scope": "H1 only" if year == 2025 else "calendar year",
        "issuance_usd_mn": value,
        "source_page": 5,
        "extraction_method": "publisher_label_transcription_visual_check",
    } for year, value in AON_ANNUAL_ISSUANCE]
    write_csv(output / "aon_property_cat_bond_annual_issuance.csv", list(annual[0]), annual)

    initial_period = {
        22: "Q3 2024", 23: "Q4 2024", 24: "Q4 2024", 25: "Q1 2025",
        26: "Q1 2025", 27: "Q2 2025", 28: "Q2 2025", 29: "Q2 2025",
    }
    rows = []
    for page in range(22, 30):
        period = initial_period[page]
        table_started = page > 22
        for line in page_text(AON_PDF, page).splitlines():
            heading = re.search(r"(Q[1-4] 20\d{2}) Catastrophe Bond Issuance", line)
            if heading:
                period = heading.group(1)
                table_started = True
                continue
            if not table_started:
                continue
            cells = re.split(r"\s{2,}", line.strip())
            if (len(cells) < 9 or len(cells) <= 4
                    or not re.fullmatch(r"\d+(?:\.\d+)?", cells[4])
                    or not re.fullmatch(r"\d+(?:\.\d+)?%", cells[-1])):
                continue
            percentages = [float(cell[:-1]) for cell in cells[-2:]
                           if re.fullmatch(r"\d+(?:\.\d+)?%", cell)]
            expected_loss = percentages[0]
            spread = percentages[1] if len(percentages) == 2 else None
            rows.append({
                "period": period, "source_page": page,
                "beneficiary_printed": cells[0], "issuer_printed": cells[1],
                "series_printed": cells[2], "class_printed": cells[3],
                "issue_size_usd_mn": float(cells[4]),
                "expected_loss_pct": expected_loss,
                "initial_spread_pct": spread,
                "derived_spread_to_el_multiple": round(spread / expected_loss, 4)
                if spread is not None and expected_loss else None,
                "row_text": line.strip(),
                "extraction_method": "pdftotext_layout_row_parse_visual_spot_check",
            })
    fields = list(rows[0])
    write_csv(output / "aon_2024_2025_tranche_pricing.csv", fields, rows)
    return {
        "annual_rows": len(annual), "tranche_rows": len(rows),
        "table_issue_size_usd_mn": round(sum(row["issue_size_usd_mn"] for row in rows), 2),
        "missing_initial_spread_rows": sum(row["initial_spread_pct"] is None for row in rows),
    }


def extract_gc(output: Path) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        svg = Path(temp_dir) / "gc.svg"
        subprocess.run(["pdftocairo", "-f", "1", "-l", "1", "-svg", str(GC_PDF), str(svg)],
                       check=True, capture_output=True, text=True)
        text = svg.read_text(encoding="utf-8")
    segments = re.findall(
        r'stroke-width:2\.25[^>]+d="M ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+)', text
    )
    if len(segments) != 26:
        raise ValueError(f"Expected 26 line segments in GC chart, found {len(segments)}")
    points = [(float(segments[0][0]), float(segments[0][1]))]
    points.extend((float(segment[2]), float(segment[3])) for segment in segments)
    baseline_y = 142.121094
    points_per_index_unit = 26.25 / 20
    rows = []
    for year, (x_coord, y_coord) in zip(range(2000, 2027), points):
        rows.append({
            "year": year,
            "rol_index": round((y_coord - baseline_y) / points_per_index_unit, 1),
            "source_page": 1,
            "svg_x": round(x_coord, 6), "svg_y": round(y_coord, 6),
            "digitization_uncertainty_index_points": 0.4,
            "extraction_method": "vector_path_digitization_axis_calibrated",
        })
    write_csv(output / "guy_carpenter_global_property_cat_rol_index.csv", list(rows[0]), rows)
    if rows[0]["rol_index"] != 100.0 or rows[-1]["rol_index"] != 156.0:
        raise ValueError("GC axis calibration validation failed")
    return {"rows": len(rows), "coverage": "2000-2026", "base_2000": rows[0]["rol_index"]}


def extract_lane(output: Path) -> dict:
    rows = []
    for values in LANE_ROWS:
        row = dict(zip(LANE_FIELDS, values))
        row.update({
            "source_page": 5,
            "extraction_method": "manual_table_transcription_double_visual_check",
        })
        rows.append(row)
    write_csv(output / "lane_annual_nat_cat_ils_pricing.csv", list(rows[0]), rows)
    if sum(row["annual_limit_issued_usd_mn"] for row in rows) != 137622:
        raise ValueError("Lane issuance total does not match publisher total")
    if sum(row["tranches"] for row in rows) != 977:
        raise ValueError("Lane tranche total does not match publisher total")
    return {"rows": len(rows), "coverage": "2001-2023", "issuer_total_usd_mn": 137622,
            "tranche_total": 977}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    for path in (AON_PDF, GC_PDF, LANE_PDF):
        if not path.exists():
            raise FileNotFoundError(path)
    results = {
        "aon": extract_aon(args.output),
        "guy_carpenter": extract_gc(args.output),
        "lane": extract_lane(args.output),
        "sources": {str(path.relative_to(ROOT)): sha256(path) for path in (AON_PDF, GC_PDF, LANE_PDF)},
        "caveats": {
            "aon": "The table sums its listed tranches; the report headline is broader. Four rows omit initial spread. No aggregate guidance series is published.",
            "guy_carpenter": "Values are axis-calibrated from the PDF vector path, not publisher-supplied tabular observations.",
            "lane": "Publisher table values; SSST and WSST are distinct model cases from 2006 onward.",
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "extraction_manifest.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
