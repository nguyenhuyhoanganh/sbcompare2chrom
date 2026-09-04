"""Diff, scoring and reporting tests.

These cover the judgement calls -- what counts as a change, what it is called,
and how far up the list it goes -- because those are the parts that decide
whether the output is worth reading.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chromiumdiff.diff import diff_snapshots
from chromiumdiff.extract import mojom
from chromiumdiff.model import (ADDED, BUCKET_HOUSEKEEPING, Fact, REMOVED,
                               Report, Snapshot)
from chromiumdiff.score import (Scope, score_all, score_change,
                               summarize_findings)


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

    def test_a_retired_flag_is_housekeeping_not_breakage(self):
        """The single most consequential row in the bucket table.

        90 flags are retired in a real M148 -> M151, split 45/45, and not one
        of them changes what a user sees. Filing them as breakage is how half a
        report becomes false alarms -- which is the failure this whole tool was
        built around avoiding.
        """
        old = snap("148.0.0.0", [feature("Shipped", "enabled")])
        new = snap("151.0.0.0", [])
        change = diff_snapshots(old, new, platform="windows")[0]
        self.assertEqual(score_change(change).bucket, "housekeeping")

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

        from chromiumdiff.extract import run_on_tree

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

        from chromiumdiff.extract import run_on_tree

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


class TestScoring(unittest.TestCase):
    """Severity is the ceiling; every point below it has a sentence."""

    def setUp(self):
        self.old = snap("139.0.0.0", [feature("Foo", "disabled")])
        self.new = snap("143.0.0.0", [feature("Foo", "enabled")])
        self.change = diff_snapshots(self.old, self.new)[0]

    def test_the_signal_decides_the_severity_not_the_kind(self):
        """The precise statement wins over the coarse prior.

        Both of these are `(mojo_method, modified)`, whose prior is 75. One is
        an ABI break and the other is a build condition on the mojom, and the
        old rule -- max(prior, signal) -- gave them the same number. Four real
        rows arrived that way at M143 -> M151.
        """
        def method(sig, attrs):
            return Fact(kind="mojo_method", key="blink.mojom.Foo.Bar",
                        name="Bar", path="a.mojom",
                        attrs={"interface": "blink.mojom.Foo",
                               "signature": sig, "attrs": attrs})
        abi = diff_snapshots(snap("148.0.0.0", [method("Bar(int32 a)", "")]),
                             snap("151.0.0.0", [method("Bar(string a)", "")]))[0]
        gate = diff_snapshots(snap("148.0.0.0", [method("Bar(int32 a)", "")]),
                              snap("151.0.0.0",
                                   [method("Bar(int32 a)", "EnableIfNot=is_win")]))[0]
        self.assertEqual(abi.severity, 80)
        self.assertEqual(gate.severity, 35)

    def test_an_android_only_mojo_change_scores_zero(self):
        """The extractor's platform_state has to be the one the scorer reads.

        This is the join the two modules can drift on: mojom resolves
        `[EnableIf=is_android]` and `score._not_in_build` reads
        `platform_state`, and if either spelling moves the deduction goes back
        to skipping every Mojo finding in silence -- which is how an
        Android-only field changing type reached the top of a Windows report at
        80 points. Measured on wide M148 -> M151: seven findings.
        """
        facts = mojom.extract("""
module blink.mojom;

[EnableIf=is_android]
struct Handset {
  int32 imei;
};
""", "handset.mojom")
        gone = [f for f in facts if f.kind == "mojo_field"]
        self.assertEqual(len(gone), 1)
        change = diff_snapshots(snap("148.0.0.0", gone),
                                snap("151.0.0.0", []))[0]
        finding = score_change(change)
        self.assertEqual(finding.score, 0)
        self.assertEqual(finding.bucket, BUCKET_HOUSEKEEPING)
        self.assertIn("not compiled into the windows build",
                      " ".join(finding.reasons))

    def test_a_change_with_no_signal_falls_back_to_the_kind(self):
        old = snap("148.0.0.0", [])
        new = snap("151.0.0.0", [Fact(kind="switch", key="brand-new",
                                      name="brand-new", path="switches.cc",
                                      attrs={"var": "kBrandNew"})])
        change = diff_snapshots(old, new, platform="windows")[0]
        self.assertEqual(change.signals, [])
        self.assertEqual(change.severity, 10)

    def test_score_never_rises_above_severity(self):
        findings = score_all(diff_snapshots(
            snap("148.0.0.0", [feature("A", "disabled"), feature("B", "enabled")]),
            snap("151.0.0.0", [feature("A", "enabled")]), platform="windows"))
        for f in findings:
            self.assertLessEqual(f.score, f.change.severity)

    def test_every_adjustment_carries_its_sentence(self):
        finding = score_change(self.change)
        self.assertTrue(finding.reasons)
        self.assertTrue(all(r.strip() for r in finding.reasons))
        self.assertIn(str(finding.change.severity), finding.reasons[0])

    def test_a_declaration_outside_our_build_scores_nothing(self):
        """It cannot move anything here, so it does not compete for attention."""
        never = feature("Bar", "enabled")
        never.attrs["platform_state"] = {"windows": "not_compiled"}
        before = feature("Bar", "disabled")
        before.attrs["platform_state"] = {"windows": "not_compiled"}
        change = diff_snapshots(snap("148.0.0.0", [before]),
                                snap("151.0.0.0", [never]),
                                platform="windows")[0]
        finding = score_change(change)
        self.assertEqual(finding.score, 0)
        self.assertEqual(finding.bucket, "housekeeping")

    def test_leaving_our_build_keeps_its_full_weight(self):
        """The case the old rule scored *down*.

        `_platform_applicable` read `after or before`, so a feature whose
        Windows guard closed -- the case where we lose the feature -- was
        penalised 45 points for not being in the Windows build.
        """
        gone = feature("Bar", "enabled")
        gone.attrs["platform_state"] = {"windows": "not_compiled"}
        change = diff_snapshots(snap("148.0.0.0", [feature("Bar", "enabled")]),
                                snap("151.0.0.0", [gone]),
                                platform="windows")[0]
        finding = score_change(change)
        self.assertEqual(finding.score, finding.change.severity)
        self.assertGreater(finding.score, 0)

    def test_a_removal_is_discounted_when_the_tree_was_not_read(self):
        """Absence from a twentieth of the tree is not evidence of deletion.

        Measured M148 -> M151 on the default set: of 141 preference keys that
        vanished, 100 had simply moved into a file the run never opened.
        """
        change = diff_snapshots(snap("148.0.0.0", [feature("Gone", "enabled")]),
                                snap("151.0.0.0", []), platform="windows")[0]
        partial = Scope({"to": {"candidates": 1164, "read": 64}}, to_ref="151")
        whole = Scope({"to": {"candidates": 1164, "read": 1164}}, to_ref="151")
        self.assertLess(score_change(change, partial).score,
                        score_change(change, whole).score)
        self.assertEqual(score_change(change, whole).score, change.severity)

    def test_an_addition_is_not_discounted(self):
        """An addition is a thing seen, not a thing not seen."""
        change = diff_snapshots(snap("148.0.0.0", []),
                                snap("151.0.0.0", [feature("New", "enabled")]),
                                platform="windows")[0]
        partial = Scope({"to": {"candidates": 1164, "read": 64}}, to_ref="151")
        self.assertEqual(score_change(change, partial).score, change.severity)

    def test_an_unconfirmed_disappearance_is_filed_as_housekeeping(self):
        """`pref_left_scan` says "deleted, or moved"; coverage says which."""
        key = Fact(kind="pref", key="a.b", name="a.b", path="pref_names.h",
                   attrs={"var": "kAB"})
        change = diff_snapshots(snap("148.0.0.0", [key]), snap("151.0.0.0", []),
                                platform="windows")[0]
        self.assertIn("pref_left_scan", change.signals)
        partial = Scope({"to": {"candidates": 1164, "read": 64}}, to_ref="151")
        whole = Scope({"to": {"candidates": 1164, "read": 1164}}, to_ref="151")
        self.assertEqual(score_change(change, partial).bucket, "housekeeping")
        self.assertEqual(score_change(change, whole).bucket, "breaking")

    def test_new_capability_is_new_surface_not_breakage(self):
        old = snap("139.0.0.0", [])
        new = snap("143.0.0.0", [blink("NewApi", "test")])
        findings = score_all(diff_snapshots(old, new))
        self.assertEqual(findings[0].bucket, "new")


class TestOwnership(unittest.TestCase):
    """Every finding lands on exactly one desk, and the tables say which.

    The third axis, and the one that decides whether a reader keeps reading.
    It is derived in `Report.by_owner` and nowhere else on purpose: the failure
    this project keeps having is one fact derived twice, and an owner computed
    once in the markdown renderer and once in the HTML one would drift the same
    way the reason strings did.
    """

    def test_every_kind_has_an_owner(self):
        """A kind added without one would silently be filed as Browser C++."""
        from chromiumdiff.model import ALL_KINDS, KIND_OWNERS
        self.assertEqual(sorted(KIND_OWNERS), sorted(ALL_KINDS))

    def test_every_owner_named_is_a_real_owner(self):
        from chromiumdiff.diff import SIGNAL_OWNERS
        from chromiumdiff.model import KIND_OWNERS, OWNER_ORDER
        for source in (KIND_OWNERS, SIGNAL_OWNERS):
            for key, owner in source.items():
                self.assertIn(owner, OWNER_ORDER, key)

    def test_every_owner_is_reachable_and_says_what_it_means(self):
        """Reachable from one table or the other, not necessarily both.

        `config` has no surface of its own -- nothing is *declared* outside the
        repository -- so it is reached only by signal. An owner reachable from
        neither would be a name in the report legend that no row can carry.
        """
        from chromiumdiff.diff import SIGNAL_OWNERS
        from chromiumdiff.model import (KIND_OWNERS, OWNER_LABELS,
                                       OWNER_MEANINGS, OWNER_ORDER)
        reachable = set(KIND_OWNERS.values()) | set(SIGNAL_OWNERS.values())
        self.assertEqual(sorted(reachable), sorted(OWNER_ORDER))
        for owner in OWNER_ORDER:
            self.assertTrue(OWNER_LABELS.get(owner), owner)
            self.assertTrue(OWNER_MEANINGS.get(owner), owner)

    def test_a_signal_overrides_the_surface_it_was_declared_on(self):
        """A renamed Finch string is a config job, not a C++ one.

        Both of these are `base_feature`, whose surface owner is Browser C++.
        One stops the build and is fixed in the file beside it; the other
        compiles and is fixed in a server-side config nobody can see from here.
        """
        from chromiumdiff.diff import owner_of
        from chromiumdiff.model import OWNER_CONFIG, OWNER_NATIVE
        renamed = diff_snapshots(
            snap("148.0.0.0", [feature("OldName", "enabled", var="kThing")]),
            snap("151.0.0.0", [feature("NewName", "enabled", var="kThing")]))
        lead = [c for c in renamed
                if "feature_string_renamed" in c.signals]
        self.assertTrue(lead)
        self.assertEqual(owner_of(lead[0]), OWNER_CONFIG)

        flipped = diff_snapshots(
            snap("148.0.0.0", [feature("Thing", "disabled")]),
            snap("151.0.0.0", [feature("Thing", "enabled")]))[0]
        self.assertEqual(owner_of(flipped), OWNER_NATIVE)

    def test_both_renderers_and_the_summary_agree_on_who_owns_what(self):
        """Three consumers of one derivation, which is where drift starts.

        `report.md` prints a per-owner table, `report.html` filters on an
        `owner` field baked into its data, and `summary.by_owner` is what a
        script reads. All three go through `owner_of`; a fourth answer computed
        locally in any of them would be the reason two people disagree about
        whose row it is.
        """
        import re

        from chromiumdiff.report import html as html_report
        from chromiumdiff.report import markdown as md_report
        from chromiumdiff.model import OWNER_LABELS

        findings = score_all(diff_snapshots(
            snap("148.0.0.0", [feature("A", "disabled"), feature("B", "enabled")]),
            snap("151.0.0.0", [feature("A", "enabled"), feature("C", "enabled")])))
        report = Report(from_ref="a", to_ref="b", findings=findings,
                        summary=summarize_findings(findings))

        counted = report.summary["by_owner"]
        text = md_report.render(report)
        for owner, total in counted.items():
            if not total:
                continue
            row = re.search(rf"^\| {re.escape(OWNER_LABELS[owner])} \|.*\| (\d+) \|$",
                            text, re.M)
            self.assertIsNotNone(row, OWNER_LABELS[owner])
            self.assertEqual(int(row.group(1)), total, owner)

        rows = html_report.payload_of(html_report.render(report))
        from collections import Counter
        self.assertEqual(Counter(r["owner"] for r in rows),
                         Counter({k: v for k, v in counted.items() if v}))

    def test_the_owner_counts_partition_the_report(self):
        """Each tally adds up to the total, so the counts are the report."""
        from chromiumdiff.model import OWNER_ORDER
        findings = score_all(diff_snapshots(
            snap("148.0.0.0", [feature("A", "disabled"), feature("B", "enabled")]),
            snap("151.0.0.0", [feature("A", "enabled"), feature("C", "enabled")])))
        summary = summarize_findings(findings)
        self.assertEqual(sum(summary["by_owner"].values()), len(findings))
        self.assertEqual(sorted(summary["by_owner"]), sorted(OWNER_ORDER))


class TestWebApiGates(unittest.TestCase):
    """The three-stage rule, applied to the surface that carries 14,549 facts.

    An addition a page cannot reach is stage A and an addition it can is stage
    B; the report gave both the same 30 points and the same sentence. Resolving
    it needs the *status* of the gating flag, not just its presence: 133 of 220
    added members at M148 -> M151 are reachable on arrival and 87 are not, and
    several of the reachable ones do carry `[RuntimeEnabled]`.
    """

    def _idl(self, name, iface="Widget", runtime="", ext=None):
        return Fact(kind="idl_member", key=f"{iface}.{name}", name=name,
                    path="a.idl",
                    attrs={"interface": iface, "member_type": "operation",
                           "signature": f"void {name}()", "ext": ext or {},
                           "runtime_enabled": runtime, "from_partial": False})

    def _flag(self, name, status):
        return Fact(kind="blink_runtime_feature", key=name, name=name,
                    path="runtime_enabled_features.json5",
                    attrs={"platform_status": {"windows": status}})

    def test_an_addition_behind_a_closed_gate_is_not_the_same_as_a_live_one(self):
        old = snap("148.0.0.0", [self._flag("Later", "experimental"),
                                 self._flag("Shipped", "stable")])
        new = snap("151.0.0.0", [self._flag("Later", "experimental"),
                                 self._flag("Shipped", "stable"),
                                 self._idl("gated", runtime="Later"),
                                 self._idl("live", runtime="Shipped"),
                                 self._idl("plain")])
        by_key = {c.key: c for c in diff_snapshots(old, new)}
        self.assertIn("web_api_added_gated", by_key["Widget.gated"].signals)
        self.assertIn("web_api_added_live", by_key["Widget.live"].signals)
        self.assertIn("web_api_added_live", by_key["Widget.plain"].signals)

    def test_a_gate_on_the_interface_counts_too(self):
        """45 of the 87 gated additions are gated only there, and read as live."""
        iface = Fact(kind="idl_interface", key="Widget", name="Widget",
                     path="a.idl",
                     attrs={"ext": {"RuntimeEnabled": "Later"}, "members": []})
        old = snap("148.0.0.0", [self._flag("Later", "test"), iface])
        new = snap("151.0.0.0", [self._flag("Later", "test"), iface,
                                 self._idl("hidden")])
        change = [c for c in diff_snapshots(old, new)
                  if c.key == "Widget.hidden"][0]
        self.assertIn("web_api_added_gated", change.signals)

    def test_an_unreadable_gate_stays_undecided(self):
        """A `default` run reads a third of the flags; guessing is the bug."""
        new = snap("151.0.0.0", [self._idl("mystery", runtime="NotInThisRun")])
        change = diff_snapshots(snap("148.0.0.0", []), new)[0]
        self.assertIn("web_api_added", change.signals)
        self.assertNotIn("web_api_added_live", change.signals)
        self.assertNotIn("web_api_added_gated", change.signals)

    def test_removing_what_no_page_could_reach_is_housekeeping(self):
        """32 of 77 removals at M148 -> M151. They were all Breaking."""
        old = snap("148.0.0.0", [self._flag("Later", "experimental"),
                                 self._idl("gone", runtime="Later")])
        new = snap("151.0.0.0", [self._flag("Later", "experimental")])
        change = [c for c in diff_snapshots(old, new)
                  if c.key == "Widget.gone"][0]
        self.assertIn("web_api_removed_gated", change.signals)
        self.assertEqual(score_change(change).bucket, BUCKET_HOUSEKEEPING)


class TestEverySignalIsClassified(unittest.TestCase):
    """One signal, one severity, one label, one bucket.

    Four tables keyed on the same names, in two files, is exactly the shape of
    duplication that drifts here. A signal missing from the bucket table would
    silently fall through to the direction rule and be filed by "something was
    removed" rather than by what the removal was.
    """

    def _tables(self):
        from chromiumdiff.diff import (SIGNAL_BUCKET, SIGNAL_LABELS,
                                      SIGNAL_SEVERITY)
        return SIGNAL_SEVERITY, SIGNAL_LABELS, SIGNAL_BUCKET

    def test_the_three_tables_hold_the_same_signals(self):
        severity, labels, buckets = self._tables()
        self.assertEqual(set(severity), set(labels))
        self.assertEqual(set(severity), set(buckets))

    def test_every_bucket_named_is_a_real_bucket(self):
        from chromiumdiff.model import BUCKET_ORDER
        _, _, buckets = self._tables()
        for signal, bucket in buckets.items():
            self.assertIn(bucket, BUCKET_ORDER, signal)

    def test_every_bucket_is_reachable(self):
        from chromiumdiff.model import BUCKET_ORDER
        _, _, buckets = self._tables()
        self.assertEqual(sorted(set(buckets.values())), sorted(BUCKET_ORDER))

    def test_every_bucket_says_what_it_means(self):
        from chromiumdiff.model import BUCKET_LABELS, BUCKET_MEANINGS, BUCKET_ORDER
        for bucket in BUCKET_ORDER:
            self.assertTrue(BUCKET_LABELS.get(bucket))
            self.assertTrue(BUCKET_MEANINGS.get(bucket))

    def test_every_provenance_verdict_says_what_it_means(self):
        """The ladder and its glosses are two lists that have to stay one.

        `_STRENGTH` orders the verdicts and decides which of them count as a
        citation; `VERDICT_MEANINGS` is what a page, a report and the `why`
        command all print for them. A verdict added to the ladder and not to
        the glosses reaches a reader as a bare word with no meaning attached,
        and one removed from the ladder leaves a sentence nothing can produce.
        """
        from chromiumdiff.enrich.gerrit import _STRENGTH
        from chromiumdiff.model import VERDICT_MEANINGS
        self.assertEqual(sorted(_STRENGTH), sorted(VERDICT_MEANINGS))
        for verdict, meaning in VERDICT_MEANINGS.items():
            self.assertTrue(meaning.strip(), verdict)

    def test_the_page_carries_the_glosses_rather_than_its_own_copy(self):
        """The renderer reads the one definition, so a change reaches both.

        The sentences used to be written into the page's JavaScript, where
        nothing outside a browser could reach them and nothing kept them equal
        to anything else.
        """
        from chromiumdiff.model import VERDICT_MEANINGS
        from chromiumdiff.report import html as html_report
        self.assertIn("window.__EVID__=", html_report.render(
            Report(from_ref="a", to_ref="b", findings=[], summary={},
                   meta={"platform": "windows"})))
        self.assertNotIn(VERDICT_MEANINGS["exact"], html_report._JS)

    def test_a_change_of_every_kind_and_direction_gets_a_bucket(self):
        """Including the ones that carry no signal at all -- 903 of 2,800 on a
        real M148 -> M151 run, and every one of them has to be filed."""
        from chromiumdiff.diff import bucket_of
        from chromiumdiff.model import (ADDED, ALL_KINDS, BUCKET_ORDER, MODIFIED,
                                       REMOVED, Change)
        for kind in ALL_KINDS:
            for direction in (ADDED, REMOVED, MODIFIED):
                bare = Change(change_type=direction, kind=kind, key="k",
                              name="k")
                self.assertIn(bucket_of(bare), BUCKET_ORDER,
                              f"{kind}/{direction}")


class TestPartitions(unittest.TestCase):
    """Bounding the scan is a speed/completeness trade, and must be explicit.

    Measured M148 -> M151: the full run is about 120s and 126 MB; --partition
    downloads is 17s and 2.6 MB. The saving is real and so is the loss.
    """

    def test_partition_narrows_the_fetch_list(self):
        from chromiumdiff.targets import get_targets

        full = get_targets("default")
        part = get_targets("default", ["downloads"])
        self.assertLess(len(part), len(full))
        self.assertTrue(any("resources/downloads" in t.path for t in part))
        self.assertFalse(any("resources/bookmarks" in t.path for t in part))

    def test_core_targets_survive_every_partition(self):
        """Prefs and flag metadata are cheap and relevant to everything."""
        from chromiumdiff.targets import get_targets

        for name in ("downloads", "settings", "history"):
            paths = {t.path for t in get_targets("default", [name])}
            self.assertIn("chrome/common/pref_names.h", paths, name)
            self.assertIn("chrome/browser/flag-metadata.json", paths, name)

    def test_partitions_combine(self):
        from chromiumdiff.targets import get_targets

        both = {t.path for t in get_targets("default", ["downloads", "bookmarks"])}
        self.assertTrue(any("resources/downloads" in p for p in both))
        self.assertTrue(any("resources/bookmarks" in p for p in both))

    def test_unknown_partition_is_rejected(self):
        from chromiumdiff.targets import get_targets

        with self.assertRaises(KeyError):
            get_targets("default", ["not-a-partition"])

    def test_partition_is_part_of_the_cache_key(self):
        """Otherwise a partial snapshot gets reused as if it were a full one.

        This exact class of bug has bitten twice: a "minimal" snapshot holding
        the full fact set, and a widened filter that changed nothing.
        """
        from chromiumdiff.snapshot import snapshot_path

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
        from chromiumdiff.acquire import GitilesSource
        from chromiumdiff.targets import get_targets

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

    Three of them accepted the flag and dropped it. `catalog` was the worst:
    it reported coverage against the full target list while describing a run
    that only fetched one partition.
    """

    def _parse(self, argv):
        from chromiumdiff.cli import build_parser
        return build_parser().parse_args(argv)

    def test_every_command_taking_the_flag_forwards_it(self):
        import inspect
        from chromiumdiff import cli

        for name in ("cmd_snapshot", "cmd_compare", "cmd_run"):
            src = inspect.getsource(getattr(cli, name))
            self.assertIn("build_snapshot", src, name)
            self.assertEqual(
                src.count("build_snapshot("), src.count("partitions=args.partitions"),
                f"{name} builds a snapshot without forwarding --partition")

    def test_catalog_measures_the_partition_it_was_given(self):
        from chromiumdiff import catalog
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
        from chromiumdiff import catalog
        report = catalog.analyze(["media/base/media_switches.cc"],
                                 ref="151.0.0.0", partitions=["downloads"])
        text = "\n".join(catalog.summarize(report))
        self.assertIn("downloads", text)
        self.assertIn("covers less by design", text)


