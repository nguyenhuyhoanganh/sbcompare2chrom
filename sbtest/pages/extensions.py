"""Extensions / add-ons page (chrome://extensions).

``info()`` uses ``chrome.developerPrivate`` (available on this page) for a reliable list.
Removing an extension opens a *native* confirmation ("Remove "X"?") in upstream
Chromium: handle it with ``session.native.wait_dialog("remove_extension")``.
"""
from __future__ import annotations

from selenium.webdriver.remote.webelement import WebElement

from sbtest.pages.base import BasePage


class ExtensionsPage(BasePage):
    page = "extensions"
    ROOT = "extensions-manager >>> #items-list"
    DEV_MODE = "extensions-manager >>> #toolbar >>> #devMode"
    LOAD_UNPACKED = "extensions-manager >>> #toolbar >>> #loadUnpacked"
    ITEMS = "extensions-manager >>> #items-list >>> extensions-item"

    def info(self) -> list[dict]:
        """``[{id, name, version, state, type, location}]`` straight from the extension system."""
        return self.web.driver.execute_async_script(
            "const done = arguments[arguments.length - 1];"
            "chrome.developerPrivate.getExtensionsInfo({includeDisabled: true, includeTerminated: true},"
            " l => done(l.map(e => ({id: e.id, name: e.name, version: e.version, state: e.state,"
            " type: e.type, location: e.location}))));")

    def names(self) -> list[str]:
        """Names shown as cards in the UI."""
        return [self.web.text(self.web.find("deep=#name", within=i)) for i in self.web.find_all(self.ITEMS)]

    def item(self, name: str, timeout: float | None = None) -> WebElement:
        def _f():
            for i in self.web.find_all(self.ITEMS):
                if self.web.text(self.web.find("deep=#name", within=i, timeout=1)) == name:
                    return i
            return None
        return self.web.wait_until(_f, timeout, f"extension card {name!r}")

    def ext_id(self, name: str) -> str:
        return self.item(name).get_attribute("id")

    def is_enabled(self, name: str) -> bool:
        return self.web.is_checked(self.web.find("deep=#enableToggle", within=self.item(name)))

    def set_enabled(self, name: str, on: bool = True) -> None:
        self.web.set_checked(self.web.find("deep=#enableToggle", within=self.item(name)), on)

    def set_dev_mode(self, on: bool = True) -> None:
        self.web.set_checked(self.DEV_MODE, on)

    def open_details(self, name: str) -> None:
        self.web.click(self.web.find("deep=#detailsButton", within=self.item(name)))
        self.web.wait_url("?id=")

    def click_remove(self, name: str) -> None:
        """Clicks Remove; confirm in the native dialog (or the cr-dialog in forks that use one)."""
        self.web.click(self.web.find("deep=#removeButton", within=self.item(name)))

    def wait_gone(self, name: str, timeout: float | None = None) -> None:
        self.web.wait_until(lambda: name not in [e["name"] for e in self.info()], timeout, f"{name!r} removed")
