"""Rank the changes, and say why each one ranks where it does.

`diff.py` answers *what happened* and how much that kind of thing normally
costs -- the severity.  This stage answers the two questions left, both of
which depend on the run rather than on the change:

  * **Is it in the binary we ship?**  Chromium wraps declarations in
    ``#if BUILDFLAG(IS_WIN)`` chains, and 146 declarations at M151 resolve to
    "not on Windows".  A change to one of those cannot move anything here, so
    it scores zero.
  * **Did this run read enough of the tree to believe a removal?**  A removal
    is an inference from absence, and absence from a tree the run read a
    part of is a much weaker claim than absence from one it read all of.
    Measured M148 -> M151: the curated files alone report 139 preference keys
    gone and a full run still holds 29 of them, so those 29 had simply moved
    into a file the curated list never opened.  The answer is the finding's
    `unconfirmed` flag and a sentence in its reasons, never a smaller score.

Both are facts about Chromium and about this run.  Neither needs a description
of who is reading, which is the whole reason the scoring could be rebuilt at
all: the previous version added points for "we patch the declaring file" and
"our source references this symbol", and those needed a description of a
second, modified tree.  Without one, every adjustment was zero and the top
bucket was unreachable.

**A score is its severity, or zero.**  Severity is what this kind of change
costs; the score is what it costs in the binary we ship, and the build rule is
the only thing between them.  Doubt about the evidence is not a cost, so it
does not change the number: the bucket and the score describe the change as if
it is real, and `unconfirmed` says the evidence for it is incomplete.  A reader
who understands the signal table understands the ranking, and the one way the
two numbers differ has a sentence next to it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .diff import bucket_of, leading_signal, SIGNAL_LABELS
from .model import (
    ADDED,
    BUCKET_ADDED,
    BUCKET_CLEANUP,
    BUCKET_ORDER,
    KIND_LABELS,
    REMOVED,
    Change,
    Finding,
    group_of,
)
from .extract._cpp import PLATFORM

# How much of a surface the new snapshot has to have read before a
# disappearance from it counts as a disappearance rather than as scope. Per
# surface, not per run: the curated files alone read 99.8% of the web API
# definitions at M151 and 1.7% of the pref and switch files, and one figure for
# both is wrong in one direction or the other. An `analysis` snapshot reads
# every surface at 98.18% or more at M143, M147, M148 and M151, so on those
# runs this flags nothing; it is here for the pair where a surface falls
# under it. A partitioned run is measured against the whole tree as well, so a
# surface it reads only inside its own roots falls under this, and its
# removals are flagged.
CONFIRMING_COVERAGE = 0.95

# Signals that are *only* an inference from absence, and say so in their own
# label. These do not merely score lower on a partial read; they are filed
# somewhere else, because "this key is not in the files we read" is not a
# report of a broken contract until the tree has been read.
UNCONFIRMED_SIGNALS = frozenset(("pref_left_scan", "switch_left_scan"))


# Which coverage row answers for a fact kind. A removal is only as believable
# as the read of the surface it was removed from, and those differ by a factor
# of fifty on the curated files: 99.8% of the web API definitions against 1.7%
# of the pref and switch files. One scalar for all of them made a vanished web
# API exactly as doubtful as a vanished preference, which is wrong in one
# direction or the other whichever number you pick.
KIND_SURFACE = {
    "base_feature": "feature flags",
    "feature_param": "feature flags",
    "blink_runtime_feature": "web platform flags",
    "idl_interface": "web API definitions",
    "idl_member": "web API definitions",
    "mojo_interface": "process-boundary interfaces",
    "mojo_method": "process-boundary interfaces",
    "mojo_struct": "process-boundary interfaces",
    "mojo_field": "process-boundary interfaces",
    "mojo_enum": "process-boundary interfaces",
    "pref": "preference keys and switches",
    "switch": "preference keys and switches",
    "flag_entry": "chrome://flags entries",
    "webui_route": "chrome:// routes",
    "webui_control": "chrome:// controls",
    "webui_gate": "chrome:// visibility gates",
}


class Scope:
    """What the run read of the new version's tree, and where it has holes.

    A removal is an absence from the new snapshot, so it is believed only as
    far as the new snapshot was read. An addition is the mirror -- an absence
    from the old one -- but it is a thing *seen* in the version being adopted,
    and "it may have existed in a file we did not open" does not make it any
    less present there. So coverage only ever doubts a removal, and the old
    snapshot is asked about holes alone: a target it did not have, or a file
    it could not parse, which are absences the run knows it produced.

    That asymmetry is the documented failure mode of this tool, not a
    hypothetical one: what goes wrong on a partial read is removals reading as
    deletions.
    """

    __slots__ = ("to_ref", "share", "surfaces", "incomplete",
                 "from_incomplete")

    def __init__(self, coverage: Optional[dict] = None,
                 to_ref: str = "", incomplete: str = "",
                 from_incomplete: str = "") -> None:
        self.to_ref = to_ref
        # The new snapshot's `meta.coverage`: the whole read, and the read of
        # each surface. Only the new side's, because coverage only ever doubts
        # a removal, so an old-side figure would be read by nothing.
        self.share = _share(coverage)
        rows = coverage.get("by_surface") if isinstance(coverage, dict) else None
        self.surfaces = ({k: _share(v) for k, v in rows.items()}
                         if isinstance(rows, dict) else {})
        # Why this run cannot confirm an absence at all, whatever it read.
        # Coverage answers "how much of the tree was in scope"; it says
        # nothing about a file that was in scope and was not there, or one
        # that was there and would not parse. Both produce exactly the shape
        # a removal has -- a fact on one side and not the other -- and both
        # are zero on every run measured so far, which is the reason to latch
        # it now rather than after the first run where they are not.
        self.incomplete = incomplete
        self.from_incomplete = from_incomplete

    def share_for(self, kind: str) -> Optional[float]:
        """The new snapshot's read of the surface this kind is declared on."""
        surface = KIND_SURFACE.get(kind)
        if surface and surface in self.surfaces:
            return self.surfaces[surface]
        # A surface with no row of its own uses the whole read, never a guess.
        return self.share

    def gap_for(self, change_type: str) -> str:
        """The hole that matters for evidence in *this* direction.

        A removal is "not in the new snapshot", so a hole in the new snapshot
        is what could have invented it; a hole in the old one could not. An
        addition is the mirror. The first version tested both at once, which
        doubted a removal for a fault on the side its evidence does not come
        from -- and did the same to additions.
        """
        if change_type == ADDED:
            return self.from_incomplete
        return self.incomplete

    def confirms_absence(self, kind: str = "",
                         change_type: str = REMOVED) -> bool:
        """Was the side this evidence rests on read well enough to believe it?

        A hole on that side settles it. Past that, an addition is believed,
        and a removal is believed as far as the new snapshot read the surface
        of its kind -- per kind, not per run, because on the curated files the
        overall figure averaged surfaces read from 1.7% to 99.8%, and using it
        doubted a web API removal seen against a near-complete read exactly as
        hard as a preference removal seen against almost none.
        """
        if self.gap_for(change_type):
            return False
        if change_type == ADDED:
            return True
        share = self.share_for(kind)
        return share is None or share >= CONFIRMING_COVERAGE

    def read_percent(self, kind: str = "") -> str:
        share = self.share_for(kind)
        if share is None:
            return "?"
        # One decimal under 1%: a partition that read 2 of 529 pref files
        # printed "0%", which reads as nothing read at all.
        pct = share * 100
        if 0 < pct < 1:
            return f"{pct:.1f}%" if pct >= 0.05 else "under 0.1%"
        return f"{pct:.0f}%"


