"""Diff, impact and reporting tests.

These cover the judgement calls -- what counts as a change, what counts as
evidence, what gets escalated -- because those are the parts that decide
whether the output is worth reading.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chromedrift.diff import diff_snapshots
from chromedrift.impact import score_all, score_change
from chromedrift.model import Fact, Report, Snapshot
from chromedrift.downstream import Area, TouchSet, _symbols_from_hunks


def feature(name, state, var=None, form="macro2", path="content/features.cc"):
    return Fact(
        kind="base_feature", key=name, name=name, path=path,
        attrs={
            "var": var or ("k" + name),
            "default_state": state,
            "platform_state": {"windows": state},
            "declared_form": form,
        },
    )


def blink(name, windows_status):
    return Fact(
        kind="blink_runtime_feature", key=name, name=name,
        path="runtime_enabled_features.json5",
        attrs={
            "status": windows_status,
            "windows_status": windows_status,
            "platform_status": {"windows": windows_status},
        },
    )


def snap(ref, facts):
    # A ref is not always a version: a fork snapshot is labelled by branch.
    head = ref.split(".")[0]
    return Snapshot(ref=ref, facts=facts,
                    milestone=int(head) if head.isdigit() else None)


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

    def test_default_flip_is_high_severity(self):
        old = snap("139.0.0.0", [feature("Foo", "disabled")])
        new = snap("143.0.0.0", [feature("Foo", "enabled")])
        change = diff_snapshots(old, new)[0]
        self.assertIn("enabled_by_default", change.signals)
        self.assertGreaterEqual(change.severity, 70)

    def test_flip_elsewhere_is_not_a_flip_for_us(self):
        """The global default moved; the Windows branch did not.

        Chromium wraps defaults in #if BUILDFLAG chains, so the global value
        and the shipped value routinely disagree. Only the shipped one is our
        change.
        """
        old_fact = feature("Foo", "disabled")
        new_fact = feature("Foo", "disabled")
        new_fact.attrs["default_state"] = "enabled"      # global moved
        new_fact.attrs["platform_state"] = {"windows": "disabled"}   # ours did not
        change = diff_snapshots(snap("139.0.0.0", [old_fact]),
                                snap("143.0.0.0", [new_fact]))[0]
        self.assertNotIn("enabled_by_default", change.signals)
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
        """A feature that never builds for us is not our problem."""
        builds = feature("Foo", "enabled")
        never = feature("Bar", "enabled")
        never.attrs["platform_state"] = {"windows": "not_compiled"}
        old = snap("139.0.0.0", [feature("Foo", "disabled"),
                                 feature("Bar", "disabled")])
        new = snap("143.0.0.0", [builds, never])
        scored = {c.key: score_change(c, TouchSet(platform="windows")).score
                  for c in diff_snapshots(old, new, platform="windows")}
        self.assertLess(scored["Bar"], scored["Foo"])

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


class TestForkMode(unittest.TestCase):
    """Same engine, opposite meanings.

    In an uprev a missing fact means Chromium cleaned up. Across a fork it
    means the vendor removed it -- a deliberate decision that must survive
    every rebase. Reading a fork comparison with uprev semantics scores every
    intentional divergence as upstream housekeeping.
    """

    def _diff(self, old_facts, new_facts, mode):
        from chromedrift.diff import diff_snapshots
        return diff_snapshots(snap("148.0.0.0", old_facts),
                              snap("148.0.0.0", new_facts),
                              platform="windows", mode=mode)

    def test_removal_means_cleanup_upstream_but_deletion_in_a_fork(self):
        old = [feature("Shipped", "enabled")]
        uprev = self._diff(old, [], "uprev")[0]
        fork = self._diff(old, [], "fork")[0]

        self.assertIn("flag_retired_on", uprev.signals)
        self.assertIn("fork_dropped", fork.signals)
        # The fork case is the more serious of the two: we removed it on
        # purpose, and the next rebase brings it back.
        self.assertGreater(fork.severity, uprev.severity)

    def test_changed_default_is_an_override_in_fork_mode(self):
        old = [feature("Foo", "disabled")]
        new = [feature("Foo", "enabled")]
        fork = self._diff(old, new, "fork")[0]
        self.assertIn("fork_default_override", fork.signals)

    def test_addition_means_the_vendor_added_it(self):
        fork = self._diff([], [feature("VendorOnly", "enabled")], "fork")[0]
        self.assertIn("fork_added", fork.signals)
        self.assertNotIn("new_feature_on_by_default", fork.signals)

    def test_rename_pairing_is_disabled_across_a_fork(self):
        """Removal plus addition sharing a variable is a rename over time.

        Across a fork it means the vendor replaced one thing with another,
        which is two decisions, not one rename -- collapsing them hides one.
        """
        old = [Fact(kind="pref", key="old.path", name="old.path",
                    path="pref_names.h", attrs={"var": "kHomePage"})]
        new = [Fact(kind="pref", key="new.path", name="new.path",
                    path="pref_names.h", attrs={"var": "kHomePage"})]

        uprev = self._diff(old, new, "uprev")
        self.assertEqual(len(uprev), 1)
        self.assertIn("pref_renamed", uprev[0].signals)

        fork = self._diff(old, new, "fork")
        self.assertEqual(len(fork), 2)
        self.assertEqual({c.change_type for c in fork}, {"added", "removed"})

    def test_every_fork_signal_has_a_label_and_severity(self):
        from chromedrift.diff import FORK_LABELS, FORK_SIGNALS, SIGNAL_LABELS, SIGNAL_SEVERITY
        for name in FORK_SIGNALS:
            self.assertIn(name, SIGNAL_LABELS, name)
            self.assertIn(name, SIGNAL_SEVERITY, name)
        self.assertEqual(set(FORK_SIGNALS), set(FORK_LABELS))


class TestForkModeSurvivesTheDiff(unittest.TestCase):
    """The inversion has to hold all the way to the page a human reads.

    Every test above this one stops at `diff.py`, and for a while that was
    exactly where fork semantics stopped too: scoring, the model prompt and the
    report all kept their uprev wording, so a feature the vendor had added
    appeared under "New opportunity -- new capability we could adopt". The
    fork signals were right and everything downstream of them was wrong.
    """

    def _fork_findings(self, old_facts, new_facts):
        from chromedrift.model import MODE_FORK
        changes = diff_snapshots(snap("148.0.0.0", old_facts),
                                 snap("fork-main-dev", new_facts),
                                 mode=MODE_FORK)
        return score_all(changes, TouchSet(name="Fork", platform="windows"),
                         mode=MODE_FORK)

    def test_vendor_addition_is_not_an_opportunity(self):
        finding = self._fork_findings([], [feature("AcmeSauce", "enabled")])[0]
        self.assertIn("fork_added", finding.change.signals)
        # Our own shipped customization is not a capability on offer.
        self.assertNotEqual(finding.bucket, "opportunity")

    def test_no_finding_lands_in_opportunity_in_fork_mode(self):
        findings = self._fork_findings(
            [feature("Dropped", "enabled"), feature("Flipped", "enabled")],
            [feature("Flipped", "disabled"), feature("Added", "enabled")],
        )
        self.assertTrue(findings)
        self.assertEqual([f for f in findings if f.bucket == "opportunity"], [])

    def test_divergence_we_reference_must_be_carried(self):
        touch = TouchSet(name="Fork", platform="windows", symbols={"kDropped"})
        from chromedrift.model import MODE_FORK
        changes = diff_snapshots(snap("148.0.0.0", [feature("Dropped", "enabled")]),
                                 snap("fork-main-dev", []), mode=MODE_FORK)
        finding = score_all(changes, touch, mode=MODE_FORK)[0]
        # We removed it and our own source names it: the next rebase puts it
        # back, so this is work, not trivia.
        self.assertEqual(finding.bucket, "must_fix")

    def test_uprev_mode_keeps_its_opportunity_bucket(self):
        """The fork branch must not quietly change uprev behaviour."""
        changes = diff_snapshots(snap("148.0.0.0", []),
                                 snap("151.0.0.0", [feature("Shiny", "enabled")]))
        finding = score_all(changes, TouchSet(name="Fork", platform="windows"))[0]
        self.assertEqual(finding.bucket, "opportunity")

    def test_report_says_which_comparison_it_is(self):
        from chromedrift.model import MODE_FORK, Report
        from chromedrift.report import html as html_report
        from chromedrift.report import markdown as md_report

        findings = self._fork_findings([], [feature("AcmeSauce", "enabled")])
        report = Report(from_ref="148.0.0.0", to_ref="fork-main-dev",
                        findings=findings, meta={"mode": MODE_FORK})
        for text in (md_report.render(report), html_report.render(report)):
            self.assertNotIn("uprev impact", text.lower())
            self.assertIn("upstream", text.lower())
        # ...and an uprev report is still an uprev report.
        uprev = Report(from_ref="148.0.0.0", to_ref="151.0.0.0", findings=[])
        self.assertIn("uprev impact", md_report.render(uprev).lower())


class TestProvenance(unittest.TestCase):
    """A two-way diff cannot tell a decision from merge debt. Three-way can.

    A fork built by repeatedly merging newer Chromium accumulates both, and
    they look identical against a single upstream version: our value differs.
    Comparing against the series the fork was merged from separates them --
    matching an older version exactly means nobody decided anything.
    """

    def _run(self, fork_facts, series, base=None):
        from chromedrift.provenance import analyze
        return analyze(fork=snap("fork", fork_facts),
                       upstream=[snap(ref, facts) for ref, facts in series],
                       base_ref=base)

    def test_matching_an_older_version_is_debt_not_a_decision(self):
        from chromedrift.provenance import STALE

        report = self._run(
            [feature("Foo", "disabled")],                       # our value
            [("143.0.0.0", [feature("Foo", "disabled")]),        # matches here
             ("148.0.0.0", [feature("Foo", "enabled")])])        # base moved on

        v = report.verdicts[0]
        self.assertEqual(v.state, STALE)
        self.assertEqual(v.matches, "143.0.0.0")
        self.assertTrue(v.is_debt())

    def test_matching_no_upstream_version_is_a_decision(self):
        from chromedrift.provenance import DIVERGED

        report = self._run(
            [feature("Foo", "disabled")],
            [("143.0.0.0", [feature("Foo", "enabled")]),
             ("148.0.0.0", [feature("Foo", "enabled")])])

        self.assertEqual(report.verdicts[0].state, DIVERGED)
        self.assertFalse(report.verdicts[0].is_debt())

    def test_added_after_our_base_is_debt_we_never_took(self):
        from chromedrift.provenance import MISSING_NEW

        report = self._run(
            [],
            [("143.0.0.0", []),
             ("148.0.0.0", [feature("NewUpstream", "enabled")])])

        v = report.verdicts[0]
        self.assertEqual(v.state, MISSING_NEW)
        self.assertTrue(v.is_debt())

    def test_present_since_the_oldest_version_but_absent_is_our_removal(self):
        from chromedrift.provenance import MISSING_OLD

        report = self._run(
            [],
            [("143.0.0.0", [feature("Always", "enabled")]),
             ("148.0.0.0", [feature("Always", "enabled")])])

        v = report.verdicts[0]
        self.assertEqual(v.state, MISSING_OLD)
        self.assertFalse(v.is_debt())   # a removal we chose, not debt

    def test_fact_upstream_never_had_is_ours(self):
        from chromedrift.provenance import VENDOR_ONLY

        report = self._run(
            [feature("VendorOnly", "enabled")],
            [("143.0.0.0", []), ("148.0.0.0", [])])

        self.assertEqual(report.verdicts[0].state, VENDOR_ONLY)

    def test_stale_reports_the_newest_version_we_still_match(self):
        """How far behind we are, not merely that we are behind."""
        report = self._run(
            [feature("Foo", "disabled")],
            [("139.0.0.0", [feature("Foo", "disabled")]),
             ("143.0.0.0", [feature("Foo", "disabled")]),
             ("148.0.0.0", [feature("Foo", "enabled")])])
        self.assertEqual(report.verdicts[0].matches, "143.0.0.0")

    def test_in_sync_is_not_debt(self):
        from chromedrift.provenance import IN_SYNC

        report = self._run(
            [feature("Foo", "enabled")],
            [("143.0.0.0", [feature("Foo", "disabled")]),
             ("148.0.0.0", [feature("Foo", "enabled")])])
        self.assertEqual(report.verdicts[0].state, IN_SYNC)
        self.assertEqual(report.debt(), [])


class TestPartitions(unittest.TestCase):
    """Bounding the scan is a speed/completeness trade, and must be explicit.

    Measured M148 -> M151: the full run is about 120s and 126 MB; --partition
    downloads is 17s and 2.6 MB. The saving is real and so is the loss.
    """

    def test_partition_narrows_the_fetch_list(self):
        from chromedrift.targets import get_targets

        full = get_targets("default")
        part = get_targets("default", ["downloads"])
        self.assertLess(len(part), len(full))
        self.assertTrue(any("resources/downloads" in t.path for t in part))
        self.assertFalse(any("resources/bookmarks" in t.path for t in part))

    def test_core_targets_survive_every_partition(self):
        """Prefs and flag metadata are cheap and relevant to everything."""
        from chromedrift.targets import get_targets

        for name in ("downloads", "settings", "history"):
            paths = {t.path for t in get_targets("default", [name])}
            self.assertIn("chrome/common/pref_names.h", paths, name)
            self.assertIn("chrome/browser/flag-metadata.json", paths, name)

    def test_partitions_combine(self):
        from chromedrift.targets import get_targets

        both = {t.path for t in get_targets("default", ["downloads", "bookmarks"])}
        self.assertTrue(any("resources/downloads" in p for p in both))
        self.assertTrue(any("resources/bookmarks" in p for p in both))

    def test_unknown_partition_is_rejected(self):
        from chromedrift.targets import get_targets

        with self.assertRaises(KeyError):
            get_targets("default", ["not-a-partition"])

    def test_partition_is_part_of_the_cache_key(self):
        """Otherwise a partial snapshot gets reused as if it were a full one.

        This exact class of bug has bitten twice: a "minimal" snapshot holding
        the full fact set, and a widened filter that changed nothing.
        """
        from chromedrift.snapshot import snapshot_path

        full = snapshot_path("/c", "refs/tags/151.0.0.0", "default")
        part = snapshot_path("/c", "refs/tags/151.0.0.0", "default", ["downloads"])
        self.assertNotEqual(full, part)
        self.assertIn("downloads", part)

    def test_diff_refuses_to_compare_across_partitions(self):
        """One side missing whole categories reads as mass addition."""
        old = snap("148.0.0.0", [feature("Foo", "enabled")])
        new = snap("151.0.0.0", [feature("Foo", "disabled")])
        old.meta = {"target_set": "default", "partitions": []}
        new.meta = {"target_set": "default", "partitions": ["downloads"]}
        with self.assertRaises(ValueError):
            diff_snapshots(old, new)


class TestDocumentedInterface(unittest.TestCase):
    """The docs are the interface for people who never read the source.

    Both halves of this drifted at once and neither showed up in a test run:
    `--platform` was removed from the CLI while eight documented commands kept
    passing it (they now exit with an argparse error before doing any work),
    and the skill's signal reference still named `android_enabled_by_default`
    after the rename, while missing every fork-mode signal -- the ones the fork
    comparison produces exclusively.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DOCS = ("README.md",
            "skills/analyzing-chromium-uprevs/SKILL.md",
            "skills/analyzing-chromium-uprevs/reference/signals.md",
            "skills/analyzing-chromium-uprevs/reference/traps.md",
            "skills/analyzing-chromium-uprevs/reference/settings-surface.md")

    def _read(self, rel):
        with open(os.path.join(self.ROOT, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_every_documented_command_parses(self):
        import contextlib
        import io
        import re

        from chromedrift.cli import build_parser

        pattern = re.compile(r"python3?\s+-m\s+chromedrift\s+((?:[^\n\\]|\\\n)*)")
        rejected = []
        for doc in self.DOCS:
            for match in pattern.finditer(self._read(doc)):
                raw = match.group(1).replace("\\\n", " ").split("#")[0].strip()
                argv = [a for a in raw.split() if not a.startswith("$")]
                # Prose quoting a bare subcommand, or a snippet with an elided
                # argument, is not a command anyone is expected to paste.
                if len(argv) < 2 or "…" in raw or "<" in raw or "--version" in argv:
                    continue
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(buf):
                        build_parser().parse_args(argv)
                except SystemExit:
                    rejected.append(f"{doc}: chromedrift {raw[:70]}")
        self.assertEqual(rejected, [], "documented commands the CLI rejects")

    def test_the_signal_reference_matches_the_signals(self):
        import re

        from chromedrift.diff import SIGNAL_LABELS, SIGNAL_SEVERITY

        real = set(SIGNAL_SEVERITY) | set(SIGNAL_LABELS)
        text = self._read("skills/analyzing-chromium-uprevs/reference/signals.md")
        documented = {t for t in re.findall(r"`([a-z][a-z0-9_]{4,})`", text)
                      if "_" in t}

        self.assertEqual(sorted(documented - real), [],
                         "signals.md documents signals the tool never emits")
        self.assertEqual(sorted(real - documented), [],
                         "the tool emits signals signals.md does not explain")


class TestProfilePlatform(unittest.TestCase):
    """A field that can only be right one way must not fail quietly.

    The CLI dropped --platform because reading the wrong platform inverts
    conclusions. The profile kept a `platform` field and trusted it, so a
    profile left saying "android" -- which the shipped example did -- turned off
    the not-compiled penalty completely: platform_state holds only "windows", so
    looking up "android" finds nothing and scores nothing down. Nothing in the
    output mentioned it.
    """

    def _profile(self, body):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".json5")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        self.addCleanup(os.remove, path)
        return path

    def test_a_stale_platform_is_refused_not_believed(self):
        from chromedrift.downstream import load_profile
        path = self._profile('{ name: "Fork", platform: "android" }')
        with self.assertRaises(ValueError) as caught:
            load_profile(path, log=lambda m: None)
        self.assertIn("android", str(caught.exception))
        self.assertIn("windows", str(caught.exception))

    def test_windows_and_an_absent_field_both_work(self):
        from chromedrift.downstream import load_profile
        for body in ('{ name: "Fork", platform: "windows" }',
                     '{ name: "Fork", platform: "Windows" }',
                     '{ name: "Fork" }'):
            touch = load_profile(self._profile(body), log=lambda m: None)
            self.assertEqual(touch.platform, "windows")

    def test_the_penalty_it_protects_still_applies(self):
        from chromedrift.model import Change
        change = Change(change_type="modified", kind="base_feature",
                        key="Foo", name="Foo",
                        after={"platform_state": {"windows": "not_compiled"}})
        finding = score_change(change, TouchSet(name="Fork", platform="windows"))
        self.assertTrue(any("not compiled" in r for r in finding.reasons))


class TestFetchMarkers(unittest.TestCase):
    """A cached outcome has to remember which outcome it was.

    A target genuinely absent from an older milestone is cached so it is not
    refetched every run. When that cache only recorded "done", a run in which
    every target 404s -- a mistyped tag, or a proxy that answers 404 instead of
    blocking -- failed loudly the first time and then, on the identical second
    invocation, read as a fully cached tree. The snapshot written from it held
    zero facts, and diffed against a real one the entire feature surface
    appeared to vanish. Nothing in the output said so.
    """

    def setUp(self):
        import tempfile
        from chromedrift.acquire import GitilesSource
        from chromedrift.targets import get_targets

        class AllMissing(GitilesSource):
            def fetch_file(self, path):
                return None

            def fetch_archive(self, directory):
                return None

        self.root = tempfile.mkdtemp()
        self.targets = get_targets("minimal")
        self.source = AllMissing("refs/tags/999.0.0.0", self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _missing(self, stats):
        return [p for p, v in stats.items() if v == "missing"]

    def test_a_missing_target_stays_missing_on_the_next_run(self):
        tree = os.path.join(self.root, "tree")
        first = self.source.materialize(self.targets, tree)
        second = self.source.materialize(self.targets, tree)
        self.assertEqual(len(self._missing(first)), len(self.targets))
        self.assertEqual(len(self._missing(second)), len(self.targets),
                         "a re-run reported the failed fetches as cached")

    def test_the_absence_is_still_cached_not_refetched(self):
        tree = os.path.join(self.root, "tree")
        self.source.materialize(self.targets, tree)
        calls = []
        self.source.fetch_file = lambda path: calls.append(path)
        self.source.materialize(self.targets, tree)
        self.assertEqual(calls, [], "cached absences were refetched")


class TestPartitionPlumbing(unittest.TestCase):
    """Every command that accepts --partition has to act on it.

    Three of them accepted the flag and dropped it: `provenance` (the command
    the fork comparison actually runs), `profile`, and `catalog` -- which then
    reported coverage against the full target list while describing a run that
    only fetched one partition.
    """

    def _parse(self, argv):
        from chromedrift.cli import build_parser
        return build_parser().parse_args(argv)

    def test_every_command_taking_the_flag_forwards_it(self):
        import inspect
        from chromedrift import cli

        for name in ("cmd_snapshot", "cmd_diff", "cmd_run", "cmd_profile",
                     "cmd_provenance"):
            src = inspect.getsource(getattr(cli, name))
            self.assertIn("build_snapshot", src, name)
            self.assertEqual(
                src.count("build_snapshot("), src.count("partitions=args.partitions"),
                f"{name} builds a snapshot without forwarding --partition")

    def test_catalog_measures_the_partition_it_was_given(self):
        from chromedrift import catalog
        paths = ["chrome/browser/resources/settings/route.ts",
                 "components/download/public/common/download_features.cc",
                 "media/base/media_switches.cc"]
        full = catalog.analyze(paths, ref="151.0.0.0")
        scoped = catalog.analyze(paths, ref="151.0.0.0", partitions=["downloads"])
        self.assertEqual(scoped.partitions, ["downloads"])
        self.assertLess(len(scoped.target_paths), len(full.target_paths))
        # media/ is outside the downloads partition, so a partitioned run must
        # not claim to have covered it.
        covered = {c.path for c in scoped.covered()}
        self.assertNotIn("media/base/media_switches.cc", covered)
        self.assertIn("media/base/media_switches.cc",
                      {c.path for c in full.covered()})

    def test_the_summary_admits_it_is_partial(self):
        from chromedrift import catalog
        report = catalog.analyze(["media/base/media_switches.cc"],
                                 ref="151.0.0.0", partitions=["downloads"])
        text = "\n".join(catalog.summarize(report))
        self.assertIn("downloads", text)
        self.assertIn("covers less by design", text)


class TestHtmlReportScales(unittest.TestCase):
    """A full uprev is thousands of findings, and the obvious rendering froze
    the tab.

    Measured on a real 3,120-finding report, the first version rebuilt 1.79 MB
    of HTML and 6,240 <tr> nodes on **every keystroke** -- 48% of that string
    being detail markup for rows that were hidden -- then re-attached 3,120
    click listeners. Typing one word ran the whole pipeline seven times.

    The four properties below are what make it usable. Each is checked by
    running the page's own script against a fake document, because "how much
    DOM does it build per keystroke" is a runtime property that no amount of
    inspecting the generated HTML text can see.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _report_html(self, n=3000):
        from chromedrift.model import Change, Finding, Report
        from chromedrift.report import html as html_report
        findings = [
            Finding(change=Change(change_type="modified", kind="base_feature",
                                  key=f"Feature{i}", name=f"Feature{i}",
                                  signals=["flag_retired_on"],
                                  paths=[f"content/f{i}.cc"]),
                    score=100 - i % 100, bucket="fyi",
                    reasons=["base severity 75"])
            for i in range(n)]
        return html_report.render(Report(from_ref="a", to_ref="b",
                                         findings=findings))

    def test_every_finding_is_still_embedded(self):
        """Paging must not become a way to lose data.

        Filtering and paging are presentation. The payload stays complete, so a
        reader can always search the whole set and the JSON never disagrees
        with the page.
        """
        import json
        import re
        text = self._report_html(300)
        payload = re.search(r"window\.__FINDINGS__=(\[.*?\]);\n", text, re.S)
        self.assertIsNotNone(payload, "findings payload not found in the page")
        rows = json.loads(payload.group(1))
        self.assertEqual(len(rows), 300)

    def test_the_page_offers_paging_at_all(self):
        self.assertIn('id="more"', self._report_html(300))

    def test_the_table_does_not_re_measure_itself_on_every_insert(self):
        """Layout, not JavaScript, is what made expanding a row lag.

        With the default auto layout, column widths depend on cell content, so
        inserting one expanded row makes the browser re-measure every cell in
        the table before it can paint. A fast machine hides this; a work laptop
        showed it as "not responding". Fixed layout needs explicit widths, so
        the colgroup has to be there too.
        """
        text = self._report_html(300)
        self.assertIn("table-layout:fixed", text.replace(" ", ""))
        self.assertIn("<colgroup>", text)
        self.assertNotIn("border-collapse:collapse", text.replace(" ", ""))

    def test_behaviour_under_load(self):
        """Runs the report's own script against a fake DOM."""
        import json
        import shutil
        import subprocess
        import tempfile

        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed; structural checks still ran")
        harness = os.path.join(self.ROOT, "tests", "js", "report_dom.js")
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(self._report_html())
            path = fh.name
        self.addCleanup(os.remove, path)
        result = subprocess.run([node, harness, path], capture_output=True,
                                text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[:400])
        out = json.loads(result.stdout)

        # 1. Only a page of rows reaches the DOM, not all 3,000. Asserted as a
        #    property rather than a constant, so tuning the page size for a
        #    slower machine does not need a test edit -- but removing paging
        #    still fails.
        self.assertLess(out["initialRows"], out["total"])
        self.assertLessEqual(out["initialRows"], 250)
        self.assertEqual(out["rowsAfterShowMore"], out["initialRows"] * 2)

        # 2. Detail markup -- half the old payload -- is built on expand only.
        self.assertEqual(out["detailsBuiltUpfront"], 0)
        self.assertEqual(out["detailsAfterClick"], 1)
        self.assertTrue(out["detailHasEvidence"],
                        "lazy details must still carry the evidence")
        self.assertTrue(out["detailRemovedOnSecondClick"])

        # 3. Typing does no work until the user pauses. Counting repaints is
        #    the measure that bites: the row count after filtering is a full
        #    page either way, so it cannot tell a debounced input from one
        #    that rebuilds the table on every character.
        self.assertEqual(out["paintsWhileTyping"], 0,
                         "search input repaints while typing; it is not debounced")
        self.assertEqual(out["paintsAfterDebounce"], 1,
                         "the debounced tail should repaint exactly once")
        self.assertIn("of 1111", out["afterDebounce"])
        self.assertEqual(out["rowsAfterFilter"], out["initialRows"])


class TestVendorDiscovery(unittest.TestCase):
    """Find the vendor's files without being told where they are.

    A fork of this shape is taken from Chromium whole, then its own files are
    placed *inside* Chromium's directories: an `acme/` subfolder here, an
    `-acme` suffix on a variant of an upstream component there. So "which files
    are ours" cannot be read off Chromium's layout, and after enough years
    nobody has the list. Both `vendor_markers` and the target list were being
    filled in from memory, and a forgotten path removes a whole surface from
    every comparison silently.

    `acme` is a placeholder throughout. The module carries no vendor vocabulary
    of its own, so every test states the markers it is scanning for.
    """

    MARKERS = {"dir_tokens": ("acme",), "file_suffixes": ("-acme",)}

    LAYOUT = (
        # upstream
        "chrome/browser/resources/settings/privacy_page/privacy_page.html",
        "chrome/browser/resources/settings/route.ts",
        # vendor variants of upstream components, inside upstream directories
        "chrome/browser/resources/settings/privacy_page/privacy_page-acme.html",
        "chrome/browser/resources/downloads/item-acme.html.ts",
        # vendor subfolder inside a tracked surface
        "chrome/browser/resources/settings/acme/secret_mode.html",
        # vendor subfolder beside the surfaces, outside every target
        "chrome/browser/resources/acme/quick_menu.html",
        # native UI: vendor-owned, but no extractor reads it
        "ui/acme/views/acme_toolbar.cc",
    )

    def setUp(self):
        import tempfile
        self.root = tempfile.mkdtemp()
        for rel in self.LAYOUT:
            path = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("// x\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _scan(self, **kw):
        from chromedrift import discover
        return discover.scan(self.root, log=lambda m: None,
                             **dict(self.MARKERS, **kw))

    def test_scanning_without_markers_refuses_rather_than_finding_nothing(self):
        """"No vendor files" and "you told me nothing to look for" differ.

        A tool that carries no vendor vocabulary cannot report the second as
        the first: an empty result would read as a clean fork.
        """
        from chromedrift import discover
        with self.assertRaises(ValueError):
            discover.scan(self.root, log=lambda m: None)

    def test_upstream_files_are_not_claimed(self):
        found = {h.path for h in self._scan().hits}
        self.assertNotIn("chrome/browser/resources/settings/route.ts", found)
        self.assertNotIn(
            "chrome/browser/resources/settings/privacy_page/privacy_page.html", found)

    def test_the_suffix_is_found_inside_an_upstream_directory(self):
        """No path prefix reaches it and it has no vendor symbol prefix."""
        from chromedrift.discover import BY_NAME
        hits = {h.path: h for h in self._scan().hits}
        for rel in ("chrome/browser/resources/settings/privacy_page/"
                    "privacy_page-acme.html",
                    "chrome/browser/resources/downloads/item-acme.html.ts"):
            self.assertIn(rel, hits, rel)
            self.assertEqual(hits[rel].rule, BY_NAME)

    def test_a_double_extension_still_matches(self):
        """item-acme.html.ts must strip both extensions before testing the stem."""
        report = self._scan()
        self.assertIn("-acme", report.suffixes_seen())
        self.assertEqual(report.suffixes_seen()["-acme"], 2)

    def test_vendor_folders_are_found_at_any_depth(self):
        from chromedrift.discover import BY_DIR
        hits = {h.path: h for h in self._scan().hits}
        for rel in ("chrome/browser/resources/settings/acme/secret_mode.html",
                    "chrome/browser/resources/acme/quick_menu.html",
                    "ui/acme/views/acme_toolbar.cc"):
            self.assertIn(rel, hits, rel)
            self.assertEqual(hits[rel].rule, BY_DIR)

    def test_uncovered_splits_what_can_be_fixed_from_what_cannot(self):
        """A worklist mixing the two is mostly unactionable."""
        from chromedrift.discover import uncovered_dirs
        fetchable, unreadable = uncovered_dirs(self._scan())
        self.assertIn("chrome/browser/resources/acme",
                      [d for d, _ in fetchable])
        # Native C++ UI is vendor-owned and no extractor reads it; calling that
        # "missing" implies a fix that does not exist.
        self.assertIn("ui/acme/views", [d for d, _ in unreadable])

    def test_macro_scanning_catches_the_common_shape(self):
        """ACME_CUSTOM_DOWNLOADS, not only X_ACME_Y."""
        path = os.path.join(self.root, "chrome/browser/download/download_prefs.cc")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#if defined(ACME_CUSTOM_DOWNLOADS)\n// ours\n#endif\n")
        report = self._scan(scan_content=True)
        self.assertIn("ACME_CUSTOM_DOWNLOADS", report.macros)

    def test_the_build_flags_come_from_the_tokens_given(self):
        """One list to get right, not two that drift.

        A vendor's build flags are its own name shouted, so they are derived
        from the directory tokens rather than kept as a second list.
        """
        path = os.path.join(self.root, "chrome/browser/net/x.cc")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#if defined(OTHERVENDOR_THING)\n// not ours\n#endif\n")
        report = self._scan(scan_content=True)
        self.assertEqual(dict(report.macros), {})

    def test_the_suggested_profile_reflects_the_tree(self):
        from chromedrift.discover import suggest_profile
        text = suggest_profile(self._scan())
        self.assertIn('"acme/"', text)
        self.assertIn('"-acme"', text)
        # The symbol prefixes are derived from the directories found, not from
        # a vendor list this module refuses to carry.
        self.assertIn('"kAcme"', text)

    def test_markers_recognise_a_variant_file_as_ours(self):
        """The marker vocabulary had no way to express this before."""
        from chromedrift.coverage import VendorMarkers
        markers = VendorMarkers.from_profile(
            {"vendor_markers": {"path_markers": ["acme/"],
                                "filename_markers": ["-acme"]}})
        self.assertTrue(markers.path_is_ours(
            "chrome/browser/resources/settings/privacy_page-acme.html"))
        self.assertTrue(markers.path_is_ours(
            "chrome/browser/resources/settings/item-acme.html.ts"))
        self.assertFalse(markers.path_is_ours(
            "chrome/browser/resources/settings/privacy_page.html"))


class TestReferenceClosure(unittest.TestCase):
    """"Is this enough?" is only answerable after extraction.

    File coverage says whether we fetched the files someone listed. It cannot
    say whether we fetched the files this surface depends on, because that
    depends on what the surface references. Walking the links the data itself
    declares turns the question into a list.
    """

    def _snap(self, facts):
        return Snapshot(ref="151.0.0.0", facts=facts)

    def test_a_self_contained_surface_reports_complete(self):
        from chromedrift.catalog import summarize_closure, unresolved_references
        snap_ = self._snap([
            Fact("webui_route", "settings/PRIVACY", "PRIVACY", "route.ts",
                 attrs={"guards": ["enablePrivacyGuide"]}),
            Fact("webui_gate", "enablePrivacyGuide", "enablePrivacyGuide", "h.cc",
                 attrs={"features": ["kPrivacyGuide"]}),
            feature("PrivacyGuide", "enabled"),
        ])
        self.assertEqual(unresolved_references(snap_), {})
        self.assertIn("complete", summarize_closure({})[0])

    def test_a_flag_declared_outside_the_partition_is_named(self):
        from chromedrift.catalog import unresolved_references
        snap_ = self._snap([
            Fact("webui_gate", "enableThing", "enableThing", "h.cc",
                 attrs={"features": ["kThingDeclaredInContent"]}),
        ])
        self.assertEqual(unresolved_references(snap_),
                         {"feature": ["ThingDeclaredInContent"]})

    def test_a_pref_bound_but_never_declared_is_named(self):
        from chromedrift.catalog import unresolved_references
        snap_ = self._snap([
            Fact("webui_control", "settings/x/pref:download.prompt", "pref:download.prompt",
                 "x.html", attrs={"pref": "download.prompt"}),
        ])
        self.assertEqual(unresolved_references(snap_), {"pref": ["download.prompt"]})

    def test_the_summary_names_what_to_add(self):
        from chromedrift.catalog import summarize_closure, unresolved_references
        snap_ = self._snap([
            Fact("webui_gate", "g", "g", "h.cc", attrs={"features": ["kMissing"]}),
        ])
        text = "\n".join(summarize_closure(unresolved_references(snap_)))
        self.assertIn("1 unresolved", text)
        self.assertIn("Missing", text)


class TestCompletePartitions(unittest.TestCase):
    """Filtering a curated list inherits the curation gap.

    `--partition downloads` was only ever as complete as the hand-written list
    happened to be, and measured at M151 it was missing bookmark and history
    pref files and a downloads Mojo interface. `--complete` derives the targets
    from directory roots instead, so what is covered stops depending on what
    anyone remembered.
    """

    def test_complete_pulls_roots_not_a_curated_subset(self):
        from chromedrift.targets import get_targets
        filtered = get_targets("default", ["downloads"])
        complete = get_targets("default", ["downloads"], complete=True)
        self.assertTrue(any(t.kind == "tree" and t.path == "components/download"
                            for t in complete),
                        "complete should pull the whole components/download root")
        self.assertFalse(any(t.kind == "tree" and t.path == "components/download"
                             for t in filtered))

    def test_complete_covers_what_the_curated_list_missed(self):
        """Measured gaps at M151, now inside the roots by construction."""
        from chromedrift.targets import get_targets
        targets = get_targets("default", ["bookmarks", "history"], complete=True)
        prefixes = [t.path.rstrip("/") + "/" for t in targets if t.kind == "tree"]
        for missed in ("components/bookmarks/common/bookmark_pref_names.h",
                       "components/history/core/common/pref_names.h"):
            self.assertTrue(any(missed.startswith(p) for p in prefixes), missed)

    def test_complete_filters_through_the_one_readable_list(self):
        """`--complete` and `wide` ask the same question, so they share a list.

        They did not. `--complete` carried its own copy, written earlier, that
        had never learned the `*_prefs.{h,cc}` convention or the `.h` half of
        four `.cc` hints -- so the flag whose entire promise is "100% of these
        roots, by construction" was fetching less than the extractors read.
        Measured at M151 across the tree: 86 files holding 747 keys.
        """
        from chromedrift.targets import READABLE_SUFFIXES, get_targets

        wide = {t.include for t in get_targets("wide")
                if t.kind == "tree" and t.include}
        self.assertIn(READABLE_SUFFIXES, wide)
        for target in get_targets("default", ["extensions"], complete=True):
            if target.kind != "tree":
                continue
            missing = set(READABLE_SUFFIXES) - set(target.include or ())
            self.assertFalse(missing, f"{target.path} filters out {missing}")

    def test_complete_fetches_the_pref_files_the_extractor_reads(self):
        """The concrete files the second list was dropping, at M151."""
        from chromedrift.targets import get_targets, reaches, scope_of
        files, trees = scope_of(get_targets("default", ["extensions"],
                                            complete=True))
        for path in ("extensions/browser/extension_prefs.h",
                     "extensions/browser/extension_prefs.cc",
                     "extensions/common/features/feature_flags.h"):
            self.assertTrue(reaches(path, files, trees), path)

    def test_an_unaffordable_root_is_refused_not_faked(self):
        from chromedrift.targets import get_targets
        with self.assertRaises(ValueError) as caught:
            get_targets("default", ["webplatform"], complete=True)
        self.assertIn("webplatform", str(caught.exception))

    def test_complete_needs_a_partition(self):
        from chromedrift.targets import get_targets
        with self.assertRaises(ValueError):
            get_targets("default", None, complete=True)

    def test_complete_is_part_of_the_cache_key(self):
        from chromedrift.snapshot import snapshot_path
        a = snapshot_path("/c", "refs/tags/151", "default", ["settings"])
        b = snapshot_path("/c", "refs/tags/151", "default", ["settings"], True)
        self.assertNotEqual(a, b)

    def test_diff_refuses_to_mix_complete_with_filtered(self):
        from chromedrift.diff import diff_snapshots
        old = Snapshot(ref="a", facts=[],
                       meta={"target_set": "default", "partitions": ["settings"],
                             "complete": True})
        new = Snapshot(ref="b", facts=[],
                       meta={"target_set": "default", "partitions": ["settings"],
                             "complete": False})
        with self.assertRaises(ValueError):
            diff_snapshots(old, new)


class TestCatalog(unittest.TestCase):
    """Turn "is the target set enough?" from a guess into a number.

    Curation failed twice by inspection. A blobless clone lists every path in
    Chromium in seconds, so coverage becomes measurable and the gap is named
    rather than suspected.
    """

    PATHS = [
        "content/public/common/content_features.cc",       # covered by a tree target
        "chrome/common/chrome_features.cc",                # covered by a file target
        "cc/base/features.cc",                             # not covered
        "components/sync/base/features.cc",                # covered
        "base/task/task_features.cc",                      # not covered
        "content/browser/x_unittest.cc",                   # a test, ignore
        "components/y/features_browsertest.cc",            # a test, ignore
        "ash/constants/ash_features.cc",                   # platform we do not ship
        "chrome/browser/browser.cc",                       # not a feature file
        "third_party/blink/renderer/core/dom/element.idl",  # not a .cc
    ]

    def _report(self, **kw):
        from chromedrift.catalog import analyze
        return analyze(self.PATHS, ref="151.0.0.0", **kw)

    def test_only_plausible_feature_files_are_candidates(self):
        paths = {c.path for c in self._report().candidates}
        self.assertIn("cc/base/features.cc", paths)
        self.assertNotIn("chrome/browser/browser.cc", paths)
        self.assertNotIn("third_party/blink/renderer/core/dom/element.idl", paths)

    def test_tests_are_excluded(self):
        paths = {c.path for c in self._report().candidates}
        self.assertNotIn("content/browser/x_unittest.cc", paths)
        self.assertNotIn("components/y/features_browsertest.cc", paths)

    def test_platforms_we_do_not_ship_are_excluded_by_default(self):
        self.assertNotIn("ash/constants/ash_features.cc",
                         {c.path for c in self._report().candidates})
        self.assertIn("ash/constants/ash_features.cc",
                      {c.path for c in
                       self._report(include_irrelevant=True).candidates})

    def test_coverage_distinguishes_fetched_from_unfetched(self):
        report = self._report()
        covered = {c.path for c in report.covered()}
        missing = {c.path for c in report.missing()}
        # A tree target covers everything beneath it.
        self.assertIn("content/public/common/content_features.cc", covered)
        # An exact file target covers just that file.
        self.assertIn("chrome/common/chrome_features.cc", covered)
        self.assertIn("cc/base/features.cc", missing)
        self.assertIn("base/task/task_features.cc", missing)

    def test_coverage_is_reported_as_a_number(self):
        report = self._report()
        self.assertEqual(len(report.candidates),
                         len(report.covered()) + len(report.missing()))
        self.assertTrue(0 <= report.coverage_pct() <= 100)

    def test_missing_is_grouped_so_the_gap_is_actionable(self):
        by_area = self._report().missing_by_area()
        self.assertIn("cc", by_area)
        self.assertIn("base", by_area)


class TestVendorShadowing(unittest.TestCase):
    """A fork shadows upstream with a build flag instead of editing it.

    Both implementations ship; a build flag picks one. Upstream's branch stays
    byte-identical, so a value comparison reports nothing while the branch that
    actually runs is the vendor's.
    """

    MARKERS = None

    def setUp(self):
        from chromedrift.coverage import VendorMarkers
        self.MARKERS = VendorMarkers(
            macros=["ACME"], symbol_prefixes=["kAcme"],
            path_markers=["acme/"])

    def _fact(self, name, state="enabled", conditions=(), path="a_features.cc"):
        f = feature(name, state, path=path)
        f.attrs["conditions"] = list(conditions)
        return f

    def test_identical_value_behind_a_vendor_guard_is_shadowed_not_untouched(self):
        from chromedrift.coverage import SHADOWED, analyze

        report = analyze(
            fork=snap("fork", [self._fact("Foo", "enabled",
                                        ["defined(ACME_CUSTOM)"])]),
            upstream=snap("148.0.0.0", [self._fact("Foo", "enabled")]),
            markers=self.MARKERS)

        # The value matches exactly. Only the guard reveals the shadow.
        self.assertEqual(report.verdicts[0].state, SHADOWED)
        self.assertEqual(report.verdicts[0].guards, ["defined(ACME_CUSTOM)"])

    def test_unguarded_identical_declaration_is_untouched(self):
        from chromedrift.coverage import UNTOUCHED, analyze

        report = analyze(
            fork=snap("fork", [self._fact("Foo", "enabled")]),
            upstream=snap("148.0.0.0", [self._fact("Foo", "enabled")]),
            markers=self.MARKERS)
        self.assertEqual(report.verdicts[0].state, UNTOUCHED)

    def test_platform_guard_is_not_a_vendor_guard(self):
        """#if BUILDFLAG(IS_WIN) is upstream's own, not ours.

        Both sides carry it, because that is what "upstream's own guard" means:
        it arrived with the merge. Nothing about it says we shadowed anything.
        """
        from chromedrift.coverage import UNTOUCHED, analyze

        guarded = lambda: self._fact("Foo", "enabled", ["BUILDFLAG(IS_WIN)"])
        report = analyze(fork=snap("fork", [guarded()]),
                         upstream=snap("148.0.0.0", [guarded()]),
                         markers=self.MARKERS)
        self.assertEqual(report.verdicts[0].state, UNTOUCHED)

    def test_a_guard_only_we_have_is_a_change_even_if_it_is_not_ours(self):
        """A non-vendor guard we added still changes what compiles.

        Not SHADOWED -- no vendor marker names it -- but not untouched either.
        Comparing only `default_state` called this identical to upstream, which
        is the same blind spot in miniature: the value matches and the
        condition deciding whether the value is used does not.
        """
        from chromedrift.coverage import MODIFIED, SHADOWED, analyze

        report = analyze(
            fork=snap("fork", [self._fact("Foo", "enabled",
                                        ["BUILDFLAG(IS_WIN)"])]),
            upstream=snap("148.0.0.0", [self._fact("Foo", "enabled")]),
            markers=self.MARKERS)
        self.assertNotEqual(report.verdicts[0].state, SHADOWED)
        self.assertEqual(report.verdicts[0].state, MODIFIED)

    def test_a_windows_branch_override_is_not_untouched(self):
        """The case the shadow analysis exists for.

        Upstream ships enabled everywhere; we ship disabled on Windows only.
        `default_state` is "enabled" on both sides, so comparing that alone
        reported our override as an untouched upstream declaration.
        """
        from chromedrift.coverage import MODIFIED, analyze

        theirs = Fact(kind="base_feature", key="Foo", name="Foo",
                      path="content/features.cc",
                      attrs={"var": "kFoo", "default_state": "enabled",
                             "platform_state": {"windows": "enabled"},
                             "conditions": []})
        ours = Fact(kind="base_feature", key="Foo", name="Foo",
                    path="content/features.cc",
                    attrs={"var": "kFoo", "default_state": "enabled",
                           "platform_state": {"windows": "disabled"},
                           "conditions": []})
        report = analyze(fork=snap("fork", [ours]),
                         upstream=snap("148.0.0.0", [theirs]),
                         markers=self.MARKERS)
        self.assertEqual(report.verdicts[0].state, MODIFIED)

    def test_ours_only_is_split_by_whether_anything_says_it_is_ours(self):
        """Two opposite situations wore the same label.

        A declaration only we have, carrying a vendor marker, is ours. One with
        no marker at all is usually the reverse: upstream deleted it and our
        merge kept it alive. Both were reported as "vendor_only", so the debt
        was filed under decisions.
        """
        from chromedrift.coverage import ORPHANED, VENDOR_ONLY, analyze

        mine = self._fact("AcmeThing", "enabled",
                          ["defined(ACME_CUSTOM)"])
        leftover = self._fact("LongDeadUpstreamFlag", "enabled")
        report = analyze(fork=snap("fork", [mine, leftover]),
                         upstream=snap("148.0.0.0", []),
                         markers=self.MARKERS)
        states = {v.key: v.state for v in report.verdicts}
        self.assertEqual(states["AcmeThing"], VENDOR_ONLY)
        self.assertEqual(states["LongDeadUpstreamFlag"], ORPHANED)

    def test_guards_used_reports_what_each_flag_covers(self):
        from chromedrift.coverage import analyze

        report = analyze(
            fork=snap("fork", [self._fact("A", "enabled", ["defined(ACME_UI)"]),
                             self._fact("B", "enabled", ["defined(ACME_UI)"])]),
            upstream=snap("148.0.0.0", [self._fact("A"), self._fact("B")]),
            markers=self.MARKERS)
        self.assertEqual(report.guards_used(), {"defined(ACME_UI)": 2})

    def test_without_markers_the_analysis_is_skipped_not_guessed(self):
        from chromedrift.coverage import VendorMarkers, analyze

        report = analyze(
            fork=snap("fork", [self._fact("Foo", "enabled", ["defined(X)"])]),
            upstream=snap("148.0.0.0", [self._fact("Foo")]),
            markers=VendorMarkers())
        self.assertFalse(report.markers_configured)
        self.assertEqual(report.verdicts, [])

    def test_guard_appearing_is_itself_a_change(self):
        """The value never moves; the guard around it does."""
        old = self._fact("Foo", "enabled")
        new = self._fact("Foo", "enabled", ["defined(ACME_CUSTOM)"])
        changes = diff_snapshots(snap("148.0.0.0", [old]), snap("fork", [new]),
                                 platform="windows")
        self.assertEqual(len(changes), 1)
        self.assertIn("conditions", changes[0].deltas)


class TestClustering(unittest.TestCase):
    """One upstream change arrives as fragments; they must read as one story."""

    def _finding(self, kind, key, attrs, score=50):
        from chromedrift.model import Change, Finding
        return Finding(
            change=Change(change_type="modified", kind=kind, key=key,
                          name=key.split("/")[-1], before=dict(attrs),
                          after=dict(attrs)),
            score=score, bucket="review")

    def test_route_gate_feature_form_one_cluster(self):
        from chromedrift.cluster import build_clusters

        route = self._finding("webui_route", "settings/SITE_SETTINGS_LNA",
                              {"surface": "settings", "route": "lna",
                               "guards": ["enableLna"]}, 70)
        gate = self._finding("webui_gate", "enableLna",
                             {"features": ["kLnaChecks"]}, 60)
        flag = self._finding("base_feature", "LnaChecks", {}, 50)
        clusters = build_clusters([route, gate, flag])

        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(next(iter(clusters.values()))), 3)

    def test_guard_on_either_side_links_the_route(self):
        """A migration re-gates a page; reading only the new guard splits it."""
        from chromedrift.cluster import build_clusters
        from chromedrift.model import Change, Finding

        moved = Finding(
            change=Change(change_type="modified", kind="webui_route",
                          key="settings/PAGE", name="PAGE",
                          before={"guards": ["oldGate"]},
                          after={"guards": ["newGate"]},
                          deltas={"guards": [["oldGate"], ["newGate"]]}),
            score=60, bucket="review")
        old_gate = self._finding("webui_gate", "oldGate", {"features": []}, 40)
        new_gate = self._finding("webui_gate", "newGate", {"features": []}, 40)

        clusters = build_clusters([moved, old_gate, new_gate])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(next(iter(clusters.values()))), 3)

    def test_control_joins_the_route_it_labels(self):
        """SITE_SETTINGS_LNA and siteSettingsLna are one identifier."""
        from chromedrift.cluster import build_clusters

        route = self._finding("webui_route", "settings/SITE_SETTINGS_LNA",
                              {"surface": "settings", "guards": []}, 60)
        control = self._finding("webui_control",
                                "settings/site_settings/label:siteSettingsLna",
                                {"surface": "settings", "page": "site_settings",
                                 "label": "siteSettingsLna"}, 40)
        clusters = build_clusters([route, control])
        self.assertEqual(len(clusters), 1)

    def test_blink_flag_without_a_declared_feature_stays_alone(self):
        """base_feature: "none" means there is no link. Do not invent one."""
        from chromedrift.cluster import build_clusters

        blink = self._finding("blink_runtime_feature", "LnaSplitPermissions",
                              {"base_feature": "none"}, 20)
        flag = self._finding("base_feature", "LnaChecksSplitPermissions", {}, 50)
        self.assertEqual(build_clusters([blink, flag]), {})

    def test_blink_flag_joins_via_its_declared_feature(self):
        from chromedrift.cluster import build_clusters

        blink = self._finding("blink_runtime_feature", "SomeApi",
                              {"base_feature": "kBackingFeature"}, 20)
        flag = self._finding("base_feature", "BackingFeature", {}, 50)
        self.assertEqual(len(build_clusters([blink, flag])), 1)

    def test_unrelated_findings_are_not_clustered(self):
        from chromedrift.cluster import build_clusters

        a = self._finding("base_feature", "Alpha", {})
        b = self._finding("base_feature", "Beta", {})
        self.assertEqual(build_clusters([a, b]), {})


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
                        signals=["enabled_by_default"], severity=75)
        report = Report(from_ref="139.0.0.0", to_ref="143.0.0.0",
                        findings=[Finding(change=change, score=75,
                                          bucket="review")],
                        meta={"platform": "windows"})

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


