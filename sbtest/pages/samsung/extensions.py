"""Samsung add-ons page (internet://extensions; WebDriver URL chrome://extensions, title "Add-ons").

STATUS: verified on Samsung Browser 31.0.0.55 (Chromium 148).

How it differs from Chromium:
- "Developer mode" is a si-toggle in the LEFT side bar (#devModeToggle); turning it on shows
  "Load Unpacked", "Pack add-on" and "Update" in the toolbar
- cards (extensions-item#<id>): name, version, description, "Details" / "Remove"
  (si-flat-button), dev "Reload" icon and the on/off si-toggle (#enableToggle)
- side bar: Add-ons, Keyboard shortcuts; list footer: "Get add-ons" (Galaxy Store / web store)
``info()`` (chrome.developerPrivate) works unchanged.
"""
from __future__ import annotations

from sbtest.pages.chromium.extensions import ExtensionsPage as ChromiumExtensionsPage
from sbtest.pages.samsung.base import SamsungPageMixin


class ExtensionsPage(SamsungPageMixin, ChromiumExtensionsPage):
    TOOLBAR = "extensions-manager >>> #toolbar"
    DEV_MODE = "extensions-manager >>> #sidebar >>> #devModeToggle"
    GET_ADDONS = "extensions-manager >>> #items-list >>> #webstore-button"

    def _card_button(self, name: str, label: str):
        return self.find_by_text("si-flat-button", label, within=self.item(name))

    def open_details(self, name: str) -> None:
        self.web.click(self._card_button(name, "Details"))
        self.web.wait_url("?id=")

    def click_remove(self, name: str) -> None:
        """Clicks Remove; confirm in the dialog that follows (``confirm_remove``)."""
        self.web.click(self._card_button(name, "Remove"))

    def confirm_remove(self, native=None, confirm: bool = True) -> None:
        """Answer the remove confirmation - a si-dialog on the page, or a native prompt."""
        if self.has_dialog() or self._wait_dialog(2):
            self.dialog_button("Remove" if confirm else "Cancel")
            self.wait_dialog_closed()
            return
        if native is None:
            raise RuntimeError("no remove confirmation on the page; pass `native` for the browser prompt")
        dlg = native.wait_dialog("remove_extension")
        dlg.click("Remove" if confirm else "Cancel")

    def _wait_dialog(self, timeout: float) -> bool:
        try:
            self.open_dialog(timeout=timeout)
            return True
        except TimeoutError:
            return False

    def load_unpacked(self, native, folder) -> None:
        """Developer mode -> toolbar "Load Unpacked" -> Windows folder picker -> folder."""
        self.set_dev_mode(True)
        self.toolbar("Load Unpacked")
        native.file_dialog("open").select_folder(folder)

    SHORTCUTS = "extensions-manager >>> #sidebar >>> #shortcutButton"

    def open_shortcuts(self) -> None:
        self.web.click(self.SHORTCUTS)
        self.web.wait_url("/shortcuts")

    def shortcuts(self) -> dict[str, str]:
        """Keyboard shortcuts page: ``{"Activate add-on for <name>": "Not set" | "Ctrl+..."}``."""
        out = {}
        for el in self.web.find_all('deepcss=[aria-label^="Shortcut "]'):
            # an empty shortcut shows "Not set" as the input placeholder
            out[self.web.attr(el, "aria-label")[len("Shortcut "):]] = (
                self.web.value(el) or self.web.text(el) or self.web.attr(el, "placeholder") or "")
        return out

    def open_pack_dialog(self) -> None:
        """Developer mode -> toolbar "Pack add-on" -> Pack extension dialog (si-dialog)."""
        self.set_dev_mode(True)
        self.toolbar("Pack add-on")
        self.open_dialog()

    def pack_inputs(self):
        """(root directory input, private key input) of the open Pack extension dialog."""
        inputs = self.web.find_all("deepcss=input", within=self._dialog_host())
        return inputs[0], inputs[1]

    def pack_button_enabled(self) -> bool:
        btn = self.find_by_text("dialog-button-si, si-flat-button, button", "Pack extension",
                                within=self._dialog_host())
        return not self.web.js("return arguments[0].hasAttribute('disabled') || "
                               "(arguments[0].shadowRoot && !!arguments[0].shadowRoot.querySelector('button[disabled]'))", btn)

    def pack(self, folder) -> None:
        """Pack an unpacked add-on folder: writes <folder>.crx and <folder>.pem next to it."""
        self.open_pack_dialog()
        self.web.type(self.pack_inputs()[0], str(folder))
        self.web.wait_until(self.pack_button_enabled, message="Pack extension enabled")
        self.dialog_button("Pack extension")

    def get_addons(self) -> None:
        """"Get add-ons" under the list: opens the add-on store in a new tab (switched to)."""
        before = self.web.tabs
        self.web.click(self.GET_ADDONS)
        self.web.wait_new_tab(before)

    def dev_toolbar(self) -> list[str]:
        """Labels of the toolbar buttons shown (developer mode adds Load Unpacked / Pack / Update)."""
        return [self.web.attr(e, "aria-label")
                for e in self.web.find_all("deepcss=[role=button][aria-label]", within=self.web.find(self.TOOLBAR))]
