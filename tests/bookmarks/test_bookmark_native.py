"""Bookmarks through the browser's own UI (Windows only). Cases: testcases/bookmarks/bookmark_manager.md"""
import pytest

from sbtest.steps import step


@pytest.mark.native
@pytest.mark.case("BM-010")
def test_ctrl_d_bookmarks_page(web, native, pages, site):
    with step("1. Open 'Static page 1'"):
        web.open(site.url("/pages/page1.html"))
    with step("2. Ctrl+D -> bookmark bubble -> Done", expected="bubble shown"):
        native.hotkey("^d")
        bubble = native.wait_dialog("bookmark_added")
        bubble.click("Done")
        bubble.wait_closed()
    with step("3. Open the bookmark manager", expected="'Static page 1' listed"):
        pages.bookmarks.open()
        pages.bookmarks.wait_item("Static page 1")
