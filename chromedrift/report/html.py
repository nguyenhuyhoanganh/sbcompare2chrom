"""Self-contained HTML dashboard.

Markdown is right for a ticket; a triage list of several hundred rows needs
filtering and sorting to be usable at all. This emits one file with the data
embedded -- no CDN, no build step, no server -- so it can be attached to a mail
thread or dropped on an internal share and still work.

The page is a small app rather than a long document, because the readers are
teams and no team wants to scroll through another team's rows to reach its own.
A menu across the top picks the kind of thing -- feature flags, web APIs,
process calls, settings, `chrome://` screens, the flags page -- and only that
pane is on screen. Down the left of each pane are its subdivisions: first the
three every team asks for, **new / changed / gone**, then what actually
happened, in the diff engine's own sentences. `chrome://` screens subdivide by
page instead, because a page is the unit a UI team owns.

The layout before this one had the same content on one long page: eighty
collapsed bars, three sections deep, before the reader reached anything
readable. The sentences were right and the shape was wrong -- a signal label
annotates one row well and heads eighty badly. Nothing was dropped here; it was
put behind a menu.

Every row in every pane is also in the last tab's table, and the numbers always
agree, because both are built from the same findings.
"""

from __future__ import annotations

import html
import json
from typing import Dict, List, Sequence

from ..diff import SIGNAL_LABELS
from ..model import (ADDED, BUCKET_LABELS, BUCKET_MUST_FIX, BUCKET_ORDER,
                     BUCKET_REVIEW, KIND_GROUPS, KIND_LABELS, MODIFIED,
                     REMOVED, Report, group_of)
from . import markdown as md_report
from . import wording as surfaces

