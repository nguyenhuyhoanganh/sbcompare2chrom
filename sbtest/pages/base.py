"""BasePage: helpers shared by every page object - Samsung's own WebUI components (si-*).

Samsung rewrote the internal pages with its own component set; compared with upstream Chromium:

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

from sbtest.web.web import Web


def q(value: str) -> str:
    """Quote a value for a CSS attribute selector: ``f'[aria-label={q(name)}]'``."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


_JS_VISIBLE_BY_TEXT = r"""
const sel = arguments[0], text = arguments[1], contains = arguments[2], start = arguments[3];
const out = [];
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
// text as rendered, including shadow content and slotted nodes
const ctext = n => {
  if (n.nodeType === 3) return n.nodeValue;
  if (n.nodeType !== 1 && n.nodeType !== 11) return '';
  if (n.nodeType === 1 && /^(SCRIPT|STYLE|TEMPLATE)$/.test(n.tagName)) return '';
  let kids = n.shadowRoot ? n.shadowRoot.childNodes : n.childNodes;
  if (n.tagName === 'SLOT') { const a = n.assignedNodes({flatten: true}); if (a.length) kids = a; }
  let t = ''; for (const c of kids) t += ' ' + ctext(c); return t;
};
const vis = el => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0; };
const walk = root => {
  for (const el of root.querySelectorAll(sel)) {
    const t = norm(el.shadowRoot ? ctext(el) : (el.innerText || el.textContent));
    if ((contains ? t.includes(text) : t === text) && vis(el)) out.push(el);
  }
  for (const el of root.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot);
};
walk(start ? (start.shadowRoot || start) : document);
return out;
"""

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


class BasePage:
    """Base of every page object: open/wait, side bar search, toolbar buttons, snack bar,
    si-dialog, context menu. Page objects add selectors (class constants) and page steps."""

    #: key in config ``pages`` (bookmarks, history, ...)
    page: str = ""
    #: element that proves the page rendered
    ROOT: str = "body"
    SEARCH_INPUT = "deepcss=si-side-bar-toolbar-search-field"
    TOAST = "deepcss=si-snack-bar"
    #: host element of the page toolbar (si-toolbar-button children)
    TOOLBAR = "body"

    def __init__(self, web: Web) -> None:
        self.web = web

    # -- open / state ------------------------------------------------------------
    @property
    def url(self) -> str:
        return self.web.cfg.page_url(self.page)

    def open(self, subpath: str = "") -> "BasePage":
        self.web.open(self.url + (("/" + subpath.lstrip("/")) if subpath else ""))
        self.wait_loaded()
        return self

    def wait_loaded(self) -> None:
        try:
            self.web.wait_present(self.ROOT, timeout=self.web.long_timeout)
        except TimeoutError as e:
            raise TimeoutError(
                f"{type(self).__name__} did not render at {self.web.url!r} (expected {self.url}): {e}. "
                "If the URL is wrong check config pages.scheme / pages.<name>; if the page loaded, "
                f"ROOT={self.ROOT!r} no longer matches - re-explore with `python -m sbtest.tools.dom {self.page}`."
            ) from e

    def is_open(self) -> bool:
        return self.web.url.startswith(self.url)

    # -- toolbar search ----------------------------------------------------------
    def search(self, text: str) -> None:
        field = self.web.find(self.SEARCH_INPUT)
        self.web.type(self.web.find("deep=#searchInput", within=field), text)

    def clear_search(self) -> None:
        field = self.web.find(self.SEARCH_INPUT)
        inp = self.web.find("deep=#searchInput", within=field)
        self.web.clear(inp)
        self.web.set_value(inp, "")

    # -- generic text based helpers ---------------------------------------------
    def find_by_text(self, css: str, text: str, contains: bool = False, within: WebElement | None = None,
                     timeout: float | None = None) -> WebElement:
        """Visible element of ``css`` (searched in all shadow roots) whose text is ``text``."""
        return self.web.wait_until(
            lambda: (self.web.js(_JS_VISIBLE_BY_TEXT, css, text, contains, within) or [None])[0],
            timeout, f"{css} with text {text!r}")

    def click_text(self, text: str, css: str = "button, cr-button, a, [role=button], [role=menuitem], .dropdown-item",
                   contains: bool = False, within: WebElement | None = None) -> None:
        self.web.click(self.find_by_text(css, text, contains, within))

    # -- context menu (si-action-menu) -----------------------------------------------
    def click_menu_item(self, text: str) -> None:
        self.web.click(self.find_by_text("button.si-context-menu-item, [role=menuitem]", text))

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

    def dialog_text(self) -> str:
        return self.web.js("return (arguments[0].innerText || arguments[0].textContent || '').trim()",
                           self.open_dialog())

    def dialog_input(self, input_id: str) -> WebElement:
        """Inner <input> of an si-input in the open dialog, e.g. ``dialog_input("name")``."""
        return self.web.find(f"deep=#{input_id} >>> #input", within=self._dialog_host())

    def _dialog_host(self) -> WebElement:
        """Component that owns the open cr-dialog (its inputs/buttons live in the same shadow root)."""
        return self.web.js("return arguments[0].getRootNode().host || arguments[0].parentElement",
                           self.open_dialog())

    def dialog_button(self, text: str) -> None:
        self.click_text(text, css="dialog-button-si, si-flat-button, button", within=self._dialog_host())

    def wait_dialog_closed(self, timeout: float | None = None) -> None:
        self.web.wait_until(lambda: not self.has_dialog(), timeout, "si-dialog closed")

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

    def has_dialog(self) -> bool:
        return bool(self.web.js(_JS_OPEN_SI_DIALOG))

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
