"""Prove what the target set is missing, instead of guessing at it.

The target list in `targets.py` is curated by hand, and curation has failed
twice already: once missing `chrome_features.cc` and 12 other files holding 964
declarations, once missing Lit templates. Each time the fix was to add more
files and hope. That is not a method, because it has no endpoint -- there is no
moment at which you can say the list is complete.

This module supplies the endpoint. A **blobless clone** downloads Chromium's
complete file tree without any file contents:

    git clone --filter=blob:none --no-checkout --depth 1 --branch <tag>

Measured on M151: **4.8 seconds, 18 MB, 498,082 files**. From that listing,
every file that could plausibly declare a feature can be enumerated by name --
464 non-test `.cc` files at M151 -- and compared against what the targets
actually fetch.

The answer stops being "I think we have enough" and becomes a number, with the
missing files named.

Discovery only. Fetching content still goes through `acquire.py`; a sparse
checkout of the candidates proved far slower than the archive downloads.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

from .acquire import GITILES_BASE
from .extract.base_features import feature_name_from_var as _bare
from .targets import could_declare, get_targets



@dataclass
class CatalogEntry:
    path: str
    covered: bool = False
    reason: str = ""


@dataclass
class CatalogReport:
    ref: str
    total_files: int = 0
    candidates: List[CatalogEntry] = field(default_factory=list)
    target_paths: List[str] = field(default_factory=list)
    partitions: List[str] = field(default_factory=list)

    def covered(self) -> List[CatalogEntry]:
        return [c for c in self.candidates if c.covered]

    def missing(self) -> List[CatalogEntry]:
        return [c for c in self.candidates if not c.covered]

    def coverage_pct(self) -> int:
        if not self.candidates:
            return 0
        return len(self.covered()) * 100 // len(self.candidates)

    def missing_by_area(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for entry in self.missing():
            top = entry.path.split("/")[0]
            out[top] = out.get(top, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "partitions": self.partitions,
            "total_files": self.total_files,
            "candidates": len(self.candidates),
            "covered": len(self.covered()),
            "missing": len(self.missing()),
            "coverage_pct": self.coverage_pct(),
            "missing_by_area": self.missing_by_area(),
            "missing_paths": [c.path for c in self.missing()],
        }


def list_tree(ref: str, workdir: Optional[str] = None,
              base: str = GITILES_BASE, log=lambda m: None) -> List[str]:
    """Every path in Chromium at ``ref``, via a blobless clone.

    Downloads the commit and tree objects but no file contents, which is what
    keeps this to seconds rather than hours.
    """
    tmp = workdir or tempfile.mkdtemp(prefix="chromiumdiff-catalog-")
    repo = os.path.join(tmp, "src")
    branch = ref.split("/")[-1] if ref.startswith("refs/") else ref

    if not os.path.isdir(os.path.join(repo, ".git")):
        log(f"  blobless clone of {branch} (no file contents) ...")
        cmd = ["git", "clone", "--filter=blob:none", "--no-checkout",
               "--depth", "1", "--branch", branch, f"{base}.git", repo]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            raise RuntimeError(
                f"blobless clone failed for {branch}: "
                f"{result.stderr.strip()[:300]}")

    listing = subprocess.run(
        ["git", "-C", repo, "ls-tree", "-r", "HEAD", "--name-only"],
        capture_output=True, text=True, timeout=600)
    if listing.returncode != 0:
        raise RuntimeError(f"ls-tree failed: {listing.stderr.strip()[:300]}")

    paths = [p for p in listing.stdout.splitlines() if p]
    if workdir is None:
        shutil.rmtree(tmp, ignore_errors=True)
    return paths


def covered_by_targets(path: str, targets: Sequence) -> bool:
    """Would this target set actually put this file on disk?

    Answered by `targets.reaches`, the single definition of scope, rather than
    by a copy kept here. Two things went wrong while this module had its own:

    A tree target carries a suffix filter as well as a path, and matching on
    the path alone ignores it. `chrome/browser/ui/webui` is fetched for `.cc`
    only, so a header underneath it is never written to disk and never read --
    but a prefix-only check counted it as covered. At M151 that was 5 files
    reported as read that no run reads, in the one command whose job is to
    measure the gap, and the error pointed the reassuring way.

    Nested targets also have to be tried in full: a path excluded by the
    narrow filter on `chrome/browser/ui/webui` may still be reached by the
    wide one on `chrome/browser`.
    """
    from .targets import reaches, scope_of

    files, trees = scope_of(targets)
    return reaches(path, files, trees)


def target_paths(target_set: str = "default",
                 partitions: Optional[Sequence[str]] = None,
                 complete: bool = False) -> List[str]:
    """The paths this target set names, for the report's own record."""
    return sorted(t.path for t in get_targets(target_set, partitions, complete))