_CSS = """
:root{
--bg:#fbfbfa;--fg:#1a1a19;--muted:#6b6b66;--faint:#8f8d87;
--line:#e6e4e0;--card:#fff;--sunk:#f4f3f0;
--must:#b4342a;--review:#a86a12;--opp:#2f6b45;--fyi:#6b6b66;--accent:#2b5fa8;
--new:#2f6b45;--chg:#a86a12;--gone:#b4342a;
--radius:10px;
--shadow:0 1px 2px rgba(20,18,14,.05),0 1px 8px rgba(20,18,14,.04);
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#191918;--fg:#eceae5;--muted:#9a978f;--faint:#807d76;
--line:#333230;--card:#211f1e;--sunk:#1e1c1b;
--must:#f08076;--review:#e0aa52;--opp:#7cc397;--fyi:#9a978f;--accent:#7aa8e8;
--new:#7cc397;--chg:#e0aa52;--gone:#f08076;
--shadow:0 1px 2px rgba(0,0,0,.3),0 1px 8px rgba(0,0,0,.2);}}
:root[data-theme=dark]{
--bg:#191918;--fg:#eceae5;--muted:#9a978f;--faint:#807d76;
--line:#333230;--card:#211f1e;--sunk:#1e1c1b;
--must:#f08076;--review:#e0aa52;--opp:#7cc397;--fyi:#9a978f;--accent:#7aa8e8;
--new:#7cc397;--chg:#e0aa52;--gone:#f08076;
--shadow:0 1px 2px rgba(0,0,0,.3),0 1px 8px rgba(0,0,0,.2);}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:1300px;margin:0 auto;padding:0 20px 70px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86em}
.muted{color:var(--muted)}
[hidden]{display:none !important}

/* -- masthead ------------------------------------------------------------ */
.top{padding:24px 0 14px}
.eyebrow{font-size:.75rem;letter-spacing:.09em;text-transform:uppercase;
color:var(--muted);font-weight:600}
h1{font-size:1.4rem;margin:6px 0 5px;letter-spacing:-.015em;line-height:1.25}
h1 .arrow{color:var(--muted);font-weight:400;padding:0 .2em}
.sub{color:var(--muted);font-size:.85rem}

/* -- top menu ------------------------------------------------------------ */
/* Sticky, because it is the only navigation: every pane below is one of these
   and nothing scrolls between them. */
.menu{position:sticky;top:0;z-index:6;display:flex;gap:1px;align-items:stretch;
overflow-x:auto;background:var(--bg);border-bottom:1px solid var(--line);
margin:0 -20px 20px;padding:0 20px;scrollbar-width:thin}
.menu button{appearance:none;background:none;border:0;
border-bottom:2px solid transparent;color:var(--muted);font:inherit;
font-size:.88rem;padding:11px 12px 9px;cursor:pointer;white-space:nowrap;
display:flex;gap:7px;align-items:baseline}
.menu button:hover{color:var(--fg)}
.menu button.on{color:var(--fg);border-bottom-color:var(--accent);font-weight:600}
.menu button b{font-weight:600;font-variant-numeric:tabular-nums;
color:var(--faint);font-size:.79rem}
.menu .last{border-left:1px solid var(--line);margin-left:8px;padding-left:14px}
.menu .who{align-self:center;font-size:.68rem;letter-spacing:.09em;
text-transform:uppercase;color:var(--faint);padding:0 9px 0 14px;
border-left:1px solid var(--line);margin-left:5px;white-space:nowrap}

/* -- pane head ----------------------------------------------------------- */
.panehead{margin:0 0 15px}
.panehead h2{font-size:1.14rem;margin:0 0 4px;letter-spacing:-.01em}
.panehead p{color:var(--muted);font-size:.89rem;margin:0;max-width:80ch}

/* -- triage -------------------------------------------------------------- */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
padding:14px 16px;box-shadow:var(--shadow);display:block;color:inherit;
border-left:3px solid var(--line);text-align:left;font:inherit;cursor:pointer;
width:100%}
.card:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
.card .n{font-size:1.85rem;font-weight:600;line-height:1.15;
font-variant-numeric:tabular-nums}
.card .l{font-size:.82rem;font-weight:600}
.card .m{color:var(--muted);font-size:.79rem;margin-top:5px;line-height:1.45}
.card.must{border-left-color:var(--must)}.card.must .n{color:var(--must)}
.card.review{border-left-color:var(--review)}.card.review .n{color:var(--review)}
.card.opportunity{border-left-color:var(--opp)}.card.opportunity .n{color:var(--opp)}
.card.fyi .n{color:var(--fyi)}

/* -- overview map -------------------------------------------------------- */
.map{width:100%;border-collapse:separate;border-spacing:0;margin-top:14px;
background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
overflow:hidden;box-shadow:var(--shadow)}
.map th,.map td{padding:10px 14px;border-bottom:1px solid var(--line);
text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.map th{font-size:.71rem;text-transform:uppercase;letter-spacing:.05em;
color:var(--muted);font-weight:600;background:var(--sunk)}
.map th:first-child,.map td:first-child{text-align:left;
font-variant-numeric:normal;white-space:normal}
.map tr:last-child td{border-bottom:0}
.map tbody tr:hover td{background:var(--sunk)}
.map .go{background:none;border:0;font:inherit;color:var(--fg);cursor:pointer;
padding:0;text-align:left;font-weight:600}
.map .go:hover{color:var(--accent)}
.map .go small{display:block;font-weight:400;color:var(--muted);font-size:.78rem;
max-width:56ch;line-height:1.4;margin-top:2px;white-space:normal}
.map .team{font-size:.68rem;letter-spacing:.07em;text-transform:uppercase;
color:var(--faint);font-weight:600;background:var(--sunk)}
.m-added{color:var(--new)}.m-modified{color:var(--chg)}.m-removed{color:var(--gone)}

/* -- two-pane body ------------------------------------------------------- */
.split{display:grid;grid-template-columns:minmax(196px,262px) minmax(0,1fr);
gap:18px;align-items:start}
@media (max-width:860px){.split{grid-template-columns:1fr}
.side{position:static;max-height:none}}
.side{display:flex;flex-direction:column;gap:1px;position:sticky;top:54px;
max-height:calc(100vh - 74px);overflow-y:auto;scrollbar-width:thin;
padding-right:4px}
.side button{appearance:none;background:none;border:0;border-radius:7px;
font:inherit;font-size:.86rem;text-align:left;padding:6px 9px;cursor:pointer;
color:var(--muted);display:flex;gap:8px;align-items:baseline;width:100%;
line-height:1.35}
.side button:hover{background:var(--sunk);color:var(--fg)}
.side button.on{background:var(--sunk);color:var(--fg);font-weight:600;
box-shadow:inset 2px 0 0 var(--accent)}
.side button .n{margin-left:auto;font-variant-numeric:tabular-nums;
font-size:.78rem;color:var(--faint);font-weight:400;padding-left:6px}
.side .dot{flex:0 0 7px;height:7px;border-radius:50%;align-self:center}
.d-added{background:var(--new)}.d-modified{background:var(--chg)}
.d-removed{background:var(--gone)}
.d-3{background:var(--must)}.d-2{background:var(--review)}
.d-1{background:var(--accent)}.d-0{background:var(--line)}
.side .lbl{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;
color:var(--faint);font-weight:600;padding:4px 9px 5px}
.side .lbl+*{margin-top:0}
.side .lbl:not(:first-child){padding-top:16px}

/* -- rows ---------------------------------------------------------------- */
.rows{background:var(--card);border:1px solid var(--line);
border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
.rowhead{padding:12px 16px;border-bottom:1px solid var(--line);
background:var(--sunk)}
.rowhead b{font-size:.95rem}
.rowhead span{color:var(--muted);font-size:.85rem;margin-left:8px}
.rowhead p{margin:5px 0 0;color:var(--muted);font-size:.84rem;max-width:84ch}
.row{display:flex;gap:10px;align-items:baseline;padding:7px 16px;
border-bottom:1px solid var(--line);font-size:.89rem}
.row:last-child{border-bottom:0}
.row .mk{flex:0 0 1em;text-align:center;font-weight:700}
.mk-added{color:var(--new)}.mk-removed{color:var(--gone)}.mk-modified{color:var(--chg)}
.row .what{flex:1 1 26ch;min-width:0;overflow-wrap:anywhere}
.row .kw{color:var(--faint);font-size:.79rem}
.row .why{flex:0 1 32ch;color:var(--muted);font-size:.8rem;text-align:right;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .sc{flex:0 0 3.2em;text-align:right;color:var(--faint);font-size:.79rem;
font-variant-numeric:tabular-nums}
.row .tag{font-size:.67rem;border:1px solid currentColor;border-radius:99px;
padding:0 6px;white-space:nowrap;vertical-align:1px;margin-left:6px}
.t-must_fix{color:var(--must)}.t-review{color:var(--review)}
.t-ours{color:var(--accent)}
.subhead{padding:9px 16px 5px;font-size:.72rem;letter-spacing:.07em;
text-transform:uppercase;color:var(--muted);font-weight:600;
background:var(--sunk);border-bottom:1px solid var(--line)}
.more-note{color:var(--muted);font-size:.83rem;margin:10px 0 0}
.empty{padding:28px;text-align:center;color:var(--muted)}

/* -- table --------------------------------------------------------------- */
.controls{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;align-items:center}
input[type=search],select{background:var(--card);color:var(--fg);
border:1px solid var(--line);border-radius:7px;padding:7px 10px;font:inherit;
font-size:.87rem}
input[type=search]{flex:1;min-width:210px}
/* Its own scroll box, so the column headers stay put: a sticky <th> sticks to
   the nearest scrollport, and the wrapper is already one because overflow-x
   makes overflow-y a scroll container too. */
.tablewrap{overflow:auto;max-height:min(72vh,800px);border:1px solid var(--line);
border-radius:var(--radius);background:var(--card);box-shadow:var(--shadow)}
/* table-layout:fixed is the single biggest lever here. With the default auto
   layout, column widths depend on cell content, so inserting one expanded row
   makes the browser re-measure every cell before it can paint. Fixed layout
   takes the widths from the colgroup and never looks at content. */
table.find{border-collapse:separate;border-spacing:0;table-layout:fixed;
width:100%;font-size:.87rem;min-width:940px}
table.find th,table.find td{text-align:left;padding:9px 12px;
border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
table.find th{font-weight:600;color:var(--muted);font-size:.75rem;
text-transform:uppercase;letter-spacing:.05em;cursor:pointer;user-select:none;
white-space:nowrap;position:sticky;top:0;z-index:1;background:var(--card);
box-shadow:inset 0 -1px 0 var(--line)}
table.find th:hover{color:var(--fg)}
table.find tbody tr:last-child td{border-bottom:none}
tbody tr.det td{background:var(--sunk);font-size:.85rem}
/* Rows outside the viewport skip layout entirely; the intrinsic size keeps the
   scrollbar honest so skipping does not make the page jump. */
table.find tbody tr{content-visibility:auto;contain-intrinsic-size:auto 40px}
tbody tr.row-t{cursor:pointer}
tbody tr.row-t:hover td{background:color-mix(in srgb,var(--card) 88%,var(--accent))}
.score{font-variant-numeric:tabular-nums;font-weight:600}
.pill{display:inline-block;padding:1px 7px;border-radius:99px;font-size:.73rem;
border:1px solid currentColor;white-space:nowrap}
.b-must_fix{color:var(--must)}.b-review{color:var(--review)}
.b-opportunity{color:var(--opp)}.b-fyi{color:var(--fyi)}
.chg{font-size:.73rem;padding:1px 8px;border-radius:99px;white-space:nowrap;
font-weight:600}
.c-added{background:color-mix(in srgb,var(--new) 15%,transparent);color:var(--new)}
.c-removed{background:color-mix(in srgb,var(--gone) 15%,transparent);color:var(--gone)}
.c-modified{background:color-mix(in srgb,var(--chg) 15%,transparent);color:var(--chg)}
.where{color:var(--muted);font-size:.83rem}
.grp{font-size:.72rem;color:var(--faint);margin-top:2px}
.moved{font-size:.78rem;color:var(--muted);margin-top:2px}
.ours{font-size:.68rem;border:1px solid var(--accent);color:var(--accent);
border-radius:99px;padding:0 6px;white-space:nowrap;vertical-align:1px}
ul.tight{margin:6px 0;padding-left:18px}
.note{background:var(--card);border:1px solid var(--line);border-radius:8px;
border-left:3px solid var(--review);padding:10px 14px;margin:0 0 14px;
font-size:.87rem;color:var(--muted)}
#more{margin-top:12px;width:100%;padding:10px;background:var(--card);
color:var(--fg);border:1px solid var(--line);border-radius:8px;font:inherit;
font-size:.87rem;cursor:pointer}
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
/* Labels are looked up, not repeated. Ten kind labels, four bucket labels and
   about forty story sentences stored once each instead of once per finding. */
const KINDS=window.__KINDS__||{},BUCKETS=window.__BUCKETS__||{},
STORIES=window.__STORIES__||{};
const kindLabel=f=>KINDS[f.kind]||f.kind, bucketLabel=f=>BUCKETS[f.bucket]||f.bucket,
whyLabel=f=>STORIES[f.why]||f.why||'';
/* Sized for the weakest machine that has to open this, not the fastest. */
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
    f._hay=(f.name+' '+f.kind+' '+(f.what||'')+' '+(f.where||'')+' '+whyLabel(f)+' '
      +(f.signals||[]).join(' ')+' '+(f.paths||[]).join(' ')
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
var CHG={added:'new',removed:'gone',modified:'changed'};
function whatCell(f){
  var out=f.what?esc(f.what):'<code>'+esc(f.name)+'</code>';
  if(f.ours) out+=' <span class="ours">ours</span>';
  if(f.moved) out+='<div class="moved">'+esc(f.moved)+'</div>';
  return out;
}
function surfaceCell(f){
  var out=esc(kindLabel(f));
  if(f.group) out+='<div class="grp">'+esc(f.group)+'</div>';
  return out;
}
function rowHtml(f,i){
  const c=f.change_type||'';
  return '<tr class="row-t" data-i="'+i+'"><td class="score">'+f.score+'</td>'+
    '<td><span class="chg c-'+c+'">'+esc(CHG[c]||c)+'</span></td>'+
    '<td><span class="pill b-'+f.bucket+'">'+esc(bucketLabel(f))+'</span></td>'+
    '<td>'+whatCell(f)+'</td>'+
    '<td>'+esc(whyLabel(f))+'</td>'+
    '<td class="where">'+esc(f.where||'')+'</td>'+
    '<td class="muted">'+surfaceCell(f)+'</td></tr>';
}
function paint(){
  const slice=view.slice(0,shown);
  cnt.textContent=(view.length?('showing '+slice.length+' of '+view.length):'0')+
    ' \\u00b7 '+DATA.length+' total';
  if(!view.length){
    tb.innerHTML='<tr><td colspan="7" class="empty">No findings match.</td></tr>';
    more.hidden=true;return;
  }
  tb.innerHTML=slice.map(rowHtml).join('');
  more.hidden=shown>=view.length;
  more.textContent='Show '+Math.min(PAGE,view.length-shown)+' more ('+
    (view.length-shown)+' hidden)';
}
/* Sorting reads the displayed value, not the stored one: Surface and What
   happened show labels that are looked up. */
function sortVal(f){
  if(sortKey==='kind')return kindLabel(f);
  if(sortKey==='bucket')return bucketLabel(f);
  if(sortKey==='why')return whyLabel(f);
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
  const tr=e.target.closest('tr.row-t'); if(!tr)return;
  const next=tr.nextElementSibling;
  if(next&&next.classList.contains('det')){next.remove();return;}
  const f=view[+tr.dataset.i]; if(!f)return;
  const det=document.createElement('tr');
  det.className='det';
  det.innerHTML='<td colspan="7">'+details(f)+'</td>';
  tr.after(det);
});
more.addEventListener('click',()=>{shown+=PAGE;paint();});
document.querySelectorAll('th[data-k]').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.k; sortDir=(k===sortKey)?-sortDir:(k==='score'?-1:1); sortKey=k; apply();}));

/* -- navigation -----------------------------------------------------------
   Every pane is server-rendered and already in the document; the menu only
   decides which one is on screen. Written against querySelectorAll and data
   attributes rather than element ids, so it is inert -- not broken -- in the
   fake DOM the table's own performance tests run against. */
function show(tab){
  document.querySelectorAll('[data-tab]').forEach(function(b){
    b.classList.toggle('on',b.dataset.tab===tab);});
  document.querySelectorAll('[data-pane]').forEach(function(p){
    p.hidden=(p.dataset.pane!==tab);});
  window.scrollTo(0,0);
}
function pick(sub){
  var tab=sub.split('/')[0];
  document.querySelectorAll('[data-sub]').forEach(function(b){
    if(b.dataset.sub.split('/')[0]===tab)
      b.classList.toggle('on',b.dataset.sub===sub);});
  document.querySelectorAll('[data-subpane]').forEach(function(p){
    if(p.dataset.subpane.split('/')[0]===tab)
      p.hidden=(p.dataset.subpane!==sub);});
}
document.querySelectorAll('[data-tab]').forEach(function(b){
  b.addEventListener('click',function(){
    show(b.dataset.tab);
    if(b.dataset.go) pick(b.dataset.go);});});
document.querySelectorAll('[data-sub]').forEach(function(b){
  b.addEventListener('click',function(){pick(b.dataset.sub);});});
/* A count is only useful if it takes you to the rows it counted, so every
   triage card carries the filter it stands for. */
document.querySelectorAll('[data-set]').forEach(function(el){
  el.addEventListener('click',function(){
    var p=el.dataset.set.split(':'),sel={fb:fb,fk:fk,fa:fa}[p[0]];
    if(!sel)return;
    fb.value='';fk.value='';fa.value='';
    sel.value=p.slice(1).join(':');
    apply();show('all');});});
/* Debounced: typing "network" used to run the whole pipeline seven times. */
let timer=null;
q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,140);});
[fb,fk,fa].forEach(el=>el&&el.addEventListener('change',apply));
apply();
"""


