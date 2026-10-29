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
# called with the step record when a step ends (set by the pytest plugin, e.g. screenshots)
_listener = None
# called with (step record, step number, mark number, mark) right BEFORE an interaction
_mark_listener = None
# a passed step lasts at least this long (seconds; config timeouts.min_step, set by the plugin)
_min_duration = 0.0


def reset() -> None:
    _current.clear()


def set_listener(fn, on_mark=None) -> None:
    """``fn(rec, n)`` when a step ends; ``on_mark(rec, n, i, mark)`` before each interaction."""
    global _listener, _mark_listener
    _listener, _mark_listener = fn, on_mark


def set_min_duration(seconds: float) -> None:
    """Every passed step takes at least ``seconds``: the browser UI settles (animations,
    bubbles, focus) before the next step, and a person can follow the run. 0 = no minimum."""
    global _min_duration
    _min_duration = max(0.0, float(seconds or 0))


def history() -> list[dict]:
    return list(_current)


def recording() -> bool:
    """True while step screenshots are taken (``--screenshot-steps``): only then do the web and
    native layers spend time measuring where they interact."""
    return _listener is not None


def mark(kind: str, label: str = "", web: tuple | None = None, screen: tuple | None = None) -> None:
    """Remember an interaction of the running step for its screenshot: ``kind`` ("click",
    "type", ...), a short ``label``, and where - ``web=(x, y, w, h, devicePixelRatio)`` in the
    page viewport, or ``screen=(left, top, right, bottom)`` in screen pixels (browser UI,
    Windows dialogs). Neither: listed on the picture without a frame (keyboard shortcuts)."""
    if _listener is None or not _current or _current[-1]["status"] != "running":
        return
    rec, m = _current[-1], {"kind": kind, "label": label[:40], "web": web, "screen": screen}
    rec.setdefault("marks", []).append(m)
    if _mark_listener is not None:
        try:
            _mark_listener(rec, len(_current), len(rec["marks"]), m)
        except Exception as e:  # noqa: BLE001 - evidence must never break a test
            log.warning("step mark listener failed: %s", e)


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
        left = _min_duration - (time.time() - rec["start"])
        if left > 0:   # a failed step does not wait: its evidence is collected right away
            time.sleep(left)
    finally:
        rec["duration"] = round(time.time() - rec["start"], 2)
        if _listener is not None:
            try:
                _listener(rec, len(_current))
            except Exception as e:  # noqa: BLE001 - evidence must never break a test
                log.warning("step listener failed: %s", e)
