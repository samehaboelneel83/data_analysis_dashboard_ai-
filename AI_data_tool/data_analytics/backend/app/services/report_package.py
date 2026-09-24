"""Offline report package (MASTER_PLAN Phase 5 item 4).

One self-contained HTML file: the report's visible pages, each widget's
RESULT frozen at export time (resolved as the exporter -- their row security,
their column security, the dataset's export policy), and a small renderer
inlined beside it. It opens from `file://`, on a laptop with no network and no
account, which is the point: a report handed to someone outside the platform,
or read on a plane.

What it deliberately is not: live. There is no query path inside it, so it can
leak nothing the exporter could not see when they pressed the button, and it
says on every page when that was and whose view it is.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any

#: Past this many rows a frozen table is a data export, not a report page.
MAX_ROWS_PER_WIDGET = 500


def _trim(result: dict) -> dict:
    """Keep what the renderer draws; cap row counts, and SAY the cap."""
    out = {k: v for k, v in result.items() if k in (
        "type", "rows", "columns", "dimension", "measure", "aggregation", "value", "total",
        "truncation", "content", "status", "reason")}
    rows = result.get("rows")
    if isinstance(rows, list) and len(rows) > MAX_ROWS_PER_WIDGET:
        out["rows"] = rows[:MAX_ROWS_PER_WIDGET]
        out["package_cap"] = {"shown": MAX_ROWS_PER_WIDGET, "of": len(rows)}
    return out


def build_package_html(report: dict[str, Any], exporter: str, generated: datetime | None = None) -> str:
    """`report` = {name, description, classification, pages: [{name, widgets: [
    {title, widget_type, layout, content?, result?, withheld?}]}]}."""
    generated = generated or datetime.now(timezone.utc)
    payload = {
        "name": report.get("name") or "Report",
        "description": report.get("description") or "",
        "classification": report.get("classification"),
        "exporter": exporter,
        "generated": generated.strftime("%Y-%m-%d %H:%M UTC"),
        "pages": [{
            "name": p.get("name") or "Page",
            "widgets": [{**{k: w.get(k) for k in ("title", "widget_type", "layout", "content", "withheld")},
                         **({"result": _trim(w["result"])} if isinstance(w.get("result"), dict) else {})}
                        for w in p.get("widgets") or []],
        } for p in report.get("pages") or []],
    }
    # `</` would end the <script> element early; JSON allows the escaped form.
    data = json.dumps(payload, ensure_ascii=False, default=str).replace("</", "<\\/")
    title = html.escape(payload["name"])
    return _TEMPLATE.replace("%%TITLE%%", title).replace("%%DATA%%", data)


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%TITLE%%</title>
<style>
:root{--bg:#f6f7f9;--surface:#fff;--text:#1d2330;--muted:#6b7280;--border:#e3e6eb;--accent:#4f7cff}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--surface:#171a21;--text:#e7e9ee;--muted:#9aa1ad;--border:#2a2f3a;--accent:#7c9cff}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Arabic",sans-serif;background:var(--bg);color:var(--text)}
header{padding:14px 18px;background:var(--surface);border-bottom:1px solid var(--border)}
header h1{font-size:18px;margin:0}header .meta{color:var(--muted);font-size:12px;margin-top:4px}
.badge{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#fff;background:#b45309;border-radius:4px;padding:2px 7px;margin-inline-start:8px}
nav{display:flex;gap:4px;padding:8px 18px;flex-wrap:wrap}nav button{font:inherit;border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:6px;padding:4px 10px;cursor:pointer}
nav button[aria-selected=true]{border-color:var(--accent);color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(12,1fr);grid-auto-rows:56px;gap:10px;padding:10px 18px 40px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:8px 10px;overflow:hidden;display:flex;flex-direction:column;min-width:0}
.card h2{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.body{flex:1;min-height:0;overflow:auto}.note{color:var(--muted);font-size:11px;margin-top:4px}
table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid var(--border);padding:3px 6px;text-align:start}td.n{text-align:end;font-variant-numeric:tabular-nums}
.kpi{font-size:32px;font-weight:700}
@media (max-width:700px){.grid{grid-template-columns:1fr;grid-auto-rows:auto}.card{grid-column:1!important;grid-row:auto!important;min-height:220px}}
</style></head><body>
<header><h1 id="t"></h1><div class="meta" id="m"></div></header>
<nav id="tabs" role="tablist"></nav><main id="page" class="grid"></main>
<script type="application/json" id="report-data">%%DATA%%</script>
<script>
(function(){
var R=JSON.parse(document.getElementById('report-data').textContent);
var PAL=['#4f7cff','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16'];
function el(t,a,c){var e=document.createElement(t);if(a)for(var k in a){if(k==='text')e.textContent=a[k];else e.setAttribute(k,a[k]);}(c||[]).forEach(function(x){if(x)e.appendChild(x)});return e}
function svg(t,a){var e=document.createElementNS('http://www.w3.org/2000/svg',t);for(var k in a)e.setAttribute(k,a[k]);return e}
function fmt(v){if(typeof v!=='number')return v==null?'':String(v);var a=Math.abs(v);return a>=1e6?(v/1e6).toFixed(1)+'M':a>=1e4?(v/1e3).toFixed(1)+'K':Math.round(v*100)/100+''}
document.getElementById('t').textContent=R.name;
if(R.classification){document.getElementById('t').appendChild(el('span',{'class':'badge',text:R.classification}))}
document.getElementById('m').textContent='Snapshot taken '+R.generated+' — the rows '+R.exporter+' could see then. Not live.'+(R.description?' '+R.description:'');
function series(res){return (res.rows||[]).filter(function(r){return r&&('name' in r)&&typeof r.value==='number'})}
function bars(res,horizontal){var rows=series(res).slice(0,30);var W=520,H=240,s=svg('svg',{viewBox:'0 0 '+W+' '+H,width:'100%',height:'100%',role:'img'});
 var max=Math.max.apply(null,rows.map(function(r){return r.value}).concat([0]))||1;var bw=(W-40)/Math.max(rows.length,1);
 rows.forEach(function(r,i){var h=(H-40)*Math.max(r.value,0)/max;var x=30+i*bw;s.appendChild(svg('rect',{x:x+2,y:H-24-h,width:Math.max(bw-4,1),height:h,fill:PAL[0],rx:2}));
  var t=svg('text',{x:x+bw/2,y:H-10,'font-size':10,'text-anchor':'middle',fill:'currentColor'});t.textContent=String(r.name).slice(0,12);s.appendChild(t);
  var v=svg('text',{x:x+bw/2,y:H-28-h,'font-size':9,'text-anchor':'middle',fill:'currentColor'});v.textContent=fmt(r.value);s.appendChild(v)});return s}
function line(res){var rows=series(res).slice(0,200);var W=520,H=240,s=svg('svg',{viewBox:'0 0 '+W+' '+H,width:'100%',height:'100%',role:'img'});if(!rows.length)return s;
 var vs=rows.map(function(r){return r.value});var lo=Math.min.apply(null,vs.concat([0])),hi=Math.max.apply(null,vs)||1;
 var pts=rows.map(function(r,i){return (30+i*(W-40)/Math.max(rows.length-1,1))+','+(H-24-(H-40)*(r.value-lo)/((hi-lo)||1))}).join(' ');
 s.appendChild(svg('polyline',{points:pts,fill:'none',stroke:PAL[0],'stroke-width':2}));
 [0,rows.length-1].forEach(function(i){var t=svg('text',{x:i?W-10:30,y:H-8,'font-size':10,'text-anchor':i?'end':'start',fill:'currentColor'});t.textContent=rows[i].name;s.appendChild(t)});return s}
function pie(res){var rows=series(res).filter(function(r){return r.value>0}).slice(0,12);var tot=rows.reduce(function(a,r){return a+r.value},0)||1;
 var s=svg('svg',{viewBox:'0 0 360 220',width:'100%',height:'100%',role:'img'});var a0=-Math.PI/2;
 rows.forEach(function(r,i){var a1=a0+2*Math.PI*r.value/tot;var x0=110+90*Math.cos(a0),y0=110+90*Math.sin(a0),x1=110+90*Math.cos(a1),y1=110+90*Math.sin(a1);
  s.appendChild(svg('path',{d:'M110 110 L'+x0+' '+y0+' A90 90 0 '+(a1-a0>Math.PI?1:0)+' 1 '+x1+' '+y1+' Z',fill:PAL[i%PAL.length]}));a0=a1;
  var t=svg('text',{x:215,y:20+i*16,'font-size':11,fill:'currentColor'});t.textContent='■ '+r.name+' — '+Math.round(100*r.value/tot)+'%';t.setAttribute('style','fill:'+PAL[i%PAL.length]);s.appendChild(t)});return s}
function table(res){var rows=res.rows||[];if(!rows.length)return el('div',{'class':'note',text:'No rows.'});
 var cols=res.columns||Object.keys(rows[0]).filter(function(k){return typeof rows[0][k]!=='object'||rows[0][k]===null});
 var t=el('table');t.appendChild(el('tr',{},cols.map(function(c){return el('th',{text:c})})));
 rows.slice(0,500).forEach(function(r){t.appendChild(el('tr',{},cols.map(function(c){var v=Array.isArray(r)?r[cols.indexOf(c)]:r[c];return el('td',{'class':typeof v==='number'?'n':'',text:fmt(v)})})))});return t}
function body(w){var res=w.result||{};var t=w.widget_type;
 if(w.withheld)return el('div',{'class':'note',text:w.withheld});
 if(t==='text')return el('div',{text:w.content||''});
 if(res.status==='refused'||res.reason)return el('div',{'class':'note',text:res.reason||'Not available.'});
 if(t==='kpi'||t==='card'||t==='gauge'){var r=(res.rows||[])[0]||{};var v=r.value!=null?r.value:res.value;return el('div',{'class':'kpi',text:fmt(v)})}
 if(series(res).length&&['line','area','step','forecast','numeric_series'].indexOf(t)>=0)return line(res);
 if(series(res).length&&['pie','donut','treemap','funnel'].indexOf(t)>=0)return pie(res);
 if(series(res).length&&!res.columns)return bars(res);
 return table(res)}
function show(i){var p=R.pages[i];var m=document.getElementById('page');m.innerHTML='';
 [].forEach.call(document.querySelectorAll('nav button'),function(b,j){b.setAttribute('aria-selected',String(j===i))});
 p.widgets.forEach(function(w){var L=w.layout||{};var c=el('section',{'class':'card',style:'grid-column:'+((L.x||0)+1)+' / span '+(L.w||6)+';grid-row:'+((L.y||0)+1)+' / span '+(L.h||4)});
  if(w.title)c.appendChild(el('h2',{text:w.title}));var b=el('div',{'class':'body'});b.appendChild(body(w));c.appendChild(b);
  var res=w.result||{};if(res.package_cap)c.appendChild(el('div',{'class':'note',text:'Showing '+res.package_cap.shown+' of '+res.package_cap.of+' rows in this package.'}));
  else if(res.truncation&&res.truncation.applied)c.appendChild(el('div',{'class':'note',text:'Showing '+res.truncation.shown+' of '+res.truncation.of+' groups (row limit).'}));
  m.appendChild(c)})}
var nav=document.getElementById('tabs');R.pages.forEach(function(p,i){var b=el('button',{role:'tab',text:p.name});b.onclick=function(){show(i)};nav.appendChild(b)});
if(R.pages.length)show(0);else document.getElementById('page').textContent='This report has no page to show.';
})();
</script></body></html>
"""