# ---------------------------------------------------------------------------
# The findings payload behind the table
# ---------------------------------------------------------------------------

def _moved(finding_dict: dict, limit: int = 34) -> str:
    """"100 -> 109", for the second line of the What cell.

    Short by design. A Mojo signature runs past 400 characters, and pasted into
    a fixed-layout table cell it wraps to six lines and pushes every other row
    off the screen -- for a value the reader can get in full by opening the row.
    """
    for key, old, new in finding_dict.get("deltas", []):
        if key in ("platform_state", "platform_status"):
            continue
        return f"{_clip(old, limit)} → {_clip(new, limit)}"
    return ""


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _where(change) -> str:
    """The screen a change belongs to, or the directory that declares it."""
    if change.kind in surfaces.WEBUI_KINDS:
        return surfaces.screen_of(change) or ""
    path = (change.paths or [""])[0]
    return path.rsplit("/", 1)[0] if "/" in path else path


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
            # A row used to show an identifier and leave the reader to work out
            # the rest. `where` is the screen or the declaring directory,
            # `what` is the thing in words, `why` is the one sentence saying
            # what happened to it.
            "where": _where(change),
            "what": surfaces.describe(change),
            "why": surfaces.story_of(change)[0],
            # Which of the three consequence groups the kind belongs to. A flat
            # list of thirteen kinds reads as thirteen kinds of "feature", and
            # two thirds of them are not features at all.
            "group": group_of(change.kind),
            "paths": (change.locations or change.paths)[:3],
            "we_patch": finding.matched_paths[:5],
            "we_ref": finding.matched_symbols[:8],
            # The one bit of the impact analysis worth seeing without opening
            # the row: on a real run 53 of 2,792 findings touch our code, and
            # those 53 are the reason the report exists.
            "ours": bool(finding.matched_paths or finding.matched_symbols),
            "areas": finding.areas,
            "deltas": deltas[:6],
            "reasons": finding.reasons,
            "chromestatus": status.get("summary", ""),
        }
        moved = _moved(row)
        # `what` already says "off -> on for Windows" for the kinds that have a
        # platform state, so repeating it under the prose prints the same arrow
        # twice in one cell.
        row["moved"] = "" if moved in row["what"] else moved
        # Drop empty values. Every consumer in the page guards for a missing
        # key, and on a run without a profile or enrichment these are empty on
        # every single row: measured at 3,120 findings, chromestatus, we_patch
        # and we_ref were empty 3,120 times each.
        rows.append({k: v for k, v in row.items()
                     if v not in ("", [], {}, None, False)})
    return rows


