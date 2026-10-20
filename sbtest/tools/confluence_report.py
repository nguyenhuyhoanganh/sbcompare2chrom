"""Publish a test run (artifacts/runs/<ts>/results.json) as a new Confluence page.

    python -m sbtest.tools.confluence_report artifacts/runs/20261020_101500
    python -m sbtest.tools.confluence_report <run_dir> --space QA --parent-id 123456 --title "SI 29.1 / Chromium 141"
    python -m sbtest.tools.confluence_report <run_dir> --dry-run      # writes <run_dir>/confluence_page.html only
    python run.py --exe ... --all --publish                           # run, then publish

The page has: build/browser info, totals, one table per feature (case id, test, result,
failed step, error) and the failure screenshots (page.png = tab with the failing element
outlined, screen.png = whole Windows screen) attached and shown inline.
Space / parent come from config ``atlassian.report_space`` / ``report_parent_id``.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from sbtest.atlassian import Atlassian, esc, log_page
from sbtest.config import load_config
from sbtest.utils import slug

COLORS = {"passed": "Green", "failed": "Red", "error": "Red", "skipped": "Grey"}
SHOTS = ("page.png", "screen.png")


def _status(outcome: str) -> str:
    return (f'<ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">{COLORS.get(outcome, "Grey")}'
            f'</ac:parameter><ac:parameter ac:name="title">{esc(outcome.upper())}</ac:parameter></ac:structured-macro>')


def attachment_name(test: dict, shot: str) -> str:
    """Unique attachment file name for a test's screenshot."""
    key = "_".join(test.get("cases") or []) or test["name"]
    return f"{slug(key, 60)}_{slug(test['name'], 60)}_{shot}"


def build_page(results: dict) -> tuple[str, str, list[tuple[Path, str]]]:
    """-> (title, storage xhtml, [(file, attachment name)])."""
    meta, tests = results["meta"], results["tests"]
    counts = defaultdict(int)
    for t in tests:
        counts[t["outcome"]] += 1
    version = meta.get("browser_version") or "?"
    title = f"Sanity run {meta.get('started', '')[:16].replace('T', ' ')} - Chromium {version}"

    info_rows = [("Started", meta.get("started")), ("Finished", meta.get("finished")),
                 ("Executable", meta.get("exe")), ("Browser version", version),
                 ("User agent", meta.get("user_agent")), ("chromedriver", meta.get("chromedriver")),
                 ("Machine", f"{meta.get('machine', '')} ({meta.get('os', '')})"), ("Artifacts", meta.get("run_dir"))]
    parts = ['<h2>Summary</h2><p>'
             + " ".join(f"{_status(k)} {counts.get(k, 0)}" for k in ("passed", "failed", "error", "skipped"))
             + f" &#160; total {len(tests)}</p>",
             "<table><tbody>" + "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in info_rows)
             + "</tbody></table>"]

    by_feature: dict[str, list] = defaultdict(list)
    for t in tests:
        by_feature[t.get("feature") or "other"].append(t)
    files: list[tuple[Path, str]] = []
    failures = []
    for feature in sorted(by_feature):
        rows = []
        for t in sorted(by_feature[feature], key=lambda x: (x.get("cases") or ["~"])[0]):
            rows.append(
                f"<tr><td>{esc(', '.join(t.get('cases') or []) or '-')}</td><td>{esc(t['name'])}</td>"
                f"<td>{_status(t['outcome'])}</td><td>{esc(t.get('failed_step') or '')}</td>"
                f"<td>{esc((t.get('message') or '')[:300])}</td><td>{esc(t.get('duration'))}s</td></tr>")
            if t["outcome"] in ("failed", "error"):
                failures.append(t)
        ok = sum(1 for t in by_feature[feature] if t["outcome"] == "passed")
        parts.append(f"<h2>{esc(feature)} ({ok}/{len(by_feature[feature])} passed)</h2>"
                     "<table><tbody><tr><th>Case</th><th>Test</th><th>Result</th><th>Failed step</th>"
                     "<th>Error</th><th>Time</th></tr>" + "".join(rows) + "</tbody></table>")

    if failures:
        parts.append("<h2>Failures</h2>")
    for t in failures:
        parts.append(f"<h3>{esc(', '.join(t.get('cases') or []) or t['name'])} - {esc(t['name'])}</h3>"
                     f"<p><strong>Failed step:</strong> {esc(t.get('failed_step') or '-')}<br/>"
                     f"<strong>Expected:</strong> {esc(t.get('expected') or '-')}<br/>"
                     f"<strong>Error:</strong> {esc(t.get('message') or '-')}</p>")
        ev = Path(t.get("evidence_dir") or "")
        for shot in SHOTS:
            f = ev / shot
            if t.get("evidence_dir") and f.exists():
                name = attachment_name(t, shot)
                files.append((f, name))
                parts.append(f'<p><ac:image ac:width="900"><ri:attachment ri:filename="{esc(name)}"/></ac:image></p>')
        steps = [s for s in t.get("steps") or []]
        if steps:
            parts.append("<ol>" + "".join(f"<li>[{esc(s['status'])}] {esc(s['title'])}</li>" for s in steps) + "</ol>")
    return title, "".join(parts), files


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("run_dir")
    p.add_argument("--space")
    p.add_argument("--parent-id")
    p.add_argument("--title")
    p.add_argument("--dry-run", action="store_true", help="only write <run_dir>/confluence_page.html")
    args = p.parse_args(argv)

    run_dir = Path(args.run_dir)
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    title, body, files = build_page(results)
    title = args.title or title
    (run_dir / "confluence_page.html").write_text(f"<h1>{esc(title)}</h1>{body}", encoding="utf-8")
    if args.dry_run:
        print(f"Dry run: {run_dir / 'confluence_page.html'} ({len(files)} attachment(s))")
        return 0

    cfg = load_config()
    space = args.space or cfg.get("atlassian.report_space")
    parent = args.parent_id or cfg.get("atlassian.report_parent_id") or ""
    if not space:
        raise SystemExit("Set atlassian.report_space in config/local.yaml or pass --space")
    at = Atlassian.from_config(cfg)
    page = at.create_page(space, title, body, parent_id=str(parent))
    log_page(page)
    for f, name in files:
        at.attach(page["id"], f, name=name)
    url = at.confluence_url + (page.get("_links") or {}).get("webui", f"/pages/viewpage.action?pageId={page['id']}")
    print(f"Published: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
