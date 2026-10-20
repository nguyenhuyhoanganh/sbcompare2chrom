"""Turn results.json into a folder that becomes one Confluence page per run.

    <run_dir>/confluence/
        manifest.json        {"title", "body_storage", "body_markdown", "attachments": [...]}
        page.storage.html    Confluence storage format (status lozenges, tables, inline images)
        page.md              same content in Markdown (for tools that take Markdown)
        attachments/         failure screenshots, named <case>_<test>_<page|screen>.png

The upload itself (create the page, attach the files) is done with the Confluence skill;
nothing here talks to Confluence.
"""
from __future__ import annotations

import html
import json
import shutil
from collections import defaultdict
from pathlib import Path

from sbtest.utils import slug

COLORS = {"passed": "Green", "failed": "Red", "error": "Red", "skipped": "Grey"}
SHOTS = ("page.png", "screen.png")
ORDER = ("passed", "failed", "error", "skipped")


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _status(outcome: str) -> str:
    return (f'<ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">{COLORS.get(outcome, "Grey")}'
            f'</ac:parameter><ac:parameter ac:name="title">{esc(outcome.upper())}</ac:parameter></ac:structured-macro>')


def attachment_name(test: dict, shot: str) -> str:
    key = "_".join(test.get("cases") or []) or "nocase"
    return f"{slug(key, 60)}_{slug(test['name'], 60)}_{shot}"


def _md_cell(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def build(results: dict) -> dict:
    """-> {"title", "storage", "markdown", "files": [(source path, attachment name)]}"""
    meta, tests = results["meta"], results["tests"]
    counts = defaultdict(int)
    for t in tests:
        counts[t["outcome"]] += 1
    version = meta.get("browser_version") or "?"
    title = (f"Sanity {meta.get('target', '')} {meta.get('started', '')[:16].replace('T', ' ')}"
             f" - Chromium {version}").replace("  ", " ")
    info = [("Target", meta.get("target")), ("Started", meta.get("started")), ("Finished", meta.get("finished")),
            ("Executable", meta.get("exe")), ("Browser version", version), ("User agent", meta.get("user_agent")),
            ("chromedriver", meta.get("chromedriver")), ("Machine", f"{meta.get('machine', '')} ({meta.get('os', '')})"),
            ("Artifacts", meta.get("run_dir"))]

    st = ["<h2>Summary</h2><p>" + " ".join(f"{_status(k)} {counts.get(k, 0)}" for k in ORDER)
          + f" &#160; total {len(tests)}</p>",
          "<table><tbody>" + "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in info) + "</tbody></table>"]
    md = [f"# {title}", "", "## Summary", "",
          " ".join(f"**{k.upper()}** {counts.get(k, 0)}" for k in ORDER) + f" - total {len(tests)}", "",
          "| | |", "|---|---|"] + [f"| {k} | {_md_cell(v)} |" for k, v in info]

    by_feature: dict[str, list] = defaultdict(list)
    for t in tests:
        by_feature[t.get("feature") or "other"].append(t)
    files: list[tuple[Path, str]] = []
    failures = []
    for feature in sorted(by_feature):
        group = sorted(by_feature[feature], key=lambda x: (x.get("cases") or ["~"])[0])
        ok = sum(1 for t in group if t["outcome"] == "passed")
        st.append(f"<h2>{esc(feature)} ({ok}/{len(group)} passed)</h2><table><tbody><tr><th>Case</th><th>Test</th>"
                  "<th>Result</th><th>Failed step</th><th>Error</th><th>Time</th></tr>")
        md += ["", f"## {feature} ({ok}/{len(group)} passed)", "",
               "| Case | Test | Result | Failed step | Error | Time |", "|---|---|---|---|---|---|"]
        for t in group:
            cases = ", ".join(t.get("cases") or []) or "-"
            st.append(f"<tr><td>{esc(cases)}</td><td>{esc(t['name'])}</td><td>{_status(t['outcome'])}</td>"
                      f"<td>{esc(t.get('failed_step'))}</td><td>{esc((t.get('message') or '')[:300])}</td>"
                      f"<td>{esc(t.get('duration'))}s</td></tr>")
            md.append(f"| {_md_cell(cases)} | {_md_cell(t['name'])} | {t['outcome'].upper()} | "
                      f"{_md_cell(t.get('failed_step'))} | {_md_cell((t.get('message') or '')[:300])} | {t.get('duration')}s |")
            if t["outcome"] in ("failed", "error"):
                failures.append(t)
        st.append("</tbody></table>")

    if failures:
        st.append("<h2>Failures</h2>")
        md += ["", "## Failures"]
    for t in failures:
        head = f"{', '.join(t.get('cases') or []) or '-'} - {t['name']}"
        st.append(f"<h3>{esc(head)}</h3><p><strong>Failed step:</strong> {esc(t.get('failed_step') or '-')}<br/>"
                  f"<strong>Expected:</strong> {esc(t.get('expected') or '-')}<br/>"
                  f"<strong>Error:</strong> {esc(t.get('message') or '-')}</p>")
        md += ["", f"### {head}", "", f"- Failed step: {t.get('failed_step') or '-'}",
               f"- Expected: {t.get('expected') or '-'}", f"- Error: {t.get('message') or '-'}", ""]
        ev = Path(t.get("evidence_dir") or "")
        for shot in SHOTS:
            if t.get("evidence_dir") and (ev / shot).exists():
                name = attachment_name(t, shot)
                files.append((ev / shot, name))
                st.append(f'<p><ac:image ac:width="900"><ri:attachment ri:filename="{esc(name)}"/></ac:image></p>')
                md.append(f"![{name}](attachments/{name})")
        if t.get("steps"):
            st.append("<ol>" + "".join(f"<li>[{esc(s['status'])}] {esc(s['title'])}</li>" for s in t["steps"]) + "</ol>")
            md += [""] + [f"{i}. [{s['status']}] {s['title']}" for i, s in enumerate(t["steps"], 1)]
    return {"title": title, "storage": "".join(st), "markdown": "\n".join(md) + "\n", "files": files}


def export(run_dir: Path) -> Path:
    """Write <run_dir>/confluence/ and return its path."""
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    page = build(results)
    out = run_dir / "confluence"
    if out.exists():
        shutil.rmtree(out)
    (out / "attachments").mkdir(parents=True)
    (out / "page.storage.html").write_text(page["storage"], encoding="utf-8")
    (out / "page.md").write_text(page["markdown"], encoding="utf-8")
    for src, name in page["files"]:
        shutil.copyfile(src, out / "attachments" / name)
    manifest = {"title": page["title"], "body_storage": "page.storage.html", "body_markdown": "page.md",
                "attachments": [f"attachments/{name}" for _, name in page["files"]]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out
