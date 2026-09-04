"""Tests for what an agent is given: a bounded runner, and a route to a row.

The interesting cases are the bounds, not the happy path: what a command that
prints too much costs, what a command that refuses to stop costs, and whether
a failing query is reported at the line the model actually wrote.

`why` is here rather than beside the other commands because it exists for a
caller that is not a browser. Its output is read by whatever asked, so what it
says about a weak verdict matters as much as what it finds.
"""

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chromiumdiff.agent import tools


def _report(path, findings):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"from_ref": "a", "to_ref": "b", "findings": findings}, fh)
    return path


class RunShellTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_stdout_and_stderr_arrive_interleaved(self):
        """Merged, because split streams have to be guessed back together.

        The order they were written in is the only thing that says which
        output a traceback interrupted.
        """
        r = tools.run_shell("echo first; echo second >&2; echo third",
                            cwd=self.dir)
        self.assertTrue(r.ok)
        self.assertEqual(["first", "second", "third"], r.output.split())

    def test_exit_code_is_reported_and_named_in_the_text(self):
        r = tools.run_shell("echo nope; exit 3", cwd=self.dir)
        self.assertFalse(r.ok)
        self.assertEqual(3, r.exit_code)
        self.assertIn("exit code 3", r.as_text())

    def test_command_runs_in_the_directory_it_was_given(self):
        open(os.path.join(self.dir, "marker.txt"), "w").close()
        r = tools.run_shell("ls", cwd=self.dir)
        self.assertIn("marker.txt", r.output)

    def test_a_binary_that_does_not_exist_is_a_result_not_an_exception(self):
        """A failing tool call must reach the model as an answer.

        Raising here would end the turn instead of letting the model try
        something else, which is the one thing a bad command must not do.
        """
        r = tools._run(["/nonexistent/binary"], cwd=self.dir, timeout=5,
                       cap=tools.DEFAULT_CAP, env=None)
        self.assertFalse(r.ok)
        self.assertIn("could not start", r.output)

    def test_empty_output_still_says_something(self):
        r = tools.run_shell("true", cwd=self.dir)
        self.assertEqual("[no output]", r.as_text())


class OutputCapTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_output_is_cut_at_the_cap_and_the_rest_is_counted(self):
        r = tools.run_shell("yes abcdefgh | head -c 200000", cwd=self.dir,
                            cap=1000)
        self.assertEqual(1000, r.kept)
        self.assertEqual(200000, r.kept + r.dropped)
        self.assertIn("truncated", r.as_text())
        self.assertIn("200000", r.as_text())

    def test_the_cap_counts_bytes_and_says_so(self):
        """The unit has to be the one the budget is charged in.

        A context window is charged by encoded size, so a page of non-ASCII
        must count as the bytes it is. Reporting the cut in characters while
        enforcing it in bytes makes the two numbers disagree by the encoding,
        which nothing downstream can correct for.
        """
        r = tools.run_shell(
            f"{sys.executable} -c \"print('\\u01a1' * 20000)\"",
            cwd=self.dir, cap=1000)
        self.assertEqual(1000, r.kept)
        self.assertLess(len(r.output), r.kept)
        self.assertIn("bytes", r.as_text())

    def test_too_much_output_is_not_reported_as_a_timeout(self):
        """The cap must not be enforced by letting the command hang.

        Stopping the read at the cap would block the writer on a full pipe
        until the timeout, so a query that printed too much would be reported
        as one that never finished -- a different defect with a different fix.
        """
        started = time.monotonic()
        r = tools.run_shell("yes abcdefgh | head -c 2000000", cwd=self.dir,
                            cap=500, timeout=30)
        self.assertFalse(r.timed_out)
        self.assertTrue(r.ok)
        self.assertLess(time.monotonic() - started, 20)

    def test_output_under_the_cap_carries_no_note(self):
        r = tools.run_shell("echo small", cwd=self.dir, cap=1000)
        self.assertEqual(0, r.dropped)
        self.assertNotIn("truncated", r.as_text())


class TimeoutTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_command_that_will_not_stop_is_stopped(self):
        started = time.monotonic()
        r = tools.run_shell("sleep 3", cwd=self.dir, timeout=0.5)
        self.assertTrue(r.timed_out)
        self.assertFalse(r.ok)
        self.assertIn("timed out", r.as_text())
        self.assertLess(time.monotonic() - started, 20)

    @unittest.skipIf(os.name != "posix", "process groups are POSIX")
    def test_the_timeout_kills_what_the_command_started_too(self):
        """The claim the process group exists for, tested where it can fail.

        Killing only the pid `Popen` returns leaves a backgrounded grandchild
        running -- and holding the pipe. Here the grandchild writes a file
        after the timeout has passed, so the file existing is proof it
        survived.
        """
        marker = os.path.join(self.dir, "survived.txt")
        child = (f"{sys.executable} -c "
                 f"\"import time; time.sleep(1.0); "
                 f"open({marker!r}, 'w').write('x')\"")
        r = tools.run_shell(f"{child} & sleep 3", cwd=self.dir, timeout=0.5)
        self.assertTrue(r.timed_out)
        time.sleep(2.0)
        self.assertFalse(
            os.path.exists(marker),
            "a process the command started outlived the timeout")

    @unittest.skipIf(os.name != "posix", "process groups are POSIX")
    def test_killing_a_child_in_our_own_group_does_not_kill_us(self):
        """The guard against the timeout taking the whole session down.

        `os.getpgid(child)` answers "the group the child is in", which is
        *ours* whenever the child was started without a session of its own.
        Signalling it then kills the server, the caller and the terminal.

        The check runs inside a helper that `run_python` has already put in a
        session of its own, so a regression kills the helper and fails this
        test rather than killing the process running the suite.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        helper = (
            "import subprocess, sys\n"
            f"sys.path.insert(0, {root!r})\n"
            "from chromiumdiff.agent import tools\n"
            # No new session, so this child shares the helper's group.
            "child = subprocess.Popen(['sleep', '5'])\n"
            "tools._kill_tree(child)\n"
            "print('caller survived', child.wait())\n")
        r = tools.run_python(helper, cwd=self.dir, timeout=20)
        self.assertIn("caller survived", r.output)


class RunPythonTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.report = _report(
            os.path.join(self.dir, "report.json"),
            [{"bucket": "breaking", "change": {"kind": "mojo_field"}},
             {"bucket": "breaking", "change": {"kind": "pref"}},
             {"bucket": "new", "change": {"kind": "idl_member"}}])

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_report_is_already_loaded(self):
        r = tools.run_python("print(len(F), R['to_ref'])", cwd=self.dir,
                             report_path=self.report)
        self.assertTrue(r.ok, r.output)
        self.assertEqual("3 b", r.output.strip())

    def test_counter_is_bound_without_an_import(self):
        """The aggregation every second question needs, one line in.

        A query that has to import before it can count spends a line, and
        sometimes a whole failed attempt, on machinery.
        """
        r = tools.run_python(
            "print(sorted(Counter(f['bucket'] for f in F).items()))",
            cwd=self.dir, report_path=self.report)
        self.assertTrue(r.ok, r.output)
        self.assertEqual("[('breaking', 2), ('new', 1)]", r.output.strip())

    def test_a_query_can_still_import_what_it_wants(self):
        r = tools.run_python("import re\nprint(bool(re.match('a', 'abc')))",
                             cwd=self.dir, report_path=self.report)
        self.assertTrue(r.ok, r.output)
        self.assertEqual("True", r.output.strip())

    def test_without_a_report_the_names_are_empty_rather_than_missing(self):
        """`R is None` is answerable; `NameError` is a failed turn."""
        r = tools.run_python("print(R, F)", cwd=self.dir)
        self.assertTrue(r.ok, r.output)
        self.assertEqual("None []", r.output.strip())

    def test_a_traceback_points_at_the_line_the_query_wrote(self):
        """The reason the query is compiled under its own name.

        Preloading by prepending lines would report this failure several lines
        below where it is, and a model shown the wrong line fixes the wrong
        thing.
        """
        r = tools.run_python("x = 1\ny = 2\nraise ValueError('boom')",
                             cwd=self.dir, report_path=self.report)
        self.assertFalse(r.ok)
        self.assertIn('File "<query>", line 3', r.output)
        self.assertIn("ValueError: boom", r.output)

    def test_the_traceback_does_not_show_the_machinery(self):
        """A frame the model cannot edit is a frame it should not be shown."""
        r = tools.run_python("raise ValueError('boom')", cwd=self.dir,
                             report_path=self.report)
        self.assertNotIn("driver.py", r.output)
        self.assertNotIn("exec(compile", r.output)

    def test_a_syntax_error_is_reported_against_the_query(self):
        r = tools.run_python("print(", cwd=self.dir, report_path=self.report)
        self.assertFalse(r.ok)
        self.assertIn("<query>", r.output)

    def test_the_query_files_are_cleaned_up(self):
        before = set(os.listdir(tempfile.gettempdir()))
        tools.run_python("print(1)", cwd=self.dir)
        left = [n for n in set(os.listdir(tempfile.gettempdir())) - before
                if n.startswith("chromiumdiff-query-")]
        self.assertEqual([], left)

    def test_a_query_is_bounded_by_the_same_cap(self):
        r = tools.run_python("print('x' * 100000)", cwd=self.dir, cap=800)
        self.assertEqual(800, len(r.output))
        self.assertGreater(r.dropped, 0)


class ResultTest(unittest.TestCase):

    def test_as_dict_carries_what_a_caller_needs_to_decide(self):
        r = tools.Result("out", 0, 0, 1.2345, False, kept=3)
        self.assertEqual(
            {"output": "out", "exit_code": 0, "kept": 3, "dropped": 0,
             "seconds": 1.234, "timed_out": False, "ok": True}, r.as_dict())

    def test_a_timeout_is_not_ok_even_with_a_zero_exit_code(self):
        """A killed command can still report 0, and did before this.

        `returncode` after a group kill is whatever the shell last set, so
        success has to mean both things: it finished, and it finished in time.
        """
        self.assertFalse(tools.Result("partial", 0, 0, 30.0, True).ok)


class WhyCommandTest(unittest.TestCase):
    """The route to a row for a caller that cannot click one.

    Every case here is about what the words say, not whether a lookup ran. A
    CL reached from a weak verdict reads exactly like a CL reached from a
    strong one, and the output is the only thing standing between those two.
    """

    CL = {"number": 7685815, "subject": "Preload early hints",
          "at": "2026-05-11 12:02:38.000000000", "date": "2026-05-11",
          "url": "https://chromium-review.googlesource.com/c/chromium/src/"
                 "+/7685815",
          "bugs": [{"id": "493637574"}]}

    def setUp(self):
        from chromiumdiff.enrich import gerrit
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        # `_stale` asks Gerrit where the branch point was before it trusts a
        # stored answer. Stubbed rather than left to fail, so the test says
        # the same thing on a machine with a network as on one without.
        self._saved = gerrit.window_for
        gerrit.window_for = lambda *a, **k: None
        self.addCleanup(self._restore)

    def _restore(self):
        from chromiumdiff.enrich import gerrit
        gerrit.window_for = self._saved

    def _report(self, verdict="introduced", changes=None):
        from chromiumdiff.model import Change, Finding, Report
        gerrit_block = {"candidates": 6, "diffs_read": True,
                        "window": ["2026-04-06", "2026-06-30"],
                        "changes": [dict(self.CL, match=verdict)]
                        if changes is None else changes}
        report = Report(
            from_ref="a", to_ref="b", summary={},
            meta={"platform": "windows"},
            findings=[Finding(
                change=Change(change_type="modified", kind="mojo_field",
                              key="blink.mojom.Params.early_hints",
                              name="early_hints",
                              paths=["navigation_params.mojom"],
                              locations=["navigation_params.mojom:571"],
                              signals=["ipc_shape_changed"], severity=80),
                score=80, bucket="breaking",
                reasons=["severity 80 -- Mojo data shape changed"],
                enrichment={"gerrit": gerrit_block})])
        with open(os.path.join(self.dir, "report.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh)
        return "mojo_field:blink.mojom.Params.early_hints"

    def _run(self, *argv):
        from chromiumdiff.cli import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["why"] + list(argv) + [self.dir, "--no-save"])
        return code, out.getvalue(), err.getvalue()

    def test_a_row_prints_its_cl(self):
        uid = self._report()
        code, out, _ = self._run(uid)
        self.assertEqual(0, code)
        self.assertIn("7685815", out)
        self.assertIn("Preload early hints", out)

    def test_a_verdict_is_printed_with_what_it_claims(self):
        """One word is not enough for a reader who has not memorised seven.

        `touched` and `introduced` are both "a CL was found", and a caller
        that treats them alike reports a coincidence as a cause. The sentence
        travels with the word so that cannot happen quietly.
        """
        from chromiumdiff.model import VERDICT_MEANINGS
        uid = self._report(verdict="touched")
        _, out, _ = self._run(uid)
        self.assertIn(VERDICT_MEANINGS["touched"], out)

    def test_the_glosses_come_from_the_one_definition(self):
        from chromiumdiff.model import VERDICT_MEANINGS
        for verdict in VERDICT_MEANINGS:
            uid = self._report(verdict=verdict)
            _, out, _ = self._run(uid)
            self.assertIn(VERDICT_MEANINGS[verdict], out)

    def test_the_answer_separates_the_cl_from_the_issue(self):
        """The step the caller stops one short of.

        The CL is in hand, it reads like an answer, and it answers a different
        question: what was done, not what was wrong.
        """
        uid = self._report()
        _, out, _ = self._run(uid)
        self.assertIn("the CL says what was done", out)
        self.assertIn("493637574", out)

    def test_an_empty_search_does_not_read_as_no_cause(self):
        """The one sentence this stage must never be heard saying.

        No CL found means the search came back empty. It does not mean the
        change had no cause, and a caller told the first will go looking while
        one told the second stops.
        """
        uid = self._report(changes=[])
        _, out, _ = self._run(uid)
        self.assertIn("not a change with no cause", out)

    def test_an_unknown_uid_names_the_ones_it_could_have_meant(self):
        self._report()
        code, _, err = self._run("early_hints")
        self.assertEqual(1, code)
        self.assertIn("mojo_field:blink.mojom.Params.early_hints", err)

    def test_a_misspelt_uid_falls_back_to_near_spellings(self):
        self._report()
        code, _, err = self._run("mojo_field:blink.mojom.Parms.early_hint")
        self.assertEqual(1, code)
        self.assertIn("mojo_field:blink.mojom.Params.early_hints", err)

    def test_a_uid_resembling_nothing_gets_no_invented_suggestion(self):
        self._report()
        code, _, err = self._run("zzzzzzzzzzzz")
        self.assertEqual(1, code)
        self.assertNotIn("did you mean", err)

    def test_json_carries_the_change_and_the_gerrit_block(self):
        uid = self._report()
        _, out, _ = self._run(uid, "--json")
        doc = json.loads(out)
        self.assertEqual(uid, doc["uid"])
        self.assertEqual("ipc_shape_changed", doc["change"]["signals"][0])
        self.assertEqual(7685815, doc["gerrit"]["changes"][0]["number"])

    def test_a_directory_with_no_report_is_refused(self):
        from chromiumdiff.cli import main
        err = io.StringIO()
        empty = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, empty, True)
        with contextlib.redirect_stderr(err):
            code = main(["why", "anything", empty])
        self.assertEqual(1, code)
        self.assertIn("no report.json", err.getvalue())


class BriefingTest(unittest.TestCase):
    """The note is read before every answer, so it has to be true and small.

    True: every number in it is read out of the report it sits beside, so a
    second report cannot inherit the first one's counts. Small: it is paid for
    on every turn, which is a different economy from a document read once.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _report(self, findings=None, meta=None):
        from chromiumdiff.model import Change, Finding, Report
        if findings is None:
            findings = [Finding(
                change=Change(change_type="modified", kind="mojo_field",
                              key="blink.mojom.Params.early_hints",
                              name="early_hints"),
                score=80, bucket="breaking")]
        return Report(from_ref="M148", to_ref="M151", findings=findings,
                      summary={"total": len(findings)},
                      meta=meta or {"platform": "windows",
                                    "target_set": "default"})

    def test_the_counts_come_from_the_report_it_sits_beside(self):
        from chromiumdiff.agent import briefing
        from chromiumdiff.model import Change, Finding
        many = [Finding(change=Change(change_type="added", kind="pref",
                                      key=f"k{i}", name=f"k{i}"),
                        score=10, bucket="housekeeping") for i in range(7)]
        text = briefing.render(self._report(findings=many), self.dir)
        self.assertIn("7 findings", text)
        self.assertIn("7 Housekeeping", text)
        self.assertNotIn("Breaking", text)

    def test_the_uid_recipe_it_prints_is_the_one_the_code_uses(self):
        """Prose describing a derivation is a second copy of it.

        The note tells the reader to build a uid as `kind:key`, and nothing
        stops `Change.uid` from changing under it. This is the one thing
        holding the sentence to the code.
        """
        from chromiumdiff.agent import briefing
        from chromiumdiff.model import Change
        change = Change(change_type="modified", kind="mojo_field",
                        key="blink.mojom.Params.early_hints", name="x")
        text = briefing.render(self._report(), self.dir)
        self.assertIn("`kind:key`", text)
        self.assertEqual(f"{change.kind}:{change.key}", change.uid)

    def test_it_names_every_bucket_the_model_defines(self):
        from chromiumdiff.agent import briefing
        from chromiumdiff.model import BUCKET_ORDER
        text = briefing.render(self._report(), self.dir)
        for bucket in BUCKET_ORDER:
            self.assertIn(bucket, text)

    def test_it_warns_against_the_thing_that_costs_a_session(self):
        from chromiumdiff.agent import briefing
        text = briefing.render(self._report(), self.dir)
        self.assertIn("one line", text)
        self.assertIn("grep", text)

    def test_it_says_when_the_scan_was_incomplete(self):
        from chromiumdiff.agent import briefing
        meta = {"platform": "windows", "target_set": "default",
                "complete": False}
        self.assertIn("not complete",
                      briefing.render(self._report(meta=meta), self.dir))
        meta["complete"] = True
        self.assertNotIn("not complete",
                         briefing.render(self._report(meta=meta), self.dir))

    def test_coverage_is_quoted_from_the_side_being_moved_to(self):
        from chromiumdiff.agent import briefing
        meta = {"platform": "windows", "target_set": "wide",
                "coverage": {"from": {"read": 1, "candidates": 100},
                             "to": {"read": 90, "candidates": 100}}}
        text = briefing.render(self._report(meta=meta), self.dir)
        self.assertIn("Read 90 of 100", text)
        self.assertNotIn("Read 1 of 100", text)

    def test_it_stays_cheap_enough_to_read_every_turn(self):
        """A budget, not a style rule.

        This is prepended to every question asked about the report. Doubling
        it is not a formatting change, it is a per-turn cost, and the point of
        the note is to save turns rather than to spend them.
        """
        from chromiumdiff.agent import briefing
        text = briefing.render(self._report(), self.dir)
        self.assertLess(len(text), 8000, "the briefing has grown expensive")

    def test_write_puts_it_where_an_agent_will_look(self):
        from chromiumdiff.agent import briefing
        path = briefing.write(self._report(), self.dir)
        self.assertEqual(os.path.join(self.dir, "AGENTS.md"), path)
        with open(path, encoding="utf-8") as fh:
            self.assertIn("M148 to M151", fh.read())

    def test_a_missing_report_json_does_not_stop_the_note(self):
        """The size line is a convenience; the warning it carries is not."""
        from chromiumdiff.agent import briefing
        text = briefing.render(self._report(), self.dir)
        self.assertIn("do not grep it", text)


