"""Self-contained HTML dashboard: one filterable table, and rows that read.

Markdown is right for a ticket; a triage list of several hundred rows needs
filtering and sorting to be usable at all. This emits one file with the data
embedded -- no CDN, no build step, no server -- so it can be attached to a mail
thread or dropped on an internal share and still work.

It is one table on purpose, and the two layouts tried in between are worth
recording because both were worse. Grouping every finding by signal put
twenty-one collapsed bars on one page whose titles were near-synonyms in
Chromium's own vocabulary ("Default flipped on", "Now ON by default on
Windows", "New feature, on by default" are three different bars). Putting those
behind a per-team menu fixed the wall and cost the one thing the table is good
at: you could no longer see everything at once, or sort it, or search it.

What was actually missing was never the shape. It was that a row said
`id:cancelButton` and left the reader to work out the rest -- which page, which
direction, what kind of control, whether it matters to us. So the table keeps
its shape and every row now carries that:

    What            the thing in words, not an identifier: "toggle -- httpsOnly
                    (writes generated.https_first_mode_enabled)"
    What happened   the sentence the diff engine already wrote for it, which is
                    the label of the signal that set its severity
    Where           the screen it is on, or the directory that declares it

Nothing here invents a fact or drops one. Every column is a field that was
already on the finding and was simply never rendered.
"""

from __future__ import annotations

import html
import json
from typing import List

from ..diff import SIGNAL_LABELS, owner_of
from ..model import (BUCKET_LABELS, BUCKET_MEANINGS, BUCKET_ORDER, KIND_GROUPS,
                     KIND_LABELS, OWNER_LABELS, OWNER_ORDER, Report,
                     group_of)
from .markdown import TITLE, display_name
from . import wording as surfaces

