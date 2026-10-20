"""Bookmarks sanity on Samsung Browser. Cases: testcases/bookmarks/sanity.md"""
import pytest

from sbtest.steps import step
from sbtest.utils import unique

samsung_only = pytest.mark.targets("samsung")


@samsung_only
@pytest.mark.native
@pytest.mark.sanity
@pytest.mark.case("BM-101")
def test_ctrl_d_bookmarks_current_page(web, native, pages, site):
    with step("1. Open 'Static page 1'"):
        web.open(site.url("/pages/page1.html"))
    with step("2. Ctrl+D", expected="'Page bookmarked.' toast with Edit, star filled"):
        native.hotkey("^d")
        toast = native.wait_dialog("bookmark_added")
        assert toast.button("Edit") is not None
        assert native.element("bookmark_star").element_info.name == "Remove from Bookmarks"
    with step("3. Open the bookmark manager", expected="'Static page 1' listed"):
        pages.bookmarks.open().wait_item("Static page 1")


@samsung_only
@pytest.mark.native
@pytest.mark.case("BM-102")
def test_star_removes_bookmark(web, native, pages, site):
    web.open(site.url("/pages/page1.html"))
    native.hotkey("^d")
    native.wait_dialog("bookmark_added")
    bookmarked = {"class_name": "StarView", "title": "Remove from Bookmarks"}
    with step("1. Click the filled star", expected="page no longer bookmarked"):
        # the "Page bookmarked." toast fades in over the star: invoke through UIA, and fall
        # back to the real mouse once the toast is gone
        native.click("bookmark_star", real_mouse=False)
        try:
            web.wait_until(lambda: not native.exists(bookmarked), timeout=3)
        except TimeoutError:
            try:
                native.wait_dialog("bookmark_added", timeout=1).wait_closed(timeout=15)
            except TimeoutError:
                pass  # toast already gone
            native.click(bookmarked)
        web.wait_until(lambda: not native.exists(bookmarked), message="star no longer 'Remove from Bookmarks'")
    with step("2. Open the bookmark manager", expected="'Static page 1' not listed"):
        bm = pages.bookmarks.open()
        bm.wait_item("Static page 1", present=False)


@pytest.mark.sanity
@pytest.mark.case("BM-103")
@pytest.mark.browser(bookmarks="seed_basic")
def test_edit_name_and_url(pages, site):
    bm = pages.bookmarks.open()
    name, url = unique("Edited"), site.url("/pages/page3.html")
    with step("2-3. Edit 'Static page 1': new name + web address, Save", expected="list updated"):
        bm.edit("Static page 1", name=name, url=url)
    assert "Static page 1" not in bm.titles()
    assert bm.item_url(name) == url


@samsung_only
@pytest.mark.case("BM-104")
@pytest.mark.browser(bookmarks="seed_basic")
def test_edit_from_context_menu(pages):
    bm = pages.bookmarks.open()
    name = unique("Renamed")
    with step("2. Right click 'Static page 2'", expected="Edit, Delete, Open all ... entries"):
        bm.item_menu("Static page 2", "Edit")
        bm.open_dialog()
    with step("2b. Change the name, Save", expected="new name listed"):
        bm._fill_edit_dialog(name, None)
        bm.save_dialog()
        bm.wait_item(name)


@samsung_only
@pytest.mark.sanity
@pytest.mark.case("BM-105")
@pytest.mark.browser(bookmarks="seed_basic")
def test_delete_from_context_menu_and_undo(pages):
    bm = pages.bookmarks.open()
    with step("2. Right click 'Static page 2' > Delete", expected="gone + '1 bookmark deleted'"):
        bm.item_menu("Static page 2", "Delete")
        bm.wait_item("Static page 2", present=False)
        assert "1 bookmark deleted" in bm.wait_toast("deleted")
    with step("3. Undo", expected="back in the list"):
        bm.undo()
        bm.wait_item("Static page 2")


@samsung_only
@pytest.mark.case("BM-106")
@pytest.mark.browser(bookmarks="seed_basic")
def test_select_all_and_delete(pages, web):
    bm = pages.bookmarks.open()
    with step("2a. Select all", expected="'3 selected'"):
        bm.toolbar("Select all")
        web.wait_until(lambda: all(bm.is_selected(t) for t in ("Static page 1", "Static page 2", "Work")),
                       message="all rows ticked")
        assert "3 selected" in web.text("bookmarks-app >>> bookmarks-toolbar >>> #overlay >>> #number-selected")
    with step("2b. Delete", expected="list empty, snack bar"):
        toast = bm.delete_selected()
        web.wait_until(lambda: not bm.titles(), message="bookmark list empty")
    assert "deleted" in toast.lower()


@pytest.mark.sanity
@pytest.mark.case("BM-107")
@pytest.mark.browser(bookmarks="seed_basic")
def test_open_bookmark(pages, web):
    bm = pages.bookmarks.open()
    with step("2. Click 'Static page 1'", expected="page loaded (new tab on Samsung)"):
        bm.open_item("Static page 1")
        web.switch_tab(title="Static page 1")


@pytest.mark.sanity
@pytest.mark.case("BM-108")
@pytest.mark.browser(bookmarks="seed_basic")
def test_bookmarks_survive_restart(session, pages):
    bm = pages.bookmarks.open()
    folder, name = unique("Kept folder"), unique("Kept name")
    with step("1. Add a folder, rename 'Static page 1'"):
        bm.add_folder(folder)
        bm.edit("Static page 1", name=name)
    with step("2-3. Restart, open the bookmark manager", expected="both still listed"):
        session.restart()
        bm = pages.of(session.web).bookmarks.open()
        bm.wait_item(folder)
        bm.wait_item(name)
