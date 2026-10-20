"""Map test code to the numbered steps of the test case document.

    with step("1. Open the bookmark manager"):
        pages.bookmarks.open()
    with step("2. Add a bookmark", expected="Bookmark shows in the list"):
        ...

Steps are logged, written to the report, and a failure says *which step* failed.
"""
from __future__ import annotations

import contextlib
import time

from sbtest.utils import log

_current: list[dict] = []


def reset() -> None:
    _current.clear()


def history() -> list[dict]:
    return list(_current)


@contextlib.contextmanager
def step(title: str, expected: str = ""):
    rec = {"title": title, "expected": expected, "status": "running", "start": time.time()}
    _current.append(rec)
    log.info("STEP %s", title)
    try:
        yield rec
    except BaseException as e:
        rec["status"] = "failed"
        rec["error"] = f"{type(e).__name__}: {e}"
        if hasattr(e, "add_note"):
            e.add_note(f"[sbtest] failed at step: {title}" + (f" | expected: {expected}" if expected else ""))
        raise
    else:
        rec["status"] = "passed"
    finally:
        rec["duration"] = round(time.time() - rec["start"], 2)
