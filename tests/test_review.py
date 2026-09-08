"""Investigation invariants, deliberately independent of named Chromium cases."""

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from chromiumdiff import cluster, evidence, review
from chromiumdiff.cli import main
from chromiumdiff.model import Change, Fact, Finding, Report, Snapshot, write_json
from chromiumdiff.snapshot import snapshot_path, tree_path


def fixture(root, prefix="Orbital"):
    cache = str(Path(root) / "cache")
    meta = dict(target_set="default", platform="windows", partitions=[], complete=False)
    feature = Fact("base_feature", prefix, prefix, "engine/features.cc", 2,
                   {"var": "k" + prefix, "platform_state": {"windows": "enabled"}})
    gate = Fact("webui_gate", "handler/visible", "visible", "ui/handler.cc", 2,
                {"data_key": "visible", "features": ["k" + prefix]})
    before = Fact("webui_route", prefix + "Old", prefix + "Old", "ui/route.ts", 2,
                  {"guards": ["visible"], "route": "/old"})
    after = Fact("webui_route", prefix + "New", prefix + "New", "ui/route.ts", 2,
                 {"guards": ["visible"], "route": "/new"})
    param = Fact("feature_param", prefix + ":Limit", "Limit", "engine/features.cc", 3,
                 {"feature": "k" + prefix, "value": "12"})
    old = Snapshot("refs/tags/1.0.0.0", [feature, gate, before], meta=meta)
    new = Snapshot("refs/tags/2.0.0.0", [feature, gate, after, param], meta=meta)
    findings = [Finding(Change("removed", before.kind, before.key, before.name,
                              before=before.attrs, paths=[before.path]), score=0),
                Finding(Change("added", after.kind, after.key, after.name,
                               after=after.attrs, paths=[after.path]), score=1),
                Finding(Change("added", param.kind, param.key, param.name,
                               after=param.attrs, paths=[param.path]), score=50)]
    report = Report(old.ref, new.ref, findings, meta=meta)
    path = str(Path(root) / "report.json")
    write_json(path, report.to_dict())
    for snap, route in ((old, "old"), (new, "new")):
        write_json(snapshot_path(cache, snap.ref, "default"), snap.to_dict())
        tree = Path(tree_path(cache, snap.ref))
        (tree / "ui").mkdir(parents=True)
        (tree / "engine").mkdir()
        (tree / "ui/route.ts").write_text("// routes\nopen('/" + route + "');\n")
        (tree / "engine/features.cc").write_text("// declarations\nfeature();\n")
        # The implementation-only path is not a declared extractor target.
        (tree / "engine/work.cc").write_text("int capacity() { return " +
                                             ("4" if snap is old else "12") + "; }\n")
    (Path(tree_path(cache, new.ref)) / "ui/extra.ts").write_text("// cached on one side only\n")
    return report, old, new, cache, path


def event(ids, **kw):
    value = dict(title="Entry moves to its replacement", status="confirmed", items=ids,
                 before="The prior entry was declared", after="The new entry is declared",
                 mechanism="The same backing binding connects the entry transition",
                 impact="Consumers of the old route should be checked",
                 conditions="Windows source defaults; actual rollout unknown",
                 action="Inspect callers of the old route", uncertainties=[],
                 evidence=[{"item": uid, "supports": "Contributes its before/after transition"}
                           for uid in ids])
    value.update(kw)
    return value


