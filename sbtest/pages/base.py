"""BasePage + helpers shared by Chromium WebUI pages (cr-toolbar, cr-toast, cr-dialog, cr-action-menu).

Page objects hold *selectors and page-specific steps only*. Assertions stay in tests.
When the fork changes a page, only the selector constants here need updating.
"""
from __future__ import annotations

from selenium.webdriver.remote.webelement import WebElement

from sbtest.web.web import Web


def q(value: str) -> str:
    """Quote a value for a CSS attribute selector: ``f'[aria-label={q(name)}]'``."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# Visible elements of a given CSS inside every shadow root, filtered by exact text.
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


class BasePage:
    #: key in config ``pages`` (bookmarks, history, ...)
    page: str = ""
    #: element that proves the page rendered
    ROOT: str = "body"
    SEARCH_INPUT: str = "deepcss=cr-toolbar-search-field"
    TOAST: str = "deepcss=cr-toast"

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

    def click_menu_item(self, text: str) -> None:
        """Item of the open cr-action-menu (``.dropdown-item``)."""
        self.web.click(self.find_by_text(".dropdown-item, [role=menuitem]", text))

    # -- toast -------------------------------------------------------------------
    def toast_element(self) -> WebElement | None:
        for t in self.web.find_all(self.TOAST, visible=False):
            if self.web.js("return arguments[0].open === true || arguments[0].hasAttribute('open')", t):
                return t
        return None

    def wait_toast(self, contains: str = "", timeout: float | None = None) -> str:
        """Wait for an open cr-toast (optionally containing text); returns its text."""
        def _t():
            el = self.toast_element()
            if el is None:
                return None
            txt = self.web.text(el) or self.web.page_text()
            return txt if contains in txt else None
        return self.web.wait_until(_t, timeout, f"toast containing {contains!r}")

    def toast_action(self, text: str = "Undo") -> None:
        """Click a button shown with the toast (e.g. Undo)."""
        self.click_text(text, css="cr-button, button")

    # -- dialogs (cr-dialog) -----------------------------------------------------
    def open_dialog(self, timeout: float | None = None) -> WebElement:
        """The currently open ``cr-dialog`` (Edit bookmark, Clear data, ...)."""
        def _d():
            for d in self.web.find_all("deepcss=cr-dialog", visible=False):
                if self.web.js("return !!arguments[0].open || arguments[0].hasAttribute('open')", d):
                    return d
            return None
        return self.web.wait_until(_d, timeout, "open cr-dialog")

    def dialog_text(self) -> str:
        return self.web.text(self.open_dialog())

    def dialog_input(self, input_id: str) -> WebElement:
        """Inner <input> of a cr-input inside the open dialog, e.g. ``dialog_input("name")``."""
        return self.web.find(f"deep=#{input_id} >>> input", within=self._dialog_host())

    def _dialog_host(self) -> WebElement:
        """Component that owns the open cr-dialog (its inputs/buttons live in the same shadow root)."""
        return self.web.js("return arguments[0].getRootNode().host || arguments[0].parentElement",
                           self.open_dialog())

    def dialog_button(self, text: str) -> None:
        self.click_text(text, css="cr-button, button", within=self._dialog_host())

    def wait_dialog_closed(self, timeout: float | None = None) -> None:
        def _closed():
            for d in self.web.find_all("deepcss=cr-dialog", visible=False):
                if self.web.js("return !!arguments[0].open", d):
                    return False
            return True
        self.web.wait_until(_closed, timeout, "cr-dialog closed")
