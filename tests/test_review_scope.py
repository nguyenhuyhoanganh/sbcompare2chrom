"""Selected scope completion must not imply whole-index completion."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from chromiumdiff import review
from chromiumdiff.cli import main
from chromiumdiff.model import write_json
from tests.test_review import fixture, event


class TestReviewScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report, _, _, self.cache, self.path = fixture(self.tmp.name)
        self.directory = str(Path(self.tmp.name) / "review")
        review.initialize(self.path, self.directory, self.cache)
        self.index, self.ledger = review.load(self.directory)
        self.ids = [self.report.findings[0].uid, "file:engine/work.cc"]
        self.scope = {"description": "Selected entry and implementation changes",
                      "fingerprint": self.index["fingerprint"], "items": self.ids}

    def configured(self):
        return review.record(self.index, self.ledger, {"scope": self.scope})

    def complete(self):
        return review.record(self.index, self.configured(), {
            "events": [event([self.ids[0]])],
            "dispositions": [{"id": self.ids[1], "status": "explained", "reason": "Inspected capacity transition"}]})

    def test_source_only_work_counts_and_outside_pending_remains_visible(self):
        ledger = review.record(self.index, self.configured(), {"events": [event([self.ids[0]])]})
        state = review.check(self.index, ledger)
        self.assertFalse(state["scope"]["accounting_complete"])
        self.assertEqual(state["scope"]["counts"]["pending"], 1)
        state = review.check(self.index, self.complete())
        self.assertTrue(state["scope"]["accounting_complete"])
        self.assertFalse(state["accounting_complete"])
        self.assertEqual(state["scope"]["by_kind"]["source_delta"]["total"], 1)
        self.assertEqual(state["scope"]["outside_scope"], len(self.index["items"]) - 2)

    def test_scope_rejects_empty_unknown_duplicate_stale_and_wrong_type(self):
        for value in ([], ["missing"], [self.ids[0]] * 2, [["bad"]], "all"):
            with self.assertRaises(ValueError):
                review.record(self.index, self.ledger, {"scope": {**self.scope, "items": value}})
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            review.record(self.index, self.ledger, {"scope": {**self.scope, "fingerprint": "old"}})
        self.assertFalse(review.check(self.index, self.ledger)["scope"]["accounting_complete"])

    def test_provisional_events_only_block_scopes_they_touch(self):
        ledger = self.complete()
        uid = self.report.findings[1].uid
        ledger = review.record(self.index, ledger, {"events": [event([uid], status="provisional")]})
        self.assertTrue(review.check(self.index, ledger)["scope"]["accounting_complete"])
        scoped_event = next(e for e in ledger["events"] if self.ids[0] in e["items"])
        scoped_event["status"] = "provisional"
        self.assertFalse(review.check(self.index, ledger)["scope"]["accounting_complete"])

    def test_cli_scope_gate_and_render_preserve_whole_index_status(self):
        write_json(str(Path(self.directory) / "review.json"), self.complete())
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["review", "check", self.directory, "--scope"]), 0)
        self.assertFalse(json.loads(output.getvalue())["accounting_complete"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["review", "check", self.directory]), 1)
            self.assertEqual(main(["review", "render", self.directory, "--require-scope-complete"]), 0)
        path = Path(self.directory) / "review.md"
        self.assertIn("Status: PARTIAL", path.read_text())
        self.assertIn("Scope accounting: COMPLETE", path.read_text())
        before = path.read_bytes()
        write_json(str(Path(self.directory) / "review.json"), self.configured())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["review", "render", self.directory, "--require-scope-complete"]), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_input_changes_prevent_scoped_completion(self):
        write_json(str(Path(self.directory) / "review.json"), self.complete())
        source = Path(self.index["inputs"]["source_roots"]["to"]) / "engine/work.cc"
        source.write_text("changed after review\n")
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["review", "check", self.directory, "--scope"]), 1)
        self.assertFalse(json.loads(output.getvalue())["scope"]["accounting_complete"])
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        _, ledger = review.load(self.directory)
        self.assertIsNone(ledger.get("scope"))
        self.assertEqual(ledger["history"][-1]["scope"], self.scope)

    def test_context_refresh_retains_scope_but_reopens_affected_decisions(self):
        write_json(str(Path(self.directory) / "review.json"), self.complete())
        self.report.findings[0].enrichment = {"gerrit": {"changes": [{"number": 123}]}}
        write_json(self.path, self.report.to_dict())
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        index, ledger = review.load(self.directory)
        self.assertEqual(ledger["scope"]["items"], self.ids)
        self.assertEqual(ledger["scope"]["fingerprint"], index["fingerprint"])
        self.assertFalse(review.check(index, ledger)["scope"]["accounting_complete"])


if __name__ == "__main__":
    unittest.main()
