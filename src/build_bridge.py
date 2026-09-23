"""Build a conservative Artemis deal -> TRACE 144A CUSIP bridge.

Inputs are local-only. Artemis content and WRDS TRACE exports are licensed
research inputs and must not be copied or redistributed. This script makes no
network requests and writes only derived, gitignored CSV/JSON reports.

The Artemis directory index is deliberately the only Artemis matching input.
The richer prose-mined deal/tranche tables are provisional and are not read.
"""

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "data" / "index.csv"
TRACE_PATH = (ROOT / "data" / "raw" / "wrds" / "2026-08-30" /
              "wrds_trace_camasterfile_144a.csv")
BRIDGE_PATH = ROOT / "data" / "bridge.csv"
UNMATCHED_ARTEMIS_PATH = ROOT / "data" / "bridge_unmatched_artemis.csv"
UNMATCHED_TRACE_PATH = ROOT / "data" / "bridge_unmatched_trace.csv"
SUMMARY_PATH = ROOT / "data" / "bridge_summary.json"

MAX_MONTH_DISTANCE = 1
MAX_TENOR_YEARS = 15.0
MIN_TENOR_DAYS = 30

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

TOKEN_ALIASES = {
    "LIMITED": "LTD",
    "LTD": "LTD",
    "REINS": "REINSURANCE",
    "REINSURENCE": "REINSURANCE",
    "CAP": "CAPITAL",
    "ST": "STATE",
    "STR": "STREET",
    "BRDG": "BRIDGE",
    "LTS": "LIGHTS",
    "PT": "POINT",
    "RIV": "RIVER",
    "PROT": "PROTECTION",
    "MKTS": "MARKETS",
    "INTERGRITY": "INTEGRITY",
}

LEGAL_TAIL = {"LTD", "DAC", "PLC", "PCC", "PTE", "LP", "CORP", "INC", "LLC"}
GENERIC_FUZZY = LEGAL_TAIL | {"RE", "REINSURANCE", "CAPITAL", "THE"}


def _ascii_upper(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().replace("&", " AND ")


def extract_series(value):
    """Return an explicit series identifier, never a bare legal-entity year."""
    text = _ascii_upper(value)
    match = re.search(r"\bSER(?:IES)?\s*[-:]?\s*((?:19|20)\d{2})[- ]?([0-9]+[A-Z]?)\b", text)
    if match:
        return "%s-%s" % (match.group(1), match.group(2))
    match = re.search(r"\((?:SERIES\s+)?((?:19|20)\d{2}-[0-9]+[A-Z]?)\)", text)
    if match:
        return match.group(1)
    # An unlabelled year-dash-number inside the legal name: "Home Re 2021-1
    # Ltd.", "Loma Reinsurance (Bermuda) Ltd. 2013-1". A bare year never counts.
    match = re.search(r"\b((?:19|20)\d{2}-[0-9]+[A-Z]?)\b", text)
    if match:
        return match.group(1)
    return ""


def _prepare_name(value, source):
    text = _ascii_upper(value)
    if source == "artemis":
        text = re.split(r"\s+(?:-|\N{EN DASH}|\N{EM DASH})\s+", text, maxsplit=1)[0]
        text = re.sub(r"\([^)]*\)", " ", text)
        # "Home Re 2021-1 Ltd.": the series token is not part of the issuer.
        text = re.sub(r"\b(?:19|20)\d{2}-[0-9]+[A-Z]?\b", " ", text)
    else:
        text = re.split(r"\b(?:ACTING\s+(?:IN|N|ON)|SEGREGATED\s+ACCT|SERIES\s+ACCOUNT)\b",
                        text, maxsplit=1)[0]
        text = re.sub(r"\bSER(?:IES)?\s*[-:]?\s*(?:19|20)\d{2}[- ]?[0-9]+[A-Z]?\b", " ", text)
        text = re.sub(r"\b(?:19|20)\d{2}-[0-9]+[A-Z]?\s*$", " ", text)
        # Some TRACE names put an unlabelled series after an already-complete
        # legal issuer: "AQUILA RE I LTD 2023-1".
        text = re.sub(r"\b(LTD|DAC|PLC|PCC|PTE)\s+(?:19|20)\d{2}-[0-9]+[A-Z]?\b", r"\1", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value, source, aliases=True):
    tokens = _prepare_name(value, source).split()
    if aliases:
        tokens = [TOKEN_ALIASES.get(token, token) for token in tokens]
    while tokens and tokens[-1] in LEGAL_TAIL:
        tokens.pop()
    if tokens and tokens[0] == "THE":
        tokens.pop(0)
    return tokens


def normalise_issuer(value, source="artemis"):
    """Canonical issuer key used for matching; series and legal tails removed."""
    return " ".join(_tokens(value, source, aliases=True))


def _strict_issuer(value, source):
    return " ".join(_tokens(value, source, aliases=False))


def _month_ordinal_from_artemis(value):
    parts = str(value).strip().split()
    if len(parts) != 2 or parts[0] not in MONTHS:
        return None
    try:
        return int(parts[1]) * 12 + MONTHS[parts[0]]
    except ValueError:
        return None


def _month_ordinal_from_date(value):
    parts = str(value).split("-")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]) * 12 + int(parts[1])
    except ValueError:
        return None


