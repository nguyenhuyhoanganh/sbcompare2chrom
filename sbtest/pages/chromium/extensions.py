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

    def wait_installed(self, name: str, timeout: float | None = None) -> dict:
        """Wait until the extension system reports ``name`` (any state); returns its info."""
        return self.web.wait_until(lambda: next((e for e in self.info() if e["name"] == name), None),
                                   timeout or self.web.long_timeout, f"{name!r} installed")

    # -- install flows (native parts need the `native` fixture) -------------------
    def load_unpacked(self, native, folder) -> None:
        """Developer mode -> "Load unpacked" -> Windows folder picker -> folder."""
        self.set_dev_mode(True)
        self.web.click(self.LOAD_UNPACKED)
        native.file_dialog("open").select_folder(folder)

    def drop_crx(self, native, crx, confirm: bool = True) -> None:
        """Drag a .crx from File Explorer onto this page (real OS drag), then answer the
        native "Add <name>?" prompt. Developer mode must be on for drops to be accepted."""
        self.set_dev_mode(True)
        native.drag_file_from_explorer(crx, web=self.web)
        dlg = native.wait_dialog("add_extension", timeout=self.web.long_timeout)
        # Chrome: [Add extension] [Cancel]; Samsung: [Add] [Not now]
        if confirm:
            dlg.click_any("Add extension", "Add")
        else:
            dlg.click_any("Cancel", "Not now")

    def wait_gone(self, name: str, timeout: float | None = None) -> None:
        self.web.wait_until(lambda: name not in [e["name"] for e in self.info()], timeout, f"{name!r} removed")
