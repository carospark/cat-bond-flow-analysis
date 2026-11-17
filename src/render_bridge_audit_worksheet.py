"""Render the bridge audit sample as a local HTML worksheet for the hand check.

The CSV written by ``draw_bridge_audit_sample.py`` carries 27 evidence
columns per pair, which is hard to read row by row. This lays each pair out
as a card: the Artemis side (name, sponsor, size, date, series, a link to the
deal page), the TRACE side (CUSIP, issuer name and variants, description,
debt-type codes, issue and maturity dates, coupon range), and the bridge's
own evidence line by line. A verdict control and a notes box sit on each
card; the page keeps them in the browser's local storage and an "Export CSV"
button writes the sample back out with ``audit_verdict`` and ``audit_notes``
filled, ready for ``score_bridge_audit.py``.

    ./.venv/bin/python src/render_bridge_audit_worksheet.py
    open data/bridge_audit_worksheet.html

The output is gitignored with the sample (it carries Artemis and TRACE
content) and is meant to be opened locally, not published.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = ROOT / "data" / "bridge_audit_sample.csv"
OUT_PATH = ROOT / "data" / "bridge_audit_worksheet.html"
VERDICTS = ("correct", "wrong", "undecidable")

ARTEMIS_FIELDS = [
    ("artemis_issuer_name", "Issuer (deal page)"), ("artemis_sponsor", "Sponsor"),
    ("artemis_size_text", "Size"), ("artemis_date_text", "Date"), ("artemis_series_id", "Series"),
]
TRACE_FIELDS = [
    ("cusip_id", "CUSIP"), ("trace_issuer_nm", "Issuer name"), ("trace_issuer_variants", "Name variants"),
    ("trace_security_description", "Description"), ("trace_debt_type_codes", "Debt-type codes"),
    ("trace_ever_un_cat", "Ever UN-CAT"), ("trace_issue_date", "Issue date"), ("trace_maturity_date", "Maturity"),
    ("trace_coupon_min", "Coupon min"), ("trace_coupon_max", "Coupon max"),
]
EVIDENCE_FIELDS = [
    ("match_confidence", "Confidence"), ("match_method", "Method"), ("title_evidence", "N-PORT title"),
    ("name_evidence", "Name"), ("name_similarity", "Name similarity"), ("series_evidence", "Series"),
    ("date_evidence", "Date"), ("maturity_evidence", "Maturity"), ("coupon_evidence", "Coupon"),
]

STYLE = """
body{font:14px/1.45 -apple-system,Helvetica,Arial,sans-serif;margin:0;background:#f5f5f2;color:#1d1d1b}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:10px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;z-index:2}
header h1{font-size:16px;margin:0}
button{font:inherit;padding:6px 12px;border:1px solid #888;border-radius:6px;background:#fff;cursor:pointer}
#progress{color:#555}
main{max-width:1100px;margin:0 auto;padding:16px}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;margin:0 0 16px;padding:12px 16px}
.card.correct{border-left:6px solid #2e7d32}.card.wrong{border-left:6px solid #c62828}.card.undecidable{border-left:6px solid #ef6c00}
.card h2{font-size:15px;margin:0 0 8px}.card h2 small{font-weight:normal;color:#666;margin-left:8px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:700px){.cols{grid-template-columns:1fr}}
.col h3{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#666;margin:6px 0 4px}
dl{margin:0;display:grid;grid-template-columns:max-content 1fr;gap:2px 10px}
dt{color:#666;white-space:nowrap}dd{margin:0;word-break:break-word}
.evidence dd{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
.verdict{margin-top:10px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.verdict label{cursor:pointer}
textarea{width:100%;box-sizing:border-box;margin-top:6px;font:inherit;min-height:40px}
a{color:#0b57d0}
"""

SCRIPT = """
const KEY='bridge_audit_v1';
let state={};
try{state=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){state={}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(state))}catch(e){}}
function progress(){const n=ROWS.length,d=ROWS.filter(r=>(state[r.sample_id]||{}).verdict).length;
  document.getElementById('progress').textContent=d+' of '+n+' pairs decided';}
function setVerdict(id,v){state[id]=Object.assign(state[id]||{},{verdict:v});save();
  const c=document.getElementById('card-'+id);c.className='card '+v;progress();}
function setNotes(id,t){state[id]=Object.assign(state[id]||{},{notes:t});save();}
function csvCell(s){s=(s==null?'':String(s));return /[",\\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;}
function exportCsv(){const rows=[COLUMNS.join(',')];
  for(const r of ROWS){const st=state[r.sample_id]||{};const copy=Object.assign({},r,{audit_verdict:st.verdict||'',audit_notes:st.notes||''});
    rows.push(COLUMNS.map(c=>csvCell(copy[c])).join(','));}
  const blob=new Blob([rows.join('\\n')+'\\n'],{type:'text/csv'});const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);a.download='bridge_audit_sample.csv';a.click();}
function clearAll(){if(!window.confirm)return;state={};save();location.reload();}
window.addEventListener('DOMContentLoaded',()=>{
  for(const r of ROWS){const st=state[r.sample_id]||{};
    if(st.verdict){document.getElementById('card-'+r.sample_id).className='card '+st.verdict;
      const el=document.querySelector('input[name="v'+r.sample_id+'"][value="'+st.verdict+'"]');if(el)el.checked=true;}
    if(st.notes){document.getElementById('n'+r.sample_id).value=st.notes;}}
  progress();});
"""


def _dl(row: pd.Series, fields: list[tuple[str, str]], cls: str = "") -> str:
    items = []
    for key, label in fields:
        value = html.escape(str(row.get(key, "")))
        items.append(f"<dt>{html.escape(label)}</dt><dd>{value or '&mdash;'}</dd>")
    return f'<dl class="{cls}">' + "".join(items) + "</dl>"


def render_card(row: pd.Series) -> str:
    sid = html.escape(str(row["sample_id"]))
    url = str(row.get("deal_url", ""))
    link = f'<a href="{html.escape(url)}" target="_blank" rel="noopener">Artemis deal page</a>' if url else ""
    radios = "".join(
        f'<label><input type="radio" name="v{sid}" value="{v}" onchange="setVerdict({sid},\'{v}\')"> {v}</label>'
        for v in VERDICTS
    )
    return f"""<section class="card" id="card-{sid}">
<h2>#{sid} {html.escape(str(row.get('artemis_issuer_name', '')))} &harr; {html.escape(str(row.get('cusip_id', '')))}
<small>{html.escape(str(row.get('stratum', '')))}</small></h2>
<div class="cols">
<div class="col"><h3>Artemis</h3>{_dl(row, ARTEMIS_FIELDS)}<p>{link}</p></div>
<div class="col"><h3>TRACE master</h3>{_dl(row, TRACE_FIELDS)}</div>
</div>
<h3>Bridge evidence</h3>{_dl(row, EVIDENCE_FIELDS, 'evidence')}
<div class="verdict"><strong>Verdict:</strong>{radios}</div>
<textarea id="n{sid}" placeholder="Notes (what you checked, what disagreed)" oninput="setNotes({sid},this.value)"></textarea>
</section>"""


def render(sample: pd.DataFrame) -> str:
    columns = list(sample.columns)
    rows_json = json.dumps(sample.astype(str).to_dict(orient="records"))
    cards = "\n".join(render_card(row) for _, row in sample.iterrows())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bridge audit worksheet</title><style>{STYLE}</style>
<script>const COLUMNS={json.dumps(columns)};const ROWS={rows_json};{SCRIPT}</script></head>
<body><header><h1>Bridge audit: {len(sample)} pairs</h1><span id="progress"></span>
<button onclick="exportCsv()">Export CSV</button></header>
<main>
<p>For each pair decide whether the TRACE CUSIP is a note of the Artemis deal (same issuer entity <em>and</em> the same series or issuance, not a sibling series from the same programme).
Mark <b>correct</b>, <b>wrong</b>, or <b>undecidable</b> when the pages do not settle it. Verdicts stay in this browser; export the CSV when done and save it over <code>data/bridge_audit_sample.csv</code>.</p>
{cards}
</main></body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sample", type=Path, default=SAMPLE_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    sample = pd.read_csv(args.sample, dtype=str, keep_default_na=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(sample), encoding="utf-8")
    print("wrote %s: %d pairs" % (args.out, len(sample)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
