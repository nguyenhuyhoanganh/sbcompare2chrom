"""Empty an output folder before a run writes into it, so it only holds the latest result."""
from __future__ import annotations

import shutil
from pathlib import Path

from sbtest.utils import log


def clear_dir(folder: Path, root: Path) -> list[Path]:
    """Delete everything inside ``folder`` (kept itself). ``folder`` must lie inside ``root``
    (the artifacts folder), so a misconfigured path never wipes the repo. Returns what could
    not be removed (Windows: a file still open in a viewer, a browser not closed)."""
    folder, root = folder.resolve(), root.resolve()
    if folder == root or root not in folder.parents:
        raise ValueError(f"refusing to clear {folder}: not inside {root}")
    failed = []
    for p in sorted(folder.glob("*")) if folder.is_dir() else []:
        try:
            shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
        except OSError as e:
            log.warning("could not remove %s: %s", p, e)
            failed.append(p)
    folder.mkdir(parents=True, exist_ok=True)
    return failed
