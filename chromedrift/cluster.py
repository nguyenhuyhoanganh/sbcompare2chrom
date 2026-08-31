"""Group related findings into one story.

A single Chromium change arrives as scattered fragments across every surface
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
the only work left is updating a stale route reference.

Grouping uses the links the extractors already captured, not string similarity
on names. A route names its guard; a guard names its features; a feature shares
its name with the Blink runtime flag. Those are facts, so the resulting cluster
is exact rather than a guess.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from .extract.base_features import feature_name_from_var as _flag_name
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


def _data_key(finding: Finding) -> str:
    """The bare loadTimeData key a gate sets, whatever its own key is."""
    for attrs in _both_attrs(finding):
        if attrs.get("data_key"):
            return str(attrs["data_key"])
    return finding.change.name or finding.change.key.rsplit("/", 1)[-1]


# Verdicts that name the declaring file rather than the fact. Two rows sharing
# one of these share a busy file, which is not a story.
_LEAD_VERDICTS = frozenset({"crowded", "touched"})

# How many findings one CL may join. A guard-rail, not a measurement, and it
# is written down as one.
#
# Nothing in the data needs it. Measured over a real M148 -> M151 run with the
# top 150 resolved, groups run 2 to 7 with a single exception at 14 -- CL
# 7899676, "[dom] Introduce HyperlinkElementUtils", where one CL introduces a
# mixin and fourteen members of the interface move with it. That group is
# right, and it is the most useful one in the run; a cap of twelve would drop
# it whole, since a group past the cap is skipped rather than split.
#
# The real guard against a CL joining everything it touched is upstream and
# already there: a reformat is `common: true` in Gerrit's diff and never
# counts as a changed line, and a lead names the file rather than the fact and
# is excluded below. This exists only so that if both of those ever fail, the
# failure is a group nobody reads rather than a group holding half the report.
CL_GROUP_MAX = 20


def build_clusters(findings: Sequence[Finding]) -> Dict[str, List[Finding]]:
    """Return cluster_id -> findings, for clusters of two or more.

    Singletons are left out: a lone finding is already its own story and
    wrapping it in a cluster adds noise rather than removing it.
    """
    union = _Union()
    for f in findings:
        union.add(f.uid)

    # A gate's own key is qualified by its handler, because two handlers set
    # the same loadTimeData key to different things. A route names only the
    # bare key, so the join is on that -- and it is one-to-many, since the
    # route does not say which handler serves it.
    gates: Dict[str, List[Finding]] = {}
    for f in findings:
        if f.change.kind == KIND_WEBUI_GATE:
            gates.setdefault(_data_key(f), []).append(f)
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
                    for gate in gates.get(guard, ()):
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

    # Every rule above joins on a link Chromium declares *in the source*, and
    # that is why they reach almost nothing at the top of a report: between a
    # `.mojom` and an `.idl` no such link is ever written. Measured on a real
    # M148 -> M151 run, the rules above cover 183 of 3,022 findings and 143 of
    # those groups are a feature and its parameters -- which is the bottom of
    # the ranking, not the top. Of the 150 highest-scoring findings they reach
    # 6.
    #
    # A shared CL is the same kind of evidence recorded somewhere else. The
    # author wrote one change and it landed across several declarations; the
    # CL number is Chromium saying so, not a guess from name similarity. It
    # reaches 86 of that same top 150, and none of the 6.
    #
    # Only the CL, never the issue. An issue collects a programme of work --
    # one in this run carries 24 CLs across unrelated surfaces -- and joining
    # on it would build a group nobody can read. A CL is one author's one
    # change, which is the unit this function is about.
    by_cl: Dict[int, List[Finding]] = {}
    for f in findings:
        for change in ((f.enrichment or {}).get("gerrit") or {}).get(
                "changes") or []:
            # A lead names the file, not the fact, so two rows sharing one is
            # evidence that the file is busy and nothing more.
            if change.get("match") in _LEAD_VERDICTS:
                continue
            number = change.get("number")
            if number:
                by_cl.setdefault(number, []).append(f)
    for members in by_cl.values():
        if len(members) < 2 or len(members) > CL_GROUP_MAX:
            continue
        first = members[0]
        for other in members[1:]:
            union.union(first.uid, other.uid)

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
    """Cluster overview for the report, heaviest first."""
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
