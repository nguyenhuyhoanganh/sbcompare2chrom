"""Self-contained HTML dashboard.

Markdown is right for a ticket; a triage list of several hundred rows needs
filtering and sorting to be usable at all. This emits one file with the data
embedded -- no CDN, no build step, no server -- so it can be attached to a mail
thread or dropped on an internal share and still work.
"""

from __future__ import annotations

import html
import json
from typing import List

from ..diff import SIGNAL_LABELS
from ..model import BUCKET_LABELS, BUCKET_ORDER, KIND_GROUPS, KIND_LABELS, Report
from . import markdown as md_report

_CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a19;--muted:#6b6b66;--line:#e3e2df;--card:#fff;
--must:#b4342a;--review:#a86a12;--opp:#2f6b45;--fyi:#6b6b66;--accent:#2b5fa8;}
:root:not([data-theme=light]) {}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#191918;--fg:#eceae5;--muted:#9a978f;--line:#302f2c;--card:#211f1e;
--must:#f08076;--review:#e0aa52;--opp:#7cc397;--fyi:#9a978f;--accent:#7aa8e8;}}
:root[data-theme=dark]{--bg:#191918;--fg:#eceae5;--muted:#9a978f;--line:#302f2c;
--card:#211f1e;--must:#f08076;--review:#e0aa52;--opp:#7cc397;--fyi:#9a978f;--accent:#7aa8e8;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;}
.wrap{max-width:1180px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:1.55rem;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:1.1rem;margin:36px 0 12px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:.9rem;margin-bottom:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.card .n{font-size:1.8rem;font-weight:600;line-height:1.1;font-variant-numeric:tabular-nums}
.card .l{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.05em}
.card.must .n{color:var(--must)}.card.review .n{color:var(--review)}
.card.opportunity .n{color:var(--opp)}.card.fyi .n{color:var(--fyi)}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 14px;align-items:center}
input[type=search],select{background:var(--card);color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:7px 10px;font:inherit;font-size:.88rem}
input[type=search]{flex:1;min-width:200px}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
/* table-layout:fixed is the single biggest lever here. With the default auto
   layout, column widths depend on cell content, so inserting one expanded row
   makes the browser re-measure every cell in the table before it can paint.
   Fixed layout takes the widths from the colgroup and never looks at content,
   so expanding a row costs the row instead of the table. border-collapse also
   moves off `collapse`, whose border resolution is measurably slower. */
table{border-collapse:separate;border-spacing:0;table-layout:fixed;width:100%;
font-size:.88rem;min-width:860px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);
vertical-align:top;overflow-wrap:anywhere}
th{font-weight:600;color:var(--muted);font-size:.78rem;text-transform:uppercase;
letter-spacing:.04em;cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:0;
background:var(--card)}
tbody tr:last-child td{border-bottom:none}
tbody tr.det td{background:color-mix(in srgb,var(--card) 92%,var(--fg));font-size:.85rem}
/* Rows outside the viewport skip layout entirely; the intrinsic size keeps the
   scrollbar honest so skipping does not make the page jump. */
tbody tr{content-visibility:auto;contain-intrinsic-size:auto 38px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86em}
.score{font-variant-numeric:tabular-nums;font-weight:600}
.pill{display:inline-block;padding:1px 7px;border-radius:99px;font-size:.74rem;
border:1px solid currentColor;white-space:nowrap}
.b-must_fix{color:var(--must)}.b-review{color:var(--review)}
.b-opportunity{color:var(--opp)}.b-fyi{color:var(--fyi)}
.muted{color:var(--muted)}
tbody tr.row{cursor:pointer}
tbody tr.row:hover td{background:color-mix(in srgb,var(--card) 88%,var(--accent))}
ul.tight{margin:6px 0;padding-left:18px}
.empty{padding:28px;text-align:center;color:var(--muted)}
.note{background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:10px 14px;margin:14px 0;font-size:.87rem;color:var(--muted)}
#more{margin-top:12px;width:100%;padding:10px;background:var(--card);color:var(--fg);
border:1px solid var(--line);border-radius:8px;font:inherit;font-size:.88rem;cursor:pointer}
#more:hover{background:color-mix(in srgb,var(--card) 88%,var(--accent))}
"""

_JS = """
/* Rendering is windowed, lazy and delegated, because a full uprev is thousands
   of findings and the obvious implementation makes the page unusable.
   Measured on a real 3,120-finding report, the previous version rebuilt 1.79 MB
   of HTML and 6,240 <tr> nodes on EVERY keystroke -- 48% of it detail markup for
   rows that were hidden -- then re-attached 3,120 click listeners. Typing one
   word froze the tab. */
