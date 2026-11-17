"""Build the coverage-aware market atlas tables (Phase 2 groundwork).

The atlas describes the market by segment, peril, trigger, sponsor type,
layer (attachment-probability band) and year from the parsed tables, and
adds the principal roll-forward by segment, fund-by-fund net subscriptions
by month, and the mark-versus-trade gap by quarter from the joins. Every
table carries the count behind each number and the share of the universe
it was computed from, so a chart can show its coverage beside it. Nothing
here tests a hypothesis.

    ./.venv/bin/python src/build_atlas.py
    ./.venv/bin/python src/build_atlas.py --parser-root /path/to/cat-bond-issuance

Inputs (all local, gitignored):
  parser   data/deals.csv, data/tranches.csv, data/losses.csv, src/roll_forward.py
  here     src/build_deal_panel.py (peril lexicon), data/processed/nport/fund_flows.csv,
           data/fund_marks_vs_trace.csv, config/fund_registry.json

Outputs under data/atlas/:
  universe_deals.csv        one row per deal with its segment, sponsor type, issue year, USD size
  universe_by_year.csv      deals and issued USD by segment and year
  peril_by_year.csv         core-segment deals by hazard class and year (multi-class deals split),
                            mapped from the peril text with the panel builder's lexicon
  trigger_by_year.csv       deals and issued USD by trigger type and year
  sponsor_type_by_year.csv  deals and issued USD by sponsor type and year
  layer_by_year.csv         tranches by attachment-probability band and year: spread, EL, size
  outstanding_by_segment.csv  roll-forward closing stock per year by segment
  fund_flows_by_month.csv   net subscriptions per fund lineage per month, event windows marked
  marks_by_quarter.csv      fund mark versus TRACE gap distribution per quarter
  comparators_by_year.csv   the published annual comparators in their own units: Guy Carpenter
                            rate-on-line index, Lane weighted premium and expected loss, Aon issuance
  summary.json              coverage counts for every table

Universe rule (segments are exclusive, applied in this order): mortgage
(peril names mortgage insurance, or the issuer is a known mortgage ILS
programme); life_health (mortality, longevity, medical, health, pandemic);
cyber; other_specialty (terror, lottery, aviation, marine, energy, crop,
agriculture, liability, workers, operational, satellite); private_lite
(the directory marks the deal private); core_property_cat (everything
else, including "unknown property catastrophe risks"). Mortgage, life and
lite are reported, never folded into the core.

Layer bands are on the tranche's attachment probability in percent:
below 1, 1 to 2, 2 to 4, 4 to 8, 8 and above. Spread is the parsed
risk-margin spread; the price-guidance midpoint is reported beside it with
its own count. Size weights use the final tranche size in USD where it is
stated in dollars; non-USD tranche sizes are counted but not weighted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_deal_panel import map_perils  # noqa: E402  (the panel builder's peril lexicon)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_DIR = DATA / "atlas"
PARSER_ROOT = ROOT.parent / "cat-bond-issuance"
FUND_FLOWS_PATH = DATA / "processed" / "nport" / "fund_flows.csv"
MARKS_PATH = DATA / "fund_marks_vs_trace.csv"
REFERENCE_DIR = DATA / "processed" / "reference_series"
REGISTRY_PATH = ROOT / "config" / "fund_registry.json"

SEGMENTS = ["core_property_cat", "private_lite", "mortgage", "life_health", "cyber", "other_specialty"]
MORTGAGE_RE = re.compile(
    r"bellemeade|oaktown|eagle re|radnor|home re|triangle re|cherry blossom|greystone|sierra ltd|splitrock",
    re.IGNORECASE)
CORE_PERIL_RE = re.compile(
    r"hurricane|named storm|storm|earthquake|quake|wind|typhoon|cyclone|flood|wildfire|fire|property|"
    r"catastrophe|hail|tornado|convective|winter|volcan|tsunami|meteorite|peril", re.I)
PERIL_RULES = [
    ("mortgage", re.compile(r"mortgage", re.I)),
    ("life_health", re.compile(r"mortality|longevity|medical|health|pandemic|life insurance|lapse", re.I)),
    ("cyber", re.compile(r"\bcyber", re.I)),
    ("other_specialty", re.compile(
        r"terror|lottery|aviation|marine|energy|crop|agricultur|liability|workers|operational|satellite|space|"
        r"motor|auto physical|shipping|trade credit", re.I)),
]
SPONSOR_RULES = [
    ("public_sector", re.compile(
        r"citizens|authority|government|republic|ministry|state of|kingdom|world bank|ibrd|fema|nfip|tcip|ccrif|"
        r"pacific alliance|federal|commonwealth|county|city of|\bmta\b|department of|water & power|fonden|agroasemex|"
        r"transportation|zenkyoren|caisse|consorcio|earthquake commission|\beqc\b|texas windstorm|twia|"
        r"north carolina|louisiana|florida hurricane|\bcea\b|cal(?:ifornia)? earthquake|jamaica|mexico|chile|"
        r"philippines|peru|colombia|new zealand|agency|municipal|hong kong|hkmc|turkish|underwriting association|"
        r"\bjua\b|\biua\b|fair plan|windstorm", re.I)),
    ("reinsurer", re.compile(
        r"\bre\b|reinsurance|reinsurer|\bscor\b|swiss re|munich re|hannover|everest|renaissance|partner re|"
        r"arch capital|axis|aspen|validus|markel|sirius|transre|odyssey|lloyd|syndicate|toa re|korean re|"
        r"pxre|converium|gerling|centre solutions|"
        r"peak re|catlin|ace\b|chubb tempest|platinum|flagstone|montpelier|endurance|axa xl|xl\b", re.I)),
    ("insurer", re.compile(
        r"insurance|assurance|mutual|usaa|allstate|state farm|farmers|nationwide|liberty|travelers|chubb|"
        r"aig|american international|hartford|safeco|zurich|allianz|axa\b|generali|tokio|sompo|mitsui|"
        r"aioi|nissay|heritage|universal|american strategic|united property|frontline|american coastal|"
        r"homeowners choice|hci|security first|avatar|safepoint|slide|kin\b|lemonade|hippo|root\b|aetna|"
        r"cigna|health|amerisure|cincinnati|erie|auto club|csaa|interinsurance|exchange|group\b|assicurazioni|"
        r"guaranty|mgic|radian|essent|arch mortgage|groupama|beazley|hiscox|amlin|assurant|sorema|covea|"
        r"mapfre|unipol|achmea|ageas|aviva|direct line|admiral|\bnmi\b|enact|fidelis|convex|ark\b|"
        r"lancashire|kemper|progressive|geico|mercury|palomar|kingstone|florida peninsula|first protective|"
        r"chartis|amtrust|vantage risk|core specialty|\bcna\b|\bagf\b|yasuda|fm global|andover|"
        r"people's trust|tower hill|castle key|texas farm|louisiana farm|bankers|elements|fednat|ark re", re.I)),
]
EVENT_WINDOWS = {
    "ian": ("2022-08", "2022-11"),
    "milton": ("2024-09", "2024-12"),
}
AP_BANDS = [(0.0, 1.0, "ap_lt_1"), (1.0, 2.0, "ap_1_2"), (2.0, 4.0, "ap_2_4"), (4.0, 8.0, "ap_4_8"), (8.0, float("inf"), "ap_8_plus")]


# ---------------------------------------------------------------- helpers

def pct_to_float(text) -> float | None:
    """'1.21%' -> 1.21; '' -> None. Takes the first number in a range."""
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", str(text or ""))
    return float(m.group(1)) if m else None


def guidance_mid(text) -> float | None:
    """'9.75% to 10.5%' -> 10.125; a single figure stands alone."""
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", str(text or ""))]
    if not nums:
        return None
    return sum(nums[:2]) / min(len(nums), 2)


def usd_millions(size_text) -> tuple[float | None, str]:
    """Size cell -> (USD millions, basis). Mirrors the parser's rule: a
    parenthetical USD equivalent wins, a dollar figure is taken as is, a
    non-USD figure is counted but not converted."""
    s = str(size_text or "").strip()
    if not s or s.lower() in ("not issued", "unknown", "?", "tbc", "n/a"):
        return None, "missing"
    par = re.search(r"\(\s*(?:US)?\$\s*([\d,.]+)\s*(m|mn|million|bn|billion)?\s*\)", s, re.I)
    if par:
        return _to_millions(par.group(1), par.group(2)), "usd_equiv"
    m = re.match(r"^(?:US)?\$\s*([\d,.]+)\s*(m|mn|million|bn|billion)?\b", s, re.I)
    if m:
        if not m.group(2):
            return None, "unit_missing"
        return _to_millions(m.group(1), m.group(2)), "usd"
    return None, "non_usd_unconverted"


def _to_millions(number: str, unit: str | None) -> float | None:
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    unit = (unit or "m").lower()
    return value * 1000 if unit in ("bn", "billion") else value


def issue_year(date_text) -> int | None:
    m = re.search(r"((?:19|20)\d{2})", str(date_text or ""))
    return int(m.group(1)) if m else None


def classify_segment(perils: str, issuer_name: str, is_private: str) -> tuple[str, bool]:
    """(segment, mixed). A deal whose perils name both a specialty line and a
    property-catastrophe peril ("U.S. hurricane, UK extreme mortality") stays
    in the core with `mixed` set; mortgage always wins."""
    text = str(perils or "")
    if MORTGAGE_RE.search(str(issuer_name or "")) or PERIL_RULES[0][1].search(text):
        return "mortgage", False
    core = bool(CORE_PERIL_RE.search(text))
    for label, rule in PERIL_RULES[1:]:
        if rule.search(text):
            if core:
                return ("private_lite" if str(is_private).strip().lower() == "true" else "core_property_cat"), True
            return label, False
    if str(is_private).strip().lower() == "true":
        return "private_lite", False
    return "core_property_cat", False


def classify_sponsor(sponsor: str) -> str:
    text = str(sponsor or "").strip()
    if not text:
        return "unknown"
    for label, rule in SPONSOR_RULES:
        if rule.search(text):
            return label
    return "corporate_other"


def ap_band(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "ap_unknown"
    for lo, hi, label in AP_BANDS:
        if lo <= value < hi:
            return label
    return "ap_unknown"


def lineage_of(fund_id: str, registry: dict) -> str:
    """Collapse predecessor and successor funds to one lineage id (the successor's)."""
    entries = {e["id"]: e for e in registry.get("sec_registered", [])}
    seen = set()
    current = fund_id
    while current in entries and entries[current].get("successor_id") and current not in seen:
        seen.add(current)
        current = entries[current]["successor_id"]
    return current


# ---------------------------------------------------------------- tables

def universe_table(deals: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "deal_slug": deals["deal_slug"],
        "deal_url": deals["deal_url"],
        "deal_name": deals["deal_name"],
        "issue_year": deals["date_of_issue"].map(issue_year),
        "segment": [classify_segment(p, n, pr)[0] for p, n, pr in
                    zip(deals["perils_covered"], deals["deal_name"], deals["deal_is_private"])],
        "mixed_peril": [classify_segment(p, n, pr)[1] for p, n, pr in
                        zip(deals["perils_covered"], deals["deal_name"], deals["deal_is_private"])],
        "sponsor": deals["cedent_sponsor"],
        "sponsor_type": deals["cedent_sponsor"].map(classify_sponsor),
        "trigger_type": deals["trigger_type"].replace("", "unknown"),
        "perils_covered": deals["perils_covered"],
        "deal_status": deals["deal_status"],
    })
    sizes = deals["size"].map(usd_millions)
    out["size_usd_m"] = [s[0] for s in sizes]
    out["size_basis"] = [s[1] for s in sizes]
    return out


