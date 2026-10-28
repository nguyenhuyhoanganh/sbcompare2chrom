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
    md.write_text("| BM-001 | A | High | web |  | x.md | ✅ Pass |\n| DL-003 | B | Medium | native |  | y.md | ⏳ Not run |\n",
                  encoding="utf-8")
    assert co.previous_results(md) == {"BM-001": "passed", "DL-003": None}
    assert co.previous_results(tmp_path / "missing.md") == {}


def test_summary_lists_failures_with_evidence(tmp_path):
    import json

    from sbtest.tools.summary import collect

    ev = tmp_path / "failures" / "t2"
    ev.mkdir(parents=True)
    tests = [
        {"nodeid": "tests/features/general/test_navigation.py::test_back_forward", "name": "test_back_forward",
         "feature": "general", "cases": ["GEN-001"], "outcome": "passed", "duration": 1.0},
        {"nodeid": "tests/features/downloads/test_downloads.py::test_clear_all", "name": "test_clear_all",
         "feature": "downloads", "cases": ["DL-003"], "outcome": "failed", "duration": 2.0,
         "failed_step": "3. Clear all", "message": "Timed out", "evidence_dir": str(ev)},
    ]
    (tmp_path / "results.json").write_text(json.dumps({"meta": {"selection": "all"}, "tests": tests}))
    data = collect(tmp_path)
    assert data["verdict"] == "BUILD FAILED"
    assert data["per_feature"] == {"downloads": {"failed": 1}, "general": {"passed": 1}}
    assert data["failures"] == [{"case": "DL-003", "title": "Clear all", "outcome": "failed",
                                 "test": tests[1]["nodeid"], "failed_step": "3. Clear all", "error": "Timed out",
                                 "evidence": str(ev / "failure.txt")}]


def test_marks_are_recorded_only_while_step_pictures_are_on():
    from sbtest import steps

    steps.reset()
    with steps.step("1. Off"):
        steps.mark("click", "A", screen=(0, 0, 10, 10))
    assert "marks" not in steps.history()[0]
    seen = []
    steps.set_listener(lambda rec, n: None, on_mark=lambda rec, n, i, m: seen.append((n, i, m["kind"])))
    try:
        with steps.step("2. On"):
            steps.mark("click", "Save", screen=(0, 0, 10, 10))
            steps.mark("keys", "^d")
    finally:
        steps.set_listener(None)
        steps.reset()
    assert seen == [(2, 1, "click"), (2, 2, "keys")]   # each interaction is announced before it runs


def test_draw_marks_frames_targets_and_lists_shortcuts():
    from PIL import Image

    from sbtest.reporting.evidence import draw_marks

    img = Image.new("RGB", (800, 600), "white")
    marks = [{"kind": "click", "label": "Save", "web": None, "screen": (1100, 400, 1200, 440)},   # screen px
             {"kind": "type", "label": "'abc'", "web": (10, 20, 100, 30, 2.0), "screen": None},  # CSS px, dpr 2
             {"kind": "keys", "label": "^d", "web": None, "screen": None}]                       # no place
    draw_marks(img, marks, origin=(1000, 300), viewport=(50, 60))
    red = lambda xy: img.getpixel(xy)[0] > 200 and img.getpixel(xy)[1] < 60
    # frames sit 3 px outside the target so they never hide it
    assert red((100 - 2, 120)) and not red((100 + 5, 120))     # click: left edge at 1100-1000
    assert red((50 + 20 - 2, 60 + 40 + 30))                    # type: viewport + x*dpr, mid height
    assert img.getpixel((5, 5)) != (255, 255, 255)   # shortcut listed in the strip at the top


def test_confluence_step_pictures_of_failed_cases_by_default(tmp_path):
    from PIL import Image

    from sbtest.reporting.confluence_export import export

    run, results = _run_with_failure(tmp_path)
    pics = []
    for t in results["tests"]:
        p = tmp_path / f"{t['name']}_01-1_click.jpg"
        Image.new("RGB", (40, 20), "white").save(p)
        pics.append(p)
        t["steps"] = [{"status": t["outcome"], "title": "1. Do", "pictures": [str(p)]}]
    (run / "results.json").write_text(json.dumps(results), encoding="utf-8")
    for mode, expected in (("failed", {"ADD-002"}), ("all", {"ADD-001", "ADD-002"}), ("none", set())):
        out = export(run, mode)
        names = json.loads((out / "manifest.json").read_text())["attachments"]
        cases = {n.split("/")[-1].split("_")[0] for n in names if "_01-1_" in n}
        assert cases == expected, mode
        assert (('ac:name="expand"' in (out / "page.storage.html").read_text(encoding="utf-8")) == bool(expected))
