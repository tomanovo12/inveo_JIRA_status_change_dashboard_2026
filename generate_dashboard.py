#!/usr/bin/env python3
"""
Inveo JIRA Dashboard Generator
Stáhne changelog z JIRA a vygeneruje HTML dashboard.
"""

import os
import json
import base64
import urllib.parse
from datetime import datetime, timedelta, date
import requests

# ── Konfigurace ────────────────────────────────────────────────────────────────
JIRA_BASE  = "https://inveo-cz.atlassian.net"
CLOUD_ID   = "a1c9c25d-c293-4138-96f4-23214a115b30"
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_TOKEN"]
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "docs")

# Rozsah: posledních 90 dní (vždy relativní k dnešku)
DATE_TO   = date.today()
DATE_FROM = DATE_TO - timedelta(days=90)

DATE_FROM_STR = DATE_FROM.isoformat()
DATE_TO_STR   = DATE_TO.isoformat()

SESSION = requests.Session()
SESSION.auth = (JIRA_EMAIL, JIRA_TOKEN)
SESSION.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

# ── Helpers ────────────────────────────────────────────────────────────────────
def jira_get(path):
    url = f"{JIRA_BASE}{path}"
    r = SESSION.get(url, timeout=30)
    if not r.ok:
        print(f"  HTTP {r.status_code} na {url}")
        print(f"  Odpověď: {r.text[:300]}")
        r.raise_for_status()
    return r.json()

def jira_post(path, body):
    url = f"{JIRA_BASE}{path}"
    r = SESSION.post(url, json=body, timeout=30)
    if not r.ok:
        print(f"  HTTP {r.status_code} na {url}")
        print(f"  Odpověď: {r.text[:500]}")
        r.raise_for_status()
    return r.json()

def fetch_issues_with_status_change():
    """Stáhne issues aktualizované v daném rozsahu (changelog se filtruje dále)."""
    issues = []
    jql = f'updated >= "{DATE_FROM_STR}" AND updated <= "{DATE_TO_STR}" ORDER BY updated DESC'
    print(f"Hledám issues aktualizované {DATE_FROM_STR} – {DATE_TO_STR}...")

    next_token = None
    while True:
        body = {"jql": jql, "maxResults": 100, "fields": ["summary"]}
        if next_token:
            body["nextPageToken"] = next_token

        data = jira_post("/rest/api/3/search/jql", body)
        batch = data.get("issues", [])
        issues.extend(batch)
        print(f"  Načteno {len(issues)} issues...")

        next_token = data.get("nextPageToken")
        if data.get("isLast", True) or not batch or not next_token:
            break

    print(f"Celkem issues ke zpracování: {len(issues)}")
    return issues

def fetch_changelog(issue_key, summary):
    """Načte changelog pro jeden issue a vrátí status změny v rozsahu."""
    changes = []
    start = 0
    while True:
        path = f"/rest/api/3/issue/{issue_key}/changelog?startAt={start}&maxResults=100"
        data = jira_get(path)
        histories = data.get("values", [])
        for h in histories:
            h_date = h.get("created", "")[:10]
            if h_date < DATE_FROM_STR or h_date > DATE_TO_STR:
                continue
            author = h.get("author", {}).get("displayName", "—")
            for item in h.get("items", []):
                if item.get("field") == "status":
                    changes.append({
                        "issueKey":     issue_key,
                        "project":      issue_key.split("-")[0],
                        "issueSummary": summary,
                        "date":         h["created"],
                        "author":       author,
                        "fromStatus":   item.get("fromString", "—"),
                        "toStatus":     item.get("toString", "—"),
                    })
        if data.get("isLast", True) or len(histories) < 100:
            break
        start += len(histories)
    return changes

def fetch_all_changes(issues):
    """Projde všechny issues a sbírá status změny."""
    all_changes = []
    total = len(issues)
    for i, iss in enumerate(issues, 1):
        key     = iss["key"]
        summary = iss["fields"].get("summary", key)
        try:
            changes = fetch_changelog(key, summary)
            all_changes.extend(changes)
            if i % 20 == 0 or i == total:
                print(f"  [{i}/{total}] {key} → {len(changes)} změn (celkem {len(all_changes)})")
        except Exception as e:
            print(f"  [{i}/{total}] {key} CHYBA: {e}")
    all_changes.sort(key=lambda x: x["date"], reverse=True)
    return all_changes