class TestHtmlReportScales(unittest.TestCase):
    """A full upgrade is thousands of findings, and the obvious rendering froze
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

    def _report(self, n=3000):
        from chromiumdiff.model import Change, Finding, Report
        findings = [
            Finding(change=Change(change_type="modified", kind="base_feature",
                                  key=f"Feature{i}", name=f"Feature{i}",
                                  signals=["flag_retired_on"],
                                  paths=[f"content/f{i}.cc"]),
                    score=100 - i % 100, bucket="housekeeping",
                    reasons=["base severity 75"])
            for i in range(n)]
        return Report(from_ref="a", to_ref="b", findings=findings)

    def _report_html(self, n=3000):
        from chromiumdiff.report import html as html_report
        return html_report.render(self._report(n))

    def test_every_finding_is_still_embedded(self):
        """Paging must not become a way to lose data.

        Filtering and paging are presentation. The payload stays complete, so a
        reader can always search the whole set and the JSON never disagrees
        with the page.
        """
        from chromiumdiff.report import html as html_report
        text = self._report_html(300)
        rows = html_report.payload_of(text)
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
        # 300 of the 3,000 fixture rows are `ipc`; the rest are `config`.
        self.assertIn("300", out["ownerFilterCount"])
        self.assertIn("3000", out["allOwnersRestores"])

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

        # 4. The floor under provenance, run rather than read. The fixture
        #    carries 30 rows of each shape, and "Has a CL" must return the
        #    120 that name their fact -- `exact`, `declares`, the `described`
        #    ones reached by commit message, and the ones cited over a lookup
        #    that lost requests -- and none of the 60 that only list reviews:
        #    the fallback exists so a click always answers, and it stops being
        #    worth having the moment it passes for an answer.
        # Plus 30 whose stored answer a run baked an issue history into, which
        # a served page hides in favour of the chip on the CL.
        self.assertIn("of 300", out["hasCl"])
        # 30 plain `exact`, 30 cited over a lookup that lost requests, and
        # 30 `introduced`. All three are a changed line tied to the
        # identifier; the last is the strongest verdict on the page, and
        # matching the word `exact` alone had left it out of the option for
        # strong evidence and filed it under "Has a CL" beside rows found by
        # a commit message.
        self.assertIn("of 240", out["exactOnly"])
        # 30 leads over diffs that were read, plus 30 over diffs the budget
        # declined. Both are leads; only the second can still be answered.
        self.assertIn("of 60", out["weakOnly"])
        self.assertTrue(out["weakRowClass"], "a lead row needs its own state")
        self.assertTrue(out["weakRowIsNotCl"])

        # A click on one of them returns CLs -- that is the guarantee -- under
        # a sentence saying what they are. The badge is not enough on its own;
        # it is one word at the end of a line a reader is skimming.
        self.assertTrue(out["weakDetailListsTheCl"],
                        "a lead row must still show the CLs it found")
        self.assertTrue(out["weakDetailSaysLead"])
        self.assertTrue(out["weakDetailBadge"])

        # A row the budget declined is a lead of a different kind: nothing was
        # read, so the verdicts that name a fact were never attempted. Filling
        # it with leads made it read as exhausted and took its way out with it
        # -- the remedy and the lookup button both lived in the branch that
        # runs only when there are no CLs at all, so the one row that could
        # still be answered became the one row that could no longer ask.
        self.assertTrue(out["budgetRowSaysNothingWasRead"],
                        "a budget-declined row must not read as exhausted")
        self.assertTrue(out["budgetRowNamesThePool"],
                        "three of 147 is the fact that makes the leads weak")
        self.assertTrue(out["budgetRowOffersTheRemedy"],
                        "the row that can still be answered must say how")

        # A qualifier is a property of the lookup, not of how the lookup
        # ended. Written into the empty panel's innermost branch it reached
        # the one shape a partial failure cannot make, and missed the three
        # it does.
        self.assertTrue(out["aCitedRowStillWarns"],
                        "a row that lost requests reads as a finished search")
        self.assertTrue(out["theWarningNamesTheCount"])
        self.assertTrue(out["theCitationSurvivesTheWarning"])

        # And the disclaimer is not printed over evidence that does name it.
        self.assertTrue(out["exactDetailListsTheCl"])
        self.assertFalse(out["exactDetailSaysLead"])

        # 5. A CL reached by its commit message was never in the file search,
        #    so it cannot borrow that search's denominator: "3 of 62 merged
        #    CLs touched this file" would be a count nobody measured.
        self.assertIn("of 30", out["messageRowCount"])
        self.assertTrue(out["messageDetailListsTheCl"])
        self.assertTrue(out["messageDetailSaysHow"])
        self.assertTrue(out["messageDetailHidesTheDenominator"],
                        "a message-found CL must not print the file's pool")

        # 4. A score of zero is a real result -- base severity 35 for a removed
        #    preference, minus 45 for one not compiled on Windows, clamped --
        #    and it has to survive the trip into the payload. It did not: the
        #    payload dropped empty values with `v not in ("", [], {}, None,
        #    False)`, and `0 == False` in Python, so 238 of 6,757 rows in a
        #    real M143 -> M151 report lost their score and rendered the word
        #    `undefined` in the Score column. The old fixture gave every row a
        #    truthy score, which is why nothing here noticed.
        self.assertFalse(out["undefinedInRows"],
                         "a cell rendered the string 'undefined'; a field the "
                         "payload may omit is being printed without a guard")
        self.assertFalse(out["undefinedAfterFilter"])
        # A run of rows sharing a cause repeated the cause on every line of
        # it: ten consecutive Mojo findings in a real report printed the same
        # sentence four times, the same directory five times and the same
        # surface five times, while the phrase that differed sat in the
        # narrowest column. Held back, the value is stated once per run and
        # kept on the cell it was omitted from.
        # Every row states its own values. Three treatments for a repeated
        # value were tried -- dropping it, merging the run into one tall
        # cell, and dimming it -- and each encoded the current sort order
        # into the appearance of a value that had not changed.
        self.assertTrue(out["everyRowStatesItsCause"])
        self.assertTrue(out["everyRowStatesItsPath"])
        self.assertTrue(out["noCellIsMarkedAsARepeat"],
                        "two identical values may not be drawn differently")

        self.assertTrue(out["zeroRendersAsZero"],
                        "a zero score must render as 0, not as blank")

    def test_a_zero_score_survives_into_the_payload(self):
        """The other half of the same bug, at the layer that caused it.

        The harness above proves the page renders a zero; this proves one
        reaches it. `_to_rows` dropped empty values with
        `v not in ("", [], {}, None, False)`, and `0 == False`, so the score
        key vanished for every finding scoring zero -- 238 of 6,757 rows in a
        real M143 -> M151 run. `ours: False` still has to be dropped, which is
        what makes the two cases easy to conflate.
        """
        from chromiumdiff.report.html import _to_rows

        report = self._report()
        report.findings[0].score = 0
        report.findings[0].matched_paths = []
        report.findings[0].matched_symbols = []
        rows = _to_rows(report, "windows")
        self.assertEqual(rows[0].get("score"), 0,
                         "a finding scoring zero lost its score")
        self.assertNotIn("ours", rows[0],
                         "False still has to be dropped")


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
        from chromiumdiff.catalog import summarize_closure, unresolved_references
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
        from chromiumdiff.catalog import unresolved_references
        snap_ = self._snap([
            Fact("webui_gate", "enableThing", "enableThing", "h.cc",
                 attrs={"features": ["kThingDeclaredInContent"]}),
        ])
        self.assertEqual(unresolved_references(snap_),
                         {"feature": ["ThingDeclaredInContent"]})

    def test_a_pref_bound_but_never_declared_is_named(self):
        from chromiumdiff.catalog import unresolved_references
        snap_ = self._snap([
            Fact("webui_control", "settings/x/pref:download.prompt", "pref:download.prompt",
                 "x.html", attrs={"pref": "download.prompt"}),
        ])
        self.assertEqual(unresolved_references(snap_), {"pref": ["download.prompt"]})

    def test_the_summary_names_what_to_add(self):
        from chromiumdiff.catalog import summarize_closure, unresolved_references
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
        from chromiumdiff.targets import get_targets
        filtered = get_targets("default", ["downloads"])
        complete = get_targets("default", ["downloads"], complete=True)
        self.assertTrue(any(t.kind == "tree" and t.path == "components/download"
                            for t in complete),
                        "complete should pull the whole components/download root")
        self.assertFalse(any(t.kind == "tree" and t.path == "components/download"
                             for t in filtered))

    def test_complete_covers_what_the_curated_list_missed(self):
        """Measured gaps at M151, now inside the roots by construction."""
        from chromiumdiff.targets import get_targets
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
        from chromiumdiff.targets import READABLE_SUFFIXES, get_targets

        wide = {t.include for t in get_targets("wide")
                if t.kind == "tree" and t.include}
        self.assertIn(READABLE_SUFFIXES, wide)
        for target in get_targets("default", ["extensions"], complete=True):
            if target.kind != "tree":
                continue
            missing = set(READABLE_SUFFIXES) - set(target.include or ())
            self.assertFalse(missing, f"{target.path} filters out {missing}")

    def test_the_gate_root_is_the_extractors_own(self):
        """One directory, three places that used to spell it out.

        `webui_gates.applies_to` claims every .cc under its handler directory --
        a rule, not a naming convention -- so the fetch side has to name the
        same directory in two places: the default set's tree target and the
        `--complete` filter. All three were string literals. Chromium moves its
        WebUI directories, and two of the three would have moved with it while
        the third went quiet: the fetch would keep working and the extractor
        would stop matching, or the reverse.
        """
        from chromiumdiff.extract.webui_gates import WEBUI_HANDLER_DIR, applies_to
        from chromiumdiff.targets import GATE_ROOT, get_targets, reaches, scope_of

        self.assertEqual(GATE_ROOT, WEBUI_HANDLER_DIR.rstrip("/"))
        probe = WEBUI_HANDLER_DIR + "settings/settings_ui.cc"
        self.assertTrue(applies_to(probe))
        for args in (("default", None, False), ("wide", None, False),
                     ("default", ["settings"], False),
                     ("default", ["settings"], True)):
            files, trees = scope_of(get_targets(*args))
            self.assertTrue(reaches(probe, files, trees),
                            f"{args} does not fetch what the gate extractor reads")

    def test_complete_fetches_the_pref_files_the_extractor_reads(self):
        """The concrete files the second list was dropping, at M151."""
        from chromiumdiff.targets import get_targets, reaches, scope_of
        files, trees = scope_of(get_targets("default", ["extensions"],
                                            complete=True))
        for path in ("extensions/browser/extension_prefs.h",
                     "extensions/browser/extension_prefs.cc",
                     "extensions/common/features/feature_flags.h"):
            self.assertTrue(reaches(path, files, trees), path)

    def test_an_unaffordable_root_is_refused_not_faked(self):
        from chromiumdiff.targets import get_targets
        with self.assertRaises(ValueError) as caught:
            get_targets("default", ["webplatform"], complete=True)
        self.assertIn("webplatform", str(caught.exception))

    def test_complete_needs_a_partition(self):
        from chromiumdiff.targets import get_targets
        with self.assertRaises(ValueError):
            get_targets("default", None, complete=True)

    def test_complete_is_part_of_the_cache_key(self):
        from chromiumdiff.snapshot import snapshot_path
        a = snapshot_path("/c", "refs/tags/151", "default", ["settings"])
        b = snapshot_path("/c", "refs/tags/151", "default", ["settings"], True)
        self.assertNotEqual(a, b)

    def test_diff_refuses_to_mix_complete_with_filtered(self):
        from chromiumdiff.diff import diff_snapshots
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
        "third_party/blink/renderer/core/dom/element.idl",  # web API definitions
        "third_party/blink/public/mojom/frame/frame.mojom",  # process boundary
    ]

    def _report(self, **kw):
        from chromiumdiff.catalog import analyze
        return analyze(self.PATHS, ref="151.0.0.0", **kw)

    def test_every_surface_an_extractor_reads_is_a_candidate(self):
        """The denominator asks the extractors; there is no second list.

        `.idl` and `.mojom` used to be excluded from it, so `wide` reported
        100% while 3,798 such files -- 72% of a report's facts -- sat outside
        the measurement. A file no extractor reads is still not a candidate.
        """
        paths = {c.path for c in self._report().candidates}
        self.assertIn("cc/base/features.cc", paths)
        self.assertIn("third_party/blink/renderer/core/dom/element.idl", paths)
        self.assertIn("third_party/blink/public/mojom/frame/frame.mojom", paths)
        self.assertNotIn("chrome/browser/browser.cc", paths)

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


class TestTheMarkdownCarriesTheGroup(unittest.TestCase):
    """`report.md` is the copy that travels.

    A reader pastes one section of it into a ticket and that section is the
    whole of what the next person sees. The table of groups at the top says
    which findings belong together, and nobody pastes the table.
    """

    def _finding(self, key, score, group=None):
        from chromiumdiff.model import Change, Finding
        return Finding(
            change=Change(change_type="modified", kind="mojo_method", key=key,
                          name=key.split(".")[-1], signals=["ipc_signature_change"]),
            score=score, bucket="breaking", reasons=["severity 80"],
            enrichment={"cluster": group} if group else {})

    def _detail(self, finding):
        from chromiumdiff.report.markdown import _render_details
        return _render_details([finding], "windows")

    def test_a_fragment_says_so_and_points_at_the_heaviest(self):
        text = self._detail(self._finding(
            "blink.mojom.SubAppsService.Add", 15,
            {"id": "x", "label": "[sub apps] change web api", "size": 7,
             "kinds": [], "top_score": 80}))
        self.assertIn("Part of a larger change", text)
        self.assertIn("[sub apps] change web api", text)
        self.assertIn("6 elsewhere in this report", text)
        self.assertIn("The heaviest scores 80", text)

    def test_the_heaviest_is_not_named_on_the_heaviest(self):
        """Telling the top row of a group to go read the top row of its group
        is noise."""
        text = self._detail(self._finding(
            "blink.mojom.SubAppsService.Add", 80,
            {"id": "x", "label": "l", "size": 2, "kinds": [], "top_score": 80}))
        self.assertIn("Part of a larger change", text)
        self.assertNotIn("read that one first", text)

    def test_a_lone_finding_says_nothing(self):
        self.assertNotIn("Part of a larger change",
                         self._detail(self._finding("blink.mojom.I.m", 80)))


class TestAFragmentSaysItIsOne(unittest.TestCase):
    """The run works out which findings are fragments of one change, and
    `report.md` prints the groups. The table did not carry it at all.

    Read alone, a parameter of an enabled feature is a 15-point row in "New
    surface", whose whole meaning is that nothing switches it on -- while the
    feature it belongs to sits at 55 in the same report with the flag already
    flipped. Measured on a real M148 -> M151 run, 20 rows are in exactly that
    position, and every one of them was already clustered with its parent.
    """

    def test_the_payload_carries_the_group(self):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report.html import _to_rows

        finding = Finding(
            change=Change(change_type="added", kind="feature_param",
                          key="CastStreamingMaxVideoBitrate/max_bitrate_mbps",
                          name="max_bitrate_mbps"),
            score=15, bucket="new",
            enrichment={"cluster": {"id": "x", "label": "CastStreamingMaxVideoBitrate",
                                    "size": 2, "kinds": [], "top_score": 55,
                                    "members": ["base_feature:CastStreamingMaxVideoBitrate",
                                                "feature_param:CastStreamingMaxVideoBitrate/max_bitrate_mbps"]}})
        row = _to_rows(Report(from_ref="a", to_ref="b", summary={}, meta={},
                              findings=[finding]), "windows")[0]
        self.assertEqual(row["grp"]["n"], "CastStreamingMaxVideoBitrate")
        self.assertEqual(row["grp"]["c"], 2)
        self.assertEqual(row["grp"]["t"], 55)
        # Who else is in it, so a lookup can say which other rows it changed.
        self.assertIn("base_feature:CastStreamingMaxVideoBitrate",
                      row["grp"]["m"])

    def test_a_lone_finding_is_not_a_group(self):
        """A cluster of one is the finding itself, and saying so is noise."""
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report.html import _to_rows

        finding = Finding(
            change=Change(change_type="added", kind="feature_param",
                          key="A/b", name="b"),
            score=15, bucket="new",
            enrichment={"cluster": {"id": "x", "label": "A", "size": 1,
                                    "kinds": [], "top_score": 15}})
        row = _to_rows(Report(from_ref="a", to_ref="b", summary={}, meta={},
                              findings=[finding]), "windows")[0]
        self.assertNotIn("grp", row)


class TestClustering(unittest.TestCase):
    """One Chromium change arrives as fragments; they must read as one story."""

    def _finding(self, kind, key, attrs, score=50):
        from chromiumdiff.model import Change, Finding
        return Finding(
            change=Change(change_type="modified", kind=kind, key=key,
                          name=key.split("/")[-1], before=dict(attrs),
                          after=dict(attrs)),
            score=score, bucket="behaviour")

    def _cited(self, kind, key, cls, score=70):
        """A finding carrying the CLs a lookup tied to it."""
        from chromiumdiff.model import Change, Finding
        return Finding(
            change=Change(change_type="modified", kind=kind, key=key,
                          name=key.split(".")[-1]),
            score=score, bucket="breaking",
            enrichment={"gerrit": {"changes": cls}})

    def test_one_cl_across_several_declarations_is_one_story(self):
        """Every other rule joins on a link Chromium declares in the source,
        and between a `.mojom` and an `.idl` no such link is ever written.

        Measured on a real M148 -> M151 run: those rules reach 6 of the 150
        highest-scoring findings, because 143 of the groups they do build are
        a feature and its parameters, which is the bottom of the ranking. A
        shared CL is the same evidence recorded elsewhere -- one author, one
        change, landing across several declarations -- and it reaches 84.
        """
        from chromiumdiff.cluster import build_clusters

        cl = [{"number": 7957918, "match": "exact",
               "subject": "[sub apps] change web api"}]
        rows = [self._cited("mojo_method", "blink.mojom.SubAppsService.Add", cl),
                self._cited("idl_interface", "SubAppsAddParams", cl),
                self._cited("idl_member", "SubAppsAddParams.installURL", cl)]
        clusters = build_clusters(rows)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(next(iter(clusters.values()))), 3)

    def test_a_group_is_named_by_the_cl_that_made_it(self):
        """`Add` is the leaf of `blink.mojom.SubAppsService.Add` and tells a
        reader nothing about the group. The author already wrote a name for
        the change; the subject is it."""
        from chromiumdiff.cluster import build_clusters, cluster_label

        cl = [{"number": 7957918, "match": "exact",
               "subject": "[sub apps] change web api"}]
        rows = [self._cited("mojo_method", "blink.mojom.SubAppsService.Add", cl,
                            score=80),
                self._cited("idl_interface", "SubAppsAddParams", cl, score=70)]
        members = next(iter(build_clusters(rows).values()))
        self.assertEqual(cluster_label(members), "[sub apps] change web api")

    def test_a_cl_on_one_member_does_not_name_the_group(self):
        """It names that member's change. Only a CL every member carries is
        speaking about the group."""
        from chromiumdiff.cluster import cluster_label
        from chromiumdiff.model import Change, Finding

        shared = {"number": 1, "match": "exact", "subject": "the shared one"}
        lone = {"number": 2, "match": "exact", "subject": "only on this row"}
        a = self._cited("mojo_method", "I.a", [shared, lone], score=80)
        b = self._cited("mojo_method", "I.b", [shared], score=70)
        self.assertEqual(cluster_label([a, b]), "the shared one")
        # and with nothing shared, the highest-scoring member's own name
        c = self._cited("mojo_method", "I.c", [lone], score=90)
        self.assertEqual(cluster_label([b, c]), "c")

    def test_a_cluster_names_its_members(self):
        """A lookup joins two rows and only one is the row asked about. Without
        the members on the cluster, the answer cannot say which other rows it
        just changed, and a panel already open on one of them goes on showing
        an answer that stopped being true."""
        from chromiumdiff.cluster import annotate

        cl = [{"number": 1, "match": "exact", "subject": "s"}]
        rows = [self._cited("mojo_method", "I.a", cl),
                self._cited("mojo_method", "I.b", cl)]
        annotate(rows)
        members = rows[0].enrichment["cluster"]["members"]
        self.assertEqual(sorted(members),
                         ["mojo_method:I.a", "mojo_method:I.b"])

    def test_a_lead_is_not_a_link(self):
        """`crowded` and `touched` name the declaring file, not the fact. Two
        rows sharing one share a busy file, which is not a story -- and
        `about_flags.cc` alone would put five hundred findings in one group."""
        from chromiumdiff.cluster import build_clusters

        cl = [{"number": 8007779, "match": "touched", "subject": "unrelated"}]
        rows = [self._cited("flag_entry", "flag-a", cl),
                self._cited("flag_entry", "flag-b", cl)]
        self.assertEqual(build_clusters(rows), {})

    def test_a_group_past_the_guard_rail_is_skipped_not_split(self):
        """The cap is a guard-rail, so the behaviour at it has to be the one
        the comment claims: a group past it is dropped whole. A split group
        would read as two changes where there was one."""
        from chromiumdiff.cluster import CL_GROUP_MAX, build_clusters

        cl = [{"number": 1, "match": "exact", "subject": "s"}]
        rows = [self._cited("idl_member", f"I.m{i}", cl)
                for i in range(CL_GROUP_MAX + 1)]
        self.assertEqual(build_clusters(rows), {})
        rows = rows[:CL_GROUP_MAX]
        self.assertEqual(len(next(iter(build_clusters(rows).values()))),
                         CL_GROUP_MAX)

    def test_route_gate_feature_form_one_cluster(self):
        from chromiumdiff.cluster import build_clusters

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
        from chromiumdiff.cluster import build_clusters
        from chromiumdiff.model import Change, Finding

        moved = Finding(
            change=Change(change_type="modified", kind="webui_route",
                          key="settings/PAGE", name="PAGE",
                          before={"guards": ["oldGate"]},
                          after={"guards": ["newGate"]},
                          deltas={"guards": [["oldGate"], ["newGate"]]}),
            score=60, bucket="behaviour")
        old_gate = self._finding("webui_gate", "oldGate", {"features": []}, 40)
        new_gate = self._finding("webui_gate", "newGate", {"features": []}, 40)

        clusters = build_clusters([moved, old_gate, new_gate])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(next(iter(clusters.values()))), 3)

    def test_control_joins_the_route_it_labels(self):
        """SITE_SETTINGS_LNA and siteSettingsLna are one identifier."""
        from chromiumdiff.cluster import build_clusters

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
        from chromiumdiff.cluster import build_clusters

        blink = self._finding("blink_runtime_feature", "LnaSplitPermissions",
                              {"base_feature": "none"}, 20)
        flag = self._finding("base_feature", "LnaChecksSplitPermissions", {}, 50)
        self.assertEqual(build_clusters([blink, flag]), {})

    def test_blink_flag_joins_via_its_declared_feature(self):
        from chromiumdiff.cluster import build_clusters

        blink = self._finding("blink_runtime_feature", "SomeApi",
                              {"base_feature": "kBackingFeature"}, 20)
        flag = self._finding("base_feature", "BackingFeature", {}, 50)
        self.assertEqual(len(build_clusters([blink, flag])), 1)

    def test_unrelated_findings_are_not_clustered(self):
        from chromiumdiff.cluster import build_clusters

        a = self._finding("base_feature", "Alpha", {})
        b = self._finding("base_feature", "Beta", {})
        self.assertEqual(build_clusters([a, b]), {})


class TestWindowsConsoleEncoding(unittest.TestCase):
    """Reports must survive a non-UTF-8 stdout.

    On Windows, redirected output falls back to the ANSI code page (cp1252 for
    most installs), and every report contains arrows and em-dashes. Before the
    fix this failed with "'charmap' codec can't encode character '\\u2192'".
    """

    def test_report_renders_to_a_cp1252_stdout(self):
        import subprocess
        import tempfile

        from chromiumdiff.model import Change, Finding, Report, write_json

        change = Change(change_type="modified", kind="base_feature",
                        key="Foo", name="Foo",
                        deltas={"default_state": ["disabled", "enabled"]},
                        signals=["enabled_by_default"], severity=75)
        report = Report(from_ref="139.0.0.0", to_ref="143.0.0.0",
                        findings=[Finding(change=change, score=75,
                                          bucket="behaviour")],
                        meta={"platform": "windows"})

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            write_json(path, report.to_dict())

            env = dict(os.environ, PYTHONIOENCODING="cp1252")
            result = subprocess.run(
                [sys.executable, "-m", "chromiumdiff", "report", path,
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
        from chromiumdiff.model import Change, Finding, Report
        change = Change(change_type="modified", kind="base_feature",
                        key="Foo", name="Foo",
                        deltas={"default_state": ["disabled", "enabled"]},
                        signals=["enabled_by_default"], severity=75)
        return Report(from_ref="148.0.0.0", to_ref="151.0.0.0",
                      findings=[Finding(change=change, score=75,
                                        bucket="behaviour",
                                        reasons=["base severity 75"])],
                      summary=summary)

    def test_the_serialized_finding_has_no_verdict_field(self):
        payload = self._report().to_dict()
        self.assertNotIn("ai", payload["summary"])
        self.assertNotIn("ai", payload["findings"][0])

    def test_a_legacy_report_with_a_verdict_still_loads(self):
        """Reports written before the stage was removed must not crash."""
        from chromiumdiff.model import Report

        payload = self._report().to_dict()
        payload["summary"]["ai"] = {"headline": "old"}
        payload["findings"][0]["ai"] = {"verdict": "breaks_us"}
        loaded = Report.from_dict(payload)
        self.assertEqual(len(loaded.findings), 1)
        self.assertFalse(hasattr(loaded.findings[0], "ai"))

    def test_neither_renderer_offers_a_verdict_column(self):
        from chromiumdiff.report import html as html_report
        from chromiumdiff.report import markdown as md_report

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

        from chromiumdiff.report import html as html_report

        text = html_report.render(self._report())
        # Scoped to the findings table: the overview carries a table of its own
        # and its <thead> comes first in the document.
        find = text[text.index('<table class="find">'):]
        head = find[find.index("<colgroup>"):find.index("</colgroup>")]
        cols = len(re.findall(r"<col[ />]", head))
        ths = len(re.findall(r"<th ", find[find.index("<thead>"):find.index("</thead>")]))
        spans = {int(n) for n in re.findall(r'colspan="(\d+)"', find)}
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

        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        change = Change(change_type="modified", kind="feature_param",
                        key="helpUrl", name="helpUrl",
                        after={"feature": "kGlic", "default": "https://x.test/a"})
        change.deltas = {"default": ["https://x.test/a", "https://x.test/b"]}
        text = html_report.render(
            Report(from_ref="a", to_ref="b",
                   findings=[Finding(change=change, score=40, bucket="housekeeping")]))
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
        that says what Chromium *meant* to ship is fetched and thrown away.
        """
        from chromiumdiff.report import markdown as md_report

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
        from chromiumdiff.report import markdown as md_report
        self.assertNotIn("What Chromium says shipped",
                         md_report.render(self._report()))

    def test_the_brief_reaches_the_html_report_too(self):
        """Both tests above render the *markdown* report, and the HTML one was
        never asserted -- so when `_brief_html` lost its return statement the
        page printed the bare word `None` where the section belongs, and
        nothing failed. The feature is only shipped in the file people open.
        """
        from chromiumdiff.report import html as html_report

        page = html_report.render(self._report(milestone_brief=[
            {"milestone": 149, "name": "CSS anchor positioning",
             "summary": "Positions an element relative to another."},
        ]), "windows")
        self.assertIn("CSS anchor positioning", page)
        self.assertIn("Positions an element relative to another.", page)
        self.assertIn('<details class="brief">', page)
        # The specific way it failed: a function that builds and never returns.
        self.assertNotIn(">None<", page)
        self.assertNotIn("\nNone\n", page)

    def test_a_report_without_a_brief_renders_no_html_section(self):
        from chromiumdiff.report import html as html_report
        self.assertNotIn('class="brief"',
                         html_report.render(self._report(), "windows"))


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
        from chromiumdiff.extract import run_on_tree

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
        from chromiumdiff.extract import run_on_tree

        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp)
            facts, _ = run_on_tree(tmp, allow_prefixes={"chrome/browser/ui/webui/"})
            self.assertIn("mojo_interface", {f.kind for f in facts})

    def test_the_snapshot_scope_carries_the_filter(self):
        """snapshot.py must pass the filter through, not just the path."""
        from chromiumdiff.targets import get_targets

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
        from chromiumdiff.model import Fact, Snapshot
        return Snapshot(
            ref="test", meta={"target_set": "default", "partitions": [],
                              "complete": False},
            facts=[Fact(kind="x", key=p, name="x", path=p) for p in paths])

    def test_a_file_outside_the_tree_filter_is_flagged(self):
        from chromiumdiff.catalog import scope_violations

        # The default target asks for chrome/browser/ui/webui as *.cc only.
        snap = self._snap(["chrome/browser/ui/webui/downloads/downloads.cc",
                           "chrome/browser/ui/webui/downloads/downloads.mojom"])
        self.assertEqual(scope_violations(snap),
                         ["chrome/browser/ui/webui/downloads/downloads.mojom"])

    def test_a_file_under_no_target_at_all_is_flagged(self):
        from chromiumdiff.catalog import scope_violations
        snap = self._snap(["chrome/browser/ui/views/toolbar/toolbar_view.cc"])
        self.assertEqual(len(scope_violations(snap)), 1)

    def test_a_clean_snapshot_is_silent(self):
        from chromiumdiff.catalog import scope_violations
        snap = self._snap(["chrome/browser/ui/webui/downloads/downloads.cc",
                           "chrome/common/pref_names.h",
                           "third_party/blink/public/mojom/frame/frame.mojom"])
        self.assertEqual(scope_violations(snap), [])

    def test_a_polymer_to_lit_migration_is_not_a_violation(self):
        """Both dialects are inside the WebUI filter, so neither is out of scope."""
        from chromiumdiff.catalog import scope_violations
        snap = self._snap(["chrome/browser/resources/history/app.html",
                           "chrome/browser/resources/history/app.html.ts"])
        self.assertEqual(scope_violations(snap), [])

    def test_the_real_snapshots_in_the_cache_are_clean(self):
        """Runs against whatever real snapshots this machine has built."""
        import glob
        import os

        from chromiumdiff.catalog import scope_violations
        from chromiumdiff.model import Snapshot, read_json

        from chromiumdiff.model import SCHEMA_VERSION

        found = sorted(glob.glob(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".chromiumdiff-cache", "snapshots", "*.json")))
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
        from chromiumdiff.targets import discover_candidates
        return set(discover_candidates(self._Tree(paths))[0])

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
        from chromiumdiff.acquire import FetchTarget
        from chromiumdiff.targets import coverage_against

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
        from chromiumdiff.acquire import FetchTarget
        from chromiumdiff.targets import coverage_against

        cov = coverage_against({"chrome/browser/x/x_prefs.h": "p"},
                               [FetchTarget("chrome/browser", "tree", (".cc",))])
        self.assertEqual(cov["missed"], 1)

    def test_the_wide_target_set_closes_most_of_the_gap(self):
        """`--target-set wide` exists to be the answer when the gap matters."""
        from chromiumdiff.targets import coverage_against, get_targets

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
    identifier while holding the string emitted nothing -- yet any code
    writes `features::kFoo`, never the string, so the rename breaks our build.
    kDIPS -> kBtm is a real instance.

    A WebUI control's identity contains the preference it writes, because the
    preference alone is not unique. So a control that starts writing a
    different preference changes identity with it, and arrived as an unrelated
    removal plus addition -- 21 times across M130 -> M151.
    """

    def _feature(self, name, var):
        from chromiumdiff.model import Fact
        return Fact(kind="base_feature", key=name, name=name,
                    path="content/features.cc",
                    attrs={"var": var, "default_state": "enabled",
                           "platform_state": {"windows": "enabled"}})

    def _control(self, pref, element_id, control="settings-toggle-button"):
        from chromiumdiff.model import Fact
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

class TestTargetSetsAreHonestAboutCost(unittest.TestCase):
    """Three target sets, and each has to say what it costs and what it reads.

    Coverage is a property of a run, not of the tool, so nothing may hard-code
    it as a constant. Measured at M151: `default` reads 42 of the 1,039 files
    in the tree that could declare -- 4% of files, but more than half the
    `base::Feature` declarations, because the curated files are the large ones
    -- and `wide` reads all 1,039, for about 315 MB per version against 40.
    """

    def test_every_named_set_resolves(self):
        from chromiumdiff.targets import TARGET_SETS, get_targets
        for name in TARGET_SETS:
            self.assertTrue(get_targets(name), name)

    def test_wide_is_a_superset_of_default(self):
        """A release gate must never read *less* than a working run."""
        from chromiumdiff.targets import get_targets
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
        from chromiumdiff.extract import REGISTRY
        from chromiumdiff.targets import READABLE_SUFFIXES

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
        from chromiumdiff.targets import get_targets

        default_trees = {t.path for t in get_targets("default") if t.kind == "tree"}
        for target in get_targets("wide"):
            if target.kind == "tree" and target.path not in default_trees:
                self.assertTrue(target.include, f"{target.path} has no filter")

    def test_the_cache_key_separates_the_sets(self):
        """Otherwise a 40 MB snapshot gets reused as if it were the 315 MB one."""
        from chromiumdiff.snapshot import snapshot_path
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
        from chromiumdiff.targets import get_targets
        targets = get_targets("minimal")
        self.assertEqual(len(targets), 3, [t.path for t in targets])
        self.assertTrue(all(t.kind == "file" for t in targets))

    def test_minimal_is_a_subset_of_default(self):
        from chromiumdiff.targets import get_targets
        minimal = {t.path for t in get_targets("minimal")}
        default = get_targets("default")
        names = {t.path for t in default if t.kind == "file"}
        trees = [t.path.rstrip("/") + "/" for t in default if t.kind == "tree"]
        for path in minimal:
            self.assertTrue(path in names or any(path.startswith(p) for p in trees),
                            f"{path} is in minimal but not reachable from default")

    def test_every_partition_core_file_is_reachable_from_default(self):
        """PARTITION_CORE promises these to every partition."""
        from chromiumdiff.targets import PARTITION_CORE, get_targets
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
        from chromiumdiff.acquire import FetchTarget
        return [FetchTarget("chrome/browser/ui/webui", "tree", (".cc",)),
                FetchTarget("chrome/browser", "tree", ("prefs.h", ".mojom")),
                FetchTarget("chrome/common/pref_names.h", "file")]

    def test_a_wider_target_covers_what_a_narrower_one_excludes(self):
        from chromiumdiff.targets import reaches, scope_of
        files, trees = scope_of(self._targets())
        self.assertTrue(reaches(
            "chrome/browser/ui/webui/bookmarks/bookmark_prefs.h", files, trees))

    def test_a_path_no_target_claims_is_not_reached(self):
        from chromiumdiff.targets import reaches, scope_of
        files, trees = scope_of(self._targets())
        self.assertFalse(reaches("chrome/browser/ui/views/toolbar.cc", files, trees))

    def test_an_exact_file_target_is_reached(self):
        from chromiumdiff.targets import reaches, scope_of
        files, trees = scope_of(self._targets())
        self.assertTrue(reaches("chrome/common/pref_names.h", files, trees))

    def test_extraction_and_coverage_give_the_same_answer(self):
        """They used to disagree, which is the whole reason for one definition."""
        from chromiumdiff.catalog import scope_violations
        from chromiumdiff.model import Fact, Snapshot
        from chromiumdiff.targets import coverage_against, get_targets

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

    def test_catalog_agrees_with_the_shared_rule(self):
        """catalog measured on the path prefix and ignored the suffix filter.

        The default set asks for .cc under chrome/browser/ui/webui, so this
        header is never written to disk and never read. catalog counted it
        as covered -- an error in the reassuring direction, in the one
        command whose whole job is measuring the gap.
        """
        from chromiumdiff.catalog import covered_by_targets
        from chromiumdiff.targets import get_targets, reaches, scope_of

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
        from chromiumdiff.catalog import covered_by_targets
        from chromiumdiff.targets import get_targets

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
        from chromiumdiff.targets import could_declare

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
        from chromiumdiff.catalog import analyze
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
        from chromiumdiff.extract import constants
        from chromiumdiff.extract.base_features import FILE_HINTS

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
        from chromiumdiff.targets import READABLE_SUFFIXES

        for base in self._probe_basenames():
            self.assertTrue(
                any(base.endswith(s) for s in READABLE_SUFFIXES),
                f"{base} is read by an extractor but no fetch filter keeps it")

    def test_the_probes_are_really_read(self):
        """Guards the test itself: a probe nothing reads proves nothing."""
        from chromiumdiff.extract import REGISTRY

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
        for path in glob.glob(os.path.join(root, "chromiumdiff", "**", "*.py"),
                              recursive=True):
            if os.path.basename(path) == "base_features.py":
                continue
            with open(path, encoding="utf-8") as fh:
                if self.RULE.search(fh.read()):
                    offenders.append(os.path.relpath(path, root))
        self.assertEqual(offenders, [],
                         "re-use extract.base_features.feature_name_from_var")

    def test_every_consumer_agrees_with_it(self):
        from chromiumdiff.catalog import _bare
        from chromiumdiff.cluster import _flag_name
        from chromiumdiff.extract.base_features import feature_name_from_var

        for probe in ("kBackForwardCache", "kDIPS", "kilo", "k", "Feature", ""):
            expected = feature_name_from_var(probe)
            self.assertEqual(_bare(probe), expected, probe)
            self.assertEqual(_flag_name(probe), expected, probe)

    def test_the_inverse_round_trips_through_the_same_rule(self):
        """`enrich.gerrit` needs the rule backwards, and asks the same owner.

        A feature's declaration line is written as `kFoo` since the macro
        dropped its string argument, so a diff searched for `Foo` alone misses
        it. The inverse therefore has to agree with the forward rule on what
        counts as an identifier -- otherwise the search asks for a spelling
        that is not in the file.
        """
        from chromiumdiff.extract.base_features import (feature_name_from_var,
                                                       var_from_feature_name)

        for probe in ("BackForwardCache", "DIPS", "Feature"):
            var = var_from_feature_name(probe)
            self.assertEqual(feature_name_from_var(var), probe, probe)
        for already in ("kBackForwardCache", "kDIPS"):
            self.assertEqual(var_from_feature_name(already), already, already)


class TestTheReportCarriesItsOwnCoverage(unittest.TestCase):
    """How much of the tree was read bounds every count above it.

    It was printed to stderr and stored on the snapshot, and then not carried
    into the report, while README and SKILL.md both said the report held it.
    It now also decides two things in the scoring -- what an unconfirmed
    removal scores and where it is filed -- so the number the report states and
    the number the ranking used have to be the same one.
    """

    def _report(self):
        from chromiumdiff.score import summarize_findings
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

    def test_the_summary_claims_no_coverage_of_its_own(self):
        """One name per measurement. `summary.coverage` used to be area
        routing while `meta.coverage` was tree coverage, so a reader -- or an
        agent -- looking up one found the other with nothing saying so."""
        from chromiumdiff.score import summarize_findings
        self.assertNotIn("coverage", summarize_findings([]))

    def test_the_ranking_reads_the_same_measurement_the_report_prints(self):
        from chromiumdiff.score import Scope
        meta = self._report().meta
        scope = Scope({"to": meta["coverage"]["to"]}, to_ref="refs/tags/151")
        self.assertFalse(scope.confirms_absence())
        self.assertEqual(scope.read_percent(), "4%")

    def test_tree_coverage_survives_into_the_report_json(self):
        blob = self._report().to_dict()
        self.assertEqual(blob["meta"]["coverage"]["to"]["read"], 42)
        self.assertEqual(blob["meta"]["uncovered_files"],
                         ["chrome/browser/x_prefs.h"])

    def test_the_rendered_report_states_it(self):
        from chromiumdiff.report import markdown as md
        text = md.render(self._report())
        self.assertIn("read 42 of 1,039 files", text)
        self.assertIn("`chrome/browser/` (251 files)", text)
        self.assertIn("--target-set wide", text)

    def test_a_wide_run_is_not_told_to_widen(self):
        from chromiumdiff.report import markdown as md
        report = self._report()
        report.meta["target_set"] = "wide"
        self.assertNotIn("--target-set wide", md.render(report))

    def test_a_report_without_the_measurement_renders_no_empty_row(self):
        from chromiumdiff.report import markdown as md
        report = self._report()
        report.meta["coverage"] = {}
        self.assertNotIn("Coverage at", md.render(report))


class TestTheControlRuleAndItsWordsAgree(unittest.TestCase):
    """What the extractor admits, the renderer has to be able to name.

    Two lists, and they had drifted in both directions at once.
    `wording.CONTROL_WORDS` carried `collapse-radio-button`, a tag the old
    extractor never emitted because it was not one of the 27 names in
    `CONTROL_TAGS`; and `cr-searchable-drop-down` was emitted and came out as
    its raw tag, because no word matched it. A tag that reaches the report
    unnamed is the jargon that table exists to remove.
    """

    def test_every_admissible_tag_gets_a_word(self):
        from chromiumdiff.extract.webui_controls import (INTERACTIVE_SEGMENTS,
                                                        STRUCTURAL_TAGS)
        from chromiumdiff.report.wording import control_word

        unnamed = [tag for tag in
                   [f"cr-{seg}" for seg in sorted(INTERACTIVE_SEGMENTS)]
                   + sorted(STRUCTURAL_TAGS)
                   if control_word(tag) == tag]
        self.assertEqual(unnamed, [],
                         "these tags reach the report as raw tag names")

    def test_the_rule_admits_what_it_was_built_for(self):
        from chromiumdiff.extract.webui_controls import is_control

        for tag in ("settings-toggle-button", "cr-icon-button",
                    "settings-collapse-radio-button", "cr-action-menu",
                    "settings-category-default-radio-group",
                    "cr-searchable-drop-down"):
            self.assertTrue(is_control(tag, "", element_id="x"), tag)

    def test_the_rule_keeps_decoration_out(self):
        from chromiumdiff.extract.webui_controls import is_control

        for tag in ("cr-icon", "cr-iconset", "cr-ripple", "site-favicon",
                    "iron-media-query"):
            self.assertFalse(is_control(tag, "", element_id="x", label="y"), tag)

    def test_a_preference_makes_anything_a_control(self):
        """The rule that recovered the 41 the name list was dropping."""
        from chromiumdiff.extract.webui_controls import is_control

        self.assertTrue(is_control("some-unknown-widget", "download.prompt"))
        self.assertFalse(is_control("some-unknown-widget", ""))

    def test_an_interactive_tag_with_no_identity_is_not_worth_a_fact(self):
        """Position is the only identity left, and it churns on reorder."""
        from chromiumdiff.extract.webui_controls import is_control

        self.assertFalse(is_control("cr-button", ""))
        self.assertTrue(is_control("cr-button", "", element_id="save"))
        self.assertTrue(is_control("cr-button", "", label="saveLabel"))


class TestATruncatedTreeIsRefused(unittest.TestCase):
    """The target-set guard was one derivation short of its own reasoning.

    It compares the *label* a snapshot was built under, which catches `minimal`
    against `default` and nothing else. Two sides both labelled "default" pass
    it even when one is a truncated checkout -- and `--local-src` / `--to-src`
    is exactly how that happens. Pointed at a partial tree, one side of a
    real run held 1,647 facts against the other's 24,959 and the tool said
    nothing: it printed "scope: ok" twice, because every fact really did come
    from a file the target set asked for, then reported 23,318 removals that
    had not happened.
    """

    def _snap(self, ref, n, kind="base_feature"):
        from chromiumdiff.model import Fact, Snapshot
        return Snapshot(ref=ref, meta={"target_set": "default"},
                        facts=[Fact(kind, f"F{i}", f"F{i}", path="a.cc",
                                    attrs={"default_state": "enabled"})
                               for i in range(n)])

    def test_a_side_holding_a_fraction_of_the_other_is_refused(self):
        from chromiumdiff.diff import diff_snapshots
        with self.assertRaises(ValueError) as caught:
            diff_snapshots(self._snap("full", 24959), self._snap("partial", 1647))
        message = str(caught.exception)
        self.assertIn("truncated tree", message)
        # The message has to name the thing to check, not just the numbers.
        self.assertIn("--to-src", message)

    def test_two_real_versions_are_not_refused(self):
        """M143 holds 24,113 facts against M151's 24,959 -- 3% apart."""
        from chromiumdiff.diff import diff_snapshots
        diff_snapshots(self._snap("m143", 24113), self._snap("m151", 24959))

    def test_an_empty_side_is_refused(self):
        from chromiumdiff.diff import diff_snapshots
        with self.assertRaises(ValueError) as caught:
            diff_snapshots(self._snap("good", 24959), self._snap("broken", 0))
        self.assertIn("no facts at all", str(caught.exception))

    def test_small_fixtures_are_left_alone(self):
        """A ratio over a handful of facts is noise, not evidence.

        Without a floor this guard fires on every unit test in this file that
        builds a one-fact snapshot against a three-fact one, which is how it
        was first written.
        """
        from chromiumdiff.diff import diff_snapshots
        diff_snapshots(self._snap("a", 1), self._snap("b", 9))


