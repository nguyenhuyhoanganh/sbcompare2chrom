"""Helpers for Samsung's own WebUI components (si-*), mixed into every Samsung page object.

Samsung rewrote the internal pages with its own component set; what differs from Chromium:

    Chromium (cr-*)               Samsung (si-*)
    cr-toolbar-search-field       si-side-bar-toolbar-search-field (left side bar)
    cr-button in toolbar          si-toolbar-button (label in aria-label of its #container)
    cr-toast                      si-snack-bar inside si-snack-bar-manager (+ si-flat-button "Undo")
    cr-dialog                     si-dialog (wraps a native <dialog>), buttons dialog-button-si
    cr-action-menu .dropdown-item si-action-menu, button.si-context-menu-item[role=menuitem]
    cr-checkbox per row           si-select (round check box at the start of each row)
    cr-toggle                     si-toggle

Verified on Samsung Browser 31.0.0.55 (Chromium 148).
"""
from __future__ import annotations

from selenium.webdriver.remote.webelement import WebElement

from sbtest.pages.base import q

# text of every open snack bar (its message is slotted into the manager's shadow root)
_JS_SNACKBAR_TEXT = r"""
const out = [];
const walk = root => {
  for (const m of root.querySelectorAll('si-snack-bar-manager')) {
    const bar = m.shadowRoot && m.shadowRoot.querySelector('si-snack-bar');
    const shown = bar && (bar.hasAttribute('open') || bar.open || getComputedStyle(bar).display !== 'none'
                          && bar.getClientRects().length > 0);
    if (shown) out.push((m.shadowRoot.textContent || '').replace(/\s+/g, ' ').trim());
  }
  for (const el of root.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot);
};
walk(document);
return out.filter(Boolean).join(' | ');
"""

# the open si-dialog's inner <dialog>
_JS_OPEN_SI_DIALOG = r"""
const found = [];
const walk = root => {
  for (const d of root.querySelectorAll('si-dialog')) {
    const inner = d.shadowRoot && d.shadowRoot.querySelector('dialog');
    if ((inner && inner.open) || d.hasAttribute('open')) found.push(d);
  }
  for (const el of root.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot);
};
walk(document);
return found[0] || null;
"""


class SamsungPageMixin:
    """Overrides BasePage helpers for si-* components. Put it first in the bases:
    ``class BookmarksPage(SamsungPageMixin, ChromiumBookmarksPage)``."""

    SEARCH_INPUT = "deepcss=si-side-bar-toolbar-search-field"
    TOAST = "deepcss=si-snack-bar"
    #: host element of the page toolbar (si-toolbar-button children)
    TOOLBAR = "body"

    # -- toolbar (si-toolbar-button) ------------------------------------------------
    def toolbar_button(self, label: str) -> WebElement:
        """Toolbar button by its label (``Edit``, ``Delete``, ``Create folder``, ``Load Unpacked``...)."""
        return self.web.find(f"deepcss=[role=button][aria-label={q(label)}]", within=self.web.find(self.TOOLBAR))

    def toolbar(self, label: str) -> None:
        self.web.click(self.toolbar_button(label))

    def cancel_selection(self) -> None:
        """The "<" (Cancel) button of the selection toolbar ("2 selected")."""
        self.web.click(self.web.find("deepcss=#back-icon-button", within=self.web.find(self.TOOLBAR)))

    def toolbar_enabled(self, label: str) -> bool:
        host = self.web.js("return arguments[0].getRootNode().host", self.toolbar_button(label))
        return not self.web.js("return arguments[0].hasAttribute('disabled')", host)

    # -- snack bar (toast) -----------------------------------------------------------
    def toast_element(self) -> WebElement | None:
        for t in self.web.find_all(self.TOAST, visible=True):
            return t
        return None

    def wait_toast(self, contains: str = "", timeout: float | None = None) -> str:
        """Wait for the snack bar ("1 bookmark deleted"...) and return its text."""
        def _t():
            txt = self.web.js(_JS_SNACKBAR_TEXT)
            return txt if txt and contains.lower() in txt.lower() else None
        return self.web.wait_until(_t, timeout, f"snack bar containing {contains!r}")

    def toast_action(self, text: str = "Undo") -> None:
        self.click_text(text, css="si-flat-button, button")

    # -- dialogs (si-dialog) ---------------------------------------------------------
    def open_dialog(self, timeout: float | None = None) -> WebElement:
        return self.web.wait_until(lambda: self.web.js(_JS_OPEN_SI_DIALOG), timeout, "open si-dialog")

    def has_dialog(self) -> bool:
        return bool(self.web.js(_JS_OPEN_SI_DIALOG))

    def dialog_text(self) -> str:
        return self.web.js("return (arguments[0].innerText || arguments[0].textContent || '').trim()",
                           self.open_dialog())

    def dialog_input(self, input_id: str) -> WebElement:
        """Inner <input> of an si-input in the open dialog, e.g. ``dialog_input("name")``."""
        return self.web.find(f"deep=#{input_id} >>> #input", within=self._dialog_host())

    def dialog_button(self, text: str) -> None:
        self.click_text(text, css="dialog-button-si, si-flat-button, button", within=self._dialog_host())

    def wait_dialog_closed(self, timeout: float | None = None) -> None:
        self.web.wait_until(lambda: not self.has_dialog(), timeout, "si-dialog closed")

    def confirm_dialog_if_open(self, *labels: str, wait: float = 1.5) -> str | None:
        """Click the first of ``labels`` if a confirmation si-dialog shows up within ``wait`` s."""
        try:
            self.open_dialog(timeout=wait)
        except TimeoutError:
            return None
        for label in labels:
            try:
                self.find_by_text("dialog-button-si, si-flat-button, button", label, within=self._dialog_host(),
                                  timeout=0.5)
            except TimeoutError:
                continue
            self.dialog_button(label)
            self.wait_dialog_closed()
            return label
        raise LookupError(f"none of {labels} in dialog: {self.dialog_text()!r}")

    # -- context menu (si-action-menu) -----------------------------------------------
    def click_menu_item(self, text: str) -> None:
        self.web.click(self.find_by_text("button.si-context-menu-item, [role=menuitem]", text))

    def menu_items(self) -> list[str]:
        return [t for t in (self.web.text(e) for e in self.web.find_all("deepcss=button.si-context-menu-item")) if t]

    # -- side bar ------------------------------------------------------------------------
    def side_bar(self, text: str) -> None:
        """Click an entry of the left side bar (filters such as ``Last hour``, ``Image``...).
        Matched on the light-DOM text: si-select repeats its label in a shadow aria node."""
        def _find():
            for el in self.web.find_all("deepcss=.si-nav-menu-item"):
                if self.web.js("return (arguments[0].textContent || '').replace(/\\s+/g, ' ').trim()", el) == text:
                    return el
            return None
        self.web.click(self.web.wait_until(_find, message=f"side bar entry {text!r}"))

    def toolbar_any(self, *labels: str) -> str:
        """Click the first toolbar button present among ``labels`` (labels change with the
        selection, e.g. "Delete" / "Delete all"); returns the label used."""
        for label in labels:
            if self.web.find_all(f"deepcss=[role=button][aria-label={q(label)}]", within=self.web.find(self.TOOLBAR)):
                self.toolbar(label)
                return label
        raise LookupError(f"none of the toolbar buttons {labels}")
