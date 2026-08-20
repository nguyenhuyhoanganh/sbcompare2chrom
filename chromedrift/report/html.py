"""Self-contained HTML dashboard.

Markdown is right for a ticket; a triage list of several hundred rows needs
filtering and sorting to be usable at all. This emits one file with the data
embedded -- no CDN, no build step, no server -- so it can be attached to a mail
thread or dropped on an internal share and still work.

The page is laid out as the questions a reader arrives with, in the order they
arrive:

    1. Is anything on fire?          the triage counts, each with what to do
    2. What is this uprev made of?   the three groups, and why they differ
    3. What actually happened?       one section per group, on the axis that
                                     carries that group's meaning
    4. Show me everything            the filterable table

Sections 2 and 3 are the ones that were missing. A 2,792-row table answers "what
scores highest" and nothing else; it cannot answer "what changed on my screen",
"which flags are now on in our build", or "what breaks outside the binary" --
which is what people actually open the report to find out. Every row in those
sections is also in the table, and the numbers in one always agree with the
other, because both read the same findings.
"""

from __future__ import annotations

import html
import json
from typing import List, Sequence

from ..diff import SIGNAL_LABELS
from ..model import (ADDED, BUCKET_LABELS, BUCKET_ORDER, KIND_FLAG_ENTRY,
                     KIND_GROUP_SURFACE, KIND_GROUP_MEANINGS, KIND_GROUPS,
                     KIND_LABELS, MODIFIED, REMOVED, Report, group_of)
from . import markdown as md_report
from . import wording as surfaces

