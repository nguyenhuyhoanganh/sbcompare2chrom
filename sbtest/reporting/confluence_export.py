"""Turn a run into a folder that becomes one Confluence page per build.

    <run_dir>/confluence/
        manifest.json        {"title", "body_storage", "body_markdown", "attachments": [...]}
        page.storage.html    Confluence storage format: verdict, build info, one table per
                             feature (ID, name, steps, expected, result, screenshot)
        page.md              the same report in Markdown
        attachments/         one result screenshot per test (JPEG), referenced by the page,
                             + step pictures (--screenshot-steps) of the cases chosen by
                             report.confluence_step_pictures: failed (default) | all | none,
                             shown in one collapsed "Expand" block per case under each table

Same rows as the HTML report (sbtest/reporting/report.py). The upload itself (create the
page, attach the files) is done with the Confluence skill; nothing here talks to Confluence.
"""
from __future__ import annotations

import html
import json
import shutil
from collections import defaultdict
from pathlib import Path

from sbtest.reporting.cases import load_cases
from sbtest.reporting.report import RESULT_LABEL, Row, _copy_images, build_info, build_rows, summary, write_markdown
from sbtest.utils import slug

STEP_PICTURES = ("failed", "all", "none")

COLORS = {"passed": "Green", "failed": "Red", "error": "Red", "skipped": "Grey"}


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _status(result: str) -> str:
    return (f'<ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">{COLORS.get(result, "Grey")}'
            f'</ac:parameter><ac:parameter ac:name="title">{esc(RESULT_LABEL.get(result, result.upper()))}'
            '</ac:parameter></ac:structured-macro>')


def _wants_steps(r: Row, mode: str) -> bool:
    return any(x.get("files") for x in r.executed) and (
        mode == "all" or (mode == "failed" and r.result in ("failed", "error")))


def _steps_block(r: Row, files: list[str]) -> str:
    """Collapsed "Expand" block with the step pictures of one case (titles + full-width images)."""
    n = sum(len(x["files"]) for x in r.executed)
    body = []
    for x in r.executed:
        if not x.get("files"):
            continue
        body.append(f"<p><strong>[{esc(x['status'])}] {esc(x['title'])}</strong></p><p>")
        for label, name in x["files"]:
            files.append(name)
            body.append(f'<ac:image ac:width="600" ac:title="{esc(label)}"><ri:attachment ri:filename="{esc(name)}"/></ac:image> ')
        body.append("</p>")
    title = f"{r.case_id} {r.title} - step pictures ({n}) - {RESULT_LABEL.get(r.result, r.result.upper())}"
    return ('<ac:structured-macro ac:name="expand"><ac:parameter ac:name="title">' + esc(title[:200])
            + '</ac:parameter><ac:rich-text-body>' + "".join(body) + "</ac:rich-text-body></ac:structured-macro>")


def build(rows: list[Row], meta: dict, step_pictures: str = "failed") -> dict:
    """-> {"title", "storage", "files": [attachment names]} (images already in attachments/)."""
    s = summary(rows, meta)
    c = s["counts"]
    title = f"Sanity {s['build']} - {(meta.get('started') or '')[:16].replace('T', ' ')} - {s['verdict']}"
    color = "Green" if s["verdict"] == "PASSED" else "Red"
    st = [f'<p><ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">{color}</ac:parameter>'
          f'<ac:parameter ac:name="title">BUILD {esc(s["verdict"])}</ac:parameter></ac:structured-macro> '
          + " ".join(f"{_status(k)} {c.get(k, 0)}" for k in ("passed", "failed", "error", "skipped"))
          + f" &#160; {s['total']} cases</p>",
          "<table><tbody>" + "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in build_info(meta))
          + "</tbody></table>"]
    by_feature: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_feature[r.feature].append(r)
    files = []
    for feature, group in by_feature.items():
        ok = sum(r.result == "passed" for r in group)
        run = sum(r.result in ("passed", "failed", "error") for r in group)
        st.append(f"<h2>{esc(feature.capitalize())} ({ok}/{run} passed)</h2>")
        st.append("<table><tbody><tr><th>ID</th><th>Name / description</th><th>Steps</th><th>Expected</th>"
                  "<th>Result</th><th>Screenshot</th></tr>")
        for r in group:
            steps = "<ol>" + "".join(f"<li>{esc(x)}</li>" for x in r.steps) + "</ol>" if r.steps else ""
            exp = "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in r.expected) + "</ul>" if r.expected else ""
            res = _status(r.result) + f" {r.duration:.1f}s"
            if r.result in ("failed", "error"):
                res += f"<p><strong>Failed at:</strong> {esc(r.failed_step or '-')}</p><p>{esc(r.error[:500])}</p>"
            elif r.result == "skipped":
                res += f"<p>{esc(r.error[:200])}</p>"
            shot = ""
            if r.image:
                name = Path(r.image).name
                files.append(name)
                shot = f'<ac:image ac:width="300"><ri:attachment ri:filename="{esc(name)}"/></ac:image>'
            desc = esc(r.title) + (f"<br/><em>{esc(r.description)}</em>" if r.description else "")
            if _wants_steps(r, step_pictures):
                res += "<p><em>Step pictures below the table.</em></p>"
            st.append(f"<tr><td><strong>{esc(r.case_id)}</strong></td><td>{desc}</td><td>{steps}</td><td>{exp}</td>"
                      f"<td>{res}</td><td>{shot}</td></tr>")
        st.append("</tbody></table>")
        st.extend(_steps_block(r, files) for r in group if _wants_steps(r, step_pictures))
    return {"title": title, "storage": "".join(st), "files": sorted(set(files))}