class TestMissingTargetsReachTheReport(unittest.TestCase):
    """A target that was never fetched is a file's worth of facts missing.

    `cmd_snapshot` printed it and the snapshot recorded it, and there it
    stopped: `run` never read it back, so on the cache hit that every second
    run is, the warning did not appear at all -- and it was in none of the
    three report files. Same shape as the coverage figure that schema 16 had to
    rescue from scrollback.
    """

    def _report(self, missing):
        from chromiumdiff.model import Report
        return Report(from_ref="a", to_ref="b", findings=[],
                      summary={}, meta={"missing_targets": missing})

    def test_the_markdown_names_them(self):
        from chromiumdiff.report import markdown as md
        text = md.render(self._report({"b": ["net/base/features.cc",
                                             "media/base/media_switches.cc"]}))
        self.assertIn("2 target(s) absent from `b`", text)
        self.assertIn("net/base/features.cc", text)

    def test_nothing_is_said_when_nothing_is_missing(self):
        from chromiumdiff.report import markdown as md
        self.assertNotIn("absent from", md.render(self._report({"b": []})))


class TestCoverageIsGradedAgainstTheTree(unittest.TestCase):
    """A denominator you choose is how a coverage number flatters itself.

    `DISCOVERY_ROOTS` was the fourteen roots the fetch targets happen to live
    under, so the per-run measurement graded `wide` against the ground `wide`
    already covered: 1,039 of 1,039, reported as 100%, while `catalog` -- which
    walks the real tree -- counted 1,192 files the same rule admits. The 153 in
    the gap could never surface as missed, and they hold real declarations:
    `base/base_switches.h`, `cc/base/features.cc`,
    `device/fido/public/features.cc`.

    README says the two "describe the same population". This is that sentence
    as a test.
    """

    ROOTS_MUST_COVER = (
        "base/base_switches.h",
        "base/features.cc",
        "cc/base/features.cc",
        "device/fido/public/features.cc",
        "sandbox/policy/features.cc",
        "google_apis/gaia/gaia_switches.cc",
        "storage/browser/quota/quota_features.cc",
        "pdf/pdf_features.cc",
        "mojo/core/embedder/features.cc",
        "chrome/renderer/chrome_render_frame_features.cc",
        "third_party/blink/renderer/platform/features.cc",
    )

    def test_a_file_the_rule_admits_is_inside_a_root(self):
        """Otherwise it cannot be counted, however wide the run."""
        from chromiumdiff.targets import DISCOVERY_ROOTS, could_declare

        roots = tuple(r.rstrip("/") + "/" for r in DISCOVERY_ROOTS)
        outside = [p for p in self.ROOTS_MUST_COVER
                   if could_declare(p) and not p.startswith(roots)]
        self.assertEqual(outside, [],
                         "the rule says these can declare, but no root lists "
                         "them, so the measurement can never see them")

    def test_vendored_third_party_is_excluded_by_name(self):
        """Named, so both measurements agree rather than merely coinciding.

        Left to fall outside the roots instead, `catalog` would count these
        while the per-run measurement could not, and the two numbers would
        disagree for a reason nobody had written down.
        """
        from chromiumdiff.targets import could_declare

        for path in ("third_party/zlib/cpu_features.h",
                     "third_party/abseil-cpp/absl/base/features.h",
                     "third_party/webrtc_overrides/field_trial.cc"):
            self.assertIsNone(could_declare(path), path)
        # Blink is Chromium's own code and stays in.
        self.assertIsNotNone(
            could_declare("third_party/blink/renderer/platform/features.cc"))

    def test_the_two_measurements_describe_one_population(self):
        """Checked against a real tree listing when one is on disk."""
        import glob

        from chromiumdiff.targets import (DISCOVERY_ROOTS, could_declare,
                                         discover_candidates)

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        listings = glob.glob(os.path.join(root, ".chromiumdiff-cache",
                                          "listings", "*", "*.json"))
        if not listings:
            self.skipTest("no cached tree listings here")

        # Every path any listing holds, as the whole tree the run can see.
        import json as _json
        paths = []
        by_ref = {}
        for path in listings:
            ref = os.path.basename(os.path.dirname(path))
            with open(path, encoding="utf-8") as fh:
                by_ref.setdefault(ref, []).extend(_json.load(fh))
        ref, paths = max(by_ref.items(), key=lambda kv: len(kv[1]))

        roots = tuple(r.rstrip("/") + "/" for r in DISCOVERY_ROOTS)
        admitted = [p for p in paths if could_declare(p)]
        unreachable = [p for p in admitted if not p.startswith(roots)]
        self.assertEqual(unreachable[:5], [],
                         f"{ref}: {len(unreachable)} files the rule admits sit "
                         f"outside every root, so no run can count them")


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

        from chromiumdiff.extract import run_on_tree
        import chromiumdiff.extract as ex

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
        from chromiumdiff.model import Fact, dedupe_facts

        low = Fact("pref", "shared", "shared", path="components/alpha/p.cc")
        high = Fact("pref", "shared", "shared", path="components/zebra/p.cc")
        for order in ((low, high), (high, low)):
            kept = dedupe_facts(order)
            self.assertEqual([f.path for f in kept], ["components/alpha/p.cc"])

    def test_an_earlier_line_in_one_file_wins(self):
        from chromiumdiff.model import Fact, dedupe_facts

        first = Fact("switch", "s", "s", path="a.cc", line=10)
        second = Fact("switch", "s", "s", path="a.cc", line=90)
        self.assertEqual(dedupe_facts([second, first])[0].line, 10)


class TestBuildGuardsAreRecordedAndResolved(unittest.TestCase):
    """A guard decides whether a declaration is in the binary we ship.

    Only `base::Feature` recorded one, so the comparison could see
    11% of the surface and none of the preference keys -- the thing the README
    calls the most expensive to get wrong. Resolving the guard for Windows also
    gives the scoring stage something to act on: 115 keys at M151 are not in a
    Windows build at all, and nothing had marked them.
    """

    def _pref(self, source):
        from chromiumdiff.extract import constants
        return {f.key: f.attrs for f in constants.extract(source, "components/x/pref_names.cc")}

    def test_a_headers_include_guard_is_not_a_build_guard(self):
        from chromiumdiff.extract import constants
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
        from chromiumdiff.extract._cpp import conditional_spans, enclosing_conditions
        source = ('#if defined(ENABLE_X)\nA\n'
                  '#elif BUILDFLAG(IS_WIN)\nB\n#else\nC\n#endif\n')
        spans = conditional_spans(source)
        self.assertEqual(enclosing_conditions(spans, source.index("\nB") + 1),
                         ["!(defined(ENABLE_X))", "BUILDFLAG(IS_WIN)"])
        self.assertEqual(enclosing_conditions(spans, source.index("\nC") + 1),
                         ["!(defined(ENABLE_X))", "!(BUILDFLAG(IS_WIN))"])

    def test_a_plain_else_is_unchanged(self):
        from chromiumdiff.extract._cpp import conditional_spans, enclosing_conditions
        source = "#if BUILDFLAG(IS_WIN)\nA\n#else\nB\n#endif\n"
        self.assertEqual(
            enclosing_conditions(conditional_spans(source), source.index("\nB") + 1),
            ["!(BUILDFLAG(IS_WIN))"])

    def test_a_grit_condition_is_read_by_the_same_evaluator(self):
        from chromiumdiff.extract._cpp import eval_grit_condition
        self.assertIs(eval_grit_condition("not is_win"), False)
        self.assertIs(eval_grit_condition("is_win or is_macosx"), True)
        self.assertIs(eval_grit_condition("is_macosx or is_linux"), False)
        self.assertIsNone(eval_grit_condition("_google_chrome"))

    def test_a_control_grit_excludes_is_scored_down(self):
        from chromiumdiff.score import score_change
        from chromiumdiff.model import Change
        change = Change(change_type="modified", kind="webui_control",
                        key="k", name="k",
                        before={"platform_state": {"windows": "not_compiled"}},
                        after={"platform_state": {"windows": "not_compiled"}})
        finding = score_change(change)
        self.assertEqual(finding.score, 0)
        self.assertTrue(any("not compiled" in r for r in finding.reasons),
                        finding.reasons)


class TestEveryComparedAttributeIsExplained(unittest.TestCase):
    """A row with a severity and a blank reason column is unreadable.

    An attribute in `MEANINGFUL_ATTRS` is there because someone decided a
    change to it carries meaning. If it then moves and the report
    says nothing about what moved, the reader has to open the source. Measured
    M148 -> M151, 380 of 709 modified changes arrived that way, including a
    preference whose C++ constant had been renamed.
    """

    def _change(self, kind, attr, before, after):
        from chromiumdiff.diff import _make_change
        from chromiumdiff.model import Fact
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
        from chromiumdiff.diff import _make_change
        from chromiumdiff.model import Fact
        old = Fact("blink_runtime_feature", "F", "F", attrs={"base_feature": "F"})
        new = Fact("blink_runtime_feature", "F", "F", attrs={"base_feature": "none"})
        change = _make_change("modified", old, new, "windows", 151,
                              {"base_feature": ["F", "none"]})
        self.assertIn("runtime_flag_rewired", change.signals)

    def test_labelling_the_expiry_moves_changed_no_ranking(self):
        """281 of them at M148 -> M151; the floor stays under the base."""
        from chromiumdiff.diff import BASE_SEVERITY, SIGNAL_SEVERITY
        self.assertLess(SIGNAL_SEVERITY["flag_expiry_moved"],
                        BASE_SEVERITY[("flag_entry", "modified")])

    # A value for every attribute the comparison treats as meaningful, chosen
    # so that moving it is a real move rather than a type accident. Kept beside
    # the invariant it feeds rather than inside it, because adding an attribute
    # to MEANINGFUL_ATTRS should fail here loudly until someone says what a
    # change to it means.
    _SAMPLE = {
        "default_state": ("disabled", "enabled"),
        "signatures": (["void f()"], ["void f()", "void f(long a)"]),
        "overload_traits": (["void f() [A]"], ["void f() [B]"]),
        "position": (0, 1),
        "stable": (None, True),
        "min_version": (None, "2"),
        "inherited_conditions": (["EnableIf=is_win"], []),
        "platform_state": ({"windows": "disabled"}, {"windows": "enabled"}),
        "platform_status": ({"windows": "test"}, {"windows": "stable"}),
        "windows_status": ("test", "stable"),
        "status": ("experimental", "stable"),
        "conditions": ([], ["BUILDFLAG(IS_WIN)"]),
        "build_conditions": (["is_win"], ["not is_win"]),
        "var": ("kOld", "kNew"),
        "default": ("100", "200"),
        "type": ("int", "double"),
        "feature": ("OldOwner", "NewOwner"),
        "signature": ("a()", "b()"),
        "params": ("int32 a", "int32 a, bool b"),
        "response": ("", "(bool ok)"),
        "attrs": ({}, {"Sync": True}),
        "member_type": ("attribute", "operation"),
        "idl_kind": ("interface", "dictionary"),
        "inherits": ("", "Base"),
        "ext": ({}, {"SecureContext": True}),
        "values": (["a"], ["a", "b"]),
        "runtime_enabled": ("", "SomeFlag"),
        "module": ("blink.mojom", "other.mojom"),
        # A struct becoming a union is a different wire format under an
        # unchanged name; an ordinal moving reassigns which bytes are which.
        "mojo_kind": ("struct", "union"),
        "ordinal": ("0", "1"),
        "expiry_milestone": (150, 160),
        "route": ("/a", "/b"),
        "parent": ("", "PARENT"),
        "guards": ([], ["someKey"]),
        "control": ("cr-toggle", "cr-checkbox"),
        "pref": ("a.b", "a.c"),
        "label": ("labelA", "labelB"),
        "expression": ("IsEnabled(kA)", "IsEnabled(kB)"),
        "features": (["kA"], ["kB"]),
        "enabled_checks": (["kA"], ["kB"]),
        "base_feature": ("Feature", "none"),
        "base_feature_status": ("stable", "test"),
        "origin_trial_feature_name": ("", "Trial"),
        "depends_on": ([], ["Other"]),
        "implied_by": ([], ["Other"]),
        "public": (False, True),
        "copied_from_base_feature_if": ("", "overridden"),
        "origin_trial_allows_third_party": (False, True),
        "settable_from_internals": (False, True),
        "browser_process_read_access": (False, True),
        "browser_process_read_write_access": (False, True),
        "origin_trial_os": ([], ["win"]),
        "origin_trial_type": ("", "deprecation"),
        "origin_trial_allows_insecure": (False, True),
        "is_protected_feature": (False, True),
    }

    def test_every_compared_attribute_produces_a_signal(self):
        """The invariant itself, with no snapshots needed to check it.

        The real-range test below is the one that found these, but it only runs
        where someone has already pulled two versions -- so on a bare checkout
        the rule went unchecked, and four attributes had drifted out from under
        it: a base::Feature's `conditions`, a Mojo method's `attrs`, a Windows
        state moving to `conditional`, and the three Blink fields that say who
        may reach a flag from outside the renderer.
        """
        from chromiumdiff.diff import MEANINGFUL_ATTRS

        missing_sample = []
        unexplained = []
        for kind, attrs in MEANINGFUL_ATTRS.items():
            for attr in attrs:
                if attr not in self._SAMPLE:
                    missing_sample.append(f"{kind}.{attr}")
                    continue
                before, after = self._SAMPLE[attr]
                change = self._change(kind, attr, before, after)
                if not change.signals:
                    unexplained.append(f"{kind}.{attr}")

        self.assertEqual(missing_sample, [],
                         "no sample value here, so the rule cannot be checked "
                         "for these -- add one to _SAMPLE")
        self.assertEqual(unexplained, [],
                         "compared and then never explained: a row with a "
                         "severity and a blank reason column")

    def test_no_modified_change_in_the_real_range_is_unexplained(self):
        import glob

        from chromiumdiff.diff import diff_snapshots
        from chromiumdiff.model import SCHEMA_VERSION, Snapshot, read_json

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        snaps = {}
        for path in glob.glob(os.path.join(root, ".chromiumdiff-cache",
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
    36,356 facts), a fifth set one that was wrong, and nothing further along read
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
        from chromiumdiff.extract import mojom
        found = self._lines(mojom.extract(self.MOJOM, "a/b.mojom"), self.MOJOM)
        self.assertEqual(found["Pinger"][0], 6)
        self.assertIn("interface Pinger", found["Pinger"][1])

    def test_every_mojo_method_has_its_own_line(self):
        from chromiumdiff.extract import mojom
        found = self._lines(mojom.extract(self.MOJOM, "a/b.mojom"), self.MOJOM)
        self.assertEqual(found["Ping"][0], 7)
        self.assertEqual(found["Pong"][0], 8)

    def test_every_idl_member_has_its_own_line(self):
        from chromiumdiff.extract import web_idl
        path = "third_party/blink/renderer/core/x.idl"
        found = self._lines(web_idl.extract(self.IDL, path), self.IDL)
        self.assertEqual(found["width"][0], 2)
        self.assertEqual(found["resize"][0], 3)

    def test_a_blink_flag_has_a_line_on_either_layout(self):
        from chromiumdiff.extract import blink_runtime
        path = "third_party/blink/renderer/platform/runtime_enabled_features.json5"
        found = self._lines(blink_runtime.extract(self.JSON5, path), self.JSON5)
        self.assertEqual(found["Alpha"][0], 4)
        self.assertEqual(found["Beta"][0], 7, "a brace sharing the line still counts")

    def test_a_flag_entry_has_a_line_on_either_layout(self):
        from chromiumdiff.extract import flags_metadata
        path = "chrome/browser/flag-metadata.json"
        found = self._lines(flags_metadata.extract(self.FLAGS, path), self.FLAGS)
        self.assertEqual(found["alpha-flag"][0], 3)
        self.assertEqual(found["beta-flag"][0], 6)

    def test_the_line_never_walks_back_to_the_line_above(self):
        """`\\s` matches newlines; `[ \\t]` is what these patterns need."""
        from chromiumdiff.extract import blink_runtime, flags_metadata
        for module, source, name in (
                (blink_runtime, self.JSON5, "Alpha"),
                (flags_metadata, self.FLAGS, "alpha-flag")):
            lines = module.name_lines(source)
            self.assertIn(name, source.splitlines()[lines[name] - 1])

    def test_the_change_carries_the_place_not_just_the_file(self):
        from chromiumdiff.diff import _make_change
        from chromiumdiff.model import Fact
        old = Fact("mojo_method", "k", "k", path="a/b.mojom", line=41)
        new = Fact("mojo_method", "k", "k", path="a/b.mojom", line=87)
        change = _make_change("modified", old, new, "windows", 151,
                              {"signature": ["x", "y"]})
        self.assertEqual(change.locations, ["a/b.mojom:41", "a/b.mojom:87"])
        self.assertEqual(change.paths, ["a/b.mojom"],
                         "the profile matches path prefixes; keep them clean")

    def test_both_renderers_show_it(self):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report
        from chromiumdiff.report import markdown as md_report
        change = Change(change_type="modified", kind="mojo_method",
                        key="blink.mojom.X.Y", name="Y",
                        paths=["a/b.mojom"], locations=["a/b.mojom:41"],
                        signals=["ipc_signature_change"], severity=80)
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=change, score=80,
                                          bucket="behaviour")])
        self.assertIn("a/b.mojom:41", md_report.render(report))
        self.assertIn("a/b.mojom:41", html_report.render(report))

    def test_a_report_from_before_this_still_renders(self):
        """Version 20 reports have no locations; fall back to the file."""
        from chromiumdiff.model import Report
        from chromiumdiff.report import markdown as md_report
        blob = {"from_ref": "a", "to_ref": "b", "findings": [{
            "change": {"change_type": "modified", "kind": "mojo_method",
                       "key": "k", "name": "Y", "paths": ["a/b.mojom"],
                       "signals": [], "severity": 80},
            "score": 80, "bucket": "behaviour"}]}
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
        from chromiumdiff.extract import web_idl
        self.assertTrue(web_idl.applies_to(
            "third_party/blink/renderer/modules/webgl/x.idl"))
        self.assertTrue(web_idl.applies_to(
            "third_party/blink/renderer/core/dom/element.idl"))

    def test_the_extensions_dialect_is_not(self):
        from chromiumdiff.extract import web_idl
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
        from chromiumdiff.extract import web_idl
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
        for path in glob.glob(os.path.join(root, "chromiumdiff", "**", "*.py"),
                              recursive=True):
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if "dirnames[:]" in line and "= sorted" not in line:
                        offenders.append(f"{os.path.basename(path)}:{lineno}")
        self.assertEqual(offenders, [])

