"""``Web``: the single object tests use for everything inside web content.

    web.open_internal("bookmarks")
    web.type("bookmarks-app >>> cr-toolbar >>> cr-toolbar-search-field >>> input", "abc")
    web.click("text=Delete")
    assert "Deleted" in web.text("deepcss=cr-toast")
"""
from __future__ import annotations

from sbtest import steps
from sbtest.web.actions import ActionsMixin
from sbtest.web.navigation import NavigationMixin
from sbtest.web.reader import ReaderMixin
from sbtest.web.waits import WaitsMixin


class Web(WaitsMixin, ActionsMixin, ReaderMixin, NavigationMixin):
    def __init__(self, driver, cfg, native_factory=None) -> None:
        self.driver = driver
        self.cfg = cfg
        self._native_factory = native_factory
        self.timeout = float(cfg.get("timeouts.default", 10))
        self.long_timeout = float(cfg.get("timeouts.long", 30))
        self.interval = float(cfg.get("timeouts.poll", 0.2))
        #: (locator text, element or None) of the last element looked up - used by failure reports
        self.last_target: tuple[str, object] | None = None

    def highlight(self, el=None, color: str = "red") -> bool:
        """Outline an element (default: the last one used) so it shows in a screenshot."""
        el = el if el is not None else (self.last_target[1] if self.last_target else None)
        if el is None:
            return False
        try:
            self.driver.execute_script(
                "const e = arguments[0]; e.scrollIntoView({block: 'center'});"
                "e.style.outline = '3px solid ' + arguments[1]; e.style.outlineOffset = '2px';", el, color)
            return True
        except Exception:  # noqa: BLE001 - stale / detached element
            return False

    def _mark(self, kind: str, el, label: str = "") -> None:
        """Record where this action happens, for the step screenshot (only when recording)."""
        if not steps.recording() or el is None:
            return
        try:
            rect = self.driver.execute_script(
                "const r = arguments[0].getBoundingClientRect();"
                "return [r.left, r.top, r.width, r.height, window.devicePixelRatio];", el)
            steps.mark(kind, label, web=tuple(rect))
        except Exception:  # noqa: BLE001 - only a picture aid
            pass

    @property
    def native(self):
        """The session's NativeBrowser (created on first use), or None when native is disabled."""
        return self._native_factory() if self._native_factory else None