# ── HTML generátor ─────────────────────────────────────────────────────────────
PROJECT_PALETTE = [
    "#0052cc","#1a66d4","#36b37e","#00b8d9","#ff8b00","#6554c0","#8777d9","#ff5630",
    "#57d9a3","#00a3bf","#172b4d","#ff7452","#2684ff","#4c9aff","#0747a6","#403294",
    "#79e2f2","#ffe380","#00875a","#e01e5a","#1264a3","#2eb886","#ecb22e","#ab9df2",
    "#78dce8","#a9dc76","#ffd866","#fc9867","#ff6188","#727072","#403e41","#0d3349",
    "#007a5e","#5c4aff","#c07400","#7b2d00","#5c0f8b","#006655","#00558b","#8b0000",
    "#4b0082","#006400","#8b4513","#2f4f4f","#800080","#b8860b","#008080","#4169e1",
    "#dc143c","#228b22","#ff4500","#9400d3","#1e90ff","#32cd32","#ff1493","#00ced1",
    "#ffa500","#20b2aa","#cd853f","#708090",
]

def build_html(data, date_from, date_to):
    projects = sorted(set(d["project"] for d in data))
    proj_colors = {p: PROJECT_PALETTE[i % len(PROJECT_PALETTE)] for i, p in enumerate(projects)}

    meta = json.dumps({
        "lastUpdated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "taskCount":   len(set(d["issueKey"] for d in data)),
        "recordCount": len(data),
        "dateFrom":    date_from,
        "dateTo":      date_to,
    }, ensure_ascii=False)

    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    proj_colors_js = json.dumps(proj_colors)

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Inveo JIRA – Status změny</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f6fa;color:#2d3748}}
  header{{background:#0052cc;color:white;padding:18px 28px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}}
  header h1{{font-size:1.15rem;font-weight:600}}
  .header-meta{{font-size:0.78rem;opacity:0.65;text-align:right}}
  .container{{max-width:1400px;margin:0 auto;padding:24px}}
  .kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:24px}}
  .kpi{{background:white;border-radius:10px;padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
  .kpi .num{{font-size:2rem;font-weight:700;color:#0052cc;line-height:1}}
  .kpi .lbl{{font-size:0.78rem;color:#718096;margin-top:5px}}
  .filters{{background:white;border-radius:10px;padding:16px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:24px;display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end}}
  .filter-group{{display:flex;flex-direction:column;gap:5px}}
  .filter-group label{{font-size:0.72rem;font-weight:600;color:#718096;text-transform:uppercase;letter-spacing:.04em}}
  .filter-group select,.filter-group input{{border:1px solid #e2e8f0;border-radius:6px;padding:7px 10px;font-size:0.86rem;background:#f7f8fc;color:#2d3748;min-width:140px}}
  .filter-group select:focus,.filter-group input:focus{{outline:none;border-color:#0052cc}}
  .btn-reset{{padding:7px 16px;border-radius:6px;border:1px solid #e2e8f0;background:white;color:#4a5568;font-size:0.84rem;cursor:pointer}}
  .btn-reset:hover{{background:#f0f0f0}}
  .charts{{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-bottom:20px}}
  .charts2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}}
  .card{{background:white;border-radius:10px;padding:20px 22px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
  .card h2{{font-size:0.9rem;font-weight:600;color:#4a5568;margin-bottom:16px}}
  .chart-wrap{{position:relative;height:220px}}
  .chart-wrap-lg{{position:relative;height:240px}}
  .table-wrap{{background:white;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.06);overflow:hidden}}
  .table-header{{padding:16px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #e2e8f0;flex-wrap:wrap;gap:8px}}
  .table-header h2{{font-size:0.92rem;font-weight:600;color:#4a5568}}
  .table-header-right{{display:flex;align-items:center;gap:10px}}
  .count-badge{{background:#e8f0fe;color:#0052cc;font-size:0.78rem;font-weight:600;padding:3px 9px;border-radius:20px}}
  .pagination{{display:flex;align-items:center;gap:6px}}
  .pg-btn{{padding:4px 10px;border-radius:5px;border:1px solid #e2e8f0;background:white;color:#4a5568;font-size:0.8rem;cursor:pointer}}
  .pg-btn:hover{{background:#f0f0f0}}
  .pg-btn:disabled{{opacity:0.4;cursor:default}}
  .pg-info{{font-size:0.8rem;color:#718096}}
  table{{width:100%;border-collapse:collapse}}
  thead th{{background:#f7f8fc;font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#718096;padding:11px 14px;text-align:left;border-bottom:1px solid #e2e8f0;white-space:nowrap}}
  tbody tr{{border-bottom:1px solid #f0f0f0;transition:background .1s}}
  tbody tr:hover{{background:#fafbff}}
  tbody td{{padding:9px 14px;font-size:0.84rem}}
  .key-link{{color:#0052cc;text-decoration:none;font-weight:600}}
  .key-link:hover{{text-decoration:underline}}
  .summary-cell{{max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .date-cell{{color:#718096;white-space:nowrap}}
  .author-cell{{white-space:nowrap}}
  .arrow{{color:#a0aec0;margin:0 5px}}
  .badge{{display:inline-block;padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;white-space:nowrap}}
  .badge-created{{background:#e2e8f0;color:#4a5568}}
  .badge-planned{{background:#ebf8ff;color:#2b6cb0}}
  .badge-started{{background:#fef3c7;color:#92400e}}
  .badge-inreview{{background:#f3e8ff;color:#6b21a8}}
  .badge-accepted{{background:#d1fae5;color:#065f46}}
  .badge-canceled{{background:#fee2e2;color:#991b1b}}
  .badge-done{{background:#d1fae5;color:#065f46}}
  .badge-inprogress{{background:#fef3c7;color:#92400e}}
  .badge-todo{{background:#e2e8f0;color:#4a5568}}
  .badge-delivered{{background:#d1fae5;color:#065f46}}
  .badge-needstesting{{background:#fef9c3;color:#854d0e}}
  .badge-awaitingdep{{background:#ede9fe;color:#5b21b6}}
  .badge-testing{{background:#fef3c7;color:#92400e}}
  .badge-rejected{{background:#fee2e2;color:#991b1b}}
  .badge-waiting{{background:#f0fdf4;color:#166534}}
  .badge-default{{background:#e2e8f0;color:#4a5568}}
  .proj-badge{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:0.7rem;font-weight:700;color:white}}
  .no-data{{text-align:center;padding:40px;color:#a0aec0;font-size:0.9rem}}
</style>
</head>
<body>
<header>
  <div>
    <h1>Inveo JIRA – Status změny · Všechny projekty</h1>
    <span style="font-size:0.82rem;opacity:.75;">{date_from} – {date_to} · {len(projects)} projektů</span>
  </div>
  <div class="header-meta" id="header-meta">Načítám…</div>
</header>
<div class="container">
  <div class="kpis">
    <div class="kpi"><div class="num" id="kpi-total">–</div><div class="lbl">Celkem změn</div></div>
    <div class="kpi"><div class="num" id="kpi-tasks">–</div><div class="lbl">Unikátních tasků</div></div>
    <div class="kpi"><div class="num" id="kpi-projects">–</div><div class="lbl">Projektů</div></div>
    <div class="kpi"><div class="num" id="kpi-authors">–</div><div class="lbl">Autorů změn</div></div>
    <div class="kpi"><div class="num" id="kpi-days">–</div><div class="lbl">Dní s aktivitou</div></div>
  </div>
  <div class="filters">
    <div class="filter-group"><label>Od data</label><input type="date" id="f-from"/></div>
    <div class="filter-group"><label>Do data</label><input type="date" id="f-to"/></div>
    <div class="filter-group"><label>Projekt</label><select id="f-project"><option value="">Všechny</option></select></div>
    <div class="filter-group"><label>Autor</label><select id="f-author"><option value="">Všichni</option></select></div>
    <div class="filter-group"><label>Z&nbsp;statusu</label><select id="f-from-status"><option value="">Jakýkoliv</option></select></div>
    <div class="filter-group"><label>Do&nbsp;statusu</label><select id="f-to-status"><option value="">Jakýkoliv</option></select></div>
    <div class="filter-group"><label>Název / key</label><input type="text" id="f-summary" placeholder="fulltext…" style="min-width:180px"/></div>
    <div class="filter-group"><label>&nbsp;</label><button class="btn-reset" onclick="resetFilters()">Resetovat</button></div>
  </div>
  <div class="charts">
    <div class="card"><h2>Změny v čase (týdně)</h2><div class="chart-wrap"><canvas id="chart-timeline"></canvas></div></div>
    <div class="card"><h2>Top přechody stavů</h2><div class="chart-wrap"><canvas id="chart-transitions"></canvas></div></div>
  </div>
  <div class="charts2">
    <div class="card"><h2>Aktivita podle projektu (top 20)</h2><div class="chart-wrap-lg"><canvas id="chart-projects"></canvas></div></div>
    <div class="card"><h2>Aktivita podle autora (top 15)</h2><div class="chart-wrap-lg"><canvas id="chart-authors"></canvas></div></div>
  </div>
  <div class="table-wrap">
    <div class="table-header">
      <h2>Detail změn</h2>
      <div class="table-header-right">
        <span class="count-badge" id="table-count">0 záznamů</span>
        <div class="pagination">
          <button class="pg-btn" id="pg-prev" onclick="changePage(-1)" disabled>&#8592;</button>
          <input type="number" id="pg-input" min="1" value="1" style="width:52px;padding:3px 6px;border:1px solid #e2e8f0;border-radius:5px;font-size:0.8rem;text-align:center;"/>
          <span class="pg-info" id="pg-total">/ –</span>
          <button class="pg-btn" id="pg-next" onclick="changePage(1)">&#8594;</button>
        </div>
      </div>
    </div>
    <table>
      <thead><tr><th>Projekt</th><th>Task</th><th>Název</th><th>Datum</th><th>Autor</th><th>Přechod</th></tr></thead>
      <tbody id="table-body"></tbody>
    </table>
    <div id="no-data" class="no-data" style="display:none">Žádná data neodpovídají filtru.</div>
  </div>
</div>
<script>
const DATA_META={meta};
const RAW_DATA={raw};
const PROJECT_COLORS={proj_colors_js};
const PAGE_SIZE=100;
let currentPage=0,filtered=[],timelineChart=null,transitionsChart=null,projectsChart=null,authorsChart=null;
function projColor(p){{return PROJECT_COLORS[p]||'#718096';}}
function badgeClass(s){{
  const m={{'Created':'badge-created','Planned Today':'badge-planned','Started':'badge-started','In Review':'badge-inreview','Accepted':'badge-accepted','Canceled':'badge-canceled','Cancelled':'badge-canceled','Done':'badge-done','In Progress':'badge-inprogress','To Do':'badge-todo','Delivered':'badge-delivered','Needs testing':'badge-needstesting','Awaiting deployment':'badge-awaitingdep','Testing':'badge-testing','Rejected':'badge-rejected','Waiting':'badge-waiting','Backlog':'badge-todo','Ready to Start':'badge-todo','Selected for Development':'badge-todo','Staging Test':'badge-testing','Dev Test':'badge-testing','Icebox':'badge-todo','Billed':'badge-accepted','Offer':'badge-planned','Order':'badge-started'}};
  return m[s]||'badge-default';
}}
function badge(s){{return `<span class="badge ${{badgeClass(s)}}">${{s}}</span>`;}}
function weekKey(dateStr){{
  const p=dateStr.slice(0,10).split('-');
  const d=new Date(+p[0],+p[1]-1,+p[2]);
  const day=d.getDay();
  d.setDate(d.getDate()+(day===0?-6:1-day));
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}}
function initFilters(){{
  const projects=[...new Set(RAW_DATA.map(d=>d.project))].sort();
  const authors=[...new Set(RAW_DATA.map(d=>d.author))].sort();
  const fromSt=[...new Set(RAW_DATA.map(d=>d.fromStatus))].sort();
  const toSt=[...new Set(RAW_DATA.map(d=>d.toStatus))].sort();
  const pEl=document.getElementById('f-project');
  projects.forEach(p=>{{const o=document.createElement('option');o.value=p;o.textContent=p;pEl.appendChild(o);}});
  const aEl=document.getElementById('f-author');
  authors.forEach(a=>{{const o=document.createElement('option');o.value=a;o.textContent=a;aEl.appendChild(o);}});
  const fsEl=document.getElementById('f-from-status');
  fromSt.forEach(s=>{{const o=document.createElement('option');o.value=s;o.textContent=s;fsEl.appendChild(o);}});
  const tsEl=document.getElementById('f-to-status');
  toSt.forEach(s=>{{const o=document.createElement('option');o.value=s;o.textContent=s;tsEl.appendChild(o);}});
  document.getElementById('f-from').value=DATA_META.dateFrom;
  document.getElementById('f-to').value=DATA_META.dateTo;
  ['f-from','f-to','f-project','f-author','f-from-status','f-to-status'].forEach(id=>document.getElementById(id).addEventListener('change',applyFilters));
  document.getElementById('f-summary').addEventListener('input',applyFilters);
  document.getElementById('pg-input').addEventListener('change',function(){{goToPage(this.value);}});
  document.getElementById('pg-input').addEventListener('keydown',function(e){{if(e.key==='Enter')goToPage(this.value);}});
}}
function applyFilters(){{
  currentPage=0;
  const f={{from:document.getElementById('f-from').value,to:document.getElementById('f-to').value,project:document.getElementById('f-project').value,author:document.getElementById('f-author').value,fromStatus:document.getElementById('f-from-status').value,toStatus:document.getElementById('f-to-status').value,summary:document.getElementById('f-summary').value.trim().toLowerCase()}};
  filtered=RAW_DATA.filter(d=>{{
    const dt=d.date.slice(0,10);
    if(f.from&&dt<f.from)return false;
    if(f.to&&dt>f.to)return false;
    if(f.project&&d.project!==f.project)return false;
    if(f.author&&d.author!==f.author)return false;
    if(f.fromStatus&&d.fromStatus!==f.fromStatus)return false;
    if(f.toStatus&&d.toStatus!==f.toStatus)return false;
    if(f.summary&&!d.issueSummary.toLowerCase().includes(f.summary)&&!d.issueKey.toLowerCase().includes(f.summary))return false;
    return true;
  }});
  renderAll();
}}
function resetFilters(){{
  document.getElementById('f-from').value=DATA_META.dateFrom;
  document.getElementById('f-to').value=DATA_META.dateTo;
  ['f-project','f-author','f-from-status','f-to-status'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('f-summary').value='';
  applyFilters();
}}
function changePage(dir){{currentPage=Math.max(0,Math.min(currentPage+dir,Math.ceil(filtered.length/PAGE_SIZE)-1));renderTable();}}
function goToPage(val){{const p=parseInt(val,10);if(!isNaN(p)){{currentPage=Math.max(0,Math.min(p-1,Math.ceil(filtered.length/PAGE_SIZE)-1));renderTable();}}}}
function renderKPIs(){{
  document.getElementById('kpi-total').textContent=filtered.length.toLocaleString('cs-CZ');
  document.getElementById('kpi-tasks').textContent=new Set(filtered.map(d=>d.issueKey)).size.toLocaleString('cs-CZ');
  document.getElementById('kpi-projects').textContent=new Set(filtered.map(d=>d.project)).size;
  document.getElementById('kpi-authors').textContent=new Set(filtered.map(d=>d.author)).size;
  document.getElementById('kpi-days').textContent=new Set(filtered.map(d=>d.date.slice(0,10))).size;
}}
function renderTimeline(){{
  const weeks={{}};filtered.forEach(d=>{{const w=weekKey(d.date);weeks[w]=(weeks[w]||0)+1;}});
  const labels=Object.keys(weeks).sort();const values=labels.map(l=>weeks[l]);
  if(timelineChart)timelineChart.destroy();
  const ctx=document.getElementById('chart-timeline').getContext('2d');
  timelineChart=new Chart(ctx,{{type:'bar',data:{{labels:labels.map(l=>{{const d=new Date(l.split('-').join('/'));return `${{d.getDate()}}.${{d.getMonth()+1}}.`;}}),datasets:[{{label:'Počet změn',data:values,backgroundColor:'#0052cc',borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{title:(items)=>{{const w=labels[items[0].dataIndex];const d=new Date(w.split('-').join('/'));return `Týden od ${{d.getDate()}}.${{d.getMonth()+1}}.${{d.getFullYear()}}`;}}}}}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxTicksLimit:20}}}},y:{{beginAtZero:true}}}},onClick(evt){{const pts=timelineChart.getElementsAtEventForMode(evt,'nearest',{{intersect:true}},false);if(!pts.length)return;const ws=labels[pts[0].index];const we=new Date(ws.split('-').join('/'));we.setDate(we.getDate()+6);const es=we.getFullYear()+'-'+String(we.getMonth()+1).padStart(2,'0')+'-'+String(we.getDate()).padStart(2,'0');const fF=document.getElementById('f-from');const fT=document.getElementById('f-to');if(fF.value===ws&&fT.value===es){{fF.value=DATA_META.dateFrom;fT.value=DATA_META.dateTo;}}else{{fF.value=ws;fT.value=es;}}applyFilters();}}}}}}  );
  document.getElementById('chart-timeline').style.cursor='pointer';
}}
function renderTransitions(){{
  const trans={{}};filtered.forEach(d=>{{const k=`${{d.fromStatus}} → ${{d.toStatus}}`;trans[k]=(trans[k]||0)+1;}});
  const sorted=Object.entries(trans).sort((a,b)=>b[1]-a[1]).slice(0,8);
  const colors=['#0052cc','#36b37e','#ff5630','#6554c0','#ff8b00','#00b8d9','#57d9a3','#ff7452'];
  const aF=document.getElementById('f-from-status').value,aT=document.getElementById('f-to-status').value;
  const borders=sorted.map(s=>{{const[f,t]=s[0].split(' → ');return(f===aF&&t===aT)?'#ff8b00':'#fff';}});
  if(transitionsChart)transitionsChart.destroy();
  const ctx=document.getElementById('chart-transitions').getContext('2d');
  transitionsChart=new Chart(ctx,{{type:'doughnut',data:{{labels:sorted.map(s=>s[0]),datasets:[{{data:sorted.map(s=>s[1]),backgroundColor:colors,borderWidth:3,borderColor:borders}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'right',labels:{{font:{{size:10}},boxWidth:11}}}}}},onClick(evt){{const pts=transitionsChart.getElementsAtEventForMode(evt,'nearest',{{intersect:true}},false);if(!pts.length)return;const[fS,tS]=sorted[pts[0].index][0].split(' → ');const fF=document.getElementById('f-from-status');const fT=document.getElementById('f-to-status');if(fF.value===fS&&fT.value===tS){{fF.value='';fT.value='';}}else{{fF.value=fS;fT.value=tS;}}applyFilters();}}}}}}  );
  document.getElementById('chart-transitions').style.cursor='pointer';
}}
function renderProjects(){{
  const counts={{}};filtered.forEach(d=>{{counts[d.project]=(counts[d.project]||0)+1;}});
  const sorted=Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,20);
  const aP=document.getElementById('f-project').value;
  const bg=sorted.map(s=>{{const c=projColor(s[0]);return(!aP||s[0]===aP)?c:c+'55';}});
  if(projectsChart)projectsChart.destroy();
  const ctx=document.getElementById('chart-projects').getContext('2d');
  projectsChart=new Chart(ctx,{{type:'bar',data:{{labels:sorted.map(s=>s[0]),datasets:[{{label:'Změny',data:sorted.map(s=>s[1]),backgroundColor:bg,borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{display:false}},ticks:{{font:{{size:10}}}}}},y:{{beginAtZero:true}}}},onClick(evt){{const pts=projectsChart.getElementsAtEventForMode(evt,'nearest',{{intersect:true}},false);if(!pts.length)return;const p=sorted[pts[0].index][0];const el=document.getElementById('f-project');el.value=el.value===p?'':p;applyFilters();}}}}}}  );
  document.getElementById('chart-projects').style.cursor='pointer';
}}
function renderAuthors(){{
  const counts={{}};filtered.forEach(d=>{{counts[d.author]=(counts[d.author]||0)+1;}});
  const sorted=Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,15);
  const palette=['#0052cc','#36b37e','#6554c0','#ff8b00','#00b8d9','#ff5630','#57d9a3','#ff7452','#172b4d','#4c9aff','#2684ff','#403294','#e01e5a','#1264a3','#2eb886'];
  const aA=document.getElementById('f-author').value;
  const bg=sorted.map((s,i)=>{{const c=palette[i%palette.length];return(!aA||s[0]===aA)?c:c+'55';}});
  if(authorsChart)authorsChart.destroy();
  const ctx=document.getElementById('chart-authors').getContext('2d');
  authorsChart=new Chart(ctx,{{type:'bar',data:{{labels:sorted.map(s=>s[0].split(' ')[0]),datasets:[{{label:'Změny',data:sorted.map(s=>s[1]),backgroundColor:bg,borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{title:(items)=>sorted[items[0].dataIndex][0]}}}}}},scales:{{x:{{grid:{{display:false}},ticks:{{font:{{size:10}}}}}},y:{{beginAtZero:true}}}},onClick(evt){{const pts=authorsChart.getElementsAtEventForMode(evt,'nearest',{{intersect:true}},false);if(!pts.length)return;const a=sorted[pts[0].index][0];const el=document.getElementById('f-author');el.value=el.value===a?'':a;applyFilters();}}}}}}  );
  document.getElementById('chart-authors').style.cursor='pointer';
}}
function renderTable(){{
  const tbody=document.getElementById('table-body');
  const noData=document.getElementById('no-data');
  const totalPages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE));
  currentPage=Math.min(currentPage,totalPages-1);
  document.getElementById('table-count').textContent=`${{filtered.length.toLocaleString('cs-CZ')}} záznamů`;
  document.getElementById('pg-input').value=currentPage+1;
  document.getElementById('pg-input').max=totalPages;
  document.getElementById('pg-total').textContent=`/ ${{totalPages}}`;
  document.getElementById('pg-prev').disabled=currentPage===0;
  document.getElementById('pg-next').disabled=currentPage>=totalPages-1;
  if(filtered.length===0){{tbody.innerHTML='';noData.style.display='block';return;}}
  noData.style.display='none';
  const page=filtered.slice(currentPage*PAGE_SIZE,(currentPage+1)*PAGE_SIZE);
  tbody.innerHTML=page.map(d=>{{
    const dt=new Date(d.date);
    const ds=`${{dt.getDate()}}.${{dt.getMonth()+1}}.${{dt.getFullYear()}} ${{String(dt.getHours()).padStart(2,'0')}}:${{String(dt.getMinutes()).padStart(2,'0')}}`;
    return `<tr><td><span class="proj-badge" style="background:${{projColor(d.project)}}">${{d.project}}</span></td><td><a class="key-link" href="https://inveo-cz.atlassian.net/browse/${{d.issueKey}}" target="_blank">${{d.issueKey}}</a></td><td class="summary-cell" title="${{d.issueSummary.replace(/"/g,'&quot;')}}">${{d.issueSummary}}</td><td class="date-cell">${{ds}}</td><td class="author-cell">${{d.author}}</td><td>${{badge(d.fromStatus)}} <span class="arrow">→</span> ${{badge(d.toStatus)}}</td></tr>`;
  }}).join('');
}}
function renderAll(){{renderKPIs();renderTimeline();renderTransitions();renderProjects();renderAuthors();renderTable();}}
initFilters();applyFilters();
(function(){{
  const el=document.getElementById('header-meta');
  if(!el||!DATA_META)return;
  const d=new Date(DATA_META.lastUpdated);
  const fmt=d.toLocaleString('cs-CZ',{{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}});
  el.textContent=`Aktualizováno: ${{fmt}} · ${{DATA_META.taskCount.toLocaleString('cs-CZ')}} tasků · ${{DATA_META.recordCount.toLocaleString('cs-CZ')}} změn`;
}})();
</script>
</body>
</html>"""

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    issues = fetch_issues_with_status_change()
    data   = fetch_all_changes(issues)

    print(f"\nCelkem status změn: {len(data)}")
    print(f"Unikátních tasků:   {len(set(d['issueKey'] for d in data))}")
    print(f"Projektů:           {len(set(d['project'] for d in data))}")

    html = build_html(data, DATE_FROM_STR, DATE_TO_STR)

    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nDashboard uložen: {out_path} ({len(html)//1024} KB)")