def _date_guard(artemis_month, trace_month):
    """Hard acceptance guard; a name match outside this window is not identity."""
    if artemis_month is None or trace_month is None:
        return False
    if pd.isna(artemis_month) or pd.isna(trace_month):
        return False
    return abs(int(artemis_month) - int(trace_month)) <= MAX_MONTH_DISTANCE


def _is_nameless(names):
    upper = names.fillna("").astype(str).str.strip().str.upper()
    return upper.eq("") | upper.str.contains("UNKNOWN ISSUER", regex=False)


def _infer_names_from_ticker(work, base):
    """Borrow an issuer name from the ticker when every named holder agrees.

    Some master rows carry no issuer name but do carry the exchange ticker in
    ``company_symbol``. If every named CUSIP sharing that ticker normalises to
    one issuer key, the nameless CUSIP is given that name and flagged; the
    match must still clear the date guard, and confidence is capped.
    """
    if "company_symbol" not in work.columns:
        return base
    symbol = work.company_symbol.fillna("").astype(str).str.strip()
    usable = symbol.ne("") & symbol.ne(work.cusip_id.astype(str))
    named = work[usable & ~_is_nameless(work.issuer_nm)].copy()
    if named.empty:
        return base
    named["key"] = named.issuer_nm.map(lambda x: normalise_issuer(x, "trace"))
    named["symbol"] = symbol[named.index]
    agree = named.groupby("symbol").key.nunique().eq(1)
    unanimous = named[named.symbol.isin(agree[agree].index)]
    counts = unanimous.groupby("symbol").cusip_id.nunique()
    chosen = (unanimous.sort_values(["symbol", "stdt_parsed", "issuer_nm"], kind="stable")
              .drop_duplicates("symbol").set_index("symbol").issuer_nm)
    nameless = base[_is_nameless(base.issuer_nm)]
    if nameless.empty:
        return base
    first_symbol = (work[usable].sort_values(["cusip_id", "stdt_parsed"], kind="stable")
                    .drop_duplicates("cusip_id").set_index("cusip_id").company_symbol)
    for row in nameless.itertuples():
        sym = first_symbol.get(row.cusip_id)
        if sym in chosen.index:
            base.loc[row.Index, "issuer_nm"] = chosen[sym]
            base.loc[row.Index, "issuer_name_source"] = "ticker %s shared by %d named CUSIPs" % (
                sym, int(counts[sym]))
    return base


