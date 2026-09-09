"""Synthetic contracts for blind root-cause trials; not semantic benchmarks."""

from pathlib import Path
import tempfile
import sys
import unittest

from chromiumdiff import review, review_trials, root_cause_eval
from chromiumdiff.evidence import digest
from chromiumdiff.model import read_json, write_json
from chromiumdiff.snapshot import tree_path


class TestRootCauseTrials(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = str(Path(self.tmp.name) / "cache")
        self.file = "engine/implementation.cc"
        self.spec = {"id": "synthetic-cause", "question": "Why did capacity change?",
                     "refs": {"from": "1.0.0.0", "to": "2.0.0.0"}, "files": [self.file],
                     "sha256": {}, "history_files": {}}
        for side, ref in self.spec["refs"].items():
            path = Path(tree_path(self.cache, ref)) / self.file
            path.parent.mkdir(parents=True)
            path.write_text("int capacity() { return " + ("4" if side == "from" else "8") + "; }\n")
            self.spec["sha256"][side] = {self.file: review._file_hash(path)}
        self.gold = {"case_id": self.spec["id"], "source_spec_digest": digest(self.spec),
                     "provenance": "Synthetic fixture, no semantic benchmark claims",
                     "checks": {key: "Synthetic expected evidence" for key in root_cause_eval.CHECKS}}

    def prepare(self, name):
        directory = str(Path(self.tmp.name) / name)
        meta = review_trials.prepare(self.spec, directory, self.cache, reference_mode="core", task_type="root-cause")
        return directory, meta

    def collected(self, count=1):
        paths = []
        for n in range(count):
            directory, metadata = self.prepare(str(n))
            (Path(metadata["workspace"]) / "answer.md").write_text("Synthetic answer; no causal claim.\n")
            review_trials.finish(directory, {"model": "synthetic-test-runner", "session_id": str(n),
                                            "context_limit": 10000, "context_limit_verified": True})
            paths.append(directory)
        return paths

    def assessment(self, paths):
        result = root_cause_eval.assessment_template(self.gold, paths)
        result.update(reviewer="synthetic-independent-reviewer", provenance="Unit-test judgments only")
        for entry in result["trials"].values():
            entry.update(answer_reviewed=True, unsupported_claims=[])
            for check in entry["checks"].values():
                check.update(verdict="pass", reason="Synthetic supported claim", evidence=["fixed source"])
        return result

    def test_staging_has_only_requested_skill_and_no_expected_answers(self):
        directory, meta = self.prepare("blind")
        workspace = Path(meta["workspace"])
        self.assertEqual([p.name for p in (workspace / "skills").iterdir()], ["investigating-chromium-root-causes"])
        self.assertFalse(list(workspace.rglob("evaluations.json")))
        self.assertFalse((workspace / "tests").exists())
        self.assertFalse(root_cause_eval.inspect_trial(meta)["artifacts_valid"])
        self.assertTrue(meta["frozen_files"])
        with self.assertRaises(ValueError):
            self.prepare("blind")
        self.spec["sha256"]["to"][self.file] = "wrong"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.prepare("changed-input")

    def test_history_must_be_pinned_and_is_copied_to_the_runtime_cache(self):
        relative = "gerrit/probe/123.json"
        src = Path(self.cache) / relative
        write_json(str(src), {"status": "MERGED"})
        self.spec["history_files"] = {relative: review._file_hash(src)}
        _, metadata = self.prepare("history")
        target = Path(metadata["workspace"]) / "data/cache" / relative
        self.assertEqual(target.read_bytes(), src.read_bytes())
        src.write_text("{}")
        with self.assertRaisesRegex(ValueError, "history file"):
            self.prepare("bad-history")

    def test_one_answer_or_unreviewed_checks_cannot_pass(self):
        paths = self.collected()
        template = root_cause_eval.assessment_template(self.gold, paths)
        self.assertTrue(all(c["verdict"] == "unresolved" for e in template["trials"].values() for c in e["checks"].values()))
        self.assertEqual(root_cause_eval.evaluate(self.gold, paths)["verdict"], "not_passed")
        self.assertEqual(root_cause_eval.evaluate(self.gold, paths, self.assessment(paths))["verdict"], "not_passed")

    def test_five_synthetic_assessments_pass_only_with_complete_provenance(self):
        paths = self.collected(5)
        assessment = self.assessment(paths)
        self.assertEqual(root_cause_eval.evaluate(self.gold, paths, assessment)["verdict"],
                         "pass_for_pinned_case_and_runner_only")
        entry = next(iter(assessment["trials"].values()))
        entry["checks"]["cause"]["verdict"] = "fail"
        self.assertEqual(root_cause_eval.evaluate(self.gold, paths, assessment)["verdict"], "not_passed")
        entry["checks"]["cause"]["verdict"] = "pass"
        meta_path = Path(paths[1]) / "trial.json"
        meta = read_json(str(meta_path))
        meta["execution"]["session_id"] = "0"
        write_json(str(meta_path), meta)
        self.assertEqual(root_cause_eval.evaluate(self.gold, paths, assessment)["verdict"], "not_passed")

    def test_changed_prose_and_changed_evidence_invalidate_assessment(self):
        paths = self.collected()
        assessment = self.assessment(paths)
        meta = read_json(str(Path(paths[0]) / "trial.json"))
        answer = Path(meta["workspace"]) / "answer.md"
        before = answer.read_bytes()
        answer.write_text("Different claim\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            root_cause_eval.evaluate(self.gold, paths, assessment)
        answer.write_bytes(before)
        frozen = next(p for p in meta["frozen_files"] if p.endswith("implementation.cc"))
        (Path(meta["workspace"]) / frozen).write_text("tampered source\n")
        result = root_cause_eval.evaluate(self.gold, paths, assessment)
        self.assertFalse(result["trials"][0]["artifacts_valid"])

    def test_failed_execution_and_unsupported_claims_cannot_receive_credit(self):
        paths = self.collected()
        assessment = self.assessment(paths)
        entry = next(iter(assessment["trials"].values()))
        entry["unsupported_claims"] = [{"severity": "major", "claim": "invented cause",
                                         "reason": "no evidence", "evidence": ["source only"]}]
        self.assertFalse(root_cause_eval.evaluate(self.gold, paths, assessment)["trials"][0]["semantic_pass"])
        entry["unsupported_claims"] = []
        meta_path = Path(paths[0]) / "trial.json"
        meta = read_json(str(meta_path))
        meta["execution"]["error"] = "runner failed"
        write_json(str(meta_path), meta)
        self.assertFalse(root_cause_eval.evaluate(self.gold, paths, assessment)["trials"][0]["semantic_pass"])

    def test_command_runner_collects_the_root_answer_without_a_review_ledger(self):
        directory, meta = self.prepare("command-runner")
        runner = {"model": "synthetic-command-runner", "context_limit": 10000,
                  "context_limit_verified": True, "timeout_seconds": 10,
                  "command": [sys.executable, "-c",
                              "from pathlib import Path; Path('answer.md').write_text('Synthetic output, not a semantic evaluation')"]}
        result = review_trials.run(directory, runner)
        self.assertEqual(result["state"], "collected")
        self.assertEqual(result["execution"]["exit_code"], 0)
        self.assertTrue(result["result"]["artifacts_valid"])
        self.assertFalse((Path(meta["review_directory"]) / "review.json").exists())
        with self.assertRaisesRegex(ValueError, "already been attempted"):
            review_trials.run(directory, runner)


if __name__ == "__main__":
    unittest.main()