class TestNoVerdictStage(unittest.TestCase):
    """The tool stops at evidence, and nothing may quietly re-add a verdict.

    A verdict column that a failed stage leaves empty reads exactly like a
    clean result -- which is why the AI stage needed an unmissable warning line
    of its own. Removing the stage removes that whole failure mode, but only if
    nothing leaks back: a stray `ai` key in the JSON is the shape a consumer
    would start depending on again.
    """

    def _report(self, **summary):
        from chromedrift.model import Change, Finding, Report
        change = Change(change_type="modified", kind="base_feature",
                        key="Foo", name="Foo",
                        deltas={"default_state": ["disabled", "enabled"]},
                        signals=["enabled_by_default"], severity=75)
        return Report(from_ref="148.0.0.0", to_ref="151.0.0.0",
                      findings=[Finding(change=change, score=75,
                                        bucket="review",
                                        reasons=["base severity 75"])],
                      summary=summary)

    def test_the_serialized_finding_has_no_verdict_field(self):
        payload = self._report().to_dict()
        self.assertNotIn("ai", payload["summary"])
        self.assertNotIn("ai", payload["findings"][0])

    def test_a_legacy_report_with_a_verdict_still_loads(self):
        """Reports written before the stage was removed must not crash."""
        from chromedrift.model import Report

        payload = self._report().to_dict()
        payload["summary"]["ai"] = {"headline": "old"}
        payload["findings"][0]["ai"] = {"verdict": "breaks_us"}
        loaded = Report.from_dict(payload)
        self.assertEqual(len(loaded.findings), 1)
        self.assertFalse(hasattr(loaded.findings[0], "ai"))

    def test_neither_renderer_offers_a_verdict_column(self):
        from chromedrift.report import html as html_report
        from chromedrift.report import markdown as md_report

        report = self._report()
        md = md_report.render(report)
        html = html_report.render(report)
        self.assertNotIn("Verdict", md)
        self.assertNotIn("| Verdict", md)
        self.assertNotIn(">Verdict<", html)
        # The evidence a reader needs to reach their own conclusion stays.
        self.assertIn("Score reasoning", md)

    def test_the_html_table_columns_still_line_up(self):
        """Dropping a column silently breaks the empty and detail rows.

        Their colspan is written out separately from the colgroup, so the two
        disagree without any error -- the table just renders wrong.
        """
        import re

        from chromedrift.report import html as html_report

        text = html_report.render(self._report())
        head = text[text.index("<colgroup>"):text.index("</colgroup>")]
        cols = len(re.findall(r"<col[ />]", head))
        ths = len(re.findall(r"<th ", text[text.index("<thead>"):text.index("</thead>")]))
        spans = {int(n) for n in re.findall(r'colspan="(\d+)"', text)}
        self.assertEqual(cols, ths)
        self.assertEqual(spans, {ths})

    def test_the_page_fetches_nothing(self):
        """The README promises it opens on an air-gapped machine.

        Nothing enforced that. One `<link rel=stylesheet>` or one webfont
        `url()` and the page still renders on the machine that built it, looks
        broken on the one it was mailed to, and no test says a word. Data
        legitimately contains URLs -- a feature parameter's default value is
        sometimes a support link -- so the check is on what the *markup* points
        at, not on whether the characters appear.
        """
        import re

        from chromedrift.model import Change, Finding, Report
        from chromedrift.report import html as html_report

        change = Change(change_type="modified", kind="feature_param",
                        key="helpUrl", name="helpUrl",
                        after={"feature": "kGlic", "default": "https://x.test/a"})
        change.deltas = {"default": ["https://x.test/a", "https://x.test/b"]}
        text = html_report.render(
            Report(from_ref="a", to_ref="b",
                   findings=[Finding(change=change, score=40, bucket="fyi")]))
        markup = text.split("window.__FINDINGS__")[0]
        targets = re.findall(r'(?:src|href|action)\s*=\s*["\']([^"\']*)',
                             markup)
        self.assertTrue(all(t.startswith("#") for t in targets), targets)
        self.assertNotIn("@import", markup)
        self.assertNotIn("url(", markup)
        # The URL in the data still reaches the reader, as text.
        self.assertIn("x.test", text)

    def test_the_milestone_brief_reaches_the_report(self):
        """Chromestatus context used to exist only inside the model prompt.

        With the prompt gone it has to land in the report, or the one source
        that says what upstream *meant* to ship is fetched and thrown away.
        """
        from chromedrift.report import markdown as md_report

        report = self._report(milestone_brief=[
            {"milestone": 149, "name": "CSS anchor positioning",
             "summary": "Positions an element relative to another."},
        ])
        text = md_report.render(report)
        self.assertIn("CSS anchor positioning", text)
        self.assertIn("Positions an element relative to another.", text)
        # And it must be labelled as background, not as a per-finding claim.
        self.assertIn("not* matched to the findings", text)

    def test_a_report_without_a_brief_renders_no_empty_section(self):
        from chromedrift.report import markdown as md_report
        self.assertNotIn("What Chromium says shipped",
                         md_report.render(self._report()))