def _trim(value, limit: int = 90) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) \
        else ("(absent)" if value is None else str(value))
    return text if len(text) <= limit else text[:limit] + "…"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _esc(value: object) -> str:
    return html.escape(str(value))


def _n(value: int) -> str:
    return f"{value:,}"


DIRECTIONS = ((ADDED, "New"), (MODIFIED, "Changed"), (REMOVED, "Gone"))

# What each direction means for the team reading it. "New" and "gone" are not
# self-explanatory in a report about somebody else's tree: upstream deleting
# something is usually harmless, and upstream adding something is not work
# unless we want it.
DIRECTION_NOTES = {
    ADDED: "Upstream added these. Nothing breaks; the question is whether we "
           "want them.",
    MODIFIED: "These existed before and are different now. This is the pile to "
              "review.",
    REMOVED: "Upstream deleted these. Harmless unless we reference the name "
             "— the rows tagged <b>ours</b> do.",
}

_SEV_DOT = ((70, "d-3"), (45, "d-2"), (25, "d-1"))


def _sev_dot(severity: int) -> str:
    """How heavy a story is, before it is opened."""
    for floor, name in _SEV_DOT:
        if severity >= floor:
            return name
    return "d-0"


def _row_html(finding, why: str = "") -> str:
    """One finding: what it is, what happened to it, and its score.

    The identifier does not lead. `id:cancelButton` and `AAPMBlocksWebGPU` are
    precise and say nothing, which is what made the first version of this report
    unreadable; `detail()` puts the thing into words and drops the kind word the
    tab already says.
    """
    change = finding.change
    direction = change.change_type
    tags = ""
    if finding.bucket in (BUCKET_MUST_FIX, BUCKET_REVIEW):
        tags += (f'<span class="tag t-{finding.bucket}">'
                 f'{_esc(BUCKET_LABELS[finding.bucket])}</span>')
    if finding.matched_paths or finding.matched_symbols:
        tags += '<span class="tag t-ours">ours</span>'
    side = f'<span class="why" title="{_esc(why)}">{_esc(why)}</span>' if why else ""
    word, rest = surfaces.split_detail(change)
    lead = f'<span class="kw">{_esc(word)}</span> ' if word else ""
    return (f'<div class="row"><span class="mk mk-{direction}">'
            f'{_esc(surfaces.MARK.get(direction, "?"))}</span>'
            f'<span class="what">{lead}{_esc(rest)}{tags}</span>'
            f'{side}<span class="sc">{finding.score}</span></div>')


