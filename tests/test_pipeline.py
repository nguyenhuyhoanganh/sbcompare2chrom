"""Diff, impact and reporting tests.

These cover the judgement calls -- what counts as a change, what counts as
evidence, what gets escalated -- because those are the parts that decide
whether the output is worth reading.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
                                 snap("sb-main-dev", new_facts),
                                 mode=MODE_FORK)
        return score_all(changes, TouchSet(name="SB", platform="windows"),
                         mode=MODE_FORK)

    def test_vendor_addition_is_not_an_opportunity(self):
        finding = self._fork_findings([], [feature("SbrowserSauce", "enabled")])[0]
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
        touch = TouchSet(name="SB", platform="windows", symbols={"kDropped"})
        from chromedrift.model import MODE_FORK
        changes = diff_snapshots(snap("148.0.0.0", [feature("Dropped", "enabled")]),
                                 snap("sb-main-dev", []), mode=MODE_FORK)
        finding = score_all(changes, touch, mode=MODE_FORK)[0]
        # We removed it and our own source names it: the next rebase puts it
        # back, so this is work, not trivia.
        self.assertEqual(finding.bucket, "must_fix")

    def test_uprev_mode_keeps_its_opportunity_bucket(self):
        """The fork branch must not quietly change uprev behaviour."""
        changes = diff_snapshots(snap("148.0.0.0", []),
                                 snap("151.0.0.0", [feature("Shiny", "enabled")]))
        finding = score_all(changes, TouchSet(name="SB", platform="windows"))[0]
        self.assertEqual(finding.bucket, "opportunity")

    def test_report_says_which_comparison_it_is(self):
        from chromedrift.model import MODE_FORK, Report
        from chromedrift.report import html as html_report
        from chromedrift.report import markdown as md_report

        findings = self._fork_findings([], [feature("SbrowserSauce", "enabled")])
        report = Report(from_ref="148.0.0.0", to_ref="sb-main-dev",
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
        return analyze(fork=snap("sb", fork_facts),
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
            [feature("SamsungOnly", "enabled")],
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
    after the rename, while missing every fork-mode signal -- the ones the SB
    comparison produces exclusively.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DOCS = ("README.md", "SETUP.md", "HANDOFF.md",
            "PIPELINE.md", "COVERAGE.md",
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
        from chromedrift.sbprofile import load_profile
        path = self._profile('{ name: "SB", platform: "android" }')
        with self.assertRaises(ValueError) as caught:
            load_profile(path, log=lambda m: None)
        self.assertIn("android", str(caught.exception))
        self.assertIn("windows", str(caught.exception))

    def test_windows_and_an_absent_field_both_work(self):
        from chromedrift.sbprofile import load_profile
        for body in ('{ name: "SB", platform: "windows" }',
                     '{ name: "SB", platform: "Windows" }',
                     '{ name: "SB" }'):
            touch = load_profile(self._profile(body), log=lambda m: None)
            self.assertEqual(touch.platform, "windows")

    def test_the_penalty_it_protects_still_applies(self):
        from chromedrift.model import Change
        change = Change(change_type="modified", kind="base_feature",
                        key="Foo", name="Foo",
                        after={"platform_state": {"windows": "not_compiled"}})
        finding = score_change(change, TouchSet(name="SB", platform="windows"))
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

    This fork is taken from Chromium whole, then its own files are placed
    *inside* Chromium's directories: a `samsung/` subfolder here, a `-si`
    suffix on a variant of an upstream component there. So "which files are
    ours" cannot be read off Chromium's layout, and after enough years nobody
    has the list. Both `vendor_markers` and the target list were being filled
    in from memory, and a forgotten path removes a whole surface from every
    comparison silently.
    """

    LAYOUT = (
        # upstream
        "chrome/browser/resources/settings/privacy_page/privacy_page.html",
        "chrome/browser/resources/settings/route.ts",
        # vendor variants of upstream components, inside upstream directories
        "chrome/browser/resources/settings/privacy_page/privacy_page-si.html",
        "chrome/browser/resources/downloads/item-si.html.ts",
        # vendor subfolder inside a tracked surface
        "chrome/browser/resources/settings/samsung/secret_mode.html",
        # vendor subfolder beside the surfaces, outside every target
        "chrome/browser/resources/samsung/quick_menu.html",
        # native UI: vendor-owned, but no extractor reads it
        "ui/samsung/views/sbrowser_toolbar.cc",
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
        return discover.scan(self.root, log=lambda m: None, **kw)

    def test_upstream_files_are_not_claimed(self):
        found = {h.path for h in self._scan().hits}
        self.assertNotIn("chrome/browser/resources/settings/route.ts", found)
        self.assertNotIn(
            "chrome/browser/resources/settings/privacy_page/privacy_page.html", found)

    def test_the_si_suffix_is_found_inside_an_upstream_directory(self):
        """No path prefix reaches it and it has no vendor symbol prefix."""
        from chromedrift.discover import BY_NAME
        hits = {h.path: h for h in self._scan().hits}
        for rel in ("chrome/browser/resources/settings/privacy_page/privacy_page-si.html",
                    "chrome/browser/resources/downloads/item-si.html.ts"):
            self.assertIn(rel, hits, rel)
            self.assertEqual(hits[rel].rule, BY_NAME)

    def test_a_double_extension_still_matches(self):
        """item-si.html.ts must strip both extensions before testing the stem."""
        report = self._scan()
        self.assertIn("-si", report.suffixes_seen())
        self.assertEqual(report.suffixes_seen()["-si"], 2)

    def test_samsung_folders_are_found_at_any_depth(self):
        from chromedrift.discover import BY_DIR
        hits = {h.path: h for h in self._scan().hits}
        for rel in ("chrome/browser/resources/settings/samsung/secret_mode.html",
                    "chrome/browser/resources/samsung/quick_menu.html",
                    "ui/samsung/views/sbrowser_toolbar.cc"):
            self.assertIn(rel, hits, rel)
            self.assertEqual(hits[rel].rule, BY_DIR)

    def test_uncovered_splits_what_can_be_fixed_from_what_cannot(self):
        """A worklist mixing the two is mostly unactionable."""
        from chromedrift.discover import uncovered_dirs
        fetchable, unreadable = uncovered_dirs(self._scan())
        self.assertIn("chrome/browser/resources/samsung",
                      [d for d, _ in fetchable])
        # Native C++ UI is vendor-owned and no extractor reads it; calling that
        # "missing" implies a fix that does not exist.
        self.assertIn("ui/samsung/views", [d for d, _ in unreadable])

    def test_macro_scanning_catches_the_common_shape(self):
        """SBROWSER_CUSTOM_DOWNLOADS, not only S_SBROWSER_X."""
        path = os.path.join(self.root, "chrome/browser/download/download_prefs.cc")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#if defined(SBROWSER_CUSTOM_DOWNLOADS)\n// ours\n#endif\n")
        report = self._scan(scan_content=True)
        self.assertIn("SBROWSER_CUSTOM_DOWNLOADS", report.macros)

    def test_the_suggested_profile_reflects_the_tree(self):
        from chromedrift.discover import suggest_profile
        text = suggest_profile(self._scan())
        self.assertIn('"samsung/"', text)
        self.assertIn('"-si"', text)

    def test_markers_recognise_a_si_file_as_ours(self):
        """The marker vocabulary had no way to express this before."""
        from chromedrift.coverage import VendorMarkers
        markers = VendorMarkers.from_profile(
            {"vendor_markers": {"path_markers": ["samsung/"],
                                "filename_markers": ["-si"]}})
        self.assertTrue(markers.path_is_ours(
            "chrome/browser/resources/settings/privacy_page-si.html"))
        self.assertTrue(markers.path_is_ours(
            "chrome/browser/resources/settings/item-si.html.ts"))
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

    def test_suffixes_cover_every_extractor(self):
        """A file an extractor can read but a complete fetch skips is a hole."""
        from chromedrift.targets import COMPLETE_SUFFIXES
        for sample in ("download_features.cc", "chrome_features.h",
                       "media_switches.cc", "pref_names.h", "foo.mojom",
                       "bar.idl", "page.html", "item.html.ts", "route.ts",
                       "runtime_enabled_features.json5"):
            self.assertTrue(any(sample.endswith(s) for s in COMPLETE_SUFFIXES),
                            f"{sample} is readable but would not be fetched")

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
            macros=["SBROWSER"], symbol_prefixes=["kSbrowser"],
            path_markers=["sbrowser/"])

    def _fact(self, name, state="enabled", conditions=(), path="a_features.cc"):
        f = feature(name, state, path=path)
        f.attrs["conditions"] = list(conditions)
        return f

    def test_identical_value_behind_a_vendor_guard_is_shadowed_not_untouched(self):
        from chromedrift.coverage import SHADOWED, analyze

        report = analyze(
            fork=snap("sb", [self._fact("Foo", "enabled",
                                        ["defined(SBROWSER_CUSTOM)"])]),
            upstream=snap("148.0.0.0", [self._fact("Foo", "enabled")]),
            markers=self.MARKERS)

        # The value matches exactly. Only the guard reveals the shadow.
        self.assertEqual(report.verdicts[0].state, SHADOWED)
        self.assertEqual(report.verdicts[0].guards, ["defined(SBROWSER_CUSTOM)"])

    def test_unguarded_identical_declaration_is_untouched(self):
        from chromedrift.coverage import UNTOUCHED, analyze

        report = analyze(
            fork=snap("sb", [self._fact("Foo", "enabled")]),
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
        report = analyze(fork=snap("sb", [guarded()]),
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
            fork=snap("sb", [self._fact("Foo", "enabled",
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
        report = analyze(fork=snap("sb", [ours]),
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

        mine = self._fact("SbrowserThing", "enabled",
                          ["defined(SBROWSER_CUSTOM)"])
        leftover = self._fact("LongDeadUpstreamFlag", "enabled")
        report = analyze(fork=snap("sb", [mine, leftover]),
                         upstream=snap("148.0.0.0", []),
                         markers=self.MARKERS)
        states = {v.key: v.state for v in report.verdicts}
        self.assertEqual(states["SbrowserThing"], VENDOR_ONLY)
        self.assertEqual(states["LongDeadUpstreamFlag"], ORPHANED)

    def test_guards_used_reports_what_each_flag_covers(self):
        from chromedrift.coverage import analyze

        report = analyze(
            fork=snap("sb", [self._fact("A", "enabled", ["defined(SBROWSER_UI)"]),
                             self._fact("B", "enabled", ["defined(SBROWSER_UI)"])]),
            upstream=snap("148.0.0.0", [self._fact("A"), self._fact("B")]),
            markers=self.MARKERS)
        self.assertEqual(report.guards_used(), {"defined(SBROWSER_UI)": 2})

    def test_without_markers_the_analysis_is_skipped_not_guessed(self):
        from chromedrift.coverage import VendorMarkers, analyze

        report = analyze(
            fork=snap("sb", [self._fact("Foo", "enabled", ["defined(X)"])]),
            upstream=snap("148.0.0.0", [self._fact("Foo")]),
            markers=VendorMarkers())
        self.assertFalse(report.markers_configured)
        self.assertEqual(report.verdicts, [])

    def test_guard_appearing_is_itself_a_change(self):
        """The value never moves; the guard around it does."""
        old = self._fact("Foo", "enabled")
        new = self._fact("Foo", "enabled", ["defined(SBROWSER_CUSTOM)"])
        changes = diff_snapshots(snap("148.0.0.0", [old]), snap("sb", [new]),
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
