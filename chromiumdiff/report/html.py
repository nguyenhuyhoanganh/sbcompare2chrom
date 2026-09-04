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
import re
from typing import List

from ..diff import SIGNAL_LABELS, owner_of
from ..model import (BUCKET_LABELS, BUCKET_MEANINGS, BUCKET_ORDER, KIND_GROUPS,
                     KIND_LABELS, OWNER_LABELS, OWNER_ORDER, Report,
                     VERDICT_MEANINGS, group_of)
from .markdown import TITLE, display_name
from . import wording as surfaces

_CSS = """
/* One accent, one radius, one spacing rhythm, and no shadows at all. The
   palette is neutral-warm rather than blue-grey so the four bucket colours --
   which are the only saturated things on the page -- carry all of the meaning
   and none of the decoration. */
:root{
--bg:#faf9f7;--fg:#191817;--muted:#6c6a64;--faint:#9c9992;
--line:#e7e4de;--line2:#d9d5cd;--card:#fff;--sunk:#f5f3ef;
--brk:#c0392f;--beh:#a06a10;--new-b:#2c6b45;--hk:#77746d;
--accent:#2f5fa8;--accent-soft:#eaf0fb;
/* One radius, and it is small, because nothing on this page is a card. A
   14px corner with a drop shadow under it is the shape of a thing that floats
   above the document, and none of this floats: the table is the document.
   2px is a manufacturing tolerance, not a style -- enough that a 1px border
   does not look chipped at the corner, not enough to read as a pill. The
   second radius went when the last container that used it was flattened. */
--r1:2px;
color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#141413;--fg:#eeece7;--muted:#a19e96;--faint:#78756e;
--line:#2e2d2a;--line2:#3b3a36;--card:#1d1c1b;--sunk:#232220;
--brk:#f0857a;--beh:#e3ae57;--new-b:#7fc79b;--hk:#a19e96;
--accent:#7fa9e8;--accent-soft:#1c2433;
color-scheme:dark;}}
:root[data-theme=dark]{
--bg:#141413;--fg:#eeece7;--muted:#a19e96;--faint:#78756e;
--line:#2e2d2a;--line2:#3b3a36;--card:#1d1c1b;--sunk:#232220;
--brk:#f0857a;--beh:#e3ae57;--new-b:#7fc79b;--hk:#a19e96;
--accent:#7fa9e8;--accent-soft:#1c2433;
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
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;
border-radius:var(--r1)}

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
.lede{margin:15px 0 18px;font-size:.98rem;line-height:1.6;max-width:74ch;
color:var(--muted)}
.lede b{color:var(--fg);font-weight:600}

/* -- triage ladder ------------------------------------------------------- */
/* Four counts. The only thing worth encoding about them is the order, because
   the order is the reader's working order: 276 Breaking is the morning's job
   whatever the other three say.
   Two earlier versions encoded the wrong things. Four cards in a grid said
   "peers", when this is a ladder -- and it put 276 in one box and 1,240 in
   another, where the eye cannot compare them. Adding a proportional bar fixed
   the comparison and made it worse: the bar is longest on Housekeeping, so the
   heaviest mark on the page pointed at the bucket that matters least. A
   summary for triage cannot give its loudest signal to the thing you look at
   last.
   So: no bar, no box. Figures in one right-aligned column so they compare
   themselves, severity order down the page, and the sentence that says what
   the bucket means -- which is the part a reader actually needs and the part
   the cards had shrunk to a caption. */
.cards{border-top:1px solid var(--line)}
.card{--c:var(--hk);display:grid;
grid-template-columns:6ch minmax(0,1fr);
grid-template-areas:"n l" "n m";
column-gap:20px;row-gap:2px;
width:100%;padding:9px 4px 10px;text-align:left;font:inherit;color:inherit;
background:none;border:0;border-bottom:1px solid var(--line);cursor:pointer;
transition:background .13s ease}
.card:hover,.card:focus-visible{background:var(--sunk)}
.card .n{grid-area:n;align-self:start;text-align:right;color:var(--c);
font-size:1.2rem;font-weight:660;line-height:1.3;letter-spacing:-.015em;
font-variant-numeric:tabular-nums}
.card .l{grid-area:l;align-self:center;font-size:.87rem;font-weight:620}
.card .m{grid-area:m;max-width:82ch;color:var(--muted);font-size:.79rem;
line-height:1.5}
.card.breaking{--c:var(--brk)}
.card.behaviour{--c:var(--beh)}
.card.new{--c:var(--new-b)}
.card.housekeeping{--c:var(--hk)}

/* -- filter row ---------------------------------------------------------- */
/* The header, the triage and the filter row cost 660px of a 900px laptop
   before the first finding, which left the table a quarter of the screen no
   matter how tall its own box was allowed to be. The content all earns its
   place; the space around it did not. */
.controls{display:flex;flex-wrap:wrap;gap:9px;margin:18px 0 12px;
align-items:center}
input[type=search],select{background:var(--card);color:var(--fg);
border:1px solid var(--line);border-radius:var(--r1);padding:9px 12px;
font:inherit;font-size:.87rem;
transition:border-color .14s ease,box-shadow .14s ease}
input[type=search]{flex:1;min-width:230px}
input[type=search]::placeholder{color:var(--faint)}
input[type=search]:hover,select:hover{border-color:var(--line2)}
input[type=search]:focus,select:focus{outline:none;border-color:var(--accent);
box-shadow:0 0 0 3px var(--accent-soft)}
select{cursor:pointer}

/* -- picking more than one of something ---------------------------------- */
/* A `<select multiple>` needs a modifier key nobody discovers, has no way to
   say "all", and stands four rows tall in a bar that is one row. This is a
   disclosure holding checkboxes: closed it is the same shape as the control
   it replaces, open it is a bordered list.

   It is positioned over the page rather than pushing it down, which is what
   the native dropdown it replaces already did. The rule this page keeps --
   nothing floats -- is about the document, and a list that exists only while
   a control is open is not part of the document. It gets a border and no
   shadow, like everything else here. */
.pick{position:relative}
.pick>summary{list-style:none;cursor:pointer;white-space:nowrap;
background:var(--card);color:var(--fg);
border:1px solid var(--line);border-radius:var(--r1);padding:9px 12px;
font-size:.87rem;transition:border-color .14s ease}
.pick>summary::-webkit-details-marker{display:none}
.pick>summary::after{content:" \\25be";color:var(--faint)}
.pick>summary:hover{border-color:var(--line2)}
.pick[open]>summary{border-color:var(--accent)}
.pick summary b{font-weight:600}
.pick .opts{position:absolute;z-index:30;top:calc(100% + 4px);left:0;
min-width:100%;max-height:290px;overflow-y:auto;padding:5px;
background:var(--card);border:1px solid var(--line2);border-radius:var(--r1)}
.pick .opts label{display:flex;align-items:center;gap:8px;
padding:5px 8px;white-space:nowrap;cursor:pointer;font-size:.85rem;
border-radius:var(--r1)}
.pick .opts label:hover{background:var(--sunk)}
.pick .opts input{margin:0;flex:none}
/* The `<optgroup>` heading, which the checkbox list has to keep: a flat list
   of sixteen kinds reads as sixteen kinds of feature, and two thirds of them
   are not features. Set like the other small headings on the page rather than
   as bold body text, so it reads as a divider and not as a choice. */
.pick .opts .head{display:block;padding:9px 8px 3px;
font-size:.68rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
color:var(--faint)}
.pick .opts .head:first-child{padding-top:3px}
.pick .opts .clear{width:100%;text-align:left;font:inherit;font-size:.8rem;
color:var(--muted);background:none;border:0;border-top:1px solid var(--line);
margin-top:4px;padding:7px 8px 3px;cursor:pointer}
.pick .opts .clear:hover{color:var(--fg)}

/* The exclude box. Narrower than search because it takes a few words rather
   than a phrase, and it sits beside search because they are the same kind of
   question asked in opposite directions. */
#x{flex:0 1 250px;min-width:150px}
#x:not(:placeholder-shown){border-color:var(--brk)}
#cnt{margin-left:auto;font-size:.82rem;color:var(--faint);
font-variant-numeric:tabular-nums}

/* -- table --------------------------------------------------------------- */
/* Its own scroll box, so the column headers stay put: a sticky <th> sticks to
   the nearest scrollport, and the wrapper is already one because overflow-x
   makes overflow-y a scroll container too. */
/* Tall enough to be the page rather than a window onto it. 74vh capped at
   860px left a quarter of the screen empty below the box and showed ten rows
   on a laptop, which is a scroll every ten findings. The cap is kept -- above
   about 1,500px the header has scrolled away and a taller box only makes the
   sticky row harder to reach -- but it is now far enough up that no ordinary
   display meets it. */
.tablewrap{overflow:auto;max-height:min(88vh,1500px);border:1px solid var(--line);
background:var(--card)}
/* table-layout:fixed is the single biggest lever here. With the default auto
   layout, column widths depend on cell content, so inserting one expanded row
   makes the browser re-measure every cell before it can paint. Fixed layout
   takes the widths from the colgroup and never looks at content. */
table.find{border-collapse:separate;border-spacing:0;table-layout:fixed;
width:100%;font-size:.875rem;min-width:900px}
table.find th,table.find td{text-align:left;padding:11px 14px;
border-bottom:1px solid var(--line);vertical-align:top;
overflow-wrap:break-word}
table.find th{font-weight:600;color:var(--muted);font-size:.7rem;
text-transform:uppercase;letter-spacing:.075em;cursor:pointer;user-select:none;
white-space:nowrap;position:sticky;top:0;z-index:1;
background:var(--card);padding-top:13px;padding-bottom:11px;
box-shadow:inset 0 -1px 0 var(--line)}
table.find th:hover{color:var(--fg)}
/* `table-layout:fixed` with no widths splits six columns evenly, which gave a
   62-character Mojo identifier the same room as the word "Breaking". What
   varies between rows is the What column, and it is the column that wraps, so
   it gets the width the fixed ones do not need. */
table.find th:nth-child(1){width:62px}
table.find th:nth-child(2){width:112px}
table.find th:nth-child(3){width:40%}
table.find th:nth-child(4){width:19%}
table.find th:nth-child(5){width:16%}
table.find th:nth-child(6){width:13%}
table.find tbody tr:last-child td{border-bottom:none}
/* Rows outside the viewport skip layout entirely; the intrinsic size keeps the
   scrollbar honest so skipping does not make the page jump. */
table.find tbody tr{content-visibility:auto;contain-intrinsic-size:auto 46px}
tbody tr.row-t{cursor:pointer}
tbody tr.row-t:hover td{background:var(--sunk)}
/* The expanded panel is already marked by its ground; a coloured rail on top
   of that is a second answer to a question nobody asked twice. */
tbody tr.det td{background:var(--sunk);font-size:.85rem}

.score{font-variant-numeric:tabular-nums;font-weight:650;letter-spacing:-.015em;
font-size:.95rem;color:var(--muted)}
.s-hi{color:var(--brk)}.s-mid{color:var(--beh)}

/* Squared off. A capsule is the shape of a button on a phone, and none of
   these are buttons -- they are labels on a line of data. `999px` was on five
   different elements here and it is the single thing that dated the page. */
.pill{display:inline-block;padding:2px 7px;border-radius:var(--r1);font-size:.71rem;
font-weight:600;letter-spacing:.01em;white-space:nowrap;
background:color-mix(in srgb,currentColor 13%,transparent)}
.b-breaking{color:var(--brk)}.b-behaviour{color:var(--beh)}
.b-new{color:var(--new-b)}.b-housekeeping{color:var(--hk)}

.mk{font-weight:700;padding-right:6px;font-variant-numeric:tabular-nums}
/* The marker takes the bucket colour rather than a copy of it. There were
   six tokens here carrying three values -- `--new`/`--chg`/`--gone` held the
   same hex as `--new-b`/`--beh`/`--brk` in all three themes, and existed only
   to feed these three rules. Tuning one for contrast would have left the
   other behind and drifted the `+ ~ -` markers off the buckets they name. */
.mk-added{color:var(--new-b)}.mk-removed{color:var(--brk)}
.mk-modified{color:var(--beh)}
.where{color:var(--muted);font-size:.815rem;line-height:1.45}
.grp{font-size:.715rem;color:var(--faint);margin-top:3px}
.moved{font-size:.775rem;color:var(--faint);margin-top:4px;line-height:1.45}
ul.tight{margin:7px 0;padding-left:19px;line-height:1.7}
.empty{padding:44px;text-align:center;color:var(--faint)}
.note{background:var(--card);border:1px solid var(--line);
border-left:3px solid var(--beh);padding:12px 15px;margin:0 0 16px;
font-size:.87rem;color:var(--muted)}
#more{margin-top:14px;width:100%;padding:12px;background:var(--card);
color:var(--muted);border:1px solid var(--line);border-radius:var(--r1);
font:inherit;font-size:.86rem;font-weight:600;cursor:pointer;
transition:border-color .14s ease,color .14s ease,background .14s ease}
#more:hover{border-color:var(--accent);color:var(--accent);background:var(--sunk)}
.more-note{color:var(--faint);font-size:.81rem;margin:14px 0 0;line-height:1.6;
max-width:78ch}

/* -- shipped-feature brief ----------------------------------------------- */
/* Background, not findings, so it sits below the table and stays folded. */
.brief{margin:26px 0 0;background:var(--card);border:1px solid var(--line);
overflow:hidden}
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
border-radius:var(--r1);padding:1px 6px;margin-right:8px;vertical-align:1px;
font-variant-numeric:tabular-nums}
.brief .fname{font-weight:600;font-size:.88rem}
.brief .ship{color:var(--faint);font-size:.75rem;margin-left:6px}
.brief .fsum{color:var(--muted);font-size:.83rem;line-height:1.55;margin-top:5px}
.brief a{color:var(--accent)}

/* Provenance. Sunk rather than boxed: it sits inside a row that is already an
   inset panel, and a second border there reads as a second table. */
.prov{margin:12px 0 2px;padding-top:10px;border-top:1px solid var(--line)}
.prov h4{margin:0 0 7px;font-size:.78rem;font-weight:650;letter-spacing:.03em;
text-transform:uppercase;color:var(--muted)}
/* Which rows carry evidence, without spending a column on it. A 3px edge is
   visible while scanning and invisible while reading. */
tr.row-t td:first-child{position:relative}
tr.p-exact td:first-child::before,tr.p-cl td:first-child::before{
content:"";position:absolute;left:0;top:6px;bottom:6px;width:3px;
background:var(--new-b)}
tr.p-cl td:first-child::before{background:var(--accent)}
tr.p-skipped td:first-child::before{content:"";position:absolute;left:0;
top:6px;bottom:6px;width:3px;background:var(--line2)}
button.lookup{margin-top:7px;font:inherit;font-size:.85rem;font-weight:550;
color:var(--accent);background:var(--accent-soft);border:1px solid transparent;
border-radius:var(--r1);padding:5px 11px;cursor:pointer}
button.lookup:hover:not(:disabled){border-color:var(--accent)}
button.lookup:disabled{color:var(--muted);background:var(--sunk);cursor:default}
/* What the issue is actually about, in the reporter's words. Its own line:
   the issue number and the CL count are metadata, this is the sentence. */
.prov .isum{display:block;margin-top:4px;font-weight:400;letter-spacing:0;
text-transform:none;color:var(--fg);font-size:.88rem;line-height:1.5}
/* An issue is not a CL, and the two blocks were identical boxes stacked on
   each other, so a reader scanning the panel met "Issue 4012" in the same
   frame as "CL 7982397" and had to read the label to know which was which.
   The tracker side is sunk and rail-marked in the accent colour instead. */
/* An issue is subordinate to the CL that cited it, and that is a relation
   the layout can state: it is indented under it. The first attempt made it a
   rounded box with a coloured rail down the edge -- the same device the
   triage cards had just been rid of, kept in one corner of the page. */
.prov.iss{margin-left:15px;padding-top:9px}
.prov.iss h4{margin-top:0}
/* A dead link with no reason reads as a broken report. The reason is the same
   every time and it is not about this reader, so it is stated once, plainly,
   inside the block it explains. */
/* Above the answer and outside it, because it qualifies whatever the answer
   turned out to be. Amber rather than red: the row is not wrong, it is
   unfinished, and the reader can finish it by opening the row again. */
.warn{margin:12px 0 0;padding:8px 11px;font-size:.82rem;line-height:1.5;
color:var(--beh);background:color-mix(in srgb,var(--beh) 9%,transparent);
border-left:2px solid var(--beh)}
.prov .why403{margin:6px 0 0;color:var(--muted);font-size:.8rem;
line-height:1.5}
.prov .moreiss{margin-top:8px}
.prov .none{margin:0;color:var(--muted);font-size:.88rem;line-height:1.55}
/* Above a list of leads, not instead of one. It carries the disclaimer the
   badges cannot: that these CLs are on the page because the reader asked and
   not because any of them names the fact. */
/* Stated before the evidence, because it changes how the evidence reads. */
p.grp{margin:0 0 10px;padding:7px 10px;font-size:.85rem;line-height:1.5;
color:var(--fg);background:var(--sunk);border-left:2px solid var(--accent)}
.prov .lead{margin:0 0 7px;color:var(--muted);font-size:.88rem;line-height:1.55;
padding-left:9px;border-left:2px solid color-mix(in srgb,var(--faint) 45%,transparent)}
.prov .none code{font-size:.85em}
.prov .pool{margin-left:9px;font-weight:400;letter-spacing:0;text-transform:none;
color:var(--faint);font-size:.75rem}
ul.cls{margin:0;padding:0;list-style:none}
ul.cls li{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;
padding:3px 0;font-size:.88rem;line-height:1.5}
a.cl{color:var(--accent);text-decoration:none;font-weight:600;
font-variant-numeric:tabular-nums;white-space:nowrap}
a.cl:hover{text-decoration:underline}
/* An issue is not a CL, and the heading of the issue block had been wearing
   the CL link's class. So one issue number was blue and bare as a heading and
   grey under a dotted rule three lines below it, and the two were the same
   number. One treatment in two sizes: a heading is the accent colour and
   carries the same dotted rule the inline chip does, so the rule is what says
   "tracker link" in both places and the size says which one you are looking
   at. */
a.issl{color:var(--accent);text-decoration:none;font-weight:600;
font-variant-numeric:tabular-nums;white-space:nowrap;
border-bottom:1px dotted color-mix(in srgb,var(--accent) 45%,transparent)}
a.issl:hover{border-bottom-color:var(--accent)}
.cls .when{color:var(--faint);font-size:.78rem;font-variant-numeric:tabular-nums;
white-space:nowrap}
/* Left-packed: a growing subject pushed the issue link to the far edge of
   a 1,320px row, where it read as a separate column. */
.cls .subj{flex:0 1 auto;min-width:0;color:var(--fg)}
.cls a.bug{color:var(--muted);font-size:.78rem;white-space:nowrap;
text-decoration:none;border-bottom:1px dotted var(--line2)}
.cls a.bug:hover{color:var(--accent)}
.cls .chain,.cls .in{font-size:.72rem;color:var(--muted);white-space:nowrap;
background:var(--sunk);border:1px solid var(--line);border-radius:var(--r1);
padding:0 6px}
.cls .in{border-style:dashed;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
/* Restricted: still a link, visibly not a promise. The width is stated
   because `border-bottom-style` alone falls back to `medium` -- on the
   heading, which had no border to restyle, that drew a rule three times the
   weight of the one on the chip beside it. */
/* The chip that opens an issue in place. Sized and coloured as the link it
   replaces, because it is the same thing to a reader -- what changes is where
   the answer arrives, not what they are clicking. */
button.ibtn{font:inherit;font-size:.78rem;white-space:nowrap;cursor:pointer;
background:none;border:0;padding:0;color:var(--muted);
border-bottom:1px dotted var(--line2)}
button.ibtn:hover{color:var(--accent);border-bottom-color:var(--accent)}
button.ibtn.on{color:var(--accent);border-bottom-style:solid;
border-bottom-color:var(--accent)}
button.ibtn.on::after{content:"";margin-left:4px}
button.ibtn.bug-x{color:var(--faint);border-bottom-style:dashed;
border-bottom-color:var(--faint)}
button.ibtn.bug-x:hover{color:var(--beh);border-bottom-color:var(--beh)}
/* Opened inside the CL's own line, indented under it, so several stacked read
   as belonging to that CL rather than to the row.
   `ul.cls li` is a flex row, so a panel appended to it is another item on that
   row and sits to the right of the subject until it happens not to fit. Given
   the whole line it drops below instead, and two of them stack rather than
   competing for the width the subject was using. */
.ihist{flex:0 0 100%;width:100%;margin:7px 0 4px;padding:8px 0 2px 11px;
border-left:2px solid var(--line2)}
.ihist h4{margin:0 0 5px}
.ihist .cls{margin:0}
.ihist .none{margin:0}
.cls a.bug-x,a.issl.bug-x{color:var(--faint);
border-bottom:1px dashed var(--faint)}
.cls a.bug-x:hover,a.issl.bug-x:hover{color:var(--beh);
border-bottom-color:var(--beh)}
/* A word, not a glyph: U+26BF rendered as a tofu box in the report's own
   font stack, which reads as a rendering fault rather than as a warning. */
.locked{margin-left:5px;font-size:.68rem;font-weight:650;letter-spacing:.04em;
text-transform:uppercase;color:var(--beh);
background:color-mix(in srgb,var(--beh) 14%,transparent);
padding:1px 5px;border-radius:var(--r1);white-space:nowrap}
/* The evidence badge is the one place the two strengths must not blur. */
.ev{font-size:.68rem;font-weight:650;letter-spacing:.04em;text-transform:uppercase;
padding:1px 6px;border-radius:var(--r1);white-space:nowrap}
/* Every badge is drawn the same way and separated by colour and by the word
   it carries. `introduced` was a filled block for a while -- the one solid
   badge on the page, on the grounds that it is the one verdict whose answer
   *is* the change -- and it turned a list of six verdicts into one shout and
   five whispers. The ladder is already written down; the badge does not have
   to perform it. */
.ev-introduced{color:var(--new-b);
background:color-mix(in srgb,var(--new-b) 18%,transparent)}
.ev-exact{color:var(--new-b);background:color-mix(in srgb,var(--new-b) 13%,transparent)}
/* A pure rename changes no line, so it gets its own badge rather than
   borrowing one that claims a line was edited. */
.ev-moved{color:var(--new-b);background:color-mix(in srgb,var(--new-b) 10%,transparent)}
/* Between the two: the author's own words, but not the declaring line. */
.ev-described{color:var(--accent);background:var(--accent-soft)}
.ev-declares{color:var(--beh);background:color-mix(in srgb,var(--beh) 15%,transparent)}
/* The two that name no fact. Grey on purpose: every colour in this palette is
   already spoken for by a verdict that identifies something, and a lead
   wearing one would read as the weakest of those rather than as neither. */
.ev-crowded,.ev-touched{color:var(--faint);
background:color-mix(in srgb,var(--faint) 12%,transparent)}

/* -- asking about the report --------------------------------------------- */
/* Present only when a server answered `/api/ping` with a chat on the other
   end. The same file opened from a disk has no launcher at all, which is the
   rule the row lookups already follow.

   It does not float and it is not a circle. Everything above says this page
   has no cards and no shadows, and a chat bubble is the most card-shaped
   thing in the vocabulary -- so it is a docked control with one border, and
   the panel it opens is a column of the document rather than a sheet over it.
   The launcher sits still while the page scrolls because it is a way in, not
   a part of the report. */
#askbtn{position:fixed;right:18px;bottom:18px;z-index:40;
display:none;align-items:center;gap:8px;
padding:9px 14px;font:inherit;font-size:.82rem;font-weight:600;
color:var(--fg);background:var(--card);
border:1px solid var(--line2);border-radius:var(--r1);cursor:pointer}
#askbtn:hover{border-color:var(--accent);color:var(--accent)}
#askbtn::before{content:"";width:7px;height:7px;border-radius:50%;
background:var(--accent);flex:none}
#askbtn.on{display:inline-flex}

#ask{position:fixed;top:0;right:0;bottom:0;width:min(460px,100vw);z-index:41;
display:none;flex-direction:column;
background:var(--card);border-left:1px solid var(--line2)}
#ask.on{display:flex}
#ask header{display:flex;align-items:baseline;gap:10px;flex:none;
padding:14px 16px;border-bottom:1px solid var(--line)}
/* The pair of refs is long and the title is not, so the title holds its line
   and the refs give way. Letting both wrap turned a one-line header into
   three and pushed the conversation down the panel. */
#ask header b{font-size:.86rem;font-weight:650;white-space:nowrap;flex:none}
#ask header span{color:var(--faint);font-size:.74rem;
flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#ask header button{margin-left:auto;font:inherit;font-size:.78rem;
color:var(--muted);background:none;border:0;cursor:pointer;padding:2px 4px}
#ask header button:hover{color:var(--fg)}
#asklog{flex:1;overflow-y:auto;padding:14px 16px;font-size:.87rem;
line-height:1.6;overscroll-behavior:contain}
#askform{flex:none;display:flex;gap:8px;padding:12px 16px;
border-top:1px solid var(--line)}
#askin{flex:1;font:inherit;font-size:.87rem;resize:none;
padding:8px 10px;color:var(--fg);background:var(--bg);
border:1px solid var(--line2);border-radius:var(--r1)}
#askform button{font:inherit;font-size:.82rem;font-weight:600;padding:0 14px;
color:var(--card);background:var(--accent);border:0;
border-radius:var(--r1);cursor:pointer}
#askform button:disabled{background:var(--faint);cursor:default}

.qa{margin:0 0 16px}
.qa.you{color:var(--fg);font-weight:600;
padding-left:11px;border-left:2px solid var(--accent)}
.qa.them p{margin:0 0 9px}
.qa.them p:last-child{margin-bottom:0}
.qa.err{color:var(--brk)}
.qa ul{margin:0 0 9px;padding-left:1.15em}
.qa li{margin:0 0 3px}
/* A uid is the longest unbroken token an answer contains and also the one it
   cites most, so it is the one thing guaranteed to be wider than this panel.
   Left alone it ran off the right edge and the identifier the reader was
   being sent to was the part that got cut. */
.qa code{overflow-wrap:anywhere;word-break:break-word}
.qa pre{margin:8px 0;padding:9px 11px;overflow-x:auto;
background:var(--sunk);border:1px solid var(--line);border-radius:var(--r1);
font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
font-size:.78rem;line-height:1.5}
/* The work is shown, folded. What a query was is the difference between an
   answer a reader can check and one they have to believe, and it is also the
   thing they do not want in front of them once they have. */
.qa details{margin:0 0 10px;font-size:.79rem}
.qa summary{color:var(--muted);cursor:pointer;list-style:none;
padding:3px 0}
.qa summary::-webkit-details-marker{display:none}
.qa summary::before{content:"› ";color:var(--faint)}
.qa details[open] summary::before{content:"⌄ "}
.qa summary:hover{color:var(--fg)}
.qa .ran{color:var(--faint)}
.asking{color:var(--faint);font-size:.8rem}
@media (max-width:720px){#ask{width:100vw;border-left:0}}
"""

