"""Markdown report: the artifact a team pastes into a ticket or a wiki.

Ordered by what a reader needs first -- the five counts, then what happened,
then the rows.  Every finding shows the reasons behind its score, because a
list that cannot be argued with is a list that gets ignored.

Nothing here states a verdict.  The report carries evidence and a rank; the
judgement is made by whoever reads it, which is why the score reasoning and the
declaring lines are always present rather than summarized away.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from ..diff import SIGNAL_LABELS, leading_signal
from ..enrich.gerrit import CITES as _CITES, strength as _strength
from . import wording
from ..model import (
    BUCKET_ADDED,
    BUCKET_BEHAVIOUR,
    BUCKET_CLEANUP,
    BUCKET_CONTRACT,
    BUCKET_LABELS,
    BUCKET_MEANINGS,
    BUCKET_ORDER,
    BUCKET_SCHEDULED,
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


def _covering(findings: Sequence[Finding], per_signal: int = 3,
              cap: int = 60) -> List[Finding]:
    """Rows for a bucket table: every signal represented, heaviest first.

    A bucket table used to be the top N by score, and score is not spread
    evenly across signals. At M148 -> M151 the 40 rows of Compatibility break
    were all score 80, so they covered 2 of the bucket's 11 signals and a
    reader going top to bottom saw forty Mojo signature changes and not one of
    the 45 removed web APIs -- severity 70 -- nor either of the two renamed
    preference constants that stop code compiling. Behaviour change was worse:
    40 rows, 1 signal of 18, and all 129 `web_api_shipped` rows absent.

    The *What happened* section already counts every signal. What a table adds
    is identifiers to go and grep, and it adds nothing for a signal it never
    shows. So each signal contributes its highest-scoring few, signals come in
    severity order, and whatever room is left goes to the next-highest rows.

    This is the report doing what the skill tells its reader to do: when the
    list is long, group by signal rather than truncate.
    """
    groups: Dict[str, List[Finding]] = {}
    for finding in findings:
        lead = leading_signal(finding.change) or ""
        groups.setdefault(lead, []).append(finding)
    for rows in groups.values():
        rows.sort(key=lambda f: -f.score)
    order = sorted(groups, key=lambda k: (
        -max(f.change.severity for f in groups[k]), -len(groups[k]), k))

    picked: List[Finding] = []
    taken = set()
    for key in order:
        for finding in groups[key][:per_signal]:
            picked.append(finding)
            taken.add(finding.uid)
    rest = [f for f in findings if f.uid not in taken]
    rest.sort(key=lambda f: -f.score)
    return picked + rest[:max(0, cap - len(picked))]


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
                f"{len(stats.get('by_kind', {}))} kinds of declaration.")
        if idle:
            line += (f" {idle} of them score zero: Chromium's own build "
                     f"conditions keep the declaration out of the {platform} "
                     f"binary on both sides of the change, so nothing they do "
                     f"reaches our users.")
        out.append(line)
        out.append("")

    out.append(_render_stories(report))
    out.append(_render_screens(report))
    out.append(_render_clusters(report, summary))
    out.append(_render_milestone_brief(summary))

    # -- buckets --------------------------------------------------------
    # Upstream cleanup is deliberately not given a table. It is the largest
    # bucket in every report and the one nothing in it needs doing about; a
    # reader who wants it has `report.json` and the sortable table in
    # `report.html`. Scheduled does get one: it is a tenth of the report, it
    # is the only part about work that has not happened, and until it was its
    # own bucket a reader had to filter `report.json` by signal id to find it.
    for bucket in (BUCKET_CONTRACT, BUCKET_BEHAVIOUR, BUCKET_ADDED,
                   BUCKET_SCHEDULED):
        findings = report.by_bucket(bucket)
        if not findings:
            continue
        out.append(f"## {BUCKET_LABELS[bucket]} ({len(findings)})")
        out.append("")
        out.append(BUCKET_MEANINGS.get(bucket, ""))
        out.append("")
        out.append("| Score | What changed | Kind | What moved | Where |")
        out.append("|---:|---|---|---|---|")
        shown = _covering(findings, cap=detail_limit + 20)
        for finding in shown:
            out.append(
                f"| {finding.score} | {_esc(wording.describe(finding.change))} "
                f"| {KIND_LABELS.get(finding.change.kind, finding.change.kind)} "
                f"| {_esc(_state_arrow(finding, platform))} "
                f"| `{_esc(_location(finding))}` |"
            )
        if len(findings) > len(shown):
            out.append(f"| … | _{len(findings) - len(shown)} more, and every "
                       f"signal above already has a row_ | | | |")
        out.append("")

        if bucket in (BUCKET_CONTRACT, BUCKET_BEHAVIOUR):
            out.append(_render_details(shown, platform))

    out.append(_render_unconfirmed(report, platform, detail_limit))

    # -- appendix -------------------------------------------------------
    out.append("## How this was produced")
    out.append("")
    out.append(_render_provenance(report))
    return "\n".join(out)


def _render_unconfirmed(report: Report, platform: str,
                        detail_limit: int) -> str:
    """The removals this run could not confirm.

    Every one of them is filed under Upstream cleanup, which has no table, and
    markdown cannot be filtered -- so without this section the only way to
    reach them is to open `report.json` and know which signal ids to look for.
    They are there because the evidence is short, not because they are minor:
    the same rows on a run that read the whole tree are compatibility breaks
    worth 15 more points.
    """
    findings = [f for f in report.findings if f.unconfirmed]
    if not findings:
        return ""
    out = [f"## Unconfirmed ({len(findings)})", "",
           f"Filed under {BUCKET_LABELS[BUCKET_CLEANUP]} because this run did "
           f"not read enough of the tree to tell a deletion from a move, not "
           f"because nothing happened. Re-run with `--target-set wide` to "
           f"settle them.", "",
           "| Score | What changed | Kind | Where |",
           "|---:|---|---|---|"]
    for finding in findings[:detail_limit]:
        out.append(
            f"| {finding.score} | {_esc(wording.describe(finding.change))} "
            f"| {KIND_LABELS.get(finding.change.kind, finding.change.kind)} "
            f"| `{_esc(_location(finding))}` |"
        )
    if len(findings) > detail_limit:
        out.append(f"| … | _{len(findings) - detail_limit} more_ | | |")
    out.append("")
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
        stories = wording.build_stories(report.findings, group_kinds)
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
        # Every story, not the top few. There are about fifty in a full upgrade
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

    The bucket tables answer "what is most severe". Whoever owns a screen
    arrives with a different question -- what is different about my page -- and
    a list of `id:cancelButton` rows cannot answer it: it names neither the
    page, nor the direction, nor what the control is.
    """
    screens = wording.build(report.findings)
    if not screens:
        return ""
    totals = wording.summarize(screens)
    out = ["## What changed on each screen", "",
           f"{totals['added']} new · {totals['changed']} changed · "
           f"{totals['removed']} gone, across {totals['screens']} screens. "
           f"Every row here is also in the tables below.", ""]
    for screen in screens[:limit]:
        out.append(f"**{_esc(screen.name)}** — {screen.headline()}")
        out.append("")
        for finding in screen.sorted_items()[:per_screen]:
            mark = wording.MARK.get(finding.change.change_type, "?")
            out.append(f"- `{mark}` {_esc(wording.describe(finding.change))}")
        remaining = len(screen.items) - per_screen
        if remaining > 0:
            out.append(f"- … and {remaining} more on this screen")
        out.append("")
    if len(screens) > limit:
        out.append(f"… and {len(screens) - limit} more screens with fewer "
                   f"changes; `report.json` and `report.html` hold them all.")
        out.append("")
    return "\n".join(out)


