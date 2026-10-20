"""Settings (chrome://settings).

Besides the UI helpers, ``get_pref``/``set_pref`` use ``chrome.settingsPrivate`` which is
available on the settings page: use it to *verify* a UI change really changed the
preference, or to prepare state quickly. Pref names: chrome://prefs-internals.
"""
from __future__ import annotations

from selenium.webdriver.remote.webelement import WebElement

from sbtest.pages.base import BasePage, q


class SettingsPage(BasePage):
    page = "settings"
    ROOT = "settings-ui >>> #main"
    SEARCH_INPUT = "settings-ui >>> #toolbar >>> #search"
    MENU = "settings-ui >>> #leftMenu"

    def open_section(self, section: str) -> "SettingsPage":
        """``downloads`` | ``onStartup`` | ``appearance`` | ``search`` | ``privacy`` | ``clearBrowserData`` ..."""
        return self.open(section)

    def menu(self, label: str) -> None:
        """Click a left menu entry by its text (e.g. "Downloads")."""
        self.click_text(label, css="a.cr-nav-menu-item", within=self.web.find(self.MENU))

    # -- controls by label -------------------------------------------------------
    def toggle(self, label: str) -> WebElement:
        """The cr-toggle whose aria-label is ``label`` (settings-toggle-button)."""
        return self.web.find(f"deepcss=cr-toggle[aria-label={q(label)}]")

    def is_on(self, label: str) -> bool:
        return self.web.is_checked(self.toggle(label))

    def set_toggle(self, label: str, on: bool = True) -> None:
        self.web.set_checked(self.toggle(label), on)

    def radio(self, label: str) -> WebElement:
        return self.find_by_text("cr-radio-button, controlled-radio-button", label, contains=True)

    def choose_radio(self, label: str) -> None:
        el = self.radio(label)
        self.web.click(el)
        self.web.wait_until(lambda: self.web.is_checked(el), message=f"radio {label!r} checked")

    def dropdown(self, label: str) -> WebElement:
        """Native <select> inside the settings-dropdown-menu labelled ``label``."""
        return self.web.find(f"deepcss=select[aria-label={q(label)}]")

    def choose(self, label: str, option_text: str) -> None:
        self.web.select(self.dropdown(label), text=option_text)

    # -- prefs (verification / setup) -------------------------------------------
    def get_pref(self, name: str):
        """Value of a preference, e.g. ``get_pref("download.prompt_for_download")``."""
        return self.web.driver.execute_async_script(
            "const done = arguments[arguments.length - 1];"
            "chrome.settingsPrivate.getPref(arguments[0], p => done(p ? p.value : null));", name)

    def set_pref(self, name: str, value) -> bool:
        return self.web.driver.execute_async_script(
            "const done = arguments[arguments.length - 1];"
            "chrome.settingsPrivate.setPref(arguments[0], arguments[1], '', ok => done(ok));", name, value)