def _flatten_step_pictures(rows: list[Row], out: Path, mode: str) -> None:
    """Confluence attachments have no folders: attachments/steps/<test>/02-1_click.jpg ->
    attachments/<case>_02-1_click.jpg, kept only for the chosen cases (``files`` per step)."""
    for r in rows:
        keep = _wants_steps(r, mode) if mode != "none" else False
        for x in r.executed:
            x["files"] = []
            for label, rel in x.get("imgs") or []:
                src = out / rel.replace("img/", "attachments/", 1)
                if not keep or not src.exists():
                    continue
                name = f"{slug(r.case_id, 30)}_{src.name}"
                shutil.copyfile(src, out / "attachments" / name)
                x["files"].append((label, name))
        if mode == "failed" and r.result not in ("failed", "error"):
            for x in r.executed:
                x["files"] = []
    shutil.rmtree(out / "attachments" / "steps", ignore_errors=True)


def export(run_dir: Path, step_pictures: str | None = None) -> Path:
    """Write <run_dir>/confluence/ and return its path. ``step_pictures``: failed | all | none
    (default: report.confluence_step_pictures of the config)."""
    if step_pictures is None:
        from sbtest.config import load_config

        step_pictures = load_config().get("report.confluence_step_pictures") or "failed"
    if step_pictures not in STEP_PICTURES:
        raise ValueError(f"step_pictures: one of {STEP_PICTURES}, not {step_pictures!r}")
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = build_rows(results, load_cases())
    out = run_dir / "confluence"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    _copy_images(rows, out)                       # -> out/img/*.jpg
    (out / "img").rename(out / "attachments")
    for r in rows:
        r.image = r.image.replace("img/", "attachments/", 1) if r.image else ""
    for r in rows:   # _wants_steps looks at "files": mark which executed steps have pictures at all
        for x in r.executed:
            x["files"] = list(x.get("imgs") or [])
    _flatten_step_pictures(rows, out, step_pictures)
    page = build(rows, results["meta"], step_pictures)
    (out / "page.storage.html").write_text(page["storage"], encoding="utf-8")
    write_markdown(rows, results["meta"], out)
    (out / "report.md").rename(out / "page.md")
    shown = [r for r in rows if any(x.get("files") for x in r.executed)]
    if shown:   # Markdown pages get the step pictures as a plain list
        md = ["", "## Step pictures", ""]
        for r in shown:
            md += [f"### {r.case_id} {r.title} - {RESULT_LABEL.get(r.result, r.result.upper())}", ""]
            for x in r.executed:
                if x.get("files"):
                    md += [f"**[{x['status']}] {x['title']}**", ""]
                    md += [f"![{label}](attachments/{name})" for label, name in x["files"]] + [""]
        with (out / "page.md").open("a", encoding="utf-8") as f:
            f.write("\n".join(md))
    manifest = {"title": page["title"], "body_storage": "page.storage.html", "body_markdown": "page.md",
                "attachments": [f"attachments/{name}" for name in page["files"]]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out