# What a cluster member moved, in the attributes a reader reasons over. The
# gate a page sits behind, the flags a gate reads, and the state a flag held
# are what turn a list of fragments into a direction; the rest identify what
# moved. `expression` is deliberately absent -- it is the raw C++ condition,
# and `features` names the same flags in the form a reader greps for.
_STORY_ATTRS = ("route", "parent", "guards", "features", "condition",
                "default_state", "windows_status", "signature", "pref",
                "label", "control", "screen")


def _attr(value) -> str:
    """A list reads as a list, not as a Python repr."""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def _member_move(change) -> List[str]:
    """What this fragment moved, in the direction it moved.

    Only a modification has two sides worth printing. On an addition or a
    removal the marker already says which way it went, so `guards:
    enableLocalNetworkAccessSetting` on a `-` row reads as the gate the page
    was behind -- where `enableLocalNetworkAccessSetting -> None` spends half
    the line saying what the marker said.
    """
    before = getattr(change, "before", None) or {}
    after = getattr(change, "after", None) or {}
    out = []
    for key in _STORY_ATTRS:
        was, now = before.get(key), after.get(key)
        if was == now or (not was and not now):
            continue
        if was and now:
            # Two lists print as what left and what arrived, never as both
            # lists side by side. A gate's `features` shares a long prefix
            # with itself, so truncating both halves at one width rendered
            # `kLocalNetworkAccessChecks, kLocalNetworkAcc… →
            # kLocalNetworkAccessChecks, kLocalNetworkAcc…` -- two ellipses
            # hiding the one flag that left, which was the whole row.
            if isinstance(was, (list, tuple)) and isinstance(now, (list, tuple)):
                gone = [v for v in was if v not in now]
                came = [v for v in now if v not in was]
                moved = ([f"−{v}" for v in gone] + [f"+{v}" for v in came])
                out.append(f"{key}: {_cell(', '.join(moved), 92)}")
            else:
                out.append(f"{key}: {_cell(_attr(was), 44)} → "
                           f"{_cell(_attr(now), 44)}")
        else:
            out.append(f"{key}: {_cell(_attr(was if was else now), 92)}")
    return out