_JS = """
/* Rendering is windowed, lazy and delegated, because a full upgrade is thousands
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
/* Five fields arrive as indices into a table because their values repeat
   across thousands of rows -- `group` has three distinct values and was
   costing 58 KB of the download. Put back in one pass here so that every
   reader below sees ordinary strings and none of them has to know. */
(function(){const P=window.__POOL__||{};
for(const field in P){const table=P[field];
  for(let i=0;i<DATA.length;i++){const v=DATA[i][field];
    if(typeof v==='number')DATA[i][field]=table[v];}}})();
const kindLabel=f=>KINDS[f.kind]||f.kind, bucketLabel=f=>BUCKETS[f.bucket]||f.bucket,
whyLabel=f=>STORIES[f.why]||f.why||'';
/* Sized for the weakest machine that has to open this, not the fastest --
   but the row that is off screen costs almost nothing now that
   `content-visibility:auto` lets it skip layout, so the page holds twice what
   it did and the reader meets the button half as often. */
const PAGE=200;
const q=document.getElementById('q'),x=document.getElementById('x'),
fb=document.getElementById('fb'),
fk=document.getElementById('fk'),fg=document.getElementById('fg'),
fo=document.getElementById('fo'),fp=document.getElementById('fp'),
tb=document.getElementById('tb'),cnt=document.getElementById('cnt'),
more=document.getElementById('more');
let sortKey='score',sortDir=-1,shown=PAGE,view=DATA;
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
/* Five states, and they are not degrees of the same thing: `exact` and `cl`
   say a CL was found, `weak` says CLs are listed but none of them names this
   fact, `none` says the scan ran and matched nothing, `skipped` says nobody
   looked. Collapsing any of them into "no CL" -- or `weak` into `cl` -- is the
   mistake the whole stage exists to avoid. */
var WEAK={crowded:1,touched:1};
/* Both of these are a changed line tied to this identifier; `introduced` adds
   which direction the line moved. The filter asks whether a diff proved the
   CL, so both belong in the same state. Testing for `exact` alone left the
   strongest verdict on the page outside the option for strong evidence --
   37 CLs of a real top 150 -- and put those rows under "Has a CL" beside the
   ones found by a commit message. */
var PROVED={introduced:1,exact:1};
function allWeak(f){
  return f.cls&&f.cls.length&&f.cls.every(function(c){return WEAK[c.m];});
}
function provState(f){
  if(f.cls&&f.cls.length){
    if(allWeak(f))return 'weak';
    return f.cls.every(function(c){return PROVED[c.m];})?'exact':'cl';
  }
  if(f.cl_pool===undefined)return 'unasked';
  return f.no_diffs?'skipped':'none';
}
function hayOf(f){
  if(f._raw===undefined)
    f._raw=f.name+' '+f.kind+' '+(f.what||'')+' '+(f.where||'')+' '+whyLabel(f)+' '
      +(f.signals||[]).join(' ')+' '+(f.paths||[]).join(' ')
      +' '+(f.chromestatus||'');
  return f._raw;
}

/* The words a row is made of, with `AIManager` counted as `ai` + `manager`
   and `site_settings` as `site` + `settings`. Camel humps are separated first
   so the split can be on non-alphanumerics alone, which avoids a lookbehind
   that not every browser has. */
function tokensOf(f){
  if(f._tk===undefined)
    f._tk=hayOf(f).replace(/([a-z0-9])([A-Z])/g,'$1 $2')
                  .replace(/([A-Z]+)([A-Z][a-z])/g,'$1 $2')
                  .toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  return f._tk;
}

/* How many words a term may span. `webgpu` is two (`web`+`gpu`); nothing
   anyone types to exclude a topic is more than a handful. */
var SPAN=4;

/* Does `term` name this row?
 *
 * A term matches a run of whole consecutive words, so `ai` finds `AIManager`
 * and `AutofillAiOrder` and does not find `EmailVerification` -- which plain
 * substring did, along with 163 other rows on a real report, because `ai` is
 * inside `email`, `available`, `chain` and `failed`.
 *
 * Whole words, not a prefix of one: matching a prefix let `settings` reach
 * `SqlDiskCacheSynchronousOff`. A trailing `*` asks for the prefix anyway,
 * which is what `cookie*` needs to reach `Cookies`.
 */
function hasTerm(f,term){
  var star=term.charAt(term.length-1)==='*';
  var want=star?term.slice(0,-1):term;
  if(!want)return false;
  var t=tokensOf(f);
  for(var i=0;i<t.length;i++){
    var acc='';
    for(var k=0;k<SPAN&&i+k<t.length;k++){
      acc+=t[i+k];
      if(star?acc.indexOf(want)===0:acc===want)return true;
      if(acc.length>=want.length)break;
    }
  }
  return false;
}

/* Comma-separated, because that is how anybody writes a list. Blank entries
   are dropped so a trailing comma while typing does not exclude everything. */
function terms(value){
  return String(value||'').toLowerCase().split(',')
    .map(function(s){return s.trim();}).filter(Boolean);
}

/* Ticked boxes, in the order they appear. No box ticked means no filter,
   which is what "All buckets" says and what a single select could not. */
function picked(el){
  if(!el)return [];
  return Array.prototype.slice.call(el.querySelectorAll('input:checked'))
    .map(function(i){return i.value;});
}

var SEL={b:[],k:[],g:[],o:[],p:[]},EXCL=[];

function readFilters(){
  SEL={b:picked(fb),k:picked(fk),g:picked(fg),o:picked(fo),p:picked(fp)};
  EXCL=terms(x&&x.value);
}

/* What a closed picker says. The first choice by name, and a count for the
   rest: "Breaking +2" rather than three labels the control has no room for.
   Untouched it says what the single select said, so a report nobody has
   filtered reads exactly as it did before. */
function pickLabels(){
  [fb,fk,fg,fo,fp].forEach(function(el){
    if(!el)return;
    var on=Array.prototype.slice.call(el.querySelectorAll('input:checked'));
    var sum=el.querySelector('summary');
    if(!sum)return;
    if(!on.length){sum.textContent=el.dataset.all||'All';return;}
    var first=on[0].parentNode.querySelector('span');
    var text=first?first.textContent:on[0].value;
    sum.textContent=on.length>1?text+' +'+(on.length-1):text;});
}

function clearPick(el){
  if(!el)return;
  el.querySelectorAll('input:checked').forEach(function(i){i.checked=false;});
}

function setPick(el,value){
  if(!el)return;
  el.querySelectorAll('input').forEach(function(i){i.checked=i.value===value;});
}

function provPasses(f,want){
  var st=provState(f);
  return want==='cl' ? (st==='cl'||st==='exact') : st===want;
}

/* Within one filter the choices are OR -- Breaking *or* Behaviour change --
   and between filters they stay AND, which is what the single selects did and
   the only reading that lets the four narrow each other. */
function match(f,t){
  if(SEL.p.length&&!SEL.p.some(function(v){return provPasses(f,v);}))return false;
  if(SEL.b.length&&SEL.b.indexOf(f.bucket)<0)return false;
  if(SEL.k.length&&SEL.k.indexOf(f.kind)<0)return false;
  if(SEL.g.length&&SEL.g.indexOf(f.group)<0)return false;
  if(SEL.o.length&&SEL.o.indexOf(f.owner)<0)return false;
  for(var i=0;i<EXCL.length;i++)if(hasTerm(f,EXCL[i]))return false;
  if(!t)return true;
  if(f._hay===undefined)f._hay=hayOf(f).toLowerCase();
  return f._hay.indexOf(t)!==-1;
}
/* Built only when a row is actually expanded. This was half the payload. */
/* A row that is one fragment of a larger change says so, and says what the
   largest thing in that change scores. Read alone a parameter of an enabled
   feature is a 15-point "New surface" row, and the sentence that bucket
   carries -- nothing switches it on -- is false of it: the feature does, from
   another row in the same report. */
function groupNote(f){
  if(!f.grp)return '';
  var more=f.grp.c-1;
  return '<p class="grp"><b>Part of a larger change</b> \u2014 '+esc(f.grp.n)+
    ', '+f.grp.c+' findings in all'+(more?' ('+more+' other'+(more===1?'':'s')+
    ' in this report)':'')+
    (f.grp.t>f.score?'. The heaviest of them scores <b>'+f.grp.t+
      '</b>, so read that one first.':'.')+'</p>';
}
function details(f){
  const L=[];
  if(f.signals&&f.signals.length)L.push('<li><b>Signals:</b> '+esc(f.signals.join(', '))+'</li>');
  if(f.paths&&f.paths.length)L.push('<li><b>Declared in:</b> <code>'+esc(f.paths.join(', '))+'</code></li>');
  (f.deltas||[]).forEach(d=>L.push('<li><b>'+esc(d[0])+':</b> <code>'+esc(d[1])+'</code> \\u2192 <code>'+esc(d[2])+'</code></li>'));
  if(f.chromestatus)L.push('<li><b>Chromestatus:</b> '+esc(f.chromestatus)+'</li>');
  if(f.reasons&&f.reasons.length)L.push('<li class="muted"><b>Score:</b> '+esc(f.reasons.join(' \\u00b7 '))+'</li>');
  return groupNote(f)+'<ul class="tight">'+L.join('')+'</ul>'+provenance(f);
}
/* The review behind the row. The strengths are never levelled: `exact` means
   that CL edited a line carrying this identifier, `declares` means it edited
   the body of the declaration, and `crowded` and `touched` mean it named
   nothing and is a lead. The pool it was picked from is printed with it,
   because "1 of 62 CLs that touched this file" is what makes the one CL mean
   anything. */
/* What each verdict actually claims. The badge is one word because a row has
   room for one word; the sentence is what the word stands for, and a reader
   who has not memorised the ladder needs it on hover rather than in the
   README. Embedded from `model.VERDICT_MEANINGS` rather than written here,
   because the same seven sentences answer the same question at a command
   line, and two copies of an explanation drift into two explanations. */
var EVID=window.__EVID__||{};
function clRow(c,strong){
  var u='https://chromium-review.googlesource.com/c/chromium/src/+/'+c.n;
  /* A restricted issue keeps its link -- the reader may well be the one
     person who can open it -- but says so first. More than four in ten of the
     issues a real report links answer 403, and a dead link with no warning
     reads as a broken tool. `Fixed:` is shown apart from `Bug:` because closing an issue
     and referencing one are different claims. */
  var b=(c.b||[]).map(function(g){
    var label=(g.f?'fixes ':'issue ')+esc(g.i);
    /* Served, the chip opens the issue's own CL history in place. That is the
       question a reader actually has at this point -- "what else touched this
       bug" -- and the tracker cannot always answer it: four in ten issues
       return 403, while the CLs citing them are public on Gerrit either way.
       Off a disk there is nothing to ask, so it stays the link it always was. */
    if(LIVE)
      return '<button class="ibtn'+(g.r?' bug-x':'')+'" data-issue="'+esc(g.i)+
        '" title="show the CLs that cite this issue">'+label+'</button>';
    return '<a class="bug'+(g.r?' bug-x':'')+'" href="'+
      'https://issues.chromium.org/issues/'+g.i+'" target="_blank"'+
      ' rel="noreferrer" title="'+(g.r?'access-restricted: opens only with '+
      'Google credentials':'public issue')+'">'+label+'</a>'+
      (g.r?'<span class="locked">restricted</span>':'');
    }).join(' ');
  return '<li><a class="cl" href="'+u+'" target="_blank" rel="noreferrer">CL '+
    c.n+'</a><span class="when">'+esc(c.d)+'</span>'+
    (strong&&c.m?'<span class="ev ev-'+c.m+'" title="'+esc(EVID[c.m]||'')+
      '">'+esc(c.m)+'</span>':'')+
    '<span class="subj">'+esc(c.s)+'</span>'+(b?' '+b:'')+'</li>';
}
/* One issue, rendered the same whether a run baked it in or a click just
   fetched it. Two renderers for one thing is how the served page and the
   mailed file start disagreeing about what an issue looks like. */
function issueHtml(i){
  /* How long the issue has been worked, from the CLs already in hand. No
     request, and it is the one thing the tracker page would tell a reader who
     cannot open the tracker page. */
  var cls=i.cls||[],
      ds=cls.map(function(c){return c.d;}).filter(Boolean).sort(),
      span=ds.length>1&&ds[0]!==ds[ds.length-1]
        ? ds[0]+' \u2192 '+ds[ds.length-1] : (ds[0]||''),
      total=i.total||cls.length;
  return '<h4><a class="issl'+(i.restricted?' bug-x':'')+
    '" href="https://issues.chromium.org/issues/'+esc(i.id)+
    '" target="_blank" rel="noreferrer">Issue '+esc(i.id)+'</a>'+
    (i.restricted?'<span class="locked">restricted</span>':'')+
    '<span class="pool">'+total+' CL'+(total===1?'':'s')+' cite it'+
    (total>cls.length?', newest '+cls.length+' shown':'')+
    (span?' \u00b7 '+esc(span):'')+'</span>'+
    (i.t?'<span class="isum">'+esc(i.t)+'</span>':'')+'</h4>'+
    /* Why the link will not open, stated where the link is. "Restricted"
       alone reads as a fault in the report; 403 with its cause reads as a
       fact about the tracker, which is what it is. */
    (i.restricted?'<p class="why403">HTTP 403 \u2014 this issue sits in a '+
      'restricted tracker component (security, abuse, or Google-internal). '+
      'It opens only for an account cleared for that component, so a public '+
      'Chromium account gets the same 403. The CLs below are public and '+
      'carry what the issue was about.</p>':'')+
    (cls.length
      ? '<ul class="cls">'+cls.map(function(c){return clRow(c,false);}).join('')+
        '</ul>'
      : '<p class="none">Gerrit indexes no CL citing this issue.</p>');
}
/* Gerrit's own record of a revert or a cherry-pick. Free in the search
   response, and the one thing that makes a flag's launch/revert/reland
   history readable without reading every subject twice. */
function chain(c){
  var out='';
  if(c.rv)out+='<span class="chain">reverts '+c.rv+'</span>';
  if(c.cp)out+='<span class="chain">cherry-pick of '+c.cp+'</span>';
  if(c.f)out+='<span class="in">in '+esc(c.f.split('/').pop())+'</span>';
  return out;
}
/* Live mode is discovered, never baked in. The same file opened from a disk
   fails this fetch and stays exactly as static as it was; served by
   `chromiumdiff serve` it answers, and rows gain a lookup button. */
var LIVE=false;
/* The token the chat routes want. It is read here rather than embedded in the
   page, so this file saved to a disk and passed on grants nothing: what it
   carries is the code to ask, never the permission. */
var TOKEN='';
try{fetch('api/ping').then(function(r){return r.ok?r.json():null;})
  .then(function(d){if(d&&d.ok){LIVE=true;TOKEN=d.token||'';
    if(fp)fp.hidden=false;
    if(d.chat)askEnable(d);
    document.querySelectorAll('tr.det').forEach(function(tr){
      var f=view[+tr.previousElementSibling.dataset.i];
      if(f)tr.firstChild.innerHTML=details(f);});}})
  .catch(function(){});}catch(e){}

/* The keys a lookup owns. Assigning over them leaves whatever the previous
   answer held -- a baked `issues` list outliving a lookup that no longer
   fetches one -- so they are cleared first. The list is the renderer's own,
   embedded rather than restated here. */
function applyProv(f,d){
  (window.__PROVKEYS__||[]).forEach(function(k){delete f[k];});
  Object.assign(f,d);
}
/* What a row's answer amounts to, cheaply. Used to decide whether a verified
   answer differs from the one already on screen, so a row that was already
   right does not repaint under the reader. */
function provSig(f){
  /* The group is in here because a row can gain one without its own CLs
     changing at all: looking up a *different* row is what joins them, and the
     row that gains a group that way is not the row being looked at. Left out,
     the verified answer was assigned and the repaint skipped, so the panel
     went on saying nothing until the next full page load. */
  return (f.cls||[]).map(function(c){return c.n+':'+c.m;}).join(',')
    +'|'+(f.cl_pool||0)+'|'+(f.no_diffs?1:0)
    +'|'+(f.grp?f.grp.n+':'+f.grp.c+':'+f.grp.t:'');
}
/* A lookup joins two rows and only one of them is the row that was asked
   about. The other gains a group without anything happening to it on screen,
   and a panel already open on it goes on saying nothing -- 23 rows open, one
   button pressed, one panel updated and the rest stale. The answer names the
   group's members, so they are given it here, and any of them the reader
   currently has open is redrawn. */
function spreadGroup(f){
  if(!f.grp||!f.grp.m||!f.grp.m.length)return;
  const mine=new Set(f.grp.m);
  DATA.forEach(function(o){
    if(o===f||!mine.has(o.id))return;
    o.grp={n:f.grp.n,c:f.grp.c,t:f.grp.t,m:f.grp.m};
  });
  document.querySelectorAll('tr.det').forEach(function(tr){
    const head=tr.previousElementSibling;
    if(!head)return;
    const o=view[+head.dataset.i];
    if(o&&o!==f&&mine.has(o.id))
      tr.innerHTML='<td colspan="6">'+details(o)+'</td>';
  });
}
function lookupBtn(f){
  return '<button class="lookup" data-uid="'+esc(f.id)+'">Look up the CL '+
    'for this row</button>';
}
/* What would make this row's answer less than sure, printed above the answer
   instead of inside one branch of it.
   A lookup that lost requests ends in whichever shape the surviving evidence
   produces -- an empty panel, a list of leads, or a citation -- and the
   warning had been written into the innermost branch of the first of those,
   which is the one shape that cannot happen after a partial failure: the
   floor hands any row with a candidate a lead. So the three shapes a
   half-failed lookup actually produces were the three that said nothing.
   A qualifier is a property of the lookup, not of how the lookup ended. */
function qualifier(f){
  var w=[];
  if(f.cl_failed)
    w.push(f.cl_failed+' request'+(f.cl_failed===1?'':'s')+' to Gerrit failed '+
      'during this lookup, so what follows is not a finished search \u2014 '+
      'open the row again to retry.');
  if(f.cl_partial)
    w.push('Gerrit returned this file\u2019s candidate list at its page limit, '+
      'so the window may hold CLs the list below does not.');
  return w.length?'<p class="warn">'+w.join(' ')+'</p>':'';
}
function provenance(f){
  var out=qualifier(f);
  if(!f.cls||!f.cls.length){
    /* Asked and unanswered is a result, and a different one depending on
       whether the diffs were read. Silence would read as "not asked". */
    if(f.cl_pool===undefined)
      return LIVE?out+'<div class="prov"><h4>Why it changed</h4><p class="none">'+
        'Not looked up yet.</p>'+lookupBtn(f)+'</div>':'';
    return out+'<div class="prov"><h4>Why it changed</h4><p class="none">'+
      (f.no_diffs
        ? 'Not looked up \u2014 '+f.cl_pool+' CLs touched this file, more than '+
          'the run\u2019s diff budget would read.'+
          (LIVE?'':' Serve the directory and open the row, or raise '+
                   '<code>--click-budget</code>.')
        /* Reached now only when the pool itself is empty, because a pool with
           anything in it falls back to `touched`. Kept for the reports of
           earlier runs, which are on disk and still open in this page. */
        : (f.cl_pool
            ? 'No CL among the '+
              (f.cl_read?f.cl_read+' read of the '+f.cl_pool:f.cl_pool)+
              ' that touched '+(f.cl_files>1?'either file':'this file')+
              ' can be tied to this identifier.'
            /* Never phrased as an absence. The two trees differ, so
               something landed; what failed is this search. Naming what it
               asked is the only honest form of the answer, and it is also
               the one a reader can act on. */
            : ('This lookup found nothing. Nothing touched '+
              (f.cl_files>1?'either file':'this file')+
              ' on any branch in the window, and no commit message in it '+
              'names this identifier \u2014 so the CL that made this change '+
              'is recorded under something other than the name or the path '+
              'held here.')))+'</p>'+
      (LIVE&&f.no_diffs?lookupBtn(f):'')+'</div>';
  }
  if(f.cls&&f.cls.length){
    /* A crowd of CLs that all edited one declaration is the only list here
       that is not an answer to "why". It is the sequence the declaration
       passed through, so it is headed as one. */
    var hist=allWeak(f)&&f.cls[0].m==='crowded';
    out+='<div class="prov"><h4>'+(hist?'How it got here':'Why it changed')+
      (f.cl_by_message
        ? '<span class="pool">found by commit message \u2014 nothing '+
          'touched '+(f.cl_files>1?'either file':'this file')+' in the '+
          'window</span>'
        /* Three numbers, and they answer three different questions: how
           many CLs touched the file, how many of those a diff tied to this
           fact, and how many of those are printed below. Printing the third
           against the first read as the second -- "8 of 19 merged CLs
           touched this file" on a row where 15 matched and 7 were cut, with
           nothing saying the list had been cut at all. */
        : (f.cl_pool?'<span class="pool">'+(f.cl_match||f.cls.length)+' of '+
        f.cl_pool+
        ' merged CLs touched '+(f.cl_files>1?'these '+f.cl_files+' files':'this file')+
        (f.cl_match?' \u00b7 newest '+f.cls.length+' shown':'')+
        (f.cl_read?' \u00b7 '+f.cl_read+' of them read':'')+
        (f.no_diffs?' \u00b7 diffs not read, descriptions only':'')+
        '</span>':''))+'</h4>'+
      /* A badge saying `touched` is true and easy to skim past. The reader
         who opened this row is owed the disclaimer in words, above the list,
         before they read the first subject line as an explanation. */
      (allWeak(f)?'<p class="lead">'+(hist
        ? 'No one CL singles this out \u2014 these '+f.cls.length+' each edited '+
          'the declaration it belongs to, none the line that names it. '+
          'Read oldest first, they are how it reached the state above.'
        : 'No CL mentions this identifier. These are the newest CLs that '+
          'touched '+(f.cl_files>1?'the declaring files':'the declaring file')+
          '. Leads, not a citation.'+
          /* A row the budget declined is not a row that was searched and came
             back empty -- nothing read its diffs, so the strongest verdicts
             were never even attempted. Filling it with leads made it *look*
             exhausted and, worse, took its way out with it: the remedy and
             the lookup button both live in the branch that runs when there
             are no CLs at all, so the one row that could still be answered
             was the one row that could no longer ask. */
          (f.no_diffs?' Nothing here was read \u2014 '+f.cl_pool+' CLs touched '+
            'this file, more than the run\u2019s diff budget would open.':''))+
        '</p>':'')+
      '<ul class="cls">'+
      f.cls.map(function(c){return clRow(c,true);}).join('')+'</ul>'+
      /* Which is why the button is offered here too, and only here: a row
         holding nothing but leads over unread diffs is exactly the row a
         lookup can still turn into a citation. */
      (LIVE&&f.no_diffs&&allWeak(f)?lookupBtn(f)
        :(!LIVE&&f.no_diffs&&allWeak(f)
          ?'<p class="none">Open this row through '+
           '<code>chromiumdiff serve</code>, or raise '+
           '<code>--click-budget</code>.</p>':''))+
      '</div>';
  }
  /* Every issue the row's CLs cite, busiest first. A flag that launched,
     reverted and relanded often cites two or three, and showing one made the
     answer depend on which CL happened to sort first. */
  /* Only what a run baked in, and only where nothing can be asked. Served, a
     row shows no issue until the reader picks the CL whose issue they want --
     which is the click that says which CL they think is the right one. Doing
     both puts the same issue on the page twice: once before the reader has
     touched it, and again under the CL when they do. */
  (LIVE?[]:(f.issues||[])).forEach(function(i){
    if(!i||!i.cls||!i.cls.length)return;
    out+='<div class="prov iss">'+issueHtml(i)+'</div>';
  });
  if(f.issues_more)
    out+='<p class="none moreiss">'+f.issues_more+' further issue'+
      (f.issues_more===1?'':'s')+' cited by these CLs, in report.json.</p>';
  return out;
}
/* Identifiers and paths carry no spaces, so a cell free to break anywhere
   breaks inside a word: `third_party/blink/public/mojo` + `m/navigation`, and
   `early_hints_preloa` + `ded_resources`. Both were on screen in a real
   report. Offering the separators as break opportunities instead keeps every
   fragment a token the reader recognises. */
function brk(s){
  return esc(s==null?'':s).replace(/([/._,])/g,'$1<wbr>')
                          .replace(/(&lt;)/g,'$1<wbr>');
}
var MARK={added:'+',removed:'\u2212',modified:'~'};
function whatCell(f){
  var c=f.change_type||'';
  var out='<span class="mk mk-'+c+'" title="'+esc(c)+'">'+(MARK[c]||'?')+'</span>'+
    (f.what?brk(f.what):'<code>'+brk(f.name)+'</code>');
  if(f.moved) out+='<div class="moved">'+brk(f.moved)+'</div>';
  return out;
}
function surfaceCell(f){
  var out=esc(kindLabel(f));
  if(f.group) out+='<div class="grp">'+esc(f.group)+'</div>';
  return out;
}
/* Every cell reads the same, whether or not the row above says the same
   thing. Three treatments for a repeat were tried -- leaving it out, merging
   the run into one tall cell, and dimming it -- and each of them encoded a
   fact about the current sort into the appearance of a value. This table
   sorts and filters, so that fact is not about the finding, and a reader
   should not have to work out why two identical values look different. */
function rowHtml(f,i){
  var sb=f.score>=70?' s-hi':(f.score>=45?' s-mid':'');
  return '<tr class="row-t p-'+provState(f)+'" data-i="'+i+'">'+
    '<td class="score'+sb+'">'+f.score+'</td>'+
    '<td><span class="pill b-'+f.bucket+'">'+esc(bucketLabel(f))+'</span></td>'+
    '<td>'+whatCell(f)+'</td>'+
    '<td>'+esc(whyLabel(f))+'</td>'+
    '<td class="where">'+brk(f.where||'')+'</td>'+
    '<td class="muted">'+surfaceCell(f)+'</td></tr>';
}
function paint(){
  const slice=view.slice(0,shown);
  /* The excluded count is said out loud. Without it a reader who typed a term
     an hour ago sees a short list and reads it as a small report. */
  var hidden=EXCL.length?DATA.filter(function(f){
    return EXCL.some(function(term){return hasTerm(f,term);});}).length:0;
  cnt.textContent=(view.length?('showing '+slice.length+' of '+view.length):'0')+
    ' \\u00b7 '+DATA.length+' total'+
    (hidden?' \\u00b7 '+hidden+' excluded':'');
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
  readFilters();
  pickLabels();
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
  /* Each issue opens in its own box appended to that CL's line, so a second
     one lands under the first instead of replacing it -- a reader comparing
     two issues is comparing them, not toggling between them. Clicking the
     same chip again closes only that box. */
  const ib=e.target.closest('button.ibtn');
  if(ib){
    const li=ib.closest('li'), id=ib.dataset.issue;
    const open=li.querySelector('.ihist[data-issue="'+id+'"]');
    if(open){open.remove();ib.classList.remove('on');return;}
    const box=document.createElement('div');
    box.className='ihist';box.dataset.issue=id;
    box.innerHTML='<p class="none">Reading issue '+esc(id)+'\u2026</p>';
    li.appendChild(box);ib.classList.add('on');
    fetch('api/issue?id='+encodeURIComponent(id))
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){
        /* An issue Gerrit indexes no CL for is an answer, not a failure. */
        box.innerHTML=d&&d.id?issueHtml(d)
          :'<p class="none">Issue '+esc(id)+' could not be read.</p>';})
      .catch(function(){
        box.innerHTML='<p class="none">Could not reach the server for issue '+
          esc(id)+'. Is <code>chromiumdiff serve</code> still running?</p>';});
    return;
  }
  const btn=e.target.closest('button.lookup');
  if(btn){
    e.stopPropagation();
    const cell=btn.closest('td'), row=btn.closest('tr.det');
    const f=view[+row.previousElementSibling.dataset.i];
    btn.disabled=true; btn.textContent='Looking\u2026';
    fetch('api/why?uid='+encodeURIComponent(btn.dataset.uid))
      .then(r=>r.ok?r.json():Promise.reject(r.status))
      .then(d=>{applyProv(f,d); f._hay=undefined;
        /* Panels above this one are about to grow -- a row joined into the
           same group gains a line it did not have -- and everything below
           them slides down by that much, including the button the reader's
           pointer is still on. Measured: a sibling two rows up gained 38px
           and this row moved 37. So the row is pinned: where it sat before
           the redraw is where it sits after, and the growth is absorbed by
           the scroll instead of by the reader. */
        const anchor=row.previousElementSibling||row;
        const was=anchor.getBoundingClientRect().top;
        cell.innerHTML=details(f);
        if(fp)fp.hidden=false; spreadGroup(f);
        const box=document.querySelector('.tablewrap');
        const drift=anchor.getBoundingClientRect().top-was;
        if(box&&drift)box.scrollTop+=drift;})
      .catch(err=>{btn.disabled=false;
        btn.textContent='Lookup failed ('+err+') \u2014 try again';});
    return;
  }
  const tr=e.target.closest('tr.row-t'); if(!tr)return;
  const next=tr.nextElementSibling;
  if(next&&next.classList.contains('det')){next.remove();return;}
  const f=view[+tr.dataset.i]; if(!f)return;
  const det=document.createElement('tr');
  det.className='det';
  det.innerHTML='<td colspan="6">'+details(f)+'</td>';
  tr.after(det);
  /* A row that already carries CLs shows no lookup button, so nothing on the
     page could ever ask the server about it again -- and a stored answer
     written by a lookup that has since been corrected would be served for as
     long as the report exists. Opening the row asks. The server hands back
     what it holds unless it judges the answer stale, so this costs one
     localhost round trip and no Gerrit request on a row that is already
     right; when it is not, the panel is replaced with the answer that is.
     An unresolved row is not asked -- resolving one costs real requests, and
     that is what the button is for. */
  if(LIVE&&f.cls&&f.cls.length){
    const before=provSig(f), drawn=det.innerHTML;
    fetch('api/why?uid='+encodeURIComponent(f.id))
      .then(r=>r.ok?r.json():null)
      .then(d=>{
        if(!d)return;
        applyProv(f,d);
        if(provSig(f)===before)return;
        /* Only if nothing has happened to the panel since it was drawn. The
           reader may have closed the row or opened an issue inside it while
           this was in flight, and replacing it under them would take the
           thing they just asked for. */
        if(det.innerHTML!==drawn)return;
        det.innerHTML='<td colspan="6">'+details(f)+'</td>';
      })
      .catch(()=>{});
  }
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
    /* A card is one bucket, so it replaces the filters rather than adding to
       them: it is a way to see what that count counted, and leaving another
       filter on would show fewer rows than the number that was clicked. */
    [fb,fk,fg,fo,fp].forEach(clearPick);
    setPick(sel,p.slice(1).join(':'));
    apply();});});
/* Debounced: typing "network" used to run the whole pipeline seven times. */
let timer=null;
q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,140);});
/* The same debounce, for the same reason: `ai, glic, webgpu` is eighteen
   keystrokes and each one would otherwise re-filter three thousand rows. */
if(x)x.addEventListener('input',()=>{clearTimeout(timer);
  timer=setTimeout(apply,140);});
[fb,fk,fg,fo,fp].forEach(function(el){
  if(!el)return;
  el.addEventListener('change',apply);
  var clear=el.querySelector('.clear');
  if(clear)clear.addEventListener('click',function(){clearPick(el);apply();});});
/* Clicking away closes whichever picker is open, which is what the control it
   replaces did and what anyone expects of something shaped like a dropdown. */
document.addEventListener('click',function(e){
  [fb,fk,fg,fo,fp].forEach(function(el){
    if(el&&el.open&&!el.contains(e.target))el.open=false;});});
apply();

/* -- asking about the report --------------------------------------------- */
/* Built only when `/api/ping` says a chat is on the other end. Nothing below
   runs otherwise, and the markup is created here rather than rendered into the
   file so that a saved copy has no dead panel in it.

   A turn is started with a POST and then followed by polling. Holding the
   response open would be fewer requests and one more way to hang: the work
   happens in another thread and sometimes another process, and a connection
   nobody closes is a page that never finishes loading. */
var askSession=null,askTurn=null,askPoll=null;

function askEl(tag,attrs,parent){
  var el=document.createElement(tag);
  Object.keys(attrs||{}).forEach(function(k){el[k]=attrs[k];});
  if(parent)parent.appendChild(el);
  return el;
}

function askEnable(ping){
  var btn=askEl('button',{id:'askbtn',className:'on',type:'button',
    textContent:'Ask about this report'},document.body);
  var panel=askEl('div',{id:'ask'},document.body);
  var head=askEl('header',{},panel);
  askEl('b',{textContent:'Ask about this report'},head);
  askEl('span',{textContent:(ping.from||'')+' \\u2192 '+(ping.to||'')},head);
  askEl('button',{type:'button',textContent:'close'},head)
    .addEventListener('click',function(){panel.classList.remove('on');});
  var log=askEl('div',{id:'asklog'},panel);
  askEl('p',{className:'asking',textContent:
    'Answers are worked out by running queries over report.json in this '+
    'directory. The queries are shown with each answer.'},log);
  var form=askEl('form',{id:'askform'},panel);
  var input=askEl('textarea',{id:'askin',rows:2,
    placeholder:'What changed in settings?'},form);
  var send=askEl('button',{type:'submit',textContent:'Ask'},form);

  btn.addEventListener('click',function(){
    panel.classList.add('on');input.focus();});
  form.addEventListener('submit',function(e){
    e.preventDefault();askSend(input,send,log);});
  /* Enter asks, shift-enter breaks a line. A question is one line far more
     often than it is several, and a textarea that swallows Enter makes the
     common case take a mouse. */
  input.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();
      askSend(input,send,log);}});
}

function askSay(log,cls,text){
  var el=askEl('div',{className:'qa '+cls},log);
  if(cls==='them')el.innerHTML=askProse(text);
  else el.textContent=text;
  log.scrollTop=log.scrollHeight;
  return el;
}

/* Enough of a renderer for what an answer actually contains: paragraphs,
   bullets, fenced code, inline code and bold. Everything goes through `esc`
   first, so what arrives is text however it was written.

   Bullets and bold are here because leaving them out did not leave them out
   -- it printed `**120**` and a column of hyphens at a reader, which is worse
   than either rendering them or refusing to. A list is the shape most answers
   about a report take. */
function askInline(s){
  return esc(s)
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>');
}

function askProse(text){
  var parts=String(text).split(/```/),out='';
  parts.forEach(function(part,i){
    if(i%2){out+='<pre>'+esc(part.replace(/^\\w*\\n/,''))+'</pre>';return;}
    part.split(/\\n{2,}/).forEach(function(block){
      if(!block.trim())return;
      var lines=block.split('\\n');
      if(lines.every(function(l){return /^\\s*[-*]\\s+/.test(l)||!l.trim();})){
        out+='<ul>'+lines.filter(function(l){return l.trim();})
              .map(function(l){
                return '<li>'+askInline(l.replace(/^\\s*[-*]\\s+/,''))+'</li>';})
              .join('')+'</ul>';
        return;}
      out+='<p>'+askInline(block).replace(/\\n/g,'<br>')+'</p>';});});
  return out||'<p></p>';
}

function askSend(input,send,log){
  var question=input.value.trim();
  if(!question||send.disabled)return;
  input.value='';
  send.disabled=true;
  askSay(log,'you',question);
  var waiting=askSay(log,'asking','working\\u2026');
  fetch('api/chat',{method:'POST',
    headers:{'Content-Type':'application/json',
             'X-Chromiumdiff-Token':TOKEN},
    body:JSON.stringify({session:askSession,message:question})})
   .then(function(r){return r.json();})
   .then(function(d){
     if(d.error){waiting.className='qa err';waiting.textContent=d.error;
       send.disabled=false;return;}
     askSession=d.session;askTurn=d.turn;
     waiting.remove();
     askFollow(d.turn,0,log,send);})
   .catch(function(e){
     waiting.className='qa err';
     waiting.textContent='could not reach the server: '+e;
     send.disabled=false;});
}

function askFollow(turn,since,log,send){
  fetch('api/chat/events?turn='+encodeURIComponent(turn)+'&since='+since,
        {headers:{'X-Chromiumdiff-Token':TOKEN}})
   .then(function(r){return r.json();})
   .then(function(d){
     (d.events||[]).forEach(function(ev){askEvent(ev,log);});
     if(d.running){
       askPoll=setTimeout(function(){
         askFollow(turn,d.next,log,send);},700);
     }else{
       send.disabled=false;
     }})
   .catch(function(){
     askSay(log,'err','lost the connection to the server');
     send.disabled=false;});
}

/* One open block per answer, so consecutive prose from one turn reads as one
   answer rather than as several. */
var askBlock=null;

function askEvent(ev,log){
  if(ev.type==='text'){
    if(!askBlock||askBlock.dataset.closed)askBlock=askSay(log,'them','');
    askBlock.innerHTML+=askProse(ev.text);
    log.scrollTop=log.scrollHeight;
    return;}
  if(ev.type==='tool'){
    var d=askEl('details',{},askBlock&&!askBlock.dataset.closed?askBlock:log);
    askEl('summary',{textContent:'ran '+ev.name},d);
    askEl('pre',{textContent:ev.input},d);
    d.dataset.tool=ev.name;
    log.scrollTop=log.scrollHeight;
    return;}
  if(ev.type==='tool_result'){
    var all=log.querySelectorAll('details[data-tool]');
    var last=all[all.length-1];
    if(last){
      var out=askEl('pre',{textContent:ev.output},last);
      out.className='ran';
      last.querySelector('summary').textContent=
        'ran '+ev.name+' \\u00b7 '+(ev.ok?'ok':'failed')+
        ' \\u00b7 '+ev.seconds+'s';}
    log.scrollTop=log.scrollHeight;
    return;}
  if(ev.type==='error'){askSay(log,'err',ev.message);return;}
  if(ev.type==='done'&&askBlock)askBlock.dataset.closed='1';
}
"""


