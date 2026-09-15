"""Clean raw TRACE 144A transaction exports into one trade table.

Inputs are the licensed WRDS exports under ``data/raw/tier1/wrds/``: four
enhanced-table batches (``trace_enh_*.csv``) and four standard-table tail
batches (``trace_std_*.csv``). They are raw disseminated messages, so the same
economic trade can appear several times: once as reported, again as a
cancellation or correction notice, and again as a corrected replacement.
Inter-dealer trades are reported by both dealers. This script removes those
duplicates and writes a single table keyed on CUSIP and execution date.

The rules follow Dick-Nielsen (2009, 2014) but were checked against how the
status codes actually link in these files (see ``docs/SOURCES.md``):

Enhanced table, reports dated on or after 2012-02-06 (new format):
  * ``X`` is a cancellation. It is a copy of the cancelled trade with the same
    ``msg_seq_nb`` on the same report date. Drop the X and that original.
  * A correction is a triple. ``C`` is a copy of the original trade (same
    ``msg_seq_nb``) flagging that it was corrected; ``R`` carries the corrected
    values and points at the original through ``orig_msg_seq_nb``. Drop the C
    and the original; keep the R. Chains (an R later corrected) resolve
    because the later C shares the R's ``msg_seq_nb``.
  * ``Y`` is a reversal of a trade reported on an earlier day. Drop the Y and
    the original it names in ``orig_msg_seq_nb``; fall back to matching on
    trade characteristics when the pointer does not resolve.
Enhanced table, reports before 2012-02-06 (old format):
  * ``C`` is a cancellation: drop it and the original it points at.
  * ``W`` is a correction carrying the corrected values: drop the original it
    points at, keep the W.
  * ``asof_cd == 'R'`` on an ordinary trade marks a reversal: drop it and one
    matching original.
Both eras:
  * Inter-dealer trades (``cntra_mp_id == 'D'``) appear once per dealer. Pair
    the buy and sell reports on characteristics and keep the buy side.

Standard table (the 2025-12-05 onward tail):
  * ``function == 'C'`` is a cancellation notice (``trc_st == 'N'``) that
    repeats the cancelled trade and names it in ``orig_msg_seq_nb``. Drop both.
  * ``function == 'N'`` is a correction (``trc_st == 'O'``) carrying the new
    values with the old ones in ``orig_*``. Drop the original, keep the row.
  * ``function == 'E'`` is an erroneous report: drop it and its original.
  * Volumes above the dissemination cap arrive as ``1MM+``; they are stored as
    1,000,000 with ``volume_capped`` set.

No network access. Inputs and outputs are gitignored.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WRDS_DIR = ROOT / "data" / "raw" / "tier1" / "wrds"
OUTPUT_PATH = ROOT / "data" / "trace_trades_clean.csv"
SUMMARY_PATH = ROOT / "data" / "trace_trades_clean_summary.json"
NEW_FORMAT_START = pd.Timestamp("2012-02-06")

CHAR_KEY = ["cusip_id", "trd_exctn_dt", "trd_exctn_tm", "rptd_pr", "entrd_vol_qt"]
CHAR_KEY_SIDED = CHAR_KEY + ["rpt_side_cd", "cntra_mp_id"]


def _read(paths: list[str]) -> pd.DataFrame:
    frames = [pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
              for path in paths]
    frame = pd.concat(frames, ignore_index=True)
    frame["_row"] = range(len(frame))
    return frame


def _drop_matching(frame: pd.DataFrame, keep: pd.Series, keys: list[str],
                   references: pd.DataFrame, ref_keys: list[str],
                   one_per_reference: bool = True,
                   order_column: str = "trd_rpt_dt") -> pd.Series:
    """Unset ``keep`` for rows whose ``keys`` equal a reference's ``ref_keys``.

    With ``one_per_reference`` each reference retires at most one live row,
    the earliest by report date, so two identical trades are not both removed
    by a single notice.
    """
    if references.empty:
        return keep
    live = frame[keep]
    ref = references[ref_keys].dropna()
    if ref.empty:
        return keep
    ref = ref.rename(columns=dict(zip(ref_keys, keys)))
    ref["_ref"] = range(len(ref))
    merged = live.reset_index().merge(ref, on=keys, how="inner")
    if merged.empty:
        return keep
    if one_per_reference:
        merged = merged.sort_values(["_ref", order_column, "_row"])
        merged = merged.drop_duplicates("_ref")
    keep = keep.copy()
    keep.loc[merged["index"].unique()] = False
    return keep


def clean_enhanced(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    frame = frame.copy()
    frame["_rpt"] = pd.to_datetime(frame["trd_rpt_dt"], errors="coerce")
    new = frame["_rpt"] >= NEW_FORMAT_START
    status = frame["trc_st"].fillna("")
    keep = pd.Series(True, index=frame.index)
    steps: dict[str, int] = {"input_rows": int(len(frame))}
    seq_key = ["cusip_id", "trd_rpt_dt", "msg_seq_nb"]
    ptr_key = ["cusip_id", "trd_rpt_dt", "orig_msg_seq_nb"]
    any_seq = ["cusip_id", "msg_seq_nb"]
    any_ptr = ["cusip_id", "orig_msg_seq_nb"]

    def count(label: str, before: pd.Series) -> None:
        steps[label] = int(before.sum() - keep.sum())

    # --- New format -------------------------------------------------------
    before = keep.copy()
    cancels = frame[new & (status == "X")]
    keep[cancels.index] = False
    keep = _drop_matching(frame, keep, seq_key, cancels, seq_key)
    keep = _drop_matching(frame, keep, seq_key, cancels, ptr_key)
    count("new_format_cancellations", before)

    before = keep.copy()
    flags = frame[new & (status == "C")]
    keep[flags.index] = False
    keep = _drop_matching(frame, keep, seq_key, flags, seq_key)
    replacements = frame[new & (status == "R") & keep]
    keep = _drop_matching(frame, keep, seq_key, replacements, ptr_key)
    unresolved = replacements[~replacements.set_index(ptr_key).index.isin(
        frame[~keep].set_index(seq_key).index)]
    keep = _drop_matching(frame, keep, any_seq, unresolved, any_ptr)
    count("new_format_corrections", before)

    before = keep.copy()
    reversals = frame[new & (status == "Y")]
    keep[reversals.index] = False
    keep = _drop_matching(frame, keep, any_seq, reversals, any_ptr)
    matched = reversals.set_index(any_ptr).index.isin(frame[~keep].set_index(any_seq).index)
    keep = _drop_matching(frame, keep, CHAR_KEY_SIDED, reversals[~matched], CHAR_KEY_SIDED)
    count("new_format_reversals", before)

    # --- Old format -------------------------------------------------------
    before = keep.copy()
    old_cancels = frame[~new & (status == "C")]
    keep[old_cancels.index] = False
    keep = _drop_matching(frame, keep, seq_key, old_cancels, ptr_key)
    pointed = old_cancels["orig_msg_seq_nb"].notna()
    keep = _drop_matching(frame, keep, CHAR_KEY_SIDED, old_cancels[~pointed], CHAR_KEY_SIDED)
    count("old_format_cancellations", before)

    before = keep.copy()
    old_corrections = frame[~new & (status == "W")]
    keep = _drop_matching(frame, keep, seq_key, old_corrections, ptr_key)
    count("old_format_corrections", before)

    before = keep.copy()
    asof_reversals = frame[keep & (status == "T") & (frame["asof_cd"].fillna("") == "R")]
    keep[asof_reversals.index] = False
    keep = _drop_matching(frame, keep, CHAR_KEY_SIDED, asof_reversals, CHAR_KEY_SIDED)
    count("asof_reversals", before)

    # --- Inter-dealer double reporting -------------------------------------
    before = keep.copy()
    dealer = frame[keep & (frame["cntra_mp_id"].fillna("") == "D")]
    buys = dealer[dealer["rpt_side_cd"] == "B"]
    sells = dealer[dealer["rpt_side_cd"] == "S"]
    if not buys.empty and not sells.empty:
        pair = sells.reset_index().merge(buys[CHAR_KEY].drop_duplicates(), on=CHAR_KEY)
        keep.loc[pair["index"].unique()] = False
    count("interdealer_sell_side_duplicates", before)

    before = keep.copy()
    live = frame[keep]
    dupes = live.duplicated(["cusip_id", "trd_rpt_dt", "msg_seq_nb", "trc_st"], keep="first")
    keep.loc[live[dupes].index] = False
    count("exact_duplicates", before)

    steps["output_rows"] = int(keep.sum())
    cleaned = frame[keep].drop(columns=["_rpt"])
    return cleaned, steps


def clean_standard(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    frame = frame.copy()
    keep = pd.Series(True, index=frame.index)
    steps: dict[str, int] = {"input_rows": int(len(frame))}
    function = frame["function"].fillna("")
    seq_key = ["cusip_id", "trans_dt", "msg_seq_nb"]
    ptr_key = ["cusip_id", "orig_dis_dt", "orig_msg_seq_nb"]

    def count(label: str, before: pd.Series) -> None:
        steps[label] = int(before.sum() - keep.sum())

    before = keep.copy()
    cancels = frame[function.isin(["C", "E"])]
    keep[cancels.index] = False
    keep = _drop_matching(frame, keep, seq_key, cancels, ptr_key, order_column="trans_dt")
    count("cancellations_and_errors", before)

    before = keep.copy()
    corrections = frame[function == "N"]
    keep = _drop_matching(frame, keep, seq_key, corrections, ptr_key, order_column="trans_dt")
    count("corrections", before)

    before = keep.copy()
    dealer = frame[keep & (frame["contra_party_type"].fillna("") == "D")]
    key = ["cusip_id", "trd_exctn_dt", "trd_exctn_tm", "rptd_pr", "ascii_rptd_vol_tx"]
    buys = dealer[dealer["side"] == "B"]
    sells = dealer[dealer["side"] == "S"]
    if not buys.empty and not sells.empty:
        pair = sells.reset_index().merge(buys[key].drop_duplicates(), on=key)
        keep.loc[pair["index"].unique()] = False
    count("interdealer_sell_side_duplicates", before)

    before = keep.copy()
    live = frame[keep]
    dupes = live.duplicated(key + ["side", "msg_seq_nb"], keep="first")
    keep.loc[live[dupes].index] = False
    count("exact_duplicates", before)

    steps["output_rows"] = int(keep.sum())
    return frame[keep], steps


def parse_volume(value: object) -> tuple[float | None, bool]:
    text = str(value or "").strip().upper().replace(",", "")
    if not text or text == "NAN":
        return None, False
    if text.endswith("MM+"):
        return float(text[:-3]) * 1_000_000, True
    if text.endswith("+"):
        return float(text[:-1]), True
    try:
        return float(text), False
    except ValueError:
        return None, False


def normalize(enhanced: pd.DataFrame, standard: pd.DataFrame) -> pd.DataFrame:
    enh = pd.DataFrame({
        "source_table": "trace_enhanced",
        "cusip_id": enhanced["cusip_id"],
        "trade_date": enhanced["trd_exctn_dt"],
        "trade_time": enhanced["trd_exctn_tm"],
        "report_date": enhanced["trd_rpt_dt"],
        "price": pd.to_numeric(enhanced["rptd_pr"], errors="coerce"),
        "volume": pd.to_numeric(enhanced["entrd_vol_qt"], errors="coerce"),
        "volume_capped": False,
        "dealer_side": enhanced["rpt_side_cd"],
        "contra_party": enhanced["cntra_mp_id"],
        "as_of": enhanced["asof_cd"].fillna("") == "A",
        "disseminated": enhanced["dissem_fl"].fillna("") == "Y",
        "ats": enhanced["ats_indicator"].fillna("") == "Y",
        "yield": pd.to_numeric(enhanced["yld_pt"], errors="coerce"),
        "msg_seq_nb": enhanced["msg_seq_nb"],
        "record_status": enhanced["trc_st"],
    })
    volumes = standard["ascii_rptd_vol_tx"].map(parse_volume)
    std = pd.DataFrame({
        "source_table": "trace_standard",
        "cusip_id": standard["cusip_id"],
        "trade_date": standard["trd_exctn_dt"],
        "trade_time": standard["trd_exctn_tm"],
        "report_date": standard["trans_dt"],
        "price": pd.to_numeric(standard["rptd_pr"], errors="coerce"),
        "volume": volumes.map(lambda item: item[0]),
        "volume_capped": volumes.map(lambda item: item[1]),
        "dealer_side": standard["side"],
        "contra_party": standard["contra_party_type"],
        "as_of": standard["asof_cd"].fillna("") == "A",
        "disseminated": True,
        "ats": standard["ats_indicator"].fillna("") == "Y",
        "yield": pd.to_numeric(standard["yld_pt"], errors="coerce"),
        "msg_seq_nb": standard["msg_seq_nb"],
        "record_status": standard["trc_st"],
    })
    combined = pd.concat([enh, std], ignore_index=True)
    combined = combined.sort_values(["cusip_id", "trade_date", "trade_time", "msg_seq_nb"])
    return combined.reset_index(drop=True)


def drop_standard_overlap(table: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Prefer the enhanced table where both cover the same execution dates."""
    enhanced_last = table.loc[table["source_table"] == "trace_enhanced", "trade_date"].max()
    if pd.isna(enhanced_last):
        return table, 0
    overlap = (table["source_table"] == "trace_standard") & (table["trade_date"] <= enhanced_last)
    return table[~overlap].reset_index(drop=True), int(overlap.sum())


