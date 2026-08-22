"""Diff, scoring and reporting tests.

These cover the judgement calls -- what counts as a change, what it is called,
and how far up the list it goes -- because those are the parts that decide
whether the output is worth reading.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chromedrift.diff import diff_snapshots
from chromedrift.extract import mojom
from chromedrift.model import BUCKET_HOUSEKEEPING, Fact, Report, Snapshot
from chromedrift.score import (Scope, score_all, score_change,
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
        from chromedrift.model import ALL_KINDS, KIND_OWNERS
        self.assertEqual(sorted(KIND_OWNERS), sorted(ALL_KINDS))

    def test_every_owner_named_is_a_real_owner(self):
        from chromedrift.diff import SIGNAL_OWNERS
        from chromedrift.model import KIND_OWNERS, OWNER_ORDER
        for source in (KIND_OWNERS, SIGNAL_OWNERS):
            for key, owner in source.items():
                self.assertIn(owner, OWNER_ORDER, key)

    def test_every_owner_is_reachable_and_says_what_it_means(self):
        """Reachable from one table or the other, not necessarily both.

        `config` has no surface of its own -- nothing is *declared* outside the
        repository -- so it is reached only by signal. An owner reachable from
        neither would be a name in the report legend that no row can carry.
        """
        from chromedrift.diff import SIGNAL_OWNERS
        from chromedrift.model import (KIND_OWNERS, OWNER_LABELS,
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
        from chromedrift.diff import owner_of
        from chromedrift.model import OWNER_CONFIG, OWNER_NATIVE
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
        import json
        import re

        from chromedrift.report import html as html_report
        from chromedrift.report import markdown as md_report
        from chromedrift.model import OWNER_LABELS

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

        html = html_report.render(report)
        rows = json.loads(re.search(r"window\.__FINDINGS__=(\[.*?\]);\n",
                                    html, re.S).group(1))
        from collections import Counter
        self.assertEqual(Counter(r["owner"] for r in rows),
                         Counter({k: v for k, v in counted.items() if v}))

    def test_the_owner_counts_partition_the_report(self):
        """Each tally adds up to the total, so the counts are the report."""
        from chromedrift.model import OWNER_ORDER
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
        """51 of 220 additions are gated only there, and were read as live."""
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
        from chromedrift.diff import (SIGNAL_BUCKET, SIGNAL_LABELS,
                                      SIGNAL_SEVERITY)
        return SIGNAL_SEVERITY, SIGNAL_LABELS, SIGNAL_BUCKET

    def test_the_three_tables_hold_the_same_signals(self):
        severity, labels, buckets = self._tables()
        self.assertEqual(set(severity), set(labels))
        self.assertEqual(set(severity), set(buckets))

    def test_every_bucket_named_is_a_real_bucket(self):
        from chromedrift.model import BUCKET_ORDER
        _, _, buckets = self._tables()
        for signal, bucket in buckets.items():
            self.assertIn(bucket, BUCKET_ORDER, signal)

    def test_every_bucket_is_reachable(self):
        from chromedrift.model import BUCKET_ORDER
        _, _, buckets = self._tables()
        self.assertEqual(sorted(set(buckets.values())), sorted(BUCKET_ORDER))

    def test_every_bucket_says_what_it_means(self):
        from chromedrift.model import BUCKET_LABELS, BUCKET_MEANINGS, BUCKET_ORDER
        for bucket in BUCKET_ORDER:
            self.assertTrue(BUCKET_LABELS.get(bucket))
            self.assertTrue(BUCKET_MEANINGS.get(bucket))

    def test_a_change_of_every_kind_and_direction_gets_a_bucket(self):
        """Including the ones that carry no signal at all -- 903 of 2,800 on a
        real M148 -> M151 run, and every one of them has to be filed."""
        from chromedrift.diff import bucket_of
        from chromedrift.model import (ADDED, ALL_KINDS, BUCKET_ORDER, MODIFIED,
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
    after the rename.
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

    Three of them accepted the flag and dropped it. `catalog` was the worst:
    it reported coverage against the full target list while describing a run
    that only fetched one partition.
    """

    def _parse(self, argv):
        from chromedrift.cli import build_parser
        return build_parser().parse_args(argv)

    def test_every_command_taking_the_flag_forwards_it(self):
        import inspect
        from chromedrift import cli

        for name in ("cmd_snapshot", "cmd_diff", "cmd_run"):
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

    def _report(self, n=3000):
        from chromedrift.model import Change, Finding, Report
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
        from chromedrift.report import html as html_report
        return html_report.render(self._report(n))

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
        from chromedrift.report.html import _to_rows

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
        from chromedrift.extract.webui_gates import WEBUI_HANDLER_DIR, applies_to
        from chromedrift.targets import GATE_ROOT, get_targets, reaches, scope_of

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
        "third_party/blink/renderer/core/dom/element.idl",  # web API definitions
        "third_party/blink/public/mojom/frame/frame.mojom",  # process boundary
    ]

    def _report(self, **kw):
        from chromedrift.catalog import analyze
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


