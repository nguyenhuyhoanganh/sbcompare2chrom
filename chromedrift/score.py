"""Rank the changes, and say why each one ranks where it does.

`diff.py` answers *what happened* and how much that kind of thing normally
costs.  This stage answers the two questions left, both of which depend on the
run rather than on the change:

  * **Is it in the binary we ship?**  Chromium wraps declarations in
    ``#if BUILDFLAG(IS_WIN)`` chains, and 146 declarations at M151 resolve to
    "not on Windows".  A change to one of those cannot move anything here.
  * **Did this run read enough of the tree to believe a removal?**  A removal
    is an inference from absence, and absence from a tree the run read a
    twentieth of is a much weaker claim than absence from one it read all of.
    Measured M148 -> M151 on the default set: of 141 preference keys that
    vanished, 100 had simply moved into a file the run never opened.

Both are facts about Chromium and about this run.  Neither needs a description
of who is reading, which is the whole reason the scoring could be rebuilt at
all: the previous version added points for "we patch the declaring file" and
"our source references this symbol", and those needed a description of a
second, modified tree.  Without one, every adjustment was zero, the top bucket
was unreachable, and the ranking was a second copy of the severity.

**Nothing raises a score.**  Severity is the ceiling -- the most this kind of
change can cost -- and the modifiers only take away, for reasons that are
stated on the finding.  So a reader who understands the signal table
understands the ranking, and every point of difference between the two numbers
has a sentence next to it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .diff import bucket_of, leading_signal, SIGNAL_LABELS
from .model import (
    BUCKET_HOUSEKEEPING,
    BUCKET_ORDER,
    KIND_LABELS,
    REMOVED,
    Change,
    Finding,
    group_of,
)
from .extract._cpp import PLATFORM

# How much of a version's tree a run has to have read before a disappearance
# from it counts as a disappearance rather than as scope. `wide` reads all of
# it; `default` reads about a twentieth.
CONFIRMING_COVERAGE = 0.95

# What an unconfirmed removal loses. Flat rather than scaled by the coverage
# share, and this is deliberate: coverage is measured in *files*, and the whole
# reason the default set is worth running is that file count is not declaration
# count -- it reads 5% of the files and more than half of the base::Feature
# declarations. Treating 5% as a probability would say a default run knows
# almost nothing, which is false and would flatten two thirds of the report
# into a band six points wide. A fixed step keeps the order inside the group
# and moves the group.
#
# Sized against the severity table, whose own steps are 5 and whose meaningful
# gaps are 10 to 15: enough to sort an unconfirmed removal below a
# modification of the same weight -- the modification was seen on both sides --
# and not enough to bury a Mojo removal in ordinary churn.
UNCONFIRMED_PENALTY = 15

# Signals that are *only* an inference from absence, and say so in their own
# label. These do not merely score lower on a partial read; they are filed
# somewhere else, because "this key is not in the files we read" is not a
# report of a broken contract until the tree has been read.
UNCONFIRMED_SIGNALS = frozenset(("pref_left_scan", "switch_left_scan"))


class Scope:
    """How much of the new version's tree the run read.

    Only the new side matters, and only for removals. A fact absent from the
    new snapshot is a removal only if the new tree was read; the same argument
    does not run backwards, because an addition is a thing seen rather than a
    thing not seen, and "it may have existed in a file we did not open" does
    not make it any less present in the version being adopted.

    That asymmetry is the documented failure mode of this tool, not a
    hypothetical one: what goes wrong on a partial read is removals reading as
    deletions.
    """

    __slots__ = ("to_ref", "to_share")

    def __init__(self, coverage: Optional[dict] = None,
                 to_ref: str = "") -> None:
        self.to_ref = to_ref
        self.to_share = _share((coverage or {}).get("to"))

    def confirms_absence(self) -> bool:
        """Was the new tree read completely enough to call an absence real?"""
        return self.to_share is None or self.to_share >= CONFIRMING_COVERAGE

    def read_percent(self) -> str:
        return "?" if self.to_share is None else f"{self.to_share * 100:.0f}%"


def _share(row: Optional[dict]) -> Optional[float]:
    """read / candidates, or None when the run did not measure it.

    None means "unknown", and unknown is treated as complete on purpose: the
    alternative is to discount every finding of a run that could not measure
    itself, which turns a missing measurement into a silent, uniform downgrade
    of the whole report.
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
        finding.bucket = BUCKET_HOUSEKEEPING
        finding.reasons = reasons + [
            f"0 — not compiled into the {PLATFORM} build on either side of "
            f"this change, so nothing it does reaches our users"
        ]
        return finding

    score = change.severity
    bucket = bucket_of(change)

    if change.change_type == REMOVED and not scope.confirms_absence():
        score -= UNCONFIRMED_PENALTY
        why = (f"-{UNCONFIRMED_PENALTY} unconfirmed: this run read "
               f"{scope.read_percent()} of the tree at "
               f"{scope.to_ref or 'the new version'}, so \"gone\" may mean "
               f"\"moved into a file we never opened\"")
        # For the two signals that are *only* an absence inference, the doubt
        # decides the filing as well as the number. `pref_left_scan` says
        # "deleted, or moved out of the files we read" in its own label; on a
        # partial run the second reading is the likelier one, and 139 of these
        # at the top of an M148 -> M151 report -- roughly 100 of which had
        # simply moved -- is how a list stops being read.
        if leading_signal(change) in UNCONFIRMED_SIGNALS:
            bucket = BUCKET_HOUSEKEEPING
            why += "; filed as housekeeping rather than breaking"
        reasons.append(why + " — --target-set wide settles it")

    finding.score = max(0, min(100, score))
    finding.bucket = bucket
    finding.reasons = reasons
    return finding


def score_all(changes: Sequence[Change],
              scope: Optional[Scope] = None) -> List[Finding]:
    findings = [score_change(c, scope) for c in changes]
    findings.sort(key=lambda f: (-f.score, f.change.kind, f.change.key))
    return findings


def summarize_findings(findings: Sequence[Finding]) -> Dict[str, object]:
    """The counts a report header needs, each of them a partition of the whole.

    Every finding appears in exactly one bucket, one group and one signal
    tally, so each of these adds up to the total and a reader can treat the
    counts as the report rather than as highlights.
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
    }
