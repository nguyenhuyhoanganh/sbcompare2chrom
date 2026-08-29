#!/usr/bin/env python3
"""Print the review and the issue behind one finding, without a browser.

`chromedrift serve` answers the same question through a page and a click. An
agent has neither, and driving the HTTP path means starting a server, polling a
port, URL-encoding a uid and decoding a payload whose keys are one letter long.
This does the lookup directly instead: same enricher, same cache, one command.

Reads a report, finds the finding a search term names, resolves it against
Gerrit if it has not been resolved before, and prints what came back in the
order a reader needs it -- what changed, which CLs changed it, and what bug
each CL was filed against.

Usage:
    python3 scripts/why.py <report-dir-or-json> <search> [options]

    --cache DIR    cache directory (default: $CHROMEDRIFT_CACHE or
                   .chromedrift-cache, matching the rest of the tool)
    --budget N     read at most N diffs (default 600, the `serve` per-click
                   ceiling; 0 removes it)
    --issues N     look up at most N distinct issues (default 6)
    --limit N      when the search matches many findings, list at most N
                   (default 15 -- enough to recognise the right uid in a list,
                   short enough that a broad search does not bury the prompt)
    --save         write the resolved lookup back into report.json
    --json         print the raw provenance block instead of prose

Exit codes: 0 resolved or listed, 1 nothing matched, 2 the report is unusable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Run from anywhere: the repository root is four levels up from this file
# (skills/<name>/scripts/why.py), and an agent invoking this by path should not
# have to also set PYTHONPATH.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from chromedrift.enrich import gerrit
    from chromedrift.model import Report
except ImportError as exc:  # a checkout this script was copied out of
    print(f"cannot import chromedrift ({exc}). Run this from the "
          f"chromedrift repository, or set PYTHONPATH to its root.",
          file=sys.stderr)
    sys.exit(2)

CL_URL = "https://chromium-review.googlesource.com/c/chromium/src/+/"
ISSUE_URL = "https://issues.chromium.org/issues/"

# What each verdict lets the reader claim. Printed beside the badge because a
# verdict read without its meaning is the one failure this whole lookup exists
# to prevent: `touched` and `crowded` name a file, not a fact, and quoting one
# as a cause invents a cause.
MEANING = {
    "introduced": "this CL put the new value there -- it IS the change",
    "exact": "a line this CL changed carries the identifier",
    "moved": "this CL renamed the declaring file; no line changed",
    "declares": "this CL edited the declaration's body, not its name line",
    "described": "the CL's own title names it; no diff was read",
    "crowded": "LEAD ONLY -- many CLs edited this declaration, none singles it out",
    "touched": "LEAD ONLY -- nothing matched the identifier; this merely touched the file",
}
# Everything at or below this rank is a lead rather than a citation. Taken from
# the enricher rather than restated, so the two cannot drift apart.
LEADS = {"crowded", "touched"}


def load(path: str):
    """Return (Report, json_path). Exits with a usable message on failure."""
    if os.path.isdir(path):
        json_path = os.path.join(path, "report.json")
    else:
        json_path = path
    if not os.path.exists(json_path):
        print(f"no report.json at {json_path} -- run `chromedrift run` first",
              file=sys.stderr)
        sys.exit(2)
    try:
        with open(json_path, encoding="utf-8") as fh:
            return Report.from_dict(json.load(fh)), json_path
    except (OSError, ValueError, KeyError) as exc:
        print(f"{json_path} is not a readable chromedrift report ({exc})",
              file=sys.stderr)
        sys.exit(2)


def find(report, term: str):
    """Findings matching `term`, best first.

    An exact uid or key match wins outright and is returned alone, so a caller
    who already knows the identifier is never handed a menu.
    """
    low = term.lower()
    exact = [f for f in report.findings
             if f.uid.lower() == low or f.change.key.lower() == low]
    if exact:
        return exact[:1]
    hits = [f for f in report.findings
            if low in f.uid.lower()
            or low in (f.change.name or "").lower()
            or any(low in p.lower() for p in f.change.locations or [])]
    hits.sort(key=lambda f: -f.score)
    return hits


def block(finding) -> dict:
    return (finding.enrichment or {}).get("gerrit") or {}


def resolve(finding, report, cache: str, budget: int, issues: int) -> list:
    """Look the finding up unless it already carries CLs. Returns warnings."""
    if block(finding).get("changes"):
        return []
    notes = []
    try:
        gerrit.enrich([finding], report.from_ref, report.to_ref, cache,
                      top=1, budget=budget, with_history=issues,
                      log=lambda m: notes.append(m.strip()))
    except Exception as exc:
        # A lookup that cannot reach Gerrit must not read as "no CL found".
        # That is the same wrong answer as an absent row, arrived at faster.
        return [f"! the lookup could not reach Gerrit ({exc}). This is not "
                f"an answer about Chromium -- nothing was established."]
    # `!` is the enricher's own mark for a line that qualifies an answer.
    return [n for n in notes if n.startswith("!")]


def describe(finding) -> str:
    c = finding.change
    where = (c.locations or [""])[0]
    deltas = ", ".join(f"{k}: {v[0]} -> {v[1]}"
                       for k, v in (c.deltas or {}).items()
                       if isinstance(v, list) and len(v) == 2
                       and not isinstance(v[0], dict))
    lines = [f"{finding.uid}",
             f"  score {finding.score} | {finding.bucket} | "
             f"{', '.join(c.signals) or 'no signal'}",
             f"  {c.change_type}{': ' + deltas if deltas else ''}"]
    if where:
        lines.append(f"  declared at {where}")
    return "\n".join(lines)


def render(finding, warnings) -> str:
    b = block(finding)
    out = [describe(finding), ""]
    for w in warnings:
        out.append(w)
    if warnings:
        out.append("")

    changes = b.get("changes") or []
    if not changes:
        out.append("No CL was tied to this finding.")
        out.append("")
        if any("could not reach Gerrit" in w for w in warnings):
            out.append("  The lookup failed before it established anything. "
                       "This is not a result -- retry it.")
        elif not b:
            out.append("  Nothing was looked up. Check the arguments above.")
        elif b.get("diffs_read") is False:
            out.append(f"  Nobody looked: {b.get('candidates', 0)} CLs touched "
                       f"this file, past the diff budget. Re-run with a larger "
                       f"--budget.")
        else:
            out.append("  The file was asked on main, off main, and by commit "
                       "message, and all three missed. This says the CL is "
                       "recorded under some other name or path -- it does NOT "
                       "say the declaration changed on its own.")
            out.append("  See skills/investigating-chromium-root-causes/"
                       "reference/no-row.md before reporting this.")
        return "\n".join(out)

    pool = b.get("candidates") or 0
    read = b.get("candidates_read")
    matched = b.get("matched") or len(changes)
    scope = (f"{matched} of {pool} merged CLs touched this file"
             if pool else f"{matched} CLs")
    if read:
        scope += f", {read} of them read"
    if matched > len(changes):
        scope += f", newest {len(changes)} shown"
    if b.get("found_by") == "message":
        scope = (f"{len(changes)} found by commit message -- nothing "
                 f"touched this file in the window")
    if b.get("failed_fetches"):
        out.append(f"! {b['failed_fetches']} request(s) to Gerrit failed -- "
                   f"this is not a finished search.")
        out.append("")

    leads_only = all(c.get("match") in LEADS for c in changes)
    out.append(f"{'LEADS, NOT A CITATION' if leads_only else 'Why it changed'}"
               f"  ({scope})")
    for cl in changes:
        verdict = cl.get("match", "")
        out.append(f"  CL {cl.get('number')}  {cl.get('date', '')}  [{verdict}]"
                   f"  {cl.get('subject', '')}")
        out.append(f"    {MEANING.get(verdict, 'unknown verdict')}")
        if cl.get("reverts"):
            out.append(f"    reverts CL {cl['reverts']}")
        if cl.get("cherry_pick_of"):
            out.append(f"    cherry-pick of CL {cl['cherry_pick_of']}")
        out.append(f"    {CL_URL}{cl.get('number')}")

    issues = b.get("issues") or []
    if issues:
        out.append("")
        out.append("The bug behind it")
    for issue in issues:
        if not issue.get("changes"):
            continue
        mark = " (RESTRICTED -- title unavailable, CLs still readable)" \
            if issue.get("restricted") else ""
        title = issue.get("title") or "(no title)"
        total = issue.get("total") or len(issue["changes"])
        out.append(f"  issue {issue['id']}{mark}")
        out.append(f"    {title}")
        out.append(f"    cited by {total} CL{'' if total == 1 else 's'}:")
        for cl in issue["changes"]:
            out.append(f"      CL {cl.get('number')}  {cl.get('date', '')}  "
                       f"{cl.get('subject', '')}")
        out.append(f"    {ISSUE_URL}{issue['id']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True, description=__doc__.split("\n")[0])
    ap.add_argument("report", help="report directory, or a report.json in one")
    ap.add_argument("search", help="uid, key, name, or a path fragment")
    ap.add_argument("--cache", default=os.environ.get("CHROMEDRIFT_CACHE",
                                                      ".chromedrift-cache"))
    ap.add_argument("--budget", type=int, default=600)
    ap.add_argument("--issues", type=int, default=6)
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report, json_path = load(args.report)
    hits = find(report, args.search)
    if not hits:
        print(f"nothing in {json_path} matches {args.search!r}.", file=sys.stderr)
        print("An absent row is not an absent change -- see "
              "skills/investigating-chromium-root-causes/reference/no-row.md.",
              file=sys.stderr)
        return 1
    if len(hits) > 1:
        print(f"{len(hits)} findings match {args.search!r}. Re-run with one uid:")
        for f in hits[:args.limit]:
            print(f"  {f.score:>3}  {f.bucket:<13}  {f.uid}")
        if len(hits) > args.limit:
            print(f"  ... and {len(hits) - args.limit} more")
        return 0

    finding = hits[0]
    warnings = resolve(finding, report, args.cache, args.budget, args.issues)
    if args.json:
        print(json.dumps({"uid": finding.uid, "score": finding.score,
                          "bucket": finding.bucket,
                          "signals": finding.change.signals,
                          "gerrit": block(finding)}, indent=2))
    else:
        print(render(finding, warnings))

    if args.save:
        tmp = json_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(report.to_dict(), fh)
            os.replace(tmp, json_path)
        except OSError as exc:
            print(f"could not save back to {json_path}: {exc}", file=sys.stderr)
            if os.path.exists(tmp):
                os.remove(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
