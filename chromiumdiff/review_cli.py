"""Bounded command interface for a fresh agent reading report evidence."""

from __future__ import annotations

import json
import os

from . import evidence, review
from .model import read_json, write_json


def _leaves(value, path=""):
    if isinstance(value, dict) and value:
        for key, child in sorted(value.items()):
            yield from _leaves(child, path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list) and value:
        for i, child in enumerate(value):
            yield from _leaves(child, path + "/" + str(i))
    elif isinstance(value, str) and len(value) > 1000:
        for offset in range(0, len(value), 1000):
            yield {"pointer": path, "offset": offset, "value": value[offset:offset + 1000],
                   "string_length": len(value)}
    else:
        yield {"pointer": path, "value": value}


def _paged(args, rows):
    return review.page(rows, args.cursor, args.limit, args.max_chars)


def _path_prefixes(values):
    prefixes = []
    for value in values:
        prefix = value.rstrip("/")
        if (not prefix or "\\" in prefix or
                any(part in ("", ".", "..") for part in prefix.split("/"))):
            raise ValueError("path-prefix must be a nonempty Chromium-relative path")
        prefixes.append(prefix)
    return sorted(set(prefixes))


def command(args):
    action = args.review_command
    if action == "init":
        result = review.initialize(args.report, args.directory, args.cache,
                                   args.source_repo, args.refresh)
    elif action == "prepare-trial":
        from .review_trials import prepare
        result = prepare(read_json(args.spec), args.directory, args.cache, args.reference_mode, args.seed)
    elif action in ("run-trial", "collect-trial"):
        from .review_trials import run, finish
        result = (run if action == "run-trial" else finish)(args.directory, read_json(args.runner))
    elif action in ("evaluate", "assessment-template"):
        from .review_eval import evaluate, assessment_template
        trials = [(os.path.realpath(directory), *review.load(directory, verify=False)) for directory in args.trials]
        if action == "assessment-template":
            if os.path.exists(args.output):
                raise ValueError("assessment output already exists; refusing to overwrite reviewer judgments")
            write_json(args.output, assessment_template(read_json(args.gold), trials))
            result = {"output": os.path.abspath(args.output), "status": "unadjudicated_template"}
        else:
            result = evaluate(read_json(args.gold), trials,
                              read_json(args.adjudication) if args.adjudication else None,
                              [read_json(path) for path in args.manifests])
    else:
        index, ledger = review.load(args.directory)
        if action in ("focus", "focus-read"):
            from . import review_focus
            errors = review.verify_sources(index)
            if errors:
                raise ValueError("; ".join(errors))
            if action == "focus":
                if os.path.exists(args.output):
                    raise ValueError("focus output already exists; choose a new path to preserve prior evidence")
                packet = review_focus.build(index, _path_prefixes(args.path_prefix), args.fact_kind, args.hops)
                write_json(args.output, packet)
                result = {"output": os.path.abspath(args.output), **packet["summary"], "limits": packet["limits"]}
            else:
                packet = review_focus.load(index, args.file)
                if args.section == "summary":
                    if args.item:
                        raise ValueError("--item requires a focus data section, not summary")
                    result = {**packet["summary"], "request": packet["request"], "refs": packet["refs"],
                              "limits": packet["limits"]}
                else:
                    rows = packet[args.section]
                    if args.item:
                        rows = [row for row in rows if row.get("id") == args.item or
                                row.get("source") == args.item or row.get("target") == args.item or
                                args.item in row.get("targets", []) or
                                (args.item.startswith("file:") and row.get("path") == args.item[5:])]
                    if args.section in ("findings", "files"):
                        rows = [{**row, "status": ledger["dispositions"].get(row["id"], {}).get("status", "pending")}
                                for row in rows]
                    result = _paged(args, rows)
        elif action == "overview":
            prefixes = _path_prefixes(args.path_prefix)
            result = _paged(args, review.overview_rows(index, ledger, args.group_by,
                                                       args.path_depth, prefixes))
            result.update(index_total=len(index["items"]), group_by=args.group_by,
                          path_prefixes=prefixes,
                          note="Counts from indexed evidence, not semantic review. Path groups may overlap; counts are not events.")
        elif action == "index":
            if args.after and args.cursor:
                raise ValueError("use --after or --cursor, not both")
            prefixes = _path_prefixes(args.path_prefix)
            rows = review.index_rows(index, ledger, args.status, args.query,
                                     item_kind=args.item_kind, fact_kinds=args.fact_kind,
                                     path_prefixes=prefixes)
            if args.after:
                rows = [r for r in rows if r["id"] > args.after]
            result = _paged(args, rows)
            result["next_after"] = result["items"][-1]["id"] if result["next_cursor"] is not None else None
            result["pagination_note"] = "With mutable status filters, continue using --after and cursor 0."
            result["index_total"] = len(index["items"])
            result["filters"] = {"status": args.status, "query": args.query,
                                 "item_kind": args.item_kind, "fact_kinds": args.fact_kind,
                                 "path_prefixes": prefixes}
            result["scope_note"] = "Filters select retrieval only, not scope decisions. Fact-kind filters omit source-only changes."
        elif action == "events":
            rows = [{"id": e["id"], "title": e["title"], "status": e["status"],
                     "member_count": len(e["items"]), "open_questions": len(e["uncertainties"])}
                    for e in sorted(ledger["events"], key=lambda e: (e.get("order", 1000000), e["id"]))]
            result = _paged(args, rows)
        elif action == "inspect":
            if args.uid in index["items"]:
                item = index["items"][args.uid]
            elif args.uid in index["graph"]["nodes"]:
                item = index["graph"]["nodes"][args.uid]
            elif any(e["id"] == args.uid for e in ledger["events"]):
                item = next(e for e in ledger["events"] if e["id"] == args.uid)
            else:
                raise ValueError("unknown item/node id; search review index first")
            result = _paged(args, list(_leaves(item)))
            result["uid"] = args.uid
        elif action == "related":
            result = _paged(args, evidence.related(index["graph"], args.uid, args.hops, args.hub_limit))
        elif action == "unresolved":
            result = _paged(args, index["graph"]["unresolved"])
        elif action == "source":
            source = review.source_rows(index, args.side, args.path, args.start, args.end, args.fetch)
            result = {**source, **_paged(args, source["items"])}
        elif action == "record":
            updated = review.record(index, ledger, read_json(args.file))
            write_json(os.path.join(args.directory, "review.json"), updated)
            result = review.check(index, updated)
        elif action == "check":
            result = review.check(index, ledger)
            result["input_errors"] = review.verify_sources(index)
            if result["input_errors"]:
                result["accounting_complete"] = False
        elif action == "render":
            errors = review.verify_sources(index)
            if errors:
                raise ValueError("; ".join(errors))
            text = review.render(index, ledger, require_complete=args.require_complete)
            path = os.path.join(args.directory, "review.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            result = {"output": os.path.abspath(path), **review.check(index, ledger)}
        else:
            raise ValueError("unknown review command")
        result["fingerprint"] = index["fingerprint"]
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if action == "evaluate" and args.adjudication:
        return 0 if result["release_verdict"] == "pass_for_pinned_case_and_runner_only" else 1
    return 1 if action == "check" and not result["accounting_complete"] else 0


def add_parser(sub, default_cache):
    parser = sub.add_parser("review", help="resumable evidence investigation and event ledger")
    commands = parser.add_subparsers(dest="review_command", required=True)
    p = commands.add_parser("init", help="index findings, unchanged facts and raw source-delta leads")
    p.add_argument("report", help="report.json or its directory")
    p.add_argument("--directory", required=True, help="separate review output directory")
    p.add_argument("--cache", default=default_cache)
    p.add_argument("--source-repo", help="optional local Chromium Git object database for all changed paths")
    p.add_argument("--refresh", action="store_true", help="re-index; archive decisions if evidence changed")
    p.set_defaults(func=command)
    p = commands.add_parser("prepare-trial", help="stage source-pinned inputs without gold or prior answers")
    p.add_argument("spec", help="case specification JSON (source files and exact refs)")
    p.add_argument("--directory", required=True)
    p.add_argument("--cache", default=default_cache)
    p.add_argument("--reference-mode", choices=("full", "core"), default="full")
    p.add_argument("--seed", type=int, default=0, help="nonzero: deterministic rank/bucket/order perturbation")
    p.set_defaults(func=command)
    for name in ("run-trial", "collect-trial"):
        p = commands.add_parser(name)
        p.add_argument("directory")
        p.add_argument("--runner", required=True, help="runner identity/config JSON; no credentials in this file")
        p.set_defaults(func=command)
    p = commands.add_parser("evaluate", help="score event coverage and optionally gate independent semantic assessments")
    p.add_argument("gold", help="independently authored gold JSON; do not expose it to the tested agent")
    p.add_argument("trials", nargs="+", help="one or more saved review directories")
    p.add_argument("--adjudication", help="independent semantic assessments pinned to gold and each saved ledger")
    p.add_argument("--manifests", nargs="*", default=[], help="collected trial.json execution manifests")
    p.set_defaults(func=command)
    p = commands.add_parser("assessment-template", help="create an unresolved independent adjudication form")
    p.add_argument("gold")
    p.add_argument("trials", nargs="+")
    p.add_argument("--output", required=True, help="new JSON file, kept outside all tested workspaces")
    p.set_defaults(func=command)
    for name in ("focus", "focus-read", "overview", "index", "events", "inspect", "related", "unresolved", "source", "record", "check", "render"):
        p = commands.add_parser(name)
        p.add_argument("directory", help="directory created by review init")
        p.set_defaults(func=command)
        if name in ("focus-read", "overview", "index", "events", "inspect", "related", "unresolved", "source"):
            p.add_argument("--cursor", type=int, default=0)
            p.add_argument("--limit", type=int, default=30)
            p.add_argument("--max-chars", type=int, default=24000,
                           help="JSON payload character budget, not model tokens (2000..100000)")
        if name in ("focus", "overview", "index"):
            p.add_argument("--path-prefix", action="append", default=[],
                           help="exact relative file/directory prefix; repeat for OR, not a complete feature boundary")
        if name == "focus":
            p.add_argument("--fact-kind", action="append", default=[], help="requested kinds; supporting kinds remain visible")
            p.add_argument("--hops", type=int, default=3, help="declared dependency depth after source matching (0..8)")
            p.add_argument("--output", required=True, help="new focus JSON packet; does not change review decisions")
        if name == "focus-read":
            p.add_argument("--file", required=True, help="focus JSON created for this review")
            p.add_argument("--item", help="exact item/reference id, or file:path for source locations")
            p.add_argument("--section", default="summary",
                           choices=("summary", "findings", "files", "references", "unresolved", "sources"))
        if name == "overview":
            p.add_argument("--group-by", choices=("fact-kind", "path"), default="fact-kind")
            p.add_argument("--path-depth", type=int, default=3, help="path components per group (1..12)")
        if name == "index":
            p.add_argument("--status", choices=("pending", "event", "explained", "unresolved", "out_of_scope"))
            p.add_argument("--query", default="", help="case-insensitive identifier/name/path search")
            p.add_argument("--after", default="", help="stable last id; safe even after recording dispositions")
            p.add_argument("--item-kind", choices=("finding", "source_delta", "milestone_lead"))
            p.add_argument("--fact-kind", action="append", default=[],
                           help="exact declaration kind from overview; repeat for OR; excludes non-finding items")
        if name in ("inspect", "related"):
            p.add_argument("uid")
        if name == "related":
            p.add_argument("--hops", type=int, default=2)
            p.add_argument("--hub-limit", type=int, default=40)
        if name == "source":
            p.add_argument("path", help="exact Chromium-relative path")
            p.add_argument("--side", choices=("from", "to", "diff"), default="diff")
            p.add_argument("--start", type=int, default=1)
            p.add_argument("--end", type=int, default=120)
            p.add_argument("--fetch", action="store_true", help="fetch missing exact-ref source from Gitiles")
        if name == "record":
            p.add_argument("--file", required=True, help="JSON patch of events/dispositions")
        if name == "render":
            p.add_argument("--require-complete", action="store_true",
                           help="refuse to write while items or events remain unfinished; not semantic approval")
