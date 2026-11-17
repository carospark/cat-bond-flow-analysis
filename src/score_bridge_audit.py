"""Score the hand-checked bridge audit sample.

Reads ``data/bridge_audit_sample.csv`` after the ``audit_verdict`` column has
been filled (correct / wrong / undecidable; blank means not yet read) and
reports precision by stratum and overall, two ways:

- unweighted: correct over decided pairs in the sample;
- weighted: the per-confidence precisions re-weighted by each confidence
  level's share of pairs in the full bridge, which is the estimate for the
  bridge as a whole (the sample over-draws low and medium on purpose).

Wilson 95% intervals are given on both. Undecidable pairs are reported but
excluded from the denominator. Nothing is written unless ``--out`` is given,
in which case the summary goes to a JSON file.

    ./.venv/bin/python src/score_bridge_audit.py
    ./.venv/bin/python src/score_bridge_audit.py --out data/bridge_audit_summary.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = ROOT / "data" / "bridge_audit_sample.csv"
BRIDGE_PATH = ROOT / "data" / "bridge.csv"
VERDICTS = ("correct", "wrong", "undecidable")


def wilson(correct: int, n: int, z: float = 1.959964) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = correct / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _tally(frame: pd.DataFrame) -> dict:
    verdicts = frame["audit_verdict"].str.strip().str.lower()
    unknown = sorted(set(verdicts[verdicts.ne("")]) - set(VERDICTS))
    if unknown:
        raise ValueError("unrecognised audit_verdict values: %s" % unknown)
    correct = int(verdicts.eq("correct").sum())
    wrong = int(verdicts.eq("wrong").sum())
    undecidable = int(verdicts.eq("undecidable").sum())
    unread = int(verdicts.eq("").sum())
    decided = correct + wrong
    lo, hi = wilson(correct, decided)
    return {
        "pairs": int(len(frame)), "correct": correct, "wrong": wrong, "undecidable": undecidable,
        "unread": unread, "decided": decided,
        "precision": (correct / decided) if decided else None, "wilson95": [lo, hi],
    }


def score(sample: pd.DataFrame, bridge: pd.DataFrame | None = None) -> dict:
    out = {"overall": _tally(sample), "by_stratum": {}, "by_confidence": {}}
    for stratum, frame in sample.groupby("stratum", sort=True):
        out["by_stratum"][stratum] = _tally(frame)
    confidence = sample["stratum"].str.split(":").str[0]
    for level, frame in sample.groupby(confidence, sort=True):
        out["by_confidence"][level] = _tally(frame)
    if bridge is not None and "match_confidence" in bridge.columns and len(bridge):
        shares = bridge["match_confidence"].value_counts(normalize=True)
        weighted, covered, var = 0.0, 0.0, 0.0
        for level, share in shares.items():
            cell = out["by_confidence"].get(level)
            if not cell or not cell["decided"]:
                continue
            weighted += share * cell["precision"]
            covered += share
            p, n = cell["precision"], cell["decided"]
            var += (share ** 2) * p * (1 - p) / n
        if covered:
            est = weighted / covered
            se = math.sqrt(var) / covered
            out["weighted"] = {
                "bridge_pairs": int(len(bridge)), "bridge_shares": {k: float(v) for k, v in shares.items()},
                "share_of_bridge_covered_by_decided_strata": covered,
                "precision": est, "normal95": [max(0.0, est - 1.959964 * se), min(1.0, est + 1.959964 * se)],
            }
    return out


def format_report(result: dict) -> str:
    def line(label: str, cell: dict) -> str:
        prec = "n/a" if cell["precision"] is None else "%.1f%%" % (100 * cell["precision"])
        lo, hi = cell["wilson95"]
        ci = "" if lo is None else " [%.1f, %.1f]" % (100 * lo, 100 * hi)
        return "  %-22s %3d pairs: %2d correct, %2d wrong, %2d undecidable, %2d unread -> %s%s" % (
            label, cell["pairs"], cell["correct"], cell["wrong"], cell["undecidable"], cell["unread"], prec, ci)

    lines = ["bridge audit sample", line("overall", result["overall"]), "by confidence:"]
    lines += [line(k, v) for k, v in result["by_confidence"].items()]
    lines.append("by stratum:")
    lines += [line(k, v) for k, v in result["by_stratum"].items()]
    if "weighted" in result:
        w = result["weighted"]
        lines.append("weighted to the bridge's confidence mix (%d pairs, %.0f%% of pairs in decided strata): %.1f%% [%.1f, %.1f]" % (
            w["bridge_pairs"], 100 * w["share_of_bridge_covered_by_decided_strata"], 100 * w["precision"],
            100 * w["normal95"][0], 100 * w["normal95"][1]))
    if result["overall"]["unread"]:
        lines.append("note: %d pairs have no verdict yet" % result["overall"]["unread"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sample", type=Path, default=SAMPLE_PATH)
    parser.add_argument("--bridge", type=Path, default=BRIDGE_PATH)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    sample = pd.read_csv(args.sample, dtype=str, keep_default_na=False)
    bridge = pd.read_csv(args.bridge, dtype=str, keep_default_na=False) if args.bridge.exists() else None
    result = score(sample, bridge)
    print(format_report(result))
    if args.out:
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("wrote %s" % args.out)
    return 0 if not result["overall"]["unread"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
