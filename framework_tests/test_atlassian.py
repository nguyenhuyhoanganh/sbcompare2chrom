"""Confluence/Jira client against a fake Server/DC REST API."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sbtest.atlassian import Atlassian, parse_confluence_url, parse_jira_key, storage_to_markdown
from sbtest.tools.confluence_report import build_page

STORAGE = (
    "<h2>ADD-001 Install from Web Store</h2><p>Precondition: <strong>clean</strong> profile</p>"
    "<ol><li>Open internet://extensions</li><li>Click <em>Add</em></li></ol>"
    "<table><tbody><tr><th>Step</th><th>Expected</th></tr>"
    "<tr><td><p>1. Open store</p></td><td><p>Page shown | ok</p></td></tr></tbody></table>"
    '<ac:structured-macro ac:name="status"><ac:parameter ac:name="title">PASS</ac:parameter></ac:structured-macro>'
    '<ac:image><ri:attachment ri:filename="shot.png"/></ac:image>'
    '<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA[x = 1]]></ac:plain-text-body></ac:structured-macro>'
)


def test_storage_to_markdown():
    md = storage_to_markdown(STORAGE)
    assert "## ADD-001 Install from Web Store" in md
    assert "1. Open internet://extensions" in md and "2. Click _Add_" in md
    assert "| Step | Expected |" in md and "| 1. Open store | Page shown \\| ok |" in md
    assert "[PASS]" in md and "[attachment: shot.png]" in md


def test_parse_urls():
    assert parse_confluence_url("https://c/pages/viewpage.action?pageId=42") == ("id", "42", "")
    assert parse_confluence_url("https://c/spaces/QA/pages/77/Title") == ("id", "77", "")
    assert parse_confluence_url("https://c/display/QA/Add-ons+sanity") == ("title", "QA", "Add-ons sanity")
    assert parse_confluence_url("https://c/x/AbCd")[0] == "tiny"
    assert parse_jira_key("https://j/browse/SIB-123") == "SIB-123"


class _Fake(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def _reply(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.calls.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path.startswith("/rest/api/content/42"):
            return self._reply({"id": "42", "title": "T", "body": {"storage": {"value": STORAGE}}})
        if self.path.startswith("/rest/api/2/issue/SIB-1"):
            return self._reply({"key": "SIB-1", "fields": {"summary": "S", "description": "d"}})
        self._reply({})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        self.calls.append(("POST", self.path, self.headers.get("X-Atlassian-Token"), data))
        self._reply({"id": "99", "_links": {"webui": "/pages/viewpage.action?pageId=99"}})


@pytest.fixture
def fake():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Fake.calls = []
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_client_roundtrip(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    at = Atlassian(fake, fake, token="tok")
    assert at.confluence_page_from_url(f"{fake}/pages/viewpage.action?pageId=42")["title"] == "T"
    assert at.jira_issue("SIB-1")["key"] == "SIB-1"
    page = at.create_page("QA", "Run", "<p>x</p>", parent_id="5")
    f = tmp_path / "page.png"
    f.write_bytes(b"\x89PNG")
    at.attach(page["id"], f, name="BM-001_page.png")
    assert _Fake.calls[0][2] == "Bearer tok"
    post_page = json.loads(_Fake.calls[2][3])
    assert post_page["ancestors"] == [{"id": "5"}] and post_page["space"] == {"key": "QA"}
    assert b'filename="BM-001_page.png"' in _Fake.calls[3][3]
    assert _Fake.calls[3][1] == "/rest/api/content/99/child/attachment" and _Fake.calls[3][2] == "no-check"


def test_build_report_page(tmp_path):
    ev = tmp_path / "f"
    ev.mkdir()
    (ev / "page.png").write_bytes(b"x")
    results = {"meta": {"started": "2026-10-20T10:00:00", "browser_version": "141.0.1.2"}, "tests": [
        {"name": "test_a", "feature": "addons", "cases": ["ADD-001"], "outcome": "passed", "duration": 1},
        {"name": "test_b", "feature": "addons", "cases": ["ADD-002"], "outcome": "failed", "duration": 2,
         "failed_step": "2. Disable", "expected": "off", "message": "AssertionError <x>",
         "evidence_dir": str(ev), "steps": [{"status": "failed", "title": "2. Disable"}]},
    ]}
    title, body, files = build_page(results)
    assert "Chromium 141.0.1.2" in title
    assert "addons (1/2 passed)" in body and "AssertionError &lt;x&gt;" in body
    assert files == [(ev / "page.png", "ADD-002_test_b_page.png")]
    assert 'ri:filename="ADD-002_test_b_page.png"' in body
    import xml.etree.ElementTree as ET  # Confluence rejects storage that is not well-formed XHTML
    ET.fromstring(f'<r xmlns:ac="a" xmlns:ri="r">{body}</r>')
