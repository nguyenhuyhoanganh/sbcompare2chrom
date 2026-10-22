"""Case parser + per-build report (no browser)."""
import json

from sbtest.reporting.cases import parse_file
from sbtest.reporting.report import build_rows, generate, summary

CASE_MD = """# Feature

## BM-900 Add a bookmark
- Priority: High
- Type: web
- Precondition: Clean profile
- Steps:
  1. Open the manager
  2. Add "X", a long step
     that wraps
- Expected:
  - "X" is listed
- Automated: tests/features/bookmarks/test_x.py::test_add

## BM-901 Second
- Type: native
- Steps:
  1. Do it
- Expected: it works
"""


def test_parse_case_file(tmp_path):
    md = tmp_path / "x.md"
    md.write_text(CASE_MD, encoding="utf-8")
    a, b = parse_file(md, "bookmarks", "cases/bookmarks/x.md")
    assert (a.id, a.title, a.priority, a.type, a.precondition) == ("BM-900", "Add a bookmark", "High", "web", "Clean profile")
    assert a.steps == ["Open the manager", 'Add "X", a long step that wraps']
    assert a.expected == ['"X" is listed'] and a.automated.endswith("::test_add")
    assert (b.id, b.steps, b.expected) == ("BM-901", ["Do it"], ["it works"])


def test_report_rows_verdict_and_files(tmp_path):
    md = tmp_path / "x.md"
    md.write_text(CASE_MD, encoding="utf-8")
    cases = {c.id: c for c in parse_file(md, "bookmarks", "x.md")}
    results = {"meta": {"product_version": "31.0.0.55", "browser_version": "148.0"},
               "tests": [
                   {"nodeid": "t.py::test_add", "name": "test_add", "feature": "bookmarks", "cases": ["BM-900"],
                    "outcome": "passed", "duration": 1.0, "message": "", "steps": [], "screenshot": ""},
                   {"nodeid": "t.py::test_two", "name": "test_two", "feature": "bookmarks", "cases": ["BM-901"],
                    "outcome": "skipped", "duration": 0, "message": "native UI not available",
                    "steps": []}]}
    rows = build_rows(results, cases)
    assert [(r.case_id, r.result) for r in rows] == [("BM-900", "passed"), ("BM-901", "skipped")]
    s = summary(rows, results["meta"])
    assert s["verdict"] == "PASSED" and s["build"] == "Samsung Browser 31.0.0.55 (Chromium 148.0)"
    results["tests"][0].update(outcome="failed", failed_step="2. Add", message="boom")
    assert summary(build_rows(results, cases), results["meta"])["verdict"] == "FAILED"

    run = tmp_path / "run"
    run.mkdir()
    (run / "results.json").write_text(json.dumps(results), encoding="utf-8")
    index = generate(run)
    html = index.read_text(encoding="utf-8")
    assert "BUILD FAILED" in html and "Failed at:" in html and (run / "report" / "report.md").exists()


def _run_with_failure(tmp_path):
    """A results.json with one passed and one failed case (with a screenshot), like a real run."""
    shot = tmp_path / "shot.png"
    from PIL import Image

    Image.new("RGB", (40, 20), "white").save(shot)
    results = {"meta": {"started": "2026-10-20T10:00:00", "browser_version": "148.0.1.2",
                        "product_version": "31.0.0.55"},
               "tests": [
                   {"nodeid": "a.py::test_a", "name": "test_a", "feature": "addons", "cases": ["ADD-001"],
                    "outcome": "passed", "duration": 1, "screenshot": str(shot), "steps": []},
                   {"nodeid": "a.py::test_b", "name": "test_b", "feature": "addons", "cases": ["ADD-002"],
                    "outcome": "failed", "duration": 2, "failed_step": "2. Disable", "message": "AssertionError <x> | y",
                    "screenshot": str(shot), "steps": [{"status": "failed", "title": "2. Disable"}]}]}
    run = tmp_path / "run"
    run.mkdir()
    (run / "results.json").write_text(json.dumps(results), encoding="utf-8")
    return run, results


def test_confluence_page_is_well_formed(tmp_path):
    import xml.etree.ElementTree as ET

    from sbtest.reporting.confluence_export import build
    from sbtest.reporting.report import _copy_images

    run, results = _run_with_failure(tmp_path)
    rows = build_rows(results, {})
    _copy_images(rows, run)
    page = build(rows, results["meta"])
    assert "31.0.0.55" in page["title"] and page["title"].endswith("FAILED")
    assert "Addons (1/2 passed)" in page["storage"] and "AssertionError &lt;x&gt;" in page["storage"]
    ET.fromstring(f'<r xmlns:ac="a" xmlns:ri="r">{page["storage"].replace("&#160;", " ")}</r>')  # Confluence needs XHTML


def test_confluence_export_folder(tmp_path):
    from sbtest.reporting.confluence_export import export

    run, _ = _run_with_failure(tmp_path)
    out = export(run)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["attachments"] and all((out / a).exists() for a in manifest["attachments"])
    assert (out / "page.md").exists() and (out / "page.storage.html").exists()

def test_clear_dir_empties_only_folders_inside_artifacts(tmp_path):
    import pytest

    from sbtest.reporting.cleanup import clear_dir

    results = tmp_path / "test-results"
    (results / "failures" / "test_x").mkdir(parents=True)
    (results / "results.json").write_text("{}")
    (results / "logs").mkdir()
    (results / "logs" / "chromedriver_x.log").write_text("log")
    (tmp_path / ".cache").mkdir()

    assert clear_dir(results, tmp_path) == []
    assert results.is_dir() and not list(results.iterdir())
    assert (tmp_path / ".cache").exists()                      # outside the cleared folder
    assert clear_dir(tmp_path / "doctor", tmp_path) == []      # missing folder: created empty
    for bad in (tmp_path, tmp_path.parent / "elsewhere"):
        with pytest.raises(ValueError):
            clear_dir(bad, tmp_path)


def test_overview_keeps_results_of_cases_not_rerun(tmp_path):
    from sbtest.tools import case_overview as co

    md = tmp_path / "TESTCASES.md"
    md.write_text("| BM-001 | A | High | web |  | x.md | ✅ Pass |\n| DL-003 | B | Medium | native |  | y.md | ⏳ Chưa chạy |\n",
                  encoding="utf-8")
    assert co.previous_results(md) == {"BM-001": "passed", "DL-003": None}
    assert co.previous_results(tmp_path / "missing.md") == {}
