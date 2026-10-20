"""Chrome Web Store item page (a normal website, reached through the company proxy).

The store's markup changes often and is not under our control: the install button is
found by its visible text (config ``webstore.add_button_texts``), not by CSS classes.
After the click the browser shows a *native* "Add "<name>"?" prompt.
"""
from __future__ import annotations

import re

from sbtest.pages.base import BasePage


class WebStorePage(BasePage):
    page = "webstore"
    ROOT = "body"

    def item_url(self, ext_id: str) -> str:
        return self.web.cfg.get("webstore.item_url", "https://chromewebstore.google.com/detail/{id}").format(id=ext_id)

    def open_item(self, ext_id: str) -> "WebStorePage":
        self.web.open(self.item_url(ext_id))
        self.web.wait_until(lambda: self._add_button() is not None or self._remove_button() is not None,
                            self.web.long_timeout, "web store install/remove button")
        return self

    def _buttons(self, texts: list[str]):
        rx = re.compile("|".join(f"^{re.escape(t)}$" for t in texts), re.I)
        for el in self.web.find_all("button, [role=button]"):
            if rx.match(self.web.text(el)):
                return el
        return None

    def _add_button(self):
        return self._buttons(self.web.cfg.get("webstore.add_button_texts") or ["Add to Chrome"])

    def _remove_button(self):
        return self._buttons(self.web.cfg.get("webstore.remove_button_texts") or ["Remove from Chrome"])

    def is_installed(self) -> bool:
        return self._remove_button() is not None

    def install(self, ext_id: str, native, confirm: bool = True) -> None:
        """Open the item, click Add, answer the native prompt."""
        self.open_item(ext_id)
        self.web.click(self._add_button())
        dlg = native.wait_dialog("add_extension", timeout=self.web.long_timeout)
        dlg.click("Add extension" if confirm else "Cancel")
        if confirm:
            self.web.wait_until(self.is_installed, self.web.long_timeout, "store shows the extension as installed")