def collapse_trace(trace):
    """Collapse longitudinal master history to one evidence-bearing CUSIP row."""
    required = {"cusip_id", "issuer_nm", "scrty_ds", "debt_type_cd", "cpn_rt",
                "mtrty_dt", "stdt", "enddt"}
    missing = required - set(trace.columns)
    if missing:
        raise ValueError("TRACE input missing columns: %s" % ", ".join(sorted(missing)))

    work = trace.copy()
    work = work[work.cusip_id.astype(str).str.strip().ne("")].copy()
    work["stdt_parsed"] = pd.to_datetime(work.stdt, errors="coerce")
    work["mtrty_parsed"] = pd.to_datetime(work.mtrty_dt, errors="coerce")
    work["enddt_parsed"] = pd.to_datetime(work.enddt, errors="coerce")
    work["coupon_num"] = pd.to_numeric(work.cpn_rt, errors="coerce")
    work["ever_un_cat_row"] = work.debt_type_cd.eq("UN-CAT")

    work["usable_coupon"] = work.coupon_num.where(
        work.coupon_num.gt(0) & work.coupon_num.lt(50))
    grouped = work.groupby("cusip_id", sort=True)
    out = grouped.agg(
        trace_issue_date=("stdt_parsed", "min"),
        trace_last_end_date=("enddt_parsed", "max"),
        trace_maturity_date=("mtrty_parsed", "min"),
        trace_ever_un_cat=("ever_un_cat_row", "max"),
        trace_history_rows=("cusip_id", "size"),
        trace_coupon_min=("coupon_num", "min"),
        trace_coupon_max=("coupon_num", "max"),
        trace_coupon_observation_count=("coupon_num", "count"),
        trace_usable_coupon_min=("usable_coupon", "min"),
        trace_usable_coupon_max=("usable_coupon", "max"),
        trace_usable_coupon_observation_count=("usable_coupon", "count"),
    ).reset_index()

    # The earliest historical master row is closest to original issuance and
    # generally has the least-truncated issuer, but some CUSIPs start life as
    # "UNKNOWN ISSUER" or blank and are named only in later rows. Prefer the
    # earliest *named* row and record when that was not the first row. Keep
    # all observed variants too.
    work["_nameless"] = _is_nameless(work.issuer_nm)
    ordered = work.sort_values(["cusip_id", "_nameless", "stdt_parsed", "issuer_nm"], kind="stable")
    base = ordered.drop_duplicates("cusip_id")[["cusip_id", "issuer_nm", "scrty_ds"]]
    first_row_nameless = (work.sort_values(["cusip_id", "stdt_parsed", "issuer_nm"], kind="stable")
                          .drop_duplicates("cusip_id").set_index("cusip_id")._nameless)
    base["issuer_name_source"] = "master"
    later = base.cusip_id.map(first_row_nameless).fillna(False).astype(bool) & ~_is_nameless(base.issuer_nm)
    base.loc[later, "issuer_name_source"] = "master:later_row"
    base = _infer_names_from_ticker(work, base)
    variants = (work.loc[work.issuer_nm.astype(str).str.strip().ne(""), ["cusip_id", "issuer_nm"]]
                .drop_duplicates().sort_values(["cusip_id", "issuer_nm"])
                .groupby("cusip_id").issuer_nm.agg("|".join)
                .rename("issuer_variants").reset_index())
    codes = (work[work.debt_type_cd.ne("")][["cusip_id", "debt_type_cd"]]
             .drop_duplicates().sort_values(["cusip_id", "debt_type_cd"])
             .groupby("cusip_id").debt_type_cd.agg("|".join)
             .rename("trace_debt_type_codes").reset_index())
    out = out.merge(base, on="cusip_id", how="left")
    out = out.merge(variants, on="cusip_id", how="left")
    out = out.merge(codes, on="cusip_id", how="left")
    out["trace_debt_type_codes"] = out.trace_debt_type_codes.fillna("")
    for column in ["trace_issue_date", "trace_last_end_date", "trace_maturity_date"]:
        out[column] = out[column].map(
            lambda value: "" if pd.isna(value) else value.date().isoformat())
    for column in ["trace_coupon_min", "trace_coupon_max",
                   "trace_usable_coupon_min", "trace_usable_coupon_max"]:
        out[column] = out[column].map(lambda value: "" if pd.isna(value) else float(value))
    return out


