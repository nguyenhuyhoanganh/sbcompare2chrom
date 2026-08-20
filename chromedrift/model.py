"""Core data model shared by every stage of the pipeline.

The pipeline is a straight line of pure data transforms:

    Snapshot(ref)  ->  [Fact]         extract/*
    (Snapshot, Snapshot) -> [Change]  diff.py
    ([Change], TouchSet) -> [Finding] impact.py
    [Finding] -> [Finding+context]    cluster.py, enrich/*
    [Finding] -> report               report/*

It ends at the report on purpose.  Deciding what a change means for the
product is judgement, and it is left to whoever reads the report.

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
#  11: a WebUI control's identity is qualified by its element id when it has
#      one. The preference alone is not unique -- a radio group and its buttons
#      share it -- so 142 of 881 controls at M148 were being dropped as
#      duplicates, and which survived depended on directory walk order.
#  12: findings no longer carry an `ai` verdict. The tool stops at the evidence
#      and the ranking; judging what a change means is the reader's job, and
#      the reader is a human or an agent running the
#      `analyzing-chromium-uprevs` skill. A version 11 report may hold `ai`
#      blocks, which nothing here reads any more.
#  13: extraction honours a tree target's suffix filter, not just its path
#      prefix. Version 12 snapshots extracted whatever an earlier, wider run
#      had left under the prefix in the shared tree cache: at M148 that was 103
#      .mojom files under chrome/browser/ui/webui, which the "default" target
#      asks for as .cc only. Diffed against a clean M151 it produced 803
#      phantom "Mojo method removed" findings at severity 80 -- the tool's
#      highest -- sitting at the top of the report.
#  14: the target set reads every pref file in the tree, not just
#      chrome/common/pref_names.h. Version 13 snapshots hold 683 pref keys
#      where 1,575 exist, so 892 keys were absent -- and because Chromium is
#      actively splitting that file up, keys leaving it read as deletions.
#  15: four corrections found by auditing extraction and comparison against six
#      real versions (M130 through M151):
#        - a base::Feature's C++ identifier is compared. Version 14 keyed on
#          the feature string only, so renaming the identifier while holding
#          the string produced no change at all -- kDIPS -> kBtm among them,
#          which breaks the build of anything writing features::kDIPS.
#        - a WebUI control that starts writing a different preference is paired
#          and reported. Version 14 emitted two unconnected rows, because the
#          preference is part of the control's identity; 21 real repoints were
#          split that way.
#        - the `*_prefs.{h,cc}` naming convention is read as well as
#          `*pref_names.{h,cc}`, adding 469 keys in 54 files.
#        - a control's `pref` attribute requires the `prefs.` binding prefix,
#          so an ordinary component property is no longer recorded as a
#          preference key. 27 of 156 bindings at M151 were such properties.
#  16: every snapshot records how much of its version's tree the target set
#      actually read, measured against a recursive listing of that tree rather
#      than assumed. Version 15 snapshots carry no such measurement, and the
#      target set they were built from named files chosen at M151, which is a
#      different scope from the one the same name resolves to now.
#  17: `wide` reads every filename shape an extractor understands, not only
#      feature and pref files, and reaches content/ and blink/public. Version 16
#      downloaded the archives holding 934 of the tree's 1,424 .mojom files and
#      124 of its 132 WebUI surfaces, then discarded them for want of a suffix
#      in a filter. String constants are also read across platform trees now,
#      so a pref key moving into a ChromeOS file reads as a move rather than a
#      deletion.
#  18: filename hints match the bare spelling as well as the prefixed one.
#      Chromium writes both `content_switches.cc` and plain `switches.cc`, and
#      the hints required the underscore, so 44 files at M151 were fetched and
#      never read -- among them `components/embedder_support/switches.cc`,
#      which declares --headless, and `extensions/common/switches.cc`, which
#      declares 35 more. Version 17 snapshots are missing those switches while
#      reporting that they read every file in the tree. The candidate rule also
#      learned the `*flags.{cc,h}` convention, which the extractors already
#      read, so coverage now counts 31 files it used to leave out of its own
#      denominator.
#  19: one list of the filename shapes an extractor can read, and one name per
#      distinct measurement.
#        - `--complete` filtered its partition roots through a second copy of
#          that list, which had never learned the `*_prefs.{h,cc}` convention
#          or the `.h` half of four `.cc` hints. The flag whose whole promise is
#          "100% of these roots, by construction" skipped 86 files holding 747
#          keys at M151, so a version 18 `--complete` snapshot is missing them.
#        - a report's `summary.coverage` was area routing while a snapshot's
#          `meta.coverage` was tree coverage. It is now
#          `summary.area_coverage`, and `meta.coverage` in a report means the
#          same thing it means on a snapshot.
#  20: extraction stopped depending on the order the filesystem hands back
#      directories, and everything the comparison treats as meaningful now
#      produces a label.
#        - `os.walk` was sorted for files and not for directories, and when two
#          files declare the same fact the order decided which survived. 228
#          uids collide in the M151 tree and 68 disagree on a compared
#          attribute, so a version 19 snapshot is one of several possible
#          answers: walking the same tree twice in different orders and diffing
#          the result against itself produced 68 changes, topped by a
#          `web_api_signature_change` at severity 50. Dedupe now picks the
#          lowest (path, line) instead of the first arrival.
#        - preference and switch declarations record the `#if` chain around
#          them, resolved for Windows. 115 keys at M151 are not in our binary
#          at all, and nothing had marked them.
#        - WebUI controls record their GRIT `<if expr>` resolved the same way.
#        - a header's own include guard is no longer recorded as a build guard,
#          and an `#elif` branch carries the negation of the branches above it.
#        - a WebUI gate is identified by its handler as well as its
#          loadTimeData key, and a WebUI control by its declaring file as well
#          as its directory. Neither string was unique: at M151, 62 of 668 gate
#          keys were set by more than one handler and 98 of 1,256 control keys
#          declared in more than one file, so 318 declarations were dropped as
#          duplicates and which survived depended on walk order. This is the
#          same defect schema 11 fixed for a control's preference, one level
#          out. Recovering them moves the M151 default set from 24,679 facts to
#          24,871 and wide from 36,095 to 36,356.
#        - nine new signals label attributes that were compared and never
#          explained -- 380 of 709 modified changes at M148 -> M151.
#  21: every fact points at a line, and a finding carries the place rather than
#      only the file.
#        - four of the thirteen kinds set no line number at all -- every Mojo
#          method, every IDL member, every Blink runtime flag and every
#          chrome://flags entry, 20,844 of 36,356 facts. Mojo interfaces had
#          one and it was wrong: `\s*` after the newline in the interface
#          pattern crossed blank lines and masked comments, so 1,453 of 1,455
#          were reported at the last content line above the declaration.
#        - `Change` carries `locations` ("path:line"), and both renderers show
#          it. Version 20 reports cite a file and leave the reader to search it.
#        - the Web IDL reader is restricted to `third_party/blink/renderer/`.
#          The `.idl` extension is shared with Chrome Extensions IDL and with
#          MIDL, and it read both wrongly rather than not at all: 1,081 facts at
#          M151, 96 of them with a whole nested declaration inside their own
#          signature, all reported as Web API changes.
#  22: two curated lists that had decayed became rules, and every attribute the
#      comparison treats as meaningful now produces a label.
#        - a WebUI control is recognised by shape rather than by a list of 27
#          tag names. Measured at M151 across the eight surfaces the default
#          set reads, that list matched 902 of 2,462 custom-element occurrences
#          (36%), and 41 of the misses bind a real preference --
#          `settings-collapse-radio-button` writes one 27 times, and
#          `report/wording.py` already carried a word for that very tag, so the
#          renderer knew about a control the extractor never emitted. A version
#          21 snapshot holds 884 controls where 971 exist, 156 of them
#          preference-bound where 190 are, and 130 identified only by position
#          against 15 now.
#        - `BASE_FEATURE_PARAM` without a name string derives the name from the
#          variable, as `BASE_FEATURE` already did. 20 declarations at M151 are
#          written that way, and version 21 read the *default value* as the
#          param name and dropped the default: `kCacheCertVerificationTtlSecs`
#          came out as a param called `1800`, so changing 1800 to 3600 read as
#          one param removed and another added instead of a default moving.
#        - nine attributes were compared and never explained. A base::Feature's
#          `conditions` (55 rows in M143 -> M148), a Mojo method's `attrs`, a
#          Windows state moving to `conditional`, a feature param's type or
#          owning flag, an IDL member's `member_type`, and the three Blink
#          fields that decide who may reach a flag from outside the renderer.
#          `mojo_interface.module` was dropped from the compared set instead:
#          it is part of the key and can never differ.
#        - two more curated lists found by the same audit. A preference key
#          written `inline constexpr std::string_view kFoo = "..."` is read;
#          version 21 knew only the `char kFoo[]` spelling, so all 63 keys in
#          files Chromium has migrated -- `components/soda/pref_names.h`
#          entirely -- were invisible while the file itself counted as covered.
#          And the Blink manifest's `origin_trial_os`, `origin_trial_type`,
#          `origin_trial_allows_insecure` and `is_protected_feature` are
#          carried, which is 40 declarations at M151 deciding who may turn a
#          flag on from outside the binary.
SCHEMA_VERSION = 22

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

# The thirteen kinds are not thirteen kinds of "feature", and reading them as
# though they were is the most common misreading of a report. They fall into
# three groups that differ in what a change to them *means*:
#
#   switches   the only group where a change moves behaviour on its own
#   contracts  a change breaks something outside the binary, silently -- stored
#              user data, launch scripts, live websites, the other process
#   surface    a change moves what the user sees, or moves a removal date
#
# Measured on a real M139 -> M143 report: 3,120 findings split 34% / 35% / 30%,
# so two thirds of a report is *not* about features being turned on or off.
# A flat kind list hides that, which is why the report groups its filter.
KIND_GROUP_SWITCH = "Behaviour switches"
KIND_GROUP_CONTRACT = "External contracts"
KIND_GROUP_SURFACE = "UI and scheduling"

KIND_GROUPS = (
    (KIND_GROUP_SWITCH, (KIND_BASE_FEATURE, KIND_FEATURE_PARAM, KIND_BLINK_RUNTIME)),
    (KIND_GROUP_CONTRACT, (KIND_PREF, KIND_SWITCH, KIND_IDL_INTERFACE,
                           KIND_IDL_MEMBER, KIND_MOJO_INTERFACE, KIND_MOJO_METHOD)),
    (KIND_GROUP_SURFACE, (KIND_WEBUI_ROUTE, KIND_WEBUI_CONTROL, KIND_WEBUI_GATE,
                          KIND_FLAG_ENTRY)),
)


# What a change in each group *means*, in one sentence. Kept beside the groups
# rather than in a renderer because both reports print it and a reader who only
# sees the group name learns nothing from it.
KIND_GROUP_MEANINGS = {
    KIND_GROUP_SWITCH: "The only group where a change moves behaviour on its "
                       "own. What our build does is different after this.",
    KIND_GROUP_CONTRACT: "A change here breaks something outside the binary, "
                         "and silently: data already on a user's disk, launch "
                         "scripts, live websites, the other process.",
    KIND_GROUP_SURFACE: "A change here moves what the user sees, or moves the "
                        "date something is scheduled to be removed.",
}


def group_of(kind: str) -> str:
    """Which of the three groups a fact kind belongs to."""
    for name, kinds in KIND_GROUPS:
        if kind in kinds:
            return name
    return ""


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
# the diff. Scoring and both renderers describe a change in words that are only
# true for one of the two, so each of them has to be told which comparison it
# is looking at.
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
    # "path:line" per side. Separate from `paths` because a downstream profile
    # matches path prefixes against that list, and because a reader needs the
    # place, not just the file: content_features.cc declares nearly two hundred
    # features, which is the same reason symbol evidence outranks path evidence
    # when scoring. Every extractor had been computing a line number and
    # nothing carried it past the snapshot.
    locations: List[str] = field(default_factory=list)
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
            "locations": self.locations,
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
            locations=d.get("locations", []) or [],
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
    """Drop duplicate uids, keeping the declaration lowest in path order.

    Chromium declares the same thing in more than one place far more often than
    it looks: 228 uids in the M151 tree, and 68 of those disagree on an
    attribute the diff compares. ``switch:disabled`` is declared by three
    different C++ constants in three files, none of them the same switch.

    Which copy survives therefore has to be decided by a rule, not by arrival.
    It used to be "first seen", and first was whatever ``os.walk`` handed back
    first -- filesystem order, which differs between machines and between the
    two trees of a single comparison. Diffing the M151 tree against itself under
    two walk orders produced 68 changes describing nothing, topped by a
    ``web_api_signature_change`` at severity 50.

    Lowest ``(path, line)`` is arbitrary in the same way "first" was, but it is
    a property of the tree rather than of the machine reading it, so two runs
    anywhere agree. The walk is sorted as well, so ordering never reaches here.
    """
    best: Dict[str, Fact] = {}
    for f in facts:
        current = best.get(f.uid)
        if current is None or (f.path, f.line) < (current.path, current.line):
            best[f.uid] = f
    return sorted(best.values(), key=lambda f: (f.kind, f.key))