def _render_clusters(report: Report, summary: dict, limit: int = 12) -> str:
    """Related findings, grouped into one story each -- and told, not named.

    Read individually, the fragments of one Chromium change contradict each
    other: a page removed here, a page added there. Grouped, they read as what
    actually happened.

    This printed the label, the fragment count and the kinds, which names the
    story without telling it. The evidence that makes it a story -- what each
    fragment moved from and to -- was only in `report.json`, so the reader who
    stops at `report.md` got seven rows of Local Network Access identifiers and
    no way to see that the split-permissions experiment had shipped and taken
    the combined page with it.

    Whoever reads this next has to write one sentence per group. The material
    for that sentence is every member's move, together, which is what is
    printed here.
    """
    # Every block whose fragments disagree gets printed, however many that
    # is; the flat ones fill whatever room is left. A fixed twelve cut 12 of
    # the 24 contradictory blocks on a wide run, and those are the only ones
    # that mislead when read apart.
    every = [r for r in ((summary or {}).get("clusters") or [])
             if r.get("size", 0) > 1]
    telling = [r for r in every if r.get("spread", 0) >= 5]
    flat = [r for r in every if r.get("spread", 0) < 5]
    rows = telling + flat[:max(0, limit - len(telling))]
    if not rows:
        return ""
    by_uid = {f.uid: f for f in report.findings}
    out = ["## Related changes, grouped", "",
           "Each block is one Chromium change arriving across several kinds. "
           "Read the block, not the rows: the fragments contradict each other "
           "apart and agree together. `report.json` holds the rest.", ""]
    for r in rows:
        out.append(f"### {_esc(r.get('label', ''))} — "
                   f"{r.get('size', 0)} fragments, top score "
                   f"{r.get('top_score', 0)}")
        out.append("")
        for uid in r.get("members", []):
            finding = by_uid.get(uid)
            if finding is None:
                continue
            change = finding.change
            mark = wording.MARK.get(change.change_type, "?")
            out.append(
                f"- `{mark}` **{_esc(display_name(change))}** "
                f"· {KIND_LABELS.get(change.kind, change.kind)} "
                f"· score {finding.score}")
            for move in _member_move(change):
                out.append(f"  - {_esc(move)}")
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
        out.extend(_group_line(finding))
        # The place, not just the file. Every extractor computes a line number
        # and nothing used to carry it past the snapshot, so a Mojo method in a
        # 900-line .mojom cited the file and left the reader to find it.
        where = change.locations or change.paths
        if where:
            # Every one of them. An overloaded member is declared several
            # times and the row is about the set, so cutting the list at three
            # dropped the line an overload was actually removed from --
            # `WebGLRenderingContextBase.texElementImage2D` lost the
            # declaration at line 651 and the report pointed at three others.
            shown = where if len(where) <= 6 else where[:6]
            line = f"- Declared in: `{'`, `'.join(shown)}`"
            if len(where) > len(shown):
                line += f" and {len(where) - len(shown)} more"
            out.append(line)
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
        out.extend(_provenance_lines(finding))
        out.append(f"- Score reasoning: {'; '.join(finding.reasons)}")
        out.append("")
    out.append("</details>")
    out.append("")
    return "\n".join(out)


def _group_line(finding) -> List[str]:
    """That this finding is one fragment of a larger change, and which row to
    read first.

    This file is the one that travels: a reader pastes a section of it into a
    ticket, and what they paste is the whole of what the next person sees. A
    parameter of an enabled feature reads here as a 15-point row in "New
    declarations" -- a bucket whose meaning is that nothing switches it on --
    while
    the feature it belongs to sits at 55 in a section further down. The table
    of groups at the top of the report says so, and nobody pastes the table.
    """
    group = (finding.enrichment or {}).get("cluster") or {}
    if group.get("size", 0) < 2:
        return []
    others = group["size"] - 1
    line = (f"- Part of a larger change: **{_esc(group.get('label', ''))}** "
            f"— {group['size']} findings in all, {others} elsewhere in this "
            f"report")
    top = group.get("top_score", 0)
    if top > finding.score:
        line += f". The heaviest scores {top}; read that one first"
    return [line + "."]


