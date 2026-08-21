"""Markdown report: the artifact a team pastes into a ticket or a wiki.

Ordered by what a reader needs first -- the four counts, then what happened,
then the rows.  Every finding shows the reasons behind its score, because a
list that cannot be argued with is a list that gets ignored.

Nothing here states a verdict.  The report carries evidence and a rank; the
judgement is made by whoever reads it, which is why the score reasoning and the
declaring lines are always present rather than summarized away.
"""

from __future__ import annotations

from typing import List, Sequence

from ..diff import SIGNAL_LABELS
from . import wording as surfaces
from ..model import (
    BUCKET_BEHAVIOUR,
    BUCKET_BREAKING,
    BUCKET_LABELS,
    BUCKET_MEANINGS,
    BUCKET_NEW,
    BUCKET_ORDER,
    KIND_GROUP_MEANINGS,
    KIND_GROUPS,
    KIND_LABELS,
    Finding,
    Report,
)

TITLE = "Chromium version comparison"

def _esc(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


# For these kinds the bare name is ambiguous -- several interfaces declare an
# `echoCancellation` member, and `bits`, `id` and `size` are field names in
# dozens of Mojo structs -- so the qualified key is what identifies it.
_QUALIFIED_KINDS = ("idl_member", "mojo_method", "mojo_field")


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


def _location(finding: Finding, limit: int = 52) -> str:
    """Where to look, in one cell: the file and the line inside it.

    The place, not the file. `content_features.cc` declares nearly two hundred
    features, so citing the file leaves the reader to find the line, which is
    the work this column exists to save.

    Trimmed from the *front* when it will not fit, because the useful half is
    at the back. Cutting the tail off `third_party/blink/public/mojom/ai/
    ai_manager.mojom:41` at 52 characters removes the filename and the line
    number and leaves four directory names every row in the block shares.
    """
    where = finding.change.locations or finding.change.paths
    if not where:
        return "—"
    text = where[0]
    if len(text) <= limit:
        return text
    parts = text.split("/")
    out = parts[-1]
    for part in reversed(parts[:-1]):
        if len(part) + 1 + len(out) + 2 > limit:
            break
        out = f"{part}/{out}"
    return "…/" + out


def render(report: Report, platform: str = "windows",
           detail_limit: int = 40) -> str:
    out: List[str] = []
    counts = report.bucket_counts()
    summary = report.summary or {}
    meta = report.meta or {}

    out.append(f"# {TITLE}: {report.from_ref} → {report.to_ref}")
    out.append("")
    out.append(f"Platform **{platform}** · target set "
               f"`{meta.get('target_set', '?')}` · generated "
               f"{meta.get('generated', '')}")
    out.append("")

    out.append("## What kind of change")
    out.append("")
    out.append("| | Count | Meaning |")
    out.append("|---|---:|---|")
    for bucket in BUCKET_ORDER:
        out.append(f"| {BUCKET_LABELS[bucket]} | {counts.get(bucket, 0)} | "
                   f"{BUCKET_MEANINGS.get(bucket, '')} |")
    out.append("")

    stats = summary.get("changes") or {}
    if stats:
        idle = summary.get("not_in_build") or 0
        line = (f"{stats.get('total', 0)} semantic changes across "
                f"{len(stats.get('by_kind', {}))} surface types.")
        if idle:
            line += (f" {idle} of them score zero: Chromium's own build "
                     f"conditions keep the declaration out of the {platform} "
                     f"binary on both sides of the change, so nothing they do "
                     f"reaches our users.")
        out.append(line)
        out.append("")

    out.append(_render_stories(report))
    out.append(_render_screens(report))
    out.append(_render_clusters(summary))
    out.append(_render_milestone_brief(summary))

    # -- buckets --------------------------------------------------------
    # Housekeeping is deliberately not given a table. It is the largest bucket
    # in every report and the one nothing in it needs doing about; a reader
    # who wants it has `report.json` and the sortable table in `report.html`.
    for bucket in (BUCKET_BREAKING, BUCKET_BEHAVIOUR, BUCKET_NEW):
        findings = report.by_bucket(bucket)
        if not findings:
            continue
        out.append(f"## {BUCKET_LABELS[bucket]} ({len(findings)})")
        out.append("")
        out.append(BUCKET_MEANINGS.get(bucket, ""))
        out.append("")
        out.append("| Score | What changed | Surface | What moved | Where |")
        out.append("|---:|---|---|---|---|")
        for finding in findings[:detail_limit]:
            out.append(
                f"| {finding.score} | {_esc(surfaces.describe(finding.change))} "
                f"| {KIND_LABELS.get(finding.change.kind, finding.change.kind)} "
                f"| {_esc(_state_arrow(finding, platform))} "
                f"| `{_esc(_location(finding))}` |"
            )
        if len(findings) > detail_limit:
            out.append(f"| … | _{len(findings) - detail_limit} more_ | | | |")
        out.append("")

        if bucket in (BUCKET_BREAKING, BUCKET_BEHAVIOUR):
            out.append(_render_details(findings[:detail_limit], platform))

    # -- appendix -------------------------------------------------------
    out.append("## How this was produced")
    out.append("")
    out.append(_render_provenance(report))
    return "\n".join(out)


def _render_stories(report: Report) -> str:
    """What happened, in the diff engine's own sentences.

    2,792 rows are not 2,792 things that happened; they are about forty, and
    the sentence for each was already written -- it is the signal label that set
    the finding's severity. Until this section existed it was reachable only by
    expanding one row at a time, so the report could say what scored highest and
    never what the milestone actually did.
    """
    out: List[str] = []
    for group_name, group_kinds in KIND_GROUPS:
        stories = surfaces.build_stories(report.findings, group_kinds)
        if not stories:
            continue
        total = sum(len(s.items) for s in stories)
        out += [f"### {group_name} — {total}", "",
                KIND_GROUP_MEANINGS.get(group_name, ""), "",
                # Both numbers, because the rows are ordered by the first one
                # and printing only the second made the table look unsorted:
                # `Top score` ran 100, 84, 83, 80, 78, 75, 82, 50, 63 down a
                # column with no visible reason. Severity is what this kind of
                # change costs and it is the ranking; top score is that after
                # the build conditions and this run's own coverage weighed in,
                # so the gap between the two columns is the discount.
                "| Count | What happened | Direction | Severity | Top score |",
                "|---:|---|---|---:|---:|"]
        # Every story, not the top few. There are about fifty in a full uprev
        # and the tail is where the quiet ones live -- 181 flags that arrived
        # with nothing else moving is a fact about the milestone, and cutting
        # the table at fourteen rows hid 546 of these 974 findings.
        for story in stories:
            out.append(f"| {len(story.items)} | {_esc(story.title)} | "
                       f"{story.headline()} | {story.severity()} | "
                       f"{story.top_score()} |")
        out.append("")
    if not out:
        return ""
    return "\n".join(["## What happened", "",
                      "Every finding falls under exactly one of these. The "
                      "sentence is the diff engine's, not a summary of it.",
                      ""] + out)


def _render_screens(report: Report, limit: int = 12, per_screen: int = 12) -> str:
    """What changed on each `chrome://` screen.

    The bucket tables answer "what is most severe". Whoever owns a surface
    arrives with a different question -- what is different about my page -- and
    a list of `id:cancelButton` rows cannot answer it: it names neither the
    page, nor the direction, nor what the control is.
    """
    screens = surfaces.build(report.findings)
    if not screens:
        return ""
    totals = surfaces.summarize(screens)
    out = ["## What changed on each screen", "",
           f"{totals['added']} new · {totals['changed']} changed · "
           f"{totals['removed']} gone, across {totals['screens']} screens. "
           f"Every row here is also in the tables below.", ""]
    for screen in screens[:limit]:
        out.append(f"**{_esc(screen.name)}** — {screen.headline()}")
        out.append("")
        for finding in screen.sorted_items()[:per_screen]:
            mark = surfaces.MARK.get(finding.change.change_type, "?")
            out.append(f"- `{mark}` {_esc(surfaces.describe(finding.change))}")
        remaining = len(screen.items) - per_screen
        if remaining > 0:
            out.append(f"- … and {remaining} more on this screen")
        out.append("")
    if len(screens) > limit:
        out.append(f"… and {len(screens) - limit} more screens with fewer "
                   f"changes; `report.json` and `report.html` hold them all.")
        out.append("")
    return "\n".join(out)


def _render_clusters(summary: dict) -> str:
    """Related findings, grouped into one story each.

    Read individually, the fragments of one Chromium change contradict each
    other -- a page removed here, a page added there. Grouped, they read as
    what actually happened.
    """
    rows = (summary or {}).get("clusters") or []
    rows = [r for r in rows if r.get("size", 0) > 1][:12]
    if not rows:
        return ""
    out = ["## Related changes, grouped", "",
           "Each row is one Chromium change arriving across several surfaces. "
           "Read the group, not the individual rows.", "",
           "| Top score | Story | Fragments | Surfaces |",
           "|---:|---|---:|---|"]
    for r in rows:
        kinds = ", ".join(KIND_LABELS.get(k, k) for k in r.get("kinds", []))
        out.append(f"| {r.get('top_score', 0)} | `{_cell(r.get('label', ''), 44)}` "
                   f"| {r.get('size', 0)} | {_cell(kinds, 70)} |")
    out.append("")
    return "\n".join(out)


def _render_milestone_brief(summary: dict, limit: int = 200) -> str:
    """What Chromium says it shipped in this window.

    The report is what a reader reasons over, so the grounding lives here --
    otherwise the one source that says what Chromium *intended* to ship is
    fetched, paid for, and thrown away.

    Folded into a `<details>` block because it is background, not findings: a
    reader scanning for work should step over it, and a reader trying to
    explain a change should find it without another network call.

    Newest milestone first, because the one being adopted is the one the reader
    came for. This is also the only place the list is cut, so the count below
    is true and the "… and N more" line means what it says -- `report.json`
    really does hold the rest.
    """
    entries = (summary or {}).get("milestone_brief") or []
    if not entries:
        return ""
    shown = entries[:limit]
    span = sorted({e.get("milestone") for e in entries if e.get("milestone")})
    scope = f" across M{span[0]}–M{span[-1]}" if span else ""
    head_count = (f"{len(shown)} of {len(entries)}" if len(entries) > limit
                  else str(len(entries)))
    out = ["## What Chromium says shipped in this window", "",
           f"<details><summary>{head_count} features from chromestatus"
           f"{scope}</summary>", ""]
    for entry in shown:
        head = f"- **M{entry.get('milestone', '?')}** {_esc(entry.get('name', ''))}"
        if entry.get("shipping"):
            head += f" _({_esc(entry['shipping'])})_"
        out.append(head)
        # `_esc` collapses newlines. Chromestatus prose carries blank lines and
        # indented code samples, and a raw one breaks out of this list.
        if entry.get("summary"):
            out.append(f"  - {_esc(entry['summary'])}")
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
        # The place, not just the file. Every extractor computes a line number
        # and nothing used to carry it past the snapshot, so a Mojo method in a
        # 900-line .mojom cited the file and left the reader to find it.
        where = change.locations or change.paths
        if where:
            out.append(f"- Declared in: `{'`, `'.join(where[:3])}`")
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


def _missing_target_lines(report: Report) -> List[str]:
    """Targets a side did not have, which is a file's worth of facts missing.

    Recorded on the snapshot since the beginning and reported nowhere: the
    warning was printed by the run that built the snapshot and lost on every
    cached run after it. A target absent from one side and present on the other
    is the shape that reads as a mass deletion.
    """
    missing = (report.meta or {}).get("missing_targets") or {}
    out: List[str] = []
    for ref, paths in missing.items():
        if not paths:
            continue
        out.append(f"- **{len(paths)} target(s) absent from `{ref}`**, so "
                   f"nothing they declare could be compared: "
                   + ", ".join(f"`{p}`" for p in paths[:4])
                   + (f" and {len(paths) - 4} more" if len(paths) > 4 else "")
                   + ".")
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
    lines += _missing_target_lines(report)
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