class TestTreeFilterIsPartOfScope(unittest.TestCase):
    """A tree target's suffix filter has to survive into extraction.

    The tree cache is shared per ref across target sets and partitions, so a
    wider earlier run leaves files behind that a later, narrower run never
    asked for. Scoping on the path prefix alone extracts them anyway -- and
    since the two sides of a comparison rarely carry the same leftovers, the
    difference reads as a mass deletion of whatever the other side lacks.

    Measured: 103 stray .mojom files under chrome/browser/ui/webui in one
    snapshot and none in the other produced 803 phantom "Mojo method removed"
    findings, at the highest severity the tool assigns.
    """

    def _tree(self, tmp):
        import os
        webui = os.path.join(tmp, "chrome", "browser", "ui", "webui")
        os.makedirs(webui)
        with open(os.path.join(webui, "handler.cc"), "w") as fh:
            fh.write('html_source->AddBoolean("someKey", '
                     'base::FeatureList::IsEnabled(features::kThing));')
        # The leftover a --complete run would have deposited here.
        with open(os.path.join(webui, "leftover.mojom"), "w") as fh:
            fh.write("module chrome.mojom;\ninterface Stray { DoThing(); };\n")
        return webui

    def test_a_leftover_file_outside_the_filter_is_not_extracted(self):
        import tempfile
        from chromedrift.extract import run_on_tree

        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp)
            facts, _ = run_on_tree(
                tmp, allow_prefixes={"chrome/browser/ui/webui/": (".cc",)})
            kinds = {f.kind for f in facts}
            self.assertIn("webui_gate", kinds, "the .cc target must still be read")
            self.assertNotIn("mojo_interface", kinds,
                             "a .mojom left in the tree cache is not in scope")

    def test_a_prefix_with_no_filter_still_takes_everything(self):
        """The bare-set form keeps working, for callers that want the tree."""
        import tempfile
        from chromedrift.extract import run_on_tree

        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp)
            facts, _ = run_on_tree(tmp, allow_prefixes={"chrome/browser/ui/webui/"})
            self.assertIn("mojo_interface", {f.kind for f in facts})

    def test_the_snapshot_scope_carries_the_filter(self):
        """snapshot.py must pass the filter through, not just the path."""
        from chromedrift.targets import get_targets

        prefixes = {t.path.rstrip("/") + "/": t.include
                    for t in get_targets("default") if t.kind == "tree"}
        self.assertEqual(prefixes.get("chrome/browser/ui/webui/"), (".cc",))


