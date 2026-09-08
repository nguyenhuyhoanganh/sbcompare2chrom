"""Source-backed retrieval for a user-selected area, not semantic event discovery.

No feature names or scores select evidence. Unchanged files/facts can reference
changed dependencies. Lexical matches are leads, never proof of execution.
"""

from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import posixpath
import re

from . import review
from .evidence import digest
from .model import read_json

SCHEMA = 1
IDENTIFIER = re.compile(r"\b[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*\b")
MOJO_IMPORT = re.compile(r'''["']([^"'\n]+?\.mojom)(?:-webui\.js|-lite\.js|(?:-shared|-forward)?\.h)?["']''')
FEATURE_CALL = re.compile(r"\bFeatureList::IsEnabled\s*\(\s*([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)")


def _paths(node):
    return {f["path"] for f in node.get("sides", {}).values() if f.get("path")}


def _seed_paths(index, prefixes):
    scope = index["inputs"]["source_scope"]
    paths = set()
    if scope["mode"] == "git":
        for commit in scope["commits"].values():
            raw = review._git(scope["repository"], "ls-tree", "-r", "--name-only", "-z", commit)
            paths.update(p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p)
    else:
        for root in index["inputs"]["source_roots"].values():
            base = Path(root).resolve()
            for prefix in prefixes:
                location = review.safe_path(root, prefix)
                candidates = [location] if location.is_file() else location.rglob("*")
                for path in candidates:
                    if path.is_file() and not path.is_symlink():
                        relative = str(path.relative_to(base))
                        if not any(part in (".git", ".chromiumdiff") for part in path.relative_to(base).parts):
                            paths.add(relative)
    return sorted(p for p in paths if review._matches_paths([p], prefixes))


def _preview(value, limit=650):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) <= limit:
        return value
    return {"preview": encoded[:limit], "truncated": True,
            "full_characters": len(encoded), "next_check": "review inspect this item"}


