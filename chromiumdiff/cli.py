"""Command-line interface.

Each pipeline stage is also its own subcommand.  That is not decoration: the
expensive stage (snapshots) and the stage you iterate on (scoring, reports)
have completely different cost profiles, and being able to re-run the cheap
half against a warm cache is the difference between a tool people tune and a
tool people run once.

The pipeline stops at the report.  Judging what a change means for a
particular product is deliberately not done here: the report is the input to a
reader -- a human, or an agent running the `analyzing-chromium-upgrades` skill --
and this tool's job is to make that input complete, ranked and citable rather
than to reach a verdict of its own.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import os
import shutil
import sys
from typing import List, Optional

from . import __version__
from .acquire import CHROMIUMDASH, GITILES_BASE, USER_AGENT
from .extract._cpp import PLATFORM
from . import catalog, cluster
from .agent import briefing
from .diff import diff_snapshots, summarize
from . import serve as serve_mod
from .enrich import chromestatus, gerrit
from .model import (BUCKET_HOUSEKEEPING, BUCKET_LABELS, BUCKET_ORDER,
                    SCHEMA_VERSION, VERDICT_MEANINGS, Report, read_json,
                    write_json)
from .report import html as html_report
from .report import markdown as md_report
from .score import Scope, score_all, summarize_findings
from .snapshot import build_snapshot
from .targets import partition_names

DEFAULT_CACHE = os.environ.get("CHROMIUMDIFF_CACHE", ".chromiumdiff-cache")


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


def cmd_compare(args: argparse.Namespace) -> int:
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
    scope = scope_for(old, new)
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
    # Written with the report rather than on request, because the thing it
    # prevents happens on the first command somebody runs here and there is no
    # request before that. It costs about a thousand tokens and one file.
    brief_path = briefing.write(report, out_dir)

    counts = report.bucket_counts()
    print()
    print(f"{old.ref} -> {new.ref}")
    for bucket in BUCKET_ORDER:
        print(f"  {BUCKET_LABELS[bucket]:18s} {counts.get(bucket, 0):5d}")
    print()
    print(f"  {md_path}")
    print(f"  {html_path}")
    print(f"  {json_path}")
    print(f"  {brief_path}")
    print()
    print(f"  why each row changed:  python3 -m chromiumdiff serve {out_dir}")
    return 0



def _redact_proxy(value: str) -> str:
    """Keep the host, drop anything that could be a credential."""
    remainder = value.rsplit("@", 1)
    if len(remainder) == 2:
        scheme = value.split("://", 1)[0] + "://" if "://" in value else ""
        return f"{scheme}<redacted>@{remainder[1]}"
    return value



def scope_for(old, new) -> Scope:
    """What the scoring stage is allowed to conclude from this pair.

    Both trees. A removal is an absence from the new one and an addition is an
    absence from the old one, so each direction is judged by the read of the
    side its evidence comes from. `Scope` learned to hold both and the call
    site kept passing one -- the same two-door mistake as the Mojo ordinal, so
    it is a named function now and a test drives it rather than reading it.
    """
    return Scope({"from": (old.meta or {}).get("coverage") or {},
                  "to": (new.meta or {}).get("coverage") or {}},
                 to_ref=new.ref, incomplete=_incomplete_reason(new),
                 from_incomplete=_incomplete_reason(old))


def _incomplete_reason(snapshot) -> str:
    """Why this snapshot cannot settle an absence, beyond how much it read.

    A target the source did not have, and a file that would not parse, both
    leave a hole shaped exactly like a removal: a fact on one side and not the
    other. Coverage cannot see either -- it measures what was in scope, not
    what came back -- so an absence is not confirmed while either is non-zero.
    Both are zero on every version measured so far, which is why this is a
    latch rather than a fix.
    """
    meta = snapshot.meta or {}
    missing = meta.get("missing_targets") or []
    errors = (meta.get("extract_stats") or {}).get("_errors") or 0
    reasons = []
    if missing:
        reasons.append(f"{len(missing)} target(s) the source did not have")
    if errors:
        reasons.append(f"{errors} file(s) that would not parse")
    return " and ".join(reasons)


# One clean fetch of the default target set costs 79 MB for a single version
# (36 MB of trees, 32 MB of directory listings, 12 MB of snapshot), so a pair
# costs about this much. The wide set roughly doubles it. README quotes the
# same number; a test keeps the two together.
PAIR_DISK_MB = 150


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
            print("        note: two versions on the default target set take"
                  f" roughly {PAIR_DISK_MB} MB; --target-set wide about doubles it")
    except OSError as exc:
        report(f"{args.cache} writable", False, str(exc))

    print("network")
    for label, url in (
        ("gitiles (source)", f"{GITILES_BASE}/+/refs/heads/main/DEPS?format=TEXT"),
        ("chromiumdash (version resolution)",
         f"{CHROMIUMDASH}/fetch_milestones?mstone=143"),
        ("chromestatus (enrichment, optional)",
         "https://chromestatus.com/api/v0/features?milestone=143"),
        # `serve` only. Named here because it is the one host a lookup needs
        # that neither `run` nor `snapshot` ever touches, so a machine that
        # passes `check` and then cannot answer a click would have had no
        # warning.
        ("chromium-review (provenance, optional)",
         f"{gerrit.GERRIT}/changes/?q=status:merged&n=1"),
    ):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                size = len(resp.read(2048))
            report(label, size > 0, f"HTTP 200")
        except Exception as exc:
            optional = "optional" in label
            skip = " (skippable with --no-enrich)" if "enrichment" in label else (
                " (only `serve` needs it)" if optional else "")
            report(label, optional, f"{exc}{skip}")

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
              "in chromiumdiff/targets.py.")

    if args.out:
        write_json(args.out, report.to_dict())
        print(f"\nwritten: {args.out}")
    return 0


FIGURES_PATH = "docs/figures.json"


def measured_figures(report: Report, wide: Optional[Report] = None) -> dict:
    """Every number the shipped documents quote, taken from a real run.

    The documents state measurements -- bucket counts, owner totals, coverage,
    the share of findings with no signal -- and every one of them was being
    kept up to date by hand. Six times in one working session a figure was
    corrected only because a test happened to look at it, and four of the
    wrong ones had been written by the same hand that was correcting them.

    So the figures become an artifact. `chromiumdiff figures` writes it from a
    report, the documents quote it, and a test holds the documents to it
    without needing anyone to have run the tool.
    """
    from .diff import SIGNAL_OWNERS, SIGNAL_SEVERITY, leading_signal
    from .model import KIND_OWNERS, OWNER_NATIVE

    def owner_of_finding(finding):
        lead = leading_signal(finding.change)
        return (SIGNAL_OWNERS.get(lead)
                or KIND_OWNERS.get(finding.change.kind, OWNER_NATIVE))

    breaking_by_owner: dict = {}
    for finding in report.findings:
        if finding.bucket == "breaking":
            owner = owner_of_finding(finding)
            breaking_by_owner[owner] = breaking_by_owner.get(owner, 0) + 1

    # What the CL-and-issue stage found, over whatever rows the report has had
    # resolved. Every figure here moved when the candidate window was
    # corrected, and every document quoting one had to be re-measured by hand
    # -- twice, because the first sweep only looked for flags and commands.
    # `rows` is emitted beside them so the numbers carry their own denominator
    # and a report with three rows resolved cannot read like a run.
    from .enrich.gerrit import CITES, strength

    prov: dict = {}
    resolved = [f for f in report.findings
                if ((f.enrichment or {}).get("gerrit") or {}).get("changes")]
    if resolved:
        verdicts: dict = {}
        issues: dict = {}
        named = 0
        cls = 0
        for finding in resolved:
            block = finding.enrichment["gerrit"]
            changes = block["changes"]
            cls += len(changes)
            if any(strength(c.get("match")) < CITES for c in changes):
                named += 1
            for change in changes:
                verdicts[change.get("match")] = verdicts.get(
                    change.get("match"), 0) + 1
                for bug in change.get("bugs") or []:
                    issues.setdefault(bug["id"], False)
                    if bug.get("restricted"):
                        issues[bug["id"]] = True
            for issue in block.get("issues") or []:
                issues.setdefault(issue["id"], bool(issue.get("restricted")))
                if issue.get("restricted"):
                    issues[issue["id"]] = True
        prov = {
            "rows": len(resolved),
            "rows_named_by_a_verdict": named,
            "rows_leads_only": len(resolved) - named,
            "cls_cited": cls,
            "verdicts": dict(sorted(verdicts.items())),
            "issues_linked": len(issues),
            "issues_restricted": sum(1 for v in issues.values() if v),
        }

    summary = report.summary or {}
    coverage = (report.meta or {}).get("coverage") or {}
    out = {
        "pair": [report.from_ref, report.to_ref],
        "schema": SCHEMA_VERSION,
        "total": summary.get("total"),
        "not_in_build": summary.get("not_in_build"),
        "buckets": summary.get("by_bucket") or {},
        "owners": summary.get("by_owner") or {},
        "breaking_by_owner": breaking_by_owner,
        "no_signal": sum(1 for f in report.findings
                         if not f.change.signals),
        "coverage": {"default": {k: v for k, v in (coverage.get("to") or {}).items()
                                 if k in ("read", "candidates")}},
    }
    # Absent rather than zeroed on a report nothing has been looked up in: a
    # figure of 0 reads as a measurement, and there was no measurement.
    if prov:
        out["provenance"] = prov
    if wide is not None:
        wide_cov = ((wide.meta or {}).get("coverage") or {}).get("to") or {}
        out["coverage"]["wide"] = {k: v for k, v in wide_cov.items()
                                   if k in ("read", "candidates")}
    return out


def cmd_figures(args: argparse.Namespace) -> int:
    report = Report.from_dict(read_json(args.report))
    wide = Report.from_dict(read_json(args.wide)) if args.wide else None
    figures = measured_figures(report, wide)
    # A `wide` run is expensive and rarely on disk, so this is usually invoked
    # without one -- and dropping the section that needed it would silently
    # delete a real measurement, which is the failure this artifact exists to
    # prevent. What cannot be recomputed is carried forward instead, and said
    # out loud so nobody reads a stale figure as a fresh one.
    if wide is None and os.path.exists(args.out):
        try:
            previous = read_json(args.out)
        except (OSError, ValueError):
            previous = {}
        kept = (previous.get("coverage") or {}).get("wide")
        if kept:
            figures["coverage"]["wide"] = kept
            print(f"  kept coverage.wide from {args.out} "
                  f"(re-run with --wide to remeasure it)")
    write_json(args.out, figures)
    print(f"  figures -> {args.out}")
    for key in ("total", "not_in_build", "no_signal"):
        print(f"    {key}: {figures[key]}")
    print(f"    buckets: {figures['buckets']}")
    print(f"    owners: {figures['owners']}")
    prov = figures.get("provenance")
    if prov:
        print(f"    provenance: {prov['rows_named_by_a_verdict']} of "
              f"{prov['rows']} rows named by a verdict, {prov['cls_cited']} "
              f"CLs, {prov['issues_restricted']} of {prov['issues_linked']} "
              f"issues restricted")
    else:
        print("    provenance: no row in this report has been looked up")
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


def cmd_package(args: argparse.Namespace) -> int:
    """Write the tool into one file, for somebody who does not have a checkout.

    The point is not distribution for its own sake. A report is read by people
    who did not make it, and telling them to clone a repository and find an
    interpreter is how a report goes unread.
    """
    from .agent import package as package_mod

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills = args.skills or os.path.join(root, "skills")
    written = package_mod.build(args.out, skills=skills
                                if os.path.isdir(skills) else None)
    size = os.path.getsize(written)
    print(f"written: {written}  ({size / 1000:.0f} kB)")
    if not os.path.isdir(skills):
        # Said rather than passed over: a copy that answers without the skills
        # answers differently, and the person running this is the only one who
        # can tell whether that matters.
        print(f"  no skills/ at {skills} -- the archive has the tool but not "
              f"the method it is meant to follow", file=sys.stderr)
    print(f"  run it with:  python3 {os.path.basename(written)} serve <report>")
    return 0


def _report_directory(path: str) -> Optional[str]:
    """The directory holding `report.json`, from that directory or that file.

    Shared rather than repeated: two commands take the same argument and have
    to accept it in the same two forms, and the second copy of a rule like
    this is where they stop agreeing.
    """
    directory = path
    if os.path.isfile(directory):
        directory = os.path.dirname(os.path.abspath(directory))
    if not os.path.exists(os.path.join(directory, "report.json")):
        print(f"no report.json in {directory} -- run `run` first",
              file=sys.stderr)
        return None
    return directory


def cmd_serve(args: argparse.Namespace) -> int:
    """Serve a report so it can resolve a row's CL when that row is opened.

    `run` resolves nothing, so the file it writes can be mailed and read
    anywhere. This pays per row instead, and nothing is spent on the 3,000
    nobody opens.
    """
    directory = _report_directory(args.report)
    if directory is None:
        return 1
    chat = None
    if args.chat:
        from .agent import chat as chat_mod
        from .agent import engine as engine_mod
        try:
            engine = engine_mod.build(args.engine)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        # Refused at startup rather than at the first question. A panel that
        # appears and then says it cannot answer has already cost the reader
        # the time it took to type one.
        reason = engine.available()
        if reason:
            print(f"--chat needs an engine that can run: {reason}",
                  file=sys.stderr)
            return 1
        chat = chat_mod.Chat(directory, engine, allow_shell=not args.no_shell)
    return serve_mod.serve(directory, args.cache, port=args.port,
                           budget=args.click_budget, refresh=args.refresh,
                           save=not args.no_save, chat=chat, log=print)


def cmd_why(args: argparse.Namespace) -> int:
    """Look one row up, from a terminal rather than from a click.

    `serve` already does this, and does it better for a person: a report is
    open, a row is in front of them, and the lookup is a click. What it cannot
    serve is anything that is not a browser -- a script, a note being written,
    or a model asked what a finding means. Those had one route to the CL
    behind a row, which was to open a browser and click it.

    The work is `serve`'s own: the same lookup, the same per-row budget, the
    same write back into `report.json`, so a row resolved here is resolved for
    the page too and the next reader pays nothing for it.
    """
    directory = _report_directory(args.report)
    if directory is None:
        return 1
    state = serve_mod._State(directory, args.cache, args.click_budget,
                             save=not args.no_save, refresh=args.refresh)
    finding = state.by_uid.get(args.uid)
    if finding is None:
        print(f"no finding with uid {args.uid!r} in this report",
              file=sys.stderr)
        # A near miss is the common case -- a truncated uid, a kind prefix
        # left off, the name without its interface -- and the alternative to
        # naming the neighbours is that the caller has to go and grep 3,000
        # of them for a spelling it already almost had.
        #
        # Containment is tried first because it is what the common miss looks
        # like: the caller had a real name and dropped the prefix, so the uid
        # they want has theirs inside it. Edit distance ranks by how a string
        # looks rather than by what it holds, and offered
        # `flag_entry:dse-preload2-on-press` for a Mojo field.
        near = [uid for uid in state.by_uid if args.uid in uid][:5]
        if not near:
            near = difflib.get_close_matches(args.uid, list(state.by_uid),
                                             5, 0.5)
        if near:
            print("did you mean:", file=sys.stderr)
            for uid in near:
                print(f"  {uid}", file=sys.stderr)
        return 1
    try:
        state.resolve(args.uid)
    except Exception as exc:  # a failed lookup is an answer, not a crash
        print(f"lookup failed: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps({"uid": args.uid,
                          "change": finding.change.to_dict(),
                          "bucket": finding.bucket,
                          "score": finding.score,
                          "reasons": finding.reasons,
                          "gerrit": (finding.enrichment or {}).get("gerrit")
                          or {}}, indent=1))
    else:
        print(_why_text(args.uid, finding))
    return 0


def _why_text(uid: str, finding) -> str:
    """One row's answer, with what each verdict claims printed beside it.

    The verdict is the whole point and it is one word, so the word goes with
    its sentence every time rather than on a ladder the reader is assumed to
    have memorised. `touched` and `introduced` are both "a CL", and treating
    them alike is the mistake this output exists to prevent.
    """
    out: List[str] = [uid]
    change = finding.change
    where = (change.locations or change.paths or [""])[0]
    out.append(f"  {finding.bucket}, score {finding.score}"
               + (f", {', '.join(change.signals)}" if change.signals else ""))
    if where:
        out.append(f"  {where}")
    for reason in finding.reasons:
        out.append(f"  {reason}")

    block = (finding.enrichment or {}).get("gerrit") or {}
    changes = block.get("changes") or []
    window = block.get("window") or []
    pool = block.get("candidates")
    out.append("")
    if window and pool is not None:
        out.append(f"  {pool} CL(s) touched this declaration between "
                   f"{window[0]} and {window[1]}"
                   + (", and their diffs were read"
                      if block.get("diffs_read") else ""))
    if not changes:
        # The one thing this stage must never be read as saying is "nothing
        # changed this". It searched and did not find, which is a different
        # sentence and leads somewhere else.
        out.append("  no CL in that window names this identifier. That is a "
                   "search that came back empty, not a change with no cause.")
        if block.get("failed_fetches"):
            out.append(f"  {block['failed_fetches']} request(s) failed, so the "
                       f"search was not finished -- ask again to retry them")
        return "\n".join(out)

    for cl in changes:
        verdict = cl.get("match", "")
        out.append(f"  CL {cl.get('number')}  {cl.get('date', '')}  {verdict}")
        out.append(f"    {cl.get('subject', '')}")
        out.append(f"    {cl.get('url', '')}")
        meaning = VERDICT_MEANINGS.get(verdict)
        if meaning:
            out.append(f"    {verdict}: {meaning}")
        for bug in cl.get("bugs") or []:
            out.append(f"    bug {bug.get('id')}: "
                       f"https://issues.chromium.org/issues/{bug.get('id')}")
        out.append("")
    # Said here because this is the moment it is wrong to stop: the CL is in
    # hand, it reads like an answer, and it answers a different question.
    out.append("  the CL says what was done; the issue it cites says what was "
               "wrong. They are different answers.")
    return "\n".join(out)


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
        prog="chromiumdiff",
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

    p = sub.add_parser("compare", parents=[cache, which_files, two_checkouts],
                       help="semantic comparison between two refs")
    p.add_argument("from_ref", metavar="FROM")
    p.add_argument("to_ref", metavar="TO")
    p.add_argument("--out", help="write changes JSON here")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("run",
                       parents=[cache, which_files, two_checkouts],
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

    p = sub.add_parser("figures",
                       help="write the measurements the documents quote")
    p.add_argument("report", help="path to a default-target-set report.json")
    p.add_argument("--wide", help="path to a wide report.json, for its coverage")
    p.add_argument("--out", default=FIGURES_PATH)
    p.set_defaults(func=cmd_figures)

    p = sub.add_parser("serve",
                       help="serve a report on localhost, where opening a row "
                            "looks its CL up on demand")
    p.add_argument("report", help="report directory, or a report.json in one")
    # Its own --cache rather than the shared pair: a server has nothing to
    # refresh, since a lookup either hits the cache or was never made.
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--no-save", action="store_true",
                   help="do not write what was looked up back to report.json")
    # A re-asked row still reads the HTTP cache, so a bad response cached once
    # is a bad answer for ever. Its own flag rather than the shared pair,
    # because a server has no snapshot to refetch -- only Gerrit's answers.
    p.add_argument("--refresh", action="store_true",
                   help="ignore the cached Gerrit responses and ask again")
    p.add_argument("--click-budget", type=int,
                   default=serve_mod.CLICK_BUDGET, metavar="N",
                   help=f"read at most N diffs per row opened "
                        f"(default: {serve_mod.CLICK_BUDGET}, 0 for no "
                        f"ceiling). Only the busiest two declaration files in "
                        f"the tree come near it")
    # Off unless asked for, and the help says why rather than leaving it to be
    # found out. Without it this server reads a report; with it, a question
    # typed into a browser runs commands on this machine.
    p.add_argument("--chat", action="store_true",
                   help="add a chat panel to the page. Questions are answered "
                        "by running commands in the report directory on this "
                        "machine, so turn it on for a report you trust")
    p.add_argument("--engine", default="",
                   help="which backend answers (default: http, configured by "
                        "CHROMIUMDIFF_MODEL_URL)")
    p.add_argument("--no-shell", action="store_true",
                   help="answer with python queries only, no shell commands")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("why",
                       help="look up the CL behind one finding, without a "
                            "browser")
    p.add_argument("uid", help="the finding's uid, as report.json spells it")
    # Optional and defaulting to here, because the caller is usually already
    # standing in the report's directory -- a shell in it, or a script run
    # from it -- and naming the directory again is a step that can be wrong.
    p.add_argument("report", nargs="?", default=".",
                   help="report directory, or a report.json in one "
                        "(default: the current directory)")
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="the raw finding and its Gerrit block, for a program")
    p.add_argument("--no-save", action="store_true",
                   help="do not write what was looked up back to report.json")
    p.add_argument("--refresh", action="store_true",
                   help="ignore the cached Gerrit responses and ask again")
    p.add_argument("--click-budget", type=int,
                   default=serve_mod.CLICK_BUDGET, metavar="N",
                   help=f"read at most N diffs for this row "
                        f"(default: {serve_mod.CLICK_BUDGET}, 0 for no "
                        f"ceiling)")
    p.set_defaults(func=cmd_why)

    p = sub.add_parser("package",
                       help="write the whole tool into one runnable file")
    p.add_argument("--out", default="chromiumdiff.pyz",
                   help="where to write it (default: chromiumdiff.pyz)")
    p.add_argument("--skills", default="",
                   help="skills directory to include (default: skills/ beside "
                        "this checkout)")
    p.set_defaults(func=cmd_package)

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
    `chromiumdiff report ... > report.md` dies with

        'charmap' codec can't encode character '\\u2192'

    and so does `chromiumdiff check`, whose own output uses an em-dash -- which
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
        if os.environ.get("CHROMIUMDIFF_DEBUG"):
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