const DATA=window.__FINDINGS__||[];
/* Labels are looked up, not repeated. Ten kind labels and four bucket labels
   stored once each instead of once per finding: 188 KB on a 3,120-row report. */
const KINDS=window.__KINDS__||{},BUCKETS=window.__BUCKETS__||{};
const kindLabel=f=>KINDS[f.kind]||f.kind, bucketLabel=f=>BUCKETS[f.bucket]||f.bucket;
/* Sized for the weakest machine that has to open this, not the fastest.
   A work laptop rendering 200 rows of a collapsed-border auto-layout table was
   the original "not responding"; 100 with fixed layout is comfortable, and the
   search box is the real navigation tool anyway. */
const PAGE=100;
const q=document.getElementById('q'),fb=document.getElementById('fb'),
fk=document.getElementById('fk'),fa=document.getElementById('fa'),
tb=document.getElementById('tb'),cnt=document.getElementById('cnt'),
more=document.getElementById('more');
let sortKey='score',sortDir=-1,shown=PAGE,view=DATA;
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function match(f,t){
  if(fb.value&&f.bucket!==fb.value)return false;
  if(fk.value&&f.kind!==fk.value)return false;
  if(fa.value){
    if(fa.value==='__none__'){ if((f.areas||[]).length) return false; }
    else if(!(f.areas||[]).includes(fa.value)) return false;
  }
  if(!t)return true;
  if(f._hay===undefined)
    f._hay=(f.name+' '+f.kind+' '+(f.signals||[]).join(' ')+' '+(f.paths||[]).join(' ')
      +' '+(f.we_ref||[]).join(' ')+' '+(f.chromestatus||'')).toLowerCase();
  return f._hay.indexOf(t)!==-1;
}
/* Built only when a row is actually expanded. This was half the payload. */
function details(f){
  const L=[];
  if(f.signals&&f.signals.length)L.push('<li><b>Signals:</b> '+esc(f.signals.join(', '))+'</li>');
  if(f.paths&&f.paths.length)L.push('<li><b>Declared in:</b> <code>'+esc(f.paths.join(', '))+'</code></li>');
  if(f.we_patch&&f.we_patch.length)L.push('<li><b>We patch:</b> <code>'+esc(f.we_patch.join(', '))+'</code></li>');
  if(f.we_ref&&f.we_ref.length)L.push('<li><b>We reference:</b> <code>'+esc(f.we_ref.join(', '))+'</code></li>');
  (f.deltas||[]).forEach(d=>L.push('<li><b>'+esc(d[0])+':</b> <code>'+esc(d[1])+'</code> \\u2192 <code>'+esc(d[2])+'</code></li>'));
  if(f.chromestatus)L.push('<li><b>Chromestatus:</b> '+esc(f.chromestatus)+'</li>');
  if(f.reasons&&f.reasons.length)L.push('<li class="muted"><b>Score:</b> '+esc(f.reasons.join(' \\u00b7 '))+'</li>');
  return '<ul class="tight">'+L.join('')+'</ul>';
}
function rowHtml(f,i){
  return '<tr class="row" data-i="'+i+'"><td class="score">'+f.score+'</td>'+
    '<td><span class="pill b-'+f.bucket+'">'+esc(bucketLabel(f))+'</span></td>'+
    '<td><code>'+esc(f.name)+'</code></td>'+
    '<td class="muted">'+esc(kindLabel(f))+'</td>'+
    '<td>'+esc(f.moved||'')+'</td>'+
    '<td>'+esc((f.we_ref||f.we_patch||[]).join(', '))+'</td></tr>';
}
function paint(){
  const slice=view.slice(0,shown);
  cnt.textContent=(view.length?('showing '+slice.length+' of '+view.length):'0')+
    ' \\u00b7 '+DATA.length+' total';
  if(!view.length){
    tb.innerHTML='<tr><td colspan="6" class="empty">No findings match.</td></tr>';
    more.hidden=true;return;
  }
  tb.innerHTML=slice.map(rowHtml).join('');
  more.hidden=shown>=view.length;
  more.textContent='Show '+Math.min(PAGE,view.length-shown)+' more ('+
    (view.length-shown)+' hidden)';
}
/* Sorting reads the displayed value, not the stored one: the Surface column
   shows a label that is looked up, so sorting on the raw kind would order the
   rows differently from how they read. */