def _name_match(artemis_row, trace_row):
    akey = artemis_row["issuer_key"]
    tkey = trace_row["issuer_key"]
    if not akey or not tkey:
        return None
    if akey == tkey:
        strict_equal = artemis_row["issuer_strict"] == trace_row["issuer_strict"]
        return {"rank": 3, "method": "exact_normalized_issuer" if strict_equal
                else "canonical_alias_issuer", "similarity": 1.0}

    short, long = sorted([akey, tkey], key=len)
    if len(short) >= 8 and long.startswith(short + " "):
        return {"rank": 2, "method": "truncated_issuer_prefix",
                "similarity": round(float(len(short)) / len(long), 4)}

    atokens = set(token for token in akey.split() if token not in GENERIC_FUZZY)
    ttokens = set(token for token in tkey.split() if token not in GENERIC_FUZZY)
    if not atokens or not ttokens:
        return None
    common = atokens & ttokens
    jaccard = float(len(common)) / len(atokens | ttokens)
    ratio = SequenceMatcher(None, akey, tkey).ratio()
    first_same = akey.split()[0] == tkey.split()[0]
    if first_same and len(common) >= 2 and (jaccard >= 0.75 or ratio >= 0.86):
        return {"rank": 1, "method": "fuzzy_issuer_date",
                "similarity": round(max(jaccard, ratio), 4)}
    return None


def _maturity_evidence(trace_row, artemis_row):
    issue = pd.to_datetime(trace_row.trace_issue_date, errors="coerce")
    maturity = pd.to_datetime(trace_row.trace_maturity_date, errors="coerce")
    art_month = pd.to_datetime(artemis_row.date_text, format="%b %Y", errors="coerce")
    if pd.isna(maturity):
        return True, "unavailable", "TRACE maturity is blank"
    anchors = [stamp for stamp in [issue, art_month] if not pd.isna(stamp)]
    if not anchors:
        return False, "contradiction", "no usable issue-date anchor"
    if any((maturity - stamp).days < MIN_TENOR_DAYS for stamp in anchors):
        return False, "contradiction", "maturity is not after issue/deal month"
    tenor = (maturity - anchors[0]).days / 365.25
    if tenor > MAX_TENOR_YEARS:
        return False, "contradiction", "maturity implies %.2f-year tenor" % tenor
    return True, "corroborates", "maturity implies %.2f-year tenor" % tenor


def _coupon_evidence(trace_row):
    usable_count = int(trace_row.trace_usable_coupon_observation_count)
    if usable_count:
        return ("available_not_comparable_to_index: %d plausible coupon observations, range %s-%s%%" %
                (usable_count, trace_row.trace_usable_coupon_min,
                 trace_row.trace_usable_coupon_max))
    if int(trace_row.trace_coupon_observation_count):
        return "not_comparable: only zero/placeholder coupon observations"
    return "unavailable: TRACE coupon is blank"


def _confidence(name_rank, month_distance, series_state, maturity_state):
    if (name_rank == 3 and month_distance == 0 and
            series_state != "missing_or_not_stated" and maturity_state == "corroborates"):
        return "high"
    if name_rank == 3 and month_distance == 0 and maturity_state == "corroborates":
        return "high"
    if name_rank >= 2 and maturity_state != "contradiction":
        return "medium"
    return "low"