_CSS = """
/* One accent, one radius scale, one shadow scale, one spacing rhythm. The
   palette is neutral-warm rather than blue-grey so the four bucket colours --
   which are the only saturated things on the page -- carry all of the meaning
   and none of the decoration. */
:root{
--bg:#faf9f7;--bg2:#f2f0ec;--fg:#191817;--muted:#6c6a64;--faint:#9c9992;
--line:#e7e4de;--line2:#d9d5cd;--card:#fff;--sunk:#f5f3ef;
--brk:#c0392f;--beh:#a06a10;--new-b:#2c6b45;--hk:#77746d;
--accent:#2f5fa8;--accent-soft:#eaf0fb;
--new:#2c6b45;--chg:#a06a10;--gone:#c0392f;
--r1:9px;--r2:14px;
--sh1:0 1px 2px rgba(24,20,12,.05);
--sh2:0 1px 2px rgba(24,20,12,.04),0 4px 14px -4px rgba(24,20,12,.08);
--sh3:0 2px 4px rgba(24,20,12,.05),0 12px 28px -10px rgba(24,20,12,.16);
color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#141413;--bg2:#111110;--fg:#eeece7;--muted:#a19e96;--faint:#78756e;
--line:#2e2d2a;--line2:#3b3a36;--card:#1d1c1b;--sunk:#232220;
--brk:#f0857a;--beh:#e3ae57;--new-b:#7fc79b;--hk:#a19e96;
--accent:#7fa9e8;--accent-soft:#1c2433;
--new:#7fc79b;--chg:#e3ae57;--gone:#f0857a;
--sh1:0 1px 2px rgba(0,0,0,.4);
--sh2:0 1px 2px rgba(0,0,0,.35),0 4px 14px -4px rgba(0,0,0,.5);
--sh3:0 2px 4px rgba(0,0,0,.4),0 12px 28px -10px rgba(0,0,0,.65);
color-scheme:dark;}}
:root[data-theme=dark]{
--bg:#141413;--bg2:#111110;--fg:#eeece7;--muted:#a19e96;--faint:#78756e;
--line:#2e2d2a;--line2:#3b3a36;--card:#1d1c1b;--sunk:#232220;
--brk:#f0857a;--beh:#e3ae57;--new-b:#7fc79b;--hk:#a19e96;
--accent:#7fa9e8;--accent-soft:#1c2433;
--new:#7fc79b;--chg:#e3ae57;--gone:#f0857a;
--sh1:0 1px 2px rgba(0,0,0,.4);
--sh2:0 1px 2px rgba(0,0,0,.35),0 4px 14px -4px rgba(0,0,0,.5);
--sh3:0 2px 4px rgba(0,0,0,.4),0 12px 28px -10px rgba(0,0,0,.65);
color-scheme:dark;}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI Variable Text","Segoe UI",
Roboto,"Helvetica Neue",Arial,sans-serif;
font-feature-settings:"cv05","ss01";-webkit-font-smoothing:antialiased;
text-rendering:optimizeLegibility}
.wrap{max-width:1320px;margin:0 auto;padding:0 24px 72px}
code{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
font-size:.87em;font-variant-ligatures:none}
.muted{color:var(--muted)}
.tablewrap{scrollbar-color:var(--line2) transparent}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}

/* -- masthead ------------------------------------------------------------ */
.top{padding:38px 0 4px}
.eyebrow{display:inline-flex;align-items:center;gap:7px;font-size:.71rem;
letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:600}
.eyebrow::before{content:"";width:6px;height:6px;border-radius:50%;
background:var(--accent)}
h1{font-size:1.55rem;margin:11px 0 7px;letter-spacing:-.022em;line-height:1.22;
font-weight:650}
h1 code{font-size:.94em;letter-spacing:-.01em}
h1 .arrow{color:var(--accent);font-weight:400;padding:0 .3em}
.sub{color:var(--faint);font-size:.82rem;letter-spacing:.005em}

/* -- lede ---------------------------------------------------------------- */
.lede{margin:20px 0 26px;font-size:.98rem;line-height:1.6;max-width:74ch;
color:var(--muted)}
.lede b{color:var(--fg);font-weight:600}

/* -- triage cards -------------------------------------------------------- */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(212px,1fr));
gap:14px}
/* The bucket colour is a wash from the top edge and a dot beside the label,
   not a bar across the top: a 3px bar inside a 14px radius gets eaten by the
   corner at both ends and reads as a mistake. */
.card{background:var(--card);border:1px solid var(--line);
border-radius:var(--r2);padding:17px 18px 16px;box-shadow:var(--sh2);
display:block;color:inherit;text-align:left;font:inherit;cursor:pointer;
width:100%;
transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}
.card:hover{transform:translateY(-2px);box-shadow:var(--sh3);
border-color:var(--line2)}
.card:active{transform:translateY(0)}
.card .n{font-size:2.05rem;font-weight:640;line-height:1.05;letter-spacing:-.03em;
font-variant-numeric:tabular-nums}
.card .l{font-size:.8rem;font-weight:640;letter-spacing:.005em;margin-top:4px;
display:flex;align-items:center;gap:7px}
.card .l::before{content:"";flex:0 0 7px;height:7px;border-radius:50%;
background:var(--line2)}
.card .m{color:var(--muted);font-size:.785rem;margin-top:8px;line-height:1.5}
.card.breaking{background:linear-gradient(180deg,
color-mix(in srgb,var(--brk) 8%,var(--card)),var(--card) 58%)}
.card.behaviour{background:linear-gradient(180deg,
color-mix(in srgb,var(--beh) 8%,var(--card)),var(--card) 58%)}
.card.new{background:linear-gradient(180deg,
color-mix(in srgb,var(--new-b) 8%,var(--card)),var(--card) 58%)}
.card.breaking .n{color:var(--brk)}
.card.breaking .l::before{background:var(--brk)}
.card.behaviour .n{color:var(--beh)}
.card.behaviour .l::before{background:var(--beh)}
.card.new .n{color:var(--new-b)}.card.new .l::before{background:var(--new-b)}
.card.housekeeping .n{color:var(--hk)}
.card.housekeeping .l::before{background:var(--hk)}

/* -- filter row ---------------------------------------------------------- */
.controls{display:flex;flex-wrap:wrap;gap:9px;margin:28px 0 14px;
align-items:center}
input[type=search],select{background:var(--card);color:var(--fg);
border:1px solid var(--line);border-radius:var(--r1);padding:9px 12px;
font:inherit;font-size:.87rem;box-shadow:var(--sh1);
transition:border-color .14s ease,box-shadow .14s ease}
input[type=search]{flex:1;min-width:230px}
input[type=search]::placeholder{color:var(--faint)}
input[type=search]:hover,select:hover{border-color:var(--line2)}
input[type=search]:focus,select:focus{outline:none;border-color:var(--accent);
box-shadow:0 0 0 3px var(--accent-soft)}
select{cursor:pointer}
#cnt{margin-left:auto;font-size:.82rem;color:var(--faint);
font-variant-numeric:tabular-nums}

/* -- table --------------------------------------------------------------- */
/* Its own scroll box, so the column headers stay put: a sticky <th> sticks to
   the nearest scrollport, and the wrapper is already one because overflow-x
   makes overflow-y a scroll container too. */
.tablewrap{overflow:auto;max-height:min(74vh,860px);border:1px solid var(--line);
border-radius:var(--r2);background:var(--card);box-shadow:var(--sh2)}
/* table-layout:fixed is the single biggest lever here. With the default auto
   layout, column widths depend on cell content, so inserting one expanded row
   makes the browser re-measure every cell before it can paint. Fixed layout
   takes the widths from the colgroup and never looks at content. */
table.find{border-collapse:separate;border-spacing:0;table-layout:fixed;
width:100%;font-size:.875rem;min-width:900px}
table.find th,table.find td{text-align:left;padding:11px 14px;
border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
table.find th{font-weight:600;color:var(--muted);font-size:.7rem;
text-transform:uppercase;letter-spacing:.075em;cursor:pointer;user-select:none;
white-space:nowrap;position:sticky;top:0;z-index:1;
background:var(--card);padding-top:13px;padding-bottom:11px;
box-shadow:inset 0 -1px 0 var(--line)}
table.find th:hover{color:var(--fg)}
table.find tbody tr:last-child td{border-bottom:none}
/* Rows outside the viewport skip layout entirely; the intrinsic size keeps the
   scrollbar honest so skipping does not make the page jump. */
table.find tbody tr{content-visibility:auto;contain-intrinsic-size:auto 46px}
tbody tr.row-t{cursor:pointer}
tbody tr.row-t:hover td{background:var(--sunk)}
tbody tr.det td{background:var(--sunk);font-size:.85rem;
box-shadow:inset 2px 0 0 var(--accent)}

.score{font-variant-numeric:tabular-nums;font-weight:650;letter-spacing:-.015em;
font-size:.95rem;color:var(--muted)}
.s-hi{color:var(--brk)}.s-mid{color:var(--beh)}

.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.71rem;
font-weight:600;letter-spacing:.01em;white-space:nowrap;
background:color-mix(in srgb,currentColor 13%,transparent)}
.b-breaking{color:var(--brk)}.b-behaviour{color:var(--beh)}
.b-new{color:var(--new-b)}.b-housekeeping{color:var(--hk)}

.mk{font-weight:700;padding-right:6px;font-variant-numeric:tabular-nums}
.mk-added{color:var(--new)}.mk-removed{color:var(--gone)}
.mk-modified{color:var(--chg)}
.where{color:var(--muted);font-size:.815rem;line-height:1.45}
.grp{font-size:.715rem;color:var(--faint);margin-top:3px}
.moved{font-size:.775rem;color:var(--faint);margin-top:4px;line-height:1.45}
ul.tight{margin:7px 0;padding-left:19px;line-height:1.7}
.empty{padding:44px;text-align:center;color:var(--faint)}
.note{background:var(--card);border:1px solid var(--line);border-radius:var(--r1);
border-left:3px solid var(--beh);padding:12px 15px;margin:0 0 16px;
font-size:.87rem;color:var(--muted);box-shadow:var(--sh1)}
#more{margin-top:14px;width:100%;padding:12px;background:var(--card);
color:var(--muted);border:1px solid var(--line);border-radius:var(--r1);
font:inherit;font-size:.86rem;font-weight:600;cursor:pointer;box-shadow:var(--sh1);
transition:border-color .14s ease,color .14s ease,background .14s ease}
#more:hover{border-color:var(--accent);color:var(--accent);background:var(--sunk)}
.more-note{color:var(--faint);font-size:.81rem;margin:14px 0 0;line-height:1.6;
max-width:78ch}

/* -- shipped-feature brief ----------------------------------------------- */
/* Background, not findings, so it sits below the table and stays folded. */
.brief{margin:26px 0 0;background:var(--card);border:1px solid var(--line);
border-radius:var(--r2);box-shadow:var(--sh2);overflow:hidden}
.brief>summary{cursor:pointer;padding:15px 18px;font-size:.87rem;
font-weight:640;list-style:none;display:flex;align-items:center;gap:9px}
.brief>summary::-webkit-details-marker{display:none}
.brief>summary::before{content:"▸";color:var(--accent);font-size:.8em}
.brief[open]>summary::before{content:"▾"}
.brief>summary:hover{background:var(--sunk)}
.brief .body{padding:2px 18px 18px;border-top:1px solid var(--line)}
.brief .why{color:var(--muted);font-size:.82rem;line-height:1.6;
max-width:78ch;margin:13px 0 4px}
.brief .feat{padding:11px 0;border-bottom:1px solid var(--line)}
.brief .feat:last-child{border-bottom:none}
.brief .ms{display:inline-block;font-size:.68rem;font-weight:700;
letter-spacing:.03em;color:var(--accent);background:var(--accent-soft);
border-radius:999px;padding:1px 8px;margin-right:8px;vertical-align:1px;
font-variant-numeric:tabular-nums}
.brief .fname{font-weight:600;font-size:.88rem}
.brief .ship{color:var(--faint);font-size:.75rem;margin-left:6px}
.brief .fsum{color:var(--muted);font-size:.83rem;line-height:1.55;margin-top:5px}
.brief a{color:var(--accent)}
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
fk=document.getElementById('fk'),fg=document.getElementById('fg'),
fo=document.getElementById('fo'),
tb=document.getElementById('tb'),cnt=document.getElementById('cnt'),
more=document.getElementById('more');
let sortKey='score',sortDir=-1,shown=PAGE,view=DATA;
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function match(f,t){
  if(fb.value&&f.bucket!==fb.value)return false;
  if(fk.value&&f.kind!==fk.value)return false;
  if(fg.value&&f.group!==fg.value)return false;
  if(fo.value&&f.owner!==fo.value)return false;
  if(!t)return true;
  if(f._hay===undefined)
    f._hay=(f.name+' '+f.kind+' '+(f.what||'')+' '+(f.where||'')+' '+whyLabel(f)+' '
      +(f.signals||[]).join(' ')+' '+(f.paths||[]).join(' ')
      +' '+(f.chromestatus||'')).toLowerCase();
  return f._hay.indexOf(t)!==-1;
}
/* Built only when a row is actually expanded. This was half the payload. */
function details(f){
  const L=[];
  if(f.signals&&f.signals.length)L.push('<li><b>Signals:</b> '+esc(f.signals.join(', '))+'</li>');
  if(f.paths&&f.paths.length)L.push('<li><b>Declared in:</b> <code>'+esc(f.paths.join(', '))+'</code></li>');
  (f.deltas||[]).forEach(d=>L.push('<li><b>'+esc(d[0])+':</b> <code>'+esc(d[1])+'</code> \\u2192 <code>'+esc(d[2])+'</code></li>'));
  if(f.chromestatus)L.push('<li><b>Chromestatus:</b> '+esc(f.chromestatus)+'</li>');
  if(f.reasons&&f.reasons.length)L.push('<li class="muted"><b>Score:</b> '+esc(f.reasons.join(' \\u00b7 '))+'</li>');
  return '<ul class="tight">'+L.join('')+'</ul>';
}
var MARK={added:'+',removed:'\u2212',modified:'~'};
function whatCell(f){
  var c=f.change_type||'';
  var out='<span class="mk mk-'+c+'" title="'+esc(c)+'">'+(MARK[c]||'?')+'</span>'+
    (f.what?esc(f.what):'<code>'+esc(f.name)+'</code>');
  if(f.moved) out+='<div class="moved">'+esc(f.moved)+'</div>';
  return out;
}
function surfaceCell(f){
  var out=esc(kindLabel(f));
  if(f.group) out+='<div class="grp">'+esc(f.group)+'</div>';
  return out;
}
function rowHtml(f,i){
  var sb=f.score>=70?' s-hi':(f.score>=45?' s-mid':'');
  return '<tr class="row-t" data-i="'+i+'"><td class="score'+sb+'">'+f.score+'</td>'+
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
    tb.innerHTML='<tr><td colspan="6" class="empty">No findings match.</td></tr>';
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
  det.innerHTML='<td colspan="6">'+details(f)+'</td>';
  tr.after(det);
});
more.addEventListener('click',()=>{shown+=PAGE;paint();});
document.querySelectorAll('th[data-k]').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.k; sortDir=(k===sortKey)?-sortDir:(k==='score'?-1:1); sortKey=k; apply();}));

/* A triage count is only useful if it takes you to the rows it counted, so
   each card carries the filter it stands for. */
document.querySelectorAll('[data-set]').forEach(function(el){
  el.addEventListener('click',function(){
    var p=el.dataset.set.split(':'),sel={fb:fb,fk:fk,fg:fg,fo:fo}[p[0]];
    if(!sel)return;
    fb.value='';fk.value='';fg.value='';fo.value='';
    sel.value=p.slice(1).join(':');
    apply();});});
/* Debounced: typing "network" used to run the whole pipeline seven times. */
let timer=null;
q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,140);});
[fb,fk,fg,fo].forEach(el=>el&&el.addEventListener('change',apply));
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


def _says_the_same(change, what: str) -> bool:
    """Would the `moved` line repeat what the prose already said?

    Both sides of the first non-platform delta, compared untruncated. A prose
    line built from the same delta contains both of them; one built from a
    different attribute does not.
    """
    for key, delta in sorted(change.deltas.items()):
        if key in ("platform_state", "platform_status"):
            continue
        if not (isinstance(delta, list) and len(delta) == 2):
            continue
        return all(str(side) in what for side in delta if side not in (None, ""))
    return False


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
            "name": display_name(change),
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
            # list of sixteen kinds reads as sixteen kinds of "feature", and
            # two thirds of them are not features at all.
            "group": group_of(change.kind),
            # Whose desk it lands on. The third axis and the only one that
            # answers "is this mine": measured M148 -> M151, the longest list
            # holds 2 of the 315 Breaking rows and the second shortest holds
            # 126, so length and urgency point opposite ways.
            "owner": owner_of(change),
            "paths": (change.locations or change.paths)[:3],
            "deltas": deltas[:6],
            "reasons": finding.reasons,
            "chromestatus": status.get("summary", ""),
        }
        # `what` already says "off -> on for Windows" for the kinds that have
        # a platform state, and "array<uint8> -> BigBuffer" for a Mojo field,
        # so repeating it under the prose prints the same arrow twice in one
        # cell.
        #
        # The test is made against the *raw* delta, not the payload's copy of
        # it. Two truncations sit between them -- `_trim` at 90 characters on
        # the way into `deltas`, `_moved` at 34 on the way out -- and `describe`
        # applies neither, so the two strings said the same thing and did not
        # match. A long generic type printed both:
        # `map<mojo_base.mojom.String16, ManifestLocalizedTextObject> ->
        # map<Locale, ManifestLocalizedTextObject>?` above its own truncation.
        row["moved"] = "" if _says_the_same(change, row["what"]) else _moved(row)
        # Drop empty values. Every consumer in the page guards for a missing
        # key, and on a run with --no-enrich `chromestatus` is empty on every
        # single row -- 3,120 of them on a real report.
        rows.append({k: v for k, v in row.items() if not _is_empty(v)})
    return rows


def _is_empty(value) -> bool:
    """Empty in the sense the page's guards mean -- and a number never is.

    This was `value not in ("", [], {}, None, False)`, and `0 == False` in
    Python, so every finding scoring zero lost its `score` key on the way into
    the payload. The page then rendered the literal string `undefined` in the
    Score column: 238 of 6,757 rows on a real M143 -> M151 run, 98 of 2,792 on
    an M148 one. Sorting broke with it, since `sortVal` returned `undefined`
    and fell through to the string comparator for those rows only.

    A score of zero is a real, reachable result -- base severity 35 for a
    removed pref, minus 45 for one that is not compiled on Windows, clamped at
    zero -- so it has to survive the trip.
    """
    if isinstance(value, bool):
        return value is False
    if isinstance(value, (int, float)):
        return False
    return value in ("", [], {}, None)


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


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _triage_html(report: Report) -> str:
    """The counts, each with the sentence saying what the bucket means.

    A number under one word is not triage; the sentence beside it is, and it
    was only ever in the markdown report.
    """
    counts = report.bucket_counts()
    return "".join(
        f'<button class="card {b}" data-set="fb:{b}">'
        f'<div class="n">{_n(counts.get(b, 0))}</div>'
        f'<div class="l">{_esc(BUCKET_LABELS[b])}</div>'
        f'<div class="m">{_esc(BUCKET_MEANINGS.get(b, ""))}</div></button>'
        for b in BUCKET_ORDER)


def _brief_html(summary: dict, limit: int = 200) -> str:
    """What Chromium says it shipped in this window, folded below the table.

    It was fetched on every run, written into `report.json` and `report.md`,
    and then left out of the one artifact people actually open. A reader
    looking at a row that says `CSSAnchorScope` reached stable had the
    paragraph explaining it three files away.

    Background, so it sits under the findings and stays closed: it is the
    answer to "why did this change", not to "what do I do".
    """
    entries = (summary or {}).get("milestone_brief") or []
    if not entries:
        return ""
    shown = entries[:limit]
    span = sorted({e.get("milestone") for e in entries if e.get("milestone")})
    scope = f" · M{span[0]}–M{span[-1]}" if span else ""
    count = (f"{len(shown)} of {_n(len(entries))}" if len(entries) > limit
             else _n(len(entries)))

    items = []
    for entry in shown:
        head = (f'<span class="ms">M{_esc(entry.get("milestone", "?"))}</span>'
                f'<span class="fname">{_esc(entry.get("name", ""))}</span>')
        if entry.get("shipping"):
            head += f'<span class="ship">{_esc(entry["shipping"])}</span>'
        body = ""
        if entry.get("summary"):
            body = f'<div class="fsum">{_esc(entry["summary"])}</div>'
        if entry.get("spec"):
            spec = _esc(entry["spec"])
            body += (f'<div class="fsum"><a href="{spec}" rel="noreferrer">'
                     f'{spec}</a></div>')
        items.append(f'<div class="feat">{head}{body}</div>')

    more = ""
    if len(entries) > limit:
        more = (f'<div class="why">{_n(len(entries) - limit)} more are in '
                f'<code>report.json</code> under '
                f'<code>summary.milestone_brief</code>.</div>')

    return (f'<details class="brief"><summary>What Chromium says shipped in '
            f'this window — {count} features{scope}</summary>'
            f'<div class="body">'
            f'<p class="why">Chromium\'s own words about the milestones being '
            f'adopted, newest first. These are <b>not</b> matched to the rows '
            f'above — the names are prose and the findings are identifiers — '
            f'so read them as background, not as a second opinion on any '
            f'single row.</p>{"".join(items)}{more}</div></details>')


def render(report: Report, platform: str = "windows") -> str:
    rows = _to_rows(report, platform)
    meta = report.meta or {}
    summary = report.summary or {}

    kinds = sorted({r["kind"] for r in rows})
    groups = [g for g, _ in KIND_GROUPS if any(r.get("group") == g for r in rows)]
    idle = summary.get("not_in_build") or 0

    # One sentence per story, stored once instead of once per row.
    stories = {}
    for finding in report.findings:
        key, headline = surfaces.story_of(finding.change)
        stories[key] = headline

    notes = []
    absent = sum(len(v) for v in (meta.get("missing_targets") or {}).values())
    if absent:
        notes.append(
            f"{absent} file(s) the target set asked for were not in one of the "
            f"two trees, so nothing they declare could be compared. "
            f"<code>report.json</code> names them under "
            f"<code>meta.missing_targets</code>.")
    notes_html = "".join(f'<div class="note">{n}</div>' for n in notes)

    option = lambda v, label="": f'<option value="{html.escape(v)}">{html.escape(label or v)}</option>'

    # Grouped, because a flat list of sixteen kinds reads as sixteen kinds of
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

    stats = summary.get("changes") or {}
    lede = (f"{_n(meta.get('facts_from', 0))} \u2192 "
            f"{_n(meta.get('facts_to', 0))} declarations read; "
            f"{_n(stats.get('total', len(rows)))} of them differ. ")
    lede += (f"{_n(idle)} score zero because Chromium's build conditions keep "
             f"the declaration out of the {html.escape(platform)} binary on "
             f"both sides of the change."
             if idle else
             "Every one of them is in the binary this product ships.")

    return f"""<title>{html.escape(TITLE)}</title>
