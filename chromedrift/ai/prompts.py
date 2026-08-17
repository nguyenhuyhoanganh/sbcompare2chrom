"""Prompt construction for the map and reduce passes.

Two properties drive the design.

**The model judges, it does not discover.**  Every record handed over is
already normalized, scored and evidence-annotated by the deterministic stages.
The model's job is the part that genuinely needs judgement -- what does this
mean for *our* product, what should someone do about it -- not recomputing a
diff it cannot see.

**Fabrication has to be unattractive.**  Chromium feature names are evocative
enough that a model will happily narrate what ``PwaNavigationCapturing`` does
from the name alone.  So the record carries the real evidence (default states,
statuses, signatures, chromestatus summary), the instructions demand citation
of that evidence, and ``unknown`` is offered as a first-class verdict.  A
confident wrong answer is worse than no answer here: it costs a reviewer more
time than the finding would have.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence

from ..diff import SIGNAL_LABELS
from ..model import KIND_LABELS, MODE_FORK, MODE_UPREV, Finding
from ..sbprofile import Area, TouchSet

SYSTEM_MAP = """\
You are a browser platform engineer doing Chromium uprev impact analysis for a \
downstream vendor browser (a Chromium fork shipped on Windows).

You are given change records already extracted and scored from two Chromium \
versions. For each record decide what it means FOR THIS BROWSER and what the \
team should do.

Rules:
- Judge only from the evidence in the record. Do NOT infer behaviour from a \
feature's name.
- If the evidence does not support a conclusion, use verdict "unknown" and say \
what evidence would settle it. This is expected and useful; guessing is not.
- "we_reference" evidence means the vendor's own source or patches touch this \
symbol or file. That is the strongest signal that action is required.
- Prefer concrete actions ("re-test picture-in-picture on Windows 11", "rebase \
our patch in render_widget_host_view_aura.cc") over generic advice ("monitor \
this"). Name a file only if the record names it; do not invent paths.
- Be brief. One or two sentences per field.

Return ONLY a JSON object, no prose around it:
{"assessments":[{"id":"<exact id from the record>",
  "verdict":"breaks_us|behaviour_change|adopt|no_impact|unknown",
  "rationale":"why, citing the evidence",
  "action":"what to do, or empty if none",
  "effort":"none|small|medium|large|unknown",
  "risk":"low|medium|high|unknown",
  "test_hint":"what to test, or empty"}]}

Verdicts:
- breaks_us: compiles or runs incorrectly against our fork; needs a code change
- behaviour_change: still builds, but user-visible or performance behaviour moves
- adopt: new capability worth taking advantage of
- no_impact: safe to ignore for this product
- unknown: evidence insufficient
"""

# Fork comparison: the same records, read the other way round.
#
# Reusing SYSTEM_MAP here would be actively misleading. It frames every record
# as "Chromium changed something between two of its own versions", so the model
# reads a missing fact as upstream cleanup. In a fork comparison a missing fact
# is something *the vendor deleted on purpose*, and an extra one is the
# vendor's own code -- the opposite conclusion, from the same JSON.
SYSTEM_MAP_FORK = """\
You are a browser platform engineer comparing a downstream vendor browser (a \
Chromium fork shipped on Windows) against the upstream Chromium release it was \
merged from. Both sides are at the same milestone.

Direction matters and is fixed: the comparison runs upstream -> our fork.

- "removed" means WE removed something upstream still has. The next rebase \
brings it back unless a patch carries the removal. It is not upstream cleanup.
- "added" means WE have something upstream does not. It is our own divergence, \
already shipped, and it has to survive every future merge. It is NOT a new \
capability to consider adopting.
- "modified" means our declaration differs from upstream's. Decide whether that \
reads as a deliberate product decision or as a merge that quietly missed an \
upstream change.

For each record decide what the difference IS and what it costs to keep.

Rules:
- Judge only from the evidence in the record. Do NOT infer behaviour from a \
name, and do not assume a difference is intentional just because it exists.
- If the evidence cannot tell a decision from an accident, use verdict \
"unknown" and say what would settle it (a commit message, an owner, a bug id). \
This is the common and correct answer here; guessing is not.
- Be brief. One or two sentences per field.

Return ONLY a JSON object, no prose around it:
{"assessments":[{"id":"<exact id from the record>",
  "verdict":"breaks_us|behaviour_change|adopt|no_impact|unknown",
  "rationale":"why, citing the evidence",
  "action":"what to do, or empty if none",
  "effort":"none|small|medium|large|unknown",
  "risk":"low|medium|high|unknown",
  "test_hint":"what to test, or empty"}]}

Verdicts, in fork terms:
- breaks_us: the next rebase silently undoes this, or our side no longer builds
- behaviour_change: our users see something different from upstream's
- adopt: upstream's version is better and we should drop ours
- no_impact: the difference is cosmetic or already dead code
- unknown: cannot tell decision from accident with what is here
"""


SYSTEM_REDUCE = """\
You are writing the executive summary of a Chromium uprev impact report for a \
downstream vendor browser team.

You receive per-change assessments already produced. Aggregate them. Do not \
invent findings that are not present in the input.

Return ONLY a JSON object:
{"headline":"one sentence on the overall risk of this uprev",
 "themes":[{"title":"...","detail":"...","findings":["id","id"]}],
 "must_do":["concrete action", "..."],
 "watch":["thing to verify during QA", "..."],
 "questions":["open question a human must answer", "..."]}