function sortVal(f){
  if(sortKey==='kind')return kindLabel(f);
  if(sortKey==='bucket')return bucketLabel(f);
  return f[sortKey];
}
function apply(){
  const t=q.value.trim().toLowerCase();
  view=DATA.filter(f=>match(f,t));
  view.sort((a,b)=>{
    const x=sortVal(a),y=sortVal(b);
    if(typeof x==='number'&&typeof y==='number')return (x-y)*sortDir;
    return String(x||'').localeCompare(String(y||''))*sortDir;});
  shown=PAGE;paint();
}
/* One listener for the whole table instead of one per row. */
tb.addEventListener('click',e=>{
  const tr=e.target.closest('tr.row'); if(!tr)return;
  const next=tr.nextElementSibling;
  if(next&&next.classList.contains('det')){next.remove();return;}
  const f=view[+tr.dataset.i]; if(!f)return;
  const det=document.createElement('tr');
  det.className='det';
  det.innerHTML='<td colspan="6">'+details(f)+'</td>';
  tr.after(det);
});
more.addEventListener('click',()=>{shown+=PAGE;paint();});
document.querySelectorAll('th[data-k]').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.k; sortDir=(k===sortKey)?-sortDir:(k==='score'?-1:1); sortKey=k; apply();}));
/* Debounced: typing "network" used to run the whole pipeline seven times. */
let timer=null;
q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,140);});
[fb,fk,fa].forEach(el=>el&&el.addEventListener('change',apply));
apply();
"""


def _moved(finding_dict: dict) -> str:
    for key, old, new in finding_dict.get("deltas", []):
        if key in ("platform_state", "platform_status"):
            continue
        return f"{old} → {new}"
    return finding_dict.get("change_type", "")


def _to_rows(report: Report, platform: str) -> List[dict]:
    rows = []
    for finding in report.findings:
        change = finding.change
        deltas = []
        for key, delta in sorted(change.deltas.items()):
            if not (isinstance(delta, list) and len(delta) == 2):
                continue
            if key in ("platform_state", "platform_status"):
                old = delta[0].get(platform, "?") if isinstance(delta[0], dict) else "?"
                new = delta[1].get(platform, "?") if isinstance(delta[1], dict) else "?"
                if old == new:
                    continue
                deltas.append([f"{key} [{platform}]", str(old), str(new)])
            else:
                deltas.append([key, _trim(delta[0]), _trim(delta[1])])
        status = (finding.enrichment or {}).get("chromestatus") or {}
        row = {
            "id": finding.uid,
            "name": md_report.display_name(change),
            "kind": change.kind,
            "change_type": change.change_type,
            "bucket": finding.bucket,
            "score": finding.score,
            "signals": [SIGNAL_LABELS.get(s, s) for s in change.signals],
            "paths": change.paths[:3],
            "we_patch": finding.matched_paths[:5],
            "we_ref": finding.matched_symbols[:8],
            "areas": finding.areas,
            "deltas": deltas[:6],
            "reasons": finding.reasons,
            "chromestatus": status.get("summary", ""),
        }
        row["moved"] = _moved(row)
        # Drop empty values. Every consumer in the page already guards for a
        # missing key (`f.signals||[]`, `f.we_ref||[]`), and on a run without a
        # profile or without enrichment these are empty on every single row:
        # measured at 3,120 findings, chromestatus/we_patch/we_ref were empty
        # 3,120 times each. Carrying them costs a fifth of the payload to say
        # nothing.
        rows.append({k: v for k, v in row.items() if v not in ("", [], {}, None)})
    return rows


def _trim(value, limit: int = 90) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) \
        else ("(absent)" if value is None else str(value))
    return text if len(text) <= limit else text[:limit] + "…"


def render(report: Report, platform: str = "windows") -> str:
    rows = _to_rows(report, platform)
    counts = report.bucket_counts()
    meta = report.meta or {}

    kinds = sorted({r["kind"] for r in rows})
    areas = sorted({a for r in rows for a in r.get("areas", [])})
    unassigned_count = sum(1 for r in rows if not r.get("areas"))

    cards = "".join(
        f'<div class="card {b.replace("must_fix","must")}">'
        f'<div class="n">{counts.get(b,0)}</div>'
        f'<div class="l">{html.escape(BUCKET_LABELS[b])}</div></div>'
        for b in BUCKET_ORDER
    )

    mode = md_report.mode_of(report)
    notes = []
    subtitle = md_report.MODE_SUBTITLES.get(mode)
    if subtitle:
        notes.append(html.escape(subtitle.replace("**", "").replace("*", "")))
    profile = meta.get("profile") or {}
    if profile and not profile.get("paths_total") and not profile.get("symbols_total"):
        notes.append("No downstream evidence was supplied, so nothing can land in "
                     "<b>Must fix</b>. Point the profile at your patch directory or fork.")
    notes_html = "".join(f'<div class="note">{n}</div>' for n in notes)

    option = lambda v, label="": f'<option value="{html.escape(v)}">{html.escape(label or v)}</option>'

    # Grouped, because a flat list of thirteen kinds reads as thirteen kinds of
    # "feature" -- and two thirds of them are not features at all. The groups
    # say which is which without needing a legend.
    surface_options = ""
    for group_name, group_kinds in KIND_GROUPS:
        present = [k for k in group_kinds if k in kinds]
        if not present:
            continue
        surface_options += f'<optgroup label="{html.escape(group_name)}">'
        surface_options += "".join(option(k, KIND_LABELS.get(k, k)) for k in present)
        surface_options += "</optgroup>"

    return f"""<title>{html.escape(md_report.MODE_TITLES[mode])}</title>