class TestScopeViolations(unittest.TestCase):
    """A snapshot must not hold facts from files its target set never asked for.

    This is the check that would have caught the tree-filter leak. Comparing
    the two sides for symmetry was tried first and cannot work: a file type
    legitimately vanishes when Chromium migrates one (Polymer `.html` to Lit
    `.html.ts`) and legitimately appears when a surface is new, and both look
    exactly like a leak. Asking one snapshot whether it stayed inside its own
    declared scope is exact instead of heuristic.
    """

    def _snap(self, paths):
        from chromedrift.model import Fact, Snapshot
        return Snapshot(
            ref="test", meta={"target_set": "default", "partitions": [],
                              "complete": False},
            facts=[Fact(kind="x", key=p, name="x", path=p) for p in paths])

    def test_a_file_outside_the_tree_filter_is_flagged(self):
        from chromedrift.catalog import scope_violations

        # The default target asks for chrome/browser/ui/webui as *.cc only.
        snap = self._snap(["chrome/browser/ui/webui/downloads/downloads.cc",
                           "chrome/browser/ui/webui/downloads/downloads.mojom"])
        self.assertEqual(scope_violations(snap),
                         ["chrome/browser/ui/webui/downloads/downloads.mojom"])

    def test_a_file_under_no_target_at_all_is_flagged(self):
        from chromedrift.catalog import scope_violations
        snap = self._snap(["chrome/browser/ui/views/toolbar/toolbar_view.cc"])
        self.assertEqual(len(scope_violations(snap)), 1)

    def test_a_clean_snapshot_is_silent(self):
        from chromedrift.catalog import scope_violations
        snap = self._snap(["chrome/browser/ui/webui/downloads/downloads.cc",
                           "chrome/common/pref_names.h",
                           "third_party/blink/public/mojom/frame/frame.mojom"])
        self.assertEqual(scope_violations(snap), [])

    def test_a_polymer_to_lit_migration_is_not_a_violation(self):
        """Both dialects are inside the WebUI filter, so neither is out of scope."""
        from chromedrift.catalog import scope_violations
        snap = self._snap(["chrome/browser/resources/history/app.html",
                           "chrome/browser/resources/history/app.html.ts"])
        self.assertEqual(scope_violations(snap), [])

    def test_the_real_snapshots_in_the_cache_are_clean(self):
        """Runs against whatever real snapshots this machine has built."""
        import glob
        import os

        from chromedrift.catalog import scope_violations
        from chromedrift.model import Snapshot, read_json

        from chromedrift.model import SCHEMA_VERSION

        found = sorted(glob.glob(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".chromedrift-cache", "snapshots", "*.json")))
        checked = 0
        for path in found:
            raw = read_json(path)
            # A snapshot written by another version of this code was scoped by
            # that version's target set, so judging it against this one says
            # nothing. The pipeline rebuilds those anyway.
            if raw.get("schema") != SCHEMA_VERSION:
                continue
            checked += 1
            snap = Snapshot.from_dict(raw)
            self.assertEqual(scope_violations(snap), [],
                             f"{os.path.basename(path)} read out-of-scope files")
        if not checked:
            self.skipTest("no current-schema snapshots on this machine")


class TestDiscoveryMeasuresTheGap(unittest.TestCase):
    """The target list is measured against the tree, every run.

    A named list of files decays. Built as it stood at M130 and run against
    M151, twenty-one milestones later, it misses 96 of the 346 pref files that
    exist there (27%) and 216 of the 631 feature files (34%). The decay is
    silent -- a file nobody listed is a file nobody notices -- and this project
    has twice responded by adding names, which only resets the clock.

    Fetching everything discovery finds is not the answer either: Gitiles
    serves about one request per second per client whatever the concurrency, so
    the ~1,000 matching files cost seventeen minutes per version. Discovery
    therefore measures rather than fetches, and the number it produces is what
    stops the gap from being invisible.
    """

    class _Tree:
        def __init__(self, paths):
            self.paths = paths

        def list_recursive(self, directory):
            d = directory.rstrip("/") + "/"
            return [p for p in self.paths if p.startswith(d)]

    def _found(self, paths):
        from chromedrift.targets import discover_candidates
        return set(discover_candidates(self._Tree(paths)))

    def test_both_pref_naming_conventions_are_found(self):
        got = self._found([
            "chrome/common/pref_names.h",
            "components/bookmarks/common/bookmark_pref_names.h",
            "chrome/browser/ui/safety_hub/safety_hub_prefs.h",
            "components/performance_manager/public/user_tuning/prefs.h",
        ])
        self.assertEqual(len(got), 4, got)

    def test_feature_and_switch_files_are_found(self):
        got = self._found([
            "chrome/common/chrome_features.cc",
            "components/omnibox/common/omnibox_features.cc",
            "media/media_switches.cc",
            "components/x/x_field_trial.cc",
        ])
        self.assertEqual(len(got), 4, got)

    def test_a_file_that_did_not_exist_before_is_still_found(self):
        """The whole point: no list has to be edited when Chromium adds one."""
        got = self._found(["chrome/browser/ai/features.cc",
                           "chrome/browser/actor/ui/actor_ui_prefs.cc"])
        self.assertEqual(len(got), 2, got)

    def test_test_files_are_not_candidates(self):
        got = self._found([
            "components/x/x_features.cc",
            "components/x/x_features_unittest.cc",
            "components/x/x_prefs_browsertest.cc",
            "components/x/test/x_features.cc",
        ])
        self.assertEqual(got, {"components/x/x_features.cc"})

    def test_platforms_we_do_not_ship_are_not_candidates(self):
        got = self._found([
            "components/x/x_prefs.cc",
            "chrome/browser/ash/app_mode/pref_names.cc",
            "components/x/ios/x_prefs.cc",
            "components/x/android/x_features.cc",
        ])
        self.assertEqual(got, {"components/x/x_prefs.cc"})

    def test_unrelated_files_are_not_candidates(self):
        got = self._found(["base/android/library_loader/library_prefetcher.cc",
                           "components/x/pref_service.cc",
                           "components/x/feature_engagement_tracker.cc"])
        self.assertEqual(got, set())

    def test_coverage_counts_what_a_target_set_reaches(self):
        from chromedrift.acquire import FetchTarget
        from chromedrift.targets import coverage_against

        candidates = {"components/a/a_features.cc": "f",
                      "components/b/b_features.cc": "f",
                      "chrome/browser/c/c_prefs.h": "p"}
        targets = [FetchTarget("components/a/a_features.cc", "file"),
                   FetchTarget("chrome/browser/c", "tree", (".h",))]
        cov = coverage_against(candidates, targets)
        self.assertEqual(cov["candidates"], 3)
        self.assertEqual(cov["read"], 2)
        self.assertEqual(cov["missed_paths"], ["components/b/b_features.cc"])

    def test_a_tree_filter_that_excludes_a_file_leaves_it_uncovered(self):
        """Reaching a directory is not the same as reading the file in it."""
        from chromedrift.acquire import FetchTarget
        from chromedrift.targets import coverage_against

        cov = coverage_against({"chrome/browser/x/x_prefs.h": "p"},
                               [FetchTarget("chrome/browser", "tree", (".cc",))])
        self.assertEqual(cov["missed"], 1)

    def test_the_wide_target_set_closes_most_of_the_gap(self):
        """`--target-set wide` exists to be the answer when the gap matters."""
        from chromedrift.targets import coverage_against, get_targets

        candidates = {"components/deep/nested/x_features.cc": "f",
                      "chrome/browser/deep/y_prefs.h": "p",
                      "media/z_switches.cc": "f"}
        narrow = coverage_against(candidates, get_targets("default"))
        wide = coverage_against(candidates, get_targets("wide"))
        self.assertEqual(narrow["read"], 0)
        self.assertEqual(wide["read"], 3)


