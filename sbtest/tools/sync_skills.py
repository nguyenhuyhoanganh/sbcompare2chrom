"""Mirror the agent skills from .agents/skills/ (the source, Agent Skills standard) into
.claude/skills/ (where Claude Code loads them). Edit only .agents/skills/, then run:

    python -m sbtest.tools.sync_skills            # copy, remove what no longer exists
    python -m sbtest.tools.sync_skills --check    # exit 1 if the copy is out of date

A copy instead of a symlink: git on Windows checks symlinks out as plain text files
unless Developer Mode and core.symlinks are on.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from sbtest.config import ROOT

SOURCE = ROOT / ".agents" / "skills"
MIRRORS = [ROOT / ".claude" / "skills"]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def _files(folder: Path) -> dict[str, bytes]:
    if not folder.is_dir():
        return {}
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def diff(source: Path = SOURCE, mirror: Path = MIRRORS[0]) -> list[str]:
    """Paths that differ between the source and a mirror ('+' missing, '-' extra, '~' changed)."""
    src, dst = _files(source), _files(mirror)
    out = [f"+ {p}" for p in src if p not in dst]
    out += [f"- {p}" for p in dst if p not in src]
    out += [f"~ {p}" for p in src if p in dst and src[p] != dst[p]]
    return sorted(out, key=lambda s: s[2:])


def sync(source: Path = SOURCE, mirror: Path = MIRRORS[0]) -> None:
    if mirror.exists():
        shutil.rmtree(mirror)
    shutil.copytree(source, mirror, ignore=IGNORE)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only report differences")
    args = ap.parse_args(argv)
    stale = False
    for mirror in MIRRORS:
        changes = diff(SOURCE, mirror)
        rel = mirror.relative_to(ROOT).as_posix()
        if not changes:
            print(f"{rel}: up to date")
            continue
        if args.check:
            stale = True
            print(f"{rel}: out of date, run python -m sbtest.tools.sync_skills")
            print("\n".join(f"  {c}" for c in changes))
        else:
            sync(SOURCE, mirror)
            print(f"{rel}: synced ({len(changes)} change(s))")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