def build(wrds_dir: Path = WRDS_DIR) -> tuple[pd.DataFrame, dict]:
    enhanced_paths = sorted(glob.glob(str(wrds_dir / "trace_enh_*.csv")))
    standard_paths = sorted(glob.glob(str(wrds_dir / "trace_std_*.csv")))
    if not enhanced_paths:
        raise SystemExit(f"no enhanced TRACE files under {wrds_dir}")
    enhanced, enhanced_steps = clean_enhanced(_read(enhanced_paths))
    if standard_paths:
        standard, standard_steps = clean_standard(_read(standard_paths))
    else:
        standard, standard_steps = pd.DataFrame(), {"input_rows": 0, "output_rows": 0}
    table = normalize(enhanced, standard) if len(standard) else normalize(
        enhanced, pd.DataFrame(columns=_read(enhanced_paths[:1]).columns))
    table, overlap = drop_standard_overlap(table)
    summary = {
        "inputs": {"enhanced": [Path(p).name for p in enhanced_paths],
                   "standard": [Path(p).name for p in standard_paths]},
        "enhanced": enhanced_steps,
        "standard": standard_steps,
        "standard_rows_overlapping_enhanced_dropped": overlap,
        "output": {
            "rows": int(len(table)),
            "cusips": int(table["cusip_id"].nunique()),
            "first_trade_date": str(table["trade_date"].min()),
            "last_trade_date": str(table["trade_date"].max()),
            "rows_by_source": table["source_table"].value_counts().to_dict(),
            "rows_by_contra_party": table["contra_party"].fillna("NA").value_counts().to_dict(),
            "capped_volume_rows": int(table["volume_capped"].sum()),
        },
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wrds-dir", type=Path, default=WRDS_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    args = parser.parse_args()
    table, summary = build(args.wrds_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.output, index=False)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.output} ({len(table)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