def match_frames(index, securities):
    """Return bridge and diagnostic frames from Artemis and collapsed TRACE."""
    art = index.copy().reset_index(drop=True)
    art["artemis_id"] = art.index.astype(int)
    art["issuer_key"] = art.issuer_name.map(lambda x: normalise_issuer(x, "artemis"))
    art["issuer_strict"] = art.issuer_name.map(lambda x: _strict_issuer(x, "artemis"))
    art["series_id"] = art.issuer_name.map(extract_series)
    art["month_ordinal"] = art.date_text.map(_month_ordinal_from_artemis)

    sec = securities.copy().reset_index(drop=True)
    sec["issuer_key"] = sec.issuer_nm.map(lambda x: normalise_issuer(x, "trace"))
    sec["issuer_strict"] = sec.issuer_nm.map(lambda x: _strict_issuer(x, "trace"))
    sec["series_id"] = sec.issuer_nm.map(extract_series)
    sec["month_ordinal"] = sec.trace_issue_date.map(_month_ordinal_from_date)

    art_by_month = defaultdict(list)
    art_by_key = defaultdict(list)
    for row in art.to_dict("records"):
        if row["month_ordinal"] is not None and not pd.isna(row["month_ordinal"]):
            art_by_month[int(row["month_ordinal"])].append(row)
        if row["issuer_key"]:
            art_by_key[row["issuer_key"]].append(row)

    selected = []
    trace_diagnostics = []
    ambiguous_artemis_ids = set()
    for trace_row in sec.itertuples(index=False):
        tr = trace_row._asdict()
        month = tr["month_ordinal"]
        candidates = []
        maturity_rejections = 0
        if month is not None and not pd.isna(month):
            nearby = []
            for delta in range(-MAX_MONTH_DISTANCE, MAX_MONTH_DISTANCE + 1):
                nearby.extend(art_by_month.get(int(month) + delta, []))
            # Exact issuer candidates from all years make the date guard an
            # independently necessary safety check. Nearby rows additionally
            # permit controlled truncation/fuzzy recovery.
            pool = nearby + art_by_key.get(tr["issuer_key"], [])
            pool = {row["artemis_id"]: row for row in pool}.values()
            for ar in pool:
                name = _name_match(ar, tr)
                if name is None:
                    continue
                if not _date_guard(ar["month_ordinal"], month):
                    continue
                month_distance = abs(int(ar["month_ordinal"]) - int(month))
                a_series, t_series = ar["series_id"], tr["series_id"]
                if a_series and t_series and a_series != t_series:
                    continue
                series_state = ("exact_series" if a_series and t_series else
                                "missing_or_not_stated")
                maturity_ok, maturity_state, maturity_text = _maturity_evidence(
                    pd.Series(tr), pd.Series(ar))
                if not maturity_ok:
                    maturity_rejections += 1
                    continue
                score = (name["rank"], 1 if series_state == "exact_series" else 0,
                         -month_distance)
                candidates.append((score, name, month_distance, series_state,
                                   maturity_state, maturity_text, ar))

        if not candidates:
            reason = "no_name_and_date_candidate"
            if maturity_rejections:
                reason = "candidate_contradicted_by_maturity"
            trace_diagnostics.append({"cusip_id": tr["cusip_id"], "reason": reason,
                                      "candidate_count": 0, "detail": ""})
            continue

        best_score = max(item[0] for item in candidates)
        best = [item for item in candidates if item[0] == best_score]
        # Different Artemis rows with indistinguishable index evidence cannot
        # be resolved. Emitting every cross-product would fabricate tranches.
        if len(best) != 1:
            ids = sorted(item[6]["artemis_id"] for item in best)
            ambiguous_artemis_ids.update(ids)
            trace_diagnostics.append({
                "cusip_id": tr["cusip_id"],
                "reason": "ambiguous_artemis_deals",
                "candidate_count": len(best),
                "detail": "artemis_ids=" + "|".join(str(value) for value in ids),
            })
            continue

        _, name, distance, series_state, maturity_state, maturity_text, ar = best[0]
        confidence = _confidence(name["rank"], distance, series_state, maturity_state)
        name_source = tr.get("issuer_name_source") or "master"
        method = name["method"]
        if name_source.startswith("ticker"):
            # A borrowed name is corroborating evidence, not identity. A name
            # taken from a later master row is still the master's own identity.
            confidence = "medium" if confidence == "high" else confidence
            method = method + "+ticker_inferred_name"
        date_evidence = ("same issue month" if distance == 0 else
                         "TRACE issue month is adjacent to Artemis month")
        selected.append({
            "deal_url": ar["deal_url"],
            "artemis_issuer_name": ar["issuer_name"],
            "artemis_sponsor": ar["sponsor"],
            "artemis_size_text": ar["size_text"],
            "artemis_date_text": ar["date_text"],
            "artemis_series_id": ar["series_id"],
            "cusip_id": tr["cusip_id"],
            "trace_issuer_nm": tr["issuer_nm"],
            "trace_issuer_variants": tr["issuer_variants"],
            "trace_security_description": tr["scrty_ds"],
            "trace_debt_type_codes": tr["trace_debt_type_codes"],
            "trace_ever_un_cat": tr["trace_ever_un_cat"],
            "trace_history_rows": tr["trace_history_rows"],
            "trace_issue_date": tr["trace_issue_date"],
            "trace_last_end_date": tr["trace_last_end_date"],
            "trace_maturity_date": tr["trace_maturity_date"],
            "trace_coupon_min": tr["trace_coupon_min"],
            "trace_coupon_max": tr["trace_coupon_max"],
            "trace_coupon_observation_count": tr["trace_coupon_observation_count"],
            "match_confidence": confidence,
            "match_method": method,
            "name_similarity": name["similarity"],
            "name_evidence": "Artemis '%s' -> %s; TRACE '%s' -> %s; TRACE name source: %s" %
                             (ar["issuer_name"], ar["issuer_key"],
                              tr["issuer_nm"], tr["issuer_key"], name_source),
            "series_evidence": series_state,
            "date_evidence": date_evidence,
            "maturity_evidence": maturity_state + ": " + maturity_text,
            "coupon_evidence": _coupon_evidence(pd.Series(tr)),
            "size_evidence": "not_testable: TRACE master has no principal/size field",
        })
        trace_diagnostics.append({"cusip_id": tr["cusip_id"], "reason": "matched",
                                  "candidate_count": 1, "detail": ar["deal_url"]})

    bridge = pd.DataFrame(selected)
    if not bridge.empty:
        bridge = bridge.sort_values(["artemis_date_text", "artemis_issuer_name", "cusip_id"],
                                    kind="stable").reset_index(drop=True)

    matched_deals = set(bridge.deal_url) if not bridge.empty else set()
    unmatched_artemis = []
    trace_keys = set(sec.issuer_key)
    trace_max_month = sec.month_ordinal.dropna().max() if len(sec) else None
    for ar in art.to_dict("records"):
        if ar["deal_url"] in matched_deals:
            continue
        if str(ar["size_text"]).strip().lower() in {"not issued", "withdrawn", "cancelled"}:
            reason = "not_issued"
        elif ar["artemis_id"] in ambiguous_artemis_ids:
            reason = "ambiguous_same_month_series"
        elif (trace_max_month is not None and ar["month_ordinal"] is not None and
              ar["month_ordinal"] > trace_max_month):
            reason = "after_trace_snapshot"
        elif ar["issuer_key"] in trace_keys:
            reason = "issuer_present_but_no_unique_date_match"
        elif ar["month_ordinal"] is not None and ar["month_ordinal"] < 2002 * 12 + 7:
            reason = "before_trace_export_coverage"
        else:
            reason = "no_trace_issuer_candidate"
        unmatched_artemis.append({
            "issuer_name": ar["issuer_name"], "deal_url": ar["deal_url"],
            "sponsor": ar["sponsor"], "size_text": ar["size_text"],
            "date_text": ar["date_text"], "issuer_key": ar["issuer_key"],
            "unmatched_reason": reason,
        })

    diag = pd.DataFrame(trace_diagnostics)
    unmatched_trace = sec[sec.trace_ever_un_cat].copy()
    unmatched_trace = unmatched_trace.merge(diag, on="cusip_id", how="left")
    unmatched_trace = unmatched_trace[unmatched_trace.reason.ne("matched")].copy()
    art_keys = set(art.issuer_key)
    diagnoses = []
    for row in unmatched_trace.itertuples(index=False):
        reason = row.reason
        if reason == "no_name_and_date_candidate":
            if row.issuer_key in art_keys:
                reason = "artemis_issuer_present_date_mismatch"
            else:
                fuzzy_any = any(_name_match(
                    {"issuer_key": key, "issuer_strict": key},
                    {"issuer_key": row.issuer_key, "issuer_strict": row.issuer_strict})
                    for key in art_keys if key)
                reason = ("probable_normalisation_failure" if fuzzy_any else
                          "probable_artemis_gap_or_false_un_cat")
        diagnoses.append(reason)
    unmatched_trace["unmatched_reason"] = diagnoses
    keep = ["cusip_id", "issuer_nm", "issuer_variants", "issuer_key", "scrty_ds",
            "trace_debt_type_codes", "trace_issue_date", "trace_maturity_date",
            "trace_coupon_min", "trace_coupon_max", "trace_history_rows",
            "unmatched_reason", "candidate_count", "detail"]
    unmatched_trace = unmatched_trace[keep].sort_values(
        ["unmatched_reason", "issuer_nm", "cusip_id"], kind="stable")
    return bridge, pd.DataFrame(unmatched_artemis), unmatched_trace


