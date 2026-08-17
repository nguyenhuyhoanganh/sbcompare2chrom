"""Score each change against the downstream profile and bucket it.

Severity from `diff.py` answers "how much does this normally matter".  This
stage answers the question the team actually has: **does it matter to us**.

The scoring is deliberately transparent rather than clever.  Every adjustment
appends a human-readable reason, so a reviewer can see why something landed in
"Must fix" and can argue with it.  A ranking nobody can audit gets ignored the
first time it is wrong, and this ranking also decides what the AI stage spends
its context on -- so an unexplained score would propagate into an unexplained
recommendation.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .model import (
    ADDED,
    BUCKET_FYI,
    BUCKET_MUST_FIX,
    BUCKET_OPPORTUNITY,
    BUCKET_REVIEW,
    MODE_FORK,
    MODE_UPREV,
    Change,
    Finding,
)
from .sbprofile import TouchSet, change_tokens

# Signals that mean "someone has to do something", regardless of score, once
# there is any downstream evidence attached.
BREAKING_SIGNALS = {
    "ipc_signature_change",
    "ipc_removed",
    "feature_deleted",
    # A retired flag changes nothing by itself, but if we named the symbol our
    # build stops compiling and our override silently stops applying.
    "flag_retired_on",
    "flag_retired_off",
    "pref_renamed",
    "switch_renamed",
    "web_api_removed",
    "killswitch_retired",
}

# Signals that describe new capability rather than breakage.
OPPORTUNITY_SIGNALS = {
    "web_api_shipped",
    "web_api_added",
    "new_feature_on_by_default",
}

# Fork mode inverts what "added" and "removed" mean, and the bucket names have
# to follow. A fact the vendor added is not a capability on offer -- it is
# divergence the team already owns and has to keep carrying through every
# rebase. Bucketing it as "New opportunity" tells the team their own
# customization is something they might like to adopt.
FORK_CARRY_SIGNALS = {
    "fork_dropped",            # a rebase silently puts it back
    "fork_default_override",   # a rebase silently reverts the default
    "fork_ui_removed",
}

# Symbol evidence outweighs path evidence on purpose.  Patching a file that
# declares two hundred features says almost nothing about which of them we
# depend on; touching the feature's own identifier says a great deal.
PATH_MATCH_BONUS = 12
SYMBOL_MATCH_BONUS = 30
AREA_WEIGHT_FACTOR = 0.20      # area weight 0-100 -> up to +20
NOT_COMPILED_PENALTY = 45
NOISE_PENALTY = 12


def _platform_applicable(change: Change, platform: str) -> Optional[bool]:
    """False when the change provably does not compile on our platform."""
    attrs = change.after or change.before or {}
    states = attrs.get("platform_state")
    if isinstance(states, dict) and platform in states:
        if states[platform] == "not_compiled":
            return False
        return True
    statuses = attrs.get("platform_status")
    if isinstance(statuses, dict) and platform in statuses:
        return True
    return None


def score_change(change: Change, touch: TouchSet,
                 mode: str = MODE_UPREV) -> Finding:
    finding = Finding(change=change)
    score = change.severity
    reasons: List[str] = [
        f"base severity {change.severity} ({change.change_type} {change.kind})"
    ]

    tokens = change_tokens(change)
    matched_paths = touch.match_paths(change.paths)
    matched_symbols = touch.match_symbols(tokens)
    areas = touch.match_areas(change, tokens)

    finding.matched_paths = matched_paths
    finding.matched_symbols = matched_symbols
    finding.areas = [a.id for a in areas]

    if matched_paths:
        score += PATH_MATCH_BONUS
        reasons.append(
            f"+{PATH_MATCH_BONUS} we patch {len(matched_paths)} of the declaring "
            f"file(s): {', '.join(matched_paths[:3])}"
        )
    if matched_symbols:
        score += SYMBOL_MATCH_BONUS
        reasons.append(
            f"+{SYMBOL_MATCH_BONUS} our source references "
            f"{', '.join(matched_symbols[:3])}"
        )
    if areas:
        top = max(areas, key=lambda a: a.weight)
        bonus = int(round(top.weight * AREA_WEIGHT_FACTOR))
        score += bonus
        reasons.append(f"+{bonus} owned area '{top.title or top.id}' (weight {top.weight})")

    applicable = _platform_applicable(change, touch.platform)
    if applicable is False:
        score -= NOT_COMPILED_PENALTY
        reasons.append(
            f"-{NOT_COMPILED_PENALTY} not compiled on {touch.platform}")

    if any(touch.is_ignored(p) for p in change.paths) and change.paths:
        score -= NOT_COMPILED_PENALTY
        reasons.append(f"-{NOT_COMPILED_PENALTY} in an ignored path")

    # Experimental churn is the bulk of any Chromium diff and almost never
    # actionable on its own; keep it visible but out of the way.
    if ("experimental_dropped" in change.signals and not matched_symbols
            and not matched_paths):
        score -= NOISE_PENALTY
        reasons.append(f"-{NOISE_PENALTY} experimental flag churn, no local reference")

    score = max(0, min(100, score))
    finding.score = score
    finding.reasons = reasons
    finding.bucket = _bucket(change, finding, score, mode)
    return finding


def _bucket(change: Change, finding: Finding, score: int,
            mode: str = MODE_UPREV) -> str:
    # Only symbol-level evidence is specific enough to promote something to
    # "must fix" on its own; a path match means "somewhere in a file we also
    # touch", which is a reason to look, not a reason to act.
    evidence = bool(finding.matched_symbols)
    weak_evidence = bool(finding.matched_paths)

    if mode == MODE_FORK:
        # Nothing in a fork comparison is an opportunity: both sides are code
        # that already exists, and every difference is either ours to defend or
        # upstream's to absorb.
        breaking = bool(set(change.signals) & FORK_CARRY_SIGNALS)
        opportunity = False
    else:
        breaking = bool(set(change.signals) & BREAKING_SIGNALS)
        opportunity = bool(set(change.signals) & OPPORTUNITY_SIGNALS) or (
            change.change_type == ADDED)

    if evidence and (breaking or score >= 60):
        return BUCKET_MUST_FIX
    if (evidence or weak_evidence) and score >= 35:
        return BUCKET_REVIEW
    # New capability is classified by what it *is*, not by how it scores.  A
    # web API reaching stable scores highly because it is significant, but it
    # is "here is what your users just got", not "here is what might break" --
    # and 150 of those drowning the review list is how a triage tool becomes
    # something people stop opening.
    if opportunity and not breaking:
        return BUCKET_OPPORTUNITY
    if score >= 65:
        # High intrinsic severity with no known local dependency still needs a
        # human to confirm the dependency really is absent.
        return BUCKET_REVIEW
    return BUCKET_FYI


def score_all(changes: List[Change], touch: TouchSet,
              mode: str = MODE_UPREV) -> List[Finding]:
    findings = [score_change(c, touch, mode) for c in changes]
    findings.sort(key=lambda f: (-f.score, f.change.kind, f.change.key))
    return findings


def area_coverage(findings: List[Finding], touch: Optional[TouchSet] = None
                  ) -> Dict[str, object]:
    """Per-area counts plus what fell outside every area.

    The unassigned count is not a footnote. Scoping a report by area while
    silently dropping whatever matched nothing is the surest way to lose
    findings: on M148 -> M151 the unassigned set held 281 findings scoring 60+,
    including the ten most severe in the whole report. Reporting the number
    makes both the gap and the quality of the area definitions visible.
    """
    rows: Dict[str, Dict[str, object]] = {}
    unassigned: List[Finding] = []

    for finding in findings:
        if not finding.areas:
            unassigned.append(finding)
            continue
        for area_id in finding.areas:
            row = rows.setdefault(area_id, {"total": 0, "actionable": 0, "top_score": 0})
            row["total"] = int(row["total"]) + 1
            if finding.bucket in (BUCKET_MUST_FIX, BUCKET_REVIEW):
                row["actionable"] = int(row["actionable"]) + 1
            row["top_score"] = max(int(row["top_score"]), finding.score)

    if touch is not None:
        for area_id, row in rows.items():
            area = touch.area_by_id(area_id)
            if area:
                row["title"] = area.title or area.id
                row["owner"] = area.owner
                row["kind"] = area.kind

    return {
        "areas": dict(sorted(rows.items(), key=lambda kv: -int(kv[1]["total"]))),
        "unassigned": {
            "total": len(unassigned),
            "actionable": sum(1 for f in unassigned
                              if f.bucket in (BUCKET_MUST_FIX, BUCKET_REVIEW)),
            "scoring_60_plus": sum(1 for f in unassigned if f.score >= 60),
            "top_score": max((f.score for f in unassigned), default=0),
        },
    }


def summarize_findings(findings: List[Finding],
                       touch: Optional[TouchSet] = None) -> Dict[str, object]:
    by_bucket: Dict[str, int] = {}
    by_area: Dict[str, int] = {}
    by_signal: Dict[str, int] = {}
    for finding in findings:
        by_bucket[finding.bucket] = by_bucket.get(finding.bucket, 0) + 1
        for area in finding.areas:
            by_area[area] = by_area.get(area, 0) + 1
        for signal in finding.change.signals:
            by_signal[signal] = by_signal.get(signal, 0) + 1
    return {
        "total": len(findings),
        "by_bucket": by_bucket,
        "by_area": dict(sorted(by_area.items(), key=lambda kv: -kv[1])),
        "by_signal": dict(sorted(by_signal.items(), key=lambda kv: -kv[1])),
        "with_evidence": sum(
            1 for f in findings if f.matched_paths or f.matched_symbols),
        "coverage": area_coverage(findings, touch),
    }
