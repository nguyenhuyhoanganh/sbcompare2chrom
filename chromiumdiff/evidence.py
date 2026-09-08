"""Versioned retrieval links, including facts which did not change.

Edges are evidence to investigate, never instructions to merge events. No
feature-name vocabulary, score threshold, or connected-component verdict is
used here. Unsupported syntax remains a source-reading task.
"""

from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
from typing import Optional

from .model import Report, Snapshot


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def build_graph(report: Report, old: Optional[Snapshot] = None,
                new: Optional[Snapshot] = None) -> dict:
    nodes = {}
    for side, snapshot in (("from", old), ("to", new)):
        if snapshot is None:
            continue
        for fact in sorted(snapshot.facts, key=lambda f: (f.uid, f.path, f.line)):
            node = nodes.setdefault(fact.uid, {"uid": fact.uid, "kind": fact.kind,
                                               "name": fact.name, "sides": {}})
            node["sides"].setdefault(side, fact.to_dict())
    for f in sorted(report.findings, key=lambda f: f.uid):
        c = f.change
        node = nodes.setdefault(f.uid, {"uid": f.uid, "kind": c.kind,
                                       "name": c.name, "sides": {}})
        node["finding"] = True
        for side, attrs in (("from", c.before), ("to", c.after)):
            if attrs is not None:
                node["sides"].setdefault(side, {
                    "kind": c.kind, "key": c.key, "name": c.name,
                    "attrs": attrs, "locations_unqualified": c.locations})

    edges = {}
    unresolved = []

    def edge(source, target, relation, side, location, certainty):
        if source == target:
            return
        row = dict(source=source, target=target, relation=relation, side=side,
                   location=location, certainty=certainty)
        row["id"] = "edge:" + digest(row)[:20]
        edges[row["id"]] = row

    for side in ("from", "to"):
        aliases = defaultdict(set)
        for uid, node in nodes.items():
            fact = node["sides"].get(side)
            if fact is None:
                continue
            attrs = fact.get("attrs") or {}
            names = {fact["key"], fact["name"]}
            for attr in ("var", "data_key"):
                if isinstance(attrs.get(attr), str):
                    names.add(attrs[attr])
            for name in names:
                aliases[(node["kind"], name)].add(uid)
                aliases[(node["kind"], name.rsplit("::", 1)[-1])].add(uid)

        for uid, node in sorted(nodes.items()):
            fact = node["sides"].get(side)
            if fact is None:
                continue
            a = fact.get("attrs") or {}
            kind = node["kind"]
            requests = []
            if kind == "webui_route":
                requests += [("webui_gate", x, "guard") for x in a.get("guards") or []]
            if kind == "webui_gate":
                requests += [("base_feature", x, "feature_expression")
                             for x in a.get("features") or []]
            if kind == "webui_control" and a.get("pref"):
                requests.append(("pref", a["pref"], "pref_binding"))
            if kind == "feature_param" and a.get("feature"):
                requests.append(("base_feature", a["feature"], "parameter_owner"))
            if kind == "blink_runtime_feature":
                declared = a.get("base_feature")
                if isinstance(declared, str) and declared and declared != "none":
                    requests.append(("base_feature", declared, "declared_base_feature"))
                for attr in ("depends_on", "implied_by"):
                    values = a.get(attr) or []
                    if isinstance(values, str):
                        values = [values]
                    requests += [("blink_runtime_feature", x, attr) for x in values]
            if kind.startswith("idl_"):
                runtime = a.get("runtime_enabled") or (a.get("ext") or {}).get("RuntimeEnabled")
                if isinstance(runtime, str) and runtime:
                    requests.append(("blink_runtime_feature", runtime, "runtime_gate"))
                if kind == "idl_member" and a.get("interface"):
                    requests.append(("idl_interface", a["interface"], "interface_member"))
            if kind == "mojo_method" and a.get("interface"):
                requests.append(("mojo_interface", a["interface"], "interface_member"))
            if kind == "mojo_field" and a.get("struct"):
                requests.append(("mojo_struct", a["struct"], "struct_field"))

            location = {"ref": report.from_ref if side == "from" else report.to_ref,
                        "path": fact.get("path"), "line": fact.get("line"),
                        "attrs": sorted({r[2] for r in requests})}
            for target_kind, name, relation in requests:
                # Prefer fully qualified identifiers. Bare-name matches can be
                # ambiguous across handlers/namespaces; retain that warning.
                targets = aliases.get((target_kind, name), set())
                if not targets:
                    targets = aliases.get((target_kind, name.rsplit("::", 1)[-1]), set())
                if not targets:
                    unresolved.append(dict(source=uid, side=side, relation=relation,
                                           target_kind=target_kind, identifier=name))
                for target in sorted(targets):
                    edge(uid, target, relation, side, location,
                         "ambiguous_target" if len(targets) > 1 else "declared_reference")

    # A CL node avoids quadratic pairs and makes high-fanout CLs visible.
    for f in sorted(report.findings, key=lambda f: f.uid):
        for cl in ((f.enrichment.get("gerrit") or {}).get("changes") or []):
            number = cl.get("number")
            if not number:
                continue
            uid = f"cl:{number}"
            nodes.setdefault(uid, dict(uid=uid, kind="cl", name=cl.get("subject", uid),
                                       sides={}, number=number))
            match = cl.get("match", "unknown")
            edge(f.uid, uid, "cl_match", "window", {"match": match},
                 "lead" if match in ("touched", "crowded", "described", "unknown")
                 else "matched_diff")
    return {"nodes": nodes, "edges": sorted(edges.values(), key=lambda e: e["id"]),
            "unresolved": sorted(unresolved, key=lambda r: (r["source"], r["side"],
                                                           r["relation"], r["identifier"]))}


def related(graph: dict, uid: str, hops: int = 2, hub_limit: int = 40) -> list:
    """Deterministic bounded traversal; every skipped hub is explicit.

    Query that hub with one hop to page through *all* its direct links. Weak
    leads are returned but never expanded automatically.
    """
    if uid not in graph["nodes"]:
        raise ValueError(f"unknown evidence node: {uid}")
    if not 1 <= hops <= 4 or hub_limit < 1:
        raise ValueError("hops must be 1..4; hub-limit must be positive")
    adjacency = defaultdict(list)
    for e in graph["edges"]:
        adjacency[e["source"]].append((e["target"], e))
        adjacency[e["target"]].append((e["source"], e))
    seen = {uid}
    queue = deque([(uid, [])])
    rows = []
    while queue:
        current, chain = queue.popleft()
        neighbors = sorted(adjacency[current], key=lambda x: (x[0], x[1]["id"]))
        if current != uid and len(neighbors) > hub_limit:
            rows.append({"uid": current, "hub": True, "degree": len(neighbors),
                         "continuation": "query this uid with --hops 1", "chain": chain})
            continue
        for other, e in neighbors:
            route = chain + [e]
            rows.append({"uid": other, "kind": graph["nodes"][other]["kind"],
                         "name": graph["nodes"][other]["name"],
                         "finding": bool(graph["nodes"][other].get("finding")),
                         "chain": route})
            if other not in seen and len(route) < hops and e["certainty"] not in (
                    "lead", "ambiguous_target"):
                seen.add(other)
                queue.append((other, route))
    return rows