def _share(row: Optional[dict]) -> Optional[float]:
    """read / candidates, or None when the run did not measure it.

    None means the run did not measure this, and it is treated as complete.
    Every run measures it except smoke, whose report says it cannot compare
    two versions; past that, None comes from callers with no run behind them
    -- a test, or an evaluation that states its own holes -- which want a
    change judged on its own.
    """
    if not isinstance(row, dict):
        return None
    candidates, read = row.get("candidates"), row.get("read")
    if not isinstance(candidates, int) or not candidates:
        return None
    if not isinstance(read, int):
        return None
    return max(0.0, min(1.0, read / candidates))


def _not_in_build(change: Change) -> bool:
    """True when Chromium excludes this from the Windows build on every side.

    Every side, not the newest one. The previous version read
    ``change.after or change.before``, so a feature that *left* the Windows
    build -- the case where we lose it -- was scored down 45 points for not
    being in the Windows build. A declaration entering or leaving our binary is
    the change; only one that was outside it before and after is irrelevant.
    """
    sides = [a for a in (change.before, change.after) if a]
    if not sides:
        return False
    for attrs in sides:
        states = attrs.get("platform_state")
        if not isinstance(states, dict) or states.get(PLATFORM) != "not_compiled":
            return False
    return True


def _headline(change: Change) -> str:
    """The sentence the severity came from, for the first reason line."""
    lead = leading_signal(change)
    if lead:
        return SIGNAL_LABELS.get(lead, lead)
    return (f"{change.change_type} "
            f"{KIND_LABELS.get(change.kind, change.kind).lower()}, "
            f"nothing more specific to say about it")


