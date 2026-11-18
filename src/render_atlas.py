"""Render the atlas tables as one local HTML page with coverage beside every chart.

    ./.venv/bin/python src/render_atlas.py
    open data/atlas/atlas.html

Reads the CSVs that ``build_atlas.py`` wrote under data/atlas/ and writes
``data/atlas/atlas.html`` (gitignored with the rest of data/). The page is
self-contained: inline SVG, no external scripts, light and dark themes, a
tooltip on every mark, and a table view under every chart so no number is
reachable only by hovering. Every figure states what it was computed from:
the deals or tranches behind it, how many had the field, and what was left
out. Nothing here is a hypothesis test.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ATLAS_DIR = ROOT / "data" / "atlas"
OUT_PATH = ATLAS_DIR / "atlas.html"

SEGMENT_ORDER = ["core_property_cat", "private_lite", "mortgage", "life_health", "cyber", "other_specialty"]
SEGMENT_LABELS = {"core_property_cat": "Core property cat", "private_lite": "Private / lite", "mortgage": "Mortgage ILS",
                  "life_health": "Life and health", "cyber": "Cyber", "other_specialty": "Other specialty"}
SPONSOR_ORDER = ["insurer", "reinsurer", "public_sector", "corporate_other", "undisclosed", "unknown"]
TRIGGER_ORDER = ["Indemnity", "Industry loss index", "Parametric", "Parametric index", "Modelled loss", "unknown"]
BAND_ORDER = ["ap_lt_1", "ap_1_2", "ap_2_4", "ap_4_8", "ap_8_plus", "ap_unknown"]
EL_BAND_ORDER = [b.replace("ap_", "el_", 1) for b in BAND_ORDER]
EL_BAND_LABELS = {"el_lt_1": "Expected loss below 1%", "el_1_2": "1% to 2%", "el_2_4": "2% to 4%",
                  "el_4_8": "4% to 8%", "el_8_plus": "8% and above", "el_unknown": "Expected loss not stated"}
BAND_LABELS = {"ap_lt_1": "Attachment probability below 1%", "ap_1_2": "1% to 2%", "ap_2_4": "2% to 4%",
               "ap_4_8": "4% to 8%", "ap_8_plus": "8% and above", "ap_unknown": "Attachment probability not stated"}
MAX_SERIES = 8

STYLE = """
:root{color-scheme:light;--surface:#fcfcfb;--card:#ffffff;--text:#0b0b0b;--text-2:#52514e;--muted:#8a8984;--grid:#e6e5e1;--line:#d9d8d3;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948;--pos:#2a78d6;--neg:#e34948;--window:rgba(235,104,52,.12)}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#1a1a19;--card:#232322;--text:#f0efec;--text-2:#c3c2b7;--muted:#8d8c86;--grid:#33332f;--line:#3d3d39;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;--pos:#3987e5;--neg:#e66767;--window:rgba(217,89,38,.18)}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--card:#232322;--text:#f0efec;--text-2:#c3c2b7;--muted:#8d8c86;--grid:#33332f;--line:#3d3d39;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;--pos:#3987e5;--neg:#e66767;--window:rgba(217,89,38,.18)}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--text);font:14px/1.45 -apple-system,Helvetica,Arial,sans-serif}
header{padding:20px 16px 8px;max-width:1100px;margin:0 auto}header h1{font-size:20px;margin:0 0 4px}header p{color:var(--text-2);margin:4px 0}
.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:8px 0}
button{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer}
main{max-width:1100px;margin:0 auto;padding:0 16px 40px}
.fig{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin:0 0 18px}
.fig h2{font-size:15px;margin:0 0 2px}.fig .sub{color:var(--text-2);margin:0 0 8px;font-size:13px}
.fig .coverage{color:var(--text-2);font-size:12.5px;margin:6px 0 0;padding:6px 10px;border-left:3px solid var(--line)}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin:6px 0;font-size:12.5px;color:var(--text-2)}
.legend span{display:inline-flex;align-items:center;gap:6px}.legend i{display:inline-block;width:12px;height:12px;border-radius:2px}
.legend i.line{height:2px;width:16px;border-radius:0}
svg{display:block;width:100%;height:auto;overflow:visible}
.grid line{stroke:var(--grid);stroke-width:1}.axis text{fill:var(--text-2);font-size:11px}.axis line,.axis path{stroke:var(--line)}
.bar{stroke:var(--card);stroke-width:2;shape-rendering:crispEdges}.bar:hover{filter:brightness(1.12)}
.series-line{fill:none;stroke-width:2}.dot{stroke:var(--card);stroke-width:2}
.hit{fill:transparent}.crosshair{stroke:var(--text-2);stroke-width:1;stroke-dasharray:3 3;display:none}
.tip{position:fixed;pointer-events:none;background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 10px;font-size:12.5px;box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;z-index:9;max-width:320px}
.tip b{font-size:13px}.tip .row{display:flex;gap:8px;align-items:center}.tip .row i{display:inline-block;width:12px;height:2px}
details summary{cursor:pointer;color:var(--text-2);font-size:12.5px;margin-top:6px}
table{border-collapse:collapse;font-size:12px;margin-top:6px;width:100%}th,td{border-bottom:1px solid var(--grid);padding:3px 6px;text-align:right}th:first-child,td:first-child{text-align:left}
.multi{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.multi .fig{margin:0}
@media(max-width:600px){header,main{padding-left:16px;padding-right:16px}}
"""

SCRIPT = r"""
const S=['--s1','--s2','--s3','--s4','--s5','--s6','--s7','--s8'];
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const tip=document.createElement('div');tip.className='tip';document.body.appendChild(tip);
function showTip(e,title,rows){tip.replaceChildren();const b=document.createElement('b');b.textContent=title;tip.appendChild(b);
  for(const r of rows){const d=document.createElement('div');d.className='row';if(r.color){const i=document.createElement('i');i.style.background=r.color;d.appendChild(i);}
    const v=document.createElement('strong');v.textContent=r.value;d.appendChild(v);const l=document.createElement('span');l.textContent=r.label;d.appendChild(l);tip.appendChild(d);}
  tip.style.display='block';moveTip(e);}
function moveTip(e){const w=tip.offsetWidth,h=tip.offsetHeight;let x=e.clientX+14,y=e.clientY+14;if(x+w>innerWidth-8)x=e.clientX-w-14;if(y+h>innerHeight-8)y=e.clientY-h-14;tip.style.left=x+'px';tip.style.top=y+'px';}
function hideTip(){tip.style.display='none';}
const fmt=(v,d)=>v==null||Number.isNaN(v)?'n/a':Number(v).toLocaleString(undefined,{maximumFractionDigits:d==null?0:d});
const NS='http://www.w3.org/2000/svg';
function el(t,a,parent){const n=document.createElementNS(NS,t);for(const k in a)n.setAttribute(k,a[k]);if(parent)parent.appendChild(n);return n;}
function niceMax(v){if(v<=0)return 1;const p=Math.pow(10,Math.floor(Math.log10(v)));const m=v/p;const n=m<=1?1:m<=2?2:m<=2.5?2.5:m<=5?5:10;return n*p;}

/* stacked bars: data=[{x, values:{key:number}, meta:{...}}], keys in fixed order */
function stackedBars(host,data,keys,labels,opts){
  const W=960,H=300,M={t:10,r:12,b:34,l:58};const w=W-M.l-M.r,h=H-M.t-M.b;
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`},host);
  const totals=data.map(d=>keys.reduce((s,k)=>s+(d.values[k]||0),0));const ymax=niceMax(Math.max(...totals,0));
  const n=data.length;const bw=w/n;const grid=el('g',{class:'grid'},svg);const ax=el('g',{class:'axis'},svg);
  const ticks=5;for(let i=0;i<=ticks;i++){const y=M.t+h-h*i/ticks;el('line',{x1:M.l,x2:M.l+w,y1:y,y2:y},grid);const t=el('text',{x:M.l-6,y:y+4,'text-anchor':'end'},ax);t.textContent=fmt(ymax*i/ticks);}
  const step=Math.ceil(n/16);data.forEach((d,i)=>{if(i%step===0||i===n-1){const t=el('text',{x:M.l+bw*(i+.5),y:H-M.b+16,'text-anchor':'middle'},ax);t.textContent=d.x;}});
  const ylab=el('text',{x:M.l-6,y:M.t-2,'text-anchor':'end'},ax);ylab.textContent=opts.unit||'';
  data.forEach((d,i)=>{let y0=M.t+h;keys.forEach((k,ki)=>{const v=d.values[k]||0;if(v<=0)return;const bh=h*v/ymax;y0-=bh;
    const r=el('rect',{class:'bar',x:M.l+bw*i+bw*0.12,y:y0,width:bw*0.76,height:bh,fill:`var(${S[ki%8]})`,rx:0},svg);
    const rows=keys.filter(kk=>(d.values[kk]||0)>0).map(kk=>({color:css(S[keys.indexOf(kk)%8]),value:fmt(d.values[kk],opts.decimals),label:labels[kk]||kk}));
    rows.push({value:fmt(totals[i],opts.decimals),label:'total'});if(d.meta)for(const m of d.meta)rows.push({value:m[1],label:m[0]});
    r.addEventListener('pointermove',e=>showTip(e,d.x,rows));r.addEventListener('pointerleave',hideTip);});});
}
/* line chart, one or more series: series=[{key,label,points:[{x,y,n}]}], x categorical */
function lines(host,xs,series,opts){
  const W=opts.width||960,H=opts.height||260,M={t:10,r:12,b:34,l:52};const w=W-M.l-M.r,h=H-M.t-M.b;
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`},host);
  const ys=series.flatMap(s=>s.points.map(p=>p.y)).filter(v=>v!=null);const ymax=niceMax(Math.max(...ys,0));const ymin=Math.min(0,...ys);
  const yr=ymax-ymin||1;const sx=i=>M.l+w*(xs.length>1?i/(xs.length-1):0.5);const sy=v=>M.t+h-(v-ymin)/yr*h;
  const grid=el('g',{class:'grid'},svg);const ax=el('g',{class:'axis'},svg);
  for(let i=0;i<=4;i++){const v=ymin+yr*i/4;el('line',{x1:M.l,x2:M.l+w,y1:sy(v),y2:sy(v)},grid);const t=el('text',{x:M.l-6,y:sy(v)+4,'text-anchor':'end'},ax);t.textContent=fmt(v,opts.decimals);}
  const step=Math.ceil(xs.length/(W>600?14:7));xs.forEach((x,i)=>{if(i%step===0||i===xs.length-1){const t=el('text',{x:sx(i),y:H-M.b+16,'text-anchor':'middle'},ax);t.textContent=x;}});
  if(opts.windows)for(const win of opts.windows){const a=xs.indexOf(win[0]),b=xs.indexOf(win[1]);if(a<0||b<0)continue;el('rect',{x:sx(a)-w/xs.length/2,y:M.t,width:sx(b)-sx(a)+w/xs.length,height:h,fill:'var(--window)'},svg);const t=el('text',{x:sx(a),y:M.t+12,class:'axis'},ax);t.textContent=win[2];}
  series.forEach((s,si)=>{const col=`var(${S[si%8]})`;let d='';s.points.forEach((p,i)=>{if(p.y==null){return;}d+=(d&&s.points[i-1]&&s.points[i-1].y!=null?'L':'M')+sx(i)+' '+sy(p.y)+' ';});
    el('path',{class:'series-line',d,stroke:col},svg);s.points.forEach((p,i)=>{if(p.y!=null)el('circle',{class:'dot',cx:sx(i),cy:sy(p.y),r:3.5,fill:col},svg);});});
  const ch=el('line',{class:'crosshair',x1:0,x2:0,y1:M.t,y2:M.t+h},svg);
  const hit=el('rect',{class:'hit',x:M.l,y:M.t,width:w,height:h},svg);
  hit.addEventListener('pointermove',e=>{const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const q=pt.matrixTransform(svg.getScreenCTM().inverse());
    const i=Math.max(0,Math.min(xs.length-1,Math.round((q.x-M.l)/w*(xs.length-1))));ch.setAttribute('x1',sx(i));ch.setAttribute('x2',sx(i));ch.style.display='block';
    const rows=series.map((s,si)=>{const p=s.points[i]||{};return {color:css(S[si%8]),value:fmt(p.y,opts.decimals),label:s.label+(p.n!=null?' (n='+p.n+')':'')};});
    showTip(e,xs[i],rows);});
  hit.addEventListener('pointerleave',()=>{ch.style.display='none';hideTip();});
}
/* signed bars around zero (fund flows): points=[{x,y,meta}] */
function signedBars(host,points,opts){
  const W=opts.width||960,H=opts.height||220,M={t:10,r:12,b:30,l:60};const w=W-M.l-M.r,h=H-M.t-M.b;
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`},host);const ys=points.map(p=>p.y).filter(v=>v!=null);
  const amax=niceMax(Math.max(...ys.map(Math.abs),0));const sy=v=>M.t+h/2-(v/amax)*h/2;const bw=w/points.length;
  const grid=el('g',{class:'grid'},svg);const ax=el('g',{class:'axis'},svg);
  for(const v of [-amax,-amax/2,0,amax/2,amax]){el('line',{x1:M.l,x2:M.l+w,y1:sy(v),y2:sy(v)},grid);const t=el('text',{x:M.l-6,y:sy(v)+4,'text-anchor':'end'},ax);t.textContent=fmt(v/1e6,0)+'m';}
  if(opts.windows)for(const win of opts.windows){const a=points.findIndex(p=>p.x===win[0]),b=points.findIndex(p=>p.x===win[1]);if(a<0||b<0)continue;el('rect',{x:M.l+bw*a,y:M.t,width:bw*(b-a+1),height:h,fill:'var(--window)'},svg);const t=el('text',{x:M.l+bw*a+2,y:M.t+12},ax);t.textContent=win[2];}
  const step=Math.ceil(points.length/12);points.forEach((p,i)=>{if(i%step===0||i===points.length-1){const t=el('text',{x:M.l+bw*(i+.5),y:H-M.b+16,'text-anchor':'middle'},ax);t.textContent=p.x;}
    if(p.y==null){const r=el('rect',{x:M.l+bw*i+bw*.2,y:M.t,width:bw*.6,height:h,fill:'var(--grid)',opacity:.5},svg);r.addEventListener('pointermove',e=>showTip(e,p.x,[{value:'null',label:'net flow (sign unexplained or component missing)'}]));r.addEventListener('pointerleave',hideTip);return;}
    const y=Math.min(sy(0),sy(p.y)),bh=Math.abs(sy(p.y)-sy(0));const r=el('rect',{class:'bar',x:M.l+bw*i+bw*.2,y,width:bw*.6,height:Math.max(bh,1),fill:p.y>=0?'var(--pos)':'var(--neg)'},svg);
    r.addEventListener('pointermove',e=>showTip(e,p.x,[{value:fmt(p.y/1e6,1)+'m',label:'net flow, USD'},...(p.meta||[]).map(m=>({value:m[1],label:m[0]}))]));r.addEventListener('pointerleave',hideTip);});
}
function table(host,cols,rows){const t=document.createElement('table');const tr=document.createElement('tr');for(const c of cols){const th=document.createElement('th');th.textContent=c;tr.appendChild(th);}t.appendChild(tr);
  for(const r of rows){const tr2=document.createElement('tr');for(const c of cols){const td=document.createElement('td');td.textContent=r[c]==null?'':String(r[c]);tr2.appendChild(td);}t.appendChild(tr2);}host.appendChild(t);}
function legend(host,keys,labels,kind){const d=document.createElement('div');d.className='legend';keys.forEach((k,i)=>{const s=document.createElement('span');const sw=document.createElement('i');if(kind==='line')sw.className='line';sw.style.background=`var(${S[i%8]})`;s.appendChild(sw);s.appendChild(document.createTextNode(labels[k]||k));d.appendChild(s);});host.appendChild(d);}
document.getElementById('theme').addEventListener('click',()=>{const r=document.documentElement;const cur=r.getAttribute('data-theme');const dark=cur?cur==='dark':matchMedia('(prefers-color-scheme: dark)').matches;r.setAttribute('data-theme',dark?'light':'dark');});
"""


def _read(name: str) -> pd.DataFrame | None:
    path = ATLAS_DIR / name
    return pd.read_csv(path, keep_default_na=True) if path.exists() else None


def _fig(fig_id: str, title: str, sub: str, coverage: str, kind: str = "") -> str:
    return (f'<section class="fig {kind}" id="{fig_id}"><h2>{html.escape(title)}</h2><p class="sub">{html.escape(sub)}</p>'
            f'<div class="legend-host"></div><div class="chart"></div>'
            f'<p class="coverage">{html.escape(coverage)}</p>'
            f'<details><summary>Table</summary><div class="table"></div></details></section>')


def _stacked_payload(frame: pd.DataFrame, key: str, order: list[str], value: str, count: str, meta_fn) -> dict:
    keys = [k for k in order if k in set(frame[key])] + sorted(set(frame[key]) - set(order))
    if len(keys) > MAX_SERIES:
        keep = frame.groupby(key)[value].sum().sort_values(ascending=False).index[:MAX_SERIES - 1].tolist()
        keys = [k for k in keys if k in keep] + ["Other"]
        frame = frame.assign(**{key: frame[key].where(frame[key].isin(keep), "Other")})
    data = []
    for year, part in frame.groupby("issue_year"):
        values = part.groupby(key)[value].sum().to_dict()
        data.append({"x": str(int(year)), "values": {k: float(values.get(k, 0) or 0) for k in keys}, "meta": meta_fn(part)})
    return {"keys": keys, "data": data,
            "table": [{**{"year": int(r.issue_year)}, **{c: r[c] for c in frame.columns if c != "issue_year"}} for _, r in frame.iterrows()]}


def build_payload() -> tuple[dict, dict]:
    summary = json.loads((ATLAS_DIR / "summary.json").read_text()) if (ATLAS_DIR / "summary.json").exists() else {}
    payload: dict = {}

    uni = _read("universe_by_year.csv")
    if uni is not None:
        payload["universe"] = _stacked_payload(
            uni, "segment", SEGMENT_ORDER, "issued_usd_m", "deals",
            lambda part: [["deals in year", str(int(part["year_deals"].iloc[0]))],
                          ["deals with a USD size", str(int(part["deals_sized"].sum()))]])
        payload["universe"]["labels"] = SEGMENT_LABELS

    peril = _read("peril_by_year.csv")
    if peril is not None:
        payload["peril"] = _stacked_payload(
            peril, "hazard_class", [], "issued_usd_m_split", "deals",
            lambda part: [["core deals in year", str(int(part["year_core_deals"].iloc[0]))],
                          ["deals split over several classes", str(int(part["deals_multi"].sum()))],
                          ["unmapped", str(int(part.loc[part["hazard_class"].eq("unmapped"), "deals"].sum()))]])
        payload["peril"]["labels"] = {k: k.replace("_", " ") for k in payload["peril"]["keys"]}

    for name, key, order in (("trigger", "trigger_type", TRIGGER_ORDER), ("sponsor", "sponsor_type", SPONSOR_ORDER)):
        frame = _read(f"{name}{'_type' if name == 'sponsor' else ''}_by_year.csv")
        if frame is not None:
            payload[name] = _stacked_payload(
                frame, key, order, "issued_usd_m", "deals",
                lambda part: [["deals in year", str(int(part["year_deals"].iloc[0]))],
                              ["deals with a USD size", str(int(part["deals_sized"].sum()))]])
            payload[name]["labels"] = {k: k.replace("_", " ") for k in payload[name]["keys"]}

    def _layer_payload(frame, order, labels, metric):
        core = frame[frame["segment"].eq("core_property_cat")]
        years = sorted(core["issue_year"].unique().tolist())
        bands = {}
        for band in order:
            part = core[core["band"].eq(band)].set_index("issue_year")
            if part.empty:
                continue
            bands[band] = {
                "label": labels[band],
                "xs": [str(y) for y in years],
                "spread": [{"x": str(y), "y": (None if y not in part.index or pd.isna(part.loc[y, "median_spread"]) else float(part.loc[y, "median_spread"])),
                            "n": (0 if y not in part.index else int(part.loc[y, "n_spread"]))} for y in years],
                "el": [{"x": str(y), "y": (None if y not in part.index or pd.isna(part.loc[y, "median_el"]) else float(part.loc[y, "median_el"])),
                        "n": (0 if y not in part.index else int(part.loc[y, "n_el"]))} for y in years],
                "tranches": int(part["tranches"].sum()), "with_spread": int(part["n_spread"].sum()), "with_el": int(part["n_el"].sum()),
            }
        return {"bands": bands, "core_tranches": int(core["tranches"].sum()),
                "core_with_metric": int(core[f"n_{metric}"].sum()),
                "table": core.drop(columns=["segment"]).to_dict(orient="records")}

    layers = _read("layer_by_year.csv")
    if layers is not None:
        payload["layers"] = _layer_payload(layers, BAND_ORDER, BAND_LABELS, "ap")
    layers_el = _read("layer_by_year_el.csv")
    if layers_el is not None:
        payload["layers_el"] = _layer_payload(layers_el, EL_BAND_ORDER, EL_BAND_LABELS, "el")
    cov = _read("layer_coverage_by_year.csv")
    if cov is not None:
        core = cov[cov["segment"].eq("core_property_cat")].drop(columns=["segment"])
        payload["layer_coverage"] = {"table": core.to_dict(orient="records")}

    stock = _read("outstanding_by_segment.csv")
    if stock is not None and not stock.empty:
        keys = [k for k in SEGMENT_ORDER if k in set(stock["segment"])] + sorted(set(stock["segment"]) - set(SEGMENT_ORDER))
        data = []
        for year, part in stock.groupby("year"):
            vals = part.set_index("segment")["outstanding"].to_dict()
            data.append({"x": str(int(year)), "values": {k: float(vals.get(k, 0) or 0) for k in keys},
                         "meta": [["measured at", str(part["measured_at"].iloc[0])]]})
        payload["stock"] = {"keys": keys, "data": data, "labels": SEGMENT_LABELS,
                            "table": stock[["year", "segment", "measured_at", "issued", "written_down", "recovered", "repaid", "outstanding", "deals"]].to_dict(orient="records")}

    flows = _read("fund_flows_by_month.csv")
    if flows is not None and not flows.empty:
        lineages = {}
        for lineage, part in flows.groupby("lineage"):
            part = part.sort_values("month")
            lineages[lineage] = {
                "points": [{"x": r.month, "y": (None if pd.isna(r.net_flow_usd) else float(r.net_flow_usd)),
                            "meta": [["funds", str(int(r.funds))], ["basis", str(r.basis)]]} for r in part.itertuples()],
                "months": int(len(part)), "null_months": int(part["net_flow_usd"].isna().sum()),
                "total": (None if part["net_flow_usd"].isna().all() else float(part["net_flow_usd"].sum())),
            }
        payload["flows"] = {"lineages": lineages, "windows": [["2022-08", "2022-11", "Ian"], ["2024-09", "2024-12", "Milton"]],
                            "table": flows.to_dict(orient="records")}

    marks = _read("marks_by_quarter.csv")
    if marks is not None and not marks.empty:
        payload["marks"] = {"xs": marks["quarter"].astype(str).tolist(),
                            "series": [{"key": "median_abs_gap", "label": "median absolute gap, points",
                                        "points": [{"x": q, "y": float(v), "n": int(n)} for q, v, n in zip(marks["quarter"], marks["median_abs_gap"], marks["pairs_with_trace"])]},
                                       {"key": "p90_abs_gap", "label": "90th percentile absolute gap, points",
                                        "points": [{"x": q, "y": float(v), "n": int(n)} for q, v, n in zip(marks["quarter"], marks["p90_abs_gap"], marks["pairs_with_trace"])]}],
                            "pairs": int(marks["pairs"].sum()), "with_trace": int(marks["pairs_with_trace"].sum()),
                            "table": marks.to_dict(orient="records")}
    comp = _read("comparators_by_year.csv")
    if comp is not None and not comp.empty:
        years = comp["year"].astype(int).astype(str).tolist()
        def ser(col, label):
            return {"key": col, "label": label, "points": [{"x": y, "y": (None if pd.isna(v) else float(v))} for y, v in zip(years, comp[col])]} if col in comp.columns else None
        panels = [p for p in [
            ("rol", "Guy Carpenter global property-cat rate-on-line index, 2000 = 100", [ser("gc_rol_index_2000_eq_100", "ROL index")]),
            ("lane", "Lane annual nat-cat ILS pricing, percent of limit", [ser("lane_weighted_premium_pct", "weighted premium %"), ser("lane_weighted_el_pct", "weighted expected loss %")]),
            ("aon", "Aon property-cat bond annual issuance, USD m", [ser("aon_property_cat_issuance_usd_m", "issuance USD m")]),
        ] if all(p[2])]
        payload["comparators"] = {"xs": years, "panels": [{"id": pid, "title": title, "series": series} for pid, title, series in panels],
                                  "table": comp.to_dict(orient="records")}
    return payload, summary


def render(payload: dict, summary: dict) -> str:
    u = summary.get("universe", {})
    seg_counts = u.get("by_segment", {})
    figs = []
    if "universe" in payload:
        figs.append(_fig("f-universe", "Issued principal by segment and year",
                         "USD millions from the parsed size, mortgage, life and lite reported separately from the core",
                         "Computed from %d directory deals; %d have no USD size and are counted but not summed; %d have no issue year. Segments: %s." % (
                             u.get("deals", 0), u.get("deals_without_usd_size", 0), u.get("deals_without_issue_year", 0),
                             ", ".join("%s %d" % (SEGMENT_LABELS.get(k, k), v) for k, v in seg_counts.items()))))
    if "peril" in payload:
        p = summary.get("peril", {})
        figs.append(_fig("f-peril", "Issued principal allocated by peril, core property cat",
                         "An accounting allocation, not exposure: a deal covering several hazard classes is counted in each and its size split equally between them; the hazard map is the panel builder's peril lexicon. Sample selection for an event study must use the full peril tags and contract terms, never this split",
                         "Core segment only: %d deals, %d mapped to at least one hazard class (%d of them only as multi-peril, unspecified), %d unmapped, %d carry a mixed specialty peril and stay in the core." % (
                             p.get("core_deals", 0), p.get("core_deals_mapped", 0), p.get("core_deals_multi_peril_unspecified", 0),
                             p.get("core_deals_unmapped", 0), p.get("core_deals_mixed_peril", 0))))
    if "trigger" in payload:
        figs.append(_fig("f-trigger", "Issued principal by trigger type and year", "Whole directory; 'unknown' is a page the parser read no trigger from",
                         "Trigger known on %d of %d deals." % (sum(v for k, v in u.get("trigger_type", {}).items() if k != "unknown"), u.get("deals", 0))))
    if "sponsor" in payload:
        figs.append(_fig("f-sponsor", "Issued principal by sponsor type and year",
                         "Keyword classification of the parsed sponsor name: insurer, reinsurer, public sector, corporate or other; undisclosed where a private deal names none, unknown where a public one does",
                         "Sponsor named on %d of %d deals (%d private deals name none); the keyword rules are in build_atlas.py, the corporate/other and unknown rows are listed in review_sponsor_type.csv for a hand check." % (
                             u.get("deals", 0) - u.get("sponsor_type", {}).get("unknown", 0) - u.get("sponsor_type", {}).get("undisclosed", 0),
                             u.get("deals", 0), u.get("sponsor_type", {}).get("undisclosed", 0))))
    def _layer_fig(fig_id, L, title, sub, coverage):
        inner = "".join(
            f'<section class="fig" data-band="{html.escape(band)}"><h2>{html.escape(b["label"])}</h2>'
            f'<p class="sub">Median risk-margin spread (percent) by issue year, core tranches</p><div class="chart"></div>'
            f'<p class="coverage">{b["tranches"]} tranches in this band; spread stated on {b["with_spread"]}, expected loss on {b["with_el"]}. Hover shows the count behind each point.</p></section>'
            for band, b in L["bands"].items())
        return (f'<section class="fig" id="{fig_id}"><h2>{html.escape(title)}</h2><p class="sub">{html.escape(sub)}</p>'
                f'<p class="coverage">{coverage}</p><div class="multi">{inner}</div><details><summary>Table</summary><div class="table"></div></details></section>')

    if "layers_el" in payload:
        L = payload["layers_el"]
        both = summary.get("layers", {}).get("core_tranches_with_both_el_and_ap", 0)
        figs.append(_layer_fig("f-layers-el", L, "Pricing by expected-loss band (primary view)",
                               "One panel per band, the same y-axis unit in every panel; the same edges as the attachment-probability bands below",
                               f'Core tranches {L["core_tranches"]}, expected loss stated on {L["core_with_metric"]} ({both} of them also state an attachment probability). '
                               'An expected-loss band is a pricing band, not a layer: it folds attachment and severity together, so bonds in one band can attach at very different probabilities. '
                               'Coverage by year for both metrics is in the table under the next figure.'))
    if "layers" in payload:
        L = payload["layers"]
        figs.append(_layer_fig("f-layers", L, "Layers: spread by attachment-probability band",
                               "The layer language; well covered from 2022 on, a source gap for 2019 to 2021 (the pages state no attachment probability)",
                               f'Core tranches {L["core_tranches"]}, attachment probability stated on {L["core_with_metric"]}; tranches without it are the last panel. '
                               'Spread is the parsed risk margin; the price-guidance midpoint and size-weighted spread are in the table. '
                               'Any layer-overlap comparison against reinsurance should use this view, and only where the year\'s coverage supports it.'))
    if "layer_coverage" in payload:
        figs.append('<section class="fig" id="f-layer-coverage"><h2>Coverage of the two band views, core tranches by issue year</h2>'
                    '<p class="sub">Tranches and issued USD with expected loss, attachment probability, both, and expected loss plus a settled spread</p>'
                    '<div class="table"></div></section>')
    if "flows" in payload:
        F = payload["flows"]
        inner = "".join(
            f'<section class="fig" data-lineage="{html.escape(name)}"><h2>{html.escape(name)}</h2>'
            f'<p class="sub">Net subscriptions per month, USD, from Form N-PORT; Ian and Milton windows shaded</p><div class="chart"></div>'
            f'<p class="coverage">{d["months"]} months, {d["null_months"]} with a null flow (sign unexplained or a component missing); total {"n/a" if d["total"] is None else format(d["total"] / 1e6, ",.0f") + "m"}.</p></section>'
            for name, d in F["lineages"].items())
        figs.append(f'<section class="fig" id="f-flows"><h2>Fund net subscriptions by lineage and month</h2>'
                    f'<p class="sub">Observed sales minus redemptions for the registered funds; predecessor and successor funds are one lineage</p>'
                    f'<p class="coverage">{len(F["lineages"])} lineages. Only quarter-end filings are public, so each series arrives in three-month batches with a 60-day lag.</p>'
                    f'<div class="multi">{inner}</div><details><summary>Table</summary><div class="table"></div></details></section>')
    if "marks" in payload:
        M = payload["marks"]
        figs.append(_fig("f-marks", "Fund marks versus TRACE by quarter",
                         "Absolute gap in price points between the par-weighted fund mark and the TRACE volume-weighted price around each quarter end",
                         "%d CUSIP-quarter pairs, %d with a TRACE price in the window. Hover shows the pair count behind each point." % (M["pairs"], M["with_trace"])))
    if "comparators" in payload:
        C = payload["comparators"]
        cov = summary.get("comparators", {})
        inner = "".join(
            f'<section class="fig" data-panel="{html.escape(p["id"])}"><h2>{html.escape(p["title"])}</h2><div class="legend-host"></div><div class="chart"></div>'
            f'<p class="coverage">{", ".join("%s: %d years" % (s["label"], cov.get(s["key"], 0)) for s in p["series"])}.</p></section>'
            for p in C["panels"])
        figs.append(f'<section class="fig" id="f-comparators"><h2>Published comparators, each in its own units</h2>'
                    f'<p class="sub">Extracted from the publishers\' charts and tables; shown beside the parsed series, never joined to them</p>'
                    f'<p class="coverage">The rate-on-line index is a digitised chart with a stated uncertainty of about half an index point; the Lane series are weighted by limit issued over the tranches in each year; Aon counts property-cat bonds on its own scope. Hover shows the values; the table has every column.</p>'
                    f'<div class="multi">{inner}</div><details><summary>Table</summary><div class="table"></div></details></section>')
    body = "\n".join(figs)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cat bond market atlas</title><style>{STYLE}</style></head>
<body><header><h1>Cat bond market atlas</h1>
<p>Descriptive tables from the parsed directory and the joins, with the count behind every number. Generated {html.escape(str(summary.get("generated_at", "")))}. Not a hypothesis test.</p>
<div class="toolbar"><button id="theme">Toggle theme</button></div></header>
<main>{body}</main>
<script>const P={json.dumps(payload)};{SCRIPT}
(function(){{
  function mount(id,key,unit,decimals){{const f=document.getElementById(id);if(!f||!P[key])return;const d=P[key];legend(f.querySelector('.legend-host'),d.keys,d.labels,'rect');
    stackedBars(f.querySelector('.chart'),d.data,d.keys,d.labels,{{unit:unit,decimals:decimals}});const cols=Object.keys(d.table[0]||{{}});table(f.querySelector('.table'),cols,d.table);}}
  mount('f-universe','universe','USD m',0);mount('f-peril','peril','USD m, split',0);mount('f-trigger','trigger','USD m',0);mount('f-sponsor','sponsor','USD m',0);mount('f-stock','stock','USD m',0);
  for(const [id,L] of [['f-layers',P.layers],['f-layers-el',P.layers_el]]){{if(!L)continue;const f=document.getElementById(id);for(const [band,b] of Object.entries(L.bands)){{const host=f.querySelector(`[data-band="${{band}}"] .chart`);
      lines(host,b.xs,[{{key:'spread',label:'median spread %',points:b.spread}},{{key:'el',label:'median expected loss %',points:b.el}}],{{width:480,height:220,decimals:2}});
      legend(host.parentElement,['spread','el'],{{spread:'median spread %',el:'median expected loss %'}},'line');}}
    table(f.querySelector('.table'),Object.keys(L.table[0]||{{}}),L.table);}}
  if(P.layer_coverage){{const f=document.getElementById('f-layer-coverage');table(f.querySelector('.table'),Object.keys(P.layer_coverage.table[0]||{{}}),P.layer_coverage.table);}}
  if(P.flows){{const f=document.getElementById('f-flows');for(const [name,d] of Object.entries(P.flows.lineages)){{signedBars(f.querySelector(`[data-lineage="${{name}}"] .chart`),d.points,{{width:480,height:200,windows:P.flows.windows}});}}
    table(f.querySelector('.table'),Object.keys(P.flows.table[0]||{{}}),P.flows.table);}}
  if(P.comparators){{const f=document.getElementById('f-comparators');for(const p of P.comparators.panels){{const host=f.querySelector(`[data-panel="${{p.id}}"]`);
      lines(host.querySelector('.chart'),P.comparators.xs,p.series,{{width:480,height:220,decimals:1}});if(p.series.length>1)legend(host.querySelector('.legend-host'),p.series.map(s=>s.key),Object.fromEntries(p.series.map(s=>[s.key,s.label])),'line');}}
    table(f.querySelector('.table'),Object.keys(P.comparators.table[0]||{{}}),P.comparators.table);}}
  if(P.marks){{const f=document.getElementById('f-marks');legend(f.querySelector('.legend-host'),['median_abs_gap','p90_abs_gap'],{{median_abs_gap:'median absolute gap',p90_abs_gap:'90th percentile'}},'line');
    lines(f.querySelector('.chart'),P.marks.xs,P.marks.series,{{decimals:2}});table(f.querySelector('.table'),Object.keys(P.marks.table[0]||{{}}),P.marks.table);}}
}})();
</script></body></html>"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    payload, summary = build_payload()
    args.out.write_text(render(payload, summary), encoding="utf-8")
    print("wrote %s (%d figures)" % (args.out, len(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
