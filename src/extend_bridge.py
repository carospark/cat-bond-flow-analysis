"""Program-level attribution for CUSIPs the strict bridge cannot place.

The strict bridge (``build_bridge.py``) refuses a match unless issuer name and
issue month agree within one month and nothing contradicts it. That leaves
real ILS securities unattributed for three reasons that this layer records
explicitly rather than forcing through the strict path:

* the directory has the issuer program but no deal within the date guard
  (shelf takedowns such as Pioneer 2002, repeat series such as Successor X);
* the directory has several deals in the same month for the same vehicle, so
  no single deal is identifiable;
* the directory has no deal at all for the program (later Sector Re V
  sidecar series, privately placed notes).

For each such CUSIP this script finds the issuer *program*, the directory
deals in that program, and the nearest deal by issue month. Output is a
separate table with confidence ``program``; it never modifies ``bridge.csv``.

Levels, strongest first:

* ``program_nearest``: program found in the directory and exactly one deal
  is nearest by month within ``--max-months``; that deal is attached.
* ``program_maturity_split``: two or more deals were equally near, every one
  of them states a scheduled maturity in the parsed directory (``--deals``),
  and the TRACE maturity month falls within ``--maturity-tolerance`` months
  of exactly one; that deal is attached. Twins that differ only in tenor
  (Kilimanjaro III 2021-1 versus 2021-2) split this way. A tied deal with no
  stated maturity blocks the split, because it cannot be ruled out.
* ``program_tied``: program found, two or more deals equally near and not
  separable by maturity; the program is attached, the deal is left blank and
  the tied deals listed.
* ``program_only``: program found but no deal within ``--max-months``.
* ``program_absent``: the program name does not occur in the directory.

Program key: the strict bridge's normalised issuer key with trailing Roman or
Arabic numerals removed (``SECTOR RE V`` and ``SECTOR RE`` are one program).

Holders' titles check every row. After attribution, the fund-reported
N-PORT titles for each CUSIP are resolved to directory deals with the strict
bridge's own issuer normalisation and series extraction (the title is cut
before its class, series or coupon suffix first). When every title resolves
to the same single deal and the TRACE issue month is within
``--title-max-months`` of that deal's directory month:

* a row attached to a different deal is re-pointed, level
  ``program_nport_title_repointed`` (Queen Street 2023 Re DAC was the
  nearest-by-month Montoya Re 2022-2 before this check);
* a tied row whose tie includes the named deal is resolved, level
  ``program_nport_title``;
* a row already on that deal is marked confirmed.

Titles that name a deal outside the date window, that name an issuer the
directory lacks, or that disagree with one another never move a row; they
set ``title_conflict`` and say why in ``title_evidence``, so the attribution
is kept but not silently.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_bridge import (  # noqa: E402
    TRACE_PATH,
    _month_ordinal_from_artemis,
    _month_ordinal_from_date,
    collapse_trace,
    extract_series,
    normalise_issuer,
)

DATA = ROOT / "data"
INDEX_PATH = DATA / "index.csv"
DEALS_PATH = DATA / "deals.csv"
# Directory maturity fields in order of preference; the dictionary calls
# maturity_scheduled the resolved one, maturity_date the stated one, and
# maturity_date_derived issue-plus-term.
MATURITY_FIELDS = ["maturity_scheduled", "maturity_date", "maturity_date_derived"]
BRIDGE_PATH = DATA / "bridge.csv"
SCREEN_PATH = DATA / "raw" / "tier1" / "wrds" / "screens" / "screen_all_1332.txt"
SUPPLEMENT_PATH = DATA / "raw" / "tier1" / "wrds" / "screens" / "supplement_pull_needed.txt"
OUTPUT_PATH = DATA / "bridge_program.csv"
SUMMARY_PATH = DATA / "bridge_program_summary.json"

ROMAN = re.compile(r"^(?:M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))$")
GENERIC_FAMILY = {"RE", "REINSURANCE", "CAPITAL", "LTD", "THE", "NEW", "BLUE", "GOLDEN",
                  "EAST", "NORTH", "SOUTH", "WEST", "FIRST", "GLOBAL"}


def program_key(issuer_name: str, source: str) -> str:
    """Normalised issuer key without trailing numerals or a lone year."""
    tokens = normalise_issuer(issuer_name, source).split()
    while tokens and (ROMAN.match(tokens[-1]) or tokens[-1].isdigit()):
        tokens.pop()
    # A program year that survived normalisation, e.g. PIONEER 2002 -> PIONEER.
    tokens = [t for t in tokens if not re.fullmatch(r"(?:19|20)\d{2}", t)]
    return " ".join(tokens)


def family_key(program: str) -> str:
    """First distinctive token, as a weaker fallback for near-miss spellings."""
    tokens = [t for t in program.split() if t not in GENERIC_FAMILY]
    return tokens[0] if tokens and len(tokens[0]) >= 5 else ""


def _month_ordinal_from_text(value) -> int | None:
    """``April 2025`` or ``Apr 2025`` to a month ordinal; anything else is None."""
    parts = str(value).strip().split()
    if len(parts) != 2:
        return None
    return _month_ordinal_from_artemis("%s %s" % (parts[0][:3].title(), parts[1]))


def deal_maturities(deals: pd.DataFrame) -> dict[str, tuple[int, str]]:
    """deal_url -> (maturity month ordinal, field it came from), where stated."""
    out: dict[str, tuple[int, str]] = {}
    for row in deals.to_dict("records"):
        for field in MATURITY_FIELDS:
            month = _month_ordinal_from_text(row.get(field, ""))
            if month is not None:
                out[row["deal_url"]] = (month, field)
                break
    return out


def split_ties(result: pd.DataFrame, securities: pd.DataFrame,
               maturities: dict[str, tuple[int, str]], tolerance: int) -> pd.DataFrame:
    """Resolve ``program_tied`` rows whose tied deals differ in stated maturity."""
    result = result.copy()
    for column in ("trace_maturity_date", "maturity_evidence"):
        if column not in result.columns:
            result[column] = ""
    trace_maturity = securities.set_index("cusip_id").trace_maturity_date
    result["trace_maturity_date"] = result.cusip_id.map(trace_maturity).fillna("")
    for idx in result.index[result.level.eq("program_tied")]:
        row = result.loc[idx]
        month = _month_ordinal_from_date(row.trace_maturity_date)
        urls = [u for u in str(row.tied_deal_urls).split("|") if u]
        if month is None:
            result.loc[idx, "maturity_evidence"] = "TRACE maturity is blank"
            continue
        missing = [u for u in urls if u not in maturities]
        if missing:
            result.loc[idx, "maturity_evidence"] = (
                "%d of %d tied deals state no maturity" % (len(missing), len(urls)))
            continue
        distances = sorted((abs(maturities[u][0] - month), u) for u in urls)
        within = [u for dist, u in distances if dist <= tolerance]
        detail = "; ".join("%s: %d months" % (u.rstrip("/").rsplit("/", 1)[-1], dist)
                           for dist, u in distances)
        if len(within) == 1:
            url = within[0]
            result.loc[idx, ["level", "deal_url", "tied_deal_urls"]] = [
                "program_maturity_split", url, ""]
            result.loc[idx, "maturity_evidence"] = (
                "TRACE maturity %s matches %s only (%s)" % (
                    row.trace_maturity_date, maturities[url][1], detail))
        else:
            result.loc[idx, "maturity_evidence"] = (
                "%d tied deals within %d months (%s)" % (len(within), tolerance, detail))
    return result


def split_by_title(result: pd.DataFrame, title_series: dict[str, str]) -> pd.DataFrame:
    """Resolve ``program_tied`` rows whose holders name exactly one tied deal's series.

    Funds describe positions in Form N-PORT with titles like "Kilimanjaro III
    Re 2019-1 Class A-1". When every title for a CUSIP names the same series
    and exactly one tied deal's directory slug carries it, that deal wins at
    level ``program_nport_title``. Runs before the maturity split because a
    stated series is stronger evidence than a maturity month.
    """
    from resolve_ties_from_nport import normalize_series, series_from_deal_url

    result = result.copy()
    if "title_evidence" not in result.columns:
        result["title_evidence"] = ""
    for idx in result.index[result.level.eq("program_tied")]:
        row = result.loc[idx]
        title = title_series.get(row.cusip_id)
        if not title:
            continue
        urls = [u for u in str(row.tied_deal_urls).split("|") if u]
        matches = [u for u in urls if normalize_series(title) in
                   {normalize_series(s) for s in series_from_deal_url(u)}]
        if len(matches) == 1:
            result.loc[idx, ["level", "deal_url", "tied_deal_urls"]] = [
                "program_nport_title", matches[0], ""]
            result.loc[idx, "title_evidence"] = "nport_title:%s names %s" % (
                title, matches[0].rstrip("/").rsplit("/", 1)[-1])
        elif not matches:
            result.loc[idx, "title_evidence"] = "nport_title:%s names none of the tied deals" % title
        else:
            result.loc[idx, "title_evidence"] = "nport_title:%s names %d tied deals" % (title, len(matches))
    return result


# Where a holder's title stops naming the issuer and starts naming the note:
# class, series, tranche, coupon, registration tags, and the series token.
TITLE_SUFFIX = re.compile(
    r"\s+(?:CLASS\b|CL\b|SERIES\b|SER\b|SR\s*(?:19|20)\d\d|TRANCHE\b|NOTES?\b|REGD\b|144A\b|V/R\b|P/P\b"
    r"|FRN\b|FLT\b|VAR\b|\d+(?:\.\d+)?\s*%|(?:19|20)\d\d\s*-\s*(?:\d|[IVX]+\b))", re.I)


def title_issuer_key(title: str) -> tuple[str, str]:
    """(normalised issuer key, normalised series) a holder's title names.

    "Queen Street 2023 Re DAC" -> ("QUEEN STREET 2023 RE", ""),
    "Kilimanjaro III Re 2019-1 Class A-1" -> ("KILIMANJARO III RE", "2019-1").
    """
    from resolve_ties_from_nport import normalize_series, series_from_title

    text = str(title or "").strip()
    cut = TITLE_SUFFIX.search(text)
    head = text[:cut.start()] if cut else text
    series = normalize_series(series_from_title(text) or extract_series(text))
    return normalise_issuer(head, "trace"), series


def load_title_texts(holdings_path: Path) -> dict[str, list[str]]:
    """CUSIP -> distinct holder titles; {} when there is no holdings file."""
    if holdings_path is None or not Path(holdings_path).exists():
        return {}
    holdings = pd.read_csv(holdings_path, dtype=str, keep_default_na=False, usecols=["cusip", "title"])
    holdings["cusip"] = holdings["cusip"].str.strip().str.upper()
    holdings = holdings[holdings["cusip"].ne("") & holdings["title"].str.strip().ne("")]
    return holdings.groupby("cusip")["title"].agg(lambda s: sorted(set(t.strip() for t in s))).to_dict()


def _slug(url: str) -> str:
    return str(url).rstrip("/").rsplit("/", 1)[-1]


def check_titles(result: pd.DataFrame, index: pd.DataFrame, title_texts: dict[str, list[str]],
                 max_months: int = 3) -> pd.DataFrame:
    """Re-point, resolve, confirm or flag every program row by its holders' titles.

    Each title is resolved to the set of directory deals whose normalised
    issuer key equals the title's, narrowed to the title's series when it
    names one. The titles for a CUSIP agree when the intersection of those
    sets is exactly one deal. A row moves only on agreement plus a TRACE
    issue month within ``max_months`` of the named deal's directory month.
    """
    result = result.copy()
    for column in ("title_evidence", "title_conflict"):
        if column not in result.columns:
            result[column] = ""
    if not title_texts or result.empty:
        return result
    art = index.copy()
    art["key"] = art.issuer_name.map(lambda x: normalise_issuer(x, "artemis"))
    art["series"] = art.issuer_name.map(extract_series)
    from resolve_ties_from_nport import normalize_series
    art["series"] = art["series"].map(normalize_series)
    art["month"] = art.date_text.map(_month_ordinal_from_artemis)
    by_key: dict[str, list[dict]] = defaultdict(list)
    deals_by_url: dict[str, dict] = {}
    for row in art.to_dict("records"):
        deals_by_url[row["deal_url"]] = row
        if row["key"]:
            by_key[row["key"]].append(row)

    for idx in result.index:
        row = result.loc[idx]
        titles = title_texts.get(str(row.cusip_id), [])
        if not titles:
            continue
        sets: list[set[str]] = []
        unresolved: list[str] = []
        for title in titles:
            key, series = title_issuer_key(title)
            deals = by_key.get(key, [])
            if series:
                deals = [d for d in deals if d["series"] == series]
            if not deals:
                unresolved.append("%s%s" % (key or title, " %s" % series if series else ""))
                continue
            sets.append({d["deal_url"] for d in deals})
        note = ""
        conflict = ""
        current = str(row.deal_url)
        tied = [u for u in str(row.tied_deal_urls).split("|") if u]
        if sets:
            agreed = set.intersection(*sets)
        else:
            agreed = set()
        if unresolved and not sets:
            keys = sorted(set(unresolved))
            note = "nport_title names %s, not in directory" % ", ".join("'%s'" % k for k in keys)
            if current:
                conflict = "title_issuer_not_in_directory"
        elif not agreed:
            note = "nport_titles disagree: %s" % " | ".join(titles[:4])
            conflict = "titles_disagree" if current else ""
        elif len(agreed) > 1:
            if current and current not in agreed:
                note = "nport_titles name %d deals, none the attached one" % len(agreed)
                conflict = "title_contradicts_attribution"
            elif current:
                note = "nport_title consistent with %s (%d deals share the name)" % (_slug(current), len(agreed))
        else:
            url = next(iter(agreed))
            deal = deals_by_url[url]
            month = _month_ordinal_from_date(row.trace_issue_date)
            distance = (abs(int(deal["month"]) - int(month))
                        if deal["month"] is not None and month is not None else None)
            within = distance is not None and distance <= max_months
            if url == current:
                note = "nport_title confirms %s" % _slug(url)
            elif within and (row.level in ("program_tied",) and url in tied):
                result.loc[idx, ["level", "deal_url", "tied_deal_urls", "artemis_issuer_name",
                                 "artemis_date_text", "month_distance"]] = [
                    "program_nport_title", url, "", deal["issuer_name"], deal["date_text"], str(distance)]
                note = "nport_title '%s' names %s" % (titles[0], _slug(url))
            elif within:
                was = "%s %s" % (row.level, _slug(current)) if current else row.level
                result.loc[idx, ["level", "deal_url", "tied_deal_urls", "artemis_issuer_name",
                                 "artemis_date_text", "month_distance"]] = [
                    "program_nport_title_repointed", url, "", deal["issuer_name"], deal["date_text"], str(distance)]
                note = ("nport_title '%s' names %s (TRACE issue %s, directory %s); was %s"
                        % (titles[0], _slug(url), row.trace_issue_date, deal["date_text"], was))
            else:
                note = ("nport_title '%s' names %s but its %s is %s months from TRACE issue %s; kept"
                        % (titles[0], _slug(url), deal["date_text"],
                           "?" if distance is None else distance, row.trace_issue_date))
                conflict = "title_names_deal_outside_date_window"
        if unresolved and sets:
            note += "; also unresolved: %s" % ", ".join(sorted(set(unresolved)))
        existing = str(row.title_evidence)
        result.loc[idx, "title_evidence"] = (existing + "; " + note) if existing and note else (note or existing)
        result.loc[idx, "title_conflict"] = conflict
    return result


def attribute(unplaced: pd.DataFrame, index: pd.DataFrame, max_months: int) -> pd.DataFrame:
    art = index.copy()
    art["program"] = art.issuer_name.map(lambda x: program_key(x, "artemis"))
    art["family"] = art.program.map(family_key)
    art["month"] = art.date_text.map(_month_ordinal_from_artemis)
    by_program: dict[str, list] = defaultdict(list)
    by_family: dict[str, list] = defaultdict(list)
    for row in art.to_dict("records"):
        if row["program"]:
            by_program[row["program"]].append(row)
        if row["family"]:
            by_family[row["family"]].append(row)

    rows = []
    for sec in unplaced.itertuples(index=False):
        program = program_key(sec.issuer_nm, "trace")
        family = family_key(program)
        month = _month_ordinal_from_date(sec.trace_issue_date)
        deals, basis = by_program.get(program, []), "program"
        if not deals and family:
            deals, basis = by_family.get(family, []), "family"
        record = {
            "cusip_id": sec.cusip_id, "trace_issuer_nm": sec.issuer_nm,
            "trace_issue_date": sec.trace_issue_date, "program": program,
            "family": family, "match_basis": basis if deals else "",
            "level": "", "deal_url": "", "artemis_issuer_name": "",
            "artemis_date_text": "", "month_distance": "", "program_deals": len(deals),
            "tied_deal_urls": "", "match_confidence": "program",
        }
        if not deals:
            record["level"] = "program_absent"
            rows.append(record)
            continue
        dated = [(abs(int(d["month"]) - int(month)), d) for d in deals
                 if d["month"] is not None and month is not None]
        dated = [(dist, d) for dist, d in dated if dist <= max_months]
        if not dated:
            record["level"] = "program_only"
            rows.append(record)
            continue
        best = min(dist for dist, _ in dated)
        nearest = [d for dist, d in dated if dist == best]
        record["month_distance"] = best
        if len(nearest) == 1:
            deal = nearest[0]
            record.update(level="program_nearest", deal_url=deal["deal_url"],
                          artemis_issuer_name=deal["issuer_name"],
                          artemis_date_text=deal["date_text"])
        else:
            record.update(level="program_tied",
                          tied_deal_urls="|".join(sorted(d["deal_url"] for d in nearest)))
        rows.append(record)
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--trace", type=Path, default=TRACE_PATH)
    parser.add_argument("--bridge", type=Path, default=BRIDGE_PATH)
    parser.add_argument("--screens", type=Path, nargs="*", default=[SCREEN_PATH, SUPPLEMENT_PATH],
                        help="identifier lists whose CUSIPs should be attributed")
    parser.add_argument("--max-months", type=int, default=24)
    parser.add_argument("--deals", type=Path, default=DEALS_PATH,
                        help="parsed deal directory with maturity fields (optional); "
                             "used only to split tied deals by stated maturity")
    parser.add_argument("--maturity-tolerance", type=int, default=1,
                        help="months a TRACE maturity may differ from a stated deal maturity")
    parser.add_argument("--nport-holdings", type=Path,
                        default=ROOT / "data" / "processed" / "nport" / "fund_holdings.csv",
                        help="parsed N-PORT holdings whose titles name series (optional); "
                             "used to split tied deals before the maturity split")
    parser.add_argument("--title-max-months", type=int, default=3,
                        help="months a TRACE issue date may differ from the directory month of a deal "
                             "the holders' titles name before the row is re-pointed to it")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    args = parser.parse_args()

    index = pd.read_csv(args.index, dtype=str)
    bridge = pd.read_csv(args.bridge, dtype=str)
    screen: set[str] = set()
    for path in args.screens:
        if path.exists():
            screen |= {line.strip() for line in path.read_text().splitlines() if line.strip()}
    securities = collapse_trace(pd.read_csv(args.trace, dtype=str, keep_default_na=False))
    unplaced = securities[securities.cusip_id.isin(screen - set(bridge.cusip_id))]
    unplaced = unplaced[unplaced.issuer_nm.fillna("").str.strip().ne("")
                        & ~unplaced.issuer_nm.fillna("").str.upper().str.contains("UNKNOWN ISSUER")]
    result = attribute(unplaced, index, args.max_months)
    title_series: dict[str, str] = {}
    if args.nport_holdings.exists():
        from resolve_ties_from_nport import title_series_map
        title_series = title_series_map(args.nport_holdings)
    result = split_by_title(result, title_series)
    maturities: dict[str, tuple[int, str]] = {}
    if args.deals.exists():
        deals = pd.read_csv(args.deals, dtype=str, low_memory=False)
        maturities = deal_maturities(deals)
    result = split_ties(result, securities, maturities, args.maturity_tolerance)
    title_texts = load_title_texts(args.nport_holdings)
    result = check_titles(result, index, title_texts, args.title_max_months)
    result = result.sort_values(["level", "program", "cusip_id"]).reset_index(drop=True)
    result.to_csv(args.output, index=False)
    summary = {
        "screen_cusips": len(screen), "already_in_bridge": len(screen & set(bridge.cusip_id)),
        "attributed_here": int(len(result)),
        "nameless_skipped": int(len(screen - set(bridge.cusip_id)) - len(result)),
        "by_level": result.level.value_counts().to_dict(),
        "by_basis": result.match_basis.replace("", "none").value_counts().to_dict(),
        "programs_absent": sorted(result.loc[result.level.eq("program_absent"), "program"].unique().tolist()),
        "max_months": args.max_months,
        "nport_title_split": {
            "holdings_source": str(args.nport_holdings) if title_series else "skipped: %s not found" % args.nport_holdings,
            "cusips_with_unanimous_title_series": len(title_series),
            "resolved": int(result.level.eq("program_nport_title").sum()),
            "unresolved_by_reason": (result.loc[result.level.eq("program_tied") & result.title_evidence.ne(""), "title_evidence"]
                                     .str.replace(r"^nport_title:\S+ ", "", regex=True).value_counts().to_dict()),
        },
        "nport_title_check": {
            "cusips_with_titles": int(result.cusip_id.isin(set(title_texts)).sum()),
            "title_max_months": args.title_max_months,
            "repointed": [
                {"cusip_id": r.cusip_id, "deal": _slug(r.deal_url), "evidence": r.title_evidence}
                for r in result[result.level.eq("program_nport_title_repointed")].itertuples()],
            "confirmed": int(result.title_evidence.str.contains("nport_title confirms").sum()),
            "conflicts_by_kind": result.title_conflict.replace("", pd.NA).dropna().value_counts().to_dict(),
        },
        "maturity_split": {
            "deals_source": str(args.deals) if args.deals.exists() else "skipped: %s not found" % args.deals,
            "deals_with_stated_maturity": len(maturities),
            "tolerance_months": args.maturity_tolerance,
            "still_tied_by_reason": (result.loc[result.level.eq("program_tied"), "maturity_evidence"]
                                     .str.replace(r" \(.*\)$", "", regex=True).value_counts().to_dict()),
        },
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.output} ({len(result)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
