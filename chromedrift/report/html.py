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
from ..model import BUCKET_LABELS, BUCKET_ORDER, KIND_LABELS, Report
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
.headline{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:6px;padding:14px 16px;margin:0 0 24px;font-size:1.02rem}
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
table{border-collapse:collapse;width:100%;font-size:.88rem;min-width:860px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:.78rem;text-transform:uppercase;
letter-spacing:.04em;cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:0;
background:var(--card)}
tbody tr:last-child td{border-bottom:none}
tbody tr.det td{background:color-mix(in srgb,var(--card) 92%,var(--fg));font-size:.85rem}
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
"""

_JS = """
const DATA=window.__FINDINGS__||[];
const q=document.getElementById('q'),fb=document.getElementById('fb'),
fk=document.getElementById('fk'),fa=document.getElementById('fa'),
tb=document.getElementById('tb'),cnt=document.getElementById('cnt');
let sortKey='score',sortDir=-1;
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function match(f){
  const t=q.value.trim().toLowerCase();
  if(fb.value&&f.bucket!==fb.value)return false;
  if(fk.value&&f.kind!==fk.value)return false;
  if(fa.value){
    if(fa.value==='__none__'){ if((f.areas||[]).length) return false; }
    else if(!(f.areas||[]).includes(fa.value)) return false;
  }
  if(!t)return true;
  return (f.name+' '+f.kind+' '+(f.signals||[]).join(' ')+' '+(f.paths||[]).join(' ')
    +' '+(f.verdict||'')+' '+(f.rationale||'')).toLowerCase().includes(t);
}
function details(f){
  const L=[];
  if(f.signals&&f.signals.length)L.push('<li><b>Signals:</b> '+esc(f.signals.join(', '))+'</li>');
  if(f.paths&&f.paths.length)L.push('<li><b>Declared in:</b> <code>'+esc(f.paths.join(', '))+'</code></li>');
  if(f.we_patch&&f.we_patch.length)L.push('<li><b>We patch:</b> <code>'+esc(f.we_patch.join(', '))+'</code></li>');
  if(f.we_ref&&f.we_ref.length)L.push('<li><b>We reference:</b> <code>'+esc(f.we_ref.join(', '))+'</code></li>');
  (f.deltas||[]).forEach(d=>L.push('<li><b>'+esc(d[0])+':</b> <code>'+esc(d[1])+'</code> → <code>'+esc(d[2])+'</code></li>'));
  if(f.chromestatus)L.push('<li><b>Chromestatus:</b> '+esc(f.chromestatus)+'</li>');
  if(f.rationale)L.push('<li><b>AI:</b> '+esc(f.rationale)+'</li>');
  if(f.action)L.push('<li><b>Action:</b> '+esc(f.action)+'</li>');
  if(f.test_hint)L.push('<li><b>Test:</b> '+esc(f.test_hint)+'</li>');
  if(f.reasons&&f.reasons.length)L.push('<li class="muted"><b>Score:</b> '+esc(f.reasons.join(' · '))+'</li>');
  return '<ul class="tight">'+L.join('')+'</ul>';
}
function render(){
  const rows=DATA.filter(match).sort((a,b)=>{
    const x=a[sortKey],y=b[sortKey];
    if(typeof x==='number'&&typeof y==='number')return (x-y)*sortDir;
    return String(x||'').localeCompare(String(y||''))*sortDir;});
  cnt.textContent=rows.length+' of '+DATA.length;
  if(!rows.length){tb.innerHTML='<tr><td colspan="6" class="empty">No findings match.</td></tr>';return;}
  tb.innerHTML=rows.map((f,i)=>
    '<tr class="row" data-i="'+i+'"><td class="score">'+f.score+'</td>'+
    '<td><span class="pill b-'+f.bucket+'">'+esc(f.bucket_label)+'</span></td>'+
    '<td><code>'+esc(f.name)+'</code></td>'+
    '<td class="muted">'+esc(f.kind_label)+'</td>'+
    '<td>'+esc(f.moved||'')+'</td>'+
    '<td>'+esc(f.verdict||'—')+'</td></tr>'+
    '<tr class="det" id="d'+i+'" hidden><td colspan="6">'+details(f)+'</td></tr>').join('');
  tb.querySelectorAll('tr.row').forEach(tr=>tr.addEventListener('click',()=>{
    const d=document.getElementById('d'+tr.dataset.i); if(d)d.hidden=!d.hidden;}));
}
document.querySelectorAll('th[data-k]').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.k; sortDir=(k===sortKey)?-sortDir:(k==='score'?-1:1); sortKey=k; render();}));
[q,fb,fk,fa].forEach(el=>el&&el.addEventListener('input',render));
render();
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
        ai = finding.ai or {}
        row = {
            "id": finding.uid,
            "name": md_report.display_name(change),
            "kind": change.kind,
            "kind_label": KIND_LABELS.get(change.kind, change.kind),
            "change_type": change.change_type,
            "bucket": finding.bucket,
            "bucket_label": BUCKET_LABELS.get(finding.bucket, finding.bucket),
            "score": finding.score,
            "signals": [SIGNAL_LABELS.get(s, s) for s in change.signals],
            "paths": change.paths[:3],
            "we_patch": finding.matched_paths[:5],
            "we_ref": finding.matched_symbols[:8],
            "areas": finding.areas,
            "deltas": deltas[:6],
            "reasons": finding.reasons,
            "chromestatus": status.get("summary", ""),
            "verdict": ai.get("verdict", ""),
            "rationale": ai.get("rationale", ""),
            "action": ai.get("action", ""),
            "test_hint": ai.get("test_hint", ""),
        }
        row["moved"] = _moved(row)
        rows.append(row)
    return rows