class TestIdentityMovesAreStillChanges(unittest.TestCase):
    """When the part of a fact that moved *is* its identity, pairing recovers it.

    Two cases found by auditing six real versions, both of which produced no
    usable finding at all before:

    A base::Feature is keyed on its feature string, so renaming the C++
    identifier while holding the string emitted nothing -- yet downstream code
    writes `features::kFoo`, never the string, so the rename breaks our build.
    kDIPS -> kBtm is a real instance.

    A WebUI control's identity contains the preference it writes, because the
    preference alone is not unique. So a control that starts writing a
    different preference changes identity with it, and arrived as an unrelated
    removal plus addition -- 21 times across M130 -> M151.
    """

    def _feature(self, name, var):
        from chromedrift.model import Fact
        return Fact(kind="base_feature", key=name, name=name,
                    path="content/features.cc",
                    attrs={"var": var, "default_state": "enabled",
                           "platform_state": {"windows": "enabled"}})

    def _control(self, pref, element_id, control="settings-toggle-button"):
        from chromedrift.model import Fact
        key = f"settings/a11y_page/pref:{pref}#{element_id}"
        return Fact(kind="webui_control", key=key, name=key,
                    path="chrome/browser/resources/settings/a11y_page/p.html",
                    attrs={"surface": "settings", "page": "a11y_page",
                           "control": control, "pref": pref, "label": "",
                           "element_id": element_id, "build_conditions": []})

    def test_a_renamed_cpp_identifier_is_reported(self):
        changes = diff_snapshots(snap("130.0.0.0", [self._feature("DIPS", "kDIPS")]),
                                 snap("136.0.0.0", [self._feature("DIPS", "kBtm")]))
        self.assertEqual(len(changes), 1)
        self.assertIn("feature_symbol_renamed", changes[0].signals)
        self.assertEqual(changes[0].deltas["var"], ["kDIPS", "kBtm"])

    def test_a_repointed_control_becomes_one_finding(self):
        changes = diff_snapshots(
            snap("148.0.0.0", [self._control("a11y.old_key", "toggle")]),
            snap("151.0.0.0", [self._control("a11y.new_key", "toggle")]))
        self.assertEqual(len(changes), 1, [c.name for c in changes])
        self.assertIn("ui_control_repointed", changes[0].signals)
        self.assertEqual(changes[0].deltas["pref"], ["a11y.old_key", "a11y.new_key"])

    def test_a_repoint_that_also_changes_the_control_type_says_both(self):
        changes = diff_snapshots(
            snap("148.0.0.0", [self._control("a11y.old", "t")]),
            snap("151.0.0.0", [self._control("a11y.new", "t", "settings-dropdown-menu")]))
        self.assertEqual(len(changes), 1)
        self.assertIn("ui_control_repointed", changes[0].signals)
        self.assertIn("ui_control_type_changed", changes[0].signals)

    def test_two_controls_leaving_one_anchor_are_not_paired(self):
        """Pairing is only safe when exactly one leaves and one arrives."""
        changes = diff_snapshots(
            snap("148.0.0.0", [self._control("a.one", "t"), self._control("a.two", "t")]),
            snap("151.0.0.0", [self._control("a.three", "t")]))
        self.assertEqual([c for c in changes if "ui_control_repointed" in c.signals], [])

    def test_fork_mode_does_not_pair_either_of_them(self):
        """Across a fork these are two decisions, not one move."""
        from chromedrift.model import MODE_FORK
        changes = diff_snapshots(
            snap("148.0.0.0", [self._control("a11y.old", "t")]),
            snap("fork-main-dev", [self._control("a11y.new", "t")]), mode=MODE_FORK)
        self.assertEqual(len(changes), 2)


class TestTargetSetsAreHonestAboutCost(unittest.TestCase):
    """Three target sets, and each has to say what it costs and what it reads.

    Coverage is a property of a run, not of the tool, so nothing may hard-code
    it as a constant. Measured at M151: `default` reads 42 of the 1,039 files
    in the tree that could declare -- 4% of files, but more than half the
    `base::Feature` declarations, because the curated files are the large ones
    -- and `wide` reads all 1,039, for about 315 MB per version against 40.
    """

    def test_every_named_set_resolves(self):
        from chromedrift.targets import TARGET_SETS, get_targets
        for name in TARGET_SETS:
            self.assertTrue(get_targets(name), name)

    def test_wide_is_a_superset_of_default(self):
        """A release gate must never read *less* than a working run."""
        from chromedrift.targets import get_targets
        default = {(t.path, t.kind) for t in get_targets("default")}
        wide = {(t.path, t.kind) for t in get_targets("wide")}
        self.assertTrue(default <= wide, sorted(default - wide))

    def test_every_wide_suffix_is_read_by_some_extractor(self):
        """The archives are large; the filter is what stops the tree being.

        A suffix nobody reads is bytes unpacked and then ignored, and worse, it
        reads as coverage that is not there. Several of these only match at a
        specific path -- `route.ts` is a route table only under
        resources/, `flag-metadata.json` only by its exact name -- so the probe
        has to be a path that could really occur.
        """
        from chromedrift.extract import REGISTRY
        from chromedrift.targets import READABLE_SUFFIXES

        probes = {
            ".json5": "third_party/blink/renderer/platform/"
                      "runtime_enabled_features.json5",
            "route.ts": "chrome/browser/resources/settings/route.ts",
            "routes.ts": "chrome/browser/resources/history/routes.ts",
            "flag-metadata.json": "chrome/browser/flag-metadata.json",
            ".html": "chrome/browser/resources/settings/a11y_page/p.html",
            ".html.ts": "chrome/browser/resources/downloads/item.html.ts",
            ".mojom": "services/network/public/mojom/x.mojom",
            ".idl": "third_party/blink/renderer/modules/x.idl",
        }
        for suffix in READABLE_SUFFIXES:
            probe = probes.get(suffix) or (
                f"components/x/y{suffix}" if suffix.startswith(".")
                else f"components/x/y_{suffix}")
            self.assertTrue(
                any(applies(probe) for _, applies, _ in REGISTRY),
                f"{suffix} is fetched but no extractor reads {probe}")

    def test_wide_roots_all_carry_a_filter(self):
        """An unfiltered root would unpack a whole Chromium subsystem to disk."""
        from chromedrift.targets import get_targets

        default_trees = {t.path for t in get_targets("default") if t.kind == "tree"}
        for target in get_targets("wide"):
            if target.kind == "tree" and target.path not in default_trees:
                self.assertTrue(target.include, f"{target.path} has no filter")

    def test_the_cache_key_separates_the_sets(self):
        """Otherwise a 40 MB snapshot gets reused as if it were the 315 MB one."""
        from chromedrift.snapshot import snapshot_path
        paths = {snapshot_path("c", "refs/tags/151.0.0.0", name)
                 for name in ("default", "minimal", "wide")}
        self.assertEqual(len(paths), 3)


class TestMinimalStaysMinimal(unittest.TestCase):
    """The smoke-test set has to stay a smoke test.

    It exists so CI can prove the wiring works in about a megabyte. A file
    added to it costs every smoke run, and the cost is invisible -- the set
    still works, it is just no longer fast. One did creep in: an edit meant for
    `default_targets` matched an identical line in `minimal_targets` too, and
    the three-file set quietly started pulling 683 preference keys.
    """

    def test_minimal_is_three_declaration_files(self):
        from chromedrift.targets import get_targets
        targets = get_targets("minimal")
        self.assertEqual(len(targets), 3, [t.path for t in targets])
        self.assertTrue(all(t.kind == "file" for t in targets))

    def test_minimal_is_a_subset_of_default(self):
        from chromedrift.targets import get_targets
        minimal = {t.path for t in get_targets("minimal")}
        default = get_targets("default")
        names = {t.path for t in default if t.kind == "file"}
        trees = [t.path.rstrip("/") + "/" for t in default if t.kind == "tree"]
        for path in minimal:
            self.assertTrue(path in names or any(path.startswith(p) for p in trees),
                            f"{path} is in minimal but not reachable from default")

    def test_every_partition_core_file_is_reachable_from_default(self):
        """PARTITION_CORE promises these to every partition."""
        from chromedrift.targets import PARTITION_CORE, get_targets
        default = get_targets("default")
        names = {t.path for t in default if t.kind == "file"}
        trees = [t.path.rstrip("/") + "/" for t in default if t.kind == "tree"]
        for path in PARTITION_CORE:
            self.assertTrue(path in names or any(path.startswith(p) for p in trees),
                            f"{path} is promised to partitions but not fetched")


class TestOneDefinitionOfScope(unittest.TestCase):
    """"Is this path in scope" had three implementations and two answers.

    Nested targets are normal and their filters differ: chrome/browser/ui/webui
    is declared for .cc while chrome/browser is declared for a dozen suffixes,
    so a header under the former is reached by the latter. Two of the three
    copies stopped at the first prefix that matched and answered no -- for 21
    files that were on disk and being read, which made the coverage figure
    under-report the tool against itself.
    """

    def _targets(self):
        from chromedrift.acquire import FetchTarget
        return [FetchTarget("chrome/browser/ui/webui", "tree", (".cc",)),
                FetchTarget("chrome/browser", "tree", ("prefs.h", ".mojom")),
                FetchTarget("chrome/common/pref_names.h", "file")]

    def test_a_wider_target_covers_what_a_narrower_one_excludes(self):
        from chromedrift.targets import reaches, scope_of
        files, trees = scope_of(self._targets())
        self.assertTrue(reaches(
            "chrome/browser/ui/webui/bookmarks/bookmark_prefs.h", files, trees))

    def test_a_path_no_target_claims_is_not_reached(self):
        from chromedrift.targets import reaches, scope_of
        files, trees = scope_of(self._targets())
        self.assertFalse(reaches("chrome/browser/ui/views/toolbar.cc", files, trees))

    def test_an_exact_file_target_is_reached(self):
        from chromedrift.targets import reaches, scope_of
        files, trees = scope_of(self._targets())
        self.assertTrue(reaches("chrome/common/pref_names.h", files, trees))

    def test_extraction_and_coverage_give_the_same_answer(self):
        """They used to disagree, which is the whole reason for one definition."""
        from chromedrift.catalog import scope_violations
        from chromedrift.model import Fact, Snapshot
        from chromedrift.targets import coverage_against, get_targets

        path = "chrome/browser/ui/webui/bookmarks/bookmark_prefs.h"
        targets = get_targets("wide")
        cov = coverage_against({path: "pref"}, targets)
        snap = Snapshot(ref="t", facts=[Fact(kind="pref", key="k", name="k", path=path)],
                        meta={"target_set": "wide", "partitions": [], "complete": False})
        # Coverage says it is read, and the scope check agrees it is allowed.
        self.assertEqual(cov["missed"], 0, cov["missed_paths"])
        self.assertEqual(scope_violations(snap), [])



class TestEveryScopeCheckAgrees(unittest.TestCase):
    """One question, one answer, in all four places that ask it.

    "Is this path in scope" is asked by extraction, by the coverage
    measurement, by the snapshot scope check, by `catalog`, and by
    `discover`. Whenever a copy of the rule drifts, the tool reports on a
    scope it is not actually using -- which is the defect this project has
    now hit four separate times.
    """

    NESTED = "chrome/browser/ui/webui/bookmarks/bookmark_prefs.h"

    def test_discover_agrees_with_the_shared_rule(self):
        """`wide` reaches this file; discover used to call it a gap.

        discover kept its own copy that stopped at the first prefix that
        matched. `chrome/browser/ui/webui` is declared for .cc, so it
        answered no -- while `chrome/browser`, declared for a dozen
        suffixes, fetches the file and an extractor reads it. The result
        was a worklist telling you to add targets you already have.
        """
        from chromedrift.discover import DiscoveryReport, Hit, BY_DIR, uncovered_dirs
        from chromedrift.targets import get_targets, reaches, scope_of

        report = DiscoveryReport(root="/fork")
        report.hits = [Hit(self.NESTED, BY_DIR, "acme")]

        files, trees = scope_of(get_targets("wide"))
        self.assertTrue(reaches(self.NESTED, files, trees))

        fetchable, unreadable = uncovered_dirs(report, "wide")
        self.assertEqual(fetchable, [], "a covered file was reported as a gap")
        self.assertEqual(unreadable, [])

    def test_catalog_agrees_with_the_shared_rule(self):
        """catalog measured on the path prefix and ignored the suffix filter.

        The default set asks for .cc under chrome/browser/ui/webui, so this
        header is never written to disk and never read. catalog counted it
        as covered -- an error in the reassuring direction, in the one
        command whose whole job is measuring the gap.
        """
        from chromedrift.catalog import covered_by_targets
        from chromedrift.targets import get_targets, reaches, scope_of

        targets = get_targets("default")
        files, trees = scope_of(targets)
        self.assertFalse(reaches(self.NESTED, files, trees))
        self.assertFalse(covered_by_targets(self.NESTED, targets))

    def test_catalog_honours_complete(self):
        """`--complete` fetches whole roots, so it must be measured that way.

        catalog took the flag from the shared parser and never passed it on,
        so a `--complete` run was measured against the curated file list it
        replaces -- reporting as missing every file the run does fetch.
        """
        from chromedrift.catalog import covered_by_targets
        from chromedrift.targets import get_targets

        path = "components/bookmarks/browser/bookmark_pref_names.h"
        filtered = get_targets("default", ["bookmarks"])
        complete = get_targets("default", ["bookmarks"], complete=True)
        self.assertFalse(covered_by_targets(path, filtered))
        self.assertTrue(covered_by_targets(path, complete))


class TestOneDefinitionOfWhatCouldDeclare(unittest.TestCase):
    """"Could this file declare something" must have one answer too.

    catalog carried its own filename regex, written before the `*_prefs.{h,cc}`
    convention was known and before the platform filter was fixed. Measured
    against the real M151 tree it disagreed with the coverage measurement on
    320 of about a thousand files: it missed 204 pref files that every run now
    reads, and counted 116 Android and about_flags files that no run reads.

    catalog exists to be the authority on what is missing, so it disagreeing
    with the number each run prints is the worst place for this to happen.
    """

    PREF_CONVENTION = "chrome/browser/accessibility/animation_policy_prefs.cc"
    ANDROID = "chrome/browser/android/chrome_startup_flags.cc"

    def test_catalog_uses_the_same_rule_as_the_coverage_measurement(self):
        from chromedrift.targets import could_declare

        self.assertTrue(could_declare(self.PREF_CONVENTION))
        self.assertFalse(could_declare(self.ANDROID))

        report = self._catalog([self.PREF_CONVENTION, self.ANDROID])
        self.assertEqual([c.path for c in report.candidates],
                         [self.PREF_CONVENTION])

    def test_all_platforms_still_widens_it(self):
        report = self._catalog([self.ANDROID], include_irrelevant=True)
        self.assertEqual([c.path for c in report.candidates], [self.ANDROID])

    def test_test_files_are_excluded_either_way(self):
        path = "components/foo/foo_features_unittest.cc"
        self.assertEqual(self._catalog([path]).candidates, [])
        self.assertEqual(
            self._catalog([path], include_irrelevant=True).candidates, [])

    def _catalog(self, paths, include_irrelevant=False):
        from chromedrift.catalog import analyze
        return analyze(paths, ref="151", include_irrelevant=include_irrelevant)


class TestOneDefinitionOfWhatIsReadable(unittest.TestCase):
    """Every convention an extractor reads has to be fetchable.

    The existing pair of tests walks this the other way -- no suffix is fetched
    that nothing reads -- and that direction is the cheap one, because its
    failure is wasted bandwidth. This direction's failure is a declaration on
    disk that nothing opens, which looks exactly like a declaration that does
    not exist.

    Derived from the extractors' own hint tuples rather than a list of sample
    filenames, because a sample list is a third copy: the one it replaced had
    ten entries and not one of them was a `*_prefs.h`, which is precisely the
    convention that had gone missing.
    """

    def _probe_basenames(self):
        """Real basenames carrying every convention an extractor claims."""
        from chromedrift.extract import constants
        from chromedrift.extract.base_features import FILE_HINTS

        for hint in FILE_HINTS:
            # A hint spelled with a leading underscore is deliberately narrower:
            # `_util.cc` is a feature file, a bare `util.cc` is not.
            if not hint.startswith("_"):
                yield hint
            yield "foo" + (hint if hint.startswith("_") else "_" + hint)
        for hint in (constants._SWITCH_HINT,) + constants._PREF_HINTS:
            stem = hint.strip("_.")
            for ext in (".cc", ".h"):
                yield stem + ext
                yield "foo_" + stem + ext

    def test_every_extractor_hint_is_fetched(self):
        from chromedrift.targets import READABLE_SUFFIXES

        for base in self._probe_basenames():
            self.assertTrue(
                any(base.endswith(s) for s in READABLE_SUFFIXES),
                f"{base} is read by an extractor but no fetch filter keeps it")

    def test_the_probes_are_really_read(self):
        """Guards the test itself: a probe nothing reads proves nothing."""
        from chromedrift.extract import REGISTRY

        for base in self._probe_basenames():
            path = "components/x/" + base
            self.assertTrue(any(applies(path) for _, applies, _ in REGISTRY),
                            f"probe {path} is not read by anything")