class TestEvidenceGraph(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report, self.old, self.new, _, _ = fixture(self.tmp.name)

    def test_unchanged_bridges_work_for_unseen_names(self):
        for name in ("Orbital", "UnlistedZX19", "ArbitraryPermissionQ"):
            old = copy.deepcopy(self.old)
            new = copy.deepcopy(self.new)
            report = copy.deepcopy(self.report)
            # Rename consistently, without adding name-specific rules.
            old = Snapshot.from_dict(json.loads(json.dumps(old.to_dict()).replace("Orbital", name)))
            new = Snapshot.from_dict(json.loads(json.dumps(new.to_dict()).replace("Orbital", name)))
            report = Report.from_dict(json.loads(json.dumps(report.to_dict()).replace("Orbital", name)))
            graph = evidence.build_graph(report, old, new)
            rows = evidence.related(graph, "feature_param:" + name + ":Limit", hops=3)
            target = [r for r in rows if r["uid"] == "webui_route:" + name + "New"]
            self.assertTrue(target)
            self.assertEqual([e["relation"] for e in target[0]["chain"]],
                             ["parameter_owner", "feature_expression", "guard"])
            self.assertFalse(graph["nodes"]["base_feature:" + name].get("finding"))

    def test_graph_ignores_scores_buckets_and_input_order(self):
        expected = evidence.build_graph(self.report, self.old, self.new)
        self.report.findings.reverse()
        for f in self.report.findings:
            f.score = 100 - f.score
            f.bucket = "contract"
        self.old.facts.reverse()
        self.new.facts.reverse()
        self.assertEqual(evidence.build_graph(self.report, self.old, self.new), expected)

    def test_ambiguous_handler_is_visible_and_not_expanded(self):
        extra = Fact("webui_gate", "other/visible", "visible", "other.cc", 1,
                     {"data_key": "visible", "features": ["kOrbital"]})
        self.new.facts.append(extra)
        graph = evidence.build_graph(self.report, self.old, self.new)
        rows = evidence.related(graph, "webui_route:OrbitalNew", hops=3)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["chain"][0]["certainty"] == "ambiguous_target" for r in rows))

    def test_explicit_none_is_not_joined_by_similar_name(self):
        self.new.facts.append(Fact("blink_runtime_feature", "Orbital", "Orbital", "runtime.json5", 2,
                                  {"base_feature": "none"}))
        graph = evidence.build_graph(self.report, self.old, self.new)
        self.assertFalse(evidence.related(graph, "blink_runtime_feature:Orbital"))
        same_name = [Finding(Change("added", "base_feature", "Orbital", "Orbital", after={})),
                     Finding(Change("added", "blink_runtime_feature", "Orbital", "Orbital",
                                    after={"base_feature": "none"}))]
        self.assertEqual(cluster.build_clusters(same_name), {})

    def test_both_sides_and_unresolved_references_survive(self):
        self.old.facts[-1].attrs["guards"] = ["oldMissingGuard"]
        graph = evidence.build_graph(self.report, self.old, self.new)
        self.assertTrue(any(r["identifier"] == "oldMissingGuard" and r["side"] == "from"
                            for r in graph["unresolved"]))
        self.assertTrue(any(e["side"] == "to" for e in graph["edges"]))

    def test_shared_cl_is_a_link_not_an_event(self):
        for f in self.report.findings:
            f.enrichment["gerrit"] = {"changes": [{"number": 123, "match": "exact"}]}
        graph = evidence.build_graph(self.report)
        self.assertNotIn("events", graph)
        rows = evidence.related(graph, self.report.findings[0].uid, hub_limit=1)
        self.assertTrue(any(r.get("hub") and r["uid"] == "cl:123" for r in rows))
        self.assertEqual(len(evidence.related(graph, "cl:123", hops=1)), 3)

    def test_prose_cl_match_is_a_lead(self):
        self.report.findings[0].enrichment["gerrit"] = {
            "changes": [{"number": 123, "match": "described"}]}
        graph = evidence.build_graph(self.report)
        self.assertEqual(graph["edges"][0]["certainty"], "lead")


class TestReviewWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report, self.old, self.new, self.cache, self.path = fixture(self.tmp.name)
        self.directory = str(Path(self.tmp.name) / "review")
        review.initialize(self.path, self.directory, self.cache)
        self.index, self.ledger = review.load(self.directory)

    def cli(self, *args):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(["review", *args])
        return code, json.loads(stdout.getvalue()) if stdout.getvalue() else None

    def test_raw_implementation_delta_and_unknown_cache_side_are_indexed(self):
        rows = self.index["items"]
        self.assertEqual(rows["file:engine/work.cc"]["findings"], [])
        self.assertEqual(rows["file:engine/work.cc"]["state"], "modified")
        self.assertEqual(rows["file:ui/extra.ts"]["state"], "one_side_cached")
        self.assertNotIn("file:engine/features.cc", rows)

    def test_hidden_source_is_included_but_acquisition_markers_are_not(self):
        roots = self.index["inputs"]["source_roots"]
        for side in ("from", "to"):
            Path(roots[side], ".gn").write_text(side)
            markers = Path(roots[side], ".chromiumdiff")
            markers.mkdir()
            (markers / "marker").write_text(side)
        rows, _ = review.source_inventory(roots)
        self.assertIn(".gn", {r["path"] for r in rows})
        self.assertNotIn(".chromiumdiff/marker", {r["path"] for r in rows})

    def test_init_does_not_overwrite_existing_review_without_refresh(self):
        with self.assertRaisesRegex(ValueError, "review exists"):
            review.initialize(self.path, self.directory, self.cache)

    def test_every_item_is_pageable_without_score_cutoff(self):
        expected = sorted(self.index["items"])
        seen, after = [], ""
        while True:
            code, data = self.cli("index", self.directory, "--limit", "1", "--after", after)
            self.assertEqual(code, 0)
            seen.extend(r["id"] for r in data["items"])
            if data["next_after"] is None:
                break
            after = data["next_after"]
        self.assertEqual(seen, expected)

    def test_stable_after_cursor_does_not_skip_when_pending_shrinks(self):
        _, first = self.cli("index", self.directory, "--limit", "1", "--status", "pending")
        uid = first["items"][0]["id"]
        updated = review.record(self.index, self.ledger, {"dispositions": [
            {"id": uid, "status": "explained", "reason": "Inspected the before/after source"}]})
        write_json(str(Path(self.directory) / "review.json"), updated)
        _, second = self.cli("index", self.directory, "--limit", "1", "--status", "pending",
                             "--after", first["next_after"])
        self.assertEqual(second["items"][0]["id"], sorted(self.index["items"])[1])

    def test_pending_batches_resume_past_first_page_and_account_for_all_kinds(self):
        # More than one page of implementation-only changes; no named feature
        # and no classifier score are needed to keep them in the work queue.
        for side, root in self.index["inputs"]["source_roots"].items():
            for i in range(35):
                Path(root, f"engine/unit-{i:02}.cc").write_text(f"// {side} {i}\n")
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        index, _ = review.load(self.directory)
        expected = set(index["items"])
        seen = []
        decision_path = str(Path(self.tmp.name) / "batch.json")
        while True:
            _, batch = self.cli("index", self.directory, "--status", "pending", "--limit", "10")
            if not batch["items"]:
                break
            ids = [row["id"] for row in batch["items"]]
            self.assertTrue(set(ids).isdisjoint(seen))
            seen.extend(ids)
            # This tests accounting, not the truth of an agent explanation.
            write_json(decision_path, {"dispositions": [
                {"id": uid, "status": "explained", "reason": "Synthetic batching exercise only"}
                for uid in ids]})
            _, saved = self.cli("record", self.directory, "--file", decision_path)
            self.assertEqual(saved["counts"].get("pending", 0), len(expected) - len(seen))
            self.assertEqual(sum(g["total"] for g in saved["by_kind"].values()), len(expected))
            for kind, group in saved["by_kind"].items():
                self.assertEqual(sum(group["counts"].values()), group["total"])
                self.assertEqual(group["counts"].get("pending", 0), sum(
                    item["kind"] == kind and uid not in seen for uid, item in index["items"].items()))
            if len(seen) == 10:
                self.assertFalse(saved["accounting_complete"])
                with redirect_stderr(io.StringIO()):
                    code, _ = self.cli("render", self.directory, "--require-complete")
                self.assertEqual(code, 1)
                self.assertFalse(Path(self.directory, "review.md").exists())
        self.assertEqual(set(seen), expected)
        self.assertGreater(len(seen), 30)
        self.assertEqual(self.cli("check", self.directory)[0], 0)
        self.assertEqual(self.cli("render", self.directory, "--require-complete")[0], 0)

    def test_context_payload_and_long_string_inspection_are_bounded(self):
        from chromiumdiff.review_cli import _leaves
        value = "a" * 8000
        rows = list(_leaves({"x": value}))
        actual, cursor = [], 0
        while True:
            result = review.page(rows, cursor, max_chars=2000)
            self.assertLessEqual(len(json.dumps(result)), 2000)
            actual.extend(r["value"] for r in result["items"])
            if result["next_cursor"] is None:
                break
            cursor = result["next_cursor"]
        self.assertEqual("".join(actual), value)

    def test_unknown_ids_and_primary_overlap_fail_atomically(self):
        with self.assertRaisesRegex(ValueError, "unknown item"):
            review.record(self.index, self.ledger, {"events": [event(["unknown"])]})
        uid = self.report.findings[0].uid
        with self.assertRaisesRegex(ValueError, "multiple events"):
            review.record(self.index, self.ledger, {"events": [event([uid], id="one"), event([uid], id="two")]})
        self.assertEqual(self.ledger["events"], [])

    def test_misspelled_patch_fields_are_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "accepts only"):
            review.record(self.index, self.ledger, {"event": []})

    def test_identical_edits_to_both_source_sides_invalidate_inventory(self):
        for side in ("from", "to"):
            Path(self.index["inputs"]["source_roots"][side], "engine/features.cc").write_text("changed both")
        self.assertTrue(review.verify_sources(self.index))

    def test_every_member_requires_its_own_evidence_explanation(self):
        ids = [f.uid for f in self.report.findings]
        e = event(ids)
        e["evidence"].pop()
        with self.assertRaisesRegex(ValueError, "no evidence explanation"):
            review.record(self.index, self.ledger, {"events": [e]})

    def test_event_ids_are_stable_and_splits_release_previous_members(self):
        ids = [f.uid for f in self.report.findings]
        first = review.record(self.index, self.ledger, {"events": [event(ids)]})
        reversed_members = review.record(self.index, self.ledger, {"events": [event(ids[::-1])]})
        self.assertEqual(first["events"][0]["id"], reversed_members["events"][0]["id"])
        split = review.record(self.index, first, {"remove_events": [first["events"][0]["id"]],
                                                 "events": [event(ids[:1])]})
        self.assertNotIn(ids[1], split["dispositions"])

    def test_provisional_and_unresolved_cannot_pass_completion(self):
        decisions = [{"id": uid, "status": "explained", "reason": "Source examined"}
                     for uid in self.index["items"]]
        done = review.record(self.index, self.ledger, {"dispositions": decisions})
        self.assertTrue(review.check(self.index, done)["accounting_complete"])
        uid = self.report.findings[0].uid
        provisional = review.record(self.index, done, {"events": [event([uid], status="provisional")]})
        self.assertFalse(review.check(self.index, provisional)["accounting_complete"])
        self.assertIn("PARTIAL", review.render(self.index, provisional))
        unresolved = review.record(self.index, done, {"dispositions": [
            {"id": uid, "status": "unresolved", "reason": "Need consumer evidence"}]})
        self.assertFalse(review.check(self.index, unresolved)["accounting_complete"])

    def test_evidence_change_invalidates_and_refresh_archives_decisions(self):
        uid = self.report.findings[0].uid
        done = review.record(self.index, self.ledger, {"events": [event([uid])]})
        write_json(str(Path(self.directory) / "review.json"), done)
        self.report.findings[0].enrichment["gerrit"] = {"changes": [{"number": 123}]}
        write_json(self.path, self.report.to_dict())
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            review.load(self.directory)
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        _, new = review.load(self.directory)
        self.assertEqual(new["events"][0]["status"], "provisional")
        self.assertEqual(new["events"][0]["items"], [uid])
        self.assertEqual(new["history"][0]["events"], done["events"])

    def test_context_refresh_preserves_unrelated_work_and_invalidates_connected_event(self):
        uid = self.report.findings[-1].uid
        other = "file:engine/work.cc"
        done = review.record(self.index, self.ledger, {"events": [event([uid]), event([other])]})
        write_json(str(Path(self.directory) / "review.json"), done)
        self.report.findings[0].enrichment["gerrit"] = {"changes": [{"number": 99}]}
        write_json(self.path, self.report.to_dict())
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        _, updated = review.load(self.directory)
        status = {e["items"][0]: e["status"] for e in updated["events"]}
        # Unchanged gate and feature bridge connect the other finding.
        self.assertEqual(status, {uid: "provisional", other: "confirmed"})

    def test_source_change_resets_baseline_instead_of_preserving_conclusions(self):
        done = review.record(self.index, self.ledger, {"events": [event([self.report.findings[0].uid])]})
        write_json(str(Path(self.directory) / "review.json"), done)
        Path(self.index["inputs"]["source_roots"]["to"], "engine/work.cc").write_text("new baseline")
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        _, updated = review.load(self.directory)
        self.assertEqual(updated["events"], [])
        self.assertEqual(updated["history"][0]["events"], done["events"])

    def test_refresh_reopens_explained_decisions_and_keeps_new_leads_pending(self):
        uid = self.report.findings[0].uid
        done = review.record(self.index, self.ledger, {"dispositions": [
            {"id": uid, "status": "explained", "reason": "Old interpretation"}]})
        write_json(str(Path(self.directory) / "review.json"), done)
        self.report.findings[0].enrichment["context"] = {"new": "evidence"}
        self.report.summary["milestone_brief"] = [{"title": "Independent new lead"}]
        write_json(self.path, self.report.to_dict())
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        index, updated = review.load(self.directory)
        self.assertEqual(updated["dispositions"][uid]["status"], "unresolved")
        self.assertEqual(len(review.index_rows(index, updated, "pending", "brief:")), 1)

    def test_rank_change_and_identical_refresh_preserve_decisions(self):
        before = review.report_digest(self.report)
        self.report.findings.reverse()
        self.report.findings[0].score = 999
        self.report.findings[0].bucket = "contract"
        self.assertEqual(review.report_digest(self.report), before)
        uid = self.report.findings[0].uid
        done = review.record(self.index, self.ledger, {"events": [event([uid])]})
        write_json(str(Path(self.directory) / "review.json"), done)
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        _, new = review.load(self.directory)
        self.assertEqual(new, done)

    def test_source_is_version_qualified_and_hash_pinned(self):
        old = review.source_rows(self.index, "from", "engine/work.cc")
        new = review.source_rows(self.index, "to", "engine/work.cc")
        self.assertIn("return 4", old["items"][0]["text"])
        self.assertIn("return 12", new["items"][0]["text"])
        self.assertNotEqual(old["provenance"]["from"]["sha256"], new["provenance"]["to"]["sha256"])
        uid = self.report.findings[0].uid
        e = event([uid])
        e["evidence"].append({"source": {"side": "to", **new["provenance"]["to"]},
                              "supports": "Consumer now selects 12"})
        recorded = review.record(self.index, self.ledger, {"events": [e]})
        Path(self.index["inputs"]["source_roots"]["to"], "engine/work.cc").write_text("changed")
        self.assertTrue(review.validate(self.index, recorded))
        self.assertTrue(review.verify_sources(self.index))

    def test_source_cannot_escape_cache_or_follow_external_symlink(self):
        for path in ("../report.json", "/etc/passwd", "x/../../a", "x\\a", "x//a"):
            with self.assertRaises(ValueError):
                review.source_rows(self.index, "to", path)
        tree = Path(self.index["inputs"]["source_roots"]["to"])
        (tree / "outside").symlink_to(Path(self.tmp.name))
        with self.assertRaises(ValueError):
            review.source_rows(self.index, "to", "outside/report.json")

    def test_missing_side_is_not_diffed_as_an_empty_file(self):
        result = review.source_rows(self.index, "diff", "ui/extra.ts")
        self.assertEqual(result["items"], [])
        self.assertIn("Not cached", result["warning"])

    def test_supplemental_fetch_does_not_inflate_baseline_inventory(self):
        with patch("chromiumdiff.review.GitilesSource.fetch_file", return_value=b"int extra = 1;\n"):
            result = review.source_rows(self.index, "to", "unfetched/body.cc", fetch=True)
        self.assertEqual(result["provenance"]["to"]["origin"], "fetched_supplement")
        self.assertEqual(review.verify_sources(self.index), [])
        again = review.source_rows(self.index, "to", "unfetched/body.cc")
        self.assertEqual(again["provenance"]["to"]["origin"], "supplemental_cache")

    def test_missing_snapshot_is_explicit_and_does_not_read_other_target_set(self):
        Path(snapshot_path(self.cache, self.old.ref, "default")).unlink()
        review.initialize(self.path, self.directory, self.cache, refresh=True)
        index, _ = review.load(self.directory)
        self.assertTrue(index["warnings"])
        self.assertNotIn("from", index["graph"]["nodes"]["base_feature:Orbital"]["sides"])

    def test_cli_check_is_nonzero_for_partial_and_render_preserves_raw_report(self):
        before = Path(self.path).read_bytes()
        code, result = self.cli("check", self.directory)
        self.assertEqual(code, 1)
        self.assertFalse(result["accounting_complete"])
        code, result = self.cli("render", self.directory)
        self.assertEqual(code, 0)
        self.assertIn("PARTIAL", Path(result["output"]).read_text())
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_strict_render_rejects_each_unfinished_state_without_replacing_output(self):
        done = review.record(self.index, self.ledger, {"dispositions": [
            {"id": uid, "status": "explained", "reason": "Synthetic accounting exercise only"}
            for uid in self.index["items"]]})
        uid = self.report.findings[0].uid
        states = {
            "pending": self.ledger,
            "unresolved": review.record(self.index, done, {"dispositions": [
                {"id": uid, "status": "unresolved", "reason": "Need before/after consumer evidence"}]}),
            "provisional": review.record(self.index, done, {"events": [
                event([uid], status="provisional")]}),
        }
        output = Path(self.directory, "review.md")
        output.write_text("Existing saved report\n")
        before = output.read_bytes()
        for name, ledger in states.items():
            with self.subTest(state=name):
                write_json(str(Path(self.directory, "review.json")), ledger)
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    code, _ = self.cli("render", self.directory, "--require-complete")
                self.assertEqual(code, 1)
                self.assertIn("review is incomplete", stderr.getvalue())
                self.assertEqual(output.read_bytes(), before)

    def test_documented_cli_end_to_end_with_record_and_evaluation(self):
        uid = self.report.findings[0].uid
        code, inspected = self.cli("inspect", self.directory, uid, "--limit", "200")
        self.assertEqual(code, 0)
        self.assertTrue(any(r["pointer"].endswith("/change/before/route") for r in inspected["items"]))
        code, linked = self.cli("related", self.directory, uid)
        self.assertEqual(code, 0)
        self.assertTrue(linked["items"])
        code, source = self.cli("source", self.directory, "engine/work.cc", "--side", "diff")
        self.assertEqual(code, 0)
        self.assertTrue(any("+int capacity" in r["text"] for r in source["items"]))
        decisions = {"events": [event([uid])], "dispositions": [
            {"id": other, "status": "explained", "reason": "Synthetic accounting exercise only"}
            for other in self.index["items"] if other != uid]}
        patch_path = str(Path(self.tmp.name) / "decisions.json")
        write_json(patch_path, decisions)
        code, recorded = self.cli("record", self.directory, "--file", patch_path)
        self.assertEqual(code, 0)
        self.assertTrue(recorded["accounting_complete"])
        code, events = self.cli("events", self.directory)
        self.assertEqual(code, 0)
        self.assertEqual(events["items"][0]["member_count"], 1)
        code, detail = self.cli("inspect", self.directory, events["items"][0]["id"])
        self.assertEqual(code, 0)
        self.assertTrue(any(r["pointer"] == "/mechanism" for r in detail["items"]))
        self.assertEqual(self.cli("check", self.directory)[0], 0)
        code, output = self.cli("render", self.directory)
        self.assertEqual(code, 0)
        text = Path(output["output"]).read_text()
        self.assertIn("https://chromium.googlesource.com/chromium/src/+/refs/tags/1.0.0.0/ui/route.ts#2", text)
        gold_path = str(Path(self.tmp.name) / "gold.json")
        write_json(gold_path, {"provenance": "synthetic CLI contract test, not semantic adjudication",
                               "events": [{"id": "one", "items": [uid]}]})
        code, evaluated = self.cli("evaluate", gold_path, self.directory)
        self.assertEqual(code, 0)
        self.assertEqual(evaluated["trials"][0]["exact_event_membership_recall"], 1)


