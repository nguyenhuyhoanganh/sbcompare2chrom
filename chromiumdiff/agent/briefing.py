"""The note left in a report directory for whoever is asked about it next.

An agent started in a report directory knows nothing about the report, and the
first thing it does is find out -- badly. Watched without a briefing it opens
`report.json` to see what is in there, or greps it for a name, and both cost
the session: the file is written by `json.dump` with no indent, so it is one
line of several megabytes, and a single match returns all of it.

Everything here exists to spend a few hundred tokens preventing that. The
numbers are read out of the report at the moment the note is written rather
than described in prose, so the note cannot be out of date with the report it
sits beside -- a second report in another directory gets its own.

The file is called `AGENTS.md` because several tools read a file by that name
from the directory they start in. Nothing depends on that; it is a plain
document and stays readable if no tool ever picks it up.
"""

from __future__ import annotations

import os
from typing import List, Optional

from ..model import BUCKET_LABELS, BUCKET_ORDER, Report

NAME = "AGENTS.md"

# The skills that answer questions about a report, named rather than pointed
# at. A path recorded here is a path on the machine that wrote the file, and a
# report directory is a thing people copy; a name survives the copy and a
# stale absolute path sends the reader somewhere that does not exist.
SKILLS = ("analyzing-chromium-upgrades", "investigating-chromium-root-causes")


def path_in(directory: str) -> str:
    return os.path.join(directory, NAME)


def write(report: Report, directory: str) -> str:
    """Write the note beside the report, and return where it went."""
    target = path_in(directory)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(render(report, directory))
    return target


