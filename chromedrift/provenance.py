"""Tell deliberate divergence apart from merge debt.

A fork built the way most vendor browsers are built -- take all of Chromium,
modify it, then every few milestones merge a newer Chromium and fix the
conflicts -- accumulates two kinds of difference that look identical in a
two-way diff:

* **A decision.** Someone changed this on purpose and means to keep it.
* **Debt.** A merge dropped or missed an upstream change, and nobody noticed.

Both read as "our value differs from upstream". Only the second one is a
problem, and after enough merges nobody remembers which is which.

The way to separate them is provenance. Compare the fork not against one
upstream version but against the *series* of versions it was merged from. If
our value matches an older Chromium exactly, we did not decide anything -- we
are simply stale, and the diff names the milestone we are stuck on. If our
value matches no upstream version at all, someone wrote it, and that is a
decision worth carrying forward.

Snapshots make this affordable: each upstream version is ~40 MB and cached
forever, so a five-version history costs one slow run and then nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .diff import meaningful_attrs
from .model import Fact, Snapshot

# Classification of one fact in the fork, relative to the upstream series.
IN_SYNC = "in_sync"            # matches the version we claim to be based on
STALE = "stale"                # matches an OLDER upstream version -- merge debt
DIVERGED = "diverged"          # matches no upstream version -- our decision
# The base has it and we do not. Which of the two this is depends on when
# upstream introduced it, and the series is what tells them apart:
MISSING_NEW = "missing_new"    # arrived during the series; a merge never took it
MISSING_OLD = "missing_old"    # present since the oldest version; we dropped it
VENDOR_ONLY = "vendor_only"    # only we have it

STATES = (IN_SYNC, STALE, DIVERGED, MISSING_NEW, MISSING_OLD, VENDOR_ONLY)

# Which states are debt (something slipped) versus a decision (someone chose).
DEBT_STATES = (STALE, MISSING_NEW)
DECISION_STATES = (DIVERGED, MISSING_OLD, VENDOR_ONLY)

STATE_LABELS = {
    IN_SYNC: "In sync with the base version",
    STALE: "Stale — our value matches an older Chromium; a merge missed this",
    DIVERGED: "Diverged — matches no upstream version; someone changed it",
    MISSING_NEW: "Never taken — upstream added this during the version range "
                 "we merged through, and no merge picked it up",
    MISSING_OLD: "Removed — upstream has always had it; we dropped it",
    VENDOR_ONLY: "Ours only — no upstream equivalent",
}


def _same(a: Fact, b: Fact) -> bool:
    return meaningful_attrs(a) == meaningful_attrs(b)


@dataclass
class Verdict:
    uid: str
    kind: str
    key: str
    state: str
    matches: str = ""          # which upstream version our value matches
    first_seen: str = ""       # earliest upstream version that has this fact
    base_has: bool = False
    detail: str = ""

    def is_debt(self) -> bool:
        return self.state in DEBT_STATES

    def to_dict(self) -> dict:
        return {
            "uid": self.uid, "kind": self.kind, "key": self.key,
            "state": self.state, "matches": self.matches,
            "first_seen": self.first_seen, "base_has": self.base_has,
            "detail": self.detail, "debt": self.is_debt(),
        }


@dataclass
class ProvenanceReport:
    fork_ref: str
    base_ref: str
    history: List[str] = field(default_factory=list)
    verdicts: List[Verdict] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        out = {s: 0 for s in STATES}
        for v in self.verdicts:
            out[v.state] = out.get(v.state, 0) + 1
        return out

    def debt(self) -> List[Verdict]:
        return [v for v in self.verdicts if v.is_debt()]

    def stale_by_version(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.verdicts:
            if v.state == STALE and v.matches:
                out[v.matches] = out.get(v.matches, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def to_dict(self) -> dict:
        return {
            "fork_ref": self.fork_ref,
            "base_ref": self.base_ref,
            "history": self.history,
            "counts": self.counts(),
            "stale_by_version": self.stale_by_version(),
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


def analyze(fork: Snapshot, upstream: Sequence[Snapshot],
            base_ref: Optional[str] = None) -> ProvenanceReport:
    """Classify every fact in ``fork`` against an ordered upstream series.

    ``upstream`` must be ordered oldest first. ``base_ref`` is the version the
    fork claims to be based on; it defaults to the newest one supplied.
    """
    if not upstream:
        raise ValueError("provenance needs at least one upstream snapshot")

    series = list(upstream)
    base = next((s for s in series if s.ref == base_ref), series[-1])
    indexes: List[Tuple[str, Dict[str, Fact]]] = [(s.ref, s.index()) for s in series]
    base_index = base.index()
    fork_index = fork.index()

    report = ProvenanceReport(fork_ref=fork.ref, base_ref=base.ref,
                              history=[s.ref for s in series])

    for uid, our in fork_index.items():
        first_seen = next((ref for ref, idx in indexes if uid in idx), "")
        theirs = base_index.get(uid)

        if theirs is not None and _same(our, theirs):
            state, matches = IN_SYNC, base.ref
        else:
            # Newest first: if we match several versions, report the newest,
            # because that is how far behind we actually are.
            matches = ""
            for ref, idx in reversed(indexes):
                candidate = idx.get(uid)
                if candidate is not None and _same(our, candidate):
                    matches = ref
                    break
            if matches and matches != base.ref:
                state = STALE
            elif theirs is None and not first_seen:
                state, matches = VENDOR_ONLY, ""
            else:
                state, matches = DIVERGED, ""

        report.verdicts.append(Verdict(
            uid=uid, kind=our.kind, key=our.key, state=state, matches=matches,
            first_seen=first_seen, base_has=theirs is not None,
        ))

    # Facts the base has and we do not. Whether that is debt or a decision
    # depends on when upstream introduced it: something that appeared partway
    # through the series is something a merge should have brought along and did
    # not, while something present since the oldest version in the series is
    # something we once had and removed.
    oldest_ref, oldest_index = indexes[0]
    for uid, theirs in base_index.items():
        if uid in fork_index:
            continue
        in_oldest = uid in oldest_index
        report.verdicts.append(Verdict(
            uid=uid, kind=theirs.kind, key=theirs.key,
            state=MISSING_OLD if in_oldest else MISSING_NEW,
            first_seen=oldest_ref if in_oldest else "",
            base_has=True,
            detail=("present since " + oldest_ref) if in_oldest
            else f"introduced after {oldest_ref} and present in {base.ref}",
        ))

    report.verdicts.sort(key=lambda v: (STATES.index(v.state), v.kind, v.key))
    return report


def summarize(report: ProvenanceReport, limit: int = 15) -> List[str]:
    """Human-readable headline lines for the report."""
    counts = report.counts()
    total = len(report.verdicts)
    debt = len(report.debt())
    lines = [
        f"{total} facts compared, {debt} look like merge debt "
        f"({debt * 100 // max(1, total)}%)",
    ]
    for state in STATES:
        if counts.get(state):
            lines.append(f"  {state:14s} {counts[state]:6d}  {STATE_LABELS[state]}")
    stale = report.stale_by_version()
    if stale:
        lines.append("  stale against:")
        for ref, n in list(stale.items())[:limit]:
            lines.append(f"    {ref:28s} {n} facts still match this version")
    return lines