class TestClustering(unittest.TestCase):
    """One Chromium change arrives as fragments; they must read as one story."""

    def _finding(self, kind, key, attrs, score=50):
        from chromedrift.model import Change, Finding
        return Finding(
            change=Change(change_type="modified", kind=kind, key=key,
                          name=key.split("/")[-1], before=dict(attrs),
                          after=dict(attrs)),
            score=score, bucket="behaviour")

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
            score=60, bucket="behaviour")
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
                                          bucket="behaviour")],
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
                                        bucket="behaviour",
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

        from chromedrift.model import Change, Finding, Report
        from chromedrift.report import html as html_report

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
    identifier while holding the string emitted nothing -- yet any code
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
    """How much of the tree was read bounds every count above it.

    It was printed to stderr and stored on the snapshot, and then not carried
    into the report, while README and SKILL.md both said the report held it.
    It now also decides two things in the scoring -- what an unconfirmed
    removal scores and where it is filed -- so the number the report states and
    the number the ranking used have to be the same one.
    """

    def _report(self):
        from chromedrift.score import summarize_findings
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
        from chromedrift.score import summarize_findings
        self.assertNotIn("coverage", summarize_findings([]))

    def test_the_ranking_reads_the_same_measurement_the_report_prints(self):
        from chromedrift.score import Scope
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
        from chromedrift.extract.webui_controls import (INTERACTIVE_SEGMENTS,
                                                        STRUCTURAL_TAGS)
        from chromedrift.report.wording import control_word

        unnamed = [tag for tag in
                   [f"cr-{seg}" for seg in sorted(INTERACTIVE_SEGMENTS)]
                   + sorted(STRUCTURAL_TAGS)
                   if control_word(tag) == tag]
        self.assertEqual(unnamed, [],
                         "these tags reach the report as raw tag names")

    def test_the_rule_admits_what_it_was_built_for(self):
        from chromedrift.extract.webui_controls import is_control

        for tag in ("settings-toggle-button", "cr-icon-button",
                    "settings-collapse-radio-button", "cr-action-menu",
                    "settings-category-default-radio-group",
                    "cr-searchable-drop-down"):
            self.assertTrue(is_control(tag, "", element_id="x"), tag)

    def test_the_rule_keeps_decoration_out(self):
        from chromedrift.extract.webui_controls import is_control

        for tag in ("cr-icon", "cr-iconset", "cr-ripple", "site-favicon",
                    "iron-media-query"):
            self.assertFalse(is_control(tag, "", element_id="x", label="y"), tag)

    def test_a_preference_makes_anything_a_control(self):
        """The rule that recovered the 41 the name list was dropping."""
        from chromedrift.extract.webui_controls import is_control

        self.assertTrue(is_control("some-unknown-widget", "download.prompt"))
        self.assertFalse(is_control("some-unknown-widget", ""))

    def test_an_interactive_tag_with_no_identity_is_not_worth_a_fact(self):
        """Position is the only identity left, and it churns on reorder."""
        from chromedrift.extract.webui_controls import is_control

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
        from chromedrift.model import Fact, Snapshot
        return Snapshot(ref=ref, meta={"target_set": "default"},
                        facts=[Fact(kind, f"F{i}", f"F{i}", path="a.cc",
                                    attrs={"default_state": "enabled"})
                               for i in range(n)])

    def test_a_side_holding_a_fraction_of_the_other_is_refused(self):
        from chromedrift.diff import diff_snapshots
        with self.assertRaises(ValueError) as caught:
            diff_snapshots(self._snap("full", 24959), self._snap("partial", 1647))
        message = str(caught.exception)
        self.assertIn("truncated tree", message)
        # The message has to name the thing to check, not just the numbers.
        self.assertIn("--to-src", message)

    def test_two_real_versions_are_not_refused(self):
        """M143 holds 24,113 facts against M151's 24,959 -- 3% apart."""
        from chromedrift.diff import diff_snapshots
        diff_snapshots(self._snap("m143", 24113), self._snap("m151", 24959))

    def test_an_empty_side_is_refused(self):
        from chromedrift.diff import diff_snapshots
        with self.assertRaises(ValueError) as caught:
            diff_snapshots(self._snap("good", 24959), self._snap("broken", 0))
        self.assertIn("no facts at all", str(caught.exception))

    def test_small_fixtures_are_left_alone(self):
        """A ratio over a handful of facts is noise, not evidence.

        Without a floor this guard fires on every unit test in this file that
        builds a one-fact snapshot against a three-fact one, which is how it
        was first written.
        """
        from chromedrift.diff import diff_snapshots
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
        from chromedrift.model import Report
        return Report(from_ref="a", to_ref="b", findings=[],
                      summary={}, meta={"missing_targets": missing})

    def test_the_markdown_names_them(self):
        from chromedrift.report import markdown as md
        text = md.render(self._report({"b": ["net/base/features.cc",
                                             "media/base/media_switches.cc"]}))
        self.assertIn("2 target(s) absent from `b`", text)
        self.assertIn("net/base/features.cc", text)

    def test_nothing_is_said_when_nothing_is_missing(self):
        from chromedrift.report import markdown as md
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
        from chromedrift.targets import DISCOVERY_ROOTS, could_declare

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
        from chromedrift.targets import could_declare

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

        from chromedrift.targets import (DISCOVERY_ROOTS, could_declare,
                                         discover_candidates)

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        listings = glob.glob(os.path.join(root, ".chromedrift-cache",
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


class TestTheDocumentedSourceMapStillHolds(unittest.TestCase):
    """The README's map of the source is a second derivation of the source.

    It goes stale exactly the way the measured tables do, and for longer,
    because nothing recomputes it. Caught drifted: a stated total of 10,180
    lines against 10,017 actual, `report/` at 1,691 against 1,493, and a test
    count of 273 against 287. Those are small numbers to be wrong about, and
    that is the point -- a reader who checks one and finds it wrong stops
    trusting the ones they cannot check, like the coverage tables.

    Unlike the M151 fact table, this needs nothing on disk, so it runs
    everywhere.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _readme(self):
        with open(os.path.join(self.ROOT, "README.md"), encoding="utf-8") as fh:
            return fh.read()

    @staticmethod
    def _int(raw):
        return int(raw.replace(".", "").replace(",", ""))

    def _lines_of(self, name):
        """Line count for a module or a package directory."""
        path = os.path.join(self.ROOT, "chromedrift", name)
        if name.endswith("/"):
            total = 0
            for dirpath, _, filenames in os.walk(path):
                for filename in sorted(filenames):
                    if filename.endswith(".py"):
                        with open(os.path.join(dirpath, filename),
                                  encoding="utf-8") as fh:
                            total += sum(1 for _ in fh)
            return total
        with open(path, encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    def test_the_source_map_lists_every_module(self):
        """A map that quietly stops naming a file is the same defect as one
        that names a wrong number, and harder to see. `score.py` arrived and
        four modules left in one change; nothing but this would have said so.

        Dunders are excluded: `__init__.py` and `__main__.py` are three and
        four lines of plumbing, and listing them tells a reader nothing.
        """
        listed = {name for name, _ in self._rows()}
        actual = set()
        for name in os.listdir(os.path.join(self.ROOT, "chromedrift")):
            if name.startswith("__"):
                continue
            if name.endswith(".py"):
                actual.add(name)
            elif os.path.isdir(os.path.join(self.ROOT, "chromedrift", name)):
                actual.add(name + "/")
        self.assertEqual(sorted(listed), sorted(actual))

    def _rows(self):
        return re.findall(r"(?m)^  ([a-z_]+\.py|[a-z]+/)\s+([\d.,]+)\s",
                          self._readme())

    def test_the_source_map_matches_the_source(self):
        rows = self._rows()
        self.assertTrue(rows, "source map not found in README")
        wrong = []
        for name, stated in rows:
            actual = self._lines_of(name)
            if self._int(stated) != actual:
                wrong.append(f"{name}: README says {stated}, actually {actual}")
        self.assertEqual(wrong, [], "the README's source map has drifted")

    def test_the_stated_total_matches_the_files_it_counts(self):
        m = re.search(r"\(([\d.,]+) lines, (\d+) files\)", self._readme())
        self.assertIsNotNone(m, "the line/file total is not in the README")
        stated_lines, stated_files = self._int(m.group(1)), int(m.group(2))

        total, files = 0, 0
        for dirpath, dirnames, filenames in os.walk(
                os.path.join(self.ROOT, "chromedrift")):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                files += 1
                with open(os.path.join(dirpath, filename), encoding="utf-8") as fh:
                    total += sum(1 for _ in fh)
        self.assertEqual((stated_lines, stated_files), (total, files))

    def test_the_stated_test_count_matches_this_suite(self):
        """Counting the suite from inside it. Discovery imports, it does not run."""
        loader = unittest.defaultTestLoader
        suite = loader.discover(os.path.join(self.ROOT, "tests"))
        self.assertEqual(loader.errors, [], "test discovery reported errors")

        def count(s):
            return sum(count(x) if isinstance(x, unittest.TestSuite) else 1
                       for x in s)

        m = re.search(r"\*\*([\d.,]+) tests", self._readme())
        self.assertIsNotNone(m, "the test count is not in the README")
        self.assertEqual(self._int(m.group(1)), count(suite))


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
        "Preference keys": "pref",
        "Pref": "pref",
        "Command-line switches": "switch",
        "Switch": "switch",
        "Mojo interfaces": "mojo_interface",
        "Mojo interface": "mojo_interface",
        "Mojo methods": "mojo_method",
        "Mojo method": "mojo_method",
        "Mojo structs": "mojo_struct",
        "Mojo struct fields": "mojo_field",
        "Mojo enums": "mojo_enum",
        "WebUI controls": "webui_control",
        "Facts": None,                       # None = total fact count
    }
    DOCS = ("README.md", "skills/analyzing-chromium-uprevs/SKILL.md",
            "docs/pipeline.html")
    ROW_RE = re.compile(r"^\s*\|([^|]+)\|([^|]+)\|([^|]+)\|\s*$", re.MULTILINE)
    # The interactive page states the same counts as chips rather than table
    # rows, and it went stale in exactly the same way.
    CHIP_RE = re.compile(r'<span class="chip[^"]*">([^<·]+)·\s*([\d.,]+)</span>')
    CHIPS = {"base::Feature": "base_feature", "pref": "pref", "switch": "switch",
             "Mojo method": "mojo_method", "Mojo interface": "mojo_interface",
             "Mojo struct": "mojo_struct", "Mojo struct field": "mojo_field",
             "Mojo enum": "mojo_enum",
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

    Only `base::Feature` recorded one, so the comparison could see
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
        source = ('#if defined(ENABLE_X)\nA\n'
                  '#elif BUILDFLAG(IS_WIN)\nB\n#else\nC\n#endif\n')
        spans = conditional_spans(source)
        self.assertEqual(enclosing_conditions(spans, source.index("\nB") + 1),
                         ["!(defined(ENABLE_X))", "BUILDFLAG(IS_WIN)"])
        self.assertEqual(enclosing_conditions(spans, source.index("\nC") + 1),
                         ["!(defined(ENABLE_X))", "!(BUILDFLAG(IS_WIN))"])

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
        from chromedrift.score import score_change
        from chromedrift.model import Change
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

    # A value for every attribute the comparison treats as meaningful, chosen
    # so that moving it is a real move rather than a type accident. Kept beside
    # the invariant it feeds rather than inside it, because adding an attribute
    # to MEANINGFUL_ATTRS should fail here loudly until someone says what a
    # change to it means.
    _SAMPLE = {
        "default_state": ("disabled", "enabled"),
        "signatures": (["void f()"], ["void f()", "void f(long a)"]),
        "overload_gates": (["void f() [A]"], ["void f() [B]"]),
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
        from chromedrift.diff import MEANINGFUL_ATTRS

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
                                          bucket="behaviour")])
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
        from chromedrift.model import Finding, Report
        from chromedrift.report import html as html_report
        report = Report(from_ref="a", to_ref="b",
                        findings=[Finding(change=self._control(), score=30,
                                          bucket="behaviour")])
        row = html_report._to_rows(report, "windows")[0]
        self.assertEqual(row["change_type"], "added")
        self.assertEqual(row["where"], "settings › privacy_page")
        self.assertIn("toggle", row["what"])

    def test_a_report_with_no_screens_renders_no_empty_section(self):
        from chromedrift.model import Change, Finding, Report
        from chromedrift.report import markdown as md_report
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

        from chromedrift.model import Finding, Report
        from chromedrift.report import html as html_report

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
        printed = re.findall(
            r'data-set="(\w+):([\w_]+)"[^>]*>\s*<div class="n">([\d,]+)</div>',
            text)
        self.assertEqual(len(printed), len(BUCKET_ORDER), printed)
        for which, value, count in printed:
            field = {"fk": "kind", "fb": "bucket"}[which]
            self.assertEqual(int(count.replace(",", "")),
                             sum(1 for r in rows if r[field] == value),
                             f"{which}:{value} sends the reader to a different "
                             f"number from the one it prints")

    def test_a_long_delta_does_not_take_over_the_table_cell(self):
        """A Mojo signature runs past 400 characters."""
        from chromedrift.model import Finding, Report
        from chromedrift.report import html as html_report

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


class TestTheDocumentedReasoningIsTheRealReasoning(unittest.TestCase):
    """The reason lines quoted in the docs must be lines the scorer emits.

    Both documents print a sample of a finding's `reasons` to explain what the
    two numbers mean, and a sample is a second copy of a string the code owns.
    It drifted within an hour of being written: the wording gained a clause
    saying which bucket an unconfirmed disappearance is filed under, and the
    two documents still showed the sentence without it.

    Whitespace is normalised because the documents wrap for width; every other
    character has to match.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DOCS = ("README.md", "skills/analyzing-chromium-uprevs/reference/signals.md")

    @staticmethod
    def _flat(text):
        return " ".join(text.split())

    def _real_reasons(self):
        """Every reason line the scorer produces for the documented cases."""
        from chromedrift.model import Fact
        from chromedrift.score import Scope, score_change

        # The default set's real coverage of the M151 tree. It moved when the
        # denominator stopped being two filename rules and started asking the
        # extractors -- 64/1,164 was 5% of the pref and feature files, not of
        # the tree -- and the documents quote the sentence this Scope prints,
        # so the fixture has to be the measured pair or the check is circular.
        partial = Scope({"to": {
            "candidates": 8366, "read": 3677,
            # Per surface, because that is what the sentence now quotes: a
            # preference removal is judged against the read of the pref files
            # and not against an average that includes 99% of the web API
            # definitions.
            "by_surface": {
                "preference keys and switches": {"candidates": 348, "read": 4},
                "web API definitions": {"candidates": 2170, "read": 2166},
            }}}, to_ref="refs/tags/151.0.7922.138")
        key = Fact(kind="pref", key="a.b", name="a.b", path="pref_names.h",
                   attrs={"var": "kAB"})
        api = Fact(kind="idl_interface", key="Foo", name="Foo",
                   path="third_party/blink/renderer/core/foo.idl",
                   attrs={"idl_kind": "interface"})
        out = []
        for fact in (key, api):
            change = diff_snapshots(snap("148.0.0.0", [fact]),
                                    snap("151.0.0.0", []),
                                    platform="windows")[0]
            out += score_change(change, partial).reasons
        # A default flipping on, which loses nothing and so shows the shape of
        # a finding whose score is its severity.
        flip = diff_snapshots(snap("148.0.0.0", [feature("Foo", "disabled")]),
                              snap("151.0.0.0", [feature("Foo", "enabled")]),
                              platform="windows")[0]
        out += score_change(flip, partial).reasons
        return {self._flat(r) for r in out}

    def test_every_quoted_reason_line_is_one_the_scorer_emits(self):
        real = self._real_reasons()
        quoted = []
        for doc in self.DOCS:
            with open(os.path.join(self.ROOT, doc), encoding="utf-8") as fh:
                text = fh.read()
            # Fenced blocks whose first line starts a reason line.
            for block in re.findall(r"(?ms)^```\n(severity \d+ .*?)^```", text):
                for chunk in re.split(r"(?m)^(?=severity \d+ |-\d+ |0 )", block):
                    if chunk.strip():
                        quoted.append((doc, self._flat(chunk)))
        self.assertTrue(quoted, "no sample reason block found in the docs")
        wrong = [f"{doc}: {line[:90]}" for doc, line in quoted if line not in real]
        self.assertEqual(wrong, [], "documented reason lines the scorer never emits")


class TestTheSkillFollowsTheAuthoringGuidance(unittest.TestCase):
    """The published rules for a skill, held as a test rather than a habit.

    From the Agent Skills authoring guidance: the frontmatter has a `name` of
    at most 64 characters in lowercase-and-hyphens and a `description` of at
    most 1,024, the SKILL.md body stays under 500 lines, a reference file over
    100 lines opens with a table of contents, and references are one level deep
    -- a reference file that links another one leaves Claude previewing with
    `head` instead of reading the whole thing.
    """

    ROOT = "skills/analyzing-chromium-uprevs"

    def _read(self, name):
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, name), encoding="utf-8") as fh:
            return fh.read()

    def _references(self):
        import glob
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return sorted(glob.glob(os.path.join(here, self.ROOT, "reference", "*.md")))

    def test_the_frontmatter_is_within_its_limits(self):
        import re
        text = self._read(f"{self.ROOT}/SKILL.md")
        name = re.search(r"^name: (.+)$", text, re.M).group(1).strip()
        description = re.search(r"^description: (.+)$", text, re.M).group(1)
        self.assertLessEqual(len(name), 64)
        self.assertRegex(name, r"^[a-z0-9-]+$")
        for reserved in ("anthropic", "claude"):
            self.assertNotIn(reserved, name)
        self.assertTrue(description.strip())
        self.assertLessEqual(len(description), 1024)

    def test_the_body_stays_under_five_hundred_lines(self):
        body = self._read(f"{self.ROOT}/SKILL.md").split("---", 2)[-1]
        self.assertLess(len(body.splitlines()), 500)

    def test_a_long_reference_opens_with_a_table_of_contents(self):
        for path in self._references():
            text = self._read(path)
            if len(text.splitlines()) <= 100:
                continue
            head = "\n".join(text.splitlines()[:12])
            self.assertIn("## Contents", head, path)

    def test_references_are_one_level_deep(self):
        """No reference file links another; SKILL.md links them all."""
        import os
        import re
        skill = self._read(f"{self.ROOT}/SKILL.md")
        for path in self._references():
            name = os.path.basename(path)
            self.assertIn(f"reference/{name}", skill,
                          f"{name} is not linked from SKILL.md")
            linked = re.findall(r"\]\(([^)]+\.md)\)", self._read(path))
            self.assertEqual(linked, [], f"{name} links another document")


