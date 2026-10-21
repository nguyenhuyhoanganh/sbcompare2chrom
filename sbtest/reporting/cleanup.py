"""Remove the outputs of earlier runs so artifacts/ holds only the latest result."""
from __future__ import annotations

import shutil
from pathlib import Path

from sbtest.utils import log


def clean_previous_runs(artifacts: Path, keep: int = 1, current: Path | None = None) -> list[Path]:
    """Delete old ``runs/<ts>/`` folders, keeping the ``keep`` newest ones (``current``, the run
    about to start, counts as one), plus the chromedriver logs and leftover profiles of earlier
    runs. ``keep <= 0`` keeps everything. Returns what could not be removed (file in use)."""
    if keep <= 0:
        return []
    runs = artifacts / "runs"
    others = sorted((p for p in runs.glob("*") if p.is_dir() and p != current),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    old = others[keep - 1:] if current else others[keep:]
    targets = old + sorted((artifacts / "logs").glob("*.log")) + sorted(p for p in (artifacts / "profiles").glob("*")
                                                                       if p.is_dir())
    failed = []
    for p in targets:
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        except OSError as e:   # Windows: a file still open (report in a viewer, browser not closed)
            log.warning("could not remove %s: %s", p, e)
            failed.append(p)
    return failed
