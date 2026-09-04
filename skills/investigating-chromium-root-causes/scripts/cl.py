#!/usr/bin/env python3
"""Read one CL's own words and its own diff, without a browser.

`why.py` says which CLs a finding is tied to and how. This is the step after:
opening one of them and looking at what it actually did. That is the only
evidence above a verdict, and on the rows where a verdict is `declares` or the
subject reads as unrelated it is the evidence that settles it.

Two things it prints that a subject line does not carry:

- **The full commit message.** Chromium subjects are `[area] what`, and the
  area is the author's word for the surface, not the identifier's. A CL titled
  "[sub apps] change web api" is the CL behind
  `SubAppsServiceRemoveResult.manifest_id` and says nothing that matches it.
  The body and the footers usually do.
- **The diff of one file**, with the two sides kept apart. A finding records a
  declaration's before and after; the CL that made the change is the one whose
  removed line carries the before and whose added line carries the after.

Usage:
    python3 scripts/cl.py <number> [path-fragment] [options]

    --find TOKEN   mark every diff line containing TOKEN (repeatable)
    --context N    context lines around a marked line (default 3; 0 for all)
    --files        list the files the CL touches and stop
    --cache DIR    cache directory (default: $CHROMIUMDIFF_CACHE or
                   .chromiumdiff-cache, matching the rest of the tool)

Exit codes: 0 printed, 1 no such CL or no such file in it, 2 unusable input.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from chromiumdiff.enrich import gerrit
except ImportError as exc:
    print(f"cannot import chromiumdiff ({exc}). Run this from the chromiumdiff "
          f"repository, or set PYTHONPATH to its root.", file=sys.stderr)
    sys.exit(2)


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("number")
    ap.add_argument("path", nargs="?", default="",
                    help="path or fragment of one file the CL touches")
    ap.add_argument("--find", action="append", default=[], metavar="TOKEN")
    ap.add_argument("--context", type=int, default=3)
    ap.add_argument("--files", action="store_true")
    ap.add_argument("--cache", default=os.environ.get("CHROMIUMDIFF_CACHE",
                                                      ".chromiumdiff-cache"))
    args = ap.parse_args()
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
        if args.files or not args.path:
            print("\n  Pass one of these as the second argument to read its diff.")
            return 0

    wanted = [p for p in files if args.path in p]
    if not wanted:
        print(f"  no file in this CL matches {args.path!r}; the ones it "
              f"touches are listed above.", file=sys.stderr)
        return 1
    for path in sorted(wanted)[:3]:
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


if __name__ == "__main__":
    sys.exit(main())
