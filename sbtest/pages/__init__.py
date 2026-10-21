"""Page objects of Samsung Browser's internal pages (internet://..., opened as chrome://...).

    base.py          BasePage - helpers for Samsung's si-* components (side bar search,
                     toolbar buttons, snack bar, si-dialog, context menu)
    bookmarks.py  history.py  downloads.py  extensions.py
    webstore.py      Chrome Web Store item page (public website)

Tests use the ``pages`` fixture: ``pages.bookmarks.open()``, ``pages.extensions.info()`` ...
"""
from sbtest.pages.base import BasePage, q
from sbtest.pages.bookmarks import BookmarksPage
from sbtest.pages.downloads import DownloadsPage
from sbtest.pages.extensions import ExtensionsPage
from sbtest.pages.history import HistoryPage
from sbtest.pages.webstore import WebStorePage

PAGE_CLASSES = {
    "bookmarks": BookmarksPage,
    "history": HistoryPage,
    "downloads": DownloadsPage,
    "extensions": ExtensionsPage,
    "webstore": WebStorePage,
}


def page_class(name: str):
    if name not in PAGE_CLASSES:
        raise AttributeError(f"No page object {name!r}; add it to sbtest/pages/ and PAGE_CLASSES")
    return PAGE_CLASSES[name]


class Pages:
    """Lazy factory bound to one ``Web``: ``pages.history``, ``pages.extensions`` ..."""

    def __init__(self, web) -> None:
        self.web = web

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return page_class(name)(self.web)

    def of(self, web):
        """Same factory for another Web (e.g. after ``session.restart()``)."""
        return Pages(web)


__all__ = ["BasePage", "BookmarksPage", "DownloadsPage", "ExtensionsPage", "HistoryPage", "Pages",
           "WebStorePage", "page_class", "q"]
