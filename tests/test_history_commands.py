"""Lookup retries, disclosure and CLI failures against controlled evidence."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chromiumdiff import history_cli
from chromiumdiff.cli import main
from chromiumdiff.model import Change, Finding, Report, read_report, write_json


class TestLookup(unittest.TestCase):
    def setUp(self):
        self.finding = Finding(Change("modified", "base_feature", "Example", "Example", paths=["engine.cc"]))
        self.finding.enrichment = {"gerrit": {"changes": [{"number": 1, "match": "described"}],
                                            "diffs_read": False, "failed_fetches": 2,
                                            "search_incomplete": True}}
        self.report = Report("1.0.0.0", "2.0.0.0", [self.finding])

    def cli(self, *args):
        """Through the shared entrypoint, because that is what a reader runs."""
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = main(["why", *args])
        return code, out.getvalue(), err.getvalue()

    def test_retry_reuses_http_cache_refresh_refetches_and_old_warnings_clear(self):
        def enriched(findings, *args, **kwargs):
            findings[0].enrichment.setdefault("gerrit", {}).update(
                changes=[{"number": 2, "match": "exact"}], diffs_read=True)
            return {"available": True}
        original = copy.deepcopy(self.finding.enrichment)
        for refresh in (False, True):
            self.finding.enrichment = copy.deepcopy(original)
            with patch.object(history_cli.gerrit, "enrich", side_effect=enriched) as lookup:
                state = history_cli.resolve(self.finding, self.report, "cache", 1000, 3,
                                            retry=not refresh, refresh=refresh)
            self.assertEqual(state["status"], "complete")
            self.assertEqual(state["warnings"], [])
            self.assertEqual(lookup.call_args.kwargs["refresh"], refresh)
            self.assertEqual(self.finding.enrichment["gerrit"]["changes"][0]["number"], 2)

    def test_stored_partial_result_stays_partial_without_implicit_network(self):
        with patch.object(history_cli.gerrit, "enrich") as lookup:
            state = history_cli.resolve(self.finding, self.report, "cache", 1000, 3)
        lookup.assert_not_called()
        self.assertEqual(state["status"], "partial")
        self.assertEqual(len(state["warnings"]), 3)

    def test_empty_partial_result_discloses_every_limit_in_text_and_json(self):
        self.finding.enrichment["gerrit"]["changes"] = []
        for field in ("failed_fetches", "search_incomplete", "diffs_read"):
            self.finding.enrichment["gerrit"] = {"changes": [], field: False if field == "diffs_read" else 1}
            state = history_cli.lookup_state(self.finding)
            self.assertEqual(state["status"], "partial")
            text = history_cli.render_lookup(self.finding, state)
            for warning in state["warnings"]:
                self.assertIn(warning, text)
            self.assertNotIn("completed searches", text)

    def test_failed_retry_keeps_saved_evidence_and_json_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "report.json")
            write_json(path, self.report.to_dict())
            with patch.object(history_cli.gerrit, "enrich", side_effect=RuntimeError("offline")):
                code, stdout, _ = self.cli(path, self.finding.uid, "--retry", "--json", "--save")
            result = json.loads(stdout)
            self.assertEqual(code, 3)
            self.assertEqual(result["lookup"]["status"], "unavailable")
            self.assertIn("offline", str(result["lookup"]["warnings"]))
            self.assertEqual(read_report(path).findings[0].enrichment["gerrit"], self.finding.enrichment["gerrit"])

    def test_no_window_is_unavailable_not_an_empty_completed_search(self):
        with patch.object(history_cli.gerrit, "window_for", return_value=None):
            state = history_cli.resolve(self.finding, self.report, "cache", 100, 0, retry=True)
        self.assertEqual(state["status"], "unavailable")
        self.assertIn("no window", str(state["warnings"]))

    def test_save_failure_is_nonzero_and_does_not_replace_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            write_json(str(path), self.report.to_dict())
            before = path.read_bytes()
            with patch.object(history_cli.os, "replace", side_effect=OSError("disk unavailable")):
                code, out, err = self.cli(str(path), self.finding.uid, "--json", "--save")
            self.assertEqual(code, 2)
            self.assertFalse(json.loads(out)["save"]["written"])
            self.assertIn("disk unavailable", err)
            self.assertEqual(path.read_bytes(), before)

    def test_an_unreadable_report_exits_two_without_raising_through_the_cli(self):
        """A subcommand returns its code; it must not call sys.exit itself."""
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.cli(str(Path(tmp) / "report.json"), "anything")
            self.assertEqual(code, 2)
            self.assertIn("chromiumdiff run", err)
            path = Path(tmp) / "report.json"
            path.write_text("{not json")
            code, _, err = self.cli(str(path), "anything")
            self.assertEqual(code, 2)
            self.assertIn("not a readable chromiumdiff report", err)


class TestClPaging(unittest.TestCase):
    def run_page(self, *args):
        with patch.object(history_cli, "detail", return_value={"status": "MERGED"}), \
             patch.object(history_cli, "files_of",
                          return_value={f"engine/{i}.cc": {} for i in reversed(range(7))}), \
             patch.object(history_cli, "diff_of", return_value={"content": [{"b": ["new();"]}]}) as diffs, \
             redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            code = main(["cl", "123", "engine/", *args])
        return code, [c.args[1] for c in diffs.call_args_list], out.getvalue()

    def test_every_match_can_be_read_once_and_truncation_is_visible(self):
        paths = []
        for offset in (0, 3, 6):
            code, current, out = self.run_page("--offset", str(offset))
            self.assertEqual(code, 0)
            paths.extend(current)
            if offset < 6:
                self.assertIn("--offset " + str(offset + 3), out)
                self.assertIn("omitted", out)
        self.assertEqual(paths, [f"engine/{i}.cc" for i in range(7)])
        self.assertEqual(self.run_page("--offset", "7")[0], 2)


if __name__ == "__main__":
    unittest.main()
