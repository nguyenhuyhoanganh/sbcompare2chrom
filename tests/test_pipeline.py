"""Diff, impact, budgeting and AI-plumbing tests.

These cover the judgement calls -- what counts as a change, what counts as
evidence, what gets escalated -- because those are the parts that decide
whether the output is worth reading.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chromedrift.ai.budget import Budget, estimate_tokens, pack
from chromedrift.ai.client import parse_json_response
from chromedrift.diff import diff_snapshots
from chromedrift.impact import score_all, score_change
from chromedrift.model import Fact, Snapshot
from chromedrift.sbprofile import Area, TouchSet, _symbols_from_hunks


def feature(name, state, var=None, form="macro2", path="content/features.cc"):
    return Fact(
        kind="base_feature", key=name, name=name, path=path,
        attrs={
            "var": var or ("k" + name),
            "default_state": state,
            "platform_state": {"android": state, "windows": state},
            "declared_form": form,
        },
    )


def blink(name, android_status):
    return Fact(
        kind="blink_runtime_feature", key=name, name=name,
        path="runtime_enabled_features.json5",
        attrs={
            "status": android_status,
            "android_status": android_status,
            "platform_status": {"android": android_status, "windows": android_status},
        },
    )


def snap(ref, facts):
    return Snapshot(ref=ref, facts=facts, milestone=int(ref.split(".")[0]))


class TestDiffSemantics(unittest.TestCase):
    def test_syntax_only_change_is_not_a_change(self):
        """A declaration rewritten by the macro migration must diff as equal."""
        old = snap("139.0.0.0", [feature("Foo", "enabled", form="macro3")])
        new = snap("143.0.0.0", [feature("Foo", "enabled", form="macro2")])
        self.assertEqual(diff_snapshots(old, new), [])

    def test_moving_a_declaration_is_reported_quietly(self):
        old = snap("139.0.0.0", [feature("Foo", "enabled", path="a/features.cc")])
        new = snap("143.0.0.0", [feature("Foo", "enabled", path="b/features.cc")])
        changes = diff_snapshots(old, new)
        self.assertEqual(len(changes), 1)
        self.assertIn("declaration_moved", changes[0].signals)
        self.assertLess(changes[0].severity, 45)

    def test_android_default_flip_is_high_severity(self):
        old = snap("139.0.0.0", [feature("Foo", "disabled")])
        new = snap("143.0.0.0", [feature("Foo", "enabled")])
        change = diff_snapshots(old, new)[0]
        self.assertIn("android_enabled_by_default", change.signals)
        self.assertGreaterEqual(change.severity, 70)

    def test_platform_divergent_flip_scored_on_our_platform(self):
        """Enabled on desktop, still off on Android, is not a flip for us."""
        old_fact = feature("Foo", "disabled")
        new_fact = feature("Foo", "disabled")
        new_fact.attrs["default_state"] = "enabled"
        new_fact.attrs["platform_state"] = {"android": "disabled", "windows": "enabled"}
        change = diff_snapshots(snap("139.0.0.0", [old_fact]),
                                snap("143.0.0.0", [new_fact]))[0]
        self.assertNotIn("android_enabled_by_default", change.signals)
        self.assertIn("default_flip_on", change.signals)

    def test_retired_killswitch_is_not_an_api_removal(self):
        """Blink deletes flags after features ship.

        On the real M139->M143 diff, 170 of 202 removed runtime features had
        been stable. Treating those as API removals would bury the report.
        """
        old = snap("139.0.0.0", [blink("Shipped", "stable")])
        new = snap("143.0.0.0", [])
        change = diff_snapshots(old, new)[0]
        self.assertIn("killswitch_retired", change.signals)
        self.assertNotIn("web_api_removed", change.signals)
        self.assertLess(change.severity, 50)

    def test_retired_flag_is_classified_by_its_last_state(self):
        """A removed base::Feature is cleanup, not a lost feature.

        On the real M148->M151 Windows diff, 90 flags were removed, split 45/45
        between shipped-then-retired and never-shipped. One label for both made
        half the list false alarms.
        """
        on = feature("Shipped", "enabled")
        off = feature("Abandoned", "disabled")
        old = snap("148.0.0.0", [on, off])
        new = snap("151.0.0.0", [])
        by_key = {c.key: c for c in diff_snapshots(old, new, platform="windows")}

        self.assertIn("flag_retired_on", by_key["Shipped"].signals)
        self.assertIn("flag_retired_off", by_key["Abandoned"].signals)
        # Neither is a user-visible change on its own.
        for c in by_key.values():
            self.assertNotIn("feature_deleted", c.signals)
            self.assertLess(c.severity, 65)

    def test_retired_flag_still_reaches_must_fix_with_local_evidence(self):
        """Cleanup upstream is still a build break if we name the symbol."""
        old = snap("148.0.0.0", [feature("Shipped", "enabled")])
        new = snap("151.0.0.0", [])
        change = diff_snapshots(old, new, platform="windows")[0]
        self.assertEqual(
            score_change(change, TouchSet(platform="windows")).bucket, "fyi")
        self.assertEqual(
            score_change(change, TouchSet(platform="windows",
                                          symbols={"kShipped"})).bucket,
            "must_fix")

    def test_experimental_reaching_stable_is_shipped(self):
        old = snap("139.0.0.0", [blink("Api", "experimental")])
        new = snap("143.0.0.0", [blink("Api", "stable")])
        change = diff_snapshots(old, new)[0]
        self.assertIn("web_api_shipped", change.signals)

    def test_feature_string_rename_detected_via_variable(self):
        """Same C++ variable, different Finch string: a silent rename."""
        old = snap("139.0.0.0", [feature("FedCmIdPregistration", "disabled",
                                         var="kFedCmIdPRegistration")])
        new = snap("143.0.0.0", [feature("FedCmIdPRegistration", "disabled",
                                         var="kFedCmIdPRegistration")])
        changes = diff_snapshots(old, new)
        self.assertEqual(len(changes), 1)
        self.assertIn("feature_string_renamed", changes[0].signals)
        self.assertEqual(changes[0].deltas["value"],
                         ["FedCmIdPregistration", "FedCmIdPRegistration"])

    def test_pref_rename_pairs_removal_and_addition(self):
        old = snap("139.0.0.0", [Fact(kind="pref", key="old.path", name="old.path",
                                      path="pref_names.h", attrs={"var": "kHomePage"})])
        new = snap("143.0.0.0", [Fact(kind="pref", key="new.path", name="new.path",
                                      path="pref_names.h", attrs={"var": "kHomePage"})])
        changes = diff_snapshots(old, new)
        self.assertEqual(len(changes), 1)
        self.assertIn("pref_renamed", changes[0].signals)


class TestSnapshotScoping(unittest.TestCase):
    """Guards against the shared tree cache leaking scope between target sets."""

    def test_extraction_is_scoped_to_declared_targets(self):
        import tempfile

        from chromedrift.extract import run_on_tree

        with tempfile.TemporaryDirectory() as root:
            wanted = os.path.join(root, "content", "public", "common")
            other = os.path.join(root, "net", "base")
            os.makedirs(wanted)
            os.makedirs(other)
            decl = 'BASE_FEATURE(kWanted, base::FEATURE_ENABLED_BY_DEFAULT);'
            with open(os.path.join(wanted, "content_features.cc"), "w",
                      encoding="utf-8") as fh:
                fh.write(decl)
            # Left behind by an earlier, wider run against the same ref.
            with open(os.path.join(other, "features.cc"), "w",
                      encoding="utf-8") as fh:
                fh.write('BASE_FEATURE(kLeftover, base::FEATURE_ENABLED_BY_DEFAULT);')

            unscoped, _ = run_on_tree(root)
            self.assertEqual({f.key for f in unscoped}, {"Wanted", "Leftover"})

            scoped, _ = run_on_tree(
                root, allow_paths={"content/public/common/content_features.cc"})
            self.assertEqual({f.key for f in scoped}, {"Wanted"})

    def test_prefix_targets_scope_a_whole_subtree(self):
        import tempfile

        from chromedrift.extract import run_on_tree

        with tempfile.TemporaryDirectory() as root:
            deep = os.path.join(root, "net", "base")
            os.makedirs(deep)
            with open(os.path.join(deep, "features.cc"), "w",
                      encoding="utf-8") as fh:
                fh.write('BASE_FEATURE(kNet, base::FEATURE_ENABLED_BY_DEFAULT);')
            hit, _ = run_on_tree(root, allow_prefixes={"net/"})
            miss, _ = run_on_tree(root, allow_prefixes={"media/"})
            self.assertEqual({f.key for f in hit}, {"Net"})
            self.assertEqual(miss, [])

    def test_diff_refuses_mismatched_target_sets(self):
        old = snap("139.0.0.0", [feature("Foo", "disabled")])
        new = snap("143.0.0.0", [feature("Foo", "enabled")])
        old.meta = {"target_set": "minimal"}
        new.meta = {"target_set": "default"}
        with self.assertRaises(ValueError) as ctx:
            diff_snapshots(old, new)
        self.assertIn("target set", str(ctx.exception))


class TestImpactScoring(unittest.TestCase):
    def setUp(self):
        self.old = snap("139.0.0.0", [feature("Foo", "disabled")])
        self.new = snap("143.0.0.0", [feature("Foo", "enabled")])
        self.change = diff_snapshots(self.old, self.new)[0]

    def test_no_evidence_stays_out_of_must_fix(self):
        finding = score_change(self.change, TouchSet())
        self.assertNotEqual(finding.bucket, "must_fix")

    def test_symbol_evidence_promotes_to_must_fix(self):
        touch = TouchSet(symbols={"kFoo"})
        finding = score_change(self.change, touch)
        self.assertEqual(finding.bucket, "must_fix")
        self.assertIn("kFoo", finding.matched_symbols)

    def test_path_evidence_alone_is_only_review(self):
        """Patching a file that declares hundreds of features proves little."""
        touch = TouchSet(modified_paths={"content/features.cc"})
        finding = score_change(self.change, touch)
        self.assertEqual(finding.bucket, "review")

    def test_not_compiled_on_our_platform_is_scored_down(self):
        fact = feature("Foo", "enabled")
        fact.attrs["platform_state"] = {"android": "not_compiled", "windows": "enabled"}
        change = diff_snapshots(snap("139.0.0.0", [feature("Foo", "disabled")]),
                                snap("143.0.0.0", [fact]))[0]
        plain = score_change(change, TouchSet(platform="windows")).score
        ours = score_change(change, TouchSet(platform="android")).score
        self.assertLess(ours, plain)

    def test_area_weight_and_reasons_are_explicit(self):
        touch = TouchSet(symbols={"kFoo"},
                         areas=[Area(id="media", title="Media", weight=90,
                                     symbols=["Foo"])])
        finding = score_change(self.change, touch)
        self.assertIn("media", finding.areas)
        self.assertTrue(any("owned area" in r for r in finding.reasons))
        # Every adjustment must be traceable.
        self.assertTrue(all(r for r in finding.reasons))

    def test_new_capability_goes_to_opportunity_not_review(self):
        old = snap("139.0.0.0", [])
        new = snap("143.0.0.0", [blink("NewApi", "stable")])
        findings = score_all(diff_snapshots(old, new), TouchSet())
        self.assertEqual(findings[0].bucket, "opportunity")


class TestAreaRouting(unittest.TestCase):
    """Areas route findings to teams; the leftover must stay visible."""

    def _finding(self, fact, touch):
        old = snap("148.0.0.0", [])
        new = snap("151.0.0.0", [fact])
        return score_change(diff_snapshots(old, new, platform="windows")[0], touch)

    def test_matches_by_pref_prefix(self):
        pref = Fact(kind="pref", key="download.default_directory",
                    name="download.default_directory", path="pref_names.h",
                    attrs={"var": "kDownloadDefaultDirectory"})
        touch = TouchSet(platform="windows",
                         areas=[Area(id="downloads", prefs=["download."])])
        self.assertEqual(self._finding(pref, touch).areas, ["downloads"])

    def test_matches_by_flag_prefix_on_variable_or_name(self):
        touch = TouchSet(platform="windows",
                         areas=[Area(id="downloads", flags=["kDownload"])])
        self.assertEqual(
            self._finding(feature("DownloadLater", "enabled"), touch).areas,
            ["downloads"])

    def test_matches_by_fact_kind(self):
        """Cross-cutting infrastructure belongs to no product but needs an owner."""
        method = Fact(kind="mojo_method", key="blink.mojom.Foo.Bar", name="Bar",
                      path="a.mojom", attrs={"interface": "blink.mojom.Foo",
                                             "signature": "Bar()"})
        touch = TouchSet(platform="windows",
                         areas=[Area(id="ipc", kind="infra",
                                     kinds=["mojo_method"])])
        self.assertEqual(self._finding(method, touch).areas, ["ipc"])

    def test_unmatched_finding_has_no_area(self):
        touch = TouchSet(platform="windows",
                         areas=[Area(id="downloads", paths=["components/download/"])])
        self.assertEqual(self._finding(feature("Unrelated", "enabled"), touch).areas, [])

    def test_coverage_counts_the_leftover(self):
        from chromedrift.impact import area_coverage

        touch = TouchSet(platform="windows",
                         areas=[Area(id="downloads", flags=["kDownload"])])
        mine = self._finding(feature("DownloadLater", "enabled"), touch)
        orphan = self._finding(feature("Unrelated", "enabled"), touch)
        coverage = area_coverage([mine, orphan], touch)

        self.assertEqual(coverage["areas"]["downloads"]["total"], 1)
        self.assertEqual(coverage["unassigned"]["total"], 1)
        self.assertGreater(coverage["unassigned"]["top_score"], 0)


class TestReportFiltering(unittest.TestCase):
    """Filtering happens at render time, never before analysis."""

    def _report(self):
        from chromedrift.model import Change, Finding, Report

        def mk(name, areas, score):
            return Finding(
                change=Change(change_type="modified", kind="base_feature",
                              key=name, name=name),
                areas=areas, score=score, bucket="review")

        return Report(from_ref="148.0.0.0", to_ref="151.0.0.0",
                      findings=[mk("A", ["downloads"], 70),
                                mk("B", ["ipc"], 80),
                                mk("C", [], 90)])

    def test_filter_keeps_only_that_area(self):
        sliced = self._report().filtered("downloads")
        self.assertEqual([f.change.key for f in sliced.findings], ["A"])

    def test_unassigned_is_addressable(self):
        """The leftover must be reachable, or it silently disappears."""
        sliced = self._report().filtered("_unassigned")
        self.assertEqual([f.change.key for f in sliced.findings], ["C"])

    def test_filtering_does_not_mutate_the_full_report(self):
        report = self._report()
        report.filtered("downloads")
        self.assertEqual(len(report.findings), 3)

    def test_filter_records_what_it_hid(self):
        sliced = self._report().filtered("ipc")
        self.assertEqual(sliced.summary["filtered_to_area"], "ipc")
        self.assertEqual(sliced.summary["filtered_from_total"], 3)

    def test_no_area_returns_everything(self):
        report = self._report()
        self.assertIs(report.filtered(None), report)


class TestPatchEvidence(unittest.TestCase):
    def test_symbols_come_from_hunk_bodies(self):
        patch = (
            "--- a/content/features.cc\n"
            "+++ b/content/features.cc\n"
            "@@ -1,3 +1,4 @@\n"
            " BASE_FEATURE(kExisting, base::FEATURE_DISABLED_BY_DEFAULT);\n"
            "+  overrides->push_back({&features::kMyFeature, kOff});\n"
            "-  RemovedSymbol();\n"
        )
        symbols = _symbols_from_hunks(patch)
        self.assertIn("kMyFeature", symbols)
        self.assertIn("kExisting", symbols)   # context lines count as evidence
        self.assertIn("RemovedSymbol", symbols)
        # The +++/--- headers are not hunk content.
        self.assertNotIn("content/features.cc", symbols)


class TestBudget(unittest.TestCase):
    def test_input_budget_reserves_output_space(self):
        budget = Budget(context_window=200_000, max_output_tokens=8_000,
                        reserve_tokens=4_000)
        available = budget.input_budget()
        self.assertLess(available, 200_000 - 8_000 - 4_000)
        self.assertGreater(available, 150_000)

    def test_pack_respects_the_budget(self):
        items = ["x" * 350 for _ in range(10)]     # ~100 tokens each
        batches = pack(items, lambda s: s, budget_tokens=250)
        self.assertGreater(len(batches), 1)
        for batch in batches:
            self.assertLessEqual(len(batch), 3)

    def test_oversized_item_is_isolated_not_dropped(self):
        items = ["small", "y" * 100_000, "small"]
        batches = pack(items, lambda s: s, budget_tokens=100)
        flattened = [i for b in batches for i in b]
        self.assertEqual(len(flattened), 3)

    def test_estimate_is_monotonic(self):
        self.assertGreater(estimate_tokens("a" * 1000), estimate_tokens("a" * 100))
        self.assertEqual(estimate_tokens(""), 0)


class TestWindowsConsoleEncoding(unittest.TestCase):
    """Reports must survive a non-UTF-8 stdout.

    On Windows, redirected output falls back to the ANSI code page (cp1252 for
    most installs), and every report contains arrows and em-dashes. Before the
    fix this failed with "'charmap' codec can't encode character '\\u2192'".
    """

    def test_report_renders_to_a_cp1252_stdout(self):
        import subprocess
        import tempfile

        from chromedrift.model import Change, Finding, Report, write_json

        change = Change(change_type="modified", kind="base_feature",
                        key="Foo", name="Foo",
                        deltas={"default_state": ["disabled", "enabled"]},
                        signals=["android_enabled_by_default"], severity=75)
        report = Report(from_ref="139.0.0.0", to_ref="143.0.0.0",
                        findings=[Finding(change=change, score=75,
                                          bucket="review")],
                        meta={"platform": "android"})

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            write_json(path, report.to_dict())

            env = dict(os.environ, PYTHONIOENCODING="cp1252")
            result = subprocess.run(
                [sys.executable, "-m", "chromedrift", "report", path,
                 "--format", "md"],
                cwd=repo_root, env=env, capture_output=True, timeout=60)

        self.assertEqual(result.returncode, 0,
                         result.stderr.decode("utf-8", "replace"))
        self.assertIn("→", result.stdout.decode("utf-8", "replace"))


class TestResponseParsing(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_json_response('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        self.assertEqual(
            parse_json_response('```json\n{"a": 1}\n```'), {"a": 1})

    def test_json_wrapped_in_prose(self):
        parsed = parse_json_response(
            'Sure! Here is the analysis:\n{"assessments": []}\nHope that helps.')
        self.assertEqual(parsed, {"assessments": []})

    def test_bare_array_is_wrapped(self):
        self.assertEqual(parse_json_response('[{"id": "x"}]'),
                         {"assessments": [{"id": "x"}]})

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_json_response("no json at all"))
        self.assertIsNone(parse_json_response(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
