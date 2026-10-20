"""Page objects for Samsung Internet internal pages (internet://...).

Each class subclasses the Chromium reference and overrides what Samsung changed. The
module docstring of each file records whether it has been verified on a real build.
"""
from sbtest.pages.samsung.bookmarks import BookmarksPage
from sbtest.pages.samsung.downloads import DownloadsPage
from sbtest.pages.samsung.extensions import ExtensionsPage
from sbtest.pages.samsung.history import HistoryPage
from sbtest.pages.samsung.settings import SettingsPage

__all__ = ["BookmarksPage", "DownloadsPage", "ExtensionsPage", "HistoryPage", "SettingsPage"]
