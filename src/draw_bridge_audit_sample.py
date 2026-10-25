"""Draw a held-out audit sample of strict-bridge pairs for hand checking.

The bridge's own agreement with the N-PORT titles is partly in-sample, since
the same titles feed the bridge. An independent precision estimate needs a
human to read a sample of pairs against the Artemis page and the TRACE
master row. This draws that sample, stratified by match confidence and by
issue-year bucket with a fixed seed, writes every evidence column the pair
carries, and leaves the verdict columns empty. Nothing here scores anything.

    ./.venv/bin/python src/draw_bridge_audit_sample.py            # 40 pairs
    ./.venv/bin/python src/draw_bridge_audit_sample.py --n 60 --seed 7

Output: data/bridge_audit_sample.csv (gitignored: it carries Artemis and
TRACE content). Columns `audit_verdict` (fill with correct / wrong /
undecidable) and `audit_notes` are for the reader.

Allocation: every low-confidence pair is drawn (there are a handful and they
are the riskiest); the remainder is split 55/45 between high and medium,
over-weighting medium relative to its share because that is where the
ticker-inferred names, the title-capped pairs and the propagated siblings
live. Within a confidence stratum the draw is spread over four issue-year
buckets in proportion to the stratum's pairs, at least one per non-empty
bucket.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "data" / "bridge.csv"
OUT_PATH = ROOT / "data" / "bridge_audit_sample.csv"
YEAR_BUCKETS = [(0, 2012, "to_2012"), (2013, 2017, "2013_2017"), (2018, 2021, "2018_2021"), (2022, 9999, "2022_on")]
EVIDENCE_COLUMNS = [
    "deal_url", "artemis_issuer_name", "artemis_sponsor", "artemis_size_text", "artemis_date_text",
    "artemis_series_id", "cusip_id", "trace_issuer_nm", "trace_issuer_variants",
    "trace_security_description", "trace_debt_type_codes", "trace_ever_un_cat", "trace_issue_date",
    "trace_maturity_date", "trace_coupon_min", "trace_coupon_max", "match_confidence", "match_method",
    "title_evidence", "name_similarity", "name_evidence", "series_evidence", "date_evidence",
    "maturity_evidence", "coupon_evidence",
]


def year_bucket(date_text: str) -> str:
    try:
        year = int(str(date_text).strip()[-4:])
    except ValueError:
        return "unknown"
    for lo, hi, label in YEAR_BUCKETS:
        if lo <= year <= hi:
            return label
    return "unknown"


def allocate(counts: pd.Series, n: int) -> dict:
    """Spread n draws over strata in proportion to counts, at least one each
    where a stratum has pairs, never more than the stratum holds."""
    counts = counts[counts > 0]
    if counts.empty or n <= 0:
        return {}
    raw = counts / counts.sum() * n
    alloc = {k: max(1, int(np.floor(v))) for k, v in raw.items()}
    alloc = {k: min(v, int(counts[k])) for k, v in alloc.items()}
    remainder = n - sum(alloc.values())
    order = (raw - pd.Series(alloc)).sort_values(ascending=False).index
    for key in list(order) * 3:
        if remainder <= 0:
            break
        if alloc[key] < counts[key]:
            alloc[key] += 1
            remainder -= 1
    for key in list(order)[::-1] * 3:
        if remainder >= 0:
            break
        if alloc[key] > 1:
            alloc[key] -= 1
            remainder += 1
    return alloc


def draw_sample(bridge: pd.DataFrame, n: int = 40, seed: int = 20261025) -> pd.DataFrame:
    work = bridge.copy()
    work["year_bucket"] = work["artemis_date_text"].map(year_bucket)
    rng = np.random.default_rng(seed)
    low = work[work["match_confidence"].eq("low")]
    n_rest = max(n - len(low), 0)
    n_high = int(round(n_rest * 0.55))
    n_medium = n_rest - n_high
    pieces = [low.assign(stratum="low:" + low["year_bucket"])]
    for confidence, quota in (("high", n_high), ("medium", n_medium)):
        pool = work[work["match_confidence"].eq(confidence)]
        for bucket, k in allocate(pool["year_bucket"].value_counts(), quota).items():
            cell = pool[pool["year_bucket"].eq(bucket)]
            take = cell.iloc[rng.choice(len(cell), size=min(k, len(cell)), replace=False)]
            pieces.append(take.assign(stratum=f"{confidence}:{bucket}"))
    sample = pd.concat(pieces, ignore_index=True)
    columns = ["stratum"] + [c for c in EVIDENCE_COLUMNS if c in sample.columns]
    sample = sample[columns].sort_values(["stratum", "artemis_date_text", "cusip_id"]).reset_index(drop=True)
    sample.insert(0, "sample_id", range(1, len(sample) + 1))
    sample["audit_verdict"] = ""
    sample["audit_notes"] = ""
    return sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bridge", type=Path, default=BRIDGE_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20261025)
    args = parser.parse_args(argv)
    bridge = pd.read_csv(args.bridge, dtype=str, keep_default_na=False)
    sample = draw_sample(bridge, args.n, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(args.out, index=False)
    print("wrote %s: %d pairs, seed %d" % (args.out, len(sample), args.seed))
    print(sample.groupby("stratum").size().to_string())
    print("title evidence in the sample: %s" % sample["title_evidence"].value_counts().to_dict()
          if "title_evidence" in sample.columns else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