# ---------------------------------------------------------------------------
# The findings payload behind the table
# ---------------------------------------------------------------------------

def _delta_pair(old: str, new: str, limit: int) -> str:
    """Two states of one attribute, clipped around what differs between them.

    Clipping each side from its own start was the obvious thing and it threw
    away the only information the line carries. Every signature that *gained* a
    parameter shares a prefix with the one before it, so 34 characters of each
    are the same 34 characters, and the cell rendered

        pending_remote<AIManagerCreateLan… → pending_remote<AIManagerCreateLan…

    -- a delta showing no delta, on five consecutive rows of a real report.

    The shared head and tail are context; what lies between them is the edit.
    When one side of that is empty the change is an addition or a removal, and
    it is written with the same `+` and `-` the What column already uses,
    rather than as an arrow out of nothing.
    """
    old, new = str(old), str(new)
    # An arrow needs two sides. A response type that was dropped is a removal,
    # and `DeviceAttributeResult result →` trails off into a blank cell.
    if old and not new:
        return f"− {_clip(old, limit * 2)}"
    if new and not old:
        return f"+ {_clip(new, limit * 2)}"
    if len(old) <= limit and len(new) <= limit:
        return f"{old} → {new}"
    shortest = min(len(old), len(new))
    head = 0
    while head < shortest and old[head] == new[head]:
        head += 1
    tail = 0
    while (tail < shortest - head
           and old[len(old) - 1 - tail] == new[len(new) - 1 - tail]):
        tail += 1
    trim = " ,;"
    a = old[head:len(old) - tail].strip(trim)
    b = new[head:len(new) - tail].strip(trim)
    if a and not b:
        return f"− {_clip(a, limit * 2)}"
    if b and not a:
        return f"+ {_clip(b, limit * 2)}"
    if not a and not b:
        return f"{_clip(old, limit)} → {_clip(new, limit)}"
    lead = "…" if head else ""
    trail = "…" if tail else ""
    return f"{lead}{_clip(a, limit)}{trail} → {lead}{_clip(b, limit)}{trail}"


