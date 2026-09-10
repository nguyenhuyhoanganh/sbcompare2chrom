"""Resumable, evidence-backed human/agent review. No model dependency.

The immutable index is a bounded-query input; review.json is the reader's
event ledger. Accounting completeness and semantic correctness are different:
validation can prove the former, never the latter.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote, urlparse

from . import __version__
from .acquire import GitilesSource
from .evidence import build_graph, digest
from .model import SCHEMA_VERSION, Snapshot, read_json, read_report, write_json
from .snapshot import snapshot_path, tree_path
from .targets import READABLE_SUFFIXES

# 2: the recorded item selection is `selection`, not `scope`. A ledger written
# under 1 must fail loudly here rather than be read as having no selection,
# which would turn a recorded COMPLETE selection into a silent absence.
REVIEW_SCHEMA = 2
EVENT_FIELDS = ("title", "before", "after", "mechanism", "impact", "conditions", "action")


def report_digest(report, include_enrichment=True) -> str:
    """Evidence identity independent of ranking, row order and derived clusters."""
    rows = []
    for f in sorted(report.findings, key=lambda f: f.uid):
        c = f.change.to_dict()
        c.pop("severity", None)
        rows.append({"change": c, "unconfirmed": f.unconfirmed,
                     "enrichment": {k: v for k, v in f.enrichment.items() if k != "cluster"}
                     if include_enrichment else {}})
    return digest({"from": report.from_ref, "to": report.to_ref, "findings": rows,
                   "meta": {k: v for k, v in report.meta.items()
                            if k not in ("generated", "tool_version")},
                   "milestone_brief": report.summary.get("milestone_brief", []) if include_enrichment else []})


def safe_path(root: str, relative: str) -> Path:
    if not relative or relative.startswith(("/", "\\")) or "\\" in relative:
        raise ValueError("source path must be relative to the Chromium tree")
    if any(p in ("", ".", "..") for p in relative.split("/")):
        raise ValueError("source path must not contain empty, '.' or '..' segments")
    base = Path(root).resolve()
    path = (base / relative).resolve()
    if base not in path.parents:
        raise ValueError("source path escapes its tree (possibly via a symlink)")
    return path


def _git(repo, *args) -> bytes:
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def _file_hash(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def implementation_identity(root=None) -> dict:
    root = Path(root) if root is not None else Path(__file__).resolve().parent.parent
    tool_files = {str(p.relative_to(root)): _file_hash(p)
                  for p in sorted((root / "chromiumdiff").rglob("*.py"))}
    skill_files = {str(p.relative_to(root)): _file_hash(p)
                   for p in sorted((root / "skills").rglob("*"))
                   if p.is_file() and p.suffix in (".md", ".py")}
    return {"tool_sha256": digest(tool_files), "skill_sha256": digest(skill_files)}


def source_inventory(roots: dict, repo=None, refs=None) -> tuple:
    """Raw file-delta leads, independent of extractor filenames or grammar.

    Cached presence is not an upstream addition/deletion. A supplied Git
    repository establishes those with exact commit objects, without checkout.
    """
    if repo:
        commits = {side: _git(repo, "rev-parse", "--verify", "--end-of-options",
                             ref + "^{commit}").decode().strip()
                   for side, ref in refs.items()}
        raw = _git(repo, "diff", "--raw", "--no-abbrev", "--no-renames",
                   "--no-ext-diff", "--no-textconv", "-z",
                   commits["from"], commits["to"], "--").split(b"\0")
        rows = []
        for i in range(0, len(raw) - 1, 2):
            mode_old, mode_new, old, new, status = raw[i].decode().split()
            path = os.fsdecode(raw[i + 1])
            rows.append(dict(id="file:" + path, kind="source_delta", path=path,
                             state=status, hashes={"from": old, "to": new},
                             modes={"from": mode_old.lstrip(":"), "to": mode_new}))
        return sorted(rows, key=lambda x: x["id"]), {
            "mode": "git", "repository": os.path.abspath(repo), "commits": commits,
            "limit": "All changed paths at these commits; file review is not semantic proof."}

    files = {}
    for side, root in roots.items():
        table = files[side] = {}
        if not os.path.isdir(root):
            continue
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in (".chromiumdiff", ".git") and
                             not os.path.islink(os.path.join(directory, d)))
            for name in sorted(names):
                path = Path(directory) / name
                if path.is_symlink() or not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                table[relative] = _file_hash(path)
    rows = []
    for path in sorted(set(files["from"]) | set(files["to"])):
        old, new = files["from"].get(path), files["to"].get(path)
        if old == new:
            continue
        rows.append(dict(id="file:" + path, kind="source_delta", path=path,
                         state="modified" if old and new else "one_side_cached",
                         hashes={"from": old, "to": new}))
    return rows, {"mode": "cached", "files_per_side": {s: len(v) for s, v in files.items()},
                  "inventory_sha256": digest(files),
                  "limit": "Only cached files, possibly beyond the original scan. A missing side "
                           "is unknown, not an upstream addition/removal. Uncached code and symlinks "
                           "are unexamined; .git and acquisition markers are excluded."}


def initialize(report_path: str, directory: str, cache: str, source_repo=None,
               refresh=False) -> dict:
    report_path = os.path.abspath(report_path)
    if os.path.isdir(report_path):
        report_path = os.path.join(report_path, "report.json")
    directory = os.path.abspath(directory)
    ledger_path = os.path.join(directory, "review.json")
    index_path = os.path.join(directory, "review-index.json")
    if (os.path.exists(ledger_path) or os.path.exists(index_path)) and not refresh:
        raise ValueError("review exists; resume it, or use init --refresh to re-index with invalidation")
    previous = read_json(ledger_path) if os.path.exists(ledger_path) else None
    previous_index = read_json(index_path) if os.path.exists(index_path) else None
    report = read_report(report_path)
    refs = {"from": report.from_ref, "to": report.to_ref}
    cache = os.path.abspath(cache)
    roots = {s: os.path.abspath(tree_path(cache, r)) for s, r in refs.items()}
    snapshots, snapshot_inputs, warnings = {}, {}, []
    for side, ref in refs.items():
        path = snapshot_path(cache, ref, report.meta.get("target_set", "analysis"),
                             report.meta.get("partitions"), report.meta.get("complete", False))
        if not os.path.isfile(path):
            snapshots[side] = None
            warnings.append(f"{side}: no matching snapshot; unchanged bridges unavailable: {path}")
            continue
        data = read_json(path)
        if data.get("schema") != SCHEMA_VERSION or data.get("ref") != ref:
            raise ValueError(f"incompatible snapshot: {path}; rebuild the report and snapshots")
        for field in ("target_set", "partitions", "complete", "platform"):
            expected = report.meta.get(field)
            if expected is not None and data.get("meta", {}).get(field) != expected:
                raise ValueError(f"snapshot {field} differs from report: {path}")
        snapshots[side] = Snapshot.from_dict(data)
        snapshot_inputs[side] = {"path": os.path.abspath(path), "sha256": _file_hash(path)}
    graph = build_graph(report, snapshots["from"], snapshots["to"])
    file_rows, source_scope = source_inventory(roots, source_repo, refs)
    items = {}
    for f in sorted(report.findings, key=lambda f: f.uid):
        items[f.uid] = {"id": f.uid, "kind": "finding", "name": f.change.name,
                        "paths": f.change.paths, "data": f.to_dict()}
    for row in file_rows:
        row["findings"] = sorted(f.uid for f in report.findings if row["path"] in f.change.paths)
        items[row["id"]] = row
    # Chromium's milestone summaries are independent leads, not proof of a
    # rollout on this platform/tag and not restricted to already-matched rows.
    for brief in report.summary.get("milestone_brief", []):
        uid = "brief:" + digest(brief)[:20]
        items[uid] = {"id": uid, "kind": "milestone_lead", "data": brief}
    inputs = {"report": report_path, "report_digest": report_digest(report),
              "baseline_digest": report_digest(report, include_enrichment=False),
              "refs": refs, "snapshots": snapshot_inputs, "source_roots": roots,
              "cache": cache, "source_scope": source_scope, "tool_version": __version__,
              "implementation": implementation_identity(),
              "coverage": report.meta.get("coverage", {}), "platform": report.meta.get("platform"),
              "target_set": report.meta.get("target_set"), "partitions": report.meta.get("partitions", []),
              "unconfirmed": sum(f.unconfirmed for f in report.findings)}
    # Moving a frozen trial to a different directory must not change its
    # evidence identity. Paths stay in inputs for retrieval, not identity.
    stamp = digest({"report": inputs["report_digest"],
                    "snapshots": {s: v["sha256"] for s, v in snapshot_inputs.items()},
                    "files": file_rows,
                    "source_scope": {k: v for k, v in source_scope.items()
                                     if k not in ("repository", "limit")}})
    index = {"schema": REVIEW_SCHEMA, "fingerprint": stamp, "inputs": inputs,
             "warnings": warnings, "items": items, "graph": graph}
    ledger = {"schema": REVIEW_SCHEMA, "fingerprint": stamp, "events": [],
              "dispositions": {}, "history": []}
    if previous:
        if previous.get("fingerprint") == stamp:
            ledger = previous
        else:
            # Do not silently carry conclusions onto changed evidence. Retain
            # the entire old review as history, including unresolved questions.
            ledger["history"] = previous.get("history", []) + [{
                "fingerprint": previous.get("fingerprint"),
                "events": previous.get("events", []),
                "dispositions": previous.get("dispositions", {}),
                "selection": previous.get("selection"),
                "selection_history": previous.get("selection_history", []),
                "reason": "Evidence changed; revalidate before re-recording decisions."}]
            if previous_index and _same_baseline(previous_index, index):
                ledger = _refresh_context(previous_index, index, previous, ledger)
                warnings.append("Context changed: affected decisions need revalidation; unrelated work retained. "
                                "Previous decisions are archived in review.json history.")
                # A refresh can retire an item the selection named, and a
                # selection that silently vanished reads as one never recorded.
                if previous.get("selection") and not ledger.get("selection"):
                    warnings.append("Item selection cleared: the refreshed index no longer holds every selected "
                                    "item. Record a new selection before claiming selection completion.")
            else:
                warnings.append("Baseline evidence changed: prior decisions archived in review.json history; all items pending.")
    write_json(index_path, index)
    write_json(ledger_path, ledger)
    return {"directory": directory, "fingerprint": stamp, "items": len(items),
            "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
            "source_scope": source_scope, "warnings": warnings}


def _same_baseline(old: dict, new: dict) -> bool:
    a, b = old["inputs"], new["inputs"]
    return (a.get("baseline_digest") == b["baseline_digest"] and
            {s: v["sha256"] for s, v in a["snapshots"].items()} ==
            {s: v["sha256"] for s, v in b["snapshots"].items()} and
            a["source_scope"] == b["source_scope"])


def _refresh_context(old: dict, new: dict, previous: dict, fresh: dict) -> dict:
    """New CL/context invalidates nearby decisions, not the whole investigation.

    Changes to actual snapshots/source/scope still reset the baseline. A new
    relation can connect an already-reviewed item to newly enriched evidence;
    inspect both old and new adjacency, including unchanged bridges.
    """
    def content(item):
        value = copy.deepcopy(item)
        data = value.get("data") or {}
        if value.get("kind") == "finding":
            for key in ("score", "bucket", "reasons"):
                data.pop(key, None)
            data.get("enrichment", {}).pop("cluster", None)
        return value
    changed = {uid for uid in set(old["items"]) | set(new["items"])
               if content(old["items"].get(uid, {})) != content(new["items"].get(uid, {}))}
    affected = set(changed)
    adjacency = {}
    for graph in (old["graph"], new["graph"]):
        for edge in graph["edges"]:
            adjacency.setdefault(edge["source"], set()).add(edge["target"])
            adjacency.setdefault(edge["target"], set()).add(edge["source"])
    frontier = set(changed)
    while frontier:
        frontier = {n for uid in frontier for n in adjacency.get(uid, ())} - affected
        affected.update(frontier)
    for uid, item in new["items"].items():
        if set(item.get("findings", [])) & affected:
            affected.add(uid)
    fresh["events"] = copy.deepcopy(previous["events"])
    fresh["selection_history"] = copy.deepcopy(previous.get("selection_history", []))
    if previous.get("selection"):
        selection = copy.deepcopy(previous["selection"])
        if set(selection["items"]) <= set(new["items"]):
            selection["fingerprint"] = new["fingerprint"]
            fresh["selection"] = selection
    fresh["dispositions"] = {uid: copy.deepcopy(d) for uid, d in previous["dispositions"].items()
                             if uid in new["items"]}
    retained = []
    for event in fresh["events"]:
        if not set(event["items"]) <= set(new["items"]):
            for uid in event["items"]:
                fresh["dispositions"].pop(uid, None)
            continue
        dependencies = set(event["items"]) | {e.get(key) for e in event["evidence"]
                                               for key in ("item", "node") if e.get(key)}
        if dependencies & affected:
            event["status"] = "provisional"
            event["uncertainties"] = list(event["uncertainties"]) + [
                "New contextual evidence or relationship: revalidate event boundaries and conclusions."]
        retained.append(event)
    fresh["events"] = retained
    for uid in affected:
        entry = fresh["dispositions"].get(uid)
        if entry and entry["status"] != "event":
            fresh["dispositions"][uid] = {"status": "unresolved", "reason":
                "New contextual evidence: recheck this decision. Previously: " + entry.get("reason", "")}
    return fresh


def load(directory: str, verify=True) -> tuple:
    index = read_json(os.path.join(directory, "review-index.json"))
    ledger = read_json(os.path.join(directory, "review.json"))
    found = {index.get("schema"), ledger.get("schema")}
    if found != {REVIEW_SCHEMA}:
        # Both numbers, because "unsupported" without them leaves the reader to
        # guess whether the review directory or the build is the old one.
        raise ValueError(f"review schema {sorted(map(str, found))} in {directory}; "
                         f"this build reads {REVIEW_SCHEMA}. Run review init again.")
    if index["fingerprint"] != ledger.get("fingerprint"):
        raise ValueError("review/index fingerprints differ; do not combine different runs")
    if verify and report_digest(read_report(index["inputs"]["report"])) != index["inputs"]["report_digest"]:
        raise ValueError("report evidence changed; run review init --refresh before continuing")
    return index, ledger


def page(rows: list, cursor=0, limit=30, max_chars=24000) -> dict:
    if not 1 <= limit <= 200 or not 2000 <= max_chars <= 100000 or cursor < 0 or cursor > len(rows):
        raise ValueError("limit must be 1..200, max-chars 2000..100000, cursor 0..total")
    out, size, pos = [], 0, cursor
    for row in rows[cursor:cursor + limit]:
        length = len(json.dumps(row, ensure_ascii=False))
        if size + length > max_chars - 500:
            if not out:
                raise ValueError(f"item at cursor {pos} needs {length + 500} chars; "
                                 "increase --max-chars or inspect its source in smaller slices")
            break
        out.append(row)
        size += length
        pos += 1
    return {"items": out, "total": len(rows), "cursor": cursor,
            "next_cursor": pos if pos < len(rows) else None}


def _matches_paths(paths, prefixes) -> bool:
    return not prefixes or any(path == prefix or path.startswith(prefix + "/")
                               for path in paths for prefix in prefixes)


def item_paths(item: dict) -> list:
    return item.get("paths", []) if item["kind"] == "finding" else [item.get("path", "")]


def _passes_kind_filters(item: dict, item_kind, fact_kinds) -> bool:
    """Every filter except the path one, asked in one place.

    `path_filter_omission` has to apply the same kind filters `index_rows`
    applies, or it reports milestone leads as withheld by a path prefix in a
    query that excluded them by kind. Two copies of the rule is how they differ.
    """
    if item_kind and item["kind"] != item_kind:
        return False
    if fact_kinds and (item["kind"] != "finding" or
                       item["data"]["change"]["kind"] not in fact_kinds):
        return False
    return True


def path_filter_omission(index: dict, prefixes, item_kind=None, fact_kinds=()) -> dict:
    """What a path prefix removes for carrying no path at all, counted.

    A milestone lead has no path, so no prefix can ever match one: a
    path-filtered sweep that reads every row it returns still never sees them,
    and nothing said so. Kind filters announce their own omission in the note;
    this one could only be found by adding the kinds up by hand.
    """
    if not prefixes:
        return {}
    kinds = {}
    for item in index["items"].values():
        if _passes_kind_filters(item, item_kind, fact_kinds) and not any(item_paths(item)):
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    if not kinds:
        return {}
    return {"excluded_without_path": sum(kinds.values()), "by_kind": kinds,
            "reason": "A path prefix matches paths; an item with none cannot match any prefix. "
                      "Query these kinds without --path-prefix."}


def index_rows(index: dict, ledger: dict, status=None, query="", *,
               item_kind=None, fact_kinds=(), path_prefixes=()) -> list:
    rows = []
    for uid, item in sorted(index["items"].items()):
        state = ledger["dispositions"].get(uid, {}).get("status", "pending")
        if status and state != status:
            continue
        if not _passes_kind_filters(item, item_kind, fact_kinds):
            continue
        if not _matches_paths(item_paths(item), path_prefixes):
            continue
        text = " ".join((uid, item.get("name", ""), " ".join(item.get("paths", [])),
                         json.dumps(item.get("data", {}).get("name", ""))))
        if query.casefold() not in text.casefold():
            continue
        row = {k: v for k, v in item.items() if k != "data"}
        row["status"] = state
        if item["kind"] == "finding":
            c = item["data"]["change"]
            row.update(fact_kind=c["kind"], direction=c["change_type"],
                       changed_attributes=sorted(c["deltas"]), unconfirmed=item["data"]["unconfirmed"])
        elif item["kind"] == "milestone_lead":
            row["summary"] = {k: v for k, v in item["data"].items()
                              if k in ("id", "name", "milestone", "summary", "url")}
        rows.append(row)
    return rows


def overview_rows(index: dict, ledger: dict, group_by="fact-kind", path_depth=3,
                  path_prefixes=()) -> list:
    """Aggregate the complete index without emitting findings or source bodies.

    Path groups are retrieval hints, not feature boundaries. An item with
    several paths can occur in several groups; counts are not event counts.
    """
    if group_by not in ("fact-kind", "path") or not 1 <= path_depth <= 12:
        raise ValueError("group-by must be fact-kind or path; path-depth must be 1..12")
    groups = {}
    for uid, item in sorted(index["items"].items()):
        paths = item_paths(item)
        if not _matches_paths(paths, path_prefixes):
            continue
        if group_by == "fact-kind":
            keys = {item["data"]["change"]["kind"] if item["kind"] == "finding" else item["kind"]}
        else:
            keys = {"/".join(path.split("/")[:path_depth]) for path in paths if path} or {"(no path)"}
        status = ledger["dispositions"].get(uid, {}).get("status", "pending")
        for key in keys:
            group = groups.setdefault(key, {"group": key, "total": 0, "item_kinds": {}, "counts": {}})
            group["total"] += 1
            group["item_kinds"][item["kind"]] = group["item_kinds"].get(item["kind"], 0) + 1
            group["counts"][status] = group["counts"].get(status, 0) + 1
    return [groups[key] for key in sorted(groups)]


def source_bytes(index: dict, side: str, path: str, fetch=False):
    inputs = index["inputs"]
    local = safe_path(inputs["source_roots"][side], path)
    scope = inputs["source_scope"]
    if scope["mode"] == "git":
        commit = scope["commits"][side]
        entry = _git(scope["repository"], "ls-tree", "-z", commit, "--", path)
        if not entry:
            return None, "git_absent"
        # Do not dereference symlinks/submodules as ordinary implementation.
        mode = entry.split(b" ", 1)[0]
        if mode not in (b"100644", b"100755"):
            raise ValueError("source is a symlink or submodule; inspect its Git metadata")
        return _git(scope["repository"], "show", f"{commit}:{path}"), "git"
    if local.is_file():
        return local.read_bytes(), "cache"
    supplement = safe_path(tree_path(os.path.join(inputs["cache"], "review-sources"),
                                     inputs["refs"][side]), path)
    if supplement.is_file():
        return supplement.read_bytes(), "supplemental_cache"
    if fetch:
        data = GitilesSource(inputs["refs"][side], inputs["cache"]).fetch_file(quote(path, safe="/"))
        if data is None:
            return None, "upstream_404"
        # Separate from the baseline inventory: fetching a contextual file
        # must not invalidate every recorded event or inflate scan coverage.
        supplement.parent.mkdir(parents=True, exist_ok=True)
        supplement.write_bytes(data)
        return data, "fetched_supplement"
    return None, "not_cached"


def source_rows(index: dict, side: str, path: str, start=1, end=120, fetch=False) -> dict:
    if start < 1 or end < start or end - start > 2000:
        raise ValueError("source range must start at >=1 and span at most 2001 lines")
    sides = ("from", "to") if side == "diff" else (side,)
    contents, provenance = {}, {}
    for s in sides:
        data, origin = source_bytes(index, s, path, fetch)
        if data is not None and (len(data) > 20 * 1024 * 1024 or b"\0" in data):
            raise ValueError("binary or >20 MB source; inspect with local source tools")
        provenance[s] = {"ref": index["inputs"]["refs"][s], "path": path,
                         "origin": origin,
                         "sha256": hashlib.sha256(data).hexdigest() if data is not None else None}
        if data is None and origin == "not_cached":
            return {"provenance": provenance, "items": [],
                    "warning": "Not cached does not mean absent; retry --fetch or supply a Git source repository."}
        contents[s] = (data or b"").decode("utf-8", errors="replace").splitlines()
    if side == "diff":
        lines = list(difflib.unified_diff(contents["from"], contents["to"],
                                        fromfile="from/" + path, tofile="to/" + path, lineterm=""))
    else:
        lines = contents[side]
    rows = []
    for num, line in enumerate(lines[start - 1:end], start):
        # Minified files remain pageable without truncating an individual line.
        for offset in range(0, max(1, len(line)), 1000):
            rows.append({"line": num, "column": offset + 1, "text": line[offset:offset + 1000]})
    return {"provenance": provenance, "items": rows, "total_lines": len(lines),
            "next_line": end + 1 if end < len(lines) else None,
            "line_numbers": "unified diff output" if side == "diff" else "source"}


def validate_selection(index: dict, selection) -> list:
    """The recorded item selection: which indexed items the user's request covers.

    A separate word from `source_scope` (which files were read) and from the
    `out_of_scope` disposition (excluded by the request), because a reader who
    meets one `scope` in three meanings cannot tell which one a gate measures.
    """
    if selection is None:
        return []
    if not isinstance(selection, dict) or set(selection) != {"description", "items", "fingerprint"}:
        return ["selection requires description, items and fingerprint"]
    errors = []
    if not isinstance(selection["description"], str) or not selection["description"].strip():
        errors.append("selection description must record the user's requested boundary")
    if selection["fingerprint"] != index["fingerprint"]:
        errors.append("selection fingerprint differs from the current evidence")
    ids = selection["items"]
    if (not isinstance(ids, list) or not ids or any(not isinstance(uid, str) for uid in ids)
            or len(ids) != len(set(ids))):
        errors.append("selection items must be a nonempty list of unique item IDs")
    elif not set(ids) <= set(index["items"]):
        errors.append("selection contains unknown item IDs")
    return errors


def validate(index: dict, ledger: dict) -> list:
    errors, members = validate_selection(index, ledger.get("selection")), {}
    event_ids = set()
    for event in ledger.get("events", []):
        eid = event.get("id")
        if not isinstance(eid, str) or not eid or eid in event_ids:
            errors.append("missing or duplicate event id")
        event_ids.add(eid)
        if eid in index["items"] or eid in index["graph"]["nodes"]:
            errors.append(f"{eid}: event id collides with an evidence id")
        if "order" in event and (type(event["order"]) is not int or event["order"] < 0):
            errors.append(f"{eid}: optional narrative order must be a nonnegative integer")
        for field in EVENT_FIELDS:
            if not isinstance(event.get(field), str) or not event[field].strip():
                errors.append(f"{eid}: {field} must be a nonempty explanation")
        if event.get("status") not in ("confirmed", "provisional"):
            errors.append(f"{eid}: status must be confirmed or provisional")
        if (not isinstance(event.get("uncertainties"), list) or
                any(not isinstance(q, str) or not q.strip() for q in event.get("uncertainties", []))):
            errors.append(f"{eid}: uncertainties must be a list of nonempty strings (may be empty)")
        ids = event.get("items", [])
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            errors.append(f"{eid}: items must be a nonempty unique list")
        for uid in ids:
            if uid not in index["items"]:
                errors.append(f"{eid}: unknown item {uid}")
            if uid in members:
                errors.append(f"{uid}: primary member of multiple events")
            members[uid] = eid
        citations = event.get("evidence") or []
        supported = set()
        for citation in citations:
            if (not isinstance(citation, dict) or not isinstance(citation.get("supports"), str)
                    or not citation["supports"].strip()):
                errors.append(f"{eid}: evidence needs a supports explanation")
                continue
            uid = citation.get("item")
            url = citation.get("url")
            source = citation.get("source")
            if uid:
                if uid not in index["items"] and uid not in index["graph"]["nodes"]:
                    errors.append(f"{eid}: unknown evidence {uid}")
                supported.add(uid)
            elif url:
                parsed = urlparse(url)
                if parsed.scheme != "https" or not parsed.netloc:
                    errors.append(f"{eid}: evidence URL must be HTTPS")
            elif source:
                try:
                    if source.get("side") not in ("from", "to") or not source.get("sha256"):
                        raise ValueError("source citation requires side and sha256")
                    data, _ = source_bytes(index, source["side"], source["path"])
                    if data is None or hashlib.sha256(data).hexdigest() != source["sha256"]:
                        raise ValueError("source citation is missing or its hash changed")
                    if "start" in source or "end" in source:
                        start, end = source.get("start", 1), source.get("end", source.get("start", 1))
                        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(data.splitlines()):
                            raise ValueError("source citation line range is outside the cited file")
                except (KeyError, OSError, ValueError) as exc:
                    errors.append(f"{eid}: {exc}")
            else:
                errors.append(f"{eid}: evidence needs an item/node id, source or URL")
        for uid in set(ids) - supported:
            errors.append(f"{eid}: no evidence explanation for member {uid}")
    for uid, entry in ledger.get("dispositions", {}).items():
        if uid not in index["items"]:
            errors.append(f"unknown disposition {uid}")
        status = entry.get("status")
        if status == "event":
            if members.get(uid) != entry.get("event"):
                errors.append(f"{uid}: dangling event disposition")
        elif status not in ("explained", "unresolved", "out_of_scope"):
            errors.append(f"{uid}: invalid disposition status")
        elif not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            errors.append(f"{uid}: disposition requires a reason")
        if status != "event" and uid in members:
            errors.append(f"{uid}: event member has non-event disposition")
    for uid, eid in members.items():
        if ledger.get("dispositions", {}).get(uid) != {"status": "event", "event": eid}:
            errors.append(f"{uid}: missing event disposition")
    return errors


def record(index: dict, ledger: dict, patch: dict) -> dict:
    """Atomic upsert. Explicit remove_events supports merges and splits."""
    if not isinstance(patch, dict) or set(patch) - {"events", "dispositions", "remove_events", "selection"}:
        raise ValueError("review patch accepts only events, dispositions, remove_events and selection")
    if any(not isinstance(v, list) for k, v in patch.items() if k != "selection"):
        raise ValueError("event/disposition patch fields must be lists")
    for e in patch.get("events", []):
        if (not isinstance(e, dict) or not isinstance(e.get("items"), list)
                or any(not isinstance(uid, str) for uid in e["items"])):
            raise ValueError("each event requires an items list of string IDs")
        if "id" in e and (not isinstance(e["id"], str) or not e["id"]):
            raise ValueError("event id must be a nonempty string")
    if any(not isinstance(eid, str) for eid in patch.get("remove_events", [])):
        raise ValueError("remove_events must contain string event IDs")
    for d in patch.get("dispositions", []):
        if not isinstance(d, dict) or not isinstance(d.get("id"), str):
            raise ValueError("each disposition requires a string id")
    updated = copy.deepcopy(ledger)
    if "selection" in patch:
        errors = validate_selection(index, patch["selection"])
        if errors:
            raise ValueError("; ".join(errors))
        if updated.get("selection") != patch["selection"]:
            updated.setdefault("selection_history", []).append(copy.deepcopy(updated.get("selection")))
        updated["selection"] = copy.deepcopy(patch["selection"])
    incoming = copy.deepcopy(patch.get("events", []))
    for event in incoming:
        event.setdefault("id", "event:" + digest(sorted(event.get("items", [])))[:20])
    replace = set(patch.get("remove_events", [])) | {e["id"] for e in incoming}
    updated["events"] = [e for e in updated["events"] if e["id"] not in replace] + incoming
    updated["events"].sort(key=lambda e: e["id"])
    updated["dispositions"] = {uid: d for uid, d in updated["dispositions"].items()
                               if d.get("event") not in replace}
    for event in incoming:
        for uid in event.get("items", []):
            updated["dispositions"][uid] = {"status": "event", "event": event["id"]}
    for d in patch.get("dispositions", []):
        updated["dispositions"][d["id"]] = {k: v for k, v in d.items() if k != "id"}
    errors = validate(index, updated)
    if errors:
        raise ValueError("invalid review patch: " + "; ".join(errors[:20]))
    return updated


def selection_check(index: dict, ledger: dict, errors=()) -> dict:
    selection = ledger.get("selection")
    if not selection:
        return {"configured": False, "accounting_complete": False}
    if validate_selection(index, selection):
        return {"configured": True, "accounting_complete": False, "invalid": True}
    selected = set(selection["items"])
    counts, by_kind = {}, {}
    for uid in selected:
        status = ledger["dispositions"].get(uid, {}).get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
        kind = index["items"][uid]["kind"]
        group = by_kind.setdefault(kind, {"total": 0, "counts": {}})
        group["total"] += 1
        group["counts"][status] = group["counts"].get(status, 0) + 1
    events = [e for e in ledger["events"] if selected & set(e["items"])]
    provisional = sum(e.get("status") != "confirmed" for e in events)
    return {"configured": True, "description": selection["description"],
            "total": len(selected), "outside_selection": len(index["items"]) - len(selected),
            "counts": counts, "by_kind": by_kind, "events": len(events),
            "provisional_events": provisional,
            "accounting_complete": not errors and not counts.get("pending") and
                not counts.get("unresolved") and not provisional,
            "limit": "Only the explicitly selected items are counted. Selection and semantic completeness require review."}


def check(index: dict, ledger: dict) -> dict:
    errors = validate(index, ledger)
    counts, by_kind = {}, {}
    for uid, item in sorted(index["items"].items()):
        status = ledger["dispositions"].get(uid, {}).get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
        group = by_kind.setdefault(item["kind"], {"total": 0, "counts": {}})
        group["total"] += 1
        group["counts"][status] = group["counts"].get(status, 0) + 1
    provisional = sum(e.get("status") != "confirmed" for e in ledger["events"])
    return {"total": len(index["items"]), "counts": counts, "events": len(ledger["events"]),
            "by_kind": by_kind,
            "provisional_events": provisional, "errors": errors,
            "selection": selection_check(index, ledger, errors),
            "unresolved_reference_count": len(index["graph"]["unresolved"]),
            "accounting_complete": not errors and not counts.get("pending") and
                not counts.get("unresolved") and not provisional,
            "semantic_completeness": "not measured by this validator; requires independent review/evaluation",
            "source_scope": index["inputs"]["source_scope"], "warnings": index["warnings"]}


def verify_sources(index: dict) -> list:
    """Check pinned local inputs at the completion boundary, not every page."""
    errors = []
    try:
        if report_digest(read_report(index["inputs"]["report"])) != index["inputs"]["report_digest"]:
            errors.append("Report evidence changed; run review init --refresh")
    except (OSError, ValueError) as exc:
        errors.append("Report evidence unavailable: " + str(exc))
    for side, value in index["inputs"]["snapshots"].items():
        if not os.path.isfile(value["path"]) or _file_hash(value["path"]) != value["sha256"]:
            errors.append(f"{side} snapshot changed; run review init --refresh")
    scope = index["inputs"]["source_scope"]
    if scope["mode"] == "cached":
        rows, current_scope = source_inventory(index["inputs"]["source_roots"])
        expected = [{k: v for k, v in item.items() if k != "findings"}
                    for _, item in sorted(index["items"].items()) if item["kind"] == "source_delta"]
        if rows != expected or current_scope["inventory_sha256"] != scope.get("inventory_sha256"):
            errors.append("Cached source inventory changed; run review init --refresh and revalidate decisions")
    return errors


def coverage_section(index: dict, state: dict) -> list:
    """State what the comparison read, and what it left open, before the events.

    A reader who does not know which files the extractor parses cannot tell a
    removed declaration from an unparsed file. Every figure comes from the run.
    """
    inputs = index["inputs"]
    lines = ["## Coverage and limits", "",
             "This comparison reads declarations the extractor parses. It does not "
             "compare behaviour, and a file with no declaration parser is absent from "
             "the findings whether or not it changed.", "",
             "Parsed file suffixes: " + ", ".join(READABLE_SUFFIXES) + ".", ""]
    for side in sorted(inputs.get("coverage", {})):
        value = inputs["coverage"][side]
        if isinstance(value, dict) and "candidates" in value:
            lines.append(f"- {side}: {value['read']} of {value['candidates']} candidate "
                         f"declarations read; {value['missed']} missed.")
    missed = inputs.get("coverage", {}).get("to", {}).get("missed_by_directory") or {}
    if missed:
        top = sorted(missed.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        lines.append("- Candidates missed by directory (to side): " +
                     "; ".join(f"{name} {count}" for name, count in top) +
                     (f"; and {len(missed) - len(top)} more directories" if len(missed) > len(top) else ""))
    lines += [f"- Acquisition: target set {inputs.get('target_set')}; "
              f"partitions {', '.join(inputs.get('partitions') or []) or 'none'}; "
              f"unconfirmed findings: {inputs['unconfirmed']}.",
              f"- Unresolved declaration references: {state['unresolved_reference_count']}.",
              f"- Source scope: {inputs['source_scope']['limit']}",
              "- Finch, external configuration, product patches and rendered UI require "
              "separate evidence."]
    lines += ["- " + warning for warning in index["warnings"]]
    return lines + ["",
                    "These limits bound what the comparison could observe. They are the "
                    "places a reviewer must check by hand.", ""]


def render(index: dict, ledger: dict, require_complete=False, require_selection_complete=False) -> str:
    state = check(index, ledger)
    if state["errors"]:
        raise ValueError("cannot render invalid ledger: " + "; ".join(state["errors"][:20]))
    if require_complete and not state["accounting_complete"]:
        raise ValueError(
            "review is incomplete: "
            f"{state['counts'].get('pending', 0)} pending items, "
            f"{state['counts'].get('unresolved', 0)} unresolved items, "
            f"{state['provisional_events']} provisional events. "
            "Resume the saved review; omit --require-complete only to render a PARTIAL report.")
    if require_selection_complete and not state["selection"]["accounting_complete"]:
        raise ValueError("item selection is unconfigured or incomplete; record its items and resolve its remaining work")
    inputs = index["inputs"]
    out = ["# Chromium upgrade review", "",
           f"{inputs['refs']['from']} → {inputs['refs']['to']} · {inputs['platform']}", "",
           "Status: " + ("all indexed items accounted for" if state["accounting_complete"] else "PARTIAL"),
           "", f"Indexed items: {state['total']}; events: {state['events']}; "
           f"provisional events: {state['provisional_events']}.",
           "", "Disposition counts: " + json.dumps(state["counts"], sort_keys=True),
           "", "Accounting does not establish semantic completeness or product safety.", ""]
    chosen = state["selection"]
    if chosen["configured"]:
        out.extend(["## Recorded item selection", "", chosen["description"], "",
                    "Selection accounting: " + ("COMPLETE" if chosen["accounting_complete"] else "PARTIAL"),
                    f"Selected items: {chosen['total']}; outside the selection: {chosen['outside_selection']}.",
                    "Disposition counts: " + json.dumps(chosen["counts"], sort_keys=True),
                    "", chosen["limit"], ""])
    out.extend(coverage_section(index, state))
    ordered = sorted(ledger["events"], key=lambda e: (e.get("order", 1000000), e["id"]))
    for i, event in enumerate(ordered, 1):
        out.extend([f"## {i}. {event['title']}", "", f"Status: {event['status']}", ""])
        for key in EVENT_FIELDS[1:]:
            out.extend([f"{key.capitalize()}: {event[key]}", ""])
        if event["uncertainties"]:
            out.extend(["Uncertainties: " + "; ".join(event["uncertainties"]), ""])
        for e in event["evidence"]:
            ref = citation_text(index, e)
            out.append(f"- {ref}: {e['supports']}")
        out.append("")
    return "\n".join(out) + "\n"


def citation_text(index: dict, citation: dict) -> str:
    """Make source evidence navigable without inventing side-qualified lines."""
    def link(side, path, line=None):
        ref = index["inputs"]["refs"][side]
        url = "https://chromium.googlesource.com/chromium/src/+/" + quote(ref, safe="/")
        url += "/" + quote(path, safe="/")
        if line:
            url += "#" + str(line)
        label = f"{side}: {path}" + (f":{line}" if line else "")
        label = label.replace("[", "\\[").replace("]", "\\]")
        return f"[{label}]({url})"
    if citation.get("source"):
        source = citation["source"]
        return link(source["side"], source["path"], source.get("start"))
    if citation.get("url"):
        return "[External evidence](" + citation["url"].replace(")", "%29") + ")"
    uid = citation["item"]
    node = index["graph"]["nodes"].get(uid, {})
    links = [link(side, fact["path"], fact.get("line"))
             for side, fact in sorted(node.get("sides", {}).items()) if fact.get("path")]
    if not links and uid.startswith("file:"):
        item = index["items"][uid]
        links = [link(side, item["path"]) for side, value in item["hashes"].items()
                 if value and set(value) != {"0"}]
    return "`" + uid.replace("`", "") + "`" + (" · " + ", ".join(links) if links else "")
