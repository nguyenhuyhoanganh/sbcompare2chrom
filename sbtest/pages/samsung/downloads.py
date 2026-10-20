"""Samsung downloads page (internet://downloads; WebDriver URL chrome://downloads).

STATUS: verified on Samsung Browser 31.0.0.55 (Chromium 148).

How it differs from Chromium:
- left side bar: search + category filter (All, Image, Video, Audio, Document, Others)
- each row: name, size, source link and icon buttons "Copy link", "Show in folder"
  (aria-label; title "Open Downloads folder") and X "Remove <name> from download history"
- toolbar: "Clear download history"
- a finished download also opens the toolbar Downloads bubble
"""
from __future__ import annotations

from sbtest.pages.chromium.downloads import DownloadsPage as ChromiumDownloadsPage
from sbtest.pages.samsung.base import SamsungPageMixin

_JS_ITEM_INFO = r"""
const r = arguments[0].shadowRoot;
const t = s => { const e = r.querySelector(s); return e ? (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim() : ''; };
const visible = e => e && getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0;
const name = r.querySelector('#name');
const progress = r.querySelector('si-progress, #progress, progress, [role=progressbar]');
return {
  name: name ? (name.getAttribute('title') || name.textContent || '').trim() : '',
  url: (r.querySelector('#downloadItemUrl') || {}).href || '',
  size: t('#size'),
  description: t('#inProgressStatus') || t('#description') || t('.description') || t('#progress-size-text'),
  tag: t('#tag'),
  in_progress: visible(progress),
};
"""


class DownloadsPage(SamsungPageMixin, ChromiumDownloadsPage):
    ROOT = "downloads-manager >>> #mainContainer"
    TOOLBAR = "downloads-manager >>> #toolbar"
    CATEGORIES = ("All", "Image", "Video", "Audio", "Document", "Others")

    def info(self, item) -> dict:
        """``{name, url, size, description, tag, in_progress}`` of one row."""
        return self.web.js(_JS_ITEM_INFO, item)

    def status(self, name: str) -> str:
        i = self.info(self.item(name))
        return " ".join(x for x in (i["tag"], i["description"], i["size"]) if x)

    def action(self, name: str, action: str) -> None:
        """Row icon button by aria-label or title: ``Show in folder`` | ``Copy link`` | ``Pause``..."""
        item = self.item(name)
        # in-progress rows: text buttons Pause/Resume (#pauseOrResume) and Cancel (#cancelButton)
        for b in self.web.find_all("deepcss=si-flat-button", within=item):
            if self.web.text(b) == action:
                self.web.click(b)
                return
        for attr in ("aria-label", "title"):
            hits = self.web.find_all(f'deepcss=[{attr}="{action}"]', within=item)
            if hits:
                self.web.click(hits[0])
                return
        raise LookupError(f"no button {action!r} on download row {name!r}")

    def remove(self, name: str) -> None:
        self.web.click(self.web.find("deep=#remove", within=self.item(name)))
        self.wait_item(name, present=False)

    def clear_all(self) -> None:
        self.toolbar("Clear download history")
        self.confirm_dialog_if_open("Clear", "Delete", "OK")
        self.web.wait_until(lambda: not self.items(), message="downloads list empty")

    def filter_category(self, label: str) -> None:
        """Side bar category: one of ``CATEGORIES``."""
        self.side_bar(label)
