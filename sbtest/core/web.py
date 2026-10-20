"""``Web``: the single object tests use for everything inside web content.

    web.open_internal("bookmarks")
    web.type("bookmarks-app >>> cr-toolbar >>> cr-toolbar-search-field >>> input", "abc")
    web.click("text=Delete")
    assert "Deleted" in web.text("deepcss=cr-toast")
"""
from __future__ import annotations

from sbtest.core.actions import ActionsMixin
from sbtest.core.navigation import NavigationMixin
from sbtest.core.reader import ReaderMixin
from sbtest.core.waits import WaitsMixin


class Web(WaitsMixin, ActionsMixin, ReaderMixin, NavigationMixin):
    def __init__(self, driver, cfg, native_factory=None) -> None:
        self.driver = driver
        self.cfg = cfg
        self._native_factory = native_factory
        self.timeout = float(cfg.get("timeouts.default", 10))
        self.long_timeout = float(cfg.get("timeouts.long", 30))
        self.interval = float(cfg.get("timeouts.poll", 0.2))

    @property
    def native(self):
        """The session's NativeBrowser (created on first use), or None when native is disabled."""
        return self._native_factory() if self._native_factory else None
