"""Markdown report: the artifact a team pastes into a ticket or a wiki.

Ordered by what a reader needs first -- the triage counts, then the work, then
the evidence.  Every finding shows the reasons behind its score, because a
triage list that cannot be argued with is a triage list that gets ignored.

Nothing here states a verdict.  The report carries evidence and a rank; the
judgement is made by whoever reads it, which is why the score reasoning and the
declaring paths are always present rather than summarized away.
"""

from __future__ import annotations

from typing import List, Sequence

from ..diff import SIGNAL_LABELS
from ..model import (
    BUCKET_LABELS,
    BUCKET_MUST_FIX,
    BUCKET_OPPORTUNITY,
    BUCKET_ORDER,
    BUCKET_REVIEW,
    KIND_LABELS,
    MODE_FORK,
    MODE_UPREV,
    Finding,
    Report,
)

# The same table means two different things depending on which comparison ran,
# and the wording is what tells a reader which one they are holding. Titling a
# fork comparison "uprev impact" and offering the vendor's own customizations
# as "new capability we could adopt" is not a cosmetic slip -- it inverts the
# reading of every row.
MODE_TITLES = {
    MODE_UPREV: "Chromium uprev impact",
    MODE_FORK: "Fork divergence from upstream",
}

MODE_SUBTITLES = {
    MODE_FORK: "Comparison runs **upstream → our fork** at the same milestone. "
               "Everything below is a difference we own: *removed* means we "
               "dropped something upstream still has, *added* means we carry "
               "something upstream does not.",
}

_BUCKET_MEANINGS = {
    MODE_UPREV: {
        BUCKET_MUST_FIX: "We touch this and it changed. Assume work is needed.",
        BUCKET_REVIEW: "Either we touch it, or it is severe enough to confirm.",
        BUCKET_OPPORTUNITY: "New capability we could adopt.",
        "fyi": "Recorded for completeness.",
    },
    MODE_FORK: {
        BUCKET_MUST_FIX: "Divergence we depend on. A rebase undoes it silently "
                         "unless a patch carries it.",
        BUCKET_REVIEW: "Divergence with no clear owner. Decide: keep it, or "
                       "take upstream's version.",
        BUCKET_OPPORTUNITY: "Not used in a fork comparison.",
        "fyi": "Recorded for completeness.",
    },
}


def mode_of(report: Report) -> str:
    mode = (report.meta or {}).get("mode") or MODE_UPREV
    return mode if mode in MODE_TITLES else MODE_UPREV