def score_change(change: Change, scope: Optional[Scope] = None) -> Finding:
    scope = scope or Scope()
    finding = Finding(change=change)
    reasons = [f"severity {change.severity} — {_headline(change)}"]

    # Not in our binary on any side: it cannot move anything here, so it does
    # not compete for attention, and it is filed where nothing needs doing.
    if _not_in_build(change):
        finding.score = 0
        finding.bucket = BUCKET_CLEANUP
        finding.reasons = reasons + [
            f"0 — not compiled into the {PLATFORM} build on either side of "
            f"this change, so nothing it does reaches our users"
        ]
        return finding

    bucket = bucket_of(change)

    # Both directions rest on an absence. A removal is "not in the new side";
    # an addition is "not in the old side", and a run whose *old* snapshot was
    # short of targets invents New declarations exactly as readily as a short
    # new one invents removals. An overload disappearing is a MODIFIED change and
    # was slipping past this for the same reason.
    # An overload set moving is a MODIFIED change resting on an absence, and
    # which side depends on which way it moved: an entry gone is an absence
    # from the new snapshot, an entry gained is an absence from the old one.
    # Treating every `signatures` delta as a removal asked the wrong side of
    # every overload addition -- found by testing all four evidence shapes
    # against all four holes rather than the four combinations I had picked.
    direction = change.change_type
    if "signatures" in change.deltas:
        was, now = change.deltas["signatures"]
        direction = REMOVED if set(was or ()) - set(now or ()) else ADDED
    rests_on_absence = (direction == REMOVED
                        or (direction == ADDED and scope.from_incomplete))
    if rests_on_absence and not scope.confirms_absence(change.kind, direction):
        # A flag and a sentence, and the score is left alone. A fixed 15-point
        # deduction sat here and changed no row of an `analysis` run at
        # M148 -> M151, while on a hole it could take a severity-10 addition
        # to 0 -- the number that means "not in the Windows build".
        #
        # The flag is set wherever this doubt is, not only where the filing
        # also moves: scoped to the two `*_left_scan` signals it named 31 of
        # the 303 doubted rows at M148 -> M151 on the curated files, and left
        # out 120 Compatibility breaks, the bucket read first.
        finding.unconfirmed = True
        gap = scope.gap_for(direction)
        if gap:
            why = (f"unconfirmed: {gap}, so the absence this row rests on may "
                   f"come from those files rather than from Chromium")
        else:
            why = (f"unconfirmed: this run read "
                   f"{scope.read_percent(change.kind)} of that surface at "
                   f"{scope.to_ref or 'the new version'}, so \"gone\" may mean "
                   f"\"moved into a file we never opened\"")
        # For the two signals that are *only* an absence inference, the doubt
        # decides the filing as well as the number. `pref_left_scan` says
        # "deleted, or moved out of the files we read" in its own label; on a
        # partial run the second reading is the likelier one, and 139 of these
        # at the top of an M148 -> M151 report -- 29 of which a full run
        # shows had simply moved -- is how a list stops being read.
        #
        # Only these two move bucket. Every row in this branch already carries
        # `unconfirmed`; the bucket says what the evidence supports, the flag
        # says the evidence is short, and they are not the same statement.
        if leading_signal(change) in UNCONFIRMED_SIGNALS:
            bucket = BUCKET_CLEANUP
            why += "; filed as upstream cleanup rather than a compatibility break"
        # No advice about reading more in the row: an analysis run already
        # fetches every target there is, and on a partitioned run the sentence
        # gives the share of the tree the run read.
        reasons.append(why)

    if (direction == ADDED and bucket == BUCKET_ADDED
            and scope.from_incomplete):
        # "New declarations" asserts the thing was not there before, which is
        # the very claim a hole in the old side leaves unproven, so the row
        # moves rather than keep a label its own flag contradicts.
        #
        # Only for a hole -- a target the old side did not have, a file that
        # would not parse -- and never for partial coverage. An addition is a
        # thing *seen*, and "it may have existed in a file we did not open"
        # does not make it any less present in the version being adopted;
        # applying coverage doubt here emptied the bucket entirely, which is
        # the failure this scoring was rebuilt to remove.
        bucket = BUCKET_CLEANUP
        finding.unconfirmed = True
        reasons.append(
            "filed as upstream cleanup rather than a new declaration: this "
            "run cannot show it was absent before")

    finding.score = change.severity
    finding.bucket = bucket
    finding.reasons = reasons
    return finding