def build(index, prefixes, fact_kinds=(), hops=3):
    if not prefixes or not 0 <= hops <= 8:
        raise ValueError("focus requires path prefixes and hops 0..8")
    for prefix in prefixes:
        review.safe_path(index["inputs"]["source_roots"]["from"], prefix)
    nodes = index["graph"]["nodes"]
    selected, references, questions = defaultdict(set), {}, {}
    direct, sources, referenced_files = set(), [], set()
    aliases, mojo_files = defaultdict(set), defaultdict(set)
    for uid, node in sorted(nodes.items()):
        if any(review._matches_paths([path], prefixes) for path in _paths(node)):
            selected[uid].add("declared_in_selected_paths")
            direct.add(uid)
        for side, fact in node.get("sides", {}).items():
            if node["kind"] == "base_feature":
                var = fact.get("attrs", {}).get("var")
                if var:
                    aliases[(side, var)].add(uid)
                    aliases[(side, var.rsplit("::", 1)[-1])].add(uid)
            if node["kind"].startswith("mojo_"):
                aliases[(side, fact["key"].replace(".", "::"))].add(uid)
                if fact.get("path"):
                    mojo_files[(side, fact["path"])].add(uid)
    for item in index["items"].values():
        if item["kind"] == "finding" and review._matches_paths(item["paths"], prefixes):
            selected[item["id"]].add("declared_in_selected_paths")
            direct.add(item["id"])
        if item["kind"] == "source_delta" and item["path"].endswith(".mojom"):
            for side in ("from", "to"):
                mojo_files[(side, item["path"])]  # Keep imported files without extracted facts.

    def question(row):
        questions[digest(row)] = row

    def reference(row, targets):
        row["targets"] = sorted(targets)
        row["certainty"] = ("unmatched" if not targets else
                            "lexical_lead" if len(targets) == 1 else "ambiguous_lead")
        rid = "reference:" + digest(row)[:20]
        references[rid] = {"id": rid, **row}
        # Preserve every ambiguous candidate; none is asserted to execute.
        for uid in targets:
            selected[uid].add(rid)
        if not targets:
            question({**row, "reason": (
                "Referenced file is in the comparison but has no extracted declaration; read its source"
                if row.get("candidate_paths") else
                "No indexed declaration or file matches this reference; the target may be outside the comparison")})

    paths = _seed_paths(index, prefixes)
    if not paths:
        question({"path_prefixes": sorted(set(prefixes)),
                  "reason": "No source files found under selected prefixes; scope may be missing or misspelled"})
    for path in paths:
        for side in ("from", "to"):
            try:
                data, origin = review.source_bytes(index, side, path)
            except (OSError, ValueError) as exc:
                question({"side": side, "path": path, "reason": str(exc)})
                continue
            source = {"side": side, "path": path, "origin": origin,
                      "sha256": hashlib.sha256(data).hexdigest() if data is not None else None}
            sources.append(source)
            if data is None:
                if origin != "git_absent":
                    question({**source, "reason": "Missing cached side is unknown, not upstream absence"})
                continue
            if len(data) > 20 * 1024 * 1024 or b"\0" in data:
                question({**source, "reason": "Binary or >20 MB source was not scanned"})
                continue
            text = data.decode("utf-8", errors="replace")
            seen = set()
            for match in FEATURE_CALL.finditer(text):
                symbol = match.group(1)
                if not aliases.get((side, symbol)) and not aliases.get((side, symbol.rsplit("::", 1)[-1])):
                    question({**source, "line": text.count("\n", 0, match.start()) + 1,
                              "identifier": symbol, "reason": "Feature check has no matching declaration"})
            for line, content in enumerate(text.splitlines(), 1):
                for match in IDENTIFIER.finditer(content):
                    symbol = match.group()
                    targets = aliases.get((side, symbol), set())
                    if not targets and "::" in symbol and "::mojom::" not in symbol:
                        targets = aliases.get((side, symbol.rsplit("::", 1)[-1]), set())
                    if not targets and "::mojom::" in symbol:
                        targets = aliases.get((side, re.sub(r"(?:Ptr|DataView)$", "", symbol)), set())
                    # Avoid turning every ordinary identifier into an unknown
                    # reference; unsupported expressions remain an explicit limit.
                    if not targets or symbol in seen:
                        continue
                    seen.add(symbol)
                    reference({**source, "line": line, "identifier": symbol,
                               "relation": "source_identifier"}, targets)
                for match in MOJO_IMPORT.finditer(content):
                    imported = match.group(1)
                    if imported in seen:
                        continue
                    seen.add(imported)
                    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(path), imported))
                    candidates = [p for s, p in mojo_files if s == side and p in (imported, normalized)]
                    if not candidates:
                        candidates = sorted({p for s, p in mojo_files if s == side and
                                             (imported.endswith("/" + p) or p.endswith("/" + imported.lstrip("./")))})
                    if not candidates:
                        candidates = sorted({p for s, p in mojo_files if s == side and
                                             posixpath.basename(p) == posixpath.basename(imported)})
                    targets = {uid for p in candidates for uid in mojo_files[(side, p)]}
                    referenced_files.update(candidates)
                    reference({**source, "line": line, "identifier": imported,
                               "relation": "mojo_import", "candidate_paths": candidates}, targets)

    # Traverse declared dependencies, not every consumer of a shared flag.
    # Interface/struct children are evidence when their owning contract is used.
    outgoing = defaultdict(list)
    for edge in index["graph"]["edges"]:
        if edge["certainty"] != "declared_reference":
            continue
        outgoing[edge["source"]].append((edge["target"], edge))
        if edge["relation"] in ("interface_member", "struct_field"):
            outgoing[edge["target"]].append((edge["source"], edge))
    queue = deque((uid, 0) for uid in sorted(selected))
    visited = set(selected)
    while queue:
        uid, depth = queue.popleft()
        for target, edge in sorted(outgoing[uid], key=lambda pair: (pair[0], pair[1]["id"])):
            if target in visited:
                continue
            if depth == hops:
                question({"source": uid, "target": target, "relation": edge["relation"],
                          "reason": "Dependency hop limit; inspect related source"})
                continue
            selected[target].add(edge["id"])
            references[edge["id"]] = edge
            visited.add(target)
            queue.append((target, depth + 1))
    for row in index["graph"]["unresolved"]:
        if row["source"] in selected:
            question({**row, "reason": "Unresolved declaration reference"})

    findings = []
    for uid in sorted(selected):
        item = index["items"].get(uid)
        if not item or item["kind"] != "finding":
            continue
        change = item["data"]["change"]
        findings.append({"id": uid, "name": item["name"], "kind": change["kind"],
                         "direction": change["change_type"], "paths": item["paths"],
                         "selection": "direct" if uid in direct else "dependency",
                         "requested_kind": not fact_kinds or change["kind"] in fact_kinds,
                         "deltas": _preview(change["deltas"]),
                         "before": _preview(change.get("before")), "after": _preview(change.get("after")),
                         "unconfirmed": item["data"]["unconfirmed"],
                         "references": sorted(selected[uid])})
    relevant_paths = set(paths) | referenced_files | {path for uid in selected for path in _paths(nodes[uid])}
    relevant_paths.update(path for uid in selected for path in index["items"].get(uid, {}).get("paths", []))
    files = [{"id": uid, "path": item["path"], "state": item["state"],
              "selection": "direct" if item["path"] in paths else "dependency",
              "finding_count": len(item["findings"]), "hashes": item["hashes"]}
             for uid, item in sorted(index["items"].items())
             if item["kind"] == "source_delta" and item["path"] in relevant_paths]
    result = {"schema": SCHEMA, "fingerprint": index["fingerprint"],
              "refs": index["inputs"]["refs"],
              "request": {"path_prefixes": sorted(set(prefixes)), "fact_kinds": sorted(set(fact_kinds)), "hops": hops},
              "findings": findings, "files": files, "references": [references[k] for k in sorted(references)],
              "unresolved": [questions[k] for k in sorted(questions)], "sources": sources,
              "limits": ["Retrieval candidates, not event boundaries or proof of importance.",
                         "Lexical references can occur in inactive code, tests or comments; inspect consumers and conditions.",
                         "Only selected-path source is scanned for lexical references; indirect code requires further investigation.",
                         "Unrecognized syntax, dynamic bindings, missing cache and ambiguous targets can hide dependencies.",
                         "Unselected items are unexamined, not automatically out of scope.",
                         "Compact previews can omit conditions; use inspect and source before concluding."]}
    result["limits"].extend(index["warnings"])
    result["summary"] = {"index_total": len(index["items"]), "seed_files": len(paths),
                         "selected_nodes": len(selected), "findings": len(findings), "files": len(files),
                         "dependency_findings": sum(f["selection"] == "dependency" for f in findings),
                         "unresolved": len(questions), "semantic_completeness": "not measured",
                         "serialized_characters": {key: len(json.dumps(result[key], ensure_ascii=False, separators=(",", ":")))
                                                   for key in ("findings", "files", "references", "unresolved", "sources")},
                         "token_count": None}
    result["digest"] = digest(result)
    return result


def load(index, path):
    packet = read_json(path)
    if packet.get("schema") != SCHEMA or packet.get("fingerprint") != index["fingerprint"]:
        raise ValueError("focus evidence differs from review index; rebuild the focus packet")
    if packet.get("digest") != digest({key: value for key, value in packet.items() if key != "digest"}):
        raise ValueError("focus packet content changed; rebuild instead of editing retrieved evidence")
    for source in packet["sources"]:
        data, _ = review.source_bytes(index, source["side"], source["path"])
        actual = hashlib.sha256(data).hexdigest() if data is not None else None
        if actual != source["sha256"]:
            raise ValueError("focus source changed; refresh the review and rebuild the focus packet")
    return packet
