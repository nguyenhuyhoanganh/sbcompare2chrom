"""Trial isolation and semantic gates; synthetic judgments are not benchmarks."""

import copy
from contextlib import redirect_stdout
import io
import sys
import tempfile
import unittest
from pathlib import Path

from chromiumdiff import evidence, review, review_eval, review_trials
from chromiumdiff.cli import main
from chromiumdiff.model import read_json, write_json
from chromiumdiff.snapshot import tree_path
from tests.test_review import fixture, event


class TestSemanticGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        report, _, _, cache, report_path = fixture(self.tmp.name)
        directory = str(Path(self.tmp.name) / "review")
        review.initialize(report_path, directory, cache)
        index, ledger = review.load(directory)
        uid = report.findings[0].uid
        ledger = review.record(index, ledger, {"events": [event([uid], id="observed")],
            "dispositions": [{"id": key, "status": "explained", "reason": "Synthetic unit-test judgment"}
                             for key in index["items"] if key != uid]})
        self.gold = {"provenance": "Synthetic gate contract, not a real independent adjudication",
                     "events": [{"id": "expected", "items": [uid], "critical": True}]}
        self.trials = [("run-" + str(i), index, copy.deepcopy(ledger)) for i in range(5)]
        assessment = {"verdict": "pass", "reason": "Synthetic assessment", "evidence": ["fixture before/after"]}
        self.adjudication = {"gold_digest": evidence.digest(self.gold), "reviewer": "unit test",
            "provenance": "Synthetic contract only", "trials": {label: {
                "ledger_digest": evidence.digest(saved), "reviewed_predicted_event_ids": ["observed"],
                "events": [{"gold_id": "expected", "predicted_event_ids": ["observed"],
                            "checks": {key: copy.deepcopy(assessment) for key in review_eval.CHECKS}}],
                "dispositions": copy.deepcopy(assessment), "unsupported_claims": []}
            for label, _, saved in self.trials}}
        self.manifests = [{"review_directory": label, "state": "collected",
            "source_spec_digest": "fixed-spec", "implementation": idx["inputs"]["implementation"],
            "runner": {"model": "synthetic-runner", "context_limit": 200000, "context_limit_verified": True},
            "execution": {"session_id": label},
            "result": {"artifacts_valid": True, "ledger_digest": evidence.digest(saved),
                       "fingerprint": idx["fingerprint"]}}
            for label, idx, saved in self.trials]

    def evaluate(self):
        return review_eval.evaluate(self.gold, self.trials, self.adjudication, self.manifests)

    def test_complete_pinned_adjudication_has_only_case_scoped_pass(self):
        result = self.evaluate()
        self.assertEqual(result["release_verdict"], "pass_for_pinned_case_and_runner_only")
        self.assertEqual(result["release_blockers"], [])

    def test_assessment_template_is_pinned_but_never_prefilled_as_correct(self):
        template = review_eval.assessment_template(self.gold, self.trials)
        self.assertEqual(template["gold_digest"], evidence.digest(self.gold))
        entry = template["trials"]["run-0"]
        self.assertEqual(entry["reviewed_predicted_event_ids"], [])
        self.assertEqual(entry["predicted_event_ids_to_review"], ["observed"])
        self.assertTrue(all(c["verdict"] == "unresolved" for c in entry["events"][0]["checks"].values()))
        with self.assertRaisesRegex(ValueError, "reviewer"):
            review_eval.evaluate(self.gold, self.trials, template, self.manifests)

    def test_perfect_membership_cannot_override_wrong_meaning(self):
        self.adjudication["trials"]["run-0"]["events"][0]["checks"]["meaning"]["verdict"] = "fail"
        result = self.evaluate()
        self.assertEqual(result["trials"][0]["exact_event_membership_recall"], 1)
        self.assertEqual(result["semantic_accuracy"]["trials"][0]["event_recall"], 0)
        self.assertEqual(result["release_verdict"], "not_passed")

    def test_missing_citations_and_unreviewed_extras_are_rejected(self):
        entry = self.adjudication["trials"]["run-0"]
        entry["events"][0]["checks"]["citations"]["evidence"] = []
        with self.assertRaisesRegex(ValueError, "evidence citations"):
            self.evaluate()
        entry["events"][0]["checks"]["citations"]["evidence"] = ["source"]
        entry["reviewed_predicted_event_ids"] = []
        with self.assertRaisesRegex(ValueError, "all predicted events"):
            self.evaluate()

    def test_stale_gold_and_stale_prose_cannot_reuse_adjudication(self):
        self.gold["events"][0]["critical"] = False
        with self.assertRaisesRegex(ValueError, "gold digest"):
            self.evaluate()
        self.gold["events"][0]["critical"] = True
        self.trials[0][2]["events"][0]["after"] = "A new unsupported claim"
        with self.assertRaisesRegex(ValueError, "stale"):
            self.evaluate()

    def test_major_unsupported_claim_blocks_even_when_event_is_recovered(self):
        self.adjudication["trials"]["run-0"]["unsupported_claims"] = [{
            "event_id": "observed", "severity": "major", "claim": "Invented rollout",
            "reason": "No rollout evidence", "evidence": ["source only declares default"]}]
        self.assertEqual(self.evaluate()["release_verdict"], "not_passed")

    def test_copied_execution_or_unknown_context_budget_cannot_pass(self):
        self.manifests[1]["execution"]["session_id"] = self.manifests[0]["execution"]["session_id"]
        self.assertEqual(self.evaluate()["release_verdict"], "not_passed")
        self.manifests[1]["execution"]["session_id"] = "run-1"
        self.manifests[1]["runner"]["context_limit_verified"] = False
        self.assertEqual(self.evaluate()["release_verdict"], "not_passed")

    def test_single_run_and_unreviewed_dispositions_do_not_establish_release(self):
        self.trials = self.trials[:1]
        self.adjudication["trials"] = {"run-0": self.adjudication["trials"]["run-0"]}
        self.adjudication["trials"]["run-0"]["dispositions"]["verdict"] = "unresolved"
        result = self.evaluate()
        self.assertEqual(result["release_verdict"], "not_passed")
        self.assertTrue(any("five" in s for s in result["release_blockers"]))

    def test_changed_report_or_source_cannot_pass_old_assessment(self):
        index = self.trials[0][1]
        path = index["inputs"]["report"]
        data = read_json(path)
        data["findings"][0]["enrichment"] = {"new": "context"}
        write_json(path, data)
        result = self.evaluate()
        self.assertFalse(result["semantic_accuracy"]["trials"][0]["accounting_complete"])
        self.assertEqual(result["release_verdict"], "not_passed")

    def test_cli_adjudication_failure_is_nonzero_and_template_will_not_overwrite(self):
        directory = str(Path(self.tmp.name, "review").resolve())
        ledger = self.trials[0][2]
        write_json(str(Path(directory, "review.json")), ledger)
        entry = self.adjudication["trials"]["run-0"]
        self.adjudication["trials"] = {directory: entry}
        gold = str(Path(self.tmp.name, "gold.json"))
        assessment = str(Path(self.tmp.name, "assessment.json"))
        output = str(Path(self.tmp.name, "template.json"))
        write_json(gold, self.gold)
        write_json(assessment, self.adjudication)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["review", "evaluate", gold, directory,
                                   "--adjudication", assessment]), 1)
            self.assertEqual(main(["review", "assessment-template", gold, directory, "--output", output]), 0)
        before = Path(output).read_bytes()
        from chromiumdiff.review_cli import command
        from chromiumdiff.cli import build_parser
        args = build_parser().parse_args(["review", "assessment-template", gold, directory, "--output", output])
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            command(args)
        self.assertEqual(Path(output).read_bytes(), before)


class TestTrialRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = str(Path(self.tmp.name) / "cache")
        self.file = "third_party/blink/renderer/modules/testing/unlisted.idl"
        self.spec = {"id": "arbitrary-source-case", "refs": {"from": "1.0.0.0", "to": "2.0.0.0"},
                     "files": [self.file, "engine/implementation.cc"]}
        for side, ref in self.spec["refs"].items():
            root = Path(tree_path(self.cache, ref))
            path = root / self.file
            path.parent.mkdir(parents=True)
            member = "previous" if side == "from" else "replacement"
            path.write_text("[Exposed=Window] interface Unlisted {\n  attribute long " + member + ";\n};\n")
            (root / "engine").mkdir()
            (root / "engine/implementation.cc").write_text("// " + side + " implementation\n")

    def prepare(self, name="trial", **kwargs):
        return review_trials.prepare(self.spec, str(Path(self.tmp.name) / name), self.cache, **kwargs)

    def test_answer_free_staging_with_raw_source_and_example_ablation(self):
        metadata = self.prepare(reference_mode="core")
        workspace = Path(metadata["workspace"])
        self.assertFalse((workspace / "tests").exists())
        self.assertFalse(list(workspace.rglob("evaluations.json")))
        refs = workspace / "skills/analyzing-chromium-upgrades/reference"
        self.assertIn("withheld", (refs / "traps.md").read_text())
        self.assertIn("Recording decisions", (refs / "investigation.md").read_text())
        self.assertTrue(metadata["staged_skill_sha256"])
        self.assertIn("implementation.cc", str(metadata["source_sha256"]))
        with self.assertRaisesRegex(ValueError, "never overwritten"):
            self.prepare()

    def test_rank_and_directory_perturbation_preserve_evidence_identity(self):
        fingerprints = []
        for name, seed in (("one", 0), ("two", 73)):
            trial = self.prepare(name, seed=seed)
            root = Path(trial["workspace"])
            review.initialize(str(root / "data"), trial["review_directory"], str(root / "data/cache"))
            index, _ = review.load(trial["review_directory"])
            fingerprints.append(index["fingerprint"])
        self.assertEqual(fingerprints[0], fingerprints[1])

    def test_case_missing_source_and_wrong_hash_are_not_silent(self):
        self.spec["sha256"] = {"from": {self.file: "wrong"}}
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.prepare("wrong-hash")
        self.spec.pop("sha256")
        self.spec["files"].append("missing.cc")
        with self.assertRaisesRegex(ValueError, "absence cannot be inferred"):
            self.prepare("missing")

    def test_runner_failure_is_collected_not_fabricated_as_success(self):
        self.prepare()
        directory = str(Path(self.tmp.name) / "trial")
        result = review_trials.run(directory, {"model": "synthetic-command", "context_limit": 200000,
            "timeout_seconds": 10, "command": [sys.executable, "-c", "raise SystemExit(7)"]})
        self.assertEqual(result["execution"]["exit_code"], 7)
        self.assertTrue(result["execution"]["session_id"])
        self.assertFalse(result["result"]["artifacts_valid"])
        with self.assertRaisesRegex(ValueError, "already been attempted"):
            review_trials.run(directory, {})

    def test_runner_argv_validation_and_timeout(self):
        self.prepare()
        directory = str(Path(self.tmp.name) / "trial")
        runner = {"model": "synthetic", "context_limit": 1000, "timeout_seconds": 1,
                  "command": "not a shell string"}
        with self.assertRaisesRegex(ValueError, "argv"):
            review_trials.run(directory, runner)
        runner["command"] = [sys.executable, "-c", "import time; time.sleep(2)"]
        result = review_trials.run(directory, runner)
        self.assertTrue(result["execution"]["timed_out"])
        self.assertFalse(result["result"]["accounting_complete"])

    def test_unexecuted_interactive_trial_cannot_be_collected_without_identity(self):
        self.prepare()
        directory = str(Path(self.tmp.name) / "trial")
        with self.assertRaisesRegex(ValueError, "unique session_id"):
            review_trials.finish(directory, {"model": "unknown"})
        result = review_trials.finish(directory, {"model": "tool default, revision unknown", "session_id": "failed-test"})
        self.assertFalse(result["result"]["artifacts_valid"])
        self.assertNotIn("context_limit_verified", result["runner"])


class TestCaseRubrics(unittest.TestCase):
    def test_real_case_rubrics_are_source_pinned_and_separate_from_runtime(self):
        root = Path(__file__).resolve().parent / "fixtures"
        cases = list((root / "review_cases").glob("*.json"))
        self.assertGreaterEqual(len(cases), 2)
        for path in cases:
            spec = read_json(str(path))
            gold = read_json(str(root / "review_gold" / path.name))
            self.assertEqual(gold["source_spec_digest"], evidence.digest(spec))
            sources = set(spec["files"] + spec.get("context_files", []))
            for side in ("from", "to"):
                self.assertEqual(set(spec["sha256"][side]), sources)
                self.assertTrue(all(len(h) == 64 for h in spec["sha256"][side].values()))
            for item in gold["events"]:
                self.assertTrue(set(item["source_paths"]) <= sources)
                self.assertTrue(item["required_meaning"])
            self.assertTrue(gold["negative_controls"])


if __name__ == "__main__":
    unittest.main()