def _by_year(universe: pd.DataFrame, key: str) -> pd.DataFrame:
    frame = universe[universe["issue_year"].notna()].copy()
    frame["issue_year"] = frame["issue_year"].astype(int)
    frame["sized"] = frame["size_usd_m"].notna()
    g = frame.groupby(["issue_year", key])
    out = g.agg(deals=("deal_slug", "size"), deals_sized=("sized", "sum"),
                issued_usd_m=("size_usd_m", "sum")).reset_index()
    totals = frame.groupby("issue_year").agg(year_deals=("deal_slug", "size"),
                                             year_issued_usd_m=("size_usd_m", "sum")).reset_index()
    out = out.merge(totals, on="issue_year")
    out["share_of_year_deals"] = (out["deals"] / out["year_deals"]).round(4)
    out["share_of_year_usd"] = (out["issued_usd_m"] / out["year_issued_usd_m"]).round(4)
    out["issued_usd_m"] = out["issued_usd_m"].round(1)
    return out


def hazard_classes(perils: str) -> list[str]:
    """Distinct hazard classes named by a deal's peril text, in lexicon order."""
    out = []
    for hazard, _region in map_perils(str(perils or "")):
        if hazard not in out:
            out.append(hazard)
    return out


def peril_table(universe: pd.DataFrame, mapper=hazard_classes) -> pd.DataFrame:
    """Core-segment deals by hazard class and year. A deal mapped to k classes
    counts once in each class and its size is split k ways; `deals_multi`
    says how many of a cell's deals were split. Peril text the lexicon does
    not recognise ("Unknown property catastrophe risks") is `unmapped`."""
    core = universe[universe["segment"].eq("core_property_cat") & universe["issue_year"].notna()].copy()
    core["issue_year"] = core["issue_year"].astype(int)
    core["hazard_class"] = core["perils_covered"].map(lambda t: mapper(t) or ["unmapped"])
    core["classes"] = core["hazard_class"].map(len)
    rows = core.explode("hazard_class")
    rows["size_split_usd_m"] = rows["size_usd_m"] / rows["classes"]
    rows["multi"] = rows["classes"] > 1
    g = rows.groupby(["issue_year", "hazard_class"])
    out = g.agg(deals=("deal_slug", "size"), deals_multi=("multi", "sum"),
                deals_sized=("size_usd_m", lambda s: int(s.notna().sum())),
                issued_usd_m_split=("size_split_usd_m", "sum")).reset_index()
    totals = core.groupby("issue_year").agg(year_core_deals=("deal_slug", "size")).reset_index()
    out = out.merge(totals, on="issue_year")
    out["issued_usd_m_split"] = out["issued_usd_m_split"].round(1)
    return out


