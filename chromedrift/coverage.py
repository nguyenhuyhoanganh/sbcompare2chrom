"""Find where the fork shadows upstream rather than replacing it.

A vendor fork of this shape does not overwrite Chromium's code. It merges the
new Chromium in whole, keeps its own implementation beside it, and chooses
between them at build time::

    #if defined(SBROWSER_CUSTOM_DOWNLOADS)
      ... the vendor's implementation, which is what actually ships ...
    #else
      ... Chromium's, untouched since the merge ...
    #endif

Both are present, so a value comparison finds nothing: upstream's branch really
is identical to upstream. The branch that runs is the other one.

That is why "our fork matches M148" can be true and misleading at the same
time. The question worth answering is not whether upstream's code is intact --
after a merge it always is -- but **which parts of it are shadowed**, and how
old the shadow is.

This module answers the first half by reading the guards recorded during
extraction. The second half is `provenance.py`: once you know a declaration is
shadowed, comparing the vendor's side against a series of upstream versions
says which milestone the cover was written against.

Marker names cannot be guessed, so the profile declares them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .diff import meaningful_attrs
from .model import Fact, Snapshot

# Classification of one upstream fact against the fork.
UNTOUCHED = "untouched"      # present, unguarded, same value
SHADOWED = "shadowed"        # a vendor build flag chooses an alternative
MODIFIED = "modified"        # present and unguarded, but the value differs
ABSENT = "absent"            # upstream has it, the fork does not
VENDOR_ONLY = "vendor_only"  # only the fork has it, and it looks like ours
ORPHANED = "orphaned"        # only the fork has it, and nothing says it is ours

STATES = (UNTOUCHED, SHADOWED, MODIFIED, ABSENT, VENDOR_ONLY, ORPHANED)

STATE_LABELS = {
    UNTOUCHED: "Untouched — upstream's declaration, no vendor guard",
    SHADOWED: "Shadowed — a vendor build flag selects our version instead",
    MODIFIED: "Modified — no guard, but the value differs from upstream",
    ABSENT: "Absent — upstream has it, we do not",
    VENDOR_ONLY: "Ours only — vendor naming or guard confirms we wrote it",
    ORPHANED: "Orphaned — we have it, upstream does not, and nothing marks it "
              "as ours: most likely upstream deleted it and our merge kept it",
}


@dataclass
class VendorMarkers:
    """How to recognise the vendor's own code. Declared in the profile.

    Naming differs per vendor, so nothing here is guessed. An empty marker set
    disables the analysis rather than inventing matches.
    """

    macros: List[str] = field(default_factory=list)          # SBROWSER, SAMSUNG
    symbol_prefixes: List[str] = field(default_factory=list)  # kSbrowser
    path_markers: List[str] = field(default_factory=list)     # sbrowser/

    @classmethod
    def from_profile(cls, profile: dict) -> "VendorMarkers":
        raw = (profile or {}).get("vendor_markers") or {}
        return cls(
            macros=[m.upper() for m in raw.get("macros", [])],
            symbol_prefixes=list(raw.get("symbol_prefixes", [])),
            path_markers=[p.lower() for p in raw.get("path_markers", [])],
        )

    def configured(self) -> bool:
        return bool(self.macros or self.symbol_prefixes or self.path_markers)

    def guard_is_ours(self, condition: str) -> bool:
        upper = condition.upper()
        return any(m in upper for m in self.macros)

    def symbol_is_ours(self, fact: Fact) -> bool:
        var = str(fact.attrs.get("var", ""))
        return any(fact.name.startswith(p.lstrip("k")) or var.startswith(p)
                   for p in self.symbol_prefixes)

    def path_is_ours(self, path: str) -> bool:
        low = (path or "").lower()
        return any(m in low for m in self.path_markers)


@dataclass
class Verdict:
    uid: str
    kind: str
    key: str
    state: str
    guards: List[str] = field(default_factory=list)
    path: str = ""

    def to_dict(self) -> dict:
        return {"uid": self.uid, "kind": self.kind, "key": self.key,
                "state": self.state, "guards": self.guards, "path": self.path}


@dataclass
class CoverageReport:
    fork_ref: str
    upstream_ref: str
    verdicts: List[Verdict] = field(default_factory=list)
    markers_configured: bool = True

    def counts(self) -> Dict[str, int]:
        out = {s: 0 for s in STATES}
        for v in self.verdicts:
            out[v.state] = out.get(v.state, 0) + 1
        return out

    def shadowed(self) -> List[Verdict]:
        return [v for v in self.verdicts if v.state == SHADOWED]

    def guards_used(self) -> Dict[str, int]:
        """Which vendor flags do the shadowing, and how much each covers."""
        out: Dict[str, int] = {}
        for v in self.shadowed():
            for g in v.guards:
                out[g] = out.get(g, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def to_dict(self) -> dict:
        return {
            "fork_ref": self.fork_ref, "upstream_ref": self.upstream_ref,
            "markers_configured": self.markers_configured,
            "counts": self.counts(), "guards_used": self.guards_used(),
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


def _vendor_guards(fact: Fact, markers: VendorMarkers) -> List[str]:
    conditions = fact.attrs.get("conditions") or []
    if not isinstance(conditions, list):
        return []
    return [c for c in conditions if markers.guard_is_ours(str(c))]


def analyze(fork: Snapshot, upstream: Snapshot,
            markers: VendorMarkers) -> CoverageReport:
    report = CoverageReport(fork_ref=fork.ref, upstream_ref=upstream.ref,
                            markers_configured=markers.configured())
    if not markers.configured():
        return report

    fork_index = fork.index()
    up_index = upstream.index()

    for uid, ours in fork_index.items():
        guards = _vendor_guards(ours, markers)
        theirs = up_index.get(uid)

        if theirs is None:
            # Only ours -- but for two very different reasons. A vendor guard,
            # a vendor symbol prefix or a vendor path says we wrote it. Nothing
            # at all saying so usually means the opposite: upstream deleted the
            # declaration and our merge kept the old one alive. That is debt,
            # not a decision, and collapsing both into "ours only" hides it.
            if guards or markers.symbol_is_ours(ours) or markers.path_is_ours(ours.path):
                state = VENDOR_ONLY
            else:
                state = ORPHANED
        elif guards:
            # The value may match upstream exactly and still not be what runs.
            state = SHADOWED
        elif meaningful_attrs(ours) != meaningful_attrs(theirs):
            # Compare everything the diff would compare, not just the global
            # default. A fork that overrides only the `#if BUILDFLAG(IS_WIN)`
            # branch leaves default_state identical -- and that is precisely
            # the override this tool exists to find.
            state = MODIFIED
        else:
            state = UNTOUCHED

        report.verdicts.append(Verdict(uid=uid, kind=ours.kind, key=ours.key,
                                       state=state, guards=guards,
                                       path=ours.path))

    for uid, theirs in up_index.items():
        if uid not in fork_index:
            report.verdicts.append(Verdict(uid=uid, kind=theirs.kind,
                                           key=theirs.key, state=ABSENT,
                                           path=theirs.path))

    report.verdicts.sort(key=lambda v: (STATES.index(v.state), v.kind, v.key))
    return report


def summarize(report: CoverageReport, limit: int = 15) -> List[str]:
    if not report.markers_configured:
        return ["vendor_markers not configured in the profile; "
                "shadow analysis skipped. Without them a shadowed declaration "
                "is indistinguishable from an untouched one."]
    counts = report.counts()
    lines = [f"{len(report.verdicts)} declarations compared "
             f"({report.fork_ref} vs {report.upstream_ref})"]
    for state in STATES:
        if counts.get(state):
            lines.append(f"  {state:12s} {counts[state]:6d}  {STATE_LABELS[state]}")
    guards = report.guards_used()
    if guards:
        lines.append("  vendor flags doing the shadowing:")
        for g, n in list(guards.items())[:limit]:
            lines.append(f"    {g[:56]:56s} covers {n}")
    return lines