def _esc(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


# For these kinds the bare name is ambiguous -- several interfaces declare an
# `echoCancellation` member -- so the qualified key is what identifies it.
_QUALIFIED_KINDS = ("idl_member", "mojo_method")


def display_name(change) -> str:
    return change.key if change.kind in _QUALIFIED_KINDS else change.name


def _cell(value: object, limit: int = 60) -> str:
    """Table cells must stay readable.

    A Mojo signature can run past 400 characters; pasted into a table it
    destroys the row and the reader learns nothing anyway. The full value is
    always in the details block below.
    """
    text = _esc(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _state_arrow(finding: Finding, platform: str) -> str:
    change = finding.change
    for key in ("platform_state", "platform_status"):
        delta = change.deltas.get(key)
        if isinstance(delta, list) and len(delta) == 2:
            old = (delta[0] or {}).get(platform, "?") if isinstance(delta[0], dict) else "?"
            new = (delta[1] or {}).get(platform, "?") if isinstance(delta[1], dict) else "?"
            if old != new:
                return f"{old} → {new}"
    for key in ("default_state", "status", "signature", "value"):
        delta = change.deltas.get(key)
        if isinstance(delta, list) and len(delta) == 2:
            return f"{_cell(delta[0], 46)} → {_cell(delta[1], 46)}"
    return change.change_type


def _signals(finding: Finding) -> str:
    return ", ".join(SIGNAL_LABELS.get(s, s) for s in finding.change.signals) or "—"


def _evidence(finding: Finding) -> str:
    bits = []
    if finding.matched_paths:
        bits.append(f"patches {len(finding.matched_paths)} file(s)")
    if finding.matched_symbols:
        bits.append(f"refs {', '.join(finding.matched_symbols[:2])}")
    return "; ".join(bits) or "—"


def render(report: Report, platform: str = "windows",
           detail_limit: int = 40) -> str:
    out: List[str] = []
    counts = report.bucket_counts()
    summary = report.summary or {}

    mode = mode_of(report)
    out.append(f"# {MODE_TITLES[mode]}: {report.from_ref} → {report.to_ref}")
    out.append("")
    meta = report.meta or {}
    out.append(
        f"Product: **{meta.get('product', 'downstream browser')}** · "
        f"platform **{platform}** · generated {meta.get('generated', '')}"
    )
    out.append("")
    if MODE_SUBTITLES.get(mode):
        out.append(MODE_SUBTITLES[mode])
        out.append("")

    out.append("## Triage")
    out.append("")
    out.append("| Bucket | Count | Meaning |")
    out.append("|---|---:|---|")
    meanings = _BUCKET_MEANINGS[mode]
    for bucket in BUCKET_ORDER:
        # A bucket a mode never fills would only add a confusing empty row.
        if mode == MODE_FORK and bucket == BUCKET_OPPORTUNITY \
                and not counts.get(bucket, 0):
            continue
        out.append(f"| {BUCKET_LABELS[bucket]} | {counts.get(bucket, 0)} | "
                   f"{meanings.get(bucket, '')} |")
    out.append("")

    stats = summary.get("changes") or {}
    if stats:
        out.append(f"Scanned {stats.get('total', 0)} semantic changes across "
                   f"{len(stats.get('by_kind', {}))} surface types; "
                   f"{summary.get('with_evidence', 0)} intersect our fork.")
        out.append("")

    out.append(_render_clusters(summary))
    out.append(_render_coverage(summary))
    out.append(_render_milestone_brief(summary))

    # -- buckets --------------------------------------------------------
    for bucket in (BUCKET_MUST_FIX, BUCKET_REVIEW, BUCKET_OPPORTUNITY):
        findings = report.by_bucket(bucket)
        if not findings:
            continue
        out.append(f"## {BUCKET_LABELS[bucket]} ({len(findings)})")
        out.append("")
        out.append("| Score | Change | Surface | What moved | Our evidence |")
        out.append("|---:|---|---|---|---|")
        for finding in findings[:detail_limit]:
            out.append(
                f"| {finding.score} | `{_esc(display_name(finding.change))}` "
                f"| {KIND_LABELS.get(finding.change.kind, finding.change.kind)} "
                f"| {_esc(_state_arrow(finding, platform))} "
                f"| {_esc(_evidence(finding))} |"
            )
        if len(findings) > detail_limit:
            out.append(f"| … | _{len(findings) - detail_limit} more_ | | | |")
        out.append("")

        if bucket in (BUCKET_MUST_FIX, BUCKET_REVIEW):
            out.append(_render_details(findings[:detail_limit], platform))

    # -- appendix -------------------------------------------------------
    out.append("## How this was produced")
    out.append("")
    out.append(_render_provenance(report))
    return "\n".join(out)


def _render_clusters(summary: dict) -> str:
    """Related findings, grouped into one story each.

    Read individually, the fragments of one upstream change contradict each
    other -- a page removed here, a page added there. Grouped, they read as
    what actually happened.
    """
    rows = (summary or {}).get("clusters") or []
    rows = [r for r in rows if r.get("size", 0) > 1][:12]
    if not rows:
        return ""
    out = ["## Related changes, grouped", "",
           "Each row is one upstream change arriving across several surfaces. "
           "Read the group, not the individual rows.", "",
           "| Top score | Story | Fragments | Surfaces |",
           "|---:|---|---:|---|"]
    for r in rows:
        kinds = ", ".join(KIND_LABELS.get(k, k) for k in r.get("kinds", []))
        out.append(f"| {r.get('top_score', 0)} | `{_cell(r.get('label', ''), 44)}` "
                   f"| {r.get('size', 0)} | {_cell(kinds, 70)} |")
    out.append("")
    return "\n".join(out)


def _render_coverage(summary: dict) -> str:
    """Where findings landed by area, and how many landed nowhere.

    The unassigned row is the point of this section. Routing a report to teams
    by area quietly drops whatever matched no area, and that leftover is where
    cross-cutting infrastructure changes live -- often the most severe ones.
    """
    coverage = (summary or {}).get("area_coverage") or {}
    areas = coverage.get("areas") or {}
    unassigned = coverage.get("unassigned") or {}
    if not areas and not unassigned.get("total"):
        return ""

    out = ["## Coverage by area", ""]
    if summary.get("filtered_to_area"):
        out.insert(0, "")
        out.insert(0, f"> Showing only area **{summary['filtered_to_area']}** — "
                      f"{summary.get('filtered_from_total', '?')} findings in the "
                      f"full report.")
    out.append("| Area | Findings | Actionable | Kind | Owner |")
    out.append("|---|---:|---:|---|---|")
    for area_id, row in areas.items():
        out.append(f"| {area_id} | {row.get('total', 0)} | "
                   f"{row.get('actionable', 0)} | {row.get('kind', '')} | "
                   f"{row.get('owner', '')} |")
    total = unassigned.get("total", 0)
    if total:
        out.append(f"| **_unassigned** | **{total}** | "
                   f"**{unassigned.get('actionable', 0)}** | — | **nobody** |")
    out.append("")
    if unassigned.get("scoring_60_plus"):
        out.append(
            f"⚠️ {unassigned['scoring_60_plus']} unassigned findings score 60 or "
            f"more (highest: {unassigned.get('top_score', 0)}). These belong to "
            f"no area, so no per-area report shows them. Either extend the area "
            f"definitions or review this set explicitly."
        )
        out.append("")
    out.append("Re-render one area with "
               "`chromedrift report <report.json> --area <id>`.")
    out.append("")
    return "\n".join(out)


def _render_milestone_brief(summary: dict, limit: int = 200) -> str:
    """What Chromium says it shipped in this window.

    This used to exist only as context inside the model prompt. With the
    judging stage gone, the report *is* what a reader reasons over, so the
    grounding has to live here instead -- otherwise the one source that says
    what upstream intended is fetched, paid for, and thrown away.

    Folded into a `<details>` block because it is background, not findings: a
    reader scanning for work should step over it, and a reader trying to
    explain a change should find it without another network call.
    """
    entries = (summary or {}).get("milestone_brief") or []
    if not entries:
        return ""
    out = ["## What Chromium says shipped in this window", "",
           f"<details><summary>{len(entries)} features from chromestatus</summary>",
           ""]
    for entry in entries[:limit]:
        head = f"- **M{entry.get('milestone', '?')}** {entry.get('name', '')}"
        if entry.get("shipping"):
            head += f" _({entry['shipping']})_"
        out.append(head)
        if entry.get("summary"):
            out.append(f"  - {entry['summary']}")
        if entry.get("spec"):
            out.append(f"  - Spec: {entry['spec']}")
    if len(entries) > limit:
        out.append(f"- … and {len(entries) - limit} more (full list in report.json)")
    out.append("")
    out.append("</details>")
    out.append("")
    out.append("These are Chromium's own words about the window being adopted. "
               "They are *not* matched to the findings above — the names are "
               "prose and ours are identifiers — so read them as background, "
               "not as a second opinion on any single row.")
    out.append("")
    return "\n".join(out)


def _render_details(findings: Sequence[Finding], platform: str) -> str:
    out: List[str] = ["<details><summary>Details and reasoning</summary>", ""]
    for finding in findings:
        change = finding.change
        out.append(f"#### `{display_name(change)}` — score {finding.score}")
        out.append("")
        out.append(f"- Surface: {KIND_LABELS.get(change.kind, change.kind)} "
                   f"({change.change_type})")
        out.append(f"- Signals: {_signals(finding)}")
        if change.paths:
            out.append(f"- Declared in: `{'`, `'.join(change.paths[:3])}`")
        if finding.matched_paths:
            out.append(f"- We patch: `{'`, `'.join(finding.matched_paths[:5])}`")
        if finding.matched_symbols:
            out.append(f"- We reference: `{'`, `'.join(finding.matched_symbols[:8])}`")
        if finding.areas:
            out.append(f"- Areas: {', '.join(finding.areas)}")
        for key, delta in sorted(change.deltas.items()):
            if not (isinstance(delta, list) and len(delta) == 2):
                continue
            if key in ("platform_state", "platform_status"):
                # Dumping the whole per-platform dict buries the one value the
                # reader cares about; show their platform only.
                old = delta[0].get(platform, "?") if isinstance(delta[0], dict) else "?"
                new = delta[1].get(platform, "?") if isinstance(delta[1], dict) else "?"
                if old != new:
                    out.append(f"- {key} [{platform}]: `{old}` → `{new}`")
                continue
            out.append(f"- {key}: `{_esc(delta[0])}` → `{_esc(delta[1])}`")
        status = (finding.enrichment or {}).get("chromestatus") or {}
        if status.get("summary"):
            out.append(f"- Chromestatus: {status['summary']}")
        if status.get("spec"):
            out.append(f"- Spec: {status['spec']}")
        out.append(f"- Score reasoning: {'; '.join(finding.reasons)}")
        out.append("")
    out.append("</details>")
    out.append("")
    return "\n".join(out)


def _tree_coverage_lines(report: Report) -> List[str]:
    """How much of each version's tree the target set read.

    This qualifies every count above it: a file the target set does not reach
    cannot produce a finding, so a clean report over 4% of the tree and a clean
    report over all of it are different claims. The number is measured against
    a listing of that version's own tree on each run, never written down, and
    it belongs beside the facts it bounds rather than only in the run's log.
    """
    coverage = (report.meta or {}).get("coverage") or {}
    out: List[str] = []
    for side, ref in (("from", report.from_ref), ("to", report.to_ref)):
        row = coverage.get(side) or {}
        candidates, read = row.get("candidates"), row.get("read")
        if not candidates:
            continue
        pct = read * 100 // candidates
        out.append(f"- Coverage at `{ref}`: read {read:,} of {candidates:,} "
                   f"files in that tree that could declare ({pct}%).")
        gaps = list((row.get("missed_by_directory") or {}).items())[:3]
        if gaps:
            out.append("  Largest gaps: "
                       + ", ".join(f"`{d}/` ({n:,} files)" for d, n in gaps)
                       + ".")
    if out and (report.meta or {}).get("target_set") != "wide":
        out.append("  Run `--target-set wide` to read every file an extractor "
                   "understands.")
    return out


def _render_provenance(report: Report) -> str:
    meta = report.meta or {}
    summary = report.summary or {}
    lines = [
        f"- Snapshots extracted from Chromium `{report.from_ref}` and "
        f"`{report.to_ref}` (target set `{meta.get('target_set', '?')}`).",
        f"- Facts: {meta.get('facts_from', '?')} → {meta.get('facts_to', '?')}.",
    ]
    lines += _tree_coverage_lines(report)
    profile = meta.get("profile") or {}
    if profile:
        lines.append(
            f"- Downstream profile: {profile.get('paths_total', 0)} patched paths, "
            f"{profile.get('symbols_total', 0)} referenced symbols."
        )
        if not profile.get("paths_total") and not profile.get("symbols_total"):
            lines.append(
                "- **No downstream evidence was supplied**, so nothing could land "
                "in *Must fix*. Point the profile at your patch directory or fork "
                "to get real impact scoring."
            )
    lines.append(
        "- No verdict is computed here. Every row above is extracted evidence "
        "and a deterministic rank; deciding what it means for the product is "
        "the reader's job."
    )
    by_kind = (summary.get("changes") or {}).get("by_kind") or {}
    if by_kind:
        lines.append("- Changes by surface:")
        for kind, counts in by_kind.items():
            lines.append(
                f"  - {KIND_LABELS.get(kind, kind)}: "
                f"+{counts.get('added',0)} / -{counts.get('removed',0)} / "
                f"~{counts.get('modified',0)}"
            )
    return "\n".join(lines)