def summarize(index, securities, bridge, unmatched_artemis, unmatched_trace):
    matched_deals = int(bridge.deal_url.nunique()) if not bridge.empty else 0
    matched_cusips = int(bridge.cusip_id.nunique()) if not bridge.empty else 0
    uncat = securities[securities.trace_ever_un_cat]
    matched_uncat = int(bridge[bridge.trace_ever_un_cat].cusip_id.nunique()) if not bridge.empty else 0
    years = pd.to_numeric(bridge.artemis_date_text.str[-4:], errors="coerce") if not bridge.empty else pd.Series(dtype=float)
    pre = bridge[years.lt(2021)] if not bridge.empty else bridge
    beyond = bridge[~bridge.trace_ever_un_cat] if not bridge.empty else bridge
    pre_beyond = pre[~pre.trace_ever_un_cat] if not pre.empty else pre
    return {
        "inputs": {
            "artemis_deals": int(len(index)),
            "trace_unique_cusips": int(len(securities)),
            "trace_ever_un_cat_cusips": int(len(uncat)),
        },
        "matches": {
            "bridge_pairs": int(len(bridge)),
            "artemis_deals_matched": matched_deals,
            "artemis_match_rate_pct": round(100.0 * matched_deals / len(index), 2),
            "trace_cusips_matched": matched_cusips,
            "un_cat_cusips_matched": matched_uncat,
            "un_cat_match_rate_pct": round(100.0 * matched_uncat / len(uncat), 2),
        },
        "pre_2021_contribution": {
            "matched_pairs_for_pre_2021_deals": int(len(pre)),
            "matched_pre_2021_deals": int(pre.deal_url.nunique()) if not pre.empty else 0,
            "matched_cusips_for_pre_2021_deals": int(pre.cusip_id.nunique()) if not pre.empty else 0,
            "cusips_never_labelled_un_cat": int(beyond.cusip_id.nunique()) if not beyond.empty else 0,
            "pre_2021_cusips_never_labelled_un_cat": int(pre_beyond.cusip_id.nunique()) if not pre_beyond.empty else 0,
        },
        "confidence_distribution_pairs": ({str(k): int(v) for k, v in
                                            bridge.match_confidence.value_counts().items()}
                                           if not bridge.empty else {}),
        "unmatched_artemis_by_reason": {str(k): int(v) for k, v in
                                         unmatched_artemis.unmatched_reason.value_counts().items()},
        "unmatched_un_cat_by_reason": {str(k): int(v) for k, v in
                                        unmatched_trace.unmatched_reason.value_counts().items()},
    }


