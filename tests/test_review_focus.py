"""Focused evidence retrieval; tests do not assert semantic conclusions."""

import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from chromiumdiff import review, review_focus
from chromiumdiff.cli import main
from chromiumdiff.model import Fact, Change, Finding, write_json
from chromiumdiff.snapshot import snapshot_path, tree_path
from tests.test_review import fixture


class TestFocus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        report, old, new, self.cache, self.report_path = fixture(self.tmp.name)
        self.directory = str(Path(self.tmp.name) / "review")
        # The user area is intentionally an arbitrary name. It contains no
        # changed declaration referring to the dependency: unchanged source
        # and facts are necessary to recover the external change.
        self.prefix = "unlisted-area"
        old_dep = Fact("base_feature", "Unfamiliar", "Unfamiliar", "shared/features.cc", 1,
                       {"var": "kUnfamiliar", "default_state": "disabled"})
        new_dep = Fact("base_feature", "Unfamiliar", "Unfamiliar", "shared/features.cc", 1,
                       {"var": "kUnfamiliar", "default_state": "enabled"})
        iface = Fact("mojo_interface", "arbitrary.mojom.Endpoint", "Endpoint", "shared/api.mojom", 1,
                     {"module": "arbitrary.mojom"})
        method = Fact("mojo_method", "arbitrary.mojom.Endpoint.Perform", "Perform", "shared/api.mojom", 2,
                      {"interface": "arbitrary.mojom.Endpoint", "signature": "Perform(int32 value)"})
        for snap, dep in ((old, old_dep), (new, new_dep)):
            snap.facts.extend([dep, iface])
            if snap is new:
                snap.facts.append(method)
            write_json(snapshot_path(self.cache, snap.ref, "default"), snap.to_dict())
            root = Path(tree_path(self.cache, snap.ref))
            (root / self.prefix).mkdir()
            (root / "shared").mkdir()
            # An unchanged file still links the selected area to both changes.
            (root / self.prefix / "consumer.cc").write_text(
                "if (base::FeatureList::IsEnabled(features::kUnfamiliar)) {}\n"
                "arbitrary::mojom::Endpoint* endpoint;\n"
                '#include "shared/raw.mojom.h"\n'
                "if (base::FeatureList::IsEnabled(features::kMissingDeclaration)) {}\n")
            (root / self.prefix / "body.cc").write_text("// " + snap.ref + "\n")
            (root / "shared/features.cc").write_text(str(dep.attrs))
            (root / "shared/api.mojom").write_text("interface Endpoint {" +
                                                  ("Perform(int32 value);" if snap is new else "") + "};\n")
            (root / "shared/raw.mojom").write_text("// unparsed " + snap.ref + "\n")
        report.findings.extend([
            Finding(Change("modified", old_dep.kind, old_dep.key, old_dep.name,
                           before=old_dep.attrs, after=new_dep.attrs, paths=[old_dep.path],
                           deltas={"default_state": {"before": "disabled", "after": "enabled"}}), score=0),
            Finding(Change("added", method.kind, method.key, method.name,
                           after=method.attrs, paths=[method.path]), score=0)])
        write_json(self.report_path, report.to_dict())
        review.initialize(self.report_path, self.directory, self.cache)
        self.index, self.ledger = review.load(self.directory)

    def test_unchanged_source_retrieves_external_flag_and_mojo_without_name_rules(self):
        packet = review_focus.build(self.index, [self.prefix], ["webui_route"])
        ids = {row["id"] for row in packet["findings"]}
        self.assertIn("base_feature:Unfamiliar", ids)
        self.assertIn("mojo_method:arbitrary.mojom.Endpoint.Perform", ids)
        self.assertTrue(all(not row["requested_kind"] for row in packet["findings"]))
        self.assertTrue(all(row["selection"] == "dependency" for row in packet["findings"]))
        files = {row["id"] for row in packet["files"]}
        self.assertIn("file:unlisted-area/body.cc", files)
        self.assertIn("file:shared/raw.mojom", files)
        self.assertNotIn("file:unlisted-area/consumer.cc", files)  # unchanged, but scanned
        self.assertTrue(any(q.get("identifier") == "features::kMissingDeclaration" for q in packet["unresolved"]))
        self.assertEqual(self.ledger["dispositions"], {})
        self.assertIsNone(packet["summary"]["token_count"])

    def test_focus_does_not_expand_every_consumer_of_a_shared_flag(self):
        packet = review_focus.build(self.index, ["ui"])
        ids = {row["id"] for row in packet["findings"]}
        self.assertNotIn("feature_param:Orbital:Limit", ids)
        self.assertIn("webui_route:OrbitalNew", ids)

    def test_hop_boundary_and_ambiguous_source_references_are_visible(self):
        packet = review_focus.build(self.index, [self.prefix], hops=0)
        self.assertTrue(any(q.get("reason", "").startswith("Dependency hop limit") for q in packet["unresolved"]))
        duplicate = copy.deepcopy(self.index["graph"]["nodes"]["base_feature:Unfamiliar"])
        duplicate["uid"] = "base_feature:DifferentOwner"
        self.index["graph"]["nodes"][duplicate["uid"]] = duplicate
        packet = review_focus.build(self.index, [self.prefix])
        ambiguous = [r for r in packet["references"] if r.get("certainty") == "ambiguous_lead"]
        self.assertTrue(any("base_feature:DifferentOwner" in r["targets"] for r in ambiguous))

    def test_unmatched_reference_is_labelled_and_every_question_states_a_check(self):
        packet = review_focus.build(self.index, [self.prefix])
        unmatched = [r for r in packet["references"] if r["certainty"] == "unmatched"]
        self.assertTrue(unmatched)
        self.assertTrue(all(r["targets"] == [] for r in unmatched))
        # Source matches and declared edges are different row shapes in one
        # section; certainty is the field an agent can read on either.
        self.assertEqual([r for r in packet["references"]
                          if r.get("targets") == [] and r["certainty"] != "unmatched"], [])
        self.assertLessEqual({r["certainty"] for r in packet["references"]},
                             {"declared_reference", "lexical_lead", "ambiguous_lead", "unmatched"})
        # Every question must name its own next check, not only the ones the
        # graph produced; an unlabelled row tells the agent nothing to do.
        self.assertTrue(all(row.get("reason") for row in packet["unresolved"]))

    def test_missing_side_and_missing_snapshot_paths_do_not_silently_drop_items(self):
        for node in self.index["graph"]["nodes"].values():
            for fact in node.get("sides", {}).values():
                fact.pop("path", None)
        packet = review_focus.build(self.index, ["ui"])
        self.assertIn("webui_route:OrbitalNew", {r["id"] for r in packet["findings"]})
        self.assertTrue(any(q.get("path") == "ui/extra.ts" for q in packet["unresolved"]))

    def test_order_and_scores_do_not_change_focus(self):
        before = review_focus.build(self.index, [self.prefix])
        self.index["items"] = dict(reversed(list(self.index["items"].items())))
        self.index["graph"]["edges"].reverse()
        for item in self.index["items"].values():
            if item["kind"] == "finding":
                item["data"]["score"] = 999
                item["data"]["bucket"] = "changed-ranking"
        self.assertEqual(review_focus.build(self.index, [self.prefix]), before)

    def test_packet_freshness_digest_and_previews(self):
        packet = review_focus.build(self.index, [self.prefix])
        path = str(Path(self.tmp.name) / "focus.json")
        write_json(path, packet)
        self.assertEqual(review_focus.load(self.index, path), packet)
        changed = copy.deepcopy(packet)
        changed["findings"].clear()
        write_json(path, changed)
        with self.assertRaisesRegex(ValueError, "content changed"):
            review_focus.load(self.index, path)
        write_json(path, packet)
        Path(self.index["inputs"]["source_roots"]["to"], self.prefix, "consumer.cc").write_text("changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            review_focus.load(self.index, path)
        self.assertTrue(review_focus._preview("x" * 2000)["truncated"])

    def test_cli_build_read_and_no_overwrite(self):
        path = str(Path(self.tmp.name) / "focus.json")
        def cli(*args):
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = main(["review", *args])
            return code, json.loads(out.getvalue()) if out.getvalue() else None
        code, result = cli("focus", self.directory, "--path-prefix", self.prefix, "--output", path)
        self.assertEqual(code, 0)
        self.assertGreater(result["dependency_findings"], 0)
        self.assertEqual(cli("focus", self.directory, "--path-prefix", self.prefix, "--output", path)[0], 1)
        code, result = cli("focus-read", self.directory, "--file", path, "--section", "findings", "--limit", "1")
        self.assertEqual(code, 0)
        self.assertIsNotNone(result["next_cursor"])
        self.assertEqual(result["items"][0]["status"], "pending")
        code, refs = cli("focus-read", self.directory, "--file", path, "--section", "references",
                         "--item", "base_feature:Unfamiliar")
        self.assertTrue(refs["items"])
        self.assertEqual(review.load(self.directory)[1], self.ledger)

    def test_empty_or_unknown_scope_is_not_silently_complete(self):
        with self.assertRaisesRegex(ValueError, "requires path prefixes"):
            review_focus.build(self.index, [])
        packet = review_focus.build(self.index, ["nonexistent-area"])
        self.assertEqual(packet["findings"], [])
        self.assertTrue(packet["unresolved"])
        self.assertEqual(packet["summary"]["semantic_completeness"], "not measured")

    def test_git_focus_reads_pinned_objects_not_the_checkout(self):
        repo = Path(self.tmp.name) / "git-source"
        repo.mkdir()
        def git(*args):
            return subprocess.run(["git", "-C", str(repo), *args], check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git("init")
        for side, ref in self.index["inputs"]["refs"].items():
            shutil.copytree(self.index["inputs"]["source_roots"][side], repo, dirs_exist_ok=True)
            git("add", ".")
            git("-c", "user.email=test@example.invalid", "-c", "user.name=Fixture",
                "commit", "-m", side)
            git("tag", ref.removeprefix("refs/tags/"))
        Path(repo, self.prefix, "consumer.cc").write_text("uncommitted checkout contents")
        status = git("status", "--porcelain").stdout
        directory = str(Path(self.tmp.name) / "git-review")
        review.initialize(self.report_path, directory, self.cache, str(repo))
        index, _ = review.load(directory)
        packet = review_focus.build(index, [self.prefix])
        self.assertIn("base_feature:Unfamiliar", {row["id"] for row in packet["findings"]})
        self.assertTrue(all(row["origin"] == "git" for row in packet["sources"]))
        self.assertEqual(git("status", "--porcelain").stdout, status)


if __name__ == "__main__":
    unittest.main()