class TestTheReportSaysWhatChangedOnEachScreen(unittest.TestCase):
    """A row reading `id:cancelButton` answers none of the reader's questions.

    It does not say which page the control is on, whether it arrived or
    vanished, or what kind of control it is -- and the same loadTimeData key
    appears once per handler that sets it, so `webuiRefresh2026` showed up nine
    times with nothing to tell the nine apart. Every field needed to answer all
    of that was already on the facts and was simply never rendered.
    """

    def _control(self, change_type="added", **attrs):
        from chromiumdiff.model import Change
        base = {"surface": "settings", "page": "privacy_page",
                "control": "settings-toggle-button", "element_id": "httpsOnly",
                "pref": "generated.https_first_mode_enabled", "label": ""}
        base.update(attrs)
        side = {"after": base} if change_type != "removed" else {"before": base}
        return Change(change_type=change_type, kind="webui_control",
                      key="settings/privacy_page/p/id:httpsOnly",
                      name="id:httpsOnly", **side)

    def test_a_control_names_its_screen(self):
        from chromiumdiff.report import wording as surfaces
        self.assertEqual(surfaces.screen_of(self._control()),
                         "settings › privacy_page")

    def test_a_gate_is_placed_by_the_handler_that_sets_it(self):
        """Otherwise every gate lands in one undifferentiated pile."""
        from chromiumdiff.model import Change
        from chromiumdiff.report import wording as surfaces
        for handler, screen in (("downloads_ui", "downloads"),
                                ("new_tab_page_ui", "new_tab_page"),
                                ("history_util", "history")):
            change = Change(change_type="added", kind="webui_gate",
                            key=f"{handler}/showThing", name="showThing",
                            after={"handler": handler, "features": ["kThing"]})
            self.assertEqual(surfaces.screen_of(change), screen)

    def test_a_control_is_described_in_words(self):
        from chromiumdiff.report import wording as surfaces
        self.assertEqual(
            surfaces.describe(self._control()),
            "toggle — httpsOnly (writes generated.https_first_mode_enabled)")

    def test_a_retyped_control_shows_both_types(self):
        from chromiumdiff.report import wording as surfaces
        change = self._control("modified", control="settings-toggle-button")
        change.deltas = {"control": ["settings-dropdown-menu",
                                     "settings-toggle-button"]}
        self.assertIn("dropdown → toggle", surfaces.describe(change))

    def test_a_route_says_what_shows_it(self):
        from chromiumdiff.model import Change
        from chromiumdiff.report import wording as surfaces
        change = Change(change_type="added", kind="webui_route",
                        key="settings/AI", name="AI",
                        after={"surface": "settings", "route": "/ai",
                               "guards": ["showAiPage"]})
        self.assertEqual(surfaces.describe(change),
                         "page /ai (shown when showAiPage)")

    def test_screens_group_and_count_by_direction(self):
        from chromiumdiff.model import Finding
        from chromiumdiff.report import wording as surfaces
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
        from chromiumdiff.model import Finding
        from chromiumdiff.report import wording as surfaces
        findings = [Finding(change=self._control("removed"), score=90),
                    Finding(change=self._control("added"), score=10)]
        order = [f.change.change_type
                 for f in surfaces.build(findings)[0].sorted_items()]
        self.assertEqual(order, ["added", "removed"])

    def test_nothing_but_screens_is_grouped(self):
        from chromiumdiff.model import Change, Finding
        from chromiumdiff.report import wording as surfaces
        flag = Change(change_type="added", kind="base_feature", key="F", name="F")
        self.assertEqual(surfaces.build([Finding(change=flag)]), [])

    def test_both_renderers_carry_the_section(self):
        from chromiumdiff.model import Finding, Report
        from chromiumdiff.report import html as html_report
        from chromiumdiff.report import markdown as md_report
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=self._control(), score=30,
                                          bucket="behaviour")])
        md = md_report.render(report)
        self.assertIn("What changed on each screen", md)
        # The page answers the same question per row, in the Where column: a
        # control that names no page is the row nobody can act on.
        row = html_report._to_rows(report, "windows")[0]
        self.assertEqual(row["where"], "settings › privacy_page")
        for text in (md, html_report.render(report)):
            self.assertIn("settings › privacy_page", text)
            self.assertIn("toggle", text)

    def test_the_table_carries_the_direction_and_the_place(self):
        """Both were reachable only by opening a row, or not at all."""
        from chromiumdiff.model import Finding, Report
        from chromiumdiff.report import html as html_report
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=self._control(), score=30,
                                          bucket="behaviour")])
        row = html_report._to_rows(report, "windows")[0]
        self.assertEqual(row["change_type"], "added")
        self.assertEqual(row["where"], "settings › privacy_page")
        self.assertIn("toggle", row["what"])

    def test_a_report_with_no_screens_renders_no_empty_section(self):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import markdown as md_report
        flag = Change(change_type="added", kind="base_feature", key="F", name="F")
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=flag, score=20, bucket="housekeeping")])
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
        from chromiumdiff.diff import _severity_for
        from chromiumdiff.model import Change
        change = Change(change_type=change_type, kind=kind,
                        key=kw.pop("key", "K"), name=kw.pop("name", "K"), **kw)
        change.signals = list(signals)
        change.severity = _severity_for(change)
        return change

    def test_the_story_is_the_signal_that_set_the_severity(self):
        """Otherwise a finding is filed under one sentence and ranked by another."""
        from chromiumdiff.diff import SIGNAL_SEVERITY, leading_signal
        from chromiumdiff.report import wording as surfaces

        change = self._change(signals=["flag_expiring", "flag_retired_on",
                                       "declaration_moved"])
        top = leading_signal(change)
        self.assertEqual(top, max(change.signals,
                                  key=lambda s: SIGNAL_SEVERITY[s]))
        self.assertEqual(surfaces.story_of(change)[0], top)
        self.assertEqual(change.severity, SIGNAL_SEVERITY[top])

    def test_the_pick_does_not_depend_on_signal_order(self):
        from chromiumdiff.report import wording as surfaces
        pair = ["flag_expiring", "flag_retired_on"]
        first = surfaces.story_of(self._change(signals=pair))
        second = surfaces.story_of(self._change(signals=list(reversed(pair))))
        self.assertEqual(first, second)

    def test_a_change_with_no_signal_still_has_a_headline(self):
        """A third of a real report carries no signal -- things that only arrived."""
        from chromiumdiff.model import ALL_KINDS
        from chromiumdiff.report import wording as surfaces
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
        from chromiumdiff.model import ALL_KINDS, KIND_GROUPS, Finding
        from chromiumdiff.report import wording as surfaces

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
        from chromiumdiff.model import ALL_KINDS, KIND_GROUPS, group_of
        grouped = [k for _, kinds in KIND_GROUPS for k in kinds]
        self.assertEqual(sorted(grouped), sorted(ALL_KINDS))
        self.assertEqual(len(set(grouped)), len(grouped))
        self.assertTrue(all(group_of(k) for k in ALL_KINDS))

    def test_the_heaviest_story_leads(self):
        from chromiumdiff.model import Finding
        from chromiumdiff.report import wording as surfaces
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
        from chromiumdiff.model import Finding, Report
        from chromiumdiff.report import html as html_report
        from chromiumdiff.report import markdown as md_report
        report = Report(from_ref="a", to_ref="b", findings=[
            Finding(change=self._change(signals=["enabled_by_default"]),
                    score=75, bucket="behaviour")])
        md = md_report.render(report)
        html_text = html_report.render(report)
        for text in (md, html_text):
            self.assertIn("Now ON by default on Windows", text)
        # The markdown groups by consequence and says what the group means.
        self.assertIn("Behaviour switches", md)
        self.assertIn("moves behaviour on its own", md)
        # The page carries it per row, in the What happened column.
        self.assertIn("What happened", html_text)
        self.assertIn("enabled_by_default", html_text)

    def test_the_html_says_what_happened_on_every_row(self):
        """The column is only useful if the lookup table holds every key."""
        import json
        import re

        from chromiumdiff.model import Finding, Report
        from chromiumdiff.report import html as html_report

        report = Report(from_ref="a", to_ref="b", findings=[
            Finding(change=self._change(key="a", signals=["enabled_by_default"]),
                    score=75, bucket="behaviour"),
            Finding(change=self._change(key="b", kind="flag_entry",
                                        change_type="removed"),
                    score=30, bucket="housekeeping")])
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
        """A triage count is a button; it must open the rows it counted.

        The cards and the table are built from the same findings by different
        code, so a count that counted something slightly different -- changes
        rather than findings -- would send the reader to a table showing a
        different number from the one they clicked.
        """
        import json
        import re

        from chromiumdiff.model import ALL_KINDS, BUCKET_ORDER, Finding, Report
        from chromiumdiff.report import html as html_report

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
        printed = re.findall(
            r'data-set="(\w+):([\w_]+)"[^>]*>\s*<span class="n">([\d,]+)'
            r'</span>', text)
        self.assertEqual(len(printed), len(BUCKET_ORDER), printed)
        for which, value, count in printed:
            field = {"fk": "kind", "fb": "bucket"}[which]
            self.assertEqual(int(count.replace(",", "")),
                             sum(1 for r in rows if r[field] == value),
                             f"{which}:{value} sends the reader to a different "
                             f"number from the one it prints")

    def test_a_long_delta_does_not_take_over_the_table_cell(self):
        """A Mojo signature runs past 400 characters."""
        from chromiumdiff.model import Finding, Report
        from chromiumdiff.report import html as html_report

        change = self._change(kind="mojo_method", change_type="modified",
                              signals=["ipc_signature_change"])
        change.deltas = {"signature": ["uint32 a, " * 60, "uint32 b, " * 60]}
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=change, score=80,
                                          bucket="behaviour")])
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
        for path in glob.glob(os.path.join(root, "chromiumdiff", "**", "*.py"),
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


class TestAMojoOrdinalChangeReachesTheReport(unittest.TestCase):
    """Extracting a fact is not the same as comparing it.

    This pipeline has two doors -- the extractor makes a Fact, and
    `MEANINGFUL_ATTRS` decides which of its fields a diff looks at. The
    previous commit opened the first, wrote "the ordinal is now a compared
    attribute" in its message, and asserted only that the key existed on the
    fact. `Foo@0 -> Foo@1` produced no change at all, on the surface this tool
    ranks highest, and the suite stayed green.

    So this one drives the whole path: two snapshots in, a scored finding out.
    """

    def _snap(self, ref, body):
        from chromiumdiff.extract import mojom
        return Snapshot(ref=ref, facts=mojom.extract(
            f"module t;\ninterface I {{\n  {body}\n}};\n", "t.mojom"),
            meta={"target_set": "default"})

    def test_a_moved_ordinal_is_a_breaking_change(self):
        changes = diff_snapshots(self._snap("148.0.0.0", "Foo@0(int32 a);"),
                                 self._snap("151.0.0.0", "Foo@1(int32 a);"))
        methods = [c for c in changes if c.kind == "mojo_method"]
        self.assertEqual(len(methods), 1)
        change = methods[0]
        self.assertEqual(change.deltas, {"ordinal": ["0", "1"]})
        self.assertEqual(change.signals, ["ipc_ordinal_changed"])
        finding = score_change(change)
        self.assertEqual(finding.score, 80)
        self.assertEqual(finding.bucket, "breaking")

    def test_the_row_says_what_moved(self):
        """A reader must not have to open the mojom to see it."""
        from chromiumdiff.report import wording
        change = [c for c in diff_snapshots(
            self._snap("148.0.0.0", "Foo@0(int32 a);"),
            self._snap("151.0.0.0", "Foo@1(int32 a);"))
            if c.kind == "mojo_method"][0]
        self.assertIn("ordinal", wording.story_of(change)[0].lower())

    def test_an_unchanged_ordinal_is_not_a_change(self):
        self.assertEqual(
            [c for c in diff_snapshots(self._snap("148.0.0.0", "Foo@0(int32 a);"),
                                       self._snap("151.0.0.0", "Foo@0(int32 a);"))
             if c.kind == "mojo_method"], [])

    def test_a_method_that_never_had_one_is_unaffected(self):
        """Absent, not zero, so it compares equal to how it always was."""
        self.assertEqual(
            [c for c in diff_snapshots(self._snap("148.0.0.0", "Foo(int32 a);"),
                                       self._snap("151.0.0.0", "Foo(int32 a);"))
             if c.kind == "mojo_method"], [])


class TestTheThingsFixedWithoutBeingLocked(unittest.TestCase):
    """Six behaviours that were corrected and then not held by anything.

    Each one shipped in a commit whose message described it, which is the
    exact form of evidence this suite exists to replace. They are grouped so
    the gap is visible rather than spread across the classes they belong to.
    """

    # --- the whitespace normaliser, and the false negative it first traded for
    def test_a_reformatted_signature_is_not_a_change(self):
        from chromiumdiff.extract.web_idl import _normalize_signature as norm
        wrapped = ("Promise<ArrayBuffer> deriveBits( AlgorithmIdentifier a, "
                   "CryptoKey b, optional long? length = null)")
        inline = ("Promise<ArrayBuffer> deriveBits(AlgorithmIdentifier a, "
                  "CryptoKey b, optional long? length = null)")
        self.assertEqual(norm(wrapped), norm(inline))
        # And the return type keeps the space that separates it from the name.
        self.assertIn("> deriveBits(", norm(inline))

    def test_a_string_literal_is_left_exactly_as_written(self):
        """`"a,b"` is not `"a, b"`, and the first normaliser made them equal."""
        from chromiumdiff.extract.web_idl import _normalize_signature as norm
        self.assertNotEqual(norm('void f(optional DOMString s = "a,b")'),
                            norm('void f(optional DOMString s = "a, b")'))
        self.assertIn('"a,b"', norm('void f(optional DOMString s = "a,b")'))

    # --- the completeness latch, in both directions
    def _switch_change(self, direction):
        old = Fact(kind="switch", key="s", name="s", path="switches.cc",
                   attrs={"var": "kS"})
        if direction == "added":
            return diff_snapshots(snap("148.0.0.0", []),
                                  snap("151.0.0.0", [old]))[0]
        return diff_snapshots(snap("148.0.0.0", [old]),
                              snap("151.0.0.0", []))[0]

    FULL = {"from": {"candidates": 100, "read": 100},
            "to": {"candidates": 100, "read": 100}}

    def test_the_latch_asks_the_side_the_evidence_comes_from(self):
        """A removal is an absence from the new side; an addition from the old.

        Testing both at once discounted each for a fault on the side its
        evidence does not come from.
        """
        old_hole = Scope(self.FULL, "r", from_incomplete="2 targets missing")
        new_hole = Scope(self.FULL, "r", incomplete="2 targets missing")
        removed = self._switch_change("removed")
        added = self._switch_change("added")
        # A hole in the old side cannot have invented a removal.
        self.assertTrue(old_hole.confirms_absence("switch", REMOVED))
        self.assertFalse(new_hole.confirms_absence("switch", REMOVED))
        # ...and the mirror for an addition.
        self.assertFalse(old_hole.confirms_absence("switch", ADDED))
        self.assertTrue(new_hole.confirms_absence("switch", ADDED))
        self.assertEqual(score_change(removed, old_hole).score,
                         score_change(removed, Scope(self.FULL, "r")).score)
        self.assertEqual(score_change(added, new_hole).bucket, "new")

    def test_an_unconfirmed_addition_is_not_called_new_surface(self):
        """The label asserts it was not there before. That is the doubt."""
        scope = Scope(self.FULL, "r", from_incomplete="2 targets missing")
        finding = score_change(self._switch_change("added"), scope)
        self.assertEqual(finding.bucket, "housekeeping")
        self.assertIn("cannot show it was absent before",
                      " ".join(finding.reasons))

    def test_coverage_is_read_from_the_side_that_answers(self):
        """`share_for` looked only at the new side, whatever the direction."""
        lopsided = Scope({
            "from": {"candidates": 1000, "read": 10,
                     "by_surface": {"preference keys and switches":
                                    {"candidates": 100, "read": 1}}},
            "to": {"candidates": 1000, "read": 1000,
                   "by_surface": {"preference keys and switches":
                                  {"candidates": 100, "read": 100}}}},
            to_ref="r")
        self.assertEqual(lopsided.read_percent("switch", REMOVED), "100%")
        self.assertEqual(lopsided.read_percent("switch", ADDED), "1%")

    # --- platform_state, on a kind that only started comparing it
    def test_a_mojo_method_leaving_the_windows_build_is_a_change(self):
        """Compared on three of sixteen kinds, so this produced no row."""
        from chromiumdiff.extract import mojom
        def snap_of(ref, body):
            return Snapshot(ref=ref, facts=mojom.extract(
                f"module t;\ninterface I {{\n  {body}\n}};\n", "t.mojom"),
                meta={"target_set": "default"})
        changes = [c for c in diff_snapshots(
            snap_of("148.0.0.0", "Foo(int32 a);"),
            snap_of("151.0.0.0", "[EnableIf=is_android] Foo(int32 a);"))
            if c.kind == "mojo_method"]
        self.assertEqual(len(changes), 1)
        self.assertIn("platform_state", changes[0].deltas)
        self.assertTrue(changes[0].signals)

    # --- per-overload extended attributes, not just the runtime flag
    def test_an_extended_attribute_moving_on_one_overload_is_visible(self):
        from chromiumdiff.extract import web_idl
        from chromiumdiff.model import dedupe_facts
        def snap_of(ref, body):
            return Snapshot(ref=ref, facts=dedupe_facts(web_idl.extract(
                "interface N { %s };" % body,
                "third_party/blink/renderer/x.idl")),
                meta={"target_set": "default"})
        before = "[SecureContext] void f(long a); void f(double b);"
        after = "void f(long a); [SecureContext] void f(double b);"
        change = [c for c in diff_snapshots(snap_of("148.0.0.0", before),
                                            snap_of("151.0.0.0", after))
                  if c.kind == "idl_member"][0]
        self.assertIn("overload_traits", change.deltas)

    # --- the implicit ordinal, for fields as well as methods
    def test_a_field_moving_inside_a_stable_struct_is_a_wire_change(self):
        """607 fields shifted at M148 -> M151 and 0 were in a stable struct.

        The method case was tested and the field case was not, which is the
        half the review had to point out twice.
        """
        from chromiumdiff.extract import mojom
        def snap_of(ref, body):
            return Snapshot(ref=ref, facts=mojom.extract(
                f"module t;\n[Stable]\nstruct S {{ {body} }};\n", "t.mojom"),
                meta={"target_set": "default"})
        changes = [c for c in diff_snapshots(
            snap_of("148.0.0.0", "int32 a; int32 b;"),
            snap_of("151.0.0.0", "int32 b; int32 a;"))
            if c.kind == "mojo_field"]
        self.assertEqual(len(changes), 2)
        for change in changes:
            self.assertIn("position", change.deltas)
            self.assertIn("ipc_shape_changed", change.signals)

    def test_withdrawing_stability_is_not_a_hundred_members_moving(self):
        """The regression the full version matrix found, and I introduced.

        `position` is recorded only inside `[Stable]`, so when Chromium drops
        the annotation the attribute disappears and every field's delta reads
        `[6, None]`. Read as an ordinal move that is an ABI break each: 183
        rows at 80 points on M143 -> M147 wide, from
        `device.mojom.HidCollectionInfo` and its neighbours losing `[Stable]`
        upstream. A position is evidence only against another position.
        """
        from chromiumdiff.extract import mojom

        def snap_of(ref, header):
            return Snapshot(ref=ref, facts=mojom.extract(
                f"module t;\n{header}struct S {{ int32 a; int32 b; }};\n",
                "t.mojom"), meta={"target_set": "default"})

        changes = diff_snapshots(snap_of("148.0.0.0", "[Stable]\n"),
                                 snap_of("151.0.0.0", ""))
        # Not one row per member either. The promise belongs to the container
        # and the container says it: three files withdrawing `[Stable]` at
        # M143 -> M147 produced 32 container rows and 164 members restating
        # them, 11% of the Behaviour bucket for one upstream annotation edit.
        self.assertEqual([c.kind for c in changes], ["mojo_struct"])
        self.assertEqual(changes[0].signals, ["ipc_stability_changed"])
        self.assertEqual(score_change(changes[0]).bucket, "behaviour")

    def test_the_same_move_outside_a_stable_struct_is_not_reported(self):
        """1,110 of them at M148 -> M151. Chromium reorders freely there."""
        from chromiumdiff.extract import mojom
        def snap_of(ref, body):
            return Snapshot(ref=ref, facts=mojom.extract(
                f"module t;\nstruct S {{ {body} }};\n", "t.mojom"),
                meta={"target_set": "default"})
        self.assertEqual(
            [c for c in diff_snapshots(snap_of("148.0.0.0", "int32 a; int32 b;"),
                                       snap_of("151.0.0.0", "int32 b; int32 a;"))
             if c.kind == "mojo_field"], [])

    # --- and the permutation the earlier test claimed to be
    def test_one_event_scores_the_same_under_either_declaration_order(self):
        """The previous version compared two different events and called it a
        permutation test."""
        from chromiumdiff.extract import web_idl
        from chromiumdiff.model import dedupe_facts
        def snap_of(ref, body):
            return Snapshot(ref=ref, facts=dedupe_facts(web_idl.extract(
                "interface N { %s };" % body,
                "third_party/blink/renderer/x.idl")),
                meta={"target_set": "default"})
        scores = set()
        for order in ("void f(); void f(long a);", "void f(long a); void f();"):
            change = [c for c in diff_snapshots(snap_of("148.0.0.0", order),
                                                snap_of("151.0.0.0", "void f();"))
                      if c.kind == "idl_member"][0]
            self.assertIn("web_api_overload_removed", change.signals)
            scores.add(score_change(change).score)
        self.assertEqual(scores, {60})


class TestASurfaceCountsEveryFileThatReadsIt(unittest.TestCase):
    """The global denominator and a surface's denominator ask different things.

    One counts files, so a file two extractors read counts once. The other
    asks which files could declare that kind, so the same file belongs to
    both surfaces. Sharing one answer attributed each file to whichever rule
    claimed it first, and the pref and switch surface reported 4 of 348 where
    it reads 9 of 529 -- 378 files at M151 belong to more than one surface.
    """

    class _Tree:
        def __init__(self, paths):
            self.paths = paths

        def list_recursive(self, root):
            return [p for p in self.paths if p.startswith(root)]

    PATHS = [
        # Read by the feature extractor and by the constant extractor: it
        # declares switches and the flags that gate them.
        "base/base_switches.cc",
        "third_party/blink/renderer/core/dom/element.idl",
    ]

    def test_a_shared_file_counts_once_globally_and_once_per_surface(self):
        from chromiumdiff.targets import coverage_against, discover_candidates
        candidates, memberships = discover_candidates(self._Tree(self.PATHS))
        shared = "base/base_switches.cc"
        self.assertIn(shared, candidates)
        self.assertGreater(len(memberships[shared]), 1,
                           "expected more than one extractor to read it")
        coverage = coverage_against(candidates, [], memberships)
        # Global: one file, one candidate.
        self.assertEqual(coverage["candidates"], len(candidates))
        # Per surface: it appears under each surface that reads it.
        appearances = sum(1 for row in coverage["by_surface"].values()
                          if row["candidates"])
        self.assertGreaterEqual(appearances, len(memberships[shared]))
        self.assertGreater(
            sum(row["candidates"] for row in coverage["by_surface"].values()),
            coverage["candidates"],
            "surfaces should overlap; only the global count deduplicates")


class TestTheBoundariesThatKeepBeingCrossed(unittest.TestCase):
    """Four joins where a capability existed and the caller did not use it.

    Three times in this project the data model learned something and the
    pipeline kept doing without it: the Mojo ordinal, `platform_state`, and
    the two-sided coverage. Boundary tests are worth more here than more
    tests of the parts.
    """

    def _mojom_snapshot(self, ref, body, meta=None):
        from chromiumdiff.extract import mojom
        return Snapshot(ref=ref, facts=mojom.extract(body, "t.mojom"),
                        meta=meta or {"target_set": "default"})

    def test_the_run_hands_the_scorer_both_sides_of_the_coverage(self):
        """`Scope` held two sides while the run passed one.

        The first version of this read `cmd_run`'s source for the strings
        `"from"` and `"to"`, which appear in it for other reasons -- so
        dropping the old side from the call left the test green. It drives
        the function now: two snapshots in, and the object it returns has to
        answer the two directions differently.
        """
        from chromiumdiff.cli import scope_for

        thin = Snapshot(ref="148.0.0.0", facts=[], meta={
            "coverage": {"candidates": 100, "read": 1}})
        full = Snapshot(ref="151.0.0.0", facts=[], meta={
            "coverage": {"candidates": 100, "read": 100}})
        scope = scope_for(thin, full)
        self.assertEqual(scope.read_percent("switch", REMOVED), "100%")
        self.assertEqual(scope.read_percent("switch", ADDED), "1%")
        self.assertEqual(scope.to_ref, "151.0.0.0")
        # And the mirror, so neither side is hard-coded.
        mirrored = scope_for(full, thin)
        self.assertEqual(mirrored.read_percent("switch", REMOVED), "1%")
        self.assertEqual(mirrored.read_percent("switch", ADDED), "100%")

    def test_an_unguarded_declaration_equals_one_guarded_onto_windows(self):
        """Same answer, one representation each; comparing the form said
        "may no longer be in the binary we ship" when nothing moved."""
        plain = "module t;\nstruct S { int32 a; };\n"
        guarded = "module t;\n[EnableIf=is_win]\nstruct S { int32 a; };\n"
        self.assertEqual(
            [c.key for c in diff_snapshots(self._mojom_snapshot("1", plain),
                                           self._mojom_snapshot("2", guarded))],
            [])
        # ...and a guard that does exclude us is still a change.
        android = "module t;\n[EnableIf=is_android]\nstruct S { int32 a; };\n"
        self.assertTrue(diff_snapshots(self._mojom_snapshot("1", plain),
                                       self._mojom_snapshot("2", android)))

    def test_a_container_edit_produces_one_row_not_one_per_member(self):
        """Moving a guard off a struct produced three rows for one edit, and
        withdrawing `[Stable]` produced 164 across three files."""
        moved_before = ("module t;\nstruct S {\n  [EnableIf=is_win] int32 a;\n"
                        "  int32 b;\n};\n")
        moved_after = ("module t;\n[EnableIf=is_win]\nstruct S {\n"
                       "  int32 a;\n  int32 b;\n};\n")
        rows = diff_snapshots(self._mojom_snapshot("1", moved_before),
                              self._mojom_snapshot("2", moved_after))
        self.assertEqual([c.kind for c in rows], ["mojo_field"],
                         "only the field whose own attribute moved")

        stable_before = "module t;\n[Stable]\nstruct S { int32 a; int32 b; };\n"
        stable_after = "module t;\nstruct S { int32 a; int32 b; };\n"
        rows = diff_snapshots(self._mojom_snapshot("1", stable_before),
                              self._mojom_snapshot("2", stable_after))
        self.assertEqual([c.kind for c in rows], ["mojo_struct"])
        self.assertEqual(rows[0].signals, ["ipc_stability_changed"])

    def test_both_renderers_show_every_location_of_a_five_way_overload(self):
        """`report.json` carried all of them and the renderers cut at three,
        which dropped the line an overload had been removed from."""
        from chromiumdiff.extract import web_idl
        from chromiumdiff.model import Report, dedupe_facts
        from chromiumdiff.report import html as html_report
        from chromiumdiff.report import markdown as md_report

        def side(body):
            return dedupe_facts(web_idl.extract(
                "interface N {\n  %s\n};" % body,
                "third_party/blink/renderer/x.idl"))
        wide = "\n  ".join(f"void f({'long a, ' * n}long z);" for n in range(5))
        changes = diff_snapshots(
            Snapshot(ref="1", facts=side(wide), meta={"target_set": "default"}),
            Snapshot(ref="2", facts=side(wide.split("\n  ", 1)[1]),
                     meta={"target_set": "default"}))
        findings = score_all([c for c in changes if c.kind == "idl_member"])
        locations = findings[0].change.locations
        # The name says five. Checking the first four was the same fault the
        # renderers had: stopping before the one that mattered.
        self.assertEqual(len(locations), 5)
        report = Report(from_ref="1", to_ref="2", findings=findings,
                        summary=summarize_findings(findings))
        rendered = md_report.render(report)
        payload = html_report.render(report)
        for where in locations:
            self.assertIn(where, rendered, f"markdown dropped {where}")
            self.assertIn(where, payload, f"html dropped {where}")


class TestPairedAttributesStayScoped(unittest.TestCase):
    """`PAIRED_ATTRS` is a rule in the generic diff, so its reach is checked.

    `position` means "lexical index inside a `[Stable]` mojom declaration".
    Skipping its delta when one side lacks it is right for that meaning and
    would silently hide a signal for any other kind that later records an
    attribute under the same name.
    """

    def test_only_the_kinds_that_mean_it_compare_a_position(self):
        from chromiumdiff.diff import MEANINGFUL_ATTRS, PAIRED_ATTRS
        for attr in PAIRED_ATTRS:
            owners = {kind for kind, attrs in MEANINGFUL_ATTRS.items()
                      if attr in attrs}
            self.assertEqual(
                owners, {"mojo_method", "mojo_field"},
                f"{attr!r} is skipped when one side lacks it; a new kind "
                f"comparing it under a different meaning would lose rows")

    def test_a_paired_attribute_still_speaks_when_both_sides_have_it(self):
        from chromiumdiff.extract import mojom

        def snap_of(ref, body):
            return Snapshot(ref=ref, facts=mojom.extract(
                f"module t;\n[Stable]\nstruct S {{ {body} }};\n", "t.mojom"),
                meta={"target_set": "default"})
        changes = [c for c in diff_snapshots(snap_of("1", "int32 a; int32 b;"),
                                             snap_of("2", "int32 b; int32 a;"))
                   if c.kind == "mojo_field"]
        self.assertEqual(len(changes), 2)
        for change in changes:
            self.assertIn("position", change.deltas)


class TestTheCompletenessMatrix(unittest.TestCase):
    """Every hole against every direction, rather than the four I checked.

    A hole is a target the source did not have or a file that would not
    parse, on either side. A change's evidence is an absence from exactly one
    side, so sixteen combinations reduce to one rule -- and the first version
    of this got it backwards in both directions at once, testing both sides
    for every change.
    """

    FULL = {"from": {"candidates": 100, "read": 100},
            "to": {"candidates": 100, "read": 100}}

    def _scopes(self):
        return {
            "no hole": Scope(self.FULL, "r"),
            "old hole": Scope(self.FULL, "r", from_incomplete="2 missing"),
            "new hole": Scope(self.FULL, "r", incomplete="2 missing"),
            "both": Scope(self.FULL, "r", from_incomplete="2 missing",
                          incomplete="2 missing"),
        }

    def _whole(self, direction):
        fact = Fact(kind="switch", key="s", name="s", path="switches.cc",
                    attrs={"var": "kS"})
        sides = ([], [fact]) if direction == ADDED else ([fact], [])
        return diff_snapshots(snap("148.0.0.0", sides[0]),
                              snap("151.0.0.0", sides[1]))[0]

    def _variant(self, direction):
        from chromiumdiff.extract import web_idl
        from chromiumdiff.model import dedupe_facts

        def side(body):
            return dedupe_facts(web_idl.extract(
                "interface N { %s };" % body,
                "third_party/blink/renderer/x.idl"))
        one = "void f(); void f(long a);"
        two = one + " void f(long a, long b);"
        before, after = (one, two) if direction == ADDED else (two, one)
        return [c for c in diff_snapshots(
            Snapshot(ref="148.0.0.0", facts=side(before),
                     meta={"target_set": "default"}),
            Snapshot(ref="151.0.0.0", facts=side(after),
                     meta={"target_set": "default"}))
            if c.kind == "idl_member"][0]

    # Which side each kind of evidence rests on. A variant removal is an
    # absence from the new side even though the change itself is MODIFIED.
    EXPECTED_HOLE = {
        "whole added": "old hole",
        "whole removed": "new hole",
        "variant added": "old hole",
        "variant removed": "new hole",
    }

    def test_each_evidence_shape_is_discounted_by_exactly_one_hole(self):
        cases = {
            "whole added": self._whole(ADDED),
            "whole removed": self._whole(REMOVED),
            "variant added": self._variant(ADDED),
            "variant removed": self._variant(REMOVED),
        }
        for name, change in cases.items():
            clean = score_change(change, self._scopes()["no hole"]).score
            for hole, scope in self._scopes().items():
                score = score_change(change, scope).score
                discounted = score < clean
                should = hole in ("both", self.EXPECTED_HOLE[name])
                self.assertEqual(
                    discounted, should,
                    f"{name} under {hole}: score {score} against {clean}")

    def test_a_variant_addition_is_not_discounted_by_a_new_side_hole(self):
        """Its evidence is that the old side did not have it.

        The narrow case worth naming on its own: an overload appearing was
        being judged by a fault in the snapshot it appears *in*.
        """
        change = self._variant(ADDED)
        clean = score_change(change, self._scopes()["no hole"]).score
        self.assertEqual(
            score_change(change, self._scopes()["new hole"]).score, clean)

    def test_a_removal_survives_a_hole_in_the_side_it_was_present_on(self):
        change = self._whole(REMOVED)
        clean = score_change(change, self._scopes()["no hole"]).score
        self.assertEqual(
            score_change(change, self._scopes()["old hole"]).score, clean)


class TestTheReportIsSafeToOpen(unittest.TestCase):
    """A report is a file people forward to each other and open in a browser.

    Chromium's own source is not the threat here; `--local-src` and a
    hand-edited `report.json` are, and the tool accepts both.
    """

    def test_a_payload_cannot_end_its_own_script_tag(self):
        import json
        """`json.dumps` escapes nothing an HTML parser cares about.

        The parser ends the script at the first `</script>` in the byte
        stream, inside a string literal or not, and escaping at render time
        cannot help because the break already happened when the document was
        parsed.
        """
        from chromiumdiff.report.html import _embed
        out = _embed({"name": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script>", out)
        self.assertNotIn("<script", out)
        # And still valid JSON for the browser to parse back.
        self.assertEqual(json.loads(out)["name"],
                         "</script><script>alert(1)</script>")

    def test_only_http_links_are_clickable(self):
        """Escaping keeps the attribute intact; it does not make a scheme safe.

        `javascript:alert(1)` survives every entity encoding and runs on
        click, and the value arrives from chromestatus over the network.
        """
        from chromiumdiff.report.html import _http_url
        self.assertTrue(_http_url("https://spec.example/x"))
        self.assertTrue(_http_url("http://spec.example/x"))
        self.assertFalse(_http_url("javascript:alert(1)"))
        self.assertFalse(_http_url("  JavaScript:alert(1)"))
        self.assertFalse(_http_url("data:text/html,x"))
        self.assertFalse(_http_url(None))

    def test_a_line_separator_cannot_break_the_literal(self):
        """U+2028 is valid JSON and illegal in a JS string literal."""
        from chromiumdiff.report.html import _embed
        self.assertNotIn("\u2028", _embed({"a": "x\u2028y"}))

    def test_a_ref_cannot_climb_out_of_the_cache(self):
        """Both cache paths are built from the ref, and both used to allow it.

        `/` and `:` were replaced and `\\` was not -- a separator on the
        platform this tool is written for -- so `..\\..\\victim` wrote outside
        the cache, and `tree_path` is where a whole source tree is unpacked.
        """
        from chromiumdiff.acquire import safe_name as _safe_name
        for hostile in ("..\\..\\victim", "../../etc/passwd", "a/b", "a:b",
                        "..", "....//"):
            safe = _safe_name(hostile)
            self.assertNotIn("/", safe)
            self.assertNotIn("\\", safe)
            self.assertNotIn("..", safe)
        # And an ordinary ref still produces the name the cache already uses.
        self.assertEqual(_safe_name("refs/tags/151.0.7922.138"),
                         "refs_tags_151.0.7922.138")

    def test_check_does_not_print_proxy_credentials(self):
        """`check` output is the first thing pasted into a ticket."""
        from chromiumdiff.cli import _redact_proxy
        self.assertEqual(_redact_proxy("http://user:pw@proxy.corp:8080"),
                         "http://<redacted>@proxy.corp:8080")
        self.assertEqual(_redact_proxy("http://proxy.corp:8080"),
                         "http://proxy.corp:8080")


class TestOneEligibilityPolicy(unittest.TestCase):
    """Discovery and extraction cannot disagree about what is product code.

    Sharing the extractor predicate was not enough while each pipeline wrapped
    it in its own exclusions. Measured at M151, they disagreed both ways:
    `content/web_test/common/mojo_echo.mojom` counted as a candidate nothing
    would ever read, and `cc/mojom/hit_test_opaqueness.mojom` produced facts
    while a substring rule kept it out of the denominator -- hit testing is a
    product concept, not test code.
    """

    CASES = {
        "cc/mojom/hit_test_opaqueness.mojom": True,
        "third_party/blink/renderer/core/dom/element.idl": True,
        "content/public/common/content_features.cc": True,
        "content/web_test/common/mojo_echo.mojom": False,
        "services/network/public/mojom/network_service_test.mojom": False,
        "media/mojo/mojom/video_decoder_test_service.mojom": False,
        "mojo/public/tools/fuzzers/fuzz.mojom": False,
        "chrome/updater/x_features.cc": False,
    }

    def test_both_pipelines_give_the_same_answer(self):
        from chromiumdiff.extract import _skip
        from chromiumdiff.targets import could_declare
        for path, keep in self.CASES.items():
            self.assertEqual(not _skip(path), keep, f"extraction: {path}")
            self.assertEqual(could_declare(path) is not None, keep,
                             f"discovery: {path}")

    def test_a_product_word_containing_test_is_not_test_code(self):
        """The rule is a suffix before the extension, not a substring."""
        from chromiumdiff.eligibility import skip_reason
        self.assertEqual(skip_reason("cc/mojom/hit_test_opaqueness.mojom"), "")
        self.assertEqual(skip_reason("ui/latency_test_helper.cc"), "")
        self.assertTrue(skip_reason("ui/widget_test.cc"))
        self.assertTrue(skip_reason("ui/widget_test_service.mojom"))


class TestRemovalConfidenceIsPerSurface(unittest.TestCase):
    """A removal is only as believable as the read of its own surface.

    One scalar for the whole run made a vanished web API -- seen against a
    99.8% read of the IDL -- exactly as doubtful as a vanished preference seen
    against 1.7% of the pref files. On the default set that cost 45 real web
    API removals 15 points each.
    """

    COVERAGE = {"to": {
        "candidates": 8366, "read": 3677,
        "by_surface": {
            "web API definitions": {"candidates": 2170, "read": 2166},
            "preference keys and switches": {"candidates": 348, "read": 4},
        }}}

    def _scope(self):
        return Scope(self.COVERAGE, to_ref="refs/tags/151.0.7922.138")

    def test_a_well_read_surface_confirms_its_own_absences(self):
        scope = self._scope()
        self.assertTrue(scope.confirms_absence("idl_member"))
        self.assertFalse(scope.confirms_absence("pref"))

    def test_the_sentence_quotes_the_surface_not_the_run(self):
        scope = self._scope()
        self.assertEqual(scope.read_percent("idl_member"), "100%")
        self.assertEqual(scope.read_percent("pref"), "1%")

    def test_a_kind_with_no_row_falls_back_to_the_whole_read(self):
        """Never a guess: an unmeasured surface uses the figure there is."""
        self.assertEqual(self._scope().read_percent("mojo_method"), "44%")

    def test_a_web_api_removal_keeps_its_full_severity(self):
        api = Fact(kind="idl_interface", key="Foo", name="Foo",
                   path="third_party/blink/renderer/core/foo.idl",
                   attrs={"idl_kind": "interface"})
        change = diff_snapshots(snap("148.0.0.0", [api]),
                                snap("151.0.0.0", []), platform="windows")[0]
        self.assertEqual(score_change(change, self._scope()).score, 70)


class TestAnOverloadSetIsPartOfTheContract(unittest.TestCase):
    """Web IDL overloads a member by argument list; dedupe kept one.

    So `Navigator.install` gaining `install(InstallParams)` and
    `Document.parseHTMLUnsafe` losing `(html, SetHTMLUnsafeOptions)` both
    produced no row at all: the declaration deduplication kept was unchanged
    in each case. Measured M148 -> M151: 121 members carry more than one
    signature, 56 had that set change, and these are the 2 the diff could not
    see -- one of them a web API disappearing.
    """

    def _snap(self, ref, body):
        from chromiumdiff.extract import web_idl
        from chromiumdiff.model import dedupe_facts
        return Snapshot(ref=ref, facts=dedupe_facts(web_idl.extract(
            "interface N { %s };" % body,
            "third_party/blink/renderer/x.idl")),
            meta={"target_set": "default"})

    ONE = "Promise<R> install(); Promise<R> install(USVString u);"
    TWO = ONE + " Promise<R> install(P p);"

    def test_a_member_carries_every_signature_it_has(self):
        facts = {f.key: f for f in self._snap("151.0.0.0", self.ONE).facts}
        self.assertEqual(facts["N.install"].attrs["signatures"],
                         ["Promise<R> install()",
                          "Promise<R> install(USVString u)"])

    def test_a_member_with_one_signature_carries_no_list(self):
        """Recorded only when there is more than one, so nothing else moves."""
        facts = {f.key: f for f in
                 self._snap("151.0.0.0", "Promise<R> install();").facts}
        self.assertNotIn("signatures", facts["N.install"].attrs)

    def test_losing_an_overload_is_breaking(self):
        change = [c for c in diff_snapshots(self._snap("148.0.0.0", self.TWO),
                                            self._snap("151.0.0.0", self.ONE))
                  if c.kind == "idl_member"][0]
        self.assertEqual(change.signals, ["web_api_overload_removed"])
        finding = score_change(change)
        self.assertEqual(finding.score, 60)
        self.assertEqual(finding.bucket, "breaking")

    def test_filling_a_gap_below_the_existing_counts_is_new_surface(self):
        """A call at that count used to throw, so no call changes target."""
        narrow = "Promise<R> install(USVString u);"
        change = [c for c in diff_snapshots(
            self._snap("148.0.0.0", narrow),
            self._snap("151.0.0.0", "Promise<R> install(); " + narrow))
            if c.kind == "idl_member"][0]
        self.assertEqual(change.signals, ["web_api_overload_added"])
        self.assertEqual(score_change(change).bucket, "new")

    def test_a_longer_overload_captures_calls_that_were_being_clamped(self):
        """A second version of the same wrong claim, caught the same way.

        Web IDL serves a call with more arguments than any overload declares
        by using the longest one and dropping the extras. Adding an overload
        longer than every existing one therefore takes those calls, without
        removing anything and without touching the call site.
        """
        wider = self.ONE + " Promise<R> install(USVString u, USVString v);"
        change = [c for c in diff_snapshots(self._snap("148.0.0.0", self.ONE),
                                            self._snap("151.0.0.0", wider))
                  if c.kind == "idl_member"][0]
        self.assertEqual(change.signals, ["web_api_overload_shadowed"])

    def test_an_optional_argument_serves_more_than_one_count(self):
        """Declared parameter count is not the effective overload set."""
        from chromiumdiff.diff import _arity_range
        self.assertEqual(_arity_range("void f(optional long a)"), (0, 1))
        self.assertEqual(_arity_range("void f(long... a)"), (0, None))
        self.assertEqual(_arity_range("void f(long a, optional long b)"), (1, 2))

    def test_a_first_second_overload_is_still_judged_against_the_first(self):
        """The old side has no `signatures` list; it has one `signature`.

        Without falling back to it, every member growing from one declaration
        to two read as reaching an argument count nothing had, and scored 25
        even when the new overload took the same count as the old one.
        """
        change = [c for c in diff_snapshots(
            self._snap("148.0.0.0", "void f(DOMString s);"),
            self._snap("151.0.0.0", "void f(DOMString s); void f(Params p);"))
            if c.kind == "idl_member"][0]
        self.assertEqual(change.signals, ["web_api_overload_shadowed"])

    def test_gaining_an_overload_at_an_existing_arity_can_take_a_call(self):
        """The first version of this claimed adding one breaks nothing.

        Web IDL resolves by argument count first and type second, so a new
        overload at a count something already had can capture a call that used
        to reach the other one. `Navigator.install` is exactly that: M151 adds
        `install(InstallParams)` beside `install(USVString install_url)`, both
        taking one argument, so `navigator.install(someObject)` stops
        stringifying. The site is unedited and nothing was removed.
        """
        change = [c for c in diff_snapshots(self._snap("148.0.0.0", self.ONE),
                                            self._snap("151.0.0.0", self.TWO))
                  if c.kind == "idl_member"][0]
        self.assertEqual(change.signals, ["web_api_overload_shadowed"])
        self.assertEqual(score_change(change).bucket, "behaviour")

    def test_a_gate_moving_on_one_overload_is_visible(self):
        """The variant set kept signatures and dropped the gates.

        So `[RuntimeEnabled]` moving on one overload of a member showed up
        only when deduplication happened to keep that declaration. 12 of the
        121 overload groups at M151 have overloads that disagree about their
        gate; on M148 -> M151 none of them moved without something else
        reporting it, so this closes the mechanism rather than fixing a
        visible wrong answer.
        """
        before = ("[RuntimeEnabled=A] void f(long a); "
                  "[RuntimeEnabled=B] void f(double b);")
        after = ("[RuntimeEnabled=A] void f(long a); "
                 "[RuntimeEnabled=C] void f(double b);")
        change = [c for c in diff_snapshots(self._snap("148.0.0.0", before),
                                            self._snap("151.0.0.0", after))
                  if c.kind == "idl_member"][0]
        self.assertIn("overload_traits", change.deltas)
        # The same event the single-declaration case already names, so it
        # carries that name rather than a signal of its own.
        self.assertEqual(change.signals, ["web_api_exposure_changed"])
        self.assertEqual(score_change(change).bucket, "behaviour")

    def test_a_gate_change_is_not_read_as_an_overload_disappearing(self):
        """Which is what folding the gate into the identity would have done."""
        before = ("[RuntimeEnabled=A] void f(long a); "
                  "[RuntimeEnabled=B] void f(double b);")
        after = ("[RuntimeEnabled=A] void f(long a); "
                 "[RuntimeEnabled=C] void f(double b);")
        change = [c for c in diff_snapshots(self._snap("148.0.0.0", before),
                                            self._snap("151.0.0.0", after))
                  if c.kind == "idl_member"][0]
        self.assertNotIn("web_api_overload_removed", change.signals)
        self.assertNotIn("signatures", change.deltas)

    def test_overloads_that_agree_about_their_gate_carry_no_list(self):
        """Recorded only where it discriminates: 12 groups of the 121."""
        facts = {f.key: f for f in
                 self._snap("151.0.0.0", "void f(long a); void f(double b);").facts}
        self.assertNotIn("overload_traits", facts["N.f"].attrs)
        self.assertIn("signatures", facts["N.f"].attrs)

    def test_a_row_points_at_every_overload_it_is_about(self):
        """The report cited the surviving declaration's line for the group.

        Recorded and shown, and deliberately not compared: a group's line
        numbers move whenever anything above them does, and comparing them
        would turn ordinary churn into rows. What was missing was landing on
        the right declaration, not being told a line moved.
        """
        from chromiumdiff.diff import MEANINGFUL_ATTRS
        change = [c for c in diff_snapshots(
            self._snap("148.0.0.0", "void f();\n  void f(long a);"),
            self._snap("151.0.0.0", "void f();"))
            if c.kind == "idl_member"][0]
        self.assertEqual(len(change.locations), 2)
        self.assertNotIn("overload_locations",
                         MEANINGFUL_ATTRS["idl_member"])

    def test_the_verdict_does_not_depend_on_which_copy_survived(self):
        """One event, one score, whatever deduplication happened to keep.

        Hanging the overload signal on an `elif` made the same removal score
        60 when the surviving declaration was unchanged and 50 when it was
        not -- a fact about declaration order, not about the API.
        """
        kept_same = diff_snapshots(
            self._snap("148.0.0.0", "void f(); void f(long a);"),
            self._snap("151.0.0.0", "void f();"))
        kept_moved = diff_snapshots(
            self._snap("148.0.0.0", "void f(long a); void f(double b);"),
            self._snap("151.0.0.0", "void f(short a);"))
        for changes in (kept_same, kept_moved):
            change = [c for c in changes if c.kind == "idl_member"][0]
            self.assertIn("web_api_overload_removed", change.signals)
            self.assertEqual(score_change(change).score, 60)


class TestAbsenceNeedsMoreThanCoverage(unittest.TestCase):
    """A missing target and an unparsable file both look like a removal.

    Coverage measures what was in scope, not what came back, so neither shows
    up in it. Both are zero on every version measured so far; the latch is
    here so the first run where they are not does not quietly confirm a
    removal it cannot see.
    """

    FULL = {"to": {"candidates": 100, "read": 100}}

    def test_a_complete_run_confirms_an_absence(self):
        self.assertTrue(Scope(self.FULL, "refs/tags/151").confirms_absence("pref"))

    def test_a_missing_target_withholds_confirmation(self):
        scope = Scope(self.FULL, "refs/tags/151",
                      incomplete="2 target(s) the source did not have")
        self.assertFalse(scope.confirms_absence("pref"))

    def test_the_reason_says_which_it_was(self):
        from chromiumdiff.model import Fact
        scope = Scope(self.FULL, "refs/tags/151",
                      incomplete="1 file(s) that would not parse")
        fact = Fact(kind="pref", key="a.b", name="a.b", path="pref_names.h",
                    attrs={"var": "kAB"})
        change = diff_snapshots(snap("148.0.0.0", [fact]),
                                snap("151.0.0.0", []), platform="windows")[0]
        reasons = " ".join(score_change(change, scope).reasons)
        self.assertIn("would not parse", reasons)
        self.assertNotIn("of that surface", reasons)

    def test_the_reason_is_built_from_the_snapshot(self):
        from chromiumdiff.cli import _incomplete_reason
        clean = Snapshot(ref="r", facts=[], meta={"missing_targets": [],
                                                  "extract_stats": {"_errors": 0}})
        holed = Snapshot(ref="r", facts=[], meta={"missing_targets": ["a", "b"],
                                                  "extract_stats": {"_errors": 3}})
        self.assertEqual(_incomplete_reason(clean), "")
        self.assertEqual(_incomplete_reason(holed),
                         "2 target(s) the source did not have and "
                         "3 file(s) that would not parse")


class TestTheCoverageDenominatorAsksTheExtractors(unittest.TestCase):
    """There is no second list of what could declare, and that is the point.

    It has been wrong twice, the same way both times. Most recently it counted
    two filename conventions while the extractors grew to read `.mojom`,
    `.idl` and the WebUI templates, so `wide` reported 1,164 of 1,164 -- 100%
    -- while 3,798 files carrying 72% of a report's facts were not counted.
    """

    def test_every_extractor_widens_the_denominator(self):
        from chromiumdiff.extract import REGISTRY
        from chromiumdiff.targets import could_declare
        samples = {
            "base_features": "content/public/common/content_features.cc",
            "web_idl": "third_party/blink/renderer/core/dom/element.idl",
            "mojom": "third_party/blink/public/mojom/frame/frame.mojom",
        }
        for name, path in samples.items():
            self.assertIsNotNone(could_declare(path), f"{name}: {path}")
        # A file no extractor reads is still not a candidate.
        self.assertIsNone(could_declare("chrome/browser/browser.cc"))

    def test_the_denominator_and_the_extractors_cannot_disagree(self):
        """The rules *are* the extractor predicates, not a copy of them."""
        from chromiumdiff.extract import REGISTRY
        from chromiumdiff.targets import _discovery_rules
        rules = _discovery_rules()
        self.assertEqual(len(rules), len(REGISTRY))
        for rule, (_, applies, _fn) in zip(rules, REGISTRY):
            self.assertIs(rule.applies, applies)


class TestNoRowPrintsTheSameArrowTwice(unittest.TestCase):
    """The `What` cell says what moved; the line under it must not repeat it.

    Two truncations sit between the prose and the payload's copy of the same
    delta -- 90 characters into `deltas`, 34 out of `_moved` -- and `describe`
    applies neither. So the dedupe compared two strings that said the same
    thing and did not match, and the row printed both: a Mojo field whose type
    went from `map<mojo_base.mojom.String16, ManifestLocalizedTextObject>` to
    `map<Locale, ManifestLocalizedTextObject>?` showed that, and then showed
    its own truncation underneath.

    The kinds that gained the most from this are the ones with long values,
    which is why it surfaced when the Mojo data types arrived.
    """

    def _row(self, kind, key, attrs_before, attrs_after, deltas):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report
        change = Change(change_type="modified", kind=kind, key=key,
                        name=key.split(".")[-1], before=attrs_before,
                        after=attrs_after, deltas=deltas)
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=change, score=80)])
        return html_report._to_rows(report, "windows")[0]

    def test_a_long_type_change_is_not_shown_twice(self):
        long_old = "map<mojo_base.mojom.String16, ManifestLocalizedTextObject>"
        long_new = "map<Locale, ManifestLocalizedTextObject>?"
        row = self._row("mojo_field", "blink.mojom.Manifest.description_localized",
                        {"type": long_old}, {"type": long_new},
                        {"type": [long_old, long_new]})
        self.assertIn(long_new, row["what"])
        self.assertNotIn("moved", row)

    def test_a_short_type_change_is_not_shown_twice_either(self):
        row = self._row("mojo_field", "blink.mojom.IDBValue.bits",
                        {"type": "array<uint8>"},
                        {"type": "mojo_base.mojom.BigBuffer"},
                        {"type": ["array<uint8>", "mojo_base.mojom.BigBuffer"]})
        self.assertNotIn("moved", row)

    def test_a_delta_the_prose_does_not_carry_still_shows(self):
        """The line is not decoration -- a Mojo method's signature is only
        there, because `describe` prints the call and not its parameters."""
        row = self._row("mojo_method", "blink.mojom.AIManager.CreateWriter",
                        {"signature": "CreateWriter(int32 a)"},
                        {"signature": "CreateWriter(string a)"},
                        {"signature": ["CreateWriter(int32 a)",
                                       "CreateWriter(string a)"]})
        self.assertTrue(row.get("moved"))


