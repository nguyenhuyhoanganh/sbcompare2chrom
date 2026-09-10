"""Item-selection completion must not imply whole-index completion."""

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


class TestReviewSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report, _, _, self.cache, self.path = fixture(self.tmp.name)
        self.directory = str(Path(self.tmp.name) / "review")
        review.initialize(self.path, self.directory, self.cache)
        self.index, self.ledger = review.load(self.directory)
        self.ids = [self.report.findings[0].uid, "file:engine/work.cc"]
        self.selection = {"description": "Selected entry and implementation changes",
                          "fingerprint": self.index["fingerprint"], "items": self.ids}

    def configured(self):
        return review.record(self.index, self.ledger, {"selection": self.selection})

    def complete(self):
        return review.record(self.index, self.configured(), {
            "events": [event([self.ids[0]])],
            "dispositions": [{"id": self.ids[1], "status": "explained", "reason": "Inspected capacity transition"}]})

    def test_source_only_work_counts_and_outside_pending_remains_visible(self):
        ledger = review.record(self.index, self.configured(), {"events": [event([self.ids[0]])]})
        state = review.check(self.index, ledger)
        self.assertFalse(state["selection"]["accounting_complete"])
        self.assertEqual(state["selection"]["counts"]["pending"], 1)
        state = review.check(self.index, self.complete())
        self.assertTrue(state["selection"]["accounting_complete"])
        self.assertFalse(state["accounting_complete"])
        self.assertEqual(state["selection"]["by_kind"]["source_delta"]["total"], 1)
        self.assertEqual(state["selection"]["outside_selection"], len(self.index["items"]) - 2)

    def test_selection_rejects_empty_unknown_duplicate_stale_and_wrong_type(self):
        for value in ([], ["missing"], [self.ids[0]] * 2, [["bad"]], "all"):
            with self.assertRaises(ValueError):
                review.record(self.index, self.ledger, {"selection": {**self.selection, "items": value}})
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            review.record(self.index, self.ledger, {"selection": {**self.selection, "fingerprint": "old"}})
        self.assertFalse(review.check(self.index, self.ledger)["selection"]["accounting_complete"])

    def test_provisional_events_only_block_selections_they_touch(self):
        ledger = self.complete()
        uid = self.report.findings[1].uid
        ledger = review.record(self.index, ledger, {"events": [event([uid], status="provisional")]})
        self.assertTrue(review.check(self.index, ledger)["selection"]["accounting_complete"])
        selected_event = next(e for e in ledger["events"] if self.ids[0] in e["items"])
        selected_event["status"] = "provisional"
        self.assertFalse(review.check(self.index, ledger)["selection"]["accounting_complete"])

    def test_cli_selection_gate_and_render_preserve_whole_index_status(self):
        write_json(str(Path(self.directory) / "review.json"), self.complete())
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["review", "check", self.directory, "--selection"]), 0)
        self.assertFalse(json.loads(output.getvalue())["accounting_complete"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["review", "check", self.directory]), 1)
            self.assertEqual(main(["review", "render", self.directory, "--require-selection-complete"]), 0)
        path = Path(self.directory) / "review.md"
        self.assertIn("Status: PARTIAL", path.read_text())
        self.assertIn("Selection accounting: COMPLETE", path.read_text())
        before = path.read_bytes()
        write_json(str(Path(self.directory) / "review.json"), self.configured())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["review", "render", self.directory, "--require-selection-complete"]), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_input_changes_prevent_selection_completion(self):
        write_json(str(Path(self.directory) / "review.json"), self.complete())
        source = Path(self.index["inputs"]["source_roots"]["to"]) / "engine/work.cc"
        source.write_text("changed after review\n")
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["review", "check", self.directory, "--selection"]), 1)
        self.assertFalse(json.loads(output.getvalue())["selection"]["accounting_complete"])
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        _, ledger = review.load(self.directory)
        self.assertIsNone(ledger.get("selection"))
        self.assertEqual(ledger["history"][-1]["selection"], self.selection)

    def test_context_refresh_retains_the_selection_but_reopens_affected_decisions(self):
        write_json(str(Path(self.directory) / "review.json"), self.complete())
        self.report.findings[0].enrichment = {"gerrit": {"changes": [{"number": 123}]}}
        write_json(self.path, self.report.to_dict())
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        index, ledger = review.load(self.directory)
        self.assertEqual(ledger["selection"]["items"], self.ids)
        self.assertEqual(ledger["selection"]["fingerprint"], index["fingerprint"])
        self.assertFalse(review.check(index, ledger)["selection"]["accounting_complete"])

    def test_a_refresh_that_retires_a_selected_item_says_the_selection_is_gone(self):
        """A selection that vanished silently reads as one never recorded.

        A `brief:` id is a digest of the brief's own text, so re-enriching a
        report retires the item without touching the baseline. That is a context
        refresh, which keeps unrelated decisions -- and cannot keep a selection
        naming an item the new index no longer holds.
        """
        self.report.summary["milestone_brief"] = [{"text": "Orbital ships in 2.0"}]
        write_json(self.path, self.report.to_dict())
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        index, ledger = review.load(self.directory)
        brief = next(uid for uid in index["items"] if uid.startswith("brief:"))
        selection = {"description": "One finding and the milestone lead beside it",
                     "fingerprint": index["fingerprint"], "items": [self.ids[0], brief]}
        write_json(str(Path(self.directory) / "review.json"),
                   review.record(index, ledger, {"selection": selection}))

        self.report.summary["milestone_brief"] = [{"text": "Orbital ships in 2.1"}]
        write_json(self.path, self.report.to_dict())
        result = review.initialize(self.path, self.directory, self.cache, refresh=True)
        index, ledger = review.load(self.directory)
        self.assertNotIn(brief, index["items"])
        self.assertIsNone(ledger.get("selection"))
        self.assertTrue(any("Item selection cleared" in w for w in result["warnings"]),
                        result["warnings"])
        self.assertEqual(ledger["history"][-1]["selection"], selection)
        # The gate fails closed: an absent selection cannot report completion.
        self.assertFalse(review.check(index, ledger)["selection"]["accounting_complete"])

    def test_the_reported_fields_are_the_ones_the_reference_has_to_name(self):
        """reference/selection.md presents this field list as the whole of it.

        It named eight of the ten once, leaving out `events` and `limit`. The
        list is prose, so no test can read it; what a test can do is fail when
        the set changes, so whoever changes it is told the reference moves too.
        """
        recorded = self.configured()
        self.assertEqual(sorted(review.selection_check(self.index, recorded)),
                         ["accounting_complete", "by_kind", "configured", "counts",
                          "description", "events", "limit", "outside_selection",
                          "provisional_events", "total"],
                         "selection_check's fields changed; update the field list in "
                         "skills/analyzing-chromium-upgrades/reference/selection.md "
                         "and its Vietnamese copy.")
        self.assertEqual(sorted(review.selection_check(self.index, self.ledger)),
                         ["accounting_complete", "configured"])
        stale = {**recorded, "selection": {**self.selection, "fingerprint": "old"}}
        self.assertEqual(sorted(review.selection_check(self.index, stale)),
                         ["accounting_complete", "configured", "invalid"])


if __name__ == "__main__":
    unittest.main()