def _moved(finding_dict: dict, limit: int = 34) -> str:
    """"100 -> 109", for the second line of the What cell.

    Short by design. A Mojo signature runs past 400 characters, and pasted into
    a fixed-layout table cell it wraps to six lines and pushes every other row
    off the screen -- for a value the reader can get in full by opening the row.
    """
    for key, old, new in finding_dict.get("deltas", []):
        if key in ("platform_state", "platform_status"):
            continue
        return _delta_pair(old, new, limit)
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
                deltas.append([key, *_trim_pair(delta[0], delta[1])])
        status = (finding.enrichment or {}).get("chromestatus") or {}
        provenance = (finding.enrichment or {}).get("gerrit") or {}
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
            # Six rather than three: an overloaded member is declared several
            # times, and the row is about the set. Three cut off the very
            # declaration an overload had been removed from.
            "paths": (change.locations or change.paths)[:6],
            "deltas": deltas[:6],
            "reasons": finding.reasons,
            "chromestatus": status.get("summary", ""),
            # The review that made the change, and the issue it cites. Carried
            # as a compact list because the page holds one of these per
            # enriched row and the payload is already the largest thing in the
            # file; `number` is enough to rebuild both URLs in the browser.
            "cls": [
                {"n": c.get("number"), "d": c.get("date", ""),
                 "s": c.get("subject", ""), "m": c.get("match", ""),
                 "b": [{"i": b["id"],
                        **({"f": 1} if b.get("closes") else {}),
                        **({"r": 1} if b.get("restricted") else {})}
                       for b in c.get("bugs") or []],
                 **({"rv": c["reverts"]} if c.get("reverts") else {}),
                 **({"cp": c["cherry_pick_of"]} if c.get("cherry_pick_of")
                    else {}),
                 **({"f": c["file"]} if c.get("file") else {})}
                for c in (provenance.get("changes") or [])
            ],
            "issues": [_issue_payload(i)
                       for i in provenance.get("issues") or []][:3],
        }
        # The run already works out which findings are fragments of one
        # change, and `report.md` prints the groups. The table did not, so a
        # row read alone gave no sign that it was a fragment -- a feature's
        # parameter scores 15 in "New surface", whose whole meaning is that
        # nothing switches it on, while the feature it belongs to sits at 55
        # in the same report with the flag already flipped. The reader had to
        # notice the shared prefix and go looking.
        cluster = (finding.enrichment or {}).get("cluster") or {}
        if cluster.get("size", 0) > 1:
            row["grp"] = {"n": cluster.get("label", ""),
                          "c": cluster["size"],
                          "t": cluster.get("top_score", 0),
                          # Who else is in it. A lookup joins two rows and only
                          # one of them is the row being asked about, so the
                          # answer has to be able to say which others it just
                          # changed -- otherwise a panel already open on one of
                          # them keeps showing an answer that is no longer true.
                          "m": cluster.get("members") or []}
        # Only alongside the CLs it is the denominator for. `_is_empty` keeps a
        # zero on purpose -- a score of 0 is a real rank -- so an unconditional
        # `cl_pool` would ride on all 3,022 rows to say nothing on 2,896 of
        # them.
        if provenance:
            row["cl_pool"] = provenance.get("candidates") or 0
            # Same trap `cl_pool` fell into: `_is_empty` keeps a zero, so an
            # unconditional count rides on every row to say nothing on almost
            # all of them.
            extra = len(provenance.get("issues") or []) - 3
            if extra > 0:
                row["issues_more"] = extra
            row["cl_files"] = len([p for p in (change.paths or [])[:2]])
            # Set by the enricher and never mapped, so the panel's
            # `f.cl_read` was undefined on every row and the denominator it
            # guards printed unqualified, so a file whose newest N were read
            # out of more than N read as though the whole list had been. The
            # number found and the number opened are different claims and the
            # row has room for both.
            if provenance.get("candidates_read"):
                row["cl_read"] = provenance["candidates_read"]
            # How many were tied to this fact, when the list below was cut.
            if provenance.get("matched"):
                row["cl_match"] = provenance["matched"]
            # What would make this row's answer less than sure. A lookup that
            # lost a fetch and one that read every diff and matched nothing
            # produce the same empty panel, and only the run knows which.
            if provenance.get("failed_fetches"):
                row["cl_failed"] = provenance["failed_fetches"]
            # Written by the lookup and read by nobody: it appeared once in
            # the whole repository, at the line that set it. The same shape as
            # `candidates_read`, in the commit that fixed `candidates_read`.
            # `PROVENANCE_KEYS` is the thread meant to stop that, and it only
            # works if a new key is put on it.
            if provenance.get("search_incomplete"):
                row["cl_partial"] = True
            # "no CL edits this line" and "nobody looked" are different
            # answers, and only the run knows which one this is. A row that
            # was never asked about carries neither, and says nothing.
            if provenance.get("diffs_read") is False:
                row["no_diffs"] = True
            # These CLs were not found by asking who touched the file, so the
            # file's denominator does not count them and the panel must not
            # print it as though it did.
            if provenance.get("found_by") == "message":
                row["cl_by_message"] = True
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


