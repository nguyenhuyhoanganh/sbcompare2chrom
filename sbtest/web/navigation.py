"""Navigation, tabs/windows, JavaScript dialogs (alert/confirm/prompt), CDP, screenshots."""
from __future__ import annotations

import contextlib
from pathlib import Path

from selenium.common.exceptions import NoAlertPresentException, WebDriverException
from selenium.webdriver.common.alert import Alert

from sbtest.utils import poll


class NavigationMixin:
    driver: object

    # -- pages -----------------------------------------------------------------
    def open(self, url: str, wait: bool = True, blocking: bool = True) -> None:
        """Open a URL (http/file/internet://...) in the current tab.

        ``blocking=False`` navigates through ``location.href`` and returns at once - use it
        when the navigation stops at a browser prompt (HTTP sign-in, leave-site dialog),
        otherwise WebDriver would wait for a page load that only happens after the prompt.
        """
        if blocking:
            self.driver.get(url)
        else:
            self.driver.execute_script("setTimeout(() => { location.href = arguments[0]; }, 0);", url)
            return
        if wait:
            self.wait_ready()

    def open_internal(self, name: str) -> None:
        """Internal page by logical name from config ``pages`` (bookmarks, history, settings...)."""
        self.open(self.cfg.page_url(name))

    def back(self) -> None:
        self.driver.back()

    def forward(self) -> None:
        self.driver.forward()

    def refresh(self) -> None:
        self.driver.refresh()

    @property
    def url(self) -> str:
        return self.driver.current_url

    @property
    def title(self) -> str:
        return self.driver.title

    # -- tabs ------------------------------------------------------------------
    @property
    def tabs(self) -> list[str]:
        return list(self.driver.window_handles)

    def new_tab(self, url: str | None = None) -> str:
        self.driver.switch_to.new_window("tab")
        if url:
            self.open(url)
        return self.driver.current_window_handle

    def switch_tab(self, index: int | None = None, title: str | None = None, url: str | None = None,
                   timeout: float | None = None) -> str:
        """Switch by index, or to the first tab whose title/url *contains* the text."""
        if index is not None:
            handle = self.tabs[index]
            self.driver.switch_to.window(handle)
            return handle

        def _match():
            for h in self.tabs:
                self.driver.switch_to.window(h)
                if (title and title in self.driver.title) or (url and url in self.driver.current_url):
                    return h
            return None

        return self.wait_until(_match, timeout, f"tab title~{title} url~{url}")

    def wait_new_tab(self, before: list[str], timeout: float | None = None, switch: bool = True) -> str:
        """``before = web.tabs; web.click(link); web.wait_new_tab(before)``"""
        new = self.wait_until(lambda: [h for h in self.tabs if h not in before], timeout, "new tab/window")
        if switch:
            self.driver.switch_to.window(new[0])
        return new[0]

    def close_tab(self, switch_to: int = -1) -> None:
        self.driver.close()
        if self.tabs:
            self.driver.switch_to.window(self.tabs[switch_to])

    # -- frames ----------------------------------------------------------------
    @contextlib.contextmanager
    def frame(self, loc):
        """Work inside an iframe, then return to the page::

            with web.frame("#editor-frame"):
                web.type("#body", "hello")
        """
        self.driver.switch_to.frame(self.find(loc))
        try:
            yield self
        finally:
            self.driver.switch_to.default_content()

    # -- JS dialogs (alert / confirm / prompt / beforeunload) -------------------
    def wait_alert(self, timeout: float | None = None) -> Alert:
        def _get():
            try:
                a = self.driver.switch_to.alert
                _ = a.text
                return a
            except NoAlertPresentException:
                return None
        return poll(_get, self._t(timeout), self.interval, "JavaScript dialog")

    def alert_text(self, timeout: float | None = None) -> str:
        return self.wait_alert(timeout).text

    def accept_alert(self, prompt_text: str | None = None, timeout: float | None = None) -> str:
        a = self.wait_alert(timeout)
        text = a.text
        if prompt_text is not None:
            a.send_keys(prompt_text)
        a.accept()
        return text

    def dismiss_alert(self, timeout: float | None = None) -> str:
        a = self.wait_alert(timeout)
        text = a.text
        a.dismiss()
        return text

    def has_alert(self) -> bool:
        try:
            _ = self.driver.switch_to.alert.text
            return True
        except (NoAlertPresentException, WebDriverException):
            return False

    # -- misc ------------------------------------------------------------------
    def js(self, script: str, *args):
        return self.driver.execute_script(script, *args)

    def cdp(self, cmd: str, params: dict | None = None):
        """Chrome DevTools Protocol command, e.g. ``web.cdp("Browser.getVersion")``."""
        return self.driver.execute_cdp_cmd(cmd, params or {})

    def screenshot(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.driver.save_screenshot(str(path))
        return path