def build(index_path=INDEX_PATH, trace_path=TRACE_PATH):
    index = pd.read_csv(index_path, dtype=str, keep_default_na=False)
    expected = {"issuer_name", "deal_url", "sponsor", "size_text", "date_text"}
    missing = expected - set(index.columns)
    if missing:
        raise ValueError("Artemis index missing columns: %s" % ", ".join(sorted(missing)))
    trace = pd.read_csv(trace_path, dtype=str, keep_default_na=False)
    securities = collapse_trace(trace)
    bridge, unmatched_artemis, unmatched_trace = match_frames(index, securities)
    summary = summarize(index, securities, bridge, unmatched_artemis, unmatched_trace)
    return bridge, unmatched_artemis, unmatched_trace, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--trace", type=Path, default=TRACE_PATH)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)

    bridge, unmatched_artemis, unmatched_trace, summary = build(args.index, args.trace)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bridge.to_csv(args.output_dir / BRIDGE_PATH.name, index=False, encoding="utf-8")
    unmatched_artemis.to_csv(args.output_dir / UNMATCHED_ARTEMIS_PATH.name,
                             index=False, encoding="utf-8")
    unmatched_trace.to_csv(args.output_dir / UNMATCHED_TRACE_PATH.name,
                           index=False, encoding="utf-8")
    with (args.output_dir / SUMMARY_PATH.name).open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print("wrote %s (%d matched pairs)" % (args.output_dir / BRIDGE_PATH.name, len(bridge)))
    print("wrote %s (%d unmatched Artemis deals)" %
          (args.output_dir / UNMATCHED_ARTEMIS_PATH.name, len(unmatched_artemis)))
    print("wrote %s (%d unmatched UN-CAT CUSIPs)" %
          (args.output_dir / UNMATCHED_TRACE_PATH.name, len(unmatched_trace)))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
