"""Per-build sanity report: one row per test case with its description, steps, expected
result, actual result and a screenshot of how it ended.

    <run_dir>/report/index.html     open in a browser; the folder can be zipped and shared
    <run_dir>/report/report.md      same content in Markdown
    <run_dir>/report/img/           result screenshots (JPEG, one per test)

Built from <run_dir>/results.json (written by the pytest plugin) + testcases/**/*.md.
Regenerate any time:  python -m sbtest.tools.report artifacts/runs/<ts>
"""
from __future__ import annotations

import html
import json
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sbtest.reporting.cases import Case, load_cases
from sbtest.utils import slug

RESULT_LABEL = {"passed": "PASS", "failed": "FAIL", "error": "ERROR", "skipped": "SKIP", "na": "N/A"}
FEATURE_ORDER = ("addons", "bookmarks", "downloads", "history", "settings", "general", "reference", "other")


@dataclass
class Row:
    case_id: str
    title: str
    feature: str
    description: str
    steps: list[str]
    expected: list[str]
    result: str                     # passed | failed | error | skipped | na
    test: str
    duration: float
    failed_step: str = ""
    error: str = ""
    executed: list[dict] = field(default_factory=list)
    screenshot: str = ""            # absolute path of the source picture
    image: str = ""                 # path inside report/ (img/x.jpg)
    priority: str = ""
    type: str = ""


def _result(test: dict) -> str:
    if test["outcome"] == "skipped" and "not applicable to target" in (test.get("message") or ""):
        return "na"
    return test["outcome"]


def build_rows(results: dict, cases: dict[str, Case]) -> list[Row]:
    rows: list[Row] = []
    for t in results["tests"]:
        ids = t.get("cases") or [""]
        for cid in ids:
            c = cases.get(cid)
            rows.append(Row(
                case_id=cid or "-", title=c.title if c else t["name"], feature=(c.feature if c else t.get("feature")) or "other",
                description=c.precondition if c else "", steps=list(c.steps) if c else [],
                expected=list(c.expected) if c else [], result=_result(t), test=t["nodeid"],
                duration=t.get("duration", 0.0), failed_step=t.get("failed_step", ""), error=t.get("message", ""),
                executed=t.get("steps") or [], screenshot=t.get("screenshot") or "",
                priority=c.priority if c else "", type=c.type if c else ""))
    rank = {f: i for i, f in enumerate(FEATURE_ORDER)}
    rows.sort(key=lambda r: (rank.get(r.feature, 99), r.feature, r.case_id))
    return rows


def summary(rows: list[Row], meta: dict) -> dict:
    counts = Counter(r.result for r in rows)
    failed = counts["failed"] + counts["error"]
    product = meta.get("product_version") or ""
    name = "Samsung Browser" if meta.get("target") == "samsung" else "Chrome"
    return {
        "counts": counts, "total": len(rows), "failed": failed,
        "verdict": "PASSED" if failed == 0 and counts["passed"] else ("FAILED" if failed else "NO RESULT"),
        "build": f"{name} {product}".strip() + (f" (Chromium {meta.get('browser_version')})" if meta.get("browser_version") else ""),
    }


def build_info(meta: dict) -> list[tuple[str, str]]:
    return [
        ("Build", f"{meta.get('product_version') or '?'}"), ("Chromium", meta.get("browser_version") or "?"),
        ("Target", meta.get("target") or ""), ("Executable", meta.get("exe") or ""),
        ("chromedriver", meta.get("chromedriver") or ""), ("Machine", f"{meta.get('machine', '')} - {meta.get('os', '')}"),
        ("Started", (meta.get("started") or "").replace("T", " ")), ("Finished", (meta.get("finished") or "").replace("T", " ")),
        ("Selection", meta.get("selection") or "all"),
    ]