class TestEveryKindIsSaidInWords(unittest.TestCase):
    """No fact kind may reach the report as a bare identifier.

    `wording.py` exists because `blink.mojom.IDBValue.bits` is precise and tells
    a reader nothing, and its `describe` ends in `return name` for anything it
    has no branch for. That fallback is silent: the row renders, it just renders
    as the identifier the module was written to replace.

    Three kinds arrived that way -- `mojo_struct`, `mojo_field` and `mojo_enum`
    were added to the model, the extractor, the comparison and both severity
    tables, and `describe` was never told about them, so every one of the 3,076
    field facts at M151 would have printed its own key back.
    """

    def _change(self, kind):
        from chromiumdiff.model import Change
        # Only the attributes every kind of that shape really carries, so the
        # test fails when a branch is missing rather than when it is thin.
        attrs = {
            "mojo_struct": {"mojo_kind": "struct", "field_count": 3},
            "mojo_field": {"struct": "a.B", "type": "int32"},
            "mojo_enum": {"values": ["kA", "kB"]},
            "webui_control": {"control": "cr-toggle", "label": "x"},
            "webui_route": {"route": "/a"},
            "webui_gate": {"features": ["kA"]},
            "idl_member": {"member_type": "attribute"},
            "idl_interface": {"idl_kind": "interface"},
            "mojo_interface": {"method_count": 2},
            "flag_entry": {"expiry_milestone": 155},
            "feature_param": {"feature": "Owner"},
            "base_feature": {"platform_state": {"windows": "enabled"}},
            "blink_runtime_feature": {"status": "stable"},
        }.get(kind, {})
        return Change(change_type="modified", kind=kind, key="a.B.c",
                      name="c", after=attrs)

    def test_every_kind_describes_itself_as_more_than_its_name(self):
        from chromiumdiff.model import ALL_KINDS
        from chromiumdiff.report import wording

        bare = []
        for kind in ALL_KINDS:
            change = self._change(kind)
            said = wording.describe(change)
            if said in (change.name, change.key):
                bare.append(kind)
        self.assertEqual(bare, [], "kinds that reach the report as an identifier")

    def test_every_kind_has_a_word_for_what_it_is(self):
        from chromiumdiff.model import ALL_KINDS
        from chromiumdiff.report.wording import KIND_WORDS
        self.assertEqual(sorted(set(ALL_KINDS) - set(KIND_WORDS)), [])


class TestAChainReadsInTheOrderItHappened(unittest.TestCase):
    """`date` is a day, and a revert and its reland land on the same one.

    Measured on `AutofillImprovePhoneFieldParser` of a real M148 -> M151 run:
    "Enable" on 05-21, then "Reland" and "Revert" both on 05-22, printed in
    that order. Read forward that says the flag was enabled, relanded, and
    then reverted -- it ended up off. It ended up on. The list was ordered by
    a key that cannot tell two CLs on one day apart, so it kept whatever order
    the search returned.

    Gerrit numbers a change when it is uploaded, and a revert is uploaded
    after the thing it reverts and a reland after the revert, so the number
    orders the day the date cannot.
    """

    @staticmethod
    def _cl(number, at, subject, match="declares"):
        return {"number": number, "at": at, "date": at[:10],
                "subject": subject, "match": match, "bugs": []}

    # The real chain, with the numbers Gerrit really gave it: the revert was
    # created after the enable and still carries the lower number, so a
    # tie-break on the number would be reading noise.
    ENABLE = (7867911, "2026-05-21 20:33:53.000000000", "Enable AutofillImprove")
    REVERT = (7867879, "2026-05-22 04:01:52.000000000",
              'Revert "Enable AutofillImprove"')
    RELAND = (7870889, "2026-05-22 08:06:11.000000000",
              'Reland "Enable AutofillImprove"')

    def _order(self, hits):
        from chromiumdiff.enrich import gerrit
        return [h["subject"] for h in gerrit._prune(hits)]

    def test_a_reland_never_prints_above_the_revert_it_undid(self):
        # Shuffled on input, because the defect was that input order survived.
        hits = [self._cl(*self.RELAND), self._cl(*self.REVERT),
                self._cl(*self.ENABLE)]
        self.assertEqual(self._order(hits),
                         [self.ENABLE[2], self.REVERT[2], self.RELAND[2]])

    def test_the_crowded_history_orders_the_same_way(self):
        """The branch that reverses itself has to reverse a settled order."""
        from chromiumdiff.enrich import gerrit

        extra = [self._cl(7860000 + i, f"2026-05-20 0{i}:00:00.000000000",
                          f"earlier {i}") for i in range(gerrit.DECL_MAX)]
        hits = [self._cl(*self.RELAND), self._cl(*self.REVERT)] + extra
        out = self._order(hits)
        self.assertLess(out.index(self.REVERT[2]), out.index(self.RELAND[2]))

    # The inversion the real chain proves, put on one day -- which is the
    # shape a day-only key cannot order at all and the number orders backwards.
    FIRST = (7867911, "2026-05-22 04:01:52.000000000", "landed first")
    SECOND = (7867879, "2026-05-22 08:06:11.000000000", "landed second")

    def test_a_lower_numbered_cl_can_be_the_later_one(self):
        """Neither the day nor the number can order this pair; the stamp can.

        Gerrit does not number changes in the order they are created, and the
        real chain shows it: the revert was created after the enable and
        carries 7867879 against 7867911. Two such CLs landing on one day is
        the case both weaker keys get wrong -- the day has nothing to compare,
        and the number compares the wrong thing.
        """
        self.assertLess(self.SECOND[0], self.FIRST[0])
        for order in ([self.FIRST, self.SECOND], [self.SECOND, self.FIRST]):
            self.assertEqual(self._order([self._cl(*c) for c in order]),
                             [self.FIRST[2], self.SECOND[2]])

    def test_an_issue_history_is_ordered_the_same_way(self):
        """It builds its own rows rather than going through `_compact`, so it
        is the one list that can quietly keep ordering by the day."""
        from chromiumdiff.enrich import gerrit

        rows = [{"_number": 2, "subject": "second",
                 "submitted": "2026-05-22 08:06:11.000000000"},
                {"_number": 1, "subject": "first",
                 "submitted": "2026-05-22 04:01:52.000000000"}]
        real = gerrit._get_json
        gerrit._get_json = lambda *a, **k: [dict(r) for r in rows]
        try:
            out = gerrit.issue_history("500975618", cache_dir="")
        finally:
            gerrit._get_json = real
        self.assertEqual([c["subject"] for c in out], ["second", "first"])
        self.assertEqual(out[0]["at"], "2026-05-22 08:06:11.000000000")

    def test_a_compacted_cl_keeps_the_stamp_it_is_ordered_by(self):
        """`date` is the stamp truncated for a reader, derived once. Dropping
        the stamp leaves every list ordered by a day again."""
        from chromiumdiff.enrich import gerrit

        out = gerrit._compact(
            {"_number": 1, "subject": "s",
             "submitted": "2026-05-22 08:06:11.000000000"}, "exact")
        self.assertEqual(out["at"], "2026-05-22 08:06:11.000000000")
        self.assertEqual(out["date"], "2026-05-22")

    def test_the_newest_of_a_day_is_the_one_a_cap_keeps(self):
        """Selection is newest-first, so the tie-break has to run that way too
        -- a cap that drops the reland and keeps the revert reports the
        opposite of the state the report found."""
        from chromiumdiff.enrich import gerrit

        hits = ([self._cl(*self.RELAND), self._cl(*self.REVERT)]
                + [self._cl(7800000 + i, f"2026-05-01 0{i % 10}:00:00.000000000",
                            f"old {i}") for i in range(gerrit.KEEP_MAX)])
        self.assertIn(self.RELAND[2], self._order(hits))


class TestTheFiguresArtifactCarriesTheProvenanceStage(unittest.TestCase):
    """Every figure this stage produces moved when the window was corrected.

    Each one was then re-measured by hand, twice, because the first sweep
    looked only for flags and command names and prose is where they live.
    `chromiumdiff figures` is the answer the project already has for that, and
    the stage was not in it.
    """

    def _report(self, findings):
        from chromiumdiff.model import Change, Finding, Report
        return Report(from_ref="a", to_ref="b", summary={}, meta={},
                      findings=findings)

    def _finding(self, key, changes, issues=None):
        from chromiumdiff.model import Change, Finding
        block = {"changes": changes}
        if issues is not None:
            block["issues"] = issues
        return Finding(
            change=Change(change_type="modified", kind="base_feature",
                          key=key, name=key), score=50,
            enrichment={"gerrit": block})

    def test_it_counts_what_the_documents_quote(self):
        from chromiumdiff.cli import measured_figures

        rows = [
            self._finding("A", [{"match": "exact", "number": 1,
                                 "bugs": [{"id": "111111"}]},
                                {"match": "declares", "number": 2, "bugs": []}]),
            # Leads only: named by nothing, and counted apart because a run
            # must not report itself as having explained more than it did.
            self._finding("B", [{"match": "touched", "number": 3,
                                 "bugs": [{"id": "222222",
                                           "restricted": True}]}]),
        ]
        out = measured_figures(self._report(rows))["provenance"]
        self.assertEqual(out["rows"], 2)
        self.assertEqual(out["rows_named_by_a_verdict"], 1)
        self.assertEqual(out["rows_leads_only"], 1)
        self.assertEqual(out["cls_cited"], 3)
        self.assertEqual(out["verdicts"],
                         {"declares": 1, "exact": 1, "touched": 1})
        self.assertEqual(out["issues_linked"], 2)
        self.assertEqual(out["issues_restricted"], 1)

    def test_a_report_nothing_was_looked_up_in_claims_nothing(self):
        """Zero reads as a measurement, and there was no measurement."""
        from chromiumdiff.model import Change, Finding
        from chromiumdiff.cli import measured_figures

        bare = Finding(change=Change(change_type="modified",
                                     kind="base_feature", key="A", name="A"),
                       score=50)
        self.assertNotIn("provenance",
                         measured_figures(self._report([bare])))

    def test_it_does_not_delete_a_measurement_it_cannot_retake(self):
        """A `wide` run is expensive and rarely on disk, so this is usually
        invoked without one. Dropping the section that needed it would silently
        delete a real figure, which is the failure the artifact exists to
        prevent."""
        import argparse

        from chromiumdiff.cli import cmd_figures
        from chromiumdiff.model import write_json

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        out = os.path.join(tmp, "figures.json")
        report = os.path.join(tmp, "report.json")
        write_json(report, self._report([]).to_dict())
        write_json(out, {"coverage": {"wide": {"read": 8295,
                                               "candidates": 8366}}})
        cmd_figures(argparse.Namespace(report=report, wide=None, out=out))
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["coverage"]["wide"]["read"], 8295)


class TestEveryFlagIsActedOn(unittest.TestCase):
    """A command must not accept a flag it then ignores.

    Every subcommand used to inherit one shared parent parser, so `catalog`
    advertised --local-src, --refresh and (while it existed) --mode, and did
    nothing with any of
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
        with open(os.path.join(root, "chromiumdiff", "cli.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == f"cmd_{name}")
        return {n.attr for n in ast.walk(fn)
                if isinstance(n, ast.Attribute)
                and getattr(n.value, "id", "") == "args"}

    def test_no_subcommand_offers_a_flag_it_never_reads(self):
        from chromiumdiff.cli import build_parser

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
        from chromiumdiff.cli import build_parser

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

    # `agent/` is the one place where a model reading the output is the whole
    # subject, so the rule stops at its door rather than being weakened for
    # everyone. What it still protects is the claim that mattered: the
    # pipeline -- snapshot, compare, rank, report -- ends at the report, and
    # nothing on that path may promise a stage that was removed. A chat asked
    # for by name with `serve --chat` is not that stage returning; it reads a
    # finished report the same way a person does.
    EXEMPT = os.sep + "agent" + os.sep

    def test_nothing_in_the_package_describes_a_model_reading_the_output(self):
        import glob

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for path in glob.glob(os.path.join(root, "chromiumdiff", "**", "*.py"),
                              recursive=True):
            if self.EXEMPT in path:
                continue
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


class TestProvenanceStopsAtEvidence(unittest.TestCase):
    """A CL is cited only when the diff says so, and the two strengths differ.

    The whole point of the stage is that a declaration file is shared: 500 CLs
    touched about_flags.cc between the M148 and M151 branch points and 62
    touched content_features.cc, so the file alone names hundreds of CLs for
    one flag. What narrows it is the diff, and how far the diff narrows it is
    the difference between a citation and a guess -- which is why the two
    verdicts are separate values and not a confidence number.
    """

    def _change(self, kind, key, name=None):
        from chromiumdiff.model import Change
        return Change(change_type="modified", kind=kind, key=key,
                      name=name if name is not None else key)

    def test_a_feature_is_searched_for_under_both_spellings(self):
        from chromiumdiff.enrich.gerrit import tokens_for

        tokens = tokens_for(self._change("base_feature", "BackForwardCache"))
        self.assertIn("BackForwardCache", tokens)
        self.assertIn("kBackForwardCache", tokens)

    def test_a_qualified_key_also_yields_the_leaf_the_declaration_writes(self):
        from chromiumdiff.enrich.gerrit import tokens_for

        tokens = tokens_for(self._change(
            "mojo_method", "blink.mojom.AIManager.CreateLanguageModel",
            "CreateLanguageModel"))
        self.assertIn("CreateLanguageModel", tokens)

    def test_a_leaf_too_short_to_identify_anything_is_not_searched_for(self):
        """`url` matches every line in a .mojom; the qualified key does not."""
        from chromiumdiff.enrich.gerrit import tokens_for

        tokens = tokens_for(self._change(
            "mojo_field", "blink.mojom.TokenError.url", "url"))
        self.assertNotIn("url", tokens)
        self.assertIn("blink.mojom.TokenError.url", tokens)

    def test_a_changed_line_is_exact_and_a_neighbour_is_only_nearby(self):
        from chromiumdiff.enrich import gerrit

        edited = [("  kFoo,", True), ("  b);", False)]
        self.assertEqual(gerrit._match(gerrit._Scanned(edited), {"kFoo"}),
                         "exact")

        # The name line is untouched; a line inside its parameter list is not.
        body = [("  kFoo(", False), ("    a,", True), ("    b);", False)]
        self.assertEqual(gerrit._match(gerrit._Scanned(body), {"kFoo"}),
                         "declares")

    def test_a_change_above_the_name_is_not_part_of_the_declaration(self):
        """Directional on purpose. A declaration's body follows its name -- a
        Mojo method's parameters, a field's type -- so an edit *above* the name
        belongs to whatever was declared before it, not to this."""
        from chromiumdiff.enrich import gerrit

        above = [("  edited,", True), ("  Other();", False),
                 ("  CreateWriter(", False), ("    a);", False)]
        self.assertEqual(gerrit._match(gerrit._Scanned(above),
                                       {"CreateWriter"}), "")
        below = [("  edited,", False), ("  Other();", False),
                 ("  CreateWriter(", False), ("    a,", True), ("    b);", False)]
        self.assertEqual(gerrit._match(gerrit._Scanned(below),
                                       {"CreateWriter"}), "declares")

    def test_a_key_that_is_not_written_anywhere_falls_back_to_its_container(self):
        """`blink.mojom.TokenError.url` is our construction, not text.

        A .mojom writes `struct TokenError {` and `url.mojom.Url? url;` and
        never the qualified name, and `url` is too short to search for -- so
        the whole token set was unfindable and 13 diffs were read for a string
        that cannot occur in any of them. Reported as "no CL edits a line
        carrying this identifier", which was true and deeply misleading.
        """
        from chromiumdiff.enrich.gerrit import tokens_for

        from chromiumdiff.enrich.gerrit import container_for

        change = self._change("mojo_field", "blink.mojom.TokenError.url", "url")
        self.assertNotIn("url", tokens_for(change))
        self.assertEqual(container_for(change), "TokenError")

    def test_the_container_can_never_reach_the_stronger_verdict(self):
        """A changed line mentioning `TokenError` is not a changed line
        declaring `TokenError.url`. Mixed into the token set it claimed `exact`
        on two CLs that had merely tidied the struct."""
        from chromiumdiff.enrich import gerrit

        seq = [("struct TokenError {", True), ("  int32 a;", False),
               ("};", False)]
        self.assertEqual(
            gerrit._match(gerrit._Scanned(seq),
                          {"blink.mojom.TokenError.url"}, "TokenError"),
            "declares")

    def test_a_key_with_a_usable_leaf_does_not_widen_to_its_container(self):
        """`AIManager` names twenty methods; falling back to it when the method
        itself is searchable would trade one answer for twenty."""
        from chromiumdiff.enrich.gerrit import tokens_for

        from chromiumdiff.enrich.gerrit import container_for

        change = self._change("mojo_method",
                              "blink.mojom.AIManager.CreateLanguageModel",
                              "CreateLanguageModel")
        self.assertIn("CreateLanguageModel", tokens_for(change))
        self.assertEqual(container_for(change), "")

    def test_a_mention_far_from_every_edit_is_no_evidence_at_all(self):
        from chromiumdiff.enrich import gerrit

        seq = [("  kFoo;", False), ("  Other();", False),
               ("  edited,", True), ("  more);", False)]
        self.assertEqual(gerrit._match(gerrit._Scanned(seq), {"kFoo"}), "")

    def test_a_declaration_that_never_closes_is_not_attributed(self):
        """A shape the scanner cannot close is one it cannot bound, and an
        unbounded region would swallow the rest of the file."""
        from chromiumdiff.enrich import gerrit

        seq = [("  kFoo", False)] + [("filler", False)] * 80 + [("x", True)]
        self.assertEqual(gerrit._match(gerrit._Scanned(seq), {"kFoo"}), "")

    def test_a_record_in_another_grammar_falls_back_to_its_enclosing_block(self):
        """`runtime_enabled_features.json5` names a feature inside a `{...},`
        record and nothing after it ever ends in `;`, so scanning forward could
        only ever run to the cap."""
        from chromiumdiff.enrich import gerrit

        seq = [("  {", False),
               ('    name: "GetComputedStyleOutsideFlatTree",', False),
               ('    status: "stable",', True),
               ("  },", False),
               ("  {", False),
               ('    name: "Other",', False),
               ("  },", False)]
        self.assertEqual(
            gerrit._match(gerrit._Scanned(seq),
                          {"GetComputedStyleOutsideFlatTree"}), "declares")

        # ...and the record next door is not this one.
        elsewhere = list(seq)
        elsewhere[2] = ('    status: "stable",', False)
        elsewhere[5] = ('    name: "Other",', True)
        self.assertEqual(
            gerrit._match(gerrit._Scanned(elsewhere),
                          {"GetComputedStyleOutsideFlatTree"}), "")

    def test_a_struct_body_runs_to_its_closing_brace(self):
        """A field is reached through the struct that declares it, so the
        region is the whole struct rather than the first line ending in `;`."""
        from chromiumdiff.enrich import gerrit

        seq = [("struct TokenError {", False), ("  string? a;", False),
               ("  url.mojom.Url? url;", True), ("};", False)]
        self.assertEqual(gerrit._match(gerrit._Scanned(seq),
                                       {"TokenError"}), "declares")
        after = [("struct TokenError {", False), ("};", False),
                 ("struct Other { int32 x; };", True)]
        self.assertEqual(gerrit._match(gerrit._Scanned(after),
                                       {"TokenError"}), "")

    def test_a_declares_hit_survives_beside_an_exact_one(self):
        """It used to be dropped as a weaker copy of the same answer, and it
        is not one: a CL that edited the declaration's body without touching
        the line naming it is a different CL doing different work. On a real
        top 150 the rule threw away 40 CLs across 18 findings, all of them on
        rows that had more than one contributor.

        It still ranks below, so it can never be read as the citation.
        """
        from chromiumdiff.enrich.gerrit import _prune

        kept = _prune([{"match": "declares", "date": "2026-06-01"},
                       {"match": "exact", "date": "2026-04-01"}])
        self.assertEqual({h["match"] for h in kept}, {"exact", "declares"})

    def test_a_crowd_of_declarations_is_still_dropped_beside_a_strong_hit(self):
        """The scarcity test is what makes `declares` mean anything, and it
        does not stop applying because a strong hit turned up."""
        from chromiumdiff.enrich import gerrit

        crowd = [{"match": "declares", "date": f"2026-06-{i + 1:02d}"}
                 for i in range(gerrit.DECL_MAX + 1)]
        kept = gerrit._prune(crowd + [{"match": "exact", "date": "2026-04-01"}])
        self.assertEqual([h["match"] for h in kept], ["exact"])

    def test_a_crowd_of_declarations_is_demoted_and_not_dropped(self):
        """The ai_manager.mojom case: four confident, unrelated answers.

        They must not stay `declares`, which claims one of them made this
        change. They must also not vanish -- dropping them told a reader who
        opened the row that nothing was found about a declaration that eleven
        CLs had edited. `crowded` is both: kept, and ranked below every verdict
        that names the fact.
        """
        from chromiumdiff.enrich import gerrit

        many = [{"match": "declares", "date": f"2026-06-0{i}"}
                for i in range(1, gerrit.DECL_MAX + 2)]
        kept = gerrit._prune(many)
        self.assertEqual(len(kept), len(many))
        self.assertEqual({h["match"] for h in kept}, {"crowded"})
        self.assertGreaterEqual(gerrit._STRENGTH["crowded"], gerrit.CITES)

        few = many[:gerrit.DECL_MAX]
        self.assertEqual([h["match"] for h in gerrit._prune(few)],
                         ["declares"] * gerrit.DECL_MAX)

    def test_a_crowd_never_displaces_a_cl_that_names_the_fact(self):
        """Demoting them is only safe while they cannot outrank real
        evidence, so the one `exact` still retires all eleven."""
        from chromiumdiff.enrich import gerrit

        hits = [{"match": "declares", "date": f"2026-06-0{i}"}
                for i in range(1, gerrit.DECL_MAX + 2)]
        hits.append({"match": "exact", "date": "2026-04-01"})
        self.assertEqual([h["match"] for h in gerrit._prune(hits)], ["exact"])

    def test_a_row_with_several_cls_reads_forward(self):
        """One CL is a citation and has no order. Several are a sequence, and
        a flag that launched, was reverted, relanded, reverted and relanded
        again is a story -- read newest-first it is not one. 28 of a real top
        150 keep more than one CL, so this is where those rows live.

        The cap still takes the newest, because that is what a cap should
        keep; only the surviving order changes.
        """
        from chromiumdiff.enrich.gerrit import _prune

        kept = _prune([{"match": "exact", "date": "2026-06-01"},
                       {"match": "exact", "date": "2026-04-01"}])
        self.assertEqual([h["date"] for h in kept],
                         ["2026-04-01", "2026-06-01"])

    def test_the_cap_keeps_the_newest_of_a_long_chain(self):
        from chromiumdiff.enrich import gerrit

        chain = [{"match": "exact", "date": f"2026-06-{i + 1:02d}"}
                 for i in range(gerrit.KEEP_MAX + 4)]
        kept = gerrit._prune(chain)
        self.assertEqual(len(kept), gerrit.KEEP_MAX)
        self.assertEqual(kept[-1]["date"], chain[-1]["date"])
        self.assertNotIn(chain[0]["date"], [h["date"] for h in kept])

    def test_a_footer_that_is_not_a_public_issue_is_not_offered_as_one(self):
        """Measured over 62 real CLs: 2 point at Google's internal tracker."""
        from chromiumdiff.enrich.gerrit import bugs_in

        self.assertEqual(
            bugs_in("Subject\n\nBug: 40123456, b/999888777\n"
                    "Fixed: crbug.com/445649104\nBug: none\n"
                    "Change-Id: I1\n"),
            [{"id": "40123456"},
             {"id": "445649104", "closes": True}])
        self.assertEqual(bugs_in("Subject\n\nChange-Id: I1\n"), [])

    def test_closing_an_issue_is_not_the_same_claim_as_citing_one(self):
        """Chromium writes both, 575 `Bug:` to 34 `Fixed:` in a real sample."""
        from chromiumdiff.enrich.gerrit import bugs_in

        self.assertNotIn("closes", bugs_in("s\n\nBug: 40123456\n")[0])
        self.assertTrue(bugs_in("s\n\nFixed: 40123456\n")[0]["closes"])