<style>{_CSS}</style>
<div class="wrap">
<h1>{html.escape(md_report.MODE_TITLES[mode])}</h1>
<div class="sub"><code>{html.escape(report.from_ref)}</code> →
<code>{html.escape(report.to_ref)}</code> ·
{html.escape(str(meta.get('product','downstream browser')))} ·
platform {html.escape(platform)} · {html.escape(str(meta.get('generated','')))}</div>
{notes_html}
<div class="cards">{cards}</div>
<h2>Findings</h2>
<div class="controls">
<input type="search" id="q" placeholder="Search name, signal, path, symbol…">
<select id="fb"><option value="">All buckets</option>
{''.join(option(b, BUCKET_LABELS[b]) for b in BUCKET_ORDER)}</select>
<select id="fk"><option value="">All surfaces</option>
{surface_options}</select>
<select id="fa"><option value="">All areas</option>
{''.join(option(a) for a in areas)}
{option("__none__", f"(no area) — {unassigned_count}") if unassigned_count else ""}</select>
<span class="muted" id="cnt"></span>
</div>
<div class="tablewrap"><table>
<colgroup><col style="width:64px"><col style="width:116px"><col style="width:28%">
<col style="width:170px"><col><col style="width:20%"></colgroup>
<thead><tr>
<th data-k="score">Score</th><th data-k="bucket">Bucket</th>
<th data-k="name">Change</th><th data-k="kind">Surface</th>
<th data-k="moved">What moved</th><th data-k="we_ref">We reference</th>
</tr></thead><tbody id="tb"></tbody></table></div>
<button id="more" hidden></button>
<p class="muted" style="margin-top:10px;font-size:.85rem">Click a row for evidence
and score reasoning. Rows render in pages of 100 &mdash; the JSON below holds every
finding regardless of what is on screen.</p>
</div>
<script>window.__FINDINGS__={json.dumps(rows, ensure_ascii=False)};
window.__KINDS__={json.dumps(KIND_LABELS, ensure_ascii=False)};
window.__BUCKETS__={json.dumps(BUCKET_LABELS, ensure_ascii=False)};</script>
<script>{_JS}</script>
"""