def score_all(changes: Sequence[Change],
              scope: Optional[Scope] = None) -> List[Finding]:
    findings = [score_change(c, scope) for c in changes]
    findings.sort(key=lambda f: (-f.score, f.change.kind, f.change.key))
    return findings


def summarize_findings(findings: Sequence[Finding]) -> Dict[str, object]:
    """The counts a report header needs, and what each of them covers.

    `by_bucket` and `by_group` are partitions: every finding is in exactly one
    bucket and one group, so each adds up to the total and a reader can treat
    them as the report rather than as highlights.

    `by_signal` is not, and reading it as one has gone wrong twice. A finding
    can carry no signal at all -- 981 of 3,022 at M148 -> M151 -- so the sum
    is the findings that carry one, and the number of keys is the distinct
    leading signals, not the number of groups the report prints. *What
    happened* falls back to the kind and the direction for the rest, which is
    why that section partitions and this tally does not.
    """
    by_bucket: Dict[str, int] = {b: 0 for b in BUCKET_ORDER}
    by_group: Dict[str, int] = {}
    by_signal: Dict[str, int] = {}
    for finding in findings:
        by_bucket[finding.bucket] = by_bucket.get(finding.bucket, 0) + 1
        group = group_of(finding.change.kind)
        if group:
            by_group[group] = by_group.get(group, 0) + 1
        lead = leading_signal(finding.change)
        if lead:
            by_signal[lead] = by_signal.get(lead, 0) + 1
    return {
        "total": len(findings),
        "by_bucket": by_bucket,
        "by_group": by_group,
        "by_signal": dict(sorted(by_signal.items(), key=lambda kv: -kv[1])),
        # Counted from the condition, not from `score == 0`, so the sentence
        # the report prints beside it is exactly true whatever else the
        # scoring does.
        "not_in_build": sum(1 for f in findings if _not_in_build(f.change)),
        # Not a partition -- an `unconfirmed` finding is already counted in
        # its bucket. It is here because it is the one number that says how
        # much of this report is limited by what the run read rather than by
        # what Chromium did, and a full run is expected to drive it to zero.
        "unconfirmed": sum(1 for f in findings if f.unconfirmed),
    }
