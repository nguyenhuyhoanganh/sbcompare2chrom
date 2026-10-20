"""Bookmarks from the browser toolbar (star, Ctrl+D toast, Bookmarks panel) on Samsung Browser.
Cases: testcases/bookmarks/toolbar.md. Windows only (native UI)."""
import pytest

from sbtest.steps import step
from sbtest.utils import unique

pytestmark = [pytest.mark.native, pytest.mark.targets("samsung")]


def type_into(native, field: str, text: str) -> None:
    el = native.element(field, in_main=False)
    el.set_focus()
    native.hotkey("^a", focus=False)
    native.type_text(text)


@pytest.mark.sanity
@pytest.mark.case("BM-101")
def test_ctrl_d_toast_and_rename(web, native, pages, site):
    name = unique("Renamed from toast")
    with step("1. Open 'Static page 1'"):
        web.open(site.url("/pages/page1.html"))
    with step("2. Ctrl+D", expected="toast 'Page bookmarked.' with Edit, star filled"):
        native.hotkey("^d")
        toast = native.wait_dialog("bookmark_added")
        assert native.exists("bookmark_star_filled")
    with step("3. Edit on the toast, new name, Save", expected="edit bubble with name and address"):
        toast.click("Edit")
        native.element("bookmark_edit_name", in_main=False)
        shown = native.element("bookmark_edit_url", in_main=False).get_value()   # shown without "http://"
        assert shown == site.url("/pages/page1.html").split("://", 1)[1], shown
        type_into(native, "bookmark_edit_name", name)
        native.click("bookmark_edit_save")
    with step("4. Open the bookmark manager", expected="listed with the new name"):
        bm = pages.bookmarks.open()
        bm.wait_item(name)
        assert "Static page 1" not in bm.titles()


@pytest.mark.case("BM-102")
def test_star_removes_bookmark(web, native, pages, site):
    web.open(site.url("/pages/page1.html"))
    native.hotkey("^d")
    native.wait_dialog("bookmark_added")
    with step("1. Click the filled star", expected="page no longer bookmarked"):
        # the toast fades in over the star: UIA invoke first, real mouse once the toast is gone
        native.click("bookmark_star", real_mouse=False)
        try:
            web.wait_until(lambda: not native.exists("bookmark_star_filled"), timeout=3)
        except TimeoutError:
            try:
                native.wait_dialog("bookmark_added", timeout=1).wait_closed(timeout=15)
            except TimeoutError:
                pass  # toast already gone
            native.click("bookmark_star_filled")
        web.wait_until(lambda: not native.exists("bookmark_star_filled"), message="star no longer filled")
    with step("2. Open the bookmark manager", expected="'Static page 1' not listed"):
        pages.bookmarks.open().wait_item("Static page 1", present=False)


@pytest.mark.sanity
@pytest.mark.case("BM-115")
@pytest.mark.browser(bookmarks="seed_basic")
def test_panel_browse_and_open(web, native, site):
    web.open(site.url("/index.html"))
    with step("1. Toolbar Bookmarks", expected="panel with PC bookmarks > Bookmark bar"):
        native.click("bookmarks_button")
        native.element("bookmarks_panel_folder", name="PC bookmarks")
    with step("2. Open 'Bookmark bar'", expected="Static page 1, Static page 2, Work listed"):
        native.click("bookmarks_panel_folder", name="Bookmark bar")
        for title in ("Static page 1", "Static page 2"):
            native.element("bookmarks_panel_item", name=title)
        native.element("bookmarks_panel_folder", name="Work")
    with step("3. Click 'Static page 1'", expected="the page opens"):
        native.click("bookmarks_panel_item", name="Static page 1")
        web.switch_tab(title="Static page 1")


@pytest.mark.case("BM-116")
def test_panel_add_page_and_expand(web, native, pages, site):
    title = unique("Panel page")
    web.open(site.page(title))
    web.wait_title(title)
    with step("1. Bookmarks panel > Add bookmark", expected="current page bookmarked, star filled"):
        native.click("bookmarks_button")
        native.click("bookmarks_panel_add_page")
        web.wait_until(lambda: native.exists("bookmark_star_filled"), message="star filled")
    with step("2. Panel > Expand", expected="bookmark manager opens and lists the page"):
        native.hotkey("{ESC}")
        native.click("bookmarks_button")
        native.click("bookmarks_panel_expand")
        web.switch_tab(url=web.cfg.page_url("bookmarks"))
        bm = pages.bookmarks
        bm.wait_loaded()
        bm.search(title)
        bm.wait_item(title)