class TestTheThirdEvidenceTierIsFree(unittest.TestCase):
    """The CL's own description arrives with the candidate list, so it costs
    nothing -- and it is not redundant with the diff.

    Measured over the top 150 findings of a real M148 -> M151 run: 65 are found
    only by the diff and 17 only by the description, because a CL can delete
    the declaration it is named after and leave the identifier in no surviving
    line. Adding the tier took the run from 115 resolved findings to 131 while
    the budget below took it from 1,568 requests to 1,068.
    """

    def test_a_description_naming_the_identifier_is_evidence(self):
        from chromiumdiff.enrich.gerrit import _match_message

        cl = {"subject": "Enable AndroidCaptureKeyEvents by default",
              "revisions": {"r": {"commit": {"message": "body\n"}}}}
        self.assertTrue(_match_message(cl, {"AndroidCaptureKeyEvents"}))
        self.assertFalse(_match_message(cl, {"SomethingElse"}))

    def test_it_ranks_under_the_line_and_over_the_neighbourhood(self):
        from chromiumdiff.enrich.gerrit import _prune

        kept = _prune([{"match": "declares", "date": "2026-07-01"},
                       {"match": "described", "date": "2026-05-01"},
                       {"match": "exact", "date": "2026-03-01"}])
        # All three are contributors and all three are kept; the ladder shows
        # in which of them the cap would drop first, not in the print order,
        # which is chronological once a row holds more than one.
        self.assertEqual([h["date"] for h in kept],
                         ["2026-03-01", "2026-05-01", "2026-07-01"])


class TestABudgetBuysTheMostRowsItCan(unittest.TestCase):
    """A file is read whole whether it explains sixteen findings or one.

    So the unit of value is requests *per finding*, and a budget that runs out
    has to give up the worst trade rather than whichever file came first. At
    the default it gives up only trades that buy nothing: on a real run, 1,200
    diffs resolve the same 131 findings that 1,568 do.
    """

    COST = {"autofill": 127, "extension": 44, "runtime": 500, "content": 72}
    SERVED = {"autofill": 16, "extension": 1, "runtime": 1, "content": 5}

    def test_the_worst_trade_is_the_first_one_dropped(self):
        from chromiumdiff.enrich.gerrit import spend_order

        read, skipped = spend_order(self.COST, self.SERVED, budget=200)
        self.assertEqual(read, ["autofill", "content"])
        self.assertTrue(skipped[0].startswith("extension"))
        self.assertTrue(any(s.startswith("runtime") for s in skipped))

    def test_no_budget_reads_everything(self):
        from chromiumdiff.enrich.gerrit import spend_order

        read, skipped = spend_order(self.COST, self.SERVED, budget=0)
        self.assertEqual(sorted(read), sorted(self.COST))
        self.assertEqual(skipped, [])

    def test_a_file_is_taken_whole_or_not_at_all(self):
        """Half a file's CLs would make "no CL edits this line" depend on
        which half, which is a claim this stage must never make by accident."""
        from chromiumdiff.enrich.gerrit import spend_order

        read, _ = spend_order(self.COST, self.SERVED, budget=200)
        self.assertEqual(sum(self.COST[p] for p in read), 199)

    def test_a_file_nobody_looked_at_says_so(self):
        from chromiumdiff.report.html import _to_rows
        from chromiumdiff.model import Change, Finding, Report

        def report(diffs_read):
            block = {"candidates": 500, "changes": [
                {"number": 1, "date": "2026-06-01", "match": "described",
                 "subject": "s", "bugs": []}]}
            if diffs_read is not None:
                block["diffs_read"] = diffs_read
            return Report(from_ref="a", to_ref="b", summary={},
                          meta={"platform": "windows"},
                          findings=[Finding(
                              change=Change(change_type="modified",
                                            kind="base_feature", key="F",
                                            name="F", paths=["f.cc"]),
                              score=50, enrichment={"gerrit": block})])

        self.assertTrue(_to_rows(report(False), "windows")[0]["no_diffs"])
        self.assertNotIn("no_diffs", _to_rows(report(None), "windows")[0])


class TestTheProvenanceWindowIsTakenFromTheTags(unittest.TestCase):
    """Both bounds are facts the tags state, not estimates from their dates.

    The lower one is the *from* tag's branch point, because everything on main
    before it is in both trees and cannot explain a difference. Taking the tag
    date instead would have started the M148 window on 2026-05-26 rather than
    2026-04-06 and lost seven weeks of CLs. The upper one is the *to* tag's own
    date, because six weeks of merge-backs land on a release branch after it is
    cut and those are in the tree being compared.
    """

    FROM_TAG = {"message": "Incrementing VERSION to 148.0.7778.217\n\n"
                           "Cr-Branched-From: " + "a" * 40 +
                           "-refs/heads/main@{#1610480}\n",
                "committer": {"time": "Tue May 26 20:44:49 2026"}}
    BRANCH_POINT = {"message": "some CL\n",
                    "committer": {"time": "Mon Apr 06 22:34:10 2026"}}
    TO_TAG = {"message": "Incrementing VERSION to 151.0.7922.138\n\n"
                         "Cr-Branched-From: " + "b" * 40 +
                         "-refs/heads/main@{#1654411}\n",
              "committer": {"time": "Mon Aug 10 22:57:55 2026"}}
    TO_BRANCH_POINT = {"message": "some other CL\n",
                       "committer": {"time": "Mon Jun 29 18:02:11 2026"}}

    def _window(self):
        from chromiumdiff.enrich import gerrit

        lookup = {"148": self.FROM_TAG, "a" * 40: self.BRANCH_POINT,
                  "151": self.TO_TAG, "b" * 40: self.TO_BRANCH_POINT}
        real = gerrit._commit
        gerrit._commit = lambda ref, *a, **k: lookup.get(ref)
        try:
            return gerrit.window_for("148", "151", cache_dir="")
        finally:
            gerrit._commit = real

    def test_it_starts_at_the_branch_point_not_the_tag(self):
        self.assertEqual(self._window()[0], "2026-04-06")

    def test_the_main_search_stops_where_the_target_left_main(self):
        """A CL on main after the branch point is not in the released tree.

        It is not a harmless extra candidate either: it can carry the
        identifier, earn `exact`, and outrank the CL that really did it.
        Measured over 105 resolved rows of a real M148 -> M151 run while this
        ended at the tag date, 38 of 160 cited CLs had landed after M151
        branched and 11 rows ranked one of them first.
        """
        self.assertEqual(self._window()[1], "2026-06-30")

    def test_the_unpinned_search_still_reaches_the_tag_for_merge_backs(self):
        """Merge-backs land on the release branch for weeks after it is cut.

        They are in the tree being compared, so the one search that is not
        pinned to main is the one search allowed past the branch point.
        """
        self.assertEqual(self._window()[2], "2026-08-11")

    def test_a_target_tag_with_no_branch_point_keeps_the_old_ceiling(self):
        from chromiumdiff.enrich import gerrit

        bare = {"message": "Incrementing VERSION to 151.0.7922.138\n",
                "committer": {"time": "Mon Aug 10 22:57:55 2026"}}
        lookup = {"148": self.FROM_TAG, "a" * 40: self.BRANCH_POINT,
                  "151": bare}
        real = gerrit._commit
        gerrit._commit = lambda ref, *a, **k: lookup.get(ref)
        try:
            self.assertEqual(gerrit.window_for("148", "151", cache_dir=""),
                             ("2026-04-06", "2026-08-11", "2026-08-11"))
        finally:
            gerrit._commit = real


class TestAFailedFetchIsNeverReadAsNoEvidence(unittest.TestCase):
    """A dropped request and "this CL does not mention it" look identical.

    Gerrit rate-limits an anonymous client with HTTP 429, and a diff that came
    back empty because of one is indistinguishable, at the point of use, from a
    diff that genuinely does not carry the identifier. Absorbing it would turn
    a network hiccup into a confident "no CL found", which is the one thing
    this tool is not allowed to do.
    """

    def test_a_failure_is_counted_rather_than_swallowed(self):
        import chromiumdiff.enrich.gerrit as gerrit
        from chromiumdiff.acquire import AcquireError

        gerrit._failures.__init__()
        real = gerrit._http_get
        gerrit._http_get = lambda *a, **k: (_ for _ in ()).throw(
            AcquireError("404 nope"))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = gerrit._get_json("https://example.invalid/x", tmp,
                                       ("probe.json",))
        finally:
            gerrit._http_get = real
        self.assertIsNone(out)
        self.assertEqual(gerrit._failures.count, 1)
        self.assertIn("example.invalid", gerrit._failures.first)

    def test_rate_limiting_is_retried_on_its_own_ladder(self):
        """The generic 1.5/3/6s backoff is too short for a per-minute limiter."""
        import chromiumdiff.enrich.gerrit as gerrit
        from chromiumdiff.acquire import AcquireError

        gerrit._failures.__init__()
        calls = []

        def flaky(*a, **k):
            calls.append(1)
            if len(calls) < 3:
                raise AcquireError("HTTP Error 429: Too Many Requests")
            return b')]}\'\n{"ok": true}'

        real_get, real_sleep = gerrit._http_get, gerrit.time.sleep
        gerrit._http_get, gerrit.time.sleep = flaky, lambda s: None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = gerrit._get_json("https://example.invalid/y", tmp,
                                       ("probe.json",))
        finally:
            gerrit._http_get, gerrit.time.sleep = real_get, real_sleep
        self.assertEqual(out, {"ok": True})
        self.assertEqual(gerrit._failures.count, 0)


class TestTheSearchProvesItsOwnCompleteness(unittest.TestCase):
    """Gerrit stops at 500 rows for an anonymous query and does not say so.

    `start=500` returns an empty list with no `_more_changes` marker, which is
    exactly what reaching the end looks like. A window that comes back at the
    cap is therefore split and asked again, so the count is established rather
    than assumed, and `truncated` is claimed only where splitting can no longer
    help.
    """

    def _run(self, pages):
        from chromiumdiff.enrich import gerrit

        real = gerrit._page
        gerrit._page = lambda path, after, before, start, *a, **k: (
            pages(after, before)[start:start + gerrit.PAGE])
        try:
            return gerrit._search_window("f.cc", "2026-04-06", "2026-06-30",
                                         "", False, lambda m: None)
        finally:
            gerrit._page = real

    def test_a_window_at_the_cap_is_split_rather_than_believed(self):
        from chromiumdiff.enrich import gerrit

        def pages(after, before):
            """Whole window: capped. Either half: 400, which the cap hid."""
            whole = after == "2026-04-06" and before == "2026-06-30"
            n = gerrit.PAGE_CAP if whole else 400
            base = 0 if whole else (1 if after == "2026-04-06" else 2) * 10000
            return [{"_number": base + i} for i in range(n)]

        rows, truncated = self._run(pages)
        self.assertFalse(truncated)
        self.assertGreater(len(rows), gerrit.PAGE_CAP)

    def test_a_single_day_still_at_the_cap_is_reported_as_partial(self):
        from chromiumdiff.enrich import gerrit

        rows, truncated = self._run(
            lambda a, b: [{"_number": i} for i in range(gerrit.PAGE_CAP)])
        self.assertTrue(truncated)


class TestProvenanceRidesOnlyOnTheRowsItExplains(unittest.TestCase):
    """The payload carries a denominator only beside the CLs it counts.

    `_is_empty` keeps a zero on purpose, because a score of 0 is a real rank.
    That makes an unconditional `cl_pool` ride on all 3,022 rows to say nothing
    on the 2,896 with no CL, in a file whose size is already its main cost.
    """

    def _report(self, enriched):
        from chromiumdiff.model import Change, Finding, Report

        findings = []
        for i, enrich in enumerate(enriched):
            change = Change(change_type="modified", kind="base_feature",
                            key=f"Feat{i}", name=f"Feat{i}",
                            paths=["content/features.cc"])
            findings.append(Finding(change=change, score=50,
                                    enrichment=enrich or {}))
        return Report(from_ref="a", to_ref="b", findings=findings,
                      summary={}, meta={"platform": "windows"})

    def test_a_row_with_no_cl_carries_no_denominator(self):
        from chromiumdiff.report.html import _to_rows

        rows = _to_rows(self._report([None]), "windows")
        self.assertNotIn("cl_pool", rows[0])
        self.assertNotIn("cls", rows[0])

    def test_a_row_with_a_cl_carries_the_pool_it_was_picked_from(self):
        from chromiumdiff.report.html import _to_rows

        rows = _to_rows(self._report([{"gerrit": {
            "candidates": 62,
            "changes": [{"number": 7885356, "date": "2026-06-01",
                         "subject": "Enable it", "match": "exact",
                         "bugs": [{"id": "40123456"}]}]}}]), "windows")
        self.assertEqual(rows[0]["cl_pool"], 62)
        self.assertEqual(rows[0]["cls"][0]["n"], 7885356)
        self.assertEqual(rows[0]["cls"][0]["b"], [{"i": "40123456"}])

    def test_a_restricted_issue_is_flagged_in_the_payload(self):
        """70 of 236 issues a real report links answer 403; an unmarked link
        to one reads as a broken tool rather than as a closed door."""
        from chromiumdiff.report.html import _to_rows

        rows = _to_rows(self._report([{"gerrit": {
            "candidates": 3,
            "changes": [{"number": 1, "date": "2026-06-01", "subject": "s",
                         "match": "exact",
                         "bugs": [{"id": "9", "restricted": True,
                                   "closes": True}]}]}}]), "windows")
        self.assertEqual(rows[0]["cls"][0]["b"], [{"i": "9", "f": 1, "r": 1}])

    def test_the_markdown_prints_the_pool_and_the_strength(self):
        from chromiumdiff.report.markdown import _provenance_lines
        from chromiumdiff.model import Change, Finding

        finding = Finding(
            change=Change(change_type="modified", kind="base_feature",
                          key="Feat", name="Feat"),
            enrichment={"gerrit": {"candidates": 62, "changes": [
                {"number": 7885356, "date": "2026-06-01", "match": "exact",
                 "subject": "Enable it",
                 "bugs": [{"id": "40123456"}]}]}})
        text = "\n".join(_provenance_lines(finding))
        self.assertIn("1 of 62 merged CLs", text)
        self.assertIn("*exact*", text)
        self.assertIn("/7885356", text)
        self.assertIn("issues.chromium.org/issues/40123456", text)


