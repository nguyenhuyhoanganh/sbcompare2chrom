"""Tests for the bounded command and query runner.

The interesting cases are the bounds, not the happy path: what a command that
prints too much costs, what a command that refuses to stop costs, and whether
a failing query is reported at the line the model actually wrote.
"""

import json
import os
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


if __name__ == "__main__":
    unittest.main()
