"""Command-line interface.

Each pipeline stage is also its own subcommand.  That is not decoration: the
expensive stage (snapshots) and the stage you iterate on (scoring, reports)
have completely different cost profiles, and being able to re-run the cheap
half against a warm cache is the difference between a tool people tune and a
tool people run once.

The pipeline stops at the report.  Judging what a change means for the product
is deliberately not done here: the report is the input to a reader -- a human,
or an agent running the `analyzing-chromium-uprevs` skill -- and this tool's
job is to make that input complete, ranked and citable rather than to reach a
verdict of its own.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import sys
from typing import List, Optional

from . import __version__
from . import jsonc
from .acquire import CHROMIUMDASH, GITILES_BASE, USER_AGENT
from .extract._cpp import PLATFORM
from . import catalog, cluster, coverage, discover, provenance
from .diff import MODE_UPREV, MODES, diff_snapshots, summarize
from .enrich import chromestatus
from .impact import score_all, summarize_findings
from .model import Report, read_json, write_json
from .report import html as html_report
from .report import markdown as md_report
from .downstream import TouchSet, load_profile
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
                             target_milestone=new.milestone, mode=args.mode)
    print(f"{len(changes)} semantic changes  {old.ref} -> {new.ref} "
          f"[{args.mode}]")
    for kind, counts in summarize(changes).items():
        print(f"  {kind:24s} +{counts['added']:<5d} -{counts['removed']:<5d} "
              f"~{counts['modified']}")
    if args.out:
        write_json(args.out, {"from": old.ref, "to": new.ref,
                              "changes": [c.to_dict() for c in changes]})
        print(f"written: {args.out}")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    snapshots = []
    if args.ref:
        snapshots.append(build_snapshot(
            args.ref, args.cache, args.target_set, platform=PLATFORM,
            refresh=args.refresh, partitions=args.partitions,
            complete=args.complete, log=_log))
    touch = load_profile(args.profile, snapshots=snapshots, log=_log)
    print(f"profile: {touch.name} (platform {touch.platform})")
    print(f"  areas:            {len(touch.areas)}")
    print(f"  patched files:    {len(touch.modified_paths)}")
    print(f"  patched prefixes: {len(touch.modified_prefixes)}")
    print(f"  symbols:          {len(touch.symbols)}")
    for key, value in sorted(touch.provenance.items()):
        print(f"    {key}: {value}")
    if not touch.has_evidence():
        print("\n  WARNING: no downstream evidence. Impact scoring will not be "
              "able to place anything in 'Must fix'.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    # Each side can come from its own checkout. Comparing a vendor fork against
    # upstream needs exactly that: two different trees, neither of which is a
    # Chromium tag. A single --local-src would point both sides at one tree.
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

    _log("[3/5] diff")
    platform = PLATFORM
    changes = diff_snapshots(old, new, platform=platform,
                             target_milestone=new.milestone, mode=args.mode)
    _log(f"  {len(changes)} semantic changes ({args.mode} mode)")

    _log("[4/5] downstream profile")
    if args.profile:
        # Both snapshots: a symbol that exists only in the old one is a
        # dependency upstream just deleted, which is the highest-value finding.
        touch = load_profile(args.profile, snapshots=[old, new], log=_log)
    else:
        touch = TouchSet(name="downstream (no profile)", platform=platform)
        _log("  no --profile given: scoring on intrinsic severity only")

    findings = score_all(changes, touch, mode=args.mode)
    # Group related findings before anything reads them. One upstream change
    # arrives as fragments across several surfaces; ungrouped they contradict
    # each other.
    clusters = cluster.annotate(findings)
    if clusters:
        biggest = max(len(m) for m in clusters.values())
        _log(f"  {len(clusters)} clusters link related findings "
             f"(largest: {biggest} findings)")
    finding_summary = summarize_findings(findings, touch)
    finding_summary["clusters"] = cluster.summarize(clusters)
    _log(f"  {finding_summary['with_evidence']} findings intersect our fork")
    _log_coverage(finding_summary.get("area_coverage") or {})

    milestone_brief: List[dict] = []
    if not args.no_enrich:
        _log("[5/5] chromestatus enrichment")
        milestones = _milestone_span(old.milestone, new.milestone)
        chromestatus.enrich([f for f in findings if f.bucket != "fyi"],
                            milestones, args.cache, refresh=args.refresh,
                            log=_log)
        # Per-finding matching is weak by nature (prose names vs identifiers),
        # so the shipped-feature list is carried whole as well. It is the one
        # piece of context that says what Chromium *meant* to ship in this
        # window, and the reader of the report -- human or agent -- needs it
        # for exactly the reason a matcher cannot supply it.
        milestone_brief = chromestatus.milestone_brief(
            milestones, args.cache, refresh=args.refresh, log=_log)
        _log(f"  milestone brief: {len(milestone_brief)} shipped features")
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
            "product": touch.name,
            "platform": platform,
            "generated": _now(),
            "target_set": args.target_set,
            "mode": args.mode,
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
            "profile": touch.provenance,
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
    print(f"  must fix:    {counts.get('must_fix', 0)}")
    print(f"  needs review:{counts.get('review', 0):>4}")
    print(f"  opportunity: {counts.get('opportunity', 0)}")
    print(f"  fyi:         {counts.get('fyi', 0)}")
    print()
    print(f"  {md_path}")
    print(f"  {html_path}")
    print(f"  {json_path}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Verify a fresh machine can actually run the pipeline.

    Every check here corresponds to a failure seen in practice: a Python too
    old for the syntax, a proxy that blocks one host but not another, a cache
    directory on a read-only mount, a profile with a typo.  Reporting them
    together beats discovering them one at a time two minutes into a run.
    """
    import json as _json
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
            print(f"        proxy env: {var}={os.environ[var]}")

    if args.profile:
        print("downstream profile")
        try:
            touch = load_profile(args.profile, log=lambda m: None)
            report(f"{args.profile} parses", True,
                   f"{len(touch.areas)} areas, {len(touch.modified_paths)} paths, "
                   f"{len(touch.symbols)} symbols")
            if not touch.has_evidence():
                print("        warning: no evidence sources resolved; nothing "
                      "can reach 'Must fix'")
        except Exception as exc:
            report(f"{args.profile} parses", False, str(exc))

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


