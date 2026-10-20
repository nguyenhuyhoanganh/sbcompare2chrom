"""Samsung history page (internet://history; WebDriver URL chrome://history).

STATUS: verified on Samsung Browser 31.0.0.55 (Chromium 148).

How it differs from Chromium:
- one history-item per entry; the first entry of a day also carries the day header
  ("Today - Tuesday, October 20, 2026") with its own select-all check box (#all-select)
- entries are selected with a round check box (si-select#select); Share / Delete act on
  the selection, "Clear history" is always in the toolbar
- left side bar: search, time filter (All time / Last hour / Today / Yesterday / Older),
  "Clear browsing data" (opens internet://settings/clearBrowserData)
"""
from __future__ import annotations

from selenium.webdriver.remote.webelement import WebElement

from sbtest.pages.chromium.history import HistoryPage as ChromiumHistoryPage
from sbtest.pages.samsung.base import SamsungPageMixin

_JS_ROWS = r"""
return arguments[0].map(i => {
  const r = i.shadowRoot, link = r.querySelector('#item-container');
  const txt = s => { const e = r.querySelector(s); return e ? e.textContent.replace(/\s+/g, ' ').trim() : ''; };
  const t = r.querySelector('#history-item-title');
  return {title: t ? t.title : '', url: link ? link.href : '', domain: txt('.website-domain'),
          time: txt('#time-accessed'), day: txt('#date-accessed')};
});
"""


class HistoryPage(SamsungPageMixin, ChromiumHistoryPage):
    TOOLBAR = "#history-app >>> #toolbar"
    CLEAR_DATA_LINK = "#history-app >>> #content-side-bar >>> #clear-browsing-data"
    TIME_FILTERS = ("All time", "Last hour", "Today", "Yesterday", "Older")

    def rows(self) -> list[dict]:
        """``[{title, url, domain, time, day}]`` of the listed entries (newest first)."""
        from selenium.common.exceptions import StaleElementReferenceException

        for attempt in range(5):
            try:
                return self.web.js(_JS_ROWS, self.items())
            except StaleElementReferenceException:
                if attempt == 4:
                    raise
        return []

    def item(self, title: str, timeout: float | None = None) -> WebElement:
        def _f():
            for i in self.items():
                if self.web.js("const t = arguments[0].shadowRoot.querySelector('#history-item-title');"
                               "return t ? t.title : ''", i) == title:
                    return i
            return None
        return self.web.wait_until(_f, timeout, f"history item {title!r}")

    def days(self) -> list[str]:
        return [r["day"] for r in self.rows() if r["day"]]

    # -- actions -----------------------------------------------------------------
    def open_item(self, title: str) -> None:
        self.web.click(self.web.find("deep=#history-item-title", within=self.item(title)))

    def select(self, *titles: str) -> None:
        for t in titles:
            self.web.click(self.web.find("deep=si-select#select", within=self.item(t)))

    def delete_selected(self, confirm: bool = True) -> None:
        """Toolbar Delete (removes the selected entries; confirms if a dialog asks)."""
        self.toolbar("Delete")
        if confirm:
            self.confirm_dialog_if_open("Delete", "Remove", "OK")
        else:
            if self.has_dialog():
                self.dialog_button("Cancel")
                self.wait_dialog_closed()

    def remove(self, title: str) -> None:
        self.select(title)
        self.delete_selected()
        self.wait_item(title, present=False)

    def clear_history(self, confirm: bool = True) -> None:
        """Toolbar "Clear history" (-> confirmation)."""
        self.toolbar("Clear history")
        if confirm:
            self.confirm_dialog_if_open("Clear", "Delete", "Clear history", "OK")
        elif self.has_dialog():
            self.dialog_button("Cancel")
            self.wait_dialog_closed()

    def time_filters(self) -> list[str]:
        """Ticked time filters. They are check boxes: several can be on (union of ranges)."""
        out = []
        for el in self.web.find_all("deepcss=si-select.si-nav-menu-item"):
            label = self.web.js("return (arguments[0].textContent || '').replace(/\\s+/g, ' ').trim()", el)
            if label in self.TIME_FILTERS and self.web.is_checked(el):
                out.append(label)
        return out

    def filter_time(self, *labels: str) -> None:
        """Leave exactly ``labels`` ticked among ``TIME_FILTERS`` (ticks first, then unticks)."""
        for label in labels:
            if label not in self.time_filters():
                self.side_bar(label)
        for label in self.time_filters():
            if label not in labels:
                self.side_bar(label)
        self.web.wait_until(lambda: sorted(self.time_filters()) == sorted(labels), message=f"time filters {labels}")