class TestGitInventory(unittest.TestCase):
    def test_exact_commits_find_unparsed_files_without_touching_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", "-q", root], check=True)
            def git(*args):
                return subprocess.run(["git", "-C", root, *args], check=True,
                                      stdout=subprocess.PIPE).stdout.decode().strip()
            Path(root, "ordinary.cc").write_text("int f() { return 1; }\n")
            git("add", "ordinary.cc")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "before")
            old = git("rev-parse", "HEAD")
            Path(root, "ordinary.cc").write_text("int f() { return 2; }\n")
            Path(root, "unknown.grammar").write_text("new capability declaration")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "after")
            new = git("rev-parse", "HEAD")
            Path(root, "ordinary.cc").write_text("user's uncommitted work\n")
            before_status = git("status", "--porcelain")
            rows, scope = review.source_inventory({}, root, {"from": old, "to": new})
            self.assertEqual({r["path"] for r in rows}, {"ordinary.cc", "unknown.grammar"})
            self.assertEqual(git("status", "--porcelain"), before_status)
            index = {"inputs": {"source_scope": scope, "source_roots": {"from": root, "to": root}}}
            data, origin = review.source_bytes(index, "to", "ordinary.cc")
            self.assertEqual(data, b"int f() { return 2; }\n")
            self.assertEqual(origin, "git")
            self.assertEqual(review.source_bytes(index, "from", "unknown.grammar"), (None, "git_absent"))


