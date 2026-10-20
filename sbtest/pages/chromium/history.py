"""History page (chrome://history)."""
from __future__ import annotations

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.remote.webelement import WebElement

from sbtest.pages.base import BasePage

_JS_ROWS = r"""
return arguments[0].map(i => {
  const r = i.shadowRoot, link = r.querySelector('#link');
  const txt = s => { const e = r.querySelector(s); return e ? e.textContent.trim() : ''; };
  return {title: link ? link.title : '', url: link ? link.href : '', domain: txt('#domain'), time: txt('#time-accessed')};
});
"""


class HistoryPage(BasePage):
    page = "history"
    ROOT = "#history-app >>> #history"
    ITEMS = "#history-app >>> #history >>> history-item"
    TOOLBAR = "#history-app >>> #toolbar"
    CLEAR_DATA_LINK = "#history-app >>> #contentSideBar >>> #clear-browsing-data"

    # -- reading -----------------------------------------------------------------
    def items(self) -> list[WebElement]:
        return self.web.find_all(self.ITEMS)

    def rows(self) -> list[dict]:
        """``[{title, url, domain, time}]`` of the visible entries, read in one JS call."""
        # the list re-renders while it loads: retry when a row goes stale between the two calls
        for attempt in range(5):
            try:
                return self.web.js(_JS_ROWS, self.items())
            except StaleElementReferenceException:
                if attempt == 4:
                    raise
        return []

    def titles(self) -> list[str]:
        return [r["title"] for r in self.rows()]

    def urls(self) -> list[str]:
        return [r["url"] for r in self.rows()]

    def item(self, title: str, timeout: float | None = None) -> WebElement:
        def _f():
            for i in self.items():
                if self.web.js("return arguments[0].shadowRoot.querySelector('#link').title", i) == title:
                    return i
            return None
        return self.web.wait_until(_f, timeout, f"history item {title!r}")

    def has_item(self, title: str) -> bool:
        return title in self.titles()

    def wait_item(self, title: str, present: bool = True, timeout: float | None = None) -> None:
        self.web.wait_until(lambda: self.has_item(title) == present, timeout,
                            f"history item {title!r} {'present' if present else 'absent'}")

    def is_empty(self) -> bool:
        return not self.items()

    # -- actions -----------------------------------------------------------------
    def open_item(self, title: str) -> None:
        self.web.click(self.web.find("deep=#link", within=self.item(title)))

    def select(self, *titles: str) -> None:
        for t in titles:
            self.web.click(self.web.find("deep=#checkbox", within=self.item(t)))

    def delete_selected(self, confirm: bool = True) -> None:
        """Toolbar Delete -> confirmation cr-dialog ("Remove" / "Cancel")."""
        self.click_text("Delete", css="cr-button", within=self.web.find(self.TOOLBAR))
        if confirm:
            self.dialog_button("Remove")
        else:
            self.dialog_button("Cancel")
        self.wait_dialog_closed()

    def item_menu(self, title: str, action: str) -> None:
        """``Remove from history`` | ``More from this site`` ..."""
        self.web.click(self.web.find("deep=#menu-button", within=self.item(title)))
        self.click_menu_item(action)

    def remove(self, title: str) -> None:
        self.item_menu(title, "Remove from history")
        self.wait_item(title, present=False)

    def open_clear_browsing_data(self) -> None:
        """Opens chrome://settings/clearBrowserData (in a new tab in upstream Chromium)."""
        self.web.click(self.CLEAR_DATA_LINK)
