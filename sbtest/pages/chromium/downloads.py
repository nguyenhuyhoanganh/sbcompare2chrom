"""Downloads page (chrome://downloads)."""
from __future__ import annotations

from selenium.webdriver.remote.webelement import WebElement

from sbtest.pages.base import BasePage

_JS_ITEM_INFO = r"""
const r = arguments[0].shadowRoot;
const t = s => { const e = r.querySelector(s); return e ? (e.innerText || e.textContent || '').trim() : ''; };
const link = r.querySelector('#file-link');
const visible = e => e && getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0;
return {
  name: (visible(link) ? link.textContent : (r.querySelector('#name') || {}).textContent || '').trim(),
  url: (r.querySelector('#url') || link || {}).href || '',
  description: t('.description'),
  tag: t('#tag'),
  in_progress: !!r.querySelector('#content.is-active.show-progress') || visible(r.querySelector('cr-progress')),
};
"""


class DownloadsPage(BasePage):
    page = "downloads"
    ROOT = "downloads-manager >>> #mainContainer"
    ITEMS = "downloads-manager >>> downloads-item"
    CLEAR_ALL = "downloads-manager >>> #toolbar >>> #clearAll"

    def items(self) -> list[WebElement]:
        return self.web.find_all(self.ITEMS)

    def info(self, item: WebElement) -> dict:
        """``{name, url, description, tag, in_progress}`` of one row."""
        return self.web.js(_JS_ITEM_INFO, item)

    def names(self) -> list[str]:
        return [self.info(i)["name"] for i in self.items()]

    def item(self, name: str, timeout: float | None = None) -> WebElement:
        def _f():
            for i in self.items():
                if self.info(i)["name"] == name:
                    return i
            return None
        return self.web.wait_until(_f, timeout, f"download item {name!r}")

    def wait_item(self, name: str, present: bool = True, timeout: float | None = None) -> None:
        self.web.wait_until(lambda: (name in self.names()) == present, timeout,
                            f"download {name!r} {'present' if present else 'absent'}")

    def wait_complete(self, name: str, timeout: float | None = None) -> dict:
        def _done():
            i = self.info(self.item(name, timeout=1))
            return i if not i["in_progress"] else None
        return self.web.wait_until(_done, self.web.long_timeout if timeout is None else timeout,
                                   f"download {name!r} complete")

    def status(self, name: str) -> str:
        """Description line, e.g. "Paused", "Canceled", "277 KB/s - 1.6 MB of 10 MB"."""
        i = self.info(self.item(name))
        return " ".join(x for x in (i["tag"], i["description"]) if x)

    # -- actions -----------------------------------------------------------------
    def action(self, name: str, action: str) -> None:
        """Row action: quick buttons (``Show in folder``, ``Delete from history``, ``Copy download link``)
        or items of the ⋮ menu (``Pause``, ``Resume``, ``Cancel``, ``Retry``...)."""
        item = self.item(name)
        quick = self.web.find_all(f"deep=[aria-label=\"{action}\"]", within=item)
        if quick:
            self.web.click(quick[0])
            return
        self.web.click(self.web.find("deep=#more-actions", within=item))
        self.click_menu_item(action)

    def remove(self, name: str) -> None:
        self.web.click(self.web.find("deep=#quick-remove", within=self.item(name)))
        self.wait_item(name, present=False)

    def clear_all(self) -> None:
        self.web.click(self.CLEAR_ALL)
        self.web.wait_until(lambda: not self.items(), message="downloads list empty")
