"""Group related findings into one story.

A single upstream change arrives as scattered fragments across every surface
the extractors read. The Local Network Access migration between M148 and M151
produced seven separate findings:

    webui_route    SITE_SETTINGS_LOCAL_NETWORK_ACCESS   removed
    webui_route    SITE_SETTINGS_LOCAL_NETWORK          re-gated
    webui_gate     enableLocalNetworkAccessSplitPermissions   removed
    webui_gate     enableLocalNetworkAccessSetting      expression changed
    webui_control  label:siteSettingsLocalNetworkAccess removed
    base_feature   LocalNetworkAccessChecksSplitPermissions   flag retired
    blink_runtime  LocalNetworkAccessSplitPermissions   dropped

Read as seven lines they contradict each other -- one says a page was removed,
another says a page appeared. Read as one cluster they say something simple and
true: the page moved to split permissions, users already had it at M148, and
the only downstream work is updating a stale route reference.

Grouping uses the links the extractors already captured, not string similarity
on names. A route names its guard; a guard names its features; a feature shares
its name with the Blink runtime flag. Those are facts, so the resulting cluster
is exact rather than a guess.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .model import (
    KIND_BASE_FEATURE,
    KIND_BLINK_RUNTIME,
    KIND_FEATURE_PARAM,
    KIND_WEBUI_CONTROL,
    KIND_WEBUI_GATE,
    KIND_WEBUI_ROUTE,
    Finding,
)


class _Union:
    """Union-find over finding uids."""

    def __init__(self) -> None:
        self.parent: Dict[str, str] = {}

    def add(self, x: str) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _flag_name(var_or_name: str) -> str:
    """kLocalNetworkAccessChecks -> LocalNetworkAccessChecks"""
    if len(var_or_name) > 1 and var_or_name[0] == "k" and var_or_name[1].isupper():
        return var_or_name[1:]
    return var_or_name


def _attrs(finding: Finding) -> dict:
    return finding.change.after or finding.change.before or {}


def _both_attrs(finding: Finding) -> List[dict]:
    """Both sides of a change.

    A modified fact can point at different things before and after -- the very
    case that matters. ``SITE_SETTINGS_LOCAL_NETWORK`` was guarded by
    ``enableLocalNetworkAccessSplitPermissions`` at M148 and by
    ``enableLocalNetworkAccessSetting`` at M151; reading only the new side
    splits one migration into two unrelated clusters.
    """
    return [d for d in (finding.change.before, finding.change.after) if d]


def _norm(text: str) -> str:
    """SITE_SETTINGS_LOCAL_NETWORK_ACCESS and siteSettingsLocalNetworkAccess
    are the same identifier written in two conventions."""
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def build_clusters(findings: Sequence[Finding]) -> Dict[str, List[Finding]]:
    """Return cluster_id -> findings, for clusters of two or more.

    Singletons are left out: a lone finding is already its own story and
    wrapping it in a cluster adds noise rather than removing it.
    """
    union = _Union()
    by_kind_key: Dict[tuple, Finding] = {}
    for f in findings:
        union.add(f.uid)
        by_kind_key[(f.change.kind, f.change.key)] = f

    # Gates are keyed by the loadTimeData key, which is what a route names.
    gates = {f.change.key: f for f in findings
             if f.change.kind == KIND_WEBUI_GATE}
    # base::Feature findings are keyed by the feature string.
    features = {f.change.key: f for f in findings
                if f.change.kind == KIND_BASE_FEATURE}

    # Routes indexed by their normalized name, so a control naming the same
    # thing in camelCase joins the route that spells it in SHOUTY_CASE.
    routes_by_norm: Dict[str, Finding] = {}
    for f in findings:
        if f.change.kind == KIND_WEBUI_ROUTE:
            routes_by_norm.setdefault(_norm(f.change.name), f)

    for f in findings:
        kind = f.change.kind

        if kind == KIND_WEBUI_ROUTE:
            # route -> its loadTimeData guard, on both sides of the change
            for attrs in _both_attrs(f):
                for guard in attrs.get("guards") or []:
                    gate = gates.get(guard)
                    if gate is not None:
                        union.union(f.uid, gate.uid)

        elif kind == KIND_WEBUI_GATE:
            # gate -> every base::Feature its expression names
            for attrs in _both_attrs(f):
                for var in attrs.get("features") or []:
                    feature = features.get(_flag_name(var))
                    if feature is not None:
                        union.union(f.uid, feature.uid)

        elif kind == KIND_BLINK_RUNTIME:
            # Only join on a link Chromium actually declares. Many Blink flags
            # carry base_feature: "none", meaning there is no C++ feature to
            # join to -- inventing one from name similarity would be a guess.
            for attrs in _both_attrs(f):
                declared = attrs.get("base_feature")
                if isinstance(declared, str) and declared and declared != "none":
                    twin = features.get(_flag_name(declared))
                    if twin is not None:
                        union.union(f.uid, twin.uid)
            twin = features.get(f.change.key)
            if twin is not None:
                union.union(f.uid, twin.uid)

        elif kind == KIND_FEATURE_PARAM:
            for attrs in _both_attrs(f):
                owner = features.get(attrs.get("feature", ""))
                if owner is not None:
                    union.union(f.uid, owner.uid)

        elif kind == KIND_WEBUI_CONTROL:
            # A control joins the page it labels. Exact match after
            # normalization only: a looser rule would drag every control on a
            # busy page into one cluster.
            for attrs in _both_attrs(f):
                for candidate in (attrs.get("label"), attrs.get("element_id")):
                    route = routes_by_norm.get(_norm(candidate)) if candidate else None
                    if route is not None:
                        union.union(f.uid, route.uid)

    groups: Dict[str, List[Finding]] = {}
    for f in findings:
        groups.setdefault(union.find(f.uid), []).append(f)
    return {root: members for root, members in groups.items()
            if len(members) > 1}


def cluster_label(members: Sequence[Finding]) -> str:
    """A human name for the cluster: the highest-scoring member's name."""
    lead = max(members, key=lambda f: f.score)
    return lead.change.name


def annotate(findings: Sequence[Finding]) -> Dict[str, List[Finding]]:
    """Attach cluster info to each finding in place; return the clusters."""
    clusters = build_clusters(findings)
    for root, members in clusters.items():
        label = cluster_label(members)
        for f in members:
            f.enrichment["cluster"] = {
                "id": root,
                "label": label,
                "size": len(members),
                "kinds": sorted({m.change.kind for m in members}),
                "top_score": max(m.score for m in members),
            }
    return clusters


def summarize(clusters: Dict[str, List[Finding]], limit: int = 25) -> List[dict]:
    """Cluster overview for the report, biggest impact first."""
    rows = []
    for root, members in clusters.items():
        rows.append({
            "id": root,
            "label": cluster_label(members),
            "size": len(members),
            "top_score": max(m.score for m in members),
            "kinds": sorted({m.change.kind for m in members}),
            "buckets": sorted({m.bucket for m in members}),
            "members": [m.uid for m in sorted(members, key=lambda x: -x.score)],
        })
    rows.sort(key=lambda r: (-r["top_score"], -r["size"]))
    return rows[:limit] if limit else rows