class TestClusterRefresh(unittest.TestCase):
    def test_refresh_clears_stale_membership_and_retains_more_than_25(self):
        findings = []
        for i in range(31):
            for j in range(2):
                f = Finding(Change("added", "pref", f"group{i}-{j}", f"group{i}-{j}"))
                f.enrichment["gerrit"] = {"changes": [{"number": i + 1, "match": "exact"}]}
                findings.append(f)
        r = Report("old", "new", findings)
        cluster.refresh(r)
        self.assertEqual(len(r.summary["clusters"]), 31)
        findings[0].enrichment.pop("gerrit")
        cluster.refresh(r)
        self.assertNotIn("cluster", findings[0].enrichment)
        self.assertNotIn("cluster", findings[1].enrichment)

    def test_cluster_ids_and_members_are_input_order_independent(self):
        findings = [Finding(Change("added", "pref", x, x), enrichment={
            "gerrit": {"changes": [{"number": 10, "match": "exact"}]}})
                    for x in ("c", "a", "b")]
        first = Report("old", "new", findings)
        cluster.refresh(first)
        second = Report("old", "new", findings[::-1])
        cluster.refresh(second)
        self.assertEqual(first.summary, second.summary)


class TestReviewEvaluation(unittest.TestCase):
    def setUp(self):
        self.gold = {"provenance": "independent source inspection",
                     "events": [{"id": "migration", "items": ["a", "b"], "critical": True},
                                {"id": "new-contract", "items": ["c"]}]}
        self.index = {"fingerprint": "frozen", "items": {x: {} for x in "abcd"}}

    def trial(self, *groups):
        return {"events": [event(list(g)) for g in groups]}

    def test_good_partitions_are_consistent_despite_wording_and_event_ids(self):
        from chromiumdiff.review_eval import evaluate
        result = evaluate(self.gold, [("one", self.index, self.trial("ab", "c")),
                                       ("two", self.index, self.trial("c", "ba"))])
        self.assertEqual(result["trials"][0]["exact_event_membership_recall"], 1)
        self.assertEqual(result["repeatability"][0]["event_partition_jaccard"], 1)
        self.assertEqual(result["semantic_accuracy"], "not automatically measured")

    def test_one_mega_event_is_not_full_event_recall(self):
        from chromiumdiff.review_eval import evaluate
        result = evaluate(self.gold, [("merged", self.index, self.trial("abc"))])["trials"][0]
        self.assertEqual(result["finding_recall"], 1)
        self.assertEqual(result["exact_event_membership_recall"], 0)
        self.assertEqual(result["overmerged_groups"], 1)
        self.assertEqual(result["missed_critical_event_ids"], ["migration"])

    def test_split_members_and_unadjudicated_extra_event_are_visible(self):
        from chromiumdiff.review_eval import evaluate
        result = evaluate(self.gold, [("split", self.index, self.trial("a", "b", "c", "d"))])["trials"][0]
        self.assertEqual(result["split_gold_events"], 1)
        self.assertEqual(result["unadjudicated_events_outside_gold"], 1)

    def test_different_inputs_cannot_claim_repeatability(self):
        from chromiumdiff.review_eval import evaluate
        with self.assertRaisesRegex(ValueError, "identical pinned"):
            evaluate(self.gold, [("one", self.index, self.trial("ab", "c")),
                                 ("two", {**self.index, "fingerprint": "other"}, self.trial("ab", "c"))])


class TestSkillContract(unittest.TestCase):
    def test_stdlib_frontmatter_links_and_python39_syntax(self):
        import ast
        import re
        root = Path(__file__).resolve().parent.parent
        skill = root / "skills/analyzing-chromium-upgrades/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        fields = dict(line.split(": ", 1) for line in frontmatter.strip().splitlines())
        self.assertEqual(fields["name"], "analyzing-chromium-upgrades")
        self.assertTrue(fields["description"])
        for relative in re.findall(r"\]\((reference/[^)]+)\)", text):
            self.assertTrue((skill.parent / relative).is_file(), relative)
        for name in ("evidence", "review", "review_cli", "review_eval", "review_trials"):
            ast.parse((root / "chromiumdiff" / (name + ".py")).read_text(), feature_version=(3, 9))


if __name__ == "__main__":
    unittest.main()
