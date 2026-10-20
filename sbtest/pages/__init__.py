"""Page objects.

    sbtest/pages/base.py       BasePage: helpers shared by all internal pages (search, toast, dialogs, menus)
    sbtest/pages/chromium/     upstream Chromium / Chrome implementation (reference, verified)
    sbtest/pages/samsung/      Samsung Internet implementation (subclasses, override what differs)
    sbtest/pages/webstore.py   Chrome Web Store (a public website, same for both targets)

Tests never import a target-specific class: they use the ``pages`` fixture, which picks the
implementation from config ``page_objects`` (set by the target):

    pages.bookmarks.open()      pages.extensions.info()      pages.webstore.install(id, native)
"""
from importlib import import_module

from sbtest.pages.base import BasePage, q
from sbtest.pages.webstore import WebStorePage

PAGE_CLASSES = {
    "bookmarks": "BookmarksPage",
    "history": "HistoryPage",
    "downloads": "DownloadsPage",
    "settings": "SettingsPage",
    "extensions": "ExtensionsPage",
}


def page_class(name: str, implementation: str = "chromium"):
    """Class of page ``name`` for an implementation (``chromium`` | ``samsung``)."""
    if name == "webstore":
        return WebStorePage
    if name not in PAGE_CLASSES:
        raise AttributeError(f"No page object {name!r}; add it to sbtest/pages/<impl>/ and PAGE_CLASSES")
    return getattr(import_module(f"sbtest.pages.{implementation}"), PAGE_CLASSES[name])


class Pages:
    """Lazy factory bound to one ``Web``: ``pages.history``, ``pages.settings`` ..."""

    def __init__(self, web) -> None:
        self.web = web
        self.implementation = web.cfg.get("page_objects") or "chromium"

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return page_class(name, self.implementation)(self.web)

    def of(self, web):
        """Same factory for another Web (e.g. after ``session.restart()``)."""
        return Pages(web)


__all__ = ["BasePage", "Pages", "WebStorePage", "page_class", "q"]
