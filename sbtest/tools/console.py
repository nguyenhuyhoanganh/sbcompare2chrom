"""Readable console output for the setup and doctor tools: numbered sections, one line per
check with a coloured [ OK ] / [WARN] / [FAIL] tag, and a "fix:" line under problems.
Technical logging goes to a file instead of the console (``log_to_file``)."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

OK, WARN, FAIL = "OK", "WARN", "FAIL"
_TAGS = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
_COLORS = {OK: "32", WARN: "33", FAIL: "31", "head": "36;1", "dim": "90", "bold": "1"}


def _use_color() -> bool:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name == "nt":   # switch the Windows console to ANSI colours (Windows 10+)
        try:
            import ctypes

            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if not k.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            k.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:  # noqa: BLE001
            return False
    return True


COLOR = _use_color()


def paint(text: str, style: str) -> str:
    return f"\033[{_COLORS[style]}m{text}\033[0m" if COLOR else text


def title(text: str) -> None:
    line = "=" * max(40, len(text) + 4)
    print("\n" + paint(line, "head"), paint(f"  {text}", "head"), paint(line, "head"), sep="\n", flush=True)


def section(label: str, text: str) -> None:
    """``[2/5] Keyboard and network`` (label "2/5"), ``[4.2] ...`` inside a bigger flow."""
    print("\n" + paint(f"[{label}] {text}", "bold"), flush=True)


def check(status: str, text: str, fix: str = "") -> None:
    """``[ OK ] text``; problems get an indented ``fix: ...`` line under them."""
    print(f"  {paint(_TAGS[status], status)} {text}", flush=True)
    if fix and status != OK:
        print(f"         {paint('fix:', status)} {fix}", flush=True)


def note(text: str) -> None:
    """A progress or info line (dim), e.g. "starting the browser once (a few seconds)"."""
    print(f"         {paint(text, 'dim')}", flush=True)


def log_to_file(path: Path, verbose: bool = False) -> None:
    """Technical log (INFO/DEBUG) -> ``path``; the console only shows warnings, readably."""
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.DEBUG)
    to_file = logging.FileHandler(path, mode="w", encoding="utf-8")
    to_file.setLevel(logging.DEBUG if verbose else logging.INFO)
    to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
    to_console = logging.StreamHandler(sys.stdout)
    to_console.setLevel(logging.DEBUG if verbose else logging.WARNING)
    to_console.setFormatter(logging.Formatter("         note: %(message)s"))
    root.addHandler(to_file)
    root.addHandler(to_console)
    # third-party chatter (selenium, urllib3, pywinauto) stays in the file
    for name in ("selenium", "urllib3", "comtypes", "pywinauto", "PIL"):
        logging.getLogger(name).setLevel(logging.WARNING)