class TestOneDefinitionOfTheKPrefixRule(unittest.TestCase):
    """`kFooBar` -> `FooBar` is applied at four stages and defined at one.

    Extraction uses it to derive the key a base::Feature fact is stored under,
    so the reference closure, the clustering and the area routing all have to
    strip it exactly the same way to match those keys back. Four copies agreed
    when this was written; the point is that nothing keeps them agreeing.
    """

    RULE = re.compile(r"\[1\]\.isupper\(\)|\[1:2\]\.isupper\(\)")

    def test_only_base_features_defines_it(self):
        import glob

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for path in glob.glob(os.path.join(root, "chromedrift", "**", "*.py"),
                              recursive=True):
            if os.path.basename(path) == "base_features.py":
                continue
            with open(path, encoding="utf-8") as fh:
                if self.RULE.search(fh.read()):
                    offenders.append(os.path.relpath(path, root))
        self.assertEqual(offenders, [],
                         "re-use extract.base_features.feature_name_from_var")

    def test_every_consumer_agrees_with_it(self):
        from chromedrift.catalog import _bare
        from chromedrift.cluster import _flag_name
        from chromedrift.extract.base_features import feature_name_from_var

        for probe in ("kBackForwardCache", "kDIPS", "kilo", "k", "Feature", ""):
            expected = feature_name_from_var(probe)
            self.assertEqual(_bare(probe), expected, probe)
            self.assertEqual(_flag_name(probe), expected, probe)


class TestTheReportCarriesItsOwnCoverage(unittest.TestCase):
    """Two different measurements may not share one name.

    Tree coverage -- how much of the version's tree was read -- was printed to
    stderr and stored on the snapshot, and then not carried into the report,
    while README and SKILL.md both said the report held it. What the report did
    hold under `coverage` was area routing, so following either document led to
    the wrong object with nothing saying so.
    """

    def _report(self):
        from chromedrift.impact import summarize_findings
        summary = {"changes": {"total": 0, "by_kind": {}}}
        summary.update(summarize_findings([]))
        return Report(
            from_ref="refs/tags/148", to_ref="refs/tags/151", findings=[],
            summary=summary,
            meta={"target_set": "default",
                  "coverage": {"from": {"candidates": 986, "read": 43,
                                        "missed_by_directory": {}},
                               "to": {"candidates": 1039, "read": 42,
                                      "missed_by_directory":
                                          {"chrome/browser": 251}}},
                  "uncovered_files": ["chrome/browser/x_prefs.h"]})

    def test_area_coverage_has_its_own_name(self):
        from chromedrift.impact import summarize_findings
        summary = summarize_findings([])
        self.assertIn("area_coverage", summary)
        self.assertNotIn("coverage", summary)

    def test_tree_coverage_survives_into_the_report_json(self):
        blob = self._report().to_dict()
        self.assertEqual(blob["meta"]["coverage"]["to"]["read"], 42)
        self.assertEqual(blob["meta"]["uncovered_files"],
                         ["chrome/browser/x_prefs.h"])

    def test_the_rendered_report_states_it(self):
        from chromedrift.report import markdown as md
        text = md.render(self._report())
        self.assertIn("read 42 of 1,039 files", text)
        self.assertIn("`chrome/browser/` (251 files)", text)
        self.assertIn("--target-set wide", text)

    def test_a_wide_run_is_not_told_to_widen(self):
        from chromedrift.report import markdown as md
        report = self._report()
        report.meta["target_set"] = "wide"
        self.assertNotIn("--target-set wide", md.render(report))

    def test_a_report_without_the_measurement_renders_no_empty_row(self):
        from chromedrift.report import markdown as md
        report = self._report()
        report.meta["coverage"] = {}
        self.assertNotIn("Coverage at", md.render(report))


class TestTheDocumentedFiguresStillHold(unittest.TestCase):
    """A measured number written into a document is a second derivation of it.

    The code is already guarded -- no help text or log line may quote a coverage
    figure of its own -- but the documents carry a table of them, and it goes
    stale silently: the skill said 24,677 facts and 633 WebUI controls after
    both had moved, and nothing said so.

    README and SKILL.md state the same M151 table in two languages, so this
    parses each and checks it against the snapshots on disk. Skips where those
    do not exist, like the scope-violation check above: anyone who has run the
    tool re-verifies the documents for free, and a bare checkout does not fail.
    """

    # Row label -> the fact kind it counts. Both documents, both languages.
    ROWS = {
        "`base::Feature`": "base_feature",
        "Feature params": "feature_param",
        "Tham s\u1ed1 feature": "feature_param",
        "Preference keys": "pref",
        "Pref": "pref",
        "Command-line switches": "switch",
        "Switch": "switch",
        "Mojo interfaces": "mojo_interface",
        "Mojo interface": "mojo_interface",
        "Mojo methods": "mojo_method",
        "Mojo method": "mojo_method",
        "WebUI controls": "webui_control",
        "\u0110i\u1ec1u khi\u1ec3n WebUI": "webui_control",
        "Facts": None,                       # None = total fact count
        "**T\u1ed5ng s\u1ed1 fact**": None,
    }
    DOCS = ("README.md", "skills/analyzing-chromium-uprevs/SKILL.md",
            "docs/pipeline.html")
    ROW_RE = re.compile(r"^\s*\|([^|]+)\|([^|]+)\|([^|]+)\|\s*$", re.MULTILINE)
    # The interactive page states the same counts as chips rather than table
    # rows, and it went stale in exactly the same way.
    CHIP_RE = re.compile(r'<span class="chip[^"]*">([^<·]+)·\s*([\d.,]+)</span>')
    CHIPS = {"base::Feature": "base_feature", "pref": "pref", "switch": "switch",
             "Mojo method": "mojo_method", "Mojo interface": "mojo_interface",
             "IDL member": "idl_member", "IDL interface": "idl_interface",
             "route": "webui_route", "control": "webui_control",
             "gate": "webui_gate"}

    def _root(self):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _snapshots(self):
        """M151 default and wide, unpartitioned, at the current schema."""
        import glob

        from chromedrift.model import SCHEMA_VERSION, read_json

        out = {}
        for path in glob.glob(os.path.join(self._root(), ".chromedrift-cache",
                                           "snapshots", "*.json")):
            blob = read_json(path)
            meta = blob.get("meta") or {}
            if (blob.get("schema") != SCHEMA_VERSION
                    or meta.get("partitions") or meta.get("complete")
                    or "151." not in blob.get("ref", "")):
                continue
            out[meta.get("target_set")] = blob
        return out

    @staticmethod
    def _number(cell):
        """`**2.062**` / `1,623` / `42 (4%)` -> int, or None if not a count."""
        digits = re.match(r"^[*`\s]*([\d.,]+)", cell.strip())
        if not digits:
            return None
        raw = digits.group(1).replace(".", "").replace(",", "")
        return int(raw) if raw.isdigit() else None

    def test_the_m151_table_matches_the_snapshots(self):
        snaps = self._snapshots()
        if "default" not in snaps or "wide" not in snaps:
            self.skipTest("no current-schema M151 default+wide snapshots here")

        def expected(target_set, kind):
            blob = snaps[target_set]
            if kind is None:
                return len(blob.get("facts", []))
            return (blob.get("counts") or {}).get(kind, 0)

        checked = 0
        for name in self.DOCS:
            with open(os.path.join(self._root(), name), encoding="utf-8") as fh:
                text = fh.read()
            for label, value in self.CHIP_RE.findall(text):
                kind = self.CHIPS.get(label.strip())
                got = self._number(value)
                if kind is None or got is None:
                    continue
                self.assertEqual(
                    got, expected("default", kind),
                    f"{name}: chip {label.strip()!r} says {got}; the default "
                    f"snapshot says {expected('default', kind)}")
                checked += 1
            for label, default_cell, wide_cell in self.ROW_RE.findall(text):
                label = label.strip()
                if label not in self.ROWS:
                    continue
                kind = self.ROWS[label]
                for target_set, cell in (("default", default_cell),
                                         ("wide", wide_cell)):
                    got = self._number(cell)
                    if got is None:
                        continue
                    self.assertEqual(
                        got, expected(target_set, kind),
                        f"{name}: row {label!r}, column {target_set} says {got}; "
                        f"the snapshot on disk says {expected(target_set, kind)}")
                    checked += 1
        self.assertGreaterEqual(checked, 24,
                                "the tables moved; this test found almost "
                                "nothing to check")


class TestExtractionDoesNotDependOnWalkOrder(unittest.TestCase):
    """The same tree must give the same facts on every machine.

    `os.walk` sorted filenames and not directories, and when two files declare
    the same fact the order decided which one survived -- 228 colliding uids in
    the M151 tree, 68 of them disagreeing on an attribute the diff compares.
    Filesystem order differs between machines and between the two trees of one
    comparison, so diffing the M151 tree against itself under two walk orders
    produced 68 changes describing nothing, the largest a
    `web_api_signature_change` at severity 50.

    That also made the documented promise false: a released tag's snapshot is
    supposed to be shareable between jobs and teams because its content never
    changes.
    """

    SOURCE = 'inline constexpr char kOne[] = "shared";\n'
    OTHER = 'inline constexpr char kTwo[] = "shared";\n'

    def _tree(self, tmp):
        # Two directories declaring the same key with different C++ constants,
        # which is the real shape: `switch:disabled` has three of them.
        for name, text in (("zebra", self.SOURCE), ("alpha", self.OTHER)):
            path = os.path.join(tmp, "components", name)
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "pref_names.cc"), "w",
                      encoding="utf-8") as fh:
                fh.write(text)

    def _facts(self, tmp, shuffle_seed=None):
        import random

        from chromedrift.extract import run_on_tree
        import chromedrift.extract as ex

        real = os.walk
        if shuffle_seed is not None:
            random.seed(shuffle_seed)

            def walk(top, *a, **k):
                for dp, dn, fn in real(top, *a, **k):
                    random.shuffle(dn)
                    yield dp, dn, fn
            ex.os.walk = walk
        try:
            facts, _ = run_on_tree(tmp)
        finally:
            ex.os.walk = real
        return [(f.uid, f.path, tuple(sorted(f.attrs.items()))) for f in facts]

    def test_every_walk_order_gives_the_same_facts(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp)
            baseline = self._facts(tmp)
            for seed in range(6):
                self.assertEqual(self._facts(tmp, seed), baseline,
                                 f"walk order {seed} changed the fact set")

    def test_the_surviving_copy_is_chosen_by_path_not_arrival(self):
        from chromedrift.model import Fact, dedupe_facts

        low = Fact("pref", "shared", "shared", path="components/alpha/p.cc")
        high = Fact("pref", "shared", "shared", path="components/zebra/p.cc")
        for order in ((low, high), (high, low)):
            kept = dedupe_facts(order)
            self.assertEqual([f.path for f in kept], ["components/alpha/p.cc"])

    def test_an_earlier_line_in_one_file_wins(self):
        from chromedrift.model import Fact, dedupe_facts

        first = Fact("switch", "s", "s", path="a.cc", line=10)
        second = Fact("switch", "s", "s", path="a.cc", line=90)
        self.assertEqual(dedupe_facts([second, first])[0].line, 10)


class TestBuildGuardsAreRecordedAndResolved(unittest.TestCase):
    """A guard decides whether a declaration is in the binary we ship.

    Only `base::Feature` recorded one, so the fork shadow analysis could see
    11% of the surface and none of the preference keys -- the thing the README
    calls the most expensive to get wrong. Resolving the guard for Windows also
    gives the scoring stage something to act on: 115 keys at M151 are not in a
    Windows build at all, and nothing had marked them.
    """

    def _pref(self, source):
        from chromedrift.extract import constants
        return {f.key: f.attrs for f in constants.extract(source, "components/x/pref_names.cc")}

    def test_a_headers_include_guard_is_not_a_build_guard(self):
        from chromedrift.extract import constants
        source = ('#ifndef COMPONENTS_X_PREF_NAMES_H_\n'
                  '#define COMPONENTS_X_PREF_NAMES_H_\n'
                  'inline constexpr char kA[] = "a.b";\n'
                  '#endif\n')
        attrs = {f.key: f.attrs for f in
                 constants.extract(source, "components/x/pref_names.h")}
        self.assertNotIn("conditions", attrs["a.b"])
        self.assertNotIn("platform_state", attrs["a.b"])

    def test_a_platform_guard_is_recorded_and_resolved(self):
        attrs = self._pref('#if BUILDFLAG(IS_CHROMEOS)\n'
                           'inline constexpr char kA[] = "a.b";\n#endif\n')
        self.assertEqual(attrs["a.b"]["conditions"], ["BUILDFLAG(IS_CHROMEOS)"])
        self.assertEqual(attrs["a.b"]["platform_state"], {"windows": "not_compiled"})

    def test_a_guard_that_keeps_us_records_no_state(self):
        """Unguarded and "guarded but still ours" must compare as the same."""
        attrs = self._pref('#if !BUILDFLAG(IS_ANDROID)\n'
                           'inline constexpr char kA[] = "a.b";\n#endif\n')
        self.assertNotIn("platform_state", attrs["a.b"])

    def test_a_non_platform_buildflag_is_not_guessed(self):
        attrs = self._pref('#if BUILDFLAG(ENABLE_PLUGINS)\n'
                           'inline constexpr char kA[] = "a.b";\n#endif\n')
        self.assertEqual(attrs["a.b"]["platform_state"], {"windows": "conditional"})

    def test_an_elif_branch_carries_the_branches_above_it(self):
        from chromedrift.extract._cpp import conditional_spans, enclosing_conditions
        source = ('#if defined(ACME_X)\nA\n'
                  '#elif BUILDFLAG(IS_WIN)\nB\n#else\nC\n#endif\n')
        spans = conditional_spans(source)
        self.assertEqual(enclosing_conditions(spans, source.index("\nB") + 1),
                         ["!(defined(ACME_X))", "BUILDFLAG(IS_WIN)"])
        self.assertEqual(enclosing_conditions(spans, source.index("\nC") + 1),
                         ["!(defined(ACME_X))", "!(BUILDFLAG(IS_WIN))"])

    def test_a_plain_else_is_unchanged(self):
        from chromedrift.extract._cpp import conditional_spans, enclosing_conditions
        source = "#if BUILDFLAG(IS_WIN)\nA\n#else\nB\n#endif\n"
        self.assertEqual(
            enclosing_conditions(conditional_spans(source), source.index("\nB") + 1),
            ["!(BUILDFLAG(IS_WIN))"])

    def test_a_grit_condition_is_read_by_the_same_evaluator(self):
        from chromedrift.extract._cpp import eval_grit_condition
        self.assertIs(eval_grit_condition("not is_win"), False)
        self.assertIs(eval_grit_condition("is_win or is_macosx"), True)
        self.assertIs(eval_grit_condition("is_macosx or is_linux"), False)
        self.assertIsNone(eval_grit_condition("_google_chrome"))

    def test_a_control_grit_excludes_is_scored_down(self):
        from chromedrift.impact import NOT_COMPILED_PENALTY, score_change
        from chromedrift.model import Change
        change = Change(change_type="modified", kind="webui_control",
                        key="k", name="k",
                        after={"platform_state": {"windows": "not_compiled"}})
        finding = score_change(change, TouchSet())
        self.assertTrue(any(str(NOT_COMPILED_PENALTY) in r
                            for r in finding.reasons), finding.reasons)


