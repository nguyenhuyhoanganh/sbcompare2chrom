"""Samsung Internet bookmarks page (internet://bookmarks).

STATUS: NOT VERIFIED on a Samsung build - inherits the upstream Chromium implementation.
Samsung rewrote many internal pages: explore the real page
(python -m sbtest.tools.dom bookmarks --interactive) and override the selector constants and
methods that differ here. Keep the public method names/return types of the parent so the
tests in tests/features/ keep working on both targets.
"""
from sbtest.pages.chromium.bookmarks import BookmarksPage as ChromiumBookmarksPage


class BookmarksPage(ChromiumBookmarksPage):
    pass
