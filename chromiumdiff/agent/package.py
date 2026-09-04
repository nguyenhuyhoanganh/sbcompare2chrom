"""Fold the whole tool into one file somebody can be sent.

`zipapp` is in the standard library and makes a single runnable `.pyz` out of
a package directory, which is the only packaging this can honestly offer: no
build step, no third-party tool, and nothing to install on the machine that
receives it beyond the Python that machine already needs to run any of this.

Roughly 650 kB, and what it holds is the tool -- not the report, not the tree
cache. A report directory is megabytes and belongs to whoever made it; the
cache is gigabytes. The file is the program, and it is pointed at a directory
when it runs.

    python3 chromiumdiff.pyz serve --chat out/M148_to_M151

The skills go in when they are there. They are what the answers are supposed
to follow, and a copy of the tool that cannot find them is a copy that answers
from nothing.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipapp
from typing import List, Optional

MAIN = "chromiumdiff.cli:main"

# Never copied into the archive. `__pycache__` is bytecode for whichever
# interpreter happened to build the file, and it is both dead weight and a way
# for a stale `.pyc` to shadow the source beside it.
SKIP = ("__pycache__", ".git", ".DS_Store")


def build(target: str, source: Optional[str] = None,
          skills: Optional[str] = None) -> str:
    """Write a runnable archive at `target`, and return where it went."""
    package = source or os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    staging = tempfile.mkdtemp(prefix="chromiumdiff-package-")
    try:
        _copy(package, os.path.join(staging, "chromiumdiff"))
        if skills and os.path.isdir(skills):
            _copy(skills, os.path.join(staging, "skills"))
        target = target if target.endswith(".pyz") else target + ".pyz"
        parent = os.path.dirname(os.path.abspath(target))
        if parent:
            os.makedirs(parent, exist_ok=True)
        # `/usr/bin/env python3` rather than this interpreter's own path: the
        # archive is made to be sent somewhere, and a path to a Python in this
        # home directory is one the receiving machine does not have.
        zipapp.create_archive(staging, target=target, main=MAIN,
                              interpreter="/usr/bin/env python3")
        os.chmod(target, 0o755)
        return target
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _copy(source: str, target: str) -> None:
    shutil.copytree(source, target,
                    ignore=shutil.ignore_patterns(*SKIP, "*.pyc"))


def contents(archive: str) -> List[str]:
    """What ended up in it, for a caller that wants to check rather than hope."""
    import zipfile
    with zipfile.ZipFile(archive) as zf:
        return sorted(zf.namelist())