def _sorted(findings: Sequence) -> List:
    return sorted(findings, key=lambda f: (-f.score, f.change.key))


# Big enough that a real uprev truncates nothing: the largest single list on
# M148 -> M151 is 531 new feature flags. A pane that quietly stopped at 400
# would be a list claiming to be complete and not being it.
PANE_LIMIT = 600


def _rows_block(findings: Sequence, head: str, note: str = "",
                with_why: bool = True, limit: int = PANE_LIMIT) -> str:
    items = _sorted(findings)
    body = "".join(
        _row_html(f, surfaces.story_of(f.change)[1] if with_why else "")
        for f in items[:limit])
    if not body:
        body = '<div class="empty">Nothing here.</div>'
    if len(items) > limit:
        body += (f'<div class="row"><span class="mk"></span>'
                 f'<span class="what muted">… and '
                 f'{_n(len(items) - limit)} more. Open <b>All findings</b> and '
                 f'filter to see every one.</span></div>')
    return (f'<div class="rows"><div class="rowhead"><b>{head}</b>'
            f'<span>{_n(len(items))}</span>'
            + (f'<p>{note}</p>' if note else "")
            + f'</div>{body}</div>')


# ---------------------------------------------------------------------------
# Panes
# ---------------------------------------------------------------------------

def _by_direction(findings: Sequence) -> Dict[str, List]:
    out: Dict[str, List] = {ADDED: [], MODIFIED: [], REMOVED: []}
    for finding in findings:
        out.setdefault(finding.change.change_type, []).append(finding)
    return out