# Every key `_to_rows` adds for provenance, named once. `serve` returns this
# subset to the page after a lookup, and when it kept its own copy of the list
# the two drifted the first time a key was renamed: `issue` became `issues` in
# the renderer and the server went on filtering for `issue`, so every lookup
# answered with the CLs and silently dropped the issue history.
# What a lookup owns, and therefore what it must hand back. `grp` is on the
# list because a lookup is what produces it: the CLs it brings in are what the
# grouping joins on, so the row that was just asked about can gain a group it
# did not have a moment ago. Without it here the note appeared only on the
# next page load, which is the one moment the reader is not looking.
PROVENANCE_KEYS = ("cls", "cl_pool", "cl_files", "cl_read", "cl_match",
                   "cl_failed", "cl_partial", "issues", "issues_more",
                   "no_diffs", "cl_by_message", "grp")


def _issue_payload(issue) -> dict:
    if not isinstance(issue, dict) or not issue.get("changes"):
        return {}
    return {
        "id": issue.get("id"),
        "restricted": bool(issue.get("restricted")),
        "t": issue.get("title") or "",
        "total": issue.get("total") or len(issue["changes"]),
        "cls": [{"n": c.get("number"), "d": c.get("date", ""),
                 "s": c.get("subject", "")} for c in issue["changes"][:8]],
    }


