"""Offline tests for the TRACE cleaning rules, one synthetic case per rule."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from clean_trace_trades import (  # noqa: E402
    clean_enhanced,
    clean_standard,
    drop_standard_overlap,
    normalize,
    parse_volume,
)

ENH_COLUMNS = [
    "cusip_id", "trd_exctn_dt", "trd_exctn_tm", "trd_rpt_dt", "msg_seq_nb", "trc_st",
    "entrd_vol_qt", "rptd_pr", "asof_cd", "rpt_side_cd", "cntra_mp_id", "dissem_fl",
    "orig_msg_seq_nb", "yld_pt", "ats_indicator",
]


def enh(rows):
    frame = pd.DataFrame(rows, columns=ENH_COLUMNS)
    frame["_row"] = range(len(frame))
    return frame


def trade(cusip, exec_dt, tm, rpt_dt, seq, status="T", vol="1000000", price="100",
          asof=None, side="S", contra="C", orig=None):
    return [cusip, exec_dt, tm, rpt_dt, seq, status, vol, price, asof, side, contra,
            "Y", orig, None, None]


class EnhancedNewFormatTests(unittest.TestCase):
    def test_cancellation_removes_copy_and_original(self):
        frame = enh([
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1", status="X"),
            trade("A", "2020-01-02", "11:00:00", "2020-01-02", "2"),
        ])
        cleaned, steps = clean_enhanced(frame)
        self.assertEqual(cleaned["msg_seq_nb"].tolist(), ["2"])
        self.assertEqual(steps["new_format_cancellations"], 2)

    def test_correction_keeps_replacement_and_drops_original_and_flag(self):
        frame = enh([
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1", price="100.5"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1", status="C", price="100.5"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "9", status="R", price="100.6", orig="1"),
        ])
        cleaned, steps = clean_enhanced(frame)
        self.assertEqual(cleaned["trc_st"].tolist(), ["R"])
        self.assertEqual(cleaned["rptd_pr"].tolist(), ["100.6"])
        self.assertEqual(steps["new_format_corrections"], 2)

    def test_correction_chain_keeps_only_the_last_replacement(self):
        frame = enh([
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1", price="100.5"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1", status="C", price="100.5"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "5", status="R", price="100.6", orig="1"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "5", status="C", price="100.6"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "9", status="R", price="100.7", orig="5"),
        ])
        cleaned, _ = clean_enhanced(frame)
        self.assertEqual(cleaned["rptd_pr"].tolist(), ["100.7"])

    def test_reversal_by_pointer_across_days(self):
        frame = enh([
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-06", "7", status="Y", asof="R", orig="1"),
            trade("A", "2020-01-03", "10:00:00", "2020-01-03", "2"),
        ])
        cleaned, steps = clean_enhanced(frame)
        self.assertEqual(cleaned["msg_seq_nb"].tolist(), ["2"])
        self.assertEqual(steps["new_format_reversals"], 2)

    def test_reversal_falls_back_to_characteristics(self):
        frame = enh([
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-06", "7", status="Y", asof="R", orig="404"),
        ])
        cleaned, _ = clean_enhanced(frame)
        self.assertTrue(cleaned.empty)

    def test_one_notice_retires_one_trade_only(self):
        # Two identical trades, one reversal: one must survive.
        frame = enh([
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "2"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-06", "7", status="Y", asof="R", orig="404"),
        ])
        cleaned, _ = clean_enhanced(frame)
        self.assertEqual(len(cleaned), 1)

    def test_interdealer_pair_keeps_buy_side(self):
        frame = enh([
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "1", side="B", contra="D"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "2", side="S", contra="D"),
            trade("A", "2020-01-02", "10:05:00", "2020-01-02", "3", side="S", contra="D"),
            trade("A", "2020-01-02", "10:00:00", "2020-01-02", "4", side="S", contra="C"),
        ])
        cleaned, steps = clean_enhanced(frame)
        self.assertEqual(sorted(cleaned["msg_seq_nb"]), ["1", "3", "4"])
        self.assertEqual(steps["interdealer_sell_side_duplicates"], 1)


class EnhancedOldFormatTests(unittest.TestCase):
    def test_old_cancellation_and_correction(self):
        frame = enh([
            trade("A", "2011-03-01", "10:00:00", "2011-03-01", "1"),
            trade("A", "2011-03-01", "10:00:00", "2011-03-01", "2", status="C", orig="1"),
            trade("A", "2011-03-01", "11:00:00", "2011-03-01", "3", price="99"),
            trade("A", "2011-03-01", "11:00:00", "2011-03-01", "4", status="W", price="99.5", orig="3"),
        ])
        cleaned, steps = clean_enhanced(frame)
        self.assertEqual(cleaned["trc_st"].tolist(), ["W"])
        self.assertEqual(cleaned["rptd_pr"].tolist(), ["99.5"])
        self.assertEqual(steps["old_format_cancellations"], 2)
        self.assertEqual(steps["old_format_corrections"], 1)

    def test_asof_reversal_on_plain_trade(self):
        frame = enh([
            trade("A", "2011-03-01", "10:00:00", "2011-03-01", "1"),
            trade("A", "2011-03-01", "10:00:00", "2011-03-04", "2", asof="R"),
            trade("A", "2011-03-02", "10:00:00", "2011-03-02", "3"),
        ])
        cleaned, steps = clean_enhanced(frame)
        self.assertEqual(cleaned["msg_seq_nb"].tolist(), ["3"])
        self.assertEqual(steps["asof_reversals"], 2)


STD_COLUMNS = [
    "cusip_id", "trd_exctn_dt", "trd_exctn_tm", "trans_dt", "msg_seq_nb", "trc_st",
    "function", "ascii_rptd_vol_tx", "rptd_pr", "asof_cd", "side", "contra_party_type",
    "orig_msg_seq_nb", "orig_dis_dt", "yld_pt", "ats_indicator",
]


def std(rows):
    frame = pd.DataFrame(rows, columns=STD_COLUMNS)
    frame["_row"] = range(len(frame))
    return frame


def message(cusip, exec_dt, tm, seq, status="M", function=None, vol="500000", price="101",
            side="B", contra="C", orig=None, orig_dt=None):
    return [cusip, exec_dt, tm, exec_dt, seq, status, function, vol, price, None, side,
            contra, orig, orig_dt, None, None]


class StandardTests(unittest.TestCase):
    def test_cancel_correct_and_capped_volume(self):
        frame = std([
            message("A", "2026-01-05", "10:00:00", "10"),
            message("A", "2026-01-05", "10:00:00", None, status="N", function="C", orig="10", orig_dt="2026-01-05"),
            message("A", "2026-01-05", "11:00:00", "11", price="101.0"),
            message("A", "2026-01-05", "11:00:00", "12", status="O", function="N", price="101.2", orig="11", orig_dt="2026-01-05"),
            message("A", "2026-01-06", "09:00:00", "13", vol="1MM+"),
        ])
        cleaned, steps = clean_standard(frame)
        self.assertEqual(cleaned["msg_seq_nb"].tolist(), ["12", "13"])
        self.assertEqual(steps["cancellations_and_errors"], 2)
        self.assertEqual(steps["corrections"], 1)
        self.assertEqual(parse_volume("1MM+"), (1_000_000.0, True))
        self.assertEqual(parse_volume("306000.00"), (306000.0, False))


class NormalizeTests(unittest.TestCase):
    def test_columns_and_overlap_preference(self):
        enhanced = enh([trade("A", "2025-12-04", "10:00:00", "2025-12-04", "1")])
        standard = std([
            message("A", "2025-12-04", "10:00:00", "20"),
            message("A", "2025-12-05", "10:00:00", "21", vol="1MM+"),
        ])
        table = normalize(enhanced, standard)
        self.assertEqual(len(table), 3)
        table, dropped = drop_standard_overlap(table)
        self.assertEqual(dropped, 1)
        self.assertEqual(table["source_table"].tolist(), ["trace_enhanced", "trace_standard"])
        self.assertEqual(table.loc[1, "volume"], 1_000_000.0)
        self.assertTrue(bool(table.loc[1, "volume_capped"]))
        for column in ("cusip_id", "trade_date", "price", "volume", "dealer_side", "contra_party"):
            self.assertIn(column, table.columns)


if __name__ == "__main__":
    unittest.main()