Keep themes to at most 6, ordered by importance. Every action must trace to an \
assessment in the input.
"""


def _fmt_state(attrs: Optional[dict], platform: str) -> str:
    if not attrs:
        return "-"
    states = attrs.get("platform_state") or attrs.get("platform_status")
    if isinstance(states, dict) and states.get(platform):
        return str(states[platform])
    return str(attrs.get("default_state") or attrs.get("status") or "-")


def render_finding(finding: Finding, platform: str = "windows") -> str:
    """One compact, evidence-dense record.  Roughly 120-250 tokens."""
    change = finding.change
    lines = [f"### {change.uid}"]
    lines.append(
        f"what: {change.change_type} {KIND_LABELS.get(change.kind, change.kind)} "
        f"`{change.name}`")

    if change.signals:
        labels = [SIGNAL_LABELS.get(s, s) for s in change.signals]
        lines.append(f"signals: {'; '.join(labels)}")

    if change.kind in ("base_feature", "blink_runtime_feature"):
        before = _fmt_state(change.before, platform)
        after = _fmt_state(change.after, platform)
        if before != after:
            lines.append(f"{platform} default: {before} -> {after}")
        else:
            lines.append(f"{platform} default: {after}")

    for key, (old, new) in sorted(change.deltas.items()):
        if key in ("platform_state", "platform_status"):
            continue
        lines.append(f"changed {key}: {_short(old)} -> {_short(new)}")

    if change.paths:
        lines.append(f"declared in: {', '.join(change.paths[:2])}")

    if finding.matched_paths:
        lines.append(f"we_patch: {', '.join(finding.matched_paths[:4])}")
    if finding.matched_symbols:
        lines.append(f"we_reference: {', '.join(finding.matched_symbols[:6])}")
    if finding.areas:
        lines.append(f"our_areas: {', '.join(finding.areas)}")
    if not finding.matched_paths and not finding.matched_symbols:
        lines.append("we_reference: none found in our source or patches")

    status = finding.enrichment.get("chromestatus")
    if isinstance(status, dict):
        if status.get("summary"):
            lines.append(f"chromestatus: {status['summary']}")
        for key in ("spec", "shipped_milestone", "ff_position", "safari_position"):
            if status.get(key):
                lines.append(f"  {key}: {status[key]}")

    lines.append(f"our_score: {finding.score} ({finding.bucket})")
    return "\n".join(lines)


def _short(value, limit: int = 160) -> str:
    if value is None:
        return "(absent)"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def render_areas(areas: Sequence[Area]) -> str:
    if not areas:
        return "(no owned areas declared)"
    lines = []
    for area in areas:
        bits = [f"- {area.id}: {area.title or area.id} (weight {area.weight})"]
        if area.owner:
            bits.append(f"owner {area.owner}")
        if area.notes:
            bits.append(area.notes)
        lines.append(" | ".join(bits))
    return "\n".join(lines)


def render_milestone_brief(entries: Sequence[dict]) -> str:
    """Chromium's own account of what shipped, as shared grounding."""
    lines = []
    for entry in entries:
        head = f"- M{entry.get('milestone','?')} {entry.get('name','')}"
        if entry.get("shipping"):
            head += f" [{entry['shipping']}]"
        lines.append(head)
        if entry.get("summary"):
            lines.append(f"    {entry['summary']}")
    return "\n".join(lines)


def system_for(mode: str = MODE_UPREV) -> str:
    """The system prompt matching the comparison actually being run."""
    return SYSTEM_MAP_FORK if mode == MODE_FORK else SYSTEM_MAP


def _comparison_line(mode: str, from_ref: str, to_ref: str) -> str:
    if mode == MODE_FORK:
        return (f"FORK COMPARISON: upstream {from_ref} -> our fork {to_ref} "
                f"(same milestone; every difference below is ours)")
    return f"UPREV: {from_ref} -> {to_ref}"


def build_map_prompt(findings: Sequence[Finding], touch: TouchSet,
                     from_ref: str, to_ref: str,
                     relevant_areas: Optional[Sequence[Area]] = None,
                     milestone_brief: Optional[Sequence[dict]] = None,
                     mode: str = MODE_UPREV) -> str:
    areas = relevant_areas if relevant_areas is not None else touch.areas
    header = [
        f"PRODUCT: {touch.name} (Chromium fork, platform: {touch.platform})",
        _comparison_line(mode, from_ref, to_ref),
        "",
        "OUR OWNED AREAS:",
        render_areas(areas),
        "",
    ]
    if milestone_brief:
        header += [
            "WHAT CHROMIUM SAYS SHIPPED IN THIS WINDOW "
            "(background from chromestatus; entries here may or may not "
            "correspond to the change records below):",
            render_milestone_brief(milestone_brief),
            "",
        ]
    header += [f"CHANGE RECORDS ({len(findings)}):", ""]
    body = "\n\n".join(render_finding(f, touch.platform) for f in findings)
    return "\n".join(header) + body


def build_reduce_prompt(assessments: List[dict], findings: Sequence[Finding],
                        touch: TouchSet, from_ref: str, to_ref: str,
                        bucket_counts: Dict[str, int],
                        mode: str = MODE_UPREV) -> str:
    by_id = {f.uid: f for f in findings}
    lines = [
        f"PRODUCT: {touch.name} (platform: {touch.platform})",
        _comparison_line(mode, from_ref, to_ref),
        f"Triage buckets: {json.dumps(bucket_counts)}",
        "",
        "ASSESSMENTS:",
    ]
    for item in assessments:
        finding = by_id.get(item.get("id", ""))
        name = finding.change.name if finding else item.get("id", "?")
        areas = ",".join(finding.areas) if finding and finding.areas else "-"
        lines.append(
            f"- [{item.get('id')}] {name} | verdict={item.get('verdict')} "
            f"| effort={item.get('effort')} | risk={item.get('risk')} "
            f"| areas={areas}"
        )
        if item.get("rationale"):
            lines.append(f"    why: {item['rationale']}")
        if item.get("action"):
            lines.append(f"    action: {item['action']}")
    return "\n".join(lines)