def cmd_discover(args: argparse.Namespace) -> int:
    """Find the vendor's own files without being told where they are.

    A fork of this shape puts its files inside Chromium's directories, so the
    list of "ours" is not derivable from Chromium's layout -- and after enough
    years nobody has it written down. Both `vendor_markers` and the target list
    were being filled in from memory, and a forgotten path removes a whole
    surface from every comparison without saying so.
    """
    if not args.token and not args.suffix:
        _log("error: give at least one --token or --suffix naming your fork's "
             "own code, e.g. --token acme --suffix=-acme.")
        _log("       There is no default: this tool carries no vendor "
             "vocabulary, and a guessed marker invents matches rather than "
             "failing.")
        return 1
    report = discover.scan(args.fork_src,
                           dir_tokens=args.token or (),
                           file_suffixes=args.suffix or (),
                           scan_content=args.scan_content, log=_log)
    print()
    for line in discover.summarize(report):
        print(line)

    fetchable, unreadable = discover.uncovered_dirs(report, args.target_set)
    if fetchable:
        total = sum(n for _, n in fetchable)
        print()
        print(f"FIXABLE — {total} vendor files an extractor would read, in "
              f"{len(fetchable)} directories the target list never fetches.")
        print("They are absent from every comparison and nothing else says so. "
              "Add the ones that matter to chromedrift/targets.py:")
        for directory, n in fetchable[: args.limit]:
            print(f"  {n:5d}  {directory}/")
        if len(fetchable) > args.limit:
            print(f"  ... and {len(fetchable) - args.limit} more directories")
    else:
        print()
        print("Every vendor file an extractor could read is already in the "
              "target set.")

    if unreadable:
        total = sum(n for _, n in unreadable)
        print()
        print(f"OUT OF MODEL — {total} vendor files in {len(unreadable)} "
              f"directories that no extractor reads whatever we fetch.")
        print("Native C++ UI, .grd strings, build files. Adding a target changes "
              "nothing; state these in the report's limits instead.")
        for directory, n in unreadable[: args.limit]:
            print(f"  {n:5d}  {directory}/")
        if len(unreadable) > args.limit:
            print(f"  ... and {len(unreadable) - args.limit} more directories")

    print()
    print("Paste into the profile (verify by hand -- these are observations, "
          "not proof of ownership):")
    print(discover.suggest_profile(report))

    if args.out:
        write_json(args.out, report.to_dict())
        print(f"\nwritten: {args.out}")
    return 0