_CSS = """
:root{
--bg:#fbfbfa;--fg:#1a1a19;--muted:#6b6b66;--faint:#8f8d87;
--line:#e6e4e0;--card:#fff;--sunk:#f4f3f0;
--must:#b4342a;--review:#a86a12;--opp:#2f6b45;--fyi:#6b6b66;--accent:#2b5fa8;
--new:#2f6b45;--chg:#a86a12;--gone:#b4342a;
--nav:46px;--radius:10px;
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
.wrap{max-width:1220px;margin:0 auto;padding:0 20px 96px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86em}
.muted{color:var(--muted)}
.num{font-variant-numeric:tabular-nums}

/* -- masthead ------------------------------------------------------------ */
.top{padding:34px 0 22px}
.eyebrow{font-size:.76rem;letter-spacing:.09em;text-transform:uppercase;
color:var(--muted);font-weight:600}
h1{font-size:1.75rem;margin:6px 0 6px;letter-spacing:-.015em;line-height:1.2}
h1 .arrow{color:var(--muted);font-weight:400;padding:0 .25em}
.sub{color:var(--muted);font-size:.88rem}
.lede{margin:14px 0 0;font-size:1rem;max-width:62ch}

/* -- section nav --------------------------------------------------------- */
/* Sticky because the page is one long scroll by design: the sections are the
   argument, and losing your place in them is what made the old single-table
   report feel like a data dump. */
.nav{position:sticky;top:0;z-index:5;height:var(--nav);display:flex;gap:4px;
align-items:center;overflow-x:auto;background:color-mix(in srgb,var(--bg) 88%,transparent);
backdrop-filter:blur(8px);border-bottom:1px solid var(--line);
margin:0 -20px 26px;padding:0 20px;scrollbar-width:thin}
.nav a{color:var(--muted);text-decoration:none;font-size:.83rem;padding:5px 10px;
border-radius:99px;white-space:nowrap}
.nav a:hover{background:var(--sunk);color:var(--fg)}
.nav a b{font-weight:600;font-variant-numeric:tabular-nums;color:var(--faint);
margin-left:5px}
section{scroll-margin-top:calc(var(--nav) + 14px)}
h2{font-size:1.18rem;margin:0 0 4px;letter-spacing:-.01em}
.sechead{margin:44px 0 16px;padding-top:8px;border-top:1px solid var(--line)}
.sechead .meaning{color:var(--muted);font-size:.92rem;margin:6px 0 0;max-width:74ch}
.sechead .count{color:var(--faint);font-weight:400;font-size:1rem}

/* -- triage -------------------------------------------------------------- */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
padding:14px 16px;box-shadow:var(--shadow);display:block;color:inherit;
text-decoration:none;border-left:3px solid var(--line)}
a.card:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
.card .n{font-size:1.9rem;font-weight:600;line-height:1.15;font-variant-numeric:tabular-nums}
.card .l{font-size:.82rem;font-weight:600;letter-spacing:.02em}
.card .m{color:var(--muted);font-size:.8rem;margin-top:5px;line-height:1.45}
.card.must{border-left-color:var(--must)}.card.must .n{color:var(--must)}
.card.review{border-left-color:var(--review)}.card.review .n{color:var(--review)}
.card.opportunity{border-left-color:var(--opp)}.card.opportunity .n{color:var(--opp)}
.card.fyi .n{color:var(--fyi)}

/* -- the three groups ---------------------------------------------------- */
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.grp-card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
padding:16px 18px 14px;box-shadow:var(--shadow);display:flex;flex-direction:column}
.grp-card h3{margin:0;font-size:.98rem;display:flex;align-items:baseline;gap:8px}
.grp-card h3 .n{margin-left:auto;font-size:1.35rem;font-weight:600;
font-variant-numeric:tabular-nums}
.grp-card p{color:var(--muted);font-size:.84rem;margin:8px 0 0;line-height:1.5}
.bar{display:flex;height:6px;border-radius:99px;overflow:hidden;margin:11px 0 7px;
background:var(--sunk)}
.bar i{display:block}
.bar .b-added{background:var(--new)}.bar .b-modified{background:var(--chg)}
.bar .b-removed{background:var(--gone)}
.split{font-size:.78rem;color:var(--muted);display:flex;gap:11px;flex-wrap:wrap}
.split b{font-weight:600;font-variant-numeric:tabular-nums}
.split .s-added b{color:var(--new)}.split .s-modified b{color:var(--chg)}
.split .s-removed b{color:var(--gone)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.chip{font-size:.76rem;border:1px solid var(--line);border-radius:99px;padding:2px 9px;
color:var(--muted);text-decoration:none;background:var(--sunk)}
.chip:hover{border-color:var(--accent);color:var(--fg)}
.chip b{font-weight:600;font-variant-numeric:tabular-nums;margin-left:5px;color:var(--faint)}

/* -- story and screen blocks --------------------------------------------- */
/* Both are the same shape: a headline, how much it covers, and the rows under
   it. They differ only in what the headline names -- a thing that happened, or
   a screen it happened on. */
.blocks{display:grid;gap:8px}
.blocks details{border:1px solid var(--line);border-radius:var(--radius);
background:var(--card);overflow:hidden}
.blocks details[open]{box-shadow:var(--shadow)}
.blocks summary{cursor:pointer;padding:11px 15px;display:flex;gap:11px;
align-items:baseline;flex-wrap:wrap;list-style:none}
.blocks summary::-webkit-details-marker{display:none}
.blocks summary::before{content:"";flex:0 0 7px;height:7px;border-radius:50%;
background:var(--line);align-self:center}
.sev-3 summary::before{background:var(--must)}
.sev-2 summary::before{background:var(--review)}
.sev-1 summary::before{background:var(--accent)}
.blocks summary .n{font-variant-numeric:tabular-nums;font-weight:600;
min-width:3ch;text-align:right}
.blocks summary .t{font-weight:600;font-size:.94rem;flex:1 1 22ch}
.blocks .tally{font-weight:400;font-size:.8rem;color:var(--muted);white-space:nowrap}
.blocks ul{list-style:none;margin:0;padding:2px 15px 12px 33px}
.blocks li{display:flex;gap:9px;align-items:baseline;padding:4px 0;
border-top:1px solid var(--line);font-size:.89rem}
.blocks li:first-child{border-top:0}
.mk{flex:0 0 1.1em;text-align:center;font-weight:700}
.mk-added{color:var(--new)}.mk-removed{color:var(--gone)}.mk-modified{color:var(--chg)}
.blocks .sc{margin-left:auto;color:var(--faint);font-size:.78rem;
font-variant-numeric:tabular-nums;padding-left:10px}
.blocks .at{color:var(--faint);font-size:.8rem}
.sub-h{font-size:.9rem;margin:26px 0 10px;color:var(--fg);font-weight:600;
letter-spacing:.01em}
.sub-h:first-of-type{margin-top:0}
.legend{color:var(--muted);font-size:.82rem;margin:0 0 12px}
.legend span{margin-right:14px}
.more-note{color:var(--muted);font-size:.84rem;margin:10px 0 0}

/* -- table --------------------------------------------------------------- */
.controls{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;align-items:center}
input[type=search],select{background:var(--card);color:var(--fg);border:1px solid var(--line);
border-radius:7px;padding:7px 10px;font:inherit;font-size:.87rem}
input[type=search]{flex:1;min-width:210px}
/* Its own scroll box, so the column headers actually stay put: a sticky <th>
   sticks to the nearest scrollport, and the wrapper is already one because
   overflow-x:auto makes overflow-y a scroll container too. Bounding it turns
   that accident into the behaviour people expect. */
.tablewrap{overflow:auto;max-height:min(74vh,820px);border:1px solid var(--line);
border-radius:var(--radius);background:var(--card);box-shadow:var(--shadow)}
/* table-layout:fixed is the single biggest lever here. With the default auto
   layout, column widths depend on cell content, so inserting one expanded row
   makes the browser re-measure every cell in the table before it can paint.
   Fixed layout takes the widths from the colgroup and never looks at content,
   so expanding a row costs the row instead of the table. border-collapse also
   moves off `collapse`, whose border resolution is measurably slower. */
table{border-collapse:separate;border-spacing:0;table-layout:fixed;width:100%;
font-size:.87rem;min-width:940px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);
vertical-align:top;overflow-wrap:anywhere}
th{font-weight:600;color:var(--muted);font-size:.75rem;text-transform:uppercase;
letter-spacing:.05em;cursor:pointer;user-select:none;white-space:nowrap;
position:sticky;top:0;z-index:1;background:var(--card);
box-shadow:inset 0 -1px 0 var(--line)}
th:hover{color:var(--fg)}
tbody tr:last-child td{border-bottom:none}
tbody tr.det td{background:var(--sunk);font-size:.85rem}
/* Rows outside the viewport skip layout entirely; the intrinsic size keeps the
   scrollbar honest so skipping does not make the page jump. */
tbody tr{content-visibility:auto;contain-intrinsic-size:auto 40px}
tbody tr.row{cursor:pointer}
tbody tr.row:hover td{background:color-mix(in srgb,var(--card) 88%,var(--accent))}
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
.empty{padding:32px;text-align:center;color:var(--muted)}
.note{background:var(--card);border:1px solid var(--line);border-radius:8px;
border-left:3px solid var(--review);
padding:10px 14px;margin:14px 0;font-size:.87rem;color:var(--muted)}
#more{margin-top:12px;width:100%;padding:10px;background:var(--card);color:var(--fg);
border:1px solid var(--line);border-radius:8px;font:inherit;font-size:.87rem;cursor:pointer}
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
   about forty story headlines stored once each instead of once per finding:
   188 KB on a 3,120-row report for the kinds alone, and the story headlines are
   full sentences. */
const KINDS=window.__KINDS__||{},BUCKETS=window.__BUCKETS__||{},
STORIES=window.__STORIES__||{};
const kindLabel=f=>KINDS[f.kind]||f.kind, bucketLabel=f=>BUCKETS[f.bucket]||f.bucket,
whyLabel=f=>STORIES[f.why]||f.why||'';
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
/* The "what" column reads as prose, not as an identifier: a row saying
   `id:cancelButton` names neither the page nor the direction. `moved` is
   carried only when the prose does not already contain it, so the arrow is
   never printed twice. */
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
  return '<tr class="row" data-i="'+i+'"><td class="score">'+f.score+'</td>'+
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
/* Sorting reads the displayed value, not the stored one: Surface and Why show
   labels that are looked up, so sorting on the raw key would order the rows
   differently from how they read. */
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
  const tr=e.target.closest('tr.row'); if(!tr)return;
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
/* The summary sections are the navigation. A count is only useful if you can
   get from it to the rows it counts, so every card and chip carries the filter
   it stands for and the anchor does the scrolling. */
document.querySelectorAll('[data-set]').forEach(el=>el.addEventListener('click',()=>{
  const p=el.dataset.set.split(':'),sel={fb:fb,fk:fk,fa:fa}[p[0]];
  if(!sel)return;
  fb.value='';fk.value='';fa.value='';
  sel.value=p.slice(1).join(':');
  apply();}));
/* Debounced: typing "network" used to run the whole pipeline seven times. */
let timer=null;
q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,140);});
[fb,fk,fa].forEach(el=>el&&el.addEventListener('change',apply));
apply();
"""