def _kind_pane(tab: str, title: str, meaning: str, kinds: Sequence[str],
               findings: Sequence) -> str:
    """One kind of thing, split two ways down the left.

    First by direction, because "what is new, what is gone, what changed" is
    the question every team asks before any other. Then by what happened, in
    the diff engine's own sentences -- which is the finer answer, and which
    only works as a list you pick from rather than as eighty headings stacked
    on one page.
    """
    by_dir = _by_direction(findings)
    side, body = ['<div class="lbl">Direction</div>'], []
    first = True
    for direction, label in DIRECTIONS:
        mine = by_dir.get(direction) or []
        sub = f"{tab}/d-{direction}"
        on = " on" if first and mine else ""
        side.append(
            f'<button class="{on.strip()}" data-sub="{sub}">'
            f'<span class="dot d-{direction}"></span>{label}'
            f'<span class="n">{_n(len(mine))}</span></button>')
        body.append(
            f'<div data-subpane="{sub}"{"" if on else " hidden"}>'
            + _rows_block(mine, f"{label} — {_esc(title.lower())}",
                          DIRECTION_NOTES[direction])
            + "</div>")
        if mine:
            first = False
    side.append('<div class="lbl">What happened</div>')
    for i, story in enumerate(surfaces.build_stories(findings, kinds)):
        sub = f"{tab}/s-{i}"
        side.append(
            f'<button data-sub="{sub}" title="{_esc(story.title)}">'
            f'<span class="dot {_sev_dot(story.severity())}"></span>'
            f'{_esc(_clip(story.title, 44))}'
            f'<span class="n">{_n(len(story.items))}</span></button>')
        body.append(f'<div data-subpane="{sub}" hidden>'
                    + _rows_block(story.items, _esc(story.title),
                                  f"{story.headline()}.", with_why=False)
                    + "</div>")
    return (f'<section class="pane" data-pane="{tab}" hidden>'
            f'<div class="panehead"><h2>{_esc(title)}</h2>'
            f'<p>{_esc(meaning)}</p></div>'
            f'<div class="split"><div class="side">{"".join(side)}</div>'
            f'<div>{"".join(body)}</div></div></section>')