def analyze(paths: Sequence[str], ref: str, target_set: str = "default",
            include_irrelevant: bool = False,
            partitions: Optional[Sequence[str]] = None,
            complete: bool = False) -> CatalogReport:
    # `complete` has to be passed through, not dropped. It replaces the curated
    # file list with whole directory roots, so measuring a `--complete` run
    # against the list it does not use reports every file it does fetch as
    # missing.
    targets = get_targets(target_set, partitions, complete)
    report = CatalogReport(ref=ref, total_files=len(paths),
                           partitions=sorted(partitions) if partitions else [],
                           target_paths=target_paths(target_set, partitions,
                                                     complete))

    for path in paths:
        # `could_declare` is the same rule the per-run coverage line uses, so
        # the two numbers describe the same population. It knows both pref
        # naming conventions, and that pref keys live in headers as often as
        # in .cc files.
        note = could_declare(path, include_other_platforms=include_irrelevant)
        if not note:
            continue
        report.candidates.append(
            CatalogEntry(path=path, reason=note,
                         covered=covered_by_targets(path, targets)))

    report.candidates.sort(key=lambda c: (c.covered, c.path))
    return report


def summarize(report: CatalogReport, limit: int = 30) -> List[str]:
    scope = ("the current target set" if not report.partitions
             else f"partition(s) {'+'.join(report.partitions)}")
    lines = [
        f"{report.total_files:,} files at {report.ref}",
        f"{len(report.candidates)} could declare features "
        f"(by filename, excluding tests and platforms we do not ship)",
        f"{len(report.covered())} covered by {scope} "
        f"({report.coverage_pct()}%)",
        f"{len(report.missing())} not fetched",
    ]
    if report.partitions:
        lines.append("  (a partitioned run covers less by design; this "
                     "percentage describes that run, not the full target set)")
    by_area = report.missing_by_area()
    if by_area:
        lines.append("")
        lines.append("missing, by top-level directory:")
        for area, n in list(by_area.items())[:limit]:
            lines.append(f"  {area:28s} {n}")
    return lines


# ---------------------------------------------------------------------------
# Reference closure: the only honest form of "did we get everything"
#
# File-level coverage answers "did we fetch the files someone listed". It cannot
# answer "did we fetch the files this surface actually depends on", because that
# depends on what the surface references, which is only knowable after
# extraction.
#
# The declarative layer is a graph with links the data itself declares:
#
#     webui_route --guards--> webui_gate --features--> base_feature
#     webui_control --pref--> pref
#     blink_runtime --base_feature--> base_feature
#     feature_param --feature--> base_feature
#
# So completeness becomes checkable rather than hoped for: walk every declared
# edge and report the ones whose target is not in the snapshot. An empty list is
# a proof that the extracted surface is self-contained. A non-empty one names
# the exact declarations to add, instead of leaving "is this enough?" as a
# feeling.
# ---------------------------------------------------------------------------

_DANGLING_LABEL = {
    "gate": "page guard with no handler declaring it",
    "feature": "flag referenced by a gate but declared nowhere we fetched",
    "pref": "preference bound by a control but declared nowhere we fetched",
    "blink_feature": "Blink flag naming a base::Feature we did not fetch",
    "param_owner": "feature parameter whose owning feature we did not fetch",
}


def unresolved_references(snapshot) -> Dict[str, List[str]]:
    """Declared links whose target is absent from this snapshot."""
    by_kind: Dict[str, Set[str]] = {}
    for fact in snapshot.facts:
        by_kind.setdefault(fact.kind, set()).add(fact.key)

    # A route names the bare loadTimeData key; a gate's own key is qualified
    # by the handler that sets it, so the closure resolves against the bare
    # one. Reading the qualified key here would report every guard in the tree
    # as unresolved.
    gates = {(f.attrs.get("data_key") or f.name)
             for f in snapshot.facts if f.kind == "webui_gate"}
    features = by_kind.get("base_feature", set())
    prefs = by_kind.get("pref", set())
    out: Dict[str, Set[str]] = {k: set() for k in _DANGLING_LABEL}

    for fact in snapshot.facts:
        a = fact.attrs
        if fact.kind == "webui_route":
            for guard in a.get("guards") or []:
                if guard not in gates:
                    out["gate"].add(guard)
        elif fact.kind == "webui_gate":
            for var in a.get("features") or []:
                if _bare(var) not in features:
                    out["feature"].add(_bare(var))
        elif fact.kind == "webui_control":
            pref = a.get("pref") or ""
            if pref and pref not in prefs:
                out["pref"].add(pref)
        elif fact.kind == "blink_runtime_feature":
            declared = a.get("base_feature")
            if isinstance(declared, str) and declared and declared != "none":
                if _bare(declared) not in features:
                    out["blink_feature"].add(_bare(declared))
        elif fact.kind == "feature_param":
            owner = a.get("feature") or ""
            if owner and owner not in features:
                out["param_owner"].add(owner)

    return {k: sorted(v) for k, v in out.items() if v}