def cmd_provenance(args: argparse.Namespace) -> int:
    """Separate deliberate divergence from merge debt.

    A two-way diff cannot tell "we changed this on purpose" from "a merge
    dropped this and nobody noticed". Comparing the fork against the *series*
    of upstream versions it was merged from can: matching an older version
    exactly means we are stale, not that we decided anything.
    """
    _log(f"fork snapshot: {args.fork}")
    fork = build_snapshot(args.fork, args.cache, args.target_set,
                          platform=PLATFORM, local_src=args.fork_src,
                          refresh=args.refresh, partitions=args.partitions,
                          log=_log)

    upstream = []
    for ref in args.upstream:
        _log(f"upstream snapshot: {ref}")
        upstream.append(build_snapshot(ref, args.cache, args.target_set,
                                       platform=PLATFORM,
                                       refresh=args.refresh,
                                       partitions=args.partitions,
                          complete=args.complete, log=_log))

    report = provenance.analyze(upstream=upstream, fork=fork,
                                base_ref=args.base)
    print()
    for line in provenance.summarize(report):
        print(line)

    debt = report.debt()
    if debt:
        print(f"\nTop merge debt ({min(len(debt), args.limit)} of {len(debt)}):")
        for v in debt[: args.limit]:
            where = f" (matches {v.matches})" if v.matches else ""
            print(f"  {v.state:12s} {v.kind:22s} {v.key[:44]:44s}{where}")

    # Value comparison alone cannot see a declaration the fork shadows with a
    # build flag, because upstream's branch is genuinely unchanged.
    if args.profile:
        markers = coverage.VendorMarkers.from_profile(jsonc.load(args.profile))
        cov = coverage.analyze(fork=fork, upstream=upstream[-1], markers=markers)
        print()
        for line in coverage.summarize(cov):
            print(line)
        if args.out:
            write_json(args.out.replace(".json", "") + ".coverage.json",
                       cov.to_dict())

    if args.out:
        write_json(args.out, report.to_dict())
        print(f"\nwritten: {args.out}")
    return 0


def _log_coverage(coverage: dict) -> None:
    """Always show where findings landed, including what landed nowhere."""
    areas = coverage.get("areas") or {}
    unassigned = coverage.get("unassigned") or {}
    if not areas and not unassigned.get("total"):
        return
    _log("  area coverage:")
    for area_id, row in areas.items():
        owner = f" [{row['owner']}]" if row.get("owner") else ""
        _log(f"    {area_id:22s} {row['total']:5d} findings, "
             f"{row['actionable']} actionable{owner}")
    total = unassigned.get("total", 0)
    if total:
        _log(f"    {'(no area)':22s} {total:5d} findings, "
             f"{unassigned.get('actionable', 0)} actionable, "
             f"{unassigned.get('scoring_60_plus', 0)} scoring 60+")
        if unassigned.get("scoring_60_plus"):
            _log("      ^ these have no owner. Assign an area or review them "
                 "explicitly; a scoped report will not show them.")


def cmd_report(args: argparse.Namespace) -> int:
    report = Report.from_dict(read_json(args.report))
    platform = report.meta.get("platform", PLATFORM)

    if args.list_areas:
        coverage = (report.summary or {}).get("area_coverage") or {}
        rows = coverage.get("areas") or {}
        print(f"{len(report.findings)} findings in {args.report}\n")
        for area_id, row in rows.items():
            owner = f"  owner={row['owner']}" if row.get("owner") else ""
            kind = f"  kind={row['kind']}" if row.get("kind") else ""
            print(f"  {area_id:22s} {row['total']:5d} findings, "
                  f"{row['actionable']} actionable{kind}{owner}")
        un = coverage.get("unassigned") or {}
        if un.get("total"):
            print(f"  {'_unassigned':22s} {un['total']:5d} findings, "
                  f"{un.get('actionable', 0)} actionable, "
                  f"{un.get('scoring_60_plus', 0)} scoring 60+")
        print("\nRe-render one slice with:  --area <id>")
        return 0

    if args.area:
        known = set(report.known_areas()) | {"_unassigned"}
        if args.area not in known:
            _log(f"error: unknown area {args.area!r}. Known: "
                 f"{', '.join(sorted(known)) or '(none)'}")
            return 1
        report = report.filtered(args.area)
        _log(f"  filtered to area {args.area!r}: {len(report.findings)} findings")

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


