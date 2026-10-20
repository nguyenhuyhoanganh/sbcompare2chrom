"""Reading page content: text (shadow DOM aware), attributes, state, lists, tables."""
from __future__ import annotations

from selenium.webdriver.remote.webelement import WebElement

from sbtest.web.locators import JS_COMPOSED_TEXT, find_all, is_visible


class ReaderMixin:
    driver: object

    def text(self, loc) -> str:
        """Visible text of the element, including text rendered inside its shadow root."""
        el = self.find(loc, visible=False)
        if self.driver.execute_script("return !!arguments[0].shadowRoot", el):
            return (self.driver.execute_script(JS_COMPOSED_TEXT, el) or "").strip()
        txt = (el.text or "").strip()
        return txt or (self.driver.execute_script(JS_COMPOSED_TEXT, el) or "").strip()

    def texts(self, loc, within: WebElement | None = None) -> list[str]:
        """Texts of all visible matches, in DOM order."""
        return [self.text(el) for el in find_all(self.driver, loc, within) if is_visible(self.driver, el)]

    def page_text(self) -> str:
        """All visible text of the current page, piercing every shadow root."""
        return self.driver.execute_script(JS_COMPOSED_TEXT, None) or ""

    def attr(self, loc, name: str) -> str | None:
        return self.find(loc, visible=False).get_attribute(name)

    def prop(self, loc, name: str):
        return self.driver.execute_script("return arguments[0][arguments[1]];", self.find(loc, visible=False), name)

    def value(self, loc) -> str:
        return self.prop(loc, "value") or ""

    def exists(self, loc, visible: bool = True) -> bool:
        """Immediate check, no waiting."""
        els = find_all(self.driver, loc)
        return any(is_visible(self.driver, e) for e in els) if visible else bool(els)

    def is_visible(self, loc) -> bool:
        return self.exists(loc, visible=True)

    def count(self, loc, visible: bool = True) -> int:
        els = find_all(self.driver, loc)
        return sum(1 for e in els if is_visible(self.driver, e)) if visible else len(els)

    def is_enabled(self, loc) -> bool:
        el = self.find(loc, visible=False)
        return el.is_enabled() and el.get_attribute("disabled") is None and el.get_attribute("aria-disabled") != "true"

    def is_checked(self, loc) -> bool:
        """Works for input checkbox/radio, cr-checkbox, cr-toggle, cr-radio-button, aria widgets."""
        el = self.find(loc, visible=False)
        return bool(self.driver.execute_script(
            "const e = arguments[0];"
            "if (typeof e.checked === 'boolean') return e.checked;"
            "const a = e.getAttribute('aria-checked') || e.getAttribute('aria-pressed');"
            "if (a !== null) return a === 'true';"
            "return e.hasAttribute('checked');", el))

    def table(self, loc) -> list[dict[str, str]]:
        """``<table>`` -> list of {header: cell_text} dicts."""
        el = self.find(loc)
        return self.driver.execute_script(r"""
            const t = arguments[0];
            const heads = Array.from(t.querySelectorAll('thead th, tr:first-child th')).map(h => h.innerText.trim());
            const rows = Array.from(t.querySelectorAll('tbody tr')).filter(r => r.querySelector('td'));
            return rows.map(r => {
              const cells = Array.from(r.querySelectorAll('td')).map(c => c.innerText.trim());
              const o = {}; cells.forEach((c, i) => o[heads[i] || String(i)] = c); return o;
            });""", el)

    def focused(self) -> WebElement | None:
        """Deepest focused element (follows shadowRoot.activeElement)."""
        return self.driver.execute_script(
            "let a = document.activeElement; while (a && a.shadowRoot && a.shadowRoot.activeElement)"
            " a = a.shadowRoot.activeElement; return a;")