<style>{_CSS}</style>
<div class="wrap">
<header class="top">
<div class="eyebrow">{html.escape(TITLE)}</div>
<h1><code>{html.escape(report.from_ref)}</code><span class="arrow">\u2192</span>
<code>{html.escape(report.to_ref)}</code></h1>
<div class="sub">platform {html.escape(platform)} \u00b7
target set {html.escape(str(meta.get('target_set', '?')))} \u00b7
generated {html.escape(str(meta.get('generated', '')))}</div>
<p class="lede">{lede} Each row opens with
<b class="mk-added">+</b>&nbsp;new, <b class="mk-modified">~</b>&nbsp;changed or
<b class="mk-removed">\u2212</b>&nbsp;gone.</p>
</header>
{notes_html}
<div class="cards">{_triage_html(report)}</div>
<div class="controls">
<input type="search" id="q" placeholder="Search name, signal, path, page\u2026">
<select id="fb"><option value="">All buckets</option>
{''.join(option(b, BUCKET_LABELS[b]) for b in BUCKET_ORDER)}</select>
<select id="fk"><option value="">All surfaces</option>
{surface_options}</select>
<select id="fg"><option value="">All consequences</option>
{''.join(option(g) for g in groups)}</select>
<select id="fo"><option value="">All owners</option>
{''.join(option(o, OWNER_LABELS[o]) for o in OWNER_ORDER)}</select>
<span class="muted" id="cnt"></span>
</div>
<div class="tablewrap"><table class="find">
<colgroup><col style="width:62px"><col style="width:132px">
<col style="width:31%"><col style="width:24%"><col style="width:16%">
<col style="width:150px"></colgroup>
<thead><tr>
<th data-k="score">Score</th><th data-k="bucket">Bucket</th>
<th data-k="name">What</th><th data-k="why">What happened</th>
<th data-k="where">Where</th><th data-k="kind">Surface</th>
</tr></thead><tbody id="tb"></tbody></table></div>
<button id="more" hidden></button>
<p class="more-note">Rows render in pages of 100 &mdash; the JSON below holds
every finding regardless of what is on screen. Click any row for its evidence,
its declaring line, and the reasoning behind its score.</p>
{_brief_html(summary)}
</div>
<script>window.__FINDINGS__={json.dumps(rows, ensure_ascii=False)};
window.__KINDS__={json.dumps(KIND_LABELS, ensure_ascii=False)};
window.__BUCKETS__={json.dumps(BUCKET_LABELS, ensure_ascii=False)};
window.__STORIES__={json.dumps(stories, ensure_ascii=False)};</script>
<script>{_JS}</script>
"""