def _screens_pane(tab: str, title: str, meaning: str, report: Report) -> str:
    """One `chrome://` page per entry, because a page is what a UI team owns.

    The identifier alone answers none of their questions: `id:cancelButton`
    names neither the page, nor the direction, nor what kind of control it is,
    and the same loadTimeData key appears once per handler that sets it. Every
    field needed to place it was already on the fact and was never rendered.
    """
    screens = surfaces.build(report.findings)
    if not screens:
        return ""
    side, body = [], []
    for i, screen in enumerate(screens):
        sub = f"{tab}/{i}"
        side.append(
            f'<button class="{"on" if i == 0 else ""}" data-sub="{sub}">'
            f'{_esc(screen.name)}<span class="n">{_n(len(screen.items))}</span>'
            f'</button>')
        blocks = []
        by_dir = _by_direction(screen.items)
        for direction, label in DIRECTIONS:
            mine = by_dir.get(direction) or []
            if not mine:
                continue
            blocks.append(
                f'<div class="subhead">{label} — {_n(len(mine))}</div>'
                + "".join(_row_html(f) for f in _sorted(mine)))
        body.append(
            f'<div data-subpane="{sub}"{"" if i == 0 else " hidden"}>'
            f'<div class="rows"><div class="rowhead">'
            f'<b>{_esc(screen.name)}</b>'
            f'<span>{_esc(screen.headline())}</span></div>'
            f'{"".join(blocks)}</div></div>')
    return (f'<section class="pane" data-pane="{tab}" hidden>'
            f'<div class="panehead"><h2>{_esc(title)}</h2>'
            f'<p>{_esc(meaning)} {_n(len(screens))} pages moved.</p></div>'
            f'<div class="split"><div class="side">{"".join(side)}</div>'
            f'<div>{"".join(body)}</div></div></section>')


def _triage_html(report: Report, mode: str) -> str:
    """The counts, each with what a reader is supposed to do about it.

    A number under the word "Review" is not triage; the sentence beside it is,
    and it was only ever in the markdown report.
    """
    counts = report.bucket_counts()
    meanings = md_report.BUCKET_MEANINGS[mode]
    return "".join(
        f'<button class="card {b.replace("must_fix", "must")}" '
        f'data-set="fb:{b}">'
        f'<div class="n">{_n(counts.get(b, 0))}</div>'
        f'<div class="l">{_esc(BUCKET_LABELS[b])}</div>'
        f'<div class="m">{_esc(meanings.get(b, ""))}</div></button>'
        for b in BUCKET_ORDER)