def _moved(finding_dict: dict, limit: int = 34) -> str:
    """"100 → 109", for the second line of the What cell.

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
            # what happened to it, and the change type was only reachable by
            # opening the row.
            "where": _where(change),
            "what": surfaces.describe(change),
            "why": surfaces.story_of(change)[0],
            # Which of the three the kind belongs to. A flat list of thirteen
            # reads as thirteen kinds of "feature", and two thirds of them are
            # not features at all -- the most common misreading of a report,
            # and it was visible only inside a filter dropdown.
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
        # `what` already says "off → on for Windows" for the kinds that have a
        # platform state, so repeating it under the prose prints the same arrow
        # twice in one cell.
        row["moved"] = "" if moved in row["what"] else moved
        # Drop empty values. Every consumer in the page already guards for a
        # missing key (`f.signals||[]`, `f.we_ref||[]`), and on a run without a
        # profile or without enrichment these are empty on every single row:
        # measured at 3,120 findings, chromestatus/we_patch/we_ref were empty
        # 3,120 times each. Carrying them costs a fifth of the payload to say
        # nothing.
        rows.append({k: v for k, v in row.items()
                     if v not in ("", [], {}, None, False)})
    return rows


def _trim(value, limit: int = 90) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) \
        else ("(absent)" if value is None else str(value))
    return text if len(text) <= limit else text[:limit] + "…"


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------

_SEV_CLASS = ((70, "sev-3"), (45, "sev-2"), (25, "sev-1"))


def _sev_class(severity: int) -> str:
    """A dot, so the weight of a block is visible before it is opened."""
    for floor, name in _SEV_CLASS:
        if severity >= floor:
            return name
    return "sev-0"


def _esc(value: object) -> str:
    return html.escape(str(value))


def _n(value: int) -> str:
    return f"{value:,}"


def _block_html(block, mark_where: bool = False, limit: int = 14,
                start_open: bool = False) -> str:
    """One `<details>`: a headline, its tally, and the rows it stands for."""
    items = block.sorted_items()
    out = [f'<details class="{_sev_class(block.severity())}"'
           f'{" open" if start_open else ""}>',
           f'<summary><span class="n">{_n(len(items))}</span>'
           f'<span class="t">{_esc(block.title)}</span>'
           f'<span class="tally">{_esc(block.headline())}</span></summary><ul>']
    for finding in items[:limit]:
        direction = finding.change.change_type
        where = ""
        if mark_where:
            screen = surfaces.screen_of(finding.change) or _where(finding.change)
            if screen:
                where = f'<span class="at">{_esc(screen)}</span>'
        out.append(
            f'<li><span class="mk mk-{direction}">'
            f'{_esc(surfaces.MARK.get(direction, "?"))}</span>'
            f'<span>{_esc(surfaces.describe(finding.change))}</span>{where}'
            f'<span class="sc">{finding.score}</span></li>')
    if len(items) > limit:
        out.append(f'<li><span class="mk"></span><span class="muted">'
                   f'… and {_n(len(items) - limit)} more, in the table below'
                   f'</span></li>')
    out.append("</ul></details>")
    return "".join(out)


_LEGEND = ('<p class="legend"><span><b class="mk-added">+</b> new</span>'
           '<span><b class="mk-modified">~</b> changed</span>'
           '<span><b class="mk-removed">−</b> gone</span>'
           '<span>The number on the right is the finding\'s score.</span></p>')


def _sechead(title: str, meaning: str, count: int = 0) -> str:
    tally = f' <span class="count">{_n(count)}</span>' if count else ""
    return (f'<div class="sechead"><h2>{_esc(title)}{tally}</h2>'
            f'<p class="meaning">{meaning}</p></div>')


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _triage_html(report: Report, mode: str) -> str:
    """The counts, each with what a reader is supposed to do about it.

    A number under the word "Review" is not triage; the sentence beside it is,
    and it was only ever in the markdown report.
    """
    counts = report.bucket_counts()
    meanings = md_report.BUCKET_MEANINGS[mode]
    cards = []
    for bucket in BUCKET_ORDER:
        cards.append(
            f'<a class="card {bucket.replace("must_fix", "must")}" href="#all" '
            f'data-set="fb:{bucket}">'
            f'<div class="n">{_n(counts.get(bucket, 0))}</div>'
            f'<div class="l">{_esc(BUCKET_LABELS[bucket])}</div>'
            f'<div class="m">{_esc(meanings.get(bucket, ""))}</div></a>')
    return "".join(cards)


def _by_group(report: Report) -> List[tuple]:
    """[(name, kinds, findings)] -- computed once, in group order.

    The nav, the group cards and the section headings all print the same three
    numbers. Counting them three times is how two of them come to disagree.
    """
    out = []
    for name, kinds in KIND_GROUPS:
        mine = [f for f in report.findings if f.change.kind in kinds]
        if mine:
            out.append((name, kinds, mine))
    return out


def _groups_html(groups: Sequence[tuple]) -> str:
    """What the report is made of, split the way its meaning splits.

    Thirteen kinds read as thirteen kinds of "feature". They are three kinds of
    consequence, and until now the only place that said so was the label on an
    `<optgroup>` inside a filter dropdown.
    """
    out = []
    for group_name, group_kinds, mine in groups:
        total = len(mine)
        counts = {d: sum(1 for f in mine if f.change.change_type == d)
                  for d in (ADDED, MODIFIED, REMOVED)}
        bar = "".join(
            f'<i class="b-{d}" style="width:{counts[d] * 100 / total:.4g}%"></i>'
            for d in (ADDED, MODIFIED, REMOVED) if counts[d])
        split = "".join(
            f'<span class="s-{d}"><b>{_n(counts[d])}</b> '
            f'{surfaces.VERB[d]}</span>'
            for d in (ADDED, MODIFIED, REMOVED) if counts[d])
        chips = []
        for kind in group_kinds:
            n = sum(1 for f in mine if f.change.kind == kind)
            if not n:
                continue
            chips.append(f'<a class="chip" href="#all" data-set="fk:{kind}">'
                         f'{_esc(KIND_LABELS.get(kind, kind))}<b>{_n(n)}</b></a>')
        out.append(
            f'<div class="grp-card"><h3>{_esc(group_name)}'
            f'<span class="n">{_n(total)}</span></h3>'
            f'<div class="bar">{bar}</div><div class="split">{split}</div>'
            f'<p>{_esc(KIND_GROUP_MEANINGS.get(group_name, ""))}</p>'
            f'<div class="chips">{"".join(chips)}</div></div>')
    return f'<div class="groups">{"".join(out)}</div>'


def _stories_html(report: Report, kinds: Sequence[str], limit: int = 14) -> str:
    stories = surfaces.build_stories(report.findings, kinds)
    if not stories:
        return ""
    # The first one opens, because a column of closed bars says nothing about
    # what is inside any of them.
    return ('<div class="blocks">'
            + "".join(_block_html(s, mark_where=True, limit=limit,
                                  start_open=(i == 0))
                      for i, s in enumerate(stories))
            + "</div>")


def _screens_html(report: Report, limit: int = 40, per_screen: int = 18) -> str:
    """"What changed on each screen", above the table rather than inside it.

    The table answers "what has the highest severity"; this answers "what is
    different about this page", which is the question anyone owning a surface
    actually arrives with. Neither can be read off the other: the same
    loadTimeData key is set by nine different handlers, and a flat list shows
    it nine times with nothing to tell them apart.
    """
    screens = surfaces.build(report.findings)
    if not screens:
        return ""
    totals = surfaces.summarize(screens)
    head = (f"{_n(totals['added'])} new · {_n(totals['changed'])} changed · "
            f"{_n(totals['removed'])} gone, across {_n(totals['screens'])} "
            f"screens, ordered by how much moved.")
    out = [f'<p class="legend">{_esc(head)}</p>', '<div class="blocks">']
    out += [_block_html(s, limit=per_screen, start_open=(i == 0))
            for i, s in enumerate(screens[:limit])]
    out.append("</div>")
    if len(screens) > limit:
        out.append(f'<p class="more-note">… and {_n(len(screens) - limit)} more '
                   f'screens with fewer changes. Filter the table by surface to '
                   f'see them.</p>')
    return "\n".join(out)


def render(report: Report, platform: str = "windows") -> str:
    rows = _to_rows(report, platform)
    meta = report.meta or {}
    summary = report.summary or {}
    mode = md_report.mode_of(report)

    kinds = sorted({r["kind"] for r in rows})
    areas = sorted({a for r in rows for a in r.get("areas", [])})
    unassigned_count = sum(1 for r in rows if not r.get("areas"))
    ours = sum(1 for r in rows if r.get("ours"))

    # One headline map for every story present, so a full sentence is stored
    # once instead of once per row.
    stories = {}
    for finding in report.findings:
        key, headline = surfaces.story_of(finding.change)
        stories[key] = headline

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

    # One section per group, on the axis that carries that group's meaning:
    # the two code-facing groups by what happened, the user-facing one by the
    # screen it happened on -- with the flags entries, which belong to no
    # screen, kept as their own block.
    groups = _by_group(report)
    sections = []
    nav = ['<a href="#triage">Triage</a>', '<a href="#made-of">Made of</a>']
    for group_name, group_kinds, mine in groups:
        total = len(mine)
        anchor = "g-" + group_name.split()[0].lower()
        nav.append(f'<a href="#{anchor}">{_esc(group_name)}<b>{_n(total)}</b></a>')
        body = ""
        if group_name == KIND_GROUP_SURFACE:
            screens = _screens_html(report)
            if screens:
                body += f'<h3 class="sub-h">What changed on each screen</h3>{screens}'
            flags = _stories_html(report, (KIND_FLAG_ENTRY,))
            if flags:
                body += ('<h3 class="sub-h">chrome://flags, which belongs to no '
                         'screen</h3>' + flags)
        else:
            body = _stories_html(report, group_kinds)
        sections.append(
            f'<section id="{anchor}">'
            + _sechead(group_name,
                       _esc(KIND_GROUP_MEANINGS.get(group_name, "")), total)
            + _LEGEND + body + "</section>")
    nav.append(f'<a href="#all">Every finding<b>{_n(len(rows))}</b></a>')

    stats = summary.get("changes") or {}
    lede = (f"{_n(meta.get('facts_from', 0))} → {_n(meta.get('facts_to', 0))} "
            f"declarations read; {_n(stats.get('total', len(rows)))} of them "
            f"differ, across {len(stats.get('by_kind', {})) or len(kinds)} "
            f"surfaces. ")
    lede += (f"{_n(ours)} of the changes touch code we patch or reference."
             if ours else
             "None of them touch code this profile says we patch or reference.")

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
<p class="lede">{html.escape(lede)}</p>
</header>
<nav class="nav">{''.join(nav)}</nav>
{notes_html}
<section id="triage">
{_sechead("Triage",
          "Every finding lands in exactly one of these. The sentence is what to "
          "do about it; the number takes you to the rows.")}
<div class="cards">{_triage_html(report, mode)}</div>
</section>
<section id="made-of">
{_sechead("What this uprev is made of",
          "Thirteen surfaces, three consequences. Reading them as thirteen "
          "kinds of &ldquo;feature&rdquo; is the most common misreading of a "
          "report &mdash; two thirds of one is not about features at all.")}
{_groups_html(groups)}
</section>
{''.join(sections)}
<section id="all">
{_sechead("Every finding",
          "The whole set, filterable and sortable. Every row in the sections "
          "above is one of these. Click a row for its evidence, its declaring "
          "line, and the reasoning behind its score.")}
<div class="controls">
<input type="search" id="q" placeholder="Search name, signal, path, symbol…">
<select id="fb"><option value="">All buckets</option>
{''.join(option(b, BUCKET_LABELS[b]) for b in BUCKET_ORDER)}</select>
<select id="fk"><option value="">All surfaces</option>
{surface_options}</select>
<select id="fa"><option value="">All areas</option>
{''.join(option(a) for a in areas)}
{option("__none__", f"(no area) — {unassigned_count}") if unassigned_count else ""}</select>
<span class="muted num" id="cnt"></span>
</div>
<div class="tablewrap"><table>
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
