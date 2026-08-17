"""Build and cache a Snapshot for one Chromium ref.

Snapshots are the expensive artifact (network-bound) and the stable one: for a
released tag the content never changes, so a snapshot is cached on disk
forever and every later stage is cheap to re-run.  This is what makes the tool
usable interactively -- you iterate on scoring and reporting against a warm
cache, not against gitiles.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Sequence

from .acquire import (
    AcquireError,
    GitilesSource,
    LocalSource,
    Source,
    milestone_info,
    resolve_ref,
)
from .extract import run_on_tree
from .model import SCHEMA_VERSION, Snapshot, read_json, write_json
from .targets import get_targets


def snapshot_path(cache_dir: str, ref: str, target_set: str,
                  partitions: Optional[Sequence[str]] = None,
                  complete: bool = False) -> str:
    """Cache path.  The partition belongs in the key.

    A partitioned snapshot covers a fraction of the surface. Keying only on
    the target-set name would let one be reused as if it were the full run --
    the same mistake that once made a "minimal" snapshot silently hold the
    full fact set, and later made a widened filter change nothing.
    """
    safe = ref.replace("/", "_").replace(":", "_")
    part = ("." + "+".join(sorted(partitions))) if partitions else ""
    # A complete partition covers strictly more than a filtered one of the same
    # name, so it cannot share a key with it.
    part += ".complete" if complete else ""
    return os.path.join(cache_dir, "snapshots", f"{safe}.{target_set}{part}.json")


def tree_path(cache_dir: str, ref: str) -> str:
    safe = ref.replace("/", "_").replace(":", "_")
    return os.path.join(cache_dir, "trees", safe)


def build_snapshot(ref: str, cache_dir: str, target_set: str = "default",
                   platform: str = "Windows", local_src: Optional[str] = None,
                   refresh: bool = False, partitions: Optional[Sequence[str]] = None,
                   complete: bool = False, log=print) -> Snapshot:
    """Resolve a ref, materialize its target files, and extract facts."""
    resolved, milestone = resolve_ref(ref, platform=platform)
    out_path = snapshot_path(cache_dir, resolved, target_set, partitions,
                             complete)

    if os.path.exists(out_path) and not refresh:
        cached = read_json(out_path)
        if cached.get("schema") == SCHEMA_VERSION:
            log(f"  snapshot cache hit: {out_path}")
            return Snapshot.from_dict(cached)
        log(f"  snapshot cache stale (schema {cached.get('schema')} != "
            f"{SCHEMA_VERSION}), rebuilding")

    targets = get_targets(target_set, partitions, complete)
    root = tree_path(cache_dir, resolved)
    os.makedirs(root, exist_ok=True)

    source: Source
    if local_src:
        log(f"  source: local checkout {local_src}")
        source = LocalSource(resolved, local_src, log=log)
    else:
        log(f"  source: gitiles {resolved} ({len(targets)} targets)")
        source = GitilesSource(resolved, cache_dir, refresh=refresh, log=log)

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
    allow_prefixes = {t.path.rstrip("/") + "/" for t in targets if t.kind == "tree"}

    log(f"  extracting from {root} ...")
    facts, stats = run_on_tree(root, log=log, allow_paths=allow_paths,
                               allow_prefixes=allow_prefixes)

    snap = Snapshot(
        ref=resolved,
        milestone=milestone,
        facts=facts,
        meta={
            "target_set": target_set,
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
