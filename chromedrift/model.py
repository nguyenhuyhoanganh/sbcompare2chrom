"""Core data model shared by every stage of the pipeline.

The pipeline is a straight line of pure data transforms:

    Snapshot(ref)  ->  [Fact]         extract/*
    (Snapshot, Snapshot) -> [Change]  diff.py
    ([Change], TouchSet) -> [Finding] impact.py
    [Finding] -> [Finding+ai]         ai/analyze.py
    [Finding] -> report               report/*

Every stage reads and writes JSON, so any stage can be run, cached, inspected
and re-run on its own.  That matters here because acquiring a snapshot costs
network time while the diff/impact stages are iterated on constantly.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# Bump whenever cached artifacts stop meaning what an older build thought they
# meant, so stale caches are rebuilt instead of silently misread.
#   2: extraction is scoped to the declared target set. Version 1 snapshots
#      took their scope from whatever the shared per-ref tree cache held, so a
#      "minimal" snapshot could contain the full fact set.
#   3: the "default" target set gained the desktop WebUI surfaces, so a
#      version 2 snapshot named "default" no longer means the same thing.
#   4: base_feature facts record the preprocessor guards enclosing them.
#      Snapshots without that attribute compare as different from ones with
#      it, which made an identical tree look 1,369 facts diverged.
#   5: WebUI templates include the Lit dialect (.html.ts). Version 4 read only
#      Polymer .html, leaving 23% of templates unread -- and nearly all of
#      extensions, print_preview, history, bookmarks and downloads.
#   6: the tree cache marker now includes the target's suffix filter. Version 5
#      snapshots were rebuilt over trees fetched under the old, narrower
#      filter, so they claim to cover Lit templates and do not.
#   7: the target set gained 13 feature files it had been missing, including
#      chrome_features.cc. Version 6 snapshots cover about 45% fewer
#      base::Feature declarations than they appear to.
#   8: the filename filter widened past the *_features.cc convention and now
#      excludes test files. Version 7 read 1 of 24 declarations in
#      chrome/browser/ui/webui and counted test-only features elsewhere.
#   9: the product is a Windows desktop browser, so platform is fixed rather
#      than selectable. platform_state/platform_status now carry only
#      "windows", and blink facts renamed android_status -> windows_status.
#  10: the legacy `const base::Feature kFoo{...}` form records "conditions"
#      like the macro form does. Version 9 omitted it there, so a feature
#      written the old way on one side of a comparison and the new way on the
#      other reported as modified when nothing had changed.
SCHEMA_VERSION = 10

# ---------------------------------------------------------------------------
# Fact kinds.  Each is produced by exactly one extractor.
# ---------------------------------------------------------------------------

KIND_BASE_FEATURE = "base_feature"
KIND_FEATURE_PARAM = "feature_param"
KIND_BLINK_RUNTIME = "blink_runtime_feature"
KIND_IDL_INTERFACE = "idl_interface"
KIND_IDL_MEMBER = "idl_member"
KIND_MOJO_INTERFACE = "mojo_interface"
KIND_MOJO_METHOD = "mojo_method"
KIND_SWITCH = "switch"
KIND_PREF = "pref"
KIND_FLAG_ENTRY = "flag_entry"
# Desktop WebUI. Settings, History, Downloads, Bookmarks, Extensions and ~130
# other chrome:// pages are all built the same way, and form one chain:
#   route -> loadTimeData guard -> base::Feature
KIND_WEBUI_ROUTE = "webui_route"
KIND_WEBUI_CONTROL = "webui_control"
KIND_WEBUI_GATE = "webui_gate"

ALL_KINDS = (
    KIND_BASE_FEATURE,
    KIND_FEATURE_PARAM,
    KIND_BLINK_RUNTIME,
    KIND_IDL_INTERFACE,
    KIND_IDL_MEMBER,
    KIND_MOJO_INTERFACE,
    KIND_MOJO_METHOD,
    KIND_SWITCH,
    KIND_PREF,
    KIND_FLAG_ENTRY,
    KIND_WEBUI_ROUTE,
    KIND_WEBUI_CONTROL,
    KIND_WEBUI_GATE,
)

# Human labels used in reports.
KIND_LABELS = {
    KIND_BASE_FEATURE: "Chromium feature flag",
    KIND_FEATURE_PARAM: "Feature parameter",
    KIND_BLINK_RUNTIME: "Blink runtime feature",
    KIND_IDL_INTERFACE: "Web IDL interface",
    KIND_IDL_MEMBER: "Web IDL member",
    KIND_MOJO_INTERFACE: "Mojo interface",
    KIND_MOJO_METHOD: "Mojo method",
    KIND_SWITCH: "Command-line switch",
    KIND_PREF: "Preference",
    KIND_FLAG_ENTRY: "chrome://flags entry",
    KIND_WEBUI_ROUTE: "WebUI page",
    KIND_WEBUI_CONTROL: "WebUI control",
    KIND_WEBUI_GATE: "WebUI visibility gate",
}

ADDED = "added"
REMOVED = "removed"
MODIFIED = "modified"

# Two comparisons, one engine, opposite meanings.
#
#   uprev: upstream at time A vs upstream at time B. "Removed" means Chromium
#          cleaned something up, which is usually harmless.
#   fork:  upstream vs a vendor fork at the same milestone. "Removed" means the
#          vendor deleted it -- a deliberate product decision that must survive
#          every future rebase, and "added" is divergence to carry, not a
#          capability on offer.
#
# These live here rather than in diff.py because the inversion does not stop at
# the diff. Scoring, the model prompt and the report all describe a change in
# words that are only true for one of the two, so each of them has to be told
# which comparison it is looking at.
MODE_UPREV = "uprev"
MODE_FORK = "fork"
MODES = (MODE_UPREV, MODE_FORK)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    """One extracted, normalized piece of the Chromium feature surface.

    ``key`` must be stable across Chromium versions even when the *syntax*
    that declares it changes.  This is not hypothetical: between M139 and M143
    the ``BASE_FEATURE`` macro dropped its string-name argument, so a parser
    keyed on raw source text reports every feature as removed-and-re-added.
    Extractors are responsible for normalizing to a semantic key.
    """

    kind: str
    key: str
    name: str
    path: str = ""
    line: int = 0
    attrs: Dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"{self.kind}:{self.key}"

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "key": self.key, "name": self.name}
        if self.path:
            d["path"] = self.path
        if self.line:
            d["line"] = self.line
        if self.attrs:
            d["attrs"] = self.attrs
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Fact":
        return cls(
            kind=d["kind"],
            key=d["key"],
            name=d.get("name", d["key"]),
            path=d.get("path", ""),
            line=d.get("line", 0),
            attrs=d.get("attrs", {}) or {},
        )


@dataclass
class Snapshot:
    """The complete extracted feature surface of one Chromium ref."""

    ref: str
    facts: List[Fact] = field(default_factory=list)
    milestone: Optional[int] = None
    created: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created:
            self.created = _dt.datetime.now(_dt.timezone.utc).isoformat(
                timespec="seconds"
            )

    def index(self) -> Dict[str, Fact]:
        """uid -> Fact.  Later duplicates lose; extractors dedupe first."""
        return {f.uid: f for f in self.facts}

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.facts:
            out[f.kind] = out.get(f.kind, 0) + 1
        return dict(sorted(out.items()))

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "ref": self.ref,
            "milestone": self.milestone,
            "created": self.created,
            "meta": self.meta,
            "counts": self.counts(),
            "facts": [f.to_dict() for f in self.facts],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        return cls(
            ref=d["ref"],
            milestone=d.get("milestone"),
            created=d.get("created", ""),
            meta=d.get("meta", {}) or {},
            facts=[Fact.from_dict(x) for x in d.get("facts", [])],
        )


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------


@dataclass
class Change:
    """A semantic difference between two snapshots, for one Fact identity."""

    change_type: str  # added | removed | modified
    kind: str
    key: str
    name: str
    before: Optional[dict] = None
    after: Optional[dict] = None
    deltas: Dict[str, List[Any]] = field(default_factory=dict)  # attr -> [old, new]
    paths: List[str] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)
    severity: int = 0

    @property
    def uid(self) -> str:
        return f"{self.kind}:{self.key}"

    def to_dict(self) -> dict:
        return {
            "change_type": self.change_type,
            "kind": self.kind,
            "key": self.key,
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "deltas": self.deltas,
            "paths": self.paths,
            "signals": self.signals,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Change":
        return cls(
            change_type=d["change_type"],
            kind=d["kind"],
            key=d["key"],
            name=d.get("name", d["key"]),
            before=d.get("before"),
            after=d.get("after"),
            deltas=d.get("deltas", {}) or {},
            paths=d.get("paths", []) or [],
            signals=d.get("signals", []) or [],
            severity=d.get("severity", 0),
        )


# ---------------------------------------------------------------------------
# Findings (change + downstream impact + optional AI verdict)
# ---------------------------------------------------------------------------

BUCKET_MUST_FIX = "must_fix"
BUCKET_REVIEW = "review"
BUCKET_OPPORTUNITY = "opportunity"
BUCKET_FYI = "fyi"

BUCKET_ORDER = [BUCKET_MUST_FIX, BUCKET_REVIEW, BUCKET_OPPORTUNITY, BUCKET_FYI]

BUCKET_LABELS = {
    BUCKET_MUST_FIX: "Must fix",
    BUCKET_REVIEW: "Needs review",
    BUCKET_OPPORTUNITY: "New opportunity",
    BUCKET_FYI: "FYI",
}


@dataclass
class Finding:
    change: Change
    areas: List[str] = field(default_factory=list)
    matched_paths: List[str] = field(default_factory=list)
    matched_symbols: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    score: int = 0
    bucket: str = BUCKET_FYI
    enrichment: Dict[str, Any] = field(default_factory=dict)
    ai: Dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return self.change.uid

    def to_dict(self) -> dict:
        return {
            "change": self.change.to_dict(),
            "areas": self.areas,
            "matched_paths": self.matched_paths,
            "matched_symbols": self.matched_symbols,
            "reasons": self.reasons,
            "score": self.score,
            "bucket": self.bucket,
            "enrichment": self.enrichment,
            "ai": self.ai,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(
            change=Change.from_dict(d["change"]),
            areas=d.get("areas", []) or [],
            matched_paths=d.get("matched_paths", []) or [],
            matched_symbols=d.get("matched_symbols", []) or [],
            reasons=d.get("reasons", []) or [],
            score=d.get("score", 0),
            bucket=d.get("bucket", BUCKET_FYI),
            enrichment=d.get("enrichment", {}) or {},
            ai=d.get("ai", {}) or {},
        )


@dataclass
class Report:
    """Full pipeline output for one uprev (from_ref -> to_ref)."""

    from_ref: str
    to_ref: str
    findings: List[Finding] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def bucket_counts(self) -> Dict[str, int]:
        out = {b: 0 for b in BUCKET_ORDER}
        for f in self.findings:
            out[f.bucket] = out.get(f.bucket, 0) + 1
        return out

    def by_bucket(self, bucket: str) -> List[Finding]:
        return [f for f in self.findings if f.bucket == bucket]

    def filtered(self, area: Optional[str]) -> "Report":
        """A view of this report narrowed to one area.

        Filtering happens here, at render time, and never before analysis:
        the JSON always holds every finding, so slicing per team costs nothing
        and cannot hide anything. Pass ``"_unassigned"`` for the leftover.
        """
        if not area:
            return self
        if area == "_unassigned":
            keep = [f for f in self.findings if not f.areas]
        else:
            keep = [f for f in self.findings if area in f.areas]
        return Report(
            from_ref=self.from_ref,
            to_ref=self.to_ref,
            findings=keep,
            summary=dict(self.summary, filtered_to_area=area,
                         filtered_from_total=len(self.findings)),
            meta=self.meta,
        )

    def known_areas(self) -> List[str]:
        seen: Dict[str, int] = {}
        for f in self.findings:
            for a in f.areas:
                seen[a] = seen.get(a, 0) + 1
        return [a for a, _ in sorted(seen.items(), key=lambda kv: -kv[1])]

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "from_ref": self.from_ref,
            "to_ref": self.to_ref,
            "summary": self.summary,
            "meta": self.meta,
            "bucket_counts": self.bucket_counts(),
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Report":
        return cls(
            from_ref=d["from_ref"],
            to_ref=d["to_ref"],
            findings=[Finding.from_dict(x) for x in d.get("findings", [])],
            summary=d.get("summary", {}) or {},
            meta=d.get("meta", {}) or {},
        )


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def write_json(path: str, obj: Any) -> str:
    """Write ``obj`` as UTF-8 JSON, creating parent directories."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=False)
    os.replace(tmp, path)
    return path


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dedupe_facts(facts: Iterable[Fact]) -> List[Fact]:
    """Drop duplicate uids, keeping the first occurrence (stable ordering).

    Chromium declares a handful of features in more than one place (e.g. a
    feature listed both in a component's own ``*_features.cc`` and re-exported
    from a public header).  Without this the diff sees phantom modifications
    whose direction depends on filesystem walk order.
    """
    seen: Dict[str, Fact] = {}
    for f in facts:
        if f.uid not in seen:
            seen[f.uid] = f
    return sorted(seen.values(), key=lambda f: (f.kind, f.key))