def layer_table(tranches: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    t = tranches.copy()
    seg = universe.set_index("deal_slug")["segment"]
    t["segment"] = t["deal_slug"].map(seg).fillna("unknown")
    t["issue_year"] = t["date_text"].map(issue_year)
    t["ap"] = t["attachment_probability"].map(pct_to_float)
    t["el"] = t["expected_loss"].map(pct_to_float)
    t["spread"] = t["spread_risk_margin"].map(pct_to_float)
    t["guidance_mid"] = t["price_guidance"].map(guidance_mid)
    sizes = t["tranche_size_final"].map(usd_millions)
    t["size_usd_m"] = [s[0] for s in sizes]
    t["band"] = t["ap"].map(ap_band)
    t = t[t["issue_year"].notna()].copy()
    t["issue_year"] = t["issue_year"].astype(int)
    t["spread_x_size"] = t["spread"] * t["size_usd_m"]
    t["size_if_spread"] = t["size_usd_m"].where(t["spread"].notna())
    g = t.groupby(["segment", "issue_year", "band"])
    out = g.agg(
        tranches=("tranche_id", "size"),
        n_ap=("ap", "count"), n_el=("el", "count"), n_spread=("spread", "count"),
        n_guidance=("guidance_mid", "count"), n_sized_usd=("size_usd_m", "count"),
        median_ap=("ap", "median"), median_el=("el", "median"),
        median_spread=("spread", "median"), median_guidance_mid=("guidance_mid", "median"),
        issued_usd_m=("size_usd_m", "sum"),
        spread_x_size=("spread_x_size", "sum"), size_if_spread=("size_if_spread", "sum"),
    ).reset_index()
    out["size_weighted_spread"] = (out["spread_x_size"] / out["size_if_spread"]).where(out["size_if_spread"] > 0)
    out = out.drop(columns=["spread_x_size", "size_if_spread"])
    year_totals = t.groupby(["segment", "issue_year"]).agg(year_tranches=("tranche_id", "size"),
                                                           year_tranches_with_ap=("ap", "count")).reset_index()
    out = out.merge(year_totals, on=["segment", "issue_year"])
    for col in ("median_ap", "median_el", "median_spread", "median_guidance_mid", "size_weighted_spread"):
        out[col] = out[col].round(3)
    out["issued_usd_m"] = out["issued_usd_m"].round(1)
    return out


def outstanding_by_segment(book: pd.DataFrame, universe: pd.DataFrame, rf) -> pd.DataFrame:
    seg = universe.set_index("deal_slug")["segment"]
    work = book.copy()
    work["segment"] = work["slug"].map(seg).fillna("unknown")
    pieces = []
    for segment, part in work.groupby("segment"):
        flows = rf.monthly_flows(part)
        stock = rf.outstanding_by_year(flows)
        stock = stock.assign(segment=segment, deals=len(part))
        pieces.append(stock)
    out = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    return out


def fund_flows_table(flows: pd.DataFrame, registry: dict) -> pd.DataFrame:
    f = flows.copy()
    f["lineage"] = f["fund_id"].map(lambda x: lineage_of(x, registry))
    f["month"] = f["month_end"].str[:7]
    f["net_flow"] = pd.to_numeric(f["net_flow"], errors="coerce")
    f["net_assets"] = pd.to_numeric(f["net_assets_at_period_end"], errors="coerce")
    f["null_flow"] = f["net_flow"].isna()
    g = f.groupby(["lineage", "month"])
    out = g.agg(funds=("fund_id", "nunique"), net_flow_usd=("net_flow", "sum"),
                months_null=("null_flow", "sum"), basis=("net_flow_basis", lambda s: "|".join(sorted(set(s)))),
                net_assets_usd=("net_assets", "max")).reset_index()
    out.loc[out["months_null"] > 0, "net_flow_usd"] = pd.NA
    out["event_window"] = ""
    for name, (lo, hi) in EVENT_WINDOWS.items():
        out.loc[(out["month"] >= lo) & (out["month"] <= hi), "event_window"] = name
    return out.sort_values(["lineage", "month"]).reset_index(drop=True)


def marks_table(marks: pd.DataFrame) -> pd.DataFrame:
    m = marks.copy()
    m["diff"] = pd.to_numeric(m["diff_points_both"], errors="coerce")
    m["abs_diff"] = m["diff"].abs()
    m["stale_flag"] = m["stale"].astype(str).str.lower().isin(("true", "1"))
    m["quarter"] = m["period_end"].str[:7]
    g = m.groupby("quarter")
    out = g.agg(pairs=("cusip", "size"), pairs_with_trace=("diff", "count"),
                median_gap=("diff", "median"), median_abs_gap=("abs_diff", "median"),
                p90_abs_gap=("abs_diff", lambda s: s.quantile(0.9)),
                share_stale=("stale_flag", "mean"),
                share_abs_gap_over_5=("abs_diff", lambda s: (s > 5).mean())).reset_index()
    for col in ("median_gap", "median_abs_gap", "p90_abs_gap", "share_stale", "share_abs_gap_over_5"):
        out[col] = out[col].round(3)
    return out


def comparators_table(reference_dir: Path) -> pd.DataFrame:
    """The published annual series extracted under data/processed/reference_series,
    merged on year, each column named for its source and unit. They are
    comparators in their own units, never joined to the parsed tables."""
    frames = []
    rol = reference_dir / "guy_carpenter_global_property_cat_rol_index.csv"
    if rol.exists():
        r = pd.read_csv(rol)
        frames.append(r[["year", "rol_index", "digitization_uncertainty_index_points"]].rename(
            columns={"rol_index": "gc_rol_index_2000_eq_100", "digitization_uncertainty_index_points": "gc_rol_uncertainty_points"}))
    lane = reference_dir / "lane_annual_nat_cat_ils_pricing.csv"
    if lane.exists():
        l = pd.read_csv(lane)
        frames.append(l[["year", "weighted_premium_pct", "wsst_el_pct", "annual_limit_issued_usd_mn", "tranches"]].rename(
            columns={"weighted_premium_pct": "lane_weighted_premium_pct", "wsst_el_pct": "lane_weighted_el_pct",
                     "annual_limit_issued_usd_mn": "lane_limit_issued_usd_m", "tranches": "lane_tranches"}))
    aon = reference_dir / "aon_property_cat_bond_annual_issuance.csv"
    if aon.exists():
        a = pd.read_csv(aon)
        frames.append(a[["year", "issuance_usd_mn"]].rename(columns={"issuance_usd_mn": "aon_property_cat_issuance_usd_m"}))
    if not frames:
        return pd.DataFrame(columns=["year"])
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on="year", how="outer")
    return out.sort_values("year").reset_index(drop=True)