# Fields whose values repeat across thousands of rows. Measured on a real
# 3,022-finding report: `reasons` is 319 KB of text drawn from 66 distinct
# strings, `signals` 127 KB from 63, and `group` 58 KB from *three*. Stored
# once each and referenced by index they cost 534 KB less -- a quarter of the
# whole payload, which is the file's load time, since parsing 2.2 MB of inline
# JSON is the one thing on this page that is not instant.
#
# `what` and `paths` are deliberately absent: they are near-unique per row, so
# a table of them is the same bytes plus an index.
_POOLED = ("reasons", "signals", "where", "group", "owner")


_PAYLOAD_RE = None  # compiled on first use by `payload_of`


def payload_of(page: str) -> List[dict]:
    """The rows a rendered page carries, with pooled values put back.

    The page interns five repeated fields to cut a quarter off its own size,
    and rehydrates them on load. Anything else reading the payload -- a test,
    a script -- has to do the same, so it is done here once rather than
    reimplemented at each reader, which is how the two would come to disagree.
    """
    global _PAYLOAD_RE
    if _PAYLOAD_RE is None:
        # The last embedded line ends `;</script>` rather than `;\n`, and a pattern
        # that only knows the second one runs past it into the script below.
        _PAYLOAD_RE = re.compile(
            r"window\.__(FINDINGS|POOL)__=(.*?);(?=\n|</script>)", re.S)
    found = {name: json.loads(body)
             for name, body in _PAYLOAD_RE.findall(page)}
    rows = found.get("FINDINGS") or []
    for field, table in (found.get("POOL") or {}).items():
        for row in rows:
            if isinstance(row.get(field), int):
                row[field] = table[row[field]]
    return rows