def _copy_images(rows: list[Row], out: Path, max_width: int = 1600) -> None:
    """Result screenshots -> report/img/*.jpg (smaller, so the folder stays easy to share)."""
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    done: dict[str, str] = {}
    for r in rows:
        src = Path(r.screenshot) if r.screenshot else None
        if not src or not src.exists():
            continue
        if str(src) in done:
            r.image = done[str(src)]
            continue
        name = f"{slug(r.case_id, 30)}_{slug(Path(r.test.split('::')[-1]).name, 60)}.jpg"
        try:
            from PIL import Image

            with Image.open(src) as im:
                im = im.convert("RGB")
                if im.width > max_width:
                    im = im.resize((max_width, int(im.height * max_width / im.width)))
                im.save(img_dir / name, "JPEG", quality=80)
        except Exception:  # noqa: BLE001 - no PIL / unreadable: copy as is
            name = name[:-4] + src.suffix
            shutil.copyfile(src, img_dir / name)
        r.image = done[str(src)] = f"img/{name}"


# ---------------------------------------------------------------------------------- HTML
def _e(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--muted:#5b6475;--line:#e3e6eb;--pass:#1a7f37;--fail:#cf222e;--skip:#6e7781;--na:#8c959f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 "Segoe UI",system-ui,sans-serif}
main{max-width:1500px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 10px}
.sub{color:var(--muted);margin-bottom:16px}.verdict{display:inline-block;padding:6px 14px;border-radius:6px;color:#fff;font-weight:700;font-size:16px}
.v-PASSED{background:var(--pass)}.v-FAILED{background:var(--fail)}.v-NO{background:var(--skip)}
.cards{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 16px;min-width:110px}
.card b{display:block;font-size:22px}.info{border-collapse:collapse;background:var(--card);border:1px solid var(--line)}
.info th,.info td{padding:5px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.info th{color:var(--muted);font-weight:600;white-space:nowrap}
table.cases{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line)}
table.cases th{background:#eef0f3;text-align:left;padding:8px;font-weight:600;position:sticky;top:0}
table.cases td{padding:8px;border-top:1px solid var(--line);vertical-align:top}
td ol,td ul{margin:0;padding-left:18px}.id{font-weight:700;white-space:nowrap}.muted{color:var(--muted);font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;color:#fff;font-weight:700;font-size:12px}
.r-passed{background:var(--pass)}.r-failed,.r-error{background:var(--fail)}.r-skipped{background:var(--skip)}.r-na{background:var(--na)}
.err{color:var(--fail);margin-top:6px;white-space:pre-wrap;word-break:break-word}.shot img{width:220px;border:1px solid var(--line);border-radius:4px}
.feat{color:var(--muted);font-weight:400;font-size:14px}tr.fail-row td{background:#fff5f5}
"""


def write_html(rows: list[Row], meta: dict, out: Path) -> Path:
    s = summary(rows, meta)
    c = s["counts"]
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Sanity report - {_e(s['build'])}</title>",
             f"<meta name='viewport' content='width=device-width,initial-scale=1'><style>{CSS}</style></head><body><main>",
             f"<h1>Sanity report - {_e(s['build'])}</h1>",
             f"<div class='sub'>{_e((meta.get('started') or '').replace('T', ' '))} on {_e(meta.get('machine'))}</div>",
             f"<span class='verdict v-{s['verdict'].split()[0]}'>BUILD {_e(s['verdict'])}</span>",
             "<div class='cards'>"]
    for key, label in (("passed", "Passed"), ("failed", "Failed"), ("error", "Error"), ("skipped", "Skipped"), ("na", "N/A")):
        parts.append(f"<div class='card'><b>{c.get(key, 0)}</b>{label}</div>")
    parts.append(f"<div class='card'><b>{s['total']}</b>Cases</div></div>")
    parts.append("<table class='info'>" + "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in build_info(meta))
                 + "</table>")
    by_feature: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_feature[r.feature].append(r)
    for feature, group in by_feature.items():
        ok = sum(r.result == "passed" for r in group)
        run = sum(r.result in ("passed", "failed", "error") for r in group)
        parts.append(f"<h2>{_e(feature.capitalize())} <span class='feat'>{ok}/{run} passed</span></h2>")
        parts.append("<table class='cases'><tr><th>ID</th><th>Name / description</th><th>Steps</th><th>Expected</th>"
                     "<th>Result</th><th>Screenshot</th></tr>")
        for r in group:
            steps = "<ol>" + "".join(f"<li>{_e(x)}</li>" for x in r.steps) + "</ol>" if r.steps else ""
            exp = "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in r.expected) + "</ul>" if r.expected else ""
            res = f"<span class='badge r-{r.result}'>{RESULT_LABEL.get(r.result, r.result.upper())}</span>" \
                  f" <span class='muted'>{r.duration:.1f}s</span>"
            if r.result in ("failed", "error"):
                if r.failed_step:
                    res += f"<div class='err'><b>Failed at:</b> {_e(r.failed_step)}</div>"
                res += f"<div class='err'>{_e(r.error)}</div>"
                if r.executed:
                    res += "<ol class='muted'>" + "".join(f"<li>[{_e(x['status'])}] {_e(x['title'])}</li>" for x in r.executed) + "</ol>"
            elif r.result in ("skipped", "na"):
                res += f"<div class='muted'>{_e(r.error)}</div>"
            shot = f"<a href='{_e(r.image)}' target='_blank'><img src='{_e(r.image)}' loading='lazy' alt='result'></a>" if r.image else ""
            desc = f"<div>{_e(r.title)}</div>" + (f"<div class='muted'>{_e(r.description)}</div>" if r.description else "") \
                   + f"<div class='muted'>{_e(r.priority)} {_e(r.type)}</div>"
            cls = " class='fail-row'" if r.result in ("failed", "error") else ""
            parts.append(f"<tr{cls}><td class='id'>{_e(r.case_id)}</td><td>{desc}</td><td>{steps}</td><td>{exp}</td>"
                         f"<td>{res}</td><td class='shot'>{shot}</td></tr>")
        parts.append("</table>")
    parts.append("</main></body></html>")
    path = out / "index.html"
    path.write_text("".join(parts), encoding="utf-8")
    return path


# ------------------------------------------------------------------------------ Markdown
def _md(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def write_markdown(rows: list[Row], meta: dict, out: Path) -> Path:
    s = summary(rows, meta)
    c = s["counts"]
    md = [f"# Sanity report - {s['build']}", "", f"**BUILD {s['verdict']}** - "
          + ", ".join(f"{RESULT_LABEL[k]} {c.get(k, 0)}" for k in ("passed", "failed", "error", "skipped", "na"))
          + f" (total {s['total']})", "", "| | |", "|---|---|"]
    md += [f"| {k} | {_md(v)} |" for k, v in build_info(meta)]
    by_feature: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_feature[r.feature].append(r)
    for feature, group in by_feature.items():
        md += ["", f"## {feature.capitalize()}", "", "| ID | Name | Description | Steps | Expected | Result | Screenshot |",
               "|---|---|---|---|---|---|---|"]
        for r in group:
            steps = "<br>".join(f"{i}. {_md(x)}" for i, x in enumerate(r.steps, 1))
            exp = "<br>".join(f"- {_md(x)}" for x in r.expected)
            res = RESULT_LABEL.get(r.result, r.result.upper())
            if r.result in ("failed", "error"):
                res += f"<br>Failed at: {_md(r.failed_step)}<br>{_md(r.error)[:300]}"
            shot = f"[img]({r.image})" if r.image else ""
            md.append(f"| {r.case_id} | {_md(r.title)} | {_md(r.description)} | {steps} | {exp} | {res} | {shot} |")
    path = out / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def generate(run_dir: Path) -> Path:
    """Write <run_dir>/report/ and return index.html."""
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = build_rows(results, load_cases())
    out = run_dir / "report"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    _copy_images(rows, out)
    write_markdown(rows, results["meta"], out)
    (out / "rows.json").write_text(json.dumps([r.__dict__ for r in rows], indent=1, default=str), encoding="utf-8")
    return write_html(rows, results["meta"], out)