# ---------------------------------------------------------------- build

def load_parser_rollforward(parser_root: Path):
    src = parser_root / "src"
    if not (src / "roll_forward.py").exists():
        return None
    sys.path.insert(0, str(src))
    import roll_forward  # noqa: E402
    return roll_forward


def build(parser_root: Path = PARSER_ROOT, out_dir: Path = OUT_DIR) -> dict:
    deals = pd.read_csv(parser_root / "data" / "deals.csv", dtype=str, keep_default_na=False)
    tranches = pd.read_csv(parser_root / "data" / "tranches.csv", dtype=str, keep_default_na=False)
    registry = json.loads(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
    out_dir.mkdir(parents=True, exist_ok=True)

    universe = universe_table(deals)
    universe["hazard_classes"] = universe["perils_covered"].map(lambda t: "|".join(hazard_classes(t)))
    universe.to_csv(out_dir / "universe_deals.csv", index=False)
    by_segment = _by_year(universe, "segment")
    by_segment.to_csv(out_dir / "universe_by_year.csv", index=False)
    peril = peril_table(universe)
    peril.to_csv(out_dir / "peril_by_year.csv", index=False)
    _by_year(universe, "trigger_type").to_csv(out_dir / "trigger_by_year.csv", index=False)
    _by_year(universe, "sponsor_type").to_csv(out_dir / "sponsor_type_by_year.csv", index=False)
    layers = layer_table(tranches, universe)
    layers.to_csv(out_dir / "layer_by_year.csv", index=False)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parser_root": str(parser_root),
        "universe": {
            "deals": int(len(universe)),
            "by_segment": universe["segment"].value_counts().to_dict(),
            "issued_usd_m_by_segment": universe.groupby("segment")["size_usd_m"].sum().round(1).to_dict(),
            "deals_without_usd_size": int(universe["size_usd_m"].isna().sum()),
            "size_basis": universe["size_basis"].value_counts().to_dict(),
            "deals_without_issue_year": int(universe["issue_year"].isna().sum()),
            "sponsor_type": universe["sponsor_type"].value_counts().to_dict(),
            "trigger_type": universe["trigger_type"].value_counts().to_dict(),
        },
        "peril": {
            "core_deals": int(universe["segment"].eq("core_property_cat").sum()),
            "core_deals_mapped": int((universe["segment"].eq("core_property_cat") & universe["hazard_classes"].ne("")).sum()),
            "core_deals_in_several_classes": int((universe["segment"].eq("core_property_cat") & universe["hazard_classes"].str.contains(r"\|")).sum()),
            "core_deals_unmapped": int(peril.loc[peril["hazard_class"].eq("unmapped"), "deals"].sum()) if not peril.empty else 0,
            "core_deals_mixed_peril": int((universe["segment"].eq("core_property_cat") & universe["mixed_peril"]).sum()),
        },
        "layers": {
            "tranches": int(len(tranches)),
            "tranches_with_attachment_probability": int(tranches["attachment_probability"].map(pct_to_float).notna().sum()),
            "tranches_with_expected_loss": int(tranches["expected_loss"].map(pct_to_float).notna().sum()),
            "tranches_with_spread": int(tranches["spread_risk_margin"].map(pct_to_float).notna().sum()),
            "tranches_with_guidance": int(tranches["price_guidance"].map(guidance_mid).notna().sum()),
            "band_counts": layers.groupby("band")["tranches"].sum().to_dict() if not layers.empty else {},
        },
    }

    rf = load_parser_rollforward(parser_root)
    if rf is not None:
        book = None
        try:
            book, _, _ = rf.build(exclude_mortgage=False)
            book_note = "full book including mortgage ILS"
        except Exception as exc:  # the parser's ledger has only ever run ex-mortgage
            book_note = "parser roll-forward failed on the full book (%s: %s)" % (type(exc).__name__, exc)
            try:
                book, _, _ = rf.build(exclude_mortgage=True)
                book_note = "mortgage ILS excluded: " + book_note
            except Exception as exc2:
                book_note += "; and on the ex-mortgage book (%s: %s)" % (type(exc2).__name__, exc2)
    if rf is not None and book is not None:
        stock = outstanding_by_segment(book, universe, rf)
        stock.to_csv(out_dir / "outstanding_by_segment.csv", index=False)
        latest = stock[stock["year"].eq(stock["year"].max())] if not stock.empty else stock
        summary["outstanding"] = {
            "book": book_note,
            "book_deals": int(len(book)),
            "book_deals_unknown_segment": int(book["slug"].map(universe.set_index("deal_slug")["segment"]).isna().sum()),
            "latest_year": int(stock["year"].max()) if not stock.empty else None,
            "latest_outstanding_usd_m_by_segment": {r.segment: round(float(r.outstanding), 1) for r in latest.itertuples()},
            "trace_maturities": book.attrs.get("trace_path"),
        }
    elif rf is None:
        summary["outstanding"] = {"skipped": "parser roll_forward.py not found under %s" % parser_root}
    else:
        summary["outstanding"] = {"skipped": book_note}

    if FUND_FLOWS_PATH.exists():
        flows = pd.read_csv(FUND_FLOWS_PATH, dtype=str, keep_default_na=False)
        ff = fund_flows_table(flows, registry)
        ff.to_csv(out_dir / "fund_flows_by_month.csv", index=False)
        summary["fund_flows"] = {
            "lineages": int(ff["lineage"].nunique()),
            "lineage_months": int(len(ff)),
            "months_with_null_flow": int(ff["net_flow_usd"].isna().sum()),
            "window": [ff["month"].min(), ff["month"].max()] if not ff.empty else None,
            "net_flow_usd_total_by_lineage": ff.groupby("lineage")["net_flow_usd"].sum(min_count=1).round(0).to_dict(),
        }
    else:
        summary["fund_flows"] = {"skipped": "no fund_flows.csv"}

    if MARKS_PATH.exists():
        marks = pd.read_csv(MARKS_PATH, dtype=str, keep_default_na=False)
        mt = marks_table(marks)
        mt.to_csv(out_dir / "marks_by_quarter.csv", index=False)
        summary["marks"] = {"quarters": int(len(mt)), "pairs": int(mt["pairs"].sum()),
                            "pairs_with_trace": int(mt["pairs_with_trace"].sum())}
    else:
        summary["marks"] = {"skipped": "no fund_marks_vs_trace.csv"}

    comparators = comparators_table(REFERENCE_DIR)
    comparators.to_csv(out_dir / "comparators_by_year.csv", index=False)
    summary["comparators"] = {c: int(comparators[c].notna().sum()) for c in comparators.columns if c != "year"}

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--parser-root", type=Path, default=PARSER_ROOT)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    summary = build(args.parser_root, args.out_dir)
    print(json.dumps(summary["universe"]["by_segment"], indent=2))
    print("wrote %s" % args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
