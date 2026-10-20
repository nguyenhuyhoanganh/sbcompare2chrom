"""Explicit waits. Never use time.sleep in tests - wait for a condition instead."""
from __future__ import annotations

import fnmatch
import time
from pathlib import Path
from typing import Callable

from selenium.webdriver.remote.webelement import WebElement

from sbtest.core.locators import find_all, is_visible
from sbtest.utils import poll


class WaitsMixin:
    driver: object
    timeout: float
    interval: float

    def _t(self, timeout: float | None) -> float:
        return self.timeout if timeout is None else timeout

    def wait_until(self, fn: Callable, timeout: float | None = None, message: str = ""):
        """Generic wait: ``web.wait_until(lambda: web.count(".row") == 3, message="3 rows")``."""
        return poll(fn, self._t(timeout), self.interval, message)

    def find(self, loc, timeout: float | None = None, visible: bool = True, within: WebElement | None = None) -> WebElement:
        """First element matching ``loc`` (waits for it; visible by default)."""
        if isinstance(loc, WebElement):
            self.last_target = (str(loc), loc)
            return loc
        self.last_target = (str(loc), None)  # kept for failure reports even if not found

        def _get():
            for el in find_all(self.driver, loc, within):
                if not visible or is_visible(self.driver, el):
                    return el
            return None

        el = poll(_get, self._t(timeout), self.interval, f"element {'visible ' if visible else ''}{loc}")
        self.last_target = (str(loc), el)
        return el

    def find_all(self, loc, visible: bool = True, within: WebElement | None = None) -> list[WebElement]:
        """All matches right now (no waiting). Combine with ``wait_count`` when needed."""
        els = find_all(self.driver, loc, within)
        return [e for e in els if is_visible(self.driver, e)] if visible else els

    def wait_visible(self, loc, timeout: float | None = None, within=None) -> WebElement:
        return self.find(loc, timeout, visible=True, within=within)

    def wait_present(self, loc, timeout: float | None = None, within=None) -> WebElement:
        return self.find(loc, timeout, visible=False, within=within)

    def wait_gone(self, loc, timeout: float | None = None, within=None) -> bool:
        """Wait until no *visible* element matches ``loc``."""
        return self.wait_until(lambda: not self.find_all(loc, within=within), timeout, f"element gone {loc}")

    def wait_count(self, loc, count: int, timeout: float | None = None, within=None) -> list[WebElement]:
        def _ok():
            els = self.find_all(loc, within=within)
            return els if len(els) == count else None
        if count == 0:
            self.wait_gone(loc, timeout, within)
            return []
        return self.wait_until(_ok, timeout, f"{count} x {loc}")

    def wait_text(self, loc, expected: str, timeout: float | None = None, contains: bool = True) -> WebElement:
        def _ok():
            el = self.find(loc, timeout=0.5)
            txt = self.text(el)
            return el if (expected in txt if contains else txt == expected) else None
        return self.wait_until(_ok, timeout, f"text {'~' if contains else '='}{expected!r} in {loc}")

    def wait_page_text(self, expected: str, timeout: float | None = None) -> bool:
        """Text visible anywhere on the page (shadow DOM included)."""
        return self.wait_until(lambda: expected in self.page_text(), timeout, f"page text {expected!r}")

    def wait_url(self, part: str, timeout: float | None = None) -> str:
        return self.wait_until(lambda: self.driver.current_url if part in self.driver.current_url else None,
                               timeout, f"url contains {part!r}")

    def wait_title(self, part: str, timeout: float | None = None) -> str:
        return self.wait_until(lambda: self.driver.title if part in self.driver.title else None,
                               timeout, f"title contains {part!r}")

    def wait_ready(self, timeout: float | None = None) -> None:
        self.wait_until(lambda: self.driver.execute_script("return document.readyState") == "complete",
                        timeout, "document.readyState == complete")

    def wait_file(self, folder: Path, pattern: str = "*", timeout: float | None = None, settle: float = 0.5) -> Path:
        """Wait for a finished download in ``folder`` matching glob ``pattern``.

        Ignores Chromium temp files (.crdownload / .tmp) and waits until size is stable.
        """
        folder = Path(folder)

        def _done():
            for f in folder.iterdir():
                if f.suffix in (".crdownload", ".tmp", ".partial") or f.name.startswith(".com.google"):
                    continue
                if fnmatch.fnmatch(f.name, pattern) and f.is_file():
                    size = f.stat().st_size
                    time.sleep(settle)
                    if f.exists() and f.stat().st_size == size:
                        return f
            return None

        return self.wait_until(_done, timeout, f"downloaded file {pattern} in {folder}")