class TestAMojoOrdinalChangeReachesTheReport(unittest.TestCase):
    """Extracting a fact is not the same as comparing it.

    This pipeline has two doors -- the extractor makes a Fact, and
    `MEANINGFUL_ATTRS` decides which of its fields a diff looks at. The
    previous commit opened the first, wrote "the ordinal is now a compared
    attribute" in its message, and asserted only that the key existed on the
    fact. `Foo@0 -> Foo@1` produced no change at all, on the surface this tool
    ranks highest, and 316 tests passed.

    So this one drives the whole path: two snapshots in, a scored finding out.
    """

    def _snap(self, ref, body):
        from chromedrift.extract import mojom
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
        from chromedrift.report import wording
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
        from chromedrift.report.html import _embed
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
        from chromedrift.report.html import _http_url
        self.assertTrue(_http_url("https://spec.example/x"))
        self.assertTrue(_http_url("http://spec.example/x"))
        self.assertFalse(_http_url("javascript:alert(1)"))
        self.assertFalse(_http_url("  JavaScript:alert(1)"))
        self.assertFalse(_http_url("data:text/html,x"))
        self.assertFalse(_http_url(None))

    def test_a_line_separator_cannot_break_the_literal(self):
        """U+2028 is valid JSON and illegal in a JS string literal."""
        from chromedrift.report.html import _embed
        self.assertNotIn("\u2028", _embed({"a": "x\u2028y"}))

    def test_a_ref_cannot_climb_out_of_the_cache(self):
        """Both cache paths are built from the ref, and both used to allow it.

        `/` and `:` were replaced and `\\` was not -- a separator on the
        platform this tool is written for -- so `..\\..\\victim` wrote outside
        the cache, and `tree_path` is where a whole source tree is unpacked.
        """
        from chromedrift.acquire import safe_name as _safe_name
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
        from chromedrift.cli import _redact_proxy
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
        from chromedrift.extract import _skip
        from chromedrift.targets import could_declare
        for path, keep in self.CASES.items():
            self.assertEqual(not _skip(path), keep, f"extraction: {path}")
            self.assertEqual(could_declare(path) is not None, keep,
                             f"discovery: {path}")

    def test_a_product_word_containing_test_is_not_test_code(self):
        """The rule is a suffix before the extension, not a substring."""
        from chromedrift.eligibility import skip_reason
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
        from chromedrift.extract import web_idl
        from chromedrift.model import dedupe_facts
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

    def test_gaining_a_new_argument_count_is_new_surface(self):
        """No existing call can reach it, because resolution counts first."""
        wider = self.ONE + " Promise<R> install(USVString u, USVString v);"
        change = [c for c in diff_snapshots(self._snap("148.0.0.0", self.ONE),
                                            self._snap("151.0.0.0", wider))
                  if c.kind == "idl_member"][0]
        self.assertEqual(change.signals, ["web_api_overload_added"])
        self.assertEqual(score_change(change).bucket, "new")

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
        self.assertIn("overload_gates", change.deltas)
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
        self.assertNotIn("overload_gates", facts["N.f"].attrs)
        self.assertIn("signatures", facts["N.f"].attrs)

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
        from chromedrift.model import Fact
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
        from chromedrift.cli import _incomplete_reason
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
        from chromedrift.extract import REGISTRY
        from chromedrift.targets import could_declare
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
        from chromedrift.extract import REGISTRY
        from chromedrift.targets import _discovery_rules
        rules = _discovery_rules()
        self.assertEqual(len(rules), len(REGISTRY))
        for rule, (_, applies, _fn) in zip(rules, REGISTRY):
            self.assertIs(rule.applies, applies)