def render(report: Report, directory: str) -> str:
    meta = report.meta or {}
    summary = report.summary or {}
    counts = report.bucket_counts()
    json_path = os.path.join(directory, "report.json")
    size = _megabytes(json_path)

    out: List[str] = []
    add = out.append

    add(f"# {report.from_ref} to {report.to_ref}")
    add("")
    add(f"This directory holds one comparison of two Chromium versions, made "
        f"by `chromiumdiff`. It is about **{meta.get('platform', 'windows')}**.")
    add("")

    add("## What is here")
    add("")
    add("| File | What it is |")
    add("|---|---|")
    add(f"| `report.json` | Every finding, with its evidence. {size} |")
    add("| `report.md` | The same report as prose, in reading order |")
    add("| `report.html` | The same report as a page, with the evidence "
        "behind each row |")
    add("")

    add("## Read it with a script, never with grep")
    add("")
    add("`report.json` is written without indentation, so **the whole file is "
        "one line**. `grep` for any name in it returns every byte of the file "
        "as a single matching line, which is the fastest way to lose a "
        "session. Load it instead:")
    add("")
    add("```python")
    add("import json")
    add('R = json.load(open("report.json"))')
    add('F = R["findings"]')
    add("```")
    add("")
    add("Print an aggregate or a slice. Printing a whole finding is fine; "
        "printing the list is not.")
    add("")

    add("### The shape")
    add("")
    add("```")
    add("R.summary   counts already worked out -- by_bucket, by_owner,")
    add("            by_signal, by_kind, clusters, milestone_brief")
    add("R.meta      platform, target_set, coverage, generated")
    add("R.findings  every row")
    add("")
    add("finding.change      change_type, kind, key, name, before, after,")
    add("                    deltas, paths, locations, signals, severity")
    add("finding.reasons     why it scored what it scored")
    add("finding.score       0-100")
    add("finding.bucket      " + ", ".join(BUCKET_ORDER))
    add("finding.enrichment  gerrit: the CLs behind it, once looked up")
    add("```")
    add("")
    add("A finding's **uid** is not stored. It is `kind:key` -- "
        "`f\"{c['kind']}:{c['key']}\"` -- and that is what `why` takes.")
    add("")

    add("## What is in this one")
    add("")
    add(f"- **{summary.get('total', len(report.findings))} findings**, "
        f"target set `{meta.get('target_set', 'default')}`"
        + (f", generated {meta['generated']}" if meta.get("generated") else ""))
    for bucket in BUCKET_ORDER:
        if counts.get(bucket):
            add(f"- {counts[bucket]} {BUCKET_LABELS[bucket]}")
    coverage = _coverage_line(meta)
    if coverage:
        add(f"- {coverage}")
    if meta.get("complete") is False:
        add("- The scan is **not complete**: some targeted files were not "
            "read. `R['meta']['missing_targets']` says which, and a fact that "
            "would have come from one of them is absent rather than negative.")
    add("")
    add("Counts are already in `R['summary']`. Recomputing one is fine; "
        "disagreeing with one without saying why is not.")
    add("")

    add("## Getting the review behind a row")
    add("")
    add("```")
    add("python3 -m chromiumdiff why <uid>          # in this directory")
    add("python3 -m chromiumdiff why <uid> --json   # the same, for a program")
    add("```")
    add("")
    add("It asks Gerrit, so it is slow the first time and free after -- the "
        "answer is written back into `report.json`. It also prints what the "
        "verdict on each CL actually claims, and those differ enormously: "
        "`introduced` means that CL made this change, `touched` means the CL "
        "edited the same file and nothing ties it to this identifier. Do not "
        "report the second as a cause.")
    add("")
    add("**A CL is not the defect.** The CL says what was done. The issue it "
        "cites says what was wrong. If the question is \"what was the actual "
        "problem\", the answer is in the issue.")
    add("")

    add("## Four ways to be wrong while quoting this report correctly")
    add("")
    add("1. **A retired flag is not a removed feature.** Chromium deletes a "
        "flag once the outcome is settled. `flag_retired_on` means the "
        "behaviour is now permanent; `flag_retired_off` means the code is "
        "gone. Most retirements are the first. Reading the class as lost "
        "capability inverts what it usually means.")
    add("2. **Read `platform_state.windows`, not `default_state`.** They "
        "disagree, in both directions, and the second is not what ships here.")
    add("3. **A Mojo change breaks a build, not necessarily a run.** Both "
        "ends come from the same tree, so one build always agrees with "
        "itself. It is a break for code outside this tree -- say which, "
        "before calling it a runtime break.")
    add("4. **`pref_left_scan` is an unsettled question, not a deletion.** "
        "The key may live in a file this target set never opened. A `wide` "
        "run is what settles it.")
    add("")

    add("## What this report cannot tell you")
    add("")
    add("It compares Chromium against Chromium. It does not know what any "
        "downstream build does, so it can say what moved upstream and why "
        "upstream moved it, and it can never say why a particular product "
        "broke. Say which of those you are answering.")
    add("")

    add("## Skills")
    add("")
    add("Two skills cover this work, if this checkout has them (`skills/`):")
    for name in SKILLS:
        add(f"- `{name}`")
    add("")
    add("The first produces and classifies a whole report; the second traces "
        "one finding back to the review that caused it. Read the relevant one "
        "before interpreting a removal.")
    return "\n".join(out) + "\n"


def _megabytes(path: str) -> str:
    try:
        size = os.path.getsize(path)
    except OSError:
        return "One line -- load it, do not grep it."
    return (f"{size / 1_000_000:.1f} MB on one line -- load it, do not grep "
            f"it.")


def _coverage_line(meta: dict) -> Optional[str]:
    """How much of the tree this run actually read, from the `to` side.

    The `to` side rather than an average of both: a reader asking what is
    missing is asking about the version being moved to, and two numbers here
    invite the wrong one to be quoted.
    """
    coverage = (meta or {}).get("coverage") or {}
    side = coverage.get("to") or {}
    read, candidates = side.get("read"), side.get("candidates")
    if not read or not candidates:
        return None
    return (f"Read {read} of {candidates} candidate files "
            f"({read * 100 // candidates}%). A fact from a file this target "
            f"set did not open is missing, not absent.")
