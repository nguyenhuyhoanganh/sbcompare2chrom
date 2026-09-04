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
open.** Resolving the top N up front cannot know which ones you care about;
here the click says so. A report of 3,022 findings costs nothing until you
expand one, and then costs one file's worth of diffs.

Nothing about the file on disk changes. The page asks ``/api/ping`` once on
load and turns the live path on only if something answers, so the very same
``report.html`` mailed to somebody, or opened on an air-gapped machine, behaves
exactly as it did before.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

from . import cluster
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
# being flag-metadata.json at 662 CLs, about_flags.cc at 500 and
# runtime_enabled_features.json5 at 337 -- and the first of those is itself
# trimmed to 500 by the per-file ceiling before any diff is read. Typical is
# far below: across a stratified sample of all sixteen kinds the median file
# has 8.
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
    in.
    """

    def __init__(self, directory: str, cache_dir: str, budget: int,
                 save: bool = True, refresh: bool = False,
                 chat=None) -> None:
        self.directory = os.path.abspath(directory)
        self.cache_dir = cache_dir
        self.budget = budget
        self.save = save
        # Re-asking a row still reads the HTTP cache, so a bad response cached
        # once is a bad answer for ever. This is the only way past it, and the
        # only caller `enrich`'s `refresh` has ever had.
        self.refresh = refresh
        self.chat = chat
        # Minted per process and never written down. The page reads it from
        # `/api/ping`, which a page on another origin can send but cannot read
        # -- no `Access-Control-Allow-Origin` goes out, which is the same
        # absence that made this server necessary in the first place. Without
        # it any page open in the same browser could post to this port, and
        # with a chat on the other end that is a way to run commands here.
        self.token = secrets.token_urlsafe(16)
        self.json_path = os.path.join(self.directory, "report.json")
        self._load()
        self.resolved = 0
        self.restaled = 0
        self._page: Optional[bytes] = None
        # Derived on the first click, not at startup: it costs two requests,
        # and a server nobody opens a row on should not spend them -- nor
        # should the test suite, which runs with no network.
        self._before_main: Optional[str] = None

    # -- the file underneath ------------------------------------------------

    def _load(self) -> None:
        with open(self.json_path, encoding="utf-8") as fh:
            self.report: Report = Report.from_dict(json.load(fh))
        self.by_uid: Dict[str, Finding] = {f.uid: f
                                           for f in self.report.findings}
        try:
            self._mtime = os.path.getmtime(self.json_path)
        except OSError:
            self._mtime = 0.0

    def _reload_if_changed(self) -> bool:
        """Pick up a `report.json` something else has written.

        The page used to be the only writer, so the copy in memory was the
        only copy that mattered. It is not any more: `chromiumdiff why` writes
        the same file, and a chat can run it. Without this the next lookup
        here would write the in-memory report over the answers that command
        had just saved, and they would be gone with nothing to say they had
        ever been there.
        """
        try:
            mtime = os.path.getmtime(self.json_path)
        except OSError:
            return False
        if mtime <= self._mtime:
            return False
        try:
            self._load()
        except (OSError, ValueError):
            # A half-written file is not a reason to lose the working one. The
            # next lookup tries again, by which time the writer has finished.
            return False
        self._page = None
        return True

    # -- the page -----------------------------------------------------------

    def page(self) -> bytes:
        """Rendered on demand and cached until a lookup invalidates it.

        Re-rendering on every lookup would put a two-megabyte render in the
        path of a click; doing it on the next page request costs nothing a
        reader can feel and keeps a reload honest.
        """
        self._reload_if_changed()
        if self._page is None:
            self._page = html_report.render(
                self.report,
                self.report.meta.get("platform", "windows")).encode("utf-8")
        return self._page

    # -- lookups ------------------------------------------------------------

    def resolve(self, uid: str) -> Optional[dict]:
        """Look one finding up, and return the block the page renders."""
        self._reload_if_changed()
        finding = self.by_uid.get(uid)
        if finding is None:
            return None
        already = (finding.enrichment or {}).get("gerrit") or {}
        if already.get("changes") and not self._stale(already):
            return self._payload(finding)
        with _LOCK:
            # The lookup's own account of itself, kept rather than dropped.
            # `log` was swallowed here, so a fetch that failed reached the
            # reader as "no CL edits this line" -- the one thing this stage is
            # built never to say. What lands on the row is recorded by
            # `enrich` itself, because it belongs to the answer rather than to
            # whoever asked for it.
            notes: List[str] = []
            # Dropped rather than written over: `enrich` reuses the block it
            # finds, so a key an older run set and this one does not would
            # survive the re-lookup and be read as part of the new answer.
            if already.get("changes"):
                (finding.enrichment or {}).pop("gerrit", None)
            gerrit.enrich(
                [finding], self.report.from_ref, self.report.to_ref,
                self.cache_dir, top=1, budget=self.budget,
                # None of it, on purpose. The CLs already carry their `Bug:`
                # footers for free in the search response, so the row can name
                # every issue without asking the tracker anything; the history
                # behind one is fetched only when a reader picks that CL and
                # asks. A row citing six issues used to spend twelve requests
                # before the reader had decided which CL mattered.
                with_history=0, refresh=self.refresh,
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
            if already.get("changes"):
                self.restaled += 1
            # Findings are grouped by the links Chromium declares, and a
            # shared CL is one of them -- but the only place that ran was
            # `run`, which never asks Gerrit anything, so the CL rule could
            # never fire. A lookup is the moment the evidence for it arrives,
            # so the grouping is redone here. It fetches nothing: it reads
            # what the row already holds, and the pass over the report costs
            # less than the render that follows it.
            groups = cluster.annotate(self.report.findings)
            # The summary is where `report.md` reads the groups from, and it
            # was written once by `run` -- before any CL existed to group on.
            # Re-rendering the report after a session of lookups would have
            # printed the run's groups over the lookups' findings.
            if self.report.summary is not None:
                self.report.summary["clusters"] = cluster.summarize(groups)
            self._page = None
            self._persist()
        return self._payload(finding)

    def _stale(self, block: dict) -> bool:
        """Was this answer written by a version of the lookup since corrected?

        A stored answer is not re-fetched -- that is what makes a click cheap
        the second time -- and the cost of that is a report outliving both the
        bug it was written under and the request it lost. Three cases, all
        visible in what was stored, so none needs a flag or a version stamp:

        - A CL dated after the target left main cannot be in the tree being
          compared. The window used to run to the tag's date, six weeks past
          the branch point, and 16 of the 60 rows in one real report cite such
          a CL.
        - A CL with no `at` was compacted before the submit stamp was kept,
          so every list it is in was ordered by the day. A revert and its
          reland land on the same day.
        - A lookup that lost requests left an answer it says itself is not a
          finished search. The panel tells the reader to open the row again to
          retry, and until this was here that instruction did nothing: the row
          had CLs, so it was served rather than asked.

        Recomputed, not repaired: the row is asked again, which is the only
        thing that can be right about it.
        """
        if block.get("failed_fetches"):
            return True
        changes = block.get("changes") or []
        if any(not cl.get("at") for cl in changes):
            return True
        if self._before_main is None:
            try:
                window = gerrit.window_for(self.report.from_ref,
                                           self.report.to_ref, self.cache_dir)
            except Exception:
                window = None
            # "" means the question cannot be asked, not that it was answered
            # no: a report whose refs no longer resolve keeps what it holds.
            self._before_main = window[1] if window else ""
        return bool(self._before_main) and any(
            (cl.get("date") or "") > self._before_main for cl in changes)

    def issue(self, issue: str) -> dict:
        """One issue's title and the CLs citing it, in the row's own shape.

        Serialised on the same lock as a lookup: `enrich.gerrit` keeps
        module-level state and two callers inside it at once is how a failure
        counter starts reporting somebody else's failures.

        Not written back to `report.json`. A row's CLs are the answer and are
        worth keeping; an issue's history is context the reader asked to see
        once, and the HTTP cache already makes the second ask free.
        """
        with _LOCK:
            meta = gerrit.issue_meta(issue, self.cache_dir, self.refresh)
            # The default limit, matching what a baked run asks for, so a
            # click reads the entry a run already wrote instead of missing on
            # a key that differs only in a number nobody chose.
            cls = gerrit.issue_history(issue, self.cache_dir,
                                       refresh=self.refresh)
        return {"id": issue,
                "restricted": not meta.get("public", True),
                "t": meta.get("title") or "",
                "total": len(cls),
                "cls": [{"n": c.get("number"), "d": c.get("date", ""),
                         "s": c.get("subject", "")} for c in cls[:12]]}

    def _persist(self) -> None:
        """Write the report back, atomically.

        A session can spend minutes resolving rows one click at a time, and
        losing that to a closed terminal would make the live path strictly
        worse than not having it. Written through a temporary file in the same
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
            try:
                self._mtime = os.path.getmtime(self.json_path)
            except OSError:
                pass
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

    def _chat_allowed(self) -> bool:
        """Is this request from the page this process served?

        Two things are checked and they cover different attackers. The token
        answers "did the sender read `/api/ping` from this origin", which only
        a same-origin page could have done. The `Origin` header answers "does
        the browser think this is a cross-site request", which is the case the
        token is protecting against in the first place -- and a request with
        neither is a curl, which is fine.

        This route runs commands. Everything else here only reads a report, so
        the cost of being wrong is not the same and neither is the check.
        """
        if self.state.chat is None:
            self._json(404, {"error": "not serving a chat -- start with "
                                      "--chat to enable it"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host', '')}":
            self._json(403, {"error": "cross-origin"})
            return False
        if self.headers.get("X-Chromiumdiff-Token") != self.state.token:
            self._json(403, {"error": "this page was not served by this "
                                      "process -- reload it"})
            return False
        return True

    def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's name
        route = urllib.parse.urlparse(self.path).path
        if route != "/api/chat":
            self._json(404, {"error": "not found"})
            return
        if not self._chat_allowed():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        # A body large enough to be a denial of service is not a question.
        if length > 64 * 1024:
            self._json(413, {"error": "that is not a question"})
            return
        try:
            doc = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "expected JSON"})
            return
        if not isinstance(doc, dict):
            self._json(400, {"error": "expected an object"})
            return
        answer = self.state.chat.ask(doc.get("session"), doc.get("message"))
        self._json(400 if "error" in answer else 200, answer)

    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's name
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        if route in ("/", ""):
            route = "/report.html"

        if route == "/api/ping":
            # The token rides on the reply rather than being baked into the
            # page, so the same rendered `report.html` is safe to save or mail:
            # nothing in the file grants anything. A page on another origin can
            # send this request and cannot read what comes back.
            self._json(200, {"ok": True,
                             "from": self.state.report.from_ref,
                             "to": self.state.report.to_ref,
                             "chat": self.state.chat is not None,
                             "token": self.state.token})
            return

        if route == "/api/chat/events":
            if not self._chat_allowed():
                return
            query = urllib.parse.parse_qs(parsed.query)
            turn = query.get("turn", [""])[0]
            try:
                since = int(query.get("since", ["0"])[0])
            except ValueError:
                since = 0
            block = self.state.chat.events(turn, since)
            if block is None:
                self._json(404, {"error": "no such turn"})
                return
            self._json(200, block)
            return

        if route == "/api/chat/history":
            if not self._chat_allowed():
                return
            sid = urllib.parse.parse_qs(parsed.query).get("session", [""])[0]
            block = self.state.chat.history(sid)
            if block is None:
                self._json(404, {"error": "no such conversation"})
                return
            self._json(200, block)
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

        if route == "/api/issue":
            issue = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
            if not issue.isdigit():
                self._json(400, {"error": "numeric issue id required"})
                return
            try:
                self._json(200, self.state.issue(issue))
            except Exception as exc:  # never take the server down for one issue
                self._json(500, {"error": str(exc)})
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
          budget: int = CLICK_BUDGET, save: bool = True,
          refresh: bool = False, chat=None, log=print) -> int:
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

    state = _State(directory, cache_dir, budget, save=save, refresh=refresh,
                   chat=chat)
    handler = type("_Bound", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    say(f"  {state.report.from_ref} -> {state.report.to_ref}, "
        f"{len(state.by_uid)} findings")
    say(f"  http://127.0.0.1:{port}/")
    say(f"  expanding a row without a CL looks one up, reading at most "
        f"{budget} diffs")
    if chat is not None:
        # Said plainly, because it is the one thing about this server that is
        # not just reading a file. Somebody starting it should know what they
        # turned on without going and reading for it.
        say(f"  a chat panel is on: questions run commands in {directory} on "
            f"this machine")
    say(f"  lookups are {'saved back to report.json' if save else 'not saved'}")
    say("  ctrl-c to stop, and it will say how to fold what you found back "
        "into report.md")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        # `say`, not `log`: this is the last thing the process does, and with
        # stdout going anywhere but a terminal a plain print dies in the
        # buffer. The start-up lines learned that already.
        say(f"\nstopped after resolving {state.resolved} row(s)"
            + (f"; {os.path.join(state.directory, 'report.json')} holds them"
               if save and state.resolved else ""))
        # `report.md` and `report.html` on disk are what a session leaves
        # behind for anyone who was not at the keyboard, and neither is
        # rewritten here -- overwriting a file the reader may have open, or
        # edited, is worse than leaving it a command away. Nobody guesses the
        # command, though, so it is printed at the one moment it is wanted.
        if save and state.resolved:
            say(f"  the CLs, the issues and the groups they formed reach "
                f"report.md and report.html with:")
            # `--out` is not optional here: without it `report` writes to
            # stdout, which prints a report to the terminal and leaves the two
            # files exactly as stale as they were.
            say(f"    python3 -m chromiumdiff report "
                f"{os.path.join(state.directory, 'report.json')} "
                f"--format both --out "
                f"{os.path.join(state.directory, 'report')}")
    finally:
        httpd.server_close()
    return 0