def summarize_closure(dangling: Dict[str, List[str]], limit: int = 8) -> List[str]:
    if not dangling:
        return ["reference closure: complete — every declared link resolves "
                "inside this snapshot"]
    total = sum(len(v) for v in dangling.values())
    lines = [f"reference closure: {total} unresolved reference(s)"]
    for kind, names in sorted(dangling.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {len(names):4d}  {_DANGLING_LABEL[kind]}")
        for name in names[:limit]:
            lines.append(f"          {name}")
        if len(names) > limit:
            lines.append(f"          ... and {len(names) - limit} more")
    return lines


# ---------------------------------------------------------------------------
# Scope violations: the check that would have caught the tree-filter leak
#
# The tree cache is shared per ref across target sets and partitions, so a wider
# earlier run leaves files behind. If the reading side does not apply the same
# filter the fetching side did, those leftovers are extracted -- and the two
# refs almost never carry the same leftovers, so the difference surfaces as a
# mass deletion of whatever the other side happens to lack.
#
# Measured: 103 stray .mojom files under chrome/browser/ui/webui in the M148
# tree and none in the M151 tree produced 803 "Mojo method removed" findings at
# severity 80 -- the highest the tool assigns, at the top of the report,
# describing nothing that happened.
#
# Comparing the two sides for symmetry was the first thing tried, and it cannot
# work: a file type legitimately vanishes when Chromium migrates one (the
# desktop WebUI move from Polymer `.html` to Lit `.html.ts` empties a suffix
# inside a root), and legitimately appears when a surface is new. Both look
# exactly like a leak.
#
# Asking a single snapshot whether it read anything its own target set never
# allowed has no such ambiguity. It needs no second snapshot, it names the
# offending files, and it is exact rather than heuristic.
# ---------------------------------------------------------------------------


def declared_scope(snapshot) -> tuple:
    """(exact files, {tree prefix: suffix filter}) this snapshot was allowed."""
    meta = snapshot.meta or {}
    targets = get_targets(meta.get("target_set", "default"),
                          meta.get("partitions") or None,
                          bool(meta.get("complete")))
    from .targets import scope_of
    files, trees = scope_of(targets)
    return files, dict(trees)


def scope_violations(snapshot) -> List[str]:
    """Files this snapshot drew facts from that its target set never allowed."""
    try:
        files, trees = declared_scope(snapshot)
    except (KeyError, ValueError):
        return []
    from .targets import reaches
    pairs = list(trees.items())
    return sorted({f.path for f in snapshot.facts
                   if f.path and not reaches(f.path, files, pairs)})


def summarize_violations(snapshot, violations: List[str],
                         limit: int = 6) -> List[str]:
    if not violations:
        return ["scope: ok — every fact came from a file the target set asked for"]
    by_suffix: Dict[str, int] = {}
    for path in violations:
        name = path.rsplit("/", 1)[-1]
        suffix = "." + name.split(".", 1)[1] if "." in name else "(none)"
        by_suffix[suffix] = by_suffix.get(suffix, 0) + 1
    lines = [f"scope: {len(violations)} FILE(S) OUT OF SCOPE in {snapshot.ref} — "
             f"facts were read from files this target set never asked for"]
    for suffix, n in sorted(by_suffix.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {n:5d}  *{suffix}")
    for path in violations[:limit]:
        lines.append(f"          {path}")
    if len(violations) > limit:
        lines.append(f"          ... and {len(violations) - limit} more")
    lines.append("      This is a stale tree cache, not a Chromium change. "
                 "Re-run that side with --refresh; diffing it would report the "
                 "extra files as a mass deletion on the other side.")
    return lines
