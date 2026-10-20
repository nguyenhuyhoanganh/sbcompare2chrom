"""Page objects for upstream Chromium / Google Chrome WebUI (chrome://...).

Verified against Chromium 141. They are the reference implementation: Samsung page
objects (sbtest/pages/samsung/) start as subclasses of these and override what differs.
"""
from sbtest.pages.chromium.bookmarks import BookmarksPage
from sbtest.pages.chromium.downloads import DownloadsPage
from sbtest.pages.chromium.extensions import ExtensionsPage
from sbtest.pages.chromium.history import HistoryPage
from sbtest.pages.chromium.settings import SettingsPage

__all__ = ["BookmarksPage", "DownloadsPage", "ExtensionsPage", "HistoryPage", "SettingsPage"]
