"""Build and cache a Snapshot for one Chromium ref.

Snapshots are the expensive artifact (network-bound) and the stable one: for a
released tag the content never changes, so a snapshot is cached on disk
forever and every later stage is cheap to re-run.  This is what makes the tool
usable interactively -- you iterate on scoring and reporting against a warm
cache, not against gitiles.
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional, Sequence, Tuple

from .acquire import (
    safe_name,
    AcquireError,
    GitilesSource,
    LocalSource,
    Source,
    milestone_info,
    resolve_ref,
)
from .extract import run_on_tree
from .model import SCHEMA_VERSION, Snapshot, read_json, write_json
from .targets import coverage_against, discover_candidates, get_targets


def snapshot_path(cache_dir: str, ref: str, target_set: str,
                  partitions: Optional[Sequence[str]] = None,
                  complete: bool = False) -> str:
    """Cache path.  The partition belongs in the key.

    A partitioned snapshot covers a fraction of the surface. Keying only on
    the target-set name would let one be reused as if it were the full run --
    the same mistake that once made a smoke-run snapshot silently hold the
    full fact set, and later made a widened filter change nothing.
    """
    safe = safe_name(ref)
    part = ("." + "+".join(sorted(partitions))) if partitions else ""
    # A complete partition covers strictly more than a filtered one of the same
    # name, so it cannot share a key with it.
    part += ".complete" if complete else ""
    return os.path.join(cache_dir, "snapshots", f"{safe}.{target_set}{part}.json")


def tree_path(cache_dir: str, ref: str) -> str:
    safe = safe_name(ref)
    return os.path.join(cache_dir, "trees", safe)


def _partition_prefixes(partitions: Sequence[str]) -> Tuple[str, ...]:
    from .targets import PARTITIONS, PARTITION_CORE
    out = tuple(PARTITION_CORE)
    for name in partitions:
        out += PARTITIONS[name]
    return out


def measure_coverage(candidates: dict, memberships: dict, targets: Sequence,
                     partitions: Optional[Sequence[str]] = None
                     ) -> Tuple[dict, Optional[dict]]:
    """What a target set reads of the tree, and a partition of its own roots.

    Returns `(tree, own)`. `tree` counts every candidate in the tree,
    partitioned or not: it is the figure the scoring stage confirms a removal
    against, and a removal is an absence from the tree. A partition used to be
    measured against its own roots only, so `--partition downloads` read 2 of
    2 pref files there and, at M148 -> M151, confirmed six removals that were
    moves to files outside the partition. `own` is that roots-only figure --
    the one `--complete` makes 100% -- and None for an unpartitioned run,
    where the two are the same.
    """
    tree = coverage_against(candidates, targets, memberships)
    if not partitions:
        return tree, None
    prefixes = _partition_prefixes(partitions)
    own = coverage_against({p: v for p, v in candidates.items()
                            if p.startswith(prefixes)}, targets, memberships)
    return tree, own


def _partition_measured_on_its_roots(cached: dict) -> bool:
    """A cached partitioned snapshot whose coverage counts only its roots.

    The scorer confirms a removal against `coverage`, so reusing one would
    confirm removals the partition could not see. It is rebuilt rather than
    the schema bumped: the schema number also stamps every `report.json`, and
    the review commands re-read the report their ledger was built from, so a
    bump would stop every existing report and review from loading to fix a
    cache that only partitioned runs write. A snapshot with no coverage at
    all -- smoke -- has nothing to misread.
    """
    meta = cached.get("meta") or {}
    return (bool(meta.get("partitions")) and bool(meta.get("coverage"))
            and "partition_coverage" not in meta)


def build_snapshot(ref: str, cache_dir: str, target_set: str = "analysis",
                   platform: str = "Windows", local_src: Optional[str] = None,
                   refresh: bool = False, partitions: Optional[Sequence[str]] = None,
                   complete: bool = False, log=print) -> Snapshot:
    """Resolve a ref, materialize its target files, and extract facts."""
    resolved, milestone = resolve_ref(ref, platform=platform)
    out_path = snapshot_path(cache_dir, resolved, target_set, partitions,
                             complete)

    if os.path.exists(out_path) and not refresh:
        cached = read_json(out_path)
        if cached.get("schema") != SCHEMA_VERSION:
            log(f"  snapshot cache stale (schema {cached.get('schema')} != "
                f"{SCHEMA_VERSION}), rebuilding")
        elif _partition_measured_on_its_roots(cached):
            log("  snapshot cache stale (its partition coverage counted only "
                "the partition's own roots), rebuilding")
        else:
            log(f"  snapshot cache hit: {out_path}")
            return Snapshot.from_dict(cached)

    targets = get_targets(target_set, partitions, complete)
    root = tree_path(cache_dir, resolved)
    os.makedirs(root, exist_ok=True)

    source: Source
    if local_src:
        log(f"  source: local checkout {local_src}")
        source = LocalSource(resolved, local_src, log=log)
    else:
        log(f"  source: gitiles {resolved}")
        source = GitilesSource(resolved, cache_dir, refresh=refresh, log=log)

    # Ask this version's own tree what exists, and measure the target list
    # against it. A named list decays -- built as it stood at M130 and run at
    # M151 it misses 27% of the pref files and 34% of the feature files there --
    # and the decay is silent, because a file nobody listed is a file nobody
    # notices. Measuring costs one cached recursive listing per root; it does
    # not change what is fetched, only whether the gap is visible.
    coverage: dict = {}
    partition_coverage: Optional[dict] = None
    if target_set != "smoke":
        candidates, memberships = discover_candidates(source, log=log)
        coverage, partition_coverage = measure_coverage(
            candidates, memberships, targets, partitions)
        pct = coverage["read"] * 100 // max(1, coverage["candidates"])
        log(f"  coverage: reads {coverage['read']} of {coverage['candidates']} "
            f"files in this tree that could declare ({pct}% of files)")
        if partition_coverage is not None:
            own = partition_coverage
            log(f"  inside the partition's roots: reads {own['read']} of "
                f"{own['candidates']} "
                f"({own['read'] * 100 // max(1, own['candidates'])}% of files)")
        if coverage["missed"]:
            # A file count understates what a run gets, because the files
            # someone chose are the big ones: a minority of the files holds a
            # majority of the declarations, measured per surface in README's
            # target-set table. Both numbers are worth knowing and neither is
            # the whole answer, so the log gives the one that can be measured
            # without fetching, then says why the rest went unread.
            top = list(coverage["missed_by_directory"].items())[:3]
            log("    largest gaps: "
                + ", ".join(f"{d}/ ({n} files)" for d, n in top))
            # Say which of the two causes it is. There is no wider target set
            # to recommend, so naming one would be advice you cannot act on.
            log("    these include everything outside this run's partitions; "
                "drop --partition to read those" if partitions else
                "    no target reads these; the run cannot see them at all")
    log(f"  {len(targets)} targets")

    started = time.time()
    fetch_stats = source.materialize(targets, root)
    fetched = time.time() - started

    missing = [p for p, v in fetch_stats.items() if v == "missing"]
    if len(missing) == len(targets):
        raise AcquireError(
            f"every target missing for {resolved} -- is the ref valid? "
            f"(a proxy that answers 404 looks identical to a bad tag here)")
    if missing:
        # Not fatal: a target may genuinely not exist yet in an older
        # milestone. Silent, though, it is the difference between "this
        # feature was added" and "we never fetched the file declaring it".
        log(f"  ! {len(missing)} of {len(targets)} targets missing at "
            f"{resolved}: {', '.join(missing[:3])}"
            + (" ..." if len(missing) > 3 else ""))

    # Scope extraction to what this target set declared, not to whatever the
    # shared per-ref tree cache happens to hold from an earlier run.
    allow_paths = {t.path for t in targets if t.kind == "file"}
    # The suffix filter travels with the prefix. Without it, a file left in the
    # shared per-ref tree cache by an earlier, wider run gets extracted even
    # though this target set never asked for it.
    allow_prefixes = {t.path.rstrip("/") + "/": t.include
                      for t in targets if t.kind == "tree"}

    log(f"  extracting from {root} ...")
    facts, stats = run_on_tree(root, log=log, allow_paths=allow_paths,
                               allow_prefixes=allow_prefixes)

    snap = Snapshot(
        ref=resolved,
        milestone=milestone,
        facts=facts,
        meta={
            "target_set": target_set,
            # What the tree holds versus what this run read. Recorded so the
            # number travels with the snapshot instead of scrolling past.
            "coverage": {k: v for k, v in coverage.items()
                         if k != "missed_paths"},
            # What a partition read of its own roots, beside the tree figure
            # the scorer reads. Its presence also marks a partitioned snapshot
            # as measured against the tree.
            **({"partition_coverage":
                    {k: v for k, v in partition_coverage.items()
                     if k != "missed_paths"}}
               if partition_coverage is not None else {}),
            "uncovered_files": coverage.get("missed_paths", [])[:400],
            "partitions": sorted(partitions) if partitions else [],
            "complete": complete,
            "platform": platform,
            "fetch_seconds": round(fetched, 1),
            "fetch_stats": fetch_stats,
            "missing_targets": missing,
            "extract_stats": stats,
            "milestone_info": milestone_info(milestone) if milestone else {},
        },
    )
    write_json(out_path, snap.to_dict())
    log(f"  snapshot: {len(facts)} facts -> {out_path}")
    return snap


def load_snapshot(path: str) -> Snapshot:
    return Snapshot.from_dict(read_json(path))
