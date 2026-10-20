"""Small shared helpers: logging, unique names, process cleanup, polling."""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Callable, TypeVar

import psutil

log = logging.getLogger("sbtest")

T = TypeVar("T")


def unique(prefix: str = "sb") -> str:
    """Unique, readable test value, e.g. ``unique("Folder")`` -> ``Folder_1a2b3c``."""
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


def slug(text: str, max_len: int = 80) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:max_len].strip("_") or "x"


def kill_tree(pid: int, timeout: float = 5) -> None:
    """Kill a process and all its children (browser spawns many)."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    procs = parent.children(recursive=True) + [parent]
    for p in procs:
        try:
            p.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(procs, timeout=timeout)


def find_browser_pid(user_data_dir: str) -> int | None:
    """PID of the top browser process started with this --user-data-dir.

    The user-data-dir is unique per session, so this is reliable even when several
    browsers run at once. Child processes (renderer, gpu, ...) carry ``--type=``.
    """
    needle = str(user_data_dir).lower().rstrip("\\/")
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
        except psutil.Error:
            continue
        joined = " ".join(cmd).lower()
        if needle in joined and "--type=" not in joined:
            return p.info["pid"]
    return None


def poll(fn: Callable[[], T], timeout: float, interval: float = 0.2, message: str = "") -> T:
    """Call ``fn`` until it returns a truthy value; return it or raise TimeoutError.

    Exceptions inside ``fn`` are treated as "not yet" and re-raised in the timeout
    message, which makes it safe for stale elements / windows not yet created.
    """
    end = time.time() + timeout
    last_exc: Exception | None = None
    while True:
        try:
            value = fn()
            if value:
                return value
        except Exception as e:  # noqa: BLE001 - intentionally broad, reported below
            last_exc = e
        if time.time() >= end:
            first_line = str(last_exc).strip().splitlines()[0] if last_exc and str(last_exc).strip() else ""
            detail = f" (last error: {type(last_exc).__name__}: {first_line})" if last_exc else ""
            raise TimeoutError(f"Timed out after {timeout}s: {message or fn}{detail}")
        time.sleep(interval)
