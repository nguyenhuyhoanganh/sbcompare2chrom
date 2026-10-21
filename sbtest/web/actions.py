"""User actions on web content: click, type, keys, hover, select, drag & drop, scroll, upload.

All methods take a locator (see ``sbtest.web.locators``) or a WebElement, wait for the
element, scroll it into view and retry once on stale/intercepted elements.
"""
from __future__ import annotations

import time
from pathlib import Path

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select

from sbtest.utils import log

RETRY_ERRORS = (StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException)

JS_HTML5_DND = r"""
const src = arguments[0], dst = arguments[1];
const dt = new DataTransfer();
const fire = (el, type, x, y) => {
  const r = el.getBoundingClientRect();
  const ev = new DragEvent(type, {bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
    clientX: r.left + r.width / 2 + (x || 0), clientY: r.top + r.height / 2 + (y || 0)});
  el.dispatchEvent(ev);
};
fire(src, 'dragstart'); fire(dst, 'dragenter'); fire(dst, 'dragover'); fire(dst, 'drop'); fire(src, 'dragend');
"""


class ActionsMixin:
    driver: object

    def _with_retry(self, loc, fn, attempts: int = 3):
        last = None
        for i in range(attempts):
            el = self.find(loc)
            try:
                return fn(el)
            except RETRY_ERRORS as e:
                last = e
                log.debug("retry %s on %s: %s", i + 1, loc, type(e).__name__)
                time.sleep(0.3)
        raise last

    def scroll_to(self, loc) -> WebElement:
        el = self.find(loc, visible=False)
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", el)
        return el

    def scroll_by(self, dx: int = 0, dy: int = 500) -> None:
        self.driver.execute_script("window.scrollBy(arguments[0], arguments[1]);", dx, dy)

    def click(self, loc, js_fallback: bool = True) -> None:
        """Real click (ActionChains/WebDriver). Falls back to JS click if something overlays it."""

        def _click(el: WebElement):
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            try:
                el.click()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                if not js_fallback:
                    raise
                log.debug("JS click fallback on %s", loc)
                self.driver.execute_script("arguments[0].click();", el)

        self._with_retry(loc, _click)

    def js_click(self, loc) -> None:
        self.driver.execute_script("arguments[0].click();", self.find(loc, visible=False))

    def double_click(self, loc) -> None:
        self._with_retry(loc, lambda el: ActionChains(self.driver).double_click(self.scroll_to(el)).perform())

    def right_click(self, loc) -> None:
        """Opens the *web* context menu (cr-action-menu etc.). Native context menus: use native.context_menu_web."""
        self._with_retry(loc, lambda el: ActionChains(self.driver).context_click(self.scroll_to(el)).perform())

    def hover(self, loc) -> None:
        self._with_retry(loc, lambda el: ActionChains(self.driver).move_to_element(self.scroll_to(el)).perform())

    def type(self, loc, text: str, clear: bool = True, enter: bool = False) -> None:
        """Type into an input. For Polymer ``cr-input`` target its inner ``input``:
        ``"cr-input#name >>> input"`` (or use the page object helper)."""

        def _type(el: WebElement):
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            if el.is_displayed():
                el.click()
            if clear:
                self._clear_el(el)
            el.send_keys(text)
            if enter:
                el.send_keys(Keys.ENTER)

        self._with_retry(loc, _type)

    def _clear_el(self, el: WebElement) -> None:
        try:
            el.clear()
        except Exception:  # noqa: BLE001 - some custom inputs refuse clear()
            pass
        if el.get_attribute("value"):
            mod = Keys.COMMAND if self.driver.capabilities.get("platformName", "").lower() == "mac" else Keys.CONTROL
            el.send_keys(mod, "a")
            el.send_keys(Keys.DELETE)

    def clear(self, loc) -> None:
        self._with_retry(loc, self._clear_el)

    def set_value(self, loc, value: str) -> None:
        """Set value via JS + input/change events (for inputs that ignore send_keys)."""
        el = self.find(loc, visible=False)
        self.driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles: true, composed: true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true, composed: true}));", el, value)

    def press(self, *keys, loc=None) -> None:
        """Send keys to an element or to the focused element.

        ``web.press(Keys.ENTER)``  ``web.press(Keys.CONTROL, "a")`` (chord)  ``web.press("Delete")``
        Keys sent here go to the *page*; browser shortcuts (Ctrl+D, Ctrl+H, Ctrl+T...) are
        handled by the browser UI - use ``native.hotkey("^d")`` for those.
        """
        keys = tuple(getattr(Keys, k.upper(), k) if isinstance(k, str) and len(k) > 1 else k for k in keys)
        if loc is not None:
            self.find(loc).send_keys(*keys)
            return
        chain = ActionChains(self.driver)
        mods = [k for k in keys[:-1] if k in (Keys.CONTROL, Keys.SHIFT, Keys.ALT, Keys.COMMAND)]
        for m in mods:
            chain.key_down(m)
        chain.send_keys(*[k for k in keys if k not in mods])
        for m in reversed(mods):
            chain.key_up(m)
        chain.perform()

    def select(self, loc, text: str | None = None, value: str | None = None, index: int | None = None) -> None:
        """Native ``<select>``. For Chromium ``cr-select``/``md-select`` (wrapping a select) target the inner select."""
        s = Select(self.find(loc))
        if text is not None:
            s.select_by_visible_text(text)
        elif value is not None:
            s.select_by_value(value)
        elif index is not None:
            s.select_by_index(index)

    def set_checked(self, loc, checked: bool = True) -> None:
        """Checkbox / cr-checkbox / cr-toggle: click only if the state differs."""
        el = self.find(loc)
        if self.is_checked(el) != checked:
            self.click(el)
            self.wait_until(lambda: self.is_checked(el) == checked, message=f"checked={checked} {loc}")

    def drag_and_drop(self, source, target, method: str = "actions", offset: tuple[int, int] = (0, 0)) -> None:
        """Drag ``source`` onto ``target``.

        method:
          "actions" WebDriver pointer actions (works for mouse-event based DnD, sortable lists)
          "html5"   synthesized HTML5 DragEvents (pages using draggable=true / dataTransfer)
          "native"  real OS mouse via pywinauto (anything, incl. drop on browser UI) - needs native
        """
        src, dst = self.scroll_to(source), self.find(target)
        if method == "html5":
            self.driver.execute_script(JS_HTML5_DND, src, dst)
        elif method == "actions":
            (ActionChains(self.driver).move_to_element(src).click_and_hold().pause(0.2)
             .move_by_offset(5, 5).move_to_element_with_offset(dst, *offset).pause(0.2).release().perform())
        elif method == "native":
            if self.native is None:
                raise RuntimeError("native drag requires the native layer (Windows, non-headless)")
            self.native.drag_web_element(self, src, dst, offset)
        else:
            raise ValueError(method)

    def drag_by(self, source, dx: int, dy: int) -> None:
        ActionChains(self.driver).drag_and_drop_by_offset(self.scroll_to(source), dx, dy).perform()

    def upload(self, loc, *files: str | Path) -> None:
        """Set files on ``<input type=file>`` without opening the OS file picker.
        If the page only opens a picker from a button, use ``native.file_dialog().open(path)``."""
        el = self.find(loc, visible=False)
        el.send_keys("\n".join(str(Path(f).resolve()) for f in files))
