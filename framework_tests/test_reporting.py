"""results.json -> Confluence export folder."""
import json
import xml.etree.ElementTree as ET

from sbtest.reporting.confluence_export import build, export


def _results(ev_dir):
    return {"meta": {"started": "2026-10-20T10:00:00", "browser_version": "141.0.1.2", "target": "samsung"}, "tests": [
        {"name": "test_a", "feature": "addons", "cases": ["ADD-001"], "outcome": "passed", "duration": 1},
        {"name": "test_b", "feature": "addons", "cases": ["ADD-002"], "outcome": "failed", "duration": 2,
         "failed_step": "2. Disable", "expected": "off", "message": "AssertionError <x> | y",
         "evidence_dir": str(ev_dir), "steps": [{"status": "failed", "title": "2. Disable"}]},
    ]}


def test_build_page(tmp_path):
    (tmp_path / "page.png").write_bytes(b"x")
    page = build(_results(tmp_path))
    assert "samsung" in page["title"] and "Chromium 141.0.1.2" in page["title"]
    assert "addons (1/2 passed)" in page["storage"] and "AssertionError &lt;x&gt;" in page["storage"]
    ET.fromstring(f'<r xmlns:ac="a" xmlns:ri="r">{page["storage"]}</r>')  # Confluence needs well-formed XHTML
    assert page["files"] == [(tmp_path / "page.png", "ADD-002_test_b_page.png")]
    assert "![ADD-002_test_b_page.png](attachments/ADD-002_test_b_page.png)" in page["markdown"]
    assert "AssertionError <x> \\| y" in page["markdown"]


def test_export_folder(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    (ev / "page.png").write_bytes(b"png")
    run = tmp_path / "run"
    run.mkdir()
    (run / "results.json").write_text(json.dumps(_results(ev)))
    out = export(run)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["attachments"] == ["attachments/ADD-002_test_b_page.png"]
    assert (out / "attachments" / "ADD-002_test_b_page.png").read_bytes() == b"png"
    assert (out / "page.md").exists() and (out / "page.storage.html").exists()
