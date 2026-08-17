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
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set

from .acquire import GITILES_BASE
from .targets import get_targets

# Files whose name suggests they declare features, switches or field trials.
CANDIDATE_RE = re.compile(
    r"(features|feature_list|switches|fieldtrial|field_trial|flags)\.(cc|h)$")

# Test files declare features that drive tests and ship to nobody.
TEST_PATH_RE = re.compile(
    r"(unittest|browsertest|_test\.|/test/|/tests/|/testing/|test_util)")

# Trees a desktop product never compiles.
IRRELEVANT_RE = re.compile(r"^(ash|chromeos|ios|fuchsia|android_webview)/")


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
    tmp = workdir or tempfile.mkdtemp(prefix="chromedrift-catalog-")
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


def target_prefixes(target_set: str = "default") -> Set[str]:
    """What the fetch list actually reaches: exact files plus tree roots."""
    out: Set[str] = set()
    for target in get_targets(target_set):
        out.add(target.path if target.kind == "file" else target.path.rstrip("/") + "/")
    return out


def _is_covered(path: str, prefixes: Iterable[str]) -> bool:
    for prefix in prefixes:
        if prefix.endswith("/"):
            if path.startswith(prefix):
                return True
        elif path == prefix:
            return True
    return False


def analyze(paths: Sequence[str], ref: str, target_set: str = "default",
            include_irrelevant: bool = False) -> CatalogReport:
    prefixes = target_prefixes(target_set)
    report = CatalogReport(ref=ref, total_files=len(paths),
                           target_paths=sorted(prefixes))

    for path in paths:
        if not path.endswith(".cc"):
            continue
        if not CANDIDATE_RE.search(path):
            continue
        if TEST_PATH_RE.search(path):
            continue
        if not include_irrelevant and IRRELEVANT_RE.match(path):
            continue
        report.candidates.append(
            CatalogEntry(path=path, covered=_is_covered(path, prefixes)))

    report.candidates.sort(key=lambda c: (c.covered, c.path))
    return report


def summarize(report: CatalogReport, limit: int = 30) -> List[str]:
    lines = [
        f"{report.total_files:,} files at {report.ref}",
        f"{len(report.candidates)} could declare features "
        f"(by filename, excluding tests and platforms we do not ship)",
        f"{len(report.covered())} covered by the current target set "
        f"({report.coverage_pct()}%)",
        f"{len(report.missing())} not fetched",
    ]
    by_area = report.missing_by_area()
    if by_area:
        lines.append("")
        lines.append("missing, by top-level directory:")
        for area, n in list(by_area.items())[:limit]:
            lines.append(f"  {area:28s} {n}")
    return lines