def _intern(rows: List[dict]) -> dict:
    """Replace repeated values with indices into a table, in place.

    The page rehydrates in one pass on load, so nothing downstream of it knows
    this happened -- which is the point. A payload format that every reader has
    to remember is a payload format somebody forgets.
    """
    pool: dict = {}
    for field in _POOLED:
        seen: dict = {}
        values: list = []
        for row in rows:
            if field not in row:
                continue
            token = json.dumps(row[field], ensure_ascii=False, sort_keys=True)
            index = seen.get(token)
            if index is None:
                index = seen[token] = len(values)
                values.append(row[field])
            row[field] = index
        if values:
            pool[field] = values
    return pool


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
    text = _as_text(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _as_text(value) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) \
        else ("(absent)" if value is None else str(value))


def _trim_pair(old, new, limit: int = 90, context: int = 14):
    """Two states of one attribute, each shortened around where they differ.

    Trimming each side from its own start independently is what produced the
    report's emptiest line. A Mojo method that gains a parameter keeps every
    character of its old signature, so the first 90 of each side are the same
    90 characters, and both the What column and the detail panel printed

        pending_remote<AIManagerCreateLanguageModelClient> client, A…
        -> pending_remote<AIManagerCreateLanguageModelClient> client, A…

    on five consecutive rows: a delta rendered as two copies of one string.
    No amount of care further down can undo that, because by then the two
    sides really are equal -- the difference was cut off upstream.

    So the cut is made where the difference is. A short run of the shared head
    is kept before it so the reader can place the edit, and the shared tail is
    marked rather than repeated.
    """
    old, new = _as_text(old), _as_text(new)
    if len(old) <= limit and len(new) <= limit:
        return old, new
    shortest = min(len(old), len(new))
    head = 0
    while head < shortest and old[head] == new[head]:
        head += 1
    tail = 0
    while (tail < shortest - head
           and old[len(old) - 1 - tail] == new[len(new) - 1 - tail]):
        tail += 1
    start = max(0, head - context)
    lead = "…" if start else ""
    trail = "…" if tail else ""

    def cut(text: str, stop: int) -> str:
        body = text[start:stop]
        return lead + (body if len(body) <= limit else body[:limit] + "…") + trail

    return cut(old, len(old) - tail), cut(new, len(new) - tail)


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
    total = sum(counts.get(b, 0) for b in BUCKET_ORDER)

    def row(bucket: str) -> str:
        count = counts.get(bucket, 0)
        share = f"{count:,} of {total:,} findings" if total else "none"
        return (
            f'<button class="card {bucket}" data-set="fb:{bucket}" '
            f'title="{_esc(share)}">'
            f'<span class="n">{_n(count)}</span>'
            f'<span class="l">{_esc(BUCKET_LABELS[bucket])}</span>'
            f'<span class="m">{_esc(BUCKET_MEANINGS.get(bucket, ""))}</span>'
            f'</button>')

    return "".join(row(b) for b in BUCKET_ORDER)


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
            # Escaping keeps the attribute intact; it does not make the scheme
            # safe. `javascript:alert(1)` survives every entity encoding and
            # runs on click. The value comes from chromestatus over the
            # network, so the scheme is checked rather than trusted, and a URL
            # that is not http(s) is shown as the text it is.
            if _http_url(entry["spec"]):
                body += (f'<div class="fsum"><a href="{spec}" '
                         f'rel="noreferrer">{spec}</a></div>')
            else:
                body += f'<div class="fsum">{spec}</div>'
        items.append(f'<div class="feat">{head}{body}</div>')

    more = ""
    if len(entries) > limit:
        more = (f'<div class="why">{_n(len(entries) - limit)} more are in '
                f'<code>report.json</code> under '
                f'<code>summary.milestone_brief</code>.</div>')

    # This function built its markup and then fell off the end without
    # returning it, so `{_brief_html(summary)}` interpolated `None` and the
    # page printed the bare word "None" where the section belongs. Invisible
    # to the two tests that cover this feature, because both render the
    # *markdown* report; the HTML one was never asserted.
    return (
        f'<details class="brief"><summary>What Chromium says shipped in this '
        f'window \u2014 {count} feature{"" if len(entries) == 1 else "s"} '
        f'from chromestatus{scope}</summary>'
        f'<div class="body">'
        f'<div class="why">These are Chromium\u2019s own words about the '
        f'window being adopted. They are <em>not</em> matched to the findings '
        f'above \u2014 the names are prose and ours are identifiers \u2014 so '
        f'read them as background, not as a second opinion on any single '
        f'row.</div>'
        + "".join(items) + more +
        '</div></details>')