class TestShadowAnalysisSeesEveryGuard(unittest.TestCase):
    """A vendor guard is a vendor guard in either dialect.

    `_vendor_guards` read `conditions` only, which `base_features` alone
    recorded. The `-si` filename marker in the shipped profile points at a
    settings template, whose guard is a GRIT `<if expr>` under
    `build_conditions` -- so the one example the documentation gives was the
    one shape the analysis could not see.
    """

    def _markers(self):
        from chromedrift.coverage import VendorMarkers
        return VendorMarkers.from_profile(
            {"vendor_markers": {"macros": ["ACME"]}})

    def _guards(self, attrs):
        from chromedrift.coverage import _vendor_guards
        from chromedrift.model import Fact
        return _vendor_guards(Fact("pref", "k", "k", attrs=attrs), self._markers())

    def test_a_cpp_guard_is_found(self):
        self.assertEqual(self._guards({"conditions": ["defined(ACME_A)"]}),
                         ["defined(ACME_A)"])

    def test_a_grit_guard_is_found(self):
        self.assertEqual(self._guards({"build_conditions": ["acme_custom"]}),
                         ["acme_custom"])

    def test_an_upstream_platform_guard_is_not_ours(self):
        self.assertEqual(self._guards({"conditions": ["BUILDFLAG(IS_WIN)"],
                                       "build_conditions": ["is_win"]}), [])

    def test_a_guarded_pref_reads_as_shadowed(self):
        from chromedrift.coverage import SHADOWED, analyze
        from chromedrift.model import Fact, Snapshot
        upstream = Snapshot(ref="up", facts=[Fact("pref", "a.b", "a.b",
                                                  attrs={"var": "kA"})])
        fork = Snapshot(ref="fork", facts=[
            Fact("pref", "a.b", "a.b",
                 attrs={"var": "kA", "conditions": ["defined(ACME_A)"]})])
        report = analyze(fork=fork, upstream=upstream, markers=self._markers())
        self.assertEqual([v.state for v in report.verdicts], [SHADOWED])


class TestEveryComparedAttributeIsExplained(unittest.TestCase):
    """A row with a severity and a blank reason column is unreadable.

    An attribute in `MEANINGFUL_ATTRS` is there because someone decided a
    change to it carries downstream meaning. If it then moves and the report
    says nothing about what moved, the reader has to open the source. Measured
    M148 -> M151, 380 of 709 modified changes arrived that way, including a
    preference whose C++ constant had been renamed.
    """

    def _change(self, kind, attr, before, after):
        from chromedrift.diff import _make_change
        from chromedrift.model import Fact
        old = Fact(kind, "k", "k", path="components/x/y.cc", attrs={attr: before})
        new = Fact(kind, "k", "k", path="components/x/y.cc", attrs={attr: after})
        return _make_change("modified", old, new, "windows", 151,
                            {attr: [before, after]})

    CASES = [
        ("pref", "var", "kOld", "kNew", "pref_symbol_renamed"),
        ("switch", "var", "kOld", "kNew", "switch_symbol_renamed"),
        ("pref", "platform_state", None, {"windows": "not_compiled"},
         "build_gate_changed"),
        ("idl_member", "ext", {"A": True}, {}, "web_api_exposure_changed"),
        ("idl_member", "runtime_enabled", "A", "B", "web_api_exposure_changed"),
        ("idl_interface", "values", ["a"], ["a", "b"], "web_api_shape_changed"),
        ("idl_interface", "inherits", "", "Base", "web_api_shape_changed"),
        ("webui_control", "build_conditions", ["is_win"], ["not is_win"],
         "build_gate_changed"),
        ("webui_control", "label", "a", "b", "ui_control_relabelled"),
        ("flag_entry", "expiry_milestone", 150, 160, "flag_expiry_moved"),
    ]

    def test_each_attribute_produces_its_signal(self):
        for kind, attr, before, after, expected in self.CASES:
            change = self._change(kind, attr, before, after)
            self.assertIn(expected, change.signals, f"{kind}.{attr}")

    def test_a_blink_flag_losing_its_feature_says_so(self):
        from chromedrift.diff import _make_change
        from chromedrift.model import Fact
        old = Fact("blink_runtime_feature", "F", "F", attrs={"base_feature": "F"})
        new = Fact("blink_runtime_feature", "F", "F", attrs={"base_feature": "none"})
        change = _make_change("modified", old, new, "windows", 151,
                              {"base_feature": ["F", "none"]})
        self.assertIn("runtime_flag_rewired", change.signals)

    def test_labelling_the_expiry_moves_changed_no_ranking(self):
        """281 of them at M148 -> M151; the floor stays under the base."""
        from chromedrift.diff import BASE_SEVERITY, SIGNAL_SEVERITY
        self.assertLess(SIGNAL_SEVERITY["flag_expiry_moved"],
                        BASE_SEVERITY[("flag_entry", "modified")])

    def test_no_modified_change_in_the_real_range_is_unexplained(self):
        import glob

        from chromedrift.diff import diff_snapshots
        from chromedrift.model import SCHEMA_VERSION, Snapshot, read_json

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        snaps = {}
        for path in glob.glob(os.path.join(root, ".chromedrift-cache",
                                           "snapshots", "*.default.json")):
            blob = read_json(path)
            if blob.get("schema") == SCHEMA_VERSION:
                snaps[blob["ref"]] = Snapshot.from_dict(blob)
        if len(snaps) < 2:
            self.skipTest("needs two current-schema default snapshots")
        old, new = [snaps[r] for r in sorted(snaps)[:2]]
        mute = [c for c in diff_snapshots(old, new)
                if c.change_type == "modified" and not c.signals]
        self.assertEqual(
            [(c.kind, sorted(c.deltas)) for c in mute], [],
            "these attributes are compared and then never explained")


class TestEveryFactPointsAtItsDeclaration(unittest.TestCase):
    """A citation that stops at the filename is not a citation.

    `content_features.cc` declares nearly two hundred features -- the same
    argument the scoring stage uses to rank symbol evidence above path
    evidence. Four of the thirteen kinds set no line at all (every Mojo method,
    every IDL member, every Blink flag, every chrome://flags entry: 20,844 of
    36,356 facts), a fifth set one that was wrong, and nothing downstream read
    the field anyway.
    """

    MOJOM = ("module blink.mojom;\n"
             "\n"
             "// A comment that masking turns into blank space,\n"
             "// several lines of it.\n"
             "\n"
             "interface Pinger {\n"
             "  Ping(int32 n) => (bool ok);\n"
             "  Pong();\n"
             "};\n")

    IDL = ("interface Thing {\n"
           "  readonly attribute long width;\n"
           "  void resize(long w);\n"
           "};\n")

    JSON5 = ('{\n'
             '  data: [\n'
             '    {\n'
             '      name: "Alpha",\n'
             '      status: "stable",\n'
             '    },\n'
             '    { name: "Beta", status: "experimental" },\n'
             '  ],\n'
             '}\n')

    FLAGS = ('[\n'
             '  {\n'
             '    "name": "alpha-flag",\n'
             '    "expiry_milestone": 150\n'
             '  },\n'
             '  { "name": "beta-flag", "expiry_milestone": 151 }\n'
             ']\n')

    def _lines(self, facts, source):
        rows = source.splitlines()
        return {f.name: (f.line, rows[f.line - 1] if f.line else "") for f in facts}

    def test_a_mojo_interface_is_not_reported_at_the_line_above_it(self):
        """`\\s*` after the newline crossed the comment block and the blank
        line, so 1,453 of 1,455 interfaces at M151 pointed at the wrong line."""
        from chromedrift.extract import mojom
        found = self._lines(mojom.extract(self.MOJOM, "a/b.mojom"), self.MOJOM)
        self.assertEqual(found["Pinger"][0], 6)
        self.assertIn("interface Pinger", found["Pinger"][1])

    def test_every_mojo_method_has_its_own_line(self):
        from chromedrift.extract import mojom
        found = self._lines(mojom.extract(self.MOJOM, "a/b.mojom"), self.MOJOM)
        self.assertEqual(found["Ping"][0], 7)
        self.assertEqual(found["Pong"][0], 8)

    def test_every_idl_member_has_its_own_line(self):
        from chromedrift.extract import web_idl
        path = "third_party/blink/renderer/core/x.idl"
        found = self._lines(web_idl.extract(self.IDL, path), self.IDL)
        self.assertEqual(found["width"][0], 2)
        self.assertEqual(found["resize"][0], 3)

    def test_a_blink_flag_has_a_line_on_either_layout(self):
        from chromedrift.extract import blink_runtime
        path = "third_party/blink/renderer/platform/runtime_enabled_features.json5"
        found = self._lines(blink_runtime.extract(self.JSON5, path), self.JSON5)
        self.assertEqual(found["Alpha"][0], 4)
        self.assertEqual(found["Beta"][0], 7, "a brace sharing the line still counts")

    def test_a_flag_entry_has_a_line_on_either_layout(self):
        from chromedrift.extract import flags_metadata
        path = "chrome/browser/flag-metadata.json"
        found = self._lines(flags_metadata.extract(self.FLAGS, path), self.FLAGS)
        self.assertEqual(found["alpha-flag"][0], 3)
        self.assertEqual(found["beta-flag"][0], 6)

    def test_the_line_never_walks_back_to_the_line_above(self):
        """`\\s` matches newlines; `[ \\t]` is what these patterns need."""
        from chromedrift.extract import blink_runtime, flags_metadata
        for module, source, name in (
                (blink_runtime, self.JSON5, "Alpha"),
                (flags_metadata, self.FLAGS, "alpha-flag")):
            lines = module.name_lines(source)
            self.assertIn(name, source.splitlines()[lines[name] - 1])

    def test_the_change_carries_the_place_not_just_the_file(self):
        from chromedrift.diff import _make_change
        from chromedrift.model import Fact
        old = Fact("mojo_method", "k", "k", path="a/b.mojom", line=41)
        new = Fact("mojo_method", "k", "k", path="a/b.mojom", line=87)
        change = _make_change("modified", old, new, "windows", 151,
                              {"signature": ["x", "y"]})
        self.assertEqual(change.locations, ["a/b.mojom:41", "a/b.mojom:87"])
        self.assertEqual(change.paths, ["a/b.mojom"],
                         "the profile matches path prefixes; keep them clean")

    def test_both_renderers_show_it(self):
        from chromedrift.model import Change, Finding, Report
        from chromedrift.report import html as html_report
        from chromedrift.report import markdown as md_report
        change = Change(change_type="modified", kind="mojo_method",
                        key="blink.mojom.X.Y", name="Y",
                        paths=["a/b.mojom"], locations=["a/b.mojom:41"],
                        signals=["ipc_signature_change"], severity=80)
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=change, score=80,
                                          bucket="review")])
        self.assertIn("a/b.mojom:41", md_report.render(report))
        self.assertIn("a/b.mojom:41", html_report.render(report))

    def test_a_report_from_before_this_still_renders(self):
        """Version 20 reports have no locations; fall back to the file."""
        from chromedrift.model import Report
        from chromedrift.report import markdown as md_report
        blob = {"from_ref": "a", "to_ref": "b", "findings": [{
            "change": {"change_type": "modified", "kind": "mojo_method",
                       "key": "k", "name": "Y", "paths": ["a/b.mojom"],
                       "signals": [], "severity": 80},
            "score": 80, "bucket": "review"}]}
        text = md_report.render(Report.from_dict(blob))
        self.assertIn("a/b.mojom", text)


class TestWebIdlReadsOnlyWebIdl(unittest.TestCase):
    """Three languages share the `.idl` extension in this tree.

    Chrome Extensions IDL wraps `dictionary` and `interface Functions` blocks
    in a `namespace`, so the whole nested body parsed as one member: 96 of the
    1,081 facts it produced at M151 had another declaration inside their own
    signature, and the rest were reported as Web API changes -- where
    `web_api_removed` reads "site-visible break" and no site can call
    `chrome.fileManagerPrivate`. `ichromeaccessible.idl` is MIDL, which spells
    `interface X : IUnknown {` the same way.

    Reading a dialect wrongly is worse than a stated gap.
    """

    EXTENSION_IDL = ('namespace fileSystem {\n'
                     '  dictionary AcceptOption {\n'
                     '    DOMString? description;\n'
                     '  };\n'
                     '};\n')

    def test_blink_idl_is_read(self):
        from chromedrift.extract import web_idl
        self.assertTrue(web_idl.applies_to(
            "third_party/blink/renderer/modules/webgl/x.idl"))
        self.assertTrue(web_idl.applies_to(
            "third_party/blink/renderer/core/dom/element.idl"))

    def test_the_extensions_dialect_is_not(self):
        from chromedrift.extract import web_idl
        for path in ("chrome/common/extensions/api/file_manager_private.idl",
                     "extensions/common/api/file_system.idl",
                     "chrome/common/apps/platform_apps/api/x.idl",
                     "ui/accessibility/platform/ichromeaccessible.idl"):
            self.assertFalse(web_idl.applies_to(path), path)

    def test_it_would_have_read_the_namespace_as_an_interface(self):
        """Kept as the evidence for why the door is shut.

        The extension's `namespace` becomes one Web IDL interface and the
        dictionaries inside it disappear, so the surface is neither absent nor
        present but misdescribed -- the outcome this project treats as worse
        than a gap.
        """
        from chromedrift.extract import web_idl
        facts = web_idl.extract(self.EXTENSION_IDL,
                                "third_party/blink/renderer/x.idl")
        self.assertEqual([(f.kind, f.key) for f in facts],
                         [("idl_interface", "fileSystem")])


class TestEveryTreeWalkIsSorted(unittest.TestCase):
    """One unsorted walk was enough to make a snapshot machine-dependent.

    Fixing the one in `run_on_tree` and leaving four others is the shape of
    problem this project keeps finding: the same decision made in several
    places, and only some of them right. None of the remaining four can produce
    a wrong answer today -- they feed sets, dicts or a sorted list -- but that
    is a property of their callers, not of them.
    """

    def test_no_walk_leaves_directory_order_to_the_filesystem(self):
        import glob

        # Written as a substring check rather than a lookahead: `\s*=\s*(?!x)`
        # backtracks the whitespace away and then matches everything, which is
        # how the first version of this test reported all six lines as broken.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for path in glob.glob(os.path.join(root, "chromedrift", "**", "*.py"),
                              recursive=True):
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if "dirnames[:]" in line and "= sorted" not in line:
                        offenders.append(f"{os.path.basename(path)}:{lineno}")
        self.assertEqual(offenders, [])

    def test_discover_splits_the_worklist_the_way_extraction_reads(self):
        """A vendor file under a test directory is not a missing target."""
        from chromedrift.discover import _readable_by_any_extractor

        self.assertTrue(_readable_by_any_extractor(
            "chrome/browser/acme/acme_features.cc"))
        self.assertFalse(_readable_by_any_extractor(
            "chrome/browser/acme/test/acme_features.cc"),
            "extraction skips it, so adding a target would not fix anything")
        self.assertFalse(_readable_by_any_extractor(
            "chrome/browser/acme/toolbar.grd"))