class TestTheDocumentedM148FiguresAreStillTrue(unittest.TestCase):
    """The headline numbers the documents quote, checked against a real run.

    These go stale silently and they are the numbers a reader trusts most: the
    documents said "90 flags removed, splitting exactly 45 and 45" for four
    commits after widening the target set made it 154, and "261 of the 315
    Breaking rows" for one commit after the web API gates dropped Breaking to
    282. Both survived every other test in this file, because nothing here
    reads prose.

    Checked against `out/report.json` when one exists, which is the same
    bargain the M151 fact table strikes: anyone who has run the tool
    re-verifies the documents for free, and a bare checkout does not fail.
    """

    REPORT = "out/report.json"
    PAIR = ("148.0.7778.217", "151.0.7922.138")

    def _report(self):
        import json
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(here, self.REPORT)
        if not os.path.exists(path):
            self.skipTest(f"no {self.REPORT}; run the pair to check the docs")
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
        meta = report.get("meta") or {}
        if not all(v in f"{meta.get('from_ref', '')}{report.get('from_ref','')}"
                   f"{report.get('to_ref','')}" for v in self.PAIR):
            self.skipTest("out/report.json is a different pair")
        if (meta.get("target_set") or "default") != "default":
            self.skipTest("out/report.json is not the default target set")
        return report

    def _docs(self):
        import glob
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        names = ["README.md", "docs/pipeline.html"]
        names += [os.path.relpath(p, here) for p in
                  glob.glob(os.path.join(here, "skills", "**", "*.md"),
                            recursive=True)]
        out = {}
        for name in names:
            with open(os.path.join(here, name), encoding="utf-8") as fh:
                out[name] = fh.read()
        return out

    def _leading(self, finding):
        from chromedrift.diff import SIGNAL_SEVERITY
        signals = finding["change"].get("signals") or []
        return max(signals, key=lambda s: (SIGNAL_SEVERITY.get(s, 0), s)) \
            if signals else ""

    def test_the_quoted_figures_match_the_run(self):
        import re
        from collections import Counter
        from chromedrift.diff import SIGNAL_OWNERS
        from chromedrift.model import KIND_OWNERS, OWNER_NATIVE

        report = self._report()
        findings = report["findings"]
        counts = Counter(self._leading(f) for f in findings)
        breaking = [f for f in findings if f["bucket"] == "breaking"]

        def owner(finding):
            lead = self._leading(finding)
            return SIGNAL_OWNERS.get(lead) or KIND_OWNERS.get(
                finding["change"]["kind"], OWNER_NATIVE)

        contract = sum(1 for f in breaking
                       if owner(f) in ("ipc", "webplatform"))
        retired = counts["flag_retired_on"] + counts["flag_retired_off"]

        # Phrase as written -> the number it has to be. The pattern is the
        # sentence, not just the digits, so a figure that moves into a
        # different sentence is not silently satisfied by the old one.
        expected = [
            (r"(\d+) of the (\d+) Breaking rows",
             (contract, len(breaking))),
            (r"(\d+) of ([\d,]+) findings at M148 . M151 are in that state",
             (report["summary"]["not_in_build"], report["summary"]["total"])),
            (r"(\d+) that had shipped(?:,| and) (\d+)",
             (counts["flag_retired_on"], counts["flag_retired_off"])),
        ]
        seen = 0
        for name, text in self._docs().items():
            for pattern, want in expected:
                for m in re.finditer(pattern, text):
                    seen += 1
                    got = tuple(int(g.replace(",", "")) for g in m.groups())
                    self.assertEqual(
                        got, want,
                        f"{name}: {m.group(0)!r} but the run says {want}")
        self.assertGreaterEqual(seen, 6, "the documented sentences moved")

        # A named figure may not have two current values across the documents.
        # Matching three sentences was not enough: the bucket counts appeared
        # in four more places and stayed at a previous run's numbers while
        # every test passed, because no test was looking at those places.
        labels = {
            "Breaking": len(breaking),
            "Behaviour change": report["summary"]["by_bucket"]["behaviour"],
            "New surface": report["summary"]["by_bucket"]["new"],
            "Housekeeping": report["summary"]["by_bucket"]["housekeeping"],
        }
        for name, text in self._docs().items():
            for label, want in labels.items():
                # A count beside the label, in a table cell or a code block.
                for m in re.finditer(
                        rf"{re.escape(label)}\**\s*(?:\||)\s*([\d,]{{3,7}})(?=\s|\||<|$)",
                        text):
                    value = int(m.group(1).replace(",", ""))
                    # Only figures in the plausible range are this pair's
                    # counts; a year or a line number is not.
                    if not (100 <= value <= 9999):
                        continue
                    self.assertEqual(
                        value, want,
                        f"{name}: {label} appears as {value}, the run says {want}")
        # And the total the retired-flag sentences describe.
        self.assertEqual(retired, 132,
                         "the retired-flag total moved; update the documents")