def _provenance_filter(rows: List[dict]) -> str:
    """Present when there is provenance to filter by, hidden until there is.

    A row that carries a CL and a row that does not look identical in the
    table, and on a report where a fifth of the rows are resolved that is the
    difference between a list you can work through and one you have to open
    row by row to find out.

    A control that filters nothing is worse than no control, so on a report
    nobody has looked anything up in it starts hidden -- and the page unhides
    it the moment either becomes true: a server answered, or a lookup landed.
    Rendering it always, rather than deciding here, is what lets the same file
    be right in both cases.
    """
    hidden = "" if any("cl_pool" in row for row in rows) else " hidden"
    options = [("", "All evidence"),
               ("cl", "Has a CL"),
               # It returns `introduced` as well as `exact`, and both are a
               # changed line tied to the identifier. The label says what the
               # filter asks rather than naming one of the two answers.
               ("exact", "A diff proved it"),
               # Its own option rather than a corner of "Has a CL". A reader
               # filtering for rows that are explained does not want the rows
               # that merely list candidates, and a reader auditing the weak
               # end has no other way to reach them.
               ("weak", "Leads only, nothing names it"),
               ("none", "Scanned, nothing found"),
               ("skipped", "Not looked up")]
    # The first option is the "everything" state and is not a value anything
    # can be, so it is dropped: with checkboxes, "all" is no box ticked.
    return _picker("fp", options[0][1], [(None, options[1:])],
                   hidden=bool(hidden))


def _picker(ident: str, all_label: str, groups, hidden: bool = False) -> str:
    """One filter, chooseable more than one at a time.

    A disclosure rather than a `<select multiple>`, because the native control
    needs a modifier key to pick a second value, cannot express "no filter",
    and is four rows tall in a bar that is one row.

    `groups` is a list of `(heading or None, [(value, label), ...])`. The
    heading is kept because the surfaces list needs it and the `<optgroup>`
    this replaces had it: a flat list of sixteen kinds reads as sixteen kinds
    of feature, and two thirds of them are not features at all.

    The summary carries the label the closed control shows. It is rewritten by
    the page as boxes are ticked, and starts as the "all" wording the single
    select used, so a report nobody touches reads exactly as it did.
    """
    body = []
    for heading, options in groups:
        if heading:
            body.append(f'<b class="head">{_esc(heading)}</b>')
        body.extend(
            f'<label><input type="checkbox" value="{_esc(value)}">'
            f'<span>{_esc(label)}</span></label>'
            for value, label in options)
    return (f'<details class="pick" id="{ident}"'
            f'{" hidden" if hidden else ""} data-all="{_esc(all_label)}">'
            f'<summary>{_esc(all_label)}</summary>'
            f'<div class="opts">{"".join(body)}'
            f'<button type="button" class="clear">Clear</button>'
            f'</div></details>')


    return (f'<details class="brief"><summary>What Chromium says shipped in '
            f'this window — {count} features{scope}</summary>'
            f'<div class="body">'
            f'<p class="why">Chromium\'s own words about the milestones being '
            f'adopted, newest first. These are <b>not</b> matched to the rows '
            f'above — the names are prose and the findings are identifiers — '
            f'so read them as background, not as a second opinion on any '
            f'single row.</p>{"".join(items)}{more}</div></details>')


def _http_url(value: object) -> bool:
    """Only `http:` and `https:` become a clickable link."""
    return isinstance(value, str) and value.strip().lower().startswith(
        ("http://", "https://"))


def _embed(value) -> str:
    """JSON for an inline `<script>`, which is not the same as JSON.

    `json.dumps` escapes nothing that matters to an HTML parser, and the
    parser ends the script at the first `</script>` in the byte stream --
    inside a string literal or not. A fact name carrying one would run
    whatever followed it, in a file people open in a browser and forward to
    each other, and escaping at render time cannot help because the break
    happened when the document was parsed.

    Chromium's own source is not the threat; `--local-src` and a hand-edited
    `report.json` are, and neither is worth trusting for this. U+2028 and
    U+2029 go too: they are valid JSON and illegal in a JavaScript string
    literal, so a page carrying one fails to parse at all.
    """
    return (json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def render(report: Report, platform: str = "windows") -> str:
    rows = _to_rows(report, platform)
    provenance_filter = _provenance_filter(rows)
    # After the filter is built, because that reads `cl_pool`, and before the
    # payload is embedded, because that is what shrinks.
    pool = _intern(rows)
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
    surface_groups = []
    for group_name, group_kinds in KIND_GROUPS:
        present = [k for k in group_kinds if k in kinds]
        if present:
            surface_groups.append(
                (group_name, [(k, KIND_LABELS.get(k, k)) for k in present]))

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
<input type="search" id="x" placeholder="Exclude: ai, glic\u2026">
{_picker("fb", "All buckets", [(None, [(b, BUCKET_LABELS[b]) for b in BUCKET_ORDER])])}
{_picker("fk", "All surfaces", surface_groups)}
{_picker("fg", "All consequences", [(None, [(g, g) for g in groups])])}
{_picker("fo", "All owners", [(None, [(o, OWNER_LABELS[o]) for o in OWNER_ORDER])])}
{provenance_filter}
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
<p class="more-note">Rows render a page at a time &mdash; the JSON below holds
every finding regardless of what is on screen, and the button above says how
many are hidden. Click any row for its evidence, its declaring line, and the
reasoning behind its score.</p>
{_brief_html(summary)}
</div>
<script>window.__FINDINGS__={_embed(rows)};
window.__KINDS__={_embed(KIND_LABELS)};
window.__BUCKETS__={_embed(BUCKET_LABELS)};
window.__STORIES__={_embed(stories)};
window.__PROVKEYS__={_embed(list(PROVENANCE_KEYS))};
window.__EVID__={_embed(VERDICT_MEANINGS)};
window.__POOL__={_embed(pool)};</script>
<script>{_JS}</script>
"""