class TestTheReportSaysWhatChangedOnEachScreen(unittest.TestCase):
    """A row reading `id:cancelButton` answers none of the reader's questions.

    It does not say which page the control is on, whether it arrived or
    vanished, or what kind of control it is -- and the same loadTimeData key
    appears once per handler that sets it, so `webuiRefresh2026` showed up nine
    times with nothing to tell the nine apart. Every field needed to answer all
    of that was already on the facts and was simply never rendered.
    """

    def _control(self, change_type="added", **attrs):
        from chromedrift.model import Change
        base = {"surface": "settings", "page": "privacy_page",
                "control": "settings-toggle-button", "element_id": "httpsOnly",
                "pref": "generated.https_first_mode_enabled", "label": ""}
        base.update(attrs)
        side = {"after": base} if change_type != "removed" else {"before": base}
        return Change(change_type=change_type, kind="webui_control",
                      key="settings/privacy_page/p/id:httpsOnly",
                      name="id:httpsOnly", **side)

    def test_a_control_names_its_screen(self):
        from chromedrift.report import wording as surfaces
        self.assertEqual(surfaces.screen_of(self._control()),
                         "settings › privacy_page")

    def test_a_gate_is_placed_by_the_handler_that_sets_it(self):
        """Otherwise every gate lands in one undifferentiated pile."""
        from chromedrift.model import Change
        from chromedrift.report import wording as surfaces
        for handler, screen in (("downloads_ui", "downloads"),
                                ("new_tab_page_ui", "new_tab_page"),
                                ("history_util", "history")):
            change = Change(change_type="added", kind="webui_gate",
                            key=f"{handler}/showThing", name="showThing",
                            after={"handler": handler, "features": ["kThing"]})
            self.assertEqual(surfaces.screen_of(change), screen)

    def test_a_control_is_described_in_words(self):
        from chromedrift.report import wording as surfaces
        self.assertEqual(
            surfaces.describe(self._control()),
            "toggle — httpsOnly (writes generated.https_first_mode_enabled)")

    def test_a_retyped_control_shows_both_types(self):
        from chromedrift.report import wording as surfaces
        change = self._control("modified", control="settings-toggle-button")
        change.deltas = {"control": ["settings-dropdown-menu",
                                     "settings-toggle-button"]}
        self.assertIn("dropdown → toggle", surfaces.describe(change))

    def test_a_route_says_what_shows_it(self):
        from chromedrift.model import Change
        from chromedrift.report import wording as surfaces
        change = Change(change_type="added", kind="webui_route",
                        key="settings/AI", name="AI",
                        after={"surface": "settings", "route": "/ai",
                               "guards": ["showAiPage"]})
        self.assertEqual(surfaces.describe(change),
                         "page /ai (shown when showAiPage)")

    def test_screens_group_and_count_by_direction(self):
        from chromedrift.model import Finding
        from chromedrift.report import wording as surfaces
        findings = [Finding(change=self._control("added"), score=30),
                    Finding(change=self._control("removed"), score=20),
                    Finding(change=self._control("modified"), score=40)]
        screens = surfaces.build(findings)
        self.assertEqual([s.name for s in screens], ["settings › privacy_page"])
        self.assertEqual(screens[0].headline(), "1 new · 1 changed · 1 gone")
        self.assertEqual(surfaces.summarize(screens),
                         {"screens": 1, "added": 1, "changed": 1, "removed": 1})

    def test_new_things_are_listed_first(self):
        """"What is new here" is the question people arrive with."""
        from chromedrift.model import Finding
        from chromedrift.report import wording as surfaces
        findings = [Finding(change=self._control("removed"), score=90),
                    Finding(change=self._control("added"), score=10)]
        order = [f.change.change_type
                 for f in surfaces.build(findings)[0].sorted_items()]
        self.assertEqual(order, ["added", "removed"])

    def test_nothing_but_screens_is_grouped(self):
        from chromedrift.model import Change, Finding
        from chromedrift.report import wording as surfaces
        flag = Change(change_type="added", kind="base_feature", key="F", name="F")
        self.assertEqual(surfaces.build([Finding(change=flag)]), [])

    def test_both_renderers_carry_the_section(self):
        from chromedrift.model import Finding, Report
        from chromedrift.report import html as html_report
        from chromedrift.report import markdown as md_report
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=self._control(), score=30,
                                          bucket="review")])
        for text in (md_report.render(report), html_report.render(report)):
            self.assertIn("What changed on each screen", text)
            self.assertIn("settings › privacy_page", text)
            self.assertIn("toggle", text)

    def test_the_table_carries_the_direction_and_the_place(self):
        """Both were reachable only by opening a row, or not at all."""
        from chromedrift.model import Finding, Report
        from chromedrift.report import html as html_report
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=self._control(), score=30,
                                          bucket="review")])
        row = html_report._to_rows(report, "windows")[0]
        self.assertEqual(row["change_type"], "added")
        self.assertEqual(row["where"], "settings › privacy_page")
        self.assertIn("toggle", row["what"])

    def test_a_report_with_no_screens_renders_no_empty_section(self):
        from chromedrift.model import Change, Finding, Report
        from chromedrift.report import markdown as md_report
        flag = Change(change_type="added", kind="base_feature", key="F", name="F")
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=flag, score=20, bucket="fyi")])
        self.assertNotIn("What changed on each screen", md_report.render(report))


class TestTheReportSaysWhatHappened(unittest.TestCase):
    """A list of 2,792 rows is not a list of 2,792 things that happened.

    It is about forty, and the sentence for each was already written: the
    signal labels say "Shipped, then flag retired -- behaviour is now permanent
    and can no longer be turned off". Until this section existed that sentence
    was reachable only by expanding one table row at a time, so the report could
    say which row scored highest and never what the milestone did.
    """

    def _change(self, kind="base_feature", change_type="added", signals=(),
                **kw):
        from chromedrift.diff import _severity_for
        from chromedrift.model import Change
        change = Change(change_type=change_type, kind=kind,
                        key=kw.pop("key", "K"), name=kw.pop("name", "K"), **kw)
        change.signals = list(signals)
        change.severity = _severity_for(change)
        return change

    def test_the_story_is_the_signal_that_set_the_severity(self):
        """Otherwise a finding is filed under one sentence and ranked by another."""
        from chromedrift.diff import SIGNAL_SEVERITY, leading_signal
        from chromedrift.report import wording as surfaces

        change = self._change(signals=["flag_expiring", "flag_retired_on",
                                       "declaration_moved"])
        top = leading_signal(change)
        self.assertEqual(top, max(change.signals,
                                  key=lambda s: SIGNAL_SEVERITY[s]))
        self.assertEqual(surfaces.story_of(change)[0], top)
        self.assertEqual(change.severity, SIGNAL_SEVERITY[top])

    def test_the_pick_does_not_depend_on_signal_order(self):
        from chromedrift.report import wording as surfaces
        pair = ["flag_expiring", "flag_retired_on"]
        first = surfaces.story_of(self._change(signals=pair))
        second = surfaces.story_of(self._change(signals=list(reversed(pair))))
        self.assertEqual(first, second)

    def test_a_change_with_no_signal_still_has_a_headline(self):
        """A third of a real report carries no signal -- things that only arrived."""
        from chromedrift.model import ALL_KINDS
        from chromedrift.report import wording as surfaces
        for kind in ALL_KINDS:
            for direction in ("added", "removed", "modified"):
                key, headline = surfaces.story_of(
                    self._change(kind=kind, change_type=direction))
                self.assertTrue(key and headline, (kind, direction))
                # A lowercase URL scheme must not be sentence-cased into
                # `Chrome://flags entry`.
                self.assertNotIn("Chrome://", headline)

    def test_every_finding_lands_in_exactly_one_story(self):
        """The section is a partition of the report, not a highlight reel."""
        from chromedrift.model import ALL_KINDS, KIND_GROUPS, Finding
        from chromedrift.report import wording as surfaces

        findings = []
        for i, kind in enumerate(ALL_KINDS):
            for direction in ("added", "removed", "modified"):
                findings.append(Finding(
                    change=self._change(kind=kind, change_type=direction,
                                        key=f"{kind}/{direction}/{i}",
                                        signals=["declaration_moved"] if i % 3
                                        else []),
                    score=10 + i))
        seen = []
        for _, kinds in KIND_GROUPS:
            for story in surfaces.build_stories(findings, kinds):
                seen += [id(f) for f in story.items]
        self.assertEqual(sorted(seen), sorted(id(f) for f in findings))
        self.assertEqual(len(set(seen)), len(seen), "a finding was counted twice")

    def test_every_kind_belongs_to_exactly_one_group(self):
        """The group is printed on every row; a kind in none of them prints blank."""
        from chromedrift.model import ALL_KINDS, KIND_GROUPS, group_of
        grouped = [k for _, kinds in KIND_GROUPS for k in kinds]
        self.assertEqual(sorted(grouped), sorted(ALL_KINDS))
        self.assertEqual(len(set(grouped)), len(grouped))
        self.assertTrue(all(group_of(k) for k in ALL_KINDS))

    def test_the_heaviest_story_leads(self):
        from chromedrift.model import Finding
        from chromedrift.report import wording as surfaces
        findings = [
            Finding(change=self._change(key="a", signals=["flag_expiring"])),
            Finding(change=self._change(key="b", signals=["enabled_by_default"])),
            Finding(change=self._change(key="c", signals=["flag_expiring"])),
        ]
        titles = [s.title for s in
                  surfaces.build_stories(findings, ("base_feature",))]
        self.assertEqual(titles[0], "Now ON by default on Windows",
                         "one severity-75 finding outranks two severity-45 ones")

    def test_both_renderers_carry_the_section(self):
        from chromedrift.model import Finding, Report
        from chromedrift.report import html as html_report
        from chromedrift.report import markdown as md_report
        report = Report(from_ref="a", to_ref="b", findings=[
            Finding(change=self._change(signals=["enabled_by_default"]),
                    score=75, bucket="review")])
        for text in (md_report.render(report), html_report.render(report)):
            self.assertIn("Now ON by default on Windows", text)
            self.assertIn("Behaviour switches", text)
            # The group name alone says nothing; the sentence beside it does.
            self.assertIn("moves behaviour on its own", text)

    def test_the_html_says_what_happened_on_every_row(self):
        """The column is only useful if the lookup table holds every key."""
        import json
        import re

        from chromedrift.model import Finding, Report
        from chromedrift.report import html as html_report

        report = Report(from_ref="a", to_ref="b", findings=[
            Finding(change=self._change(key="a", signals=["enabled_by_default"]),
                    score=75, bucket="review"),
            Finding(change=self._change(key="b", kind="flag_entry",
                                        change_type="removed"),
                    score=30, bucket="fyi")])
        text = html_report.render(report)
        rows = json.loads(re.search(r"window\.__FINDINGS__=(\[.*?\]);\n",
                                    text, re.S).group(1))
        # The map is the last assignment in its script block, so it ends at
        # the tag rather than at a newline.
        stories = json.loads(re.search(r"window\.__STORIES__=(\{.*?\});[\n<]",
                                       text, re.S).group(1))
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIn(row["why"], stories)
            self.assertTrue(stories[row["why"]])

    def test_every_printed_count_matches_the_rows_it_filters_to(self):
        """Each count is a link that filters the table; the two must agree.

        The summary sections and the table are built from the same findings by
        different code, so a count that counted something slightly different --
        changes rather than findings, or a kind list that drifted from the
        group -- would send the reader to a table showing a different number
        from the one they clicked.
        """
        import json
        import re

        from chromedrift.model import ALL_KINDS, BUCKET_ORDER, Finding, Report
        from chromedrift.report import html as html_report

        findings = []
        for i, kind in enumerate(ALL_KINDS):
            for j in range(i % 3 + 1):
                findings.append(Finding(
                    change=self._change(kind=kind, key=f"{kind}/{j}",
                                        signals=["declaration_moved"]),
                    score=20 + j, bucket=BUCKET_ORDER[i % len(BUCKET_ORDER)]))
        text = html_report.render(Report(from_ref="a", to_ref="b",
                                         findings=findings))
        rows = json.loads(re.search(r"window\.__FINDINGS__=(\[.*?\]);\n",
                                    text, re.S).group(1))

        # Every chip and card: `data-set="fk:pref"` ... `<b>3</b>` or `<div
        # class="n">3</div>`, depending on which one it is.
        printed = re.findall(
            r'data-set="(\w+):([\w_]+)"[^>]*>(.*?)</a>', text, re.S)
        self.assertTrue(printed)
        for which, value, body in printed:
            count = int(re.search(r"([\d,]+)\s*</(?:b|div)>", body)
                        .group(1).replace(",", ""))
            field = {"fk": "kind", "fb": "bucket"}[which]
            self.assertEqual(count, sum(1 for r in rows if r[field] == value),
                             f"{which}:{value} sends the reader to a different "
                             f"number from the one it prints")

    def test_the_three_group_totals_agree_wherever_they_are_printed(self):
        """The nav, the group card and the section heading print the same number.

        They used to count it three times from three loops, which is how two of
        them come to disagree after someone edits one.
        """
        import json
        import re

        from chromedrift.model import (ALL_KINDS, KIND_GROUPS, Finding, Report,
                                       group_of)
        from chromedrift.report import html as html_report

        findings = [Finding(change=self._change(kind=kind, key=f"{kind}/{j}"),
                            score=20, bucket="fyi")
                    for i, kind in enumerate(ALL_KINDS)
                    for j in range(i % 4 + 1)]
        text = html_report.render(Report(from_ref="a", to_ref="b",
                                         findings=findings))
        rows = json.loads(re.search(r"window\.__FINDINGS__=(\[.*?\]);\n",
                                    text, re.S).group(1))
        total = 0
        for group_name, _ in KIND_GROUPS:
            expected = sum(1 for r in rows if group_of(r["kind"]) == group_name)
            total += expected
            printed = re.findall(
                re.escape(group_name) + r"\s*<(?:b|span)[^>]*>([\d,]+)<", text)
            self.assertEqual(len(printed), 3,
                             f"{group_name}: the nav, the card and the section "
                             f"heading each print it; found {printed}")
            self.assertEqual({int(p.replace(",", "")) for p in printed},
                             {expected}, group_name)
            self.assertIn(f'id="g-{group_name.split()[0].lower()}"', text)
        self.assertEqual(total, len(rows), "a kind belongs to no group")

    def test_a_long_delta_does_not_take_over_the_table_cell(self):
        """A Mojo signature runs past 400 characters."""
        from chromedrift.model import Finding, Report
        from chromedrift.report import html as html_report

        change = self._change(kind="mojo_method", change_type="modified",
                              signals=["ipc_signature_change"])
        change.deltas = {"signature": ["uint32 a, " * 60, "uint32 b, " * 60]}
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=change, score=80,
                                          bucket="review")])
        row = html_report._to_rows(report, "windows")[0]
        self.assertLessEqual(len(row.get("moved", "")), 80)
        # The full value stays one click away.
        self.assertTrue(row["deltas"])



class TestNoCoverageNumberIsHardcoded(unittest.TestCase):
    """Nothing shown to a user may quote a coverage figure of its own.

    Coverage changes whenever a filter changes, and it has gone stale twice:
    help text and a log line were still advertising 96% after `wide` reached
    100%. Every run measures its own coverage and prints it, so a second copy
    in a string can only ever disagree with the first.

    Comments recording a historical measurement are fine -- they name the
    milestone they were taken at. This guards the strings that reach a user.
    """

    CLAIM = re.compile(r"\d+\s*%+\s*of (the )?(files|declarations)")

    def _user_visible_strings(self):
        """Every argparse `help=` and every string logged, across the package."""
        import ast
        import glob

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for path in glob.glob(os.path.join(root, "chromedrift", "**", "*.py"),
                              recursive=True):
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                if name == "log":
                    args = list(node.args)
                elif name == "add_argument":
                    args = [kw.value for kw in node.keywords if kw.arg == "help"]
                else:
                    continue
                for arg in args:
                    for sub in ast.walk(arg):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                            yield os.path.basename(path), sub.lineno, sub.value

    def test_no_help_text_or_log_line_quotes_a_percentage(self):
        offenders = [f"{f}:{n}  {t.strip()[:60]}"
                     for f, n, t in self._user_visible_strings()
                     if self.CLAIM.search(t)]
        self.assertEqual(offenders, [])


class TestEveryFlagIsActedOn(unittest.TestCase):
    """A command must not accept a flag it then ignores.

    Every subcommand used to inherit one shared parent parser, so `catalog`
    advertised --local-src, --refresh and --mode and did nothing with any of
    them, and `discover` advertised eight it ignored. The worst of those was
    --complete: catalog took it, dropped it, and measured the run against the
    curated file list that --complete exists to replace -- reporting as
    missing every file the run does fetch.
    """

    # Flags argparse always adds, and positional/handler plumbing.
    IGNORED = {"help", "func", "command"}

    def _handler_reads(self, name):
        import ast

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "chromedrift", "cli.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == f"cmd_{name}")
        return {n.attr for n in ast.walk(fn)
                if isinstance(n, ast.Attribute)
                and getattr(n.value, "id", "") == "args"}

    def test_no_subcommand_offers_a_flag_it_never_reads(self):
        from chromedrift.cli import build_parser

        parser = build_parser()
        commands = parser._subparsers._group_actions[0].choices
        unused = {}
        for name, sub in commands.items():
            offered = {a.dest for a in sub._actions} - self.IGNORED
            leftover = sorted(offered - self._handler_reads(name))
            if leftover:
                unused[name] = leftover
        self.assertEqual(unused, {})


class TestTheRemovedVerdictStageLeavesNoTrace(unittest.TestCase):
    """The AI stage is gone. Help text and docstrings must not advertise it."""

    def test_the_run_command_help_does_not_promise_ai(self):
        from chromedrift.cli import build_parser

        parser = build_parser()
        run = parser._subparsers._group_actions[0].choices["run"]
        self.assertNotIn("AI", run.description or "")
        text = " ".join(
            c.help or "" for c in
            parser._subparsers._group_actions[0]._choices_actions)
        self.assertNotIn("AI", text)

    # "AI stage" was the only phrase this looked for, so five comments and
    # docstrings still described a model consuming the output -- including one
    # that justified a whole design decision by a context window that no longer
    # exists. A reader who believes them looks for a stage that is not there.
    TRACES = re.compile(
        r"\bAI stage\b|the model\b|\bLLM\b|context window|\bprompts?\b(?!_)"
        r"|tokens against", re.IGNORECASE)
    # `prompt_for_download` is a real Chromium preference key, quoted in an
    # extractor's docstring as sample markup.
    ALLOWED = re.compile(r"prompt_for_download|promptForDownload")

    def test_nothing_in_the_package_describes_a_model_reading_the_output(self):
        import glob

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for path in glob.glob(os.path.join(root, "chromedrift", "**", "*.py"),
                              recursive=True):
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if self.ALLOWED.search(line):
                        continue
                    if self.TRACES.search(line):
                        offenders.append(f"{os.path.basename(path)}:{lineno}: "
                                         f"{line.strip()[:60]}")
        self.assertEqual(offenders, [],
                         "the tool stops at the report; nothing may promise a "
                         "stage that was removed")

if __name__ == "__main__":
    unittest.main(verbosity=2)