class ChatServerTest(unittest.TestCase):
    """The whole path, over a real socket, with the endpoint replaced.

    A question is posted, a turn runs, a query really executes against a real
    `report.json`, and the events come back by polling. Everything between the
    page and the model is under test; only the model is not.
    """

    REPLIES = ["<run-python>\nprint(len(F))\n</run-python>",
               "There is one finding."]

    def setUp(self):
        import threading
        from http.server import ThreadingHTTPServer
        from chromiumdiff import serve as serve_mod
        from chromiumdiff.agent import chat as chat_mod
        from chromiumdiff.agent import engine as engine_mod

        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        _report(os.path.join(self.dir, "report.json"),
                [{"change": {"change_type": "modified", "kind": "mojo_field",
                             "key": "k", "name": "k"},
                  "score": 80, "bucket": "breaking", "reasons": []}])
        self.chat = chat_mod.Chat(
            self.dir, engine_mod.ScriptedEngine(list(self.REPLIES)))
        state = serve_mod._State(self.dir, tempfile.mkdtemp(), budget=1,
                                 save=False, chat=self.chat)
        self.token = state.token
        handler = type("_B", (serve_mod._Handler,), {"state": state})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def _request(self, path, data=None, token=True, origin=None):
        import urllib.error
        import urllib.request
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Chromiumdiff-Token"] = self.token
        if origin:
            headers["Origin"] = origin
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(self.base + path, data=body,
                                         headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Closed rather than left to the collector: an HTTPError holds the
            # socket, and a suite that leaks one per refusal prints a
            # ResourceWarning from somewhere unrelated to the test that leaked.
            with exc:
                try:
                    return exc.code, json.loads(exc.read().decode("utf-8"))
                except ValueError:
                    return exc.code, {}

    def _ask(self, question="how many findings?"):
        status, doc = self._request("/api/chat", {"message": question})
        self.assertEqual(200, status, doc)
        events, since = [], 0
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            _, block = self._request(
                f"/api/chat/events?turn={doc['turn']}&since={since}")
            events.extend(block["events"])
            since = block["next"]
            if not block["running"]:
                break
        return doc, events

    def test_ping_says_a_chat_is_here_and_hands_over_the_token(self):
        status, doc = self._request("/api/ping", token=False)
        self.assertEqual(200, status)
        self.assertTrue(doc["chat"])
        self.assertEqual(self.token, doc["token"])

    def test_a_question_runs_a_query_and_comes_back_with_an_answer(self):
        _, events = self._ask()
        kinds = [e["type"] for e in events]
        self.assertIn("tool", kinds)
        self.assertIn("tool_result", kinds)
        self.assertEqual("done", kinds[-1])
        result = [e for e in events if e["type"] == "tool_result"][0]
        # The query really ran against the real file: one finding is in it.
        self.assertEqual("1", result["output"].strip())
        answer = " ".join(e["text"] for e in events if e["type"] == "text")
        self.assertIn("one finding", answer.lower())

    def test_the_conversation_is_kept_and_can_be_read_back(self):
        doc, _ = self._ask()
        _, history = self._request(
            f"/api/chat/history?session={doc['session']}")
        roles = [m["role"] for m in history["messages"]]
        self.assertEqual(["user", "assistant"], roles)

    def test_a_second_question_carries_the_first_one_with_it(self):
        """A conversation the engine is not told about is a list of firsts."""
        self.chat.engine.replies = ["Two.", "Three."]
        doc, _ = self._ask("first question")
        status, _ = self._request("/api/chat",
                                  {"session": doc["session"],
                                   "message": "second question"})
        self.assertEqual(200, status)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and len(self.chat.engine.seen) < 2:
            time.sleep(0.05)
        sent = self.chat.engine.seen[-1]
        asked = [m["content"] for m in sent if m["role"] == "user"]
        self.assertIn("first question", asked)
        self.assertIn("second question", asked)

    def test_a_post_without_the_token_is_refused(self):
        """Any page open in this browser can post here. Only ours can read.

        The token comes from `/api/ping`, which is same-origin readable and
        nothing else, so holding it is the proof that matters.
        """
        status, _ = self._request("/api/chat", {"message": "hi"}, token=False)
        self.assertEqual(403, status)

    def test_a_post_from_another_origin_is_refused(self):
        status, _ = self._request("/api/chat", {"message": "hi"},
                                  origin="http://evil.example")
        self.assertEqual(403, status)

    def test_an_unknown_turn_is_not_found(self):
        status, _ = self._request("/api/chat/events?turn=nope&since=0")
        self.assertEqual(404, status)

    def test_a_body_that_is_not_a_question_is_refused(self):
        status, _ = self._request("/api/chat", {"message": "   "})
        self.assertEqual(400, status)


class ChatOffTest(unittest.TestCase):
    """Without --chat the routes are not merely idle, they are absent."""

    def setUp(self):
        import threading
        from http.server import ThreadingHTTPServer
        from chromiumdiff import serve as serve_mod

        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        _report(os.path.join(self.dir, "report.json"), [])
        state = serve_mod._State(self.dir, tempfile.mkdtemp(), budget=1,
                                 save=False)
        handler = type("_B", (serve_mod._Handler,), {"state": state})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def test_ping_says_there_is_no_chat(self):
        import urllib.request
        with urllib.request.urlopen(self.base + "/api/ping",
                                    timeout=10) as resp:
            self.assertFalse(json.loads(resp.read().decode("utf-8"))["chat"])

    def test_posting_a_question_is_not_found(self):
        import urllib.error
        import urllib.request
        request = urllib.request.Request(
            self.base + "/api/chat", data=b"{}",
            headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        with caught.exception as exc:
            self.assertEqual(404, exc.code)


class TurnBookkeepingTest(unittest.TestCase):
    """One turn at a time per conversation, and a bounded number kept.

    Both were described where they are implemented and neither was checked.
    The first is a correctness rule -- a second question asked mid-answer
    reaches the engine with a history missing the first answer, so it is
    answered as though nothing had been asked, and the two answers land in
    whichever order they finish.
    """

    def setUp(self):
        from chromiumdiff.agent import chat as chat_mod
        from chromiumdiff.agent import engine as engine_mod
        self.chat_mod, self.engine_mod = chat_mod, engine_mod
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        _report(os.path.join(self.dir, "report.json"), [])

    def _chat(self, engine=None):
        return self.chat_mod.Chat(
            self.dir, engine or self.engine_mod.ScriptedEngine(["done."]))

    def _settle(self, chat, turn):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            block = chat.events(turn, 0)
            if block and not block["running"]:
                return block
            time.sleep(0.02)
        self.fail("the turn never finished")

    def test_an_empty_question_is_refused_before_anything_starts(self):
        answer = self._chat().ask(None, "   ")
        self.assertIn("error", answer)
        self.assertNotIn("turn", answer)

    def test_a_second_question_mid_answer_is_refused_not_queued(self):
        engine_mod = self.engine_mod

        class _Slow(engine_mod.Engine):
            def _run(self, session, question, workspace, emit):
                time.sleep(1.0)
                emit(engine_mod.text("late answer"))
                session.add("assistant", "late answer")

        chat = self._chat(_Slow())
        first = chat.ask(None, "first")
        second = chat.ask(first["session"], "second")
        self.assertIn("error", second)
        self.assertEqual(first["turn"], second["turn"])
        self._settle(chat, first["turn"])

    def test_a_finished_conversation_accepts_the_next_question(self):
        chat = self._chat(self.engine_mod.ScriptedEngine(["one.", "two."]))
        first = chat.ask(None, "first")
        self._settle(chat, first["turn"])
        second = chat.ask(first["session"], "second")
        self.assertNotIn("error", second)
        self.assertNotEqual(first["turn"], second["turn"])

    def test_two_conversations_do_not_block_each_other(self):
        chat = self._chat(self.engine_mod.ScriptedEngine(["a.", "b."]))
        one = chat.ask(None, "first")
        two = chat.ask(None, "second")
        self.assertNotIn("error", two)
        self.assertNotEqual(one["session"], two["session"])

    def test_old_turns_are_forgotten_and_the_conversation_is_not(self):
        """Turns are the live view; what was said is on disk.

        Forgetting a turn bounds memory over a long session. Forgetting the
        conversation would lose the answers.
        """
        chat = self._chat()
        keep = self.chat_mod.KEEP_TURNS
        first = chat.ask(None, "first")
        self._settle(chat, first["turn"])
        for i in range(keep + 3):
            later = chat.ask(None, f"q{i}")
            self._settle(chat, later["turn"])
        self.assertLessEqual(len(chat.turns), keep)
        self.assertIsNone(chat.events(first["turn"], 0))
        history = chat.history(first["session"])
        self.assertIsNotNone(history)
        self.assertEqual("first", history["messages"][0]["content"])

    def test_events_can_be_read_from_where_the_last_poll_stopped(self):
        chat = self._chat()
        started = chat.ask(None, "hello")
        whole = self._settle(chat, started["turn"])
        tail = chat.events(started["turn"], whole["next"] - 1)
        self.assertEqual(1, len(tail["events"]))
        self.assertEqual(whole["events"][-1], tail["events"][0])

    def test_a_poll_beyond_the_end_returns_nothing_rather_than_failing(self):
        chat = self._chat()
        started = chat.ask(None, "hello")
        self._settle(chat, started["turn"])
        self.assertEqual([], chat.events(started["turn"], 9999)["events"])

    def test_the_page_is_not_shown_the_tool_chatter(self):
        """`history` is what a reader reloads into the panel.

        The engine needs the tool turns; a person reading back what they asked
        does not, and they are the bulk of a long conversation.
        """
        chat = self._chat(self.engine_mod.ScriptedEngine(
            ["<run-python>\nprint(1)\n</run-python>", "one."]))
        started = chat.ask(None, "how many?")
        self._settle(chat, started["turn"])
        roles = [m["role"] for m in chat.history(started["session"])["messages"]]
        self.assertEqual(["user", "assistant"], roles)
        session = chat.sessions.get(started["session"])
        self.assertIn("tool", [m["role"] for m in session.messages])

    def test_an_unknown_conversation_is_absent(self):
        self.assertIsNone(self._chat().history("nope"))


class SessionHistoryTest(unittest.TestCase):
    """What a later turn is told about an earlier one.

    The history is kept here rather than in the engine, so these rules are
    the whole of the conversation's memory. Every one of them was described
    in a docstring and none was checked.
    """

    def setUp(self):
        from chromiumdiff.agent import session as session_mod
        self.mod = session_mod
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_the_oldest_turns_are_dropped_first(self):
        s = self.mod.Session()
        for i in range(12):
            s.add("user", f"question {i}")
            s.add("assistant", f"answer {i} " + "x" * 3000)
        sent = s.for_engine()
        content = [m["content"] for m in sent]
        self.assertLess(len(sent), len(s.messages))
        self.assertLessEqual(
            sum(len(m["content"]) for m in sent), self.mod.HISTORY_BUDGET
            + max(len(m["content"]) for m in s.messages)
            + self.mod.OPENING_MAX)
        self.assertEqual(s.messages[-1], sent[-1], "the newest turn must go")
        # "question 0" is the opening and is kept on purpose; what has to be
        # gone is the middle, which is what the budget is spent on.
        self.assertNotIn("question 1", content)
        self.assertIn("question 0", content)

    def test_the_opening_question_survives_the_trimming(self):
        """What the conversation is about, when the tail no longer says.

        "Which of those need retesting?" refers to something, and after eight
        turns the something has been dropped. One message, and it cannot
        invent anything -- which is the difference between it and a summary.
        """
        s = self.mod.Session()
        s.add("user", "what changed in settings?")
        for i in range(12):
            s.add("assistant", f"answer {i} " + "x" * 3000)
            s.add("user", f"follow-up {i}")
        sent = s.for_engine()
        self.assertEqual("what changed in settings?", sent[0]["content"])
        self.assertNotIn("answer 0", [m["content"][:8] for m in sent])

    def test_a_pasted_log_is_not_carried_on_every_later_turn(self):
        """An anchor worth one message, not worth the budget."""
        s = self.mod.Session()
        s.add("user", "here is the log:\n" + "L" * (self.mod.OPENING_MAX * 2))
        for i in range(12):
            s.add("assistant", f"answer {i} " + "x" * 3000)
            s.add("user", f"follow-up {i}")
        sent = s.for_engine()
        self.assertNotIn("here is the log", sent[0]["content"])

    def test_the_opening_is_not_sent_twice_while_it_is_still_in_the_tail(self):
        s = self.mod.Session()
        s.add("user", "first question")
        s.add("assistant", "short answer")
        sent = s.for_engine()
        self.assertEqual(1, [m["content"] for m in sent]
                         .count("first question"))

    def test_a_question_larger_than_the_budget_is_still_sent_whole(self):
        """Trimming the newest turn sends a question with its point removed."""
        s = self.mod.Session()
        s.add("user", "y" * (self.mod.HISTORY_BUDGET * 3))
        sent = s.for_engine()
        self.assertEqual(1, len(sent))
        self.assertEqual(self.mod.HISTORY_BUDGET * 3, len(sent[0]["content"]))

    def test_a_tool_result_does_not_cost_the_rest_of_the_conversation(self):
        """The answer written from a result carries forward; the result does
        not. Otherwise one large query is a permanent tax on every later turn.
        """
        s = self.mod.Session()
        s.add_tool_result("python", "z" * 50000)
        carried = s.messages[-1]["content"]
        self.assertLess(len(carried), self.mod.RESULT_KEEP + 200)
        self.assertIn("not kept in the history", carried)

    def test_a_short_tool_result_is_kept_whole(self):
        s = self.mod.Session()
        s.add_tool_result("python", "42")
        self.assertIn("42", s.messages[-1]["content"])
        self.assertNotIn("not kept", s.messages[-1]["content"])

    def test_a_conversation_survives_a_restart(self):
        store = self.mod.SessionStore(self.dir)
        s = store.new()
        s.add("user", "what changed")
        store.save(s)
        again = self.mod.SessionStore(self.dir)
        self.assertEqual("what changed",
                         again.get(s.id).messages[0]["content"])

    def test_a_session_id_cannot_name_a_file_outside_the_store(self):
        """The id arrives from a URL and would otherwise be joined to a path.

        Checked against the ids that exist rather than sanitised, so there is
        no escaping-rule to get wrong.

        The decoy is a *readable session file* one directory up. Pointing the
        hostile ids at `/etc/passwd` proved nothing: that returns None however
        the store is written, because it is not a session, so the test passed
        with the guard deleted.
        """
        store = self.mod.SessionStore(self.dir)
        store.save(store.new())                      # so `chats/` exists
        decoy = os.path.join(self.dir, "secret.json")
        with open(decoy, "w", encoding="utf-8") as fh:
            json.dump({"id": "secret", "messages":
                       [{"role": "user", "content": "not yours"}]}, fh)
        self.assertIsNone(store.get("../secret"),
                          "a session id reached a file outside the store")
        for hostile in ("../../etc/passwd", "..", "/etc/passwd", "a/../../b"):
            self.assertIsNone(store.get(hostile), hostile)

    def test_an_unknown_session_is_absent_rather_than_invented(self):
        self.assertIsNone(self.mod.SessionStore(self.dir).get("nope"))

    def test_ids_are_not_guessable_from_each_other(self):
        made = {self.mod.new_id() for _ in range(200)}
        self.assertEqual(200, len(made))
        self.assertTrue(all(len(i) >= 12 for i in made))


class TurnLimitsTest(unittest.TestCase):
    """The two ceilings on one question, both claimed and neither checked."""

    def setUp(self):
        from chromiumdiff.agent import engine as engine_mod
        self.mod = engine_mod
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        _report(os.path.join(self.dir, "report.json"), [])
        self.ws = engine_mod.Workspace(self.dir)

    def _forever(self):
        """An engine that never stops asking for another lookup."""
        mod = self.mod

        class _Loop(mod.TextProtocolEngine):
            calls = 0

            def complete(self, messages):
                _Loop.calls += 1
                return "<run-python>\nprint(1)\n</run-python>"

        return _Loop()

    def test_a_loop_that_will_not_converge_is_stopped(self):
        from chromiumdiff.agent.session import Session
        session = Session()
        session.add("user", "go")
        events = []
        self._forever().run(session, "go", self.ws, events.append)
        ran = len([e for e in events if e["type"] == "tool"])
        self.assertLessEqual(ran, self.mod.MAX_STEPS)
        self.assertTrue([e for e in events if e["type"] == "error"])
        self.assertEqual("done", events[-1]["type"])

    def test_the_reader_is_told_why_it_stopped(self):
        from chromiumdiff.agent.session import Session
        session = Session()
        session.add("user", "go")
        events = []
        self._forever().run(session, "go", self.ws, events.append)
        said = " ".join(e.get("message", "") for e in events
                        if e["type"] == "error")
        self.assertIn(str(self.mod.MAX_STEPS), said)

    def test_a_turn_that_runs_too_long_gives_up(self):
        from chromiumdiff.agent.session import Session
        mod = self.mod
        original = mod.TURN_SECONDS
        mod.TURN_SECONDS = -1.0          # every turn is already over time
        self.addCleanup(setattr, mod, "TURN_SECONDS", original)
        session = Session()
        session.add("user", "go")
        events = []
        self._forever().run(session, "go", self.ws, events.append)
        self.assertEqual([], [e for e in events if e["type"] == "tool"])
        self.assertTrue([e for e in events if e["type"] == "error"])


class WorkspaceTest(unittest.TestCase):
    """What the engine is told about the report, and what it may reach."""

    def setUp(self):
        from chromiumdiff.agent import engine as engine_mod
        self.mod = engine_mod
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        _report(os.path.join(self.dir, "report.json"), [])

    def test_the_note_on_disk_is_the_note_that_is_used(self):
        """An edited AGENTS.md is somebody's correction. It wins."""
        with open(os.path.join(self.dir, "AGENTS.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("# hand-written")
        self.assertIn("hand-written",
                      self.mod.Workspace(self.dir).briefing_text())

    def test_a_report_written_before_the_note_existed_still_gets_one(self):
        text = self.mod.Workspace(self.dir).briefing_text()
        self.assertIn("do not grep it", text)

    def test_a_directory_with_nothing_in_it_does_not_raise(self):
        empty = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertEqual("", self.mod.Workspace(empty).briefing_text())

    def test_the_prompt_carries_the_report_and_the_protocol(self):
        prompt = self.mod.Workspace(self.dir).system_prompt()
        self.assertIn("<run-python>", prompt)
        self.assertIn("do not grep it", prompt)
        self.assertIn(str(self.mod.MAX_STEPS), prompt)

    def test_without_shell_the_prompt_does_not_offer_it(self):
        """A tool named in the prompt and refused at the door wastes a turn."""
        prompt = self.mod.Workspace(
            self.dir, allow_shell=False).system_prompt()
        self.assertNotIn("<run-shell>", prompt)
        self.assertIn("<run-python>", prompt)

    def test_shell_is_refused_with_a_reason_when_it_is_off(self):
        result = self.mod.Workspace(self.dir, allow_shell=False).run(
            "shell", "echo hello")
        self.assertFalse(result.ok)
        self.assertIn("python", result.output)
        self.assertNotIn("hello", result.output)

    def test_a_tool_that_does_not_exist_is_an_answer(self):
        result = self.mod.Workspace(self.dir).run("telepathy", "x")
        self.assertFalse(result.ok)
        self.assertIn("telepathy", result.output)


class HttpEngineFailureTest(unittest.TestCase):
    """What the reader is told when the endpoint is the thing that is wrong.

    Three failures that look identical from a spinner and need different
    fixes: it refused, it was unreachable, it answered something else.
    """

    def setUp(self):
        from chromiumdiff.agent import engine as engine_mod
        self.mod = engine_mod

    def _engine(self, handler):
        import threading
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

        outer = handler

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                outer(self)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        return self.mod.HttpEngine(base_url=f"http://127.0.0.1:{port}/v1",
                                   model="m", timeout=10)

    def _say(self, engine):
        from chromiumdiff.agent.session import Session
        directory = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, directory, True)
        _report(os.path.join(directory, "report.json"), [])
        session = Session()
        session.add("user", "hello")
        events = []
        engine.run(session, "hello", self.mod.Workspace(directory),
                   events.append)
        return " ".join(e.get("message", "") for e in events
                        if e["type"] == "error"), events

    def test_a_refusal_carries_what_the_endpoint_said(self):
        """`400` alone sends the reader to the wrong question."""
        def refuse(h):
            body = b'{"error":{"message":"model not enabled for this key"}}'
            h.send_response(400)
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body)

        said, events = self._say(self._engine(refuse))
        self.assertIn("400", said)
        self.assertIn("model not enabled", said)
        self.assertEqual("done", events[-1]["type"])

    def test_an_answer_in_an_unknown_shape_says_what_arrived(self):
        def odd(h):
            body = b'{"output":"hello"}'
            h.send_response(200)
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body)

        said, _ = self._say(self._engine(odd))
        self.assertIn("shape", said)
        self.assertIn("output", said)

    def test_an_endpoint_that_is_not_there_is_named_as_such(self):
        engine = self.mod.HttpEngine(base_url="http://127.0.0.1:1/v1",
                                     model="m", timeout=5)
        said, events = self._say(engine)
        self.assertIn("could not reach", said)
        self.assertEqual("done", events[-1]["type"])

    def test_an_unconfigured_engine_says_which_variable_to_set(self):
        engine = self.mod.HttpEngine(base_url="")
        self.assertIn("CHROMIUMDIFF_MODEL_URL", engine.available())

    def test_a_refusal_does_not_leak_the_connection_it_read(self):
        """This runs inside a server that stays up.

        The error body is worth reading and the object holding it owns a
        socket. Left to the collector, a session against a misconfigured
        endpoint leaks one connection per refusal -- and a refusal is exactly
        what a reader retries.
        """
        import warnings

        def refuse(h):
            h.send_response(400)
            h.send_header("Content-Length", "2")
            h.end_headers()
            h.wfile.write(b"{}")

        engine = self._engine(refuse)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            for _ in range(3):
                self._say(engine)
            import gc
            gc.collect()
        leaked = [w for w in caught
                  if issubclass(w.category, ResourceWarning)
                  and "HTTPError" in str(w.message)]
        self.assertEqual([], leaked, "an unclosed response per refusal")

    def test_the_cline_engine_says_it_is_not_wired_up(self):
        engine = self.mod.ClineEngine()
        self.assertIn("not wired up", engine.available())
        said, events = self._say(engine)
        self.assertIn("not wired up", said)
        self.assertEqual("done", events[-1]["type"])


class ToolsReachTheCliTest(unittest.TestCase):
    """The command the briefing tells a reader to run has to actually run.

    Everything a question needs is a query over the report except one thing:
    the CL behind a row, which only `why` can fetch. The briefing names
    `python3 -m chromiumdiff why <uid>` and every command runs with the report
    directory as its working directory -- where the package is not importable,
    so the one documented command failed with `No module named chromiumdiff`
    and the one thing a query cannot do for itself was unreachable.
    """

    def setUp(self):
        from chromiumdiff.agent.engine import Workspace
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        _report(os.path.join(self.dir, "report.json"),
                [{"change": {"change_type": "modified", "kind": "mojo_field",
                             "key": "k", "name": "k"},
                  "score": 80, "bucket": "breaking", "reasons": []}])
        self.ws = Workspace(self.dir)

    def test_the_package_is_importable_from_the_report_directory(self):
        r = self.ws.run("shell",
                        f"{sys.executable} -c "
                        f"'import chromiumdiff; print(chromiumdiff.__name__)'")
        self.assertTrue(r.ok, r.as_text())
        self.assertEqual("chromiumdiff", r.output.strip())

    def test_the_command_the_briefing_names_is_the_command_that_works(self):
        """Read out of the briefing rather than retyped here.

        A test that spells the command itself passes while the document sends
        the reader somewhere else, which is the failure this is for.
        """
        from chromiumdiff.agent import briefing
        text = briefing.render(
            __import__("chromiumdiff.model", fromlist=["Report"]).Report(
                from_ref="a", to_ref="b", findings=[], summary={},
                meta={"platform": "windows"}), self.dir)
        named = [line.strip() for line in text.splitlines()
                 if line.strip().startswith("python3 -m chromiumdiff why")]
        self.assertTrue(named, "the briefing stopped naming `why`")
        command = named[0].split("#")[0].replace("<uid>", "mojo_field:k")
        r = self.ws.run("shell", command)
        self.assertNotIn("No module named", r.output)
        self.assertIn("mojo_field:k", r.output)

    def test_a_query_can_import_the_package_too(self):
        r = self.ws.run("python", "import chromiumdiff.model as m\n"
                                  "print(sorted(m.VERDICT_MEANINGS)[0])")
        self.assertTrue(r.ok, r.as_text())
        self.assertEqual("crowded", r.output.strip())

    def test_an_existing_python_path_is_kept(self):
        """A caller's own path still applies, after ours."""
        from chromiumdiff.agent import tools as t
        env = t.child_env({"PYTHONPATH": "/somewhere/else"})
        self.assertTrue(env["PYTHONPATH"].endswith("/somewhere/else"))
        self.assertIn(os.pathsep, env["PYTHONPATH"])

    def test_the_root_it_adds_actually_holds_the_package(self):
        from chromiumdiff.agent import tools as t
        root = t.child_env({})["PYTHONPATH"]
        # A directory in a checkout, or the .pyz itself when packaged. Both
        # are things `-m chromiumdiff` can import from.
        self.assertTrue(os.path.isdir(os.path.join(root, "chromiumdiff"))
                        or root.endswith(".pyz"), root)


class AnswerRenderingTest(unittest.TestCase):
    """The page's own renderer, run rather than read.

    It puts text a model wrote into `innerHTML`. Three defects were found by
    looking at a screenshot of it and none by reading it: `**120**` printed
    with its asterisks, a list printed as a column of hyphens, and a uid --
    the longest token an answer contains and the one it cites most -- running
    off the edge of the panel. The first two are here. The third is CSS, and
    is checked by rendering the page and looking for the rule.
    """

    @classmethod
    def setUpClass(cls):
        import shutil as _shutil
        import subprocess
        from chromiumdiff.model import Report
        from chromiumdiff.report import html as html_report

        node = _shutil.which("node")
        if not node:
            raise unittest.SkipTest("node not installed")
        cls.tmp = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        page = os.path.join(cls.tmp, "report.html")
        with open(page, "w", encoding="utf-8") as fh:
            fh.write(html_report.render(
                Report(from_ref="a", to_ref="b", findings=[], summary={},
                       meta={"platform": "windows"})))
        root = os.path.dirname(os.path.abspath(__file__))
        done = subprocess.run(
            [node, os.path.join(root, "js", "ask_prose.js"), page],
            capture_output=True, text=True, timeout=120)
        if done.returncode != 0:
            raise AssertionError(done.stderr[:400])
        cls.out = json.loads(done.stdout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmp", ""), ignore_errors=True)

    def test_bold_is_rendered_not_printed(self):
        self.assertIn("<strong>120</strong>", self.out["bold"])
        self.assertNotIn("**", self.out["bold"])

    def test_a_list_is_a_list(self):
        """The shape most answers about a report take."""
        for key in ("bullets", "starBullets"):
            self.assertIn("<ul>", self.out[key], key)
            self.assertEqual(2, self.out[key].count("<li>"), key)
            self.assertNotIn("<li>- ", self.out[key], key)

    def test_a_paragraph_beside_a_list_stays_a_paragraph(self):
        self.assertIn("<p>Read these:</p>", self.out["bullets"])

    def test_inline_code_survives_a_uid(self):
        self.assertIn("<code>mojo_field:blink.mojom.Params.x</code>",
                      self.out["inlineCode"])

    def test_a_fence_becomes_a_block_without_its_language(self):
        self.assertIn("<pre>print(len(F))", self.out["fenced"])
        self.assertNotIn("python\n", self.out["fenced"])

    def test_blank_lines_separate_and_single_ones_do_not(self):
        self.assertEqual(2, self.out["paragraphs"].count("<p>"))
        self.assertEqual(1, self.out["softBreak"].count("<p>"))
        self.assertIn("<br>", self.out["softBreak"])

    def test_nothing_at_all_still_produces_a_block(self):
        self.assertEqual("<p></p>", self.out["empty"])

    # The tags the renderer is allowed to produce. Anything else beginning a
    # tag came from the answer, which is the failure.
    OURS = re.compile(r"</?(?:p|ul|li|code|strong|pre|br)>")

    def test_markup_in_an_answer_arrives_as_text(self):
        """An answer is text from outside, and it lands in `innerHTML`.

        Nothing before this point is a sanitiser: the model writes what it
        writes, and a report directory can hold anything. The other rendering
        rules are convenience; this one is not.

        Checked by removing the tags the renderer itself emits and requiring
        that no `<` is left. Naming the dangerous strings instead -- `<script`,
        `onerror=` -- checks a list rather than the property, and `onerror=`
        appears in correct output as inert text, which is how this test failed
        while the code was right.
        """
        for key in ("markup", "markupInCode", "markupInFence"):
            leftover = self.OURS.sub("", self.out[key])
            self.assertNotIn("<", leftover, key)
            self.assertNotIn(">", leftover, key)
            self.assertIn("&lt;", self.out[key], key)

    def test_an_ampersand_is_not_doubled(self):
        self.assertIn("flags &amp; switches", self.out["ampersand"])
        self.assertNotIn("&amp;amp;", self.out["ampersand"])

    def test_a_long_identifier_is_allowed_to_wrap(self):
        from chromiumdiff.model import Report
        from chromiumdiff.report import html as html_report
        page = html_report.render(
            Report(from_ref="a", to_ref="b", findings=[], summary={},
                   meta={"platform": "windows"}))
        self.assertIn("overflow-wrap:anywhere", page.replace(" ", ""))


class OutsideWriterTest(unittest.TestCase):
    """`report.json` has two writers now, and the server used to be one of one.

    A chat can run `chromiumdiff why`, which resolves a row in another process
    and saves it. Nothing told the server, so the next thing it saved was its
    own older copy written over the top -- lookups gone, with nothing to say
    they had been there.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "report.json")

    def _write(self, keys):
        _report(self.path, [{"change": {"change_type": "added", "kind": "pref",
                                        "key": k, "name": k},
                             "score": 10, "bucket": "housekeeping",
                             "reasons": []} for k in keys])
        # Two writes inside one filesystem timestamp are one write as far as
        # mtime is concerned, and the test would pass without the reload.
        stamp = os.path.getmtime(self.path) + 10
        os.utime(self.path, (stamp, stamp))

    def _state(self):
        from chromiumdiff import serve as serve_mod
        return serve_mod._State(self.dir, tempfile.mkdtemp(), budget=1,
                                save=False)

    def test_a_row_added_by_another_process_becomes_visible(self):
        self._write(["a"])
        state = self._state()
        self.assertEqual({"pref:a"}, set(state.by_uid))
        self._write(["a", "b"])
        state.page()
        self.assertEqual({"pref:a", "pref:b"}, set(state.by_uid))

    def test_a_lookup_sees_a_row_that_arrived_after_startup(self):
        self._write(["a"])
        state = self._state()
        self._write(["a", "b"])
        # `resolve` returns None for an unknown uid, so reaching the lookup at
        # all is the assertion: without the reload this row does not exist.
        self.assertIsNotNone(state.by_uid.get("pref:a"))
        state.resolve("pref:b")
        self.assertIn("pref:b", state.by_uid)

    def test_a_half_written_file_is_not_taken(self):
        """A writer mid-write must not empty the report being served."""
        self._write(["a"])
        state = self._state()
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write('{"findings": [')
        stamp = os.path.getmtime(self.path) + 10
        os.utime(self.path, (stamp, stamp))
        self.assertFalse(state._reload_if_changed())
        self.assertEqual({"pref:a"}, set(state.by_uid))

    def test_an_untouched_file_is_not_reread(self):
        self._write(["a"])
        state = self._state()
        self.assertFalse(state._reload_if_changed())


class PackageTest(unittest.TestCase):
    """One file, and it has to run somewhere that is not this checkout.

    The whole value of the archive is that it works where the repository is
    not, so it is built and then run from a directory with nothing else in it.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _build(self, skills=None):
        from chromiumdiff.agent import package
        return package.build(os.path.join(self.dir, "chromiumdiff.pyz"),
                             skills=skills)

    def test_the_archive_runs_on_its_own(self):
        import subprocess
        archive = self._build()
        done = subprocess.run([sys.executable, archive, "--version"],
                              cwd=self.dir, capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue(done.stdout.strip())

    def test_it_carries_every_command(self):
        import subprocess
        archive = self._build()
        done = subprocess.run([sys.executable, archive, "--help"],
                              cwd=self.dir, capture_output=True, text=True,
                              timeout=60)
        for command in ("run", "serve", "why", "report", "package"):
            self.assertIn(command, done.stdout)

    def test_no_bytecode_travels_with_it(self):
        """A `.pyc` built here can shadow the source it was built from.

        It is also dead weight in a file whose only job is to be small enough
        to send.
        """
        from chromiumdiff.agent import package
        names = package.contents(self._build())
        self.assertEqual([], [n for n in names if "__pycache__" in n])
        self.assertEqual([], [n for n in names if n.endswith(".pyc")])

    def test_the_skills_go_in_when_they_are_there(self):
        from chromiumdiff.agent import package
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        skills = os.path.join(root, "skills")
        if not os.path.isdir(skills):
            self.skipTest("this checkout has no skills/")
        names = package.contents(self._build(skills=skills))
        self.assertTrue([n for n in names if n.endswith("SKILL.md")])

    def test_it_names_a_python_the_other_machine_will_have(self):
        """A shebang pointing at this home directory runs nowhere else."""
        archive = self._build()
        with open(archive, "rb") as fh:
            first = fh.readline()
        self.assertEqual(b"#!/usr/bin/env python3\n", first)


if __name__ == "__main__":
    unittest.main()
