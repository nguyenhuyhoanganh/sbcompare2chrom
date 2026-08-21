"""Command-line interface.

Each pipeline stage is also its own subcommand.  That is not decoration: the
expensive stage (snapshots) and the stage you iterate on (scoring, reports)
have completely different cost profiles, and being able to re-run the cheap
half against a warm cache is the difference between a tool people tune and a
tool people run once.

The pipeline stops at the report.  Judging what a change means for a
particular product is deliberately not done here: the report is the input to a
reader -- a human, or an agent running the `analyzing-chromium-uprevs` skill --
and this tool's job is to make that input complete, ranked and citable rather
than to reach a verdict of its own.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import sys
from typing import List, Optional

from . import __version__
from .acquire import CHROMIUMDASH, GITILES_BASE, USER_AGENT
from .extract._cpp import PLATFORM
from . import catalog, cluster
from .diff import diff_snapshots, summarize
from .enrich import chromestatus
from .model import (BUCKET_HOUSEKEEPING, BUCKET_LABELS, BUCKET_ORDER,
                    Report, read_json, write_json)
from .report import html as html_report
from .report import markdown as md_report
from .score import Scope, score_all, summarize_findings
from .snapshot import build_snapshot
from .targets import partition_names

DEFAULT_CACHE = os.environ.get("CHROMEDRIFT_CACHE", ".chromedrift-cache")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_snapshot(args: argparse.Namespace) -> int:
    _log(f"snapshot {args.ref}")
    snap = build_snapshot(args.ref, args.cache, args.target_set,
                          platform=PLATFORM, local_src=args.local_src,
                          refresh=args.refresh, partitions=args.partitions,
                          complete=args.complete, log=_log)
    print(f"{snap.ref}  milestone={snap.milestone}  facts={len(snap.facts)}")
    for kind, count in snap.counts().items():
        print(f"  {kind:24s} {count}")
    if snap.meta.get("missing_targets"):
        print(f"  missing targets: {len(snap.meta['missing_targets'])}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    old = build_snapshot(args.from_ref, args.cache, args.target_set,
                         platform=PLATFORM,
                         local_src=args.from_src or args.local_src,
                         refresh=args.refresh, partitions=args.partitions,
                         complete=args.complete, log=_log)
    new = build_snapshot(args.to_ref, args.cache, args.target_set,
                         platform=PLATFORM,
                         local_src=args.to_src or args.local_src,
                         refresh=args.refresh, partitions=args.partitions,
                         complete=args.complete, log=_log)
    changes = diff_snapshots(old, new, platform=PLATFORM,
                             target_milestone=new.milestone)
    print(f"{len(changes)} semantic changes  {old.ref} -> {new.ref}")
    for kind, counts in summarize(changes).items():
        print(f"  {kind:24s} +{counts['added']:<5d} -{counts['removed']:<5d} "
              f"~{counts['modified']}")
    if args.out:
        write_json(args.out, {"from": old.ref, "to": new.ref,
                              "changes": [c.to_dict() for c in changes]})
        print(f"written: {args.out}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    # Each side can come from its own checkout, which is what an air-gapped
    # run against two mirrored trees needs. A single --local-src would point
    # both sides at one directory.
    from_src = args.from_src or args.local_src
    to_src = args.to_src or args.local_src

    _log(f"[1/5] snapshot {args.from_ref}")
    old = build_snapshot(args.from_ref, args.cache, args.target_set,
                         platform=PLATFORM, local_src=from_src,
                         refresh=args.refresh, partitions=args.partitions,
                         complete=args.complete, log=_log)
    _log(f"[2/5] snapshot {args.to_ref}")
    new = build_snapshot(args.to_ref, args.cache, args.target_set,
                         platform=PLATFORM, local_src=to_src,
                         refresh=args.refresh, partitions=args.partitions,
                         complete=args.complete, log=_log)

    # Completeness is only checkable after extraction: whether the surface is
    # self-contained depends on what it references, not on what was fetched.
    dangling = catalog.unresolved_references(new)
    for line in catalog.summarize_closure(dangling):
        _log("  " + line)

    # Each side must have read only what its own target set asked for. Checked
    # on every run because the failure it catches is invisible in the output: a
    # stale tree cache leaves extra files on one side, and they surface as a
    # mass deletion on the other, at the highest severity the tool assigns.
    out_of_scope = {}
    for snap in (old, new):
        bad = catalog.scope_violations(snap)
        if bad:
            out_of_scope[snap.ref] = bad
        for line in catalog.summarize_violations(snap, bad):
            _log("  " + line)

    # Re-stated on every run, not only the one that built the snapshot.
    for snap in (old, new):
        absent = (snap.meta or {}).get("missing_targets") or []
        if absent:
            _log(f"  ! {snap.ref}: {len(absent)} target(s) absent from that "
                 f"source: {', '.join(absent[:3])}"
                 + (" ..." if len(absent) > 3 else ""))

    _log("[3/5] diff")
    platform = PLATFORM
    changes = diff_snapshots(old, new, platform=platform,
                             target_milestone=new.milestone)
    _log(f"  {len(changes)} semantic changes")

    _log("[4/5] rank")
    # The scoring stage is told how much of the NEW tree this run read,
    # because that is what decides whether a fact's absence from it means
    # "removed" or means "in a file we never opened". Passing the same
    # measurement the coverage line prints keeps the two from drifting into
    # separate answers.
    scope = Scope({"to": (new.meta or {}).get("coverage") or {}},
                  to_ref=new.ref)
    findings = score_all(changes, scope)
    # Group related findings before anything reads them. One Chromium change
    # arrives as fragments across several surfaces; ungrouped they contradict
    # each other.
    clusters = cluster.annotate(findings)
    if clusters:
        biggest = max(len(m) for m in clusters.values())
        _log(f"  {len(clusters)} clusters link related findings "
             f"(largest: {biggest} findings)")
    finding_summary = summarize_findings(findings)
    finding_summary["clusters"] = cluster.summarize(clusters)
    for bucket in BUCKET_ORDER:
        _log(f"    {BUCKET_LABELS[bucket]:18s} "
             f"{finding_summary['by_bucket'].get(bucket, 0):5d}")

    milestone_brief: List[dict] = []
    if not args.no_enrich:
        _log("[5/5] chromestatus enrichment")
        milestones = _milestone_span(old.milestone, new.milestone)
        chromestatus.enrich(
            [f for f in findings if f.bucket != BUCKET_HOUSEKEEPING],
            milestones, args.cache, refresh=args.refresh, log=_log)
        # Per-finding matching is weak by nature (prose names vs identifiers),
        # so the shipped-feature list is carried whole as well. It is the one
        # piece of context that says what Chromium *meant* to ship in this
        # window, and the reader of the report -- human or agent -- needs it
        # for exactly the reason a matcher cannot supply it.
        milestone_brief = chromestatus.milestone_brief(
            milestones, args.cache, refresh=args.refresh, log=_log)
        # The span is part of the number: 200 features means something
        # different over three milestones than over eight, and a reader who
        # cannot see which milestones were asked about cannot tell whether the
        # one being adopted is among them.
        span = f"M{milestones[0]}-M{milestones[-1]}" if milestones else "none"
        _log(f"  milestone brief: {len(milestone_brief)} shipped features "
             f"across {span}")
    else:
        _log("[5/5] enrichment skipped")

    report = Report(
        from_ref=old.ref,
        to_ref=new.ref,
        findings=findings,
        summary={
            "changes": {"total": len(changes), "by_kind": summarize(changes)},
            **finding_summary,
            "milestone_brief": milestone_brief,
        },
        meta={
            "platform": platform,
            "generated": _now(),
            "target_set": args.target_set,
            "facts_from": len(old.facts),
            "facts_to": len(new.facts),
            # How much of each version's tree the target set actually read,
            # measured during extraction. It was printed to stderr and stored
            # on the snapshots, and then not carried here -- so the one number
            # saying how much of the answer is missing survived only in
            # scrollback, while both documents claimed the report held it.
            "coverage": {"from": (old.meta or {}).get("coverage") or {},
                         "to": (new.meta or {}).get("coverage") or {}},
            # The TO side's, because that is the tree being adopted. Capped at
            # 400 paths by the snapshot that recorded them.
            "uncovered_files": (new.meta or {}).get("uncovered_files") or [],
            # Targets the source did not have. `cmd_snapshot` printed this and
            # the snapshot recorded it, and then it stopped there: `run` never
            # read it back, so on the cache hit that every second run is, the
            # warning did not appear at all -- and it was in none of the three
            # report files. A target that was never fetched is a whole file's
            # declarations missing from the comparison, which is the same thing
            # `coverage` says and the same reason it had to stop living in
            # scrollback.
            "missing_targets": {
                old.ref: (old.meta or {}).get("missing_targets") or [],
                new.ref: (new.meta or {}).get("missing_targets") or [],
            },
            "partitions": sorted(args.partitions) if args.partitions else [],
            "complete": args.complete,
            "unresolved_references": dangling,
            "out_of_scope_files": out_of_scope,
            "tool_version": __version__,
        },
    )

    json_path = os.path.join(out_dir, "report.json")
    md_path = os.path.join(out_dir, "report.md")
    html_path = os.path.join(out_dir, "report.html")
    write_json(json_path, report.to_dict())
    _write_text(md_path, md_report.render(report, platform=platform))
    _write_text(html_path, html_report.render(report, platform=platform))

    counts = report.bucket_counts()
    print()
    print(f"{old.ref} -> {new.ref}")
    for bucket in BUCKET_ORDER:
        print(f"  {BUCKET_LABELS[bucket]:18s} {counts.get(bucket, 0):5d}")
    print()
    print(f"  {md_path}")
    print(f"  {html_path}")
    print(f"  {json_path}")
    return 0



def _redact_proxy(value: str) -> str:
    """Keep the host, drop anything that could be a credential."""
    remainder = value.rsplit("@", 1)
    if len(remainder) == 2:
        scheme = value.split("://", 1)[0] + "://" if "://" in value else ""
        return f"{scheme}<redacted>@{remainder[1]}"
    return value


def cmd_check(args: argparse.Namespace) -> int:
    """Verify a fresh machine can actually run the pipeline.

    Every check here corresponds to a failure seen in practice: a Python too
    old for the syntax, a proxy that blocks one host but not another, a cache
    directory on a read-only mount, a profile with a typo.  Reporting them
    together beats discovering them one at a time two minutes into a run.
    """
    import urllib.request

    ok = True

    def report(label: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        mark = "OK  " if good else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
        if not good:
            ok = False

    print("python")
    version = ".".join(str(x) for x in sys.version_info[:3])
    report(f"version {version}", sys.version_info >= (3, 9),
           "" if sys.version_info >= (3, 9) else "need 3.9 or newer")

    print("cache directory")
    try:
        os.makedirs(args.cache, exist_ok=True)
        probe = os.path.join(args.cache, ".write-probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        free = shutil.disk_usage(args.cache).free // (1024 ** 3)
        report(f"{os.path.abspath(args.cache)} writable", True, f"{free} GB free")
        if free < 2:
            print("        note: a two-version run needs roughly 250 MB")
    except OSError as exc:
        report(f"{args.cache} writable", False, str(exc))

    print("network")
    for label, url in (
        ("gitiles (source)", f"{GITILES_BASE}/+/refs/heads/main/DEPS?format=TEXT"),
        ("chromiumdash (version resolution)",
         f"{CHROMIUMDASH}/fetch_milestones?mstone=143"),
        ("chromestatus (enrichment, optional)",
         "https://chromestatus.com/api/v0/features?milestone=143"),
    ):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                size = len(resp.read(2048))
            report(label, size > 0, f"HTTP 200")
        except Exception as exc:
            optional = "optional" in label
            report(label, optional, f"{exc}" + (" (skippable with --no-enrich)"
                                                if optional else ""))

    for var in ("HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"):
        if os.environ.get(var):
            # The name and the host, never the value: a proxy URL carries
            # `user:password@` often enough, and `check` output is the first
            # thing pasted into a ticket or kept as a CI artifact.
            print(f"        proxy env: {var}={_redact_proxy(os.environ[var])}")

    print()
    print("ready" if ok else "not ready — see FAIL lines above")
    return 0 if ok else 1


def cmd_catalog(args: argparse.Namespace) -> int:
    """Measure what the target set misses, instead of guessing.

    Curation has no endpoint: you add files, discover more are missing, and
    add again. A blobless clone lists every path in Chromium in seconds, so
    the question becomes a number with the missing files named.
    """
    _log(f"cataloguing {args.ref}")
    paths = catalog.list_tree(args.ref, workdir=args.keep_clone, log=_log)
    report = catalog.analyze(paths, ref=args.ref, target_set=args.target_set,
                             include_irrelevant=args.all_platforms,
                             partitions=args.partitions,
                             complete=args.complete)
    print()
    for line in catalog.summarize(report):
        print(line)

    missing = report.missing()
    if missing:
        print(f"\nNot fetched ({min(len(missing), args.limit)} of {len(missing)}):")
        for entry in missing[: args.limit]:
            print(f"  {entry.path}")
        print("\nAdd the ones that matter to WEBUI_SURFACES or the target list "
              "in chromedrift/targets.py.")

    if args.out:
        write_json(args.out, report.to_dict())
        print(f"\nwritten: {args.out}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    report = Report.from_dict(read_json(args.report))
    platform = report.meta.get("platform", PLATFORM)

    if args.format in ("md", "both"):
        text = md_report.render(report, platform=platform)
        _emit(text, args.out, ".md")
    if args.format in ("html", "both"):
        text = html_report.render(report, platform=platform)
        _emit(text, args.out, ".html")
    return 0


def _emit(text: str, out: Optional[str], suffix: str) -> None:
    if not out:
        print(text)
        return
    path = out if out.endswith(suffix) else out + suffix
    _write_text(path, text)
    print(f"written: {path}", file=sys.stderr)


def _write_text(path: str, text: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


MILESTONE_SPAN_LIMIT = 8


def _milestone_span(start: Optional[int], end: Optional[int],
                    limit: int = MILESTONE_SPAN_LIMIT) -> List[int]:
    """Which milestones to ask chromestatus about, newest end kept.

    Each milestone is one API call, so a long gap has to be capped somewhere.
    It was capped at ``start + 8``, which keeps the *oldest* eight and drops
    everything after them -- the exact opposite of the comment above it, which
    said the useful context is concentrated in the milestones being adopted.
    On a 139 -> 151 run that fetched M140 to M147 and never asked about M148,
    M149, M150 or M151; on 130 -> 151 it stopped at M138. The target milestone,
    the one the whole report is about, was the first thing thrown away.

    Counting back from ``end`` keeps the window against the version being
    adopted. Short spans are unaffected: 148 -> 151 is three milestones either
    way.
    """
    if not end:
        return []
    if not start or start >= end:
        return [end]
    first = max(start + 1, end - limit + 1)
    return list(range(first, end + 1))


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chromedrift",
        description="Compare two Chromium versions and rank what changed: "
                    "feature flags, web APIs, preferences, command-line "
                    "switches, Mojo interfaces and the chrome:// surfaces.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    # Flags are grouped so that a command only offers the ones it acts on.
    # They used to come from one shared parent, which meant `catalog` accepted
    # --local-src and (while it existed) --mode, and silently did nothing
    # with either.

    cache = argparse.ArgumentParser(add_help=False)
    cache.add_argument("--cache", default=DEFAULT_CACHE,
                       help=f"cache directory (default: {DEFAULT_CACHE})")
    cache.add_argument("--refresh", action="store_true",
                       help="ignore caches and refetch")

    target_set = argparse.ArgumentParser(add_help=False)
    target_set.add_argument("--target-set", default="default",
                            choices=("default", "minimal", "wide"),
                            help="which Chromium files to pull. default: a "
                             "curated list, about 40 MB per version. It reads "
                             "a small share of the files that could declare "
                             "something, but a large share of the "
                             "declarations, because the curated files are the "
                             "big ones. wide: whole-directory archives for "
                             "components/, chrome/browser/, content/ and "
                             "others -- about 315 MB per version, and nearly "
                             "every file an extractor understands. The widest "
                             "read available; it is not a release verdict, and "
                             "the run prints what it missed. minimal: three "
                             "files, for smoke tests. Every run measures and "
                             "prints the coverage it achieved")
    which_files = argparse.ArgumentParser(add_help=False, parents=[target_set])
    which_files.add_argument("--partition", action="append", dest="partitions",
                             metavar="NAME",
                             help="limit what is fetched and scanned to one "
                             "part of the product (repeatable). Faster, and "
                             "less complete by design: a change affecting "
                             "downloads can live in content/ or in a Mojo "
                             "interface and match no partition. A smaller "
                             "question, not a cheaper answer to the same one. "
                             "Available: "
                             f"{', '.join(partition_names())}")
    which_files.add_argument("--complete", action="store_true",
                             help="with --partition: fetch the partition's "
                             "whole directories instead of a curated file "
                             "list, so coverage inside them is complete by "
                             "construction. Costs a few MB more; refused for "
                             "partitions whose roots are whole subsystems")

    one_checkout = argparse.ArgumentParser(add_help=False)
    one_checkout.add_argument("--local-src", default=None,
                              help="read from an existing checkout instead of "
                                   "gitiles")

    # Each side of a comparison can come from its own tree, which is what an
    # air-gapped run against two mirrored checkouts needs. A single
    # --local-src would point both sides at the same directory.
    two_checkouts = argparse.ArgumentParser(add_help=False,
                                            parents=[one_checkout])
    two_checkouts.add_argument("--from-src", default=None,
                               help="checkout for the FROM side only "
                                    "(overrides --local-src)")
    two_checkouts.add_argument("--to-src", default=None,
                               help="checkout for the TO side only "
                                    "(overrides --local-src)")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snapshot", parents=[cache, which_files, one_checkout],
                       help="extract the feature surface of one Chromium ref")
    p.add_argument("ref", help="milestone (143), version (143.0.7499.40) or git ref")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("diff", parents=[cache, which_files, two_checkouts],
                       help="semantic diff between two refs")
    p.add_argument("from_ref", metavar="FROM")
    p.add_argument("to_ref", metavar="TO")
    p.add_argument("--out", help="write changes JSON here")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("run", parents=[cache, which_files, two_checkouts],
                       help="full pipeline: snapshot, diff, rank, report")
    p.add_argument("from_ref", metavar="FROM")
    p.add_argument("to_ref", metavar="TO")
    p.add_argument("--out", default="out", help="output directory (default: out)")
    p.add_argument("--no-enrich", action="store_true",
                   help="skip chromestatus enrichment")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("check",
                       help="verify this machine can run the pipeline")
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("catalog", parents=[which_files],
                       help="measure what the target set is missing")
    p.add_argument("ref", help="Chromium ref, e.g. 151.0.7922.138")
    p.add_argument("--limit", type=int, default=40,
                   help="how many missing paths to print (default: 40)")
    p.add_argument("--all-platforms", action="store_true",
                   help="include ash/, chromeos/, ios/ and other trees a "
                        "desktop product never compiles")
    p.add_argument("--keep-clone",
                   help="reuse or keep the blobless clone in this directory")
    p.add_argument("--out", help="write the report JSON here")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("report",
                       help="re-render a saved report.json")
    p.add_argument("report", help="path to report.json")
    p.add_argument("--format", default="md", choices=("md", "html", "both"))
    p.add_argument("--out", help="output path (stdout if omitted)")
    p.set_defaults(func=cmd_report)

    return parser


def _force_utf8_io() -> None:
    """Make stdout/stderr UTF-8 regardless of platform defaults.

    On Windows, Python only uses UTF-8 for a real console; the moment output is
    redirected to a file or a pipe it falls back to the ANSI code page, which
    for most installs is cp1252.  Reports contain arrows and em-dashes, so
    `chromedrift report ... > report.md` dies with

        'charmap' codec can't encode character '\\u2192'

    and so does `chromedrift check`, whose own output uses an em-dash -- which
    would make the very first command a Windows user runs the one that fails.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # not a reconfigurable text stream; nothing to fix


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_io()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _log("interrupted")
        return 130
    except Exception as exc:
        _log(f"error: {exc}")
        if os.environ.get("CHROMEDRIFT_DEBUG"):
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