def _map_html(tabs: Sequence[tuple]) -> str:
    """Where the work is, as one table that is also the navigation.

    A team lead opens this to answer one question -- how much of this is mine,
    and how much of that is the kind that needs looking at -- and every row is
    a button that opens exactly the rows it counted.
    """
    out = ['<table class="map"><thead><tr><th>Area</th><th>New</th>'
           '<th>Changed</th><th>Gone</th><th>Total</th>'
           '<th>Flagged</th></tr></thead><tbody>']
    seen_team = ""
    for tab, title, meaning, _kinds, mine, team in tabs:
        if team != seen_team:
            out.append(f'<tr><td class="team" colspan="6">{_esc(team)}</td></tr>')
            seen_team = team
        counts = _by_direction(mine)
        flagged = sum(1 for f in mine
                      if f.bucket in (BUCKET_MUST_FIX, BUCKET_REVIEW))
        cells = "".join(
            f'<td class="m-{d}">{_n(len(counts.get(d) or []))}</td>'
            for d, _ in DIRECTIONS)
        out.append(
            f'<tr><td><button class="go" data-tab="{tab}">{_esc(title)}'
            f'<small>{_esc(meaning)}</small></button></td>'
            f'{cells}<td>{_n(len(mine))}</td><td>{_n(flagged)}</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


# Which team reads which tab. The file is one artifact and two audiences, and
# a native engineer scrolling through 271 settings-page rows to reach the Mojo
# ones is the reason the menu is split at all.
TEAM_OF = {"screens": "WebUI", "chromeflags": "WebUI"}


def render(report: Report, platform: str = "windows") -> str:
    rows = _to_rows(report, platform)
    meta = report.meta or {}
    summary = report.summary or {}
    mode = md_report.mode_of(report)

    kinds = sorted({r["kind"] for r in rows})
    areas = sorted({a for r in rows for a in r.get("areas", [])})
    unassigned_count = sum(1 for r in rows if not r.get("areas"))
    ours = sum(1 for r in rows if r.get("ours"))

    # One sentence per story, stored once instead of once per row.
    stories = {}
    for finding in report.findings:
        key, headline = surfaces.story_of(finding.change)
        stories[key] = headline

    # The tabs and the findings behind each, counted once here so the menu, the
    # overview table and the pane heading cannot disagree.
    tabs = []
    for tab, title, meaning, tab_kinds in surfaces.TABS:
        mine = [f for f in report.findings if f.change.kind in tab_kinds]
        if mine:
            tabs.append((tab, title, meaning, tab_kinds, mine,
                         TEAM_OF.get(tab, "Native")))

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
    # "feature" -- and two thirds of them are not features at all.
    surface_options = ""
    for group_name, group_kinds in KIND_GROUPS:
        present = [k for k in group_kinds if k in kinds]
        if not present:
            continue
        surface_options += f'<optgroup label="{html.escape(group_name)}">'
        surface_options += "".join(option(k, KIND_LABELS.get(k, k)) for k in present)
        surface_options += "</optgroup>"

    menu = ['<button class="on" data-tab="overview">Overview</button>']
    panes = []
    seen_team = ""
    for tab, title, meaning, tab_kinds, mine, team in tabs:
        if team != seen_team:
            menu.append(f'<span class="who">{_esc(team)}</span>')
            seen_team = team
        menu.append(f'<button data-tab="{tab}">{_esc(title)}'
                    f'<b>{_n(len(mine))}</b></button>')
        if tab == "screens":
            panes.append(_screens_pane(tab, title, meaning, report))
        else:
            panes.append(_kind_pane(tab, title, meaning, tab_kinds, mine))
    menu.append(f'<button data-tab="all" class="last">All findings<b>{_n(len(rows))}</b></button>')

    stats = summary.get("changes") or {}
    lede = (f"{_n(meta.get('facts_from', 0))} → "
            f"{_n(meta.get('facts_to', 0))} declarations read; "
            f"{_n(stats.get('total', len(rows)))} of them differ. ")
    lede += (f"{_n(ours)} touch code we patch or reference."
             if ours else
             "None touch code this profile says we patch or reference.")

    return f"""<title>{html.escape(md_report.MODE_TITLES[mode])}</title>
<style>{_CSS}</style>
<div class="wrap">
<header class="top">
<div class="eyebrow">{html.escape(md_report.MODE_TITLES[mode])}</div>
<h1><code>{html.escape(report.from_ref)}</code><span class="arrow">→</span>
<code>{html.escape(report.to_ref)}</code></h1>
<div class="sub">{html.escape(str(meta.get('product', 'downstream browser')))} ·
platform {html.escape(platform)} ·
target set {html.escape(str(meta.get('target_set', '?')))} ·
generated {html.escape(str(meta.get('generated', '')))}</div>
</header>
<nav class="menu">{''.join(menu)}</nav>

<section class="pane" data-pane="overview">
<div class="panehead"><h2>Overview</h2><p>{html.escape(lede)} Pick an area from
the table below or from the menu. Each one opens on what is <b>new</b>, what
<b>changed</b> and what is <b>gone</b>, and then on what happened, one thing at
a time.</p></div>
{notes_html}
<div class="cards">{_triage_html(report, mode)}</div>
{_map_html(tabs)}
<p class="more-note"><b>Flagged</b> counts the rows in <b>Must fix</b> or
<b>Needs review</b> &mdash; the ones with evidence that we touch them, or severe
enough to confirm. Every number on this page is a button: it opens the rows it
counted.</p>
</section>

{''.join(panes)}

<section class="pane" data-pane="all" hidden>
<div class="panehead"><h2>All findings</h2><p>Every row from every tab, in one
sortable table. Click a row for its evidence, its declaring line, and the
reasoning behind its score.</p></div>
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
<div class="tablewrap"><table class="find">
<colgroup><col style="width:62px"><col style="width:88px"><col style="width:112px">
<col style="width:27%"><col style="width:23%"><col style="width:15%">
<col style="width:150px"></colgroup>
<thead><tr>
<th data-k="score">Score</th><th data-k="change_type">Change</th>
<th data-k="bucket">Bucket</th>
<th data-k="name">What</th><th data-k="why">What happened</th>
<th data-k="where">Where</th><th data-k="kind">Surface</th>
</tr></thead><tbody id="tb"></tbody></table></div>
<button id="more" hidden></button>
<p class="more-note">Rows render in pages of 100 &mdash; the JSON below holds
every finding regardless of what is on screen.</p>
</section>
</div>
<script>window.__FINDINGS__={json.dumps(rows, ensure_ascii=False)};
window.__KINDS__={json.dumps(KIND_LABELS, ensure_ascii=False)};
window.__BUCKETS__={json.dumps(BUCKET_LABELS, ensure_ascii=False)};
window.__STORIES__={json.dumps(stories, ensure_ascii=False)};</script>
<script>{_JS}</script>
"""