def _trim(value, limit: int = 90) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) \
        else ("(absent)" if value is None else str(value))
    return text if len(text) <= limit else text[:limit] + "…"


def render(report: Report, platform: str = "windows") -> str:
    rows = _to_rows(report, platform)
    counts = report.bucket_counts()
    meta = report.meta or {}
    ai_summary = (report.summary or {}).get("ai") or {}

    kinds = sorted({r["kind"] for r in rows})
    areas = sorted({a for r in rows for a in r["areas"]})
    unassigned_count = sum(1 for r in rows if not r["areas"])

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
    status_note = md_report.ai_status_note(report.summary or {})
    if status_note:
        # Markdown emphasis is meaningless here; keep the words, drop the marks.
        notes.append(html.escape(status_note.replace("**", "").replace("`", "")))
    profile = meta.get("profile") or {}
    if profile and not profile.get("paths_total") and not profile.get("symbols_total"):
        notes.append("No downstream evidence was supplied, so nothing can land in "
                     "<b>Must fix</b>. Point the profile at your patch directory or fork.")
    notes_html = "".join(f'<div class="note">{n}</div>' for n in notes)

    headline = ""
    if ai_summary.get("headline"):
        headline = f'<div class="headline">{html.escape(ai_summary["headline"])}</div>'

    option = lambda v, label="": f'<option value="{html.escape(v)}">{html.escape(label or v)}</option>'

    return f"""<title>{html.escape(md_report.MODE_TITLES[mode])}</title>
<style>{_CSS}</style>
<div class="wrap">
<h1>{html.escape(md_report.MODE_TITLES[mode])}</h1>
<div class="sub"><code>{html.escape(report.from_ref)}</code> →
<code>{html.escape(report.to_ref)}</code> ·
{html.escape(str(meta.get('product','downstream browser')))} ·
platform {html.escape(platform)} · {html.escape(str(meta.get('generated','')))}</div>
{headline}
{notes_html}
<div class="cards">{cards}</div>
<h2>Findings</h2>
<div class="controls">
<input type="search" id="q" placeholder="Search name, signal, path, rationale…">
<select id="fb"><option value="">All buckets</option>
{''.join(option(b, BUCKET_LABELS[b]) for b in BUCKET_ORDER)}</select>
<select id="fk"><option value="">All surfaces</option>
{''.join(option(k, KIND_LABELS.get(k,k)) for k in kinds)}</select>
<select id="fa"><option value="">All areas</option>
{''.join(option(a) for a in areas)}
{option("__none__", f"(no area) — {unassigned_count}") if unassigned_count else ""}</select>
<span class="muted" id="cnt"></span>
</div>
<div class="tablewrap"><table>
<thead><tr>
<th data-k="score">Score</th><th data-k="bucket">Bucket</th>
<th data-k="name">Change</th><th data-k="kind_label">Surface</th>
<th data-k="moved">What moved</th><th data-k="verdict">Verdict</th>
</tr></thead><tbody id="tb"></tbody></table></div>
<p class="muted" style="margin-top:10px;font-size:.85rem">Click a row for evidence
and score reasoning.</p>
</div>
<script>window.__FINDINGS__={json.dumps(rows, ensure_ascii=False)};</script>
<script>{_JS}</script>
"""
