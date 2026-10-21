"""Scratch exploration - copy to tests/_scratch/test_explore_<topic>.py (git-ignored), edit, run:

    python -m pytest tests/_scratch/test_explore_<topic>.py -s -p no:cacheprovider

then open artifacts/explore/<topic>/*.png and read the printed [explore] lines.
Delete the file when the test is written.
"""
import pytest

from sbtest.tools.explore import Explorer

pytestmark = pytest.mark.native                      # drop it for web-only exploration


@pytest.mark.browser(bookmarks="seed_basic", extensions=["sample_addon"])   # the data the flow needs
def test_explore(web, native, pages, site):
    x = Explorer(web, native, "topic")              # -> artifacts/explore/topic/

    web.open(site.url("/index.html"))               # or pages.bookmarks.open(), site.page("Title")
    x.snap("start")

    # one try_step per user action; it snaps after each and never stops the run
    x.try_step("open the toolbar menu", lambda: native.click("extensions_button"))
    x.find_native("(?i)sb sample|pin|more options")  # exact UIA names / classes to put in the ui map
    x.esc()

    x.try_step("internal page", lambda: pages.extensions.open())
    x.find_web("SB Sample Addon")                     # DOM lines + ready locators
