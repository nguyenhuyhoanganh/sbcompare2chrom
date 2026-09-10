"""The two history lookups: which CLs changed a finding, and what one CL did.

`chromiumdiff serve` answers the first question through a page and a click. An
agent has neither, and driving the HTTP path means starting a server, polling a
port, URL-encoding a uid and decoding a payload whose keys are one letter long.
These do the lookups directly instead: same enricher, same cache, one command.

`why` reads a report, finds the finding a search term names, resolves it against
Gerrit if it has not been resolved before, and prints what came back in the
order a reader needs it -- what changed, which CLs changed it, and what bug each
CL was filed against.

`cl` is the step after: opening one of those CLs and looking at what it actually
did. That is the only evidence above a verdict, and on the rows where a verdict
is `declares` or the subject reads as unrelated it is the evidence that settles
it. Two things it prints that a subject line does not carry:

- **The full commit message.** Chromium subjects are `[area] what`, and the area
  is the author's word for the product area, not the identifier's. A CL titled
  "[sub apps] change web api" is the CL behind
  `SubAppsServiceRemoveResult.manifest_id` and says nothing that matches it.
  The body and the footers usually do.
- **The diff of one file**, with the two sides kept apart. A finding records a
  declaration's before and after; the CL that made the change is the one whose
  removed line carries the before and whose added line carries the after.

Both commands run from the repository root, like the rest of the tool:

    python3 -m chromiumdiff why <report-dir-or-json> <search> [options]
    python3 -m chromiumdiff cl <number> [path-fragment] [options]

`why` exits 0 on a completed lookup or a list of candidates, 1 when nothing
matched, 2 on an input or save error, and 3 on an incomplete or unavailable
lookup. A completed lookup is not proof of cause. `cl` exits 0 when it printed,
1 when there is no such CL or no such file in it, and 2 on unusable input.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import urllib.parse

from . import cluster
from .enrich import gerrit
from .model import read_report

CL_URL = "https://chromium-review.googlesource.com/c/chromium/src/+/"
ISSUE_URL = "https://issues.chromium.org/issues/"

# What each verdict lets the reader claim. Printed beside the badge because a
# verdict read without its meaning is the one failure this whole lookup exists
# to prevent: `touched` and `crowded` name a file, not a fact, and quoting one
# as a cause invents a cause.
MEANING = {
    "introduced": "added the new value or removed the old one, inside this declaration -- it IS the change",
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


# --- why: which CLs changed one finding ------------------------------------


def load_report(path: str):
    """Return (Report, json_path), or (None, json_path) after reporting why.

    A subcommand returns its exit code to the shared CLI, so a failure here
    cannot call sys.exit: that would bypass the one place exit codes are set.
    """
    json_path = os.path.join(path, "report.json") if os.path.isdir(path) else path
    if not os.path.exists(json_path):
        print(f"no report.json at {json_path} -- run `chromiumdiff run` first",
              file=sys.stderr)
        return None, json_path
    try:
        # `read_report`, not `Report.from_dict`: it refuses a report written by
        # a build whose bucket ids differ from this one's, which otherwise
        # renders as a report with most of its findings missing from the counts.
        return read_report(json_path), json_path
    except (OSError, ValueError, KeyError) as exc:
        print(f"{json_path} is not a readable chromiumdiff report ({exc})",
              file=sys.stderr)
        return None, json_path


def matching_findings(report, term: str):
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


def gerrit_block(finding) -> dict:
    return (finding.enrichment or {}).get("gerrit") or {}


def lookup_state(finding, warnings=(), origin="stored", unavailable=False) -> dict:
    """One disclosure contract for text and JSON, including empty results."""
    b = gerrit_block(finding)
    notes = list(b.get("lookup_warnings") or []) + list(warnings)
    if b.get("diffs_read") is False:
        notes.append("Relevant diffs were not read; retry with --retry and a larger --budget.")
    if b.get("failed_fetches"):
        notes.append(f"{b['failed_fetches']} Gerrit retrieval(s) failed; evidence is incomplete.")
    if b.get("search_incomplete"):
        notes.append("The candidate list is incomplete; it may omit relevant CLs.")
    status = ("unavailable" if unavailable else "not_run" if not b else
              "partial" if notes else "complete")
    return {"status": status, "origin": origin, "warnings": list(dict.fromkeys(notes))}


def resolve(finding, report, cache: str, budget: int, issues: int,
            retry=False, refresh=False) -> dict:
    """Explicit retries retain the HTTP cache; refresh refetches it."""
    if gerrit_block(finding).get("changes") and not (retry or refresh):
        return lookup_state(finding)
    notes = []
    candidate = copy.deepcopy(finding)
    candidate.enrichment = dict(candidate.enrichment or {})
    candidate.enrichment.pop("gerrit", None)
    try:
        summary = gerrit.enrich([candidate], report.from_ref, report.to_ref, cache,
                                top=1, budget=budget, with_history=issues, refresh=refresh,
                                log=lambda m: notes.append(m.strip()))
    except Exception as exc:
        return lookup_state(finding, [f"Lookup failed ({exc}); any displayed evidence is from the saved result."],
                            origin="lookup", unavailable=True)
    warnings = [n for n in notes if n.startswith("!")]
    if not summary.get("available"):
        warnings.append("Lookup unavailable: " + summary.get("reason", "no result") +
                        "; any displayed evidence is from the saved result.")
        return lookup_state(finding, warnings, origin="lookup", unavailable=True)
    finding.enrichment = candidate.enrichment
    if warnings:
        finding.enrichment.setdefault("gerrit", {})["lookup_warnings"] = warnings
    return lookup_state(finding, warnings, origin="lookup")


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


def render_lookup(finding, lookup) -> str:
    b = gerrit_block(finding)
    out = [describe(finding), "", f"Lookup: {lookup['status']} ({lookup['origin']})"]
    for w in lookup["warnings"]:
        out.append("! " + w)
    if lookup["warnings"]:
        out.append("")

    changes = b.get("changes") or []
    if not changes:
        out.append("No CL was tied to this finding.")
        out.append("")
        if lookup["status"] != "complete":
            out.append("  The lookup is unfinished or unavailable. No cause was established.")
        else:
            out.append("  The completed searches found no explaining match within their "
                       "paths, identifiers and branch window. The cause remains unknown.")
        out.append("  See reference/no-row.md in the active skill before reporting this.")
        return "\n".join(out)

    pool = b.get("candidates") or 0
    read = b.get("candidates_read")
    matched = b.get("matched") or len(changes)
    searched = (f"{matched} of {pool} merged CLs touched this file"
                if pool else f"{matched} CLs")
    if read:
        searched += f", {read} of them read"
    if matched > len(changes):
        searched += f", newest {len(changes)} shown"
    if b.get("found_by") == "message":
        searched = (f"{len(changes)} found by commit message -- nothing "
                    f"touched this file in the window")
    leads_only = all(c.get("match") in LEADS for c in changes)
    out.append(f"{'LEADS, NOT A CITATION' if leads_only else 'Why it changed'}"
               f"  ({searched})")
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


# --- cl: one CL's own words and its own diff -------------------------------


def detail(number: str, cache: str) -> dict:
    doc = gerrit._get_json(
        f"{gerrit.GERRIT}/changes/{number}?o=CURRENT_REVISION&o=CURRENT_COMMIT",
        cache, ("probe", f"{number}.json"))
    return doc if isinstance(doc, dict) else {}


def files_of(number: str, cache: str) -> dict:
    doc = gerrit._get_json(
        f"{gerrit.GERRIT}/changes/{number}/revisions/current/files",
        cache, ("probe", f"f{number}.json"))
    return doc if isinstance(doc, dict) else {}


def diff_of(number: str, path: str, cache: str) -> dict:
    quoted = urllib.parse.quote(path, safe="")
    doc = gerrit._get_json(
        f"{gerrit.GERRIT}/changes/{number}/revisions/current/files/"
        f"{quoted}/diff",
        cache, ("probe", f"d{number}_{gerrit._slug(path)}.json"))
    return doc if isinstance(doc, dict) else {}


def message_of(doc: dict) -> str:
    for rev in (doc.get("revisions") or {}).values():
        commit = rev.get("commit") or {}
        return rev.get("commit_with_footers") or commit.get("message") or ""
    return ""


def render_diff(doc: dict, find, context: int) -> str:
    """The two sides kept apart, which is what makes a change readable.

    `{"ab": [...]}` is unchanged, `a` removed, `b` added. A block carrying
    `common` is Gerrit saying the lines are the same content differing only
    inside the line -- a reindent -- and it is marked, because counting one as
    an edit is how a reformat becomes evidence.
    """
    out = []
    blocks = doc.get("content") or []
    marked = []
    for block in blocks:
        common = bool(block.get("common"))
        for line in block.get("a") or []:
            marked.append(("~" if common else "-", line))
        for line in block.get("b") or []:
            marked.append(("~" if common else "+", line))
        for line in block.get("ab") or []:
            marked.append((" ", line))
    if not find:
        return "\n".join(f"  {m} {t}" for m, t in marked)

    # Only lines the CL changed. A token on a context line says the file
    # mentions it, which is the question the file search already answered; the
    # question here is whether *this CL* touched a line carrying it.
    hits = {i for i, (m, t) in enumerate(marked)
            if m in "-+" and any(f.lower() in t.lower() for f in find)}
    if not hits:
        return "  (no line in this file's diff carries the token)"
    if context <= 0:
        keep = set(range(len(marked)))
    else:
        keep = set()
        for i in hits:
            keep |= set(range(max(0, i - context),
                              min(len(marked), i + context + 1)))
    for i in sorted(keep):
        if i - 1 not in keep and out:
            out.append("  ...")
        mark, text = marked[i]
        star = " <<<" if i in hits else ""
        out.append(f"  {mark} {text}{star}")
    return "\n".join(out)


# --- the two commands ------------------------------------------------------


def why_command(args) -> int:
    report, json_path = load_report(args.report)
    if report is None:
        return 2
    hits = matching_findings(report, args.search)
    if not hits:
        print(f"nothing in {json_path} matches {args.search!r}.", file=sys.stderr)
        print("An absent row is not an absent change -- see "
              "reference/no-row.md in the active skill.",
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
    lookup = resolve(finding, report, args.cache, args.budget, args.issues,
                     retry=args.retry, refresh=args.refresh)
    saved = {"requested": args.save, "written": False}
    if args.save:
        cluster.refresh(report)
        tmp = json_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(report.to_dict(), fh)
            os.replace(tmp, json_path)
            saved["written"] = True
        except OSError as exc:
            saved["error"] = str(exc)
            print(f"could not save back to {json_path}: {exc}", file=sys.stderr)
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    if args.json:
        print(json.dumps({"uid": finding.uid, "score": finding.score,
                          "bucket": finding.bucket, "signals": finding.change.signals,
                          "gerrit": gerrit_block(finding), "lookup": lookup, "save": saved}, indent=2))
    else:
        print(render_lookup(finding, lookup))
    if "error" in saved:
        return 2
    return 0 if lookup["status"] == "complete" else 3


def cl_command(args) -> int:
    if not args.number.isdigit():
        print("the CL number is a number", file=sys.stderr)
        return 2

    doc = detail(args.number, args.cache)
    if not doc:
        print(f"CL {args.number} could not be read. It may not exist, or the "
              f"lookup could not reach Gerrit -- which is not the same thing.",
              file=sys.stderr)
        return 1

    print(f"CL {args.number}  {doc.get('status', '')}  "
          f"{(doc.get('submitted') or '')[:19]}")
    print(f"  {gerrit.GERRIT}/c/{gerrit.PROJECT}/+/{args.number}")
    if doc.get("revert_of"):
        print(f"  reverts CL {doc['revert_of']}")
    if doc.get("cherry_pick_of_change"):
        print(f"  cherry-pick of CL {doc['cherry_pick_of_change']}")
    print()
    print("--- what the author said " + "-" * 45)
    message = message_of(doc)
    print("\n".join("  " + ln for ln in (message or "(no message)").split("\n")))

    files = {p: v for p, v in files_of(args.number, args.cache).items()
             if p != "/COMMIT_MSG"}
    print()
    print(f"--- {len(files)} file(s) touched " + "-" * 42)
    if args.files or not args.path:
        for path, meta in sorted(files.items()):
            plus, minus = meta.get("lines_inserted", 0), meta.get("lines_deleted", 0)
            print(f"  {path}  +{plus} -{minus}"
                  + (f"  [{meta['status']}]" if meta.get("status") else ""))
        print("\n  Pass one of these as the second argument to read its diff.")
        return 0

    wanted = sorted(p for p in files if args.path in p)
    if not wanted:
        print(f"  no file in this CL matches {args.path!r}; the ones it "
              f"touches are listed above.", file=sys.stderr)
        return 1
    if args.offset >= len(wanted):
        print(f"offset {args.offset} is past {len(wanted)} matching files", file=sys.stderr)
        return 2
    selected = wanted[args.offset:args.offset + args.limit]
    end = args.offset + len(selected)
    print(f"Matching files: {len(wanted)}; showing {args.offset + 1}..{end}.")
    if args.offset:
        print(f"  {args.offset} earlier matching file(s) omitted on this page; use --offset 0 to start again.")
    if end < len(wanted):
        print(f"  {len(wanted) - end} matching file(s) omitted; repeat with --offset {end} --limit {args.limit}.")
    for path in selected:
        diff = diff_of(args.number, path, args.cache)
        print()
        print(f"--- {path}  [{diff.get('change_type', '?')}] " + "-" * 10)
        # A rename answers for the old path with the whole file as one skip
        # block and no marker, which reads as an empty file unless it is named.
        if diff.get("change_type") == "RENAMED" or (diff.get("meta_a") or {}).get(
                "name") not in (None, path):
            other = (diff.get("meta_a") or {}).get("name")
            if other and other != path:
                print(f"  (renamed from {other})")
        print(render_diff(diff, args.find, args.context))
    return 0


def _run(args) -> int:
    if args.command == "why":
        if args.budget < 0 or args.issues < 0 or args.limit < 1:
            print("budget/issues must be nonnegative and limit must be positive", file=sys.stderr)
            return 2
        return why_command(args)
    if args.limit < 1 or args.offset < 0:
        print("limit must be positive and offset must be nonnegative", file=sys.stderr)
        return 2
    return cl_command(args)


def add_parser(sub, default_cache) -> None:
    p = sub.add_parser("why", help="which CLs changed one finding, and the bug behind them")
    p.add_argument("report", help="report directory, or a report.json in one")
    p.add_argument("search", help="uid, key, name, or a path fragment")
    p.add_argument("--cache", default=default_cache)
    p.add_argument("--budget", type=int, default=600,
                   help="read at most N diffs (default 600, the `serve` per-click ceiling; 0 removes it)")
    p.add_argument("--issues", type=int, default=6, help="look up at most N distinct issues")
    p.add_argument("--limit", type=int, default=15,
                   help="when the search matches many findings, list at most N")
    p.add_argument("--save", action="store_true", help="write the resolved lookup back into report.json")
    retry = p.add_mutually_exclusive_group()
    retry.add_argument("--retry", action="store_true", help="repeat lookup using the HTTP cache")
    retry.add_argument("--refresh", action="store_true", help="repeat lookup and refetch Gerrit data")
    p.add_argument("--json", action="store_true",
                   help="print provenance, lookup diagnostics and save status as JSON")
    p.set_defaults(func=_run)

    p = sub.add_parser("cl", help="one CL's own message and the diff of one of its files")
    p.add_argument("number")
    p.add_argument("path", nargs="?", default="",
                   help="path or fragment of one file the CL touches")
    p.add_argument("--find", action="append", default=[], metavar="TOKEN",
                   help="mark every diff line containing TOKEN (repeatable)")
    p.add_argument("--context", type=int, default=3,
                   help="context lines around a marked line (0 for all)")
    p.add_argument("--files", action="store_true", help="list the files the CL touches and stop")
    p.add_argument("--limit", type=int, default=3, help="diffs per page")
    p.add_argument("--offset", type=int, default=0, help="skip N matching files")
    p.add_argument("--cache", default=default_cache)
    p.set_defaults(func=_run)
