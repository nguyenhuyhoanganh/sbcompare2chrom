"""Page objects. Access through the ``pages`` fixture: ``pages.bookmarks.open()``."""
from sbtest.pages.base import BasePage, q
from sbtest.pages.bookmarks import BookmarksPage
from sbtest.pages.downloads import DownloadsPage
from sbtest.pages.extensions import ExtensionsPage
from sbtest.pages.history import HistoryPage
from sbtest.pages.settings import SettingsPage
from sbtest.pages.webstore import WebStorePage


class Pages:
    """Lazy factory bound to one ``Web``: ``pages.history``, ``pages.settings`` ..."""

    REGISTRY = {
        "bookmarks": BookmarksPage,
        "history": HistoryPage,
        "downloads": DownloadsPage,
        "settings": SettingsPage,
        "extensions": ExtensionsPage,
        "webstore": WebStorePage,
    }

    def __init__(self, web) -> None:
        self.web = web

    def __getattr__(self, name: str):
        try:
            return self.REGISTRY[name](self.web)
        except KeyError as e:
            raise AttributeError(f"No page object {name!r}; add it to sbtest/pages and Pages.REGISTRY") from e


__all__ = ["BasePage", "BookmarksPage", "DownloadsPage", "ExtensionsPage", "HistoryPage", "Pages",
           "SettingsPage", "WebStorePage", "q"]
