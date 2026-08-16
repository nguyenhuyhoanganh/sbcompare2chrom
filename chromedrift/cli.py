"""Command-line interface.

Each pipeline stage is also its own subcommand.  That is not decoration: the
expensive stage (snapshots) and the stage you iterate on (scoring, prompts,
reports) have completely different cost profiles, and being able to re-run the
cheap half against a warm cache is the difference between a tool people tune
and a tool people run once.
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
from .ai.analyze import analyze
from .ai.client import LLMClient, LLMConfig
from . import cluster, coverage, provenance
from .diff import MODE_FORK, MODE_UPREV, MODES, diff_snapshots, summarize
from .enrich import chromestatus
from .impact import score_all, summarize_findings
from .model import Report, read_json, write_json
from .report import html as html_report
from .report import markdown as md_report
from .sbprofile import TouchSet, load_profile
from .snapshot import build_snapshot

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
                          platform=args.platform, local_src=args.local_src,
                          refresh=args.refresh, log=_log)
    print(f"{snap.ref}  milestone={snap.milestone}  facts={len(snap.facts)}")
    for kind, count in snap.counts().items():
        print(f"  {kind:24s} {count}")
    if snap.meta.get("missing_targets"):
        print(f"  missing targets: {len(snap.meta['missing_targets'])}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    old = build_snapshot(args.from_ref, args.cache, args.target_set,
                         platform=args.platform, local_src=args.local_src,
                         refresh=args.refresh, log=_log)
    new = build_snapshot(args.to_ref, args.cache, args.target_set,
                         platform=args.platform, local_src=args.local_src,
                         refresh=args.refresh, log=_log)
    changes = diff_snapshots(old, new, platform=args.platform.lower(),
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
        snapshots.append(build_snapshot(args.ref, args.cache, args.target_set,
                                        platform=args.platform, log=_log))
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

    _log(f"[1/6] snapshot {args.from_ref}")
    old = build_snapshot(args.from_ref, args.cache, args.target_set,
                         platform=args.platform, local_src=from_src,
                         refresh=args.refresh, log=_log)
    _log(f"[2/6] snapshot {args.to_ref}")
    new = build_snapshot(args.to_ref, args.cache, args.target_set,
                         platform=args.platform, local_src=to_src,
                         refresh=args.refresh, log=_log)

    _log("[3/6] diff")
    platform = args.platform.lower()
    changes = diff_snapshots(old, new, platform=platform,
                             target_milestone=new.milestone, mode=args.mode)
    _log(f"  {len(changes)} semantic changes ({args.mode} mode)")

    _log("[4/6] downstream profile")
    if args.profile:
        # Both snapshots: a symbol that exists only in the old one is a
        # dependency upstream just deleted, which is the highest-value finding.
        touch = load_profile(args.profile, snapshots=[old, new], log=_log)
    else:
        touch = TouchSet(name="downstream (no profile)", platform=platform)
        _log("  no --profile given: scoring on intrinsic severity only")

    findings = score_all(changes, touch)
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
    _log_coverage(finding_summary.get("coverage") or {})

    milestone_brief = None
    if not args.no_enrich:
        _log("[5/6] chromestatus enrichment")
        milestones = _milestone_span(old.milestone, new.milestone)
        top = [f for f in findings if f.bucket != "fyi"][: args.top or 200]
        chromestatus.enrich(top, milestones, args.cache, refresh=args.refresh,
                            log=_log)
        # Per-finding matching is weak by nature (prose names vs identifiers),
        # so the shipped-feature list is also carried as shared model context.
        milestone_brief = chromestatus.milestone_brief(
            milestones, args.cache, refresh=args.refresh, log=_log)
        _log(f"  milestone brief: {len(milestone_brief)} shipped features")
    else:
        _log("[5/6] enrichment skipped")

    ai_summary = {}
    if not args.no_ai:
        _log("[6/6] AI analysis")
        config = LLMConfig.load(args.llm)
        client = LLMClient(config, cache_dir=args.cache, log=_log)
        _log(f"  provider={config.provider} model={config.model} "
             f"window={config.context_window}")
        _, ai_summary = analyze(findings, touch, client, old.ref, new.ref,
                                top=args.top, milestone_brief=milestone_brief,
                                log=_log)
    else:
        _log("[6/6] AI analysis skipped")

    report = Report(
        from_ref=old.ref,
        to_ref=new.ref,
        findings=findings,
        summary={
            "changes": {"total": len(changes), "by_kind": summarize(changes)},
            **finding_summary,
            "ai": ai_summary,
        },
        meta={
            "product": touch.name,
            "platform": platform,
            "generated": _now(),
            "target_set": args.target_set,
            "mode": args.mode,
            "facts_from": len(old.facts),
            "facts_to": len(new.facts),
            "profile": touch.provenance,
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
    directory on a read-only mount, a profile with a typo, an LLM base_url
    whose hostname does not resolve.  Reporting them together beats
    discovering them one at a time two minutes into a run.
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

    if args.llm:
        print("llm endpoint")
        try:
            config = LLMConfig.load(args.llm)
            report(f"{args.llm} parses", True,
                   f"provider={config.provider} model={config.model} "
                   f"window={config.context_window}")
            if config.provider == "echo":
                print("        note: echo is the offline stub; no model is called")
            elif not config.resolved_key():
                print(f"        warning: {config.api_key_env} is not set in the "
                      f"environment")
            if config.provider != "echo" and config.base_url:
                client = LLMClient(config, log=_log)
                try:
                    client.complete("Reply with exactly: ok", "ping")
                    report("live completion", True)
                except Exception as exc:
                    report("live completion", False, str(exc)[:200])
        except Exception as exc:
            report(f"{args.llm} parses", False, str(exc))

    print()
    print("ready" if ok else "not ready — see FAIL lines above")
    return 0 if ok else 1


def cmd_provenance(args: argparse.Namespace) -> int:
    """Separate deliberate divergence from merge debt.

    A two-way diff cannot tell "we changed this on purpose" from "a merge
    dropped this and nobody noticed". Comparing the fork against the *series*
    of upstream versions it was merged from can: matching an older version
    exactly means we are stale, not that we decided anything.
    """
    _log(f"fork snapshot: {args.fork}")
    fork = build_snapshot(args.fork, args.cache, args.target_set,
                          platform=args.platform, local_src=args.fork_src,
                          refresh=args.refresh, log=_log)

    upstream = []
    for ref in args.upstream:
        _log(f"upstream snapshot: {ref}")
        upstream.append(build_snapshot(ref, args.cache, args.target_set,
                                       platform=args.platform,
                                       refresh=args.refresh, log=_log))

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
    platform = report.meta.get("platform", "android")

    if args.list_areas:
        coverage = (report.summary or {}).get("coverage") or {}
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

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cache", default=DEFAULT_CACHE,
                        help=f"cache directory (default: {DEFAULT_CACHE})")
    common.add_argument("--target-set", default="default",
                        choices=("default", "minimal"),
                        help="which Chromium files to pull")
    common.add_argument("--platform", default="Android",
                        help="platform whose defaults matter (default: Android)")
    common.add_argument("--local-src", default=None,
                        help="use an existing checkout instead of gitiles "
                             "(applies to both sides)")
    common.add_argument("--from-src", default=None,
                        help="checkout for the FROM side only")
    common.add_argument("--to-src", default=None,
                        help="checkout for the TO side only, e.g. a vendor fork")
    common.add_argument("--refresh", action="store_true",
                        help="ignore caches and refetch")
    common.add_argument("--mode", default=MODE_UPREV, choices=MODES,
                        help="uprev: upstream over time (default). "
                             "fork: upstream vs a vendor fork at the same "
                             "milestone, where a missing fact means the vendor "
                             "removed it")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snapshot", parents=[common],
                       help="extract the feature surface of one Chromium ref")
    p.add_argument("ref", help="milestone (143), version (143.0.7499.40) or git ref")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("diff", parents=[common],
                       help="semantic diff between two refs")
    p.add_argument("from_ref", metavar="FROM")
    p.add_argument("to_ref", metavar="TO")
    p.add_argument("--out", help="write changes JSON here")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("profile", parents=[common],
                       help="inspect what a downstream profile resolves to")
    p.add_argument("profile", help="path to the profile json5")
    p.add_argument("--ref", help="snapshot ref to build the symbol vocabulary from")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("run", parents=[common],
                       help="full pipeline: snapshot, diff, impact, AI, report")
    p.add_argument("from_ref", metavar="FROM")
    p.add_argument("to_ref", metavar="TO")
    p.add_argument("--profile", help="downstream profile json5")
    p.add_argument("--llm", help="LLM config json5")
    p.add_argument("--out", default="out", help="output directory (default: out)")
    # Default 0 = no cap. Measured on M148 -> M151: the full non-FYI set is
    # 1,226 findings, about 105k tokens, which fits one 200k-window request.
    # An arbitrary cap was discarding 93% of the analysis to save a cost that
    # does not exist; bound it only for very wide uprevs or small windows.
    p.add_argument("--top", type=int, default=0,
                   help="cap findings sent to the model (default: 0 = no cap)")
    p.add_argument("--no-ai", action="store_true", help="skip the AI stage")
    p.add_argument("--no-enrich", action="store_true",
                   help="skip chromestatus enrichment")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("check",
                       help="verify this machine can run the pipeline")
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--profile", help="also validate a downstream profile")
    p.add_argument("--llm", help="also validate (and ping) an LLM config")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("provenance", parents=[common],
                       help="separate deliberate divergence from merge debt")
    p.add_argument("fork", help="label for the fork snapshot, e.g. sb-main-dev")
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
