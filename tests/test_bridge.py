"""Golden and guard tests for the local Artemis -> TRACE bridge.

Run the complete local-input suite:
    ./.venv/bin/python tests/test_bridge.py

Run only fast unit/guard tests (used for the explicit mutation check):
    ./.venv/bin/python tests/test_bridge.py --unit-only
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_bridge import (build, collapse_trace, extract_series, match_frames,  # noqa: E402
                          normalise_issuer)


failures = []


def check(ok, label, detail=""):
    if ok:
        print("PASS", label)
    else:
        print("FAIL", label, detail)
        failures.append(label)


def security(cusip, issuer, issue, maturity="2024-01-15", series_codes=""):
    return {
        "cusip_id": cusip,
        "issuer_nm": issuer,
        "issuer_variants": issuer,
        "scrty_ds": "Unsecured Insurance Linked Security",
        "trace_debt_type_codes": series_codes,
        "trace_ever_un_cat": True,
        "trace_history_rows": 1,
        "trace_issue_date": issue,
        "trace_last_end_date": issue,
        "trace_maturity_date": maturity,
        "trace_coupon_min": 5.0,
        "trace_coupon_max": 5.0,
        "trace_coupon_observation_count": 1,
        "trace_usable_coupon_min": 5.0,
        "trace_usable_coupon_max": 5.0,
        "trace_usable_coupon_observation_count": 1,
    }


def deal(name, date, suffix):
    return {
        "issuer_name": name,
        "deal_url": "https://example.invalid/" + suffix,
        "sponsor": "Test sponsor",
        "size_text": "$100m",
        "date_text": date,
    }


# Unit expectations for the transformations needed by real TRACE truncations.
NORMALISER = {
    ("Citrus Re Ltd. (Series 2015-1)", "artemis"): "CITRUS RE",
    ("KILIMANJARO II RE LIMITED", "trace"): "KILIMANJARO II RE",
    ("ATLAS CAP DAC", "trace"): "ATLAS CAPITAL",
    ("Golden State Re II Ltd. (Series 2018-1)", "artemis"): "GOLDEN STATE RE II",
    ("GOLDEN ST RE II LTD", "trace"): "GOLDEN STATE RE II",
    ("INTEGRITY RE 2025-1", "trace"): "INTEGRITY RE",
    ("RESIDENTIAL REINS 2021 LTD", "trace"): "RESIDENTIAL REINSURANCE 2021",
    ("SANDERS RE II LTD ACTING IN RESPECT SEGREGATED ACCOUNT 2025-1", "trace"):
        "SANDERS RE II",
    ("Aquila Re I Ltd. (Series 2023-1)", "artemis"): "AQUILA RE I",
    ("AQUILA RE I LTD 2023-1", "trace"): "AQUILA RE I",
    ("Artex Axcell Re – PI0055 Grantham notes", "artemis"): "ARTEX AXCELL RE",
}
for (raw, source), expected in NORMALISER.items():
    actual = normalise_issuer(raw, source)
    check(actual == expected, "UNIT normaliser %s" % raw, "%s != %s" % (actual, expected))

check(extract_series("Citrus Re Ltd. (Series 2015-1)") == "2015-1",
      "UNIT Artemis series")
check(extract_series("AQUILA RE I LTD SER 20231") == "2023-1",
      "UNIT compact TRACE series")
check(extract_series("RESIDENTIAL REINS 2021 LTD") == "",
      "GUARD legal-entity year is not a series")

# A longitudinal TRACE coupon history must become one security, not one bridge
# row per reset.
raw_trace = pd.DataFrame([
    {"cusip_id": "000000AA1", "issuer_nm": "ALPHA RE LTD", "scrty_ds": "ILS",
     "debt_type_cd": "", "cpn_rt": "3.0", "mtrty_dt": "2024-01-15",
     "stdt": "2020-01-10", "enddt": "2020-02-10"},
    {"cusip_id": "000000AA1", "issuer_nm": "ALPHA RE LTD", "scrty_ds": "ILS",
     "debt_type_cd": "UN-CAT", "cpn_rt": "4.0", "mtrty_dt": "2024-01-15",
     "stdt": "2020-02-11", "enddt": "2021-01-01"},
])
collapsed = collapse_trace(raw_trace)
check(len(collapsed) == 1, "GUARD coupon resets collapse to one CUSIP")
check(bool(collapsed.iloc[0].trace_ever_un_cat), "UNIT ever-UN-CAT aggregation")
check(collapsed.iloc[0].trace_coupon_min == 3.0 and collapsed.iloc[0].trace_coupon_max == 4.0,
      "UNIT coupon range retained")

# Mutation-sensitive date guard: the exact same issuer two years away must not
# match. Temporarily replacing _date_guard's final return with `return True`
# makes this assertion fail (verified manually in the delivery run).
synthetic_index = pd.DataFrame([deal("Alpha Re Ltd. (Series 2020-1)", "Jan 2020", "alpha")])
synthetic_trace = pd.DataFrame([security("000000AA1", "ALPHA RE LTD", "2022-01-10",
                                               maturity="2026-01-15")])
synthetic_bridge, _, _ = match_frames(synthetic_index, synthetic_trace)
check(synthetic_bridge.empty, "GUARD wrong-year exact issuer rejected")

# Same issuer/month without a TRACE series is unknowable; an explicit series
# resolves it without collapsing the one-to-many structure.
twins = pd.DataFrame([
    deal("Beta Re Ltd. (Series 2020-1)", "Jan 2020", "beta-1"),
    deal("Beta Re Ltd. (Series 2020-2)", "Jan 2020", "beta-2"),
])
ambiguous, _, unmatched = match_frames(
    twins, pd.DataFrame([security("000000AB9", "BETA RE LTD", "2020-01-10")]))
check(ambiguous.empty, "GUARD same-month series collision not cross-joined")
check(unmatched.iloc[0].unmatched_reason == "ambiguous_artemis_deals",
      "UNIT ambiguity diagnosis")
resolved, _, _ = match_frames(
    twins, pd.DataFrame([security("000000AC7", "BETA RE LTD SERIES 2020-2",
                                         "2020-01-10")]))
check(len(resolved) == 1 and resolved.iloc[0].deal_url.endswith("beta-2"),
      "UNIT explicit TRACE series resolves collision")

check(extract_series("Home Re 2021-1 Ltd.") == "2021-1",
      "UNIT unlabelled Artemis series inside the legal name")
check(normalise_issuer("Home Re 2021-1 Ltd.", "artemis") == "HOME RE",
      "UNIT Artemis series token is not part of the issuer")

# A master row with no issuer name may borrow one from its exchange ticker,
# but only when every named CUSIP on that ticker agrees, and the borrowing is
# recorded so the match can never be reported as identity evidence.
ticker_trace = pd.DataFrame([
    {"cusip_id": "000000BA1", "issuer_nm": "GAMMA RE LTD", "scrty_ds": "ILS",
     "debt_type_cd": "", "cpn_rt": "3.0", "mtrty_dt": "2024-01-15",
     "stdt": "2020-01-10", "enddt": "2021-01-01", "company_symbol": "GMRE"},
    {"cusip_id": "000000BB9", "issuer_nm": "UNKNOWN ISSUER", "scrty_ds": "ILS",
     "debt_type_cd": "", "cpn_rt": "3.0", "mtrty_dt": "2024-01-15",
     "stdt": "2020-01-10", "enddt": "2021-01-01", "company_symbol": "GMRE"},
    {"cusip_id": "000000BC7", "issuer_nm": "DELTA RE LTD", "scrty_ds": "ILS",
     "debt_type_cd": "", "cpn_rt": "3.0", "mtrty_dt": "2024-01-15",
     "stdt": "2020-01-10", "enddt": "2021-01-01", "company_symbol": "MIXD"},
    {"cusip_id": "000000BD5", "issuer_nm": "EPSILON RE LTD", "scrty_ds": "ILS",
     "debt_type_cd": "", "cpn_rt": "3.0", "mtrty_dt": "2024-01-15",
     "stdt": "2020-01-10", "enddt": "2021-01-01", "company_symbol": "MIXD"},
    {"cusip_id": "000000BE3", "issuer_nm": "", "scrty_ds": "ILS",
     "debt_type_cd": "", "cpn_rt": "3.0", "mtrty_dt": "2024-01-15",
     "stdt": "2020-01-10", "enddt": "2021-01-01", "company_symbol": "MIXD"},
])
ticker_collapsed = collapse_trace(ticker_trace).set_index("cusip_id")
check(ticker_collapsed.loc["000000BA1", "issuer_name_source"] == "master",
      "UNIT named master row keeps its own name")
check(ticker_collapsed.loc["000000BB9", "issuer_nm"] == "GAMMA RE LTD"
      and ticker_collapsed.loc["000000BB9", "issuer_name_source"].startswith("ticker GMRE"),
      "UNIT nameless CUSIP borrows the unanimous ticker name and is flagged")
check(ticker_collapsed.loc["000000BE3", "issuer_nm"] == ""
      and ticker_collapsed.loc["000000BE3", "issuer_name_source"] == "master",
      "GUARD ticker shared by disagreeing issuers lends no name")
borrowed_bridge, _, _ = match_frames(
    pd.DataFrame([deal("Gamma Re Ltd. (Series 2020-1)", "Jan 2020", "gamma")]),
    ticker_collapsed.reset_index())
check(set(borrowed_bridge.cusip_id) == {"000000BA1", "000000BB9"},
      "UNIT borrowed name still has to clear the strict match")
borrowed = borrowed_bridge.set_index("cusip_id")
check(borrowed.loc["000000BA1", "match_confidence"] == "high"
      and borrowed.loc["000000BB9", "match_confidence"] == "medium"
      and borrowed.loc["000000BB9", "match_method"].endswith("+ticker_inferred_name")
      and "ticker GMRE" in borrowed.loc["000000BB9", "name_evidence"],
      "GUARD borrowed name caps confidence at medium and is visible in evidence")

if "--unit-only" in sys.argv:
    if failures:
        raise SystemExit("%d bridge unit test(s) failed" % len(failures))
    print("\nAll bridge unit tests passed.")
    raise SystemExit(0)


bridge, unmatched_artemis, unmatched_trace, summary = build()


def cusips_for(name):
    return set(bridge.loc[bridge.artemis_issuer_name.eq(name), "cusip_id"])


# Hand-verified from issuer, first TRACE effective date, maturity, and the
# unique Artemis directory month. These exact sets also pin one-to-many output.
GOLDEN = {
    "Citrus Re Ltd. (Series 2015-1)": {"177510AC8", "177510AD6", "177510AE4"},
    "Kilimanjaro Re Ltd. (Series 2015-1)": {"494074AF4", "494074AG2"},
    "Residential Reinsurance 2020 Limited (Series 2020-1)": {"76124AAB4"},
    "Residential Reinsurance 2020 Limited (Series 2020-2)":
        {"76120AAA0", "76120AAB8", "76120AAC6"},
    "Kortis Capital Ltd.": {"500646AA2"},
    "Golden State Re II Ltd. (Series 2018-1)": {"38123FAB4"},
}
for name, expected in GOLDEN.items():
    actual = cusips_for(name)
    check(actual == expected, "EXPECT golden %s" % name,
          "actual=%s expected=%s" % (sorted(actual), sorted(expected)))

# Known-wrong cross-products: the index has no evidence that distinguishes
# these same-vehicle, same-month series.
for name in [
        "Citrus Re Ltd. (Series 2014-1)",
        "Citrus Re Ltd. (Series 2014-2)",
        "Kilimanjaro Re Ltd. (Series 2018-1)",
        "Kilimanjaro Re Ltd. (Series 2018-2)"]:
    check(not cusips_for(name), "REJECT ambiguous pair %s" % name)

check(bridge.cusip_id.is_unique, "GUARD one CUSIP maps to at most one Artemis deal")
check(bridge[["name_evidence", "date_evidence", "maturity_evidence",
              "coupon_evidence", "size_evidence", "match_confidence"]]
      .apply(lambda column: column.astype(str).str.strip().ne("").all()).all(),
      "GUARD every pair carries complete evidence and confidence")
check(set(bridge.match_confidence).issubset({"high", "medium", "low"}),
      "GUARD confidence vocabulary")
check(summary["pre_2021_contribution"]["pre_2021_cusips_never_labelled_un_cat"] > 0,
      "EXPECT bridge adds pre-2021 CUSIPs beyond UN-CAT")
check(len(unmatched_artemis) + bridge.deal_url.nunique() == 1311,
      "GUARD every Artemis deal is matched or diagnosed")
check(len(unmatched_trace) + bridge[bridge.trace_ever_un_cat].cusip_id.nunique() == 663,
      "GUARD every UN-CAT CUSIP is matched or diagnosed")

if failures:
    raise SystemExit("%d bridge test(s) failed" % len(failures))
print("\nAll bridge tests passed.")