def _milestone_span(start: Optional[int], end: Optional[int]) -> List[int]:
    if not end:
        return []
    if not start or start >= end:
        return [end]
    # Cap the span: each milestone is one API call, and the useful context is
    # concentrated in the milestones being adopted.
    return list(range(start + 1, min(end, start + 8) + 1))


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chromedrift",
        description="Detect what changed between two Chromium versions and "
                    "what it means for a downstream browser.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    # Flags are grouped so that a command only offers the ones it acts on.
    # They used to come from one shared parent, which meant `catalog` accepted
    # --local-src and --mode and silently did nothing with either.

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
                             "others -- about 315 MB per version, and it reads "
                             "everything an extractor understands. Use it for "
                             "a release gate. minimal: three files, for smoke "
                             "tests. Every run measures and prints the "
                             "coverage it achieved")
    which_files = argparse.ArgumentParser(add_help=False, parents=[target_set])
    which_files.add_argument("--partition", action="append", dest="partitions",
                             metavar="NAME",
                             help="limit what is fetched and scanned to one "
                             "part of the product (repeatable). Faster, and "
                             "less complete by design: a change affecting "
                             "downloads can live in content/ or in a Mojo "
                             "interface and match no partition. Use the full "
                             "set for a release gate. Available: "
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

    # Each side of a comparison can come from its own tree. Comparing a vendor
    # fork against upstream needs exactly that, and a single --local-src would
    # point both sides at the same one.
    two_checkouts = argparse.ArgumentParser(add_help=False,
                                            parents=[one_checkout])
    two_checkouts.add_argument("--from-src", default=None,
                               help="checkout for the FROM side only "
                                    "(overrides --local-src)")
    two_checkouts.add_argument("--to-src", default=None,
                               help="checkout for the TO side only, e.g. a "
                                    "vendor fork (overrides --local-src)")

    compare = argparse.ArgumentParser(add_help=False)
    compare.add_argument("--mode", default=MODE_UPREV, choices=MODES,
                         help="uprev: upstream over time (default). "
                              "fork: upstream vs a vendor fork at the same "
                              "milestone, where a missing fact means the "
                              "vendor removed it")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snapshot", parents=[cache, which_files, one_checkout],
                       help="extract the feature surface of one Chromium ref")
    p.add_argument("ref", help="milestone (143), version (143.0.7499.40) or git ref")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("diff", parents=[cache, which_files, two_checkouts, compare],
                       help="semantic diff between two refs")
    p.add_argument("from_ref", metavar="FROM")
    p.add_argument("to_ref", metavar="TO")
    p.add_argument("--out", help="write changes JSON here")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("profile", parents=[cache, which_files],
                       help="inspect what a downstream profile resolves to")
    p.add_argument("profile", help="path to the profile json5")
    p.add_argument("--ref", help="snapshot ref to build the symbol vocabulary from")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("run", parents=[cache, which_files, two_checkouts, compare],
                       help="full pipeline: snapshot, diff, score, report")
    p.add_argument("from_ref", metavar="FROM")
    p.add_argument("to_ref", metavar="TO")
    p.add_argument("--profile", help="downstream profile json5")
    p.add_argument("--out", default="out", help="output directory (default: out)")
    p.add_argument("--no-enrich", action="store_true",
                   help="skip chromestatus enrichment")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("check",
                       help="verify this machine can run the pipeline")
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--profile", help="also validate a downstream profile")
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

    p = sub.add_parser("discover", parents=[target_set],
                       help="find the vendor's own files in a fork checkout")
    p.add_argument("--fork-src", required=True,
                   help="path to the fork checkout (read from disk, no network)")
    p.add_argument("--token", action="append",
                   help="directory name marking vendor code, e.g. acme "
                        "(repeatable; no default -- see --suffix)")
    p.add_argument("--suffix", action="append",
                   help="filename suffix marking a vendor variant of an "
                        "upstream file (repeatable). Write it with an equals "
                        "sign, --suffix=-acme, or argparse reads the leading "
                        "dash as another option. At least one --token or "
                        "--suffix is required: the tool carries no vendor "
                        "vocabulary of its own")
    p.add_argument("--scan-content", action="store_true",
                   help="also read sources for #if defined(<VENDOR>_*) guards "
                        "(minutes, not seconds)")
    p.add_argument("--limit", type=int, default=30,
                   help="how many uncovered directories to print (default: 30)")
    p.add_argument("--out", help="write the full report JSON here")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("provenance", parents=[cache, which_files],
                       help="separate deliberate divergence from merge debt")
    p.add_argument("fork", help="label for the fork snapshot, e.g. fork-main-dev")
    p.add_argument("upstream", nargs="+",
                   help="upstream refs oldest first, e.g. 143.0.x 148.0.x")
    p.add_argument("--fork-src", required=True,
                   help="path to the fork checkout")
    p.add_argument("--base", default=None,
                   help="which upstream ref the fork claims to be based on "
                        "(default: the newest one given)")
    p.add_argument("--limit", type=int, default=25,
                   help="how many debt items to print (default: 25)")
    p.add_argument("--profile",
                   help="profile json5 with vendor_markers, for shadow analysis")
    p.add_argument("--out", help="write the full report JSON here")
    p.set_defaults(func=cmd_provenance)

    p = sub.add_parser("report",
                       help="re-render a saved report.json, optionally one area")
    p.add_argument("report", help="path to report.json")
    p.add_argument("--format", default="md", choices=("md", "html", "both"))
    p.add_argument("--out", help="output path (stdout if omitted)")
    p.add_argument("--area",
                   help="render only this area, or _unassigned for the leftover")
    p.add_argument("--list-areas", action="store_true",
                   help="list areas present in the report and exit")
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