class TestServingDoesNotChangeTheFile(unittest.TestCase):
    """`serve` adds a live path without taking the offline one away.

    The report's value is that it is one file that works anywhere. Serving it
    must not fork that into two artifacts, so the page discovers whether
    anything is listening rather than being built differently, and the file on
    disk is byte-identical either way.
    """

    def _dir(self):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        report = Report(from_ref="a", to_ref="b", summary={},
                        meta={"platform": "windows"},
                        findings=[Finding(
                            change=Change(change_type="modified",
                                          kind="base_feature", key="F",
                                          name="F", paths=["f.cc"]),
                            score=50)])
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh)
        with open(os.path.join(tmp, "report.html"), "w", encoding="utf-8") as fh:
            fh.write(html_report.render(report))
        return tmp

    def _server(self):
        import threading
        from http.server import ThreadingHTTPServer
        from chromiumdiff import serve as serve_mod

        state = serve_mod._State(self._dir(), tempfile.mkdtemp(), budget=1)
        handler = type("_B", (serve_mod._Handler,), {"state": state})
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.shutdown)
        self.addCleanup(httpd.server_close)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    def _get(self, base, path):
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(base + path, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            # Closed, not dropped: an HTTPError owns the socket, and one left
            # to the collector prints a ResourceWarning later, from whichever
            # frame happened to be running when the collector got to it.
            with exc:
                return exc.code, b""

    def test_the_page_reports_which_pair_it_is_serving(self):
        base = self._server()
        status, body = self._get(base, "/api/ping")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["from"], "a")

    def test_only_the_report_is_reachable(self):
        """Nothing resolves a path out of the request, so there is no traversal
        to get wrong -- and this is what holds that true."""
        base = self._server()
        self.assertEqual(self._get(base, "/")[0], 200)
        for path in ("/../../etc/passwd", "/serve.py", "/report.py",
                     "/%2e%2e/report.json"):
            self.assertEqual(self._get(base, path)[0], 404, path)

    def test_an_unknown_finding_is_a_miss_not_a_crash(self):
        base = self._server()
        self.assertEqual(self._get(base, "/api/why?uid=nope:nope")[0], 404)
        self.assertEqual(self._get(base, "/api/why")[0], 400)

    def test_the_dom_harness_knows_the_same_provenance_keys(self):
        """The page embeds the list; the node harness carries a copy.

        The copy is there because the harness evaluates only the page's code
        block and never runs the block that assigns the payload, so it has to
        stand the constant up itself. Two lists is the shape this project
        keeps finding bugs in, and this is the thread that catches this one:
        a key added to the renderer and not to the harness would leave the
        harness testing a page that clears one fewer field than the real one.
        """
        import re

        from chromiumdiff.report.html import PROVENANCE_KEYS

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "tests", "js", "report_dom.js")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        block = re.search(r"__PROVKEYS__ = \[(.*?)\]", text, re.S)
        self.assertIsNotNone(block, "the harness no longer declares the list")
        self.assertEqual(sorted(re.findall(r"'([^']+)'", block.group(1))),
                         sorted(PROVENANCE_KEYS))

    def test_stopping_says_how_to_get_what_you_found_into_the_report(self):
        """A session's findings go to `report.json` and nowhere else.

        Rewriting `report.md` from under a reader who may have it open is
        worse than leaving it a command away -- but nobody guesses the
        command, so it is printed at the one moment it is wanted.
        """
        import shutil

        from chromiumdiff import serve as serve_mod

        directory = self._dir()
        lines = []
        real_server, real_state = (serve_mod.ThreadingHTTPServer,
                                   serve_mod._State)

        class _Stops(real_server):
            def serve_forever(self, *a, **k):
                raise KeyboardInterrupt

        class _Found(real_state):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.resolved = 3

        serve_mod.ThreadingHTTPServer, serve_mod._State = _Stops, _Found
        try:
            serve_mod.serve(directory, tempfile.mkdtemp(), log=lines.append)
        finally:
            (serve_mod.ThreadingHTTPServer,
             serve_mod._State) = real_server, real_state
        text = "\n".join(lines)
        self.assertIn("stopped after resolving 3 row(s)", text)

        # Run what it printed, rather than reading it. The command parsed
        # cleanly and named the right file and still did nothing, because
        # `report` writes to stdout unless `--out` says otherwise: the reader
        # got a report in the terminal and two files as stale as before.
        printed = [ln.strip() for ln in lines
                   if "python3 -m chromiumdiff report" in ln]
        self.assertEqual(1, len(printed), text)
        argv = printed[0].split()[3:]           # drop `python3 -m chromiumdiff`
        md = os.path.join(directory, "report.md")
        html = os.path.join(directory, "report.html")
        for path in (md, html):
            if os.path.exists(path):
                os.remove(path)

        from chromiumdiff import cli
        self.assertEqual(0, cli.main(argv))
        for path in (md, html):
            self.assertTrue(os.path.exists(path),
                            "%s: the command it prints does not write it" % path)

    def test_an_issue_id_has_to_be_one(self):
        """The route takes a number and nothing else.

        It reaches the tracker and Gerrit with whatever it is handed, so the
        one thing it must not do is pass a caller's string through to either.
        """
        base = self._server()
        for bad in ("", "abc", "1;2", "../x", "12%20OR%201"):
            self.assertEqual(self._get(base, f"/api/issue?id={bad}")[0], 400, bad)

    def _state_with(self, changes, before_main=""):
        from chromiumdiff import serve as serve_mod

        state = serve_mod._State(self._dir(), tempfile.mkdtemp(), budget=1)
        state._before_main = before_main
        finding = state.by_uid["base_feature:F"]
        finding.enrichment = {"gerrit": {"changes": changes}}
        return state, finding

    def test_an_answer_written_under_a_corrected_lookup_is_asked_again(self):
        """A stored answer is not re-fetched, and the cost of that is a report
        outliving the bug it was written under.

        Both known ones are visible in what was stored, so neither needs a
        flag or a version stamp: a CL with no `at` was ordered by the day, and
        a CL dated after the target left main is not in the tree at all. 16 of
        the 60 rows in one real report cite the second kind.
        """
        good = [{"number": 1, "date": "2026-05-01",
                 "at": "2026-05-01 00:00:00.000000000"}]
        state, _ = self._state_with(good, before_main="2026-06-30")
        self.assertFalse(state._stale({"changes": good}))

        no_stamp = [{"number": 1, "date": "2026-05-01"}]
        self.assertTrue(state._stale({"changes": no_stamp}))

        past_branch = [{"number": 1, "date": "2026-07-20",
                        "at": "2026-07-20 00:00:00.000000000"}]
        self.assertTrue(state._stale({"changes": past_branch}))

    def test_a_lookup_that_lost_requests_is_asked_again(self):
        """The panel tells the reader to open the row again to retry.

        Until this was here that instruction did nothing: the row had CLs, so
        it was served rather than asked, and an answer the lookup itself calls
        unfinished stayed unfinished for as long as the report existed.
        """
        good = [{"number": 1, "date": "2026-05-01",
                 "at": "2026-05-01 00:00:00.000000000"}]
        state, _ = self._state_with(good, before_main="2026-06-30")
        self.assertFalse(state._stale({"changes": good}))
        self.assertTrue(state._stale({"changes": good, "failed_fetches": 2}))

    def test_refresh_reaches_the_enricher(self):
        """`enrich` has taken a `refresh` since it was written and no caller
        ever set it. Re-asking a row still reads the HTTP cache, so a bad
        response cached once is a bad answer for ever; this is the way past."""
        from chromiumdiff import serve as serve_mod
        from chromiumdiff.enrich import gerrit

        seen = {}
        real = gerrit.enrich
        gerrit.enrich = lambda *a, **k: (seen.update(k), {"available": False})[1]
        try:
            state = serve_mod._State(self._dir(), tempfile.mkdtemp(), budget=1,
                                     refresh=True)
            state.resolve("base_feature:F")
        finally:
            gerrit.enrich = real
        self.assertIs(seen.get("refresh"), True)

    def test_a_report_whose_refs_no_longer_resolve_keeps_what_it_holds(self):
        """An unanswerable question is not an answer of no. Throwing the row
        away because the window could not be derived would lose evidence to a
        network fault."""
        state, _ = self._state_with([], before_main="")
        self.assertFalse(state._stale(
            {"changes": [{"number": 1, "date": "2026-07-20",
                          "at": "2026-07-20 00:00:00.000000000"}]}))

    def test_a_stale_block_is_dropped_rather_than_written_over(self):
        """`enrich` reuses the block it finds, so a key an older run set and
        this one does not would survive and read as part of the new answer."""
        from chromiumdiff.enrich import gerrit

        state, finding = self._state_with(
            [{"number": 1, "date": "2026-05-01"}])          # no `at` -> stale
        finding.enrichment["gerrit"]["issues"] = [{"id": "1", "changes": [1]}]
        real = gerrit.enrich

        def spy(findings, *a, **k):
            self.assertNotIn("gerrit", findings[0].enrichment)
            return {}

        gerrit.enrich = spy
        try:
            state.resolve("base_feature:F")
        finally:
            gerrit.enrich = real

    def test_a_lookup_updates_the_summary_the_markdown_reads(self):
        """`report.md` takes its group table from the summary, which `run`
        wrote once -- before any CL existed to group on. Re-rendering after a
        session of lookups would print the run's groups over the lookups'
        findings."""
        from chromiumdiff import cluster, serve as serve_mod
        from chromiumdiff.enrich import gerrit

        real = gerrit.enrich
        gerrit.enrich = lambda *a, **k: {"available": False}
        try:
            state = serve_mod._State(self._dir(), tempfile.mkdtemp(), budget=1)
            state.report.summary = {"clusters": [{"label": "stale"}]}
            state.resolve("base_feature:F")
        finally:
            gerrit.enrich = real
        self.assertEqual(state.report.summary["clusters"], [])

    def test_a_lookup_regroups_the_report(self):
        """The CL rule can only fire once a lookup has brought the CLs in.

        `cluster.annotate` ran in `run` and nowhere else, and `run` never asks
        Gerrit anything -- so the rule that joins findings sharing a CL could
        never fire at all. A lookup is the moment its evidence arrives.
        """
        from chromiumdiff import cluster, serve as serve_mod
        from chromiumdiff.enrich import gerrit

        seen = []
        real_enrich, real_annotate = gerrit.enrich, cluster.annotate
        gerrit.enrich = lambda *a, **k: {"available": False}
        cluster.annotate = lambda findings: seen.append(len(findings)) or {}
        try:
            state = serve_mod._State(self._dir(), tempfile.mkdtemp(), budget=1)
            state.resolve("base_feature:F")
        finally:
            gerrit.enrich, cluster.annotate = real_enrich, real_annotate
        self.assertEqual(seen, [1])

    def test_a_row_lookup_does_not_pay_for_issue_history(self):
        """The CLs carry their `Bug:` footers already; the history behind one
        is fetched only when a reader picks that CL and asks for it.

        Held here rather than at the renderer because the cost is the point:
        a row citing six issues used to spend twelve requests before the
        reader had decided which CL mattered.
        """
        from chromiumdiff import serve as serve_mod
        from chromiumdiff.enrich import gerrit

        seen = {}
        real = gerrit.enrich

        def spy(*a, **k):
            seen.update(k)
            return {"available": False}

        gerrit.enrich = spy
        try:
            state = serve_mod._State(self._dir(), tempfile.mkdtemp(), budget=1)
            state.resolve("base_feature:F")
        finally:
            gerrit.enrich = real
        self.assertEqual(seen.get("with_history"), 0)

    def test_the_server_returns_every_key_the_renderer_adds(self):
        """One list, in the renderer. Two lists drifted the first time a key
        was renamed -- `issue` became `issues` and the server went on filtering
        for `issue`, so every lookup dropped the issue history in silence."""
        from chromiumdiff.report import html as html_report
        from chromiumdiff import serve as serve_mod
        import inspect

        source = inspect.getsource(serve_mod._State._payload)
        self.assertIn("PROVENANCE_KEYS", source)
        for key in ("cls", "issues", "no_diffs"):
            self.assertIn(key, html_report.PROVENANCE_KEYS)

    def test_a_lookup_survives_the_session_that_made_it(self):
        """Minutes of clicking must not be lost to a closed terminal, or the
        live path is strictly worse than baking the answers in."""
        from chromiumdiff import serve as serve_mod

        directory = self._dir()
        state = serve_mod._State(directory, tempfile.mkdtemp(), budget=1)
        finding = state.report.findings[0]
        finding.enrichment["gerrit"] = {
            "candidates": 3, "diffs_read": True,
            "changes": [{"number": 1, "date": "2026-06-01", "match": "exact",
                         "subject": "s", "bugs": []}]}
        state._persist()

        reloaded = serve_mod._State(directory, tempfile.mkdtemp(), budget=1)
        again = reloaded.report.findings[0]
        self.assertEqual(
            again.enrichment["gerrit"]["changes"][0]["number"], 1)
        # And the page it serves is built from that, not from a stale file.
        self.assertIn(b"7885356" if False else b'"n": 1', reloaded.page())

    def test_saving_can_be_declined(self):
        from chromiumdiff import serve as serve_mod

        directory = self._dir()
        state = serve_mod._State(directory, tempfile.mkdtemp(), budget=1,
                                 save=False)
        state.report.findings[0].enrichment["gerrit"] = {"candidates": 1}
        state._persist()
        with open(os.path.join(directory, "report.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["findings"][0]["enrichment"], {})

    def test_the_page_is_static_until_something_answers(self):
        """A report mailed to somebody must behave as it always did, so live
        mode starts off and is turned on only by a reply."""
        from chromiumdiff.model import Report
        from chromiumdiff.report import html as html_report

        page = html_report.render(Report(from_ref="a", to_ref="b"))
        self.assertIn("var LIVE=false", page)
        self.assertIn("fetch('api/ping')", page)


class TestTheEvidenceFilterAppearsWhenItCanFilter(unittest.TestCase):
    """A row with a CL and a row without look identical in the table.

    On a report where a fifth of the rows are resolved, that is the difference
    between a list you can work through and one you have to open row by row to
    find out. But a control that filters nothing is worse than no control, so
    on an untouched report it is rendered hidden and the page unhides it the
    moment a server answers or a lookup lands. Rendering it either way is what
    lets one file be right in both cases.
    """

    def _page(self, enriched):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        findings = []
        for i, block in enumerate(enriched):
            findings.append(Finding(
                change=Change(change_type="modified", kind="base_feature",
                              key=f"F{i}", name=f"F{i}", paths=["f.cc"]),
                score=50, enrichment=({"gerrit": block} if block else {})))
        return html_report.render(Report(from_ref="a", to_ref="b",
                                         findings=findings, summary={},
                                         meta={"platform": "windows"}))

    def test_hidden_until_there_is_something_to_filter(self):
        page = self._page([None, None])
        self.assertIn('id="fp" hidden', page)
        # ...and the page can turn it on without being re-rendered.
        self.assertIn("fp.hidden=false", page.replace(" ", ""))

    def test_shown_as_soon_as_one_row_carries_evidence(self):
        page = self._page([None, {"candidates": 3, "diffs_read": True}])
        self.assertIn('id="fp"', page)
        self.assertNotIn('id="fp" hidden', page)
        for label in ("Has a CL", "Scanned, nothing found", "Not looked up"):
            self.assertIn(label, page)

    def test_the_four_states_are_kept_apart_in_the_page(self):
        """`none` and `skipped` must not collapse into one "no CL": telling
        them apart is the whole point of the stage."""
        page = self._page([{"candidates": 3, "diffs_read": True}])
        self.assertIn("function provState", page)
        for state in ("'exact'", "'cl'", "'skipped'", "'unasked'"):
            self.assertIn(state, page)


class TestThePayloadStopsRepeatingItself(unittest.TestCase):
    """The page's size is its load time, and a quarter of it was repetition.

    Measured on a real 3,022-finding report: `reasons` is 319 KB of text drawn
    from 66 distinct strings, `signals` 127 KB from 63, and `group` 58 KB from
    three. Stored once and referenced by index the payload falls from 2.29 MB
    to 1.75 MB. Every interaction was already under 5 ms, so the download and
    the JSON parse were the only thing left that a reader could feel.
    """

    def _page(self, n=400):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        findings = [
            Finding(change=Change(change_type="modified", kind="base_feature",
                                  key=f"F{i}", name=f"F{i}",
                                  signals=["flag_retired_on"],
                                  paths=[f"content/f{i}.cc"]),
                    score=50, reasons=["base severity 75"])
            for i in range(n)]
        return html_report.render(Report(from_ref="a", to_ref="b",
                                         findings=findings, summary={},
                                         meta={"platform": "windows"}))

    def test_a_value_shared_by_every_row_is_stored_once(self):
        import re

        page = self._page()
        payload = re.search(r"window\.__FINDINGS__=(\[.*?\]);\n", page, re.S)
        self.assertIn('"reasons": 0', payload.group(1))
        self.assertEqual(payload.group(1).count("base severity 75"), 0)
        self.assertIn("base severity 75", page)  # once, in the pool

    def test_the_page_puts_them_back_before_anything_reads_them(self):
        page = self._page()
        self.assertIn("window.__POOL__=", page)
        self.assertIn("DATA[i][field]=table[v]", page.replace(" ", ""))

    def test_one_reader_for_the_payload_and_it_rehydrates(self):
        """Every other reader goes through this, so none of them can drift
        into parsing the interned form as if it were the plain one."""
        from chromiumdiff.report import html as html_report

        rows = html_report.payload_of(self._page(5))
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(row["reasons"], ["base severity 75"])
            self.assertIsInstance(row["group"], str)

    def test_a_field_that_is_nearly_unique_is_left_alone(self):
        """A table of 2,986 distinct `what` strings is the same bytes plus an
        index, so pooling it would cost rather than save."""
        from chromiumdiff.report import html as html_report

        rows = html_report.payload_of(self._page(5))
        self.assertNotIn("what", html_report._POOLED)
        self.assertIsInstance(rows[0]["what"], str)


class TestARowCountsWhatItActuallyDid(unittest.TestCase):
    """Three numbers, three questions, and the row was answering one of them
    three times.

    How many CLs touched the file, how many of those a diff tied to this fact,
    and how many of those are printed. `1 of 510 merged CLs touched this file`
    was said about a file whose newest 500 were read; `8 of 19` was said about
    a row where 15 matched and 7 were cut with nothing to say so. The issue
    block one panel down had this right the whole time -- "11 CLs cite it,
    newest 8 shown".
    """

    def _finding(self, block):
        from chromiumdiff.model import Change, Finding

        return Finding(
            change=Change(change_type="modified", kind="base_feature",
                          key="kFoo", name="kFoo", paths=["f.cc"]),
            score=90, enrichment={"gerrit": block})

    BLOCK = {"candidates": 510, "candidates_read": 500, "matched": 15,
             "diffs_read": True,
             "changes": [{"number": 700 + i, "date": f"2026-06-{i + 1:02d}",
                          "match": "exact", "subject": "s", "bugs": []}
                         for i in range(12)]}

    def test_the_number_opened_reaches_the_row(self):
        """Set by the enricher under `candidates_read` and never mapped, so
        the panel's own guard on it could not fire on any row ever built."""
        from chromiumdiff.model import Report
        from chromiumdiff.report import html as html_report

        row = html_report._to_rows(
            Report(from_ref="a", to_ref="b",
                   findings=[self._finding(self.BLOCK)]), "windows")[0]
        self.assertEqual(row["cl_pool"], 510)
        self.assertEqual(row["cl_read"], 500)
        self.assertEqual(row["cl_match"], 15)

    def test_a_list_that_was_cut_says_so_in_both_reports(self):
        from chromiumdiff.model import Report
        from chromiumdiff.report import markdown as md_report

        line = [l for l in md_report._provenance_lines(self._finding(self.BLOCK))
                if "merged CLs" in l][0]
        self.assertIn("15 of 510", line)
        self.assertIn("500 of them read", line)
        self.assertIn("newest 12 shown", line)

    def test_the_enricher_records_the_cut_it_made(self):
        """Asserted through `enrich`, because the block above is hand-built
        and a hand-built block cannot notice the line that fills it."""
        from chromiumdiff.enrich import gerrit
        from chromiumdiff.model import Change, Finding

        n = gerrit.KEEP_MAX + 4
        cls = [{"_number": 100 + i, "subject": f"CL {i}",
                "submitted": f"2026-05-{i + 1:02d} 00:00:00.000000000"}
               for i in range(n)]
        finding = Finding(
            change=Change(change_type="modified", kind="base_feature",
                          key="kFoo", name="kFoo", paths=["f.cc"]), score=90)
        saved = (gerrit.window_for, gerrit._search_window, gerrit._diff)
        gerrit.window_for = lambda *a, **k: ("2026-04-06", "2026-06-30",
                                            "2026-08-11")
        gerrit._search_window = lambda *a, **k: ([dict(c) for c in cls], False)
        gerrit._diff = lambda *a, **k: [("  kFoo,", gerrit.ADDED)]
        try:
            gerrit.enrich([finding], "148", "151", cache_dir="",
                          with_history=0, log=lambda m: None)
        finally:
            (gerrit.window_for, gerrit._search_window, gerrit._diff) = saved
        block = finding.enrichment["gerrit"]
        self.assertEqual(len(block["changes"]), gerrit.KEEP_MAX)
        self.assertEqual(block["matched"], n,
                         "the row prints this as its numerator; without it "
                         "the count of what fitted passes for the count of "
                         "what matched")

    def test_a_list_that_was_not_cut_claims_no_cut(self):
        from chromiumdiff.report import markdown as md_report

        whole = dict(self.BLOCK, matched=None, candidates_read=None,
                     changes=self.BLOCK["changes"][:2])
        line = [l for l in md_report._provenance_lines(self._finding(whole))
                if "merged CLs" in l][0]
        self.assertIn("2 of 510", line)
        self.assertNotIn("shown", line)
        self.assertNotIn("read", line)


class TestGerritsDiffIsReadAsGerritMeansIt(unittest.TestCase):
    """The four block shapes, and the rename that carries a fact out of a file.

    `_blocks` is where three of the four "confident wrong answers" this stage
    was built to stop actually get stopped, and nothing in the suite had ever
    called it: every mutation below left the suite green. They are cheap to
    hold because the shapes are Gerrit's, small, and documented.
    """

    def _blocks(self, content):
        from chromiumdiff.enrich.gerrit import _blocks

        return _blocks({"content": content})

    def test_context_is_not_a_change(self):
        from chromiumdiff.enrich.gerrit import CONTEXT

        self.assertEqual(self._blocks([{"ab": ["  int a;", "  int b;"]}]),
                         [("  int a;", CONTEXT), ("  int b;", CONTEXT)])

    def test_a_removed_line_and_an_added_one_are_told_apart(self):
        """The whole of `introduced` rests on this. Flattened into one
        "changed" flag, the direction an edit went is gone, and a CL that took
        the new value *out* reads exactly like the one that put it in."""
        from chromiumdiff.enrich.gerrit import ADDED, REMOVED

        self.assertEqual(
            self._blocks([{"a": ["  Vector2d x;"], "b": ["  Vector2dF x;"]}]),
            [("  Vector2d x;", REMOVED), ("  Vector2dF x;", ADDED)])

    def test_a_reindent_is_not_an_edit(self):
        """`{"a": [...], "b": [...], "common": true}` is Gerrit saying these
        lines are the same content differing only inside the line. Read as
        changed, a CL that reformats a file becomes an `exact` match for every
        declaration in it -- 49 such blocks in one real sample."""
        from chromiumdiff.enrich.gerrit import CONTEXT

        seq = self._blocks([{"a": ["  int kFoo;"], "b": ["    int kFoo;"],
                             "common": True}])
        self.assertEqual({state for _, state in seq}, {CONTEXT})

    def test_a_skip_stands_for_the_lines_it_hides(self):
        """`{"skip": N}` is N unchanged lines Gerrit did not send. Dropped,
        the file silently shortens and every line after it moves -- which
        moves what counts as inside a declaration."""
        from chromiumdiff.enrich.gerrit import CONTEXT

        seq = self._blocks([{"ab": ["  a"]}, {"skip": 40}, {"ab": ["  b"]}])
        self.assertEqual(len(seq), 42)
        self.assertEqual(seq[41], ("  b", CONTEXT))
        self.assertEqual({state for _, state in seq}, {CONTEXT})

    def test_a_skip_that_is_not_a_number_does_not_stop_the_scan(self):
        self.assertEqual(len(self._blocks([{"skip": None}, {"ab": ["  a"]}])), 1)

    def test_a_row_served_from_a_stale_cache_says_it_is_short(self):
        """`--refresh` promises to ignore the cache. When the warm pass loses
        a fetch, the read pass finds the entry a previous run left and serves
        it -- still the best available answer, and not a finished one.

        The qualifier is recorded by `enrich` rather than by whoever called
        it, so it travels with the answer whether the answer came from a click
        or from a batch. Recorded by the caller it reached one of the two.
        """
        import json
        import shutil
        import tempfile

        from chromiumdiff.enrich import gerrit
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        cls = [{"_number": 100, "subject": "s", "id": "i0",
                "current_revision": "r",
                "submitted": "2026-05-01 00:00:00.000000000"}]

        def finding():
            return Finding(
                change=Change(change_type="modified", kind="base_feature",
                              key="kFoo", name="kFoo", paths=["f.cc"]),
                score=90)

        def row_for(f):
            return html_report._to_rows(
                Report(from_ref="a", to_ref="b", findings=[f]), "windows")[0]

        saved = (gerrit.window_for, gerrit._search_window, gerrit._http_get)
        gerrit.window_for = lambda *a, **k: ("2026-04-06", "2026-06-30",
                                            "2026-08-11")
        gerrit._search_window = lambda *a, **k: ([dict(c) for c in cls], False)
        cache = tempfile.mkdtemp()
        try:
            gerrit._http_get = lambda url, **k: json.dumps(
                {"content": [{"b": ["  kFoo,"]}]}).encode()
            warm = finding()
            gerrit.enrich([warm], "1", "2", cache_dir=cache, with_history=0,
                          log=lambda m: None)
            self.assertIsNone(row_for(warm).get("cl_failed"),
                              "a run that lost nothing must not warn")

            def boom(url, **k):
                raise gerrit.AcquireError("HTTP 500")

            gerrit._http_get = boom
            stale = finding()
            gerrit.enrich([stale], "1", "2", cache_dir=cache, refresh=True,
                          with_history=0, log=lambda m: None)
        finally:
            (gerrit.window_for, gerrit._search_window,
             gerrit._http_get) = saved
            shutil.rmtree(cache, ignore_errors=True)
        served = row_for(stale)
        self.assertTrue(served.get("cls"), "the stale answer is still served")
        self.assertEqual(served.get("cl_failed"), 1,
                         "and it is served without saying it is short")

    def test_a_search_that_could_not_prove_itself_complete_says_so(self):
        """Set by the lookup and read by nobody: `search_incomplete` appeared
        exactly once in the repository, at the line that assigned it. The same
        shape as `candidates_read`, in the commit that fixed
        `candidates_read`. `PROVENANCE_KEYS` is the thread meant to catch
        that, and it only holds if a new key is put on it."""
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        finding = Finding(
            change=Change(change_type="modified", kind="base_feature",
                          key="kFoo", name="kFoo", paths=["f.cc"]), score=90,
            enrichment={"gerrit": {"candidates": 500, "diffs_read": True,
                                   "search_incomplete": True,
                                   "changes": [{"number": 1, "date": "2026-06-01",
                                                "match": "exact", "subject": "s",
                                                "bugs": []}]}})
        row = html_report._to_rows(
            Report(from_ref="a", to_ref="b", findings=[finding]), "windows")[0]
        self.assertTrue(row.get("cl_partial"))
        self.assertIn("cl_partial", html_report.PROVENANCE_KEYS)

    def test_the_lookup_records_the_search_it_could_not_finish(self):
        """Asserted through `enrich`, because the block above is hand-built
        and testing the mapping is not testing the thing that fills it -- the
        same gap this key fell into in the first place."""
        from chromiumdiff.enrich import gerrit
        from chromiumdiff.model import Change, Finding

        cls = [{"_number": 100, "subject": "s",
                "submitted": "2026-05-01 00:00:00.000000000"}]
        finding = Finding(
            change=Change(change_type="modified", kind="base_feature",
                          key="kFoo", name="kFoo", paths=["f.cc"]), score=90)
        saved = (gerrit.window_for, gerrit._search_window, gerrit._diff)
        gerrit.window_for = lambda *a, **k: ("2026-04-06", "2026-06-30",
                                            "2026-08-11")
        # `True` is the search saying it came back at the page cap and cannot
        # prove the window holds nothing more.
        gerrit._search_window = lambda *a, **k: ([dict(c) for c in cls], True)
        gerrit._diff = lambda *a, **k: [("  kFoo,", gerrit.ADDED)]
        try:
            gerrit.enrich([finding], "1", "2", cache_dir="", with_history=0,
                          log=lambda m: None)
        finally:
            (gerrit.window_for, gerrit._search_window, gerrit._diff) = saved
        self.assertTrue(
            finding.enrichment["gerrit"].get("search_incomplete"),
            "the row is served a list the search could not prove complete, "
            "and says nothing about it")

    def test_a_long_cache_key_is_the_same_key_in_the_next_process(self):
        """`_slug` folded a long path with `hash()`, which Python salts per
        process: the same path produced a different filename on every run, so
        the entry could never be read back by anything but the run that wrote
        it. A cache that silently never hits is a cache that is not there.

        Asserted against a constant, which is the whole test: a salted hash
        cannot produce one twice.
        """
        from chromiumdiff.enrich.gerrit import _slug

        long = ("third_party/blink/renderer/modules/" + "x" * 100
                + "/feature.idl")
        self.assertGreater(len(long), 120, "the short branch is not the one "
                                           "under test")
        self.assertEqual(
            _slug(long),
            "third_party_blink_renderer_modules_" + "x" * 65
            + "_ef2405159e66")
        # And a short one is left readable rather than folded at all.
        self.assertEqual(_slug("chrome/browser/about_flags.cc"),
                         "chrome_browser_about_flags.cc")

    def test_a_cl_gerrit_dated_nowhere_does_not_lead_the_list(self):
        """`_neg_date` inverts digits so an ascending sort reads newest
        first, and the empty string sorts before every inverted date -- so a
        CL Gerrit returned without `submitted` or `updated` led every list it
        appeared in, on the strength of knowing nothing about it."""
        from chromiumdiff.enrich.gerrit import _neg_date

        dates = ["2026-04-01", "", "2026-06-01"]
        self.assertEqual(sorted(dates, key=_neg_date),
                         ["2026-06-01", "2026-04-01", ""])

    def test_refresh_fetches_each_diff_once(self):
        """The diffs are warmed in a thread pool and then read back in order.
        Passing `refresh` to both passes fetched every diff twice, so the flag
        cost double and met the rate limiter at half the work.

        Counted at the network boundary rather than at `_get_json`: the two
        passes call that once each by design, and what the fix saves is the
        fetch behind it. So the cache directory is real, and only the HTTP
        call is replaced.
        """
        import json
        import shutil
        import tempfile

        from chromiumdiff.enrich import gerrit
        from chromiumdiff.model import Change, Finding

        urls = []
        cls = [{"_number": 100 + i, "subject": "s", "id": f"i{i}",
                "current_revision": "r",
                "submitted": f"2026-05-{i + 1:02d} 00:00:00.000000000"}
               for i in range(3)]
        finding = Finding(
            change=Change(change_type="modified", kind="base_feature",
                          key="kFoo", name="kFoo", paths=["f.cc"]), score=90)
        saved = (gerrit.window_for, gerrit._search_window, gerrit._http_get)
        gerrit.window_for = lambda *a, **k: ("2026-04-06", "2026-06-30",
                                            "2026-08-11")
        gerrit._search_window = lambda *a, **k: ([dict(c) for c in cls], False)
        gerrit._http_get = lambda url, **k: (
            urls.append(url)
            or json.dumps({"content": [{"b": ["  kFoo,"]}]}).encode())
        cache = tempfile.mkdtemp()
        try:
            gerrit.enrich([finding], "148", "151", cache_dir=cache,
                          refresh=True, with_history=0, workers=1,
                          log=lambda m: None)
        finally:
            (gerrit.window_for, gerrit._search_window,
             gerrit._http_get) = saved
            shutil.rmtree(cache, ignore_errors=True)
        diffs = [u for u in urls if "/diff" in u]
        self.assertEqual(len(diffs), len(cls))
        self.assertEqual(len(diffs), len(set(diffs)),
                         f"a diff was fetched twice: {len(diffs)} requests "
                         f"for {len(set(diffs))} files")

    def test_a_lost_rename_lookup_marks_the_row_it_changed(self):
        """The one fetch whose failure changes the conclusion rather than
        thinning the evidence: `moved` is granted from `_followed`, and
        `_followed` is filled by this request. Lose it and the fact reads as
        deleted at the old path -- the answer the verdict exists to prevent --
        and the row said nothing, because the failure was recorded against no
        file at all."""
        import json
        import shutil
        import tempfile

        from chromiumdiff.enrich import gerrit
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        cls = [{"_number": 100, "subject": "s", "id": "i0",
                "current_revision": "r",
                "submitted": "2026-05-01 00:00:00.000000000"}]
        # Two findings in two files, both losing their rename lookup. The run
        # loses four requests and each row loses two, so a row printing the
        # run's total tells a reader who lost two that it lost four.
        findings = [
            Finding(change=Change(change_type="removed", kind="idl_member",
                                  key=f"Foo{i}.bar", name="bar",
                                  paths=[f"a/old{i}.idl"]), score=90)
            for i in range(2)]

        def http(url, **k):
            if url.endswith("/files/"):
                raise gerrit.AcquireError("HTTP 500")
            return json.dumps(
                {"content": [{"ab": ["interface Foo {};"]}]}).encode()

        saved = (gerrit.window_for, gerrit._search_window, gerrit._http_get)
        gerrit.window_for = lambda *a, **k: ("2026-04-06", "2026-06-30",
                                            "2026-08-11")
        gerrit._search_window = lambda *a, **k: ([dict(c) for c in cls], False)
        gerrit._http_get = http
        cache = tempfile.mkdtemp()
        try:
            gerrit.enrich(findings, "1", "2", cache_dir=cache,
                          with_history=0, log=lambda m: None)
        finally:
            (gerrit.window_for, gerrit._search_window,
             gerrit._http_get) = saved
            shutil.rmtree(cache, ignore_errors=True)
        rows = html_report._to_rows(
            Report(from_ref="a", to_ref="b", findings=findings), "windows")
        for row in rows:
            self.assertTrue(row.get("cl_failed"),
                            "the request that decides `moved` failed and the "
                            "row reports a finished search")
        self.assertEqual(gerrit._failures.count, sum(r["cl_failed"] for r in rows),
                         "each row must count its own losses, not the run's")
        self.assertEqual({r["cl_failed"] for r in rows}, {2})

    def test_a_fact_is_followed_into_the_file_it_was_renamed_into(self):
        """A pure rename changes no line, so no diff of the old path carries
        the evidence -- CL 7810461 renamed `html_or_foreign_element.idl` and
        every member of that interface read as removed at the old path with
        nothing to say so. `moved` exists for exactly that, and it is reached
        only if the rename is followed."""
        from chromiumdiff.enrich import gerrit

        old, new = "a/old.idl", "a/new.idl"
        docs = {old: {"content": [{"ab": ["interface Foo {};"]}]},
                new: {"content": [{"a": ["interface Foo {};"],
                                   "b": ["interface Foo { attribute x; };"]}]}}
        import urllib.parse

        saved = (gerrit._get_json, gerrit._renamed_to)
        gerrit._get_json = lambda url, *a, **k: next(
            (d for p, d in docs.items()
             if urllib.parse.quote(p, safe="") in url), None)
        gerrit._renamed_to = lambda *a, **k: new
        try:
            seq = gerrit._diff({"_number": 1, "id": "x", "current_revision": "r"},
                               old, "", False, lambda m: None)
        finally:
            (gerrit._get_json, gerrit._renamed_to) = saved
        self.assertTrue(any(state for _, state in seq),
                        "the rename was not followed, so `moved` can never "
                        "be reached and the fact reads as deleted")


class TestTheChangeItselfIsTheEvidence(TestProvenanceStopsAtEvidence):
    """The sharpest question is the one the report could already answer.

    Every other verdict asks whether a CL *touched* the thing, which any CL
    that reformatted the file satisfies. A finding does not merely name a
    declaration -- it records that declaration's two states -- so the CL that
    made the change is, by construction, a CL whose diff *adds* a line
    carrying the state the fact ended up in. That question has one answer
    where "who touched this file" has hundreds.
    """

    def _tokens(self, deltas):
        from chromiumdiff.enrich.gerrit import delta_tokens
        from chromiumdiff.model import Change

        return delta_tokens(Change(change_type="modified", kind="mojo_field",
                                   key="k", name="k", deltas=deltas))

    def test_only_the_difference_is_searched_for(self):
        """A value on both sides did not change. Searching for it would match
        every CL that touched the declaration for any reason at all."""
        gained, lost = self._tokens(
            {"type": ["array<url.mojom.Url>", "array<url.mojom.LinkHeader>"]})
        self.assertIn("LinkHeader", gained)
        self.assertNotIn("mojom", gained | lost)
        self.assertNotIn("array", gained | lost)

    def test_a_value_that_is_not_code_is_not_searched_for(self):
        """`enabled`, `stable` and `109` are in every other declaration in the
        file. Shape is the test -- an inner capital, an underscore or a dot --
        or else length, because a long string is specific by being long."""
        gained, _ = self._tokens({"default_state": ["disabled", "enabled"],
                                  "default": ["100", "109"],
                                  "status": ["stable", ""]})
        self.assertEqual(gained, set())

        gained, _ = self._tokens({"var": ["kPreinstalledApps",
                                          "kPreinstalledExtensions"],
                                  "conditions": [[], ["IS_ANDROID"]]})
        self.assertIn("kPreinstalledExtensions", gained)
        self.assertIn("IS_ANDROID", gained)

    def test_a_long_construct_is_reached_through_the_words_it_gained(self):
        """A Mojo signature spans several lines of the file, so it is never a
        substring of one. The words it gained are."""
        gained, _ = self._tokens({"params": [
            "pending_remote<Client> client",
            "pending_remote<Client> client, pending_remote<DownloadObserver>?"
            " monitor"]})
        self.assertIn("DownloadObserver", gained)
        # And the whole signature is not offered as a line to search for.
        self.assertFalse(any(" " in t for t in gained))

    # -- and what the verdict then requires of a diff ------------------------

    DELTA = {"type": ["gfx.mojom.Vector2d", "gfx.mojom.Vector2dF"]}

    def _hit(self, seq, **kw):
        from chromiumdiff.enrich import gerrit

        return gerrit._match(
            gerrit._Scanned(seq),
            tokens={"border_offset"},
            **{"gained": self._tokens(self.DELTA)[0],
               "lost": self._tokens(self.DELTA)[1], **kw})

    def test_the_cl_that_added_the_value_is_the_one_named(self):
        from chromiumdiff.enrich.gerrit import ADDED

        self.assertEqual(
            self._hit([("  gfx.mojom.Vector2dF border_offset;", ADDED)]),
            "introduced")

    def test_the_side_the_value_landed_on_decides(self):
        """A CL that *removes* a line carrying the fact's new value is not the
        CL that introduced it -- it is closer to the opposite.

        Written so the line-level check has to be the thing that decides. An
        unrelated added line satisfies the cheap pre-filter, so a rule that
        only asked "did this value appear anywhere on either side" would pass
        here, and did.
        """
        from chromiumdiff.enrich import gerrit
        from chromiumdiff.enrich.gerrit import ADDED, REMOVED

        gained, lost = self._tokens({"type": ["Vector2d", "PointF"]})
        self.assertEqual((gained, lost), ({"PointF"}, {"Vector2d"}))
        verdict = gerrit._match(
            gerrit._Scanned([("  PointF unrelated_field;", ADDED),
                             ("  PointF border_offset;", REMOVED)]),
            tokens={"border_offset"}, gained=gained, lost=lost)
        self.assertNotEqual(verdict, "introduced")
        # It is still a CL that changed the line, which is what `exact` says.
        self.assertEqual(verdict, "exact")

    def test_removing_the_old_value_is_the_same_event(self):
        """The other direction does count. A CL that took the before-state out
        of this declaration performed the transition the finding records, and
        for a removal there is no after-state to add."""
        from chromiumdiff.enrich import gerrit
        from chromiumdiff.enrich.gerrit import REMOVED

        gained, lost = self._tokens({"type": ["Vector2d", "PointF"]})
        self.assertEqual(gerrit._match(
            gerrit._Scanned([("  Vector2d border_offset;", REMOVED)]),
            tokens={"border_offset"}, gained=gained, lost=lost), "introduced")

    def test_a_verdict_nobody_knows_ranks_below_the_ones_we_do(self):
        """There were three defaults for this one lookup: `_prune` sorted an
        unknown verdict last, `enrich` indexed the table and would have raised,
        and the markdown report defaulted to zero -- the strongest rank there
        is -- so an unrecognised verdict printed as a citation."""
        from chromiumdiff.enrich.gerrit import CITES, _STRENGTH, strength

        self.assertGreater(strength("bogus"), max(_STRENGTH.values()))
        self.assertGreaterEqual(strength("bogus"), CITES)
        for known in _STRENGTH:
            self.assertLess(strength(known), strength("bogus"))

    def test_the_value_must_land_inside_this_declaration(self):
        """Present in the diff is not present in the declaration. A file of
        nothing but declarations always carries the type name somewhere."""
        from chromiumdiff.enrich.gerrit import ADDED, CONTEXT

        self.assertNotEqual(
            self._hit([("  gfx.mojom.Vector2dF something_else;", ADDED),
                       ("  gfx.mojom.Vector2d border_offset;", CONTEXT)]),
            "introduced")

    def test_it_outranks_every_other_verdict(self):
        """It is the only one whose answer is the change rather than a
        neighbour of it, so nothing may sort above it."""
        from chromiumdiff.enrich.gerrit import _STRENGTH

        self.assertEqual(min(_STRENGTH, key=_STRENGTH.get), "introduced")
        self.assertLess(_STRENGTH["introduced"], _STRENGTH["exact"])


class TestADeltaHasToShowTheDelta(unittest.TestCase):
    """The emptiest line the report ever printed, and why no care downstream
    could have saved it.

    Both sides of a delta were shortened from their own start. A Mojo method
    that gains a parameter keeps every character of its old signature, so the
    first 90 of each side were the same 90 characters and the cell rendered
    two copies of one string -- on five consecutive rows of a real M148 ->
    M151 report, in the What column and again in the detail panel. The
    difference was gone before anything that formats it was reached.
    """

    SIG = ("CreateLanguageModel(pending_remote<AIManagerCreateLanguageModel"
           "Client> client, AILanguageModelCreateOptions options")

    def test_two_sides_sharing_a_prefix_do_not_come_out_equal(self):
        from chromiumdiff.report.html import _trim_pair

        old, new = _trim_pair(self.SIG + ")",
                              self.SIG + ", pending_remote<on_device_model."
                                         "mojom.DownloadObserver>? monitor)")
        self.assertNotEqual(old, new, "a delta may not render as one string "
                                      "printed twice")
        self.assertIn("DownloadObserver", new)
        self.assertNotIn("DownloadObserver", old)

    def test_what_the_change_did_is_written_with_the_marks_already_in_use(self):
        """One side empty is an addition or a removal, not an arrow out of
        nothing. `DeviceAttributeResult result →` trailed into a blank."""
        from chromiumdiff.report.html import _delta_pair

        self.assertEqual(_delta_pair("DeviceAttributeResult result", "", 34),
                         "\u2212 DeviceAttributeResult result")
        self.assertEqual(_delta_pair("", "NewThing x", 34), "+ NewThing x")
        pair = _delta_pair(self.SIG + ")",
                           self.SIG + ", pending_remote<X>? monitor)", 34)
        self.assertTrue(pair.startswith("+ "), pair)
        self.assertIn("monitor", pair)

    def test_the_payload_itself_carries_the_difference(self):
        """Asserted through `_to_rows` rather than on the helper, because the
        helper was never the thing that was wrong -- the call site was. The
        payload is where the two sides became equal, and every reader of it
        downstream inherited that."""
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        finding = Finding(
            change=Change(change_type="modified", kind="mojo_method",
                          key="blink.mojom.AIManager.CreateLanguageModel",
                          name="CreateLanguageModel", paths=["ai.mojom"],
                          deltas={"signature": [
                              self.SIG + ")",
                              self.SIG + ", pending_remote<on_device_model."
                                         "mojom.DownloadObserver>? monitor)"]}),
            score=80)
        row = html_report._to_rows(
            Report(from_ref="a", to_ref="b", findings=[finding]), "windows")[0]
        key, old, new = row["deltas"][0]
        self.assertEqual(key, "signature")
        self.assertNotEqual(old, new,
                            "the payload may not hand both sides the same "
                            "string; nothing downstream can recover from it")
        self.assertIn("DownloadObserver", new)
        self.assertNotIn("DownloadObserver", old)
        # And the one-line form in the What column says what was added.
        self.assertTrue(row["moved"].startswith("+ "), row["moved"])

    def test_a_short_pair_is_left_alone(self):
        from chromiumdiff.report.html import _delta_pair, _trim_pair

        self.assertEqual(_trim_pair("100", "109"), ("100", "109"))
        self.assertEqual(_delta_pair("100", "109", 34), "100 → 109")


class TestThePanelSaysWhatTheReaderCannotSee(unittest.TestCase):
    """Three things the page has to state rather than leave to be inferred.

    Each replaced something the reader was expected to work out: why a link
    will not open, that a category colour is a category and not a shade, and
    that a row nobody read can still be read.
    """

    def _page(self):
        from chromiumdiff.model import Report
        from chromiumdiff.report import html as html_report

        return html_report.render(Report(from_ref="a", to_ref="b"))

    def test_the_triage_is_read_in_severity_order(self):
        """The order down the page is the reader's working order, and it is
        the one thing worth encoding about four counts.

        Asserted with housekeeping largest and breaking smallest, so ordering
        by count and ordering by severity give opposite answers. A summary
        that sorted itself by size would put the bucket you look at last at
        the top.
        """
        import re

        from chromiumdiff.model import BUCKET_ORDER, Change, Finding, Report
        from chromiumdiff.report import html as html_report

        sizes = {"breaking": 1, "behaviour": 2, "new": 4, "housekeeping": 8}
        findings = [
            Finding(change=Change(change_type="modified", kind="base_feature",
                                  key=f"{bucket}/{i}", name=f"k{i}",
                                  paths=["f.cc"]),
                    score=10, bucket=bucket)
            for bucket, n in sizes.items() for i in range(n)]
        page = html_report.render(Report(from_ref="a", to_ref="b",
                                         findings=findings), "windows")

        rows = re.findall(r'data-set="fb:(\w+)"[^>]*>\s*<span class="n">'
                          r'([\d,]+)</span>', page)
        self.assertEqual([b for b, _ in rows], list(BUCKET_ORDER),
                         "the largest bucket may not float to the top")
        self.assertEqual(dict(rows)["housekeeping"], "8")
        self.assertEqual(dict(rows)["breaking"], "1")


class TestALookupAlwaysAnswers(unittest.TestCase):
    """Clicking a row returns a CL whenever one could exist.

    The stage began by refusing to answer unless the diff named the fact, and
    that refusal is the reason it can be trusted. But a reader clicking "Look
    up the CL for this row" has asked a question, and five separate paths
    answered it with silence: a token too short to search for, a budget that
    declined the file, a crowd of equally plausible CLs, a diff that matched
    nothing, and a finding whose name is not written anywhere. In four of the
    five the CLs that could have made the change were already in hand.

    So the ladder gained a floor that names no fact and says so. What is left
    is one shape, asserted at the bottom of this class: no CL touched the
    declaring file inside the window, where there is genuinely nothing to
    cite. Everything above it answers.
    """

    WINDOW = ("2026-04-06", "2026-06-30", "2026-08-11")

    # A declaration whose name line is untouched and whose body is edited --
    # the Mojo parameter-list shape, which reads as `declares`.
    BODY_EDITED = [("  kFoo(", False), ("    a,", True), ("    b);", False)]
    # Nothing to do with the finding.
    UNRELATED = [("  kOther;", True)]

    @staticmethod
    def _cls(count, first, subject):
        return [{"_number": first + i, "subject": f"{subject} {first + i}",
                 "submitted": f"2026-05-{10 + i:02d} 00:00:00.000000000"}
                for i in range(count)]

    def _enrich(self, *, pool=3, diff=None, budget=0, paths=("f.cc",),
                key="kFoo", name=None, kind="base_feature", subject="CL",
                off_main=0, message=0, deltas=None):
        """`enrich` over one finding with the network replaced.

        Driven through the real entry point rather than `_prune`, because the
        guarantee is about what a lookup returns and most of the silent paths
        are in `enrich` and not in the ranking.

        `pool` is what the file search finds on main, `off_main` what it finds
        once the branch pin comes off, and `message` what a search of commit
        messages returns. Every one of the three is a separate question, and
        the tests below turn them on one at a time.
        """
        from chromiumdiff.enrich import gerrit
        from chromiumdiff.model import Change, Finding

        finding = Finding(
            change=Change(change_type="modified", kind=kind, key=key,
                          name=key if name is None else name,
                          paths=list(paths), deltas=dict(deltas or {})),
            score=90)
        on_main = self._cls(pool, 100, subject)
        branched = self._cls(off_main, 300, subject)
        # A message search only ever returns CLs whose text carries the token;
        # a fixture that did otherwise would test a filter Gerrit applies.
        named = self._cls(message, 500, f"Remove {key} from")

        def search(path, a, b, *rest, **kw):
            # (cache_dir, refresh, log, depth, branch) follow the three named
            # above, so branch is the fifth when it is passed positionally.
            branch = kw.get("branch", rest[4] if len(rest) > 4 else True)
            return [dict(r) for r in (on_main if branch else branched)], False

        saved = (gerrit.window_for, gerrit._search_window, gerrit._diff,
                 gerrit._page)
        gerrit.window_for = lambda *a, **k: self.WINDOW
        gerrit._search_window = search
        gerrit._page = lambda *a, **k: [dict(r) for r in named]
        gerrit._diff = lambda cl, path, *a, **k: (
            diff(cl, path) if callable(diff) else (diff or self.UNRELATED))
        try:
            summary = gerrit.enrich([finding], "148", "151", cache_dir="",
                                    budget=budget, with_history=0,
                                    log=lambda m: None)
        finally:
            (gerrit.window_for, gerrit._search_window, gerrit._diff,
             gerrit._page) = saved
        return (finding.enrichment.get("gerrit") or {}), summary

    def test_asking_for_no_issue_history_asks_for_none_of_it(self):
        """`with_history=0` is a ceiling of nothing, not the absence of one.

        It used to mean "fetch every issue", because the guard was truthiness
        rather than `is not None` -- so `serve`, which defers issue history to
        a click, would have paid for every issue on the row while showing
        none of them. `None` is the way to say "no limit".
        """
        from chromiumdiff.enrich import gerrit
        from chromiumdiff.model import Change, Finding

        cl = {"_number": 100, "subject": "CL 100",
              "submitted": "2026-05-10 00:00:00.000000000",
              "revisions": {"r": {"commit": {
                  "message": "CL 100\n\nBug: 500975618\n"}}}}
        finding = Finding(
            change=Change(change_type="modified", kind="base_feature",
                          key="kFoo", name="kFoo", paths=["f.cc"]), score=90)
        asked = []
        saved = (gerrit.window_for, gerrit._search_window, gerrit._diff,
                 gerrit._page, gerrit.issue_history, gerrit.issue_meta)
        gerrit.window_for = lambda *a, **k: self.WINDOW
        gerrit._search_window = lambda *a, **k: ([dict(cl)], False)
        gerrit._page = lambda *a, **k: []
        gerrit._diff = lambda *a, **k: [("  kFoo;", True)]
        gerrit.issue_history = lambda i, *a, **k: asked.append(i) or []
        gerrit.issue_meta = lambda i, *a, **k: asked.append(i) or {"public": True}
        try:
            gerrit.enrich([finding], "148", "151", cache_dir="", budget=0,
                          with_history=0, log=lambda m: None)
            block = finding.enrichment["gerrit"]
            # The footer still reaches the row: it is free in the search
            # response, and it is what the chip on the CL is built from.
            self.assertEqual([b["id"] for b in block["changes"][0]["bugs"]],
                             ["500975618"])
            self.assertEqual(asked, [])
            self.assertFalse(block.get("issues"))

            finding.enrichment = {}
            gerrit.enrich([finding], "148", "151", cache_dir="", budget=0,
                          with_history=None, log=lambda m: None)
            self.assertEqual(asked, ["500975618", "500975618"])
        finally:
            (gerrit.window_for, gerrit._search_window, gerrit._diff,
             gerrit._page, gerrit.issue_history, gerrit.issue_meta) = saved

    # -- the four paths that used to end in silence -------------------------

    def test_a_crowded_declaration_answers_with_the_crowd(self):
        """Eleven CLs edited the declaration and none of them is the answer.

        `ai_manager.mojom`. Dropping them was the honest reading of "these do
        not identify anything" and it is still what the badge says; the row no
        longer goes empty over it.
        """
        from chromiumdiff.enrich import gerrit

        block, _ = self._enrich(pool=gerrit.DECL_MAX + 2, diff=self.BODY_EDITED)
        self.assertEqual(len(block["changes"]), gerrit.DECL_MAX + 2)
        self.assertEqual({c["match"] for c in block["changes"]}, {"crowded"})

    def test_a_history_reads_forward(self):
        """Every other list here is newest-first, because a citation is the
        last word on a line. This one is not a citation -- it is the sequence
        the declaration passed through to reach the state the report found --
        and a history read backwards is not a history."""
        from chromiumdiff.enrich import gerrit

        block, _ = self._enrich(pool=gerrit.DECL_MAX + 2, diff=self.BODY_EDITED)
        dates = [c["date"] for c in block["changes"]]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual({c["match"] for c in block["changes"]}, {"crowded"})

    def test_a_diff_that_matches_nothing_falls_back_to_the_file(self):
        """"No CL among the 13 read of the 13 that touched this file edits a
        line carrying this identifier" is true and leaves the reader exactly
        where they started. The 13 are still the only candidates there are."""
        from chromiumdiff.enrich import gerrit

        block, _ = self._enrich(pool=5, diff=self.UNRELATED)
        self.assertEqual({c["match"] for c in block["changes"]}, {"touched"})
        self.assertEqual(len(block["changes"]), gerrit.TOUCHED_MAX)
        # Newest first: the fallback offers leads, so recency is all it has.
        self.assertEqual([c["number"] for c in block["changes"]],
                         [104, 103, 102])

    def test_a_file_the_budget_declined_still_answers(self):
        """The candidate list arrives with the search; only the diffs are
        budgeted. A file nobody read is exactly the file with nothing else."""
        block, _ = self._enrich(pool=5, budget=1)
        self.assertFalse(block["diffs_read"])
        self.assertEqual({c["match"] for c in block["changes"]}, {"touched"})

    def test_a_name_too_short_to_search_for_still_answers(self):
        """`url`, `id`, `name`: under four characters the token set is empty
        and the diff loop skips the finding entirely."""
        from chromiumdiff.enrich.gerrit import container_for, tokens_for
        from chromiumdiff.model import Change

        change = Change(change_type="modified", kind="mojo_field", key="url",
                        name="url", paths=["f.mojom"])
        self.assertEqual(tokens_for(change), set())
        self.assertEqual(container_for(change), "")

        block, _ = self._enrich(pool=4, key="url", kind="mojo_field")
        self.assertEqual({c["match"] for c in block["changes"]}, {"touched"})

    # -- and the floor never rises above the evidence ------------------------

    def test_evidence_that_names_the_fact_retires_every_lead(self):
        """The floor is reached only when everything above it is empty. If it
        could sit beside an `exact` hit it would be noise on the rows that are
        actually answered, which is most of them."""
        block, _ = self._enrich(pool=4, diff=lambda cl, path: (
            [("  kFoo,", True)] if cl["_number"] == 101 else self.UNRELATED))
        self.assertEqual([c["match"] for c in block["changes"]], ["exact"])
        self.assertEqual([c["number"] for c in block["changes"]], [101])

    def test_a_lead_never_outranks_a_weaker_verdict_that_names_the_fact(self):
        """`described` is the weakest verdict that names the fact, and it is
        still stronger than any number of leads."""
        from chromiumdiff.enrich import gerrit

        block, _ = self._enrich(pool=6, subject="Rename kFoo to kBar")
        self.assertEqual({c["match"] for c in block["changes"]}, {"described"})
        self.assertLess(gerrit._STRENGTH["described"], gerrit.CITES)

    def test_a_lead_is_not_counted_as_a_finding_that_was_explained(self):
        """The summary is what a run reports about itself; leads must not
        inflate it, or the guarantee becomes a way to look finished."""
        block, summary = self._enrich(pool=3, diff=self.UNRELATED)
        self.assertEqual({c["match"] for c in block["changes"]}, {"touched"})
        self.assertEqual(summary["findings_resolved"], 0)
        self.assertEqual(summary["findings_leads_only"], 1)

        _, real = self._enrich(pool=3, diff=[("  kFoo,", True)])
        self.assertEqual(real["findings_resolved"], 1)
        self.assertEqual(real["findings_leads_only"], 0)

    # -- the boundary, stated -----------------------------------------------

    # -- and when the file itself leads nowhere -----------------------------

    def test_each_scope_asks_gerrit_a_different_question(self):
        """Asserted on the query string, because everything else here stubs
        the search. Widening that never reaches the wire would leave every
        test in this class passing and the tool unchanged."""
        from chromiumdiff.enrich import gerrit

        pinned = gerrit._query("a/b.cc", "2026-04-06", "2026-08-11")
        self.assertIn('file:"a/b.cc"', pinned)
        self.assertIn("branch:main", pinned)

        widened = gerrit._query("a/b.cc", "2026-04-06", "2026-08-11",
                                branch=False)
        self.assertIn('file:"a/b.cc"', widened)
        self.assertNotIn("branch:main", widened)

        message = gerrit._query('(message:"kFoo")', "2026-04-06", "2026-08-11",
                                "raw", False)
        self.assertIn('(message:"kFoo")', message)
        self.assertNotIn("file:", message)
        self.assertNotIn("branch:main", message)
        for q in (pinned, widened, message):
            self.assertIn("status:merged", q)
            self.assertIn("mergedafter:2026-04-06", q)
            self.assertIn("mergedbefore:2026-08-11", q)

    def test_a_widened_search_does_not_read_the_pinned_ones_cache(self):
        """Same file, same window, different question, different answer. The
        key carried only the path, so the second search would have been served
        the first one's empty list."""
        from chromiumdiff.enrich import gerrit

        seen = []
        real = gerrit._get_json
        gerrit._get_json = lambda url, cache, key, **k: seen.append(key) or []
        try:
            gerrit._page("a/b.cc", "2026-04-06", "2026-08-11", 0, "", False,
                         lambda m: None)
            gerrit._page("a/b.cc", "2026-04-06", "2026-08-11", 0, "", False,
                         lambda m: None, "file", False)
        finally:
            gerrit._get_json = real
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0], seen[1])


    def test_a_file_with_nothing_on_main_is_asked_again_off_it(self):
        """Six weeks of merge-backs land on the release branch after it is
        cut, and they are in the tree being compared. The window already
        admitted their dates; `branch:main` was the only thing hiding them."""
        block, _ = self._enrich(pool=0, off_main=3)
        self.assertEqual(block["candidates"], 3)
        self.assertTrue(block["changes"])
        self.assertEqual([c["number"] for c in block["changes"]],
                         [302, 301, 300])

    def test_the_branch_pin_stays_on_while_main_answers(self):
        """Widening is a weaker search, so it is reached and not preferred: a
        file with CLs on main must never see the unpinned list."""
        block, _ = self._enrich(pool=2, off_main=3)
        self.assertEqual(block["candidates"], 2)
        self.assertTrue(all(c["number"] < 300 for c in block["changes"]))

    def test_a_fact_whose_file_was_never_touched_is_asked_of_the_tree(self):
        """The case that says the file question is the wrong one.

        A declaration generated from a template, a path Gerrit records under
        another name, a `.idl` arriving by a third-party roll: nothing landed
        on the file, and yet something landed. The author's own words are the
        remaining way to it, and what comes back is `described` because that
        is exactly what it is.
        """
        block, summary = self._enrich(pool=0, off_main=0, message=2)
        self.assertEqual({c["match"] for c in block["changes"]}, {"described"})
        self.assertEqual(block["found_by"], "message")
        self.assertEqual(summary["findings_by_message"], 1)
        # A citation, not a lead: it is counted as a finding that was
        # explained, because the CL names the thing.
        self.assertEqual(summary["findings_resolved"], 1)

    def test_the_tree_is_asked_only_after_the_file_has_failed_completely(self):
        """One unscoped request per unanswered finding is affordable only
        because it is rare. A file with candidates has already been searched
        properly, and its own CLs are the better leads."""
        block, summary = self._enrich(pool=4, diff=self.UNRELATED, message=2)
        self.assertEqual({c["match"] for c in block["changes"]}, {"touched"})
        self.assertNotIn("found_by", block)
        self.assertEqual(summary["findings_by_message"], 0)

    # -- the boundary, restated ---------------------------------------------

    def test_what_is_left_is_a_search_that_missed_not_a_change_without_a_cl(self):
        """The correction this class exists to record.

        There is no such thing as a fact that changed without a CL: the two
        trees differ, so something landed. Every empty row here is a statement
        about this search -- the file was never touched under the name we hold,
        the identifier is spelled differently in the message index, the window
        is wrong -- and never about Chromium. The summary keeps the count so
        the run says how often it failed rather than implying it cannot.
        """
        block, summary = self._enrich(pool=0, off_main=0, message=0)
        self.assertNotIn("changes", block)
        self.assertEqual(block["candidates"], 0)
        self.assertEqual(summary["findings_by_message"], 0)
        self.assertEqual(summary["findings_leads_only"], 0)

    def test_every_other_shape_answers(self):
        """The guarantee itself, over the shapes that reach it.

        Written as one sweep rather than trusting the cases above to have
        covered the product: what matters is that no combination of pool size,
        diff shape and budget produces an empty row while a candidate exists.
        """
        from chromiumdiff.enrich import gerrit

        diffs = {"nothing matches": self.UNRELATED,
                 "declaration edited": self.BODY_EDITED,
                 "line edited": [("  kFoo,", True)],
                 "empty diff": []}
        for pool in (1, 2, gerrit.DECL_MAX + 2, 9):
            for label, diff in diffs.items():
                for budget in (0, 1):
                    with self.subTest(pool=pool, diff=label, budget=budget):
                        block, _ = self._enrich(pool=pool, diff=diff,
                                                budget=budget)
                        self.assertTrue(
                            block.get("changes"),
                            f"{pool} candidate CLs and no answer")
                        for change in block["changes"]:
                            self.assertIn(change["match"], gerrit._STRENGTH)