class TestTheThreeStageRuleIsNeverTaughtAsUniversal(unittest.TestCase):
    """Wherever a document explains the three stages, it says what they miss.

    The rule is true of flags, Blink runtime features and the chrome:// screens
    they gate, and false of Mojo, preferences and command-line switches, where
    the declaration is the contract and it changes on adoption. Measured at
    M148 -> M151, 261 of the 315 Breaking rows are on the second half.

    It was written as universal three times -- "the rule that governs
    everything", "the trap that matters most", "Chromium moves every feature
    through three stages" -- and each time the surrounding prose then taught a
    reader to dismiss the highest-severity findings in the report as cleanup.
    Correcting the wording is not enough on its own, because the sentence is
    natural to write; so the invariant is that the *same passage* names the
    surfaces the rule does not cover.
    """

    # Scoped to the section the passage sits in, not to a character window.
    # A window was tried first and passed while the warning it was meant to
    # require had been deleted: these documents mention Mojo everywhere, so
    # any window wide enough to hold a section also catches a neighbour's
    # mention. The section is the unit a reader actually reads.
    MARKERS = ("three stages", "three moments", "three-stage")
    EXCEPTIONS = ("mojo",)

    DOCUMENTS = (
        "README.md",
        "skills/analyzing-chromium-uprevs/SKILL.md",
        "docs/pipeline.html",
    )

    @staticmethod
    def _sections(text: str):
        """Split on headings, markdown and HTML alike."""
        import re
        cuts = [m.start() for m in
                re.finditer(r"^#{1,6} |<h[1-6][ >]", text, re.M)]
        cuts = [0] + cuts + [len(text)]
        return [text[a:b] for a, b in zip(cuts, cuts[1:]) if b > a]

    def test_every_section_naming_the_stages_also_names_the_exception(self):
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        checked = 0
        for name in self.DOCUMENTS:
            with open(os.path.join(here, name), encoding="utf-8") as fh:
                text = fh.read()
            for section in self._sections(text):
                lowered = section.lower()
                if not any(m in lowered for m in self.MARKERS):
                    continue
                checked += 1
                self.assertTrue(
                    any(word in lowered for word in self.EXCEPTIONS),
                    f"{name}: a section teaches the three-stage rule without "
                    f"naming a surface it does not govern:\n"
                    f"{section[:200]}")
        self.assertGreaterEqual(checked, 3, "the passages moved or were renamed")