GERRIT_CL = "https://chromium-review.googlesource.com/c/chromium/src/+/"
ISSUE_URL = "https://issues.chromium.org/issues/"


def _provenance_lines(finding) -> List[str]:
    """The review that made the change, as lines a ticket can hold.

    The pool the CL was chosen from is part of the citation, not decoration:
    "1 of 62 merged CLs touched this file" is the difference between a
    reference and a coincidence. Every verdict is printed under its own name,
    because a reader pasting one of these into a ticket has to be able to tell
    them apart.

    That matters most at the bottom of the ladder, where `crowded` and
    `touched` name no fact at all: they exist so a lookup always answers, and
    an answer that reads as a citation once it has been copied out of the
    report is worse than the silence they replaced. So the heading itself
    changes on a row carrying nothing else -- markdown has no badge colour, no
    row state and no panel to put a disclaimer in, and the line a reader
    copies is the whole of what travels.
    """
    block = (finding.enrichment or {}).get("gerrit") or {}
    changes = block.get("changes") or []
    out: List[str] = []
    if changes:
        pool = block.get("candidates") or 0
        files = len({c["file"] for c in changes if c.get("file")}) or 1
        where = f"these {files} files" if files > 1 else "this file"
        leads = all(_strength(c.get("match")) >= _CITES for c in changes)
        # A crowd that all edited one declaration is that declaration's
        # history, and `_prune` has already ordered it forward. Calling it
        # "leads" would be true and would throw away the one thing it is.
        history = leads and all(c.get("match") == "crowded" for c in changes)
        what = ("- How it got here, oldest first" if history
                else "- Leads only, no CL names this" if leads
                else "- Why it changed")
        # The count that was tied to this fact, not the count that fitted.
        # `report.md` is the copy that travels into a ticket, so a list cut
        # without saying so travels as the whole answer.
        matched = block.get("matched") or len(changes)
        cut = (f", newest {len(changes)} shown"
               if matched > len(changes) else "")
        # Found and opened are different numbers, and the gap is where a
        # missing CL would be. A file whose newest N were read out of more
        # than N said "1 of <all of them> merged CLs touched this file" in
        # both reports; the line a reader pastes into a ticket has to carry
        # the difference.
        read = block.get("candidates_read")
        seen = f", {read} of them read" if read else ""
        head = (f"{what} ({matched} of {pool} merged CLs "
                f"touched {where}{seen}{cut}):" if pool else f"{what}:")
        out.append(head)
        for cl in changes:
            bugs = "".join(
                f" [{'fixes' if b.get('closes') else 'issue'} {b['id']}"
                f"{' (restricted)' if b.get('restricted') else ''}]"
                f"({ISSUE_URL}{b['id']})"
                for b in cl.get("bugs") or [])
            chain = ""
            if cl.get("reverts"):
                chain += f" (reverts CL {cl['reverts']})"
            if cl.get("cherry_pick_of"):
                chain += f" (cherry-pick of CL {cl['cherry_pick_of']})"
            if cl.get("file"):
                chain += f" in `{cl['file']}`"
            out.append(f"  - [CL {cl['number']}]({GERRIT_CL}{cl['number']}) "
                       f"{cl.get('date', '')} *{cl.get('match', '')}* — "
                       f"{cl.get('subject', '')}{chain}{bugs}")
    for issue in (block.get("issues") or [])[:3]:
        if not issue.get("changes"):
            continue
        total = issue.get("total") or len(issue["changes"])
        titled = f" — {issue['title']}" if issue.get("title") else ""
        out.append(f"- [Issue {issue['id']}]({ISSUE_URL}{issue['id']})"
                   f"{' (access-restricted)' if issue.get('restricted') else ''}"
                   f"{titled}, cited by {total} CL"
                   f"{'' if total == 1 else 's'}:")
        for cl in issue["changes"]:
            out.append(f"  - [CL {cl['number']}]({GERRIT_CL}{cl['number']}) "
                       f"{cl.get('date', '')} — {cl.get('subject', '')}")
    return out


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
        lines.append("- Changes by kind:")
        for kind, counts in by_kind.items():
            lines.append(
                f"  - {KIND_LABELS.get(kind, kind)}: "
                f"+{counts.get('added',0)} / -{counts.get('removed',0)} / "
                f"~{counts.get('modified',0)}"
            )
    return "\n".join(lines)