class TestALeadIsNeverPrintedAsACitation(unittest.TestCase):
    """The guarantee is only worth having if the weak end reads as weak.

    Every path added above returns CLs that name nothing, and the failure mode
    of all of them is the same: a reader skims three subject lines under "Why
    it changed" and takes the first as the answer. So the page separates them
    from evidence in three independent places -- the row's state, the badge,
    and a sentence above the list -- and this is what holds all three.
    """

    def _row(self, match):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report.html import _to_rows

        report = Report(
            from_ref="a", to_ref="b", summary={}, meta={"platform": "windows"},
            findings=[Finding(
                change=Change(change_type="modified", kind="base_feature",
                              key="kFoo", name="kFoo", paths=["f.cc"]),
                score=90,
                enrichment={"gerrit": {
                    "candidates": 9, "diffs_read": True,
                    "changes": [{"number": 1, "date": "2026-06-01",
                                 "match": match, "subject": "s",
                                 "bugs": []}]}})])
        return _to_rows(report, "windows")[0]

    def test_the_payload_carries_the_verdict_the_scan_reached(self):
        for match in ("exact", "declares", "crowded", "touched"):
            self.assertEqual(self._row(match)["cls"][0]["m"], match)

    def test_the_page_sorts_leads_into_their_own_state(self):
        """`weak` rather than a corner of `cl`: a reader filtering for rows
        that are explained must not be handed rows that merely list
        candidates."""
        from chromiumdiff.report import html as html_report

        from chromiumdiff.model import Report

        page = html_report.render(Report(from_ref="a", to_ref="b"))
        self.assertIn("var WEAK={crowded:1,touched:1}", page)
        self.assertIn("if(allWeak(f))return 'weak'", page)
        self.assertIn('<option value="weak"', page)

    def test_the_disclaimer_is_prose_and_not_only_a_badge(self):
        """A badge reading `touched` is true and easy to skim past, and the
        reader who opened the row is owed the sentence before the list.

        The two weak verdicts get different sentences because they are not the
        same claim. `touched` is a lead and says so. `crowded` is every CL that
        edited the declaration, which is that declaration's history -- so it is
        headed as one, ordered forward, and never called a citation either."""
        from chromiumdiff.model import Report
        from chromiumdiff.report import html as html_report

        page = html_report.render(Report(from_ref="a", to_ref="b"))
        self.assertIn("Leads, not ", page)
        self.assertIn("No CL mentions this identifier", page)
        self.assertIn("No one CL singles this out", page)
        self.assertIn("how it reached the state above", page)
        self.assertIn("How it got here", page)

    def test_the_markdown_report_says_it_too(self):
        """`report.md` has no badge colour, no row state and no panel. The
        line a reader copies into a ticket is the whole of what travels, so
        the heading carries the disclaimer there."""
        from chromiumdiff.model import BUCKET_BREAKING, Change, Finding, Report
        from chromiumdiff.report import markdown as md

        def rendered(match):
            report = Report(
                from_ref="a", to_ref="b", summary={},
                meta={"platform": "windows"},
                findings=[Finding(
                    change=Change(change_type="modified", kind="base_feature",
                                  key="kFoo", name="kFoo", paths=["f.cc"]),
                    score=90, bucket=BUCKET_BREAKING,
                    enrichment={"gerrit": {
                        "candidates": 9, "diffs_read": True,
                        "changes": [{"number": 7700001, "date": "2026-06-01",
                                     "match": match, "subject": "s",
                                     "bugs": []}]}})])
            return md.render(report, "windows")

        # Neither weak verdict may wear the heading a citation wears, and the
        # two do not share one: `touched` is a lead, `crowded` is the
        # declaration's history and is ordered to be read as one.
        for weak, heading in (("crowded", "How it got here, oldest first"),
                              ("touched", "Leads only, no CL names this")):
            page = rendered(weak)
            self.assertIn(heading, page)
            self.assertNotIn("- Why it changed", page)
            self.assertIn("CL 7700001", page)
        for strong in ("exact", "moved", "declares", "described"):
            page = rendered(strong)
            self.assertIn("- Why it changed", page)
            self.assertNotIn("Leads only", page)

    def test_an_empty_row_blames_the_search_and_not_the_change(self):
        """The page must never say a change has no CL.

        The two trees differ, so something landed. An empty row is a fact
        about three questions this run asked and missed -- the file on main,
        the file on any branch, the commit messages -- and saying otherwise
        invites a reader to conclude Chromium changed on its own.
        """
        from chromiumdiff.model import Report
        from chromiumdiff.report import html as html_report

        page = html_report.render(Report(from_ref="a", to_ref="b"))
        self.assertIn("This lookup found nothing", page)
        # Asserted within one JS literal: the sentence is assembled from
        # several and no phrase crossing a `+` exists in the file.
        self.assertIn("is recorded under something other than the name", page)
        for absence in ("nothing to cite", "there is no CL"):
            self.assertNotIn(absence, page)

    def test_a_cl_found_by_its_message_does_not_borrow_the_files_denominator(self):
        """"3 of 62 merged CLs touched this file" is a claim about the file
        search. A CL reached by its commit message was not in that 62 and
        printing it there would invent a count nobody measured."""
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report

        report = Report(
            from_ref="a", to_ref="b", summary={}, meta={"platform": "windows"},
            findings=[Finding(
                change=Change(change_type="modified", kind="base_feature",
                              key="kFoo", name="kFoo", paths=["f.cc"]),
                score=90,
                enrichment={"gerrit": {
                    "candidates": 0, "diffs_read": False,
                    "found_by": "message",
                    "changes": [{"number": 1, "date": "2026-06-01",
                                 "match": "described", "subject": "s",
                                 "bugs": []}]}})])
        row = html_report._to_rows(report, "windows")[0]
        self.assertTrue(row["cl_by_message"])
        self.assertIn("cl_by_message", html_report.PROVENANCE_KEYS)

        page = html_report.render(Report(from_ref="a", to_ref="b"))
        self.assertIn("found by commit message", page)


class TestClickingARowThroughTheServerAnswers(unittest.TestCase):
    """The guarantee at the surface the user actually touches.

    `enrich` is what the tests above drive; `serve` is what the button calls,
    with `top=1` and its own budget, and it returns a filtered subset of the
    renderer's keys. A floor in the enricher that the lookup response drops on
    the way out would be no floor at all.
    """

    def _state(self, budget):
        from chromiumdiff.model import Change, Finding, Report
        from chromiumdiff.report import html as html_report
        from chromiumdiff import serve as serve_mod

        report = Report(from_ref="a", to_ref="b", summary={},
                        meta={"platform": "windows"},
                        findings=[Finding(
                            change=Change(change_type="modified",
                                          kind="base_feature", key="kFoo",
                                          name="kFoo", paths=["f.cc"]),
                            score=90)])
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh)
        with open(os.path.join(tmp, "report.html"), "w", encoding="utf-8") as fh:
            fh.write(html_report.render(report))
        return serve_mod._State(tmp, tempfile.mkdtemp(), budget=budget)

    def _resolve(self, budget=1, pool=5, state=None):
        from chromiumdiff.enrich import gerrit

        state = state or self._state(budget)
        rows = [{"_number": 200 + i, "subject": f"CL {200 + i}",
                 "submitted": f"2026-05-{10 + i:02d} 00:00:00.000000000"}
                for i in range(pool)]
        saved = (gerrit.window_for, gerrit._search_window, gerrit._diff)
        gerrit.window_for = lambda *a, **k: ("2026-04-06", "2026-06-30",
                                            "2026-08-11")
        gerrit._search_window = lambda *a, **k: ([dict(r) for r in rows], False)
        gerrit._diff = lambda *a, **k: [("  kOther;", True)]
        try:
            return state.resolve(state.report.findings[0].uid)
        finally:
            gerrit.window_for, gerrit._search_window, gerrit._diff = saved

    def test_the_button_comes_back_with_a_cl(self):
        payload = self._resolve()
        self.assertTrue(payload["cls"])
        self.assertEqual({c["m"] for c in payload["cls"]}, {"touched"})

    def test_the_answer_still_says_the_diffs_were_not_read(self):
        """Answering is not the same as having looked, and the row has to keep
        saying which -- a lead offered as though the scan had run would be the
        confident wrong answer this stage exists to avoid."""
        payload = self._resolve(budget=1)
        self.assertTrue(payload["no_diffs"])
        self.assertEqual(payload["cl_pool"], 5)

    def test_the_lead_survives_the_round_trip_to_disk(self):
        """A resolved row is written back so a session's clicking is not lost,
        and the floor has to reach the file and not only the response --
        otherwise a reopened report is silent again on every row the floor
        answered."""
        from chromiumdiff import serve as serve_mod

        state = self._state(budget=1)
        self.assertTrue(self._resolve(state=state)["cls"])

        reopened = serve_mod._State(state.directory, tempfile.mkdtemp(),
                                    budget=1)
        changes = (reopened.report.findings[0]
                   .enrichment["gerrit"]["changes"])
        self.assertEqual({c["match"] for c in changes}, {"touched"})
        # And the page it re-renders carries them, so a reader who never
        # clicks again still sees what the last session found.
        self.assertIn(b'"touched"', reopened.page())


class TestPrintedCommandsExist(unittest.TestCase):
    """A command the project shows a reader has to be one the CLI accepts.

    Three names reached users that the tool never had: `--gerrit-max-cls`,
    `--gerrit-issues` and a `why` subcommand. Each was written into a docstring
    or a warning, each read as an instruction, and each sent whoever followed it
    into an argparse error. Nothing checked them, because the check needs the
    parser and the prose in the same place, which no single test had been.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SKIP = {".git", ".chromiumdiff-cache", "out", "__pycache__", "node_modules"}
    # How the project writes a command: run it, or quote it in backticks.
    COMMAND = re.compile(r"(?:python3 -m chromiumdiff|`chromiumdiff)\s+([a-z]+)"
                         r"((?:\s+[^`\n|)]*)?)")
    # A command longer than a line is still one command. Shell wraps with a
    # backslash; Python wraps by putting the next piece of the string on the
    # next line. Scanning raw lines reads `--format both` as belonging to
    # nothing, which is how a fake flag on a continuation line survived.
    SHELL_WRAP = re.compile(r"\\\s*$")
    STRING_ENDS = re.compile(r"[\"']\s*$")
    STRING_OPENS = re.compile(r"^\s*[frbu]*[\"']")
    PLACEHOLDER = re.compile(r"\{[^{}]*\}")

    # Inside a fenced block the prefix is often dropped, because the block
    # already says it is a shell. Prose never does that, so a fence is what
    # separates `chromiumdiff figures ...` the command from "chromiumdiff does".
    FENCE = re.compile(r"^\s*```")
    BARE = re.compile(r"^(\s*\$?\s*)chromiumdiff(\s+[a-z]+)")

    def _logical_lines(self, path, text):
        """Yield (line number, command text) with wrapped lines put back."""
        lines = text.splitlines()
        python = path.endswith(".py")
        fenced = False
        i = 0
        while i < len(lines):
            start, buf = i, lines[i]
            if self.FENCE.match(buf):
                fenced = not fenced
            elif fenced:
                buf = self.BARE.sub(r"\1python3 -m chromiumdiff\2", buf, count=1)
            while i + 1 < len(lines):
                nxt = lines[i + 1]
                if self.SHELL_WRAP.search(buf):
                    buf = self.SHELL_WRAP.sub(" ", buf) + nxt.strip()
                elif (python and self.STRING_ENDS.search(buf)
                        and self.STRING_OPENS.match(nxt)):
                    buf = (self.STRING_ENDS.sub("", buf)
                           + self.STRING_OPENS.sub("", nxt))
                else:
                    break
                i += 1
            if python:
                # `{os.path.join(...)}` is an argument, not a flag, and the
                # brackets in it would end the scan early.
                buf = self.PLACEHOLDER.sub("X", buf)
            yield start + 1, buf
            i += 1

    def _texts(self):
        for dirpath, dirnames, filenames in os.walk(self.ROOT):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP]
            for name in filenames:
                if not name.endswith((".py", ".md", ".html")):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8") as fh:
                        yield os.path.relpath(path, self.ROOT), fh.read()
                except (UnicodeDecodeError, OSError):
                    continue

    def _parser_shape(self):
        import argparse

        from chromiumdiff import cli
        parser = cli.build_parser()
        shape = {}
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    flags = set()
                    for a in sub._actions:
                        flags.update(a.option_strings)
                    shape[name] = flags
        return shape

    def test_every_command_the_project_prints_is_one_the_cli_accepts(self):
        shape = self._parser_shape()
        self.assertIn("serve", shape)  # the scan is worthless if this is empty
        wrong, seen = [], 0
        for path, text in self._texts():
            for line_no, line in self._logical_lines(path, text):
                for match in self.COMMAND.finditer(line):
                    sub, rest = match.group(1), match.group(2) or ""
                    seen += 1
                    where = "%s:%d  %s" % (path, line_no, match.group(0).strip())
                    if sub not in shape:
                        wrong.append("%s -> no `%s` subcommand" % (where, sub))
                        continue
                    for flag in re.findall(r"--[a-z][a-z0-9-]*", rest):
                        if flag not in shape[sub]:
                            wrong.append("%s -> `%s` has no %s"
                                         % (where, sub, flag))
        self.assertGreater(seen, 20, "the scan found no commands to check")
        self.assertEqual([], wrong, "\n".join(wrong))

    def test_a_skill_never_shows_a_report_command_that_writes_nothing(self):
        """`report` prints unless `--out` or a redirect sends it somewhere.

        That is the right default for a subcommand, and wrong in a skill: an
        agent runs what the file shows, and the whole reason these lines exist
        is to get a `serve` session's lookups into `report.md`. Without `--out`
        the agent gets a report in its own output and hands over the stale
        file, which is the failure the instruction was written to prevent.
        """
        skills = os.path.join(self.ROOT, "skills")
        checked = []
        for path, text in self._texts():
            if not path.startswith("skills" + os.sep):
                continue
            for line_no, line in self._logical_lines(path, text):
                for match in self.COMMAND.finditer(line):
                    if match.group(1) != "report":
                        continue
                    rest = match.group(2) or ""
                    checked.append("%s:%d" % (path, line_no))
                    self.assertTrue(
                        "--out" in rest or ">" in line,
                        "%s:%d shows `report` with nowhere to write: %s"
                        % (path, line_no, line.strip()))
        self.assertTrue(os.path.isdir(skills))
        self.assertTrue(checked, "no report command found in skills/")

    def test_the_disk_note_and_the_readme_agree(self):
        # Measured on a clean fetch, so the two places that quote it must not
        # drift apart the way the two of them already had.
        from chromiumdiff import cli
        readme = os.path.join(self.ROOT, "README.md")
        with open(readme, encoding="utf-8") as fh:
            rows = [ln for ln in fh if "Free disk" in ln]
        self.assertEqual(1, len(rows), "README lost its free-disk row")
        # As a whole number: "150" sits inside "1500", so a substring
        # test accepts a tenfold error in the row it exists to hold.
        self.assertRegex(rows[0], r"\b%d\b" % cli.PAIR_DISK_MB)