class TestEveryShippedDocumentIsInEnglish(unittest.TestCase):
    """No Vietnamese left in anything a reader or an agent opens.

    The documents were written in Vietnamese and translated, and the
    translation was reported complete twice while `pipeline.html` still held
    six of them: a CSS comment and five strings inside the interactive
    comparison widget, which a reader sees rendered on the page rather than in
    the prose anyone proof-read. A grep is the only thing that finds those.

    Diacritics are the test rather than a word list, because they are what
    Vietnamese has and English does not, and no identifier in this project
    carries one.
    """

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MARKS = re.compile(
        "[\u00e0-\u00e3\u00e8-\u00ea\u00ec\u00ed\u00f2-\u00f5"
        "\u00f9\u00fa\u00fd\u0103\u0111\u0129\u0169\u01a1\u01b0"
        "\u1ea0-\u1ef9]", re.I)

    def _shipped_files(self):
        import glob
        for pattern in ("README.md", "docs/*.html", "skills/**/*.md",
                        "chromedrift/**/*.py", "tests/*.py", "tests/js/*.js"):
            for path in glob.glob(os.path.join(self.ROOT, pattern),
                                  recursive=True):
                yield path

    def test_no_document_or_source_carries_vietnamese(self):
        offenders = []
        for path in sorted(self._shipped_files()):
            with open(path, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if self.MARKS.search(line):
                        rel = os.path.relpath(path, self.ROOT)
                        offenders.append(f"{rel}:{n}  {line.strip()[:70]}")
        self.assertEqual(offenders, [])


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
        from chromedrift.model import Change, Finding, Report
        from chromedrift.report import html as html_report
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
        from chromedrift.model import Change
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
        from chromedrift.model import ALL_KINDS
        from chromedrift.report import wording

        bare = []
        for kind in ALL_KINDS:
            change = self._change(kind)
            said = wording.describe(change)
            if said in (change.name, change.key):
                bare.append(kind)
        self.assertEqual(bare, [], "kinds that reach the report as an identifier")

    def test_every_kind_has_a_word_for_what_it_is(self):
        from chromedrift.model import ALL_KINDS
        from chromedrift.report.wording import KIND_WORDS
        self.assertEqual(sorted(set(ALL_KINDS) - set(KIND_WORDS)), [])


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
