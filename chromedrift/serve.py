"""Serve a report over localhost so it can look a CL up when you click a row.

The report is a single file on purpose, and that is also its one hard limit:
opened from a disk it is on the ``file://`` origin, and chromium-review sends
no ``Access-Control-Allow-Origin``, so the page cannot ask it anything. Every
route around that was tried and closed:

- JSONP. ``?callback=`` is ignored -- the response is the same XSSI-prefixed
  JSON, so a ``<script>`` tag gets a syntax error rather than a call.
- A real ``Origin`` instead of ``null``, on both chromium-review and gitiles.
  No ``Access-Control-Allow-Origin`` on either.
- An ``OPTIONS`` preflight. HTTP 400.

So the answer is not to defeat the origin but to leave it. Served over
``http://127.0.0.1`` the page has an origin that can talk to something, and
that something is this process, which already knows how to ask Gerrit.

What it buys is the thing a pre-baked report cannot: **you pay for the rows you
open.** ``why`` resolves the top N findings up front because it cannot know
which ones you care about; here the click says so. A report of 3,022 findings
costs nothing until you expand one, and then costs one file's worth of diffs.

Nothing about the file on disk changes. The page asks ``/api/ping`` once on
load and turns the live path on only if something answers, so the very same
``report.html`` mailed to somebody, or opened on an air-gapped machine, behaves
exactly as it did before.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

from .enrich import gerrit
from .model import Finding, Report
from .report import html as html_report

# Enrichment mutates module-level state in `enrich.gerrit` (the failure
# counter, the followed-rename memo), so requests are served one at a time.
# The work inside one request is still parallel, which is where the time goes.
_LOCK = threading.Lock()

# Per click, not per run, and generous on purpose. A run's budget is spread
# over hundreds of rows nobody asked for; a click is one row somebody did, so
# declining it leaves the reader nowhere -- pressing the button again returns
# the same refusal. 600 covers every declaration file measured, the busiest
# being runtime_enabled_features.json5 at 510 CLs and about_flags.cc at 500.
# Typical is far below it: the median file in a real top-300 has 13.
CLICK_BUDGET = 600

_ALLOWED = {"report.html": "text/html; charset=utf-8",
            "report.json": "application/json",
            "report.md": "text/markdown; charset=utf-8"}


class _State:
    """The report, and the one copy of it everything here answers from.

    The page is rendered from the loaded report rather than read off the disk,
    so the payload can never disagree with what a lookup is about to mutate.
    It also means a restart shows everything the last session resolved: the
    lookups are saved back to ``report.json``, and the next render bakes them
    in exactly as ``why`` would have.
    """

    def __init__(self, directory: str, cache_dir: str, budget: int,
                 issues: int = 6, save: bool = True) -> None:
        self.directory = os.path.abspath(directory)
        self.cache_dir = cache_dir
        self.budget = budget
        self.issues = issues
        self.save = save
        self.json_path = os.path.join(self.directory, "report.json")
        with open(self.json_path, encoding="utf-8") as fh:
            self.report: Report = Report.from_dict(json.load(fh))
        self.by_uid: Dict[str, Finding] = {f.uid: f for f in self.report.findings}
        self.resolved = 0
        self._page: Optional[bytes] = None

    # -- the page -----------------------------------------------------------

    def page(self) -> bytes:
        """Rendered on demand and cached until a lookup invalidates it.

        Re-rendering on every lookup would put a two-megabyte render in the
        path of a click; doing it on the next page request costs nothing a
        reader can feel and keeps a reload honest.
        """
        if self._page is None:
            self._page = html_report.render(
                self.report,
                self.report.meta.get("platform", "windows")).encode("utf-8")
        return self._page

    # -- lookups ------------------------------------------------------------

    def resolve(self, uid: str) -> Optional[dict]:
        """Look one finding up, and return the block the page renders."""
        finding = self.by_uid.get(uid)
        if finding is None:
            return None
        already = (finding.enrichment or {}).get("gerrit") or {}
        if already.get("changes"):
            return self._payload(finding)
        with _LOCK:
            # The lookup's own account of itself, kept rather than dropped.
            # `log` was swallowed here, so a fetch that failed reached the
            # reader as "no CL edits this line" -- the one thing this stage is
            # built never to say. What lands on the row is recorded by
            # `enrich` itself, because it belongs to the answer rather than to
            # whoever asked for it.
            notes: List[str] = []
            gerrit.enrich(
                [finding], self.report.from_ref, self.report.to_ref,
                self.cache_dir, top=1, budget=self.budget,
                with_history=self.issues,
                log=lambda m: notes.append(m.strip()))
            for note in notes:
                # `!` is the enricher's own mark for a line that qualifies an
                # answer rather than reporting progress. Flushed, because the
                # process is about to block in `serve_forever` and a
                # block-buffered warning is one nobody reads.
                if note.startswith("!"):
                    print(f"  {note}")
                    try:
                        sys.stdout.flush()
                    except (AttributeError, ValueError):
                        pass
            self.resolved += 1
            self._page = None
            self._persist()
        return self._payload(finding)

    def _persist(self) -> None:
        """Write the report back, atomically.

        A session can spend minutes resolving rows one click at a time, and
        losing that to a closed terminal would make the live path strictly
        worse than `why`. Written through a temporary file in the same
        directory so an interrupted write cannot leave a half-report where a
        whole one was.
        """
        if not self.save:
            return
        tmp = self.json_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.report.to_dict(), fh)
            os.replace(tmp, self.json_path)
        except OSError:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _payload(self, finding: Finding) -> dict:
        """Exactly the shape `_to_rows` produces, so the page has one renderer."""
        rows = html_report._to_rows(
            Report(from_ref=self.report.from_ref, to_ref=self.report.to_ref,
                   findings=[finding], summary={}, meta=self.report.meta),
            self.report.meta.get("platform", "windows"))
        row = rows[0] if rows else {}
        return {k: row[k] for k in html_report.PROVENANCE_KEYS if k in row}


class _Handler(BaseHTTPRequestHandler):
    state: _State = None  # set by serve()
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter than the default one-per-asset
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # The page is local and so is the data; nothing here should be cached
        # by the browser across a re-render of the report.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, doc) -> None:
        self._send(code, json.dumps(doc).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's name
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        if route in ("/", ""):
            route = "/report.html"

        if route == "/api/ping":
            self._json(200, {"ok": True,
                             "from": self.state.report.from_ref,
                             "to": self.state.report.to_ref})
            return

        if route == "/api/why":
            uid = urllib.parse.parse_qs(parsed.query).get("uid", [""])[0]
            if not uid:
                self._json(400, {"error": "uid required"})
                return
            try:
                block = self.state.resolve(uid)
            except Exception as exc:  # a lookup must never take the server down
                self._json(500, {"error": str(exc)})
                return
            if block is None:
                self._json(404, {"error": "no such finding"})
                return
            self._json(200, block)
            return

        # Only the three files the report is made of, and matched on the whole
        # route rather than its basename. Taking the basename could not escape
        # the directory -- it always yields a plain filename, joined to a fixed
        # path -- but it accepted `/%2e%2e/report.json` as a request for
        # `report.json`, and a server that answers a request it does not
        # understand is how the next version gets this wrong.
        name = route[1:]
        if name not in _ALLOWED:
            self._json(404, {"error": "not found"})
            return
        if name == "report.html":
            # Rendered from the report this process holds, not read off the
            # disk, so a reload always shows what the clicks have resolved.
            self._send(200, self.state.page(), _ALLOWED[name])
            return
        path = os.path.join(self.state.directory, name)
        if not os.path.exists(path):
            self._json(404, {"error": f"{name} is not in this directory"})
            return
        with open(path, "rb") as fh:
            self._send(200, fh.read(), _ALLOWED[name])


def serve(directory: str, cache_dir: str, port: int = 8787,
          budget: int = CLICK_BUDGET, issues: int = 6, save: bool = True,
          log=print) -> int:
    """Run until interrupted. Bound to the loopback interface only."""
    # Flushed, because the process then blocks forever in serve_forever: with
    # stdout going anywhere but a terminal it is block-buffered, so the address
    # a reader needs would sit in the buffer until the server was stopped.
    def say(line: str) -> None:
        log(line)
        try:
            sys.stdout.flush()
        except (AttributeError, ValueError):
            pass

    state = _State(directory, cache_dir, budget, issues=issues, save=save)
    handler = type("_Bound", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    say(f"  {state.report.from_ref} -> {state.report.to_ref}, "
        f"{len(state.by_uid)} findings")
    say(f"  http://127.0.0.1:{port}/")
    say(f"  expanding a row without a CL looks one up, reading at most "
        f"{budget} diffs")
    say(f"  lookups are {'saved back to report.json' if save else 'not saved'}")
    say("  ctrl-c to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log(f"\nstopped after resolving {state.resolved} row(s)"
            + (f"; {os.path.join(state.directory, 'report.json')} holds them"
               if save and state.resolved else ""))
    finally:
        httpd.server_close()
    return 0
